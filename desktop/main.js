const path = require("path");
const fs = require("fs");
const http = require("http");
const https = require("https");
const { spawn } = require("child_process");
const { app, BrowserWindow, ipcMain, shell, screen } = require("electron");
const signotecBridge = require("./signotec-bridge");

// Ensure only one instance of the desktop app runs at a time.
// Extra clicks on the shortcut will just raise the existing window.
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
}

const PROJECT_ROOT = path.resolve(__dirname, "..");
const LOCAL_DESKTOP_URL = "http://127.0.0.1:8000";
const REMOTE_DESKTOP_URL = "https://baupass-control.up.railway.app";
let resolvedDesktopUrl = (process.env.BAUPASS_DESKTOP_URL || "").trim();
// Backend auto-start only makes sense when pointing at localhost.
let IS_LOCAL = false;
const AUTOSTART_BACKEND = IS_LOCAL && String(process.env.BAUPASS_DESKTOP_AUTOSTART_BACKEND || "1").trim() !== "0";

let mainWindow = null;
let splashWindow = null;
let backendProcess = null;
let backendStartedByDesktop = false;
const SPLASH_MAX_VISIBLE_MS = 1500;

function updateSplashProgress(percent, message, detail) {
  if (!splashWindow || splashWindow.isDestroyed()) {
    return;
  }

  const safePercent = Math.max(0, Math.min(100, Number(percent || 0)));
  try {
    splashWindow.setProgressBar(safePercent / 100);
    splashWindow.webContents.send("splash:progress", {
      percent: safePercent,
      message: String(message || "Ladevorgang läuft"),
      detail: String(detail || "Bitte kurz warten"),
    });
  } catch {
    // Ignore if splash has just been destroyed during shutdown.
  }
}

function buildHealthUrl(baseUrl) {
  const normalized = String(baseUrl || "").replace(/\/+$/, "");
  return `${normalized}/api/health`;
}

