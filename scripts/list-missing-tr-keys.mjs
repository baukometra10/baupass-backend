import { readFileSync } from "fs";

const src = readFileSync("app.js", "utf8");

function extractBlock(lang) {
  const anchor = src.indexOf("const UI_TRANSLATIONS");
  const marker = `\n  ${lang}: {`;
  const start = src.indexOf(marker, anchor);
  if (start < 0) return {};
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
  const out = {};
  const re = /\n\s+([a-zA-Z0-9_]+):\s*"((?:\\.|[^"\\])*)"/g;
  let m;
  while ((m = re.exec(block))) out[m[1]] = m[2];
  return out;
}

const de = extractBlock("de");
const en = extractBlock("en");
const tr = extractBlock("tr");
const missing = Object.keys(de).filter((k) => !tr[k]);
const enHas = missing.filter((k) => en[k]);
const onlyDe = missing.filter((k) => !en[k]);
console.log("tr missing", missing.length, "en has", enHas.length, "only de", onlyDe.length);
console.log("only de sample:", onlyDe.slice(0, 30).join(", "));
