#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_cell_refine -- BLUEPRINT-CELL REFINEMENT LOOP (owner GO 2026-07-10)
# ============================================================================
# The extractor (cec_cell_extract) is a FIDELITY tool: it replicates the hand
# cell verbatim (placement copied, hand copper wins over synthesis). This
# module is the IMPROVEMENT half the owner asked for ("can it extract from the
# 12VHPWR and *improve* on it? ... help me pack components into a smaller
# space"): treat the extracted template as the BASELINE + seed, search the
# cell's internal placement (translate / 90-degree rotate / pack-against /
# swap) with ROUTE-IN-THE-LOOP scoring, and accept only variants that pass
# every gate AND beat the baseline -- improve-never-regress, the golden
# discipline at cell scale.
#
# OWNER RULINGS BOUND HERE (2026-07-10):
#   * SINGLE-FACE FIRST: dual-sided cell search is DEFERRED until the
#     single-face stack is exhausted -- the stop condition is "the connector
#     width is the limiting factor" (then dual-side buys nothing). Templates
#     with flipped parts are refused with a named reason; there is no face
#     variable in the search. (Dual-side pours/routing = a later refinement.)
#   * BEFORE/AFTER OWNER PANELS: every refinement emits a side-by-side
#     baseline-vs-refined render + metrics; the OWNER denotes improvements.
#     Machine score ranks candidates; it does not ratify them.
#   * FINDER: find_cells() detects repeated component groups from the NETLIST
#     alone (copy-paste NOT required -- structural fingerprint), and (with a
#     board) reports which instances have no/partial internal copper to
#     extract ("areas where there is no copper ... find those areas for me").
#   * SCOPE: blueprint refinement + blueprint routing only. No waves.
#
# The cell problem is TINY (the 12vhpwr lane: 6 parts, ~5 routed nets in a
# ~10x20mm window), which flips the whole-board economics: route-in-the-loop
# is affordable per candidate, so thousands of fully-routed, fully-gated
# variants evaluate in seconds on the host (profile harness:
# build/profile_refiner.py). pcbnew is needed only at the EDGES (extract from
# a real board; emit micro-boards for real kicad-cli DRC + renders) -- the
# search itself is pure geometry over cec_pcb's parsed footprints and runs
# anywhere.
#
# Container legs (extract / emit / DRC / render):
#   sg docker -c "docker compose -f docker/compose.yaml exec -T routing \
#       python3 scripts/cec_cell_refine.py refine --board <pcb> --refs ... --anchor RS4"
#
# ROUTING FORMS this module owns (all F.Cu, single-face ruling):
#   * KELVIN TAPS (canonical, the 798526e geometry): a 2-pad port whose first
#     pad is on the ANCHOR (the shunt force/sense taps, e.g. /SENSEP{n}_HI =
#     RS.1 -> RFH.1) routes as perpendicular-exit-from-the-pad -> run -> one
#     90-degree bend. HI/LO tap lengths are gate-matched (skew cap) because
#     they are the sense pair.
#   * LOCAL CHAINS (escape-L, the synthesize_ideal_internal algorithm,
#     re-run on the VARIANT geometry): internal nets (/IN{n}_P, /IN{n}_N) and
#     2-pad supply links (the IC bypass +{n}V{n}: U.6 <-> C.1). GND is NOT
#     routed in-cell (plane-served on every CEC board); the bypass stays
#     honest via the decoupler-adjacency gate instead.
# A route that cannot lay clear of foreign pads/tracks is REFUSED with a
# named reason (escalate-never-force); a refused variant is infeasible.
import argparse
import cProfile
import io
import json
import math
import os
import pstats
import re
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cec_pcb  # host-safe: parses .kicad_mod text, no pcbnew

MM = 1_000_000
CLR_MM = 0.20          # copper clearance floor (Sense-class, matches the board DRU)
TRACK_W = 0.25         # Sense-class width (matches the hand cell's 0.25)
TAP_SKEW_MAX = 8.0     # mm, HI-vs-LO tap mismatch SANITY bound only -- the hand lane itself
                       # carries ~6mm (RS.1->RFH 10.4 vs RS.2->RFL 4.5); skew is driven DOWN
                       # by the score (4x weight), never hard-gated below the owner's own design
TAP_LEN_MAX = 14.0     # mm, a tap longer than this is not a Kelvin tap
DECOUPLER_MM = 3.0     # bypass-cap pad must sit within this of its IC supply pad


def _rot(lx, ly, a_deg):
    """KiCad footprint rotation (y-down screen frame) -- same convention as
    cec_cell_extract._rot / cec_pcb, verified against extracted pad rel_mm."""
    a = math.radians(a_deg)
    return (lx * math.cos(a) + ly * math.sin(a), -lx * math.sin(a) + ly * math.cos(a))


# --------------------------------------------------------------------------
# Sized local pads (cec_pcb.local_pads gives centres only; clearance needs
# extents). Parsed once per libid from the same .kicad_mod source of truth.
# --------------------------------------------------------------------------
_SIZED_CACHE = {}


def local_pads_sized(libid):
    """{pad: (lx, ly, hw, hh)} -- centre + half-extents at the pad's own rotation
    folded into the box (conservative AABB of the rotated pad rect)."""
    if libid in _SIZED_CACHE:
        return _SIZED_CACHE[libid]
    nick, name = libid.split(":")
    t = open(cec_pcb.fp_path(nick, name)).read()
    out = {}
    for m in re.finditer(r"\(pad ", t):
        b = cec_pcb.carve(t, m.start())
        head = b.split("\n")[0]
        if "np_thru_hole" in head:
            continue
        num = re.match(r'\(pad "([^"]*)"', b)
        at = re.search(r"\(at (-?[\d.]+) (-?[\d.]+)(?: (-?[\d.]+))?\)", b)
        size = re.search(r"\(size ([\d.]+) ([\d.]+)\)", b)
        if not (num and at and size):
            continue
        lx, ly = float(at.group(1)), float(at.group(2))
        prot = float(at.group(3) or 0.0)
        sx, sy = float(size.group(1)) / 2.0, float(size.group(2)) / 2.0
        if abs(prot % 180.0) > 45.0:                      # 90-ish pad rotation swaps extents
            sx, sy = sy, sx
        out[num.group(1)] = (lx, ly, sx, sy)
    _SIZED_CACHE[libid] = out
    return out


