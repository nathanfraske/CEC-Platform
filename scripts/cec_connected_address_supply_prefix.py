"""Fresh Source roles for a retired, already-wired supply-address endpoint.

This is only a class-only prefix eligibility observer.  The stock endpoint
cut producer rederives the complete old chain and its literal fixed throat;
no request label, copied manufacturer proof or caller width supplies authority.
The existing prefix receiver still owns every actual new narrow component's
current/factory floor, length, topology and full-width throat.  This module
grants no retirement, routing, barrel, load allocation or saved admission.
"""
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import time

import pcbnew
import cec_copper_echo as syntax
import cec_current_topology as topology
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_force_current as force
import cec_native_construction_frame as native
import cec_operation_budget as budget
import cec_request_wire_identity as wire
import cec_route_dimensions as dimensions
import cec_source_supply_endpoint_cut as cuts


ROLE = 'source_recompiled_connected_supply_strapped_address'


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('connected_address_prefix_deadline')


def _same(first, second, deadline):
    return wire.canonical(first, deadline=deadline) == wire.canonical(second, deadline=deadline)


def _inventory(board):
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    tracks = list(board.GetTracks())
    if len(pads) + len(tracks) > 16384:
        raise ValueError('connected_address_prefix_inventory_bound')
    def unique(items):
        result = {force._uid(item): item for item in items}
        if len(result) != len(items):
            raise ValueError('connected_address_prefix_duplicate_native_identity')
        return result
    return unique(pads), unique(tracks)


def _group_state(board, item):
    # GetParentGroup returns KiCad's opaque EDA_GROUP base, not PCB_GROUP.
    # Resolve the actual concrete native membership before reading identity
    # or lock state; SWIG base-subobject pointers are not UUIDs.
    matches = [g for g in board.Groups() if g.ContainsItem(item)]
    if item.GetParentGroup() is None and not matches:
        return None
    if item.GetParentGroup() is None or len(matches) != 1:
        raise ValueError('connected_address_prefix_exact_native_group_required')
    group = matches[0]
    if item.GetParentGroupId().AsString() != force._uid(group):
        raise ValueError('connected_address_prefix_exact_native_group_required')
    return (force._uid(group), group.GetName(), bool(group.IsLocked()),
        group.GetParentGroupId().AsString())


def _state(board, deadline):
    # The existing private IR formatter does not normalize unfinished copper.
    # It is used for immutable input identity, never to accept a saved child.
    return (native._identity(board, deadline),
        int(board.GetDesignSettings().m_TrackMinWidth),
        int(board.GetDesignSettings().m_MinClearance))


def _nodes(raw, deadline):
    root = syntax._parse(syntax._TOKEN.findall(raw))
    result = {}
    for node in root[1:]:
        _tick(deadline)
        if not isinstance(node, list):
            continue
        ids = [r[1].strip('"') for r in node[1:] if isinstance(r, list)
            and len(r) == 2 and r[0] == 'uuid']
        if ids:
            if len(ids) != 1 or ids[0] in result:
                raise ValueError('connected_address_prefix_ambiguous_native_node')
            result[ids[0]] = node
    return result


def _pad_node(fp_node, pad, deadline):
    selected = [n for n in fp_node[1:] if isinstance(n, list) and n
        and n[0] == 'pad' and any(isinstance(r, list) and len(r) == 2
            and r[0] == 'uuid' and r[1].strip('"') == force._uid(pad) for r in n)]
    if len(selected) != 1:
        raise ValueError('connected_address_prefix_exact_native_pad_required')
    result = []; positions = 0; nets = 0
    for row in selected[0]:
        if isinstance(row, list) and row and row[0] == 'at':
            # Only the rigid pose is compared through actual native geometry.
            # Retain every other serialized pad field, including unknown ones.
            if len(row) not in (3, 4):
                raise ValueError('connected_address_prefix_literal_pad_pose_required')
            for value in row[1:]:
                number = float(value)
                if not math.isfinite(number) or abs(number) > 2000000:
                    raise ValueError('connected_address_prefix_finite_pad_pose_required')
            positions += 1
        elif isinstance(row, list) and row and row[0] == 'net':
            # RAM netcode ordinals are not persisted electrical identities.
            if len(row) not in (2, 3) or json.loads(row[-1]) != str(pad.GetNetname()):
                raise ValueError('connected_address_prefix_literal_pad_net_required')
            if len(row) == 3:
                int(row[1])
            nets += 1; result.append(['net', str(pad.GetNetname())])
        else:
            result.append(row)
    if positions != 1 or (pad.GetNetCode() > 0 and nets != 1) or nets > 1:
        raise ValueError('connected_address_prefix_complete_native_pad_required')
    _tick(deadline)
    return result


