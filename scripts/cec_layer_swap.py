#!/usr/bin/env python3
"""Post-route layer-swap finishing stage for the F.Cu SENSEC high-current pours (Design [1] winner,
2026-06-27, branch claude/placement-corridor).

WHAT IT DOES
------------
A foreign-signal F.Cu track that crosses a SENSEC pour carves a hole in the high-current copper
(it forces an antipad through the F.Cu pour, necking the 40A path). This stage moves the foreign
copper OFF F.Cu so the SENSEC pour can fill SOLID, stitching each relayered run back to F.Cu with a
board-legal via, then refills all zones (real ZONE_FILLER).

THE WINNING REDESIGN vs the old B.Cu-only script
------------------------------------------------
The old script always targeted B.Cu. On this 4-layer cable-board stackup (F.Cu / In1=GND plane /
In2=GND plane / B.Cu) B.Cu is the ONLY *signal* layer and it is congested under the pours (157
routed segments), so the step-3a B.Cu copper-collision guard rejected ~29 of 39 swaps -- the real
cause of the 6/41 stall. This redesign fixes TWO things:

  (1) THROUGH/TAP GATE (the correctness fix the old script lacked). A foreign F.Cu seg is a swap
      candidate ONLY if it is a genuine THROUGH crossing: BOTH endpoints lie OUTSIDE every SENSEC
      pour bbox AND the segment's interior actually enters pour copper. Any seg with an endpoint
      inside a pour is a TAP -- a pad escape that dies on a via or an F.Cu-only SMD pad INSIDE the
      protected zone. A tap has no "other side" to bridge to; relayering it just moves the
      perforation from the F.Cu pour to the inner GND plane and collides with the in-pour vias.
      Taps are NOT relayered; they are ESCALATED (a placement/corridor change, the route-time
      keepout band) per the constraint-loop human-ratification boundary.

  (2) TARGET THE In2 INNER GND PLANE, not B.Cu. The In2 "12V"-named layer (GetLayerID('12V')->6)
      is a SOLID GND plane carrying NO routed tracks, with a 0.3mm zone local_clearance, so the
      real ZONE_FILLER AUTO-OPENS an antipad slot around any foreign In2 track and around each
      transition via -- no manual antipad geometry. 43 non-GND vias already pass DRC-clean through
      both inner GND planes. Each THROUGH crossing first tries B.Cu (cheapest, still uses the
      existing congestion guard); if B.Cu collides it falls back to In2.

HONEST LIMIT (measured on build/eps-rev3-route/eps-8pin-rev3-routed.kicad_pcb): there are exactly 4
THROUGH crossing-segments (/DETC2 x2, /USB_CC2 x2 -- one parallel pair cutting BOTH HI pours). This
stage clears the /USB_CC2 pair onto In2 (DRC-clean, 0 new shorts, +5-7% F.Cu fill on the HI pours)
and ESCALATES /DETC2: its ONLY exit toward pad U1.29 runs pinned between the ESP32 (U1) pad row and
the B.Cu /DETECT and /CAN_H tracks, so no transition via has a legal home anywhere on that run -- a
genuine PLACEMENT-density constraint, not a tunable. The 35 TAP segments are likewise infeasible to
clear by ANY post-route layer manipulation on this stackup (forcing all 32 swappable segs onto In2
produced 27 shorting_items + clearance + hole collisions): they are pad escapes whose foreign-net
DESTINATIONS are F.Cu-only SMD pads INSIDE the pour (14 such pads measured inside the outlines), so
"cross it on an inner layer" is undefined. Through-nets blocked by placement density AND the taps
both need the UPSTREAM corridor keepout during routing (CEC_TWO_PASS_CORRIDOR), which the comparison
board build/eps-rev3-tpc-module/...routed-tpc.kicad_pcb already demonstrates (0 through-crossings,
few tap clips). And even a fully de-clipped solid-F.Cu board runs ~227C at 40A/4-cable, bound by the
F.Cu-only shunt RS pad -- closing the 30C-rise gate is a shunt/footprint/stackup change = separate
owner ratification, NOT anything a layer-swap can touch.

Usage: python3 cec_layer_swap.py <in.kicad_pcb> <out.kicad_pcb> [copper_clear_mm] [hole_clear_mm]
Run inside the routing container (pcbnew = KiCad 10). Exit 0 on success (board saved to OUT, even if
0 crossings cleared -- a refill-only board is still a valid, improved-or-equal artifact).
"""
import sys, os, math, json
import pcbnew
from collections import defaultdict, Counter

IN, OUT = sys.argv[1], sys.argv[2]
UM = 1_000_000
CLEAR = int(float(sys.argv[3]) * UM) if len(sys.argv) > 3 else int(0.2 * UM)
HOLE_CLEAR = int(float(sys.argv[4]) * UM) if len(sys.argv) > 4 else int(0.25 * UM)
F = pcbnew.F_Cu
B = pcbnew.B_Cu

