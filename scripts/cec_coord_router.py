#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_coord_router -- PRODUCTION co-coordinating GLOBAL router for the CEC
#                       automated PCB routing pipeline.
# ============================================================================
# Owner ask (2026-07-08 evening, ratified "Implement it up... get it in"): every routing
# path should be aware of every OTHER net's attempt while it is being planned -- literal
# NEGOTIATED CONGESTION, the PathFinder algorithm (Ebeling/McMurchie, VPR/FPGA lineage):
# all nets' wavefront distance fields relax SIMULTANEOUSLY as one (N, L, H, W) tensor,
# present-sharing (pres_w) + persistent history (hist_w) make every net's cost field
# carry the marks of every other net's prior attempts, and the loop rips up + reroutes
# only the nets still crossing overused cells until the board's congestion resolves to
# zero (or is honestly reported if it structurally cannot).
#
# BASE: scripts/cec_coord_router_proto.py -- a WORKING prototype, measured on the real
# board build/fresh/atx-24pin-rev3/20260708T2055-periph-left-dataflow-s1.kicad_pcb (180
# two-pin connections, 118x141 grid @ 0.5mm): GPU cupy 12.8-15.3s vs CPU numpy 110-124s
# (8.1-8.7x), byte-identical results -- the wavefront-relax tensor op is a legitimate GPU
# win. But it did NOT converge in 20 iterations (residual_overuse ~1693) because its
# capacity model was naive (1 track/cell, PAD/TERMINAL cells counted as overuse same as
# through-traffic) and its "GPU" path recovery copied the WHOLE (N,H,W) distance tensor
# to the host every iteration and then walked it in a sequential Python loop -- the actual
# GPU-resident compute was a sliver of the wall time.
#
# THIS MODULE fixes all three, plus adds a second copper layer:
#
#   1. CAPACITY MODEL (_capacity): cap = max(1, floor(grid_mm / pitch_mm)) tracks/cell/layer
#      (default pitch_mm=0.45, so at the pipeline's standard 0.5mm grid cap=1 -- same raw
#      number as the prototype, but now interpreted correctly: see (2) below for why 1 is
#      no longer as tight as it sounds).
#   2. TERMINAL EXEMPTION (standard global-routing practice): a net's own path ENDPOINTS
#      (its source and destination grid cell -- the pad it terminates at) never count
#      toward THAT net's overuse contribution. A densely-pinned IC's pads landing in
#      neighbouring/shared coarse cells no longer manufacture phantom congestion -- only
#      genuine THROUGH-TRAFFIC over a cell counts against its capacity. This is the single
#      biggest lever versus the prototype's 1693 residual.
#   3. FOREIGN FIXED COPPER (not infinity): cells under an EXCLUDED net's pad (GND, which
#      rides the plane and is never routed as a 2-pin corridor) get an elevated additive
#      cost (foreign_cost, default 5.0) so nets avoid threading through a GND pad's silicon
#      real estate when a cheaper detour exists, but are never hard-blocked -- there is
#      always a legal (if pricier) path, matching a real antipad/keepout's soft avoidance.
#   4. TWO LAYERS (L=2, F.Cu=0 / B.Cu=1): the dist tensor gains a layer axis (N, L, H, W);
#      a VIA move (same cell, opposite layer, cost=via_cost) is a same-order relax edge
#      alongside the four planar neighbours. Each layer gets a mild PREFERRED-DIRECTION
#      bias (F.Cu prefers horizontal, B.Cu prefers vertical, 0.8x/1.2x multipliers by
#      default) -- the classic "Manhattan layer assignment" convergence aid: it keeps
#      same-direction traffic off each other's backs instead of two full layers of
#      criss-crossing nets fighting over every cell.
#   5. PATHFINDER DISCIPLINE done properly: pres_w RAMPS with iteration
#      (pres_w * (1 + it*pres_growth), default pres_growth=0.35, hist_w=1.5 -- empirically
#      tuned on the real eps-8pin board, see the HERDING FIX + BEST-SO-FAR notes on
#      route_negotiated) so early rounds are gentle (let legitimate sharing settle) and late
#      rounds punish persistent conflict hard; after iteration 0, ONLY nets whose CURRENT path
#      crosses a cell that is still over capacity get ripped up and rerouted -- a net that has
#      settled keeps its path and keeps contributing usage/history untouched (this is also
#      most of the wall-clock win: N shrinks fast after the first round). CHUNKED negotiation
#      within each iteration (not one global simultaneous batch) breaks LOCKSTEP HERDING where
#      many nets that don't see each other pick the same "currently cheap" cell together; the
#      final result tracks the BEST residual seen across all iterations, not just the last one,
#      since real dense boards oscillate around a floor rather than monotonically improving
#      (measured: 150 iterations landed WORSE than 80 on the same run).
#   6. GPU-RESIDENT PATH RECOVERY (_batched_descent): all active nets descend their own
#      distance field SIMULTANEOUSLY as vectorized gather/argmin over 5 candidate moves
#      (4 planar neighbours + 1 via) per step, entirely on-device; the only host<->device
#      traffic is the FINAL small (Na, steps, 3) path-index array, once, at the very end of
#      the descent loop -- not a whole-tensor .get() every relax sweep like the prototype.
#
# Still a GLOBAL router on a coarse grid: this produces per-net CORRIDORS + a congestion
# map, feeding FR's bake_hints/keepouts. It does NOT lay detailed copper -- FR/pcbnew still
# do that. Read-only on boards: never mutates or saves a .kicad_pcb.
#
# HONEST RESULT (orchestrator-reviewed 2026-07-08): on the two real fresh-wave boards this was
# measured against, the raw residual_overuse does NOT reach 0 even after the herding fix + best-
# so-far tracking -- it floors around ~130 (eps-8pin, 136 nets) / ~500 (atx-24pin-rev3, 181 nets).
# This is NOT silently loosened; it is a genuine, diagnosed property of coarse global routing at
# pitch_mm=0.45/grid_mm=0.5 on real dense boards (diffuse congestion, mostly at multi-pin net
# fan-out points the MST decomposition creates). Two metrics are reported so a caller can tell
# genuine corridor conflict from pin-escape noise: residual_overuse (raw) and
# residual_overuse_escaped (cells within escape_radius of ANY terminal exempted -- see
# route_negotiated's ESCAPE-RADIUS METRIC docstring). Do not chase raw-residual-0 by loosening cap
# or pitch_mm -- see build/teeth_coord_router.py's CONVERGENCE section for the full reasoning.
#
# CLI: python3 scripts/cec_coord_router.py <board> [--cpu] [--grid-mm 0.5] [--iters 40]
import math
import os
import sys
import time

HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# -- fail-safe backend import: numpy is required, cupy is optional (GPU) -------------------
try:
    import numpy as _np
except ImportError:  # pragma: no cover -- numpy is a hard dependency of this module
    _np = None

try:
    import cupy as _cp
except ImportError:
    _cp = None

F_CU, B_CU = 0, 1
LAYER_NAMES = {F_CU: "F.Cu", B_CU: "B.Cu"}


