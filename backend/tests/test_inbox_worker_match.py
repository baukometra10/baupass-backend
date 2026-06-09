from backend.app.platform.inbox_worker_match import suggest_worker_from_inbox_text
from backend.app.platform.payroll_inbox import suggest_doc_type_from_email


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self._params = ()

    def execute(self, _sql, params):
        self._params = params
        return self

    def fetchall(self):
        company_id = self._params[0] if self._params else ""
        return [row for row in self.rows if row["company_id"] == company_id]


def test_suggest_worker_from_inbox_by_full_name():
    db = _FakeDb([
        {
            "id": "wrk-1",
            "company_id": "cmp-a",
            "first_name": "Max",
            "last_name": "Müller",
            "insurance_number": "",
            "badge_id": "BP-ABC",
            "badge_id_lookup": "BP-ABC",
        }
    ])
    hit = suggest_worker_from_inbox_text(
        db,
        "cmp-a",
        subject="Dokumente für Max Müller",
        body_text="Anbei der Ausweis",
    )
    assert hit["workerId"] == "wrk-1"
    assert hit["confidence"] == "high"


def test_suggest_doc_type_personalausweis():
    hit = suggest_doc_type_from_email(
        filename="scan.pdf",
        subject="Personalausweis Max Müller",
        from_addr="hr@firma.de",
        body_text="",
    )
    assert hit["docType"] == "personalausweis"
    assert hit["confidence"] == "high"
