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
DECOUPLER_ROUTED_MM = 5.0  # ...and the ROUTED bypass link must stay under this
                           # (efficacy = the actual loop, not just proximity;
                           # owner 2026-07-10 "decoupler distance and efficacy")


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

    def __init__(self, template, *, pitch_axis="y", envelope=None):
        self.t = template
        self.anchor = template["anchor"]["ref"]
        self.pitch_axis = pitch_axis
        # HARD ENVELOPE (owner 2026-07-11 "fit inside of a certain footprint in
        # a certain way"): anchor-frame (x0, x1, y0, y1) every part courtyard
        # must stay inside -- the FULL-REDESIGN rung's constraint. The
        # escalation ladder is: stamp blueprint -> renudge (small seat fixes) ->
        # refine() on the DESTINATION-extracted template with this envelope
        # (full redesign against the real board's context) -> human.
        self.envelope = tuple(envelope) if envelope else None
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
        # ---- boundary-copper STAND-INS (owner 2026-07-10): the pour/lane copper
        # serving the port nets, fixed in the anchor frame. F.Cu ones are routing
        # OBSTACLES for every other role and placement no-go for foreign pads; all
        # of them are emitted onto the microboards so DRC judges the real context.
        # (Single-face ruling: only F.Cu stand-ins constrain the router.)
        self.standins = list(self.t.get("standins") or [])
        self.standin_fcu = []                    # [(role, box)] routing/placement obstacles
        self.standin_all = []                    # [(role, box)] EVERY copper layer -- a
        for s in self.standins:                  # through-via barrel must clear all of it
            role = s["net_role"]
            box = None
            if s["kind"] == "track":
                x1, y1 = s["start_rel_mm"]
                x2, y2 = s["end_rel_mm"]
                hw = s.get("width_mm", TRACK_W) / 2.0
                box = (min(x1, x2) - hw, max(x1, x2) + hw, min(y1, y2) - hw, max(y1, y2) + hw)
                if s.get("layer") == "F.Cu":
                    self.standin_fcu.append((role, box))
            elif s["kind"] == "zone":
                box = tuple(s["box_rel_mm"])
                if s.get("layer") == "F.Cu":
                    self.standin_fcu.append((role, box))
            elif s["kind"] == "via":
                x, y = s["at_rel_mm"]
                r = s.get("dia_mm", 0.6) / 2.0
                box = (x - r, x + r, y - r, y + r)
                if "F.Cu" in (s.get("layers") or []):
                    self.standin_fcu.append((role, box))
            if box is not None:
                self.standin_all.append((role, box))

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
        """AABBs of every pad NOT on `role`, plus every F.Cu stand-in NOT on `role`
        (the clearance obstacles for that net)."""
        out = []
        for (ref, pad), r in self.pad_role.items():
            if r == role:
                continue
            x, y, hw, hh = self.pad_at(pose, ref, pad)
            out.append((x - hw, x + hw, y - hh, y + hh))
        out.extend(box for r, box in self.standin_fcu if r != role)
        return out

    def route_obstacles(self, pose, role):
        """Routing obstacles for `role` -- foreign copper, PLUS for TAP roles the
        SENSE DISCIPLINE set (owner 2026-07-11: the B4 LO tap doubled back
        through the shunt pad and the via field, all same-net so the router
        allowed it): a Kelvin tap that touches its own force copper after
        leaving the pad senses the lane, not the pad's inner edge -- so the
        role's own stand-ins AND its own anchor pad are obstacles too (the exit
        stub, which lies on the pad by construction, is checked against the
        foreign set only)."""
        out = self.foreign_pad_boxes(pose, role)
        if role in self.tap_roles:
            out.extend(box for r, box in self.standin_fcu if r == role)
            for ref, pad in self.role_pads[role]:
                if ref == self.anchor:
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
    routes, refused = synth_routes_partial(model, pose)
    if refused:
        raise Refusal(refused[0][1])
    return routes


def synth_routes_partial(model, pose, extra_obstacles=()):
    """Like synth_routes but keeps going past refusals: returns (routes, refused)
    where refused = [(role, reason)]. The GRADED form the search cost needs -- an
    all-or-nothing Refusal makes every infeasible pose cost the same, so SA sees
    a flat plateau and scrambled starts never claw back to feasibility (measured
    2026-07-10: 9/9 scrambled starts flat at cost 85 on the RS4 deep run).
    extra_obstacles: additional AABBs every net must clear (finalize_cell passes
    the GND via barrels so chains route around them)."""
    laid = []                                                     # [(role, seg)]
    routes = {}
    refused = []
    _synth_taps(model, pose, laid, routes, refused, extra_obstacles)
    _synth_chains(model, pose, laid, routes, refused, extra_obstacles)
    return routes, refused


def _synth_taps(model, pose, laid, routes, refused, extra_obstacles=()):
    def lay(role, segs):
        routes[role] = segs
        laid.extend((role, s) for s in segs)

    # 1) anchor taps -- TEXTBOOK KELVIN, owner-ruled 2026-07-10 ("perpendicular
    #    90 out of the inside of the shunt pad and then a 90 and then route to
    #    wherever after it comes inwards for a bit, the textbook"): the tap
    #    leaves the pad ACROSS its INNER edge (the sense point is the element
    #    side of the pad -- maximum accuracy, §6.8), runs INWARD along the row
    #    a short inset, takes ONE perpendicular 90, then routes to the target
    #    (L first, maze fallback). Textbook-or-refuse: a pose that cannot seat
    #    the textbook exit is infeasible -- no silent fallback geometry.
    anc_pads = [model.pad_at(pose, r, p)
                for role in model.tap_roles for r, p in model.role_pads[role] if r == model.anchor]
    row_x = (abs(anc_pads[0][0] - anc_pads[1][0]) >= abs(anc_pads[0][1] - anc_pads[1][1])) \
        if len(anc_pads) >= 2 else True
    acx, acy, _ar = pose[model.anchor]
    for role in model.tap_roles:
        (r1, p1), (r2, p2) = model.role_pads[role]
        if r2 == model.anchor:
            (r1, p1), (r2, p2) = (r2, p2), (r1, p1)
        ax, ay, ahw, ahh = model.pad_at(pose, r1, p1)             # anchor pad
        tx, ty, _, _ = model.pad_at(pose, r2, p2)                 # target pad
        obstacles = model.foreign_pad_boxes(pose, role) + list(extra_obstacles)
        post_obs = model.route_obstacles(pose, role) + list(extra_obstacles)
        if row_x:                                                 # pads run along X
            dir_in = math.copysign(1.0, (acx - ax) or 1.0)
            inner = ax + dir_in * ahw
            turns = [(inner + dir_in * ins, ay) for ins in (0.6, 1.0, 1.6)]
        else:
            dir_in = math.copysign(1.0, (acy - ay) or 1.0)
            inner = ay + dir_in * ahh
            turns = [(ax, inner + dir_in * ins) for ins in (0.6, 1.0, 1.6)]
        last = None
        done = False
        clear = CLR_MM + TRACK_W + 0.05                           # past the pad band + margin
        for turn in turns:
            if done:
                break
            stub = (ax, ay, turn[0], turn[1])                     # across the inner edge, inward
            try:
                _check([stub], role, obstacles, laid)
            except Refusal as e:
                last = e
                continue
            # second stroke: the perpendicular 90 must clear the SHUNT PAD BAND
            # (a 2512 pad face is ~3.4mm tall -- an L at the target's own y runs
            # straight across the other pad, measured); waypoint ladder = target
            # side first, then away
            for sgn in (math.copysign(1.0, ((ty - ay) if row_x else (tx - ax)) or 1.0),
                        -math.copysign(1.0, ((ty - ay) if row_x else (tx - ax)) or 1.0)):
                wp = (turn[0], ay + sgn * (ahh + clear)) if row_x else \
                     (ax + sgn * (ahw + clear), turn[1])
                perp = (turn[0], turn[1], wp[0], wp[1])
                try:
                    _check([stub], role, obstacles, laid)
                    _check([perp], role, post_obs, laid)
                except Refusal as e:
                    last = e
                    continue
                for l in _l_paths(wp, (tx, ty)):
                    try:
                        _check(list(l), role, post_obs, laid)
                        lay(role, [stub, perp, *l])
                        done = True
                        break
                    except Refusal as e:
                        last = e
                if not done:                                      # maze from the waypoint
                    try:
                        segs = _route_hop(wp, (tx, ty), role, post_obs,
                                          laid + [(role, stub), (role, perp)])
                        lay(role, [stub, perp] + segs)
                        done = True
                    except Refusal as e:
                        last = e
                if done:
                    break
        if not done:
            refused.append((role, f"{role}: textbook tap refused ({last})"))


