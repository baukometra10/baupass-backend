import os
import sqlite3
import secrets
import csv
import io
import json
import base64
import smtplib
import ipaddress
import html
import socket
import re
import threading
import time
import math
from contextlib import closing, contextmanager
from functools import wraps
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from email.message import EmailMessage
from email.utils import getaddresses
from urllib.parse import quote, urlsplit, urlunsplit, unquote_to_bytes
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from flask import Flask, jsonify, request, send_from_directory, g, Response, redirect, has_request_context
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import pyotp
import qrcode

BASE_DIR = Path(__file__).resolve().parent.parent
WORKER_LOGIN_MAX_DISTANCE_METERS = 100
_site_geocode_cache: dict[str, tuple[float, float] | None] = {}

# ──────────────────────────────────────────────
# PWA-Icon-Generierung (PNG, einmalig gecacht)
# ──────────────────────────────────────────────
_icon_png_cache: dict[int, bytes] = {}

WORKER_ICON_PRIMARY_RGB = (199, 134, 82)   # #c78652
WORKER_ICON_SECONDARY_RGB = (138, 82, 48)  # #8a5230
WORKER_ICON_TEXT_RGBA = (246, 239, 226, 255)  # #f6efe2


def _generate_icon_png(size: int) -> bytes:
    """Erzeugt ein PNG-Icon (size×size) mit Baupass-Branding."""
    if size in _icon_png_cache:
        return _icon_png_cache[size]

    from PIL import Image, ImageDraw, ImageFont
    import io as _io

    r1, g1, b1 = WORKER_ICON_PRIMARY_RGB
    r2, g2, b2 = WORKER_ICON_SECONDARY_RGB
    radius = max(4, size // 6)
    denom = max(1, 2 * (size - 1))

    try:
        import numpy as np
        yi, xi = np.mgrid[0:size, 0:size]
        t = (xi + yi) / denom
        arr = np.zeros((size, size, 4), dtype=np.uint8)
        arr[:, :, 0] = np.clip(r1 + (r2 - r1) * t, 0, 255).astype(np.uint8)
        arr[:, :, 1] = np.clip(g1 + (g2 - g1) * t, 0, 255).astype(np.uint8)
        arr[:, :, 2] = np.clip(b1 + (b2 - b1) * t, 0, 255).astype(np.uint8)
        arr[:, :, 3] = 255
        img_raw = Image.fromarray(arr, "RGBA")
    except ImportError:
        pixels = bytearray(size * size * 4)
        idx = 0
        for y in range(size):
            for x in range(size):
                tn = x + y
                pixels[idx]     = r1 + (r2 - r1) * tn // denom
                pixels[idx + 1] = g1 + (g2 - g1) * tn // denom
                pixels[idx + 2] = b1 + (b2 - b1) * tn // denom
                pixels[idx + 3] = 255
                idx += 4
        img_raw = Image.frombytes("RGBA", (size, size), bytes(pixels))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img_raw, mask=mask)

    draw = ImageDraw.Draw(result)
    text = "BP"
    font_size = max(48, int(size * 0.375))
    font = None
    for fp in ["segoeuib.ttf", "arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        try:
            font = ImageFont.truetype(fp, font_size)
            break
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    text_x = (size - tw) / 2 - bbox[0]
    text_y = size * (330 / 512) - th / 2 - bbox[1]
    draw.text((text_x, text_y), text, fill=WORKER_ICON_TEXT_RGBA, font=font)

    buf = _io.BytesIO()
    result.save(buf, "PNG")
    data = buf.getvalue()
    _icon_png_cache[size] = data
    return data
_default_db_path = BASE_DIR / "backend" / "baupass.db"
# DB path selection:
# 1. Explicit env var BAUPASS_DB_PATH always wins (Render, custom setups).
# 2. Auto-detect Railway persistent volume: if /data exists and is writable,
#    always use /data/baupass.db – even on first deploy (init_db creates it).
#    This ensures data survives redeployments without manual env var config.
# 3. Fall back to backend/baupass.db (local / default).
_env_db_path = os.getenv("BAUPASS_DB_PATH", "").strip()
if not _env_db_path:
    _railway_data = Path("/data")
    _railway_candidate = _railway_data / "baupass.db"
    if _railway_data.is_dir() and os.access(_railway_data, os.W_OK):
        _env_db_path = str(_railway_candidate)
        # Auto-migrate: if the persistent volume is empty but the local fallback DB
        # already has data (companies, workers etc.), copy it over automatically so
        # no data is lost on the first deployment after enabling the volume.
        if not _railway_candidate.exists() and _default_db_path.exists() and _default_db_path.stat().st_size > 0:
            try:
                import shutil as _shutil
                _shutil.copy2(str(_default_db_path), str(_railway_candidate))
                print(f"[baupass] Auto-migrated existing DB from {_default_db_path} to {_railway_candidate}", flush=True)
            except Exception as _migrate_err:
                print(f"[baupass] WARNING: DB auto-migration failed: {_migrate_err}", flush=True)
DB_PATH = Path((_env_db_path or str(_default_db_path))).expanduser()
try:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
except OSError:
    # Fallback to default if the configured path is not writable (e.g. wrong env var).
    DB_PATH = _default_db_path
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Module-level cache for Resend credentials stored in DB.
# Populated at startup (init_db) and refreshed after settings save.
# Avoids opening a second SQLite connection from background threads.
_resend_key_cache: dict = {
    "key": "",
    "from_email": "",
    "source": "",
    "brevo_key": "",
    "brevo_from_email": "",
}

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def get_cors_origins():
    origins = [
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "https://saa-s-flow--mahmodscharif12.replit.app",
        re.compile(r"^https://[a-z0-9-]+\.github\.io$"),
        re.compile(r"^https://[a-z0-9-]+\.onrender\.com$"),
    ]
    extra_origins = [item.strip() for item in (os.getenv("BAUPASS_CORS_ORIGINS") or "").split(",") if item.strip()]
    return origins + extra_origins

@app.route("/user/<id>")
def user(id):
    return f"Baustellenausweis für User {id}"

from flask_cors import CORS
# CORS mit erlaubten Origins und Credentials aktivieren (kein Wildcard!)
CORS(app, supports_credentials=True, origins=get_cors_origins())

SESSION_TTL_HOURS = 12
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 10
SESSION_COOKIE_NAME = "baupass_session"
failed_login_attempts = {}

PLAN_NET_PRICE_EUR = {
    "tageskarte": 19.0,
    "starter": 49.0,
    "professional": 99.0,
    "enterprise": 199.0,
}

AUTO_SUSPEND_GRACE_DAYS = 3
APP_STARTED_AT = datetime.now(timezone.utc)
DUNNING_LAST_RUN_AT = None
DUNNING_LAST_RESULT = {"remindersSent": 0, "reminderFailures": 0, "overdueUpdated": 0, "suspendedCompanies": 0}
BACKUP_RETENTION_DAYS = max(1, int(os.getenv("BAUPASS_BACKUP_RETENTION_DAYS", "30")))
ALERT_DEDUP_MINUTES = max(5, int(os.getenv("BAUPASS_ALERT_DEDUP_MINUTES", "30")))
INVOICE_SEND_MAX_RETRIES = max(1, int(os.getenv("BAUPASS_INVOICE_SEND_MAX_RETRIES", "5")))
INVOICE_RETRY_CRITICAL_WARN_THRESHOLD = max(1, int(os.getenv("BAUPASS_INVOICE_RETRY_CRITICAL_WARN_THRESHOLD", "10")))
INVOICE_RETRY_CRITICAL_ALERT_THRESHOLD = max(
    INVOICE_RETRY_CRITICAL_WARN_THRESHOLD,
    int(os.getenv("BAUPASS_INVOICE_RETRY_CRITICAL_ALERT_THRESHOLD", "20")),
)
INVOICE_RETRY_ALERT_EMAIL_COOLDOWN_MINUTES = max(
    5,
    int(os.getenv("BAUPASS_INVOICE_RETRY_ALERT_EMAIL_COOLDOWN_MINUTES", "30")),
)
INVOICE_RETRY_ALERT_TOP_ITEMS = max(3, int(os.getenv("BAUPASS_INVOICE_RETRY_ALERT_TOP_ITEMS", "5")))
INVOICE_SMTP_CIRCUIT_FAIL_THRESHOLD = max(2, int(os.getenv("BAUPASS_INVOICE_SMTP_CIRCUIT_FAIL_THRESHOLD", "3")))
INVOICE_SMTP_CIRCUIT_OPEN_SECONDS = max(120, int(os.getenv("BAUPASS_INVOICE_SMTP_CIRCUIT_OPEN_SECONDS", "900")))
INVOICE_SMTP_STUCK_MINUTES = max(5, int(os.getenv("BAUPASS_INVOICE_SMTP_STUCK_MINUTES", "20")))
OPERATION_APPROVAL_EXPIRY_MINUTES = max(5, int(os.getenv("BAUPASS_OPERATION_APPROVAL_EXPIRY_MINUTES", "30")))

REQUEST_RATE_LIMITS = {
    "import": {"max": 10, "window_seconds": 60},
    "login": {"max": 30, "window_seconds": 60},
    "worker_login": {"max": 30, "window_seconds": 60},
    "password_reset": {"max": 5, "window_seconds": 300},
}
request_rate_state = {}
_rate_lock = threading.Lock()

_background_started = False
_background_lock = threading.Lock()
_invoice_smtp_circuit_lock = threading.Lock()
_invoice_smtp_circuit = {
    "consecutive_failures": 0,
    "open_until": None,
    "last_error": "",
}
_invoice_retry_guard_lock = threading.Lock()
_invoice_retry_inflight = {}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA synchronous=NORMAL")
        g.db.execute("PRAGMA busy_timeout=30000")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def utc_now():
    return datetime.now(timezone.utc)


def utc_iso(value=None):
    dt = value or utc_now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"


def now_iso():
    return utc_iso()


def parse_iso_date(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_PHOTO_DATA_URL_RE = re.compile(r"^data:image\/(png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=\r\n]+$", re.IGNORECASE)


def clean_text_input(value, max_len=255):
    raw = str(value or "").strip()
    raw = _CONTROL_CHARS_RE.sub("", raw)
    if len(raw) > max_len:
        raw = raw[:max_len]
    return raw


def sanitize_hex_color(value, fallback="#0f4c5c"):
    raw = clean_text_input(value, max_len=7)
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", raw):
        return raw.lower()
    return fallback


def sanitize_optional_email(value, field_error="invalid_email"):
    raw = clean_text_input(value, max_len=254)
    if not raw:
        return ""
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", raw):
        raise ValueError(field_error)
    return raw


def sanitize_iban(value):
    raw = clean_text_input(value, max_len=64).upper().replace(" ", "")
    raw = re.sub(r"[^A-Z0-9]", "", raw)
    if not raw:
        return ""
    if len(raw) < 15 or len(raw) > 34:
        raise ValueError("invalid_iban")
    return raw


def sanitize_bic(value):
    raw = clean_text_input(value, max_len=20).upper().replace(" ", "")
    raw = re.sub(r"[^A-Z0-9]", "", raw)
    if not raw:
        return ""
    if not re.fullmatch(r"[A-Z0-9]{8}([A-Z0-9]{3})?", raw):
        raise ValueError("invalid_bic")
    return raw


def clean_id_input(value, max_len=64):
    candidate = clean_text_input(value, max_len=max_len)
    if candidate and not _SAFE_ID_RE.fullmatch(candidate):
        raise ValueError("invalid_identifier")
    return candidate


def sanitize_photo_data(value, required=False):
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise ValueError("photo_required")
        return ""
    if len(raw) > 5_000_000:
        raise ValueError("photo_too_large")
    if not _PHOTO_DATA_URL_RE.fullmatch(raw):
        raise ValueError("invalid_photo_data")
    return raw.replace("\n", "").replace("\r", "")


def _required_worker_doc_types():
    return ["mindestlohnnachweis", "personalausweis"]


def get_worker_required_document_snapshot(db, worker_id, today_value=None):
    worker_id = clean_id_input(worker_id)
    if not worker_id:
        return {
            "requiredTypes": _required_worker_doc_types(),
            "missingTypes": [],
            "expiredTypes": [],
            "expiringSoonTypes": [],
            "latestByType": {},
        }

    today = str(today_value or now_iso()[:10])
    soon_date = (parse_iso_date(today) or utc_now().date()) + timedelta(days=30)
    required_doc_types = _required_worker_doc_types()
    placeholders = ", ".join("?" for _ in required_doc_types)

    latest_rows = db.execute(
        f"""
        SELECT wd.doc_type, wd.expiry_date, wd.created_at
        FROM worker_documents wd
        JOIN (
            SELECT doc_type, MAX(created_at) AS latest_created_at
            FROM worker_documents
            WHERE worker_id = ?
              AND doc_type IN ({placeholders})
            GROUP BY doc_type
        ) latest ON latest.doc_type = wd.doc_type AND latest.latest_created_at = wd.created_at
        WHERE wd.worker_id = ?
        """,
        (worker_id, *required_doc_types, worker_id),
    ).fetchall()

    latest_by_type = {}
    for row in latest_rows:
        doc_type = str(row["doc_type"] or "").strip().lower()
        if not doc_type:
            continue
        latest_by_type[doc_type] = {
            "expiryDate": str(row["expiry_date"] or "").strip(),
            "createdAt": str(row["created_at"] or "").strip(),
        }

    missing_types = []
    expired_types = []
    expiring_soon_types = []

    for doc_type in required_doc_types:
        entry = latest_by_type.get(doc_type)
        if not entry:
            missing_types.append(doc_type)
            continue
        expiry = entry.get("expiryDate") or ""
        if expiry:
            if expiry < today:
                expired_types.append(doc_type)
            else:
                expiry_parsed = parse_iso_date(expiry)
                if expiry_parsed and expiry_parsed <= soon_date:
                    expiring_soon_types.append(doc_type)

    return {
        "requiredTypes": required_doc_types,
        "missingTypes": missing_types,
        "expiredTypes": expired_types,
        "expiringSoonTypes": expiring_soon_types,
        "latestByType": latest_by_type,
    }


def get_worker_lock_metadata(db, worker_row, today_value=None):
    if not worker_row:
        return {}
    worker_type = str(worker_row["worker_type"] or "worker").strip().lower()
    if worker_type != "worker":
        return {}

    snapshot = get_worker_required_document_snapshot(db, worker_row["id"], today_value=today_value)
    expired_types = snapshot.get("expiredTypes") or []
    if expired_types:
        label_map = {
            "personalausweis": "Personalausweis/Reisepass",
            "mindestlohnnachweis": "Mindestlohnnachweis",
        }
        labels = [label_map.get(item, item) for item in expired_types]
        return {
            "lockReasonCode": "expired_documents",
            "lockReason": f"Automatisch gesperrt wegen abgelaufener Pflichtdokumente: {', '.join(labels)}",
            "expiredRequiredDocTypes": expired_types,
        }
    return {}


def worker_has_expired_required_documents(db, worker_id, today_value=None):
    snapshot = get_worker_required_document_snapshot(db, worker_id, today_value=today_value)
    expired_types = list(snapshot.get("expiredTypes") or [])
    return len(expired_types) > 0, expired_types


def unlock_worker_if_documents_valid(db, worker_row, today_value=None, actor=None):
    if not worker_row:
        return False
    if str(worker_row["deleted_at"] or "").strip():
        return False
    if str(worker_row["worker_type"] or "worker").strip().lower() != "worker":
        return False

    worker_id = str(worker_row["id"] or "").strip()
    if not worker_id:
        return False

    has_expired, _expired_types = worker_has_expired_required_documents(db, worker_id, today_value=today_value)
    if has_expired:
        return False
    if str(worker_row["status"] or "").strip().lower() != "gesperrt":
        return False

    lock_code = f"worker_doc_expired_lock_{worker_id}"
    unresolved_lock_alert = db.execute(
        "SELECT id FROM system_alerts WHERE code = ? AND resolved_at IS NULL ORDER BY created_at DESC LIMIT 1",
        (lock_code,),
    ).fetchone()
    if not unresolved_lock_alert:
        return False

    db.execute("UPDATE workers SET status = 'aktiv' WHERE id = ?", (worker_id,))
    db.execute("UPDATE system_alerts SET resolved_at = ? WHERE code = ? AND resolved_at IS NULL", (now_iso(), lock_code))

    log_audit(
        "worker.auto_unlocked_documents",
        f"Mitarbeiter {worker_id} wurde nach gueltigem Dokument-Update automatisch entsperrt",
        target_type="worker",
        target_id=worker_id,
        company_id=worker_row["company_id"],
        actor=actor,
    )
    return True


def lock_worker_for_expired_documents(db, worker_row, today_value=None):
    if not worker_row:
        return False
    if str(worker_row["deleted_at"] or "").strip():
        return False
    if str(worker_row["worker_type"] or "worker").strip().lower() != "worker":
        return False

    worker_id = str(worker_row["id"] or "").strip()
    if not worker_id:
        return False

    has_expired, expired_types = worker_has_expired_required_documents(db, worker_id, today_value=today_value)
    if not has_expired:
        return False

    if str(worker_row["status"] or "").strip().lower() != "gesperrt":
        db.execute("UPDATE workers SET status = 'gesperrt' WHERE id = ?", (worker_id,))

    badge = str(worker_row["badge_id"] or "-")
    full_name = f"{str(worker_row['first_name'] or '').strip()} {str(worker_row['last_name'] or '').strip()}".strip() or "Mitarbeiter"
    create_system_alert(
        db,
        code=f"worker_doc_expired_lock_{worker_id}",
        severity="warning",
        message=f"Mitarbeiter {full_name} ({badge}) wurde wegen abgelaufener Dokumente automatisch gesperrt.",
        details={
            "workerId": worker_id,
            "companyId": worker_row["company_id"],
            "expiredDocTypes": expired_types,
        },
        dedup_minutes=240,
    )
    return True


def lock_workers_with_expired_documents(db, today_value=None):
    today = str(today_value or now_iso()[:10])
    rows = db.execute(
        """
        SELECT id, company_id, first_name, last_name, badge_id, worker_type, status, deleted_at
        FROM workers
        WHERE deleted_at IS NULL
          AND worker_type = 'worker'
          AND status != 'gesperrt'
        """
    ).fetchall()

    changed = 0
    for row in rows:
        if lock_worker_for_expired_documents(db, row, today_value=today):
            changed += 1

    if changed > 0:
        db.commit()
    return changed


def get_rate_limit_key(scope):
    return f"{scope}|{get_client_ip()}"


def check_rate_limit(scope):
    rule = REQUEST_RATE_LIMITS.get(scope)
    if not rule:
        return True, 0

    now_ts = time.time()
    key = get_rate_limit_key(scope)
    with _rate_lock:
        state = request_rate_state.get(key)
        if not state:
            request_rate_state[key] = {"count": 1, "window_start": now_ts}
            return True, 0

        elapsed = now_ts - float(state.get("window_start", now_ts))
        if elapsed >= rule["window_seconds"]:
            request_rate_state[key] = {"count": 1, "window_start": now_ts}
            return True, 0

        state["count"] = int(state.get("count", 0)) + 1
        if state["count"] > rule["max"]:
            retry_after = max(1, int(rule["window_seconds"] - elapsed))
            return False, retry_after

        return True, 0


def require_rate_limit(scope):
    def decorator(handler):
        @wraps(handler)
        def wrapper(*args, **kwargs):
            allowed, retry_after = check_rate_limit(scope)
            if not allowed:
                return jsonify({"error": "rate_limited", "retryAfterSeconds": retry_after}), 429
            return handler(*args, **kwargs)

        return wrapper

    return decorator


def expiry_iso(hours=SESSION_TTL_HOURS):
    return utc_iso(utc_now() + timedelta(hours=hours))


def _next_local_midnight_utc():
    timezone_name = os.getenv("BAUPASS_TIMEZONE", "Europe/Berlin")
    try:
        local_tz = ZoneInfo(timezone_name)
    except Exception:
        local_tz = timezone.utc

    local_now = datetime.now(local_tz)
    return (local_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def worker_session_expiry_iso():
    # Worker app sessions are daily cards and expire at next local midnight.
    next_midnight_utc = _next_local_midnight_utc().replace(microsecond=0)
    return next_midnight_utc.replace(tzinfo=None).isoformat() + "Z"


def worker_access_token_expiry_iso():
    # Visitor-card link expires after a short window, but never later than local midnight.
    max_hours = max(1, int(os.getenv("BAUPASS_VISITOR_LINK_HOURS", "12")))
    now_utc = datetime.now(timezone.utc)
    by_hours_utc = now_utc + timedelta(hours=max_hours)
    expires_utc = min(by_hours_utc, _next_local_midnight_utc()).replace(microsecond=0)
    return expires_utc.replace(tzinfo=None).isoformat() + "Z"


def resolve_worker_session_expiry_iso(worker):
    session_end = parse_iso_utc(worker_session_expiry_iso())
    visit_end = resolve_worker_access_end_utc(worker)
    if visit_end and visit_end < session_end:
        return visit_end.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"
    return session_end.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"


def resolve_worker_access_token_expiry_iso(worker):
    link_end = parse_iso_utc(worker_access_token_expiry_iso())
    visit_end = resolve_worker_access_end_utc(worker)
    if visit_end and visit_end < link_end:
        return visit_end.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"
    return link_end.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"


def purge_expired_worker_app_sessions(db, now_value=None):
    timestamp = now_value or now_iso()
    result = db.execute("DELETE FROM worker_app_sessions WHERE expires_at < ?", (timestamp,))
    return int(result.rowcount or 0)


def normalize_company_plan(plan_value):
    plan = str(plan_value or "").strip().lower()
    return plan if plan in PLAN_NET_PRICE_EUR else "tageskarte"


def normalize_branding_preset(value):
    preset = str(value or "").strip().lower()
    return preset if preset in {"construction", "industry", "premium"} else "construction"


def slugify_company_alias(value):
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    normalized = normalized.strip("-")
    return normalized[:48] or "firma"


def normalize_email_address(value):
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def suggest_company_document_email(company_name, settings_row=None):
    row = settings_row
    if row is None:
        try:
            row = get_db().execute("SELECT imap_username FROM settings WHERE id = 1").fetchone()
        except Exception:
            row = None

    imap_username = (row["imap_username"] if row and "imap_username" in row.keys() else "") or ""
    imap_username = normalize_email_address(imap_username)
    if "@" not in imap_username:
        return ""

    local_part, domain = imap_username.split("@", 1)
    alias_base = (local_part.split("+", 1)[0] or "dokumente").strip() or "dokumente"
    return f"{alias_base}+{slugify_company_alias(company_name)}@{domain}"


def extract_message_recipient_address(msg):
    for header_name in ("Delivered-To", "X-Original-To", "Envelope-To", "To"):
        header_value = msg.get(header_name)
        if not header_value:
            continue
        for _, email_addr in getaddresses([header_value]):
            normalized = normalize_email_address(email_addr)
            if normalized:
                return normalized
    return ""


def find_company_by_document_email(db, email_address):
    normalized = normalize_email_address(email_address)
    if not normalized:
        return None
    return db.execute(
        "SELECT * FROM companies WHERE lower(document_email) = ? AND deleted_at IS NULL",
        (normalized,),
    ).fetchone()


def rematch_inbox_company_links(db, company_id=None):
    """Rebuild inbox-company matches by recipient address. Optionally limited to one company."""
    if company_id:
        company = db.execute(
            "SELECT id, document_email FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
        if not company:
            return 0

        db.execute("UPDATE email_inbox SET matched_company_id = NULL WHERE matched_company_id = ?", (company_id,))
        document_email = normalize_email_address(company["document_email"] or "")
        if not document_email:
            return 0
        result = db.execute(
            "UPDATE email_inbox SET matched_company_id = ? WHERE lower(to_addr) = ?",
            (company_id, document_email),
        )
        return int(result.rowcount or 0)

    db.execute("UPDATE email_inbox SET matched_company_id = NULL")
    result = db.execute(
        """
        UPDATE email_inbox
        SET matched_company_id = (
            SELECT c.id
            FROM companies c
            WHERE c.deleted_at IS NULL
              AND lower(c.document_email) = lower(email_inbox.to_addr)
            LIMIT 1
        )
        WHERE COALESCE(to_addr, '') <> ''
        """
    )
    return int(result.rowcount or 0)


def normalize_worker_type(worker_type):
    normalized = str(worker_type or "worker").strip().lower()
    return normalized if normalized in {"worker", "visitor"} else "worker"


def parse_date_start(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_datetime_local_to_utc_iso(value):
    text = str(value or "").strip()
    if not text:
        return ""
    timezone_name = os.getenv("BAUPASS_TIMEZONE", "Europe/Berlin")
    try:
        local_tz = ZoneInfo(timezone_name)
    except Exception:
        local_tz = timezone.utc
    try:
        local_dt = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except ValueError:
        try:
            parsed = parse_iso_utc(text)
            if not parsed:
                return ""
            return parsed.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"
        except Exception:
            return ""
    localized = local_dt.replace(tzinfo=local_tz)
    as_utc = localized.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)
    return as_utc.isoformat() + "Z"


def serialize_worker_record(row):
    return {
        "id": row["id"],
        "companyId": row["company_id"],
        "subcompanyId": row["subcompany_id"],
        "firstName": row["first_name"],
        "lastName": row["last_name"],
        "insuranceNumber": row["insurance_number"],
        "workerType": normalize_worker_type(row["worker_type"]),
        "role": row["role"],
        "site": row["site"],
        "validUntil": row["valid_until"],
        "visitorCompany": row["visitor_company"],
        "visitPurpose": row["visit_purpose"],
        "hostName": row["host_name"],
        "visitEndAt": row["visit_end_at"],
        "status": row["status"],
        "photoData": row["photo_data"],
        "badgeId": row["badge_id"],
        "badgePinConfigured": bool(row["badge_pin_hash"]),
        "physicalCardId": row["physical_card_id"],
        "deletedAt": row["deleted_at"],
    }


def resolve_worker_access_end_utc(worker):
    worker_type = normalize_worker_type(worker["worker_type"] if isinstance(worker, sqlite3.Row) else worker.get("worker_type") or worker.get("workerType"))
    visit_end_at = worker["visit_end_at"] if isinstance(worker, sqlite3.Row) else worker.get("visit_end_at", worker.get("visitEndAt", ""))
    valid_until = worker["valid_until"] if isinstance(worker, sqlite3.Row) else worker.get("valid_until", worker.get("validUntil", ""))
    if worker_type != "visitor":
        return None
    visit_end_dt = parse_iso_utc(visit_end_at)
    if visit_end_dt:
        return visit_end_dt.astimezone(timezone.utc)
    valid_until_dt = parse_date_start(valid_until)
    if valid_until_dt:
        return valid_until_dt.replace(hour=23, minute=59, second=59)
    return None


def worker_visit_has_expired(worker, reference_dt=None):
    access_end = resolve_worker_access_end_utc(worker)
    if not access_end:
        return False
    now_dt = reference_dt or datetime.now(timezone.utc)
    return access_end <= now_dt


def calculate_net_amount_by_plan(company_plan, payload_net_amount):
    # Keep manual values from UI, but provide a predictable fallback for tariff-based billing.
    explicit_net = float(payload_net_amount or 0)
    if explicit_net > 0:
        return round(explicit_net, 2)
    normalized_plan = normalize_company_plan(company_plan)
    return PLAN_NET_PRICE_EUR[normalized_plan]


@app.after_request
def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(self)"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' https:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )
    path = (request.path or "").lower()
    is_pwa_asset = (
        path in {
            "/worker.html",
            "/worker.css",
            "/worker-app.js",
            "/worker-manifest.json",
            "/worker-sw.js",
            "/worker-icon-192.png",
            "/worker-icon-512.png",
            "/worker-icon-192.svg",
            "/worker-icon-512.svg",
        }
        or path.startswith("/worker-icon-")
    )

    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    elif is_pwa_asset:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    else:
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Pragma"] = "no-cache"

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text/html" in content_type:
        response.headers["Content-Language"] = "de"
        response.headers["X-Robots-Tag"] = "notranslate"
        existing_cache_control = response.headers.get("Cache-Control") or ""
        if "no-transform" not in existing_cache_control.lower():
            response.headers["Cache-Control"] = (existing_cache_control + ", no-transform").strip(", ")

    return response


def build_login_throttle_key():
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    client_ip = forwarded.split(",", 1)[0].strip() if forwarded else (request.remote_addr or "local")
    username = ((request.get_json(silent=True) or {}).get("username") or "").strip().lower()
    return f"{client_ip}|{username}"


def can_attempt_login(throttle_key):
    state = failed_login_attempts.get(throttle_key)
    if not state:
        return True, 0
    locked_until = state.get("locked_until")
    if not locked_until:
        return True, 0
    now = utc_now()
    if now >= locked_until:
        failed_login_attempts.pop(throttle_key, None)
        return True, 0
    remaining_seconds = int((locked_until - now).total_seconds())
    return False, max(remaining_seconds, 1)


def register_login_failure(throttle_key):
    now = utc_now()
    state = failed_login_attempts.get(throttle_key, {"count": 0, "locked_until": None})
    state["count"] = int(state.get("count", 0)) + 1
    if state["count"] >= LOGIN_MAX_ATTEMPTS:
        state["locked_until"] = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
    failed_login_attempts[throttle_key] = state


def clear_login_failures(throttle_key):
    failed_login_attempts.pop(throttle_key, None)


def clear_login_failures_for_username(username):
    normalized_username = str(username or "").strip().lower()
    if not normalized_username:
        return
    keys_to_delete = [key for key in failed_login_attempts.keys() if key.endswith(f"|{normalized_username}")]
    for key in keys_to_delete:
        failed_login_attempts.pop(key, None)


def get_user_from_session_token(token_value):
    if not token_value:
        return None
    db = get_db()
    session = db.execute(
        "SELECT user_id, expires_at, support_read_only, support_company_name, support_actor_name, preview_company_id FROM sessions WHERE token = ?",
        (token_value,),
    ).fetchone()
    if not session:
        return None
    if session["expires_at"] < now_iso():
        db.execute("DELETE FROM sessions WHERE token = ?", (token_value,))
        db.commit()
        return None
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return None
    payload = row_to_dict(user)
    payload["support_read_only"] = is_read_only_support_session(session)
    payload["support_company_name"] = session["support_company_name"] or ""
    payload["support_actor_name"] = session["support_actor_name"] or ""
    payload["preview_company_id"] = session["preview_company_id"] or ""
    return payload


def render_login_page():
    db = get_db()
    settings_row = db.execute("SELECT invoice_logo_data, platform_name, operator_name, turnstile_endpoint FROM settings WHERE id = 1").fetchone()
    logo_src = ""
    platform_name = "BauPass Control"
    operator_name = "Deine Betriebsfirma"
    turnstile_endpoint = "Noch nicht gesetzt"
    if settings_row:
        logo_src = (settings_row["invoice_logo_data"] or "").strip()
        platform_name = settings_row["platform_name"] or platform_name
        operator_name = settings_row["operator_name"] or operator_name
        turnstile_endpoint = (settings_row["turnstile_endpoint"] or "").strip() or turnstile_endpoint

    if not logo_src:
        fallback_logo = BASE_DIR / "branding" / "baukometra-logo.svg"
        if fallback_logo.exists():
            svg = fallback_logo.read_text(encoding="utf-8")
            logo_src = f"data:image/svg+xml;charset=utf-8,{quote(svg)}"
        else:
            logo_src = "/branding/baukometra-logo.svg"

    fallback_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="210" height="84" viewBox="0 0 210 84"><rect width="210" height="84" rx="12" fill="#0f4c5c"/><text x="50%" y="54%" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="32" font-weight="700" fill="white">BK</text></svg>'
    fallback_data = f"data:image/svg+xml;charset=utf-8,{quote(fallback_svg)}"

    template = """
        <!DOCTYPE html>
        <html lang="de" translate="no">
        <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <meta name="google" content="notranslate" />
            <meta http-equiv="Content-Language" content="de" />
            <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate, max-age=0" />
            <meta http-equiv="Pragma" content="no-cache" />
            <meta http-equiv="Expires" content="0" />
            <title>__PLATFORM__ Login</title>
            <link rel="preconnect" href="https://fonts.googleapis.com" />
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
            <link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet" />
            <link rel="stylesheet" href="/styles.css" />
            <style>
                body.auth-locked {
                    display: block;
                }
                .server-auth-shell {
                    min-height: 100vh;
                }
                .server-auth-shell .auth-overlay {
                    padding: 16px;
                }
                .server-auth-shell .auth-panel {
                    width: min(100%, 560px);
                    max-height: calc(100vh - 32px);
                    overflow: auto;
                }
                .server-auth-shell .auth-form {
                    gap: 10px;
                }
                .server-auth-shell .server-auth-submit {
                    position: sticky;
                    bottom: 0;
                    z-index: 2;
                    margin-top: 6px;
                    box-shadow: 0 -10px 18px rgba(255, 252, 246, 0.94);
                }
                .server-auth-shell .auth-form label {
                    gap: 5px;
                }
                .server-auth-shell .auth-form input {
                    padding: 10px 12px;
                }
                .server-auth-shell .auth-system-grid {
                    margin-top: 10px;
                    gap: 8px;
                }
                .server-auth-shell .meta-box {
                    padding: 12px;
                }
                .server-auth-error {
                    display: none;
                    margin: 0;
                    padding: 10px 12px;
                    border-radius: 12px;
                    color: #8a1f1f;
                    background: rgba(197, 61, 47, 0.16);
                    border: 1px solid rgba(197, 61, 47, 0.3);
                    font-weight: 600;
                }
                @media (max-height: 820px) {
                    .server-auth-shell .auth-panel {
                        gap: 12px;
                        padding: 20px;
                    }
                    .server-auth-shell .auth-copy {
                        margin-top: 6px;
                        line-height: 1.45;
                    }
                    .server-auth-shell .auth-hints {
                        display: none;
                    }
                }
            </style>
        </head>
        <body class="auth-locked">
            <div class="server-auth-shell">
                <div id="authOverlay" class="auth-overlay active" style="display:grid; position:relative; inset:auto; min-height:100vh;">
                    <div class="auth-panel">
                        <div>
                            <img class="website-logo-sync website-logo website-logo-auth" src="__LOGO__" alt="Firmenlogo" onerror="this.onerror=null;this.src='__FALLBACK__'" />
                            <p class="eyebrow">Melde-Seite</p>
                            <h2>Sicher in __PLATFORM__ anmelden</h2>
                            <p class="auth-copy">Super-Admin behaelt die Systemhoheit. Firmen-Admins sehen nur ihre Firma. Der Drehkreuz-Login bekommt einen schnellen Zutrittsmodus.</p>
                            <div class="auth-system-grid">
                                <article class="auth-system-card">
                                    <span>Plattform</span>
                                    <strong id="loginPlatformName">__PLATFORM__</strong>
                                </article>
                                <article class="auth-system-card">
                                    <span>Betreiber</span>
                                    <strong id="loginOperatorName">__OPERATOR__</strong>
                                </article>
                                <article class="auth-system-card full-width">
                                    <span>Drehkreuz-Endpunkt</span>
                                    <strong id="loginTurnstileEndpoint">__TURNSTILE__</strong>
                                </article>
                            </div>
                        </div>

                        <p id="errorBox" class="server-auth-error"></p>
                        <form id="f" class="auth-form" novalidate>
                            <label>
                                Benutzername
                                <input id="u" required />
                            </label>
                            <label>
                                Passwort
                                <input id="p" type="password" required />
                            </label>
                            <label>
                                OTP-Code (wenn 2FA aktiv)
                                <input id="o" />
                            </label>
                            <label>
                                Zugangstyp
                                <select id="s">
                                    <option value="auto">Automatisch</option>
                                    <option value="server-admin">Server-Admin</option>
                                    <option value="company-admin">Firmen-Admin</option>
                                    <option value="turnstile">Drehkreuz</option>
                                </select>
                            </label>
                            <button type="submit" class="primary-button server-auth-submit">Anmelden</button>
                        </form>

                        <div class="auth-hints">
                            <div class="meta-box">
                                <p>Demo-Zugaenge</p>
                                <p>Super-Admin: superadmin / 1234</p>
                                <p>Firmen-Admin: firma / 1234</p>
                                <p>Drehkreuz: drehkreuz / 1234</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <script>
                const form = document.getElementById('f');
                const errorBox = document.getElementById('errorBox');
                const showError = (msg) => {
                    errorBox.textContent = msg;
                    errorBox.style.display = 'block';
                };
                form.addEventListener('submit', async (event) => {
                    event.preventDefault();
                    errorBox.style.display = 'none';
                    let res;
                    let p = null;
                    try {
                        res = await fetch('/api/login', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                username: document.getElementById('u').value.trim(),
                                password: document.getElementById('p').value,
                                otpCode: document.getElementById('o').value.trim(),
                                loginScope: document.getElementById('s').value
                            })
                        });
                    } catch {
                        showError('Backend nicht erreichbar. Bitte Seite neu laden und Server prüfen.');
                        return;
                    }
                    p = await res.json().catch(() => ({ error: 'login_failed' }));
                    const code = (p && p.error) ? p.error : (!res.ok ? String(res.status) : '');
                    if (code) {
                        if (code === 'too_many_attempts') {
                            showError('Zu viele Fehlversuche. Bitte spaeter erneut versuchen.');
                            return;
                        }
                        if (code === 'invalid_credentials') {
                            showError('Benutzername oder Passwort ist falsch. Bitte Daten prüfen.');
                            return;
                        }
                        if (code === 'otp_required') {
                            showError('Für dieses Konto ist 2FA aktiv. Bitte OTP-Code eingeben.');
                            return;
                        }
                        if (code === 'otp_invalid') {
                            showError('OTP-Code ist ungültig oder abgelaufen. Bitte neuen Code eingeben.');
                            return;
                        }
                        if (code === 'forbidden_tenant_host') {
                            showError('Dieser Zugang ist nur über die freigegebene Firmen-Domain erlaubt.');
                            return;
                        }
                        if (code === 'admin_ip_not_allowed') {
                            showError('Admin-Zugriff von dieser IP ist nicht erlaubt.');
                            return;
                        }
                        if (code === 'login_scope_mismatch') {
                            showError('Zugangstyp passt nicht zum Konto. Bitte Server-Admin/Firmen-Admin korrekt auswählen.');
                            return;
                        }
                        if (code === 'support_company_mismatch') {
                            showError('Dieser Login passt nicht zur ausgewaehlten Firma. Bitte den Firmen-Admin der markierten Firma verwenden.');
                            return;
                        }
                        if (code === 'support_session_read_only') {
                            showError('Dieser Support-Login ist nur lesend. Aenderungen sind in dieser Sitzung gesperrt.');
                            return;
                        }
                        showError('Login fehlgeschlagen: ' + code);
                        return;
                    }
                    if (!p || p.ok !== true || !p.token) {
                        showError('Login-Antwort unvollstaendig. Bitte erneut versuchen.');
                        return;
                    }
                    location.href = '/';
                });
            </script>
        </body>
        </html>
        """
    return (
        template
        .replace("__LOGO__", html.escape(logo_src, quote=True))
        .replace("__FALLBACK__", html.escape(fallback_data, quote=True))
        .replace("__PLATFORM__", html.escape(platform_name))
        .replace("__OPERATOR__", html.escape(operator_name))
        .replace("__TURNSTILE__", html.escape(turnstile_endpoint))
    )


def get_request_host():
    return (request.host or "").split(":", 1)[0].strip().lower()


def is_request_secure():
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    if forwarded_proto:
        return forwarded_proto == "https"
    return request.is_secure


def get_auth_token_from_request():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return (request.cookies.get(SESSION_COOKIE_NAME, "") or "").strip()


def get_preferred_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return ""


def is_private_or_local_host(hostname):
    normalized = (hostname or "").strip().lower()
    if not normalized:
        return False
    if normalized in {"127.0.0.1", "localhost", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(normalized)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return False


def should_force_https_links(hostname):
    # Default to HTTP on local/private networks unless explicitly enabled.
    flag = (os.getenv("BAUPASS_FORCE_HTTPS_LINKS") or "0").strip().lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    return is_private_or_local_host(hostname)


def get_public_base_url():
    configured = (os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if configured:
        return configured

    if has_request_context() and request.host:
        return f"{request.scheme}://{request.host}"

    preferred_ip = get_preferred_local_ip() or "127.0.0.1"
    port = (os.getenv("PORT") or "8000").strip() or "8000"
    scheme = "https" if get_ssl_context_from_env() else "http"
    default_port = "443" if scheme == "https" else "80"
    port_suffix = "" if port == default_port else f":{port}"
    return f"{scheme}://{preferred_ip}{port_suffix}"


def should_use_cross_site_cookie():
    origin = (request.headers.get("Origin") or "").strip().rstrip("/")
    current_origin = f"{request.scheme}://{request.host}".rstrip("/")
    return bool(origin) and origin != current_origin and is_request_secure()


def get_ssl_context_from_env():
    ssl_mode = (os.getenv("BAUPASS_SSL_MODE") or "").strip().lower()
    if ssl_mode in {"", "0", "false", "off", "disabled", "none"}:
        return None
    if ssl_mode in {"adhoc", "enabled", "https"}:
        return "adhoc"
    if ssl_mode == "cert":
        cert_file = (os.getenv("BAUPASS_SSL_CERT") or "").strip()
        key_file = (os.getenv("BAUPASS_SSL_KEY") or "").strip()
        if not cert_file or not key_file:
            raise RuntimeError("BAUPASS_SSL_MODE=cert requires BAUPASS_SSL_CERT and BAUPASS_SSL_KEY")
        return cert_file, key_file
    raise RuntimeError(f"Unsupported BAUPASS_SSL_MODE: {ssl_mode}")


def get_client_ip():
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    return forwarded.split(",", 1)[0].strip() if forwarded else (request.remote_addr or "local")


def parse_ip_whitelist(raw):
    return [item.strip() for item in (raw or "").replace(";", ",").split(",") if item.strip()]


def ip_allowed(ip_value, whitelist):
    if not whitelist:
        return True
    try:
        ip_obj = ipaddress.ip_address(ip_value)
    except ValueError:
        return False
    for rule in whitelist:
        try:
            if "/" in rule:
                if ip_obj in ipaddress.ip_network(rule, strict=False):
                    return True
            elif ip_obj == ipaddress.ip_address(rule):
                return True
        except ValueError:
            continue
    return False


def init_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=30000")
    cur = db.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            platform_name TEXT NOT NULL,
            operator_name TEXT NOT NULL,
            turnstile_endpoint TEXT NOT NULL,
            rental_model TEXT NOT NULL,
            invoice_logo_data TEXT NOT NULL DEFAULT '',
            invoice_primary_color TEXT NOT NULL DEFAULT '#0f4c5c',
            invoice_accent_color TEXT NOT NULL DEFAULT '#e36414',
            invoice_iban TEXT NOT NULL DEFAULT '',
            invoice_bic TEXT NOT NULL DEFAULT '',
            invoice_bank_name TEXT NOT NULL DEFAULT '',
            invoice_tax_id TEXT NOT NULL DEFAULT '',
            invoice_vat_id TEXT NOT NULL DEFAULT '',
            invoice_operator_street TEXT NOT NULL DEFAULT '',
            invoice_operator_zip_city TEXT NOT NULL DEFAULT '',
            invoice_operator_phone TEXT NOT NULL DEFAULT '',
            invoice_operator_website TEXT NOT NULL DEFAULT '',
            smtp_host TEXT NOT NULL DEFAULT '',
            smtp_port INTEGER NOT NULL DEFAULT 587,
            smtp_username TEXT NOT NULL DEFAULT '',
            smtp_password TEXT NOT NULL DEFAULT '',
            smtp_sender_email TEXT NOT NULL DEFAULT '',
            smtp_sender_name TEXT NOT NULL DEFAULT 'BauPass Control',
            smtp_use_tls INTEGER NOT NULL DEFAULT 1,
            resend_api_key TEXT NOT NULL DEFAULT '',
            resend_from_email TEXT NOT NULL DEFAULT '',
            brevo_api_key TEXT NOT NULL DEFAULT '',
            brevo_from_email TEXT NOT NULL DEFAULT '',
            admin_ip_whitelist TEXT NOT NULL DEFAULT '',
            enforce_tenant_domain INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS companies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            billing_email TEXT NOT NULL DEFAULT '',
            document_email TEXT NOT NULL DEFAULT '',
            access_host TEXT NOT NULL DEFAULT '',
            branding_preset TEXT NOT NULL DEFAULT 'construction',
            plan TEXT NOT NULL,
            status TEXT NOT NULL,
            deleted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            company_id TEXT,
            twofa_secret TEXT,
            twofa_enabled INTEGER NOT NULL DEFAULT 0,
            api_key_hash TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(company_id) REFERENCES companies(id)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS otp_codes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            actor_user_id TEXT,
            actor_role TEXT,
            company_id TEXT,
            target_type TEXT,
            target_id TEXT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS system_alerts (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workers (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            subcompany_id TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            insurance_number TEXT NOT NULL,
            worker_type TEXT NOT NULL DEFAULT 'worker',
            role TEXT NOT NULL,
            site TEXT NOT NULL,
            valid_until TEXT NOT NULL,
            visitor_company TEXT NOT NULL DEFAULT '',
            visit_purpose TEXT NOT NULL DEFAULT '',
            host_name TEXT NOT NULL DEFAULT '',
            visit_end_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            photo_data TEXT NOT NULL,
            badge_id TEXT NOT NULL,
            badge_pin_hash TEXT NOT NULL DEFAULT '',
            physical_card_id TEXT,
            deleted_at TEXT,
            FOREIGN KEY(company_id) REFERENCES companies(id),
            FOREIGN KEY(subcompany_id) REFERENCES subcompanies(id)
        );

        CREATE TABLE IF NOT EXISTS subcompanies (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            name TEXT NOT NULL,
            contact TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'aktiv',
            deleted_at TEXT,
            FOREIGN KEY(company_id) REFERENCES companies(id)
        );

        CREATE TABLE IF NOT EXISTS access_logs (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            gate TEXT NOT NULL,
            note TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(worker_id) REFERENCES workers(id)
        );

        CREATE TABLE IF NOT EXISTS worker_app_tokens (
            token TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            created_by_user_id TEXT,
            FOREIGN KEY(worker_id) REFERENCES workers(id)
        );

        CREATE TABLE IF NOT EXISTS worker_app_sessions (
            token TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(worker_id) REFERENCES workers(id)
        );

        CREATE TABLE IF NOT EXISTS day_close_acknowledgements (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            company_id TEXT,
            acknowledged_by_user_id TEXT NOT NULL,
            comment TEXT NOT NULL,
            open_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(acknowledged_by_user_id) REFERENCES users(id),
            FOREIGN KEY(company_id) REFERENCES companies(id)
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY,
            invoice_number TEXT NOT NULL,
            company_id TEXT NOT NULL,
            recipient_email TEXT NOT NULL,
            invoice_date TEXT NOT NULL,
            invoice_period TEXT NOT NULL,
            description TEXT NOT NULL,
            net_amount REAL NOT NULL,
            vat_rate REAL NOT NULL,
            vat_amount REAL NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            sent_at TEXT,
            rendered_html TEXT NOT NULL,
            created_by_user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(id),
            FOREIGN KEY(created_by_user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS invoice_send_attempts (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            outcome TEXT NOT NULL,
            error_message TEXT NOT NULL DEFAULT '',
            actor_label TEXT NOT NULL DEFAULT 'system',
            next_retry_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id)
        );

        CREATE TABLE IF NOT EXISTS invoice_dead_letters (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id)
        );

        CREATE TABLE IF NOT EXISTS operation_approvals (
            id TEXT PRIMARY KEY,
            action_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_by_user_id TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            decided_by_user_id TEXT,
            decided_at TEXT,
            decision_note TEXT NOT NULL DEFAULT '',
            execution_result_json TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(requested_by_user_id) REFERENCES users(id),
            FOREIGN KEY(decided_by_user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS email_inbox (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL DEFAULT '',
            from_addr TEXT NOT NULL DEFAULT '',
            to_addr TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            body_text TEXT NOT NULL DEFAULT '',
            matched_company_id TEXT,
            received_at TEXT NOT NULL,
            processed INTEGER NOT NULL DEFAULT 0,
            dismissed INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(matched_company_id) REFERENCES companies(id)
        );

        CREATE TABLE IF NOT EXISTS email_attachments (
            id TEXT PRIMARY KEY,
            inbox_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL DEFAULT '',
            file_size INTEGER NOT NULL DEFAULT 0,
            file_data BLOB,
            assigned_worker_id TEXT,
            assigned_doc_type TEXT,
            saved_path TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(inbox_id) REFERENCES email_inbox(id)
        );

        CREATE TABLE IF NOT EXISTS worker_documents (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            source_email_from TEXT NOT NULL DEFAULT '',
            source_inbox_id TEXT,
            uploaded_by_user_id TEXT,
            created_at TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(worker_id) REFERENCES workers(id)
        );
        """
    )

    setting_exists = cur.execute("SELECT id FROM settings WHERE id = 1").fetchone()
    if not setting_exists:
        cur.execute(
            """
            INSERT INTO settings (
                id, platform_name, operator_name, turnstile_endpoint, rental_model,
                invoice_logo_data, invoice_primary_color, invoice_accent_color,
                invoice_iban, invoice_bic, invoice_bank_name, invoice_tax_id, invoice_vat_id,
                invoice_operator_street, invoice_operator_zip_city, invoice_operator_phone, invoice_operator_website,
                smtp_host, smtp_port, smtp_username, smtp_password, smtp_sender_email, smtp_sender_name, smtp_use_tls,
                resend_api_key, resend_from_email, brevo_api_key, brevo_from_email,
                admin_ip_whitelist, enforce_tenant_domain
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("BauPass Control", "Deine Betriebsfirma", "", "tageskarte", "", "#0f4c5c", "#e36414", "", "", "", "", "", "", "", "", "", "", 587, "", "", "", "BauPass Control", 1, "", "", "", "", "", 0),
        )

    settings_columns = [row[1] for row in cur.execute("PRAGMA table_info(settings)").fetchall()]
    if "invoice_logo_data" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_logo_data TEXT NOT NULL DEFAULT ''")
    if "invoice_primary_color" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_primary_color TEXT NOT NULL DEFAULT '#0f4c5c'")
    if "invoice_accent_color" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_accent_color TEXT NOT NULL DEFAULT '#e36414'")
    if "invoice_iban" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_iban TEXT NOT NULL DEFAULT ''")
    if "invoice_bic" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_bic TEXT NOT NULL DEFAULT ''")
    if "invoice_bank_name" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_bank_name TEXT NOT NULL DEFAULT ''")
    if "invoice_tax_id" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_tax_id TEXT NOT NULL DEFAULT ''")
    if "invoice_vat_id" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_vat_id TEXT NOT NULL DEFAULT ''")
    if "invoice_operator_street" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_operator_street TEXT NOT NULL DEFAULT ''")
    if "invoice_operator_zip_city" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_operator_zip_city TEXT NOT NULL DEFAULT ''")
    if "invoice_operator_phone" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_operator_phone TEXT NOT NULL DEFAULT ''")
    if "invoice_operator_website" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_operator_website TEXT NOT NULL DEFAULT ''")
    if "invoice_operator_email" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_operator_email TEXT NOT NULL DEFAULT ''")
    if "invoice_email_subject" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_email_subject TEXT NOT NULL DEFAULT ''")
    if "invoice_email_intro" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_email_intro TEXT NOT NULL DEFAULT ''")
    if "smtp_host" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN smtp_host TEXT NOT NULL DEFAULT ''")
    if "smtp_port" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN smtp_port INTEGER NOT NULL DEFAULT 587")
    if "smtp_username" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN smtp_username TEXT NOT NULL DEFAULT ''")
    if "smtp_password" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN smtp_password TEXT NOT NULL DEFAULT ''")
    if "smtp_sender_email" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN smtp_sender_email TEXT NOT NULL DEFAULT ''")
    if "smtp_sender_name" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN smtp_sender_name TEXT NOT NULL DEFAULT 'BauPass Control'")
    if "smtp_use_tls" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN smtp_use_tls INTEGER NOT NULL DEFAULT 1")
    if "admin_ip_whitelist" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN admin_ip_whitelist TEXT NOT NULL DEFAULT ''")
    if "enforce_tenant_domain" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN enforce_tenant_domain INTEGER NOT NULL DEFAULT 0")

    company_exists = cur.execute("SELECT id FROM companies LIMIT 1").fetchone()
    if not company_exists:
        company_id = "cmp-default"
        cur.execute(
            "INSERT INTO companies (id, name, contact, plan, status) VALUES (?, ?, ?, ?, ?)",
            (company_id, "Muster Bau GmbH", "Sabine Keller", "tageskarte", "test"),
        )

        users = [
            ("usr-superadmin", "superadmin", generate_password_hash("1234"), "Systemleitung", "superadmin", None),
            ("usr-company", "firma", generate_password_hash("1234"), "Firmen-Admin", "company-admin", company_id),
            ("usr-turnstile", "drehkreuz", generate_password_hash("1234"), "Drehkreuz Terminal", "turnstile", company_id),
        ]
        cur.executemany(
            "INSERT INTO users (id, username, password_hash, name, role, company_id) VALUES (?, ?, ?, ?, ?, ?)",
            users,
        )

    # Migration fuer alte Datenbankversionen mit Klartextpasswoertern.
    columns = [row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "password_hash" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
        columns = [row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()]

    if "password" in columns:
        rows = cur.execute("SELECT id, password, password_hash FROM users").fetchall()
        for row in rows:
            if row[2]:
                continue
            current = row[1] or "1234"
            hashed = current if current.startswith("pbkdf2:") or current.startswith("scrypt:") else generate_password_hash(current)
            cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, row[0]))
    else:
        rows = cur.execute("SELECT id, password_hash FROM users").fetchall()
        for row in rows:
            if not row[1]:
                cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash("1234"), row[0]))

    if "twofa_secret" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN twofa_secret TEXT")
    if "twofa_enabled" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN twofa_enabled INTEGER NOT NULL DEFAULT 0")
    if "email" not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")

    company_columns = [row[1] for row in cur.execute("PRAGMA table_info(companies)").fetchall()]
    if "deleted_at" not in company_columns:
        cur.execute("ALTER TABLE companies ADD COLUMN deleted_at TEXT")
    if "billing_email" not in company_columns:
        cur.execute("ALTER TABLE companies ADD COLUMN billing_email TEXT NOT NULL DEFAULT ''")
    if "access_host" not in company_columns:
        cur.execute("ALTER TABLE companies ADD COLUMN access_host TEXT NOT NULL DEFAULT ''")
    if "document_email" not in company_columns:
        cur.execute("ALTER TABLE companies ADD COLUMN document_email TEXT NOT NULL DEFAULT ''")
    if "branding_preset" not in company_columns:
        cur.execute("ALTER TABLE companies ADD COLUMN branding_preset TEXT NOT NULL DEFAULT 'construction'")

    worker_columns = [row[1] for row in cur.execute("PRAGMA table_info(workers)").fetchall()]
    if "deleted_at" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN deleted_at TEXT")
    if "subcompany_id" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN subcompany_id TEXT")
    if "worker_type" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN worker_type TEXT NOT NULL DEFAULT 'worker'")
    if "visitor_company" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN visitor_company TEXT NOT NULL DEFAULT ''")
    if "visit_purpose" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN visit_purpose TEXT NOT NULL DEFAULT ''")
    if "host_name" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN host_name TEXT NOT NULL DEFAULT ''")
    if "visit_end_at" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN visit_end_at TEXT NOT NULL DEFAULT ''")
    if "badge_pin_hash" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN badge_pin_hash TEXT NOT NULL DEFAULT ''")
    if "physical_card_id" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN physical_card_id TEXT")
    if "site_latitude" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN site_latitude REAL")
    if "site_longitude" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN site_longitude REAL")

    if "worker_app_enabled" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN worker_app_enabled INTEGER NOT NULL DEFAULT 1")

    # IMAP-Einstellungen fuer Dokumenten-Postfach
    if "imap_host" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN imap_host TEXT NOT NULL DEFAULT ''")
    if "imap_port" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN imap_port INTEGER NOT NULL DEFAULT 993")
    if "imap_username" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN imap_username TEXT NOT NULL DEFAULT ''")
    if "imap_password" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN imap_password TEXT NOT NULL DEFAULT ''")
    if "imap_folder" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN imap_folder TEXT NOT NULL DEFAULT 'INBOX'")
    if "imap_use_ssl" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN imap_use_ssl INTEGER NOT NULL DEFAULT 1")
    if "impressum_text" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN impressum_text TEXT NOT NULL DEFAULT ''")
    if "datenschutz_text" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN datenschutz_text TEXT NOT NULL DEFAULT ''")
    if "resend_api_key" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN resend_api_key TEXT NOT NULL DEFAULT ''")
    if "resend_from_email" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN resend_from_email TEXT NOT NULL DEFAULT ''")
    if "brevo_api_key" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN brevo_api_key TEXT NOT NULL DEFAULT ''")
    if "brevo_from_email" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN brevo_from_email TEXT NOT NULL DEFAULT ''")
    if "admin_summary_email" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN admin_summary_email TEXT NOT NULL DEFAULT ''")
    if "worker_expiry_warn_days" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN worker_expiry_warn_days INTEGER NOT NULL DEFAULT 7")

    inbox_columns = [row[1] for row in cur.execute("PRAGMA table_info(email_inbox)").fetchall()]
    if "to_addr" not in inbox_columns:
        cur.execute("ALTER TABLE email_inbox ADD COLUMN to_addr TEXT NOT NULL DEFAULT ''")
    if "matched_company_id" not in inbox_columns:
        cur.execute("ALTER TABLE email_inbox ADD COLUMN matched_company_id TEXT")

    system_alert_columns = [row[1] for row in cur.execute("PRAGMA table_info(system_alerts)").fetchall()]
    if "resolved_at" not in system_alert_columns:
        cur.execute("ALTER TABLE system_alerts ADD COLUMN resolved_at TEXT")

    session_columns = [row[1] for row in cur.execute("PRAGMA table_info(sessions)").fetchall()]
    if "last_seen" not in session_columns:
        cur.execute("ALTER TABLE sessions ADD COLUMN last_seen TEXT")
    if "support_read_only" not in session_columns:
        cur.execute("ALTER TABLE sessions ADD COLUMN support_read_only INTEGER NOT NULL DEFAULT 0")
    if "support_company_name" not in session_columns:
        cur.execute("ALTER TABLE sessions ADD COLUMN support_company_name TEXT NOT NULL DEFAULT ''")
    if "support_actor_name" not in session_columns:
        cur.execute("ALTER TABLE sessions ADD COLUMN support_actor_name TEXT NOT NULL DEFAULT ''")
    if "preview_company_id" not in session_columns:
        cur.execute("ALTER TABLE sessions ADD COLUMN preview_company_id TEXT")

    invoice_columns = [row[1] for row in cur.execute("PRAGMA table_info(invoices)").fetchall()]
    if "due_date" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN due_date TEXT")
    if "paid_at" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN paid_at TEXT")
    if "auto_suspend_triggered_at" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN auto_suspend_triggered_at TEXT")
    if "reminder_stage" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN reminder_stage INTEGER NOT NULL DEFAULT 0")
    if "last_reminder_sent_at" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN last_reminder_sent_at TEXT")
    if "last_reminder_error" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN last_reminder_error TEXT")
    if "send_attempt_count" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN send_attempt_count INTEGER NOT NULL DEFAULT 0")
    if "last_send_attempt_at" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN last_send_attempt_at TEXT")
    if "next_retry_at" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN next_retry_at TEXT")
    if "items_json" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN items_json TEXT NOT NULL DEFAULT ''")
    if "discount_amount" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN discount_amount REAL NOT NULL DEFAULT 0")

    operation_approval_columns = [row[1] for row in cur.execute("PRAGMA table_info(operation_approvals)").fetchall()]
    if "expires_at" not in operation_approval_columns:
        cur.execute("ALTER TABLE operation_approvals ADD COLUMN expires_at TEXT")
        cur.execute(
            "UPDATE operation_approvals SET expires_at = ? WHERE COALESCE(TRIM(expires_at), '') = ''",
            ((utc_now() + timedelta(minutes=OPERATION_APPROVAL_EXPIRY_MINUTES)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),),
        )

    # Rechnungsnummern pro Firma eindeutig halten: Alt-Duplikate bereinigen und Unique-Index setzen.
    duplicates = cur.execute(
        """
        SELECT company_id, invoice_number, COUNT(*) AS c
        FROM invoices
        WHERE invoice_number IS NOT NULL AND TRIM(invoice_number) <> ''
        GROUP BY company_id, invoice_number
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    for dup in duplicates:
        rows = cur.execute(
            """
            SELECT id, invoice_number
            FROM invoices
            WHERE company_id = ? AND invoice_number = ?
            ORDER BY created_at ASC, id ASC
            """,
            (dup[0], dup[1]),
        ).fetchall()
        for idx, row in enumerate(rows[1:], start=2):
            base = str(row[1] or "RE").strip() or "RE"
            candidate = f"{base}-{idx}"
            suffix = idx
            while cur.execute(
                "SELECT 1 FROM invoices WHERE company_id = ? AND invoice_number = ? AND id <> ?",
                (dup[0], candidate, row[0]),
            ).fetchone():
                suffix += 1
                candidate = f"{base}-{suffix}"
            cur.execute("UPDATE invoices SET invoice_number = ? WHERE id = ?", (candidate, row[0]))

    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_company_invoice_number_unique ON invoices(company_id, invoice_number)"
    )

    # ── Neu: is_active fuer User (Drehkreuz deaktivierbar) ──
    user_columns = [row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "is_active" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        user_columns = [row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "api_key_hash" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN api_key_hash TEXT NOT NULL DEFAULT ''")

    # ── Neu: Ablaufdatum fuer Mitarbeiterdokumente ──
    doc_columns = [row[1] for row in cur.execute("PRAGMA table_info(worker_documents)").fetchall()]
    if "expiry_date" not in doc_columns:
        cur.execute("ALTER TABLE worker_documents ADD COLUMN expiry_date TEXT")

    # ── Neu: Passwort-Reset-Token Tabelle ──
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    # ── Neu: Hardware-Geraete (Smart-Boxes / OSDP-Controller) ──
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            name TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            device_type TEXT NOT NULL DEFAULT 'osdp',
            api_key_hash TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(company_id) REFERENCES companies(id)
        )
        """
    )

    # Bestehende Installationen nachziehen, falls die Tabelle schon vor der finalen
    # Geraete-Struktur angelegt wurde (verhindert 500 bei SELECT/Serialize).
    device_columns = [row[1] for row in cur.execute("PRAGMA table_info(devices)").fetchall()]
    if "location" not in device_columns:
        cur.execute("ALTER TABLE devices ADD COLUMN location TEXT NOT NULL DEFAULT ''")
    if "device_type" not in device_columns:
        cur.execute("ALTER TABLE devices ADD COLUMN device_type TEXT NOT NULL DEFAULT 'osdp'")
    if "api_key_hash" not in device_columns:
        cur.execute("ALTER TABLE devices ADD COLUMN api_key_hash TEXT NOT NULL DEFAULT ''")
    if "last_seen_at" not in device_columns:
        cur.execute("ALTER TABLE devices ADD COLUMN last_seen_at TEXT")
    if "created_at" not in device_columns:
        cur.execute("ALTER TABLE devices ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")

    # Populate Resend key cache from DB so _get_resend_api_key_and_source() works without
    # opening a second connection. Safe here because we're still in init_db's raw connection.
    try:
        db.row_factory = sqlite3.Row
        _cache_row = db.execute("SELECT resend_api_key, resend_from_email, brevo_api_key, brevo_from_email FROM settings WHERE id = 1").fetchone()
        if _cache_row:
            _resend_key_cache["key"] = str(_cache_row["resend_api_key"] or "").strip()
            _resend_key_cache["from_email"] = str(_cache_row["resend_from_email"] or "").strip()
            _resend_key_cache["brevo_key"] = str(_cache_row["brevo_api_key"] or "").strip()
            _resend_key_cache["brevo_from_email"] = str(_cache_row["brevo_from_email"] or "").strip()
    except Exception:
        pass

    db.commit()
    db.close()


try:
    init_db()
except Exception as _init_db_exc:
    import traceback as _tb
    print(f"[baupass] CRITICAL: init_db() failed: {_init_db_exc}", flush=True)
    _tb.print_exc()
    raise


def row_to_dict(row):
    return dict(row) if row is not None else None


def create_turnstile_api_key():
    return secrets.token_urlsafe(32)


def hash_turnstile_api_key(raw_key):
    return generate_password_hash(raw_key)


def find_turnstile_by_api_key(db, raw_key):
    if not raw_key:
        return None
    candidates = db.execute(
        "SELECT * FROM users WHERE role = 'turnstile' AND COALESCE(api_key_hash, '') != '' AND COALESCE(is_active, 1) = 1"
    ).fetchall()
    for candidate in candidates:
        if check_password_hash(candidate["api_key_hash"], raw_key):
            return candidate
    return None


def serialize_user(user_row):
    if not user_row:
        return None
    support_read_only = False
    support_company_name = ""
    support_actor_name = ""
    if hasattr(user_row, "keys"):
        keys = set(user_row.keys())
        support_read_only = "support_read_only" in keys and bool(user_row["support_read_only"])
        support_company_name = user_row["support_company_name"] if "support_company_name" in keys and user_row["support_company_name"] else ""
        support_actor_name = user_row["support_actor_name"] if "support_actor_name" in keys and user_row["support_actor_name"] else ""
    preview_company_id = ""
    if hasattr(user_row, "keys") and "preview_company_id" in user_row.keys():
        preview_company_id = user_row["preview_company_id"] or ""
    return {
        "id": user_row["id"],
        "username": user_row["username"],
        "name": user_row["name"],
        "role": user_row["role"],
        "company_id": user_row["company_id"],
        "twofa_enabled": int(user_row["twofa_enabled"]),
        "email": user_row["email"] if hasattr(user_row, "keys") and "email" in set(user_row.keys()) else "",
        "support_read_only": support_read_only,
        "support_company_name": support_company_name,
        "support_actor_name": support_actor_name,
        "preview_company_id": preview_company_id,
    }


def log_audit(event_type, message, target_type=None, target_id=None, company_id=None, actor=None):
    db = get_db()
    actor_user_id = actor["id"] if actor else None
    actor_role = actor["role"] if actor else None
    resolved_company = company_id if company_id is not None else (actor.get("company_id") if actor else None)
    db.execute(
        """
        INSERT INTO audit_logs (id, event_type, actor_user_id, actor_role, company_id, target_type, target_id, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"aud-{secrets.token_hex(8)}",
            event_type,
            actor_user_id,
            actor_role,
            resolved_company,
            target_type,
            target_id,
            message,
            now_iso(),
        ),
    )
    db.commit()


def is_read_only_support_session(session_row):
    if not session_row:
        return False
    if hasattr(session_row, "keys") and "support_read_only" in session_row.keys():
        return bool(session_row["support_read_only"])
    return False


def is_read_only_support_request_allowed():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return True
    return request.path in {"/api/logout", "/api/me/heartbeat"}


def is_tenant_host_valid(db, user):
    if not user or user.get("role") == "superadmin":
        return True
    setting = db.execute("SELECT enforce_tenant_domain FROM settings WHERE id = 1").fetchone()
    if not setting or int(setting["enforce_tenant_domain"]) != 1:
        return True
    company_id = user.get("company_id")
    if not company_id:
        return True
    company = db.execute("SELECT access_host FROM companies WHERE id = ?", (company_id,)).fetchone()
    required_host = (company["access_host"] if company else "").strip().lower()
    if not required_host:
        return True
    return get_request_host() == required_host


def require_auth(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        token = get_auth_token_from_request()
        if not token:
            return jsonify({"error": "unauthorized"}), 401
        db = get_db()
        session = db.execute(
            "SELECT user_id, expires_at, support_read_only, support_company_name, support_actor_name, preview_company_id FROM sessions WHERE token = ?",
            (token,),
        ).fetchone()
        if not session:
            return jsonify({"error": "invalid_session"}), 401

        if session["expires_at"] < now_iso():
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            db.commit()
            return jsonify({"error": "session_expired"}), 401

        user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not user:
            return jsonify({"error": "invalid_user"}), 401

        if int(user["is_active"] if "is_active" in user.keys() else 1) == 0:
            return jsonify({"error": "account_disabled"}), 403

        user_payload = row_to_dict(user)
        user_payload["support_read_only"] = is_read_only_support_session(session)
        user_payload["support_company_name"] = session["support_company_name"] or ""
        user_payload["support_actor_name"] = session["support_actor_name"] or ""
        user_payload["preview_company_id"] = session["preview_company_id"] or ""

        if not is_tenant_host_valid(db, user_payload):
            return jsonify({"error": "forbidden_tenant_host"}), 403

        if user_payload.get("role") != "superadmin":
            company_error = get_company_access_error(db, user_payload.get("company_id"))
            if company_error:
                db.execute("DELETE FROM sessions WHERE token = ?", (token,))
                db.commit()
                return jsonify(company_error), 403

        if user_payload.get("role") in ["superadmin", "company-admin"]:
            settings_row = db.execute("SELECT admin_ip_whitelist FROM settings WHERE id = 1").fetchone()
            whitelist = parse_ip_whitelist(settings_row["admin_ip_whitelist"] if settings_row else "")
            if whitelist and not ip_allowed(get_client_ip(), whitelist):
                return jsonify({"error": "admin_ip_not_allowed"}), 403

        if is_read_only_support_session(session) and not is_read_only_support_request_allowed():
            return jsonify({"error": "support_session_read_only"}), 403

        db.execute("UPDATE sessions SET expires_at = ? WHERE token = ?", (expiry_iso(), token))
        db.commit()

        g.current_user = user_payload
        g.token = token
        g.current_session = row_to_dict(session)
        g.preview_company_id = user_payload["preview_company_id"] if user_payload.get("role") == "superadmin" else ""
        return handler(*args, **kwargs)

    return wrapper


def require_roles(*roles):
    def decorator(handler):
        @wraps(handler)
        def wrapper(*args, **kwargs):
            user = g.current_user
            if user["role"] not in roles:
                return jsonify({"error": "forbidden"}), 403
            return handler(*args, **kwargs)

        return wrapper

    return decorator


def require_worker_session(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "unauthorized"}), 401

        token = auth_header.split(" ", 1)[1]
        db = get_db()
        purge_expired_worker_app_sessions(db)
        db.commit()
        session = db.execute("SELECT worker_id, expires_at FROM worker_app_sessions WHERE token = ?", (token,)).fetchone()
        if not session:
            return jsonify({"error": "invalid_worker_session"}), 401

        if session["expires_at"] < now_iso():
            db.execute("DELETE FROM worker_app_sessions WHERE token = ?", (token,))
            db.commit()
            return jsonify({"error": "worker_session_expired"}), 401

        worker = db.execute("SELECT * FROM workers WHERE id = ?", (session["worker_id"],)).fetchone()
        if not worker or worker["deleted_at"]:
            return jsonify({"error": "worker_not_available"}), 401

        company_error = get_company_access_error(db, worker["company_id"])
        if company_error:
            db.execute("DELETE FROM worker_app_sessions WHERE token = ?", (token,))
            db.commit()
            return jsonify(company_error), 403

        g.worker = row_to_dict(worker)
        g.worker_token = token
        g.worker_session_expires_at = session["expires_at"]
        return handler(*args, **kwargs)

    return wrapper


# --- API: Foto-Upload für Mitarbeiter (nach require_worker_session und app Definitionen!) ---
@app.post("/api/worker-app/photo")
@require_worker_session
def update_worker_photo():
    payload = request.get_json(silent=True) or {}
    try:
        photo_data = sanitize_photo_data(payload.get("photoData", ""), required=True)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    db = get_db()
    db.execute("UPDATE workers SET photo_data = ? WHERE id = ?", (photo_data, g.worker["id"]))
    db.commit()
    return jsonify({"ok": True})

def visible_company_clause(user):
    if user["role"] == "superadmin":
        preview_id = getattr(g, "preview_company_id", "") if has_request_context() else ""
        if preview_id:
            return " WHERE id = ?", [preview_id]
        return "", []
    return " WHERE id = ?", [user["company_id"]]


def check_and_apply_overdue_suspensions(db):
    """Checks for overdue unpaid invoices and auto-locks companies."""
    today = now_iso().split("T")[0]
    overdue_rows = db.execute(
        """
        SELECT DISTINCT inv.company_id FROM invoices AS inv
        WHERE inv.status IN ('sent', 'overdue')
          AND inv.paid_at IS NULL
          AND inv.due_date IS NOT NULL
                    AND DATE(inv.due_date) <= DATE(?, ?)
        """,
                (today, f"-{AUTO_SUSPEND_GRACE_DAYS} day"),
    ).fetchall()

    suspended_companies = []
    for row in overdue_rows:
        company_id = row[0]
        company = db.execute("SELECT id, name, status FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not company:
            continue
        if company["status"] != "gesperrt":
            db.execute(
                "UPDATE companies SET status = ? WHERE id = ?",
                ("gesperrt", company_id),
            )
            db.execute(
                "UPDATE invoices SET auto_suspend_triggered_at = ? WHERE company_id = ? AND paid_at IS NULL AND auto_suspend_triggered_at IS NULL",
                (now_iso(), company_id),
            )
            log_audit(
                "company.auto_suspended_overdue_invoice",
                f"Firma '{company['name']}' automatically suspended due to overdue invoice",
                target_type="company",
                target_id=company_id,
            )
            suspended_companies.append(company_id)

    if suspended_companies:
        db.commit()
    return suspended_companies


def send_payment_reminder_email(invoice_row, company_row, settings_row, stage, days_until_due):
    smtp_host = (settings_row["smtp_host"] or "").strip()
    smtp_sender = (settings_row["smtp_sender_email"] or "").strip()
    if not smtp_host or not smtp_sender:
        return False, "SMTP ist nicht konfiguriert"

    stage_label = {1: "Erinnerung", 2: "Letzte Erinnerung", 3: "Überfällig"}.get(stage, "Erinnerung")
    due_label = invoice_row["due_date"] or "-"

    if days_until_due < 0:
        timing_text = f"seit {abs(days_until_due)} Tag(en) überfällig"
    elif days_until_due == 0:
        timing_text = "heute faellig"
    else:
        timing_text = f"in {days_until_due} Tag(en) fällig"

    text_body = (
        f"Guten Tag,\n\n"
        f"dies ist eine Zahlungs-{stage_label.lower()} für die Rechnung {invoice_row['invoice_number']} "
        f"({company_row['name']}).\n"
        f"Fälligkeit: {due_label} ({timing_text})\n"
        f"Offener Betrag: {float(invoice_row['total_amount'] or 0):.2f} EUR\n\n"
        f"Bitte begleichen Sie den Betrag zeitnah, um eine Sperrung zu vermeiden.\n\n"
        f"Viele Grüße\n{settings_row['operator_name']}"
    )
    message = EmailMessage()
    message["Subject"] = f"{stage_label}: Rechnung {invoice_row['invoice_number']} ({timing_text})"
    message["From"] = f"{settings_row['smtp_sender_name']} <{smtp_sender}>"
    message["To"] = invoice_row["recipient_email"]
    message.set_content(text_body)

    try:
        with smtplib.SMTP(smtp_host, int(settings_row["smtp_port"] or 587), timeout=20) as smtp:
            if int(settings_row["smtp_use_tls"] or 0) == 1:
                smtp.starttls()
            smtp_username = (settings_row["smtp_username"] or "").strip()
            if smtp_username:
                smtp.login(smtp_username, settings_row["smtp_password"] or "")
            smtp.send_message(message)
        return True, ""
    except Exception as exc:
        fallback_ok, fallback_error, _provider_used = _send_via_any_api(
            subject=str(message["Subject"]),
            sender_email=smtp_sender,
            sender_name=settings_row["smtp_sender_name"] or "",
            recipient=invoice_row["recipient_email"],
            text_body=text_body,
            html_body="",
        )
        if fallback_ok:
            return True, ""
        return False, f"{exc} | API-Fallback: {fallback_error}"


@contextmanager
def _smtp_connect(host, port, use_tls):
    """Context manager: connects to SMTP, auto-selects SSL (port 465) vs STARTTLS."""
    port = int(port or 587)
    use_ssl = port == 465
    use_tls_flag = int(use_tls or 0) == 1
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
            yield smtp
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls_flag:
                smtp.starttls()
            yield smtp


def _run_smtp_diagnostics(smtp_settings):
    host = smtp_settings["smtp_host"]
    port = int(smtp_settings["smtp_port"] or 587)
    use_tls = int(smtp_settings["smtp_use_tls"] or 0) == 1
    smtp_username = smtp_settings["smtp_username"]
    smtp_password = smtp_settings["smtp_password"]
    stage = "init"
    result = {
        "ok": False,
        "host": host,
        "port": port,
        "useTls": use_tls,
        "hasUsername": bool(smtp_username),
        "hasPassword": bool(str(smtp_password or "").strip()),
        "hasSender": bool(smtp_settings["smtp_sender_email"]),
    }
    try:
        stage = "dns"
        result["resolvedAddresses"] = len(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))

        if port == 465:
            stage = "connect_ssl"
            with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                stage = "ehlo_ssl"
                smtp.ehlo()
                if smtp_username:
                    stage = "auth"
                    smtp.login(smtp_username, smtp_password)
        else:
            stage = "connect"
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                stage = "ehlo"
                smtp.ehlo()
                if use_tls:
                    stage = "starttls"
                    smtp.starttls()
                    stage = "ehlo_tls"
                    smtp.ehlo()
                if smtp_username:
                    stage = "auth"
                    smtp.login(smtp_username, smtp_password)
        result["ok"] = True
        result["stage"] = "done"
        return result
    except Exception as exc:
        result["stage"] = stage
        result["errorType"] = exc.__class__.__name__
        result["error"] = str(exc)
        return result


def _normalize_env_value(raw):
    value = str(raw or "").strip()
    if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
        value = value[1:-1].strip()
    return value


def _get_resend_api_key_and_source():
    # Check module-level cache first (populated from DB at startup and after settings save).
    cached_key = _normalize_env_value(_resend_key_cache.get("key") or "")
    if cached_key:
        return cached_key, "db_settings"

    # Fallback: read from DB directly in case cache is stale/empty.
    try:
        with closing(sqlite3.connect(DB_PATH)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT resend_api_key, resend_from_email FROM settings WHERE id = 1").fetchone()
            if row:
                db_key = _normalize_env_value(row["resend_api_key"] or "")
                db_from_email = _normalize_env_value(row["resend_from_email"] or "")
                if db_key:
                    _resend_key_cache["key"] = db_key
                    _resend_key_cache["from_email"] = db_from_email
                    return db_key, "db_settings"
                if db_from_email and not _resend_key_cache.get("from_email"):
                    _resend_key_cache["from_email"] = db_from_email
    except Exception:
        pass

    # Accept common variable names to reduce deployment misconfiguration issues.
    for key_name in (
        "RESEND_API_KEY",
        "RESEND_KEY",
        "RESEND_API_TOKEN",
        "BAUPASS_RESEND_API_KEY",
        "RESEND_APIKEY",
        "RESEND_TOKEN",
    ):
        candidate = _normalize_env_value(os.getenv(key_name))
        if candidate:
            return candidate, key_name

    # Last-resort heuristic: detect any non-empty env var that looks like a Resend key/token.
    for env_name, env_value in os.environ.items():
        upper_name = str(env_name or "").upper()
        if "RESEND" not in upper_name:
            continue
        if not any(token in upper_name for token in ("API_KEY", "APIKEY", "TOKEN", "KEY")):
            continue
        candidate = _normalize_env_value(env_value)
        if candidate:
            return candidate, env_name

    # Extra fallback for unusual variable names (e.g. just "RESEND"):
    # accept values that look like real Resend keys.
    for env_name, env_value in os.environ.items():
        upper_name = str(env_name or "").upper()
        if "RESEND" not in upper_name:
            continue
        candidate = _normalize_env_value(env_value)
        if candidate.startswith("re_"):
            return candidate, env_name

    return "", ""


def _collect_resend_env_presence():
    """Return non-secret visibility into RESEND-related env vars for diagnostics."""
    known_names = [
        "RESEND_API_KEY",
        "RESEND_KEY",
        "RESEND_API_TOKEN",
        "BAUPASS_RESEND_API_KEY",
        "RESEND_APIKEY",
        "RESEND_TOKEN",
        "RESEND_FROM_EMAIL",
        "RESEND_FROM_NAME",
        "RESEND_API_URL",
    ]
    details = []
    for name in known_names:
        raw = os.getenv(name)
        value = _normalize_env_value(raw)
        details.append({
            "name": name,
            "set": bool(value),
            "length": len(value),
        })

    dynamic_names = []
    for env_name, env_value in os.environ.items():
        upper_name = str(env_name or "").upper()
        if "RESEND" not in upper_name:
            continue
        if upper_name in known_names:
            continue
        candidate = _normalize_env_value(env_value)
        dynamic_names.append({
            "name": env_name,
            "set": bool(candidate),
            "length": len(candidate),
        })

    return {"known": details, "dynamic": dynamic_names}


def _send_via_resend(subject, sender_email, sender_name, recipient, text_body, html_body, attachments=None):
    """Send e-mail via Resend API over HTTPS (fallback when SMTP egress is blocked)."""
    api_key, _key_source = _get_resend_api_key_and_source()
    if not api_key:
        return False, "resend_not_configured (expected: RESEND_API_KEY | RESEND_KEY | RESEND_API_TOKEN)"

    endpoint = _normalize_env_value(os.getenv("RESEND_API_URL") or "https://api.resend.com/emails")
    from_email = _normalize_env_value(os.getenv("RESEND_FROM_EMAIL") or "")
    from_name = _normalize_env_value(os.getenv("RESEND_FROM_NAME") or "")
    # Fall back to module-level cache (populated from DB at startup / after settings save).
    if not from_email:
        from_email = _normalize_env_value(_resend_key_cache.get("from_email") or "")
    if not from_email:
        from_email = sender_email or ""
    if not from_name:
        from_name = sender_name or ""
    if not from_email:
        return False, "resend_missing_from_email"
    from_header = f'"{from_name}" <{from_email}>' if from_name else from_email

    payload = {
        "from": from_header,
        "to": [recipient],
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }
    if attachments:
        payload["attachments"] = [
            {
                "filename": str(item.get("filename") or "attachment.bin"),
                "content": str(item.get("content_b64") or ""),
                "content_type": str(item.get("mime_type") or "application/octet-stream"),
            }
            for item in attachments
            if item and item.get("content_b64")
        ]
    req = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "BauPass/1.0 (resend-client; python-urllib)",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            if 200 <= status < 300:
                return True, ""
            return False, f"resend_http_{status}"
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return False, f"resend_http_{exc.code}: {body[:300]}"
    except URLError as exc:
        return False, f"resend_url_error: {exc}"
    except Exception as exc:
        return False, f"resend_error: {exc}"


def _get_brevo_api_key():
    """Return Brevo API key from module-level cache (DB) or env var."""
    cached = _normalize_env_value(_resend_key_cache.get("brevo_key") or "")
    if cached:
        return cached
    return _normalize_env_value(os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY") or "")


def _send_via_brevo(subject, sender_email, sender_name, recipient, text_body, html_body, attachments=None):
    """Send e-mail via Brevo (formerly Sendinblue) API — no Cloudflare, allows any from address."""
    api_key = _get_brevo_api_key()
    if not api_key:
        return False, "brevo_not_configured"

    from_email = _normalize_env_value(_resend_key_cache.get("brevo_from_email") or "") or sender_email or ""
    from_name = sender_name or ""
    if not from_email:
        return False, "brevo_missing_from_email"

    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": text_body,
        "htmlContent": html_body,
    }
    if attachments:
        payload["attachment"] = [
            {
                "name": str(item.get("filename") or "attachment.bin"),
                "content": str(item.get("content_b64") or ""),
                "contentType": str(item.get("mime_type") or "application/octet-stream"),
            }
            for item in attachments
            if item and item.get("content_b64")
        ]
    req = Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            if 200 <= status < 300:
                return True, ""
            return False, f"brevo_http_{status}"
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return False, f"brevo_http_{exc.code}: {body[:300]}"
    except URLError as exc:
        return False, f"brevo_url_error: {exc}"
    except Exception as exc:
        return False, f"brevo_error: {exc}"


def _send_via_any_api(subject, sender_email, sender_name, recipient, text_body, html_body, attachments=None):
    """Try API providers (Resend, then Brevo). Returns (ok, error_string, provider_used)."""
    resend_key, _ = _get_resend_api_key_and_source()
    if resend_key:
        ok, err = _send_via_resend(subject, sender_email, sender_name, recipient, text_body, html_body, attachments=attachments)
        if ok:
            return True, "", "resend"
        # Fall through to Brevo on any Resend failure
        app.logger.warning(f"[API-MAIL] Resend fehlgeschlagen ({err}), versuche Brevo")

    brevo_key = _get_brevo_api_key()
    if brevo_key:
        ok, err = _send_via_brevo(subject, sender_email, sender_name, recipient, text_body, html_body, attachments=attachments)
        if ok:
            return True, "", "brevo"
        return False, f"brevo: {err}", "brevo"

    if resend_key:
        # Resend was tried but failed, Brevo not configured
        _, resend_err = _send_via_resend(subject, sender_email, sender_name, recipient, text_body, html_body, attachments=attachments)
        return False, f"resend: {resend_err}", "resend"

    return False, "no_api_provider_configured (set Resend or Brevo key in Einstellungen)", "none"


def _build_email_html(platform_name: str, primary_color: str, accent_color: str, title: str, body_html: str, footer_name: str) -> str:
    """Return a branded HTML email string."""
    # Inline SVG logo (simplified icon part only for email compatibility)
    logo_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 310 310">'
        f'<rect width="310" height="310" rx="46" fill="{primary_color}"/>'
        '<path d="M56 224 L156 92 L256 224 Z" fill="#ffffff" opacity="0.94"/>'
        '<path d="M96 224 L156 144 L216 224 Z" fill="#12343b" opacity="0.95"/>'
        '<circle cx="235" cy="88" r="20" fill="#fff4e6"/>'
        '</svg>'
    )
    return f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:32px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);max-width:600px;width:100%;">
      <!-- Header -->
      <tr>
        <td style="background:linear-gradient(135deg,{primary_color} 0%,{accent_color} 100%);padding:28px 36px;text-align:left;">
          <table cellpadding="0" cellspacing="0">
            <tr>
              <td style="vertical-align:middle;padding-right:14px;">{logo_svg}</td>
              <td style="vertical-align:middle;">
                <span style="color:#ffffff;font-size:22px;font-weight:700;letter-spacing:0.5px;">{platform_name}</span><br>
                <span style="color:rgba(255,255,255,0.75);font-size:12px;letter-spacing:2px;text-transform:uppercase;">Digitale Baustellenkontrolle</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <!-- Body -->
      <tr>
        <td style="padding:36px 36px 28px;">
          <h2 style="margin:0 0 20px;color:{primary_color};font-size:20px;font-weight:700;">{title}</h2>
          {body_html}
        </td>
      </tr>
      <!-- Footer -->
      <tr>
        <td style="background:#f8f9fa;border-top:1px solid #e9ecef;padding:18px 36px;text-align:center;">
          <p style="margin:0;color:#6c757d;font-size:12px;">
            {footer_name} &nbsp;·&nbsp; Diese E-Mail wurde automatisch generiert.<br>
            Bitte antworten Sie nicht auf diese E-Mail.
          </p>
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def _resolve_smtp_settings(saved_settings, override_payload=None):
    payload = override_payload or {}
    smtp_password_override = payload.get("smtpPassword") if "smtpPassword" in payload else None
    smtp_settings = {
        "smtp_host": str(payload.get("smtpHost") if "smtpHost" in payload else (saved_settings["smtp_host"] if saved_settings else "") or "").strip(),
        "smtp_port": int(payload.get("smtpPort") or (saved_settings["smtp_port"] if saved_settings else 587) or 587),
        "smtp_username": str(payload.get("smtpUsername") if "smtpUsername" in payload else (saved_settings["smtp_username"] if saved_settings else "") or "").strip(),
        "smtp_password": str((smtp_password_override if str(smtp_password_override or "").strip() else (saved_settings["smtp_password"] if saved_settings else "")) or ""),
        "smtp_sender_email": str(payload.get("smtpSenderEmail") if "smtpSenderEmail" in payload else (saved_settings["smtp_sender_email"] if saved_settings else "") or "").strip(),
        "smtp_sender_name": str(payload.get("smtpSenderName") if "smtpSenderName" in payload else (saved_settings["smtp_sender_name"] if saved_settings else "") or "").strip(),
        "smtp_use_tls": (1 if bool(payload.get("smtpUseTls")) else 0) if "smtpUseTls" in payload else (int(saved_settings["smtp_use_tls"] or 0) if saved_settings else 0),
        "platform_name": str(payload.get("platformName") if "platformName" in payload else (saved_settings["platform_name"] if saved_settings else "BauPass Control") or "BauPass Control").strip(),
        "operator_name": str(payload.get("operatorName") if "operatorName" in payload else (saved_settings["operator_name"] if saved_settings else "BauPass Control") or "BauPass Control").strip(),
        "invoice_primary_color": str(payload.get("invoicePrimaryColor") if "invoicePrimaryColor" in payload else (saved_settings["invoice_primary_color"] if saved_settings else "#0f4c5c") or "#0f4c5c").strip(),
        "invoice_accent_color": str(payload.get("invoiceAccentColor") if "invoiceAccentColor" in payload else (saved_settings["invoice_accent_color"] if saved_settings else "#e36414") or "#e36414").strip(),
    }
    if not smtp_settings["smtp_sender_name"]:
        smtp_settings["smtp_sender_name"] = smtp_settings["platform_name"]
    if not smtp_settings["operator_name"]:
        smtp_settings["operator_name"] = smtp_settings["platform_name"]
    return smtp_settings


def _send_otp_email_to_user(db, user_row, code, smtp_settings_override=None):
    """Send a 6-digit OTP code to the user's stored email address via SMTP."""
    try:
        user_keys = set(user_row.keys()) if hasattr(user_row, "keys") else set()
        email = (user_row["email"] if "email" in user_keys else "").strip()
    except Exception as exc:
        app.logger.error(f"[OTP-MAIL] Fehler beim Lesen der E-Mail-Adresse: {exc}")
        return False
    if not email:
        app.logger.warning(f"[OTP-MAIL] Kein E-Mail für Benutzer '{user_row.get('username', '?')}' – E-Mail-Versand übersprungen")
        return False

    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if not settings:
        app.logger.error("[OTP-MAIL] Keine Settings in der Datenbank gefunden")
        return False

    smtp_settings = _resolve_smtp_settings(settings, smtp_settings_override)
    smtp_host = smtp_settings["smtp_host"]
    smtp_sender = smtp_settings["smtp_sender_email"]
    platform_name = smtp_settings["platform_name"]
    smtp_sender_name = smtp_settings["smtp_sender_name"]
    primary_color = smtp_settings["invoice_primary_color"]
    accent_color = smtp_settings["invoice_accent_color"]
    username = user_row["username"] if hasattr(user_row, "keys") else str(user_row)
    operator_name = smtp_settings["operator_name"]

    # If SMTP is not configured at all, use API fallback directly (no fallback loop needed)
    smtp_configured = bool(smtp_host and smtp_sender)
    resend_api_key, _ = _get_resend_api_key_and_source()
    brevo_api_key = _get_brevo_api_key()
    if not smtp_configured and not resend_api_key and not brevo_api_key:
        app.logger.warning("[OTP-MAIL] Weder SMTP noch API-Fallback konfiguriert – E-Mail-Versand nicht möglich")
        return False
    if not smtp_configured:
        app.logger.info("[OTP-MAIL] SMTP nicht konfiguriert, sende OTP direkt über API-Fallback")
    # Use smtp_sender as from address, fall back to stored API sender addresses
    if not smtp_sender:
        smtp_sender = _normalize_env_value(_resend_key_cache.get("from_email") or "")
    if not smtp_sender:
        smtp_sender = _normalize_env_value(_resend_key_cache.get("brevo_from_email") or "")
    if not smtp_sender:
        app.logger.warning("[OTP-MAIL] Keine Absender-E-Mail konfiguriert – E-Mail-Versand nicht möglich")
        return False

    body_html = f"""
        <p style="color:#374151;font-size:15px;line-height:1.6;margin:0 0 24px;">
            Guten Tag,<br><br>
            Ihr Anmelde-Sicherheitscode für <strong>{platform_name}</strong>:
        </p>
        <div style="text-align:center;margin:0 0 28px;">
            <div style="display:inline-block;background:#f8f9fa;border:2px dashed {primary_color};border-radius:10px;padding:18px 40px;">
                <span style="font-size:36px;font-weight:700;letter-spacing:10px;color:{primary_color};font-family:'Courier New',monospace;">{code}</span>
            </div>
            <p style="margin:10px 0 0;color:#6c757d;font-size:12px;">⏱ Gültig für <strong>10 Minuten</strong></p>
        </div>
        <table cellpadding="0" cellspacing="0" style="background:#fff8f0;border-left:4px solid {accent_color};border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:24px;width:100%;">
            <tr><td>
                <p style="margin:0;color:#374151;font-size:13px;">
                    <strong>Benutzerkonto:</strong> {username}
                </p>
            </td></tr>
        </table>
        <p style="color:#6c757d;font-size:13px;margin:0;border-top:1px solid #e9ecef;padding-top:16px;">
            ⚠️ Falls Sie sich <strong>nicht</strong> angemeldet haben, ignorieren Sie diese E-Mail. Ihr Konto ist sicher.
        </p>"""

    html_content = _build_email_html(platform_name, primary_color, accent_color,
                                     "Ihr Sicherheitscode", body_html, operator_name)

    msg = EmailMessage()
    msg["Subject"] = f"{platform_name}: Ihr Sicherheitscode – {code}"
    msg["From"] = f'"{smtp_sender_name}" <{smtp_sender}>'
    msg["To"] = email
    text_content = (
        f"Guten Tag,\n\nIhr Sicherheitscode: {code}\n\nGültig 10 Minuten.\nBenutzerkonto: {username}\n\n"
        f"Falls Sie sich nicht angemeldet haben, ignorieren Sie diese E-Mail.\n\n{operator_name}"
    )
    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    # Skip SMTP attempt entirely if not configured — go straight to API fallback
    if not smtp_configured:
        fallback_ok, fallback_error, _provider_used = _send_via_any_api(
            subject=msg["Subject"],
            sender_email=smtp_sender,
            sender_name=smtp_sender_name,
            recipient=email,
            text_body=text_content,
            html_body=html_content,
        )
        if fallback_ok:
            app.logger.info(f"[OTP-MAIL] OTP über API-Fallback versendet an {email} (Benutzer: {username})")
            return True
        app.logger.error(f"[OTP-MAIL] API-Fallback fehlgeschlagen: {fallback_error}")
        return False

    try:
        with _smtp_connect(smtp_host, smtp_settings["smtp_port"], smtp_settings["smtp_use_tls"]) as smtp:
            smtp_username = smtp_settings["smtp_username"]
            if smtp_username:
                smtp.login(smtp_username, smtp_settings["smtp_password"])
            smtp.send_message(msg)
        app.logger.info(f"[OTP-MAIL] OTP-Code erfolgreich gesendet an {email} (Benutzer: {username})")
        return True
    except Exception as exc:
        app.logger.error(f"[OTP-MAIL] SMTP-Fehler beim Senden an {email}: {exc}")
        fallback_ok, fallback_error, _provider_used = _send_via_any_api(
            subject=msg["Subject"],
            sender_email=smtp_sender,
            sender_name=smtp_sender_name,
            recipient=email,
            text_body=text_content,
            html_body=html_content,
        )
        if fallback_ok:
            app.logger.warning(f"[OTP-MAIL] SMTP ausgefallen, OTP über API-Fallback versendet an {email}")
            return True
        app.logger.error(f"[OTP-MAIL] API-Fallback fehlgeschlagen: {fallback_error}")
        return False


def run_invoice_dunning_cycle(db):
    """Update overdue status and send staged reminders before automatic suspension."""
    today = utc_now().date()
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    rows = db.execute(
        """
        SELECT invoices.*, companies.name AS company_name, companies.deleted_at AS company_deleted_at
        FROM invoices
        JOIN companies ON companies.id = invoices.company_id
        WHERE invoices.paid_at IS NULL
          AND invoices.due_date IS NOT NULL
          AND invoices.status IN ('sent', 'overdue')
        ORDER BY invoices.created_at ASC
        """
    ).fetchall()

    result = {
        "remindersSent": 0,
        "reminderFailures": 0,
        "overdueUpdated": 0,
    }

    for row in rows:
        if row["company_deleted_at"]:
            continue

        due_date = parse_iso_date(row["due_date"])
        if not due_date:
            continue

        days_until_due = (due_date - today).days
        invoice_id = row["id"]
        current_stage = int(row["reminder_stage"] or 0)
        last_reminder_day = str(row["last_reminder_sent_at"] or "")[:10]

        if days_until_due < 0 and row["status"] != "overdue":
            db.execute("UPDATE invoices SET status = 'overdue' WHERE id = ?", (invoice_id,))
            result["overdueUpdated"] += 1

        target_stage = 0
        if days_until_due <= 7 and days_until_due > 3:
            target_stage = 1
        elif days_until_due <= 3 and days_until_due >= 0:
            target_stage = 2
        elif days_until_due < 0:
            target_stage = 3

        if target_stage == 0:
            continue

        should_send = target_stage > current_stage or (target_stage == 3 and last_reminder_day != today.isoformat())
        if not should_send:
            continue

        company_row = {"name": row["company_name"]}
        sent_ok, error_message = send_payment_reminder_email(row, company_row, settings, target_stage, days_until_due)

        if sent_ok:
            db.execute(
                "UPDATE invoices SET reminder_stage = ?, last_reminder_sent_at = ?, last_reminder_error = '' WHERE id = ?",
                (target_stage, now_iso(), invoice_id),
            )
            log_audit(
                "invoice.reminder_sent",
                f"Mahnstufe {target_stage} für Rechnung {row['invoice_number']} versendet",
                target_type="invoice",
                target_id=invoice_id,
                company_id=row["company_id"],
                actor=None,
            )
            result["remindersSent"] += 1
        else:
            db.execute(
                "UPDATE invoices SET last_reminder_error = ? WHERE id = ?",
                (error_message, invoice_id),
            )
            log_audit(
                "invoice.reminder_failed",
                f"Mahnstufe {target_stage} für Rechnung {row['invoice_number']} fehlgeschlagen: {error_message}",
                target_type="invoice",
                target_id=invoice_id,
                company_id=row["company_id"],
                actor=None,
            )
            result["reminderFailures"] += 1

    db.commit()
    return result


def create_system_alert(db, code, severity, message, details="", dedup_minutes=ALERT_DEDUP_MINUTES):
    details_text = details if isinstance(details, str) else json.dumps(details, ensure_ascii=False)
    threshold = utc_iso(utc_now() - timedelta(minutes=dedup_minutes))
    recent = db.execute(
        """
        SELECT id
        FROM system_alerts
        WHERE code = ? AND severity = ? AND message = ? AND created_at >= ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (code, severity, message, threshold),
    ).fetchone()
    if recent:
        return None

    alert_id = f"alert-{secrets.token_hex(6)}"
    db.execute(
        "INSERT INTO system_alerts (id, code, severity, message, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (alert_id, code, severity, message, details_text, now_iso()),
    )
    db.commit()
    return alert_id


def rotate_import_backups(backup_dir):
    now_dt = utc_now()
    removed = 0
    kept = 0
    errors = 0

    for path in backup_dir.glob("import-backup-*.json"):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            age_days = (now_dt - mtime).days
            if age_days >= BACKUP_RETENTION_DAYS:
                path.unlink(missing_ok=True)
                removed += 1
            else:
                kept += 1
        except Exception:
            errors += 1

    return {"removed": removed, "kept": kept, "errors": errors, "retentionDays": BACKUP_RETENTION_DAYS}


def create_import_rollback_backup(db, role, target_company_id):
    backup_dir = BASE_DIR / "backend" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    rotation = rotate_import_backups(backup_dir)

    company_clause = ""
    company_params = []
    if role != "superadmin" or target_company_id:
        scope_id = target_company_id
        company_clause = " WHERE company_id = ?"
        company_params = [scope_id]

    payload = {
        "meta": {
            "type": "import-rollback-backup",
            "createdAt": now_iso(),
            "scopeCompanyId": target_company_id,
            "role": role,
        },
        "companies": [],
        "subcompanies": [],
        "workers": [],
        "accessLogs": [],
        "invoices": [],
    }

    if role == "superadmin" and not target_company_id:
        payload["companies"] = [row_to_dict(row) for row in db.execute("SELECT * FROM companies ORDER BY name").fetchall()]
    elif target_company_id:
        payload["companies"] = [
            row_to_dict(row)
            for row in db.execute("SELECT * FROM companies WHERE id = ? ORDER BY name", (target_company_id,)).fetchall()
        ]

    payload["subcompanies"] = [
        row_to_dict(row)
        for row in db.execute(f"SELECT * FROM subcompanies{company_clause} ORDER BY name", company_params).fetchall()
    ]
    payload["workers"] = [
        row_to_dict(row)
        for row in db.execute(f"SELECT * FROM workers{company_clause} ORDER BY last_name, first_name", company_params).fetchall()
    ]
    payload["invoices"] = [
        row_to_dict(row)
        for row in db.execute(f"SELECT * FROM invoices{company_clause} ORDER BY created_at DESC", company_params).fetchall()
    ]

    worker_ids = [row["id"] for row in payload["workers"]]
    if worker_ids:
        placeholders = ",".join(["?"] * len(worker_ids))
        payload["accessLogs"] = [
            row_to_dict(row)
            for row in db.execute(
                f"SELECT * FROM access_logs WHERE worker_id IN ({placeholders}) ORDER BY timestamp DESC",
                worker_ids,
            ).fetchall()
        ]

    filename = f"import-backup-{utc_now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}.json"
    backup_path = backup_dir / filename
    backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if rotation.get("errors"):
        create_system_alert(
            db,
            code="backup_rotation_errors",
            severity="warning",
            message="Backup-Rotation hatte Fehler.",
            details=rotation,
        )
    return str(backup_path)


def check_visitor_card_expiry_notifications(db):
    """Send an e-mail to the company-admin when a visitor card expires within the next 24 hours.
    Uses audit_logs to avoid sending duplicate mails on the same day."""
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    smtp_host = (settings["smtp_host"] or "").strip() if settings else ""
    smtp_sender = (settings["smtp_sender_email"] or "").strip() if settings else ""
    if not smtp_host or not smtp_sender:
        return  # SMTP not configured, nothing to do

    now = utc_now()
    cutoff = utc_iso(now + timedelta(hours=24))
    today_str = now.date().isoformat()

    expiring = db.execute(
        """
        SELECT workers.*, companies.name AS company_name
        FROM workers
        JOIN companies ON companies.id = workers.company_id
        WHERE workers.visit_end_at != ''
          AND workers.visit_end_at IS NOT NULL
          AND workers.visit_end_at <= ?
          AND workers.deleted_at IS NULL
          AND workers.status != 'gesperrt'
        """,
        (cutoff,),
    ).fetchall()

    for worker in expiring:
        dedup_key = f"visitor_expiry_notif.{worker['id']}.{today_str}"
        already_sent = db.execute(
            "SELECT id FROM audit_logs WHERE event_type = ? AND created_at >= ? LIMIT 1",
            (dedup_key, f"{today_str}T00:00:00"),
        ).fetchone()
        if already_sent:
            continue

        # Use company billing email, or fall back to SMTP sender (operator)
        company_row = db.execute(
            "SELECT billing_email FROM companies WHERE id = ? LIMIT 1",
            (worker["company_id"],),
        ).fetchone()
        recipient = (company_row["billing_email"] if company_row else "") or smtp_sender
        if not recipient:
            continue
        expire_label = worker["visit_end_at"][:16].replace("T", " ")
        msg = EmailMessage()
        msg["Subject"] = f"Besucherkarte läuft ab: {worker['first_name']} {worker['last_name']}"
        msg["From"] = f"{settings['smtp_sender_name']} <{smtp_sender}>"
        msg["To"] = recipient
        msg.set_content(
            f"Guten Tag,\n\n"
            f"die Besucherkarte von {worker['first_name']} {worker['last_name']} "
            f"(Badge {worker['badge_id']}, Firma {worker['company_name']}) "
            f"läuft am {expire_label} Uhr ab.\n\n"
            f"Bitte verlängern oder löschen Sie die Karte im BauPass-Admin-Panel.\n\n"
            f"Viele Grüße\n{settings['operator_name']}"
        )
        mail_sent = False
        try:
            with smtplib.SMTP(smtp_host, int(settings["smtp_port"] or 587), timeout=20) as smtp:
                if int(settings["smtp_use_tls"] or 0) == 1:
                    smtp.starttls()
                if (settings["smtp_username"] or "").strip():
                    smtp.login(settings["smtp_username"].strip(), settings["smtp_password"] or "")
                smtp.send_message(msg)
            mail_sent = True
        except Exception:
            visitor_text = (
                f"Guten Tag,\n\n"
                f"die Besucherkarte von {worker['first_name']} {worker['last_name']} "
                f"(Badge {worker['badge_id']}, Firma {worker['company_name']}) "
                f"l\u00e4uft am {expire_label} Uhr ab.\n\n"
                f"Bitte verl\u00e4ngern oder l\u00f6schen Sie die Karte im BauPass-Admin-Panel.\n\n"
                f"Viele Gr\u00fc\u00dfe\n{settings['operator_name']}"
            )
            fallback_ok, _, _provider_used = _send_via_any_api(
                subject=str(msg["Subject"]),
                sender_email=smtp_sender,
                sender_name=settings["smtp_sender_name"] or "",
                recipient=recipient,
                text_body=visitor_text,
                html_body="",
            )
            mail_sent = fallback_ok
        if mail_sent:
            db.execute(
                "INSERT INTO audit_logs (id, event_type, actor_user_id, actor_role, company_id, target_type, target_id, message, created_at) VALUES (?,?,NULL,NULL,?,?,?,?,?)",
                (f"aud-{secrets.token_hex(8)}", dedup_key, worker["company_id"], "worker", worker["id"],
                 f"Ablauf-Mail fuer {worker['first_name']} {worker['last_name']} (Badge {worker['badge_id']}) gesendet an {recipient}", now_iso()),
            )
            db.commit()


def run_dunning_job_once():
    global DUNNING_LAST_RUN_AT, DUNNING_LAST_RESULT
    with app.app_context():
        db = get_db()
        result = run_invoice_dunning_cycle(db)
        suspended = check_and_apply_overdue_suspensions(db)
        result["suspendedCompanies"] = len(suspended)
        check_visitor_card_expiry_notifications(db)
        if int(result.get("reminderFailures", 0)) > 0:
            create_system_alert(
                db,
                code="dunning_reminder_failures",
                severity="warning",
                message=f"Dunning hatte {int(result.get('reminderFailures', 0))} fehlgeschlagene Erinnerungen.",
                details=result,
            )
        if int(result.get("suspendedCompanies", 0)) > 0:
            create_system_alert(
                db,
                code="dunning_company_suspensions",
                severity="info",
                message=f"Dunning hat {int(result.get('suspendedCompanies', 0))} Firmen gesperrt.",
                details=result,
                dedup_minutes=10,
            )
        DUNNING_LAST_RUN_AT = now_iso()
        DUNNING_LAST_RESULT = result


def start_background_jobs():
    global _background_started
    with _background_lock:
        if _background_started:
            return
        _background_started = True

    interval_hours = max(1, int(os.getenv("BAUPASS_DUNNING_INTERVAL_HOURS", "24")))
    session_cleanup_seconds = max(60, int(os.getenv("BAUPASS_WORKER_SESSION_CLEANUP_SECONDS", "300")))
    invoice_retry_seconds = max(60, int(os.getenv("BAUPASS_INVOICE_RETRY_SECONDS", "180")))

    def scheduler_loop():
        while True:
            try:
                run_dunning_job_once()
                with app.app_context():
                    db = get_db()
                    backup_dir = BASE_DIR / "backend" / "backups"
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    rotation = rotate_import_backups(backup_dir)
                    if rotation.get("errors"):
                        create_system_alert(
                            db,
                            code="backup_rotation_errors",
                            severity="warning",
                            message="Geplante Backup-Rotation hatte Fehler.",
                            details=rotation,
                        )
            except Exception as exc:
                with app.app_context():
                    db = get_db()
                    create_system_alert(
                        db,
                        code="dunning_scheduler_error",
                        severity="critical",
                        message="Dunning-Scheduler ist fehlgeschlagen.",
                        details={"error": str(exc)},
                    )
            time.sleep(interval_hours * 3600)

    def check_doc_expiry_warnings():
        """Erstellt System-Alerts für ablaufende Dokumente."""
        try:
            with app.app_context():
                db = get_db()
                today = now_iso()[:10]
                warn_date = (utc_now() + timedelta(days=30)).strftime("%Y-%m-%d")
                rows = db.execute(
                    """SELECT wd.id, wd.doc_type, wd.expiry_date, wd.worker_id,
                              w.first_name, w.last_name, w.badge_id, w.company_id,
                              c.name AS company_name
                       FROM worker_documents wd
                       JOIN workers w ON w.id = wd.worker_id
                       JOIN companies c ON c.id = w.company_id
                       WHERE wd.expiry_date IS NOT NULL
                         AND wd.expiry_date <= ?
                         AND wd.expiry_date >= ?
                         AND w.deleted_at IS NULL
                         AND c.deleted_at IS NULL
                       ORDER BY wd.expiry_date""",
                    (warn_date, today),
                ).fetchall()
                for row in rows:
                    alert_code = f"doc_expiry_{row['id']}"
                    existing = db.execute("SELECT id FROM system_alerts WHERE code = ? AND resolved_at IS NULL", (alert_code,)).fetchone()
                    if not existing:
                        create_system_alert(
                            db, code=alert_code, severity="warning",
                            message=f"Dokument '{row['doc_type']}' von {row['first_name']} {row['last_name']} ({row['badge_id']}) bei Firma {row['company_name']} läuft ab am {row['expiry_date']}.",
                            details={"workerId": row["worker_id"], "docId": row["id"], "companyId": row["company_id"]},
                        )
                db.commit()
        except Exception:
            pass

    def send_daily_summary_email():
        """Sendet tägliche Zusammenfassung an Superadmin-E-Mail."""
        try:
            with app.app_context():
                db = get_db()
                settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
                if not settings:
                    return
                smtp_host = (settings["smtp_host"] or "").strip()
                smtp_sender = (settings["smtp_sender_email"] or "").strip()
                admin_email = ((settings["admin_summary_email"] if "admin_summary_email" in settings.keys() else "") or smtp_sender)
                if not admin_email:
                    return

                today = now_iso()[:10]
                yesterday = (utc_now() - timedelta(days=1)).strftime("%Y-%m-%d")

                total_entries = db.execute(
                    "SELECT COUNT(*) AS c FROM access_logs WHERE DATE(timestamp) = ?", (yesterday,)
                ).fetchone()["c"]
                companies_active = db.execute(
                    """SELECT COUNT(DISTINCT w.company_id) AS c
                       FROM access_logs al JOIN workers w ON w.id = al.worker_id
                       WHERE DATE(al.timestamp) = ?""", (yesterday,)
                ).fetchone()["c"]
                new_workers = db.execute(
                    """SELECT COUNT(*) AS c FROM workers
                       WHERE deleted_at IS NULL AND DATE(COALESCE(valid_until,'')) <= DATE('now','+7 day')
                         AND DATE(COALESCE(valid_until,'')) >= DATE('now')""",
                ).fetchone()["c"]
                expired_docs_count = db.execute(
                    "SELECT COUNT(*) AS c FROM worker_documents WHERE expiry_date IS NOT NULL AND expiry_date < ?", (today,)
                ).fetchone()["c"]
                open_invoices_count = db.execute(
                    "SELECT COUNT(*) AS c FROM invoices WHERE paid_at IS NULL AND status NOT IN ('bezahlt','draft')"
                ).fetchone()["c"]

                platform_label = str(settings["platform_name"] or "BauPass").strip() or "BauPass"
                operator_label = str(settings["operator_name"] or platform_label).strip() or platform_label
                summary_text = (
                    f"{platform_label} Tageszusammenfassung für {yesterday}:\n\n"
                    f"  Zutritte gestern:           {total_entries}\n"
                    f"  Aktive Firmen gestern:      {companies_active}\n"
                    f"  Mitarbeiter bald ablaufend: {new_workers}\n"
                    f"  Abgelaufene Dokumente:      {expired_docs_count}\n"
                    f"  Offene Rechnungen:          {open_invoices_count}\n\n"
                    f"Diese Zusammenfassung wurde automatisch von {operator_label} erstellt."
                )
                import email.message as _email_mod, smtplib as _smtplib
                msg = _email_mod.EmailMessage()
                msg["Subject"] = f"{platform_label} Tageszusammenfassung {yesterday}"
                msg["From"] = f"{settings['smtp_sender_name']} <{smtp_sender}>" if smtp_sender else operator_label
                msg["To"] = admin_email
                msg.set_content(summary_text)
                _primary = str(settings["invoice_primary_color"] or "#0f4c5c").strip()
                html_body = _build_email_html(
                    platform_label, _primary, _primary,
                    f"Tageszusammenfassung {yesterday}",
                    (
                        f"<p style='margin:0 0 10px'>Hier ist Ihre tägliche Übersicht für <strong>{yesterday}</strong>:</p>"
                        f"<table style='width:100%;border-collapse:collapse;font-size:14px'>"
                        f"<tr><td style='padding:6px 0;color:#555'>Zutritte gestern</td><td style='text-align:right;font-weight:700'>{total_entries}</td></tr>"
                        f"<tr><td style='padding:6px 0;color:#555'>Aktive Firmen gestern</td><td style='text-align:right;font-weight:700'>{companies_active}</td></tr>"
                        f"<tr><td style='padding:6px 0;color:#555'>Mitarbeiter bald ablaufend (7 Tage)</td><td style='text-align:right;font-weight:700'>{new_workers}</td></tr>"
                        f"<tr><td style='padding:6px 0;color:#555'>Abgelaufene Dokumente</td><td style='text-align:right;font-weight:700'>{expired_docs_count}</td></tr>"
                        f"<tr style='border-top:1px solid #eee'><td style='padding:6px 0;color:#555'>Offene Rechnungen</td><td style='text-align:right;font-weight:700'>{open_invoices_count}</td></tr>"
                        f"</table>"
                    ),
                    operator_label,
                )
                try:
                    if smtp_host:
                        with _smtplib.SMTP(smtp_host, int(settings["smtp_port"] or 587), timeout=15) as smtp:
                            if int(settings["smtp_use_tls"] or 0):
                                smtp.starttls()
                            if (settings["smtp_username"] or "").strip():
                                smtp.login(settings["smtp_username"], settings["smtp_password"] or "")
                            smtp.send_message(msg)
                    else:
                        _send_via_any_api(
                            subject=str(msg["Subject"]),
                            sender_email=smtp_sender or "",
                            sender_name=settings["smtp_sender_name"] or "",
                            recipient=admin_email,
                            text_body=summary_text,
                            html_body=html_body,
                        )
                except Exception:
                    _send_via_any_api(
                        subject=str(msg["Subject"]),
                        sender_email=smtp_sender or "",
                        sender_name=settings["smtp_sender_name"] or "",
                        recipient=admin_email,
                        text_body=summary_text,
                        html_body=html_body,
                    )
        except Exception:
            pass

    def send_worker_expiry_reminders():
        """Sendet Erinnerungs-E-Mails wenn Mitarbeiter-Ausweise bald ablaufen."""
        try:
            with app.app_context():
                db = get_db()
                settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
                if not settings:
                    return
                smtp_sender = (settings["smtp_sender_email"] or "").strip()
                warn_days = int(settings["worker_expiry_warn_days"] if "worker_expiry_warn_days" in settings.keys() else 7)
                if warn_days <= 0:
                    return

                warn_date = (utc_now() + timedelta(days=warn_days)).strftime("%Y-%m-%d")
                today = now_iso()[:10]

                # Workers whose valid_until is within the next N days and not yet reminded today
                rows = db.execute(
                    """SELECT w.id, w.first_name, w.last_name, w.badge_id, w.valid_until,
                              w.company_id, c.name AS company_name, c.billing_email,
                              u.email AS admin_email
                       FROM workers w
                       JOIN companies c ON c.id = w.company_id
                       LEFT JOIN users u ON u.company_id = c.id AND u.role = 'company-admin'
                       WHERE w.deleted_at IS NULL
                         AND w.worker_type != 'visitor'
                         AND w.valid_until != ''
                         AND DATE(w.valid_until) <= ?
                         AND DATE(w.valid_until) >= ?
                         AND c.deleted_at IS NULL
                       ORDER BY w.valid_until ASC""",
                    (warn_date, today),
                ).fetchall()

                # Group by company
                by_company: dict = {}
                for row in rows:
                    cid = row["company_id"]
                    if cid not in by_company:
                        by_company[cid] = {
                            "company_name": row["company_name"],
                            "billing_email": row["billing_email"] or "",
                            "admin_email": row["admin_email"] or "",
                            "workers": [],
                        }
                    by_company[cid]["workers"].append(row)

                platform_label = str(settings["platform_name"] or "BauPass").strip() or "BauPass"
                operator_label = str(settings["operator_name"] or platform_label).strip() or platform_label
                _primary = str(settings["invoice_primary_color"] or "#0f4c5c").strip()

                for cid, data in by_company.items():
                    recipient = data["admin_email"] or data["billing_email"]
                    if not recipient:
                        continue
                    alert_code = f"worker_expiry_reminder_{cid}_{today}"
                    existing = db.execute(
                        "SELECT id FROM system_alerts WHERE code = ?", (alert_code,)
                    ).fetchone()
                    if existing:
                        continue  # Already sent today

                    worker_lines_text = "\n".join(
                        f"  - {w['first_name']} {w['last_name']} ({w['badge_id']}): gültig bis {w['valid_until']}"
                        for w in data["workers"]
                    )
                    worker_rows_html = "".join(
                        f"<tr><td style='padding:5px 8px'>{w['first_name']} {w['last_name']}</td>"
                        f"<td style='padding:5px 8px'>{w['badge_id']}</td>"
                        f"<td style='padding:5px 8px;color:#c53d2f;font-weight:700'>{w['valid_until']}</td></tr>"
                        for w in data["workers"]
                    )
                    subject = f"{platform_label}: {len(data['workers'])} Mitarbeiter-Ausweis/Ausweise laufen bald ab"
                    text_body = (
                        f"Guten Tag,\n\n"
                        f"folgende Mitarbeiter bei {data['company_name']} haben Ausweise, die in den nächsten {warn_days} Tagen ablaufen:\n\n"
                        f"{worker_lines_text}\n\n"
                        f"Bitte verlängern Sie die Gültigkeiten rechtzeitig in {platform_label}.\n\n"
                        f"Mit freundlichen Grüßen\n{operator_label}"
                    )
                    html_body = _build_email_html(
                        platform_label, _primary, _primary,
                        "Ablaufende Mitarbeiterausweise",
                        (
                            f"<p style='margin:0 0 10px'>Folgende Mitarbeiter bei <strong>{data['company_name']}</strong> "
                            f"haben Ausweise, die in den nächsten <strong>{warn_days} Tagen</strong> ablaufen:</p>"
                            f"<table style='width:100%;border-collapse:collapse;font-size:13px;border:1px solid #eee'>"
                            f"<thead><tr style='background:#f5f5f5'><th style='padding:5px 8px;text-align:left'>Name</th>"
                            f"<th style='padding:5px 8px;text-align:left'>Badge-ID</th>"
                            f"<th style='padding:5px 8px;text-align:left'>Gültig bis</th></tr></thead>"
                            f"<tbody>{worker_rows_html}</tbody></table>"
                            f"<p style='margin:12px 0 0;font-size:13px;color:#555'>Bitte verlängern Sie die Gültigkeiten rechtzeitig.</p>"
                        ),
                        operator_label,
                    )
                    try:
                        smtp_host = (settings["smtp_host"] or "").strip()
                        import email.message as _em, smtplib as _sl
                        msg = _em.EmailMessage()
                        msg["Subject"] = subject
                        msg["From"] = f"{settings['smtp_sender_name']} <{smtp_sender}>" if smtp_sender else operator_label
                        msg["To"] = recipient
                        msg.set_content(text_body)
                        msg.add_alternative(html_body, subtype="html")
                        if smtp_host:
                            with _sl.SMTP(smtp_host, int(settings["smtp_port"] or 587), timeout=15) as smtp:
                                if int(settings["smtp_use_tls"] or 0):
                                    smtp.starttls()
                                if (settings["smtp_username"] or "").strip():
                                    smtp.login(settings["smtp_username"], settings["smtp_password"] or "")
                                smtp.send_message(msg)
                        else:
                            _send_via_any_api(
                                subject=subject,
                                sender_email=smtp_sender or "",
                                sender_name=settings["smtp_sender_name"] or "",
                                recipient=recipient,
                                text_body=text_body,
                                html_body=html_body,
                            )
                        # Mark as sent so we don't spam
                        create_system_alert(
                            db, code=alert_code, severity="info",
                            message=f"Ablauf-Erinnerung für {len(data['workers'])} Mitarbeiter bei {data['company_name']} gesendet.",
                            details={"companyId": cid, "recipientCount": len(data["workers"])},
                        )
                        db.commit()
                    except Exception:
                        pass
        except Exception:
            pass

    def send_document_expiry_notifications():
        """Sendet E-Mail-Benachrichtigungen an Firmen-Admins wenn Dokumente bald ablaufen."""
        try:
            with app.app_context():
                db = get_db()
                settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
                if not settings:
                    return
                smtp_sender = (settings["smtp_sender_email"] or "").strip()
                warn_days = 30
                warn_date = (utc_now() + timedelta(days=warn_days)).strftime("%Y-%m-%d")
                today = now_iso()[:10]

                rows = db.execute(
                    """SELECT wd.id AS doc_id, wd.doc_type, wd.expiry_date,
                              w.first_name, w.last_name, w.badge_id, w.company_id,
                              c.name AS company_name, c.billing_email,
                              u.email AS admin_email
                       FROM worker_documents wd
                       JOIN workers w ON w.id = wd.worker_id
                       JOIN companies c ON c.id = w.company_id
                       LEFT JOIN users u ON u.company_id = c.id AND u.role = 'company-admin'
                       WHERE wd.expiry_date IS NOT NULL
                         AND wd.expiry_date <= ?
                         AND wd.expiry_date >= ?
                         AND w.deleted_at IS NULL
                         AND c.deleted_at IS NULL
                       ORDER BY wd.expiry_date ASC""",
                    (warn_date, today),
                ).fetchall()

                by_company: dict = {}
                for row in rows:
                    cid = row["company_id"]
                    if cid not in by_company:
                        by_company[cid] = {
                            "company_name": row["company_name"],
                            "billing_email": row["billing_email"] or "",
                            "admin_email": row["admin_email"] or "",
                            "docs": [],
                        }
                    by_company[cid]["docs"].append(row)

                platform_label = str(settings["platform_name"] or "BauPass").strip() or "BauPass"
                operator_label = str(settings["operator_name"] or platform_label).strip() or platform_label
                _primary = str(settings["invoice_primary_color"] or "#0f4c5c").strip()

                for cid, data in by_company.items():
                    recipient = data["admin_email"] or data["billing_email"]
                    if not recipient:
                        continue
                    alert_code = f"doc_expiry_notification_{cid}_{today}"
                    if db.execute("SELECT id FROM system_alerts WHERE code = ?", (alert_code,)).fetchone():
                        continue  # Heute bereits gesendet

                    doc_lines_text = "\n".join(
                        f"  - {d['first_name']} {d['last_name']} ({d['badge_id']}): {d['doc_type'].replace('_', ' ')} · Ablauf {d['expiry_date']}"
                        for d in data["docs"]
                    )
                    doc_rows_html = "".join(
                        f"<tr><td style='padding:5px 8px'>{d['first_name']} {d['last_name']}</td>"
                        f"<td style='padding:5px 8px'>{d['badge_id']}</td>"
                        f"<td style='padding:5px 8px'>{d['doc_type'].replace('_', ' ')}</td>"
                        f"<td style='padding:5px 8px;color:#c53d2f;font-weight:700'>{d['expiry_date']}</td></tr>"
                        for d in data["docs"]
                    )
                    subject = f"{platform_label}: {len(data['docs'])} Dokument(e) bei {data['company_name']} laufen bald ab"
                    text_body = (
                        f"Guten Tag,\n\nfolgende Dokumente bei {data['company_name']} laufen in den nächsten {warn_days} Tagen ab:\n\n"
                        f"{doc_lines_text}\n\n"
                        f"Bitte aktualisieren Sie die Dokumente rechtzeitig in {platform_label}.\n\n"
                        f"Mit freundlichen Grüßen\n{operator_label}"
                    )
                    html_body = _build_email_html(
                        platform_label, _primary, _primary,
                        "Ablaufende Dokumente",
                        (
                            f"<p style='margin:0 0 10px'>Folgende Dokumente bei <strong>{data['company_name']}</strong> "
                            f"laufen in den nächsten <strong>{warn_days} Tagen</strong> ab:</p>"
                            f"<table style='width:100%;border-collapse:collapse;font-size:13px;border:1px solid #eee'>"
                            f"<thead><tr style='background:#f5f5f5'>"
                            f"<th style='padding:5px 8px;text-align:left'>Name</th>"
                            f"<th style='padding:5px 8px;text-align:left'>Badge-ID</th>"
                            f"<th style='padding:5px 8px;text-align:left'>Dokument</th>"
                            f"<th style='padding:5px 8px;text-align:left'>Ablaufdatum</th>"
                            f"</tr></thead><tbody>{doc_rows_html}</tbody></table>"
                            f"<p style='margin:12px 0 0;font-size:13px;color:#555'>Bitte aktualisieren Sie die Dokumente rechtzeitig.</p>"
                        ),
                        operator_label,
                    )
                    try:
                        smtp_host = (settings["smtp_host"] or "").strip()
                        import email.message as _em2, smtplib as _sl2
                        msg = _em2.EmailMessage()
                        msg["Subject"] = subject
                        msg["From"] = f"{settings['smtp_sender_name']} <{smtp_sender}>" if smtp_sender else operator_label
                        msg["To"] = recipient
                        msg.set_content(text_body)
                        msg.add_alternative(html_body, subtype="html")
                        if smtp_host:
                            with _sl2.SMTP(smtp_host, int(settings["smtp_port"] or 587), timeout=15) as smtp:
                                if int(settings["smtp_use_tls"] or 0):
                                    smtp.starttls()
                                if (settings["smtp_username"] or "").strip():
                                    smtp.login(settings["smtp_username"], settings["smtp_password"] or "")
                                smtp.send_message(msg)
                        else:
                            _send_via_any_api(
                                subject=subject,
                                sender_email=smtp_sender or "",
                                sender_name=settings["smtp_sender_name"] or "",
                                recipient=recipient,
                                text_body=text_body,
                                html_body=html_body,
                            )
                        create_system_alert(
                            db, code=alert_code, severity="info",
                            message=f"Dokument-Ablauf-Benachrichtigung für {len(data['docs'])} Dokument(e) bei {data['company_name']} gesendet.",
                            details={"companyId": cid, "docCount": len(data["docs"]), "recipient": recipient},
                        )
                        db.commit()
                    except Exception:
                        pass
        except Exception:
            pass

    # Expiry-Check beim Start einmal ausführen, danach täglich
    check_doc_expiry_warnings()
    with app.app_context():
        lock_workers_with_expired_documents(get_db())

    def daily_job_loop():
        """Läuft einmal täglich: Dokument-Ablauf-Prüfung + Zusammenfassungs-E-Mail + Ablauf-Erinnerungen."""
        while True:
            time.sleep(86400)  # 24 Stunden warten
            check_doc_expiry_warnings()
            with app.app_context():
                lock_workers_with_expired_documents(get_db())
            send_daily_summary_email()
            send_worker_expiry_reminders()
            send_document_expiry_notifications()

    threading.Thread(target=daily_job_loop, name="baupass-daily-jobs", daemon=True).start()

    def worker_session_cleanup_loop():
        while True:
            try:
                with app.app_context():
                    db = get_db()
                    auto_close_expired_visitor_entries(db)
                    deleted = purge_expired_worker_app_sessions(db)
                    if deleted > 0:
                        db.commit()
            except Exception:
                # Ignore cleanup loop failures; auth still enforces token expiry.
                pass
            time.sleep(session_cleanup_seconds)

    def invoice_retry_loop():
        while True:
            try:
                with app.app_context():
                    db = get_db()
                    result = retry_failed_invoice_deliveries(db)
                    if int(result.get("failed", 0)) > 0:
                        create_system_alert(
                            db,
                            code="invoice_retry_failures",
                            severity="warning",
                            message=f"Automatische Rechnungs-Retries hatten {int(result.get('failed', 0))} Fehlschläge.",
                            details=result,
                            dedup_minutes=15,
                        )

                    summary = get_critical_invoice_retry_summary(
                        db,
                        min_score=70,
                        top_items=INVOICE_RETRY_ALERT_TOP_ITEMS,
                    )
                    critical_count = int(summary.get("criticalCount", 0))
                    if critical_count >= INVOICE_RETRY_CRITICAL_WARN_THRESHOLD:
                        severity = "critical" if critical_count >= INVOICE_RETRY_CRITICAL_ALERT_THRESHOLD else "warning"
                        create_system_alert(
                            db,
                            code=f"invoice_retry_backlog_{severity}",
                            severity=severity,
                            message=(
                                f"Rechnungs-Retry-Queue hat {critical_count} kritische Faelle "
                                f"(Score >= 70)."
                            ),
                            details=summary,
                            dedup_minutes=20,
                        )

                        mail_sent, reason = send_invoice_retry_backlog_alert_email(db, summary, severity)
                        if (not mail_sent) and reason not in {"cooldown", "smtp_not_configured", "no_recipients", "settings_missing"}:
                            create_system_alert(
                                db,
                                code="invoice_retry_backlog_email_failed",
                                severity="warning",
                                message="E-Mail-Alarm fuer kritische Retry-Faelle konnte nicht gesendet werden.",
                                details={"error": reason, "severity": severity, "criticalCount": critical_count},
                                dedup_minutes=30,
                            )

                    smtp_stuck_threshold = utc_iso(
                        utc_now() - timedelta(minutes=INVOICE_SMTP_STUCK_MINUTES)
                    )
                    smtp_stuck_count = db.execute(
                        """
                        SELECT COUNT(*) AS c
                        FROM invoices
                        WHERE status = 'send_failed'
                          AND paid_at IS NULL
                          AND COALESCE(error_message, '') <> ''
                          AND (
                              LOWER(error_message) LIKE '%smtp%'
                              OR LOWER(error_message) LIKE '%timeout%'
                              OR LOWER(error_message) LIKE '%connection refused%'
                              OR LOWER(error_message) LIKE '%network is unreachable%'
                              OR LOWER(error_message) LIKE '%getaddrinfo%'
                              OR LOWER(error_message) LIKE '%name or service%'
                              OR LOWER(error_message) LIKE '%authentication%'
                              OR LOWER(error_message) LIKE '%535%'
                          )
                          AND COALESCE(last_send_attempt_at, created_at) <= ?
                        """,
                        (smtp_stuck_threshold,),
                    ).fetchone()["c"]
                    if int(smtp_stuck_count or 0) > 0:
                        create_system_alert(
                            db,
                            code="invoice_smtp_stuck_failures",
                            severity="critical",
                            message=(
                                f"SMTP-Fehler dauern bereits laenger als {INVOICE_SMTP_STUCK_MINUTES} Minuten an "
                                f"({int(smtp_stuck_count)} Rechnung(en))."
                            ),
                            details={
                                "thresholdMinutes": INVOICE_SMTP_STUCK_MINUTES,
                                "affectedInvoices": int(smtp_stuck_count),
                            },
                            dedup_minutes=15,
                        )
            except Exception:
                pass
            time.sleep(invoice_retry_seconds)

    threading.Thread(target=scheduler_loop, name="baupass-dunning-scheduler", daemon=True).start()
    threading.Thread(target=worker_session_cleanup_loop, name="baupass-worker-session-cleanup", daemon=True).start()
    threading.Thread(target=invoice_retry_loop, name="baupass-invoice-retry", daemon=True).start()


def get_company_access_error(db, company_id):
    if not company_id:
        return None

    company = db.execute("SELECT id, name, status, deleted_at FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        return {"error": "company_not_found", "companyStatus": "unbekannt", "companyName": "Unbekannte Firma"}
    if company["deleted_at"]:
        return {"error": "company_deleted", "companyStatus": "geloescht", "companyName": company["name"]}

    status = (company["status"] or "aktiv").strip().lower()
    if status == "gesperrt":
        return {
            "error": "company_locked",
            "companyStatus": status,
            "companyName": company["name"],
            "message": f"Firma {company['name']} ist wegen offener Zahlung gesperrt.",
        }
    return None


def visible_worker_clause(user, prefix=""):
    if user["role"] == "superadmin":
        preview_id = getattr(g, "preview_company_id", "") if has_request_context() else ""
        if preview_id:
            return f" WHERE {prefix}company_id = ?", [preview_id]
        return "", []
    return f" WHERE {prefix}company_id = ?", [user["company_id"]]


def visible_log_clause(user):
    if user["role"] == "superadmin":
        preview_id = getattr(g, "preview_company_id", "") if has_request_context() else ""
        if preview_id:
            return " WHERE workers.company_id = ?", [preview_id]
        return "", []
    return " WHERE workers.company_id = ?", [user["company_id"]]


def resolve_subcompany_id(db, company_id, subcompany_id):
    candidate = (subcompany_id or "").strip()
    if not candidate:
        return None

    row = db.execute(
        "SELECT * FROM subcompanies WHERE id = ? AND company_id = ?",
        (candidate, company_id),
    ).fetchone()
    if not row:
        raise ValueError("subcompany_not_found")
    if row["deleted_at"]:
        raise ValueError("subcompany_deleted")
    return candidate


def parse_iso_utc(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_access_filters(user, direction="", gate="", from_date="", to_date=""):
    clause, base_params = visible_log_clause(user)
    params = list(base_params)
    conditions = []

    if clause:
        conditions.append(clause.replace(" WHERE ", "", 1))

    conditions.append("workers.deleted_at IS NULL")

    if direction:
        conditions.append("access_logs.direction = ?")
        params.append(direction)

    if gate:
        conditions.append("lower(access_logs.gate) LIKE ?")
        params.append(f"%{gate.lower()}%")

    if from_date:
        conditions.append("access_logs.timestamp >= ?")
        params.append(f"{from_date}T00:00:00Z")

    if to_date:
        conditions.append("access_logs.timestamp <= ?")
        params.append(f"{to_date}T23:59:59Z")

    return conditions, params


def build_open_entries_from_rows(rows, now_dt):
    last_event_by_worker = {}
    for row in rows:
        last_event_by_worker[row["worker_id"]] = {
            "workerId": row["worker_id"],
            "name": f"{row['first_name']} {row['last_name']}",
            "badgeId": row["badge_id"],
            "gate": row["gate"],
            "timestamp": row["timestamp"],
            "direction": row["direction"],
        }
    open_entries = []
    for item in last_event_by_worker.values():
        if item["direction"] != "check-in":
            continue

        entry_dt = parse_iso_utc(item["timestamp"])
        minutes_open = 0
        if entry_dt:
            minutes_open = max(int((now_dt - entry_dt).total_seconds() // 60), 0)

        if minutes_open >= 240:
            severity = "red"
        elif minutes_open >= 120:
            severity = "yellow"
        else:
            severity = "green"

        open_entries.append(
            {
                **item,
                "openMinutes": minutes_open,
                "severity": severity,
            }
        )

    open_entries.sort(key=lambda entry: entry["timestamp"], reverse=True)
    return open_entries


def auto_close_expired_visitor_entries(db, reference_dt=None):
    now_dt = reference_dt or datetime.now(timezone.utc)
    rows = db.execute(
        """
        SELECT workers.id AS worker_id, workers.first_name, workers.last_name, workers.badge_id,
               workers.visit_end_at, access_logs.direction, access_logs.gate, access_logs.timestamp
        FROM workers
        JOIN (
            SELECT worker_id, MAX(timestamp) AS latest_ts
            FROM access_logs
            GROUP BY worker_id
        ) latest ON latest.worker_id = workers.id
        JOIN access_logs ON access_logs.worker_id = latest.worker_id AND access_logs.timestamp = latest.latest_ts
        WHERE workers.deleted_at IS NULL
          AND workers.worker_type = 'visitor'
          AND workers.visit_end_at != ''
          AND access_logs.direction = 'check-in'
        """
    ).fetchall()

    auto_closed = []
    for row in rows:
        visit_end_dt = parse_iso_utc(row["visit_end_at"])
        if not visit_end_dt or visit_end_dt > now_dt:
            continue
        close_timestamp = visit_end_dt.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"
        log_id = f"log-{secrets.token_hex(6)}"
        db.execute(
            "INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (
                log_id,
                row["worker_id"],
                "check-out",
                row["gate"] or "System Besucherende",
                "Automatischer Austritt nach Besucher-Ende",
                close_timestamp,
            ),
        )
        auto_closed.append(
            {
                "workerId": row["worker_id"],
                "name": f"{row['first_name']} {row['last_name']}",
                "badgeId": row["badge_id"],
                "timestamp": close_timestamp,
            }
        )

    if auto_closed:
        db.commit()
        log_audit(
            "access.auto_visitor_close",
            f"{len(auto_closed)} Besucher automatisch nach Ablauf ausgetragen",
            target_type="access",
            target_id=now_dt.date().isoformat(),
        )

    return auto_closed


def auto_close_open_entries_after_midnight(db):
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_iso = day_start.isoformat().replace("+00:00", "Z")

    rows = db.execute(
        """
        SELECT workers.id AS worker_id, workers.company_id, workers.first_name, workers.last_name, workers.badge_id,
               access_logs.direction, access_logs.gate, access_logs.timestamp
        FROM workers
        JOIN (
            SELECT worker_id, MAX(timestamp) AS latest_ts
            FROM access_logs
            GROUP BY worker_id
        ) latest ON latest.worker_id = workers.id
        JOIN access_logs ON access_logs.worker_id = latest.worker_id AND access_logs.timestamp = latest.latest_ts
        WHERE workers.deleted_at IS NULL
          AND access_logs.direction = 'check-in'
          AND access_logs.timestamp < ?
        """,
        (day_start_iso,),
    ).fetchall()

    auto_closed = []
    for row in rows:
        log_id = f"log-{secrets.token_hex(6)}"
        db.execute(
            "INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (
                log_id,
                row["worker_id"],
                "check-out",
                row["gate"] or "System Tagesabschluss",
                "Automatischer Austritt nach 00:00",
                day_start_iso,
            ),
        )
        auto_closed.append(
            {
                "workerId": row["worker_id"],
                "name": f"{row['first_name']} {row['last_name']}",
                "badgeId": row["badge_id"],
                "timestamp": day_start_iso,
            }
        )

    if auto_closed:
        db.commit()
        log_audit(
            "access.auto_day_close",
            f"{len(auto_closed)} offene Eintritte nach 00:00 automatisch ausgetragen",
            target_type="access",
            target_id=day_start.date().isoformat(),
        )

    return auto_closed


@app.get("/api/health")
def health():
    diagnostics = get_runtime_diagnostics()
    db_path_str = str(DB_PATH)
    data_dir_exists = Path("/data").is_dir()
    data_dir_writable = data_dir_exists and os.access(Path("/data"), os.W_OK)
    db_file_exists = DB_PATH.exists()
    return jsonify(
        {
            "status": "ok",
            "time": now_iso(),
            "warnings": len(diagnostics["warnings"]),
            "recoveryEnabled": diagnostics["recoveryEnabled"],
            "gateApiConfigured": diagnostics["gateApiConfigured"],
            "db": {
                "path": db_path_str,
                "persistent": db_path_str.startswith("/data/"),
                "exists": db_file_exists,
                "sizeBytes": DB_PATH.stat().st_size if db_file_exists else 0,
                "dataDirExists": data_dir_exists,
                "dataDirWritable": data_dir_writable,
                "envVar": os.getenv("BAUPASS_DB_PATH", ""),
            },
        }
    )


@app.get("/api/public/branding")
def public_branding():
    """Oeffentlicher Endpunkt fuer Branding-Informationen (kein Login noetig)."""
    try:
        db = get_db()
        row = db.execute(
            "SELECT platform_name, invoice_primary_color, invoice_accent_color, invoice_logo_data FROM settings WHERE id = 1"
        ).fetchone()
        if not row:
            return jsonify({"platformName": "BauPass", "primaryColor": "#0f4c5c", "accentColor": "#e36414", "logoData": ""})
        return jsonify({
            "platformName": str(row["platform_name"] or "BauPass"),
            "primaryColor": str(row["invoice_primary_color"] or "#0f4c5c"),
            "accentColor": str(row["invoice_accent_color"] or "#e36414"),
            "logoData": str(row["invoice_logo_data"] or ""),
        })
    except Exception:
        return jsonify({"platformName": "BauPass", "primaryColor": "#0f4c5c", "accentColor": "#e36414", "logoData": ""})


@app.get("/api/phone-test")
def phone_test_api():
        return jsonify(
                {
                        "status": "ok",
                        "time": now_iso(),
                        "host": request.host,
                        "remoteAddr": request.remote_addr,
                        "userAgent": request.headers.get("User-Agent", ""),
                }
        )


@app.get("/phone-test")
def phone_test_page():
        host = html.escape(request.host or "")
        remote_addr = html.escape(request.remote_addr or "")
        user_agent = html.escape(request.headers.get("User-Agent", ""))
        now_value = html.escape(now_iso())
        return f"""
<!DOCTYPE html>
<html lang=\"de\" translate=\"no\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <meta name=\"google\" content=\"notranslate\" />
    <meta http-equiv=\"Content-Language\" content=\"de\" />
    <title>BauPass Telefon-Test</title>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Arial, sans-serif;
            background: #f8f7f4;
            color: #1f1f1f;
        }}
        .card {{
            max-width: 700px;
            margin: 0 auto;
            background: #ffffff;
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 16px;
        }}
        .ok {{
            color: #0a7a2f;
            font-weight: 700;
            margin: 0 0 12px;
        }}
        .row {{
            margin: 6px 0;
            word-break: break-all;
        }}
    </style>
</head>
<body>
    <main class=\"card\">
        <p class=\"ok\">BauPass Telefon-Test: ERREICHBAR</p>
        <p class=\"row\"><strong>Zeit:</strong> {now_value}</p>
        <p class=\"row\"><strong>Host:</strong> {host}</p>
        <p class=\"row\"><strong>Client-IP:</strong> {remote_addr}</p>
        <p class=\"row\"><strong>User-Agent:</strong> {user_agent}</p>
    </main>
</body>
</html>
"""


def get_runtime_diagnostics():
    resend_api_key, resend_key_source = _get_resend_api_key_and_source()
    brevo_api_key = _get_brevo_api_key()
    diagnostics = {
        "warnings": [],
        "recoveryEnabled": bool((os.getenv("BAUPASS_RECOVERY_SECRET") or "").strip()),
        "gateApiConfigured": bool((os.getenv("BAUPASS_GATE_API_KEY") or "").strip()),
        "publicBaseUrlConfigured": bool((os.getenv("PUBLIC_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip()),
        "resendConfigured": bool(resend_api_key),
        "resendKeySource": resend_key_source,
        "brevoConfigured": bool(brevo_api_key),
    }

    if not diagnostics["recoveryEnabled"]:
        diagnostics["warnings"].append(
            {
                "code": "missing_recovery_secret",
                "message": "BAUPASS_RECOVERY_SECRET ist nicht gesetzt. Admin-Recovery ist deaktiviert.",
            }
        )
    if not diagnostics["gateApiConfigured"]:
        diagnostics["warnings"].append(
            {
                "code": "missing_gate_api_key",
                "message": "BAUPASS_GATE_API_KEY ist nicht gesetzt. NFC-Gate-Tap ist deaktiviert.",
            }
        )
    if not diagnostics["publicBaseUrlConfigured"]:
        diagnostics["warnings"].append(
            {
                "code": "missing_public_base_url",
                "message": "PUBLIC_BASE_URL ist nicht gesetzt. Externe Links koennen auf lokalen Host zeigen.",
            }
        )
    if not diagnostics["resendConfigured"] and not diagnostics["brevoConfigured"]:
        diagnostics["warnings"].append(
            {
                "code": "missing_resend_api_key",
                "message": (
                    "Kein API-Fallback-Key erkannt. Brevo-Key in Einstellungen setzen "
                    "(empfohlen) oder RESEND_API_KEY / RESEND_KEY / RESEND_API_TOKEN bereitstellen."
                ),
            }
        )

    db = None
    try:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        admin_rows = db.execute("SELECT username, role, password_hash FROM users WHERE role IN ('superadmin', 'company-admin', 'turnstile')").fetchall()
        weak_users = [row["username"] for row in admin_rows if check_password_hash(row["password_hash"], "1234")]
        if weak_users:
            diagnostics["warnings"].append(
                {
                    "code": "default_passwords_present",
                    "message": f"Standardpasswort 1234 noch aktiv fuer: {', '.join(weak_users[:10])}",
                }
            )
    except Exception as exc:
        diagnostics["warnings"].append(
            {
                "code": "runtime_diagnostics_failed",
                "message": f"Runtime-Diagnose konnte nicht vollstaendig gelesen werden: {exc}",
            }
        )
    finally:
        if db is not None:
            db.close()

    return diagnostics


@app.get("/api/qr.png")
def qr_png():
    data = (request.args.get("data") or "").strip()
    if not data:
        return jsonify({"error": "missing_data"}), 400

    try:
        size = int(request.args.get("size") or 280)
    except ValueError:
        size = 280
    size = max(120, min(size, 1024))

    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((size, size))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return Response(buffer.getvalue(), mimetype="image/png")


@app.get("/api/qr")
def qr_data_url():
    data = (request.args.get("data") or "").strip()
    if not data:
        return jsonify({"error": "missing_data"}), 400

    try:
        size = int(request.args.get("size") or 280)
    except ValueError:
        size = 280
    size = max(120, min(size, 1024))

    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((size, size))

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = buffer.getvalue().hex()
    # hex-to-bytes on client is simple and avoids binary transport issues in JSON.
    return jsonify({"pngHex": encoded})


@app.post("/api/login")
@require_rate_limit("login")
def login():
    def login_error(code, **extra):
        payload = {"ok": False, "error": code}
        payload.update(extra)
        return jsonify(payload)

    throttle_key = build_login_throttle_key()
    allowed, retry_after = can_attempt_login(throttle_key)
    if not allowed:
        return login_error("too_many_attempts", retryAfterSeconds=retry_after)

    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip().lower()
    password = payload.get("password") or ""
    otp_code = (payload.get("otpCode") or "").strip()
    login_scope = (payload.get("loginScope") or "auto").strip().lower()
    support_company_id = (payload.get("supportCompanyId") or "").strip()
    support_actor_name = (payload.get("supportActorName") or "").strip()

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE lower(username) = ?", (username,)).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        register_login_failure(throttle_key)
        log_audit("login.failed", f"Fehlgeschlagener Login fuer {username or 'unbekannt'}")
        return login_error("invalid_credentials")

    required_role_by_scope = {
        "server-admin": "superadmin",
        "company-admin": "company-admin",
        "turnstile": "turnstile",
    }
    required_role = required_role_by_scope.get(login_scope)
    if required_role and user["role"] != required_role:
        register_login_failure(throttle_key)
        log_audit("login.failed", f"Login-Typ passt nicht zu {username or 'unbekannt'}")
        return login_error("login_scope_mismatch")

    twofa_enabled = int(user["twofa_enabled"]) == 1
    turnstile_auto_2fa = user["role"] == "turnstile"
    if twofa_enabled and not turnstile_auto_2fa:
        user_keys = set(user.keys()) if hasattr(user, "keys") else set()
        user_email = (user["email"] if "email" in user_keys else "").strip()

        if not otp_code:
            # Step 1: credentials correct – send OTP via email
            if user_email:
                otp = str(secrets.randbelow(900000) + 100000)
                otp_id = secrets.token_urlsafe(16)
                expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                db.execute("DELETE FROM otp_codes WHERE user_id = ?", (user["id"],))
                db.execute(
                    "INSERT INTO otp_codes (id, user_id, code, expires_at) VALUES (?,?,?,?)",
                    (otp_id, user["id"], otp, expires)
                )
                db.commit()
                sent = _send_otp_email_to_user(db, user, otp)
                if not sent:
                    # E-Mail-Versand fehlgeschlagen → Code im Server-Log ausgeben als Notfall-Fallback
                    app.logger.warning(
                        f"[OTP-FALLBACK] Kein SMTP konfiguriert oder Versand fehlgeschlagen – "
                        f"OTP fuer Benutzer '{user['username']}': {otp}"
                    )
                # Return "otp_sent" – NOT a login failure
                return login_error("otp_sent")
            else:
                # No email configured: fall back to TOTP prompt
                register_login_failure(throttle_key)
                return login_error("otp_required")
        else:
            # Step 2: verify submitted OTP
            now_str = datetime.now(timezone.utc).isoformat()
            otp_row = db.execute(
                "SELECT id FROM otp_codes WHERE user_id = ? AND code = ? AND expires_at > ?",
                (user["id"], otp_code, now_str)
            ).fetchone()
            if otp_row:
                db.execute("DELETE FROM otp_codes WHERE user_id = ?", (user["id"],))
                db.commit()
            else:
                # Fallback: try TOTP (authenticator app)
                secret = (user["twofa_secret"] or "").strip()
                if not (secret and pyotp.TOTP(secret).verify(otp_code, valid_window=1)):
                    register_login_failure(throttle_key)
                    return login_error("otp_invalid")

    if not is_tenant_host_valid(db, row_to_dict(user)):
        register_login_failure(throttle_key)
        return login_error("forbidden_tenant_host")

    if user["role"] != "superadmin":
        company_error = get_company_access_error(db, user["company_id"])
        if company_error:
            log_audit("login.blocked", f"Login fuer {user['username']} wegen Firmensperre blockiert", target_type="company", target_id=user["company_id"])
            return login_error(company_error["error"], companyStatus=company_error["companyStatus"], companyName=company_error["companyName"], message=company_error.get("message", ""))

    support_read_only = 0
    support_company_name = ""
    if support_company_id:
        if user["role"] != "company-admin" or user["company_id"] != support_company_id:
            register_login_failure(throttle_key)
            return login_error("support_company_mismatch")
        company_row = db.execute("SELECT id, name FROM companies WHERE id = ?", (support_company_id,)).fetchone()
        if not company_row:
            register_login_failure(throttle_key)
            return login_error("company_not_found")
        support_read_only = 1
        support_company_name = company_row["name"] or ""

    clear_login_failures(throttle_key)

    token = secrets.token_urlsafe(24)
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
    db.execute(
        """
        INSERT INTO sessions (token, user_id, expires_at, support_read_only, support_company_name, support_actor_name)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (token, user["id"], expiry_iso(), support_read_only, support_company_name, support_actor_name),
    )
    db.commit()

    login_message = f"Benutzer {user['username']} angemeldet"
    if support_read_only:
        actor_label = support_actor_name or "Support"
        login_message = f"Support-Login fuer {support_company_name or user['username']} gestartet durch {actor_label} (nur lesen)"
    log_audit("login.success", login_message, target_type="user", target_id=user["id"], actor=row_to_dict(user), company_id=user["company_id"])

    response_user = row_to_dict(user)
    response_user["support_read_only"] = bool(support_read_only)
    response_user["support_company_name"] = support_company_name
    response_user["support_actor_name"] = support_actor_name
    response = jsonify({"ok": True, "token": token, "user": serialize_user(response_user)})
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="None" if should_use_cross_site_cookie() else "Lax",
        secure=is_request_secure(),
    )
    return response


@app.post("/api/logout")
@require_auth
def logout():
    get_db().execute("DELETE FROM sessions WHERE token = ?", (g.token,))
    get_db().commit()
    log_audit("login.logout", f"Benutzer {g.current_user['username']} abgemeldet", target_type="user", target_id=g.current_user["id"], actor=g.current_user)
    response = jsonify({"ok": True})
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/api/me")
@require_auth
def me():
    return jsonify({"user": serialize_user(g.current_user)})


@app.get("/api/session/bootstrap")
def session_bootstrap():
    token = get_auth_token_from_request()

    user = get_user_from_session_token(token)
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    db = get_db()
    if not is_tenant_host_valid(db, user):
        return jsonify({"error": "forbidden_tenant_host"}), 403

    if user.get("role") != "superadmin":
        company_error = get_company_access_error(db, user.get("company_id"))
        if company_error:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            db.commit()
            return jsonify(company_error), 403

    if user.get("role") in ["superadmin", "company-admin"]:
        settings_row = db.execute("SELECT admin_ip_whitelist FROM settings WHERE id = 1").fetchone()
        whitelist = parse_ip_whitelist(settings_row["admin_ip_whitelist"] if settings_row else "")
        if whitelist and not ip_allowed(get_client_ip(), whitelist):
            return jsonify({"error": "admin_ip_not_allowed"}), 403

    db.execute("UPDATE sessions SET expires_at = ? WHERE token = ?", (expiry_iso(), token))
    db.commit()

    return jsonify({"token": token, "user": serialize_user(user)})


@app.get("/api/system/status")
@require_auth
@require_roles("superadmin")
def system_status():
    db = get_db()
    active_sessions = db.execute("SELECT COUNT(*) AS c FROM sessions WHERE expires_at >= ?", (now_iso(),)).fetchone()["c"]
    worker_sessions = db.execute("SELECT COUNT(*) AS c FROM worker_app_sessions WHERE expires_at >= ?", (now_iso(),)).fetchone()["c"]
    open_entries = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM (
            SELECT access_logs.worker_id, MAX(access_logs.timestamp) AS latest_ts
            FROM access_logs
            JOIN workers ON workers.id = access_logs.worker_id
            WHERE workers.deleted_at IS NULL
            GROUP BY access_logs.worker_id
        ) latest
        JOIN access_logs ON access_logs.worker_id = latest.worker_id AND access_logs.timestamp = latest.latest_ts
        WHERE access_logs.direction = 'check-in'
        """
    ).fetchone()["c"]

    recent_issues = db.execute(
        """
        SELECT event_type, message, created_at
        FROM audit_logs
        WHERE event_type IN ('login.failed', 'security.password_changed', 'access.booked')
           OR event_type LIKE 'company.%'
           OR event_type LIKE 'worker.%'
        ORDER BY created_at DESC
        LIMIT 20
        """
    ).fetchall()

    locks = []
    now = utc_now()
    for key, state in list(failed_login_attempts.items()):
        locked_until = state.get("locked_until")
        if not locked_until:
            continue
        if locked_until <= now:
            failed_login_attempts.pop(key, None)
            continue
        locks.append(
            {
                "key": key,
                "retryAfterSeconds": int((locked_until - now).total_seconds()),
            }
        )

    session_details = db.execute(
        """
        SELECT s.last_seen, u.name, u.role, u.username
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.expires_at >= ?
        ORDER BY s.last_seen DESC
        LIMIT 20
        """,
        (now_iso(),),
    ).fetchall()

    setting = db.execute("SELECT worker_app_enabled FROM settings WHERE id = 1").fetchone()

    return jsonify(
        {
            "serverTime": now_iso(),
            "currentHost": get_request_host(),
            "currentIp": get_client_ip(),
            "activeSessions": active_sessions,
            "activeWorkerSessions": worker_sessions,
            "openEntries": open_entries,
            "loginLocks": locks[:50],
            "recentIssues": [row_to_dict(row) for row in recent_issues],
            "sessionDetails": [
                {
                    "name": row["name"],
                    "role": row["role"],
                    "username": row["username"],
                    "lastSeen": row["last_seen"],
                }
                for row in session_details
            ],
            "workerAppEnabled": int(setting["worker_app_enabled"]) == 1 if setting else True,
        }
    )


@app.get("/api/system/runtime-check")
@require_auth
@require_roles("superadmin")
def system_runtime_check():
    diagnostics = get_runtime_diagnostics()
    return jsonify({"ok": True, "serverTime": now_iso(), **diagnostics})


@app.post("/api/system/recover-admin")
def system_recover_admin():
    configured_secret = (os.getenv("BAUPASS_RECOVERY_SECRET") or "").strip()
    if not configured_secret:
        return jsonify({"ok": False, "error": "recovery_disabled"}), 503

    payload = request.get_json(silent=True) or {}
    provided_secret = (payload.get("recoverySecret") or request.headers.get("X-Recovery-Secret") or "").strip()
    if not provided_secret or not secrets.compare_digest(provided_secret, configured_secret):
        log_audit("system.recovery_failed", "Recovery-Versuch mit ungueltigem Secret")
        return jsonify({"ok": False, "error": "invalid_recovery_secret"}), 401

    username = (payload.get("username") or os.getenv("BAUPASS_RECOVERY_USERNAME") or "superadmin").strip().lower()
    new_password = payload.get("newPassword") or ""
    if len(new_password) < 8:
        return jsonify({"ok": False, "error": "password_too_short"}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE lower(username) = ?", (username,)).fetchone()
    if not user:
        return jsonify({"ok": False, "error": "user_not_found"}), 404
    if user["role"] not in {"superadmin", "company-admin", "turnstile"}:
        return jsonify({"ok": False, "error": "recovery_not_allowed_for_role"}), 403

    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), user["id"]))
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
    db.commit()
    clear_login_failures_for_username(username)
    log_audit(
        "system.recovery_password_reset",
        f"Recovery-Passwortreset fuer {username}",
        target_type="user",
        target_id=user["id"],
    )
    return jsonify({"ok": True, "username": username, "role": user["role"]})


@app.post("/api/superadmin/preview-session")
@require_auth
@require_roles("superadmin")
def set_superadmin_preview_session():
    data = request.json or {}
    company_id = (data.get("company_id") or "").strip()
    db = get_db()
    if company_id:
        company = db.execute("SELECT id, name FROM companies WHERE id = ? AND deleted_at IS NULL", (company_id,)).fetchone()
        if not company:
            return jsonify({"error": "company_not_found"}), 404
        db.execute("UPDATE sessions SET preview_company_id = ? WHERE token = ?", (company_id, g.token))
        db.commit()
        log_audit(
            "superadmin.preview_session.start",
            f"Superadmin-Vorschau gestartet fuer Unternehmen: {company['name']} ({company_id})",
            target_type="company",
            target_id=company_id,
            actor=g.current_user,
        )
        return jsonify({"ok": True, "preview_company_id": company_id})
    else:
        db.execute("UPDATE sessions SET preview_company_id = NULL WHERE token = ?", (g.token,))
        db.commit()
        return jsonify({"ok": True, "preview_company_id": None})


@app.post("/api/system/repair")
@require_auth
@require_roles("superadmin")
def system_repair():
    db = get_db()
    now = now_iso()
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    db.execute("DELETE FROM worker_app_sessions WHERE expires_at < ?", (now,))
    db.execute("DELETE FROM worker_app_tokens WHERE expires_at < ?", (now,))
    db.commit()
    failed_login_attempts.clear()
    log_audit("system.repair", "System-Reparatur ausgefuehrt (abgelaufene Sitzungen bereinigt, Login-Sperren geloescht)", actor=g.current_user)
    return jsonify({"ok": True})


@app.post("/api/me/heartbeat")
def heartbeat():
    token = get_auth_token_from_request()
    if not token:
        return jsonify({"ok": True, "active": False})

    db = get_db()
    session = db.execute("SELECT expires_at FROM sessions WHERE token = ?", (token,)).fetchone()
    if not session:
        return jsonify({"ok": True, "active": False})

    if session["expires_at"] < now_iso():
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.commit()
        return jsonify({"ok": True, "active": False})

    db.execute("UPDATE sessions SET last_seen = ?, expires_at = ? WHERE token = ?", (now_iso(), expiry_iso(), token))
    db.commit()
    return jsonify({"ok": True, "active": True})


@app.post("/api/me/password")
@require_auth
def change_password():
    payload = request.get_json(silent=True) or {}
    current_password = payload.get("currentPassword") or ""
    new_password = payload.get("newPassword") or ""

    if len(new_password) < 8:
        return jsonify({"error": "password_too_short"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (g.current_user["id"],)).fetchone()
    if not row or not check_password_hash(row["password_hash"], current_password):
        return jsonify({"error": "invalid_current_password"}), 400

    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), g.current_user["id"]))
    db.execute("DELETE FROM sessions WHERE user_id = ?", (g.current_user["id"],))
    db.commit()
    log_audit("security.password_changed", "Passwort wurde geaendert", target_type="user", target_id=g.current_user["id"], actor=g.current_user)
    return jsonify({"ok": True})


@app.get("/api/me/2fa")
@require_auth
def get_twofa_status():
    return jsonify({"enabled": int(g.current_user["twofa_enabled"]) == 1})


@app.post("/api/me/2fa/activate")
@require_auth
def activate_twofa():
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (g.current_user["id"],)).fetchone()
    user_keys = set(row.keys()) if hasattr(row, "keys") else set()
    user_email = (row["email"] if "email" in user_keys else "").strip()
    if not user_email:
        return jsonify({"error": "email_required"}), 400
    secret = pyotp.random_base32()
    db.execute("UPDATE users SET twofa_secret = ?, twofa_enabled = 1 WHERE id = ?", (secret, g.current_user["id"]))
    db.commit()
    log_audit("security.2fa_enabled", "2FA wurde aktiviert", target_type="user", target_id=g.current_user["id"], actor=g.current_user)
    return jsonify({"ok": True})


@app.post("/api/me/2fa/disable")
@require_auth
def disable_twofa():
    db = get_db()
    db.execute("UPDATE users SET twofa_enabled = 0 WHERE id = ?", (g.current_user["id"],))
    db.commit()
    log_audit("security.2fa_disabled", "2FA wurde deaktiviert", target_type="user", target_id=g.current_user["id"], actor=g.current_user)
    return jsonify({"ok": True})


@app.post("/api/emergency/disable-2fa")
def emergency_disable_twofa():
    """Emergency endpoint: disable 2FA for a user using a server-side secret token."""
    emergency_token = os.getenv("BAUPASS_EMERGENCY_TOKEN", "").strip()
    if not emergency_token:
        return jsonify({"error": "not_configured"}), 403
    payload = request.get_json(silent=True) or {}
    submitted = (payload.get("token") or "").strip()
    username = (payload.get("username") or "").strip()
    if not submitted or not username:
        return jsonify({"error": "missing_fields"}), 400
    # Constant-time compare to avoid timing attacks
    import hmac as _hmac
    if not _hmac.compare_digest(submitted, emergency_token):
        return jsonify({"error": "forbidden"}), 403
    db = get_db()
    user = db.execute("SELECT id, username, twofa_enabled FROM users WHERE username = ?", (username,)).fetchone()
    if not user:
        return jsonify({"error": "user_not_found"}), 404
    db.execute("UPDATE users SET twofa_enabled = 0, email = '' WHERE id = ?", (user["id"],))
    db.execute("DELETE FROM otp_codes WHERE user_id = ?", (user["id"],))
    db.commit()
    app.logger.warning(f"[EMERGENCY] 2FA deaktiviert fuer Benutzer '{username}' via Emergency-Endpunkt")
    return jsonify({"ok": True, "username": username})


@app.put("/api/me/email")
@require_auth
def update_me_email():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({"error": "invalid_email"}), 400
    db = get_db()
    db.execute("UPDATE users SET email = ? WHERE id = ?", (email, g.current_user["id"]))
    db.commit()
    return jsonify({"ok": True, "email": email})


@app.get("/api/settings")
@require_auth
def get_settings():
    row = get_db().execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return jsonify(
        {
            "platformName": row["platform_name"],
            "operatorName": row["operator_name"],
            "turnstileEndpoint": row["turnstile_endpoint"],
            "rentalModel": row["rental_model"],
            "invoiceLogoData": row["invoice_logo_data"],
            "invoicePrimaryColor": row["invoice_primary_color"],
            "invoiceAccentColor": row["invoice_accent_color"],
            "invoiceIban": row["invoice_iban"] if "invoice_iban" in row.keys() else "",
            "invoiceBic": row["invoice_bic"] if "invoice_bic" in row.keys() else "",
            "invoiceBankName": row["invoice_bank_name"] if "invoice_bank_name" in row.keys() else "",
            "invoiceTaxId": row["invoice_tax_id"] if "invoice_tax_id" in row.keys() else "",
            "invoiceVatId": row["invoice_vat_id"] if "invoice_vat_id" in row.keys() else "",
            "invoiceOperatorStreet": row["invoice_operator_street"] if "invoice_operator_street" in row.keys() else "",
            "invoiceOperatorZipCity": row["invoice_operator_zip_city"] if "invoice_operator_zip_city" in row.keys() else "",
            "invoiceOperatorPhone": row["invoice_operator_phone"] if "invoice_operator_phone" in row.keys() else "",
            "invoiceOperatorWebsite": row["invoice_operator_website"] if "invoice_operator_website" in row.keys() else "",
            "invoiceOperatorEmail": row["invoice_operator_email"] if "invoice_operator_email" in row.keys() else "",
            "invoiceEmailSubject": row["invoice_email_subject"] if "invoice_email_subject" in row.keys() else "",
            "invoiceEmailIntro": row["invoice_email_intro"] if "invoice_email_intro" in row.keys() else "",
            "smtpHost": row["smtp_host"],
            "smtpPort": row["smtp_port"],
            "smtpUsername": row["smtp_username"],
            "smtpPassword": row["smtp_password"],
            "smtpSenderEmail": row["smtp_sender_email"],
            "smtpSenderName": row["smtp_sender_name"],
            "smtpUseTls": int(row["smtp_use_tls"]) == 1,
            "adminIpWhitelist": row["admin_ip_whitelist"],
            "enforceTenantDomain": int(row["enforce_tenant_domain"]) == 1,
            "workerAppEnabled": int(row["worker_app_enabled"]) == 1,
            "imapHost": row["imap_host"],
            "imapPort": int(row["imap_port"] or 993),
            "imapUsername": row["imap_username"],
            "imapPassword": row["imap_password"],
            "imapFolder": row["imap_folder"] or "INBOX",
            "imapUseSsl": int(row["imap_use_ssl"]) == 1,
            "impressumText": row["impressum_text"] or "",
            "datenschutzText": row["datenschutz_text"] or "",
            "resendApiKey": row["resend_api_key"] if "resend_api_key" in row.keys() else "",
            "resendFromEmail": row["resend_from_email"] if "resend_from_email" in row.keys() else "",
            "brevoApiKey": row["brevo_api_key"] if "brevo_api_key" in row.keys() else "",
            "brevoFromEmail": row["brevo_from_email"] if "brevo_from_email" in row.keys() else "",
        }
    )


@app.post("/api/settings/smtp-test")
@require_auth
@require_roles("superadmin")
def smtp_test():
    """Send a test e-mail using the currently saved SMTP settings."""
    db = get_db()
    payload = request.get_json(silent=True) or {}
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if not settings:
        return jsonify({"ok": False, "error": "no_settings"}), 400
    smtp_settings = _resolve_smtp_settings(settings, payload)
    missing_fields = []
    if not smtp_settings["smtp_host"]:
        missing_fields.append("smtpHost")
    if not smtp_settings["smtp_sender_email"]:
        missing_fields.append("smtpSenderEmail")
    if missing_fields:
        return jsonify({"ok": False, "error": "smtp_not_configured", "missingFields": missing_fields}), 400
    # Send to the logged-in user's email, or the sender address as fallback
    recipient = (str(payload.get("recipient") or "").strip() or (g.current_user["email"] or "").strip() or smtp_settings["smtp_sender_email"])
    platform_name = smtp_settings["platform_name"]
    smtp_sender_name = smtp_settings["smtp_sender_name"]
    primary_color = smtp_settings["invoice_primary_color"]
    accent_color = smtp_settings["invoice_accent_color"]
    try:
        msg = EmailMessage()
        msg["Subject"] = f"{platform_name}: SMTP Test-Mail ✅"
        msg["From"] = f'"{smtp_sender_name}" <{smtp_settings["smtp_sender_email"]}>'
        msg["To"] = recipient
        body_html = f"""
            <p style="color:#374151;font-size:15px;line-height:1.6;margin:0 0 20px;">
                Diese E-Mail bestätigt, dass SMTP für <strong>{platform_name}</strong> korrekt konfiguriert ist.
            </p>
            <table cellpadding="0" cellspacing="0" style="background:#f0fdf4;border-left:4px solid #16a34a;border-radius:0 8px 8px 0;padding:14px 18px;margin-bottom:24px;width:100%;">
                <tr><td>
                    <p style="margin:0 0 6px;color:#15803d;font-size:14px;font-weight:700;">✅ Verbindung erfolgreich</p>
                    <p style="margin:0;color:#374151;font-size:13px;">
                        <strong>Empfänger:</strong> {recipient}<br>
                        <strong>Absender:</strong> {smtp_settings["smtp_sender_email"]}<br>
                        <strong>SMTP-Host:</strong> {smtp_settings["smtp_host"]}:{smtp_settings["smtp_port"]}
                    </p>
                </td></tr>
            </table>
            <p style="color:#6c757d;font-size:13px;margin:0;">
                OTP-Codes für die Zwei-Faktor-Anmeldung werden ab sofort an diese Adresse zugestellt.
            </p>"""
        operator_name = smtp_settings["operator_name"]
        html_content = _build_email_html(platform_name, primary_color, accent_color,
                                         "SMTP Konfiguration erfolgreich", body_html, operator_name)
        text_content = (
            f"SMTP Test erfolgreich.\nEmpfänger: {recipient}\nAbsender: {smtp_settings['smtp_sender_email']}\n"
            f"Host: {smtp_settings['smtp_host']}\n\n{operator_name}"
        )
        msg.set_content(text_content)
        msg.add_alternative(html_content, subtype="html")
        with _smtp_connect(smtp_settings["smtp_host"], smtp_settings["smtp_port"], smtp_settings["smtp_use_tls"]) as s:
            smtp_username = smtp_settings["smtp_username"]
            if smtp_username:
                s.login(smtp_username, smtp_settings["smtp_password"])
            s.send_message(msg)
        app.logger.info(f"[SMTP-TEST] Test-Mail erfolgreich gesendet an {recipient}")
        return jsonify({"ok": True, "recipient": recipient})
    except Exception as exc:
        diag_result = _run_smtp_diagnostics(smtp_settings)
        app.logger.error(f"[SMTP-TEST] Fehler beim Senden an {recipient}: {exc}")
        resend_api_key, resend_key_source = _get_resend_api_key_and_source()
        brevo_api_key = _get_brevo_api_key()
        resend_env = _collect_resend_env_presence()
        fallback_ok, fallback_error, fallback_provider = _send_via_any_api(
            subject=msg["Subject"] if "msg" in locals() else f"{platform_name}: SMTP Test-Mail",
            sender_email=smtp_settings["smtp_sender_email"],
            sender_name=smtp_settings["smtp_sender_name"],
            recipient=recipient,
            text_body=text_content if "text_content" in locals() else "SMTP Test",
            html_body=html_content if "html_content" in locals() else "<p>SMTP Test</p>",
        )
        if fallback_ok:
            app.logger.warning(f"[SMTP-TEST] SMTP ausgefallen, Test-Mail über API-Fallback versendet an {recipient}")
            return jsonify({"ok": True, "recipient": recipient, "delivery": fallback_provider})
        if not diag_result.get("ok"):
            app.logger.error(
                f"[SMTP-TEST-DIAG] stage={diag_result.get('stage')} type={diag_result.get('errorType')} error={diag_result.get('error')}"
            )
        return jsonify({
            "ok": False,
            "error": "smtp_send_failed",
            "detail": str(exc),
            "diagnostics": diag_result,
            "fallbackError": fallback_error,
            "resendConfigured": bool(resend_api_key),
            "resendKeySource": resend_key_source,
            "brevoConfigured": bool(brevo_api_key),
            "resendEnv": resend_env,
        })


@app.post("/api/settings/smtp-diagnose")
@require_auth
@require_roles("superadmin")
def smtp_diagnose():
    db = get_db()
    payload = request.get_json(silent=True) or {}
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if not settings:
        return jsonify({"ok": False, "error": "no_settings"}), 400
    smtp_settings = _resolve_smtp_settings(settings, payload)
    missing_fields = []
    if not smtp_settings["smtp_host"]:
        missing_fields.append("smtpHost")
    if not smtp_settings["smtp_sender_email"]:
        missing_fields.append("smtpSenderEmail")
    if missing_fields:
        return jsonify({"ok": False, "error": "smtp_not_configured", "missingFields": missing_fields}), 400
    result = _run_smtp_diagnostics(smtp_settings)
    resend_api_key, resend_key_source = _get_resend_api_key_and_source()
    brevo_api_key = _get_brevo_api_key()
    result["resendConfigured"] = bool(resend_api_key)
    result["resendKeySource"] = resend_key_source
    result["brevoConfigured"] = bool(brevo_api_key)
    result["resendEnv"] = _collect_resend_env_presence()
    status_code = 200
    if not result.get("ok"):
        app.logger.warning(
            f"[SMTP-DIAG] stage={result.get('stage')} type={result.get('errorType')} error={result.get('error')}"
        )
    return jsonify(result), status_code


@app.post("/api/settings/resend-test")
@require_auth
@require_roles("superadmin")
def resend_test():
    """Test API fallback delivery directly (without SMTP)."""
    db = get_db()
    payload = request.get_json(silent=True) or {}
    requested_provider = str(payload.get("provider") or "").strip().lower()
    if requested_provider not in ("", "resend", "brevo"):
        requested_provider = ""
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()

    recipient = (str(payload.get("recipient") or "").strip() or (g.current_user["email"] or "").strip())
    if not recipient and settings:
        recipient = str(settings["smtp_sender_email"] or "").strip()
    if not recipient and settings:
        recipient = str(settings["brevo_from_email"] or "").strip()
    if not recipient and settings:
        recipient = str(settings["resend_from_email"] or "").strip()
    if not recipient:
        return jsonify({"ok": False, "error": "missing_recipient"})

    sender_email = ""
    sender_name = "BauPass"
    if settings:
        sender_email = str(settings["smtp_sender_email"] or "").strip()
        sender_name = str(settings["smtp_sender_name"] or "BauPass").strip() or "BauPass"

    env_presence = _collect_resend_env_presence()
    resend_api_key, resend_key_source = _get_resend_api_key_and_source()
    brevo_api_key = _get_brevo_api_key()
    if requested_provider == "resend" and not resend_api_key:
        return jsonify({
            "ok": False,
            "error": "resend_not_configured",
            "provider": "resend",
            "resendConfigured": False,
            "resendKeySource": "",
            "resendEnv": env_presence,
        })
    if requested_provider == "brevo" and not brevo_api_key:
        return jsonify({
            "ok": False,
            "error": "brevo_not_configured",
            "provider": "brevo",
            "brevoConfigured": False,
            "resendEnv": env_presence,
        })
    if not requested_provider and not resend_api_key and not brevo_api_key:
        return jsonify({
            "ok": False,
            "error": "resend_not_configured",
            "resendConfigured": False,
            "resendKeySource": "",
            "resendEnv": env_presence,
            "resendDbKeySet": bool(_resend_key_cache.get("key")),
            "resendCacheDebug": f"cache_key_len={len(_resend_key_cache.get('key',''))}",
        })

    subject = "BauPass: API Direkt-Test"
    text_body = (
        "Dieser Test wurde direkt ueber die HTTPS API-Fallback-Zustellung versendet.\n"
        "Wenn diese Mail ankommt, funktioniert die API-Zustellung korrekt im Container."
    )
    html_body = (
        "<p>Dieser Test wurde direkt ueber die <strong>HTTPS API-Fallback-Zustellung</strong> versendet.</p>"
        "<p>Wenn diese Mail ankommt, funktioniert die API-Zustellung korrekt im Container.</p>"
    )

    used_provider = requested_provider or "auto"
    if requested_provider == "resend":
        fallback_ok, fallback_error = _send_via_resend(
            subject=subject,
            sender_email=sender_email,
            sender_name=sender_name,
            recipient=recipient,
            text_body=text_body,
            html_body=html_body,
        )
    elif requested_provider == "brevo":
        fallback_ok, fallback_error = _send_via_brevo(
            subject=subject,
            sender_email=sender_email,
            sender_name=sender_name,
            recipient=recipient,
            text_body=text_body,
            html_body=html_body,
        )
    else:
        fallback_ok, fallback_error, used_provider = _send_via_any_api(
            subject=subject,
            sender_email=sender_email,
            sender_name=sender_name,
            recipient=recipient,
            text_body=text_body,
            html_body=html_body,
        )

    if fallback_ok:
        return jsonify({
            "ok": True,
            "recipient": recipient,
            "delivery": used_provider,
            "provider": used_provider,
            "resendConfigured": bool(resend_api_key),
            "resendKeySource": resend_key_source,
            "brevoConfigured": bool(brevo_api_key),
            "resendEnv": env_presence,
        })

    # Enrich error with a hint about provider-specific restrictions
    detail_hint = fallback_error
    if "1010" in str(fallback_error):
        detail_hint += " — Tipp: Cloudflare blockiert den Request (Bot-Erkennung). User-Agent wurde gesetzt, bitte erneut versuchen."
    elif "403" in str(fallback_error) or "validation_error" in str(fallback_error) or "domain" in str(fallback_error).lower():
        detail_hint += " — Tipp: API-Provider-Policies prüfen (Absender/Domain verifizieren). Bei Resend ist Gmail als Absender nicht erlaubt."
    return jsonify({
        "ok": False,
        "error": "resend_send_failed",
        "detail": detail_hint,
        "provider": used_provider,
        "resendConfigured": True,
        "resendKeySource": resend_key_source,
        "resendEnv": env_presence,
    })


@app.put("/api/settings")
@require_auth
@require_roles("superadmin")
def update_settings():
    payload = request.get_json(silent=True) or {}
    db = get_db()

    current_row = db.execute(
        "SELECT smtp_password, imap_password FROM settings WHERE id = 1"
    ).fetchone()
    current_smtp_password = str(current_row["smtp_password"] or "") if current_row else ""
    current_imap_password = str(current_row["imap_password"] or "") if current_row else ""
    payload_smtp_password = str(payload.get("smtpPassword") or "")
    try:
        invoice_operator_email = sanitize_optional_email(
            payload.get("invoiceOperatorEmail", ""),
            field_error="invalid_invoice_operator_email",
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    db.execute(
        """
        UPDATE settings
        SET platform_name = ?, operator_name = ?, turnstile_endpoint = ?, rental_model = ?,
            invoice_logo_data = ?, invoice_primary_color = ?, invoice_accent_color = ?,
            invoice_iban = ?, invoice_bic = ?, invoice_bank_name = ?,
            invoice_tax_id = ?, invoice_vat_id = ?,
            invoice_operator_street = ?, invoice_operator_zip_city = ?,
            invoice_operator_phone = ?, invoice_operator_website = ?, invoice_operator_email = ?,
            invoice_email_subject = ?, invoice_email_intro = ?,
            smtp_host = ?, smtp_port = ?, smtp_username = ?, smtp_password = ?,
            smtp_sender_email = ?, smtp_sender_name = ?, smtp_use_tls = ?,
            admin_ip_whitelist = ?, enforce_tenant_domain = ?, worker_app_enabled = ?
        WHERE id = 1
        """,
        (
            payload.get("platformName", "BauPass Control"),
            payload.get("operatorName", "Deine Betriebsfirma"),
            payload.get("turnstileEndpoint", ""),
            payload.get("rentalModel", "tageskarte"),
            payload.get("invoiceLogoData", ""),
            payload.get("invoicePrimaryColor", "#0f4c5c"),
            payload.get("invoiceAccentColor", "#e36414"),
            payload.get("invoiceIban", ""),
            payload.get("invoiceBic", ""),
            payload.get("invoiceBankName", ""),
            payload.get("invoiceTaxId", ""),
            payload.get("invoiceVatId", ""),
            payload.get("invoiceOperatorStreet", ""),
            payload.get("invoiceOperatorZipCity", ""),
            payload.get("invoiceOperatorPhone", ""),
            payload.get("invoiceOperatorWebsite", ""),
            invoice_operator_email,
            payload.get("invoiceEmailSubject", ""),
            payload.get("invoiceEmailIntro", ""),
            payload.get("smtpHost", ""),
            int(payload.get("smtpPort", 587) or 587),
            payload.get("smtpUsername", ""),
            payload_smtp_password if payload_smtp_password.strip() else current_smtp_password,
            payload.get("smtpSenderEmail", ""),
            payload.get("smtpSenderName", "BauPass Control"),
            1 if payload.get("smtpUseTls", True) else 0,
            payload.get("adminIpWhitelist", ""),
            1 if payload.get("enforceTenantDomain", False) else 0,
            1 if payload.get("workerAppEnabled", True) else 0,
        ),
    )
    # Impressum / Datenschutz
    impressum_text = str(payload.get("impressumText") or "")[:20000]
    datenschutz_text = str(payload.get("datenschutzText") or "")[:20000]
    db.execute("UPDATE settings SET impressum_text = ?, datenschutz_text = ? WHERE id = 1", (impressum_text, datenschutz_text))
    # Resend-Konfiguration (API-Key direkt in DB speichern, umgeht Railway-Env-Probleme)
    # Leeres Feld = bestehenden Key behalten (wie SMTP-Passwort-Logik)
    resend_api_key_payload = str(payload.get("resendApiKey") or "").strip()
    resend_from_email_payload = str(payload.get("resendFromEmail") or "").strip()
    if resend_api_key_payload:
        db.execute(
            "UPDATE settings SET resend_api_key = ?, resend_from_email = ? WHERE id = 1",
            (resend_api_key_payload, resend_from_email_payload),
        )
        _resend_key_cache["key"] = resend_api_key_payload
        _resend_key_cache["from_email"] = resend_from_email_payload
    elif resend_from_email_payload:
        db.execute("UPDATE settings SET resend_from_email = ? WHERE id = 1", (resend_from_email_payload,))
        _resend_key_cache["from_email"] = resend_from_email_payload
    # Brevo-Konfiguration (kein Cloudflare-Block, erlaubt Gmail als Absender)
    brevo_api_key_payload = str(payload.get("brevoApiKey") or "").strip()
    brevo_from_email_payload = str(payload.get("brevoFromEmail") or "").strip()
    if brevo_api_key_payload:
        db.execute(
            "UPDATE settings SET brevo_api_key = ?, brevo_from_email = ? WHERE id = 1",
            (brevo_api_key_payload, brevo_from_email_payload),
        )
        _resend_key_cache["brevo_key"] = brevo_api_key_payload
        _resend_key_cache["brevo_from_email"] = brevo_from_email_payload
    elif brevo_from_email_payload:
        db.execute("UPDATE settings SET brevo_from_email = ? WHERE id = 1", (brevo_from_email_payload,))
        _resend_key_cache["brevo_from_email"] = brevo_from_email_payload
    # IMAP-Felder separat aktualisieren (immer optional)
    payload_imap_password = str(payload.get("imapPassword") or "")
    imap_fields = {
        "imap_host": clean_text_input(payload.get("imapHost", ""), max_len=255),
        "imap_port": int(payload.get("imapPort") or 993),
        "imap_username": clean_text_input(payload.get("imapUsername", ""), max_len=255),
        "imap_password": payload_imap_password if payload_imap_password.strip() else current_imap_password,
        "imap_folder": clean_text_input(payload.get("imapFolder", "INBOX"), max_len=100) or "INBOX",
        "imap_use_ssl": 1 if payload.get("imapUseSsl", True) else 0,
    }
    for col, val in imap_fields.items():
        db.execute(f"UPDATE settings SET {col} = ? WHERE id = 1", (val,))
    db.commit()
    log_audit("settings.updated", "Systemeinstellungen wurden aktualisiert", actor=g.current_user)
    return get_settings()


@app.get("/api/companies")
@require_auth
def list_companies():
    include_deleted = request.args.get("includeDeleted", "0") == "1"
    clause, params = visible_company_clause(g.current_user)
    if include_deleted:
        where = clause
    else:
        where = f"{clause}{' AND' if clause else ' WHERE'} deleted_at IS NULL"

    rows = get_db().execute(f"SELECT * FROM companies{where} ORDER BY name", params).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/companies/document-emails/export")
@require_auth
@require_roles("superadmin")
def export_company_document_emails_csv():
    db = get_db()
    rows = db.execute(
        """
        SELECT
            c.id,
            c.name,
            c.contact,
            c.billing_email,
            c.document_email,
            c.status,
            c.deleted_at,
            MAX(e.received_at) AS last_inbox_activity_at,
            SUM(CASE WHEN e.dismissed = 0 THEN 1 ELSE 0 END) AS open_inbox_count,
            SUM(CASE WHEN e.dismissed = 0 AND e.matched_company_id IS NULL AND lower(e.to_addr) = lower(c.document_email) THEN 1 ELSE 0 END) AS unresolved_inbox_count
        FROM companies c
        LEFT JOIN email_inbox e ON (e.matched_company_id = c.id OR lower(e.to_addr) = lower(c.document_email))
        GROUP BY c.id, c.name, c.contact, c.billing_email, c.document_email, c.status, c.deleted_at
        ORDER BY name
        """
    ).fetchall()

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return jsonify({"error": "pdf_dependency_missing", "message": "Bitte reportlab installieren."}), 503

    buffer = io.BytesIO()
    pw, ph = landscape(A4)
    pdf = rl_canvas.Canvas(buffer, pagesize=landscape(A4))
    col_x = [36, 186, 326, 402, 512, 640, 688, 736]
    headers = ["Firma", "Dokument-Email", "Status", "Rechnungs-Email", "Letzter Eingang", "Offen", "Ungelöst", "Gelöscht"]

    def draw_doc_email_hdr(y):
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(36, y, "BauPass - Firmen Dokument-E-Mails")
        y -= 14
        pdf.setFont("Helvetica", 8)
        pdf.drawString(36, y, f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        y -= 16
        pdf.setFont("Helvetica-Bold", 7)
        for i, h in enumerate(headers):
            pdf.drawString(col_x[i], y, h)
        y -= 8
        pdf.line(36, y, pw - 36, y)
        y -= 10
        return y

    y = ph - 36
    y = draw_doc_email_hdr(y)
    pdf.setFont("Helvetica", 7)
    for row in rows:
        if y < 48:
            pdf.showPage()
            y = ph - 36
            y = draw_doc_email_hdr(y)
            pdf.setFont("Helvetica", 7)
        pdf.drawString(col_x[0], y, str(row["name"] or "")[:24])
        pdf.drawString(col_x[1], y, str(row["document_email"] or "")[:24])
        pdf.drawString(col_x[2], y, str(row["status"] or "")[:12])
        pdf.drawString(col_x[3], y, str(row["billing_email"] or "")[:24])
        pdf.drawString(col_x[4], y, str(row["last_inbox_activity_at"] or "")[:18])
        pdf.drawString(col_x[5], y, str(int(row["open_inbox_count"] or 0)))
        pdf.drawString(col_x[6], y, str(int(row["unresolved_inbox_count"] or 0)))
        pdf.drawString(col_x[7], y, "Ja" if row["deleted_at"] else "Nein")
        y -= 11
    if not rows:
        pdf.drawString(36, y, "Keine Firmen gefunden.")
    pdf.save()
    buffer.seek(0)
    filename = f"firmen-dokument-emails-{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/subcompanies")
@require_auth
def list_subcompanies():
    include_deleted = request.args.get("includeDeleted", "0") == "1"
    requested_company_id = (request.args.get("companyId") or "").strip()
    user = g.current_user

    conditions = []
    params = []

    if user["role"] == "superadmin":
        if requested_company_id:
            conditions.append("company_id = ?")
            params.append(requested_company_id)
    else:
        conditions.append("company_id = ?")
        params.append(user.get("company_id"))

    if not include_deleted:
        conditions.append("deleted_at IS NULL")

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = get_db().execute(f"SELECT * FROM subcompanies{where_clause} ORDER BY name", params).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.post("/api/subcompanies")
@require_auth
@require_roles("superadmin", "company-admin")
def create_subcompany():
    payload = request.get_json(silent=True) or {}
    user = g.current_user
    try:
        company_id = clean_id_input(payload.get("companyId") or user.get("company_id") or "")
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    name = clean_text_input(payload.get("name") or "", max_len=120)
    contact = clean_text_input(payload.get("contact") or "", max_len=180)

    if not company_id:
        return jsonify({"error": "missing_company"}), 400
    if user["role"] != "superadmin" and company_id != user.get("company_id"):
        return jsonify({"error": "forbidden_company"}), 403
    if not name:
        return jsonify({"error": "missing_name"}), 400

    db = get_db()
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company or company["deleted_at"]:
        return jsonify({"error": "company_not_available"}), 400

    existing = db.execute(
        "SELECT * FROM subcompanies WHERE company_id = ? AND lower(name) = lower(?) AND deleted_at IS NULL",
        (company_id, name),
    ).fetchone()
    if existing:
        return jsonify({"error": "subcompany_exists"}), 400

    subcompany_id = f"sub-{secrets.token_hex(6)}"
    db.execute(
        "INSERT INTO subcompanies (id, company_id, name, contact, status, deleted_at) VALUES (?, ?, ?, ?, ?, NULL)",
        (subcompany_id, company_id, name, contact, "aktiv"),
    )
    db.commit()
    log_audit(
        "subcompany.created",
        f"Subunternehmen {name} wurde angelegt",
        target_type="subcompany",
        target_id=subcompany_id,
        company_id=company_id,
        actor=user,
    )

    row = db.execute("SELECT * FROM subcompanies WHERE id = ?", (subcompany_id,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.post("/api/companies")
@require_auth
@require_roles("superadmin")
def create_company():
    payload = request.get_json(silent=True) or {}
    company_id = f"cmp-{secrets.token_hex(6)}"
    turnstile_endpoint = clean_text_input(payload.get("turnstileEndpoint", ""), max_len=320)
    company_name = clean_text_input(payload.get("name", "Neue Firma"), max_len=120) or "Neue Firma"
    company_contact = clean_text_input(payload.get("contact", ""), max_len=180)
    billing_email = clean_text_input(payload.get("billingEmail", ""), max_len=160)
    document_email = clean_text_input(payload.get("documentEmail", ""), max_len=160)
    if not document_email:
        document_email = suggest_company_document_email(company_name)
    access_host = clean_text_input((payload.get("accessHost") or payload.get("access_host") or "").strip().lower(), max_len=180)
    branding_preset = normalize_branding_preset(payload.get("brandingPreset") or payload.get("branding_preset"))
    company_status = clean_text_input(payload.get("status", "aktiv"), max_len=32) or "aktiv"
    admin_password = (payload.get("adminPassword") or "").strip() or "1234"
    turnstile_password = (payload.get("turnstilePassword") or "").strip() or admin_password
    try:
        turnstile_count = int(payload.get("turnstileCount", 1) or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_turnstile_count", "message": "Anzahl Drehkreuze muss eine Zahl sein."}), 400

    if turnstile_count < 1 or turnstile_count > 20:
        return jsonify({"error": "invalid_turnstile_count", "message": "Anzahl Drehkreuze muss zwischen 1 und 20 liegen."}), 400

    if len(admin_password) < 4:
        return jsonify({"error": "password_too_short", "message": "Passwort muss mindestens 4 Zeichen haben."}), 400
    if len(turnstile_password) < 4:
        return jsonify({"error": "turnstile_password_too_short", "message": "Drehkreuz-Passwort muss mindestens 4 Zeichen haben."}), 400

    db = get_db()
    if turnstile_endpoint:
        db.execute("UPDATE settings SET turnstile_endpoint = ? WHERE id = 1", (turnstile_endpoint,))
    db.execute(
        "INSERT INTO companies (id, name, contact, billing_email, document_email, access_host, branding_preset, plan, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            company_id,
            company_name,
            company_contact,
            billing_email,
            document_email,
            access_host,
            branding_preset,
            normalize_company_plan(payload.get("plan", "tageskarte")),
            company_status,
        ),
    )

    username_base = "".join(c for c in company_name.lower() if c.isalnum())[:12] or "firma"
    username = username_base
    suffix = 1
    while db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        username = f"{username_base}{suffix}"
        suffix += 1

    db.execute(
        "INSERT INTO users (id, username, password_hash, name, role, company_id) VALUES (?, ?, ?, ?, ?, ?)",
        (
            f"usr-{secrets.token_hex(6)}",
            username,
            generate_password_hash(admin_password),
            f"{company_name} Admin",
            "company-admin",
            company_id,
        ),
    )

    turnstile_credentials = []
    for index in range(turnstile_count):
        if turnstile_count == 1:
            turnstile_username_base = f"{username_base}gate"
            turnstile_display_name = f"{company_name} Drehkreuz"
        else:
            turnstile_username_base = f"{username_base}gate{index + 1}"
            turnstile_display_name = f"{company_name} Drehkreuz {index + 1}"

        turnstile_username = turnstile_username_base
        turnstile_suffix = 1
        while db.execute("SELECT 1 FROM users WHERE username = ?", (turnstile_username,)).fetchone():
            turnstile_username = f"{turnstile_username_base}{turnstile_suffix}"
            turnstile_suffix += 1

        turnstile_api_key = create_turnstile_api_key()
        db.execute(
            "INSERT INTO users (id, username, password_hash, name, role, company_id, api_key_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                f"usr-{secrets.token_hex(6)}",
                turnstile_username,
                generate_password_hash(turnstile_password),
                turnstile_display_name,
                "turnstile",
                company_id,
                hash_turnstile_api_key(turnstile_api_key),
            ),
        )
        turnstile_credentials.append(
            {
                "username": turnstile_username,
                "password": turnstile_password,
                "apiKey": turnstile_api_key,
            }
        )

    db.commit()
    log_audit("company.created", f"Firma {company_name} wurde angelegt", target_type="company", target_id=company_id, company_id=company_id, actor=g.current_user)

    row = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    return (
        jsonify(
            {
                "company": row_to_dict(row),
                "adminCredentials": {
                    "username": username,
                    "password": admin_password,
                },
                "turnstileCredentials": {
                    "username": turnstile_credentials[0]["username"],
                    "password": turnstile_credentials[0]["password"],
                    "apiKey": turnstile_credentials[0]["apiKey"],
                },
                "turnstileCredentialsList": turnstile_credentials,
            }
        ),
        201,
    )


@app.post("/api/demo-seed")
@require_auth
@require_roles("superadmin", "company-admin")
def demo_seed():
    payload = request.get_json(silent=True) or {}
    company_id = payload.get("companyId") or g.current_user.get("company_id")
    mode = (payload.get("mode") or "replace").strip().lower()
    include_invoices = int(payload.get("includeInvoices") or 0) == 1
    include_access_logs = int(payload.get("includeAccessLogs") or 1) == 1
    include_overdue_example = int(payload.get("includeOverdueExample") or 1) == 1

    if mode not in {"replace", "append"}:
        return jsonify({"error": "invalid_mode"}), 400

    db = get_db()
    if g.current_user["role"] == "superadmin" and not company_id:
        first_company = db.execute("SELECT id FROM companies WHERE deleted_at IS NULL ORDER BY name LIMIT 1").fetchone()
        company_id = (first_company["id"] if first_company else "") or ""
        if not company_id:
            company_id = "cmp-default"
            db.execute(
                "INSERT OR IGNORE INTO companies (id, name, contact, billing_email, access_host, plan, status, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (company_id, "Muster Bau GmbH", "Sabine Keller", "", "", "professional", "test"),
            )

    if g.current_user["role"] != "superadmin" and company_id != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_company"}), 403

    if mode == "replace":
        db.execute("DELETE FROM access_logs WHERE worker_id IN (SELECT id FROM workers WHERE company_id = ?)", (company_id,))
        db.execute("DELETE FROM workers WHERE company_id = ?", (company_id,))
        db.execute("DELETE FROM subcompanies WHERE company_id = ?", (company_id,))
        if include_invoices:
            db.execute("DELETE FROM invoices WHERE company_id = ?", (company_id,))

    subcompanies = [
        (f"sub-{secrets.token_hex(6)}", company_id, "Demir Montage", "Ali Demir", "aktiv", None),
        (f"sub-{secrets.token_hex(6)}", company_id, "Lehmann Kranservice", "Mara Lehmann", "aktiv", None),
    ]
    db.executemany(
        "INSERT INTO subcompanies (id, company_id, name, contact, status, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        subcompanies,
    )

    workers = [
        {
            "id": f"wrk-{secrets.token_hex(6)}",
            "company_id": company_id,
            "subcompany_id": subcompanies[0][0],
            "first_name": "Ali",
            "last_name": "Demir",
            "insurance_number": "12 345678 A 111",
            "role": "Kranfuehrer",
            "site": "Neubau Mitte",
            "valid_until": "2026-12-31",
            "status": "aktiv",
            "photo_data": "",
            "badge_id": "BP-AD-DEM01",
        },
        {
            "id": f"wrk-{secrets.token_hex(6)}",
            "company_id": company_id,
            "subcompany_id": subcompanies[1][0],
            "first_name": "Mara",
            "last_name": "Lehmann",
            "insurance_number": "12 345678 A 222",
            "role": "Polierin",
            "site": "Neubau Mitte",
            "valid_until": "2026-12-31",
            "status": "aktiv",
            "photo_data": "",
            "badge_id": "BP-ML-DEM02",
        },
    ]

    for worker in workers:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number, role, site, valid_until, status, photo_data, badge_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                worker["id"],
                worker["company_id"],
                worker["subcompany_id"],
                worker["first_name"],
                worker["last_name"],
                worker["insurance_number"],
                worker["role"],
                worker["site"],
                worker["valid_until"],
                worker["status"],
                worker["photo_data"],
                worker["badge_id"],
            ),
        )

    access_logs_created = 0
    if include_access_logs:
        db.execute(
            "INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"log-{secrets.token_hex(6)}",
                workers[0]["id"],
                "check-in",
                "Drehkreuz Nord",
                "Fruehschicht",
                now_iso(),
            ),
        )
        db.execute(
            "INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"log-{secrets.token_hex(6)}",
                workers[1]["id"],
                "check-in",
                "Drehkreuz Sued",
                "Spaetschicht",
                now_iso(),
            ),
        )
        access_logs_created = 2

    invoices_created = 0
    if include_invoices:
        company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        created_by = g.current_user["id"]
        base_date = utc_now().date()
        invoice_examples = [
            {
                "number": f"RE-{base_date.year}-{secrets.token_hex(2).upper()}",
                "offset": -28,
                "due_offset": -14,
                "status": "overdue" if include_overdue_example else "sent",
                "desc": "Monatliche Baustellenplattform",
                "total": 119.0,
                "period": "Demo-Monat 1",
                "reminder_stage": 3 if include_overdue_example else 1,
            },
            {
                "number": f"RE-{base_date.year}-{secrets.token_hex(2).upper()}",
                "offset": -7,
                "due_offset": 7,
                "status": "sent",
                "desc": "Mitarbeiterverwaltung + Zutritt",
                "total": 89.0,
                "period": "Demo-Monat 2",
                "reminder_stage": 1,
            },
        ]
        for item in invoice_examples:
            invoice_date = (base_date + timedelta(days=item["offset"])).isoformat()
            due_date = (base_date + timedelta(days=item["due_offset"])).isoformat()
            net_amount = round(item["total"] / 1.19, 2)
            vat_amount = round(item["total"] - net_amount, 2)
            db.execute(
                """
                INSERT INTO invoices (
                    id, invoice_number, company_id, recipient_email, invoice_date, invoice_period, description,
                    net_amount, vat_rate, vat_amount, total_amount, status, error_message, sent_at,
                    rendered_html, created_by_user_id, created_at, due_date, paid_at,
                    auto_suspend_triggered_at, reminder_stage, last_reminder_sent_at, last_reminder_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"inv-{secrets.token_hex(6)}",
                    item["number"],
                    company_id,
                    (company["billing_email"] or "buchhaltung@demo-firma.de") if company else "buchhaltung@demo-firma.de",
                    invoice_date,
                    item["period"],
                    item["desc"],
                    net_amount,
                    19.0,
                    vat_amount,
                    item["total"],
                    item["status"],
                    "",
                    now_iso(),
                    f"<html><body><h1>{item['number']}</h1></body></html>",
                    created_by,
                    now_iso(),
                    due_date,
                    None,
                    None,
                    item["reminder_stage"],
                    None,
                    "",
                ),
            )
            invoices_created += 1

    db.commit()
    log_audit(
        "demo.seed",
        f"Demo-Daten geladen (mode={mode}, workers={len(workers)}, logs={access_logs_created}, invoices={invoices_created})",
        target_type="company",
        target_id=company_id,
        company_id=company_id,
        actor=g.current_user,
    )

    return jsonify(
        {
            "ok": True,
            "mode": mode,
            "workersCreated": len(workers),
            "accessLogsCreated": access_logs_created,
            "invoicesCreated": invoices_created,
            "companyId": company_id,
        }
    )


@app.get("/api/workers")
@require_auth
def list_workers():
    db = get_db()
    include_deleted = request.args.get("includeDeleted", "0") == "1"
    lock_workers_with_expired_documents(db)
    clause, params = visible_worker_clause(g.current_user)
    where = clause if include_deleted else f"{clause}{' AND' if clause else ' WHERE'} deleted_at IS NULL"
    rows = db.execute(f"SELECT * FROM workers{where} ORDER BY last_name, first_name", params).fetchall()

    serialized = []
    for row in rows:
        item = serialize_worker_record(row)
        item.update(get_worker_lock_metadata(db, row))
        serialized.append(item)
    return jsonify(serialized)


@app.post("/api/workers/import-csv")
@require_auth
@require_roles("superadmin", "company-admin")
def import_workers_csv():
    """Bulk-import workers from a CSV file.
    Expected columns (case-insensitive):
    vorname, nachname, firma, versicherungsnr, typ, rolle, baustelle, gueltig_bis
    Returns a summary: created, skipped, errors.
    """
    if "file" not in request.files:
        return jsonify({"error": "no_file"}), 400
    uploaded_file = request.files["file"]
    if not uploaded_file.filename or not uploaded_file.filename.lower().endswith(".csv"):
        return jsonify({"error": "invalid_file_type", "message": "Nur CSV-Dateien erlaubt."}), 400

    db = get_db()
    # Read CSV safely
    raw_bytes = uploaded_file.read(2 * 1024 * 1024)  # max 2 MB
    try:
        raw_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw_text = raw_bytes.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(raw_text), delimiter=None)
    # Try to detect delimiter (csv.Sniffer)
    try:
        sample = raw_text[:2048]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
        reader = csv.DictReader(io.StringIO(raw_text), dialect=dialect)
    except csv.Error:
        reader = csv.DictReader(io.StringIO(raw_text))

    # Normalize header names
    def _col(row, *candidates):
        for key in row:
            norm = key.strip().lower().replace(" ", "_").replace("-", "_").replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")
            if norm in candidates:
                return str(row[key] or "").strip()
        return ""

    created = []
    skipped = []
    errors = []

    # Pre-load companies for name->id lookup
    all_companies = {str(r["name"]).strip().lower(): str(r["id"]) for r in db.execute("SELECT id, name FROM companies WHERE deleted_at IS NULL").fetchall()}

    for row_num, row in enumerate(reader, start=2):
        try:
            first_name = _col(row, "vorname", "first_name", "firstname")
            last_name = _col(row, "nachname", "last_name", "lastname", "name")
            if not first_name or not last_name:
                skipped.append({"row": row_num, "reason": "Vor- oder Nachname fehlt"})
                continue

            company_name_raw = _col(row, "firma", "company", "unternehmen", "company_name")
            company_id = all_companies.get(company_name_raw.lower(), "")
            if not company_id:
                # Try partial match
                for cn, cid in all_companies.items():
                    if company_name_raw.lower() in cn or cn in company_name_raw.lower():
                        company_id = cid
                        break
            if not company_id:
                if g.current_user["role"] == "company-admin":
                    company_id = g.current_user.get("company_id", "")
                else:
                    skipped.append({"row": row_num, "reason": f"Firma '{company_name_raw}' nicht gefunden"})
                    continue

            if g.current_user["role"] == "company-admin" and company_id != g.current_user.get("company_id"):
                skipped.append({"row": row_num, "reason": "Firma nicht erlaubt"})
                continue

            insurance_number = _col(row, "versicherungsnr", "insurance_number", "sozialversicherungsnr", "svnr")
            worker_type_raw = _col(row, "typ", "type", "worker_type").lower()
            worker_type = "worker" if worker_type_raw not in ("visitor", "besucher") else "visitor"
            role_value = _col(row, "rolle", "role", "position") or "Mitarbeiter"
            site_value = _col(row, "baustelle", "site", "standort") or ""
            valid_until_raw = _col(row, "gueltig_bis", "gueltigbis", "valid_until", "validuntil", "ablaufdatum")
            # Normalize date
            valid_until_value = None
            if valid_until_raw:
                # Try DD.MM.YYYY and YYYY-MM-DD
                for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        from datetime import datetime as _dt
                        parsed = _dt.strptime(valid_until_raw, fmt)
                        valid_until_value = parsed.strftime("%Y-%m-%dT23:59:00")
                        break
                    except ValueError:
                        continue

            worker_id = f"wrk-{secrets.token_hex(6)}"
            # Generate unique badge_id
            badge_id_value = str(row_num).zfill(6)
            existing_badge = db.execute("SELECT id FROM workers WHERE badge_id = ?", (badge_id_value,)).fetchone()
            if existing_badge:
                badge_id_value = secrets.token_hex(4)

            db.execute(
                """
                INSERT INTO workers (
                    id, company_id, subcompany_id, first_name, last_name, insurance_number,
                    worker_type, role, site, valid_until, visitor_company, visit_purpose,
                    host_name, visit_end_at, status, photo_data, badge_id, badge_pin_hash,
                    physical_card_id, deleted_at
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, '', '', '', NULL, 'active', '', ?, '', '', NULL)
                """,
                (worker_id, company_id, first_name, last_name, insurance_number,
                 worker_type, role_value, site_value, valid_until_value, badge_id_value),
            )
            created.append({"row": row_num, "name": f"{first_name} {last_name}", "id": worker_id})
        except Exception as exc:
            errors.append({"row": row_num, "reason": str(exc)[:200]})

    if created:
        db.commit()
        log_audit("workers.bulk_imported", f"{len(created)} Mitarbeiter per CSV importiert", actor=g.current_user)

    return jsonify({
        "created": len(created),
        "skipped": len(skipped),
        "errors": len(errors),
        "details": {"created": created[:50], "skipped": skipped[:50], "errors": errors[:50]},
    })


@app.get("/api/workers/export.csv")
@require_auth
@require_roles("superadmin", "company-admin")
def export_workers_csv():
    include_deleted = request.args.get("includeDeleted", "0") == "1"
    where_clause, params = visible_worker_clause(g.current_user, prefix="workers.")
    if not include_deleted:
        where_clause = f"{where_clause}{' AND' if where_clause else ' WHERE'} workers.deleted_at IS NULL"

    rows = get_db().execute(
        f"""
        SELECT workers.*, companies.name AS company_name, subcompanies.name AS subcompany_name
        FROM workers
        JOIN companies ON companies.id = workers.company_id
        LEFT JOIN subcompanies ON subcompanies.id = workers.subcompany_id
        {where_clause}
        ORDER BY workers.last_name, workers.first_name
        """,
        params,
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "company_id",
            "company_name",
            "subcompany_id",
            "subcompany_name",
            "first_name",
            "last_name",
            "worker_type",
            "insurance_number",
            "role",
            "site",
            "valid_until",
            "visitor_company",
            "visit_purpose",
            "host_name",
            "visit_end_at",
            "status",
            "badge_id",
            "physical_card_id",
            "deleted_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["company_id"],
                row["company_name"],
                row["subcompany_id"],
                row["subcompany_name"],
                row["first_name"],
                row["last_name"],
                row["worker_type"],
                row["insurance_number"],
                row["role"],
                row["site"],
                row["valid_until"],
                row["visitor_company"],
                row["visit_purpose"],
                row["host_name"],
                row["visit_end_at"],
                row["status"],
                row["badge_id"],
                row["physical_card_id"],
                row["deleted_at"],
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="mitarbeiterliste.csv"'},
    )


@app.get("/api/workers/export.pdf")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def export_workers_pdf():
    include_deleted = request.args.get("includeDeleted", "0") == "1"
    include_photos = request.args.get("includePhotos", "0") == "1"
    period = (request.args.get("period") or "all").strip().lower()
    date_param = (request.args.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()

    # Validate date_param to prevent injection
    try:
        period_date = datetime.strptime(date_param, "%Y-%m-%d").date()
    except ValueError:
        period_date = datetime.now().date()

    db = get_db()
    where_clause, params = visible_worker_clause(g.current_user, prefix="workers.")
    if not include_deleted:
        where_clause = f"{where_clause}{' AND' if where_clause else ' WHERE'} workers.deleted_at IS NULL"

    period_label = ""
    if period == "day":
        day_str = period_date.isoformat()
        where_clause = f"{where_clause}{' AND' if where_clause else ' WHERE'} workers.id IN (SELECT DISTINCT worker_id FROM access_logs WHERE date(timestamp) = ?)"
        params = list(params) + [day_str]
        period_label = f" | Tag: {day_str}"
    elif period == "week":
        week_start = (period_date - timedelta(days=period_date.weekday())).isoformat()
        week_end = (period_date - timedelta(days=period_date.weekday()) + timedelta(days=6)).isoformat()
        where_clause = f"{where_clause}{' AND' if where_clause else ' WHERE'} workers.id IN (SELECT DISTINCT worker_id FROM access_logs WHERE date(timestamp) >= ? AND date(timestamp) <= ?)"
        params = list(params) + [week_start, week_end]
        period_label = f" | Woche: {week_start} – {week_end}"

    rows = db.execute(
        f"""
        SELECT workers.id, workers.first_name, workers.last_name, workers.status,
               workers.photo_data, workers.badge_id, workers.site,
               companies.name AS company_name, subcompanies.name AS subcompany_name
        FROM workers
        JOIN companies ON companies.id = workers.company_id
        LEFT JOIN subcompanies ON subcompanies.id = workers.subcompany_id
        {where_clause}
        ORDER BY workers.last_name, workers.first_name
        """,
        params,
    ).fetchall()

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.utils import ImageReader
    except Exception:
        return jsonify({"error": "pdf_dependency_missing", "message": "Bitte reportlab installieren."}), 503

    buffer = io.BytesIO()
    page_width, page_height = A4
    pdf = rl_canvas.Canvas(buffer, pagesize=A4)

    row_height = 44 if include_photos else 13
    photo_size = 36

    def draw_worker_page_header(y):
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(36, y, "BauPass - Mitarbeiterliste")
        y -= 16
        pdf.setFont("Helvetica", 9)
        pdf.drawString(36, y, f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}{period_label} | {len(rows)} Mitarbeiter")
        y -= 20
        pdf.setFont("Helvetica-Bold", 9)
        x_name = 36 + (photo_size + 6 if include_photos else 0)
        pdf.drawString(x_name, y, "Name")
        pdf.drawString(x_name + 170, y, "Firma")
        pdf.drawString(x_name + 310, y, "Subunternehmen")
        pdf.drawString(x_name + 430, y, "Status")
        y -= 10
        pdf.line(36, y, page_width - 36, y)
        y -= 12
        return y

    y = page_height - 42
    y = draw_worker_page_header(y)
    pdf.setFont("Helvetica", 9)

    for row in rows:
        if y < (row_height + 12):
            pdf.showPage()
            y = page_height - 42
            y = draw_worker_page_header(y)
            pdf.setFont("Helvetica", 9)

        x_text = 36
        if include_photos:
            photo_bytes = None
            pd = row["photo_data"] or ""
            if pd.startswith("data:image/") and "," in pd:
                try:
                    b64 = pd.split(",", 1)[1]
                    photo_bytes = base64.b64decode(b64.strip())
                except Exception:
                    photo_bytes = None
            if photo_bytes:
                try:
                    img_buf = io.BytesIO(photo_bytes)
                    img_reader = ImageReader(img_buf)
                    pdf.drawImage(img_reader, 36, y - photo_size + 4, width=photo_size, height=photo_size, preserveAspectRatio=True, mask="auto")
                except Exception:
                    pass
            x_text = 36 + photo_size + 6

        text_y = y - (photo_size // 2 - 4 if include_photos else 0)
        full_name = f"{(row['last_name'] or '').strip()}, {(row['first_name'] or '').strip()}".strip(", ")
        pdf.drawString(x_text, text_y, full_name[:28])
        pdf.drawString(x_text + 170, text_y, str(row["company_name"] or "-")[:22])
        pdf.drawString(x_text + 310, text_y, str(row["subcompany_name"] or "-")[:18])
        pdf.drawString(x_text + 430, text_y, str(row["status"] or "-")[:10])
        y -= row_height

    if not rows:
        pdf.drawString(36, y, "Keine Mitarbeiter gefunden.")

    pdf.save()
    buffer.seek(0)
    filename = f"mitarbeiterliste-{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/workers/attendance.pdf")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def export_attendance_pdf():
    """Anwesenheitsliste als PDF – alle Mitarbeiter mit offenem Check-in."""
    date_param = (request.args.get("date") or datetime.now().strftime("%Y-%m-%d")).strip()
    try:
        datetime.strptime(date_param, "%Y-%m-%d")
    except ValueError:
        date_param = datetime.now().strftime("%Y-%m-%d")

    db = get_db()
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    platform_label = str(settings["platform_name"] or "BauPass").strip() if settings else "BauPass"

    # Get the latest access log entry per worker for today
    clause, params = visible_worker_clause(g.current_user, prefix="w.")
    rows = db.execute(
        f"""
        SELECT w.id AS worker_id, w.first_name, w.last_name, w.badge_id,
               al.direction, al.gate, al.timestamp,
               c.name AS company_name
        FROM workers w
        JOIN (
            SELECT worker_id, MAX(timestamp) AS latest_ts
            FROM access_logs
            WHERE DATE(timestamp) = ?
            GROUP BY worker_id
        ) latest ON latest.worker_id = w.id
        JOIN access_logs al ON al.worker_id = w.id AND al.timestamp = latest.latest_ts
        JOIN companies c ON c.id = w.company_id
        {clause}
        WHERE w.deleted_at IS NULL
        ORDER BY al.timestamp DESC
        """,
        [date_param] + list(params),
    ).fetchall()

    now_dt = datetime.now(timezone.utc)
    open_entries = build_open_entries_from_rows(rows, now_dt)

    # Add company_name for each entry
    worker_id_to_company = {row["worker_id"]: row["company_name"] for row in rows}

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib import colors as rl_colors
    except Exception:
        return jsonify({"error": "pdf_dependency_missing", "message": "Bitte reportlab installieren."}), 503

    buffer = io.BytesIO()
    page_width, page_height = A4
    pdf = rl_canvas.Canvas(buffer, pagesize=A4)
    primary_color = str(settings["invoice_primary_color"] or "#0f4c5c").strip() if settings else "#0f4c5c"

    def hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

    try:
        pr, pg, pb = hex_to_rgb(primary_color)
    except Exception:
        pr, pg, pb = 0.059, 0.298, 0.361

    row_height = 16

    def draw_header(y):
        # Header band
        pdf.setFillColorRGB(pr, pg, pb)
        pdf.rect(0, page_height - 56, page_width, 56, fill=1, stroke=0)
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(36, page_height - 28, f"{platform_label} – Anwesenheitsliste")
        pdf.setFont("Helvetica", 9)
        pdf.drawString(36, page_height - 44, f"Datum: {date_param}  |  Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  {len(open_entries)} aktive Eintritte")

        y = page_height - 72
        pdf.setFillColorRGB(0.95, 0.95, 0.95)
        pdf.rect(36, y - 2, page_width - 72, row_height, fill=1, stroke=0)
        pdf.setFillColorRGB(pr, pg, pb)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(40, y + 2, "Name")
        pdf.drawString(180, y + 2, "Firma")
        pdf.drawString(310, y + 2, "Badge-ID")
        pdf.drawString(390, y + 2, "Eintritt (UTC)")
        pdf.drawString(490, y + 2, "Tor")
        pdf.drawString(550, y + 2, "Dauer (Min)")
        return y - row_height - 4

    y = draw_header(page_height)
    pdf.setFont("Helvetica", 8)
    pdf.setFillColorRGB(0.1, 0.1, 0.1)

    severity_colors = {
        "green": (0.1, 0.6, 0.3),
        "yellow": (0.8, 0.55, 0.0),
        "red": (0.75, 0.1, 0.1),
    }

    for entry in open_entries:
        if y < 40:
            pdf.showPage()
            y = draw_header(page_height)
            pdf.setFont("Helvetica", 8)
            pdf.setFillColorRGB(0.1, 0.1, 0.1)

        sr, sg, sb = severity_colors.get(entry.get("severity", "green"), (0.1, 0.6, 0.3))
        pdf.setFillColorRGB(sr, sg, sb)
        pdf.circle(38, y + 5, 3, fill=1, stroke=0)
        pdf.setFillColorRGB(0.1, 0.1, 0.1)

        pdf.drawString(44, y + 2, str(entry.get("name", ""))[:26])
        company_name = worker_id_to_company.get(entry.get("workerId", ""), "")
        pdf.drawString(184, y + 2, str(company_name)[:20])
        pdf.drawString(314, y + 2, str(entry.get("badgeId", ""))[:14])
        ts = str(entry.get("timestamp", ""))[:16]
        pdf.drawString(394, y + 2, ts)
        pdf.drawString(494, y + 2, str(entry.get("gate", ""))[:12])
        pdf.drawString(554, y + 2, str(entry.get("openMinutes", "")))

        y -= row_height

    if not open_entries:
        pdf.setFont("Helvetica", 10)
        pdf.setFillColorRGB(0.4, 0.4, 0.4)
        pdf.drawString(36, y + 20, "Keine aktiven Eintritte für dieses Datum.")

    pdf.save()
    buffer.seek(0)
    filename = f"anwesenheitsliste-{date_param}.pdf"
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/workers")
@require_auth
@require_roles("superadmin", "company-admin")
def create_worker():
    payload = request.get_json(silent=True) or {}
    user = g.current_user
    try:
        company_id = clean_id_input(payload.get("companyId") or user.get("company_id"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    db = get_db()

    if user["role"] != "superadmin" and company_id != user.get("company_id"):
        return jsonify({"error": "forbidden_company"}), 403

    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company or company["deleted_at"]:
        return jsonify({"error": "company_not_available"}), 400

    try:
        subcompany_id = resolve_subcompany_id(db, company_id, payload.get("subcompanyId"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        photo_data = sanitize_photo_data(payload.get("photoData"), required=True)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    worker_type = normalize_worker_type(payload.get("workerType"))
    visitor_company = clean_text_input(payload.get("visitorCompany") or "", max_len=120)
    visit_purpose = clean_text_input(payload.get("visitPurpose") or "", max_len=200)
    host_name = clean_text_input(payload.get("hostName") or "", max_len=120)
    visit_end_at = parse_datetime_local_to_utc_iso(payload.get("visitEndAt"))

    if worker_type == "visitor":
        if not visit_purpose:
            return jsonify({"error": "visit_purpose_required"}), 400
        if not visitor_company:
            return jsonify({"error": "visitor_company_required"}), 400
        if not host_name:
            return jsonify({"error": "host_name_required"}), 400
        if not visit_end_at:
            return jsonify({"error": "visit_end_required"}), 400

    badge_pin_hash = ""
    if worker_type != "visitor":
        try:
            badge_pin = validate_badge_pin_or_raise(payload.get("badgePin"))
        except ValueError as error:
            return jsonify({"error": str(error), "message": "Badge-PIN muss aus 4 bis 8 Ziffern bestehen."}), 400
        badge_pin_hash = generate_password_hash(badge_pin)

    physical_card_id = normalize_physical_card_id(payload.get("physicalCardId"))
    try:
        ensure_unique_physical_card_id_or_raise(db, physical_card_id)
    except ValueError as error:
        return jsonify({"error": str(error), "message": "Diese Karten-ID ist bereits einem anderen Mitarbeiter zugeordnet."}), 409

    first_name = clean_text_input(payload.get("firstName", ""), max_len=80)
    last_name = clean_text_input(payload.get("lastName", ""), max_len=80)
    insurance_number = clean_text_input(payload.get("insuranceNumber", ""), max_len=64)
    role_value = clean_text_input(payload.get("role", ""), max_len=120)
    site_value = clean_text_input(payload.get("site", ""), max_len=120)
    valid_until_value = clean_text_input(payload.get("validUntil", ""), max_len=32)
    status_value = clean_text_input(payload.get("status", "aktiv"), max_len=32) or "aktiv"
    badge_id_value = normalize_badge_id(clean_text_input(payload.get("badgeId", f"{'VS' if worker_type == 'visitor' else 'BP'}-{secrets.token_hex(3).upper()}"), max_len=64))

    worker_id = f"wrk-{secrets.token_hex(6)}"
    db.execute(
        """
        INSERT INTO workers (
            id, company_id, subcompany_id, first_name, last_name, insurance_number, worker_type, role, site, valid_until, visitor_company, visit_purpose, host_name, visit_end_at, status, photo_data, badge_id, badge_pin_hash, physical_card_id, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            worker_id,
            company_id,
            subcompany_id,
            first_name,
            last_name,
            insurance_number if worker_type != "visitor" else "",
            worker_type,
            role_value if worker_type != "visitor" else (role_value or "Besucher"),
            site_value,
            valid_until_value,
            visitor_company,
            visit_purpose,
            host_name,
            visit_end_at,
            status_value,
            photo_data,
            badge_id_value,
            badge_pin_hash,
            physical_card_id,
            None,
        ),
    )
    db.commit()
    log_audit("worker.created", f"Mitarbeiter {first_name} {last_name} erstellt", target_type="worker", target_id=worker_id, company_id=company_id, actor=g.current_user)
    row = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    return jsonify(serialize_worker_record(row)), 201


@app.put("/api/workers/<worker_id>")
@require_auth
@require_roles("superadmin", "company-admin")
def update_worker(worker_id):
    payload = request.get_json(silent=True) or {}
    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404

    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    if worker["deleted_at"]:
        return jsonify({"error": "worker_deleted"}), 400

    photo_override_requested = bool(payload.get("photoMatchOverride"))
    photo_similarity_raw = payload.get("photoMatchSimilarity")
    photo_override_reason = clean_text_input(payload.get("photoMatchOverrideReason") or "", max_len=240)
    photo_similarity = None
    if photo_similarity_raw is not None and str(photo_similarity_raw).strip() != "":
        try:
            photo_similarity = float(photo_similarity_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_photo_match_similarity"}), 400
        if photo_similarity < 0 or photo_similarity > 1:
            return jsonify({"error": "invalid_photo_match_similarity"}), 400

    if photo_override_requested and g.current_user["role"] != "superadmin":
        return jsonify({"error": "photo_override_forbidden"}), 403
    if photo_override_requested and len(photo_override_reason) < 8:
        return jsonify({"error": "photo_override_reason_required"}), 400

    # 4-Augen: photo override requires second superadmin – validate everything first,
    # then store in operation_approvals and return 202 instead of saving immediately.
    # The actual DB write happens in execute_approved_operation after approval.
    _photo_override_needs_approval = photo_override_requested

    try:
        next_company_id = clean_id_input(payload.get("companyId", worker["company_id"]))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if g.current_user["role"] != "superadmin" and next_company_id != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_company"}), 403

    company = db.execute("SELECT * FROM companies WHERE id = ?", (next_company_id,)).fetchone()
    if not company or company["deleted_at"]:
        return jsonify({"error": "company_not_available"}), 400

    try:
        subcompany_id = resolve_subcompany_id(db, next_company_id, payload.get("subcompanyId", worker["subcompany_id"]))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    try:
        updated_photo_data = sanitize_photo_data(payload.get("photoData", worker["photo_data"]), required=True)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    next_physical_card_id = normalize_physical_card_id(payload.get("physicalCardId", worker["physical_card_id"]))
    try:
        ensure_unique_physical_card_id_or_raise(db, next_physical_card_id, worker_id_to_exclude=worker_id)
    except ValueError as error:
        return jsonify({"error": str(error), "message": "Diese Karten-ID ist bereits einem anderen Mitarbeiter zugeordnet."}), 409

    worker_type = normalize_worker_type(payload.get("workerType", worker["worker_type"]))
    visitor_company = clean_text_input(payload.get("visitorCompany", worker["visitor_company"]) or "", max_len=120)
    visit_purpose = clean_text_input(payload.get("visitPurpose", worker["visit_purpose"]) or "", max_len=200)
    host_name = clean_text_input(payload.get("hostName", worker["host_name"]) or "", max_len=120)
    visit_end_at = parse_datetime_local_to_utc_iso(payload.get("visitEndAt", worker["visit_end_at"])) if payload.get("visitEndAt", worker["visit_end_at"]) else ""
    if worker_type == "visitor":
        if not visit_purpose:
            return jsonify({"error": "visit_purpose_required"}), 400
        if not visitor_company:
            return jsonify({"error": "visitor_company_required"}), 400
        if not host_name:
            return jsonify({"error": "host_name_required"}), 400
        if not visit_end_at:
            return jsonify({"error": "visit_end_required"}), 400

    next_badge_pin_hash = worker["badge_pin_hash"] or ""
    raw_badge_pin = payload.get("badgePin")
    if worker_type != "visitor" and raw_badge_pin is not None:
        normalized_candidate_pin = normalize_badge_pin(raw_badge_pin)
        if normalized_candidate_pin:
            try:
                validated_pin = validate_badge_pin_or_raise(normalized_candidate_pin)
            except ValueError as error:
                return jsonify({"error": str(error), "message": "Badge-PIN muss aus 4 bis 8 Ziffern bestehen."}), 400
            next_badge_pin_hash = generate_password_hash(validated_pin)
        elif not next_badge_pin_hash:
            return jsonify({"error": "badge_pin_required", "message": "Bitte eine Badge-PIN fuer diesen Mitarbeiter setzen."}), 400
    if worker_type != "visitor" and not next_badge_pin_hash:
        return jsonify({"error": "badge_pin_required", "message": "Bitte eine Badge-PIN fuer diesen Mitarbeiter setzen."}), 400

    next_first_name = clean_text_input(payload.get("firstName", worker["first_name"]), max_len=80)
    next_last_name = clean_text_input(payload.get("lastName", worker["last_name"]), max_len=80)
    next_insurance_number = clean_text_input(payload.get("insuranceNumber", worker["insurance_number"]), max_len=64)
    next_role = clean_text_input(payload.get("role", worker["role"]), max_len=120)
    next_site = clean_text_input(payload.get("site", worker["site"]), max_len=120)
    next_valid_until = clean_text_input(payload.get("validUntil", worker["valid_until"]), max_len=32)
    next_status = clean_text_input(payload.get("status", worker["status"]), max_len=32) or worker["status"]

    # --- 4-Augen: if photo changed under an override, store a pending approval
    #     and return 202. The second superadmin executes the actual write.
    if _photo_override_needs_approval and updated_photo_data != (worker["photo_data"] or ""):
        approval_payload = {
            "workerId": worker_id,
            "companyId": next_company_id,
            "subcompanyId": subcompany_id,
            "firstName": next_first_name,
            "lastName": next_last_name,
            "insuranceNumber": next_insurance_number if worker_type != "visitor" else "",
            "workerType": worker_type,
            "role": next_role if worker_type != "visitor" else (next_role or visitor_company or "Besucher"),
            "site": next_site,
            "validUntil": next_valid_until,
            "visitorCompany": visitor_company,
            "visitPurpose": visit_purpose,
            "hostName": host_name,
            "visitEndAt": visit_end_at,
            "status": next_status,
            "photoData": updated_photo_data,
            "badgePinHash": next_badge_pin_hash if worker_type != "visitor" else "",
            "physicalCardId": next_physical_card_id,
            "photoMatchOverrideReason": photo_override_reason,
            "photoMatchSimilarity": photo_similarity,
        }
        approval_id = create_operation_approval(
            db,
            action_type="worker.photo_override",
            payload=approval_payload,
            actor=g.current_user,
            target_type="worker",
            target_id=worker_id,
            company_id=next_company_id,
        )
        return jsonify({
            "ok": True,
            "approvalRequested": True,
            "approvalId": approval_id,
            "message": "Foto-Override erfordert eine zweite Superadmin-Freigabe.",
        }), 202

    db.execute(
        """
        UPDATE workers
        SET company_id = ?, subcompany_id = ?, first_name = ?, last_name = ?, insurance_number = ?, worker_type = ?, role = ?, site = ?, valid_until = ?, visitor_company = ?, visit_purpose = ?, host_name = ?, visit_end_at = ?, status = ?, photo_data = ?, badge_pin_hash = ?, physical_card_id = ?
        WHERE id = ?
        """,
        (
            next_company_id,
            subcompany_id,
            next_first_name,
            next_last_name,
            next_insurance_number if worker_type != "visitor" else "",
            worker_type,
            next_role if worker_type != "visitor" else (next_role or visitor_company or "Besucher"),
            next_site,
            next_valid_until,
            visitor_company,
            visit_purpose,
            host_name,
            visit_end_at,
            next_status,
            updated_photo_data,
            next_badge_pin_hash if worker_type != "visitor" else "",
            next_physical_card_id,
            worker_id,
        ),
    )
    db.commit()

    if photo_override_requested and updated_photo_data != (worker["photo_data"] or ""):
        similarity_label = f"{photo_similarity * 100:.1f}%" if isinstance(photo_similarity, float) else "n/a"
        log_audit(
            "security.worker_photo_override",
            f"Foto-Override fuer Mitarbeiter {worker_id} bestaetigt (Aehnlichkeit: {similarity_label}, Grund: {photo_override_reason})",
            target_type="worker",
            target_id=worker_id,
            company_id=worker["company_id"],
            actor=g.current_user,
        )

    log_audit("worker.updated", f"Mitarbeiter {worker_id} aktualisiert", target_type="worker", target_id=worker_id, company_id=worker["company_id"], actor=g.current_user)
    return jsonify({"ok": True})


@app.delete("/api/workers/<worker_id>")
@require_auth
@require_roles("superadmin", "company-admin")
def delete_worker(worker_id):
    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404

    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    db.execute("UPDATE workers SET deleted_at = ? WHERE id = ?", (now_iso(), worker_id))
    db.commit()
    log_audit("worker.deleted", f"Mitarbeiter {worker_id} geloescht", target_type="worker", target_id=worker_id, company_id=worker["company_id"], actor=g.current_user)
    return jsonify({"ok": True})


@app.post("/api/workers/<worker_id>/restore")
@require_auth
@require_roles("superadmin", "company-admin")
def restore_worker(worker_id):
    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404

    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    db.execute("UPDATE workers SET deleted_at = NULL WHERE id = ?", (worker_id,))
    db.commit()
    log_audit("worker.restored", f"Mitarbeiter {worker_id} wiederhergestellt", target_type="worker", target_id=worker_id, company_id=worker["company_id"], actor=g.current_user)
    return jsonify({"ok": True})


@app.post("/api/workers/<worker_id>/reset-pin")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def reset_worker_pin(worker_id):
    payload = request.get_json(silent=True) or {}
    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404
    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403
    if worker["deleted_at"]:
        return jsonify({"error": "worker_deleted"}), 400
    if worker["badge_id"].upper().startswith("VS"):
        return jsonify({"error": "visitor_no_pin", "message": "Besucher haben keine Badge-PIN."}), 400

    raw_pin = normalize_badge_pin(payload.get("newPin", ""))
    if not raw_pin:
        return jsonify({"error": "missing_pin", "message": "Bitte eine neue PIN angeben."}), 400
    try:
        validated_pin = validate_badge_pin_or_raise(raw_pin)
    except ValueError as error:
        return jsonify({"error": "invalid_pin", "message": str(error)}), 400

    new_hash = generate_password_hash(validated_pin)
    db.execute("UPDATE workers SET badge_pin_hash = ? WHERE id = ?", (new_hash, worker_id))
    db.commit()
    log_audit(
        "worker.pin_reset",
        f"Badge-PIN fuer {worker['first_name']} {worker['last_name']} (Badge {worker['badge_id']}) wurde zurueckgesetzt",
        target_type="worker", target_id=worker_id, company_id=worker["company_id"], actor=g.current_user
    )
    return jsonify({"ok": True})


def build_worker_app_access_payload(db, worker_id, actor_user):
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return None, (jsonify({"error": "worker_not_found"}), 404)

    if actor_user["role"] != "superadmin" and worker["company_id"] != actor_user.get("company_id"):
        return None, (jsonify({"error": "forbidden_worker"}), 403)

    if worker["deleted_at"]:
        return None, (jsonify({"error": "worker_deleted"}), 400)

    if worker_visit_has_expired(worker):
        return None, (jsonify({"error": "visitor_visit_expired", "message": "Diese Besucherkarte ist zeitlich abgelaufen."}), 400)

    now = now_iso()
    db.execute(
        "UPDATE worker_app_tokens SET revoked_at = ? WHERE worker_id = ? AND revoked_at IS NULL AND expires_at >= ?",
        (now, worker_id, now),
    )

    access_token = secrets.token_urlsafe(32)
    access_expires_at = resolve_worker_access_token_expiry_iso(worker)
    db.execute(
        "INSERT INTO worker_app_tokens (token, worker_id, expires_at, revoked_at, created_by_user_id) VALUES (?, ?, ?, NULL, ?)",
        (access_token, worker_id, access_expires_at, actor_user["id"]),
    )
    db.commit()

    link = f"{get_public_base_url()}/worker.html?access={access_token}"
    return {
        "accessToken": access_token,
        "link": link,
        "created": True,
        "oneTime": True,
        "accessExpiresAt": access_expires_at,
        "workerId": worker_id,
    }, None


def serialize_worker_for_app(worker):
    site_location = None
    latitude = worker["site_latitude"] if hasattr(worker, "keys") and "site_latitude" in worker.keys() else None
    longitude = worker["site_longitude"] if hasattr(worker, "keys") and "site_longitude" in worker.keys() else None
    if latitude is not None and longitude is not None:
        site_location = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "radiusMeters": WORKER_LOGIN_MAX_DISTANCE_METERS,
        }
    return {
        "id": worker["id"],
        "subcompanyId": worker["subcompany_id"],
        "firstName": worker["first_name"],
        "lastName": worker["last_name"],
        "workerType": normalize_worker_type(worker["worker_type"]),
        "role": worker["role"],
        "site": worker["site"],
        "validUntil": worker["valid_until"],
        "visitorCompany": worker["visitor_company"],
        "visitPurpose": worker["visit_purpose"],
        "hostName": worker["host_name"],
        "visitEndAt": worker["visit_end_at"],
        "status": worker["status"],
        "photoData": worker["photo_data"],
        "badgeId": worker["badge_id"],
        "siteLocation": site_location,
    }


def _normalize_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_meters(latitude_a, longitude_a, latitude_b, longitude_b):
    earth_radius_m = 6371000.0
    lat1 = math.radians(float(latitude_a))
    lon1 = math.radians(float(longitude_a))
    lat2 = math.radians(float(latitude_b))
    lon2 = math.radians(float(longitude_b))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    haversine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(haversine))


def _geocode_site_address(site_label):
    normalized = str(site_label or "").strip()
    if not normalized:
        return None
    cache_key = normalized.lower()
    if cache_key in _site_geocode_cache:
        return _site_geocode_cache[cache_key]

    encoded_query = quote(normalized)
    geocode_url = f"https://nominatim.openstreetmap.org/search?q={encoded_query}&format=jsonv2&limit=1"
    request_obj = Request(
        geocode_url,
        headers={
            "User-Agent": "BauPass Control/1.0 (worker geofence)",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request_obj, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        _site_geocode_cache[cache_key] = None
        return None

    if not payload:
        _site_geocode_cache[cache_key] = None
        return None

    first_hit = payload[0]
    latitude = _normalize_float(first_hit.get("lat"))
    longitude = _normalize_float(first_hit.get("lon"))
    if latitude is None or longitude is None:
        _site_geocode_cache[cache_key] = None
        return None

    _site_geocode_cache[cache_key] = (latitude, longitude)
    return _site_geocode_cache[cache_key]


def ensure_worker_site_coordinates(db, worker):
    latitude = worker["site_latitude"] if hasattr(worker, "keys") and "site_latitude" in worker.keys() else None
    longitude = worker["site_longitude"] if hasattr(worker, "keys") and "site_longitude" in worker.keys() else None
    if latitude is not None and longitude is not None:
        return float(latitude), float(longitude)

    geocoded = _geocode_site_address(worker["site"])
    if not geocoded:
        return None

    latitude, longitude = geocoded
    db.execute(
        "UPDATE workers SET site_latitude = ?, site_longitude = ? WHERE id = ?",
        (latitude, longitude, worker["id"]),
    )
    db.commit()
    return latitude, longitude


def validate_worker_login_distance_or_raise(db, worker, payload):
    if normalize_worker_type(worker["worker_type"]) != "worker":
        return None

    location = payload.get("location") if isinstance(payload, dict) else None
    if not isinstance(location, dict):
        raise ValueError("worker_geolocation_required")

    device_latitude = _normalize_float(location.get("latitude"))
    device_longitude = _normalize_float(location.get("longitude"))
    if device_latitude is None or device_longitude is None:
        raise ValueError("worker_geolocation_required")

    site_coordinates = ensure_worker_site_coordinates(db, worker)
    if not site_coordinates:
        # Koordinaten nicht ermittelbar – Geofence-Prüfung überspringen, Login erlauben.
        # Dies passiert wenn der Baustellen-Name keine geocodierbare Adresse ist.
        return None

    distance_meters = _haversine_meters(site_coordinates[0], site_coordinates[1], device_latitude, device_longitude)
    if distance_meters > WORKER_LOGIN_MAX_DISTANCE_METERS:
        raise PermissionError(f"outside_site_radius:{int(round(distance_meters))}")

    return {
        "distanceMeters": int(round(distance_meters)),
        "siteLatitude": float(site_coordinates[0]),
        "siteLongitude": float(site_coordinates[1]),
    }


def normalize_badge_id(value):
    normalized = str(value or "").strip().upper()
    # Normalize unicode dash variants and remove all whitespace inside the ID.
    normalized = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def normalize_badge_pin(value):
    return re.sub(r"\s+", "", str(value or "").strip())


def validate_badge_pin_or_raise(pin_value):
    normalized_pin = normalize_badge_pin(pin_value)
    if not re.fullmatch(r"\d{4,8}", normalized_pin):
        raise ValueError("invalid_badge_pin")
    return normalized_pin


def normalize_physical_card_id(value):
    normalized = str(value or "").strip().upper()
    return normalized or None


def ensure_unique_physical_card_id_or_raise(db, physical_card_id, worker_id_to_exclude=None):
    if not physical_card_id:
        return
    if worker_id_to_exclude:
        duplicate = db.execute(
            """
            SELECT id
            FROM workers
            WHERE physical_card_id = ? AND id != ? AND deleted_at IS NULL
            LIMIT 1
            """,
            (physical_card_id, worker_id_to_exclude),
        ).fetchone()
    else:
        duplicate = db.execute(
            """
            SELECT id
            FROM workers
            WHERE physical_card_id = ? AND deleted_at IS NULL
            LIMIT 1
            """,
            (physical_card_id,),
        ).fetchone()
    if duplicate:
        raise ValueError("duplicate_physical_card_id")


def create_access_log_entry(db, worker_id, direction, gate, note, timestamp_value=None):
    log_id = f"log-{secrets.token_hex(6)}"
    db.execute(
        "INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (
            log_id,
            worker_id,
            direction,
            gate,
            note,
            timestamp_value or now_iso(),
        ),
    )
    return log_id


def create_worker_app_session(db, worker):
    session_token = secrets.token_urlsafe(28)
    expires_at = resolve_worker_session_expiry_iso(worker)
    site_coordinates = ensure_worker_site_coordinates(db, worker)
    db.execute(
        "INSERT INTO worker_app_sessions (token, worker_id, expires_at) VALUES (?, ?, ?)",
        (session_token, worker["id"], expires_at),
    )
    db.commit()
    worker_payload = dict(worker)
    if site_coordinates:
        worker_payload["site_latitude"] = float(site_coordinates[0])
        worker_payload["site_longitude"] = float(site_coordinates[1])
    return {
        "token": session_token,
        "worker": serialize_worker_for_app(worker_payload),
        "sessionExpiresAt": expires_at,
        "cardType": normalize_worker_type(worker["worker_type"]),
    }


@app.get("/api/workers/<worker_id>/app-access")
@require_auth
@require_roles("superadmin", "company-admin")
def get_worker_app_access(worker_id):
    payload, error_response = build_worker_app_access_payload(get_db(), worker_id, g.current_user)
    if error_response:
        return error_response
    return jsonify(payload)


@app.post("/api/workers/<worker_id>/app-access")
@require_auth
@require_roles("superadmin", "company-admin")
def create_worker_app_access(worker_id):
    db = get_db()
    payload, error_response = build_worker_app_access_payload(db, worker_id, g.current_user)
    if error_response:
        return error_response
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    log_audit("worker.app_access_created", f"Mitarbeiter-App-Link fuer {worker_id} erzeugt", target_type="worker", target_id=worker_id, company_id=worker["company_id"], actor=g.current_user)
    return jsonify(payload)


@app.post("/api/worker-app/login")
@require_rate_limit("worker_login")
def worker_app_login():
    payload = request.get_json(silent=True) or {}
    access_token = (payload.get("accessToken") or "").strip()
    badge_id = normalize_badge_id(payload.get("badgeId"))
    badge_pin = normalize_badge_pin(payload.get("badgePin"))
    if not access_token and not badge_id:
        return jsonify({"error": "missing_worker_app_credentials"}), 400

    db = get_db()
    deleted = purge_expired_worker_app_sessions(db)
    if deleted > 0:
        db.commit()
    setting = db.execute("SELECT worker_app_enabled FROM settings WHERE id = 1").fetchone()
    if setting and int(setting["worker_app_enabled"]) == 0:
        return jsonify({"error": "worker_app_disabled", "message": "Die Mitarbeiter-App ist zurzeit nicht verfuegbar. Bitte spaeter erneut versuchen."}), 503

    if access_token:
        token_row = db.execute("SELECT * FROM worker_app_tokens WHERE token = ?", (access_token,)).fetchone()
        if not token_row:
            return jsonify({"error": "invalid_access_token"}), 401

        if token_row["revoked_at"]:
            return jsonify({"error": "access_token_already_used", "message": "Dieser Besucherkarten-Link wurde bereits genutzt."}), 401

        if token_row["expires_at"] < now_iso():
            return jsonify({"error": "access_token_expired"}), 401

        worker = db.execute("SELECT * FROM workers WHERE id = ?", (token_row["worker_id"],)).fetchone()
        if not worker or worker["deleted_at"]:
            return jsonify({"error": "worker_not_available"}), 401

        if worker_visit_has_expired(worker):
            return jsonify({"error": "visitor_visit_expired", "message": "Diese Besucherkarte ist zeitlich abgelaufen."}), 401

        company_error = get_company_access_error(db, worker["company_id"])
        if company_error:
            return jsonify(company_error), 403

        # Einmal-Link (QR) soll unmittelbar funktionieren. Standortpruefung bleibt
        # weiterhin fuer Badge-ID/PIN-Login aktiv (siehe unten im badge_id-Branch).

        consumed_at = now_iso()
        consumed = db.execute(
            "UPDATE worker_app_tokens SET revoked_at = ? WHERE token = ? AND revoked_at IS NULL",
            (consumed_at, access_token),
        )
        if int(consumed.rowcount or 0) == 0:
            return jsonify({"error": "access_token_already_used", "message": "Dieser Besucherkarten-Link wurde bereits genutzt."}), 401

        session_data = create_worker_app_session(db, worker)
        log_audit(
            "worker_app.login",
            f"Besucher {worker['first_name']} {worker['last_name']} (Badge {worker['badge_id']}) hat sich per Einmal-Link angemeldet",
            target_type="worker", target_id=worker["id"], company_id=worker["company_id"]
        )
        db.commit()
        return jsonify(session_data)

    badge_matches = db.execute(
        """
        SELECT *
        FROM workers
                WHERE UPPER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(badge_id, ' ', ''), char(9), ''), char(10), ''), char(13), ''), '‐', '-'), '‑', '-'), '–', '-'), '—', '-')) = ?
                    AND deleted_at IS NULL
        ORDER BY id
        LIMIT 2
        """,
        (badge_id,),
    ).fetchall()
    if not badge_matches:
        return jsonify({"error": "invalid_badge_id", "message": "Badge-ID wurde nicht gefunden."}), 401
    if len(badge_matches) > 1:
        return jsonify({"error": "duplicate_badge_id", "message": "Badge-ID ist mehrfach vergeben. Bitte Admin informieren."}), 409

    worker = badge_matches[0]
    if worker_visit_has_expired(worker):
        return jsonify({"error": "visitor_visit_expired", "message": "Diese Besucherkarte ist zeitlich abgelaufen."}), 401

    is_visitor = badge_id.startswith("VS")
    if not is_visitor:
        if not worker["badge_pin_hash"]:
            return jsonify({"error": "badge_pin_not_configured", "message": "Fuer diese Karte ist noch keine Badge-PIN hinterlegt."}), 403
        if not badge_pin:
            return jsonify({"error": "missing_badge_pin", "message": "Bitte Badge-PIN eingeben."}), 400
        if not check_password_hash(worker["badge_pin_hash"], badge_pin):
            return jsonify({"error": "invalid_badge_pin", "message": "Badge-ID oder PIN ist ungueltig."}), 401

    company_error = get_company_access_error(db, worker["company_id"])
    if company_error:
        return jsonify(company_error), 403

    try:
        validate_worker_login_distance_or_raise(db, worker, payload)
    except ValueError as exc:
        error_code = str(exc)
        if error_code == "worker_geolocation_required":
            return jsonify({"error": error_code, "message": "Bitte Standortfreigabe aktivieren und direkt auf der Baustelle anmelden."}), 400
        if error_code == "site_location_unavailable":
            return jsonify({"error": error_code, "message": "Fuer diese Baustelle konnten noch keine Koordinaten ermittelt werden. Bitte Admin informieren."}), 403
        raise
    except PermissionError as exc:
        distance_text = str(exc).split(":", 1)[1] if ":" in str(exc) else ""
        return jsonify({"error": "outside_site_radius", "message": f"Login nur auf der Baustelle moeglich (max. {WORKER_LOGIN_MAX_DISTANCE_METERS} m). Aktuell ca. {distance_text} m entfernt."}), 403

    session_data = create_worker_app_session(db, worker)
    login_type = "Besucher" if is_visitor else "Mitarbeiter"
    log_audit(
        "worker_app.login",
        f"{login_type} {worker['first_name']} {worker['last_name']} (Badge {badge_id}) hat sich per Badge-ID angemeldet",
        target_type="worker", target_id=worker["id"], company_id=worker["company_id"]
    )
    db.commit()
    return jsonify(session_data)


@app.get("/api/worker-app/me")
@require_worker_session
def worker_app_me():
    db = get_db()
    worker = g.worker
    company = db.execute("SELECT * FROM companies WHERE id = ?", (worker["company_id"],)).fetchone()
    subcompany = None
    if worker["subcompany_id"]:
        subcompany = db.execute("SELECT * FROM subcompanies WHERE id = ?", (worker["subcompany_id"],)).fetchone()
    setting = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return jsonify(
        {
            "worker": serialize_worker_for_app(worker),
            "company": {
                "name": company["name"] if company else "",
            },
            "subcompany": {
                "name": subcompany["name"] if subcompany else "",
            },
            "settings": {
                "platformName": setting["platform_name"],
                "operatorName": setting["operator_name"],
            },
            "sessionExpiresAt": getattr(g, "worker_session_expires_at", ""),
            "cardType": normalize_worker_type(worker["worker_type"]),
        }
    )


@app.post("/api/worker-app/offline-events")
@require_worker_session
def worker_app_sync_offline_events():
    payload = request.get_json(silent=True) or {}
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        return jsonify({"error": "invalid_offline_events"}), 400

    worker = g.worker
    stored_count = 0
    for event in events[:50]:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "offline_login").strip() or "offline_login"
        occurred_at = str(event.get("occurredAt") or now_iso()).strip() or now_iso()
        distance_meters = _normalize_float(event.get("distanceMeters"))
        message = f"Offline-Ereignis nachsynchronisiert: {event_type} | Zeitpunkt {occurred_at}"
        if distance_meters is not None:
            message += f" | Distanz {int(round(distance_meters))} m"
        log_audit(
            f"worker_app.{event_type}",
            message,
            target_type="worker",
            target_id=worker["id"],
            company_id=worker["company_id"],
        )
        stored_count += 1

    return jsonify({"ok": True, "stored": stored_count})


@app.post("/api/worker-app/logout")
@require_worker_session
def worker_app_logout():
    db = get_db()
    db.execute("DELETE FROM worker_app_sessions WHERE token = ?", (g.worker_token,))
    db.commit()
    return jsonify({"ok": True})


@app.put("/api/companies/<company_id>")
@require_auth
@require_roles("superadmin")
def update_company(company_id):
    payload = request.get_json(silent=True) or {}
    db = get_db()
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "company_not_found"}), 404

    company_name = clean_text_input(payload.get("name", company["name"]), max_len=120)
    company_contact = clean_text_input(payload.get("contact", company["contact"]), max_len=180)
    company_billing_email = clean_text_input(payload.get("billingEmail", company["billing_email"]), max_len=160)
    company_document_email = clean_text_input(payload.get("documentEmail", company["document_email"]), max_len=160)
    if not company_document_email:
        company_document_email = suggest_company_document_email(company_name)
    company_access_host = clean_text_input((payload.get("accessHost") or payload.get("access_host") or company["access_host"]), max_len=180)
    company_branding_preset = normalize_branding_preset(payload.get("brandingPreset") or payload.get("branding_preset") or company["branding_preset"])
    company_status = clean_text_input(payload.get("status", company["status"]), max_len=32) or company["status"]

    db.execute(
        "UPDATE companies SET name = ?, contact = ?, billing_email = ?, document_email = ?, access_host = ?, branding_preset = ?, plan = ?, status = ? WHERE id = ?",
        (
            company_name,
            company_contact,
            company_billing_email,
            company_document_email,
            company_access_host,
            company_branding_preset,
            payload.get("plan", company["plan"]),
            company_status,
            company_id,
        ),
    )
    rematch_inbox_company_links(db, company_id=company_id)
    db.commit()
    log_audit("company.updated", f"Firma {company_id} aktualisiert", target_type="company", target_id=company_id, company_id=company_id, actor=g.current_user)
    return jsonify({"ok": True})


@app.post("/api/documents/inbox/rematch-company-links")
@require_auth
@require_roles("superadmin")
def rematch_document_inbox_links():
    db = get_db()
    count = rematch_inbox_company_links(db)
    db.commit()
    return jsonify({"ok": True, "matchedCount": count})


@app.post("/api/documents/inbox/<inbox_id>/match-company")
@require_auth
@require_roles("superadmin")
def set_document_inbox_company_match(inbox_id):
    payload = request.get_json(silent=True) or {}
    company_id = clean_text_input(payload.get("companyId", ""), max_len=64)
    db = get_db()

    inbox_row = db.execute("SELECT id FROM email_inbox WHERE id = ?", (inbox_id,)).fetchone()
    if not inbox_row:
        return jsonify({"error": "inbox_not_found"}), 404

    if company_id:
        company = db.execute("SELECT id FROM companies WHERE id = ? AND deleted_at IS NULL", (company_id,)).fetchone()
        if not company:
            return jsonify({"error": "company_not_found"}), 404
        db.execute("UPDATE email_inbox SET matched_company_id = ? WHERE id = ?", (company_id, inbox_id))
    else:
        db.execute("UPDATE email_inbox SET matched_company_id = NULL WHERE id = ?", (inbox_id,))

    db.commit()
    return jsonify({"ok": True})


@app.delete("/api/companies/<company_id>")
@require_auth
@require_roles("superadmin")
def delete_company(company_id):
    if company_id == "cmp-default":
        return jsonify({"error": "default_company_protected"}), 400

    db = get_db()
    force = request.args.get("force", "0") == "1"
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "company_not_found"}), 404

    count = db.execute("SELECT COUNT(*) AS c FROM workers WHERE company_id = ? AND deleted_at IS NULL", (company_id,)).fetchone()["c"]
    if count > 0 and not force:
        return jsonify({"error": "company_has_workers"}), 400

    if force:
        now = now_iso()
        worker_rows = db.execute("SELECT id FROM workers WHERE company_id = ?", (company_id,)).fetchall()
        worker_ids = [row["id"] for row in worker_rows]

        db.execute("UPDATE workers SET deleted_at = ?, status = 'gesperrt' WHERE company_id = ?", (now, company_id))
        db.execute("UPDATE subcompanies SET deleted_at = ?, status = 'pausiert' WHERE company_id = ?", (now, company_id))
        db.execute("UPDATE companies SET deleted_at = ?, status = ? WHERE id = ?", (now, "pausiert", company_id))
        db.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE company_id = ?)", (company_id,))

        if worker_ids:
            placeholders = ",".join(["?"] * len(worker_ids))
            db.execute(f"DELETE FROM worker_app_tokens WHERE worker_id IN ({placeholders})", worker_ids)
            db.execute(f"DELETE FROM worker_app_sessions WHERE worker_id IN ({placeholders})", worker_ids)
    else:
        db.execute("UPDATE companies SET deleted_at = ?, status = ? WHERE id = ?", (now_iso(), "pausiert", company_id))

    db.commit()
    log_audit(
        "company.deleted",
        f"Firma {company_id} gelöscht{' (force)' if force else ''}",
        target_type="company",
        target_id=company_id,
        company_id=company_id,
        actor=g.current_user,
    )
    return jsonify({"ok": True, "force": force})


@app.put("/api/companies/<company_id>/admin-security")
@require_auth
@require_roles("superadmin")
def set_company_admin_security(company_id):
    """Superadmin sets OTP email and enables/disables 2FA for a company's admin user."""
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    enable_2fa = bool(payload.get("enable2fa", False))
    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({"error": "invalid_email"}), 400
    db = get_db()
    admin_user = db.execute(
        "SELECT id, username, email, twofa_enabled FROM users WHERE company_id = ? AND role = 'company-admin' LIMIT 1",
        (company_id,)
    ).fetchone()
    if not admin_user:
        return jsonify({"error": "admin_not_found"}), 404
    db.execute(
        "UPDATE users SET email = ?, twofa_enabled = ? WHERE id = ?",
        (email, 1 if enable_2fa else 0, admin_user["id"])
    )
    if not enable_2fa:
        db.execute("DELETE FROM otp_codes WHERE user_id = ?", (admin_user["id"],))
    db.commit()
    log_audit("security.admin_otp_updated",
              f"OTP-Einstellungen fuer Admin '{admin_user['username']}' der Firma {company_id} aktualisiert",
              target_type="user", target_id=admin_user["id"], actor=g.current_user)
    return jsonify({"ok": True, "username": admin_user["username"], "email": email, "twofa_enabled": enable_2fa})


@app.get("/api/companies/<company_id>/admin-security")
@require_auth
@require_roles("superadmin")
def get_company_admin_security(company_id):
    """Get OTP/2FA status of a company's admin user."""
    db = get_db()
    admin_user = db.execute(
        "SELECT username, email, twofa_enabled FROM users WHERE company_id = ? AND role = 'company-admin' LIMIT 1",
        (company_id,)
    ).fetchone()
    if not admin_user:
        return jsonify({"error": "admin_not_found"}), 404
    return jsonify({
        "username": admin_user["username"],
        "email": admin_user["email"] or "",
        "twofa_enabled": bool(int(admin_user["twofa_enabled"] or 0))
    })


@app.post("/api/companies/<company_id>/add-turnstile")
@require_auth
@require_roles("superadmin")
def add_company_turnstile(company_id):
    payload = request.get_json(silent=True) or {}
    db = get_db()

    company = db.execute("SELECT * FROM companies WHERE id = ? AND deleted_at IS NULL", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "company_not_found"}), 404

    password = (payload.get("password") or "").strip()
    if len(password) < 4:
        return jsonify({"error": "password_too_short", "message": "Passwort muss mindestens 4 Zeichen haben."}), 400

    # Zähle vorhandene Drehkreuze dieser Firma
    existing_count = db.execute(
        "SELECT COUNT(*) AS c FROM users WHERE company_id = ? AND role = 'turnstile'",
        (company_id,),
    ).fetchone()["c"]

    username_base_raw = "".join(c for c in company["name"].lower() if c.isalnum())[:12] or "gate"
    username_base = f"{username_base_raw}gate{existing_count + 1}"
    username = username_base
    suffix = 1
    while db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        username = f"{username_base}{suffix}"
        suffix += 1

    display_name = f"{company['name']} Drehkreuz {existing_count + 1}"
    user_id = f"usr-{secrets.token_hex(6)}"
    api_key = create_turnstile_api_key()
    db.execute(
        "INSERT INTO users (id, username, password_hash, name, role, company_id, api_key_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, generate_password_hash(password), display_name, "turnstile", company_id, hash_turnstile_api_key(api_key)),
    )
    db.commit()
    log_audit(
        "company.turnstile_added",
        f"Drehkreuz-Zugang '{username}' für Firma {company['name']} angelegt",
        target_type="company",
        target_id=company_id,
        company_id=company_id,
        actor=g.current_user,
    )
    return jsonify({"ok": True, "username": username, "password": password, "apiKey": api_key}), 201


# ── Drehkreuz-User Verwaltung ──────────────────────────────────────────────

@app.get("/api/companies/<company_id>/turnstiles")
@require_auth
@require_roles("superadmin", "company-admin")
def list_company_turnstiles(company_id):
    user = g.current_user
    # Company-Admins duerfen nur ihre eigene Firma einsehen
    if user["role"] == "company-admin" and user.get("company_id") != company_id:
        return jsonify({"error": "forbidden"}), 403
    db = get_db()
    company = db.execute("SELECT id FROM companies WHERE id = ? AND deleted_at IS NULL", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "company_not_found"}), 404
    rows = db.execute(
        """SELECT u.id, u.username, u.name, u.is_active,
                  CASE WHEN COALESCE(u.api_key_hash, '') != '' THEN 1 ELSE 0 END AS has_api_key,
                  MAX(s.last_seen) AS last_seen
           FROM users u
           LEFT JOIN sessions s ON s.user_id = u.id
           WHERE u.company_id = ? AND u.role = 'turnstile'
           GROUP BY u.id ORDER BY u.name""",
        (company_id,),
    ).fetchall()
    return jsonify([
        {"id": r["id"], "username": r["username"], "name": r["name"],
         "isActive": int(r["is_active"] or 1) == 1, "lastSeen": r["last_seen"], "hasApiKey": int(r["has_api_key"] or 0) == 1}
        for r in rows
    ])


@app.post("/api/companies/<company_id>/turnstiles/<user_id>/reset-password")
@require_auth
@require_roles("superadmin", "company-admin")
def reset_turnstile_password(company_id, user_id):
    # Company-Admins duerfen nur ihre eigene Firma verwalten
    if g.current_user["role"] == "company-admin" and g.current_user.get("company_id") != company_id:
        return jsonify({"error": "forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    password = (payload.get("password") or "").strip()
    if len(password) < 4:
        return jsonify({"error": "password_too_short"}), 400
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id = ? AND company_id = ? AND role = 'turnstile'",
        (user_id, company_id),
    ).fetchone()
    if not user:
        return jsonify({"error": "user_not_found"}), 404
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), user_id))
    db.commit()
    log_audit("security.turnstile_password_reset", f"Passwort für Drehkreuz '{user['username']}' zurückgesetzt",
              target_type="user", target_id=user_id, company_id=company_id, actor=g.current_user)
    return jsonify({"ok": True})


@app.post("/api/companies/<company_id>/turnstiles/<user_id>/rotate-api-key")
@require_auth
@require_roles("superadmin")
def rotate_turnstile_api_key(company_id, user_id):
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id = ? AND company_id = ? AND role = 'turnstile'",
        (user_id, company_id),
    ).fetchone()
    if not user:
        return jsonify({"error": "user_not_found"}), 404

    api_key = create_turnstile_api_key()
    db.execute("UPDATE users SET api_key_hash = ? WHERE id = ?", (hash_turnstile_api_key(api_key), user_id))
    db.commit()
    log_audit(
        "security.turnstile_api_key_rotated",
        f"API-Key für Drehkreuz '{user['username']}' rotiert",
        target_type="user",
        target_id=user_id,
        company_id=company_id,
        actor=g.current_user,
    )
    return jsonify({"ok": True, "apiKey": api_key})


@app.post("/api/companies/<company_id>/turnstiles/<user_id>/toggle-active")
@require_auth
@require_roles("superadmin")
def toggle_turnstile_active(company_id, user_id):
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id = ? AND company_id = ? AND role = 'turnstile'",
        (user_id, company_id),
    ).fetchone()
    if not user:
        return jsonify({"error": "user_not_found"}), 404
    new_active = 0 if int(user["is_active"] or 1) == 1 else 1
    db.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_active, user_id))
    if new_active == 0:
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.commit()
    log_audit(
        "security.turnstile_toggled",
        f"Drehkreuz '{user['username']}' {'deaktiviert' if not new_active else 'aktiviert'}",
        target_type="user", target_id=user_id, company_id=company_id, actor=g.current_user,
    )
    return jsonify({"ok": True, "isActive": new_active == 1})


# ── Compliance-Übersicht ───────────────────────────────────────────────────

REQUIRED_DOC_TYPES = ["mindestlohnnachweis", "personalausweis"]

@app.get("/api/compliance/overview")
@require_auth
@require_roles("superadmin", "company-admin")
def compliance_overview():
    user = g.current_user
    db = get_db()
    today = now_iso()[:10]

    if user["role"] == "superadmin":
        companies = db.execute("SELECT id, name FROM companies WHERE deleted_at IS NULL ORDER BY name").fetchall()
    else:
        companies = db.execute("SELECT id, name FROM companies WHERE id = ?", (user["company_id"],)).fetchall()

    result = []
    for company in companies:
        workers = db.execute(
            "SELECT id, first_name, last_name, badge_id, status FROM workers WHERE company_id = ? AND deleted_at IS NULL AND worker_type = 'worker'",
            (company["id"],),
        ).fetchall()

        company_entry = {"companyId": company["id"], "companyName": company["name"], "workers": []}
        for worker in workers:
            docs = db.execute(
                "SELECT doc_type, expiry_date FROM worker_documents WHERE worker_id = ? ORDER BY created_at DESC",
                (worker["id"],),
            ).fetchall()
            present_types = {}
            for doc in docs:
                dt = doc["doc_type"]
                if dt not in present_types:
                    present_types[dt] = doc["expiry_date"]

            worker_status = {}
            overall = "ok"
            for req in REQUIRED_DOC_TYPES:
                if req not in present_types:
                    worker_status[req] = "missing"
                    overall = "red"
                else:
                    expiry = present_types[req]
                    if expiry and expiry < today:
                        worker_status[req] = "expired"
                        if overall != "red":
                            overall = "yellow"
                    elif expiry:
                        days_left = (datetime.strptime(expiry, "%Y-%m-%d").date() - utc_now().date()).days
                        if days_left <= 30:
                            worker_status[req] = "expiring_soon"
                            if overall == "ok":
                                overall = "yellow"
                        else:
                            worker_status[req] = "ok"
                    else:
                        worker_status[req] = "ok"

            company_entry["workers"].append({
                "id": worker["id"],
                "name": f"{worker['first_name']} {worker['last_name']}".strip(),
                "badgeId": worker["badge_id"],
                "status": worker["status"],
                "docs": worker_status,
                "overall": overall,
            })

        red_count = sum(1 for w in company_entry["workers"] if w["overall"] == "red")
        yellow_count = sum(1 for w in company_entry["workers"] if w["overall"] == "yellow")
        company_entry["redCount"] = red_count
        company_entry["yellowCount"] = yellow_count
        company_entry["greenCount"] = len(company_entry["workers"]) - red_count - yellow_count
        result.append(company_entry)

    return jsonify(result)


# ── Passwort-Reset per E-Mail ──────────────────────────────────────────────

@app.post("/api/auth/request-password-reset")
@require_rate_limit("password_reset")
def request_password_reset():
    payload = request.get_json(silent=True) or {}
    username = clean_text_input(payload.get("username") or "", max_len=120)
    if not username:
        return jsonify({"ok": True})  # Keine Rückmeldung ob User existiert

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username = ? AND role IN ('company-admin', 'superadmin')",
        (username,),
    ).fetchone()
    if not user:
        return jsonify({"ok": True})

    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    smtp_host = (settings["smtp_host"] if settings else "").strip()
    smtp_sender = (settings["smtp_sender_email"] if settings else "").strip()
    if not smtp_host or not smtp_sender:
        return jsonify({"error": "smtp_not_configured", "message": "E-Mail-Versand ist nicht konfiguriert."}), 503

    raw_token = secrets.token_urlsafe(32)
    token_hash = __import__("hashlib").sha256(raw_token.encode()).hexdigest()
    token_id = f"rst-{secrets.token_hex(8)}"
    expires_at = utc_iso(utc_now() + timedelta(hours=2))

    db.execute(
        "INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at, created_at) VALUES (?,?,?,?,?)",
        (token_id, user["id"], token_hash, expires_at, now_iso()),
    )
    db.commit()

    base_url = request.host_url.rstrip("/")
    reset_link = f"{base_url}/?resetToken={raw_token}"
    msg = __import__("email.message", fromlist=["EmailMessage"]).EmailMessage()
    msg["Subject"] = "Passwort zurücksetzen – BauPass Control"
    msg["From"] = f"{settings['smtp_sender_name']} <{smtp_sender}>"

    # Empfänger-Priorität: 1) users.email, 2) billing_email der Firma, 3) username als Fallback
    user_email = (user["email"] or "").strip() if user["email"] else ""
    if not user_email:
        company_row = db.execute("SELECT billing_email FROM companies WHERE id = ?", (user["company_id"] or "",)).fetchone()
        user_email = (company_row["billing_email"] if company_row else "") or username
    recipient = user_email or username
    msg["To"] = recipient
    msg.set_content(
        f"Hallo {user['name']},\n\nKlicke auf folgenden Link, um dein Passwort zurückzusetzen (gültig 2 Stunden):\n\n{reset_link}\n\nWenn du das nicht angefordert hast, ignoriere diese E-Mail.\n\nViele Grüße\n{settings['operator_name']}"
    )

    try:
        import smtplib
        smtp_port = int(settings["smtp_port"] or 587)
        use_ssl = smtp_port == 465
        if use_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as smtp:
                if (settings["smtp_username"] or "").strip():
                    smtp.login(settings["smtp_username"], settings["smtp_password"] or "")
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
                if int(settings["smtp_use_tls"] or 0):
                    smtp.starttls()
                if (settings["smtp_username"] or "").strip():
                    smtp.login(settings["smtp_username"], settings["smtp_password"] or "")
                smtp.send_message(msg)
    except Exception as exc:
        return jsonify({"error": "smtp_error", "message": str(exc)}), 502

    log_audit("security.password_reset_requested", f"Passwort-Reset angefordert für {username}")
    return jsonify({"ok": True})


@app.post("/api/auth/reset-password/<raw_token>")
def apply_password_reset(raw_token):
    payload = request.get_json(silent=True) or {}
    new_password = (payload.get("password") or "").strip()
    if len(new_password) < 8:
        return jsonify({"error": "password_too_short", "message": "Mindestens 8 Zeichen."}), 400

    token_hash = __import__("hashlib").sha256(raw_token.encode()).hexdigest()
    db = get_db()
    row = db.execute(
        "SELECT * FROM password_reset_tokens WHERE token_hash = ? AND used_at IS NULL",
        (token_hash,),
    ).fetchone()
    if not row:
        return jsonify({"error": "invalid_token"}), 400
    if row["expires_at"] < now_iso():
        return jsonify({"error": "token_expired"}), 400

    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), row["user_id"]))
    db.execute("UPDATE password_reset_tokens SET used_at = ? WHERE id = ?", (now_iso(), row["id"]))
    db.execute("DELETE FROM sessions WHERE user_id = ?", (row["user_id"],))
    db.commit()
    log_audit("security.password_reset_applied", "Passwort wurde über Reset-Link geändert", target_type="user", target_id=row["user_id"])
    return jsonify({"ok": True})


@app.post("/api/companies/<company_id>/repair")
@require_auth
@require_roles("superadmin", "company-admin")
def repair_company(company_id):
    user = g.current_user
    db = get_db()
    if user["role"] != "superadmin" and user.get("company_id") != company_id:
        return jsonify({"error": "forbidden"}), 403

    now = now_iso()
    workers = db.execute("SELECT id FROM workers WHERE company_id = ?", (company_id,)).fetchall()
    worker_ids = [w["id"] for w in workers]
    fixed = []

    expired_tokens = 0
    expired_sessions = 0
    for wid in worker_ids:
        r = db.execute("DELETE FROM worker_app_tokens WHERE worker_id = ? AND expires_at < ?", (wid, now))
        expired_tokens += r.rowcount
        r = db.execute("DELETE FROM worker_app_sessions WHERE worker_id = ? AND expires_at < ?", (wid, now))
        expired_sessions += r.rowcount

    if expired_tokens:
        fixed.append(f"{expired_tokens} abgelaufene App-Tokens entfernt")
    if expired_sessions:
        fixed.append(f"{expired_sessions} abgelaufene App-Sitzungen entfernt")

    no_badge = db.execute(
        "SELECT id FROM workers WHERE company_id = ? AND (badge_id IS NULL OR badge_id = '') AND deleted_at IS NULL",
        (company_id,)
    ).fetchall()
    for w in no_badge:
        db.execute("UPDATE workers SET badge_id = ? WHERE id = ?", (f"BP-{w['id'][-6:].upper()}", w["id"]))
    if no_badge:
        fixed.append(f"{len(no_badge)} fehlende Ausweisnummern ergaenzt")

    bad_status = db.execute(
        "SELECT id FROM workers WHERE company_id = ? AND status NOT IN ('aktiv','gesperrt','abgelaufen') AND deleted_at IS NULL",
        (company_id,)
    ).fetchall()
    for w in bad_status:
        db.execute("UPDATE workers SET status = 'aktiv' WHERE id = ?", (w["id"],))
    if bad_status:
        fixed.append(f"{len(bad_status)} ungueltige Mitarbeiter-Status korrigiert")

    if not fixed:
        fixed.append("Keine Probleme gefunden - System ist in Ordnung")

    db.commit()
    log_audit("company.repair", f"Firma-Diagnose: {'; '.join(fixed)}", actor=user, target_type="company", target_id=company_id)
    return jsonify({"ok": True, "fixed": fixed})


@app.post("/api/companies/<company_id>/restore")
@require_auth
@require_roles("superadmin")
def restore_company(company_id):
    db = get_db()
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "company_not_found"}), 404

    db.execute("UPDATE companies SET deleted_at = NULL, status = ? WHERE id = ?", ("aktiv", company_id))
    db.commit()
    log_audit("company.restored", f"Firma {company_id} wiederhergestellt", target_type="company", target_id=company_id, company_id=company_id, actor=g.current_user)
    return jsonify({"ok": True})


@app.get("/api/access-logs")
@require_auth
def list_access_logs():
    auto_close_open_entries_after_midnight(get_db())
    direction = (request.args.get("direction") or "").strip()
    gate = (request.args.get("gate") or "").strip()
    from_date = (request.args.get("from") or "").strip()
    to_date = (request.args.get("to") or "").strip()
    limit = min(max(int(request.args.get("limit", "1000")), 1), 5000)

    conditions, params = build_access_filters(g.current_user, direction, gate, from_date, to_date)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = get_db().execute(
        f"""
        SELECT access_logs.*
        FROM access_logs
        JOIN workers ON workers.id = access_logs.worker_id
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()

    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/access-logs/export.csv")
@require_auth
def export_access_csv():
    auto_close_open_entries_after_midnight(get_db())
    direction = (request.args.get("direction") or "").strip()
    gate = (request.args.get("gate") or "").strip()
    from_date = (request.args.get("from") or "").strip()
    to_date = (request.args.get("to") or "").strip()

    conditions, params = build_access_filters(g.current_user, direction, gate, from_date, to_date)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = get_db().execute(
        f"""
        SELECT access_logs.id, access_logs.direction, access_logs.gate, access_logs.note, access_logs.timestamp,
               workers.first_name, workers.last_name, workers.badge_id
        FROM access_logs
        JOIN workers ON workers.id = access_logs.worker_id
        {where_clause}
        ORDER BY access_logs.timestamp DESC
        LIMIT 5000
        """,
        params,
    ).fetchall()

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return jsonify({"error": "pdf_dependency_missing", "message": "Bitte reportlab installieren."}), 503

    buffer = io.BytesIO()
    pw, ph = landscape(A4)
    pdf = rl_canvas.Canvas(buffer, pagesize=landscape(A4))
    period_label = f" | Zeitraum: {from_date or '...'} – {to_date or '...'}".rstrip(" | Zeitraum: ... – ...") if (from_date or to_date) else ""
    col_x = [36, 180, 276, 342, 408, 532, 660]
    al_headers = ["Name", "Badge-ID", "Richtung", "Tor", "Zeitstempel (UTC)", "Notiz", ""]

    def draw_access_hdr(y):
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(36, y, f"BauPass - Zutrittsjournal{period_label}")
        y -= 14
        pdf.setFont("Helvetica", 8)
        pdf.drawString(36, y, f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')} | {len(rows)} Einträge")
        y -= 16
        pdf.setFont("Helvetica-Bold", 8)
        for i, h in enumerate(al_headers):
            pdf.drawString(col_x[i], y, h)
        y -= 8
        pdf.line(36, y, pw - 36, y)
        y -= 11
        return y

    y = ph - 36
    y = draw_access_hdr(y)
    pdf.setFont("Helvetica", 8)
    for row in rows:
        if y < 48:
            pdf.showPage()
            y = ph - 36
            y = draw_access_hdr(y)
            pdf.setFont("Helvetica", 8)
        full_name = f"{(row['last_name'] or '').strip()}, {(row['first_name'] or '').strip()}".strip(", ")
        pdf.drawString(col_x[0], y, full_name[:28])
        pdf.drawString(col_x[1], y, str(row["badge_id"] or "")[:18])
        dir_label = {"in": "Eintritt", "out": "Austritt"}.get(str(row["direction"] or ""), str(row["direction"] or "-"))
        pdf.drawString(col_x[2], y, dir_label[:12])
        pdf.drawString(col_x[3], y, str(row["gate"] or "-")[:16])
        pdf.drawString(col_x[4], y, str(row["timestamp"] or "")[:22])
        pdf.drawString(col_x[5], y, str(row["note"] or "")[:28])
        y -= 12
    if not rows:
        pdf.drawString(36, y, "Keine Einträge gefunden.")
    pdf.save()
    buffer.seek(0)
    filename = f"zutrittsjournal-{datetime.now().strftime('%Y-%m-%d')}.pdf"
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/access-logs/summary")
@require_auth
def access_summary():
    auto_close_expired_visitor_entries(get_db())
    auto_close_open_entries_after_midnight(get_db())
    direction = (request.args.get("direction") or "").strip()
    gate = (request.args.get("gate") or "").strip()
    from_date = (request.args.get("from") or "").strip()
    to_date = (request.args.get("to") or "").strip()

    conditions, params = build_access_filters(g.current_user, direction, gate, from_date, to_date)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = get_db().execute(
        f"""
        SELECT access_logs.worker_id, access_logs.direction, access_logs.gate, access_logs.timestamp,
               workers.first_name, workers.last_name, workers.badge_id
        FROM access_logs
        JOIN workers ON workers.id = access_logs.worker_id
        {where_clause}
        ORDER BY access_logs.timestamp ASC
        LIMIT 5000
        """,
        params,
    ).fetchall()

    hourly = [{"hour": f"{hour:02d}:00", "checkIn": 0, "checkOut": 0} for hour in range(24)]
    now_dt = datetime.now(timezone.utc)

    for row in rows:
        ts = parse_iso_utc(row["timestamp"])
        if ts:
            hour = ts.hour
            if row["direction"] == "check-in":
                hourly[hour]["checkIn"] += 1
            elif row["direction"] == "check-out":
                hourly[hour]["checkOut"] += 1

    open_entries = build_open_entries_from_rows(rows, now_dt)

    return jsonify(
        {
            "hourly": hourly,
            "openEntries": open_entries[:150],
        }
    )


@app.get("/api/reporting/summary")
@require_auth
@require_roles("superadmin", "company-admin")
def reporting_summary():
    db = get_db()
    user = g.current_user
    is_superadmin = user["role"] == "superadmin"
    company_id = user.get("company_id")

    invoice_scope_sql = ""
    invoice_scope_params = []
    company_scope_sql = ""
    company_scope_params = []
    access_scope_sql = ""
    access_scope_params = []
    audit_scope_sql = ""
    audit_scope_params = []

    if not is_superadmin:
        invoice_scope_sql = " AND invoices.company_id = ?"
        invoice_scope_params = [company_id]
        company_scope_sql = " AND id = ?"
        company_scope_params = [company_id]
        access_scope_sql = " AND workers.company_id = ?"
        access_scope_params = [company_id]
        audit_scope_sql = " AND (company_id = ? OR company_id IS NULL)"
        audit_scope_params = [company_id]

    paid_total_row = db.execute(
        f"""
        SELECT COALESCE(SUM(invoices.total_amount), 0) AS value
        FROM invoices
        WHERE (invoices.status = 'bezahlt' OR invoices.paid_at IS NOT NULL)
        {invoice_scope_sql}
        """,
        invoice_scope_params,
    ).fetchone()

    open_total_row = db.execute(
        f"""
        SELECT COALESCE(SUM(invoices.total_amount), 0) AS value
        FROM invoices
        WHERE invoices.paid_at IS NULL
          AND invoices.status IN ('draft', 'sent', 'overdue', 'send_failed')
        {invoice_scope_sql}
        """,
        invoice_scope_params,
    ).fetchone()

    overdue_row = db.execute(
        f"""
        SELECT COUNT(*) AS invoice_count, COALESCE(SUM(invoices.total_amount), 0) AS total_value
        FROM invoices
        WHERE invoices.paid_at IS NULL
          AND invoices.due_date IS NOT NULL
          AND DATE(invoices.due_date) < DATE('now')
        {invoice_scope_sql}
        """,
        invoice_scope_params,
    ).fetchone()

    locked_companies_row = db.execute(
        f"""
        SELECT COUNT(*) AS value
        FROM companies
        WHERE deleted_at IS NULL
          AND status = 'gesperrt'
        {company_scope_sql}
        """,
        company_scope_params,
    ).fetchone()

    suspensions_row = db.execute(
        f"""
        SELECT COUNT(*) AS value
        FROM audit_logs
        WHERE event_type = 'company.auto_suspended_overdue_invoice'
          AND DATE(created_at) >= DATE('now', '-30 day')
        {audit_scope_sql}
        """,
        audit_scope_params,
    ).fetchone()

    access_rows = db.execute(
        f"""
        SELECT DATE(access_logs.timestamp) AS day,
               SUM(CASE WHEN access_logs.direction = 'check-in' THEN 1 ELSE 0 END) AS check_in,
               SUM(CASE WHEN access_logs.direction = 'check-out' THEN 1 ELSE 0 END) AS check_out
        FROM access_logs
        JOIN workers ON workers.id = access_logs.worker_id
        WHERE DATE(access_logs.timestamp) >= DATE('now', '-6 day')
        {access_scope_sql}
        GROUP BY DATE(access_logs.timestamp)
        ORDER BY day ASC
        """,
        access_scope_params,
    ).fetchall()

    access_map = {row["day"]: row for row in access_rows}
    access_daily = []
    for day_offset in range(6, -1, -1):
        day = (datetime.now(timezone.utc).date() - timedelta(days=day_offset)).isoformat()
        source = access_map.get(day)
        access_daily.append(
            {
                "day": day,
                "checkIn": int(source["check_in"] or 0) if source else 0,
                "checkOut": int(source["check_out"] or 0) if source else 0,
            }
        )

    top_overdue_companies = []
    if is_superadmin:
        top_rows = db.execute(
            """
            SELECT companies.id, companies.name,
                   COUNT(invoices.id) AS overdue_count,
                   COALESCE(SUM(invoices.total_amount), 0) AS overdue_total
            FROM invoices
            JOIN companies ON companies.id = invoices.company_id
            WHERE invoices.paid_at IS NULL
              AND invoices.due_date IS NOT NULL
              AND DATE(invoices.due_date) < DATE('now')
              AND companies.deleted_at IS NULL
            GROUP BY companies.id, companies.name
            ORDER BY overdue_total DESC
            LIMIT 5
            """
        ).fetchall()
        top_overdue_companies = [
            {
                "companyId": row["id"],
                "companyName": row["name"],
                "overdueCount": int(row["overdue_count"] or 0),
                "overdueTotal": float(row["overdue_total"] or 0),
            }
            for row in top_rows
        ]

    return jsonify(
        {
            "kpis": {
                "paidTotal": float(paid_total_row["value"] or 0),
                "openTotal": float(open_total_row["value"] or 0),
                "overdueInvoiceCount": int(overdue_row["invoice_count"] or 0),
                "overdueTotal": float(overdue_row["total_value"] or 0),
                "lockedCompanies": int(locked_companies_row["value"] or 0),
                "suspensionsLast30d": int(suspensions_row["value"] or 0),
            },
            "accessDaily": access_daily,
            "topOverdueCompanies": top_overdue_companies,
            "generatedAt": now_iso(),
        }
    )


@app.get("/api/access-logs/day-close-check")
@require_auth
def access_day_close_check():
    auto_close_expired_visitor_entries(get_db())
    auto_closed = auto_close_open_entries_after_midnight(get_db())
    date_value = (request.args.get("date") or "").strip()
    if not date_value:
        date_value = datetime.now().date().isoformat()

    conditions, params = build_access_filters(g.current_user, "", "", date_value, date_value)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = get_db().execute(
        f"""
        SELECT access_logs.worker_id, access_logs.direction, access_logs.gate, access_logs.timestamp,
               workers.first_name, workers.last_name, workers.badge_id
        FROM access_logs
        JOIN workers ON workers.id = access_logs.worker_id
        {where_clause}
        ORDER BY access_logs.timestamp ASC
        LIMIT 5000
        """,
        params,
    ).fetchall()

    now_dt = datetime.now(timezone.utc)
    open_entries = build_open_entries_from_rows(rows, now_dt)

    db = get_db()
    ack_scope_condition = "company_id IS NULL"
    ack_params = [date_value]
    if g.current_user["role"] != "superadmin":
        ack_scope_condition = "company_id = ?"
        ack_params.append(g.current_user.get("company_id"))

    try:
        acknowledgement = db.execute(
            f"""
            SELECT day_close_acknowledgements.*, users.name AS acknowledged_by_name
            FROM day_close_acknowledgements
            JOIN users ON users.id = day_close_acknowledgements.acknowledged_by_user_id
            WHERE day_close_acknowledgements.date = ? AND {ack_scope_condition}
            ORDER BY day_close_acknowledgements.created_at DESC
            LIMIT 1
            """,
            ack_params,
        ).fetchone()
    except sqlite3.OperationalError:
        acknowledgement = None

    acknowledgement_payload = None
    if acknowledgement:
        acknowledgement_payload = {
            "id": acknowledgement["id"],
            "date": acknowledgement["date"],
            "comment": acknowledgement["comment"],
            "openCount": acknowledgement["open_count"],
            "createdAt": acknowledgement["created_at"],
            "acknowledgedBy": acknowledgement["acknowledged_by_name"],
        }

    return jsonify(
        {
            "date": date_value,
            "due": datetime.now().hour >= 18,
            "openCount": len(open_entries),
            "openEntries": open_entries[:150],
            "autoClosedCount": len(auto_closed),
            "autoClosedEntries": auto_closed[:50],
            "acknowledgement": acknowledgement_payload,
        }
    )


@app.post("/api/access-logs/day-close-ack")
@require_auth
@require_roles("superadmin", "company-admin")
def acknowledge_day_close():
    payload = request.get_json(silent=True) or {}
    date_value = (payload.get("date") or "").strip() or datetime.now().date().isoformat()
    comment = (payload.get("comment") or "").strip()

    if len(comment) < 4:
        return jsonify({"error": "comment_too_short"}), 400

    conditions, params = build_access_filters(g.current_user, "", "", date_value, date_value)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = get_db().execute(
        f"""
        SELECT access_logs.worker_id, access_logs.direction, access_logs.gate, access_logs.timestamp,
               workers.first_name, workers.last_name, workers.badge_id
        FROM access_logs
        JOIN workers ON workers.id = access_logs.worker_id
        {where_clause}
        ORDER BY access_logs.timestamp ASC
        LIMIT 5000
        """,
        params,
    ).fetchall()

    open_entries = build_open_entries_from_rows(rows, datetime.now(timezone.utc))
    company_id = None if g.current_user["role"] == "superadmin" else g.current_user.get("company_id")
    ack_id = f"ack-{secrets.token_hex(6)}"

    db = get_db()
    db.execute(
        """
        INSERT INTO day_close_acknowledgements (id, date, company_id, acknowledged_by_user_id, comment, open_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ack_id,
            date_value,
            company_id,
            g.current_user["id"],
            comment,
            len(open_entries),
            now_iso(),
        ),
    )
    db.commit()

    log_audit(
        "access.day_close_acknowledged",
        f"Tagesabschluss für {date_value} quittiert: {comment}",
        target_type="access",
        target_id=date_value,
        company_id=company_id,
        actor=g.current_user,
    )

    return jsonify({"ok": True, "id": ack_id, "openCount": len(open_entries), "date": date_value})


@app.post("/api/access-logs")
@require_auth
def create_access_log():
    auto_close_expired_visitor_entries(get_db())
    auto_close_open_entries_after_midnight(get_db())
    payload = request.get_json(silent=True) or {}
    worker_id = payload.get("workerId")
    user = g.current_user

    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404

    if worker["deleted_at"]:
        return jsonify({"error": "worker_deleted"}), 400

    if user["role"] != "superadmin" and worker["company_id"] != user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    if lock_worker_for_expired_documents(db, worker):
        db.commit()
        return jsonify({
            "error": "worker_documents_expired",
            "message": "Mitarbeiter wurde wegen abgelaufener Pflichtdokumente automatisch gesperrt.",
        }), 400

    company_error = get_company_access_error(db, worker["company_id"])
    if company_error:
        return jsonify(company_error), 403

    if worker_visit_has_expired(worker):
        return jsonify({"error": "visitor_visit_expired", "message": "Diese Besucherkarte ist zeitlich abgelaufen."}), 400

    if worker["status"] != "aktiv":
        return jsonify({"error": "worker_not_active"}), 400

    log_id = create_access_log_entry(
        db,
        worker_id,
        payload.get("direction", "check-in"),
        payload.get("gate", "Drehkreuz Nord"),
        payload.get("note", ""),
        payload.get("timestamp", now_iso()),
    )
    db.commit()
    log_audit("access.booked", f"Zutritt {payload.get('direction', 'check-in')} fuer Worker {worker_id}", target_type="worker", target_id=worker_id, company_id=worker["company_id"], actor=g.current_user)
    row = db.execute("SELECT * FROM access_logs WHERE id = ?", (log_id,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.post("/api/gates/tap")
def gate_tap():
    auto_close_expired_visitor_entries(get_db())
    auto_close_open_entries_after_midnight(get_db())
    provided_key = (request.headers.get("X-Gate-Key") or "").strip()
    if not provided_key:
        return jsonify({"error": "gate_unauthorized"}), 401

    db = get_db()
    turnstile_user = find_turnstile_by_api_key(db, provided_key)
    if not turnstile_user:
        return jsonify({"error": "gate_unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    physical_card_id = normalize_physical_card_id(payload.get("physicalCardId") or payload.get("cardId"))
    if not physical_card_id:
        return jsonify({"error": "missing_physical_card_id"}), 400

    requested_direction = (payload.get("direction") or "").strip().lower()
    direction = requested_direction
    if requested_direction and requested_direction not in {"check-in", "check-out", "auto", "toggle"}:
        return jsonify({"error": "invalid_direction"}), 400

    gate_name = (payload.get("gate") or "NFC Gate").strip() or "NFC Gate"
    gate_note = (payload.get("note") or "NFC Tap").strip()
    timestamp_value = (payload.get("timestamp") or now_iso()).strip() or now_iso()

    workers = db.execute(
        """
        SELECT *
        FROM workers
        WHERE physical_card_id = ? AND deleted_at IS NULL
        ORDER BY id
        LIMIT 2
        """,
        (physical_card_id,),
    ).fetchall()
    if not workers:
        return jsonify({"error": "card_not_assigned"}), 404
    if len(workers) > 1:
        return jsonify({"error": "duplicate_physical_card_id"}), 409

    worker = workers[0]

    if turnstile_user["company_id"] != worker["company_id"]:
        return jsonify({"error": "forbidden_worker_company"}), 403

    if lock_worker_for_expired_documents(db, worker):
        db.commit()
        return jsonify({
            "error": "worker_documents_expired",
            "message": "Mitarbeiter wurde wegen abgelaufener Pflichtdokumente automatisch gesperrt.",
        }), 403

    if requested_direction in {"", "auto", "toggle"}:
        latest_log = db.execute(
            """
            SELECT direction
            FROM access_logs
            WHERE worker_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (worker["id"],),
        ).fetchone()
        direction = "check-out" if latest_log and str(latest_log["direction"] or "").lower() == "check-in" else "check-in"
    elif requested_direction in {"check-in", "check-out"}:
        direction = requested_direction

    company_error = get_company_access_error(db, worker["company_id"])
    if company_error:
        return jsonify(company_error), 403
    company_access_error = get_company_access_error(db, turnstile_user["company_id"])
    if company_access_error:
        return jsonify(company_access_error), 403
    if worker_visit_has_expired(worker):
        return jsonify({"error": "visitor_visit_expired", "message": "Diese Besucherkarte ist zeitlich abgelaufen."}), 403
    if worker["status"] != "aktiv":
        return jsonify({"error": "worker_not_active"}), 403

    log_id = create_access_log_entry(db, worker["id"], direction, gate_name, gate_note, timestamp_value)
    db.commit()
    log_audit(
        "access.gate_tap",
        f"NFC Tap {direction} fuer Worker {worker['id']} an {gate_name}",
        target_type="worker",
        target_id=worker["id"],
        company_id=worker["company_id"],
        actor=row_to_dict(turnstile_user),
    )

    feedback_message = "Du bist jetzt angemeldet." if direction == "check-in" else "Du bist jetzt abgemeldet."
    feedback_title = "ANMELDUNG ERFOLGREICH" if direction == "check-in" else "ABMELDUNG ERFOLGREICH"
    feedback_tone = "success_in" if direction == "check-in" else "success_out"

    return jsonify(
        {
            "ok": True,
            "logId": log_id,
            "worker": {
                "id": worker["id"],
                "firstName": worker["first_name"],
                "lastName": worker["last_name"],
                "badgeId": worker["badge_id"],
                "status": worker["status"],
            },
            "direction": direction,
            "gate": gate_name,
            "timestamp": timestamp_value,
            "feedbackTitle": feedback_title,
            "feedbackMessage": feedback_message,
            "feedbackTone": feedback_tone,
        }
    ), 201


def send_invoice_email(invoice_row, company_row, settings_row):
    smtp_host = (settings_row["smtp_host"] or "").strip()
    smtp_sender = (settings_row["smtp_sender_email"] or "").strip()
    if not smtp_sender:
        smtp_sender = _normalize_env_value(_resend_key_cache.get("brevo_from_email") or "")
    if not smtp_sender:
        smtp_sender = _normalize_env_value(_resend_key_cache.get("from_email") or "")

    attachment_payload = []
    safe_invoice_no = re.sub(r"[^A-Za-z0-9._-]+", "-", str(invoice_row["invoice_number"] or "rechnung")).strip("-") or "rechnung"
    pdf_filename = f"rechnung-von-baupass-{safe_invoice_no}.pdf"
    platform_label = str(settings_row["platform_name"] or "BauPass").strip() or "BauPass"
    operator_label = str(settings_row["operator_name"] or platform_label).strip() or platform_label
    mail_subject = f"Rechnung von {platform_label} - {invoice_row['invoice_number']}"
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.lib import colors as rl_colors
        from reportlab.pdfgen import canvas as rl_canvas

        pdf_buffer = io.BytesIO()
        pdf = rl_canvas.Canvas(pdf_buffer, pagesize=A4)
        page_w, page_h = A4
        M_L = 25 * mm   # DIN 5008 linker Rand
        M_R = 20 * mm
        M_B = 18 * mm   # Bodenrand über Footer
        CW  = page_w - M_L - M_R  # nutzbare Breite

        brand_primary = sanitize_hex_color(settings_row["invoice_primary_color"], fallback="#0f4c5c")
        brand_accent  = sanitize_hex_color(settings_row["invoice_accent_color"],  fallback=brand_primary)

        invoice_no   = str(invoice_row["invoice_number"]  or "-")
        invoice_date = str(invoice_row["invoice_date"]     or "-")
        due_date     = str(invoice_row["due_date"]         or "-")
        period       = str(invoice_row["invoice_period"]   or "-")
        company_name = str(company_row["name"]             or "-")
        description  = str(invoice_row["description"]      or "-")
        net_amount   = float(invoice_row["net_amount"]     or 0)
        vat_rate     = float(invoice_row["vat_rate"]       or 0)
        vat_amount   = float(invoice_row["vat_amount"]     or 0)
        total_amount = float(invoice_row["total_amount"]   or 0)
        discount_amount = float(invoice_row["discount_amount"] if "discount_amount" in invoice_row.keys() else 0)

        try:
            items_json_raw = str(invoice_row["items_json"] if "items_json" in invoice_row.keys() else "") or ""
            pdf_items = json.loads(items_json_raw) if items_json_raw.strip().startswith("[") else []
        except Exception:
            pdf_items = []
        if not pdf_items:
            pdf_items = [{"description": description, "qty": 1, "unit": "Pauschal", "unitPrice": net_amount, "total": net_amount}]

        def _sr(key, fallback=""):
            try:
                return str(settings_row[key] or "").strip()
            except (IndexError, KeyError):
                return fallback

        op_iban     = _sr("invoice_iban")
        op_bic      = _sr("invoice_bic")
        op_bank     = _sr("invoice_bank_name")
        op_tax_id   = _sr("invoice_tax_id")
        op_vat_id   = _sr("invoice_vat_id")
        op_street   = _sr("invoice_operator_street")
        op_zip_city = _sr("invoice_operator_zip_city")
        op_phone    = _sr("invoice_operator_phone")
        op_website  = _sr("invoice_operator_website")
        op_email    = _sr("invoice_operator_email")

        def _money(v):
            return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

        c_primary   = rl_colors.HexColor(brand_primary)
        c_accent    = rl_colors.HexColor(brand_accent)
        c_dark      = rl_colors.HexColor("#1a2633")
        c_mid       = rl_colors.HexColor("#4a5568")
        c_light     = rl_colors.HexColor("#718096")
        c_rule      = rl_colors.HexColor("#d1d9e0")
        c_bg_box    = rl_colors.HexColor("#f4f7fa")
        c_stripe    = rl_colors.HexColor("#edf2f7")

        # ── Logo-Hilfsfunktionen ─────────────────────────────────────
        def _build_baukometra_wordmark_png():
            try:
                from PIL import Image, ImageDraw, ImageFont
            except Exception:
                return None
            w, h = 960, 240
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([0, 20, 210, 220], radius=32, fill=(15, 76, 92, 255))
            font_b = font_s = None
            for fn in ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
                try:
                    font_b = ImageFont.truetype(fn, 108)
                    font_s = ImageFont.truetype(fn, 58)
                    break
                except Exception:
                    continue
            font_b = font_b or ImageFont.load_default()
            font_s = font_s or ImageFont.load_default()
            d.text((52, 72), "BK",         fill=(255,255,255,255), font=font_s)
            d.text((248, 44), "BauKometra", fill=(255,255,255,255), font=font_b)
            d.line([(250, 180), (750, 180)], fill=(227, 100, 20, 255), width=10)
            buf = io.BytesIO(); img.save(buf, "PNG"); return buf.getvalue()

        def _decode_data_url(raw):
            v = str(raw or "").strip()
            if not v.startswith("data:image") or "," not in v:
                return "", b""
            hdr, payload = v.split(",", 1)
            mime = hdr[5:].split(";", 1)[0].strip().lower()
            try:
                return mime, base64.b64decode(payload) if ";base64" in hdr.lower() else unquote_to_bytes(payload)
            except Exception:
                return "", b""

        def _svg_to_png(svg_bytes):
            try:
                from svglib.svglib import svg2rlg
                from reportlab.graphics import renderPM
                drw = svg2rlg(io.BytesIO(svg_bytes))
                if not drw: return b""
                pil = renderPM.drawToPIL(drw, dpi=220)
                buf = io.BytesIO(); pil.save(buf, "PNG"); return buf.getvalue()
            except Exception:
                return b""

        def _logo_bytes():
            data_url = str(settings_row["invoice_logo_data"] or "").strip()
            if not data_url:
                fbf = BASE_DIR / "branding" / "baukometra-logo.svg"
                if fbf.exists():
                    try:
                        data_url = f"data:image/svg+xml;charset=utf-8,{quote(fbf.read_text(encoding='utf-8'))}"
                    except Exception:
                        data_url = ""
            mime, raw = _decode_data_url(data_url)
            if mime == "image/svg+xml":
                png = _svg_to_png(raw)
                if png: return png
            elif raw:
                return raw
            return _build_baukometra_wordmark_png() or b""

        def _draw_logo_text_fallback(x, y):
            # Draw a built-in fallback mark so a logo is always visible even without PIL/svglib.
            tile_h = 11 * mm
            tile_w = 11 * mm
            pdf.setFillColor(rl_colors.white)
            pdf.roundRect(x, y, tile_w, tile_h, 1.8 * mm, stroke=0, fill=1)
            pdf.setFillColor(c_primary)
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawString(x + 2.3 * mm, y + 3.6 * mm, "BK")
            pdf.setFillColor(rl_colors.white)
            pdf.setFont("Helvetica-Bold", 13)
            pdf.drawString(x + tile_w + 2.5 * mm, y + 4.2 * mm, "BauKometra")

        # ════════════════════════════════════════════════════════════
        # 1  HEADER-BAND (Höhe 30 mm)
        # ════════════════════════════════════════════════════════════
        HDR_H = 30 * mm
        pdf.setFillColor(c_primary)
        pdf.rect(0, page_h - HDR_H, page_w, HDR_H, stroke=0, fill=1)

        # ── Logo links im Header ──────────────────────────────────
        logo_drawn = False
        try:
            lb = _logo_bytes()
            if lb:
                ir = ImageReader(io.BytesIO(lb))
                pdf.drawImage(ir, M_L, page_h - HDR_H + 5 * mm,
                              width=50 * mm, height=20 * mm,
                              preserveAspectRatio=True, mask="auto")
                logo_drawn = True
        except Exception:
            pass
        if not logo_drawn:
            _draw_logo_text_fallback(M_L, page_h - HDR_H + 10 * mm)

        # ── RECHNUNG + Plattformname rechts ──────────────────────
        pdf.setFillColor(rl_colors.white)
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawRightString(page_w - M_R, page_h - HDR_H + 14 * mm, "RECHNUNG")
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(rl_colors.HexColor("#a8c4d4"))
        pdf.drawRightString(page_w - M_R, page_h - HDR_H + 7 * mm, platform_label)

        # Status-Badge (OFFEN / ÜBERFÄLLIG / BEZAHLT) – rechts unter "RECHNUNG"
        _inv_status = str(invoice_row["status"] if "status" in invoice_row.keys() else "").lower()
        if _inv_status == "bezahlt":
            _badge_bg, _badge_txt = rl_colors.HexColor("#16a34a"), "BEZAHLT"
        elif _inv_status in ("overdue", "überfällig"):
            _badge_bg, _badge_txt = rl_colors.HexColor("#dc2626"), "ÜBERFÄLLIG"
        else:
            _badge_bg, _badge_txt = rl_colors.HexColor("#d97706"), "OFFEN"
        _BDG_W, _BDG_H = 24 * mm, 6.5 * mm
        _BDG_X = page_w - M_R - _BDG_W
        _BDG_Y = page_h - HDR_H + 0.5 * mm
        pdf.setFillColor(_badge_bg)
        pdf.roundRect(_BDG_X, _BDG_Y, _BDG_W, _BDG_H, 1.5, stroke=0, fill=1)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.setFillColor(rl_colors.white)
        pdf.drawCentredString(_BDG_X + _BDG_W / 2, _BDG_Y + 1.8 * mm, _badge_txt)

        # ════════════════════════════════════════════════════════════
        # 2  ABSENDER + RECHNUNGSDATEN-BOX  (unterhalb Header)
        # ════════════════════════════════════════════════════════════
        # Absender links oben, Metabox rechts oben – beide starten 4 mm unterhalb Header
        SECTION_TOP = page_h - HDR_H - 4 * mm

        # --- Absenderzeile (kleine Rücksendeadresse für DIN-5008-Fenster)
        ret_addr_parts = [operator_label]
        if op_street:   ret_addr_parts.append(op_street)
        if op_zip_city: ret_addr_parts.append(op_zip_city)
        pdf.setFont("Helvetica", 7)
        pdf.setFillColor(c_light)
        pdf.drawString(M_L, SECTION_TOP, "  \u25AA  ".join(ret_addr_parts))

        # --- Metabox rechts (Rechnungsdaten)
        META_W = 72 * mm
        META_X = page_w - M_R - META_W
        META_Y = SECTION_TOP
        meta_rows = [
            ("Rechnungsnr.",      invoice_no),
            ("Datum",             invoice_date),
            ("Zahlbar bis",       due_date),
            ("Leistungszeitraum", period),
        ]
        META_H = len(meta_rows) * 7 * mm + 10 * mm
        pdf.setFillColor(c_bg_box)
        pdf.setStrokeColor(c_rule)
        pdf.setLineWidth(0.4)
        pdf.roundRect(META_X, META_Y - META_H, META_W, META_H, 3, stroke=1, fill=1)

        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColor(c_light)
        pdf.drawString(META_X + 4 * mm, META_Y - 6 * mm, "RECHNUNGSDATEN")

        for i, (lbl, val) in enumerate(meta_rows):
            ry = META_Y - 13 * mm - i * 7 * mm
            pdf.setFont("Helvetica", 8)
            pdf.setFillColor(c_mid)
            pdf.drawString(META_X + 4 * mm, ry, lbl)
            pdf.setFont("Helvetica-Bold", 8)
            pdf.setFillColor(c_dark)
            pdf.drawRightString(META_X + META_W - 4 * mm, ry, val)

        # ════════════════════════════════════════════════════════════
        # 3  EMPFÄNGERADRESSE (DIN 5008-Fenster: 45 mm unterhalb Kopfbereich)
        # ════════════════════════════════════════════════════════════
        ADDR_TOP = SECTION_TOP - 8 * mm  # kleiner Abstand nach Absender
        ADDR_H   = 38 * mm
        ADDR_W   = META_X - M_L - 8 * mm  # bis zur Metabox

        pdf.setStrokeColor(c_rule)
        pdf.setLineWidth(0.3)
        pdf.line(M_L, ADDR_TOP, M_L + ADDR_W, ADDR_TOP)  # obere Fensterlinie

        pdf.setFont("Helvetica-Bold", 11)
        pdf.setFillColor(c_dark)
        pdf.drawString(M_L, ADDR_TOP - 10 * mm, company_name[:50])
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(c_mid)
        _company_contact = str(company_row["contact"] or "").strip() if company_row else ""
        _company_billing_email = str(company_row["billing_email"] or "").strip() if company_row else ""
        if _company_contact:
            pdf.drawString(M_L, ADDR_TOP - 17 * mm, _company_contact[:60])
        if _company_billing_email:
            pdf.setFont("Helvetica", 8)
            pdf.setFillColor(c_light)
            pdf.drawString(M_L, ADDR_TOP - 22 * mm, _company_billing_email[:60])
        if not _company_contact:
            pdf.drawString(M_L, ADDR_TOP - 17 * mm, "z. Hd. Buchhaltung")

        # ════════════════════════════════════════════════════════════
        # 4  BETREFFZEILE
        # ════════════════════════════════════════════════════════════
        SUBJ_Y = ADDR_TOP - ADDR_H - 8 * mm

        pdf.setFont("Helvetica-Bold", 13)
        pdf.setFillColor(c_dark)
        pdf.drawString(M_L, SUBJ_Y, f"Rechnung Nr. {invoice_no}")

        pdf.setStrokeColor(c_accent)
        pdf.setLineWidth(2)
        pdf.line(M_L, SUBJ_Y - 2.5 * mm, M_L + CW, SUBJ_Y - 2.5 * mm)
        pdf.setLineWidth(0.5)

        # Intro-Satz
        INTRO_Y = SUBJ_Y - 10 * mm
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(c_mid)
        pdf.drawString(M_L, INTRO_Y, f"Sehr geehrte Damen und Herren, hiermit stellen wir Ihnen für den Zeitraum {period} folgende Leistungen in Rechnung:")

        # ════════════════════════════════════════════════════════════
        # 5  POSITIONSTABELLE
        # ════════════════════════════════════════════════════════════
        TBL_TOP = INTRO_Y - 7 * mm

        C_POS  = 9  * mm
        C_TOT  = 30 * mm
        C_NET  = 28 * mm
        C_UNIT = 14 * mm
        C_QTY  = 16 * mm
        C_DESC = CW - C_POS - C_QTY - C_UNIT - C_NET - C_TOT

        # x-Positionen der Spaltenstarts
        cx = [M_L]
        for w in [C_POS, C_DESC, C_QTY, C_UNIT, C_NET]:
            cx.append(cx[-1] + w)

        HDR_ROW_H = 7 * mm
        DATA_ROW_H = 11 * mm

        # Tabellenkopf
        pdf.setFillColor(c_primary)
        pdf.rect(M_L, TBL_TOP - HDR_ROW_H, CW, HDR_ROW_H, stroke=0, fill=1)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColor(rl_colors.white)
        hdr_defs = [
            (0, "Pos",          "L", C_POS),
            (1, "Beschreibung", "L", C_DESC),
            (2, "Menge",        "R", C_QTY),
            (3, "Einheit",      "C", C_UNIT),
            (4, "Einzelpreis",  "R", C_NET),
            (5, "Gesamtbetrag", "R", C_TOT),
        ]
        hy = TBL_TOP - HDR_ROW_H + 2.5 * mm
        for ci, hdr, align, cw in hdr_defs:
            hx = cx[ci]
            if align == "R":
                pdf.drawRightString(hx + cw - 2 * mm, hy, hdr)
            elif align == "C":
                pdf.drawCentredString(hx + cw / 2, hy, hdr)
            else:
                pdf.drawString(hx + 2 * mm, hy, hdr)

        # Tabellenzeilen
        row_y = TBL_TOP - HDR_ROW_H
        INFO_SECTION_H = 52 * mm   # reservierter Block von unten (über Footer)
        FOOTER_H = 14 * mm
        table_stop_y = FOOTER_H + INFO_SECTION_H + 40 * mm
        visible_rows = 0
        hidden_rows = 0
        for idx, item in enumerate(pdf_items):
            if row_y - DATA_ROW_H < table_stop_y:
                hidden_rows = len(pdf_items) - idx
                break
            row_y -= DATA_ROW_H
            visible_rows += 1
            pdf.setFillColor(rl_colors.white if idx % 2 == 0 else c_stripe)
            pdf.rect(M_L, row_y, CW, DATA_ROW_H, stroke=0, fill=1)
            pdf.setStrokeColor(c_rule)
            pdf.setLineWidth(0.3)
            pdf.line(M_L, row_y, M_L + CW, row_y)

            i_desc  = str(item.get("description") or "-")
            i_qty   = float(item.get("qty") or 1)
            i_unit  = str(item.get("unit") or "Pauschal")
            i_price = float(item.get("unitPrice") or 0)
            i_total = float(item.get("total") or 0)
            qty_str = f"{i_qty:g}" if i_qty != int(i_qty) else str(int(i_qty))
            text_y  = row_y + DATA_ROW_H / 2 - 1.5 * mm

            pdf.setFont("Helvetica", 8)
            pdf.setFillColor(c_mid)
            pdf.drawString(cx[0] + 2 * mm, text_y, str(idx + 1))

            # Beschreibung – mehrzeilig umbrechen wenn nötig
            try:
                from reportlab.lib.utils import simpleSplit as _simpleSplit
                _desc_lines = _simpleSplit(i_desc, "Helvetica", 8, C_DESC - 4 * mm)[:2]
            except Exception:
                _desc_lines = [i_desc[:55]]
            pdf.setFont("Helvetica", 8)
            pdf.setFillColor(c_dark)
            if len(_desc_lines) > 1:
                pdf.drawString(cx[1] + 2 * mm, row_y + DATA_ROW_H / 2 + 1 * mm, _desc_lines[0])
                pdf.setFont("Helvetica", 7.5)
                pdf.setFillColor(c_mid)
                pdf.drawString(cx[1] + 2 * mm, row_y + DATA_ROW_H / 2 - 3.5 * mm, _desc_lines[1])
                pdf.setFont("Helvetica", 8)
                pdf.setFillColor(c_dark)
            else:
                pdf.drawString(cx[1] + 2 * mm, text_y, _desc_lines[0] if _desc_lines else i_desc[:55])

            pdf.drawRightString(cx[2] + C_QTY  - 2 * mm, text_y, qty_str)
            pdf.drawCentredString(cx[3] + C_UNIT / 2,    text_y, i_unit[:10])
            pdf.drawRightString(cx[4] + C_NET  - 2 * mm, text_y, _money(i_price))
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawRightString(cx[5] + C_TOT  - 2 * mm, text_y, _money(i_total))

        if hidden_rows > 0:
            row_y -= 6 * mm
            pdf.setFont("Helvetica-Oblique", 7.5)
            pdf.setFillColor(c_mid)
            pdf.drawString(M_L, row_y, f"Weitere Positionen im System: {hidden_rows} (aus Platzgruenden nicht angezeigt)")

        TABLE_BOTTOM = row_y  # unterkante letzte Zeile

        # ════════════════════════════════════════════════════════════
        # 6  SUMMENBLOCK  (rechts, direkt unter Tabelle)
        # ════════════════════════════════════════════════════════════
        TOT_W = 72 * mm
        TOT_X = page_w - M_R - TOT_W
        TOT_GAP = 4 * mm   # Abstand Tabelle → Summenblock

        # Zeilenanzahl berechnen
        tot_rows = [("Nettobetrag", _money(net_amount))]
        if discount_amount > 0:
            tot_rows.append(("Abzgl. Rabatt", f"– {_money(discount_amount)}"))
        tot_rows.append((f"MwSt. {vat_rate:.0f} %", _money(vat_amount)))
        TOT_INNER_H = len(tot_rows) * 7 * mm + 11 * mm  # Zeilen + Gesamtzeile
        TOT_TOP = TABLE_BOTTOM - TOT_GAP

        pdf.setFillColor(c_bg_box)
        pdf.setStrokeColor(c_rule)
        pdf.setLineWidth(0.4)
        pdf.roundRect(TOT_X, TOT_TOP - TOT_INNER_H, TOT_W, TOT_INNER_H, 3, stroke=1, fill=1)

        tr_y = TOT_TOP - 7 * mm
        for lbl, val in tot_rows:
            pdf.setFont("Helvetica", 8.5)
            pdf.setFillColor(c_mid)
            pdf.drawString(TOT_X + 4 * mm, tr_y, lbl)
            pdf.setFillColor(c_dark)
            pdf.drawRightString(TOT_X + TOT_W - 4 * mm, tr_y, val)
            tr_y -= 7 * mm

        pdf.setStrokeColor(c_primary)
        pdf.setLineWidth(0.8)
        pdf.line(TOT_X + 3 * mm, tr_y + 4 * mm, TOT_X + TOT_W - 3 * mm, tr_y + 4 * mm)
        pdf.setLineWidth(0.5)

        # Gesamtbetrag-Balken
        pdf.setFillColor(c_primary)
        pdf.roundRect(TOT_X, TOT_TOP - TOT_INNER_H, TOT_W, 10 * mm, 3, stroke=0, fill=1)
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.setFillColor(rl_colors.white)
        band_center = TOT_TOP - TOT_INNER_H + 5 * mm - 1.5 * mm
        pdf.drawString(TOT_X + 4 * mm, band_center, "Gesamtbetrag")
        pdf.drawRightString(TOT_X + TOT_W - 4 * mm, band_center, _money(total_amount))

        BLOCK_BOTTOM = TOT_TOP - TOT_INNER_H  # unterste Y-Koordinate des Summenblocks

        # ════════════════════════════════════════════════════════════
        # 8  FOOTER-BAND  (immer am Seitenende, zuerst zeichnen)
        # ════════════════════════════════════════════════════════════
        pdf.setFillColor(c_primary)
        pdf.rect(0, 0, page_w, FOOTER_H, stroke=0, fill=1)
        fp = [operator_label]
        if op_street:   fp.append(op_street)
        if op_zip_city: fp.append(op_zip_city)
        if op_phone:    fp.append(f"Tel.: {op_phone}")
        if op_email:    fp.append(op_email)
        if op_website:  fp.append(op_website)
        if op_tax_id:   fp.append(f"St.-Nr.: {op_tax_id}")
        if op_vat_id:   fp.append(f"USt-ID: {op_vat_id}")
        pdf.setFont("Helvetica", 7)
        pdf.setFillColor(rl_colors.HexColor("#b0ccd8"))
        fl1 = "  ·  ".join(fp[:5])
        fl2 = "  ·  ".join(fp[5:]) if len(fp) > 5 else ""
        pdf.drawCentredString(page_w / 2, FOOTER_H - 5 * mm, fl1)
        if fl2:
            pdf.drawCentredString(page_w / 2, FOOTER_H - 9 * mm, fl2)

        # ════════════════════════════════════════════════════════════
        # 7  ZAHLUNGSINFORMATIONEN + KONTAKT
        #    Fest verankert oberhalb des Footers – immer sichtbar
        # ════════════════════════════════════════════════════════════
        INFO_TOP = FOOTER_H + INFO_SECTION_H
        INFO_COL2_X = M_L + CW / 2

        # White panel behind payment/contact so it stays readable regardless of above content.
        pdf.setFillColor(rl_colors.white)
        pdf.rect(M_L - 2 * mm, FOOTER_H + 1 * mm, CW + 4 * mm, INFO_SECTION_H - 2 * mm, stroke=0, fill=1)

        # Vielen-Dank-Zeile
        pdf.setFont("Helvetica-Oblique", 8.5)
        pdf.setFillColor(c_mid)
        pdf.drawString(M_L, INFO_TOP + 10 * mm, "Vielen Dank für Ihr Vertrauen. Bitte überweisen Sie den Gesamtbetrag unter Angabe der Rechnungsnummer.")

        # Trennlinie
        pdf.setStrokeColor(c_rule)
        pdf.setLineWidth(0.4)
        pdf.line(M_L, INFO_TOP + 2 * mm, M_L + CW, INFO_TOP + 2 * mm)

        # Linke Spalte: Bankdaten
        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColor(c_light)
        pdf.drawString(M_L, INFO_TOP - 2 * mm, "BANKVERBINDUNG & ZAHLUNG")
        iy = INFO_TOP - 9 * mm
        pdf.setFont("Helvetica", 8.5)
        pdf.setFillColor(c_dark)
        bank_lines = []
        if op_bank:   bank_lines.append(f"Bank: {op_bank}")
        if op_iban:   bank_lines.append(f"IBAN: {op_iban}")
        if op_bic:    bank_lines.append(f"BIC:  {op_bic}")
        if op_tax_id: bank_lines.append(f"St.-Nr.: {op_tax_id}")
        if op_vat_id: bank_lines.append(f"USt-ID: {op_vat_id}")
        for ln in bank_lines:
            if ln.startswith("IBAN:"):
                # IBAN-Zeile hervorheben
                pdf.setFillColor(rl_colors.HexColor("#e8f4fc"))
                pdf.roundRect(M_L - 1.5 * mm, iy - 1.5 * mm, CW / 2 - 2 * mm, 6 * mm, 1.5, stroke=0, fill=1)
                pdf.setFont("Helvetica-Bold", 8.5)
                pdf.setFillColor(c_primary)
                pdf.drawString(M_L, iy, ln)
            else:
                pdf.setFont("Helvetica", 8.5)
                pdf.setFillColor(c_dark)
                pdf.drawString(M_L, iy, ln)
            iy -= 5.5 * mm

        # Verwendungszweck als eigene hervorgehobene Box
        _vzweck_lbl = f"Rg. {invoice_no}  ·  Fällig: {due_date}"
        _vzweck_box_w = CW / 2 - 2 * mm
        _vzweck_box_h = 9 * mm
        iy -= 1 * mm
        pdf.setFillColor(rl_colors.HexColor("#fff7ed"))
        pdf.setStrokeColor(rl_colors.HexColor("#f59e0b"))
        pdf.setLineWidth(0.7)
        pdf.roundRect(M_L - 1.5 * mm, iy - _vzweck_box_h + 3 * mm, _vzweck_box_w, _vzweck_box_h, 2, stroke=1, fill=1)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColor(rl_colors.HexColor("#b45309"))
        pdf.drawString(M_L, iy + 2 * mm, "Verwendungszweck:")
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.setFillColor(c_dark)
        pdf.drawString(M_L, iy - 2 * mm, _vzweck_lbl)
        pdf.setLineWidth(0.4)

        # Vertikaler Trennstrich zwischen Bank- und Kontaktspalte
        pdf.setStrokeColor(c_rule)
        pdf.setLineWidth(0.5)
        pdf.line(INFO_COL2_X - 4 * mm, FOOTER_H + 3 * mm, INFO_COL2_X - 4 * mm, INFO_TOP + 4 * mm)
        pdf.setLineWidth(0.4)

        # Rechte Spalte: Kontakt
        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColor(c_light)
        pdf.drawString(INFO_COL2_X, INFO_TOP - 2 * mm, "KONTAKT")
        cy = INFO_TOP - 9 * mm
        pdf.setFont("Helvetica", 8.5)
        pdf.setFillColor(c_dark)
        contact_lines = []
        if op_street:   contact_lines.append(op_street)
        if op_zip_city: contact_lines.append(op_zip_city)
        if op_phone:    contact_lines.append(f"Tel.: {op_phone}")
        if op_email:    contact_lines.append(op_email)
        if op_website:  contact_lines.append(op_website)
        if contact_lines:
            for ln in contact_lines[:5]:
                pdf.drawString(INFO_COL2_X, cy, ln)
                cy -= 5 * mm
        else:
            pdf.setFillColor(c_mid)
            pdf.drawString(INFO_COL2_X, cy, "Keine Kontaktdaten hinterlegt")

        # ════════════════════════════════════════════════════════════
        # 9  BEZAHLT-WASSERZEICHEN  (nur wenn Rechnung bezahlt ist)
        # ════════════════════════════════════════════════════════════
        if _inv_status == "bezahlt":
            try:
                from reportlab.lib.colors import Color as _WmColor
                pdf.saveState()
                pdf.translate(page_w / 2, page_h / 2)
                pdf.rotate(35)
                _wm_col = _WmColor(0.086, 0.639, 0.290, alpha=0.09)
                pdf.setFillColor(_wm_col)
                pdf.setFont("Helvetica-Bold", 96)
                pdf.drawCentredString(0, 0, "BEZAHLT")
                pdf.restoreState()
            except Exception:
                pass

        pdf.save()
        pdf_bytes = pdf_buffer.getvalue()
        if pdf_bytes:
            attachment_payload.append({
                "filename":    pdf_filename,
                "mime_type":   "application/pdf",
                "content_b64": base64.b64encode(pdf_bytes).decode("ascii"),
                "raw":         pdf_bytes,
            })
    except Exception as exc:
        app.logger.warning(f"[INVOICE-MAIL] PDF-Anhang konnte nicht erzeugt werden: {exc}")

    # Rechnungen sollen immer mit PDF-Anhang rausgehen.
    if not attachment_payload:
        return False, "PDF-Anhang konnte nicht erzeugt werden (reportlab/Logo/Rendering prüfen)"

    # Use custom email template from settings if configured
    custom_subject = str(settings_row["invoice_email_subject"] if "invoice_email_subject" in settings_row.keys() else "") or ""
    custom_intro = str(settings_row["invoice_email_intro"] if "invoice_email_intro" in settings_row.keys() else "") or ""
    if custom_subject.strip():
        mail_subject = custom_subject.replace("{invoiceNumber}", str(invoice_row["invoice_number"] or "")).replace("{platformName}", platform_label)
    intro_text = custom_intro.strip() if custom_intro.strip() else f"anbei erhalten Sie Ihre Rechnung Nr. {invoice_row['invoice_number']} von {platform_label}.\nAlle Details entnehmen Sie bitte dem beigefügten PDF-Anhang."
    intro_html = custom_intro.strip() if custom_intro.strip() else (
        f"anbei erhalten Sie Ihre Rechnung Nr. <strong>{html.escape(str(invoice_row['invoice_number'] or '-'))}</strong> "
        f"von <strong>{html.escape(platform_label)}</strong>.</p>"
        f"<p style='margin:0 0 14px;'>Alle Details entnehmen Sie bitte dem beigefügten <strong>PDF-Anhang</strong>."
    )

    text_body = (
        f"Guten Tag,\n\n"
        f"{intro_text}\n\n"
        f"Viele Grüße\n{operator_label}"
    )
    body_html = (
        f"<p style='margin:0 0 14px;'>Guten Tag,</p>"
        f"<p style='margin:0 0 14px;'>{intro_html}</p>"
        f"<p style='margin:0;color:#6b7280;font-size:13px;'>Mit freundlichen Grüßen<br><strong>{html.escape(operator_label)}</strong></p>"
    )

    if not smtp_host or not smtp_sender:
        # Try API fallback path if SMTP is not configured but an API key is available
        resend_key, _resend_key_source = _get_resend_api_key_and_source()
        brevo_key = _get_brevo_api_key()
        if resend_key or brevo_key:
            ok, err, _provider_used = _send_via_any_api(
                subject=mail_subject,
                sender_email=smtp_sender or "noreply@example.com",
                sender_name=settings_row["smtp_sender_name"] or "",
                recipient=invoice_row["recipient_email"],
                text_body=text_body,
                html_body=_build_email_html(
                    platform_label,
                    str(settings_row["invoice_primary_color"] or "#0f4c5c"),
                    str(settings_row["invoice_accent_color"] or "#e36414"),
                    "Rechnung von BauPass",
                    body_html,
                    operator_label,
                ),
                attachments=attachment_payload,
            )
            return ok, err if not ok else ""
        return False, "SMTP ist nicht konfiguriert"
    html_body = _build_email_html(
        platform_label,
        str(settings_row["invoice_primary_color"] or "#0f4c5c"),
        str(settings_row["invoice_accent_color"] or "#e36414"),
        "Rechnung von BauPass",
        body_html,
        operator_label,
    )
    message = EmailMessage()
    message["Subject"] = mail_subject
    message["From"] = f"{settings_row['smtp_sender_name']} <{smtp_sender}>"
    message["To"] = invoice_row["recipient_email"]
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    if attachment_payload:
        for att in attachment_payload:
            raw_bytes = att.get("raw") or b""
            if raw_bytes:
                message.add_attachment(
                    raw_bytes,
                    maintype="application",
                    subtype="pdf",
                    filename=str(att.get("filename") or "rechnung.pdf"),
                )

    try:
        with smtplib.SMTP(smtp_host, int(settings_row["smtp_port"] or 587), timeout=20) as smtp:
            if int(settings_row["smtp_use_tls"] or 0) == 1:
                smtp.starttls()
            smtp_username = (settings_row["smtp_username"] or "").strip()
            if smtp_username:
                smtp.login(smtp_username, settings_row["smtp_password"] or "")
            smtp.send_message(message)
        return True, ""
    except Exception as exc:
        fallback_ok, fallback_error, _provider_used = _send_via_any_api(
            subject=str(message["Subject"]),
            sender_email=smtp_sender,
            sender_name=settings_row["smtp_sender_name"] or "",
            recipient=invoice_row["recipient_email"],
            text_body=text_body,
            html_body=html_body,
            attachments=attachment_payload,
        )
        if fallback_ok:
            return True, ""
        return False, f"{exc} | API-Fallback: {fallback_error}"


def get_invoice_retry_delay_seconds(attempt_count):
    # 1. Fehler: 5 min, 2. Fehler: 15 min, danach 30 min
    if attempt_count <= 1:
        return 5 * 60
    if attempt_count == 2:
        return 15 * 60
    return 30 * 60


def is_smtp_related_error(error_message):
    msg = str(error_message or "").strip().lower()
    if not msg:
        return False
    smtp_markers = [
        "smtp",
        "timed out",
        "timeout",
        "connection refused",
        "network is unreachable",
        "getaddrinfo",
        "name or service not known",
        "authentication",
        "535",
        "mail server",
    ]
    return any(marker in msg for marker in smtp_markers)


def classify_invoice_send_error(error_message):
    msg = str(error_message or "").strip().lower()
    if not msg:
        return "unknown"
    if any(token in msg for token in ["535", "authentication", "username", "password", "auth"]):
        return "auth"
    if any(token in msg for token in ["429", "rate", "too many", "421"]):
        return "rate_limit"
    if any(token in msg for token in ["timeout", "timed out", "connection refused", "network is unreachable", "getaddrinfo", "name or service"]):
        return "network"
    if any(token in msg for token in ["550", "mailbox", "recipient", "user unknown"]):
        return "recipient"
    if "smtp ist nicht konfiguriert" in msg:
        return "config"
    return "other"


def get_adaptive_invoice_retry_delay_seconds(attempt_count, error_message):
    base = get_invoice_retry_delay_seconds(attempt_count)
    category = classify_invoice_send_error(error_message)
    if category == "network":
        return int(base * 2)
    if category == "auth":
        return max(60 * 30, int(base * 3))
    if category == "rate_limit":
        return max(60 * 20, int(base * 2.5))
    if category == "config":
        return max(60 * 30, int(base * 3))
    return int(base)


def get_invoice_smtp_circuit_open_until():
    with _invoice_smtp_circuit_lock:
        value = _invoice_smtp_circuit.get("open_until")
        if isinstance(value, datetime):
            return value
        return None


def is_invoice_smtp_circuit_open():
    open_until = get_invoice_smtp_circuit_open_until()
    if not open_until:
        return False
    return datetime.now(timezone.utc) < open_until


def on_invoice_send_success_reset_circuit():
    with _invoice_smtp_circuit_lock:
        _invoice_smtp_circuit["consecutive_failures"] = 0
        _invoice_smtp_circuit["open_until"] = None
        _invoice_smtp_circuit["last_error"] = ""


def on_invoice_send_failure_update_circuit(error_message):
    if not is_smtp_related_error(error_message):
        return
    with _invoice_smtp_circuit_lock:
        failures = int(_invoice_smtp_circuit.get("consecutive_failures") or 0) + 1
        _invoice_smtp_circuit["consecutive_failures"] = failures
        _invoice_smtp_circuit["last_error"] = str(error_message or "")
        if failures >= INVOICE_SMTP_CIRCUIT_FAIL_THRESHOLD:
            _invoice_smtp_circuit["open_until"] = datetime.now(timezone.utc) + timedelta(seconds=INVOICE_SMTP_CIRCUIT_OPEN_SECONDS)


def create_invoice_dead_letter(db, invoice_id, reason, last_error=""):
    existing = db.execute(
        "SELECT id FROM invoice_dead_letters WHERE invoice_id = ? AND resolved_at IS NULL ORDER BY created_at DESC LIMIT 1",
        (invoice_id,),
    ).fetchone()
    if existing:
        return existing["id"]

    dead_id = f"idl-{secrets.token_hex(6)}"
    db.execute(
        """
        INSERT INTO invoice_dead_letters (id, invoice_id, reason, last_error, created_at, resolved_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (dead_id, invoice_id, str(reason or "manual_review"), str(last_error or ""), now_iso()),
    )
    return dead_id


def resolve_invoice_dead_letters(db, invoice_id):
    db.execute(
        """
        UPDATE invoice_dead_letters
        SET resolved_at = ?
        WHERE invoice_id = ? AND resolved_at IS NULL
        """,
        (now_iso(), invoice_id),
    )


def get_invoice_dead_letters(db):
    rows = db.execute(
        """
        SELECT
            invoice_dead_letters.*,
            invoices.invoice_number,
            invoices.company_id,
            invoices.recipient_email,
            invoices.total_amount,
            invoices.status AS invoice_status,
            invoices.send_attempt_count,
            invoices.last_send_attempt_at,
            invoices.next_retry_at,
            companies.name AS company_name
        FROM invoice_dead_letters
        JOIN invoices ON invoices.id = invoice_dead_letters.invoice_id
        JOIN companies ON companies.id = invoices.company_id
        WHERE invoice_dead_letters.resolved_at IS NULL
        ORDER BY invoice_dead_letters.created_at DESC
        LIMIT 100
        """
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def sanitize_invoice_id_list(raw_invoice_ids, max_items=50):
    if not isinstance(raw_invoice_ids, list):
        return []
    cleaned_ids = []
    seen_ids = set()
    for raw in raw_invoice_ids[:max_items]:
        candidate = clean_id_input(raw)
        if not candidate or candidate in seen_ids:
            continue
        seen_ids.add(candidate)
        cleaned_ids.append(candidate)
    return cleaned_ids


def execute_invoice_retry_send_bulk(db, cleaned_ids, actor, success_event, failed_event):
    results = []
    sent_count = 0
    failed_count = 0
    skipped_count = 0

    for invoice_id in cleaned_ids:
        invoice = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice:
            skipped_count += 1
            results.append({"id": invoice_id, "sent": False, "error": "invoice_not_found"})
            continue
        if invoice["paid_at"]:
            skipped_count += 1
            results.append({"id": invoice_id, "sent": False, "error": "invoice_already_paid"})
            continue
        if str(invoice["status"] or "").lower() != "send_failed":
            skipped_count += 1
            results.append({"id": invoice_id, "sent": False, "error": "invoice_not_in_retry_state"})
            continue

        sent_ok, error_message, updated = attempt_invoice_delivery(
            db,
            invoice_id,
            actor=actor,
            audit_event_success=success_event,
            audit_event_failed=failed_event,
        )
        if sent_ok:
            sent_count += 1
        else:
            failed_count += 1
        results.append({"id": invoice_id, "sent": sent_ok, "error": error_message if not sent_ok else "", "invoice": updated})

    return {
        "requested": len(cleaned_ids),
        "sent": sent_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "results": results,
    }


def resolve_invoice_dead_letter_case(db, invoice_id, actor):
    invoice = db.execute("SELECT id, invoice_number, company_id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice:
        return False, "invoice_not_found"

    open_dead_letter = db.execute(
        "SELECT id FROM invoice_dead_letters WHERE invoice_id = ? AND resolved_at IS NULL LIMIT 1",
        (invoice_id,),
    ).fetchone()
    if not open_dead_letter:
        return False, "dead_letter_not_found"

    resolve_invoice_dead_letters(db, invoice_id)
    log_audit(
        "invoice.dead_letter_resolved",
        f"Dead-Letter-Fall für Rechnung {invoice['invoice_number']} als erledigt markiert",
        target_type="invoice",
        target_id=invoice_id,
        company_id=invoice["company_id"],
        actor=actor,
    )
    db.commit()
    return True, ""


def create_operation_approval(db, action_type, payload, actor, target_type=None, target_id=None, company_id=None):
    approval_id = f"apr-{secrets.token_hex(8)}"
    expires_at = (utc_now() + timedelta(minutes=OPERATION_APPROVAL_EXPIRY_MINUTES)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    db.execute(
        """
        INSERT INTO operation_approvals (
            id, action_type, payload_json, status, requested_by_user_id,
            requested_at, expires_at, decided_by_user_id, decided_at, decision_note, execution_result_json
        ) VALUES (?, ?, ?, 'pending', ?, ?, ?, NULL, NULL, '', '')
        """,
        (
            approval_id,
            str(action_type or ""),
            json.dumps(payload or {}, ensure_ascii=True),
            actor["id"],
            now_iso(),
            expires_at,
        ),
    )
    db.commit()
    log_audit(
        "approval.requested",
        f"Freigabe für Aktion {action_type} angefordert",
        target_type=target_type,
        target_id=target_id,
        company_id=company_id,
        actor=actor,
    )
    return approval_id


def mark_expired_operation_approvals(db):
    now_value = now_iso()
    db.execute(
        """
        UPDATE operation_approvals
        SET status = 'expired', decided_at = ?, decision_note = CASE
            WHEN COALESCE(TRIM(decision_note), '') = '' THEN 'expired_by_timeout'
            ELSE decision_note
        END
        WHERE status = 'pending' AND COALESCE(expires_at, '') <> '' AND expires_at <= ?
        """,
        (now_value, now_value),
    )


def list_pending_operation_approvals(db, limit=50, action_type="", max_age_minutes=0):
    mark_expired_operation_approvals(db)

    conditions = ["operation_approvals.status = 'pending'"]
    params = []
    cleaned_action = str(action_type or "").strip().lower()
    if cleaned_action:
        conditions.append("LOWER(operation_approvals.action_type) = ?")
        params.append(cleaned_action)

    max_age = max(0, int(max_age_minutes or 0))
    if max_age > 0:
        age_cutoff = (utc_now() - timedelta(minutes=max_age)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        conditions.append("operation_approvals.requested_at >= ?")
        params.append(age_cutoff)

    where_clause = " AND ".join(conditions)
    rows = db.execute(
        f"""
        SELECT
            operation_approvals.*,
            requester.username AS requested_by_username,
            requester.name AS requested_by_name,
            decider.username AS decided_by_username,
            decider.name AS decided_by_name
        FROM operation_approvals
        LEFT JOIN users AS requester ON requester.id = operation_approvals.requested_by_user_id
        LEFT JOIN users AS decider ON decider.id = operation_approvals.decided_by_user_id
        WHERE {where_clause}
        ORDER BY operation_approvals.requested_at DESC
        LIMIT ?
        """,
        (*params, max(1, min(int(limit), 200))),
    ).fetchall()

    result = []
    for row in rows:
        item = row_to_dict(row)
        try:
            item["payload"] = json.loads(item.get("payload_json") or "{}")
        except Exception:
            item["payload"] = {}
        result.append(item)
    return result


def execute_approved_operation(db, approval_row, actor):
    action_type = str(approval_row["action_type"] or "").strip().lower()
    try:
        payload = json.loads(approval_row["payload_json"] or "{}")
    except Exception as exc:
        raise ValueError("invalid_approval_payload") from exc

    if action_type == "invoice.retry_send_bulk":
        cleaned_ids = sanitize_invoice_id_list(payload.get("invoiceIds") or [])
        if not cleaned_ids:
            raise ValueError("missing_invoice_ids")
        summary = execute_invoice_retry_send_bulk(
            db,
            cleaned_ids,
            actor=actor,
            success_event="invoice.approved_bulk_retry_sent",
            failed_event="invoice.approved_bulk_retry_failed",
        )
        return {"action": action_type, "summary": summary}

    if action_type == "invoice.dead_letter_resolve":
        invoice_id = clean_id_input((payload or {}).get("invoiceId"))
        if not invoice_id:
            raise ValueError("missing_invoice_id")
        resolved_ok, error_code = resolve_invoice_dead_letter_case(db, invoice_id, actor=actor)
        if not resolved_ok:
            raise ValueError(error_code)
        return {"action": action_type, "invoiceId": invoice_id, "resolved": True}

    if action_type == "worker.photo_override":
        worker_id = clean_id_input((payload or {}).get("workerId"))
        if not worker_id:
            raise ValueError("missing_worker_id")
        worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
        if not worker:
            raise ValueError("worker_not_found")
        if worker["deleted_at"]:
            raise ValueError("worker_deleted")
        photo_data = payload.get("photoData") or worker["photo_data"]
        photo_similarity = payload.get("photoMatchSimilarity")
        photo_override_reason = str(payload.get("photoMatchOverrideReason") or "")
        db.execute(
            """
            UPDATE workers
            SET company_id = ?, subcompany_id = ?, first_name = ?, last_name = ?, insurance_number = ?,
                worker_type = ?, role = ?, site = ?, valid_until = ?, visitor_company = ?, visit_purpose = ?,
                host_name = ?, visit_end_at = ?, status = ?, photo_data = ?, badge_pin_hash = ?, physical_card_id = ?
            WHERE id = ?
            """,
            (
                payload.get("companyId") or worker["company_id"],
                payload.get("subcompanyId") if payload.get("subcompanyId") is not None else worker["subcompany_id"],
                payload.get("firstName") or worker["first_name"],
                payload.get("lastName") or worker["last_name"],
                payload.get("insuranceNumber") if payload.get("insuranceNumber") is not None else worker["insurance_number"],
                payload.get("workerType") or worker["worker_type"],
                payload.get("role") if payload.get("role") is not None else worker["role"],
                payload.get("site") if payload.get("site") is not None else worker["site"],
                payload.get("validUntil") if payload.get("validUntil") is not None else worker["valid_until"],
                payload.get("visitorCompany") if payload.get("visitorCompany") is not None else worker["visitor_company"],
                payload.get("visitPurpose") if payload.get("visitPurpose") is not None else worker["visit_purpose"],
                payload.get("hostName") if payload.get("hostName") is not None else worker["host_name"],
                payload.get("visitEndAt") if payload.get("visitEndAt") is not None else worker["visit_end_at"],
                payload.get("status") or worker["status"],
                photo_data,
                payload.get("badgePinHash") if payload.get("badgePinHash") is not None else worker["badge_pin_hash"],
                payload.get("physicalCardId") if payload.get("physicalCardId") is not None else worker["physical_card_id"],
                worker_id,
            ),
        )
        similarity_label = f"{photo_similarity * 100:.1f}%" if isinstance(photo_similarity, float) else "n/a"
        log_audit(
            "security.worker_photo_override",
            f"Foto-Override fuer Mitarbeiter {worker_id} durch 4-Augen-Freigabe bestaetigt (Aehnlichkeit: {similarity_label}, Grund: {photo_override_reason})",
            target_type="worker",
            target_id=worker_id,
            company_id=payload.get("companyId") or worker["company_id"],
            actor=actor,
        )
        log_audit(
            "worker.updated",
            f"Mitarbeiter {worker_id} aktualisiert (Foto-Override 4-Augen)",
            target_type="worker",
            target_id=worker_id,
            company_id=payload.get("companyId") or worker["company_id"],
            actor=actor,
        )
        return {"action": action_type, "workerId": worker_id}

    raise ValueError("unsupported_approval_action")


def build_invoice_incident_export_csv(db):
    retry_rows = db.execute(
        """
        SELECT invoices.*, companies.name AS company_name
        FROM invoices
        JOIN companies ON companies.id = invoices.company_id
        WHERE invoices.status = 'send_failed' AND invoices.paid_at IS NULL
        ORDER BY COALESCE(invoices.next_retry_at, invoices.created_at) ASC
        """
    ).fetchall()
    dead_letter_rows = get_invoice_dead_letters(db)
    alert_rows = db.execute(
        """
        SELECT code, severity, message, details, created_at
        FROM system_alerts
        ORDER BY created_at DESC
        LIMIT 25
        """
    ).fetchall()
    metrics = get_invoice_ops_metrics(db)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "record_type",
        "key",
        "label",
        "invoice_id",
        "invoice_number",
        "company_id",
        "company_name",
        "severity",
        "status",
        "reason",
        "recipient_email",
        "total_amount",
        "send_attempt_count",
        "next_retry_at",
        "created_at",
        "message",
        "details",
    ])

    summary_rows = [
        ("critical_over_24h", "Kritische Fehlversände >24h", metrics.get("criticalOver24h", 0)),
        ("avg_first_success_minutes", "Ø Minuten bis erster Erfolg", metrics.get("avgFirstSuccessMinutes", 0)),
        ("open_retry_queue", "Offene Retry-Fälle", len(retry_rows)),
        ("open_dead_letters", "Offene Dead-Letter-Fälle", len(dead_letter_rows)),
        ("open_system_alerts", "Offene System-Alerts", len(alert_rows)),
    ]
    for key, label, value in summary_rows:
        writer.writerow(["summary", key, label, "", "", "", "", "", "", "", "", value, "", "", utc_iso(), "", ""])

    for error_item in metrics.get("topErrorReasons", []):
        writer.writerow([
            "summary_error_reason",
            error_item.get("label") or "unknown",
            "Top Error Reason",
            "",
            "",
            "",
            "",
            "warning",
            "",
            "",
            "",
            error_item.get("count", 0),
            "",
            "",
            utc_iso(),
            "",
            "",
        ])

    for row in retry_rows:
        writer.writerow([
            "retry_queue",
            row["id"],
            "Retry Queue",
            row["id"],
            row["invoice_number"],
            row["company_id"],
            row["company_name"] or "",
            "warning",
            row["status"] or "",
            classify_invoice_send_error(row["error_message"] or ""),
            row["recipient_email"] or "",
            float(row["total_amount"] or 0),
            int(row["send_attempt_count"] or 0),
            row["next_retry_at"] or "",
            row["created_at"] or "",
            row["error_message"] or "",
            "",
        ])

    for row in dead_letter_rows:
        writer.writerow([
            "dead_letter",
            row["id"],
            "Dead Letter",
            row["invoice_id"],
            row["invoice_number"],
            row["company_id"],
            row["company_name"] or "",
            "critical",
            row["invoice_status"] or "",
            row["reason"] or "",
            row["recipient_email"] or "",
            float(row["total_amount"] or 0),
            int(row["send_attempt_count"] or 0),
            row["next_retry_at"] or "",
            row["created_at"] or "",
            row["last_error"] or "",
            "",
        ])

    for row in alert_rows:
        writer.writerow([
            "system_alert",
            row["code"] or "",
            "System Alert",
            "",
            "",
            "",
            "",
            row["severity"] or "",
            "open",
            row["code"] or "",
            "",
            "",
            "",
            "",
            row["created_at"] or "",
            row["message"] or "",
            json.dumps(row_to_dict(row).get("details") or "", ensure_ascii=True),
        ])

    csv_text = output.getvalue()
    output.close()
    return csv_text


def acquire_invoice_retry_guard(invoice_id, ttl_seconds=90):
    now_dt = datetime.now(timezone.utc)
    with _invoice_retry_guard_lock:
        expired_ids = [
            key for key, expires_at in _invoice_retry_inflight.items()
            if not isinstance(expires_at, datetime) or expires_at <= now_dt
        ]
        for key in expired_ids:
            _invoice_retry_inflight.pop(key, None)

        current = _invoice_retry_inflight.get(invoice_id)
        if isinstance(current, datetime) and current > now_dt:
            return False

        _invoice_retry_inflight[invoice_id] = now_dt + timedelta(seconds=max(15, int(ttl_seconds or 90)))
        return True


def release_invoice_retry_guard(invoice_id):
    with _invoice_retry_guard_lock:
        _invoice_retry_inflight.pop(invoice_id, None)


def parse_iso_datetime_utc(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def calculate_invoice_retry_priority(invoice_row, company_issue_count=1):
    attempt_count = int(invoice_row["send_attempt_count"] or 0)
    amount = float(invoice_row["total_amount"] or 0)
    created_dt = parse_iso_datetime_utc(invoice_row["created_at"]) or datetime.now(timezone.utc)
    age_days = max(0, (datetime.now(timezone.utc) - created_dt).days)

    attempts_score = min(36, max(1, attempt_count) * 8)
    age_score = min(26, age_days * 1.5)
    amount_score = min(22, amount / 220)
    company_score = min(16, max(1, int(company_issue_count or 1)) * 4)
    score = int(round(attempts_score + age_score + amount_score + company_score))

    tier = "niedrig"
    if score >= 70:
        tier = "kritisch"
    elif score >= 45:
        tier = "hoch"

    return {
        "score": score,
        "tier": tier,
        "ageDays": age_days,
        "attemptCount": attempt_count,
        "amount": round(amount, 2),
        "companyIssueCount": max(1, int(company_issue_count or 1)),
    }


def get_critical_invoice_retry_summary(db, min_score=70, top_items=INVOICE_RETRY_ALERT_TOP_ITEMS):
    rows = db.execute(
        """
        SELECT invoices.*, companies.name AS company_name
        FROM invoices
        JOIN companies ON companies.id = invoices.company_id
        WHERE invoices.status = 'send_failed'
          AND invoices.paid_at IS NULL
        """
    ).fetchall()

    company_counts = {}
    for row in rows:
        key = str(row["company_id"] or "").strip()
        if key:
            company_counts[key] = int(company_counts.get(key, 0)) + 1

    critical_rows = []
    for row in rows:
        issue_count = company_counts.get(str(row["company_id"] or ""), 1)
        priority = calculate_invoice_retry_priority(row, issue_count)
        if int(priority["score"]) < int(min_score):
            continue
        critical_rows.append(
            {
                "id": row["id"],
                "invoiceNumber": row["invoice_number"],
                "companyName": row["company_name"] or "Firma",
                "companyId": row["company_id"],
                "score": priority["score"],
                "tier": priority["tier"],
                "amount": priority["amount"],
                "ageDays": priority["ageDays"],
                "attemptCount": priority["attemptCount"],
                "nextRetryAt": row["next_retry_at"] or "",
                "lastError": row["error_message"] or "",
            }
        )

    critical_rows.sort(key=lambda item: (-int(item["score"]), -int(item["ageDays"]), item["invoiceNumber"] or ""))
    return {
        "criticalCount": len(critical_rows),
        "maxScore": int(critical_rows[0]["score"]) if critical_rows else 0,
        "top": critical_rows[: max(1, int(top_items))],
    }


def get_ops_alert_recipients(settings_row):
    env_recipients = [item.strip() for item in (os.getenv("BAUPASS_ALERT_EMAIL_RECIPIENTS") or "").split(",") if item.strip()]
    admin_summary = ""
    if settings_row and "admin_summary_email" in settings_row.keys():
        admin_summary = (settings_row["admin_summary_email"] or "").strip()
    smtp_sender = (settings_row["smtp_sender_email"] or "").strip() if settings_row else ""

    merged = []
    for candidate in env_recipients + ([admin_summary] if admin_summary else []) + ([smtp_sender] if smtp_sender else []):
        if candidate and candidate not in merged:
            merged.append(candidate)
    return merged


def should_send_ops_alert_email(db, event_type, cooldown_minutes=INVOICE_RETRY_ALERT_EMAIL_COOLDOWN_MINUTES):
    threshold = utc_iso(utc_now() - timedelta(minutes=max(1, int(cooldown_minutes))))
    recent = db.execute(
        "SELECT id FROM audit_logs WHERE event_type = ? AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
        (event_type, threshold),
    ).fetchone()
    return recent is None


def record_ops_alert_email_sent(db, event_type, message):
    db.execute(
        """
        INSERT INTO audit_logs (id, event_type, actor_user_id, actor_role, company_id, target_type, target_id, message, created_at)
        VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?, ?)
        """,
        (f"aud-{secrets.token_hex(8)}", event_type, "system", "invoice-retry", message, now_iso()),
    )
    db.commit()


def send_invoice_retry_backlog_alert_email(db, summary, severity):
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if not settings:
        return False, "settings_missing"

    smtp_host = (settings["smtp_host"] or "").strip()
    smtp_sender = (settings["smtp_sender_email"] or "").strip()
    if not smtp_host or not smtp_sender:
        return False, "smtp_not_configured"

    recipients = get_ops_alert_recipients(settings)
    if not recipients:
        return False, "no_recipients"

    event_type = f"ops.invoice_retry_backlog_email.{severity}"
    if not should_send_ops_alert_email(db, event_type):
        return False, "cooldown"

    critical_count = int(summary.get("criticalCount", 0))
    top_rows = summary.get("top", [])
    top_lines = []
    for idx, item in enumerate(top_rows, start=1):
        top_lines.append(
            f"{idx}. {item.get('invoiceNumber') or '-'} | {item.get('companyName') or '-'} | "
            f"Score {item.get('score', 0)} | Versuch {item.get('attemptCount', 0)} | "
            f"{float(item.get('amount', 0)):.2f} EUR | Alter {item.get('ageDays', 0)} Tage"
        )

    alert_text = (
        "BauPass hat eine kritische Lage in der Rechnungs-Retry-Queue erkannt.\n\n"
        f"Schweregrad: {severity}\n"
        f"Kritische Faelle (Score >= 70): {critical_count}\n"
        f"Hoechster Score: {int(summary.get('maxScore', 0))}\n\n"
        "Top-Faelle:\n"
        f"{chr(10).join(top_lines) if top_lines else 'Keine Top-Faelle.'}\n\n"
        "Bitte im Admin-Panel den Rechnungsbereich oeffnen und die Queue pruefen."
    )
    message = EmailMessage()
    message["Subject"] = f"[BauPass] {'KRITISCH' if severity == 'critical' else 'Warnung'}: {critical_count} kritische Retry-Faelle"
    message["From"] = f"{settings['smtp_sender_name']} <{smtp_sender}>"
    message["To"] = ", ".join(recipients)
    message.set_content(alert_text)

    try:
        with smtplib.SMTP(smtp_host, int(settings["smtp_port"] or 587), timeout=20) as smtp:
            if int(settings["smtp_use_tls"] or 0) == 1:
                smtp.starttls()
            smtp_username = (settings["smtp_username"] or "").strip()
            if smtp_username:
                smtp.login(smtp_username, settings["smtp_password"] or "")
            smtp.send_message(message)
        record_ops_alert_email_sent(
            db,
            event_type,
            f"Retry-Backlog Alert versendet ({severity}) an {', '.join(recipients)} bei {critical_count} kritischen Faellen.",
        )
        return True, "sent"
    except Exception as exc:
        for r in recipients:
            fallback_ok, _, _provider_used = _send_via_any_api(
                subject=str(message["Subject"]),
                sender_email=smtp_sender,
                sender_name=settings["smtp_sender_name"] or "",
                recipient=r,
                text_body=alert_text,
                html_body="",
            )
            if fallback_ok:
                record_ops_alert_email_sent(
                    db,
                    event_type,
                    f"Retry-Backlog Alert (API-Fallback) versendet ({severity}) an {r}.",
                )
                return True, "sent_via_resend"
        return False, str(exc)


def resolve_invoice_attempt_actor_label(actor):
    if not actor:
        return "system"
    if isinstance(actor, dict):
        name = str(actor.get("name") or "").strip()
        email = str(actor.get("email") or "").strip()
        user_id = str(actor.get("id") or "").strip()
        return name or email or user_id or "system"
    return str(actor).strip() or "system"


def log_invoice_send_attempt(db, invoice_id, attempt_number, outcome, error_message="", actor=None, next_retry_at=None):
    db.execute(
        """
        INSERT INTO invoice_send_attempts (
            id, invoice_id, attempt_number, outcome, error_message, actor_label, next_retry_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"isat-{secrets.token_hex(6)}",
            invoice_id,
            int(attempt_number or 1),
            str(outcome or "failed"),
            str(error_message or ""),
            resolve_invoice_attempt_actor_label(actor),
            next_retry_at,
            now_iso(),
        ),
    )


def attempt_invoice_delivery(db, invoice_id, actor=None, audit_event_success="invoice.sent", audit_event_failed="invoice.send_failed", settings_override=None):
    invoice_row = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice_row:
        return False, "invoice_not_found", None

    if not acquire_invoice_retry_guard(invoice_id):
        return False, "retry_in_progress", row_to_dict(invoice_row)

    try:
        previous_attempts = int(invoice_row["send_attempt_count"] or 0)
        next_attempts = previous_attempts + 1
        attempt_at = now_iso()

        company = db.execute("SELECT * FROM companies WHERE id = ?", (invoice_row["company_id"],)).fetchone()
        if not company or company["deleted_at"]:
            dead_letter_id = None
            if next_attempts >= INVOICE_SEND_MAX_RETRIES:
                dead_letter_id = create_invoice_dead_letter(db, invoice_id, "company_not_available", "company_not_available")
            db.execute(
                "UPDATE invoices SET status = ?, error_message = ?, send_attempt_count = send_attempt_count + 1, last_send_attempt_at = ?, next_retry_at = NULL WHERE id = ?",
                ("send_failed", "company_not_available", attempt_at, invoice_id),
            )
            log_invoice_send_attempt(
                db,
                invoice_id,
                next_attempts,
                outcome="failed",
                error_message="company_not_available",
                actor=actor,
                next_retry_at=None,
            )
            if dead_letter_id:
                create_system_alert(
                    db,
                    code="invoice_dead_letter_created",
                    severity="warning",
                    message=f"Rechnung {invoice_row['invoice_number']} wurde in die Dead-Letter-Queue verschoben.",
                    details={"invoiceId": invoice_id, "deadLetterId": dead_letter_id, "reason": "company_not_available"},
                    dedup_minutes=10,
                )
            db.commit()
            return False, "company_not_available", row_to_dict(invoice_row)

        settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        effective_settings = dict(settings) if settings else {}
        if isinstance(settings_override, dict):
            for key, value in settings_override.items():
                effective_settings[str(key)] = value

        if is_invoice_smtp_circuit_open():
            open_until = get_invoice_smtp_circuit_open_until()
            if open_until:
                delay_seconds = max(60, int((open_until - datetime.now(timezone.utc)).total_seconds()))
            else:
                delay_seconds = INVOICE_SMTP_CIRCUIT_OPEN_SECONDS
            next_retry = utc_iso(utc_now() + timedelta(seconds=delay_seconds))
            db.execute(
                "UPDATE invoices SET status = ?, error_message = ?, last_send_attempt_at = ?, next_retry_at = ? WHERE id = ?",
                ("send_failed", "smtp_circuit_open", attempt_at, next_retry, invoice_id),
            )
            log_invoice_send_attempt(
                db,
                invoice_id,
                max(1, previous_attempts),
                outcome="skipped",
                error_message="smtp_circuit_open",
                actor=actor,
                next_retry_at=next_retry,
            )
            db.commit()
            refreshed = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            return False, "smtp_circuit_open", row_to_dict(refreshed)

        sent_ok, error_message = send_invoice_email(invoice_row, company, effective_settings)

        if sent_ok:
            on_invoice_send_success_reset_circuit()
            db.execute(
                "UPDATE invoices SET status = ?, sent_at = ?, error_message = '', send_attempt_count = ?, last_send_attempt_at = ?, next_retry_at = NULL WHERE id = ?",
                ("sent", attempt_at, next_attempts, attempt_at, invoice_id),
            )
            resolve_invoice_dead_letters(db, invoice_id)
            log_invoice_send_attempt(
                db,
                invoice_id,
                next_attempts,
                outcome="sent",
                error_message="",
                actor=actor,
                next_retry_at=None,
            )
            log_audit(
                audit_event_success,
                f"Rechnung {invoice_row['invoice_number']} an {invoice_row['recipient_email']} versendet",
                target_type="invoice",
                target_id=invoice_id,
                company_id=invoice_row["company_id"],
                actor=actor,
            )
        else:
            on_invoice_send_failure_update_circuit(error_message)
            retry_delay = get_adaptive_invoice_retry_delay_seconds(next_attempts, error_message)
            has_retry_budget = next_attempts < INVOICE_SEND_MAX_RETRIES
            next_retry = utc_iso(utc_now() + timedelta(seconds=retry_delay)) if has_retry_budget else None
            db.execute(
                "UPDATE invoices SET status = ?, error_message = ?, send_attempt_count = ?, last_send_attempt_at = ?, next_retry_at = ? WHERE id = ?",
                ("send_failed", error_message, next_attempts, attempt_at, next_retry, invoice_id),
            )
            log_invoice_send_attempt(
                db,
                invoice_id,
                next_attempts,
                outcome="failed",
                error_message=error_message,
                actor=actor,
                next_retry_at=next_retry,
            )
            log_audit(
                audit_event_failed,
                f"Rechnung {invoice_row['invoice_number']} konnte nicht versendet werden: {error_message}",
                target_type="invoice",
                target_id=invoice_id,
                company_id=invoice_row["company_id"],
                actor=actor,
            )
            if not has_retry_budget:
                dead_letter_id = create_invoice_dead_letter(db, invoice_id, "max_retries_exhausted", error_message)
                create_system_alert(
                    db,
                    code="invoice_dead_letter_created",
                    severity="warning",
                    message=f"Rechnung {invoice_row['invoice_number']} wurde in die Dead-Letter-Queue verschoben.",
                    details={"invoiceId": invoice_id, "deadLetterId": dead_letter_id, "reason": "max_retries_exhausted"},
                    dedup_minutes=10,
                )

        db.commit()
        refreshed = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        return sent_ok, ("" if sent_ok else error_message), row_to_dict(refreshed)
    finally:
        release_invoice_retry_guard(invoice_id)


def retry_failed_invoice_deliveries(db):
    due_rows = db.execute(
        """
        SELECT id
        FROM invoices
        WHERE status = 'send_failed'
          AND sent_at IS NULL
          AND COALESCE(send_attempt_count, 0) < ?
          AND (next_retry_at IS NULL OR next_retry_at <= ?)
        ORDER BY created_at ASC
        LIMIT 25
        """,
        (INVOICE_SEND_MAX_RETRIES, now_iso()),
    ).fetchall()

    result = {"attempted": 0, "sent": 0, "failed": 0}
    for row in due_rows:
        result["attempted"] += 1
        sent_ok, _error, _invoice = attempt_invoice_delivery(
            db,
            row["id"],
            actor=None,
            audit_event_success="invoice.retry_sent",
            audit_event_failed="invoice.retry_failed",
        )
        if sent_ok:
            result["sent"] += 1
        else:
            result["failed"] += 1
    return result


def get_invoice_ops_metrics(db):
    invoice_rows = db.execute(
        """
        SELECT invoices.*, companies.name AS company_name
        FROM invoices
        JOIN companies ON companies.id = invoices.company_id
        ORDER BY invoices.created_at DESC
        """
    ).fetchall()
    attempt_rows = db.execute(
        """
        SELECT invoice_id, outcome, error_message, created_at
        FROM invoice_send_attempts
        ORDER BY created_at DESC
        """
    ).fetchall()

    attempts_by_invoice = {}
    for row in attempt_rows:
        attempts_by_invoice.setdefault(row["invoice_id"], []).append(row)

    first_success_minutes = []
    critical_over_24h = 0
    trend_buckets = {}
    error_buckets = {}
    now_dt = utc_now()
    window_start = now_dt - timedelta(days=6)

    for invoice in invoice_rows:
        invoice_attempts = attempts_by_invoice.get(invoice["id"], [])
        created_dt = parse_iso_datetime_utc(invoice["created_at"])
        if created_dt and invoice_attempts:
            success_attempts = [row for row in invoice_attempts if str(row["outcome"] or "").lower() == "sent"]
            if success_attempts:
                earliest_success = min(
                    (parse_iso_datetime_utc(row["created_at"]) for row in success_attempts),
                    key=lambda value: value or datetime.max.replace(tzinfo=timezone.utc),
                )
                if earliest_success:
                    first_success_minutes.append(max(0, int((earliest_success - created_dt).total_seconds() // 60)))

        if str(invoice["status"] or "").lower() == "send_failed":
            issue_count = 1
            company_id = str(invoice["company_id"] or "")
            if company_id:
                issue_count = sum(1 for row in invoice_rows if str(row["company_id"] or "") == company_id and str(row["status"] or "").lower() == "send_failed" and not row["paid_at"])
            priority = calculate_invoice_retry_priority(invoice, issue_count)
            if priority["score"] >= 70 and created_dt and (now_dt - created_dt).total_seconds() >= 24 * 3600:
                critical_over_24h += 1

        for row in invoice_attempts:
            attempt_dt = parse_iso_datetime_utc(row["created_at"])
            if attempt_dt and attempt_dt >= window_start:
                day_key = attempt_dt.strftime("%Y-%m-%d")
                trend_buckets[day_key] = int(trend_buckets.get(day_key, 0)) + 1
            if str(row["outcome"] or "").lower() == "failed":
                label = classify_invoice_send_error(row["error_message"] or "")
                error_buckets[label] = int(error_buckets.get(label, 0)) + 1

    trend = []
    for offset in range(7):
        day = (window_start + timedelta(days=offset)).strftime("%Y-%m-%d")
        trend.append({"day": day, "count": int(trend_buckets.get(day, 0))})

    sorted_errors = sorted(error_buckets.items(), key=lambda item: (-int(item[1]), item[0]))[:5]
    avg_first_success_minutes = round(sum(first_success_minutes) / len(first_success_minutes), 1) if first_success_minutes else 0

    return {
        "avgFirstSuccessMinutes": avg_first_success_minutes,
        "criticalOver24h": critical_over_24h,
        "retryVolume7d": trend,
        "topErrorReasons": [{"label": label, "count": count} for label, count in sorted_errors],
    }


@app.get("/api/invoices")
@require_auth
@require_roles("superadmin", "company-admin")
def list_invoices():
    db = get_db()
    if g.current_user["role"] == "superadmin":
        rows = db.execute(
            """
            SELECT invoices.*, companies.name AS company_name
            FROM invoices
            JOIN companies ON companies.id = invoices.company_id
            ORDER BY invoices.created_at DESC
            LIMIT 300
            """
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT invoices.*, companies.name AS company_name
            FROM invoices
            JOIN companies ON companies.id = invoices.company_id
            WHERE invoices.company_id = ?
            ORDER BY invoices.created_at DESC
            LIMIT 300
            """,
            (g.current_user["company_id"],),
        ).fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/api/invoices/ops-metrics")
@require_auth
@require_roles("superadmin")
def get_invoice_ops_metrics_endpoint():
    db = get_db()
    return jsonify(get_invoice_ops_metrics(db))


@app.get("/api/invoices/dead-letters")
@require_auth
@require_roles("superadmin")
def list_invoice_dead_letters():
    db = get_db()
    return jsonify(get_invoice_dead_letters(db))


@app.get("/api/invoices/next-number")
@require_auth
@require_roles("superadmin")
def get_next_invoice_number():
    """Return the next sequential invoice number in RE-YYYY-NNN format."""
    db = get_db()
    year = datetime.now().year
    prefix = f"RE-{year}-"
    rows = db.execute(
        "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ? ORDER BY invoice_number DESC",
        (f"{prefix}%",),
    ).fetchall()
    max_seq = 0
    for row in rows:
        num_part = str(row["invoice_number"] or "")[len(prefix):]
        if num_part.isdigit():
            max_seq = max(max_seq, int(num_part))
    next_num = f"{prefix}{str(max_seq + 1).zfill(4)}"
    return jsonify({"nextNumber": next_num})


@app.post("/api/invoices/send")
@require_auth
@require_roles("superadmin")
def send_invoice():
    payload = request.get_json(silent=True) or {}
    company_id = payload.get("companyId")
    recipient_email = (payload.get("recipientEmail") or "").strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient_email):
        return jsonify({"error": "invalid_recipient_email"}), 400

    db = get_db()
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company or company["deleted_at"]:
        return jsonify({"error": "company_not_available"}), 400

    if g.current_user["role"] != "superadmin" and company_id != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_company"}), 403

    invoice_number = (payload.get("invoiceNumber") or "").strip() or f"RE-{datetime.now().year}-{secrets.token_hex(3).upper()}"
    if len(invoice_number) < 3 or len(invoice_number) > 64:
        return jsonify({"error": "invalid_invoice_number_length", "message": "Rechnungsnummer muss zwischen 3 und 64 Zeichen haben."}), 400
    duplicate_invoice = db.execute(
        "SELECT id FROM invoices WHERE company_id = ? AND invoice_number = ? LIMIT 1",
        (company_id, invoice_number),
    ).fetchone()
    if duplicate_invoice:
        return jsonify({"error": "duplicate_invoice_number", "message": "Rechnungsnummer ist bereits vergeben."}), 409

    invoice_date = (payload.get("invoiceDate") or utc_now().date().isoformat()).strip()
    due_date_input = (payload.get("dueDate") or "").strip()
    invoice_date_obj = parse_iso_date(invoice_date) or utc_now().date()
    due_date_obj = parse_iso_date(due_date_input) or (invoice_date_obj + timedelta(days=14))
    if due_date_obj < invoice_date_obj:
        return jsonify({"error": "invalid_due_date", "message": "Fälligkeitsdatum darf nicht vor dem Rechnungsdatum liegen."}), 400
    due_date = due_date_obj.isoformat()
    invoice_period = (payload.get("invoicePeriod") or "").strip()
    description = (payload.get("description") or "").strip()
    rendered_html = payload.get("renderedHtml") or ""

    # Optional one-shot override values from the current UI state.
    raw_overrides = payload.get("invoiceSettingsOverrides") or {}
    settings_override = {}
    if isinstance(raw_overrides, dict):
        override_map = {
            "invoiceLogoData": "invoice_logo_data",
            "invoicePrimaryColor": "invoice_primary_color",
            "invoiceAccentColor": "invoice_accent_color",
            "invoiceIban": "invoice_iban",
            "invoiceBic": "invoice_bic",
            "invoiceBankName": "invoice_bank_name",
            "invoiceTaxId": "invoice_tax_id",
            "invoiceVatId": "invoice_vat_id",
            "invoiceOperatorStreet": "invoice_operator_street",
            "invoiceOperatorZipCity": "invoice_operator_zip_city",
            "invoiceOperatorPhone": "invoice_operator_phone",
            "invoiceOperatorWebsite": "invoice_operator_website",
        }
        for source_key, target_key in override_map.items():
            if source_key in raw_overrides:
                settings_override[target_key] = str(raw_overrides.get(source_key) or "").strip()
        if "invoiceOperatorEmail" in raw_overrides:
            try:
                settings_override["invoice_operator_email"] = sanitize_optional_email(
                    raw_overrides.get("invoiceOperatorEmail", ""),
                    field_error="invalid_invoice_operator_email",
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

    # Multi-position support
    items_raw = payload.get("items") or []
    items_json_str = ""
    if items_raw and isinstance(items_raw, list):
        cleaned_items = []
        computed_net = 0.0
        for item in items_raw:
            qty = float(item.get("qty") or 1)
            unit_price = float(item.get("unitPrice") or 0)
            total_item = round(qty * unit_price, 2)
            item_description = str(item.get("description") or "").strip()[:200]
            if not item_description and total_item <= 0:
                continue
            cleaned_items.append({
                "description": item_description,
                "qty": qty,
                "unit": str(item.get("unit") or "Pauschal").strip()[:30],
                "unitPrice": unit_price,
                "total": total_item,
            })
            computed_net += total_item
        if cleaned_items:
            items_json_str = json.dumps(cleaned_items, ensure_ascii=False)
            net_amount = round(computed_net, 2)
        else:
            net_amount = calculate_net_amount_by_plan(company["plan"], payload.get("netAmount"))
    else:
        net_amount = calculate_net_amount_by_plan(company["plan"], payload.get("netAmount"))

    # Discount / Skonto
    discount_amount = round(float(payload.get("discountAmount") or 0), 2)
    if discount_amount < 0 or discount_amount > net_amount:
        discount_amount = 0.0
    net_after_discount = round(net_amount - discount_amount, 2)

    vat_rate = float(payload.get("vatRate") or 0)
    if vat_rate < 0 or vat_rate > 100:
        return jsonify({"error": "invalid_vat_rate", "message": "MwSt. muss zwischen 0 und 100 liegen."}), 400
    vat_amount = round(net_after_discount * (vat_rate / 100), 2)
    total_amount = round(net_after_discount + vat_amount, 2)

    if not invoice_period or not description or not rendered_html:
        return jsonify({"error": "missing_invoice_fields"}), 400

    invoice_id = f"inv-{secrets.token_hex(6)}"
    db.execute(
        """
        INSERT INTO invoices (
            id, invoice_number, company_id, recipient_email, invoice_date, invoice_period, description,
            net_amount, vat_rate, vat_amount, total_amount, status, error_message, sent_at,
            rendered_html, created_by_user_id, created_at, due_date, reminder_stage, last_reminder_sent_at, last_reminder_error,
            send_attempt_count, last_send_attempt_at, next_retry_at, items_json, discount_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invoice_id,
            invoice_number,
            company_id,
            recipient_email,
            invoice_date,
            invoice_period,
            description,
            net_amount,
            vat_rate,
            vat_amount,
            total_amount,
            "draft",
            "",
            None,
            rendered_html,
            g.current_user["id"],
            now_iso(),
            due_date,
            0,
            None,
            "",
            0,
            None,
            None,
            items_json_str,
            discount_amount,
        ),
    )
    db.commit()

    sent_ok, error_message, result = attempt_invoice_delivery(
        db,
        invoice_id,
        actor=g.current_user,
        settings_override=settings_override,
    )
    return jsonify({"invoice": result, "sent": sent_ok, "error": error_message if not sent_ok else ""})


@app.post("/api/invoices/<invoice_id>/retry-send")
@require_auth
@require_roles("superadmin")
def retry_send_invoice(invoice_id):
    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice:
        return jsonify({"error": "invoice_not_found"}), 404
    if invoice["paid_at"]:
        return jsonify({"error": "invoice_already_paid"}), 400

    sent_ok, error_message, updated = attempt_invoice_delivery(
        db,
        invoice_id,
        actor=g.current_user,
        audit_event_success="invoice.manual_retry_sent",
        audit_event_failed="invoice.manual_retry_failed",
    )
    return jsonify({"invoice": updated, "sent": sent_ok, "error": error_message if not sent_ok else ""})


@app.get("/api/invoices/<invoice_id>/attempts")
@require_auth
@require_roles("superadmin")
def get_invoice_send_attempts(invoice_id):
    db = get_db()
    invoice = db.execute("SELECT id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice:
        return jsonify({"error": "invoice_not_found"}), 404

    rows = db.execute(
        """
        SELECT id, invoice_id, attempt_number, outcome, error_message, actor_label, next_retry_at, created_at
        FROM invoice_send_attempts
        WHERE invoice_id = ?
        ORDER BY created_at DESC
        LIMIT 40
        """,
        (invoice_id,),
    ).fetchall()
    return jsonify({"invoiceId": invoice_id, "attempts": [row_to_dict(row) for row in rows]})


@app.put("/api/invoices/<invoice_id>/dead-letter/resolve")
@require_auth
@require_roles("superadmin")
def resolve_invoice_dead_letter(invoice_id):
    db = get_db()
    invoice = db.execute("SELECT id, invoice_number, company_id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice:
        return jsonify({"error": "invoice_not_found"}), 404

    open_dead_letter = db.execute(
        "SELECT id FROM invoice_dead_letters WHERE invoice_id = ? AND resolved_at IS NULL LIMIT 1",
        (invoice_id,),
    ).fetchone()
    if not open_dead_letter:
        return jsonify({"error": "dead_letter_not_found"}), 404

    approval_id = create_operation_approval(
        db,
        "invoice.dead_letter_resolve",
        {"invoiceId": invoice_id},
        actor=g.current_user,
        target_type="invoice",
        target_id=invoice_id,
        company_id=invoice["company_id"],
    )
    return jsonify({"ok": True, "approvalRequested": True, "approvalId": approval_id, "invoiceId": invoice_id}), 202


@app.post("/api/invoices/retry-send-bulk")
@require_auth
@require_roles("superadmin")
def retry_send_invoices_bulk():
    payload = request.get_json(silent=True) or {}
    cleaned_ids = sanitize_invoice_id_list(payload.get("invoiceIds") or [])
    if not cleaned_ids:
        return jsonify({"error": "missing_invoice_ids"}), 400

    db = get_db()
    approval_id = create_operation_approval(
        db,
        "invoice.retry_send_bulk",
        {"invoiceIds": cleaned_ids},
        actor=g.current_user,
        target_type="invoice",
        target_id=cleaned_ids[0],
    )
    return jsonify({"ok": True, "approvalRequested": True, "approvalId": approval_id, "requested": len(cleaned_ids)}), 202


@app.get("/api/invoices/approvals/pending")
@require_auth
@require_roles("superadmin")
def list_pending_invoice_approvals_endpoint():
    db = get_db()
    limit = min(max(int(request.args.get("limit", "50")), 1), 200)
    action_type = (request.args.get("actionType") or "").strip().lower()
    max_age_minutes = max(0, int(request.args.get("maxAgeMinutes", "0")))
    return jsonify(list_pending_operation_approvals(db, limit=limit, action_type=action_type, max_age_minutes=max_age_minutes))


@app.post("/api/invoices/approvals/<approval_id>/decision")
@require_auth
@require_roles("superadmin")
def decide_invoice_approval(approval_id):
    decision_payload = request.get_json(silent=True) or {}
    decision = str(decision_payload.get("decision") or "").strip().lower()
    if decision not in {"approve", "reject"}:
        return jsonify({"error": "invalid_decision"}), 400

    db = get_db()
    mark_expired_operation_approvals(db)
    db.commit()
    approval = db.execute(
        "SELECT * FROM operation_approvals WHERE id = ?",
        (approval_id,),
    ).fetchone()
    if not approval:
        return jsonify({"error": "approval_not_found"}), 404

    status_value = str(approval["status"] or "").strip().lower()
    if status_value == "expired":
        return jsonify({"error": "approval_expired"}), 410
    if status_value != "pending":
        return jsonify({"error": "approval_not_pending"}), 409

    expires_at = parse_iso_datetime_utc(approval["expires_at"])
    if expires_at and expires_at <= utc_now():
        db.execute(
            """
            UPDATE operation_approvals
            SET status = 'expired', decided_at = ?, decision_note = 'expired_by_timeout'
            WHERE id = ?
            """,
            (now_iso(), approval_id),
        )
        db.commit()
        return jsonify({"error": "approval_expired"}), 410

    if approval["requested_by_user_id"] == g.current_user["id"]:
        return jsonify({"error": "approver_must_be_different_user"}), 403

    note = str(decision_payload.get("note") or "").strip()[:400]
    if decision == "reject":
        if not note:
            return jsonify({"error": "decision_note_required"}), 400
        db.execute(
            """
            UPDATE operation_approvals
            SET status = 'rejected', decided_by_user_id = ?, decided_at = ?, decision_note = ?
            WHERE id = ?
            """,
            (g.current_user["id"], now_iso(), note, approval_id),
        )
        db.commit()
        log_audit(
            "approval.rejected",
            f"Freigabe {approval_id} wurde abgelehnt",
            target_type="approval",
            target_id=approval_id,
            actor=g.current_user,
        )
        return jsonify({"ok": True, "approvalId": approval_id, "status": "rejected"})

    try:
        execution_result = execute_approved_operation(db, approval, actor=g.current_user)
    except ValueError as exc:
        error_text = str(exc)
        db.execute(
            """
            UPDATE operation_approvals
            SET status = 'rejected', decided_by_user_id = ?, decided_at = ?, decision_note = ?
            WHERE id = ?
            """,
            (g.current_user["id"], now_iso(), f"execution_failed:{error_text}", approval_id),
        )
        db.commit()
        return jsonify({"error": "approval_execution_failed", "details": error_text}), 400

    db.execute(
        """
        UPDATE operation_approvals
        SET status = 'approved', decided_by_user_id = ?, decided_at = ?, decision_note = ?, execution_result_json = ?
        WHERE id = ?
        """,
        (
            g.current_user["id"],
            now_iso(),
            note,
            json.dumps(execution_result or {}, ensure_ascii=True),
            approval_id,
        ),
    )
    db.commit()
    log_audit(
        "approval.approved",
        f"Freigabe {approval_id} wurde bestätigt und ausgeführt",
        target_type="approval",
        target_id=approval_id,
        actor=g.current_user,
    )
    return jsonify({"ok": True, "approvalId": approval_id, "status": "approved", "execution": execution_result})


# ── 4-Augen: Foto-Override-Freigaben ─────────────────────────────────────────

@app.get("/api/workers/photo-override-approvals/pending")
@require_auth
@require_roles("superadmin")
def list_pending_photo_override_approvals():
    db = get_db()
    mark_expired_operation_approvals(db)
    db.commit()
    rows = db.execute(
        """
        SELECT * FROM operation_approvals
        WHERE action_type = 'worker.photo_override' AND status = 'pending'
        ORDER BY requested_at DESC
        LIMIT 50
        """,
    ).fetchall()
    result = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        similarity = payload.get("photoMatchSimilarity")
        result.append({
            "approvalId": row["id"],
            "workerId": payload.get("workerId"),
            "workerName": f"{payload.get('firstName', '')} {payload.get('lastName', '')}".strip(),
            "overrideReason": payload.get("photoMatchOverrideReason"),
            "similarity": round(similarity * 100, 1) if isinstance(similarity, (int, float)) else None,
            "requestedByUserId": row["requested_by_user_id"],
            "requestedAt": row["requested_at"],
            "expiresAt": row["expires_at"],
            "photoData": payload.get("photoData"),
        })
    return jsonify(result)


@app.post("/api/workers/photo-override-approvals/<approval_id>/decision")
@require_auth
@require_roles("superadmin")
def decide_photo_override_approval(approval_id):
    decision_payload = request.get_json(silent=True) or {}
    decision = str(decision_payload.get("decision") or "").strip().lower()
    if decision not in {"approve", "reject"}:
        return jsonify({"error": "invalid_decision"}), 400

    db = get_db()
    mark_expired_operation_approvals(db)
    db.commit()
    approval = db.execute(
        "SELECT * FROM operation_approvals WHERE id = ? AND action_type = 'worker.photo_override'",
        (approval_id,),
    ).fetchone()
    if not approval:
        return jsonify({"error": "approval_not_found"}), 404

    status_value = str(approval["status"] or "").strip().lower()
    if status_value == "expired":
        return jsonify({"error": "approval_expired"}), 410
    if status_value != "pending":
        return jsonify({"error": "approval_not_pending"}), 409

    expires_at = parse_iso_datetime_utc(approval["expires_at"])
    if expires_at and expires_at <= utc_now():
        db.execute(
            "UPDATE operation_approvals SET status = 'expired', decided_at = ?, decision_note = 'expired_by_timeout' WHERE id = ?",
            (now_iso(), approval_id),
        )
        db.commit()
        return jsonify({"error": "approval_expired"}), 410

    if approval["requested_by_user_id"] == g.current_user["id"]:
        return jsonify({"error": "approver_must_be_different_user"}), 403

    note = str(decision_payload.get("note") or "").strip()[:400]
    if decision == "reject":
        if not note:
            return jsonify({"error": "decision_note_required"}), 400
        db.execute(
            "UPDATE operation_approvals SET status = 'rejected', decided_by_user_id = ?, decided_at = ?, decision_note = ? WHERE id = ?",
            (g.current_user["id"], now_iso(), note, approval_id),
        )
        db.commit()
        log_audit(
            "approval.rejected",
            f"Foto-Override-Freigabe {approval_id} abgelehnt",
            target_type="approval",
            target_id=approval_id,
            actor=g.current_user,
        )
        return jsonify({"ok": True, "approvalId": approval_id, "status": "rejected"})

    try:
        execution_result = execute_approved_operation(db, approval, actor=g.current_user)
    except ValueError as exc:
        error_text = str(exc)
        db.execute(
            "UPDATE operation_approvals SET status = 'rejected', decided_by_user_id = ?, decided_at = ?, decision_note = ? WHERE id = ?",
            (g.current_user["id"], now_iso(), f"execution_failed:{error_text}", approval_id),
        )
        db.commit()
        return jsonify({"error": "approval_execution_failed", "details": error_text}), 400

    db.execute(
        "UPDATE operation_approvals SET status = 'approved', decided_by_user_id = ?, decided_at = ?, decision_note = ?, execution_result_json = ? WHERE id = ?",
        (g.current_user["id"], now_iso(), note, json.dumps(execution_result or {}, ensure_ascii=True), approval_id),
    )
    db.commit()
    log_audit(
        "approval.approved",
        f"Foto-Override-Freigabe {approval_id} bestaetigt und ausgefuehrt",
        target_type="approval",
        target_id=approval_id,
        actor=g.current_user,
    )
    return jsonify({"ok": True, "approvalId": approval_id, "status": "approved", "execution": execution_result})


@app.get("/api/invoices/retry-queue/export.csv")
@require_auth
@require_roles("superadmin")
def export_invoice_retry_queue_csv():
    db = get_db()
    rows = db.execute(
        """
        SELECT invoices.*, companies.name AS company_name
        FROM invoices
        JOIN companies ON companies.id = invoices.company_id
        WHERE invoices.status = 'send_failed' AND invoices.paid_at IS NULL
        ORDER BY COALESCE(invoices.next_retry_at, invoices.created_at) ASC
        """
    ).fetchall()

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return jsonify({"error": "pdf_dependency_missing", "message": "Bitte reportlab installieren."}), 503

    buffer = io.BytesIO()
    pw, ph = landscape(A4)
    pdf = rl_canvas.Canvas(buffer, pagesize=landscape(A4))
    rq_col_x = [36, 120, 236, 356, 426, 496, 566, 656]
    rq_headers = ["Rechnungs-Nr.", "Firma", "Empfänger-Email", "Betrag", "Versuche", "Nächster Retry", "Erstellt", "Fehler"]

    def draw_rq_hdr(y):
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(36, y, "BauPass - Rechnungs-Retry-Queue")
        y -= 14
        pdf.setFont("Helvetica", 8)
        pdf.drawString(36, y, f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')} | {len(rows)} Einträge")
        y -= 16
        pdf.setFont("Helvetica-Bold", 7)
        for i, h in enumerate(rq_headers):
            pdf.drawString(rq_col_x[i], y, h)
        y -= 8
        pdf.line(36, y, pw - 36, y)
        y -= 10
        return y

    y = ph - 36
    y = draw_rq_hdr(y)
    pdf.setFont("Helvetica", 7)
    for row in rows:
        if y < 48:
            pdf.showPage()
            y = ph - 36
            y = draw_rq_hdr(y)
            pdf.setFont("Helvetica", 7)
        pdf.drawString(rq_col_x[0], y, str(row["invoice_number"] or "")[:16])
        pdf.drawString(rq_col_x[1], y, str(row["company_name"] or "")[:18])
        pdf.drawString(rq_col_x[2], y, str(row["recipient_email"] or "")[:28])
        pdf.drawString(rq_col_x[3], y, f"{float(row['total_amount'] or 0):.2f} €")
        pdf.drawString(rq_col_x[4], y, str(int(row["send_attempt_count"] or 0)))
        pdf.drawString(rq_col_x[5], y, str(row["next_retry_at"] or "")[:18])
        pdf.drawString(rq_col_x[6], y, str(row["created_at"] or "")[:18])
        pdf.drawString(rq_col_x[7], y, str(row["error_message"] or "")[:20])
        y -= 11
    if not rows:
        pdf.drawString(36, y, "Keine offenen Retry-Einträge.")
    pdf.save()
    buffer.seek(0)
    filename = f"invoice-retry-queue-{utc_now().strftime('%Y-%m-%d')}.pdf"
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/invoices/incidents/export.csv")
@require_auth
@require_roles("superadmin")
def export_invoice_incidents_csv():
    db = get_db()
    retry_rows = db.execute(
        """
        SELECT invoices.*, companies.name AS company_name
        FROM invoices
        JOIN companies ON companies.id = invoices.company_id
        WHERE invoices.status = 'send_failed' AND invoices.paid_at IS NULL
        ORDER BY COALESCE(invoices.next_retry_at, invoices.created_at) ASC
        """
    ).fetchall()
    dead_letter_rows = get_invoice_dead_letters(db)
    alert_rows = db.execute(
        "SELECT code, severity, message, created_at FROM system_alerts ORDER BY created_at DESC LIMIT 25"
    ).fetchall()
    metrics = get_invoice_ops_metrics(db)

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return jsonify({"error": "pdf_dependency_missing", "message": "Bitte reportlab installieren."}), 503

    buffer = io.BytesIO()
    pw, ph = landscape(A4)
    pdf = rl_canvas.Canvas(buffer, pagesize=landscape(A4))

    y = ph - 36
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(36, y, "BauPass - Rechnungs-Incident-Report")
    y -= 16
    pdf.setFont("Helvetica", 9)
    pdf.drawString(36, y, f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    y -= 20

    # Summary section
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(36, y, "Zusammenfassung")
    y -= 12
    pdf.setFont("Helvetica", 9)
    summary_items = [
        ("Kritische Fehlversände >24h", metrics.get("criticalOver24h", 0)),
        ("Ø Minuten bis erster Erfolg", metrics.get("avgFirstSuccessMinutes", 0)),
        ("Offene Retry-Fälle", len(retry_rows)),
        ("Offene Dead-Letter-Fälle", len(dead_letter_rows)),
        ("Offene System-Alerts", len(alert_rows)),
    ]
    for label, value in summary_items:
        pdf.drawString(36, y, f"{label}: {value}")
        y -= 12
    y -= 8

    # Retry queue section
    if retry_rows:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(36, y, f"Retry-Queue ({len(retry_rows)} Einträge)")
        y -= 12
        inc_col_x = [36, 120, 236, 356, 426, 496, 566]
        inc_headers = ["Rechnungs-Nr.", "Firma", "Email", "Betrag", "Versuche", "Nächster Retry", "Fehler"]
        pdf.setFont("Helvetica-Bold", 7)
        for i, h in enumerate(inc_headers):
            pdf.drawString(inc_col_x[i], y, h)
        y -= 8
        pdf.line(36, y, pw - 36, y)
        y -= 10
        pdf.setFont("Helvetica", 7)
        for row in retry_rows:
            if y < 48:
                pdf.showPage()
                y = ph - 36
            pdf.drawString(inc_col_x[0], y, str(row["invoice_number"] or "")[:16])
            pdf.drawString(inc_col_x[1], y, str(row["company_name"] or "")[:18])
            pdf.drawString(inc_col_x[2], y, str(row["recipient_email"] or "")[:28])
            pdf.drawString(inc_col_x[3], y, f"{float(row['total_amount'] or 0):.2f} €")
            pdf.drawString(inc_col_x[4], y, str(int(row["send_attempt_count"] or 0)))
            pdf.drawString(inc_col_x[5], y, str(row["next_retry_at"] or "")[:18])
            pdf.drawString(inc_col_x[6], y, str(row["error_message"] or "")[:22])
            y -= 11
        y -= 8

    # Dead letters section
    if dead_letter_rows:
        if y < 80:
            pdf.showPage()
            y = ph - 36
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(36, y, f"Dead Letters ({len(dead_letter_rows)} Einträge)")
        y -= 12
        dl_col_x = [36, 120, 236, 356, 426, 566]
        dl_headers = ["Rechnungs-Nr.", "Firma", "Email", "Betrag", "Grund", "Erstellt"]
        pdf.setFont("Helvetica-Bold", 7)
        for i, h in enumerate(dl_headers):
            pdf.drawString(dl_col_x[i], y, h)
        y -= 8
        pdf.line(36, y, pw - 36, y)
        y -= 10
        pdf.setFont("Helvetica", 7)
        for row in dead_letter_rows:
            if y < 48:
                pdf.showPage()
                y = ph - 36
            pdf.drawString(dl_col_x[0], y, str(row.get("invoice_number", "") or "")[:16])
            pdf.drawString(dl_col_x[1], y, str(row.get("company_name", "") or "")[:18])
            pdf.drawString(dl_col_x[2], y, str(row.get("recipient_email", "") or "")[:28])
            pdf.drawString(dl_col_x[3], y, f"{float(row.get('total_amount', 0) or 0):.2f} €")
            pdf.drawString(dl_col_x[4], y, str(row.get("reason", "") or "")[:22])
            pdf.drawString(dl_col_x[5], y, str(row.get("created_at", "") or "")[:18])
            y -= 11
        y -= 8

    # System alerts section
    if alert_rows:
        if y < 80:
            pdf.showPage()
            y = ph - 36
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(36, y, f"System-Alerts ({len(alert_rows)} Einträge)")
        y -= 12
        sa_col_x = [36, 160, 230, 500]
        sa_headers = ["Code", "Schweregrad", "Meldung", "Erstellt"]
        pdf.setFont("Helvetica-Bold", 7)
        for i, h in enumerate(sa_headers):
            pdf.drawString(sa_col_x[i], y, h)
        y -= 8
        pdf.line(36, y, pw - 36, y)
        y -= 10
        pdf.setFont("Helvetica", 7)
        for row in alert_rows:
            if y < 48:
                pdf.showPage()
                y = ph - 36
            pdf.drawString(sa_col_x[0], y, str(row["code"] or "")[:20])
            pdf.drawString(sa_col_x[1], y, str(row["severity"] or "")[:12])
            pdf.drawString(sa_col_x[2], y, str(row["message"] or "")[:52])
            pdf.drawString(sa_col_x[3], y, str(row["created_at"] or "")[:18])
            y -= 11

    if not retry_rows and not dead_letter_rows and not alert_rows:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(36, y, "Keine Vorfälle vorhanden.")

    pdf.save()
    buffer.seek(0)
    filename = f"invoice-incidents-{utc_now().strftime('%Y-%m-%d')}.pdf"
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.put("/api/invoices/<invoice_id>/pay")
@require_auth
@require_roles("superadmin")
def mark_invoice_paid(invoice_id):
    """Mark an invoice as paid, optionally lifting company suspension if all invoices are now paid."""
    payload = request.get_json(silent=True) or {}
    payment_date = (payload.get("paymentDate") or now_iso().split("T")[0]).strip()
    notes = (payload.get("notes") or "").strip()

    db = get_db()
    invoice = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice:
        return jsonify({"error": "invoice_not_found"}), 404

    # Permission check: verify company_id matches current user
    if g.current_user["role"] != "superadmin" and invoice["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_company"}), 403

    invoice_number = invoice["invoice_number"]
    company_id = invoice["company_id"]
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "company_not_found"}), 404

    # Mark as paid
    db.execute(
        "UPDATE invoices SET status = ?, paid_at = ?, last_reminder_error = '' WHERE id = ?",
        ("bezahlt", payment_date, invoice_id),
    )
    log_audit(
        "invoice.marked_paid",
        f"Rechnung {invoice_number} als bezahlt markiert",
        target_type="invoice",
        target_id=invoice_id,
        company_id=company_id,
        actor=g.current_user,
    )

    # Check if company should be unsuspended: all invoices are now either paid or cancelled
    remaining_overdue = db.execute(
        """
        SELECT COUNT(*) as count FROM invoices
        WHERE company_id = ? AND paid_at IS NULL AND auto_suspend_triggered_at IS NOT NULL
        """,
        (company_id,),
    ).fetchone()

    if remaining_overdue["count"] == 0 and company["status"] == "gesperrt":
        # Lift suspension if all auto-suspended invoices are now paid
        db.execute("UPDATE companies SET status = ? WHERE id = ?", ("aktiv", company_id))
        log_audit(
            "company.auto_unsuspended_invoices_paid",
            f"Firma '{company['name']}' Sperrung aufgehoben - alle Rechnungen bezahlt",
            target_type="company",
            target_id=company_id,
            actor=g.current_user,
        )

    db.commit()
    result = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    return jsonify({"invoice": row_to_dict(result)})


@app.get("/api/invoices/<invoice_id>/reminder-letter.pdf")
@require_auth
@require_roles("superadmin")
def invoice_reminder_letter_pdf(invoice_id):
    """Mahnungs-PDF fuer eine Rechnung generieren (Zahlungserinnerung / Mahnung)."""
    db = get_db()
    invoice = db.execute(
        """SELECT invoices.*, companies.name AS company_name, companies.contact AS company_contact,
                  companies.billing_email AS company_billing_email
           FROM invoices JOIN companies ON companies.id = invoices.company_id
           WHERE invoices.id = ?""",
        (invoice_id,),
    ).fetchone()
    if not invoice:
        return jsonify({"error": "invoice_not_found"}), 404

    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
    except Exception:
        return jsonify({"error": "pdf_dependency_missing", "message": "Bitte reportlab installieren."}), 503

    reminder_stage = int(invoice["reminder_stage"] or 0)
    # Determine dunning level labels
    if reminder_stage == 0:
        letter_type = "Zahlungserinnerung"
        deadline_days = 14
        warning_text = ""
    elif reminder_stage == 1:
        letter_type = "1. Mahnung"
        deadline_days = 10
        warning_text = "Bitte beachten Sie, dass bei Nichtzahlung weitere Mahnschritte folgen."
    elif reminder_stage == 2:
        letter_type = "2. Mahnung"
        deadline_days = 7
        warning_text = "Dies ist unsere zweite Zahlungsaufforderung. Wir behalten uns rechtliche Schritte vor."
    else:
        letter_type = "Letzte Mahnung vor rechtlichen Schritten"
        deadline_days = 5
        warning_text = "Wir werden ohne Zahlungseingang innerhalb der gesetzten Frist ein Inkassobüro beauftragen."

    new_due_date = (utc_now() + timedelta(days=deadline_days)).strftime("%d.%m.%Y")
    invoice_date_str = str(invoice["invoice_date"] or "")
    original_due_str = str(invoice["due_date"] or "")
    total_amount = float(invoice["total_amount"] or 0)

    operator_name = str(settings["operator_name"] or settings["platform_name"] or "BauPass").strip() if settings else "BauPass"
    operator_street = str(settings["invoice_operator_street"] or "").strip() if settings else ""
    operator_zip_city = str(settings["invoice_operator_zip_city"] or "").strip() if settings else ""
    operator_phone = str(settings["invoice_operator_phone"] or "").strip() if settings else ""
    operator_email = str(settings["invoice_operator_email"] or "").strip() if settings else ""
    primary_color = str(settings["invoice_primary_color"] or "#0f4c5c").strip() if settings else "#0f4c5c"

    def hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

    try:
        pr, pg, pb = hex_to_rgb(primary_color)
    except Exception:
        pr, pg, pb = 0.059, 0.298, 0.361

    buffer = io.BytesIO()
    page_width, page_height = A4
    pdf = rl_canvas.Canvas(buffer, pagesize=A4)

    # ── Header band ──
    pdf.setFillColorRGB(pr, pg, pb)
    pdf.rect(0, page_height - 50, page_width, 50, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(36, page_height - 30, letter_type.upper())
    pdf.setFont("Helvetica", 9)
    pdf.drawString(36, page_height - 44, operator_name)

    # ── Sender address block (small above recipient) ──
    y = page_height - 80
    pdf.setFillColorRGB(0.5, 0.5, 0.5)
    pdf.setFont("Helvetica", 7)
    sender_line = f"{operator_name}, {operator_street}, {operator_zip_city}".strip(", ")
    pdf.drawString(36, y, sender_line)

    # ── Recipient address block ──
    y -= 18
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(36, y, str(invoice["company_name"] or ""))
    if invoice["company_contact"]:
        y -= 14
        pdf.drawString(36, y, str(invoice["company_contact"] or ""))
    if invoice["company_billing_email"]:
        y -= 14
        pdf.setFont("Helvetica", 9)
        pdf.setFillColorRGB(0.4, 0.4, 0.4)
        pdf.drawString(36, y, str(invoice["company_billing_email"] or ""))
        pdf.setFillColorRGB(0.1, 0.1, 0.1)

    # ── Date / Ref block right-aligned ──
    ref_y = page_height - 98
    pdf.setFont("Helvetica", 9)
    pdf.setFillColorRGB(0.4, 0.4, 0.4)
    pdf.drawRightString(page_width - 36, ref_y, f"Datum: {datetime.now().strftime('%d.%m.%Y')}")
    ref_y -= 13
    pdf.drawRightString(page_width - 36, ref_y, f"Rechnungs-Nr.: {invoice['invoice_number']}")
    ref_y -= 13
    pdf.drawRightString(page_width - 36, ref_y, f"Urspr. Fälligkeit: {original_due_str}")

    # ── Subject line ──
    y = page_height - 200
    pdf.setFillColorRGB(pr, pg, pb)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(36, y, f"{letter_type}: Rechnung {invoice['invoice_number']}")
    y -= 18
    pdf.setFillColorRGB(0.1, 0.1, 0.1)

    # ── Body text ──
    pdf.setFont("Helvetica", 10)
    salutation = f"Sehr geehrte Damen und Herren,"
    pdf.drawString(36, y, salutation)
    y -= 18
    pdf.setFont("Helvetica", 9)
    body_lines = [
        f"für nachfolgend aufgeführte Rechnung haben wir bis heute keinen Zahlungseingang",
        f"verzeichnet. Wir bitten Sie, den ausstehenden Betrag bis zum {new_due_date} zu begleichen.",
    ]
    for line in body_lines:
        pdf.drawString(36, y, line)
        y -= 13

    # ── Invoice detail box ──
    y -= 8
    box_y = y - 58
    pdf.setFillColorRGB(0.97, 0.97, 0.97)
    pdf.rect(36, box_y, page_width - 72, 60, fill=1, stroke=0)
    pdf.setFillColorRGB(pr, pg, pb)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(44, box_y + 44, "Rechnungs-Nr.")
    pdf.drawString(160, box_y + 44, "Datum")
    pdf.drawString(240, box_y + 44, "Zeitraum")
    pdf.drawString(380, box_y + 44, "Betrag (brutto)")
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(44, box_y + 26, str(invoice["invoice_number"] or ""))
    pdf.drawString(160, box_y + 26, str(invoice_date_str)[:10])
    pdf.drawString(240, box_y + 26, str(invoice["invoice_period"] or "")[:22])
    pdf.drawString(380, box_y + 26, f"{total_amount:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."))
    y = box_y - 18

    if warning_text:
        pdf.setFillColorRGB(0.75, 0.1, 0.1)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(36, y, warning_text[:110])
        y -= 16
        pdf.setFillColorRGB(0.1, 0.1, 0.1)

    # ── Payment reference ──
    y -= 6
    pdf.setFont("Helvetica", 9)
    iban = str(settings["invoice_iban"] or "").strip() if settings else ""
    bic = str(settings["invoice_bic"] or "").strip() if settings else ""
    bank_name = str(settings["invoice_bank_name"] or "").strip() if settings else ""
    if iban:
        pdf.setFillColorRGB(0.4, 0.4, 0.4)
        pdf.drawString(36, y, f"Bitte überweisen Sie auf: IBAN {iban}" + (f" | BIC {bic}" if bic else "") + (f" ({bank_name})" if bank_name else ""))
        y -= 13
        pdf.drawString(36, y, f"Verwendungszweck: {invoice['invoice_number']}")
        y -= 13

    # ── Closing ──
    y -= 8
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(36, y, "Mit freundlichen Grüßen")
    y -= 14
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(36, y, operator_name)
    if operator_phone or operator_email:
        y -= 12
        pdf.setFont("Helvetica", 8)
        pdf.setFillColorRGB(0.4, 0.4, 0.4)
        contact_parts = []
        if operator_phone:
            contact_parts.append(f"Tel: {operator_phone}")
        if operator_email:
            contact_parts.append(f"E-Mail: {operator_email}")
        pdf.drawString(36, y, "  |  ".join(contact_parts))

    # ── Footer ──
    pdf.setFillColorRGB(pr, pg, pb)
    pdf.rect(0, 0, page_width, 24, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica", 7)
    footer_parts = [operator_name]
    if operator_street:
        footer_parts.append(operator_street)
    if operator_zip_city:
        footer_parts.append(operator_zip_city)
    pdf.drawString(36, 8, "  |  ".join(footer_parts)[:120])

    pdf.save()
    buffer.seek(0)

    stage_label = {0: "zahlungserinnerung", 1: "mahnung-1", 2: "mahnung-2"}.get(reminder_stage, "letzte-mahnung")
    filename = f"RE-{invoice['invoice_number']}-{stage_label}.pdf"
    log_audit(
        "invoice.reminder_letter_generated",
        f"Mahnungs-PDF fuer Rechnung {invoice['invoice_number']} (Stufe {reminder_stage}) erstellt",
        target_type="invoice",
        target_id=invoice_id,
        company_id=invoice["company_id"],
        actor=g.current_user,
    )
    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/documents/expiring")
@require_auth
@require_roles("superadmin", "company-admin")
def list_expiring_documents():
    """Ablaufende Dokumente in den naechsten N Tagen zurueckgeben."""
    db = get_db()
    user = g.current_user
    try:
        days = min(max(int(request.args.get("days", "30")), 1), 365)
    except (ValueError, TypeError):
        days = 30

    limit_date = (utc_now() + timedelta(days=days)).strftime("%Y-%m-%d")
    today = now_iso()[:10]

    if user["role"] == "superadmin":
        company_filter_sql = ""
        params = [today, limit_date]
    else:
        company_filter_sql = "AND w.company_id = ?"
        params = [today, limit_date, user["company_id"]]

    rows = db.execute(
        f"""
        SELECT wd.id AS doc_id, wd.doc_type, wd.expiry_date, wd.worker_id,
               w.first_name, w.last_name, w.badge_id, w.company_id,
               c.name AS company_name
        FROM worker_documents wd
        JOIN workers w ON w.id = wd.worker_id
        JOIN companies c ON c.id = w.company_id
        WHERE wd.expiry_date IS NOT NULL
          AND wd.expiry_date != ''
          AND wd.expiry_date >= ?
          AND wd.expiry_date <= ?
          AND w.deleted_at IS NULL
          {company_filter_sql}
        ORDER BY wd.expiry_date ASC
        LIMIT 500
        """,
        params,
    ).fetchall()

    result = []
    for row in rows:
        expiry = row["expiry_date"]
        try:
            days_left = (datetime.strptime(expiry, "%Y-%m-%d").date() - utc_now().date()).days
        except Exception:
            days_left = None

        if days_left is not None and days_left <= 7:
            urgency = "critical"
        elif days_left is not None and days_left <= 14:
            urgency = "warning"
        else:
            urgency = "info"

        result.append({
            "docId": row["doc_id"],
            "docType": row["doc_type"],
            "expiryDate": expiry,
            "daysLeft": days_left,
            "urgency": urgency,
            "workerId": row["worker_id"],
            "workerName": f"{row['first_name']} {row['last_name']}".strip(),
            "badgeId": row["badge_id"],
            "companyId": row["company_id"],
            "companyName": row["company_name"],
        })

    return jsonify({"count": len(result), "daysWindow": days, "items": result})


@app.get("/api/audit-logs")
@require_auth
@require_roles("superadmin", "company-admin")
def list_audit_logs():
    user = g.current_user
    db = get_db()
    event_type = (request.args.get("eventType") or "").strip()
    actor_role = (request.args.get("actorRole") or "").strip()
    target_type = (request.args.get("targetType") or "").strip()
    query_text = (request.args.get("q") or "").strip()
    from_date = (request.args.get("from") or request.args.get("dateFrom") or "").strip()
    to_date = (request.args.get("to") or request.args.get("dateTo") or "").strip()
    limit = min(max(int(request.args.get("limit", "300")), 1), 1000)
    offset = max(int(request.args.get("offset", "0")), 0)

    conditions = []
    params = []

    if user["role"] != "superadmin":
        conditions.append("(company_id = ? OR actor_user_id IN (SELECT id FROM users WHERE company_id = ?) OR company_id IS NULL)")
        params.extend([user["company_id"], user["company_id"]])

    if event_type:
        conditions.append("event_type LIKE ?")
        params.append(f"{event_type}%")

    if actor_role:
        conditions.append("actor_role = ?")
        params.append(actor_role)

    if target_type:
        conditions.append("target_type = ?")
        params.append(target_type)

    if query_text:
        conditions.append("(message LIKE ? OR event_type LIKE ? OR IFNULL(target_id, '') LIKE ?)")
        pattern = f"%{query_text}%"
        params.extend([pattern, pattern, pattern])

    if from_date:
        conditions.append("created_at >= ?")
        params.append(f"{from_date}T00:00:00Z")

    if to_date:
        conditions.append("created_at <= ?")
        params.append(f"{to_date}T23:59:59Z")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = db.execute(
        f"SELECT * FROM audit_logs {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    total = db.execute(f"SELECT COUNT(*) AS c FROM audit_logs {where_clause}", params).fetchone()["c"]

    return jsonify({
        "logs": [row_to_dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@app.get("/api/audit-logs/export.csv")
@require_auth
@require_roles("superadmin", "company-admin")
def export_audit_csv():
    user = g.current_user
    db = get_db()
    event_type = (request.args.get("eventType") or "").strip()
    actor_role = (request.args.get("actorRole") or "").strip()
    target_type = (request.args.get("targetType") or "").strip()
    query_text = (request.args.get("q") or "").strip()
    from_date = (request.args.get("from") or "").strip()
    to_date = (request.args.get("to") or "").strip()

    conditions = []
    params = []
    if user["role"] != "superadmin":
        conditions.append("(company_id = ? OR company_id IS NULL)")
        params.append(user["company_id"])
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if actor_role:
        conditions.append("actor_role = ?")
        params.append(actor_role)
    if target_type:
        conditions.append("target_type = ?")
        params.append(target_type)
    if query_text:
        conditions.append("(message LIKE ? OR event_type LIKE ? OR IFNULL(target_id, '') LIKE ?)")
        pattern = f"%{query_text}%"
        params.extend([pattern, pattern, pattern])
    if from_date:
        conditions.append("created_at >= ?")
        params.append(f"{from_date}T00:00:00Z")
    if to_date:
        conditions.append("created_at <= ?")
        params.append(f"{to_date}T23:59:59Z")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = db.execute(f"SELECT * FROM audit_logs {where_clause} ORDER BY created_at DESC LIMIT 2000", params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "event_type", "actor_user_id", "actor_role", "company_id", "target_type", "target_id", "message", "created_at"])
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["event_type"],
                row["actor_user_id"],
                row["actor_role"],
                row["company_id"],
                row["target_type"],
                row["target_id"],
                row["message"],
                row["created_at"],
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-logs.csv"},
    )


@app.get("/api/export")
@require_auth
def export_payload():
    db = get_db()
    user = g.current_user
    include_audit = request.args.get("includeAudit", "0") == "1"
    include_day_close = request.args.get("includeDayClose", "0") == "1"
    include_deleted = request.args.get("includeDeleted", "0") == "1"
    requested_company_id = (request.args.get("companyId") or "").strip()

    if user["role"] != "superadmin":
        requested_company_id = user.get("company_id") or ""

    settings = get_settings().json
    companies = list_companies().json
    subcompanies = list_subcompanies().json
    workers = list_workers().json
    logs = list_access_logs().json
    invoices = []
    if user["role"] == "superadmin":
        if requested_company_id:
            invoice_rows = db.execute(
                """
                SELECT invoices.*, companies.name AS company_name
                FROM invoices
                JOIN companies ON companies.id = invoices.company_id
                WHERE invoices.company_id = ?
                ORDER BY invoices.created_at DESC
                """,
                (requested_company_id,),
            ).fetchall()
            invoices = [row_to_dict(row) for row in invoice_rows]
        else:
            invoice_rows = db.execute(
                """
                SELECT invoices.*, companies.name AS company_name
                FROM invoices
                JOIN companies ON companies.id = invoices.company_id
                ORDER BY invoices.created_at DESC
                """
            ).fetchall()
            invoices = [row_to_dict(row) for row in invoice_rows]

    if include_deleted:
        if requested_company_id:
            worker_rows = db.execute(
                "SELECT * FROM workers WHERE company_id = ? ORDER BY last_name, first_name",
                (requested_company_id,),
            ).fetchall()
        elif user["role"] == "superadmin":
            worker_rows = db.execute("SELECT * FROM workers ORDER BY last_name, first_name").fetchall()
        else:
            worker_rows = db.execute(
                "SELECT * FROM workers WHERE company_id = ? ORDER BY last_name, first_name",
                (user.get("company_id"),),
            ).fetchall()
        workers = [serialize_worker_record(row) for row in worker_rows]

    if requested_company_id:
        companies = [item for item in companies if item.get("id") == requested_company_id]
        subcompanies = [item for item in subcompanies if item.get("companyId") == requested_company_id]
        workers = [item for item in workers if item.get("companyId") == requested_company_id]
        worker_ids = {item.get("id") for item in workers}
        logs = [item for item in logs if item.get("workerId") in worker_ids]
    elif not include_deleted:
        companies = [item for item in companies if not item.get("deleted_at")]
        workers = [item for item in workers if not item.get("deletedAt")]

    user = g.current_user
    users = [user]

    if user["role"] == "superadmin":
        rows = db.execute("SELECT * FROM users ORDER BY username").fetchall()
        users = [row_to_dict(row) for row in rows]
        if requested_company_id:
            users = [item for item in users if item.get("company_id") in [None, requested_company_id]]
    users = [
        {
            "id": item["id"],
            "username": item["username"],
            "name": item["name"],
            "role": item["role"],
            "company_id": item["company_id"],
            "twofa_enabled": int(item.get("twofa_enabled", 0)),
        }
        for item in users
    ]

    audit_logs = []
    if include_audit:
        if user["role"] == "superadmin" and not requested_company_id:
            audit_rows = db.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 5000").fetchall()
        else:
            scope_company_id = requested_company_id or user.get("company_id")
            audit_rows = db.execute(
                "SELECT * FROM audit_logs WHERE company_id = ? OR company_id IS NULL ORDER BY created_at DESC LIMIT 5000",
                (scope_company_id,),
            ).fetchall()
        audit_logs = [row_to_dict(row) for row in audit_rows]

    day_close_acknowledgements = []
    if include_day_close:
        if user["role"] == "superadmin" and not requested_company_id:
            ack_rows = db.execute("SELECT * FROM day_close_acknowledgements ORDER BY created_at DESC LIMIT 2000").fetchall()
        else:
            scope_company_id = requested_company_id or user.get("company_id")
            ack_rows = db.execute(
                "SELECT * FROM day_close_acknowledgements WHERE company_id = ? OR company_id IS NULL ORDER BY created_at DESC LIMIT 2000",
                (scope_company_id,),
            ).fetchall()
        day_close_acknowledgements = [row_to_dict(row) for row in ack_rows]

    export_scope = "company" if requested_company_id else ("system" if user["role"] == "superadmin" else "company")
    metadata = {
        "schemaVersion": "2026-04-export-v2",
        "scope": export_scope,
        "companyId": requested_company_id or user.get("company_id"),
        "generatedBy": {
            "id": user.get("id"),
            "username": user.get("username"),
            "role": user.get("role"),
        },
        "counts": {
            "companies": len(companies),
            "subcompanies": len(subcompanies),
            "workers": len(workers),
            "accessLogs": len(logs),
            "invoices": len(invoices),
            "users": len(users),
            "auditLogs": len(audit_logs),
            "dayCloseAcknowledgements": len(day_close_acknowledgements),
        },
        "options": {
            "includeAudit": include_audit,
            "includeDayClose": include_day_close,
            "includeDeleted": include_deleted,
        },
    }

    log_audit(
        "export.created",
        f"Export erstellt (scope={export_scope}, companies={len(companies)}, workers={len(workers)}, logs={len(logs)})",
        target_type="export",
        target_id=metadata["schemaVersion"],
        company_id=metadata["companyId"],
        actor=user,
    )

    return jsonify(
        {
            "meta": metadata,
            "settings": settings,
            "companies": companies,
            "subcompanies": subcompanies,
            "workers": workers,
            "accessLogs": logs,
            "invoices": invoices,
            "users": users,
            "auditLogs": audit_logs,
            "dayCloseAcknowledgements": day_close_acknowledgements,
            "exportedAt": now_iso(),
        }
    )


@app.post("/api/import")
@require_auth
@require_roles("superadmin", "company-admin")
@require_rate_limit("import")
def import_payload():
    payload = request.get_json(silent=True) or {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    dry_run = int(payload.get("dryRun", 1)) == 1
    import_only_changes = int(payload.get("importOnlyChanges", 0)) == 1

    if not isinstance(data, dict):
        return jsonify({"error": "invalid_payload"}), 400

    db = get_db()
    user = g.current_user
    role = user.get("role")
    target_company_id = user.get("company_id") if role != "superadmin" else (payload.get("companyId") or "")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    schema_version = str(meta.get("schemaVersion") or "").strip()
    if schema_version and not schema_version.startswith("2026-04-export-v2"):
        return jsonify({"error": "unsupported_schema_version", "message": f"Import-Version nicht unterstützt: {schema_version}"}), 400

    companies = data.get("companies") or []
    subcompanies = data.get("subcompanies") or []
    workers = data.get("workers") or []
    access_logs = data.get("accessLogs") or []
    invoices = data.get("invoices") or []

    summary = {
        "dryRun": dry_run,
        "schemaVersion": schema_version or "unknown",
        "importOnlyChanges": import_only_changes,
        "accepted": {"companies": 0, "subcompanies": 0, "workers": 0, "accessLogs": 0, "invoices": 0},
        "unchanged": {"companies": 0, "subcompanies": 0, "workers": 0, "accessLogs": 0, "invoices": 0},
        "skipped": {"forbidden": 0, "invalid": 0},
        "conflicts": {"companies": 0, "subcompanies": 0, "workers": 0, "accessLogs": 0, "invoices": 0},
    }

    def company_allowed(company_id):
        if role == "superadmin":
            return True if not target_company_id else str(company_id or "") == str(target_company_id)
        return str(company_id or "") == str(target_company_id or "")

    prepared_companies = []
    prepared_subcompanies = []
    prepared_workers = []
    prepared_access_logs = []
    prepared_invoices = []

    for item in companies:
        cid = item.get("id")
        if not cid:
            summary["skipped"]["invalid"] += 1
            continue
        if not company_allowed(cid):
            summary["skipped"]["forbidden"] += 1
            continue
        exists = db.execute("SELECT 1 FROM companies WHERE id = ?", (cid,)).fetchone()
        if exists:
            summary["conflicts"]["companies"] += 1
            if import_only_changes:
                current = db.execute(
                    "SELECT * FROM companies WHERE id = ?",
                    (cid,),
                ).fetchone()
                if current and current["name"] == item.get("name", "") and current["contact"] == item.get("contact", "") and current["billing_email"] == item.get("billing_email", item.get("billingEmail", "")) and current["document_email"] == item.get("document_email", item.get("documentEmail", "")) and current["access_host"] == item.get("access_host", item.get("accessHost", "")) and normalize_branding_preset(current["branding_preset"]) == normalize_branding_preset(item.get("branding_preset", item.get("brandingPreset"))) and normalize_company_plan(current["plan"]) == normalize_company_plan(item.get("plan")) and current["status"] == item.get("status", "aktiv"):
                    summary["unchanged"]["companies"] += 1
                    continue
        prepared_companies.append(
            (
                cid,
                item.get("name", ""),
                item.get("contact", ""),
                item.get("billing_email", item.get("billingEmail", "")),
                item.get("document_email", item.get("documentEmail", "")),
                item.get("access_host", item.get("accessHost", "")),
                normalize_branding_preset(item.get("branding_preset", item.get("brandingPreset"))),
                normalize_company_plan(item.get("plan")),
                item.get("status", "aktiv"),
                item.get("deleted_at", item.get("deletedAt")),
            )
        )

    for item in subcompanies:
        sid = item.get("id")
        cid = item.get("company_id", item.get("companyId"))
        if not sid or not cid:
            summary["skipped"]["invalid"] += 1
            continue
        if not company_allowed(cid):
            summary["skipped"]["forbidden"] += 1
            continue
        exists = db.execute("SELECT 1 FROM subcompanies WHERE id = ?", (sid,)).fetchone()
        if exists:
            summary["conflicts"]["subcompanies"] += 1
            if import_only_changes:
                current = db.execute("SELECT * FROM subcompanies WHERE id = ?", (sid,)).fetchone()
                if current and current["company_id"] == cid and current["name"] == item.get("name", "") and current["contact"] == item.get("contact", "") and current["status"] == item.get("status", "aktiv"):
                    summary["unchanged"]["subcompanies"] += 1
                    continue
        prepared_subcompanies.append(
            (
                sid,
                cid,
                item.get("name", ""),
                item.get("contact", ""),
                item.get("status", "aktiv"),
                item.get("deleted_at", item.get("deletedAt")),
            )
        )

    for item in workers:
        wid = item.get("id")
        cid = item.get("company_id", item.get("companyId"))
        if not wid or not cid:
            summary["skipped"]["invalid"] += 1
            continue
        if not company_allowed(cid):
            summary["skipped"]["forbidden"] += 1
            continue
        exists = db.execute("SELECT 1 FROM workers WHERE id = ?", (wid,)).fetchone()
        if exists:
            summary["conflicts"]["workers"] += 1
            if import_only_changes:
                current = db.execute("SELECT * FROM workers WHERE id = ?", (wid,)).fetchone()
                if current and current["company_id"] == cid and (current["subcompany_id"] or "") == (item.get("subcompany_id", item.get("subcompanyId")) or "") and current["first_name"] == item.get("first_name", item.get("firstName", "")) and current["last_name"] == item.get("last_name", item.get("lastName", "")) and current["insurance_number"] == item.get("insurance_number", item.get("insuranceNumber", "")) and normalize_worker_type(current["worker_type"]) == normalize_worker_type(item.get("worker_type", item.get("workerType"))) and current["role"] == item.get("role", "") and current["site"] == item.get("site", "") and current["valid_until"] == item.get("valid_until", item.get("validUntil", "")) and (current["visitor_company"] or "") == (item.get("visitor_company", item.get("visitorCompany", "")) or "") and (current["visit_purpose"] or "") == (item.get("visit_purpose", item.get("visitPurpose", "")) or "") and (current["host_name"] or "") == (item.get("host_name", item.get("hostName", "")) or "") and (current["visit_end_at"] or "") == (item.get("visit_end_at", item.get("visitEndAt", "")) or "") and current["status"] == item.get("status", "aktiv") and (current["badge_id"] or "") == (item.get("badge_id", item.get("badgeId", "")) or ""):
                    summary["unchanged"]["workers"] += 1
                    continue
        prepared_workers.append(
            (
                wid,
                cid,
                item.get("subcompany_id", item.get("subcompanyId")),
                item.get("first_name", item.get("firstName", "")),
                item.get("last_name", item.get("lastName", "")),
                item.get("insurance_number", item.get("insuranceNumber", "")),
                normalize_worker_type(item.get("worker_type", item.get("workerType"))),
                item.get("role", ""),
                item.get("site", ""),
                item.get("valid_until", item.get("validUntil", "")),
                item.get("visitor_company", item.get("visitorCompany", "")),
                item.get("visit_purpose", item.get("visitPurpose", "")),
                item.get("host_name", item.get("hostName", "")),
                item.get("visit_end_at", item.get("visitEndAt", "")),
                item.get("status", "aktiv"),
                item.get("photo_data", item.get("photoData", "")),
                item.get("badge_id", item.get("badgeId", "")),
                "",
                item.get("physical_card_id", item.get("physicalCardId")),
                item.get("deleted_at", item.get("deletedAt")),
            )
        )

    known_worker_ids = {row[0] for row in prepared_workers}
    if not dry_run:
        existing_worker_rows = db.execute("SELECT id, company_id FROM workers").fetchall()
        for row in existing_worker_rows:
            if company_allowed(row["company_id"]):
                known_worker_ids.add(row["id"])

    for item in access_logs:
        lid = item.get("id")
        worker_id = item.get("worker_id", item.get("workerId"))
        if not lid or not worker_id:
            summary["skipped"]["invalid"] += 1
            continue
        if worker_id not in known_worker_ids:
            summary["skipped"]["invalid"] += 1
            continue
        exists = db.execute("SELECT 1 FROM access_logs WHERE id = ?", (lid,)).fetchone()
        if exists:
            summary["conflicts"]["accessLogs"] += 1
            if import_only_changes:
                current = db.execute("SELECT * FROM access_logs WHERE id = ?", (lid,)).fetchone()
                if current and current["worker_id"] == worker_id and current["direction"] == item.get("direction", "check-in") and current["gate"] == item.get("gate", "") and current["note"] == item.get("note", "") and current["timestamp"] == item.get("timestamp", now_iso()):
                    summary["unchanged"]["accessLogs"] += 1
                    continue
        prepared_access_logs.append(
            (
                lid,
                worker_id,
                item.get("direction", "check-in"),
                item.get("gate", ""),
                item.get("note", ""),
                item.get("timestamp", now_iso()),
            )
        )

    for item in invoices:
        if role != "superadmin":
            summary["skipped"]["forbidden"] += 1
            continue
        iid = item.get("id")
        cid = item.get("company_id", item.get("companyId"))
        if not iid or not cid:
            summary["skipped"]["invalid"] += 1
            continue
        if not company_allowed(cid):
            summary["skipped"]["forbidden"] += 1
            continue
        exists = db.execute("SELECT 1 FROM invoices WHERE id = ?", (iid,)).fetchone()
        if exists:
            summary["conflicts"]["invoices"] += 1
            if import_only_changes:
                current = db.execute("SELECT * FROM invoices WHERE id = ?", (iid,)).fetchone()
                if current and current["company_id"] == cid and current["invoice_number"] == item.get("invoice_number", item.get("invoiceNumber", "")) and current["recipient_email"] == item.get("recipient_email", item.get("recipientEmail", "")) and current["invoice_date"] == item.get("invoice_date", item.get("invoiceDate", "")) and current["invoice_period"] == item.get("invoice_period", item.get("invoicePeriod", "")) and current["description"] == item.get("description", "") and float(current["total_amount"] or 0) == float(item.get("total_amount", item.get("totalAmount", 0)) or 0) and current["status"] == item.get("status", "draft"):
                    summary["unchanged"]["invoices"] += 1
                    continue
        prepared_invoices.append(
            (
                iid,
                item.get("invoice_number", item.get("invoiceNumber", "")),
                cid,
                item.get("recipient_email", item.get("recipientEmail", "")),
                item.get("invoice_date", item.get("invoiceDate", "")),
                item.get("invoice_period", item.get("invoicePeriod", "")),
                item.get("description", ""),
                float(item.get("net_amount", item.get("netAmount", 0)) or 0),
                float(item.get("vat_rate", item.get("vatRate", 0)) or 0),
                float(item.get("vat_amount", item.get("vatAmount", 0)) or 0),
                float(item.get("total_amount", item.get("totalAmount", 0)) or 0),
                item.get("status", "draft"),
                item.get("error_message", item.get("errorMessage", "")),
                item.get("sent_at", item.get("sentAt")),
                item.get("rendered_html", item.get("renderedHtml", "<html><body>Imported invoice</body></html>")),
                user.get("id"),
                item.get("created_at", item.get("createdAt", now_iso())),
                item.get("due_date", item.get("dueDate")),
                item.get("paid_at", item.get("paidAt")),
                item.get("auto_suspend_triggered_at", item.get("autoSuspendTriggeredAt")),
                int(item.get("reminder_stage", item.get("reminderStage", 0)) or 0),
                item.get("last_reminder_sent_at", item.get("lastReminderSentAt")),
                item.get("last_reminder_error", item.get("lastReminderError", "")),
            )
        )

    summary["accepted"]["companies"] = len(prepared_companies)
    summary["accepted"]["subcompanies"] = len(prepared_subcompanies)
    summary["accepted"]["workers"] = len(prepared_workers)
    summary["accepted"]["accessLogs"] = len(prepared_access_logs)
    summary["accepted"]["invoices"] = len(prepared_invoices)

    if dry_run:
        return jsonify({"ok": True, "summary": summary})

    backup_path = create_import_rollback_backup(db, role, target_company_id)

    if role == "superadmin":
        db.executemany(
            "INSERT OR REPLACE INTO companies (id, name, contact, billing_email, document_email, access_host, branding_preset, plan, status, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            prepared_companies,
        )

    db.executemany(
        "INSERT OR REPLACE INTO subcompanies (id, company_id, name, contact, status, deleted_at) VALUES (?, ?, ?, ?, ?, ?)",
        prepared_subcompanies,
    )
    db.executemany(
        """
        INSERT OR REPLACE INTO workers (
            id, company_id, subcompany_id, first_name, last_name, insurance_number, worker_type, role, site, valid_until,
            visitor_company, visit_purpose, host_name, visit_end_at, status, photo_data, badge_id, badge_pin_hash, physical_card_id, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        prepared_workers,
    )
    db.executemany(
        "INSERT OR REPLACE INTO access_logs (id, worker_id, direction, gate, note, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        prepared_access_logs,
    )
    db.executemany(
        """
        INSERT OR REPLACE INTO invoices (
            id, invoice_number, company_id, recipient_email, invoice_date, invoice_period, description,
            net_amount, vat_rate, vat_amount, total_amount, status, error_message, sent_at,
            rendered_html, created_by_user_id, created_at, due_date, paid_at,
            auto_suspend_triggered_at, reminder_stage, last_reminder_sent_at, last_reminder_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        prepared_invoices,
    )
    db.commit()

    log_audit(
        "import.applied",
        f"Import ausgefuehrt (companies={summary['accepted']['companies']}, workers={summary['accepted']['workers']}, logs={summary['accepted']['accessLogs']}, invoices={summary['accepted']['invoices']}, backup={backup_path})",
        target_type="import",
        target_id=now_iso(),
        company_id=target_company_id,
        actor=user,
    )

    return jsonify({"ok": True, "summary": summary, "backupPath": backup_path})


@app.get("/api/health")
def api_health():
    db_ok = True
    db_error = ""
    try:
        with closing(sqlite3.connect(DB_PATH)) as db:
            db.execute("SELECT 1").fetchone()
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    uptime_seconds = int((utc_now() - APP_STARTED_AT).total_seconds())
    diagnostics = get_runtime_diagnostics()
    status = "ok" if db_ok else "degraded"

    alerts = []
    try:
        with closing(sqlite3.connect(DB_PATH)) as alerts_db:
            alerts_db.row_factory = sqlite3.Row
            alert_rows = alerts_db.execute(
                "SELECT * FROM system_alerts ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            alerts = [row_to_dict(row) for row in alert_rows]
    except Exception:
        alerts = []

    if not db_ok:
        try:
            db = get_db()
            create_system_alert(db, "health_db_down", "critical", "Health-Check: Datenbank nicht erreichbar.", {"error": db_error})
        except Exception:
            pass
    elif diagnostics.get("warnings"):
        try:
            db = get_db()
            create_system_alert(
                db,
                "health_runtime_warnings",
                "warning",
                f"Health-Check meldet {len(diagnostics.get('warnings', []))} Warnungen.",
                diagnostics.get("warnings", []),
                dedup_minutes=60,
            )
        except Exception:
            pass

    return jsonify(
        {
            "status": status,
            "uptimeSeconds": uptime_seconds,
            "startedAt": APP_STARTED_AT.replace(microsecond=0).isoformat() + "Z",
            "db": {"ok": db_ok, "error": db_error},
            "dunning": {
                "lastRunAt": DUNNING_LAST_RUN_AT,
                "lastResult": DUNNING_LAST_RESULT,
                "intervalHours": max(1, int(os.getenv("BAUPASS_DUNNING_INTERVAL_HOURS", "24"))),
            },
            "warnings": diagnostics.get("warnings", []),
            "alerts": alerts,
        }
    ), (200 if db_ok else 503)


@app.get("/api/health/live")
def api_health_live():
    return jsonify({"status": "alive", "startedAt": APP_STARTED_AT.replace(microsecond=0).isoformat() + "Z"})


@app.get("/api/health/ready")
def api_health_ready():
    try:
        with closing(sqlite3.connect(DB_PATH)) as db:
            db.execute("SELECT 1").fetchone()
        return jsonify({"status": "ready"}), 200
    except Exception as exc:
        return jsonify({"status": "not_ready", "error": str(exc)}), 503


@app.get("/api/system-alerts")
@require_auth
@require_roles("superadmin", "company-admin")
def list_system_alerts():
    limit = min(max(int(request.args.get("limit", "100")), 1), 500)
    severity = (request.args.get("severity") or "").strip().lower()

    conditions = []
    params = []
    if severity:
        conditions.append("severity = ?")
        params.append(severity)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = get_db().execute(
        f"SELECT * FROM system_alerts {where_clause} ORDER BY created_at DESC LIMIT ?",
        [*params, limit],
    ).fetchall()

    return jsonify([row_to_dict(row) for row in rows])


# ─────────────────────────────────────────────────────────────────
# DOKUMENTE-POSTFACH: IMAP-Polling + API
# ─────────────────────────────────────────────────────────────────

ALLOWED_DOC_TYPES = {
    "mindestlohnnachweis",
    "personalausweis",
    "sozialversicherungsnachweis",
    "arbeitserlaubnis",
    "gesundheitszeugnis",
    "sonstiges",
}

ALLOWED_UPLOAD_MIMETYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

DOCS_UPLOAD_DIR = BASE_DIR / "backend" / "uploads" / "documents"


def _parse_imap_attachment_limit_bytes() -> int:
    raw = os.getenv("BAUPASS_IMAP_MAX_ATTACHMENT_MB", "15")
    try:
        mb = max(1, int(raw))
    except (TypeError, ValueError):
        mb = 15
    return mb * 1024 * 1024


MAX_IMAP_ATTACHMENT_BYTES = _parse_imap_attachment_limit_bytes()


def _decode_mime_header(value) -> str:
    if value is None:
        return ""
    text = str(value)
    try:
        from email.header import decode_header

        parts = []
        for chunk, encoding in decode_header(text):
            if isinstance(chunk, bytes):
                parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
            else:
                parts.append(str(chunk))
        return "".join(parts).strip()
    except Exception:
        return text.strip()


def _sanitize_attachment_filename(filename: str) -> str:
    decoded = _decode_mime_header(filename)
    cleaned = clean_text_input(decoded, max_len=220)
    cleaned = cleaned.replace("\\", "_").replace("/", "_").replace(":", "_")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = re.sub(r"[^A-Za-z0-9._()\- ]", "_", cleaned)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = "anhang.bin"
    if cleaned.startswith("."):
        cleaned = f"file{cleaned}"
    if "." not in Path(cleaned).name:
        cleaned = f"{cleaned}.bin"
    return cleaned[:180]


def _stored_file_path(file_path: Path) -> str:
    resolved = file_path.resolve()
    try:
        return str(resolved.relative_to(BASE_DIR))
    except ValueError:
        return str(resolved)


def get_imap_settings(db):
    row = db.execute(
        "SELECT imap_host, imap_port, imap_username, imap_password, imap_folder, imap_use_ssl FROM settings WHERE id = 1"
    ).fetchone()
    if not row:
        return None
    return dict(row)


def poll_imap_inbox():
    """Pollt das konfigurierte IMAP-Postfach und speichert neue Mails in email_inbox."""
    import imaplib
    import email as _email
    import email.policy as _email_policy

    try:
        with app.app_context():
            db = get_db()
            cfg = get_imap_settings(db)
            if not cfg or not cfg.get("imap_host") or not cfg.get("imap_username"):
                return  # IMAP nicht konfiguriert

            host = cfg["imap_host"]
            port = int(cfg.get("imap_port") or 993)
            username = cfg["imap_username"]
            password = cfg["imap_password"] or ""
            folder = cfg.get("imap_folder") or "INBOX"
            use_ssl = bool(cfg.get("imap_use_ssl", 1))

            try:
                if use_ssl:
                    conn = imaplib.IMAP4_SSL(host, port)
                else:
                    conn = imaplib.IMAP4(host, port)
                    conn.starttls()
                conn.login(username, password)
            except Exception as exc:
                with app.app_context():
                    inner_db = get_db()
                    create_system_alert(
                        inner_db,
                        code="imap_connect_failed",
                        severity="warning",
                        message="IMAP-Verbindung fehlgeschlagen.",
                        details={"error": str(exc)},
                    )
                    inner_db.commit()
                return

            conn.select(folder, readonly=False)
            # Alle Mails im Ordner berücksichtigen. Deduplizierung passiert über
            # message_id bzw. IMAP UID-Fallback in der DB.
            status, data = conn.search(None, "ALL")
            if status != "OK":
                conn.logout()
                return

            msg_ids = (data[0] or b"").split()
            for num in msg_ids:
                status, msg_data = conn.fetch(num, "(RFC822)")
                if status != "OK":
                    continue
                raw = msg_data[0][1] if msg_data and msg_data[0] else None
                if not raw:
                    continue

                msg = _email.message_from_bytes(raw, policy=_email_policy.compat32)

                # Stabile Fallback-ID aus IMAP UID, falls Message-ID fehlt.
                imap_uid = ""
                try:
                    uid_status, uid_data = conn.fetch(num, "(UID)")
                    if uid_status == "OK" and uid_data and uid_data[0]:
                        uid_chunk = uid_data[0][0] if isinstance(uid_data[0], tuple) else uid_data[0]
                        uid_bytes = uid_chunk if isinstance(uid_chunk, (bytes, bytearray)) else str(uid_chunk).encode("utf-8", errors="ignore")
                        uid_match = re.search(rb"UID\s+(\d+)", uid_bytes)
                        if uid_match:
                            imap_uid = uid_match.group(1).decode("ascii", errors="ignore")
                except Exception:
                    imap_uid = ""

                message_id = str(msg.get("Message-ID") or "").strip()
                if not message_id and imap_uid:
                    message_id = f"imap-uid:{imap_uid}"
                from_addr = _decode_mime_header(msg.get("From") or "")
                to_addr = extract_message_recipient_address(msg)
                subject = _decode_mime_header(msg.get("Subject") or "")
                received_at = now_iso()
                matched_company = find_company_by_document_email(db, to_addr)
                matched_company_id = matched_company["id"] if matched_company else None

                # Doppelten Einlese-Schutz via message_id
                if message_id:
                    existing = db.execute(
                        "SELECT id FROM email_inbox WHERE message_id = ?", (message_id,)
                    ).fetchone()
                    if existing:
                        continue

                body_text = ""
                attachments_data = []

                skipped_oversized = 0
                for part in msg.walk():
                    if part.is_multipart():
                        continue
                    ctype = part.get_content_type()
                    disposition = str(part.get_content_disposition() or "").lower()
                    filename_header = part.get_filename()

                    if ctype == "text/plain" and disposition != "attachment" and not filename_header:
                        try:
                            payload_text = part.get_payload(decode=True)
                            if payload_text:
                                charset = part.get_content_charset() or "utf-8"
                                body_text = payload_text.decode(charset, errors="replace")
                        except Exception:
                            body_text = ""
                    elif filename_header or disposition == "attachment":
                        filename = _sanitize_attachment_filename(filename_header or "anhang.bin")
                        payload = part.get_payload(decode=True)
                        if payload:
                            if len(payload) > MAX_IMAP_ATTACHMENT_BYTES:
                                skipped_oversized += 1
                                continue
                            attachments_data.append({
                                "filename": filename,
                                "content_type": ctype or "application/octet-stream",
                                "file_size": len(payload),
                                "file_data": payload,
                            })

                inbox_id = f"inb-{secrets.token_hex(8)}"
                db.execute(
                    "INSERT INTO email_inbox (id, message_id, from_addr, to_addr, subject, body_text, matched_company_id, received_at) VALUES (?,?,?,?,?,?,?,?)",
                    (inbox_id, message_id, from_addr, to_addr, subject, body_text[:2000], matched_company_id, received_at),
                )

                for att in attachments_data:
                    att_id = f"att-{secrets.token_hex(8)}"
                    db.execute(
                        "INSERT INTO email_attachments (id, inbox_id, filename, content_type, file_size, file_data) VALUES (?,?,?,?,?,?)",
                        (att_id, inbox_id, att["filename"], att["content_type"], att["file_size"], att["file_data"]),
                    )

                if skipped_oversized > 0:
                    create_system_alert(
                        db,
                        code="imap_attachment_too_large",
                        severity="warning",
                        message="Ein oder mehrere Mail-Anhänge wurden wegen Größenlimit verworfen.",
                        details={"messageId": message_id, "skipped": skipped_oversized, "maxBytes": MAX_IMAP_ATTACHMENT_BYTES},
                    )

                # Mail als gelesen markieren
                conn.store(num, "+FLAGS", "\\Seen")

            db.commit()
            conn.logout()
    except Exception as exc:
        try:
            with app.app_context():
                inner_db = get_db()
                create_system_alert(
                    inner_db,
                    code="imap_poll_error",
                    severity="warning",
                    message="IMAP-Postfach-Abruf fehlgeschlagen.",
                    details={"error": str(exc)},
                )
                inner_db.commit()
        except Exception:
            pass


# IMAP-Polling in Background-Jobs einhängen
_orig_start_background_jobs = start_background_jobs


def start_background_jobs_with_imap():
    _orig_start_background_jobs()
    imap_poll_interval = max(60, int(os.getenv("BAUPASS_IMAP_POLL_SECONDS", "180")))

    def imap_loop():
        time.sleep(10)  # kurz nach Start warten
        while True:
            try:
                poll_imap_inbox()
            except Exception:
                pass
            time.sleep(imap_poll_interval)

    threading.Thread(target=imap_loop, name="baupass-imap-poller", daemon=True).start()


# start_background_jobs wurde oben bereits aufgerufen – IMAP-Thread separat starten
_imap_poll_interval = max(60, int(os.getenv("BAUPASS_IMAP_POLL_SECONDS", "180")))

def _start_imap_thread():
    def imap_loop():
        time.sleep(10)
        while True:
            try:
                poll_imap_inbox()
            except Exception:
                pass
            time.sleep(_imap_poll_interval)
    threading.Thread(target=imap_loop, name="baupass-imap-poller", daemon=True).start()


# ── Dokumente-Inbox API ──────────────────────────────────────────

@app.post("/api/documents/imap/trigger")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def trigger_imap_poll():
    """Manueller IMAP-Abruf auf Anforderung."""
    try:
        poll_imap_inbox()
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/documents/inbox")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def list_document_inbox():
    db = get_db()
    if g.current_user["role"] == "superadmin":
        rows = db.execute(
            "SELECT * FROM email_inbox WHERE dismissed = 0 ORDER BY received_at DESC LIMIT 100"
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM email_inbox WHERE dismissed = 0 AND matched_company_id = ? ORDER BY received_at DESC LIMIT 100",
            (g.current_user.get("company_id"),),
        ).fetchall()

    result = []
    for row in rows:
        inbox_id = row["id"]
        attachments = db.execute(
            "SELECT id, filename, content_type, file_size, assigned_worker_id, assigned_doc_type, saved_path FROM email_attachments WHERE inbox_id = ?",
            (inbox_id,),
        ).fetchall()
        entry = dict(row)
        entry["attachments"] = [dict(a) for a in attachments]
        if row["matched_company_id"]:
            company = db.execute(
                "SELECT id, name, document_email FROM companies WHERE id = ?",
                (row["matched_company_id"],),
            ).fetchone()
            if company:
                entry["matched_company_name"] = company["name"]
                entry["matched_company_document_email"] = company["document_email"]
        result.append(entry)

    return jsonify(result)


@app.post("/api/documents/inbox/<inbox_id>/dismiss")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def dismiss_inbox_email(inbox_id):
    db = get_db()
    db.execute("UPDATE email_inbox SET dismissed = 1 WHERE id = ?", (inbox_id,))
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/documents/inbox/<inbox_id>/attachments/<attachment_id>/assign")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def assign_attachment_to_worker(inbox_id, attachment_id):
    """Hängt einen E-Mail-Anhang an einen Mitarbeiter und speichert die Datei."""
    payload = request.get_json(silent=True) or {}
    worker_id = clean_text_input(payload.get("workerId", ""), max_len=64)
    doc_type = clean_text_input(payload.get("docType", ""), max_len=64).lower()
    notes = clean_text_input(payload.get("notes", ""), max_len=500)

    if not worker_id:
        return jsonify({"error": "missing_worker_id"}), 400
    if doc_type not in ALLOWED_DOC_TYPES:
        return jsonify({"error": "invalid_doc_type", "allowed": sorted(ALLOWED_DOC_TYPES)}), 400

    db = get_db()
    inbox_row = db.execute("SELECT * FROM email_inbox WHERE id = ?", (inbox_id,)).fetchone()
    if not inbox_row:
        return jsonify({"error": "inbox_not_found"}), 404

    att = db.execute(
        "SELECT * FROM email_attachments WHERE id = ? AND inbox_id = ?", (attachment_id, inbox_id)
    ).fetchone()
    if not att:
        return jsonify({"error": "attachment_not_found"}), 404

    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404
    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    # Datei auf Filesystem speichern
    base_upload_root = DOCS_UPLOAD_DIR.resolve()
    worker_doc_dir = (DOCS_UPLOAD_DIR / worker_id).resolve()
    if worker_doc_dir != base_upload_root and base_upload_root not in worker_doc_dir.parents:
        return jsonify({"error": "invalid_storage_path"}), 400
    try:
        worker_doc_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return jsonify({"error": "storage_error", "detail": str(exc)}), 500

    ts = utc_now().strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitize_attachment_filename(att["filename"] or "anhang.bin")
    file_path = (worker_doc_dir / f"{doc_type}_{ts}_{safe_name}").resolve()
    if worker_doc_dir not in file_path.parents:
        return jsonify({"error": "invalid_target_path"}), 400

    file_data = att["file_data"]
    if not file_data:
        return jsonify({"error": "attachment_no_data"}), 400

    if isinstance(file_data, memoryview):
        file_data = file_data.tobytes()
    elif isinstance(file_data, bytearray):
        file_data = bytes(file_data)
    elif isinstance(file_data, str):
        file_data = file_data.encode("utf-8", errors="replace")
    else:
        file_data = bytes(file_data)

    if len(file_data) > MAX_IMAP_ATTACHMENT_BYTES:
        return jsonify({"error": "attachment_too_large", "maxBytes": MAX_IMAP_ATTACHMENT_BYTES}), 400

    try:
        file_path.write_bytes(file_data)
    except Exception as exc:
        return jsonify({"error": "write_error", "detail": str(exc)}), 500

    stored_path = _stored_file_path(file_path)

    doc_id = f"doc-{secrets.token_hex(8)}"
    db.execute(
        """INSERT INTO worker_documents
           (id, worker_id, company_id, doc_type, filename, file_path, file_size, source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_id,
            worker_id,
            worker["company_id"],
            doc_type,
            safe_name,
            stored_path,
            len(file_data),
            inbox_row["from_addr"],
            inbox_id,
            g.current_user["id"],
            now_iso(),
            notes,
        ),
    )

    # Anhang als zugewiesen markieren
    db.execute(
        "UPDATE email_attachments SET assigned_worker_id = ?, assigned_doc_type = ?, saved_path = ? WHERE id = ?",
        (worker_id, doc_type, stored_path, attachment_id),
    )

    # Wenn alle Anhänge dieser Mail zugewiesen sind → Mail als processed markieren
    unassigned = db.execute(
        "SELECT id FROM email_attachments WHERE inbox_id = ? AND assigned_worker_id IS NULL",
        (inbox_id,),
    ).fetchone()
    if not unassigned:
        db.execute("UPDATE email_inbox SET processed = 1 WHERE id = ?", (inbox_id,))

    unlock_worker_if_documents_valid(db, worker, actor=g.current_user)

    db.commit()

    log_audit(
        "worker.document_added",
        f"Dokument '{doc_type}' ({att['filename']}) von {inbox_row['from_addr']} wurde Mitarbeiter {worker['badge_id']} zugewiesen",
        target_type="worker",
        target_id=worker_id,
        company_id=worker["company_id"],
        actor=g.current_user,
    )
    return jsonify({"ok": True, "documentId": doc_id})


# ── Mitarbeiter-Dokumente API ────────────────────────────────────

@app.get("/api/workers/<worker_id>/documents")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def list_worker_documents(worker_id):
    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404
    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    rows = db.execute(
        "SELECT id, doc_type, filename, file_size, source_email_from, created_at, notes, expiry_date FROM worker_documents WHERE worker_id = ? ORDER BY created_at DESC",
        (worker_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/workers/<worker_id>/documents/upload")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def upload_worker_document(worker_id):
    """Direkt-Upload eines Dokuments vom PC für einen Mitarbeiter."""
    doc_type = clean_text_input(request.form.get("docType", ""), max_len=64).lower()
    notes = clean_text_input(request.form.get("notes", ""), max_len=500)
    expiry_date = clean_text_input(request.form.get("expiryDate", ""), max_len=10) or None
    if expiry_date:
        try:
            datetime.strptime(expiry_date, "%Y-%m-%d")
        except ValueError:
            expiry_date = None

    if doc_type not in ALLOWED_DOC_TYPES:
        return jsonify({"error": "invalid_doc_type", "allowed": sorted(ALLOWED_DOC_TYPES)}), 400

    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        return jsonify({"error": "missing_file"}), 400

    mime = (uploaded_file.mimetype or "").lower().split(";")[0].strip()
    if mime not in ALLOWED_UPLOAD_MIMETYPES:
        return jsonify({"error": "invalid_file_type"}), 400

    file_data = uploaded_file.read()
    if len(file_data) > MAX_IMAP_ATTACHMENT_BYTES:
        return jsonify({"error": "file_too_large", "maxBytes": MAX_IMAP_ATTACHMENT_BYTES}), 400

    safe_name = _sanitize_attachment_filename(uploaded_file.filename)

    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404
    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    base_upload_root = DOCS_UPLOAD_DIR.resolve()
    worker_doc_dir = (DOCS_UPLOAD_DIR / worker_id).resolve()
    if worker_doc_dir != base_upload_root and base_upload_root not in worker_doc_dir.parents:
        return jsonify({"error": "invalid_storage_path"}), 400
    try:
        worker_doc_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return jsonify({"error": "storage_error", "detail": str(exc)}), 500

    ts = utc_now().strftime("%Y%m%d_%H%M%S")
    file_path = (worker_doc_dir / f"{doc_type}_{ts}_{safe_name}").resolve()
    if worker_doc_dir not in file_path.parents:
        return jsonify({"error": "invalid_target_path"}), 400

    try:
        file_path.write_bytes(file_data)
    except Exception as exc:
        return jsonify({"error": "write_error", "detail": str(exc)}), 500

    stored_path = _stored_file_path(file_path)
    doc_id = f"doc-{secrets.token_hex(8)}"
    db.execute(
        """INSERT INTO worker_documents
           (id, worker_id, company_id, doc_type, filename, file_path, file_size, source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes, expiry_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_id, worker_id, worker["company_id"], doc_type, safe_name,
            stored_path, len(file_data), "", None,
            g.current_user["id"], now_iso(), notes, expiry_date,
        ),
    )
    unlock_worker_if_documents_valid(db, worker, actor=g.current_user)
    db.commit()

    log_audit(
        "worker.document_uploaded",
        f"Dokument '{doc_type}' ({safe_name}) direkt hochgeladen für Mitarbeiter {worker['badge_id']}",
        target_type="worker", target_id=worker_id,
        company_id=worker["company_id"], actor=g.current_user,
    )
    return jsonify({"ok": True, "documentId": doc_id})


@app.get("/api/workers/<worker_id>/documents/<doc_id>/download")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def download_worker_document(worker_id, doc_id):
    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404
    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    doc = db.execute(
        "SELECT * FROM worker_documents WHERE id = ? AND worker_id = ?", (doc_id, worker_id)
    ).fetchone()
    if not doc:
        return jsonify({"error": "document_not_found"}), 404

    file_path = BASE_DIR / doc["file_path"]
    if not file_path.exists():
        return jsonify({"error": "file_not_found"}), 404

    from flask import send_file
    return send_file(str(file_path), as_attachment=True, download_name=doc["filename"])


@app.delete("/api/workers/<worker_id>/documents/<doc_id>")
@require_auth
@require_roles("superadmin", "company-admin")
def delete_worker_document(worker_id, doc_id):
    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404
    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    doc = db.execute(
        "SELECT * FROM worker_documents WHERE id = ? AND worker_id = ?", (doc_id, worker_id)
    ).fetchone()
    if not doc:
        return jsonify({"error": "document_not_found"}), 404

    file_path = BASE_DIR / doc["file_path"]
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass

    db.execute("DELETE FROM worker_documents WHERE id = ?", (doc_id,))
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/settings/otp-test")
@require_auth
@require_roles("superadmin")
def otp_test_send():
    """Send a test OTP email to a specific email address to verify OTP delivery works."""
    db = get_db()
    payload = request.get_json(silent=True) or {}
    target_email = (payload.get("email") or "").strip()
    if not target_email or "@" not in target_email:
        return jsonify({"ok": False, "error": "invalid_email"}), 400
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    smtp_settings = _resolve_smtp_settings(settings, payload)
    missing_fields = []
    if not smtp_settings["smtp_host"]:
        missing_fields.append("smtpHost")
    if not smtp_settings["smtp_sender_email"]:
        missing_fields.append("smtpSenderEmail")
    if missing_fields:
        return jsonify({"ok": False, "error": "smtp_not_configured", "missingFields": missing_fields}), 400
    test_code = "123456"
    # Use a fake user_row with the target email
    class _FakeUser:
        def keys(self):
            return ["email", "username"]
        def __getitem__(self, k):
            return target_email if k == "email" else "test-otp"
        def get(self, k, default=""):
            return target_email if k == "email" else ("test-otp" if k == "username" else default)
    sent = _send_otp_email_to_user(db, _FakeUser(), test_code, smtp_settings_override=payload)
    if sent:
        return jsonify({"ok": True, "recipient": target_email})
    diag_result = _run_smtp_diagnostics(smtp_settings)
    if not diag_result.get("ok"):
        app.logger.error(
            f"[OTP-TEST-DIAG] stage={diag_result.get('stage')} type={diag_result.get('errorType')} error={diag_result.get('error')}"
        )
    resend_api_key, resend_key_source = _get_resend_api_key_and_source()
    brevo_api_key = _get_brevo_api_key()
    resend_configured = bool(resend_api_key)
    brevo_configured = bool(brevo_api_key)
    api_fallback_configured = resend_configured or brevo_configured
    detail_text = "SMTP delivery failed. Check server logs for [OTP-MAIL]."
    fallback_error = ""
    if diag_result.get("stage") == "connect" and "Network is unreachable" in str(diag_result.get("error") or ""):
        if api_fallback_configured:
            detail_text = "SMTP egress blocked on Railway. API fallback is configured; check [OTP-MAIL] logs for provider errors."
            fallback_error = "resend_configured_but_send_failed"
        else:
            detail_text = (
                "SMTP egress blocked on Railway and no API fallback key was found. "
                "Configure Brevo API key in settings (recommended) or RESEND_API_KEY for HTTPS fallback."
            )
            fallback_error = "resend_not_configured"
    return jsonify({
        "ok": False,
        "error": "otp_send_failed",
        "detail": detail_text,
        "diagnostics": diag_result,
        "fallbackError": fallback_error,
        "resendConfigured": resend_configured,
        "resendKeySource": resend_key_source,
        "brevoConfigured": brevo_configured,
        "resendEnv": _collect_resend_env_presence(),
    })


# IMAP-Settings GET/PATCH (in allgemeine Settings integriert)
# Wird über /api/settings mit den übrigen Feldern gespeichert.
# Zusätzliches Endpoint um IMAP zu testen:
@app.post("/api/settings/imap/test")
@require_auth
@require_roles("superadmin")
def test_imap_connection():
    import imaplib
    payload = request.get_json(silent=True) or {}
    db = get_db()
    stored = get_imap_settings(db) or {}

    host = clean_text_input(payload.get("imapHost", stored.get("imap_host", "")), max_len=255)
    port = int(payload.get("imapPort") or stored.get("imap_port") or 993)
    username = clean_text_input(payload.get("imapUsername", stored.get("imap_username", "")), max_len=255)
    password = str(payload.get("imapPassword") or stored.get("imap_password") or "")
    use_ssl = bool(payload.get("imapUseSsl", stored.get("imap_use_ssl", 1)))
    folder = clean_text_input(payload.get("imapFolder", stored.get("imap_folder", "INBOX")), max_len=100) or "INBOX"

    if not host or not username or not password:
        return jsonify({"error": "missing_fields"}), 400
    try:
        if use_ssl:
            conn = imaplib.IMAP4_SSL(host, port)
        else:
            conn = imaplib.IMAP4(host, port)
            conn.starttls()
        conn.login(username, password)
        status, _ = conn.select(folder, readonly=True)
        conn.logout()
        if status != "OK":
            return jsonify({"ok": False, "error": f"Ordner '{folder}' nicht gefunden."}), 200
        return jsonify({"ok": True, "message": f"Verbindung zu {host} erfolgreich."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 200


@app.get("/")
def root():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/worker.html")
def worker_entry_redirect():
    return send_from_directory(BASE_DIR, "worker.html")


def _load_invoice_logo_data_url():
    try:
        with closing(sqlite3.connect(DB_PATH)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT invoice_logo_data FROM settings WHERE id = 1").fetchone()
    except Exception:
        return ""
    if not row:
        return ""
    return (row["invoice_logo_data"] or "").strip()


def _build_worker_icon_svg(icon_size: int) -> str:
    _ = html  # keep import used in this module without removing broader helpers.
    return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{icon_size}\" height=\"{icon_size}\" viewBox=\"0 0 512 512\">\n  <defs>\n    <linearGradient id=\"bg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">\n      <stop offset=\"0%\" stop-color=\"#c78652\" />\n      <stop offset=\"100%\" stop-color=\"#8a5230\" />\n    </linearGradient>\n  </defs>\n  <rect width=\"512\" height=\"512\" rx=\"118\" fill=\"url(#bg)\" />\n  <text x=\"256\" y=\"330\" text-anchor=\"middle\" font-family=\"'Segoe UI', Arial, sans-serif\" font-size=\"192\" font-weight=\"800\" letter-spacing=\"4\" fill=\"#f6efe2\">BP</text>\n</svg>"""


@app.get("/worker-icon-<int:icon_size>.svg")
def worker_icon_svg(icon_size: int):
    if icon_size not in (192, 512):
        return jsonify({"error": "not_found"}), 404
    svg = _build_worker_icon_svg(icon_size)
    response = Response(svg.encode("utf-8"), mimetype="image/svg+xml")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.get("/worker-icon-<int:icon_size>.png")
def worker_icon_png(icon_size: int):
    if icon_size not in (192, 512):
        return jsonify({"error": "not_found"}), 404

    data = _generate_icon_png(icon_size)
    if not data:
        return jsonify({"error": "icon_generation_failed"}), 500
    response = Response(data, mimetype="image/png")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@app.get("/<path:path>")
def static_proxy(path):
    target = BASE_DIR / path
    if target.exists() and target.is_file():
        return send_from_directory(BASE_DIR, path)
    return jsonify({"error": "not_found"}), 404


start_background_jobs()
_start_imap_thread()


# ── Hardware-Geraete (Watchdog / OSDP Smart-Box) ─────────────────────────────

DEVICE_ONLINE_THRESHOLD_SECONDS = 90  # Geraet gilt als offline wenn > 90s kein Heartbeat


def _serialize_device(row, now_value=None):
    last_seen = str(row["last_seen_at"] or "")
    online = False
    if last_seen:
        try:
            last_ts = (parse_iso_utc(last_seen) or datetime.now(timezone.utc)).replace(tzinfo=timezone.utc)
            delta = (datetime.now(timezone.utc) - last_ts).total_seconds()
            online = delta <= DEVICE_ONLINE_THRESHOLD_SECONDS
        except Exception:
            pass
    return {
        "id": row["id"],
        "companyId": row["company_id"],
        "name": row["name"],
        "location": row["location"],
        "deviceType": row["device_type"],
        "lastSeenAt": last_seen,
        "online": online,
        "createdAt": row["created_at"],
    }


@app.get("/api/admin/devices")
@require_auth
@require_roles("superadmin", "company-admin")
def list_devices():
    db = get_db()
    company_id = g.current_user.get("company_id") if g.current_user.get("role") != "superadmin" else None
    if company_id:
        rows = db.execute("SELECT * FROM devices WHERE company_id = ? ORDER BY name", (company_id,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM devices ORDER BY company_id, name").fetchall()
    return jsonify({"devices": [_serialize_device(r) for r in rows]})


@app.post("/api/admin/devices")
@require_auth
@require_roles("superadmin", "company-admin")
def create_device():
    payload = request.get_json(silent=True) or {}
    db = get_db()
    name = clean_text_input(payload.get("name", ""), max_len=80)
    if not name:
        return jsonify({"error": "name_required"}), 400
    location = clean_text_input(payload.get("location", ""), max_len=120)
    device_type = clean_text_input(payload.get("deviceType", "osdp"), max_len=32) or "osdp"
    company_id = g.current_user.get("company_id") or clean_text_input(payload.get("companyId", ""), max_len=64) or None
    raw_key = secrets.token_urlsafe(32)
    key_hash = generate_password_hash(raw_key)
    device_id = f"dev-{secrets.token_hex(6)}"
    db.execute(
        "INSERT INTO devices (id, company_id, name, location, device_type, api_key_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (device_id, company_id, name, location, device_type, key_hash, now_iso()),
    )
    db.commit()
    log_audit("device.created", f"Geraet '{name}' ({device_type}) angelegt", target_type="device", target_id=device_id, company_id=company_id, actor=g.current_user)
    return jsonify({"ok": True, "device": {"id": device_id, "name": name, "location": location, "deviceType": device_type, "apiKey": raw_key, "online": False}})


@app.delete("/api/admin/devices/<device_id>")
@require_auth
@require_roles("superadmin", "company-admin")
def delete_device(device_id):
    db = get_db()
    device = db.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if not device:
        return jsonify({"error": "device_not_found"}), 404
    if g.current_user.get("role") != "superadmin" and device["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden"}), 403
    db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    db.commit()
    log_audit("device.deleted", f"Geraet '{device['name']}' geloescht", target_type="device", target_id=device_id, company_id=device["company_id"], actor=g.current_user)
    return jsonify({"ok": True})


@app.post("/api/device/heartbeat")
def device_heartbeat():
    """OSDP Smart-Box ruft diesen Endpoint regelmaessig auf um Online-Status zu signalisieren."""
    raw_key = (request.headers.get("X-Device-API-Key") or "").strip()
    if not raw_key:
        return jsonify({"error": "api_key_required"}), 401
    db = get_db()
    devices = db.execute("SELECT * FROM devices").fetchall()
    matched = None
    for dev in devices:
        if dev["api_key_hash"] and check_password_hash(dev["api_key_hash"], raw_key):
            matched = dev
            break
    if not matched:
        return jsonify({"error": "invalid_api_key"}), 401
    db.execute("UPDATE devices SET last_seen_at = ? WHERE id = ?", (now_iso(), matched["id"]))
    db.commit()
    return jsonify({"ok": True, "device": matched["name"], "ts": now_iso()})


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    ssl_context = get_ssl_context_from_env()
    app.run(host=host, port=port, ssl_context=ssl_context)