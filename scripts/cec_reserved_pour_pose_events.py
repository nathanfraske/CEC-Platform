"""Finite native-contour separation proposals for a reserved-pour collision.

These are search events only. Filled antipads, zone names, bounding rectangles
and same-net neighbours cannot authorize a footprint seat. Every returned
translation clears the literal offending reservation on its actual pad face;
all other source, placement, current and saved-board guards still apply.
"""
import math
import time
import pcbnew
import cec_constraints as constraints
import cec_decoupler_cell as cells
import cec_force_current as force


def _box(item):
    b=item.GetBoundingBox()
    return b.GetLeft(),b.GetTop(),b.GetRight(),b.GetBottom()


def _separations(own,other,gap):
    guard=2000
    return ((other[0]-gap-guard-own[2],0),(other[2]+gap+guard-own[0],0),
        (0,other[1]-gap-guard-own[3]),(0,other[3]+gap+guard-own[1]))


def propose(board,footprint,zone_uuid,*,max_events=32,max_candidates=512,max_vertices=2048,timeout_s=.5):
    if (type(zone_uuid) is not str or not zone_uuid or type(max_events) is not int
            or not 1<=max_events<=64 or type(max_candidates) is not int or not 4<=max_candidates<=2048
            or type(max_vertices) is not int or not 4<=max_vertices<=8192
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=2.):
        raise ValueError('bounded_native_reserved_pour_events_required')
    deadline=time.monotonic()+timeout_s
    regions=[(z,int(face)) for z,face in constraints.laid_pour_regions(board) if force._uid(z)==zone_uuid]
    result=dict(events_nm=[],complete=True,zone_uuid=zone_uuid,native_regions=len(regions),
        source_mutated=False,placement_authority=False,routing_admitted=False,release_authority=False)
    if not regions:return result
    pads=list(footprint.Pads())
    if len(pads)>512:raise ValueError('reserved_pour_pad_inventory_bound')
    contexts=[];raw=set();vertices=0
    def offer(vectors):
        for point in vectors:
            if point in raw:continue
            if len(raw)>=max_candidates:result['complete']=False;return False
            raw.add(point)
        return True
    for zone,face in regions:
        if time.monotonic()>=deadline:result['complete']=False;return result
        foreign=[p for p in pads if p.IsOnLayer(face) and p.GetNetname()!=zone.GetNetname()]
        if not foreign:continue
        outline=zone.Outline();colliding=[p for p in foreign if outline.Collide(p.GetEffectiveShape(face),0)]
        if not colliding:continue
        # Keep OUTSIDE pad polygons. A proposal filter must not clear an
        # inscribed approximation while real round/chamfered land remains.
        shapes=[]
        for pad in foreign:
            if time.monotonic()>=deadline:result['complete']=False;return result
            poly=pcbnew.SHAPE_POLY_SET()
            pad.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE,False)
            if not poly.OutlineCount():raise ValueError('native_reserved_pour_pad_polygon_unknown')
            gap=max(int(board.GetDesignSettings().m_MinClearance),int(zone.GetLocalClearance()),
                int(cells._netclass(board,pad.GetNetname())['clearance']),
                int(cells._netclass(board,zone.GetNetname())['clearance']))
            shapes.append((poly,gap))
        contexts.append((outline,shapes,face))
        edges=[]
        for i in range(outline.OutlineCount()):
            chains=[outline.COutline(i),*[outline.CHole(i,j) for j in range(outline.HoleCount(i))]]
            for chain in chains:
                vertices+=chain.PointCount()
                if vertices>max_vertices or chain.ArcCount():
                    result['complete']=False;continue
                for k in range(chain.PointCount()):
                    a,b=chain.CPoint(k),chain.CPoint((k+1)%chain.PointCount())
                    edges.append((min(a.x,b.x),min(a.y,b.y),max(a.x,b.x),max(a.y,b.y)))
        for pad in colliding:
            own=_box(pad)
            gap=max(int(board.GetDesignSettings().m_MinClearance),int(zone.GetLocalClearance()),
                int(cells._netclass(board,pad.GetNetname())['clearance']),
                int(cells._netclass(board,zone.GetNetname())['clearance']))
            offer(_separations(own,_box(zone),gap))
            # Nearby actual contour edges (including concave pockets/holes)
            # precede the whole-zone box; a large bus need not force a move
            # all the way outside its enclosing rectangle.
            ordered=sorted(edges,key=lambda q:(max(q[0]-own[2],own[0]-q[2],0)**2+
                max(q[1]-own[3],own[1]-q[3],0)**2,q))
            for edge in ordered:
                if time.monotonic()>=deadline or len(raw)>=max_candidates:
                    result['complete']=False;break
                if not offer(_separations(own,edge,gap)):break
    for dx,dy in sorted(raw,key=lambda q:(math.hypot(*q),q)):
        if time.monotonic()>=deadline:result['complete']=False;break
        if (dx==dy==0 or any(abs(v)>2000000000 for v in (dx,dy))):continue
        clear=True
        for outline,shapes,face in contexts:
            for poly,gap in shapes:
                moved=pcbnew.SHAPE_POLY_SET(poly);moved.Move(pcbnew.VECTOR2I(dx,dy))
                if outline.Collide(moved,gap):clear=False;break
            if not clear:break
        if clear:result['events_nm'].append([dx,dy])
        if len(result['events_nm'])>=max_events:result['complete']=False;break
    result.update(native_conflicting_faces=sorted({face for _,_,face in contexts}),
        native_vertices_observed=vertices,candidate_translations=len(raw),
        exact_reserved_contours_not_filled_antipads=True,
        whole_offending_reservation_cleared_not_whole_board_qualified=True)
    return result
