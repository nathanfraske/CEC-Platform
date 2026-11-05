"""Observe an exact Source RC input node and bounded internal surface spans.

This module constructs/removes nothing. Identity and native ownership are NOT
retirement, current, Kelvin, timing, fabrication or route admission authority.
A future saved receiver must recompile this observer and receive its entire
literal cut/additions and absolute affected measurement evidence independently.
"""
import json
import math
import re
import time
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as row
import cec_current_topology as topology
import cec_device_power_roles as roles
import cec_force_bypass_terminals as capacitors
import cec_force_current as force
import cec_fr as fr
import cec_pair_semantics as pairs
import cec_quiet_signal_requests as source_pins
import cec_sense_topology as lineage
import cec_source_ground_leaf as source_roles
import cec_source_netlist_semantics as semantic
import cec_source_no_connect as source_nc
import cec_source_reference_group_transport as annotation


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _tick(deadline):
    _require(time.monotonic() < deadline, 'measurement_filter_span_deadline')


def _source_context(board, source, hint, refs, expected_nets, deadline):
    """Fresh canonical source/embedded pins, not native value/name guesses."""
    root = source_nc._root(board, hint)
    _require(root is not None, 'measurement_filter_canonical_root_required')
    root = Path(root).resolve()
    _, hashes, instances = source_roles._hierarchy(root, deadline)
    tree, exporter = source_roles._export(root, deadline)
    comps, nets, node_net = source_roles._tables(tree)
    identities = {ref: source_roles._identity(board, ref, comps, instances, deadline) for ref in sorted(refs)}
    # Series/capacitor identity includes BOTH land assignments; an intact
    # post-filter pin must not hide a changed anchor-facing resistor land.
    for ref, identity in identities.items():
        if roles.footprint_contract(identity[0]) is None:
            for pad in identity[0].Pads():
                _require(node_net.get((ref, pad.GetNumber())) == pad.GetNetname(),
                         'measurement_filter_source_passive_land_assignment_changed')
    pins = {}
    for net, expected in expected_nets.items():
        _require(nets.get(net) == expected, 'measurement_filter_exact_canonical_net_required')
        for ref, number in sorted(expected):
            _require(node_net.get((ref, number)) == net, 'measurement_filter_source_pin_net_changed')
            pin = source_pins._source_pin(identities[ref], number, deadline)
            pad = identities[ref][0].FindPadByNumber(number)
            _require(pad is not None and pad.GetPinType() in ('', pin['type']),
                     'measurement_filter_native_source_pin_type_contradiction')
            pins[ref, number] = pin
    return dict(root_schematic=str(root), schematic_files_sha256=hashes, exporter=exporter), pins


def _resistor(fp):
    pads = list(fp.Pads())
    _require(re.search(r'(?:^|[-_])Resistor_SMD$', str(fp.GetFPID().GetLibNickname()))
             and len(pads) == 2 and len({p.GetNumber() for p in pads}) == 2,
             'measurement_filter_typed_series_resistor_required')
    value = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\s*([kKM]?)\s*(?:Ω|[rR]|[oO][hH][mM][sS]?)?', fp.GetValue().strip())
    _require(value is not None, 'measurement_filter_positive_declared_resistance_required')
    ohms = float(value[1]) * {'': 1., 'k': 1e3, 'K': 1e3, 'M': 1e6}[value[2]]
    _require(math.isfinite(ohms) and ohms > 0, 'measurement_filter_positive_declared_resistance_required')
    return ohms


