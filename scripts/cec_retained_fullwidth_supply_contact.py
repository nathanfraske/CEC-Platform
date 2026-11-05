"""Source-qualified common material contact; no moving/qualifying thin ink.

All group members and track world geometry stay exact. A positively assigned
supply cap may retain a full-class/full-current contact only through a native
core common to its ORIGINAL land, PROJECTED SAME land and unchanged track.
Floating geometry proposes centers only; native Boolean containment decides.
"""
import math,time
import pcbnew
import cec_force_current as force
import cec_decoupler_cell as cells
import cec_assembly_envelope as assembly
import cec_field_coupling as field


def plan(parent,projected,*,track_uuid,board_hint,source_floor,timeout_s=10.):
    if(type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10
            or type(track_uuid)is not str or not track_uuid or not callable(source_floor)):
        raise ValueError('bounded_retained_fullwidth_contact_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('retained_fullwidth_contact_deadline')
    tracks={force._uid(t):t for t in parent.GetTracks()};new={force._uid(t):t for t in projected.GetTracks()}
    edge=tracks.get(track_uuid);candidate=new.get(track_uuid)
    if edge is None or candidate is None or edge.GetClass()!='PCB_TRACK'or edge.HasSolderMask():return None
    groups=[g for g in parent.Groups()if g.ContainsItem(edge)]
    if(len(groups)!=1 or groups[0].GetName()!='CEC_LOCAL_ENDPOINT_NECKDOWN'or groups[0].IsLocked()
            or groups[0].GetParentGroup()is not None):return None
    group=groups[0];members=list(group.GetItems());ids=sorted(force._uid(t)for t in members)
    if not members or len(members)>512 or any(t.GetClass()!='PCB_TRACK'for t in members):return None
    live_groups=[g for g in projected.Groups()if force._uid(g)==force._uid(group)]
    if(len(live_groups)!=1 or live_groups[0].GetName()!=group.GetName()or live_groups[0].IsLocked()!=group.IsLocked()
            or live_groups[0].GetParentGroup()is not None or sorted(force._uid(t)for t in live_groups[0].GetItems())!=ids):return None
    old_inventory=field._field_snapshot_inventory(parent);new_inventory=field._field_snapshot_inventory(projected)
    for t in members:
        tick();uid=force._uid(t)
        if uid not in new or old_inventory.get(('track',uid))!=new_inventory.get(('track',uid)):return None
        if [force._uid(g)for g in parent.Groups()if g.ContainsItem(t)]!=[force._uid(group)]:return None
        if [force._uid(g)for g in projected.Groups()if g.ContainsItem(new[uid])]!=[force._uid(group)]:return None
        if new[uid].IsLocked()!=t.IsLocked():return None
    full,gap=source_floor(edge)
    if type(full)is not int or type(gap)is not int or full<=0 or gap<0:return None
    with force._thermal_hint(board_hint):contract=cells._supply_current_widths(parent,edge.GetNetname())
    if not contract or edge.GetLayer()not in contract['required_by_layer_nm']:return None
    floor=max(full,int(parent.GetDesignSettings().m_TrackMinWidth),contract['required_by_layer_nm'][edge.GetLayer()])
    if edge.GetWidth()<floor:return None
    pads={force._uid(p):p for fp in projected.GetFootprints()for p in fp.Pads()}
    roots=[p for fp in parent.GetFootprints()for p in fp.Pads()if p.GetNetCode()==edge.GetNetCode()
        and p.IsOnLayer(edge.GetLayer())and not p.HasHole()and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
        and edge.GetEffectiveShape(edge.GetLayer()).Collide(p.GetEffectiveShape(edge.GetLayer()),0)]
    projected_roots={force._uid(p)for fp in projected.GetFootprints()for p in fp.Pads()
        if p.GetNetname()==edge.GetNetname()and p.IsOnLayer(edge.GetLayer())and
        edge.GetEffectiveShape(edge.GetLayer()).Collide(p.GetEffectiveShape(edge.GetLayer()),0)}
    if projected_roots!={force._uid(p)for p in roots}:return None
    for item in parent.GetTracks():
        if item.GetClass()!='PCB_VIA'or item.GetNetCode()!=edge.GetNetCode()or not item.IsOnLayer(edge.GetLayer()):continue
        if edge.GetEffectiveShape(edge.GetLayer()).Collide(item.GetEffectiveShape(edge.GetLayer()),0):
            uid=force._uid(item)
            if old_inventory.get(('track',uid))!=new_inventory.get(('track',uid)):return None
    proofs=[]
    for old in roots:
        tick();uid=force._uid(old);pad=pads.get(uid)
        if pad is None or pad.GetNetname()!=old.GetNetname()or pad.GetNumber()!=old.GetNumber()or not pad.IsOnLayer(edge.GetLayer()):return None
        if tuple(old.GetPosition())==tuple(pad.GetPosition())and old.GetOrientationDegrees()==pad.GetOrientationDegrees():continue
        if old.GetSize()!=pad.GetSize()or old.GetShape()!=pad.GetShape()or old.GetAttribute()!=pad.GetAttribute():return None
        a,b=old.GetParentFootprint(),pad.GetParentFootprint()
        if(a.GetReference()!=b.GetReference()or a.GetValue()!=b.GetValue()or a.GetFPIDAsString()!=b.GetFPIDAsString()
                or a.GetLayer()!=b.GetLayer()or a.IsLocked()!=b.IsLocked()or a.IsDNP()!=b.IsDNP()):return None
        from cec_measurement_leaf import _bypass_supply_owner
        try:authority=_bypass_supply_owner(parent,old,board_hint)
        except ValueError:return None
        material=pcbnew.SHAPE_POLY_SET();edge.TransformShapeToPolygon(material,edge.GetLayer(),0,1,pcbnew.ERROR_INSIDE)
        shapes=[old.GetEffectivePolygon(edge.GetLayer(),pcbnew.ERROR_INSIDE),pad.GetEffectivePolygon(edge.GetLayer(),pcbnew.ERROR_INSIDE),material]
        native_common=pcbnew.SHAPE_POLY_SET(shapes[0])
        for shape in shapes[1:]:native_common.BooleanIntersection(shape)
        if not native_common.OutlineCount():return None
        bounds=native_common.BBox()
        # Necessary exact integer extent, not a 1nm Boolean tolerance waiver.
        if min(bounds.GetWidth(),bounds.GetHeight())<floor:return None
        common=assembly.polygon_from_native(shapes[0]).intersection(assembly.polygon_from_native(shapes[1])).intersection(assembly.polygon_from_native(shapes[2]))
        if common.is_empty or not common.is_valid:return None
        # Eroded geometry is proposal only. Include exact bound-midpoint for
        # a just-fitting full-width Source rectangle; never add tolerance.
        radius=(floor+1)//2;x0,y0,x1,y1=common.bounds
        points=[common.representative_point(),common.centroid]
        core=common.buffer(-radius/1e6)
        if not core.is_empty:points.extend([core.representative_point(),core.centroid])
        from shapely.geometry import Point
        points.append(Point((x0+x1)/2,(y0+y1)/2));witness=None
        for p in points[:5]:
            tick();at=pcbnew.VECTOR2I(round(p.x*1e6),round(p.y*1e6));circle=pcbnew.SHAPE_CIRCLE(at,radius)
            native=pcbnew.SHAPE_POLY_SET();circle.TransformToPolygon(native,1,pcbnew.ERROR_OUTSIDE)
            contained=True
            for shape in shapes:
                residual=pcbnew.SHAPE_POLY_SET(native);residual.BooleanSubtract(shape)
                if residual.OutlineCount():contained=False;break
            if contained:witness=dict(center_nm=list(at),diameter_nm=2*radius,native_error_nm=1);break
        if witness is None:return None
        proofs.append(dict(pad_uuid=uid,source_authority=authority,native_common_core=witness))
    if not proofs:return None
    tick()
    return dict(uuid=track_uuid,net=edge.GetNetname(),layer=int(edge.GetLayer()),source_group_uuid=force._uid(group),
        source_group_member_uuids=ids,full_width_floor_nm=floor,required_clearance_nm=gap,
        common_source_and_projected_same_pad_native_core=True,source_pad_contacts=proofs,
        original_track_lock_retained=bool(edge.IsLocked()),old_narrow_component_not_qualified=True,
        unchanged_full_rail_current_contract=contract,all_group_members_world_geometry_and_locks_unchanged=True,
        current_qualified=False,release_authority=False)
