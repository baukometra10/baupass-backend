import re

with open("app.js", "r", encoding="utf-8") as f:
    content = f.read()

old = "    const container = document.getElementById('adminPanel') || document.body;\n    container.innerHTML += html;"
new = "    const container = document.getElementById('adminPanel') || document.body;\n    container.innerHTML += html;\n    renderAbsenceCalendarSection();\n    renderCurrentVisitorsSection();"

if old not in content:
    print("NOT FOUND")
    print(repr(content[963212+1400:963212+1800]))
else:
    content2 = content.replace(old, new, 1)
    with open("app.js", "w", encoding="utf-8") as f:
        f.write(content2)
    print("patched OK")