def plan(board, source, *, board_hint, pad_uuid, span_uuid,
         expected_source_sha256, timeout_s=10.):
    """Return Source-bound ownership OBSERVATION, or raise on any unknown.

    ``pad_uuid`` is a manufacturer measurement input; ``span_uuid`` must be
    strictly internal to its complete three-land post-resistor RC node.
    F-only is deliberate. No callback/caller capability dictionary is trusted.
    """
    _require(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10
        and type(board_hint) is str and bool(board_hint)
        and all(type(v) is str and bool(v) for v in (pad_uuid, span_uuid))
        and type(expected_source_sha256) is str and re.fullmatch('[0-9a-f]{64}', expected_source_sha256),
        'bounded_named_measurement_filter_source_required')
    started = time.monotonic(); deadline = started + timeout_s
    source = Path(source).resolve(strict=True)
    _require(source.suffix == '.kicad_pcb' and Path(board.GetFileName()).resolve() == source
        and force._hash(source) == expected_source_sha256, 'measurement_filter_source_epoch_mismatch')
    binding = row._source_binding(board); family = force._family(source, board_hint); code = force._code_identity()
    saved = pcbnew.LoadBoard(str(source))
    _require(saved is not None and row._source_binding(saved) == binding,
             'measurement_filter_saved_native_source_mismatch')
    all_pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    _require(len(all_pads) <= 16384, 'measurement_filter_pad_inventory_bound')
    roots = [p for p in all_pads if force._uid(p) == pad_uuid]
    _require(len(roots) == 1, 'measurement_filter_unique_source_input_required')
    root = roots[0]; owner = root.GetParentFootprint(); model = roles.footprint_contract(owner)
    pair = pairs.footprint_input_contract(owner)
    _require(model is not None and pair is not None and not owner.IsDNP()
        and model['pins'].get(root.GetNumber()) == 'measurement' and root.GetNumber() in pair[1],
        'measurement_filter_manufacturer_input_pair_required')
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    _require(len(fps) == len(list(board.GetFootprints())), 'measurement_filter_unique_native_references_required')
    with force._thermal_hint(board_hint):
        domains = topology.board_current_domains(board, board_hint)
        declared_pairs = fr._board_kelvin_pairs(board)
        anchors = {ref for d in domains.values() if d.get('complete') is True for ref in d.get('authority_refs', ())}
        evidence = lineage.board_evidence(board, anchor_pairs=declared_pairs, anchor_refs=anchors)
    selected = [r for r in evidence['details'] if r['ref'] == owner.GetReference()]
    _require(len(selected) == 1 and selected[0].get('ok') is True
        and selected[0]['selected']['kind'] == 'filtered', 'measurement_filter_authoritative_filtered_lineage_required')
    selected = selected[0]; paths = selected['selected']
    _require(all(len(paths[k]['series']) == 1 for k in ('p', 'n')),
             'measurement_filter_one_disjoint_series_resistor_per_leg_required')
    for leg in ('p', 'n'):
        domain = domains.get(paths[leg]['anchor_net'], {})
        _require(domain.get('complete') is True and domain.get('source_refs') and domain.get('sink_refs')
            and paths['anchor_ref'] in domain.get('authority_refs', ()),
            'measurement_filter_complete_current_anchor_authority_required')
    input_nets = selected['input_nets']; leg_index = selected['pins'].index(root.GetNumber())
    net = input_nets[leg_index]; other_net = input_nets[1-leg_index]
    _require(root.GetNetname() == net and net not in domains and other_net not in domains,
             'measurement_filter_input_node_is_not_current_domain')
    cap_proof = capacitors.select(board, net, return_nets=[other_net], max_pads=8)
    _require(len(cap_proof['capacitors']) == 1, 'measurement_filter_unique_differential_capacitor_required')
    cap_info = cap_proof['capacitors'][0]; cap = fps[cap_info['ref']]
    series = {leg: fps[paths[leg]['series'][0]['ref']] for leg in ('p', 'n')}
    resistances = {leg: _resistor(fp) for leg, fp in series.items()}
    _require(series['p'] is not series['n'], 'measurement_filter_disjoint_series_parts_required')
    step = paths['p' if leg_index == 0 else 'n']['series'][0]
    resistor_land = series['p' if leg_index == 0 else 'n'].FindPadByNumber(step['input_pad'])
    cap_land = next(p for p in cap.Pads() if force._uid(p) == cap_info['pad_uuid'])
    expected_pads = {force._uid(root), force._uid(resistor_land), force._uid(cap_land)}
    native_pads = [p for p in all_pads if p.GetNetname() == net]
    _require(len(native_pads) == 3 and {force._uid(p) for p in native_pads} == expected_pads,
             'measurement_filter_exact_three_native_lands_required')
    expected_nets = {}
    for index, leg in enumerate(('p', 'n')):
        s = paths[leg]['series'][0]
        cap_pad = next(p for p in cap.Pads() if p.GetNetname() == input_nets[index])
        expected_nets[input_nets[index]] = {(owner.GetReference(), selected['pins'][index]),
            (s['ref'], s['input_pad']), (cap.GetReference(), cap_pad.GetNumber())}
        native_members = [(p.GetParentFootprint().GetReference(), p.GetNumber())
            for p in all_pads if p.GetNetname() == input_nets[index]]
        _require(len(native_members) == 3 and set(native_members) == expected_nets[input_nets[index]],
                 'measurement_filter_both_input_nodes_exact_three_native_lands_required')
    refs = {owner.GetReference(), cap.GetReference(), *(fp.GetReference() for fp in series.values())}
    source_context, source_pin = _source_context(board, source, board_hint, refs, expected_nets, deadline)
    for index, leg in enumerate(('p', 'n')):
        _require(source_pin[owner.GetReference(), selected['pins'][index]]['type'] == 'input',
                 'measurement_filter_source_manufacturer_input_type_required')
        for ref, number in expected_nets[input_nets[index]] - {(owner.GetReference(), selected['pins'][index])}:
            _require(source_pin[ref, number]['type'] == 'passive', 'measurement_filter_source_passive_type_required')
    _tick(deadline)
    material = [t for t in board.GetTracks() if t.GetNetname() == net]
    _require(3 <= len(material) <= 64 and not any(z.GetNetname() == net and not z.GetIsRuleArea() for z in board.Zones()),
             'measurement_filter_bounded_surface_node_without_zones_required')
    items = [*native_pads, *material]
    _require(len({force._uid(i) for i in items}) == len(items), 'measurement_filter_unique_material_identities_required')
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    fixed_parents = []
    for fp in {force._uid(p.GetParentFootprint()): p.GetParentFootprint() for p in native_pads}.values():
        if fp.GetParentGroup() is None:
            continue
        parents = [g for g in board.Groups() if any(force._uid(i) == force._uid(fp) for i in g.GetItems())]
        _require(len(parents) == 1, 'measurement_filter_exact_fixed_annotation_parent_required')
        fixed_parents.append((force._uid(fp), force._uid(parents[0])))
    fixed_annotations = (annotation.inspect_many(source, sorted(fixed_parents),
        timeout_s=min(10., max(.001, deadline-time.monotonic()))) if fixed_parents else [])
    resolver = fr._project_netclass_resolver(str(source), board=board); spec = resolver(net) or {}
    width_floor = max(int(board.GetDesignSettings().m_TrackMinWidth), math.ceil(float(spec.get('track_width') or 0)*1e6))
    # This observer creates no factory exception or new geometry. Bind the
    # actual saved board/project floor; the ordinary native item resolver
    # below independently adds its effective class/local clearance.
    gap = max(int(board.GetDesignSettings().m_MinClearance), math.ceil(float(spec.get('clearance') or 0)*1e6))
    _require(width_floor > 0 and spec.get('track_width') and spec.get('clearance'),
             'measurement_filter_positive_authored_dimensions_required')
    for item in items:
        _tick(deadline)
        _require(force._uid(item) not in grouped and item.GetParentGroup() is None,
                 'measurement_filter_grouped_source_material_refused')
        if item.GetClass() == 'PAD':
            _require(not item.GetParentFootprint().IsDNP()
                and item.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not item.HasHole()
                and tuple(map(int, item.GetLayerSet().CuStack())) == (int(pcbnew.F_Cu),),
                'measurement_filter_populated_front_surface_lands_required')
        else:
            _require(item.GetClass() == 'PCB_TRACK' and int(item.GetLayer()) == int(pcbnew.F_Cu)
                and not item.HasSolderMask() and width_floor <= item.GetWidth() <= 350000,
                'measurement_filter_ordinary_authored_front_track_required')
    graph = pcbnew.CONNECTIVITY_DATA()
    for item in items:
        _tick(deadline); _require(graph.Add(item), 'measurement_filter_native_graph_refused')
    reached = {pad_uuid} | {force._uid(i) for i in graph.GetConnectedItems(root)}
    _require(reached == {force._uid(i) for i in items}, 'measurement_filter_complete_native_node_required')
    spans = [t for t in material if force._uid(t) == span_uuid]
    _require(len(spans) == 1, 'measurement_filter_exact_source_internal_span_required')
    span = spans[0]; ends = [tuple(span.GetStart()), tuple(span.GetEnd())]
    item_gap = int(fr._foreign_clearance_resolver(board)(span, pcbnew.F_Cu))
    gap = max(gap, item_gap)
    _require(gap > 0, 'measurement_filter_positive_source_clearance_required')
    dx, dy = abs(ends[0][0]-ends[1][0]), abs(ends[0][1]-ends[1][1])
    _require(ends[0] != ends[1] and (dx == 0 or dy == 0 or dx == dy) and span.GetLength() <= 8000000,
             'measurement_filter_bounded_canonical_internal_span_required')
    contacts = {p: [] for p in ends}
    for item in items:
        if item is span or force._uid(item) == span_uuid:
            continue
        _tick(deadline)
        if not item.GetEffectiveShape(pcbnew.F_Cu).Collide(span.GetEffectiveShape(pcbnew.F_Cu), 0):
            continue
        _require(item.GetClass() == 'PCB_TRACK', 'measurement_filter_span_touches_terminal_not_internal')
        shared = set(ends) & {tuple(item.GetStart()), tuple(item.GetEnd())}
        _require(len(shared) == 1, 'measurement_filter_span_has_unowned_interior_contact')
        point = next(iter(shared))
        span_far = next(p for p in ends if p != point)
        peer_far = next(p for p in (tuple(item.GetStart()), tuple(item.GetEnd())) if p != point)
        _require(sum((span_far[i]-point[i])*(peer_far[i]-point[i]) for i in (0,1)) <= 0,
                 'measurement_filter_retained_endcap_points_into_source_span')
        contacts[point].append(force._uid(item))
    _require(all(len(v) == 1 for v in contacts.values())
        and len({v[0] for v in contacts.values()}) == 2, 'measurement_filter_two_exact_retained_endcaps_required')
    # Unknown native-source annotations must not disappear through SWIG.
    _, nodes = additive._nodes(source)
    for item in material:
        node = nodes.get(force._uid(item))
        _require(type(node) is list and node and node[0] == 'segment'
            and all(type(n) is list and n and n[0] in ('start', 'end', 'width', 'layer', 'net', 'uuid', 'locked')
                    for n in node[1:]), 'measurement_filter_unknown_source_track_metadata')
    _require(fr._tap_foreign_clear(board, span.GetStart(), span.GetEnd(), span.GetWidth(),
        pcbnew.F_Cu, gap, {span.GetNetCode()}), 'measurement_filter_source_span_clearance_unknown_or_refused')
    result = dict(schema=1, scope='source_rc_filter_internal_span_observation', complete=True,
        source=str(source), source_sha256=expected_source_sha256, source_native_binding=binding,
        source_context=source_context, manufacturer=model, lineage=selected, capacitor=cap_info,
        fixed_annotation_parents=fixed_annotations,
        fixed_annotation_groups_and_all_member_literal_bytes_must_survive_saved_receiving=True,
        declared_series_resistance_ohms=resistances, node_net=net,
        node_pad_uuids=sorted(expected_pads), node_track_uuids=sorted(force._uid(t) for t in material),
        input_pad_uuid=pad_uuid, internal_span_uuid=span_uuid, layer=int(pcbnew.F_Cu),
        source_points_nm=[list(p) for p in ends], source_width_nm=int(span.GetWidth()), clearance_nm=gap,
        clearance_basis=dict(board_minimum_nm=int(board.GetDesignSettings().m_MinClearance),
            project_netclass_nm=math.ceil(float(spec['clearance'])*1e6), native_item_effective_nm=item_gap),
        retained_endcaps=[dict(at_nm=list(p), native_uuid=contacts[p][0]) for p in ends],
        family=family, code_identity=code, retirement_authority=False, current_authority=False,
        kelvin_qualified=False, route_admission=False, release_authority=False,
        saved_independent_source_cut_additions_and_absolute_measurement_receiving_required=True)
    _tick(deadline)
    _require(binding == row._source_binding(board) and family == force._family(source, board_hint)
        and code == force._code_identity() and force._hash(source) == expected_source_sha256
        and all(force._hash(Path(p)) == h for p, h in source_context['schematic_files_sha256'].items())
        and force._hash(Path(source_context['exporter']['exporter'])) == source_context['exporter']['exporter_sha256'],
        'measurement_filter_source_family_code_or_export_changed')
    # Require semantic identity too; a hand-authored raw export digest is not enough.
    semantic.replay_identity(dict(exporter=source_context['exporter']))
    _tick(deadline)
    result['elapsed_s'] = time.monotonic()-started
    return result


