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
def build_problem(board_path, grid_mm=0.5, excluded_nets=("GND",)):
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
    bb = b.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetLeft() / 1e6, bb.GetTop() / 1e6
    W = int(bb.GetWidth() / 1e6 / grid_mm) + 1
    H = int(bb.GetHeight() / 1e6 / grid_mm) + 1

    def _cell(p):
        gx = int((p.GetPosition().x / 1e6 - x0) / grid_mm)
        gy = int((p.GetPosition().y / 1e6 - y0) / grid_mm)
        return min(H - 1, max(0, gy)), min(W - 1, max(0, gx))

    def _layer(p):
        try:
            if p.IsOnLayer(pcbnew.F_Cu):
                return F_CU
            if p.IsOnLayer(pcbnew.B_Cu):
                return B_CU
        except Exception:
            pass
        return F_CU

    pads_by_net = {}
    foreign_cells = set()
    for fp in b.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if not n:
                continue
            gy, gx = _cell(p)
            if n in excluded_nets:
                foreign_cells.add((_layer(p), gy, gx))
                continue
            pads_by_net.setdefault(n, set()).add((_layer(p), gy, gx))

    # 2-pin decomposition: MST edges per multi-pin net (distance ignores layer -- topology
    # only; the relax/via cost handles the actual layer-crossing cost during routing).
    conns = []
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
            for i, p in enumerate(pts):
                nd = math.hypot(pts[bi][1] - p[1], pts[bi][2] - p[2])
                if nd < d[i]:
                    d[i], par[i] = nd, bi
    return conns, H, W, foreign_cells


# ============================================================================
# Capacity model
# ============================================================================
def _capacity(grid_mm, pitch_mm=0.45):
    """floor(grid_mm / pitch_mm) trace pitches per cell per layer, floored at 1."""
    return max(1, int(math.floor(grid_mm / pitch_mm + 1e-9)))


# ============================================================================
# Core negotiated-congestion router (xp-polymorphic: numpy or cupy)
# ============================================================================
def route_negotiated(conns, H, W, xp, *, L=2, iters=40, hist_w=1.5, pres_w=2.0,
                      grid_mm=0.5, pitch_mm=0.45, cap=None, via_cost=3.0,
                      bias=True, bias_h=(0.8, 1.2), bias_v=(1.2, 0.8),
                      foreign_cells=None, foreign_cost=5.0, max_sweeps=None,
                      max_steps=None, pres_growth=0.35, chunk_frac=0.125, chunk_min=6,
                      escape_radius=2):
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
    INF = xp.float32(1e9)

    srcs = np.zeros((N, 3), dtype=np.int32)
    dsts = np.zeros((N, 3), dtype=np.int32)
    for i, (_n, a, b) in enumerate(conns):
        srcs[i] = a
        dsts[i] = b

    bh = xp.asarray(bias_h if bias else (1.0,) * L, dtype=xp.float32)
    bv = xp.asarray(bias_v if bias else (1.0,) * L, dtype=xp.float32)

    base_cost = xp.ones((L, H, W), dtype=xp.float32)
    if foreign_cells:
        fc = np.zeros((L, H, W), dtype=np.float32)
        for (l, y, x) in foreign_cells:
            if 0 <= l < L and 0 <= y < H and 0 <= x < W:
                fc[l, y, x] += foreign_cost
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
    best_it = 0

    for it in range(iters):
        it_used = it + 1
        pres_w_it = pres_w * (1.0 + it * pres_growth)

        if it > 0:
            active = [i for i in range(N) if _path_crosses(paths[i], overuse_np)]
            if not active:
                break

        rng = np.random.RandomState(1000 + it)
        order = list(active)
        rng.shuffle(order)
        csize = max(chunk_min, int(math.ceil(len(order) * chunk_frac)))
        chunks = [order[i:i + csize] for i in range(0, len(order), csize)]

        for chunk in chunks:
            for i in chunk:
                _accumulate(paths[i], usage_raw, usage_cong, sign=-1)  # rip up (no-op if None)

            pres_host = np.maximum(0.0, usage_cong - cap) * pres_w_it
            cellcost = base_cost + xp.asarray(pres_host + history * hist_w, dtype=xp.float32)

            a_srcs = srcs[chunk]
            a_dsts = dsts[chunk]
            dist = _relax(a_srcs, L, H, W, xp, cellcost, bh, bv, via_cost, max_sweeps, INF)
            new_paths = _batched_descent(dist, a_srcs, a_dsts, L, H, W, xp, via_cost, max_steps)
            for idx, i in enumerate(chunk):
                paths[i] = new_paths[idx]
                _accumulate(paths[i], usage_raw, usage_cong, sign=+1)

        overuse_np = np.maximum(0.0, usage_cong - cap)
        residual_overuse = float(overuse_np.sum())
        residual_overuse_escaped = float((overuse_np * ~escape_mask).sum())
        history = history + overuse_np
        if best_residual is None or residual_overuse < best_residual:
            best_residual = residual_overuse
            best_residual_escaped = residual_overuse_escaped
            best_paths = list(paths)          # shallow copy: elements are replaced, not mutated
            best_usage_raw = usage_raw.copy()
            best_it = it + 1
        if _debug:
            print(f"  it={it:3d} active={len(active):4d} chunks={len(chunks):3d} "
                  f"pres_w={pres_w_it:6.2f} residual={residual_overuse:8.1f} "
                  f"(escaped={residual_overuse_escaped:.1f}) best={best_residual:8.1f}@{best_it}",
                  file=sys.stderr)
        if residual_overuse == 0.0:
            break

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
def _relax(a_srcs, L, H, W, xp, cellcost, bias_h, bias_v, via_cost, max_sweeps, INF):
    import numpy as np
    Na = len(a_srcs)
    dist = xp.full((Na, L, H, W), INF, dtype=xp.float32)
    idx = xp.arange(Na)
    sl = xp.asarray(a_srcs[:, 0], dtype=xp.int64)
    sy = xp.asarray(a_srcs[:, 1], dtype=xp.int64)
    sx = xp.asarray(a_srcs[:, 2], dtype=xp.int64)
    dist[idx, sl, sy, sx] = 0.0

    cc = cellcost[None, :, :, :]                                   # (1, L, H, W)
    cost_h = (cellcost * bias_h[:, None, None])[None, :, :, :]
    cost_v = (cellcost * bias_v[:, None, None])[None, :, :, :]

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
        if bool(xp.all(nd == dist)):
            dist = nd
            break
        dist = nd
    return dist


