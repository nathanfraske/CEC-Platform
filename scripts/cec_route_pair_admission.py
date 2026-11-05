"""Independent route-owned pair replacement; additive guards stay strict.

One complete qualified pair may be reconstructed to recover a native-proven
non-pair pin column. Neither locked power nor ordinary local-repair budgets
are relaxed. Every source item outside that exact pair remains immutable.
The result is a route-progress transaction, never fabrication approval.
"""
import copy
import json
from pathlib import Path


def pair_only_failure(proof):
    return bool(proof.get('ok') is False
        and proof.get('parent_copper',{}).get('ok') is False
        and proof.get('functional_placement_unchanged') is True
        and proof.get('placement_unchanged') is True
        and proof.get('outline_unchanged') is True
        and proof.get('power_zones_unchanged') is True
        and proof.get('qualified_pairs',{}).get('ok') is True
        and proof.get('power_obligations',{}).get('ok') is True
        and proof.get('score_admission',{}).get('accepted') is True)


def changed_pair_scope(before, after, contract, *, max_pair_items=256):
    """Classify a bounded complete qualified pair, never arbitrary locked nets."""
    import cec_priority_dependency as dependency
    if type(max_pair_items) is not int or not 1 <= max_pair_items <= 4096:
        raise ValueError('pair inventory limit must be bounded')
    changed = {uid for uid,row in before.items() if after.get(uid)!=row}
    if not 1 <= len(changed) <= max_pair_items:
        return dict(ok=False,reason='outside_bounded_pair_replacement')
    scope = dependency.pair_scope_plan(contract,{before[uid][1] for uid in changed},(),max_pairs=1)
    if not scope['ok']:
        return scope
    owned = {uid for uid,row in before.items() if row[1] in scope['nets']}
    if len(owned)>max_pair_items:
        return dict(ok=False,reason='complete_pair_exceeds_inventory_limit')
    # UUID reuse cannot turn a signal pair item into an unrelated conductor.
    if any(uid in after and after[uid][1] != before[uid][1] for uid in owned):
        return dict(ok=False,reason='pair_item_net_identity_changed')
    return dict(scope,changed_parent_uuids=sorted(changed),owned_parent_uuids=sorted(owned))


def _frozen_state(path):
    import cec_full_pipeline as pipeline
    state_path=Path(path).with_suffix('.pourfirst-state.json')
    if not state_path.is_file():
        return None
    state=json.loads(state_path.read_text())
    skeleton=Path(state.pop('skeleton'))
    if not skeleton.is_absolute():
        skeleton=state_path.parent/skeleton
    state['skeleton_sha256']=pipeline.sha256_file(skeleton)
    return state


