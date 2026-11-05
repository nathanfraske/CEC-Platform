"""Retire a stranded generated local GND barrel, not a functional stitch.

The small via has lost its live SMD/route owner and fails the local factory
exception. Only the unlocked generated ownership group may own it. A nearby
unchanged qualified barrel must already bridge every touched reference plane
through continuous saved plane copper. All surviving partitions, proved local
returns, current, field and final native rules remain separate hard gates.
"""
import math
import time
import pcbnew
import cec_force_current as force
import cec_fab_profile as fab
import cec_fr as fr
import cec_ground_plane_echo as echo
import cec_ground_dead_end_tail as tails
import cec_kelvin_copper_cut as physical
from cec_native_items import discard_items


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('stale_local_ground_inventory_deadline')


def _qualified_bridge(board, via):
    if (via.GetClass() != 'PCB_VIA' or via.GetNetname() != 'GND'
            or via.GetViaType() != pcbnew.VIATYPE_THROUGH
            or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu):
        return False
    ordinary = fab.board_legal_through_via_geometry(board,
        via.GetWidth(via.TopLayer()) / 1e6, via.GetDrillValue() / 1e6)
    return (via.GetWidth(via.TopLayer()) >= round(ordinary[0] * 1e6)
            and via.GetDrillValue() >= round(ordinary[1] * 1e6)
            or fab.local_pofv_via_decision(board, via)[0])


def _witnesses(board, via, retained, planes, width_nm, deadline):
    # This is existing-material connectivity, not a manufactured new trace
    # or a current-width exemption. Endpoint disks are strictly inside real
    # annuli and saved plane copper. Native Boolean capsule containment then
    # proves a bounded path around actual antipads/bores. No floating repair
    # of a fractured fill or a zone-owner graph vertex supplies this proof.
    sx,sy=tuple(via.GetPosition());tx,ty=tuple(retained.GetPosition())
    window=pcbnew.SHAPE_POLY_SET();window.NewOutline()
    for x,y in ((min(sx,tx)-1000000,min(sy,ty)-1000000),
            (max(sx,tx)+1000000,min(sy,ty)-1000000),
            (max(sx,tx)+1000000,max(sy,ty)+1000000),
            (min(sx,tx)-1000000,max(sy,ty)+1000000)):window.Append(x,y)
    native=[*(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks()]
    radius=min((v.GetWidth(v.TopLayer())-v.GetDrillValue())//8 for v in (via,retained))
    if radius<1000:raise ValueError('positive_annular_material_witness_required')
    def capsule(start,end,width):
        p=pcbnew.SHAPE_POLY_SET()
        pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*end),width).TransformToPolygon(
            p,1,pcbnew.ERROR_OUTSIDE)
        return p
    def ports(item,face,material):
        annulus=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(annulus,face,0,1,pcbnew.ERROR_INSIDE)
        hole=pcbnew.SHAPE_POLY_SET();item.GetEffectiveHoleShape().TransformToPolygon(hole,1,pcbnew.ERROR_OUTSIDE)
        annulus.BooleanSubtract(hole)
        r=(item.GetWidth(face)+item.GetDrillValue())/4;cx,cy=tuple(item.GetPosition());result=[]
        for n in range(16):
            _tick(deadline);angle=math.tau*n/16;at=(round(cx+r*math.cos(angle)),round(cy+r*math.sin(angle)))
            disk=capsule(at,at,2*radius)
            for shape in (annulus,material):
                missing=pcbnew.SHAPE_POLY_SET(disk);missing.BooleanSubtract(shape)
                if missing.OutlineCount():break
            else:result.append(at)
        return result
    from shapely.geometry import Point
    work=physical._Work(deadline)
    witnesses=[]
    for zone in board.Zones():
        _tick(deadline)
        if zone.GetIsRuleArea() or zone.GetNetname() != 'GND':
            continue
        for face in sorted(planes):
            if not zone.IsOnLayer(face):
                continue
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(face):
                raise ValueError('stale_local_ground_reference_fill_unknown')
            copper=zone.GetFilledPolysList(face)
            if not all(copper.Collide(v.GetEffectiveShape(face), 0) for v in (via, retained)):
                continue
            material=pcbnew.SHAPE_POLY_SET(copper);material.BooleanIntersection(window)
            # Native fills do not necessarily encode drill voids. Subtract
            # ALL local real bores, including foreign and nonplated holes.
            for item in [via,*native]:
                _tick(deadline)
                if not (item.GetClass()=='PCB_VIA' and item.IsOnLayer(face)
                        or item.GetClass()=='PAD' and item.HasHole()):continue
                if not window.BBox().Intersects(item.GetBoundingBox()):continue
                hole=pcbnew.SHAPE_POLY_SET();item.GetEffectiveHoleShape().TransformToPolygon(hole,1,pcbnew.ERROR_OUTSIDE)
                material.BooleanSubtract(hole)
            starts,ends=ports(via,face,material),ports(retained,face,material)
            # A via can join TWO disconnected islands belonging to the same
            # zone UUID. Every possible old annular-contact island must reach
            # the unchanged bridge, not just the easiest sampled contact.
            # Decode only this native-clipped bounded neighbourhood, never
            # repair a whole-board fill with buffer(0).
            annulus=physical._shape(via,face,True,work).difference(physical._hole(via,False,work))
            islands=[p for p in physical._parts(physical._poly(material,work))
                if p.intersection(annulus).area>0]
            paths=[]
            for island in islands:
                pairs=sorted(((s,t) for s in starts for t in ends
                    if island.contains(Point(*s)) and island.contains(Point(*t))),
                    key=lambda pair:math.dist(*pair))
                path=None
                for start,end in pairs[:16]:
                    options=[[start,end],[start,(end[0],start[1]),end],[start,(start[0],end[1]),end]]
                    for points in options:
                        _tick(deadline);missing=pcbnew.SHAPE_POLY_SET()
                        for p,q in zip(points,points[1:]):missing.BooleanAdd(capsule(p,q,2*radius))
                        missing.BooleanSubtract(material)
                        if not missing.OutlineCount():path=points;break
                    if path:break
                if not path:break
                paths.append(path)
            if islands and len(paths)==len(islands):
                witnesses.append(dict(zone_uuid=force._uid(zone), layer=int(face),
                    native_existing_material_capsules_and_annular_disks=True,
                    all_possible_source_annular_contact_islands_received=True,
                    source_contact_islands=len(islands),
                    existing_material_paths_nm=[[list(p) for p in path] for path in paths],
                    connectivity_witness_width_nm=2*radius,
                    witness_is_not_a_new_trace_or_current_rating=True,
                    current_or_inductance_qualified=False))
    _tick(deadline)
    return witnesses


