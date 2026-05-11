from __future__ import annotations

import re
import sys
from pathlib import Path

BLOCK_PATTERNS = [
    r"threading\.Thread\(",
    r"ThreadPoolExecutor\(",
]

ALLOW_MARKER = "# baupass:allow-inline-thread"

# Baseline exceptions already موجودة في server.py. الهدف منع إدخال المزيد.
ALLOWED_EXISTING_SNIPPETS = {
    'threading.Thread(target=scheduler_loop, name="baupass-dunning-scheduler", daemon=True).start()',
    'threading.Thread(target=worker_session_cleanup_loop, name="baupass-worker-session-cleanup", daemon=True).start()',
    'threading.Thread(target=invoice_retry_loop, name="baupass-invoice-retry", daemon=True).start()',
    'threading.Thread(target=imap_loop, name="baupass-imap-poller", daemon=True).start()',
    'with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:',
}


def main() -> int:
    target = Path("backend/server.py")
    if not target.exists():
        print("[thread-guard] skipped: backend/server.py not found")
        return 0

    text = target.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    violations: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        if ALLOW_MARKER in line:
            continue
        for pat in BLOCK_PATTERNS:
            if re.search(pat, line):
                snippet = line.strip()
                if snippet in ALLOWED_EXISTING_SNIPPETS:
                    break
                violations.append((idx, snippet))
                break

    if violations:
        print("[thread-guard] blocked inline threading usage in backend/server.py")
        for line_no, snippet in violations[:20]:
            print(f"  line {line_no}: {snippet}")
        print("Fix: move background work to backend/app/tasks and RQ worker.")
        print(f"If a temporary exception is absolutely needed, add marker: {ALLOW_MARKER}")
        return 1

    print("[thread-guard] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
