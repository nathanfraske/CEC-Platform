"""Source-declared minimum conductor geometry for one additive auxiliary limb.

This is NOT a consumer/load allocation or a whole-net current exception.  The
unchanged aggregate contract remains authoritative for every old conductor.
One explicit board-policy endpoint pair can own one new nonbranching chain.
Its minimum trace geometry is reported separately; pads, vias and connector
barrels supply connectivity only, never ampacity, thermal or transient proof.
"""
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
import math
import os
from pathlib import Path
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_board_policy as policy
import cec_cell_row_rebuild as row
import cec_current_topology as topology
import cec_fab_profile as fab
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_kelvin_copper_cut as cut
import cec_native_supply_via_context as web
import cec_route_dimensions as dimensions
import cec_route_quality as craft
import cec_source_ground_leaf as canonical
import cec_source_no_connect as source_root
from cec_footprint_fields import footprint_properties


POLICY_KEY = 'auxiliary_attachment_requirements'
SCOPE = 'explicit_auxiliary_attachment_minimum_conductor_geometry_only'
RECEIVE_STAGES = ('geometry', 'source_sense_audit', 'candidate_sense_audit', 'sense_comparison')


def _left(deadline):
    left = deadline-time.monotonic()
    if left <= 0:
        raise ValueError('auxiliary_attachment_deadline')
    return min(10., left)


def _deadline(timeout_s):
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10:
        raise ValueError('bounded_auxiliary_attachment_receiving_required')
    return time.monotonic()+timeout_s


class _ReceiveStages:
    """Four finite constituents, no retries or unbounded shared remainder."""
    def __init__(self, result, timeout_s):
        first_deadline = _deadline(timeout_s)
        self.timeout = float(timeout_s)
        self.started = first_deadline-self.timeout
        self.deadline = self.started+len(RECEIVE_STAGES)*self.timeout
        self.rows = result['stages']
        self.failed = False
        result['budget'] = dict(constituent_timeout_s=self.timeout,
            constituent_limit=len(RECEIVE_STAGES), aggregate_timeout_s=len(RECEIVE_STAGES)*self.timeout,
            maximum_aggregate_timeout_s=40., retries=0,
            deadline_kind='cooperative_native_item_bounded')

    @contextmanager
    def stage(self, name):
        if self.failed or len(self.rows) >= len(RECEIVE_STAGES) or name != RECEIVE_STAGES[len(self.rows)]:
            raise ValueError('auxiliary_finite_receiving_stage_order_required')
        started = time.monotonic()
        deadline = min(started+self.timeout, self.deadline)
        # Float subtraction across an exponent boundary can report a few
        # ulps more than the declared lease. Bound only this duration report;
        # the actual deadline and both independent _left checks are unchanged.
        record = dict(name=name, complete=False, elapsed_s=None, error=None,
            lease_s=min(self.timeout, max(0., deadline-started)))
        self.rows.append(record)
        try:
            _left(deadline)
            yield deadline
            _left(deadline)
            record['complete'] = True
        except Exception as exc:
            self.failed = True
            record['error'] = type(exc).__name__+':'+str(exc)
            raise
        finally:
            record['elapsed_s'] = time.monotonic()-started


def _text(value):
    return type(value) is str and 0 < len(value) <= 1024 and value == value.strip()


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _hint(value):
    override = os.environ.get('CEC_THERMAL_BOARD_HINT')
    if override:
        declared, active = policy.policy_path(value), policy.policy_path(override)
        if declared and active and Path(declared).resolve() != Path(active).resolve():
            raise ValueError('auxiliary_current_policy_identity_conflict')
        return override
    return value


def _declaration(board, attachment_id, hint):
    if not _text(attachment_id) or not _text(hint):
        raise ValueError('explicit_auxiliary_attachment_and_board_identity_required')
    rows = policy.load(board.GetFileName(), board_hint=hint, required=True).get('params', {}).get(POLICY_KEY, [])
    if type(rows) is not list or not 1 <= len(rows) <= 16:
        raise ValueError('bounded_existing_auxiliary_attachment_declarations_required')
    keys = {'id', 'net', 'attached_terminal', 'tap_terminal', 'minimum_continuous_amps', 'basis'}
    endpoints = {'ref', 'pin', 'mpn', 'footprint'}
    identities = set()
    for spec in rows:
        if (type(spec) is not dict or set(spec) != keys
                or any(not _text(spec[k]) for k in ('id', 'net', 'basis'))
                or not _positive(spec['minimum_continuous_amps'])):
            raise ValueError('exact_auxiliary_minimum_conductor_declaration_required')
        for name in ('attached_terminal', 'tap_terminal'):
            end = spec[name]
            if type(end) is not dict or set(end) != endpoints or any(not _text(v) for v in end.values()):
                raise ValueError('exact_selected_auxiliary_endpoint_required')
        pair = tuple((spec[n]['ref'], spec[n]['pin']) for n in ('attached_terminal', 'tap_terminal'))
        if pair[0] == pair[1] or (spec['net'], frozenset(pair)) in identities:
            raise ValueError('distinct_unique_auxiliary_attachment_pair_required')
        identities.add((spec['net'], frozenset(pair)))
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('duplicate_auxiliary_attachment_identity')
    found = [r for r in rows if r['id'] == attachment_id]
    if len(found) != 1:
        raise ValueError('existing_selected_auxiliary_attachment_required')
    return deepcopy(found[0])