function probeBackend(baseUrl, timeoutMs = 600) {
  const healthUrl = buildHealthUrl(baseUrl);
  return new Promise((resolve) => {
    let parsed;
    try {
      parsed = new URL(healthUrl);
    } catch {
      resolve(false);
      return;
    }

    const client = parsed.protocol === "https:" ? https : http;
    const req = client.request(
      {
        protocol: parsed.protocol,
        hostname: parsed.hostname,
        port: parsed.port || (parsed.protocol === "https:" ? 443 : 80),
        path: parsed.pathname,
        method: "GET",
        timeout: timeoutMs,
      },
      (res) => {
        resolve(res.statusCode && res.statusCode >= 200 && res.statusCode < 500);
      }
    );
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
    req.on("error", () => resolve(false));
    req.end();
  });
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function resolvePythonCommand() {
  const candidates = [
    path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe"),
    path.join(PROJECT_ROOT, ".venv", "bin", "python"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return process.platform === "win32" ? "python" : "python3";
}

function startBackend() {
  if (backendProcess) {
    return;
  }

  const pythonCmd = resolvePythonCommand();
  // Derive the port from the resolved desktop URL so backend and frontend always match.
  let desktopPort = "8000";
  try {
    desktopPort = String(new URL(resolvedDesktopUrl || LOCAL_DESKTOP_URL).port || "8000");
  } catch {
    // keep default
  }
  backendProcess = spawn(pythonCmd, ["backend/run_prod.py"], {
    cwd: PROJECT_ROOT,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    env: { ...process.env, PORT: desktopPort, HOST: "127.0.0.1" },
  });
  backendStartedByDesktop = true;

  backendProcess.stdout.on("data", (chunk) => {
    const text = String(chunk || "").trim();
    if (text) {
      console.log(`[desktop][backend] ${text}`);
    }
  });

  backendProcess.stderr.on("data", (chunk) => {
    const text = String(chunk || "").trim();
    if (text) {
      console.warn(`[desktop][backend] ${text}`);
    }
  });

  backendProcess.on("exit", (code) => {
    console.log(`[desktop] backend exited with code ${code}`);
    backendProcess = null;
  });
}

async function ensureBackend() {
  // For hosted deployments, avoid blocking startup with a remote health probe.
  // The app should open immediately and let the web app handle its own loading state.
  if (!IS_LOCAL) {
    return;
  }

  updateSplashProgress(22, "Lokalen Dienst prüfen", "Backend-Verbindung wird getestet");

  const available = await probeBackend(resolvedDesktopUrl || LOCAL_DESKTOP_URL);
  if (available) {
    updateSplashProgress(32, "Lokaler Dienst bereit", "Anwendung wird vorbereitet");
    return;
  }
  if (!AUTOSTART_BACKEND) {
    return;
  }

  startBackend();
  updateSplashProgress(36, "Lokalen Dienst starten", "Bitte kurz warten");
  for (let i = 0; i < 30; i += 1) {
    // Wait up to about 6s for backend startup.
    // If still unavailable, the shell still opens and user sees unreachable message.
    // This avoids hanging desktop startup forever.
    // eslint-disable-next-line no-await-in-loop
    await wait(200);
    // eslint-disable-next-line no-await-in-loop
    if (await probeBackend(resolvedDesktopUrl || LOCAL_DESKTOP_URL)) {
      updateSplashProgress(48, "Lokaler Dienst verbunden", "UI wird jetzt geladen");
      return;
    }
    if (i % 5 === 0) {
      updateSplashProgress(38 + Math.min(8, Math.floor(i / 5) * 2), "Lokaler Dienst startet", "Verbindung wird aufgebaut");
    }
  }
}

function sendWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.webContents.send("desktop:window-state", {
    isMaximized: mainWindow.isMaximized(),
  });
}

function closeSplashWindow() {
  if (!splashWindow || splashWindow.isDestroyed()) {
    splashWindow = null;
    return;
  }
  splashWindow.setProgressBar(-1);
  splashWindow.close();
  splashWindow = null;
}

function createSplashWindow() {
  if (splashWindow && !splashWindow.isDestroyed()) {
    return;
  }

  splashWindow = new BrowserWindow({
    width: 560,
    height: 340,
    minWidth: 560,
    minHeight: 340,
    maxWidth: 560,
    maxHeight: 340,
    frame: false,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    show: true,
    center: true,
    backgroundColor: "#0b1218",
    autoHideMenuBar: true,
    icon: path.join(PROJECT_ROOT, process.platform === "win32" ? "worker-icon-512.ico" : "worker-icon-512.png"),
    webPreferences: {
      preload: path.join(__dirname, "splash-preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false,
    },
  });

  splashWindow.loadFile(path.join(__dirname, "splash.html")).catch(() => {
    closeSplashWindow();
  });

  splashWindow.webContents.on("did-finish-load", () => {
    updateSplashProgress(8, "SUPPIX startet", "Arbeitsbereich wird aufgebaut");
  });

  splashWindow.on("closed", () => {
    splashWindow = null;
  });
}

function createWindow() {
  updateSplashProgress(16, "Fenster wird vorbereitet", "Sichere Umgebung wird geladen");
  let mainWindowShown = false;

  const revealMainWindow = (closeDelayMs = 160) => {
    if (!mainWindow || mainWindow.isDestroyed() || mainWindowShown) {
      return;
    }
    mainWindowShown = true;
    mainWindow.show();
    mainWindow.focus();
    setTimeout(closeSplashWindow, closeDelayMs);
    sendWindowState();
  };

  mainWindow = new BrowserWindow({
    width: 1480,
    height: 920,
    minWidth: 1100,
    minHeight: 720,
    frame: false,
    show: false,
    backgroundColor: "#0d131a",
    autoHideMenuBar: true,
    icon: path.join(PROJECT_ROOT, process.platform === "win32" ? "worker-icon-512.ico" : "worker-icon-512.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      spellcheck: false,
    },
  });

  mainWindow.webContents.on("did-start-loading", () => {
    updateSplashProgress(58, "Anwendung wird geladen", "Komponenten werden initialisiert");
  });

  mainWindow.webContents.on("dom-ready", () => {
    updateSplashProgress(78, "Fast fertig", "Benutzeroberfläche wird gerendert");
  });

  // Show as soon as first paint is ready to reduce perceived startup delay.
  mainWindow.once("ready-to-show", () => {
    updateSplashProgress(90, "Anwendung bereit", "Oberfläche wird angezeigt");
    revealMainWindow(0);
  });

  mainWindow.loadURL(resolvedDesktopUrl || REMOTE_DESKTOP_URL);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("did-finish-load", () => {
    updateSplashProgress(100, "Bereit", "Willkommen in SUPPIX");
    revealMainWindow(0);
  });

  mainWindow.webContents.on("did-fail-load", () => {
    updateSplashProgress(100, "Verbindung fehlgeschlagen", "Die Oberfläche wird trotzdem geöffnet");
    revealMainWindow(300);
  });

  setTimeout(() => {
    if (mainWindow && !mainWindow.isDestroyed() && !mainWindowShown) {
      updateSplashProgress(96, "Start dauert länger", "Anwendung wird jetzt angezeigt");
      revealMainWindow(0);
    }
  }, 1000);

  mainWindow.on("maximize", sendWindowState);
  mainWindow.on("unmaximize", sendWindowState);

  mainWindow.on("closed", () => {
    closeSplashWindow();
    mainWindow = null;
  });
}

ipcMain.handle("desktop:minimize", () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.minimize();
  }
});

ipcMain.handle("desktop:toggle-maximize", () => {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  if (mainWindow.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    // Use explicit work-area bounds for reliable frameless maximize on Windows.
    try {
      const display = screen.getDisplayNearestPoint(mainWindow.getBounds());
      mainWindow.setFullScreen(false);
      mainWindow.setBounds(display.workArea, false);
    } catch {
      mainWindow.maximize();
    }
  }
  sendWindowState();
});

ipcMain.handle("desktop:close", () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.close();
  }
});

