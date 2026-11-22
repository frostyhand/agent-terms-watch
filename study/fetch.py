#!/usr/bin/env python3
"""Agent Terms Watch: fetch each shop's robots.txt and terms pages.

For each site in the panel:
  1. robots.txt, raw, saved as is.
  2. The home page, to find links to the site's terms of use and terms of sale
     (link text or path), with common paths as a fallback.
  3. Up to two terms pages (one "use", one "sale"), saved as plain text.
  4. If the live terms page is walled or missing, the latest Wayback Machine copy.
  5. With --backfill, the Wayback copy of the same terms URL and of robots.txt
     closest to one year earlier, so changes over the year can be counted.

Read-only. Respects robots.txt for our own token. One request at a time per site,
with a pause between requests. No LLMs.

Usage:
  python study/fetch.py --panel data/panel.csv --out results/run --backfill 20251122
  python study/fetch.py --sites ebay.com,amazon.com --out results/try
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from lxml import html as lhtml
from protego import Protego

VERSION = "0.1.0"
UA = f"AgenticWebCensus/{VERSION} (+https://github.com/frostyhand/agentic-web-census; research; read-only; terms check)"
UA_TOKEN = "AgenticWebCensus"
TIMEOUT = 15.0
MAX_PAGE = 4 * 1024 * 1024
PAUSE = 0.8
CONCURRENCY = 16
WAYBACK_CONCURRENCY = 6

WALL_STATUSES = {401, 403, 405, 418, 429, 451, 503}
WALL_BODY_RE = re.compile(
    r"Just a moment\.\.\.|cf-chl|challenge-platform|px-captcha|_pxCaptcha|Access Denied</|"
    r"Request unsuccessful\. Incapsula|perimeterx|datadome|captcha-delivery|Pardon Our Interruption|"
    r"Robot or human\?|<title>Access Denied",
    re.I,
)

USE_TEXT_RE = re.compile(
    r"^\s*(?:website |site |online )?(?:terms of (?:use|service)|conditions of use|terms (?:and|&) conditions(?: of use)?|"
    r"user agreement|terms|legal(?: terms| notices?)?|terms & policies)\s*$",
    re.I,
)
SALE_TEXT_RE = re.compile(r"^\s*(?:terms|conditions) (?:of|and conditions of) (?:sale|purchase)\s*$", re.I)
PATH_RE = re.compile(r"terms|conditions|user-?agreement|/legal|/tos\b", re.I)
SALE_PATH_RE = re.compile(r"(?:terms|conditions)[-_ ]?(?:of[-_ ]?)?(?:sale|purchase)", re.I)
SKIP_RE = re.compile(r"mailto:|tel:|javascript:|/account|/login|/signin|/cart|privacy|cookie|accessib|gift-?card|reward|loyalty|sms|text-?messag|sweepstake|promo", re.I)
FALLBACK_PATHS = [
    "/terms", "/terms-of-use", "/terms-of-service", "/terms-and-conditions",
    "/policies/terms-of-service", "/pages/terms-of-service", "/pages/terms-of-use",
    "/pages/terms-and-conditions", "/legal/terms", "/help/terms", "/legal",
]


# ---------- helpers ----------

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def decode(b: bytes) -> str:
    return b.decode("utf-8", errors="replace")


def page_text(body: str) -> str:
    try:
        doc = lhtml.fromstring(body)
    except Exception:
        return ""
    for bad in doc.xpath("//script|//style|//noscript|//svg|//template"):
        bad.drop_tree()
    for blk in doc.xpath("//p|//li|//div|//br|//h1|//h2|//h3|//h4|//h5|//h6|//tr|//section|//article"):
        blk.tail = "\n" + (blk.tail or "")
    txt = doc.text_content()
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in txt.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def reg_domain(host: str) -> str:
    parts = (host or "").lower().split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_site(url: str, origin: str) -> bool:
    return reg_domain(urlparse(url).hostname or "") == reg_domain(urlparse(origin).hostname or "")


def walled(r: dict) -> bool:
    if r.get("status") in WALL_STATUSES:
        return True
    if re.search(r"captcha|challenge|splashui|/blocked|px-|distil", urlparse(r.get("final") or "").path + "?" + (urlparse(r.get("final") or "").query), re.I):
        return True
    return r.get("status") == 200 and bool(WALL_BODY_RE.search(decode(r.get("body") or b"")[:20000]))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "_", s.lower()).strip("_")[:120]


class Site:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.last = 0.0

    async def get(self, url: str) -> dict:
        wait = self.last + PAUSE - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        rec: dict = {"url": url}
        try:
            async with self.client.stream("GET", url, headers={"user-agent": UA, "accept": "text/html,text/plain,*/*;q=0.8", "accept-language": "en-US,en;q=0.9"}) as r:
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    if len(buf) > MAX_PAGE:
                        break
                rec.update(status=r.status_code, final=str(r.url), type=r.headers.get("content-type", "").lower(), body=bytes(buf))
        except Exception as e:
            rec.update(status=None, error=type(e).__name__)
        self.last = time.monotonic()
        return rec


# ---------- Wayback ----------

class Wayback:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.sem = asyncio.Semaphore(WAYBACK_CONCURRENCY)

    async def closest(self, url: str, ts: str, before: bool = False) -> dict | None:
        """Closest 200 capture to ts (YYYYMMDD), in one request: the archive redirects to the nearest
        capture. With before=True a capture dated after ts is dropped (the year-ago window is then
        enforced again in summarise.py)."""
        async with self.sem:
            for attempt in range(3):
                try:
                    r = await self.client.get(f"https://web.archive.org/web/{ts}id_/{url}", timeout=45)
                    if r.status_code == 429:
                        await asyncio.sleep(20 * (attempt + 1))
                        continue
                    if r.status_code != 200:
                        return None
                    m = re.search(r"/web/(\d{14})id_/(.+)$", str(r.url))
                    if not m:
                        return None
                    if before and m.group(1)[:8] > ts:
                        return None
                    return {"ts": m.group(1), "url": m.group(2), "body": r.content[:MAX_PAGE]}
                except Exception:
                    await asyncio.sleep(3 * (attempt + 1))
        return None


# ---------- discovery ----------

def terms_links(body: str, base: str, origin: str) -> list[tuple[int, str, str]]:
    """(score, kind, url): lower score is better."""
    try:
        doc = lhtml.fromstring(body)
    except Exception:
        return []
    out = []
    for a in doc.xpath("//a[@href]"):
        href = urljoin(base, a.get("href", "")).split("#")[0]
        label = re.sub(r"\s+", " ", a.text_content() or "").strip()[:80]
        if not href.startswith("http") or not same_site(href, origin) or SKIP_RE.search(href):
            continue
        path = urlparse(href).path
        if SALE_TEXT_RE.search(label) or SALE_PATH_RE.search(path):
            out.append((0 if SALE_TEXT_RE.search(label) else 1, "sale", href))
        elif USE_TEXT_RE.search(label):
            out.append((0 if re.search(r"use|service|conditions|agreement", label, re.I) else 2, "use", href))
        elif PATH_RE.search(path) and len(label) < 40:
            out.append((3, "use", href))
    return sorted(set(out))


async def one(row: dict, client: httpx.AsyncClient, wb: Wayback, outdir: Path, backfill: str | None, sem) -> dict:
    async with sem:
        site = Site(client)
        origin = row["origin"].rstrip("/")
        name = slug(row["site"])
        res: dict = {"site": row["site"], "panel": row["panel"], "segment": row.get("segment", ""), "origin": origin, "ts": now(), "v": VERSION}

        # robots.txt
        rb = await site.get(origin + "/robots.txt")
        robots_txt = decode(rb.get("body") or b"") if rb.get("status") == 200 and "html" not in rb.get("type", "") else ""
        res["robots"] = {"status": rb.get("status"), "error": rb.get("error"), "final": rb.get("final"), "bytes": len(robots_txt),
                         "sha256": hashlib.sha256(robots_txt.encode()).hexdigest() if robots_txt else None, "source": "live"}
        if not robots_txt:
            snap = await wb.closest(f"{urlparse(origin).hostname}/robots.txt", datetime.now(timezone.utc).strftime("%Y%m%d"))
            if snap and b"<html" not in snap["body"][:500].lower():
                robots_txt = decode(snap["body"])
                res["robots"].update(source="wayback", wayback_ts=snap["ts"], bytes=len(robots_txt),
                                     sha256=hashlib.sha256(robots_txt.encode()).hexdigest())
        if robots_txt:
            (outdir / "robots" / f"{name}.txt").write_text(robots_txt)
        ours = Protego.parse(robots_txt) if robots_txt and res["robots"]["source"] == "live" else None

        def allowed(u: str) -> bool:
            return ours.can_fetch(u, UA_TOKEN) if ours else True

        # home page and terms discovery
        cands: list[tuple[int, str, str]] = []
        home = None
        if allowed(origin + "/"):
            home = await site.get(origin + "/")
            res["home"] = {"status": home.get("status"), "error": home.get("error"), "final": home.get("final"), "walled": walled(home)}
            if home.get("status") == 200 and not walled(home):
                cands = terms_links(decode(home["body"]), home["final"], origin)
        else:
            res["home"] = {"robots_disallow": True}
        if not cands:
            snap = await wb.closest(urlparse(origin).hostname + "/", datetime.now(timezone.utc).strftime("%Y%m%d"))
            if snap:
                cands = terms_links(decode(snap["body"]), origin + "/", origin)
                res["home"]["wayback_ts"] = snap["ts"]
        res["discovery"] = "links" if cands else "fallback"
        if not cands and not res["home"].get("walled") and res["home"].get("status") not in WALL_STATUSES:
            cands = [(5, "use", origin + p) for p in FALLBACK_PATHS]

        # fetch up to one "use" and one "sale" page
        res["pages"] = []
        got: set[str] = set()
        tried = 0
        for score, kind, url in cands:
            if kind in got or tried >= 8:
                continue
            tried += 1
            page = {"kind": kind, "url": url, "score": score}
            text, source = "", None
            if allowed(url):
                r = await site.get(url)
                page.update(status=r.get("status"), error=r.get("error"), final=r.get("final"), walled=walled(r))
                if r.get("status") == 200 and not page["walled"] and "html" in r.get("type", "html"):
                    text, source = page_text(decode(r["body"])), "live"
            else:
                page["robots_disallow"] = True
            if len(text) < 1500 and score < 5:  # walled, missing, or rendered by script: try the archive
                snap = await wb.closest(url, datetime.now(timezone.utc).strftime("%Y%m%d"))
                if snap:
                    t2 = page_text(decode(snap["body"]))
                    if len(t2) > len(text):
                        text, source = t2, "wayback"
                        page["wayback_ts"] = snap["ts"]
            if len(text) < 1500:
                if score >= 5:
                    continue  # a fallback path that does not exist
                page["thin"] = len(text)
                text = ""
            page.update(source=source, chars=len(text), sha256=hashlib.sha256(text.encode()).hexdigest() if text else None)
            if text:
                fn = f"{name}__{kind}.txt"
                (outdir / "terms" / fn).write_text(text)
                page["file"] = fn
                got.add(kind)
            res["pages"].append(page)

        # one year earlier, from the archive
        if backfill:
            res["backfill"] = {"target": backfill}
            snap = await wb.closest(f"{urlparse(origin).hostname}/robots.txt", backfill, before=True)
            if snap and b"<html" not in snap["body"][:500].lower():
                (outdir / "robots_then" / f"{name}.txt").write_bytes(snap["body"])
                res["backfill"]["robots_ts"] = snap["ts"]
            for p in res["pages"]:
                if not p.get("file"):
                    continue
                snap = await wb.closest(p.get("final") or p["url"], backfill, before=True)
                if snap is None and p.get("final") and p["final"] != p["url"]:
                    snap = await wb.closest(p["url"], backfill, before=True)
                if snap:
                    t = page_text(decode(snap["body"]))
                    if len(t) >= 1500:
                        fn = f"{name}__{p['kind']}.txt"
                        (outdir / "terms_then" / fn).write_text(t)
                        res["backfill"][p["kind"] + "_ts"] = snap["ts"]
        return res


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel")
    ap.add_argument("--sites")
    ap.add_argument("--out", required=True)
    ap.add_argument("--backfill", help="YYYYMMDD: also fetch archive copies from on or before this date")
    ap.add_argument("--shard", default="0/1", help="i/n: only every n-th site starting at i")
    a = ap.parse_args()
    if a.panel:
        rows = list(csv.DictReader(open(a.panel)))
    else:
        rows = [{"site": s, "panel": "adhoc", "segment": "", "origin": "https://www." + s} for s in a.sites.split(",")]
    i, n = map(int, a.shard.split("/"))
    rows = rows[i::n]
    done_sites = set()
    if (Path(a.out) / "sites.jsonl").exists():  # resume
        done_sites = {json.loads(l)["site"] for l in open(Path(a.out) / "sites.jsonl")}
        rows = [r for r in rows if r["site"] not in done_sites]
        print(f"resuming: {len(done_sites)} done, {len(rows)} to go", file=sys.stderr)
    out = Path(a.out)
    for d in ("robots", "terms", "robots_then", "terms_then"):
        (out / d).mkdir(parents=True, exist_ok=True)
    limits = httpx.Limits(max_connections=60, max_keepalive_connections=20)
    async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT, limits=limits, http2=False) as client:
        wb = Wayback(httpx.AsyncClient(follow_redirects=True, timeout=40, headers={"user-agent": UA}))
        sem = asyncio.Semaphore(CONCURRENCY)
        done = 0
        with open(out / "sites.jsonl", "a") as f:
            for coro in asyncio.as_completed([one(r, client, wb, out, a.backfill, sem) for r in rows]):
                try:
                    res = await coro
                except Exception as e:
                    print("error", type(e).__name__, e, file=sys.stderr)
                    continue
                f.write(json.dumps(res) + "\n")
                f.flush()
                done += 1
                if done % 25 == 0:
                    print(f"{done}/{len(rows)}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