class _Context:
    def __init__(self, source, posed, board_hint, deadline, source_state, posed_state, path):
        self.source, self.posed, self.hint = source, posed, board_hint
        self.deadline, self.path = deadline, path
        self.old_pads, self.old_tracks = _inventory(source)
        self.new_pads, self.new_tracks = _inventory(posed)
        self.old_nodes = _nodes(source_state[0][0], deadline)
        self.new_nodes = _nodes(posed_state[0][0], deadline)
        self.resolver = dimensions.project_resolver(path, board=source)
        with force._thermal_hint(board_hint):
            self.domains = topology.board_current_domains(source, board_hint=board_hint)
        self.profile = fab.active_profile_name(source, hint=board_hint)
        if not self.profile or self.profile != fab.active_profile_name(posed, hint=board_hint):
            raise ValueError('connected_address_prefix_unchanged_source_profile_required')
        if source_state[1:] != posed_state[1:]:
            raise ValueError('connected_address_prefix_original_factory_floors_required')
        self.floors = {}; self.derived = None; self.external = {}

    def remaining(self):
        _tick(self.deadline)
        return min(10., self.deadline - time.monotonic())

    def floor(self, track):
        _tick(self.deadline)
        key = (str(track.GetNetname()), int(track.GetLayer()))
        if key not in self.floors:
            name = fab.COPPER_LAYER_IDS.get(key[1])
            if name is None:
                raise ValueError('connected_address_prefix_actual_copper_face_required')
            display = self.source.GetLayerName(key[1]); spec = self.resolver(key[0]) or {}
            with force._thermal_hint(self.hint):
                authority = topology.current_contract_for_net(key[0], self.hint, self.domains)
            if authority is None:
                raise ValueError('connected_address_prefix_source_current_required')
            rated = dimensions.current_trace_widths(authority, (name,), self.profile, rise_c=30.)[name]
            per_face = spec.get('track_width_by_layer_mm') or {}
            width = math.ceil(max(float(spec.get('track_width') or 0),
                float(per_face.get(display) or 0), float(per_face.get(name) or 0),
                dimensions.board_limits(self.source)['track_width'], rated) * 1e6)
            clearance = max(int(self.source.GetDesignSettings().m_MinClearance),
                math.ceil(float(spec.get('clearance') or 0) * 1e6))
            if width <= 0 or clearance < 0:
                raise ValueError('connected_address_prefix_source_dimensions_required')
            self.floors[key] = (width, clearance)
        return self.floors[key]

    def derive(self):
        if self.derived is None:
            # Lock handling here is observation only. The enclosing compiler
            # independently owns any retirement/lock permission; this helper
            # neither applies nor authorizes a cut.
            self.derived = cuts.plan(self.source, self.posed, board_hint=self.hint,
                source_floor=self.floor, allow_locked=True, timeout_s=self.remaining())
            for cut in self.derived:
                proof = cut.get('source_authority') or {}
                for path, digest in (proof.get('schematic_files_sha256') or {}).items():
                    if str(path) in self.external and self.external[str(path)] != digest:
                        raise ValueError('connected_address_prefix_conflicting_source_evidence')
                    self.external[str(path)] = digest
                exporter = proof.get('exporter') or {}
                if exporter:
                    self.external[str(exporter['exporter'])] = exporter['exporter_sha256']
        _tick(self.deadline)
        return self.derived

    def rigid_owner(self, pad_uuid):
        old, live = self.old_pads[pad_uuid], self.new_pads.get(pad_uuid)
        if live is None:
            raise ValueError('connected_address_prefix_posed_pad_missing')
        first, last = old.GetParentFootprint(), live.GetParentFootprint()
        model = roles.footprint_contract(first)
        from cec_footprint_fields import footprint_properties
        if (not model or model != roles.footprint_contract(last)
                or model['pins'].get(old.GetNumber()) != 'address'
                or first.IsDNP() or last.IsDNP() or first.IsFlipped() != last.IsFlipped()
                or force._uid(first) != force._uid(last)
                or first.GetReference() != last.GetReference() or first.GetValue() != last.GetValue()
                or first.GetFPIDAsString() != last.GetFPIDAsString()
                or first.GetAttributes() != last.GetAttributes()
                or footprint_properties(first) != footprint_properties(last)
                or first.IsLocked() != last.IsLocked()
                or first.IsExcludedFromBOM() != last.IsExcludedFromBOM()
                or first.IsExcludedFromPosFiles() != last.IsExcludedFromPosFiles()
                or first.GetOrientationDegrees() % 90 or last.GetOrientationDegrees() % 90):
            raise ValueError('connected_address_prefix_actual_same_source_owner_required')
        witness = pcbnew.FOOTPRINT(first)
        witness.SetPosition(last.GetPosition()); witness.SetOrientationDegrees(last.GetOrientationDegrees())
        expected = {force._uid(p): p for p in witness.Pads()}
        actual = {force._uid(p): p for p in last.Pads()}
        if len(expected) != len(list(witness.Pads())) or len(actual) != len(list(last.Pads())) or expected.keys() != actual.keys():
            raise ValueError('connected_address_prefix_complete_rigid_pad_inventory_required')
        import cec_source_current_pad_ports as pad_ports
        for uid, pad in actual.items():
            if pad_ports._pad_identity(pad) != pad_ports._pad_identity(expected[uid]):
                raise ValueError('connected_address_prefix_rigid_pad_identity_changed')
            original = self.old_pads[uid]
            if not _same(_pad_node(self.old_nodes[force._uid(first)], original, self.deadline),
                    _pad_node(self.new_nodes[force._uid(last)], pad, self.deadline), self.deadline):
                raise ValueError('connected_address_prefix_native_pad_definition_changed')
        _tick(self.deadline)
        return live

    def validate_cut(self, cut):
        proof = cut.get('source_authority') or {}
        if proof.get('scope') != 'fresh_source_manufacturer_supply_tied_address':
            return None
        pad = self.rigid_owner(cut['pad_uuid']); face = cut['layer_id']; net = cut['net']
        if tuple(map(int, pad.GetLayerSet().CuStack())) != (face,) or str(pad.GetNetname()) != net:
            raise ValueError('connected_address_prefix_actual_source_surface_required')
        if set(cut['retired_track_uuids']) & self.new_tracks.keys():
            raise ValueError('connected_address_prefix_complete_source_chain_retirement_required')
        for uid in cut['retained_throat_track_uuids']:
            old, live = self.old_tracks[uid], self.new_tracks.get(uid)
            if (live is None or live.GetClass() != 'PCB_TRACK'
                    or live.GetWidth() < cut['width_nm'] or live.GetLayer() != face
                    or str(live.GetNetname()) != net
                    or tuple(cut['retained_throat_nm']) not in (tuple(live.GetStart()), tuple(live.GetEnd()))
                    or not _same(self.old_nodes[uid], self.new_nodes.get(uid), self.deadline)):
                raise ValueError('connected_address_prefix_literal_full_width_throat_changed')
            if _group_state(self.source, old) != _group_state(self.posed, live):
                raise ValueError('connected_address_prefix_retained_throat_group_changed')
        with force._thermal_hint(self.hint):
            before = cells._supply_current_widths(self.source, net)
            after = cells._supply_current_widths(self.posed, net)
        expected = cut['unchanged_full_rail_current_contract']
        if (not before or before.get('profile') != self.profile
                or not _same(before, expected, self.deadline) or not _same(before, after, self.deadline)):
            raise ValueError('connected_address_prefix_unchanged_whole_source_current_required')
        self.remaining()
        return pad


