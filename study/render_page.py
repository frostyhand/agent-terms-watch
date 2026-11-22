#!/usr/bin/env python3
"""Render docs/index.html: a searchable table of hand-checked shops and the headline counts.

Only shops in data/hand-check.csv with a stance_checked value are named. Everything else is counted, not named.

Usage: python study/render_page.py results/local-2026-11-22 data/hand-check.csv docs/index.html
"""
from __future__ import annotations

import csv
import html
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

LABEL = {
    "ban": "Bans AI agents",
    "allowlist": "Approved agents only",
    "conditional": "Agents must identify themselves",
    "permitted": "Allows agents, shopper answers for them",
    "mention": "Mentions agents, no clear rule",
    "ai_scrape_ban": "Names AI tools in an anti-scraping clause",
    "own_feature": "Only its own AI assistant",
    "none": "Nothing on AI agents",
}


def main(run: str, hand: str, out: str):
    rows = {json.loads(l)["site"]: json.loads(l) for l in open(Path(run) / "classified.jsonl")}
    checked = [h for h in csv.DictReader(open(hand)) if h.get("stance_checked")] if Path(hand).exists() else []
    dropped = {h["site"] for h in checked if h["stance_checked"] == "not_shop"}
    measured = [r for r in rows.values() if r["terms_found"] and r["now"] and not r["foreign_page"] and r["site"] not in dropped]
    cnt = Counter(r["now"]["stance"] for r in measured)
    for h in checked:
        r = rows.get(h["site"])
        if r and r["now"] and r in measured and h["stance_checked"] != "not_shop":
            cnt[r["now"]["stance"]] -= 1
            cnt[h["stance_checked"]] += 1
    rules = sum(cnt[k] for k in ("ban", "allowlist", "conditional", "permitted", "mention"))
    trs = []
    for h in sorted((h for h in checked if h["stance_checked"] not in ("none", "not_shop", "own_feature")), key=lambda h: h["site"]):
        r = rows.get(h["site"], {})
        rb = r.get("robots_now", {})
        blocked = [u for u in ("ChatGPT-User", "Claude-User", "Perplexity-User") if rb.get("present") and not rb[u]["home"]]
        url = (r.get("terms_urls") or [""])[0]
        trs.append(
            f"<tr><td><a href=\"{html.escape(url)}\" rel=\"nofollow\">{html.escape(h['site'])}</a></td>"
            f"<td><span class=\"tag {h['stance_checked']}\">{LABEL.get(h['stance_checked'], h['stance_checked'])}</span></td>"
            f"<td>{html.escape(h.get('quote', ''))}</td>"
            f"<td>{', '.join(blocked) or 'none'}</td>"
            f"<td>{html.escape(h.get('added', ''))}</td></tr>"
        )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Terms Watch</title>
<meta name="description" content="A weekly, open record of how US online shops treat AI shopping agents in their terms and robots.txt.">
<style>
:root{{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a65;--line:#e4e1d8;--accent:#2f5d50;--ban:#a23b2a;--allow:#2f5d50;--cond:#8a6a12;--mention:#55607a}}
@media (prefers-color-scheme: dark){{:root{{--bg:#151514;--fg:#ecebe6;--muted:#a3a19a;--line:#33322e;--accent:#8fc3b2;--ban:#e28b7b;--allow:#8fc3b2;--cond:#e2c06e;--mention:#a9b4cf}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1040px;margin:0 auto;padding:40px 16px 64px}}
h1{{font-size:2rem;margin:0 0 .25rem}} .sub{{color:var(--muted);margin:0 0 2rem}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:0 0 2rem}}
.stat{{border:1px solid var(--line);border-radius:10px;padding:14px}} .stat b{{display:block;font-size:1.6rem}}
input{{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:transparent;color:var(--fg);font:inherit;margin:0 0 12px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:.93rem}}
th,td{{text-align:left;vertical-align:top;padding:10px 8px;border-bottom:1px solid var(--line)}} th{{color:var(--muted);font-weight:600}}
a{{color:var(--accent)}} .tag{{white-space:nowrap;font-size:.8rem;font-weight:600}}
.ban{{color:var(--ban)}} .allowlist{{color:var(--allow)}} .conditional{{color:var(--cond)}} .mention,.own_feature{{color:var(--mention)}}
footer{{color:var(--muted);font-size:.85rem;margin-top:2rem}}
</style></head><body><main>
<h1>Agent Terms Watch</h1>
<p class="sub">Can your AI shopping agent legally shop here? A weekly, open record of how {len(rows)} US online shops treat AI agents in their terms and robots.txt. Updated {date.today().strftime('%d %b %Y')}.</p>
<div class="stats">
<div class="stat"><b>{len(measured)}</b>shops with terms read</div>
<div class="stat"><b>{rules}</b>with a rule about AI agents</div>
<div class="stat"><b>{cnt['ban']}</b>ban AI agents</div>
<div class="stat"><b>{cnt['allowlist'] + cnt['conditional']}</b>allow some agents, with conditions</div>
</div>
<input id="q" placeholder="Filter by shop or rule" aria-label="Filter">
<div class="wrap"><table id="t"><thead><tr><th>Shop</th><th>Rule</th><th>What the terms say</th><th>robots.txt blocks</th><th>Added</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
<footer>Only hand-checked shops are listed. Terms say what a shop claims the right to do, not what it enforces. Method, code and data: <a href="https://github.com/frostyhand/agent-terms-watch">github.com/frostyhand/agent-terms-watch</a>. By Tejaswi Suresh, RankSaga Ltd.</footer>
</main>
<script>
const q=document.getElementById('q'),rows=[...document.querySelectorAll('#t tbody tr')];
q.addEventListener('input',()=>{{const v=q.value.toLowerCase();rows.forEach(r=>r.style.display=r.textContent.toLowerCase().includes(v)?'':'none')}});
</script></body></html>"""
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(page)
    print(f"wrote {out}: {len(trs)} named shops")


if __name__ == "__main__":
    main(*sys.argv[1:4])