def _pads(board, spec):
    result = {}
    for name in ('attached_terminal', 'tap_terminal'):
        end = spec[name]
        owners = [f for f in board.GetFootprints() if f.GetReference() == end['ref']]
        if len(owners) != 1:
            raise ValueError('unique_auxiliary_selected_component_required')
        fp = owners[0]
        if (fp.IsDNP() or footprint_properties(fp).get('MPN') != end['mpn']
                or fp.GetFPIDAsString() != end['footprint']):
            raise ValueError('auxiliary_selected_part_or_population_mismatch')
        pads = [p for p in fp.Pads() if str(p.GetNumber()) == end['pin']]
        if (len(pads) != 1 or pads[0].GetNetname() != spec['net'] or pads[0].GetNetCode() <= 0
                or pads[0].GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_PTH)):
            raise ValueError('unique_actual_auxiliary_pin_and_net_required')
        result[name] = pads[0]
    attached = result['attached_terminal']
    if attached.HasHole() or attached.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
        raise ValueError('initial_auxiliary_attachment_requires_single_smd_source_land')
    return result


def _canonical(board, spec, deadline):
    root = source_root._root(board, spec['_hint'])
    if root is None:
        raise ValueError('current_auxiliary_source_schematic_required')
    root = root.resolve()
    _, hashes, instances = canonical._hierarchy(root, deadline)
    tree, exporter = canonical._export(root, deadline)
    comps, _, node_net = canonical._tables(tree)
    witnesses = {}
    for name in ('attached_terminal', 'tap_terminal'):
        end = spec[name]
        ident = canonical._identity(board, end['ref'], comps, instances, deadline)
        pin = canonical._pin(ident, end['pin'])
        # Every actual terminal of BOTH selected parts keeps its source net.
        # The diode or connector is not reclassified as a modeled consumer.
        for p in ident[0].Pads():
            if node_net.get((end['ref'], p.GetNumber()), '') != p.GetNetname():
                raise ValueError('auxiliary_selected_component_source_pin_parity_mismatch')
        if node_net.get((end['ref'], end['pin'])) != spec['net']:
            raise ValueError('auxiliary_source_endpoint_net_mismatch')
        witnesses[name] = dict(symbol_uuid=ident[3]['uuid'], source=str(ident[1]),
            pin_type=pin['type'], selected_part=end)
    if any(force._hash(Path(p)) != digest for p, digest in hashes.items()):
        raise ValueError('auxiliary_schematic_changed_during_export')
    return dict(root=str(root), schematic_files_sha256=hashes, endpoints=witnesses,
                fresh_export=exporter)


