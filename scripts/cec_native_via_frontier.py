"""Geometry-derived, explicitly sized barrel proposals across every copper layer.

The free-space approximation ranks candidates only. Each returned point still
passes the existing native via/edge/fabrication/hole guards plus a caller's
contact predicate. It is not connectivity, capacity or release authority.
"""
import math
import time

import pcbnew
import cec_fab_profile as fab
import cec_fr as fr
import cec_force_current as force


def _rank_points(candidates, origin, *, diverse, axis_bend_penalty_mm=0.):
    """Nearest-first legacy order or bounded angular breadth, proposals only."""
    def cost(q):
        dx,dy=[abs(q[i]-origin[i]) for i in (0,1)]
        return (max(dx,dy)+(math.sqrt(2)-1)*min(dx,dy)
            +axis_bend_penalty_mm*int(dx>0 and dy>0)) if axis_bend_penalty_mm else math.dist(q,origin)
    ranked=sorted(candidates,key=lambda q:(cost(q),q))
    if not diverse:return ranked
    groups={i:[] for i in range(8)}
    for point in ranked:
        x,y=point[0]-origin[0],point[1]-origin[1]
        sector=math.floor((math.atan2(y,x)+math.pi/8)/(math.pi/4))%8
        groups[sector].append(point)
    output=[];used=set()
    # Keep the nearest choice first, then cover every populated direction
    # before funding a second vertex in the same power-trunk shadow.
    for depth in range(max((len(g) for g in groups.values()),default=0)):
        ring=sorted((g[depth] for g in groups.values() if len(g)>depth),
            key=lambda q:(cost(q),q))
        for point in ring:
            if point not in used:used.add(point);output.append(point)
    return output