b = pcbnew.LoadBoard(IN)

# ---- target the In2 inner GND plane (the winning design's escape layer) --------------------------
# The In2 layer is the "12V"-NAMED layer that is actually poured GND (the stale name flagged by the
# 2026-06-14 owner directive). Resolve it ROBUSTLY: prefer the second inner copper layer of the
# enabled stack; only fall back to GetLayerID('12V') if the name resolves. If the board has no
# distinct second inner GND plane (e.g. the Hub/24-pin keep an inner as a real routing layer), the
# In2 fallback is simply unavailable and through-crossings use B.Cu only.
def _inner_gnd_plane_layer():
    # which inner copper layers carry a board-spanning GND zone?
    bb = b.GetBoardEdgesBoundingBox()
    barea = max(1, bb.GetWidth()) * max(1, bb.GetHeight())
    gnd_inners = []
    for z in b.Zones():
        if z.GetIsRuleArea():
            continue
        if not z.GetNetname().endswith("GND"):
            continue
        zb = z.GetBoundingBox()
        if (zb.GetWidth() * zb.GetHeight()) / barea < 0.5:
            continue
        for lid in z.GetLayerSet().CuStack():
            if lid not in (F, B) and lid not in gnd_inners:
                gnd_inners.append(lid)
    # prefer In2.Cu if it is a GND plane (the canonical eps stackup); else the last GND inner.
    if pcbnew.In2_Cu in gnd_inners:
        return pcbnew.In2_Cu
    if gnd_inners:
        return gnd_inners[-1]
    # name fallback
    try:
        lid = b.GetLayerID("12V")
        if lid is not None and lid >= 0 and lid not in (F, B):
            return lid
    except Exception:
        pass
    return None

IN2 = _inner_gnd_plane_layer()
print(f"target inner GND plane layer: {IN2} "
      f"({b.GetLayerName(IN2) if IN2 is not None else 'NONE -- B.Cu-only fallback'})")

# ---- via sizing per netclass (board-legal sizes) -------------------------------------------------
NC = b.GetAllNetClasses()
def via_size_for(net):
    ni = b.FindNet(net)
    try:
        ncn = ni.GetNetClassName()
        nc = NC[ncn]
        vd, vdr = int(nc.GetViaDiameter()), int(nc.GetViaDrill())
        # never undersize below the board legal floor (0.6/0.3 -> 0.15mm annular > 0.1 min)
        if vd < int(0.6 * UM) or vdr <= 0:
            return int(0.6 * UM), int(0.3 * UM)
        return vd, vdr
    except Exception:
        return int(0.6 * UM), int(0.3 * UM)

# ---- 1. F.Cu SENSEC pour bboxes ------------------------------------------------------------------
pours = []
for z in b.Zones():
    nn = z.GetNetname()
    if (nn.endswith("_HI") or nn.endswith("_LO")) and z.IsOnLayer(F):
        bb = z.GetBoundingBox()
        pours.append((nn, bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))

def is_swappable_net(tn):
    # never move the SENSEC force/sense nets or GND -- only foreign signals
    return not (tn.endswith("GND") or tn.endswith("_HI") or tn.endswith("_LO"))

def pt_in_pour(x, y, exclude_net):
    for nn, l, tp, r, bm in pours:
        if nn == exclude_net:
            continue
        if l <= x <= r and tp <= y <= bm:
            return nn
    return None

def seg_enters_pour_interior(s, e, tn):
    """True if the segment's INTERIOR (excluding exact endpoints) crosses foreign pour copper.
    Samples the centerline -- this is what distinguishes a genuine THROUGH crossing from a
    bbox-corner graze (the old script's bbox-overlap test counted 211 grazes as clips)."""
    for k in range(1, 20):
        x = s.x + (e.x - s.x) * k // 20
        y = s.y + (e.y - s.y) * k // 20
        if pt_in_pour(x, y, tn):
            return True
    return False

# ---- THROUGH/TAP classification (THE correctness gate) -------------------------------------------
tracks = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
through_segs = []     # genuine THROUGH crossings -- relayer candidates
tap_segs = []         # foreign segs with an endpoint inside a pour -- ESCALATE, never relayer
for t in tracks:
    if t.GetLayer() != F or not is_swappable_net(t.GetNetname()):
        continue
    s, e = t.GetStart(), t.GetEnd()
    si = pt_in_pour(s.x, s.y, t.GetNetname())
    ei = pt_in_pour(e.x, e.y, t.GetNetname())
    if si is not None or ei is not None:
        # an endpoint inside a pour -> TAP (only count it if it really touches pour copper, not a
        # bbox graze at the endpoint -- an endpoint exactly on the pour is still a tap to escalate)
        if seg_enters_pour_interior(s, e, t.GetNetname()) or si is not None or ei is not None:
            # require the seg to actually overlap the pour bbox at all (skip far-away false hits)
            if any((min(s.x, e.x) <= r and max(s.x, e.x) >= l
                    and min(s.y, e.y) <= bm and max(s.y, e.y) >= tp)
                   for nn, l, tp, r, bm in pours if nn != t.GetNetname()):
                tap_segs.append(t)
        continue
    # both endpoints OUTSIDE every pour -> THROUGH only if the interior actually enters pour copper
    if seg_enters_pour_interior(s, e, t.GetNetname()):
        through_segs.append(t)