def _intent(board, attachment_id, hint, deadline):
    spec = _declaration(board, attachment_id, hint)
    pads = _pads(board, spec)
    _left(deadline)
    with force._thermal_hint(hint):
        domains = topology.board_current_domains(board, hint)
        aggregate = topology.current_contract_for_net(spec['net'], hint, domains)
    domain = domains.get(spec['net'])
    if (not domain or domain.get('complete') is not True or domain.get('missing_refs')
            or not aggregate or aggregate.get('source') != 'board_design_basis'
            or not _positive(aggregate.get('amps')) or not _positive(aggregate.get('geometry_margin'))
            or aggregate['geometry_margin'] < 1 or type(aggregate.get('margin_included')) is not bool
            or aggregate['margin_included'] and aggregate['geometry_margin'] != 1):
        raise ValueError('unchanged_complete_aggregate_current_and_margin_required')
    if spec['minimum_continuous_amps'] > aggregate['amps']:
        raise ValueError('auxiliary_minimum_exceeds_existing_aggregate_design_basis')
    if pads['attached_terminal'].GetParentFootprint().GetReference() in domain['authority_refs']:
        raise ValueError('aggregate_current_terminal_cannot_be_reclassified_as_auxiliary')
    profile = fab.active_profile_name(board, hint=hint)
    if not profile or profile not in fab.PROFILES:
        raise ValueError('existing_auxiliary_copper_profile_required')
    project = dimensions.project_resolver(board.GetFileName(), board=board)(spec['net']) or {}
    if not all(_positive(project.get(k)) for k in ('track_width', 'clearance', 'via_diameter', 'via_drill')):
        raise ValueError('complete_source_auxiliary_netclass_dimensions_required')
    limits = dimensions.board_limits(board)
    current = dict(amps=spec['minimum_continuous_amps'], geometry_margin=aggregate['geometry_margin'],
        margin_included=aggregate['margin_included'], source='explicit_auxiliary_minimum_conductor_requirement')
    raw = dimensions.current_trace_widths(current, fab.enabled_copper_layers(board), profile, rise_c=30.)
    widths = {n: max(w, project['track_width'], limits['track_width']) for n, w in raw.items()}
    provenance = _canonical(board, dict(spec, _hint=hint), deadline)
    endpoints = {name: dict(force._pad_row(p), footprint_uuid=force._uid(p.GetParentFootprint()),
        net=p.GetNetname(), layers=list(map(int, p.GetLayerSet().CuStack())),
        drill_nm=list(p.GetDrillSize()), size_nm=list(p.GetSize())) for name, p in pads.items()}
    return dict(schema=1, scope=SCOPE, declaration=spec, net=spec['net'], endpoints=endpoints,
        aggregate_current_authority=deepcopy(aggregate), aggregate_domain=deepcopy(domain),
        minimum_conductor_authority=current, required_by_layer_mm=widths,
        clearance_mm=max(project['clearance'], board.GetDesignSettings().m_MinClearance/1e6), copper_profile=profile,
        ordinary_via_geometry_mm=list(dimensions.ordinary_via_geometry(project, limits)),
        rise_c=30., rise_basis='existing_shared_current_trace_model', source_schematic=provenance,
        load_current_inferred=False, branch_sharing_assumed=False, aggregate_budget_reduced=False,
        current_total_qualified=False, barrel_current_qualified=False, whole_fan_supply_qualified=False,
        thermal_or_transient_qualified=False, kelvin_qualified=False, release_authority=False)


def _material(board, net):
    pads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == net]
    items = [t for t in board.GetTracks() if t.GetNetname() == net]
    items += [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == net]
    if not 2 <= len(pads) <= 256 or len(pads)+len(items) > 4096:
        raise ValueError('auxiliary_native_material_inventory_bound')
    if (len({force._item_key(i) for i in [*pads, *items]}) != len(pads)+len(items)
            or len({force._uid(i) for i in [*pads, *items]}) != len(pads)+len(items)):
        raise ValueError('ambiguous_auxiliary_native_material_identity')
    return pads, items


def _source_topology(board, contract, *, _projected_omit=()):
    pads, items = _material(board, contract['net'])
    items = [i for i in items if force._uid(i) not in _projected_omit]
    graph, members = force._components(pads, items)
    ends = _pads(board, contract['declaration'])
    attached, tap = (force._item_key(ends[k]) for k in ('attached_terminal', 'tap_terminal'))
    isolated = [m for m in members if attached in m]
    if isolated != [{attached}]:
        raise ValueError('original_auxiliary_land_must_be_native_isolated_without_old_copper')
    trunk = [m for m in members if tap in m]
    authority = force._authority_pads(board, contract['net'], contract['aggregate_domain'])
    if len(trunk) != 1 or not authority or not {force._item_key(p) for p in authority} <= trunk[0]:
        raise ValueError('tap_must_contact_actual_complete_aggregate_terminal_component')
    return dict(original_native_partitions=graph['components'],
        original_isolated_material=[contract['endpoints']['attached_terminal']['uuid']],
        aggregate_native_terminals_connected=True,
        inherited_tap_and_aggregate_capacity_obligations_retained=True,
        inherited_supply_spur_and_barrel_rating_qualified=False)


def source_contract(board, attachment_id, *, board_hint, timeout_s=10.):
    """Recompile current policy, selected source schematic/export and native PCB.

    No caller current/margin/role parameter or success boolean is accepted.
    This API does not create a route, receipt group, policy or board mutation.
    """
    deadline = _deadline(timeout_s)
    board_hint = _hint(board_hint)
    path = Path(board.GetFileName()).resolve()
    family, epoch, binding = force._family(path, board_hint), force._code_identity(), row._source_binding(board)
    fresh = pcbnew.LoadBoard(str(path))
    if binding != row._source_binding(fresh):
        raise ValueError('auxiliary_exact_saved_source_board_required')
    # Rule/profile values come from saved bytes too, not caller-mutated native settings.
    result = _intent(fresh, attachment_id, board_hint, deadline)
    result['source_topology'] = _source_topology(fresh, result)
    _left(deadline)
    if (family != force._family(path, board_hint) or epoch != force._code_identity()
            or binding != row._source_binding(board) or not _bindings_stable(result)):
        raise ValueError('auxiliary_source_family_code_or_native_identity_changed')
    result.update(source_sha256=force._hash(path), source_family=family, code_identity=epoch,
                  board_mutated=False, identity_stable=True)
    return result