def _synth_chains(model, pose, laid, routes, refused, extra_obstacles=()):
    def lay(role, segs):
        routes[role] = segs
        laid.extend((role, s) for s in segs)

    # 2) internal chains + supply links: escape-L (synthesize_ideal_internal's
    #    algorithm, re-run on the variant geometry) hardened with a Manhattan
    #    DOGLEG fallback per hop -- both L orders, then 3-leg detours probing
    #    intermediate columns/rows, first clean candidate wins (deterministic).
    for role in sorted(model.internal_roles) + model.link_roles:
        pads = model.role_pads[role]
        if len(pads) < 2:
            continue
        try:
            obstacles = model.foreign_pad_boxes(pose, role) + list(extra_obstacles)
            centers = [model.pad_at(pose, ref, pad)[:2] for ref, pad in pads]
            nodes = []
            for k, (ref, pad) in enumerate(pads):
                others = [c for j, c in enumerate(centers) if j != k]
                cen = (sum(c[0] for c in others) / len(others),
                       sum(c[1] for c in others) / len(others)) if others else None
                nodes.append(_escape(model, pose, ref, pad, role, obstacles, laid, toward=cen))
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
        except Refusal as e:
            refused.append((role, str(e)))
    return routes, refused


def _escape(model, pose, ref, pad, role, obstacles, laid, esc=1.2, toward=None):
    """Pick the pad's escape stub: candidate directions ordered TOWARD the
    chain's other pads when `toward` is given (a wrong-side escape poisons the
    hop into a long maze detour -- measured 2026-07-10: CF4.1 escaping DOWN
    away from its y1.6-band chain), else outward from the part centre on the
    dominant axis. First stub whose endpoint and run clear all foreign copper
    wins."""
    px, py, _hw, _hh = model.pad_at(pose, ref, pad)
    cx, cy, _r = pose[ref]
    ddx, ddy = px - cx, py - cy
    cand = [(math.copysign(esc, ddx or 1.0), 0.0), (0.0, math.copysign(esc, ddy or 1.0))]
    if abs(ddx) < abs(ddy):
        cand.reverse()
    cand = cand + [(-cand[0][0], -cand[0][1]), (-cand[1][0], -cand[1][1])]
    if toward is not None:
        tx, ty = toward
        cand.sort(key=lambda d: (px + d[0] - tx) ** 2 + (py + d[1] - ty) ** 2)
    last = None
    for dx, dy in cand:
        e = (px + dx, py + dy)
        try:
            _check([(px, py, e[0], e[1])], role, obstacles, laid)
            return ((px, py), e)
        except Refusal as ex:
            last = ex
    raise Refusal(f"{role}: pad {ref}.{pad} has no clear escape ({last})")


GRID = 0.1                                       # hop-router raster. 0.2 was too coarse: with the
                                                 # 0.45 clearance inflation it could not represent
                                                 # hand-tight ~0.33mm channel pitch, forcing wild
                                                 # detours around laid taps (measured 2026-07-10:
                                                 # IN chain 58.7mm vs the hand cell's 6.7mm)


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
    # domain = hop bbox + margin FIRST (the full obstacle field spans the fixed
    # lane stand-ins, ~10x the cells for paths that never go there; measured
    # 2026-07-10: suite 11s -> 163s at GRID 0.1 full-domain); full domain only
    # as the retry when the tight domain has no path.
    (ax, ay), (bx, by) = a, b
    for m, clip in ((4.0, True), (3.0, False)):
        xs = [ax, bx]
        ys = [ay, by]
        if not clip:
            for (x0, x1, y0, y1) in obstacles:
                xs += [x0, x1]
                ys += [y0, y1]
            for _r, s in laid:
                xs += [s[0], s[2]]
                ys += [s[1], s[3]]
        segs = _maze_domain(a, b, role, obstacles, laid, xs, ys, m)
        if segs is not None:
            return segs
    raise Refusal(f"{role}: hop {a}->{b} has no clear path (maze exhausted; {last})")


def _maze_domain(a, b, role, obstacles, laid, xs, ys, m):
    """One BFS attempt on the raster spanning xs/ys + margin m; None if no path
    (caller escalates to a wider domain)."""
    (ax, ay), (bx, by) = a, b
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
        return None                               # caller widens the domain / refuses
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
    try:
        return _check(segs, role, obstacles, laid)
    except Refusal:
        return None                               # raster/geometry mismatch: widen or refuse


# --------------------------------------------------------------------------
# Gates + score
# --------------------------------------------------------------------------
def _seg_len(s):
    return math.hypot(s[2] - s[0], s[3] - s[1])


