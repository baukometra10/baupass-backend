import { readFileSync } from "fs";

const src = readFileSync("app-i18n-extra-langs.js", "utf8");
const deRe = /[äöüßÄÖÜ]|(?:\bMitarbeiter\b|\bRechnung\b|\bDokumente\b|\bZutritt\b|\bBetrieb\b|\bAusweis\b|\bSchicht\b|\bVersand\b|\bBitte\b|\bFehlt\b|\bkopieren\b|\bProdukt\b|\bInstall-Link\b|\bweitere\b|\bGmbH\b)/i;

function parsePack(name) {
  const m = src.match(new RegExp(`${name}: \\{([\\s\\S]*?)\\n    \\},`));
  const out = [];
  for (const x of m[1].matchAll(/\n    ([a-zA-Z0-9_]+): "((?:\\.|[^"\\])*)"/g)) {
    let val;
    try {
      val = JSON.parse(`"${x[2]}"`);
    } catch {
      continue;
    }
    if (deRe.test(val)) out.push({ key: x[1], val });
  }
  return out;
}

for (const lang of ["tr", "fr", "es", "it", "pl"]) {
  const hits = parsePack(lang);
  console.log("\n" + lang, hits.length);
  hits.forEach((h) => console.log(" ", h.key, "=>", h.val.slice(0, 60)));
}