def _elbow_polygon(item, outside=False):
    polygon = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(polygon, pcbnew.F_Cu, 0, 1,
        pcbnew.ERROR_OUTSIDE if outside else pcbnew.ERROR_INSIDE, False)
    return polygon


def _elbow_intersection(a, b, outside=False):
    polygon = _elbow_polygon(a, outside)
    polygon.BooleanIntersection(_elbow_polygon(b, outside))
    return polygon


def _elbow_positive(polygon):
    area = polygon.Area()
    return polygon.OutlineCount() > 0 and math.isfinite(area) and area > 0


def _elbow_contours(polygon, deadline):
    """Literal integer contours, not an area/bounding-box contact surrogate."""
    count = 0
    def ring(chain):
        nonlocal count
        _tick(deadline)
        size = chain.PointCount(); count += size
        _require(3 <= size and count <= 16384, 'measurement_filter_elbow_contour_bound')
        points = [tuple(map(int, chain.CPoint(i))) for i in range(size)]
        if points[-1] == points[0]:
            points.pop()
        _require(len(points) >= 3, 'measurement_filter_elbow_contour_unknown')
        variants = []
        for direction in (points, list(reversed(points))):
            first = min(range(len(direction)), key=direction.__getitem__)
            variants.append(direction[first:]+direction[:first])
        return [list(p) for p in min(variants)]
    result = [dict(outline_nm=ring(polygon.COutline(i)),
        holes_nm=sorted(ring(polygon.CHole(i, j)) for j in range(polygon.HoleCount(i))))
        for i in range(polygon.OutlineCount())]
    _tick(deadline)
    return sorted(result, key=lambda value: json.dumps(value, sort_keys=True))


