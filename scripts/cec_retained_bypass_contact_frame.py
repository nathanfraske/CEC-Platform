"""Zero-cut bypass slides with positively retained native Source contacts.

This is NOT the unwired-land tier. Every original touching stroke must still
touch the posed land. Removing all moving pads from the graph, each original
stroke component must have its own full-width entry inside BOTH old and new
lands. Only actual Source-selected bypasses of stationary owners qualify.
No pad/zone/barrel contact, foreign-net bridge, cut, remote-return waiver or
current rating is inferred. Local supply and immediate Ground demands remain.
"""
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_constraints as constraints
import cec_decoupler_cell as cell
import cec_device_power_roles as roles
import cec_force_current as force
import cec_projected_ground_contact as signatures


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('retained_bypass_contact_frame_deadline')


def _pose(fp):
    return [fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6,
            fp.GetOrientationDegrees()]


def _same_pose(fp, target):
    return (tuple(fp.GetPosition()) == tuple(round(v * 1e6) for v in target[:2])
            and abs((fp.GetOrientationDegrees() - target[2] + 180) % 360 - 180) < 1e-9)


def _full_entry(board, pad, future, track, width, face, deadline):
    if track.GetWidth() < width:
        return None
    # A conservative endpoint disk, never a centre-only or bounding-box kiss.
    for at in (track.GetStart(), track.GetEnd()):
        _tick(deadline)
        marker = pcbnew.PCB_TRACK(board)
        marker.SetLayer(face)
        marker.SetStart(at)
        marker.SetEnd(at)
        marker.SetWidth(width + 4000)
        contained = True
        for land in (pad, future):
            outside = pcbnew.SHAPE_POLY_SET()
            marker.TransformShapeToPolygon(outside, face, 0, 1000, pcbnew.ERROR_OUTSIDE)
            inside = pcbnew.SHAPE_POLY_SET()
            land.TransformShapeToPolygon(inside, face, 0, 1000, pcbnew.ERROR_INSIDE)
            outside.BooleanSubtract(inside)
            if outside.OutlineCount():
                contained = False
                break
        if contained:
            return dict(track_uuid=force._uid(track), at_nm=list(at), width_nm=width,
                        complete_old_and_projected_entry_disk_contained=True)
    return None


