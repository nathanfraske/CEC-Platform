"""Bounded native wide-stroke diagnosis and rectilinear *planning* geometry.

KiCad straight tracks are capsules, not flat-ended rectangles. Canonical
centerlines alone do not prevent lollipops at short, wide links or a bulb at
an unequal-width elbow. Report those separately from electrical DRC. They
request the power geometry owner's attention, never a renderer-only fix or
permission for an ordinary signal router to neck down a power conductor.

The polygon helper is for upstream corridor producers. It neither writes a
BOARD nor certifies ampacity: flat-end landing, native post-fill width,
clearance, shunt isolation, reference-plane and current-state receiving are
still required before replacing any protected native copper.
"""
from collections import Counter, defaultdict
import math
import time


def rectilinear_profile(points, width_mm, *, flush_start=False, flush_end=False):
    """Constant-width Manhattan corridor, mitred bends, explicit end policy.

    Square caps remain the conservative default. Flat caps are an explicit
    geometry proposal, NOT an assertion that a pad/trunk landing is qualified.
    Unlike raster dilation, this yields one clean polygon without microsteps.
    Coordinates must be nanometre-exact; diagonal/self-overlapping centerlines
    are refused rather than silently snapped. Dimensions include no guessed
    branch-current sharing or unrecorded safety margin.
    """
    from shapely.geometry import LineString, box
    if (type(width_mm) not in (float, int) or not math.isfinite(width_mm)
            or not 0 < width_mm <= 100 or type(flush_start) is not bool
            or type(flush_end) is not bool):
        raise ValueError("invalid_corridor_dimensions")
    if not isinstance(points, (list, tuple)) or not 2 <= len(points) <= 256:
        raise ValueError("invalid_corridor_inventory")
    native = []
    for point in points:
        if not isinstance(point, (tuple, list)) or len(point) != 2:
            raise ValueError("invalid_corridor_point")
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in point):
            raise ValueError("invalid_corridor_point")
        p = tuple(round(v * 1e6) for v in point)
        if any(abs(v * 1e6 - q) > 1e-5 for v, q in zip(point, p)):
            raise ValueError("non_native_coordinate")
        native.append(p)
    for a, b in zip(native, native[1:]):
        if a == b or (a[0] != b[0] and a[1] != b[1]):
            raise ValueError("non_manhattan_centerline")
    line = LineString(native)
    if not line.is_simple:
        raise ValueError("self_overlapping_centerline")
    half = width_mm * 1e6 / 2
    # One analytic mitred envelope, not a cell walk or a sequence of circles.
    shape = line.buffer(half, cap_style=2, join_style=2, mitre_limit=2)
    for at_start, flush in ((True, flush_start), (False, flush_end)):
        if flush:
            continue
        at = native[0] if at_start else native[-1]
        shape = shape.union(box(at[0]-half, at[1]-half,
                                at[0]+half, at[1]+half))
    if shape.geom_type != "Polygon" or shape.interiors or not shape.is_valid:
        raise ValueError("unsupported_corridor_union")
    ring = list(shape.exterior.coords)[:-1]
    if any(a[0] != b[0] and a[1] != b[1]
           for a, b in zip(ring, ring[1:]+ring[:1])):
        raise ValueError("non_manhattan_contour")
    return dict(polygon=[(x/1e6, y/1e6) for x, y in ring], width_mm=width_mm,
        start_cap="flat" if flush_start else "square",
        end_cap="flat" if flush_end else "square",
        replacement_authorized=False, post_fill_width_qualified=False,
        scope="analytic_corridor_proposal_not_native_replacement")


