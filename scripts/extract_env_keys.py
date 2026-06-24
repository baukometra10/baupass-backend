#!/usr/bin/env python3
"""Extract all environment variable names referenced in the project."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    "node_modules", ".venv", ".venv311", "dist", "__pycache__", ".git",
    "mobile/build", "mobile/.dart_tool", "test-results",
}
EXTS = {".py", ".js", ".ts", ".sh", ".ps1", ".yml", ".yaml", ".toml", ".json", ".md", ".example"}

PATTERNS = [
    re.compile(r"os\.getenv\(['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"os\.environ\.get\(['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"os\.environ\[['\"]([A-Z][A-Z0-9_]*)['\"]\]"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"process\.env\[['\"]([A-Z][A-Z0-9_]*)['\"]\]"),
    re.compile(r"getenv\(['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"^([A-Z][A-Z0-9_]*)=", re.M),
]

found: dict[str, set[str]] = {}

for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    if any(part in SKIP_DIRS for part in path.parts):
        continue
    name = path.name
    if path.suffix.lower() not in EXTS and not name.startswith(".env"):
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    for pat in PATTERNS:
        for match in pat.finditer(text):
            key = match.group(1)
            if len(key) >= 3:
                found.setdefault(key, set()).add(rel)

for key in sorted(found, key=str.lower):
    print(key)

print(f"\n# TOTAL: {len(found)}", flush=True)
