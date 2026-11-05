"""Review checkpoints preserve evaluated geometry without granting admission."""
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_full_pipeline as pipeline


def candidate():
    return SimpleNamespace(strat="synthetic", seed=17, W=20, H=30,
                           P={"X": (1, 2, 90)}, residual=2,
                           journal=[{"pass": "owner", "owned_cells": {"a": ["X"]}}],
                           joint_supply_groups=[{"owner":"DEVICE", "admitted":False,
                                                 "rejection_counts":{"supply_lane":3}}],
                           critical_supply_groups=[{"owner":"DEVICE", "ok":False,
                                "reason":"no_complete_prelock_seat"}],
                           orientation_admission={"ok":False,"rejected":["DEVICE"]},
                           proxy={"hpwl": 50}, route_preflight={"ok": False})


def test_review_keeps_exact_evaluated_bytes_and_failed_evidence(tmp_path):
    source = tmp_path / "evaluated.kicad_pcb"
    source.write_text("exact evaluated geometry")
    destination = tmp_path / "review/board.kicad_pcb"
    result = {"ok": True, "evidence": {"ok": False, "bad": ["unseated"]},
              "pads": {"ok": False}, "courtyards": {"violations": ["overlap"]}}
    with mock.patch.object(pipeline, "_copy_sidecars") as copy, \
         mock.patch("cec_constraints.intake_gate", return_value={"ok": True}):
        def copy_exact(src, dst, **kw):
            dst.parent.mkdir(parents=True)
            dst.write_bytes(Path(src).read_bytes())
            return [str(dst)]
        copy.side_effect = copy_exact
        record = pipeline._retain_placement_candidate(
            source, candidate(), result, SimpleNamespace(sch="current.sch"), destination)
    assert destination.read_bytes() == source.read_bytes()
    assert record["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert record["evaluation"] == result
    assert record["placement_journal"] == candidate().journal
    assert record["joint_supply_groups"] == candidate().joint_supply_groups
    assert record["critical_supply_groups"] == candidate().critical_supply_groups
    assert record["orientation_admission"] == candidate().orientation_admission
    assert not record["routing_admitted"] and not record["release_accepted"]
    assert json.loads(Path(record["report"]).read_text())["evaluation"] == result
    assert json.loads(Path(record["report"]).read_text())["placement_journal"] == candidate().journal
    assert json.loads(Path(record["report"]).read_text())["joint_supply_groups"] == candidate().joint_supply_groups
    assert json.loads(Path(record["report"]).read_text())["critical_supply_groups"] == candidate().critical_supply_groups
    provenance = pipeline._placement_stage_artifact_provenance(destination)
    assert provenance["kind"] == "pipeline_placement_review"
    assert provenance["sha256"] == record["sha256"]
    assert not provenance["routing_admitted"] and not provenance["release_accepted"]


@pytest.mark.parametrize("defect", ["changed_bytes", "different_path", "failed_worker", "failed_source", "admitted", "wrong_role", "missing_digest", "malformed"])
def test_review_resume_refuses_unattested_or_changed_artifacts(tmp_path, defect):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("evaluated authored copper")
    row = {"schema": 1, "role": "initial-placement-review", "board": str(board),
           "sha256": pipeline.sha256_file(board), "evaluation": {"ok": True},
           "source_intake": {"ok": True}, "routing_admitted": False, "release_accepted": False}
    if defect == "changed_bytes": board.write_text("different board")
    if defect == "different_path": row["board"] = str(tmp_path / "other.kicad_pcb")
    if defect == "failed_worker": row["evaluation"]["ok"] = False
    if defect == "failed_source": row["source_intake"]["ok"] = False
    if defect == "admitted": row["routing_admitted"] = True
    if defect == "wrong_role": row["role"] = "route-review"
    if defect == "missing_digest": row.pop("sha256")
    if defect == "malformed": row = []
    board.with_suffix(".placement-review.json").write_text(json.dumps(row))
    assert pipeline._placement_stage_artifact_provenance(board) is None


def test_worker_error_cannot_become_a_review_success(tmp_path):
    with mock.patch.object(pipeline, "_copy_sidecars") as copy:
        with pytest.raises(pipeline.PipelineBlocked, match="native failure"):
            pipeline._retain_placement_candidate(
                tmp_path / "missing", candidate(),
                {"ok": False, "error": "native failure"}, None,
                tmp_path / "out.kicad_pcb")
        copy.assert_not_called()


def test_materialized_source_mismatch_cannot_become_a_review_success(tmp_path):
    with mock.patch.object(pipeline, "_copy_sidecars", return_value=[]), \
         mock.patch("cec_constraints.intake_gate", return_value={
             "ok": False, "reasons": ["DNP flag lost"]}):
        with pytest.raises(pipeline.PipelineBlocked, match="DNP flag lost"):
            pipeline._retain_placement_candidate(
                tmp_path / "source", candidate(), {"ok": True},
                SimpleNamespace(sch="current.sch"), tmp_path / "out.kicad_pcb")


def test_review_requires_explicit_replacement_authority(tmp_path):
    with mock.patch("cec_synth_pipeline.Config.load", return_value=SimpleNamespace()):
        with pytest.raises(ValueError, match="requires replacement"):
            pipeline.run_full_pipeline(board_name="arbitrary", input_board=None,
                                       out_dir=tmp_path, candidate_review_only=True)


def test_review_cli_rejects_route_probe_combination():
    with pytest.raises(SystemExit) as error:
        pipeline.main(["--board", "arbitrary", "--replace-placement",
                       "--placement-candidates-only", "--route-only-probe"])
    assert error.value.code == 2


def test_skipped_review_probes_cannot_disable_production_admission(tmp_path):
    with pytest.raises(SystemExit):
        pipeline.main(["--board", "arbitrary", "--review-skip-route-probes"])
    with mock.patch("cec_synth_pipeline.Config.load", return_value=SimpleNamespace()):
        with pytest.raises(ValueError, match="only for candidate review"):
            pipeline.run_full_pipeline(board_name="arbitrary", input_board=None,
                out_dir=tmp_path, review_skip_route_probes=True)


def test_library_and_blueprint_changes_invalidate_source_digest(tmp_path):
    source = tmp_path / "source.kicad_pcb"
    sch = tmp_path / "root.kicad_sch"
    land = tmp_path / "land.kicad_mod"
    blueprint = tmp_path / "cell.json"
    for path in (source, sch, land, blueprint):
        path.write_text("before")
    cfg = SimpleNamespace(dir=str(tmp_path), sch=str(sch),
                          params={"blueprint_cells": [{"template": str(blueprint)}]})
    with mock.patch("cec_sch_gates.inventory", return_value={
            "ANY_X": {"footprint": "any:land", "on_board": True}}), \
         mock.patch("cec_pcb.fp_path", return_value=str(land)):
        before = pipeline._files_signature(pipeline._source_files(cfg, source))
        land.write_text("changed pad geometry")
        after_land = pipeline._files_signature(pipeline._source_files(cfg, source))
        blueprint.write_text("changed rigid cell")
        after_cell = pipeline._files_signature(pipeline._source_files(cfg, source))
    assert before["sha256"] != after_land["sha256"] != after_cell["sha256"]


def test_missing_library_source_fails_closed(tmp_path):
    sch = tmp_path / "root.kicad_sch"
    cfg = SimpleNamespace(dir=str(tmp_path), sch=str(sch), params={})
    with mock.patch("cec_sch_gates.inventory", return_value={
            "ANY_X": {"footprint": "any:missing"}}), \
         mock.patch("cec_pcb.fp_path", return_value=str(tmp_path / "missing.kicad_mod")):
        with pytest.raises(pipeline.PipelineBlocked, match="footprint source is missing"):
            pipeline._source_files(cfg, sch)


def test_review_cannot_be_overridden_into_detailed_routing_by_environment():
    import cec_synth_pipeline as synth
    with mock.patch.dict(os.environ, {"CEC_ROUTE_ORACLE": "1"}):
        assert not synth._route_oracle_enabled(
            SimpleNamespace(params={"placement_candidates_only": True}))
        assert synth._route_oracle_enabled(SimpleNamespace(params={}))


def test_physically_invalid_candidate_never_starts_route_probe(tmp_path):
    import cec_synth_pipeline as synth
    proposal = candidate()
    proposal.corridor_cross = proposal.corridor_cross_aware = 0
    cfg = SimpleNamespace(params={"placement_preflight_require_physical": True})
    with mock.patch.object(synth, "materialize"), \
         mock.patch.object(synth, "_oracle_pads_in_bounds", return_value={"ok": False}), \
         mock.patch.object(synth, "_oracle_courtyard_overlaps", return_value={"violations": []}), \
         mock.patch.object(synth, "_route_preflight_worker_count", return_value=1), \
         mock.patch.object(synth, "_route_authority_analyze") as analyze:
        ranked = synth.rerank_route_preflight(cfg, [proposal], topk=1)
    analyze.assert_not_called()
    assert ranked[0].route_preflight["error"] == "physical_placement_invalid"
    assert not ranked[0].route_preflight["physical_admission"]["ok"]


def test_infeasible_outline_is_recorded_without_aborting_larger_trials():
    from cec_edge_packing import EdgePackingInfeasible
    engine = SimpleNamespace(place_candidates=mock.Mock(side_effect=[
        EdgePackingInfeasible("no safe bank seat"), [candidate()]]))
    rejected = []
    rows = []
    for height in (20., 30.):
        rows += pipeline._fresh_outline_candidates(engine, None, 20., height,
            strategies=("synthetic",), seeds=(17,), workers=1, rejections=rejected)
    assert len(rows) == 1
    assert rejected[0]["outline_mm"] == [20., 20.]
    assert rejected[0]["stage"] == "edge_bank_packing"
    assert not rejected[0]["routing_admitted"]


@pytest.mark.parametrize("failure", [ValueError("invalid policy"), KeyError("missing part"),
                                     RuntimeError("implementation failure")])
def test_only_typed_geometric_infeasibility_may_be_skipped(failure):
    engine = SimpleNamespace(place_candidates=mock.Mock(side_effect=failure))
    rejected = []
    with pytest.raises(type(failure)):
        pipeline._fresh_outline_candidates(engine, None, 20., 20., strategies=("plain",),
            seeds=(0,), workers=1, rejections=rejected)
    assert rejected == []
