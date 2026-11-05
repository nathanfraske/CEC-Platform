"""Source-selected capacitor Ground body-contact ownership.

This is a narrow extension of the existing complete macro boundary typer,
not an alternate router or saved receiver. Canonical roles, exact native
material, full Source class and every retained control port are rederived.
No Ground load, role, width, cut, current or release waiver is granted.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_escape_replan as escape
import cec_cell_ground_cut_boundaries as boundaries
import cec_cell_macro_requests as macro
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_ground_return_preservation as returns
import cec_macro_cut_components as components
import cec_route_dimensions as dimensions
import cec_source_ground_leaf as canonical
import cec_source_netlist_semantics as semantic
import cec_source_sideband_monitor_tap as material


SCOPE = 'source_selected_cap_class_ground_multiport'
KIND = 'positive_existing_low_power_ground_boundary'  # existing adapter schema
MAX_EDGES = 64
MAX_ITEMS = 16384
MAX_CONTACT_CHECKS = 65536
MAX_EDGE_LENGTH_NM = 8000000
MAX_TOTAL_LENGTH_NM = 32000000


def _stable(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _need(ok, reason):
    if not ok:
        raise ValueError(reason)


def _tick(deadline):
    _need(time.monotonic() < deadline, 'selected_cap_ground_deadline')


def _lease(deadline):
    _need(type(deadline) in (int, float) and math.isfinite(deadline)
        and time.monotonic() < deadline <= time.monotonic() + 9.7,
        'selected_cap_ground_inherited_bounded_lease_required')


def _groups(board):
    return sorted([dict(uuid=force._uid(g), name=g.GetName(), locked=bool(g.IsLocked()),
        members=sorted(force._uid(i) for i in g.GetItems())) for g in board.Groups()],
        key=lambda g: g['uuid'])


def _reference_members(board):
    """Exact supported reference-map native members, not a UUID-only claim."""
    result = {}
    for group in board.Groups():
        for item in group.GetItems():
            kind = item.GetClass()
            if kind == 'FOOTPRINT':
                continue  # pads/pose/properties plus existing macro owner
            if kind == 'PCB_TEXT':
                q = (kind, item.GetText(), tuple(item.GetPosition()), int(item.GetLayer()),
                    item.IsLocked(), item.IsVisible(), item.IsMirrored(), tuple(item.GetTextSize()),
                    item.GetTextThickness(), item.GetTextAngle().AsDegrees(),
                    int(item.GetHorizJustify()), int(item.GetVertJustify()), item.IsBold(), item.IsItalic())
            elif kind == 'PCB_SHAPE' and item.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                q = (kind, tuple(item.GetStart()), tuple(item.GetEnd()), int(item.GetLayer()),
                    item.GetWidth(), item.IsLocked())
            elif kind in ('PCB_TRACK', 'PCB_VIA', 'PAD'):
                q = _item(board, item)
            else:
                raise ValueError('unsupported_retained_reference_group_member:' + kind)
            result[force._uid(item)] = _stable(q)
    return result


def _member_groups(board, item):
    return sorted(force._uid(g) for g in board.Groups() if g.ContainsItem(item))


def _item(board, item):
    kind = item.GetClass()
    q = dict(uuid=force._uid(item), kind=kind, net=item.GetNetname(),
        locked=bool(item.IsLocked()), groups=_member_groups(board, item))
    if kind == 'PCB_TRACK':
        q.update(start_nm=list(item.GetStart()), end_nm=list(item.GetEnd()),
            width_nm=item.GetWidth(), layer_id=int(item.GetLayer()),
            solder_mask=bool(item.HasSolderMask()))
    elif kind == 'PCB_VIA':
        q.update(at_nm=list(item.GetPosition()), drill_nm=item.GetDrillValue(),
            via_type=int(item.GetViaType()), top=int(item.TopLayer()), bottom=int(item.BottomLayer()),
            widths=[[int(l), item.GetWidth(l)] for l in board.GetEnabledLayers().CuStack()])
    elif kind == 'PAD':
        fp = item.GetParentFootprint()
        q.update(footprint_uuid=force._uid(fp), ref=fp.GetReference(), pin=item.GetNumber(),
            at_nm=list(item.GetPosition()), size_nm=list(item.GetSize()),
            drill_nm=list(item.GetDrillSize()), offset_nm=list(item.GetOffset()),
            shape=int(item.GetShape()), attribute=int(item.GetAttribute()),
            angle=item.GetOrientationDegrees(), layers=list(map(int, item.GetLayerSet().Seq())),
            polygons=[[int(l), item.GetEffectivePolygon(l, pcbnew.ERROR_INSIDE).Format()]
                for l in board.GetEnabledLayers().CuStack() if item.IsOnLayer(l)],
            owner_value=fp.GetValue(), owner_package=fp.GetFPIDAsString(),
            owner_properties=canonical.footprint_properties(fp), owner_locked=bool(fp.IsLocked()),
            owner_groups=_member_groups(board, fp), owner_path=fp.GetPath().AsString())
    else:
        raise ValueError('unsupported_selected_cap_ground_native_port:' + kind)
    return _stable(q)


def _items(board):
    found = [p for fp in board.GetFootprints() for p in fp.Pads()] + list(board.GetTracks())
    _need(len(found) <= MAX_ITEMS, 'selected_cap_ground_native_inventory_bound')
    result = {force._uid(i): i for i in found}
    _need(len(result) == len(found), 'selected_cap_ground_unique_native_identity_required')
    return result


def _positive_contact(board, first, second, face, deadline):
    """A lower material intersection, excluding every actual local drill.

    Native pad/track polygons alone contain the material drilled by a third
    object. Do not allow that invisible copper to authorize a Source cut.
    No area/clearance tolerance, rasterization or bounding-box positive proof.
    """
    _tick(deadline)
    area = material._copper(first, face)
    area.BooleanIntersection(material._copper(second, face))
    if not area.OutlineCount():
        return 0
    for item in _items(board).values():
        _tick(deadline)
        if (not item.IsOnLayer(face) or not (item.GetClass() == 'PCB_VIA'
                or item.GetClass() == 'PAD' and item.HasHole())):
            continue
        actual_hole = item.GetEffectiveHoleShape()
        if not area.BBox().Intersects(actual_hole.BBox()):
            continue  # disjoint native bounds are negative-only acceleration
        hole = pcbnew.SHAPE_POLY_SET()
        actual_hole.TransformToPolygon(hole, 1, pcbnew.ERROR_OUTSIDE)
        area.BooleanSubtract(hole)
        if not area.OutlineCount():
            return 0
    return area.Area()


def _source_context(parent, proposal, deadline):
    """No caller's role/current dictionaries are treated as authority."""
    _tick(deadline)
    _need(type(proposal) is dict and proposal.get('scope') == 'source_typed_complete_cell_escape_proposal'
        and proposal.get('source_native_binding') == row._source_binding(parent),
        'fresh_complete_source_macro_context_required')
    # Use the same independently recompiled ownership INPUTS as the outer
    # macro. A nested observer must not drop a positive additional-cap reach
    # or stage option and then misdiagnose a valid Source frame as unknown.
    # This forwards no role, current, cut or constructor proof as authority.
    fresh = escape.recompile_source_proposal(parent, proposal)
    # Extra macro cuts are attached later; these original typed inputs cannot
    # change. The entire fresh original is bound in the returned certificate.
    keys = ('source_native_binding', 'poses', 'device_contracts', 'selected_bypasses',
        'stationary_device_owners', 'reference_group_uuids', 'max_shift_mm', 'board_hint')
    _need(all(fresh.get(k) == proposal.get(k) for k in keys), 'forged_selected_cap_source_roles')
    source = Path(parent.GetFileName()).resolve(strict=True)
    saved = pcbnew.LoadBoard(str(source))
    _need(row._source_binding(saved) == row._source_binding(parent)
        and _groups(saved) == _groups(parent)
        and _reference_members(saved) == _reference_members(parent),
        'saved_exact_source_native_context_required')
    live, disk = _items(parent), _items(saved)
    _need(live.keys() == disk.keys() and all(_item(parent, v) == _item(saved, disk[u])
        for u, v in live.items()), 'source_native_geometry_differs_from_saved_family')
    root = canonical.source_nc._root(parent, proposal['board_hint'])
    _need(root is not None,'canonical_selected_cap_Source_root_required')
    root = root.resolve(strict=True)
    files, hashes, instances = canonical._hierarchy(root, deadline)
    tree, exporter = canonical._export(root, deadline)
    comps, _, node_net = canonical._tables(tree)
    identities = {}
    def identity(ref):
        if ref not in identities:
            identities[ref] = canonical._identity(parent, ref, comps, instances, deadline)
        return identities[ref]
    caps = {}; owners = {}; currents = {}
    _need(bool(fresh['selected_bypasses']), 'actual_source_selected_cap_required')
    for ref, assignment in sorted(fresh['selected_bypasses'].items()):
        _tick(deadline)
        cap = identity(ref); fp = cap[0]
        _need(canonical._ceramic(fp) and len(list(fp.Pads())) == 2,
            'fresh_canonical_two_land_ceramic_required')
        owner_ref = assignment['owner']; owner = identity(owner_ref); op = owner[0]
        _need(owner_ref in fresh['stationary_device_owners'],
            'fixed_source_owner_required_for_control_boundary')
        model = roles.footprint_contract(op)
        _need(model is not None and model == fresh['device_contracts'].get(owner_ref)
            and {p.GetNumber() for p in op.Pads()} == set(model['pins']),
            'fresh_complete_manufacturer_owner_contract_required')
        roles.physical_pinmap(op, model, board_hint=proposal['board_hint'])
        _need(model['pins'].get(assignment['pin']) in ('power_input', 'power_output'),
            'selected_cap_actual_supply_owner_required')
        for p in op.Pads():
            _need(node_net.get((owner_ref, p.GetNumber())) == p.GetNetname(),
                'canonical_owner_native_pin_net_mismatch')
        roots = [p for p in fp.Pads() if p.GetNetname() == 'GND']
        _need(len(roots) == 1 and {p.GetNetname() for p in fp.Pads()} == {'GND', assignment['rail']},
            'literal_selected_cap_supply_and_ground_required')
        for p in fp.Pads():
            _need(node_net.get((ref, p.GetNumber())) == p.GetNetname()
                and canonical._pin(cap, p.GetNumber())['type'] == 'passive',
                'canonical_cap_passive_pin_net_required')
        rail = assignment['rail']
        if rail not in currents:
            kind, domain, contract = full._model(parent, source, rail, proposal['board_hint'])
            authority = contract.get('current_authority', {})
            _need(kind in ('aggregate_source_sink', 'explicit_all_terminal_distributed_supply')
                and type(authority.get('amps')) in (int, float)
                and math.isfinite(authority['amps']) and authority['amps'] > 0
                and authority.get('source') and contract.get('required_by_layer_mm'),
                'known_unchanged_full_source_rail_current_required')
            currents[rail] = _stable(dict(kind=kind, domain=domain, contract=contract))
        caps[force._uid(roots[0])] = dict(ref=ref, owner=owner_ref, rail=rail,
            pad_uuid=force._uid(roots[0]), assignment=assignment,
            symbol_uuid=cap[3]['uuid'], full_rail_current=currents[rail])
        owners[owner_ref] = (owner, model)
    context = dict(source=str(source), source_sha256=force._hash(source),
        family=force._family(source, proposal['board_hint']), code=force._code_identity(),
        fresh_macro_digest=_digest(fresh), groups=_groups(parent),
        reference_members=_reference_members(parent), canonical_root=str(root),
        schematic_files_sha256=hashes,
        exporter=semantic.replay_identity(dict(exporter=exporter))['exporter'], selected_caps=caps,
        unchanged_full_rail_currents=currents)
    _tick(deadline)
    return context, owners, node_net, files


