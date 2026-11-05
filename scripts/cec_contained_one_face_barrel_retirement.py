"""Receive deletion of electrically redundant, fully buried one-face barrels.

A dangling-via warning is not deletion authority. This separate native scope
requires one actual contact face and the WHOLE conservative outer via disk
inside one retained native copper body on that face. The default cannot cut
a trace. An explicit compound scope may additionally retire one short,
pad/zone-free source stem per barrel, rooted only at retained track endpoints.
It cannot cut a land, power zone, mechanical hole or real layer transition. Source locks and
membership require explicit object permissions; typed dependency annotations
remain protected. Geometry, current, field and clipped-cut receivers still
have independent authority. No new ampacity or fabrication credit is given.
"""
import math
import tempfile
import time
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_generated_pickup_retirement as physical
import cec_ordinary_route_receiving as ordinary
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items


def _ids(values, label):
    if (type(values) not in (list, tuple, set) or len(values) > 8
            or any(type(u) is not str or not u for u in values)
            or len(set(values)) != len(values)):
        raise ValueError('bounded_exact_' + label + '_required')
    return set(values)


def attached_short_leaf_uuids(board, via_uuids, *, maximum_length_nm=1000000):
    """Bounded exact-source proposals, never permission to cut those tracks."""
    ids = _ids(via_uuids, 'contained_leaf_source_barrels')
    if not ids or type(maximum_length_nm) is not int or not 1 <= maximum_length_nm <= 1000000:
        raise ValueError('bounded_contained_leaf_discovery_required')
    tracks = list(board.GetTracks()); live = {force._uid(t):t for t in tracks}
    if len(tracks) > 8192 or len(live) != len(tracks):
        raise ValueError('contained_leaf_discovery_native_inventory_bound')
    if any(u not in live or live[u].GetClass() != 'PCB_VIA' for u in ids):
        raise ValueError('contained_leaf_discovery_exact_native_barrels_required')
    axes = {(str(live[u].GetNetname()),tuple(live[u].GetPosition())) for u in ids}
    result = sorted(force._uid(t) for t in tracks if t.GetClass() == 'PCB_TRACK'
        and 0 < t.GetLength() <= maximum_length_nm
        and any((str(t.GetNetname()),tuple(p)) in axes for p in (t.GetStart(),t.GetEnd())))
    if len(result) > 8: raise ValueError('contained_leaf_discovery_work_bound')
    return result


def _leaf_rows(board, native, graphics, via_rows, leaf_ids, unlock, grouped, deadline):
    """Re-prove real pad-free single-root source stems; no net-name authority."""
    import cec_fr as fr
    paired = fr.coupled_pair_nets(board)
    live = {force._uid(t):t for t in board.GetTracks()}
    retired_vias = {r['uuid'] for r in via_rows}; rows = []; assigned = set()
    for uid in sorted(leaf_ids):
        t = live.get(uid)
        if (t is None or t.GetClass() != 'PCB_TRACK' or not 0 < t.GetWidth() <= 1000000
                or not 0 < t.GetLength() <= 1000000):
            raise ValueError('contained_leaf_short_native_track_required')
        if str(t.GetNetname()) in paired:
            raise ValueError('contained_leaf_coupled_pair_requires_its_own_receiver')
        owners = [g for g in board.Groups() if g.ContainsItem(t)]
        if t.IsLocked() and uid not in unlock:
            raise ValueError('contained_leaf_explicit_source_lock_permission_required')
        endpoints = [tuple(t.GetStart()),tuple(t.GetEnd())]
        matches = [r for r in via_rows if r['net'] == str(t.GetNetname())
            and r['contact_face'] == int(t.GetLayer())
            and tuple(r['source_position_nm']) in endpoints]
        if len(matches) != 1 or matches[0]['uuid'] in assigned:
            raise ValueError('contained_leaf_one_exact_source_stem_per_barrel_required')
        via = matches[0]; assigned.add(via['uuid'])
        if (len(owners) > 1 or owners and (uid not in grouped or owners[0].IsLocked()
                or owners[0].GetParentGroup() is not None
                or force._uid(owners[0]) not in via['source_owner_uuids'])):
            raise ValueError('contained_leaf_explicit_same_direct_source_owner_required')
        root = endpoints[1] if endpoints[0] == tuple(via['source_position_nm']) else endpoints[0]
        roots = []; face = int(t.GetLayer()); shape = t.GetEffectiveShape(face)
        for item in native:
            if time.monotonic() >= deadline: raise ValueError('contained_leaf_native_geometry_deadline')
            oid = force._uid(item)
            if oid in leaf_ids | retired_vias or not item.IsOnLayer(face): continue
            if item.GetClass() == 'ZONE':
                if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                    if item.Outline().Collide(shape,0):
                        raise ValueError('contained_leaf_unknown_saved_zone_material')
                    continue
                other = item.GetFilledPolysList(face)
            else:
                other = item.GetEffectiveShape(face)
            if not shape.Collide(other,0): continue
            if (item.GetClass() != 'PCB_TRACK' or item.GetNetCode() != t.GetNetCode()
                    or item.GetWidth() < t.GetWidth()
                    or root not in (tuple(item.GetStart()),tuple(item.GetEnd()))):
                raise ValueError('contained_leaf_retained_contacts_must_be_full_width_root_endpoints')
            roots.append(oid)
        if not roots: raise ValueError('contained_leaf_actual_retained_root_required')
        if not set(via['retained_native_whole_disk_covers']) - leaf_ids:
            raise ValueError('contained_leaf_barrel_cover_cannot_be_retired_stem')
        for graphic in graphics:
            if time.monotonic() >= deadline: raise ValueError('contained_leaf_native_geometry_deadline')
            if not graphic.IsOnLayer(face): continue
            poly = pcbnew.SHAPE_POLY_SET()
            graphic.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE)
            if poly.OutlineCount() and poly.Collide(shape,0):
                raise ValueError('contained_leaf_unassigned_native_copper_contact')
        rows.append(dict(uuid=uid, via_uuid=via['uuid'], net=str(t.GetNetname()), layer=face,
            width_nm=t.GetWidth(), start_nm=list(t.GetStart()), end_nm=list(t.GetEnd()),
            retained_root_nm=list(root), retained_root_track_uuids=sorted(roots),
            source_locked=bool(t.IsLocked()), source_owner_uuids=sorted(force._uid(g) for g in owners),
            removed_length_nm=t.GetLength()))
    return rows


