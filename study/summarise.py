#!/usr/bin/env python3
"""Headline numbers from classified.jsonl (and an optional hand-check CSV that overrides codes).

Usage: python study/summarise.py results/local-2026-11-22 [results/hand-check.csv] > results/local-2026-11-22/summary.md
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

THEN_FROM, THEN_TO = "20250522", "20251130"  # a "year ago" copy must fall in this window
STANCES = ["ban", "allowlist", "conditional", "permitted", "mention", "ai_scrape_ban", "own_feature", "none"]
UAS = ["ChatGPT-User", "Claude-User", "Perplexity-User"]


def pct(a, b):
    return f"{a} of {b} ({100 * a / b:.1f}%)" if b else f"{a} of 0"


def main(run: str, hand: str | None):
    rows = [json.loads(l) for l in open(Path(run) / "classified.jsonl")]
    overrides = {}
    if hand and Path(hand).exists():
        for h in csv.DictReader(open(hand)):
            if h.get("stance_checked"):
                overrides[h["site"]] = h
    for r in rows:
        if r["site"] in overrides and r["now"]:
            r["now"]["stance"] = overrides[r["site"]]["stance_checked"]
        elif r["site"] in overrides and overrides[r["site"]]["stance_checked"] != "not_shop":
            r["now"] = {"stance": overrides[r["site"]]["stance_checked"], "features": {}, "evidence": {}}
            r["terms_found"] = True

    measured = [r for r in rows if r["terms_found"] and r["now"] and not r["foreign_page"] and r["now"]["stance"] != "not_shop"]
    p = print
    p(f"# Agent Terms Watch: summary for `{Path(run).name}`\n")
    p(f"- Shops in panel: {len(rows)} (named {sum(r['panel'] == 'named' for r in rows)}, top sites {sum(r['panel'] != 'named' for r in rows)})")
    p(f"- Terms page found and read: {pct(len(measured), len(rows))}; from the live site {sum('live' in r['terms_source'] for r in measured)}, "
      f"archive only {sum(r['terms_source'] == ['wayback'] for r in measured)}; dropped as non-US page {sum(r['foreign_page'] for r in rows)}")
    p(f"- Hand-checked overrides applied: {len(overrides)}\n")

    for label, group in (("All shops", measured), ("Named US retailers", [r for r in measured if r["panel"] == "named"]),
                         ("Top US shopping sites", [r for r in measured if r["panel"] != "named"])):
        c = Counter(r["now"]["stance"] for r in group)
        f = lambda k: sum(r["now"]["features"].get(k, False) for r in group)  # noqa: E731
        p(f"## {label} (n = {len(group)})\n")
        p("| Measure | Shops |\n|---|---|")
        for s in STANCES:
            p(f"| Agent stance: {s} | {pct(c[s], len(group))} |")
        for k, name in (("agent_human", "Agent rule requires human review"), ("agent_liability", "Agent rule puts shopper or agent on the hook"),
                        ("agent_signed", "Mentions signed or verified agent identity"), ("agent_legacy", "Older \"intelligent agent\" boilerplate only"), ("automation_ban", "Older robot / automated-means clause"),
                        ("auto_purchase_ban", "Automated ordering named"), ("ai_training_ban", "Bans using content to train AI")):
            p(f"| {name} | {pct(f(k), len(group))} |")
        p("")

    # a year ago
    paired = [r for r in measured if r["then"] and any(THEN_FROM <= v[:8] <= THEN_TO for v in r["then_ts"].values() if v)]
    p(f"## Change over the year (shops with an archived copy dated {THEN_FROM} to {THEN_TO}, n = {len(paired)})\n")
    RULE = ("ban", "allowlist", "conditional", "permitted", "mention")
    then_rule = sum(r["then"]["stance"] in RULE for r in paired)
    now_rule = sum(r["now"]["stance"] in RULE for r in paired)
    added = [r["site"] for r in paired if r["then"]["stance"] not in RULE and r["now"]["stance"] in RULE]
    p(f"- Explicit agent wording a year ago: {pct(then_rule, len(paired))}; now: {pct(now_rule, len(paired))}")
    p(f"- Added agent wording this year: {len(added)}: {', '.join(sorted(added)[:60])}")
    tb = sum(r["then"]["features"]["ai_training_ban"] for r in paired)
    nb = sum(r["now"]["features"]["ai_training_ban"] for r in paired)
    p(f"- AI training ban a year ago {pct(tb, len(paired))}; now {pct(nb, len(paired))}\n")

    # robots.txt
    rb = [r for r in rows if r["robots_now"].get("present")]
    p(f"## robots.txt and user-triggered agents (robots.txt read for {pct(len(rb), len(rows))})\n")
    p("| Agent token | Named in robots.txt | Blocked from home page | Blocked from /checkout | Blocked from home a year ago* |\n|---|---|---|---|---|")
    rb_then = [r for r in rb if r["robots_then"].get("present")]
    for ua in UAS:
        named = sum(r["robots_now"][ua]["named"] for r in rb)
        home = sum(not r["robots_now"][ua]["home"] for r in rb)
        chk = sum(not r["robots_now"][ua]["checkout"] for r in rb)
        then = sum(not r["robots_then"][ua]["home"] for r in rb_then)
        p(f"| {ua} | {pct(named, len(rb))} | {pct(home, len(rb))} | {pct(chk, len(rb))} | {pct(then, len(rb_then))} |")
    p(f"\n*Among {len(rb_then)} shops with an archived robots.txt from on or before the backfill date.\n")
    p(f"- robots.txt carries a comment about agents or AI: {pct(sum(r['robots_now'].get('agent_comment', False) for r in rb), len(rb))}\n")
    # platform default policy (Shopify)
    sh = [r for r in rb if r["robots_now"].get("shopify")]
    p("## Platform policy in robots.txt (Shopify defaults)\n")
    p(f"- Shopify stores (robots.txt names Shopify): {len(sh)}")
    p(f"- Now carry the 2026 \"Agents must\" block: {pct(sum(r['robots_now'].get('agents_must', False) for r in rb), len(rb))}; "
      f"also pitch the Shop skill to agents (SKILL.md): {sum(r['robots_now'].get('skill_pitch', False) for r in rb)}")
    p(f"- Still carry the older \"Checkouts are for humans\" box: {sum(r['robots_now'].get('humans_only', False) for r in rb)}")
    pr = [r for r in rb if r["robots_then"].get("present")]
    was = [r for r in pr if r["robots_then"].get("humans_only")]
    p(f"- A year ago, \"Checkouts are for humans\": {pct(len(was), len(pr))}; of those, now \"Agents must\": {pct(sum(r['robots_now'].get('agents_must', False) for r in was), len(was))}\n")

    # contradictions
    both = [r for r in measured if r["robots_now"].get("present")]
    p("## Terms and robots.txt disagree\n")
    ban_open = [r["site"] for r in both if r["now"]["stance"] in ("ban",) and r["robots_now"]["ChatGPT-User"]["home"]]
    open_block = [r["site"] for r in both if r["now"]["stance"] in ("none", "mention", "own_feature") and not r["robots_now"]["ChatGPT-User"]["home"]]
    allow_block = [r["site"] for r in both if r["now"]["stance"] == "allowlist" and not all(r["robots_now"][u]["home"] for u in UAS)]
    p(f"- Terms ban agents, robots.txt lets ChatGPT-User in: {len(ban_open)}: {', '.join(sorted(ban_open)[:40])}")
    p(f"- Terms silent on agents, robots.txt blocks ChatGPT-User: {len(open_block)}: {', '.join(sorted(open_block)[:40])}")
    p(f"- Terms allowlist some agents, robots.txt blocks at least one user-triggered agent: {len(allow_block)}: {', '.join(sorted(allow_block)[:40])}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
