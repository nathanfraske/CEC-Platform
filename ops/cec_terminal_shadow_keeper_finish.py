"""Retire terminal-shadowed stubs and rebuild their actual owned keeper.

A short centerline wholly inside an existing plated land is not, by itself,
retirement authority. All surviving native partitions and every original
keeper contact must survive; retained strokes keep their full source-current
width. The complete saved phase is reconstructed independently. Ground and
all other owners stay literal. Full native/current/Kelvin gates remain external.
"""
import json
import math
from pathlib import Path
import tempfile
import time

import pcbnew
from shapely.geometry import Polygon
from shapely.ops import unary_union
import cec_additive_route_receiving as additive
import cec_assembly_envelope as assembly
import cec_centered_terminal_landing as centered
import cec_copper_echo as syntax
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_planar_reflow as current
import cec_native_contour_regions as signed
import cec_native_pocket_preflight as material
import cec_native_track_ports as ports
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as native
import cec_regional_fill as regional
import cec_rounded_landing as landing
import cec_zone_fill as fill
from cec_native_items import discard_items

POLICY = 'source-current-terminal-shadow-stub-and-keeper-rebuild-v1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def plain(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _shape(item, face):
    poly = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(poly, face, 0, 1000, pcbnew.ERROR_OUTSIDE, False)
    poly.Simplify()
    return poly


