"""Explicit incoming quiet output in a complete Source-owned macro.

Not an ordinary signal alias or a new placement/current/process authority.
Only fresh canonical INA output -> physical ADC requests are consumed. The
first tier requires the moved output to be an actual isolated Source land;
the ADC and all original quiet copper stay fixed. Other macro geometry is
owned exclusively by the independent complete-macro receiver.
"""
import copy
import contextvars
from contextlib import contextmanager
import json
import math
from pathlib import Path
import time
import uuid

import pcbnew
import cec_cell_row_rebuild as row
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_quiet_signal_requests as source_requests
import cec_quiet_signal_completion as quiet

KIND = 'source_typed_incoming_quiet_output'
SCOPE = 'independently_received_projected_quiet_output_path'
_observer = contextvars.ContextVar('projected_quiet_receiving_observer', default=None)


def ids(values):
    """Identity-only, explicit opt-in. No net/width/layer/endpoint overrides."""
    if type(values) not in (list, tuple) or len(values) > 4:
        raise ValueError('bounded_quiet_output_pad_uuid_list_required')
    result = []
    for value in values:
        if type(value) is not str:
            raise ValueError('literal_quiet_output_pad_uuid_required')
        try:
            if str(uuid.UUID(value)) != value:
                raise ValueError('canonical_quiet_output_pad_uuid_required')
        except (ValueError, AttributeError) as exc:
            raise ValueError('canonical_quiet_output_pad_uuid_required') from exc
        if value in result:
            raise ValueError('unique_quiet_output_pad_uuids_required')
        result.append(value)
    return sorted(result)


def _budget(seconds):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 10:
        raise ValueError('bounded_projected_quiet_constituent_required')
    return float(seconds)


def _remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise ValueError('projected_quiet_constituent_deadline')
    return min(10., left)


