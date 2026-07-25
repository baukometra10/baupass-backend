"""Per-company briefing hours for morning/shift pulse."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.platform.ai.operator_settings import (
    auto_briefing_hours_for_company,
    merge_settings,
    normalize_briefing_hours,
    resolve_briefing_email,
    resolve_briefing_lang,
    save_settings,
    get_settings,
)
from backend.app.platform.ai.scheduler import company_due_hours


class _FakeDb:
    def __init__(
        self,
        *,
        work_start="08:00",
        shifts=None,
        report_tz="Europe/Berlin",
        admin_emails=None,
        billing_email="",
        invoice_email_lang="ar",
    ):
        self.rows = {}
        self.sends = set()
        self.work_start = work_start
        self.shifts = list(shifts or [])
        self.report_tz = report_tz
        self.admin_emails = list(admin_emails or [])
        self.billing_email = billing_email
        self.invoice_email_lang = invoice_email_lang

    def execute(self, sql, params=None):
        sql_l = " ".join(str(sql).lower().split())
        if sql_l.startswith("create table"):
            return self
        if "select" in sql_l and "company_ai_operator_settings" in sql_l:
            cid = params[0]
            raw = self.rows.get(cid)

            class Row(dict):
                def __getitem__(self, key):
                    return dict.get(self, key)

            if not raw:
                return _Result(None)
            return _Result(Row({"settings_json": raw, "updated_at": "t"}))
        if "insert" in sql_l and "company_ai_operator_settings" in sql_l:
            cid, payload, *_rest = params
            self.rows[cid] = payload
            return self
        if "company_ai_briefing_sends" in sql_l and "select" in sql_l:
            key = (params[0], params[1], int(params[2]))
            return _Result({"ok": 1} if key in self.sends else None)
        if "insert" in sql_l and "company_ai_briefing_sends" in sql_l:
            self.sends.add((params[0], params[1], int(params[2])))
            return self
        if "work_start_time" in sql_l and "from companies" in sql_l:
            return _Result({"work_start_time": self.work_start})
        if "report_timezone" in sql_l and "from companies" in sql_l:
            return _Result({"report_timezone": self.report_tz})
        if "from shift_assignments" in sql_l:
            return _ResultRows([{"start_time": s} for s in self.shifts])
        if "from users" in sql_l and "company-admin" in sql_l:
            return _ResultRows([{"email": e} for e in self.admin_emails])
        if "billing_email" in sql_l and "from companies" in sql_l:
            return _Result(
                {
                    "billing_email": self.billing_email,
                    "document_email": "",
                    "contract_owner_email": "",
                    "contact": "",
                }
            )
        if "invoice_email_lang" in sql_l and "from companies" in sql_l:
            return _Result({"invoice_email_lang": self.invoice_email_lang})
        return self

    def commit(self):
        return None


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row else []


class _ResultRows:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def test_normalize_briefing_hours_csv_and_list():
    assert normalize_briefing_hours("6,14,22") == [6, 14, 22]
    assert normalize_briefing_hours([6, "14:00", 22]) == [6, 14, 22]
    assert normalize_briefing_hours("7") == [7]
    assert normalize_briefing_hours("auto", allow_empty=True) == []
    assert normalize_briefing_hours("", allow_empty=True) == []


def test_save_auto_is_default_and_manual_override():
    db = _FakeDb(work_start="08:00")
    s = get_settings(db, "cmp-1")
    assert s["briefingHoursMode"] == "auto"

    manual = save_settings(
        db,
        "cmp-1",
        {"briefingEnabled": True, "briefingHours": "6,14,22", "briefingTz": "Europe/Berlin"},
        actor="admin",
    )
    assert manual["briefingHoursMode"] == "manual"
    assert manual["briefingHours"] == [6, 14, 22]

    back = save_settings(db, "cmp-1", {"briefingHours": "auto"}, actor="admin")
    assert back["briefingHoursMode"] == "auto"
    assert back["briefingHours"] == []
    assert 7 in back["briefingHoursResolved"]  # 08:00 → briefing at 07


def test_auto_hours_from_work_start_and_shifts():
    db = _FakeDb(
        work_start="08:00",
        shifts=["2026-07-25T14:00:00Z", "2026-07-26T22:30:00Z"],
    )
    hours = auto_briefing_hours_for_company(db, "cmp-1")
    assert hours == [7, 13, 21]


def test_company_due_hours_manual_matches_local_shift():
    settings = {
        "briefingEnabled": True,
        "briefingHoursMode": "manual",
        "briefingHours": [6, 14, 22],
        "briefingTz": "Europe/Berlin",
    }
    now = datetime(2026, 7, 25, 12, 10, tzinfo=ZoneInfo("UTC"))  # 14:10 CEST
    due = company_due_hours(settings, now_utc=now)
    assert due
    assert due[0][0] == 14
    assert due[0][1] == "2026-07-25"


def test_company_due_hours_auto_uses_work_start():
    db = _FakeDb(work_start="08:00", report_tz="Europe/Berlin")
    settings = {
        "briefingEnabled": True,
        "briefingHoursMode": "auto",
        "briefingHours": [],
        "briefingTz": "",
    }
    # 07:10 Berlin = 05:10 UTC in summer
    now = datetime(2026, 7, 25, 5, 10, tzinfo=ZoneInfo("UTC"))
    due = company_due_hours(settings, now_utc=now, db=db, company_id="cmp-1")
    assert due
    assert due[0][0] == 7


def test_company_due_hours_skips_wrong_hour():
    settings = {
        "briefingEnabled": True,
        "briefingHoursMode": "manual",
        "briefingHours": [6, 22],
        "briefingTz": "Europe/Berlin",
    }
    now = datetime(2026, 7, 25, 12, 10, tzinfo=ZoneInfo("UTC"))  # 14:10 Berlin
    assert company_due_hours(settings, now_utc=now) == []


def test_merge_legacy_briefing_hour():
    raw = '{"enabled": true, "briefingHour": 5}'
    merged = merge_settings(raw)
    assert merged["briefingHours"] == [5]
    assert merged["briefingHoursMode"] == "manual"


def test_resolve_briefing_email_from_company_admins():
    db = _FakeDb(admin_emails=["a@firma.de", "b@firma.de"], billing_email="billing@firma.de")
    to = resolve_briefing_email({"briefingEmail": ""}, db=db, company_id="cmp-1")
    assert to == "a@firma.de, b@firma.de"


def test_resolve_briefing_email_falls_back_to_billing():
    db = _FakeDb(admin_emails=[], billing_email="billing@firma.de")
    to = resolve_briefing_email({"briefingEmail": "auto"}, db=db, company_id="cmp-1")
    assert to == "billing@firma.de"


def test_resolve_briefing_email_manual_override():
    db = _FakeDb(admin_emails=["a@firma.de"])
    to = resolve_briefing_email({"briefingEmail": "ops@firma.de"}, db=db, company_id="cmp-1")
    assert to == "ops@firma.de"


def test_resolve_briefing_lang_from_company():
    db = _FakeDb(invoice_email_lang="tr")
    assert resolve_briefing_lang({"briefingLang": ""}, db=db, company_id="cmp-1") == "tr"
    assert resolve_briefing_lang({"briefingLang": "auto"}, db=db, company_id="cmp-1") == "tr"
    assert resolve_briefing_lang({"briefingLang": "en"}, db=db, company_id="cmp-1") == "en"


def test_morning_dispatch_uses_turkish_not_german():
    from backend.app.platform.ai.operator_pulse import format_morning_dispatch

    body = format_morning_dispatch(
        {
            "lang": "tr",
            "companyId": "cmp-1",
            "snapshot": {
                "workersOnSite": 2,
                "openSecurityFindings": 0,
                "pendingLeave": 0,
                "expiredDocuments": 0,
                "riskLevel": "low",
            },
            "recommendations": [],
        },
        company_name="Demo",
    )
    assert "Sabah operasyon" in body
    assert "Morgen-Betriebs" not in body


def test_resolve_briefing_tz_auto_uses_company():
    from backend.app.platform.ai.operator_settings import resolve_briefing_tz

    db = _FakeDb(report_tz="Europe/Istanbul")
    assert resolve_briefing_tz({"briefingTz": "auto"}, db=db, company_id="cmp-1") == "Europe/Istanbul"