def gates(model, pose, routes):
    """Hard gates; returns [] when clean, else named failures."""
    fails = []
    refs = list(model.parts)
    eps = 1e-6                                    # exactly-touching courtyards are LEGAL;
    boxes = {r: model.courtyard(pose, r) for r in refs}   # without eps a 4dp template
    for i, a in enumerate(refs):                  # round-trip flips the tie by 1e-16
        A = boxes[a]                              # (measured 2026-07-10)
        for b in refs[i + 1:]:
            B = boxes[b]
            if not (A[1] <= B[0] + eps or B[1] <= A[0] + eps or
                    A[3] <= B[2] + eps or B[3] <= A[2] + eps):
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
    # hard envelope: every courtyard inside the ruled box (full-redesign rung)
    if model.envelope:
        ex0, ex1, ey0, ey1 = model.envelope
        for r in refs:
            A = boxes[r]
            if A[0] < ex0 - eps or A[1] > ex1 + eps or A[2] < ey0 - eps or A[3] > ey1 + eps:
                fails.append(f"envelope:{r}")
    # stand-in encroachment: NO non-anchor pad may sit on/next to the fixed
    # pour/lane/via copper -- same-net included (owner 2026-07-10: RFL4 planted
    # on the LO lane + via fan "where it would be terrible" -- a via under a pad
    # is an assembly defect, and sensing off the force copper defeats Kelvin).
    # Only the ANCHOR is exempt: the shunt sits in its lane by design.
    for (ref, pad), r in model.pad_role.items():
        if ref == model.anchor:
            continue
        for srole, (bx0, bx1, by0, by1) in model.standin_fcu:
            x, y, hw, hh = model.pad_at(pose, ref, pad)
            if not (x + hw + CLR_MM <= bx0 or x - hw - CLR_MM >= bx1 or
                    y + hh + CLR_MM <= by0 or y - hh - CLR_MM >= by1):
                fails.append(f"standin_clash:{ref}.{pad}:{srole}")
    # decoupler adjacency + EFFICACY: the pair must sit tight AND the routed
    # bypass link must be short (proximity with a wandering route is a big loop)
    for role in model.link_roles:
        (r1, p1), (r2, p2) = model.role_pads[role]
        x1, y1, _, _ = model.pad_at(pose, r1, p1)
        x2, y2, _, _ = model.pad_at(pose, r2, p2)
        d = math.hypot(x2 - x1, y2 - y1)
        if d > DECOUPLER_MM:
            fails.append(f"decoupler_far:{role}:{d:.1f}mm")
        L = sum(_seg_len(s) for s in routes.get(role, ()))
        if L > DECOUPLER_ROUTED_MM:
            fails.append(f"decoupler_loop:{role}:{L:.1f}mm")
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


def parts_extents(model, pose):
    """The parts-courtyard envelope alone -- the cell's physical footprint claim."""
    xs, ys = [], []
    for r in model.parts:
        x0, x1, y0, y1 = model.courtyard(pose, r)
        xs += [x0, x1]
        ys += [y0, y1]
    return (max(xs) - min(xs), max(ys) - min(ys))


def score(model, pose, routes):
    """Lexicographic, smaller better: pitch-axis PARTS extent, off-axis PARTS
    extent, then scored copper + tap skew. Extents are parts-only (a window-
    clipped board trunk must not swing the comparison -- measured 2026-07-10);
    scored copper = TAP + INTERNAL roles only: the link role's copper is
    delivery-dependent board context (the hand cell's +3V3 arrives on a trunk
    shared by six lanes), so it is gated for adjacency (decoupler_far) but never
    scored. Tap length caps + skew keep long-tap escapes from gaming the
    parts-only extents."""
    w, h = parts_extents(model, pose)
    pitch = h if model.pitch_axis == "y" else w
    other = w if model.pitch_axis == "y" else h
    scored_roles = list(model.tap_roles) + sorted(model.internal_roles)
    total = sum(_seg_len(s) for r in scored_roles for s in routes.get(r, ()))
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
    routes, refused = synth_routes_partial(model, pose)
    # GRADED refusal (2026-07-10): each unroutable role costs 15 on top of a
    # flat 10, so "4 roles refused" > "1 role refused" > feasible -- SA can walk
    # back to feasibility instead of wandering a flat all-refused plateau.
    ref_pen = (10.0 + 15.0 * len(refused)) if refused else 0.0
    g = gates(model, pose, routes) if routes else []
    gate_pen = 8.0 * len(g)
    # one uniform base formula (an empty-routes special case made 5-refused
    # cost LESS than 4-refused: the missing copper term undercut the penalty)
    s = score(model, pose, routes if routes else {})
    base = s[0] * 10.0 + s[1] * 2.0 + s[2] * 0.15
    if refused:
        routes = None                             # partial routes never accepted as best
    return 40.0 * ov + ref_pen + gate_pen + base, routes


GND_VIA_DIA = 0.6
GND_VIA_DRILL = 0.3


def synth_gnd_vias(model, pose, routes, *, seed_vias=None, seed_stubs=None):
    """Grounding vias (owner 2026-07-10): every non-anchor GND pad gets a
    stitching via adjacent to it (short stub, via into the plane). Ladder:
    adjacent ring -> SHARE an existing via -> wide reach with a routed stub.
    seed_vias/seed_stubs: already-committed placements (finalize negotiation) --
    pads whose stub already exists are skipped, seeds constrain clearances, and
    the returned lists INCLUDE the seeds. Returns (vias, stubs, missing);
    missing is reported, never forced."""
    vias = list(seed_vias or [])
    stubs = list(seed_stubs or [])
    missing = []
    laid = [(r, s) for r, ss in routes.items() for s in ss] + [("GND", s) for s in stubs]
    r_via = GND_VIA_DIA / 2.0
    # VIA-IN-PAD guard (owner 2026-07-11): a barrel may not touch ANY pad --
    # same-net included (solder wicking is net-blind; only foreign pads were
    # checked before, so a GND via could land on the neighbouring GND pin)
    all_pads = []
    for (ref2, pad2), _r2 in model.pad_role.items():
        x, y, hw, hh = model.pad_at(pose, ref2, pad2)
        all_pads.append((x - hw, x + hw, y - hh, y + hh))
    for ref, pad in sorted(model.role_pads.get("GND", [])):
        if ref == model.anchor:
            continue
        px, py, hw, hh = model.pad_at(pose, ref, pad)
        if any(abs(s[0] - px) < 1e-6 and abs(s[1] - py) < 1e-6 for s in stubs):
            continue                              # already served by a seed stub
        cx, cy, _ = pose[ref]
        obstacles = model.foreign_pad_boxes(pose, "GND")
        placed = False
        # ring: outward from the part centre first, then the other directions,
        # at growing standoff
        dirs = sorted(((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)),
                      key=lambda d: -((px - cx) * d[0] + (py - cy) * d[1]))
        for standoff in (0.6, 0.8, 1.05):         # first rung sits 0.25 off the pad edge
                                                  # (0.55 left exactly CLR -- float-tie
                                                  # vs the new all-pads barrel guard)
            if placed:
                break
            for dx, dy in dirs:
                n = math.hypot(dx, dy)
                vx = px + dx / n * (max(hw, hh) + r_via + standoff - 0.35)
                vy = py + dy / n * (max(hw, hh) + r_via + standoff - 0.35)
                vbox = (vx - r_via, vx + r_via, vy - r_via, vy + r_via)
                stub = (px, py, vx, vy)
                # the barrel pierces EVERY layer: clear ALL pads (via-in-pad is
                # net-blind), F.Cu obstacles, AND all stand-in copper on any
                # layer (measured 2026-07-11: 3 GND vias landed on the B.Cu LO
                # lane -- real DRC shorts on a model-clean board)
                barrel_obs = all_pads + obstacles + \
                    [b for r_, b in model.standin_all if r_ != "GND"]
                clear = all(vbox[1] + CLR_MM <= b[0] or vbox[0] - CLR_MM >= b[1] or
                            vbox[3] + CLR_MM <= b[2] or vbox[2] - CLR_MM >= b[3]
                            for b in barrel_obs)
                clear = clear and all(
                    _seg_box_clear((v["at_rel_mm"][0], v["at_rel_mm"][1],
                                    v["at_rel_mm"][0], v["at_rel_mm"][1]), vbox,
                                   CLR_MM + r_via) for v in vias)
                clear = clear and all(_seg_box_clear(s, vbox, CLR_MM + TRACK_W / 2.0)
                                      for _r, s in laid)
                if not clear:
                    continue
                try:
                    _check([stub], "GND", obstacles, laid)
                except Refusal:
                    continue
                vias.append({"at_rel_mm": [round(vx, 4), round(vy, 4)],
                             "dia_mm": GND_VIA_DIA, "drill_mm": GND_VIA_DRILL})
                stubs.append(stub)
                laid.append(("GND", stub))
                placed = True
                break
        if not placed:
            # rung 2: SHARE an already-placed GND via (adjacent pin clusters --
            # the INA240's 4 GND-role pins do not need 4 barrels)
            for v in vias:
                try:
                    segs = _route_hop((px, py), tuple(v["at_rel_mm"]), "GND", obstacles, laid)
                except Refusal:
                    continue
                stubs.extend(segs)
                laid.extend(("GND", s) for s in segs)
                placed = True
                break
        if not placed:
            # rung 3: WIDE REACH -- the lane band under a compacted cell blocks
            # every adjacent barrel (measured 2026-07-11: the INA240 got NO
            # ground via, only the bypass cap's); reach past the band with a
            # ROUTED stub to a barrel-legal site
            barrel_obs = all_pads + obstacles + \
                [b for r_, b in model.standin_all if r_ != "GND"]
            for R in (1.6, 2.2, 2.8, 3.4):
                if placed:
                    break
                for k in range(12):
                    a = 2.0 * math.pi * k / 12.0
                    vx, vy = px + R * math.cos(a), py + R * math.sin(a)
                    vbox = (vx - r_via, vx + r_via, vy - r_via, vy + r_via)
                    if not all(vbox[1] + CLR_MM <= b[0] or vbox[0] - CLR_MM >= b[1] or
                               vbox[3] + CLR_MM <= b[2] or vbox[2] - CLR_MM >= b[3]
                               for b in barrel_obs):
                        continue
                    if not all(math.hypot(v["at_rel_mm"][0] - vx, v["at_rel_mm"][1] - vy)
                               >= GND_VIA_DIA + CLR_MM for v in vias):
                        continue
                    if not all(_seg_box_clear(s, vbox, CLR_MM + TRACK_W / 2.0)
                               for _r, s in laid):
                        continue
                    try:
                        segs = _route_hop((px, py), (vx, vy), "GND", obstacles, laid)
                    except Refusal:
                        continue
                    vias.append({"at_rel_mm": [round(vx, 4), round(vy, 4)],
                                 "dia_mm": GND_VIA_DIA, "drill_mm": GND_VIA_DRILL})
                    stubs.extend(segs)
                    laid.extend(("GND", s) for s in segs)
                    placed = True
                    break
        if not placed:
            missing.append(f"{ref}.{pad}")
    return vias, stubs, missing