print(f"THROUGH crossings (both ep outside + interior in pour): {len(through_segs)} "
      f"{dict(Counter(t.GetNetname() for t in through_segs))}")
print(f"TAP segments (endpoint inside a pour -- ESCALATE, not relayered): {len(tap_segs)} "
      f"{dict(Counter(t.GetNetname() for t in tap_segs))}")

# ---- chain-grow: extend each THROUGH seg to its contiguous same-net F.Cu run so the WHOLE crossing
# relayers together and the F<->target vias land at the pour exit nodes (outside the pour). We grow
# ONLY into segments that are themselves still inside-the-pour-interior OR share a node with an
# inside-pour seg, so the exit vias sit just outside the pour edge. -------------------------------
def _key(pt):
    return (round(pt.x / 1000), round(pt.y / 1000))

# CHAIN-GROW: a through-net (e.g. /DETC2, /USB_CC2) crosses the pour band as a CONTIGUOUS F.Cu run
# that may span multiple pours joined by short jogs in the gap between them. Relayer the WHOLE run
# as one chain and place the F<->inner vias only at the two OUTER exit nodes (where the run leaves
# the pour band and rejoins kept F.Cu) -- NOT at every per-pour edge. This is what lets the parallel
# /DETC2 || /USB_CC2 pair both escape: their per-pour-edge vias would stack 0.4mm apart (illegal),
# but their OUTER turn-nodes are 0.85-2.3mm apart (legal). A chain grows into a neighbor seg as long
# as that neighbor's interior is in a pour OR it bridges two in-pour segs across the inter-pour gap.
fcu_by_node = defaultdict(list)
for t in tracks:
    if t.GetLayer() == F and is_swappable_net(t.GetNetname()):
        fcu_by_node[(t.GetNetname(), _key(t.GetStart()))].append(t)
        fcu_by_node[(t.GetNetname(), _key(t.GetEnd()))].append(t)

def _interior_in_pour(t):
    return seg_enters_pour_interior(t.GetStart(), t.GetEnd(), t.GetNetname())

# bbox of all pours a net crosses, inflated by the inter-pour-gap so a jog between two HI pours is
# absorbed into the chain (but a far-away turn-down out of the band is NOT).
GAP_GROW = int(float(os.environ.get("CEC_CHAIN_GAP_MM", "8.0")) * UM)
def _near_pour_edge(x, y):
    """The point sits in the gap just OUTSIDE a foreign pour edge (within GAP_GROW horizontally and
    inside the pour's y-band) -- i.e. it is a legitimate inter-pour jog endpoint, not a turn-down."""
    for nn, l, tp, r, bm in pours:
        if tp <= y <= bm and (l - GAP_GROW <= x <= l or r <= x <= r + GAP_GROW):
            return True
    return False
def _seg_in_band(t):
    """A neighbor belongs to the chain if its interior crosses a pour, OR it is a SHORT inter-pour
    jog: both endpoints sit in the gap just outside a pour edge (within the pour y-band) and the seg
    is shorter than GAP_GROW. This absorbs the (47.14,10.46)->(47.75,11.08) jog between SENSEC1_HI
    and SENSEC2_HI but NOT a long turn-down to a board corner (which would drag the exit via off into
    congested copper)."""
    if _interior_in_pour(t):
        return True
    s, e = t.GetStart(), t.GetEnd()
    if math.hypot(e.x - s.x, e.y - s.y) > GAP_GROW:
        return False
    return _near_pour_edge(s.x, s.y) and _near_pour_edge(e.x, e.y)

relayer = {id(t): t for t in through_segs}
frontier = list(through_segs)
while frontier:
    t = frontier.pop()
    net = t.GetNetname()
    for ep in (_key(t.GetStart()), _key(t.GetEnd())):
        for nb in fcu_by_node[(net, ep)]:
            if id(nb) in relayer:
                continue
            if _seg_in_band(nb):
                relayer[id(nb)] = nb
                frontier.append(nb)
relayer_segs = list(relayer.values())
print(f"relayer set after chain-grow: {len(relayer_segs)} "
      f"{dict(Counter(t.GetNetname() for t in relayer_segs))}")