# ============================================================================
# Problem construction (pcbnew, read-only)
# ============================================================================
def build_problem(board_path, grid_mm=0.5, excluded_nets=("GND",),
                  *, detailed=False):
    """KiCad .kicad_pcb -> (conns, H, W, foreign_cells).

    conns: list of (net_name, (l_src, y_src, x_src), (l_dst, y_dst, x_dst)) -- multi-pin
           nets are MST-decomposed to two-pin connections (same as the prototype).
    H, W:  grid dimensions in cells at grid_mm resolution, from the board edge bbox.
    foreign_cells: set of (layer, y, x) occupied by a pad of an EXCLUDED net (GND) --
           fixed copper that costs more to route near/through but is not a hard block.

    A pad's layer is F_CU unless it sits ONLY on B.Cu (flipped part / bottom silk logo
    footprints do not have copper pads so never enter this set). THT pads that are on
    both copper layers are recorded on F_CU (their barrel is reachable from either side;
    F_CU is the routing-plane convention this pipeline already uses).
    """
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    if detailed:
        import cec_fab_profile
        layer_names = tuple(cec_fab_profile.routing_layers(
            b, hint=board_path, include_power=True))
        if not layer_names:
            raise ValueError("board has no legal routing layers")
        layer_ids = tuple(b.GetLayerID(name) for name in layer_names)
        profile_name = cec_fab_profile.active_profile_name(b, hint=board_path)
        profile = cec_fab_profile.get_profile(profile_name) if profile_name else None
        role_by_name = (dict(zip(cec_fab_profile.COPPER_LAYERS,
                                 profile["roles"])) if profile else {})
    else:
        # Frozen compatibility mode for synthetic callers written around the
        # original two-layer prototype. Production board routing opts into the
        # detailed stack and receives every declared non-ground route layer.
        layer_names = ("F.Cu", "B.Cu")
        layer_ids = (pcbnew.F_Cu, pcbnew.B_Cu)
        profile_name = None
        role_by_name = {"F.Cu": "SIG", "B.Cu": "SIG"}
    layer_index = {int(layer_id): index
                   for index, layer_id in enumerate(layer_ids)}
    bb = b.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetLeft() / 1e6, bb.GetTop() / 1e6
    W = int(bb.GetWidth() / 1e6 / grid_mm) + 1
    H = int(bb.GetHeight() / 1e6 / grid_mm) + 1

    def _cell(p):
        gx = int((p.GetPosition().x / 1e6 - x0) / grid_mm)
        gy = int((p.GetPosition().y / 1e6 - y0) / grid_mm)
        return min(H - 1, max(0, gy)), min(W - 1, max(0, gx))

    def _layers(p):
        out = []
        try:
            for layer_id, index in layer_index.items():
                if p.IsOnLayer(layer_id):
                    out.append(index)
        except Exception:
            pass
        return tuple(out or (0,))

    pads_by_net = {}
    netclasses = {}
    foreign_cells = set()
    # Every real foreign copper land is a hard obstacle for a future route,
    # not merely a congestion preference.  Keep cell ownership by net so a
    # connection may enter its own pads/tracks while being forbidden from
    # crossing another net's copper.  This is deliberately built from the
    # physical board artifact; it therefore also describes partially-routed
    # candidates instead of hallucinating capacity through existing copper.
    from collections import defaultdict
    cell_owners = defaultdict(set)

    def _item_cells(item, layers, *, centre=None):
        cells = set()
        try:
            box = item.GetBoundingBox()
            margin = 0.20 + 0.5 * float(grid_mm)
            bx0 = box.GetLeft() / 1e6 - margin
            by0 = box.GetTop() / 1e6 - margin
            bx1 = box.GetRight() / 1e6 + margin
            by1 = box.GetBottom() / 1e6 + margin
            gx0 = max(0, int(math.floor((bx0 - x0) / grid_mm)))
            gy0 = max(0, int(math.floor((by0 - y0) / grid_mm)))
            gx1 = min(W - 1, int(math.ceil((bx1 - x0) / grid_mm)))
            gy1 = min(H - 1, int(math.ceil((by1 - y0) / grid_mm)))
            tolerance = int(round(margin * 1e6))
            for gy in range(gy0, gy1 + 1):
                for gx in range(gx0, gx1 + 1):
                    point = pcbnew.VECTOR2I(
                        int(round((x0 + (gx + 0.5) * grid_mm) * 1e6)),
                        int(round((y0 + (gy + 0.5) * grid_mm) * 1e6)))
                    try:
                        hit = bool(item.HitTest(point, tolerance))
                    except TypeError:
                        hit = bool(item.HitTest(point))
                    if hit:
                        cells.update((layer, gy, gx) for layer in layers)
        except Exception:                                # noqa: BLE001
            pass
        if centre is not None:
            gy, gx = _cell(centre)
            cells.update((layer, gy, gx) for layer in layers)
        return cells

    for fp in b.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if not n:
                continue
            gy, gx = _cell(p)
            layers = _layers(p)
            for cell in _item_cells(p, layers, centre=p):
                cell_owners[cell].add(n)
            if n in excluded_nets:
                # A through-hole land/barrel occupies every routing layer in
                # its padstack. Record all of them; treating it as F.Cu-only
                # manufactures both false capacity and false layer-jump work.
                for layer in layers:
                    foreign_cells.add((layer, gy, gx))
                continue
            pads_by_net.setdefault(n, set()).add((layers[0], gy, gx))
            try:
                netclasses[n] = p.GetNet().GetNetClassName()
            except Exception:                              # noqa: BLE001
                netclasses.setdefault(n, "")

    # Existing routed copper consumes future capacity too.  Vias occupy every
    # routing layer in their span; tracks occupy their exact layer.  The
    # HitTest raster avoids the old giant-bounding-box artifact on diagonals.
    for track in b.GetTracks():
        net = track.GetNetname()
        if not net:
            continue
        layers = _layers(track) if track.GetClass() == "PCB_VIA" else \
            (layer_index.get(int(track.GetLayer())),)
        layers = tuple(layer for layer in layers if layer is not None)
        centre = track if track.GetClass() == "PCB_VIA" else None
        for cell in _item_cells(track, layers, centre=centre):
            cell_owners[cell].add(net)

    # 2-pin decomposition: MST edges per multi-pin net (distance ignores layer -- topology
    # only; the relax/via cost handles the actual layer-crossing cost during routing).
    conns = []
    conn_classes = []
    for n, pts in pads_by_net.items():
        pts = list(pts)
        if len(pts) < 2:
            continue
        used = {0}
        d = [math.hypot(pts[0][1] - p[1], pts[0][2] - p[2]) for p in pts]
        par = [0] * len(pts)
        while len(used) < len(pts):
            best, bi = min((dd, i) for i, dd in enumerate(d) if i not in used)
            used.add(bi)
            conns.append((n, pts[par[bi]], pts[bi]))
            conn_classes.append(netclasses.get(n, ""))
            for i, p in enumerate(pts):
                nd = math.hypot(pts[bi][1] - p[1], pts[bi][2] - p[2])
                if nd < d[i]:
                    d[i], par[i] = nd, bi
    if not detailed:
        return conns, H, W, foreign_cells

    physical_roles = []
    try:
        import cec_fab_profile
        for name in cec_fab_profile.COPPER_LAYERS:
            physical_roles.append(role_by_name.get(name, "SIG"))
    except Exception:                                  # noqa: BLE001
        physical_roles = []

    def _ground_referenced(layer_name):
        """Whether this signal layer borders a declared uninterrupted GND."""
        try:
            import cec_fab_profile
            physical = list(cec_fab_profile.COPPER_LAYERS)
            at = physical.index(layer_name)
            return any(0 <= other < len(physical_roles)
                       and physical_roles[other] == "GND"
                       for other in (at - 1, at + 1))
        except Exception:                              # noqa: BLE001
            return layer_name in ("F.Cu", "B.Cu")

    allowed_layers = []
    net_kinds = []
    for (net, src, dst), netclass in zip(conns, conn_classes):
        upper = net.upper()
        klass = str(netclass or "").upper()
        high_speed = (klass in {"USB", "DIFF", "DIFFPAIR", "HIGH_SPEED"}
                      or "USB_D_" in upper or "SGMII" in upper
                      or "PCIE" in upper)
        power = ("POWER" in klass or upper.startswith("+")
                 or any(token in upper for token in (
                     "VBUS", "VCC", "VDD", "_5V", "_3V3", "_12V")))
        if high_speed:
            kind = "high_speed"
            allowed = [i for i, name in enumerate(layer_names)
                       if "SIG" in role_by_name.get(name, "SIG")
                       and _ground_referenced(name)]
        elif power:
            kind = "power"
            allowed = list(range(len(layer_names)))
        else:
            kind = "signal"
            allowed = [i for i, name in enumerate(layer_names)
                       if "SIG" in role_by_name.get(name, "SIG")]
        # A real terminal layer is always reachable. This matters for an
        # intentionally bottom-mounted component even if a custom stack role
        # is stricter than the library default.
        allowed = sorted(set(allowed) | {src[0], dst[0]})
        allowed_layers.append(tuple(i in allowed for i in range(len(layer_names))))
        net_kinds.append(kind)

    blocked_cells_by_conn = []
    all_blocked = set(cell_owners)
    for net, _src, _dst in conns:
        blocked_cells_by_conn.append({
            cell for cell, owners in cell_owners.items()
            if any(owner != net for owner in owners)})
    blocked_per_layer = [0] * len(layer_names)
    for layer, _y, _x in all_blocked:
        if 0 <= layer < len(blocked_per_layer):
            blocked_per_layer[layer] += 1
    meta = {
        "layer_names": layer_names,
        "layer_ids": layer_ids,
        "layer_roles": tuple(role_by_name.get(name, "SIG")
                             for name in layer_names),
        "ground_referenced": tuple(_ground_referenced(name)
                                   for name in layer_names),
        "allowed_layers_by_conn": tuple(allowed_layers),
        "net_kinds": tuple(net_kinds),
        "netclasses": tuple(conn_classes),
        "profile": profile_name,
        "grid_mm": float(grid_mm),
        "grid_origin_mm": (float(x0), float(y0)),
        "blocked_cell_count": len(all_blocked),
        "blocked_cells_per_layer": tuple(blocked_per_layer),
        # Internal route inputs are removed by public consumers before the
        # JSON-safe stackup metadata is returned.
        "_blocked_cells_by_conn": tuple(blocked_cells_by_conn),
    }
    return conns, H, W, foreign_cells, meta