def finalize_cell(model, pose, *, mitre=True):
    """Acceptance-time synthesis in DESIGNER ORDER (owner 2026-07-11: C13's
    bypass via was crowded out because chains routed first): TAPS -> GND VIAS
    (first claim on the space next to their pads) -> CHAINS (routing around the
    via barrels) -> lint -> mitre. Returns (routes, gvias, gstubs, gmissing) or
    falls back to chains-first order when via-aware chains refuse (reported via
    gmissing sentinel, never silently)."""
    laid, routes, refused = [], {}, []
    _synth_taps(model, pose, laid, routes, refused)
    if refused:
        raise Refusal(refused[0][1])
    gvias, gstubs, gmissing = synth_gnd_vias(model, pose, routes)
    r_via = GND_VIA_DIA / 2.0
    via_boxes = [(v["at_rel_mm"][0] - r_via, v["at_rel_mm"][0] + r_via,
                  v["at_rel_mm"][1] - r_via, v["at_rel_mm"][1] + r_via) for v in gvias]
    laid2 = list(laid) + [("GND", s) for s in gstubs]
    routes2, refused2 = dict(routes), []
    _synth_chains(model, pose, laid2, routes2, refused2, via_boxes)
    if refused2:
        # NEGOTIATION (bounded): a chain lost its corridor to a via/stub -- drop
        # the via nearest the refused hop, re-run chains, then re-seat the
        # dropped pad's via against the final field (measured 2026-07-11: C13's
        # vias-first stub walled off IN_N's only passage at the B5 pose)
        reason = refused2[0][1]
        import re as _re
        mm_ = _re.findall(r"\((-?[\d.]+), (-?[\d.]+)\)", reason)
        hop_mid = ((float(mm_[0][0]) + float(mm_[1][0])) / 2.0,
                   (float(mm_[0][1]) + float(mm_[1][1])) / 2.0) if len(mm_) >= 2 else (0.0, 0.0)
        order = sorted(range(len(gvias)),
                       key=lambda i: (gvias[i]["at_rel_mm"][0] - hop_mid[0]) ** 2 +
                                     (gvias[i]["at_rel_mm"][1] - hop_mid[1]) ** 2)
        settled = False
        for drop in order:
            kept = [v for i, v in enumerate(gvias) if i != drop]
            kept_boxes = [(v["at_rel_mm"][0] - r_via, v["at_rel_mm"][0] + r_via,
                           v["at_rel_mm"][1] - r_via, v["at_rel_mm"][1] + r_via) for v in kept]
            # stubs whose far end is the dropped via go too
            dv = gvias[drop]["at_rel_mm"]
            kept_stubs = [s for s in gstubs
                          if math.hypot(s[2] - dv[0], s[3] - dv[1]) > 1e-6]
            laid3 = list(laid) + [("GND", s) for s in kept_stubs]
            routes3, refused3 = dict(routes), []
            _synth_chains(model, pose, laid3, routes3, refused3, kept_boxes)
            if refused3:
                continue
            gvias, gstubs, gmissing = synth_gnd_vias(model, pose, routes3,
                                                     seed_vias=kept, seed_stubs=kept_stubs)
            via_boxes = [(v["at_rel_mm"][0] - r_via, v["at_rel_mm"][0] + r_via,
                          v["at_rel_mm"][1] - r_via, v["at_rel_mm"][1] + r_via) for v in gvias]
            routes2 = routes3
            settled = True
            break
        if not settled:
            # full fallback: chains-first, via ladder fights the routed field
            routes3, refused3 = synth_routes_partial(model, pose)
            if refused3:
                raise Refusal(refused3[0][1])
            gvias, gstubs, gmissing = synth_gnd_vias(model, pose, routes3)
            gmissing = gmissing + ["(fallback:chains-first)"]
            via_boxes = [(v["at_rel_mm"][0] - r_via, v["at_rel_mm"][0] + r_via,
                          v["at_rel_mm"][1] - r_via, v["at_rel_mm"][1] + r_via) for v in gvias]
            routes2 = routes3
    gnd_laid = [("GND", s) for s in gstubs]
    routes2 = lint_routes(model, pose, routes2, extra_obstacles=via_boxes, extra_laid=gnd_laid)
    if mitre:
        routes2 = mitre_routes(model, pose, routes2, extra_obstacles=via_boxes, extra_laid=gnd_laid)
    return routes2, gvias, gstubs, gmissing