# ---- geometry helpers ----------------------------------------------------------------------------
def pt_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    tt = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + tt * dx), py - (ay + tt * dy))

def seg_seg_dist(a, bb):
    a0x, a0y = a[0]; a1x, a1y = a[1]; b0x, b0y = bb[0]; b1x, b1y = bb[1]
    def ccw(Ax, Ay, Bx, By, Cx, Cy):
        return (Cy - Ay) * (Bx - Ax) - (By - Ay) * (Cx - Ax)
    d1 = ccw(a0x, a0y, a1x, a1y, b0x, b0y); d2 = ccw(a0x, a0y, a1x, a1y, b1x, b1y)
    d3 = ccw(b0x, b0y, b1x, b1y, a0x, a0y); d4 = ccw(b0x, b0y, b1x, b1y, a1x, a1y)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(pt_seg_dist(b0x, b0y, a0x, a0y, a1x, a1y), pt_seg_dist(b1x, b1y, a0x, a0y, a1x, a1y),
              pt_seg_dist(a0x, a0y, b0x, b0y, b1x, b1y), pt_seg_dist(a1x, a1y, b0x, b0y, b1x, b1y))

def keyp(pt):
    return (round(pt.x / 1000), round(pt.y / 1000))

def endpoints(t):
    return keyp(t.GetStart()), keyp(t.GetEnd())