def _native_prepare(source,candidate,output_dir,cfg,*,max_pair_items=256):
    import pcbnew
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    import cec_route_checkpoint as checkpoint
    import cec_route_placement_admission as placement
    import cec_placement_route_prefix as prefix
    import cec_priority_replacement_receipt as receipt
    import cec_future_pin_access as access
    import cec_local_copper_cell as copper
    import cec_frozen_pour_void as fills
    import cec_fr
    import cec_staged_fr as staged

    source,candidate,output_dir=map(lambda p:Path(p).resolve(),(source,candidate,output_dir))
    if source==candidate or output_dir.exists():
        raise ValueError('pair revalidation requires a new private artifact family')
    output_dir.mkdir(parents=True)
    inputs=pipeline._artifact_rows(p for board in (source,candidate)
        for p in pipeline._placement_authority_family(board) if p.is_file())
    result=dict(schema=1,ok=False,release_authority=False,
        source_sha256=pipeline.sha256_file(source),proposed_sha256=pipeline.sha256_file(candidate))
    def refuse(reason):
        result['reason']=reason
        return result
    try:
        bound,binding=synth.config_with_board_route_authority(cfg,str(candidate))
        result['authority_binding']=binding
        with synth._oracle_env(bound.params):
            proof=checkpoint.preservation(source,candidate,bound)
            result['additive_checkpoint']=proof
            if not pair_only_failure(proof):
                return refuse('not_an_isolated_pair_transition')
            counts=proof['score_admission']
            recovered=set(counts['before']['unconn_nets'])-set(counts['after']['unconn_nets'])
            if (not recovered or counts['after']['unconnected']>=counts['before']['unconnected']
                    or counts['after']['drc']!=0):
                return refuse('no_strict_native_connectivity_gain')
            if (placement._project_policy(source.with_suffix('.kicad_pro'))!=
                    placement._project_policy(candidate.with_suffix('.kicad_pro'))
                    or source.with_suffix('.kicad_dru').read_bytes()!=candidate.with_suffix('.kicad_dru').read_bytes()):
                return refuse('design_rule_authority_changed')
            first,last=pcbnew.LoadBoard(str(source)),pcbnew.LoadBoard(str(candidate))
            if placement._population(first)!=placement._population(last):
                return refuse('component_or_pad_definition_changed')
            a,b=copper.copper_inventory(first),copper.copper_inventory(last)
            original=prefix.capture(str(source))
            scope=changed_pair_scope(a,b,original,max_pair_items=max_pair_items)
            result['pair_scope']=scope
            if not scope['ok']:
                return refuse(scope['reason'])
            witness=access.replacement_witness(source,original,scope['pairs'][0],recovered,
                max_pair_items=max_pair_items)
            result['native_access_witness']=witness
            if not witness['ok'] or set(witness['scope']['nets'])!=set(scope['nets']):
                return refuse('pair_owned_pin_obstruction_not_reproduced')
            nets=set(witness['target_nets'])
            connected,unused=staged.fully_connected_nets(last,nets)
            if not nets<=connected:
                return refuse('recovered_pin_net_not_fully_connected')
            # Native connectivity must not silently relabel the saved copper.
            if copper.copper_inventory(last)!=b:
                return refuse('native_connectivity_relabelled_copper')
            additions={uid:row for uid,row in b.items() if uid not in a}
            returns={item.m_Uuid.AsString() for group in last.Groups()
                if group.GetName()==cec_fr.LOCAL_PAIR_RETURN_VIA_GROUP for item in group.GetItems()}
            if any(row[1] not in set(scope['nets'])|nets
                    and not (row[0]=='PCB_VIA' and row[1]=='GND' and uid in returns)
                    for uid,row in additions.items()):
                return refuse('unrelated_generated_copper')
            result['protected_fill']=fills.preservation(fills.capture(first),last)
            if not result['protected_fill']['ok']:
                return refuse('protected_power_fill_changed')
            if _frozen_state(source)!=_frozen_state(candidate):
                return refuse('frozen_power_plan_changed')
            result['placement_contract']=pipeline._frozen_placement_contract(candidate)
            if not binding.get('ok') or not result['placement_contract'].get('ok'):
                return refuse('frozen_placement_authority_invalid')
            physical=pipeline._measure_placement_physical_in_process(bound,str(candidate))
            result['physical_placement']=physical
            if not physical.get('ok'):
                return refuse('full_physical_placement_refused')
            retained=cec_fr.check_copper_geometry_prefix(str(candidate),scope['retained_contract'])
            qualified=prefix.check_qualified_pairs(str(candidate),original)
            native_proof=dict(ok=bool(retained['ok'] and qualified['ok']),constructed=True,
                released_nets=scope['nets'],retained_prefix=retained,all_original_pairs=qualified,
                placement_unchanged=proof['placement_unchanged'],physical_ok=True,
                authority=dict(ok=bool(binding.get('ok') and proof['power_obligations']['ok'])))
            result['reconstruction_proof']=native_proof
            if not native_proof['ok']:
                return refuse('independent_pair_or_prefix_refused')
            target=output_dir/'board.kicad_pcb'
            pipeline._copy_sidecars(candidate,target,cfg=bound)
            sealed=receipt.issue(original,scope,native_proof,target,source_board_sha256=result['source_sha256'])
            result['replacement_receipt']=receipt.stage(source,target,sealed)
            if pipeline.sha256_file(target)!=result['proposed_sha256']:
                return refuse('pair_revalidation_mutated_board')
            result.update(ok=True,reason='owned_pair_access_revalidated',board=str(target),
                recovered_nets=sorted(nets),authority_transition='revalidated_owned_pair_access')
            return result
    except Exception as exc:
        result['error']='%s: %s'%(type(exc).__name__,str(exc)[:1000])
        return refuse('pair_revalidation_error')
    finally:
        result['input_families_unchanged']=pipeline.artifacts_match(inputs)
        if not result['input_families_unchanged']:
            result.update(ok=False,reason='input_family_changed')
        pipeline.atomic_json(output_dir/'revalidation.json',result)


def prepare(source,candidate,output_dir,cfg,*,timeout_s=90,max_pair_items=256):
    import cec_certificate_repair as repair
    from functools import partial
    return repair._spawn_apply(partial(_native_prepare,max_pair_items=max_pair_items),
        (str(source),str(candidate),str(output_dir),copy.deepcopy(cfg)),timeout_s=timeout_s)
