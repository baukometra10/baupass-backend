#!/usr/bin/env node
/**
 * Copy STPadServerLib.js into vendor/signotec/ for static deploy (Railway/Docker).
 * Sources: existing dest, BAUPASS_SIGNOTEC_LIB_SRC, install paths, local signoPAD WebSocket.
 */
const fs = require("fs");
const path = require("path");
const https = require("https");

const ROOT = path.resolve(__dirname, "..");
const DEST = path.join(ROOT, "vendor", "signotec", "STPadServerLib.js");
const DEST_DIR = path.dirname(DEST);
const INSTALLER_FILENAME = "signotec_signoPAD-API_Web_3.5.0.exe";
const INSTALLER_DEST = path.join(DEST_DIR, INSTALLER_FILENAME);
const INSTALLER_URL = String(
  process.env.BAUPASS_SIGNOTEC_INSTALLER_URL
    || "https://backend.signotec.com/wp-content/uploads/2025/11/signotec_signoPAD-API_Web_3.5.0.exe",
).trim();
const INSTALLER_MIN_BYTES = 5_000_000;

function versionedSampleLibPaths() {
  if (process.platform !== "win32") return [];
  const roots = [
    "C:\\Program Files\\signotec\\signoPAD-API Web\\Sample",
    "C:\\Program Files (x86)\\signotec\\signoPAD-API Web\\Sample",
  ];
  const hits = [];
  for (const root of roots) {
    try {
      if (!fs.existsSync(root)) continue;
      for (const name of fs.readdirSync(root)) {
        if (/^STPadServerLib(?:-\d+\.\d+\.\d+)?\.js$/i.test(name)) {
          hits.push(path.join(root, name));
        }
      }
    } catch {
      // ignore unreadable sample dirs
    }
  }
  return hits;
}

const CANDIDATES = [
  process.env.BAUPASS_SIGNOTEC_LIB_SRC,
  ...versionedSampleLibPaths(),
  process.platform === "win32"
    ? "C:\\Program Files\\signotec\\signoPAD-API Web\\STPadServerLib.js"
    : null,
  process.platform === "win32"
    ? "C:\\Program Files (x86)\\signotec\\signoPAD-API Web\\STPadServerLib.js"
    : null,
  process.platform === "win32"
    ? "C:\\Program Files\\signotec\\signoPAD-API\\Web\\STPadServerLib.js"
    : null,
  "/opt/signotec/signoPAD-API Web/STPadServerLib.js",
  "/usr/share/signotec/signoPAD-API Web/STPadServerLib.js",
].filter(Boolean);

const LOCAL_FETCH_URLS = [
  "https://127.0.0.1:49494/STPadServerLib.js",
  "https://localhost:49494/STPadServerLib.js",
  "https://local.signotecwebsocket.de:49494/STPadServerLib.js",
];

function isValidSignotecLib(content) {
  return typeof content === "string" && content.includes("STPadServerLibCommons");
}

function findSourceFile() {
  for (const candidate of CANDIDATES) {
    const resolved = path.resolve(candidate);
    if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
      return resolved;
    }
  }
  if (process.platform === "win32") {
    const roots = [
      "C:\\Program Files",
      "C:\\Program Files (x86)",
      process.env.LOCALAPPDATA,
      process.env.ProgramData,
    ].filter(Boolean);
    for (const root of roots) {
      try {
        const hit = walkForFile(root, "STPadServerLib.js", 5);
        if (hit) return hit;
      } catch {
        // ignore unreadable roots
      }
    }
  }
  return null;
}

function walkForFile(dir, filename, maxDepth, depth = 0) {
  if (depth > maxDepth) return null;
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return null;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isFile() && entry.name.toLowerCase() === filename.toLowerCase()) {
      return full;
    }
    if (entry.isDirectory()) {
      const nested = walkForFile(full, filename, maxDepth, depth + 1);
      if (nested) return nested;
    }
  }
  return null;
}

function fetchLocalSignotecLib(url, timeoutMs = 4000) {
  return new Promise((resolve) => {
    const req = https.get(url, { rejectUnauthorized: false, timeout: timeoutMs }, (res) => {
      if (res.statusCode !== 200) {
        res.resume();
        resolve(null);
        return;
      }
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        resolve(isValidSignotecLib(text) ? text : null);
      });
    });
    req.on("error", () => resolve(null));
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
  });
}