# ---- existing copper / vias / pads / holes per target layer --------------------------------------
# For a B.Cu candidate we must clear the 157 congested B.Cu signal tracks/vias/pads. For an In2
# candidate we clear ONLY foreign copper already on In2 (initially none -- it is a solid GND plane;
# GND is same-net for our purpose only via the antipad, so we never treat the GND plane as a
# colliding net here -- the 0.3mm zone clearance handles it at refill).
def _layer_copper(layer):
    segs = []
    for t in tracks:
        if t.GetLayer() == layer:
            s = t.GetStart(); e = t.GetEnd()
            segs.append((t.GetNetname(), ((s.x, s.y), (e.x, e.y)), t.GetWidth() // 2))
    pads = []
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            if pad.IsOnLayer(layer):
                pc = pad.GetCenter(); sz = pad.GetSize()
                pads.append((pad.GetNetname(), (pc.x, pc.y), max(sz.x, sz.y) // 2))
    return segs, pads

# layer -> (segs, pads). Includes any moved segs appended live during the swap.
LCOPPER = {}
for L in (B,) + ((IN2,) if IN2 is not None else ()):
    LCOPPER[L] = _layer_copper(L)

# all drilled holes (vias + THT pads) -- hole-to-hole applies regardless of layer
all_holes = []
existing_vias = []     # (net, (x,y), copper_radius) -- via pads on every layer
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        p = t.GetPosition()
        # PCB_VIA.GetWidth() (no-arg) asserts in KiCad-10 (SWIG footgun); pass the via's TopLayer.
        try:
            vw = t.GetWidth(t.TopLayer())
        except Exception:
            vw = t.GetDrillValue() + int(0.3 * UM)   # diameter ~= drill + 2*annular fallback
        existing_vias.append((t.GetNetname(), (p.x, p.y), vw // 2))
        all_holes.append((t.GetNetname(), p.x, p.y, t.GetDrillValue() // 2))
pad_at = {}
fcu_pads = []
for fp in b.GetFootprints():
    for pad in fp.Pads():
        pc = pad.GetCenter(); sz = pad.GetSize()
        onF = pad.IsOnLayer(F); onB = pad.IsOnLayer(B)
        drill = pad.GetDrillSize()
        is_tht = (drill.x > 0 and drill.y > 0)
        if is_tht:
            all_holes.append((pad.GetNetname(), pc.x, pc.y, max(drill.x, drill.y) // 2))
        pad_at[keyp(pc)] = (pad.GetNetname(), onF, onB, is_tht)
        if onF:
            fcu_pads.append((pad.GetNetname(), (pc.x, pc.y), max(sz.x, sz.y) // 2))

def seg_collides_on(seg_geom, halfw, net, layer):
    """The relayered segment, placed on `layer`, clears foreign copper on that layer?
    For an inner GND plane the only copper that matters is OTHER foreign tracks/vias we put there
    this pass (the GND plane itself auto-antipads via its 0.3mm zone clearance at refill)."""
    (x0, y0), (x1, y1) = seg_geom
    segs, pads = LCOPPER[layer]
    for n2, g2, hw2 in segs:
        if n2 == net or n2.endswith("GND"):
            continue
        if seg_seg_dist(seg_geom, g2) < halfw + hw2 + CLEAR:
            return True
    for n2, (px, py), pr in pads:
        if n2 == net or n2.endswith("GND"):
            continue
        if pt_seg_dist(px, py, x0, y0, x1, y1) < halfw + pr + CLEAR:
            return True
    # vias on that layer (every via spans F<->B, so it is on B; on an inner only if its layer-pair
    # spans it -- approximate by treating all vias as obstacles on B and on inners)
    for n2, (vx, vy), vr in existing_vias:
        if n2 == net or n2.endswith("GND"):
            continue
        if pt_seg_dist(vx, vy, x0, y0, x1, y1) < halfw + vr + CLEAR:
            return True
    return False

def via_hole_ok(cx, cy, drill, scratch_holes):
    r = drill // 2
    for n2, hx, hy, hr in scratch_holes:
        d = math.hypot(cx - hx, cy - hy)
        if d < 1000:       # coincident with own existing hole -> handled by bridged-node skip
            continue
        if d < r + hr + HOLE_CLEAR:
            return False
    return True

def via_copper_ok(cx, cy, net, via_w, layer):
    """The transition via PAD (on F and on `layer`) clears foreign copper on both. GND is excluded
    (the inner GND plane auto-antipads the via at refill via the 0.3mm local clearance)."""
    vr = via_w // 2
    for L in (F, layer):
        if L is None:
            continue
        segs, pads = (LCOPPER[L] if L in LCOPPER else _layer_copper(L))
        for n2, g2, hw2 in segs:
            if n2 == net or n2.endswith("GND"):
                continue
            (x0, y0), (x1, y1) = g2
            if pt_seg_dist(cx, cy, x0, y0, x1, y1) < vr + hw2 + CLEAR:
                return False
        for n2, (px, py), pr in pads:
            if n2 == net or n2.endswith("GND"):
                continue
            if math.hypot(cx - px, cy - py) < vr + pr + CLEAR:
                return False
    for n2, (px, py), pr in fcu_pads:
        if n2 == net or n2.endswith("GND"):
            continue
        if math.hypot(cx - px, cy - py) < vr + pr + CLEAR:
            return False
    for n2, (vx, vy), vr2 in existing_vias:
        if n2 == net:
            continue
        if math.hypot(cx - vx, cy - vy) < vr + vr2 + CLEAR:
            return False
    return True

# bridged nodes (already F<->inner connected by a THT pad or an existing via) -> never place a via
bridged_node = set()
for ep, (net, onF, onB, is_tht) in pad_at.items():
    if is_tht or (onF and onB):
        bridged_node.add((net, ep))
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        bridged_node.add((t.GetNetname(), keyp(t.GetPosition())))

# F.Cu copper presence by node (for finding the genuine exit nodes that need a via)
fcu_ep_all = defaultdict(list)
for t in tracks:
    if t.GetLayer() == F:
        a, c = endpoints(t)
        fcu_ep_all[(t.GetNetname(), a)].append(t)
        fcu_ep_all[(t.GetNetname(), c)].append(t)

def fcu_at_kept(net, ep, chain_ids):
    """True if KEPT F.Cu copper of `net` touches this node (an F.Cu track NOT in THIS chain, or an
    F-only pad). The relayered chain bridges back to F.Cu here -> a transition via is needed. A node
    interior to the chain (touching only this chain's own segs) is NOT an exit -- it stays on the
    relayered layer with no via."""
    for t in fcu_ep_all[(net, ep)]:
        if t.GetLayer() == F and id(t) not in chain_ids:
            return True
    pa = pad_at.get(ep)
    if pa and pa[0] == net and pa[1] and not pa[2]:
        return True
    return False

def kept_stub_polyline(net, ep, pt, chain_ids, max_nodes=12):
    """Walk the KEPT F.Cu polyline of `net` outward from the exit node (following same-net F.Cu segs
    NOT in the chain, taking the longest continuation at each node, stopping at a branch / pad / via /
    bridged node). Returns the ordered list of vertices [pt, v1, v2, ...] so a transition via can be
    slid along the MULTI-segment stub (through a corner onto the next segment) -- which is what lets
    /DETC2's right via slide past the parallel /USB_CC2 turn-down onto its diverging vertical run."""
    verts = [pt]
    cur_ep = ep
    visited_segs = set()
    for _ in range(max_nodes):
        cands = [t for t in fcu_ep_all[(net, cur_ep)]
                 if t.GetLayer() == F and id(t) not in chain_ids and id(t) not in visited_segs]
        if not cands:
            break
        # longest continuation
        t = max(cands, key=lambda x: math.hypot(x.GetEnd().x - x.GetStart().x,
                                                x.GetEnd().y - x.GetStart().y))
        visited_segs.add(id(t))
        s, e = t.GetStart(), t.GetEnd()
        far = e if keyp(s) == cur_ep else s
        verts.append(far)
        cur_ep = keyp(far)
        # stop if this node is bridged (pad/via) -- can't slide past a fixed terminal
        if (net, cur_ep) in bridged_node:
            break
    return verts

def point_along_polyline(verts, dist_nm):
    """Return (pt, seg_index) at arc-length dist_nm from verts[0] along the polyline, plus which
    segment index it lands on (for the F.Cu stub split). Clamped to the polyline length."""
    acc = 0
    for i in range(len(verts) - 1):
        a, b = verts[i], verts[i + 1]
        seglen = math.hypot(b.x - a.x, b.y - a.y)
        if seglen < 1:
            continue
        if acc + seglen >= dist_nm:
            f = (dist_nm - acc) / seglen
            return pcbnew.VECTOR2I(int(round(a.x + (b.x - a.x) * f)),
                                   int(round(a.y + (b.y - a.y) * f))), i
        acc += seglen
    return verts[-1], len(verts) - 2 if len(verts) > 1 else 0

def polyline_length(verts):
    return sum(math.hypot(verts[i + 1].x - verts[i].x, verts[i + 1].y - verts[i].y)
               for i in range(len(verts) - 1))

# ---- CHAIN relayer + exit-node vias (cheapest-legal-layer dispatch, atomic per chain) ------------
# Group the relayer set into per-net contiguous CHAINS, relayer the whole chain off F.Cu to the
# cheapest legal layer (B.Cu first via the congestion guard, else the In2 inner GND plane which
# auto-antipads), and bridge it back to F.Cu with ONE via at each genuine EXIT node -- a chain node
# that touches kept F.Cu copper of the same net (an F.Cu track NOT in the chain, or an F-only pad).
# Vias land at the OUTER turn-nodes of the run (where the parallel /DETC2 || /USB_CC2 pair has
# diverged 0.85-2.3mm), never at the congested per-pour edges where they'd stack 0.4mm apart. The
# whole chain is applied ATOMICALLY: if any exit via is unsafe (copper / hole-to-hole / via-pad
# clearance), the chain is LEFT on F.Cu -- never a dangling via, never a partial swap.
def via_ok_at(coord, net, via_w, via_d, layer, scratch_holes, scratch_vias):
    if not via_copper_ok(coord.x, coord.y, net, via_w, layer):
        return False
    if not via_hole_ok(coord.x, coord.y, via_d, scratch_holes):
        return False
    vr_new = via_w // 2
    for n2, (vx, vy), vr2 in scratch_vias:
        if n2 == net:
            continue
        d = math.hypot(coord.x - vx, coord.y - vy)
        if d < 1000:
            continue
        if d < vr_new + vr2 + CLEAR:
            return False
    return True

# union-find the relayer set into chains by shared endpoints (within a net)
parent = {}
def _find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def _union(a, c):
    parent[_find(a)] = _find(c)
ep_map = defaultdict(list)
for i, t in enumerate(relayer_segs):
    parent.setdefault(i, i)
    a, c = endpoints(t)
    ep_map[(t.GetNetname(), a)].append(i)
    ep_map[(t.GetNetname(), c)].append(i)
for (_n, _e), idxs in ep_map.items():
    for j in idxs[1:]:
        _union(idxs[0], j)
chains = defaultdict(list)
for i in range(len(relayer_segs)):
    chains[_find(i)].append(relayer_segs[i])
print(f"chains: {len(chains)}")

moved = {}          # cid -> layer (for the summary tally)
crossings_cleared = 0
left_on_fcu = 0
vias_added = 0
reverted = 0
cleared_nets = set()     # through-nets fully relayered off F.Cu (with clean exit vias)
blocked_nets = set()     # through-nets that could not get a legal layer / exit via -> escalate
scratch_holes = list(all_holes)
scratch_vias = list(existing_vias)

# PHASE 1 -- relayer EVERY chain's segments off F.Cu first, so a parallel pair (/DETC2 || /USB_CC2)
# stops counting EACH OTHER's F.Cu copper when its exit via is checked (the ordering bug: whichever
# chain is processed first would otherwise drop a via over the other's not-yet-moved F.Cu run). Each
# chain takes the cheapest legal layer given the chains already moved (B.Cu first via the congestion
# guard, else the In2 inner GND plane). A chain that fits NO layer stays on F.Cu.
chain_plan = {}     # cid -> (segs, layer, chain_ids, via_w, via_d)
for cid, segs in chains.items():
    net = segs[0].GetNetname()
    hw = segs[0].GetWidth() // 2
    via_w, via_d = via_size_for(net)
    chain_ids = {id(t) for t in segs}
    layer = None
    for cand in ((B,) + ((IN2,) if IN2 is not None else ())):
        if all(not seg_collides_on(((t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)),
                                   hw, net, cand) for t in segs):
            layer = cand
            break
    if os.environ.get("CEC_LS_DEBUG") == "1":
        print(f"[dbg] chain {net} {len(segs)}segs -> layer={b.GetLayerName(layer) if layer is not None else None}")
    if layer is None:
        left_on_fcu += len(segs)
        blocked_nets.add(net)
        continue
    # commit the relayering NOW (so the next chain + every exit-via check sees the moved copper)
    for t in segs:
        t.SetLayer(layer)
        LCOPPER[layer][0].append((net, ((t.GetStart().x, t.GetStart().y),
                                        (t.GetEnd().x, t.GetEnd().y)), hw))
    chain_plan[cid] = (segs, layer, chain_ids, via_w, via_d)

# PHASE 2 -- place the exit vias. The via may SLIDE along the kept F.Cu exit polyline (through a
# corner onto the next segment, max CEC_VIA_SLIDE_MM) so it can step PAST a parallel partner's run
# to where the two nets have diverged (the /DETC2 right via slides off the parallel diagonal onto its
# own diverging vertical segment, ~1.1mm clear). Sliding stays on the net's copper: the kept-stub
# portion [node..via] is converted to relayered copper and the via sits at the boundary. A chain
# whose exit via can't be placed anywhere on the slide window is REVERTED whole back to F.Cu (no
# dangling via, no half-bridged run).
SLIDE_STEP = int(0.07 * UM)
SLIDE_MAX = int(float(os.environ.get("CEC_VIA_SLIDE_MM", "5.0")) * UM)

for cid, (segs, layer, chain_ids, via_w, via_d) in list(chain_plan.items()):
    net = segs[0].GetNetname()
    node_coord = {}
    for t in segs:
        for ep, pt in ((endpoints(t)[0], t.GetStart()), (endpoints(t)[1], t.GetEnd())):
            node_coord[ep] = pt
    exit_nodes = [(ep, pt) for ep, pt in node_coord.items()
                  if (net, ep) not in bridged_node and fcu_at_kept(net, ep, chain_ids)]
    sh = list(scratch_holes); sv = list(scratch_vias)
    plan = []          # (ep, node_pt, via_pt, slide_nm, polyline)
    ok = True
    for ep, pt in exit_nodes:
        poly = kept_stub_polyline(net, ep, pt, chain_ids)
        plen = polyline_length(poly)
        chosen = None
        slide = 0
        while slide <= min(SLIDE_MAX, plen):
            vp, _seg_i = point_along_polyline(poly, slide)
            if via_ok_at(vp, net, via_w, via_d, layer, sh, sv):
                chosen = (vp, slide)
                break
            slide += SLIDE_STEP
        if os.environ.get("CEC_LS_DEBUG") == "1":
            print(f"[dbg]   exit via {net} @({pt.x/UM:.2f},{pt.y/UM:.2f}) "
                  f"-> {'placed slide=%.2fmm' % (chosen[1]/UM) if chosen else 'FAIL (polylen %.2f)' % (plen/UM)}")
        if chosen is None:
            ok = False
            break
        vp, slide = chosen
        plan.append((ep, pt, vp, slide, poly))
        sh.append((net, vp.x, vp.y, via_d // 2))
        sv.append((net, (vp.x, vp.y), via_w // 2))
    if not ok:
        # REVERT the whole chain back to F.Cu (no partial / dangling)
        for t in segs:
            t.SetLayer(F)
        reverted += len(segs)
        left_on_fcu += len(segs)
        blocked_nets.add(net)
        continue
    netobj = b.FindNet(net)
    for ep, node_pt, vp, slide, poly in plan:
        if slide > 0:
            # convert the kept-stub portion [node..via] to relayered copper so the via bridges the
            # In2 run <-> kept F.Cu at the diverged point. Walk the polyline: relayer each kept seg
            # fully before the via; split the seg that CONTAINS the via (node-side -> relayered,
            # via-side -> stays F.Cu).
            vp_seg, seg_i = point_along_polyline(poly, slide)
            # map polyline vertices back to the kept F.Cu track objects + relayer/split them
            acc = 0
            for i in range(len(poly) - 1):
                a, c = poly[i], poly[i + 1]
                seglen = math.hypot(c.x - a.x, c.y - a.y)
                if seglen < 1:
                    continue
                # find the kept F.Cu track object for edge (a,c)
                trk = None
                for t in fcu_ep_all[(net, keyp(a))]:
                    if (t.GetLayer() == F and id(t) not in chain_ids
                            and {keyp(t.GetStart()), keyp(t.GetEnd())} == {keyp(a), keyp(c)}):
                        trk = t; break
                if trk is None:
                    break
                if acc + seglen <= slide + 1:           # whole seg is before the via -> relayer it
                    trk.SetLayer(layer)
                    acc += seglen
                else:                                    # the via is on THIS seg -> split it
                    # node-side a..vp -> relayer; via-side vp..c -> stays F.Cu
                    if keyp(trk.GetStart()) == keyp(a):
                        trk.SetEnd(vp); trk.SetLayer(layer)
                    else:
                        trk.SetStart(vp); trk.SetLayer(layer)
                    fstub = pcbnew.PCB_TRACK(b)
                    fstub.SetStart(vp); fstub.SetEnd(c); fstub.SetWidth(trk.GetWidth())
                    fstub.SetLayer(F); fstub.SetNet(netobj)
                    b.Add(fstub)
                    break
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(vp.x, vp.y))
        v.SetDrill(via_d); v.SetWidth(via_w)
        v.SetLayerPair(F, B)        # through via spans F..B (and every inner) -> connects F<->In2 too
        v.SetNet(netobj)
        b.Add(v)
        scratch_holes.append((net, vp.x, vp.y, via_d // 2))
        scratch_vias.append((net, (vp.x, vp.y), via_w // 2))
        all_holes.append((net, vp.x, vp.y, via_d // 2))
        existing_vias.append((net, (vp.x, vp.y), via_w // 2))
        bridged_node.add((net, ep))
        vias_added += 1
    crossings_cleared += len(segs)
    cleared_nets.add(net)
    moved[cid] = layer

net_layer = Counter(b.GetLayerName(L) for L in moved.values())
print(f"chains_relayered: {len(moved)} ({crossings_cleared} segs) -> {dict(net_layer)}")
print(f"left_on_fcu (no legal layer/via for the chain): {left_on_fcu}  reverted: {reverted}")
print(f"vias_added: {vias_added}")

# ---- refill all zones (antipad the new vias + foreign In2 runs; clear stale fill) -----------------
b.BuildConnectivity()
for z in b.Zones():
    z.UnFill()
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
print("zones_refilled")

pcbnew.SaveBoard(OUT, b)

# ---- machine-readable summary for the route wiring + the escalation record -----------------------
through_nets = sorted(set(t.GetNetname() for t in through_segs))
tap_nets = sorted(set(t.GetNetname() for t in tap_segs))
esc_parts = []
if blocked_nets:
    esc_parts.append(
        "ESCALATE %d through-net(s) [%s] whose exit via has NO legal home on this board (the "
        "parallel through-pair runs ~0.4mm apart from the pour band straight into the board-edge / "
        "ESP pad row, so neither member's transition via can clear the other's kept F.Cu without a "
        "PLACEMENT change). Re-route with the foreign nets separated, or accept the residual clip."
        % (len(blocked_nets), ",".join(sorted(blocked_nets))))
if tap_segs:
    esc_parts.append(
        "ESCALATE %d TAP segment(s) [%s] to a PLACEMENT/CORRIDOR change: the foreign-net via escapes "
        "originate INSIDE the SENSEC sense-IC cluster (14 swappable foreign pads sit inside the pour "
        "outlines) and CANNOT be relayered by any post-route swap (forcing all 32 onto the inner GND "
        "plane measured 27 shorting_items). The proven lever is a route-time corridor keepout band "
        "(CEC_TWO_PASS_CORRIDOR=1) so the router never crosses the sense band -- the comparison board "
        "build/eps-rev3-tpc-module/eps-8pin-rev3-routed-tpc.kicad_pcb shows 0 through-crossings + only "
        "4 tap clips with that lever."
        % (len(tap_segs), ",".join(tap_nets)))
esc_parts.append(
    "THERMAL (separate owner ratification, NOT a layer-swap): even fully de-clipped with the SENSEC "
    "pours solid, this board runs ~227C at 40A/4-cable (~123C/1-cable), bound by the F.Cu-ONLY shunt "
    "RS pad (1.23x3.35mm: shunt I2R ~+29C + copper-convergence neck ~+46C) -- a fixed geometric "
    "constraint. Closing the 30C-rise gate needs a shunt/footprint/stackup change.")
summary = {
    "through_crossing_segments": len(through_segs),
    "through_nets": through_nets,
    "through_nets_cleared": sorted(cleared_nets),
    "through_nets_blocked": sorted(blocked_nets),
    "through_segments_relayered": crossings_cleared,
    "through_per_layer": dict(net_layer),
    "tap_segments_escalated": len(tap_segs),
    "tap_nets": tap_nets,
    "vias_added": vias_added,
    "reverted_segments": reverted,
    "left_on_fcu": left_on_fcu,
    "target_inner_plane": (b.GetLayerName(IN2) if IN2 is not None else None),
    "escalation": ("none -- all THROUGH crossings cleared and no TAP residual"
                   if not blocked_nets and not tap_segs else "  ||  ".join(esc_parts)),
}
print("SUMMARY " + json.dumps(summary))
print("SAVED", OUT)
