"""Bounded additive-only native residual portfolio with exact family retention.

This composes the existing certificate router; it owns no replacement copper,
placement, power solve or release authority. A failure retains the last
independently received child, not merely the last file a worker wrote.
"""
import math
from pathlib import Path
import time


def run(source,output_dir,*,board_hint=None,wall_s=120.,max_rounds=4,max_targets=16,
        scheduling_history=None):
    import cec_additive_pair_repair as additive
    import cec_certificate_repair as repair
    import cec_force_current as force
    import cec_final_residual as residual
    import cec_stage_admission as admission
    if (type(wall_s) not in (int,float) or not math.isfinite(wall_s) or not 30<=wall_s<=600
            or type(max_rounds) is not int or not 1<=max_rounds<=32
            or type(max_targets) is not int or not 1<=max_targets<=64):
        raise ValueError('bounded_residual_breadth_policy_required')
    source=Path(source).resolve();output=Path(output_dir).resolve()
    if output.exists():raise ValueError('residual_breadth_output_already_exists')
    source_family=force._family(source,board_hint);epoch=force._code_identity()
    output.mkdir(parents=True)
    current=force._copy_family(source,output/'candidate')
    report=dict(schema=1,operation='exact_additive_residual_breadth',changed=False,
        source=str(source),source_sha256=force._hash(source),candidate=str(current),
        rounds=[],routing_admitted=False,power_qualified=False,release_authority=False)
    began=time.monotonic()
    effort=repair.RepairEffortBudget(max_attempts=max_targets*max_rounds,
        wall_budget_s=wall_s,started=began)
    deadline_token=repair._WORKER_DEADLINE.set(began+wall_s)
    try:
        drc=output/'baseline.drc.json'
        repair._spawn_apply(repair._run_drc,(str(current),str(drc)))
        baseline=repair._spawn_apply(repair._score_worker,(str(current),str(drc)))
        before=baseline;report['baseline']=baseline
        history=None
        scheduling_history=additive.scheduling_feedback(scheduling_history,[])
        report['initial_scheduling_feedback']=dict(
            scope='ordering_only_no_search_suppression',
            previous_pair_count=len(scheduling_history))
        for index in range(max_rounds):
            left=effort.remaining_wall_s()
            if left<25.:
                report['stop']='admission_reserve';break
            completion=repair._spawn_apply(additive.fresh_completion,(str(current),),
                timeout_s=min(25.,left-15.))
            if not additive.bound_snapshot(current,completion):
                raise ValueError('fresh_native_breadth_snapshot_required')
            if history is not None:
                # Search history is separate from the freshly bound native
                # residual packet. sweep() verifies its exact input identity
                # and algorithm before suppressing an equivalent funded retry.
                completion=dict(completion,plan=dict(completion.get('plan') or {},
                    certified_additive=history))
            work=output/('round-%02d'%index);work.mkdir()
            prior_candidate=force._family(current,board_hint)
            row=additive.sweep(str(current),before,completion,work_dir=work,
                effort=effort,stage_budget_s=min(60.,effort.remaining_wall_s()-5.),
                max_targets=max_targets,preserve_family=True,
                scheduling_history=scheduling_history)
            scheduling_history=additive.scheduling_feedback(
                scheduling_history,row.get('attempts') or [])
            report['scheduling_history']=scheduling_history
            report['rounds'].append(row)
            if not row.get('adopted'):
                if prior_candidate!=force._family(current,board_hint):
                    raise ValueError('unreceived_breadth_candidate_changed')
                history=row
                if (row.get('stop')=='additive_stage_wall_budget'
                        and row.get('attempts') and effort.remaining_wall_s()>=25.):
                    # A batch lease ending is not a plateau. Retain the
                    # sampled identities and continue to unvisited frontiers
                    # under this same finite portfolio/round/attempt budget.
                    force._write(output/'breadth.json',report)
                    continue
                report['stop']=row.get('stop') or 'no_unvisited_additive_gain';break
            after=row['after']
            monotonic=admission.evaluate(baseline,after,require_strict=True)
            if not monotonic['accepted'] or after['unconnected']>=before['unconnected']:
                raise ValueError('independent_breadth_monotonicity_failed')
            before=after;history=None;report.update(changed=True,final=after)
            force._write(output/'breadth.json',report)
            if after['unconnected']==0:
                report['stop']='native_connectivity_complete';break
        else:report['stop']='round_budget'
    except Exception as exc:
        report.update(stop='bounded_breadth_failure',error=type(exc).__name__+':'+str(exc))
    finally:
        repair._WORKER_DEADLINE.reset(deadline_token)
    report.update(candidate_sha256=force._hash(current),
        source_family_unchanged=source_family==force._family(source,board_hint),
        code_unchanged=epoch==force._code_identity(),wall_s=round(time.monotonic()-began,3))
    if not (report['source_family_unchanged'] and report['code_unchanged']):
        report.update(changed=False,stop='source_or_code_identity_changed')
    report['effort_budget']=effort.report()
    force._write(output/'breadth.json',report)
    return report