def plan(source, *, board_hint, zone_uuid, track_uuids, allow_locked_source=False):
    require(type(board_hint) is str and bool(board_hint) and type(zone_uuid) is str
        and bool(zone_uuid) and type(track_uuids) is list and 1 <= len(track_uuids) <= 4
        and len(set(track_uuids)) == len(track_uuids)
        and all(type(u) is str and bool(u) for u in track_uuids)
        and type(allow_locked_source) is bool, 'finite_explicit_terminal_shadow_context_required')
    source = Path(source).resolve()
    board = pcbnew.LoadBoard(str(source)); deadline = time.monotonic()+10.
    zones = {force._uid(z): z for z in board.Zones()}
    require(zone_uuid in zones, 'actual_source_terminal_keeper_required')
    zone = zones[zone_uuid]; config = landing._configuration(zone)
    require(config['name'] in (native.ZONE_NAME, signed.ZONE_NAME)
        and not config['rule_area'] and not config['group_uuid'] and config['priority'] == 0
        and len(config['layers']) == 1 and config['connection'] == int(pcbnew.ZONE_CONNECTION_FULL)
        and config['smoothing'] == 0 and (allow_locked_source or not config['locked'])
        and zone.IsFilled(), 'explicit_solid_registered_terminal_keeper_required')
    face = config['layers'][0]; net = config['net']
    profile = fab.get_profile(fab.board_profile_name(board)); name = fab.COPPER_LAYER_IDS.get(face)
    require(profile and name in fab.COPPER_LAYERS and net
        and net.rsplit('/', 1)[-1].upper() not in ('GND', 'AGND', 'PGND', 'DGND')
        and profile['roles'][fab.COPPER_LAYERS.index(name)] != 'GND',
        'terminal_shadow_cannot_rebuild_ground_or_an_unknown_face')
    require(zone.Outline().OutlineCount() == 1 and not zone.Outline().HoleCount(0)
        and zone.HasFilledPolysForLayer(face), 'one_simple_filled_source_terminal_keeper_required')
    kind, domain, contract = current._model(board, source, net, board_hint)
    floor = current._source_width_floor(board, source, contract, face)
    index = {force._uid(t): t for t in board.GetTracks()}
    contained = native._enclosed_native_track_ids(board, zone.Outline(), net, face, deadline)
    require(1 < len(contained) <= 128 and set(track_uuids) < contained,
        'complete_contained_native_stroke_inventory_and_surviving_bus_required')
    rows = [native._track_row(index[u]) for u in sorted(contained)]
    require(all(r['kind'] == 'PCB_TRACK' and not r['group_uuid']
        and r['width_nm'] >= floor and (allow_locked_source or not r['locked'])
        and not index[r['uuid']].HasSolderMask()
        and native._centerline_allowed(r['start_nm'], r['end_nm'], 'chamfer45') for r in rows),
        'all_retained_keeper_strokes_require_literal_full_source_current_width')
    retained = sorted(contained-set(track_uuids)); shadows = []
    via_ports = [v for v in board.GetTracks() if v.GetClass() == 'PCB_VIA'
        and v.GetNetname() == net and v.IsOnLayer(face)
        and zone.GetFilledPolysList(face).Collide(v.GetEffectiveShape(face), 0)]
    require(1 <= len(via_ports) <= 32, 'bounded_actual_terminal_barrel_ports_required')
    for uid in sorted(track_uuids):
        track = index[uid]; a, z = [tuple(p) for p in (track.GetStart(), track.GetEnd())]
        require(0 < track.GetLength() <= 2000000, 'bounded_short_terminal_stub_required')
        peers = [index[u] for u in retained]
        bases = [p for p in (a, z) if any(p in (tuple(t.GetStart()), tuple(t.GetEnd())) for t in peers)]
        require(len(bases) == 1, 'one_literal_retained_terminal_stub_base_required')
        tip = z if bases[0] == a else a
        require(not any(ports.on_centerline(t, tip) for t in peers),
            'terminal_stub_tip_is_another_retained_centerline_port')
        candidates = [v for v in via_ports if v.GetViaType() == pcbnew.VIATYPE_THROUGH
            and v.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*a), 0)
            and v.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*z), 0)]
        require(len(candidates) == 1, 'one_actual_plated_land_must_shadow_the_entire_stub_axis')
        shadows.append(dict(track_uuid=uid, via_uuid=force._uid(candidates[0]),
            base_nm=list(bases[0]), tip_nm=list(tip)))
    pieces = [Polygon(native.purposeful_envelope(native._native_capsule(index[u]),
        style='chamfer45', margin_nm=1000, grid_nm=1000)) for u in retained]
    frames = []
    for via in sorted(via_ports, key=force._uid):
        contacts = [index[u] for u in retained if tuple(via.GetPosition()) in
            (tuple(index[u].GetStart()), tuple(index[u].GetEnd()))]
        width = max([int(via.GetWidth(face))]+[int(t.GetWidth()) for t in contacts])
        points = centered.centered_cover(board, via, face, width)
        outside = native._poly(points); outside.BooleanSubtract(zone.Outline())
        require(not outside.OutlineCount(), 'existing_source_centered_barrel_frame_required')
        pieces.append(Polygon(points))
        frames.append(dict(via_uuid=force._uid(via), points_nm=points))
    merged = unary_union(pieces)
    require(merged.is_valid and merged.geom_type == 'Polygon' and not merged.interiors,
        'one_connected_unperforated_rebuilt_terminal_keeper_required')
    points = [[int(x), int(y)] for x, y in list(merged.exterior.coords)[:-1]]
    require(4 <= len(points) <= 1024 and all(x == int(x) and y == int(y)
        for x, y in list(merged.exterior.coords)) and all(native._centerline_allowed(a, z, 'chamfer45')
        for a, z in zip(points, points[1:]+points[:1])), 'literal_integer_cardinal_45_terminal_keeper_required')
    outside = native._poly(points); outside.BooleanSubtract(zone.Outline())
    require(not outside.OutlineCount(), 'terminal_shadow_rebuild_must_not_expand_the_source_owner')
    native._require_unoccupied_outline(board, native._poly(points), net, face, deadline,
        clearance_nm=config['clearance_nm'], allow_native_hole_bridges=True)
    region = dict(net=net, layer_id=face, polygon_nm=points,
        actual_fill_envelope_nm=native._fill_envelope(points, style='chamfer45', margin_nm=4),
        min_thickness_nm=config['min_thickness_nm'], priority=config['priority'],
        fill_policy=regional.CONDUCTOR_POLICY, retire_source_tracks=False, supporting_zones=[],
        replacement_source_zone=landing._native_source(zone, allow_complex_fill=True))
    region['regional_fill_binding'] = regional.source_binding(board, region, deadline)
    require(time.monotonic() < deadline, 'terminal_shadow_source_plan_deadline')
    return plain(dict(policy=POLICY, source=str(source), source_sha256=force._hash(source),
        source_family=force._family(source, board_hint),
        code_identity=force._code_identity(), authority_sha256=force._hash(Path(__file__).resolve()),
        helper_sha256={str(Path(m.__file__).resolve()): force._hash(Path(m.__file__))
            for m in (centered, material, regional, native, current, landing)},
        board_hint=board_hint, zone_uuid=zone_uuid, track_uuids=sorted(track_uuids),
        allow_locked_source=allow_locked_source, source_configuration=config,
        complete_source_tracks=rows, retained_track_uuids=retained, shadow_witnesses=shadows,
        retained_centered_frames=frames, points_nm=points, regional_contract=region,
        source_current_kind=kind, source_current_domain=domain, source_current_contract=contract,
        full_source_current_width_floor_nm=floor, current_or_barrel_qualified=False, release_authority=False))