@contextmanager
def _operation(source, posed, board_hint, timeout_s):
    if (not isinstance(source, pcbnew.BOARD) or not isinstance(posed, pcbnew.BOARD)
            or source is posed or type(board_hint) is not str or not board_hint
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10.):
        raise ValueError('bounded_connected_address_source_context_required')
    deadline = time.monotonic() + timeout_s
    before = (_state(source, deadline), _state(posed, deadline))
    path = Path(str(source.GetFileName())).resolve()
    if not source.GetFileName() or not path.is_file():
        raise ValueError('connected_address_prefix_actual_saved_source_required')
    family, code = force._family(path, board_hint), force._code_identity()
    env = tuple(sorted((k, v) for k, v in os.environ.items() if k.startswith('CEC_')
        and k not in budget.DIAGNOSTIC_OUTPUT_ENV_KEYS))
    ctx = None
    try:
        saved = pcbnew.LoadBoard(str(path))
        # Filename spelling and process-global project settings do not replace
        # literal native material: compare the complete saved/native identity.
        if saved is None or native._identity(saved, deadline)[:4] != before[0][0][:4]:
            raise ValueError('connected_address_prefix_source_not_exact_saved_native')
        ctx = _Context(source, posed, board_hint, deadline, *before, path)
        yield ctx
    finally:
        _tick(deadline)
        if before != (_state(source, deadline), _state(posed, deadline)):
            raise ValueError('connected_address_prefix_observer_mutated_native_inputs')
        if (family != force._family(path, board_hint) or code != force._code_identity()
                or env != tuple(sorted((k, v) for k, v in os.environ.items() if k.startswith('CEC_')
                    and k not in budget.DIAGNOSTIC_OUTPUT_ENV_KEYS))
                or ctx is not None and any(force._hash(p) != digest for p, digest in ctx.external.items())):
            raise ValueError('connected_address_prefix_source_family_code_or_evidence_changed')
        _tick(deadline)


