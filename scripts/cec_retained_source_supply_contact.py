"""Keep literal Source supply copper/contact, never qualify a new neckdown.

Cardinal same-axis only. The shared tail is identical native Source material
by width/axis/fixed-end identity. ONLY the outward probe's pad-side half is
tested against the respective inward pad polygon. No outward Source polygon
is used as lower material, and no minimum overlap LENGTH is invented.
"""
import hashlib,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_fab_check as factory
import cec_decoupler_cell as cells
import cec_source_literal_additions as literal
from cec_footprint_fields import footprint_properties


def _pad_half(pad,root,fixed,width,face):
    axis=0 if root.y==fixed.y and root.x!=fixed.x else 1 if root.x==fixed.x and root.y!=fixed.y else None
    if axis is None:return None
    centre=tuple(pad.GetPosition());a=tuple(root);b=tuple(fixed);other=1-axis
    direction=1 if b[axis]>a[axis]else-1
    if centre[other]!=a[other]or (centre[axis]-a[axis])*direction>0:return None
    probe=pcbnew.PCB_TRACK(pad.GetBoard());probe.SetStart(pad.GetPosition());probe.SetEnd(fixed)
    probe.SetWidth(width);probe.SetLayer(face)
    poly=pcbnew.SHAPE_POLY_SET();probe.TransformShapeToPolygon(poly,face,0,1,pcbnew.ERROR_OUTSIDE)
    box=poly.BBox();x0=box.GetLeft()-width;x1=box.GetRight()+width;y0=box.GetTop()-width;y1=box.GetBottom()+width
    if axis==0:
        if direction>0:x1=a[0]
        else:x0=a[0]
    else:
        if direction>0:y1=a[1]
        else:y0=a[1]
    clip=pcbnew.SHAPE_POLY_SET();clip.NewOutline()
    for x,y in((x0,y0),(x1,y0),(x1,y1),(x0,y1)):clip.Append(x,y)
    poly.BooleanIntersection(clip)
    if not poly.OutlineCount():return None
    poly.BooleanSubtract(pad.GetEffectivePolygon(face,pcbnew.ERROR_INSIDE))
    if poly.OutlineCount():return None
    return dict(pad_center_nm=list(centre),pad_side_plane_nm=list(a),fixed_source_end_nm=list(b),
        axis=axis,width_nm=width,native_error_nm=1,residual_outlines=0,
        outward_half_capsule_wholly_in_inward_pad=True)


