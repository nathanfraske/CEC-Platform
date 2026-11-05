"""Bounded native pin-1 annotation reseat for a source-typed planned pivot.

Only a sole small silk triangle/circle on a positively modeled package may
translate. Its stroke, fill, shape, angle, owner pose and pin-1 association
remain unchanged. Source AND independently reconstructed planned pad-mask
and silk geometry must clear. This is not copper or placement authority.
"""
import json
import math
from pathlib import Path
import tempfile
import time
import pcbnew
import cec_bypass_ground_pivot as pivot
import cec_copper_echo as syntax
import cec_additive_route_receiving as additive
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_ground_span_reflow as lease


def _kind(item):
    if item.GetClass()!='PCB_SHAPE':return None
    if item.GetShape()==pcbnew.SHAPE_T_CIRCLE:return 'circle'
    if item.GetShape()==pcbnew.SHAPE_T_POLY:
        p=item.GetPolyShape()
        if p.OutlineCount()==1 and p.HoleCount(0)==0 and p.COutline(0).PointCount()==3:return 'triangle'
    return None


def _centre(item):return tuple(item.GetBoundingBox().GetCenter())


def _pin1_nearest(owner,at):
    values=sorted((sum((x-y)**2 for x,y in zip(at,p.GetPosition())),str(p.GetNumber())) for p in owner.Pads())
    return bool(values) and values[0][1]=='1' and (len(values)==1 or values[0][0]<values[1][0])


def _inventory(board,marker_uuid,face):
    copper=[];ink=[];silk=pcbnew.F_SilkS if face==pcbnew.F_Cu else pcbnew.B_SilkS
    mask=pcbnew.F_Mask if face==pcbnew.F_Cu else pcbnew.B_Mask
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.IsOnLayer(mask):copper.append((pad.GetEffectiveShape(face),max(0,int(pad.GetSolderMaskExpansion(face)))))
        for item in [*fp.GetFields(),*fp.GraphicalItems()]:
            if force._uid(item)==marker_uuid or item.GetLayer()!=silk:continue
            if hasattr(item,'IsVisible') and not item.IsVisible():continue
            ink.append(item.GetEffectiveTextShape() if hasattr(item,'GetEffectiveTextShape') else item.GetEffectiveShape())
    # Treat even tented barrel lands conservatively as mask obstacles; this
    # can refuse a seat, never invent an opening/clearance exemption.
    for via in board.GetTracks():
        if via.GetClass()=='PCB_VIA' and via.IsOnLayer(face):copper.append((via.GetEffectiveShape(face),0))
    for item in board.GetDrawings():
        if item.GetLayer()==mask:copper.append((item.GetEffectiveShape(),0))
        elif item.GetLayer()==silk:ink.append(item.GetEffectiveTextShape() if hasattr(item,'GetEffectiveTextShape') else item.GetEffectiveShape())
    if len(copper)+len(ink)>16384:raise ValueError('pin1_marker_native_inventory_bound')
    if any(shape is None for shape,_ in copper) or any(shape is None for shape in ink):raise ValueError('unknown_pin1_marker_obstacle_shape')
    return copper,ink


