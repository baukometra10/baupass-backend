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
import textwrap
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
ACCESS_VISITOR_AUTOCLOSE_INTERVAL_SECONDS = 30
_access_maintenance_lock = threading.Lock()
_access_maintenance_state = {
    "last_visitor_close_monotonic": 0.0,
    "last_midnight_close_date": "",
}

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
    return f"Mitarbeiterausweis für User {id}"

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
    "starter": 149.0,
    "professional": 999.0,
    "enterprise": 2490.0,
}

# Monatliche Zusatzgebuehr pro aktivem Mitarbeiter (0.0 = alle inkludiert).
PLAN_WORKER_PRICE_EUR = {
    "tageskarte": 0.0,
    "starter": 0.0,
    "professional": 2.50,
    "enterprise": 3.00,
}

# Anzahl Mitarbeiter, die im Basispreis enthalten sind (0 = kein Freikontigent).
PLAN_WORKER_FREE_INCLUDED = {
    "tageskarte": 0,
    "starter": 0,
    "professional": 10,
    "enterprise": 10,
}

# ── Plan-Feature-Matrix ────────────────────────────────────────────────────
# Definiert welche Features ab welcher Plan-Stufe verfuegbar sind.
# Rangfolge: tageskarte < starter < professional < enterprise
PLAN_RANK = {"tageskarte": 0, "starter": 1, "professional": 2, "enterprise": 3}

PLAN_FEATURES = {
    # Feature-Key: minimale Plan-Stufe
    "access_logging":        "tageskarte",   # Basis: Ein-/Auslass-Protokoll
    "worker_management":     "tageskarte",   # Basis: Mitarbeiterverwaltung
    "qr_badges":             "tageskarte",   # Basis: QR-Badges
    "worker_app":            "starter",      # Mitarbeiter-App (Mobile Pass)
    "nfc_badges":            "starter",      # NFC-Karten
    "leave_management":      "starter",      # Urlaubs-/Fehlerzeit-Antraege
    "document_upload":       "starter",      # Dokument-Upload
    "invoicing":             "professional", # Rechnungsstellung
    "email_notifications":   "professional", # E-Mail-Benachrichtigungen
    "worker_hours_report":   "professional", # Arbeitsstunden-Bericht
    "late_checkin_alert":    "professional", # Zu-spaet-Meldung
    "subcompanies":          "professional", # Subunternehmen
    "white_label":           "enterprise",   # White-Label (eigenes Branding)
    "api_access":            "enterprise",   # API-Zugriff
    "multi_site":            "enterprise",   # Mehrere Standorte
    "premium_support":       "enterprise",   # Priority-Support
    "custom_pricing":        "enterprise",   # Individuelle Preisgestaltung
}


def company_has_feature(plan_value, feature_key):
    """Gibt True zurueck wenn der Plan-Level das Feature einschliesst."""
    plan = str(plan_value or "starter").strip().lower()
    if plan not in PLAN_RANK:
        plan = "starter"
    required_plan = PLAN_FEATURES.get(feature_key, "enterprise")
    return PLAN_RANK.get(plan, 1) >= PLAN_RANK.get(required_plan, 3)


def get_plan_features(plan_value):
    """Gibt alle verfuegbaren Features fuer einen Plan zurueck."""
    return {k: company_has_feature(plan_value, k) for k in PLAN_FEATURES}


def get_company_plan(db, company_id):
    """Liest den normalisierten Plan einer Firma."""
    if not company_id:
        return "starter"
    row = db.execute("SELECT plan FROM companies WHERE id = ? AND deleted_at IS NULL", (company_id,)).fetchone()
    if not row:
        return "starter"
    return normalize_company_plan(row["plan"])


def feature_not_available_response(feature_key, plan_value):
    """Standardisierte Antwort wenn ein Paket-Feature nicht verfuegbar ist."""
    return jsonify({
        "error": "feature_not_available",
        "feature": feature_key,
        "plan": normalize_company_plan(plan_value),
        "requiredPlan": PLAN_FEATURES.get(feature_key, "enterprise"),
    }), 403

DEFAULT_PLATFORM_NAME = "BauPass"
DEFAULT_OPERATOR_NAME = "Baukometra"

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
        g.db = sqlite3.connect(DB_PATH, timeout=60)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA synchronous=NORMAL")
        g.db.execute("PRAGMA busy_timeout=60000")
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


def run_db_write_with_retry(write_callable, attempts=5, base_delay_seconds=0.15):
    """Retry short SQLite write collisions (database is locked) with backoff."""
    for attempt in range(attempts):
        try:
            return write_callable()
        except sqlite3.OperationalError as exc:
            is_locked = "database is locked" in str(exc).lower()
            if not is_locked or attempt >= attempts - 1:
                raise
            time.sleep(base_delay_seconds * (attempt + 1))


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


def run_access_maintenance_if_due(db, reference_dt=None):
    now_dt = reference_dt or datetime.now(timezone.utc)
    today = now_dt.date().isoformat()
    now_monotonic = time.monotonic()
    run_visitor_autoclose = False
    run_midnight_close = False

    with _access_maintenance_lock:
        last_visitor_close = float(_access_maintenance_state.get("last_visitor_close_monotonic") or 0.0)
        if now_monotonic - last_visitor_close >= ACCESS_VISITOR_AUTOCLOSE_INTERVAL_SECONDS:
            _access_maintenance_state["last_visitor_close_monotonic"] = now_monotonic
            run_visitor_autoclose = True

        if _access_maintenance_state.get("last_midnight_close_date") != today:
            _access_maintenance_state["last_midnight_close_date"] = today
            run_midnight_close = True

    if run_visitor_autoclose:
        auto_close_expired_visitor_entries(db, reference_dt=now_dt)
    if run_midnight_close:
        auto_close_open_entries_after_midnight(db, reference_dt=now_dt)


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


_last_session_purge_ts: float = 0.0

def purge_expired_worker_app_sessions(db, now_value=None):
    timestamp = now_value or now_iso()
    result = db.execute("DELETE FROM worker_app_sessions WHERE expires_at < ?", (timestamp,))
    return int(result.rowcount or 0)

def _throttled_session_purge(db):
    """Purge abgelaufene Sessions höchstens 1x pro Minute (verhindert DB-Write-Lock bei parallelen Requests)."""
    global _last_session_purge_ts
    import time as _time
    now = _time.monotonic()
    if now - _last_session_purge_ts < 60:
        return 0
    _last_session_purge_ts = now
    return purge_expired_worker_app_sessions(db)


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
    imap_username = ""

    row = settings_row
    if row is None:
        try:
            row = get_db().execute("SELECT imap_username FROM settings WHERE id = 1").fetchone()
        except Exception:
            row = None

    if row and hasattr(row, "keys") and "imap_username" in row.keys():
        imap_username = row["imap_username"] or ""

    # Fallback auf zusammengeführte IMAP-Config (DB + ENV), damit Auto-Alias
    # auch auf Plattformen mit ENV-only IMAP-Konfiguration funktioniert.
    if "@" not in str(imap_username or ""):
        try:
            cfg = get_imap_settings(get_db())
            imap_username = cfg.get("imap_username") or imap_username
        except Exception:
            pass

    imap_username = normalize_email_address(imap_username)
    if "@" not in imap_username:
        return ""

    local_part, domain = imap_username.split("@", 1)
    alias_base = (local_part.split("+", 1)[0] or "dokumente").strip() or "dokumente"
    return f"{alias_base}+{slugify_company_alias(company_name)}@{domain}"


def extract_message_recipient_addresses(msg):
    candidates = []
    seen = set()
    for header_name in (
        "Delivered-To",
        "X-Original-To",
        "Envelope-To",
        "X-Envelope-To",
        "X-Forwarded-To",
        "To",
        "Cc",
        "Resent-To",
    ):
        header_value = msg.get(header_name)
        if not header_value:
            continue
        for _, email_addr in getaddresses([header_value]):
            normalized = normalize_email_address(email_addr)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(normalized)
    return candidates


def extract_message_recipient_address(msg):
    recipients = extract_message_recipient_addresses(msg)
    return recipients[0] if recipients else ""


def find_company_by_document_email(db, email_address):
    normalized = normalize_email_address(email_address)
    if not normalized:
        return None
    return db.execute(
        "SELECT * FROM companies WHERE lower(document_email) = ? AND deleted_at IS NULL",
        (normalized,),
    ).fetchone()


def find_company_by_recipient_headers(db, msg):
    """Fallback-Matching über komplette Empfänger-Header bei ungewöhnlichen Mailformaten."""
    header_chunks = []
    for header_name in (
        "Delivered-To",
        "X-Original-To",
        "Envelope-To",
        "X-Envelope-To",
        "X-Forwarded-To",
        "To",
        "Cc",
        "Resent-To",
    ):
        for header_value in msg.get_all(header_name, []):
            normalized = normalize_email_address(header_value)
            if normalized:
                header_chunks.append(normalized)

    if not header_chunks:
        return None, ""

    header_blob = " ".join(header_chunks)
    rows = db.execute(
        "SELECT * FROM companies WHERE deleted_at IS NULL AND COALESCE(document_email, '') <> ''"
    ).fetchall()

    # Längere Adressen zuerst prüfen, damit keine Teilstring-Fehlzuordnung passiert.
    companies = sorted(rows, key=lambda row: len(normalize_email_address(row["document_email"] or "")), reverse=True)
    for company in companies:
        document_email = normalize_email_address(company["document_email"] or "")
        if not document_email:
            continue
        if document_email in header_blob:
            return company, document_email

    return None, ""


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


