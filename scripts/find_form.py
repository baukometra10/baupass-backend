import re

content = open('app.js', 'r', encoding='utf-8').read()

# Find where worker form fields are in HTML
idx = content.find('id="physicalCardId"')
print('physicalCardId input at:', idx)
if idx >= 0:
    print(repr(content[max(0,idx-200):idx+300]))
