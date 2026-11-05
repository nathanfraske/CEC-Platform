"""Contact-inclusive source-sector preservation for owned terminal contours.

Retained source-current strokes and real plated frames remain with the frozen
terminal-shadow owner. Pour-only ports additionally retain original filled
sectors anchored at those actual terminals. A conservative, native full-floor
erosion partition must also survive: keeping a pad's pixels alone cannot hide
a newly pinched feed. This is geometric preservation, not zone/barrel ampacity,
thermal, Kelvin, or fabrication qualification.
"""
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import tempfile
import time

import pcbnew
from shapely.geometry import Polygon
from shapely.ops import unary_union
import cec_terminal_shadow_keeper_finish as base

POLICY = 'source-contact-sector-and-native-width-partition-preservation-v1'
NORMALS = ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1))
require = base.require
native = base.native


def _shape(poly):
    def points(ring):
        return [(ring.CPoint(i).x,ring.CPoint(i).y) for i in range(ring.PointCount())]
    return unary_union([Polygon(points(poly.Outline(i)),
        [points(poly.Hole(i,j)) for j in range(poly.HoleCount(i))])
        for i in range(poly.OutlineCount())])


def _points(shape,*,minimum=4):
    require(shape.geom_type == 'Polygon' and shape.is_valid and not shape.interiors,
        'one_valid_unperforated_contact_sector_profile_required')
    points = list(shape.exterior.coords)[:-1]
    require(minimum <= len(points) <= 1024 and all(v == int(v) for p in points for v in p),
        'integer_contact_sector_profile_without_rounding_required')
    return [[int(x),int(y)] for x,y in points]


def _halfplane(bounds, at, normal):
    require(normal in NORMALS and all(v == int(v) for v in (*bounds,*at)),
        'canonical_integer_source_terminal_halfplane_required')
    x0,y0,x1,y1 = map(int,bounds); span = max(x1-x0,y1-y0)+1000000
    points = [(x0-span,y0-span),(x1+span,y0-span),(x1+span,y1+span),(x0-span,y1+span)]
    value = lambda p: sum(normal[k]*(p[k]-at[k]) for k in (0,1))
    out = []
    for a,z in zip(points,points[1:]+points[:1]):
        va,vz = value(a),value(z)
        if va >= 0: out.append(a)
        if (va < 0) != (vz < 0):
            t = Fraction(va,va-vz)
            out.append(tuple(Fraction(a[k])+t*(z[k]-a[k]) for k in (0,1)))
    require(out and all(Fraction(v).denominator == 1 for p in out for v in p),
        'half_nanometre_source_sector_not_snapped')
    return Polygon([(int(x),int(y)) for x,y in out])


def _edges(points, original):
    """All newly authored edges are canonical; old subedges remain literal."""
    inherited = []
    for a,z in zip(points,points[1:]+points[:1]):
        if base.native._centerline_allowed(a,z,'chamfer45'): continue
        matches = [i for i,(p,r) in enumerate(zip(original,original[1:]+original[:1]))
            if all((v[0]-p[0])*(r[1]-p[1]) == (v[1]-p[1])*(r[0]-p[0])
                and all(min(p[k],r[k]) <= v[k] <= max(p[k],r[k]) for k in (0,1)) for v in (a,z))]
        require(len(matches) == 1, 'new_noncanonical_contact_sector_edge_not_inherited')
        inherited.append(dict(start_nm=a,end_nm=z,source_edge_index=matches[0]))
    return inherited


def _chord_closure(profile,original):
    """Close envelope scallops, but never fill an original reservation.

    The outer supports come from the retained real geometry; clipping to the
    literal old owner preserves intentional pockets and assembly clearances.
    The one-DBU construction margin belongs only to the derived support hull,
    not to a contact-loss, angle or clearance acceptance tolerance.
    """
    cover=base.native.purposeful_envelope(base.native._poly(_points(profile)),
        style='chamfer45',margin_nm=1,grid_nm=1)
    closed=Polygon(cover).intersection(original)
    require(closed.covers(profile),'contact_sector_chord_closure_lost_retained_support')
    _points(closed)
    return closed


