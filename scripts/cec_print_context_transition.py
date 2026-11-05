"""Independently received same-FPID print-library transition identity.

This is a typed scope adapter, NOT full admission. Current, field, Ground,
contact/Kelvin, source intake, parity, native-all-findings and craft gates
remain mandatory. No caller library authority or success receipt is accepted.
"""
import math
import json
import re
import time
from pathlib import Path


def receive_row(candidate,declaration,*,board_hint,assembly_instance=None,timeout_s=10.):
    """Resolve an exact plan declaration; serialized contexts are forbidden."""
    import cec_force_current as force
    if type(declaration)is not dict or set(declaration)!={'source','proposal'}:
        raise ValueError('exact_print_transition_declaration_required')
    paths={}
    for name in('source','proposal'):
        row=declaration[name]
        if (type(row)is not dict or set(row)!={'path','sha256'}
                or type(row['path'])is not str or not row['path']
                or type(row['sha256'])is not str or re.fullmatch('[0-9a-f]{64}',row['sha256'])is None):
            raise ValueError('exact_print_transition_file_binding_required')
        path=Path(row['path']).resolve(strict=True)
        if not path.is_file()or force._hash(path)!=row['sha256']:
            raise ValueError('print_transition_declared_file_changed')
        paths[name]=path
    proposal=json.loads(paths['proposal'].read_text())
    result=receive(paths['source'],candidate,proposal,board_hint=board_hint,
                   assembly_instance=assembly_instance,timeout_s=timeout_s)
    if any(force._hash(paths[name])!=declaration[name]['sha256']for name in paths):
        raise ValueError('print_transition_declared_file_changed_during_receiving')
    return result