def plan(source,*,board_hint,marker_uuid,delta_nm,prospective_bypass_pivot,
         minimum_silk_clearance_nm=150000,timeout_s=10.):
    deadline=lease._deadline(timeout_s)
    if (type(board_hint) is not str or not board_hint or type(marker_uuid) is not str or not marker_uuid
            or type(delta_nm) is not list or len(delta_nm)!=2 or any(type(v) is not int for v in delta_nm)
            or not 0<sum(v*v for v in delta_nm)<=750000**2
            or type(minimum_silk_clearance_nm) is not int or not 0<=minimum_silk_clearance_nm<=500000
            or type(prospective_bypass_pivot) is not dict
            or set(prospective_bypass_pivot)!={'pad_uuid','target_via_uuid','points_nm'}):
        raise ValueError('bounded_explicit_pin1_marker_and_source_typed_pivot_required')
    source=Path(source).resolve();parent=pcbnew.LoadBoard(str(source));found=[(fp,g) for fp in parent.GetFootprints()
        for g in fp.GraphicalItems() if force._uid(g)==marker_uuid]
    if len(found)!=1:raise ValueError('one_literal_native_package_marker_required')
    owner,marker=found[0];kind=_kind(marker);model=roles.footprint_contract(owner)
    if (not model or owner.IsDNP() or owner.IsLocked() or owner.GetParentGroup() or marker.IsLocked()
            or not kind or marker.GetLayer() not in (pcbnew.F_SilkS,pcbnew.B_SilkS)
            or len([p for p in owner.Pads() if p.GetNumber()=='1'])!=1
            or len([g for g in owner.GraphicalItems() if g.GetLayer()==marker.GetLayer() and _kind(g)])!=1
            or any(g.ContainsItem(i) for g in parent.Groups() for i in (owner,marker))):
        raise ValueError('unique_unlocked_modeled_native_pin1_annotation_required')
    box=marker.GetBoundingBox()
    if not 0<max(box.GetWidth(),box.GetHeight())<=1500000:raise ValueError('small_package_pin1_marker_required')
    face=pcbnew.B_Cu if owner.IsFlipped() else pcbnew.F_Cu
    if marker.GetLayer()!=(pcbnew.B_SilkS if owner.IsFlipped() else pcbnew.F_SilkS):
        raise ValueError('source_pin1_marker_must_stay_on_package_surface')
    before=_centre(marker);copy=marker.Duplicate();copy.Move(pcbnew.VECTOR2I(*delta_nm));after=_centre(copy)
    if not _pin1_nearest(owner,before) or not _pin1_nearest(owner,after):raise ValueError('unambiguous_nearest_native_pin1_association_required')
    pin1=tuple(owner.FindPadByNumber('1').GetPosition());a=[pin1[i]-before[i] for i in (0,1)];b=[pin1[i]-after[i] for i in (0,1)]
    dot=sum(x*y for x,y in zip(a,b));cross=a[0]*b[1]-a[1]*b[0]
    if dot<=0 or abs(cross)>dot:raise ValueError('pin1_marker_bearing_must_remain_within_45_degrees')
    origin=tuple(owner.GetPosition());a=[before[i]-origin[i] for i in (0,1)];b=[after[i]-origin[i] for i in (0,1)]
    if any(x*y<0 for x,y in zip(a,b)) or sum(x*y for x,y in zip(a,b))<=0:
        raise ValueError('pin1_marker_must_retain_source_package_quadrant')
    proposal=pivot.plan(source,board_hint=board_hint,**prospective_bypass_pivot)
    if proposal['footprint_uuid']==force._uid(owner):raise ValueError('neighbour_marker_not_moving_bypass_own_annotation_required')
    future=pivot.construct(source,proposal,board_hint=board_hint)
    clearance=max(minimum_silk_clearance_nm,int(parent.GetDesignSettings().m_SilkClearance))
    shape=copy.GetEffectiveShape();radius=max(shape.BBox().GetWidth(),shape.BBox().GetHeight())/2
    if not fr._edge_leg_clear(parent,pcbnew.VECTOR2I(*after),pcbnew.VECTOR2I(*after),radius+clearance):
        raise ValueError('pin1_marker_native_outline_clearance')
    for board in (parent,future):
        copper,ink=_inventory(board,marker_uuid,face)
        for other,expansion in copper:
            if time.monotonic()>=deadline:raise ValueError('pin1_marker_native_mask_deadline')
            if shape.Collide(other,clearance+expansion):raise ValueError('pin1_marker_source_or_planned_mask_clearance')
        for other in ink:
            if time.monotonic()>=deadline:raise ValueError('pin1_marker_native_ink_deadline')
            if shape.Collide(other,clearance):raise ValueError('pin1_marker_source_or_planned_silk_collision')
    return dict(schema=1,source_sha256=force._hash(source),marker_uuid=marker_uuid,owner_uuid=force._uid(owner),
        marker_kind=kind,delta_nm=delta_nm,source_centre_nm=list(before),saved_centre_nm=list(after),
        minimum_silk_clearance_nm=minimum_silk_clearance_nm,effective_silk_clearance_nm=clearance,
        prospective_bypass_pivot=json.loads(json.dumps(prospective_bypass_pivot)),
        original_marker_shape_stroke_fill_and_orientation_preserved=True,
        source_and_independently_reconstructed_prospective_masks_checked=True,
        pin1_identity_and_source_package_quadrant_preserved=True,current_qualified=False,release_authority=False)


def construct(source,proposal,*,board_hint):
    fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in
        ('marker_uuid','delta_nm','prospective_bypass_pivot','minimum_silk_clearance_nm')})
    if fresh!=proposal:raise ValueError('stale_or_forged_pin1_marker_source_plan')
    board=pcbnew.LoadBoard(str(source));item=next(g for fp in board.GetFootprints() for g in fp.GraphicalItems() if force._uid(g)==proposal['marker_uuid'])
    item.Move(pcbnew.VECTOR2I(*proposal['delta_nm']));return board


def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],release_authority=False,current_qualified=False,
        no_copper_or_component_pose_authority=True,whole_native_DRC_and_composed_pivot_receiving_still_required=True)
    try:
        source,candidate=map(Path,(source,candidate));epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in
            ('marker_uuid','delta_nm','prospective_bypass_pivot','minimum_silk_clearance_nm')})
        if fresh!=proposal:raise ValueError('saved_pin1_marker_source_plan_changed')
        with tempfile.TemporaryDirectory(prefix='cec-pin1-marker-') as tmp:
            path=force._copy_family(source,Path(tmp)/'expected');board=construct(source,proposal,board_hint=board_hint)
            field._save_field_snapshot(board,path);want_root,want=additive._nodes(path);got_root,got=additive._nodes(candidate)
            if (syntax._freeze(want_root)!=syntax._freeze(got_root) or want.keys()!=got.keys()
                    or any(syntax._freeze(want[u])!=syntax._freeze(got[u]) for u in want)):
                raise ValueError('exact_independent_whole_source_pin1_marker_replay_differs')
        if force._sidecars(source)!=force._sidecars(candidate):raise ValueError('pin1_marker_sidecars_changed')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('pin1_marker_sources_or_code_changed')
        result.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_family_and_code_unchanged=True,modified_annotation_footprint_uuids=[proposal['owner_uuid']],
            modified_graphic_uuid=proposal['marker_uuid'],all_original_copper_pads_poses_fields_and_interfaces_exact=True,
            exact_native_marker_translation=True,not_a_fabrication_or_complete_annotation_qualification=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
