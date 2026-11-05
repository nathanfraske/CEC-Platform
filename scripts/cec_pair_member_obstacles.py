"""Immutable native opposite-member obstacles for a coupled route attempt.

Excluding both pair nets from the foreign envelope is not permission to cross
established partner copper. This snapshot is local to one unchanged board
attempt; bounds only shortlist, and KiCad's exact shapes decide clearance.
"""
import math

import pcbnew

import cec_fr


class MemberObstacles:
    def __init__(self, board, layer_id, pair_net_codes):
        codes = tuple(pair_net_codes)
        if (len(codes) != 2 or any(type(c) is not int or c <= 0 for c in codes)
                or codes[0] == codes[1]
                or any(board.FindNet(c) is None for c in codes)):
            raise ValueError('two_explicit_native_member_net_codes_required')
        self.board = board
        self.layer = int(layer_id)
        self.codes = codes
        rows = {c: [] for c in codes}
        hole_clearance = max(0, int(board.GetDesignSettings().m_HoleClearance))

        def append(code, item, shape, kind, extra=0):
            if shape is None:
                raise ValueError('native_partner_shape_unavailable')
            uid = item.m_Uuid.AsString()
            if not uid:
                raise ValueError('native_partner_identity_unavailable')
            try:
                box = shape.BBox()
            except Exception:
                box = None  # Unknown bounds never remove an exact obstacle.
            rows[code].append((shape, box, dict(kind=kind, uuid=uid,
                net=item.GetNetname(), layer=board.GetLayerName(self.layer)),
                max(0, int(extra))))

        for fp in board.GetFootprints():
            for pad in fp.Pads():
                code = int(pad.GetNetCode())
                if code not in rows:
                    continue
                if self.layer in pad.GetLayerSet().CuStack():
                    append(code, pad, pad.GetEffectiveShape(self.layer), 'pad',
                           pad.GetLocalClearance() or 0)
                if pad.HasHole():
                    append(code, pad, pad.GetEffectiveHoleShape(),
                           'plated_pad_hole', hole_clearance)
        for item in board.GetTracks():
            code = int(item.GetNetCode())
            if code not in rows:
                continue
            if item.GetClass() == 'PCB_VIA':
                if self.layer not in item.GetLayerSet().CuStack():
                    continue
                append(code, item, item.GetEffectiveShape(self.layer), 'via')
                drill = int(item.GetDrillValue())
                if drill <= 0:
                    raise ValueError('native_partner_via_drill_unavailable')
                # Use the native hole shape, not a manually constructed
                # SHAPE_CIRCLE whose SWIG Collide overload accepts SEG rather
                # than SHAPE_SEGMENT and would conservatively refuse every
                # nearby legal member edge as unknown geometry.
                append(code, item, item.GetEffectiveHoleShape(),
                       'via_hole', hole_clearance)
            elif int(item.GetLayer()) == self.layer:
                if item.GetClass() not in ('PCB_TRACK', 'PCB_ARC'):
                    raise ValueError('unsupported_native_partner_copper')
                append(code, item, item.GetEffectiveShape(self.layer), 'track')
        for zone in board.Zones():
            if (int(zone.GetNetCode()) in rows and not zone.GetIsRuleArea()
                    and self.layer in zone.GetLayerSet().CuStack()):
                # A possibly stale fill cannot establish member-route space.
                raise ValueError('pair_owned_zone_requires_independent_fill_authority')
        self.rows = rows
        self.index = {c: cec_fr._bucket_foreign_shapes(r) for c, r in rows.items()}

    def clear(self, member, a, b, width_mm, clearance_mm):
        if member not in ('p', 'n'):
            raise ValueError('explicit_pair_member_required')
        for value in (width_mm, clearance_mm):
            if not math.isfinite(value) or value < 0:
                raise ValueError('finite_native_member_geometry_required')
        if width_mm <= 0:
            raise ValueError('positive_native_member_width_required')
        partner = self.codes[1 if member == 'p' else 0]
        return cec_fr._snapshot_foreign_clear(
            pcbnew.VECTOR2I_MM(*a), pcbnew.VECTOR2I_MM(*b),
            pcbnew.FromMM(width_mm), pcbnew.FromMM(clearance_mm),
            (), self.index[partner])

    def paths(self, p_points, n_points, width_mm, clearance_mm):
        issues = []
        checked = 0
        for member, points in (('p', p_points), ('n', n_points)):
            for a, b in zip(points, points[1:]):
                checked += 1
                if self.clear(member, a, b, width_mm, clearance_mm):
                    continue
                partner = self.codes[1 if member == 'p' else 0]
                shape = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I_MM(*a),
                    pcbnew.VECTOR2I_MM(*b), pcbnew.FromMM(width_mm))
                witnesses = []
                for obstacle, _box, identity, extra in self.rows[partner]:
                    try:
                        hit = obstacle.Collide(shape, max(
                            pcbnew.FromMM(clearance_mm), extra))
                    except Exception:
                        hit = True
                    if hit:
                        witnesses.append(identity)
                    if len(witnesses) >= 4:
                        break
                issues.append(dict(type='established_partner_copper',
                    member=member, segment_mm=[list(a), list(b)],
                    blockers=witnesses))
                if len(issues) >= 8:
                    return dict(ok=False, issues=issues, checked_segments=checked,
                                truncated=True)
        return dict(ok=not issues, issues=issues, checked_segments=checked)

    def corridor_mask(self, a, b, width_mm, gap_mm, clearance_mm):
        """Bits for consistent P-on-plus/P-on-minus straight offset edges.

        This is only a search prefilter. Miters, terminal fan-ins and the whole
        final ribbon still require exact member-path and independent DRC tests.
        """
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        if length <= 1e-12:
            return 3
        offset = (width_mm+gap_mm)/2
        ox, oy = -dy/length*offset, dx/length*offset
        plus = ((a[0]+ox, a[1]+oy), (b[0]+ox, b[1]+oy))
        minus = ((a[0]-ox, a[1]-oy), (b[0]-ox, b[1]-oy))
        mask = 0
        for bit, p, n in ((1, plus, minus), (2, minus, plus)):
            if (self.clear('p', *p, width_mm, clearance_mm)
                    and self.clear('n', *n, width_mm, clearance_mm)):
                mask |= bit
        return mask
