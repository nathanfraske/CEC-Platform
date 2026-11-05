"""Revalidate a small support move at the route/placement authority boundary.

This is deliberately not an option on the additive checkpoint guard. It owns
a new private artifact family, preserves protected copper/fill and all copper
outside independently proved support-owned incident branches, and runs the
normal complete physical placement gates before updating
the unchanged frozen-power plan's placement snapshot. Final route grading is
still the caller's responsibility. No board names or refdes recipes live here.
"""
import copy
import json
import math
from pathlib import Path
import cec_support_motion as support_motion


def placement_only_failure(proof):
    """An absent/incomplete checkpoint proof cannot enter this transaction."""
    return bool(proof.get('ok') is False
        and proof.get('functional_placement_unchanged') is False
        and proof.get('outline_unchanged') is True
        and proof.get('power_zones_unchanged') is True
        and proof.get('parent_copper', {}).get('ok') is True
        and proof.get('qualified_pairs', {}).get('ok') is True
        and proof.get('power_obligations', {}).get('ok') is True
        and proof.get('score_admission', {}).get('accepted') is True)


def _project_policy(path):
    data = json.loads(Path(path).read_text())
    # KiCad changes this display filename when saving an otherwise identical
    # project under a candidate stem. No other policy field is ignored.
    if isinstance(data.get('meta'), dict):
        data['meta'].pop('filename', None)
    return data


def _population(board):
    """Pose-independent native component/pad identity for a rigid move."""
    result = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref or ref in result:
            raise ValueError('ambiguous footprint identity')
        pads = []
        for pad in fp.Pads():
            at = pad.GetFPRelativePosition()
            size, drill, offset = pad.GetSize(), pad.GetDrillSize(), pad.GetOffset()
            angle = round((pad.GetOrientationDegrees()-fp.GetOrientationDegrees()) % 360, 6)
            pads.append((pad.m_Uuid.AsString(), str(pad.GetNumber()), pad.GetNetname(),
                int(pad.GetAttribute()), int(pad.GetShape()), int(pad.GetDrillShape()),
                size.x, size.y, drill.x, drill.y, offset.x, offset.y, at.x, at.y,
                angle, tuple(pad.GetLayerSet().Seq())))
        result[ref] = (fp.m_Uuid.AsString(), fp.GetFPIDAsString(), fp.GetValue(),
            int(fp.GetAttributes()), bool(fp.IsLocked()), bool(fp.IsFlipped()), tuple(sorted(pads)))
    return result


def endpoint_owner_connectivity(source, candidate, owner_ref):
    """Independently prove benefit and no lost native owner connections.

    No planner target, moved-ref receipt or claimed airwire count is trusted.
    A small IC must gain at least one source-pad connection on its own nets.
    All surviving members of EVERY original owner-pad component must remain
    attached. The separate branch proof still owns any removed/rebuilt copper.
    """
    def items(board):
        result = {}
        for item in [*(p for fp in board.GetFootprints() for p in fp.Pads()),
                     *board.GetTracks()]:
            uid = item.m_Uuid.AsString()
            if not uid or uid in result:
                raise ValueError('ambiguous native owner connectivity identity')
            result[uid] = item
        return result

    owner = source.FindFootprintByReference(owner_ref)
    pads = [p for p in owner.Pads() if p.IsOnCopperLayer()] if owner else []
    report = dict(ok=False, owner_ref=owner_ref, pads=[], release_authority=False)
    if not 3 <= len(pads) <= support_motion.MAX_OWNER_COPPER_PADS:
        return {**report, 'reason': 'outside_small_smd_owner_scope'}
    source.BuildConnectivity()
    candidate.BuildConnectivity()
    old, new = items(source), items(candidate)
    old_conn, new_conn = source.GetConnectivity(), candidate.GetConnectivity()
    pad_ids = {p.m_Uuid.AsString() for fp in source.GetFootprints() for p in fp.Pads()}
    lost, gained = set(), set()
    for pad in pads:
        uid = pad.m_Uuid.AsString()
        if uid not in new or new[uid].GetNetname() != pad.GetNetname():
            return {**report, 'reason': 'moved_pad_identity_lost'}
        if pad.GetNetCode() <= 0:
            continue
        def connected(conn, item):
            return {item.m_Uuid.AsString()} | {
                obj.m_Uuid.AsString() for obj in conn.GetConnectedItems(item)
                if obj.GetNetname() == pad.GetNetname()}
        before, after = connected(old_conn, pad), connected(new_conn, new[uid])
        missing = (before & old.keys() & new.keys()) - after
        added = (after & pad_ids) - before
        lost.update(missing)
        gained.update(added)
        report['pads'].append(dict(pad_uuid=uid, net=pad.GetNetname(),
            missing_native_members=sorted(missing), gained_pad_uuids=sorted(added)))
    if lost:
        return {**report, 'reason': 'owner_original_component_not_restored'}
    if not gained:
        return {**report, 'reason': 'owner_has_no_native_connectivity_gain'}
    return {**report, 'ok': True, 'reason': 'owner_connectivity_improved',
            'gained_pad_uuids': sorted(gained)}


