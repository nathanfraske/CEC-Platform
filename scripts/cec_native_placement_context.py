"""Native, layer/net-aware copper reservations for cooperative placement.

The caller explicitly selects immutable conductors and moving terminals. No
net, package, board, reference, current rating or coordinate policy is inferred.
These are conservative search obstacles, NOT electrical/current receiving.
Exact native clearance, holes, connectivity, source cuts and saved-board checks
remain mandatory. In particular, same-net exemption grants no hole-clearance,
via-in-pad, mating or release permission.
"""
from __future__ import annotations

import math
import time


def copper_interferes(a, b):
    """Same physical board/layer and different authored nets interfere."""
    if a.get('kind')!='copper' or b.get('kind')!='copper':
        raise ValueError('explicit_copper_context_pair_required')
    if a['context']!=b['context'] or not set(a['layers'])&set(b['layers']):return False
    return not (a['net'] and a['net']==b['net'])


def _native_stationary_land(pad, deadline):
    """Exact copper identity for a centered, drill-free symmetric native land.

    No angle/near-coordinate heuristic grants stationary-terminal authority.
    Canonical integer native outward polygons must match on every actual
    copper layer of the source and its independently rotated package clone.
    """
    import pcbnew
    import cec_native_fill_geometry as native
    if (pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
            or tuple(pad.GetOffset()) != (0, 0)
            or pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)):
        return None
    layers = tuple(map(int, pad.GetLayerSet().CuStack()))
    shapes = []
    for layer in layers:
        polygon = pcbnew.SHAPE_POLY_SET()
        pad.TransformShapeToPolygon(polygon, layer, 0, 1, pcbnew.ERROR_OUTSIDE, False)
        shapes.append(native.identity(polygon, deadline, max_vertices=4096)[0])
    return (str(pad.m_Uuid.AsString()), str(pad.GetNumber()), str(pad.GetNetname()),
            int(pad.GetNetCode()), tuple(pad.GetPosition()), tuple(pad.GetSize()),
            int(pad.GetShape()), pad.GetRoundRectRadiusRatio(), layers, tuple(shapes))