ipcMain.handle("desktop:get-window-state", () => ({
  isMaximized: Boolean(mainWindow && !mainWindow.isDestroyed() && mainWindow.isMaximized()),
}));

async function resolveDesktopUrl() {
  if (resolvedDesktopUrl) {
    return resolvedDesktopUrl;
  }
  if (process.env.BAUPASS_DESKTOP_URL) {
    resolvedDesktopUrl = String(process.env.BAUPASS_DESKTOP_URL).trim();
  } else if (await probeBackend(LOCAL_DESKTOP_URL, 800)) {
    resolvedDesktopUrl = LOCAL_DESKTOP_URL;
  } else {
    resolvedDesktopUrl = REMOTE_DESKTOP_URL;
  }
  IS_LOCAL = resolvedDesktopUrl.includes("127.0.0.1") || resolvedDesktopUrl.includes("localhost");
  return resolvedDesktopUrl;
}

ipcMain.handle("desktop:ensure-signotec-bridge", async () => {
  try {
    return await signotecBridge.ensureSignotecBridge();
  } catch (err) {
    return { ok: false, reason: String(err?.message || err || "signotec_bridge_error") };
  }
});

async function bootstrap() {
  await resolveDesktopUrl();
  if (process.platform === "win32") {
    signotecBridge.ensureSignotecBridge().then((result) => {
      console.log(`[desktop][signotec] ${JSON.stringify(result)}`);
    }).catch(() => {});
  }
  // For cloud deployments skip the splash entirely — show the main window
  // immediately so it appears within the first second.
  if (!IS_LOCAL) {
    createWindow();
    return;
  }
  createSplashWindow();
  updateSplashProgress(4, "Start initialisiert", "Bitte kurz warten");
  createWindow();
  ensureBackend().catch(() => {});
}

app.whenReady().then(bootstrap);

// Raise the existing window when the user clicks the icon again.
app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (backendStartedByDesktop && backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    resolveDesktopUrl().then(() => createWindow());
  }
});
