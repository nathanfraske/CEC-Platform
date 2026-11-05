#!/usr/bin/env python3
"""Run fresh regressions in memory-bounded, short-lived pytest processes."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cec_pipeline.regression import main

if __name__ == "__main__":
    raise SystemExit(main())
