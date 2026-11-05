#!/usr/bin/env python3
"""Bounded critical-only routing waves between placement and residual routing.

A failed constructive precision probe is not proof that a placement cannot be
routed. Exercise the existing tiered backend before demanding another placement
ECO. This module never admits residual routing or promotes an unqualified board.
"""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path


def recovery_eligible(evidence, *, physical_ok, authority_ok):
    return bool(physical_ok and authority_ok and evidence and not evidence.get('error')
        and evidence.get('critical_pair_refused_count',0)
        and not any(evidence.get(key,0) for key in (
            'critical_declaration_error_count','critical_pin_access_blocked_count',
            'critical_unroutable_count','fanout_blocked_count',
            'critical_kelvin_refused_count','critical_route_quality_refused_count')))


def pending_pair_tiers(pairs, owned):
    """Derive atomic P/N tiers from topology, not USB/CAN name guesses."""
    owned=set(owned)
    return [tuple(pair[key] for key in ('p','n')) for pair in pairs
            if not {pair['p'],pair['n']} <= owned]


def candidate_admitted(row):
    return bool(row.get('prefix',{}).get('ok') and row.get('placement_unchanged')
        and row.get('priority_gate',{}).get('ok') and row.get('physical',{}).get('ok')
        and row.get('score_admission',{}).get('accepted')
        and row.get('independent_pair_signoff_ok')
        and row.get('pair_physics',{}).get('ok'))


def constructive_validation_eligible(row):
    """Do not re-solve placements to rediscover a failed saved-board gate."""
    return bool(row.get('prefix', {}).get('ok') and row.get('placement_unchanged')
                and row.get('score_admission', {}).get('accepted')
                and row.get('independent_pair_signoff_ok')
                and row.get('pair_physics', {}).get('ok'))


def failure_stack(row):
    """Small causal index; full gate evidence stays beside it in the report."""
    failed = []
    for field, good in (
            ('protected_copper', row.get('prefix', {}).get('ok')),
            ('placement_identity', row.get('placement_unchanged')),
            ('electrical_admission', row.get('score_admission', {}).get('accepted')),
            ('pair_connectivity', row.get('independent_pair_signoff_ok')),
            ('pair_physics', row.get('pair_physics', {}).get('ok'))):
        if not good:
            failed.append(field)
    if row.get('priority_gate') and not row['priority_gate'].get('ok'):
        failed.append('priority_constructive_validation')
    return failed


