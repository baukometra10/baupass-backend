from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.entrypoint import main as shared_main


if __name__ == "__main__":
    shared_main("prod")
