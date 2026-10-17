// Records the real app and site as footage for the film. Needs the demo Lithnode on 8795 (mock engines, so runs
// cost nothing) and the site served on 8797 (`python -m http.server 8797 -d site`). Writes footage/<clip>.mp4 (30 fps)
// and footage/<clip>.json (every mouse move, click and key with its time in the clip, so the film can draw the cursor).
// Frames come from Chrome's screencast with their own timestamps, on the same clock as the log, so they line up exactly.
// Usage: node capture.js [clip ...]   clips: describe, run, site   (run also records the Office alongside it)
const puppeteer = require("puppeteer-core");
const fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const FF = process.env.FFMPEG || "ffmpeg";
const APP = "http://127.0.0.1:8795", SITE = "http://127.0.0.1:8797";
const FOLDER = "C:/Users/drewm/AppData/Local/Temp/lithnode-film/project";
const out = (f) => path.join(__dirname, "footage", f);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function page(b) {
  const p = await b.newPage();
  await p.setViewport({ width: 1920, height: 1080 });
  await p.evaluateOnNewDocument(() => { try { localStorage.setItem("hq-usage-ok-2", "1"); localStorage.setItem("hq-theme", "dark"); } catch (e) {} });
  p.on("pageerror", (e) => console.log("pageerror", e.message));
  return p;
}
// a recording with a log of the pointer: every move and click, timed from the recording's start
async function record(p, name) {
  const dir = out(name + "-frames"), frames = [];
  fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir);
  const cdp = await p.createCDPSession();
  cdp.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
    const file = path.join(dir, String(frames.length).padStart(5, "0") + ".jpg");
    fs.writeFileSync(file, Buffer.from(data, "base64")); frames.push([metadata.timestamp, file]);
    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  const t0 = Date.now(), log = [];
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 94, maxWidth: 1920, maxHeight: 1080 });
  let at = [960, 540];
  const mark = (kind, x, y) => log.push({ t: (Date.now() - t0) / 1000, kind, x: Math.round(x), y: Math.round(y) });
  return {
    mark: (kind) => mark(kind, ...at),
    async move(x, y, ms = 700) {   // eased glide, like a hand
      const [sx, sy] = at, steps = Math.max(8, Math.round(ms / 16));
      for (let i = 1; i <= steps; i++) {
        const k = i / steps, e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
        at = [sx + (x - sx) * e, sy + (y - sy) * e];
        await p.mouse.move(...at); mark("move", ...at); await sleep(ms / steps);
      }
    },
    async click() { mark("down", ...at); await p.mouse.down(); await sleep(70); await p.mouse.up(); mark("up", ...at); },
    async type(text, delay = 55) { for (const ch of text) { await p.keyboard.type(ch); mark("key", ...at); await sleep(delay + (ch === " " ? 40 : Math.random() * 40)); } },
    async stop() {
      const end = Date.now() / 1000;
      await cdp.send("Page.stopScreencast"); await sleep(300);
      // constant 30 fps: each frame holds until the next one arrived
      const list = ["ffconcat version 1.0"];
      frames.forEach(([ts, file], i) => {
        const from = i === 0 ? t0 / 1000 : ts, until = i + 1 < frames.length ? frames[i + 1][0] : end;
        list.push(`file '${file.split(path.sep).join("/")}'`, `duration ${Math.max(0.001, until - from).toFixed(4)}`);
      });
      list.push(`file '${frames[frames.length - 1][1].split(path.sep).join("/")}'`);
      fs.writeFileSync(path.join(dir, "list.txt"), list.join("\n"));
      execFileSync(FF, ["-v", "error", "-y", "-safe", "0", "-f", "concat", "-i", path.join(dir, "list.txt"), "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264", "-crf", "16", "-g", "15", "-movflags", "+faststart", out(name + ".mp4")]);
      fs.rmSync(dir, { recursive: true, force: true });
      fs.writeFileSync(out(name + ".json"), JSON.stringify({ log }, null, 0)); console.log(name, "recorded", ((Date.now() - t0) / 1000).toFixed(1) + "s,", frames.length, "frames");
    },
  };
}
async function center(p, sel) {
  const box = await (await p.waitForSelector(sel, { visible: true, timeout: 20000 })).boundingBox();
  return [box.x + box.width / 2, box.y + box.height / 2];
}
async function flowId(name) {
  const { flows } = await (await fetch(APP + "/api/flows")).json();
  return flows.find((f) => f.name === name).id;
}
// the whole app (its header, Flows and Office tabs) with this flow open; returns the Flows frame inside it
async function openApp(p, id) {
  await p.goto(APP + "/#flows", { waitUntil: "networkidle2" });
  let f;
  for (let i = 0; i < 40 && !f; i++) { f = p.frames().find((x) => x.url().includes("/flows")); if (!f) await sleep(250); }
  await f.waitForFunction(() => typeof openFlow === "function" && document.readyState === "complete");
  await f.evaluate(async (id) => { await openFlow(id); }, id);
  await f.evaluate(() => document.querySelectorAll("button").forEach((b) => { if (/^Got it$/.test(b.textContent.trim())) b.click(); }));
  await sleep(1200);
  return f;
}

