const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("studio", {
  onStatus: (cb) => ipcRenderer.on("status", (_e, s) => cb(s)),
  onFatal: (cb) => ipcRenderer.on("fatal", (_e, m) => cb(m)),
  retry: () => ipcRenderer.invoke("retry"),
  quit: () => ipcRenderer.invoke("quit"),
  openLogs: () => ipcRenderer.invoke("open-logs"),
});
