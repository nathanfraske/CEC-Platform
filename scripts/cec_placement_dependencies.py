"""Electrical collateral cells for bounded placement, never release authority.

Membership comes from existing topology and craft contracts, not reference
names or board coordinates. Primary repair transforms remain intentional;
secondary eviction must translate the whole transitive dependency group.
"""
import cec_placement_station_groups as stations


def from_board(board_path, *, craft=None, follower_groups=None):
    import cec_synth_pipeline as synth
    context = stations.from_board(board_path)
    if not context.get('ok'):
        return context
    try:
        detection = (craft or {}).get('detection_cell') or {}
        # Older receipts contain only failed pairs. Derive all relationships,
        # including currently passing ones, from the same checker contract.
        if ('details' not in detection
                or any('terminal_pairs' not in row for row in detection.get('details', ()))):
            detection = synth._oracle_comparator_adjacency(str(board_path))
        if detection.get('error') or 'details' not in detection:
            raise ValueError('electrical dependency evidence unavailable')
        rows = [dict(physical_refs=group) for group in context['groups']]
        rows.extend(dict(physical_refs=row['refs']) for row in detection['details'])
        rows.extend(dict(physical_refs=[owner, *refs])
                    for owner, refs in (follower_groups or {}).items())
        rows.extend(dict(physical_refs=[row.get('owner_ref'), row.get('cap_ref')])
                    for row in ((craft or {}).get('decoupler') or {}).get('details', ()))
        import pcbnew
        import cec_placement_relation_guard as relations
        bound_craft=dict(craft or {}, detection_cell=detection)
        relation_guard=relations.build(pcbnew.LoadBoard(str(board_path)),bound_craft)
        import hashlib
        from pathlib import Path
        if hashlib.sha256(Path(board_path).read_bytes()).hexdigest()!=context['board_sha256']:
            raise ValueError('native dependency source changed during binding')
        return dict(context, groups=stations.station_groups(rows), relation_guard=relation_guard,
                    scope='electrical collateral restriction; no route admission')
    except Exception as exc:
        return dict(ok=False, groups=[], error=f'{type(exc).__name__}: {exc}')


def cells(owner_by_cap, caps_by_owner, groups=()):
    """Merge ownership and electrical links without dropping missing members."""
    rows = [dict(physical_refs=group) for group in groups]
    rows.extend(dict(physical_refs=[owner, *refs]) for owner, refs in caps_by_owner.items())
    rows.extend(dict(physical_refs=[owner, ref]) for ref, owner in owner_by_cap.items())
    roots, members = {}, {}
    for group in stations.station_groups(rows):
        # Prefer an existing owner so legacy root-level movability retains its
        # meaning. All other owners and explicit fixed members are checked too.
        root = min({str(owner_by_cap.get(ref, ref)) for ref in group})
        members[root] = tuple(group)
        roots.update({ref: root for ref in group})
    return roots, members


def check_positions(context, positions):
    if context and context.get('ok') is False:
        return dict(ok=False,errors=[dict(kind='electrical_binding_error',
                    error=context.get('error') or 'dependency context unavailable')],applicable=True)
    if not context or 'relation_guard' not in context:
        return dict(ok=True, errors=[], applicable=False)
    from cec_placement_relation_guard import check
    return dict(check(context['relation_guard'],positions),applicable=True)


def filter_moves(context, positions, moves):
    """Filter primary electrical regressions before a finite trial quota."""
    retained, failures = [], []
    for index, move in enumerate(moves):
        poses=move.get('placements') or {move['ref']:move['position']}
        proof=check_positions(context,dict(positions,**poses))
        if proof['ok']:
            retained.append(move)
        else:
            failures.append(dict(index=index,ref=move.get('ref'),kind=move.get('kind'),errors=proof['errors']))
    return retained,dict(proposed=len(moves),retained=len(retained),refused=len(failures),
                         samples=failures[:16],samples_truncated=max(0,len(failures)-16))