def plan(board, via_uuid, *, allow_source_locked=False, max_bridge_mm=2., timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    if (type(via_uuid) is not str or not via_uuid or type(allow_source_locked) is not bool
            or type(max_bridge_mm) not in (int, float) or not math.isfinite(max_bridge_mm)
            or not 0 < max_bridge_mm <= 3.):
        raise ValueError('bounded_exact_stale_local_ground_scope_required')
    tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    zones=list(board.Zones());layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    if len(tracks)+len(pads)+len(zones)>16384:
        raise ValueError('stale_local_ground_native_inventory_bound')
    via=next((v for v in tracks if force._uid(v)==via_uuid),None)
    if (via is None or via.GetClass()!='PCB_VIA' or via.GetNetname()!='GND'
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH or via.TopLayer()!=pcbnew.F_Cu
            or via.BottomLayer()!=pcbnew.B_Cu or via.IsLocked() and not allow_source_locked):
        raise ValueError('explicit_generated_ground_through_barrel_required')
    groups=[g for g in board.Groups() if g.ContainsItem(via)]
    if (len(groups)!=1 or groups[0].GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP
            or groups[0].IsLocked()):
        raise ValueError('only_unlocked_generated_local_factory_tag_required')
    ordinary=fab.board_legal_through_via_geometry(board,
        via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6)
    if (fab.local_pofv_via_decision(board,via)[0]
            or via.GetWidth(via.TopLayer())>=round(ordinary[0]*1e6)
               and via.GetDrillValue()>=round(ordinary[1]*1e6)):
        raise ValueError('ordinary_or_live_local_ground_via_cannot_be_retired')
    shapes={l:via.GetEffectiveShape(l) for l in layers if via.IsOnLayer(l)}
    if len(shapes)!=len(layers):
        raise ValueError('complete_ground_through_layer_span_required')
    for item in [*pads,*tracks]:
        _tick(deadline)
        if force._uid(item)==via_uuid:
            continue
        if any(item.IsOnLayer(l) and shape.Collide(item.GetEffectiveShape(l),0)
               for l,shape in shapes.items()):
            raise ValueError('stale_local_ground_has_live_land_or_route_contact')
    plane_ids={int(board.GetLayerID(n)) for n in fr.plane_layers(board)}
    touched=set()
    for zone in zones:
        _tick(deadline)
        if zone.GetIsRuleArea():
            continue
        for l,shape in shapes.items():
            if not zone.IsOnLayer(l):
                continue
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(l):
                if zone.Outline().Collide(shape,0):
                    raise ValueError('stale_local_ground_contact_fill_unknown')
                continue
            if not zone.GetFilledPolysList(l).Collide(shape,0):
                continue
            if zone.GetNetname()!='GND' or l not in plane_ids:
                raise ValueError('stale_local_ground_has_unowned_or_surface_zone_contact')
            touched.add(l)
    if len(touched)<2:
        raise ValueError('two_actual_reference_plane_contacts_required')
    choices=sorted((v for v in tracks if force._uid(v)!=via_uuid and v.GetClass()=='PCB_VIA'
        and v.GetNetname()=='GND' and math.dist(tuple(v.GetPosition()),tuple(via.GetPosition()))<=max_bridge_mm*1e6),
        key=lambda v:(math.dist(tuple(v.GetPosition()),tuple(via.GetPosition())),force._uid(v)))
    replacement=None;witness=[]
    for other in choices[:32]:
        _tick(deadline)
        if not _qualified_bridge(board,other):
            continue
        try:
            proof=_witnesses(board,via,other,touched,via.GetWidth(via.TopLayer()),deadline)
        except physical.Unknown as exc:
            raise ValueError('stale_local_ground_plane_material_unknown:'+str(exc)) from exc
        if {q['layer'] for q in proof}==touched:
            replacement=other;witness=proof;break
    if replacement is None:
        raise ValueError('nearby_qualified_continuous_all_plane_bridge_required')
    _tick(deadline)
    return dict(schema=1,kind='stranded_generated_local_ground_barrel',via_uuid=via_uuid,
        ground_net='GND',retired_track_uuids=[via_uuid],retired_via_uuids=[via_uuid],
        retained_root_via_uuid=force._uid(replacement),source_binding=echo._binding(board),
        allow_source_locked=allow_source_locked,max_bridge_mm=max_bridge_mm,
        source_at_nm=list(via.GetPosition()),source_diameter_nm=via.GetWidth(via.TopLayer()),
        source_drill_nm=via.GetDrillValue(),source_locked=bool(via.IsLocked()),
        source_factory_group_uuid=force._uid(groups[0]),
        saved_plane_witnesses=witness,actual_contact_plane_ids=sorted(touched),
        source_has_no_live_pad_or_route_contact=True,current_qualified=False,
        ordinary_ground_stitch_retirement_authorized=False,release_authority=False)


def subtract(board, proposal, *, timeout_s=10.):
    if echo._binding(board)!=proposal['source_binding']:
        raise ValueError('stale_local_ground_source_binding_changed')
    fresh=plan(board,proposal['via_uuid'],allow_source_locked=proposal['allow_source_locked'],
        max_bridge_mm=proposal['max_bridge_mm'],timeout_s=timeout_s)
    if fresh!=proposal:
        raise ValueError('stale_local_ground_proposal_not_independently_rederived')
    discard_items(board,[v for v in board.GetTracks() if force._uid(v)==fresh['via_uuid']])


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    deadline=tails._deadline(timeout_s)
    r=tails._receive_exact_subtraction(source,candidate,proposal,board_hint=board_hint,
        subtractor=subtract,timeout_s=timeout_s)
    r.update(scope='stranded_generated_local_ground_via_subtraction',
        retired_via_uuids=proposal.get('retired_via_uuids',[]),
        ordinary_ground_stitch_retirement_authorized=False)
    if r['ok'] and r['complete']:
        try:
            parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
            old=next(v for v in parent.GetTracks() if force._uid(v)==proposal['via_uuid'])
            retained=next(v for v in child.GetTracks() if force._uid(v)==proposal['retained_root_via_uuid'])
            if not _qualified_bridge(child,retained):
                raise ValueError('retained_ground_bridge_factory_context_lost')
            proof=_witnesses(child,old,retained,set(proposal['actual_contact_plane_ids']),
                proposal['source_diameter_nm'],deadline)
            if {q['layer'] for q in proof}!=set(proposal['actual_contact_plane_ids']):
                raise ValueError('retained_ground_bridge_plane_material_lost')
            r['saved_reference_plane_bridges_reproved_after_native_refill']=proof
        except (ValueError,StopIteration,physical.Unknown) as exc:
            r.update(ok=False,complete=False);r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def discover_from_drc(board,drc,*,authorize_source_locked=False,timeout_s=2.):
    deadline=tails._deadline(timeout_s)
    if type(drc) is not dict or type(authorize_source_locked) is not bool:
        raise ValueError('bounded_native_drc_stale_local_ground_discovery_required')
    r=dict(complete=False,plans=[],refused=[],errors=[],release_authority=False)
    try:
        live={force._uid(v):v for v in board.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()=='GND'}
        rows=drc.get('violations') or ()
        if len(rows)>16384:raise ValueError('stale_local_ground_drc_inventory_bound')
        ids=sorted({str(i.get('uuid') or '') for row in rows
            if row.get('type') in ('clearance','shorting_items','via_dangling','hole_clearance')
            for i in row.get('items') or () if str(i.get('uuid') or '') in live})
        if len(ids)>64:raise ValueError('stale_local_ground_candidate_inventory_bound')
        for uid in ids:
            _tick(deadline)
            try:
                r['plans'].append(plan(board,uid,allow_source_locked=authorize_source_locked,
                    timeout_s=max(.001,min(2.,deadline-time.monotonic()))))
            except ValueError as exc:
                _tick(deadline)
                r['refused'].append(dict(uuid=uid,reason=str(exc)))
        _tick(deadline);r['complete']=True
    except (ValueError,RuntimeError) as exc:
        r.update(plans=[],errors=[str(exc)])
    return r
