from __future__ import annotations

import os
import sys
from pprint import pprint
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.database import postgres_preflight


def main() -> int:
    config = {
        "DATABASE_URL": os.getenv("DATABASE_URL", "").strip(),
        "DB_POOL_MIN_SIZE": int(os.getenv("DB_POOL_MIN_SIZE", "2")),
        "DB_POOL_MAX_SIZE": int(os.getenv("DB_POOL_MAX_SIZE", "20")),
        "DB_POOL_TIMEOUT_SECONDS": int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "10")),
    }

    result = postgres_preflight(config)
    pprint(result)
    return 0 if result.get("status") in {"ok", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
