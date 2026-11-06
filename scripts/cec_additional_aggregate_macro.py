"""Additional Source-canonical capacitors in a coordinated native macro.

This role supplies demands, never a selected-bypass substitution, copper cut,
load allocation or release verdict. The enclosing macro owns other disjoint
parts and must independently receive every native delta and final gate.
"""
import json
import math
from pathlib import Path
import time

import pcbnew


def _need(value, reason):
    if not value: raise ValueError(reason)


def _wire(value): return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _deadline(seconds):
    _need(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= 10.,
          'bounded_additional_aggregate_constituent_required')
    return time.monotonic() + seconds


def _left(deadline):
    left = deadline - time.monotonic()
    _need(left > 0, 'additional_aggregate_constituent_deadline')
    return min(10., left)


def collect(board, poses, *, board_hint, reference_group_uuids=(), timeout_s=10., excluded_refs=(),
            require_explicit_owner=True, allow_linear_power_stage_reconstruction=False,
            allow_owned_locked_escapes=False):
    """Rederive positive roles from the literal unchanged original Source.

    Assigned capacitors are explicitly outside this role. Unknown unrelated
    devices remain for their own compiler; an attempted unassigned ceramic
    must supply complete canonical intent rather than borrow its net name.
    No destination body/copper veto is applied before the whole cohort moves.
    """
    import cec_source_aggregate_capacitor_cell as cap
    from cec_footprint_fields import footprint_properties
    deadline = _deadline(timeout_s)
    _need(type(require_explicit_owner) is bool, 'explicit_additional_aggregate_owner_mode_required')
    _need(type(allow_linear_power_stage_reconstruction) is bool
        and type(allow_owned_locked_escapes) is bool, 'explicit_wired_aggregate_macro_policy_required')
    _need(type(poses) is dict and 1 <= len(poses) <= 64 and type(board_hint) is str and board_hint,
          'literal_additional_aggregate_macro_context_required')
    _need(all(type(p) in (list, tuple) and len(p) == 3
        and all(type(v) in (int, float) and math.isfinite(v) for v in p) for p in poses.values()),
        'finite_additional_aggregate_cohort_poses_required')
    _need(type(reference_group_uuids) in (list, tuple) and len(set(reference_group_uuids)) == len(reference_group_uuids),
          'unique_additional_cap_reference_group_scope_required')
    binding = cap.row._source_binding(board)
    with cap.force._thermal_hint(board_hint):
        assignment = cap.constraints._device_bypass_assignment(board, project_max_mm=3.5)
    selected = {r['cap_ref'] for r in assignment['assigned'].values()}
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    _need(set(poses) <= fps.keys(), 'additional_aggregate_native_pose_owner_missing')
    candidates = [fps[ref] for ref in poses if ref not in set(excluded_refs) | selected
        and cap.leaf._ceramic(fps[ref])
        and (list(fps[ref].GetPosition()) != [round(v * 1e6) for v in poses[ref][:2]]
             or (poses[ref][2] - fps[ref].GetOrientationDegrees()) % 360 != 0)]
    _need(len(candidates) <= 8, 'bounded_additional_aggregate_cap_cohort_required')
    if not candidates:
        _need(binding == cap.row._source_binding(board), 'additional_aggregate_noop_changed_Source')
        return {}
    source = Path(board.GetFileName()).resolve(strict=True)
    literal = pcbnew.LoadBoard(str(source))
    _need(binding == cap.row._source_binding(literal), 'additional_aggregate_requires_literal_unchanged_Source')
    epoch = cap.force._code_identity(); family = cap.force._family(source, board_hint)
    result = {}
    for fp in candidates:
        _left(deadline); ref = fp.GetReference(); target = poses[ref]
        _need(type(target) in (list, tuple) and len(target) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in target)
            and (target[2] - fp.GetOrientationDegrees()) % 90 == 0
            and math.dist(tuple(fp.GetPosition()), [round(v * 1e6) for v in target[:2]]) <= 128e6,
            'bounded_cardinal_additional_cap_pose_required')
        groups = [g for g in board.Groups() if g.ContainsItem(fp)]
        _need(len(groups) <= 1 and all(cap.force._uid(g) in reference_group_uuids for g in groups),
              'explicit_closed_additional_cap_reference_map_required')
        group_uid = cap.force._uid(groups[0]) if groups else None
        positives = [p for p in fp.Pads() if p.GetNetname() != 'GND']
        grounds = [p for p in fp.Pads() if p.GetNetname() == 'GND']
        _need(len(positives) == len(grounds) == 1, 'additional_aggregate_unique_supply_and_Ground_pads_required')
        positive, ground = positives[0], grounds[0]
        old_ground = any(t.GetNetCode() == ground.GetNetCode() and any(
            t.IsOnLayer(face) and ground.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face), 0)
            for face in ground.GetLayerSet().CuStack()) for t in board.GetTracks())
        ground_leaf = None; wired_identity = None
        old_supply = any(t.GetNetCode() == positive.GetNetCode() and any(
            t.IsOnLayer(face) and positive.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face), 0)
            for face in positive.GetLayerSet().CuStack()) for t in board.GetTracks())
        if allow_linear_power_stage_reconstruction and old_ground and old_supply:
            import cec_wired_aggregate_ground_leaf as leaves
            _need(group_uid is None, 'wired_aggregate_reference_map_needs_separate_transport')
            ground_leaf = leaves.plan(board, cap.force._uid(ground), poses, board_hint=board_hint,
                allow_linear_power_stage_reconstruction=True,
                allow_owned_locked_escapes=allow_owned_locked_escapes, timeout_s=_left(deadline))
            wired_identity = ground_leaf['wired_identity']
            _need(ground_leaf['scope'] == leaves.SCOPE
                and ground_leaf['source_native_binding'] == binding
                and ground_leaf['source_family'] == family and ground_leaf['code_identity'] == epoch
                and ground_leaf['pad_uuid'] == cap.force._uid(ground)
                and wired_identity['footprint_uuid'] == cap.force._uid(fp),
                'additional_aggregate_fresh_wired_Ground_role_required')
            canonical = wired_identity['canonical_source']
            original_assignment = wired_identity['unchanged_selected_bypass_assignments']
            domain, contract = wired_identity['aggregate_domain'], wired_identity['aggregate_contract']
            current = wired_identity['current_contract']; reference = None
            kind = 'aggregate_source_sink'
        elif old_ground:
            import cec_aggregate_cap_ground_leaf as leaves
            try:
                ground_leaf = leaves.plan(board, cap.force._uid(ground), board_hint=board_hint,
                    reference_group_uuid=group_uid, timeout_s=_left(deadline))
            except ValueError as exc:
                raise ValueError('additional_aggregate_old_Ground_copper_requires_separate_positive_owner:'+str(exc)) from exc
            # The DISTINCT fresh leaf already rederives canonical identity,
            # isolated supply, selected minima, whole-rail current and the
            # closed reference group in THIS call. Bind its exact epoch and
            # native Source before using those same observations. No caller
            # proof, cross-call cache, legacy alias or skipped guard exists.
            _need(ground_leaf['scope'] == leaves.SCOPE
                and ground_leaf['source'] == str(source)
                and ground_leaf['source_sha256'] == cap.force._hash(source)
                and ground_leaf['source_native_binding'] == binding
                and ground_leaf['source_family'] == family and ground_leaf['code_identity'] == epoch
                and ground_leaf['footprint_uuid'] == cap.force._uid(fp)
                and ground_leaf['pad_uuid'] == cap.force._uid(ground)
                and ground_leaf['owner'] == ref and ground_leaf['net'] == 'GND'
                and (ground_leaf['source_reference_map'] is not None) == (group_uid is not None),
                'additional_aggregate_fresh_Ground_role_Source_binding_required')
            canonical = ground_leaf['canonical_source']
            original_assignment = ground_leaf['unchanged_selected_bypass_assignments']
            domain, contract = ground_leaf['aggregate_domain'], ground_leaf['aggregate_contract']
            current = ground_leaf['current_contract']
            reference = ground_leaf['source_reference_map']
            kind = 'aggregate_source_sink'
        else:
            cap._owner(board, cap.force._uid(fp), group_uid, source)
            canonical = cap._canonical(board, fp, board_hint, deadline)
            original_assignment = cap._unassigned(board, fp, board_hint)
            graph = cap.fr._read_only_route_connectivity(board)
            _need(not {cap.force._uid(i) for i in graph.GetConnectedItems(positive)} - {cap.force._uid(positive)},
                  'additional_aggregate_Source_supply_must_be_isolated')
            kind, domain, contract = cap.full._model(board, source, str(positive.GetNetname()), board_hint)
            with cap.force._thermal_hint(board_hint):
                current = cap.cells._supply_current_widths(board, str(positive.GetNetname()))
            reference = None
            if group_uid:
                reference, = cap.maps.inspect_many(source, [(cap.force._uid(fp), group_uid)], timeout_s=_left(deadline))
        locality = canonical['locality_owner']; owner = fps.get(locality['owner_ref'])
        _need(owner is not None and (owner.GetReference() in poses or not require_explicit_owner)
            and (wired_identity is not None or owner.GetReference() not in poses or
                list(poses[owner.GetReference()][:2]) == [owner.GetPosition().x / 1e6, owner.GetPosition().y / 1e6]
                and (poses[owner.GetReference()][2] - owner.GetOrientationDegrees()) % 360 == 0),
            'additional_aggregate_requires_explicit_stationary_typed_owner')
        _need(cap.supply_role.supply_terminal_role(positive) == 'value_qualified_grounded_ceramic_supply_terminal',
              'additional_aggregate_positive_supply_role_required')
        _need(kind == 'aggregate_source_sink' and domain and domain.get('complete') is True
            and domain.get('source_refs') and domain.get('sink_refs') and ref not in domain['source_refs'],
            'additional_aggregate_complete_existing_source_domain_required')
        inventory = cap.ports.aggregate_ports(board, source, str(positive.GetNetname()), domain, contract, deadline)
        _need(current is not None and current['current_authority'] == contract['current_authority'],
              'additional_aggregate_unchanged_whole_rail_current_required')
        result[ref] = _wire(dict(schema=1, role='Source_additional_aggregate_macro_capacitor',
            source=str(source), source_sha256=cap.force._hash(source), source_family=family,
            code_identity=epoch, footprint_uuid=cap.force._uid(fp), source_pose=[fp.GetPosition().x / 1e6,
                fp.GetPosition().y / 1e6, fp.GetOrientationDegrees()], target_pose=target,
            source_fields=footprint_properties(fp), canonical_source=canonical, source_locality_owner=locality,
            unchanged_selected_bypass_assignments=original_assignment, source_reference_map=reference,
            supply_pad_uuid=cap.force._uid(positive), ground_pad_uuid=cap.force._uid(ground),
            aggregate_domain=domain, aggregate_contract=contract, current_contract=current,
            source_supply_inventory=inventory, source_supply_isolated=wired_identity is None,
            source_Ground_leaf=ground_leaf,
            ground_width_nm=max(200000, int(board.GetDesignSettings().m_TrackMinWidth),
                int(cap.cells._netclass(board, 'GND')['width'])), maximum_Ground_return_mm=.8,
            no_Source_copper_retirement=ground_leaf is None and wired_identity is None,
            Source_Ground_leaf_retirement_requires_fresh_independent_ownership=ground_leaf is not None,
            routing_admitted=False, current_authority=False,
            new_barrel_authority=False, release_authority=False))
        if wired_identity is not None:
            result[ref]['source_wired_identity'] = wired_identity
            result[ref]['source_wired_supply_cuts_require_separate_full_current_plan'] = True
    _need(binding == cap.row._source_binding(board) and epoch == cap.force._code_identity()
        and family == cap.force._family(source, board_hint), 'additional_aggregate_Source_epoch_changed')
    _left(deadline)
    return result