def rotate_isolated_local_cells(board, rotations, *, timeout_s=10., pivot_pad_uuids=None,
                                allow_reoriented_pivot_contacts=False):
    """Explicit cardinal poses carrying only exact private local portals.

    No source track is removed, stretched or re-netted. Every incident same-net
    lead on either a selected pad OR its barrel, on ANY actual copper layer,
    must belong to the selected local dogbone. An explicitly selected pivot
    pad may retain its external leads when exact native polygon replay
    proves its copper is stationary. Explicit reorientation mode instead
    requires positive native copper proof of EVERY old contact at the same
    fixed centre; it grants no clearance or current qualification. Other terminals/barrels still
    require private ownership on every actual layer. Shared owners, remote leads,
    drilled footprints and unknown scopes refuse before the first mutation.
    This is private construction, not clearance/current/placement admission.
    """
    import pcbnew
    if (type(rotations) is not dict or not 1 <= len(rotations) <= 16
            or any(type(ref) is not str or not ref or type(turn) is not int
                   or turn not in (0,90,180,270) for ref,turn in rotations.items())
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(allow_reoriented_pivot_contacts) is not bool):
        raise ValueError('bounded_explicit_cardinal_local_cells_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('local_cell_rotation_deadline')
    fps={f.GetReference():f for f in board.GetFootprints()}
    if (len(fps)!=len(list(board.GetFootprints())) or not set(rotations)<=fps.keys()):
        raise ValueError('unique_actual_local_cell_identity_required')
    active={ref:turn for ref,turn in rotations.items() if turn}
    pivots = {} if pivot_pad_uuids is None else pivot_pad_uuids
    if (type(pivots) is not dict or not set(pivots) <= set(rotations)
            or any(type(uid) is not str or not uid for uid in pivots.values())
            or len(set(pivots.values())) != len(pivots)):
        raise ValueError('unique_explicit_local_cell_pivot_pad_scope_required')
    for ref in active:
        fp=fps[ref]
        if (fp.IsLocked() or not list(fp.Pads()) or any(p.HasHole()
                or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in fp.Pads())):
            raise ValueError('unlocked_native_surface_local_cell_required')
    if not active:
        return dict(rotated_refs=[],rotated_conductor_uuids=[],routing_admitted=False,
                    release_authority=False)
    pivot_positions = {}
    stationary = set()
    stationary_proofs = {}
    reoriented_contact_proofs = {}
    for ref, turn in active.items():
        tick()
        fp = fps[ref]
        pivot_positions[ref] = tuple(fp.GetPosition())
        if ref not in pivots:
            continue
        selected = [p for p in fp.Pads() if p.m_Uuid.AsString() == pivots[ref]]
        if len(selected) != 1:
            raise ValueError('local_cell_pivot_pad_identity_unavailable')
        fixed = selected[0]
        pivot_positions[ref] = tuple(fixed.GetPosition())
        prior = _native_stationary_land(fixed, deadline)
        if prior is None:
            raise ValueError('local_cell_stationary_pivot_geometry_unqualified')
        # Clone retains the authored package and pad definitions. Keep the
        # owning EDA_ITEM wrapper alive while its borrowed footprint is read.
        clone = fp.Clone()
        projected = pcbnew.Cast_to_FOOTPRINT(pcbnew.Cast_to_BOARD_ITEM(clone))
        projected.Rotate(pcbnew.VECTOR2I(*pivot_positions[ref]),
                         pcbnew.EDA_ANGLE(turn, pcbnew.DEGREES_T))
        matching = [p for p in projected.Pads() if p.m_Uuid.AsString() == pivots[ref]]
        if len(matching) != 1:
            raise ValueError('local_cell_pivot_copper_not_exactly_stationary')
        exact = _native_stationary_land(matching[0], deadline) == prior
        if not exact:
            if not allow_reoriented_pivot_contacts:
                raise ValueError('local_cell_pivot_copper_not_exactly_stationary')
            from cec_native_pivot_contacts import preserve
            reoriented_contact_proofs[ref] = preserve(board, fixed, matching[0],
                deadline_monotonic=deadline)
        stationary.add(pivots[ref])
        if exact:
            stationary_proofs[ref] = prior
    portals=local_portals(board,list(active),timeout_s=max(.001,min(10.,deadline-time.monotonic())))
    if any(not row['all_source_contacts_in_scope'] for row in portals):
        raise ValueError('shared_native_local_portal_rotation_refused')
    ids={row['via_uuid'] for row in portals}
    owners={}
    for row in portals:
        refs={c['ref'] for c in row['source_contacts']}
        if len(refs)!=1:raise ValueError('unique_native_portal_rotation_owner_required')
        ref=next(iter(refs));owners[row['via_uuid']]=ref
        for contact in row['source_contacts']:
            for uid in contact['dogbone_track_uuids']:
                if uid in owners and owners[uid]!=ref:
                    raise ValueError('ambiguous_local_dogbone_rotation_owner')
                ids.add(uid);owners[uid]=ref
    tracks={str(t.m_Uuid.AsString()):t for t in board.GetTracks()}
    if len(tracks)!=len(list(board.GetTracks())) or not ids<=tracks.keys():
        raise ValueError('native_local_rotation_conductor_identity_required')
    pads=[p for ref in active for p in fps[ref].Pads()
          if p.m_Uuid.AsString() not in stationary]
    # A circular via exactly at an explicit fixed pivot is stationary too.
    # A displaced via or even one displaced dogbone endpoint is NOT exempt.
    moving_tracks = []
    for uid in ids:
        track = tracks[uid]
        pivot = pivot_positions[owners[uid]]
        fixed = (owners[uid] in pivots and
                 (tuple(track.GetPosition()) == pivot if track.GetClass() == 'PCB_VIA'
                  else tuple(track.GetStart()) == pivot and tuple(track.GetEnd()) == pivot))
        if not fixed:
            moving_tracks.append(track)
    moving=[*pads,*moving_tracks]
    layers=list(board.GetEnabledLayers().CuStack())
    external=set()
    for uid,track in tracks.items():
        tick()
        if uid in ids:continue
        for item in moving:
            tick()
            if (item.GetNetCode()>0 and track.GetNetCode()==item.GetNetCode()
                    and any(item.IsOnLayer(layer) and track.IsOnLayer(layer)
                        and item.GetEffectiveShape(layer).Collide(track.GetEffectiveShape(layer),0)
                        for layer in layers)):
                external.add(uid);break
    if external:
        raise ValueError('external_native_local_cell_leads_require_reconstruction:'+','.join(sorted(external)))
    original={ref:dict(origin_nm=list(fps[ref].GetPosition()),
        angle_deg=fps[ref].GetOrientationDegrees()) for ref in active}
    # All ownership checks finish before mutation. Actual native Rotate keeps
    # pad geometry, drills, barrels and dogbones in the SAME rigid transform.
    for ref,turn in active.items():
        pivot=pcbnew.VECTOR2I(*pivot_positions[ref])
        angle=pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T)
        fps[ref].Rotate(pivot,angle)
        for uid,owner in owners.items():
            if owner==ref:tracks[uid].Rotate(pivot,angle)
    return dict(rotated_refs=sorted(active),rotated_conductor_uuids=sorted(ids),
        original_poses=original,turns_deg=active,native_source_portals=portals,
        pivot_pad_uuids=dict(pivots),pivot_positions_nm={ref:list(at) for ref,at in pivot_positions.items()},
        exact_stationary_pivot_land_replay=stationary_proofs,
        source_reoriented_pivot_contact_replay=reoriented_contact_proofs,
        allow_reoriented_pivot_contacts=allow_reoriented_pivot_contacts,
        remote_copper_stretched=False,source_items_retired=False,
        independent_saved_connectivity_and_physical_receiving_required=True,
        routing_admitted=False,release_authority=False)


