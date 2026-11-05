"""Production prefix fallback is atomic across requested current domains."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pcbnew
import pytest

import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_operation_budget as budget
import cec_priority_force_dispatch as prefix
import cec_saved_family_repair as saved
import cec_score
import cec_stage_admission as admission
from test_lastmile import _board


def board_file(path, *, nets=("RENAMED_FEED", "RENAMED_LOAD")):
    board = _board([(5, 5, nets[0]), (15, 5, nets[0]),
                    (5, 10, nets[1]), (15, 10, nets[1])])
    pcbnew.SaveBoard(str(path), board, True)
    return path


def add_segment(path, net, *, via=False):
    board = pcbnew.LoadBoard(str(path))
    if via:
        item = pcbnew.PCB_VIA(board)
        item.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        item.SetWidth(pcbnew.FromMM(.6))
        item.SetDrill(pcbnew.FromMM(.3))
        item.SetViaType(pcbnew.VIATYPE_THROUGH)
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    else:
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(5, 5))
        item.SetEnd(pcbnew.VECTOR2I_MM(15, 5))
        item.SetWidth(pcbnew.FromMM(1.5))
        item.SetLayer(pcbnew.F_Cu)
    item.SetNet(board.FindNet(net))
    board.Add(item)
    pcbnew.SaveBoard(str(path), board, True)


@pytest.mark.parametrize("names", [("RENAMED_FEED", "RENAMED_LOAD"), ("/translated/A", "/translated/B")])
def test_aggregate_only_permits_additive_requested_segments(tmp_path, names):
    source = board_file(tmp_path / "source.kicad_pcb", nets=names)
    candidate = tmp_path / "candidate.kicad_pcb"
    candidate.write_bytes(source.read_bytes())
    add_segment(candidate, names[0])
    proof = prefix._aggregate_preservation(source, candidate, names)
    assert proof["ok"] and len(proof["added_uuids"]) == 1
    assert not prefix._aggregate_preservation(source, candidate, [names[1]])["ok"]
    add_segment(candidate, names[0], via=True)
    proof = prefix._aggregate_preservation(source, candidate, names)
    assert not proof["ok"] and len(proof["illegal_additions"]) == 1


@pytest.mark.parametrize("change", ["pad", "settings", "sidecar", "unknown_sidecar", "remove"])
def test_aggregate_retained_geometry_and_settings_are_exact(tmp_path, change):
    source = board_file(tmp_path / "source.kicad_pcb")
    candidate = tmp_path / "candidate.kicad_pcb"
    candidate.write_bytes(source.read_bytes())
    if change in {"sidecar", "unknown_sidecar"}:
        candidate.with_suffix(".power-prefix.json" if change == "sidecar" else ".unfamiliar.json").write_text('{}')
    else:
        board = pcbnew.LoadBoard(str(candidate))
        footprint = next(iter(board.GetFootprints()))
        if change == "pad":
            next(iter(footprint.Pads())).SetSize(pcbnew.VECTOR2I_MM(1.1, 1.1))
        elif change == "settings":
            board.SetCopperLayerCount(6)
        else:
            board.Remove(footprint)
        pcbnew.SaveBoard(str(candidate), board, True)
    assert not prefix._aggregate_preservation(source, candidate, ["RENAMED_FEED", "RENAMED_LOAD"])["ok"]


def test_output_handoff_carries_complete_family_without_mutating_source(tmp_path):
    source = board_file(tmp_path / "source.kicad_pcb")
    for index, ext in enumerate(force.SIDECARS):
        source.with_suffix(ext).write_text(str(index))
    source.with_suffix(".unfamiliar.json").write_text('opaque native companion')
    output = tmp_path / "output.kicad_pcb"
    before = source.read_bytes()
    prefix._copy_output(source, output)
    assert output.read_bytes() == before == source.read_bytes()
    assert all(source.with_suffix(ext).read_bytes() == output.with_suffix(ext).read_bytes()
               for ext in force._sidecars(source))
    assert not list(tmp_path.glob("prefix-handoff-*"))


def test_output_stale_sidecar_is_not_deleted_or_overwritten(tmp_path):
    source = board_file(tmp_path / "source.kicad_pcb")
    output = tmp_path / "output.kicad_pcb"
    output.with_suffix(".power-prefix.json").write_text("unowned")
    with pytest.raises(ValueError, match="unowned_stale_sidecar"):
        prefix._copy_output(source, output)
    assert output.with_suffix(".power-prefix.json").read_text() == "unowned"
    assert not output.exists()


def setup_worker(tmp_path):
    source = board_file(tmp_path / "source.kicad_pcb")
    candidate = tmp_path / "private.kicad_pcb"
    candidate.write_bytes(source.read_bytes())
    payload = dict(source=str(source), requested=["RENAMED_FEED", "RENAMED_LOAD"],
        board_hint=str(source), capability={"eligible": False}, timeout_s=90., reserve_s=15.,
        ledger_root=str(tmp_path / "ledger"), immutable_nets=[], policy={"intent": "current"},
        options={}, rules=None)
    return source, candidate, payload


class AggregateMocks:
    def __init__(self, candidate):
        self.candidate = str(candidate)
        self.patches = []

    def __enter__(self):
        family = lambda path, _hint=None: {str(Path(path).resolve()): force._hash(path)}
        def diagnosis(path, nets, **kwargs):
            return dict(source_unchanged=True, code_unchanged=True,
                source_family_before=family(path), source_family_after=family(path),
                code_before={"fixed.py": "exact"}, code_after={"fixed.py": "exact"},
                domains={net: dict(qualified=True, native_connectivity={"connected": True},
                    rated_connectivity={"connected": True}, current_width={"ok": True}) for net in nets})
        replay = lambda path, **kwargs: dict(source_family_before=family(path), complete=True,
            identity_stable=True)
        specs = [mock.patch.object(force, "_family", side_effect=family),
            mock.patch.object(force, "_code_identity", return_value={"fixed.py": "exact"}),
            mock.patch.object(force, "diagnose", side_effect=diagnosis),
            mock.patch.object(saved, "dispatch", return_value=dict(status="private_selection_ready",
                accepted=True, private_selection={"board": self.candidate})),
            mock.patch.object(saved, "select_private", return_value=self.candidate),
            mock.patch.object(prefix, "_aggregate_preservation", return_value={"ok": True}),
            mock.patch.object(cec_score, "score", return_value=SimpleNamespace()),
            mock.patch.object(admission, "evaluate", return_value=dict(accepted=True,
                before={"drc": 0, "unconnected": 2}, after={"drc": 0, "unconnected": 0})),
            mock.patch.object(sense, "replay", side_effect=replay),
            mock.patch.object(sense, "admit_changed_net", side_effect=lambda old, new, net: dict(
                ok=True, net=net, release_authority=False, full_kelvin_qualification=False))]
        self.patches = specs
        self.mocks = [spec.start() for spec in specs]
        return self

    def __exit__(self, *args):
        for spec in reversed(self.patches):
            spec.stop()


def test_mixed_prefix_dispatches_every_domain_and_finalizes_one_epoch(tmp_path):
    source, candidate, payload = setup_worker(tmp_path)
    original = source.read_bytes()
    with AggregateMocks(candidate) as ctx:
        result = prefix._worker(payload)
    assert result["accepted"] and result["atomic_requested_domain_admission"]
    assert result["completed_nets"] == payload["requested"]
    assert result["incomplete_nets"] == []
    assert [call.kwargs["net"] for call in ctx.mocks[3].call_args_list] == payload["requested"]
    assert ctx.mocks[2].call_args.args[1] == payload["requested"]
    assert ctx.mocks[9].call_count == 2
    assert result["release_authority"] is False
    assert source.read_bytes() == original


@pytest.mark.parametrize("term", ["domain", "width", "connectivity", "preservation", "whole", "sense", "epoch", "handoff"])
def test_any_aggregate_failure_rejects_entire_prefix(tmp_path, term):
    source, candidate, payload = setup_worker(tmp_path)
    original = source.read_bytes()
    with AggregateMocks(candidate) as ctx:
        if term in {"domain", "width", "connectivity"}:
            fields = {"domain": "qualified", "width": "current_width", "connectivity": "native_connectivity"}
            diagnostic = ctx.mocks[2].side_effect(str(candidate), payload["requested"])
            diagnostic["domains"][payload["requested"][-1]][fields[term]] = (
                None if term == "domain" else {"ok": None} if term == "width" else {"connected": None})
            ctx.mocks[2].side_effect = None
            ctx.mocks[2].return_value = diagnostic
        elif term == "preservation":
            ctx.mocks[5].return_value = {"ok": False}
        elif term == "whole":
            ctx.mocks[7].return_value = dict(accepted=False, before={}, after={})
        elif term == "sense":
            ctx.mocks[9].side_effect = None
            ctx.mocks[9].return_value = {"ok": None}
        elif term == "epoch":
            ctx.mocks[8].side_effect = lambda path, **kwargs: dict(source_family_before={"stale": "epoch"})
        else:
            ctx.mocks[4].side_effect = ValueError("selection_drift")
        result = prefix._worker(payload)
    assert not result["accepted"] and result.get("private_selection") is None
    assert source.read_bytes() == original


def test_causal_defer_never_attempts_later_nets_or_adopts_partial_work(tmp_path):
    source, candidate, payload = setup_worker(tmp_path)
    with AggregateMocks(candidate) as ctx:
        ctx.mocks[3].return_value = dict(status="deferred_dependency", reason="incomplete_affected_sense",
                                       accepted=False, private_selection=None)
        result = prefix._worker(payload)
    assert not result["accepted"] and result["reason"] == "incomplete_affected_sense"
    assert ctx.mocks[3].call_count == 1
    ctx.mocks[4].assert_not_called()
    ctx.mocks[2].assert_not_called()


def test_per_net_effort_identity_does_not_depend_on_remaining_wall_time(tmp_path):
    _, candidate, payload = setup_worker(tmp_path)
    with AggregateMocks(candidate) as ctx, mock.patch.object(budget, "available_timeout", return_value=40.):
        result = prefix._worker(payload)
    assert result["accepted"]
    assert {call.kwargs["timeout_s"] for call in ctx.mocks[3].call_args_list} == {60.}


def test_portfolio_inherits_one_shortened_finalization_lease(tmp_path):
    import os
    import time
    _, candidate, payload = setup_worker(tmp_path)
    deadline = time.time()+90.
    with AggregateMocks(candidate) as ctx, mock.patch.dict(os.environ,
            {"CEC_OPERATION_DEADLINE_EPOCH": str(deadline)}):
        observed = []
        ready = ctx.mocks[3].return_value
        def dispatch(*args, **kwargs):
            observed.append(float(os.environ["CEC_OPERATION_DEADLINE_EPOCH"]))
            return ready
        ctx.mocks[3].side_effect = dispatch
        result = prefix._worker(payload)
        assert float(os.environ["CEC_OPERATION_DEADLINE_EPOCH"]) == deadline
    assert result["accepted"] and observed == [deadline-15., deadline-15.]


def test_copy_cannot_adopt_a_changed_candidate_after_verification(tmp_path):
    source = board_file(tmp_path / "source.kicad_pcb")
    output = tmp_path / "out.kicad_pcb"
    frozen = force._hash(source)
    real_copy = prefix.shutil.copy2
    def change_then_copy(src, dst, *args, **kwargs):
        if Path(src) == source:
            source.write_bytes(source.read_bytes()+b"\n; changed after admission\n")
        return real_copy(src, dst, *args, **kwargs)
    with mock.patch.object(prefix.shutil, "copy2", side_effect=change_then_copy), \
            pytest.raises(ValueError, match="frozen_admitted_epoch"):
        prefix._copy_output(source, output, expected_board_sha256=frozen,
                            expected_companions=force._sidecars(source))
    assert not output.exists()


@pytest.mark.parametrize("term", ["schema", "operation", "admission", "preservation", "scoped", "rated", "inventory", "width"])
def test_receiver_refuses_malformed_positive_aggregate_report(tmp_path, term):
    _, candidate, payload = setup_worker(tmp_path)
    with AggregateMocks(candidate):
        report = prefix._worker(payload)
        family, code = force._family(payload["source"], payload["board_hint"]), force._code_identity()
        assert prefix._accepted_report(report, payload["requested"], family, code, report["candidate_family"])
        if term in {"schema", "operation"}:
            report[term] = "stale"
        elif term == "admission":
            report["admission"]["accepted"] = 1
        elif term == "preservation":
            report["aggregate_preservation"]["ok"] = None
        elif term == "scoped":
            report["aggregate_scoped_kelvin"][payload["requested"][0]]["ok"] = 1
        elif term == "rated":
            report["aggregate_force"]["domains"][payload["requested"][0]]["rated_connectivity"]["connected"] = None
        elif term == "width":
            report["current_width"]["ok"] = "PASS"
        else:
            report["completed_nets"] = payload["requested"][:1]
        assert not prefix._accepted_report(report, payload["requested"], family, code, report["candidate_family"])


def test_effective_score_rules_are_in_durable_request_policy(tmp_path):
    source, _, payload = setup_worker(tmp_path)
    output = tmp_path / "out.kicad_pcb"
    rules = cec_score.Rules()
    def worker(command, directory, **kwargs):
        document = json.loads(Path(command[command.index("--payload")+1]).read_text())
        assert document["policy"]["effective_score_rules"] == document["rules"]
        assert document["rules"] is not None
        report = prefix._base(source, payload["requested"], payload["capability"])
        report.update(reason="intentional_test_refusal", status="deferred_evidence")
        budget.write_json(command[command.index("--report")+1], report)
    with mock.patch.object(force, "force_route_operation_admission", return_value={"eligible": True}), \
            mock.patch.object(budget, "run", side_effect=worker):
        result = prefix.compile_prefix(source, output, payload["requested"], payload["capability"], rules=rules)
    assert not result["accepted"] and result["reason"] == "intentional_test_refusal"


def test_supervisor_failure_restores_full_original_output(tmp_path):
    source, _, payload = setup_worker(tmp_path)
    output = tmp_path / "out.kicad_pcb"
    source.with_suffix(".kicad_dru").write_text("(version 1)\n")
    failure = budget.OperationFailure(dict(operation="atomic_force_current_prefix",
        status="operation_budget_exhausted", directory=str(tmp_path), exit_code=-15))
    with mock.patch.object(force, "force_route_operation_admission", return_value={"eligible": True}), \
            mock.patch.object(budget, "run", side_effect=failure):
        result = prefix.compile_prefix(source, output, payload["requested"], payload["capability"])
    assert result["status"] == "deferred_budget" and not result["accepted"]
    assert source.read_bytes() == output.read_bytes()
    assert source.with_suffix(".kicad_dru").read_bytes() == output.with_suffix(".kicad_dru").read_bytes()


def test_unsupported_authority_never_dispatches_or_scores(tmp_path):
    source, _, payload = setup_worker(tmp_path)
    with mock.patch.object(force, "force_route_operation_admission", return_value={"eligible": False}), \
            mock.patch.object(budget, "run") as run, mock.patch.object(cec_score, "score") as score:
        assert prefix.compile_prefix(source, tmp_path / "out.kicad_pcb", payload["requested"], {}) is None
    run.assert_not_called()
    score.assert_not_called()


def test_output_alias_is_refused_before_worker(tmp_path):
    source, _, payload = setup_worker(tmp_path)
    alias = tmp_path / "alias.kicad_pcb"
    alias.hardlink_to(source)
    with pytest.raises(ValueError, match="protected input"), mock.patch.object(budget, "run") as run:
        prefix.compile_prefix(source, alias, payload["requested"], {})
    run.assert_not_called()


@pytest.mark.parametrize("requested,owners,timeout,reserve", [
    ("FEED", [], 90., 15.), ([None], [], 90., 15.), ([True], [], 90., 15.),
    (["FEED"], "OWNER", 90., 15.), (["FEED"], [None], 90., 15.),
    (["FEED"], [], True, 15.), (["FEED"], [], 90., True),
    (["FEED"], [], float("inf"), 15.), (["FEED"], [], 90., 90.)])
def test_invalid_public_policy_never_dispatches(tmp_path, requested, owners, timeout, reserve):
    source, _, _ = setup_worker(tmp_path)
    with mock.patch.object(budget, "run") as run, pytest.raises(ValueError):
        prefix.compile_prefix(source, tmp_path / "out.kicad_pcb", requested, {},
            immutable_nets=owners, timeout_s=timeout, reserve_s=reserve)
    run.assert_not_called()


def test_worker_cli_report_cannot_overwrite_authority(tmp_path):
    source, _, payload = setup_worker(tmp_path)
    request = tmp_path / "request.json"
    request.write_text(json.dumps(payload))
    before = source.read_bytes()
    with mock.patch.object(prefix, "_worker") as worker, pytest.raises(ValueError, match="protected"):
        prefix.main(["--payload", str(request), "--report", str(source)])
    worker.assert_not_called()
    assert source.read_bytes() == before


def test_production_compiler_calls_dispatch_before_pruning(tmp_path):
    import cec_fr
    import cec_synth_pipeline as synth
    source, _, payload = setup_worker(tmp_path)
    result = dict(accepted=False, reason="incomplete_affected_sense", retryable=False)
    with mock.patch.object(cec_fr, "_board_kelvin_pairs", return_value=[tuple(payload["requested"])]), \
            mock.patch.object(prefix, "compile_prefix", return_value=result) as dispatch, \
            mock.patch.object(synth, "_prune_priority_current_artifact_isolated") as prune, \
            mock.patch.object(synth, "_route_priority_current_domain_isolated") as route:
        assert synth._compile_priority_current_prefix(str(source), payload["requested"], {},
            str(tmp_path / "out.kicad_pcb"), immutable_nets=("AUTHORED_OWNER",)) == result
    assert dispatch.call_args.kwargs["immutable_nets"] == ("AUTHORED_OWNER",)
    assert dispatch.call_args.args[2] == tuple(payload["requested"])
    prune.assert_not_called()
    route.assert_not_called()
