"""Microsoft Graph inbound mail — configuration and mocked poll."""
from __future__ import annotations

import sqlite3

from backend.app.platform.mail.graph_inbound import graph_inbound_configured, poll_graph_inbox


def test_graph_inbound_off_by_default(monkeypatch):
    monkeypatch.delenv("BAUPASS_MAIL_INBOUND_PROVIDER", raising=False)
    monkeypatch.delenv("SUPPIX_MAIL_INBOUND_PROVIDER", raising=False)
    assert graph_inbound_configured() is False


def test_graph_inbound_requires_full_app_credentials(monkeypatch):
    monkeypatch.setenv("BAUPASS_MAIL_INBOUND_PROVIDER", "graph")
    monkeypatch.setenv("BAUPASS_GRAPH_TENANT_ID", "tid")
    monkeypatch.setenv("BAUPASS_GRAPH_CLIENT_ID", "cid")
    monkeypatch.delenv("BAUPASS_GRAPH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("SUPPIX_GRAPH_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("BAUPASS_GRAPH_MAILBOX_UPN", "docs@contoso.com")
    assert graph_inbound_configured() is False
    monkeypatch.setenv("BAUPASS_GRAPH_CLIENT_SECRET", "secret")
    assert graph_inbound_configured() is True


def test_poll_graph_inbox_inserts_message(monkeypatch, tmp_path):
    monkeypatch.setenv("BAUPASS_MAIL_INBOUND_PROVIDER", "graph")
    monkeypatch.setenv("BAUPASS_GRAPH_TENANT_ID", "tid")
    monkeypatch.setenv("BAUPASS_GRAPH_CLIENT_ID", "cid")
    monkeypatch.setenv("BAUPASS_GRAPH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("BAUPASS_GRAPH_MAILBOX_UPN", "docs@contoso.com")

    monkeypatch.setattr(
        "backend.app.platform.mail.graph_inbound.acquire_graph_app_token",
        lambda: "tok",
    )

    def _fake_get(url, token):
        assert token == "tok"
        if "/messages" in url and "/attachments" not in url:
            return {
                "value": [
                    {
                        "id": "g1",
                        "internetMessageId": "<m1@example>",
                        "subject": "Pass scan",
                        "from": {"emailAddress": {"address": "hr@partner.de"}},
                        "toRecipients": [{"emailAddress": {"address": "docs@contoso.com"}}],
                        "ccRecipients": [],
                        "body": {"content": "hello"},
                        "receivedDateTime": "2026-08-18T06:00:00Z",
                        "hasAttachments": False,
                    }
                ]
            }
        return {"value": []}

    monkeypatch.setattr("backend.app.platform.mail.graph_inbound._graph_get", _fake_get)
    class _Resp:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "backend.app.platform.mail.graph_inbound.urlrequest.urlopen",
        lambda *args, **kwargs: _Resp(),
    )

    db_path = tmp_path / "mail.db"
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE email_inbox (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            from_addr TEXT,
            to_addr TEXT,
            subject TEXT,
            body_text TEXT,
            matched_company_id TEXT,
            received_at TEXT
        );
        CREATE TABLE companies (
            id TEXT PRIMARY KEY,
            document_email TEXT,
            deleted_at TEXT
        );
        """
    )
    result = poll_graph_inbox(db)
    assert result["status"] == "ok"
    assert result["newEmails"] == 1
    row = db.execute("SELECT subject, from_addr FROM email_inbox").fetchone()
    assert row["subject"] == "Pass scan"
    assert row["from_addr"] == "hr@partner.de"
    db.close()
