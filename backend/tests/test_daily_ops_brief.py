"""Daily ops brief + inbox camera escalations (Phase 1)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import sqlite3


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _create_company(client, headers, name: str) -> str:
    response = client.post(
        "/api/companies",
        json={
            "name": name,
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201)
    payload = response.get_json() or {}
    company = payload.get("company") or {}
    return str(company.get("id") or payload.get("id") or "")


def _open_db(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def test_daily_brief_requires_auth(client_and_db):
    client, _db_path = client_and_db
    r = client.get("/api/ops-os/daily-brief")
    assert r.status_code in (401, 403)


def test_daily_brief_attendance_and_security(client_and_db):
    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "DailyBriefCo")
    assert cid

    created = client.post(
        f"/api/workers?company_id={cid}",
        headers=headers,
        json={
            "companyId": cid,
            "firstName": "Anna",
            "lastName": "Muster",
            "insuranceNumber": "INS-BRIEF-1",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Nordtor",
            "validUntil": "2026-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": "1234",
            "complianceSignatureData": "data:image/png;base64,AAA",
            "physicalCardId": f"CARD-BRIEF-{cid[:8]}",
        },
    )
    assert created.status_code in (200, 201), created.get_json()
    body_w = created.get_json() or {}
    wid = str(body_w.get("id") or (body_w.get("worker") or {}).get("id") or "")
    assert wid

    today = date.today().isoformat()
    db = _open_db(db_path)
    try:
        db.execute(
            """
            INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp, checked_in_late)
            VALUES (?, ?, 'check-in', 'Tor A', '', ?, 1)
            """,
            ("al-brief-1", wid, f"{today}T08:45:00"),
        )
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/ops-os/daily-brief?company_id={cid}", headers=headers)
    assert r.status_code == 200
    body = r.get_json() or {}
    assert body.get("ok") is True
    assert body.get("autoDial") is False
    att = body.get("attendance") or {}
    assert int(att.get("lateToday") or 0) >= 1
    names = [str(w.get("name") or "") for w in (att.get("lateWorkers") or [])]
    assert any("Anna" in n for n in names)
    assert "missingExpected" in att
    assert "expectedToday" in att
    # Anna checked in → she must not appear as missing on a workday
    missing_ids = {str(w.get("workerId") or "") for w in (att.get("missingWorkers") or [])}
    assert wid not in missing_ids
    sec = body.get("security") or {}
    assert "openCameraEscalations" in sec
    assert sec.get("autoDial") is False


def test_daily_brief_missing_expected_worker(client_and_db):
    client, _db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "MissingBriefCo")
    created = client.post(
        f"/api/workers?company_id={cid}",
        headers=headers,
        json={
            "companyId": cid,
            "firstName": "Ben",
            "lastName": "Fehlt",
            "insuranceNumber": "INS-MISS-1",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Nordtor",
            "validUntil": "2026-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": "1234",
            "complianceSignatureData": "data:image/png;base64,AAA",
            "physicalCardId": f"CARD-MISS-{cid[:8]}",
        },
    )
    assert created.status_code in (200, 201), created.get_json()
    wid = str((created.get_json() or {}).get("id") or "")
    assert wid

    r = client.get(f"/api/ops-os/daily-brief?company_id={cid}", headers=headers)
    assert r.status_code == 200
    att = (r.get_json() or {}).get("attendance") or {}
    # On weekends expectedToday may be 0 — still assert fields exist
    assert "missingExpected" in att
    if date.today().weekday() < 5:
        assert int(att.get("expectedToday") or 0) >= 1
        assert int(att.get("missingExpected") or 0) >= 1
        names = [str(w.get("name") or "") for w in (att.get("missingWorkers") or [])]
        assert any("Ben" in n for n in names)


def test_overview_includes_daily_brief(client_and_db):
    client, _db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "OverviewBriefCo")
    r = client.get(f"/api/ops-os/overview?company_id={cid}&refresh=1", headers=headers)
    assert r.status_code == 200
    body = r.get_json() or {}
    assert "dailyBrief" in body
    assert body["layers"].get("13_daily_brief")


def test_inbox_includes_camera_escalation_items(client_and_db):
    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "InboxCamEscCo")
    eid = "esc-inbox-1"
    details = json.dumps({"cameraName": "Hof Nord"}, ensure_ascii=False)
    db = _open_db(db_path)
    try:
        db.execute(
            """
            INSERT INTO camera_escalations (
              id, company_id, event_id, camera_id, severity, status,
              police_name, police_address, police_phone, police_country, police_city,
              snapshot_b64, details_json, created_at
            ) VALUES (?, ?, 'ev-1', 'cam-1', 'critical', 'open',
                      '', '', '', '', '', '', ?, datetime('now'))
            """,
            (eid, cid, details),
        )
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/inbox?company_id={cid}&source=security", headers=headers)
    assert r.status_code == 200
    items = (r.get_json() or {}).get("items") or []
    cam_items = [it for it in items if str(it.get("id") or "").startswith("camesc:")]
    assert cam_items, "expected camera escalation inbox items"
    assert any("Kamera" in str(it.get("title") or "") for it in cam_items)
    assert any(
        any(a.get("type") == "resolve" for a in (it.get("actions") or [])) for it in cam_items
    )

    ack = client.post(
        f"/api/inbox/camesc:{eid}/resolve?company_id={cid}",
        headers=headers,
        json={},
    )
    assert ack.status_code == 200, ack.get_json()
    body = ack.get_json() or {}
    assert body.get("ok") is True
    assert body.get("autoDial") is False

    r2 = client.get(f"/api/inbox?company_id={cid}&source=security", headers=headers)
    items2 = (r2.get_json() or {}).get("items") or []
    still_open = [it for it in items2 if str(it.get("id") or "") == f"camesc:{eid}"]
    assert not still_open, "acked escalation should leave open inbox list"


def test_daily_brief_work_window_flexible(client_and_db):
    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "FlexHoursCo")
    r = client.get(f"/api/ops-os/daily-brief?company_id={cid}", headers=headers)
    assert r.status_code == 200
    win = ((r.get_json() or {}).get("attendance") or {}).get("workWindow") or {}
    assert win.get("flexible") is True or win.get("configured") is False

    db = _open_db(db_path)
    try:
        db.execute(
            "UPDATE companies SET work_start_time = ?, work_end_time = ? WHERE id = ?",
            ("07:15", "16:45", cid),
        )
        db.commit()
    finally:
        db.close()

    r2 = client.get(f"/api/ops-os/daily-brief?company_id={cid}", headers=headers)
    win2 = ((r2.get_json() or {}).get("attendance") or {}).get("workWindow") or {}
    assert win2.get("configured") is True
    assert win2.get("start") == "07:15"
    assert win2.get("end") == "16:45"
    assert win2.get("flexible") is False


def test_apply_company_hours_to_deployment(client_and_db):
    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "ApplyHoursCo")
    created = client.post(
        f"/api/workers?company_id={cid}",
        headers=headers,
        json={
            "companyId": cid,
            "firstName": "Dana",
            "lastName": "Plan",
            "insuranceNumber": "INS-APPLY-1",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Nordtor",
            "validUntil": "2026-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": "1234",
            "complianceSignatureData": "data:image/png;base64,AAA",
            "physicalCardId": f"CARD-APPLY-{cid[:8]}",
        },
    )
    assert created.status_code in (200, 201), created.get_json()
    wid = str((created.get_json() or {}).get("id") or "")
    today = date.today()
    db = _open_db(db_path)
    try:
        db.execute(
            "UPDATE companies SET work_start_time = ?, work_end_time = ? WHERE id = ?",
            ("06:30", "15:00", cid),
        )
        db.execute(
            """
            INSERT INTO worker_deployment_days
              (id, company_id, worker_id, work_date, location_label, shift_start, shift_end, notes, day_color, source, updated_at)
            VALUES (?, ?, ?, ?, 'Baustelle A', '', '', '', '', 'manual', datetime('now'))
            """,
            ("wdd-apply-1", cid, wid, today.isoformat()),
        )
        db.commit()
    finally:
        db.close()

    r = client.post(
        f"/api/workforce/deployment-plan/apply-company-hours?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "workerId": wid, "year": today.year, "month": today.month, "onlyEmpty": True},
    )
    assert r.status_code == 200, r.get_json()
    body = r.get_json() or {}
    assert body.get("ok") is True
    assert int(body.get("appliedDays") or body.get("saved") or 0) >= 1

    plan = client.get(
        f"/api/workforce/deployment-plan?company_id={cid}&worker_id={wid}&year={today.year}&month={today.month}",
        headers=headers,
    )
    assert plan.status_code == 200
    days = (plan.get_json() or {}).get("days") or (plan.get_json() or {}).get("calendar") or []
    hit = [d for d in days if str(d.get("date") or "") == today.isoformat()]
    assert hit, "expected deployment day in response"
    assert "06:30" in str(hit[0].get("shiftStart") or hit[0].get("shift_start") or "")


def test_inbox_missing_checkin_ack(client_and_db, monkeypatch):
    """Missing expected workers appear under attendance and resolve clears them."""
    monkeypatch.setattr(
        "backend.app.platform.inbox.service._missing_past_grace",
        lambda _w, _now: True,
    )
    client, _db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "MissInboxCo")
    created = client.post(
        f"/api/workers?company_id={cid}",
        headers=headers,
        json={
            "companyId": cid,
            "firstName": "Clara",
            "lastName": "Fehlt",
            "insuranceNumber": "INS-MISS-INBOX-1",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Nordtor",
            "validUntil": "2026-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": "1234",
            "complianceSignatureData": "data:image/png;base64,AAA",
            "physicalCardId": f"CARD-MISS-INB-{cid[:8]}",
        },
    )
    assert created.status_code in (200, 201), created.get_json()
    wid = str((created.get_json() or {}).get("id") or "")
    assert wid

    if date.today().weekday() >= 5:
        # Weekend: no expected workers in Mo–Fr fallback — still ensure API is stable.
        r = client.get(f"/api/inbox?company_id={cid}&source=attendance", headers=headers)
        assert r.status_code == 200
        return

    r = client.get(f"/api/inbox?company_id={cid}&source=attendance", headers=headers)
    assert r.status_code == 200
    items = (r.get_json() or {}).get("items") or []
    miss = [it for it in items if str(it.get("id") or "").startswith("miss:") and wid in str(it.get("id"))]
    assert miss, "expected missing-checkin inbox item"
    assert miss[0].get("source") == "attendance"
    mid = miss[0]["id"]

    ack = client.post(
        f"/api/inbox/{mid}/resolve?company_id={cid}",
        headers=headers,
        json={},
    )
    assert ack.status_code == 200, ack.get_json()
    assert (ack.get_json() or {}).get("ok") is True

    r2 = client.get(f"/api/inbox?company_id={cid}&source=attendance", headers=headers)
    items2 = (r2.get_json() or {}).get("items") or []
    still = [it for it in items2 if str(it.get("id") or "") == mid]
    assert not still, "acked missing check-in should leave attendance inbox"