def _bindings_stable(contract):
    source = contract['source_schematic']
    files = dict(source['schematic_files_sha256'])
    exported = source['fresh_export']
    files[exported['exporter']] = exported['exporter_sha256']
    return all(force._hash(Path(path)) == digest for path, digest in files.items())


def _chain(board, contract, added, deadline):
    """Exact finite endpoint graph plus native physical contact exclusivity."""
    tracks = [t for t in added if t.GetClass() == 'PCB_TRACK']
    vias = [t for t in added if t.GetClass() == 'PCB_VIA']
    if not 1 <= len(tracks) <= 64 or len(vias) > 2 or len(tracks)+len(vias) != len(added):
        raise ValueError('bounded_auxiliary_tracks_and_endpoint_vias_only')
    ends = _pads(board, contract['declaration'])
    nodes = defaultdict(list); edge_nodes = {}
    for t in tracks:
        _left(deadline)
        layer = int(t.GetLayer()); name = fab.COPPER_LAYER_IDS.get(layer)
        if (layer not in (pcbnew.F_Cu, pcbnew.B_Cu) or t.GetNetname() != contract['net']
                or t.GetWidth() < math.ceil(contract['required_by_layer_mm'][name]*1e6)
                or t.GetLength() <= 0 or not craft.canonical_heading(tuple(t.GetStart()), tuple(t.GetEnd()))['ok']):
            raise ValueError('auxiliary_full_minimum_width_outer_canonical_track_required')
        edge_nodes[force._uid(t)] = [(layer, *t.GetStart()), (layer, *t.GetEnd())]
    if sum(t.GetLength() for t in tracks) > 40e6:
        raise ValueError('auxiliary_finite_chain_length_bound')
    for via in vias:
        matches = [p for p in ends.values() if tuple(p.GetPosition()) == tuple(via.GetPosition())
            and p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not p.HasHole()]
        # The ordinary geometry is a floor, not a preferred-size ceiling.
        # A wider actual landing may be needed for the unchanged full contact
        # web. Recompile the actual dimensions through the saved Source rules.
        actual = (int(via.GetWidth(pcbnew.F_Cu)), int(via.GetDrillValue()))
        project = dimensions.project_resolver(board.GetFileName(), board=board)(contract['net']) or {}
        diameter, drill = dimensions.ordinary_via_geometry(project, dimensions.board_limits(board),
            requested=tuple(n/1e6 for n in actual))
        if (len(matches) != 1 or via.GetNetname() != contract['net']
                or via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or int(via.TopLayer()) != pcbnew.F_Cu or int(via.BottomLayer()) != pcbnew.B_Cu
                or actual != (round(diameter*1e6), round(drill*1e6))
                or fab.via_pad_decision(board, matches[0], via.GetPosition(), round(diameter*1e6),
                    round(drill*1e6), via.GetNetCode())[0] is not True):
            raise ValueError('auxiliary_source_floor_contained_ordinary_endpoint_via_required')
        edge_nodes[force._uid(via)] = [(pcbnew.F_Cu, *via.GetPosition()), (pcbnew.B_Cu, *via.GetPosition())]
    for uid, vertices in edge_nodes.items():
        for vertex in vertices:
            nodes[vertex].append(uid)
    for name, pad in ends.items():
        available = [v for v in nodes if v[1:] == tuple(pad.GetPosition()) and pad.IsOnLayer(v[0])]
        if len(available) != 1:
            raise ValueError('one_exact_auxiliary_terminal_face_required')
        edge_nodes[name] = [available[0], (name,)]
        nodes[available[0]].append(name); nodes[(name,)].append(name)
    if any(len(edges) != (1 if len(vertex) == 1 else 2) for vertex, edges in nodes.items()):
        raise ValueError('auxiliary_chain_fork_cycle_or_unterminated_endpoint')
    seen = set(); todo = [('attached_terminal',)]
    while todo:
        _left(deadline); vertex = todo.pop()
        if vertex in seen: continue
        seen.add(vertex)
        for edge in nodes[vertex]: todo.extend(edge_nodes[edge])
    if seen != set(nodes):
        raise ValueError('auxiliary_chain_disconnected_or_extra_loop')
    return tracks, vias, ends, edge_nodes