def audit_board(board, *, min_width_mm=1.0, max_length_width_ratio=0.5,
                unequal_width_ratio=1.5, track_uuid_scope=None,
                timeout_s=2.0, max_tracks=8192, max_findings=1024,
                include_terminal_caps=False):
    """Find native capsule hot spots without mutating or refilling a board.

    A hidden cap is suppressed only when its conservative square envelope is
    inside a single convex, drill-free native pad. Boxes around a footprint or
    plated-hole center do not grant that suppression. Partial/time-bounded
    evidence is explicitly incomplete, never a clean-board certificate.
    """
    import pcbnew
    if (any(type(v) not in (int, float) or not math.isfinite(v) for v in
            (min_width_mm, max_length_width_ratio, unequal_width_ratio, timeout_s))
            or not 0 < min_width_mm <= 100 or not 0 < max_length_width_ratio <= 2
            or not 1 < unequal_width_ratio <= 100 or not 0 <= timeout_s <= 10
            or type(max_tracks) is not int or not 1 <= max_tracks <= 32768
            or type(max_findings) is not int or not 1 <= max_findings <= 4096
            or type(include_terminal_caps) is not bool):
        raise ValueError("invalid_power_contour_bounds")
    started = time.monotonic(); deadline = started + timeout_s
    scope = None if track_uuid_scope is None else set(track_uuid_scope)
    tracks = sorted((t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"),
                    key=lambda t: t.m_Uuid.AsString())
    findings = []; examined = 0; complete = True; junctions = defaultdict(list)
    purposeful_covers = []; fill_cache = {}; cover_cache = {}; body_deficits = {}; canonical_owner_cache = {}
    pads = defaultdict(list);terminal_pads=defaultdict(list);terminal_pad_cache={};cap_cache={}
    def result(reason):
        return dict(schema=1, complete=complete, reason=reason, findings=findings,
            finding_count=len(findings), types=dict(Counter(r["type"] for r in findings)),
            examined_tracks=examined, elapsed_s=time.monotonic()-started,
            native_copper_mutated=False, replacement_authorized=False,
            purposeful_native_cover_count=len(purposeful_covers),
            purposeful_native_covers=purposeful_covers,
            locally_hidden_join_nonlocal_body_deficits=list(body_deficits.values()),
            locally_hidden_join_nonlocal_body_deficit_count=len(body_deficits),
            nonlocal_body_deficits_are_retained_track_not_missing_native_copper=True,
            nonlocal_body_deficits_waived_or_current_qualified=False,
            terminal_caps_included=include_terminal_caps,
            terminal_cap_review_complete=complete and include_terminal_caps,
            scope="power_owner_contour_review_not_electrical_DRC_or_ampacity")
    if len(tracks) > max_tracks:
        complete = False; return result("track_inventory_bound")
    convex = (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_CIRCLE,
              pcbnew.PAD_SHAPE_OVAL, pcbnew.PAD_SHAPE_ROUNDRECT)
    for fp in board.GetFootprints():
        if time.monotonic() >= deadline:
            complete = False; return result("deadline")
        for pad in fp.Pads():
            if (include_terminal_caps and pad.GetShape() in convex and pad.GetAttribute() in
                    (pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH)):
                for layer in pad.GetLayerSet().CuStack():
                    terminal_pads[pad.GetNetCode(),int(layer)].append(pad)
            if (pad.GetShape() not in convex or pad.GetDrillSize().x
                    or pad.GetDrillSize().y):
                continue
            for layer in pad.GetLayerSet().CuStack():
                pads[pad.GetNetCode(), int(layer)].append(pad.GetEffectiveShape(layer))
    def covered(track, point):
        r = (int(track.GetWidth())+1)//2
        envelope = [pcbnew.VECTOR2I(point.x+dx*r, point.y+dy*r)
                    for dx,dy in ((-1,-1),(-1,1),(1,1),(1,-1))]
        return any(all(shape.Collide(p) for p in envelope)
                   for shape in pads[track.GetNetCode(), int(track.GetLayer())])
    def row(kind, track, ids, at=None):
        group = track.GetParentGroup()
        return dict(type=kind, net=track.GetNetname(),
            layer=board.GetLayerName(track.GetLayer()), track_uuids=sorted(ids),
            width_mm=track.GetWidth()/1e6,
            start_mm=[track.GetStart().x/1e6, track.GetStart().y/1e6],
            end_mm=[track.GetEnd().x/1e6, track.GetEnd().y/1e6],
            at_mm=None if at is None else [at.x/1e6, at.y/1e6],
            locked=bool(track.IsLocked()), group=group.GetName() if group else None,
            owner_request="native_power_contour_reconstruction_and_receiving",
            ordinary_neckdown_allowed=False, severity="review")
    def terminal_disk(track,point):
        import cec_rectilinear_copper as owner
        key=(track.m_Uuid.AsString(),point.x,point.y)
        if key not in cap_cache:
            ghost=track.Duplicate();ghost.SetStart(point);ghost.SetEnd(point)
            disk=owner._native_capsule(ghost)
            # Restrict the diagnostic to literal source copper, including
            # integer native tessellation. No virtual disk becomes a contact.
            disk.BooleanIntersection(owner._native_capsule(track));cap_cache[key]=disk
        return cap_cache[key].CloneDropTriangulation()
    def purposefully_covered(track,point=None):
        """Suppress an exposed-cap warning only for actual native copper.

        A named owner zone alone grants nothing: its outline must be straight
        Manhattan/45-degree, contain the ENTIRE conservative native capsule,
        and actual saved same-net fill must enclose that capsule, holes intact.
        Retaining the original rated track is then not an exposed round blob.
        No current/thermal/Kelvin/routing/release qualification is inferred.
        """
        import cec_rectilinear_copper as owner
        import cec_native_contour_regions as signed
        from cec_native_fill_geometry import identity
        uid = (track.m_Uuid.AsString(),None if point is None else (point.x,point.y))
        if uid in cover_cache:
            return cover_cache[uid]
        layer=int(track.GetLayer());net=track.GetNetname()
        zones=list(board.Zones())
        if len(zones)>8192:raise owner.Refused("contour_cover_zone_inventory_bound")
        candidates=[z for z in zones if not z.GetIsRuleArea()
            and z.GetNetname()==net and z.IsOnLayer(layer) and z.IsFilled() and z.HasFilledPolysForLayer(layer)]
        for z in candidates:
            owner._check_deadline(deadline)
            outline=z.Outline()
            zid=z.m_Uuid.AsString()
            if zid not in canonical_owner_cache:
                try:
                    signed.canonical_native_regions(outline,
                        timeout_s=min(10., max(.001, deadline-time.monotonic())))
                    canonical_owner_cache[zid]=True
                except owner.Refused:
                    owner._check_deadline(deadline)
                    canonical_owner_cache[zid]=False
            if not canonical_owner_cache[zid]:continue
            cap=owner._native_capsule(track) if point is None else terminal_disk(track,point)
            outside=cap.CloneDropTriangulation();outside.BooleanSubtract(outline)
            if outside.OutlineCount():continue
            key=(net,layer)
            if key not in fill_cache:
                actual=pcbnew.SHAPE_POLY_SET();vertices=0
                for support in zones:
                    owner._check_deadline(deadline)
                    if (support.GetIsRuleArea() or support.GetNetname()!=net or not support.IsOnLayer(layer)
                            or not support.IsFilled() or not support.HasFilledPolysForLayer(layer)):continue
                    shape=support.GetFilledPolysList(layer)
                    _,count=identity(shape,deadline,max_vertices=200000-vertices)
                    vertices+=count;actual.BooleanAdd(shape)
                identity(actual,deadline,max_vertices=200000)
                fill_cache[key]=actual
            cap.BooleanSubtract(fill_cache[key])
            if not cap.OutlineCount():
                purposeful_covers.append(dict(track_uuid=track.m_Uuid.AsString(),zone_uuid=z.m_Uuid.AsString(),
                    net=net,layer=board.GetLayerName(layer),
                    basis="entire_native_capsule_inside_purposeful_saved_copper" if point is None
                        else "actual_native_terminal_cap_inside_purposeful_saved_copper",
                    **({} if point is None else dict(at_nm=[point.x,point.y]))))
                cover_cache[uid] = True
                return True
        cover_cache[uid] = False
        return False
    def locally_covered_join(track,point):
        """A round-junction claim belongs to its real cap, not a remote edge.

        Reuse the exact native terminal-disk subset of the actual source
        stroke. Both junction members still need a literal canonical owner
        and complete saved same-net fill. A remote body strip never proves
        the junction clean, nor does the local proof claim whole-track cover:
        retain an explicit exact witness of that separate geometric debt.
        Native track copper itself is unchanged and is NOT a void to fill.
        """
        if purposefully_covered(track):return True
        if not purposefully_covered(track,point):return False
        import cec_rectilinear_copper as owner
        from cec_native_fill_geometry import identity
        key=(track.GetNetname(),int(track.GetLayer()))
        missing=owner._native_capsule(track);missing.BooleanSubtract(fill_cache[key])
        if missing.OutlineCount():
            uid=track.m_Uuid.AsString();digest,vertices=identity(missing,deadline,max_vertices=200000)
            body_deficits[uid]=dict(track_uuid=uid,net=track.GetNetname(),layer=board.GetLayerName(track.GetLayer()),
                joint_at_nm=[point.x,point.y],entire_join_disk_covered_by_saved_purposeful_fill=True,
                entire_track_capsule_covered_by_saved_zone_fill=False,
                retained_native_track_copper_still_present=True,
                missing_from_zone_fill_sha256=digest,missing_from_zone_fill_vertices=vertices,
                missing_from_zone_fill_area_mm2=missing.Area()/1e12,
                all_source_track_widths_and_clearance_checks_unchanged=True,
                area_or_distance_waiver_used=False,current_or_release_qualified=False)
        return True
    for track in tracks:
        if time.monotonic() >= deadline or len(findings) >= max_findings:
            complete = False; return result("deadline_or_finding_bound")
        uid = track.m_Uuid.AsString(); a, b = track.GetStart(), track.GetEnd()
        if scope is None or uid in scope:
            examined += 1
        if not track.GetNetname():
            continue
        for p, other in ((a,b), (b,a)):
            junctions[track.GetNetCode(), int(track.GetLayer()), p.x, p.y].append((track, other))
        if scope is not None and uid not in scope:
            continue
        width = int(track.GetWidth()); length = math.hypot(b.x-a.x, b.y-a.y)
        if (width >= min_width_mm*1e6 and length < width*max_length_width_ratio
                and not (covered(track, a) and covered(track, b))):
            try:
                if purposefully_covered(track):continue
            except (ValueError,RuntimeError) as exc:
                complete=False;return result("purposeful_cover_unproved:"+str(exc))
            issue = row("short_wide_capsule", track, [uid])
            issue.update(length_mm=length/1e6, length_width_ratio=length/width,
                         cap_extension_mm=width/2e6)
            findings.append(issue)
    for key, incident in sorted(junctions.items()):
        if time.monotonic() >= deadline or len(findings) >= max_findings:
            complete = False; return result("deadline_or_finding_bound")
        if len(incident) != 2:
            continue  # more complicated branches need their own owner graph
        (a, ao), (b, bo) = incident
        if a.m_Uuid.AsString() == b.m_Uuid.AsString():
            continue
        ids = [a.m_Uuid.AsString(), b.m_Uuid.AsString()]
        if scope is not None and not scope.intersection(ids):
            continue
        wide, narrow = (a,b) if a.GetWidth() >= b.GetWidth() else (b,a)
        if wide.GetWidth() < min_width_mm*1e6:
            continue
        p = pcbnew.VECTOR2I(key[2], key[3])
        va, vb = (ao.x-p.x,ao.y-p.y), (bo.x-p.x,bo.y-p.y)
        if not any(va) or not any(vb) or va[0]*vb[1]-va[1]*vb[0] == 0 or covered(wide,p):
            continue
        unequal = wide.GetWidth() >= narrow.GetWidth()*unequal_width_ratio
        if not unequal and narrow.GetWidth() < min_width_mm*1e6:
            continue
        try:
            # Enclose the actual native join cap, not unrelated distant body
            # edges. Equal wide elbows require BOTH source junction disks;
            # any remote zone-body deficit stays separately disclosed above.
            if locally_covered_join(wide,p) and (unequal or locally_covered_join(narrow,p)):
                continue
        except (ValueError, RuntimeError) as exc:
            complete=False;return result("purposeful_cover_unproved:"+str(exc))
        issue = row("unequal_width_round_join" if unequal else "wide_round_elbow", wide, ids, p)
        issue["narrow_width_mm"] = narrow.GetWidth()/1e6
        findings.append(issue)
    if include_terminal_caps:
        # Long tracks have round ends too. Their aspect ratio must not hide a
        # terminal blob. Native pads may hide a cap visually (including a
        # legitimate plated land); this is NOT drill/contact/current credit.
        # A bbox, another face, an outline-only zone or a coincident duplicate
        # track cannot hide it. Existing elbow reports avoid double counting.
        existing={(u,tuple(round(v*1e6) for v in f['at_mm'])) for f in findings
            if f.get('at_mm') is not None for u in f.get('track_uuids',[])}
        wide_by_face=defaultdict(list)
        for t in tracks:
            if t.GetWidth()>=min_width_mm*1e6:
                wide_by_face[t.GetNetCode(),int(t.GetLayer())].append(t)
        try:
            import cec_rectilinear_copper as owner
            for track in tracks:
                owner._check_deadline(deadline)
                uid=track.m_Uuid.AsString();width=int(track.GetWidth())
                if (not track.GetNetname() or width<min_width_mm*1e6
                        or scope is not None and uid not in scope
                        or track.GetLength()<width*max_length_width_ratio):continue
                if purposefully_covered(track):continue
                a,b=track.GetStart(),track.GetEnd();face=int(track.GetLayer());key=(track.GetNetCode(),face)
                for name,point,other in (('start',a,b),('end',b,a)):
                    owner._check_deadline(deadline)
                    if len(findings)>=max_findings:
                        complete=False;return result('deadline_or_finding_bound')
                    if (uid,(point.x,point.y)) in existing or purposefully_covered(track,point):continue
                    disk=terminal_disk(track,point);hidden=False
                    for pad in terminal_pads[key]:
                        owner._check_deadline(deadline)
                        pkey=(pad.m_Uuid.AsString(),face)
                        if pkey not in terminal_pad_cache:
                            poly=pcbnew.SHAPE_POLY_SET()
                            pad.GetEffectiveShape(face).TransformToPolygon(poly,1,pcbnew.ERROR_INSIDE)
                            terminal_pad_cache[pkey]=poly
                        outside=disk.CloneDropTriangulation();outside.BooleanSubtract(terminal_pad_cache[pkey])
                        if not outside.OutlineCount():hidden=True;break
                    outward=(point.x-other.x,point.y-other.y);norm=sum(v*v for v in outward)
                    if not hidden and norm:
                        for neighbor in wide_by_face[key]:
                            owner._check_deadline(deadline)
                            if neighbor.m_Uuid.AsString()==uid or neighbor.GetWidth()<width:continue
                            forward=max(sum((p[j]-point[j])*outward[j] for j in (0,1))
                                for p in (neighbor.GetStart(),neighbor.GetEnd()))
                            if forward<=0 or 4*forward*forward<width*width*norm:continue
                            outside=disk.CloneDropTriangulation();outside.BooleanSubtract(owner._native_capsule(neighbor))
                            if not outside.OutlineCount():hidden=True;break
                    if hidden:continue
                    issue=row('wide_exposed_terminal_cap',track,[uid],point)
                    issue.update(endpoint=name,cap_extension_mm=width/2e6,
                        basis='actual_source_cap_not_hidden_by_same_face_native_pad_forward_track_or_purposeful_fill')
                    findings.append(issue)
        except (ValueError,RuntimeError) as exc:
            complete=False;return result('terminal_cap_review_unproved:'+str(exc))
    # A circular zone landing is not a PCB_TRACK capsule, so the older audit
    # missed it entirely. Observe compact convex curved SOURCE outlines, not
    # drill/annular rings or tiny native fill tessellation at normal corners.
    zones=list(board.Zones())
    if len(zones)>8192:
        complete=False;return result("zone_inventory_bound")
    from shapely.geometry import Polygon
    for z in zones:
        if time.monotonic()>=deadline or len(findings)>=max_findings:
            complete=False;return result("deadline_or_finding_bound")
        if scope is not None or z.GetIsRuleArea() or not z.GetNetname() or z.GetNetname().rsplit("/",1)[-1]=="GND":continue
        outline=z.Outline()
        if outline.OutlineCount()!=1 or outline.HoleCount(0):continue
        ring=outline.Outline(0)
        if ring.ArcCount() or not 12<=ring.PointCount()<=4096:continue
        points=[(ring.CPoint(i).x,ring.CPoint(i).y) for i in range(ring.PointCount())]
        curved=sum(a[0]!=b[0] and a[1]!=b[1] and abs(a[0]-b[0])!=abs(a[1]-b[1]) for a,b in zip(points,points[1:]+points[:1]))
        if curved<8:continue
        poly=Polygon(points)
        if not poly.is_valid or not poly.equals(poly.convex_hull):continue
        x0,y0,x1,y1=poly.bounds;small=min(x1-x0,y1-y0);large=max(x1-x0,y1-y0)
        if small<min_width_mm*1e6 or large>1.6*small:continue
        findings.append(dict(type="rounded_compact_zone_landing",net=z.GetNetname(),
            layer=",".join(board.GetLayerName(int(l)) for l in z.GetLayerSet().CuStack()),
            track_uuids=[],zone_uuids=[z.m_Uuid.AsString()],width_mm=small/1e6,
            outline_vertices=ring.PointCount(),noncanonical_edges=curved,
            locked=bool(z.IsLocked()),severity="review",ordinary_neckdown_allowed=False,
            owner_request="native_power_contour_reconstruction_and_receiving"))
    return result("complete")


def component_requests(board, *, layer_ids=None, net_scope=None,
                       min_width_mm=1.0, timeout_s=2.0,
                       max_tracks=1024, max_component_tracks=64,
                       resident_width_floors_nm=None):
    """Read-only geometry-derived ownership requests for complete wide runs.

    Seed from the actual contour audit, then group contacting native wide
    strokes on the same net/layer and within one existing group owner. This
    avoids fixing one bulb at a time with overlapping same-net filler zones.
    It neither grants locked-item authority nor invents a current budget:
    callers must compile dimensions, receive any widening, and independently
    qualify the complete saved native cover. Unsupported/bounded-out input
    returns incomplete, not an empty successful repair portfolio.
    """
    import pcbnew
    import cec_rectilinear_copper as owner
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 <= timeout_s <= 10
            or type(max_tracks) is not int or not 1 <= max_tracks <= 4096
            or type(max_component_tracks) is not int or not 1 <= max_component_tracks <= 128
            or type(min_width_mm) not in (int, float) or not math.isfinite(min_width_mm)
            or not 0 < min_width_mm <= 100):
        raise ValueError("invalid_contour_component_bounds")
    layers = set(board.GetEnabledLayers().CuStack())
    if layer_ids is not None:
        if (not isinstance(layer_ids, (list, tuple, set))
                or any(type(v) is not int or v not in layers for v in layer_ids)):
            raise ValueError("invalid_contour_component_layers")
        layers &= set(layer_ids)
    if net_scope is not None and (not isinstance(net_scope, (list, tuple, set))
            or any(type(n) is not str or not n for n in net_scope)):
        raise ValueError("invalid_contour_component_nets")
    nets = None if net_scope is None else set(net_scope)
    if resident_width_floors_nm is not None:
        if (not isinstance(resident_width_floors_nm, dict)
                or any(not isinstance(k, tuple) or len(k) != 2 or type(k[0]) is not str
                    or not k[0] or type(k[1]) is not int or k[1] not in layers
                    or type(v) is not int or not 1 <= v <= 100_000_000
                    for k, v in resident_width_floors_nm.items())):
            raise ValueError("invalid_resident_contour_width_floors")
    result = dict(schema=1, complete=False, requests=[], reason=None,
        source_mutated=False, replacement_authorized=False,
        release_authority=False, new_current_authority=False)
    deadline = time.monotonic() + timeout_s
    try:
        owner._check_deadline(deadline)
        audit = audit_board(board, min_width_mm=min_width_mm,
            timeout_s=max(0, deadline-time.monotonic()))
        if not audit["complete"]:
            raise owner.Refused("source_contour_audit_incomplete:"+audit["reason"])
        result["source_finding_count"] = audit["finding_count"]
        inventory = sorted((t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"
            and t.GetNetname() and t.GetNetname().rsplit("/", 1)[-1] != "GND"
            and t.GetLayer() in layers and t.GetWidth() >= min_width_mm*1e6
            and (nets is None or t.GetNetname() in nets)), key=lambda t: t.m_Uuid.AsString())
        result["excluded_nonresident_track_uuids"] = []
        if resident_width_floors_nm is not None:
            retained = []
            for t in inventory:
                floor = resident_width_floors_nm.get((t.GetNetname(), int(t.GetLayer())))
                if floor is not None and t.GetWidth() >= floor:
                    retained.append(t)
                else:
                    result["excluded_nonresident_track_uuids"].append(t.m_Uuid.AsString())
            inventory = retained
        if len(inventory) > max_tracks:
            raise owner.Refused("contour_component_track_bound")
        index = {t.m_Uuid.AsString(): i for i, t in enumerate(inventory)}
        if len(index) != len(inventory):
            raise owner.Refused("ambiguous_contour_component_identity")
        seeds = {u for r in audit["findings"] for u in r["track_uuids"] if u in index}
        parents = list(range(len(inventory)))
        keys = [(t.GetNetname(), int(t.GetLayer()), owner._group_uuid(t)) for t in inventory]
        boxes = [t.GetBoundingBox() for t in inventory]
        shapes = [t.GetEffectiveShape(int(t.GetLayer())) for t in inventory]
        def root(i):
            while parents[i] != i:
                parents[i] = parents[parents[i]]; i = parents[i]
            return i
        for i in range(len(inventory)):
            owner._check_deadline(deadline)
            for j in range(i):
                if keys[i] == keys[j] and boxes[i].Intersects(boxes[j]) and shapes[i].Collide(shapes[j], 0):
                    parents[root(i)] = root(j)
        groups = defaultdict(list)
        for i, t in enumerate(inventory):
            groups[root(i)].append(t)
        for tracks in groups.values():
            owner._check_deadline(deadline)
            ids = [t.m_Uuid.AsString() for t in tracks]
            if not seeds.intersection(ids):
                continue
            if len(tracks) > max_component_tracks:
                raise owner.Refused("contour_component_owner_bound")
            rows = [owner._track_row(t) for t in tracks]
            result["requests"].append(dict(net=rows[0]["net"], layer_id=rows[0]["layer_id"],
                group_uuid=rows[0]["group_uuid"], source_tracks=rows,
                finding_types=sorted({r["type"] for r in audit["findings"]
                    if set(r["track_uuids"]).intersection(ids)}),
                locked_track_uuids=[r["uuid"] for r in rows if r["locked"]],
                requires_existing_dimensional_authority=True,
                requires_independent_native_receiving=True))
        result["requests"].sort(key=lambda r: (r["net"], r["layer_id"], r["source_tracks"][0]["uuid"]))
        result.update(complete=True, reason="native_contact_components_requested")
    except (owner.Refused, ValueError, RuntimeError) as exc:
        result.update(reason=str(exc), requests=[])
    return result