def receive(source,candidate,proposal,*,board_hint,assembly_instance=None,timeout_s=10.):
    import cec_force_current as force
    import cec_received_private_stage as stage
    import cec_native_library_context as libraries
    import cec_synth_pipeline as synth
    import cec_nonpolar_print_context as op
    import cec_optional_body_ink_contract as body
    result=dict(ok=False,complete=False,scope_only=True,admitted=False,release_authority=False)
    started=scope_done=finished=None
    try:
        if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
            raise ValueError('bounded_print_transition_receiving_required')
        started=time.monotonic();source=Path(source).resolve(strict=True);candidate=Path(candidate).resolve(strict=True)
        if source==candidate:raise ValueError('distinct_original_and_print_child_required')
        if type(board_hint)is not str or not board_hint or proposal.get('board_hint')!=board_hint:
            raise ValueError('exact_print_source_board_hint_required')
        paths=(source,candidate);code=force._code_identity();families=[force._family(p,board_hint)for p in paths]
        dependencies={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))
            for m in(op,op.ink,op.ink.frame,body)}
        result['bounded_composition']=dict(kind='scope_then_identity_live',
            scope_limit_s=timeout_s,identity_live_limit_s=timeout_s,aggregate_limit_s=2*timeout_s,
            whole_check_is_not_a_single_ten_second_phase=True)
        # This MUST precede any derivation of child authority. Metadata is not
        # authority: op.receive independently reconstructs the entire family.
        composed=proposal.get('reference_mapping_transition')is not None
        if composed:
            result['bounded_composition']=dict(kind='staged_map_print_scope_then_identity_live',
                per_constituent_limit_s=timeout_s,constituents=list(_STAGED_NAMES)+['identity_live'],aggregate_limit_s=6*timeout_s,
                whole_check_is_not_a_single_ten_second_phase=True)
        scope=(op.receive_staged(source,candidate,proposal,timeout_s=timeout_s)if composed
            else op.receive(source,candidate,proposal,timeout_s=timeout_s))
        result['operator_scope']=scope
        if scope.get('ok')is not True or scope.get('complete')is not True:
            raise ValueError('independent_print_scope_refused:'+str(scope.get('error')))
        scope_done=time.monotonic()
        if composed:
            if not _staged_operator_valid(scope,timeout_s):raise ValueError('invalid_staged_print_scope')
            # All enclosing preparation and operator overhead belongs to the
            # first fixed stage, never hidden outside the declared budget.
            first=scope_done-started-sum(v for k,v in scope['timings_s'].items()if k!='map_reconstruct')
            if first+1e-8<scope['timings_s']['map_reconstruct']:
                raise ValueError('print_transition_staged_scope_clock_inconsistent')
            if first>=timeout_s:raise ValueError('print_transition_map_reconstruction_deadline')
            result['bounded_composition']=dict(kind='staged_map_print_scope_then_identity_live',
                per_constituent_limit_s=timeout_s,constituents=list(_STAGED_NAMES)+['identity_live'],aggregate_limit_s=6*timeout_s,
                whole_check_is_not_a_single_ten_second_phase=True)
        elif scope_done-started>=timeout_s:raise ValueError('print_transition_scope_deadline')
        cfg=synth.Config.load(board_hint);canonical=Path(cfg.dir)/'fp-lib-table'
        old=stage.stable(libraries.authority(source,canonical))
        if stage.stable(scope.get('old_library_context'))!=old:
            raise ValueError('print_original_context_not_canonical_source')
        table=candidate.parent/'fp-lib-table'
        child_context=stage.stable(libraries.authority(candidate,table))
        if stage.stable(scope.get('new_library_context'))!=child_context:
            raise ValueError('print_child_context_not_independently_received')
        source_identity=stage.identity(source,board_hint,assembly_instance)
        child_instance=stage.matched_instance(assembly_instance,candidate)
        child_identity=stage.identity(candidate,board_hint,child_instance)
        # Require the default, unmodified canonical identity to agree FIRST;
        # only this exact receiver-owned authority field may transition.
        if source_identity['native_library_authority']!=old or child_identity['native_library_authority']!=old:
            raise ValueError('default_canonical_identity_context_conflict')
        child_identity=dict(child_identity,native_library_authority=child_context)
        if (code!=force._code_identity()or any(force._hash(Path(p))!=h for p,h in dependencies.items())
                or families!=[force._family(p,board_hint)for p in paths]
                or old!=stage.stable(libraries.authority(source,canonical))
                or child_context!=stage.stable(libraries.authority(candidate,table))):
            raise ValueError('print_transition_source_code_or_context_changed')
        finished=time.monotonic()
        if finished-scope_done>=timeout_s:raise ValueError('print_transition_identity_live_deadline')
        if finished-started>=(6 if composed else 2)*timeout_s:raise ValueError('print_transition_aggregate_deadline')
        result.update(ok=True,complete=True,operator_scope=scope,
            source_identity=source_identity,candidate_identity=child_identity,
            old_library_context=old,new_library_context=child_context,
            source_native_arguments=dict(board_hint=None,footprint_table=str(canonical)),
            candidate_native_arguments=dict(board_hint=None,footprint_table=str(table)),
            all_shared_receiving_still_required=True)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError)as exc:result['error']=str(exc)
    if started is not None:
        if finished is None:finished=time.monotonic()
        result['timings_s']=dict(scope=(scope_done if scope_done is not None else finished)-started,
            identity_live=finished-scope_done if scope_done is not None else 0.,aggregate=finished-started)
        if result.get('bounded_composition',{}).get('kind')=='reconstruction_then_saved_scope_then_identity_live':
            saved_time=scope['timings_s']['saved_native_comparison']
            result['timings_s']=dict(source_reconstruction=scope_done-started-saved_time,
                saved_native_comparison=saved_time,identity_live=finished-scope_done,aggregate=finished-started)
        elif (result.get('bounded_composition',{}).get('kind')=='staged_map_print_scope_then_identity_live'
                and scope_done is not None and _staged_operator_valid(scope,timeout_s)):
            result['timings_s']=dict(scope['timings_s'],identity_live=finished-scope_done,aggregate=finished-started)
            result['timings_s']['map_reconstruct']=scope_done-started-sum(
                v for k,v in scope['timings_s'].items()if k!='map_reconstruct')
    return result


