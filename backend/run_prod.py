import socket
import sys
import os
import logging

from waitress import serve

from server import app, get_runtime_diagnostics, init_db, check_and_apply_overdue_suspensions, run_invoice_dunning_cycle, get_db


HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))


def _int_env(name, default, minimum):
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, value)


WAITRESS_THREADS = _int_env("BAUPASS_WAITRESS_THREADS", 16, 8)
WAITRESS_CONNECTION_LIMIT = _int_env("BAUPASS_WAITRESS_CONNECTION_LIMIT", 400, 100)
WAITRESS_CHANNEL_TIMEOUT = _int_env("BAUPASS_WAITRESS_CHANNEL_TIMEOUT", 120, 30)
WAITRESS_CLEANUP_INTERVAL = _int_env("BAUPASS_WAITRESS_CLEANUP_INTERVAL", 30, 5)
SHOW_WAITRESS_QUEUE_WARNINGS = str(os.getenv("BAUPASS_WAITRESS_QUEUE_WARNINGS", "0")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def port_is_listening(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


if __name__ == "__main__":
    run_dunning_on_boot = str(os.getenv("BAUPASS_RUN_DUNNING_ON_BOOT", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    init_db()
    with app.app_context():
        db = get_db()
        dunning_result = {
            "remindersSent": 0,
            "reminderFailures": 0,
            "overdueUpdated": 0,
        }
        if run_dunning_on_boot:
            # Optional on-boot dunning; disabled by default to avoid delaying bind/readiness on platforms like Railway.
            dunning_result = run_invoice_dunning_cycle(db)
        suspended = check_and_apply_overdue_suspensions(db)
    if dunning_result.get("remindersSent") or dunning_result.get("reminderFailures") or dunning_result.get("overdueUpdated"):
        print(
            "[baupass] Dunning cycle: "
            f"sent={dunning_result.get('remindersSent', 0)}, "
            f"failed={dunning_result.get('reminderFailures', 0)}, "
            f"overdue_updated={dunning_result.get('overdueUpdated', 0)}"
        )
    if suspended:
        print(f"[baupass] Auto-suspended {len(suspended)} company/ies due to overdue invoices")
    diagnostics = get_runtime_diagnostics()
    warnings = diagnostics.get("warnings", [])
    print(f"[baupass] Runtime-Check: {len(warnings)} Warnung(en)")
    resend_configured = bool(diagnostics.get("resendConfigured"))
    resend_source = str(diagnostics.get("resendKeySource") or "")
    if resend_configured:
        print(f"[baupass] Resend: configured (source={resend_source or 'unknown'})")
    else:
        print("[baupass] Resend: NOT configured")
    for warning in warnings:
        print(f"[baupass][warn] {warning['code']}: {warning['message']}")
    if not SHOW_WAITRESS_QUEUE_WARNINGS:
        # Queue depth warnings are noisy under short bursts and do not always indicate a real issue.
        logging.getLogger("waitress.queue").setLevel(logging.ERROR)
    print(
        "[baupass] Waitress: "
        f"threads={WAITRESS_THREADS}, "
        f"connection_limit={WAITRESS_CONNECTION_LIMIT}, "
        f"channel_timeout={WAITRESS_CHANNEL_TIMEOUT}s"
    )
    serve(
        app,
        host=HOST,
        port=PORT,
        threads=WAITRESS_THREADS,
        connection_limit=WAITRESS_CONNECTION_LIMIT,
        channel_timeout=WAITRESS_CHANNEL_TIMEOUT,
        cleanup_interval=WAITRESS_CLEANUP_INTERVAL,
    )