def plan(board, poses, *, board_hint, max_shift_mm=6., timeout_s=2.,
         allow_octilinear_rotations=False):
    """Prove one finite complete bypass-only moving frame, without mutation."""
    if (type(poses) is not dict or not 1 <= len(poses) <= 8
            or type(board_hint) is not str or not board_hint
            or type(max_shift_mm) not in (int, float) or not math.isfinite(max_shift_mm)
            or not 0 < max_shift_mm <= 32.
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10.
            or type(allow_octilinear_rotations) is not bool):
        raise ValueError('bounded_retained_bypass_contact_frame_required')
    deadline = time.monotonic() + timeout_s
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    moving = {}
    for ref, target in poses.items():
        fp = fps.get(ref)
        if (fp is None or type(target) not in (list, tuple) or len(target) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in target)):
            raise ValueError('literal_finite_retained_bypass_pose_required')
        if _same_pose(fp, target):
            continue
        turn = (target[2] - fp.GetOrientationDegrees()) % 360
        if (fp.IsLocked() or fp.IsDNP() or len(list(fp.Pads())) != 2
                or not any(abs(turn - a) < 1e-6 for a in
                           range(0, 361, 45 if allow_octilinear_rotations else 90))
                or math.dist(tuple(fp.GetPosition()), [round(v * 1e6) for v in target[:2]])
                    > max_shift_mm * 1e6):
            raise ValueError('unlocked_bounded_bypass_only_contact_frame_required')
        moving[ref] = fp
    if not moving:
        raise ValueError('actual_moving_bypass_contact_frame_required')
    source = Path(board.GetFileName())
    if not board.GetFileName() or not source.is_file():
        raise ValueError('literal_saved_bypass_contact_source_required')
    binding = row._source_binding(board)
    digest = force._hash(source)
    literal = pcbnew.LoadBoard(str(source))
    if row._source_binding(literal) != binding:
        raise ValueError('literal_saved_bypass_contact_source_required')
    with force._thermal_hint(board_hint):
        assigned = constraints._device_bypass_assignment(board, project_max_mm=3.5)
    by_cap = {}
    for choice in assigned['assigned'].values():
        by_cap.setdefault(choice['cap_ref'], []).append(choice['requirement'])
    material = [*(p for fp in board.GetFootprints() for p in fp.Pads()),
                *board.GetTracks(), *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    if len(material) > 16384:
        raise ValueError('retained_bypass_native_item_bound')
    tracks = list(board.GetTracks())
    if len({force._uid(t) for t in tracks}) != len(tracks):
        raise ValueError('unique_retained_bypass_source_copper_identity_required')
    graphs = {}
    pads = {}
    retained = set()
    for ref, fp in sorted(moving.items()):
        _tick(deadline)
        requirements = by_cap.get(ref, [])
        if len(requirements) != 1:
            raise ValueError('unique_actual_source_bypass_assignment_required')
        req = requirements[0]
        owner = fps.get(req['ref'])
        model = None if owner is None else roles.footprint_contract(owner)
        if (owner is None or req['ref'] not in poses or not _same_pose(owner, poses[req['ref']])
                or not model or set(model['pins']) != {p.GetNumber() for p in owner.Pads()}
                or model['pins'].get(str(req['pin'])) not in ('power_input', 'power_output')
                or (req.get('return_rail') or 'GND') != 'GND'
                or {p.GetNetname() for p in fp.Pads()} != {req['rail'], 'GND'}
                or owner.FindPadByNumber(str(req['pin'])).GetNetname() != req['rail']):
            raise ValueError('stationary_source_typed_selected_bypass_owner_required')
        projected = pcbnew.FOOTPRINT(fp)
        projected.SetPosition(pcbnew.VECTOR2I(*(round(v * 1e6) for v in poses[ref][:2])))
        projected.SetOrientationDegrees(poses[ref][2])
        future_pads = {force._uid(p): p for p in projected.Pads()}
        for pad in fp.Pads():
            _tick(deadline)
            face = cell.cec_return_escape.smd_surface_layer(pad)
            if (pad.HasHole() or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                    or pad.GetNetCode() <= 0 or face is None):
                raise ValueError('source_selected_bypass_surface_lands_required')
            future = future_pads[force._uid(pad)]
            contacts = {}
            for item in material:
                _tick(deadline)
                if force._uid(item) == force._uid(pad) or not item.IsOnLayer(face):
                    continue
                if not item.GetBoundingBox().Intersects(pad.GetBoundingBox()):
                    continue
                if item.GetClass() == 'ZONE':
                    if not item.IsFilled():
                        raise ValueError('unknown_source_fill_at_retained_bypass')
                    touches = item.GetFilledPolysList(face).Collide(pad.GetEffectiveShape(face), 0)
                else:
                    touches = item.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face), 0)
                if not touches:
                    continue
                if (item.GetClass() != 'PCB_TRACK' or item.GetNetname() != pad.GetNetname()
                        or item.GetLength() <= 0 or not 0 < item.GetWidth() <= 20000000
                        or not future.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face), 0)):
                    raise ValueError('every_old_bypass_contact_must_be_same_net_retained_surface_stroke')
                contacts[force._uid(item)] = item
            if not 1 <= len(contacts) <= 32:
                raise ValueError('positive_bounded_old_bypass_stroke_contacts_required')
            key = (str(pad.GetNetname()), int(face))
            if key not in graphs:
                selected = [t for t in tracks if t.GetClass() == 'PCB_TRACK'
                            and t.GetNetname() == key[0] and t.GetLayer() == face]
                if not 1 <= len(selected) <= 2048:
                    raise ValueError('retained_bypass_stroke_graph_bound')
                graph = pcbnew.CONNECTIVITY_DATA()
                for item in selected:
                    _tick(deadline)
                    if not graph.Add(item):
                        raise ValueError('retained_bypass_native_stroke_graph_refused')
                graphs[key] = (graph, {force._uid(t): t for t in selected})
            graph, lookup = graphs[key]
            remaining = dict(contacts)
            components = []
            while remaining:
                _tick(deadline)
                uid = min(remaining)
                reached = {uid} | {force._uid(i) for i in graph.GetConnectedItems(remaining[uid])}
                if not reached <= lookup.keys() or not 1 <= len(reached) <= 2048:
                    raise ValueError('literal_same_net_surface_stroke_component_required')
                cohort = sorted(set(remaining) & reached)
                width = max(contacts[u].GetWidth() for u in cohort)
                entries = [_full_entry(board, pad, future, contacts[u], width, face, deadline)
                           for u in cohort]
                entry = next((e for e in entries if e is not None), None)
                if entry is None:
                    raise ValueError('each_old_bypass_component_requires_its_own_full_width_retained_entry')
                components.append(dict(source_contact_track_uuids=cohort,
                    unchanged_stroke_component_uuids=sorted(reached), full_width_entry=entry,
                    graph_excludes_all_pads_zones_barrels_and_foreign_nets=True))
                retained.update(reached)
                for u in cohort:
                    del remaining[u]
            pads[force._uid(pad)] = dict(owner=ref, pin=pad.GetNumber(), net=key[0], face=key[1],
                selected_bypass=dict(owner=req['ref'], pin=str(req['pin']), rail=req['rail']),
                manufacturer_source=model['source'], source_contacts=sorted(contacts),
                components=components, future_land_sha256=signatures._land_digest(future, deadline))
    live = {force._uid(t): t for t in tracks}
    if row._source_binding(board) != binding or force._hash(source) != digest:
        raise ValueError('retained_bypass_contact_source_changed')
    _tick(deadline)
    return json.loads(json.dumps(dict(schema=1, scope='source_retained_bypass_stroke_contact_frame',
        source=str(source.resolve()), source_sha256=digest, source_native_binding=binding,
        board_hint=board_hint, poses=poses, max_shift_mm=max_shift_mm,
        allow_octilinear_rotations=allow_octilinear_rotations, moving_refs=sorted(moving), pads=pads,
        retained_track_uuids=sorted(retained),
        retained_track_signatures={u: signatures._anchor_signature(board, live[u]) for u in sorted(retained)},
        no_source_metal_cut_or_motion=True, no_new_copper_or_barrels=True,
        inherited_source_width_not_qualified=True, immediate_ground_and_local_supply_still_required=True,
        current_qualified=False, routing_admitted=False, release_authority=False), allow_nan=False))


