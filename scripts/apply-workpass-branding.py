#!/usr/bin/env python3
"""Apply WorkPass (platform) + Suppix AI (company) customer-facing branding."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"node_modules", ".venv", ".venv311", ".git", "dist", "__pycache__", "mobile/build", ".venv-ci"}

# Order matters: longer / specific patterns first.
REPLACEMENTS: list[tuple[str, str]] = [
    ("SUPPIX AI", "Suppix AI"),
    ("Enterprise SUPPIX", "Enterprise WorkPass"),
    ("SUPPIX Plattform", "WorkPass Plattform"),
    ('appTitle: "SUPPIX"', 'appTitle: "WorkPass"'),
    ('platformName: "SUPPIX"', 'platformName: "WorkPass"'),
    ('de: "SUPPIX"', 'de: "WorkPass"'),
    ('en: "SUPPIX"', 'en: "WorkPass"'),
    ('tr: "SUPPIX"', 'tr: "WorkPass"'),
    ('ar: "SUPPIX"', 'ar: "WorkPass"'),
    ('fr: "SUPPIX"', 'fr: "WorkPass"'),
    ('es: "SUPPIX"', 'es: "WorkPass"'),
    ('it: "SUPPIX"', 'it: "WorkPass"'),
    ('pl: "SUPPIX"', 'pl: "WorkPass"'),
    ('.value = "SUPPIX"', '.value = "WorkPass"'),
    ('placeholder="SUPPIX"', 'placeholder="WorkPass"'),
    ('|| "SUPPIX"', '|| "WorkPass"'),
    ('DEFAULT "SUPPIX"', 'DEFAULT \'WorkPass\''),
    ("DEFAULT 'SUPPIX'", "DEFAULT 'WorkPass'"),
    ('DEFAULT_PLATFORM_NAME = "SUPPIX"', 'DEFAULT_PLATFORM_NAME = "WorkPass"'),
    ('DEFAULT_OPERATOR_NAME = "Suppix Technologie UG"', 'DEFAULT_OPERATOR_NAME = "Suppix AI"'),
    ('OPERATOR_DISPLAY_NAME", "Suppix Technologie UG"', 'OPERATOR_DISPLAY_NAME", "Suppix AI"'),
    ('PLATFORM_DISPLAY_NAME", "WorkPass"', 'PLATFORM_DISPLAY_NAME", "WorkPass"'),
    ('PLATFORM_DISPLAY_NAME", "SUPPIX"', 'PLATFORM_DISPLAY_NAME", "WorkPass"'),
]

AUTH_PATTERNS = [
    (r"SUPPIX'a", "WorkPass'a"),
    (r" zu SUPPIX", " zu WorkPass"),
    (r" to SUPPIX", " to WorkPass"),
    (r" à SUPPIX", " à WorkPass"),
    (r" en SUPPIX", " en WorkPass"),
    (r" a SUPPIX", " a WorkPass"),
    (r" do SUPPIX", " do WorkPass"),
    (r" إلى SUPPIX", " إلى WorkPass"),
    (r"reload SUPPIX", "reload WorkPass"),
    (r"SUPPIX mit", "WorkPass mit"),
    (r"SUPPIX login", "WorkPass login"),
    (r"SUPPIX ist", "WorkPass ist"),
    (r"SUPPIX is", "WorkPass is"),
    (r"SUPPIX bu", "WorkPass bu"),
    (r"SUPPIX مثبت", "WorkPass مثبت"),
    (r"SUPPIX est", "WorkPass est"),
    (r"SUPPIX ya", "WorkPass ya"),
    (r"SUPPIX e gia", "WorkPass e gia"),
    (r"SUPPIX jest", "WorkPass jest"),
    (r"in SUPPIX", "in WorkPass"),
    (r"used in SUPPIX", "used in WorkPass"),
    (r"genutzte Sprachen", "genutzte Sprachen"),  # noop anchor
    (r"languages used in WorkPass", "languages used in WorkPass"),
    (r"Anmeldung über SUPPIX", "Anmeldung über WorkPass"),
    (r"im SUPPIX", "in WorkPass"),
    (r"SUPPIX →", "WorkPass →"),
    (r"SUPPIX ·", "WorkPass ·"),
    (r"SUPPIX Admin", "WorkPass Admin"),
    (r"SUPPIX Betrieb", "WorkPass Betrieb"),
    (r"SUPPIX Mitarbeiter", "WorkPass Mitarbeiter"),
    (r"SUPPIX Mobile", "WorkPass Mobile"),
    (r"SUPPIX –", "WorkPass –"),
    (r"SUPPIX Portal", "WorkPass Portal"),
    (r"SUPPIX Telefon", "WorkPass Telefon"),
    (r"SUPPIX Worker", "WorkPass Worker"),
    (r"SUPPIX: ", "WorkPass: "),
    (r"SUPPIX/1.0", "WorkPass/1.0"),
    (r"content=\"SUPPIX\"", 'content="WorkPass"'),
    (r"content='SUPPIX'", "content='WorkPass'"),
    (r">SUPPIX<", ">WorkPass<"),
    (r'"name": "SUPPIX"', '"name": "WorkPass"'),
    (r'"short_name": "SUPPIX"', '"short_name": "WorkPass"'),
    (r"SMTP_SENDER_NAME=SUPPIX", "SMTP_SENDER_NAME=WorkPass"),
    (r'BauPass Control', "WorkPass"),
    (r"BauPass", "WorkPass"),
    (r"Control Pass", "WorkPass"),
    (r"baupass-control@outlook.de", "suppix-workpass-ai@outlook.de"),
]

EXTS = {".html", ".js", ".json", ".py", ".md", ".example", ".yaml", ".yml"}


def should_skip(path: Path) -> bool:
    return any(part in SKIP for part in path.parts)


def transform(text: str) -> str:
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    for pattern, repl in AUTH_PATTERNS:
        text = re.sub(pattern, repl, text)
    # Restore company AI product name if generic replace hit it
    text = text.replace('"WorkPass AI"', '"Suppix AI"')
    text = text.replace("WorkPass AI —", "Suppix AI —")
    text = text.replace("WorkPass AI –", "Suppix AI –")
    text = text.replace("navBaupassAi: \"WorkPass AI\"", 'navBaupassAi: "Suppix AI"')
    text = text.replace('navBaupassAi: "WorkPass AI"', 'navBaupassAi: "Suppix AI"')
    return text


def main() -> None:
    changed = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        if path.suffix.lower() not in EXTS and path.name not in {"control-manifest.json", "worker-manifest.json"}:
            continue
        if "apply-workpass-branding" in path.name:
            continue
        original = path.read_text(encoding="utf-8", errors="ignore")
        updated = transform(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(path.relative_to(ROOT))
    print(f"\nUpdated {changed} files.")


if __name__ == "__main__":
    main()