def lint_routes(model, pose, routes, *, extra_obstacles=(), extra_laid=()):
    """Route LINT (owner 2026-07-10: 'strange double-backs'): shortcut pass over
    each role's contiguous chains -- replace any sub-chain with a straight
    (H/V/45 only) or L path when it lays clear and is strictly shorter. Corners
    that other segments arrive at (junctions) are never cut. Runs to fixpoint;
    deterministic. Apply BEFORE mitre (mitre then rounds the surviving 90s)."""
    out = {}
    all_other = [(r, s) for r, ss in routes.items() for s in ss] + list(extra_laid)
    for role in sorted(routes):
        segs = [tuple(s) for s in routes[role]]
        obstacles = model.route_obstacles(pose, role) + list(extra_obstacles)
        # TEXTBOOK PROTECTION (owner 2026-07-10: B3's lint shortcut the inward
        # exit into a direct outward run): a tap's first two strokes -- the
        # inner-edge exit and the perpendicular 90 -- are load-bearing geometry,
        # never lint fodder. They stay at indices 0/1 because replacements
        # below never start before i0.
        i0 = 2 if role in model.tap_roles else 0
        improved = True
        while improved:
            improved = False
            n = len(segs)
            for i in range(i0, n):
                if improved:
                    break
                for j in range(i + 1, n):
                    if not all(abs(segs[k][2] - segs[k + 1][0]) < 1e-6 and
                               abs(segs[k][3] - segs[k + 1][1]) < 1e-6 for k in range(i, j)):
                        break                     # chain broken: later j can't reconnect
                    interior = [(segs[k][2], segs[k][3]) for k in range(i, j)]
                    if any(sum(1 for s in segs
                               if (abs(s[0] - px) < 1e-6 and abs(s[1] - py) < 1e-6) or
                                  (abs(s[2] - px) < 1e-6 and abs(s[3] - py) < 1e-6)) != 2
                           for px, py in interior):
                        continue                  # junction inside: not ours to cut
                    a = (segs[i][0], segs[i][1])
                    b = (segs[j][2], segs[j][3])
                    cur_len = sum(_seg_len(s) for s in segs[i:j + 1])
                    straight = (a[0], a[1], b[0], b[1])
                    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
                    cands = []
                    if dx < 1e-6 or dy < 1e-6 or abs(dx - dy) < 1e-6:
                        cands.append((straight,))  # H, V, or true 45 only
                    cands.extend(_l_paths(a, b))
                    laid = [(r, s) for r, s in all_other if r != role]
                    for rep in cands:
                        rep = [s for s in rep if _seg_len(s) > 1e-9]
                        if sum(_seg_len(s) for s in rep) >= cur_len - 0.05:
                            continue
                        try:
                            _check(rep, role, obstacles, laid)
                        except Refusal:
                            continue
                        segs = segs[:i] + [tuple(s) for s in rep] + segs[j + 1:]
                        improved = True
                        break
                    if improved:
                        break
        out[role] = segs
        all_other = [(r, s) for r, ss in {**routes, **out}.items() for s in ss] + list(extra_laid)
    return out


# --------------------------------------------------------------------------
# 45-degree corner mitre (post-acceptance finishing; owner: "only routing 90s")
# --------------------------------------------------------------------------
def mitre_routes(model, pose, routes, *, d_max=0.8, d_min=0.2,
                 extra_obstacles=(), extra_laid=()):
    """Chamfer 90-degree corners of the ACCEPTED routes into 45s (hand-routing
    idiom). The in-loop router stays Manhattan for speed; this pass runs once on
    the result. Each chamfer is re-verified geometrically against the foreign
    copper and every other segment -- a chamfer that will not lay clear keeps
    its 90 (improve-never-force). Copper length only ever shrinks."""
    out = {}
    all_other = [(role, s) for role, segs in routes.items() for s in segs] + list(extra_laid)
    for role in sorted(routes):
        segs = [list(s) for s in routes[role]]
        obstacles = model.route_obstacles(pose, role) + list(extra_obstacles)
        # TEXTBOOK PROTECTION: a tap's pad-exit corner and its perpendicular 90
        # stay SQUARE (owner: "the textbook perpendicular 90"; B3's mitre had
        # chamfered them into 45 ramps). Segs 0/1 = stub + perp; skipping
        # corners before index 2 protects both corners, and chamfer insertions
        # all land at i >= 2 so the indices hold.
        c0 = 2 if role in model.tap_roles else 0
        changed = True
        while changed:
            changed = False
            for i in range(c0, len(segs) - 1):
                a, b = segs[i], segs[i + 1]
                # corner = a's end meets b's start, one horizontal + one vertical
                if abs(a[2] - b[0]) > 1e-9 or abs(a[3] - b[1]) > 1e-9:
                    continue
                ah = abs(a[1] - a[3]) < 1e-9
                bh = abs(b[1] - b[3]) < 1e-9
                if ah == bh:
                    continue
                # T-junction guard: only a TRUE 2-segment corner may be cut --
                # shortening both legs of a corner a third segment also lands on
                # leaves that branch dangling (measured 2026-07-10: IN4_P split
                # into two islands on the real board's connectivity)
                px_, py_ = a[2], a[3]
                arrivals = sum(1 for s in segs
                               if (abs(s[0] - px_) < 1e-6 and abs(s[1] - py_) < 1e-6) or
                                  (abs(s[2] - px_) < 1e-6 and abs(s[3] - py_) < 1e-6))
                if arrivals != 2:
                    continue
                la = math.hypot(a[2] - a[0], a[3] - a[1])
                lb = math.hypot(b[2] - b[0], b[3] - b[1])
                d = min(d_max, 0.4 * la, 0.4 * lb)
                if d < d_min:
                    continue
                ax = a[2] - d * math.copysign(1.0, a[2] - a[0]) if ah else a[2]
                ay = a[3] if ah else a[3] - d * math.copysign(1.0, a[3] - a[1])
                bx = b[0] + d * math.copysign(1.0, b[2] - b[0]) if bh else b[0]
                by = b[1] if bh else b[1] + d * math.copysign(1.0, b[3] - b[1])
                cham = (ax, ay, bx, by)
                laid = [(r, s) for r, s in all_other if r != role]
                try:
                    _check([cham], role, obstacles, laid)
                except Refusal:
                    continue
                a[2], a[3] = ax, ay
                b[0], b[1] = bx, by
                segs.insert(i + 1, list(cham))
                changed = True
                break
        out[role] = [tuple(s) for s in segs]
        all_other = [(r, s) for r, ss in {**routes, **out}.items() for s in ss] + list(extra_laid)
    return out