# --------------------------------------------------------------------------
# Geometry primitives (segments as (x1,y1,x2,y2))
# --------------------------------------------------------------------------
def _seg_pt_d2(x1, y1, x2, y2, px, py):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 <= 1e-12:
        ex, ey = px - x1, py - y1
        return ex * ex + ey * ey
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    ex, ey = px - (x1 + t * dx), py - (y1 + t * dy)
    return ex * ex + ey * ey


def _seg_seg_d2(a, b):
    (ax1, ay1, ax2, ay2), (bx1, by1, bx2, by2) = a, b
    # cheap exact-enough: min of endpoint-to-segment distances + crossing test
    d1 = (ax2 - ax1) * (by1 - ay1) - (ay2 - ay1) * (bx1 - ax1)
    d2 = (ax2 - ax1) * (by2 - ay1) - (ay2 - ay1) * (bx2 - ax1)
    d3 = (bx2 - bx1) * (ay1 - by1) - (by2 - by1) * (ax1 - bx1)
    d4 = (bx2 - bx1) * (ay2 - by1) - (by2 - by1) * (ax2 - bx1)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(_seg_pt_d2(ax1, ay1, ax2, ay2, bx1, by1),
               _seg_pt_d2(ax1, ay1, ax2, ay2, bx2, by2),
               _seg_pt_d2(bx1, by1, bx2, by2, ax1, ay1),
               _seg_pt_d2(bx1, by1, bx2, by2, ax2, ay2))


def _seg_box_clear(seg, box, clr):
    """True iff segment stays >= clr from the AABB (x0,x1,y0,y1) (edge-expanded test)."""
    x0, x1, y0, y1 = box
    # quick reject: segment bbox vs inflated box
    sx0, sx1 = min(seg[0], seg[2]), max(seg[0], seg[2])
    sy0, sy1 = min(seg[1], seg[3]), max(seg[1], seg[3])
    if sx1 < x0 - clr or sx0 > x1 + clr or sy1 < y0 - clr or sy0 > y1 + clr:
        return True
    # distance from segment to box = 0 if it enters; else min distance to the 4 edges
    edges = ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0))
    # inside test (either endpoint inside the inflated box counts as too close)
    for px, py in ((seg[0], seg[1]), (seg[2], seg[3])):
        if x0 - clr <= px <= x1 + clr and y0 - clr <= py <= y1 + clr:
            return False
    return all(_seg_seg_d2(seg, e) >= clr * clr for e in edges)


# --------------------------------------------------------------------------
# The cell model
# --------------------------------------------------------------------------
class CellModel:
    """Host-side geometric model of one extracted template. Pose = {ref: (dx, dy,
    rot_deg)} in the anchor frame (anchor pinned at (0,0,0) -- the shunt's seat is
    lane-dictated, not the cell's to move)."""

    def __init__(self, template, *, pitch_axis="y"):
        self.t = template
        self.anchor = template["anchor"]["ref"]
        self.pitch_axis = pitch_axis
        if template["anchor"].get("flipped"):
            raise ValueError("flipped anchor: dual-side templates deferred (owner ruling 2026-07-10)")
        self.parts = {}                          # ref -> (fp, base_off, base_rot)
        for ref, sp in template["parts"].items():
            if sp.get("flipped"):
                raise ValueError(f"{ref} is flipped: dual-side templates deferred (owner ruling 2026-07-10)")
            self.parts[ref] = (sp["footprint"], tuple(sp["offset_mm"]), float(sp.get("rot_delta", 0.0)))
        # pad -> role map from ports + internal_pads (both carry in-cell pads only)
        self.pad_role = {}
        self.role_pads = defaultdict(list)       # role -> [(ref, pad)]
        self.role_net = dict(template.get("net_roles") or {})
        for bucket in ("ports", "internal_pads"):
            for role, spec in (template.get(bucket) or {}).items():
                for p in spec.get("pads", []):
                    self.pad_role[(p["ref"], p["pad"])] = role
                    self.role_pads[role].append((p["ref"], p["pad"]))
        self.internal_roles = set((template.get("internal_pads") or {}).keys())
        self.port_roles = set((template.get("ports") or {}).keys())
        # which roles this module routes in-cell (see header): internal chains,
        # anchor taps (2-pad port incl. an anchor pad), 2-pad supply links; never GND.
        self.tap_roles, self.link_roles = [], []
        for role in sorted(self.port_roles):
            pads = self.role_pads[role]
            if len(pads) != 2 or role == "GND":
                continue
            (self.tap_roles if any(r == self.anchor for r, _ in pads) else self.link_roles).append(role)
        self.route_roles = sorted(self.internal_roles) + self.tap_roles + self.link_roles
        self.base_pose = {r: (off[0], off[1], rot) for r, (fp, off, rot) in self.parts.items()}
        self._sized = {ref: local_pads_sized(fp) for ref, (fp, _o, _r) in self.parts.items()}
        self._cy = {}                            # (ref, rot%360) -> local courtyard bbox

    # ---- pose-dependent geometry -----------------------------------------
    def pad_at(self, pose, ref, pad):
        lx, ly, hw, hh = self._sized[ref][pad]
        dx, dy, rot = pose[ref]
        px, py = _rot(lx, ly, rot)
        if abs(rot % 180.0) > 45.0:
            hw, hh = hh, hw
        return (dx + px, dy + py, hw, hh)

    def courtyard(self, pose, ref):
        fp, _off, _r = self.parts[ref]
        dx, dy, rot = pose[ref]
        key = (ref, round(rot) % 360)
        if key not in self._cy:
            self._cy[key] = cec_pcb.courtyard_bbox(fp, 0.0, 0.0, rot)
        x0, x1, y0, y1 = self._cy[key]
        return (x0 + dx, x1 + dx, y0 + dy, y1 + dy)

    def foreign_pad_boxes(self, pose, role):
        """AABBs of every pad NOT on `role` (the clearance obstacles for that net)."""
        out = []
        for (ref, pad), r in self.pad_role.items():
            if r == role:
                continue
            x, y, hw, hh = self.pad_at(pose, ref, pad)
            out.append((x - hw, x + hw, y - hh, y + hh))
        return out


