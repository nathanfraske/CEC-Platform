"""All-face clearance for a literal, unchanged saved Ground barrel.

Existing holes may occupy antipads inside authored power-pour outlines.
Reuse may inspect the exact saved fill, never request another antipad. The
saved barrel, declared stack/profile and every zone must match; all current
pads, tracks, drills and clearances are still checked. An edited/new barrel
may pass the ordinary authored-reservation guard, but cannot claim a saved
antipad. Process ownership is rechecked by the caller with its proposed
connection present. This is not current or release authority.
"""
from pathlib import Path
import math
import time

import pcbnew
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_native_frozen_zone_access as frozen


def _barrel(board, via):
    return (force._uid(via), str(via.GetNetname()), tuple(via.GetPosition()),
        int(via.GetViaType()), int(via.TopLayer()), int(via.BottomLayer()),
        int(via.GetDrillValue()), bool(via.IsLocked()), int(via.Padstack().Mode()),
        tuple((int(l), int(via.GetWidth(l))) for l in board.GetEnabledLayers().CuStack()),
        tuple(sorted(force._uid(g) for g in board.Groups() if g.ContainsItem(via))))


def clear(board, via, clearance_nm, *, deadline, foreign_cache=None,source_path=None,
          allow_unreserved_ground_refill=False):
    if (type(clearance_nm) is not int or not 0 <= clearance_nm <= 2000000
            or type(deadline) not in (int, float) or not math.isfinite(deadline)
            or via.GetClass() != 'PCB_VIA' or via.GetNetname() != 'GND'
            or via.GetViaType() != pcbnew.VIATYPE_THROUGH
            or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
            or type(allow_unreserved_ground_refill) is not bool):
        raise ValueError('bounded_literal_retained_ground_barrel_clearance_required')
    if time.monotonic() >= deadline:
        return False
    layers = tuple(board.GetEnabledLayers().CuStack())
    diameter = max(int(via.GetWidth(l)) for l in layers)
    # A literal existing POFV land can be smaller than the board's ordinary
    # creation floors. The native_padstack_via API intentionally enforces
    # those *new ordinary via* floors, so it is not the process predicate for
    # this retained-barrel query. Use a conservative maximum native-circle
    # envelope on every face instead; the caller still has to prove actual
    # ordinary dimensions or local POFV ownership after adding its strokes.
    for layer in layers:
        shape = via.GetEffectiveShape(layer)
        box = shape.BBox()
        width = int(via.GetWidth(layer))
        if (shape.Type() != pcbnew.SH_CIRCLE or width <= via.GetDrillValue()
                or abs(box.GetWidth()-width) > 1 or abs(box.GetHeight()-width) > 1
                or math.dist(tuple(box.GetCenter()), tuple(via.GetPosition())) > 1):
            return False
    def probe():
        return fr._via_spot_clear(board, via.GetPosition(), diameter, clearance_nm,
            {via.GetNetCode()}, drill_nm=via.GetDrillValue(), net_code=via.GetNetCode(),
            existing_via_uuid=force._uid(via), foreign_cache=foreign_cache)
    active_frozen = frozen.cache_token(board) is not None
    if not active_frozen and probe():
        return True  # Authored reservations need no saved-fill authority.
    path = Path(source_path) if source_path is not None else Path(board.GetFileName()) if board.GetFileName() else None
    if path is None or not path.is_file():
        return False  # No saved source can grant a native filled pocket.
    parent = pcbnew.LoadBoard(str(path))
    original = next((v for v in parent.GetTracks() if force._uid(v) == force._uid(via)), None)
    if (original is None or original.GetClass() != 'PCB_VIA'
            or _barrel(parent, original) != _barrel(board, via)
            or tuple(parent.GetEnabledLayers().CuStack()) != layers
            or fab.board_profile_name(parent) != fab.board_profile_name(board)):
        return False
    if active_frozen:
        return probe()  # Preserve the caller's independently bound scope.
    scope = set(); owned_clearance = fr._foreign_clearance_resolver(board)
    for zone in board.Zones():
        if time.monotonic() >= deadline:
            return False
        if zone.GetIsRuleArea() or zone.GetNetCode() == via.GetNetCode():
            continue
        for layer in layers:
            if not fr._zone_is_route_reservation(board, zone, layer):
                continue
            gap = max(clearance_nm, int(zone.GetLocalClearance()), owned_clearance(zone, layer))
            if zone.Outline().Collide(via.GetEffectiveShape(layer), gap):
                scope.add(force._uid(zone))
    if not scope:
        return probe()
    if len(scope) > 32:
        return False
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        return False
    # frozen independently compares ALL zone identities, outlines, fills and
    # clearances with this saved parent. Only these intersecting immutable
    # reservations use their native fill; every other outline stays reserved.
    try:
        with frozen.frozen(board, path, timeout_s=min(10., remaining), zone_uuids=sorted(scope),
                allow_unreserved_ground_refill=allow_unreserved_ground_refill):
            return probe()
    except ValueError:
        return False