# ============================================================================
# Capacity model
# ============================================================================
def _capacity(grid_mm, pitch_mm=0.45):
    """floor(grid_mm / pitch_mm) trace pitches per cell per layer, floored at 1."""
    return max(1, int(math.floor(grid_mm / pitch_mm + 1e-9)))


def summarize_congestion(usage, cap, *, negotiated_usage=None,
                         layer_names=(), top_k=32):
    """Return a compact, JSON-safe congestion map summary.

    The full usage tensor remains available to in-process consumers. Reports
    and the dashboard receive per-layer capacity statistics plus the hottest
    exact grid cells, which is enough to trace a plateau without serializing a
    multi-megabyte dense tensor for every candidate.
    """
    import numpy as np
    raw = np.asarray(usage)
    effective = (raw if negotiated_usage is None
                 else np.asarray(negotiated_usage))
    over = np.maximum(0.0, effective - float(cap))
    raw_over = np.maximum(0.0, raw - float(cap))
    names = tuple(layer_names or ("L%d" % i for i in range(raw.shape[0])))
    layers = []
    for layer in range(raw.shape[0]):
        occupied = raw[layer] > 0
        congested = over[layer] > 0
        layers.append({
            "index": layer,
            "name": names[layer] if layer < len(names) else "L%d" % layer,
            "occupied_cells": int(occupied.sum()),
            "overused_cells": int(congested.sum()),
            "residual_overuse": float(over[layer].sum()),
            "raw_overused_cells": int((raw_over[layer] > 0).sum()),
            "raw_residual_overuse": float(raw_over[layer].sum()),
            "peak_usage": float(raw[layer].max()) if raw[layer].size else 0.0,
            "capacity": int(cap),
        })
    flat = over.reshape(-1)
    count = min(max(0, int(top_k)), int((flat > 0).sum()))
    hotspots = []
    if count:
        candidates = np.argpartition(flat, -count)[-count:]
        candidates = sorted(candidates,
                            key=lambda index: (-flat[index], int(index)))
        for index in candidates:
            layer, y, x = np.unravel_index(int(index), over.shape)
            hotspots.append({
                "layer": names[layer] if layer < len(names) else "L%d" % layer,
                "layer_index": int(layer), "x": int(x), "y": int(y),
                "usage": float(raw[layer, y, x]),
                "overuse": float(over[layer, y, x]),
            })
    return {"capacity": int(cap), "layers": layers, "hotspots": hotspots}


def blockage_witnesses(conns, paths, congestion, *, cap,
                       blocked_cells_by_conn=(), allowed_layers=None,
                       connection_priorities=None,
                       protected_priority_max=None, height=None, width=None,
                       limit=24):
    """Explain *who* owns each routed bottleneck and terminal refusal.

    A heatmap cell without connection ownership cannot steer placement: it
    says where capacity was exceeded but not which movable endpoint could
    vacate the channel.  This compact projection joins the best negotiated
    paths back to their connection indices and priority tiers.  Unroutable
    connections additionally report the legal one-cell terminal shell, so a
    caller can distinguish a boxed-in launch from a distant corridor failure.

    The result is diagnostic evidence only.  It never waives the complete
    negotiated route or KiCad checks that remain authoritative for adoption.
    """
    import numpy as np

    paths = tuple(paths or ())
    n_conns = len(conns)
    priorities = (np.zeros(n_conns, dtype=np.int32)
                  if connection_priorities is None
                  else np.asarray(connection_priorities, dtype=np.int32))
    if priorities.shape != (n_conns,):
        raise ValueError("connection_priorities shape %r != (%d,)" %
                         (priorities.shape, n_conns))
    if allowed_layers is None:
        layer_count = max((point[0] for _net, src, dst in conns
                           for point in (src, dst)), default=0) + 1
        allowed = np.ones((n_conns, layer_count), dtype=bool)
    else:
        allowed = np.asarray(allowed_layers, dtype=bool)
        if allowed.ndim != 2 or allowed.shape[0] != n_conns:
            raise ValueError("allowed_layers shape %r incompatible with %d connections" %
                             (allowed.shape, n_conns))
        layer_count = int(allowed.shape[1])
    blocked = tuple(blocked_cells_by_conn or (((),) * n_conns))
    if len(blocked) != n_conns:
        raise ValueError("blocked_cells_by_conn length %d != %d" %
                         (len(blocked), n_conns))

    hotspot_rows = list((congestion or {}).get("hotspots") or ())
    hotspot_keys = {
        (int(row["layer_index"]), int(row["y"]), int(row["x"]))
        for row in hotspot_rows}
    owners = {cell: [] for cell in hotspot_keys}
    for index, path in enumerate(paths):
        if not path:
            continue
        # Match _accumulate(): a connection's own two terminal cells are not
        # overuse-eligible and therefore cannot be named as congestion owners.
        for cell in set(tuple(point) for point in path[1:-1]):
            if cell in owners:
                owners[cell].append(index)

    witnesses = []
    for row in hotspot_rows:
        cell = (int(row["layer_index"]), int(row["y"]), int(row["x"]))
        indices = sorted(owners.get(cell, ()), key=lambda index: (
            int(priorities[index]), str(conns[index][0]), int(index)))
        connections = []
        horizontal = vertical = 0
        for index in indices:
            net, src, dst = conns[index]
            horizontal += abs(int(dst[2]) - int(src[2]))
            vertical += abs(int(dst[1]) - int(src[1]))
            priority = int(priorities[index])
            connections.append({
                "index": int(index), "net": str(net),
                "priority": priority,
                "protected": bool(protected_priority_max is not None
                                  and priority <= int(protected_priority_max)),
                "src": tuple(int(value) for value in src),
                "dst": tuple(int(value) for value in dst),
            })
        # Move residual endpoints perpendicular to the dominant traffic flow;
        # this opens a channel instead of merely sliding the same crossing
        # along its axis.  A tie keeps all cardinal choices deterministic.
        if horizontal > vertical:
            escape = ("N", "S")
        elif vertical > horizontal:
            escape = ("E", "W")
        else:
            escape = ("N", "S", "E", "W")
        witnesses.append({
            "kind": "over_capacity",
            "layer": row.get("layer"),
            "layer_index": cell[0], "x": cell[2], "y": cell[1],
            "usage": float(row.get("usage", 0.0) or 0.0),
            "capacity": int(cap),
            "overuse": float(row.get("overuse", 0.0) or 0.0),
            "connection_count": len(connections),
            "connections": connections,
            "escape_directions": escape,
        })

    if height is None:
        height = max((int(point[1]) for _net, src, dst in conns
                      for point in (src, dst)), default=0) + 1
    if width is None:
        width = max((int(point[2]) for _net, src, dst in conns
                     for point in (src, dst)), default=0) + 1
    for index, path in enumerate(paths):
        if path is not None:
            continue
        net, src, dst = conns[index]
        blocked_set = {tuple(int(value) for value in cell)
                       for cell in blocked[index]}
        terminals = []
        for name, terminal in (("src", src), ("dst", dst)):
            _terminal_layer, ty, tx = (int(value) for value in terminal)
            shell = set()
            for layer in range(layer_count):
                if not allowed[index, layer]:
                    continue
                for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    y, x = ty + dy, tx + dx
                    if 0 <= y < int(height) and 0 <= x < int(width):
                        shell.add((layer, y, x))
            blocked_shell = sorted(shell & blocked_set)
            terminals.append({
                "terminal": name,
                "cell": tuple(int(value) for value in terminal),
                "legal_neighbor_count": len(shell),
                "blocked_neighbor_count": len(blocked_shell),
                "open_neighbor_count": len(shell - blocked_set),
                "blocked_neighbors": blocked_shell[:16],
            })
        priority = int(priorities[index])
        boxed_launch = any(
            terminal["legal_neighbor_count"] > 0
            and terminal["open_neighbor_count"] == 0
            for terminal in terminals)
        witnesses.append({
            "kind": "unroutable",
            "failure_scope": ("terminal_boxed" if boxed_launch
                              else "corridor_blocked"),
            "connection_index": int(index), "net": str(net),
            "priority": priority,
            "protected": bool(protected_priority_max is not None
                              and priority <= int(protected_priority_max)),
            "src": tuple(int(value) for value in src),
            "dst": tuple(int(value) for value in dst),
            "terminals": terminals,
        })

    witnesses.sort(key=lambda row: (
        0 if row["kind"] == "unroutable" else 1,
        0 if row.get("protected") else 1,
        -float(row.get("overuse", 0.0) or 0.0),
        int(row.get("layer_index", -1)), int(row.get("y", -1)),
        int(row.get("x", -1)), str(row.get("net", ""))))
    return witnesses[:max(0, int(limit))]


