"""Retire a bounded Source-class surface Ground link, never a power mesh.

Both actual endpoint lands must already have independent, short, process-
qualified returns contacting every declared Ground plane. Exact subtraction
must preserve every native partition and every known local Ground return.
This is preparatory copper retirement, not open, ampacity, PI, shielding,
Kelvin, inherited-debt, fabrication or release qualification. The historical
small Ground-span and dead-end operators retain their narrower contracts.
"""
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as binding
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_preservation as returns
import cec_ground_return_shortcut as reference
import cec_native_ground_span_reflow as chain
import cec_native_partition_pair as partitions
import cec_route_quality as quality
import cec_source_class_ground_dead_end_tail as source_class
import cec_source_literal_retirement as literal
import cec_source_retaining_ses_import as raw
from cec_native_items import discard_items


PHASES = ('Source_identity_and_proposal', 'independent_saved_delta',
          'actual_saved_partitions_and_local_returns',
          'all_Source_returns_fields_craft_and_identity')


def _deadline(seconds):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0 < seconds <= 10):
        raise ValueError('bounded_redundant_Source_Ground_link_lease_required')
    return time.monotonic() + seconds


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('redundant_Source_Ground_link_deadline')


def _remaining(deadline):
    _tick(deadline)
    return min(10., deadline - time.monotonic())


def _ids(values):
    if (type(values) not in (list, tuple) or not 1 <= len(values) <= 8
            or any(type(v) is not str or not v for v in values)
            or len(set(values)) != len(values)):
        raise ValueError('bounded_explicit_Source_Ground_track_scope_required')
    return sorted(values)


def _poly(item, face, *, outside):
    shape = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(shape, face, 0, 1,
        pcbnew.ERROR_OUTSIDE if outside else pcbnew.ERROR_INSIDE)
    if not shape.OutlineCount():
        raise ValueError('actual_native_Ground_link_copper_polygon_required')
    return shape


