"""Keep protected narrow escapes qualified while proposing support motion.

The grouped neck's exemption belongs to a live native pad contact, not just
its net name. Moving that pad away can leave unqualified, immutable copper
even if the net is reconnected elsewhere. This is a necessary proposal bound,
not authority to change copper or waive final electrical/placement checks.
"""
import math

import pcbnew
import cec_fr as fr


def capture(board, target, resolver):
    refs = {target['ref'], *(target.get('companion_refs') or ())}
    pads = [p for fp in board.GetFootprints() if fp.GetReference() in refs
            for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    grouped = {str(item.m_Uuid.AsString()) for group in board.Groups()
               if group.GetName() == fr.ENDPOINT_NECKDOWN_GROUP for item in group.GetItems()}
    origin = board.FindFootprintByReference(target['ref']).GetPosition()
    rows = []
    for track in board.GetTracks():
        if track.GetClass() != 'PCB_TRACK' or str(track.m_Uuid.AsString()) not in grouped:
            continue
        spec = resolver(track.GetNetname()) or {}
        width = float(spec.get('track_width') or 0)
        if track.GetWidth() >= round(width*1e6): continue
        for pad in pads:
            if pad.GetNetCode() != track.GetNetCode() or not pad.IsOnLayer(track.GetLayer()): continue
            shape = pad.GetEffectiveShape(track.GetLayer())
            contacts = [pcbnew.VECTOR2I(p) for p in (track.GetStart(), track.GetEnd()) if shape.Collide(p, 0)]
            if contacts:
                rows.append(dict(pad=pad, shape=shape, contacts=contacts,
                    origin=pcbnew.VECTOR2I(origin), track_uuid=str(track.m_Uuid.AsString())))
    return rows


def preserves(rows, candidate):
    angle = math.radians(float(candidate.get('rotation_delta_deg', 0)))
    cosine, sine = math.cos(angle), math.sin(angle)
    dx, dy = round(float(candidate.get('dx_mm', 0))*1e6), round(float(candidate.get('dy_mm', 0))*1e6)
    for row in rows:
        origin = row['origin']
        # Evaluate the unchanged native land with inverse-transformed fixed
        # contacts. No board mutation, bounding-box qualification or epsilon.
        def retained(point):
            x, y = point.x-origin.x-dx, point.y-origin.y-dy
            inverse = pcbnew.VECTOR2I(round(origin.x+cosine*x-sine*y), round(origin.y+sine*x+cosine*y))
            return row['shape'].Collide(inverse, 0)
        if not any(retained(point) for point in row['contacts']): return False
    return True


def pivots(rows):
    """Finite half-turns about original pad centres, no pin/net exchange."""
    found = {}
    for row in rows:
        pad, origin = row['pad'].GetPosition(), row['origin']
        candidate = dict(dx_mm=2*(pad.x-origin.x)/1e6, dy_mm=2*(pad.y-origin.y)/1e6,
                         rotation_delta_deg=180.)
        key = tuple(candidate.values())
        if preserves(rows, candidate): found.setdefault(key, candidate)
    return list(found.values())