def calculate_net_amount_by_plan(company_plan, payload_net_amount, worker_count=0):
    # Keep manual values from UI, but provide a predictable fallback for tariff-based billing.
    explicit_net = float(payload_net_amount or 0)
    if explicit_net > 0:
        return round(explicit_net, 2)
    normalized_plan = normalize_company_plan(company_plan)
    base = PLAN_NET_PRICE_EUR[normalized_plan]
    free_included = PLAN_WORKER_FREE_INCLUDED.get(normalized_plan, 0)
    billable_workers = max(0, int(worker_count or 0) - free_included)
    worker_fee = PLAN_WORKER_PRICE_EUR.get(normalized_plan, 0.0) * billable_workers
    return round(base + worker_fee, 2)


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
    try:
        session = db.execute(
            "SELECT user_id, expires_at, support_read_only, support_company_name, support_actor_name, preview_company_id FROM sessions WHERE token = ?",
            (token_value,),
        ).fetchone()
    except sqlite3.OperationalError:
        # Backward compatibility for containers that still have an older sessions schema.
        session = db.execute(
            "SELECT user_id, expires_at FROM sessions WHERE token = ?",
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
    session_keys = set(session.keys()) if hasattr(session, "keys") else set()
    payload = row_to_dict(user)
    payload["support_read_only"] = bool(session["support_read_only"]) if "support_read_only" in session_keys else False
    payload["support_company_name"] = session["support_company_name"] if "support_company_name" in session_keys and session["support_company_name"] else ""
    payload["support_actor_name"] = session["support_actor_name"] if "support_actor_name" in session_keys and session["support_actor_name"] else ""
    payload["preview_company_id"] = session["preview_company_id"] if "preview_company_id" in session_keys and session["preview_company_id"] else ""
    return payload


def render_login_page():
    db = get_db()
    settings_row = db.execute("SELECT invoice_logo_data, platform_name, operator_name, turnstile_endpoint FROM settings WHERE id = 1").fetchone()
    logo_src = ""
    platform_name = DEFAULT_PLATFORM_NAME
    operator_name = DEFAULT_OPERATOR_NAME
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
    db = sqlite3.connect(DB_PATH, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=60000")
    cur = db.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            platform_name TEXT NOT NULL,
            operator_name TEXT NOT NULL,
            turnstile_endpoint TEXT NOT NULL,
            rental_model TEXT NOT NULL,
            monthly_invoice_auto_enabled INTEGER NOT NULL DEFAULT 1,
            monthly_invoice_run_day INTEGER NOT NULL DEFAULT 1,
            monthly_invoice_due_days INTEGER NOT NULL DEFAULT 14,
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
            smtp_sender_name TEXT NOT NULL DEFAULT 'BauPass',
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
            customer_number TEXT NOT NULL DEFAULT '',
            contact TEXT NOT NULL,
            billing_email TEXT NOT NULL DEFAULT '',
            document_email TEXT NOT NULL DEFAULT '',
            access_host TEXT NOT NULL DEFAULT '',
            work_start_time TEXT NOT NULL DEFAULT '',
            work_end_time TEXT NOT NULL DEFAULT '',
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
            badge_id_lookup TEXT NOT NULL DEFAULT '',
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

    cur.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_worker_timestamp ON access_logs(worker_id, timestamp DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_worker_documents_worker_type_created ON worker_documents(worker_id, doc_type, created_at DESC)")

    setting_exists = cur.execute("SELECT id FROM settings WHERE id = 1").fetchone()
    if not setting_exists:
        cur.execute(
            """
            INSERT INTO settings (
                id, platform_name, operator_name, turnstile_endpoint, rental_model,
                monthly_invoice_auto_enabled, monthly_invoice_run_day, monthly_invoice_due_days,
                invoice_logo_data, invoice_primary_color, invoice_accent_color,
                invoice_iban, invoice_bic, invoice_bank_name, invoice_tax_id, invoice_vat_id,
                invoice_operator_street, invoice_operator_zip_city, invoice_operator_phone, invoice_operator_website,
                smtp_host, smtp_port, smtp_username, smtp_password, smtp_sender_email, smtp_sender_name, smtp_use_tls,
                resend_api_key, resend_from_email, brevo_api_key, brevo_from_email,
                admin_ip_whitelist, enforce_tenant_domain
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (DEFAULT_PLATFORM_NAME, DEFAULT_OPERATOR_NAME, "", "tageskarte", 1, 1, 14, "", "#0f4c5c", "#e36414", "", "", "", "", "", "", "", "", "", "", 587, "", "", "", DEFAULT_PLATFORM_NAME, 1, "", "", "", "", "", 0),
        )

    settings_columns = [row[1] for row in cur.execute("PRAGMA table_info(settings)").fetchall()]
    if "invoice_logo_data" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_logo_data TEXT NOT NULL DEFAULT ''")
    if "monthly_invoice_auto_enabled" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN monthly_invoice_auto_enabled INTEGER NOT NULL DEFAULT 1")
    if "monthly_invoice_run_day" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN monthly_invoice_run_day INTEGER NOT NULL DEFAULT 1")
    if "monthly_invoice_due_days" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN monthly_invoice_due_days INTEGER NOT NULL DEFAULT 14")
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
        cur.execute(f"ALTER TABLE settings ADD COLUMN smtp_sender_name TEXT NOT NULL DEFAULT '{DEFAULT_PLATFORM_NAME}'")
    if "smtp_use_tls" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN smtp_use_tls INTEGER NOT NULL DEFAULT 1")
    if "admin_ip_whitelist" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN admin_ip_whitelist TEXT NOT NULL DEFAULT ''")
    if "enforce_tenant_domain" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN enforce_tenant_domain INTEGER NOT NULL DEFAULT 0")
    cur.execute(
        "UPDATE settings SET platform_name = ? WHERE id = 1 AND COALESCE(TRIM(platform_name), '') IN ('', 'BauPass Control', 'Control Pass')",
        (DEFAULT_PLATFORM_NAME,),
    )
    cur.execute(
        "UPDATE settings SET operator_name = ? WHERE id = 1 AND COALESCE(TRIM(operator_name), '') IN ('', 'Deine Betriebsfirma', 'Deine Firma', 'Your company', 'BauPass', 'BauPass Control', 'Control Pass')",
        (DEFAULT_OPERATOR_NAME,),
    )
    cur.execute(
        "UPDATE settings SET smtp_sender_name = ? WHERE id = 1 AND COALESCE(TRIM(smtp_sender_name), '') IN ('', 'BauPass Control', 'Control Pass', 'BauPass')",
        (DEFAULT_OPERATOR_NAME,),
    )

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
    if "work_start_time" not in company_columns:
        cur.execute("ALTER TABLE companies ADD COLUMN work_start_time TEXT NOT NULL DEFAULT ''")
    if "work_end_time" not in company_columns:
        cur.execute("ALTER TABLE companies ADD COLUMN work_end_time TEXT NOT NULL DEFAULT ''")
    if "branding_preset" not in company_columns:
        cur.execute("ALTER TABLE companies ADD COLUMN branding_preset TEXT NOT NULL DEFAULT 'construction'")
    if "customer_number" not in company_columns:
        cur.execute("ALTER TABLE companies ADD COLUMN customer_number TEXT NOT NULL DEFAULT ''")

    # Migrate customer numbers to KU-YY-NNNN format (e.g. KU-26-0105).
    # Rows that are empty or still in old numeric-only format need a new number.
    _ku_yy = datetime.now().strftime("%y")
    _ku_prefix = f"KU-{_ku_yy}-"
    _rows_to_assign = cur.execute(
        "SELECT id FROM companies WHERE COALESCE(customer_number,'') = '' "
        "OR (customer_number GLOB '[0-9]*') ORDER BY name, id"
    ).fetchall()
    if _rows_to_assign:
        _last_seq_row = cur.execute(
            "SELECT customer_number FROM companies WHERE customer_number LIKE ? ORDER BY customer_number DESC LIMIT 1",
            (_ku_prefix + "%",),
        ).fetchone()
        _next_seq = 0
        if _last_seq_row:
            _parts = str(_last_seq_row[0]).split("-")
            if len(_parts) == 3 and _parts[2].isdigit():
                _next_seq = int(_parts[2])
        for _row in _rows_to_assign:
            _next_seq += 1
            cur.execute(
                "UPDATE companies SET customer_number = ? WHERE id = ?",
                (f"KU-{_ku_yy}-{_next_seq:04d}", _row[0]),
            )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_customer_number_unique ON companies(customer_number) WHERE COALESCE(customer_number, '') != ''"
    )

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
    if "badge_id_lookup" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN badge_id_lookup TEXT NOT NULL DEFAULT ''")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_workers_badge_lookup_active ON workers(badge_id_lookup, deleted_at)")
    if "badge_pin_hash" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN badge_pin_hash TEXT NOT NULL DEFAULT ''")
    if "physical_card_id" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN physical_card_id TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_workers_physical_card_active ON workers(physical_card_id, deleted_at)")
    if "site_latitude" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN site_latitude REAL")
    if "site_longitude" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN site_longitude REAL")

    worker_badge_rows = cur.execute("SELECT id, badge_id, badge_id_lookup FROM workers").fetchall()
    for row in worker_badge_rows:
        _raw = str(row[1] or "").strip().upper()
        _raw = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", _raw)
        _raw = re.sub(r"\s+", "", _raw)
        normalized_badge_lookup = _raw
        if (row[2] or "") != normalized_badge_lookup:
            cur.execute("UPDATE workers SET badge_id_lookup = ? WHERE id = ?", (normalized_badge_lookup, row[0]))

    if "worker_app_enabled" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN worker_app_enabled INTEGER NOT NULL DEFAULT 1")
    if "worker_pass_lock_enabled" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN worker_pass_lock_enabled INTEGER NOT NULL DEFAULT 0")
    if "contact_email" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN contact_email TEXT NOT NULL DEFAULT ''")
    if "leave_balance" not in worker_columns:
        cur.execute("ALTER TABLE workers ADD COLUMN leave_balance INTEGER NOT NULL DEFAULT 30")

    # ── Urlaubstage-Zaehler in leave_requests ────────────────────
    # Bei frischen DBs kann die Tabelle hier noch nicht existieren.
    leave_req_columns = [row[1] for row in cur.execute("PRAGMA table_info(leave_requests)").fetchall()]
    if leave_req_columns and "days_count" not in leave_req_columns:
        cur.execute("ALTER TABLE leave_requests ADD COLUMN days_count INTEGER NOT NULL DEFAULT 0")

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
    if "work_start_time" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN work_start_time TEXT NOT NULL DEFAULT ''")
    if "work_end_time" not in settings_columns:
        cur.execute("ALTER TABLE settings ADD COLUMN work_end_time TEXT NOT NULL DEFAULT ''")

    # access_logs: lateness flag
    access_log_columns = [row[1] for row in cur.execute("PRAGMA table_info(access_logs)").fetchall()]
    if "checked_in_late" not in access_log_columns:
        cur.execute("ALTER TABLE access_logs ADD COLUMN checked_in_late INTEGER NOT NULL DEFAULT 0")

    inbox_columns = [row[1] for row in cur.execute("PRAGMA table_info(email_inbox)").fetchall()]
    if "to_addr" not in inbox_columns:
        cur.execute("ALTER TABLE email_inbox ADD COLUMN to_addr TEXT NOT NULL DEFAULT ''")
    if "matched_company_id" not in inbox_columns:
        cur.execute("ALTER TABLE email_inbox ADD COLUMN matched_company_id TEXT")

    attachment_columns = [row[1] for row in cur.execute("PRAGMA table_info(email_attachments)").fetchall()]
    if "content_type" not in attachment_columns:
        cur.execute("ALTER TABLE email_attachments ADD COLUMN content_type TEXT NOT NULL DEFAULT ''")
    if "file_size" not in attachment_columns:
        cur.execute("ALTER TABLE email_attachments ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0")
    if "file_data" not in attachment_columns:
        cur.execute("ALTER TABLE email_attachments ADD COLUMN file_data BLOB")
    if "assigned_worker_id" not in attachment_columns:
        cur.execute("ALTER TABLE email_attachments ADD COLUMN assigned_worker_id TEXT")
    if "assigned_doc_type" not in attachment_columns:
        cur.execute("ALTER TABLE email_attachments ADD COLUMN assigned_doc_type TEXT")
    if "saved_path" not in attachment_columns:
        cur.execute("ALTER TABLE email_attachments ADD COLUMN saved_path TEXT NOT NULL DEFAULT ''")

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
    if "payment_note" not in invoice_columns:
        cur.execute("ALTER TABLE invoices ADD COLUMN payment_note TEXT NOT NULL DEFAULT ''")

    operation_approval_columns = [row[1] for row in cur.execute("PRAGMA table_info(operation_approvals)").fetchall()]
    if "expires_at" not in operation_approval_columns:
        cur.execute("ALTER TABLE operation_approvals ADD COLUMN expires_at TEXT")
        cur.execute(
            "UPDATE operation_approvals SET expires_at = ? WHERE COALESCE(TRIM(expires_at), '') = ''",
            ((utc_now() + timedelta(minutes=OPERATION_APPROVAL_EXPIRY_MINUTES)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),),
        )

    # ── Neue Features: Migration ──────────────────────────────────────────────────────────
    company_columns_new = [row[1] for row in cur.execute("PRAGMA table_info(companies)").fetchall()]
    if "invoice_email_lang" not in company_columns_new:
        cur.execute("ALTER TABLE companies ADD COLUMN invoice_email_lang TEXT NOT NULL DEFAULT 'de'")
    if "billing_street" not in company_columns_new:
        cur.execute("ALTER TABLE companies ADD COLUMN billing_street TEXT NOT NULL DEFAULT ''")
    if "billing_zip_city" not in company_columns_new:
        cur.execute("ALTER TABLE companies ADD COLUMN billing_zip_city TEXT NOT NULL DEFAULT ''")
    settings_columns_new = [row[1] for row in cur.execute("PRAGMA table_info(settings)").fetchall()]
    if "dunning_stage1_days" not in settings_columns_new:
        cur.execute("ALTER TABLE settings ADD COLUMN dunning_stage1_days INTEGER NOT NULL DEFAULT 7")
    if "dunning_stage2_days" not in settings_columns_new:
        cur.execute("ALTER TABLE settings ADD COLUMN dunning_stage2_days INTEGER NOT NULL DEFAULT 3")
    if "invoice_email_body_template" not in settings_columns_new:
        cur.execute("ALTER TABLE settings ADD COLUMN invoice_email_body_template TEXT NOT NULL DEFAULT ''")

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

    # ── Neu: is_read fuer E-Mail-Posteingang ──
    inbox_columns = [row[1] for row in cur.execute("PRAGMA table_info(email_inbox)").fetchall()]
    if "is_read" not in inbox_columns:
        cur.execute("ALTER TABLE email_inbox ADD COLUMN is_read INTEGER NOT NULL DEFAULT 0")

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

    # ── Neu: Urlaubsantraege & Krankmeldungen ──────────────────
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'urlaub',
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            days_count INTEGER NOT NULL DEFAULT 0,
            note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ausstehend',
            reviewed_by_user_id TEXT,
            reviewed_at TEXT,
            review_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(company_id) REFERENCES companies(id)
        )
        """
    )

    # ── email_forwarded_to Spalte fuer leave_requests ──────────
    leave_req_columns = [row[1] for row in cur.execute("PRAGMA table_info(leave_requests)").fetchall()]
    if "email_forwarded_to" not in leave_req_columns:
        cur.execute("ALTER TABLE leave_requests ADD COLUMN email_forwarded_to TEXT NOT NULL DEFAULT ''")

    # ── Neu: Push-Subscriptions (VAPID-Web-Push) ───────────────
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(worker_id) REFERENCES workers(id),
            FOREIGN KEY(company_id) REFERENCES companies(id)
        )
        """
    )

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

    # ── Kundenbewertungen ──────────────────────────────────────────────────────
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_reviews (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            company_name_snapshot TEXT NOT NULL DEFAULT '',
            stars INTEGER NOT NULL DEFAULT 5,
            review_text TEXT NOT NULL DEFAULT '',
            reviewer_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    company_review_cols = [row[1] for row in cur.execute("PRAGMA table_info(companies)").fetchall()]
    if "review_enabled" not in company_review_cols:
        cur.execute("ALTER TABLE companies ADD COLUMN review_enabled INTEGER NOT NULL DEFAULT 0")
    if "review_token" not in company_review_cols:
        cur.execute("ALTER TABLE companies ADD COLUMN review_token TEXT NOT NULL DEFAULT ''")

    db.commit()
    db.close()


def init_db_with_retry(attempts=5, base_delay_seconds=0.3):
    """Retry init_db on transient SQLite lock contention during app startup."""
    for attempt in range(attempts):
        try:
            init_db()
            return
        except sqlite3.OperationalError as exc:
            is_locked = "database is locked" in str(exc).lower()
            if not is_locked or attempt >= attempts - 1:
                raise
            time.sleep(base_delay_seconds * (attempt + 1))


def normalize_e2e_superadmin_credentials():
    """Stabilize local Playwright runs against mutable developer databases."""
    reset_flag = (os.getenv("BAUPASS_E2E_RESET_SUPERADMIN") or "").strip().lower()
    if reset_flag not in {"1", "true", "yes", "on"}:
        return

    db = sqlite3.connect(DB_PATH, timeout=60)
    try:
        db.execute(
            """
            UPDATE users
            SET password_hash = ?, twofa_enabled = 0, twofa_secret = '', email = ''
            WHERE lower(username) = 'superadmin' AND role = 'superadmin'
            """,
            (generate_password_hash("1234"),),
        )
        db.execute(
            "DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE lower(username) = 'superadmin' AND role = 'superadmin')"
        )
        db.execute("DELETE FROM otp_codes WHERE user_id IN (SELECT id FROM users WHERE lower(username) = 'superadmin' AND role = 'superadmin')")
        db.commit()
    finally:
        db.close()


try:
    init_db_with_retry()
    normalize_e2e_superadmin_credentials()
except Exception as _init_db_exc:
    import traceback as _tb
    print(f"[baupass] CRITICAL: init_db() failed: {_init_db_exc}", flush=True)
    _tb.print_exc()
    raise


def row_to_dict(row):
    return dict(row) if row is not None else None


def sanitize_customer_number(raw_value, max_len=12):
    """Lässt alphanumerische Zeichen und Bindestriche durch (Format KU-YY-NNNN)."""
    cleaned = re.sub(r"[^A-Za-z0-9\-]", "", str(raw_value or "")).strip()
    if max_len > 0:
        cleaned = cleaned[:max_len]
    return cleaned


def get_next_customer_number(db):
    """Erzeugt die nächste Kundennummer im Format KU-YY-NNNN, z.B. KU-26-0105."""
    yy = datetime.now().strftime("%y")
    prefix = f"KU-{yy}-"
    row = db.execute(
        "SELECT customer_number FROM companies WHERE customer_number LIKE ? ORDER BY customer_number DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    if row:
        parts = str(row["customer_number"]).split("-")
        if len(parts) == 3 and parts[2].isdigit():
            return f"KU-{yy}-{int(parts[2]) + 1:04d}"
    return f"KU-{yy}-0001"


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
        purged = _throttled_session_purge(db)
        if purged > 0:
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

        plan_value = get_company_plan(db, worker["company_id"])
        if not company_has_feature(plan_value, "worker_app"):
            db.execute("DELETE FROM worker_app_sessions WHERE token = ?", (token,))
            db.commit()
            return feature_not_available_response("worker_app", plan_value)

        g.worker = row_to_dict(
            worker)
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


def _generate_reminder_pdf_bytes(invoice_row, company_row, settings_row, stage, days_until_due):
    """Generate a branded payment reminder PDF and return as bytes. Returns None on error."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return None

    stage_labels = {1: "Zahlungserinnerung", 2: "2. Mahnung", 3: "Letzte Mahnung"}
    letter_type = stage_labels.get(stage, "Zahlungserinnerung")
    warning_texts = {
        2: "Bitte beachten Sie, dass bei Nichtzahlung weitere Mahnschritte folgen.",
        3: "Wir werden ohne Zahlungseingang innerhalb der gesetzten Frist den Zugang sperren.",
    }
    warning_text = warning_texts.get(stage, "")
    deadline_days = {1: 14, 2: 7, 3: 5}.get(stage, 14)
    new_due_date = (datetime.now(timezone.utc) + timedelta(days=deadline_days)).strftime("%d.%m.%Y")

    invoice_number = str(invoice_row["invoice_number"] or "-")
    total_amount = float(invoice_row["total_amount"] or 0)
    invoice_date_str = str(invoice_row["invoice_date"] or "")[:10]
    original_due_str = str(invoice_row["due_date"] or "")[:10]
    invoice_period = str(invoice_row["invoice_period"] if "invoice_period" in invoice_row.keys() else "")[:22]
    c_name = str((company_row["name"] if "name" in company_row.keys() else None) or (invoice_row["company_name"] if "company_name" in invoice_row.keys() else None) or "")

    s = settings_row
    operator_name = str((s["operator_name"] if "operator_name" in s.keys() else None) or (s["platform_name"] if "platform_name" in s.keys() else None) or "").strip()
    operator_street = str((s["invoice_operator_street"] if "invoice_operator_street" in s.keys() else None) or "").strip()
    operator_zip_city = str((s["invoice_operator_zip_city"] if "invoice_operator_zip_city" in s.keys() else None) or "").strip()
    operator_phone = str((s["invoice_operator_phone"] if "invoice_operator_phone" in s.keys() else None) or "").strip()
    operator_email_addr = str((s["invoice_operator_email"] if "invoice_operator_email" in s.keys() else None) or "").strip()
    operator_website = str((s["invoice_operator_website"] if "invoice_operator_website" in s.keys() else None) or "").strip()
    iban = str((s["invoice_iban"] if "invoice_iban" in s.keys() else None) or "").strip()
    bic = str((s["invoice_bic"] if "invoice_bic" in s.keys() else None) or "").strip()
    bank_name = str((s["invoice_bank_name"] if "invoice_bank_name" in s.keys() else None) or "").strip()
    primary_color = str((s["invoice_primary_color"] if "invoice_primary_color" in s.keys() else None) or "#0f4c5c").strip()

    def _hex_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))

    try:
        pr, pg, pb = _hex_rgb(primary_color)
    except Exception:
        pr, pg, pb = 0.059, 0.298, 0.361

    # Logo handling
    logo_data = str((s["invoice_logo_data"] if "invoice_logo_data" in s.keys() else None) or "").strip()
    logo_image = None
    if logo_data.startswith("data:image"):
        try:
            import base64 as _b64
            from reportlab.lib.utils import ImageReader
            import io as _io
            _, encoded = logo_data.split(",", 1)
            raw = _b64.b64decode(encoded)
            logo_image = ImageReader(_io.BytesIO(raw))
        except Exception:
            logo_image = None

    buf = io.BytesIO()
    page_width, page_height = A4
    pdf = rl_canvas.Canvas(buf, pagesize=A4)

    # Header band
    pdf.setFillColorRGB(pr, pg, pb)
    pdf.rect(0, page_height - 58, page_width, 58, fill=1, stroke=0)
    if logo_image:
        try:
            pdf.drawImage(logo_image, page_width - 120, page_height - 52, width=80, height=42, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(36, page_height - 32, letter_type.upper())
    pdf.setFont("Helvetica", 9)
    pdf.drawString(36, page_height - 48, operator_name)

    # Sender address (small)
    y = page_height - 76
    pdf.setFillColorRGB(0.5, 0.5, 0.5)
    pdf.setFont("Helvetica", 7)
    sender_line = "  |  ".join(filter(None, [operator_name, operator_street, operator_zip_city]))
    pdf.drawString(36, y, sender_line[:110])

    # Recipient block
    y -= 20
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(36, y, c_name)
    contact = str(invoice_row["company_contact"] if "company_contact" in invoice_row.keys() else "")
    billing_street = str((invoice_row["company_billing_street"] if "company_billing_street" in invoice_row.keys() else None) or (company_row["billing_street"] if company_row and "billing_street" in company_row.keys() else "") or "").strip()
    billing_zip_city = str((invoice_row["company_billing_zip_city"] if "company_billing_zip_city" in invoice_row.keys() else None) or (company_row["billing_zip_city"] if company_row and "billing_zip_city" in company_row.keys() else "") or "").strip()
    billing_email = str((invoice_row["company_billing_email"] if "company_billing_email" in invoice_row.keys() else None) or (company_row["billing_email"] if "billing_email" in company_row.keys() else None) or "")
    if contact:
        y -= 14
        pdf.drawString(36, y, contact)
    if billing_street:
        y -= 13
        pdf.setFont("Helvetica", 9)
        pdf.drawString(36, y, billing_street)
    if billing_zip_city:
        y -= 13
        pdf.setFont("Helvetica", 9)
        pdf.drawString(36, y, billing_zip_city)
    if billing_email:
        y -= 13
        pdf.setFont("Helvetica", 9)
        pdf.setFillColorRGB(0.45, 0.45, 0.45)
        pdf.drawString(36, y, billing_email)

    # Date / Ref right-aligned
    ref_y = page_height - 94
    pdf.setFont("Helvetica", 9)
    pdf.setFillColorRGB(0.4, 0.4, 0.4)
    pdf.drawRightString(page_width - 36, ref_y, f"Datum: {datetime.now().strftime('%d.%m.%Y')}")
    ref_y -= 13
    pdf.drawRightString(page_width - 36, ref_y, f"Rechnungs-Nr.: {invoice_number}")
    ref_y -= 13
    pdf.drawRightString(page_width - 36, ref_y, f"Ursprüngliche Fälligkeit: {original_due_str}")

    # Subject line
    y = page_height - 205
    pdf.setFillColorRGB(pr, pg, pb)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(36, y, f"{letter_type}: Rechnung {invoice_number}")
    y -= 20
    pdf.setFillColorRGB(0.1, 0.1, 0.1)

    # Body text
    pdf.setFont("Helvetica", 10)
    pdf.drawString(36, y, "Sehr geehrte Damen und Herren,")
    y -= 16
    pdf.setFont("Helvetica", 9)
    for line in [
        f"für nachfolgend aufgeführte Rechnung haben wir bis heute keinen Zahlungseingang verzeichnet.",
        f"Wir bitten Sie, den ausstehenden Betrag bis zum {new_due_date} zu begleichen.",
    ]:
        pdf.drawString(36, y, line)
        y -= 13

    # Invoice detail box
    y -= 10
    box_y = y - 62
    pdf.setFillColorRGB(0.96, 0.97, 0.98)
    pdf.rect(36, box_y, page_width - 72, 64, fill=1, stroke=0)
    pdf.setFillColorRGB(pr, pg, pb)
    pdf.setFont("Helvetica-Bold", 9)
    for header, xpos in [("Rechnungs-Nr.", 44), ("Datum", 160), ("Zeitraum", 240), ("Betrag (brutto)", 380)]:
        pdf.drawString(xpos, box_y + 46, header)
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica", 9)
    amount_str = f"{total_amount:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
    pdf.drawString(44, box_y + 28, invoice_number)
    pdf.drawString(160, box_y + 28, invoice_date_str)
    pdf.drawString(240, box_y + 28, invoice_period)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(380, box_y + 28, amount_str)
    y = box_y - 16

    if warning_text:
        pdf.setFillColorRGB(0.75, 0.1, 0.1)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(36, y, warning_text[:110])
        y -= 16
        pdf.setFillColorRGB(0.1, 0.1, 0.1)

    # Bank / payment reference
    y -= 6
    if iban:
        pdf.setFillColorRGB(0.3, 0.3, 0.3)
        pdf.setFont("Helvetica", 9)
        bank_line = f"Bitte überweisen auf IBAN {iban}" + (f"  BIC {bic}" if bic else "") + (f"  ({bank_name})" if bank_name else "")
        pdf.drawString(36, y, bank_line[:110])
        y -= 13
        pdf.drawString(36, y, f"Verwendungszweck: {invoice_number}")
        y -= 13

    # Closing
    y -= 10
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(36, y, "Mit freundlichen Grüßen")
    y -= 14
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(36, y, operator_name)
    contact_parts = []
    if operator_phone:
        contact_parts.append(f"Tel: {operator_phone}")
    if operator_email_addr:
        contact_parts.append(f"E-Mail: {operator_email_addr}")
    if operator_website:
        contact_parts.append(operator_website)
    if contact_parts:
        y -= 12
        pdf.setFont("Helvetica", 8)
        pdf.setFillColorRGB(0.4, 0.4, 0.4)
        pdf.drawString(36, y, "  |  ".join(contact_parts)[:110])

    # Footer band
    pdf.setFillColorRGB(pr, pg, pb)
    pdf.rect(0, 0, page_width, 24, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica", 7)
    footer_parts = list(filter(None, [operator_name, operator_street, operator_zip_city]))
    pdf.drawString(36, 8, "  |  ".join(footer_parts)[:120])

    pdf.save()
    buf.seek(0)
    return buf.getvalue()


def send_payment_reminder_email(invoice_row, company_row, settings_row, stage, days_until_due):
    smtp_sender = (settings_row["smtp_sender_email"] or "").strip()
    sender_name = (settings_row["smtp_sender_name"] or settings_row["operator_name"] or "").strip()
    recipient = (invoice_row["recipient_email"] or "").strip()
    if not recipient:
        return False, "Empfänger-E-Mail fehlt"

    platform_name = str(settings_row["platform_name"] or "BauPass").strip()
    primary_color = str(settings_row["invoice_primary_color"] or "#0f4c5c").strip()
    accent_color = str(settings_row["invoice_accent_color"] if "invoice_accent_color" in settings_row.keys() else "#e36414").strip() or "#e36414"
    operator_name = str(settings_row["operator_name"] or platform_name).strip()
    operator_phone = str((settings_row["invoice_operator_phone"] if "invoice_operator_phone" in settings_row.keys() else None) or "").strip()
    operator_email_addr = str((settings_row["invoice_operator_email"] if "invoice_operator_email" in settings_row.keys() else None) or "").strip()
    operator_website = str((settings_row["invoice_operator_website"] if "invoice_operator_website" in settings_row.keys() else None) or "").strip()
    operator_street = str((settings_row["invoice_operator_street"] if "invoice_operator_street" in settings_row.keys() else None) or "").strip()
    operator_zip_city = str((settings_row["invoice_operator_zip_city"] if "invoice_operator_zip_city" in settings_row.keys() else None) or "").strip()
    iban = str((settings_row["invoice_iban"] if "invoice_iban" in settings_row.keys() else None) or "").strip()
    bic = str((settings_row["invoice_bic"] if "invoice_bic" in settings_row.keys() else None) or "").strip()
    bank_name = str((settings_row["invoice_bank_name"] if "invoice_bank_name" in settings_row.keys() else None) or "").strip()

    stage_label = {1: "Zahlungserinnerung", 2: "2. Mahnung", 3: "Letzte Mahnung – Sperrung droht"}.get(stage, "Zahlungserinnerung")
    due_label = invoice_row["due_date"] or "-"
    amount = f"{float(invoice_row['total_amount'] or 0):.2f} EUR"
    invoice_number = invoice_row["invoice_number"] or "-"
    company_name = company_row["name"] or "-"

    if days_until_due < 0:
        timing_text = f"seit {abs(days_until_due)} Tag(en) überfällig"
    elif days_until_due == 0:
        timing_text = "heute fällig"
    else:
        timing_text = f"in {days_until_due} Tag(en) fällig"

    subject = f"{stage_label}: Rechnung {invoice_number} ({timing_text})"

    text_body = (
        f"Guten Tag,\n\n"
        f"dies ist eine {stage_label} für die Rechnung {invoice_number} ({company_name}).\n"
        f"Fälligkeit: {due_label} ({timing_text})\n"
        f"Offener Betrag: {amount}\n\n"
        f"Bitte begleichen Sie den Betrag zeitnah, um eine Zugangssperrung zu vermeiden.\n\n"
        f"Mit freundlichen Grüßen\n{operator_name}"
    )

    warning_banner = ""
    if stage == 3:
        warning_banner = '<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:12px 16px;margin-bottom:20px;color:#856404;font-size:14px;">&#9888; <strong>Achtung:</strong> Bei ausbleibender Zahlung wird der Zugang automatisch gesperrt.</div>'

    # Contact info block for email
    contact_rows = ""
    for label, value in [
        ("Adresse", "  ".join(filter(None, [operator_street, operator_zip_city]))),
        ("Telefon", operator_phone),
        ("E-Mail", operator_email_addr),
        ("Website", operator_website),
        ("IBAN", iban + (f"  BIC {bic}" if bic else "") + (f"  ({bank_name})" if bank_name else "")),
    ]:
        if value:
            contact_rows += f'<tr><td style="padding:5px 14px;font-size:12px;color:#555;width:35%;">{html.escape(label)}</td><td style="padding:5px 14px;font-size:12px;color:#212529;">{html.escape(value)}</td></tr>'

    contact_block = ""
    if contact_rows:
        contact_block = f"""
<div style="margin-top:28px;border-top:1px solid #dee2e6;padding-top:16px;">
  <p style="margin:0 0 8px;font-size:12px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:0.05em;">Kontakt &amp; Zahlungsdetails</p>
  <table style="width:100%;border-collapse:collapse;">{contact_rows}</table>
</div>"""

    inner_html = f"""
{warning_banner}
<p style="margin:0 0 12px;color:#333;font-size:15px;">Guten Tag,</p>
<p style="margin:0 0 20px;color:#333;font-size:15px;">dies ist eine <strong>{html.escape(stage_label)}</strong> für folgende offene Rechnung:</p>
<table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
  <tr style="background:#f8f9fa;">
    <td style="padding:10px 14px;border:1px solid #dee2e6;font-size:14px;color:#555;width:40%;">Rechnungsnummer</td>
    <td style="padding:10px 14px;border:1px solid #dee2e6;font-size:14px;font-weight:600;color:#212529;">{html.escape(invoice_number)}</td>
  </tr>
  <tr>
    <td style="padding:10px 14px;border:1px solid #dee2e6;font-size:14px;color:#555;">Firma</td>
    <td style="padding:10px 14px;border:1px solid #dee2e6;font-size:14px;color:#212529;">{html.escape(company_name)}</td>
  </tr>
  <tr style="background:#f8f9fa;">
    <td style="padding:10px 14px;border:1px solid #dee2e6;font-size:14px;color:#555;">Fälligkeit</td>
    <td style="padding:10px 14px;border:1px solid #dee2e6;font-size:14px;color:#212529;">{html.escape(due_label)} <span style="color:#dc3545;">({html.escape(timing_text)})</span></td>
  </tr>
  <tr>
    <td style="padding:10px 14px;border:1px solid #dee2e6;font-size:14px;color:#555;">Offener Betrag</td>
    <td style="padding:10px 14px;border:1px solid #dee2e6;font-size:15px;font-weight:700;color:{html.escape(primary_color)};">{html.escape(amount)}</td>
  </tr>
</table>
<p style="margin:0 0 8px;color:#333;font-size:15px;">Bitte begleichen Sie den Betrag zeitnah, um eine Zugangssperrung zu vermeiden.</p>
<p style="margin:0 0 8px;color:#6c757d;font-size:13px;">Im Anhang finden Sie das Mahnschreiben als PDF-Dokument.</p>
<p style="margin:0;color:#6c757d;font-size:13px;">Bei Fragen wenden Sie sich direkt an uns.</p>
{contact_block}
"""
    html_body = _build_email_html(
        platform_name=platform_name,
        primary_color=primary_color,
        accent_color=accent_color,
        title=stage_label,
        body_html=inner_html,
        footer_name=operator_name,
    )

    # Generate PDF attachment
    pdf_bytes = _generate_reminder_pdf_bytes(invoice_row, company_row, settings_row, stage, days_until_due)
    pdf_filename = f"Mahnschreiben_{invoice_number.replace('/', '-')}.pdf"

    smtp_host = (settings_row["smtp_host"] or "").strip()
    smtp_port = int(settings_row["smtp_port"] or 587)
    smtp_use_tls = int(settings_row["smtp_use_tls"] or 0) == 1
    smtp_username = (settings_row["smtp_username"] or "").strip()
    smtp_password = settings_row["smtp_password"] or ""
    if smtp_host and smtp_sender:
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{smtp_sender}>" if sender_name else smtp_sender
            msg["To"] = recipient
            msg.set_content(text_body)
            msg.add_alternative(html_body, subtype="html")
            if pdf_bytes:
                msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)
            with _smtp_connect(smtp_host, smtp_port, smtp_use_tls) as smtp:
                if smtp_username:
                    smtp.login(smtp_username, smtp_password)
                smtp.send_message(msg)
            return True, ""
        except Exception as smtp_exc:
            app.logger.warning(f"[DUNNING] SMTP fehlgeschlagen ({smtp_exc}), versuche API-Fallback")

    # API fallback – attach PDF as base64 if available
    attachments = []
    if pdf_bytes:
        import base64 as _b64
        attachments = [{"filename": pdf_filename, "content": _b64.b64encode(pdf_bytes).decode("ascii"), "type": "application/pdf"}]

    ok, err, _provider = _send_via_any_api(
        subject=subject,
        sender_email=smtp_sender or "noreply@baupass.app",
        sender_name=sender_name,
        recipient=recipient,
        text_body=text_body,
        html_body=html_body,
        attachments=attachments,
    )
    if ok:
        return True, ""
    return False, f"API-Fallback fehlgeschlagen | {err}"


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
    """Return Brevo API key from module-level cache, DB, or env var."""
    cached = _normalize_env_value(_resend_key_cache.get("brevo_key") or "")
    if cached:
        return cached
    # Direct DB fallback in case cache is stale (e.g. after hot-reload)
    try:
        with closing(sqlite3.connect(DB_PATH)) as _db:
            _db.row_factory = sqlite3.Row
            _row = _db.execute("SELECT brevo_api_key, brevo_from_email FROM settings WHERE id = 1").fetchone()
            if _row:
                db_key = _normalize_env_value(_row["brevo_api_key"] or "")
                if db_key:
                    _resend_key_cache["brevo_key"] = db_key
                    _resend_key_cache["brevo_from_email"] = _normalize_env_value(_row["brevo_from_email"] or "")
                    return db_key
    except Exception:
        pass
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


def _count_working_days(start_str: str, end_str: str) -> int:
    """Zählt Arbeitstage (Mo–Fr) zwischen zwei ISO-Datums-Strings (inklusive)."""
    try:
        from datetime import date, timedelta
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
        if end < start:
            return 0
        count = 0
        current = start
        while current <= end:
            if current.weekday() < 5:  # 0=Mo … 4=Fr
                count += 1
            current += timedelta(days=1)
        return count
    except Exception:
        return 0


def _send_push_to_worker(db, worker_id: str, title: str, body: str, tag: str = "notification") -> int:
    """Schickt eine Web-Push-Nachricht an alle Subscriptions eines Mitarbeiters.
    Gibt die Anzahl der erfolgreich gesendeten Nachrichten zurueck."""
    try:
        from pywebpush import webpush  # noqa: F401
    except ImportError:
        return 0
    vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    vapid_email = os.getenv("VAPID_EMAIL", "mailto:admin@example.com").strip()
    if not vapid_private_key:
        return 0
    subs = db.execute(
        "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE worker_id = ?",
        (worker_id,)
    ).fetchall()
    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=json.dumps({"title": title, "body": body, "tag": tag}),
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_email}
            )
            sent += 1
        except Exception:
            pass
    return sent


def _send_email_to_worker(db, worker_id: str, subject: str, text_body: str, html_body: str):
    """Sendet E-Mail an Mitarbeiter, falls contact_email gesetzt ist."""
    worker_row = db.execute(
        "SELECT contact_email, first_name, last_name FROM workers WHERE id = ?", (worker_id,)
    ).fetchone()
    if not worker_row:
        return False
    email = (worker_row["contact_email"] or "").strip()
    if not email or "@" not in email:
        return False
    settings_row = db.execute(
        "SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1"
    ).fetchone()
    settings = dict(settings_row) if settings_row else {}
    sender_email = (settings.get("smtp_sender_email") or "").strip() or "noreply@baupass.de"
    sender_name = (settings.get("smtp_sender_name") or "BauPass").strip()
    try:
        _send_via_any_api(subject, sender_email, sender_name, email, text_body, html_body)
        return True
    except Exception:
        return False


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
        "platform_name": str(payload.get("platformName") if "platformName" in payload else (saved_settings["platform_name"] if saved_settings else DEFAULT_PLATFORM_NAME) or DEFAULT_PLATFORM_NAME).strip(),
        "operator_name": str(payload.get("operatorName") if "operatorName" in payload else (saved_settings["operator_name"] if saved_settings else DEFAULT_OPERATOR_NAME) or DEFAULT_OPERATOR_NAME).strip(),
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
        stage1_days = int((settings["dunning_stage1_days"] if settings and "dunning_stage1_days" in settings.keys() else None) or 7)
        stage2_days = int((settings["dunning_stage2_days"] if settings and "dunning_stage2_days" in settings.keys() else None) or 3)
        if days_until_due <= stage1_days and days_until_due > stage2_days:
            target_stage = 1
        elif days_until_due <= stage2_days and days_until_due >= 0:
            target_stage = 2
        elif days_until_due < 0:
            target_stage = 3

        if target_stage == 0:
            continue

        # Stage 3: repeat max every 7 days (not every day)
        stage3_repeat = False
        if target_stage == 3:
            if not last_reminder_day:
                stage3_repeat = True
            else:
                try:
                    import datetime as _dt
                    days_since_last = (today - _dt.date.fromisoformat(last_reminder_day[:10])).days
                    stage3_repeat = days_since_last >= 7
                except Exception:
                    stage3_repeat = True
        should_send = target_stage > current_stage or stage3_repeat
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
            with smtplib.SMTP(smtp_host, int(settings["smtp_port"] or 587), timeout=10) as smtp:
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


def _month_period_range(reference_date=None):
    today = reference_date or utc_now().date()
    current_month_start = today.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return previous_month_start, previous_month_end


def _resolve_company_invoice_recipient(db, company_row):
    billing_email = str(company_row["billing_email"] or "").strip()
    if billing_email:
        return billing_email
    admin_row = db.execute(
        """
        SELECT email
        FROM users
        WHERE company_id = ? AND role = 'company-admin' AND COALESCE(email, '') <> ''
        ORDER BY id ASC
        LIMIT 1
        """,
        (company_row["id"],),
    ).fetchone()
    if admin_row:
        return str(admin_row["email"] or "").strip()
    return ""


def _resolve_monthly_invoice_creator_user_id(db):
    row = db.execute("SELECT id FROM users WHERE role = 'superadmin' ORDER BY id ASC LIMIT 1").fetchone()
    return str(row["id"] or "") if row else ""


def _build_monthly_invoice_html(company_name, invoice_number, period_label, platform_label, operator_label, total_amount):
    company_safe = html.escape(str(company_name or "Firma"))
    number_safe = html.escape(str(invoice_number or "-"))
    period_safe = html.escape(str(period_label or "-"))
    platform_safe = html.escape(str(platform_label or DEFAULT_PLATFORM_NAME))
    operator_safe = html.escape(str(operator_label or DEFAULT_OPERATOR_NAME))
    amount_safe = html.escape(f"{float(total_amount or 0):.2f} EUR".replace(".", ","))
    return f"""<!DOCTYPE html>
<html lang=\"de\">
<head><meta charset=\"utf-8\"><title>{number_safe}</title></head>
<body>
  <h1>{platform_safe} Monatsrechnung</h1>
  <p>Firma: {company_safe}</p>
  <p>Rechnungsnummer: {number_safe}</p>
  <p>Leistungszeitraum: {period_safe}</p>
  <p>Betrag: {amount_safe}</p>
  <p>Erstellt durch {operator_safe}.</p>
</body>
</html>"""


def _get_monthly_invoice_settings_values(settings_row):
    auto_enabled = int(settings_row["monthly_invoice_auto_enabled"] if settings_row and "monthly_invoice_auto_enabled" in settings_row.keys() else 1) == 1
    run_day = int(settings_row["monthly_invoice_run_day"] if settings_row and "monthly_invoice_run_day" in settings_row.keys() else 1) or 1
    due_days = int(settings_row["monthly_invoice_due_days"] if settings_row and "monthly_invoice_due_days" in settings_row.keys() else 14) or 14
    return {
        "autoEnabled": auto_enabled,
        "runDay": min(max(run_day, 1), 28),
        "dueDays": min(max(due_days, 1), 90),
    }


