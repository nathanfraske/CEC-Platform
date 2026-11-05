"""Bounded replacement of an owned signal pair blocking a placement trial.

Power copper is never released. A trial owes the entire affected pair topology
and must rebuild/requalify it before promotion; a relaxed collision screen or
a successful read-only routing probe is not sufficient.
"""
from __future__ import annotations

import copy
import math
import os
from pathlib import Path


def operation_budget(params, *, env=None):
    """Account for the added pair-reconstruction work inside power repair.

    The legacy 240-second budget funded power placement alone. Each enabled
    dependency trial may now also run complete pair solves and certification.
    This is an upper scheduling allowance, not geometric admission; enclosing
    deadlines still clamp it and an explicit operator limit always wins.
    """
    env = os.environ if env is None else env
    base = float(params.get("power_terminal_search_budget_s", 240))
    pair_s = float(env.get("CEC_PRECISION_PAIR_TIMEOUT", "240"))
    if not math.isfinite(pair_s) or pair_s < 0:
        raise ValueError("invalid priority dependency pair budget")
    pair_s = max(5.0, pair_s)
    proof_s = float(params.get("priority_dependency_proof_reserve_s", 30))
    trials = max(0, int(params.get("priority_dependency_trials", 2)))
    pairs = max(0, int(params.get("priority_dependency_max_pairs", 1)))
    explicit = params.get("power_terminal_repair_timeout_s")
    requested = float(explicit) if explicit is not None else base + trials * (pairs * pair_s + (proof_s if pairs else 0))
    if any(not math.isfinite(v) or v < 0 for v in (base, pair_s, proof_s, requested)):
        raise ValueError("invalid priority dependency operation budget")
    return {"requested_s": requested, "explicit_limit": explicit is not None,
            "power_search_s": base, "dependency_trials": trials,
            "pairs_per_trial": pairs, "per_pair_s": pair_s,
            "proof_reserve_per_trial_s": proof_s}


def release_plan(contract, conflict, *, max_pairs=1):
    """Select the atomic qualified-pair closure of typed native collisions."""
    refused = {"schema": 1, "ok": False, "reason": "unproven_pair_dependency"}
    if ("placement_power_nets" not in contract or conflict.get("ok") is not False
            or max_pairs <= 0):
        return refused
    rows = []
    for row in conflict.get('violations') or ():
        if row.get('kind') == 'frozen_anchor_moved':
            # A reference alone cannot distinguish power from replaceable
            # signal ownership. Legacy/incomplete anchor reports stay blocked.
            attachments = row.get('attachments') or []
            if row.get('attachments_complete') is not True or not attachments:
                return refused
            if any(not item.get('pad') for item in attachments):
                return refused
            rows.extend(dict(item, kind='fixed_copper_pad_collision') for item in attachments)
        else:
            rows.append(row)
    if not rows or any(row.get("kind") != "fixed_copper_pad_collision"
                       or not row.get("copper_net") or not row.get("copper_uuid")
                       for row in rows):
        return refused
    return pair_scope_plan(contract, {row['copper_net'] for row in rows},
                           {row['copper_uuid'] for row in rows}, max_pairs=max_pairs)


def pair_scope_plan(contract, collisions, blocking_uuids, *, max_pairs=1):
    """Shared ownership closure, not a geometry witness or release permission.

    Both placement collisions and native pin-access conflicts owe this same
    complete qualified signal-pair scope. Callers must reproduce their own
    typed native conflict and pay every reconstruction/admission obligation.
    """
    refused = {"schema": 1, "ok": False, "reason": "unproven_pair_dependency"}
    if ('placement_power_nets' not in contract or not collisions
            or type(max_pairs) is not int or not 1 <= max_pairs <= 8):
        return refused
    pairs = [copy.deepcopy(pair) for pair in contract.get("qualified_critical_pairs", [])
             if pair.get("qualified") and pair.get("name") and pair.get("p") and pair.get("n")]
    collisions = set(collisions)
    power = set(contract["placement_power_nets"])
    qualified = {pair[key] for pair in pairs for key in ("p", "n")}
    if collisions - qualified or collisions & power:
        return {**refused, "reason": "collision_includes_nonreplaceable_copper"}
    selected, nets = [], set(collisions)
    while True:
        closure = [pair for pair in pairs if {pair["p"], pair["n"]} & nets]
        expanded = nets | {pair[key] for pair in closure for key in ("p", "n")}
        selected = closure
        if expanded == nets:
            break
        nets = expanded
    if nets & power or len(selected) > int(max_pairs):
        return {**refused, "reason": "atomic_pair_closure_exceeds_policy"}
    members = contract.get("members") or {}
    member_nets = contract.get("member_nets") or {}
    if (set(members) - set(member_nets) or
            not nets <= set(contract.get("placement_preserved_nets") or ()) or
            not nets <= set(member_nets.values())):
        return {**refused, "reason": "prefix_identity_incomplete"}
    retained = copy.deepcopy(contract)
    retained["members"] = {uid: count for uid, count in members.items()
                           if member_nets[uid] not in nets}
    retained["member_nets"] = {uid: member_nets[uid] for uid in retained["members"]}
    retained["items"] = sum(retained["members"].values())
    retained["nets"] = sorted(set(contract.get("nets") or ()) - nets)
    retained["placement_preserved_nets"] = sorted(
        set(contract.get("placement_preserved_nets") or ()) - nets)
    retained["items_by_net"] = {net: count for net, count in
                                 (contract.get("items_by_net") or {}).items() if net not in nets}
    retained["qualified_critical_pairs"] = [pair for pair in pairs
                                            if not {pair["p"], pair["n"]} & nets]
    return {"schema": 1, "ok": True, "reason": "atomic_signal_pair_replacement",
            "nets": sorted(nets), "pairs": selected,
            "blocking_uuids": sorted(set(blocking_uuids)),
            "retained_contract": retained, "replacement_required": True}


