const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn } = require("child_process");

const PORT = 49494;
let childProcess = null;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function findSTPadServerExe() {
  const candidates = [
    path.join(process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)", "signotec", "signoPAD-API Web", "STPadServer.exe"),
    path.join(process.env.ProgramFiles || "C:\\Program Files", "signotec", "signoPAD-API Web", "STPadServer.exe"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function isPortOpen(port = PORT, host = "127.0.0.1", timeoutMs = 800) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      try { socket.destroy(); } catch { /* ignore */ }
      resolve(ok);
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(false));
    socket.once("error", () => finish(false));
    socket.connect(port, host);
  });
}

async function ensureSignotecBridge() {
  if (process.platform !== "win32") {
    return { ok: false, reason: "not_windows" };
  }
  if (await isPortOpen()) {
    return { ok: true, reason: "already_running" };
  }
  const exe = findSTPadServerExe();
  if (!exe) {
    return { ok: false, reason: "not_installed" };
  }
  const workDir = path.dirname(exe);
  if (childProcess && !childProcess.killed) {
    try { childProcess.kill(); } catch { /* ignore */ }
  }
  childProcess = spawn(exe, [String(PORT)], {
    cwd: workDir,
    windowsHide: true,
    stdio: "ignore",
    detached: false,
  });
  for (let i = 0; i < 40; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await wait(250);
    // eslint-disable-next-line no-await-in-loop
    if (await isPortOpen()) {
      return { ok: true, reason: "started", exe };
    }
  }
  return { ok: false, reason: "start_failed", exe };
}

module.exports = {
  PORT,
  findSTPadServerExe,
  isPortOpen,
  ensureSignotecBridge,
};
