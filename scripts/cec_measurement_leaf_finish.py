"""Full-width 45-degree finishing of manufacturer-typed measurement leaves.

Source pin roles and exact native leaf ownership, not a net's power-like name,
own this scope. No pad, pose, via, force bus, pickup aperture or load changes.
The existing independent leaf receiver owns subtraction/contact restoration;
whole-parent current, pair/reference and clipped-Kelvin receiving remain due.
"""
import json,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_device_power_roles as roles
import cec_measurement_leaf as leaf
import cec_local_branch_access as access
import cec_field_coupling as field
import cec_octilinear_corner as corners
from cec_native_items import discard_items

RETREATS_NM=(200000,150000)
MINIMUM_VISIBLE_FLAT_NM=20000


def right_angles(points):
    return sum(corners.kind(tuple(a[i]-b[i] for i in (0,1)),tuple(c[i]-b[i] for i in (0,1))) is not None
        for a,b,c in zip(points,points[1:],points[2:]))


def paths(proposal):
    """Finite source-corner alternatives, never cut or current authority."""
    points=proposal.get('points_nm');width=proposal.get('width_nm')
    if (proposal.get('scope')!='source_typed_thin_measurement_leaf'
            or type(points) not in (list,tuple) or not 2<=len(points)<=17
            or any(type(p) not in (list,tuple) or len(p)!=2 or any(type(v) is not int or abs(v)>2000000000 for v in p) for p in points)
            or type(width) is not int or not 0<width<=350000):
        raise ValueError('bounded_typed_measurement_corner_polyline_required')
    points=[tuple(p) for p in points]
    if any(a==b for a,b in zip(points,points[1:])):raise ValueError('nonempty_measurement_corner_source_edges_required')
    result=[];seen=set()
    for maximum in RETREATS_NM:
        out=[points[0]];count=0
        for a,b,c in zip(points,points[1:],points[2:]):
            u=tuple(a[i]-b[i] for i in (0,1));v=tuple(c[i]-b[i] for i in (0,1))
            step=corners.coordinate_inset(u,v,maximum_nm=maximum,minimum_nm=50000)
            scale=2 if corners.kind(u,v)=='diagonal' else 1
            # The source's full stroke width, not its centreline, must show
            # at least 20 um of real inner flat. An invisible micro-miter is
            # not progress toward removing the old native copper elbow.
            needed=width+math.isqrt(2*MINIMUM_VISIBLE_FLAT_NM**2)+1
            if step and 4*step*step*scale>=needed*needed:
                out.extend(tuple(b[i]+(1 if x[i]>0 else -1 if x[i]<0 else 0)*step for i in (0,1)) for x in (u,v));count+=1
            else:out.append(b)
        out.append(points[-1]);key=tuple(out)
        if count and key not in seen:
            seen.add(key);result.append(dict(points_nm=[list(p) for p in out],visible_source_corners=count,
                maximum_retreat_nm=maximum,minimum_full_width_inner_flat_nm=MINIMUM_VISIBLE_FLAT_NM))
    return result


def inventory(board,*,timeout_s=10.,max_owners=16):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(max_owners) is not int or not 1<=max_owners<=16):
        raise ValueError('bounded_measurement_finishing_inventory_required')
    deadline=time.monotonic()+timeout_s;binding=leaf._binding(board);owners=[];refusals=[]
    for fp in board.GetFootprints():
        if time.monotonic()>=deadline:raise ValueError('measurement_finishing_inventory_deadline')
        model=roles.footprint_contract(fp)
        if fp.IsDNP() or not model:continue
        selected=[]
        for pad in fp.Pads():
            if model['pins'].get(str(pad.GetNumber()))!='measurement':continue
            try:
                q=leaf.plan(board,force._uid(pad),timeout_s=max(.001,deadline-time.monotonic()))
                choices=paths(q)
                if choices:selected.append(dict(source=q,choices=choices))
            except ValueError as exc:refusals.append(dict(pad_uuid=force._uid(pad),reason=str(exc)))
        if selected:
            if len(selected)>4:raise ValueError('four_disjoint_same_owner_measurement_leaves_required')
            owners.append(dict(owner=fp.GetReference(),leaves=selected))
    owners.sort(key=lambda q:(-sum(v['choices'][0]['visible_source_corners'] for v in q['leaves']),q['owner']))
    if binding!=leaf._binding(board):raise ValueError('measurement_finishing_inventory_changed_source')
    return dict(owners=owners[:max_owners],refusals=refusals,source_native_binding=binding,
        finite_inventory_not_exhaustive_no_path_proof=len(owners)>max_owners)


