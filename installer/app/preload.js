// What the page can ask of the window: recolor the title bar to match the theme, and open the folder picker.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lithnodeApp", {
  platform: process.platform,
  setBar: (color, symbol) => ipcRenderer.send("bar", { color, symbol }),
  pickFolder: () => ipcRenderer.invoke("pick-folder"),
});
