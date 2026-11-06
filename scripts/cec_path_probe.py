"""Read-only explicit-path scout; invocation is bounded by the calling worker.

Example: PYTHONPATH=src:scripts timeout 10s python3 scripts/cec_path_probe.py
  --board board.kicad_pcb --sha256 <exact hash> --request path.json
The request contains net, layer, width_nm, points_nm and clearance_nm only.
"""
import argparse
import hashlib
import json
from pathlib import Path

from cec_pipeline.native import _native
from cec_pipeline.path_probe import inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    source = Path(args.board).resolve(strict=True)
    request = json.loads(Path(args.request).read_text())
    expected = {"net", "layer", "width_nm", "points_nm", "clearance_nm"}
    if set(request) != expected:
        raise ValueError("exact_path_probe_fields_required")
    family = [source, source.with_suffix(".kicad_pro"), source.with_suffix(".kicad_dru")]
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    before = {str(p): sha(p) for p in family}
    if source.suffix != ".kicad_pcb" or before[str(source)] != args.sha256:
        raise ValueError("exact_saved_source_board_required")
    native, _quiet = _native()
    result = inspect(native.LoadBoard(str(source)), **request)
    if {str(p): sha(p) for p in family} != before:
        raise ValueError("source_family_changed_during_path_probe")
    result.update(source_family_sha256=before, source_unchanged=True)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
