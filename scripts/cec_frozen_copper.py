"""Exact, board-neutral placement boundaries for retained locked copper.

This is an early rejection filter, not a replacement for native DRC or the
final primitive-prefix proof. It never moves or regenerates a conductor.
"""
from __future__ import annotations

import copy
import math


class FrozenCopperConflict(ValueError):
    """Typed live-geometry refusal, usable without parsing exception prose."""

    def __init__(self, report):
        self.report = copy.deepcopy(report)
        super().__init__("placement conflicts with frozen copper: %s" %
                         (self.report.get("violations") or [])[:12])


def require_present(board, nets):
    """An emitter cannot claim retained authority from net names alone."""
    counts = {str(net): 0 for net in nets}
    for item in board.GetTracks():
        net = str(item.GetNetname())
        if item.IsLocked() and net in counts:
            counts[net] += 1
    missing = [net for net, count in counts.items() if not count]
    if missing:
        raise ValueError("declared frozen copper is absent: %s" % sorted(missing))
    return counts


def require_items(board, item_uuids):
    """Validate item-scoped retention without granting authority over its net."""
    requested = set(item_uuids)
    found = {str(item.m_Uuid.AsString()): item for item in board.GetTracks()
             if str(item.m_Uuid.AsString()) in requested}
    missing = requested - set(found)
    unlocked = [uid for uid, item in found.items() if not item.IsLocked()]
    if missing or unlocked:
        raise ValueError("frozen item absent or unlocked: missing=%s unlocked=%s" %
                         (sorted(missing), sorted(unlocked)))
    return found


def topology_changes(board, pad_nets, inventory, nets, remove_refs=()):
    """Reject live net/package changes which invalidate a frozen interface."""
    selected = set(nets)
    removed = set(remove_refs)
    actual = {}
    changes = []
    for footprint in board.GetFootprints():
        ref = str(footprint.GetReference())
        touches = False
        for pad in footprint.Pads():
            key = (ref, str(pad.GetNumber()))
            old = str(pad.GetNetname())
            new = str(pad_nets.get(key) or "")
            actual[key] = old
            if old in selected or new in selected:
                touches = True
                if old != new or ref in removed:
                    changes.append({"ref": ref, "pad": key[1],
                                    "before": old, "after": new,
                                    "kind": "frozen_pad_assignment_changed"})
        expected = str((inventory.get(ref) or {}).get("footprint") or "")
        if touches and expected and expected != footprint.GetFPID().GetUniStringLibId():
            changes.append({"ref": ref, "kind": "frozen_package_changed"})
    for key, net in pad_nets.items():
        if net in selected and key not in actual:
            changes.append({"ref": key[0], "pad": key[1],
                            "kind": "new_frozen_interface"})
    return changes


