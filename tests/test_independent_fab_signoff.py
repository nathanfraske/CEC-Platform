"""Release aggregation must use the complete generic manufacturing contract."""
from contextlib import ExitStack
import json
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_full_pipeline as pipeline


@pytest.mark.parametrize("finding", [
    {"unconnected": 1},
    {"acid_traps": [{"angle_deg": 2.0}]},
    {"complete": False},
    {"artifact_error": "unsupported filled geometry"},
    {"error": "factory report capped"},
    {"drc_total": 1},
    {"slivers": [{}]},
    {"islands": [{}]},
    {"drill_aspect": [{}]},
    {},
])
@pytest.mark.parametrize("contour_ok", [True, False, None])
def test_independent_signoff_does_not_drop_any_fab_blocker(tmp_path, finding, contour_ok):
    oracle = tmp_path / "oracle.json"
    oracle.write_text(json.dumps({"gate": True}))
    fab = {"schema": 2, "complete": True, "drc_total": 0,
           "unconnected": 0, **finding}
    metrics = SimpleNamespace(gates_pass=True, drc=0, drc_types={},
        unconnected=0, kelvin_ok=True, diffpair_ok=True, tracks=1,
        vias=0, length=1.0)
    native = mock.Mock()
    native.GetFootprints.return_value = []
    cfg = SimpleNamespace(sch=tmp_path / "current.kicad_sch",
                          board="arbitrary-family", is_draft=False)
    with ExitStack() as stack:
        overrides = {
            "cec_synth_pipeline._oracle_hints_pours": ({}, {}, {}),
            "cec_score.score": metrics,
            "cec_constraints.release_gate": {"ok": True},
            "pcbnew.LoadBoard": native,
            "cec_hardware_qualification.evaluate": {"ok": True},
            "cec_xfcn_contract.hardware_release_requirements": [],
            "cec_mezz_contract.hardware_release_requirements": [],
            "cec_route_quality.analyze_board": {
                "craft_ok": True, "power_contour_review_ok": contour_ok},
            "cec_fab_profile.active_profile_name": "synthetic-process",
            "cec_fab_profile.stackup_oz": {"F.Cu": 1.0},
            "cec_fab_check.check": fab,
        }
        for target, value in overrides.items():
            stack.enter_context(mock.patch(target, return_value=value))
        import cec_fab_check
        aggregate = stack.enter_context(mock.patch(
            "cec_fab_check.blocking_count", wraps=cec_fab_check.blocking_count))
        result = pipeline._independent_signoff(tmp_path / "board.kicad_pcb", cfg,
                                               oracle, tmp_path / "signoff.json")
    aggregate.assert_called_once_with(fab)
    assert result["fab_blocker_count"] == (1 if finding else 0)
    assert result["terms"]["fabrication"] is (not bool(finding))
    assert result["terms"]["power_contour_review"] is (contour_ok is True)
    assert ("power_contour_review" in result["failed_terms"]) is (contour_ok is not True)
    assert result["ok"] is (not bool(finding) and contour_ok is True)