def _stable(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _pads(board):
    values = [p for fp in board.GetFootprints() for p in fp.Pads()]
    result = {force._uid(p): p for p in values}
    if len(values) != len(result) or len(values) > 16384:
        raise ValueError('bounded_unique_projected_quiet_pad_population_required')
    return result


def _pad_identity(pad):
    # Existing exact Source-native identity, plus annotations and pad number.
    # The independent macro/additive receiver retains the complete literal FP.
    from cec_source_ground_boundary_connection import _pad_contact_identity
    return (_pad_contact_identity(pad), pad.GetNumber(), pad.GetPinType(),
            pad.GetPinFunction(), bool(pad.GetParentFootprint().IsDNP()))


def _policy(board, path, net):
    spec = fr._project_netclass_resolver(str(path), board=board)(net) or {}
    if str(spec.get('name', '')).casefold() != 'sense':
        raise ValueError('projected_quiet_must_retain_sensitive_source_class')
    layers = sorted(fr._lastmile_route_layers(board, net_name=net, spec=spec,
        exclude_front=False, allow_nonplane_power_role=False))
    if not layers:
        raise ValueError('source_quiet_signal_routing_faces_required')
    return dict(spec=_stable(spec), allowed_layers=layers)


def _candidate_policy(parent, child, source, candidate, net, expected):
    """Normalize only a byte-proved copied project's authority pathname.

    Every policy field and the native floors remain compared. A different
    sibling project, custom rule, missing companion or resolver source is
    not a copied authority. This tier does not introduce/change a rule.
    """
    import cec_route_dimensions as dimensions
    source, candidate = Path(source), Path(candidate)
    sidecars = {}
    for suffix in ('.kicad_pro', '.kicad_dru'):
        paths = [p.with_suffix(suffix) for p in (source, candidate)]
        if any(p.is_file() and p.stat().st_size > 4*1024*1024 for p in paths):
            raise ValueError('bounded_projected_quiet_policy_companions_required')
        values = [p.read_bytes() if p.is_file() else None for p in paths]
        if values[0] != values[1]:
            raise ValueError('projected_quiet_exact_source_policy_companion_required:' + suffix)
        sidecars[suffix] = values[0]
    projects = [dimensions.project_path(p) for p in (source, candidate)]
    if any(p is not None and p.resolve() != owner.with_suffix('.kicad_pro').resolve()
           for p, owner in zip(projects, (source, candidate))):
        raise ValueError('projected_quiet_exact_sibling_project_authority_required')
    authority_paths = [str(p) if p is not None else 'project_absent' for p in projects]
    policies = [_policy(b, p, net) for b, p in ((parent, source), (child, candidate))]
    for policy, path in zip(policies, authority_paths):
        if policy['spec'].get('dimension_contract', {}).get('source') != path:
            raise ValueError('projected_quiet_resolver_authority_path_mismatch')
    if policies[0] != expected:
        raise ValueError('projected_quiet_source_policy_changed')
    # This is the ONLY ignored difference, established above by exact bytes.
    policies[1]['spec']['dimension_contract']['source'] = authority_paths[0]
    if policies[1] != expected:
        raise ValueError('saved_projected_quiet_class_or_layer_policy_changed')
    if any((p.with_suffix(s).read_bytes() if p.with_suffix(s).is_file() else None) != data
           for s, data in sidecars.items() for p in (source, candidate)):
        raise ValueError('projected_quiet_policy_companion_changed_during_inspection')
    return policies[1]


def _via_process(parent, projected, child, source, candidate, via, request):
    """Ordinary Source floors, or independently existing exact local rule.

    Local provenance never becomes ordinary-via permission. The Source's
    unchanged rule, projected literal package, actual child membership and
    live SMD copper are all independently required for the local alternative.
    """
    import cec_route_dimensions as dimensions
    import cec_existing_local_pofv_pad_rule as local_rule
    import cec_constraints as constraints
    import cec_fab_profile as fab
    diameter, drill = via.GetWidth(via.TopLayer()), via.GetDrillValue()
    ordinary = dimensions.ordinary_via_geometry(request['source_policy']['spec'],
        dimensions.source_board_limits(parent, source),
        requested=(diameter/1e6, drill/1e6))
    if tuple(round(v*1e6) for v in ordinary) == (diameter, drill):
        return dict(kind='ordinary', source_floor_geometry_mm=list(ordinary))
    if fab.board_profile_name(parent) != fab.board_profile_name(child):
        raise ValueError('quiet_local_via_source_process_changed')
    groups = [g for g in child.Groups() if g.GetName() == local_rule.GROUP]
    if (len(groups) != 1 or not groups[0].ContainsItem(via)
            or force._uid(via) not in constraints._validated_local_pofv_signal_uuids(
                child, str(candidate), {})):
        raise ValueError('quiet_local_via_actual_saved_membership_and_copper_required')
    projected_pads = _pads(projected)
    contexts = [local_rule.resolve(projected, projected_pads[request[k]['pad_uuid']])
                for k in ('a', 'b')]
    contexts = [c for c in contexts if c is not None and
        local_rule.geometry(c, (diameter/1e6, drill/1e6)) == (diameter/1e6, drill/1e6)]
    if not contexts:
        raise ValueError('quiet_via_below_source_ordinary_floor_without_existing_local_rule')
    return dict(kind='existing_Source_local_POFV', existing_source_rule=contexts[0],
        actual_saved_native_membership_and_copper_reproved=True,
        ordinary_geometry_not_waived=True, current_authority=False)


def _source_request_identity(request):
    # Exact existing full-export policy; remove ONLY the generated raw hash.
    # Changed exporter, hierarchy, semantic tree, pin/net/field values refuse.
    import cec_source_netlist_semantics as semantics
    result = copy.deepcopy(request)
    result['source_bindings'] = semantics.replay_identity(result['source_bindings'])
    return _stable(result)


def plan(parent, projected, proposal, values, *, timeout_s=10.):
    """Fresh Source derivation; projected endpoints are obligations, not joins."""
    values = ids(values)
    if not values:
        return {}
    deadline = time.monotonic() + _budget(timeout_s)
    source = Path(parent.GetFileName()).resolve(strict=True)
    binding = row._source_binding(parent)
    projected_binding = row._source_binding(projected)
    if (proposal.get('scope') != 'source_typed_complete_cell_escape_proposal'
            or proposal.get('source_native_binding') != binding
            or row._source_binding(pcbnew.LoadBoard(str(source))) != binding):
        raise ValueError('literal_complete_macro_source_required_for_quiet_output')
    hint = proposal['board_hint']
    family = force._family(source, hint); epoch = force._code_identity()
    report = source_requests.plan(parent, source, board_hint=hint,
        timeout_s=_remaining(deadline))
    if report.get('complete') is not True or report.get('errors'):
        raise ValueError('fresh_canonical_quiet_output_source_compilation_required')
    old, live = _pads(parent), _pads(projected)
    graph = fr._read_only_route_connectivity(parent)
    requests = {}; used_nets = set()
    for uid in values:
        _remaining(deadline)
        matches = [r for r in report['requests'] if r.get('root_pad_uuid') == uid]
        if len(matches) != 1 or uid not in old or uid not in live:
            raise ValueError('unique_requested_source_manufacturer_quiet_output_required')
        demand = matches[0]; net = demand['net']; target_uid = demand['target_pad_uuid']
        if target_uid not in old or target_uid not in live or net in used_nets:
            raise ValueError('unique_fixed_source_adc_endpoint_required')
        owner = old[uid].GetParentFootprint(); ref = owner.GetReference()
        target_ref = old[target_uid].GetParentFootprint().GetReference()
        model = roles.footprint_contract(owner)
        if (ref not in proposal['poses'] or ref in proposal['stationary_device_owners']
                or target_ref in proposal['poses'] or model is None
                or model != proposal['device_contracts'].get(ref)
                or set(model['pins']) != {p.GetNumber() for p in owner.Pads()}
                or model['pins'].get(old[uid].GetNumber()) != 'signal_output'
                or demand['root']['role'] != 'analog_output'
                or demand['root']['manufacturer'] != model
                or demand['target']['role'] != 'adc_capable_physical_gpio'
                or demand['target']['manufacturer'].get('adc_capable') is not True):
            raise ValueError('actual_moving_manufacturer_output_and_fixed_physical_adc_required')
        # No implicit cut/reanchor of a retained quiet tree in this tier.
        if any(force._uid(item) != uid for item in graph.GetConnectedItems(old[uid])):
            raise ValueError('source_quiet_output_must_be_an_actual_isolated_land')
        if fr.net_connectivity_component_count(parent, old[uid].GetNetCode()) < 2:
            raise ValueError('source_quiet_output_must_be_disconnected')
        # Reconstruct the one allowed pad pose from literal Source, not from
        # the caller's projected board or a coordinate in the incoming request.
        expected_board = pcbnew.LoadBoard(str(source))
        expected_fp = expected_board.FindFootprintByReference(ref)
        pose = proposal['poses'][ref]
        expected_fp.SetPosition(pcbnew.VECTOR2I(*(round(v * 1e6) for v in pose[:2])))
        expected_fp.SetOrientationDegrees(pose[2])
        expected_pad = _pads(expected_board)[uid]
        if (_pad_identity(expected_pad) != _pad_identity(live[uid])
                or _pad_identity(old[uid]) == _pad_identity(live[uid])
                or _pad_identity(old[target_uid]) != _pad_identity(live[target_uid])):
            raise ValueError('exact_source_moving_output_and_unchanged_adc_pose_required')
        expected_population = {uid, target_uid}
        if ({u for u, p in old.items() if p.GetNetname() == net} != expected_population
                or {u for u, p in live.items() if p.GetNetname() == net} != expected_population):
            raise ValueError('quiet_output_exact_two_source_and_projected_terminals_required')
        # Neither this scope nor a purported macro cut may alter quiet copper.
        old_copper = {force._uid(t): t for t in parent.GetTracks() if t.GetNetname() == net}
        new_copper = {force._uid(t): t for t in projected.GetTracks() if t.GetNetname() == net}
        from cec_source_ground_boundary_connection import _metal
        if (old_copper.keys() != new_copper.keys()
                or any(_metal(t) != _metal(new_copper[u]) for u, t in old_copper.items())
                or any(z.GetNetname() == net for z in projected.Zones())):
            raise ValueError('all_original_quiet_copper_must_remain_fixed_without_pours')
        policy = _policy(parent, source, net)
        if _policy(projected, source, net) != policy:
            raise ValueError('quiet_source_layer_or_class_policy_changed')
        def endpoint(pad):
            return dict(pad_uuid=force._uid(pad), at_nm=list(pad.GetPosition()),
                layers=sorted(map(int, pad.GetLayerSet().CuStack())))
        if any(not set(endpoint(p)['layers']) <= set(policy['allowed_layers'])
               for p in (live[uid], live[target_uid])):
            raise ValueError('actual_quiet_surface_endpoint_not_on_permitted_signal_face')
        requests['quiet_output:' + uid] = dict(kind=KIND, net=net,
            a=endpoint(live[uid]), b=endpoint(live[target_uid]),
            width_nm=demand['width_nm'], clearance_nm=demand['clearance_nm'],
            allowed_layers=policy['allowed_layers'], source_quiet_request=_source_request_identity(demand),
            source_policy=policy, source_pad_uuid=uid,
            source_output_isolated=True, fixed_adc_and_original_quiet_copper_required=True,
            incoming_native_terminal_join_mandatory=True, current_authority=False,
            ordinary_authority=False, release_authority=False)
        used_nets.add(net)
    if (binding != row._source_binding(parent) or projected_binding != row._source_binding(projected)
            or family != force._family(source, hint) or epoch != force._code_identity()
            or not source_requests.bindings_current(report)):
        raise ValueError('quiet_source_projected_frame_or_canonical_epoch_changed')
    _remaining(deadline)
    return requests


def discharged(parent, projected, proposal, requests, values, *, timeout_s=10.):
    """Only freshly rederived, explicitly requested Source output obligations."""
    expected = plan(parent, projected, proposal, values, timeout_s=timeout_s)
    actual = {k: r for k, r in requests.items() if r.get('kind') == KIND
              or k.startswith('quiet_output:')}
    if actual != expected:
        raise ValueError('exact_requested_fresh_quiet_output_obligations_required')
    return {r['source_pad_uuid'] for r in expected.values()}


def _replay_options(options, values, seconds):
    import cec_cell_macro_requests as compiler
    if type(options) is not dict:
        raise ValueError('explicit_macro_reconstruction_options_required')
    values = ids(values)
    if not values:
        raise ValueError('nonempty_projected_quiet_output_opt_in_required')
    original = _stable(options)
    base = {'max_shift_mm', 'allow_owned_locked_escapes', 'rebuild_projected_ground',
            'additional_obstacle_track_uuids'}
    extras = {k: v for k, v in original.items() if k not in base}
    # A separate argument owns the explicit identity list, never a nested
    # caller-provided packet, role, width, layers or preclaimed positive.
    if 'required_quiet_output_pad_uuids' in extras:
        raise ValueError('quiet_output_opt_in_cannot_be_duplicated_in_options')
    compiler.packet_options({'explicit_native_macro_options': extras})
    budgets = extras.get('compilation_phase_timeouts_s')
    if budgets is not None and any(value > seconds for value in compiler._phase_budgets(budgets)):
        raise ValueError('quiet_compiler_constituent_exceeds_receiving_lease')
    return original


def receiving_stages(options, values, seconds):
    options = _replay_options(options, values, _budget(seconds))
    import cec_cell_macro_requests as compiler
    phases = (['compile:' + name for name in compiler.compilation_phases(
        options.get('compilation_phase_timeouts_s'))]
        if options.get('compilation_phase_timeouts_s') is not None else ['compile'])
    return ['saved_identity_and_actual_poses', *phases,
        *['actual_quiet_path:' + uid for uid in ids(values)],
        'quiet_native_field_delta', 'all_original_physical_returns', 'final_live_identity']


@contextmanager
def observe_receiving_phases(callback):
    if not callable(callback):
        raise ValueError('runtime_projected_quiet_phase_observer_required')
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)