# ----------------------------------------------------------------------------------------
# GPU-resident batched greedy descent: all active nets step simultaneously from dst -> src.
# Only the FINAL small (Na, steps, 3) index history round-trips to host, once.
# ----------------------------------------------------------------------------------------
def _batched_descent(dist, a_srcs, a_dsts, L, H, W, xp, via_cost, max_steps):
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
        valid = (y >= 0) & (y < H) & (x >= 0) & (x < W)
        yc = xp.clip(y, 0, H - 1)
        xc = xp.clip(x, 0, W - 1)
        v = dist[idx, l, yc, xc]
        return xp.where(valid, v, xp.float32(1e9))

    for _step in range(max_steps):
        if bool(xp.all(done)):
            break
        cur_val = dist[idx, cur_l, cur_y, cur_x]
        other_l = 1 - cur_l if L == 2 else cur_l  # L==2 only path used in this pipeline
        cands = [
            (cur_l, cur_y - 1, cur_x),
            (cur_l, cur_y + 1, cur_x),
            (cur_l, cur_y, cur_x - 1),
            (cur_l, cur_y, cur_x + 1),
        ]
        cand_vals = [_gather(l, y, x) for (l, y, x) in cands]
        if L == 2:
            cands.append((other_l, cur_y, cur_x))
            cand_vals.append(_gather(other_l, cur_y, cur_x))

        best_val = cur_val
        best_l, best_y, best_x = cur_l, cur_y, cur_x
        for (l, y, x), v in zip(cands, cand_vals):
            better = v < (best_val - 1e-3)
            best_l = xp.where(better, l, best_l)
            best_y = xp.where(better, y, best_y)
            best_x = xp.where(better, x, best_x)
            best_val = xp.where(better, v, best_val)

        stuck = best_val >= (cur_val - 1e-3)  # no improving neighbour -> freeze (guard)
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
        if not seen_src:
            pts.append((sl, sy, sx))  # guard: force-close so usage bookkeeping stays sane
        paths.append(pts)
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


def route_problem(conns, H, W, *, backend="auto", **kw):
    """Route a synthetic/pre-built problem (no board I/O). Returns the same dict shape as
    route_board (minus board-specific fields).

    NOTE on "paths" keys: MST decomposition (build_problem) can emit SEVERAL two-pin edges
    that all share the same underlying net name (any net with >2 pads). A plain {net: path}
    dict would silently drop all but the last edge for such a net, so multi-edge nets are
    keyed "NAME#2", "NAME#3", ... (1-based, first edge keeps the bare name) -- collision-free
    and still net-name-discoverable. "paths_by_conn" is the unambiguous parallel-to-conns list
    (index i <-> conns[i]) for callers that need exact per-edge identity (e.g. CPU/GPU diffing).
    """
    xp, backend_name = _pick_backend(backend)
    t0 = time.perf_counter()
    paths, usage, residual, its, residual_escaped = route_negotiated(conns, H, W, xp, **kw)
    if xp is _cp:
        _cp.cuda.Stream.null.synchronize()
    wall_s = time.perf_counter() - t0
    import collections
    name_count = collections.Counter(c[0] for c in conns)
    seen = collections.Counter()
    named_paths = {}
    for i, (net, _a, _b) in enumerate(conns):
        seen[net] += 1
        key = net if name_count[net] == 1 else f"{net}#{seen[net]}"
        named_paths[key] = paths[i]
    return {
        "paths": named_paths,
        "paths_by_conn": paths,
        "usage": usage,
        "residual_overuse": residual,
        "residual_overuse_escaped": residual_escaped,
        "iters_used": its,
        "wall_s": wall_s,
        "backend": backend_name,
        "n_nets": len(conns),
        "grid": (H, W),
    }


def route_board(board_path, *, grid_mm=0.5, iters=40, backend="auto", **kw):
    """Top-level API: KiCad board -> negotiated-congestion global route. Read-only on the
    board (LoadBoard only; never Save)."""
    conns, H, W, foreign_cells = build_problem(board_path, grid_mm=grid_mm)
    result = route_problem(conns, H, W, backend=backend, grid_mm=grid_mm, iters=iters,
                            foreign_cells=foreign_cells, **kw)
    result["board_path"] = board_path
    result["grid_mm"] = grid_mm
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

    conns, H, W, foreign = build_problem(board, grid_mm=grid_mm)
    cap = _capacity(grid_mm)
    print(f"problem: {len(conns)} two-pin connections on a {H}x{W} grid @ {grid_mm}mm "
          f"(cap={cap}/cell/layer, foreign_cells={len(foreign)})")

    backend = "cpu" if force_cpu else "auto"
    r = route_problem(conns, H, W, backend=backend, grid_mm=grid_mm, iters=iters,
                       foreign_cells=foreign)
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
