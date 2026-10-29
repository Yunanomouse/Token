// Bridge between the page and the workbook file. Synchronous so the page code stays simple.
const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("fcNative", {
  load: () => ipcRenderer.sendSync("fc-load"),
  save: (text) => { if (!ipcRenderer.sendSync("fc-save", text)) throw new Error("save failed"); },
  dataDir: () => ipcRenderer.sendSync("fc-datadir")
});