def _routing_layers(tracks, ends):
    """Only actual chain faces, including its SMD endpoint contact faces.

    A nominal through span is not authorization for hypothetical inner-layer
    current. The independent web receiver still scans every enabled layer and
    refuses any contact outside this actual outer-face construction.
    """
    layers = {int(t.GetLayer()) for t in tracks}
    for pad in ends.values():
        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
            layers.update(map(int, pad.GetLayerSet().CuStack()))
    return sorted(fab.COPPER_LAYER_IDS[layer] for layer in layers)


def _contacts(parent, child, contract, added, edge_nodes, deadline, *, _projected_omit=()):
    old_pads, old_items = _material(parent, contract['net'])
    old_items = [i for i in old_items if force._uid(i) not in _projected_omit]
    ends = _pads(child, contract['declaration']); end_ids = {force._uid(p) for p in ends.values()}
    layers = tuple(map(int, child.GetEnabledLayers().CuStack()))
    work = cut._Work(deadline); cache = {}
    def shape(item, layer, upper):
        key = (force._item_key(item), layer, upper)
        if key not in cache:
            cache[key] = (cut._filled_shape(item, layer, upper, work)
                if item.GetClass() == 'ZONE' else cut._shape(item, layer, upper, work))
        return cache[key]
    contacts = 0
    for new in added:
        for old in [*old_pads, *old_items]:
            for layer in layers:
                _left(deadline)
                if not new.IsOnLayer(layer) or not old.IsOnLayer(layer): continue
                overlap = shape(new, layer, True).intersection(shape(old, layer, True))
                if overlap.is_empty: continue
                if force._uid(old) in end_ids:
                    contacts += 1; continue
                captures = [shape(p, layer, False) for p in ends.values() if p.IsOnLayer(layer)]
                if not any(overlap.difference(capture).is_empty for capture in captures):
                    raise ValueError('auxiliary_second_tap_or_old_copper_contact_outside_terminal')
    for i, first in enumerate(added):
        for second in added[i+1:]:
            if set(edge_nodes[force._uid(first)]) & set(edge_nodes[force._uid(second)]): continue
            for layer in layers:
                _left(deadline)
                if first.IsOnLayer(layer) and second.IsOnLayer(layer):
                    if not shape(first, layer, True).intersection(shape(second, layer, True)).is_empty:
                        raise ValueError('auxiliary_nonadjacent_copper_contact_or_loop')
    # Positive lower-envelope endpoint contact; a pad's drill is never copper.
    endpoint_proofs = {}
    for name, pad in ends.items():
        positive = []
        hole = cut._hole(pad, True, work) if pad.HasHole() else None
        for new in added:
            for layer in layers:
                if not new.IsOnLayer(layer) or not pad.IsOnLayer(layer): continue
                a, b = shape(new, layer, False), shape(pad, layer, False)
                if new.GetClass() == 'PCB_VIA': a = a.difference(cut._hole(new, True, work))
                if hole is not None: a, b = a.difference(hole), b.difference(hole)
                if a.intersection(b).area > 0: positive.append([force._uid(new), layer])
        if not positive:
            raise ValueError('auxiliary_positive_drill_subtracted_terminal_contact_required')
        endpoint_proofs[name] = positive
    return dict(physical_tap_count=1, all_old_material_contacts_inside_declared_terminal_regions=True,
                native_contact_observations=contacts, positive_endpoint_contacts=endpoint_proofs)


