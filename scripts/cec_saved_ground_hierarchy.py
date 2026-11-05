"""Independently receive a source-selected saved owner/cap ground hierarchy.

Fallback after canonical immediate return only. No capacitor reach extension,
worker-selected dependency graph, arbitrary GND neighbour or current authority.
"""
import math
import time


def _surface_link(board, left, right, width_nm, *, new_endpoint_ids=()):
    """Full-class surface copper plus internally re-received new endpoints.

    The private scope is produced below from actual parent/child deltas and
    freshly compiled source requests. Old thin copper or a group label alone
    is never a hierarchy path. No zone/barrel edge participates.
    """
    import cec_decoupler_cell as cells
    if (left.HasHole() or right.HasHole() or left.GetNetname() != 'GND'
            or right.GetNetname() != 'GND'):
        return None
    layers = set(left.GetLayerSet().CuStack()) & set(right.GetLayerSet().CuStack())
    if len(layers) != 1:
        return None
    layer = next(iter(layers)); material = list(board.GetTracks())
    if len(material) > 16384:
        raise ValueError('bounded_saved_ground_link_inventory')
    selected = [t for t in material if t.GetClass() == 'PCB_TRACK'
        and t.GetNetname() == 'GND' and t.GetLayer() == layer
        and (t.GetWidth() >= width_nm or t.m_Uuid.AsString() in new_endpoint_ids)]
    class Surface:
        def GetTracks(self):
            return selected
        def __getattr__(self, key):
            return getattr(board, key)
    return cells._shortest_track_path_mm(Surface(), left, right, snap_mm=.000001)


def _chain(start, entries, root, link):
    seen = set(); at = start; proofs = []
    for _ in range(4):
        if at == root:
            return proofs
        if at in seen or at not in entries:
            raise ValueError('unrooted_or_circular_source_ground_hierarchy')
        seen.add(at); entry = entries[at]; peer = entry['portal_pad_uuid']
        length, limit = link(at, peer, entry)
        if (type(length) not in (int, float) or not math.isfinite(length) or length < 0
                or type(limit) not in (int, float) or not math.isfinite(limit)
                or not 0 < limit <= 4 or length > limit + 1e-9):
            raise ValueError('saved_source_directed_ground_link_missing_or_long')
        proofs.append(dict(from_uuid=at, to_uuid=peer, path_mm=length, limit_mm=limit))
        at = peer
    raise ValueError('bounded_source_ground_hierarchy_depth')


def _new_ground_prefixes(parent,child,requests,*,board_hint,deadline,source_proposal):
    """Independent exact-new delta/source compiler; never a caller ID waiver."""
    import json
    import cec_cell_escape_replan as escape
    import cec_cell_endpoint_groups as endpoints
    import cec_force_current as force
    import cec_decoupler_cell as cells
    before={force._uid(t) for t in parent.GetTracks()}
    added=[t for t in child.GetTracks() if force._uid(t) not in before and t.GetNetname()=='GND']
    if len(added)>256:raise ValueError('bounded_saved_ground_prefix_delta_required')
    width=max(200000,int(child.GetDesignSettings().m_TrackMinWidth),
        int(cells._netclass(child,'GND')['width']))
    if not any(t.GetClass()=='PCB_TRACK' and t.GetWidth()<width for t in added):
        return dict(track_uuids=[],proofs=[])
    if (type(source_proposal) is not dict
            or source_proposal.get('scope')!='source_typed_complete_cell_escape_proposal'
            or source_proposal.get('board_hint')!=board_hint):
        raise ValueError('saved_ground_prefix_fresh_source_plan_required')
    fresh=escape.recompile_source_proposal(parent,source_proposal,board_hint=board_hint)
    if fresh!=source_proposal:raise ValueError('saved_ground_prefix_source_plan_changed_or_forged')
    for ref,pose in fresh['poses'].items():
        fp=child.FindFootprintByReference(ref)
        if (fp is None or tuple(fp.GetPosition())!=tuple(round(v*1e6) for v in pose[:2])
                or abs((fp.GetOrientationDegrees()-pose[2]+180)%360-180)>1e-9
                or fp.IsFlipped()!=parent.FindFootprintByReference(ref).IsFlipped()):
            raise ValueError('saved_ground_prefix_native_pose_not_source_plan')
    expected={k:r for k,r in escape.obligations(parent,child,fresh).items() if r['kind']=='ground'}
    supplied={k:r for k,r in requests.items() if r['kind']=='ground'}
    stable=lambda x:json.dumps(x,sort_keys=True,allow_nan=False)
    if stable(expected)!=stable(supplied):
        raise ValueError('saved_ground_prefix_requests_not_fresh_source_compilation')
    if time.monotonic()>=deadline:raise ValueError('saved_ground_prefix_source_deadline')
    return endpoints.receive(parent,child,expected,added,board_hint=board_hint,deadline=deadline)