# --------------------------------------------------------------------------
# Routing synthesis (route-in-the-loop)
# --------------------------------------------------------------------------
class Refusal(Exception):
    pass


def _l_paths(a, b):
    """The two orthogonal L candidates a->corner->b."""
    (ax, ay), (bx, by) = a, b
    return (((ax, ay, bx, ay), (bx, ay, bx, by)),
            ((ax, ay, ax, by), (ax, by, bx, by)))


def _check(segs, role, obstacles, laid):
    for s in segs:
        if abs(s[0] - s[2]) < 1e-9 and abs(s[1] - s[3]) < 1e-9:
            continue
        for box in obstacles:
            if not _seg_box_clear(s, box, CLR_MM + TRACK_W / 2.0):
                raise Refusal(f"{role}: segment clips a foreign pad")
        for orole, os_ in laid:
            if orole == role:
                continue
            if _seg_seg_d2(s, os_) < (CLR_MM + TRACK_W) ** 2:
                raise Refusal(f"{role}: segment clips {orole} track")
    return segs


def synth_routes(model, pose):
    """Route every model.route_roles net on the VARIANT geometry. Returns
    {role: [segments]}; raises Refusal on the first un-layable net."""
    laid = []                                                     # [(role, seg)]
    routes = {}

    def lay(role, segs):
        routes[role] = segs
        laid.extend((role, s) for s in segs)

    # 1) anchor taps, canonical (798526e): exit PERPENDICULAR to the anchor's pad
    #    ROW (the force/current axis), run, one 90. Exiting "toward the target"
    #    along the row would plow through the shunt body -- measured wrong.
    anc_pads = [model.pad_at(pose, r, p)
                for role in model.tap_roles for r, p in model.role_pads[role] if r == model.anchor]
    row_x = (abs(anc_pads[0][0] - anc_pads[1][0]) >= abs(anc_pads[0][1] - anc_pads[1][1])) \
        if len(anc_pads) >= 2 else True
    for role in model.tap_roles:
        (r1, p1), (r2, p2) = model.role_pads[role]
        if r2 == model.anchor:
            (r1, p1), (r2, p2) = (r2, p2), (r1, p1)
        ax, ay, ahw, ahh = model.pad_at(pose, r1, p1)             # anchor pad
        tx, ty, _, _ = model.pad_at(pose, r2, p2)                 # target pad
        obstacles = model.foreign_pad_boxes(pose, role)
        if row_x:                                                 # pads run along X -> exit along Y
            exit_pt = (ax, ay + math.copysign(ahh + CLR_MM + TRACK_W, (ty - ay) or 1.0))
        else:
            exit_pt = (ax + math.copysign(ahw + CLR_MM + TRACK_W, (tx - ax) or 1.0), ay)
        stub = (ax, ay, exit_pt[0], exit_pt[1])
        last = None
        for l in _l_paths(exit_pt, (tx, ty)):
            try:
                lay(role, _check([stub, *l], role, obstacles, laid))
                break
            except Refusal as e:
                last = e
        else:
            raise Refusal(f"{role}: no canonical tap lays clear ({last})")

    # 2) internal chains + supply links: escape-L (synthesize_ideal_internal's
    #    algorithm, re-run on the variant geometry) hardened with a Manhattan
    #    DOGLEG fallback per hop -- both L orders, then 3-leg detours probing
    #    intermediate columns/rows, first clean candidate wins (deterministic).
    for role in sorted(model.internal_roles) + model.link_roles:
        pads = model.role_pads[role]
        if len(pads) < 2:
            continue
        obstacles = model.foreign_pad_boxes(pose, role)
        nodes = [_escape(model, pose, ref, pad, role, obstacles, laid) for ref, pad in pads]
        order, rem = [0], list(range(1, len(nodes)))
        while rem:
            lx, ly = nodes[order[-1]][1]
            nxt = min(rem, key=lambda i: (nodes[i][1][0] - lx) ** 2 + (nodes[i][1][1] - ly) ** 2)
            order.append(nxt)
            rem.remove(nxt)
        segs = []
        for k, idx in enumerate(order):
            (px, py), (ex, ey) = nodes[idx]
            segs.extend(_check([(px, py, ex, ey)], role, obstacles, laid))
            if k + 1 < len(order):
                nx, ny = nodes[order[k + 1]][1]
                segs.extend(_route_hop((ex, ey), (nx, ny), role, obstacles,
                                       laid + [(role, s) for s in segs]))
        lay(role, segs)
    return routes


def _escape(model, pose, ref, pad, role, obstacles, laid, esc=1.2):
    """Pick the pad's escape stub: outward from the part centre on the dominant
    axis first, then the other three directions -- the first stub whose endpoint
    and run clear all foreign copper wins. A blind dominant-axis escape can land
    the point ON a neighbour's pad row (measured: the 0603's +x escape vs the
    SOIC pad column), poisoning every hop into it."""
    px, py, _hw, _hh = model.pad_at(pose, ref, pad)
    cx, cy, _r = pose[ref]
    ddx, ddy = px - cx, py - cy
    prim = [(math.copysign(esc, ddx or 1.0), 0.0), (0.0, math.copysign(esc, ddy or 1.0))]
    if abs(ddx) < abs(ddy):
        prim.reverse()
    last = None
    for dx, dy in prim + [(-prim[0][0], -prim[0][1]), (-prim[1][0], -prim[1][1])]:
        e = (px + dx, py + dy)
        try:
            _check([(px, py, e[0], e[1])], role, obstacles, laid)
            return ((px, py), e)
        except Refusal as ex:
            last = ex
    raise Refusal(f"{role}: pad {ref}.{pad} has no clear escape ({last})")


