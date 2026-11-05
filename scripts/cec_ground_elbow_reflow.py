"""Source-typed local ground elbow and free-overrun reconstruction.

Only one selected non-converter device's grounded supply-return prefix is
eligible. Its exact retained endpoint, width and all other contacts survive.
This is neither mesh rip-up nor a current/thermal/plane/barrel qualification.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_strap_rebuild as straps
import cec_ordinary_route_receiving as ordinary
import cec_return_escape as surface
from cec_native_items import discard_items


def _deadline(timeout_s):
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('bounded_ground_elbow_lease_required')
    return time.monotonic()+timeout_s


def plan(board, seed_uuid, *, authorize_source_locked=False, timeout_s=10.):
    deadline=_deadline(timeout_s)
    if type(seed_uuid) is not str or not seed_uuid or type(authorize_source_locked) is not bool:
        raise ValueError('exact_ground_elbow_source_required')
    tracks=list(board.GetTracks());pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(tracks)+len(pads)+len(zones)>16384:raise ValueError('ground_elbow_inventory_bound')
    live={force._uid(t):t for t in tracks};seed=live.get(seed_uuid)
    if seed is None or seed.GetClass()!='PCB_TRACK' or seed.GetNetname()!='GND':
        raise ValueError('native_ground_elbow_track_required')
    layer=seed.GetLayer();width=seed.GetWidth();ends=[tuple(seed.GetStart()),tuple(seed.GetEnd())]
    if (not 0<width<=350000 or width!=max(board.GetDesignSettings().m_TrackMinWidth,
            int(cells._netclass(board,'GND')['width'])) or ends[0]==ends[1]):
        raise ValueError('full_class_small_ground_elbow_required')
    def touch(item,edge):
        if time.monotonic()>=deadline:raise ValueError('ground_elbow_inventory_deadline')
        if item.GetNetname()!='GND' or not item.IsOnLayer(layer):return False
        if item.GetClass()=='ZONE':
            if not item.IsFilled():raise ValueError('saved_ground_elbow_fill_required')
            shape=item.GetFilledPolysList(layer)
        else:shape=item.GetEffectiveShape(layer)
        return shape.Collide(edge.GetEffectiveShape(layer),0)
    root_lands=[p for p in pads if touch(p,seed)]
    if len(root_lands)!=1:raise ValueError('one_actual_ground_elbow_owner_land_required')
    root=root_lands[0];owner=root.GetParentFootprint();model=roles.footprint_contract(owner)
    if (owner.IsDNP() or not model or model['pins'].get(str(root.GetNumber()))!='ground'
            or set(model['pins'].values()) & {'switch','power_return','power_output'}
            or root.HasHole() or surface.smd_surface_layer(root)!=layer
            or tuple(root.GetPosition()) not in ends):
        raise ValueError('selected_nonconverter_manufacturer_ground_owner_required')
    assigned=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    selected=[r for r in assigned['assigned'].values() if r['requirement']['ref']==owner.GetReference()]
    if len(selected)!=1:raise ValueError('unique_source_selected_ground_owner_bypass_required')
    cap=board.FindFootprintByReference(selected[0]['cap_ref'])
    grounds=[p for p in cap.Pads() if p.GetNetname()=='GND'] if cap else []
    if len(grounds)!=1:raise ValueError('unique_selected_bypass_ground_land_required')
    manufacturer,role,requirement=straps._land_ownership(board,grounds[0],'selected_bypass')
    if requirement['ref']!=owner.GetReference() or surface.smd_surface_layer(grounds[0])!=layer:
        raise ValueError('ground_elbow_selected_bypass_owner_mismatch')
    original_return=cells._shortest_track_path_mm(board,root,grounds[0])
    if original_return is None or not 0<original_return<=4.:
        raise ValueError('actual_short_source_owner_bypass_return_required')
    source_contacts=[t for t in tracks if force._uid(t)!=seed_uuid and touch(t,seed)]
    if len(source_contacts)!=1 or source_contacts[0].GetClass()!='PCB_TRACK':
        raise ValueError('one_unbranched_native_elbow_continuation_required')
    second=source_contacts[0];a=tuple(root.GetPosition());tip=ends[1] if ends[0]==a else ends[0]
    vector=(tip[0]-a[0],tip[1]-a[1])
    if sum(v!=0 for v in vector)!=1:raise ValueError('orthogonal_source_ground_elbow_required')
    axis=0 if vector[0] else 1;sign=1 if vector[axis]>0 else -1
    pairs=[tuple(second.GetStart()),tuple(second.GetEnd())]
    junctions=[p for p in pairs if p[1-axis]==a[1-axis] and 0<(p[axis]-a[axis])*sign<abs(vector[axis])]
    if len(junctions)!=1:raise ValueError('actual_interior_endpoint_junction_required')
    junction=junctions[0];b=pairs[1] if pairs[0]==junction else pairs[0]
    if (b[axis]!=junction[axis] or b[1-axis]==junction[1-axis]
            or second.GetLayer()!=layer or second.GetWidth()!=width):
        raise ValueError('uniform_orthogonal_native_elbow_required')
    overrun=math.dist(junction,tip);first=math.dist(a,junction);last=math.dist(junction,b)
    if not 0<overrun<=350000 or not width<=last<=500000 or first<=last or first+last>4000000:
        raise ValueError('small_free_overrun_and_bounded_elbow_required')
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    for t in (seed,second):
        if (force._uid(t) in grouped or t.GetParentGroup() is not None
                or t.IsLocked() and not authorize_source_locked):
            raise ValueError('ground_elbow_source_group_or_lock_not_authorized')
    own={seed_uuid,force._uid(second)}
    extra=[p for p in pads if touch(p,second)]
    if extra or any(touch(z,seed) or touch(z,second) for z in zones):
        raise ValueError('ground_elbow_has_other_land_or_surface_plane_contact')
    retained=[t for t in tracks if force._uid(t) not in own and touch(t,second)]
    if (len(retained)!=1 or retained[0].GetClass()!='PCB_TRACK'
            or b not in (tuple(retained[0].GetStart()),tuple(retained[0].GetEnd()))):
        raise ValueError('one_exact_retained_ground_elbow_endpoint_required')
    # The retained trace must not touch any material being removed anywhere
    # except its exact terminal kernel; a hidden tee is not an elbow.
    if touch(retained[0],seed):raise ValueError('ground_elbow_hidden_retained_contact')
    corner=list(junction);corner[axis]-=sign*round(last)
    points=[list(a),corner,list(b)]
    return dict(schema=1,seed_uuid=seed_uuid,retired_track_uuids=sorted(own),
        authorize_source_locked=authorize_source_locked,source_width_nm=width,source_layer=int(layer),
        owner_pad_uuid=force._uid(root),selected_cap_ground_uuid=force._uid(grounds[0]),
        selected_requirement=requirement,manufacturer_source=manufacturer,
        retained_track_uuid=force._uid(retained[0]),retained_endpoint_nm=list(b),
        source_overrun_nm=overrun,source_functional_prefix_nm=first+last,
        source_owner_bypass_mm=original_return,replacement_points_nm=points,
        source_binding=field._field_snapshot_inventory(board),current_qualified=False,release_authority=False)


def subtract(board, proposal):
    if plan(board,proposal['seed_uuid'],authorize_source_locked=proposal['authorize_source_locked'])!=proposal:
        raise ValueError('ground_elbow_source_proposal_stale_or_forged')
    discard_items(board,[t for t in board.GetTracks() if force._uid(t) in proposal['retired_track_uuids']])


def _no_new_ground_contacts(board,proposal,tracks,*,deadline):
    allowed={proposal['owner_pad_uuid'],proposal['retained_track_uuid']}
    added={force._uid(t) for t in tracks};layer=proposal['source_layer']
    material=[*(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks(),
        *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    for t in tracks:
        for item in material:
            if time.monotonic()>=deadline:raise ValueError('ground_elbow_contact_guard_deadline')
            if force._uid(item) in allowed|added or item.GetNetname()!='GND' or not item.IsOnLayer(layer):continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled():raise ValueError('ground_elbow_new_ground_fill_unknown')
                shape=item.GetFilledPolysList(layer)
            else:shape=item.GetEffectiveShape(layer)
            if shape.Collide(t.GetEffectiveShape(layer),0):
                raise ValueError('ground_elbow_new_unowned_ground_contact')


def materialize(board, proposal):
    subtract(board,proposal);points=proposal['replacement_points_nm'];gap=max(
        board.GetDesignSettings().m_MinClearance,int(cells._netclass(board,'GND')['clearance']))
    code=board.GetNetcodeFromNetname('GND');cache={};added=[]
    for a,b in zip(points,points[1:]):
        a,b=pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b)
        if (not fr._edge_leg_clear(board,a,b,math.ceil(proposal['source_width_nm']/2))
                or not fr._tap_foreign_clear(board,a,b,proposal['source_width_nm'],
                    proposal['source_layer'],gap,{code},foreign_cache=cache)):
            raise ValueError('new_ground_elbow_native_source_guard_refused')
        t=pcbnew.PCB_TRACK(board);t.SetStart(a);t.SetEnd(b);t.SetWidth(proposal['source_width_nm'])
        t.SetLayer(proposal['source_layer']);t.SetNetCode(code);t.SetLocked(True);board.Add(t)
        added.append(force._uid(t))
    _no_new_ground_contacts(board,proposal,[t for t in board.GetTracks() if force._uid(t) in added],
        deadline=time.monotonic()+10.)
    return added


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    r=dict(schema=1,ok=False,complete=False,errors=[],current_qualified=False,
        inherited_debt_qualified=False,release_authority=False,full_saved_board_receiving_still_required=True)
    try:
        deadline=_deadline(timeout_s);paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1]:raise ValueError('distinct_saved_ground_elbow_candidates_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        fresh=plan(parent,proposal['seed_uuid'],authorize_source_locked=proposal['authorize_source_locked'])
        if fresh!=proposal:raise ValueError('ground_elbow_source_proposal_stale_or_forged')
        retired=set(proposal['retired_track_uuids']);_,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        incoming=new.keys()-old.keys()
        if old.keys()-new.keys()!=retired or len(incoming)!=2:
            raise ValueError('exact_two_track_ground_elbow_delta_required')
        actual={force._uid(t):t for t in child.GetTracks()};tracks=[actual[u] for u in incoming if u in actual]
        geometry=lambda t:(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),int(t.GetLayer()),t.GetNetname())
        points=proposal['replacement_points_nm']
        expected={(tuple(a),tuple(b),proposal['source_width_nm'],proposal['source_layer'],'GND')
            for a,b in zip(points,points[1:])}
        if len(tracks)!=2 or {geometry(t) for t in tracks}!=expected:
            raise ValueError('ground_elbow_replacement_differs_from_source_derived_chamfer')
        before=ordinary._partition(parent,deadline,retired_uuids=retired)
        after=ordinary._partition(child,deadline,retained_keys=set().union(*before))
        if any(not any(p<=q for q in after) for p in before):
            raise ValueError('ground_elbow_lost_surviving_native_partition')
        pads={force._uid(p):p for f in child.GetFootprints() for p in f.Pads()}
        length=cells._shortest_track_path_mm(child,pads[proposal['owner_pad_uuid']],pads[proposal['selected_cap_ground_uuid']])
        if length is None or length>=proposal['source_owner_bypass_mm']-1e-6:
            raise ValueError('source_selected_owner_ground_return_not_shorter')
        for fp in parent.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname()!='GND':continue
                if time.monotonic()>=deadline:raise ValueError('ground_elbow_return_replay_deadline')
                old_return=cells._existing_return(parent,pad,3.5)
                if old_return is None:continue
                new_return=cells._existing_return(child,pads[force._uid(pad)],3.5)
                if new_return is None or new_return[0]>old_return[0]+1e-6:
                    raise ValueError('ground_elbow_worsened_existing_short_ground_return')
        with tempfile.TemporaryDirectory(prefix='cec-ground-elbow-') as work:
            projected=force._copy_family(paths[0],Path(work)/'source-minus-owned-prefix')
            basis=pcbnew.LoadBoard(str(projected));subtract(basis,proposal)
            field._save_field_snapshot(basis,projected)
            # Recheck native clearance independently on the immutable cut
            # basis; the worker's manifest is never a clearance certificate.
            gap=max(basis.GetDesignSettings().m_MinClearance,int(cells._netclass(basis,'GND')['clearance']))
            cache={};code=basis.GetNetcodeFromNetname('GND')
            for t in tracks:
                if (not fr._edge_leg_clear(basis,t.GetStart(),t.GetEnd(),math.ceil(t.GetWidth()/2))
                        or not fr._tap_foreign_clear(basis,t.GetStart(),t.GetEnd(),t.GetWidth(),
                            t.GetLayer(),gap,{code},foreign_cache=cache)):
                    raise ValueError('ground_elbow_independent_native_clearance_refused')
            _no_new_ground_contacts(basis,proposal,tracks,deadline=deadline)
            proof=additive.receive(projected,paths[1],timeout_s=max(.001,min(10.,deadline-time.monotonic())))
            r['independent_exact_source_cut_additions_and_refill']=proof
            if not proof['ok'] or not proof['complete']:
                raise ValueError('ground_elbow_exact_native_replay_refused:'+str(proof['errors']))
        if families!=[force._family(p,board_hint) for p in paths] or epoch!=force._code_identity() or time.monotonic()>=deadline:
            raise ValueError('ground_elbow_source_code_or_lease_changed')
        r.update(ok=True,complete=True,retired_track_uuids=sorted(retired),added_track_uuids=sorted(incoming),
            before_owner_bypass_mm=proposal['source_owner_bypass_mm'],after_owner_bypass_mm=length,
            owner_bypass_and_existing_short_returns_preserved=True,
            all_surviving_native_partitions_preserved=True,source_candidate_and_code_unchanged=True)
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def discover_from_drc(board,drc,*,authorize_source_locked=False,timeout_s=2.):
    deadline=_deadline(timeout_s);live={force._uid(t):t for t in board.GetTracks()}
    r=dict(schema=1,complete=False,plans=[],refused=[],errors=[],board_mutated=False,release_authority=False)
    try:
        ids=sorted({i['uuid'] for v in drc.get('violations',()) if v.get('type')=='clearance'
            for i in v.get('items',()) if i.get('uuid') in live and
            live[i['uuid']].GetClass()=='PCB_TRACK' and live[i['uuid']].GetNetname()=='GND'})
        if len(ids)>64:raise ValueError('ground_elbow_drc_inventory_bound')
        for uid in ids:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('ground_elbow_discovery_deadline')
            try:q=plan(board,uid,authorize_source_locked=authorize_source_locked,timeout_s=min(10.,remaining))
            except ValueError as exc:r['refused'].append(dict(seed_uuid=uid,reason=str(exc)));continue
            if any(set(q['retired_track_uuids'])&set(p['retired_track_uuids']) for p in r['plans']):continue
            r['plans'].append(q)
            if len(r['plans'])==4:break
        r['complete']=True
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