def _contacts(board, q):
    face = q['source_configuration']['layers'][0]
    old = next(z for z in board.Zones() if base.force._uid(z) == q['zone_uuid'])
    items = [*board.GetTracks(),*(p for fp in board.GetFootprints() for p in fp.Pads())]
    require(len(items) <= 16384,'bounded_actual_contact_sector_inventory_required')
    contacts = []; deadline = time.monotonic()+10.
    for item in items:
        base.native._check_deadline(deadline)
        uid = base.force._uid(item)
        if (uid in q['track_uuids'] or not item.IsOnLayer(face)
                or item.GetNetname() != old.GetNetname()): continue
        contact = base._shape(item,face); contact.BooleanIntersection(old.GetFilledPolysList(face))
        if contact.OutlineCount() and contact.Area() > 0: contacts.append((uid,contact))
    require(1 <= len(contacts) <= 256,'bounded_positive_source_sector_contacts_required')
    return contacts


def _protected_contacts(board,q):
    old = next(z for z in board.Zones() if base.force._uid(z) == q['zone_uuid'])
    face = q['source_configuration']['layers'][0]
    for uid,contact in _contacts(board,q):
        outside = contact.CloneDropTriangulation(); outside.BooleanSubtract(base.native._poly(q['points_nm']))
        # KiCad's incumbent filled contact may already extend beyond its
        # authored boundary. Retain only that exact old fringe, never a new
        # geometric allowance, snapped point or area-loss tolerance.
        fringe = contact.CloneDropTriangulation(); fringe.BooleanSubtract(old.Outline())
        outside.BooleanSubtract(fringe)
        require(not outside.OutlineCount(),'original_contact_sector_material_outside_profile:'+uid)
        for row in q['regional_contract']['regional_fill_binding']['protected_regions']:
            region = next(z for z in board.Zones() if base.force._uid(z) == row['native']['uuid'])
            void = region.Outline().CloneDropTriangulation(); void.BooleanSubtract(region.GetFilledPolysList(face))
            overlap = contact.CloneDropTriangulation(); overlap.BooleanIntersection(void)
            require(not overlap.OutlineCount(),'contact_sector_intrudes_stronger_native_void:'+uid)
        contact.Fracture()
        yield uid,contact


