#!/usr/bin/env python3
"""Code each shop's saved terms and robots.txt for AI shopping agent rules. No LLMs.

Terms features (any saved terms page of the shop, use or sale):
  agent_rule        explicit rule about AI or software agents acting for a shopper
    agent_ban         ... that prohibits them (in general or unless approved)
    agent_allowlist   ... that names approved or authorised agents
    agent_identify    ... that requires agents to identify themselves
    agent_human       ... that requires human review or oversight
    agent_liability   ... that puts the shopper on the hook for what the agent does
  automation_ban    older robot / spider / scraper / "automated means" clause
  auto_purchase_ban automated ordering or checkout is named as prohibited or cancellable
  ai_training_ban   content may not be used to train AI or machine learning models

robots.txt features, per user-triggered agent token: named in a group, allowed to fetch / and /checkout.

Usage: python study/classify.py results/local-2026-11-22
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from protego import Protego

AGENT_RE = re.compile(
    r"\b(?:ai|a\.i\.|artificial[- ]intelligence|autonomous|semi-autonomous|software|shopping|buy[- ]for[- ]me|browser|"
    r"automated|digital|personal|third[- ]party|intelligent|virtual|purchasing) agents?\b|"
    r"\bagentic\b|\bLLM[- ](?:driven|powered|based|bots?|agents?)\b|\bLLMs? (?:bots?|agents?)\b|"
    r"\bAI[- ](?:powered|driven|enabled|based) (?:tools?|bots?|assistants?|browsers?|agents?|software|applications?)\b|"
    r"\bAI (?:assistants?|bots?|browsers?|shopping)\b|"
    r"[“\"]Agents?[”\"] (?:means|refers)|Agent Terms|Agentic Commerce Tools?|Approved Agents?",
    re.I,
)
# sentences about the shop's own AI features, or agents in the legal sense, are not agent rules
AGENT_NOT_RE = re.compile(
    r"\bwe (?:may )?use (?:artificial intelligence|ai)\b|our (?:ai|virtual|digital) (?:assistant|agent)s?\b(?![^.]*(?:third|other))|"
    r"copyright agents?|dmca|agent for (?:service|notice)|customer service agents?|sales agents?|registered agents?|designated agents?|insurance agents?|travel agents?|"
    r"collection agents?|shipping agents?|escrow agents?|agents?,? (?:officers|employees|directors|affiliates|licensors|successors|representatives)|"
    r"(?:officers|employees|directors|affiliates|licensors|contractors|subsidiaries)[^.]{0,60}\bagents\b|chatbot",
    re.I,
)
BAN_RE = re.compile(r"\bprohibit|not (?:be )?(?:permitted|allowed|authori[sz]ed)|may not|must not|shall not|will not|agree not to|unauthori[sz]ed|no (?:agent|ai)|forbid|expressly prohibited|except with|without (?:our|the) (?:prior |express )", re.I)
ALLOW_RE = re.compile(r"approved agents?|authori[sz]ed agents?|expressly approved|whitelist|allow[- ]?list|permitted agents?|the current approved", re.I)
IDENT_RE = re.compile(r"identif(?:y|ies) (?:itself|themselves|that the request|as an? (?:agent|bot|automated))|(?:clearly|properly|accurately) identified|status as an agent|"
                      r"identif(?:y|ies) (?:the|its) (?:agent|operator|principal)|user[- ]agent string|disclose (?:that|its|the name)|not conceal|obfuscat|self-identif|truthfully", re.I)
HUMAN_RE = re.compile(r"human (?:review|oversight|confirmation|approval|in the loop|intervention)|without (?:continuous )?human", re.I)
LIAB_RE = re.compile(r"(?:you are|you will be|you remain|you shall be|you're) (?:solely |fully |entirely )?(?:responsible|liable|bound)|you (?:assume|accept) (?:all |full )?(?:responsibility|risk|liability)|on your behalf[^.]{0,80}(?:binding|bound|authori[sz]ed)|not (?:be )?responsible for (?:the )?(?:conduct|actions|acts)", re.I)

AUTO_RE = re.compile(
    r"\brobots?\b|\bspiders?\b|\bscrap(?:e|er|ers|ing)\b|\bcrawl(?:er|ers|ing)\b|data[- ]mining|\bbots?\b|"
    r"automated (?:means|systems?|tools?|devices?|software|scripts?|access|process(?:es)?|programs?|methods?|technolog(?:y|ies)|queries|purchas\w*|order\w*)|"
    r"automatic (?:devices?|means|programs?)|(?:any|other) automated|scripts? or (?:other )?(?:programs|software)|through (?:any )?automated",
    re.I,
)
AUTO_NOT_RE = re.compile(r"\bwe (?:may )?(?:automatically |also )?(?:collect|use|receive|log)|cookies|automatically (?:collect|assigned|renew|charge|bill)|automatic telephone|autodial|auto-?renew|recurring|text messages?|\bsms\b|pixel|web beacons?|chatbots?", re.I)
PURCH_RE = re.compile(r"\b(?:orders?|ordering|purchas\w+|checkout|check out|buy(?:ing)?|cart|transactions?|reserv\w+|tickets?)\b", re.I)
SIGNED_RE = re.compile(r"web bot auth|http message signatures?|cryptographic(?:ally)? (?:sign|verif)|signed requests?|trusted agent protocol|intelligent commerce|agent pay|know your agent|agent (?:identity|credentials?|tokens?)", re.I)
TRAIN_RE = re.compile(r"(?:train|training|develop|improve|fine-tun)\w*[^.;]{0,120}(?:artificial intelligence|\bai\b|machine learning|models?|llms?|large language)|(?:artificial intelligence|\bai\b|machine learning)[^.;]{0,60}(?:train|training)", re.I)

# AI-era wording; anything else that names agents (e.g. "intelligent agents", "avatars", "automated agent"
# in a list of robots) is older boilerplate, kept as agent_legacy and left out of the stance
MODERN_RE = re.compile(
    r"\b(?:ai|a\.i\.|artificial[- ]intelligence|autonomous|semi-autonomous|shopping|buy[- ]for[- ]me|browser|personal|digital) agents?\b|"
    r"\bagentic\b|\bLLM|large language|\bAI[- ]?(?:powered|driven|enabled|based|assistants?|bots?|browsers?|shopping)\b|"
    r"[“\"]Agents?[”\"]|Agent Terms|Agentic Commerce|Approved Agents?|on (?:your|a user'?s?|the user'?s?) behalf",
    re.I,
)

AI_ACCESS_RE = re.compile(r"artificial intelligence (?:tools?|systems?|software|applications?|bots?)|\bAI(?:-based|-powered)? (?:tools?|systems?|software|bots?|crawlers?)\b", re.I)

# the shop describing its own AI assistant, not a rule about outside agents
OWN_RE = re.compile(r"\bour (?:own )?(?:ai|virtual|digital|agentic)\b|\bthe AI (?:Shopping )?Assistant\b|features? we (?:may )?(?:offer|provide)|optional (?:buying )?feature|(?:’s|'s) AI (?:shopping )?assistant|(?:feature|tool|service) (?:offered|provided) by (?:us|[A-Z]\w+)\.?$|^[A-Z][\w&’' ]+ (?:AI|Agentic) [A-Z]\w+ is an optional", re.I)

USER_AGENTS = ["ChatGPT-User", "Claude-User", "Perplexity-User", "Google-Agent", "Amazon-Agent"]
CRAWLERS = ["GPTBot", "OAI-SearchBot", "ClaudeBot", "Claude-SearchBot", "PerplexityBot", "Google-Extended", "Applebot-Extended", "Amazonbot", "Meta-ExternalAgent", "CCBot", "Bytespider"]
FOREIGN_RE = re.compile(r"/(?:en-|fr-|de-|es-)?(?:eu|uk|gb|pl|de|fr|ca|au|in|intl|international|row|en_gb|en-gb|en-eu|en-pl)(?:/|$|[-_])", re.I)


def sentences(text: str) -> list[str]:
    # rejoin hard-wrapped lines: a line that does not end a sentence, followed by one starting in lower case
    lines: list[str] = []
    for ln in text.split("\n"):
        if lines and not re.search(r"[.;:!?”\")]$", lines[-1]) and re.match(r"[a-z(\"“0-9]", ln):
            lines[-1] += " " + ln
        else:
            lines.append(ln)
    out = []
    for line in lines:
        out.extend(s.strip() for s in re.split(r"(?<=[.;!?])\s+(?=[A-Z(“\"])", line) if len(s.strip()) > 15)
    return out


def code_terms(text: str) -> dict:
    f = {k: False for k in ("agent_rule", "agent_ban", "agent_allowlist", "agent_identify", "agent_human", "agent_liability",
                            "agent_signed", "agent_thirdparty", "agent_legacy", "automation_ban", "auto_purchase_ban", "ai_training_ban")}
    ev: dict[str, list[str]] = {}

    def hit(k, s):
        f[k] = True
        if len(ev.setdefault(k, [])) < 3:
            ev[k].append(s[:600])

    sents = sentences(text)
    defined = re.search(r"[“\"](?:[A-Z][a-z]+ )?Agents?[”\"]|Agent Terms", text)
    for i, s in enumerate(sents):
        agent = (AGENT_RE.search(s) or (defined and re.search(r"\bAgents?\b", s))) and not AGENT_NOT_RE.search(s.replace("Agent Terms", ""))
        # AI tools named in an access ban ("use any robot, spider, ... artificial intelligence tools ... to access")
        if not agent and AUTO_RE.search(s) and AI_ACCESS_RE.search(TRAIN_RE.sub(" ", s)):
            agent = True
        if agent and not (MODERN_RE.search(s) or AI_ACCESS_RE.search(TRAIN_RE.sub(" ", s)) or defined):
            hit("agent_legacy", s)
        elif agent:
            hit("agent_rule", s)
            if not OWN_RE.search(s):
                hit("agent_thirdparty", s)
            window = " ".join(sents[max(0, i - 1): i + 2])
            if BAN_RE.search(s):
                hit("agent_ban", s)
            if ALLOW_RE.search(s):
                hit("agent_allowlist", s)
            if IDENT_RE.search(s):
                hit("agent_identify", s)
            if HUMAN_RE.search(s):
                hit("agent_human", s)
            if LIAB_RE.search(window):
                hit("agent_liability", s)
        if SIGNED_RE.search(s):
            hit("agent_signed", s)
        if AUTO_RE.search(s) and not AUTO_NOT_RE.search(s):
            hit("automation_ban", s)
            if PURCH_RE.search(s):
                hit("auto_purchase_ban", s)
        if TRAIN_RE.search(s) and re.search(r"may not|not to|prohibit|without|shall not|must not|agree", s, re.I):
            hit("ai_training_ban", s)
    if f["agent_allowlist"]:
        stance = "allowlist"
    elif f["agent_identify"]:
        stance = "conditional"
    elif f["agent_ban"]:
        stance = "ban"
    elif f["agent_liability"] and f["agent_thirdparty"]:
        stance = "permitted"
    elif f["agent_thirdparty"]:
        stance = "mention"
    elif f["agent_rule"]:
        stance = "own_feature"
    else:
        stance = "none"
    return {"features": f, "stance": stance, "evidence": ev}


def code_robots(txt: str) -> dict:
    if not txt:
        return {"present": False}
    rp = Protego.parse(txt)
    groups = {m.group(1).strip().lower() for m in re.finditer(r"(?im)^\s*user-agent\s*:\s*([^\s#]+)", txt)}
    out = {"present": True, "agent_comment": bool(re.search(r"(?im)^\s*#.*\b(?:agents?|agentic|LLM|AI\b|buy-for-me)", txt)),
           # Shopify platform defaults: late-2025 "Checkouts are for humans" box, 2026 "Agents must" block
           "humans_only": bool(re.search(r"checkouts are for humans", txt, re.I)),
           "agents_must": "Agents must:" in txt,
           "agents_md": bool(re.search(r"(?im)^#.*agents\.md", txt)),
           "skill_pitch": "SKILL.md" in txt,
           "ucp": bool(re.search(r"(?im)^#.*\bUCP\b", txt)),
           "shopify": bool(re.search(r"shopify", txt, re.I))}
    for t in USER_AGENTS + CRAWLERS:
        out[t] = {"named": t.lower() in groups, "home": rp.can_fetch("/", t), "checkout": rp.can_fetch("/checkout", t)}
    return out


def read(p: Path) -> str:
    return p.read_text(errors="replace") if p.exists() else ""


def main(run: str):
    run_p = Path(run)
    rows = [json.loads(l) for l in open(run_p / "sites.jsonl")]
    seen = set()
    out = []
    for r in rows:
        if r["site"] in seen:
            continue
        seen.add(r["site"])
        name = re.sub(r"[^a-z0-9.]+", "_", r["site"].lower()).strip("_")[:120]
        now_txt = "\n".join(read(run_p / "terms" / f"{name}__{k}.txt") for k in ("use", "sale"))
        then_txt = "\n".join(read(run_p / "terms_then" / f"{name}__{k}.txt") for k in ("use", "sale"))
        pages = [p for p in r.get("pages", []) if p.get("file")]
        foreign = any(FOREIGN_RE.search((p.get("final") or p["url"]).split("?")[0]) for p in pages)
        rec = {
            "site": r["site"], "panel": r["panel"], "segment": r.get("segment", ""),
            "terms_found": bool(pages), "terms_source": sorted({p.get("source") for p in pages if p.get("source")}),
            "terms_urls": [p.get("final") or p["url"] for p in pages], "foreign_page": foreign,
            "now": code_terms(now_txt) if now_txt.strip() else None,
            "then": code_terms(then_txt) if then_txt.strip() else None,
            "then_ts": {k: v for k, v in (r.get("backfill") or {}).items() if k.endswith("_ts")},
            "robots_now": code_robots(read(run_p / "robots" / f"{name}.txt")),
            "robots_then": code_robots(read(run_p / "robots_then" / f"{name}.txt")),
            "robots_source": r["robots"].get("source"),
        }
        out.append(rec)
    with open(run_p / "classified.jsonl", "w") as f:
        for rec in out:
            f.write(json.dumps(rec) + "\n")
    # flat table for hand checks
    keys = ["agent_rule", "agent_ban", "agent_allowlist", "agent_identify", "agent_human", "agent_liability", "agent_signed", "agent_legacy", "automation_ban", "auto_purchase_ban", "ai_training_ban"]
    with open(run_p / "classified.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site", "panel", "segment", "terms_found", "source", "foreign_page", "stance", "then_stance"] + keys + [f"then_{k}" for k in ("agent_rule", "automation_ban")] +
                   ["chatgpt_user_home", "claude_user_home", "perplexity_user_home", "robots_agent_comment", "terms_urls"])
        for r in out:
            n = (r["now"] or {}).get("features", {})
            t = (r["then"] or {}).get("features", {})
            rb = r["robots_now"]
            w.writerow([r["site"], r["panel"], r["segment"], r["terms_found"], "+".join(r["terms_source"]), r["foreign_page"],
                        (r["now"] or {}).get("stance", ""), (r["then"] or {}).get("stance", "")] +
                       [n.get(k, "") for k in keys] + [t.get("agent_rule", ""), t.get("automation_ban", "")] +
                       [rb.get(a, {}).get("home", "") if rb.get("present") else "" for a in ("ChatGPT-User", "Claude-User", "Perplexity-User")] +
                       [rb.get("agent_comment", "")] + [" ".join(r["terms_urls"])])
    print(f"classified {len(out)} sites -> {run_p / 'classified.jsonl'}")


if __name__ == "__main__":
    main(sys.argv[1])
