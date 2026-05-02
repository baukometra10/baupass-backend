import re

content = open('app.js', 'r', encoding='utf-8').read()

# Patch 1: Add contactEmail and leaveBalance prefill after physicalCardId for 2-space-indent locations
old1 = 'querySelector("#physicalCardId").value = worker.physicalCardId || "";\n      document.querySelector("#validUntil").value'
new1 = 'querySelector("#physicalCardId").value = worker.physicalCardId || "";\n      document.querySelector("#workerContactEmail") && (document.querySelector("#workerContactEmail").value = worker.contactEmail || worker.contact_email || "");\n      document.querySelector("#workerLeaveBalance") && (document.querySelector("#workerLeaveBalance").value = (worker.leaveBalance !== undefined ? worker.leaveBalance : (worker.leave_balance !== undefined ? worker.leave_balance : 30)));\n      document.querySelector("#validUntil").value'

# Patch 2: Same for 4-space-indent location
old2 = 'querySelector("#physicalCardId").value = worker.physicalCardId || "";\n        document.querySelector("#validUntil").value'
new2 = 'querySelector("#physicalCardId").value = worker.physicalCardId || "";\n        document.querySelector("#workerContactEmail") && (document.querySelector("#workerContactEmail").value = worker.contactEmail || worker.contact_email || "");\n        document.querySelector("#workerLeaveBalance") && (document.querySelector("#workerLeaveBalance").value = (worker.leaveBalance !== undefined ? worker.leaveBalance : (worker.leave_balance !== undefined ? worker.leave_balance : 30)));\n        document.querySelector("#validUntil").value'

# Patch 3: Add contactEmail and leaveBalance to payload
old3 = '    physicalCardId: document.querySelector("#physicalCardId").value.trim(),\n    validUntil: document.querySelector("#validUntil").value,'
new3 = '    physicalCardId: document.querySelector("#physicalCardId").value.trim(),\n    contactEmail: document.querySelector("#workerContactEmail")?.value.trim() || "",\n    leaveBalance: parseInt(document.querySelector("#workerLeaveBalance")?.value || "30", 10),\n    validUntil: document.querySelector("#validUntil").value,'

count1 = content.count(old1)
count2 = content.count(old2)
count3 = content.count(old3)
print(f'old1 occurrences: {count1}, old2 occurrences: {count2}, old3 occurrences: {count3}')

if count1 >= 2 and count2 >= 1 and count3 >= 1:
    content = content.replace(old1, new1)
    content = content.replace(old2, new2)
    content = content.replace(old3, new3)
    open('app.js', 'w', encoding='utf-8').write(content)
    print('patched OK')
else:
    print('MISMATCH - not patching')