async function fetchFromRunningPadServer() {
  for (const url of LOCAL_FETCH_URLS) {
    const content = await fetchLocalSignotecLib(url);
    if (content) {
      return { content, source: url };
    }
  }
  return null;
}

function downloadRemoteFile(url, dest, minBytes, timeoutMs = 180000) {
  return new Promise((resolve, reject) => {
    const requestOnce = (currentUrl, redirectsLeft = 5) => {
      const req = https.get(currentUrl, { timeout: timeoutMs }, (res) => {
        if (
          redirectsLeft > 0
          && res.statusCode >= 300
          && res.statusCode < 400
          && res.headers.location
        ) {
          res.resume();
          requestOnce(res.headers.location, redirectsLeft - 1);
          return;
        }
        if (res.statusCode !== 200) {
          res.resume();
          reject(new Error(`HTTP ${res.statusCode} for ${currentUrl}`));
          return;
        }
        const file = fs.createWriteStream(dest);
        res.pipe(file);
        file.on("error", (err) => {
          try { fs.unlinkSync(dest); } catch { /* ignore */ }
          reject(err);
        });
        file.on("finish", () => {
          file.close(() => {
            try {
              const size = fs.statSync(dest).size;
              if (size < minBytes) {
                fs.unlinkSync(dest);
                reject(new Error(`installer too small (${size} bytes)`));
                return;
              }
              resolve(size);
            } catch (err) {
              reject(err);
            }
          });
        });
      });
      req.on("error", reject);
      req.on("timeout", () => {
        req.destroy();
        reject(new Error(`timeout downloading ${currentUrl}`));
      });
    };
    requestOnce(url);
  });
}

async function syncInstaller() {
  if (fs.existsSync(INSTALLER_DEST) && fs.statSync(INSTALLER_DEST).isFile()) {
    const size = fs.statSync(INSTALLER_DEST).size;
    if (size >= INSTALLER_MIN_BYTES) {
      console.log(`[signotec] installer already present: ${INSTALLER_DEST} (${size} bytes)`);
      return 0;
    }
  }
  if (!INSTALLER_URL) {
    console.warn("[signotec] installer URL not configured");
    return 1;
  }
  try {
    console.log(`[signotec] downloading installer from ${INSTALLER_URL}`);
    const size = await downloadRemoteFile(INSTALLER_URL, INSTALLER_DEST, INSTALLER_MIN_BYTES);
    console.log(`[signotec] installer saved -> ${INSTALLER_DEST} (${size} bytes)`);
    return 0;
  } catch (err) {
    console.warn(`[signotec] installer download failed: ${err?.message || err}`);
    return 1;
  }
}

async function syncLibrary() {
  fs.mkdirSync(DEST_DIR, { recursive: true });
  if (fs.existsSync(DEST) && fs.statSync(DEST).isFile()) {
    const existing = fs.readFileSync(DEST, "utf8");
    if (isValidSignotecLib(existing)) {
      console.log(`[signotec] already present: ${DEST}`);
      return 0;
    }
  }

  const fileSource = findSourceFile();
  if (fileSource) {
    fs.copyFileSync(fileSource, DEST);
    const size = fs.statSync(DEST).size;
    console.log(`[signotec] copied ${fileSource} -> ${DEST} (${size} bytes)`);
    return 0;
  }

  const remote = await fetchFromRunningPadServer();
  if (remote) {
    fs.writeFileSync(DEST, remote.content, "utf8");
    const size = fs.statSync(DEST).size;
    console.log(`[signotec] fetched ${remote.source} -> ${DEST} (${size} bytes)`);
    return 0;
  }

  console.warn(
    "[signotec] STPadServerLib.js not found — install signoPAD-API/Web, start STPadServer, or set BAUPASS_SIGNOTEC_LIB_SRC / BAUPASS_SIGNOTEC_LIB_BASE64",
  );
  return 1;
}

async function main() {
  fs.mkdirSync(DEST_DIR, { recursive: true });
  const libCode = await syncLibrary();
  const installerCode = await syncInstaller();
  if (libCode === 0 && installerCode === 0) return 0;
  if (libCode === 0) return 0;
  return libCode;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error("[signotec] sync failed:", err?.message || err);
    process.exit(1);
  });