# ============================================================================
# Core negotiated-congestion router (xp-polymorphic: numpy or cupy)
# ============================================================================
def route_negotiated(conns, H, W, xp, *, L=2, iters=40, hist_w=1.5, pres_w=2.0,
                      grid_mm=0.5, pitch_mm=0.45, cap=None, via_cost=3.0,
                      bias=True, bias_h=(0.8, 1.2), bias_v=(1.2, 0.8),
                      foreign_cells=None, foreign_cost=5.0, max_sweeps=None,
                      max_steps=None, pres_growth=0.35, chunk_frac=0.125, chunk_min=6,
                      escape_radius=2, cost_mode="float", cost_scale=100,
                      allowed_layers=None, blocked_cells_by_conn=None,
                      connection_priorities=None, protected_priority_max=None,
                      telemetry=None, plateau_patience=8,
                      plateau_min_delta=1.0, early_stop_plateau=False):
    """PathFinder negotiated-congestion global route. Returns
    (paths, usage_raw_host, residual_overuse, iters_used, residual_overuse_escaped) where
    paths is a list (len N, index-aligned to conns) of lists of (layer, y, x) grid cells from
    dst to src, and usage_raw_host is a host numpy (L, H, W) float array of raw per-cell
    copper presence (informative -- NOT the overuse-eligible tensor the gate itself uses).

    CAPACITY IS PER (layer, cell), NOT summed across layers: usage_cong and cap are compared
    elementwise on the full (L, H, W) tensor (`usage_cong - cap`), so a cell that is full on
    F.Cu but empty on B.Cu is NOT over capacity -- the L=2 layer split is a real 2x capacity
    lever, not a bookkeeping artifact that collapses back to 1 layer's worth.

    ESCAPE-RADIUS METRIC (orchestrator refinement, 2026-07-08): pin-escape regions (the cells
    immediately around ANY net's terminal, where multiple physically-close pads/vias must all
    funnel out) are classically the DETAILED router's problem, not the GLOBAL corridor
    negotiation's -- FR-hint compilation should not bake keepouts inside them anyway. This is
    a REPORTING-ONLY refinement (it does not change pres/history cost during negotiation, so
    it cannot mask a real corridor conflict): residual_overuse_escaped is the SAME best-tracked
    overuse tensor with cells within escape_radius (Chebyshev) of ANY net's src/dst zeroed out
    before summing. Comparing the two numbers tells you whether the honest raw residual is
    genuine corridor congestion (escaped number stays large too) or pin-escape noise (escaped
    number drops near/at zero while raw stays nonzero).

    HERDING FIX (measured 2026-07-08, eps-8pin 136-net board): a single GLOBAL batch that
    relaxes every active net against one frozen cost snapshot causes LOCKSTEP HERDING --
    dozens of nets that don't see each other all pick the same "currently cheapest" cell in
    the same round, get punished together next round, and cycle without ever differentiating
    (measured: residual oscillating 100-650 for 100 iterations, never trending to 0, active
    count stuck at 30-50 nets indefinitely). The fix is CHUNKING: split the active set into
    chunks of chunk_frac*len(active) (floor chunk_min), process chunks SEQUENTIALLY within one
    outer iteration, updating usage/cellcost between chunks so a later chunk in the SAME
    iteration already sees what an earlier chunk in that iteration claimed. Each chunk is
    still relaxed + descended as ONE vectorized GPU batch (chunk_min keeps chunks worth
    batching), so this stays "wavefront fields relax simultaneously" at the chunk grain, just
    not globally-simultaneous across all ~100+ still-active nets at once. Chunk order is
    reshuffled every iteration with an iteration-seeded RNG (deterministic + reproducible,
    not wall-clock) so the same net isn't always first/last.
    """
    import numpy as np  # host-side bookkeeping is always plain numpy (small data)
    N = len(conns)
    cap = _capacity(grid_mm, pitch_mm) if cap is None else cap
    max_sweeps = (H + W + 2 * L + 4) if max_sweeps is None else max_sweeps
    max_steps = (L * H * W) if max_steps is None else max_steps
    fixed_cost = str(cost_mode).lower() in ("fixed", "int", "integer")
    if not fixed_cost and str(cost_mode).lower() not in ("float", "float32"):
        raise ValueError("cost_mode must be float or fixed")
    cost_scale = max(1, int(cost_scale))
    cost_dtype = xp.int32 if fixed_cost else xp.float32
    INF = cost_dtype(1_000_000_000)

    srcs = np.zeros((N, 3), dtype=np.int32)
    dsts = np.zeros((N, 3), dtype=np.int32)
    for i, (_n, a, b) in enumerate(conns):
        srcs[i] = a
        dsts[i] = b
    if allowed_layers is None:
        allowed_layers = np.ones((N, L), dtype=bool)
    else:
        allowed_layers = np.asarray(allowed_layers, dtype=bool)
        if allowed_layers.shape != (N, L):
            raise ValueError("allowed_layers shape %r != (%d, %d)"
                             % (allowed_layers.shape, N, L))
    for i in range(N):
        if not allowed_layers[i, srcs[i, 0]] or not allowed_layers[i, dsts[i, 0]]:
            raise ValueError("terminal layer excluded for connection %d" % i)
    if blocked_cells_by_conn is None:
        blocked_cells_by_conn = ((),) * N
    if len(blocked_cells_by_conn) != N:
        raise ValueError("blocked_cells_by_conn length %d != %d"
                         % (len(blocked_cells_by_conn), N))
    priorities_enabled = connection_priorities is not None
    if connection_priorities is None:
        connection_priorities = np.zeros(N, dtype=np.int32)
    else:
        connection_priorities = np.asarray(
            connection_priorities, dtype=np.int32)
        if connection_priorities.shape != (N,):
            raise ValueError("connection_priorities shape %r != (%d,)"
                             % (connection_priorities.shape, N))
        if bool(np.any(connection_priorities < 0)):
            raise ValueError("connection priorities must be non-negative")
    protected = np.zeros(N, dtype=bool)
    if protected_priority_max is not None:
        if not priorities_enabled:
            raise ValueError("protected priority requires connection priorities")
        protected = connection_priorities <= int(protected_priority_max)

    if len(bias_h) != L or len(bias_v) != L:
        # Alternate preferred direction through the routing stack.  Explicit
        # vectors still win; this fallback makes L>2 a supported configuration
        # rather than silently broadcasting a two-layer policy.
        bias_h = tuple(0.8 if layer % 2 == 0 else 1.2 for layer in range(L))
        bias_v = tuple(1.2 if layer % 2 == 0 else 0.8 for layer in range(L))
    if not bias:
        bias_h = bias_v = (1.0,) * L
    if fixed_cost:
        bh = xp.asarray([int(round(v * cost_scale)) for v in bias_h],
                        dtype=cost_dtype)
        bv = xp.asarray([int(round(v * cost_scale)) for v in bias_v],
                        dtype=cost_dtype)
        via_cost_work = int(round(float(via_cost) * cost_scale))
    else:
        bh = xp.asarray(bias_h, dtype=cost_dtype)
        bv = xp.asarray(bias_v, dtype=cost_dtype)
        via_cost_work = float(via_cost)

    base_cost = xp.full((L, H, W), cost_scale if fixed_cost else 1.0,
                        dtype=cost_dtype)
    if foreign_cells:
        fc = np.zeros((L, H, W), dtype=(np.int32 if fixed_cost else np.float32))
        for (l, y, x) in foreign_cells:
            if 0 <= l < L and 0 <= y < H and 0 <= x < W:
                fc[l, y, x] += (int(round(foreign_cost * cost_scale))
                                if fixed_cost else foreign_cost)
        base_cost = base_cost + xp.asarray(fc)

    usage_raw = np.zeros((L, H, W), dtype=np.float32)   # all path presence (host, small ops)
    usage_cong = np.zeros((L, H, W), dtype=np.float32)  # overuse-eligible (terminal-exempt)
    history = np.zeros((L, H, W), dtype=np.float32)
    paths = [None] * N

    # escape_mask: cells within escape_radius (Chebyshev) of ANY net's src/dst terminal.
    # Built once from the problem's own terminals -- independent of iteration state.
    escape_mask = np.zeros((L, H, W), dtype=bool)
    if escape_radius and escape_radius > 0:
        r = escape_radius
        for i in range(N):
            for (l, y, x) in (tuple(srcs[i]), tuple(dsts[i])):
                y0, y1 = max(0, y - r), min(H, y + r + 1)
                x0, x1 = max(0, x - r), min(W, x + r + 1)
                escape_mask[l, y0:y1, x0:x1] = True

    if N == 0:
        return paths, usage_raw, 0.0, 0, 0.0

    # A zero-iteration budget is a legitimate bounded diagnostic request: no
    # connection has been attempted, so every path is explicitly unroutable.
    # Returning ``best_paths`` below used to return None because the best-so-
    # far loop never ran; route_problem then crashed while naming the result.
    # Preserve the normal index-aligned shape and enough telemetry for callers
    # to report a budget exhaustion rather than an infrastructure exception.
    if int(iters) <= 0:
        if telemetry is not None:
            telemetry.update({
                "schema": 1,
                "best_iteration": 0,
                "iterations_run": 0,
                "stall_age": 0,
                "plateau": False,
                "plateau_patience": max(1, int(plateau_patience)),
                "plateau_min_delta": float(plateau_min_delta),
                "early_stop_enabled": bool(early_stop_plateau),
                "early_stopped": False,
                "budget_exhausted_before_route": True,
                "trace": [],
                "priority_routing": {
                    "enabled": bool(priorities_enabled),
                    "protected_priority_max": (
                        None if protected_priority_max is None
                        else int(protected_priority_max)),
                    "levels": [{
                        "priority": priority,
                        "connections": int(np.sum(
                            connection_priorities == priority)),
                        "protected": int(np.sum(
                            (connection_priorities == priority) & protected)),
                    } for priority in sorted(set(
                        int(value) for value in connection_priorities))],
                    "protected_connection_count": int(np.sum(protected)),
                    "protected_retries_after_initial": 0,
                },
                "_best_usage_cong": usage_cong.copy(),
            })
        return paths, usage_raw, 0.0, 0, 0.0

    active = list(range(N))
    overuse_np = np.zeros((L, H, W), dtype=bool)
    residual_overuse = 0.0
    it_used = 0
    import os
    _debug = os.environ.get("CEC_COORD_DEBUG")

    # BEST-SO-FAR TRACKING (measured 2026-07-08): negotiated congestion on a real dense
    # board does NOT monotonically improve -- it oscillates around a floor (measured on
    # eps-8pin: 80 iters -> residual 138, 150 iters on the SAME run -> residual 195, worse).
    # pres_w growth keeps forcing rerouting even after a locally-best state, so the final
    # iteration is not necessarily the best one seen. Snapshot whenever residual improves and
    # return that snapshot, not just whatever the last iteration happened to land on. Ranked by
    # RAW residual (matches the primary convergence gate); the escaped number is recorded AT
    # that same best snapshot, not independently minimized.
    best_residual = None
    best_residual_escaped = None
    best_paths = None
    best_usage_raw = None
    best_usage_cong = None
    best_it = 0
    trace = []
    previous_best = None
    route_attempts = np.zeros(N, dtype=np.int32)

    for it in range(iters):
        it_used = it + 1
        pres_w_it = pres_w * (1.0 + it * pres_growth)

        if it > 0:
            active = [i for i in range(N)
                      if paths[i] is None
                      or (not protected[i]
                          and _path_crosses(paths[i], overuse_np))]
            if not active:
                break

        rng = np.random.RandomState(1000 + it)
        if priorities_enabled:
            # Route each ownership tier to completion before the next tier
            # sees a cost snapshot.  Randomization is deterministic and only
            # breaks ties *within* one tier; it can never let a residual net
            # consume a pair/control corridor first.
            chunks = []
            for priority in sorted({int(connection_priorities[i])
                                    for i in active}):
                order = [i for i in active
                         if int(connection_priorities[i]) == priority]
                rng.shuffle(order)
                csize = max(
                    chunk_min, int(math.ceil(len(order) * chunk_frac)))
                chunks.extend(order[i:i + csize]
                              for i in range(0, len(order), csize))
        else:
            order = list(active)
            rng.shuffle(order)
            csize = max(chunk_min, int(math.ceil(len(order) * chunk_frac)))
            chunks = [order[i:i + csize]
                      for i in range(0, len(order), csize)]

        for chunk in chunks:
            route_attempts[chunk] += 1
            for i in chunk:
                _accumulate(paths[i], usage_raw, usage_cong, sign=-1)  # rip up (no-op if None)

            pres_host = np.maximum(0.0, usage_cong - cap) * pres_w_it
            dynamic_cost = pres_host + history * hist_w
            if fixed_cost:
                dynamic_cost = np.rint(dynamic_cost * cost_scale).astype(np.int32)
            cellcost = base_cost + xp.asarray(dynamic_cost, dtype=cost_dtype)

            a_srcs = srcs[chunk]
            a_dsts = dsts[chunk]
            blocked = np.zeros((len(chunk), L, H, W), dtype=bool)
            for local, connection_index in enumerate(chunk):
                for layer, y, x in blocked_cells_by_conn[connection_index]:
                    if 0 <= layer < L and 0 <= y < H and 0 <= x < W:
                        blocked[local, layer, y, x] = True
                # A connection must always be permitted to leave and enter its
                # exact terminals even when a coarse cell also contains a
                # neighbouring land. Exact detailed routing still owns the
                # within-cell escape geometry.
                for layer, y, x in (a_srcs[local], a_dsts[local]):
                    blocked[local, layer, y, x] = False
            dist = _relax(a_srcs, L, H, W, xp, cellcost, bh, bv,
                          via_cost_work, max_sweeps, INF,
                          bias_scale=(cost_scale if fixed_cost else None),
                          allowed_layers=allowed_layers[chunk],
                          blocked_cells=blocked)
            new_paths = _batched_descent(
                dist, a_srcs, a_dsts, L, H, W, xp,
                via_cost_work, max_steps, fixed_cost=fixed_cost, INF=INF)
            for idx, i in enumerate(chunk):
                paths[i] = new_paths[idx]
                _accumulate(paths[i], usage_raw, usage_cong, sign=+1)

        overuse_np = np.maximum(0.0, usage_cong - cap)
        residual_overuse = float(overuse_np.sum())
        residual_overuse_escaped = float((overuse_np * ~escape_mask).sum())
        unroutable = sum(path is None for path in paths)
        history = history + overuse_np
        if (best_residual is None
                or (unroutable, residual_overuse)
                < (sum(path is None for path in (best_paths or ())),
                   best_residual)):
            best_residual = residual_overuse
            best_residual_escaped = residual_overuse_escaped
            best_paths = list(paths)          # shallow copy: elements are replaced, not mutated
            best_usage_raw = usage_raw.copy()
            best_usage_cong = usage_cong.copy()
            best_it = it + 1
        improved_by = (None if previous_best is None
                       else max(0.0, previous_best - float(best_residual)))
        previous_best = float(best_residual)
        trace.append({
            "iteration": it + 1,
            "active": len(active),
            "chunks": len(chunks),
            "unroutable": int(unroutable),
            "residual_overuse": round(float(residual_overuse), 6),
            "residual_overuse_escaped": round(
                float(residual_overuse_escaped), 6),
            "best_residual": round(float(best_residual), 6),
            "best_iteration": int(best_it),
            "stall_age": int(it + 1 - best_it),
            "best_improvement": (None if improved_by is None
                                 else round(float(improved_by), 6)),
            **({"active_by_priority": {
                str(priority): sum(
                    int(connection_priorities[i]) == priority for i in active)
                for priority in sorted({int(connection_priorities[i])
                                        for i in active})}}
               if priorities_enabled else {}),
        })
        if _debug:
            print(f"  it={it:3d} active={len(active):4d} chunks={len(chunks):3d} "
                  f"pres_w={pres_w_it:6.2f} residual={residual_overuse:8.1f} "
                  f"(escaped={residual_overuse_escaped:.1f}) best={best_residual:8.1f}@{best_it}",
                  file=sys.stderr)
        if residual_overuse == 0.0 and unroutable == 0:
            break

        # Optional deterministic plateau stop.  This never changes the default
        # router output.  Preflight/manager callers may enable it because they
        # consume best-so-far corridor evidence, not final detailed copper.
        patience = max(1, int(plateau_patience))
        if (early_stop_plateau and best_residual is not None
                and best_residual > 0 and it + 1 - best_it >= patience):
            recent = trace[-patience:]
            span = (max(row["best_residual"] for row in recent)
                    - min(row["best_residual"] for row in recent))
            if span <= float(plateau_min_delta) + 1e-9:
                break

    if telemetry is not None:
        patience = max(1, int(plateau_patience))
        recent = trace[-patience:]
        span = ((max(row["best_residual"] for row in recent)
                 - min(row["best_residual"] for row in recent))
                if recent else 0.0)
        stall_age = max(0, int(it_used - best_it))
        plateau = bool(best_residual is not None and best_residual > 0
                       and len(recent) >= patience
                       and stall_age >= patience
                       and span <= float(plateau_min_delta) + 1e-9)
        telemetry.update({
            "schema": 1,
            "best_iteration": int(best_it),
            "iterations_run": int(it_used),
            "stall_age": stall_age,
            "plateau": plateau,
            "plateau_patience": patience,
            "plateau_min_delta": float(plateau_min_delta),
            "early_stop_enabled": bool(early_stop_plateau),
            "early_stopped": bool(early_stop_plateau and it_used < int(iters)),
            # A bounded trace is enough to diagnose convergence without making
            # every candidate JSON grow with a long manager run.
            "trace": trace[-64:],
            "priority_routing": {
                "enabled": bool(priorities_enabled),
                "protected_priority_max": (
                    None if protected_priority_max is None
                    else int(protected_priority_max)),
                "levels": [{
                    "priority": priority,
                    "connections": int(np.sum(
                        connection_priorities == priority)),
                    "protected": int(np.sum(
                        (connection_priorities == priority) & protected)),
                } for priority in sorted(set(
                    int(value) for value in connection_priorities))],
                "protected_connection_count": int(np.sum(protected)),
                "protected_retries_after_initial": int(sum(
                    max(0, int(route_attempts[index]) - 1)
                    for index in range(N) if protected[index])),
            },
        })
        # Internal handoff to route_problem for exact per-layer effective
        # capacity.  It is popped before the telemetry enters JSON.
        telemetry["_best_usage_cong"] = best_usage_cong

    return best_paths, best_usage_raw, best_residual, it_used, best_residual_escaped


