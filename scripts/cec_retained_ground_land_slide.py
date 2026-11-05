"""Small source-land slides toward a retained Ground barrel.

Only a literal two-land SMD capacitor and the pad endpoint of its existing
straight Ground lead move. All barrels, other tracks, power fills, parts,
rules, widths and board interfaces remain exact. This is geometric receiving;
whole-board current, DRC, Kelvin, fields and assembly gates remain separate.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_device_bypass as bypass
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_return_preservation as returns
import cec_ground_return_shortcut as reference
import cec_ordinary_route_receiving as ordinary
import cec_pi_cleanup as placement
import cec_route_quality as quality


def _deadline(timeout_s):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):
        raise ValueError('bounded_ground_land_slide_lease_required')
    return time.monotonic()+timeout_s


def _move(board,fp_uuid,pad_uuid,lead_uuid,delta):
    fp=next(f for f in board.GetFootprints() if force._uid(f)==fp_uuid)
    pad=next(p for p in fp.Pads() if force._uid(p)==pad_uuid)
    lead=next(t for t in board.GetTracks() if force._uid(t)==lead_uuid)
    root=tuple(pad.GetPosition());origin=tuple(fp.GetPosition())
    fp.SetPosition(pcbnew.VECTOR2I(*(origin[i]+delta[i] for i in (0,1))))
    if tuple(lead.GetStart())==root:lead.SetStart(pad.GetPosition())
    elif tuple(lead.GetEnd())==root:lead.SetEnd(pad.GetPosition())
    else:raise ValueError('source_ground_slide_root_changed')
    return fp,pad,lead


def plan(source,*,board_hint,footprint_uuid,delta_nm,allow_owned_locked=False,timeout_s=10.):
    deadline=_deadline(timeout_s)
    if (type(board_hint) is not str or not board_hint or type(footprint_uuid) is not str or not footprint_uuid
            or type(delta_nm) not in (list,tuple) or len(delta_nm)!=2
            or any(type(v) is not int for v in delta_nm)
            or not 10000<=math.hypot(*delta_nm)<=500000 or type(allow_owned_locked) is not bool):
        raise ValueError('bounded_explicit_source_ground_land_slide_required')
    source=Path(source).resolve();digest=force._hash(source);b=pcbnew.LoadBoard(str(source))
    fps=[f for f in b.GetFootprints() if force._uid(f)==footprint_uuid]
    if len(fps)!=1:raise ValueError('one_literal_source_slide_capacitor_required')
    fp=fps[0];pads=list(fp.Pads());grounds=[p for p in pads if p.GetNetname()=='GND']
    if (fp.IsLocked() or fp.IsDNP() or fp.GetParentGroup() or len(pads)!=2 or len(grounds)!=1
            or not bypass.capacitor_identity(fp.GetReference(),fp.GetFPIDAsString())
            or not bypass.capacitance_f(fp.GetValue())
            or any(p.HasHole() or cells.cec_return_escape.smd_surface_layer(p) is None for p in pads)
            or len({p.GetNetname() for p in pads})!=2 or any(p.GetNetCode()<=0 for p in pads)):
        raise ValueError('unlocked_populated_two_smd_land_capacitor_required')
    pad=grounds[0];face=cells.cec_return_escape.smd_surface_layer(pad);root=tuple(pad.GetPosition())
    tracks=list(b.GetTracks());all_pads=[p for f in b.GetFootprints() for p in f.Pads()]
    if len(tracks)+len(all_pads)+len(list(b.Zones()))>16384:
        raise ValueError('ground_land_slide_native_inventory_bound')
    leads=[t for t in tracks if t.GetClass()=='PCB_TRACK' and t.GetNetCode()==pad.GetNetCode()
        and t.GetLayer()==face and root in (tuple(t.GetStart()),tuple(t.GetEnd()))]
    if len(leads)!=1:raise ValueError('one_exact_source_ground_land_departure_required')
    lead=leads[0];ends=(tuple(lead.GetStart()),tuple(lead.GetEnd()));end=ends[1] if ends[0]==root else ends[0]
    floor=max(200000,int(b.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(b,'GND')['width']))
    if (lead.GetParentGroup() or lead.HasSolderMask() or not floor<=lead.GetWidth()<=350000
            or lead.IsLocked() and not allow_owned_locked or not 0<lead.GetLength()<=4000000
            or not quality.is_canonical_stroke(root,end,tolerance_nm=0)):
        raise ValueError('bounded_full_class_source_ground_lead_and_lock_authority_required')
    direction=(end[0]-root[0],end[1]-root[1]);dot=sum(a*z for a,z in zip(direction,delta_nm))
    if (direction[0]*delta_nm[1]!=direction[1]*delta_nm[0] or not 0<dot<sum(v*v for v in direction)):
        raise ValueError('strict_motion_along_source_ground_lead_toward_retained_barrel_required')
    vias=[v for v in tracks if v.GetClass()=='PCB_VIA' and v.GetNetCode()==pad.GetNetCode()
        and tuple(v.GetPosition())==end]
    if len(vias)!=1:raise ValueError('one_exact_unchanged_source_ground_barrel_required')
    via=vias[0];contacts=reference._reference_contacts(b,via)
    for item in [*tracks,*all_pads]:
        if time.monotonic()>=deadline:raise ValueError('ground_land_slide_source_contact_deadline')
        if force._uid(item) in {force._uid(lead),force._uid(pad),force._uid(via)} or not item.IsOnLayer(face):continue
        if item.GetEffectiveShape(face).Collide(lead.GetEffectiveShape(face),0):
            raise ValueError('source_ground_slide_lead_has_another_native_body_contact')
    before=cells._existing_return(b,pad,16.,allow_native_track_body=True)
    if before is None:raise ValueError('proved_source_ground_return_required')
    source_pose=list(fp.GetPosition());new_fp,new_pad,new_lead=_move(b,footprint_uuid,force._uid(pad),force._uid(lead),delta_nm)
    # Removed root copper must be fully covered by the actual new land. This
    # is native polygon inclusion, not endpoint proximity or a net-only claim.
    original=pcbnew.LoadBoard(str(source))
    cut=pcbnew.PCB_TRACK(b);cut.SetStart(pcbnew.VECTOR2I(*root));cut.SetEnd(new_pad.GetPosition())
    cut.SetWidth(new_lead.GetWidth());cut.SetLayer(face)
    missing=pcbnew.SHAPE_POLY_SET();cut.TransformShapeToPolygon(missing,face,0,1000,pcbnew.ERROR_OUTSIDE)
    shape=pcbnew.SHAPE_POLY_SET();new_pad.TransformShapeToPolygon(shape,face,0,1000,pcbnew.ERROR_INSIDE)
    missing.BooleanSubtract(shape)
    if missing.OutlineCount():raise ValueError('retired_ground_root_not_wholly_covered_by_new_native_land')
    additive._ground_refill(b);placement._pose_preflight(b,new_fp)
    old_vias={force._uid(v):fab.local_pofv_via_decision(original,v)[0]
        for v in original.GetTracks() if v.GetClass()=='PCB_VIA'}
    for v in b.GetTracks():
        if v.GetClass()=='PCB_VIA' and old_vias.get(force._uid(v)) and not fab.local_pofv_via_decision(b,v)[0]:
            raise ValueError('source_ground_land_slide_lost_existing_barrel_process_owner:'+force._uid(v))
    assignment=constraints._device_bypass_assignment(original,project_max_mm=3.5);supply_checks=[]
    after_assignment=constraints._device_bypass_assignment(b,project_max_mm=3.5)
    def ownership(result):
        return {key:row['cap_ref'] for key,row in result['assigned'].items()}
    if ownership(assignment)!=ownership(after_assignment):
        raise ValueError('source_ground_land_slide_changed_selected_bypass_ownership')
    for row in assignment['assigned'].values():
        if row['cap_ref']!=fp.GetReference():continue
        req=row['requirement'];owner=original.FindFootprintByReference(req['ref'])
        rail=next(p for p in original.FindFootprintByReference(fp.GetReference()).Pads() if p.GetNetname()==req['rail'])
        after_rail=next(p for p in new_fp.Pads() if force._uid(p)==force._uid(rail))
        first=cells._shortest_track_path_mm(original,owner.FindPadByNumber(str(req['pin'])),rail)
        last=cells._shortest_track_path_mm(b,b.FindFootprintByReference(req['ref']).FindPadByNumber(str(req['pin'])),after_rail)
        if first is not None and (last is None or last>first+1e-6):
            raise ValueError('existing_selected_bypass_supply_path_worsened')
        supply_checks.append(dict(requirement=req['id'],source_mm=first,candidate_mm=last))
    ground=returns.receive(original,b,timeout_s=max(.001,min(10.,deadline-time.monotonic())))
    improved=[r for r in ground['improved_terminals'] if r['pad_uuid']==force._uid(pad)]
    if not ground['ok'] or not ground['complete'] or not improved:
        raise ValueError('strict_ground_land_slide_gain_without_any_source_return_regression_required')
    if time.monotonic()>=deadline or force._hash(source)!=digest:
        raise ValueError('source_ground_land_slide_changed_or_plan_lease_exhausted')
    return dict(schema=1,source=str(source),source_sha256=digest,board_hint=board_hint,
        footprint_uuid=footprint_uuid,pad_uuid=force._uid(pad),lead_uuid=force._uid(lead),
        retained_via_uuid=force._uid(via),delta_nm=list(delta_nm),allow_owned_locked=allow_owned_locked,
        source_pose_nm=source_pose,candidate_pose_nm=list(new_fp.GetPosition()),
        source_return_mm=before[0],candidate_return_mm=improved[0]['candidate']['return_mm'],
        source_reference_contacts=contacts,selected_bypass_supply_paths=supply_checks,
        modified_nets=sorted(p.GetNetname() for p in new_fp.Pads()),
        source_root_copper_covered_by_new_actual_ground_land=True,
        every_barrel_and_power_conductor_retained=True,new_holes=0,
        current_qualified=False,routing_admitted=False,fab_ready=False,release_authority=False)


def _args(q):
    return {k:q[k] for k in ('board_hint','footprint_uuid','delta_nm','allow_owned_locked')}


def construct(proposal):
    if plan(proposal['source'],**_args(proposal))!=proposal:
        raise ValueError('stale_or_forged_ground_land_slide_plan')
    b=pcbnew.LoadBoard(proposal['source'])
    _move(b,proposal['footprint_uuid'],proposal['pad_uuid'],proposal['lead_uuid'],proposal['delta_nm'])
    return b


def receive(source,candidate,*,board_hint,footprint_uuid,delta_nm,allow_owned_locked=False,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,routing_admitted=False,
        fab_ready=False,release_authority=False)
    try:
        deadline=_deadline(timeout_s);source,candidate=[Path(p).resolve() for p in (source,candidate)]
        if source==candidate:raise ValueError('distinct_saved_ground_land_slide_members_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        q=plan(source,board_hint=board_hint,footprint_uuid=footprint_uuid,delta_nm=delta_nm,
            allow_owned_locked=allow_owned_locked,timeout_s=max(.001,deadline-time.monotonic()))
        with tempfile.TemporaryDirectory(prefix='cec-ground-land-slide-') as work:
            expected=pcbnew.LoadBoard(str(source))
            _move(expected,q['footprint_uuid'],q['pad_uuid'],q['lead_uuid'],q['delta_nm'])
            additive._ground_refill(expected)
            path=force._copy_family(source,Path(work)/'expected');field._save_field_snapshot(expected,path)
            _,nodes=additive._nodes(path);_,actual=additive._nodes(candidate)
            if ({u:syntax._freeze(v) for u,v in nodes.items()}!={u:syntax._freeze(v) for u,v in actual.items()}
                    or force._sidecars(source)!=force._sidecars(candidate)):
                raise ValueError('saved_ground_land_slide_differs_from_exact_original_source_replay')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        parts0=ordinary._partition(parent,deadline);old_fp=next(f for f in parent.GetFootprints() if force._uid(f)==footprint_uuid)
        new_fp=next(f for f in child.GetFootprints() if force._uid(f)==footprint_uuid)
        old_pads={force._uid(p):p for p in old_fp.Pads()}
        bindings={force._item_key(p):force._item_key(old_pads[force._uid(p)]) for p in new_fp.Pads()}
        parts1=ordinary._partition(child,deadline,retained_keys=set().union(*parts0),_identity_rebindings=bindings)
        if {frozenset(p) for p in parts0}!={frozenset(p) for p in parts1}:
            raise ValueError('source_ground_land_slide_original_native_partition_changed')
        if time.monotonic()>=deadline or epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('ground_land_slide_source_candidate_code_or_lease_changed')
        r.update(ok=True,complete=True,proposal=q,code_identity=epoch,source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate),every_original_native_partition_identical=True,
            exact_source_pose_and_ground_endpoint_replayed=True,modified_nets=q['modified_nets'],
            source_return_mm=q['source_return_mm'],candidate_return_mm=q['candidate_return_mm'],
            shortened_ground_return_mm=q['source_return_mm']-q['candidate_return_mm'],
            every_barrel_power_track_and_non_ground_fill_exact=True,
            independent_whole_current_DRC_Kelvin_fields_and_stack_receiving_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,StopIteration) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