GRID = 0.2                                       # hop-router raster (conservative vs the 0.325 keepaway)


def _route_hop(a, b, role, obstacles, laid):
    """One Manhattan hop a->b: the two L orders first (the fast common case), then a
    deterministic BFS on a GRID raster of the cell with all foreign copper inflated
    by clearance -- a real (tiny) maze router, so a legal channel is FOUND when one
    exists instead of enumerated-dogleg near-misses. The produced polyline is
    re-verified GEOMETRICALLY (_check) -- the raster is conservative, the geometry
    is the truth."""
    last = None
    for segs in _l_paths(a, b):
        try:
            return _check(list(segs), role, obstacles, laid)
        except Refusal as e:
            last = e
    # ---- raster BFS fallback ------------------------------------------------
    (ax, ay), (bx, by) = a, b
    xs = [ax, bx]
    ys = [ay, by]
    for (x0, x1, y0, y1) in obstacles:
        xs += [x0, x1]
        ys += [y0, y1]
    for _r, s in laid:
        xs += [s[0], s[2]]
        ys += [s[1], s[3]]
    m = 3.0
    gx0, gy0 = min(xs) - m, min(ys) - m
    nx = min(500, int((max(xs) + m - gx0) / GRID) + 1)
    ny = min(500, int((max(ys) + m - gy0) / GRID) + 1)

    def cell(px, py):
        return (min(ny - 1, max(0, int(round((py - gy0) / GRID)))),
                min(nx - 1, max(0, int(round((px - gx0) / GRID)))))

    blocked = bytearray(nx * ny)
    infl = CLR_MM + TRACK_W / 2.0
    for (x0, x1, y0, y1) in obstacles:
        i0 = max(0, int((x0 - infl - gx0) / GRID))
        i1 = min(nx - 1, int(math.ceil((x1 + infl - gx0) / GRID)))
        j0 = max(0, int((y0 - infl - gy0) / GRID))
        j1 = min(ny - 1, int(math.ceil((y1 + infl - gy0) / GRID)))
        for j in range(j0, j1 + 1):
            base = j * nx
            for i in range(i0, i1 + 1):
                blocked[base + i] = 1
    w2 = CLR_MM + TRACK_W
    for orole, s in laid:
        if orole == role:
            continue
        L = math.hypot(s[2] - s[0], s[3] - s[1])
        n = max(1, int(L / (GRID * 0.5)))
        for t in range(n + 1):
            px = s[0] + (s[2] - s[0]) * t / n
            py = s[1] + (s[3] - s[1]) * t / n
            i0 = max(0, int((px - w2 - gx0) / GRID))
            i1 = min(nx - 1, int(math.ceil((px + w2 - gx0) / GRID)))
            j0 = max(0, int((py - w2 - gy0) / GRID))
            j1 = min(ny - 1, int(math.ceil((py + w2 - gy0) / GRID)))
            for j in range(j0, j1 + 1):
                base = j * nx
                for i in range(i0, i1 + 1):
                    blocked[base + i] = 1
    sj, si = cell(ax, ay)
    tj, ti = cell(bx, by)
    for (j, i) in ((sj, si), (tj, ti)):          # endpoints are own-net copper: force-open
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                jj, ii = j + dj, i + di
                if 0 <= jj < ny and 0 <= ii < nx:
                    blocked[jj * nx + ii] = 0
    from collections import deque
    prev = {}
    dq = deque([(sj, si)])
    seen = bytearray(nx * ny)
    seen[sj * nx + si] = 1
    found = False
    while dq:
        j, i = dq.popleft()
        if (j, i) == (tj, ti):
            found = True
            break
        for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):   # fixed order: deterministic
            jj, ii = j + dj, i + di
            if 0 <= jj < ny and 0 <= ii < nx and not seen[jj * nx + ii] and not blocked[jj * nx + ii]:
                seen[jj * nx + ii] = 1
                prev[(jj, ii)] = (j, i)
                dq.append((jj, ii))
    if not found:
        raise Refusal(f"{role}: hop {a}->{b} has no clear path (maze exhausted; {last})")
    path = [(tj, ti)]
    while path[-1] != (sj, si):
        path.append(prev[path[-1]])
    path.reverse()
    pts = [(ax, ay)] + [(gx0 + i * GRID, gy0 + j * GRID) for (j, i) in path[1:-1]] + [(bx, by)]
    segs, k = [], 0
    while k < len(pts) - 1:                       # compress collinear runs into segments
        k2 = k + 1
        while k2 + 1 < len(pts):
            (x1_, y1_), (x2_, y2_), (x3_, y3_) = pts[k], pts[k2], pts[k2 + 1]
            if (abs(x1_ - x2_) < 1e-9 and abs(x2_ - x3_) < 1e-9) or \
               (abs(y1_ - y2_) < 1e-9 and abs(y2_ - y3_) < 1e-9):
                k2 += 1
            else:
                break
        segs.append((pts[k][0], pts[k][1], pts[k2][0], pts[k2][1]))
        k = k2
    return _check(segs, role, obstacles, laid)


# --------------------------------------------------------------------------
# Gates + score
# --------------------------------------------------------------------------
def _seg_len(s):
    return math.hypot(s[2] - s[0], s[3] - s[1])