def _context(parent, child, proposal, deadline):
    import cec_source_aggregate_capacitor_cell as cap
    from cec_footprint_fields import footprint_properties
    import cec_control_gate_bias_placement as identity
    roles = proposal.get('additional_aggregate_capacitors', {})
    _need(type(roles) is dict, 'additional_aggregate_role_mapping_required')
    if not roles: return roles
    fresh = collect(parent, proposal['poses'], board_hint=proposal['board_hint'],
        reference_group_uuids=proposal.get('reference_group_uuids', ()), timeout_s=_left(deadline),
        excluded_refs=proposal.get('additional_aggregate_excluded_refs', ()),
        **({k: proposal[k] for k in ('allow_linear_power_stage_reconstruction', 'allow_owned_locked_escapes')
            if k in proposal}))
    _need(_wire(fresh) == _wire(roles), 'stale_or_forged_additional_aggregate_role')
    identities = set()
    for ref, proof in roles.items():
        _need(not identities.intersection((proof['footprint_uuid'], proof['supply_pad_uuid'], proof['ground_pad_uuid'])),
              'duplicate_additional_aggregate_request_identity')
        identities.update((proof['footprint_uuid'], proof['supply_pad_uuid'], proof['ground_pad_uuid']))
        fp = child.FindFootprintByReference(ref)
        _need(fp is not None and cap.force._uid(fp) == proof['footprint_uuid']
            and footprint_properties(fp) == proof['source_fields']
            and [fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6] == proof['target_pose'][:2]
            and (fp.GetOrientationDegrees() - proof['target_pose'][2]) % 360 == 0,
            'actual_additional_aggregate_child_identity_pose_required')
        original_fp = parent.FindFootprintByReference(ref)
        expected = pcbnew.FOOTPRINT(original_fp)
        expected.SetPosition(pcbnew.VECTOR2I(*(round(v * 1e6) for v in proof['target_pose'][:2])))
        expected.SetOrientationDegrees(proof['target_pose'][2])
        _need(identity._footprint(child, fp) == identity._footprint(child, expected),
              'additional_aggregate_only_exact_Source_cardinal_footprint_may_move')
        pads = {cap.force._uid(p): p for p in fp.Pads()}
        _need(proof['supply_pad_uuid'] in pads and proof['ground_pad_uuid'] in pads
            and pads[proof['supply_pad_uuid']].GetNetname() == proof['aggregate_contract']['net']
            and pads[proof['ground_pad_uuid']].GetNetname() == 'GND',
            'additional_aggregate_saved_rail_or_pad_changed')
        _need(cap._unassigned(child, fp, proposal['board_hint']) == proof['unchanged_selected_bypass_assignments'],
              'additional_aggregate_changed_minimum_bypass_assignment')
        owner = child.FindFootprintByReference(proof['source_locality_owner']['owner_ref'])
        original = parent.FindFootprintByReference(proof['source_locality_owner']['owner_ref'])
        expected_owner = pcbnew.FOOTPRINT(original) if original is not None else None
        wired = proof.get('source_wired_identity')
        if wired is not None and wired.get('coherent_owner_motion') is not None:
            target = wired['coherent_owner_motion']['target_pose']
            expected_owner.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
            expected_owner.SetOrientationDegrees(target[2])
        _need(owner is not None and expected_owner is not None
            and identity._footprint(child, owner) == identity._footprint(child, expected_owner),
            'additional_aggregate_locality_owner_moved')
    return roles