def _native_prepare(source, candidate, output_dir, cfg,
                    max_refs=support_motion.MAX_REFS,
                    max_shift_mm=support_motion.MAX_SHIFT_MM):
    import pcbnew
    import cec_certificate_repair as repair
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    import cec_route_checkpoint as checkpoint
    import cec_local_copper_cell as copper
    import cec_frozen_pour_void as fills

    source, candidate, output_dir = map(lambda p: Path(p).resolve(),
                                       (source, candidate, output_dir))
    support_motion.limits(max_refs=max_refs, max_shift_mm=max_shift_mm)
    if source == candidate or output_dir.exists():
        raise ValueError('placement revalidation requires a new private family')
    output_dir.mkdir(parents=True)
    inputs = pipeline._artifact_rows(p for b in (source, candidate)
        for p in pipeline._placement_authority_family(b) if Path(p).is_file())
    result = dict(schema=1, ok=False, release_authority=False,
                  source_sha256=pipeline.sha256_file(source),
                  proposed_sha256=pipeline.sha256_file(candidate))

    def refuse(reason):
        result['reason'] = reason
        return result

    try:
        proof = checkpoint.preservation(source, candidate, cfg)
        result['additive_checkpoint'] = proof
        if not placement_only_failure(proof):
            return refuse('not_an_isolated_placement_transition')
        if (_project_policy(source.with_suffix('.kicad_pro')) !=
                _project_policy(candidate.with_suffix('.kicad_pro'))
                or source.with_suffix('.kicad_dru').read_bytes() !=
                   candidate.with_suffix('.kicad_dru').read_bytes()):
            return refuse('design_rule_authority_changed')
        first, last = pcbnew.LoadBoard(str(source)), pcbnew.LoadBoard(str(candidate))
        if _population(first) != _population(last):
            return refuse('component_or_pad_definition_changed')
        initial = pipeline._placement_board_snapshot(source)
        final = pipeline._placement_board_snapshot(candidate)
        moved = sorted(ref for ref in initial['placements']
                       if initial['placements'][ref] != final['placements'].get(ref))
        result['moved_refs'] = moved
        if not 1 <= len(moved) <= max_refs:
            return refuse('outside_bounded_support_scope')
        fixed = set(synth._placement_repair_immutable_refs(cfg))
        fixed.update(item.GetReference() for group in first.Groups()
                     for item in group.GetItems() if item.GetClass() == 'FOOTPRINT')
        owner_refs = [ref for ref in moved if len([
            p for p in first.FindFootprintByReference(ref).Pads() if p.IsOnCopperLayer()]) > 2]
        if len(owner_refs) > 1:
            return refuse('multiple_endpoint_owners_outside_scope')
        for ref in moved:
            a, b = first.FindFootprintByReference(ref), last.FindFootprintByReference(ref)
            distance = math.hypot(a.GetPosition().x-b.GetPosition().x,
                                  a.GetPosition().y-b.GetPosition().y)/1e6
            pads = [p for p in a.Pads() if p.IsOnCopperLayer()]
            pad_limit = support_motion.MAX_OWNER_COPPER_PADS if ref in owner_refs else 2
            if (ref in fixed or a.IsLocked() or distance > max_shift_mm
                    or not 2 <= len(pads) <= pad_limit
                    or any(p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in pads)):
                return refuse('immutable_or_out_of_scope_component')
        if owner_refs:
            result['endpoint_owner_connectivity'] = endpoint_owner_connectivity(
                first, last, owner_refs[0])
            if not result['endpoint_owner_connectivity']['ok']:
                return refuse(result['endpoint_owner_connectivity']['reason'])
        before_copper, after_copper = copper.copper_inventory(first), copper.copper_inventory(last)
        changed = sorted(uid for uid, geometry in before_copper.items()
                         if after_copper.get(uid) != geometry)
        result['all_parent_copper'] = dict(ok=not changed, expected=len(before_copper), changed=changed)
        if changed:
            import cec_support_branch_preservation as branches
            result['support_branch_rebuild'] = branches.prove(first, last, moved)
            if not result['support_branch_rebuild']['ok']:
                return refuse('existing_copper_changed')
        result['protected_fill'] = fills.preservation(fills.capture(first), last)
        if not result['protected_fill']['ok']:
            # Attribute a failing fill transition before scheduling more
            # routing. A saved source that loses protected copper under a
            # no-edit refill needs source revalidation, not a larger router.
            # Both proofs remain strict; the control is NOT an allowance.
            control = pcbnew.LoadBoard(str(source))
            _, control_proof = fills.refreshed_control(control)
            result['source_refill_control'] = control_proof
            if not control_proof['ok']:
                result['candidate_against_refill_control'] = fills.preservation(
                    fills.capture(control), last)
                return refuse('source_refill_drift')
            return refuse('protected_power_fill_changed')
        if not pipeline._frozen_placement_contract(source).get('ok'):
            return refuse('source_placement_authority_invalid')
        # The power plan itself cannot be replaced while updating placements.
        states = [json.loads(path.with_suffix('.pourfirst-state.json').read_text())
                  for path in (source, candidate)]
        for state in states:
            state.pop('placements', None)
            skeleton = Path(state.pop('skeleton'))
            state['skeleton_sha256'] = pipeline.sha256_file(skeleton)
        if states[0] != states[1]:
            return refuse('frozen_power_plan_changed')
        target = output_dir/'board.kicad_pcb'
        repair._copy_board_family(str(candidate), str(target))
        sync = pipeline._sync_safe_postfreeze_placement_delta(target)
        result['frozen_state_sync'] = sync
        if not sync.get('ok'):
            return refuse('power_dependent_placement_move')
        bound, binding = synth.config_with_board_route_authority(cfg, str(target))
        result['authority_binding'] = binding
        result['placement_contract'] = pipeline._frozen_placement_contract(target)
        if not binding.get('ok') or not binding.get('bound') or not result['placement_contract'].get('ok'):
            return refuse('refreshed_placement_authority_invalid')
        with synth._oracle_env(bound.params):
            physical = pipeline._measure_placement_physical_in_process(bound, str(target))
        result['physical_placement'] = physical
        if not physical.get('ok'):
            return refuse('full_physical_placement_refused')
        if pipeline.sha256_file(target) != result['proposed_sha256']:
            return refuse('revalidation_mutated_board')
        result.update(ok=True, reason='support_placement_revalidated', board=str(target),
                      authority_transition='revalidated_support_placement')
        return result
    except Exception as exc:
        result['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:1000])
        return refuse('placement_revalidation_error')
    finally:
        result['input_families_unchanged'] = pipeline.artifacts_match(inputs)
        if not result['input_families_unchanged']:
            result.update(ok=False, reason='input_family_changed')
        pipeline.atomic_json(output_dir/'revalidation.json', result)


def prepare(source, candidate, output_dir, cfg, *, timeout_s=90):
    """Bound native revalidation; never modify the caller's input families."""
    import cec_certificate_repair as repair
    return repair._spawn_apply(_native_prepare,
        (str(source), str(candidate), str(output_dir), copy.deepcopy(cfg)), timeout_s=timeout_s)
