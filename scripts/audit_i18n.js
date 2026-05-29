const fs = require("fs");
const path = require("path");
const code = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
const LANGS = ["de", "en", "tr", "ar", "fr", "es", "it", "pl"];
const start = code.indexOf("const UI_TRANSLATIONS = {");
const langs = {};

for (const lang of LANGS) {
  const marker = `  ${lang}: {`;
  const i = code.indexOf(marker, start);
  if (i < 0) {
    console.log("block not found:", lang);
    continue;
  }
  let depth = 1;
  let p = i + marker.length;
  while (depth > 0 && p < code.length) {
    if (code[p] === "{") depth += 1;
    else if (code[p] === "}") depth -= 1;
    p += 1;
  }
  const block = code.slice(i + marker.length, p - 1);
  langs[lang] = new Set([...block.matchAll(/^\s+(\w+):/gm)].map((m) => m[1]));
}

const de = langs.de;
console.log("DE keys:", de.size);
for (const lang of LANGS) {
  const missing = [...de].filter((k) => !langs[lang].has(k));
  if (missing.length) {
    console.log(`${lang.toUpperCase()} missing ${missing.length}:`, missing.join(", "));
  }
}

const uiKeys = new Set([...code.matchAll(/uiT\(["']([^"']+)["']\)/g)].map((m) => m[1]));
const missingUi = [...uiKeys].filter((k) => !de.has(k)).sort();
console.log("\nuiT() keys not in UI_TRANSLATIONS.de:", missingUi.length);
if (missingUi.length) console.log(missingUi.join(", "));

const watch = [
  "dashOverviewEyebrow",
  "dashOverviewH3",
  "opsExpiringDocs30",
  "opsExpiredDocs",
  "statsLockedWorkers",
  "statsExpiringCritical",
];
console.log("\nWatch keys:");
for (const k of watch) {
  const row = LANGS.map((lang) => `${lang}:${langs[lang]?.has(k) ? "✓" : "✗"}`).join(" ");
  console.log(k, row);
}