def _context(board, source, ids, deadline):
    authority = source_class._authority(board, source, 'GND')
    tracks = list(board.GetTracks())
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(tracks) + len(pads) + len(zones) > 16384:
        raise ValueError('Source_Ground_link_native_inventory_bound')
    chosen = [t for t in tracks if force._uid(t) in ids]
    if len(chosen) != len(ids) or {force._uid(t) for t in chosen} != set(ids):
        raise ValueError('unique_actual_Source_Ground_track_scope_required')
    width = authority['width_nm']
    face = int(chosen[0].GetLayer())
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    if (not 0 < width <= 1000000 or face not in (pcbnew.F_Cu, pcbnew.B_Cu)
            or any(t.GetClass() != 'PCB_TRACK' or t.GetNetname() != 'GND'
                or t.GetNetCode() <= 0 or int(t.GetLayer()) != face
                or t.GetWidth() != width or t.IsLocked() or t.HasSolderMask()
                or t.GetParentGroup() or force._uid(t) in grouped
                or t.GetLength() <= 0 or not quality.is_canonical_stroke(
                    tuple(t.GetStart()), tuple(t.GetEnd()), tolerance_nm=0)
                for t in chosen)):
        raise ValueError('plain_unlocked_ungrouped_exact_Source_class_surface_Ground_link_required')
    points = chain._chain(chosen)
    length = sum(t.GetLength() / 1e6 for t in chosen)
    if length > 12.:
        raise ValueError('Source_Ground_link_length_bound')
    caps = [pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*at), pcbnew.VECTOR2I(*at), width)
        for at in (points[0], points[-1])]
    roots = []
    for cap in caps:
        actual = [p for p in pads if p.IsOnLayer(face)
            and cap.Collide(p.GetEffectiveShape(face), 0)]
        if (len(actual) != 1 or actual[0].GetNetname() != 'GND'
                or actual[0].GetNetCode() <= 0 or actual[0].HasHole()
                or actual[0].GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                or actual[0].GetParentFootprint().IsDNP()
                or cells.cec_return_escape.smd_surface_layer(actual[0]) != face):
            raise ValueError('two_actual_populated_unique_surface_Ground_endpoint_lands_required')
        roots.append(actual[0])
    if len({force._uid(p) for p in roots}) != 2:
        raise ValueError('two_distinct_Source_Ground_endpoint_lands_required')
    # Whole-material contact ownership: touching an end cap does not license
    # a second interior tee along the same long retained conductor. Root-pad
    # material is an explicit Source-owned launch aperture, not a bbox.
    body = pcbnew.SHAPE_POLY_SET()
    aperture = pcbnew.SHAPE_POLY_SET()
    for t in chosen:
        body.BooleanAdd(_poly(t, face, outside=True))
    for pad in roots:
        aperture.BooleanAdd(_poly(pad, face, outside=False))
    for at in (points[0], points[-1]):
        cap = chosen[0].Duplicate()
        cap.SetStart(pcbnew.VECTOR2I(*at)); cap.SetEnd(pcbnew.VECTOR2I(*at))
        aperture.BooleanAdd(_poly(cap, face, outside=False))
    # Two equal-width STRAIGHT capsules sharing an exact endpoint and
    # diverging at >=90 degrees have only their bounded local junction in
    # common. Prove that with exact integer vectors, not repeated polygon
    # booleans whose rounded intersection vertices can leave 1nm slivers.
    # This does NOT license a long edge merely because it touches a port:
    # it must touch ONLY that incident cut edge, never another cut interior.
    junctions = []
    for at, inward in ((points[0], points[1]), (points[-1], points[-2])):
        u = (inward[0] - at[0], inward[1] - at[1])
        for retained in tracks:
            _tick(deadline)
            if (force._uid(retained) in ids or retained.GetClass() != 'PCB_TRACK'
                    or retained.GetNetname() != 'GND' or int(retained.GetLayer()) != face
                    or retained.GetWidth() != width or retained.HasSolderMask()
                    or retained.GetParentGroup() or force._uid(retained) in grouped):
                continue
            ends = (tuple(retained.GetStart()), tuple(retained.GetEnd()))
            if at not in ends or ends[0] == ends[1]:
                continue
            far = ends[1] if ends[0] == at else ends[0]
            v = (far[0] - at[0], far[1] - at[1])
            if (sum(a * b for a, b in zip(u, v)) > 0
                    or not quality.is_canonical_stroke(at, far, tolerance_nm=0)):
                continue
            touching = [t for t in chosen if t.GetEffectiveShape(face).Collide(
                retained.GetEffectiveShape(face), 0)]
            incident = [t for t in chosen if at in (tuple(t.GetStart()), tuple(t.GetEnd()))]
            if (len(incident) != 1 or len(touching) != 1
                    or force._uid(touching[0]) != force._uid(incident[0])):
                continue
            junctions.append(dict(retained_track_uuid=force._uid(retained),
                shared_endpoint_nm=list(at), incident_cut_track_uuid=force._uid(incident[0]),
                integer_direction_dot=sum(a * b for a, b in zip(u, v)),
                same_width_straight_capsules_only=True,
                no_other_cut_edge_has_actual_contact=True))
    unique_junctions = {r['retained_track_uuid'] for r in junctions
        if sum(q['retained_track_uuid'] == r['retained_track_uuid'] for q in junctions) == 1}
    contacts = []
    for item in [*tracks, *pads, *zones]:
        _tick(deadline)
        uid = force._uid(item)
        if uid in ids or not item.IsOnLayer(face):
            continue
        if item.GetClass() == 'ZONE':
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                raise ValueError('Source_Ground_link_surface_fill_unknown')
            shape = pcbnew.SHAPE_POLY_SET(item.GetFilledPolysList(face))
        else:
            if not any(t.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face), 0)
                    for t in chosen):
                continue
            shape = _poly(item, face, outside=True)
        overlap = shape.CloneDropTriangulation()
        overlap.BooleanIntersection(body)
        if not overlap.OutlineCount():
            continue
        if item.GetNetname() != 'GND':
            raise ValueError('Source_Ground_link_has_actual_foreign_contact:' + uid)
        if item.GetClass() == 'PAD':
            if uid not in {force._uid(p) for p in roots}:
                raise ValueError('Source_Ground_link_has_unowned_pad_contact:' + uid)
        elif uid not in unique_junctions:
            overlap.BooleanSubtract(aperture)
            if overlap.OutlineCount():
                raise ValueError('Source_Ground_link_has_unowned_interior_contact:' + uid)
        contacts.append(uid)
    _tick(deadline)
    return dict(source_authority=authority, source_layer=face, source_width_nm=width,
        source_points_nm=[list(p) for p in points], source_length_mm=length,
        endpoint_ground_pads=[force._uid(p) for p in roots],
        retained_endpoint_junctions=junctions,
        retained_native_contact_uuids=sorted(contacts)), roots


