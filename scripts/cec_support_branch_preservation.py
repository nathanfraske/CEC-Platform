"""Independent proof for rebuilding unlocked pad-incident support branches.

An additive checkpoint cannot authorize placement. This narrower proof is used
only inside full placement revalidation: unchanged component/pad definitions,
bounded support motion, protected prefix/pairs/fill and fresh native grading
remain mandatory. No worker-supplied UUID allowlist is trusted.
"""
import pcbnew
from cec_local_copper_cell import copper_inventory


def _uid(item):
    return item.m_Uuid.AsString()


def _native_items(board):
    result = {}
    for item in [*(p for fp in board.GetFootprints() for p in fp.Pads()), *board.GetTracks()]:
        uid = _uid(item)
        if not uid or uid in result:
            raise ValueError('ambiguous native item identity')
        result[uid] = item
    return result


def _pad_chain_root(pad, contacts, terminal_points, items):
    """Identify a unique endpoint, optionally behind an in-land prefix.

Segmentation inside a land does not create a second electrical owner. Only
native convex pads can prove the complete centreline between their contained
nodes from endpoints alone. Custom/concave lands, through-pad paths and
disconnected re-entries remain outside this bounded proof.
    """
    roots = contacts & terminal_points
    if len(roots) != 1:
        return None
    root = next(iter(roots))
    if len(contacts) == 1:
        return root
    convex = {pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_CIRCLE,
              pcbnew.PAD_SHAPE_OVAL, pcbnew.PAD_SHAPE_ROUNDRECT}
    if pad.GetShape() not in convex:
        return None
    adjacency = {point: set() for point in contacts}
    for item in items:
        a, b = tuple(item.GetStart()), tuple(item.GetEnd())
        if a in contacts and b in contacts:
            adjacency[a].add(b)
            adjacency[b].add(a)
    reached, pending = set(), {root}
    while pending:
        point = pending.pop()
        if point in reached:
            continue
        reached.add(point)
        pending.update(adjacency[point] - reached)
    if reached != contacts:
        return None
    # A later segment cannot pass back through the land between outside
    # endpoints. This is exact native centreline collision, not a bbox test.
    shape = pad.GetEffectiveShape(items[0].GetLayer())
    for item in items:
        a, b = item.GetStart(), item.GetEnd()
        if tuple(a) not in contacts and tuple(b) not in contacts:
            if shape.Collide(pcbnew.SHAPE_SEGMENT(a, b, 0), 0):
                return None
    return root