def receive(source, candidate, attachment_id, *, board_hint, timeout_s=10.):
    """Independent saved-parent/child minimum-chain receipt, not full admission.

    ``timeout_s`` is the (0, 10] second lease for EACH of four fixed stages:
    geometry, fresh Source audit, fresh child audit and exact comparison.
    The aggregate cap is four leases (at most 40 seconds), without retries.
    Raw audits remain in failure receipts; incomplete audits never qualify.
    Exact additive receiving replays GND fill. Whole native DRC, field, Ground
    return, current-debt and final transaction receiving remain mandatory.
    This result cannot itself replace those checks or alter their authority.
    """
    result = dict(schema=1, scope=SCOPE, ok=False, complete=False, errors=[],
        current_total_qualified=False, barrel_current_qualified=False, whole_fan_supply_qualified=False,
        kelvin_qualified=False, load_model_qualified=False, thermal_or_transient_qualified=False,
        release_authority=False, aggregate_budget_reduced=False,
        stages=[], sense_audits={}, identity_stable=False)
    stages = None
    try:
        stages = _ReceiveStages(result, timeout_s)
        with stages.stage('geometry') as deadline:
            board_hint = _hint(board_hint)
            source, candidate = [Path(p).resolve() for p in (source, candidate)]
            if source == candidate or source.samefile(candidate):
                raise ValueError('distinct_saved_auxiliary_candidate_required')
            families = [force._family(p, board_hint) for p in (source, candidate)]
            epoch = force._code_identity()
            parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
            native_bindings = [row._source_binding(b) for b in (parent, child)]
            before = _intent(parent, attachment_id, board_hint, deadline)
            after = _intent(child, attachment_id, board_hint, deadline)
            # CLI serialization timestamps are not an electrical source change.
            def semantics(value):
                out = deepcopy(value); out['source_schematic'].pop('fresh_export')
                return out
            if semantics(before) != semantics(after):
                raise ValueError('auxiliary_source_intent_current_profile_or_terminal_changed')
            result.update(contract=before, source_sha256=force._hash(source), candidate_sha256=force._hash(candidate),
                source_candidate_families=families, code_identity=epoch)
            result['source_topology'] = _source_topology(parent, before)
            result['additive'] = additive.receive(source, candidate, timeout_s=_left(deadline), board_hint=board_hint)
            if not result['additive']['ok'] or not result['additive']['complete']:
                raise ValueError('auxiliary_exact_source_plus_additions_receiving_refused')
            if force._sidecars(source) != force._sidecars(candidate):
                raise ValueError('auxiliary_complete_source_companion_family_must_remain_exact')
            _, old = additive._nodes(source); _, new = additive._nodes(candidate)
            incoming = set(new)-set(old)
            added = [t for t in child.GetTracks() if force._uid(t) in incoming]
            if len(added) != len(incoming):
                raise ValueError('auxiliary_only_new_native_tracks_and_vias_allowed')
            tracks, vias, ends, edge_nodes = _chain(child, before, added, deadline)
            nc = ends['attached_terminal'].GetNetCode(); gap = math.ceil(before['clearance_mm']*1e6)
            for track in tracks:
                _left(deadline)
                if (not fr._tap_foreign_clear(parent, track.GetStart(), track.GetEnd(), track.GetWidth(),
                        track.GetLayer(), gap, {nc}) or not fr._edge_leg_clear(parent,
                        track.GetStart(), track.GetEnd(), track.GetWidth()/2)):
                    raise ValueError('auxiliary_native_foreign_keepout_hole_or_edge_refusal')
            result['via_contact_webs'] = []
            for via in vias:
                if not fr._via_spot_clear(parent, via.GetPosition(), via.GetWidth(pcbnew.F_Cu), gap, {nc},
                        drill_nm=via.GetDrillValue(), net_code=nc):
                    raise ValueError('auxiliary_native_all_layer_via_clearance_refusal')
                proof = web.receive(child, force._uid(via), dict(net=before['net'],
                    current_authority=before['minimum_conductor_authority'],
                    required_by_layer_mm=before['required_by_layer_mm'],
                    routing_layers=_routing_layers(tracks, ends)), timeout_s=_left(deadline))
                if not proof['ok'] or not proof['complete']:
                    raise ValueError('auxiliary_actual_via_contact_web_below_minimum_geometry')
                result['via_contact_webs'].append(proof)
            result['contacts'] = _contacts(parent, child, before, added, edge_nodes, deadline)
            p, material = _material(parent, before['net'])
            original, _ = force._components(p, material)
            q, material = _material(child, before['net'])
            actual, _ = force._components(q, material)
            attached = before['endpoints']['attached_terminal']['uuid']; tap = before['endpoints']['tap_terminal']['uuid']
            def partition(graph, omit):
                return sorted(sorted(p['uuid'] for p in group if p['uuid'] not in omit)
                              for group in graph['components'] if any(p['uuid'] not in omit for p in group))
            if partition(original, {attached}) != partition(actual, {attached}):
                raise ValueError('auxiliary_changed_original_terminal_partition')
            if not any({attached, tap} <= {p['uuid'] for p in group} for group in actual['components']):
                raise ValueError('auxiliary_new_named_connection_not_native_positive')
            result['new_craft'] = craft.analyze_board(child, track_uuid_scope=incoming)
            if not result['new_craft']['craft_ok']:
                raise ValueError('auxiliary_new_or_touched_copper_craft_refused')

            def stable():
                if (families != [force._family(p, board_hint) for p in (source, candidate)]
                        or epoch != force._code_identity() or not _bindings_stable(before) or not _bindings_stable(after)
                        or native_bindings != [row._source_binding(b) for b in (parent, child)]):
                    raise ValueError('auxiliary_source_candidate_family_or_code_changed')
            stable()

        for name, path, family in zip(('source', 'candidate'), (source, candidate), families):
            with stages.stage(name+'_sense_audit') as deadline:
                stable()
                # The saved replay itself binds the loaded PCB, code and family.
                # Retain its RAW result before testing completeness or identity.
                proof = sense.replay(path, board_hint=board_hint, timeout_s=_left(deadline))
                result['sense_audits'][name] = proof
                stable()
                if proof.get('complete') is not True:
                    raise ValueError('auxiliary_'+name+'_sense_evidence_incomplete:'+str(proof.get('stop')))
                if (proof.get('identity_stable') is not True or proof.get('loaded_board_identity_verified') is not True
                        or proof.get('source') != str(path) or proof.get('source_family_before') != family
                        or proof.get('source_family_after') != family or proof.get('code_before') != epoch
                        or proof.get('code_after') != epoch):
                    raise ValueError('auxiliary_'+name+'_sense_saved_identity_unbound')

        with stages.stage('sense_comparison') as deadline:
            stable()
            transforms = sense.native_copper_transform_inventory(parent, child, modified_nets=[before['net']])
            result['native_copper_transforms'] = transforms
            if (len(transforms) != 1 or transforms[0]['net'] != before['net']
                    or any(transforms[0][k] for k in ('retired_track_uuids','retired_via_uuids','retired_zone_uuids','added_zone_uuids'))
                    or set(transforms[0]['added_track_uuids']) != incoming
                    or set(transforms[0]['added_via_uuids']) != {force._uid(v) for v in vias}):
                raise ValueError('auxiliary_exact_additive_native_transform_required')
            result['sense_preservation'] = sense.compare_contour_preservation(
                result['sense_audits']['source'], result['sense_audits']['candidate'],
                modified_nets=[before['net']], native_copper_transforms=transforms)
            if not result['sense_preservation']['comparison_complete'] or not result['sense_preservation']['same_evidence']:
                raise ValueError('auxiliary_sense_relationship_preservation_refused')
            stable()
            result.update(ok=True, complete=True, identity_stable=True,
                received_track_uuids=sorted(force._uid(t) for t in tracks),
                received_via_uuids=sorted(force._uid(t) for t in vias),
                track_requirements={force._uid(t): before['required_by_layer_mm'][fab.COPPER_LAYER_IDS[int(t.GetLayer())]] for t in tracks},
                original_terminal_partitions_preserved=True, attached_named_connection_proved=True,
                full_receiving_still_required=['native_DRC', 'field', 'ground_returns', 'current_debt', 'final_transaction'])
    except Exception as exc:
        result.update(ok=False, complete=False, identity_stable=False)
        result['errors'].append(type(exc).__name__+':'+str(exc))
    finally:
        if stages is not None:
            result['elapsed_s'] = time.monotonic()-stages.started
    return result


