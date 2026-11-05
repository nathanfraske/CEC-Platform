"""Qualify pin-local PI/Kelvin and exact power before long paired routes.

The local cells are supplied by the existing transactional PI stage. This
boundary never moves placements or replaces source files. It reconciles power
around local Kelvin taps and verifies their coexistence on the saved artifact;
only then may a caller protect that power while routing longer signal pairs.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import time


def eligible(*, power_enabled, local_pi, policy, enabled=True):
    return bool(enabled and power_enabled and policy == 'critical-first'
                and local_pi and local_pi.get('ok')
                and not local_pi.get('rolled_back'))


def admitted(report):
    """Every independent term is required; missing evidence is not a pass."""
    return bool(report.get('source_unchanged') and report.get('placement_unchanged')
        and report.get('parent_copper', {}).get('ok')
        and report.get('power', {}).get('exact_admission', {}).get('passed')
        and report.get('power_obligations', {}).get('ok')
        and report.get('ground', {}).get('ok')
        and report.get('local_pi_final', {}).get('ok')
        and report.get('kelvin_final', {}).get('ok')
        and report.get('qualified_pairs', {}).get('ok')
        and report.get('score_admission', {}).get('accepted')
        and not report.get('error'))


def prospective_recovery_allowed(board, state):
    """Only an unbuilt plan may be renegotiated behind admitted copper.

    Existing managed power zones are physical priority authority, not a
    placement-time hint. Do not notch or reroute them in this recovery path.
    Native tracks/vias, including local power, are preserved independently by
    the full parent-copper contract after a proposal is generated.
    """
    nets = set(state.get('frozen_nets') or ())
    return bool(state.get('placement_scope') == 'complete' and nets
        and state.get('pours') and state.get('corridors')
        and not any(z.GetNetname() in nets and not z.GetIsRuleArea()
                    for z in board.Zones()))


def recover_power_in_process(source, pours, out):
    """Bounded caller-owned recovery: reconcile once, then replan once.

    This runs in a supervised native worker. No source or parent copper is
    mutated; every returned board is still only a proposal for the complete
    local-power barrier's independent saved-artifact admission.
    """
    import cec_fr
    import cec_synth_pipeline as synth
    import cec_operation_budget as budget
    import pcbnew
    source = Path(source).resolve()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = dict(schema=1, ok=False, attempts=[], selected=None)
    state = cec_fr._pourfirst_state()
    if not prospective_recovery_allowed(pcbnew.LoadBoard(str(source)), state):
        report['reason'] = 'physical_power_authority_or_incomplete_plan'
        return report
    operations = (
        ('reconcile', synth._reconcile_frozen_power_authority_around_locked_prefix),
        ('replan', synth._replan_power_authority_around_locked_prefix))
    for name, operation in operations:
        budget.progress('prefix_power_' + name)
        row = dict(strategy=name, ok=False)
        report['attempts'].append(row)
        try:
            result = operation(str(source), pours, str(out), label='prefix-' + name)
            state_path = Path(result['state'])
            power = json.loads(state_path.read_text())
            if not power.get('exact_admission', {}).get('passed'):
                raise RuntimeError('recovered power lacks exact admission')
            row.update(ok=True, evidence=result)
            report.update(ok=True, selected=result['preview_board'],
                          state=str(state_path), power=power)
            break
        except Exception as exc:
            row['error'] = type(exc).__name__ + ': ' + str(exc)
            row['failure'] = synth._power_authority_failure_feedback(
                str(out), 'prefix-' + name)
        finally:
            budget.write_json(out / 'recovery.json', report)
    return report


def _compile_power_with_recovery(cfg, source, pours, out, report):
    """Replay first; recover an unbuilt conflicting plan in a private worker."""
    import pcbnew
    import cec_fr
    import cec_synth_pipeline as synth
    import cec_power_artifact_worker
    import cec_operation_budget as budget
    power = out / 'power.kicad_pcb'
    try:
        result = synth._compile_post_priority_power_state(
            str(source), list(pours), str(out / 'exact-state.json'), str(power))
        if result.get('exact_admission', {}).get('passed'):
            authority = power.with_suffix('.pourfirst-state.json')
            budget.write_json(authority, result)
            os.environ['CEC_POURFIRST_STATE'] = str(authority)
        return result
    except RuntimeError as exc:
        report['power_replay_error'] = type(exc).__name__ + ': ' + str(exc)
        if (not cfg.params.get('local_power_prefix_recovery', True)
                or not prospective_recovery_allowed(
                    pcbnew.LoadBoard(str(source)), cec_fr._pourfirst_state())):
            raise
    work = out / 'recovery'
    work.mkdir(exist_ok=False)
    payload = work / 'request.json'
    budget.write_json(payload, dict(pours=list(pours), out=str(work)))
    result_path = work / 'result.json'
    command = [sys.executable, cec_power_artifact_worker.__file__,
               'prefix-power-recovery', str(source), '--completion-file',
               str(payload), '--report', str(result_path)]
    try:
        operation = budget.run(command, work, operation='prefix-power-recovery',
            timeout=float(cfg.params.get('local_power_recovery_timeout_s', 300)))
    except budget.OperationFailure as exc:
        report['power_recovery'] = dict(ok=False, operation=exc.failure_evidence)
        if (work / 'recovery.json').exists():
            report['power_recovery']['partial'] = json.loads((work / 'recovery.json').read_text())
        raise
    recovery = json.loads(result_path.read_text())
    report['power_recovery'] = dict(recovery, operation=operation)
    if not recovery.get('ok'):
        raise RuntimeError('bounded prospective power recovery refused')
    # The next reference-plane transaction copies this exact authority with
    # the recovered board, not the source's stale placement-time plan.
    shutil.copy2(recovery['selected'], power)
    cec_fr.copy_project_sidecars(recovery['selected'], str(power))
    shutil.copy2(recovery['state'], power.with_suffix('.pourfirst-state.json'))
    os.environ['CEC_POURFIRST_STATE'] = str(power.with_suffix('.pourfirst-state.json'))
    return recovery['power']


def construct(cfg, source, out, *, local_pi, pours=()):
    import pcbnew
    import cec_fr
    import cec_synth_pipeline as synth
    import cec_full_pipeline as pipeline
    import cec_precision_route as precision
    import cec_route_preflight as preflight
    import cec_decoupler_cell as cells
    import cec_ground_plane
    import cec_placement_route_prefix as prefixes
    import cec_score
    import cec_stage_admission

    if not local_pi.get('ok') or local_pi.get('rolled_back'):
        raise ValueError('complete admitted local PI is required')
    source = Path(source).resolve()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    poses = pipeline._placement_position_signature(source)
    started = time.monotonic()
    board = pcbnew.LoadBoard(str(source))
    nets = {item.GetNetname() for item in board.GetTracks()}
    parent = cec_fr.copper_geometry_prefix_contract(str(source), nets)
    pair_prefix = prefixes.capture(str(source))
    before = cec_score.score(str(source))
    report = dict(schema=1, ok=False, selected=None,
                  stage='local_pi_kelvin_power_barrier', source=str(source),
                  source_sha256=digest, residual_allowed=False,
                  release_accepted=False, stages=[], next_pair_policy='power-first')
    bound, authority = synth.config_with_board_route_authority(cfg, str(source))
    report['source_authority'] = authority
    try:
        with synth._oracle_env(bound.params):
            # Capture obligations BEFORE a failed proposal can drop a rail.
            # The compiler's returned frozen_nets alone cannot define success.
            required_power = set(cec_fr._pourfirst_state().get('frozen_nets') or ())
            required_power.update(str(p['net']) for p in pours if p.get('net'))
            reservations = preflight.compile_route_reservations(str(source))
            local = out / 'kelvin.kicad_pcb'
            report['stages'].append('kelvin')
            report['kelvin'] = precision.precision_route(
                str(source), str(local), do_pairs=False,
                kelvin_avoid=preflight.priority_kelvin_avoid(
                    reservations, policy='critical-first'))
            kelvin = report['kelvin'].get('kelvin') or {}
            if kelvin.get('refused'):
                raise RuntimeError('local Kelvin construction refused')
            report['stages'].append('exact_power')
            power = out / 'power.kicad_pcb'
            report['power'] = _compile_power_with_recovery(
                cfg, local, pours, out, report)
            if not (report['power'].get('exact_admission') or {}).get('passed'):
                raise RuntimeError('exact local-prefix power admission refused')
            report['stages'].append('reference_planes')
            target = out / 'board.kicad_pcb'
            report['ground'] = cec_ground_plane.fill_and_admit(
                str(power), str(target),
                required_via_uuids=local_pi.get('required_via_uuids') or ())
            if not report['ground'].get('ok'):
                raise RuntimeError('local return-plane admission refused')
            report['stages'].append('saved_artifact_admission')
            report['parent_copper'] = cec_fr.check_copper_geometry_prefix(str(target), parent)
            report['placement_unchanged'] = pipeline._placement_position_signature(target) == poses
            report['qualified_pairs'] = prefixes.check_qualified_pairs(str(target), pair_prefix)
            final_board = pcbnew.LoadBoard(str(target))
            report['owned_copper_uuids'] = sorted(
                item.m_Uuid.AsString() for item in final_board.GetTracks())
            report['local_pi_final'] = cells.audit_board(
                final_board, board_path=str(target),
                ground_reach_mm=float(cfg.params.get('decoupler_ground_reach_mm', 1.5)),
                ground_pin_max_mm=float(cfg.params.get('decoupler_ground_pin_max_mm', 2.5)))
            after = cec_score.score(str(target))
            required_power.update(report['power'].get('frozen_nets') or ())
            proofs = synth._priority_power_authority_isolated(str(target), sorted(required_power))
            report['power_obligations'] = dict(required_nets=sorted(required_power),
                proofs=proofs, ok=power_connected(proofs, required_power,
                    after.detail.get('unconn_nets') or ()))
            report['kelvin_final'] = dict(ok=bool(after.kelvin_ok),
                faults=list(after.detail.get('kelvin_topology_faults') or ()))
            report['score_admission'] = cec_stage_admission.evaluate(before, after)
            report['counts'] = dict(before=dict(drc=before.drc, opens=before.unconnected),
                                   after=dict(drc=after.drc, opens=after.unconnected))
    except Exception as exc:
        report['error'] = type(exc).__name__ + ': ' + str(exc)
        if isinstance(exc, precision.PrecisionRouteRefused):
            report['kelvin'] = exc.report
    report['source_unchanged'] = hashlib.sha256(source.read_bytes()).hexdigest() == digest
    report['ok'] = admitted(report)
    if report['ok']:
        report['selected'] = str(target)
        report['selected_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        report['state'] = str(target.with_suffix('.pourfirst-state.json'))
        if not Path(report['state']).is_file():
            report.update(ok=False, selected=None, error='saved power authority is missing')
        else:
            report['state_sha256'] = hashlib.sha256(Path(report['state']).read_bytes()).hexdigest()
        report['locked_nets'] = sorted(set(report['kelvin'].get('locked_nets') or ())
                                      | set(report['power'].get('frozen_nets') or ()))
    report['wall_s'] = round(time.monotonic() - started, 6)
    pipeline.atomic_json(out / 'report.json', report)
    return report


def power_connected(proofs, nets, open_nets):
    """Apply the same source/sink-or-all-terminal rule as power admission."""
    return all(net in proofs and (
        bool(proofs[net].get('connected')) if proofs[net].get('available')
        else net not in set(open_nets)) for net in nets)


def reuse(cfg, source, out, prefix):
    """Revalidate saved power/local copper instead of compiling it twice."""
    import pcbnew
    import cec_fr,cec_ground_plane,cec_score,cec_stage_admission
    import cec_synth_pipeline as synth,cec_full_pipeline as pipeline
    import cec_placement_route_prefix as pairs
    if not prefix.get('ok') or not admitted(prefix):
        raise ValueError('an independently admitted local-power prefix is required')
    parent=Path(prefix['selected']);source=Path(source);out=Path(out)
    if (hashlib.sha256(parent.read_bytes()).hexdigest()!=prefix.get('selected_sha256')
            or hashlib.sha256(Path(prefix['state']).read_bytes()).hexdigest()!=prefix.get('state_sha256')):
        raise ValueError('local-power prefix evidence changed before reuse')
    out.mkdir(parents=True,exist_ok=False);target=out/'board.kicad_pcb'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    shutil.copy2(source,target);cec_fr.copy_project_sidecars(str(source),str(target))
    nets=set(prefix['power'].get('frozen_nets') or ())
    parent_board=pcbnew.LoadBoard(str(parent))
    all_nets={item.GetNetname() for item in parent_board.GetTracks()}
    copper=cec_fr.copper_geometry_prefix_contract(str(parent),all_nets)
    pair_contract=pairs.capture(str(source))
    def declarations(board):
        return json.dumps([row for row in cec_ground_plane._zone_declaration_signature(board)
                           if row[1] in nets],sort_keys=True)
    report=dict(schema=1,ok=False,selected=None,source=str(source),
                source_sha256=digest,release_accepted=False,residual_allowed=False)
    with synth._oracle_env(cfg.params):
        report['refilled']=bool(cec_fr.refill_zones(str(target)))
        after_board=pcbnew.LoadBoard(str(target))
        report['power_zone_declarations_unchanged']=declarations(parent_board)==declarations(after_board)
        report['parent_copper']=cec_fr.check_copper_geometry_prefix(str(target),copper)
        report['placement_unchanged']=pipeline._placement_position_signature(parent)==pipeline._placement_position_signature(target)
        report['qualified_pairs']=pairs.check_qualified_pairs(str(target),pair_contract)
        before=cec_score.score(str(parent));after=cec_score.score(str(target))
        report['score_admission']=cec_stage_admission.evaluate(before,after)
        report['power_authority']=synth._priority_power_authority_isolated(str(target),sorted(nets))
        report['power_connected']=power_connected(report['power_authority'],nets,after.detail.get('unconn_nets') or ())
        report['counts']=dict(drc=after.drc,opens=after.unconnected)
    report['source_unchanged']=digest==hashlib.sha256(source.read_bytes()).hexdigest()
    report['ok']=bool(report['refilled'] and report['power_zone_declarations_unchanged']
        and report['parent_copper']['ok'] and report['placement_unchanged']
        and report['qualified_pairs']['ok'] and report['score_admission']['accepted']
        and report['power_connected'] and report['source_unchanged'])
    if report['ok']:
        report.update(selected=str(target),state=prefix['state'])
    pipeline.atomic_json(out/'report.json',report)
    return report
