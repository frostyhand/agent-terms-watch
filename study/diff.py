#!/usr/bin/env python3
"""Compare this week's classified run with the stored state and write a change log.

State (data/state.json) holds, per site: terms and robots.txt hashes, agent stance and features,
and the user-triggered agents' robots.txt access. Full terms text is never stored in the repo.

Usage: python study/diff.py results/weekly data/state.json changes/2026-11-30.md
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

UAS = ["ChatGPT-User", "Claude-User", "Perplexity-User"]


def snapshot(run: Path) -> dict:
    sites = {json.loads(l)["site"]: json.loads(l) for l in open(run / "sites.jsonl")}
    out = {}
    for l in open(run / "classified.jsonl"):
        r = json.loads(l)
        s = sites.get(r["site"], {})
        now = r["now"] or {}
        out[r["site"]] = {
            "terms_sha": sorted(p["sha256"] for p in s.get("pages", []) if p.get("sha256") and p.get("source") == "live"),
            "robots_sha": s.get("robots", {}).get("sha256") if s.get("robots", {}).get("source") == "live" else None,
            "stance": now.get("stance"),
            "features": now.get("features"),
            "evidence": {k: v[:1] for k, v in (now.get("evidence") or {}).items() if k.startswith("agent")},
            "robots": {u: r["robots_now"][u]["home"] for u in UAS} if r["robots_now"].get("present") else None,
            "terms_urls": r["terms_urls"],
        }
    return out


def main(run: str, state_p: str, log_p: str):
    new = snapshot(Path(run))
    old = json.loads(Path(state_p).read_text()) if Path(state_p).exists() else {}
    lines = [f"# Changes found {date.today().isoformat()}\n"]
    n = 0
    for site in sorted(new):
        a, b = old.get(site), new[site]
        if not a:
            continue
        notes = []
        if a["stance"] and b["stance"] and a["stance"] != b["stance"]:
            notes.append(f"agent stance **{a['stance']} → {b['stance']}**")
            for k, v in b["evidence"].items():
                notes.append(f"  - {k}: \"{v[0][:300]}\"")
        if a.get("robots") and b.get("robots"):
            for u in UAS:
                if a["robots"][u] != b["robots"][u]:
                    notes.append(f"robots.txt {u}: {'allowed' if a['robots'][u] else 'blocked'} → {'allowed' if b['robots'][u] else 'blocked'}")
        if a["terms_sha"] and b["terms_sha"] and a["terms_sha"] != b["terms_sha"] and not notes:
            notes.append("terms text changed (no change in agent coding)")
        if a.get("robots_sha") and b.get("robots_sha") and a["robots_sha"] != b["robots_sha"] and not any("robots" in x for x in notes):
            notes.append("robots.txt changed (no change for user-triggered agents)")
        if notes:
            n += 1
            lines.append(f"## {site}\n" + "\n".join(f"- {x}" if not x.startswith("  ") else x for x in notes) + "\n")
    if n == 0:
        lines.append("No changes since the last run.\n")
    Path(log_p).parent.mkdir(parents=True, exist_ok=True)
    Path(log_p).write_text("\n".join(lines))
    # keep the old value for sites not reached this week, so a walled week is not read as a change
    merged = {**old, **{k: v for k, v in new.items() if v["stance"] is not None or k not in old}}
    Path(state_p).write_text(json.dumps(merged, indent=1, sort_keys=True))
    print(f"{n} sites changed; log {log_p}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
