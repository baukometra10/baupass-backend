const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("baupassIncomingCall", {
  respond: (action, payload) => ipcRenderer.invoke("desktop:incoming-call-respond", {
    action: String(action || ""),
    ...(payload || {}),
  }),
});
