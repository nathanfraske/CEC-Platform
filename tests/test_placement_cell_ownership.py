"""A downstream constructor may not dissolve an upstream physical cell."""
import json
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_passes as passes
import cec_synth_pipeline as synth


@pytest.mark.parametrize("action", ["translate", "rotate", "remove", "rewrite_lock"])
def test_cell_drift_names_origin_and_first_offending_stage(action):
    positions = {"AMPLIFIER_X": (12., 8., 0.), "BYPASS_Y": (14., 8., 90.)}
    def break_cell(state):
        if action == "remove":
            positions.pop("BYPASS_Y")
        else:
            positions["BYPASS_Y"] = ((14., 8., 180.) if action == "rotate"
                                      else (15., 8., 90.))
        if action == "rewrite_lock":
            state.locked["BYPASS_Y"] = positions["BYPASS_Y"]
    ladder = passes.PassLadder([
        passes.Pass("stamp", lambda _: None,
                    owned_cells_out={"cell-alpha": tuple(positions)}),
        passes.Pass("seat_followers", break_cell),
        passes.Pass("must_not_run", lambda _: pytest.fail("continued after drift")),
    ], lambda _: positions, enforce_locks=True)
    with pytest.raises(passes.CellOwnershipViolation) as caught:
        ladder.run(ladder)
    error = caught.value
    assert (error.owner_pass, error.pass_name, error.cell, error.ref) == (
        "stamp", "seat_followers", "cell-alpha", "BYPASS_Y")
    assert str(pickle.loads(pickle.dumps(error))) == str(error)
    assert pickle.loads(pickle.dumps(error)).failure_evidence == error.failure_evidence
    event = json.loads(passes.journal_to_json(ladder.journal))[-1]
    assert event["ownership_violation"]["repair_stage"] == "stamp"
    assert event["ownership_violation"]["members"] == ["AMPLIFIER_X", "BYPASS_Y"]


def test_cell_members_are_locked_but_unrelated_follower_remains_movable():
    positions = {"ANCHOR_X": (12., 8., 0.), "CAP_Y": (14., 8., 90.),
                 "FREE_Z": (20., 8., 0.)}
    def follower(state):
        assert set(state.locked) == {"ANCHOR_X", "CAP_Y"}
        positions["CAP_Y"] = (14., 8., 450.)  # same physical pose
        positions["FREE_Z"] = (21., 8., 0.)
    ladder = passes.PassLadder([
        passes.Pass("cell", lambda _: None, owned_cells_out=lambda _: {
            "pair": ["ANCHOR_X", "CAP_Y"]}),
        passes.Pass("free", follower),
    ], lambda _: positions, enforce_locks=True)
    ladder.run(ladder)
    assert positions["FREE_Z"][0] == 21.
    assert ladder.journal[0]["owned_cells"] == {"pair": ["ANCHOR_X", "CAP_Y"]}


def test_missing_cell_member_fails_at_owning_stage():
    ladder = passes.PassLadder([
        passes.Pass("stamp", lambda _: None, owned_cells_out={"pair": ["MISSING"]})
    ], lambda _: {}, enforce_locks=True)
    with pytest.raises(passes.CellOwnershipViolation) as caught:
        ladder.run(ladder)
    assert caught.value.pass_name == "stamp"
    assert caught.value.ref == "MISSING"


def test_ordinary_lock_also_refuses_removed_member():
    positions = {"PART_X": (1., 2., 0.)}
    ladder = passes.PassLadder([
        passes.Pass("seat", lambda _: None, locks_out=["PART_X"]),
        passes.Pass("drop", lambda _: positions.pop("PART_X")),
    ], lambda _: positions, enforce_locks=True)
    with pytest.raises(passes.LockViolation) as caught:
        ladder.run(ladder)
    assert caught.value.moved_to is None


def test_unenforced_ablation_records_ownership_without_changing_behavior():
    positions = {"PART_X": (1., 2., 0.)}
    ladder = passes.PassLadder([
        passes.Pass("seat", lambda _: None, owned_cells_out={"single": ["PART_X"]}),
        passes.Pass("move", lambda _: positions.update(PART_X=(5., 2., 0.))),
    ], lambda _: positions, enforce_locks=False)
    ladder.run(ladder)
    assert positions["PART_X"] == (5., 2., 0.)
    assert ladder.journal[0]["owned_cells"] == {"single": ["PART_X"]}


def test_worker_failure_certificate_survives_canonical_stage_journal(tmp_path):
    import cec_full_pipeline as pipeline
    positions = {"PART_X": (1., 2., 0.)}
    ladder = passes.PassLadder([
        passes.Pass("cell", lambda _: None, owned_cells_out={"pair": ["PART_X"]}),
        passes.Pass("late", lambda _: positions.pop("PART_X")),
    ], lambda _: positions, enforce_locks=True)
    with pytest.raises(passes.CellOwnershipViolation) as caught:
        ladder.run(ladder)
    transported = pickle.loads(pickle.dumps(caught.value))
    def action():
        raise transported
    journal = pipeline.StageJournal(tmp_path / "journal.json", "synthetic")
    with pytest.raises(passes.CellOwnershipViolation):
        journal.run("placement", "digest", action)
    record = json.loads((tmp_path / "journal.json").read_text())["stages"]["placement"]
    assert record["status"] == "failed"
    certificate = record["failure_evidence"]["certificate"]
    assert (certificate["owner_pass"], certificate["offending_pass"],
            certificate["members"]) == ("cell", "late", ["PART_X"])
    assert len(record["failure_evidence"]["placement_journal"]) == 2


def test_actual_blueprint_stage_owns_bypass_capacitor_without_special_case():
    """Exercise the real stage declaration and stamp, not a copied selector."""
    template = {"parts": {}, "internal_tracks": [], "net_roles": {}}
    for ref, offset in (("OWNER_T", [0., 0.]), ("CAP_T", [2., 0.])):
        template["parts"][ref] = {"offset_mm": offset, "rot_delta": 0.,
                                   "flipped": False}
    nl = synth.Netlist(comps={}, nets={})
    class Captured(Exception):
        pass
    def run(ladder, state=None):
        stage = next(p for p in ladder.passes if p.name == "p4b_blueprint_stamp")
        scope = dict(zip(stage.fn.__code__.co_freevars, stage.fn.__closure__))
        scope["anchors"].cell_contents = {}
        scope["comps"].cell_contents = {"AMP_Q": "land", "CAP_Q": "land"}
        scope["anneal_units"].cell_contents = ["AMP_Q", "CAP_Q"]
        stage.fn(ladder)
        assert set(stage.resolve_locks(ladder)) == {"AMP_Q", "CAP_Q"}
        assert stage.resolve_owned_cells(ladder) == {
            "blueprint:0": ["AMP_Q", "CAP_Q"]}
        raise Captured
    with mock.patch.object(synth, "View", return_value=SimpleNamespace(nl=nl)), \
            mock.patch.object(synth, "_bind_declared_interface_anchors"), \
            mock.patch.object(synth, "_device_bypass_specs", return_value={"CAP_Q": {}}), \
            mock.patch.object(passes.PassLadder, "run", run):
        with pytest.raises(Captured):
            synth.synth_one({"board": "synthetic", "params": {"blueprint_cells": [{
                "template": template, "anchor_at": [20., 15.],
                "ideal_internal": False,
                "ref_map": {"OWNER_T": "AMP_Q", "CAP_T": "CAP_Q"}}]}},
                40., 40., "plain", 0)
