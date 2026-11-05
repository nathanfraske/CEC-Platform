"""Atomic additive current-prefix fallback using saved-family repair dispatch.

This adapter never prunes a force net or converts a partial proposal into a
completed current tier. All requested domains share one lease; a final saved
epoch must independently prove every domain and every affected sense leg.
Failure retains the original family. This is routing admission, not release.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
MAX_DOMAINS = 32


def _base(source, requested, capability):
    return dict(schema=1, operation="saved_force_current_prefix", accepted=False,
        candidate_nets=list(requested), requested_nets=list(requested),
        completed_nets=[], incomplete_nets=list(requested), authority_open=[],
        domain_attempts={}, capability=capability, retryable=False,
        current_width=dict(ok=None, detail="not assessed"),
        physical_feasibility="not_assessed", release_authority=False,
        artifact=str(source), source_copper_unchanged=True,
        atomic_requested_domain_admission=False)


def _aggregate_preservation(source, candidate, requested):
    """Every original item is exact; only requested-net segments may be added."""
    import cec_copper_echo as echo
    import cec_force_current as force
    old, fixed = force._preservation_snapshot(source)
    new, after_fixed = force._preservation_snapshot(candidate)
    missing = sorted(set(old)-set(new))
    modified = sorted(uid for uid in old.keys() & new.keys() if old[uid] != new[uid])
    added = sorted(set(new)-set(old))
    _, rows, _ = echo._read(candidate)
    by_id = {row["uuid"].strip('"'): row for row in rows}
    illegal = [uid for uid in added if new[uid][0] != "segment"
        or uid not in by_id or by_id[uid]["net"].strip('"') not in set(requested)]
    old_sidecars, new_sidecars = force._sidecars(source), force._sidecars(candidate)
    sidecars = sorted(ext for ext in set(old_sidecars) | set(new_sidecars)
        if old_sidecars.get(ext) != new_sidecars.get(ext))
    allowed_ground, receiving = [], None
    if modified and not (missing or illegal or fixed != after_fixed or sidecars):
        import cec_additive_route_receiving as additive
        receiving = additive.receive(source, candidate, timeout_s=10.)
        if receiving.get("ok") is True and receiving.get("complete") is True:
            allowed_ground = sorted(row["uuid"] for row in
                receiving["allowed_original_changes"] if row["kind"] == "existing_ground_fill")
    forbidden_modified = sorted(set(modified)-set(allowed_ground))
    return dict(ok=not (missing or forbidden_modified or illegal or fixed != after_fixed or sidecars),
        original_items=len(old), missing_uuids=missing, modified_uuids=modified,
        forbidden_modified_uuids=forbidden_modified,
        allowed_ground_fill_uuids=allowed_ground, ground_refill_receiving=receiving,
        added_uuids=added, illegal_additions=illegal, changed_sidecars=sidecars,
        board_settings_unchanged=fixed == after_fixed,
        scope="exact_original_items_only_additive_requested_current_segments_received_ground_fill")


def _copy_output(source, output, *, expected_board_sha256=None, expected_companions=None):
    """Stage companions first; the saved board is the last commit marker.

    Output is a caller-owned stage artifact, never the incumbent. Refuse stale
    absent companions rather than deleting files in the output directory.
    """
    import cec_force_current as force
    source, output = Path(source).resolve(), Path(output).resolve()
    companions = force._sidecars(source) if expected_companions is None else dict(expected_companions)
    expected_board_sha256 = expected_board_sha256 or force._hash(source)
    if force._hash(source) != expected_board_sha256 or force._sidecars(source) != companions:
        raise ValueError("handoff_source_epoch_changed")
    existing = force._sidecars(output)
    for ext in set(companions) | set(existing):
        src, dst = source.with_suffix(ext), output.with_suffix(ext)
        if not src.is_file() and dst.exists():
            raise ValueError("output_has_unowned_stale_sidecar:"+ext)
    temporary = Path(tempfile.mkdtemp(prefix="prefix-handoff-", dir=output.parent))
    staged = temporary / output.name
    shutil.copy2(source, staged)
    for ext in companions:
        src = source.with_suffix(ext)
        if src.is_file():
            shutil.copy2(src, staged.with_suffix(ext))
    if (force._hash(staged) != expected_board_sha256 or force._sidecars(staged) != companions
            or force._hash(source) != expected_board_sha256 or force._sidecars(source) != companions):
        raise ValueError("staged_handoff_differs_from_frozen_admitted_epoch")
    for ext in companions:
        src = staged.with_suffix(ext)
        if src.is_file():
            os.replace(src, output.with_suffix(ext))
    os.replace(staged, output)
    temporary.rmdir()
    if force._hash(output) != expected_board_sha256 or force._sidecars(output) != companions:
        raise ValueError("output_family_handoff_identity_failed")


def _worker(payload):
    import cec_constraints
    import cec_force_current as force
    import cec_force_sense_evidence as sense
    import cec_operation_budget as budget
    import cec_saved_family_repair as saved
    import cec_score
    import cec_stage_admission

    source, requested = payload["source"], payload["requested"]
    hint = payload["board_hint"]
    report = _base(source, requested, payload["capability"])
    start = time.monotonic()
    before_family, code = force._family(source, hint), force._code_identity()
    current = source
    timeout_s, reserve = payload["timeout_s"], payload["reserve_s"]

    def available(final=False):
        return budget.available_timeout(max(0., timeout_s-(time.monotonic()-start)),
            os.environ, reserve_s=0.)

    try:
        # The nested dispatcher inherits the shortened deadline, not just a
        # funding hint. Returning restores the single aggregate proof reserve.
        with budget.finalization_reserve(reserve) as reservation:
            for net in requested:
                left = available()
                if left < 5.:
                    report.update(reason="force_prefix_shared_budget_deferred", status="deferred_budget")
                    return report
                selected = saved.dispatch(current, payload["ledger_root"],
                    operator="force_current", net=net, board_hint=hint,
                    immutable_nets=payload["immutable_nets"], policy=payload["policy"],
                    options=payload["options"], timeout_s=min(60., timeout_s-reserve),
                    finalization_reserve_s=min(5., reserve))
                report["domain_attempts"][net] = selected
                # Explicit verified selection is the only accepted handoff.
                if (selected.get("status") != "private_selection_ready"
                        or selected.get("accepted") is not True or not selected.get("private_selection")):
                    report.update(reason=selected.get("reason") or "force_dispatch_not_admitted",
                        status=selected.get("status") or "deferred", stopped_net=net,
                        completed_private_nets=list(report["domain_attempts"])[:-1])
                    return report
                handoff = saved.select_private(selected, current, board_hint=hint,
                    immutable_nets=payload["immutable_nets"], policy=payload["policy"])
                if not handoff:
                    raise ValueError("force_dispatch_selection_handoff_refused")
                current = str(handoff)
        report["finalization_budget"] = reservation
        if reservation["budget_exhausted"]:
            report.update(reason="force_prefix_shared_budget_deferred", status="deferred_budget",
                          operation_failure=reservation["operation_failure"])
            return report
        if available(final=True) <= 0.:
            report.update(reason="force_prefix_aggregate_unfunded", status="deferred_budget")
            return report
        # Recheck the aggregate on ONE unchanged saved epoch. Sequential
        # proposal admissions cannot be silently composed into a certificate.
        final_epoch = force._family(current, hint)
        diagnosis = force.diagnose(current, requested, board_hint=hint)
        report["aggregate_force"] = diagnosis
        qualified = sorted(net for net in requested
            if diagnosis.get("domains", {}).get(net, {}).get("qualified") is True)
        report["completed_nets"] = qualified
        report["incomplete_nets"] = sorted(set(requested)-set(qualified))
        report["authority_open"] = sorted(net for net in requested
            if diagnosis.get("domains", {}).get(net, {}).get("native_connectivity", {}).get("connected") is not True)
        preservation = _aggregate_preservation(source, current, requested)
        report["aggregate_preservation"] = preservation
        rules = cec_score.Rules(**payload["rules"]) if payload.get("rules") is not None else None
        admission = cec_stage_admission.evaluate(cec_score.score(source, rules), cec_score.score(current, rules))
        report["admission"] = admission
        report["before"], report["after"] = admission["before"], admission["after"]
        def replay(path):
            left = min(60., available(final=True))
            if left <= 0.:
                raise ValueError("force_prefix_sense_finalization_unfunded")
            return sense.replay(path, board_hint=hint, timeout_s=left)
        old_sense, new_sense = replay(source), replay(current)
        report["aggregate_scoped_kelvin"] = {net: sense.admit_changed_net(old_sense, new_sense, net)
            for net in requested}
        stable = (force._family(source, hint) == before_family and force._code_identity() == code
            and force._family(current, hint) == final_epoch
            and diagnosis.get("source_unchanged") is True and diagnosis.get("code_unchanged") is True
            and new_sense.get("source_family_before") == final_epoch)
        width_ok = all(diagnosis.get("domains", {}).get(net, {}).get("current_width", {}).get("ok") is True
            for net in requested)
        report["current_width"] = dict(ok=width_ok, detail="fresh saved-epoch current-domain replay")
        report["monotonic"] = admission.get("accepted") is True
        accepted = (stable and preservation["ok"] is True and admission.get("accepted") is True
            and not report["incomplete_nets"] and not report["authority_open"] and width_ok
            and all(row.get("ok") is True for row in report["aggregate_scoped_kelvin"].values()))
        report.update(accepted=accepted, reason="admitted_atomic_force_prefix" if accepted else "aggregate_force_prefix_refused",
            status="admitted" if accepted else "deferred", atomic_requested_domain_admission=accepted,
            private_selection=current if accepted else None, candidate_family=final_epoch,
            candidate_sha256=force._hash(current), source_family=before_family, code_identity=code,
            identities_stable=stable, physical_feasibility="bounded_additive_portfolio_not_global")
    except Exception as exc:
        report.update(accepted=False, reason="force_prefix_evidence_failure", status="deferred", error=repr(exc))
    finally:
        report["elapsed_s"] = round(time.monotonic()-start, 6)
    return report


def _accepted_report(report, requested, family, code, candidate_epoch):
    """Receiving boundary checks every strict aggregate term, not an origin label."""
    if (report.get("schema") != 1 or report.get("operation") != "saved_force_current_prefix"
            or report.get("status") != "admitted" or report.get("accepted") is not True
            or report.get("release_authority") is not False
            or report.get("requested_nets") != requested or report.get("candidate_nets") != requested
            or report.get("completed_nets") != requested or report.get("incomplete_nets") != []
            or report.get("authority_open") != [] or report.get("identities_stable") is not True
            or report.get("atomic_requested_domain_admission") is not True
            or report.get("source_family") != family or report.get("code_identity") != code
            or report.get("candidate_family") != candidate_epoch
            or report.get("aggregate_preservation", {}).get("ok") is not True
            or report.get("admission", {}).get("accepted") is not True
            or report.get("monotonic") is not True
            or report.get("current_width", {}).get("ok") is not True):
        return False
    diagnostic = report.get("aggregate_force", {})
    domains = diagnostic.get("domains", {})
    scoped = report.get("aggregate_scoped_kelvin", {})
    if (set(domains) != set(requested) or set(scoped) != set(requested)
            or diagnostic.get("source_unchanged") is not True or diagnostic.get("code_unchanged") is not True
            or diagnostic.get("source_family_before") != candidate_epoch
            or diagnostic.get("source_family_after") != candidate_epoch
            or diagnostic.get("code_before") != code or diagnostic.get("code_after") != code):
        return False
    return all(domains[net].get("qualified") is True
        and domains[net].get("current_width", {}).get("ok") is True
        and domains[net].get("native_connectivity", {}).get("connected") is True
        and domains[net].get("rated_connectivity", {}).get("connected") is True
        and scoped[net].get("ok") is True and scoped[net].get("net") == net
        and scoped[net].get("release_authority") is False
        and scoped[net].get("full_kelvin_qualification") is False for net in requested)


def compile_prefix(source, output, requested_nets, capability, *, rules=None,
                   immutable_nets=(), policy=None, options=None, timeout_s=90.,
                   reserve_s=15., ledger_root=None):
    """Try the atomic fallback, or return None when authority cannot dispatch.

    Both production entry paths call the shared priority-current compiler.
    Unsupported domains stay a causal refusal before any prune/ordinary retry.
    """
    import pcbnew
    import cec_force_current as force
    import cec_operation_budget as budget
    if (not isinstance(requested_nets, (list, tuple, set, frozenset))
            or any(type(net) is not str or not net for net in requested_nets)
            or not isinstance(immutable_nets, (list, tuple, set, frozenset))
            or any(type(net) is not str or not net for net in immutable_nets)
            or type(timeout_s) not in (int, float) or type(reserve_s) not in (int, float)):
        raise ValueError("explicit current and immutable net collections required")
    requested = sorted(set(requested_nets))
    if (not requested or len(requested) > MAX_DOMAINS
            or not all(len(net) <= 256 for net in requested)
            or not all(math.isfinite(float(value)) for value in (timeout_s, reserve_s))
            or not 5. <= float(timeout_s) <= 120. or not 1. <= float(reserve_s) < float(timeout_s)):
        raise ValueError("invalid bounded force prefix policy")
    source, output = str(Path(source).resolve()), Path(output).resolve()
    hint = os.environ.get("CEC_THERMAL_BOARD_HINT") or source
    force._check_output(output, force._protected_paths(source, hint))
    owners = sorted(set(immutable_nets))
    import cec_saved_family_repair as saved
    effective_options = saved._options("force_current", dict(options or {}))
    native = force.force_route_operation_admission(pcbnew.LoadBoard(source), requested,
        board_hint=hint, immutable_nets=owners, authority_path=source,
        include_bypass_terminals=effective_options["include_bypass_terminals"])
    if native.get("eligible") is not True:
        return None
    if rules is not None and not is_dataclass(rules):
        return dict(_base(source, requested, capability), reason="force_prefix_rules_not_serializable")
    output.parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="saved-force-prefix-", dir=output.parent))
    effective_rules = asdict(rules) if rules is not None else None
    payload = dict(source=source, requested=requested, board_hint=hint,
        capability=capability, immutable_nets=owners,
        policy=dict(policy or {}, tier="atomic_current_prefix", requested_nets=requested,
                    effective_score_rules=effective_rules),
        options=effective_options, timeout_s=float(timeout_s), reserve_s=float(reserve_s),
        ledger_root=str(Path(ledger_root or ROOT / "build" / "saved-family-repair-ledger").resolve()),
        rules=effective_rules)
    payload_path, report_path = directory / "payload.json", directory / "report.json"
    budget.write_json(payload_path, payload)
    family, code = force._family(source, hint), force._code_identity()
    report = _base(source, requested, capability)
    try:
        budget.run([sys.executable, str(Path(__file__).resolve()), "--payload", str(payload_path),
            "--report", str(report_path)], directory / "supervisor",
            operation="atomic_force_current_prefix", timeout=float(timeout_s))
        report = json.loads(report_path.read_text())
        if (force._family(source, hint) != family or force._code_identity() != code
                or report.get("requested_nets") != requested):
            raise ValueError("force_prefix_source_code_or_request_drift")
        if report.get("accepted") is True:
            selected = report.get("private_selection")
            if (not selected or not _accepted_report(report, requested, family, code, report.get("candidate_family"))
                    or report.get("candidate_sha256") != force._hash(selected)
                    or report.get("candidate_family") != force._family(selected, hint)
                    or _aggregate_preservation(source, selected, requested).get("ok") is not True):
                raise ValueError("force_prefix_final_selection_unbound")
            frozen_companions = force._sidecars(selected)
            _copy_output(selected, output, expected_board_sha256=report["candidate_sha256"],
                         expected_companions=frozen_companions)
            if (force._family(source, hint) != family or force._code_identity() != code
                    or force._family(selected, hint) != report["candidate_family"]
                    or force._hash(output) != report["candidate_sha256"]
                    or force._sidecars(output) != frozen_companions):
                raise ValueError("force_prefix_post_copy_epoch_drift")
            report.update(artifact=str(output), output_sha256=force._hash(output), source_copper_unchanged=True)
        else:
            _copy_output(source, output)
            report["artifact"] = str(output)
    except Exception as exc:
        failure = dict(getattr(exc, "failure_evidence", None) or {})
        exhausted = failure.get("status") in {"operation_budget_exhausted", "campaign_budget_exhausted"}
        report = dict(_base(source, requested, capability), reason="force_prefix_shared_budget_deferred" if exhausted
            else "force_prefix_supervision_or_handoff_failure", status="deferred_budget" if exhausted else "deferred",
            error=repr(exc), operation_failure=failure)
        # Never touch the incumbent, including when a child dies mid-family.
        report["source_copper_unchanged"] = force._family(source, hint) == family
        if report["source_copper_unchanged"]:
            _copy_output(source, output)
            report["artifact"] = str(output)
    report["evidence_directory"] = str(directory)
    budget.write_json(directory / "handoff.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    import cec_force_current as force
    import cec_operation_budget as budget
    payload = json.loads(Path(args.payload).read_text())
    protected = force._protected_paths(payload["source"], payload["board_hint"])
    destination = Path(args.report).resolve()
    force._check_output(destination, protected)
    force._check_output(destination.with_name(destination.name+".tmp-"+str(os.getpid())), protected)
    budget.arm_diagnostics()
    budget.write_json(destination, _worker(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