def _arguments(proposal):
    return {k: proposal[k] for k in ('board_hint', 'zone_uuid', 'track_uuids', 'allow_locked_source')}


def discover(source, *, board_hint, allow_locked_source=False, maximum_trials=8):
    """Finite read-only geometric scheduling, not saved repair authority."""
    require(type(maximum_trials) is int and 1 <= maximum_trials <= 32
        and type(allow_locked_source) is bool, 'bounded_terminal_shadow_discovery_required')
    source = Path(source).resolve(); digest = force._hash(source); epoch = force._code_identity()
    board = pcbnew.LoadBoard(str(source)); items = list(board.GetTracks())
    require(len(items) <= 16384, 'terminal_shadow_discovery_inventory_bound')
    tracks = [t for t in items if t.GetClass() == 'PCB_TRACK']
    vias = [t for t in items if t.GetClass() == 'PCB_VIA' and t.GetViaType() == pcbnew.VIATYPE_THROUGH]
    endpoints = {}
    for t in tracks:
        for at in (tuple(t.GetStart()), tuple(t.GetEnd())):
            endpoints.setdefault((str(t.GetNetname()), int(t.GetLayer()), at), set()).add(force._uid(t))
    menus = {}; deadline = time.monotonic()+10.
    for t in tracks:
        require(time.monotonic() < deadline, 'terminal_shadow_geometric_discovery_deadline')
        if t.GetParentGroup() or t.IsLocked() and not allow_locked_source or not 0 < t.GetLength() <= 2000000:
            continue
        uid = force._uid(t); face = int(t.GetLayer()); net = str(t.GetNetname())
        ends = [tuple(t.GetStart()), tuple(t.GetEnd())]
        if sum(bool(endpoints[net, face, at]-{uid}) for at in ends) != 1:
            continue
        shadowed = [v for v in vias if v.GetNetname() == net and v.IsOnLayer(face)
            and all(v.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*at), 0) for at in ends)]
        if len(shadowed) != 1:
            continue
        keepers = []
        for zone in board.Zones():
            if (zone.GetIsRuleArea() or zone.GetNetname() != net or not zone.IsOnLayer(face)
                    or zone.GetZoneName() not in (native.ZONE_NAME, signed.ZONE_NAME)):
                continue
            outside = native._native_capsule(t); outside.BooleanSubtract(zone.Outline())
            if not outside.OutlineCount():
                keepers.append(zone)
        if len(keepers) == 1:
            menus.setdefault(force._uid(keepers[0]), []).append(uid)
    proposals = []; refusals = []
    for zone_uuid, uids in sorted(menus.items())[:maximum_trials]:
        target = dict(zone_uuid=zone_uuid, track_uuids=sorted(uids)[:4], allow_locked_source=allow_locked_source)
        try:
            proposal = plan(source, board_hint=board_hint, **target)
            proposals.append(dict(target=target, proposal=proposal))
        except (ValueError, RuntimeError, KeyError, TypeError, native.Refused) as exc:
            refusals.append(dict(target=target, reason=type(exc).__name__+':'+str(exc)))
    require(digest == force._hash(source) and epoch == force._code_identity(), 'terminal_shadow_discovery_source_or_code_changed')
    return dict(ok=True, complete=True, source=str(source), source_sha256=digest,
        code_identity=epoch, maximum_trials=maximum_trials, geometric_menus=len(menus),
        proposals=proposals, refusals=refusals, actual_geometry_constructed=False,
        finite_search_is_not_all_contours_clean_proof=True, current_or_barrel_qualified=False, release_authority=False)