def placement_handoff(contract, conflict, move, *, max_pairs=1):
    """Offer, never admit, a native-witnessed owned-pair replacement trial."""
    plan = release_plan(contract, conflict, max_pairs=max_pairs)
    if not plan['ok']:
        return None
    placements = move.get('placements') or {move['ref']: move['position']}
    return dict(kind=move.get('kind'), source_kind=move.get('source_kind'),
        ref=move.get('ref'), refs=sorted(placements), placements=copy.deepcopy(placements),
        priority_dependency_replacement=True,
        dependency_offer=dict(nets=plan['nets'], pairs=plan['pairs'],
                              blocking_uuids=plan['blocking_uuids']),
        proposal={key:move[key] for key in ('dx_mm','dy_mm','distance_mm') if key in move})


def handoff_candidates(report, limit):
    """Share the unchanged bounded handoff across dependency classes fairly."""
    import json
    from itertools import zip_longest
    classes = [[], []]
    for row in report.get('rounds') or ():
        classes[0].extend(row.get('priority_dependency_candidates') or ())
        classes[1].extend(row.get('power_replan_candidates') or ())
    result, seen = [], set()
    for offered in zip_longest(*classes):
        for row in offered:
            if row is None or not row.get('placements'):
                continue
            signature = json.dumps(row['placements'], sort_keys=True, separators=(',',':'))
            if signature in seen:
                continue
            seen.add(signature)
            result.append(dict(row))
    return result[:max(0, int(limit))]


def screen_placement_handoff(board, contract, conflict, move, *, max_pairs=1,
                              back_refs=None, contexts=None):
    """Before spending a trial, check the target against everything retained.

    The initial anchor refusal intentionally stops at the attached conductor.
    Releasing that signal obligation can reveal a different power/return
    collision. Only a private context is relaxed; the source and normal
    placement gate remain untouched, and reconstruction is still mandatory.
    """
    import cec_frozen_copper
    import cec_placement_route_prefix as prefix
    plan = release_plan(contract, conflict, max_pairs=max_pairs)
    if not plan['ok']:
        return dict(ok=False, reason=plan['reason'])
    contexts = {} if contexts is None else contexts
    retained = plan['retained_contract']
    nets, uuids = tuple(sorted(prefix.preserved_nets(retained))), tuple(sorted(prefix.preserved_uuids(retained)))
    signature = (str(board), nets, uuids)
    if signature not in contexts:
        contexts[signature] = cec_frozen_copper.FrozenCopperContext(board,nets,item_uuids=uuids)
    placements = move.get('placements') or {move['ref']:move['position']}
    residual = contexts[signature].check(placements,back_refs=back_refs)
    if not residual['ok']:
        return dict(ok=False,reason='replacement_target_conflicts_with_retained_copper',
                    residual=residual, released_nets=plan['nets'])
    return dict(ok=True,reason='screened_owned_pair_replacement_offer',
        handoff=placement_handoff(contract,conflict,move,max_pairs=max_pairs))


def placement_support_predicate(board, contract, *, back_refs=(), max_pairs=1):
    """Necessary native retained-copper screen for bounded proposal producers.

    This only decides whether a proposal deserves a beam slot. It grants no
    move/release authority and returns no relaxed contract. The normal handoff
    must reproduce ownership and reconstruct every released pair afterward.
    """
    import cec_frozen_copper
    import cec_placement_route_prefix as prefix
    context=cec_frozen_copper.FrozenCopperContext(board,prefix.preserved_nets(contract),
        item_uuids=prefix.preserved_uuids(contract))
    contexts={}

    def supported(placements):
        conflict=context.check(placements,back_refs=back_refs)
        if conflict['ok']:
            return True
        result=screen_placement_handoff(board,contract,conflict,
            dict(placements=placements),back_refs=back_refs,max_pairs=max_pairs,
            contexts=contexts)
        return result['ok'] is True

    return supported


