"""Read-only native connectivity certificates for whole-net route exclusion.

Pad access is a prefix, not proof of a completed net.  Completion requires
every physical terminal and admitted copper item to inhabit one native
connected component.  Locked ownership deliberately omits mutable copper and
zones; separately admitted filled-plane completion is revalidated against the
full board at routing boundaries.  Neither query changes locks or geometry.
"""
from __future__ import annotations

import pcbnew


def _uuid(item):
    return item.m_Uuid.AsString()


def certificate(board, *, locked_only=True, nets=None):
    """Return bounded evidence, not a pad-touch or straight-chord approximation.

    KiCad handles native arcs, track-body contacts, duplicate physical lands,
    plated-pad barrels and actual via layer spans.  A private connectivity
    database contains only pads and locked tracks/vias for the ownership query;
    an unlocked track or a zone therefore cannot silently provide its bridge.
    Exceptions propagate: failed evidence is never completion authority.
    """
    requested = None if nets is None else {str(n) for n in nets if n}
    pads, copper = {}, {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            name = str(pad.GetNetname() or '')
            if pad.GetNetCode() > 0 and (requested is None or name in requested):
                pads.setdefault(name, []).append(pad)
    for item in board.GetTracks():
        name = str(item.GetNetname() or '')
        if (item.GetNetCode() > 0 and (not locked_only or item.IsLocked())
                and (requested is None or name in requested)):
            copper.setdefault(name, []).append(item)
    considered = (set(copper) if locked_only else set(pads) | set(copper))
    if requested is not None:
        considered |= requested
    if locked_only:
        conn = pcbnew.CONNECTIVITY_DATA()
        for name in sorted(considered):
            for item in pads.get(name, []) + copper.get(name, []):
                if not conn.Add(item):
                    raise RuntimeError('native locked connectivity rejected item')
    else:
        conn = board.GetConnectivity()
    rows = {}
    for name in sorted(considered):
        terminals = sorted(pads.get(name, []), key=_uuid)
        items = sorted(copper.get(name, []), key=_uuid)
        connected = ({_uuid(i) for i in conn.GetConnectedItems(terminals[0])}
                     if terminals else set())
        missing_pads = [_uuid(p) for p in terminals if _uuid(p) not in connected]
        missing_copper = [_uuid(i) for i in items if _uuid(i) not in connected]
        complete = bool(terminals and (items or not locked_only)
                        and not missing_pads and not missing_copper)
        rows[name] = dict(complete=complete, pad_count=len(terminals),
            copper_count=len(items), disconnected_pad_count=len(missing_pads),
            disconnected_copper_count=len(missing_copper),
            disconnected_pad_uuids=missing_pads[:32],
            disconnected_copper_uuids=missing_copper[:32],
            evidence_truncated=len(missing_pads) > 32 or len(missing_copper) > 32,
            reason=('one_native_connected_component' if complete else
                    'missing_physical_terminals' if not terminals else
                    'missing_locked_copper' if locked_only and not items else
                    'disconnected_native_components'))
    return dict(schema=1, authority=('locked_copper_subgraph' if locked_only
                else 'full_native_board_connectivity'), nets=rows)


def owned_nets(board):
    return {name for name, row in certificate(board)['nets'].items()
            if row['complete']}


def revalidate_completed(board, requested):
    """Demote stale exclusions without unlocking their protected route prefixes."""
    requested = sorted({str(n) for n in requested if n})
    proof = certificate(board, locked_only=False, nets=requested)
    completed = sorted(n for n in requested if proof['nets'][n]['complete'])
    return dict(requested=requested, completed=completed,
                demoted=sorted(set(requested)-set(completed)), proof=proof)