def _accumulate(path, usage_raw, usage_cong, sign):
    """path: list of (l, y, x) from dst (path[0]) to src (path[-1]). The net's own two
    endpoints are TERMINAL cells and are exempted from usage_cong (standard global-routing
    practice -- see module docstring point 2); usage_raw always gets every cell."""
    if not path:
        return
    term = {path[0], path[-1]}
    for p in path:
        l, y, x = p
        usage_raw[l, y, x] += sign
        if p not in term:
            usage_cong[l, y, x] += sign


def _path_crosses(path, overuse_mask):
    if not path:
        return False
    for (l, y, x) in path:
        if overuse_mask[l, y, x] > 0:
            return True
    return False


# ----------------------------------------------------------------------------------------
# Wavefront relax: (Na, L, H, W) simultaneous Bellman-Ford-style 4-neighbour + via relax.
# ----------------------------------------------------------------------------------------
def _relax(a_srcs, L, H, W, xp, cellcost, bias_h, bias_v, via_cost,
           max_sweeps, INF, *, bias_scale=None, allowed_layers=None,
           blocked_cells=None):
    import numpy as np
    Na = len(a_srcs)
    dist = xp.full((Na, L, H, W), INF, dtype=cellcost.dtype)
    idx = xp.arange(Na)
    sl = xp.asarray(a_srcs[:, 0], dtype=xp.int64)
    sy = xp.asarray(a_srcs[:, 1], dtype=xp.int64)
    sx = xp.asarray(a_srcs[:, 2], dtype=xp.int64)
    dist[idx, sl, sy, sx] = 0.0
    layer_mask = None
    if allowed_layers is not None:
        layer_mask = xp.asarray(allowed_layers, dtype=xp.bool_)[:, :, None, None]
        dist = xp.where(layer_mask, dist, INF)
    blocked_mask = None
    if blocked_cells is not None:
        blocked_mask = xp.asarray(blocked_cells, dtype=xp.bool_)
        if blocked_mask.shape != (Na, L, H, W):
            raise ValueError("blocked_cells shape %r != (%d, %d, %d, %d)"
                             % (blocked_mask.shape, Na, L, H, W))
        dist = xp.where(blocked_mask, INF, dist)
        dist[idx, sl, sy, sx] = 0

    cc = cellcost[None, :, :, :]                                   # (1, L, H, W)
    cost_h = cellcost * bias_h[:, None, None]
    cost_v = cellcost * bias_v[:, None, None]
    if bias_scale is not None:
        cost_h //= int(bias_scale)
        cost_v //= int(bias_scale)
        # A legal grid step must always cost at least one fixed-point unit.
        cost_h = xp.maximum(cost_h, 1)
        cost_v = xp.maximum(cost_v, 1)
    cost_h = cost_h[None, :, :, :]
    cost_v = cost_v[None, :, :, :]

    for _sweep in range(max_sweeps):
        nd = dist.copy()
        # vertical (y) neighbours
        nd[:, :, 1:, :] = xp.minimum(nd[:, :, 1:, :], dist[:, :, :-1, :] + cost_v[:, :, 1:, :])
        nd[:, :, :-1, :] = xp.minimum(nd[:, :, :-1, :], dist[:, :, 1:, :] + cost_v[:, :, :-1, :])
        # horizontal (x) neighbours
        nd[:, :, :, 1:] = xp.minimum(nd[:, :, :, 1:], dist[:, :, :, :-1] + cost_h[:, :, :, 1:])
        nd[:, :, :, :-1] = xp.minimum(nd[:, :, :, :-1], dist[:, :, :, 1:] + cost_h[:, :, :, :-1])
        # via (layer swap, same cell)
        if L == 2:
            nd[:, 0, :, :] = xp.minimum(nd[:, 0, :, :], dist[:, 1, :, :] + via_cost)
            nd[:, 1, :, :] = xp.minimum(nd[:, 1, :, :], dist[:, 0, :, :] + via_cost)
        elif L > 2:
            for l in range(L):
                for l2 in range(L):
                    if l2 != l:
                        nd[:, l, :, :] = xp.minimum(nd[:, l, :, :], dist[:, l2, :, :] + via_cost)
        if layer_mask is not None:
            nd = xp.where(layer_mask, nd, INF)
        if blocked_mask is not None:
            nd = xp.where(blocked_mask, INF, nd)
            nd[idx, sl, sy, sx] = 0
        if bool(xp.all(nd == dist)):
            dist = nd
            break
        dist = nd
    return dist


