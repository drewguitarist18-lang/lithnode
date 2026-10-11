const puppeteer = require("puppeteer-core"); const fs = require("fs"); const path = require("path");
(async () => {
  const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new", protocolTimeout: 900000,
    args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--disable-gpu-watchdog"] });
  const p = await b.newPage();
  await p.goto(require("url").pathToFileURL(path.resolve(__dirname, "render.html")).href);
  for (const [name, W, H, zoom] of [["wide", 7680, 4800, 1.35], ["tall", 3600, 6000, 2.3]]) {
    const t = Date.now();
    const url = await p.evaluate((W, H, z) => window.render(W, H, z), W, H, zoom);
    fs.writeFileSync(path.join(__dirname, `${name}.png`), Buffer.from(url.split(",")[1], "base64"));
    console.log(name, ((Date.now() - t) / 1000).toFixed(1) + "s");
  }
  await b.close();
})();