def _calculate_next_monthly_invoice_run_date(run_day, reference_date=None):
    today = reference_date or utc_now().date()
    run_day = min(max(int(run_day or 1), 1), 28)
    year = today.year
    month = today.month
    if today.day > run_day:
        month += 1
        if month > 12:
            month = 1
            year += 1
    return datetime(year, month, run_day).date()


def get_monthly_invoice_cycle_status(db, reference_date=None):
    today = reference_date or utc_now().date()
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    config = _get_monthly_invoice_settings_values(settings)
    previous_month_start, _previous_month_end = _month_period_range(reference_date=today)
    current_cycle_key = previous_month_start.strftime("%Y-%m")
    current_cycle = db.execute(
        """
        SELECT created_at, message, target_id
        FROM audit_logs
        WHERE event_type = ? AND target_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        ("invoice.monthly_auto_cycle", current_cycle_key),
    ).fetchone()
    latest_cycle = db.execute(
        """
        SELECT created_at, message, target_id
        FROM audit_logs
        WHERE event_type = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        ("invoice.monthly_auto_cycle",),
    ).fetchone()
    next_run_date = _calculate_next_monthly_invoice_run_date(config["runDay"], reference_date=today)
    return {
        "autoEnabled": config["autoEnabled"],
        "runDay": config["runDay"],
        "dueDays": config["dueDays"],
        "currentCycleKey": current_cycle_key,
        "currentCycleAlreadyRan": bool(current_cycle),
        "currentCycleRanAt": current_cycle["created_at"] if current_cycle else "",
        "lastRunAt": latest_cycle["created_at"] if latest_cycle else "",
        "lastRunCycleKey": latest_cycle["target_id"] if latest_cycle else "",
        "lastRunMessage": latest_cycle["message"] if latest_cycle else "",
        "nextScheduledRunDate": next_run_date.isoformat(),
    }


