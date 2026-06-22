#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = {".css", ".html", ".js"}
SKIP = {"node_modules", ".venv", "build", "rebrand-", "update-brand"}

replacements = [
    ("#0f4c5c", "#06b6d4"),
    ("#e36414", "#a855f7"),
]

for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix not in EXT:
        continue
    if any(part in str(path) for part in SKIP):
        continue
    if path.parts[0] in {"docs", "vendor"} and path.suffix == ".md":
        continue
    text = path.read_text(encoding="utf-8")
    orig = text
    for old, new in replacements:
        text = text.replace(old, new)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print(path.relative_to(ROOT))