_STAGED_NAMES=('map_reconstruct','map_receive','source_plan','reconstruct','saved_compare')


def _staged_operator_valid(scope,limit):
    if scope.get('ok')is not True or scope.get('complete')is not True:return False
    bound=scope.get('bounded_composition');times=scope.get('timings_s',{});observation=scope.get('staged_replay',{})
    if bound!=dict(kind='fresh_source_plan_reconstruct_saved_native',per_constituent_limit_s=limit,
            constituents=list(_STAGED_NAMES),aggregate_limit_s=5*limit):return False
    if (set(times)!=set(_STAGED_NAMES)or any(type(v)not in(int,float)or not math.isfinite(v)or not 0<=v<limit for v in times.values())
            or type(scope.get('elapsed_s'))not in(int,float)or not math.isfinite(scope['elapsed_s'])
            or not sum(times.values())-1e-8<=scope['elapsed_s']<5*limit):return False
    return observation==dict(state='received',timings_s=times,per_constituent_limit_s=limit,
        constituents=list(_STAGED_NAMES),aggregate_limit_s=5*limit,no_saved_verdict_or_release_authority=True)


def _operator_composition_valid(scope,limit):
    if scope.get('ok')is not True or scope.get('complete')is not True:return False
    bounds=scope.get('bounded_composition');timing=scope.get('timings_s',{})
    if bounds!=dict(kind='source_reconstruction_then_saved_native_comparison',
            per_constituent_limit_s=limit,aggregate_limit_s=2*limit):return False
    if set(timing)!={'source_reconstruction','saved_native_comparison','aggregate'}:return False
    if any(type(v)not in(int,float)or not math.isfinite(v)or v<0 for v in timing.values()):return False
    return (timing['source_reconstruction']<limit and timing['saved_native_comparison']<limit
        and timing['aggregate']<2*limit and math.isclose(timing['aggregate'],
            timing['source_reconstruction']+timing['saved_native_comparison'],abs_tol=1e-8))


