import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_physical_baseline as baseline  # noqa: E402


def test_suite_contains_only_current_hierarchical_beta_artifacts():
    suite = baseline.load_suite()
    assert suite["cases"]
    for case in suite["cases"]:
        board, schematic = baseline._resolve_current_beta(case)
        assert os.path.isfile(board)
        assert os.path.isfile(schematic)
        assert os.path.commonpath([ROOT, board]) == ROOT
        assert "/beta/" in board.replace("\\", "/")


def test_hub_baseline_is_deterministic_and_records_physical_identity():
    suite = baseline.load_suite()
    case = next(row for row in suite["cases"]
                if row["id"] == "hub-standard-rev2-current-beta")
    first = baseline.build_baseline(case, grid_mm=1.0, iters=0)
    second = baseline.build_baseline(case, grid_mm=1.0, iters=0)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["revision_policy"] == "current_beta_hierarchical_only"
    assert first["geometry"]["routing_layers"] == [
        "F.Cu", "In2.Cu", "In3.Cu", "B.Cu"]
    assert first["geometry"]["copper_layer_count"] == 6
    assert first["geometry"]["declared_profile"] == \
        "jlcpcb_6l_pofv_signal"
    assert first["geometry"]["footprint_count"] > 0
    assert first["geometry"]["pad_count"] > 0
    assert len(first["geometry"]["fingerprint"]) == 64
    assert first["analysis"]["constraint_ir"]["count"] > 0
    assert len(first["analysis"]["constraint_ir"]["fingerprint"]) == 64