def receive(parent, child, request, requests, *, board_hint, deadline, source_proposal=None):
    import cec_force_current as force
    import cec_constraints as constraints
    import cec_cell_escape_replan as escape
    import cec_decoupler_cell as cells
    import cec_device_power_roles as roles
    import cec_ground_return_policy as policy
    import cec_cell_row_rebuild as row
    if (type(deadline) not in (int, float) or not math.isfinite(deadline)
            or time.monotonic() >= deadline or type(board_hint) is not str or not board_hint):
        raise ValueError('saved_ground_hierarchy_deadline_or_source_context')
    if request.get('kind') != 'ground' or request.get('net') != 'GND':
        raise ValueError('typed_ground_request_required')
    binding = [row._source_binding(b) for b in (parent, child)]
    uid = request['a']['pad_uuid']
    pads = {force._uid(p): p for f in child.GetFootprints() for p in f.Pads()}
    old = {force._uid(p): p for f in parent.GetFootprints() for p in f.Pads()}
    pad, source = pads.get(uid), old.get(uid)
    if pad is None or source is None or pad.GetNetname() != 'GND' or source.GetNetname() != 'GND':
        raise ValueError('exact_source_ground_land_required')
    owner = source.GetParentFootprint(); model = roles.footprint_contract(owner)
    if (not model or model['pins'].get(source.GetNumber()) not in
            ('ground', 'power_return', 'reference', 'address')
            or roles.footprint_contract(pad.GetParentFootprint()) != model
            or force._uid(pad.GetParentFootprint()) != force._uid(owner)
            or pad.GetNumber() != source.GetNumber()
            or any(r in ('power_output', 'switch', 'feedback') for r in model['pins'].values())):
        raise ValueError('source_low_power_ground_role_required')
    with force._thermal_hint(board_hint):
        assignment = constraints._device_bypass_assignment(parent, project_max_mm=3.5)
    selected = {}
    for item in assignment['assigned'].values():
        req = item['requirement']
        # A device can also require a VIO-to-VCC (or other interrail)
        # capacitor. That fresh Source requirement is not a Ground portal.
        # Keep its separate return role unchanged; the Ground-rooted subset
        # below still owes assigned_ground_entries' unique assignment and
        # actual two-land GND/supply checks on BOTH parent and saved child.
        if (req['ref'] == owner.GetReference()
                and (req.get('return_rail') or 'GND') == 'GND'):
            cap = item['cap_ref']; value = dict(owner=req['ref'], pin=str(req['pin']), rail=req['rail'])
            if cap in selected:
                raise ValueError('unique_source_bypass_assignment_required')
            selected[cap] = value
    if not selected:
        raise ValueError('source_selected_bypass_required')
    source_entries = escape.assigned_ground_entries(parent, selected, board_hint=board_hint)
    entries = escape.assigned_ground_entries(child, selected, board_hint=board_hint)
    if uid not in source_entries or uid not in entries:
        raise ValueError('source_and_saved_ground_hierarchy_required')
    entry = entries[uid]
    def stable(value):
        import json
        return json.loads(json.dumps(value, allow_nan=False))
    if stable(request.get('selected_bypass_entry')) != stable(entry):
        raise ValueError('saved_request_not_fresh_source_assigned_hierarchy')
    if request.get('reach_mm') != policy.reach(pad, entries):
        raise ValueError('source_ground_reach_contract_changed')
    root = entry['root_portal_pad_uuid']; root_request = requests.get('ground:' + root)
    if (root not in pads or not root_request or root_request.get('kind') != 'ground'
            or root_request.get('net') != 'GND'
            or root_request.get('a', {}).get('pad_uuid') != root
            or root_request.get('reach_mm') != .8
            or pads[root].GetParentFootprint().GetReference() != entry['selected_bypass']):
        raise ValueError('mandatory_selected_cap_immediate_ground_obligation_missing')
    immediate = cells._existing_return(child, pads[root], .8, allow_native_track_body=True)
    if immediate is None:
        raise ValueError('selected_cap_immediate_return_missing')
    prefix=_new_ground_prefixes(parent,child,requests,board_hint=board_hint,
        deadline=deadline,source_proposal=source_proposal)
    endpoint_ids=frozenset(prefix['track_uuids'])
    def link(a, b, edge):
        if time.monotonic() >= deadline:
            raise ValueError('saved_ground_hierarchy_deadline')
        if edge['root_portal_pad_uuid'] != root or b not in pads:
            raise ValueError('ground_hierarchy_root_changed')
        # Explicit native surface trace graph only: a plane or a globally
        # connected via is not a short package-to-cap link.
        spec = cells._netclass(child, 'GND')
        path = _surface_link(child, pads[a], pads[b], max(200000,
            int(child.GetDesignSettings().m_TrackMinWidth), int(spec['width'])),
            new_endpoint_ids=endpoint_ids)
        limit = min(4., edge['max_link_mm'], cells._local_supply_limit_mm(edge['direct_mm'],
            max(200000, int(spec['width'])) / 1e6, max(200000, int(spec['clearance'])) / 1e6))
        return path, limit
    links = _chain(uid, entries, root, link)
    if binding != [row._source_binding(b) for b in (parent, child)]:
        raise ValueError('saved_ground_hierarchy_mutated_native_source')
    return dict(ok=True, scope='independently_source_assigned_saved_ground_hierarchy', links=links,
        root_cap_uuid=root, root_return_mm=immediate[0], root_return_max_mm=.8,
        independently_received_new_ground_prefixes=prefix,
        via_uuid=force._uid(immediate[1]), current_authority=False, release_authority=False)