# ----------------------------------------------------------------------------------------
# GPU-resident batched greedy descent: all active nets step simultaneously from dst -> src.
# Only the FINAL small (Na, steps, 3) index history round-trips to host, once.
# ----------------------------------------------------------------------------------------
def _batched_descent(dist, a_srcs, a_dsts, L, H, W, xp, via_cost, max_steps,
                     *, fixed_cost=False, INF=None):
    import numpy as np
    Na = dist.shape[0]
    if Na == 0:
        return []
    idx = xp.arange(Na)
    cur_l = xp.asarray(a_dsts[:, 0], dtype=xp.int64)
    cur_y = xp.asarray(a_dsts[:, 1], dtype=xp.int64)
    cur_x = xp.asarray(a_dsts[:, 2], dtype=xp.int64)
    src_l = xp.asarray(a_srcs[:, 0], dtype=xp.int64)
    src_y = xp.asarray(a_srcs[:, 1], dtype=xp.int64)
    src_x = xp.asarray(a_srcs[:, 2], dtype=xp.int64)

    def _at_src(l, y, x):
        return (l == src_l) & (y == src_y) & (x == src_x)

    done = _at_src(cur_l, cur_y, cur_x)
    steps_l = [cur_l.copy()]
    steps_y = [cur_y.copy()]
    steps_x = [cur_x.copy()]

    def _gather(l, y, x):
        valid = ((l >= 0) & (l < L)
                 & (y >= 0) & (y < H) & (x >= 0) & (x < W))
        lc = xp.clip(l, 0, L - 1)
        yc = xp.clip(y, 0, H - 1)
        xc = xp.clip(x, 0, W - 1)
        v = dist[idx, lc, yc, xc]
        sentinel = INF if INF is not None else dist.dtype.type(1_000_000_000)
        return xp.where(valid, v, sentinel)

    for _step in range(max_steps):
        if bool(xp.all(done)):
            break
        cur_val = dist[idx, cur_l, cur_y, cur_x]
        cands = [
            (cur_l, cur_y - 1, cur_x),
            (cur_l, cur_y + 1, cur_x),
            (cur_l, cur_y, cur_x - 1),
            (cur_l, cur_y, cur_x + 1),
        ]
        cand_vals = [_gather(l, y, x) for (l, y, x) in cands]
        for layer in range(L):
            target_l = xp.full_like(cur_l, layer)
            value = _gather(target_l, cur_y, cur_x)
            value = xp.where(target_l != cur_l, value,
                             INF if INF is not None else value.dtype.type(1_000_000_000))
            cands.append((target_l, cur_y, cur_x))
            cand_vals.append(value)

        best_val = cur_val
        best_l, best_y, best_x = cur_l, cur_y, cur_x
        for (l, y, x), v in zip(cands, cand_vals):
            better = v < best_val if fixed_cost else v < (best_val - 1e-3)
            best_l = xp.where(better, l, best_l)
            best_y = xp.where(better, y, best_y)
            best_x = xp.where(better, x, best_x)
            best_val = xp.where(better, v, best_val)

        stuck = (best_val >= cur_val if fixed_cost
                 else best_val >= (cur_val - 1e-3))  # no improving neighbour -> freeze
        move = (~done) & (~stuck)
        cur_l = xp.where(move, best_l, cur_l)
        cur_y = xp.where(move, best_y, cur_y)
        cur_x = xp.where(move, best_x, cur_x)
        done = done | stuck | _at_src(cur_l, cur_y, cur_x)

        steps_l.append(cur_l.copy())
        steps_y.append(cur_y.copy())
        steps_x.append(cur_x.copy())

    # ONE host round-trip for the whole recorded descent, not per-step.
    L_h = xp.stack(steps_l, axis=1)
    Y_h = xp.stack(steps_y, axis=1)
    X_h = xp.stack(steps_x, axis=1)
    if xp is not np:
        L_h, Y_h, X_h = L_h.get(), Y_h.get(), X_h.get()
    else:
        L_h, Y_h, X_h = np.asarray(L_h), np.asarray(Y_h), np.asarray(X_h)

    paths = []
    for i in range(Na):
        sl, sy, sx = int(a_srcs[i][0]), int(a_srcs[i][1]), int(a_srcs[i][2])
        pts = []
        seen_src = False
        for t in range(L_h.shape[1]):
            p = (int(L_h[i, t]), int(Y_h[i, t]), int(X_h[i, t]))
            if not pts or pts[-1] != p:
                pts.append(p)
            if p == (sl, sy, sx):
                seen_src = True
                break
        paths.append(pts if seen_src else None)
    return paths


