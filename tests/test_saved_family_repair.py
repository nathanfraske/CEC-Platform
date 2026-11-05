"""Saved-family orchestration contracts, with no real board trials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest import mock

import pytest

import cec_force_current as force
import cec_kelvin_branch_repair as branch
import cec_operation_budget as budget
import cec_saved_family_repair as repair


def native_ok():
    return dict(preservation={"ok": True}, whole_board={"accepted": True},
                scoped_kelvin={"ok": True}, rated_current={"qualified": True})


def proposal(request, directory, *, accepted=True, changed=True):
    """Synthetic worker output has the same exact-family receipt contract."""
    directory = Path(directory)
    directory.mkdir()
    source = Path(request["source"])
    candidate = None
    module = force if request["operator"] == "force_current" else branch
    if changed:
        (directory / "candidate").mkdir()
        candidate = directory / "candidate" / source.name
        for item in source.parent.glob(source.stem + ".*"):
            if item.is_file():
                shutil.copy2(item, candidate.with_suffix(str(item)[len(str(source.with_suffix(''))):]))
        candidate.write_text(source.read_text() + "\nprivate addition\n")
    family = module._family(source, request["board_hint"])
    code = force._code_identity()
    report = dict(schema=1, operation=repair.OPERATIONS[request["operator"]], net=request["net"],
        accepted=accepted, changed=changed if accepted else False, connected=True,
        reason=("private_admitted" if changed else "qualified_input_prefix") if accepted else "bounded_no_legal_rated_path",
        release_authority=False, source_unchanged=True, code_unchanged=True,
        source_family_before=family, source_family_after=family, code_before=code, code_after=code,
        candidate=str(candidate) if candidate else None,
        preservation={"ok": True}, whole_board_admission={"accepted": True}, scoped_kelvin={"ok": True},
        exact_refill={"stable": True}, sense_candidate_identity_matches=True,
        current_width={"ok": True}, authority_proof={"connected": True},
        rated_proof={"rated_connectivity": {"connected": True}}, surface_contacts={"ok": True},
        saved_path_screen={"ok": True}, replacement={"synthetic": True},
        environment_unchanged=True, environment_before={}, environment_after={})
    if candidate:
        report.update(candidate_sha256=repair._hash(candidate), candidate_family_unchanged=True,
                      candidate_family_verified=module._family(candidate, request["board_hint"]))
    repair._write_new(directory / "receipt.json", report)
    return report


@pytest.fixture
def context(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith("CEC_"):
            monkeypatch.delenv(key)
    source = tmp_path / "input" / "board.kicad_pcb"
    source.parent.mkdir()
    source.write_text("synthetic immutable source")
    source.with_suffix(".kicad_pro").write_text('{"clearance":0.2}')
    source.with_suffix(".kicad_prl").write_text('{"ui":"retained"}')
    source.with_suffix(".unfamiliar.json").write_text('{"authority":"retained"}')
    epoch = {"engine.py": "a" * 64}
    monkeypatch.setattr(force, "_code_identity", lambda: dict(epoch))
    monkeypatch.setattr(repair, "_toolchain", lambda: {"native": "synthetic-version"})
    monkeypatch.setattr(repair, "_preflight", lambda request: None)
    monkeypatch.setattr(repair, "_native_validate", lambda *_args: native_ok())
    launches = []

    def run(command, directory, *, operation, timeout, env):
        assert operation == "saved-family-repair"
        launches.append(dict(command=command, env=dict(env), timeout=timeout))
        request = repair._read(command[-1])
        repair._worker(request, Path(command[-1]).parent)
        directory.mkdir()
        evidence = dict(operation=operation, status="complete", directory=str(directory), command=command)
        repair._write_new(directory / "operation.json", evidence)
        return evidence

    monkeypatch.setattr(budget, "run", run)
    monkeypatch.setattr(repair, "_operator", proposal)
    kwargs = dict(operator="force_current", net="ARBITRARY_FORCE", board_hint=str(source),
        immutable_nets=["PAIR_A", "PAIR_B"], policy={"profile": "explicit", "pins": {}, "net": None},
        timeout_s=90., finalization_reserve_s=15.)
    return dict(source=source, root=tmp_path / "durable-ledger", kwargs=kwargs,
                launches=launches, epoch=epoch)


def dispatch(context, **extra):
    return repair.dispatch(context["source"], context["root"], **dict(context["kwargs"], **extra))


def select(context, result):
    return repair.select_private(result, context["source"], **{k: context["kwargs"][k]
                                for k in ("board_hint", "immutable_nets", "policy")})


def test_verified_private_family_is_not_canonical_adoption_or_release(context):
    result = dispatch(context, seed=1)
    assert result["accepted"] and result["changed"], result
    assert result["canonical_adoption"] is False and result["release_authority"] is False
    assert result["full_kelvin_qualification"] is False
    path = Path(select(context, result))
    assert path != context["source"] and path.read_text().endswith("private addition\n")
    assert context["source"].read_text() == "synthetic immutable source"
    assert path.with_suffix(".unfamiliar.json").read_bytes() == context["source"].with_suffix(".unfamiliar.json").read_bytes()
    assert result["private_selection"]["transition"] == "additive_force"
    assert len(context["launches"]) == 1


def test_native_topology_tuple_evidence_is_saved_without_relaxing_policy(context, monkeypatch):
    import cec_current_topology as topology
    import cec_fab_profile as fab
    import cec_route_dimensions as dimensions
    import cec_thermal_overlay as overlay
    from test_lastmile import _board

    net = context["kwargs"]["net"]
    board = _board([(5, 5, net), (10, 5, net)])
    monkeypatch.setattr(overlay, "board_thermal_config", lambda *args, **kwargs:
        ({net: 2.0}, None, {net: {"refs_src": ["X1"], "refs_sink": ["X2"]}}, None))
    monkeypatch.setattr(fab, "active_profile_name", lambda *args, **kwargs: "synthetic-profile")
    monkeypatch.setattr(fab, "enabled_copper_layers", lambda *args: ["F.Cu", "B.Cu"])
    monkeypatch.setattr(fab, "referenced_signal_layers", lambda *args, **kwargs: ["F.Cu", "B.Cu"])
    monkeypatch.setattr(topology, "current_contract_for_net", lambda *args, **kwargs:
        dict(amps=2.0, geometry_margin=1.25, margin_included=False))
    monkeypatch.setattr(dimensions, "current_trace_widths", lambda *args, **kwargs:
        {"F.Cu": 1.25, "B.Cu": 1.25})
    # These are the real native topology APIs that produced tuples in VHP B.
    domain = topology.board_current_domains(board, board_hint="synthetic")[net]
    contract = topology.route_width_contracts(board, board_hint="synthetic")[net]
    assert domain["complete"] and domain["source_refs"] == ("X1",)
    assert contract["routing_layers"] == ("F.Cu", "B.Cu")
    native = dict(native_ok(), rated_current=dict(qualified=True, domain=domain, width_contract=contract))
    monkeypatch.setattr(repair, "_native_validate", lambda *_args: native)
    result = dispatch(context)
    assert result["accepted"] and select(context, result), result
    evidence = result["native_admission"]["rated_current"]
    assert evidence["domain"]["source_refs"] == ["X1"]
    assert evidence["domain"]["authority_refs"] == ["X1", "X2"]
    assert evidence["width_contract"]["routing_layers"] == ["F.Cu", "B.Cu"]
    assert evidence["width_contract"]["authority_refs"] == ["X1", "X2"]
    assert native["rated_current"]["domain"]["source_refs"] == ("X1",)
    assert native["rated_current"]["width_contract"]["routing_layers"] == ("F.Cu", "B.Cu")
    saved = repair._read(Path(result["evidence_directory"]) / "validation.json")
    assert saved["native_admission"] == result["native_admission"]


@pytest.mark.parametrize("value", [object(), {1, 2}, {1: "ambiguous key"}, float("nan"), float("inf")])
def test_unsupported_native_evidence_is_not_stringified_or_adopted(context, monkeypatch, value):
    native = dict(native_ok(), extra_native_evidence=value)
    monkeypatch.setattr(repair, "_native_validate", lambda *_args: native)
    result = dispatch(context)
    assert result["status"] == "deferred_evidence" and not result["accepted"]
    assert result["private_selection"] is None and not result["physical_no_path_proof"]
    saved = repair._read(Path(result["evidence_directory"]) / "validation.json")
    assert saved["status"] == "deferred_evidence"


def test_supplied_policy_tuples_remain_invalid_before_acquisition(context):
    with pytest.raises(ValueError, match="explicit JSON"):
        dispatch(context, policy={"unserialized_policy": ("not", "an array")})
    assert not context["root"].exists() and not context["launches"]


@pytest.mark.parametrize("value", [object(), ("tuple",), {1: "ambiguous key"}, float("nan"), float("inf")])
def test_encoding_failure_never_creates_an_empty_immutable_record(tmp_path, value):
    path = tmp_path / "receipt.json"
    with pytest.raises(ValueError):
        repair._write_new(path, {"invalid": value})
    assert not path.exists()
    repair._write_new(path, {"valid": True})
    original = path.read_bytes()
    with pytest.raises(ValueError):
        repair._write_new(path, {"invalid": value})
    assert path.read_bytes() == original
    with pytest.raises(FileExistsError):
        repair._write_new(path, {"valid": "must not overwrite"})
    assert path.read_bytes() == original


def test_cached_admission_rechecks_without_replaying_operator(context, monkeypatch):
    first = dispatch(context, seed=1)
    monkeypatch.setenv("CEC_JOB_DEADLINE_EPOCH", str(time.time()+300))
    monkeypatch.setenv("CEC_OPERATION_OWNER_PID", "123456")
    monkeypatch.setenv("CEC_RUN_DIR", "/tmp/new-operational-run")
    monkeypatch.setenv("CEC_ROUTE_SEED", "999")
    second = dispatch(context, seed=999)
    assert second["accepted"] and second["cached"], second
    assert second["request_id"] == first["request_id"]
    assert second["private_selection"] == first["private_selection"]
    assert select(context, second) == select(context, first)
    assert len(context["launches"]) == 1


def test_sequential_private_domain_selection_uses_same_durable_ledger(context):
    first = dispatch(context)
    original = context["source"]
    context["source"] = Path(select(context, first))
    second = dispatch(context, net="SECOND_ARBITRARY_FORCE")
    assert second["accepted"] and second["changed"], second
    assert second["request_id"] != first["request_id"]
    assert Path(select(context, second)).read_text().count("private addition") == 2
    assert original.read_text() == "synthetic immutable source"
    assert len(context["launches"]) == 2


@pytest.mark.parametrize("tamper", ["candidate", "validation", "supervisor", "result"])
def test_sequential_private_source_requires_prior_verified_selection(context, tamper):
    first = dispatch(context)
    candidate = Path(first["private_selection"]["board"])
    directory = Path(first["evidence_directory"])
    if tamper == "candidate":
        candidate.write_text("changed since prior admission")
    elif tamper == "validation":
        (directory / "validation.json").write_text("{}")
    elif tamper == "supervisor":
        (directory / "supervisor" / "operation.json").write_text("{}")
    else:
        (directory / "result.json").write_text("{}")
    with pytest.raises((ValueError, KeyError)):
        repair.dispatch(candidate, context["root"], **dict(context["kwargs"], net="SECOND_FORCE"))
    assert len(context["launches"]) == 1


def test_unchanged_refusal_is_suppressed_across_seed_deadline_and_staging_path(context, monkeypatch, tmp_path):
    monkeypatch.setattr(repair, "_operator", lambda request, directory: proposal(request, directory, accepted=False))
    first = dispatch(context, seed=0)
    other = tmp_path / "different-stage" / "renamed.kicad_pcb"
    other.parent.mkdir()
    for item in context["source"].parent.iterdir():
        shutil.copy2(item, other.with_suffix(str(item)[len(str(context["source"].with_suffix(''))):]))
    monkeypatch.setenv("CEC_OPERATION_DEADLINE_EPOCH", str(time.time()+500))
    second = repair.dispatch(other, context["root"], **dict(context["kwargs"], board_hint=str(other)), seed=800)
    assert first["reason"] == second["reason"] == "bounded_no_legal_rated_path"
    assert first["request_id"] == second["request_id"] and second["cached"]
    assert second["physical_no_path_proof"] is False
    assert len(context["launches"]) == 1


@pytest.mark.parametrize("change", ["source", "sidecar", "absent", "policy", "options", "code", "environment", "toolchain", "policy_file"])
def test_material_identity_change_funds_a_distinct_request(context, monkeypatch, tmp_path, change):
    monkeypatch.setattr(repair, "_operator", lambda request, directory: proposal(request, directory, accepted=False))
    policy_file = tmp_path / "policy.json"
    context["kwargs"]["policy"]["external"] = str(policy_file)
    first = dispatch(context)
    if change == "source":
        context["source"].write_text("new immutable source")
    elif change == "sidecar":
        context["source"].with_suffix(".kicad_pro").write_text("new policy")
    elif change == "absent":
        context["source"].with_suffix(".kicad_dru").write_text("new declared rule")
    elif change == "policy":
        context["kwargs"]["policy"]["profile"] = "other"
    elif change == "options":
        context["kwargs"]["options"] = {"allow_maze": True}
    elif change == "code":
        context["epoch"]["engine.py"] = "b" * 64
    elif change == "environment":
        monkeypatch.setenv("CEC_PHYSICAL_POLICY", "strict-mode-b")
    elif change == "toolchain":
        monkeypatch.setattr(repair, "_toolchain", lambda: {"native": "synthetic-version-2"})
    else:
        policy_file.write_text("new external authority")
    second = dispatch(context)
    assert first["request_id"] != second["request_id"]
    assert len(context["launches"]) == 2


@pytest.mark.parametrize("field,value", [
    ("accepted", 1), ("changed", 1), ("net", "different"), ("release_authority", True),
    ("source_unchanged", None), ("code_unchanged", 1), ("candidate_sha256", "stale"),
    ("candidate_family_unchanged", None), ("whole_board_admission", {"accepted": 1}),
    ("current_width", {"ok": "yes"}), ("scoped_kelvin", {"ok": False}),
    ("surface_contacts", {}), ("exact_refill", {"stable": False}),
])
def test_receipt_truthiness_missing_proof_and_wrong_identity_never_select(context, monkeypatch, field, value):
    def corrupt(request, directory):
        result = proposal(request, directory)
        result[field] = value
        (Path(directory) / "receipt.json").write_text(json.dumps(result))
        return result
    monkeypatch.setattr(repair, "_operator", corrupt)
    result = dispatch(context)
    assert result["accepted"] is False and result["private_selection"] is None, result
    assert result["status"] == "deferred_evidence"


@pytest.mark.parametrize("change", ["sidecar_dropped", "new_sidecar", "source", "candidate", "receipt", "code"])
def test_mutation_or_mixed_epoch_never_becomes_selection(context, monkeypatch, change):
    def construct(request, directory):
        receipt = proposal(request, directory)
        candidate = Path(receipt["candidate"])
        if change == "sidecar_dropped":
            candidate.with_suffix(".kicad_prl").unlink()
            receipt["candidate_family_verified"] = force._family(candidate, request["board_hint"])
        if change == "new_sidecar":
            candidate.with_suffix(".new.json").write_text("unadmitted")
        (directory / "receipt.json").write_text(json.dumps(receipt))
        return receipt
    def verify(request, candidate, _receipt):
        if change == "source":
            context["source"].write_text("concurrent source change")
        elif change == "candidate":
            Path(candidate).write_text("different child after grading")
        elif change == "receipt":
            Path(candidate).parents[1].joinpath("receipt.json").write_text("different receipt")
        elif change == "code":
            context["epoch"]["engine.py"] = "new code"
        return native_ok()
    monkeypatch.setattr(repair, "_operator", construct)
    monkeypatch.setattr(repair, "_native_validate", verify)
    result = dispatch(context)
    assert not result["accepted"] and result["private_selection"] is None, result


@pytest.mark.parametrize("change", ["candidate", "companion", "receipt", "validation", "result", "source", "policy"])
def test_handoff_and_cached_selection_recheck_evidence(context, change):
    result = dispatch(context)
    assert result["accepted"], result
    directory = Path(result["evidence_directory"])
    candidate = Path(result["private_selection"]["board"])
    if change == "candidate": candidate.write_text("changed")
    elif change == "companion": candidate.with_suffix(".kicad_prl").write_text("changed")
    elif change == "receipt": (directory / "operator" / "receipt.json").write_text("{}")
    elif change == "validation": (directory / "validation.json").write_text("{}")
    elif change == "result":
        result["private_selection"]["family_sha256"] = "forged"
        (directory / "result.json").write_text(json.dumps(result))
    elif change == "source": context["source"].write_text("new source")
    else: context["kwargs"]["policy"]["profile"] = "new policy"
    with pytest.raises(repair.Refusal):
        select(context, result)
    if change not in ("source", "policy"):
        cached = dispatch(context)
        assert not cached["accepted"] and len(context["launches"]) == 1


def test_verified_force_noop_selects_immutable_source(context, monkeypatch):
    monkeypatch.setattr(repair, "_operator", lambda request, directory: proposal(request, directory, changed=False))
    result = dispatch(context)
    assert result["accepted"] and not result["changed"], result
    assert select(context, result) == str(context["source"])


@pytest.mark.parametrize("fault", ["outside", "symlink", "hardlink", "return_differs", "duplicate_receipt", "native_refusal"])
def test_candidate_aliases_and_untrusted_receipts_cannot_be_adopted(context, monkeypatch, fault):
    def corrupt(request, directory):
        receipt = proposal(request, directory)
        candidate = Path(receipt["candidate"])
        if fault == "outside":
            receipt["candidate"] = request["source"]
        elif fault in ("symlink", "hardlink"):
            candidate.unlink()
            if fault == "symlink": candidate.symlink_to(request["source"])
            else: os.link(request["source"], candidate)
        path = directory / "receipt.json"
        path.write_text(json.dumps(receipt))
        if fault == "return_differs": receipt["reason"] = "different return"
        if fault == "duplicate_receipt": path.write_text('{"accepted":false,"accepted":true,"changed":true}')
        return receipt
    monkeypatch.setattr(repair, "_operator", corrupt)
    if fault == "native_refusal":
        monkeypatch.setattr(repair, "_native_validate", lambda *_args: dict(native_ok(), preservation={"ok": False}))
    result = dispatch(context)
    assert not result["accepted"] and result["private_selection"] is None, result


@pytest.mark.parametrize("field,value", [("changed", False), ("status", "physical_no_path"), ("release_authority", True)])
def test_handoff_rejects_mutated_top_level_result(context, field, value):
    result = dispatch(context)
    assert result["accepted"], result
    result[field] = value
    with pytest.raises(repair.Refusal):
        select(context, result)


def test_cached_or_recovered_candidate_requires_completed_supervised_validation(context):
    result = dispatch(context)
    directory = Path(result["evidence_directory"])
    (directory / "supervisor" / "operation.json").write_text('{"status":"worker_failed"}')
    with pytest.raises(repair.Refusal):
        select(context, result)
    refused = dispatch(context)
    assert not refused["accepted"] and len(context["launches"]) == 1


def test_branch_selection_remains_explicitly_nonadditive(context):
    context["kwargs"]["operator"] = "kelvin_branch"
    result = dispatch(context)
    assert result["accepted"], result
    assert result["private_selection"]["transition"] == "typed_branch_replacement"
    assert result["canonical_adoption"] is False


def test_exclusive_request_acquisition_never_dispatches_second_owner(context, monkeypatch):
    run = budget.run
    seen = []
    def concurrent(command, directory, **kwargs):
        seen.append(dispatch(context, seed=2))
        return run(command, directory, **kwargs)
    monkeypatch.setattr(budget, "run", concurrent)
    result = dispatch(context, seed=1)
    assert result["accepted"], result
    assert seen[0]["status"] == "deferred_in_progress"
    assert len(context["launches"]) == 1


def test_operator_and_final_native_validation_share_the_original_lease(context, monkeypatch):
    deadline = time.time() + 80
    monkeypatch.setenv("CEC_OPERATION_DEADLINE_EPOCH", str(deadline))
    seen = []
    def private(request, directory):
        seen.append(("operator", float(os.environ["CEC_OPERATION_DEADLINE_EPOCH"])))
        return proposal(request, directory)
    def native(*_args):
        seen.append(("validation", float(os.environ["CEC_OPERATION_DEADLINE_EPOCH"])))
        return native_ok()
    monkeypatch.setattr(repair, "_operator", private)
    monkeypatch.setattr(repair, "_native_validate", native)
    result = dispatch(context)
    assert result["accepted"], result
    assert seen == [("operator", deadline-15), ("validation", deadline)]
    assert os.environ["CEC_OPERATION_DEADLINE_EPOCH"] == str(deadline)
    assert float(context["launches"][0]["env"]["CEC_OPERATION_DEADLINE_EPOCH"]) == deadline


def test_dependency_deferral_is_durable_and_never_launches_operator(context, monkeypatch):
    monkeypatch.setattr(repair, "_preflight", lambda _request:
        dict(reason="incomplete_affected_sense", affected_legs=[["SENSOR", "p"]]))
    operation = mock.Mock(side_effect=AssertionError("must not construct"))
    monkeypatch.setattr(repair, "_operator", operation)
    first, second = dispatch(context), dispatch(context, seed=22)
    assert first["status"] == "deferred_dependency" and second["cached"]
    assert first["dependency"]["affected_legs"] == [["SENSOR", "p"]]
    operation.assert_not_called()
    assert len(context["launches"]) == 1


def test_file_content_inside_effective_environment_policy_is_bound(context, monkeypatch, tmp_path):
    path = tmp_path / "external.json"
    monkeypatch.setenv("CEC_EFFECTIVE_POLICY", json.dumps({"authority": str(path)}))
    first = dispatch(context)
    path.write_text('{"new":"authority"}')
    second = dispatch(context)
    assert first["request_id"] != second["request_id"]
    assert len(context["launches"]) == 2


def test_dead_owner_requires_explicit_recovery_and_never_reruns_operator(context, monkeypatch):
    original = dispatch(context)
    directory = Path(original["evidence_directory"])
    (directory / "result.json").unlink()  # Simulated coordinator crash after supervised validation.
    monkeypatch.setattr(repair, "_owner_alive", lambda owner: False)
    uncertain = dispatch(context, seed=2)
    assert uncertain["status"] == "deferred_recovery_required"
    recovered = dispatch(context, seed=3, recover=True)
    assert recovered["accepted"] and recovered["recovered"], recovered
    assert select(context, recovered) == original["private_selection"]["board"]
    assert len(context["launches"]) == 1


@pytest.mark.parametrize("missing", ["validation", "supervisor_complete", "request"])
def test_incomplete_dead_attempt_stays_quarantined(context, monkeypatch, missing):
    original = dispatch(context)
    directory = Path(original["evidence_directory"])
    (directory / "result.json").unlink()
    if missing == "validation":
        (directory / "validation.json").unlink()
    elif missing == "supervisor_complete":
        (directory / "supervisor" / "operation.json").write_text('{"status":"running"}')
    else:
        (directory / "request.json").write_text('{"partial":')
    monkeypatch.setattr(repair, "_owner_alive", lambda owner: False)
    first, second = dispatch(context, recover=True), dispatch(context, recover=True)
    assert not first["accepted"] and not second["accepted"]
    assert len(context["launches"]) == 1


def test_pid_reuse_is_not_a_live_owner():
    owner = repair._owner()
    if owner["process_start"] is None:
        pytest.skip("Linux owner start token")
    assert repair._owner_alive(owner)
    owner["process_start"] = "different process incarnation"
    assert repair._owner_alive(owner) is False


@pytest.mark.parametrize("alias", ["source_symlink", "source_hardlink", "root_symlink", "ledger_under_source", "ledger_ancestor"])
def test_output_and_input_aliases_fail_before_launch(context, tmp_path, alias):
    if alias == "source_symlink":
        other = tmp_path / "source-link.kicad_pcb"; other.symlink_to(context["source"])
        context["source"] = other
    elif alias == "source_hardlink": os.link(context["source"], tmp_path / "source-hardlink.kicad_pcb")
    elif alias == "root_symlink":
        target = tmp_path / "real-root"; target.mkdir(); context["root"].symlink_to(target, target_is_directory=True)
    elif alias == "ledger_under_source": context["root"] = context["source"]
    else: context["root"] = tmp_path
    with pytest.raises((ValueError, OSError)):
        dispatch(context)
    assert not context["launches"]


@pytest.mark.parametrize("operator,status", [("force_current", "operation_budget_exhausted"), ("kelvin_branch", "campaign_budget_exhausted"), ("kelvin_branch", "worker_failed")])
def test_operator_stopped_reason_uses_typed_supervisor_cause(context, monkeypatch, operator, status):
    context["kwargs"]["operator"] = operator
    def stopped(request, directory):
        directory.mkdir()
        value = dict(accepted=False, changed=False, reason="branch_worker_stopped",
                     operation_failure={"status": status})
        repair._write_new(directory / "receipt.json", value)
        return value
    monkeypatch.setattr(repair, "_operator", stopped)
    result = dispatch(context)
    assert not result["accepted"]
    assert result["status"] == ("deferred_operator" if status == "worker_failed" else "deferred_budget")
    assert result["physical_no_path_proof"] is False


def test_incomplete_affected_sense_defer_does_not_require_baseline_isolation_pass(monkeypatch):
    import cec_sense_topology as topology
    demand = dict(leg="p", net="FORCE", start={"ref": "SHUNT"}, end={"ref": "FILTER"})
    rest = dict(leg="p", net="FILTERED", start={"ref": "FILTER"}, end={"ref": "SENSOR"})
    monkeypatch.setattr(topology, "placement_segments", lambda row: [demand, rest])
    before = dict(complete=True, identity_stable=True, loaded_board_identity_verified=True,
        lineage=dict(inputs=1, resolved=1, details=[{"ref": "SENSOR", "ok": True}]),
        clipped_isolation={"ok": False},
        same_net_connectivity={"details": [dict(d, input_ref="SENSOR", ok=True) for d in (demand, rest)]})
    assert repair._sense_dependencies(before, {"net": "FORCE"}) is None
    before["same_net_connectivity"]["details"][1]["ok"] = False
    failure = repair._sense_dependencies(before, {"net": "FORCE"})
    assert failure["reason"] == "incomplete_affected_sense"


@pytest.mark.parametrize("prefix", [*repair.PREFIXES, "enclosing"])
def test_branch_prefix_defers_before_any_native_audit(context, monkeypatch, prefix):
    # Use the real preflight function, saved before the fixture's isolation stub.
    context["kwargs"]["operator"] = "kelvin_branch"
    if prefix == "enclosing": monkeypatch.setenv("CEC_POURFIRST_STATE", "/explicit/absent-authority.json")
    else: context["source"].with_suffix(prefix).write_text("{}")
    monkeypatch.setattr(repair, "_preflight", REAL_PREFLIGHT)
    with mock.patch.object(repair, "_replay", side_effect=AssertionError("must not audit")):
        result = dispatch(context)
    assert result["status"] == "deferred_dependency"
    assert result["reason"] == ("enclosing_branch_prefix_unsupported" if prefix == "enclosing" else "saved_branch_prefix_unsupported")


REAL_PREFLIGHT = repair._preflight


SHIM = r'''
import json, os, sys, time
from pathlib import Path
import cec_force_current as force
import cec_saved_family_repair as repair
import cec_operation_budget as budget
force._code_identity = lambda: {'engine.py': 'a'*64}
repair._toolchain = lambda: {'native': 'synthetic-version'}
repair._preflight = lambda request: None
repair._native_validate = lambda *args: dict(preservation={'ok':True}, whole_board={'accepted':True},
    scoped_kelvin={'ok':True}, rated_current={'qualified':True})
def operator(request, directory):
    # The nested private operator uses the actual supervisor, as production does.
    directory.mkdir()
    nested = Path(os.environ['CEC_TEST_NATIVE_SHIM'])
    budget.run([sys.executable, str(nested), str(directory)], directory/'supervisor',
               operation='synthetic-private-operator', timeout=120)
repair._operator = operator
raise SystemExit(repair.main())
'''


@pytest.mark.skipif(os.name != "posix", reason="owned native process-group probe")
def test_real_supervised_lease_kills_descendants_and_never_renews_expired_request(context, monkeypatch, tmp_path):
    # Capture the real supervisor without disturbing the shared imported module.
    real_run = ORIGINAL_RUN
    shim = tmp_path / "entry.py"; shim.write_text(SHIM)
    nested = tmp_path / "native.py"
    descendant = ('import os,signal,sys,time; from pathlib import Path; '
        'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
        'Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)')
    nested.write_text("import subprocess,sys,time\nfrom pathlib import Path\n"
        f"subprocess.Popen([sys.executable,'-c',{descendant!r},str(Path(sys.argv[1])/'native-pid')])\n"
        "time.sleep(30)\n")
    monkeypatch.setattr(repair, "__file__", str(shim))
    monkeypatch.setattr(budget, "run", real_run)
    monkeypatch.setenv("CEC_TEST_NATIVE_SHIM", str(nested))
    # Outer supervisor keeps 15s; private operator keeps another 15s; final
    # reserve is zero in this synthetic probe, leaving about two seconds.
    context["kwargs"]["finalization_reserve_s"] = 0.
    monkeypatch.setenv("CEC_JOB_DEADLINE_EPOCH", str(time.time()+32.))
    started = time.monotonic()
    first = dispatch(context, seed=1)
    assert time.monotonic()-started < 7, first
    assert first["accepted"] is False
    assert first["status"] == "deferred_budget", first
    directory = Path(first["evidence_directory"])
    pid = int((directory / "operator" / "native-pid").read_text())
    state = Path(f"/proc/{pid}/stat")
    assert not state.exists() or state.read_text().split(") ", 1)[1].split()[0] == "Z"
    monkeypatch.setenv("CEC_JOB_DEADLINE_EPOCH", str(time.time()+1000))
    second = dispatch(context, seed=987)
    assert second["cached"] and second["request_id"] == first["request_id"]
    assert first["physical_no_path_proof"] is False


ORIGINAL_RUN = budget.run


def test_expired_parent_does_not_start_any_process(context, monkeypatch):
    monkeypatch.setattr(budget, "run", ORIGINAL_RUN)
    monkeypatch.setenv("CEC_OPERATION_DEADLINE_EPOCH", str(time.time()-1))
    monkeypatch.setenv("CEC_JOB_DEADLINE_EPOCH", str(time.time()+1000))
    with mock.patch.object(budget.subprocess, "Popen") as launch:
        result = dispatch(context)
    launch.assert_not_called()
    assert result["status"] == "deferred_budget" and result["private_selection"] is None


@pytest.mark.parametrize("deadline", ["invalid", "nan", "inf"])
def test_invalid_parent_deadline_is_durable_typed_evidence_refusal(context, monkeypatch, deadline):
    monkeypatch.setenv("CEC_OPERATION_DEADLINE_EPOCH", deadline)
    first = dispatch(context)
    assert first["status"] == "deferred_evidence" and not first["accepted"]
    assert not context["launches"]
    monkeypatch.setenv("CEC_OPERATION_DEADLINE_EPOCH", str(time.time()+600))
    second = dispatch(context, seed=100)
    assert second["request_id"] == first["request_id"] and second["cached"]
    assert not context["launches"]
