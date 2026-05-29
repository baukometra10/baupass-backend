import { STRINGS } from "./i18n.js";

const langs = Object.keys(STRINGS);
const base = new Set(Object.keys(STRINGS.de));
let ok = true;
for (const lang of langs) {
  const keys = new Set(Object.keys(STRINGS[lang]));
  for (const k of base) {
    if (!keys.has(k)) {
      console.error(`[${lang}] missing key: ${k}`);
      ok = false;
    }
  }
  for (const k of keys) {
    if (!base.has(k)) {
      console.error(`[${lang}] extra key: ${k}`);
      ok = false;
    }
  }
}
console.log(ok ? `i18n OK — ${base.size} keys × ${langs.length} languages` : "i18n key mismatch");
process.exit(ok ? 0 : 1);
