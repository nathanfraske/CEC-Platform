"""Exact Source-class Ground leaf of an additional aggregate capacitor.

Canonical passive identity and the unchanged full supply rail prove this
distinct role. It is neither a selected bypass nor a manufacturer Ground
pin. Only an exclusive endpoint-linear saved leaf is owned; every first
retained contact and every barrel/partition remains an independent demand.
"""
import hashlib
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_force_current as force
import cec_cell_row_rebuild as row
import cec_fab_profile as fab
import cec_source_sideband_monitor_tap as material
from cec_route_dimensions import NetclassTable


SCOPE = 'Source_canonical_additional_aggregate_capacitor_Ground_leaf-v1'
KIND = 'positive_existing_Source_additional_aggregate_capacitor_Ground_leaf'
MAX_TRACKS = 8
MAX_LENGTH_MM = 12.


def _need(value, reason):
    if not value: raise ValueError(reason)


def _wire(value): return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()


def _tick(deadline):
    _need(time.monotonic() < deadline, 'aggregate_cap_Ground_leaf_deadline')


def _objects(board):
    items = [*(p for f in board.GetFootprints() for p in f.Pads()), *board.GetTracks(),
        *(z for z in board.Zones() if not z.GetIsRuleArea())]
    found = {force._uid(i): i for i in items}
    _need(len(items) <= 16384 and len(found) == len(items),
        'aggregate_cap_Ground_unique_bounded_material_required')
    return found


def _lower(item, face):
    if item.GetClass() == 'ZONE':
        _need(item.IsFilled(), 'aggregate_cap_Ground_actual_zone_fill_required')
        return pcbnew.SHAPE_POLY_SET(item.GetFilledPolysList(face))
    return material._copper(item, face)


def _contact(first, second, face, holes, deadline):
    """Positive lower copper only, including third-object drill exclusion."""
    _tick(deadline)
    if not first.GetBoundingBox().Intersects(second.GetBoundingBox()): return None
    area = _lower(first, face); area.BooleanIntersection(_lower(second, face))
    if not area.OutlineCount(): return None
    for item in holes:
        _tick(deadline); hole = item.GetEffectiveHoleShape()
        if not area.BBox().Intersects(hole.BBox()): continue
        polygon = pcbnew.SHAPE_POLY_SET(); hole.TransformToPolygon(polygon, 1, pcbnew.ERROR_OUTSIDE)
        area.BooleanSubtract(polygon)
        if not area.OutlineCount(): return None
    return area if area.Area() > 0 else None


def _record(item, face):
    value = dict(uuid=force._uid(item), kind=item.GetClass(), net=item.GetNetname(),
        layer_id=int(face), lower_copper=_lower(item, face).Format(), locked=bool(item.IsLocked()))
    if item.GetClass() == 'PAD':
        value.update(footprint_uuid=force._uid(item.GetParentFootprint()),
            ref=item.GetParentFootprint().GetReference(), pin=item.GetNumber(),
            at_nm=list(item.GetPosition()), layers=list(map(int, item.GetLayerSet().CuStack())))
    elif item.GetClass() == 'PCB_TRACK':
        value.update(start_nm=list(item.GetStart()), end_nm=list(item.GetEnd()), width_nm=item.GetWidth())
    elif item.GetClass() == 'PCB_VIA':
        value.update(at_nm=list(item.GetPosition()), diameter_nm=item.GetWidth(face),
            drill_nm=item.GetDrillValue(), top=int(item.TopLayer()), bottom=int(item.BottomLayer()))
    return _wire(value)


