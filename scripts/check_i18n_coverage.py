#!/usr/bin/env python3
"""Report uiT()/t() keys used in JS/HTML vs defined in i18n bundles (section 16)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_FILES = [
    ROOT / "app.js",
    ROOT / "admin-v2" / "app.js",
    ROOT / "worker-app.js",
    ROOT / "admin-v2" / "i18n-strings.js",
    ROOT / "admin-v2" / "i18n-strings-ext.js",
    ROOT / "worker-i18n.js",
]

KEY_PATTERNS = [
    re.compile(r"""uiT\(\s*["']([^"']+)["']"""),
    re.compile(r"""\bt\(\s*["']([^"']+)["']"""),
    re.compile(r"""data-i18n=["']([^"']+)["']"""),
]
DEF_PATTERN = re.compile(r"""^\s*["']([^"']+)["']\s*:""", re.M)


def extract_used(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    keys: set[str] = set()
    for pat in KEY_PATTERNS:
        keys.update(pat.findall(text))
    return keys


def extract_defined(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return set(DEF_PATTERN.findall(path.read_text(encoding="utf-8", errors="replace")))


def main() -> int:
    used: set[str] = set()
    for p in JS_FILES:
        used |= extract_used(p)

    defined = set()
    for name in ("i18n-strings.js", "i18n-strings-ext.js", "worker-i18n.js"):
        for base in (ROOT / "admin-v2", ROOT):
            p = base / name
            if p.is_file():
                defined |= extract_defined(p)

    missing = sorted(used - defined)
    print(f"Used keys: {len(used)}")
    print(f"Defined keys (bundles): {len(defined)}")
    print(f"Missing in bundles: {len(missing)}")
    if missing:
        for k in missing[:80]:
            print(f"  - {k}")
        if len(missing) > 80:
            print(f"  ... +{len(missing) - 80} more")
        export = ROOT / "scripts" / "missing_i18n_export.txt"
        export.write_text("\n".join(missing) + "\n", encoding="utf-8")
        print(f"Full list written to {export}")
        return 1
    print("OK: all scanned keys found in i18n bundles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
