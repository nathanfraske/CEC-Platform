"""Bounded composition of disjoint, fixed-boundary measurement-lead miters.

Every step is independently received by the existing native single-owner
finisher. Original-source leaves and final leaves are then rederived, their
boundaries remain literal and fixed, and the whole saved delta is checked.
The separate whole-parent evidence receiver replays absolute clipped cuts;
local composition never supplies current, Kelvin, placement or fab authority.
"""
import copy
import json
import math
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_measurement_leaf as leaf
import cec_measurement_leaf_evidence as evidence
import cec_measurement_leaf_finish as finish

FIELDS=('pad_uuid','owner','pin','net','layer','width_nm','boundary_uuids','track_uuids','points_nm')


def _specs(steps,timeout_s):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(steps) not in (list,tuple) or not 1<=len(steps)<=8):
        raise ValueError('bounded_disjoint_measurement_cohort_required')
    roots=[]
    for step in steps:
        if (type(step) is not dict or set(step)!={'source','candidate','pad_uuids'}
                or any(type(step[k]) is not str or not step[k] for k in ('source','candidate'))
                or type(step['pad_uuids']) is not list or not 1<=len(step['pad_uuids'])<=4
                or any(type(u) is not str or not u for u in step['pad_uuids'])):
            raise ValueError('exact_native_single_owner_measurement_step_required')
        roots.extend(step['pad_uuids'])
    if len(roots)>16 or len(set(roots))!=len(roots):
        raise ValueError('unique_original_measurement_roots_required')
    return roots


def _same_leaf(first,last):
    return all(first.get(k)==last.get(k) for k in FIELDS)


def _settings(root,nodes):
    # _nodes returns the COMPLETE syntax root as well as its UUID index.
    # Exclude only those indexed objects here: their exact retained/added/
    # retired comparison is performed separately, including every zone,
    # group and footprint. Unknown non-UUID settings stay in this header.
    indexed={id(node) for node in nodes.values()}
    return syntax._freeze([node for node in root if id(node) not in indexed])


def _disjoint_scope(source_leaves,new_leaves):
    if (not source_leaves or len(source_leaves)!=len(new_leaves) or len(source_leaves)>16
            or len({q['pad_uuid'] for q in source_leaves})!=len(source_leaves)):
        raise ValueError('unique_complete_original_measurement_leaf_inventory_required')
    retired=[u for q in source_leaves for u in q['track_uuids']]
    added=[u for q in new_leaves for u in q['track_uuids']]
    fixed={u for q in source_leaves for u in q['boundary_uuids']}
    if (len(retired)!=len(set(retired)) or len(added)!=len(set(added))
            or set(retired)&set(added) or fixed&set(retired) or len(retired)>256 or len(added)>512):
        raise ValueError('disjoint_original_leaves_and_immutable_native_boundaries_required')
    for first,last in zip(source_leaves,new_leaves):
        if any(first[k]!=last[k] for k in ('pad_uuid','owner','pin','net','layer','width_nm','boundary_uuids')):
            raise ValueError('cohort_cannot_change_input_role_width_face_or_fixed_contact')
    return set(retired),set(added)


def _rebind_path(first,last,original,replacement):
    # A native cut can seed the measurement conductor itself. Its reported
    # path then consists of the WHOLE owned run and the literal input land,
    # with no retained prefix node. Independent saved cohort receiving has
    # already proved the same fixed endpoint/width/face and exact delta;
    # _rebind_reports additionally requires BOTH absolute clipped-cut passes
    # and the unchanged strict comparison of all other native metadata.
    # Never accept a partial run, a changed unowned prefix, or a caller flag.
    fields=('pad_uuid','owner','pin','net','layer','width_nm','boundary_uuids')
    if any(original.get(k)!=replacement.get(k) for k in fields):
        raise ValueError('measurement_cut_seed_terminal_boundary_role_or_dimension_changed')
    old,new=original['track_uuids'],replacement['track_uuids'];root=original['pad_uuid']
    if (type(first) is list and type(last) is list and type(old) is list and type(new) is list
            and 1<=len(old)<=16 and 1<=len(new)<=32 and len(set(old))==len(old) and len(set(new))==len(new)
            and all(type(u) is str and u for u in [*first,*last,*old,*new])
            and first==[*reversed(old),root] and last==[*reversed(new),root]
            and len(set(first))==len(first) and len(set(last))==len(last)):
        return list(first)
    return evidence._rebind_path(first,last,original,replacement)