class FrozenCopperContext:
    """Cache immutable native shapes while probing reversible footprint poses."""

    def __init__(self, board_path, nets, *, clearance_mm=0.2, item_uuids=()):
        import pcbnew
        if not math.isfinite(clearance_mm) or clearance_mm < 0:
            raise ValueError("invalid frozen copper clearance")
        self.board = pcbnew.LoadBoard(str(board_path))
        if self.board is None:
            raise ValueError("frozen copper source is unreadable")
        self.nets = set(nets)
        selected_items = require_items(self.board, item_uuids)
        self.clearance = max(pcbnew.FromMM(clearance_mm),
                             self.board.GetDesignSettings().m_MinClearance)
        import cec_route_dimensions
        self.netclass = cec_route_dimensions.project_resolver(board_path, board=self.board)
        self.footprints = {str(fp.GetReference()): fp
                           for fp in self.board.GetFootprints()}
        self.original = {ref: self._pose(fp) for ref, fp in self.footprints.items()}
        self.items = []
        self.cache = {}
        for item in self.board.GetTracks():
            if not item.IsLocked() or (str(item.GetNetname()) not in self.nets
                    and str(item.m_Uuid.AsString()) not in selected_items):
                continue
            layers = tuple(item.GetLayerSet().CuStack())
            self.items.append({
                "net": str(item.GetNetname()), "uuid": str(item.m_Uuid.AsString()),
                "box": self._box(item), "clearance": self._clearance(item),
                "shapes": {layer: item.GetEffectiveShape(layer) for layer in layers},
            })
        # An attached immutable conductor cannot follow its terminal. Moving
        # that owning package requires an explicit topology-replacement task.
        self.anchor_refs = set()
        self.anchor_attachments = {}
        contact_nets = {item['net'] for item in self.items}
        for ref, fp in self.footprints.items():
            attachments = []
            for pad in fp.Pads():
                if str(pad.GetNetname()) not in contact_nets:
                    continue
                for item in self.items:
                    if (item['net'] == str(pad.GetNetname())
                            and self._collides(pad, item, 0)):
                        attachments.append(dict(pad=str(pad.GetNumber()),
                            copper_net=item['net'], copper_uuid=item['uuid']))
            if attachments:
                self.anchor_refs.add(ref)
                self.anchor_attachments[ref] = attachments

    @staticmethod
    def _pose(fp):
        p = fp.GetPosition()
        return (p.x / 1e6, p.y / 1e6, fp.GetOrientationDegrees(), bool(fp.IsFlipped()))

    @staticmethod
    def _box(item):
        box = item.GetBoundingBox()
        return box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom()

    def _clearance(self, item):
        # KiCad 10 exposes GetEffectiveNetClass as an untyped shared_ptr on
        # some builds. Use the pipeline's project-authoritative resolver.
        clearance = float(self.netclass(str(item.GetNetname())).get("clearance") or 0)
        if not math.isfinite(clearance) or clearance < 0:
            raise ValueError("invalid frozen-copper netclass clearance")
        return max(self.clearance, round(clearance * 1e6))

    def _collides(self, pad, item, clearance):
        a, b = self._box(pad), item["box"]
        if (a[2] + clearance < b[0] or b[2] + clearance < a[0]
                or a[3] + clearance < b[1] or b[3] + clearance < a[1]):
            return False
        for layer in pad.GetLayerSet().CuStack():
            shape = item["shapes"].get(layer)
            if shape is not None and pad.GetEffectiveShape(layer).Collide(shape, clearance):
                return True
        return False

    def check(self, placements, *, back_refs=None):
        import pcbnew
        desired_back = set(back_refs) if back_refs is not None else None
        key = tuple((str(ref), *(round(float(v), 6) for v in pose[:3]),
                     (str(ref) in desired_back if desired_back is not None
                      else self.original.get(str(ref), (0, 0, 0, False))[3]))
                    for ref, pose in sorted(placements.items()))
        if key in self.cache:
            return copy.deepcopy(self.cache[key])
        moved = []
        violations = []
        try:
            for ref, x, y, angle, back in key:
                if ref not in self.footprints:
                    raise ValueError("unknown placement reference %s" % ref)
                old = self.original[ref]
                if (abs(old[0] - x) <= 1e-6 and abs(old[1] - y) <= 1e-6
                        and abs((old[2] - angle + 180) % 360 - 180) <= 1e-6
                        and old[3] == back):
                    continue
                if ref in self.anchor_refs:
                    violations.append({"ref": ref, "kind": "frozen_anchor_moved",
                        "attachments_complete": True,
                        "attachments": copy.deepcopy(self.anchor_attachments[ref])})
                    continue
                fp = self.footprints[ref]
                moved.append(ref)
                if bool(fp.IsFlipped()) != back:
                    fp.Flip(fp.GetPosition(), False)
                fp.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                fp.SetOrientationDegrees(angle)
            for ref in moved:
                for pad in self.footprints[ref].Pads():
                    net = str(pad.GetNetname())
                    for item in self.items:
                        if net == item["net"]:
                            continue
                        clearance = max(self._clearance(pad), item["clearance"])
                        if self._collides(pad, item, clearance):
                            violations.append({"ref": ref, "pad": str(pad.GetNumber()),
                                "net": net, "copper_net": item["net"],
                                "copper_uuid": item["uuid"],
                                "clearance_mm": clearance / 1e6,
                                "kind": "fixed_copper_pad_collision"})
        finally:
            for ref in moved:
                fp = self.footprints[ref]
                x, y, angle, back = self.original[ref]
                if bool(fp.IsFlipped()) != back:
                    fp.Flip(fp.GetPosition(), False)
                fp.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                fp.SetOrientationDegrees(angle)
        result = {"ok": not violations, "checked_refs": sorted(moved),
                  "protected_items": len(self.items), "violations": violations}
        self.cache[key] = copy.deepcopy(result)
        return result
