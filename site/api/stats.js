// lithnode.com/stats?key=... : Download clicks, "Send me the link" taps, installs and updates for the last 30 days.
// Private: needs the STATS_KEY env var's value as ?key=. Only counts, nothing about anyone (see _count.js).
const crypto = require("crypto");
const { events, KINDS } = require("./_count");

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const OSNAME = { win: "Windows", mac: "Mac", linux: "Linux", phone: "Phone" };

function same(a, b) {
  const x = Buffer.from(String(a || "")), y = Buffer.from(String(b || ""));
  return x.length === y.length && x.length > 0 && crypto.timingSafeEqual(x, y);
}

function tally(list, key) {
  const m = new Map();
  for (const e of list) m.set(key(e), (m.get(key(e)) || 0) + 1);
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

const table = (title, rows, head) => rows.length
  ? `<h2>${esc(title)}</h2><table><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr>${rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</table>`
  : `<h2>${esc(title)}</h2><p class="dim">None yet.</p>`;

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Robots-Tag", "noindex");
  if (!same(req.query.key, process.env.STATS_KEY)) return res.status(404).send("Not found");

  const since = new Date(Date.now() - 29 * 864e5).toISOString().slice(0, 10);
  let all;
  try { all = await events(since); } catch (e) { return res.status(500).send("Couldn't read the counts: " + esc(e.message)); }
  const of = (k) => all.filter((e) => e.kind === k);

  const days = [...new Set(all.map((e) => e.day))].sort().reverse();
  const daily = days.map((d) => [d, ...Object.keys(KINDS).map((k) => all.filter((e) => e.kind === k && e.day === d).length)]);
  const totals = Object.entries(KINDS).map(([k, name]) => `<div class="tile"><b>${of(k).length}</b><span>${esc(name)}</span></div>`).join("");

  const page = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Lithnode stats</title><style>
:root{--bg:#0b0b0d;--fg:#ececf1;--dim:#8b8b96;--line:#24242b;--card:#141418}
@media (prefers-color-scheme: light){:root{--bg:#fafafa;--fg:#111;--dim:#666;--line:#e3e3e8;--card:#fff}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;padding:24px 16px}
main{max-width:860px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}
.dim{color:var(--dim)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.tile b{display:block;font-size:26px}
.tile span{color:var(--dim);font-size:13px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--dim);font-weight:500;font-size:13px}
</style></head><body><main><h1>Lithnode stats</h1><p class="dim">Last 30 days, since ${esc(since)} (UTC days). Download clicks are on lithnode.com;
installs and updates come from the app (0.1.24 and later), once per version.</p><div class="tiles">${totals}</div>
${table("By day", daily, ["Day", ...Object.values(KINDS)])}
${table("Download clicks by where visitors came from", tally(of("d"), (e) => e.parts[1] || "unknown").map(([k, n]) => [k, n]), ["From", "Clicks"])}
${table("Download clicks by computer", tally(of("d"), (e) => OSNAME[e.parts[0]] || e.parts[0]).map(([k, n]) => [k, n]), ["Computer", "Clicks"])}
${table("Installs and updates by computer and version", tally([...of("i"), ...of("u")], (e) => `${e.kind === "i" ? "Install" : "Update"}|${OSNAME[e.parts[0]] || e.parts[0]}|${e.parts[1] || ""}`)
    .map(([k, n]) => [...k.split("|"), n]), ["What", "Computer", "Version", "Count"])}
</main></body></html>`;
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.status(200).send(page);
};