def _walk(board, pad, width, face, deadline):
    """Closed positive role already proved; no legacy role or width override."""
    items = _objects(board); root = force._uid(pad)
    holes = [i for i in items.values() if i.IsOnLayer(face) and (i.GetClass() == 'PCB_VIA'
        or i.GetClass() == 'PAD' and i.HasHole())]
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    same_face = [i for i in items.values() if i.IsOnLayer(face)]
    touching = []
    for item in same_face:
        _tick(deadline)
        if force._uid(item) == root or _contact(pad, item, face, holes, deadline) is None: continue
        _need(item.GetNetCode() == pad.GetNetCode(), 'aggregate_cap_Ground_foreign_root_contact')
        _need(item.GetClass() == 'PCB_TRACK', 'aggregate_cap_Ground_retained_material_at_root')
        touching.append(item)
    _need(0 < len(touching) <= MAX_TRACKS, 'aggregate_cap_Ground_unique_linear_departure_required')
    adjacency = {}
    for track in touching:
        _need(track.GetLayer() == face and track.GetWidth() == width
            and force._uid(track) not in grouped and not track.HasSolderMask() and not track.IsLocked(),
            'aggregate_cap_Ground_exact_class_ungrouped_departure_required')
        for point in (tuple(track.GetStart()), tuple(track.GetEnd())):
            adjacency.setdefault(point, []).append(track)
    terminals = [point for point, edges in adjacency.items() if len(edges) == 1]
    roots = [point for point in terminals if pad.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*point), 0)]
    _need(len(terminals) == 2 and len(roots) == 1 and len(adjacency) == len(touching)+1
        and all(len(edges) <= 2 for edges in adjacency.values()),
        'aggregate_cap_Ground_unique_interior_root_endpoint_required')
    points = [roots[0]]; chosen = []; length = 0.; current = adjacency[roots[0]][0]
    contacts = []; ledger = []
    while True:
        _tick(deadline); uid = force._uid(current)
        _need(current.GetClass() == 'PCB_TRACK' and current.GetLayer() == face
            and current.GetWidth() == width and uid not in grouped and uid not in chosen
            and not current.HasSolderMask() and not current.IsLocked(),
            'aggregate_cap_Ground_nonuniform_grouped_locked_or_cyclic_leaf')
        ends = [tuple(current.GetStart()), tuple(current.GetEnd())]
        _need(points[-1] in ends and ends[0] != ends[1], 'aggregate_cap_Ground_endpoint_linear_leaf_required')
        far = ends[1] if ends[0] == points[-1] else ends[0]
        chosen.append(uid); points.append(far); length += current.GetLength()/1e6
        _need(len(chosen) <= MAX_TRACKS and length <= MAX_LENGTH_MM, 'aggregate_cap_Ground_leaf_work_bound')
        contacts = []
        for item in same_face:
            _tick(deadline); other = force._uid(item)
            if other in chosen or other == root: continue
            area = _contact(current, item, face, holes, deadline)
            if area is None: continue
            _need(item.GetNetCode() == pad.GetNetCode(), 'aggregate_cap_Ground_foreign_leaf_contact:'+uid+':'+other)
            _need(area.Collide(pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*far), pcbnew.VECTOR2I(*far), width), 0),
                'aggregate_cap_Ground_unowned_interior_contact:'+uid+':'+other)
            contacts.append(item); ledger.append(dict(edge_uuid=uid, contact_uuid=other,
                actual_lower_contact_nm2=area.Area(), actual_lower_contact=area.Format()))
        if (len(contacts) != 1 or contacts[0].GetClass() != 'PCB_TRACK'
                or contacts[0].GetLayer() != face or contacts[0].GetWidth() != width
                or force._uid(contacts[0]) in grouped or contacts[0].HasSolderMask()
                or far not in (tuple(contacts[0].GetStart()), tuple(contacts[0].GetEnd()))):
            _need(contacts, 'aggregate_cap_Ground_fixed_native_boundary_missing')
            break
        current = contacts[0]
    _need(set(force._uid(t) for t in touching) <= set(chosen),
        'aggregate_cap_Ground_disconnected_root_departures')
    boundaries = sorted({_record(i, face)['uuid']: _record(i, face) for i in contacts}.values(), key=lambda x:x['uuid'])
    return dict(track_uuids=chosen, points_nm=[list(p) for p in points], source_length_mm=length,
        source_boundary_entry_nm=[list(p) for p in points[-2:]],
        boundary_uuids=[i['uuid'] for i in boundaries], retained_boundary_contacts=boundaries,
        actual_contact_ledger=ledger, source_edges=[_record(items[u], face) for u in chosen])


