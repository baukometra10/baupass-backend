/**
 * Fills missing TRANSLATIONS.ar keys from en (then de).
 * Appends Object.assign(TRANSLATIONS.ar, ...) to worker-i18n.js if not present.
 * Run: node scripts/fill-worker-ar-pack.js
 */
const fs = require("fs");
const path = require("path");

const FILE = path.join(__dirname, "../worker-i18n.js");
const code = fs.readFileSync(FILE, "utf8");

function parseBlock(lang) {
  const marker = `  ${lang}: {`;
  const i = code.indexOf(marker);
  if (i < 0) return {};
  let depth = 1;
  let p = i + marker.length;
  while (depth > 0 && p < code.length) {
    if (code[p] === "{") depth += 1;
    else if (code[p] === "}") depth -= 1;
    p += 1;
  }
  const block = code.slice(i + marker.length, p - 1);
  const vals = {};
  const rx = /^\s+(\w+):\s*("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)/gm;
  let m;
  while ((m = rx.exec(block)) !== null) {
    try {
      vals[m[1]] = JSON.parse(m[2].replace(/^`/, '"').replace(/`$/, '"'));
    } catch {
      vals[m[1]] = m[2].slice(1, -1);
    }
  }
  return vals;
}

const de = parseBlock("de");
const en = parseBlock("en");
const ar = parseBlock("ar");
const patch = {};
for (const key of Object.keys(de)) {
  if (ar[key]) continue;
  patch[key] = en[key] || de[key];
}

const MARKER = "// ─ WORKER AR PACK (auto-filled missing keys) ─";
if (code.includes(MARKER)) {
  console.log("Pack already present; keys to add:", Object.keys(patch).length);
  process.exit(0);
}

const lines = Object.entries(patch).map(([k, v]) => `  ${k}: ${JSON.stringify(v)},`);
const block = `\n${MARKER}\nObject.assign(TRANSLATIONS.ar, {\n${lines.join("\n")}\n});\n`;

fs.writeFileSync(FILE, code.replace(/\nconst LANG_META = /, `${block}\nconst LANG_META = `));
console.log("Added", Object.keys(patch).length, "Arabic pack keys (English fallback where AR missing).");