def members(board, *, context, footprint_refs=(), track_uuids=(), zone_uuids=(),
            clearance_nm=200000, timeout_s=10.):
    """Read actual selected native pads, barrels, tracks and zone contours.

    Native outward polygonization plus half the explicitly supplied clearance
    on each member makes search conservative. A declared immutable zone's
    entire authored outline is reserved, not a stale renderer or mutable GND
    plane. The caller decides which zones are immutable. Unsupported geometry,
    stale IDs, duplicates and unknown inventories refuse before returning.
    Multi-layer pads/barrels retain ALL actual enabled copper layers; a front
    SMT pad can still sit above back copper, whereas a PTH barrel cannot.
    """
    import pcbnew
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if (type(context) is not int or not 0<=context<=63
            or type(clearance_nm) is not int or not 0<=clearance_nm<=10000000
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):
        raise ValueError('bounded_native_placement_context_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_placement_context_deadline')
    def scope(values):
        if (not isinstance(values,(tuple,list,set,frozenset)) or len(values)>4096
                or any(type(v) is not str or not v for v in values)
                or len(values)!=len(set(values))):
            raise ValueError('unique_explicit_native_placement_scope_required')
        return set(values)
    refs,tids,zids=map(scope,(footprint_refs,track_uuids,zone_uuids))
    enabled=set(board.GetEnabledLayers().CuStack())
    fp_list=list(board.GetFootprints());track_list=list(board.GetTracks());zone_list=list(board.Zones())
    if len(fp_list)+len(track_list)+len(zone_list)>32768:
        raise ValueError('native_placement_context_inventory_bound')
    fps={f.GetReference():f for f in fp_list}
    tracks={str(t.m_Uuid.AsString()):t for t in track_list}
    zones={str(z.m_Uuid.AsString()):z for z in zone_list}
    if (len(fps)!=len(fp_list) or len(tracks)!=len(track_list) or len(zones)!=len(zone_list)):
        raise ValueError('native_placement_context_ambiguous_identity')
    if not refs<=fps.keys() or not tids<=tracks.keys() or not zids<=zones.keys():
        raise ValueError('native_placement_context_stale_scope')
    rows=[];vertices=0;identical_layer_shapes={}
    def geometry(poly):
        nonlocal vertices
        parts=[]
        for n in range(poly.OutlineCount()):
            tick();rings=[]
            for chain in [poly.Outline(n),*[poly.Hole(n,h) for h in range(poly.HoleCount(n))]]:
                count=chain.PointCount();vertices+=count
                if chain.ArcCount() or count<3 or vertices>200000:
                    raise ValueError('native_placement_context_polygon_bound')
                points=[(chain.CPoint(i).x/1e6,chain.CPoint(i).y/1e6) for i in range(count)]
                if not all(math.isfinite(v) and abs(v)<=2000 for point in points for v in point):
                    raise ValueError('native_placement_context_coordinate_bound')
                rings.append(points)
            polygon=Polygon(rings[0],rings[1:])
            if polygon.is_empty or not polygon.is_valid or polygon.area<=0:
                raise ValueError('native_placement_context_valid_native_contour_required')
            parts.append(polygon)
        if not parts:raise ValueError('native_placement_context_empty_native_contour')
        # 1 um outward polygonization error is retained even for exact lines.
        return unary_union(parts).buffer(clearance_nm/2e6+.001,resolution=16)
    def add(item,poly,layers,ref=None):
        tick();uid=str(item.m_Uuid.AsString())
        if not layers or len(rows)>=4096:
            raise ValueError('native_placement_context_member_or_layer_bound')
        # Through barrels often have the exact same native land on six or
        # more layers. Coalesce ONLY literally identical native geometry,
        # retaining the union of actual layers. Custom per-layer geometry
        # stays separate. This reduces placement work without promoting a
        # front SMT pad or losing a single barrel layer.
        key=(uid,poly.Format())
        if key in identical_layer_shapes:
            row=identical_layer_shapes[key]
            row['layers']=tuple(sorted(set(row['layers'])|set(layers)))
            return
        row=dict(kind='copper',context=context,ref=ref,uuid=uid,
            native_kind=item.GetClass(),net=str(item.GetNetname()),layers=tuple(sorted(layers)),
            geometry=geometry(poly),clearance_nm=clearance_nm,
            basis='outward_native_shape_or_full_declared_immutable_zone',
            electrical_or_release_authority=False)
        rows.append(row);identical_layer_shapes[key]=row
    for ref in sorted(refs):
        for pad in fps[ref].Pads():
            tick();layers=set(pad.GetLayerSet().CuStack())&enabled
            # A non-copper aperture is not silently promoted to copper. Hole
            # placement still needs its separate native physical receiving.
            if not layers:continue
            # Layer-specific custom/annular geometry must stay distinct.
            for layer in sorted(layers):
                poly=pcbnew.SHAPE_POLY_SET()
                pad.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE)
                if poly.OutlineCount():add(pad,poly,[int(layer)],ref)
    for uid in sorted(tids):
        item=tracks[uid];kind=item.GetClass()
        if kind not in ('PCB_TRACK','PCB_VIA','PCB_ARC'):
            raise ValueError('native_placement_context_unsupported_conductor')
        layers=[int(layer) for layer in enabled if item.IsOnLayer(layer)]
        for layer in sorted(layers):
            poly=pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(poly,layer,0,1000,pcbnew.ERROR_OUTSIDE)
            add(item,poly,[layer])
    for uid in sorted(zids):
        zone=zones[uid]
        if zone.GetIsRuleArea():raise ValueError('native_placement_context_not_a_copper_zone')
        layers=[int(layer) for layer in enabled if zone.IsOnLayer(layer)]
        add(zone,zone.Outline(),layers)
    tick()
    return rows