def plan(board, via_uuids, *, allow_locked_via_uuids=(),
         allow_grouped_via_uuids=(), leaf_track_uuids=(),
         allow_locked_leaf_track_uuids=(), allow_grouped_leaf_track_uuids=(), timeout_s=10.):
    """Read-only actual material proof, not native DRC or current admission."""
    selected = _ids(via_uuids, 'contained_one_face_barrels')
    unlocked = _ids(allow_locked_via_uuids, 'contained_barrel_lock_scope')
    grouped = _ids(allow_grouped_via_uuids, 'contained_barrel_group_scope')
    leaves = _ids(leaf_track_uuids, 'contained_barrel_leaf_scope')
    leaf_unlock = _ids(allow_locked_leaf_track_uuids, 'contained_leaf_lock_scope')
    leaf_grouped = _ids(allow_grouped_leaf_track_uuids, 'contained_leaf_group_scope')
    if (not selected or not unlocked <= selected or not grouped <= selected
            or selected & leaves or not leaf_unlock <= leaves or not leaf_grouped <= leaves
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10.):
        raise ValueError('explicit_bounded_contained_barrel_policy_required')
    deadline = time.monotonic() + timeout_s
    def tick():
        if time.monotonic() >= deadline:
            raise ValueError('contained_barrel_native_geometry_deadline')
    tracks = list(board.GetTracks())
    live = {force._uid(t): t for t in tracks}
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    groups = list(board.Groups())
    graphics = [*board.GetDrawings(), *[g for fp in board.GetFootprints()
                                      for g in fp.GraphicalItems()],
                *[f for fp in board.GetFootprints() for f in fp.GetFields() if f.IsVisible()]]
    native = sorted(pads + tracks + zones, key=force._uid)
    if (len(live) != len(tracks) or len(native) + len(graphics) > 16384
            or len(groups) > 2048):
        raise ValueError('contained_barrel_native_inventory_bound_or_ambiguity')
    layers = tuple(map(int, board.GetEnabledLayers().CuStack()))
    if not 2 <= len(layers) <= 64:
        raise ValueError('contained_barrel_actual_copper_stack_required')
    # Group names may carry UUID dependencies even without membership. Never
    # silently orphan a source allocation or another typed electrical anchor.
    if any(any(uid in g.GetName() for uid in selected | leaves) for g in groups):
        raise ValueError('contained_barrel_source_typed_dependency_protected')
    rows = []
    for uid in sorted(selected):
        tick(); via = live.get(uid)
        if (via is None or via.GetClass() != 'PCB_VIA' or via.GetNetCode() <= 0
                or via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
                or any(not via.IsOnLayer(l) or not 0 < via.GetDrillValue()
                       < via.GetWidth(l) <= 10000000 for l in layers)):
            raise ValueError('contained_barrel_positive_native_through_via_required')
        if via.IsLocked() and uid not in unlocked:
            raise ValueError('contained_barrel_explicit_source_lock_permission_required')
        owners = [g for g in groups if g.ContainsItem(via)]
        if (len(owners) > 1 or owners and (uid not in grouped
                or owners[0].IsLocked() or owners[0].GetParentGroup() is not None)):
            raise ValueError('contained_barrel_explicit_unlocked_direct_owner_required')
        contacts = []; faces = set()
        for item in native:
            tick(); oid = force._uid(item)
            if oid == uid: continue
            touched = []
            for layer in layers:
                if not item.IsOnLayer(layer): continue
                if item.GetClass() == 'ZONE':
                    if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                        if item.Outline().Collide(via.GetEffectiveShape(layer), 0):
                            raise ValueError('contained_barrel_unknown_saved_zone_material')
                        continue
                    shape = item.GetFilledPolysList(layer)
                else:
                    shape = item.GetEffectiveShape(layer)
                if via.GetEffectiveShape(layer).Collide(shape, 0): touched.append(layer)
            if not touched: continue
            if item.GetNetCode() != via.GetNetCode() or item.GetClass() == 'PCB_VIA':
                raise ValueError('contained_barrel_foreign_copper_or_other_barrel_contact')
            faces.update(touched)
            contacts.append(dict(uuid=oid, kind=item.GetClass(), layers=touched))
        if len(faces) != 1:
            raise ValueError('contained_barrel_exactly_one_actual_contact_face_required')
        face = next(iter(faces))
        # Actual copper art has no inferred electrical ownership. Rule areas,
        # silk and courtyard drawings do not count as conducting material.
        for graphic in graphics:
            for layer in layers:
                tick()
                if not graphic.IsOnLayer(layer): continue
                poly = pcbnew.SHAPE_POLY_SET()
                graphic.TransformShapeToPolygon(poly, layer, 0, 1000, pcbnew.ERROR_OUTSIDE)
                if poly.OutlineCount() and poly.Collide(via.GetEffectiveShape(layer), 0):
                    raise ValueError('contained_barrel_unassigned_native_copper_contact')
        covers = []
        contact_ids = {r['uuid'] for r in contacts}
        for item in native:
            tick()
            if force._uid(item) not in contact_ids or force._uid(item) in leaves: continue
            kind = item.GetClass()
            if kind == 'ZONE':
                material = item.GetFilledPolysList(face)
            elif kind == 'PCB_TRACK' or (kind == 'PAD' and not item.HasHole()
                    and item.GetAttribute() == pcbnew.PAD_ATTRIB_SMD):
                material = pcbnew.SHAPE_POLY_SET()
                item.TransformShapeToPolygon(material, face, 0, 1000, pcbnew.ERROR_INSIDE)
            else:
                continue
            outer = pcbnew.SHAPE_POLY_SET()
            via.TransformShapeToPolygon(outer, face, 0, 1000, pcbnew.ERROR_OUTSIDE)
            if not outer.OutlineCount() or not material.OutlineCount(): continue
            outer.BooleanSubtract(material)
            if not outer.OutlineCount(): covers.append(force._uid(item))
        if not covers:
            raise ValueError('contained_barrel_whole_disk_inside_one_retained_native_body_required')
        rows.append(dict(uuid=uid, net=str(via.GetNetname()), contact_face=face,
            actual_contacts=contacts, retained_native_whole_disk_covers=sorted(covers),
            source_locked=bool(via.IsLocked()), source_owner_uuids=sorted(force._uid(g) for g in owners),
            source_position_nm=list(via.GetPosition()), source_drill_nm=via.GetDrillValue(),
            source_diameters_nm={str(l): via.GetWidth(l) for l in layers}))
    result = dict(schema=1, scope='fully_contained_single_native_face_barrel_cut',
        source_binding=_source_binding(board), via_uuids=sorted(selected), rows=rows,
        allow_locked_via_uuids=sorted(unlocked), allow_grouped_via_uuids=sorted(grouped),
        surviving_copper_geometry_unchanged=True, current_qualified=False,
        new_capacity_credited=False, release_authority=False)
    if leaves:
        result.update(scope='fully_contained_barrel_and_pad_free_single_root_stem_cut',
            leaf_track_uuids=sorted(leaves), allow_locked_leaf_track_uuids=sorted(leaf_unlock),
            allow_grouped_leaf_track_uuids=sorted(leaf_grouped),
            source_leaf_rows=_leaf_rows(board,native,graphics,rows,leaves,leaf_unlock,leaf_grouped,deadline),
            surviving_copper_geometry_unchanged=True,
            no_land_zone_or_surviving_route_width_may_change=True)
    return result


