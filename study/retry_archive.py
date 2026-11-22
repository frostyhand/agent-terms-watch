#!/usr/bin/env python3
"""Second pass for pages that came back walled or thin: ask the Wayback Machine again, slowly.

Rewrites sites.jsonl in place (a copy is kept as sites.before-retry.jsonl).

Usage: python study/retry_archive.py results/local-2026-11-22 --backfill 20251122
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from fetch import UA, Wayback, decode, page_text, slug, terms_links  # noqa: E402


CAPTCHA = ("captcha", "splashui", "challenge", "blocked")


CDX_LOCK = asyncio.Lock()
CDX_GAP = 2.0  # seconds between index queries; the archive rate-limits hard
_last = [0.0]


async def archive_get(client: httpx.AsyncClient, url: str, **kw) -> httpx.Response | None:
    """One request to the archive, spaced out, with long back-off on 429."""
    for attempt in range(5):
        async with CDX_LOCK:
            wait = _last[0] + CDX_GAP - asyncio.get_event_loop().time()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                r = await client.get(url, timeout=90, **kw)
            except Exception:
                r = None
            _last[0] = asyncio.get_event_loop().time()
        if r is not None and r.status_code == 429:
            print("archive 429, backing off", file=sys.stderr)
            await asyncio.sleep(90 * (attempt + 1))
            continue
        return r
    return None


async def good_capture(client: httpx.AsyncClient, url: str, to: str | None = None, min_chars: int = 1500, raw: bool = False) -> dict | None:
    """Newest real capture (status 200, not a captcha, enough text), walking back through the index."""
    params = {"url": url, "output": "json", "filter": "statuscode:200", "fl": "timestamp,original", "collapse": "digest", "limit": "-10"}
    if to:
        params["to"] = to
        params["from"] = str(int(to[:4]) - 1) + to[4:]
    else:
        params["from"] = "20260501"
    r = await archive_get(client, "https://web.archive.org/cdx/search/cdx", params=params)
    try:
        rows = r.json()[1:] if r is not None and r.status_code == 200 and r.text.strip() else []
    except Exception:
        rows = []
    for t, orig in reversed(rows):
        snap = await archive_get(client, f"https://web.archive.org/web/{t}id_/{orig}")
        if snap is None or snap.status_code != 200 or any(c in str(snap.url).lower() for c in CAPTCHA):
            continue
        text = page_text(decode(snap.content))
        if len(text) >= min_chars and "captcha" not in text[:3000].lower():
            return {"ts": t, "text": text, "html": decode(snap.content) if raw else None, "url": orig}
    return None


async def fix(rec: dict, wb: Wayback, out: Path, backfill: str | None) -> int:
    fixed = 0
    name = slug(rec["site"])
    best = {}
    for p in rec.get("pages", []):
        if p.get("file"):
            best[p["kind"]] = min(best.get(p["kind"], 99), p.get("score", 9))
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    for p in rec.get("pages", []):
        failed = not p.get("file") and (p.get("thin") is not None or p.get("walled") or p.get("status") in (403, 418, 429, 451, 503))
        if not failed or p.get("score", 9) >= best.get(p["kind"], 99):
            continue
        got = await good_capture(wb.client, p["url"])
        if not got:
            continue
        fn = f"{name}__{p['kind']}.txt"
        (out / "terms" / fn).write_text(got["text"])
        for q in rec["pages"]:  # the page this one replaces
            if q.get("file") == fn:
                q.pop("file")
                q["replaced"] = True
        p.update(source="wayback", wayback_ts=got["ts"], chars=len(got["text"]), sha256=hashlib.sha256(got["text"].encode()).hexdigest(), file=fn, retried=True)
        p.pop("thin", None)
        best[p["kind"]] = p.get("score", 9)
        fixed += 1
        if backfill:
            then = await good_capture(wb.client, p["url"], to=backfill)
            bf = rec.setdefault("backfill", {"target": backfill})
            if then:
                (out / "terms_then" / fn).write_text(then["text"])
                bf[p["kind"] + "_ts"] = then["ts"]
            else:
                (out / "terms_then" / fn).unlink(missing_ok=True)
                bf.pop(p["kind"] + "_ts", None)
    return fixed


async def rediscover(rec: dict, wb: Wayback, out: Path, backfill: str | None) -> int:
    """No terms page at all: find the terms link on a real archived copy of the home page."""
    if any(p.get("file") for p in rec.get("pages", [])):
        return 0
    host = rec["origin"].split("//")[-1].rstrip("/")
    home = await good_capture(wb.client, host + "/", min_chars=300, raw=True)
    if not home:
        return 0
    cands = terms_links(home["html"], "https://" + host + "/", rec["origin"])
    name = slug(rec["site"])
    got = set()
    for score, kind, url in cands[:6]:
        if kind in got:
            continue
        page = await good_capture(wb.client, url)
        if not page:
            continue
        fn = f"{name}__{kind}.txt"
        (out / "terms" / fn).write_text(page["text"])
        rec.setdefault("pages", []).append({"kind": kind, "url": url, "score": score, "source": "wayback", "wayback_ts": page["ts"],
                                            "chars": len(page["text"]), "sha256": hashlib.sha256(page["text"].encode()).hexdigest(),
                                            "file": fn, "retried": True, "rediscovered": True})
        got.add(kind)
        if backfill:
            then = await good_capture(wb.client, url, to=backfill)
            if then:
                (out / "terms_then" / fn).write_text(then["text"])
                rec.setdefault("backfill", {"target": backfill})[kind + "_ts"] = then["ts"]
    rec["discovery"] = rec.get("discovery", "") + "+archive_home" if got else rec.get("discovery")
    return len(got)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--backfill")
    a = ap.parse_args()
    out = Path(a.run)
    src = out / "sites.jsonl"
    shutil.copy(src, out / "sites.before-retry.jsonl")
    recs = [json.loads(l) for l in open(src)]
    async with httpx.AsyncClient(follow_redirects=True, timeout=60, headers={"user-agent": UA}) as c:
        wb = Wayback(c)
        sem = asyncio.Semaphore(2)

        async def go(r):
            async with sem:
                return await fix(r, wb, out, a.backfill) + await rediscover(r, wb, out, a.backfill)

        counts = await asyncio.gather(*(go(r) for r in recs))
    with open(src, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    print(f"fixed {sum(counts)} pages on {sum(1 for c in counts if c)} sites", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