def endpoint_context(source_board, posed, request, *, board_hint, timeout_s=10.):
    """Re-prove one exact Source address-to-fixed-throat restoration request.

    Nonapplicable requests return None. A claimed applicable request must
    exactly match freshly derived Source material; no copied proof is trusted.
    """
    if type(request) is not dict or 'source_supply_pad_contact_lead_restoration' not in request:
        return None
    if not isinstance(source_board, pcbnew.BOARD) or not isinstance(posed, pcbnew.BOARD):
        raise ValueError('bounded_connected_address_source_context_required')
    uid = request.get('a', {}).get('pad_uuid')
    old = [p for fp in source_board.GetFootprints() for p in fp.Pads() if force._uid(p) == uid]
    if len(old) != 1:
        raise ValueError('connected_address_prefix_exact_source_launch_required')
    model = roles.footprint_contract(old[0].GetParentFootprint())
    if not model or model['pins'].get(old[0].GetNumber()) != 'address':
        return None
    with _operation(source_board, posed, board_hint, timeout_s) as ctx:
        found = [c for c in ctx.derive() if c['pad_uuid'] == uid
            and _same(c, request['source_supply_pad_contact_lead_restoration'], ctx.deadline)]
        if len(found) != 1:
            raise ValueError('connected_address_prefix_fresh_complete_source_cut_required')
        cut = found[0]; pad = ctx.validate_cut(cut)
        if pad is None:
            raise ValueError('connected_address_prefix_positive_source_address_required')
        a = dict(pad_uuid=uid, at_nm=list(pad.GetPosition()), layers=[cut['layer_id']])
        b = dict(at_nm=cut['retained_throat_nm'], layers=[cut['layer_id']],
            native_uuids=cut['retained_throat_track_uuids'])
        if (request.get('kind') != 'source_boundary' or request.get('net') != cut['net']
                or not _same(request.get('a'), a, ctx.deadline) or not _same(request.get('b'), b, ctx.deadline)
                or not _same(request.get('width_nm'), cut['width_nm'], ctx.deadline)
                or not _same(request.get('clearance_nm'), cut['clearance_nm'], ctx.deadline)
                or not _same(request.get('unchanged_full_rail_current_contract'),
                    cut['unchanged_full_rail_current_contract'], ctx.deadline)):
            raise ValueError('connected_address_prefix_exact_restoration_request_required')
        return dict(pad_uuid=uid, role=ROLE, layer_id=cut['layer_id'],
            retained_throat_track_uuids=cut['retained_throat_track_uuids'],
            retired_track_uuids=cut['retired_track_uuids'],
            current_authority=cut['unchanged_full_rail_current_contract']['current_authority'],
            source_retirement_authority=False, class_only_eligibility=True,
            current_budget_lowered=False, saved_candidate_authorized=False)