def _elbow_endpoint_in_cap(track, endpoint, point):
    # This is ONLY a retained endpoint-chain locator. Actual contact authority
    # below is the independently recorded native lower/upper intersection.
    cap = pcbnew.PCB_TRACK(track.GetBoard())
    cap.SetStart(pcbnew.VECTOR2I(*endpoint)); cap.SetEnd(pcbnew.VECTOR2I(*endpoint))
    cap.SetWidth(track.GetWidth()); cap.SetLayer(pcbnew.F_Cu)
    return _elbow_polygon(cap).Contains(pcbnew.VECTOR2I(*point))


def plan_elbow(board, source, *, board_hint, pad_uuid, span_uuids,
               expected_source_sha256, timeout_s=10.):
    """Observe one complete three-edge RC elbow with redundant native caps.

    This explicit API does not widen ``plan``. The caller supplies exactly
    three identities, never contact/role/width claims. Its middle edge must
    independently pass the existing complete canonical RC-node observer.
    No Source cut or new route is admitted by either observer.
    """
    _require(type(timeout_s) in (int, float) and math.isfinite(timeout_s) and 0 < timeout_s <= 10
        and type(board_hint) is str and bool(board_hint) and type(pad_uuid) is str and bool(pad_uuid)
        and type(span_uuids) in (list, tuple) and len(span_uuids) == 3
        and all(type(uid) is str and re.fullmatch(
            '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', uid) for uid in span_uuids)
        and len(set(span_uuids)) == 3 and type(expected_source_sha256) is str
        and re.fullmatch('[0-9a-f]{64}', expected_source_sha256),
        'bounded_named_measurement_filter_elbow_source_required')
    started = time.monotonic(); deadline = started+timeout_s
    source = Path(source).resolve(strict=True)
    _require(source.suffix == '.kicad_pcb' and Path(board.GetFileName()).resolve() == source
        and force._hash(source) == expected_source_sha256, 'measurement_filter_source_epoch_mismatch')
    selected = [t for t in board.GetTracks() if force._uid(t) in set(span_uuids)]
    _require(len(selected) == 3 and all(t.GetClass() == 'PCB_TRACK' for t in selected),
             'measurement_filter_elbow_exact_three_source_tracks_required')
    ends = {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd())) for t in selected}
    members = {}
    for uid, points in ends.items():
        for point in points:
            members.setdefault(point, []).append(uid)
    _require(len(members) == 4 and sorted(map(len, members.values())) == [1, 1, 2, 2],
             'measurement_filter_elbow_endpoint_chain_required')
    middle = [t for t in selected if all(len(members[p]) == 2 for p in ends[force._uid(t)])]
    _require(len(middle) == 1, 'measurement_filter_elbow_unique_middle_required')
    middle = middle[0]; middle_uid = force._uid(middle)
    points = [min(p for p, ids in members.items() if len(ids) == 1)]; ordered = []
    for unused in range(3):
        choices = [uid for uid in members[points[-1]] if uid not in ordered]
        _require(len(choices) == 1, 'measurement_filter_elbow_endpoint_chain_required')
        uid = choices[0]; ordered.append(uid)
        points.append(next(p for p in ends[uid] if p != points[-1]))
    by_uid = {force._uid(t): t for t in selected}; cuts = [by_uid[uid] for uid in ordered]
    vectors = [tuple(b[i]-a[i] for i in (0, 1)) for a, b in zip(points, points[1:])]
    canonical = lambda v: v != (0, 0) and (v[0] == 0 or v[1] == 0 or abs(v[0]) == abs(v[1]))
    dot = lambda a, b: sum(a[i]*b[i] for i in (0, 1))
    cross = lambda a, b: a[0]*b[1]-a[1]*b[0]
    process = lambda t: (t.GetNetCode(), int(t.GetLayer()), int(t.GetWidth()), bool(t.IsLocked()), bool(t.HasSolderMask()))
    _require(ordered[1] == middle_uid and all(canonical(v) for v in vectors)
        and cross(vectors[0], vectors[2]) == 0 and dot(vectors[0], vectors[2]) > 0
        and dot(vectors[0], vectors[1]) == 0
        and middle.GetLength() < min(cuts[0].GetLength(), cuts[2].GetLength())
        and sum(t.GetLength() for t in cuts) <= 8000000
        and len({process(t) for t in cuts}) == 1,
        'measurement_filter_elbow_bounded_canonical_equal_process_required')
    _tick(deadline)
    observation = plan(board, source, board_hint=board_hint, pad_uuid=pad_uuid,
        span_uuid=middle_uid, expected_source_sha256=expected_source_sha256,
        timeout_s=deadline-time.monotonic())
    _tick(deadline)
    _require({r['native_uuid'] for r in observation['retained_endcaps']} == {ordered[0], ordered[2]},
             'measurement_filter_elbow_middle_has_other_contacts')
    overlap = _elbow_intersection(cuts[0], cuts[2])
    upper_overlap = _elbow_intersection(cuts[0], cuts[2], True)
    unsupported = _elbow_intersection(cuts[0], cuts[2], True)
    unsupported.BooleanSubtract(_elbow_polygon(middle))
    union = pcbnew.SHAPE_POLY_SET()
    for cut in cuts:
        union.BooleanAdd(_elbow_polygon(cut))
    _require(_elbow_positive(overlap) and unsupported.OutlineCount() == 0
        and union.OutlineCount() == 1 and union.HoleCount(0) == 0,
        'measurement_filter_elbow_redundant_cap_contact_required')
    node_ids = set(observation['node_pad_uuids']+observation['node_track_uuids'])
    items = [p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p) in node_ids]
    items += [t for t in board.GetTracks() if force._uid(t) in node_ids]
    retained = [item for item in items if force._uid(item) not in ordered]
    _, nodes = additive._nodes(source)
    ports = []; all_contacts = set()
    for cut, at, inward in ((cuts[0], points[0], vectors[0]),
                            (cuts[2], points[-1], tuple(-v for v in vectors[-1]))):
        _tick(deadline)
        touched = [item for item in retained
            if item.GetEffectiveShape(pcbnew.F_Cu).Collide(cut.GetEffectiveShape(pcbnew.F_Cu), 0)]
        _require(1 <= len(touched) <= 2 and all(t.GetClass() == 'PCB_TRACK' for t in touched),
                 'measurement_filter_elbow_bounded_internal_port_contacts_required')
        seeds = [t for t in touched if at in (tuple(t.GetStart()), tuple(t.GetEnd()))]
        _require(len(seeds) == 1, 'measurement_filter_elbow_one_exact_endpoint_seed_required')
        seed = seeds[0]; seed_ends = (tuple(seed.GetStart()), tuple(seed.GetEnd()))
        _require(seed_ends[0] != seed_ends[1], 'measurement_filter_elbow_nonzero_retained_seed_required')
        joint = next(p for p in seed_ends if p != at)
        _require(dot(tuple(joint[i]-at[i] for i in (0, 1)), inward) <= 0,
                 'measurement_filter_elbow_retained_contact_points_into_cut')
        contacts = []
        for peer in touched:
            _tick(deadline)
            peer_uid = force._uid(peer)
            if peer_uid != force._uid(seed):
                peer_ends = (tuple(peer.GetStart()), tuple(peer.GetEnd()))
                _require(peer_ends[0] != peer_ends[1] and joint in peer_ends
                    and _elbow_endpoint_in_cap(cut, at, joint),
                         'measurement_filter_elbow_unowned_interior_contact')
                peer_far = next(p for p in peer_ends if p != joint)
                _require(dot(tuple(peer_far[i]-joint[i] for i in (0, 1)), inward) <= 0,
                         'measurement_filter_elbow_retained_contact_points_into_cut')
                at_joint = {force._uid(t) for t in retained if t.GetClass() == 'PCB_TRACK'
                    and joint in (tuple(t.GetStart()), tuple(t.GetEnd()))}
                _require(at_joint == {force._uid(seed), peer_uid}
                    and _elbow_positive(_elbow_intersection(seed, peer)),
                    'measurement_filter_elbow_retained_endpoint_branch_refused')
            lower = _elbow_intersection(cut, peer); upper = _elbow_intersection(cut, peer, True)
            _require(_elbow_positive(lower), 'measurement_filter_elbow_positive_port_contact_required')
            contacts.append(dict(native_uuid=peer_uid,
                source_node=nodes[peer_uid], width_nm=int(peer.GetWidth()),
                layer=int(peer.GetLayer()), locked=bool(peer.IsLocked()),
                lower_contours=_elbow_contours(lower, deadline), upper_contours=_elbow_contours(upper, deadline)))
            all_contacts.add(peer_uid)
        ports.append(dict(at_nm=list(at), seed_uuid=force._uid(seed),
            contacts=sorted(contacts, key=lambda entry: entry['native_uuid'])))
    # Every contact is physical, including tangent/unknown contacts: none can
    # disappear merely because an inside polygon has zero measured area.
    actual_contacts = {force._uid(item) for item in retained for cut in cuts
        if item.GetEffectiveShape(pcbnew.F_Cu).Collide(cut.GetEffectiveShape(pcbnew.F_Cu), 0)}
    _require(actual_contacts == all_contacts and len({p['seed_uuid'] for p in ports}) == 2,
             'measurement_filter_elbow_extra_source_contact_refused')
    graph = pcbnew.CONNECTIVITY_DATA()
    for item in retained:
        _tick(deadline); _require(graph.Add(item), 'measurement_filter_native_graph_refused')
    lookup = {force._uid(item): item for item in retained}; components = []
    for port in ports:
        seed = lookup[port['seed_uuid']]
        component = {force._uid(seed)} | {force._uid(item) for item in graph.GetConnectedItems(seed)}
        _require({r['native_uuid'] for r in port['contacts']} <= component
            and bool(component & set(observation['node_pad_uuids'])),
            'measurement_filter_elbow_real_external_terminal_required')
        components.append(component)
    _require(not components[0] & components[1] and set.union(*components) == set(lookup),
             'measurement_filter_elbow_exact_two_retained_components_required')
    native_gaps = {force._uid(t): int(fr._foreign_clearance_resolver(board)(t, pcbnew.F_Cu)) for t in cuts}
    gap = max(observation['clearance_nm'], *native_gaps.values())
    for cut in cuts:
        _tick(deadline)
        _require(fr._tap_foreign_clear(board, cut.GetStart(), cut.GetEnd(), cut.GetWidth(),
            pcbnew.F_Cu, gap, {cut.GetNetCode()}),
            'measurement_filter_source_span_clearance_unknown_or_refused')
    result = dict(schema=1, scope='source_rc_filter_internal_elbow_observation', complete=True,
        Source_node_observation=observation, source=str(source), source_sha256=expected_source_sha256,
        input_pad_uuid=pad_uuid, internal_span_uuids=ordered, middle_span_uuid=middle_uid,
        source_points_nm=[list(p) for p in points], source_width_nm=observation['source_width_nm'],
        clearance_nm=gap, cut_native_item_clearance_nm=native_gaps, layer=int(pcbnew.F_Cu),
        source_cut_nodes={uid: nodes[uid] for uid in ordered},
        source_cut_processes=[dict(uuid=force._uid(t), width_nm=int(t.GetWidth()),
            layer=int(t.GetLayer()), locked=bool(t.IsLocked()), net=t.GetNetname()) for t in cuts],
        retained_ports=ports, retained_components=[sorted(c) for c in components],
        retained_terminal_uuids=[sorted(c & set(observation['node_pad_uuids'])) for c in components],
        redundant_contact=dict(lower_contours=_elbow_contours(overlap, deadline),
            upper_contours=_elbow_contours(upper_overlap, deadline), upper_minus_middle_lower_empty=True),
        retirement_authority=False, current_authority=False, kelvin_qualified=False,
        route_admission=False, release_authority=False,
        saved_independent_source_cut_additions_and_absolute_measurement_receiving_required=True)
    context = observation['source_context']
    _require(observation['source_native_binding'] == row._source_binding(board)
        and observation['family'] == force._family(source, board_hint)
        and observation['code_identity'] == force._code_identity()
        and force._hash(source) == expected_source_sha256
        and all(force._hash(Path(p)) == h for p, h in context['schematic_files_sha256'].items())
        and force._hash(Path(context['exporter']['exporter'])) == context['exporter']['exporter_sha256'],
        'measurement_filter_source_family_code_or_export_changed')
    semantic.replay_identity(dict(exporter=context['exporter']))
    _tick(deadline)
    result['elapsed_s'] = time.monotonic()-started
    return result