def _incident_cut_requests(parent, child, proposal, proof, plans, retired, positive, deadline):
    """Project every literal external full-current cut contact, not net peers.

    Per-edge plans can name a bend on another simultaneously replaced edge.
    Only those exact positively planned edges disappear here.  Every actual
    surviving contact is a separate full-width obligation, even when several
    shared an old coordinate.  Unproved conductor motion is never inferred.
    """
    import cec_source_aggregate_capacitor_cell as cap
    import cec_control_gate_bias_placement as identity
    planned = {u for plan in plans for u in plan['retired_track_uuids']}
    old_tracks = {cap.force._uid(t):t for t in parent.GetTracks()}
    live_tracks = {cap.force._uid(t):t for t in child.GetTracks()}
    old_pads = [p for f in parent.GetFootprints() for p in f.Pads()]
    live_pads = {cap.force._uid(p):p for f in child.GetFootprints() for p in f.Pads()}
    result = {}; seen = set()
    for plan in plans:
        _left(deadline)
        _need(plan['scope'] == 'exact_bounded_whole_current_planar_reflow'
            and set(plan['retired_track_uuids']) <= planned
            and plan['net'] == proof['aggregate_contract']['net'],
            'wired_aggregate_exact_current_boundary_plan_required')
        face = plan['layer_id']
        for boundary in plan['source_boundaries']:
            _need(boundary['restored'] is True and boundary['net'] == plan['net'],
                'wired_aggregate_positive_Source_current_boundary_required')
            for at in boundary.get('anchors_nm',[]):
                point = pcbnew.VECTOR2I(*at)
                contacts = [i for i in [*old_pads,*old_tracks.values()]
                    if i.GetNetname() == plan['net'] and i.IsOnLayer(face)
                    and i.GetEffectiveShape(face).Collide(point,0)]
                _need(contacts, 'wired_aggregate_literal_current_anchor_missing')
                for item in contacts:
                    uid = cap.force._uid(item)
                    if uid in planned: continue
                    _need(uid not in retired, 'wired_aggregate_current_boundary_co_cut_needs_separate_projection')
                    if item.GetClass() == 'PAD':
                        _need(uid in live_pads, 'wired_aggregate_current_boundary_pad_missing')
                        original = item.GetParentFootprint(); target = child.FindFootprintByReference(original.GetReference())
                        expected = pcbnew.FOOTPRINT(original)
                        pose = proposal['poses'].get(original.GetReference())
                        if pose is not None:
                            expected.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in pose[:2])))
                            expected.SetOrientationDegrees(pose[2])
                        _need(target is not None and identity._footprint(child,target) == identity._footprint(child,expected),
                            'wired_aggregate_current_boundary_exact_pad_owner_pose_required')
                        terminal = cap.ports.port(live_pads[uid])
                    else:
                        _need(uid in live_tracks and identity._track(parent,item) == identity._track(child,live_tracks[uid]),
                            'wired_aggregate_current_boundary_conductor_motion_needs_typed_projection')
                        _need(live_tracks[uid].IsOnLayer(face)
                            and live_tracks[uid].GetEffectiveShape(face).Collide(point,0),
                            'wired_aggregate_current_boundary_literal_contact_lost')
                        terminal = dict(at_nm=list(at),layers=[face],native_uuids=[uid])
                    # Cap SUP itself is the graph root, not a zero-length
                    # fictitious route. Other native contacts remain debts.
                    if uid == cap.force._uid(positive): continue
                    key = (uid,tuple(terminal['at_nm']),tuple(terminal['layers']),plan['width_nm'])
                    if key in seen: continue
                    seen.add(key)
                    name = 'aggregate_incident_cut:'+proof['footprint_uuid']+':'+str(len(result))
                    result[name] = dict(kind='source_boundary',net=plan['net'],a=cap.ports.port(positive),b=terminal,
                        width_nm=max(plan['width_nm'],plan['full_current_floor_nm']),
                        unchanged_full_rail_current_contract=proof['current_contract'],
                        source_full_current_incident_cut_plan=plan,
                        every_surviving_source_component_port_mandatory=True,
                        complete_macro_projected_boundaries_and_partitions_still_mandatory=True)
    return result