def recover(cfg, source, out, *, waves=2, passes=8, timeout=300):
    import pcbnew
    import cec_fr
    import cec_full_pipeline as pipeline
    import cec_precision_route as precision
    import cec_route_preflight as preflight
    import cec_staged_fr as staged
    import cec_score
    import cec_stage_admission
    import cec_constraints
    import cec_critical_checkpoint
    import cec_route_progress
    source=Path(source).resolve();out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=True)
    report_path=out/'recovery.json'
    if report_path.exists(): raise ValueError('recovery evidence already exists; use a new directory')
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    sources=pipeline._files_signature(pipeline._source_files(cfg,source))
    engine=pipeline._files_signature(sorted(Path(__file__).parent.glob('*.py')))
    original=pcbnew.LoadBoard(str(source))
    locked={t.GetNetname() for t in original.GetTracks() if t.IsLocked()}
    prefix=cec_fr.copper_geometry_prefix_contract(str(source),locked)
    poses=pipeline._placement_position_signature(source)
    source_score=cec_score.score(str(source))
    pairs,_schedule=precision._scheduled_coupled_pairs(original,
        precision.derive_coupled_pairs(str(source),board=original))
    owned=cec_fr.owned_locked_nets_board(original)
    tiers=pending_pair_tiers(pairs,owned)
    report={'schema':1,'source':str(source),'source_sha256':source_hash,
            'stage':'critical-only-routing-waves','residual_allowed':False,
            'waves':[],'pending_tiers':[list(t) for t in tiers],
            'protected_prefix':prefix,'ok':False,'selected':None}
    report.update(source_signature=sources,engine_signature=engine)
    pipeline.atomic_json(report_path,report)
    if not tiers:
        report['reason']='no_pending_pair_tiers'
        pipeline.atomic_json(report_path,report)
        return report
    report['status'] = 'preparing-refill-control'
    pipeline.atomic_json(report_path, report)
    report['refill_control'] = cec_route_progress.prepare_refill_control(
        source, out/'refill-control', source_score=source_score)
    # The constructive preflight is read-only. Materialize independently
    # qualified pairs here, once, instead of discarding them on a sibling's
    # refusal and making every backend wave repeat the same successful work.
    report['partial_selected'] = None
    report['status'] = 'constructing-critical-prefix'
    pipeline.atomic_json(report_path, report)
    frozen_cfg = cfg if pipeline._requires_frozen_route_authority(cfg) else None
    constructed = cec_critical_checkpoint.construct(source, out/'constructive', pairs,
                                                    frozen_route_config=frozen_cfg)
    report['constructive_checkpoint'] = constructed
    current = Path(constructed['selected']) if constructed.get('ok') else source
    if constructed.get('ok'):
        report.update(partial_selected=str(current), partial_proof=constructed['proof'])
    pipeline.atomic_json(report_path, report)
    seen_geometry = set()
    for seed in range(max(0,int(waves))):
        report['status'] = 'critical-routing-waves'
        owned = cec_fr.owned_locked_nets(str(current))
        tiers = pending_pair_tiers(pairs, owned)
        target=out/('wave-%02d'%seed)/'board.kicad_pcb'
        target.parent.mkdir(parents=True,exist_ok=True)
        row={'seed':seed,'status':'routing','board':str(target), 'parent':str(current),
             'pending_tiers':[list(t) for t in tiers],
             'routing_progress': str(target.with_suffix('.tier-progress.json'))}
        report['waves'].append(row);pipeline.atomic_json(report_path,report)
        print('[priority-recovery] routing wave %d: %d critical pair tiers; residual held' % (seed,len(tiers)),flush=True)
        try:
            start = time.monotonic()
            if tiers:
                with cec_critical_checkpoint.frozen_power_context(current,frozen_cfg):
                    routed=staged.route_tiered(str(current),str(target),tiers=tiers,
                        passes=passes,opt=8,threads=1,seed=seed,timeout=timeout,
                        pre_locked_nets=owned,skip_locked_taps=True,
                        include_residual=False,adaptive_retry_depth=1)
            else:
                import shutil
                shutil.copy2(current,target)
                cec_fr.copy_project_sidecars(str(current),str(target))
                routed={'reason':'all_pairs_already_owned','tiers':[]}
            row['routing']=routed
            row['routing_elapsed_s'] = round(time.monotonic() - start, 3)
            row['status']='validating'
            pipeline.atomic_json(report_path,report)
            row['partial_proof'] = cec_critical_checkpoint.validate(
                current, target, pairs, zones_refilled=cec_fr.refill_zones(str(target)))
            if row['partial_proof']['ok']:
                current = target
                report.update(partial_selected=str(target), partial_proof=row['partial_proof'])
            row['prefix']=cec_fr.check_copper_geometry_prefix(str(target),prefix)
            row['placement_unchanged']=pipeline._placement_position_signature(target)==poses
            if row['prefix']['ok'] and row['placement_unchanged']:
                score=cec_score.score(str(target))
                row['score_admission']=cec_stage_admission.evaluate(source_score,score)
                row['independent_pair_signoff_ok']=bool(score.diffpair_ok)
                row['pair_physics']=cec_constraints.high_speed_pair_summary(str(target))
                if constructive_validation_eligible(row):
                    # Analyze the actual routed artifact. Re-materialization
                    # would discard the prefix being tested.
                    evidence=preflight.compact_placement_evidence(preflight.analyze(
                        str(target),grid_mm=1.0,iters=4,backend='auto',
                        critical_nets=tuple(cfg.params.get('critical_route_nets',()) or ()),
                        run_future_congestion=True))
                    row['priority_evidence']=evidence
                    row['priority_gate']=pipeline._placement_priority_route_gate(evidence)
                    row['physical']=pipeline._measure_placement_physical(cfg,target)
                else:
                    row['skipped_validation'] = ['constructive_preflight', 'placement_remeasure']
                    row['skip_reason'] = 'saved_board_admission_failed'
                row['ok']=candidate_admitted(row)
                row['progress_attribution'] = cec_route_progress.compare(
                    report['refill_control'], target, score,
                    admitted=bool(row['ok'] or row['partial_proof'].get('ok')))
            else: row['ok']=False
            row['failure_stack'] = failure_stack(row)
            all_nets = [net.GetNetname() for net in original.GetNetInfo().NetsByNetcode().values()
                        if net.GetNetname()]
            geometry = cec_fr.copper_geometry_signature(str(target), all_nets)['sha256']
            row['copper_geometry_sha256'] = geometry
            row['repeated_geometry'] = geometry in seen_geometry
            seen_geometry.add(geometry)
            row['elapsed_s'] = round(time.monotonic() - start, 3)
            row['status']='admitted' if row['ok'] else 'blocked'
            if row['ok']:
                report.update(ok=True,selected=str(target),reason='critical_routes_admitted')
        except Exception as exc:
            row.update(status='failed',ok=False,error=type(exc).__name__+': '+str(exc))
        pipeline.atomic_json(report_path,report)
        if report['ok']:break
        if row.get('repeated_geometry'):
            report['reason'] = 'repeated_unadmitted_geometry'
            break
    if not report.get('reason'):
        report['reason'] = 'critical_route_budget_exhausted'
    report['source_unchanged']=hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    if not report['source_unchanged']:raise RuntimeError('source changed during recovery')
    from cec_board_suite import signature_unchanged
    report['source_inputs_unchanged']=signature_unchanged(sources)
    report['engine_unchanged']=signature_unchanged(engine)
    if not report['source_inputs_unchanged'] or not report['engine_unchanged']:
        report.update(ok=False,selected=None,partial_selected=None,
                      reason='inputs_or_engine_changed_during_recovery')
    report['status'] = 'finished'
    pipeline.atomic_json(report_path,report)
    return report