def gates(model, pose, routes):
    """Hard gates; returns [] when clean, else named failures."""
    fails = []
    refs = list(model.parts)
    boxes = {r: model.courtyard(pose, r) for r in refs}
    for i, a in enumerate(refs):
        A = boxes[a]
        for b in refs[i + 1:]:
            B = boxes[b]
            if not (A[1] <= B[0] or B[1] <= A[0] or A[3] <= B[2] or B[3] <= A[2]):
                fails.append(f"overlap:{a}+{b}")
    tap_lens = {}
    for role in model.tap_roles:
        L = sum(_seg_len(s) for s in routes.get(role, ()))
        tap_lens[role] = L
        if L > TAP_LEN_MAX:
            fails.append(f"tap_long:{role}:{L:.1f}mm")
    if len(tap_lens) == 2:
        a, b = sorted(tap_lens.values())
        if b - a > TAP_SKEW_MAX:
            fails.append(f"tap_skew:{b - a:.2f}mm")
    # decoupler adjacency: each supply-link pair must stay tight (bypass loop)
    for role in model.link_roles:
        (r1, p1), (r2, p2) = model.role_pads[role]
        x1, y1, _, _ = model.pad_at(pose, r1, p1)
        x2, y2, _, _ = model.pad_at(pose, r2, p2)
        d = math.hypot(x2 - x1, y2 - y1)
        if d > DECOUPLER_MM:
            fails.append(f"decoupler_far:{role}:{d:.1f}mm")
    return fails


def extents(model, pose, routes):
    xs, ys = [], []
    for r in model.parts:
        x0, x1, y0, y1 = model.courtyard(pose, r)
        xs += [x0, x1]
        ys += [y0, y1]
    for segs in routes.values():
        for s in segs:
            xs += [s[0], s[2]]
            ys += [s[1], s[3]]
    return (max(xs) - min(xs), max(ys) - min(ys))


def score(model, pose, routes):
    """Lexicographic: pitch-axis extent, off-axis extent, copper length + tap skew.
    Smaller is better on every term."""
    w, h = extents(model, pose, routes)
    pitch = h if model.pitch_axis == "y" else w
    other = w if model.pitch_axis == "y" else h
    total = sum(_seg_len(s) for segs in routes.values() for s in segs)
    taps = [sum(_seg_len(s) for s in routes.get(r, ())) for r in model.tap_roles]
    skew = (max(taps) - min(taps)) if len(taps) >= 2 else 0.0
    return (round(pitch, 3), round(other, 3), round(total + 4.0 * skew, 3))


def _soft_cost(model, pose):
    """Search-time relaxation: overlap area + refusal penalty folded with the score
    so SA can walk through infeasible space; FINAL acceptance is strict gates."""
    refs = list(model.parts)
    boxes = {r: model.courtyard(pose, r) for r in refs}
    ov = 0.0
    for i, a in enumerate(refs):
        A = boxes[a]
        for b in refs[i + 1:]:
            B = boxes[b]
            dx = min(A[1], B[1]) - max(A[0], B[0])
            dy = min(A[3], B[3]) - max(A[2], B[2])
            if dx > 0 and dy > 0:
                ov += dx * dy
    try:
        routes = synth_routes(model, pose)
        ref_pen = 0.0
    except Refusal:
        routes, ref_pen = {}, 25.0
    if routes:
        g = gates(model, pose, routes)
        gate_pen = 8.0 * len(g)
        s = score(model, pose, routes)
        base = s[0] * 10.0 + s[1] * 2.0 + s[2] * 0.15
    else:
        gate_pen, base = 0.0, 60.0
    return 40.0 * ov + ref_pen + gate_pen + base, routes


# --------------------------------------------------------------------------
# The refinement search
# --------------------------------------------------------------------------
def refine(model, *, seed=0, starts=6, iters=3000, grid=0.1, jitter=2.0, verbose=False):
    """Multi-start SA over part poses (anchor fixed). Deterministic for a given
    (seed, starts, iters). Returns dict with baseline + best feasible variant."""
    import random
    movable = [r for r in model.parts if r != model.anchor]

    def snap(v):
        return round(v / grid) * grid

    def evaluate(pose):
        try:
            routes = synth_routes(model, pose)
        except Refusal as e:
            return None, [str(e)], None
        g = gates(model, pose, routes)
        return routes, g, (score(model, pose, routes) if not g else None)

    base_routes, base_gates, base_score = evaluate(model.base_pose)
    best = None                                   # (score, pose, routes)
    if base_score is not None:
        best = (base_score, dict(model.base_pose), base_routes)
    n_evals = 0

    for st in range(starts):
        rnd = random.Random((seed << 8) | st)
        pose = {r: model.base_pose[r] for r in model.parts}
        if st > 0:                                # scrambled starts explore; start 0 polishes baseline
            for r in movable:
                dx, dy, rot = pose[r]
                pose[r] = (snap(dx + rnd.uniform(-jitter, jitter)),
                           snap(dy + rnd.uniform(-jitter, jitter)),
                           (rot + 90.0 * rnd.randrange(4)) % 360.0)
        cost, _ = _soft_cost(model, pose)
        n_evals += 1
        T = 3.0
        for it in range(iters):
            r = rnd.choice(movable)
            old = pose[r]
            roll = rnd.random()
            if roll < 0.55:                        # grid jitter
                pose[r] = (snap(old[0] + rnd.choice((-1, 1)) * grid * rnd.randrange(1, 6)),
                           snap(old[1] + rnd.choice((-1, 1)) * grid * rnd.randrange(1, 6)), old[2])
            elif roll < 0.72:                      # rotate in place
                pose[r] = (old[0], old[1], (old[2] + rnd.choice((90.0, 180.0, 270.0))) % 360.0)
            elif roll < 0.92 and len(movable) >= 2:  # HUG: pack against another part's courtyard
                o = rnd.choice([x for x in model.parts if x != r])
                ob = model.courtyard(pose, o)
                rb = model.courtyard(pose, r)
                hw, hh = (rb[1] - rb[0]) / 2.0, (rb[3] - rb[2]) / 2.0
                side = rnd.randrange(4)
                cx0 = old[0] - (rb[0] + rb[1]) / 2.0   # origin-to-courtyard-centre offset
                cy0 = old[1] - (rb[2] + rb[3]) / 2.0
                if side == 0:
                    cc = (ob[0] - 0.1 - hw, rnd.uniform(ob[2], ob[3]))
                elif side == 1:
                    cc = (ob[1] + 0.1 + hw, rnd.uniform(ob[2], ob[3]))
                elif side == 2:
                    cc = (rnd.uniform(ob[0], ob[1]), ob[2] - 0.1 - hh)
                else:
                    cc = (rnd.uniform(ob[0], ob[1]), ob[3] + 0.1 + hh)
                pose[r] = (snap(cc[0] + cx0), snap(cc[1] + cy0), old[2])
            elif len(movable) >= 2:                # swap two parts' positions
                o = rnd.choice([x for x in movable if x != r])
                po = pose[o]
                pose[r], pose[o] = (po[0], po[1], old[2]), (old[0], old[1], po[2])
                nc, _ = _soft_cost(model, pose)
                n_evals += 1
                if nc > cost and rnd.random() >= math.exp((cost - nc) / max(T, 1e-3)):
                    pose[r], pose[o] = old, po
                else:
                    cost = nc
                T *= 0.9985
                continue
            nc, routes = _soft_cost(model, pose)
            n_evals += 1
            if nc > cost and rnd.random() >= math.exp((cost - nc) / max(T, 1e-3)):
                pose[r] = old
            else:
                cost = nc
                if routes:
                    g = gates(model, pose, routes)
                    if not g:
                        s = score(model, pose, routes)
                        if best is None or s < best[0]:
                            best = (s, dict(pose), routes)
            T *= 0.9985
        if verbose:
            print(f"  start {st}: cost {cost:.2f} best {best[0] if best else None}", file=sys.stderr)

    return {
        "baseline": {"pose": model.base_pose, "score": base_score, "gates": base_gates,
                     "routes": base_routes},
        "best": None if best is None else {"pose": best[1], "score": list(best[0]), "routes": best[2]},
        "improved": bool(best and base_score and list(best[0]) < list(base_score)),
        "n_evals": n_evals,
    }


