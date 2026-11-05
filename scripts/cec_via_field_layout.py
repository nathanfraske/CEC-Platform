"""Bounded symmetric exact-count via-field proposals, not current authority.

The caller supplies its existing pitch, reach and required barrel count.
Every selected site still requires clearance, full native landings, current,
field and fabrication receiving. Symmetry cannot lower the required count or
the rated copper width. Owned relocation mutates only caller-owned private
candidates; it never saves, promotes or changes a project's source board.
"""
from __future__ import annotations


def centered_offsets(count, *, pitch_nm, reach_nm, limit=24):
    """Deterministic integer-lattice portfolios centered exactly at (0, 0).

    Even row/column counts use half-pitch offsets. Incomplete rectangles lose
    opposite pairs, never a prefix of a ring. Thus ten barrels need not be a
    3x3 field with one side outlier. The legacy reach stays a hard bound.
    """
    if (type(count) is not int or not 1 <= count <= 25
            or type(pitch_nm) is not int or not 2 <= pitch_nm <= 10000000
            or pitch_nm % 2 or type(reach_nm) is not int
            or not 1 <= reach_nm <= 100000000
            or type(limit) is not int or not 0 <= limit <= 32):
        raise ValueError("invalid bounded symmetric field declaration")
    options = set()
    for columns in range(1, 26):
        for rows in range(1, 26):
            seats = columns * rows
            if not count <= seats <= 25:
                continue
            points = {(int((2*x-columns+1)*pitch_nm//2),
                       int((2*y-rows+1)*pitch_nm//2))
                      for x in range(columns) for y in range(rows)}
            if any(abs(x) > reach_nm or abs(y) > reach_nm for x, y in points):
                continue
            origin = (0, 0) in points
            if count % 2 and not origin:
                continue
            pairs = sorted((point for point in points if point > (0, 0)),
                key=lambda p: (p[0]*p[0]+p[1]*p[1], p))
            if len(pairs) < count // 2:
                continue
            chosen = {(0, 0)} if count % 2 else set()
            for x, y in pairs[:count//2]:
                chosen.update(((x, y), (-x, -y)))
            if len(chosen) == count:
                options.add(tuple(sorted(chosen)))
                # Reflection is a distinct legal alternative if an obstacle
                # blocks only one diagonal's omitted opposite-corner pair.
                options.add(tuple(sorted((-x, y) for x, y in chosen)))
    def rank(points):
        xs, ys = zip(*points)
        width, height = max(xs)-min(xs), max(ys)-min(ys)
        return (max(x*x+y*y for x, y in points), abs(width-height),
                (width+pitch_nm)*(height+pitch_nm), points)
    return tuple(sorted(options, key=rank)[:limit])


def shape_evidence(sites_nm, center_nm):
    """Exact integer symmetry/centroid observation, never an electrical pass."""
    sites = tuple(tuple(point) for point in sites_nm)
    if (not sites or len(sites) > 25 or len(set(sites)) != len(sites)
            or len(center_nm) != 2 or any(type(v) is not int for v in center_nm)
            or any(len(p) != 2 or any(type(v) is not int for v in p) for p in sites)):
        raise ValueError("invalid native field observation")
    cx, cy = center_nm
    symmetric = all((2*cx-x, 2*cy-y) in sites for x, y in sites)
    delta = [sum(p[i]-center_nm[i] for p in sites) for i in range(2)]
    return dict(count=len(sites), center_nm=list(center_nm),
                rotationally_symmetric=symmetric, centroid_delta_sum_nm=delta,
                centered=delta == [0, 0], release_authority=False,
                electrical_rating_qualified=False)


def _via_row(via):
    import cec_rectilinear_copper as native
    at=via.GetPosition()
    return dict(uuid=via.m_Uuid.AsString(),net=via.GetNetname(),
        position_nm=[int(at.x),int(at.y)],diameter_nm=int(via.GetWidth(via.TopLayer())),
        drill_nm=int(via.GetDrillValue()),via_type=int(via.GetViaType()),
        layers=[int(via.TopLayer()),int(via.BottomLayer())],locked=bool(via.IsLocked()),
        group_uuid=native._group_uuid(via))


def _disk(board,net,layer,at,diameter):
    import pcbnew
    import cec_rectilinear_copper as native
    prototype=pcbnew.PCB_TRACK(board);prototype.SetNet(board.FindNet(net))
    prototype.SetLayer(layer);prototype.SetStart(pcbnew.VECTOR2I(*at))
    prototype.SetEnd(pcbnew.VECTOR2I(*at));prototype.SetWidth(diameter)
    return native._native_capsule(prototype)


def _actual_copper(board,net,layer,deadline=None):
    import time
    import pcbnew
    import cec_rectilinear_copper as native
    deadline=deadline or time.monotonic()+10
    if len(list(board.GetTracks()))>8192 or len(list(board.Zones()))>8192:
        raise native.Refused("field_native_inventory_bound")
    union=pcbnew.SHAPE_POLY_SET()
    for zone in board.Zones():
        native._check_deadline(deadline)
        if (not zone.GetIsRuleArea() and zone.GetNetname()==net and zone.IsOnLayer(layer)
                and zone.IsFilled() and zone.HasFilledPolysForLayer(layer)):
            union.BooleanAdd(zone.GetFilledPolysList(layer))
    for item in board.GetTracks():
        native._check_deadline(deadline)
        if item.GetClass()=="PCB_TRACK" and item.GetNetname()==net and item.IsOnLayer(layer):
            poly=pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(poly,layer,0,1,pcbnew.ERROR_OUTSIDE,False)
            union.BooleanAdd(poly)
    return union


def plan_owned_field(board,via_uuids,*,center_zone_uuid,expand_zone_uuids=(),
        pitch_nm,reach_nm,clearance_nm,allow_locked_via_uuids=(),
        allow_grouped_via_uuids=(),allow_locked_zone_uuids=(),allow_grouped_zone_uuids=(),
        rebuild_center_landing=False,required_center_width_nm=None,center_edge_margin_nm=100000):
    """Propose an owned relocation into an actual existing landing's center.

    Count, barrels, locks and layer span never change. By default the center
    landing must already contain every proposed disk. A separately declared
    center recompile can rebuild that one landing from the complete joint
    resident inventory, exact centroid and caller's existing width floor;
    whole-board receiving must prove all prior electrical/current contacts.
    Explicitly owned other-side landing
    declarations may only expand outward; no existing copper is narrowed.
    This grants no current-sharing or Kelvin authority. Saved native fills and
    independent whole-board electrical/field/DRC receiving remain mandatory.
    """
    import time
    import pcbnew
    import cec_rectilinear_copper as native
    import cec_rounded_landing as zones
    deadline=time.monotonic()+10
    if (type(clearance_nm) is not int or not 0<=clearance_nm<=10000000
            or type(rebuild_center_landing) is not bool
            or (not rebuild_center_landing and required_center_width_nm is not None)
            or (rebuild_center_landing and (type(required_center_width_nm) is not int
                or not 1<=required_center_width_nm<=100000000))
            or type(center_edge_margin_nm) is not int or not 1<=center_edge_margin_nm<=1000000):
        raise native.Refused("invalid_field_clearance")
    wanted=list(via_uuids)
    if not 1<=len(wanted)<=25 or len(set(wanted))!=len(wanted):
        raise native.Refused("explicit_unique_owned_field_required")
    vias={v.m_Uuid.AsString():v for v in board.GetTracks() if v.GetClass()=="PCB_VIA"}
    if not set(wanted)<=vias.keys():raise native.Refused("owned_barrel_missing")
    rows=[_via_row(vias[u]) for u in sorted(wanted)]
    keys={(r["net"],r["diameter_nm"],r["drill_nm"],r["via_type"],tuple(r["layers"])) for r in rows}
    if (len(keys)!=1 or not rows[0]["net"] or rows[0]["via_type"]!=int(pcbnew.VIATYPE_THROUGH)
            or not 0<rows[0]['drill_nm']<rows[0]['diameter_nm']<=10000000):
        raise native.Refused("one_through_barrel_field_required")
    if any(r["locked"] and r["uuid"] not in set(allow_locked_via_uuids)
            or r["group_uuid"] and r["uuid"] not in set(allow_grouped_via_uuids) for r in rows):
        raise native.Refused("explicit_field_lock_group_authority_required")
    zmap={z.m_Uuid.AsString():z for z in board.Zones()}
    if center_zone_uuid not in zmap:raise native.Refused("actual_center_landing_missing")
    center_source=zones._native_source(zmap[center_zone_uuid]);c=center_source["configuration"]
    net=rows[0]["net"]
    if c["net"]!=net or c["rule_area"] or c["connection"]!=int(pcbnew.ZONE_CONNECTION_FULL):
        raise native.Refused("actual_same_net_solid_center_landing_required")
    pts=center_source["outline_nm"]
    center=tuple((min(p[i] for p in pts)+max(p[i] for p in pts))//2 for i in range(2))
    if rebuild_center_landing:
        if (c['locked'] and center_zone_uuid not in set(allow_locked_zone_uuids)
                or c['group_uuid'] and center_zone_uuid not in set(allow_grouped_zone_uuids)):
            raise native.Refused('explicit_center_rebuild_owner_required')
        sums=[sum(r['position_nm'][i] for r in rows) for i in range(2)]
        if any(v%len(rows) for v in sums):
            raise native.Refused('integer_native_barrel_centroid_required')
        center=tuple(v//len(rows) for v in sums)
    expand=[]
    if len(set(expand_zone_uuids))!=len(expand_zone_uuids) or len(expand_zone_uuids)>4:
        raise native.Refused("bounded_unique_expansion_landings_required")
    for uid in expand_zone_uuids:
        if uid not in zmap:raise native.Refused("expansion_landing_missing")
        src=zones._native_source(zmap[uid]);cfg=src["configuration"]
        if (cfg["net"]!=net or cfg["rule_area"] or cfg["connection"]!=int(pcbnew.ZONE_CONNECTION_FULL)
                or cfg["locked"] and uid not in set(allow_locked_zone_uuids)
                or cfg["group_uuid"] and uid not in set(allow_grouped_zone_uuids)):
            raise native.Refused("explicit_same_net_solid_expansion_owner_required")
        expand.append(src)
    if rebuild_center_landing:
        # Complete spatial membership across BOTH old native landings; a
        # bbox prefix can lose a corner barrel from an octagonal landing.
        domain=native._poly(center_source['outline_nm'])
        for src in expand:domain.BooleanAdd(native._poly(src['outline_nm']))
        contained=set()
        for uid,via in vias.items():
            native._check_deadline(deadline)
            if via.GetNetname()!=net:continue
            r=_via_row(via)
            disk=_disk(board,net,c['layers'][0],r['position_nm'],r['diameter_nm'])
            disk.BooleanSubtract(domain)
            if not disk.OutlineCount():contained.add(uid)
        if contained!=set(wanted):raise native.Refused('complete_joint_landing_barrel_inventory_required')
    layers={c['layers'][0],*(src['configuration']['layers'][0] for src in expand)}
    supporting_tracks={str(layer):sorted((native._track_row(t) for t in board.GetTracks()
        if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net and t.IsOnLayer(layer)),key=lambda r:r['uuid']) for layer in layers}
    if sum(map(len,supporting_tracks.values()))>8192:raise native.Refused('field_native_support_inventory_bound')
    def landing_copper(zone,layer):
        # KiCad may omit same-net resident tracks from an individual zone's
        # fill. Include those REAL, identity-bound tracks, but never a ghost
        # slab or copper outside this declared landing's native outline.
        actual=zone.GetFilledPolysList(layer).CloneDropTriangulation()
        by_id={t.m_Uuid.AsString():t for t in board.GetTracks()}
        for row in supporting_tracks[str(layer)]:actual.BooleanAdd(native._native_capsule(by_id[row['uuid']]))
        actual.BooleanIntersection(zone.Outline())
        return actual
    actual=landing_copper(zmap[center_zone_uuid],c['layers'][0]);attempts=[]
    foreign=[*board.GetTracks(),*[pad for fp in board.GetFootprints() for pad in fp.Pads()]]
    if len(foreign)>16384:raise native.Refused("field_foreign_inventory_bound")
    for offsets in centered_offsets(len(rows),pitch_nm=pitch_nm,reach_nm=reach_nm):
        native._check_deadline(deadline)
        sites=[list((center[0]+x,center[1]+y)) for x,y in offsets]
        failure=None
        rebuilt_center=None
        if rebuild_center_landing:
            from cec_field_landing import _geometry
            target_rows=[dict(rows[i],position_nm=site) for i,site in enumerate(sites)]
            rebuilt_center,_=_geometry(target_rows,required_center_width_nm,center_edge_margin_nm,'chamfer45')
            try:native._require_unoccupied_outline(board,native._poly(rebuilt_center),net,c['layers'][0],deadline,
                clearance_nm=max(clearance_nm,c['clearance_nm']))
            except native.Refused as exc:failure='rebuilt_center_native_clearance:'+str(exc)
        if failure:
            attempts.append(dict(sites_nm=sites,refused=failure));continue
        for site in sites:
            disk=_disk(board,net,c["layers"][0],site,rows[0]["diameter_nm"])
            missing=disk.CloneDropTriangulation()
            missing.BooleanSubtract(native._poly(rebuilt_center) if rebuild_center_landing else actual)
            if missing.OutlineCount():failure="center_landing_does_not_cover_entire_barrel";break
            for layer in board.GetEnabledLayers().CuStack():
                # An exact native circle avoids repeatedly tessellating the
                # same clearance disk for every obstacle/layer. The one-nm
                # outward guard contains the former polygon envelope too.
                circle=pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I(*site),
                    (rows[0]["diameter_nm"]+1)//2+clearance_nm+1)
                for item in foreign:
                    native._check_deadline(deadline)
                    if item.GetNetname()!=net and item.IsOnLayer(int(layer)) and item.GetEffectiveShape(int(layer)).Collide(circle,0):
                        failure="foreign_all_layer_barrel_clearance:"+str(int(layer))+":"+item.m_Uuid.AsString()+":"+item.GetNetname()
                        break
                if failure:break
            if failure:break
        proposed=[]
        if not failure:
            margin=pitch_nm//2
            if margin<rows[0]["diameter_nm"]//2:
                raise native.Refused("field_pitch_does_not_cover_annular_lands")
            for src in expand:
                outline=src["outline_nm"]
                x0=min(min(p[0] for p in outline),min(p[0] for p in sites)-margin)
                x1=max(max(p[0] for p in outline),max(p[0] for p in sites)+margin)
                y0=min(min(p[1] for p in outline),min(p[1] for p in sites)-margin)
                y1=max(max(p[1] for p in outline),max(p[1] for p in sites)+margin)
                polygon=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
                try:native._require_unoccupied_outline(board,native._poly(polygon),net,
                    src["configuration"]["layers"][0],time.monotonic()+2)
                except native.Refused:failure="foreign_copper_in_expanded_landing";break
                proposed.append(dict(source_zone=src,polygon_nm=polygon))
        attempts.append(dict(sites_nm=sites,refused=failure))
        if failure:continue
        # Minimum-displacement one-to-one matching is deterministic and
        # bounded (at most 25x25); no barrel identity or ownership is lost.
        from scipy.optimize import linear_sum_assignment
        costs=[[(r["position_nm"][0]-p[0])**2+(r["position_nm"][1]-p[1])**2
                for p in sites] for r in rows]
        indices,j=linear_sum_assignment(costs)
        seats={rows[int(i)]["uuid"]:sites[int(k)] for i,k in zip(indices,j)}
        result=dict(schema=1,source_vias=rows,center_source=center_source,
            center_zone_uuid=center_zone_uuid,center_nm=list(center),sites_nm=sites,
            seats_by_uuid=seats,expanded_zones=proposed,attempts=attempts,
            pitch_nm=pitch_nm,reach_nm=reach_nm,clearance_nm=clearance_nm,
            field_shape=shape_evidence(sites,center),
            supporting_tracks=supporting_tracks,
            source_count_retained=True,new_capacity_credited=False,release_authority=False)
        if rebuild_center_landing:
            result.update(rebuild_center_landing=True,required_center_width_nm=required_center_width_nm,
                center_edge_margin_nm=center_edge_margin_nm,rebuilt_center_polygon_nm=rebuilt_center,
                center_reference='exact_native_barrel_centroid',old_center_fill_preserved=False)
        result["plan_sha256"]=native._digest(result)
        return result
    raise native.Refused("no_fully_supported_centered_field:"+str([a["refused"] for a in attempts]))


def materialize_owned_field(board,proposal,*,allow_locked_via_uuids=(),allow_grouped_via_uuids=(),
        allow_locked_zone_uuids=(),allow_grouped_zone_uuids=()):
    """Only caller-owned private board mutation; no save or fill or signoff."""
    import pcbnew
    import cec_rectilinear_copper as native
    import cec_rounded_landing as zones
    p=dict(proposal);digest=p.pop("plan_sha256",None)
    if digest!=native._digest(p):raise native.Refused("owned_field_plan_identity_changed")
    # Rebuild rather than trusting even a rehashed proposed seat or outline.
    rebuilt=plan_owned_field(board,[r["uuid"] for r in p["source_vias"]],
        center_zone_uuid=p["center_zone_uuid"],
        expand_zone_uuids=[r["source_zone"]["configuration"]["uuid"] for r in p["expanded_zones"]],
        pitch_nm=p["pitch_nm"],reach_nm=p["reach_nm"],clearance_nm=p["clearance_nm"],
        allow_locked_via_uuids=allow_locked_via_uuids,allow_grouped_via_uuids=allow_grouped_via_uuids,
        allow_locked_zone_uuids=allow_locked_zone_uuids,allow_grouped_zone_uuids=allow_grouped_zone_uuids,
        rebuild_center_landing=p.get('rebuild_center_landing',False),
        required_center_width_nm=p.get('required_center_width_nm'),
        center_edge_margin_nm=p.get('center_edge_margin_nm',100000))
    if rebuilt!=proposal:raise native.Refused("owned_field_source_or_declaration_changed")
    vias={v.m_Uuid.AsString():v for v in board.GetTracks() if v.GetClass()=="PCB_VIA"}
    zmap={z.m_Uuid.AsString():z for z in board.Zones()}
    tracks={t.m_Uuid.AsString():t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'}
    for rows_on_layer in p['supporting_tracks'].values():
        for row in rows_on_layer:
            if row['uuid'] not in tracks or native._track_row(tracks[row['uuid']])!=row:
                raise native.Refused('owned_field_native_support_track_changed')
    for uid,site in p["seats_by_uuid"].items():vias[uid].SetPosition(pcbnew.VECTOR2I(*site))
    for row in p["expanded_zones"]:
        zone=zmap[row["source_zone"]["configuration"]["uuid"]]
        zone.UnFill();zone.Outline().RemoveAllContours();zone.Outline().NewOutline()
        for x,y in row["polygon_nm"]:zone.Outline().Append(x,y)
    changed=[r["source_zone"]["configuration"]["uuid"] for r in p["expanded_zones"]]
    if p.get('rebuild_center_landing',False):
        zone=zmap[p['center_zone_uuid']];zone.UnFill();zone.Outline().RemoveAllContours();zone.Outline().NewOutline()
        for x,y in p['rebuilt_center_polygon_nm']:zone.Outline().Append(x,y)
        changed.append(p['center_zone_uuid'])
    return dict(moved_via_uuids=sorted(p["seats_by_uuid"]),
        changed_zone_uuids=changed,
        native_fill_received=False,release_authority=False)


def receive_owned_field(board,proposal):
    """Full saved native disk landings on each declared layer, no cached pass."""
    import cec_rectilinear_copper as native
    import cec_rounded_landing as zones
    import time
    p=dict(proposal);digest=p.pop("plan_sha256",None)
    if digest!=native._digest(p):raise native.Refused("owned_field_receiving_identity_changed")
    rows=p['source_vias'];sites=p['sites_nm'];seats=p['seats_by_uuid']
    if (not isinstance(rows,list) or not 1<=len(rows)<=25
            or type(p.get('rebuild_center_landing',False)) is not bool):
        raise native.Refused('invalid_saved_owned_field_recompile_policy')
    if p.get('rebuild_center_landing',False):
        from cec_field_landing import _geometry
        expected_center=[sum(r['position_nm'][i] for r in rows)//len(rows) for i in range(2)]
        if (type(p['rebuild_center_landing']) is not bool or expected_center!=p['center_nm']
                or any(sum(r['position_nm'][i] for r in rows)%len(rows) for i in range(2))
                or p.get('center_reference')!='exact_native_barrel_centroid'
                or p.get('old_center_fill_preserved') is not False):
            raise native.Refused('saved_owned_center_rebuild_reference_changed')
        expected_frame,_=_geometry([dict(rows[i],position_nm=s) for i,s in enumerate(sites)],
            p['required_center_width_nm'],p['center_edge_margin_nm'],'chamfer45')
        if expected_frame!=p['rebuilt_center_polygon_nm']:
            raise native.Refused('saved_owned_center_not_derived_from_full_barrels')
    if (not 1<=len(rows)<=25 or len(sites)!=len(rows) or len(seats)!=len(rows)
            or set(seats)!={r['uuid'] for r in rows}
            or sorted(seats.values())!=sorted(sites)
            or p['field_shape']!=shape_evidence(sites,p['center_nm'])
            or not p['field_shape']['centered'] or not p['field_shape']['rotationally_symmetric']
            or tuple(sorted(tuple(s) for s in sites)) not in tuple(tuple((x+p['center_nm'][0],y+p['center_nm'][1]) for x,y in pattern)
                for pattern in centered_offsets(len(rows),pitch_nm=p['pitch_nm'],reach_nm=p['reach_nm']))):
        raise native.Refused('owned_field_receiving_seats_count_or_symmetry_invalid')
    vias={v.m_Uuid.AsString():v for v in board.GetTracks() if v.GetClass()=="PCB_VIA"}
    zmap={z.m_Uuid.AsString():z for z in board.Zones()}
    tracks={t.m_Uuid.AsString():t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'}
    for rows_on_layer in p['supporting_tracks'].values():
        for row in rows_on_layer:
            if row['uuid'] not in tracks or native._track_row(tracks[row['uuid']])!=row:
                raise native.Refused('owned_field_native_support_track_changed')
    for row in p["source_vias"]:
        expected=dict(row,position_nm=p["seats_by_uuid"][row["uuid"]])
        if row["uuid"] not in vias or _via_row(vias[row["uuid"]])!=expected:
            raise native.Refused("owned_field_barrel_identity_dimensions_or_seat_changed")
    checked=[]
    for src in [p["center_source"],*[r["source_zone"] for r in p["expanded_zones"]]]:
        cfg=src["configuration"];zone=zmap.get(cfg["uuid"])
        if zone is None or zones._configuration(zone)!=cfg or not zone.IsFilled():
            raise native.Refused("owned_field_native_landing_configuration_or_fill_changed")
        expected_outline=(p.get('rebuilt_center_polygon_nm',src['outline_nm']) if cfg['uuid']==p['center_zone_uuid'] else
            next(r['polygon_nm'] for r in p['expanded_zones'] if r['source_zone']['configuration']['uuid']==cfg['uuid']))
        if native._shape_identity(zone.Outline(),time.monotonic()+2)[0]!=native._shape_identity(native._poly(expected_outline),time.monotonic()+2)[0]:
            raise native.Refused('owned_field_saved_landing_outline_not_declared')
        layer=cfg["layers"][0]
        if not zone.HasFilledPolysForLayer(layer):raise native.Refused('owned_field_saved_landing_unfilled_layer')
        actual=zone.GetFilledPolysList(layer).CloneDropTriangulation()
        for row in p['supporting_tracks'][str(layer)]:actual.BooleanAdd(native._native_capsule(tracks[row['uuid']]))
        actual.BooleanIntersection(zone.Outline())
        for at in p["sites_nm"]:
            missing=_disk(board,cfg["net"],layer,at,p["source_vias"][0]["diameter_nm"])
            missing.BooleanSubtract(actual)
            if missing.OutlineCount():raise native.Refused("saved_native_field_landing_incomplete")
        if not (p.get('rebuild_center_landing',False) and cfg['uuid']==p['center_zone_uuid']):
            old=native._poly(src["fill_nm"]);old.BooleanSubtract(actual)
            if old.OutlineCount():raise native.Refused("owned_landing_lost_existing_filled_copper")
        checked.append(layer)
    return dict(ok=True,native_landing_layers=checked,barrel_count=len(p["source_vias"]),
        field_shape=shape_evidence(p["sites_nm"],p["center_nm"]),
        source_landing_copper_preserved=not p.get('rebuild_center_landing',False),
        other_landing_copper_preserved=True,new_capacity_credited=False,release_authority=False)


def _ground_identity(shape,deadline):
    """Exact bounded native fill identity, including KiCad hole bridges.

    This binds representation, NOT a simple-polygon qualification. Repeated
    bridge vertices are retained verbatim; there is no Unfracture, Simplify,
    approximate area, or tolerance. Ordinary source-zone validation stays
    strict. Separate native differences still receive the locality claim.
    """
    import cec_rectilinear_copper as native
    polygons=[];vertices=0
    for i in range(shape.OutlineCount()):
        rings=[]
        for ring in [shape.Outline(i),*[shape.Hole(i,j) for j in range(shape.HoleCount(i))]]:
            native._check_deadline(deadline);count=ring.PointCount();vertices+=count
            if ring.ArcCount() or count<3 or vertices>200000:raise native.Refused('bounded_native_ground_fill_required')
            points=[(int(ring.CPoint(k).x),int(ring.CPoint(k).y)) for k in range(count)]
            if any(abs(v)>2000000000 for point in points for v in point):raise native.Refused('native_ground_coordinate_bound')
            lowest=min(points);anchors=[k for k,p in enumerate(points) if p==lowest]
            if len(anchors)>64:raise native.Refused('native_ground_bridge_anchor_bound')
            choices=[]
            for k in anchors:
                forward=points[k:]+points[:k];choices.extend([forward,[forward[0],*reversed(forward[1:])]])
            rings.append(min(choices))
        polygons.append([rings[0],*sorted(rings[1:])])
    native._check_deadline(deadline)
    return native._digest(sorted(polygons))


def plan_local_ground_refill(source,compiled,field_proposals,ground_zone_uuids):
    """Bound actual KiCad refill to the explicitly moved barrel windows.

    A global filler can perturb tessellation around unrelated features. Do not
    admit those changes under a local via owner. Inside the declared windows
    ONLY the actual newly compiled native fill supplies copper; outside them
    ONLY the exact original native fill supplies copper. No imaginary plane,
    analytical copper substitute, tolerance, or reference-quality authority.
    Independent whole-board DRC/connectivity/field receiving remains required.
    """
    import time
    import pcbnew
    import cec_rectilinear_copper as native
    import cec_rounded_landing as zones
    if not 1<=len(field_proposals)<=16 or not 1<=len(ground_zone_uuids)<=16 or len(set(ground_zone_uuids))!=len(ground_zone_uuids):
        raise native.Refused('bounded_field_and_ground_refill_ownership_required')
    oldzones={z.m_Uuid.AsString():z for z in source.Zones()};newzones={z.m_Uuid.AsString():z for z in compiled.Zones()}
    oldvias={v.m_Uuid.AsString():v for v in source.GetTracks() if v.GetClass()=='PCB_VIA'}
    for proposal in field_proposals:
        receive_owned_field(compiled,proposal)
        for row in proposal['source_vias']:
            if row['uuid'] not in oldvias or _via_row(oldvias[row['uuid']])!=row:
                raise native.Refused('local_ground_refill_original_barrel_boundary_changed')
    rows=[];deadline=time.monotonic()+10
    for uid in sorted(ground_zone_uuids):
        native._check_deadline(deadline)
        if uid not in oldzones or uid not in newzones:raise native.Refused('local_ground_zone_missing')
        old,new=oldzones[uid],newzones[uid];cfg=zones._configuration(old)
        if (cfg['net'].rsplit('/',1)[-1]!='GND' or cfg['rule_area'] or len(cfg['layers'])!=1
                or zones._configuration(new)!=cfg or not old.IsFilled() or not new.IsFilled()):
            raise native.Refused('actual_unchanged_filled_ground_declaration_required')
        layer=cfg['layers'][0]
        if (native._shape_identity(old.Outline(),deadline)[0]!=native._shape_identity(new.Outline(),deadline)[0]
                or not old.HasFilledPolysForLayer(layer) or not new.HasFilledPolysForLayer(layer)):
            raise native.Refused('ground_outline_or_native_fill_layer_changed')
        windows=[];allowed=pcbnew.SHAPE_POLY_SET()
        for proposal in field_proposals:
            for row in proposal['source_vias']:
                if not oldvias[row['uuid']].IsOnLayer(layer):continue
                radius=(row['diameter_nm']+1)//2+int(old.GetLocalClearance())+int(old.GetMinThickness())
                for x,y in (row['position_nm'],proposal['seats_by_uuid'][row['uuid']]):
                    polygon=[[x-radius,y-radius],[x+radius,y-radius],[x+radius,y+radius],[x-radius,y+radius]]
                    windows.append(polygon);allowed.BooleanAdd(native._poly(polygon))
        original=old.GetFilledPolysList(layer);full=new.GetFilledPolysList(layer)
        # Bounds are validated before native boolean work; no approximate
        # areas, renderer data, ignored slivers or cached PASS are authority.
        original_id=_ground_identity(original,deadline)
        compiled_id=_ground_identity(full,deadline)
        outside=original.CloneDropTriangulation();outside.BooleanSubtract(allowed)
        inside=full.CloneDropTriangulation();inside.BooleanIntersection(allowed)
        local=outside.CloneDropTriangulation();local.BooleanAdd(inside)
        local.Fracture()
        rows.append(dict(uuid=uid,configuration=cfg,layer_id=layer,windows_nm=windows,
            original_fill_sha256=original_id,compiled_fill_sha256=compiled_id,
            local_fill_sha256=_ground_identity(local,deadline)))
    result=dict(schema=1,scope='exact_native_local_ground_refill_not_reference_or_release_qualification',
        ground_rows=rows,field_plan_sha256s=[p['plan_sha256'] for p in field_proposals],
        invented_copper=False,release_authority=False)
    result['plan_sha256']=native._digest(result)
    return result


def materialize_local_ground_refill(source,compiled,proposal,field_proposals):
    """Apply only exact source-outside / real compiled-inside native copper."""
    import pcbnew
    import cec_rectilinear_copper as native
    expected=plan_local_ground_refill(source,compiled,field_proposals,[r['uuid'] for r in proposal['ground_rows']])
    if expected!=proposal:raise native.Refused('local_ground_refill_source_or_compiled_plan_changed')
    oldzones={z.m_Uuid.AsString():z for z in source.Zones()};newzones={z.m_Uuid.AsString():z for z in compiled.Zones()}
    for row in proposal['ground_rows']:
        allowed=pcbnew.SHAPE_POLY_SET()
        for window in row['windows_nm']:allowed.BooleanAdd(native._poly(window))
        outside=oldzones[row['uuid']].GetFilledPolysList(row['layer_id']).CloneDropTriangulation();outside.BooleanSubtract(allowed)
        inside=newzones[row['uuid']].GetFilledPolysList(row['layer_id']).CloneDropTriangulation();inside.BooleanIntersection(allowed)
        outside.BooleanAdd(inside)
        outside.Fracture()
        newzones[row['uuid']].SetFilledPolysList(row['layer_id'],outside)
        newzones[row['uuid']].SetIsFilled(True)
    compiled.BuildConnectivity()
    return dict(ground_zone_count=len(proposal['ground_rows']),invented_copper=False,release_authority=False)


def receive_local_ground_refill(source,saved,proposal):
    import time
    import cec_rectilinear_copper as native
    import cec_rounded_landing as zones
    p=dict(proposal);digest=p.pop('plan_sha256',None)
    if digest!=native._digest(p):raise native.Refused('local_ground_refill_identity_changed')
    olds={z.m_Uuid.AsString():z for z in source.Zones()};news={z.m_Uuid.AsString():z for z in saved.Zones()}
    deadline=time.monotonic()+10
    for row in p['ground_rows']:
        old,new=olds.get(row['uuid']),news.get(row['uuid'])
        if (old is None or new is None or not new.IsFilled()
                or zones._configuration(old)!=row['configuration'] or zones._configuration(new)!=row['configuration']
                or native._shape_identity(old.Outline(),deadline)[0]!=native._shape_identity(new.Outline(),deadline)[0]
                or _ground_identity(old.GetFilledPolysList(row['layer_id']),deadline)!=row['original_fill_sha256']
                or _ground_identity(new.GetFilledPolysList(row['layer_id']),deadline)!=row['local_fill_sha256']):
            raise native.Refused('saved_native_local_ground_not_exact_received_construction')
    return dict(ok=True,ground_zone_count=len(p['ground_rows']),outside_windows_exactly_original=True,
        inside_windows_actual_native_refill=True,invented_copper=False,release_authority=False)
