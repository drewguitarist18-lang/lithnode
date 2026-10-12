// Emails Drew when someone views lithnode.com or clicks a download button. Stores nothing: no IP, no cookie, no log.
// The page sends {kind: "view" | "download", os} with sendBeacon. Bots, other sites' requests and floods are dropped.
// Env (Vercel project settings): GMAIL_USER, GMAIL_APP_PASSWORD (a Google app password), NOTIFY_TO.
const nodemailer = require("nodemailer");

const BOT = /bot|crawl|spider|slurp|preview|fetch|curl|wget|python|headless|lighthouse|vercel|monitor|facebookexternalhit|embedly|discord|telegram|whatsapp/i;
const OS = { win: "Windows", mac: "Mac", linux: "Linux" };
const sent = [];   // send times on this warm instance, to cap a flood at 30 an hour

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).end();
  const from = req.headers.origin || req.headers.referer || "";
  if (!/^https:\/\/(www\.)?lithnode\.com/.test(from) && !process.env.HIT_ANY_ORIGIN) return res.status(204).end();
  if (BOT.test(req.headers["user-agent"] || "")) return res.status(204).end();

  let body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = {}; } }
  body = body || {};
  const kind = ["download", "test"].includes(body.kind) ? body.kind : "view";
  const os = OS[body.os] || null;

  const now = Date.now();
  while (sent.length && now - sent[0] > 3600e3) sent.shift();
  if (sent.length >= 30) return res.status(204).end();

  const h = (k) => { try { return decodeURIComponent(req.headers[k] || ""); } catch { return ""; } };
  const where = [h("x-vercel-ip-city"), h("x-vercel-ip-country-region"), h("x-vercel-ip-country")].filter(Boolean).join(", ") || "somewhere";
  const ua = req.headers["user-agent"] || "";
  const device = /iphone|ipad|android|mobile/i.test(ua) ? "phone" : "computer";
  const ref = typeof body.ref === "string" && body.ref && !/lithnode\.com/.test(body.ref) ? body.ref.slice(0, 200) : "";
  const subject = kind === "test" ? "Lithnode: test email, site alerts are working" : kind === "download" ? `Lithnode: ${os || "a"} download from ${where}` : `Lithnode: someone's on the site from ${where}`;
  const text = [
    kind === "test" ? "Test email from the site. If you got this, alerts work." : kind === "download" ? `Someone clicked Download${os ? " for " + os : ""}.` : "Someone opened lithnode.com.",
    `From: ${where}, on a ${device}.`,
    ref ? `Came from: ${ref}` : "",
    new Date(now).toLocaleString("en-US", { timeZone: "America/New_York" }) + " ET",
  ].filter(Boolean).join("\n");

  const { GMAIL_USER, GMAIL_APP_PASSWORD, NOTIFY_TO } = process.env;
  if (!GMAIL_USER || !GMAIL_APP_PASSWORD || !NOTIFY_TO) { console.log("not configured:", subject); return res.status(204).end(); }
  sent.push(now);
  try {
    const mail = nodemailer.createTransport({ service: "gmail", auth: { user: GMAIL_USER, pass: GMAIL_APP_PASSWORD } });
    await mail.sendMail({ from: `Lithnode alerts <${GMAIL_USER}>`, to: NOTIFY_TO, subject, text });
  } catch (e) { console.log("send failed:", e.message); }
  res.status(204).end();
};
