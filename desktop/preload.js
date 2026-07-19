const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("baupassDesktop", {
  isDesktop: true,
  minimize: () => ipcRenderer.invoke("desktop:minimize"),
  toggleMaximize: () => ipcRenderer.invoke("desktop:toggle-maximize"),
  close: () => ipcRenderer.invoke("desktop:close"),
  getWindowState: () => ipcRenderer.invoke("desktop:get-window-state"),
  ensureSignotecBridge: () => ipcRenderer.invoke("desktop:ensure-signotec-bridge"),
  showIncomingCall: (payload) => ipcRenderer.invoke("desktop:show-incoming-call", payload || {}),
  dismissIncomingCall: () => ipcRenderer.invoke("desktop:dismiss-incoming-call"),
  onIncomingCallAction: (callback) => {
    if (typeof callback !== "function") {
      return () => {};
    }
    const handler = (_event, payload) => callback(payload || {});
    ipcRenderer.on("desktop:incoming-call-action", handler);
    return () => ipcRenderer.removeListener("desktop:incoming-call-action", handler);
  },
  onWindowState: (callback) => {
    if (typeof callback !== "function") {
      return () => {};
    }
    const handler = (_event, payload) => callback(payload || {});
    ipcRenderer.on("desktop:window-state", handler);
    return () => ipcRenderer.removeListener("desktop:window-state", handler);
  },
});
