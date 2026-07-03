import { readFileSync } from "fs";
import { createContext, runInContext } from "vm";

const src =
  readFileSync("worker-i18n.js", "utf8") +
  readFileSync("worker-i18n-extra-langs.js", "utf8") +
  readFileSync("worker-i18n-ar-overrides.js", "utf8");
const sandbox = {
  window: {},
  localStorage: { getItem: () => null, setItem: () => {} },
  WorkPassStorage: { KEYS: { WORKER_LANG: "x" } },
};
sandbox.window = sandbox;
const ctx = createContext(sandbox);
runInContext(src, ctx);
const T = sandbox.window.WorkerI18N?.TRANSLATIONS;
if (!T) {
  console.error("TRANSLATIONS not found");
  process.exit(1);
}
const langs = ["de", "en", "ar", "tr", "fr", "es", "it", "pl"];
const deKeys = Object.keys(T.de).sort();
console.log("Counts:", langs.map((l) => `${l}=${Object.keys(T[l] || {}).length}`).join(" "));
for (const l of langs) {
  if (l === "de") continue;
  const missing = deKeys.filter((k) => T[l][k] === undefined);
  if (missing.length) console.log(`${l} missing ${missing.length}:`, missing.join(", "));
}
