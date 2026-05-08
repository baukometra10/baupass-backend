#!/usr/bin/env python3
"""Check email_inbox table"""

import sqlite3

db = sqlite3.connect('baupass.db')
db.row_factory = sqlite3.Row
cursor = db.cursor()

# Check email_inbox table
cursor.execute('SELECT id, message_id, from_addr, subject, received_at FROM email_inbox ORDER BY received_at DESC LIMIT 15')
rows = cursor.fetchall()

print('=== Last 15 emails in email_inbox ===')
for row in rows:
    msg_id = row["message_id"][:30] if row["message_id"] else "(none)"
    subject = row["subject"][:50] if row["subject"] else "(no subject)"
    print(f'From: {row["from_addr"]:30} | Subject: {subject:50} | Received: {row["received_at"]}')
    print(f'       Message-ID: {msg_id}...')
    print()

total = cursor.execute("SELECT COUNT(*) FROM email_inbox").fetchone()[0]
print(f'Total emails in inbox: {total}')

db.close()
