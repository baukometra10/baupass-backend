from pathlib import Path

root = Path(__file__).resolve().parents[1]
skip = {"node_modules", ".venv", ".git", "__pycache__", ".venv-ci"}
subs = [
    (' or "WorkPass"', ' or "WorkPass"'),
    ('= "WorkPass"', '= "WorkPass"'),
    ('sender_name = "WorkPass"', 'sender_name = "WorkPass"'),
    ('from_name: str = "WorkPass"', 'from_name: str = "WorkPass"'),
    ('vendor: str = "WorkPass"', 'vendor: str = "WorkPass"'),
    ('Suppix AI', 'Suppix AI'),
    ('"appTitle": "WorkPass"', '"appTitle": "WorkPass"'),
]

for path in list(root.rglob("*.py")) + [root / "i18n-packs.js"]:
    if any(p in path.parts for p in skip):
        continue
    if "apply-workpass-branding" in path.name:
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    orig = text
    for a, b in subs:
        text = text.replace(a, b)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print(path.relative_to(root))