const launch = () => puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new",
  args: ["--enable-gpu", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"] });

const clips = {
  // describe a team in one line, and it's drawn
  async describe(b) {
    const p = await page(b);
    const f = await openApp(p, await flowId("Research squad"));
    const r = await record(p, "describe");
    await sleep(600);
    await r.move(...(await center(f, "#askIn")), 900); await r.click(); await sleep(250);
    await r.type("Find products worth selling, check margins and reviews, list the winners");
    await sleep(350);
    await r.move(...(await center(f, "#askBtn")), 500); await sleep(150); await r.click();
    await f.waitForFunction(() => document.getElementById("askBtn").textContent === "Build flow", { timeout: 60000 });
    r.mark("drawn");
    await sleep(3000);
    await r.stop(); await p.close();
  },
  // run the big flow from the Run dialog, watch it, approve it, see it finish; the Office records alongside
  async run(b) {
    const id = await flowId("Product hunt");
    const b2 = await launch(), p = await page(b), o = await page(b2);   // the Office in its own browser, so neither tab is in the background
    console.log("run: opening the app"); const f = await openApp(p, id);
    console.log("run: opening the office"); await o.goto(APP + "/office", { waitUntil: "load" });
    await sleep(800);
    const r = await record(p, "run"), ro = await record(o, "office");
    await sleep(1200);
    await r.move(...(await center(f, "#runBtn")), 900); await r.click(); await sleep(500);
    await f.$eval("#taskIn", (el) => { el.value = ""; el.dispatchEvent(new Event("input", { bubbles: true })); });
    await r.move(...(await center(f, "#taskIn")), 500); await r.click();
    await r.type("Find home gadgets worth selling this month", 38);
    await f.$eval("#folderIn", (el, v) => { el.value = v; el.dispatchEvent(new Event("input", { bubbles: true })); }, FOLDER);
    await sleep(300);
    if (await f.$eval("#riskBox", (el) => !el.hidden)) { await r.move(...(await center(f, "#riskOk")), 500); await r.click(); await sleep(250); }
    await r.move(...(await center(f, "#goBtn")), 500); await r.click();
    r.mark("start");
    // wait for the approval card, then approve it
    const approve = '[data-decide][data-ok="1"]';
    console.log("run: started, waiting for the approval card");
    await f.waitForSelector(approve, { visible: true, timeout: 90000 });
    r.mark("waiting");
    await sleep(1800);
    await r.move(...(await center(f, approve)), 1000); await sleep(200); await r.click();
    r.mark("approved");
    for (let i = 0; i < 60; i++) {   // until the run ends
      const st = await f.evaluate(() => run && run.status);
      if (st && !["running", "waiting"].includes(st)) break;
      await sleep(500);
    }
    r.mark("done");
    await sleep(3500);
    await r.stop(); await ro.stop(); await p.close(); await b2.close();
  },
  // the site: the hero's live black hole, tipping as the pointer drifts, then a glide to the download button
  async site(b) {
    const p = await page(b);
    await p.goto(SITE + "/", { waitUntil: "networkidle2" });
    await p.mouse.move(960, 900);
    await sleep(3000);
    const r = await record(p, "site");
    await r.move(960, 900, 10);
    await sleep(800);
    await r.move(700, 260, 3600);
    await r.move(1250, 520, 3200);
    await r.move(...(await center(p, "#dlMain")), 1400);
    await sleep(2200);
    await r.stop(); await p.close();
  },
};

(async () => {
  fs.mkdirSync(path.join(__dirname, "footage"), { recursive: true });
  const b = await launch();
  for (const name of process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(clips)) await clips[name](b);
  await b.close();
})();
