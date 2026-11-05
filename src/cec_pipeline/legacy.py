"""One explicit boundary to retained CAD validators and domain contracts."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def bootstrap():
    path = str(ROOT / "scripts")
    if path not in sys.path:
        sys.path.insert(0, path)
