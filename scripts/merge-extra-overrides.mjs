/** Merge manual overrides from ui-extra-translations into app-i18n-extra-langs.js */
import { readFileSync, writeFileSync } from "fs";
import { EXTRA_UI_STRINGS } from "./ui-extra-translations.mjs";

const path = "app-i18n-extra-langs.js";
let src = readFileSync(path, "utf8");

for (const [lang, strings] of Object.entries(EXTRA_UI_STRINGS)) {
  for (const [key, value] of Object.entries(strings)) {
    const esc = value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    const re = new RegExp(`(\\n    ${key}: )"[^"]*"`, "g");
    const langBlockStart = src.indexOf(`    ${lang}: {`);
    if (langBlockStart < 0) continue;
    const nextLang = src.indexOf("\n    },", langBlockStart + 10);
    const block = src.slice(langBlockStart, nextLang);
    if (block.includes(`\n    ${key}:`)) {
      src = src.slice(0, langBlockStart) + block.replace(re, `$1"${esc}"`) + src.slice(nextLang);
    } else {
      const insert = `\n    ${key}: "${esc}",`;
      src = src.slice(0, nextLang) + insert + src.slice(nextLang);
    }
  }
}

writeFileSync(path, src);
console.log("Merged manual overrides into", path);
