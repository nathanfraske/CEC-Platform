"""Receive changed input-path UUID witnesses for exact typed leaf reflows.

Raw physical reports are never rewritten or treated as interchangeable. Only
a full, ordered native leaf run between the SAME retained junction and input
land can be rebound, after independent saved leaf receiving and absolute
before/after clipped-cut admission. Every other evidence field stays strict.
"""
import copy,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_local_branch_access as access


def _rebind_path(first,last,original,replacement):
    fields=('pad_uuid','owner','pin','net','layer','width_nm','boundary_uuids')
    if any(original.get(k)!=replacement.get(k) for k in fields):
        raise ValueError('measurement_path_terminal_boundary_role_width_or_face_changed')
    root=original['pad_uuid'];old=original['track_uuids'];new=replacement['track_uuids']
    def parts(path,owned):
        if (type(path) is not list or not 3<=len(path)<=1024
                or type(owned) is not list or not 1<=len(owned)<=16
                or any(type(v) is not str or not v for v in [*path,*owned])
                or len(set(path))!=len(path) or len(set(owned))!=len(owned)):
            raise ValueError('bounded_unique_native_measurement_path_required')
        at=[i for i,v in enumerate(path) if v in set(owned)]
        if (len(at)!=len(owned) or at!=list(range(at[0],at[-1]+1))
                or path[at[0]:at[-1]+1]!=list(reversed(owned))):
            raise ValueError('complete_ordered_native_measurement_leaf_run_required')
        prefix,suffix=path[:at[0]],path[at[-1]+1:]
        if not prefix or prefix[-1] not in original['boundary_uuids'] or suffix!=[root]:
            raise ValueError('literal_retained_junction_and_input_land_required')
        return prefix,suffix
    if parts(first,old)!=parts(last,new):raise ValueError('unowned_native_measurement_path_context_changed')
    return list(first)


def receive(source,candidate,*,board_hint,pad_uuids,timeout_s=10.,sense_timeout_s=40.):
    r=dict(schema=1,comparison='received_stationary_measurement_leaf_evidence_preservation',
        same_evidence=False,comparison_complete=False,errors=[],input_path_witnesses_rebound=[],
        full_kelvin_qualification=False,kelvin_isolation_qualified=None,release_authority=False)
    try:
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
            raise ValueError('bounded_received_measurement_path_lease_required')
        if type(sense_timeout_s) not in (int,float) or not math.isfinite(sense_timeout_s) or not 0<sense_timeout_s<=40:
            raise ValueError('unchanged_absolute_measurement_evidence_lease_required')
        paths=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in paths]
        proof=access.receive(*paths,board_hint=board_hint,pad_uuids=pad_uuids,
            timeout_s=timeout_s,_construction_role='measurement_leaf_reflow')
        r['independent_stationary_measurement_reflow_receiving']=proof
        if not proof['ok'] or not proof['complete']:
            raise ValueError('exact_saved_stationary_measurement_reflow_required')
        before,after=[sense.replay(p,board_hint=board_hint,timeout_s=sense_timeout_s) for p in paths]
        if not all(p['complete'] and p['identity_stable'] for p in (before,after)):
            raise ValueError('complete_current_saved_absolute_measurement_reports_required')
        owners={a['pad_uuid']:(a,b) for a,b in zip(proof['source_leaves'],proof['new_leaves'])}
        if len(owners)!=len(proof['source_leaves']):raise ValueError('unique_received_measurement_leaf_roots_required')
        nets=sorted({q['net'] for q,_ in owners.values()})
        boards=[pcbnew.LoadBoard(str(p)) for p in paths]
        transforms=sense.native_copper_transform_inventory(*boards,modified_nets=nets)
        default=sense.compare_contour_preservation(before,after,modified_nets=nets,native_copper_transforms=transforms)
        r['unchanged_default_strict_comparison']=default
        adjusted=copy.deepcopy(after);old_rows={};new_rows={}
        for report,mapping in ((before,old_rows),(adjusted,new_rows)):
            for row in report['inner_departure']['details']:
                key=(row['input_ref'],row['leg'],row['net'])
                if key in mapping:raise ValueError('unique_measurement_inner_departure_rows_required')
                mapping[key]=row
        if old_rows.keys()!=new_rows.keys():raise ValueError('measurement_departure_inventory_changed')
        qualified={}
        for key,oldrow in old_rows.items():
            newrow=new_rows[key];oldnative=oldrow.get('native');newnative=newrow.get('native')
            if not isinstance(oldnative,dict) or not isinstance(newnative,dict):continue
            olddeps=oldnative.get('departures',[]);newdeps=newnative.get('departures',[])
            if len(olddeps)!=len(newdeps):continue  # Strict comparator must reject it below.
            for index,(left,right) in enumerate(zip(olddeps,newdeps)):
                first=left.get('input_contact_paths',{});last=right.get('input_contact_paths',{})
                if first.keys()!=last.keys():continue
                for root,original_path in first.items():
                    if original_path==last[root] or root not in owners:continue
                    original,replacement=owners[root]
                    if (key[0]!=original['owner'] or key[2]!=original['net']
                            or oldrow.get('ok') is not True or newrow.get('ok') is not True):
                        raise ValueError('positive_exact_measurement_departure_owner_required')
                    net=original['net']
                    if net not in qualified:
                        prior=sense.admit_changed_net(before,before,net);fresh=sense.admit_changed_net(before,after,net)
                        if (not prior['ok'] or not fresh['ok'] or not prior.get('applicable') or not fresh.get('applicable')
                                or prior['expected_legs']!=fresh['expected_legs'] or prior['checked']!=fresh['checked']):
                            raise ValueError('both_absolute_clipped_measurement_cut_passes_required')
                        qualified[net]=dict(before=prior,after=fresh)
                    rebound=_rebind_path(original_path,last[root],original,replacement)
                    r['input_path_witnesses_rebound'].append(dict(input_ref=key[0],leg=key[1],net=net,pad_uuid=root,
                        before_path=original_path,after_path=list(last[root]),
                        fixed_native_boundary_uuids=original['boundary_uuids'],
                        source_track_uuids=original['track_uuids'],candidate_track_uuids=replacement['track_uuids'],
                        basis='exact_received_leaf_run_and_two_absolute_clipped_cut_passes'))
                    right['input_contact_paths'][root]=rebound
        preserved=sense.compare_contour_preservation(before,adjusted,modified_nets=nets,native_copper_transforms=transforms)
        r.update(preservation=preserved,comparison_complete=preserved['comparison_complete'],
            same_evidence=preserved['same_evidence'],qualified_changed_nets=qualified,
            coverage_after={k:after['clipped_isolation'][k] for k in ('ok','status','expected','checked','passed','failed','unknown','unresolved_inputs')},
            raw_source_and_candidate_reports_not_modified_or_replaced=True)
        if not r['same_evidence'] or not r['comparison_complete']:raise ValueError('unreceived_measurement_evidence_difference_remains')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('measurement_evidence_source_candidate_or_code_changed')
        r.update(code_identity=epoch,source=str(paths[0]),candidate=str(paths[1]),
            source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[1]),
            source_candidate_families_and_code_unchanged=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        r.update(same_evidence=False,comparison_complete=False)
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