def _local_references(board, pad_uuids, deadline):
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    spec = cells._netclass(board, 'GND')
    normal_dia, normal_drill, limits = cells._board_legal_through_via_geometry(
        board, float(spec['via_dia']), float(spec['via_drill']))
    gap = max(int(spec['clearance']), int(board.GetDesignSettings().m_MinClearance))
    proof = []
    for uid in pad_uuids:
        _tick(deadline)
        found = [p for p in pads if force._uid(p) == uid]
        if len(found) != 1:
            raise ValueError('unique_saved_Ground_link_endpoint_land_required')
        pad = found[0]
        witness = cells._existing_return(board, pad, 1.5, allow_native_track_body=True)
        if witness is None:
            raise ValueError('each_Ground_link_endpoint_requires_independent_local_return:' + uid)
        distance, via = witness
        face = cells.cec_return_escape.smd_surface_layer(pad)
        dia = int(via.GetWidth(pcbnew.F_Cu)); drill = int(via.GetDrillValue())
        if (via.GetClass() != 'PCB_VIA' or via.GetNetname() != 'GND'
                or via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
                or dia <= 0 or drill <= 0):
            raise ValueError('actual_qualified_Ground_through_barrel_required')
        local, reason = fab.local_pofv_via_decision(board, via)
        ordinary = (dia >= round(normal_dia * 1e6) and drill >= round(normal_drill * 1e6)
            and dia >= drill + math.ceil(2 * limits['board_min_annular_mm'] * 1e6))
        if (not (local or ordinary)
                or not fr._edge_leg_clear(board, via.GetPosition(), via.GetPosition(), dia // 2)
                or not cells._hole_to_hole_clear(board, via.GetPosition(), drill / 1e6,
                    tolerance_mm=0., ignore_via_uuids={force._uid(via)})[0]
                or not fr._via_spot_clear(board, via.GetPosition(), dia, gap, {pad.GetNetCode()},
                    drill_nm=drill, net_code=pad.GetNetCode(), contained_layers={face},
                    existing_via_uuid=force._uid(via))):
            raise ValueError('Ground_link_endpoint_barrel_process_or_clearance_unqualified:' + uid)
        planes = reference._reference_contacts(board, via)
        if len({row[1] for row in planes}) < 2:
            raise ValueError('two_actual_declared_Ground_reference_faces_required')
        proof.append(dict(pad_uuid=uid, via_uuid=force._uid(via), return_mm=distance,
            diameter_nm=dia, drill_nm=drill, ordinary_geometry_qualified=ordinary,
            local_process_qualified=bool(local), local_process_reason=reason,
            reference_plane_contacts=planes))
    if len({p['via_uuid'] for p in proof}) != 2:
        raise ValueError('independent_distinct_Ground_endpoint_barrels_required')
    _tick(deadline)
    return proof


def _partition_proof(parent, child, ids, deadline):
    result = partitions.compare(parent, child, retired_uuids=ids,
        timeout_s=_remaining(deadline))
    if result.get('available') is not True or result.get('preserved') is not True:
        raise ValueError('Ground_link_cut_lost_surviving_actual_native_partition')
    return {k: v for k, v in result.items()
        if k not in ('source_parts', 'child_parts', 'demoted_parts')}


def _return_proof(parent, child, deadline):
    result = returns.receive(parent, child, timeout_s=_remaining(deadline))
    if result.get('ok') is not True or result.get('complete') is not True:
        raise ValueError('Ground_link_cut_worsened_or_could_not_observe_all_Source_known_returns')
    return {k: v for k, v in result.items() if k not in ('elapsed_s',)}


def _cut(board, ids):
    selected = [t for t in board.GetTracks() if force._uid(t) in ids]
    if len(selected) != len(ids):
        raise ValueError('exact_native_Source_Ground_subtraction_required')
    discard_items(board, selected)


def plan(source, *, board_hint, track_uuids, timeout_s=10.):
    """Read-only Source-derived cut proof; there are no supplied proof flags."""
    deadline = _deadline(timeout_s)
    ids = _ids(track_uuids)
    if type(board_hint) is not str or not board_hint:
        raise ValueError('explicit_Source_Ground_link_board_hint_required')
    source = Path(source).resolve(strict=True)
    with force._thermal_hint(board_hint):
        family = force._family(source, board_hint); epoch = force._code_identity()
        parent = pcbnew.LoadBoard(str(source)); before = binding._source_binding(parent)
        context, _ = _context(parent, source, ids, deadline)
        roots = context['endpoint_ground_pads']
        original_returns = _local_references(parent, roots, deadline)
        child = pcbnew.LoadBoard(str(source)); _cut(child, ids)
        child_returns = _local_references(child, roots, deadline)
        actual_parts = _partition_proof(parent, child, ids, deadline)
        actual_returns = _return_proof(parent, child, deadline)
        if (family != force._family(source, board_hint) or epoch != force._code_identity()
                or before != binding._source_binding(parent)):
            raise ValueError('Source_Ground_link_identity_changed_during_plan')
        _tick(deadline)
        return dict(schema=1, kind='redundant_source_ground_surface_link',
            source=str(source), board_hint=board_hint, track_uuids=ids,
            source_family=family, code_identity=epoch, source_binding=before,
            source_endpoint_returns=original_returns, cut_endpoint_returns=child_returns,
            actual_native_partitions=actual_parts, all_Source_known_returns=actual_returns,
            **context, current_qualified=False, release_authority=False,
            routing_admitted=False, full_saved_board_receiving_still_required=True)


def write_private(proposal, directory, *, timeout_s=10.):
    """Freshly rederive, then write only the literal Source-minus-cut bytes."""
    deadline = _deadline(timeout_s)
    source = Path(proposal['source']).resolve(strict=True)
    fresh = plan(source, board_hint=proposal['board_hint'], track_uuids=proposal['track_uuids'],
        timeout_s=_remaining(deadline))
    if fresh != proposal:
        raise ValueError('stale_or_forged_Source_Ground_link_proposal')
    target = force._copy_family(source, Path(directory))
    raw.write_raw(target, literal.subtract(raw.raw_text(source), fresh['track_uuids']))
    expected = pcbnew.LoadBoard(str(source)); _cut(expected, fresh['track_uuids'])
    child = pcbnew.LoadBoard(str(target))
    if field._field_snapshot_inventory(child) != field._field_snapshot_inventory(expected):
        raise ValueError('literal_Ground_link_subtraction_native_projection_differs')
    with force._thermal_hint(proposal['board_hint']):
        unchanged = (fresh['source_family'] == force._family(source, proposal['board_hint'])
            and fresh['code_identity'] == force._code_identity())
    if not unchanged:
        raise ValueError('Source_Ground_link_changed_during_private_write')
    _tick(deadline)
    return dict(candidate=str(target), candidate_sha256=force._hash(target),
        complete=True, exact_opaque_Source_subtraction=True, new_holes=0,
        added_native_uuids=[], retired_track_uuids=fresh['track_uuids'],
        current_qualified=False, routing_admitted=False, release_authority=False)


class _Lease:
    """Default single <=10s lease; optional explicit four-constituent lease."""
    def __init__(self, seconds, budgets):
        self.deadline = _deadline(seconds)
        self.index = 0; self.timings = {}
        self.started = self.phase_started = self.deadline - seconds
        if budgets is not None and (type(budgets) not in (list, tuple) or len(budgets) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v)
                    or not 0 < v <= seconds for v in budgets)):
            raise ValueError('bounded_explicit_Ground_link_receiving_phases_required')
        self.budgets = None if budgets is None else tuple(float(v) for v in budgets)
        if self.budgets is not None:
            self.deadline = self.started + self.budgets[0]

    def advance(self, name):
        if self.index >= 3 or PHASES[self.index + 1] != name:
            raise ValueError('exact_Ground_link_receiving_phase_order_required')
        now = time.monotonic(); _tick(self.deadline)
        self.timings[PHASES[self.index]] = now - self.phase_started
        self.index += 1; self.phase_started = now
        if self.budgets is not None:
            self.deadline = now + self.budgets[self.index]

    def finish(self):
        if self.index != 3:
            raise ValueError('all_Ground_link_receiving_phases_required')
        now = time.monotonic(); _tick(self.deadline)
        self.timings[PHASES[self.index]] = now - self.phase_started
        if self.budgets is not None and now - self.started >= sum(self.budgets):
            raise ValueError('Ground_link_receiving_aggregate_deadline')


