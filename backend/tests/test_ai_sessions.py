"""AI chat session persistence and deletion."""
from __future__ import annotations

from backend import server
from backend.app.platform.ai.sessions import (
    append_message,
    create_session,
    delete_all_sessions,
    delete_session,
    list_messages,
    list_sessions,
)


def test_delete_session_and_delete_all(client_and_db):
    _client, _db_path = client_and_db
    company_id = "cmp-ai-sess"
    user_id = "usr-ai-sess"
    with server.app.app_context():
        db = server.get_db()
        db.execute(
            """
            INSERT INTO companies (id, name, contact, plan, status, deleted_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (company_id, "AI Session Test", "ai@test.local", "enterprise", "aktiv"),
        )
        db.commit()

        s1 = create_session(db, company_id=company_id, user_id=user_id, title="Chat A")
        s2 = create_session(db, company_id=company_id, user_id=user_id, title="Chat B")
        append_message(db, s1["id"], role="user", content="Hallo")
        append_message(db, s2["id"], role="user", content="Hi")

        assert len(list_sessions(db, company_id=company_id, user_id=user_id)) == 2
        assert delete_session(db, s1["id"], company_id=company_id, user_id=user_id) is True
        assert list_messages(db, s1["id"]) == []
        assert len(list_sessions(db, company_id=company_id, user_id=user_id)) == 1

        deleted = delete_all_sessions(db, company_id=company_id, user_id=user_id)
        assert deleted == 1
        assert list_sessions(db, company_id=company_id, user_id=user_id) == []
        assert delete_session(db, s2["id"], company_id=company_id, user_id=user_id) is False