def _discover(board, contract, deadline):
    """Walk exact actual endpoint incidences, not labels/groups/caller UUIDs."""
    _, material = _material(board, contract['net'])
    ends = _pads(board, contract['declaration'])
    attached, tap = ends['attached_terminal'], ends['tap_terminal']
    faces = [int(l) for l in attached.GetLayerSet().CuStack()]
    if len(faces) != 1 or faces[0] not in (pcbnew.F_Cu, pcbnew.B_Cu):
        raise ValueError('auxiliary_single_outer_source_face_required')
    edges = {}; incidents = defaultdict(list)
    for item in material:
        _left(deadline)
        if item.GetClass() == 'PCB_TRACK':
            vertices = [(int(item.GetLayer()), *item.GetStart()), (int(item.GetLayer()), *item.GetEnd())]
        elif item.GetClass() == 'PCB_VIA':
            vertices = [(int(item.TopLayer()), *item.GetPosition()), (int(item.BottomLayer()), *item.GetPosition())]
        else:
            continue  # A zone/arc contact is caught by projected isolation and capture.
        uid = force._uid(item); edges[uid] = (item, vertices)
        for vertex in vertices: incidents[vertex].append(uid)
    cursor = (faces[0], *attached.GetPosition()); selected = []; previous = None
    while not (cursor[1:] == tuple(tap.GetPosition()) and tap.IsOnLayer(cursor[0])):
        _left(deadline)
        choices = [u for u in incidents[cursor] if u != previous]
        if len(choices) != 1:
            raise ValueError('auxiliary_actual_endpoint_walk_open_or_branched')
        uid = choices[0]
        if uid in selected or len(selected) >= 66:
            raise ValueError('auxiliary_actual_endpoint_walk_cycle_or_bound')
        item, vertices = edges[uid]
        if vertices[0] == vertices[1]:
            raise ValueError('auxiliary_zero_length_native_edge')
        selected.append(uid)
        cursor = vertices[1] if cursor == vertices[0] else vertices[0]
        previous = uid
    return [edges[u][0] for u in selected]