def local_portals(board, footprint_refs, *, dogbone_nm=1500000, timeout_s=10.):
    """Locate actual source barrels attached to the explicitly selected cell.

    A via must touch a selected pad, or the EXACT endpoint of one short
    same-net native track whose other endpoint is in that pad. Nearness is
    never connectivity. Shared terminal contacts are reported, not reassigned;
    the caller must preserve every owner's transform before moving a barrel.
    This inventory is read-only and grants no trace retirement, via-in-pad,
    factory, current or electrical admission. Remote explicitly owned portals
    need separate source lineage rather than a larger proximity guess.
    """
    deadline=time.monotonic()+timeout_s if type(timeout_s) in (int,float) else 0
    if (not isinstance(footprint_refs,(tuple,list,set,frozenset))
            or not 1<=len(footprint_refs)<=256
            or any(type(ref) is not str or not ref for ref in footprint_refs)
            or len(set(footprint_refs))!=len(footprint_refs)
            or type(dogbone_nm) is not int or not 0<=dogbone_nm<=1500000
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):
        raise ValueError('bounded_explicit_local_portal_scope_required')
    def tick():
        if time.monotonic()>=deadline:raise ValueError('local_portal_inventory_deadline')
    refs=set(footprint_refs);fps=list(board.GetFootprints());tracks=list(board.GetTracks())
    if len(fps)+len(tracks)>32768 or len({fp.GetReference() for fp in fps})!=len(fps):
        raise ValueError('local_portal_native_inventory_bound_or_ambiguous_refs')
    if not refs<={fp.GetReference() for fp in fps}:
        raise ValueError('local_portal_stale_footprint_scope')
    pads=[pad for fp in fps for pad in fp.Pads()]
    if len(pads)>16384:raise ValueError('local_portal_pad_inventory_bound')
    selected=[pad for pad in pads if pad.GetParentFootprint().GetReference() in refs]
    layers=tuple(board.GetEnabledLayers().CuStack())
    vias=[t for t in tracks if t.GetClass()=='PCB_VIA' and t.GetNetCode()>0]
    at_vias={}
    for via in vias:at_vias.setdefault((tuple(via.GetPosition()),via.GetNetCode()),[]).append(via)
    attached={}
    def attach(via,pad,track=None):
        uid=str(via.m_Uuid.AsString());puid=str(pad.m_Uuid.AsString())
        row=attached.setdefault(uid,dict(via_uuid=uid,net=str(via.GetNetname()),
            position_nm=list(via.GetPosition()),source_contacts={},shared_pad_contacts=[],shared_dogbone_contacts=[],
            automatic_motion_or_retirement_authority=False,electrical_or_release_authority=False))
        contact=row['source_contacts'].setdefault(puid,dict(pad_uuid=puid,
            ref=pad.GetParentFootprint().GetReference(),pin=str(pad.GetNumber()),
            position_nm=list(pad.GetPosition()),direct=False,dogbone_track_uuids=[]))
        if track is None:contact['direct']=True
        else:
            tid=str(track.m_Uuid.AsString())
            if tid not in contact['dogbone_track_uuids']:contact['dogbone_track_uuids'].append(tid)
    for pad in selected:
        tick()
        if pad.GetNetCode()<=0:continue
        for via in vias:
            tick()
            if via.GetNetCode()!=pad.GetNetCode() or not pad.GetBoundingBox().Intersects(via.GetBoundingBox()):continue
            if any(pad.IsOnLayer(layer) and via.IsOnLayer(layer)
                    and pad.GetEffectiveShape(layer).Collide(via.GetEffectiveShape(layer),0)
                    for layer in layers):attach(via,pad)
        if not dogbone_nm:continue
        for track in tracks:
            tick()
            if (track.GetClass()!='PCB_TRACK' or track.GetNetCode()!=pad.GetNetCode()
                    or track.GetLength()>dogbone_nm or not pad.IsOnLayer(track.GetLayer())
                    or not pad.GetBoundingBox().Intersects(track.GetBoundingBox())):continue
            for point,other in ((track.GetStart(),track.GetEnd()),(track.GetEnd(),track.GetStart())):
                if not pad.GetEffectiveShape(track.GetLayer()).Collide(point,0):continue
                for via in at_vias.get((tuple(other),track.GetNetCode()),[]):
                    if via.IsOnLayer(track.GetLayer()):attach(via,pad,track)
    live={str(via.m_Uuid.AsString()):via for via in vias}
    # A second owner's short track to the same barrel is just as real as a
    # second pad touching it. Inventory these exact contacts too; selecting
    # only one owner cannot silently reassign a shared local return.
    requested_at={}
    for uid in attached:
        requested_at.setdefault((tuple(live[uid].GetPosition()),live[uid].GetNetCode()),[]).append(uid)
    for track in tracks:
        tick()
        if track.GetClass()!='PCB_TRACK' or track.GetLength()>dogbone_nm:continue
        for point,other in ((track.GetStart(),track.GetEnd()),(track.GetEnd(),track.GetStart())):
            uids=requested_at.get((tuple(other),track.GetNetCode()),())
            if not uids:continue
            for pad in pads:
                tick()
                if (pad.GetNetCode()!=track.GetNetCode() or not pad.IsOnLayer(track.GetLayer())
                        or not pad.GetBoundingBox().Intersects(track.GetBoundingBox())
                        or not pad.GetEffectiveShape(track.GetLayer()).Collide(point,0)):continue
                for uid in uids:
                    attached[uid]['shared_dogbone_contacts'].append(dict(pad_uuid=str(pad.m_Uuid.AsString()),
                        track_uuid=str(track.m_Uuid.AsString()),ref=pad.GetParentFootprint().GetReference(),
                        pin=str(pad.GetNumber()),net=str(pad.GetNetname()),
                        selected_owner=pad.GetParentFootprint().GetReference() in refs))
    for uid,row in attached.items():
        tick();via=live[uid]
        for pad in pads:
            tick()
            if not pad.GetBoundingBox().Intersects(via.GetBoundingBox()):continue
            if any(pad.IsOnLayer(layer) and via.IsOnLayer(layer)
                    and pad.GetEffectiveShape(layer).Collide(via.GetEffectiveShape(layer),0)
                    for layer in layers):
                row['shared_pad_contacts'].append(dict(pad_uuid=str(pad.m_Uuid.AsString()),
                    ref=pad.GetParentFootprint().GetReference(),pin=str(pad.GetNumber()),
                    net=str(pad.GetNetname()),selected_owner=pad.GetParentFootprint().GetReference() in refs))
        row['source_contacts']=sorted(row['source_contacts'].values(),key=lambda r:r['pad_uuid'])
        row['all_actual_pad_contacts_in_scope']=all(r['selected_owner'] for r in row['shared_pad_contacts'])
        row['all_source_contacts_in_scope']=row['all_actual_pad_contacts_in_scope'] and all(
            r['selected_owner'] for r in row['shared_dogbone_contacts'])
    tick()
    return sorted(attached.values(),key=lambda r:r['via_uuid'])


