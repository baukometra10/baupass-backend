"""Microsoft Graph inbound mail — client credentials, not Entra SSO login tokens."""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib import parse as urlparse
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError


GRAPH_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH_MESSAGES_URL = (
    "https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/{folder}/messages"
)


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return default


def graph_inbound_configured() -> bool:
    provider = _env("BAUPASS_MAIL_INBOUND_PROVIDER", "SUPPIX_MAIL_INBOUND_PROVIDER").lower()
    if provider not in {"graph", "microsoft365", "outlook", "msgraph"}:
        return False
    return bool(
        _env("BAUPASS_GRAPH_TENANT_ID", "SUPPIX_GRAPH_TENANT_ID")
        and _env("BAUPASS_GRAPH_CLIENT_ID", "SUPPIX_GRAPH_CLIENT_ID")
        and _env("BAUPASS_GRAPH_CLIENT_SECRET", "SUPPIX_GRAPH_CLIENT_SECRET")
        and _env("BAUPASS_GRAPH_MAILBOX_UPN", "SUPPIX_GRAPH_MAILBOX_UPN")
    )


def graph_inbound_status() -> dict[str, Any]:
    return {
        "provider": "microsoft_graph",
        "configured": graph_inbound_configured(),
        "mailbox": _env("BAUPASS_GRAPH_MAILBOX_UPN", "SUPPIX_GRAPH_MAILBOX_UPN"),
        "folder": _env("BAUPASS_GRAPH_MAIL_FOLDER", "SUPPIX_GRAPH_MAIL_FOLDER", default="Inbox"),
    }


def acquire_graph_app_token() -> str:
    tenant = _env("BAUPASS_GRAPH_TENANT_ID", "SUPPIX_GRAPH_TENANT_ID")
    client_id = _env("BAUPASS_GRAPH_CLIENT_ID", "SUPPIX_GRAPH_CLIENT_ID")
    client_secret = _env("BAUPASS_GRAPH_CLIENT_SECRET", "SUPPIX_GRAPH_CLIENT_SECRET")
    if not (tenant and client_id and client_secret):
        raise RuntimeError("Microsoft Graph inbound is not fully configured")
    body = urlparse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default",
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        GRAPH_TOKEN_URL.format(tenant=tenant),
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlrequest.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8") or "{}")
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Microsoft Graph token response had no access_token")
    return token