def finding_requests(board, *, timeout_s=2.0,include_terminal_caps=False,min_width_mm=1.0):
    """Literal one/two-track contour scopes; never a current or cut grant.

    A foreign-obstructed member can refuse a whole connected component. This
    bounded fallback requests only the actual local capsule/elbow inventory,
    leaving source width, group/lock permissions and whole-board receiving to
    its existing geometry owner. Unsupported zone-only findings stay visible.
    """
    import cec_rectilinear_copper as owner
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10. or type(include_terminal_caps) is not bool
            or type(min_width_mm) not in (int,float) or not math.isfinite(min_width_mm)
            or not 0<min_width_mm<=100.):
        raise ValueError('bounded_local_native_contour_inventory_required')
    deadline=time.monotonic()+timeout_s
    result=dict(schema=1,complete=False,requests=[],reason=None,source_mutated=False,
        replacement_authorized=False,release_authority=False,new_current_authority=False)
    try:
        audit=audit_board(board,timeout_s=max(0,deadline-time.monotonic()),include_terminal_caps=include_terminal_caps,
            min_width_mm=min_width_mm)
        if not audit['complete']:raise owner.Refused('complete_source_local_contour_audit_required')
        items=list(board.GetTracks())
        live={t.m_Uuid.AsString():t for t in items}
        if len(items)>8192 or len(live)!=len(items):raise owner.Refused('unique_bounded_local_native_tracks_required')
        requests={};unsupported=0
        for finding in audit['findings']:
            owner._check_deadline(deadline)
            ids=tuple(sorted(finding.get('track_uuids',[])))
            if not 1<=len(ids)<=2 or not set(ids)<=live.keys():unsupported+=1;continue
            tracks=[live[u] for u in ids]
            if any(t.GetClass()!='PCB_TRACK' for t in tracks):unsupported+=1;continue
            rows=[owner._track_row(t) for t in tracks]
            if (len({(r['net'],r['layer_id']) for r in rows})!=1 or not rows[0]['net']
                    or rows[0]['net'].rsplit('/',1)[-1]=='GND'):
                unsupported+=1;continue
            requests[ids]=dict(net=rows[0]['net'],layer_id=rows[0]['layer_id'],source_tracks=rows,
                actual_source_length_nm=sum(t.GetLength() for t in tracks),
                requires_existing_dimensional_authority=True,requires_independent_native_receiving=True)
            if include_terminal_caps:
                requests[ids]['finding_types']=sorted({f['type'] for f in audit['findings']
                    if tuple(sorted(f.get('track_uuids',[])))==ids})
        result.update(complete=True,source_finding_count=audit['finding_count'],unsupported_finding_count=unsupported,
            requests=sorted(requests.values(),key=lambda r:(r['actual_source_length_nm'],r['net'],r['layer_id'],
                [t['uuid'] for t in r['source_tracks']])),reason='literal_local_native_capsule_and_elbow_requests')
    except (owner.Refused,ValueError,RuntimeError) as exc:
        result.update(reason=str(exc),requests=[])
    return result