class _Lease:
    def __init__(self, seconds, names):
        self.seconds = _budget(seconds); self.names = list(names); self.index = 0
        self.started = self.phase_started = time.monotonic()
        self.deadline = self.started + self.seconds; self.timings = {}
        self._emit()

    def _emit(self):
        if _observer.get() is not None:
            _observer.get()(dict(index=self.index, phase=self.names[self.index]))

    def close(self):
        _remaining(self.deadline)
        self.timings[self.names[self.index]] = time.monotonic() - self.phase_started

    def advance(self, name):
        if self.index + 1 >= len(self.names) or self.names[self.index + 1] != name:
            raise ValueError('ordered_projected_quiet_receiving_stages_required')
        self.close(); self.index += 1
        self.phase_started = time.monotonic(); self.deadline = self.phase_started + self.seconds
        self._emit(); _remaining(self.deadline)

    def finish(self):
        if self.index != len(self.names) - 1:
            raise ValueError('all_projected_quiet_receiving_stages_required')
        self.close()
        if time.monotonic() - self.started >= len(self.names) * self.seconds:
            raise ValueError('projected_quiet_total_composition_deadline')


def _observe_path(parent, projected, child, source, candidate, request, deadline):
    """Actual saved material only. No poses/cuts/other-net admission here."""
    import cec_additive_route_receiving as additive
    import cec_copper_echo as syntax
    import cec_source_literal_additions as literal
    import cec_decoupler_cell as cells
    net = request['net']; root_uid = request['a']['pad_uuid']; target_uid = request['b']['pad_uuid']
    expected, live = _pads(projected), _pads(child)
    if {u for u, p in live.items() if p.GetNetname() == net} != {root_uid, target_uid}:
        raise ValueError('saved_projected_quiet_third_or_missing_terminal')
    for uid in (root_uid, target_uid):
        if _pad_identity(expected[uid]) != _pad_identity(live[uid]):
            raise ValueError('saved_projected_quiet_endpoint_not_exact_source_pose')
    _candidate_policy(parent, child, source, candidate, net, request['source_policy'])
    if any(z.GetNetname() == net for z in child.Zones()):
        raise ValueError('saved_projected_quiet_pour_not_authorized')
    before = additive._nodes(source)[1]; after = additive._nodes(candidate)[1]
    source_text, candidate_text = source.read_text(), candidate.read_text()
    source_ids = literal._inventory(source_text)[1]
    old_items, new_items = list(parent.GetTracks()), list(child.GetTracks())
    old_tracks = {force._uid(t): t for t in old_items}
    tracks = {force._uid(t): t for t in new_items}
    if len(old_tracks) != len(old_items) or len(tracks) != len(new_items):
        raise ValueError('unique_saved_quiet_native_conductor_identity_required')
    old_net = {u for u, t in old_tracks.items() if t.GetNetname() == net}
    if any(u not in after or syntax._freeze(before[u]) != syntax._freeze(after[u]) for u in old_net):
        raise ValueError('saved_projected_quiet_original_copper_changed')
    added_copper = {u for u in after.keys() - before.keys()
                    if after[u][0] in ('segment', 'via', 'arc')}
    if not 1 <= len(added_copper) <= 512:
        raise ValueError('bounded_complete_macro_copper_inventory_required')
    if added_copper & source_ids:
        raise ValueError('new_quiet_copper_cannot_shadow_any_original_source_uuid')
    literal_nets = literal.incoming_copper_nets(candidate_text, added_copper)
    raw = {u for u, n in literal_nets.items() if n == net}
    incoming = {u for u, t in tracks.items() if u not in old_tracks and t.GetNetname() == net}
    if raw != incoming or not 1 <= len(incoming) <= 512:
        raise ValueError('exact_nonempty_literal_and_native_quiet_additions_required')
    if {u for u, t in tracks.items() if t.GetNetname() == net} != old_net | incoming:
        raise ValueError('saved_quiet_population_includes_retagged_or_unowned_source_conductor')
    from cec_source_ground_boundary_connection import _metal
    if any(_metal(old_tracks[u]) != _metal(tracks[u]) for u in old_net):
        raise ValueError('saved_quiet_original_native_copper_changed')
    primitive = {'PCB_TRACK': 'segment', 'PCB_VIA': 'via'}
    if any(after[u][0] != primitive.get(tracks[u].GetClass()) for u in incoming):
        raise ValueError('saved_quiet_literal_native_primitive_mismatch')
    allowed = set(request['allowed_layers']); gap = request['clearance_nm']; foreign = {}
    via_processes = {}
    for uid in sorted(incoming):
        _remaining(deadline); item = tracks[uid]
        if item.GetClass() == 'PCB_TRACK':
            a, b = item.GetStart(), item.GetEnd(); dx, dy = abs(a.x-b.x), abs(a.y-b.y)
            if (item.GetWidth() != request['width_nm'] or int(item.GetLayer()) not in allowed
                    or a == b or dx and dy and dx != dy
                    or not fr._edge_leg_clear(child, a, b, item.GetWidth()/2 + gap)
                    or not fr._tap_foreign_clear(child, a, b, item.GetWidth(), int(item.GetLayer()),
                        gap, {item.GetNetCode()}, foreign_cache=foreign)):
                raise ValueError('saved_projected_quiet_track_width_face_or_native_clearance_refused')
        elif item.GetClass() == 'PCB_VIA':
            diameter, drill = item.GetWidth(item.TopLayer()), item.GetDrillValue()
            via_processes[uid] = _via_process(parent, projected, child, source, candidate, item, request)
            if (item.GetViaType() != pcbnew.VIATYPE_THROUGH
                    or not cells._hole_to_hole_clear(child, item.GetPosition(), drill/1e6,
                        ignore_via_uuids=(uid,))[0]
                    or not fr._via_spot_clear(child, item.GetPosition(), diameter, gap,
                        {item.GetNetCode()}, drill_nm=drill, net_code=item.GetNetCode(),
                        existing_via_uuid=uid, report={})):
                raise ValueError('saved_projected_quiet_via_process_or_all_face_clearance_refused')
        else:
            raise ValueError('saved_projected_quiet_literal_primitive_refused')
    graph = fr._read_only_route_connectivity(child)
    reached = {root_uid} | {force._uid(i) for i in graph.GetConnectedItems(live[root_uid])}
    if target_uid not in reached or not incoming <= reached or not old_net <= reached:
        raise ValueError('saved_projected_quiet_entire_old_and_new_path_not_joined')
    counts = [fr.net_connectivity_component_count(b, b.GetNetcodeFromNetname(net)) for b in (parent, child)]
    if counts[1] >= counts[0]:
        raise ValueError('saved_projected_quiet_native_components_not_reduced')
    _remaining(deadline)
    return dict(net=net, root_pad_uuid=root_uid, target_pad_uuid=target_uid,
        source_components=counts[0], candidate_components=counts[1], added_native_uuids=sorted(incoming),
        exact_original_quiet_copper_preserved=True, exact_source_width_and_signal_faces_preserved=True,
        entire_native_quiet_population_accounted_for=True, via_processes=via_processes)