def to_refined_template(model, pose, routes):
    """A NEW template (stamp-compatible) carrying the refined poses + synthesized
    copper. Internal AND routed-port copper rides internal_tracks (stamp resolves
    roles via net_roles either way and locks what it lays)."""
    t = json.loads(json.dumps(model.t))          # deep copy
    for ref, (dx, dy, rot) in pose.items():
        if ref == model.anchor:
            continue
        t["parts"][ref]["offset_mm"] = [round(dx, 4), round(dy, 4)]
        t["parts"][ref]["rot_delta"] = round(rot, 1) % 360.0
    t["internal_tracks"] = [
        {"net_role": role, "layer": "F.Cu",
         "start_rel_mm": [round(s[0], 4), round(s[1], 4)],
         "end_rel_mm": [round(s[2], 4), round(s[3], 4)], "width_mm": TRACK_W}
        for role, segs in routes.items() for s in segs
        if math.hypot(s[2] - s[0], s[3] - s[1]) > 1e-6]
    t["vias"] = []
    for bucket in ("ports", "internal_pads"):
        for role, spec in (t.get(bucket) or {}).items():
            for p in spec.get("pads", []):
                x, y, _hw, _hh = model.pad_at(pose, p["ref"], p["pad"])
                p["rel_mm"] = [round(x, 4), round(y, 4)]
    t.setdefault("meta", {})["refined"] = {"by": "cec_cell_refine", "single_face": True}
    return t


# --------------------------------------------------------------------------
# FINDER: repeated component groups from the netlist alone (copy-paste not
# required), + no-copper reporting when a board is available.
# --------------------------------------------------------------------------
def find_cells(netlist_path=None, nl=None, *, hub_degree=6, min_instances=2, min_parts=3):
    """Detect repeated functional groups: drop rail/GND nets and HUB parts (>=
    hub_degree distinct signal nets -- the MCU/connectors), take connected
    components of the remaining ref graph, fingerprint each by its (footprint,
    value) multiset, and report classes with >= min_instances isomorphic
    instances. Placement-independent by construction (netlist only)."""
    import cec_synth_pipeline as sp
    if nl is None:
        nl = sp.Netlist.from_file(netlist_path)
    ref_nets = defaultdict(set)
    for net, nodes in nl.nets.items():
        if sp._is_rail_net(net):
            continue
        for ref, _pin in nodes:
            ref_nets[ref].add(net)
    hubs = {r for r, ns in ref_nets.items() if len(ns) >= hub_degree}
    edges = defaultdict(set)
    for net, nodes in nl.nets.items():
        if sp._is_rail_net(net):
            continue
        refs = {r for r, _ in nodes if r not in hubs}
        for a in refs:
            edges[a] |= refs - {a}
    seen, comps = set(), []
    for r in sorted(edges):
        if r in seen:
            continue
        stack, comp = [r], set()
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp.add(x)
            stack.extend(edges[x] - comp)
        seen |= comp
        if len(comp) >= min_parts:
            comps.append(sorted(comp))
    classes = defaultdict(list)
    for comp in comps:
        fp = tuple(sorted((nl.comps[r].footprint, nl.comps[r].value) for r in comp if r in nl.comps))
        classes[fp].append(comp)
    out = []
    for fp, insts in classes.items():
        if len(insts) < min_instances:
            continue
        # anchor = the instance's INTERFACE part: most pads on boundary (non-rail nets
        # leaving the instance -- the shunt's force taps), courtyard area breaks ties.
        # The anchor's seat is externally dictated (lane/corridor), so it is the frame
        # the stamp pins; picking the interface-most part makes that true by choice.
        inst0 = set(insts[0])
        bcount = defaultdict(int)
        for net, nodes in nl.nets.items():
            if sp._is_rail_net(net):
                continue
            refs_on = {r for r, _ in nodes}
            if refs_on & inst0 and refs_on - inst0:
                for r, _p in nodes:
                    if r in inst0:
                        bcount[r] += 1
        anchor = max(insts[0], key=lambda r: (bcount.get(r, 0),
                                              _cy_area(nl.comps[r].footprint) if r in nl.comps else 0.0))
        out.append({"n": len(insts), "parts_per_instance": len(insts[0]),
                    "signature": [f"{v or '?'} ({f.split(':')[-1]})" for f, v in fp],
                    "instances": insts, "suggested_anchor": anchor})
    out.sort(key=lambda c: (-c["n"], -c["parts_per_instance"]))
    return out