def _floor_partitions(poly,contacts,width_nm,deadline):
    require(type(width_nm) is int and width_nm > 0,'positive_actual_source_floor_required')
    kernel = poly.CloneDropTriangulation(); kernel.Simplify()
    kernel.Inflate(-((width_nm+1)//2),pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,1)
    require(kernel.OutlineCount() <= 128,'bounded_native_source_floor_components_required')
    result = []
    for i in range(kernel.OutlineCount()):
        base.native._check_deadline(deadline)
        component = kernel.CloneDropTriangulation()
        for j in reversed(range(component.OutlineCount())):
            if j != i: component.RemoveOutline(j)
        keys = set()
        for uid,contact in contacts:
            witness = contact.CloneDropTriangulation(); witness.BooleanIntersection(component)
            if witness.OutlineCount() and witness.Area() > 0: keys.add(uid)
        if keys: result.append(keys)
    return result


def _floor_receive(before_poly,after_poly,contacts,width_nm):
    deadline = time.monotonic()+10.
    old = _floor_partitions(before_poly,contacts,width_nm,deadline)
    new = _floor_partitions(after_poly,contacts,width_nm,deadline)
    require(old and any(len(p) >= 2 for p in old),'positive_source_floor_port_partition_required')
    lost = [sorted(p) for p in old if not any(p <= q for q in new)]
    require(not lost,'source_floor_pour_port_partition_lost:'+str(lost))
    return dict(ok=True,complete=True,actual_source_floor_nm=width_nm,
        source_port_partitions=[sorted(p) for p in old],candidate_port_partitions=[sorted(p) for p in new],
        every_positive_source_floor_port_partition_preserved=True,
        native_round_erosion_error_nm=1,geometry_preservation_not_ampacity_or_barrel_rating=True)


def plan(source,*,board_hint,zone_uuid,track_uuids,allow_locked_source=False):
    started = time.monotonic()
    original_plan = base.plan(source,board_hint=board_hint,zone_uuid=zone_uuid,
        track_uuids=track_uuids,allow_locked_source=allow_locked_source)
    source = Path(source).resolve(); board = pcbnew.LoadBoard(str(source))
    old = next(z for z in board.Zones() if base.force._uid(z) == zone_uuid)
    face = original_plan['source_configuration']['layers'][0]
    original = _shape(old.Outline()); base_profile = Polygon(original_plan['points_nm'])
    original_points = _points(original); contacts = _contacts(board,original_plan)
    uncovered = []
    for uid,contact in contacts:
        inside = contact.CloneDropTriangulation(); inside.BooleanIntersection(old.Outline())
        missing = inside.CloneDropTriangulation(); missing.BooleanSubtract(base.native._poly(original_plan['points_nm']))
        if missing.OutlineCount():
            # Use the literal polygons for scheduling. A second integer
            # Boolean intersection may itself move the incumbent boundary
            # by one DBU; it is not permission to invent a larger port.
            uncovered.append((uid,contact,_shape(contact).intersection(original)))
    require(1 <= len(uncovered) <= 8,'actual_bounded_pour_only_source_port_required')
    vias = {base.force._uid(v):v for v in board.GetTracks() if v.GetClass() == 'PCB_VIA'}
    menus = []
    for uid,contact,port in uncovered:
        options = []
        for frame in original_plan['retained_centered_frames']:
            via = vias[frame['via_uuid']]; at = tuple(via.GetPosition())
            for normal in NORMALS:
                half = _halfplane(original.bounds,at,normal); sector = original.intersection(half)
                if not sector.covers(port) or sector.geom_type != 'Polygon' or sector.interiors: continue
                joined = unary_union([base_profile,sector])
                try: _edges(_points(joined),original_points)
                except ValueError: continue
                native_sector = old.GetFilledPolysList(face).CloneDropTriangulation()
                native_sector.BooleanIntersection(base.native._poly(_points(half,minimum=3)))
                # One actual incumbent native component reaches both the
                # port and an existing plated terminal. No guessed bridge.
                anchor = base._shape(via,face)
                connected = False
                for i in range(native_sector.OutlineCount()):
                    part = native_sector.CloneDropTriangulation()
                    for j in reversed(range(part.OutlineCount())):
                        if j != i: part.RemoveOutline(j)
                    a = part.CloneDropTriangulation(); a.BooleanIntersection(contact)
                    z = part.CloneDropTriangulation(); z.BooleanIntersection(anchor)
                    if a.OutlineCount() and z.OutlineCount() and a.Area()>0 and z.Area()>0: connected=True
                if connected:
                    options.append((dict(contact_uuid=uid,via_uuid=frame['via_uuid'],
                        anchor_nm=list(at),normal=list(normal),halfplane_nm=_points(half,minimum=3)),sector))
        require(options,'no_actual_anchored_source_contact_sector:'+uid)
        menus.append(options)
    combinations = 1
    for options in menus: combinations *= len(options)
    require(combinations <= 256,'finite_source_contact_sector_portfolio_exceeded')
    candidates = []
    for choice in itertools.product(*menus):
        joined = unary_union([base_profile,*[sector for _,sector in choice]])
        try:
            joined = _chord_closure(joined,original)
            points = _points(joined); inherited = _edges(points,original_points)
            out = base.native._poly(points); out.BooleanSubtract(old.Outline())
            require(not out.OutlineCount(),'source_contact_sector_expanded_authored_owner')
        except ValueError: continue
        candidates.append((joined.difference(base_profile).area,
            json.dumps([row for row,_ in choice],sort_keys=True),points,inherited,[row for row,_ in choice]))
    refused = []; chosen = None
    for _,_,points,inherited,rows in sorted(candidates):
        proxy = old.GetFilledPolysList(face).CloneDropTriangulation()
        proxy.BooleanIntersection(base.native._poly(points))
        for _,contact in contacts: proxy.Append(contact)
        try:
            floor = _floor_receive(old.GetFilledPolysList(face),proxy,contacts,
                original_plan['full_source_current_width_floor_nm'])
            chosen = points,inherited,rows,floor; break
        except ValueError as exc: refused.append(str(exc))
    require(chosen is not None,'no_source_floor_preserving_contact_sector:'+str(refused[:3]))
    points,inherited,rows,floor = chosen
    q = base.plain(original_plan); q.update(policy=POLICY,points_nm=points,
        authority_sha256=base.force._hash(Path(__file__).resolve()),
        original_terminal_plan_sha256=hashlib.sha256(json.dumps(original_plan,sort_keys=True).encode()).hexdigest(),
        selected_source_sectors=rows,inherited_literal_noncanonical_outline_subedges=inherited,
        source_bounded_chord_closure_applied=True,
        finite_sector_combinations=combinations,source_floor_preflight=floor,
        prior_minimum_area_width_refusals=len(refused))
    q['helper_sha256'][str(Path(base.__file__).resolve())] = base.force._hash(Path(base.__file__))
    region = q['regional_contract']; region['polygon_nm'] = points
    region['actual_fill_envelope_nm'] = base.native._fill_envelope(points,style='chamfer45',margin_nm=4)
    region['regional_fill_binding'] = base.regional.source_binding(board,region,time.monotonic()+10.)
    list(_protected_contacts(board,q))
    require(time.monotonic()-started < 10.,'source_contact_sector_plan_deadline')
    return base.plain(q)


def construct(source,q):
    require(plan(source,**base._arguments(q)) == q,'stale_or_forged_source_contact_sector_plan')
    before,after = [pcbnew.LoadBoard(str(source)) for _ in range(2)]
    base.discard_items(after,[t for t in after.GetTracks() if base.force._uid(t) in q['track_uuids']])
    zone = next(z for z in after.Zones() if base.force._uid(z) == q['zone_uuid'])
    old = next(z for z in before.Zones() if base.force._uid(z) == q['zone_uuid'])
    face = q['source_configuration']['layers'][0]
    zone.UnFill(); zone.Outline().RemoveAllContours(); zone.Outline().Append(base.native._poly(q['points_nm']))
    selected = pcbnew.ZONES(); selected.append(zone); base.fill.compile_selected(after,selected,timeout_s=10.)
    actual = base.regional._combine(before,zone.GetFilledPolysList(face),q['regional_contract'],time.monotonic()+10.)
    # Append each clipped original record literally; a global union would
    # retessellate old native material and can shave a contact by one DBU.
    for row in q['selected_source_sectors']:
        for i in range(old.GetFilledPolysList(face).OutlineCount()):
            part = old.GetFilledPolysList(face).CloneDropTriangulation()
            for j in reversed(range(part.OutlineCount())):
                if j != i: part.RemoveOutline(j)
            part.BooleanIntersection(base.native._poly(row['halfplane_nm']))
            for protected in q['regional_contract']['regional_fill_binding']['protected_regions']:
                region = next(z for z in before.Zones() if base.force._uid(z) == protected['native']['uuid'])
                void = region.Outline().CloneDropTriangulation();void.BooleanSubtract(region.GetFilledPolysList(face))
                intrusion = part.CloneDropTriangulation();intrusion.BooleanIntersection(void)
                require(not intrusion.OutlineCount(),'source_contact_sector_intrudes_protected_native_void')
            part.Fracture(); actual.Append(part)
    for _,contact in _protected_contacts(before,q): actual.Append(contact)
    zone.UnFill(); zone.SetFilledPolysList(face,actual); zone.SetIsFilled(True)
    return after


def observe(before,after,q):
    face = q['source_configuration']['layers'][0]; deadline = time.monotonic()+10.
    old,new = [next(z for z in b.Zones() if base.force._uid(z) == q['zone_uuid']) for b in (before,after)]
    require(base.landing._configuration(new) == q['source_configuration'],'contact_sector_owner_process_changed')
    actual = new.GetFilledPolysList(face); contacts = list(_protected_contacts(before,q))
    for uid,contact in contacts:
        require(base.regional.exact_source_contour_present(actual,contact,deadline),
            'literal_source_contact_sector_contact_lost:'+uid)
    for uid in q['retained_track_uuids']:
        track = next(t for t in after.GetTracks() if base.force._uid(t) == uid)
        missing = base.native._native_capsule(track); missing.BooleanSubtract(actual)
        require(not missing.OutlineCount(),'retained_full_source_width_contact_sector_capsule_lost:'+uid)
    floor = _floor_receive(old.GetFilledPolysList(face),actual,contacts,q['full_source_current_width_floor_nm'])
    first,last = [base.assembly.polygon_from_native(base.material.source_material(b,old.GetNetname(),face,
        time.monotonic()+10.)) for b in (before,after)]
    removed = first.difference(last); added = last.difference(first)
    require(removed.area >= .0025,'no_visible_native_source_contact_sector_progress')
    return base.plain(dict(ok=True,complete=True,every_original_surviving_keeper_contact_material_preserved=True,
        every_retained_source_width_capsule_enclosed=True,actual_native_source_floor_receiving=floor,
        removed_native_area_mm2=removed.area,added_native_area_mm2=added.area,
        removed_native_bounds_mm=list(removed.bounds),source_curvature=base.centered.curve_runs(first),
        candidate_curvature=base.centered.curve_runs(last),
        saved_trace_length_mm=sum(math.dist(r['start_nm'],r['end_nm'])
            for r in q['complete_source_tracks'] if r['uuid'] in q['track_uuids'])/1e6,
        current_or_barrel_qualified=False,release_authority=False))


def receive_literal(source,candidate,q):
    result = dict(ok=False,complete=False,errors=[],current_or_barrel_qualified=False,
        fresh_whole_native_current_clipped_and_reference_receiving_still_required=True,release_authority=False)
    try:
        source,candidate = [Path(p).resolve() for p in (source,candidate)]
        require(source != candidate,'distinct_saved_source_contact_sector_candidate_required')
        epoch = base.force._code_identity(); families = [base.force._family(p,q['board_hint']) for p in (source,candidate)]
        rebuilt = construct(source,q)
        with tempfile.TemporaryDirectory(prefix='cec-contact-sector-') as work:
            expected = Path(work)/'board.kicad_pcb'; base.field._save_field_snapshot(rebuilt,expected)
            require(base.syntax._freeze(base.additive._nodes(expected)[0]) == base.syntax._freeze(base.additive._nodes(candidate)[0]),
                'contact_sector_changed_unowned_saved_native_evidence')
        require(base.force._sidecars(source) == base.force._sidecars(candidate),'contact_sector_changed_companions')
        old,new = [base.additive._nodes(p)[1] for p in (source,candidate)]
        require(old.keys()-new.keys() == set(q['track_uuids']) and not new.keys()-old.keys(),
            'exact_source_contact_sector_stub_retirement_required')
        require(all(base.syntax._freeze(n) == base.syntax._freeze(new[u]) for u,n in old.items()
            if u not in set(q['track_uuids'])|{q['zone_uuid']}),'all_other_contact_sector_objects_and_ground_must_remain_literal')
        before,after = [pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        prior = base.ordinary._partition(before,time.monotonic()+10.,retired_uuids=set(q['track_uuids']))
        last = base.ordinary._partition(after,time.monotonic()+10.,retained_keys=set().union(*prior))
        require(all(any(p <= z for z in last) for p in prior),'source_contact_sector_native_partition_lost')
        progress = observe(before,after,q)
        require(epoch == base.force._code_identity() and families == [base.force._family(p,q['board_hint']) for p in (source,candidate)],
            'source_contact_sector_family_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=base.force._hash(source),candidate_sha256=base.force._hash(candidate),
            code_identity=epoch,exact_saved_source_native_reconstruction=True,
            all_other_native_items_and_ground_sheets_literal=True,every_surviving_native_partition_preserved=True,
            retired_track_uuids=q['track_uuids'],modified_zone_uuids=[q['zone_uuid']],
            modified_nets=[q['source_configuration']['net']],actual_saved_progress=progress)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError,StopIteration,base.native.Refused) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def discover(source,*,board_hint,allow_locked_source=False,maximum_trials=8):
    """Reuse real geometric menus; independently rederive every sector owner."""
    source=Path(source).resolve();digest=base.force._hash(source);epoch=base.force._code_identity()
    found=base.discover(source,board_hint=board_hint,allow_locked_source=allow_locked_source,
        maximum_trials=maximum_trials)
    proposals=[];refusals=list(found['refusals'])
    for row in found['proposals']:
        try:
            proposal=plan(source,board_hint=board_hint,**row['target'])
            proposals.append(dict(target=row['target'],proposal=proposal))
        except (ValueError,RuntimeError,KeyError,TypeError,native.Refused) as exc:
            refusals.append(dict(target=row['target'],reason=type(exc).__name__+':'+str(exc)))
    require(digest==base.force._hash(source) and epoch==base.force._code_identity(),
        'contact_sector_readonly_source_or_runtime_changed')
    return dict(ok=True,complete=True,source=str(source),source_sha256=digest,code_identity=epoch,
        maximum_trials=maximum_trials,geometric_menus=found['geometric_menus'],
        proposals=proposals,refusals=refusals,actual_geometry_constructed=False,
        finite_search_is_not_all_contours_clean_proof=True,current_or_barrel_qualified=False,release_authority=False)
