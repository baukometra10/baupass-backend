import { readFileSync, writeFileSync } from "fs";

const draft = JSON.parse(readFileSync("scripts/i18n-extra-draft.json", "utf8"));
const keys = draft.missingByLang.tr;
const enPack = draft.extra.tr; // currently EN fallback values

const rows = keys.map((k) => ({ key: k, en: enPack[k] || "" }));
writeFileSync("scripts/missing-keys-en.json", JSON.stringify(rows, null, 2));
console.log("exported", rows.length, "keys");