def same_replay(left,right):
    """Compare two FRESH receiver results, retaining all authority fields.

    Timing observations are not repeatable identity. This helper validates
    their explicit bounds but cannot authorize a context or replace receive.
    """
    for result in(left,right):
        if result.get('ok')is not True or result.get('complete')is not True:return False
        bounds=result.get('bounded_composition',{});timing=result.get('timings_s',{})
        if bounds.get('kind')=='staged_map_print_scope_then_identity_live':
            limit=bounds.get('per_constituent_limit_s');names=list(_STAGED_NAMES)+['identity_live']
            if (type(limit)not in(int,float)or not math.isfinite(limit)or not 0<limit<=10
                    or bounds!=dict(kind='staged_map_print_scope_then_identity_live',per_constituent_limit_s=limit,
                        constituents=names,aggregate_limit_s=6*limit,whole_check_is_not_a_single_ten_second_phase=True)
                    or set(timing)!=set(names+['aggregate'])
                    or any(type(v)not in(int,float)or not math.isfinite(v)or v<0 for v in timing.values())
                    or any(timing[k]>=limit for k in names)or timing['aggregate']>=6*limit
                    or not math.isclose(timing['aggregate'],sum(timing[k]for k in names),abs_tol=1e-8)
                    or not _staged_operator_valid(result.get('operator_scope',{}),limit)):return False
            inner=result['operator_scope']['timings_s']
            if (timing['map_reconstruct']+1e-8<inner['map_reconstruct']or
                    any(not math.isclose(timing[k],inner[k],abs_tol=1e-8)for k in _STAGED_NAMES if k!='map_reconstruct')):return False
            continue
        if bounds.get('kind')=='reconstruction_then_saved_scope_then_identity_live':
            limit=bounds.get('per_constituent_limit_s')
            if (type(limit)not in(int,float)or not math.isfinite(limit)or not 0<limit<=10
                or bounds!=dict(kind='reconstruction_then_saved_scope_then_identity_live',
                    per_constituent_limit_s=limit,aggregate_limit_s=3*limit,
                    whole_check_is_not_a_single_ten_second_phase=True)
                or set(timing)!={'source_reconstruction','saved_native_comparison','identity_live','aggregate'}
                or any(type(v)not in(int,float)or not math.isfinite(v)or v<0 for v in timing.values())
                or any(timing[k]>=limit for k in('source_reconstruction','saved_native_comparison','identity_live'))
                or timing['aggregate']>=3*limit
                or not math.isclose(timing['aggregate'],sum(v for k,v in timing.items()if k!='aggregate'),abs_tol=1e-8)
                or not _operator_composition_valid(result.get('operator_scope',{}),limit)):return False
            inner=result['operator_scope']['timings_s']
            if (not math.isclose(timing['saved_native_comparison'],inner['saved_native_comparison'],abs_tol=1e-8)
                or timing['source_reconstruction']+1e-8<inner['source_reconstruction']):return False
            continue
        if (set(bounds)!={'kind','scope_limit_s','identity_live_limit_s','aggregate_limit_s','whole_check_is_not_a_single_ten_second_phase'}
                or bounds['kind']!='scope_then_identity_live'
                or bounds['whole_check_is_not_a_single_ten_second_phase']is not True
                or set(timing)!={'scope','identity_live','aggregate'}):return False
        limit=bounds['scope_limit_s']
        if (type(limit)not in(int,float)or not math.isfinite(limit)or not 0<limit<=10
                or bounds['identity_live_limit_s']!=limit or bounds['aggregate_limit_s']!=2*limit):return False
        if any(type(v)not in(int,float)or not math.isfinite(v)or v<0 for v in timing.values()):return False
        if (timing['scope']>=limit or timing['identity_live']>=limit or timing['aggregate']>=2*limit
                or not math.isclose(timing['aggregate'],timing['scope']+timing['identity_live'],abs_tol=1e-8)):return False
    def stable(result):
        value={k:v for k,v in result.items()if k!='timings_s'}
        if value.get('bounded_composition',{}).get('kind')=='staged_map_print_scope_then_identity_live':
            value['operator_scope']={k:v for k,v in value['operator_scope'].items()if k not in('timings_s','elapsed_s')}
            value['operator_scope']['staged_replay']={k:v for k,v in value['operator_scope']['staged_replay'].items()if k!='timings_s'}
        if value.get('bounded_composition',{}).get('kind')=='reconstruction_then_saved_scope_then_identity_live':
            value['operator_scope']={k:v for k,v in value['operator_scope'].items()if k!='timings_s'}
        return value
    return stable(left)==stable(right)


def require_native_context(producer,source,child,proposal,*,board_hint,candidate,
                           assembly_instance=None,timeout_s=10.):
    """Re-receive scope before comparing actual runner authority.

    No externally supplied transition receipt can authorize native context.
    This does not replace require_native_tool or the remaining shared gates.
    """
    if type(candidate)is not bool:raise ValueError('explicit_native_endpoint_required')
    received=receive(source,child,proposal,board_hint=board_hint,
                     assembly_instance=assembly_instance,timeout_s=timeout_s)
    if received.get('ok')is not True or received.get('complete')is not True:
        raise ValueError('fresh_typed_print_transition_required')
    import cec_received_private_stage as stage
    import cec_force_current as force
    context=producer.get('native_library_context',{})
    expected=received['new_library_context'if candidate else'old_library_context']
    endpoint=Path(child if candidate else source).resolve(strict=True)
    command=producer.get('command',[])
    if (producer.get('ok')is not True or producer.get('complete')is not True
            or producer.get('source_and_producer_unchanged')is not True
            or not command or command[-1]!=str(endpoint)
            or producer.get('source_files',{}).get(str(endpoint))!=force._hash(endpoint)
            or context.get('bound')is not True or context.get('source_and_context_unchanged')is not True
            or stage.stable(context.get('authority'))!=expected):
        raise ValueError('native_context_differs_from_typed_print_transition')
    return True
