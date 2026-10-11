const puppeteer = require("puppeteer-core"); const fs = require("fs"); const path = require("path");
(async () => {
  const [name, W, H, zoom, N] = process.argv.slice(2);
  const dir = path.resolve(__dirname, "frames-" + name); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new", protocolTimeout: 900000,
    args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--disable-gpu-watchdog"] });
  const p = await b.newPage();
  await p.goto(require("url").pathToFileURL(path.resolve(__dirname, "render.html")).href);
  const t0 = Date.now();
  for (let i = 0; i < +N; i++) {
    const url = await p.evaluate((W, H, z, spin) => {
      window.SPIN = spin;
      window.render(W * 2, H * 2, z);                              // twice the size, then scaled down: smooth edges
      const big = document.getElementById("c"), out = document.createElement("canvas"); out.width = W; out.height = H;
      const g = out.getContext("2d"); g.imageSmoothingQuality = "high"; g.drawImage(big, 0, 0, W, H);
      return out.toDataURL("image/png");
    }, +W, +H, +zoom, -2 * Math.PI * i / +N);
    fs.writeFileSync(path.join(dir, `f${String(i).padStart(4, "0")}.png`), Buffer.from(url.split(",")[1], "base64"));
    if (i % 60 === 0) console.log(name, i, ((Date.now() - t0) / 1000).toFixed(0) + "s");
  }
  await b.close();
})();
