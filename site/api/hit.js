// Emails Drew when someone views lithnode.com, clicks a download button, or taps "Send me the link" on a phone,
// and counts the clicks and taps for the stats page (_count.js: the day, the OS and the site that sent them; no IP, no cookie).
// The page sends {kind: "view" | "download" | "send", os, from} with sendBeacon. Bots, other sites' requests and floods are dropped.
// Env (Vercel project settings): GMAIL_USER, GMAIL_APP_PASSWORD (a Google app password), NOTIFY_TO; BLOB_READ_WRITE_TOKEN for counting.
const nodemailer = require("nodemailer");
const { record } = require("./_count");

const BOT = /bot|crawl|spider|slurp|preview|fetch|curl|wget|python|headless|lighthouse|vercel|monitor|facebookexternalhit|embedly|discord|telegram|whatsapp/i;
const OS = { win: "Windows", mac: "Mac", linux: "Linux" };
const sent = [];   // send times on this warm instance, to cap a flood at 30 an hour

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).end();
  const from = req.headers.origin || req.headers.referer || "";
  if (!/^https:\/\/(www\.)?lithnode\.com(\/|$)/.test(from) && !process.env.HIT_ANY_ORIGIN) return res.status(204).end();
  if (BOT.test(req.headers["user-agent"] || "")) return res.status(204).end();

  let body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = {}; } }
  body = body || {};
  const kind = ["download", "send", "test"].includes(body.kind) ? body.kind : "view";
  const os = OS[body.os] || null;
  const cameFrom = typeof body.from === "string" ? body.from : "";
  if (kind === "download") await record("d", [body.os in OS ? body.os : "unknown", cameFrom]);
  if (kind === "send") await record("s", ["phone", cameFrom]);

  const now = Date.now();
  while (sent.length && now - sent[0] > 3600e3) sent.shift();
  if (sent.length >= 30) return res.status(204).end();

  const h = (k) => { try { return decodeURIComponent(req.headers[k] || ""); } catch { return ""; } };
  const where = [h("x-vercel-ip-city"), h("x-vercel-ip-country-region"), h("x-vercel-ip-country")].filter(Boolean).join(", ") || "somewhere";
  const ua = req.headers["user-agent"] || "";
  const device = /iphone|ipad|android|mobile/i.test(ua) ? "phone" : "computer";
  const ref = typeof body.ref === "string" && body.ref && !/lithnode\.com/.test(body.ref) ? body.ref.slice(0, 200) : "";
  const [subject, first] = {   // each kind's subject line and first line
    view: [`Lithnode: someone's on the site from ${where}`, "Someone opened lithnode.com."],
    download: [`Lithnode: ${os || "a"} download from ${where}`, `Someone clicked Download${os ? " for " + os : ""}.`],
    send: [`Lithnode: someone on a phone tapped Send me the link, from ${where}`, "Someone on a phone tapped Send me the link, to get Lithnode on a computer later."],
    test: ["Lithnode: test email, site alerts are working", "Test email from the site. If you got this, alerts work."],
  }[kind];
  const text = [
    first,
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