def _requests(parent, child, proposal, roles, deadline):
    import cec_source_aggregate_capacitor_cell as cap
    import cec_control_gate_bias_placement as identity
    if not roles: return {}
    old_tracks = {cap.force._uid(t): t for t in parent.GetTracks()}
    live_tracks = {cap.force._uid(t): t for t in child.GetTracks()}
    old_pads = {cap.force._uid(p): p for f in parent.GetFootprints() for p in f.Pads()}
    live_pads = {cap.force._uid(p): p for f in child.GetFootprints() for p in f.Pads()}
    retired = (set(proposal.get('retired_track_uuids', ()))
        | set(proposal.get('row_plan', {}).get('retired_track_uuids', ()))
        | (old_tracks.keys() - live_tracks.keys()))
    moving_pads = {cap.force._uid(p) for fp in parent.GetFootprints()
        if fp.GetReference() in proposal['poses'] and (
            [fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6] != list(proposal['poses'][fp.GetReference()][:2])
            or (fp.GetOrientationDegrees() - proposal['poses'][fp.GetReference()][2]) % 360 != 0)
        for p in fp.Pads()}
    requests = {}
    for ref, proof in roles.items():
        _left(deadline); fp = child.FindFootprintByReference(ref)
        original_fp = parent.FindFootprintByReference(ref)
        incident = {cap.force._uid(t) for t in parent.GetTracks() if any(
            p.GetNetCode() == t.GetNetCode() and t.IsOnLayer(face)
            and p.GetEffectiveShape(face).Collide(t.GetEffectiveShape(face), 0)
            for p in original_fp.Pads() for face in p.GetLayerSet().CuStack())}
        leaf = proof.get('source_Ground_leaf')
        leaf_ids = set(leaf['track_uuids']) if leaf else set()
        supply_cuts = (incident & retired) - leaf_ids
        current_cuts = []
        if supply_cuts and proof.get('source_wired_identity') is not None:
            # Wired identity does NOT grant retirement. Each actual incident
            # edge needs the established full-current planar Source proof,
            # including its complete fixed boundaries. The enclosing macro
            # must project/restore those boundaries and all native partitions.
            for uid in sorted(supply_cuts):
                edge = old_tracks[uid]
                _need(edge.GetNetname() == proof['aggregate_contract']['net'],
                    'wired_aggregate_only_separately_owned_supply_cuts')
                plan = cap.full.plan(parent, Path(proof['source']), board_hint=proposal['board_hint'],
                    retired_track_uuids=[uid], timeout_s=_left(deadline))
                # Roles are stable JSON receipts; the native planner still
                # returns tuple-valued layer/ref inventories. Compare the
                # same representation, not a weakened subset of the rating.
                _need(_wire(plan['contract']) == proof['aggregate_contract']
                    and plan['source_sha256'] == proof['source_sha256'],
                    'wired_aggregate_same_full_current_cut_authority_required')
                current_cuts.append(plan)
        else:
            _need(not supply_cuts, 'additional_aggregate_cannot_retire_original_incident_metal')
        if leaf:
            if proof.get('source_wired_identity') is not None:
                import cec_wired_aggregate_ground_leaf as leaves
            else:
                import cec_aggregate_cap_ground_leaf as leaves
            _need(leaf_ids <= retired and not leaf_ids & live_tracks.keys(),
                'additional_aggregate_complete_independently_owned_Ground_leaf_retirement_required')
            leaves.retained_contacts_unchanged(parent, child, leaf)
        pads = {cap.force._uid(p): p for p in fp.Pads()}; positive = pads[proof['supply_pad_uuid']]
        inventory = proof['source_supply_inventory']
        choices = [p for p in inventory['root_ports'] if p['pad_uuid'] not in moving_pads
            and p['pad_uuid'] in live_pads and p['pad_uuid'] in old_pads
            and identity._pad(live_pads[p['pad_uuid']]) == identity._pad(old_pads[p['pad_uuid']])]
        choices += [cap.ports.stroke_port(s, tuple(positive.GetPosition()))
            for s in inventory['retained_full_width_strokes'] if s['native_uuid'] not in retired
            and s['native_uuid'] in live_tracks and s['native_uuid'] in old_tracks
            and identity._track(child, live_tracks[s['native_uuid']]) == identity._track(parent, old_tracks[s['native_uuid']])]
        _need(choices, 'additional_aggregate_no_surviving_full_current_Source_carrier')
        carrier = min(choices, key=lambda p: (math.dist(p['at_nm'], tuple(positive.GetPosition())), repr(p)))
        owner_uid = proof['source_locality_owner']['pad_uuid']
        owner = next((p for f in child.GetFootprints() for p in f.Pads() if cap.force._uid(p) == owner_uid), None)
        locality = proof['source_locality_owner']; net = proof['aggregate_contract']['net']
        _need(owner is not None and owner.GetNetname() == net
            and tuple(map(int, positive.GetLayerSet().CuStack())) == (locality['face'],)
            and tuple(map(int, owner.GetLayerSet().CuStack())) == (locality['face'],)
            and math.dist(tuple(positive.GetPosition()), tuple(owner.GetPosition())) <= locality['maximum_distance_mm'] * 1e6,
            'additional_aggregate_actual_owner_locality_required')
        width = cap.full._source_width_floor(parent, Path(proof['source']), proof['aggregate_contract'], locality['face'])
        base = dict(net=net, a=cap.ports.port(positive), width_nm=width,
            unchanged_full_rail_current_contract=proof['current_contract'])
        entries = {
            'aggregate_cap_feed:' + proof['footprint_uuid']: dict(base, kind='source_boundary', b=carrier,
                every_surviving_source_component_port_mandatory=True),
            'aggregate_cap_local:' + proof['footprint_uuid']: dict(base, kind='local_supply',
                a=cap.ports.port(owner), b=cap.ports.port(positive),
                source_maximum_same_surface_path_mm=locality['maximum_supply_path_mm'],
                source_required_surface_layer=locality['face']),
            'ground:' + proof['ground_pad_uuid']: dict(kind='ground', net='GND',
                a=cap.ports.port(pads[proof['ground_pad_uuid']]), reach_mm=.8, width_nm=proof['ground_width_nm'])}
        if current_cuts:
            entries.update(_incident_cut_requests(parent,child,proposal,proof,current_cuts,retired,positive,deadline))
        _need(not requests.keys() & entries.keys(), 'duplicate_additional_aggregate_request_identity')
        requests.update(entries)
    return requests


