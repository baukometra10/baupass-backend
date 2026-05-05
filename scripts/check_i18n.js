// Check that all runtimeText() keys exist in base (English) of getRuntimeUiTexts()
const fs = require("fs");
const path = require("path");
const code = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");

// 1. All runtimeText("key") usages
const usedKeys = new Set();
const usedRx = /runtimeText\(["']([^"']+)["']\)/g;
let m;
while ((m = usedRx.exec(code)) !== null) usedKeys.add(m[1]);

// 2. All runtimeTextTemplate("key") usages
const ttRx = /runtimeTextTemplate\(["']([^"']+)["']/g;
while ((m = ttRx.exec(code)) !== null) usedKeys.add(m[1]);

// 3. Extract base block from getRuntimeUiTexts
const fnStart = code.indexOf("function getRuntimeUiTexts()");
const baseStart = code.indexOf("const base = {", fnStart) + "const base = {".length;
// find matching }
let depth = 1, pos = baseStart;
while (depth > 0 && pos < code.length) {
  if (code[pos] === "{") depth++;
  else if (code[pos] === "}") depth--;
  pos++;
}
const baseBlock = code.slice(baseStart, pos - 1);
const baseKeys = new Set();
const baseRx = /^\s+(\w+):/gm;
let bm;
while ((bm = baseRx.exec(baseBlock)) !== null) baseKeys.add(bm[1]);

// 4. Extract map.de block
const mapStart = code.indexOf("const map = {", fnStart);
const deStart = code.indexOf("de: {", mapStart) + "de: {".length;
let depth2 = 1, pos2 = deStart;
while (depth2 > 0 && pos2 < code.length) {
  if (code[pos2] === "{") depth2++;
  else if (code[pos2] === "}") depth2--;
  pos2++;
}
const deBlock = code.slice(deStart, pos2 - 1);
const deKeys = new Set();
const deRx = /^\s+(\w+):/gm;
let dm;
while ((dm = deRx.exec(deBlock)) !== null) deKeys.add(dm[1]);

// 5. Find keys in map.de but not in base
const missingFromBase = [...usedKeys].filter((k) => !baseKeys.has(k)).sort();
const deOnlyKeys = [...deKeys].filter((k) => !baseKeys.has(k)).sort();

console.log("=== runtimeText keys USED but NOT in base (show German in EN) ===");
if (missingFromBase.length === 0) {
  console.log("  (none - all good!)");
} else {
  missingFromBase.forEach((k) => console.log("  MISSING:", k));
}
console.log("");
console.log("=== map.de keys NOT in base (German shows for all non-DE langs) ===");
if (deOnlyKeys.length === 0) {
  console.log("  (none - all good!)");
} else {
  deOnlyKeys.forEach((k) => console.log("  DE-ONLY:", k));
}
console.log("");
console.log(`Used: ${usedKeys.size}  Base: ${baseKeys.size}  Missing: ${missingFromBase.length}  DE-only: ${deOnlyKeys.length}`);

// 6. Check UI_TRANSLATIONS (data-ui-i18n) keys exist for all 8 languages
const uiTransStart = code.indexOf("const UI_TRANSLATIONS = {");
const uiTransEnd = code.indexOf("\n};", uiTransStart) + 2;
const uiBlock = code.slice(uiTransStart, uiTransEnd);
const LANGS = ["de", "en", "tr", "ar", "fr", "es", "it", "pl"];

// Extract keys per language from UI_TRANSLATIONS
const uiKeys = {};
LANGS.forEach((lang) => {
  const langRx = new RegExp(`["']${lang}["']\\s*:\\s*\\{([^}]*)\\}`, "g");
  let lm;
  while ((lm = langRx.exec(uiBlock)) !== null) {
    const block = lm[1];
    if (!uiKeys[lang]) uiKeys[lang] = new Set();
    const kRx = /["']([^"']+)["']\s*:/g;
    let km;
    while ((km = kRx.exec(block)) !== null) uiKeys[lang].add(km[1]);
  }
});

// Find data-ui-i18n keys used in HTML
const htmlCode = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8");
const htmlKeys = new Set();
const htmlRx = /data-ui-i18n="([^"]+)"/g;
while ((m = htmlRx.exec(htmlCode)) !== null) htmlKeys.add(m[1]);
// Also from app.js dynamic html
const jsHtmlRx = /data-ui-i18n="([^"]+)"/g;
while ((m = jsHtmlRx.exec(code)) !== null) htmlKeys.add(m[1]);

console.log("\n=== data-ui-i18n keys per language coverage ===");
const deKeys2 = uiKeys["de"] || new Set();
let uiMissingTotal = 0;
LANGS.forEach((lang) => {
  const langKeySet = uiKeys[lang] || new Set();
  const missingInLang = [...deKeys2].filter((k) => !langKeySet.has(k));
  if (missingInLang.length > 0) {
    console.log(`  ${lang.toUpperCase()} missing ${missingInLang.length}: ${missingInLang.slice(0, 10).join(", ")}${missingInLang.length > 10 ? "..." : ""}`);
    uiMissingTotal += missingInLang.length;
  }
});
if (uiMissingTotal === 0) console.log("  All 8 languages have all UI_TRANSLATIONS keys!");

// 7. Check data-ui-i18n keys actually exist in UI_TRANSLATIONS
console.log("\n=== data-ui-i18n keys used in HTML/JS but not in UI_TRANSLATIONS (DE) ===");
let htmlMissing = 0;
htmlKeys.forEach((k) => {
  if (!deKeys2.has(k)) {
    console.log("  HTML-KEY-MISSING:", k);
    htmlMissing++;
  }
});
if (htmlMissing === 0) console.log("  All data-ui-i18n keys exist in UI_TRANSLATIONS!");