def _slide_to_contact(model, pose, r, axis, direction, gap=0.1):
    """Max slide of part r along axis (+/-1) before its courtyard contacts another
    part's courtyard or an F.Cu stand-in, minus `gap`. Returns the new (dx, dy)
    or None when there is no room (or nothing to slide toward within 25mm).
    THE compaction move (owner 2026-07-10: 'not moving placements at all to
    compact it down') -- jitter+hug alone rarely walk into tight packings before
    the overlap penalty rejects the path; sliding TO contact jumps straight to
    the packed frontier and lets routing/gates veto."""
    rb = model.courtyard(pose, r)
    lo, hi = (rb[2], rb[3]) if axis == 0 else (rb[0], rb[1])      # perpendicular span
    lead = rb[1] if (axis == 0 and direction > 0) else rb[0] if axis == 0 \
        else rb[3] if direction > 0 else rb[2]
    limit = 25.0
    solids = [model.courtyard(pose, o) for o in model.parts if o != r]
    solids += [box for _role, box in model.standin_fcu]
    for B in solids:
        blo, bhi = (B[2], B[3]) if axis == 0 else (B[0], B[1])
        if bhi <= lo or blo >= hi:                                # no perpendicular overlap
            continue
        near = (B[0] if direction > 0 else B[1]) if axis == 0 else \
               (B[2] if direction > 0 else B[3])
        far = (B[1] if direction > 0 else B[0]) if axis == 0 else \
              (B[3] if direction > 0 else B[2])
        if (far - lead) * direction <= 0:
            continue                                              # entirely behind: not in path
        limit = min(limit, max((near - lead) * direction - gap, 0.0))
    if limit <= 1e-6 or limit >= 25.0:
        return None
    dx, dy, rot = pose[r]
    return (dx + direction * limit, dy, rot) if axis == 0 else (dx, dy + direction * limit, rot)


# --------------------------------------------------------------------------
# The refinement search
# --------------------------------------------------------------------------
def refine(model, *, seed=0, starts=6, iters=3000, grid=0.1, jitter=2.0,
           budget_evals=None, polish_frac=0.3, polish_grid=0.025,
           acceptance_check=None, verbose=False):
    """Multi-start SA over part poses (anchor fixed). Deterministic for a given
    (seed, starts, iters[, budget_evals]). budget_evals (owner 2026-07-10: a
    refined blueprint amortizes over N stamps -> spend much more) overrides
    `starts`: scrambled starts keep launching until ~(1-polish_frac) of the
    budget is spent, then a fine-grid POLISH stage (jitter/hug only, low
    temperature, polish_grid snap) walks the best pose with the remainder.
    Budget is counted in EVALS, not wall time, so runs stay deterministic and
    reproducible. Returns dict with baseline + best feasible variant."""
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

    def accepts(p, routes):
        """acceptance_check hook (owner 2026-07-11: a pose that cannot ground
        every GND pad must never win, however good its score)."""
        return acceptance_check is None or acceptance_check(p, routes)

    base_routes, base_gates, base_score = evaluate(model.base_pose)
    best = None                                   # (score, pose, routes)
    if base_score is not None and accepts(model.base_pose, base_routes):
        best = (base_score, dict(model.base_pose), base_routes)
    n_evals = 0
    explore_budget = None if budget_evals is None else int(budget_evals * (1.0 - polish_frac))

    st = -1
    while True:
        st += 1
        if budget_evals is None:
            if st >= starts:
                break
        elif n_evals >= explore_budget:
            break
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
            if roll < 0.45:                        # grid jitter
                pose[r] = (snap(old[0] + rnd.choice((-1, 1)) * grid * rnd.randrange(1, 6)),
                           snap(old[1] + rnd.choice((-1, 1)) * grid * rnd.randrange(1, 6)), old[2])
            elif roll < 0.60:                      # rotate in place
                pose[r] = (old[0], old[1], (old[2] + rnd.choice((90.0, 180.0, 270.0))) % 360.0)
            elif roll < 0.78:                      # COMPACT: slide to contact toward the anchor
                axis = rnd.randrange(2)
                direction = -1.0 if (old[axis] > 0) else 1.0      # anchor sits at (0,0)
                slid = _slide_to_contact(model, pose, r, axis, direction)
                if slid is None:
                    continue
                pose[r] = slid                    # NOT snapped: snapping can round back into contact
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
                        if (best is None or s < best[0]) and accepts(pose, routes):
                            best = (s, dict(pose), routes)
            T *= 0.9985
        if verbose:
            print(f"  start {st}: cost {cost:.2f} best {best[0] if best else None}", file=sys.stderr)

    # ---- POLISH: fine-grid descent around the incumbent (budgeted runs only).
    # Jitter/hug moves at polish_grid snap, cool temperature -- the coarse
    # explorer finds the basin, this walks to its floor.
    if budget_evals is not None and best is not None:
        rnd = random.Random((seed << 8) | 0xF1)
        pose = dict(best[1])
        cost, _ = _soft_cost(model, pose)
        n_evals += 1
        T = 0.4
        while n_evals < budget_evals:
            r = rnd.choice(movable)
            old = pose[r]
            if rnd.random() < 0.3:                # polish compacts too, not just dithers
                axis = rnd.randrange(2)
                direction = -1.0 if (old[axis] > 0) else 1.0
                slid = _slide_to_contact(model, pose, r, axis, direction)
                if slid is None:
                    continue
                pose[r] = slid
            else:
                step = polish_grid * rnd.randrange(1, 5)
                pose[r] = (round((old[0] + rnd.choice((-1, 1)) * step) / polish_grid) * polish_grid,
                           round((old[1] + rnd.choice((-1, 1)) * step) / polish_grid) * polish_grid,
                           old[2])
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
                        if (best is None or s < best[0]) and accepts(pose, routes):
                            best = (s, dict(pose), routes)
            T *= 0.9992
        if verbose:
            print(f"  polish: best {best[0]}", file=sys.stderr)

    return {
        "baseline": {"pose": model.base_pose, "score": base_score, "gates": base_gates,
                     "routes": base_routes},
        "best": None if best is None else {"pose": best[1], "score": list(best[0]), "routes": best[2]},
        "improved": bool(best and base_score and list(best[0]) < list(base_score)),
        "n_evals": n_evals,
    }