# ============================================================================
# Backend selection + top-level API
# ============================================================================
def _pick_backend(backend):
    if backend == "cpu":
        if _np is None:
            raise RuntimeError("numpy is required and not importable")
        return _np, "cpu"
    if backend == "gpu":
        if _cp is None:
            raise RuntimeError("cupy requested but not importable (no GPU backend)")
        return _cp, "gpu"
    if backend == "auto":
        if _cp is not None:
            try:
                _cp.cuda.Device(0).compute_capability  # cheap availability probe
                return _cp, "gpu"
            except Exception:
                pass
        return _np, "cpu"
    raise ValueError(f"unknown backend {backend!r} (want auto|cpu|gpu)")


def _planned_backend(backend, work_cells, auto_gpu_floor):
    """Pure admission policy; availability/execution is decided afterwards."""
    if backend not in ("auto", "cpu", "gpu"):
        raise ValueError(f"unknown backend {backend!r} (want auto|cpu|gpu)")
    if backend == "auto":
        return "gpu" if int(work_cells) >= int(auto_gpu_floor) else "cpu"
    return backend


def _capture_thread_locale():
    """Capture the POSIX per-thread locale selected by native libraries.

    CUDA/NVRTC initialization in some CuPy builds calls ``uselocale()`` and
    leaves the Python thread attached to a private C locale.  ``setlocale()``
    still reports the unchanged process-global C.UTF-8 locale in that state,
    while implicit text I/O silently falls back to ASCII.  Keep this tiny,
    best-effort boundary here instead of making every downstream file open
    defend against unrelated GPU process state.

    The symbol is POSIX-only.  Other platforms return ``None`` and retain
    their normal locale behavior.
    """
    try:
        import ctypes
        libc = ctypes.CDLL(None)
        use_locale = libc.uselocale
        use_locale.argtypes = [ctypes.c_void_p]
        use_locale.restype = ctypes.c_void_p
        token = use_locale(None)
        if token is None:
            return None
        return use_locale, int(token)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _restore_thread_locale(state):
    if state is None:
        return
    use_locale, token = state
    try:
        import ctypes
        use_locale(ctypes.c_void_p(token))
    except (OSError, TypeError, ValueError):
        # Routing evidence remains valid even on a platform without a usable
        # POSIX locale handle.  The paired regression test exercises Linux,
        # where the CUDA contamination has actually been observed.
        pass


