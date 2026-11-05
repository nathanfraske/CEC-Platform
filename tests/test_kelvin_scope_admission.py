"""Absolute affected-leg admission; no unchanged-fault-set escape hatch."""
import copy
from unittest.mock import patch

import pytest

import cec_force_sense_evidence as evidence
from test_force_sense_evidence import fixture


def receipts(tmp_path):
    path = tmp_path/"source.kicad_pcb"
    domains = fixture(path, overlap_at_cut=True)
    with patch("cec_current_topology.board_current_domains", return_value=domains):
        before = evidence.replay(path, board_hint="declared-fixture")
    return before, copy.deepcopy(before)


def test_absolute_affected_leg_proof_is_not_whole_board_release(tmp_path):
    before, after = receipts(tmp_path)
    result = evidence.admit_changed_net(before, after, "RENAMED_FEED")
    assert result["ok"] and result["checked"] == 1, result
    assert result["expected_legs"] == [["ANALOG_SENSOR", "p"]]
    assert not result["full_kelvin_qualification"] and not result["release_authority"]
    # The intermediate/input net on that same filtered leg receives the same
    # force-side isolation check, not an empty 'no affected force net' waiver.
    assert evidence.admit_changed_net(before, after, "FILTERED_POS")["checked"] == 1


@pytest.mark.parametrize("mutation", ["identity", "incomplete", "unresolved", "removed_input",
    "missing_demand", "duplicate_demand", "open_demand", "missing_cut", "duplicate_cut",
    "cut_unknown", "cut_failed", "not_clipped", "cut_incomplete", "changed_authority",
    "wrong_departure", "missing_departure", "missing_linear_epoch", "stale_linear_epoch"])
def test_missing_or_failed_evidence_never_promotes(tmp_path, mutation):
    before, after = receipts(tmp_path)
    clip = after["clipped_isolation"]["details"][0]
    if mutation == "identity": after["identity_stable"] = False
    elif mutation == "incomplete": after["complete"] = False
    elif mutation == "unresolved": after["lineage"]["resolved"] = 0
    elif mutation == "removed_input": after["lineage"].update(inputs=0, resolved=0, details=[])
    elif mutation == "missing_demand": after["same_net_connectivity"]["details"].pop(0)
    elif mutation == "duplicate_demand": after["same_net_connectivity"]["details"].append(after["same_net_connectivity"]["details"][0])
    elif mutation == "open_demand": after["same_net_connectivity"]["details"][0]["ok"] = False
    elif mutation == "missing_cut": after["clipped_isolation"]["details"].pop(0)
    elif mutation == "duplicate_cut": after["clipped_isolation"]["details"].append(clip)
    elif mutation == "cut_unknown": clip["ok"] = clip["native"]["ok"] = None
    elif mutation == "cut_failed": clip["ok"] = clip["native"]["ok"] = False
    elif mutation == "not_clipped": clip["native"]["tracks_clipped"] = False
    elif mutation == "cut_incomplete": clip["native"]["complete"] = False
    elif mutation == "missing_linear_epoch": clip["native"].pop("exact_linear_identity_verified", None)
    elif mutation == "stale_linear_epoch": clip["native"]["exact_linear_identity_verified"] = False
    elif mutation == "changed_authority": clip["native"]["authority"][0]["position_nm"][0] += 1
    elif mutation == "wrong_departure": after["inner_departure"]["details"][0]["ok"] = False
    elif mutation == "missing_departure": after["inner_departure"]["details"].pop(0)
    assert not evidence.admit_changed_net(before, after, "RENAMED_FEED")["ok"]


def test_already_failed_same_connector_set_does_not_waive_absolute_check(tmp_path):
    before, after = receipts(tmp_path)
    for report in (before, after):
        row = report["clipped_isolation"]["details"][0]
        row["ok"] = row["native"]["ok"] = False
    assert not evidence.admit_changed_net(before, after, "RENAMED_FEED")["ok"]


def test_preexisting_force_open_does_not_forbid_a_valid_repair(tmp_path):
    before, after = receipts(tmp_path)
    old = before["clipped_isolation"]["details"][0]
    old["ok"] = old["native"]["ok"] = None
    old["native"]["complete"] = False
    old["native"]["reason"] = "baseline_native_terminal_connectivity_incomplete"
    assert evidence.admit_changed_net(before, after, "RENAMED_FEED")["ok"]


def test_positive_proof_from_other_leg_cannot_be_substituted_consistently(tmp_path):
    before, after = receipts(tmp_path)
    for report in (before, after):
        entries = report["clipped_isolation"]["details"]
        entries[0]["native"] = copy.deepcopy(entries[1]["native"])
    result = evidence.admit_changed_net(before, after, "RENAMED_FEED")
    assert not result["ok"]
    assert "clipped_proof_does_not_match_typed_physical_leg" in result["reasons"]


@pytest.mark.parametrize("field", ["sense", "source", "authority"])
def test_same_net_physical_identity_substitution_is_refused(tmp_path, field):
    before, after = receipts(tmp_path)
    for report in (before, after):
        native = report["clipped_isolation"]["details"][0]["native"]
        target = native[field][0] if field == "authority" else native[field]
        target["uuid"] = "not-the-declared-physical-terminal"
    assert not evidence.admit_changed_net(before, after, "RENAMED_FEED")["ok"]
