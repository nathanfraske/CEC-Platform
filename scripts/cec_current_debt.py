"""Exact current-model debt comparison, not a new rating or release waiver.

One failing check may contain many distinct faults. Comparing its PASS/FAIL
label or fault count alone can admit new debt while routing improves. Use the
complete source-typed per-object inventory, preserve existing current authority,
and compare every surviving fault as well as its severity. Missing/truncated
evidence refuses comparison; legacy text is not a substitute for object IDs.
"""
from collections import Counter
from copy import deepcopy
import json
import math
from pathlib import Path


def _authority(row):
    value=row.get('current_authority')
    if not isinstance(value,dict) or not value:
        raise ValueError('current_debt_authority_missing')
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _positive(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
        raise ValueError('current_debt_dimension_missing_or_invalid')
    return float(value)


def _snapshot(result):
    if not isinstance(result,(tuple,list)) or len(result) not in (2,3):
        raise ValueError('current_debt_checker_result_missing')
    status,detail=result[:2]
    if status is not True and status is not False and status is not None:
        raise ValueError('current_debt_checker_status_invalid')
    if status is not False:
        if len(result)==3 and result[2]:raise ValueError('unexpected_nonfailure_current_payload')
        return dict(status=status,detail=detail,atoms={})
    payload=result[2] if len(result)==3 else None
    if not isinstance(payload,list):raise ValueError('complete_current_debt_inventory_required')
    summaries=[v for v in payload if isinstance(v,dict) and v.get('type')=='current_debt_inventory']
    if (len(summaries)!=1 or summaries[0].get('schema')!=1
            or summaries[0].get('complete') is not True):
        raise ValueError('complete_current_debt_inventory_required')
    # A conservative aggregate fallback after a timed-out branch classifier
    # is not a newly observed physical fault. Its resulting object inventory
    # cannot be compared with a complete, positively typed source snapshot.
    # Keep that uncertainty explicit instead of claiming either regression
    # OR improvement. Existing current requirements are never reduced here.
    for kind in ('typed_measurement_branch_receiving','typed_resistive_monitor_receiving',
            'typed_control_branch_receiving','typed_supply_consumer_receiving',
            'typed_auxiliary_attachment_receiving'):
        if kind in summaries[0]:
            branch=summaries[0][kind]
            if not isinstance(branch,dict) or branch.get('complete') is not True:
                raise ValueError('current_debt_branch_inventory_incomplete:'+kind)
    atoms={};counts=Counter()
    def add(key,atom):
        if key in atoms:raise ValueError('current_debt_duplicate_object_identity')
        atoms[key]=atom
    for row in payload:
        if not isinstance(row,dict):raise ValueError('current_debt_payload_invalid')
        kind=row.get('type')
        if kind=='current_debt_inventory':continue
        if type(row.get('net')) is not str or not row['net']:
            raise ValueError('current_debt_net_identity_missing')
        authority=_authority(row)
        if kind=='keepout' and row.get('reserve')=='pour_or_widen':
            if (type(row.get('uuid')) is not str or not row['uuid']
                    or type(row.get('layer')) is not str or not row['layer']):
                raise ValueError('current_debt_native_track_identity_missing')
            add(('trace',row['net'],row['uuid'],row['layer']),dict(authority=authority,
                actual=_positive(row.get('actual_mm')),required=_positive(row.get('required_mm'))))
            counts['trace_fault_count']+=1
        elif kind=='current_domain_path':
            segments=row.get('undersized_segments');ids=set()
            if not isinstance(segments,list) or not segments:
                raise ValueError('current_debt_domain_segment_inventory_missing')
            for segment in segments:
                if not isinstance(segment,dict) or not segment.get('uuid') or not segment.get('layer'):
                    raise ValueError('current_debt_domain_track_identity_missing')
                uid=segment['uuid']
                if uid in ids:raise ValueError('current_debt_duplicate_domain_track_identity')
                ids.add(uid)
                add(('domain_trace',row['net'],uid,segment['layer']),dict(authority=authority,
                    actual=_positive(segment.get('actual_mm')),required=_positive(segment.get('required_mm'))))
            if type(row.get('removed_undersized_segments')) is not int or row['removed_undersized_segments']!=len(ids):
                raise ValueError('current_debt_domain_inventory_truncated')
            states={}
            for name in ('original_connectivity','rated_connectivity'):
                proof=row.get(name)
                if not isinstance(proof,dict) or proof.get('available') is not True or type(proof.get('connected')) is not bool:
                    raise ValueError('current_debt_native_domain_proof_missing')
                states[name]=proof['connected']
            add(('domain',row['net']),dict(authority=authority,**states))
            counts['domain_fault_count']+=1
        else:raise ValueError('unsupported_or_unknown_current_debt_evidence')
    summary=summaries[0]
    for name in ('trace_fault_count','domain_fault_count','violation_count'):
        count=sum(counts.values()) if name=='violation_count' else counts[name]
        if type(summary.get(name)) is not int or summary[name]!=count:
            raise ValueError('current_debt_inventory_count_or_completeness_mismatch')
    if not atoms:raise ValueError('failed_current_check_without_fault_objects')
    return dict(status=status,detail=detail,atoms=atoms)


def evaluate(before,after):
    report=dict(schema=1,ok=False,complete=False,errors=[],new_faults=[],worsened_faults=[],
        current_qualified=False,release_authority=False)
    try:
        old,new=_snapshot(before),_snapshot(after)
        if new['status'] is None and (old['status'] is not None or old['detail']!=new['detail']):
            raise ValueError('current_model_evidence_became_unavailable_or_changed')
        report['new_faults']=[list(k) for k in sorted(set(new['atoms'])-set(old['atoms']))]
        for key in sorted(set(old['atoms'])&set(new['atoms'])):
            a,b=old['atoms'][key],new['atoms'][key]
            worse=a['authority']!=b['authority']
            if key[0]=='domain':
                worse|=any(a[name] and not b[name] for name in ('original_connectivity','rated_connectivity'))
            else:
                worse|=abs(a['required']-b['required'])>1e-9 or b['actual']+1e-9<a['actual']
            if worse:report['worsened_faults'].append(list(key))
        report.update(complete=True,ok=not report['new_faults'] and not report['worsened_faults'],
            before_fault_objects=len(old['atoms']),after_fault_objects=len(new['atoms']),
            current_qualified=new['status'] is True,
            qualification_scope='existing_current_width_check_only_not_whole_power_or_release')
    except (ValueError,TypeError,KeyError) as exc:report['errors'].append(str(exc))
    return report


def receive(source,candidate,*,board_hint):
    """Fresh immutable source-family/model receiving for any private operator."""
    import pcbnew
    import cec_constraints as constraints
    import cec_force_current as force
    report=dict(ok=False,complete=False,errors=[],current_qualified=False,release_authority=False)
    try:
        if type(board_hint) is not str or not board_hint:raise ValueError('current_debt_board_identity_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        families=[force._family(path,board_hint) for path in paths];epoch=force._code_identity()
        results=[]
        identical_path=paths[0]==paths[1]
        # No global cache or candidate-byte shortcut. The exact same saved
        # path/family has no independent changed-board epoch to evaluate.
        # One FRESH native snapshot, received for completeness, is sufficient
        # for its identity comparison. Distinct paths still get two native
        # evaluations, even when their PCB bytes happen to match.
        for path in paths[:1] if identical_path else paths:
            with force._thermal_hint(board_hint):
                board=pcbnew.LoadBoard(str(path))
                results.append(constraints.CHECKERS['trace-width-high-current'](board,str(path),{}))
        native_evaluations=len(results)
        if identical_path:results.append(deepcopy(results[0]))
        report=evaluate(*results)
        report['independent_native_evaluations']=native_evaluations
        report['exact_identical_saved_path_snapshot_reused']=identical_path
        stable=families==[force._family(path,board_hint) for path in paths] and epoch==force._code_identity()
        report['source_candidate_and_code_unchanged']=stable
        report['ok'] &= stable
        if not stable:report['errors'].append('current_debt_source_candidate_or_code_changed')
        report['before_result']=results[0];report['after_result']=results[1]
    except Exception as exc:report['errors'].append(type(exc).__name__+':'+str(exc))
    return report