def _replan(board, proposal):
    fresh = plan(board, proposal['via_uuids'],
        allow_locked_via_uuids=proposal['allow_locked_via_uuids'],
        allow_grouped_via_uuids=proposal['allow_grouped_via_uuids'],
        leaf_track_uuids=proposal.get('leaf_track_uuids',()),
        allow_locked_leaf_track_uuids=proposal.get('allow_locked_leaf_track_uuids',()),
        allow_grouped_leaf_track_uuids=proposal.get('allow_grouped_leaf_track_uuids',()))
    if fresh != proposal:
        raise ValueError('contained_barrel_exact_source_replan_required')
    return fresh


def subtract(board, proposal):
    fresh = _replan(board, proposal)
    live = {force._uid(t): t for t in board.GetTracks()}
    discard_items(board, [live[u] for u in fresh['via_uuids']+fresh.get('leaf_track_uuids',[])])


def receive(source, candidate, proposal, *, board_hint, sense_timeout_s=40.):
    """Exact saved retirement, full partitions, physical terminals and cuts."""
    result = dict(schema=1, ok=False, complete=False, errors=[], current_qualified=False,
        new_capacity_credited=False, release_authority=False,
        uncapped_native_DRC_and_full_release_receiving_still_required=True)
    try:
        if (type(board_hint) is not str or not board_hint
                or type(sense_timeout_s) not in (int, float) or not math.isfinite(sense_timeout_s)
                or not 0 < sense_timeout_s <= 60.):
            raise ValueError('contained_barrel_explicit_saved_receiving_budget_required')
        paths = [Path(p).resolve() for p in (source, candidate)]
        if paths[0] == paths[1]: raise ValueError('contained_barrel_distinct_saved_paths_required')
        epoch = force._code_identity(); families = [force._family(p, board_hint) for p in paths]
        parent, child = [pcbnew.LoadBoard(str(p)) for p in paths]
        _replan(parent, proposal)
        with tempfile.TemporaryDirectory(prefix='cec-contained-one-face-') as tmp:
            expected = force._copy_family(paths[0], Path(tmp)/'family')
            replay = pcbnew.LoadBoard(str(expected)); subtract(replay, proposal)
            additive._ground_refill(replay); field._save_field_snapshot(replay, expected)
            _, wanted = additive._nodes(expected); _, actual = additive._nodes(paths[1])
            if (wanted.keys() != actual.keys() or any(syntax._freeze(wanted[u])
                    != syntax._freeze(actual[u]) for u in wanted)
                    or force._preservation_snapshot(expected)[1] != force._preservation_snapshot(paths[1])[1]
                    or force._sidecars(expected) != force._sidecars(paths[1])):
                raise ValueError('contained_barrel_exact_cut_refill_or_source_metadata_differs')
        result['exact_source_cut_and_ground_refill_received'] = True
        retired = proposal['via_uuids']+proposal.get('leaf_track_uuids',[])
        first = ordinary._partition(parent, time.monotonic()+10., retired_uuids=retired)
        last = ordinary._partition(child, time.monotonic()+10., retained_keys=set().union(*first))
        if not all(any(part <= other for other in last) for part in first):
            raise ValueError('contained_barrel_surviving_native_partition_lost')
        graphs = []
        changed = sorted({r['net'] for r in proposal['rows']})
        for net in changed:
            pair = [physical._scoped_terminal_graph(b, net) for b in (parent, child)]
            if pair[0]['pad_uuids'] != pair[1]['pad_uuids']:
                raise ValueError('contained_barrel_actual_terminal_inventory_changed')
            graphs.append(dict(net=net, source=pair[0], candidate=pair[1]))
        result['actual_drilled_terminal_graphs'] = graphs
        debt = current.receive(*paths, board_hint=board_hint)
        result['current_debt_receiving'] = debt
        if not debt['ok'] or not debt['complete']:
            raise ValueError('contained_barrel_whole_current_receiving_refused')
        with force._thermal_hint(board_hint):
            delta = sorted(field.blocker_keys(field.field_coupling_summary(str(paths[1])))
                - field.blocker_keys(field.field_coupling_summary(str(paths[0]))))
        result['new_field_blocker_keys'] = delta
        if delta: raise ValueError('contained_barrel_new_field_interference_blocker')
        old, new = [sense.replay(p, board_hint=board_hint, timeout_s=sense_timeout_s) for p in paths]
        transforms = sense.native_copper_transform_inventory(parent, child, modified_nets=changed)
        cuts = sense.compare_contour_preservation(old, new, modified_nets=changed,
            native_copper_transforms=transforms)
        result['absolute_native_cut_preservation'] = cuts
        if not cuts['comparison_complete'] or not cuts['same_evidence']:
            raise ValueError('contained_barrel_absolute_physical_cuts_not_preserved')
        if epoch != force._code_identity() or families != [force._family(p, board_hint) for p in paths]:
            raise ValueError('contained_barrel_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]), code_identity=epoch,
            retired_via_uuids=proposal['via_uuids'], surviving_native_partitions_preserved=True,
            source_candidate_and_code_unchanged=True)
        if proposal.get('leaf_track_uuids'):
            result['retired_leaf_track_uuids'] = proposal['leaf_track_uuids']
    except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
