content = open('app.js', 'r', encoding='utf-8').read()

old = "<tr><th>Worker</th><th>Type</th><th>Start</th><th>End</th><th>Status</th><th>Action</th></tr>\n          ${filtered.map(req => `\n            <tr>\n              <td>${req.worker_name || 'N/A'}</td>\n              <td>${req.type || 'N/A'}</td>\n              <td>${req.start_date}</td>\n              <td>${req.end_date}</td>"
new = "<tr><th>Mitarbeiter</th><th>Art</th><th>Von</th><th>Bis</th><th>Tage</th><th>Status</th><th>Aktion</th></tr>\n          ${filtered.map(req => `\n            <tr>\n              <td>${req.worker_name || req.first_name + ' ' + req.last_name || 'N/A'}</td>\n              <td>${req.type === 'urlaub' ? 'Urlaub' : req.type === 'krank' ? 'Krank' : req.type || 'N/A'}</td>\n              <td>${req.start_date}</td>\n              <td>${req.end_date}</td>\n              <td>${req.days_count > 0 ? req.days_count : '-'}</td>"

if old not in content:
    print("NOT FOUND - checking with escaped quotes")
    # Try with escaped single quotes
    import re
    m = re.search(r'<tr><th>Worker</th>', content)
    if m:
        print("found Worker header at:", m.start())
        print(repr(content[m.start():m.start()+300]))
    else:
        print("Header not found at all")
else:
    content2 = content.replace(old, new, 1)
    open('app.js', 'w', encoding='utf-8').write(content2)
    print('patched OK')