def main():
    import cec_operation_budget
    diagnostic_handle = cec_operation_budget.arm_diagnostics()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board',required=True)
    parser.add_argument('--input',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--waves',type=int,default=2)
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--params-file')
    args=parser.parse_args()
    if args.waves<1 or args.waves>8 or args.timeout<1:parser.error('invalid recovery budget')
    import cec_synth_pipeline as synth
    import cec_full_pipeline as pipeline
    cfg=synth.Config.load(args.board);cfg.net=None
    if args.params_file:
        cfg.params.update(json.loads(Path(args.params_file).read_text()))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    cec_operation_budget.progress('recovery_source_intake')
    intake=pipeline._source_intake(cfg,Path(args.input),out/'intake.json',allow_derived_input=True)
    if not intake.get('ok'):raise RuntimeError('source intake blocked')
    bound,authority=synth.config_with_board_route_authority(cfg,str(Path(args.input).resolve()))
    pipeline.atomic_json(out/'authority.json',authority)
    if not authority.get('ok') or (pipeline._requires_frozen_route_authority(cfg) and not authority.get('bound')):
        raise RuntimeError('exact routing authority not admitted')
    cfg=bound
    cec_operation_budget.progress('recovery_physical_admission')
    physical=pipeline._measure_placement_physical(cfg,args.input)
    pipeline.atomic_json(out/'physical.json',physical)
    if not physical['ok']:raise RuntimeError('physical placement not admitted')
    cec_operation_budget.progress('recovery_critical_waves')
    result=recover(cfg,args.input,args.out,waves=args.waves,timeout=args.timeout)
    cec_operation_budget.progress('recovery_complete', admitted=bool(result.get('ok')))
    print(json.dumps({k:result.get(k) for k in ('ok','selected','reason','source_unchanged')}),flush=True)
    os._exit(0 if result['ok'] else 2)


if __name__=='__main__':main()
