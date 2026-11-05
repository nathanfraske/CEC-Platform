"""Prove retained native contacts of a reoriented, fixed-centre SMD land.

An identical rectangle is not required, but every original adjacency is.
This is not a current, clearance, placement, thermal or release certificate.
Caller names, coordinates and claimed contacts grant no exceptions.
"""
import math
import time


def preserve(board, before, after, *, deadline_monotonic, maximum_items=8192):
    import pcbnew
    if (type(maximum_items) is not int or not 1 <= maximum_items <= 32768
            or type(deadline_monotonic) not in (int, float)
            or not math.isfinite(deadline_monotonic)
            or deadline_monotonic > time.monotonic() + 10.):
        raise ValueError('bounded_native_pivot_contact_inventory_required')
    uid = str(before.m_Uuid.AsString())
    if (uid != str(after.m_Uuid.AsString())
            or before.GetNetCode() <= 0 or before.GetNetCode() != after.GetNetCode()
            or before.GetNumber() != after.GetNumber()
            or before.GetNetname() != after.GetNetname()
            or before.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or after.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or before.HasHole() or after.HasHole()
            or tuple(before.GetPosition()) != tuple(after.GetPosition())
            or tuple(before.GetSize()) != tuple(after.GetSize())
            or tuple(before.GetOffset()) != (0, 0) or tuple(after.GetOffset()) != (0, 0)
            or before.GetShape() not in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT)
            or before.GetShape() != after.GetShape()
            or before.GetRoundRectRadiusRatio() != after.GetRoundRectRadiusRatio()
            or tuple(before.GetLayerSet().CuStack()) != tuple(after.GetLayerSet().CuStack())):
        raise ValueError('exact_fixed_centre_source_native_land_required')
    items = [*board.GetTracks(), *(p for f in board.GetFootprints() for p in f.Pads()), *board.Zones()]
    if len(items) > maximum_items:
        raise ValueError('native_pivot_contact_inventory_bound')
    contacts = []
    def tick():
        if time.monotonic() >= deadline_monotonic:
            raise ValueError('native_pivot_contact_deadline')
    def material(item, layer, error):
        tick()
        poly = pcbnew.SHAPE_POLY_SET()
        if item.GetClass() == 'ZONE':
            poly.Append(item.GetFilledPolysList(layer))
        else:
            item.TransformShapeToPolygon(poly, layer, 0, 1, error)
            if item.GetClass() == 'PCB_VIA' or item.GetClass() == 'PAD' and item.HasHole():
                hole = pcbnew.SHAPE_POLY_SET()
                item.GetEffectiveHoleShape().TransformToPolygon(hole, 1, pcbnew.ERROR_OUTSIDE)
                poly.BooleanSubtract(hole)
        return poly
    def overlaps(a, b):
        tick()
        intersection = pcbnew.SHAPE_POLY_SET()
        intersection.Append(a)
        intersection.BooleanIntersection(b)
        return intersection.OutlineCount() > 0 and intersection.Area() > 0
    for layer in before.GetLayerSet().CuStack():
        old = material(before, layer, pcbnew.ERROR_OUTSIDE)
        new = material(after, layer, pcbnew.ERROR_INSIDE)
        source_box = old.BBox()
        for item in items:
            tick()
            item_uid = str(item.m_Uuid.AsString())
            if item_uid == uid or item.GetNetCode() != before.GetNetCode() or not item.IsOnLayer(layer):
                continue
            if item.GetClass() == 'ZONE':
                if item.GetIsRuleArea():
                    continue
                if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                    if item.GetBoundingBox().Intersects(before.GetBoundingBox()):
                        raise ValueError('source_pivot_nearby_same_net_fill_unknown')
                    continue
                item_box = item.GetFilledPolysList(layer).BBox()
            else:
                item_box = item.GetEffectiveShape(layer).BBox()
            # Bounds reject distant objects only. A hit still needs actual
            # native material on both sides, with holes removed below.
            if not source_box.Intersects(item_box):
                continue
            outward = material(item, layer, pcbnew.ERROR_OUTSIDE)
            if not old.Collide(outward, 0):
                continue
            # The outward source detects even a tiny old contact. The inward
            # candidate must retain positive copper area, not bbox or drill contact.
            inward = material(item, layer, pcbnew.ERROR_INSIDE)
            if not overlaps(new, inward):
                raise ValueError('source_pivot_native_contact_lost:' + item_uid)
            contacts.append(dict(uuid=item_uid, kind=item.GetClass(), layer_id=int(layer)))
    if not contacts:
        raise ValueError('positive_source_pivot_native_contact_required')
    return dict(complete=True, fixed_centre_nm=list(before.GetPosition()), pad_uuid=uid,
        original_native_contacts=contacts, all_source_native_contacts_preserved=True,
        pad_copper_identical=False, current_or_clearance_qualified=False, release_authority=False)
