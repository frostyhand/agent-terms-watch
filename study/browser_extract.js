// Run on a shop's terms page in a normal browser after it has rendered.
(() => {
  const text = document.body ? document.body.innerText : '';
  const rx = /[^.\n]*(?:\bAI\b[- ]?(?:agents?|powered|enabled|assistants?|browsers?|systems?|tools?)|artificial intelligence|agentic|autonomous|semi-autonomous|buy[- ]for[- ]me|LLM|large language|["“](?:[A-Z][a-z]+ )?Agents?["”]|Digital Agent|Automated Agent|\bAgents?\b(?= (?:must|may|that|you|are|accessing|shall))|identify (?:itself|themselves)|user[- ]agent string)[^.\n]*/g;
  const hits = [...new Set((text.match(rx) || []).map(s => s.trim().replace(/\s+/g, ' ').slice(0, 260)))]
    .filter(s => !/copyright agent|officers|employees|designated agent/i.test(s)).slice(0, 10);
  const upd = (text.match(/(?:last (?:updated|modified|revised)|effective(?: date)?|updated)[:\s][^\n]{0,40}/i) || [''])[0];
  return { url: location.href, title: document.title.slice(0, 80), chars: text.length, updated: upd.trim(), hits };
})()
