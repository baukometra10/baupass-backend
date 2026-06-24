/**
 * Replace MyMemory rate-limit poison strings using app.js en/de source packs.
 */
import { readFileSync, writeFileSync } from "fs";
import { EXTRA_UI_STRINGS } from "./ui-extra-translations.mjs";

const path = "app-i18n-extra-langs.js";
const appSrc = readFileSync("app.js", "utf8");
const src0 = readFileSync(path, "utf8");

function extractAppBlock(lang) {
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
  for (const m of block.matchAll(/\n\s+([a-zA-Z0-9_]+):\s*"((?:\\.|[^"\\])*)"/g)) {
    out[m[1]] = JSON.parse(`"${m[2]}"`);
  }
  return out;
}

function parsePack(block) {
  const out = {};
  for (const m of block.matchAll(/\n    ([a-zA-Z0-9_]+): "((?:\\.|[^"\\])*)"/g)) {
    out[m[1]] = JSON.parse(`"${m[2]}"`);
  }
  return out;
}

function esc(s) {
  return String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

const appEn = extractAppBlock("en");
const appDe = extractAppBlock("de");
const enBlock = src0.match(/en: \{([\s\S]*?)\n    \},/)[1];
const en = { ...parsePack(enBlock), ...appEn, ...(EXTRA_UI_STRINGS.en || {}) };
const langs = ["tr", "fr", "es", "it", "pl"];
const packs = { en };

for (const lang of langs) {
  const m = src0.match(new RegExp(`${lang}: \\{([\\s\\S]*?)\\n    \\},`));
  packs[lang] = { ...parsePack(m[1]), ...(EXTRA_UI_STRINGS[lang] || {}) };
}

function goodSource(key) {
  for (const src of [en[key], appEn[key], appDe[key]]) {
    if (src && !String(src).includes("MYMEMORY WARNING")) return src;
  }
  return "";
}

let fixed = 0;
for (const lang of langs) {
  for (const key of Object.keys(packs[lang])) {
    const val = String(packs[lang][key]);
    if (!val.includes("MYMEMORY WARNING")) continue;
    const replacement = goodSource(key);
    if (replacement) {
      packs[lang][key] = replacement;
      fixed++;
    }
  }
}

function packToJs(obj) {
  return Object.entries(obj)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `    ${k}: "${esc(v)}",`)
    .join("\n");
}

const js = `/* Auto-generated — scripts/build-app-i18n-extra.mjs */
(function (global) {
  const STRINGS = {
    en: {
${packToJs(packs.en)}
    },
    tr: {
${packToJs(packs.tr)}
    },
    fr: {
${packToJs(packs.fr)}
    },
    es: {
${packToJs(packs.es)}
    },
    it: {
${packToJs(packs.it)}
    },
    pl: {
${packToJs(packs.pl)}
    },
  };
  global.AppI18nExtra = STRINGS;
})(typeof window !== "undefined" ? window : globalThis);
`;

writeFileSync(path, js);
const left = (js.match(/MYMEMORY WARNING/g) || []).length;
console.log("Fixed", fixed, "entries; MYMEMORY left:", left);
