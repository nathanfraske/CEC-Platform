"""Read-only native contacts of a source SMD land, not assumed pad centres.

Connected pose constructors use these actual former track endpoints, barrel
positions and through-running body contacts as restoration obligations.
This bounded inventory neither constructs routes nor grants current, local
DRC, placement or release authority. A saved whole-board grade is required.
"""
import math
import time
import pcbnew


def inspect(board, pad, *, max_contacts=8, timeout_s=10.):
    if (type(max_contacts) is not int or not 1 <= max_contacts <= 64
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or pad.GetNetCode() <= 0):
        raise ValueError('bounded_source_smd_contact_inventory_required')
    items = list(board.GetTracks())
    if len(items) > 16384:
        raise ValueError('source_land_contact_native_inventory_bound')
    face = int(pad.GetLayer())
    shape = pad.GetEffectiveShape(face)
    deadline = time.monotonic() + timeout_s
    ports = {}
    for item in items:
        if time.monotonic() >= deadline:
            raise ValueError('source_land_contact_inventory_deadline')
        if not item.IsOnLayer(face) or item.GetNetCode() != pad.GetNetCode():
            continue
        if not item.GetEffectiveShape(face).Collide(shape, 0):
            continue
        kind = item.GetClass()
        uid = item.m_Uuid.AsString()
        if kind == 'PCB_VIA':
            candidates = [item.GetPosition()]
        elif kind == 'PCB_TRACK':
            radius = (item.GetWidth() + 1) // 2
            candidates = [at for at in (item.GetStart(), item.GetEnd())
                if shape.Collide(pcbnew.SHAPE_CIRCLE(at, radius), 0)]
            if not candidates:
                # A through-running conductor is already continuous. Join
                # its actual body, not an empty point at the pad centre.
                start, end = item.GetStart(), item.GetEnd()
                at = pad.GetPosition()
                dx, dy = end.x - start.x, end.y - start.y
                length = dx * dx + dy * dy
                if length <= 0:
                    raise ValueError('nonempty_source_contact_stroke_required')
                t = max(0., min(1., ((at.x-start.x)*dx + (at.y-start.y)*dy) / length))
                candidates = [pcbnew.VECTOR2I(round(start.x+t*dx), round(start.y+t*dy))]
        else:
            raise ValueError('unsupported_source_land_contact_kind:' + kind)
        for at in candidates:
            port = ports.setdefault(tuple(at), dict(point_nm=list(at), source_uuids=[], source_kinds=[]))
            port['source_uuids'].append(uid)
            port['source_kinds'].append(kind)
        if len(ports) > max_contacts:
            raise ValueError('source_land_contact_inventory_bound')
    if not ports:
        # Never invent a ghost lead for a former land without actual source
        # copper. Only already filled same-net copper can supply a zone port.
        at = pad.GetPosition()
        for zone in board.Zones():
            if time.monotonic() >= deadline:
                raise ValueError('source_land_contact_inventory_deadline')
            if (not zone.GetIsRuleArea() and zone.GetNetCode() == pad.GetNetCode()
                    and zone.IsOnLayer(face) and zone.HasFilledPolysForLayer(face)
                    and zone.GetFilledPolysList(face).Contains(at)):
                port = ports.setdefault(tuple(at), dict(point_nm=list(at), source_uuids=[], source_kinds=[]))
                port['source_uuids'].append(zone.m_Uuid.AsString())
                port['source_kinds'].append('ZONE')
    return dict(complete=True, ports=[ports[k] for k in sorted(ports)],
        source_pad_uuid=pad.m_Uuid.AsString(), source_mutated=False,
        ampacity_or_route_authority_granted=False)
