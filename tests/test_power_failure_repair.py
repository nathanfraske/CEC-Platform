"""Power-first scheduling uses actual current terminal evidence and exact gates."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import cec_full_pipeline as pipeline
import cec_power_failure as failure
import cec_route_preflight
import cec_synth_pipeline as synth


def certificate(ref="X9", net="rail-A", offset=0):
    return {"ok": False, "planner": {"failure_evidence": {
        "schema": 1, "kind": "power_bridge_feasibility", "net": net,
        "bridge_feasibility": {"refusals": [{"required_vias": 2}]},
        "bottleneck": {"terminals": [{"ref": ref, "pad": "2", "net": net,
                                      "x_mm": 4 + offset, "y_mm": 8}]}}}}


@pytest.mark.parametrize("ref,net,offset", [("X9", "rail-A", 0), ("K7", "/new/rail", 30)])
def test_verified_terminals_are_board_neutral(ref, net, offset):
    evidence = failure.bridge_failure(certificate(ref, net, offset))
    result = failure.terminal_evidence(evidence, {(ref, "2"): {
        "net": net, "x_mm": 4 + offset, "y_mm": 8}})
    assert not result["rejected"]
    assert result["pin_access_blocked"][0]["ref"] == ref


@pytest.mark.parametrize("change", [{"net": "other"}, {"x_mm": 4.5}, {"x_mm": float("nan")}])
def test_stale_or_unproven_terminal_is_not_moved(change):
    current = {"net": "rail-A", "x_mm": 4, "y_mm": 8, **change}
    result = failure.terminal_evidence(failure.bridge_failure(certificate()), {("X9", "2"): current})
    assert not result["pin_access_blocked"] and result["rejected"]


def test_text_and_success_cannot_trigger_repair():
    assert failure.bridge_failure({"ok": False, "error": "bridge cannot fit"}) is None
    row = certificate()
    row["ok"] = True
    assert failure.bridge_failure(row) is None


def test_shared_pin_number_keeps_each_physical_land():
    pads = {("X9", "2"): [{"net": "rail-A", "x_mm": 4, "y_mm": 8},
                           {"net": "rail-A", "x_mm": 14, "y_mm": 8}]}
    result = failure.terminal_evidence(failure.bridge_failure(certificate()), pads)
    assert not result["rejected"] and result["pin_access_blocked"]


def test_failed_field_terminal_is_not_lost_behind_stranded_destination():
    row = failure.bridge_failure(certificate())
    row['bottleneck']['field_terminals'] = [dict(ref='SOURCE', pad='9', net='rail-A', x_mm=2., y_mm=3.)]
    result = failure.terminal_evidence(row, {
        ('SOURCE', '9'): dict(net='rail-A', x_mm=2., y_mm=3.),
        ('X9', '2'): dict(net='rail-A', x_mm=4., y_mm=8.)})
    assert not result['rejected']
    assert [r['ref'] for r in result['pin_access_blocked']] == ['SOURCE', 'X9']
    row['bottleneck']['field_terminals'][0]['x_mm'] = 2.1
    assert failure.terminal_evidence(row, {
        ('SOURCE', '9'): dict(net='rail-A', x_mm=2., y_mm=3.)})['rejected']


def harness(tmp_path, *, authority_ok=True, post_ok=True, trial_key=(0, 2)):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("source")
    cfg = SimpleNamespace(params={"placement_power_replan_candidates": 1})
    ordinary = {"ok": True, "changed": False, "rounds": [{"power_replan_candidates": [
        {"placements": {"X9": [5, 8, 0]}}]}]}
    events = []

    def authority(*a, **kw):
        events.append("power")
        return {"ok": authority_ok}

    def measure(_cfg, path, **kw):
        events.append("baseline_pair" if Path(path) == board else "trial_pair")
        key = [0, 2] if Path(path) == board else list(trial_key)
        # Finalist comparisons now require the complete declared key schema,
        # not the older two-field stand-in used by this fixture.
        key += [0] * (len(cec_route_preflight.PLACEMENT_EVIDENCE_FIELDS) - len(key))
        return {"key": key}

    with ExitStack() as stack:
        patches = [
            patch.object(synth, "placement_candidate_from_board", return_value=SimpleNamespace(P={"X9": (4, 8, 0)})),
            patch.object(synth, "materialize", side_effect=lambda c, cfg, p: Path(p).write_text("trial")),
            patch.object(synth, "_oracle_pads_in_bounds", return_value={"ok": True}),
            patch.object(synth, "_oracle_courtyard_overlaps", return_value={"ok": True}),
            patch.object(synth, "placement_craft_evidence", return_value={}),
            patch.object(pipeline, "_placement_craft_gate", return_value={"ok": True}),
            patch.object(pipeline, "_placement_constraint_gate", return_value={"ok": True}),
            patch.object(pipeline, "_ensure_placement_route_authority", side_effect=authority),
            patch.object(pipeline, "_measure_placement_physical", return_value={key: {"ok": post_ok}
                for key in ("pads_in_bounds", "courtyards", "craft_gate", "constraint_gate")}),
            patch.object(pipeline, "_measure_placement_priority_routes", side_effect=measure),
            patch.object(cec_route_preflight, "placement_evidence_key", side_effect=lambda row: tuple(row["key"])),
        ]
        for item in patches:
            stack.enter_context(item)
        result = pipeline._repair_placement_priority_routes_with_power_replan(
            cfg, board, deepcopy(ordinary), repairing_failed_authority=True)
    return result, events, board.read_text()


@pytest.mark.parametrize("authority_ok,post_ok", [(False, True), (True, False)])
def test_power_or_post_power_geometry_failure_skips_pair_budget(tmp_path, authority_ok, post_ok):
    result, events, contents = harness(tmp_path, authority_ok=authority_ok, post_ok=post_ok)
    assert events == ["power"]
    assert not result["changed"] and contents == "source"


def test_fixed_authority_with_equal_priority_quality_can_progress(tmp_path):
    result, events, contents = harness(tmp_path)
    assert result["changed"] and contents == "trial"
    assert events == ["power", "baseline_pair", "trial_pair"]


def test_power_repair_cannot_regress_priority_quality(tmp_path):
    result, events, contents = harness(tmp_path, trial_key=(0, 3))
    assert not result["changed"] and contents == "source"
    assert events == ["power", "baseline_pair", "trial_pair"]
