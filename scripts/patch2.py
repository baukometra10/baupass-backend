content = open('app.js', 'r', encoding='utf-8').read()

old = (
    'function createLeaveRequestsPanel() {\n'
    '  const panel = document.createElement("div");\n'
    '  panel.id = "leaveRequestsTable";\n'
    '  document.body.appendChild(panel);\n'
    '  return panel;\n'
    '}'
)
new = (
    'function createLeaveRequestsPanel() {\n'
    '  renderAbsenceCalendarSection();\n'
    '  renderCurrentVisitorsSection();\n'
    '  const panel = document.createElement("div");\n'
    '  panel.id = "leaveRequestsTable";\n'
    '  document.body.appendChild(panel);\n'
    '  return panel;\n'
    '}'
)

if old in content:
    content = content.replace(old, new, 1)
    open('app.js', 'w', encoding='utf-8', newline='').write(content)
    print('replaced OK')
else:
    print('NOT FOUND')
    idx = content.find('createLeaveRequestsPanel')
    print(repr(content[idx:idx+300]))
