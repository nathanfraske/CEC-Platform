"""Compatibility import for the pure construction algebra."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cec_pipeline.geometry import *  # noqa: F401,F403
