const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("desktop", {
  readSettings: () => ipcRenderer.invoke("settings:read"),
  saveSettings: (backend) => ipcRenderer.invoke("settings:save", backend),
  probeBackend: (backend) => ipcRenderer.invoke("backend:probe", backend),
  session: () => ipcRenderer.invoke("auth:session"),
  login: (credentials) => ipcRenderer.invoke("auth:login", credentials),
  logout: () => ipcRenderer.invoke("auth:logout"),
  request: (options) => ipcRenderer.invoke("api:request", options),
  exportInvoice: (id) => ipcRenderer.invoke("invoice:export", id),
  print: () => ipcRenderer.invoke("invoice:print"),
});