def _cy_area(fp):
    try:
        x0, x1, y0, y1 = cec_pcb.courtyard_bbox(fp, 0.0, 0.0, 0.0)
        return (x1 - x0) * (y1 - y0)
    except Exception:                             # noqa: BLE001 -- unknown lib -> smallest
        return 0.0


def copper_coverage(board_path, instances, anchor_of):
    """CONTAINER leg: per instance, which routable roles carry extracted copper.
    Surfaces the owner's 'areas where there is no copper to extract'."""
    import cec_cell_extract as cx
    out = []
    for refs in instances:
        anchor = anchor_of(refs) if callable(anchor_of) else anchor_of
        t = cx.extract(board_path, refs, anchor_ref=anchor)
        have = {tr["net_role"] for tr in t.get("internal_tracks", [])}
        want = set((t.get("internal_pads") or {}).keys())
        want |= {r for r, s in (t.get("ports") or {}).items()
                 if len(s.get("pads", [])) >= 2 and r != "GND"}
        out.append({"anchor": anchor, "refs": refs,
                    "routed_roles": sorted(have), "unrouted_roles": sorted(want - have),
                    "coverage": (len(have & want), len(want))})
    return out


# --------------------------------------------------------------------------
# Micro-board emit + before/after panel (container legs)
# --------------------------------------------------------------------------
def emit_microboard(template, out_pcb, *, origin=(50.0, 50.0)):
    """Materialize ONE cell instance on a fresh board (real footprints, real nets,
    real tracks) so kicad-cli DRC + render judge it -- the acceptance tool is the
    REAL tool, never the search model's self-report."""
    import pcbnew
    board = pcbnew.NewBoard(out_pcb) if hasattr(pcbnew, "NewBoard") else pcbnew.CreateEmptyBoard()
    nets = {}
    for role, net in (template.get("net_roles") or {}).items():
        if net not in nets:
            ni = pcbnew.NETINFO_ITEM(board, net)
            board.Add(ni)
            nets[net] = ni
    pad_role = {}
    for bucket in ("ports", "internal_pads"):
        for role, spec in (template.get(bucket) or {}).items():
            for p in spec.get("pads", []):
                pad_role[(p["ref"], p["pad"])] = role
    ox, oy = origin
    allparts = dict(template["parts"])
    for ref, sp in allparts.items():
        nick, name = sp["footprint"].split(":")
        fp = pcbnew.FootprintLoad(os.path.dirname(cec_pcb.fp_path(nick, name)), name)
        if fp is None:
            raise RuntimeError(f"footprint load failed: {sp['footprint']}")
        fp.SetReference(ref)
        fp.SetValue(sp.get("value", ""))
        board.Add(fp)
        fp.SetPosition(pcbnew.VECTOR2I(int((ox + sp["offset_mm"][0]) * MM),
                                       int((oy + sp["offset_mm"][1]) * MM)))
        fp.SetOrientationDegrees(-float(sp.get("rot_delta", 0.0)))
        for pad in fp.Pads():
            role = pad_role.get((ref, pad.GetNumber()))
            if role and template["net_roles"].get(role) in nets:
                pad.SetNet(nets[template["net_roles"][role]])
    for tr in template.get("internal_tracks", []):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int((ox + tr["start_rel_mm"][0]) * MM),
                                   int((oy + tr["start_rel_mm"][1]) * MM)))
        t.SetEnd(pcbnew.VECTOR2I(int((ox + tr["end_rel_mm"][0]) * MM),
                                 int((oy + tr["end_rel_mm"][1]) * MM)))
        t.SetWidth(int(tr.get("width_mm", TRACK_W) * MM))
        t.SetLayer(board.GetLayerID(tr.get("layer", "F.Cu")))
        net = template["net_roles"].get(tr["net_role"])
        if net in nets:
            t.SetNet(nets[net])
        board.Add(t)
    # outline: extents + margin
    xs, ys = [], []
    for ref, sp in allparts.items():
        x0, x1, y0, y1 = cec_pcb.courtyard_bbox(sp["footprint"], sp["offset_mm"][0],
                                                sp["offset_mm"][1], sp.get("rot_delta", 0.0))
        xs += [x0, x1]
        ys += [y0, y1]
    for tr in template.get("internal_tracks", []):
        xs += [tr["start_rel_mm"][0], tr["end_rel_mm"][0]]
        ys += [tr["start_rel_mm"][1], tr["end_rel_mm"][1]]
    m = 2.0
    x0, x1, y0, y1 = min(xs) - m, max(xs) + m, min(ys) - m, max(ys) + m
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for i in range(4):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        ax, ay = corners[i]
        bx, by = corners[(i + 1) % 4]
        s.SetStart(pcbnew.VECTOR2I(int((ox + ax) * MM), int((oy + ay) * MM)))
        s.SetEnd(pcbnew.VECTOR2I(int((ox + bx) * MM), int((oy + by) * MM)))
        board.Add(s)
    pcbnew.SaveBoard(out_pcb, board)
    return out_pcb


def hand_baseline(model):
    """The honest 'before': score/metrics computed from the template's OWN extracted
    copper (the owner's hand routing), not from a re-synthesis of the hand placement.
    None when the template carries no copper (unrouted source cell)."""
    tracks = model.t.get("internal_tracks") or []
    if not tracks:
        return None, None
    routes = defaultdict(list)
    for tr in tracks:
        routes[tr["net_role"]].append((tr["start_rel_mm"][0], tr["start_rel_mm"][1],
                                       tr["end_rel_mm"][0], tr["end_rel_mm"][1]))
    routes = dict(routes)
    return score(model, model.base_pose, routes), _metrics_of(model, model.base_pose, routes)


