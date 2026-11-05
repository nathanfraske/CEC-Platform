"""Source-typed ordinary SMD escape through a checked local native antipad.

Only the Source pad identity and a proposed barrel axis are inputs. Ordinary
electrical eligibility, full class/board dimensions and the complete short
surface leg are independently recompiled. No power/pair/Kelvin net, reduced
via floor, track crossing a power fill, Source retirement or pour-outline
change is authorized. A window prepares a port; it is not open-count progress
until the enclosing original-parent transaction actually joins the route.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_via_clearance_window as geometry
import cec_native_fill_geometry as fills
import cec_native_frozen_zone_access as frozen
import cec_native_ground_span_reflow as lease
import cec_native_partition_pair as partitions
from cec_native_items import discard_items
import cec_ordinary_route_receiving as ordinary
import cec_route_dimensions as dimensions
import cec_route_quality as quality
import cec_source_retaining_ses_import as text_io
import cec_zone_fill as native_fill


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('Source_signal_window_deadline')


def _pad(board, uid):
    pads = [p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p) == uid]
    if len(pads) != 1:
        raise ValueError('one_exact_Source_signal_land_required')
    pad = pads[0]
    face = cells.cec_return_escape.smd_surface_layer(pad)
    if (face is None or pad.HasHole() or pad.GetNetCode() <= 0
            or pad.GetParentFootprint().IsDNP()):
        raise ValueError('populated_Source_signal_SMD_land_required')
    return pad, int(face)


def _axis(value):
    if (type(value) not in (list, tuple) or len(value) != 2
            or any(type(v) is not int or abs(v) > 2000000000 for v in value)):
        raise ValueError('two_exact_integer_Source_signal_via_coordinates_required')
    return list(value)


def _install_Source_floors(board, limits):
    """Private in-memory monotone projection of the SAME saved requirements."""
    settings = board.GetDesignSettings()
    for key, name in (('track_width', 'm_TrackMinWidth'), ('via_diameter', 'm_ViasMinSize'),
            ('via_drill', 'm_MinThroughDrill'), ('annular', 'm_ViasMinAnnularWidth'),
            ('clearance', 'm_MinClearance'), ('hole_to_hole', 'm_HoleToHoleMin'),
            ('hole_clearance', 'm_HoleClearance'), ('copper_edge', 'm_CopperEdgeClearance')):
        if hasattr(settings, name):
            setattr(settings, name, max(int(getattr(settings, name)), math.ceil(limits[key]*1e6)))


def _plan_geometry(source, *, board_hint, pad_uuid, position_nm, timeout_s=10., _start_nm=None):
    """Native geometry only; never an electrical-role or routing grant.

    Separate public owners must independently derive their positive Source
    electrical scope. The ordinary owner below does not accept quiet outputs,
    and the quiet-output owner cannot supply a caller net, width or cut list.
    """
    deadline = lease._deadline(timeout_s)
    if (type(board_hint) is not str or not board_hint
            or type(pad_uuid) is not str or not pad_uuid):
        raise ValueError('explicit_Source_ordinary_signal_window_identity_required')
    point = _axis(position_nm)
    source = Path(source).resolve(strict=True)
    family, code = force._family(source, board_hint), force._code_identity()
    board = pcbnew.LoadBoard(str(source))
    pad, face = _pad(board, pad_uuid)
    net = str(pad.GetNetname())
    spec = fr._project_netclass_resolver(str(source))(net) or {}
    limits = dimensions.source_board_limits(board, source)
    _install_Source_floors(board, limits)
    compiled = dimensions.compile_spec(spec, limits=limits, role='branch')
    width, diameter, drill = [round(compiled[k]*1e6)
        for k in ('track_width', 'via_diameter', 'via_drill')]
    clearance = max(math.ceil(limits['clearance']*1e6),
        round(float(spec.get('clearance') or 0)*1e6))
    if not (0 < width < 500000 and 0 < drill < diameter <= 1000000 and clearance > 0):
        raise ValueError('bounded_full_Source_ordinary_window_dimensions_required')
    at, start = pcbnew.VECTOR2I(*point), pad.GetPosition()
    if _start_nm is not None:
        start = pcbnew.VECTOR2I(*_axis(_start_nm))
        if not fab._pad_contains_circle(pad,start,(width+1)//2,tolerance_nm=0):
            raise ValueError('Source_signal_window_start_cap_not_inside_actual_land')
    distance = math.dist(tuple(start), point)
    if (not 0 < distance <= 1500000
            or not quality.is_canonical_stroke(tuple(start), point, tolerance_nm=0)):
        raise ValueError('one_short_canonical_Source_signal_dogbone_required')
    if (not cells._hole_to_hole_clear(board, at, drill/1e6)[0]
            or not fr._edge_leg_clear(board, at, at, diameter//2+clearance,
                edge_mm=max(.5, limits['copper_edge']))):
        raise ValueError('Source_signal_window_hole_or_edge_refused')
    blocked, _ = fab.via_at_pad_conflicts(board, at, diameter, drill, pad.GetNetCode())
    if blocked is not None:
        raise ValueError('Source_signal_window_conflicts_with_an_actual_pad:'+force._uid(blocked))
    resolve = fr._foreign_clearance_resolver(board)
    circle = pcbnew.SHAPE_CIRCLE(at, diameter//2)
    for item in [*board.GetTracks(), *(p for fp in board.GetFootprints() for p in fp.Pads())]:
        _tick(deadline)
        if item.GetNetCode() == pad.GetNetCode():
            continue
        for layer in board.GetEnabledLayers().CuStack():
            if item.IsOnLayer(layer) and item.GetEffectiveShape(layer).Collide(
                    circle, max(clearance, resolve(item, layer))):
                raise ValueError('Source_signal_window_intersects_immutable_copper:'+force._uid(item))
    foreign, ground = [], []
    for zone in board.Zones():
        _tick(deadline)
        if zone.GetIsRuleArea():
            continue
        if not zone.IsFilled():
            raise ValueError('Source_signal_window_requires_complete_saved_fills')
        faces = []
        for layer in zone.GetLayerSet().CuStack():
            if not zone.HasFilledPolysForLayer(layer):
                raise ValueError('Source_signal_window_fill_face_unavailable')
            if zone.GetNetname() == 'GND':
                continue
            gap = max(clearance, int(zone.GetLocalClearance()), resolve(zone, layer))
            if zone.GetFilledPolysList(layer).Collide(circle, gap):
                if zone.GetFillMode() != pcbnew.ZONE_FILL_MODE_POLYGONS:
                    raise ValueError('Source_signal_window_requires_solid_foreign_fill')
                _, radius = geometry._window(zone, at, diameter, gap, board)
                faces.append(dict(layer=int(layer), gap_nm=gap, envelope_radius_nm=radius,
                    source_native_fill_sha256=fills.identity(zone.GetFilledPolysList(layer), deadline)[0]))
        if zone.GetNetname() == 'GND':
            ground.append(force._uid(zone))
        elif faces:
            foreign.append(dict(uuid=force._uid(zone), net=str(zone.GetNetname()), faces=faces))
    if not 1 <= len(foreign) <= 8 or not ground:
        raise ValueError('one_to_eight_actual_signal_antipads_and_Ground_planes_required')
    # A short leg may approach its own via's antipad, but may NEVER cross
    # actual Source foreign copper. Only those exact affected faces enter
    # this check; all fixed pads/tracks/holes/graphics/rule areas and every
    # other zone keep their full Source clearance. Independent native fill
    # replay below must confine ALL clearance removal to the VIA envelope,
    # including any clearance needed by this local leg. It is not a surface
    # routing corridor through a pour, nor a second track-shaped window.
    affected = {r['uuid'] for r in foreign if any(f['layer']==face for f in r['faces'])}
    segment = pcbnew.SHAPE_SEGMENT(start, at, width)
    for zone in board.Zones():
        if force._uid(zone) in affected and zone.GetFilledPolysList(face).Collide(segment, 0):
            raise ValueError('Source_signal_surface_leg_crosses_retained_foreign_copper')
    with frozen.frozen(board, source, timeout_s=min(10., max(.001, deadline-time.monotonic()))):
        zones, copper = fr._layer_foreign_shapes(board, face, {pad.GetNetCode()}, identified=True)
        retained = [r for r in zones if not (r[2].get('kind')=='zone' and r[2].get('uuid') in affected)]
        if (not fr._edge_leg_clear(board, start, at, width/2+clearance,
                    edge_mm=max(.5, limits['copper_edge']))
                or not fr._snapshot_foreign_clear(start, at, width, clearance, retained, copper)):
            raise ValueError('Source_signal_surface_leg_conflicts_with_immutable_material')
    _tick(deadline)
    if family != force._family(source, board_hint) or code != force._code_identity():
        raise ValueError('Source_signal_window_family_or_code_changed')
    result = dict(schema=1, scope='Source_signal_via_window_native_geometry_only',
        source=str(source), source_sha256=force._hash(source), source_family=family,
        script_code_identity=code, board_hint=board_hint, pad_uuid=pad_uuid, face=face, net=net,
        at_nm=point, start_nm=list(start), width_nm=width, diameter_nm=diameter,
        drill_nm=drill, clearance_nm=clearance, source_class=compiled.get('name', 'Default'),
        full_Source_board_floors_mm=limits,
        foreign_zones=foreign, ground_zone_uuids=sorted(ground),
        Source_authored_outlines_and_all_existing_conductors_immutable=True,
        current_capacity_qualified=False, all_original_parent_gates_still_required=True,
        routing_admitted=False, release_authority=False)
    _tick(deadline)
    return result


def plan(source, *, board_hint, pad_uuid, position_nm, timeout_s=10.):
    """Positively ordinary Source scope; the geometry helper grants none."""
    deadline = lease._deadline(timeout_s)
    source = Path(source).resolve(strict=True)
    family, code = force._family(source, board_hint), force._code_identity()
    board = pcbnew.LoadBoard(str(source)); pad, _ = _pad(board, pad_uuid)
    if str(pad.GetNetname()) not in ordinary.eligible_nets(board, source, board_hint):
        raise ValueError('Source_window_net_not_positively_ordinary')
    result = _plan_geometry(source, board_hint=board_hint, pad_uuid=pad_uuid,
        position_nm=position_nm, timeout_s=min(10., max(.001, deadline-time.monotonic())))
    if family != result['source_family'] or code != result['script_code_identity']:
        raise ValueError('Source_ordinary_window_role_epoch_changed')
    result['scope'] = 'Source_ordinary_signal_via_native_clearance_windows'
    _tick(deadline)
    return result


def _add(board, proposal, incoming=None):
    if incoming is not None and (type(incoming) is not dict or set(incoming) != {'via', 'segment'}
            or any(type(v) is not str or not v for v in incoming.values())
            or len(set(incoming.values())) != 2):
        raise ValueError('two_exact_new_signal_window_native_identities_required')
    via = pcbnew.PCB_VIA(board)
    edge = pcbnew.PCB_TRACK(board)
    for kind, item in (('via', via), ('segment', edge)):
        item.m_Uuid.Clone(pcbnew.KIID(incoming[kind]) if incoming else pcbnew.KIID())
        item.SetNetCode(board.GetNetcodeFromNetname(proposal['net']))
        item.SetLocked(True)
    via.SetPosition(pcbnew.VECTOR2I(*proposal['at_nm']))
    via.SetWidth(proposal['diameter_nm']); via.SetDrill(proposal['drill_nm'])
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetViaType(pcbnew.VIATYPE_THROUGH)
    edge.SetStart(pcbnew.VECTOR2I(*proposal['start_nm']))
    edge.SetEnd(via.GetPosition()); edge.SetWidth(proposal['width_nm']); edge.SetLayer(proposal['face'])
    board.Add(via); board.Add(edge)
    return via, edge


def _source_clipped_native_fill(before, compiled, window, deadline):
    """Native intersection is construction, NEVER a zero-spill tolerance.

    A new antipad can re-tessellate an adjacent existing clearance edge.
    Keep only compiled copper already present in Source. The result STILL
    must pass the unchanged strict zero-spill/only-local-subtraction proof.
    No removed Source copper is restored or outside-window loss discarded.
    """
    _tick(deadline)
    raw_id = fills.identity(compiled, deadline)[0]
    constrained = compiled.CloneDropTriangulation()
    constrained.BooleanIntersection(before)
    # Use native hole-bridge serialization BEFORE the exact proofs. A raw
    # hole-bearing Boolean shape is not the literal saved positive records.
    constrained.Fracture()
    from cec_native_local_subtractive_clip import refine
    constrained, integer_construction = refine(before, compiled, constrained, window, deadline=deadline)
    proof = geometry._local_subtraction(before, constrained, window, deadline)
    lost = before.CloneDropTriangulation(); lost.BooleanSubtract(constrained)
    # An additional literal-integer containment proof. A subsequent Boolean
    # can quantize a sub-nanometre triangle to empty; that is not a witness
    # that its original vertices were inside this axis-aligned VIA window.
    bounds = window.BBox()
    for index in range(lost.OutlineCount()):
        for ring in [lost.Outline(index), *[lost.Hole(index, j) for j in range(lost.HoleCount(index))]]:
            for n in range(ring.PointCount()):
                _tick(deadline); point = ring.CPoint(n)
                if not (bounds.GetX() <= point.x <= bounds.GetRight()
                        and bounds.GetY() <= point.y <= bounds.GetBottom()):
                    raise ValueError('signal_window_literal_loss_outside_Source_via_envelope')
    proof.update(compiled_native_fill_sha256=raw_id,
        constrained_native_fill_sha256=fills.identity(constrained, deadline)[0],
        integer_subtractive_construction=integer_construction,
        Source_intersection_is_construction_not_a_spill_tolerance=True,
        literal_integer_loss_vertices_inside_via_window=True)
    return constrained, proof


def _reinstall_native_faces(zone, replacements, deadline, *, source_zone):
    """Preserve actual native component markers, not stale polygon indices."""
    faces = {}
    for layer in zone.GetLayerSet().CuStack():
        _tick(deadline)
        old = zone.GetFilledPolysList(layer).CloneDropTriangulation()
        new = replacements.get(int(layer), old)
        if old.OutlineCount() > 256 or new.OutlineCount() > 256:
            raise ValueError('signal_window_native_component_inventory_bound')
        def records(owner, shape):
            result = []
            for index in range(shape.OutlineCount()):
                _tick(deadline)
                part = shape.CloneDropTriangulation()
                for other in reversed(range(shape.OutlineCount())):
                    if other != index: part.RemoveOutline(other)
                result.append((part, bool(owner.IsIsland(layer, index))))
            return result
        originals = records(zone, old)
        source = records(source_zone, source_zone.GetFilledPolysList(layer))
        if len(source) > 256 or new.OutlineCount() != len(originals):
            raise ValueError('signal_window_component_split_requires_independent_native_anchor_owner')
        ordered = []
        used = set()
        for index in range(new.OutlineCount()):
            _tick(deadline)
            part = new.CloneDropTriangulation()
            for other in reversed(range(new.OutlineCount())):
                if other != index: part.RemoveOutline(other)
            matches = [(i, flag) for i, (shape, flag) in enumerate(originals) if part.Collide(shape, 0)]
            Source_matches = [flag for shape, flag in source if part.Collide(shape, 0)]
            if len(matches) != 1 or matches[0][0] in used or len(Source_matches) != 1:
                raise ValueError('signal_window_ambiguous_compiled_native_component_marker')
            used.add(matches[0][0])
            # A Source island cannot gain a power anchor from adding a
            # FOREIGN signal barrel. Never promote that inherited marker.
            ordered.append((matches[0][0], part, matches[0][1] or Source_matches[0]))
        # Restore the COMPILED ordering too: do not depend on UnFill's
        # handling of an old island-index cache. Every True index remains
        # attached to that same actual component. Only conservative new
        # Source-island=True markers may be added; none must be cleared.
        rebuilt = pcbnew.SHAPE_POLY_SET(); flags = []
        for _, part, flag in sorted(ordered, key=lambda row: row[0]):
            rebuilt.Append(part); flags.append(flag)
        faces[int(layer)] = (rebuilt, flags)
    zone.UnFill()
    for layer, (shape, flags) in faces.items():
        zone.SetFilledPolysList(layer, shape)
        for index, flag in enumerate(flags):
            if flag: zone.SetIsIsland(layer, index)
    zone.SetIsFilled(True)
    _tick(deadline)


def _construct_fresh(proposal, incoming, deadline):
    board, original = [pcbnew.LoadBoard(proposal['source']) for _ in range(2)]
    _install_Source_floors(board, proposal['full_Source_board_floors_mm'])
    via, edge = _add(board, proposal, incoming)
    # These windows always retain the FULL ordinary Source via dimensions.
    # Do not misclassify an off-pad normal barrel as a reduced local-POFV
    # exception with a pad-centre reach requirement. Actual pad overlap STILL
    # requires the unchanged qualified local process; every barrel also takes
    # the complete native new-hole/process guard after independent refill.
    spec = fr._project_netclass_resolver(proposal['source'])(proposal['net']) or {}
    normal = dimensions.ordinary_via_geometry(spec,proposal['full_Source_board_floors_mm'],
        requested=(via.GetWidth()/1e6,via.GetDrillValue()/1e6))
    if tuple(round(v*1e6) for v in normal) != (proposal['diameter_nm'],proposal['drill_nm']):
        raise ValueError('Source_signal_window_actual_full_normal_dimensions_required')
    blocked, overlaps = fab.via_at_pad_conflicts(board,via.GetPosition(),proposal['diameter_nm'],
        proposal['drill_nm'],via.GetNetCode())
    if blocked is not None:
        raise ValueError('Source_signal_window_actual_pad_process_refused')
    if overlaps:
        process = fab.local_pofv_via_decision(board, via)
        if not process[0]:
            raise ValueError('Source_signal_window_actual_local_process_refused:'+process[1])
    ids = set(proposal['ground_zone_uuids']) | {r['uuid'] for r in proposal['foreign_zones']}
    selected = pcbnew.ZONES()
    for zone in board.Zones():
        if force._uid(zone) in ids:
            zone.UnFill(); selected.append(zone)
    native = native_fill.compile_selected(board, selected,
        timeout_s=min(10., max(.001, deadline-time.monotonic())), initialize_selected=True)
    before, after = [{force._uid(z): z for z in b.Zones()} for b in (original, board)]
    proofs = []
    for record in proposal['foreign_zones']:
        left, right = before[record['uuid']], after[record['uuid']]
        selected_faces = {f['layer'] for f in record['faces']}
        replacements = {}
        for layer in left.GetLayerSet().CuStack():
            if int(layer) not in selected_faces and fills.identity(
                    left.GetFilledPolysList(layer), deadline) != fills.identity(
                    right.GetFilledPolysList(layer), deadline):
                raise ValueError('signal_window_changed_an_unselected_foreign_face')
        for face in record['faces']:
            region, radius = geometry._window(left, via.GetPosition(), proposal['diameter_nm'],
                face['gap_nm'], original)
            if radius != face['envelope_radius_nm']:
                raise ValueError('Source_signal_window_native_envelope_changed')
            constrained, proof = _source_clipped_native_fill(left.GetFilledPolysList(face['layer']),
                right.GetFilledPolysList(face['layer']), region, deadline)
            replacements[face['layer']] = constrained
            proofs.append(dict(zone_uuid=record['uuid'], layer=face['layer'], **proof))
        _reinstall_native_faces(right, replacements, deadline, source_zone=left)
    with tempfile.TemporaryDirectory(prefix='cec-signal-window-geometry-') as work:
        snapshot = Path(work)/'board.kicad_pcb'
        field._save_field_snapshot(board, snapshot)
        probe = pcbnew.LoadBoard(str(snapshot)); probe.SetFileName(proposal['source'])
        _install_Source_floors(probe, proposal['full_Source_board_floors_mm'])
        # A NEW-hole check, not an existing-via exemption. The independently
        # compiled fills remain, but the emitted via is absent from this clone.
        discard_items(probe, [t for t in probe.GetTracks() if force._uid(t) == force._uid(via)])
        with frozen.frozen(probe, snapshot,
                timeout_s=min(10., max(.001, deadline-time.monotonic()))):
            report = {}
            if not fr._via_spot_clear(probe, via.GetPosition(), proposal['diameter_nm'],
                    proposal['clearance_nm'], {via.GetNetCode()}, drill_nm=proposal['drill_nm'],
                    net_code=via.GetNetCode(), report=report):
                raise ValueError('native_signal_window_all_face_via_geometry_refused:'+str(report))
            if not fr._tap_foreign_clear(probe, edge.GetStart(), edge.GetEnd(), proposal['width_nm'],
                    proposal['face'], proposal['clearance_nm'], {edge.GetNetCode()}):
                raise ValueError('native_signal_window_surface_leg_geometry_refused')
    _tick(deadline)
    return board, dict(native_fill=native, local_foreign_subtractions=proofs,
        ordinary_full_Source_via_dimensions_verified=True,
        actual_pad_overlap_local_pofv_process_used=bool(overlaps),
        all_face_native_new_hole_geometry_received=True,
        surface_leg_does_not_cross_Source_foreign_copper=True,
        surface_clearance_changes_confined_to_via_window=True,
        full_Source_ordinary_class_dimensions=True, current_capacity_qualified=False)


def write_private(proposal, directory, *, timeout_s=10.):
    deadline = lease._deadline(timeout_s)
    fresh = plan(proposal['source'], board_hint=proposal['board_hint'], pad_uuid=proposal['pad_uuid'],
        position_nm=proposal['at_nm'], timeout_s=min(10., max(.001, deadline-time.monotonic())))
    if fresh != proposal:
        raise ValueError('fresh_exact_Source_signal_window_proposal_required')
    board, proof = _construct_fresh(fresh, None, deadline)
    target = force._copy_family(Path(fresh['source']), Path(directory))
    text_io.write_raw(target, geometry._literal_text(Path(fresh['source']), board, fresh))
    if (fresh['script_code_identity'] != force._code_identity()
            or fresh['source_family'] != force._family(Path(fresh['source']), fresh['board_hint'])):
        raise ValueError('Source_signal_window_changed_before_private_save')
    result = dict(candidate=str(target), candidate_sha256=force._hash(target), construction=proof,
        complete=True, routing_admitted=False, current_capacity_qualified=False,
        all_original_parent_gates_still_required=True, release_authority=False)
    _tick(deadline)
    return result


def receive(source, candidate, *, board_hint, pad_uuid, position_nm, timeout_s=10.):
    result = dict(ok=False, complete=False, errors=[], scope_only=True,
        routing_admitted=False, current_capacity_qualified=False, release_authority=False,
        all_original_parent_gates_still_required=True)
    try:
        deadline = lease._deadline(timeout_s)
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_signal_window_boundaries_required')
        epoch = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        fresh = plan(source, board_hint=board_hint, pad_uuid=pad_uuid, position_nm=position_nm,
            timeout_s=min(10., max(.001, deadline-time.monotonic())))
        _, old = additive._nodes(source)
        new_root, new = additive._nodes(candidate)
        incoming = new.keys()-old.keys()
        kinds = {new[u][0] for u in incoming}
        if old.keys()-new.keys() or len(incoming) != 2 or kinds != {'via', 'segment'}:
            raise ValueError('one_new_signal_via_and_leg_without_retirement_required')
        ids = {new[u][0]: u for u in incoming}
        projected, proof = _construct_fresh(fresh, ids, deadline)
        with tempfile.TemporaryDirectory(prefix='cec-signal-window-independent-') as work:
            expected = force._copy_family(source, Path(work)/'expected')
            text_io.write_raw(expected, geometry._literal_text(source, projected, fresh))
            expected_root = additive._nodes(expected)[0]
        if (syntax._freeze(expected_root) != syntax._freeze(new_root)
                or force._sidecars(source) != force._sidecars(candidate)):
            raise ValueError('saved_signal_window_differs_from_complete_independent_Source_replay')
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        paired = partitions.compare(parent, child,
            timeout_s=min(10., max(.001, deadline-time.monotonic())))
        if paired.get('available') is not True or paired.get('preserved') is not True:
            raise ValueError('Source_signal_window_demoted_a_retained_native_partition')
        pad, _ = _pad(child, pad_uuid)
        graph = fr._read_only_route_connectivity(child)
        reached = {force._uid(pad)} | {force._uid(i) for i in graph.GetConnectedItems(pad)}
        if not incoming <= reached:
            raise ValueError('new_signal_window_material_not_attached_to_exact_Source_land')
        if (epoch != force._code_identity()
                or families != [force._family(p, board_hint) for p in (source, candidate)]):
            raise ValueError('Source_signal_window_saved_families_or_code_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate), plan=fresh, construction=proof,
            all_original_authored_items_unchanged=True, original_native_partitions_preserved=True,
            exact_native_Source_reconstruction_received=True,
            only_Source_bounded_foreign_clearance_removal=True,
            window_is_not_itself_an_open_count_progress_claim=True)
        _tick(deadline)
    except Exception as exc:
        result.update(ok=False, complete=False)
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
