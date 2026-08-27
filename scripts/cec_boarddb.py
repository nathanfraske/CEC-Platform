#!/usr/bin/env python3
"""Immutable, incrementally transformed PCB geometry used by physical planning.

The KiCad board remains the release authority. This module is a read-only
geometry cache for the high-volume proposal side of placement: load exact pad
bounds once, then evaluate translations and orthogonal rotations without
serializing and reparsing a complete ``.kicad_pcb`` file for every trial.

Only transforms that preserve the exact axis-aligned pad bounds used by the
current pin-access oracle are admitted. Orthogonal rotation preserves that
contract exactly by rotating the source bbox corners. A caller asking for an
arbitrary transform receives :class:`UnsupportedTransform` and must fall back
to materializing a board and asking KiCad. This is deliberate fail-closed
behaviour, not an approximation path.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import threading
from dataclasses import dataclass


class UnsupportedTransform(ValueError):
    """The incremental view cannot reproduce exact source geometry."""


@dataclass(frozen=True)
class FootprintPose:
    ref: str
    x: float
    y: float
    rotation: float


@dataclass(frozen=True)
class PadGeometry:
    index: int
    ref: str
    pad: str
    net: str
    x: float
    y: float
    bbox: tuple[float, float, float, float]
    layers: tuple[str, ...]
    smd: bool = False
    pofv: bool = False

    def as_record(self):
        return {
            "ref": self.ref,
            "pad": self.pad,
            "net": self.net,
            "x": self.x,
            "y": self.y,
            "bbox": self.bbox,
            "layers": self.layers,
            "smd": self.smd,
            "pofv": self.pofv,
        }


def _canonical_angle(value):
    angle = float(value) % 360.0
    if abs(angle - 360.0) < 1.0e-9 or abs(angle) < 1.0e-9:
        return 0.0
    return angle


def _orientation_degrees(footprint):
    try:
        return float(footprint.GetOrientationDegrees())
    except Exception:  # noqa: BLE001 - KiCad API differs between releases
        orientation = footprint.GetOrientation()
        try:
            return float(orientation.AsDegrees())
        except Exception:  # noqa: BLE001
            return float(orientation.AsTenthsOfADegree()) / 10.0


def _normalized_placements(placements):
    rows = []
    for ref, pose in sorted((placements or {}).items()):
        if len(pose) < 3:
            raise ValueError("placement for %s must be (x, y, rotation)" % ref)
        rows.append((str(ref), round(float(pose[0]), 9),
                     round(float(pose[1]), 9),
                     round(_canonical_angle(pose[2]), 9)))
    return tuple(rows)


class PadSpatialIndex:
    """Small deterministic uniform index for pad-obstruction candidates."""

    def __init__(self, records, *, cell_mm=2.0):
        self.records = tuple(records)
        self.cell_mm = max(0.1, float(cell_mm))
        cells = collections.defaultdict(list)
        for index, row in enumerate(self.records):
            x0, y0, x1, y1 = row["bbox"]
            gx0, gy0 = self._cell(x0, y0)
            gx1, gy1 = self._cell(x1, y1)
            for layer in row["layers"]:
                for gy in range(gy0, gy1 + 1):
                    for gx in range(gx0, gx1 + 1):
                        cells[(str(layer), gx, gy)].append(index)
        self._cells = {key: tuple(value) for key, value in cells.items()}

    def _cell(self, x, y):
        return (int(math.floor(float(x) / self.cell_mm)),
                int(math.floor(float(y) / self.cell_mm)))

    def query_segment(self, layer, x0, y0, x1, y1, *, margin=0.0):
        """Return source-ordered pads whose grid cells can meet the segment."""
        lo_x = min(float(x0), float(x1)) - float(margin)
        hi_x = max(float(x0), float(x1)) + float(margin)
        lo_y = min(float(y0), float(y1)) - float(margin)
        hi_y = max(float(y0), float(y1)) + float(margin)
        gx0, gy0 = self._cell(lo_x, lo_y)
        gx1, gy1 = self._cell(hi_x, hi_y)
        found = set()
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                found.update(self._cells.get((str(layer), gx, gy), ()))
        return tuple(sorted(found))


class BoardView:
    """One exact placement delta over an immutable :class:`BoardDB`."""

    def __init__(self, database, placement_key):
        self.database = database
        self.placement_key = tuple(placement_key)
        self.placements = {
            ref: (x, y, rotation)
            for ref, x, y, rotation in self.placement_key
        }
        self.dirty_refs = tuple(ref for ref, *_rest in self.placement_key)
        self.dirty_pad_indices = tuple(
            index for ref in self.dirty_refs
            for index in database.pad_indices_by_ref.get(ref, ()))
        self._records = None
        self._spatial_index = None

    @property
    def invalidation(self):
        return {
            "dirty_footprints": self.dirty_refs,
            "dirty_footprint_count": len(self.dirty_refs),
            "dirty_pad_indices": self.dirty_pad_indices,
            "dirty_pad_count": len(self.dirty_pad_indices),
        }

    def _transform(self, pad, source, target):
        delta = _canonical_angle(target.rotation - source.rotation)
        quarter = int(round(delta / 90.0)) % 4
        expected = float(quarter * 90)
        if abs(delta - expected) >= 1.0e-9:
            raise UnsupportedTransform(
                "%s rotation delta %.6f is not exact in bbox mode" %
                (pad.ref, delta))

        def point(px, py):
            dx, dy = px - source.x, py - source.y
            # KiCad board coordinates are Y-down. These integer quarter-turn
            # maps are exact and avoid sin/cos noise at orthogonal angles.
            if quarter == 0:
                rdx, rdy = dx, dy
            elif quarter == 1:
                rdx, rdy = dy, -dx
            elif quarter == 2:
                rdx, rdy = -dx, -dy
            else:
                rdx, rdy = -dy, dx
            return target.x + rdx, target.y + rdy
        x, y = point(pad.x, pad.y)
        x0, y0, x1, y1 = pad.bbox
        corners = (point(x0, y0), point(x0, y1),
                   point(x1, y0), point(x1, y1))
        xs = [row[0] for row in corners]
        ys = [row[1] for row in corners]
        # KiCad source geometry is integer nanometres. Canonicalize back to
        # the six decimal millimetre precision exposed by its Python API so an
        # incremental result is byte-stable with a materialize/reload result.
        x, y = round(x, 6), round(y, 6)
        bbox = tuple(round(value, 6) for value in
                     (min(xs), min(ys), max(xs), max(ys)))
        return PadGeometry(
            index=pad.index, ref=pad.ref, pad=pad.pad, net=pad.net,
            x=x, y=y, bbox=bbox,
            layers=pad.layers, smd=pad.smd, pofv=pad.pofv)

    @property
    def pad_records(self):
        if self._records is None:
            overrides = {
                ref: FootprintPose(ref, x, y, rotation)
                for ref, (x, y, rotation) in self.placements.items()
            }
            rows = []
            for pad in self.database.pads:
                target = overrides.get(pad.ref)
                if target is None:
                    transformed = pad
                else:
                    transformed = self._transform(
                        pad, self.database.footprints[pad.ref], target)
                rows.append(transformed.as_record())
            self._records = tuple(rows)
        return self._records

    @property
    def spatial_index(self):
        if self._spatial_index is None:
            self._spatial_index = PadSpatialIndex(self.pad_records)
        return self._spatial_index

    @property
    def fingerprint(self):
        payload = {
            "base": self.database.fingerprint,
            "placements": self.placement_key,
        }
        return hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8")).hexdigest()


class BoardDB:
    """Immutable board geometry with a small bounded exact-delta cache."""

    SCHEMA = 1

    def __init__(self, *, board_path, routing_layers, copper_layer_count,
                 profile, declared_profile,
                 pofv_geometry_mm, edge_bbox, footprints, pads,
                 cache_entries=128):
        self.board_path = (os.path.abspath(board_path)
                           if board_path else "<records>")
        self.routing_layers = tuple(str(row) for row in routing_layers)
        self.copper_layer_count = int(copper_layer_count)
        if self.copper_layer_count < len(self.routing_layers):
            raise ValueError("copper layer count cannot be smaller than "
                             "routing layer count")
        self.profile = profile
        self.declared_profile = declared_profile
        self.pofv_geometry_mm = (tuple(pofv_geometry_mm)
                                 if pofv_geometry_mm else None)
        self.edge_bbox = tuple(float(value) for value in edge_bbox)
        self.footprints = {pose.ref: pose for pose in footprints}
        self.pads = tuple(pads)
        by_ref = collections.defaultdict(list)
        for index, pad in enumerate(self.pads):
            if pad.index != index:
                raise ValueError("pad indices must be contiguous and ordered")
            if pad.ref not in self.footprints:
                raise ValueError("pad %s.%s has no footprint pose" %
                                 (pad.ref, pad.pad))
            by_ref[pad.ref].append(index)
        self.pad_indices_by_ref = {
            ref: tuple(indices) for ref, indices in by_ref.items()}
        self._cache_entries = max(1, int(cache_entries))
        self._views = collections.OrderedDict()
        self._lock = threading.Lock()
        self._fingerprint = None

    @classmethod
    def from_records(cls, *, routing_layers, edge_bbox, footprints, pads,
                     copper_layer_count=None,
                     profile=None, declared_profile=None,
                     pofv_geometry_mm=None, board_path=None,
                     cache_entries=128):
        poses = [row if isinstance(row, FootprintPose) else FootprintPose(
            str(row["ref"]), float(row["x"]), float(row["y"]),
            _canonical_angle(row.get("rotation", 0.0)))
                 for row in footprints]
        geometries = []
        for index, row in enumerate(pads):
            if isinstance(row, PadGeometry):
                geometry = row
            else:
                geometry = PadGeometry(
                    index=index, ref=str(row["ref"]), pad=str(row["pad"]),
                    net=str(row["net"]), x=float(row["x"]),
                    y=float(row["y"]),
                    bbox=tuple(float(value) for value in row["bbox"]),
                    layers=tuple(str(value) for value in row["layers"]),
                    smd=bool(row.get("smd", False)),
                    pofv=bool(row.get("pofv", False)))
            geometries.append(geometry)
        return cls(
            board_path=board_path, routing_layers=routing_layers,
            copper_layer_count=(len(tuple(routing_layers))
                                if copper_layer_count is None
                                else copper_layer_count),
            profile=profile, declared_profile=declared_profile,
            pofv_geometry_mm=pofv_geometry_mm,
            edge_bbox=edge_bbox, footprints=poses, pads=geometries,
            cache_entries=cache_entries)

    @classmethod
    def from_board(cls, board_path, *, include_power=True, cache_entries=128):
        import pcbnew
        import cec_fab_profile

        board = pcbnew.LoadBoard(str(board_path))
        routing_layers = cec_fab_profile.routing_layers(
            board, hint=str(board_path), include_power=include_power)
        profile_name = cec_fab_profile.active_profile_name(
            board, hint=str(board_path))
        declared_profile = cec_fab_profile.board_profile_name(board)
        profile = (cec_fab_profile.get_profile(profile_name)
                   if profile_name else None)
        pofv_geometry = cec_fab_profile.preferred_pofv_geometry(profile)
        layer_ids = {name: board.GetLayerID(name) for name in routing_layers}
        via_radius_nm = (int(round(pofv_geometry[0] * 1e6 / 2.0))
                         if pofv_geometry else None)
        footprints = []
        pads = []
        for footprint in board.GetFootprints():
            ref = str(footprint.GetReference())
            fp_pos = footprint.GetPosition()
            footprints.append(FootprintPose(
                ref, fp_pos.x / 1e6, fp_pos.y / 1e6,
                _canonical_angle(_orientation_degrees(footprint))))
            for pad in footprint.Pads():
                net = str(pad.GetNetname())
                if not net:
                    continue
                layers = tuple(
                    name for name, layer_id in layer_ids.items()
                    if layer_id >= 0 and pad.IsOnLayer(layer_id))
                if not layers:
                    continue
                pos = pad.GetPosition()
                boxes = []
                for name in layers:
                    try:
                        box = pad.GetEffectiveShape(layer_ids[name]).BBox()
                        boxes.append((
                            box.GetX() / 1e6, box.GetY() / 1e6,
                            (box.GetX() + box.GetWidth()) / 1e6,
                            (box.GetY() + box.GetHeight()) / 1e6))
                    except Exception:  # noqa: BLE001
                        pass
                size = pad.GetSize()
                fallback = (
                    pos.x / 1e6 - size.x / 2e6,
                    pos.y / 1e6 - size.y / 2e6,
                    pos.x / 1e6 + size.x / 2e6,
                    pos.y / 1e6 + size.y / 2e6)
                bbox = ((min(box[0] for box in boxes),
                         min(box[1] for box in boxes),
                         max(box[2] for box in boxes),
                         max(box[3] for box in boxes))
                        if boxes else fallback)
                try:
                    smd = (int(pad.GetAttribute()) ==
                           int(pcbnew.PAD_ATTRIB_SMD))
                except Exception:  # noqa: BLE001
                    smd = False
                pofv = False
                if smd and via_radius_nm is not None:
                    try:
                        pofv = bool(cec_fab_profile._pad_contains_circle(
                            pad, pos, via_radius_nm))
                    except Exception:  # noqa: BLE001
                        pofv = False
                pads.append(PadGeometry(
                    index=len(pads), ref=ref, pad=str(pad.GetNumber()),
                    net=net, x=pos.x / 1e6, y=pos.y / 1e6,
                    bbox=bbox, layers=layers, smd=smd, pofv=pofv))
        edge = board.GetBoardEdgesBoundingBox()
        edge_bbox = (edge.GetLeft() / 1e6, edge.GetTop() / 1e6,
                     edge.GetRight() / 1e6, edge.GetBottom() / 1e6)
        return cls(
            board_path=str(board_path), routing_layers=routing_layers,
            copper_layer_count=board.GetCopperLayerCount(),
            profile=profile_name, declared_profile=declared_profile,
            pofv_geometry_mm=pofv_geometry,
            edge_bbox=edge_bbox, footprints=footprints, pads=pads,
            cache_entries=cache_entries)

    @property
    def fingerprint(self):
        if self._fingerprint is None:
            payload = {
                "schema": self.SCHEMA,
                "routing_layers": self.routing_layers,
                "copper_layer_count": self.copper_layer_count,
                "profile": self.profile,
                "declared_profile": self.declared_profile,
                "pofv_geometry_mm": self.pofv_geometry_mm,
                "edge_bbox": self.edge_bbox,
                "footprints": [pose.__dict__ for pose in sorted(
                    self.footprints.values(), key=lambda row: row.ref)],
                "pads": [pad.as_record() for pad in self.pads],
            }
            self._fingerprint = hashlib.sha256(json.dumps(
                payload, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8")).hexdigest()
        return self._fingerprint

    def view(self, placements=None):
        key = _normalized_placements(placements)
        for ref, *_rest in key:
            if ref not in self.footprints:
                raise KeyError("unknown footprint %s" % ref)
        effective = []
        for ref, x, y, rotation in key:
            source = self.footprints[ref]
            if (abs(x - source.x) < 1.0e-9
                    and abs(y - source.y) < 1.0e-9
                    and abs(_canonical_angle(rotation - source.rotation))
                    < 1.0e-9):
                continue
            effective.append((ref, x, y, rotation))
        key = tuple(effective)
        with self._lock:
            view = self._views.get(key)
            if view is not None:
                self._views.move_to_end(key)
                return view
            view = BoardView(self, key)
            self._views[key] = view
            while len(self._views) > self._cache_entries:
                self._views.popitem(last=False)
            return view
