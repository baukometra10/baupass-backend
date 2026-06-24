import { readFileSync, writeFileSync } from "fs";

const appSrc = readFileSync("app.js", "utf8");
const adminLangsSrc = readFileSync("admin-v2/i18n-strings-langs.js", "utf8");

function extractUiBlock(lang) {
  const anchor = appSrc.indexOf("const UI_TRANSLATIONS");
  const marker = `\n  ${lang}: {`;
  const start = appSrc.indexOf(marker, anchor);
  if (start < 0) return {};
  let depth = 0;
  let i = appSrc.indexOf("{", start);
  for (; i < appSrc.length; i++) {
    if (appSrc[i] === "{") depth++;
    else if (appSrc[i] === "}") {
      depth--;
      if (depth === 0) break;
    }
  }
  const block = appSrc.slice(start, i + 1);
  const out = {};
  const re = /\n\s+([a-zA-Z0-9_]+):\s*"((?:\\.|[^"\\])*)"/g;
  let m;
  while ((m = re.exec(block))) out[m[1]] = m[1].includes("Html") ? m[2] : JSON.parse(`"${m[2]}"`);
  return out;
}

function extractAdminLangs() {
  const out = { tr: {}, fr: {}, es: {}, it: {}, pl: {} };
  for (const lang of Object.keys(out)) {
    const marker = `${lang}: {`;
    const start = adminLangsSrc.indexOf(marker);
    if (start < 0) continue;
    let depth = 0;
    let i = adminLangsSrc.indexOf("{", start);
    for (; i < adminLangsSrc.length; i++) {
      if (adminLangsSrc[i] === "{") depth++;
      else if (adminLangsSrc[i] === "}") {
        depth--;
        if (depth === 0) break;
      }
    }
    const block = adminLangsSrc.slice(start, i + 1);
    const re = /\n\s+([a-zA-Z0-9_]+):\s*"((?:\\.|[^"\\])*)"/g;
    let m;
    while ((m = re.exec(block))) out[lang][m[1]] = JSON.parse(`"${m[2]}"`);
  }
  return out;
}

const de = extractUiBlock("de");
const en = extractUiBlock("en");
const admin = extractAdminLangs();
const targetLangs = ["tr", "fr", "es", "it", "pl"];
const existing = Object.fromEntries(targetLangs.map((l) => [l, extractUiBlock(l)]));

const missingByLang = {};
for (const lang of targetLangs) {
  missingByLang[lang] = Object.keys(de).filter((k) => !existing[lang][k]);
}

const report = {
  missingCounts: Object.fromEntries(targetLangs.map((l) => [l, missingByLang[l].length])),
  adminOverlap: {},
};
for (const lang of targetLangs) {
  report.adminOverlap[lang] = missingByLang[lang].filter((k) => admin[lang][k]).length;
}
console.log(JSON.stringify(report, null, 2));

// Build extra packs: prefer admin-v2, then EN (not DE) as interim labeled
const extra = {};
for (const lang of targetLangs) {
  extra[lang] = {};
  for (const key of missingByLang[lang]) {
    if (admin[lang][key]) extra[lang][key] = admin[lang][key];
    else if (en[key]) extra[lang][key] = en[key];
    else if (de[key]) extra[lang][key] = de[key];
  }
}

writeFileSync("scripts/i18n-extra-draft.json", JSON.stringify({ missingByLang, extra }, null, 2));
console.log("Wrote scripts/i18n-extra-draft.json");