def receive(source, candidate, *, board_hint, required_quiet_output_pad_uuids,
            macro_options, timeout_s=10.):
    """Fresh independent Source/actual-pose replay; never calls macro.receive.

    Partial quiet-path scope only. The complete macro must separately receive
    exact all-net cuts/poses/additions, local returns, native partitions and
    every mandatory obligation on this SAME candidate. Original-parent all16
    remains mandatory; success here grants no Source-motion or release grade.
    """
    import cec_cell_macro_requests as compiler
    import cec_complete_cell_receiving as cell
    import cec_field_coupling as field
    import cec_ground_return_preservation as ground
    values = ids(required_quiet_output_pad_uuids); options = _replay_options(macro_options, values, timeout_s)
    options_identity = _stable(macro_options)
    names = receiving_stages(options, values, timeout_s); lease = _Lease(timeout_s, names)
    result = dict(scope=SCOPE, ok=False, complete=False, errors=[], path_proofs=[],
        stage_timings_s=lease.timings, bounded_composition=dict(constituents=names,
            per_constituent_limit_s=timeout_s, aggregate_limit_s=len(names)*timeout_s),
        complete_macro_receiving_still_required=True, whole_original_parent_all16_still_required=True,
        current_qualified=False, adc_mode_qualified=False, load_qualified=False,
        routing_admitted=False, release_authority=False)
    try:
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        if source == candidate or source.samefile(candidate):
            raise ValueError('distinct_projected_quiet_source_and_candidate_required')
        epoch = force._code_identity(); families = [force._family(p, board_hint) for p in (source, candidate)]
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        parent_binding, child_binding = [row._source_binding(b) for b in (parent, child)]
        poses, moved = cell._poses(parent, child, board_hint, options.get('reference_group_uuids', ()))
        compile_names = [name for name in names if name.startswith('compile')]
        lease.advance(compile_names[0])
        def observe(event):
            if event['event'] == 'start' and event['index'] and len(compile_names) > 1:
                lease.advance(compile_names[event['index']])
            _remaining(lease.deadline)
        with compiler.observe_compilation_phases(observe):
            projected, packet = compiler.compile(source, poses, board_hint=board_hint,
                required_quiet_output_pad_uuids=values, timeout_s=_remaining(lease.deadline), **options)
        received = set()
        for uid in values:
            lease.advance('actual_quiet_path:' + uid)
            request = packet['requests'].get('quiet_output:' + uid)
            if request is None or request.get('kind') != KIND:
                raise ValueError('fresh_macro_quiet_request_missing')
            proof = _observe_path(parent, projected, child, source, candidate, request, lease.deadline)
            received.update(proof['added_native_uuids']); result['path_proofs'].append(proof)
        lease.advance('quiet_native_field_delta')
        before = {force._uid(t) for t in child.GetTracks()} - received
        result['quiet_field'] = field.assess_native_additions(child, before, board_path=str(candidate),
            board_hint=board_hint, timeout_s=_remaining(lease.deadline))
        if result['quiet_field'].get('ok') is not True or result['quiet_field'].get('complete') is not True:
            raise ValueError('projected_quiet_actual_field_delta_refused_or_unknown')
        lease.advance('all_original_physical_returns')
        result['physical_returns'] = ground.receive(parent, child, timeout_s=_remaining(lease.deadline))
        if result['physical_returns'].get('ok') is not True or result['physical_returns'].get('complete') is not True:
            raise ValueError('projected_quiet_actual_source_return_regression_or_unknown')
        lease.advance('final_live_identity')
        if (families != [force._family(p, board_hint) for p in (source, candidate)]
                or epoch != force._code_identity() or options_identity != _stable(macro_options)
                or values != ids(required_quiet_output_pad_uuids)
                or parent_binding != row._source_binding(parent) or child_binding != row._source_binding(child)):
            raise ValueError('projected_quiet_source_candidate_options_or_code_changed')
        for uid in values:
            proof = packet['requests']['quiet_output:' + uid]['source_quiet_request']
            if not source_requests.bindings_current(dict(scope='source_typed_quiet_analog_requests',
                    source_bindings=proof['source_bindings'])):
                raise ValueError('projected_quiet_final_canonical_epoch_changed')
        lease.finish()
        result.update(ok=True, complete=True, source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate), required_quiet_output_pad_uuids=values,
            same_source_candidate_families_and_code=True)
    except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
        result['failed_stage'] = lease.names[lease.index]
    result['elapsed_s'] = time.monotonic() - lease.started
    return result