def inventory(board, *, board_hint, timeout_s=2.):
    """Fresh saved-board branch requirements, never raw-ID fault suppression.

    The current classifier removes discovered material only from a private
    CONNECTIVITY_DATA graph. No BOARD item is deleted or saved. Re-prove the
    isolated attached land, all aggregate terminals and one physical tap.
    Missing declarations are neutral; a partial/unknown declared proof emits
    no requirements, so the unchanged aggregate rule remains in force.
    """
    result = dict(schema=1, scope=SCOPE, complete=False, track_requirements={},
        proofs=[], absent_attachments=[], refusals=[], board_mutated=False,
        aggregate_current_budget_modified=False, retirement_authority=False,
        current_total_qualified=False, barrel_current_qualified=False,
        load_model_qualified=False, release_authority=False)
    try:
        deadline = _deadline(timeout_s); hint = _hint(board_hint)
        rows = policy.load(board.GetFileName(), board_hint=hint).get('params', {}).get(POLICY_KEY, [])
        if rows == []:
            return dict(result, complete=True, neutral=True)
        if type(rows) is not list or not 1 <= len(rows) <= 16:
            raise ValueError('bounded_existing_auxiliary_attachment_declarations_required')
        path = Path(board.GetFileName()).resolve()
        family, epoch, binding = force._family(path, hint), force._code_identity(), row._source_binding(board)
        if binding != row._source_binding(pcbnew.LoadBoard(str(path))):
            raise ValueError('auxiliary_inventory_exact_saved_board_required')
        requirements = {}; proofs = []; contracts = []
        for declared in rows:
            _left(deadline)
            if type(declared) is not dict or not _text(declared.get('id')):
                raise ValueError('exact_auxiliary_attachment_identity_required')
            contract = _intent(board, declared['id'], hint, deadline); contracts.append(contract)
            # A genuinely isolated as-yet-unconstructed endpoint is not a
            # partial branch or permission to lower any existing trace.
            try:
                isolated = _source_topology(board, contract)
            except ValueError:
                isolated = None
            if isolated is not None:
                result['absent_attachments'].append(dict(id=declared['id'], source_topology=isolated))
                continue
            added = _discover(board, contract, deadline)
            tracks, vias, ends, edges = _chain(board, contract, added, deadline)
            ids = {force._uid(i) for i in added}
            projected = _source_topology(board, contract, _projected_omit=ids)
            contacts = _contacts(board, board, contract, added, edges, deadline, _projected_omit=ids)
            pads, material = _material(board, contract['net'])
            before, _ = force._components(pads, [i for i in material if force._uid(i) not in ids])
            after, _ = force._components(pads, material)
            attached = contract['endpoints']['attached_terminal']['uuid']
            def retained(graph):
                return sorted(sorted(p['uuid'] for p in part if p['uuid'] != attached)
                    for part in graph['components'] if any(p['uuid'] != attached for p in part))
            if retained(before) != retained(after):
                raise ValueError('auxiliary_projection_changes_other_native_terminal_partitions')
            webs = []
            for via in vias:
                proof = web.receive(board, force._uid(via), dict(net=contract['net'],
                    current_authority=contract['minimum_conductor_authority'],
                    required_by_layer_mm=contract['required_by_layer_mm'],
                    routing_layers=_routing_layers(tracks, ends)), timeout_s=_left(deadline))
                if not proof['ok'] or not proof['complete']:
                    raise ValueError('auxiliary_saved_via_contact_web_below_minimum_geometry')
                webs.append(proof)
            owned = {force._uid(t): dict(current_authority=contract['minimum_conductor_authority'],
                required_mm=contract['required_by_layer_mm'][fab.COPPER_LAYER_IDS[int(t.GetLayer())]],
                aggregate_current_authority=contract['aggregate_current_authority'],
                attachment_id=declared['id']) for t in tracks}
            if set(owned) & set(requirements):
                raise ValueError('auxiliary_declarations_claim_shared_material')
            requirements.update(owned)
            proofs.append(dict(id=declared['id'], contract=contract, track_requirements=owned,
                material_uuids=sorted(ids), projected_source=projected, contacts=contacts,
                actual_via_contact_webs=webs, original_terminal_partitions_preserved=True,
                source_copper_removed=False, retirement_authority=False, release_authority=False))
        _left(deadline)
        if (binding != row._source_binding(board) or family != force._family(path, hint)
                or epoch != force._code_identity() or not all(_bindings_stable(c) for c in contracts)):
            raise ValueError('auxiliary_inventory_source_family_code_or_canonical_epoch_changed')
        result.update(complete=True, neutral=False, track_requirements=requirements, proofs=proofs,
            source_sha256=force._hash(path), source_family=family, code_identity=epoch, identity_stable=True)
    except Exception as exc:
        result['refusals'].append(type(exc).__name__+':'+str(exc))
    return result
