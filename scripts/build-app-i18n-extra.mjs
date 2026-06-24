/**
 * Build app-i18n-extra-langs.js — fills UI_TRANSLATIONS gaps for tr/fr/es/it/pl (+ en fixes).
 * Uses MyMemory API with on-disk cache. Re-run after adding new de-only keys.
 */
import { readFileSync, writeFileSync, existsSync } from "fs";
import { EXTRA_UI_STRINGS } from "./ui-extra-translations.mjs";

const TARGET_LANGS = ["tr", "fr", "es", "it", "pl"];
const LANGPAIR = { tr: "tr", fr: "fr", es: "es", it: "it", pl: "pl" };
const CACHE_PATH = "scripts/translation-cache.json";
const OUT_PATH = "app-i18n-extra-langs.js";

const appSrc = readFileSync("app.js", "utf8");
const missingRows = JSON.parse(readFileSync("scripts/missing-keys-en.json", "utf8"));

function extractBlock(lang) {
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
  while ((m = re.exec(block))) {
    try {
      out[m[1]] = JSON.parse(`"${m[2]}"`);
    } catch {
      out[m[1]] = m[2];
    }
  }
  return out;
}

const de = extractBlock("de");
const en = extractBlock("en");
const existing = Object.fromEntries(TARGET_LANGS.map((l) => [l, extractBlock(l)]));

function isGermanish(text) {
  if (!text) return false;
  return /[äöüßÄÖÜ]|(?:ung|heit|keit|ieren|schaft)\b|Mitarbeiter|Firma|Rechnung|Dokument|Zutritt|Betrieb|Ausweis|Schicht|Versand|Bitte |Fehler|Speichern|Löschen|öffnen|ändern/i.test(text);
}

function sourceText(key) {
  if (EXTRA_UI_STRINGS.en?.[key]) return { text: EXTRA_UI_STRINGS.en[key], src: "en" };
  if (en[key] && !isGermanish(en[key])) return { text: en[key], src: "en" };
  if (de[key]) return { text: de[key], src: "de" };
  const row = missingRows.find((r) => r.key === key);
  if (row?.en && !isGermanish(row.en)) return { text: row.en, src: "en" };
  if (row?.en) return { text: row.en, src: "de" };
  return { text: key, src: "en" };
}

const cache = existsSync(CACHE_PATH) ? JSON.parse(readFileSync(CACHE_PATH, "utf8")) : {};

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function translateText(text, lang, srcLang) {
  if (!text || lang === srcLang) return text;
  const cacheKey = `${srcLang}|${lang}|${text}`;
  if (cache[cacheKey]) return cache[cacheKey];
  const pair = `${srcLang}|${LANGPAIR[lang]}`;
  const url = `https://api.mymemory.translated.net/get?q=${encodeURIComponent(text)}&langpair=${pair}`;
  const res = await fetch(url);
  const data = await res.json();
  let out = data?.responseData?.translatedText || text;
  if (out === text && srcLang === "de" && lang !== "de") {
    const enUrl = `https://api.mymemory.translated.net/get?q=${encodeURIComponent(text)}&langpair=de|en`;
    await sleep(350);
    const enRes = await fetch(enUrl);
    const enData = await enRes.json();
    const enText = enData?.responseData?.translatedText;
    if (enText && enText !== text) {
      await sleep(350);
      const res2 = await fetch(`https://api.mymemory.translated.net/get?q=${encodeURIComponent(enText)}&langpair=en|${LANGPAIR[lang]}`);
      const data2 = await res2.json();
      out = data2?.responseData?.translatedText || enText;
    }
  }
  cache[cacheKey] = out;
  return out;
}

const keys = Object.keys(de).filter((k) => TARGET_LANGS.some((l) => !existing[l][k]));
console.log("Keys to fill:", keys.length);

const packs = { en: { ...EXTRA_UI_STRINGS.en } };
for (const lang of TARGET_LANGS) packs[lang] = { ...(EXTRA_UI_STRINGS[lang] || {}) };

const textJobs = [];
const jobIndex = new Map();
for (const key of keys) {
  const { text, src } = sourceText(key);
  if (!packs.en[key] && src === "en") packs.en[key] = text;
  for (const lang of TARGET_LANGS) {
    if (packs[lang][key] || existing[lang][key]) continue;
    const jobKey = `${src}\0${lang}\0${text}`;
    if (!jobIndex.has(jobKey)) {
      const job = { src, lang, text, keys: [] };
      jobIndex.set(jobKey, job);
      textJobs.push(job);
    }
    jobIndex.get(jobKey).keys.push(key);
  }
}

console.log("Unique translation jobs:", textJobs.length);

let done = 0;
for (const job of textJobs) {
  const translated = await translateText(job.text, job.lang, job.src);
  for (const key of job.keys) packs[job.lang][key] = translated;
  done++;
  if (done % 20 === 0) {
    console.log(`Progress ${done}/${textJobs.length}`);
    writeFileSync(CACHE_PATH, JSON.stringify(cache, null, 2));
  }
  await sleep(350);
}

writeFileSync(CACHE_PATH, JSON.stringify(cache, null, 2));

function esc(s) {
  return String(s)
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n");
}

function packToJs(obj) {
  const lines = Object.entries(obj)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `    ${k}: "${esc(v)}",`);
  return lines.join("\n");
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

writeFileSync(OUT_PATH, js);
console.log("Wrote", OUT_PATH);
for (const lang of ["en", ...TARGET_LANGS]) {
  console.log(lang, Object.keys(packs[lang]).length, "keys");
}