def _ownership_scopes(parent, proposal, scopes, *, deadline):
    """One fresh read-only canonical/native frame, independent cut scopes.

    The caller cannot supply a context or cache. Each result retains the
    singleton port/retirement semantics and original unchanged-input fences.
    Every lookup is bounded by the one inherited deadline; no lease reset.
    """
    _lease(deadline)
    _need(type(scopes) in (list, tuple) and 1 <= len(scopes) <= MAX_EDGES,
          'bounded_selected_cap_ownership_scopes_required')
    for track_uuids in scopes:
        _need(type(track_uuids) in (list, tuple) and 1 <= len(track_uuids) <= MAX_EDGES
            and len(set(track_uuids)) == len(track_uuids), 'bounded_unique_selected_cap_edges_required')
    initial = row._source_binding(parent)
    context, owners, node_net, files = _source_context(parent, proposal, deadline)
    source = Path(context['source']); live = _items(parent)
    project = dimensions.project_path(source)
    _need(project is not None, 'saved_source_ground_class_required')
    spec = macro.fr._project_netclass_resolver(str(source), board=parent)('GND') or {}
    authored = spec.get('track_width')
    _need(type(authored) in (int, float) and math.isfinite(authored) and authored > 0,
        'saved_source_ground_class_required')
    results=[]
    for track_uuids in scopes:
        selected=set(track_uuids)
        _need(selected <= live.keys(), 'actual_selected_cap_source_edges_required')
        rows = []; checks = 0; total = 0
        for uid in sorted(selected):
            _tick(deadline); edge = live[uid]; face = int(edge.GetLayer())
            _need(edge.GetClass() == 'PCB_TRACK' and edge.GetNetname() == 'GND'
                and face in (pcbnew.F_Cu, pcbnew.B_Cu) and not edge.IsLocked()
                and not edge.HasSolderMask() and not _member_groups(parent, edge),
                'unlocked_ungrouped_actual_ground_surface_edge_required')
            layer_name = macro.fab.COPPER_LAYER_IDS[face]
            per_face = (spec.get('track_width_by_layer_mm') or {}).get(layer_name, 0.)
            _need(type(per_face) in (int, float) and math.isfinite(per_face) and per_face >= 0,
                'saved_source_ground_class_required')
            floor = max(int(parent.GetDesignSettings().m_TrackMinWidth),
                math.ceil(authored * 1e6), math.ceil(per_face * 1e6))
            # This path does not acquire an existing narrower endpoint exception.
            _need(edge.GetWidth() == floor, 'literal_full_source_ground_class_only')
            length = edge.GetLength(); total += length
            _need(0 < length <= MAX_EDGE_LENGTH_NM and total <= MAX_TOTAL_LENGTH_NM,
                'bounded_selected_cap_ground_local_edges_required')
            roots = []; ports = []
            for other_uid, obj in sorted(live.items()):
                _tick(deadline)
                if other_uid == uid or not obj.IsOnLayer(face) or not obj.GetBoundingBox().Intersects(edge.GetBoundingBox()):
                    continue
                checks += 1
                _need(checks <= MAX_CONTACT_CHECKS, 'selected_cap_ground_contact_work_bound')
                if not edge.GetEffectiveShape(face).Collide(obj.GetEffectiveShape(face), 0):
                    continue
                _need(obj.GetNetname() == 'GND', 'selected_cap_boundary_foreign_copper_contact')
                overlap = _positive_contact(parent, edge, obj, face, deadline)
                # A zero-area/tangent contact is not invented into a positive root.
                _need(overlap > 0, 'selected_cap_boundary_positive_material_contact_required')
                port = dict(item=_item(parent, obj), contact_area_nm2=overlap,
                    immutable_retained=other_uid not in selected)
                if obj.GetClass() == 'PAD':
                    _need(not obj.HasHole() and obj.GetAttribute() == pcbnew.PAD_ATTRIB_SMD,
                        'selected_cap_boundary_surface_land_required')
                    lower = material._copper(obj, face)
                    _need(lower.OutlineCount() == 1 and lower.HoleCount(0) == 0,
                        'single_connected_source_surface_land_required')
                    if other_uid in context['selected_caps']:
                        proof = dict(context['selected_caps'][other_uid], role='source_selected_bypass_ground')
                        roots.append(dict(proof, positive_native_body_contact=True,
                            endpoint_inside=[bool(obj.HitTest(p, 0)) for p in (edge.GetStart(), edge.GetEnd())]))
                        port['role'] = 'source_selected_bypass_ground'
                    else:
                        ref = obj.GetParentFootprint().GetReference(); pin = obj.GetNumber()
                        _need(ref in owners, 'selected_cap_boundary_unowned_fixed_land')
                        identity, model = owners[ref]
                        role = model['pins'].get(pin)
                        _need(role == 'control' and node_net.get((ref, pin)) == 'GND'
                            and canonical._pin(identity, pin)['type'] in ('input', 'bidirectional', 'passive'),
                            'fixed_canonical_control_ground_tie_required')
                        port.update(role='control', primary_manufacturer_role='control',
                            source_symbol_uuid=identity[3]['uuid'], manufacturer_source=model['source'],
                            control_remains_control=True, functional_ground_return=False,
                            supplies_cut_or_ground_current_authority=False)
                if other_uid not in selected:
                    ports.append(port)
            _need(roots, 'each_new_owned_edge_requires_actual_selected_cap_contact')
            # Existing zones/graphics are not silently absorbed as mesh ownership.
            for zone in parent.Zones():
                _tick(deadline)
                if zone.IsOnLayer(face) and not zone.GetIsRuleArea():
                    _need(zone.IsFilled(), 'selected_cap_boundary_zone_geometry_unknown')
                    _need(not edge.GetEffectiveShape(face).Collide(zone.GetFilledPolysList(face), 0),
                        'selected_cap_boundary_filled_zone_cut_unsupported')
            for drawing in [*parent.GetDrawings(), *(g for fp in parent.GetFootprints() for g in fp.GraphicalItems())]:
                if drawing.IsOnLayer(face):
                    _need(not drawing.GetBoundingBox().Intersects(edge.GetBoundingBox()),
                        'selected_cap_boundary_copper_graphic_scope_unknown')
            proof = dict(kind=KIND, native_source_uuid=uid, source_pad_roots=roots,
                source_owned_barrel_roots=[], source_width_nm=edge.GetWidth(),
                source_full_class_width_nm=floor, source_class_project=str(project.resolve()),
                source_class_project_sha256=force._hash(project),
                source_class_geometry_origin='fresh_saved_source_project',
                source_selected_cap_multiport_scope=SCOPE, exact_retained_ports=ports,
                source_width_preserved_not_aggregate_ground_injection_rating=True,
                every_source_partition_and_physical_return_still_requires_receiving=True,
                ground_control_straps_not_retired_or_used_as_width_authority=True,
                current_authority=False, routing_admitted=False, release_authority=False)
            rows.append(dict(change=dict(uuid=uid, net='GND',
                source_nm=[list(edge.GetStart()), list(edge.GetEnd())]), authority=proof))
        _need(initial == row._source_binding(parent), 'selected_cap_ground_source_changed')
        _need(context['family'] == force._family(source, proposal['board_hint'])
            and context['code'] == force._code_identity()
            and context['schematic_files_sha256'] == {str(p): force._hash(p) for p in files},
            'selected_cap_ground_source_family_or_code_changed')
        _tick(deadline)
        # One compact common binding avoids copying the entire code map per edge.
        results.append(_stable(dict(scope=SCOPE, context=context, extras=rows,
            retired_track_uuids=sorted(selected), contact_checks=checks,
            ownership_only=True, scope_complete=True, routing_admitted=False,
            current_authority=False, release_authority=False)))
    return results


def ownership(parent, proposal, track_uuids, *, deadline):
    """Original one union-cut proof; no representation or port change."""
    return _ownership_scopes(parent,proposal,[track_uuids],deadline=deadline)[0]


def single_edge_ownerships(parent, proposal, track_uuids, *, deadline):
    """Independent singleton proofs sharing only a fresh read-only frame."""
    _need(type(track_uuids) in (list,tuple) and 1 <= len(track_uuids) <= MAX_EDGES
        and len(set(track_uuids)) == len(track_uuids),'bounded_unique_selected_cap_edges_required')
    proofs=_ownership_scopes(parent,proposal,[[uid]for uid in track_uuids],deadline=deadline)
    return [proof['extras'][0]for proof in proofs]
