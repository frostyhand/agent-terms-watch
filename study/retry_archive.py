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
from fetch import UA, Wayback, decode, page_text, slug  # noqa: E402


CAPTCHA = ("captcha", "splashui", "challenge", "blocked")


async def good_capture(client: httpx.AsyncClient, url: str, to: str | None = None) -> dict | None:
    """Newest real capture (status 200, not a captcha, 1,500+ characters), walking back through the index."""
    params = {"url": url, "output": "json", "filter": "statuscode:200", "fl": "timestamp,original", "limit": "-12"}
    if to:
        params["to"] = to
    for attempt in range(3):
        try:
            r = await client.get("https://web.archive.org/cdx/search/cdx", params=params, timeout=90)
            rows = r.json()[1:] if r.status_code == 200 and r.text.strip() else []
            break
        except Exception:
            rows = []
            await asyncio.sleep(10 * (attempt + 1))
    for t, orig in reversed(rows):
        try:
            snap = await client.get(f"https://web.archive.org/web/{t}id_/{orig}", timeout=60)
        except Exception:
            continue
        if snap.status_code != 200 or any(c in str(snap.url).lower() for c in CAPTCHA):
            continue
        text = page_text(decode(snap.content))
        if len(text) >= 1500 and "captcha" not in text[:3000].lower():
            return {"ts": t, "text": text}
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
        sem = asyncio.Semaphore(4)

        async def go(r):
            async with sem:
                return await fix(r, wb, out, a.backfill)

        counts = await asyncio.gather(*(go(r) for r in recs))
    with open(src, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    print(f"fixed {sum(counts)} pages on {sum(1 for c in counts if c)} sites", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
