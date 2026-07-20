"""Worker hours report: formal check-in/out only + month spillover."""

from __future__ import annotations

from backend.app.domains.companies.service import CompaniesService


def test_worker_hours_summary_formal_only_and_spillover(client_and_db):
    _client, _db_path = client_and_db
    from backend import server

    with server.app.app_context():
        db = server.get_db()
        company = db.execute(
            "SELECT id FROM companies WHERE deleted_at IS NULL LIMIT 1"
        ).fetchone()
        assert company is not None
        company_id = company["id"]
        db.execute(
            "UPDATE companies SET plan = 'professional' WHERE id = ?",
            (company_id,),
        )
        worker_id = "wrk-hours-formal-test"
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, status, photo_data, badge_id
            ) VALUES (?, ?, 'Hours', 'Worker', 'INS-HRS', 'worker', 'mitarbeiter', 'Site',
                      '2099-01-01T00:00:00Z', 'aktiv', '', 'BT-HRS')
            """,
            (worker_id, company_id),
        )
        # Formal 8h day in June + GPS presence that must NOT add hours
        seeds = [
            ("log-h1", "check-in", "2026-06-15T07:00:00"),
            ("log-h2", "check-out", "2026-06-15T15:00:00"),
            ("log-h3", "app-login", "2026-06-15T16:00:00"),
            ("log-h4", "app-logout", "2026-06-15T18:00:00"),
            # Overnight spillover from June 30 into July 1 (7h)
            ("log-h5", "check-in", "2026-06-30T23:00:00"),
            ("log-h6", "check-out", "2026-07-01T06:00:00"),
        ]
        for log_id, direction, ts in seeds:
            db.execute(
                """
                INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp, checked_in_late)
                VALUES (?, ?, ?, 'Gate', '', ?, 0)
                """,
                (log_id, worker_id, direction, ts),
            )
        db.commit()

        user = {"role": "company-admin", "company_id": company_id}
        svc = CompaniesService()
        june = svc.worker_hours_summary(db, user, company_id, month_param="2026-06")
        assert "body" in june
        workers = {w["workerId"]: w for w in june["body"]["workers"]}
        assert worker_id in workers
        # 8h formal + 7h spillover attributed to June 30 = 15.0h; app-login ignored
        assert workers[worker_id]["totalHours"] == 15.0
        assert workers[worker_id]["daysWorked"] == 2

        july = svc.worker_hours_summary(db, user, company_id, month_param="2026-07")
        july_workers = {w["workerId"]: w for w in july["body"]["workers"]}
        # Spillover already attributed to June check-in day — July must not double-count
        july_hours = july_workers.get(worker_id, {}).get("totalHours", 0)
        assert july_hours == 0