def renudge(model, blueprint_pose, *, seed=0, budget_evals=1500, max_shift=0.8, grid=0.05):
    """STAMP-TIME NUDGE (owner 2026-07-10: "send it back to the blueprint
    factory to make small nudges as needed to build around the actual needs of
    the board"): constrained re-refinement around a blueprint pose against THIS
    model's context -- build the CellModel from a template whose stand-ins were
    extracted at the DESTINATION instance, so the search sees the real board's
    needs. Small moves only (slides + jitter capped at max_shift from the
    blueprint, no rotation, no swaps): the blueprint's character is preserved,
    its seating adapts. Returns {pose, routes, score} of the best gate-clean
    variant, or None -- the caller escalates (never force-fits)."""
    import random
    movable = [r for r in model.parts if r != model.anchor]
    rnd = random.Random(seed)
    best = None

    def accept(p):
        nonlocal best
        try:
            routes = synth_routes(model, p)
        except Refusal:
            return
        if gates(model, p, routes):
            return
        s = score(model, p, routes)
        if best is None or s < best["score"]:
            best = {"pose": dict(p), "routes": routes, "score": s}

    pose = {r: tuple(blueprint_pose[r]) for r in model.parts}
    accept(pose)
    cost, _ = _soft_cost(model, pose)
    n = 2
    T = 0.5
    while n < budget_evals:
        r = rnd.choice(movable)
        old = pose[r]
        if rnd.random() < 0.35:
            axis = rnd.randrange(2)
            direction = -1.0 if old[axis] > 0 else 1.0
            cand = _slide_to_contact(model, pose, r, axis, direction)
        else:
            step = grid * rnd.randrange(1, max(2, int(max_shift / grid) + 1))
            cand = (old[0] + rnd.choice((-1, 1)) * step,
                    old[1] + rnd.choice((-1, 1)) * step, old[2])
        bp = blueprint_pose[r]
        if cand is None or abs(cand[0] - bp[0]) > max_shift or abs(cand[1] - bp[1]) > max_shift:
            continue                              # nudges stay nudges
        pose[r] = cand
        nc, routes = _soft_cost(model, pose)
        n += 1
        if nc > cost and rnd.random() >= math.exp((cost - nc) / max(T, 1e-3)):
            pose[r] = old
        else:
            cost = nc
            if routes:
                g = gates(model, pose, routes)
                if not g:
                    s = score(model, pose, routes)
                    if best is None or s < best["score"]:
                        best = {"pose": dict(pose), "routes": routes, "score": s}
        T *= 0.999
    return best


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
    t["port_tracks"] = []                        # synthesized tap/link copper supersedes
    t["vias"] = []
    # prune stand-ins the COMPACTED cell no longer interacts with -- context
    # vias/stubs left floating in empty space read as strays on the emitted
    # board (owner 2026-07-10). Zones (pours) always stay.
    xs, ys = [], []
    for r in model.parts:
        x0, x1, y0, y1 = model.courtyard(pose, r)
        xs += [x0, x1]
        ys += [y0, y1]
    for segs in routes.values():
        for s in segs:
            xs += [s[0], s[2]]
            ys += [s[1], s[3]]
    env = (min(xs) - 1.5, max(xs) + 1.5, min(ys) - 1.5, max(ys) + 1.5)

    def _sb(s):
        if s["kind"] == "track":
            return (min(s["start_rel_mm"][0], s["end_rel_mm"][0]),
                    max(s["start_rel_mm"][0], s["end_rel_mm"][0]),
                    min(s["start_rel_mm"][1], s["end_rel_mm"][1]),
                    max(s["start_rel_mm"][1], s["end_rel_mm"][1]))
        if s["kind"] == "via":
            x, y = s["at_rel_mm"]
            r_ = s.get("dia_mm", 0.6) / 2.0
            return (x - r_, x + r_, y - r_, y + r_)
        return tuple(s["box_rel_mm"])
    t["standins"] = [s for s in t.get("standins", [])
                     if s["kind"] == "zone" or
                     not (_sb(s)[1] < env[0] or _sb(s)[0] > env[1] or
                          _sb(s)[3] < env[2] or _sb(s)[2] > env[3])]
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
        # +rot_delta: KiCad's y-down RotatePoint IS this module's _rot(+theta);
        # the old -rot emitted 90/270-rotated parts with their pads TRANSPOSED
        # vs the model (masked on 0/180-only cells; caught coordinate-by-
        # coordinate on the first searched pose that rotated parts, 2026-07-10:
        # 9 real DRC shorts on a "gates-clean" refined board)
        fp.SetOrientationDegrees(float(sp.get("rot_delta", 0.0)))
        for pad in fp.Pads():
            role = pad_role.get((ref, pad.GetNumber()))
            if role and template["net_roles"].get(role) in nets:
                pad.SetNet(nets[template["net_roles"][role]])
    for tr in (list(template.get("internal_tracks", [])) +
               list(template.get("port_tracks", []))):
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
    # grounding vias (owner 2026-07-10) -- their stubs ride internal_tracks
    gnd_net = (template.get("net_roles") or {}).get("GND")
    for gv in template.get("gnd_vias", []):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int((ox + gv["at_rel_mm"][0]) * MM),
                                      int((oy + gv["at_rel_mm"][1]) * MM)))
        v.SetDrill(int(gv.get("drill_mm", GND_VIA_DRILL) * MM))
        v.SetWidth(int(gv.get("dia_mm", GND_VIA_DIA) * MM))
        if gnd_net in nets:
            v.SetNet(nets[gnd_net])
        board.Add(v)
    # boundary-copper stand-ins: the fixed pour/lane context, as REAL copper so
    # DRC judges taps landing on it and clearance to it (owner ask 2026-07-10)
    zones_to_fill = []
    for s in template.get("standins", []):
        net = template["net_roles"].get(s["net_role"])
        ni = nets.get(net)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(board, net or s["net_role"])
            board.Add(ni)
            nets[net] = ni
        if s["kind"] == "track":
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int((ox + s["start_rel_mm"][0]) * MM),
                                       int((oy + s["start_rel_mm"][1]) * MM)))
            t.SetEnd(pcbnew.VECTOR2I(int((ox + s["end_rel_mm"][0]) * MM),
                                     int((oy + s["end_rel_mm"][1]) * MM)))
            t.SetWidth(int(s.get("width_mm", TRACK_W) * MM))
            t.SetLayer(board.GetLayerID(s.get("layer", "F.Cu")))
            t.SetNet(ni)
            board.Add(t)
        elif s["kind"] == "via":
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(int((ox + s["at_rel_mm"][0]) * MM),
                                          int((oy + s["at_rel_mm"][1]) * MM)))
            v.SetDrill(int(s.get("drill_mm", 0.3) * MM))
            v.SetWidth(int(s.get("dia_mm", 0.6) * MM))
            v.SetNet(ni)
            board.Add(v)
        elif s["kind"] == "zone":
            x0, x1, y0, y1 = s["box_rel_mm"]
            z = pcbnew.ZONE(board)
            z.SetLayer(board.GetLayerID(s.get("layer", "F.Cu")))
            z.SetNet(ni)
            pts = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
            outline = z.Outline()
            outline.NewOutline()
            for px, py in pts:
                outline.Append(int((ox + px) * MM), int((oy + py) * MM))
            z.SetLocalClearance(int(CLR_MM * MM))
            if hasattr(pcbnew, "ISLAND_REMOVAL_MODE_NEVER"):
                z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
            board.Add(z)
            zones_to_fill.append(z)
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
    for s in template.get("standins", []):
        if s["kind"] == "track":
            xs += [s["start_rel_mm"][0], s["end_rel_mm"][0]]
            ys += [s["start_rel_mm"][1], s["end_rel_mm"][1]]
        elif s["kind"] == "zone":
            xs += [s["box_rel_mm"][0], s["box_rel_mm"][1]]
            ys += [s["box_rel_mm"][2], s["box_rel_mm"][3]]
        elif s["kind"] == "via":
            xs.append(s["at_rel_mm"][0])
            ys.append(s["at_rel_mm"][1])
    # margin covers the widest copper's half-width (centerline extents alone put
    # a 2.5mm lane stand-in inside edge clearance -- 8 DRC hits, run A)
    wmax = max([s.get("width_mm", TRACK_W) for s in template.get("standins", [])
                if s["kind"] == "track"] +
               [tr.get("width_mm", TRACK_W) for tr in template.get("internal_tracks", [])] +
               [TRACK_W])
    m = 2.0 + wmax / 2.0
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
    # a real B.Cu GND plane when the cell carries grounding vias, so they land
    # in copper instead of dangling (the stamped cell's plane is the board's)
    if template.get("gnd_vias") and gnd_net in nets:
        z = pcbnew.ZONE(board)
        z.SetLayer(board.GetLayerID("B.Cu"))
        z.SetNet(nets[gnd_net])
        outline = z.Outline()
        outline.NewOutline()
        zi = 0.5                                  # inset: zone-to-edge clearance
        for px, py in ((x0 + zi, y0 + zi), (x1 - zi, y0 + zi),
                       (x1 - zi, y1 - zi), (x0 + zi, y1 - zi)):
            outline.Append(int((ox + px) * MM), int((oy + py) * MM))
        if hasattr(pcbnew, "ISLAND_REMOVAL_MODE_NEVER"):
            z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        board.Add(z)
        zones_to_fill.append(z)
    if zones_to_fill:                             # real ZONE_FILLER (kicad-cli cannot fill)
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
    pcbnew.SaveBoard(out_pcb, board)
    return out_pcb


