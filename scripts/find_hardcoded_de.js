const fs = require("fs");
const path = require("path");
const lines = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8").split("\n");

const germanWords = [
  "Eintritt","Austritt","Gesamt","Schärfe","Ausgabeoptionen","Mahnungsdurchlauf",
  "Monatsautomatik","Zahlungsfrist","Sendername","Steuernummer","Netto-",
  "Einleitungstext","Platzhalter","aktualisieren","Ablauf","keine Geräte",
  "Top Standort","Top Tore","Bitte Person","App-Link","physische Karte",
  "Scharf","letzte 30","letzte Woche","Sperren","Bearbeiten","Einlass","Auslass",
  "Tageskarte","Drehkreuz hinzufügen","Firmen-Login","Inkasso","Mahnung",
  "Zurücksetzen","Rabattkonto","Netto-Summe","Postleitzahl","Hausnummer",
  "Straße","Platz Postleitzahl"
];

// Lines that ARE translation definitions - skip them
const skipFn = (line) => {
  const t = line.trim();
  if (t.startsWith("//")) return true;
  // Inside translation map (indented key: "value" pattern)
  if (/^\s+(de|en|tr|ar|fr|es|it|pl):\s*\{/.test(line)) return true;
  if (/^\s+[a-zA-Z_]+:\s*["']/.test(line) && line.includes(": \"")) return true;
  if (/^\s+[a-zA-Z_]+:\s*["']/.test(line) && line.includes(": '")) return true;
  if (t.startsWith("runtimeText(")) return true;
  if (t.startsWith("uiT(")) return true;
  return false;
};

const results = [];
lines.forEach((line, i) => {
  if (skipFn(line)) return;
  germanWords.forEach((w) => {
    if (line.includes(w)) {
      results.push({ line: i + 1, text: line.trim().slice(0, 130) });
    }
  });
});

// deduplicate by line number
const seen = new Set();
results.forEach((r) => {
  if (!seen.has(r.line)) {
    seen.add(r.line);
    console.log(r.line + ": " + r.text);
  }
});
console.log("\nTotal:", seen.size);