def receive(source, candidate, *, board_hint, track_uuids, timeout_s=10.,
            receiving_phase_timeouts_s=None):
    """Independently inspect the actual child, never trust a producer receipt."""
    result = dict(schema=1, ok=False, complete=False, errors=[],
        current_qualified=False, fab_ready=False, routing_admitted=False,
        release_authority=False, full_saved_board_receiving_still_required=True)
    try:
        lease = _Lease(timeout_s, receiving_phase_timeouts_s)
        if lease.budgets is not None:
            result.update(stage_timings_s=lease.timings, bounded_composition=dict(
                constituents=list(PHASES), stage_limits_s=list(lease.budgets),
                per_constituent_limit_s=timeout_s, aggregate_limit_s=sum(lease.budgets)))
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_Ground_link_source_and_candidate_required')
        with force._thermal_hint(board_hint):
            epoch = force._code_identity()
            families = [force._family(p, board_hint) for p in (source, candidate)]
            q = plan(source, board_hint=board_hint, track_uuids=track_uuids,
                timeout_s=_remaining(lease.deadline))
            lease.advance(PHASES[1])
            if (raw.raw_text(candidate) != literal.subtract(raw.raw_text(source), q['track_uuids'])
                    or force._sidecars(source) != force._sidecars(candidate)):
                raise ValueError('saved_Ground_link_child_not_exact_opaque_Source_subtraction')
            parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
            expected = pcbnew.LoadBoard(str(source)); _cut(expected, q['track_uuids'])
            if field._field_snapshot_inventory(child) != field._field_snapshot_inventory(expected):
                raise ValueError('saved_Ground_link_child_not_exact_native_Source_subtraction')
            lease.advance(PHASES[2])
            result['actual_native_partitions'] = _partition_proof(parent, child,
                q['track_uuids'], lease.deadline)
            result['actual_saved_endpoint_returns'] = _local_references(child,
                q['endpoint_ground_pads'], lease.deadline)
            lease.advance(PHASES[3])
            result['all_Source_known_returns'] = _return_proof(parent, child, lease.deadline)
            craft = [quality.analyze_board(b) for b in (parent, child)]
            if any(craft[1][k] > craft[0][k] for k in ('issue_count', 'non_octilinear_count')):
                raise ValueError('Ground_link_subtraction_worsened_route_craft')
            # Exact subtraction cannot add an aggressor, move a victim, or
            # change ANY reference-plane fill. The full field receiver still
            # owns ultimate admission; this operator claims no shielding/PI.
            hashes = [force._hash(p) for p in (source, candidate)]
            if epoch != force._code_identity() or families != [force._family(p, board_hint)
                    for p in (source, candidate)]:
                raise ValueError('saved_Ground_link_Source_candidate_or_code_changed')
            lease.finish()
            result.update(ok=True, complete=True, proposal=q, code_identity=epoch,
                source_sha256=hashes[0], candidate_sha256=hashes[1],
                exact_opaque_Source_subtraction=True, exact_native_Source_subtraction=True,
                every_Source_native_partition_preserved=True,
                all_Source_known_return_witnesses_preserved=True,
                every_Source_reference_plane_and_power_fill_byte_unchanged=True,
                new_holes=0, added_native_uuids=[], retired_track_uuids=q['track_uuids'],
                source_candidate_and_code_unchanged=True,
                current_field_Kelvin_fabrication_and_original_parent_receiving_still_required=True)
    except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result