def hand_baseline(model):
    """The honest 'before': score/metrics computed from the template's OWN extracted
    copper (the owner's hand routing) -- internal_tracks PLUS port_tracks (the hand
    Kelvin taps / supply links live on boundary nets; without them the hand tap
    copper under-reported as 0 -- measured 2026-07-10). None when the template
    carries no copper (unrouted source cell)."""
    tracks = list(model.t.get("internal_tracks") or []) + list(model.t.get("port_tracks") or [])
    if not tracks:
        return None, None
    routes = defaultdict(list)
    for tr in tracks:
        if tr["net_role"] not in model.route_roles:
            continue                              # compare exactly what the model routes
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
    r.add_argument("--envelope", default=None,
                   help="x0,x1,y0,y1 (anchor frame, mm): HARD box every courtyard must "
                        "fit inside -- the full-redesign rung (owner 2026-07-11)")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--starts", type=int, default=6)
    r.add_argument("--iters", type=int, default=3000)
    r.add_argument("--evals", type=int, default=None,
                   help="TOTAL eval budget (deterministic; overrides --starts, adds the "
                        "fine-grid polish stage). Blueprint-grade default: 150000 -- a "
                        "refined cell amortizes over every stamp, spend accordingly "
                        "(owner 2026-07-10)")
    r.add_argument("--no-mitre", action="store_true",
                   help="skip the 45-degree corner chamfer pass on accepted routes")
    r.add_argument("--allow-missing-gnd-vias", action="store_true",
                   help="accept poses that cannot ground every GND pad (default: "
                        "grounding-complete poses only, owner 2026-07-11)")
    r.add_argument("--render", action="store_true",
                   help="also kicad-cli render both microboards (container)")
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
    env = tuple(float(v) for v in args.envelope.split(",")) if args.envelope else None
    model = CellModel(template, pitch_axis=args.pitch_axis, envelope=env)

    prof = cProfile.Profile() if args.profile else None
    t0 = time.perf_counter()
    if prof:
        prof.enable()
    accept_fn = None
    if not args.allow_missing_gnd_vias:
        def accept_fn(p, routes):                 # grounding-complete poses only
            return not synth_gnd_vias(model, p, routes)[2]
    result = refine(model, seed=args.seed, starts=args.starts, iters=args.iters,
                    budget_evals=args.evals, acceptance_check=accept_fn, verbose=True)
    if prof:
        prof.disable()
    wall = time.perf_counter() - t0

    hand_score, hand_m = hand_baseline(model)     # the owner's actual copper = the honest "before"
    base_m = _metrics_of(model, model.base_pose, result["baseline"]["routes"] or {}) \
        if result["baseline"]["routes"] else {"note": "baseline re-synthesis refused"}
    out = {"board": args.board, "refs": refs, "anchor": args.anchor,
           "standins": len(model.standins), "standins_fcu": len(model.standin_fcu),
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
        # DESIGNER-ORDER finalize: taps -> GND vias (first claim) -> chains
        # around the barrels -> lint -> mitre (owner 2026-07-11)
        try:
            final_routes, gvias, gstubs, gmissing = finalize_cell(model, best_pose,
                                                                  mitre=not args.no_mitre)
            if not gates(model, best_pose, final_routes):
                best_routes = final_routes
                out["finalize"] = "taps-vias-chains"
            else:
                gvias, gstubs, gmissing = synth_gnd_vias(model, best_pose, best_routes)
                out["finalize"] = "search-routes (finalize gates failed)"
        except Refusal as e:
            gvias, gstubs, gmissing = synth_gnd_vias(model, best_pose, best_routes)
            out["finalize"] = f"search-routes (finalize refused: {e})"
        out["gnd_vias"] = len(gvias)
        if gmissing:
            out["gnd_via_missing"] = gmissing     # reported, never forced
        out["best_metrics"] = _metrics_of(model, best_pose, best_routes)
        refined = to_refined_template(model, best_pose, best_routes)
        refined["gnd_vias"] = gvias
        refined["internal_tracks"] += [
            {"net_role": "GND", "layer": "F.Cu",
             "start_rel_mm": [round(s[0], 4), round(s[1], 4)],
             "end_rel_mm": [round(s[2], 4), round(s[3], 4)], "width_mm": TRACK_W}
            for s in gstubs]
        with open(os.path.join(out_dir, "refined-template.json"), "w") as fh:
            json.dump(refined, fh, indent=1)
        emit_microboard(model.t, os.path.join(out_dir, "baseline.kicad_pcb"))
        emit_microboard(refined, os.path.join(out_dir, "refined.kicad_pcb"))
        out["microboards"] = [os.path.join(out_dir, "baseline.kicad_pcb"),
                              os.path.join(out_dir, "refined.kicad_pcb")]
        if args.render:
            import subprocess
            for stem in ("baseline", "refined"):
                subprocess.run(["kicad-cli", "pcb", "render", "-w", "1600", "--side", "top",
                                "-o", os.path.join(out_dir, stem + "-top.png"),
                                os.path.join(out_dir, stem + ".kicad_pcb")],
                               check=False, capture_output=True)
            # hand-in-context: the SOURCE board's own render, camera on the cell
            # (pan unit measured 2026-07-10: ~10mm/unit, x sign inverted; zoom
            # calibrated so the cell window fills ~80% of the frame height)
            try:
                import pcbnew
                b = pcbnew.LoadBoard(args.board)
                bb = b.GetBoardEdgesBoundingBox()
                bcx = (bb.GetLeft() + bb.GetRight()) / 2e6
                bcy = (bb.GetTop() + bb.GetBottom()) / 2e6
                bh = (bb.GetBottom() - bb.GetTop()) / 1e6
                xs, ys = [], []
                for fp in b.GetFootprints():
                    if fp.GetReference() in set(refs):
                        fbb = fp.GetBoundingBox()
                        xs += [fbb.GetLeft() / 1e6, fbb.GetRight() / 1e6]
                        ys += [fbb.GetTop() / 1e6, fbb.GetBottom() / 1e6]
                cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
                span = max(max(xs) - min(xs), max(ys) - min(ys)) + 4.0
                zoom = max(1.0, min(6.0, 0.8 * bh / span))
                subprocess.run(["kicad-cli", "pcb", "render", "-w", "1200", "-h", "1600",
                                "--side", "top", "--zoom", f"{zoom:.2f}",
                                "--pan", f"{-(cx - bcx) / 10.0:.3f},{(cy - bcy) / 10.0:.3f},0",
                                "-o", os.path.join(out_dir, "context-top.png"), args.board],
                               check=False, capture_output=True)
                out["context_render"] = os.path.join(out_dir, "context-top.png")
            except Exception as e:                # noqa: BLE001 -- render is best-effort
                out["context_render_error"] = str(e)
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
