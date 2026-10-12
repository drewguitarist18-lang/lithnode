// Renders film.html to an MP4: every frame through renderFrame(t), the score through renderAudio(), muxed by ffmpeg.
// Usage: node render.js [out.mp4]          (default ../lithnode-night.mp4)
//        node render.js --audio            (re-score the existing mp4 without re-rendering the picture)
//        node render.js --stills 3.5 12 20.6   (PNGs of those moments into stills/, for checking)
// Needs puppeteer-core (NODE_PATH) and ffmpeg (FFMPEG or on PATH). Serves the repo itself, so it needs nothing else running.
const puppeteer = require("puppeteer-core");
const http = require("http"), fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const FF = process.env.FFMPEG || "ffmpeg", ROOT = path.resolve(__dirname, "../.."), FPS = 30, LENGTH = 30;
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

(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const url = `http://127.0.0.1:${server.address().port}/marketing/night-film/film.html`;
  const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new", protocolTimeout: 600000,
    args: ["--enable-gpu", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"] });
  const p = await b.newPage();
  await p.setViewport({ width: 1920, height: 1080 });
  p.on("pageerror", (e) => console.log("pageerror", e.message));
  await p.goto(url, { waitUntil: "load" });
  await p.evaluate(() => window.ready);
  const grab = (t, type, q) => p.evaluate(async (t, type, q) => { await renderFrame(t); return document.getElementById("cv").toDataURL(type, q).split(",")[1]; }, t, type, q);
  const args = process.argv.slice(2);

  if (args[0] === "--audio") {   // new score onto the already-rendered picture
    const out = path.resolve(args[1] || path.join(__dirname, "../lithnode-night.mp4")), tmp = path.join(__dirname, "score.pcm"), redo = out + ".tmp.mp4";
    fs.writeFileSync(tmp, Buffer.from(await p.evaluate(() => renderAudio()), "base64"));
    execFileSync(FF, ["-v", "error", "-y", "-i", out, "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", tmp, "-map", "0:v", "-map", "1:a",
      "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", redo]);
    fs.renameSync(redo, out); fs.rmSync(tmp); console.log("new score on", out);
  } else if (args[0] === "--stills") {
    const dir = path.join(__dirname, "stills"); fs.mkdirSync(dir, { recursive: true });
    for (const t of args.slice(1)) { fs.writeFileSync(path.join(dir, `t${(+t).toFixed(2)}.png`), Buffer.from(await grab(+t, "image/png"), "base64")); }
    console.log("stills in", dir);
  } else {
    const out = path.resolve(args[0] || path.join(__dirname, "../lithnode-night.mp4")), dir = path.join(__dirname, "frames");
    fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir);
    const t0 = Date.now();
    for (let i = 0; i < LENGTH * FPS; i++) {
      fs.writeFileSync(path.join(dir, String(i).padStart(4, "0") + ".jpg"), Buffer.from(await grab(i / FPS, "image/jpeg", .95), "base64"));
      if (i % 90 === 0) console.log("frame", i, ((Date.now() - t0) / 1000).toFixed(0) + "s");
    }
    fs.writeFileSync(path.join(dir, "score.pcm"), Buffer.from(await p.evaluate(() => renderAudio()), "base64"));
    execFileSync(FF, ["-v", "error", "-y", "-framerate", String(FPS), "-i", path.join(dir, "%04d.jpg"),
      "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", path.join(dir, "score.pcm"),
      "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", out]);
    fs.rmSync(dir, { recursive: true, force: true });
    console.log("wrote", out, ((Date.now() - t0) / 1000).toFixed(0) + "s");
  }
  await b.close(); server.close();
})().catch((e) => { console.error(e); process.exit(1); });