def _contact_material(before, proposal):
    """Literal old contact kernels are not obsolete keeper excess."""
    face = proposal['source_configuration']['layers'][0]
    old = next(z for z in before.Zones() if force._uid(z) == proposal['zone_uuid'])
    items = [*before.GetTracks(), *(p for fp in before.GetFootprints() for p in fp.Pads())]
    require(len(items) <= 16384, 'bounded_terminal_contact_material_inventory_required')
    rows = []; deadline = time.monotonic()+10.
    for item in items:
        require(time.monotonic() < deadline, 'terminal_contact_material_deadline')
        uid = force._uid(item)
        if (uid in proposal['track_uuids'] or not item.IsOnLayer(face)
                or item.GetNetname() != old.GetNetname()
                or not old.GetFilledPolysList(face).Collide(item.GetEffectiveShape(face), 0)):
            continue
        contact = _shape(item, face); contact.BooleanIntersection(old.GetFilledPolysList(face))
        if not contact.OutlineCount():
            continue
        outside = contact.CloneDropTriangulation(); outside.BooleanSubtract(native._poly(proposal['points_nm']))
        require(not outside.OutlineCount(), 'original_terminal_contact_outside_derived_profile:'+uid)
        for row in proposal['regional_contract']['regional_fill_binding']['protected_regions']:
            region = next(z for z in before.Zones() if force._uid(z) == row['native']['uuid'])
            void = region.Outline().CloneDropTriangulation(); void.BooleanSubtract(region.GetFilledPolysList(face))
            overlap = contact.CloneDropTriangulation(); overlap.BooleanIntersection(void)
            require(not overlap.OutlineCount(), 'source_terminal_contact_has_unqualified_regional_intrusion:'+uid)
        contact.Fracture(); rows.append((uid, contact))
    return rows


def construct(source, proposal):
    require(plan(source, **_arguments(proposal)) == proposal, 'stale_or_forged_terminal_shadow_proposal')
    before, after = [pcbnew.LoadBoard(str(source)) for _ in range(2)]
    discard_items(after, [t for t in after.GetTracks() if force._uid(t) in proposal['track_uuids']])
    zone = next(z for z in after.Zones() if force._uid(z) == proposal['zone_uuid'])
    face = proposal['source_configuration']['layers'][0]
    zone.UnFill(); zone.Outline().RemoveAllContours(); zone.Outline().Append(native._poly(proposal['points_nm']))
    selected = pcbnew.ZONES(); selected.append(zone)
    fill.compile_selected(after, selected, timeout_s=10.)
    actual = regional._combine(before, zone.GetFilledPolysList(face), proposal['regional_contract'], time.monotonic()+10.)
    # Keep each real Source contact as a literal positive record. This avoids
    # native Boolean re-tessellation eroding an incumbent contact by 1 nm.
    # Every record must lie inside the independently derived new profile and
    # clear all stronger regional voids; old non-contact excess is NOT kept.
    for _, contact in _contact_material(before, proposal):
        actual.Append(contact)
    zone.UnFill(); zone.SetFilledPolysList(face, actual); zone.SetIsFilled(True)
    return after