def plan(parent,projected,*,track_uuid,board_hint,source_floor,timeout_s=10.):
    if(type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10
            or type(track_uuid)is not str or not track_uuid or not callable(source_floor)
            or type(board_hint)is not str or not board_hint):raise ValueError('bounded_retained_source_contact_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('retained_source_supply_contact_deadline')
    path=Path(parent.GetFileName()).resolve()
    if not path.is_file():return None
    family=force._family(path,board_hint);code=force._code_identity()
    old=field._field_snapshot_inventory(parent);saved=pcbnew.LoadBoard(str(path))
    if old!=field._field_snapshot_inventory(saved):return None
    settings=('m_TrackMinWidth','m_MinClearance','m_MinThroughDrill','m_ViasMinAnnularWidth','m_CopperEdgeClearance')
    if any(getattr(parent.GetDesignSettings(),k)!=getattr(projected.GetDesignSettings(),k)
        or getattr(parent.GetDesignSettings(),k)!=getattr(saved.GetDesignSettings(),k)for k in settings):return None
    before={force._uid(t):t for t in parent.GetTracks()};after={force._uid(t):t for t in projected.GetTracks()}
    if before.keys()!=after.keys():return None  # Never grant an incoming/retired UUID allowance.
    edge=before.get(track_uuid)
    if edge is None or edge.GetClass()!='PCB_TRACK'or edge.HasSolderMask()or track_uuid not in after:return None
    groups=[g for g in parent.Groups()if g.ContainsItem(edge)]
    if(len(groups)!=1 or groups[0].GetName()!='CEC_LOCAL_ENDPOINT_NECKDOWN'or groups[0].IsLocked()
            or groups[0].GetParentGroup()is not None):return None
    group=groups[0];members=list(group.GetItems());ids=sorted(force._uid(t)for t in members)
    if not 1<=len(members)<=512 or any(t.GetClass()!='PCB_TRACK'for t in members):return None
    new_groups=[g for g in projected.Groups()if force._uid(g)==force._uid(group)]
    if(len(new_groups)!=1 or new_groups[0].GetName()!=group.GetName()or new_groups[0].IsLocked()!=group.IsLocked()
            or new_groups[0].GetParentGroup()is not None or sorted(force._uid(t)for t in new_groups[0].GetItems())!=ids):return None
    new=field._field_snapshot_inventory(projected)
    for item in members:
        tick();uid=force._uid(item)
        if uid not in after or old[('track',uid)]!=new.get(('track',uid)):return None
        if [force._uid(g)for g in parent.Groups()if g.ContainsItem(item)]!=[force._uid(group)]:return None
        if [force._uid(g)for g in projected.Groups()if g.ContainsItem(after[uid])]!=[force._uid(group)]:return None
    full,gap=source_floor(edge)
    if type(full)is not int or type(gap)is not int or full<=0 or gap<0:return None
    declared=fab.board_profile_name(parent)
    if not declared or declared!=fab.board_profile_name(projected):return None
    rules=factory.profile_rules(factory.PROFILES['jlcpcb'],factory.board_outer_copper_oz(path),declared)
    factory_floor=math.ceil(rules['track']*1e6)
    with force._thermal_hint(board_hint):
        contract=cells._supply_current_widths(parent,edge.GetNetname())
        candidate_contract=cells._supply_current_widths(projected,edge.GetNetname())
    if not contract or contract!=candidate_contract or edge.GetLayer()not in contract['required_by_layer_nm']:return None
    current_floor=contract['required_by_layer_nm'][edge.GetLayer()];width=edge.GetWidth()
    if width<max(factory_floor,current_floor,int(parent.GetDesignSettings().m_TrackMinWidth)):return None
    pad_map={force._uid(p):p for fp in projected.GetFootprints()for p in fp.Pads()};face=int(edge.GetLayer())
    roots=[p for fp in parent.GetFootprints()for p in fp.Pads()if p.GetNetname()==edge.GetNetname()and p.IsOnLayer(face)
        and edge.GetEffectiveShape(face).Collide(p.GetEffectiveShape(face),0)]
    new_roots={force._uid(p)for fp in projected.GetFootprints()for p in fp.Pads()if p.GetNetname()==edge.GetNetname()and p.IsOnLayer(face)
        and edge.GetEffectiveShape(face).Collide(p.GetEffectiveShape(face),0)}
    if new_roots!={force._uid(p)for p in roots}:return None
    proofs=[]
    for pad in roots:
        tick();uid=force._uid(pad);target=pad_map.get(uid)
        if target is None:return None
        if tuple(target.GetPosition())==tuple(pad.GetPosition())and target.GetOrientationDegrees()==pad.GetOrientationDegrees():continue
        a,b=pad.GetParentFootprint(),target.GetParentFootprint()
        if(pad.HasHole()or target.HasHole()or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or target.GetAttribute()!=pad.GetAttribute()
                or target.GetNumber()!=pad.GetNumber()or target.GetSize()!=pad.GetSize()or target.GetShape()!=pad.GetShape()
                or tuple(target.GetLayerSet().Seq())!=tuple(pad.GetLayerSet().Seq())or target.GetOrientationDegrees()!=pad.GetOrientationDegrees()
                or a.GetValue()!=b.GetValue()or a.GetFPIDAsString()!=b.GetFPIDAsString()or a.GetReference()!=b.GetReference()
                or a.IsLocked()!=b.IsLocked()or a.IsDNP()!=b.IsDNP()or footprint_properties(a)!=footprint_properties(b)):return None
        saved_fp=next((fp for fp in saved.GetFootprints()if force._uid(fp)==force._uid(a)),None)
        saved_pad=next((p for p in saved_fp.Pads()if force._uid(p)==uid),None)if saved_fp else None
        if saved_pad is None:return None
        source_poly=pad.GetEffectivePolygon(face,pcbnew.ERROR_OUTSIDE)
        if source_poly.Format()!=saved_pad.GetEffectivePolygon(face,pcbnew.ERROR_OUTSIDE).Format():return None
        shifted=pcbnew.SHAPE_POLY_SET(target.GetEffectivePolygon(face,pcbnew.ERROR_OUTSIDE))
        shifted.Move(pad.GetPosition()-target.GetPosition())
        if shifted.Format()!=source_poly.Format():return None
        for getter in ('GetLocalClearance','GetLocalSolderMaskMargin','GetLocalSolderPasteMargin','GetLocalSolderPasteMarginRatio'):
            if getattr(pad,getter)()!=getattr(target,getter)()or getattr(pad,getter)()!=getattr(saved_pad,getter)():return None
        ends=[edge.GetStart(),edge.GetEnd()];contacts=[i for i,at in enumerate(ends)if pad.HitTest(at,0)]
        if len(contacts)!=1:return None
        root=ends[contacts[0]];fixed=ends[1-contacts[0]]
        old_proof=_pad_half(pad,root,fixed,width,face);new_proof=_pad_half(target,root,fixed,width,face)
        if old_proof is None or new_proof is None:return None
        fixed_tracks=[t for t in parent.GetTracks()if t.GetClass()=='PCB_TRACK'and force._uid(t)!=track_uuid
            and t.GetNetname()==edge.GetNetname()and t.GetLayer()==face and t.GetWidth()>=max(factory_floor,current_floor)
            and tuple(fixed)in(tuple(t.GetStart()),tuple(t.GetEnd()))]
        if not fixed_tracks or any(old[('track',force._uid(t))]!=new.get(('track',force._uid(t)))for t in fixed_tracks):return None
        from cec_measurement_leaf import _bypass_supply_owner
        try:authority=_bypass_supply_owner(parent,pad,board_hint)
        except ValueError:return None
        proofs.append(dict(pad_uuid=uid,source_authority=authority,before=old_proof,after=new_proof,
            fixed_source_branch_track_uuids=sorted(force._uid(t)for t in fixed_tracks)))
    if not proofs:return None
    # This mode cannot borrow moving Source barrels to replace a lost path.
    for item in parent.GetTracks():
        if (item.GetClass()=='PCB_VIA'and item.GetNetname()==edge.GetNetname()and item.IsOnLayer(face)
            and edge.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0)):
            if old[('track',force._uid(item))]!=new.get(('track',force._uid(item))):return None
    literal_nodes=literal._inventory(path.read_text())[0]
    if track_uuid not in literal_nodes:return None
    tick()
    if family!=force._family(path,board_hint)or code!=force._code_identity():return None
    return dict(scope='unchanged_source_supply_contact_with_retained_debt',uuid=track_uuid,net=edge.GetNetname(),layer=face,
        source=str(path),source_family=family,source_track_literal_sha256=hashlib.sha256(literal_nodes[track_uuid][2].encode()).hexdigest(),
        source_group_uuid=force._uid(group),source_group_member_uuids=ids,source_width_nm=width,
        actual_factory_transverse_floor_nm=factory_floor,unchanged_current_physics_floor_nm=current_floor,
        unchanged_full_rail_current_contract=contract,source_class_floor_nm=full,source_contacts=proofs,
        original_track_lock_retained=bool(edge.IsLocked()),source_tail_only_exact_literal_identity=True,
        outward_source_polygon_not_lower_material_authority=True,all_source_group_members_world_geometry_and_locks_unchanged=True,
        original_class_and_escape_debt_retained_unqualified=True,new_thin_copper_allowance=False,
        current_qualified=False,release_authority=False)
