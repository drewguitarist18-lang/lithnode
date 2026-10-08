// The one thing the page can ask of the window: recolor the title bar to match the theme.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lithnodeApp", {
  setBar: (color, symbol) => ipcRenderer.send("bar", { color, symbol }),
});
