"""Recognize a private local support cell, never grant placement authority.

A divider/filter junction has more than two pads but need not be a shared bus.
Every terminal must be accounted for: exactly one nominated owner pin plus a
bounded, nearby set of unlocked two-terminal SMD supports. Final motion and
whole-board electrical/copper gates still decide whether any pose is legal.
"""
import math
import copy
import pcbnew


def private_cell(board, net, endpoint, peer, *, max_members=3, radius_mm=3.0):
    if (type(max_members) is not int or not 1 <= max_members <= 3
            or type(radius_mm) not in (int, float) or not math.isfinite(radius_mm)
            or not 0 < radius_mm <= 3.0):
        raise ValueError('private support cell limits exceed the existing local envelope')

    def refusal(reason):
        return dict(ok=False, reason=reason, release_authority=False)

    code = board.GetNetInfo().GetNetItem(str(net))
    if code is None or code.GetNetCode() <= 0:
        return refusal('net_missing')
    code = code.GetNetCode()
    endpoints = [(fp, pad) for fp in board.GetFootprints() for pad in fp.Pads()
                 if pad.IsOnCopperLayer() and pad.GetNetCode() == code]
    signature = lambda fp, pad: (fp.GetReference(), str(pad.GetNumber()))
    owner_pads = [(fp, pad) for fp, pad in endpoints if fp.GetReference() == peer[0]]
    if len(owner_pads) != 1 or signature(*owner_pads[0]) != tuple(peer):
        return refusal('owner_is_not_one_exact_terminal')
    supports = [(fp, pad) for fp, pad in endpoints if fp.GetReference() != peer[0]]
    if sum(signature(fp, pad) == tuple(endpoint) for fp, pad in supports) != 1:
        return refusal('support_endpoint_not_unique')
    refs = [fp.GetReference() for fp, pad in supports]
    if not 1 <= len(refs) <= max_members or len(set(refs)) != len(refs):
        return refusal('outside_private_cell_terminal_bound')
    grouped = {item.GetReference() for group in board.Groups() for item in group.GetItems()
               if item.GetClass() == 'FOOTPRINT'}
    primary = board.FindFootprintByReference(endpoint[0])
    origin = primary.GetPosition()
    distances = {}
    for fp, pad in supports:
        ref = fp.GetReference()
        pads = [p for p in fp.Pads() if p.IsOnCopperLayer()]
        if (fp.IsLocked() or ref in grouped or ref.upper().startswith(('J','H','FID','LOGO','MK'))
                or len(pads) != 2 or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                                        for p in pads)):
            return refusal('nonmovable_or_not_two_terminal_smd')
        pos = fp.GetPosition()
        distance = math.hypot(pos.x-origin.x, pos.y-origin.y)/1e6
        if distance > radius_mm:
            return refusal('nonlocal_support_terminal')
        distances[ref] = distance
    companions = sorted((ref for ref in refs if ref != endpoint[0]),
                         key=lambda ref: (distances[ref], ref))
    return dict(ok=True, reason='private_local_support_cell',
        owner=dict(ref=peer[0], pad=peer[1]), primary=endpoint[0], companions=companions,
        terminals=sorted(signature(fp, pad) for fp, pad in endpoints),
        radius_mm=radius_mm, max_members=max_members, release_authority=False)


def stationary_partition(board, target, retained=()):
    """Account for a whole private electrical cell without moving all of it.

    Native mechanical groups remain forbidden by private_cell and the motion
    gate. This recognizes only declared, live local electrical companions;
    the caller must preserve stationary poses and restore every cut boundary.
    """
    expected = tuple(target.get('companion_refs') or ())
    def refuse(reason):
        return dict(ok=False, reason=reason, release_authority=False)
    if (target.get('motion') != 'toward_endpoint' or not expected
            or len(set(expected)) != len(expected)
            or not isinstance(retained, (list, tuple))
            or any(not isinstance(ref, str) or not ref for ref in retained)
            or len(set(retained)) != len(retained)
            or not set(retained) < set(expected)):
        return refuse('invalid_private_stationary_partition')
    owner = board.FindFootprintByReference(target.get('ref', ''))
    pads = [p for p in owner.Pads() if p.GetNetname() == target.get('target_net')] if owner else []
    if len(pads) != 1:
        return refuse('primary_terminal_not_unique')
    proof = private_cell(board, target['target_net'], (target['ref'], str(pads[0].GetNumber())),
        (target.get('endpoint_ref', ''), target.get('endpoint_pad', '')))
    if not proof['ok'] or set(proof.get('companions') or ()) != set(expected):
        return refuse('declared_private_cell_not_live')
    return dict(ok=True, reason='private_companions_accounted_as_stationary',
        moving_refs=[target['ref'], *retained], stationary_refs=sorted(set(expected)-set(retained)),
        topology=proof, release_authority=False, restoration_and_pose_proof_required=True)


def articulated_primaries(board, target):
    """Finite alternative moving members of the SAME original private cell.

    Endpoint identity selects a certified net, not necessarily the one support
    that must move. Each alternative retains every other terminal explicitly
    and earns its own original-source topology proof. No mechanical group,
    new component, coordinate or shared-bus terminal is introduced.
    """
    if not stationary_partition(board, target, ())['ok']: return []
    refs = [target['ref'], *target['companion_refs']]
    result = []
    for ref in refs:
        alternative = copy.deepcopy(target)
        alternative.update(ref=ref, companion_refs=[other for other in refs if other != ref])
        if stationary_partition(board, alternative, ())['ok']:
            result.append(alternative)
    return result
