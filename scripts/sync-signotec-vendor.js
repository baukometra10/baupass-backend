#!/usr/bin/env node
/**
 * Copy STPadServerLib.js into vendor/signotec/ for static deploy (Railway/Docker).
 * Sources: BAUPASS_SIGNOTEC_LIB_SRC env, then common signoPAD-API/Web install paths.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const DEST = path.join(ROOT, "vendor", "signotec", "STPadServerLib.js");
const DEST_DIR = path.dirname(DEST);

const CANDIDATES = [
  process.env.BAUPASS_SIGNOTEC_LIB_SRC,
  process.platform === "win32"
    ? "C:\\Program Files\\signotec\\signoPAD-API Web\\STPadServerLib.js"
    : null,
  process.platform === "win32"
    ? "C:\\Program Files (x86)\\signotec\\signoPAD-API Web\\STPadServerLib.js"
    : null,
  "/opt/signotec/signoPAD-API Web/STPadServerLib.js",
  "/usr/share/signotec/signoPAD-API Web/STPadServerLib.js",
].filter(Boolean);

function findSource() {
  for (const candidate of CANDIDATES) {
    const resolved = path.resolve(candidate);
    if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
      return resolved;
    }
  }
  return null;
}

function main() {
  fs.mkdirSync(DEST_DIR, { recursive: true });
  if (fs.existsSync(DEST) && fs.statSync(DEST).isFile()) {
    console.log(`[signotec] already present: ${DEST}`);
    return 0;
  }
  const source = findSource();
  if (!source) {
    console.warn("[signotec] STPadServerLib.js not found — install signoPAD-API/Web or set BAUPASS_SIGNOTEC_LIB_SRC");
    return 1;
  }
  fs.copyFileSync(source, DEST);
  const size = fs.statSync(DEST).size;
  console.log(`[signotec] copied ${source} -> ${DEST} (${size} bytes)`);
  return 0;
}

process.exit(main());
