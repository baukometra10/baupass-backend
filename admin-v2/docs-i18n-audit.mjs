#!/usr/bin/env node
/**
 * SUPPIX Docs i18n audit — catalogs data-di18n + dt() keys vs DocsPageI18n packs.
 * Also checks template DE/EN/AR body coverage for TEMPLATE_META_IDS.
 * Usage: node admin-v2/docs-i18n-audit.mjs
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = __dirname;

const html = fs.readFileSync(path.join(root, "docs.html"), "utf8");
const app = fs.readFileSync(path.join(root, "docs-app.js"), "utf8");
const i18nSrc = fs.readFileSync(path.join(root, "docs-i18n.js"), "utf8");
const contentSrc = fs.readFileSync(path.join(root, "docs-i18n-content.js"), "utf8");

const htmlKeys = [...html.matchAll(/data-di18n="([^"]+)"/g)].map((m) => m[1]);
const dtKeys = [...app.matchAll(/\bdt\(\s*["']([^"']+)["']/g)].map((m) => m[1]);

function extractObjectLiteral(src, marker) {
  const start = src.indexOf(marker);
  if (start < 0) throw new Error("marker not found: " + marker);
  const braceStart = src.indexOf("{", start);
  let depth = 0;
  let inStr = false;
  let quote = "";
  let esc = false;
  for (let i = braceStart; i < src.length; i++) {
    const ch = src[i];
    if (inStr) {
      if (esc) {
        esc = false;
        continue;
      }
      if (ch === "\\") {
        esc = true;
        continue;
      }
      if (ch === quote) inStr = false;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      inStr = true;
      quote = ch;
      continue;
    }
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return src.slice(braceStart, i + 1);
    }
  }
  throw new Error("unbalanced object for " + marker);
}

const packs = Function(`"use strict"; return (${extractObjectLiteral(i18nSrc, "window.DocsPageI18n")});`)();

// Merge extras with the same fill/override policy as the browser runtime.
const extraPath = path.join(root, "docs-i18n-extra.js");
if (fs.existsSync(extraPath)) {
  const extraSrc = fs.readFileSync(extraPath, "utf8");
  const em = extraSrc.match(/const EXTRA = (\{\s*[\s\S]*?\n\});/);
  const om = extraSrc.match(/const OVERRIDE_BY_LANG = (\{\s*[\s\S]*?\n\});/);
  const omLegacy = extraSrc.match(/const OVERRIDE_KEYS = (\[[\s\S]*?\]);/);
  if (em) {
    const EXTRA = Function(`"use strict"; return (${em[1]});`)();
    const byLang = om ? Function(`"use strict"; return (${om[1]});`)() : null;
    const legacy = omLegacy ? Function(`"use strict"; return (${omLegacy[1]});`)() : [];
    for (const lang of Object.keys(EXTRA)) {
      const next = Object.assign({}, packs[lang] || {});
      const overrideSet = new Set(byLang?.[lang] || legacy);
      for (const [key, val] of Object.entries(EXTRA[lang] || {})) {
        if (overrideSet.has(key) || !next[key]) next[key] = val;
      }
      packs[lang] = next;
    }
  }
}
const langs = Object.keys(packs);

const used = [...new Set([...htmlKeys, ...dtKeys])].sort();
const htmlUnique = [...new Set(htmlKeys)].sort();
const dtUnique = [...new Set(dtKeys)].sort();

const DocsContentI18n = Function(
  `"use strict"; return (${extractObjectLiteral(contentSrc, "window.DocsContentI18n")});`,
)();

const metaIds = [...app.matchAll(/\{\s*id:\s*"([^"]+)"/g)]
  .map((m) => m[1])
  .filter((id, i, arr) => arr.indexOf(id) === i);
// Prefer TEMPLATE_META_IDS block ids near the top
const metaBlock = app.match(/const TEMPLATE_META_IDS = \[([\s\S]*?)\];/);
const templateIds = metaBlock
  ? [...metaBlock[1].matchAll(/id:\s*"([^"]+)"/g)].map((m) => m[1])
  : metaIds.filter((id) =>
      ["letter", "visitor", "toolbox", "blank", "policy", "meeting"].some((x) => true),
    );

const requiredTplKeys = templateIds.flatMap((id) => {
  if (id === "blank") return ["tplBlank", "tplBlankBlurb"];
  const camel = id
    .split("_")
    .map((p, i) => (i === 0 ? p : p[0].toUpperCase() + p.slice(1)))
    .join("");
  const titleKey = "tpl" + camel[0].toUpperCase() + camel.slice(1);
  return [titleKey, titleKey + "Blurb"];
});

const missingBodies = { de: [], en: [], ar: [] };
for (const id of templateIds) {
  for (const lang of ["de", "en", "ar"]) {
    const htmlBody = DocsContentI18n[lang]?.[id];
    if (!htmlBody || String(htmlBody).trim().length < 8) missingBodies[lang].push(id);
  }
}

const missingTplTitles = {
  de: requiredTplKeys.filter((k) => !packs.de?.[k]),
  en: requiredTplKeys.filter((k) => !packs.en?.[k]),
  ar: requiredTplKeys.filter((k) => !packs.ar?.[k]),
};

const report = {
  generatedAt: new Date().toISOString(),
  counts: {
    htmlOccurrences: htmlKeys.length,
    htmlUnique: htmlUnique.length,
    dtOccurrences: dtKeys.length,
    dtUnique: dtUnique.length,
    usedUnique: used.length,
    templateIds: templateIds.length,
    packSizes: Object.fromEntries(langs.map((l) => [l, Object.keys(packs[l]).length])),
  },
  missingByLang: {},
  missingFromAllPacks: [],
  deOnlyKeys: [],
  missingBodies,
  missingTplTitles,
  warnings: [],
};

for (const lang of langs) {
  report.missingByLang[lang] = used.filter((k) => !(k in packs[lang]));
}

report.missingFromAllPacks = used.filter((k) => langs.every((l) => !(k in packs[l])));
const deKeys = new Set(Object.keys(packs.de || {}));
report.deOnlyKeys = [...deKeys].filter((k) =>
  langs.filter((l) => l !== "de").every((l) => !(k in packs[l])),
);

// Soft quality warnings for secondary locales
for (const lang of ["tr", "fr", "es", "it", "pl"]) {
  const letter = String(DocsContentI18n[lang]?.letter || "");
  if (/Sir or Madam/i.test(letter)) {
    report.warnings.push(`${lang}: letter still contains 'Sir or Madam'`);
  }
}

const outDir = path.join(root, "i18n-reports");
fs.mkdirSync(outDir, { recursive: true });
const outPath = path.join(outDir, "docs-i18n-report.json");
fs.writeFileSync(outPath, JSON.stringify(report, null, 2));

console.log(JSON.stringify(report.counts, null, 2));
console.log("missing de:", report.missingByLang.de?.length || 0);
console.log("missing ar:", report.missingByLang.ar?.length || 0);
console.log("missing bodies de/en/ar:", missingBodies.de.length, missingBodies.en.length, missingBodies.ar.length);
console.log("missing tpl titles de/en/ar:", missingTplTitles.de.length, missingTplTitles.en.length, missingTplTitles.ar.length);
console.log("warnings:", report.warnings.length);
console.log("wrote", outPath);

const fail =
  (report.missingByLang.de?.length || 0) > 0 ||
  (report.missingByLang.en?.length || 0) > 0 ||
  (report.missingByLang.ar?.length || 0) > 0 ||
  missingBodies.de.length + missingBodies.en.length + missingBodies.ar.length > 0 ||
  missingTplTitles.de.length + missingTplTitles.en.length + missingTplTitles.ar.length > 0;

if (fail) {
  console.error("AUDIT FAILED");
  if (missingBodies.de.length) console.error("missing bodies de", missingBodies.de);
  if (missingTplTitles.ar.length) console.error("missing tpl ar", missingTplTitles.ar);
  if (report.missingByLang.ar?.length) console.error("missing ui ar sample", report.missingByLang.ar.slice(0, 20));
  process.exit(1);
}
console.log("AUDIT OK");
