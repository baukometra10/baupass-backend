import os
import sys
import uuid
import json
from datetime import datetime, timedelta

# Make project root importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Set a test DB path before importing the app
os.environ["BAUPASS_DB_PATH"] = os.path.join(os.path.dirname(__file__), "baupass-test.db")

from backend import server


def create_worker_and_session(db):
    cur = db.cursor()
    # Create a worker with all required NOT NULL fields
    worker_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    cur.execute(
        "INSERT INTO workers (id, company_id, first_name, last_name, insurance_number, worker_type, role, site, valid_until, status, photo_data, badge_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            worker_id,
            '1',
            'Test',
            'Worker',
            'INS-000',
            'worker',
            'arbeiter',
            'site-a',
            now,
            'active',
            '',
            'TEST123',
        ),
    )
    token = str(uuid.uuid4())
    expires = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    cur.execute(
        "INSERT INTO worker_app_sessions (worker_id, token, expires_at) VALUES (?, ?, ?)",
        (worker_id, token, expires),
    )
    db.commit()
    return worker_id, token


def run_test():
    # Initialize DB (creates schema)
    server.init_db()

    with server.app.app_context():
        db = server.get_db()
        # Ensure company id 1 exists in minimal form
        try:
            db.execute("INSERT INTO settings (id, platform_name, operator_name, turnstile_endpoint, rental_model) VALUES (1, 'Test', 'Operator', '/', 'r')")
            db.commit()
        except Exception:
            db.rollback()
        try:
            db.execute("INSERT INTO companies (id, name, contact, plan, status) VALUES (?, ?, ?, ?, ?)", ('1', 'TestCo', '', 'starter', 'active'))
            db.commit()
        except Exception:
            db.rollback()
            # If already exists, ensure plan is at least 'starter'
            try:
                db.execute("UPDATE companies SET plan = ? WHERE id = ?", ('starter', '1'))
                db.commit()
            except Exception as e:
                db.rollback()
                print("Ensure company plan failed:", e)
        # Debug: list companies
        try:
            rows = db.execute("SELECT id, name, plan, status FROM companies").fetchall()
            print("Companies in DB:")
            for r in rows:
                print(dict(r))
        except Exception as e:
            print("Listing companies failed:", e)

        worker_id, token = create_worker_and_session(db)

        client = server.app.test_client()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"events": [{"type": "offline_login", "occurredAt": datetime.utcnow().isoformat() + "Z", "distanceMeters": 12}]}
        resp = client.post("/api/worker-app/offline-events", headers=headers, data=json.dumps(payload))
        print("Status:", resp.status_code)
        try:
            print(resp.get_json())
        except Exception:
            print(resp.data)


if __name__ == "__main__":
    run_test()
