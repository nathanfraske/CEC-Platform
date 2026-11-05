"""Bounded independent support-cell construction, never board admission.

Locally certified cells may need different displacements to expose both
ends of a route. Construct the complete proposal in a new private family,
with one original-parent motion/branch budget. No intermediate becomes an
incumbent. Every incident boundary remains an explicit restoration obligation.
The caller still owes full physical, electrical, connectivity and original-
parent copper/fill admission; success here means only 'candidate constructed'.
"""
import copy
from pathlib import Path

import pcbnew
import cec_support_motion as motion


def validate(board, cells, policy):
    policy = motion.limits(**policy)
    if not isinstance(cells, (list, tuple)) or not 2 <= len(cells) <= 4:
        return dict(ok=False, reason='two_to_four_bounded_cells_required')
    if any(not isinstance(cell,dict) or not isinstance(cell.get('target'),dict)
           or not isinstance(cell.get('candidate'),dict) for cell in cells):
        return dict(ok=False, reason='invalid_cell')
    by_primary = {cell['target'].get('ref'):cell for cell in cells}
    effective, occupied, proofs, stationary, partitions = [], set(), [], set(), []
    endpoint_owners = set()
    net = None
    for cell in cells:
        if not isinstance(cell, dict) or not isinstance(cell.get('target'), dict) or not isinstance(cell.get('candidate'), dict):
            return dict(ok=False, reason='invalid_cell')
        target, candidate = copy.deepcopy(cell['target']), copy.deepcopy(cell['candidate'])
        if candidate.get('mobility_companion_refs') is not None:
            if (not isinstance(candidate['mobility_companion_refs'], (list, tuple))
                    or any(not isinstance(r, str) or not r for r in candidate['mobility_companion_refs'])):
                return dict(ok=False, reason='required_cell_companion_dropped')
            if not set(target.get('companion_refs') or ()) <= set(candidate['mobility_companion_refs']):
                import cec_support_cell_topology as topology
                partition = topology.stationary_partition(board, target, candidate['mobility_companion_refs'])
                declared = candidate.get('stationary_companion_refs')
                articulated = candidate.get('independent_companion_refs', [])
                if (not partition['ok'] or
                        not isinstance(declared, (list, tuple))
                        or not isinstance(articulated, (list, tuple))
                        or any(not isinstance(ref, str) or not ref for ref in declared)
                        or any(not isinstance(ref, str) or not ref for ref in articulated)
                        or len(set(declared)) != len(declared)
                        or len(set(articulated)) != len(articulated)
                        or set(declared) & set(articulated)
                        or set(declared) | set(articulated) != set(partition['stationary_refs'])):
                    return dict(ok=False, reason='required_cell_companion_dropped')
                for peer_ref in articulated:
                    peer = by_primary.get(peer_ref)
                    if (not peer or any(peer['target'].get(k)!=target.get(k)
                            for k in ('target_net','endpoint_ref','endpoint_pad'))
                            or target['ref'] not in peer['candidate'].get('independent_companion_refs', [])
                            or set(peer['target'].get('companion_refs') or ()) | {peer_ref}
                               != set(target.get('companion_refs') or ()) | {target['ref']}):
                        return dict(ok=False, reason='independent_companion_not_reciprocally_proved')
                partition = dict(partition,stationary_refs=list(declared),
                    independently_moved_refs=list(articulated))
                stationary.update(declared)
                partitions.append(partition)
            target['companion_refs'] = list(candidate['mobility_companion_refs'])
        refs = {target.get('ref'), *(target.get('companion_refs') or ())}
        if refs & occupied:
            return dict(ok=False, reason='independent_cells_overlap')
        occupied.update(refs)
        if len(occupied) > policy['max_refs']:
            return dict(ok=False, reason='compound_support_scope_exceeded')
        this_net = target.get('target_net')
        if not isinstance(this_net, str) or not this_net or (net is not None and net != this_net):
            return dict(ok=False, reason='cells_do_not_share_certified_target_net')
        net = this_net
        domain = motion.capture(board, target, policy)
        proof = motion.evaluate(domain, candidate)
        proofs.append(proof)
        if not proof['ok']:
            return dict(ok=False, reason=proof['reason'], motion=proofs)
        for ref in refs:
            fp = board.FindFootprintByReference(ref)
            if len([pad for pad in fp.Pads() if pad.IsOnCopperLayer()]) > 2:
                endpoint_owners.add(ref)
        if len(endpoint_owners) > 1:
            return dict(ok=False, reason='multiple_endpoint_owners_outside_scope')
        effective.append(dict(target=target, candidate=candidate))
    if stationary & occupied:
        return dict(ok=False, reason='stationary_companion_moved_by_other_cell')
    return dict(ok=True, cells=effective, refs=sorted(occupied), motion=proofs,
                stationary_refs=sorted(stationary), stationary_partitions=partitions,
                release_authority=False)


