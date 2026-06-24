import { readFileSync } from "fs";

const src = readFileSync("app.js", "utf8");
const langs = ["de", "en", "ar", "tr", "fr", "es", "it", "pl"];

function extractBlock(lang, from = "const UI_TRANSLATIONS") {
  const anchor = src.indexOf(from);
  const marker = `\n  ${lang}: {`;
  const start = src.indexOf(marker, anchor);
  if (start < 0) return new Set();
  let depth = 0;
  let i = src.indexOf("{", start);
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) break;
    }
  }
  const block = src.slice(start, i + 1);
  const keys = new Set();
  for (const m of block.matchAll(/\n\s+([a-zA-Z0-9_]+):\s/g)) keys.add(m[1]);
  return keys;
}

const packs = Object.fromEntries(langs.map((l) => [l, extractBlock(l)]));
const deKeys = [...packs.de].sort();
console.log("UI_TRANSLATIONS:", langs.map((l) => `${l}=${packs[l].size}`).join(" "));

for (const l of ["en", "ar", "tr", "fr", "es", "it", "pl"]) {
  const missing = deKeys.filter((k) => !packs[l].has(k));
  console.log(`${l} missing ${missing.length}`);
}

// runtime map
const rtPacks = Object.fromEntries(langs.map((l) => [l, extractBlock(l, "const map = {")]));
const rtDe = [...rtPacks.de].sort();
console.log("\nRuntime map:", langs.map((l) => `${l}=${rtPacks[l].size}`).join(" "));
for (const l of langs) {
  if (l === "de") continue;
  const missing = rtDe.filter((k) => !rtPacks[l].has(k));
  if (missing.length) console.log(`runtime ${l} missing ${missing.length}`);
}
