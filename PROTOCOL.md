# Protocol v1 (22 Nov 2026)

## Questions

1. What share of US online shops have an explicit rule about AI agents acting for shoppers in their terms, and what kind (ban, allowlist, conditional on identification, mention only)?
2. How many added such wording between late 2025 and late 2026?
3. How do robots.txt rules for user-triggered agents (ChatGPT-User, Claude-User, Perplexity-User) compare, now and a year ago?
4. Where do terms and robots.txt disagree?
5. Security part: do terms require agents to identify themselves, require human review, name signed or verified agent identity, or shift responsibility for agent actions to the shopper?

## Panel

`data/panel.csv`, frozen 22 Nov 2026: 157 named US retailers (one domain each) plus 492 origins from CrUX `country_us.202610` top 10k that published priced schema.org Product markup in the 22 Nov 2026 US product-page crawl, plus the Black Friday Price Truth panel sites. 649 sites.

## Collection (`study/fetch.py`)

- User agent `AgenticWebCensus/0.1.0 (...; research; read-only; terms check)`; robots.txt obeyed for that token; one request at a time per site, 0.8 s apart.
- robots.txt saved raw. If missing or walled, the latest Wayback copy is used and marked.
- Terms discovery from the home page's own links: link text such as "Terms of Use", "Conditions of Use", "Terms and Conditions", "User Agreement", "Terms of Sale", or a path naming terms or conditions. If none are found, the archived home page is tried, then common paths (`/terms`, `/policies/terms-of-service`, and so on).
- Up to one "use" page and one "sale" page per shop. A page with under 1,500 characters of text (walled, captcha, or rendered by script) is replaced by its latest Wayback copy if that is longer, otherwise recorded as thin and not coded.
- Backfill: the Wayback capture of the same terms URL and of robots.txt closest to 22 Nov 2025 and not after it. Only copies dated 22 May 2025 to 30 Nov 2025 count as "a year ago".
- Weekly runs come from GitHub-hosted runners in the US.

## Coding (`study/classify.py`), no language models

Text is split into sentences (hard-wrapped lines rejoined). A sentence is an **agent sentence** if it names AI, autonomous, software, shopping, browser, buy-for-me or third-party agents, agentic commerce, LLM-driven bots, AI assistants or browsers, or uses "Agent" after the document defines it. Sentences about the shop's own staff or legal agents ("officers, employees and agents", "designated agent") and the shop's own chatbot are excluded.

Features, from agent sentences and their neighbours: ban wording, allowlist ("approved agents", "authorized agents"), identification (user agent string, disclose, not conceal, respond truthfully), human review, liability (shopper responsible or bound, shop not responsible for agent conduct), signed identity (Web Bot Auth, HTTP Message Signatures, card network agent programs, agent credentials).

Stance, in order: allowlist, then conditional (identification required), then ban, then permitted (agents allowed, shopper liable), then mention (outside agents named, no clear rule), then own_feature (only the shop's own AI assistant), else none. AI tools named in an access ban ("robots, spiders ... artificial intelligence tools") count as agent sentences once AI-training wording is removed.

Other features from all sentences: older automation clause (robot, spider, scraper, crawler, data mining, automated means), automated ordering named, ban on using content to train AI.

robots.txt: for each token, whether it is named in a group and whether Protego allows `/` and `/checkout`. Platform defaults are flagged by their text: Shopify's late-2025 "Checkouts are for humans" box, its 2026 "Agents must:" block, links to agents.md, mentions of UCP, and the Shop skill (`SKILL.md`) pitch.

## Hand check

Every shop coded with stance other than none is checked by reading its agent section in full (saved live text, or the live page in a normal browser where the saved copy came from the archive). Every shop coded none is swept again with broader keywords (agentic, AI agent, autonomous, buy-for-me, LLM, digital or automated agent, AI-powered tools, AI assistant or browser, shopping agent) and each hit is read. Hand-check labels add `ai_scrape_ban` (AI tools named only in an anti-scraping clause) and `not_shop` (dropped from counts). `data/hand-check.csv` records `stance_checked`, which overrides the code. No shop is named in any report before its hand check.

## Ethics

Read-only, public pages, honest identification, robots.txt obeyed. Full terms text is kept in short-lived run artifacts, not republished; reports quote at most a sentence or two per shop with a link.
