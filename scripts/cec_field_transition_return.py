"""Bounded ground-return proposals for audited single-ended transitions.

Only vias attached to the two reported tracks are considered. Existing routes,
locks, placements and plane outlines are untouched. Candidate and final contact
must use actual saved/refilled reference copper, never a prospective plane.
The caller still owes independent electrical, field and preservation admission.
"""
import math


def reference_polygons(board, layers):
    import pcbnew
    if not isinstance(layers, (tuple, list)) or not 1 <= len(layers) <= 4:
        raise ValueError('one to four declared intermediate reference layers required')
    result = {}
    for name in layers:
        lid = board.GetLayerID(name)
        if lid < 0 or not pcbnew.IsCopperLayer(lid) or not board.IsLayerEnabled(lid):
            raise ValueError('reference layer is not enabled copper')
        result[lid] = [z.GetFilledPolysList(lid) for z in board.Zones()
                       if not z.GetIsRuleArea() and z.GetNetname() == 'GND'
                       and z.IsOnLayer(lid) and z.GetFilledPolysList(lid).OutlineCount()]
        if not result[lid]:
            raise ValueError('reference layer has no actual filled ground copper')
    return result


def contact_filter(board, layers):
    import pcbnew
    polygons = reference_polygons(board, layers)
    def contact(point, diameter):
        # Keep the board (native polygon owner) alive with this closure.
        owner = board
        at = pcbnew.VECTOR2I(*(round(v*1e6) for v in point))
        land = pcbnew.SHAPE_SEGMENT(at, at, round(diameter*1e6))
        return bool(owner) and all(any(poly.Collide(land, 0) for poly in rows)
                                   for rows in polygons.values())
    return contact


def transition_vias(board, interaction, *, limit=4):
    """Exact endpoint topology, not a product name or nearest-via guess."""
    import pcbnew
    if type(limit) is not int or not 1 <= limit <= 4:
        raise ValueError('one to four transition witnesses required')
    ids = interaction.get('track_uuids') or ()
    nets = interaction.get('nets') or ()
    if interaction.get('blocking') is not True or len(ids) != 2 or len(nets) != 2:
        raise ValueError('a fresh blocking interaction with two track identities is required')
    tracks = {t.m_Uuid.AsString(): t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK'}
    endpoints = set()
    for uid, net in zip(ids, nets):
        track = tracks.get(uid)
        if track is None or not net or net == 'GND' or track.GetNetname() != net:
            raise ValueError('interaction track identity or net is stale')
        for p in (track.GetStart(), track.GetEnd()):
            endpoints.add((net, tuple(p), int(track.GetLayer())))
    matches = []
    for via in board.GetTracks():
        if via.GetClass() != 'PCB_VIA' or via.GetViaType() != pcbnew.VIATYPE_THROUGH:
            continue
        if any(via.GetNetname() == net and tuple(via.GetPosition()) == point
               and via.IsOnLayer(layer) for net, point, layer in endpoints):
            matches.append(via)
    return sorted(matches, key=lambda v: (v.GetNetname(), tuple(v.GetPosition()),
                                          v.m_Uuid.AsString()))[:limit]


def verify_contacts(board, report):
    """Fresh filled-copper witnesses for every newly emitted return barrel."""
    contact = contact_filter(board, report['reference_layers'])
    items = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    rows = []
    for row in report['transitions']:
        signal = items.get(row['signal_uuid'])
        for uid in row['added_uuids']:
            via = items.get(uid)
            good = bool(signal is not None and via is not None
                        and via.GetClass() == 'PCB_VIA' and via.GetNetname() == 'GND'
                        and contact(tuple(v/1e6 for v in via.GetPosition()),
                                    via.GetWidth(via.TopLayer())/1e6)
                        and math.dist(tuple(signal.GetPosition()), tuple(via.GetPosition()))
                        <= report['return_reach_mm']*1e6+1)
            rows.append(dict(uuid=uid, actual_plane_contact=good))
    return dict(ok=bool(rows) and all(r['actual_plane_contact'] for r in rows), witnesses=rows)


def add_returns(board, interaction, *, return_reach_mm=1.5,
                via_diameter_mm=.6, via_drill_mm=.3, clearance_mm=.2):
    """Add only exact-clearance, actual-plane-contacting return candidates."""
    import cec_fab_profile
    import cec_precision_route as precision
    values = (return_reach_mm, via_diameter_mm, via_drill_mm, clearance_mm)
    if (any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
            or not .5 <= return_reach_mm <= 1.5 or not .2 <= via_diameter_mm <= 1.5
            or not .1 <= via_drill_mm < via_diameter_mm or not .1 <= clearance_mm <= 1.):
        raise ValueError('finite bounded return geometry required')
    layers = list((interaction.get('shield') or {}).get('layers') or ())
    # Two routes on the same layer cannot acquire an intervening shield by
    # adding a ground via. Leave that case to the spacing/route repair.
    if len(set(interaction.get('layers') or ())) != 2:
        return dict(applicable=False, added=0, reason='not_cross_layer')
    contact = contact_filter(board, layers)
    vias = transition_vias(board, interaction)
    diameter, drill, dimensions = cec_fab_profile.board_legal_through_via_geometry(
        board, via_diameter_mm, via_drill_mm)
    clearance = max(clearance_mm, board.GetDesignSettings().m_MinClearance/1e6)
    rows = []
    for signal in vias:
        center = tuple(v/1e6 for v in signal.GetPosition())
        added, status = precision._add_pair_transition_returns(board, center, (1.,0.),
            signal_points=(center,), clearance=clearance,
            via_diameter_mm=diameter, via_drill_mm=drill,
            return_reach_mm=return_reach_mm, reference_contact=contact)
        rows.append(dict(signal_uuid=signal.m_Uuid.AsString(), status=status,
                         added_uuids=[v.m_Uuid.AsString() for v in added]))
    return dict(applicable=True, added=sum(len(r['added_uuids']) for r in rows),
                transitions=rows, reference_layers=layers, return_reach_mm=return_reach_mm,
                dimensions=dimensions, release_authority=False)
