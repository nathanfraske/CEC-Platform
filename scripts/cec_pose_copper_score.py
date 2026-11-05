"""Native pad/copper proximity for proposal ordering, never route authority.

Footprint bounding boxes count empty package space as occupied and can miss
clearance conflicts at individual rotated lands. This advisory score measures
actual pad shapes against the saved copper and stationary lands. It does not authorize removing an
incident track, moving a locked item, or accepting a pose. Native DRC, custom
rules, refill, connectivity and the independent transaction gate still follow.
"""
import math

import pcbnew

import cec_fr


MM = 1_000_000


def _box(item):
    box = item.GetBoundingBox()
    return box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom()


def _near(a, b, gap):
    return not (a[2] + gap < b[0] or b[2] + gap < a[0]
                or a[3] + gap < b[1] or b[3] + gap < a[1])


class NativePoseCopperScore:
    """A reversible, cached native snapshot for one bounded rigid cell.

    Same-net copper is not a foreign obstacle, but net-zero copper is. Layer
    spans come from native geometry (including through vias). Incident copper
    is retained in the snapshot: attachment alone is not removal authority.
    Scores distinguish new contacts from baseline contacts. They are hints,
    not rejection proofs; in particular a later proved local copper move can
    eliminate a contact counted here. Zones are left to refill/native DRC.
    """

    def __init__(self, board, owner_ref, companion_refs=(), *,
                 generated_locked_uuids=()):
        self.board = board  # Keep native shape and footprint owners alive.
        refs = [owner_ref, *companion_refs]
        if not 1 <= len(refs) <= 4 or len(set(refs)) != len(refs):
            raise ValueError('native pose score requires one bounded unique cell')
        self.members = [board.FindFootprintByReference(ref) for ref in refs]
        if any(fp is None for fp in self.members):
            raise ValueError('native pose score member is missing')
        self.poses = [(fp, pcbnew.VECTOR2I(fp.GetPosition()),
                       fp.GetOrientationDegrees()) for fp in self.members]
        self.origin = pcbnew.VECTOR2I(self.members[0].GetPosition())
        resolve = cec_fr._foreign_clearance_resolver(board)
        floor = max(0, int(board.GetDesignSettings().m_MinClearance))
        generated = set(generated_locked_uuids)
        self.pads = []
        for fp in self.members:
            for pad in fp.Pads():
                if not pad.IsOnCopperLayer():
                    continue
                layers = tuple(pad.GetLayerSet().CuStack())
                self.pads.append((pad, {layer: max(floor, resolve(pad, layer))
                                       for layer in layers}))
        self.items = []
        stationary_pads = [pad for fp in board.GetFootprints()
                           if fp.GetReference() not in refs
                           for pad in fp.Pads() if pad.IsOnCopperLayer()]
        for item in [*board.GetTracks(), *stationary_pads]:
            uid = str(item.m_Uuid.AsString())
            self.items.append(dict(uid=uid, net=item.GetNetCode(), box=_box(item),
                fixed=bool(item.GetClass() == 'PAD'
                           or (item.IsLocked() and uid not in generated)),
                layers={layer: (item.GetEffectiveShape(layer),
                                max(floor, resolve(item, layer)))
                        for layer in item.GetLayerSet().CuStack()}))
        self.baseline, _ = self._contacts()

    def _contacts(self):
        contacts, fixed = set(), set()
        for pad, pad_rules in self.pads:
            bounds, net = _box(pad), pad.GetNetCode()
            uid = str(pad.m_Uuid.AsString())
            shapes = {}
            for item in self.items:
                if net > 0 and net == item['net']:
                    continue
                for layer, own_gap in pad_rules.items():
                    other = item['layers'].get(layer)
                    if other is None:
                        continue
                    shape, obstacle_gap = other
                    gap = max(own_gap, obstacle_gap)
                    if not _near(bounds, item['box'], gap):
                        continue
                    if layer not in shapes:
                        shapes[layer] = pad.GetEffectiveShape(layer)
                    if shapes[layer].Collide(shape, gap):
                        key = (uid, item['uid'], layer)
                        contacts.add(key)
                        if item['fixed']:
                            fixed.add(key)
        return contacts, fixed

    def score(self, candidate):
        dx, dy, angle = (float(candidate[field]) for field in
                         ('dx_mm', 'dy_mm', 'rotation_delta_deg'))
        if not all(math.isfinite(v) for v in (dx, dy, angle)):
            raise ValueError('nonfinite native pose')
        # Same clockwise-positive board transform used by the actual mover.
        theta = math.radians(angle)
        cosine, sine = math.cos(theta), math.sin(theta)
        try:
            for fp, position, orientation in self.poses:
                x, y = position.x-self.origin.x, position.y-self.origin.y
                fp.SetPosition(pcbnew.VECTOR2I(
                    round(self.origin.x + dx*MM + cosine*x + sine*y),
                    round(self.origin.y + dy*MM - sine*x + cosine*y)))
                fp.SetOrientationDegrees(orientation + angle)
            contacts, fixed = self._contacts()
        finally:
            for fp, position, orientation in self.poses:
                fp.SetPosition(position)
                fp.SetOrientationDegrees(orientation)
        new = contacts - self.baseline
        return dict(new_fixed_copper_pairs=len(new & fixed),
                    new_copper_pairs=len(new), copper_pairs=len(contacts),
                    conflicting_copper_uuids=sorted({key[1] for key in new})[:32],
                    qualification_authority=False,
                    clearance_scope='saved_project_class_native_local_and_board_floor',
                    custom_rule_and_refill_proof_required=True)