def receive(source,candidate,*,board_hint,pad_uuids,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],current_authority=False,kelvin_qualified=False,
        pair_qualified=False,placement_authority=False,routing_admitted=False,fab_ready=False,release_authority=False)
    try:
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.:
            raise ValueError('bounded_measurement_finishing_receiving_lease_required')
        if (type(pad_uuids) not in (list,tuple) or not 1<=len(pad_uuids)<=4
                or len(set(pad_uuids))!=len(pad_uuids) or any(type(u) is not str or not u for u in pad_uuids)):
            raise ValueError('unique_actual_measurement_finishing_lands_required')
        paths0=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in paths0]
        proof=access.receive(*paths0,board_hint=board_hint,pad_uuids=list(pad_uuids),
            timeout_s=timeout_s,_construction_role='measurement_leaf_reflow')
        r['independent_source_typed_leaf_receiving']=proof
        if not proof['ok'] or not proof['complete']:raise ValueError('measurement_finish_exact_leaf_receiving_refused')
        # Use the native reference-deficit receiver on the ACTUAL owned
        # measurement strokes. A force-net name must not expand this query
        # to an unrelated wide bus, nor hide a new gap under a short miter.
        import cec_pair_local_reference_refinement as reference
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths0]
        original_ids={u for q in proof['source_leaves'] for u in q['track_uuids']}
        final_ids={u for q in proof['new_leaves'] for u in q['track_uuids']}
        old=[t for t in parent.GetTracks() if force._uid(t) in original_ids]
        new=[t for t in child.GetTracks() if force._uid(t) in final_ids]
        references=[]
        for face in sorted({int(t.GetLayer()) for t in old}):
            references.append(reference.reference_deficit(parent,child,
                [t for t in old if int(t.GetLayer())==face],[t for t in new if int(t.GetLayer())==face],
                board_hint=board_hint,deadline=time.monotonic()+timeout_s))
        if not references or not all(q['ok'] and q['complete'] and not q['new_reference_deficit_added'] for q in references):
            raise ValueError('native_measurement_reference_preservation_required')
        r['exact_native_measurement_reference_preservation']=references
        rows=[]
        for old,new in zip(proof['source_leaves'],proof['new_leaves']):
            allowed=[p for p in paths(old) if p['points_nm']==new['points_nm']]
            if not allowed:raise ValueError('candidate_not_exact_full_width_source_corner_finishing')
            before,after=[sum(math.dist(a,b) for a,b in zip(q['points_nm'],q['points_nm'][1:])) for q in (old,new)]
            first,last=[right_angles(q['points_nm']) for q in (old,new)]
            if not first>last or not before>after:raise ValueError('measurement_finish_requires_visible_shorter_elbow_progress')
            rows.append(dict(pad_uuid=old['pad_uuid'],owner=old['owner'],pin=old['pin'],net=old['net'],
                source_right_angles=first,candidate_right_angles=last,centerline_removed_mm=(before-after)/1e6,
                source_corner_geometry=allowed[0]))
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths0]:
            raise ValueError('measurement_finish_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_candidate_and_code_unchanged=True,
            source_owned_measurement_progress=rows,retired_track_uuids=proof['retired_track_uuids'],
            added_native_uuids=proof['added_native_uuids'],retired_via_uuids=[],
            exact_force_copper_barrels_and_component_poses_preserved=True,
            full_current_pair_reference_absolute_clipped_stack_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def run(source,directory,*,board_hint,max_trials=8):
    if type(max_trials) is not int or not 1<=max_trials<=16:raise ValueError('bounded_measurement_finishing_trials_required')
    source,directory=map(lambda p:Path(p).resolve(),(source,directory))
    force._check_proposal_directory(directory,force._protected_paths(source,board_hint))
    if directory.exists():raise ValueError('fresh_measurement_finishing_directory_required')
    directory.mkdir(parents=True);epoch=force._code_identity();family=force._family(source,board_hint)
    parent=pcbnew.LoadBoard(str(source));menu=inventory(parent)
    r=dict(ok=True,complete=True,changed=False,errors=[],source=str(source),source_sha256=force._hash(source),
        candidate=None,code_identity=epoch,inventory=menu,trials=[],records=[],source_selected=False,
        routing_admitted=False,fab_ready=False,release_authority=False)
    for owner in menu['owners']:
        for maximum in RETREATS_NM:
            if len(r['trials'])>=max_trials:break
            b=pcbnew.LoadBoard(str(source));leaves=owner['leaves'];cut={u for x in leaves for u in x['source']['track_uuids']}
            discard_items(b,[t for t in b.GetTracks() if force._uid(t) in cut]);found=[];trial=dict(owner=owner['owner'],maximum_retreat_nm=maximum)
            for selected in leaves:
                choices=[x for x in selected['choices'] if x['maximum_retreat_nm']==maximum]
                detail={}
                if not choices or not leaf.path_clear(b,selected['source'],choices[0]['points_nm'],diagnostics=detail):
                    trial['refusal']=detail or 'no_full_width_visible_miter';break
                leaf.add_path(b,selected['source'],choices[0]['points_nm']);found.append(selected['source']['pad_uuid'])
            r['trials'].append(trial)
            if len(found)!=len(leaves):continue
            candidate=force._copy_family(source,directory/('UNADMITTED-measurement-corners-'+str(len(r['trials'])-1)))
            field._save_field_snapshot(b,candidate);proof=receive(source,candidate,board_hint=board_hint,pad_uuids=found)
            trial.update(candidate=str(candidate),independent_receiving=proof)
            if proof['ok'] and proof['complete']:
                r.update(changed=True,candidate=str(candidate),candidate_sha256=force._hash(candidate),records=[dict(
                    plan=dict(pad_uuids=found),materialized=dict(retired_track_uuids=proof['retired_track_uuids'],
                        added_native_uuids=proof['added_native_uuids']),independent_receiving=proof)]);break
        if r['changed'] or len(r['trials'])>=max_trials:break
    if epoch!=force._code_identity() or family!=force._family(source,board_hint):raise ValueError('measurement_finishing_changed_source_or_code')
    r['source_family_and_code_unchanged']=True;force._write(directory/'receipt.json',r);return r