def run_monthly_invoice_cycle(db, reference_date=None, force=False):
    previous_month_start, previous_month_end = _month_period_range(reference_date=reference_date)
    cycle_key = previous_month_start.strftime("%Y-%m")
    today = reference_date or utc_now().date()
    existing_cycle = db.execute(
        "SELECT id FROM audit_logs WHERE event_type = ? AND target_id = ? LIMIT 1",
        ("invoice.monthly_auto_cycle", cycle_key),
    ).fetchone()
    if existing_cycle:
        return {"period": cycle_key, "created": 0, "sent": 0, "skipped": 0, "failed": 0, "reason": "already_ran"}

    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    config = _get_monthly_invoice_settings_values(settings)
    if not config["autoEnabled"] and not force:
        return {"period": cycle_key, "created": 0, "sent": 0, "skipped": 0, "failed": 0, "reason": "disabled"}
    if not force and today.day != config["runDay"]:
        return {"period": cycle_key, "created": 0, "sent": 0, "skipped": 0, "failed": 0, "reason": "day_not_due"}
    platform_label = str(settings["platform_name"] or DEFAULT_PLATFORM_NAME).strip() if settings else DEFAULT_PLATFORM_NAME
    operator_label = str(settings["operator_name"] or DEFAULT_OPERATOR_NAME).strip() if settings else DEFAULT_OPERATOR_NAME
    created_by_user_id = _resolve_monthly_invoice_creator_user_id(db)
    if not created_by_user_id:
        return {"period": cycle_key, "created": 0, "sent": 0, "skipped": 0, "failed": 0, "reason": "missing_superadmin"}

    period_label = f"{previous_month_start.isoformat()} - {previous_month_end.isoformat()}"
    invoice_date = today.isoformat()
    due_date = (today + timedelta(days=config["dueDays"])).isoformat()
    companies = db.execute(
        """
        SELECT *
        FROM companies
        WHERE deleted_at IS NULL AND lower(COALESCE(status, 'aktiv')) != 'geloescht'
        ORDER BY name ASC
        """
    ).fetchall()

    result = {"period": cycle_key, "created": 0, "sent": 0, "skipped": 0, "failed": 0, "reason": ""}
    for company in companies:
        company_id = str(company["id"] or "").strip()
        if not company_id:
            result["skipped"] += 1
            continue
        invoice_number = get_next_numeric_invoice_number(db, company_id=company_id)
        existing_invoice = db.execute(
            "SELECT id FROM invoices WHERE company_id = ? AND invoice_number = ? LIMIT 1",
            (company_id, invoice_number),
        ).fetchone()
        if existing_invoice:
            result["skipped"] += 1
            continue

        recipient_email = _resolve_company_invoice_recipient(db, company)
        if not recipient_email:
            result["failed"] += 1
            create_system_alert(
                db,
                code=f"monthly_invoice_missing_recipient_{company_id}_{cycle_key}",
                severity="warning",
                message=f"Monatsrechnung für {company['name']} konnte nicht erstellt werden, weil keine Rechnungs-E-Mail hinterlegt ist.",
                details={"companyId": company_id, "period": cycle_key},
                dedup_minutes=60 * 24 * 31,
            )
            continue

        # Count active workers for per-worker billing
        active_worker_count = db.execute(
            "SELECT COUNT(*) FROM workers WHERE company_id = ? AND deleted_at IS NULL",
            (company_id,),
        ).fetchone()[0]
        normalized_plan = normalize_company_plan(company["plan"])
        worker_price_per_unit = PLAN_WORKER_PRICE_EUR.get(normalized_plan, 0.0)
        free_included = PLAN_WORKER_FREE_INCLUDED.get(normalized_plan, 0)
        billable_workers = max(0, active_worker_count - free_included)
        base_price = PLAN_NET_PRICE_EUR[normalized_plan]
        net_amount = round(base_price + worker_price_per_unit * billable_workers, 2)
        vat_rate = 19.0
        vat_amount = round(net_amount * (vat_rate / 100), 2)
        total_amount = round(net_amount + vat_amount, 2)
        description = f"Monatsabrechnung {previous_month_start.strftime('%m/%Y')} - {platform_label}"
        invoice_id = f"inv-{secrets.token_hex(6)}"
        line_items = [
            {
                "description": f"Basislizenz {previous_month_start.strftime('%m/%Y')} – {platform_label}",
                "qty": 1,
                "unit": "Monat",
                "unitPrice": base_price,
                "total": base_price,
            }
        ]
        if worker_price_per_unit > 0 and billable_workers > 0:
            worker_fee_total = round(worker_price_per_unit * billable_workers, 2)
            free_note = f", {free_included} inkl." if free_included > 0 else ""
            line_items.append({
                "description": f"Mitarbeiter-Karten ({active_worker_count} aktiv{free_note})",
                "qty": billable_workers,
                "unit": "Karte/Monat",
                "unitPrice": worker_price_per_unit,
                "total": worker_fee_total,
            })
        items_json = json.dumps(line_items, ensure_ascii=False)
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
                period_label,
                description,
                net_amount,
                vat_rate,
                vat_amount,
                total_amount,
                "draft",
                "",
                None,
                _build_monthly_invoice_html(company["name"], invoice_number, period_label, platform_label, operator_label, total_amount),
                created_by_user_id,
                now_iso(),
                due_date,
                0,
                None,
                "",
                0,
                None,
                None,
                items_json,
                0,
            ),
        )
        result["created"] += 1
        sent_ok, _error_message, _updated_invoice = attempt_invoice_delivery(
            db,
            invoice_id,
            actor=None,
            audit_event_success="invoice.monthly_auto_sent",
            audit_event_failed="invoice.monthly_auto_send_failed",
        )
        if sent_ok:
            result["sent"] += 1
        else:
            result["failed"] += 1

    db.execute(
        """
        INSERT INTO audit_logs (id, event_type, actor_user_id, actor_role, company_id, target_type, target_id, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"aud-{secrets.token_hex(8)}",
            "invoice.monthly_auto_cycle",
            created_by_user_id,
            "superadmin",
            None,
            "invoice_cycle",
            cycle_key,
            f"Monatsrechnungslauf {cycle_key}: erstellt={result['created']}, versendet={result['sent']}, uebersprungen={result['skipped']}, fehlgeschlagen={result['failed']}",
            now_iso(),
        ),
    )
    db.commit()
    return result


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
                # Build CSV attachment with all active workers
                import csv as _csv, io as _io_mod
                worker_rows = db.execute(
                    """SELECT first_name, last_name, badge_id, role, site, valid_until, status, worker_type
                       FROM workers WHERE deleted_at IS NULL ORDER BY last_name, first_name"""
                ).fetchall()
                csv_buf = _io_mod.StringIO()
                csv_writer = _csv.writer(csv_buf, delimiter=";", quoting=_csv.QUOTE_MINIMAL)
                csv_writer.writerow(["Vorname", "Nachname", "Badge-ID", "Rolle", "Standort", "Gültig bis", "Status", "Typ"])
                for wr in worker_rows:
                    csv_writer.writerow([
                        wr["first_name"] or "", wr["last_name"] or "", wr["badge_id"] or "",
                        wr["role"] or "", wr["site"] or "", wr["valid_until"] or "",
                        wr["status"] or "", wr["worker_type"] or "",
                    ])
                csv_bytes = csv_buf.getvalue().encode("utf-8-sig")
                csv_filename = f"mitarbeiterliste_{yesterday}.csv"
                msg.add_attachment(csv_bytes, maintype="text", subtype="csv", filename=csv_filename)

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
                            attachments=[{"content": csv_bytes, "filename": csv_filename, "type": "text/csv"}],
                        )
                except Exception:
                    _send_via_any_api(
                        subject=str(msg["Subject"]),
                        sender_email=smtp_sender or "",
                        sender_name=settings["smtp_sender_name"] or "",
                        recipient=admin_email,
                        text_body=summary_text,
                        html_body=html_body,
                        attachments=[{"content": csv_bytes, "filename": csv_filename, "type": "text/csv"}],
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
                    # Only send doc-expiry emails to companies with email_notifications feature
                    _cid_plan = get_company_plan(db, cid)
                    if not company_has_feature(_cid_plan, "email_notifications"):
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
        db = get_db()
        lock_workers_with_expired_documents(db)
        run_monthly_invoice_cycle(db)

    def daily_job_loop():
        """Läuft einmal täglich: Dokument-Ablauf-Prüfung + Zusammenfassungs-E-Mail + Ablauf-Erinnerungen."""
        while True:
            time.sleep(86400)  # 24 Stunden warten
            check_doc_expiry_warnings()
            with app.app_context():
                db = get_db()
                lock_workers_with_expired_documents(db)
                monthly_result = run_monthly_invoice_cycle(db)
                if monthly_result.get("failed", 0) > 0:
                    create_system_alert(
                        db,
                        code=f"monthly_invoice_cycle_{monthly_result.get('period', '')}",
                        severity="warning",
                        message=f"Monatsrechnungslauf {monthly_result.get('period', '')} hatte {monthly_result.get('failed', 0)} Fehler.",
                        details=monthly_result,
                        dedup_minutes=60 * 24 * 31,
                    )
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


def parse_invoice_period_bounds(value):
    normalized = str(value or "").strip()
    if not normalized:
        return None, None

    parts = [part.strip() for part in re.split(r"\s+-\s+|\s+bis\s+|\s+to\s+", normalized, flags=re.IGNORECASE) if part.strip()]
    if len(parts) < 2:
        return None, None

    def parse_part(token):
        raw = str(token or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return parse_iso_date(raw)
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", raw):
            try:
                return datetime.strptime(raw, "%d.%m.%Y").date()
            except ValueError:
                return None
        return None

    from_date = parse_part(parts[0])
    to_date = parse_part(parts[1])
    if not from_date or not to_date or to_date < from_date:
        return None, None
    return from_date, to_date


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


def auto_close_open_entries_after_midnight(db, reference_dt=None):
    day_start = (reference_dt or datetime.now(timezone.utc)).replace(hour=0, minute=0, second=0, microsecond=0)
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
            "SELECT platform_name, invoice_primary_color, invoice_accent_color, invoice_logo_data, impressum_text, datenschutz_text FROM settings WHERE id = 1"
        ).fetchone()
        if not row:
            return jsonify({"platformName": "BauPass", "primaryColor": "#0f4c5c", "accentColor": "#e36414", "logoData": "", "impressumText": "", "datenschutzText": ""})
        return jsonify({
            "platformName": str(row["platform_name"] or "BauPass"),
            "primaryColor": str(row["invoice_primary_color"] or "#0f4c5c"),
            "accentColor": str(row["invoice_accent_color"] or "#e36414"),
            "logoData": str(row["invoice_logo_data"] or ""),
            "impressumText": str(row["impressum_text"] or ""),
            "datenschutzText": str(row["datenschutz_text"] or ""),
        })
    except Exception:
        return jsonify({"platformName": "BauPass", "primaryColor": "#0f4c5c", "accentColor": "#e36414", "logoData": "", "impressumText": "", "datenschutzText": ""})


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
                # 60-second cooldown: if a valid OTP was sent less than 60 seconds ago, don't send a new one
                cooldown_threshold = (datetime.now(timezone.utc) + timedelta(seconds=540)).isoformat()  # expires_at > now+9min → sent within last 60s
                recent_otp = db.execute(
                    "SELECT id FROM otp_codes WHERE user_id = ? AND expires_at > ?",
                    (user["id"], cooldown_threshold)
                ).fetchone()
                if recent_otp:
                    return login_error("otp_sent")

                otp = str(secrets.randbelow(900000) + 100000)
                otp_id = secrets.token_urlsafe(16)
                expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                def _persist_otp_code():
                    db.execute("DELETE FROM otp_codes WHERE user_id = ?", (user["id"],))
                    db.execute(
                        "INSERT INTO otp_codes (id, user_id, code, expires_at) VALUES (?,?,?,?)",
                        (otp_id, user["id"], otp, expires)
                    )
                    db.commit()

                run_db_write_with_retry(_persist_otp_code)
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
    def _persist_login_session():
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
        try:
            db.execute(
                """
                INSERT INTO sessions (token, user_id, expires_at, support_read_only, support_company_name, support_actor_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (token, user["id"], expiry_iso(), support_read_only, support_company_name, support_actor_name),
            )
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            legacy_schema = (
                "no such column" in message
                or "has no column named support_read_only" in message
                or "has no column named support_company_name" in message
                or "has no column named support_actor_name" in message
            )
            if not legacy_schema:
                raise
            # Backward compatibility for environments with an older sessions table.
            db.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user["id"], expiry_iso()),
            )
        db.commit()

    run_db_write_with_retry(_persist_login_session)

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
            "invoiceEmailBodyTemplate": row["invoice_email_body_template"] if "invoice_email_body_template" in row.keys() else "",
            "dunningStage1Days": int(row["dunning_stage1_days"] if "dunning_stage1_days" in row.keys() else 7) or 7,
            "dunningStage2Days": int(row["dunning_stage2_days"] if "dunning_stage2_days" in row.keys() else 3) or 3,
            "monthlyInvoiceAutoEnabled": int(row["monthly_invoice_auto_enabled"] if "monthly_invoice_auto_enabled" in row.keys() else 1) == 1,
            "monthlyInvoiceRunDay": int(row["monthly_invoice_run_day"] if "monthly_invoice_run_day" in row.keys() else 1) or 1,
            "monthlyInvoiceDueDays": int(row["monthly_invoice_due_days"] if "monthly_invoice_due_days" in row.keys() else 14) or 14,
            "workerExpiryWarnDays": int(row["worker_expiry_warn_days"] if "worker_expiry_warn_days" in row.keys() else 30) or 30,
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
            "workerPassLockEnabled": int(row["worker_pass_lock_enabled"]) == 1 if "worker_pass_lock_enabled" in row.keys() else False,
            "workStartTime": row["work_start_time"] if "work_start_time" in row.keys() else "",
            "workEndTime": row["work_end_time"] if "work_end_time" in row.keys() else "",
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
            monthly_invoice_auto_enabled = ?, monthly_invoice_run_day = ?, monthly_invoice_due_days = ?,
            invoice_logo_data = ?, invoice_primary_color = ?, invoice_accent_color = ?,
            invoice_iban = ?, invoice_bic = ?, invoice_bank_name = ?,
            invoice_tax_id = ?, invoice_vat_id = ?,
            invoice_operator_street = ?, invoice_operator_zip_city = ?,
            invoice_operator_phone = ?, invoice_operator_website = ?, invoice_operator_email = ?,
            invoice_email_subject = ?, invoice_email_intro = ?,
            invoice_email_body_template = ?, dunning_stage1_days = ?, dunning_stage2_days = ?,
            smtp_host = ?, smtp_port = ?, smtp_username = ?, smtp_password = ?,
            smtp_sender_email = ?, smtp_sender_name = ?, smtp_use_tls = ?,
            admin_ip_whitelist = ?, enforce_tenant_domain = ?, worker_app_enabled = ?, worker_pass_lock_enabled = ?, worker_expiry_warn_days = ?,
            work_start_time = ?, work_end_time = ?
        WHERE id = 1
        """,
        (
            payload.get("platformName", DEFAULT_PLATFORM_NAME),
            payload.get("operatorName", DEFAULT_OPERATOR_NAME),
            payload.get("turnstileEndpoint", ""),
            payload.get("rentalModel", "tageskarte"),
            1 if payload.get("monthlyInvoiceAutoEnabled", True) else 0,
            min(max(int(payload.get("monthlyInvoiceRunDay") or 1), 1), 28),
            min(max(int(payload.get("monthlyInvoiceDueDays") or 14), 1), 90),
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
            str(payload.get("invoiceEmailBodyTemplate") or "")[:5000],
            int(payload.get("dunningStage1Days") or 7),
            int(payload.get("dunningStage2Days") or 3),
            payload.get("smtpHost", ""),
            int(payload.get("smtpPort", 587) or 587),
            payload.get("smtpUsername", ""),
            payload_smtp_password if payload_smtp_password.strip() else current_smtp_password,
            payload.get("smtpSenderEmail", ""),
            payload.get("smtpSenderName", DEFAULT_PLATFORM_NAME),
            1 if payload.get("smtpUseTls", True) else 0,
            payload.get("adminIpWhitelist", ""),
            1 if payload.get("enforceTenantDomain", False) else 0,
            1 if payload.get("workerAppEnabled", True) else 0,
            1 if payload.get("workerPassLockEnabled", False) else 0,
            max(0, int(payload.get("workerExpiryWarnDays") or 7)),
            str(payload.get("workStartTime") or "")[:5],
            str(payload.get("workEndTime") or "")[:5],
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
            plan_value = get_company_plan(get_db(), requested_company_id)
            if not company_has_feature(plan_value, "subcompanies"):
                return feature_not_available_response("subcompanies", plan_value)
            conditions.append("company_id = ?")
            params.append(requested_company_id)
    else:
        plan_value = get_company_plan(get_db(), user.get("company_id"))
        if not company_has_feature(plan_value, "subcompanies"):
            return feature_not_available_response("subcompanies", plan_value)
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
    plan_value = normalize_company_plan(company["plan"])
    if not company_has_feature(plan_value, "subcompanies"):
        return feature_not_available_response("subcompanies", plan_value)

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
    company_customer_number = sanitize_customer_number(payload.get("customerNumber", ""), max_len=12)
    billing_email = clean_text_input(payload.get("billingEmail", ""), max_len=160)
    document_email = clean_text_input(payload.get("documentEmail", ""), max_len=160)
    if not document_email:
        document_email = suggest_company_document_email(company_name)
    document_email = normalize_email_address(document_email)
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
    if not company_customer_number:
        company_customer_number = get_next_customer_number(db)
    duplicate_customer_no = db.execute(
        "SELECT id, name FROM companies WHERE COALESCE(customer_number, '') = ? LIMIT 1",
        (company_customer_number,),
    ).fetchone()
    if duplicate_customer_no:
        return jsonify({
            "error": "duplicate_customer_number",
            "message": "Diese Kundennummer ist bereits vergeben.",
            "conflictCompanyId": duplicate_customer_no["id"],
            "conflictCompanyName": duplicate_customer_no["name"],
        }), 409

    if document_email:
        duplicate_company = db.execute(
            "SELECT id, name FROM companies WHERE deleted_at IS NULL AND lower(document_email) = ? LIMIT 1",
            (document_email,),
        ).fetchone()
        if duplicate_company:
            return jsonify({
                "error": "duplicate_document_email",
                "message": "Diese Dokument-E-Mail ist bereits einer anderen Firma zugeordnet.",
                "conflictCompanyId": duplicate_company["id"],
                "conflictCompanyName": duplicate_company["name"],
            }), 409

    if turnstile_endpoint:
        db.execute("UPDATE settings SET turnstile_endpoint = ? WHERE id = 1", (turnstile_endpoint,))
    invoice_email_lang = clean_text_input(payload.get("invoiceEmailLang", "de") or "de", max_len=8)
    if invoice_email_lang not in ("de", "en", "fr"):
        invoice_email_lang = "de"
    db.execute(
        "INSERT INTO companies (id, name, customer_number, contact, billing_email, document_email, access_host, branding_preset, plan, status, invoice_email_lang) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            company_id,
            company_name,
            company_customer_number,
            company_contact,
            billing_email,
            document_email,
            access_host,
            branding_preset,
            normalize_company_plan(payload.get("plan", "tageskarte")),
            company_status,
            invoice_email_lang,
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
                "Gate North",
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
                "Gate South",
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


@app.get("/api/workers/current-visitors")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def get_current_visitors():
    """Gibt Besucher zurück die sich aktuell auf dem Gelände befinden (visit_end_at in der Zukunft)."""
    db = get_db()
    user = g.current_user
    company_filter = "" if user["role"] == "superadmin" else f" AND w.company_id = '{user.get('company_id', '')}'"
    now_str = datetime.utcnow().isoformat()
    rows = db.execute(
        f"""SELECT w.id, w.first_name, w.last_name, w.badge_id, w.visitor_company,
                   w.visit_purpose, w.host_name, w.visit_end_at, w.status
            FROM workers w
            WHERE w.worker_type = 'visitor'
              AND w.deleted_at IS NULL
              AND (w.visit_end_at = '' OR w.visit_end_at > ?)
              AND w.status != 'gesperrt'
              {company_filter}
            ORDER BY w.visit_end_at ASC""",
        (now_str,)
    ).fetchall()
    result = []
    for r in rows:
        expires_at = r["visit_end_at"] or ""
        minutes_left = None
        if expires_at:
            try:
                delta = datetime.fromisoformat(expires_at) - datetime.utcnow()
                minutes_left = int(delta.total_seconds() / 60)
            except Exception:
                pass
        result.append({
            "id": r["id"],
            "name": f"{r['first_name']} {r['last_name']}",
            "badge_id": r["badge_id"],
            "visitor_company": r["visitor_company"],
            "visit_purpose": r["visit_purpose"],
            "host_name": r["host_name"],
            "visit_end_at": expires_at,
            "minutes_left": minutes_left,
        })
    return jsonify(result)


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
                    host_name, visit_end_at, status, photo_data, badge_id, badge_id_lookup, badge_pin_hash,
                    physical_card_id, deleted_at
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, '', '', '', NULL, 'active', '', ?, ?, '', '', NULL)
                """,
                (worker_id, company_id, first_name, last_name, insurance_number,
                 worker_type, role_value, site_value, valid_until_value, badge_id_value, normalize_badge_id(badge_id_value)),
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
    try:
        base_upload_root = DOCS_UPLOAD_DIR.resolve()
        worker_doc_dir = (DOCS_UPLOAD_DIR / worker_id).resolve()
        if worker_doc_dir != base_upload_root and base_upload_root not in worker_doc_dir.parents:
            raise ValueError("invalid_worker_doc_path")
        worker_doc_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return jsonify({"error": "worker_doc_folder_create_failed", "detail": str(exc)}), 500

    db.execute(
        """
        INSERT INTO workers (
            id, company_id, subcompany_id, first_name, last_name, insurance_number, worker_type, role, site, valid_until, visitor_company, visit_purpose, host_name, visit_end_at, status, photo_data, badge_id, badge_id_lookup, badge_pin_hash, physical_card_id, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            normalize_badge_id(badge_id_value),
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
        SET company_id = ?, subcompany_id = ?, first_name = ?, last_name = ?, insurance_number = ?, worker_type = ?, role = ?, site = ?, valid_until = ?, visitor_company = ?, visit_purpose = ?, host_name = ?, visit_end_at = ?, status = ?, photo_data = ?, badge_pin_hash = ?, physical_card_id = ?, contact_email = ?, leave_balance = ?
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
            clean_text_input(payload.get("contactEmail", worker["contact_email"] or "") or "", max_len=200),
            max(0, int(payload.get("leaveBalance", worker["leave_balance"] if worker["leave_balance"] is not None else 30))),
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


@app.patch("/api/workers/bulk-status")
@require_auth
@require_roles("superadmin", "company-admin")
def bulk_update_worker_status():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids", [])
    status = payload.get("status", "")
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "missing_ids"}), 400
    if status not in ("aktiv", "inaktiv", "gesperrt"):
        return jsonify({"error": "invalid_status"}), 400
    ids = [str(i) for i in ids if isinstance(i, str) and i.strip()][:200]
    db = get_db()
    updated = 0
    for worker_id in ids:
        worker = db.execute("SELECT id, company_id, deleted_at FROM workers WHERE id = ?", (worker_id,)).fetchone()
        if not worker or worker["deleted_at"]:
            continue
        if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
            continue
        db.execute("UPDATE workers SET status = ? WHERE id = ?", (status, worker_id))
        updated += 1
    db.commit()
    log_audit("workers.bulk_status", f"{updated} Mitarbeiter Status auf '{status}' gesetzt", actor=g.current_user)
    return jsonify({"ok": True, "updated": updated})


@app.post("/api/workers/bulk-delete")
@require_auth
@require_roles("superadmin", "company-admin")
def bulk_delete_workers():
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids", [])
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "missing_ids"}), 400
    ids = [str(i) for i in ids if isinstance(i, str) and i.strip()][:200]
    db = get_db()
    deleted = 0
    for worker_id in ids:
        worker = db.execute("SELECT id, company_id, deleted_at FROM workers WHERE id = ?", (worker_id,)).fetchone()
        if not worker or worker["deleted_at"]:
            continue
        if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
            continue
        db.execute("UPDATE workers SET deleted_at = ? WHERE id = ?", (now_iso(), worker_id))
        deleted += 1
    db.commit()
    log_audit("workers.bulk_deleted", f"{deleted} Mitarbeiter gelöscht", actor=g.current_user)
    return jsonify({"ok": True, "deleted": deleted})


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


@app.post("/api/workers/<worker_id>/lock")
@require_auth
def set_worker_lock(worker_id):
    role = g.current_user.get("role")
    if role not in ("superadmin", "company-admin", "turnstile"):
        return jsonify({"error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status", "")).strip().lower()
    if status not in ("gesperrt", "aktiv"):
        return jsonify({"error": "invalid_status"}), 400

    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404
    if worker["deleted_at"]:
        return jsonify({"error": "worker_deleted"}), 400

    if role != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403

    db.execute("UPDATE workers SET status = ? WHERE id = ?", (status, worker_id))
    db.commit()
    action = "worker.locked" if status == "gesperrt" else "worker.unlocked"
    log_audit(action, f"Mitarbeiter {worker_id} -> {status}", target_type="worker", target_id=worker_id, company_id=worker["company_id"], actor=g.current_user)
    return jsonify({"ok": True, "status": status})


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
    if g.current_user["role"] != "superadmin":
        _pin_plan = get_company_plan(db, worker["company_id"])
        if not company_has_feature(_pin_plan, "nfc_badges"):
            return feature_not_available_response("nfc_badges", _pin_plan)
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
        "leaveBalance": int(worker["leave_balance"]) if (hasattr(worker, "keys") and "leave_balance" in worker.keys() and worker["leave_balance"] is not None) else 30,
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

    # Erst prüfen ob für diesen Mitarbeiter überhaupt Baustellen-Koordinaten existieren.
    # Wenn nicht, gibt es keine Basis für einen Geofence-Check → Login erlauben.
    site_coordinates = ensure_worker_site_coordinates(db, worker)
    if not site_coordinates:
        return None

    # Baustellen-Koordinaten bekannt → jetzt Location aus dem Request prüfen
    location = payload.get("location") if isinstance(payload, dict) else None
    if not isinstance(location, dict):
        raise ValueError("worker_geolocation_required")

    device_latitude = _normalize_float(location.get("latitude"))
    device_longitude = _normalize_float(location.get("longitude"))
    if device_latitude is None or device_longitude is None:
        raise ValueError("worker_geolocation_required")

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


def normalize_work_time_value(value):
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", normalized):
        raise ValueError("invalid_work_time")
    return normalized


def get_effective_work_start_time(db, worker_id):
    row = db.execute(
        """
        SELECT c.work_start_time AS company_work_start_time, s.work_start_time AS global_work_start_time
        FROM workers w
        LEFT JOIN companies c ON c.id = w.company_id
        LEFT JOIN settings s ON s.id = 1
        WHERE w.id = ?
        LIMIT 1
        """,
        (worker_id,),
    ).fetchone()
    if not row:
        return ""
    return str(row["company_work_start_time"] or row["global_work_start_time"] or "").strip()


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


def create_access_log_entry(db, worker_id, direction, gate, note, timestamp_value=None, worker_type="worker"):
    log_id = f"log-{secrets.token_hex(6)}"
    late = 0
    if direction == "check-in" and worker_type != "visitor":
        try:
            work_start = get_effective_work_start_time(db, worker_id)
            if work_start and ":" in work_start:
                from datetime import datetime as _dt
                now_local = _dt.now()
                sh, sm = int(work_start.split(":")[0]), int(work_start.split(":")[1])
                if (now_local.hour, now_local.minute) > (sh, sm):
                    late = 1
        except Exception:
            pass
    db.execute(
        "INSERT INTO access_logs (id, worker_id, direction, gate, note, timestamp, checked_in_late) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            log_id,
            worker_id,
            direction,
            gate,
            note,
            timestamp_value or now_iso(),
            late,
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
    db = get_db()
    worker = db.execute("SELECT company_id FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if worker:
        plan_value = get_company_plan(db, worker["company_id"])
        if not company_has_feature(plan_value, "worker_app"):
            return feature_not_available_response("worker_app", plan_value)
    payload, error_response = build_worker_app_access_payload(db, worker_id, g.current_user)
    if error_response:
        return error_response
    return jsonify(payload)


@app.post("/api/workers/<worker_id>/app-access")
@require_auth
@require_roles("superadmin", "company-admin")
def create_worker_app_access(worker_id):
    db = get_db()
    worker_plan_row = db.execute("SELECT company_id FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if worker_plan_row:
        plan_value = get_company_plan(db, worker_plan_row["company_id"])
        if not company_has_feature(plan_value, "worker_app"):
            return feature_not_available_response("worker_app", plan_value)
    payload, error_response = build_worker_app_access_payload(db, worker_id, g.current_user)
    if error_response:
        return error_response
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    log_audit("worker.app_access_created", f"Mitarbeiter-App-Link fuer {worker_id} erzeugt", target_type="worker", target_id=worker_id, company_id=worker["company_id"], actor=g.current_user)
    return jsonify(payload)


@app.get("/api/workers/<worker_id>/qr.png")
@require_auth
@require_roles("superadmin", "company-admin")
def worker_badge_qr(worker_id):
    """QR-Code fuer den Worker-Badge generieren (Badge-ID als QR)."""
    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ? AND deleted_at IS NULL", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404
    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden"}), 403
    badge_id = worker["badge_id"]
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(badge_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "-", badge_id.lower())
    return Response(
        buf.getvalue(),
        mimetype="image/png",
        headers={"Content-Disposition": f'attachment; filename="qr-{safe_name}.png"'},
    )


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
            fallback_badge_row = db.execute(
                "SELECT badge_id FROM workers WHERE id = ?",
                (token_row["worker_id"],),
            ).fetchone()
            return jsonify({
                "error": "access_token_already_used",
                "message": "Dieser Besucherkarten-Link wurde bereits genutzt.",
                "badgeId": (fallback_badge_row["badge_id"] if fallback_badge_row else ""),
            }), 401

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
        plan_value = get_company_plan(db, worker["company_id"])
        if not company_has_feature(plan_value, "worker_app"):
            return feature_not_available_response("worker_app", plan_value)

        # Einmal-Link (QR) soll unmittelbar funktionieren. Standortpruefung bleibt
        # weiterhin fuer Badge-ID/PIN-Login aktiv (siehe unten im badge_id-Branch).

        consumed_at = now_iso()
        consumed = db.execute(
            "UPDATE worker_app_tokens SET revoked_at = ? WHERE token = ? AND revoked_at IS NULL",
            (consumed_at, access_token),
        )
        if int(consumed.rowcount or 0) == 0:
            fallback_badge_row = db.execute(
                "SELECT badge_id FROM workers WHERE id = ?",
                (token_row["worker_id"],),
            ).fetchone()
            return jsonify({
                "error": "access_token_already_used",
                "message": "Dieser Besucherkarten-Link wurde bereits genutzt.",
                "badgeId": (fallback_badge_row["badge_id"] if fallback_badge_row else ""),
            }), 401

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
        WHERE badge_id_lookup = ?
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
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "worker_app"):
        return feature_not_available_response("worker_app", plan_value)

    try:
        validate_worker_login_distance_or_raise(db, worker, payload)
    except ValueError as exc:
        error_code = str(exc)
        if error_code == "worker_geolocation_required":
            return jsonify({"error": error_code, "message": "Bitte Standortfreigabe aktivieren und direkt am Standort anmelden."}), 400
        if error_code == "site_location_unavailable":
            return jsonify({"error": error_code, "message": "Fuer diese Baustelle konnten noch keine Koordinaten ermittelt werden. Bitte Admin informieren."}), 403
        raise
    except PermissionError as exc:
        distance_text = str(exc).split(":", 1)[1] if ":" in str(exc) else ""
        return jsonify({"error": "outside_site_radius", "message": f"Login nur am Standort moeglich (max. {WORKER_LOGIN_MAX_DISTANCE_METERS} m). Aktuell ca. {distance_text} m entfernt."}), 403

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
    # Urlaubstage: genommene Tage dieses Jahr (genehmigt, Typ=urlaub)
    from datetime import datetime as _dt
    this_year = str(_dt.now().year)
    taken_rows = db.execute(
        "SELECT SUM(days_count) as total FROM leave_requests WHERE worker_id = ? AND status = 'genehmigt' AND type = 'urlaub' AND start_date LIKE ?",
        (worker["id"], f"{this_year}-%")
    ).fetchone()
    leave_taken = int(taken_rows["total"] or 0)
    leave_balance = int(worker["leave_balance"]) if (worker["leave_balance"] is not None) else 30

    # Zu-spaet-Benachrichtigung: letzter Check-in heute war zu spaet?
    today_prefix = _dt.now().strftime("%Y-%m-%d")
    late_check = db.execute(
        """
        SELECT checked_in_late, timestamp FROM access_logs
        WHERE worker_id = ? AND direction = 'check-in' AND timestamp LIKE ?
        ORDER BY timestamp DESC LIMIT 1
        """,
        (worker["id"], f"{today_prefix}%"),
    ).fetchone()
    checked_in_late_today = False
    late_minutes = 0
    if late_check and int(late_check["checked_in_late"] or 0) == 1:
        checked_in_late_today = True
        try:
            work_start = get_effective_work_start_time(db, worker["id"])
            if work_start and ":" in work_start:
                checkin_time = late_check["timestamp"][11:16]  # "HH:MM"
                sh, sm = int(work_start.split(":")[0]), int(work_start.split(":")[1])
                ch, cm = int(checkin_time.split(":")[0]), int(checkin_time.split(":")[1])
                late_minutes = max(0, (ch * 60 + cm) - (sh * 60 + sm))
        except Exception:
            pass
    return jsonify(
        {
            "worker": serialize_worker_for_app(worker),
            "company": {
                "name": company["name"] if company else "",
                "brandingPreset": normalize_branding_preset(company["branding_preset"] if company and "branding_preset" in company.keys() else "construction"),
            },
            "subcompany": {
                "name": subcompany["name"] if subcompany else "",
            },
            "settings": {
                "platformName": setting["platform_name"],
                "operatorName": setting["operator_name"],
                "workerPassLockEnabled": int(setting["worker_pass_lock_enabled"]) if setting and "worker_pass_lock_enabled" in setting.keys() else 0,
            },
            "sessionExpiresAt": getattr(g, "worker_session_expires_at", ""),
            "cardType": normalize_worker_type(worker["worker_type"]),
            "leaveStats": {
                "balance": leave_balance,
                "taken": leave_taken,
                "remaining": max(0, leave_balance - leave_taken),
            },
            "lateCheckIn": {
                "today": checked_in_late_today,
                "minutes": late_minutes,
            },
            "planFeatures": get_plan_features(company["plan"] if company else "starter"),
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


_pin_fail_counts: dict = {}  # worker_id -> [fail_count, window_start_ts]
_PIN_MAX_ATTEMPTS = 5
_PIN_LOCKOUT_SECONDS = 300  # 5 minutes


def _prune_pin_fail_counts():
    """Remove expired entries to prevent unbounded memory growth."""
    now = time.time()
    expired = [k for k, v in _pin_fail_counts.items() if now - v[1] >= _PIN_LOCKOUT_SECONDS]
    for k in expired:
        _pin_fail_counts.pop(k, None)


@app.post("/api/worker-app/verify-pin")
@require_worker_session
def worker_app_verify_pin():
    worker = g.worker
    worker_id = worker["id"]
    now = time.time()

    # Periodically prune stale entries (every ~100 calls)
    if len(_pin_fail_counts) > 100:
        _prune_pin_fail_counts()

    # Rate-limit: max 5 failed attempts per worker per 5-minute window
    entry = _pin_fail_counts.get(worker_id)
    if entry:
        fail_count, window_start = entry
        if now - window_start < _PIN_LOCKOUT_SECONDS:
            if fail_count >= _PIN_MAX_ATTEMPTS:
                retry_after = int(_PIN_LOCKOUT_SECONDS - (now - window_start))
                return jsonify({"valid": False, "error": "too_many_attempts", "retryAfter": retry_after}), 429
        else:
            # Window expired — reset
            _pin_fail_counts.pop(worker_id, None)

    payload = request.get_json(silent=True) or {}
    pin_candidate = str(payload.get("pin") or "").strip()
    if not pin_candidate:
        return jsonify({"valid": False, "error": "missing_pin"}), 400
    stored_hash = worker["badge_pin_hash"] or ""
    if not stored_hash:
        return jsonify({"valid": False, "error": "no_pin_set"}), 400
    from werkzeug.security import check_password_hash
    valid = check_password_hash(stored_hash, pin_candidate)
    if not valid:
        cur_entry = _pin_fail_counts.get(worker_id)
        if cur_entry and now - cur_entry[1] < _PIN_LOCKOUT_SECONDS:
            _pin_fail_counts[worker_id] = [cur_entry[0] + 1, cur_entry[1]]
        else:
            _pin_fail_counts[worker_id] = [1, now]
    else:
        _pin_fail_counts.pop(worker_id, None)
    return jsonify({"valid": valid})


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
    company_customer_number = sanitize_customer_number(
        payload.get("customerNumber", company["customer_number"] if "customer_number" in company.keys() else ""),
        max_len=12,
    )
    if not company_customer_number:
        company_customer_number = sanitize_customer_number(company["customer_number"] if "customer_number" in company.keys() else "", max_len=12)
    if not company_customer_number:
        company_customer_number = get_next_customer_number(db)
    company_contact = clean_text_input(payload.get("contact", company["contact"]), max_len=180)
    company_billing_email = clean_text_input(payload.get("billingEmail", company["billing_email"]), max_len=160)
    company_billing_street = clean_text_input(payload.get("billingStreet", company["billing_street"] if "billing_street" in company.keys() else ""), max_len=200)
    company_billing_zip_city = clean_text_input(payload.get("billingZipCity", company["billing_zip_city"] if "billing_zip_city" in company.keys() else ""), max_len=120)
    company_document_email = clean_text_input(payload.get("documentEmail", company["document_email"]), max_len=160)
    if not company_document_email:
        company_document_email = suggest_company_document_email(company_name)
    company_document_email = normalize_email_address(company_document_email)
    company_access_host = clean_text_input((payload.get("accessHost") or payload.get("access_host") or company["access_host"]), max_len=180)
    company_branding_preset = normalize_branding_preset(payload.get("brandingPreset") or payload.get("branding_preset") or company["branding_preset"])
    company_status = clean_text_input(payload.get("status", company["status"]), max_len=32) or company["status"]
    company_invoice_email_lang = clean_text_input(payload.get("invoiceEmailLang", company["invoice_email_lang"] if "invoice_email_lang" in company.keys() else "de") or "de", max_len=8)
    if company_invoice_email_lang not in ("de", "en", "fr", "tr", "ar", "es", "it", "pl"):
        company_invoice_email_lang = "de"

    current_document_email = normalize_email_address(company["document_email"] or "")
    duplicate_customer_no = db.execute(
        "SELECT id, name FROM companies WHERE id != ? AND COALESCE(customer_number, '') = ? LIMIT 1",
        (company_id, company_customer_number),
    ).fetchone()
    if duplicate_customer_no:
        return jsonify({
            "error": "duplicate_customer_number",
            "message": "Diese Kundennummer ist bereits vergeben.",
            "conflictCompanyId": duplicate_customer_no["id"],
            "conflictCompanyName": duplicate_customer_no["name"],
        }), 409

    if company_document_email and company_document_email != current_document_email:
        duplicate_company = db.execute(
            "SELECT id, name FROM companies WHERE deleted_at IS NULL AND id != ? AND lower(document_email) = ? LIMIT 1",
            (company_id, company_document_email),
        ).fetchone()
        if duplicate_company:
            return jsonify({
                "error": "duplicate_document_email",
                "message": "Diese Dokument-E-Mail ist bereits einer anderen Firma zugeordnet.",
                "conflictCompanyId": duplicate_company["id"],
                "conflictCompanyName": duplicate_company["name"],
            }), 409

    db.execute(
        "UPDATE companies SET name = ?, customer_number = ?, contact = ?, billing_email = ?, billing_street = ?, billing_zip_city = ?, document_email = ?, access_host = ?, branding_preset = ?, plan = ?, status = ?, invoice_email_lang = ? WHERE id = ?",
        (
            company_name,
            company_customer_number,
            company_contact,
            company_billing_email,
            company_billing_street,
            company_billing_zip_city,
            company_document_email,
            company_access_host,
            company_branding_preset,
            payload.get("plan", company["plan"]),
            company_status,
            company_invoice_email_lang,
            company_id,
        ),
    )
    rematch_inbox_company_links(db, company_id=company_id)
    db.commit()
    log_audit("company.updated", f"Firma {company_id} aktualisiert", target_type="company", target_id=company_id, company_id=company_id, actor=g.current_user)
    return jsonify({"ok": True})


@app.put("/api/companies/<company_id>/work-times")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def update_company_work_times(company_id):
    db = get_db()
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "company_not_found"}), 404

    user = g.current_user
    user_role = str(user.get("role") or "").strip().lower()
    if user_role != "superadmin" and str(user.get("company_id") or "") != str(company_id):
        return jsonify({"error": "forbidden_company"}), 403

    payload = request.get_json(silent=True) or {}
    try:
        work_start_time = normalize_work_time_value(payload.get("workStartTime"))
        work_end_time = normalize_work_time_value(payload.get("workEndTime"))
    except ValueError:
        return jsonify({"error": "invalid_work_time"}), 400

    db.execute(
        "UPDATE companies SET work_start_time = ?, work_end_time = ? WHERE id = ?",
        (work_start_time, work_end_time, company_id),
    )
    db.commit()

    log_audit(
        "company.work_times.updated",
        f"Arbeitszeiten fuer Firma {company_id} aktualisiert",
        target_type="company",
        target_id=company_id,
        company_id=company_id,
        actor=user,
    )

    return jsonify(
        {
            "ok": True,
            "companyId": company_id,
            "workStartTime": work_start_time,
            "workEndTime": work_end_time,
        }
    )


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


@app.post("/api/companies/<company_id>/set-admin-password")
@require_auth
@require_roles("superadmin")
def set_company_admin_password(company_id):
    """Superadmin setzt das Passwort des Firmen-Admins direkt (ohne E-Mail)."""
    payload = request.get_json(silent=True) or {}
    new_password = (payload.get("newPassword") or "").strip()
    if len(new_password) < 8:
        return jsonify({"ok": False, "error": "password_too_short"}), 400

    db = get_db()
    admin_user = db.execute(
        "SELECT id, username FROM users WHERE company_id = ? AND role = 'company-admin' LIMIT 1",
        (company_id,)
    ).fetchone()
    if not admin_user:
        return jsonify({"ok": False, "error": "admin_not_found"}), 404

    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), admin_user["id"])
    )
    db.execute("DELETE FROM sessions WHERE user_id = ?", (admin_user["id"],))
    db.commit()
    log_audit(
        "superadmin.set_company_admin_password",
        f"Superadmin setzte Passwort fuer Company-Admin {admin_user['username']} (Firma {company_id})",
        target_type="user",
        target_id=admin_user["id"],
    )
    return jsonify({"ok": True, "username": admin_user["username"]})


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


# ── Worker-Statistiken ────────────────────────────────────────────────────────

@app.get("/api/workers/stats")
@require_auth
@require_roles("superadmin", "company-admin")
def worker_stats():
    """Statistiken ueber Mitarbeiter: Status-Verteilung, Top-Baustellen, Tore, Check-In-Stunden."""
    user = g.current_user
    db = get_db()
    company_filter = ""
    params: list = []
    access_filter = ""
    access_params: list = []
    if user["role"] != "superadmin":
        cid = user.get("company_id")
        company_filter = "AND w.company_id = ?"
        params.append(cid)
        access_filter = "AND w.company_id = ?"
        access_params.append(cid)

    status_rows = db.execute(
        f"SELECT COALESCE(status,'unbekannt') AS status, COUNT(*) AS cnt FROM workers w WHERE w.deleted_at IS NULL {company_filter} GROUP BY status ORDER BY cnt DESC",
        params,
    ).fetchall()

    site_rows = db.execute(
        f"SELECT site, COUNT(*) AS cnt FROM workers w WHERE w.deleted_at IS NULL AND TRIM(COALESCE(site,'')) != '' {company_filter} GROUP BY site ORDER BY cnt DESC LIMIT 10",
        params,
    ).fetchall()

    type_rows = db.execute(
        f"SELECT COALESCE(worker_type,'worker') AS worker_type, COUNT(*) AS cnt FROM workers w WHERE w.deleted_at IS NULL {company_filter} GROUP BY worker_type",
        params,
    ).fetchall()

    total_count = db.execute(
        f"SELECT COUNT(*) AS cnt FROM workers w WHERE w.deleted_at IS NULL {company_filter}",
        params,
    ).fetchone()["cnt"]

    gate_rows = db.execute(
        f"""SELECT COALESCE(NULLIF(TRIM(al.gate),''), 'Unbekannt') AS gate, COUNT(*) AS cnt
            FROM access_logs al JOIN workers w ON w.id = al.worker_id
            WHERE DATE(al.timestamp) >= DATE('now', '-30 day') {access_filter}
            GROUP BY gate ORDER BY cnt DESC LIMIT 10""",
        access_params,
    ).fetchall()

    hour_rows = db.execute(
        f"""SELECT CAST(strftime('%H', al.timestamp) AS INTEGER) AS hour, COUNT(*) AS cnt
            FROM access_logs al JOIN workers w ON w.id = al.worker_id
            WHERE al.direction = 'check-in' AND DATE(al.timestamp) >= DATE('now', '-30 day') {access_filter}
            GROUP BY hour ORDER BY hour ASC""",
        access_params,
    ).fetchall()

    return jsonify({
        "totalWorkers": total_count,
        "byStatus": [{"status": r["status"], "count": r["cnt"]} for r in status_rows],
        "bySite": [{"site": r["site"] or "Keine Baustelle", "count": r["cnt"]} for r in site_rows],
        "byGate": [{"gate": r["gate"], "count": r["cnt"]} for r in gate_rows],
        "checkInsByHour": [{"hour": r["hour"], "count": r["cnt"]} for r in hour_rows],
        "byType": [{"type": r["worker_type"], "count": r["cnt"]} for r in type_rows],
    })


# ── Worker-Foto Validierung ───────────────────────────────────────────────────

@app.post("/api/workers/validate-photo")
@require_auth
@require_roles("superadmin", "company-admin")
def validate_worker_photo():
    """Basis-Validierung eines Worker-Fotos per PIL (Abmessungen, Helligkeit, Kontrast)."""
    payload = request.get_json(silent=True) or {}
    photo_data = str(payload.get("photoData") or "").strip()
    if not photo_data:
        return jsonify({"valid": False, "score": 0, "errors": ["Kein Foto vorhanden"], "warnings": [], "meta": {}})

    if photo_data.startswith("data:"):
        try:
            _header, b64_data = photo_data.split(",", 1)
        except ValueError:
            return jsonify({"valid": False, "score": 0, "errors": ["Ungültiges Datenformat"], "warnings": [], "meta": {}})
    else:
        b64_data = photo_data

    try:
        img_bytes = base64.b64decode(b64_data)
    except Exception:
        return jsonify({"valid": False, "score": 0, "errors": ["Base64-Dekodierung fehlgeschlagen"], "warnings": [], "meta": {}})

    errors: list[str] = []
    warnings: list[str] = []
    size_kb = len(img_bytes) / 1024

    if size_kb < 5:
        errors.append("Bild zu klein (< 5 KB) – möglicherweise kein echtes Foto")
    elif size_kb < 20:
        warnings.append("Bildgröße sehr gering (< 20 KB) – niedrige Qualität möglich")
    if size_kb > 5000:
        warnings.append("Bild sehr groß (> 5 MB) – Komprimierung empfohlen")

    try:
        from PIL import Image as _PilImage
        img = _PilImage.open(io.BytesIO(img_bytes))
        w, h = img.size
        img_format = img.format or "unbekannt"

        if w < 100 or h < 100:
            errors.append(f"Auflösung zu niedrig ({w}×{h} px) – mindestens 100×100 px erforderlich")
        elif w < 200 or h < 250:
            warnings.append(f"Auflösung gering ({w}×{h} px) – empfohlen: mind. 200×300 px")

        ratio = w / h if h > 0 else 1.0
        if ratio < 0.3 or ratio > 3.0:
            warnings.append(f"Ungewöhnliches Seitenverhältnis ({ratio:.2f}) – Portraitformat empfohlen")

        thumb = img.convert("RGB").resize((50, 50))
        pixels = list(thumb.getdata())
        r_vals = [p[0] for p in pixels]
        g_vals = [p[1] for p in pixels]
        b_vals = [p[2] for p in pixels]
        avg_brightness = (sum(r_vals) + sum(g_vals) + sum(b_vals)) / (len(pixels) * 3)

        def _var(vals):
            avg = sum(vals) / len(vals)
            return sum((v - avg) ** 2 for v in vals) / len(vals)

        total_variance = _var(r_vals) + _var(g_vals) + _var(b_vals)

        if avg_brightness < 20:
            errors.append("Foto zu dunkel – bitte ein besser belichtetes Foto verwenden")
        elif avg_brightness > 235:
            errors.append("Foto überbelichtet – bitte Belichtung korrigieren")
        elif avg_brightness < 50:
            warnings.append("Foto wirkt dunkel – bessere Beleuchtung empfohlen")

        if total_variance < 100:
            errors.append("Foto zeigt fast keine Details – möglicherweise ein einfarbiges Bild")
        elif total_variance < 500:
            warnings.append("Geringer Kontrast – bitte prüfen, ob ein echtes Portraitfoto vorhanden ist")

        score = max(0, min(100, 100 - len(errors) * 25 - len(warnings) * 10))
        return jsonify({
            "valid": len(errors) == 0,
            "score": score,
            "errors": errors,
            "warnings": warnings,
            "meta": {"width": w, "height": h, "sizeKb": round(size_kb, 1),
                     "avgBrightness": round(avg_brightness, 1), "format": img_format},
        })
    except ImportError:
        score = max(0, min(100, 70 - len(errors) * 25))
        return jsonify({"valid": len(errors) == 0, "score": score,
                        "errors": errors, "warnings": warnings + ["Erweiterte Bildanalyse nicht verfügbar"], "meta": {}})
    except Exception as exc:
        errors.append(f"Bildverarbeitung fehlgeschlagen: {str(exc)[:80]}")
        return jsonify({"valid": False, "score": 0, "errors": errors, "warnings": warnings, "meta": {}})


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
    platform_label = str(settings["platform_name"] or "BauPass").strip() or "BauPass"
    operator_label = str(settings["operator_name"] or platform_label).strip() or platform_label
    smtp_sender_name = str(settings["smtp_sender_name"] or operator_label).strip() or operator_label
    msg["Subject"] = f"Passwort zurücksetzen – {platform_label}"
    msg["From"] = f"{smtp_sender_name} <{smtp_sender}>" if smtp_sender else smtp_sender_name

    # Empfänger-Priorität: 1) users.email, 2) billing_email der Firma, 3) username als Fallback
    user_email = (user["email"] or "").strip() if user["email"] else ""
    if not user_email:
        company_row = db.execute("SELECT billing_email FROM companies WHERE id = ?", (user["company_id"] or "",)).fetchone()
        user_email = (company_row["billing_email"] if company_row else "") or username
    recipient = user_email or username
    msg["To"] = recipient

    _user_name_safe = html.escape(str(user["name"] or username))
    _operator_safe = html.escape(operator_label)
    _platform_safe = html.escape(platform_label)
    _link_safe = html.escape(reset_link)

    text_body = (
        f"Hallo {user['name']},\n\nKlicke auf folgenden Link, um dein Passwort zurückzusetzen (gültig 2 Stunden):\n\n{reset_link}\n\nWenn du das nicht angefordert hast, ignoriere diese E-Mail.\n\nViele Grüße\n{operator_label}"
    )
    html_body = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 16px;">
    <tr><td align="center">
      <table width="100%" style="max-width:520px;background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
        <tr><td style="background:#1e293b;padding:24px 32px;">
          <p style="margin:0;font-size:1.2rem;font-weight:700;color:#ffffff;">{_platform_safe}</p>
          <p style="margin:4px 0 0;font-size:0.85rem;color:#94a3b8;">Passwort zurücksetzen</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <p style="margin:0 0 16px;font-size:1rem;color:#1e293b;">Hallo {_user_name_safe},</p>
          <p style="margin:0 0 24px;font-size:0.95rem;color:#374151;line-height:1.6;">
            du hast eine Anfrage zum Zurücksetzen deines Passworts gestellt.<br>
            Klicke auf den Button, um ein neues Passwort festzulegen. Der Link ist <strong>2 Stunden gültig</strong>.
          </p>
          <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
            <tr><td style="background:#2563eb;border-radius:8px;padding:14px 28px;">
              <a href="{_link_safe}" style="color:#ffffff;text-decoration:none;font-size:1rem;font-weight:600;">Passwort zurücksetzen</a>
            </td></tr>
          </table>
          <p style="margin:0 0 8px;font-size:0.8rem;color:#6b7280;">Oder kopiere diesen Link in deinen Browser:</p>
          <p style="margin:0 0 24px;font-size:0.78rem;color:#6b7280;word-break:break-all;">{_link_safe}</p>
          <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 16px;">
          <p style="margin:0;font-size:0.8rem;color:#9ca3af;">
            Wenn du kein Passwort-Reset angefordert hast, kannst du diese E-Mail ignorieren.<br>
            Dein Passwort wurde nicht geändert.
          </p>
        </td></tr>
        <tr><td style="background:#f8fafc;padding:16px 32px;border-top:1px solid #e5e7eb;">
          <p style="margin:0;font-size:0.8rem;color:#6b7280;">Mit freundlichen Grüßen · {_operator_safe}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    def _try_password_reset_api_fallback():
        sender_email = smtp_sender
        if not sender_email:
            sender_email = (settings["brevo_from_email"] or "").strip() if settings and "brevo_from_email" in settings.keys() else ""
        if not sender_email:
            sender_email = (settings["resend_from_email"] or "").strip() if settings and "resend_from_email" in settings.keys() else ""
        if not sender_email:
            sender_email = _normalize_env_value(_resend_key_cache.get("brevo_from_email") or "")
        if not sender_email:
            sender_email = _normalize_env_value(_resend_key_cache.get("from_email") or "")
        return _send_via_any_api(
            msg["Subject"],
            sender_email,
            smtp_sender_name,
            recipient,
            text_body,
            html_body,
        )

    if not smtp_host or not smtp_sender:
        fallback_ok, fallback_error, fallback_provider = _try_password_reset_api_fallback()
        if fallback_ok:
            log_audit(
                "security.password_reset_requested",
                f"Passwort-Reset angefordert für {username} (versendet via {fallback_provider})",
            )
            return jsonify({"ok": True, "delivery": fallback_provider})
        return jsonify({
            "error": "smtp_not_configured",
            "message": "E-Mail-Versand ist nicht konfiguriert.",
            "detail": fallback_error,
        }), 503

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
        fallback_ok, fallback_error, fallback_provider = _try_password_reset_api_fallback()
        if fallback_ok:
            log_audit(
                "security.password_reset_requested",
                f"Passwort-Reset angefordert für {username} (SMTP fehlgeschlagen, versendet via {fallback_provider})",
            )
            return jsonify({"ok": True, "delivery": fallback_provider, "smtpError": str(exc)})
        return jsonify({"error": "smtp_error", "message": f"{exc} | api_fallback_failed: {fallback_error}"}), 502

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
        generated_badge_id = f"BP-{w['id'][-6:].upper()}"
        db.execute("UPDATE workers SET badge_id = ?, badge_id_lookup = ? WHERE id = ?", (generated_badge_id, normalize_badge_id(generated_badge_id), w["id"]))
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
    db = get_db()
    run_access_maintenance_if_due(db)
    direction = (request.args.get("direction") or "").strip()
    gate = (request.args.get("gate") or "").strip()
    from_date = (request.args.get("from") or "").strip()
    to_date = (request.args.get("to") or "").strip()
    offset = max(int(request.args.get("offset", "0")), 0)
    limit = min(max(int(request.args.get("limit", "1000")), 1), 5000)
    paginated = str(request.args.get("paginated") or "").strip().lower() in {"1", "true", "yes"}

    conditions, params = build_access_filters(g.current_user, direction, gate, from_date, to_date)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = db.execute(
        f"""
        SELECT access_logs.*
        FROM access_logs
        JOIN workers ON workers.id = access_logs.worker_id
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    items = [row_to_dict(row) for row in rows]
    if not paginated:
        return jsonify(items)

    return jsonify(
        {
            "items": items,
            "limit": limit,
            "offset": offset,
            "hasMore": len(items) == limit,
            "filtersApplied": bool(direction or gate or from_date or to_date),
        }
    )


@app.get("/api/access-logs/latest")
@require_auth
def list_latest_access_logs():
    db = get_db()
    run_access_maintenance_if_due(db)

    conditions, params = build_access_filters(g.current_user)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = db.execute(
        f"""
        SELECT id, worker_id, direction, gate, note, timestamp
        FROM (
            SELECT access_logs.id,
                   access_logs.worker_id,
                   access_logs.direction,
                   access_logs.gate,
                   access_logs.note,
                   access_logs.timestamp,
                   ROW_NUMBER() OVER (
                       PARTITION BY access_logs.worker_id
                       ORDER BY access_logs.timestamp DESC, access_logs.id DESC
                   ) AS row_no
            FROM access_logs
            JOIN workers ON workers.id = access_logs.worker_id
            {where_clause}
        ) latest
        WHERE row_no = 1
        ORDER BY timestamp DESC, id DESC
        LIMIT 5000
        """,
        params,
    ).fetchall()

    items = [row_to_dict(row) for row in rows]
    return jsonify(
        {
            "items": items,
            "latest": items[0] if items else None,
        }
    )


@app.get("/api/invoices/access-line-items")
@require_auth
@require_roles("superadmin", "company-admin")
def invoice_access_line_items():
    company_id = clean_id_input(request.args.get("companyId") or "")
    invoice_period = str(request.args.get("invoicePeriod") or "").strip()
    if not company_id:
        return jsonify({"error": "missing_company_id"}), 400

    from_date, to_date = parse_invoice_period_bounds(invoice_period)
    if not from_date or not to_date:
        return jsonify({"items": []})

    db = get_db()
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company or company["deleted_at"]:
        return jsonify({"error": "company_not_available"}), 400
    if g.current_user["role"] != "superadmin" and company_id != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_company"}), 403
    if g.current_user["role"] != "superadmin":
        plan_value = get_company_plan(db, company_id)
        if not company_has_feature(plan_value, "invoicing"):
            return feature_not_available_response("invoicing", plan_value)

    from_iso = f"{from_date.isoformat()}T00:00:00Z"
    to_iso = f"{to_date.isoformat()}T23:59:59.999999Z"
    rows = db.execute(
        """
        SELECT access_logs.worker_id, workers.first_name, workers.last_name, COUNT(*) AS access_count
        FROM access_logs
        JOIN workers ON workers.id = access_logs.worker_id
        WHERE workers.company_id = ?
          AND workers.deleted_at IS NULL
          AND access_logs.timestamp >= ?
          AND access_logs.timestamp <= ?
        GROUP BY access_logs.worker_id, workers.first_name, workers.last_name
        ORDER BY workers.last_name ASC, workers.first_name ASC, access_logs.worker_id ASC
        """,
        (company_id, from_iso, to_iso),
    ).fetchall()

    price_per_access = 2.0
    items = []
    for row in rows:
        access_count = int(row["access_count"] or 0)
        amount = round(access_count * price_per_access, 2)
        worker_name = f"{str(row['first_name'] or '').strip()} {str(row['last_name'] or '').strip()}".strip() or "Unbekannt"
        items.append(
            {
                "workerId": row["worker_id"],
                "workerName": worker_name,
                "accessCount": access_count,
                "amount": amount,
            }
        )

    return jsonify({"items": items})


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
    run_access_maintenance_if_due(get_db())
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
        payload.get("gate", "Gate North"),
        payload.get("note", ""),
        payload.get("timestamp", now_iso()),
        worker_type=str(worker["worker_type"] or "worker"),
    )
    db.commit()
    log_audit("access.booked", f"Zutritt {payload.get('direction', 'check-in')} fuer Worker {worker_id}", target_type="worker", target_id=worker_id, company_id=worker["company_id"], actor=g.current_user)
    row = db.execute("SELECT * FROM access_logs WHERE id = ?", (log_id,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.post("/api/gates/tap")
def gate_tap():
    provided_key = (request.headers.get("X-Gate-Key") or "").strip()
    if not provided_key:
        return jsonify({"error": "gate_unauthorized"}), 401

    db = get_db()
    run_access_maintenance_if_due(db)
    turnstile_user = find_turnstile_by_api_key(db, provided_key)
    if not turnstile_user:
        return jsonify({"error": "gate_unauthorized"}), 401

    # NFC gate tap requires nfc_badges feature (Starter+)
    if turnstile_user.get("company_id"):
        _gate_plan = get_company_plan(db, turnstile_user["company_id"])
        if not company_has_feature(_gate_plan, "nfc_badges"):
            return feature_not_available_response("nfc_badges", _gate_plan)

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

    log_id = create_access_log_entry(db, worker["id"], direction, gate_name, gate_note, timestamp_value, worker_type=str(worker["worker_type"] or "worker"))
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
    # ── Mehrsprachigkeit ─────────────────────────────────────────────────────────
    try:
        invoice_lang = str(company_row["invoice_email_lang"] if "invoice_email_lang" in company_row.keys() else "de") or "de"
    except Exception:
        invoice_lang = "de"
    if invoice_lang not in ("de", "en", "fr", "tr", "ar", "es", "it", "pl"):
        invoice_lang = "de"
    _inv_no = str(invoice_row["invoice_number"] or "-")
    _INVOICE_I18N = {
        "de": {
            "subject": f"Rechnung von {platform_label} \u2013 {_inv_no}",
            "greeting": "Guten Tag,",
            "intro_plain": f"anbei erhalten Sie Ihre Rechnung Nr.\u00a0{_inv_no} von {platform_label}.\nAlle Details entnehmen Sie bitte dem beigef\u00fcgten PDF-Anhang.",
            "intro_html": (f"anbei erhalten Sie Ihre Rechnung Nr.\u00a0<strong>{html.escape(_inv_no)}</strong> "
                           f"von <strong>{html.escape(platform_label)}</strong>.</p>"
                           f"<p style='margin:0 0 14px;'>Alle Details entnehmen Sie bitte dem beigef\u00fcgten <strong>PDF-Anhang</strong>."),
            "closing": "Mit freundlichen Gr\u00fc\u00dfen",
            "email_header": f"Rechnung von {platform_label}",
        },
        "en": {
            "subject": f"Invoice from {platform_label} \u2013 {_inv_no}",
            "greeting": "Dear Sir or Madam,",
            "intro_plain": f"please find enclosed your invoice No.\u00a0{_inv_no} from {platform_label}.\nAll details are in the attached PDF.",
            "intro_html": (f"please find enclosed your invoice No.\u00a0<strong>{html.escape(_inv_no)}</strong> "
                           f"from <strong>{html.escape(platform_label)}</strong>.</p>"
                           f"<p style='margin:0 0 14px;'>All details are in the attached <strong>PDF</strong>."),
            "closing": "Kind regards",
            "email_header": f"Invoice from {platform_label}",
        },
        "fr": {
            "subject": f"Facture de {platform_label} \u2013 {_inv_no}",
            "greeting": "Madame, Monsieur,",
            "intro_plain": f"veuillez trouver ci-joint votre facture n\u00b0\u00a0{_inv_no} de {platform_label}.\nTous les d\u00e9tails figurent dans le PDF joint.",
            "intro_html": (f"veuillez trouver ci-joint votre facture n\u00b0\u00a0<strong>{html.escape(_inv_no)}</strong> "
                           f"de <strong>{html.escape(platform_label)}</strong>.</p>"
                           f"<p style='margin:0 0 14px;'>Tous les d\u00e9tails figurent dans le <strong>PDF joint</strong>."),
            "closing": "Cordialement",
            "email_header": f"Facture de {platform_label}",
        },
        "tr": {
            "subject": f"{platform_label} faturan\u0131z \u2013 {_inv_no}",
            "greeting": "Say\u0131n M\u00fc\u015fteri,",
            "intro_plain": f"{platform_label} taraf\u0131ndan d\u00fczenlenen {_inv_no} numaral\u0131 faturam\u0131z\u0131 ekte sunuyoruz.\nT\u00fcm ayr\u0131nt\u0131lar ekte yer alan PDF'de bulunmaktad\u0131r.",
            "intro_html": (f"{html.escape(platform_label)} taraf\u0131ndan d\u00fczenlenen <strong>{html.escape(_inv_no)}</strong> "
                           f"numaral\u0131 faturam\u0131z\u0131 ekte sunuyoruz.</p>"
                           f"<p style='margin:0 0 14px;'>T\u00fcm ayr\u0131nt\u0131lar ekte yer alan <strong>PDF</strong>'de bulunmaktad\u0131r."),
            "closing": "Sayg\u0131lar\u0131m\u0131zla",
            "email_header": f"{platform_label} Fatura",
        },
        "ar": {
            "subject": f"\u0641\u0627\u062a\u0648\u0631\u0629 \u0645\u0646 {platform_label} \u2013 {_inv_no}",
            "greeting": "\u0639\u0632\u064a\u0632\u064a \u0627\u0644\u0639\u0645\u064a\u0644,",
            "intro_plain": f"\u064a\u0633\u0639\u062f\u0646\u0627 \u0625\u0631\u0633\u0627\u0644 \u0641\u0627\u062a\u0648\u0631\u062a\u0643\u0645 \u0631\u0642\u0645\u00a0{_inv_no} \u0645\u0646 {platform_label}.\n\u062c\u0645\u064a\u0639 \u0627\u0644\u062a\u0641\u0627\u0635\u064a\u0644 \u0645\u0648\u062c\u0648\u062f\u0629 \u0641\u064a \u0645\u0644\u0641 PDF \u0627\u0644\u0645\u0631\u0641\u0642.",
            "intro_html": (f"\u064a\u0633\u0639\u062f\u0646\u0627 \u0625\u0631\u0633\u0627\u0644 \u0641\u0627\u062a\u0648\u0631\u062a\u0643\u0645 \u0631\u0642\u0645\u00a0<strong>{html.escape(_inv_no)}</strong> "
                           f"\u0645\u0646 <strong>{html.escape(platform_label)}</strong>.</p>"
                           f"<p style='margin:0 0 14px;'>\u062c\u0645\u064a\u0639 \u0627\u0644\u062a\u0641\u0627\u0635\u064a\u0644 \u0641\u064a <strong>PDF</strong> \u0627\u0644\u0645\u0631\u0641\u0642."),
            "closing": "\u0645\u0639 \u0627\u0644\u062a\u062d\u064a\u0627\u062a",
            "email_header": f"\u0641\u0627\u062a\u0648\u0631\u0629 \u0645\u0646 {platform_label}",
        },
        "es": {
            "subject": f"Factura de {platform_label} \u2013 {_inv_no}",
            "greeting": "Estimado/a cliente,",
            "intro_plain": f"adjunto encontrar\u00e1 su factura n.\u00b0\u00a0{_inv_no} de {platform_label}.\nTodos los detalles se encuentran en el PDF adjunto.",
            "intro_html": (f"adjunto encontrar\u00e1 su factura n.\u00b0\u00a0<strong>{html.escape(_inv_no)}</strong> "
                           f"de <strong>{html.escape(platform_label)}</strong>.</p>"
                           f"<p style='margin:0 0 14px;'>Todos los detalles se encuentran en el <strong>PDF adjunto</strong>."),
            "closing": "Atentamente",
            "email_header": f"Factura de {platform_label}",
        },
        "it": {
            "subject": f"Fattura da {platform_label} \u2013 {_inv_no}",
            "greeting": "Gentile Cliente,",
            "intro_plain": f"in allegato trova la sua fattura n.\u00a0{_inv_no} da {platform_label}.\nTutti i dettagli sono nel PDF allegato.",
            "intro_html": (f"in allegato trova la sua fattura n.\u00a0<strong>{html.escape(_inv_no)}</strong> "
                           f"da <strong>{html.escape(platform_label)}</strong>.</p>"
                           f"<p style='margin:0 0 14px;'>Tutti i dettagli sono nel <strong>PDF allegato</strong>."),
            "closing": "Cordiali saluti",
            "email_header": f"Fattura da {platform_label}",
        },
        "pl": {
            "subject": f"Faktura od {platform_label} \u2013 {_inv_no}",
            "greeting": "Szanowny Kliencie,",
            "intro_plain": f"w za\u0142\u0105czeniu przesy\u0142amy faktur\u0119 nr\u00a0{_inv_no} od {platform_label}.\nWszystkie szczeg\u00f3\u0142y znajduj\u0105 si\u0119 w za\u0142\u0105czonym pliku PDF.",
            "intro_html": (f"w za\u0142\u0105czeniu przesy\u0142amy faktur\u0119 nr\u00a0<strong>{html.escape(_inv_no)}</strong> "
                           f"od <strong>{html.escape(platform_label)}</strong>.</p>"
                           f"<p style='margin:0 0 14px;'>Wszystkie szczeg\u00f3\u0142y znajduj\u0105 si\u0119 w za\u0142\u0105czonym <strong>pliku PDF</strong>."),
            "closing": "Z powa\u017caniem",
            "email_header": f"Faktura od {platform_label}",
        },
    }
    _lang = _INVOICE_I18N[invoice_lang]
    mail_subject = _lang["subject"]
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.lib import colors as rl_colors
        from reportlab.pdfgen import canvas as rl_canvas

        pdf_buffer = io.BytesIO()
        pdf = rl_canvas.Canvas(pdf_buffer, pagesize=A4)
        page_w, page_h = A4
        M_L = 20 * mm
        M_R = 20 * mm
        CW  = page_w - M_L - M_R

        brand_primary = sanitize_hex_color(settings_row["invoice_primary_color"], fallback="#2196F3")
        brand_accent  = sanitize_hex_color(settings_row["invoice_accent_color"],  fallback=brand_primary)

        invoice_no   = str(invoice_row["invoice_number"]  or "-")
        invoice_date = str(invoice_row["invoice_date"]     or "-")
        due_date     = str(invoice_row["due_date"]         or "-")
        period       = str(invoice_row["invoice_period"]   or "-")
        company_name = str(company_row["name"]             or "-")
        customer_number = str(company_row["customer_number"] if "customer_number" in company_row.keys() else "").strip()
        if not customer_number:
            customer_number = "-"
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

        c_primary = rl_colors.HexColor(brand_primary)
        c_dark    = rl_colors.HexColor("#1a1a2e")
        c_mid     = rl_colors.HexColor("#555566")
        c_light   = rl_colors.HexColor("#888899")
        c_rule    = rl_colors.HexColor("#e0e0ea")
        c_tbl_hdr_bg = c_primary
        c_stripe  = rl_colors.HexColor("#f5f7fa")

        # ── Logo-Hilfsfunktionen ─────────────────────────────────────
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
                import logging as _logging
                _logging.getLogger("svglib.svglib").setLevel(_logging.ERROR)
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
            return b""

        def _draw_logo_fallback_mark(x, y):
            pdf.setFillColor(c_primary)
            pdf.circle(x + 8 * mm, y + 8 * mm, 7.5 * mm, stroke=0, fill=1)
            pdf.setFillColor(rl_colors.white)
            pdf.setFont("Helvetica-Bold", 9)
            pdf.drawCentredString(x + 8 * mm, y + 5.8 * mm, "BK")
            pdf.setFillColor(c_dark)
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(x + 18 * mm, y + 7.2 * mm, "BauKometra")

        # ════════════════════════════════════════════════════════════
        # FOOTER – 3-spaltig, Trennlinie, immer am Seitenende
        # ════════════════════════════════════════════════════════════
        FOOTER_H = 22 * mm
        FOOTER_Y = 0

        pdf.setStrokeColor(c_rule)
        pdf.setLineWidth(0.5)
        pdf.line(M_L, FOOTER_H, page_w - M_R, FOOTER_H)

        col_w = CW / 3
        # Spalte 1: Adresse
        fy = FOOTER_H - 5 * mm
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColor(c_dark)
        pdf.drawString(M_L, fy, operator_label)
        fy -= 4 * mm
        pdf.setFont("Helvetica", 7)
        pdf.setFillColor(c_mid)
        for ln in [op_street, op_zip_city]:
            if ln:
                pdf.drawString(M_L, fy, ln)
                fy -= 3.8 * mm

        # Spalte 2: Tel/Email
        col2_x = M_L + col_w
        fy2 = FOOTER_H - 5 * mm
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColor(c_dark)
        pdf.drawString(col2_x, fy2, "Kontakt")
        fy2 -= 4 * mm
        pdf.setFont("Helvetica", 7)
        pdf.setFillColor(c_mid)
        for ln in [f"Telefon: {op_phone}" if op_phone else "", f"E-Mail: {op_email}" if op_email else "", op_website]:
            if ln:
                pdf.drawString(col2_x, fy2, ln)
                fy2 -= 3.8 * mm

        # Spalte 3: Steuer/IBAN
        col3_x = M_L + 2 * col_w
        fy3 = FOOTER_H - 5 * mm
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColor(c_dark)
        pdf.drawString(col3_x, fy3, "Bankverbindung")
        fy3 -= 4 * mm
        pdf.setFont("Helvetica", 7)
        pdf.setFillColor(c_mid)
        for ln in [f"St.-Nr.: {op_tax_id}" if op_tax_id else "",
                   f"USt-ID: {op_vat_id}" if op_vat_id else "",
                   f"IBAN: {op_iban}" if op_iban else "",
                   f"BIC: {op_bic}" if op_bic else ""]:
            if ln:
                pdf.drawString(col3_x, fy3, ln)
                fy3 -= 3.8 * mm

        # ════════════════════════════════════════════════════════════
        # HEADER – Logo oben rechts + Firmenname/-slogan
        # ════════════════════════════════════════════════════════════
        LOGO_MAX_W = 48 * mm
        LOGO_MAX_H = 24 * mm
        LOGO_X = page_w - M_R - LOGO_MAX_W
        LOGO_TOP = page_h - 12 * mm

        logo_drawn = False
        # Soft backdrop behind the logo for a cleaner premium look.
        pdf.setFillColor(rl_colors.HexColor("#f8fbff"))
        pdf.setStrokeColor(rl_colors.HexColor("#e2e8f0"))
        pdf.setLineWidth(0.5)
        pdf.roundRect(LOGO_X - 2.2 * mm, LOGO_TOP - LOGO_MAX_H - 2 * mm, LOGO_MAX_W + 4.4 * mm, LOGO_MAX_H + 4 * mm, 3.5 * mm, stroke=1, fill=1)
        try:
            lb = _logo_bytes()
            if lb:
                ir = ImageReader(io.BytesIO(lb))
                pdf.drawImage(ir, LOGO_X, LOGO_TOP - LOGO_MAX_H,
                              width=LOGO_MAX_W, height=LOGO_MAX_H,
                              preserveAspectRatio=True, anchor="ne", mask="auto")
                logo_drawn = True
        except Exception:
            pass
        if not logo_drawn:
            _draw_logo_fallback_mark(LOGO_X, LOGO_TOP - LOGO_MAX_H + 3 * mm)

        # Firmenname unter Logo
        name_y = LOGO_TOP - LOGO_MAX_H - 4 * mm
        pdf.setFont("Helvetica-Bold", 11)
        pdf.setFillColor(c_dark)
        pdf.drawRightString(page_w - M_R, name_y, operator_label)
        pdf.setStrokeColor(c_primary)
        pdf.setLineWidth(0.8)
        pdf.line(page_w - M_R - 38 * mm, name_y - 1.6 * mm, page_w - M_R, name_y - 1.6 * mm)
        if op_website or op_email:
            pdf.setFont("Helvetica", 7.5)
            pdf.setFillColor(c_light)
            pdf.drawRightString(page_w - M_R, name_y - 4 * mm, op_website or op_email)

        # ════════════════════════════════════════════════════════════
        # EMPFÄNGERADRESSE (oben links, unterhalb Logobereich)
        # ════════════════════════════════════════════════════════════
        ADDR_TOP = page_h - 15 * mm
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(c_mid)
        # Kleine Rücksendeadresse
        ret_parts = [p for p in [operator_label, op_street, op_zip_city] if p]
        pdf.drawString(M_L, ADDR_TOP, "  ·  ".join(ret_parts))
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.setFillColor(c_dark)
        pdf.drawString(M_L, ADDR_TOP - 8 * mm, company_name[:55])
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(c_mid)
        _company_contact = str(company_row["contact"] or "").strip() if company_row else ""
        _company_billing_email = str(company_row["billing_email"] or "").strip() if company_row else ""
        _company_street = str(company_row["billing_street"] if company_row and "billing_street" in company_row.keys() else "").strip()
        _company_zip_city = str(company_row["billing_zip_city"] if company_row and "billing_zip_city" in company_row.keys() else "").strip()
        caddr_y = ADDR_TOP - 14 * mm
        if _company_contact:
            pdf.drawString(M_L, caddr_y, _company_contact[:60])
            caddr_y -= 5 * mm
        if _company_street:
            pdf.drawString(M_L, caddr_y, _company_street[:60])
            caddr_y -= 5 * mm
        if _company_zip_city:
            pdf.drawString(M_L, caddr_y, _company_zip_city[:60])
            caddr_y -= 5 * mm
        if _company_billing_email:
            pdf.setFont("Helvetica", 8)
            pdf.setFillColor(c_light)
            pdf.drawString(M_L, caddr_y, _company_billing_email[:60])

        # ════════════════════════════════════════════════════════════
        # HAUPTÜBERSCHRIFT "Rechnung" + Metadaten-Tabelle
        # ════════════════════════════════════════════════════════════
        HEADING_Y = page_h - 68 * mm

        pdf.setFont("Helvetica-Bold", 22)
        pdf.setFillColor(c_dark)
        pdf.drawString(M_L, HEADING_Y, "Rechnung")

        # Kundennummer-Badge rechts neben der Hauptüberschrift (Label direkt ueber Nummer)
        CUST_BADGE_W = 46 * mm
        CUST_BADGE_H = 13 * mm
        CUST_BADGE_X = page_w - M_R - CUST_BADGE_W
        CUST_BADGE_Y = HEADING_Y - 4.5 * mm
        pdf.setFillColor(rl_colors.HexColor("#eef5fb"))
        pdf.setStrokeColor(c_primary)
        pdf.setLineWidth(0.6)
        pdf.roundRect(CUST_BADGE_X, CUST_BADGE_Y, CUST_BADGE_W, CUST_BADGE_H, 2.5 * mm, stroke=1, fill=1)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColor(c_primary)
        pdf.drawCentredString(CUST_BADGE_X + (CUST_BADGE_W / 2), CUST_BADGE_Y + 8.2 * mm, "KUNDENNUMMER")
        pdf.setFont("Helvetica-Bold", 10)
        pdf.setFillColor(c_dark)
        pdf.drawCentredString(CUST_BADGE_X + (CUST_BADGE_W / 2), CUST_BADGE_Y + 3.2 * mm, customer_number)

        # Metadaten 2-spaltig direkt unter Überschrift
        _today_iso = datetime.now().strftime("%Y-%m-%d")
        _due_iso = str(invoice_row["due_date"] or "")[:10]
        _is_overdue = bool(
            _due_iso and str(invoice_row["status"] if "status" in invoice_row.keys() else "") not in ("bezahlt", "paid")
            and _due_iso < _today_iso
        )
        meta_rows = [
            ("Rechnungsnummer:",  invoice_no, False),
            ("Rechnungsdatum:",   invoice_date, False),
            ("Fälligkeitsdatum:", due_date + (" ⚠ Überfällig" if _is_overdue else ""), _is_overdue),
        ]
        meta_y = HEADING_Y - 8 * mm
        for lbl, val, is_alert in meta_rows:
            pdf.setFont("Helvetica-Bold", 9)
            pdf.setFillColor(rl_colors.HexColor("#c0392b") if is_alert else c_dark)
            pdf.drawString(M_L, meta_y, lbl)
            pdf.setFont("Helvetica", 9)
            pdf.setFillColor(rl_colors.HexColor("#c0392b") if is_alert else c_mid)
            pdf.drawString(M_L + 46 * mm, meta_y, val)
            meta_y -= 5.5 * mm

        # Einleitungstext
        INTRO_Y = meta_y - 5 * mm
        pdf.setFont("Helvetica", 9)
        pdf.setFillColor(c_mid)
        _intro = (f"Wir senden Ihnen hiermit unsere Rechnung. Bitte leisten Sie die Zahlung innerhalb von 30 Tagen "
                  f"auf unser Bankkonto unter Angabe der Rechnungsnummer {invoice_no}. "
                  f"Sofern nicht anders angegeben, entspricht das Lieferdatum dem Rechnungsdatum.")
        import textwrap as _tw
        _max_chars = max(50, int(CW / 5.2))
        _intro_lines = _tw.wrap(_intro, width=_max_chars)
        il_y = INTRO_Y
        for _line in _intro_lines[:4]:
            pdf.drawString(M_L, il_y, _line)
            il_y -= 5.0 * mm

        # ════════════════════════════════════════════════════════════
        # POSITIONSTABELLE
        # ════════════════════════════════════════════════════════════
        TBL_TOP = il_y - 5 * mm

        # Spaltenbreiten  (Name/Beschreibung bekommt den Rest)
        C_NAME = 70 * mm
        C_QTY  = 20 * mm
        C_PRICE= 28 * mm
        C_VAT  = 18 * mm
        C_TOT  = CW - C_NAME - C_QTY - C_PRICE - C_VAT

        # x-Positionen
        cx0 = M_L
        cx1 = cx0 + C_NAME
        cx2 = cx1 + C_QTY
        cx3 = cx2 + C_PRICE
        cx4 = cx3 + C_VAT

        HDR_ROW_H  = 8 * mm
        DATA_ROW_H = 9 * mm
        FOOTER_RESERVE = FOOTER_H + 58 * mm  # Platz für Summenblock + Footer

        # Tabellenkopf – blauer Balken
        pdf.setFillColor(c_tbl_hdr_bg)
        pdf.rect(M_L, TBL_TOP - HDR_ROW_H, CW, HDR_ROW_H, stroke=0, fill=1)
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.setFillColor(rl_colors.white)
        hy = TBL_TOP - HDR_ROW_H + 2.8 * mm
        hdr_cells = [
            (cx0 + 2*mm, "Name/ Beschreibung", "L"),
            (cx1,        "Menge",              "R", C_QTY),
            (cx2,        "Preis",              "R", C_PRICE),
            (cx3,        "USt.",               "R", C_VAT),
            (cx4,        "Gesamtpreis",        "R", C_TOT),
        ]
        for cell in hdr_cells:
            if cell[2] == "L":
                pdf.drawString(cell[0], hy, cell[1])
            else:
                pdf.drawRightString(cell[0] + cell[3] - 2*mm, hy, cell[1])

        # Tabellenzeilen
        row_y = TBL_TOP - HDR_ROW_H
        visible_rows = 0
        hidden_rows = 0
        for idx, item in enumerate(pdf_items):
            if row_y - DATA_ROW_H < FOOTER_RESERVE:
                hidden_rows = len(pdf_items) - idx
                break
            row_y -= DATA_ROW_H
            visible_rows += 1

            # Zebra-Stripes
            pdf.setFillColor(rl_colors.white if idx % 2 == 0 else c_stripe)
            pdf.rect(M_L, row_y, CW, DATA_ROW_H, stroke=0, fill=1)
            # untere Trennlinie
            pdf.setStrokeColor(c_rule)
            pdf.setLineWidth(0.25)
            pdf.line(M_L, row_y, M_L + CW, row_y)

            i_desc  = str(item.get("description") or "-")
            i_qty   = float(item.get("qty") or 1)
            i_unit  = str(item.get("unit") or "")
            i_price = float(item.get("unitPrice") or 0)
            i_total = float(item.get("total") or 0)
            qty_str = (f"{i_qty:g} {i_unit}").strip()
            ty = row_y + DATA_ROW_H / 2 - 1.5 * mm

            pdf.setFont("Helvetica", 9)
            pdf.setFillColor(c_dark)
            try:
                from reportlab.lib.utils import simpleSplit as _ss
                _dlines = _ss(i_desc, "Helvetica", 9, C_NAME - 4*mm)[:2]
            except Exception:
                _dlines = [i_desc[:52]]
            if len(_dlines) > 1:
                pdf.drawString(cx0 + 2*mm, row_y + DATA_ROW_H/2 + 1.2*mm, _dlines[0])
                pdf.setFont("Helvetica", 7.5)
                pdf.setFillColor(c_light)
                pdf.drawString(cx0 + 2*mm, row_y + DATA_ROW_H/2 - 3*mm, _dlines[1])
            else:
                pdf.drawString(cx0 + 2*mm, ty, _dlines[0] if _dlines else i_desc[:52])

            pdf.setFont("Helvetica", 9)
            pdf.setFillColor(c_mid)
            pdf.drawRightString(cx1 + C_QTY  - 2*mm, ty, qty_str)
            pdf.drawRightString(cx2 + C_PRICE - 2*mm, ty, _money(i_price))
            vat_cell = f"{vat_rate:.0f} %" if vat_rate else "-"
            pdf.drawRightString(cx3 + C_VAT   - 2*mm, ty, vat_cell)
            pdf.setFont("Helvetica-Bold", 9)
            pdf.setFillColor(c_dark)
            pdf.drawRightString(cx4 + C_TOT   - 2*mm, ty, _money(i_total))

        if hidden_rows > 0:
            row_y -= 5 * mm
            pdf.setFont("Helvetica-Oblique", 7.5)
            pdf.setFillColor(c_light)
            pdf.drawString(M_L, row_y, f"… {hidden_rows} weitere Positionen (nicht abgebildet)")

        TABLE_BOTTOM = row_y

        # ════════════════════════════════════════════════════════════
        # SUMMENBLOCK – rechtsbündig unter Tabelle
        # ════════════════════════════════════════════════════════════
        SUM_W = 80 * mm
        SUM_X = page_w - M_R - SUM_W
        SUM_ROW_H = 7 * mm
        TOTAL_ROW_H = 9 * mm

        sum_rows = [("Gesamtbetrag exkl. USt.", _money(net_amount))]
        if discount_amount > 0:
            sum_rows.append(("Rabatt", f"– {_money(discount_amount)}"))
        sum_rows.append((f"USt. {vat_rate:.0f} %", _money(vat_amount)))

        SUM_TOTAL_H = len(sum_rows) * SUM_ROW_H + TOTAL_ROW_H
        SUM_TOP = TABLE_BOTTOM - 5 * mm

        # Trennlinie über Summenblock
        pdf.setStrokeColor(c_rule)
        pdf.setLineWidth(0.5)
        pdf.line(SUM_X, SUM_TOP + 1*mm, page_w - M_R, SUM_TOP + 1*mm)

        sr_y = SUM_TOP - SUM_ROW_H + 2*mm
        for lbl, val in sum_rows:
            pdf.setFont("Helvetica", 9)
            pdf.setFillColor(c_mid)
            pdf.drawString(SUM_X + 2*mm, sr_y, lbl)
            pdf.setFont("Helvetica", 9)
            pdf.setFillColor(c_dark)
            pdf.drawRightString(page_w - M_R, sr_y, val)
            sr_y -= SUM_ROW_H

        # Gesamtzeile – blauer Hintergrundbalken
        TOTAL_Y = sr_y - 2*mm
        pdf.setFillColor(c_primary)
        pdf.rect(SUM_X, TOTAL_Y, SUM_W, TOTAL_ROW_H, stroke=0, fill=1)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.setFillColor(rl_colors.white)
        pdf.drawString(SUM_X + 3*mm, TOTAL_Y + 2.5*mm, "Gesamtbetrag inkl. USt")
        pdf.drawRightString(page_w - M_R - 2*mm, TOTAL_Y + 2.5*mm, _money(total_amount))

        # Verwendungszweck
        vz_y = TOTAL_Y - 8 * mm
        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(c_light)
        pdf.drawString(M_L, vz_y, f"Verwendungszweck: Rg. {invoice_no}  ·  Fällig: {due_date}")
        if op_iban:
            pdf.drawString(M_L, vz_y - 4.5*mm, f"IBAN: {op_iban}" + (f"  ·  BIC: {op_bic}" if op_bic else ""))

        # ════════════════════════════════════════════════════════════
        # BEZAHLT-WASSERZEICHEN
        # ════════════════════════════════════════════════════════════
        _inv_status = str(invoice_row["status"] if "status" in invoice_row.keys() else "").lower()
        if _inv_status == "bezahlt":
            try:
                from reportlab.lib.colors import Color as _WmColor
                pdf.saveState()
                pdf.translate(page_w / 2, page_h / 2)
                pdf.rotate(35)
                pdf.setFillColor(_WmColor(0.086, 0.639, 0.290, alpha=0.08))
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
    custom_body_template = str(settings_row["invoice_email_body_template"] if "invoice_email_body_template" in settings_row.keys() else "") or ""
    custom_intro = str(settings_row["invoice_email_intro"] if "invoice_email_intro" in settings_row.keys() else "") or ""
    if custom_subject.strip():
        mail_subject = custom_subject.replace("{invoiceNumber}", str(invoice_row["invoice_number"] or "")).replace("{platformName}", platform_label)
    if custom_body_template.strip():
        intro_text = custom_body_template.replace("{invoiceNumber}", _inv_no).replace("{platformName}", platform_label).replace("{companyName}", str(company_row["name"] or ""))
        intro_html = html.escape(intro_text).replace("\n", "<br>")
    elif custom_intro.strip():
        intro_text = custom_intro.strip()
        intro_html = html.escape(intro_text).replace("\n", "<br>")
    else:
        intro_text = _lang["intro_plain"]
        intro_html = _lang["intro_html"]

    text_body = (
        f"{_lang['greeting']}\n\n"
        f"{intro_text}\n\n"
        f"{_lang['closing']}\n{operator_label}"
    )
    body_html = (
        f"<p style='margin:0 0 14px;'>{html.escape(_lang['greeting'])}</p>"
        f"<p style='margin:0 0 14px;'>{intro_html}</p>"
        f"<p style='margin:0;color:#6b7280;font-size:13px;'>{html.escape(_lang['closing'])}<br><strong>{html.escape(operator_label)}</strong></p>"
    )
    email_header_label = _lang["email_header"]

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
                    email_header_label,
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
        email_header_label,
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
        with smtplib.SMTP(smtp_host, int(settings_row["smtp_port"] or 587), timeout=10) as smtp:
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
        with smtplib.SMTP(smtp_host, int(settings["smtp_port"] or 587), timeout=10) as smtp:
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


# ─── Kundenbewertungen ────────────────────────────────────────────────────────

@app.put("/api/companies/<company_id>/review-access")
@require_auth
@require_roles("superadmin")
def toggle_company_review_access(company_id):
    """Aktiviert oder deaktiviert die Bewertungsseite für eine Firma."""
    db = get_db()
    company = db.execute("SELECT id, name, review_enabled FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "Firma nicht gefunden"}), 404
    new_state = 0 if int(company["review_enabled"] or 0) else 1
    token = ""
    if new_state:
        import uuid as _uuid
        token = str(_uuid.uuid4()).replace("-", "")
    db.execute(
        "UPDATE companies SET review_enabled = ?, review_token = ? WHERE id = ?",
        (new_state, token, company_id)
    )
    db.commit()
    return jsonify({"review_enabled": new_state, "review_token": token if new_state else ""})


@app.get("/api/public/review")
def get_review_form_info():
    """Gibt Firmenname zurück wenn Token gültig und Bewertung aktiviert ist."""
    token = (request.args.get("token") or "").strip()
    if len(token) < 10:
        return jsonify({"error": "Ungültiger Token"}), 400
    db = get_db()
    row = db.execute(
        "SELECT id, name FROM companies WHERE review_token = ? AND review_enabled = 1 AND deleted_at IS NULL",
        (token,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Bewertungslink ungültig oder bereits deaktiviert"}), 404
    return jsonify({"company_name": row["name"], "company_id": row["id"]})


@app.post("/api/public/review/submit")
def submit_review():
    """Nimmt eine Kundenbewertung entgegen."""
    data = request.get_json(force=True, silent=True) or {}
    token = (data.get("token") or "").strip()
    stars = int(data.get("stars") or 5)
    review_text = (data.get("review_text") or "").strip()[:2000]
    reviewer_name = (data.get("reviewer_name") or "").strip()[:100]
    if len(token) < 10 or not (1 <= stars <= 5):
        return jsonify({"error": "Ungültige Eingabe"}), 400
    if len(review_text) < 5:
        return jsonify({"error": "Bitte mindestens 5 Zeichen als Bewertungstext eingeben"}), 400
    db = get_db()
    row = db.execute(
        "SELECT id, name FROM companies WHERE review_token = ? AND review_enabled = 1 AND deleted_at IS NULL",
        (token,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Bewertungslink ungültig"}), 403
    import uuid as _uuid
    review_id = f"rev-{str(_uuid.uuid4())[:8]}"
    db.execute(
        """INSERT INTO customer_reviews (id, company_id, company_name_snapshot, stars, review_text, reviewer_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (review_id, row["id"], row["name"], stars, review_text, reviewer_name, utc_now().isoformat().replace("+00:00", "Z"))
    )
    db.commit()
    return jsonify({"ok": True})


@app.get("/api/reviews")
@require_auth
@require_roles("superadmin")
def list_reviews():
    """Listet alle Kundenbewertungen auf."""
    db = get_db()
    rows = db.execute(
        "SELECT id, company_name_snapshot, stars, review_text, reviewer_name, created_at FROM customer_reviews ORDER BY created_at DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/invoices/export.csv")
@require_auth
@require_roles("superadmin")
def export_all_invoices_csv():
    """Export all invoices as a UTF-8 CSV file (Excel-compatible)."""
    import csv as _csv
    db = get_db()
    rows = db.execute(
        """
        SELECT invoices.*, companies.name AS company_name
        FROM invoices
        JOIN companies ON companies.id = invoices.company_id
        ORDER BY invoices.created_at DESC
        """
    ).fetchall()
    output = io.StringIO()
    writer = _csv.writer(output, delimiter=";", quoting=_csv.QUOTE_ALL)
    writer.writerow(["Rechnungsnummer", "Firma", "Empf\u00e4nger-Email", "Rechnungsdatum",
                     "F\u00e4lligkeit", "Netto (EUR)", "MwSt %", "MwSt (EUR)", "Gesamt (EUR)",
                     "Status", "Bezahlt am", "Zahlungsnotiz", "Mahnstufe", "Erstellt am"])
    for row in rows:
        writer.writerow([
            row["invoice_number"] or "",
            row["company_name"] or "",
            row["recipient_email"] or "",
            row["invoice_date"] or "",
            row["due_date"] or "",
            str(row["net_amount"] or 0).replace(".", ","),
            str(row["vat_rate"] or 0).replace(".", ","),
            str(row["vat_amount"] or 0).replace(".", ","),
            str(row["total_amount"] or 0).replace(".", ","),
            row["status"] or "",
            row["paid_at"] or "",
            (row["payment_note"] if "payment_note" in row.keys() else "") or "",
            str(row["reminder_stage"] if "reminder_stage" in row.keys() else 0),
            row["created_at"] or "",
        ])
    filename = f"rechnungen-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/invoices")
@require_auth
@require_roles("superadmin", "company-admin")
def list_invoices():
    db = get_db()
    if g.current_user["role"] != "superadmin":
        plan_value = get_company_plan(db, g.current_user.get("company_id"))
        if not company_has_feature(plan_value, "invoicing"):
            return feature_not_available_response("invoicing", plan_value)
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


@app.get("/api/invoices/monthly-cycle-status")
@require_auth
@require_roles("superadmin")
def get_monthly_invoice_cycle_status_endpoint():
    db = get_db()
    return jsonify(get_monthly_invoice_cycle_status(db))


@app.get("/api/invoices/dead-letters")
@require_auth
@require_roles("superadmin")
def list_invoice_dead_letters():
    db = get_db()
    return jsonify(get_invoice_dead_letters(db))


def get_next_numeric_invoice_number(db, company_id=None, min_width=6):
    if company_id:
        rows = db.execute(
            "SELECT invoice_number FROM invoices WHERE company_id = ?",
            (company_id,),
        ).fetchall()
    else:
        rows = db.execute("SELECT invoice_number FROM invoices").fetchall()

    max_seq = 0
    for row in rows:
        digits = re.sub(r"\D+", "", str(row["invoice_number"] or ""))
        if digits:
            max_seq = max(max_seq, int(digits))

    next_seq = max_seq + 1
    width = max(min_width, len(str(next_seq)))
    return str(next_seq).zfill(width)


@app.get("/api/invoices/next-number")
@require_auth
@require_roles("superadmin")
def get_next_invoice_number():
    """Return the next sequential numeric invoice number (digits only)."""
    db = get_db()
    company_id = (request.args.get("companyId") or "").strip()
    next_num = get_next_numeric_invoice_number(db, company_id=company_id or None)
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

    invoice_number_raw = (payload.get("invoiceNumber") or "").strip()
    if invoice_number_raw:
        invoice_number = re.sub(r"\D+", "", invoice_number_raw)
        if not invoice_number:
            return jsonify({"error": "invalid_invoice_number_format", "message": "Rechnungsnummer darf nur Ziffern enthalten."}), 400
    else:
        invoice_number = get_next_numeric_invoice_number(db, company_id=company_id)

    if len(invoice_number) < 3 or len(invoice_number) > 20:
        return jsonify({"error": "invalid_invoice_number_length", "message": "Rechnungsnummer muss zwischen 3 und 20 Ziffern haben."}), 400
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
        "UPDATE invoices SET status = ?, paid_at = ?, payment_note = ?, last_reminder_error = '' WHERE id = ?",
        ("bezahlt", payment_date, notes, invoice_id),
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


@app.post("/api/invoices/bulk-mark-paid")
@require_auth
@require_roles("superadmin")
def bulk_mark_invoices_paid():
    """Mehrere Rechnungen auf einmal als bezahlt markieren."""
    payload = request.get_json(silent=True) or {}
    invoice_ids = [str(i).strip() for i in (payload.get("ids") or []) if str(i).strip()]
    if not invoice_ids or len(invoice_ids) > 100:
        return jsonify({"error": "invalid_ids", "message": "1–100 IDs erforderlich"}), 400
    payment_date = (payload.get("paymentDate") or now_iso().split("T")[0]).strip()
    db = get_db()
    updated = 0
    for invoice_id in invoice_ids:
        inv = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not inv or inv["paid_at"]:
            continue
        db.execute(
            "UPDATE invoices SET status = 'bezahlt', paid_at = ?, last_reminder_error = '' WHERE id = ?",
            (payment_date, invoice_id),
        )
        log_audit(
            "invoice.marked_paid",
            f"Rechnung {inv['invoice_number']} als bezahlt markiert (Bulk)",
            target_type="invoice", target_id=invoice_id, company_id=inv["company_id"], actor=g.current_user,
        )
        updated += 1
    db.commit()
    return jsonify({"ok": True, "updated": updated})


@app.post("/api/invoices/trigger-dunning")
@require_auth
@require_roles("superadmin")
def trigger_dunning_run():
    """Manuell einen Mahnungs-Durchlauf ausloesen."""
    try:
        run_dunning_job_once()
        result = dict(DUNNING_LAST_RESULT or {})
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        return jsonify({"error": "dunning_failed", "message": str(exc)}), 500


@app.post("/api/invoices/trigger-monthly-cycle")
@require_auth
@require_roles("superadmin")
def trigger_monthly_invoice_cycle_endpoint():
    db = get_db()
    try:
        result = run_monthly_invoice_cycle(db, force=True)
        status = get_monthly_invoice_cycle_status(db)
        return jsonify({"ok": True, "result": result, "status": status})
    except Exception as exc:
        return jsonify({"error": "monthly_invoice_cycle_failed", "message": str(exc)}), 500


@app.post("/api/invoices/simulate-monthly-cycle")
@require_auth
@require_roles("superadmin")
def simulate_monthly_invoice_cycle_endpoint():
    """Run the monthly invoice cycle for the CURRENT month (simulated by using next month as reference)."""
    db = get_db()
    try:
        today = utc_now().date()
        if today.month == 12:
            sim_ref = today.replace(year=today.year + 1, month=1, day=1)
        else:
            sim_ref = today.replace(month=today.month + 1, day=1)
        result = run_monthly_invoice_cycle(db, reference_date=sim_ref, force=True)
        status = get_monthly_invoice_cycle_status(db)
        return jsonify({"ok": True, "result": result, "status": status})
    except Exception as exc:
        return jsonify({"error": "simulate_monthly_cycle_failed", "message": str(exc)}), 500


@app.get("/api/invoices/<invoice_id>/reminder-letter.pdf")
@require_auth
@require_roles("superadmin")
def invoice_reminder_letter_pdf(invoice_id):
    """Mahnungs-PDF fuer eine Rechnung generieren (Zahlungserinnerung / Mahnung)."""
    db = get_db()
    invoice = db.execute(
        """SELECT invoices.*, companies.name AS company_name, companies.contact AS company_contact,
                  companies.billing_email AS company_billing_email,
                  companies.billing_street AS company_billing_street,
                  companies.billing_zip_city AS company_billing_zip_city
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
    # Draw logo in header band if available
    if settings:
        _logo_raw = str(settings["invoice_logo_data"] or "").strip()
        if _logo_raw.startswith("data:image") and "," in _logo_raw:
            try:
                import base64 as _b64
                _, _enc = _logo_raw.split(",", 1)
                _lb = _b64.b64decode(_enc)
                from reportlab.lib.utils import ImageReader as _IR
                _ir = _IR(io.BytesIO(_lb))
                pdf.drawImage(_ir, page_width - 120, page_height - 48, width=80, height=40,
                              preserveAspectRatio=True, mask="auto")
            except Exception:
                pass

    # ── Sender address block (small above recipient) ──
    y = page_height - 80
    pdf.setFillColorRGB(0.5, 0.5, 0.5)
    pdf.setFont("Helvetica", 7)
    sender_parts = [p for p in [operator_name, operator_street, operator_zip_city] if p]
    sender_line = "  ·  ".join(sender_parts)
    pdf.drawString(36, y, sender_line[:120])
    contact_parts = [p for p in [
        f"Tel: {operator_phone}" if operator_phone else "",
        operator_email if operator_email else "",
    ] if p]
    if contact_parts:
        y -= 10
        pdf.drawString(36, y, "  ·  ".join(contact_parts)[:120])

    # ── Recipient address block ──
    y -= 18
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(36, y, str(invoice["company_name"] or ""))
    if invoice["company_contact"]:
        y -= 14
        pdf.drawString(36, y, str(invoice["company_contact"] or ""))
    _rec_street = str(invoice["company_billing_street"] or "").strip() if "company_billing_street" in invoice.keys() else ""
    _rec_zip_city = str(invoice["company_billing_zip_city"] or "").strip() if "company_billing_zip_city" in invoice.keys() else ""
    if _rec_street:
        y -= 13
        pdf.setFont("Helvetica", 9)
        pdf.drawString(36, y, _rec_street)
    if _rec_zip_city:
        y -= 13
        pdf.setFont("Helvetica", 9)
        pdf.drawString(36, y, _rec_zip_city)
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
DOC_TYPES_WITH_REQUIRED_EXPIRY = {
    "personalausweis",
    "arbeitserlaubnis",
    "gesundheitszeugnis",
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

# Nutze Railway-Volume /data auch für Uploads, wenn verfügbar
_railway_data_dir = Path("/data")
if _railway_data_dir.is_dir() and os.access(_railway_data_dir, os.W_OK):
    DOCS_UPLOAD_DIR = _railway_data_dir / "uploads" / "documents"
    # Bestehende Uploads migrieren (einmalig), falls lokales Verzeichnis Dateien hat
    _old_docs_dir = BASE_DIR / "backend" / "uploads" / "documents"
    if _old_docs_dir.exists() and not DOCS_UPLOAD_DIR.exists():
        try:
            import shutil as _shutil
            _shutil.copytree(str(_old_docs_dir), str(DOCS_UPLOAD_DIR))
            print(f"[baupass] Auto-migrated uploads from {_old_docs_dir} to {DOCS_UPLOAD_DIR}", flush=True)
        except Exception as _upd_err:
            print(f"[baupass] WARNING: Uploads auto-migration failed: {_upd_err}", flush=True)
try:
    DOCS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    DOCS_UPLOAD_DIR = BASE_DIR / "backend" / "uploads" / "documents"
    DOCS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _parse_imap_attachment_limit_bytes() -> int:
    raw = os.getenv("BAUPASS_IMAP_MAX_ATTACHMENT_MB", "15")
    try:
        mb = max(1, int(raw))
    except (TypeError, ValueError):
        mb = 15
    return mb * 1024 * 1024


MAX_IMAP_ATTACHMENT_BYTES = _parse_imap_attachment_limit_bytes()


def validate_document_expiry_date(doc_type, expiry_date_raw, today_value=None):
    expiry_date = clean_text_input(expiry_date_raw or "", max_len=10)
    today = str(today_value or now_iso()[:10])
    if not expiry_date:
        if doc_type in DOC_TYPES_WITH_REQUIRED_EXPIRY:
            return None, "document_expiry_required", "Fuer diesen Dokumenttyp ist ein Gueltigkeitsdatum erforderlich."
        return None, None, None

    try:
        parsed = datetime.strptime(expiry_date, "%Y-%m-%d")
    except ValueError:
        return None, "invalid_expiry_date", "Das Gueltigkeitsdatum ist ungueltig."

    normalized = parsed.strftime("%Y-%m-%d")
    if normalized < today:
        return None, "document_expiry_in_past", "Das Gueltigkeitsdatum darf nicht in der Vergangenheit liegen."
    return normalized, None, None


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


def _first_nonempty_env(*names):
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return ""


def _parse_optional_int(raw_value, default_value):
    if raw_value is None:
        return default_value
    text = str(raw_value).strip()
    if not text:
        return default_value
    try:
        return int(text)
    except (TypeError, ValueError):
        return default_value


def _parse_optional_bool(raw_value, default_value):
    if raw_value is None:
        return default_value
    text = str(raw_value).strip().lower()
    if not text:
        return default_value
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default_value


def get_imap_settings(db):
    row = db.execute(
        "SELECT imap_host, imap_port, imap_username, imap_password, imap_folder, imap_use_ssl FROM settings WHERE id = 1"
    ).fetchone()
    cfg = dict(row) if row else {}

    env_host = _first_nonempty_env("BAUPASS_IMAP_HOST", "IMAP_HOST")
    env_username = _first_nonempty_env("BAUPASS_IMAP_USERNAME", "IMAP_USERNAME")
    env_password = _first_nonempty_env("BAUPASS_IMAP_PASSWORD", "IMAP_PASSWORD")
    env_folder = _first_nonempty_env("BAUPASS_IMAP_FOLDER", "IMAP_FOLDER")
    env_port = _first_nonempty_env("BAUPASS_IMAP_PORT", "IMAP_PORT")
    env_use_ssl = _first_nonempty_env("BAUPASS_IMAP_USE_SSL", "IMAP_USE_SSL")

    if env_host:
        cfg["imap_host"] = env_host
    if env_username:
        cfg["imap_username"] = env_username
    if env_password:
        cfg["imap_password"] = env_password
    if env_folder:
        cfg["imap_folder"] = env_folder

    cfg["imap_port"] = _parse_optional_int(env_port, cfg.get("imap_port") or 993)
    cfg["imap_use_ssl"] = 1 if _parse_optional_bool(env_use_ssl, bool(cfg.get("imap_use_ssl", 1))) else 0

    # Guarantee a stable shape for callers, even when settings row is missing.
    cfg.setdefault("imap_host", "")
    cfg.setdefault("imap_username", "")
    cfg.setdefault("imap_password", "")
    cfg.setdefault("imap_folder", "INBOX")
    if not str(cfg.get("imap_folder") or "").strip():
        cfg["imap_folder"] = "INBOX"

    return cfg


def _normalize_imap_host_port(host_value, port_value):
    host = str(host_value or "").strip()
    port = int(port_value or 993)
    # Common admin input: "imap.example.com:993" in host field.
    # Split out the port so socket resolution works reliably.
    if host and host.count(":") == 1 and "]" not in host:
        maybe_host, maybe_port = host.rsplit(":", 1)
        if maybe_host and maybe_port.isdigit():
            host = maybe_host.strip()
            parsed_port = int(maybe_port)
            if parsed_port > 0:
                port = parsed_port
    return host, port


def poll_imap_inbox():
    """Pollt das konfigurierte IMAP-Postfach und speichert neue Mails in email_inbox.

    Gibt ein Dict zurück: {"status": "not_configured"|"connect_error"|"ok"|"error", "newEmails": int}
    """
    import imaplib
    import email as _email
    import email.policy as _email_policy

    _result = {"status": "ok", "newEmails": 0}

    try:
        with app.app_context():
            db = get_db()
            cfg = get_imap_settings(db)
            if not cfg or not cfg.get("imap_host") or not cfg.get("imap_username"):
                missing = []
                if not cfg or not str(cfg.get("imap_host") or "").strip():
                    missing.append("imap_host")
                if not cfg or not str(cfg.get("imap_username") or "").strip():
                    missing.append("imap_username")
                _result = {"status": "not_configured", "newEmails": 0, "missing": missing}
                return _result

            host, port = _normalize_imap_host_port(cfg.get("imap_host"), cfg.get("imap_port") or 993)
            username = cfg["imap_username"]
            password = cfg["imap_password"] or ""
            folder = cfg.get("imap_folder") or "INBOX"
            use_ssl = bool(cfg.get("imap_use_ssl", 1))

            _imap_timeout = 30  # Sekunden – verhindert 502 durch hängenden Socket
            try:
                attempts = [(use_ssl, port)]
                # Fallbacks for common misconfigurations (993 SSL vs 143 STARTTLS)
                if use_ssl:
                    attempts.append((False, 143 if port == 993 else port))
                else:
                    attempts.append((True, 993 if port == 143 else port))

                conn = None
                last_exc = None
                tried = set()
                for attempt_ssl, attempt_port in attempts:
                    key = (bool(attempt_ssl), int(attempt_port))
                    if key in tried:
                        continue
                    tried.add(key)
                    try:
                        if attempt_ssl:
                            conn = imaplib.IMAP4_SSL(host, attempt_port, timeout=_imap_timeout)
                        else:
                            conn = imaplib.IMAP4(host, attempt_port, timeout=_imap_timeout)
                            conn.starttls()
                        conn.login(username, password)
                        break
                    except Exception as inner_exc:
                        last_exc = inner_exc
                        try:
                            if conn is not None:
                                conn.logout()
                        except Exception:
                            pass
                        conn = None

                if conn is None and last_exc is not None:
                    raise last_exc
            except Exception as exc:
                _result = {"status": "connect_error", "newEmails": 0, "error": str(exc)}
                try:
                    create_system_alert(
                        db,
                        code="imap_connect_failed",
                        severity="warning",
                        message="IMAP-Verbindung fehlgeschlagen.",
                        details={"error": str(exc)},
                    )
                    db.commit()
                except Exception:
                    pass
                return _result

            conn.select(folder, readonly=False)
            # Alle Mails im Ordner berücksichtigen. Deduplizierung passiert über
            # message_id bzw. IMAP UID-Fallback in der DB.
            status, data = conn.search(None, "ALL")
            if status != "OK":
                conn.logout()
                _result = {"status": "error", "newEmails": 0, "error": "IMAP SEARCH fehlgeschlagen"}
                return _result

            msg_ids = (data[0] or b"").split()
            new_email_count = 0
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
                recipient_candidates = extract_message_recipient_addresses(msg)
                subject = _decode_mime_header(msg.get("Subject") or "")
                received_at = now_iso()
                matched_company = None
                matched_recipient = ""
                for candidate in recipient_candidates:
                    company_match = find_company_by_document_email(db, candidate)
                    if company_match:
                        matched_company = company_match
                        matched_recipient = candidate
                        break

                # Fallback: komplette Header prüfen (manche Provider liefern Alias
                # nicht als saubere Einzeladresse, aber im Header-Text).
                if not matched_company:
                    header_company, header_recipient = find_company_by_recipient_headers(db, msg)
                    if header_company:
                        matched_company = header_company
                        matched_recipient = header_recipient

                to_addr = matched_recipient or (recipient_candidates[0] if recipient_candidates else "")
                matched_company_id = matched_company["id"] if matched_company else None

                # Doppelten Einlese-Schutz via message_id
                # Bei bereits vorhandenen Mails trotzdem Firmen-Match nachziehen,
                # falls früher ohne matched_company_id gespeichert wurde.
                if message_id:
                    existing = db.execute(
                        "SELECT id, matched_company_id, to_addr FROM email_inbox WHERE message_id = ?",
                        (message_id,),
                    ).fetchone()
                    if existing:
                        if matched_company_id and not existing["matched_company_id"]:
                            db.execute(
                                "UPDATE email_inbox SET matched_company_id = ?, to_addr = ? WHERE id = ?",
                                (matched_company_id, to_addr, existing["id"]),
                            )
                        elif to_addr and not str(existing["to_addr"] or "").strip():
                            db.execute(
                                "UPDATE email_inbox SET to_addr = ? WHERE id = ?",
                                (to_addr, existing["id"]),
                            )

                        existing_attachment = db.execute(
                            "SELECT id FROM email_attachments WHERE inbox_id = ? LIMIT 1",
                            (existing["id"],),
                        ).fetchone()
                        if not existing_attachment:
                            fallback_text = ""
                            for part in msg.walk():
                                if part.is_multipart():
                                    continue
                                ctype = part.get_content_type()
                                disposition = str(part.get_content_disposition() or "").lower()
                                filename_header = part.get_filename()
                                if disposition == "attachment" or filename_header:
                                    continue
                                if ctype == "text/plain":
                                    try:
                                        payload_text = part.get_payload(decode=True)
                                        if payload_text:
                                            charset = part.get_content_charset() or "utf-8"
                                            fallback_text = payload_text.decode(charset, errors="replace")
                                            if fallback_text.strip():
                                                break
                                    except Exception:
                                        pass
                                elif ctype == "text/html" and not fallback_text:
                                    try:
                                        payload_html = part.get_payload(decode=True)
                                        if payload_html:
                                            charset = part.get_content_charset() or "utf-8"
                                            html_text = payload_html.decode(charset, errors="replace")
                                            plain_text = re.sub(r"<[^>]+>", " ", html_text)
                                            plain_text = html.unescape(plain_text)
                                            fallback_text = re.sub(r"\s+", " ", plain_text).strip()
                                    except Exception:
                                        pass

                            if fallback_text.strip():
                                fallback_bytes = fallback_text.encode("utf-8", errors="replace")
                                att_id = f"att-{secrets.token_hex(8)}"
                                db.execute(
                                    "INSERT INTO email_attachments (id, inbox_id, filename, content_type, file_size, file_data) VALUES (?,?,?,?,?,?)",
                                    (
                                        att_id,
                                        existing["id"],
                                        "email-text.txt",
                                        "text/plain; charset=utf-8",
                                        len(fallback_bytes),
                                        fallback_bytes,
                                    ),
                                )
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
                    elif ctype == "text/html" and disposition != "attachment" and not filename_header and not body_text:
                        # Fallback für HTML-only Mails: in einfachen Klartext wandeln.
                        try:
                            payload_html = part.get_payload(decode=True)
                            if payload_html:
                                charset = part.get_content_charset() or "utf-8"
                                html_text = payload_html.decode(charset, errors="replace")
                                plain_text = re.sub(r"<[^>]+>", " ", html_text)
                                plain_text = html.unescape(plain_text)
                                plain_text = re.sub(r"\s+", " ", plain_text).strip()
                                if plain_text:
                                    body_text = plain_text
                        except Exception:
                            pass
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

                # Wenn kein klassischer Anhang vorhanden ist, den Mailinhalt als
                # zuweisbaren Text-Anhang anbieten (Pförtner-Flow bleibt konsistent).
                if not attachments_data and str(body_text or "").strip():
                    fallback_bytes = body_text.encode("utf-8", errors="replace")
                    attachments_data.append({
                        "filename": "email-text.txt",
                        "content_type": "text/plain; charset=utf-8",
                        "file_size": len(fallback_bytes),
                        "file_data": fallback_bytes,
                    })

                inbox_id = f"inb-{secrets.token_hex(8)}"
                db.execute(
                    "INSERT INTO email_inbox (id, message_id, from_addr, to_addr, subject, body_text, matched_company_id, received_at) VALUES (?,?,?,?,?,?,?,?)",
                    (inbox_id, message_id, from_addr, to_addr, subject, body_text[:2000], matched_company_id, received_at),
                )
                new_email_count += 1

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
            _result = {"status": "ok", "newEmails": new_email_count}
    except Exception as exc:
        _result = {"status": "error", "newEmails": 0, "error": str(exc)}
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

    return _result


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
    import concurrent.futures
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(poll_imap_inbox)
            try:
                imap_result = future.result(timeout=45) or {"status": "ok", "newEmails": 0}
            except concurrent.futures.TimeoutError:
                return jsonify({"ok": False, "error": "imap_timeout", "imap": {"status": "timeout", "newEmails": 0}}), 504
        return jsonify({"ok": True, "imap": imap_result})
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
        company_id = g.current_user.get("company_id")
        rows = db.execute(
            """
            SELECT *
            FROM email_inbox
            WHERE dismissed = 0
              AND (
                    matched_company_id = ?
                 OR lower(COALESCE(to_addr, '')) = lower(
                        COALESCE((
                            SELECT document_email
                            FROM companies
                            WHERE id = ?
                            LIMIT 1
                        ), '')
                    )
              )
            ORDER BY received_at DESC
            LIMIT 100
            """,
            (company_id, company_id),
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


@app.post("/api/documents/inbox/<inbox_id>/mark-read")
@require_auth
@require_roles("superadmin", "company-admin", "turnstile")
def mark_inbox_email_read(inbox_id):
    db = get_db()
    row = db.execute("SELECT * FROM email_inbox WHERE id = ?", (inbox_id,)).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404
    db.execute("UPDATE email_inbox SET is_read = 1 WHERE id = ?", (inbox_id,))
    db.commit()
    attachments = db.execute(
        "SELECT id, filename, content_type, file_size, assigned_worker_id, assigned_doc_type FROM email_attachments WHERE inbox_id = ?",
        (inbox_id,),
    ).fetchall()
    entry = dict(row)
    entry["is_read"] = 1
    entry["attachments"] = [dict(a) for a in attachments]
    if row["matched_company_id"]:
        company = db.execute("SELECT name FROM companies WHERE id = ?", (row["matched_company_id"],)).fetchone()
        if company:
            entry["matched_company_name"] = company["name"]
    return jsonify(entry)


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
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "document_upload"):
        return feature_not_available_response("document_upload", plan_value)

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
    expiry_date, expiry_error, expiry_message = validate_document_expiry_date(doc_type, request.form.get("expiryDate", ""))

    if doc_type not in ALLOWED_DOC_TYPES:
        return jsonify({"error": "invalid_doc_type", "allowed": sorted(ALLOWED_DOC_TYPES)}), 400
    if expiry_error:
        return jsonify({"error": expiry_error, "message": expiry_message}), 400

    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        return jsonify({"error": "missing_file"}), 400

    mime = (uploaded_file.mimetype or "").lower().split(";")[0].strip()
    if mime not in ALLOWED_UPLOAD_MIMETYPES:
        return jsonify({"error": "invalid_file_type"}), 400

    file_data = uploaded_file.read()
    if not file_data:
        return jsonify({"error": "empty_file", "message": "Die Datei ist leer."}), 400
    if len(file_data) > MAX_IMAP_ATTACHMENT_BYTES:
        return jsonify({"error": "file_too_large", "maxBytes": MAX_IMAP_ATTACHMENT_BYTES}), 400

    safe_name = _sanitize_attachment_filename(uploaded_file.filename)

    db = get_db()
    worker = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404
    if g.current_user["role"] != "superadmin" and worker["company_id"] != g.current_user.get("company_id"):
        return jsonify({"error": "forbidden_worker"}), 403
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "document_upload"):
        return feature_not_available_response("document_upload", plan_value)

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
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "document_upload"):
        return feature_not_available_response("document_upload", plan_value)

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
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "document_upload"):
        return feature_not_available_response("document_upload", plan_value)

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
    import socket
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
        return jsonify({"error": "missing_fields", "detail": "Host, Benutzername und Passwort sind erforderlich."}), 400

    _timeout = 15  # Sekunden
    attempts = [(use_ssl, port)]
    # Automatischer Fallback: 993/SSL → 143/STARTTLS und umgekehrt
    if use_ssl and port == 993:
        attempts.append((False, 143))
    elif not use_ssl and port == 143:
        attempts.append((True, 993))

    conn = None
    last_exc = None
    tried_info = []
    for attempt_ssl, attempt_port in attempts:
        label = f"{'SSL' if attempt_ssl else 'STARTTLS'}/{attempt_port}"
        tried_info.append(label)
        try:
            if attempt_ssl:
                conn = imaplib.IMAP4_SSL(host, attempt_port, timeout=_timeout)
            else:
                conn = imaplib.IMAP4(host, attempt_port, timeout=_timeout)
                conn.starttls()
            conn.login(username, password)
            status, _ = conn.select(folder, readonly=True)
            conn.logout()
            if status != "OK":
                return jsonify({"ok": False, "error": f"Ordner '{folder}' nicht gefunden.", "tried": tried_info}), 200
            return jsonify({"ok": True, "message": f"Verbindung zu {host}:{attempt_port} ({'SSL' if attempt_ssl else 'STARTTLS'}) erfolgreich. Ordner '{folder}' gefunden.", "tried": tried_info})
        except (socket.timeout, TimeoutError, ConnectionRefusedError, OSError) as exc:
            last_exc = exc
            try:
                if conn is not None:
                    conn.logout()
            except Exception:
                pass
            conn = None
        except Exception as exc:
            last_exc = exc
            try:
                if conn is not None:
                    conn.logout()
            except Exception:
                pass
            conn = None
            # Auth-Fehler oder Ordner-Fehler – kein Sinn im Fallback
            err_str = str(exc).lower()
            if "auth" in err_str or "login" in err_str or "credent" in err_str or "invalid" in err_str:
                break

    tried_str = " → ".join(tried_info) if tried_info else "keine"
    detail = str(last_exc) if last_exc else "Unbekannter Fehler"
    hint = ""
    if "timed out" in detail.lower() or isinstance(last_exc, (socket.timeout, TimeoutError)):
        hint = f" (Port {port} scheint blockiert – prüfe Firewall/Hosting-Einschränkungen)"
    return jsonify({"ok": False, "error": f"{detail}{hint}", "tried": tried_info, "hint": f"Versucht: {tried_str}"}), 200


@app.get("/")
def root():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/worker.html")
def worker_entry_redirect():
    return send_from_directory(BASE_DIR, "worker.html")


@app.get("/review.html")
def review_page():
    return send_from_directory(BASE_DIR, "review.html")


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


# ═══════════════════════════════════════════════════════════════════════
# NEUE FEATURES: Export · Push-Benachrichtigungen · Urlaubsantraege
# ═══════════════════════════════════════════════════════════════════════

# ── Stundenzettel CSV-Export ─────────────────────────────────────────
@app.route("/api/export/timesheets")
@require_auth
def export_timesheets():
    user = g.current_user
    if user["role"] not in ("superadmin", "company-admin", "turnstile"):
        return jsonify({"error": "forbidden"}), 403
    db = get_db()
    company_id = user.get("company_id")
    if user["role"] == "superadmin":
        company_id = request.args.get("company_id") or None
    date_from = request.args.get("from", (datetime.utcnow() - timedelta(days=30)).date().isoformat())
    date_to = request.args.get("to", datetime.utcnow().date().isoformat())
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to):
        return jsonify({"error": "invalid_date"}), 400
    base_query = """
        SELECT w.last_name, w.first_name, w.badge_id, w.site,
               al.direction, al.gate, al.note, al.timestamp
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE al.timestamp >= ? AND al.timestamp <= ?
    """
    params = [date_from, date_to + "T23:59:59"]
    if company_id:
        base_query += " AND w.company_id = ?"
        params.append(company_id)
    base_query += " AND w.deleted_at IS NULL ORDER BY w.last_name, w.first_name, al.timestamp"
    rows = db.execute(base_query, params).fetchall()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Nachname", "Vorname", "Badge-ID", "Standort", "Richtung", "Tor", "Notiz", "Zeitstempel"])
    for row in rows:
        writer.writerow([row["last_name"], row["first_name"], row["badge_id"], row["site"],
                         row["direction"], row["gate"], row["note"], row["timestamp"]])
    output.seek(0)
    filename = f"stundenliste_{date_from}_{date_to}.csv"
    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ── Audit-Log CSV-Export ─────────────────────────────────────────────
@app.route("/api/export/audit-logs")
@require_auth
@require_roles("superadmin", "company-admin")
def export_audit_logs():
    user = g.current_user
    db = get_db()
    company_id = user.get("company_id")
    if user["role"] == "superadmin":
        company_id = request.args.get("company_id") or None
    limit = min(int(request.args.get("limit", 10000)), 50000)
    if company_id:
        rows = db.execute(
            "SELECT * FROM audit_logs WHERE company_id = ? ORDER BY created_at DESC LIMIT ?",
            (company_id, limit)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Ereignistyp", "Akteur-User-ID", "Akteur-Rolle", "Firma-ID", "Ziel-Typ", "Ziel-ID", "Nachricht", "Zeitstempel"])
    for row in rows:
        writer.writerow([
            row["id"], row["event_type"], row["actor_user_id"] or "",
            row["actor_role"] or "", row["company_id"] or "",
            row["target_type"] or "", row["target_id"] or "",
            row["message"], row["created_at"]
        ])
    output.seek(0)
    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_log.csv"'}
    )


# ── Push-Benachrichtigungen (VAPID) ──────────────────────────────────
@app.route("/api/worker-app/push-vapid-key")
def get_vapid_public_key():
    key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    return jsonify({"publicKey": key or None})


@app.post("/api/worker-app/push-subscribe")
@require_worker_session
def worker_push_subscribe():
    worker = g.worker
    data = request.get_json(silent=True) or {}
    endpoint = str(data.get("endpoint", "")).strip()
    p256dh = str(data.get("p256dh", "")).strip()
    auth_key = str(data.get("auth", "")).strip()
    if not endpoint or not p256dh or not auth_key:
        return jsonify({"error": "missing_fields"}), 400
    if len(endpoint) > 600 or len(p256dh) > 256 or len(auth_key) > 64:
        return jsonify({"error": "invalid_subscription"}), 400
    db = get_db()
    existing = db.execute("SELECT id FROM push_subscriptions WHERE endpoint = ?", (endpoint,)).fetchone()
    if existing:
        db.execute(
            "UPDATE push_subscriptions SET worker_id = ?, company_id = ?, p256dh = ?, auth = ? WHERE endpoint = ?",
            (worker["id"], worker["company_id"], p256dh, auth_key, endpoint)
        )
    else:
        sub_id = f"psub-{secrets.token_hex(8)}"
        db.execute(
            "INSERT INTO push_subscriptions (id, worker_id, company_id, endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sub_id, worker["id"], worker["company_id"], endpoint, p256dh, auth_key, now_iso())
        )
    db.commit()
    return jsonify({"ok": True})


@app.post("/api/push/trigger-checkout-reminders")
@require_auth
@require_roles("superadmin", "company-admin")
def trigger_checkout_reminders():
    try:
        from pywebpush import webpush, WebPushException  # noqa: F401
    except ImportError:
        return jsonify({"error": "push_not_configured", "detail": "pywebpush not installed"}), 503
    vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    vapid_email = os.getenv("VAPID_EMAIL", "mailto:admin@example.com").strip()
    if not vapid_private_key:
        return jsonify({"error": "vapid_not_configured"}), 503
    user = g.current_user
    db = get_db()
    company_id = user.get("company_id")
    if user["role"] == "superadmin":
        body = request.get_json(silent=True) or {}
        company_id = body.get("company_id") or company_id
    today = datetime.utcnow().date().isoformat()
    if company_id:
        checked_in_rows = db.execute(
            """SELECT DISTINCT al.worker_id FROM access_logs al
               JOIN workers w ON w.id = al.worker_id
               WHERE al.direction = 'in' AND al.timestamp >= ?
               AND w.company_id = ?
               AND al.worker_id NOT IN (
                   SELECT worker_id FROM access_logs WHERE direction = 'out' AND timestamp >= ?
               )""",
            (today, company_id, today)
        ).fetchall()
    else:
        checked_in_rows = db.execute(
            """SELECT DISTINCT worker_id FROM access_logs
               WHERE direction = 'in' AND timestamp >= ?
               AND worker_id NOT IN (
                   SELECT worker_id FROM access_logs WHERE direction = 'out' AND timestamp >= ?
               )""",
            (today, today)
        ).fetchall()
    worker_ids = [r[0] for r in checked_in_rows]
    sent = 0
    errors = 0
    for wid in worker_ids:
        subs = db.execute("SELECT * FROM push_subscriptions WHERE worker_id = ?", (wid,)).fetchall()
        for sub in subs:
            try:
                from pywebpush import webpush  # noqa: F811
                webpush(
                    subscription_info={
                        "endpoint": sub["endpoint"],
                        "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}
                    },
                    data=json.dumps({
                        "title": "Nicht ausgebucht?",
                        "body": "Du bist noch eingebucht. Vergessen auszustempeln?",
                        "tag": "checkout-reminder"
                    }),
                    vapid_private_key=vapid_private_key,
                    vapid_claims={"sub": vapid_email}
                )
                sent += 1
            except Exception:
                errors += 1
    return jsonify({"ok": True, "sent": sent, "errors": errors, "workers_reminded": len(worker_ids)})


# ── Urlaubsantraege & Krankmeldungen ─────────────────────────────────
@app.route("/api/worker-app/leave-requests", methods=["GET"])
@require_worker_session
def worker_get_leave_requests():
    worker = g.worker
    db = get_db()
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "leave_management"):
        return feature_not_available_response("leave_management", plan_value)
    rows = db.execute(
        "SELECT * FROM leave_requests WHERE worker_id = ? ORDER BY created_at DESC LIMIT 100",
        (worker["id"],)
    ).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/worker-app/leave-requests", methods=["POST"])
@require_worker_session
def worker_submit_leave_request():
    worker = g.worker
    db = get_db()
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "leave_management"):
        return feature_not_available_response("leave_management", plan_value)
    data = request.get_json(silent=True) or {}
    req_type = str(data.get("type", "")).strip()
    start_date = str(data.get("start_date", "")).strip()
    end_date = str(data.get("end_date", "")).strip()
    note = str(data.get("note", "")).strip()[:500]
    if req_type not in ("urlaub", "krank", "sonstiges"):
        return jsonify({"error": "invalid_type"}), 400
    if not start_date or not end_date:
        return jsonify({"error": "missing_dates"}), 400
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date) or not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date):
        return jsonify({"error": "invalid_date_format"}), 400
    if start_date > end_date:
        return jsonify({"error": "end_before_start"}), 400
    req_id = f"leave-{secrets.token_hex(8)}"
    days_count = _count_working_days(start_date, end_date)
    db.execute(
        "INSERT INTO leave_requests (id, worker_id, company_id, type, start_date, end_date, note, status, days_count, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'ausstehend', ?, ?)",
        (req_id, worker["id"], worker["company_id"], req_type, start_date, end_date, note, days_count, now_iso())
    )
    db.commit()
    log_audit(
        "leave_request.created",
        f"Antrag von {worker['first_name']} {worker['last_name']}: {req_type} {start_date}–{end_date}",
        target_type="worker", target_id=worker["id"], company_id=worker["company_id"]
    )

    # E-Mail-Benachrichtigung an Firmen-Admins
    admin_rows = db.execute(
        "SELECT name, email FROM users WHERE company_id = ? AND role = 'company-admin' AND email != ''",
        (worker["company_id"],)
    ).fetchall()
    if admin_rows:
        type_labels = {"urlaub": "Urlaub", "krank": "Krankmeldung", "sonstiges": "Sonstiger Antrag"}
        req_type_label = type_labels.get(req_type, req_type)
        worker_name = f"{worker['first_name']} {worker['last_name']}"
        subject = f"Neuer Antrag: {req_type_label} – {worker_name}"
        note_html = f'<p style="color:#555;margin:8px 0 0;"><strong>Notiz:</strong> {note}</p>' if note else ""
        html_mail = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;margin:0;padding:32px 0;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table width="580" style="background:#fff;border-radius:12px;overflow:hidden;max-width:580px;width:100%;box-shadow:0 2px 12px rgba(0,0,0,.08);">
  <tr><td style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:24px 32px;">
    <h1 style="margin:0;color:#fff;font-size:20px;">Neuer Abwesenheitsantrag</h1>
    <p style="margin:4px 0 0;color:rgba(255,255,255,.7);font-size:14px;">Bitte im Admin-Portal prüfen</p>
  </td></tr>
  <tr><td style="padding:28px 32px;">
    <p style="color:#444;font-size:16px;"><strong>{worker_name}</strong> ({worker['badge_id']}) hat einen neuen Antrag eingereicht:</p>
    <p style="font-size:18px;font-weight:700;color:#1a1a2e;">{req_type_label} · {start_date} – {end_date}</p>
    {note_html}
    <p style="margin-top:24px;color:#888;font-size:13px;">Jetzt im BauPass Admin-Portal prüfen und genehmigen oder ablehnen.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
        text_mail = f"Neuer Antrag von {worker_name}: {req_type_label} {start_date}–{end_date}." + (f"\nNotiz: {note}" if note else "")
        settings_row = db.execute("SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1").fetchone()
        s = dict(settings_row) if settings_row else {}
        sender_email = (s.get("smtp_sender_email") or "").strip() or "noreply@baupass.de"
        sender_name = (s.get("smtp_sender_name") or "BauPass").strip()
        for admin in admin_rows:
            try:
                _send_via_any_api(subject, sender_email, sender_name, admin["email"], text_mail, html_mail)
            except Exception:
                pass

    return jsonify({"ok": True, "id": req_id}), 201


@app.route("/api/leave-requests")
@require_auth
def get_leave_requests():
    user = g.current_user
    if user["role"] not in ("superadmin", "company-admin", "turnstile"):
        return jsonify({"error": "forbidden"}), 403
    db = get_db()
    company_id = user.get("company_id")
    if user["role"] == "superadmin":
        company_id = request.args.get("company_id") or None
    status_filter = request.args.get("status", "").strip()
    query = """
        SELECT lr.id, lr.worker_id, lr.company_id, lr.type, lr.start_date, lr.end_date,
               lr.note, lr.status, lr.reviewed_by_user_id, lr.reviewed_at, lr.review_note,
               lr.created_at, lr.email_forwarded_to, lr.days_count,
               w.first_name, w.last_name, w.badge_id,
               (w.first_name || ' ' || w.last_name) AS worker_name
        FROM leave_requests lr
        JOIN workers w ON w.id = lr.worker_id
        WHERE 1=1
    """
    params = []
    if company_id:
        query += " AND lr.company_id = ?"
        params.append(company_id)
    if status_filter:
        query += " AND lr.status = ?"
        params.append(status_filter)
    query += " ORDER BY lr.created_at DESC LIMIT 500"
    rows = db.execute(query, params).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/leave-requests/<req_id>", methods=["PUT"])
@require_auth
def review_leave_request(req_id):
    user = g.current_user
    if user["role"] not in ("superadmin", "company-admin", "turnstile"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    new_status = str(data.get("status", "")).strip()
    review_note = str(data.get("review_note", "")).strip()[:500]
    if new_status not in ("genehmigt", "abgelehnt", "ausstehend"):
        return jsonify({"error": "invalid_status"}), 400
    db = get_db()
    req_row = db.execute("SELECT * FROM leave_requests WHERE id = ?", (req_id,)).fetchone()
    if not req_row:
        return jsonify({"error": "not_found"}), 404
    if user["role"] != "superadmin" and req_row["company_id"] != user.get("company_id"):
        return jsonify({"error": "forbidden"}), 403
    db.execute(
        "UPDATE leave_requests SET status = ?, reviewed_by_user_id = ?, reviewed_at = ?, review_note = ? WHERE id = ?",
        (new_status, user["id"], now_iso(), review_note, req_id)
    )
    db.commit()
    log_audit(
        f"leave_request.{new_status}",
        f"Antrag {req_id} → {new_status} von {user['username']}",
        target_type="worker", target_id=req_row["worker_id"],
        company_id=req_row["company_id"], actor=user
    )

    # Push-Benachrichtigung an Mitarbeiter
    status_label_de = {"genehmigt": "genehmigt ✓", "abgelehnt": "abgelehnt ✗", "ausstehend": "ausstehend"}.get(new_status, new_status)
    type_labels = {"urlaub": "Urlaub", "krank": "Krankmeldung", "sonstiges": "Antrag"}
    req_type_label = type_labels.get(req_row["type"], req_row["type"])
    push_title = f"Antrag {status_label_de}"
    push_body = f"{req_type_label} {req_row['start_date']}–{req_row['end_date']}"
    if review_note:
        push_body += f" – {review_note[:80]}"
    _send_push_to_worker(db, req_row["worker_id"], push_title, push_body, tag="leave-request-status")

    # E-Mail-Benachrichtigung an Mitarbeiter (falls contact_email gesetzt)
    if new_status in ("genehmigt", "abgelehnt"):
        html_note = f'<p style="color:#555;margin:12px 0 0;"><strong>Bemerkung:</strong> {review_note}</p>' if review_note else ""
        status_color = "#1a7a3a" if new_status == "genehmigt" else "#c53d2f"
        status_icon = "✓" if new_status == "genehmigt" else "✗"
        html_mail = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;margin:0;padding:32px 0;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table width="580" style="background:#fff;border-radius:12px;overflow:hidden;max-width:580px;width:100%;box-shadow:0 2px 12px rgba(0,0,0,.08);">
  <tr><td style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:24px 32px;">
    <h1 style="margin:0;color:#fff;font-size:20px;">Ihr Antrag wurde bearbeitet</h1>
  </td></tr>
  <tr><td style="padding:28px 32px;">
    <p style="font-size:22px;font-weight:700;color:{status_color};">{status_icon} {req_type_label} {status_label_de}</p>
    <p style="color:#444;">Zeitraum: <strong>{req_row['start_date']}</strong> bis <strong>{req_row['end_date']}</strong></p>
    {html_note}
    <p style="margin-top:24px;color:#888;font-size:13px;">Bei Fragen wenden Sie sich an Ihren Administrator.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
        text_mail = f"Ihr {req_type_label} ({req_row['start_date']}–{req_row['end_date']}) wurde {status_label_de}.\n" + (f"Bemerkung: {review_note}" if review_note else "")
        _send_email_to_worker(db, req_row["worker_id"], f"Antrag {status_label_de}: {req_type_label}", text_mail, html_mail)

    return jsonify({"ok": True})


@app.get("/api/leave-requests/<req_id>/export.pdf")
@require_auth
def export_leave_request_pdf(req_id):
    user = g.current_user
    if user["role"] not in ("superadmin", "company-admin", "turnstile"):
        return jsonify({"error": "forbidden"}), 403

    db = get_db()
    row = db.execute(
        """
        SELECT lr.*, w.first_name, w.last_name, w.badge_id,
               reviewer.username AS reviewer_username
        FROM leave_requests lr
        JOIN workers w ON w.id = lr.worker_id
        LEFT JOIN users reviewer ON reviewer.id = lr.reviewed_by_user_id
        WHERE lr.id = ?
        """,
        (req_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "not_found"}), 404

    if user["role"] != "superadmin" and row["company_id"] != user.get("company_id"):
        return jsonify({"error": "forbidden"}), 403

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return jsonify({"error": "pdf_dependency_missing", "message": "Bitte reportlab installieren."}), 503

    data = row_to_dict(row)
    worker_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or data.get("worker_id", "-")
    type_label = {"urlaub": "Urlaub", "krank": "Krankmeldung", "sonstiges": "Sonstiges"}.get(data.get("type"), data.get("type") or "-")

    buffer = io.BytesIO()
    pdf = rl_canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    y = page_height - 48

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(40, y, "BauPass - Urlaubsantrag")
    y -= 20
    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, y, f"Exportiert: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    y -= 24
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Antragsdaten")
    y -= 14
    pdf.setFont("Helvetica", 10)

    lines = [
        f"ID: {data.get('id', '-')}",
        f"Mitarbeiter: {worker_name}",
        f"Badge-ID: {data.get('badge_id', '-')}",
        f"Art: {type_label}",
        f"Zeitraum: {data.get('start_date', '-')} bis {data.get('end_date', '-')}",
        f"Arbeitstage: {int(data.get('days_count') or 0)}",
        f"Status: {data.get('status', '-')}",
        f"Eingereicht am: {data.get('created_at', '-')}",
        f"Bearbeitet von: {data.get('reviewer_username') or '-'}",
        f"Bearbeitet am: {data.get('reviewed_at') or '-'}",
    ]
    for line in lines:
        pdf.drawString(40, y, line)
        y -= 14

    note = (data.get("note") or "").strip() or "-"
    review_note = (data.get("review_note") or "").strip() or "-"

    y -= 8
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Notiz")
    y -= 14
    pdf.setFont("Helvetica", 10)
    for chunk in textwrap.wrap(note, width=95)[:10]:
        pdf.drawString(40, y, chunk)
        y -= 13

    y -= 6
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Entscheidungsnotiz")
    y -= 14
    pdf.setFont("Helvetica", 10)
    for chunk in textwrap.wrap(review_note, width=95)[:10]:
        pdf.drawString(40, y, chunk)
        y -= 13

    pdf.save()
    buffer.seek(0)
    filename = f"urlaubsantrag-{str(req_id)[:24]}.pdf"
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


# ── Mitarbeiter-App: eigene Stundennachweise ────────────────────────────────

@app.get("/api/worker-app/my-timesheets")
@require_worker_session
def worker_app_my_timesheets():
    db = get_db()
    worker = g.worker
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "worker_hours_report"):
        return feature_not_available_response("worker_hours_report", plan_value)
    rows = db.execute(
        "SELECT direction, gate, note, timestamp FROM access_logs WHERE worker_id = ? ORDER BY timestamp DESC LIMIT 60",
        (worker["id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ── Company-Admin: Arbeitsstunden-Uebersicht pro Mitarbeiter/Monat ────────

@app.get("/api/companies/<company_id>/worker-hours-summary")
@require_auth
@require_roles("superadmin", "company-admin")
def company_worker_hours_summary(company_id):
    """
    Liefert fuer jeden Mitarbeiter die monatliche Arbeitsstunden-Summe.
    Query-Parameter: month=YYYY-MM (Standard: aktueller Monat)
    """
    from datetime import datetime as _dt
    db = get_db()
    user = g.current_user
    if user["role"] != "superadmin" and user.get("company_id") != company_id:
        return jsonify({"error": "forbidden"}), 403
    company = db.execute("SELECT id FROM companies WHERE id = ? AND deleted_at IS NULL", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "company_not_found"}), 404
    plan_value = get_company_plan(db, company_id)
    if not company_has_feature(plan_value, "worker_hours_report"):
        return feature_not_available_response("worker_hours_report", plan_value)

    month_param = (request.args.get("month") or "").strip()
    if month_param and len(month_param) == 7 and "-" in month_param:
        month_prefix = month_param  # "YYYY-MM"
    else:
        month_prefix = _dt.now().strftime("%Y-%m")

    # Alle check-in / check-out des Monats fuer diese Firma
    rows = db.execute(
        """
        SELECT al.worker_id, al.direction, al.timestamp,
               w.first_name, w.last_name, w.badge_id, w.role AS worker_role
        FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ?
          AND w.deleted_at IS NULL
          AND w.worker_type = 'worker'
          AND al.timestamp LIKE ?
        ORDER BY al.worker_id, al.timestamp
        """,
        (company_id, f"{month_prefix}%"),
    ).fetchall()

    # Stunden pro Mitarbeiter berechnen: check-in -> naechstes check-out (selber Tag)
    from collections import defaultdict
    worker_data = defaultdict(lambda: {"firstName": "", "lastName": "", "badgeId": "", "role": "", "totalMinutes": 0, "daysWorked": set()})
    by_worker = defaultdict(list)
    for r in rows:
        by_worker[r["worker_id"]].append(dict(r))
        d = worker_data[r["worker_id"]]
        d["firstName"] = r["first_name"] or ""
        d["lastName"] = r["last_name"] or ""
        d["badgeId"] = r["badge_id"] or ""
        d["role"] = r["worker_role"] or ""

    for wid, events in by_worker.items():
        pending_checkin = None
        for ev in events:
            if ev["direction"] == "check-in":
                pending_checkin = ev["timestamp"]
            elif ev["direction"] == "check-out" and pending_checkin:
                try:
                    from datetime import datetime as _dt2
                    t_in  = _dt2.fromisoformat(pending_checkin[:19])
                    t_out = _dt2.fromisoformat(ev["timestamp"][:19])
                    diff  = int((t_out - t_in).total_seconds() / 60)
                    if 0 < diff < 1440:  # max 24h pro Einheit
                        worker_data[wid]["totalMinutes"] += diff
                        worker_data[wid]["daysWorked"].add(pending_checkin[:10])
                except Exception:
                    pass
                pending_checkin = None

    result = []
    for wid, d in worker_data.items():
        total_h = round(d["totalMinutes"] / 60, 1)
        result.append({
            "workerId": wid,
            "firstName": d["firstName"],
            "lastName": d["lastName"],
            "badgeId": d["badgeId"],
            "role": d["role"],
            "totalHours": total_h,
            "daysWorked": len(d["daysWorked"]),
        })

    result.sort(key=lambda x: (x["lastName"] or "").lower())
    return jsonify({"month": month_prefix, "workers": result})


# ── Company-Admin: Stundendetails pro Mitarbeiter ─────────────────────────

@app.get("/api/companies/<company_id>/workers/<worker_id>/timeline")
@require_auth
@require_roles("superadmin", "company-admin")
def company_worker_timeline(company_id, worker_id):
    """
    Liefert alle Zutrittsereignisse (check-in/check-out) fuer einen einzelnen
    Mitarbeiter fuer den gewaehlten Monat, als tagesweise gruppierte Timeline.
    Query-Parameter: month=YYYY-MM (Standard: aktueller Monat)
    """
    from datetime import datetime as _dt
    db = get_db()
    user = g.current_user
    if user["role"] != "superadmin" and user.get("company_id") != company_id:
        return jsonify({"error": "forbidden"}), 403

    plan_value = get_company_plan(db, company_id)
    if not company_has_feature(plan_value, "worker_hours_report"):
        return feature_not_available_response("worker_hours_report", plan_value)

    # Verify worker belongs to company
    worker = db.execute(
        "SELECT id, first_name, last_name, badge_id FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL",
        (worker_id, company_id),
    ).fetchone()
    if not worker:
        return jsonify({"error": "worker_not_found"}), 404

    month_param = (request.args.get("month") or "").strip()
    if month_param and len(month_param) == 7 and "-" in month_param:
        month_prefix = month_param
    else:
        month_prefix = _dt.now().strftime("%Y-%m")

    rows = db.execute(
        """
        SELECT direction, gate, note, timestamp
        FROM access_logs
        WHERE worker_id = ?
          AND timestamp LIKE ?
        ORDER BY timestamp ASC
        """,
        (worker_id, f"{month_prefix}%"),
    ).fetchall()

    # Group by day and pair check-in / check-out
    from collections import defaultdict, OrderedDict
    by_day = OrderedDict()
    for r in rows:
        day = r["timestamp"][:10]
        if day not in by_day:
            by_day[day] = []
        by_day[day].append({"direction": r["direction"], "gate": r["gate"] or "", "note": r["note"] or "", "timestamp": r["timestamp"]})

    days = []
    for day, events in by_day.items():
        # Pair sessions
        sessions = []
        pending_in = None
        day_minutes = 0
        for ev in events:
            if ev["direction"] == "check-in":
                pending_in = ev
            elif ev["direction"] == "check-out":
                duration = None
                if pending_in:
                    try:
                        t_in  = _dt.fromisoformat(pending_in["timestamp"][:19])
                        t_out = _dt.fromisoformat(ev["timestamp"][:19])
                        diff  = int((t_out - t_in).total_seconds() / 60)
                        if 0 < diff < 1440:
                            duration = diff
                            day_minutes += diff
                    except Exception:
                        pass
                sessions.append({
                    "checkIn":  pending_in["timestamp"] if pending_in else None,
                    "checkOut": ev["timestamp"],
                    "gateIn":   pending_in["gate"] if pending_in else "",
                    "gateOut":  ev["gate"],
                    "durationMinutes": duration,
                })
                pending_in = None
        # Unclosed check-in (still on-site)
        if pending_in:
            sessions.append({
                "checkIn":  pending_in["timestamp"],
                "checkOut": None,
                "gateIn":   pending_in["gate"],
                "gateOut":  "",
                "durationMinutes": None,
            })
        days.append({"date": day, "sessions": sessions, "dayMinutes": day_minutes})

    return jsonify({
        "month": month_prefix,
        "workerId": worker_id,
        "firstName": worker["first_name"] or "",
        "lastName": worker["last_name"] or "",
        "badgeId": worker["badge_id"] or "",
        "days": days,
    })


# ── Company Plan-Features Endpoint ────────────────────────────────────────

@app.get("/api/companies/<company_id>/plan-features")
@require_auth
@require_roles("superadmin", "company-admin")
def get_company_plan_features(company_id):
    """Gibt die verfuegbaren Features fuer die Plan-Stufe der Firma zurueck."""
    db = get_db()
    user = g.current_user
    if user["role"] != "superadmin" and user.get("company_id") != company_id:
        return jsonify({"error": "forbidden"}), 403
    company = db.execute("SELECT plan FROM companies WHERE id = ? AND deleted_at IS NULL", (company_id,)).fetchone()
    if not company:
        return jsonify({"error": "company_not_found"}), 404
    plan = str(company["plan"] or "starter").strip().lower()
    return jsonify({
        "plan": plan,
        "features": get_plan_features(plan),
        "planRank": PLAN_RANK.get(plan, 1),
        "availablePlans": [
            {"key": "tageskarte", "labelDe": "Tageskarte", "priceEur": 19.0, "rank": 0},
            {"key": "starter", "labelDe": "Start", "priceEur": 49.0, "workerPriceEur": 1.50, "rank": 1},
            {"key": "professional", "labelDe": "Professional", "priceEur": 99.0, "workerPriceEur": 2.50, "rank": 2},
            {"key": "enterprise", "labelDe": "Enterprise", "priceEur": 199.0, "workerPriceEur": 0.0, "rank": 3},
        ],
    })


# ── Mitarbeiter-App: eigene Dokumente ──────────────────────────────────────

@app.get("/api/worker-app/my-documents")
@require_worker_session
def worker_app_my_documents():
    db = get_db()
    worker = g.worker
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "document_upload"):
        return feature_not_available_response("document_upload", plan_value)
    rows = db.execute(
        "SELECT doc_type, filename, file_size, created_at, notes, expiry_date FROM worker_documents WHERE worker_id = ? ORDER BY created_at DESC",
        (worker["id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/worker-app/company-admins", methods=["GET"])
@require_worker_session
def worker_get_company_admins():
    """Gibt Firmen-Admin-E-Mail-Adressen zurueck (fuer Chef-Versand-Vorschlag)."""
    worker = g.worker
    db = get_db()
    rows = db.execute(
        "SELECT name, email FROM users WHERE company_id = ? AND role = 'company-admin' AND email != '' ORDER BY name",
        (worker["company_id"],)
    ).fetchall()
    return jsonify([{"name": r["name"], "email": r["email"]} for r in rows])


@app.route("/api/worker-app/leave-requests/<req_id>/send-email", methods=["POST"])
@require_worker_session
def worker_send_leave_request_email(req_id):
    worker = g.worker
    db = get_db()
    plan_value = get_company_plan(db, worker["company_id"])
    if not company_has_feature(plan_value, "leave_management"):
        return feature_not_available_response("leave_management", plan_value)
    req_row = db.execute(
        "SELECT * FROM leave_requests WHERE id = ? AND worker_id = ?",
        (req_id, worker["id"])
    ).fetchone()
    if not req_row:
        return jsonify({"error": "not_found"}), 404
    data = request.get_json(silent=True) or {}
    recipient_email = str(data.get("recipient_email", "")).strip()
    if not recipient_email or "@" not in recipient_email:
        return jsonify({"error": "invalid_email"}), 400

    type_labels = {"urlaub": "Urlaub", "krank": "Krankmeldung", "sonstiges": "Sonstiger Antrag"}
    req_type = type_labels.get(req_row["type"], req_row["type"])
    worker_name = f"{worker['first_name']} {worker['last_name']}"
    subject = f"Abwesenheitsantrag: {req_type} – {worker_name}"

    note_html = (
        f'<tr><td style="padding:10px 12px;border-bottom:1px solid #eee;color:#555;width:40%;">Anmerkung</td>'
        f'<td style="padding:10px 12px;border-bottom:1px solid #eee;">{req_row["note"]}</td></tr>'
    ) if req_row["note"] else ""

    html_body = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>{subject}</title></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);max-width:600px;width:100%;">
      <tr><td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:28px 36px;">
        <h1 style="margin:0;color:#fff;font-size:22px;">Abwesenheitsantrag</h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,.7);font-size:14px;">Eingereicht über BauPass Worker App</p>
      </td></tr>
      <tr><td style="padding:28px 36px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee;border-radius:8px;overflow:hidden;border-spacing:0;">
          <tr><td style="padding:10px 12px;background:#f8f9fa;border-bottom:1px solid #eee;color:#555;width:40%;font-weight:600;">Mitarbeiter</td><td style="padding:10px 12px;background:#f8f9fa;border-bottom:1px solid #eee;font-weight:600;">{worker_name}</td></tr>
          <tr><td style="padding:10px 12px;border-bottom:1px solid #eee;color:#555;">Badge-ID</td><td style="padding:10px 12px;border-bottom:1px solid #eee;">{worker['badge_id']}</td></tr>
          <tr><td style="padding:10px 12px;border-bottom:1px solid #eee;color:#555;">Art</td><td style="padding:10px 12px;border-bottom:1px solid #eee;"><strong>{req_type}</strong></td></tr>
          <tr><td style="padding:10px 12px;border-bottom:1px solid #eee;color:#555;">Von</td><td style="padding:10px 12px;border-bottom:1px solid #eee;">{req_row['start_date']}</td></tr>
          <tr><td style="padding:10px 12px;border-bottom:1px solid #eee;color:#555;">Bis</td><td style="padding:10px 12px;border-bottom:1px solid #eee;">{req_row['end_date']}</td></tr>
          {note_html}
          <tr><td style="padding:10px 12px;color:#555;">Eingereicht am</td><td style="padding:10px 12px;">{req_row['created_at'][:10]}</td></tr>
        </table>
        <p style="margin:24px 0 0;color:#777;font-size:13px;">Bitte prüfen Sie diesen Antrag im BauPass Admin-Portal.</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""

    text_body = (
        f"Abwesenheitsantrag von {worker_name} (Badge-ID: {worker['badge_id']})\n"
        f"Art: {req_type}\n"
        f"Zeitraum: {req_row['start_date']} bis {req_row['end_date']}\n"
        f"Anmerkung: {req_row['note'] or chr(8211)}\n"
        f"Eingereicht am: {req_row['created_at'][:10]}"
    )

    settings_row = db.execute(
        "SELECT smtp_sender_email, smtp_sender_name, smtp_host, smtp_port, smtp_username, smtp_password, smtp_use_tls FROM settings WHERE id = 1"
    ).fetchone()
    settings = dict(settings_row) if settings_row else {}
    sender_email = (settings.get("smtp_sender_email") or "").strip() or "noreply@baupass.de"
    sender_name = (settings.get("smtp_sender_name") or "BauPass").strip()

    # HTML-Datei als Anhang (base64)
    import base64 as _b64
    html_attachment_content = _b64.b64encode(html_body.encode("utf-8")).decode("ascii")
    attachments = [{"filename": "Urlaubsantrag.html", "content": html_attachment_content, "type": "text/html"}]

    ok, err, _ = _send_via_any_api(subject, sender_email, sender_name, recipient_email, text_body, html_body, attachments=attachments)
    if not ok:
        smtp_host = (settings.get("smtp_host") or "").strip()
        if smtp_host:
            try:
                import smtplib
                from email.message import EmailMessage as _EM
                msg = _EM()
                msg["Subject"] = subject
                msg["From"] = f'"{sender_name}" <{sender_email}>'
                msg["To"] = recipient_email
                msg.set_content(text_body)
                msg.add_alternative(html_body, subtype="html")
                msg.add_attachment(
                    html_body.encode("utf-8"),
                    maintype="text", subtype="html",
                    filename="Urlaubsantrag.html"
                )
                with smtplib.SMTP(smtp_host, int(settings.get("smtp_port") or 587), timeout=10) as smtp:
                    if int(settings.get("smtp_use_tls") or 0) == 1:
                        smtp.starttls()
                    smtp_user = (settings.get("smtp_username") or "").strip()
                    if smtp_user:
                        smtp.login(smtp_user, settings.get("smtp_password") or "")
                    smtp.send_message(msg)
            except Exception as exc:
                app.logger.error(f"[LEAVE-MAIL] SMTP failed: {exc}")
                return jsonify({"error": "send_failed", "details": str(exc)}), 500
        else:
            return jsonify({"error": "no_email_provider", "details": err}), 500

    # Weitergeleitete E-Mail-Adresse speichern
    db.execute(
        "UPDATE leave_requests SET email_forwarded_to = ? WHERE id = ?",
        (recipient_email, req_id)
    )
    db.commit()

    log_audit(
        "leave_request.email_sent",
        f"Antrag {req_id} per E-Mail an {recipient_email} gesendet ({worker_name})",
        target_type="worker", target_id=worker["id"], company_id=worker["company_id"]
    )
    return jsonify({"ok": True})


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    ssl_context = get_ssl_context_from_env()
    app.run(host=host, port=port, ssl_context=ssl_context)