def prove(source, candidate, moved_refs, *, max_branches=8):
    """Prove exact branch ownership and retention of every old native member.

Deletion/reconstruction of an unlocked, ungrouped straight-track chain
rooted inside the actual copper of exactly one moved SMD pad is eligible. A chain must
be unbranched, acyclic, on one layer/net and have its pad at an endpoint.
An internal unlocked/ungrouped path between moved pads may also follow their
independently proved exact rigid transform. Arbitrary geometry rewrites, vias,
arcs and unrelated copper are refused. Every
surviving pad/track/via in that
pad's original connected component must remain connected to its identical pad
UUID on the final, filled candidate. This includes far endpoints and any tees;
a lower whole-board airwire total cannot conceal a lost old ground return.
"""
    if type(max_branches) is not int or not 1 <= max_branches <= 8:
        raise ValueError('support branch proof requires a finite item bound')
    before, after = copper_inventory(source), copper_inventory(candidate)
    changed = sorted(uid for uid, value in before.items() if after.get(uid) != value)
    report = dict(ok=False, changed=changed, proved=[], release_authority=False,
                  remaining_parent_copper_unchanged=True, max_branches=max_branches)

    def refuse(reason, **evidence):
        return {**report, 'reason': reason, **evidence}

    if not changed:
        return {**report, 'ok': True, 'reason': 'parent_copper_unchanged'}
    if len(changed) > max_branches:
        return refuse('branch_count_exceeds_limit')
    old_items, new_items = _native_items(source), _native_items(candidate)
    grouped = {_uid(item) for group in source.Groups() for item in group.GetItems()}
    moving = set(moved_refs)
    pads = [p for fp in source.GetFootprints() if fp.GetReference() in moving
            for p in fp.Pads() if p.IsOnCopperLayer()]
    old_conn, new_conn = source.GetConnectivity(), candidate.GetConnectivity()
    rewritten = set(changed) & after.keys()
    deleted = set(changed) - rewritten
    if rewritten:
        import cec_rigid_cell_preservation as rigid
        proof = rigid.prove(source, candidate, moving, rewritten, max_items=max_branches)
        report['rigid_internal_copper'] = proof
        if not proof['ok']:
            return refuse(proof['reason'])
        for cell in proof['proved']:
            for pad_id in cell['pad_uuids']:
                old_pad = old_items[pad_id]
                if pad_id not in new_items:
                    return refuse('moved_pad_identity_lost', refused_uuid=pad_id)
                expected = ({pad_id} | {_uid(obj) for obj in old_conn.GetConnectedItems(old_pad)
                    if _uid(obj) in old_items and obj.GetNetname() == old_pad.GetNetname()}) - deleted
                restored = {pad_id} | {_uid(obj) for obj in new_conn.GetConnectedItems(new_items[pad_id])
                    if _uid(obj) in new_items and obj.GetNetname() == old_pad.GetNetname()}
                missing = sorted(expected-restored)
                if missing:
                    return refuse('rigid_cell_original_component_not_restored',missing_native_members=missing)
            report['proved'].extend(dict(uuid=uid,mode='exact_internal_rigid_motion',
                chain=cell['uuids'],restored=True) for uid in cell['uuids'] if uid in rewritten)
    endpoints = {}
    for uid in deleted:
        item = old_items[uid]
        if uid in after or item.GetClass() != 'PCB_TRACK' or item.IsLocked() or uid in grouped:
            return refuse('not_an_unlocked_incident_branch_removal', refused_uuid=uid)
        ends = {tuple(item.GetStart()), tuple(item.GetEnd())}
        if len(ends) != 2 or item.GetNetCode() <= 0:
            return refuse('invalid_incident_branch', refused_uuid=uid)
        for point in ends:
            key = (item.GetNetCode(), item.GetLayer(), point)
            endpoints.setdefault(key, set()).add(uid)

    # Infer bounded ownership from source copper, not from a cleanup worker's
    # deletion list or a same-net match. Exact endpoint adjacency permits a
    # pruned tail after the pad-incident leg without authorizing arbitrary
    # edits elsewhere in the original connected component.
    adjacency = {uid: set() for uid in deleted}
    for members in endpoints.values():
        for uid in members:
            adjacency[uid].update(members - {uid})
    remaining = set(deleted)
    while remaining:
        chain, frontier = set(), {min(remaining)}
        while frontier:
            uid = frontier.pop()
            if uid in chain:
                continue
            chain.add(uid)
            frontier.update(adjacency[uid] - chain)
        remaining.difference_update(chain)
        uid = min(chain)
        item = old_items[uid]
        nodes = {key: members for key, members in endpoints.items() if members & chain}
        if any(len(members) > 2 for members in nodes.values()):
            return refuse('deleted_branch_is_not_a_simple_chain', refused_uuid=uid)
        terminal_points = {key[2] for key, members in nodes.items() if len(members) == 1}
        if len(terminal_points) != 2:
            return refuse('deleted_branch_is_not_a_simple_chain', refused_uuid=uid)
        owners = []
        for pad in pads:
            if (pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                    or pad.GetNetCode() != item.GetNetCode()
                    or not pad.IsOnLayer(item.GetLayer())):
                continue
            shape = pad.GetEffectiveShape(item.GetLayer())
            contacts = {key[2] for key in nodes
                        if shape.Collide(pcbnew.VECTOR2I(*key[2]), 0)}
            if contacts:
                owners.append((pad, contacts))
        if len(owners) != 1:
            return refuse('ambiguous_or_unowned_incident_branch', refused_uuid=uid)
        pad, contacts = owners[0]; pad_id = _uid(pad)
        # Exact native containment, not a centre-distance epsilon or bbox.
        # A contiguous segmented prefix inside one convex land has the same
        # unique root as a single segment. Do not admit interior ownership,
        # through-pad paths, custom-pad assumptions or disconnected re-entry.
        root_contact = _pad_chain_root(pad, contacts, terminal_points,
            [old_items[member_id] for member_id in sorted(chain)])
        if root_contact is None:
            return refuse('moved_pad_not_at_chain_root', refused_uuid=uid)
        if pad_id not in new_items:
            return refuse('moved_pad_identity_lost', refused_uuid=uid)
        original = {pad_id} | {_uid(obj) for obj in old_conn.GetConnectedItems(pad)
                              if _uid(obj) in old_items and obj.GetNetname() == item.GetNetname()}
        if not chain <= original:
            return refuse('source_branch_not_natively_connected', refused_uuid=uid)
        expected = original - deleted
        # A free stub does not provide an independently identifiable boundary.
        if not (expected - {_uid(p) for p in pads}):
            return refuse('missing_surviving_route_boundary', refused_uuid=uid)
        restored = {pad_id} | {_uid(obj) for obj in new_conn.GetConnectedItems(new_items[pad_id])
                              if _uid(obj) in new_items and obj.GetNetname() == item.GetNetname()}
        missing = sorted(expected - restored)
        if missing:
            return refuse('original_component_not_restored', refused_uuid=uid,
                          missing_native_members=missing)
        for member_id in sorted(chain):
            report['proved'].append(dict(uuid=member_id, chain=sorted(chain),
                ref=pad.GetParentFootprint().GetReference(), pad_uuid=pad_id,
                pad=str(pad.GetNumber()), net=item.GetNetname(),
                root_contact_nm=list(root_contact), contact_tolerance_nm=0,
                root_mode='convex_land_prefix' if len(contacts) > 1 else 'single_contact',
                pad_contact_nodes_nm=[list(point) for point in sorted(contacts)],
                retained_native_members=len(expected), restored=True))
    return {**report, 'ok': True, 'reason': 'owned_incident_branches_rebuilt'}