def _metrics_of(model, pose, routes):
    w, h = extents(model, pose, routes)
    taps = {r: round(sum(_seg_len(s) for s in routes.get(r, ())), 2) for r in model.tap_roles}
    return {"extent_x_mm": round(w, 2), "extent_y_mm": round(h, 2),
            "pitch_extent_mm": round(h if model.pitch_axis == "y" else w, 2),
            "copper_mm": round(sum(_seg_len(s) for ss in routes.values() for s in ss), 2),
            "tap_lens_mm": taps,
            "tap_skew_mm": round(max(taps.values()) - min(taps.values()), 3) if len(taps) >= 2 else 0.0}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="blueprint-cell refinement loop")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find", help="detect repeated groups (netlist; +copper coverage with a board)")
    f.add_argument("source", help=".net netlist (host) or .kicad_pcb (container, adds coverage)")
    f.add_argument("--hub-degree", type=int, default=6)
    r = sub.add_parser("refine", help="extract -> refine -> emit before/after micro-boards")
    r.add_argument("--board", required=True)
    r.add_argument("--refs", required=True, help="comma-separated cell refs")
    r.add_argument("--anchor", required=True)
    r.add_argument("--pitch-axis", default="y", choices=("x", "y"))
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--starts", type=int, default=6)
    r.add_argument("--iters", type=int, default=3000)
    r.add_argument("--out", default=None)
    r.add_argument("--profile", action="store_true", help="cProfile the search leg")
    args = ap.parse_args(argv)

    if args.cmd == "find":
        if args.source.endswith(".kicad_pcb"):
            import pcbnew  # noqa: F401 -- container check
            import cec_synth_pipeline as sp
            b_dir = os.path.dirname(os.path.abspath(args.source))
            netp = [os.path.join(b_dir, f) for f in os.listdir(b_dir) if f.endswith(".net")]
            if netp:
                cells = find_cells(netp[0], hub_degree=args.hub_degree)
            else:  # derive a netlist view from the board itself
                nl = _nl_from_board(args.source)
                cells = find_cells(nl=nl, hub_degree=args.hub_degree)
            for c in cells:
                cov = copper_coverage(args.source, c["instances"], lambda refs, c=c: c["suggested_anchor"]
                                      if c["suggested_anchor"] in refs else refs[0])
                c["coverage"] = cov
        else:
            cells = find_cells(args.source, hub_degree=args.hub_degree)
        print(json.dumps(cells, indent=1))
        return 0

    import cec_cell_extract as cx
    refs = [x.strip() for x in args.refs.split(",") if x.strip()]
    out_dir = args.out or os.path.join("build", "cell-refine",
                                       os.path.basename(args.board).split(".")[0] + "-" + args.anchor)
    os.makedirs(out_dir, exist_ok=True)
    template = cx.extract(args.board, refs, anchor_ref=args.anchor)
    model = CellModel(template, pitch_axis=args.pitch_axis)

    prof = cProfile.Profile() if args.profile else None
    t0 = time.perf_counter()
    if prof:
        prof.enable()
    result = refine(model, seed=args.seed, starts=args.starts, iters=args.iters, verbose=True)
    if prof:
        prof.disable()
    wall = time.perf_counter() - t0

    hand_score, hand_m = hand_baseline(model)     # the owner's actual copper = the honest "before"
    base_m = _metrics_of(model, model.base_pose, result["baseline"]["routes"] or {}) \
        if result["baseline"]["routes"] else {"note": "baseline re-synthesis refused"}
    out = {"board": args.board, "refs": refs, "anchor": args.anchor,
           "hand_baseline_score": list(hand_score) if hand_score else None,
           "hand_baseline_metrics": hand_m,
           "resynth_baseline_score": result["baseline"]["score"],
           "resynth_baseline_metrics": base_m, "improved": result["improved"],
           "n_evals": result["n_evals"], "wall_s": round(wall, 2),
           "evals_per_s": round(result["n_evals"] / max(wall, 1e-9), 1)}
    if result["best"] and hand_score:
        out["improved_vs_hand"] = list(result["best"]["score"]) < list(hand_score)
    if result["best"]:
        best_pose = result["best"]["pose"]
        best_routes = result["best"]["routes"]
        out["best_score"] = result["best"]["score"]
        out["best_metrics"] = _metrics_of(model, best_pose, best_routes)
        refined = to_refined_template(model, best_pose, best_routes)
        with open(os.path.join(out_dir, "refined-template.json"), "w") as fh:
            json.dump(refined, fh, indent=1)
        emit_microboard(model.t, os.path.join(out_dir, "baseline.kicad_pcb"))
        emit_microboard(refined, os.path.join(out_dir, "refined.kicad_pcb"))
        out["microboards"] = [os.path.join(out_dir, "baseline.kicad_pcb"),
                              os.path.join(out_dir, "refined.kicad_pcb")]
    with open(os.path.join(out_dir, "refine-report.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    if prof:
        s = io.StringIO()
        pstats.Stats(prof, stream=s).sort_stats("cumulative").print_stats(18)
        open(os.path.join(out_dir, "profile.txt"), "w").write(s.getvalue())
        print(s.getvalue()[:2400])
    print(json.dumps(out, indent=1))
    return 0


def _nl_from_board(board_path):
    """Container helper: a Netlist-shaped view straight off a .kicad_pcb (for the
    finder when no .net is exported)."""
    import pcbnew
    import cec_synth_pipeline as sp
    b = pcbnew.LoadBoard(board_path)
    comps, nets = {}, defaultdict(list)
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        comps[ref] = sp.Comp(ref=ref, value=fp.GetValue(), footprint=fp.GetFPIDAsString())
        for p in fp.Pads():
            if p.GetNetname():
                nets[p.GetNetname()].append((ref, p.GetNumber()))
    return sp.Netlist(comps=comps, nets=dict(nets))


if __name__ == "__main__":
    sys.exit(main())
