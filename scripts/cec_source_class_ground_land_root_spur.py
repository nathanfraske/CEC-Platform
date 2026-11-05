"""Source-class complete literal Ground spur ending at one retained land.

No width/load/role supplied by caller; no current or release qualification.
The old small-tail and Source-class tail APIs are deliberately untouched.
All surviving partitions and already-proved short returns remain mandatory.
"""
from pathlib import Path
import math,time
import pcbnew
import cec_source_class_ground_dead_end_tail as legacy
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_native_partition_pair as partitions
import cec_ground_return_shortcut as reference
from cec_native_items import discard_items
from cec_cell_row_rebuild import _source_binding


def _require(ok,reason):
    if not ok:raise ValueError(reason)


def _polygon(item,layer,error):
    p=pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(p,layer,0,1000,error)
    return p


def plan(board,source,seed_uuid,*,timeout_s=10.,max_tracks=8,max_length_mm=12.,
         allow_locked_track_uuids=()):
    deadline=legacy._deadline(timeout_s)
    authority=legacy._authority(board,source,'GND')
    source=Path(source).resolve(strict=True)
    family=force._family(source,str(source));epoch=force._code_identity()
    _require(type(seed_uuid)is str and seed_uuid and type(max_tracks)is int and 1<=max_tracks<=8
        and type(max_length_mm)in(int,float)and math.isfinite(max_length_mm)
        and 0<max_length_mm<=12,'bounded_literal_ground_spur_scope_required')
    allowed=ordinary._ids(allow_locked_track_uuids,'draft_exact_ground_spur_locks',8)
    native_tracks=list(board.GetTracks());tracks={force._uid(t):t for t in native_tracks}
    _require(len(tracks)==len(native_tracks),'unique_literal_ground_spur_copper_identity_required')
    pads=[p for fp in board.GetFootprints()for p in fp.Pads()]
    zones=[z for z in board.Zones()if not z.GetIsRuleArea()]
    _require(len(tracks)+len(pads)+len(zones)<=16384,'ground_spur_inventory_bound')
    owners={}
    for item in [*native_tracks,*pads,*zones]:owners.setdefault(force._uid(item),[]).append(item)
    _require(not any(len(items)>1 and any(i.GetClass()!='PAD'for i in items)
        for items in owners.values()),'unique_ground_spur_copper_object_identity_required')
    _require(len({force._item_key(p)for p in pads})==len(pads),
        'unique_native_ground_spur_pad_composite_identity_required')
    copper=list(board.GetEnabledLayers().CuStack())
    graphics=[*board.GetDrawings(),*(g for fp in board.GetFootprints()
        for g in [*fp.GraphicalItems(),*fp.GetFields()])]
    _require(len(graphics)<=16384 and not any(g.IsOnLayer(l)for g in graphics for l in copper),
        'unsupported_copper_graphics_cannot_be_ground_spur_evidence')
    _require(seed_uuid in tracks,'unique_ground_spur_seed_required')
    seed=tracks[seed_uuid];layer=int(seed.GetLayer());width=authority['width_nm']
    _require(seed.GetClass()=='PCB_TRACK'and seed.GetNetname()=='GND'
        and seed.GetWidth()==width and layer in(pcbnew.F_Cu,pcbnew.B_Cu),
        'source_class_surface_ground_track_seed_required')
    _require(all(z.IsFilled()for z in zones),'all_literal_fills_known_required')
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    face=[t for t in tracks.values()if t.GetClass()=='PCB_TRACK'and t.IsOnLayer(layer)]
    endpoints={}
    for t in face:
        for at in(tuple(t.GetStart()),tuple(t.GetEnd())):endpoints.setdefault(at,[]).append(t)
    def tick():_require(time.monotonic()<deadline,'ground_spur_deadline')
    def land_at(point):
        marker=pcbnew.VECTOR2I(*point)
        return [p for p in pads if p.IsOnLayer(layer)and p.GetEffectiveShape(layer).Collide(marker,0)]
    ends=[tuple(seed.GetStart()),tuple(seed.GetEnd())]
    # Literal unmatched endpoint only. Incidental cap overlaps are not roots;
    # every such physical contact is inventoried after the WHOLE chain walk.
    tips=[at for at in ends if len(endpoints.get(at,[]))==1 and not land_at(at)]
    _require(len(tips)==1,'one_literal_unmatched_ground_spur_tip_required')
    at=tips[0];current=seed;cut=[];length=0.;root=None;root_at=None
    while True:
        tick();uid=force._uid(current);ends=[tuple(current.GetStart()),tuple(current.GetEnd())]
        _require(current.GetClass()=='PCB_TRACK'and current.GetNetname()=='GND'
            and current.GetLayer()==layer and current.GetWidth()==width
            and uid not in grouped and current.GetParentGroup()is None
            and(not current.IsLocked()or uid in allowed)and not current.HasSolderMask()
            and at in ends and ends[0]!=ends[1]and uid not in cut,
            'ungrouped_uniform_exact_literal_ground_spur_required')
        dx,dy=abs(ends[1][0]-ends[0][0]),abs(ends[1][1]-ends[0][1])
        _require(not dx or not dy or dx==dy,'canonical_literal_ground_spur_required')
        cut.append(uid);length+=current.GetLength()/1e6
        _require(len(cut)<=max_tracks and length<=max_length_mm,'whole_ground_spur_work_bound')
        far=ends[1]if at==ends[0]else ends[0];lands=land_at(far)
        if lands:
            _require(len(lands)==1,'one_retained_ground_endpoint_land_required')
            root=lands[0];root_at=far
            _require(root.GetNetname()=='GND'and root.GetNetCode()==seed.GetNetCode()
                and not root.HasHole()
                and root.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
                and list(root.GetLayerSet().CuStack())==[layer]
                and not root.GetParentFootprint().IsDNP(),
                'literal_populated_surface_ground_land_root_required')
            break
        peers=[t for t in endpoints.get(far,[])if force._uid(t)not in cut]
        _require(len(peers)==1,'unbranched_complete_literal_ground_spur_required')
        current,at=peers[0],far
    _require(allowed=={u for u in cut if tracks[u].IsLocked()},'exact_cut_only_ground_spur_lock_scope')
    retained=set();root_uid=force._uid(root)
    _require(sum(force._uid(p)==root_uid for p in pads)==1,'unique_native_ground_root_land_identity_required')
    root_inside=_polygon(root,layer,pcbnew.ERROR_INSIDE)
    # The endpoint may be off-centre, but a point/bbox/tangent contact is not
    # landing ownership. Use conservative actual copper polygons on this face.
    landing=_polygon(tracks[cut[-1]],layer,pcbnew.ERROR_INSIDE)
    landing.BooleanIntersection(root_inside)
    _require(landing.OutlineCount()>0 and abs(landing.Area())>0,
        'positive_native_ground_spur_land_overlap_required')
    material=[*tracks.values(),*pads,*zones]
    for uid in cut:
        t=tracks[uid];shape=t.GetEffectiveShape(layer)
        for item in material:
            tick();other=force._uid(item)
            if other in cut or not item.IsOnLayer(layer):continue
            geom=item.GetFilledPolysList(layer)if item.GetClass()=='ZONE'else item.GetEffectiveShape(layer)
            if not shape.Collide(geom,0):continue
            if other==root_uid:
                _require(uid==cut[-1],'only_final_ground_spur_cap_may_contact_root_land')
                continue
            _require(item.GetClass()=='PCB_TRACK'and item.GetNetname()=='GND'
                and item.GetNetCode()==seed.GetNetCode()and int(item.GetLayer())==layer,
                'ground_spur_has_unowned_pad_via_plane_or_interior_contact:'+other)
            # Actual copper intersection must be wholly inside the retained
            # land. A nearby same-net body/mesh contact is not endpoint proof.
            overlap=_polygon(t,layer,pcbnew.ERROR_OUTSIDE)
            overlap.BooleanIntersection(_polygon(item,layer,pcbnew.ERROR_OUTSIDE))
            _require(overlap.OutlineCount()>0 and abs(overlap.Area())>0,
                'positive_native_retained_ground_landing_contact_required:'+other)
            overlap.BooleanSubtract(root_inside)
            _require(overlap.OutlineCount()==0,'ground_spur_retained_contact_escapes_root_land:'+other)
            retained.add(other)
    _require(1<=len(retained)<=8,'retained_actual_ground_root_conductors_required')
    probe=pcbnew.LoadBoard(str(source))
    discard_items(probe,[t for t in probe.GetTracks()if force._uid(t)in cut])
    inventory=partitions._inventory(probe,deadline,dict(items=16384,polygons=4096,vertices=200000))
    keys={force._item_key(root)}|{force._item_key(tracks[u])for u in retained}
    components=[p for p in inventory['components']if keys<=p]
    _require(len(components)==1,'whole_cut_root_and_retained_copper_must_remain_one_native_component')
    witnesses=[]
    for item in inventory['objects']:
        tick()
        if (item.GetClass()!='PCB_VIA'or item.GetNetname()!='GND'
            or item.GetViaType()!=pcbnew.VIATYPE_THROUGH or force._item_key(item)not in components[0]):continue
        try:contacts=reference._reference_contacts(probe,item)
        except ValueError:continue
        witnesses.append((force._uid(item),contacts))
    _require(witnesses,'whole_cut_root_has_no_real_retained_reference_plane_barrel')
    witness,contacts=min(witnesses,key=lambda q:q[0])
    _require(force._family(source,str(source))==family and force._code_identity()==epoch,
        'ground_spur_source_or_code_changed')
    tick()
    return dict(schema=1,kind='source_class_complete_ground_land_root_spur',source=str(source),
        source_authority=authority,source_binding=_source_binding(board),seed_uuid=seed_uuid,
        ground_net='GND',max_tracks=max_tracks,max_length_mm=max_length_mm,
        allow_locked_track_uuids=sorted(allowed),retired_track_uuids=cut,
        source_layer=layer,source_width_nm=width,source_length_mm=length,
        retained_root_pad_uuid=root_uid,retained_root_position_nm=list(root_at),
        retained_root_track_uuids=sorted(retained),retained_root_via_uuid=witness,
        retained_actual_reference_contacts=contacts,whole_cut_root_native_reference_proved=True,
        every_actual_cut_boundary_accounted=True,current_qualified=False,release_authority=False)


def subtract(board,proposal,*,timeout_s=10.):
    fresh=plan(board,proposal['source'],proposal['seed_uuid'],timeout_s=timeout_s,
        max_tracks=proposal['max_tracks'],max_length_mm=proposal['max_length_mm'],
        allow_locked_track_uuids=proposal['allow_locked_track_uuids'])
    _require(fresh==proposal,'draft_ground_spur_stale_or_forged_plan')
    discard_items(board,[t for t in board.GetTracks()if force._uid(t)in fresh['retired_track_uuids']])


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    if str(Path(source).resolve())!=proposal.get('source'):
        return dict(ok=False,complete=False,errors=['draft_ground_spur_source_mismatch'])
    # This performs independent fresh discovery through subtract(), exact
    # saved subtract/refill/sidecars, every surviving native partition and
    # non-worsening of EVERY already-proved short Ground return.
    result=legacy._receive_exact_subtraction(source,candidate,proposal,board_hint=board_hint,
        subtractor=subtract,timeout_s=timeout_s)
    result.update(scope='source_class_complete_ground_land_root_spur',
        current_qualified=False,release_authority=False)
    return result
