#!/usr/bin/env python3
"""Compatibility launcher for the packaged, model-directed PCB control plane."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cec_pipeline.api import *  # noqa: F401,F403 - public compatibility facade

if __name__ == "__main__":
    main()
