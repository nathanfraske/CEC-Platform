"""Native contact guard for cosmetic, continuous, uniform-width corners.

Clearance guards ignore same-net copper. They therefore cannot prove that a
cosmetic shortcut retained a tiny side contact. This guard preserves each
existing same-layer pad, barrel, track and actual filled-zone adjacency to the
old two-leg corner. It is not width, Kelvin, current or release qualification.
"""
import math
import time


def native_contact_polygon(item, layer_id, deadline_monotonic):
    """Conservative native contact material; never a capacity certificate."""
    import pcbnew
    import cec_native_fill_geometry as fills
    if item.GetClass() == 'ZONE':
        if not item.IsFilled() or not item.HasFilledPolysForLayer(layer_id):
            raise ValueError('native_contact_fill_unknown')
        poly = item.GetFilledPolysList(layer_id).CloneDropTriangulation()
    else:
        poly = pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(poly,layer_id,0,1,pcbnew.ERROR_INSIDE)
    fills.identity(poly,deadline_monotonic)
    return poly


def native_contact_radius(item, tracks, layer_id, width_nm, deadline_monotonic):
    """Inscribed native intersection witness, not electrical qualification."""
    import pcbnew
    contact=pcbnew.SHAPE_POLY_SET()
    for track in tracks:contact.BooleanAdd(native_contact_polygon(track,layer_id,deadline_monotonic))
    contact.BooleanIntersection(native_contact_polygon(item,layer_id,deadline_monotonic))
    if not contact.OutlineCount():return 0
    low,high=0,width_nm//2
    while low<high:
        if time.monotonic()>=deadline_monotonic:raise ValueError('native_contact_web_deadline')
        radius=(low+high+1)//2;eroded=contact.CloneDropTriangulation()
        eroded.Inflate(-radius,pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,1)
        if eroded.OutlineCount():low=radius
        else:high=radius-1
    return low


def native_pad_anchor(pad, point, *, layer_id):
    """Conservatively protect the CLOSED native pad copper at a vertex.

    Collide(point,0) can exclude a literal boundary that native HitTest
    includes. A one-nanometre outward observation guard preserves that launch;
    it is not permission to move a pad or lose any whole-leg adjacency. Empty
    bounding-box corners are not copper. Unknown shape geometry stays fixed.
    """
    try:
        if not pad.IsOnLayer(layer_id):return False
        shape=pad.GetEffectiveShape(layer_id)
        if shape is None:return True
        box=shape.BBox()
        if box.GetWidth()<=0 or box.GetHeight()<=0:return True
        return bool(shape.Collide(point,1))
    except (AttributeError,RuntimeError,TypeError,ValueError):
        return True


def preserve_contacts(board, source_tracks, replacement_shapes, *, layer_id,
                      net_code, deadline_monotonic, max_items=8192,
                      maximum_source_tracks=2,minimum_source_tracks=2):
    import pcbnew
    if (type(maximum_source_tracks) is not int or not 2<=maximum_source_tracks<=4
            or type(minimum_source_tracks) is not int or not 1<=minimum_source_tracks<=2
            or not minimum_source_tracks<=len(source_tracks)<=maximum_source_tracks
            or not 1 <= len(replacement_shapes) <= maximum_source_tracks+1
            or type(max_items) is not int or not 1 <= max_items <= 32768
            or type(deadline_monotonic) not in (int, float)
            or not math.isfinite(deadline_monotonic)):
        raise ValueError('bounded_native_corner_contact_scope_required')
    result = dict(ok=False, reason=None, examined=0, lost_contacts=[],
                  scope='native_local_adjacencies_not_release_qualification')
    try:
        source_ids = {t.m_Uuid.AsString() for t in source_tracks}
        old_shapes = [t.GetEffectiveShape(layer_id) for t in source_tracks]
        items = [*board.GetTracks(),
                 *(p for fp in board.GetFootprints() for p in fp.Pads()),
                 *board.Zones()]
        if len(items) > max_items:
            result['reason'] = 'contact_inventory_bound'
            return result
        for item in items:
            if time.monotonic() >= deadline_monotonic:
                result['reason'] = 'contact_deadline'
                return result
            uid = item.m_Uuid.AsString()
            if (uid in source_ids or item.GetNetCode() != net_code
                    or not item.IsOnLayer(layer_id)):
                continue
            if item.GetClass() == 'ZONE':
                if item.GetIsRuleArea():
                    continue
                # Unknown fill near the old source is not absence of a tap.
                if not item.IsFilled() or not item.HasFilledPolysForLayer(layer_id):
                    if any(item.GetBoundingBox().Intersects(t.GetBoundingBox())
                           for t in source_tracks):
                        result['reason'] = 'nearby_same_net_zone_fill_unknown'
                        return result
                    continue
                shape = item.GetEffectiveShape(layer_id)
            else:
                shape = item.GetEffectiveShape(layer_id)
            result['examined'] += 1
            if (any(old.Collide(shape, 0) for old in old_shapes)
                    and not any(new.Collide(shape, 0) for new in replacement_shapes)):
                result['lost_contacts'].append(uid)
        result['ok'] = not result['lost_contacts']
        result['reason'] = ('native_contacts_preserved' if result['ok']
                            else 'same_net_side_contact_lost')
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        result['reason'] = 'native_contact_unknown:' + type(exc).__name__
    return result
