#!/usr/bin/env python3
"""Export a verified suite into a fresh portable, non-release checkpoint."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cec_pipeline.checkpoint import export

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--field", nargs=2, action="append", default=[], metavar=("PATH", "SHA256")
    )
    args = parser.parse_args()
    print(
        json.dumps(
            export(args.receipt, args.sha256, args.output, field_receipts=args.field)
        )
    )
