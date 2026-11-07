// Counting for the stats page: each event is one empty file in the site's private Blob store, named
//   <kind>/<YYYY-MM-DD>/<part>_<part>-<random>.txt   (the .txt keeps the random part off dotted parts like 0.1.24)
// kinds: d = a Download click, s = a phone's "Send me the link", i = the app's first launch, u = first launch after an update.
// No IP, no cookie, nothing about the person: only the day and the parts (OS, version, the site that sent them).
// Files starting with _ aren't routes, so this is shared code for hit.js, ping.js and stats.js.
const { put, list } = require("@vercel/blob");

const KINDS = { d: "Download clicks", s: "Send me the link", i: "New installs", u: "Updates" };
let recent = [];   // event times on this warm instance: a flood stops at 300 an hour

const part = (v) => String(v || "").toLowerCase().replace(/[^a-z0-9.]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "unknown";

async function record(kind, parts) {
  if (!KINDS[kind] || !process.env.BLOB_READ_WRITE_TOKEN) return false;
  const now = Date.now();
  recent = recent.filter((t) => now - t < 3600e3);
  if (recent.length >= 300) return false;
  recent.push(now);
  const day = new Date(now).toISOString().slice(0, 10);
  try {
    await put(`${kind}/${day}/${parts.map(part).join("_")}.txt`, "1", { access: "private", addRandomSuffix: true, contentType: "text/plain" });
    return true;
  } catch (e) {
    console.log("count failed:", e.message);
    return false;
  }
}

// every event since `since` (YYYY-MM-DD) as {kind, day, parts}
async function events(since) {
  const out = [];
  for (const kind of Object.keys(KINDS)) {
    let cursor;
    do {
      const page = await list({ prefix: `${kind}/`, cursor, limit: 1000 });
      for (const b of page.blobs) {
        const [, day, name] = b.pathname.split("/");
        if (!day || day < since) continue;
        out.push({ kind, day, parts: name.replace(/-[^-]*\.txt$/, "").split("_") });
      }
      cursor = page.hasMore ? page.cursor : undefined;
    } while (cursor);
  }
  return out;
}

module.exports = { record, events, KINDS };
