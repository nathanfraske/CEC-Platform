"""Exact, layer-aware pad obstacles for pre-commit conductor proposals.

A maximum-size circular proxy both blocks valid elongated-pad channels and
misses rectangular corners. Keep KiCad's native shapes and netclass clearance;
never infer a pad's layer from the route's relative layer-tag spelling.
"""
from __future__ import annotations

import math

MM = 1_000_000


class Index:
    """Read-only snapshot; rebuild after any footprint or pad geometry changes."""

    def __init__(self, board, *, clearance_mm):
        import cec_fr
        if not math.isfinite(clearance_mm) or clearance_mm < 0:
            raise ValueError('invalid pad clearance')
        self.board = board
        self.minimum = round(clearance_mm * MM)
        self.clearance = cec_fr._foreign_clearance_resolver(board)
        self.pads = [(fp.GetReference(), pad) for fp in board.GetFootprints()
                     for pad in fp.Pads()]
        self.layers = {}

    def _rows(self, layer):
        import pcbnew
        if layer not in self.layers:
            rows = []
            for ref, pad in self.pads:
                net = pad.GetNetname()
                pos = pad.GetPosition()
                identity = dict(ref=ref, net=net, at_mm=[pos.x/MM, pos.y/MM],
                                pad=pad.GetNumber(), pad_uuid=pad.m_Uuid.AsString())
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and pad.HasHole():
                    rows.append((identity, True, pad.GetEffectiveHoleShape(),
                        max(self.minimum, int(self.board.GetDesignSettings().m_HoleClearance))))
                if pad.IsOnLayer(layer):
                    rows.append((identity, False, pad.GetEffectiveShape(layer),
                        max(self.minimum, self.clearance(pad, layer))))
            self.layers[layer] = rows
        return self.layers[layer]

    def _hits(self, segment, layer, own_nets, *, skip_prefixes=()):
        import pcbnew
        if (len(segment) != 5 or any(not math.isfinite(float(v)) for v in segment)
                or segment[4] <= 0 or layer not in self.board.GetEnabledLayers().CuStack()):
            raise ValueError('invalid native conductor proposal')
        x0, y0, x1, y1, width = segment
        shape = pcbnew.SHAPE_SEGMENT(
            pcbnew.VECTOR2I(round(x0*MM), round(y0*MM)),
            pcbnew.VECTOR2I(round(x1*MM), round(y1*MM)), round(width*MM))
        for identity, hole, obstacle, clearance in self._rows(layer):
            if (identity['ref'].startswith(tuple(skip_prefixes))
                    or (not hole and identity['net'] in own_nets)):
                continue
            # Missing/unsupported native geometry must refuse the caller, not
            # silently fall through to a smaller circle or no obstacle.
            if obstacle.Collide(shape, clearance):
                yield dict(identity, kind='hole' if hole else 'pad',
                           clearance_mm=clearance/MM)

    def collision(self, segment, layer, own_nets, *, skip_prefixes=()):
        """Fast first hit for the unchanged conductor admission guard."""
        return next(self._hits(segment, layer, own_nets, skip_prefixes=skip_prefixes), None)

    def collisions(self, segment, layer, own_nets, *, skip_prefixes=()):
        """All native pad/hole hits, without a first-hit or count truncation."""
        return list(self._hits(segment, layer, own_nets, skip_prefixes=skip_prefixes))

    def conductor_obstructions(self, segments, own_nets, *, skip_prefixes=()):
        """Capture one complete principal proposal, not probe alternatives.

        Completeness refers ONLY to native pads/holes. Tracks, vias, portals,
        outline and construction admission remain separate guards. No report
        here reserves territory or confers route/placement ownership.
        """
        segments = [dict(segment_mm=list(row['segment_mm']), layer=row['layer'])
                    for row in segments]
        hits = []
        for index, row in enumerate(segments):
            layer = self.board.GetLayerID(row['layer'])
            for hit in self.collisions(row['segment_mm'], layer, own_nets,
                                       skip_prefixes=skip_prefixes):
                hits.append(dict(hit, segment_index=index, segment_mm=row['segment_mm'],
                                 layer=row['layer'], blocker_net=hit['net'],
                                 net=sorted(own_nets)[0]))
        return dict(schema=1, complete_pad_set=True, nets=sorted(own_nets),
                    conductor_segments=segments, blocked_segments=hits,
                    minimum_clearance_mm=self.minimum/MM, release_authority=False)