def plan(board, pad_uuid, *, board_hint, reference_group_uuid=None, timeout_s=10.):
    """Rederive literal canonical additional-cap identity, current and leaf."""
    import cec_source_aggregate_capacitor_cell as cap
    _need(type(timeout_s) in (int,float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10.,
        'bounded_aggregate_cap_Ground_leaf_required')
    deadline = time.monotonic()+timeout_s
    _need(type(board_hint) is str and board_hint, 'aggregate_cap_Ground_named_Source_required')
    source = Path(board.GetFileName()).resolve(strict=True); project = source.with_suffix('.kicad_pro')
    _need(source.suffix == '.kicad_pcb' and project.is_file(), 'aggregate_cap_Ground_literal_saved_project_required')
    epoch = force._code_identity(); family = force._family(source, board_hint); binding = row._source_binding(board)
    _need(row._source_binding(pcbnew.LoadBoard(str(source))) == binding,
        'aggregate_cap_Ground_literal_unchanged_Source_required')
    pads = [p for f in board.GetFootprints() for p in f.Pads() if force._uid(p) == pad_uuid]
    _need(len(pads) == 1 and pads[0].GetNetname() == 'GND', 'aggregate_cap_Ground_unique_literal_Ground_pad_required')
    pad = pads[0]; fp = pad.GetParentFootprint()
    cap._owner(board, force._uid(fp), reference_group_uuid, source)
    reference = None
    if reference_group_uuid is not None:
        reference, = cap.maps.inspect_many(source, [(force._uid(fp), reference_group_uuid)],
            timeout_s=max(.001, deadline-time.monotonic()))
    canonical = cap._canonical(board, fp, board_hint, deadline)
    assignments = cap._unassigned(board, fp, board_hint)
    positive = next(p for p in fp.Pads() if p.GetNetname() != 'GND')
    _need(cap.supply_role.supply_terminal_role(positive) == 'value_qualified_grounded_ceramic_supply_terminal',
        'aggregate_cap_Ground_positive_additional_cap_role_required')
    graph = cap.fr._read_only_route_connectivity(board)
    _need(not {force._uid(i) for i in graph.GetConnectedItems(positive)}-{force._uid(positive)},
        'aggregate_cap_Ground_additional_supply_must_be_isolated')
    kind, domain, contract = cap.full._model(board, source, positive.GetNetname(), board_hint)
    _need(kind == 'aggregate_source_sink' and domain and domain.get('complete') is True
        and domain.get('source_refs') and domain.get('sink_refs') and fp.GetReference() not in domain['source_refs'],
        'aggregate_cap_Ground_complete_full_rail_Source_required')
    with force._thermal_hint(board_hint): current = cap.cells._supply_current_widths(board, positive.GetNetname())
    _need(current is not None and current['current_authority'] == contract['current_authority'],
        'aggregate_cap_Ground_unchanged_full_rail_current_required')
    face = int(pad.GetLayerSet().CuStack()[0]); spec = NetclassTable.from_board_path(source).resolve('GND') or {}
    authored = spec.get('track_width'); perface = (spec.get('track_width_by_layer_mm') or {}).get(fab.COPPER_LAYER_IDS[face], 0.)
    _need(type(authored) in (int,float) and math.isfinite(authored) and authored > 0
        and type(perface) in (int,float) and math.isfinite(perface) and perface >= 0,
        'aggregate_cap_Ground_positive_saved_class_required')
    width = max(int(board.GetDesignSettings().m_TrackMinWidth), math.ceil(authored*1e6), math.ceil(perface*1e6))
    _need(0 < width <= 20000000, 'aggregate_cap_Ground_bounded_saved_class_required')
    walked = _walk(board, pad, width, face, deadline)
    all_items = _objects(board)
    proof = _wire(dict(schema=1, scope=SCOPE, role='Source_additional_aggregate_capacitor_Ground_leaf',
        source=str(source), source_sha256=force._hash(source), source_family=family, code_identity=epoch,
        source_native_binding=binding, canonical_source=canonical,
        source_reference_map=reference,
        unchanged_selected_bypass_assignments=assignments, aggregate_domain=domain,
        aggregate_contract=contract, current_contract=current, footprint_uuid=force._uid(fp),
        pad_uuid=pad_uuid, owner=fp.GetReference(), pin=pad.GetNumber(), net='GND', layer=face,
        width_nm=width, source_ground_class_authority=dict(source=str(source), project=str(project),
            project_sha256=force._hash(project), width_nm=width, layer_id=face,
            basis='literal_saved_source_ground_class', current_authority=False), **walked,
        retained_barrel_uuids=sorted(u for u,i in all_items.items() if i.GetClass() == 'PCB_VIA'),
        every_retained_boundary_and_Source_partition_mandatory=True,
        native_partition_receiving_required=True, maximum_new_Ground_return_mm=.8,
        no_selected_bypass_alias=True, current_authority=False, Ground_current_or_ampacity_credit=False,
        new_barrel_authority=False, release_authority=False))
    _need(binding == row._source_binding(board) and epoch == force._code_identity()
        and family == force._family(source, board_hint), 'aggregate_cap_Ground_Source_epoch_changed')
    _tick(deadline)
    return proof


def retained_contacts_unchanged(parent, child, proof):
    """Necessary exact-object check only; not partition/return receiving."""
    face = proof['layer']; items = _objects(child)
    _need(all(q['uuid'] in items and _record(items[q['uuid']], face) == q
        for q in proof['retained_boundary_contacts']), 'aggregate_cap_Ground_retained_boundary_changed')
    _need(set(proof['retained_barrel_uuids']) <= items.keys(), 'aggregate_cap_Ground_retained_barrel_missing')


def single_edge_ownerships(parent, proposal, track_uuids, *, deadline):
    """Fresh distinct edge labels for compiler integration, never a waiver."""
    import cec_additional_aggregate_macro as aggregate
    _need(type(deadline) in (int,float) and math.isfinite(deadline)
        and time.monotonic() < deadline <= time.monotonic()+10., 'aggregate_cap_Ground_inherited_lease_required')
    _need(type(proposal) is dict and proposal.get('source_native_binding') == row._source_binding(parent)
        and proposal.get('scope') == 'source_typed_complete_cell_escape_proposal',
        'aggregate_cap_Ground_complete_fresh_macro_required')
    ids = list(track_uuids)
    _need(0 < len(ids) <= MAX_TRACKS and len(set(ids)) == len(ids), 'aggregate_cap_Ground_unique_edge_scope_required')
    fresh = aggregate.collect(parent, proposal['poses'], board_hint=proposal['board_hint'],
        reference_group_uuids=proposal.get('reference_group_uuids', ()),
        excluded_refs=proposal.get('additional_aggregate_excluded_refs', ()),
        **({k: proposal[k] for k in ('allow_linear_power_stage_reconstruction', 'allow_owned_locked_escapes')
            if k in proposal}),
        timeout_s=max(.001, deadline-time.monotonic()))
    _need(fresh and _wire(fresh) == _wire(proposal.get('additional_aggregate_capacitors')),
        'aggregate_cap_Ground_fresh_additional_role_required')
    leaves = [p['source_Ground_leaf'] for p in fresh.values() if p.get('source_Ground_leaf')
        and p['source_Ground_leaf'].get('scope') == SCOPE]
    scopes = {uid:p for p in leaves for uid in p['track_uuids']}
    _need(set(ids) <= scopes.keys(), 'aggregate_cap_Ground_only_exact_owned_leaf_edges')
    live = _objects(parent); rows = []
    for uid in ids:
        _tick(deadline); proof = scopes[uid]; edge = live[uid]
        authority = dict(kind=KIND, native_source_uuid=uid, source_width_nm=edge.GetWidth(),
            source_full_class_width_nm=proof['width_nm'], source_aggregate_cap_Ground_leaf=proof,
            source_Ground_root=dict(pad_uuid=proof['pad_uuid'], footprint_uuid=proof['footprint_uuid'],
                ref=proof['owner'], pin=proof['pin'], net='GND', role='additional_aggregate_capacitor_Ground',
                current_authority=False, selected_bypass=False),
            every_retained_boundary_and_Source_partition_mandatory=True,
            current_authority=False, Ground_current_or_ampacity_credit=False,
            new_barrel_authority=False, release_authority=False)
        rows.append(dict(change=dict(uuid=uid, net='GND', source_nm=[list(edge.GetStart()), list(edge.GetEnd())]),
            authority=_wire(authority)))
    return rows


def source_root_label(root):
    """Structural additional-cap root label, not fresh Source authority."""
    try:
        return (type(root) is dict and root['net'] == 'GND'
            and root['role'] == 'additional_aggregate_capacitor_Ground'
            and root['current_authority'] is False and root['selected_bypass'] is False
            and all(type(root[k]) is str and bool(root[k])
                for k in ('pad_uuid','footprint_uuid','ref','pin')))
    except (KeyError,TypeError): return False


def authority_label(authority):
    """Structural receiving dispatch only; callers must freshly rederive."""
    try:
        p = authority['source_aggregate_cap_Ground_leaf']; root = authority['source_Ground_root']
        return (authority['kind'] == KIND and p['scope'] == SCOPE and p['schema'] == 1
            and p['net'] == 'GND' and type(p['track_uuids']) is list
            and 0 < len(p['track_uuids']) <= MAX_TRACKS
            and len(set(p['track_uuids'])) == len(p['track_uuids'])
            and authority['native_source_uuid'] in p['track_uuids']
            and type(p['width_nm']) is int and 0 < p['width_nm'] <= 20000000
            and authority['source_width_nm'] == authority['source_full_class_width_nm'] == p['width_nm']
            and root['pad_uuid'] == p['pad_uuid'] and root['footprint_uuid'] == p['footprint_uuid']
            and root['ref'] == p['owner'] and root['pin'] == p['pin'] and source_root_label(root)
            and type(p['boundary_uuids']) is list and bool(p['boundary_uuids'])
            and p['native_partition_receiving_required'] is True
            and p['every_retained_boundary_and_Source_partition_mandatory'] is True
            and p['maximum_new_Ground_return_mm'] == .8 and p['no_selected_bypass_alias'] is True
            and all(p[k] is False for k in ('current_authority','Ground_current_or_ampacity_credit',
                'new_barrel_authority','release_authority'))
            and all(authority[k] is False for k in ('current_authority','Ground_current_or_ampacity_credit',
                'new_barrel_authority','release_authority'))
            and authority['every_retained_boundary_and_Source_partition_mandatory'] is True)
    except (KeyError,TypeError,ValueError): return False
