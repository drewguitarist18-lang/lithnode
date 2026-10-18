// Renders film.html to an MP4: every frame through renderFrame(t), the score through renderAudio(), muxed by ffmpeg.
// Usage: node render.js [out.mp4]          (default ../lithnode-night.mp4)
//        node render.js --audio            (re-score the existing mp4 without re-rendering the picture)
//        node render.js --stills 3.5 12 20.6   (PNGs of those moments into stills/, for checking)
//        add --vertical to any of these for the 1080x1920 cut (default ../lithnode-night-vertical.mp4)
//        --versus renders versus.html, the 14-second before/after (default ../lithnode-versus.mp4)
//        add --hook too for the 22-second feed cut that starts on the run (default ../lithnode-hook-vertical.mp4)
// Needs puppeteer-core (NODE_PATH) and ffmpeg (FFMPEG or on PATH). Serves the repo itself, so it needs nothing else running.
const puppeteer = require("puppeteer-core");
const http = require("http"), fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const HOOK = process.argv.includes("--hook"), T0 = HOOK ? 8 : 0;   // the hook cut is film 8–30
const VERSUS = process.argv.includes("--versus");
const FF = process.env.FFMPEG || "ffmpeg", ROOT = path.resolve(__dirname, "../.."), FPS = 30, LENGTH = VERSUS ? 14 : 30 - T0;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".mp4": "video/mp4", ".webm": "video/webm" };

// a static server with byte ranges, so the page's videos can seek
const server = http.createServer((req, res) => {
  const file = path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end(); }
  const size = fs.statSync(file).size, type = TYPES[path.extname(file)] || "application/octet-stream", m = /bytes=(\d*)-(\d*)/.exec(req.headers.range || "");
  if (m) {
    const a = m[1] ? +m[1] : 0, b = m[2] ? +m[2] : size - 1;
    res.writeHead(206, { "Content-Type": type, "Content-Range": `bytes ${a}-${b}/${size}`, "Content-Length": b - a + 1, "Accept-Ranges": "bytes" });
    fs.createReadStream(file, { start: a, end: b }).pipe(res);
  } else { res.writeHead(200, { "Content-Type": type, "Content-Length": size, "Accept-Ranges": "bytes" }); fs.createReadStream(file).pipe(res); }
});

const VERT = VERSUS || process.argv.includes("--vertical"), [VW, VH] = VERT ? [1080, 1920] : [1920, 1080];
(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const url = `http://127.0.0.1:${server.address().port}/marketing/night-film/${VERSUS ? "versus.html?" : `film.html?${VERT ? "v=1&" : ""}${HOOK ? "hook=1" : ""}`}`;
  const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new", protocolTimeout: 600000,
    args: ["--enable-gpu", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"] });
  const p = await b.newPage();
  await p.setViewport({ width: VW, height: VH });
  p.on("pageerror", (e) => console.log("pageerror", e.message));
  await p.goto(url, { waitUntil: "load" });
  await p.evaluate(() => window.ready);
  const grab = (t, type, q) => p.evaluate(async (t, type, q) => { await renderFrame(t); return document.getElementById("cv").toDataURL(type, q).split(",")[1]; }, t, type, q);
  const args = process.argv.slice(2).filter((a) => !["--vertical", "--hook", "--versus"].includes(a)),
    DEF = path.join(__dirname, VERSUS ? "../lithnode-versus.mp4" : `../lithnode-${HOOK ? "hook" : "night"}${VERT ? "-vertical" : ""}.mp4`);

  if (args[0] === "--audio") {   // new score onto the already-rendered picture
    const out = path.resolve(args[1] || DEF), tmp = path.join(__dirname, "score.pcm"), redo = out + ".tmp.mp4";
    fs.writeFileSync(tmp, Buffer.from(await p.evaluate(() => renderAudio()), "base64"));
    execFileSync(FF, ["-v", "error", "-y", "-i", out, "-ss", String(T0), "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", tmp, "-map", "0:v", "-map", "1:a",
      "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", redo]);
    fs.renameSync(redo, out); fs.rmSync(tmp); console.log("new score on", out);
  } else if (args[0] === "--stills") {
    const dir = path.join(__dirname, "stills"); fs.mkdirSync(dir, { recursive: true });
    for (const t of args.slice(1)) { fs.writeFileSync(path.join(dir, `t${(+t).toFixed(2)}.png`), Buffer.from(await grab(+t, "image/png"), "base64")); }
    console.log("stills in", dir);
  } else {
    const out = path.resolve(args[0] || DEF), dir = path.join(__dirname, "frames");
    fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir);
    const t0 = Date.now();
    for (let i = 0; i < LENGTH * FPS; i++) {
      fs.writeFileSync(path.join(dir, String(i).padStart(4, "0") + ".jpg"), Buffer.from(await grab(i / FPS, "image/jpeg", .95), "base64"));
      if (i % 90 === 0) console.log("frame", i, ((Date.now() - t0) / 1000).toFixed(0) + "s");
    }
    fs.writeFileSync(path.join(dir, "score.pcm"), Buffer.from(await p.evaluate(() => renderAudio()), "base64"));
    execFileSync(FF, ["-v", "error", "-y", "-framerate", String(FPS), "-i", path.join(dir, "%04d.jpg"),
      "-ss", String(T0), "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", path.join(dir, "score.pcm"),
      "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", out]);
    fs.rmSync(dir, { recursive: true, force: true });
    console.log("wrote", out, ((Date.now() - t0) / 1000).toFixed(0) + "s");
  }
  await b.close(); server.close();
})().catch((e) => { console.error(e); process.exit(1); });