def rebuilt_admitted(report):
    """All independent obligations must be paid before trial promotion."""
    return bool(report.get("constructed") and report.get("retained_prefix", {}).get("ok")
                and report.get("all_original_pairs", {}).get("ok")
                and report.get("placement_unchanged") and report.get("authority", {}).get("ok")
                and report.get("physical_ok"))


def construct_released_pairs(cfg, source, out, selected):
    """Use the declared power-authority mode, not an invented sidecar duty.

    Native locked-bus designs still owe exact copper-prefix and physical
    proofs. A board requiring compiled power reservations additionally owes
    the bound state; its missing/invalid state must never fall back to native.
    """
    import cec_full_pipeline as pipeline
    import cec_critical_checkpoint as checkpoint
    import cec_synth_pipeline as synth
    frozen_cfg = cfg if pipeline._requires_frozen_route_authority(cfg) else None
    with synth._oracle_env(cfg.params):
        return checkpoint.construct(source,out,selected,frozen_route_config=frozen_cfg)


def rebuild(cfg, board, plan, original_contract, out, *, allow_authored_prefix):
    """Rebuild released topology with the existing native constructive solver."""
    import cec_fr
    import cec_full_pipeline as pipeline
    import cec_precision_route as precision
    import cec_placement_route_prefix as prefix
    import cec_critical_checkpoint as checkpoint
    import cec_operation_budget as budget
    import shutil
    board = Path(board).resolve()
    original_pose = pipeline._placement_position_signature(board)
    derived = precision.derive_coupled_pairs(str(board))
    expected = {(row["name"], row["p"], row["n"]) for row in plan["pairs"]}
    selected = [pair for pair in derived if (pair["name"], pair["p"], pair["n"]) in expected]
    report = {"schema": 1, "ok": False, "constructed": False,
              "released_nets": plan["nets"], "replacement_required": True}
    if {(row["name"], row["p"], row["n"]) for row in selected} != expected:
        return {**report, "reason": "released_pair_declaration_changed"}
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(out.parent).free < 16 * 1024 ** 3:
        return {**report, "reason": "dependency_diagnostic_storage_floor"}
    # Preserve the exact post-power starting state and all authority sidecars.
    # The enclosing placement scratch directory disappears on ordinary return;
    # a failed pair must remain reproducible as well as a timeout. The caller
    # bounds these directories by its dependency-trial allowance.
    source = out.parent / (out.name + '-input') / board.name
    report['construction_input'] = pipeline._publish_placement_authority_payload(
        source, pipeline._capture_placement_authority_payload(board))
    budget.progress("priority_dependency_reconstruction", pairs=len(selected), board=str(board))
    construction = construct_released_pairs(cfg, source, out, selected)
    report["construction"] = construction
    if not construction.get("ok") or not construction.get("selected"):
        return {**report, "reason": "released_pair_reconstruction_failed"}
    candidate = Path(construction["selected"])
    budget.progress("priority_dependency_prefix_proof", board=str(candidate))
    report.update(constructed=True,
        retained_prefix=cec_fr.check_copper_geometry_prefix(str(candidate), plan["retained_contract"]),
        all_original_pairs=prefix.check_qualified_pairs(str(candidate), original_contract),
        placement_unchanged=original_pose == pipeline._placement_position_signature(candidate))
    if not (report["retained_prefix"]["ok"] and report["all_original_pairs"]["ok"]
            and report["placement_unchanged"]):
        return {**report, "reason": "replacement_prefix_or_pair_proof_failed"}
    # Bind the exact reconstructed artifact, not the pre-pair placement. This
    # remains inside the scratch transaction; no source board is promoted here.
    payload = pipeline._capture_placement_authority_payload(candidate)
    pipeline._publish_placement_authority_payload(board, payload)
    budget.progress("priority_dependency_authority_rebind", board=str(board))
    report["authority"] = pipeline._ensure_placement_route_authority(
        cfg, board, allow_authored_prefix=allow_authored_prefix)
    physical = pipeline._measure_placement_physical(cfg, board)
    report["physical_ok"] = all((physical.get(term) or {}).get("ok") for term in
                                 ("pads_in_bounds", "courtyards", "craft_gate", "constraint_gate"))
    # Power authority compilation can itself change the board. Reprove the
    # actual final trial, never a superseded constructor output.
    report["retained_prefix"] = cec_fr.check_copper_geometry_prefix(str(board), plan["retained_contract"])
    report["all_original_pairs"] = prefix.check_qualified_pairs(str(board), original_contract)
    report["placement_unchanged"] = original_pose == pipeline._placement_position_signature(board)
    report["ok"] = rebuilt_admitted(report)
    report["reason"] = "pair_dependency_rebuilt" if report["ok"] else "post_authority_reproof_failed"
    return report
