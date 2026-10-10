// Lithnode's own window. It starts the Lithnode engine (server/lithnode-server, built by PyInstaller)
// hidden in the background, then shows the app in a window with Lithnode's own dark title bar.
// Windows and Linux: the engine sits in server/ next to this program. Mac: in the app's Resources folder.
// Closing the window stops the engine and any runs, like Quit does.
const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const URL = "http://127.0.0.1:8790/";
const MAC = process.platform === "darwin";
const SERVER = process.platform === "win32" ? path.join(path.dirname(process.execPath), "server", "lithnode-server.exe")
  : MAC ? path.join(process.resourcesPath, "server", "lithnode-server")
  : path.join(path.dirname(process.execPath), "server", "lithnode-server");
const BAR = { color: "#111111", symbolColor: "#8d8d8d", height: 48 };   // matches the app's top bar
let win = null;
let server = null;

if (!app.requestSingleInstanceLock()) app.quit();
app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });

function ping() {
  return new Promise((resolve) => {
    const req = http.get(URL + "api/ping", (res) => {
      let body = "";
      res.on("data", (d) => { body += d; });
      res.on("end", () => resolve(body.includes("lithnode")));
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1000, () => { req.destroy(); resolve(false); });
  });
}

async function startEngine() {
  if (await ping()) return;   // already running (say, started from source)
  server = spawn(SERVER, ["--no-open"], { windowsHide: true, stdio: "ignore" });
  server.on("exit", () => { server = null; if (win) app.quit(); });   // Quit in the app ends the engine, so the window goes too
  for (let i = 0; i < 120; i++) {
    if (await ping()) return;
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error("The Lithnode engine didn't start.");
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 960, minHeight: 600, show: false,
    title: "Lithnode", backgroundColor: "#0a0a0a", icon: path.join(__dirname, MAC ? "lithnode.png" : process.platform === "win32" ? "lithnode.ico" : "lithnode.png"),
    // Mac keeps its own traffic lights (top left, over the bar); Windows and Linux draw ours at the right
    ...(MAC ? { titleBarStyle: "hiddenInset" } : { titleBarStyle: "hidden", titleBarOverlay: BAR }),
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true },
  });
  win.removeMenu();
  // no menu means no built-in shortcuts: keep reload (Ctrl+R, F5) like a browser
  win.webContents.on("before-input-event", (e, input) => {
    if (input.type === "keyDown" && (input.key === "F5" || ((input.control || input.meta) && input.key.toLowerCase() === "r"))) {
      e.preventDefault(); win.webContents.reloadIgnoringCache();
    }
  });
  win.once("ready-to-show", () => win.show());
  // links to the outside world open in the normal browser; the window only ever shows Lithnode
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(URL)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => { if (!url.startsWith(URL)) { e.preventDefault(); shell.openExternal(url); } });
  win.on("closed", () => { win = null; });
  win.loadURL(URL);
}

// the page's theme switch recolors the title bar and its buttons
ipcMain.on("bar", (_e, colors) => {
  if (!win || !colors) return;
  if (MAC) return;
  try { win.setTitleBarOverlay({ color: String(colors.color), symbolColor: String(colors.symbol) }); } catch (e) { /* older Windows */ }
});
// the system's own folder picker, on every platform (and inside the Linux sandbox, through its portal)
ipcMain.handle("pick-folder", async () => {
  const r = await dialog.showOpenDialog(win, { title: "Pick the folder your agents work in", properties: ["openDirectory", "createDirectory"] });
  return r.canceled || !r.filePaths.length ? "" : r.filePaths[0];
});

app.whenReady().then(async () => {
  try {
    await startEngine();
  } catch (e) {
    dialog.showErrorBox("Lithnode", `${e.message}\n\nTry reinstalling Lithnode from lithnode.com.`);
    app.quit();
    return;
  }
  createWindow();
});

app.on("window-all-closed", () => {
  if (server) server.kill();   // the engine stops its agents as it goes
  app.quit();
});