def _graph_get(url: str, token: str) -> dict[str, Any]:
    req = urlrequest.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    with urlrequest.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _addr_from_graph(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    email = node.get("emailAddress") if isinstance(node.get("emailAddress"), dict) else node
    return str((email or {}).get("address") or "").strip()


def _match_company_id(db, addresses: list[str]) -> tuple[str | None, str]:
    for addr in addresses:
        lowered = str(addr or "").strip().lower()
        if not lowered or "@" not in lowered:
            continue
        try:
            row = db.execute(
                "SELECT id FROM companies WHERE lower(document_email) = ? AND deleted_at IS NULL",
                (lowered,),
            ).fetchone()
        except Exception:
            row = None
        if row:
            return str(row["id"] if not isinstance(row, tuple) else row[0]), lowered
    return None, (addresses[0] if addresses else "")


def poll_graph_inbox(db) -> dict[str, Any]:
    """Pull unread Graph messages into email_inbox. Marks them read after insert."""
    from backend.server import MAX_IMAP_ATTACHMENT_BYTES, now_iso

    if not graph_inbound_configured():
        return {"status": "not_configured", "newEmails": 0, "provider": "microsoft_graph"}

    mailbox = urlparse.quote(_env("BAUPASS_GRAPH_MAILBOX_UPN", "SUPPIX_GRAPH_MAILBOX_UPN"))
    folder = urlparse.quote(_env("BAUPASS_GRAPH_MAIL_FOLDER", "SUPPIX_GRAPH_MAIL_FOLDER", default="Inbox"))
    try:
        token = acquire_graph_app_token()
        url = (
            GRAPH_MESSAGES_URL.format(mailbox=mailbox, folder=folder)
            + "?$top=25&$filter=isRead eq false"
            + "&$select=id,internetMessageId,subject,from,toRecipients,ccRecipients,body,receivedDateTime,hasAttachments"
        )
        payload = _graph_get(url, token)
    except (HTTPError, URLError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "status": "connect_error",
            "newEmails": 0,
            "provider": "microsoft_graph",
            "error": str(exc),
        }

    new_email_count = 0
    for item in payload.get("value") or []:
        message_id = str(item.get("internetMessageId") or item.get("id") or "").strip()
        if not message_id:
            continue
        if db.execute("SELECT id FROM email_inbox WHERE message_id = ?", (message_id,)).fetchone():
            continue
        recipients = [
            _addr_from_graph(node)
            for node in list(item.get("toRecipients") or []) + list(item.get("ccRecipients") or [])
        ]
        recipients = [addr for addr in recipients if addr]
        from_addr = _addr_from_graph(item.get("from") or {})
        subject = str(item.get("subject") or "")
        body_obj = item.get("body") if isinstance(item.get("body"), dict) else {}
        body_text = str(body_obj.get("content") or "")[:2000]
        matched_company_id, to_addr = _match_company_id(db, recipients)
        received_at = str(item.get("receivedDateTime") or "") or now_iso()
        inbox_id = f"inb-{secrets.token_hex(8)}"
        db.execute(
            "INSERT INTO email_inbox (id, message_id, from_addr, to_addr, subject, body_text, matched_company_id, received_at) VALUES (?,?,?,?,?,?,?,?)",
            (inbox_id, message_id, from_addr, to_addr, subject, body_text, matched_company_id, received_at),
        )
        new_email_count += 1
        graph_id = str(item.get("id") or "").strip()
        if item.get("hasAttachments") and graph_id:
            try:
                atts = _graph_get(
                    f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{urlparse.quote(graph_id)}/attachments",
                    token,
                )
                for att in atts.get("value") or []:
                    if str(att.get("@odata.type") or "") not in {
                        "#microsoft.graph.fileAttachment",
                        "microsoft.graph.fileAttachment",
                    } and not att.get("contentBytes"):
                        continue
                    raw_b64 = str(att.get("contentBytes") or "")
                    if not raw_b64:
                        continue
                    import base64

                    blob = base64.b64decode(raw_b64)
                    if len(blob) > MAX_IMAP_ATTACHMENT_BYTES:
                        continue
                    db.execute(
                        "INSERT INTO email_attachments (id, inbox_id, filename, content_type, file_size, file_data) VALUES (?,?,?,?,?,?)",
                        (
                            f"att-{secrets.token_hex(8)}",
                            inbox_id,
                            str(att.get("name") or "anhang.bin"),
                            str(att.get("contentType") or "application/octet-stream"),
                            len(blob),
                            blob,
                        ),
                    )
            except Exception:
                pass
        if matched_company_id:
            try:
                from backend.app.platform.inbox_worker_match import try_auto_assign_inbox_message

                try_auto_assign_inbox_message(
                    db,
                    inbox_id,
                    company_id=str(matched_company_id),
                    subject=subject,
                    body_text=body_text,
                    from_addr=from_addr,
                )
            except Exception:
                pass
        if graph_id:
            try:
                patch = urlrequest.Request(
                    f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{urlparse.quote(graph_id)}",
                    data=json.dumps({"isRead": True}).encode("utf-8"),
                    method="PATCH",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )
                urlrequest.urlopen(patch, timeout=15).read()
            except Exception:
                pass

    db.commit()
    return {
        "status": "ok",
        "newEmails": new_email_count,
        "provider": "microsoft_graph",
        "polledAt": datetime.now(timezone.utc).isoformat(),
    }