def route_problem(conns, H, W, *, backend="auto", layer_names=None, **kw):
    """Route a synthetic/pre-built problem (no board I/O). Returns the same dict shape as
    route_board (minus board-specific fields).

    NOTE on "paths" keys: MST decomposition (build_problem) can emit SEVERAL two-pin edges
    that all share the same underlying net name (any net with >2 pads). A plain {net: path}
    dict would silently drop all but the last edge for such a net, so multi-edge nets are
    keyed "NAME#2", "NAME#3", ... (1-based, first edge keeps the bare name) -- collision-free
    and still net-name-discoverable. "paths_by_conn" is the unambiguous parallel-to-conns list
    (index i <-> conns[i]) for callers that need exact per-edge identity (e.g. CPU/GPU diffing).
    """
    requested_backend = backend
    layers = int(kw.get("L", 2))
    work_cells = int(len(conns) * layers * H * W)
    # Measured crossover on the Hub, fixed-point / four route layers / 8 iters:
    # 7.9M cells @ .75 mm = 24.6 s CPU vs 32.2 s CUDA, while 17.8M cells
    # @ .5 mm = 101.7 s CPU vs 50.6 s CUDA with byte-identical residuals.
    # Small chunks cannot amortize launch/descent overhead; large grids do.
    # Callers can still force either backend for a pinned A/B.
    auto_gpu_floor = int(kw.pop(
        "auto_gpu_floor",
        os.environ.get("CEC_COORD_AUTO_GPU_FLOOR", "12000000")))
    service_bypass = bool(kw.pop("_service_bypass", False))
    selected_backend = _planned_backend(
        backend, work_cells, auto_gpu_floor)
    service_fallback = None
    service_socket = os.environ.get("CEC_COORD_SERVICE_SOCKET")
    if (selected_backend == "gpu" and service_socket and not service_bypass
            and os.environ.get("CEC_COORD_SERVICE_SERVER") != "1"):
        # Crucially, dispatch before _pick_backend: spawned pcbnew workers do
        # not initialize their own CUDA contexts merely to discover that the
        # persistent owner is available.
        try:
            import cec_route_awareness_service
            result = cec_route_awareness_service.route_remote(
                conns, H, W, layer_names=layer_names, **kw)
            result["backend_requested"] = requested_backend
            result["backend_work_cells"] = work_cells
            result["auto_gpu_floor"] = auto_gpu_floor
            return result
        except Exception as exc:
            if backend != "auto":
                raise RuntimeError(
                    "persistent CUDA route service failed") from exc
            # Auto means auto in both directions.  An unavailable or memory-
            # constrained GPU must degrade to the deterministic CPU engine,
            # never convert route-awareness into a wave infrastructure error.
            selected_backend = "cpu"
            service_fallback = "%s: %s" % (type(exc).__name__, exc)
    xp, backend_name = _pick_backend(selected_backend)
    negotiation = kw.pop("telemetry", None)
    if negotiation is None:
        negotiation = {}
    kw["telemetry"] = negotiation
    t0 = time.perf_counter()
    thread_locale = _capture_thread_locale() if xp is _cp else None
    try:
        paths, usage, residual, its, residual_escaped = route_negotiated(
            conns, H, W, xp, **kw)
        negotiated_usage = negotiation.pop("_best_usage_cong", None)
        if xp is _cp:
            _cp.cuda.Stream.null.synchronize()
        wall_s = time.perf_counter() - t0
    finally:
        _restore_thread_locale(thread_locale)
    import collections
    name_count = collections.Counter(c[0] for c in conns)
    seen = collections.Counter()
    named_paths = {}
    for i, (net, _a, _b) in enumerate(conns):
        seen[net] += 1
        key = net if name_count[net] == 1 else f"{net}#{seen[net]}"
        named_paths[key] = paths[i]
    unroutable_indices = [i for i, path in enumerate(paths) if path is None]
    cap = kw.get("cap")
    if cap is None:
        cap = _capacity(kw.get("grid_mm", 0.5), kw.get("pitch_mm", 0.45))
    result = {
        "paths": named_paths,
        "paths_by_conn": paths,
        "usage": usage,
        "residual_overuse": residual,
        "residual_overuse_escaped": residual_escaped,
        "iters_used": its,
        "wall_s": wall_s,
        "backend": backend_name,
        "backend_requested": requested_backend,
        "backend_work_cells": work_cells,
        "auto_gpu_floor": auto_gpu_floor,
        "n_nets": len(conns),
        "unroutable_count": len(unroutable_indices),
        "unroutable_connections": [
            {"index": i, "net": conns[i][0],
             "src": tuple(conns[i][1]), "dst": tuple(conns[i][2])}
            for i in unroutable_indices[:64]],
        "grid": (H, W),
        "layer_names": tuple(layer_names or ()),
        "cost_mode": kw.get("cost_mode", "float"),
        "negotiation": negotiation,
        "congestion": summarize_congestion(
            usage, cap, negotiated_usage=negotiated_usage,
            layer_names=layer_names),
    }
    result["blockage_witnesses"] = blockage_witnesses(
        conns, paths, result["congestion"], cap=cap,
        blocked_cells_by_conn=kw.get("blocked_cells_by_conn"),
        allowed_layers=kw.get("allowed_layers"),
        connection_priorities=kw.get("connection_priorities"),
        protected_priority_max=kw.get("protected_priority_max"),
        height=H, width=W)
    if service_fallback:
        result["route_awareness_service"] = {
            "used": False,
            "fallback": "cpu",
            "error": service_fallback,
        }
    return result


def route_board(board_path, *, grid_mm=0.5, iters=40, backend="auto", **kw):
    """Top-level API: KiCad board -> negotiated-congestion global route. Read-only on the
    board (LoadBoard only; never Save)."""
    conns, H, W, foreign_cells, meta = build_problem(
        board_path, grid_mm=grid_mm, detailed=True)
    blocked = meta.pop("_blocked_cells_by_conn", ())
    result = route_problem(conns, H, W, backend=backend, grid_mm=grid_mm, iters=iters,
                            foreign_cells=foreign_cells,
                            blocked_cells_by_conn=blocked,
                            L=len(meta["layer_names"]),
                            layer_names=meta["layer_names"],
                            allowed_layers=meta["allowed_layers_by_conn"], **kw)
    result["board_path"] = board_path
    result["grid_mm"] = grid_mm
    result["stackup"] = meta
    return result


# ============================================================================
# CLI
# ============================================================================
def main():
    args = sys.argv[1:]
    force_cpu = "--cpu" in args
    args = [a for a in args if a != "--cpu"]
    grid_mm = 0.5
    iters = 40
    if "--grid-mm" in args:
        i = args.index("--grid-mm")
        grid_mm = float(args[i + 1])
        del args[i:i + 2]
    if "--iters" in args:
        i = args.index("--iters")
        iters = int(args[i + 1])
        del args[i:i + 2]
    board = args[0] if args else \
        "/workspace/build/fresh/atx-24pin-rev3/20260708T2055-periph-left-dataflow-s1.kicad_pcb"

    conns, H, W, foreign, meta = build_problem(
        board, grid_mm=grid_mm, detailed=True)
    cap = _capacity(grid_mm)
    print(f"problem: {len(conns)} two-pin connections on a {H}x{W} grid @ {grid_mm}mm "
          f"(cap={cap}/cell/layer, foreign_cells={len(foreign)})")

    backend = "cpu" if force_cpu else "auto"
    r = route_problem(conns, H, W, backend=backend, grid_mm=grid_mm, iters=iters,
                       foreign_cells=foreign, L=len(meta["layer_names"]),
                       layer_names=meta["layer_names"],
                       allowed_layers=meta["allowed_layers_by_conn"],
                       cost_mode="fixed")
    print(f"{r['backend']:>4} : {r['wall_s']:7.2f}s  iters_used={r['iters_used']:2d}  "
          f"residual_overuse={r['residual_overuse']} "
          f"(escape-exempted={r['residual_overuse_escaped']})")

    if not force_cpu and _cp is not None and r["backend"] == "gpu":
        r2 = route_problem(conns, H, W, backend="cpu", grid_mm=grid_mm, iters=iters,
                            foreign_cells=foreign)
        print(f" cpu : {r2['wall_s']:7.2f}s  iters_used={r2['iters_used']:2d}  "
              f"residual_overuse={r2['residual_overuse']} "
              f"(escape-exempted={r2['residual_overuse_escaped']})  "
              f"speedup {r2['wall_s']/max(r['wall_s'], 1e-9):.1f}x")


if __name__ == "__main__":
    main()
