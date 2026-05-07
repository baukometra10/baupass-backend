import json
import os
from pathlib import Path


def load_local_env(root: Path):
    candidates = [
        root / "backend" / ".env.local",
        root / "backend" / ".env",
        root / ".env.local",
        root / ".env",
    ]
    loaded = []
    for env_path in candidates:
        if not env_path.exists() or not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if key in os.environ:
                continue
            os.environ[key] = value
        loaded.append(str(env_path))
    return loaded


def main():
    root = Path(__file__).resolve().parent.parent
    loaded_files = load_local_env(root)

    from backend import server

    status = server._wallet_collect_runtime_status()
    output = {
        "ok": status["ok"],
        "loadedEnvFiles": loaded_files,
        "wallet": status,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if status["ok"]:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