def sites(board, net_code, origin_nm, *, clearance_nm, radius_mm=16., max_sites=24,
          deadline, barrel_guard=None, diverse=False, diameter_mm=.6, drill_mm=.3,
          prefer_axis_aligned=False,require_full_ground_reference=False,
          preserve_requested_geometry=False):
    from shapely import affinity
    from shapely.geometry import Point,LineString,box
    from shapely.ops import unary_union,nearest_points
    import cec_kelvin_copper_cut as cut
    if (type(max_sites) is not int or not 1<=max_sites<=64
            or type(radius_mm) not in (int,float) or not math.isfinite(radius_mm)
            or not 0<radius_mm<=24 or len(origin_nm)!=2
            or any(type(v) is not int for v in origin_nm)
            or type(clearance_nm) is not int or clearance_nm<0
            or type(deadline) not in (int,float) or not math.isfinite(deadline)
            or not time.monotonic()<deadline<=time.monotonic()+10.
            or type(diverse) is not bool or type(prefer_axis_aligned) is not bool
            or type(require_full_ground_reference) is not bool
            or type(preserve_requested_geometry) is not bool
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in (diameter_mm,drill_mm))
            or not 0<drill_mm<diameter_mm<=8.
            or barrel_guard is not None and not callable(barrel_guard)):
        raise ValueError('bounded_native_barrel_frontier_required')
    # Explicit geometry is proposal extent, not current or process authority.
    # Preserve the legacy ordinary floor while allowing a source-typed caller
    # to reserve a larger full-web barrel, including aggregate power buses.
    # The finite 8-mm work bound is not a current or plated-barrel rating.
    # Every approximation and final
    # native query uses THAT size, never a smaller .6 mm stand-in.
    work=cut._Work(deadline);dia,drill,_=fab.board_legal_through_via_geometry(board,
        diameter_mm if preserve_requested_geometry else max(.6,diameter_mm),
        drill_mm if preserve_requested_geometry else max(.3,drill_mm))
    occupied=[];layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    x,y=[v/1e6 for v in origin_nm]
    region=box(x-radius_mm-dia,y-radius_mm-dia,x+radius_mm+dia,y+radius_mm+dia)
    objects=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks(),
        *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    for item in objects:
        work.tick();kind=item.GetClass()
        bb=item.GetBoundingBox()
        if not region.intersects(box(bb.GetLeft()/1e6,bb.GetTop()/1e6,
                bb.GetRight()/1e6,bb.GetBottom()/1e6)):continue
        if kind=='PCB_VIA' or kind=='PAD' and item.HasHole():
            d=(item.GetDrillValue() if kind=='PCB_VIA'
                else max(item.GetDrillSize().x,item.GetDrillSize().y))/1e6
            occupied.append(Point(item.GetPosition().x/1e6,item.GetPosition().y/1e6).buffer(
                (d+drill)/2+board.GetDesignSettings().m_HoleToHoleMin/1e6+.002))
        # All pads remain assembly obstacles in this ordinary remote-barrel
        # portfolio. Local POFV belongs to the separately qualified producer.
        if kind!='PAD' and item.GetNetCode()==net_code:continue
        # Proposal geometry only: one pad envelope and one barrel envelope
        # replace thousands of duplicated circular vertices across six
        # layers. The native all-layer/fab/contact verifier below still
        # inspects the exact actual shapes before RETURNING a seat.
        margin=dia/2+clearance_nm/1e6+.002
        if kind=='PAD':
            # Same-net SMD lands remain assembly obstacles, not foreign
            # copper. A nonoverlapping barrel beside its own land does not
            # require an additional foreign-net clearance moat. Keep the
            # conservative full pad box + barrel envelope + 2-um guard;
            # never infer POFV, drop holes, or skip the exact native/fab
            # verifier below. THT/unknown/foreign pads are unchanged.
            if (net_code>0 and item.GetNetCode()==net_code
                    and item.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not item.HasHole()):
                margin=dia/2+.002
            occupied.append(box(bb.GetLeft()/1e6,bb.GetTop()/1e6,
                bb.GetRight()/1e6,bb.GetBottom()/1e6).buffer(margin));continue
        if kind=='PCB_VIA':
            width=max(item.GetWidth(l) for l in layers if item.IsOnLayer(l))
            occupied.append(Point(item.GetPosition().x/1e6,item.GetPosition().y/1e6).buffer(
                width/2e6+margin,quad_segs=16));continue
        if kind=='PCB_TRACK':
            s,t=item.GetStart(),item.GetEnd()
            occupied.append(LineString([(s.x/1e6,s.y/1e6),(t.x/1e6,t.y/1e6)]).buffer(
                item.GetWidth()/2e6+margin,quad_segs=16));continue
        for layer in layers:
            if not item.IsOnLayer(layer):continue
            if kind=='ZONE':
                if not fr._zone_is_route_reservation(board,item,layer):continue
                if not item.IsFilled():raise ValueError('native_barrel_foreign_zone_fill_unknown')
                shape=cut._poly(item.GetFilledPolysList(layer),work)
            else:shape=cut._shape(item,layer,True,work)
            occupied.append(affinity.scale(shape,xfact=1e-6,yfact=1e-6,origin=(0,0)).buffer(
                dia/2+clearance_nm/1e6+.002))
    origin=Point(origin_nm[0]/1e6,origin_nm[1]/1e6)
    free=origin.buffer(radius_mm,quad_segs=16).difference(unary_union(occupied))
    if require_full_ground_reference:
        # A foreign-clear axis need not have Ground metal around its entire
        # annulus: saved reference fills may end inside the free-space cell.
        # Add those ACTUAL boundaries before event generation/ranking. A
        # postfilter alone can spend every funded seat on the same bad edge.
        # This conservative floating proposal region is never admission; the
        # mesh receiver still observes exact saved native annular envelopes.
        if net_code<=0 or board.FindNet(net_code).GetNetname()!='GND':
            raise ValueError('actual_ground_net_required_for_reference_frontier')
        profile=fab.get_profile(fab.board_profile_name(board))
        faces={int(board.GetLayerID(n)) for n,role in zip(fab.COPPER_LAYERS,profile['roles'])
            if role=='GND'} if profile else set()
        if not faces:raise ValueError('declared_ground_reference_profile_required')
        reference=None
        for face in sorted(faces):
            work.tick();zones=[z for z in board.Zones() if not z.GetIsRuleArea()
                and z.GetNetname()=='GND' and z.IsOnLayer(face)]
            if not zones or any(not z.IsFilled() or not z.HasFilledPolysForLayer(face) for z in zones):
                raise ValueError('all_declared_ground_reference_fills_required')
            metal=unary_union([affinity.scale(cut._poly(z.GetFilledPolysList(face),work),
                xfact=1e-6,yfact=1e-6,origin=(0,0)) for z in zones])
            safe=metal.buffer(-dia/2-.002,join_style=2)
            reference=safe if reference is None else reference.intersection(safe)
        free=free.intersection(reference)
    edges=board.GetBoardEdgesBoundingBox();margin=dia/2+clearance_nm/1e6+.002
    if edges.GetWidth()>0 and edges.GetHeight()>0:
        free=free.intersection(box(edges.GetLeft()/1e6+margin,edges.GetTop()/1e6+margin,
            edges.GetRight()/1e6-margin,edges.GetBottom()/1e6-margin))
    polygons=[free] if free.geom_type=='Polygon' else list(getattr(free,'geoms',()))
    candidates=set()
    for poly in polygons:
        work.tick()
        if poly.geom_type!='Polygon':continue
        inner=poly.buffer(-.002)
        for p in [inner] if inner.geom_type=='Polygon' else list(getattr(inner,'geoms',())):
            if p.geom_type!='Polygon' or p.is_empty:continue
            near=nearest_points(origin,p)[1];representative=p.representative_point()
            candidates.update([(near.x,near.y),(representative.x,representative.y)])
            candidates.update(tuple(q) for q in p.exterior.coords[:-1])
            if prefer_axis_aligned:
                for line in (LineString([(x-radius_mm,y),(x+radius_mm,y)]),
                             LineString([(x,y-radius_mm),(x,y+radius_mm)])):
                    section=p.intersection(line)
                    if section.is_empty:continue
                    proposal=nearest_points(origin,section)[1]
                    candidates.add((proposal.x,proposal.y))
    result=[];cache={};holes=fr._via_hole_snapshot(board)
    for xy in _rank_points(candidates,(origin.x,origin.y),diverse=diverse,
            axis_bend_penalty_mm=dia/2 if prefer_axis_aligned else 0.):
        work.tick();at=tuple(round(v*1e6) for v in xy)
        if any(math.dist(at,q)<500000 for q in result):continue
        point=pcbnew.VECTOR2I(*at)
        if (math.dist(at,origin_nm)<=radius_mm*1e6
                and fr._edge_leg_clear(board,point,point,dia*1e6/2+clearance_nm)
                and fr._via_spot_clear(board,point,round(dia*1e6),clearance_nm,{net_code},
                    drill_nm=round(drill*1e6),net_code=net_code,foreign_cache=cache,_via_holes=holes)
                and (barrel_guard is None or barrel_guard(at,round(dia*1e6)))):
            result.append(at)
        if len(result)>=max_sites:break
    return dict(sites_nm=[list(q) for q in result],diameter_mm=dia,drill_mm=drill,
        spatially_diverse_proposals=diverse,
        full_ground_reference_proposal_region_required=require_full_ground_reference,
        source_axis_alignment_preferred=prefer_axis_aligned,
        requested_geometry_preserved_subject_to_ordinary_board_floors=preserve_requested_geometry,
        no_path_proof=False,routing_admitted=False,release_authority=False)
