"""Checked local reference-return field under an existing Source pair group.

This separate owner never borrows ordinary Ground's current-carrying role.
It requires an already independently validated Source local-pair-return group,
uses only that group's existing same-drill geometry menu, and re-proves each
new member's paired-transition role after native fill. One or two antipads
form an atomic field: exact Source-derived windows, not a larger corridor.
All whole-board current/field/factory/original-parent gates remain mandatory.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as syntax
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_shortcut as returns
import cec_ground_via_clearance_window as geometry
import cec_native_fill_geometry as fills
import cec_native_frozen_zone_access as frozen
import cec_native_ground_span_reflow as lease
from cec_native_items import discard_items
import cec_native_partition_pair as partitions
import cec_pair_reference_clearance_window as ordinary_reference
import cec_pth_pair_returns as ground
import cec_signal_via_clearance_window as signal
import cec_source_retaining_ses_import as text_io
import cec_zone_fill as native_fill


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('Source_pair_return_field_deadline')


def _Source_geometry(board, source, selection):
    groups = [g for g in board.Groups() if g.GetName() == fr.LOCAL_PAIR_RETURN_VIA_GROUP]
    if len(groups) != 1:
        raise ValueError('one_existing_Source_local_pair_return_group_required')
    valid = constraints._validated_local_pair_return_uuids(board, str(source), {})
    owned = [v for v in groups[0].GetItems() if force._uid(v) in valid]
    geometries = {(int(v.GetWidth(v.TopLayer())), int(v.GetDrillValue())) for v in owned}
    # A previous minimum-land construction must not make the next field
    # ambiguous. Same-bore Source lands form the same already-supported
    # bounded menu; retain the widest actual Source land as its preference.
    # Different existing drills do require a separate positive owner, never
    # an unrecorded choice of a conveniently smaller bore.
    if not owned or len({drill for _,drill in geometries}) != 1:
        raise ValueError('one_independently_validated_Source_local_pair_drill_required')
    preferred = max(geometries)
    menu = fab.pair_return_via_geometry_candidates(board, *(v/1e6 for v in preferred))
    choices = [r for r in menu if r['selection'] == selection]
    if len(choices) != 1:
        raise ValueError('one_existing_Source_local_pair_geometry_menu_selection_required')
    contract = ground.ground_return_contract(board)
    diameter, drill = [round(choices[0][k]*1e6) for k in ('diameter_mm', 'drill_mm')]
    rule, fabrication, limits = [contract[k] for k in
        ('conservative_rule_minima_mm', 'fabrication_minima_mm', 'board_limits_mm')]
    minimum_diameter = math.ceil(max(limits['via_diameter'], fabrication['via'], rule['via_diameter'])*1e6)
    minimum_drill = math.ceil(max(limits['via_drill'], fabrication['drill'], rule['via_drill'])*1e6)
    minimum_annular = math.ceil(max(limits['annular'], fabrication['annular'], rule['annular'])*1e6)
    if diameter < minimum_diameter or drill < minimum_drill or diameter-drill < 2*minimum_annular:
        raise ValueError('Source_local_pair_geometry_below_board_fabrication_or_saved_rule_floor')
    if not 0 < drill < diameter <= 1000000:
        raise ValueError('bounded_Source_local_reference_barrel_geometry_required')
    return dict(existing_group_uuid=force._uid(groups[0]),
        qualified_Source_member_uuids=sorted(force._uid(v) for v in owned),
        Source_preferred_geometry_nm=list(preferred), selected_geometry=choices[0],
        diameter_nm=diameter, drill_nm=drill,
        clearance_nm=max(contract['clearance_nm'],
            contract['spacing_nm']['hole_clearance']-(diameter-drill)//2),
        spacing_and_process_authority=contract,
        ordinary_Ground_class_not_changed=True,
        scope='existing_Source_group_local_paired_reference_not_rated_current_transfer')


def plan(source, *, board_hint, pair_name, signal_via_uuids, positions_nm,
         geometry_selection='preferred', timeout_s=10.):
    deadline = lease._deadline(timeout_s)
    if type(board_hint) is not str or not board_hint:
        raise ValueError('explicit_Source_pair_return_field_board_identity_required')
    if type(positions_nm) not in (list, tuple) or not 1 <= len(positions_nm) <= 2:
        raise ValueError('one_or_two_exact_Source_local_return_seats_required')
    points = sorted([signal._axis(p) for p in positions_nm])
    if len(set(map(tuple, points))) != len(points):
        raise ValueError('distinct_Source_local_return_seats_required')
    source = Path(source).resolve(strict=True)
    family, code = force._family(source, board_hint), force._code_identity()
    board = pcbnew.LoadBoard(str(source))
    pair, vias = ordinary_reference._transition(board, source, pair_name, signal_via_uuids)
    authority = _Source_geometry(board, source, geometry_selection)
    diameter, drill, clearance = [authority[k] for k in ('diameter_nm', 'drill_nm', 'clearance_nm')]
    missing = {force._uid(v) for v in vias if not ordinary_reference._covered(board, v)}
    reached = [{force._uid(v) for v in vias if math.dist(point, tuple(v.GetPosition())) <= 1500000}
               for point in points]
    if not missing or any(not (row & missing) for row in reached) or not missing <= set().union(*reached):
        raise ValueError('Source_field_must_cover_all_missing_members_without_unrelated_seats')
    resolve = fr._foreign_clearance_resolver(board)
    records, reference = {}, []
    for index, point in enumerate(points):
        _tick(deadline); at = pcbnew.VECTOR2I(*point)
        report = ground.ground_site_guard(board, at, diameter, drill,
            authority['spacing_and_process_authority'], deadline=deadline)
        if not report['ok']:
            raise ValueError('Source_local_pair_field_'+report['reason'])
        blocked, overlaps = fab.via_at_pad_conflicts(board, at, diameter, drill, board.GetNetcodeFromNetname('GND'))
        if blocked is not None or overlaps:
            raise ValueError('Source_local_pair_return_seat_must_be_outside_actual_lands')
        circle = pcbnew.SHAPE_CIRCLE(at, (diameter+1)//2)
        for item in [*board.GetTracks(), *(p for fp in board.GetFootprints() for p in fp.Pads())]:
            _tick(deadline)
            if item.GetNetname() == 'GND':
                continue
            for layer in board.GetEnabledLayers().CuStack():
                if item.IsOnLayer(layer) and item.GetEffectiveShape(layer).Collide(
                        circle, max(clearance, resolve(item, layer))):
                    raise ValueError('Source_local_pair_field_intersects_immutable_copper:'+force._uid(item))
        for zone in board.Zones():
            _tick(deadline)
            if zone.GetIsRuleArea():
                continue
            if not zone.IsFilled():
                raise ValueError('Source_local_pair_field_requires_complete_saved_fills')
            uid = force._uid(zone)
            if zone.GetNetname() == 'GND':
                if uid not in reference: reference.append(uid)
                continue
            for layer in zone.GetLayerSet().CuStack():
                if not zone.HasFilledPolysForLayer(layer):
                    raise ValueError('Source_local_pair_field_native_face_unavailable')
                gap = max(clearance, int(zone.GetLocalClearance()), resolve(zone, layer))
                if not zone.GetFilledPolysList(layer).Collide(circle, gap):
                    continue
                if zone.GetFillMode() != pcbnew.ZONE_FILL_MODE_POLYGONS:
                    raise ValueError('Source_local_pair_field_solid_foreign_fill_required')
                _, radius = geometry._window(zone, at, diameter, gap, board)
                record = records.setdefault(uid, dict(uuid=uid, net=str(zone.GetNetname()), faces=[]))
                record['faces'].append(dict(layer=int(layer), seat=index, gap_nm=gap,
                    envelope_radius_nm=radius,
                    source_native_fill_sha256=fills.identity(zone.GetFilledPolysList(layer), deadline)[0]))
    if not 1 <= len(records) <= 8 or not reference:
        raise ValueError('bounded_actual_local_pair_antipads_and_Ground_planes_required')
    if family != force._family(source, board_hint) or code != force._code_identity():
        raise ValueError('Source_local_pair_field_family_or_code_changed')
    result = dict(schema=1, scope='Source_existing_local_pair_return_field_native_windows',
        source=str(source), source_sha256=force._hash(source), source_family=family,
        script_code_identity=code, board_hint=board_hint, pair_name=pair_name,
        pair_nets=[pair['p'], pair['n']], signal_via_uuids=sorted(signal_via_uuids),
        Source_missing_return_uuids=sorted(missing), positions_nm=points,
        geometry_selection=geometry_selection, local_reference_authority=authority,
        foreign_zones=[records[u] for u in sorted(records)], ground_zone_uuids=sorted(reference),
        all_original_parent_gates_still_required=True, current_capacity_qualified=False,
        routing_admitted=False, release_authority=False)
    _tick(deadline)
    return result


def _clip_field_face(before, compiled, boxes, deadline):
    """A bounding rectangle is construction space, NEVER removal authority."""
    union = pcbnew.SHAPE_POLY_SET()
    for a,b,c,d in boxes:
        shape = pcbnew.SHAPE_POLY_SET(); shape.NewOutline()
        for x,y in ((a,b),(c,b),(c,d),(a,d)): shape.Append(x,y)
        union.BooleanAdd(shape)
    bounds = union.BBox(); rectangle = pcbnew.SHAPE_POLY_SET(); rectangle.NewOutline()
    for x,y in ((bounds.GetX(),bounds.GetY()),(bounds.GetRight(),bounds.GetY()),
                (bounds.GetRight(),bounds.GetBottom()),(bounds.GetX(),bounds.GetBottom())):
        rectangle.Append(x,y)
    candidate, construction = signal._source_clipped_native_fill(before, compiled, rectangle, deadline)
    proof = geometry._local_subtraction(before, candidate, union, deadline)
    lost = before.CloneDropTriangulation(); lost.BooleanSubtract(candidate)
    for index in range(lost.OutlineCount()):
        for ring in [lost.Outline(index), *[lost.Hole(index,j) for j in range(lost.HoleCount(index))]]:
            for n in range(ring.PointCount()):
                _tick(deadline); point = ring.CPoint(n)
                if not any(a <= point.x <= c and b <= point.y <= d for a,b,c,d in boxes):
                    raise ValueError('local_pair_literal_loss_outside_exact_Source_window_union')
    return candidate, dict(proof, authorized_mask_is_exact_Source_windows_not_bbox=True,
        exact_Source_window_boxes_nm=boxes, integer_construction=construction['integer_subtractive_construction'])


def _construct_fresh(proposal, incoming_uuids, deadline):
    board, original = [pcbnew.LoadBoard(proposal['source']) for _ in range(2)]
    authority = proposal['local_reference_authority']; diameter, drill = authority['diameter_nm'], authority['drill_nm']
    if incoming_uuids is not None and (type(incoming_uuids) not in (list,tuple)
            or len(incoming_uuids) != len(proposal['positions_nm'])
            or any(type(u) is not str or not u for u in incoming_uuids)
            or len(set(incoming_uuids)) != len(incoming_uuids)):
        raise ValueError('exact_distinct_new_local_field_barrel_identities_required')
    vias = []
    for index, point in enumerate(proposal['positions_nm']):
        via = pcbnew.PCB_VIA(board)
        via.m_Uuid.Clone(pcbnew.KIID(incoming_uuids[index]) if incoming_uuids else pcbnew.KIID())
        via.SetPosition(pcbnew.VECTOR2I(*point)); via.SetWidth(diameter); via.SetDrill(drill)
        via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetNet(board.FindNet('GND')); via.SetLocked(True); board.Add(via); vias.append(via)
    fr.group_local_pair_return_vias(board,vias)
    ids = set(proposal['ground_zone_uuids']) | {r['uuid'] for r in proposal['foreign_zones']}
    selected = pcbnew.ZONES()
    for zone in board.Zones():
        if force._uid(zone) in ids: zone.UnFill(); selected.append(zone)
    native = native_fill.compile_selected(board,selected,
        timeout_s=min(10.,max(.001,deadline-time.monotonic())),initialize_selected=True)
    before, after = [{force._uid(z):z for z in b.Zones()} for b in (original,board)]
    proofs = []
    for record in proposal['foreign_zones']:
        left,right = before[record['uuid']],after[record['uuid']]; by_face = {}
        for face in record['faces']: by_face.setdefault(face['layer'],[]).append(face)
        replacements = {}
        for layer in left.GetLayerSet().CuStack():
            if int(layer) not in by_face and fills.identity(left.GetFilledPolysList(layer),deadline) != fills.identity(right.GetFilledPolysList(layer),deadline):
                raise ValueError('local_pair_field_changed_unselected_foreign_face')
        for face, rows in sorted(by_face.items()):
            boxes = []
            for row in rows:
                at = pcbnew.VECTOR2I(*proposal['positions_nm'][row['seat']])
                window,radius = geometry._window(left,at,diameter,row['gap_nm'],original)
                if radius != row['envelope_radius_nm']:
                    raise ValueError('local_pair_Source_window_envelope_changed')
                box = window.BBox(); boxes.append([box.GetX(),box.GetY(),box.GetRight(),box.GetBottom()])
            candidate,proof = _clip_field_face(left.GetFilledPolysList(face),right.GetFilledPolysList(face),boxes,deadline)
            replacements[face] = candidate; proofs.append(dict(zone_uuid=record['uuid'],layer=face,**proof))
        signal._reinstall_native_faces(right,replacements,deadline,source_zone=left)
    contacts = [returns._reference_contacts(board,via) for via in vias]
    valid = constraints._validated_local_pair_return_uuids(board,proposal['source'],{})
    if not {force._uid(v) for v in vias} <= valid:
        raise ValueError('every_new_local_field_member_must_independently_qualify')
    with tempfile.TemporaryDirectory(prefix='cec-local-pair-field-new-hole-') as work:
        snapshot = Path(work)/'board.kicad_pcb'; field._save_field_snapshot(board,snapshot)
        for via in vias:
            _tick(deadline); probe = pcbnew.LoadBoard(str(snapshot)); probe.SetFileName(proposal['source'])
            discard_items(probe,[t for t in probe.GetTracks() if force._uid(t)==force._uid(via)])
            report = ground.ground_site_guard(probe,via.GetPosition(),diameter,drill,
                authority['spacing_and_process_authority'],deadline=deadline)
            if not report['ok']: raise ValueError('new_local_pair_field_'+report['reason'])
            with frozen.frozen(probe,snapshot,timeout_s=min(10.,max(.001,deadline-time.monotonic()))):
                evidence = {}
                if not fr._via_spot_clear(probe,via.GetPosition(),diameter,authority['clearance_nm'],
                        {via.GetNetCode()},drill_nm=drill,net_code=via.GetNetCode(),report=evidence):
                    raise ValueError('new_local_pair_field_all_face_geometry_refused:'+str(evidence))
    _tick(deadline)
    return board, dict(native_fill=native, local_foreign_subtractions=proofs,
        actual_contacts_to_every_Ground_reference=contacts,
        independently_qualified_new_local_return_uuids=sorted(force._uid(v) for v in vias),
        ordinary_Ground_current_geometry_unchanged=True, all_face_native_new_hole_geometry_received=True,
        native_open_progress_claimed=False, current_capacity_qualified=False)


def _fresh(proposal,deadline):
    fresh = plan(proposal['source'],board_hint=proposal['board_hint'],pair_name=proposal['pair_name'],
        signal_via_uuids=proposal['signal_via_uuids'],positions_nm=proposal['positions_nm'],
        geometry_selection=proposal['geometry_selection'],timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if fresh != proposal: raise ValueError('fresh_exact_Source_local_pair_field_proposal_required')
    return fresh


def write_private(proposal,directory,*,timeout_s=10.):
    deadline = lease._deadline(timeout_s); fresh = _fresh(proposal,deadline)
    board,proof = _construct_fresh(fresh,None,deadline)
    target = force._copy_family(Path(fresh['source']),Path(directory))
    text_io.write_raw(target,geometry._literal_text(Path(fresh['source']),board,fresh))
    if fresh['script_code_identity'] != force._code_identity() or fresh['source_family'] != force._family(Path(fresh['source']),fresh['board_hint']):
        raise ValueError('Source_local_pair_field_changed_before_private_save')
    result = dict(complete=True,candidate=str(target),candidate_sha256=force._hash(target),construction=proof,
        routing_admitted=False,current_capacity_qualified=False,all_original_parent_gates_still_required=True,release_authority=False)
    _tick(deadline); return result


def receive(source,candidate,*,board_hint,pair_name,signal_via_uuids,positions_nm,
            geometry_selection='preferred',timeout_s=10.):
    result = dict(ok=False,complete=False,errors=[],scope_only=True,routing_admitted=False,
        current_capacity_qualified=False,all_original_parent_gates_still_required=True,release_authority=False)
    try:
        deadline = lease._deadline(timeout_s); source,candidate = [Path(p).resolve(strict=True) for p in (source,candidate)]
        if source==candidate: raise ValueError('distinct_saved_local_pair_field_boundaries_required')
        epoch = force._code_identity(); families = [force._family(p,board_hint) for p in (source,candidate)]
        fresh = plan(source,board_hint=board_hint,pair_name=pair_name,signal_via_uuids=signal_via_uuids,
            positions_nm=positions_nm,geometry_selection=geometry_selection,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        _,old = additive._nodes(source); new_root,new = additive._nodes(candidate); incoming = new.keys()-old.keys()
        if old.keys()-new.keys() or len(incoming)!=len(fresh['positions_nm']) or any(new[u][0]!='via' for u in incoming):
            raise ValueError('exact_new_local_pair_barrels_without_retirement_required')
        child = pcbnew.LoadBoard(str(candidate)); vias = [v for v in child.GetTracks() if force._uid(v) in incoming]
        if sorted(tuple(v.GetPosition()) for v in vias) != list(map(tuple,fresh['positions_nm'])):
            raise ValueError('saved_local_pair_field_seats_changed')
        ids = [force._uid(v) for v in sorted(vias,key=lambda v:tuple(v.GetPosition()))]
        projected,proof = _construct_fresh(fresh,ids,deadline)
        with tempfile.TemporaryDirectory(prefix='cec-local-pair-field-independent-') as work:
            expected = force._copy_family(source,Path(work)/'expected')
            text_io.write_raw(expected,geometry._literal_text(source,projected,fresh)); expected_root = additive._nodes(expected)[0]
        if syntax._freeze(expected_root)!=syntax._freeze(new_root) or force._sidecars(source)!=force._sidecars(candidate):
            raise ValueError('saved_local_pair_field_differs_from_independent_Source_replay')
        parent = pcbnew.LoadBoard(str(source)); paired = partitions.compare(parent,child,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if paired.get('available') is not True or paired.get('preserved') is not True:
            raise ValueError('local_pair_field_demoted_a_Source_native_partition')
        left = {frozenset(p) for p in paired['source_parts']}; keys = set().union(*left)
        right = {frozenset(k for k in p if k in keys) for p in paired['child_parts']}; right.discard(frozenset())
        if left!=right: raise ValueError('local_pair_field_cannot_merge_Source_native_partitions')
        _,signal_vias = ordinary_reference._transition(child,candidate,pair_name,signal_via_uuids)
        if not all(ordinary_reference._covered(child,v) for v in signal_vias):
            raise ValueError('saved_complete_local_pair_return_field_required')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('Source_local_pair_field_saved_epoch_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            construction=proof,every_Source_native_partition_identical=True,complete_local_return_field_received=True,
            native_open_progress_claimed=False)
        _tick(deadline)
    except Exception as exc:
        result.update(ok=False,complete=False); result['errors'].append(str(exc))
    return result
