// Renders film.html to an MP4: every frame through renderFrame(t), the score through renderAudio(), muxed by ffmpeg.
// Usage: node render.js [out.mp4]          (default ../lithnode-night.mp4)
//        node render.js --audio            (re-score the existing mp4 without re-rendering the picture)
//        node render.js --stills 3.5 12 20.6   (PNGs of those moments into stills/, for checking)
//        add --vertical to any of these for the 1080x1920 cut (default ../lithnode-night-vertical.mp4)
//        --versus renders versus.html, the 14-second before/after (default ../lithnode-versus.mp4); --versus --ads is the ad-scripts job
//        add --hook too for the 22-second feed cut that starts on the run (default ../lithnode-hook-vertical.mp4)
//        --phone renders phone.html, the run as a phone filming the monitor (default ../lithnode-phone-vertical.mp4)
//        --phone --jobs films the job hunt instead (default ../lithnode-phone-jobs-vertical.mp4)
//        --phone --photos writes its TikTok carousel, the slides in phone.html's PHOTOS, to ../carousel/ (with --jobs, ../carousel-jobs/)
//        --gym writes the gym carousel to ../carousel-gym/: gym.html's SHOTS, then phone.html's gym set (PASSES=8 for a quick look)
// Needs puppeteer-core (NODE_PATH) and ffmpeg (FFMPEG or on PATH). Serves the repo itself, so it needs nothing else running.
const puppeteer = require("puppeteer-core");
const http = require("http"), fs = require("fs"), path = require("path"), { execFileSync } = require("child_process");
const HOOK = process.argv.includes("--hook"), T0 = HOOK ? 8 : 0;   // the hook cut is film 8–30
const VERSUS = process.argv.includes("--versus"), ADS = process.argv.includes("--ads"), PHONE = process.argv.includes("--phone"), GYM = process.argv.includes("--gym");
const JOBS = process.argv.includes("--jobs");
const FF = process.env.FFMPEG || "ffmpeg", ROOT = path.resolve(__dirname, "../.."), FPS = 30;
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

const VERT = VERSUS || PHONE || GYM || process.argv.includes("--vertical"), [VW, VH] = VERT ? [1080, 1920] : [1920, 1080];
(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const page = GYM ? "gym.html" : PHONE ? `phone.html${JOBS ? "?job=jobs" : ""}` : VERSUS ? `versus.html?${ADS ? "job=ads" : ""}` : `film.html?${VERT ? "v=1&" : ""}${HOOK ? "hook=1" : ""}`;
  const url = `http://127.0.0.1:${server.address().port}/marketing/night-film/${page}`;
  const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new", protocolTimeout: 600000,
    args: ["--enable-gpu", "--ignore-gpu-blocklist", "--autoplay-policy=no-user-gesture-required"] });
  const p = await b.newPage();
  await p.setViewport({ width: VW, height: VH });
  p.on("pageerror", (e) => console.log("pageerror", e.message));
  await p.goto(url, { waitUntil: "load" });
  await p.evaluate(() => window.ready);
  const LENGTH = GYM ? 0 : PHONE ? await p.evaluate(() => window.LENGTH) : VERSUS ? 14 : 30 - T0;   // the phone cut's length is its clips'
  const grab = (t, type, q) => p.evaluate(async (t, type, q) => { await renderFrame(t); return document.getElementById("cv").toDataURL(type, q).split(",")[1]; }, t, type, q);
  const args = process.argv.slice(2).filter((a) => !["--vertical", "--hook", "--versus", "--ads", "--phone", "--gym", "--jobs"].includes(a)),
    DEF = path.join(__dirname, VERSUS ? `../lithnode-versus${ADS ? "-ads" : ""}.mp4` : `../lithnode-${PHONE ? (JOBS ? "phone-jobs" : "phone") : HOOK ? "hook" : "night"}${VERT ? "-vertical" : ""}.mp4`);

  if (GYM) {   // the gym's photos, then the desk's to end the story
    const dir = path.join(__dirname, "../carousel-gym"), passes = +(process.env.PASSES || 96), jpgs = [];
    for (let i = 0, n = await p.evaluate(() => window.PHOTO_COUNT); i < n; i++) jpgs.push(await p.evaluate((i, k) => renderPhoto(i, k), i, passes));
    const d = await b.newPage();
    await d.setViewport({ width: VW, height: VH });
    await d.goto(`http://127.0.0.1:${server.address().port}/marketing/night-film/phone.html?set=gym`, { waitUntil: "load" });
    await d.evaluate(() => window.ready);
    for (let i = 0, n = await d.evaluate(() => window.PHOTO_COUNT); i < n; i++) jpgs.push(await d.evaluate((i) => renderPhoto(i), i));
    fs.mkdirSync(dir, { recursive: true });
    for (const f of fs.readdirSync(dir)) if (/^\d+\.jpg$/.test(f)) fs.rmSync(path.join(dir, f));
    jpgs.forEach((j, i) => fs.writeFileSync(path.join(dir, `${i + 1}.jpg`), Buffer.from(j, "base64")));
    console.log(jpgs.length, "slides in", dir);
  } else if (args[0] === "--audio") {   // new score onto the already-rendered picture
    const out = path.resolve(args[1] || DEF), tmp = path.join(__dirname, "score.pcm"), redo = out + ".tmp.mp4";
    fs.writeFileSync(tmp, Buffer.from(await p.evaluate(() => renderAudio()), "base64"));
    execFileSync(FF, ["-v", "error", "-y", "-i", out, "-ss", String(T0), "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", tmp, "-map", "0:v", "-map", "1:a",
      "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest", redo]);
    fs.renameSync(redo, out); fs.rmSync(tmp); console.log("new score on", out);
  } else if (args[0] === "--photos") {   // the phone's carousel, one JPEG per slide
    const dir = path.join(__dirname, JOBS ? "../carousel-jobs" : "../carousel"), n = await p.evaluate(() => window.PHOTO_COUNT);
    fs.mkdirSync(dir, { recursive: true });
    for (const f of fs.readdirSync(dir)) if (/^\d+\.jpg$/.test(f)) fs.rmSync(path.join(dir, f));   // the last render's slides
    for (let i = 0; i < n; i++) fs.writeFileSync(path.join(dir, `${i + 1}.jpg`), Buffer.from(await p.evaluate((i) => renderPhoto(i), i), "base64"));
    console.log(n, "slides in", dir);
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
