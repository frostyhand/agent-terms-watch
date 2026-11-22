#!/usr/bin/env python3
"""List shops to hand-check: every shop with an agent stance other than none, plus a random 40 coded none.
Usage: python study/handcheck_list.py results/local-2026-11-22 > results/local-2026-11-22/to-check.md"""
import json, random, sys
from pathlib import Path
rows = [json.loads(l) for l in open(Path(sys.argv[1]) / "classified.jsonl")]
coded = [r for r in rows if r["now"] and r["now"]["stance"] != "none"]
none = [r for r in rows if r["now"] and r["now"]["stance"] == "none" and not r["foreign_page"]]
random.seed(20261122)
sample = random.sample(none, min(40, len(none)))
for label, group in (("Coded with an agent rule", coded), ("Random sample coded none", sample)):
    print(f"# {label} ({len(group)})\n")
    for r in sorted(group, key=lambda x: x["site"]):
        print(f"## {r['site']} | {r['now']['stance']} | then: {(r['then'] or {}).get('stance')} {r['then_ts']} | {' '.join(r['terms_urls'])} | foreign={r['foreign_page']}")
        for k, v in r["now"]["evidence"].items():
            if k.startswith("agent"):
                print(f"- {k}: {v[0][:400]}")
        print()
