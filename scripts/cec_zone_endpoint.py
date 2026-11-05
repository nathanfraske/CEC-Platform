"""Resolve a native zone endpoint only on its currently filled copper.

An authored outline is not an electrical attachment. This intentionally
does not snap outside points onto copper or infer a layer for a multilayer
zone. It supplies an exact same-layer origin to the ordinary guarded router.
"""
import math


def resolve(board, endpoint, net_code):
    import pcbnew
    if endpoint.get('kind') != 'zone' or net_code <= 0:
        return None
    matches = [zone for zone in board.Zones()
               if zone.m_Uuid.AsString() == str(endpoint.get('uuid') or '')
               and zone.GetNetCode() == net_code and not zone.GetIsRuleArea()]
    if len(matches) != 1:
        return None
    zone = matches[0]
    enabled = set(board.GetEnabledLayers().CuStack())
    layers = set(zone.GetLayerSet().CuStack()) & enabled
    declared = endpoint.get('copper_layers')
    if declared is not None:
        # A DRC endpoint must identify one layer, not grant access to every
        # layer of a multilayer zone as though it were a plated barrel.
        if not isinstance(declared, (list, tuple)) or len(declared) != 1:
            return None
        layer = board.GetLayerID(str(declared[0]))
        if layer not in layers:
            return None
    elif len(layers) == 1:
        layer = next(iter(layers))
    else:
        return None
    if (endpoint.get('native_layer') is not None
            and endpoint['native_layer'] != board.GetLayerName(layer)):
        return None
    try:
        coords = [float(endpoint[key]) for key in ('x_mm', 'y_mm')]
        if not all(map(math.isfinite, coords)):
            return None
        point = pcbnew.VECTOR2I(*(round(v*1_000_000) for v in coords))
        fill = zone.GetFilledPolysList(layer)
        if not zone.IsFilled() or not fill.OutlineCount() or not fill.Contains(point):
            return None
    except (KeyError, ValueError, TypeError, OverflowError):
        return None
    return point, frozenset((layer,)), None, zone
