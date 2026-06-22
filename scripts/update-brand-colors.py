#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "backend" / "server.py"
text = path.read_text(encoding="utf-8")
replacements = [
    ('"#0f4c5c"', "DEFAULT_BRAND_PRIMARY"),
    ("'#0f4c5c'", "'#06b6d4'"),
    ('"#e36414"', "DEFAULT_BRAND_ACCENT"),
    ("'#e36414'", "'#a855f7'"),
    ("#0f4c5c", "#06b6d4"),
    ("#e36414", "#a855f7"),
]
for old, new in replacements:
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
print("updated", path)
