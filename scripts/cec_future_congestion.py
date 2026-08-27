#!/usr/bin/env python3
"""Incremental, layer-aware future-route congestion forecasting.

This is a placement cost model, not a detailed router and never a release
authority.  It converts each net's terminal geometry into a deterministic MST,
selects a legal layer and monotone corridor for every edge, spreads fixed-point
RUDY demand over the edge rectangle, accounts for expected via occupancy, and
reserves the selected corridors of critical nets.  It also consumes the exact
rectangles produced by the routed-object/power-rail compiler.  A placement is
therefore scored against the same surface ownership that the detailed router
will receive instead of an easier, rail-free approximation of the board.

The important property is incremental invalidation.  A footprint proposal
changes only its pad-owner cells, its incident nets, and nets whose *possible*
route corridors cross those cells.  Those forecasts are removed and rebuilt;
all other per-net contributions remain immutable.  The resulting metrics are
exactly equivalent to a full recomputation of this model.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
from dataclasses import dataclass

import numpy as np


DEMAND_SCALE = 1024
VIA_COST_CELLS = 6


def _cell_key(cell):
    return tuple(int(value) for value in cell)


def _add_sparse(target, source, sign=1):
    for cell, value in source.items():
        updated = target.get(cell, 0) + int(sign) * int(value)
        if updated:
            target[cell] = updated
        else:
            target.pop(cell, None)


def _line(y0, x0, y1, x1):
    if y0 == y1:
        step = 1 if x1 >= x0 else -1
        return [(y0, x) for x in range(x0, x1 + step, step)]
    if x0 == x1:
        step = 1 if y1 >= y0 else -1
        return [(y, x0) for y in range(y0, y1 + step, step)]
    raise ValueError("future-congestion line must be Manhattan")


def _l_paths(layer, src, dst):
    sy, sx = src
    dy, dx = dst
    horizontal = _line(sy, sx, sy, dx) + _line(sy, dx, dy, dx)[1:]
    vertical = _line(sy, sx, dy, sx) + _line(dy, sx, dy, dx)[1:]
    rows = []
    for path in (horizontal, vertical):
        cells = tuple((int(layer), int(y), int(x)) for y, x in path)
        if cells not in rows:
            rows.append(cells)
    return tuple(rows)


@dataclass(frozen=True)
class _Terminal:
    index: int
    ref: str
    pad: str
    net: str
    y: int
    x: int
    layers: tuple[int, ...]

    @property
    def key(self):
        return (self.y, self.x, self.layers, self.ref, self.pad, self.index)


@dataclass(frozen=True)
class NetPolicy:
    kind: str
    allowed_layers: tuple[bool, ...]
    critical: bool


@dataclass(frozen=True)
class NetForecast:
    net: str
    wire_demand: tuple
    via_demand: tuple
    corridor_cells: tuple
    candidate_cells: tuple
    via_count: int
    obstacle_crossings: int
    reservation_crossings: int
    edge_count: int

    def wire_dict(self):
        return dict(self.wire_demand)

    def via_dict(self):
        return dict(self.via_demand)


class FutureCongestionContext:
    """Immutable baseline plus sparse proposal-delta evaluator."""

    SCHEMA = 1

    def __init__(self, database, conns, stackup, *, critical_nets=(),
                 reservations=(), reservation_report=None,
                 grid_mm=1.0, pitch_mm=0.45):
        self.database = database
        self.grid_mm = float(grid_mm)
        if self.grid_mm <= 0:
            raise ValueError("grid_mm must be positive")
        self.pitch_mm = float(pitch_mm)
        self.layer_names = tuple(database.routing_layers)
        self.layer_index = {name: index
                            for index, name in enumerate(self.layer_names)}
        self.layer_count = len(self.layer_names)
        if not self.layer_count:
            raise ValueError("future congestion needs routing layers")
        self.x0, self.y0, x1, y1 = database.edge_bbox
        self.width = max(1, int((x1 - self.x0) / self.grid_mm) + 1)
        self.height = max(1, int((y1 - self.y0) / self.grid_mm) + 1)
        self.capacity_tracks = max(
            1, int(math.floor(self.grid_mm / self.pitch_mm + 1.0e-9)))
        self.capacity_units = self.capacity_tracks * DEMAND_SCALE
        self.policies = self._policies(conns, stackup, set(critical_nets))
        self.reservations = tuple(self._normalize_reservation(row)
                                  for row in (reservations or ()))
        self.reservation_report = dict(reservation_report or {})
        self.reservation_owners = self._reservation_owners(self.reservations)
        self.reservation_cells = frozenset(self.reservation_owners)
        self.reservation_owned_nets = frozenset(
            str(net) for net, row in self.reservation_report.items()
            if isinstance(row, dict) and row.get("reserved"))
        self.base_records = tuple(database.view().pad_records)
        self.base_pad_cells = tuple(
            self._pad_cells(row) for row in self.base_records)
        self.base_owner_counts = self._owner_counts(
            self.base_records, self.base_pad_cells)
        self.base_records_by_net = self._records_by_net(self.base_records)
        self.base_forecasts = self._build_forecasts(
            self.base_records_by_net, self._base_owners)
        self.dependent_nets_by_cell = self._dependency_index(
            self.base_forecasts)
        self._base_arrays = self._aggregate(self.base_forecasts)
        self._base_summary = self._summarize(
            self.base_forecasts, self._base_arrays,
            records=self.base_records, pad_cells=self.base_pad_cells)
        payload = {
            "schema": self.SCHEMA,
            "board": database.fingerprint,
            "grid_mm": self.grid_mm,
            "pitch_mm": self.pitch_mm,
            "critical_nets": sorted(
                net for net, policy in self.policies.items()
                if policy.critical),
            "reservations": self.reservations,
            "reservation_owned_nets": sorted(self.reservation_owned_nets),
        }
        self.fingerprint = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8")).hexdigest()

    def _normalize_reservation(self, row):
        if not isinstance(row, dict):
            raise ValueError("route reservation must be a mapping")
        layer = str(row.get("layer", ""))
        if layer not in self.layer_index:
            raise ValueError("reservation uses non-routing layer %r" % layer)
        values = tuple(float(row[name])
                       for name in ("x0", "y0", "x1", "y1"))
        x0, y0, x1, y1 = values
        if x1 < x0 or y1 < y0:
            raise ValueError("reservation rectangle is inverted")
        return (str(row.get("net", "")), layer, x0, y0, x1, y1)

    def _reservation_owners(self, reservations):
        owners = collections.defaultdict(set)
        for net, layer_name, x0, y0, x1, y1 in reservations:
            layer = self.layer_index[layer_name]
            gx0 = max(0, int(math.floor((x0 - self.x0) / self.grid_mm)))
            gy0 = max(0, int(math.floor((y0 - self.y0) / self.grid_mm)))
            # Compiler rectangles are half-open at their far edge. Adjacent
            # covering rectangles must not invent an extra occupied grid cell.
            gx1 = min(self.width - 1, int(math.ceil(
                (x1 - self.x0) / self.grid_mm) - 1))
            gy1 = min(self.height - 1, int(math.ceil(
                (y1 - self.y0) / self.grid_mm) - 1))
            if gx1 < gx0 or gy1 < gy0:
                continue
            for gy in range(gy0, gy1 + 1):
                for gx in range(gx0, gx1 + 1):
                    owners[(layer, gy, gx)].add(net)
        return {cell: frozenset(nets) for cell, nets in owners.items()}

    def _foreign_reservation(self, net, cell):
        return int(any(owner != net for owner in
                       self.reservation_owners.get(_cell_key(cell), ())))

    def _policies(self, conns, stackup, critical_nets):
        kinds = tuple(stackup.get("net_kinds") or ())
        allowed = tuple(stackup.get("allowed_layers_by_conn") or ())
        if len(conns) != len(kinds) or len(conns) != len(allowed):
            raise ValueError("connection policy arrays must have equal length")
        policies = {}
        for conn, kind, layer_mask in zip(conns, kinds, allowed):
            net = str(conn[0])
            mask = tuple(bool(value) for value in layer_mask)
            if len(mask) != self.layer_count or not any(mask):
                raise ValueError("invalid allowed-layer policy for %s" % net)
            policy = NetPolicy(str(kind), mask, net in critical_nets)
            previous = policies.get(net)
            if previous is not None and previous != policy:
                raise ValueError("inconsistent repeated policy for %s" % net)
            policies[net] = policy
        return policies

    def _grid_point(self, x, y):
        gx = int((float(x) - self.x0) / self.grid_mm)
        gy = int((float(y) - self.y0) / self.grid_mm)
        return (min(self.height - 1, max(0, gy)),
                min(self.width - 1, max(0, gx)))

    def _pad_cells(self, row):
        bx0, by0, bx1, by1 = row["bbox"]
        gx0 = max(0, int(math.floor((bx0 - self.x0) / self.grid_mm)))
        gy0 = max(0, int(math.floor((by0 - self.y0) / self.grid_mm)))
        gx1 = min(self.width - 1,
                  int(math.floor((bx1 - self.x0) / self.grid_mm)))
        gy1 = min(self.height - 1,
                  int(math.floor((by1 - self.y0) / self.grid_mm)))
        layers = [self.layer_index[name] for name in row["layers"]
                  if name in self.layer_index]
        return tuple((layer, gy, gx) for layer in layers
                     for gy in range(gy0, gy1 + 1)
                     for gx in range(gx0, gx1 + 1))

    @staticmethod
    def _owner_counts(records, cells_by_index):
        owners = collections.defaultdict(collections.Counter)
        for index, cells in enumerate(cells_by_index):
            net = str(records[index]["net"])
            for cell in cells:
                owners[cell][net] += 1
        return {cell: dict(counts) for cell, counts in owners.items()}

    @staticmethod
    def _records_by_net(records):
        grouped = collections.defaultdict(list)
        for index, row in enumerate(records):
            grouped[str(row["net"])].append((index, row))
        return {net: tuple(rows) for net, rows in grouped.items()}

    def _base_owners(self, cell):
        return self.base_owner_counts.get(_cell_key(cell), {})

    def _terminals(self, net, records):
        rows = []
        for index, row in records:
            layers = tuple(sorted({self.layer_index[name]
                                   for name in row["layers"]
                                   if name in self.layer_index}))
            if not layers:
                continue
            y, x = self._grid_point(row["x"], row["y"])
            rows.append(_Terminal(
                int(index), str(row["ref"]), str(row["pad"]), net,
                y, x, layers))
        return tuple(sorted(rows, key=lambda terminal: terminal.key))

    @staticmethod
    def _mst_edges(terminals):
        if len(terminals) < 2:
            return ()
        used = {0}
        edges = []
        while len(used) < len(terminals):
            best = None
            for left in sorted(used):
                a = terminals[left]
                for right, b in enumerate(terminals):
                    if right in used:
                        continue
                    distance = abs(a.y - b.y) + abs(a.x - b.x)
                    key = (distance, a.key, b.key, left, right)
                    if best is None or key < best[0]:
                        best = (key, left, right)
            _key, left, right = best
            used.add(right)
            edges.append((terminals[left], terminals[right]))
        return tuple(edges)

    @staticmethod
    def _foreign_owners(owner_lookup, cell, net):
        return sum(int(count) for owner, count in owner_lookup(cell).items()
                   if owner != net and int(count) > 0)

    def _via_cells(self, terminal, route_layer):
        if route_layer in terminal.layers:
            return ()
        home = min(terminal.layers,
                   key=lambda layer: (abs(layer - route_layer), layer))
        lo, hi = sorted((home, route_layer))
        return tuple((layer, terminal.y, terminal.x)
                     for layer in range(lo, hi + 1))

    def _edge_candidates(self, net, policy, left, right, owner_lookup):
        candidates = []
        all_candidate_cells = set()
        horizontal = abs(right.x - left.x)
        vertical = abs(right.y - left.y)
        for layer, admitted in enumerate(policy.allowed_layers):
            if not admitted:
                continue
            via_left = self._via_cells(left, layer)
            via_right = self._via_cells(right, layer)
            via_count = int(bool(via_left)) + int(bool(via_right))
            for path in _l_paths(
                    layer, (left.y, left.x), (right.y, right.x)):
                candidate = set(path) | set(via_left) | set(via_right)
                all_candidate_cells.update(candidate)
                obstacles = sum(self._foreign_owners(
                    owner_lookup, cell, net) for cell in candidate)
                reservation_crossings = sum(
                    self._foreign_reservation(net, cell)
                    for cell in candidate)
                # Alternating preferred direction by routing-layer index is a
                # deterministic global-routing convention, not a hard rule.
                wrong_way = vertical if layer % 2 == 0 else horizontal
                score = ((obstacles + reservation_crossings) * 64
                         + via_count * VIA_COST_CELLS
                         + int(math.ceil(wrong_way / 4.0)))
                candidates.append((score, obstacles, reservation_crossings,
                                   via_count, layer,
                                   tuple(path), via_left, via_right))
        if not candidates:
            raise ValueError("net %s has no legal route layer" % net)
        chosen = min(candidates, key=lambda row: (
            row[0], row[3], row[4], row[5]))
        return chosen, all_candidate_cells

    @staticmethod
    def _spread_rect(layer, left, right):
        y0, y1 = sorted((left.y, right.y))
        x0, x1 = sorted((left.x, right.x))
        cells = [(layer, y, x) for y in range(y0, y1 + 1)
                 for x in range(x0, x1 + 1)]
        total = (abs(left.y - right.y) + abs(left.x - right.x) + 1) \
            * DEMAND_SCALE
        quotient, remainder = divmod(total, len(cells))
        return {cell: quotient + (1 if index < remainder else 0)
                for index, cell in enumerate(cells)}

    def _forecast(self, net, records, owner_lookup):
        policy = self.policies[net]
        # A successful routed-object reservation owns the complete rail net in
        # the detailed route contract. Do not forecast a duplicate trace through
        # the full-capacity surface that already owns all of that net's pads.
        if net in self.reservation_owned_nets:
            return NetForecast(
                net=net, wire_demand=(), via_demand=(), corridor_cells=(),
                candidate_cells=tuple(sorted(self.reservation_cells)),
                via_count=0, obstacle_crossings=0,
                reservation_crossings=0, edge_count=0)
        terminals = self._terminals(net, records)
        wire = {}
        vias = {}
        corridor = set()
        candidates = set()
        via_count = 0
        obstacles = 0
        reservation_crossings = 0
        edges = self._mst_edges(terminals)
        for left, right in edges:
            chosen, possible = self._edge_candidates(
                net, policy, left, right, owner_lookup)
            (_score, edge_obstacles, edge_reservations, edge_vias, layer,
             path, via_left, via_right) = chosen
            _add_sparse(wire, self._spread_rect(layer, left, right))
            for cell in via_left + via_right:
                vias[cell] = vias.get(cell, 0) + DEMAND_SCALE
            corridor.update(path)
            candidates.update(possible)
            via_count += edge_vias
            obstacles += edge_obstacles
            reservation_crossings += edge_reservations
        return NetForecast(
            net=net,
            wire_demand=tuple(sorted(wire.items())),
            via_demand=tuple(sorted(vias.items())),
            corridor_cells=tuple(sorted(corridor)),
            candidate_cells=tuple(sorted(candidates)),
            via_count=int(via_count),
            obstacle_crossings=int(obstacles),
            reservation_crossings=int(reservation_crossings),
            edge_count=len(edges))

    def _build_forecasts(self, records_by_net, owner_lookup):
        return {
            net: self._forecast(net, records_by_net.get(net, ()), owner_lookup)
            for net in sorted(self.policies)
        }

    @staticmethod
    def _dependency_index(forecasts):
        rows = collections.defaultdict(set)
        for net, forecast in forecasts.items():
            for cell in forecast.candidate_cells:
                rows[cell].add(net)
        return {cell: tuple(sorted(nets)) for cell, nets in rows.items()}

    def _aggregate(self, forecasts):
        shape = (self.layer_count, self.height, self.width)
        wire = np.zeros(shape, dtype=np.int64)
        via = np.zeros(shape, dtype=np.int64)
        critical = np.zeros(shape, dtype=np.int32)
        residual = np.zeros(shape, dtype=np.int32)
        reservation = np.zeros(shape, dtype=np.int64)
        for cell in self.reservation_cells:
            reservation[cell] = self.capacity_units
        for net, forecast in forecasts.items():
            for cell, value in forecast.wire_demand:
                wire[cell] += int(value)
            for cell, value in forecast.via_demand:
                via[cell] += int(value)
            target = critical if self.policies[net].critical else residual
            for cell in forecast.corridor_cells:
                target[cell] += 1
        for field in (wire, via, critical, residual, reservation):
            field.flags.writeable = False
        return {"wire": wire, "via": via,
                "critical": critical, "residual": residual,
                "reservation": reservation}

    def _summarize(self, forecasts, arrays, *, records=(), pad_cells=(),
                   changed_cells=0, affected_nets=(), mode="baseline"):
        demand = arrays["wire"] + arrays["via"] + arrays["reservation"]
        overflow = np.maximum(demand - self.capacity_units, 0)
        conflicts = arrays["critical"].astype(np.int64) * arrays["residual"]
        layers = []
        for index, name in enumerate(self.layer_names):
            layers.append({
                "name": name,
                "capacity_tracks": self.capacity_tracks,
                "wire_demand_units": int(arrays["wire"][index].sum()),
                "via_demand_units": int(arrays["via"][index].sum()),
                "reservation_demand_units": int(
                    arrays["reservation"][index].sum()),
                "overflow_units": int(overflow[index].sum()),
                "peak_demand_units": int(demand[index].max()),
                "critical_reserved_cells": int(np.count_nonzero(
                    arrays["critical"][index])),
            })
        pressure = collections.Counter()
        critical_nets = {net for net, policy in self.policies.items()
                         if policy.critical}
        for index, row in enumerate(records):
            ref = str(row["ref"])
            net = str(row["net"])
            for cell in pad_cells[index]:
                pressure[ref] += int(overflow[cell])
                if net not in critical_nets and arrays["critical"][cell] > 0:
                    pressure[ref] += (self.capacity_units
                                      * int(arrays["critical"][cell]))
                if self._foreign_reservation(net, cell):
                    pressure[ref] += self.capacity_units
        pressure_refs = [
            {"ref": ref, "pressure_units": int(value)}
            for ref, value in sorted(
                pressure.items(), key=lambda row: (-row[1], row[0]))
            if value > 0][:24]
        return {
            "schema": self.SCHEMA,
            "context_fingerprint": getattr(self, "fingerprint", None),
            "grid_mm": self.grid_mm,
            "demand_scale": DEMAND_SCALE,
            "capacity_tracks_per_cell": self.capacity_tracks,
            "wire_demand_units": int(arrays["wire"].sum()),
            "via_demand_units": int(arrays["via"].sum()),
            "reservation_demand_units": int(arrays["reservation"].sum()),
            "overflow_units": int(overflow.sum()),
            "critical_corridor_conflicts": int(conflicts.sum()),
            "critical_reserved_cells": int(np.count_nonzero(
                arrays["critical"])),
            "corridor_obstacle_crossings": sum(
                forecast.obstacle_crossings for forecast in forecasts.values()),
            "reservation_crossings": sum(
                forecast.reservation_crossings
                for forecast in forecasts.values()),
            "reservation_rect_count": len(self.reservations),
            "reservation_cell_count": len(self.reservation_cells),
            "reservation_owned_nets": sorted(self.reservation_owned_nets),
            "reservation_refused_nets": sorted(
                str(net) for net, row in self.reservation_report.items()
                if isinstance(row, dict) and not row.get("reserved")
                and not str(row.get("reason", "")).startswith(
                    "single terminal cluster")),
            "expected_via_count": sum(
                forecast.via_count for forecast in forecasts.values()),
            "pressure_refs": pressure_refs,
            "edge_count": sum(
                forecast.edge_count for forecast in forecasts.values()),
            "layers": layers,
            "incremental": {
                "mode": mode,
                "affected_nets": list(affected_nets),
                "affected_net_count": len(affected_nets),
                "changed_cell_count": int(changed_cells),
                "total_net_count": len(forecasts),
            },
        }

    def _owner_delta(self, view):
        delta = collections.defaultdict(collections.Counter)
        changed_cells = set()
        for index in view.dirty_pad_indices:
            net = str(self.base_records[index]["net"])
            old_cells = self.base_pad_cells[index]
            new_cells = self._pad_cells(view.pad_records[index])
            if old_cells == new_cells:
                continue
            for cell in old_cells:
                delta[cell][net] -= 1
                changed_cells.add(cell)
            for cell in new_cells:
                delta[cell][net] += 1
                changed_cells.add(cell)
        return {cell: dict(counts) for cell, counts in delta.items()}, changed_cells

    def _overlay_owners(self, owner_delta):
        def lookup(cell):
            cell = _cell_key(cell)
            base = self.base_owner_counts.get(cell, {})
            changed = owner_delta.get(cell)
            if not changed:
                return base
            result = dict(base)
            for net, amount in changed.items():
                value = int(result.get(net, 0)) + int(amount)
                if value > 0:
                    result[net] = value
                else:
                    result.pop(net, None)
            return result
        return lookup

    def _delta_arrays(self, forecasts, affected):
        deltas = {name: {} for name in (
            "wire", "via", "critical", "residual")}
        for net in affected:
            old = self.base_forecasts[net]
            new = forecasts[net]
            _add_sparse(deltas["wire"], old.wire_dict(), -1)
            _add_sparse(deltas["wire"], new.wire_dict(), 1)
            _add_sparse(deltas["via"], old.via_dict(), -1)
            _add_sparse(deltas["via"], new.via_dict(), 1)
            field = "critical" if self.policies[net].critical else "residual"
            _add_sparse(deltas[field], {cell: 1 for cell in old.corridor_cells}, -1)
            _add_sparse(deltas[field], {cell: 1 for cell in new.corridor_cells}, 1)
        arrays = {}
        for name, base in self._base_arrays.items():
            updated = np.array(base, copy=True)
            for cell, amount in deltas.get(name, {}).items():
                updated[cell] += int(amount)
                if updated[cell] < 0:
                    raise AssertionError("negative %s forecast cell" % name)
            updated.flags.writeable = False
            arrays[name] = updated
        touched = set()
        for delta in deltas.values():
            touched.update(delta)
        return arrays, touched

    def evaluate(self, placements=None):
        view = self.database.view(placements)
        if not view.dirty_pad_indices:
            result = dict(self._base_summary)
            result["context_fingerprint"] = self.fingerprint
            result["incremental"] = {
                "mode": "incremental", "affected_nets": [],
                "affected_net_count": 0, "changed_cell_count": 0,
                "total_net_count": len(self.base_forecasts)}
            return result
        owner_delta, changed_owner_cells = self._owner_delta(view)
        affected = {
            str(self.base_records[index]["net"])
            for index in view.dirty_pad_indices
            if str(self.base_records[index]["net"]) in self.policies}
        for cell in changed_owner_cells:
            affected.update(self.dependent_nets_by_cell.get(cell, ()))
        affected = tuple(sorted(affected))
        owner_lookup = self._overlay_owners(owner_delta)
        records_by_net = self._records_by_net(view.pad_records)
        forecasts = dict(self.base_forecasts)
        for net in affected:
            forecasts[net] = self._forecast(
                net, records_by_net.get(net, ()), owner_lookup)
        arrays, touched = self._delta_arrays(forecasts, affected)
        records = tuple(view.pad_records)
        pad_cells = tuple(self._pad_cells(row) for row in records)
        result = self._summarize(
            forecasts, arrays, records=records, pad_cells=pad_cells,
            changed_cells=len(touched),
            affected_nets=affected, mode="incremental")
        result["context_fingerprint"] = self.fingerprint
        return result

    def recompute(self, placements=None):
        """Full oracle for tests and diagnostics; production proposals use evaluate."""
        view = self.database.view(placements)
        records = tuple(view.pad_records)
        pad_cells = tuple(self._pad_cells(row) for row in records)
        owners = self._owner_counts(records, pad_cells)
        lookup = lambda cell: owners.get(_cell_key(cell), {})
        forecasts = self._build_forecasts(self._records_by_net(records), lookup)
        arrays = self._aggregate(forecasts)
        result = self._summarize(
            forecasts, arrays, records=records, pad_cells=pad_cells,
            changed_cells=int(np.prod(arrays["wire"].shape)),
            affected_nets=tuple(sorted(forecasts)), mode="full_recompute")
        result["context_fingerprint"] = self.fingerprint
        return result


def prepare(database, conns, stackup, *, critical_nets=(), reservations=(),
            reservation_report=None, grid_mm=1.0, pitch_mm=0.45):
    return FutureCongestionContext(
        database, tuple(conns), stackup,
        critical_nets=tuple(critical_nets), reservations=tuple(reservations),
        reservation_report=reservation_report, grid_mm=grid_mm,
        pitch_mm=pitch_mm)