def observe(before, after, proposal):
    face = proposal['source_configuration']['layers'][0]; deadline = time.monotonic()+10.
    old = next(z for z in before.Zones() if force._uid(z) == proposal['zone_uuid'])
    new = next(z for z in after.Zones() if force._uid(z) == proposal['zone_uuid'])
    require(landing._configuration(new) == proposal['source_configuration'], 'source_terminal_keeper_process_changed')
    require(new.IsFilled() and new.HasFilledPolysForLayer(face), 'actual_rebuilt_terminal_keeper_fill_required')
    fill_shape = new.GetFilledPolysList(face); contacts = []
    for uid, contact in _contact_material(before, proposal):
        require(time.monotonic() < deadline, 'terminal_shadow_native_contact_deadline')
        require(regional.exact_source_contour_present(fill_shape, contact, deadline),
            'literal_original_terminal_keeper_contact_material_lost:'+uid)
        contacts.append(uid)
    for uid in proposal['retained_track_uuids']:
        track = next(t for t in after.GetTracks() if force._uid(t) == uid)
        missing = native._native_capsule(track); missing.BooleanSubtract(fill_shape)
        require(not missing.OutlineCount(), 'retained_full_source_width_capsule_not_enclosed:'+uid)
    source = material.source_material(before, old.GetNetname(), face, deadline)
    candidate = material.source_material(after, old.GetNetname(), face, deadline)
    first, last = map(assembly.polygon_from_native, (source, candidate))
    removed = first.difference(last); added = last.difference(first)
    require(removed.area >= .0025, 'no_visible_native_terminal_shadow_progress')
    require(contacts, 'actual_source_terminal_keeper_contacts_required')
    return plain(dict(ok=True, complete=True, retained_native_contact_uuids=sorted(contacts),
        every_original_surviving_keeper_contact_material_preserved=True,
        every_retained_source_width_capsule_enclosed=True, removed_native_area_mm2=removed.area,
        added_native_area_mm2=added.area, removed_native_bounds_mm=list(removed.bounds),
        source_curvature=centered.curve_runs(first), candidate_curvature=centered.curve_runs(last),
        saved_trace_length_mm=sum(math.dist(r['start_nm'], r['end_nm']) for r in
            proposal['complete_source_tracks'] if r['uuid'] in proposal['track_uuids'])/1e6,
        current_or_barrel_qualified=False, release_authority=False))


def receive_literal(source, candidate, proposal):
    result = dict(ok=False, complete=False, errors=[], current_or_barrel_qualified=False,
        fresh_whole_native_current_clipped_and_reference_receiving_still_required=True, release_authority=False)
    try:
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        require(source != candidate, 'distinct_saved_terminal_shadow_candidate_required')
        epoch = force._code_identity(); families = [force._family(p, proposal['board_hint']) for p in (source, candidate)]
        before = pcbnew.LoadBoard(str(source)); after = pcbnew.LoadBoard(str(candidate))
        rebuilt = construct(source, proposal)
        with tempfile.TemporaryDirectory(prefix='cec-terminal-shadow-') as tmp:
            expected = Path(tmp)/'board.kicad_pcb'; field._save_field_snapshot(rebuilt, expected)
            require(syntax._freeze(additive._nodes(expected)[0]) == syntax._freeze(additive._nodes(candidate)[0]),
                'terminal_shadow_changed_unowned_saved_source_evidence')
        require(force._sidecars(source) == force._sidecars(candidate), 'terminal_shadow_changed_rules_or_companions')
        old, new = [additive._nodes(p)[1] for p in (source, candidate)]
        require(old.keys()-new.keys() == set(proposal['track_uuids']) and not new.keys()-old.keys(),
            'exact_source_terminal_stub_retirement_required')
        require(all(syntax._freeze(node) == syntax._freeze(new[u]) for u, node in old.items()
            if u not in set(proposal['track_uuids'])|{proposal['zone_uuid']}),
            'all_other_conductors_owners_fields_and_ground_sheets_must_remain_literal')
        prior = ordinary._partition(before, time.monotonic()+10., retired_uuids=set(proposal['track_uuids']))
        last = ordinary._partition(after, time.monotonic()+10., retained_keys=set().union(*prior))
        require(all(any(p <= q for q in last) for p in prior), 'surviving_native_terminal_partition_lost')
        progress = observe(before, after, proposal)
        require(epoch == force._code_identity() and families == [force._family(p, proposal['board_hint']) for p in (source, candidate)],
            'terminal_shadow_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(source), candidate_sha256=force._hash(candidate),
            code_identity=epoch, exact_saved_source_native_reconstruction=True,
            all_other_native_items_and_ground_sheets_literal=True, every_surviving_native_partition_preserved=True,
            retired_track_uuids=proposal['track_uuids'], modified_zone_uuids=[proposal['zone_uuid']],
            modified_nets=[proposal['source_configuration']['net']], actual_saved_progress=progress)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError, StopIteration, native.Refused) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