def observe(board, proof, *, timeout_s=10.):
    """Fresh saved-Source replay plus exact live entries after all other cuts."""
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10.:
        raise ValueError('bounded_retained_bypass_contact_observation_required')
    deadline = time.monotonic() + timeout_s
    source = Path(proof['source'])
    if force._hash(source) != proof['source_sha256']:
        raise ValueError('retained_bypass_contact_source_file_changed')
    parent = pcbnew.LoadBoard(str(source))
    fresh = plan(parent, proof['poses'], board_hint=proof['board_hint'],
        max_shift_mm=proof['max_shift_mm'], allow_octilinear_rotations=proof['allow_octilinear_rotations'],
        timeout_s=max(.001, deadline - time.monotonic()))
    if fresh != proof:
        raise ValueError('stale_or_forged_retained_bypass_contact_frame')
    binding = row._source_binding(board)
    live = {force._uid(t): t for t in board.GetTracks()}
    if (not set(proof['retained_track_uuids']) <= live.keys()
            or any(signatures._anchor_signature(board, live[u]) != signature
                   for u, signature in proof['retained_track_signatures'].items())):
        raise ValueError('retained_bypass_source_stroke_graph_changed_after_cuts')
    pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    for uid, entry in proof['pads'].items():
        _tick(deadline)
        pad = pads.get(uid)
        if (pad is None or pad.GetNetname() != entry['net']
                or signatures._land_digest(pad, deadline) != entry['future_land_sha256']
                or not _same_pose(pad.GetParentFootprint(), proof['poses'][entry['owner']])):
            raise ValueError('exact_live_retained_bypass_land_required')
        for contact in entry['source_contacts']:
            if not pad.GetEffectiveShape(entry['face']).Collide(live[contact].GetEffectiveShape(entry['face']), 0):
                raise ValueError('retained_bypass_live_stroke_contact_lost')
    if row._source_binding(board) != binding:
        raise ValueError('retained_bypass_observer_changed_board')
    _tick(deadline)
    return dict(ok=True, complete=True, all_old_stroke_contacts_and_component_entries_preserved=True,
        current_qualified=False, new_immediate_return_qualification=False,
        local_supply_and_ground_demands_still_required=True, release_authority=False)