def construct(source, destination, cells, policy, *, max_branch_tracks=8):
    """Stage disjoint cell motions without changing or replacing the source.

    Locks and generated-copper provenance are resolved by the existing native
    worker at each step. Repeated cells, over-budget combined rip-up, unknown
    ownership or a refused second step cannot produce a completed candidate.
    Failed staging remains explicitly speculative for forensic inspection.
    """
    import cec_certificate_repair as repair
    import cec_full_pipeline as pipeline
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise ValueError('compound construction requires a new private board')
    if type(max_branch_tracks) is not int or not 1 <= max_branch_tracks <= 8:
        raise ValueError('compound branch budget must be within independent admission limits')
    inputs = pipeline._artifact_rows(p for p in pipeline._placement_authority_family(source)
                                    if Path(p).is_file())
    original = pcbnew.LoadBoard(str(source))
    proof = validate(original, cells, policy)
    result = dict(schema=1, constructed=False, release_authority=False,
        source_sha256=pipeline.sha256_file(source), domain=proof, steps=[])
    try:
        if not proof['ok']:
            result['reason'] = proof['reason']
            return result
        def stationary_poses(board):
            return {ref: (tuple(board.FindFootprintByReference(ref).GetPosition()),
                          board.FindFootprintByReference(ref).GetOrientationDegrees(),
                          board.FindFootprintByReference(ref).IsFlipped())
                    for ref in proof['stationary_refs']}
        stationary_before = stationary_poses(original)
        repair._copy_board_family(str(source), str(destination))
        removed, moved_tracks, moved_vias, fixed_vias, nets = set(), set(), set(), set(), set()
        fixed_tracks = set()
        anchors = []
        for cell in proof['cells']:
            # Receipt resolution is fresh after the preceding explicit producer
            # boundary. The original source, not the first shifted board,
            # remains the authored baseline throughout this compound proposal.
            authority = repair._generated_locked_route_uuids(str(destination), str(source))
            changed, evidence = repair._relocate_footprint_worker(
                str(destination), cell['target'], cell['candidate'],
                max_branch_tracks=max_branch_tracks,
                max_copper_pads=policy.get('max_owner_copper_pads', 2),
                generated_locked_uuids=authority)
            result['steps'].append(dict(**cell, changed=changed, move=evidence))
            if not changed:
                result['reason'] = evidence.get('refusal', 'cell_motion_refused')
                return result
            removed.update(evidence.get('removed_track_uuids') or ())
            if len(removed) > max_branch_tracks:
                result['reason'] = 'compound_incident_branch_budget_exceeded'
                return result
            moved_tracks.update(evidence.get('moved_internal_track_uuids') or ())
            moved_vias.update(evidence.get('moved_pad_via_uuids') or ())
            fixed_vias.update(evidence.get('preserved_locked_pad_via_uuids') or ())
            fixed_tracks.update(evidence.get('preserved_incident_track_uuids') or ())
            nets.update(evidence.get('affected_nets') or ())
            anchors.extend(copy.deepcopy(evidence.get('preserved_anchors') or ()))
        result['stationary_companions_unchanged'] = (
            stationary_before == stationary_poses(pcbnew.LoadBoard(str(destination))))
        if not result['stationary_companions_unchanged']:
            result['reason'] = 'stationary_companion_pose_changed'
            return result
        # Sequential cell staging may remove both sides of a once-internal
        # branch. Its old intermediate coordinate is no longer an electrical
        # boundary. Rebind only a natively proved isolated two-pad branch;
        # all other obligations remain exact original boundary obligations.
        from cec_compound_boundaries import rebind_internal_branches
        boundaries = rebind_internal_branches(original,pcbnew.LoadBoard(str(destination)),
            anchors,removed,proof['refs'])
        result['boundary_rebinding'] = boundaries
        if not boundaries['ok']:
            result['reason'] = boundaries['reason']
            return result
        anchors = boundaries['anchors']
        result.update(constructed=True, reason='private_candidate_constructed',
            board=str(destination), moved_refs=proof['refs'],
            restoration=dict(preserved_anchors=anchors, affected_nets=sorted(nets),
                removed_track_uuids=sorted(removed), moved_internal_track_uuids=sorted(moved_tracks),
                preserved_incident_track_uuids=sorted(fixed_tracks),
                moved_pad_via_uuids=sorted(moved_vias), preserved_locked_pad_via_uuids=sorted(fixed_vias)))
        return result
    finally:
        result['input_families_unchanged'] = pipeline.artifacts_match(inputs)
        if not result['input_families_unchanged']:
            result.update(constructed=False, reason='input_family_changed')