def receiver_roles(source_board, posed, source_proposal, contracts, *,
                   track_uuid_scope=(), timeout_s=10.):
    """Roles only for actual new narrow launches after complete old-chain cut.

    The proposal supplies candidate owner/pose identities only. Source role,
    current, old chain and fixed throat are independently rebuilt. The stock
    prefix receiver must still validate every actual narrow component.
    """
    if (type(track_uuid_scope) not in (list, tuple, set, frozenset) or len(track_uuid_scope) > 256
            or any(type(u) is not str or not u for u in track_uuid_scope)
            or len(set(track_uuid_scope)) != len(track_uuid_scope)):
        raise ValueError('connected_address_prefix_exact_delta_scope_required')
    if not track_uuid_scope:
        return {}
    if (type(source_proposal) is not dict or type(contracts) is not dict
            or source_proposal.get('scope') != 'source_typed_complete_cell_escape_proposal'
            or source_proposal.get('board_hint') is None):
        raise ValueError('connected_address_prefix_source_proposal_required')
    hint = source_proposal['board_hint']; poses = source_proposal.get('poses')
    if type(poses) is not dict or not 1 <= len(poses) <= 8:
        raise ValueError('connected_address_prefix_bounded_source_poses_required')
    result = {}
    with _operation(source_board, posed, hint, timeout_s) as ctx:
        scope = set(track_uuid_scope)
        if scope & ctx.old_tracks.keys() or not scope <= ctx.new_tracks.keys() or any(
                ctx.new_tracks[u].GetClass() != 'PCB_TRACK' for u in scope):
            raise ValueError('connected_address_prefix_actual_new_track_scope_required')
        for cut in ctx.derive():
            ctx.remaining()
            authority = cut.get('source_authority') or {}
            if authority.get('scope') != 'fresh_source_manufacturer_supply_tied_address':
                continue
            pad = ctx.new_pads.get(cut['pad_uuid'])
            if pad is None or pad.GetParentFootprint().GetReference() not in poses:
                continue
            face = cut['layer_id']; net = cut['net']
            current = cut['unchanged_full_rail_current_contract']
            minimum = max(int(posed.GetDesignSettings().m_TrackMinWidth), current['required_by_layer_nm'][face])
            # Reconstruct only a role actually needed by the incoming narrow
            # scope. A separate wired address whose old copper was retained
            # must not poison an unrelated power-pin prefix transaction.
            # This is negative applicability only; every selected launch still
            # owes all rigid Source/cut/current/throat checks below.
            if not any(str(ctx.new_tracks[u].GetNetname()) == net
                    and ctx.new_tracks[u].GetLayer() == face
                    and minimum <= ctx.new_tracks[u].GetWidth() < cut['width_nm']
                    and any(pad.GetEffectiveShape(face).Collide(at, 0) for at in
                        (ctx.new_tracks[u].GetStart(), ctx.new_tracks[u].GetEnd())) for u in scope):
                continue
            pose = poses[pad.GetParentFootprint().GetReference()]
            if (type(pose) not in (list, tuple) or len(pose) != 3
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in pose)
                    or any(abs(v) > 2000 for v in pose[:2]) or abs(pose[2]) > 360
                    or tuple(pad.GetParentFootprint().GetPosition()) != tuple(round(v*1e6) for v in pose[:2])
                    or pad.GetParentFootprint().GetOrientationDegrees() % 360 != pose[2] % 360):
                raise ValueError('connected_address_prefix_actual_proposed_owner_pose_required')
            pad = ctx.validate_cut(cut); received = contracts.get(net)
            name = fab.COPPER_LAYER_IDS[face]
            if (type(received) is not dict or received.get('profile') != current['profile']
                    or not _same(received.get('current_authority'), current['current_authority'], ctx.deadline)
                    or name not in received.get('routing_layers', ())
                    or type(received.get('required_by_layer_mm', {}).get(name)) not in (int, float)
                    or not math.isfinite(received['required_by_layer_mm'][name])
                    or math.ceil(received['required_by_layer_mm'][name]*1e6) < cut['width_nm']):
                raise ValueError('connected_address_prefix_receiver_source_current_mismatch')
            for uid in scope:
                item = ctx.new_tracks[uid]
                if (str(item.GetNetname()) == net and item.GetLayer() == face
                        and minimum <= item.GetWidth() < cut['width_nm']
                        and any(pad.GetEffectiveShape(face).Collide(at, 0)
                            for at in (item.GetStart(), item.GetEnd()))):
                    result[cut['pad_uuid']] = ROLE
                    break
        ctx.remaining()
    return result