def new_foreign_pad_contacts(source, candidate, *, footprint_refs, track_uuids,
                             timeout_s=2.):
    """Read new exact native shorts caused by an explicit relocation scope.

    Same UUIDs/nets must resolve in both boards. A prior contact with the SAME
    foreign pad is reported as inherited, never silently promoted to legal.
    Only enabled, common physical layers count. This is an identity-backed
    forensic/reroute-debt inventory, NOT clearance receiving, ripup permission,
    source-net normalization, current qualification or release authority.
    """
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):
        raise ValueError('native_motion_contacts_bounded_budget_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_motion_contacts_deadline')
    def scope(values):
        if (not isinstance(values,(list,tuple,set,frozenset)) or not 1<=len(values)<=4096
                or any(type(v) is not str or not v for v in values)
                or len(values)!=len(set(values))):
            raise ValueError('native_motion_contacts_unique_explicit_scope_required')
        return set(values)
    refs,ids=scope(footprint_refs),scope(track_uuids)
    def inventory(board):
        fps={};tracks={};pads={}
        for fp in board.GetFootprints():
            tick();ref=str(fp.GetReference())
            if ref in fps or len(fps)>=4096:
                raise ValueError('native_motion_contacts_ambiguous_footprints')
            fps[ref]=fp
            for pad in fp.Pads():
                tick();uid=str(pad.m_Uuid.AsString())
                if uid in pads or len(pads)>=16384:
                    raise ValueError('native_motion_contacts_ambiguous_pads')
                pads[uid]=pad
        for item in board.GetTracks():
            tick();uid=str(item.m_Uuid.AsString())
            if uid in tracks or len(tracks)>=32768:
                raise ValueError('native_motion_contacts_ambiguous_tracks')
            tracks[uid]=item
        if not refs<=fps.keys() or not ids<=tracks.keys():
            raise ValueError('native_motion_contacts_stale_scope')
        return fps,tracks,pads
    old_fps,old_tracks,old_pads=inventory(source)
    fps,tracks,pads=inventory(candidate)
    layers=set(candidate.GetEnabledLayers().CuStack())
    if layers!=set(source.GetEnabledLayers().CuStack()):
        raise ValueError('native_motion_contacts_changed_layer_stack')
    selected=[]
    for ref in sorted(refs):
        if str(fps[ref].m_Uuid.AsString())!=str(old_fps[ref].m_Uuid.AsString()):
            raise ValueError('native_motion_contacts_changed_footprint_identity')
        for pad in fps[ref].Pads():
            uid=str(pad.m_Uuid.AsString());prior=old_pads.get(uid)
            if (prior is None or str(prior.GetNetname())!=str(pad.GetNetname())
                    or str(prior.GetNumber())!=str(pad.GetNumber())
                    or str(prior.GetParentFootprint().GetReference())!=ref):
                raise ValueError('native_motion_contacts_changed_pad_identity')
            if pad.GetNetCode()>0 and pad.IsOnCopperLayer():selected.append(pad)
    contacts=[]
    for uid in sorted(ids):
        tick();item=tracks[uid];prior=old_tracks[uid]
        if (item.GetClass() not in ('PCB_TRACK','PCB_VIA','PCB_ARC')
                or prior.GetClass()!=item.GetClass()
                or str(prior.GetNetname())!=str(item.GetNetname()) or item.GetNetCode()<=0):
            raise ValueError('native_motion_contacts_changed_track_identity')
        for pad in selected:
            tick()
            if str(item.GetNetname())==str(pad.GetNetname()) or not item.GetBoundingBox().Intersects(pad.GetBoundingBox()):continue
            touched=[int(layer) for layer in sorted(layers) if item.IsOnLayer(layer) and pad.IsOnLayer(layer)
                     and item.GetEffectiveShape(layer).Collide(pad.GetEffectiveShape(layer),0)]
            if not touched:continue
            puid=str(pad.m_Uuid.AsString());old_pad=old_pads[puid]
            inherited=any(prior.IsOnLayer(layer) and old_pad.IsOnLayer(layer)
                and prior.GetEffectiveShape(layer).Collide(old_pad.GetEffectiveShape(layer),0) for layer in layers)
            if len(contacts)>=16384:raise ValueError('native_motion_contacts_result_bound')
            contacts.append(dict(track_uuid=uid,native_kind=item.GetClass(),net=str(item.GetNetname()),
                pad_uuid=puid,ref=str(pad.GetParentFootprint().GetReference()),pin=str(pad.GetNumber()),
                foreign_net=str(pad.GetNetname()),layers=touched,inherited_contact=bool(inherited),
                new_contact=not inherited,automatic_ripup_authorized=False))
    return dict(schema=1,contacts=contacts,new_contacts=[r for r in contacts if r['new_contact']],
        inherited_contacts=[r for r in contacts if r['inherited_contact']],
        exact_native_overlap_only=True,clearance_qualified=False,release_authority=False)
