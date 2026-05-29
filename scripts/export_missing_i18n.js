const fs = require("fs");
const path = require("path");
const code = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
const LANGS = ["de", "en", "tr", "ar", "fr", "es", "it", "pl"];
const start = code.indexOf("const UI_TRANSLATIONS = {");
const langs = {};
const values = {};

function parseBlock(lang) {
  const marker = `  ${lang}: {`;
  const i = code.indexOf(marker, start);
  let depth = 1;
  let p = i + marker.length;
  while (depth > 0 && p < code.length) {
    if (code[p] === "{") depth += 1;
    else if (code[p] === "}") depth -= 1;
    p += 1;
  }
  const block = code.slice(i + marker.length, p - 1);
  const keys = new Set();
  const vals = {};
  const rx = /^\s+(\w+):\s*("(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`)/gm;
  let m;
  while ((m = rx.exec(block)) !== null) {
    keys.add(m[1]);
    try {
      vals[m[1]] = JSON.parse(m[2].replace(/\n/g, "\\n"));
    } catch {
      vals[m[1]] = m[2];
    }
  }
  return { keys, vals };
}

for (const lang of LANGS) {
  const parsed = parseBlock(lang);
  langs[lang] = parsed.keys;
  values[lang] = parsed.vals;
}

const targetLangs = ["en", "tr", "ar", "fr", "es", "it", "pl"];
const de = langs.de;
for (const lang of targetLangs) {
  const missing = [...de].filter((k) => !langs[lang].has(k));
  if (!missing.length) continue;
  console.log(`\n// === ${lang.toUpperCase()} (${missing.length}) ===`);
  for (const k of missing) {
    const ref = values.en[k] || values.de[k] || k;
    console.log(`    ${k}: ${JSON.stringify(ref)},`);
  }
}
