"""Pytest bootstrap — must run before `import server` in test modules."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BAUPASS_ENV", "testing")
os.environ.setdefault("BAUPASS_ENABLE_BACKGROUND_JOBS", "0")
os.environ.setdefault("BAUPASS_ENABLE_IMAP_POLLER", "0")
os.environ.setdefault("BAUPASS_SKIP_IMAP_POLL", "1")
