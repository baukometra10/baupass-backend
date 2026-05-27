import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone

# Pfad zur Datenbank
import os
DB_PATH = os.path.join(os.path.dirname(__file__), 'baupass.db')

# Superadmin-Daten
admin_id = 'usr-superadmin'
admin_username = 'admin'
admin_password = 'admin123'
admin_name = 'Super Admin'
admin_role = 'superadmin'

# Beispiel-Firma
company_id = 'cmp-demo'
company_name = 'Demo GmbH'
company_contact = 'info@demo.de'
company_billing_email = 'rechnung@demo.de'
company_access_host = ''
company_plan = 'enterprise'
company_status = 'aktiv'

# Zeitstempel
now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + 'Z'

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Superadmin anlegen
c.execute("""
INSERT OR IGNORE INTO users (id, username, password_hash, name, role, company_id, twofa_enabled)
VALUES (?, ?, ?, ?, ?, ?, 0)
""", (
    admin_id,
    admin_username,
    generate_password_hash(admin_password),
    admin_name,
    admin_role,
    company_id
))

# Firma anlegen
c.execute("""
INSERT OR IGNORE INTO companies (id, name, contact, billing_email, access_host, plan, status, deleted_at)
VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
""", (
    company_id,
    company_name,
    company_contact,
    company_billing_email,
    company_access_host,
    company_plan,
    company_status
))

conn.commit()
conn.close()

print('Superadmin und Demo-Firma wurden angelegt.')
