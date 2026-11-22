# Agent Terms Watch

Can your AI shopping agent legally shop here? Agent Terms Watch is an open, weekly record of how US online shops treat AI agents that browse and buy for people. It reads two things for each shop:

1. **The terms of use and terms of sale.** Do they ban AI agents, allow only named agents, allow agents that identify themselves, or say nothing? Do they require human review of orders? Do they make the shopper answer for what the agent does?
2. **robots.txt.** Does it name or block the user-triggered agents (ChatGPT-User, Claude-User, Perplexity-User) from the home page and the checkout?

A year-ago copy of each page from the Internet Archive's Wayback Machine shows what changed during 2026.

## Why

In 2026 shopping agents moved from demos to checkouts, and retailers answered in their legal terms. Amazon's Conditions of Use now carry "Agent Terms" that require an agent to name itself in its user agent string. eBay's User Agreement bans "buy-for-me agents" and "LLM-driven bots". Target's terms allow only a short list of approved agents. Most shops have not said anything yet. The largest single policy sits in Shopify's default robots.txt, which in autumn 2026 switched from "Checkouts are for humans" to rules for agents that identify themselves and get the buyer's authorization. The gap between what terms say and what robots.txt allows is large. Shoppers, agent builders and regulators have had no shared, dated record of these rules. This is that record.

## Security

Every rule here is also a security control. An agent that must identify itself can be told apart from an attacker's bot. An allowlist decides who may act on a shopper's account. A human review rule is a confirmation step before money moves. The study records whether a shop's terms mention signed or verified agent identity (for example Web Bot Auth or card network agent programs), and flags where terms and robots.txt disagree.

## Panel

649 US shops: 157 named US retailers across mass merchants, department stores, apparel, home, electronics, beauty, pets, sporting goods, grocery and direct-to-consumer brands, and 492 shopping sites from the Chrome UX Report's US top 10,000 origins (October 2026) that publish priced product markup. The panel is in [`data/panel.csv`](data/panel.csv).

## Method

See [`PROTOCOL.md`](PROTOCOL.md). In short: honest crawler (`AgenticWebCensus`, read-only, obeys robots.txt), terms pages found from each home page's own links, archive copies when a page is walled, rule-based coding with no language models, and a hand check of every shop counted as having an agent rule before it is named.

## Outputs

- `data/runs/<date>-summary.md`: headline numbers for each weekly run.
- `data/runs/<date>-classified.csv`: one row per shop.
- `changes/<date>.md`: what changed since the previous week.
- `data/state.json`: hashes, codes and short quoted evidence for each shop.

Full terms text is not republished here. Each row links to the shop's own page.

## Limits

Terms say what a shop claims the right to do, not what it enforces. Some pages are walled to honest crawlers or rendered by script; those are read from the archive or reported as not measured. Rule-based coding misses unusual wording, which is why named findings are hand-checked.

## Author

Tejaswi Suresh, RankSaga Ltd. Code under Apache-2.0; coded data under CC BY 4.0.