def receive(source,candidate,*,board_hint,steps,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],steps=[],retired_via_uuids=[],
        current_authority=False,kelvin_qualified=False,pair_qualified=False,placement_authority=False,
        routing_admitted=False,fab_ready=False,release_authority=False)
    try:
        roots=_specs(steps,timeout_s)
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate));epoch=force._code_identity()
        paths={source,candidate,*[Path(q[k]).resolve() for q in steps for k in ('source','candidate')]}
        families={str(p):force._family(p,board_hint) for p in paths}
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        original={u:leaf.plan(parent,u) for u in roots};final={u:leaf.plan(child,u) for u in roots}
        cursor=source;all_old=[];all_new=[];progress=[]
        for spec in steps:
            first,last=[Path(spec[k]).resolve() for k in ('source','candidate')]
            if first!=cursor or first==last or last==source:
                raise ValueError('literal_ordered_measurement_source_chain_required')
            proof=finish.receive(first,last,board_hint=board_hint,pad_uuids=spec['pad_uuids'],timeout_s=timeout_s)
            r['steps'].append(dict(source=str(first),candidate=str(last),receiving=proof))
            if not proof['ok'] or not proof['complete'] or proof['errors']:
                raise ValueError('independent_native_measurement_cohort_step_refused')
            inner=proof['independent_source_typed_leaf_receiving']
            for before,after in zip(inner['source_leaves'],inner['new_leaves']):
                uid=before['pad_uuid']
                if not _same_leaf(original[uid],before) or not _same_leaf(final[uid],after):
                    raise ValueError('measurement_step_is_not_disjoint_original_to_final_leaf')
                all_old.append(before);all_new.append(after)
            progress.extend(proof['source_owned_measurement_progress']);cursor=last
        if cursor!=candidate or len(all_old)!=len(roots):
            raise ValueError('complete_measurement_chain_must_end_at_literal_candidate')
        retired,added=_disjoint_scope(all_old,all_new)
        oldroot,old=additive._nodes(source);newroot,new=additive._nodes(candidate)
        if (old.keys()-new.keys()!=retired or new.keys()-old.keys()!=added
                or _settings(oldroot,old)!=_settings(newroot,new)
                or any(syntax._freeze(old[u])!=syntax._freeze(new[u]) for u in old.keys()&new.keys())):
            raise ValueError('whole_original_native_measurement_delta_or_unowned_material_changed')
        if epoch!=force._code_identity() or any(families[str(p)]!=force._family(p,board_hint) for p in paths):
            raise ValueError('measurement_cohort_source_candidate_chain_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source=str(source),candidate=str(candidate),
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_candidate_families_and_code_unchanged=True,source_leaves=all_old,new_leaves=all_new,
            source_owned_measurement_progress=progress,retired_track_uuids=sorted(retired),added_native_uuids=sorted(added),
            exact_force_copper_barrels_and_component_poses_preserved=True,
            original_leaf_boundaries_fixed_and_all_unowned_native_objects_exact=True,
            full_original_parent_current_reference_absolute_clipped_stack_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        r.update(ok=False,complete=False);r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def _rebind_reports(before,after,source_leaves,new_leaves):
    """Pure narrow witness transform; not a saved-board receiving predicate."""
    _disjoint_scope(source_leaves,new_leaves)
    owners={a['pad_uuid']:(a,b) for a,b in zip(source_leaves,new_leaves)}
    adjusted=copy.deepcopy(after);old_rows={};new_rows={};rebound=[];qualified={};strokes=[]
    by_exit={a['track_uuids'][-1]:(a,b) for a,b in zip(source_leaves,new_leaves)}
    def qualify(net):
        if net not in qualified:
            prior=sense.admit_changed_net(before,before,net);fresh=sense.admit_changed_net(before,after,net)
            if (not prior['ok'] or not fresh['ok'] or not prior.get('applicable') or not fresh.get('applicable')
                    or prior['expected_legs']!=fresh['expected_legs'] or prior['checked']!=fresh['checked']):
                raise ValueError('two_absolute_original_and_final_clipped_cut_passes_required')
            qualified[net]=dict(before=prior,after=fresh)
    for report,mapping in ((before,old_rows),(adjusted,new_rows)):
        for row in report['inner_departure']['details']:
            key=(row['input_ref'],row['leg'],row['net'])
            if key in mapping:raise ValueError('unique_measurement_departure_inventory_required')
            mapping[key]=row
    if old_rows.keys()!=new_rows.keys():raise ValueError('cohort_measurement_departure_inventory_changed')
    for key,left in old_rows.items():
        right=new_rows[key];old=left.get('native');new=right.get('native')
        if not isinstance(old,dict) or not isinstance(new,dict):continue
        if len(old.get('departures',[]))!=len(new.get('departures',[])):continue
        for first,last in zip(old.get('departures',[]),new.get('departures',[])):
            a,b=first.get('input_contact_paths',{}),last.get('input_contact_paths',{})
            if a.keys()!=b.keys():continue
            for root,path in a.items():
                if root not in owners or path==b[root]:continue
                original,replacement=owners[root]
                if (key[0]!=original['owner'] or key[2]!=original['net']
                        or left.get('ok') is not True or right.get('ok') is not True):
                    raise ValueError('positive_original_and_final_measurement_owner_required')
                net=original['net']
                qualify(net)
                literal_after=list(b[root])
                last['input_contact_paths'][root]=_rebind_path(path,literal_after,original,replacement)
                rebound.append(dict(input_ref=key[0],leg=key[1],net=net,pad_uuid=root,
                    before_path=list(path),after_path=literal_after,fixed_native_boundary_uuids=original['boundary_uuids'],
                    directly_seeded_complete_owned_run=path==[*reversed(original['track_uuids']),root]))
        # Reports also name the exact segment leaving the shunt cut. A
        # full-width miter can shorten the OTHER end of that received edge.
        # Rebind only its actual old/new last-leaf UUID and penultimate
        # native coordinate; the literal fixed entry point is unchanged.
        # Non-sense departures may name another explicitly received input
        # on the same cut. This never grants scope by a same-net name alone.
        for category in ('departures','non_sense_departures'):
            first_rows=old.get(category,[]);last_rows=new.get(category,[])
            if len(first_rows)!=len(last_rows):continue
            for first,last in zip(first_rows,last_rows):
                if first.get('uuid') not in by_exit or first.get('uuid')==last.get('uuid'):continue
                original,replacement=by_exit[first['uuid']]
                if (key[2]!=original['net'] or left.get('ok') is not True or right.get('ok') is not True
                        or last.get('uuid')!=replacement['track_uuids'][-1]
                        or original['points_nm'][-1]!=replacement['points_nm'][-1]):
                    raise ValueError('exact_received_fixed_entry_measurement_departure_required')
                prior=[v/1e6 for v in original['points_nm'][-2]]
                current=[v/1e6 for v in replacement['points_nm'][-2]]
                if first.get('departure_end_mm')!=prior or last.get('departure_end_mm')!=current:
                    raise ValueError('measurement_departure_end_must_match_exact_native_leaf_segment')
                qualify(original['net'])
                strokes.append(dict(input_ref=key[0],leg=key[1],net=key[2],category=category,
                    pad_uuid=original['pad_uuid'],source_uuid=first['uuid'],candidate_uuid=last['uuid'],
                    source_departure_end_mm=prior,candidate_departure_end_mm=current,
                    unchanged_native_fixed_entry_nm=original['points_nm'][-1]))
                last['uuid']=first['uuid'];last['departure_end_mm']=copy.deepcopy(first['departure_end_mm'])
    return adjusted,rebound,qualified,strokes


def receive_evidence(source,candidate,*,board_hint,steps,timeout_s=10.,sense_timeout_s=40.):
    r=dict(comparison='received_disjoint_measurement_cohort_evidence_preservation',same_evidence=False,
        comparison_complete=False,errors=[],full_kelvin_qualification=False,kelvin_isolation_qualified=None,
        release_authority=False)
    try:
        _specs(steps,timeout_s)
        if type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s) or not 0<sense_timeout_s<=40:
            raise ValueError('bounded_absolute_measurement_cohort_evidence_lease_required')
        epoch=force._code_identity();paths=[Path(p).resolve() for p in (source,candidate)]
        families=[force._family(p,board_hint) for p in paths]
        proof=receive(*paths,board_hint=board_hint,steps=steps,timeout_s=timeout_s)
        r['independent_original_source_cohort_receiving']=proof
        if not proof['ok'] or not proof['complete']:raise ValueError('complete_saved_measurement_cohort_required')
        before,after=[sense.replay(p,board_hint=board_hint,timeout_s=sense_timeout_s) for p in paths]
        if not all(q['complete'] and q['identity_stable'] for q in (before,after)):
            raise ValueError('complete_absolute_original_and_final_measurement_reports_required')
        boards=[pcbnew.LoadBoard(str(p)) for p in paths]
        nets=sorted({q['net'] for q in proof['source_leaves']})
        transforms=sense.native_copper_transform_inventory(*boards,modified_nets=nets)
        adjusted,rebound,qualified,strokes=_rebind_reports(before,after,proof['source_leaves'],proof['new_leaves'])
        preserved=sense.compare_contour_preservation(before,adjusted,modified_nets=nets,native_copper_transforms=transforms)
        r.update(preservation=preserved,input_path_witnesses_rebound=rebound,qualified_changed_nets=qualified,
            exact_native_departure_stroke_witnesses_rebound=strokes,
            same_evidence=preserved['same_evidence'],comparison_complete=preserved['comparison_complete'],
            coverage_after={k:after['clipped_isolation'][k] for k in ('ok','status','expected','checked','passed','failed','unknown','unresolved_inputs')},
            raw_source_and_candidate_reports_not_modified_or_replaced=True)
        if not r['same_evidence'] or not r['comparison_complete']:raise ValueError('unreceived_cohort_measurement_evidence_difference')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('measurement_cohort_evidence_source_candidate_or_code_changed')
        r.update(code_identity=epoch,source_candidate_families_and_code_unchanged=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        r.update(same_evidence=False,comparison_complete=False);r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def run(source,directory,*,board_hint,max_steps=8,max_trials_per_step=8):
    if type(max_steps) is not int or not 1<=max_steps<=8:
        raise ValueError('bounded_measurement_cohort_step_count_required')
    source,directory=map(lambda p:Path(p).resolve(),(source,directory))
    force._check_proposal_directory(directory,force._protected_paths(source,board_hint))
    if directory.exists():raise ValueError('fresh_measurement_cohort_directory_required')
    directory.mkdir(parents=True);epoch=force._code_identity();family=force._family(source,board_hint)
    cursor=source;steps=[];stages=[];roots=set();stop='finite_step_limit_not_no_path_proof'
    for index in range(max_steps):
        stage=finish.run(cursor,directory/('step-'+str(index)),board_hint=board_hint,max_trials=max_trials_per_step)
        stages.append(str(directory/('step-'+str(index))/'receipt.json'))
        if not stage['changed']:
            stop='no_remaining_inventory' if not stage['inventory']['owners'] else 'finite_native_trial_no_offer_not_no_path_proof';break
        ids=stage['records'][0]['plan']['pad_uuids']
        if roots&set(ids):raise ValueError('measurement_cohort_cannot_revisit_an_original_root')
        roots.update(ids);steps.append(dict(source=str(cursor),candidate=stage['candidate'],pad_uuids=ids));cursor=Path(stage['candidate'])
    r=dict(ok=True,complete=True,changed=False,source=str(source),source_sha256=force._hash(source),
        candidate=str(cursor) if steps else None,code_identity=epoch,step_receipts=stages,steps=steps,
        finite_stop_reason=stop,records=[],source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    if steps:
        proof=receive(source,cursor,board_hint=board_hint,steps=steps)
        r.update(ok=proof['ok'],complete=proof['complete'],changed=proof['ok'],errors=proof['errors'],
            candidate_sha256=force._hash(cursor),independent_original_source_receiving=proof,
            records=[dict(plan=dict(steps=steps),materialized=dict(retired_track_uuids=proof.get('retired_track_uuids',[]),
                added_native_uuids=proof.get('added_native_uuids',[])))])
    if epoch!=force._code_identity() or family!=force._family(source,board_hint):raise ValueError('measurement_cohort_changed_source_or_code')
    r['source_family_and_code_unchanged']=True;force._write(directory/'receipt.json',r);return r