def requests(parent, child, proposal):
    deadline = _deadline(10.)
    return _requests(parent, child, proposal, _context(parent, child, proposal, deadline), deadline)


def observe(parent, child, proposal, *, timeout_s=10.):
    """Independently rederive intent and observe actual complete saved copper."""
    import cec_source_aggregate_capacitor_cell as cap
    deadline = _deadline(timeout_s)
    roles = _context(parent, child, proposal, deadline)
    demands = _requests(parent, child, proposal, roles, deadline); rows = {}
    for ref, proof in roles.items():
        pads = {cap.force._uid(p): p for f in child.GetFootprints() for p in f.Pads()}
        positive = pads[proof['supply_pad_uuid']]; ground = pads[proof['ground_pad_uuid']]
        locality = proof['source_locality_owner']; floor = cap.full._source_width_floor(
            parent, Path(proof['source']), proof['aggregate_contract'], locality['face'])
        class LocalView:
            def GetTracks(self): return [t for t in child.GetTracks() if t.GetClass() in ('PCB_TRACK', 'PCB_ARC')
                and t.GetNetname() == positive.GetNetname() and int(t.GetLayer()) == locality['face'] and t.GetWidth() >= floor]
            def __getattr__(self, name): return getattr(child, name)
        local = cap.cells._shortest_track_path_mm(LocalView(), positive, pads[locality['pad_uuid']])
        _need(local is not None and local <= locality['maximum_supply_path_mm'],
              'additional_aggregate_actual_full_width_same_face_local_path_required')
        feed = demands['aggregate_cap_feed:' + proof['footprint_uuid']]
        connection = cap.ports.full_width_connection(parent, child, Path(proof['source']), feed,
            proposal['board_hint'], deadline)
        _need(connection is not None and connection.get('all_named_contacts_connected') is True
            and connection.get('zone_and_foreign_net_edges_excluded') is True,
            'additional_aggregate_actual_full_current_carrier_path_required')
        roots = []
        for root in proof['source_supply_inventory']['root_ports']:
            request = dict(feed, b=root)
            root_connection = cap.ports.full_width_connection(parent, child, Path(proof['source']), request,
                proposal['board_hint'], deadline)
            _need(root_connection is not None and root_connection.get('all_named_contacts_connected') is True
                and root_connection.get('zone_and_foreign_net_edges_excluded') is True,
                'additional_aggregate_actual_full_current_Source_root_path_required')
            roots.append(root_connection)
        cut_connections = []
        for key,request in demands.items():
            if not key.startswith('aggregate_incident_cut:'+proof['footprint_uuid']+':'):continue
            cut_connections.append(cap.ports.full_width_connection(parent,child,Path(proof['source']),request,
                proposal['board_hint'],deadline))
        class GroundView:
            def GetTracks(self): return [t for t in child.GetTracks() if t.GetNetname() == 'GND'
                and (t.GetClass() == 'PCB_VIA' or t.GetClass() in ('PCB_TRACK', 'PCB_ARC')
                     and int(t.GetLayer()) == locality['face'] and t.GetWidth() >= proof['ground_width_nm'])]
            def __getattr__(self, name): return getattr(child, name)
        immediate = cap.cells._existing_return(GroundView(), ground, .8, allow_native_track_body=True)
        _need(immediate is not None and immediate[0] <= .8, 'additional_aggregate_actual_immediate_Ground_required')
        via = immediate[1]
        blocked, _ = cap.fab.via_at_pad_conflicts(child, via.GetPosition(), via.GetWidth(via.TopLayer()),
            via.GetDrillValue(), via.GetNetCode())
        _need(blocked is None, 'additional_aggregate_actual_Ground_process_conflict')
        references = cap.reference._reference_contacts(child, via)
        rows[ref] = dict(actual_local_path_mm=local, actual_Ground_return_mm=immediate[0],
            Ground_via_uuid=cap.force._uid(via), actual_Ground_reference_contacts=references,
            full_current_carrier_connection=connection, full_current_Source_root_connections=roots,
            full_current_incident_cut_boundary_connections=cut_connections)
        _left(deadline)
    return _wire(dict(ok=True, complete=True, role='Source_additional_aggregate_macro_observation',
        capacitors=rows, routing_admitted=False, current_authority=False, new_barrel_authority=False,
        release_authority=False, enclosing_original_parent_macro_receiving_still_required=True))
