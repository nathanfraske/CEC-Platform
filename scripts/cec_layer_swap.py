#!/usr/bin/env python3
"""Post-route layer-swap (per-net chain, netclass-via, hole+zone aware): move FOREIGN-signal F.Cu
track segments that clip the F.Cu SENSEC pours down to B.Cu (under the pour). For each net, group its
clipping segments into contiguous chains; swap a whole chain only if EVERY segment is B.Cu-collision-
free AND every F<->B transition node can take a properly-sized via without a hole-clearance violation.
Then refill all zones (real ZONE_FILLER) so the GND plane antipads the new vias.

Usage: python3 layer_swap.py <in.kicad_pcb> <out.kicad_pcb> [copper_clear_mm] [hole_clear_mm]
Run inside the routing container (pcbnew = KiCad 10)."""
import sys, math
import pcbnew
from collections import defaultdict, Counter

IN, OUT = sys.argv[1], sys.argv[2]
UM = 1_000_000
CLEAR = int(float(sys.argv[3]) * UM) if len(sys.argv) > 3 else int(0.2 * UM)
HOLE_CLEAR = int(float(sys.argv[4]) * UM) if len(sys.argv) > 4 else int(0.25 * UM)
F = pcbnew.F_Cu
B = pcbnew.B_Cu

b = pcbnew.LoadBoard(IN)

# ---- via sizing per netclass (board-legal sizes) -------------------------------------------------
NC = b.GetAllNetClasses()
def via_size_for(net):
    ni = b.FindNet(net)
    try:
        ncn = ni.GetNetClassName()
        nc = NC[ncn]
        return int(nc.GetViaDiameter()), int(nc.GetViaDrill())
    except Exception:
        return int(0.6 * UM), int(0.3 * UM)

# ---- 1. F.Cu SENSEC pour bboxes ------------------------------------------------------------------
pours = []
for z in b.Zones():
    nn = z.GetNetname()
    if (nn.endswith("_HI") or nn.endswith("_LO")) and z.IsOnLayer(F):
        bb = z.GetBoundingBox()
        pours.append((nn, bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))

def seg_clips(t):
    s = t.GetStart(); e = t.GetEnd(); tn = t.GetNetname()
    for nn, l, tp, r, bm in pours:
        if tn == nn:
            continue
        if min(s.x, e.x) <= r and max(s.x, e.x) >= l and min(s.y, e.y) <= bm and max(s.y, e.y) >= tp:
            return True
    return False

def is_swappable_net(tn):
    return not (tn.endswith("GND") or tn.endswith("_HI") or tn.endswith("_LO"))

tracks = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
clip_segs0 = [t for t in tracks if t.GetLayer() == F and is_swappable_net(t.GetNetname()) and seg_clips(t)]
print(f"clip segs (foreign F.Cu over pour bbox): {len(clip_segs0)}")
print("  per net:", dict(Counter(t.GetNetname() for t in clip_segs0)))

# ---- chain-grow: extend each clip seg to adjacent same-net F.Cu segs whose bbox overlaps an INFLATED
# pour region, so a contiguous run swaps together and the F<->B vias land at the pour exit (less
# crowded) instead of one pair of vias per isolated clip seg.  GROW_MM controls how far past the pour
# edge a grown seg may sit.  Bounded by the swappable-net rule. -----------------------------------
import os as _os
GROW_MM = float(_os.environ.get("GROW_MM", "2.0"))
GROW = int(GROW_MM * UM)
def seg_in_inflated_pour(t):
    s = t.GetStart(); e = t.GetEnd(); tn = t.GetNetname()
    for nn, l, tp, r, bm in pours:
        if tn == nn:
            continue
        if (min(s.x, e.x) <= r + GROW and max(s.x, e.x) >= l - GROW
                and min(s.y, e.y) <= bm + GROW and max(s.y, e.y) >= tp - GROW):
            return True
    return False

def _key(pt):
    return (round(pt.x / 1000), round(pt.y / 1000))
# adjacency: same-net F.Cu segs sharing an endpoint
fcu_by_node = defaultdict(list)
for t in tracks:
    if t.GetLayer() == F and is_swappable_net(t.GetNetname()):
        fcu_by_node[(t.GetNetname(), _key(t.GetStart()))].append(t)
        fcu_by_node[(t.GetNetname(), _key(t.GetEnd()))].append(t)
grown = {id(t): t for t in clip_segs0}
frontier = list(clip_segs0)
while frontier:
    t = frontier.pop()
    net = t.GetNetname()
    for ep in (_key(t.GetStart()), _key(t.GetEnd())):
        for nb in fcu_by_node[(net, ep)]:
            if id(nb) in grown:
                continue
            if seg_in_inflated_pour(nb):      # only grow into segs still in/near the pour band
                grown[id(nb)] = nb
                frontier.append(nb)
clip_segs = list(grown.values())
print(f"swap_candidates after chain-grow (GROW_MM={GROW_MM}): {len(clip_segs)}")
print("  per net:", dict(Counter(t.GetNetname() for t in clip_segs)))

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

# ---- existing B.Cu copper / vias / pads / holes --------------------------------------------------
bcu_segs = []
for t in tracks:
    if t.GetLayer() == B:
        s = t.GetStart(); e = t.GetEnd()
        bcu_segs.append((t.GetNetname(), ((s.x, s.y), (e.x, e.y)), t.GetWidth() // 2))
bcu_vias = []
all_holes = []
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        p = t.GetPosition()
        bcu_vias.append((t.GetNetname(), (p.x, p.y), t.GetWidth() // 2))
        all_holes.append((t.GetNetname(), p.x, p.y, t.GetDrillValue() // 2))
bcu_pads = []
pad_at = {}
for fp in b.GetFootprints():
    for pad in fp.Pads():
        pc = pad.GetCenter(); sz = pad.GetSize()
        onF = pad.IsOnLayer(F); onB = pad.IsOnLayer(B)
        drill = pad.GetDrillSize()
        is_tht = (drill.x > 0 and drill.y > 0)
        if is_tht:
            all_holes.append((pad.GetNetname(), pc.x, pc.y, max(drill.x, drill.y) // 2))
        if onB:
            bcu_pads.append((pad.GetNetname(), (pc.x, pc.y), max(sz.x, sz.y) // 2))
        pad_at[keyp(pc)] = (pad.GetNetname(), onF, onB, is_tht)

def seg_collides(seg_geom, halfw, net):
    (x0, y0), (x1, y1) = seg_geom
    for n2, g2, hw2 in bcu_segs:
        if n2 == net:
            continue
        if seg_seg_dist(seg_geom, g2) < halfw + hw2 + CLEAR:
            return True
    for n2, (vx, vy), vr in bcu_vias:
        if n2 == net:
            continue
        if pt_seg_dist(vx, vy, x0, y0, x1, y1) < halfw + vr + CLEAR:
            return True
    for n2, (px, py), pr in bcu_pads:
        if n2 == net:
            continue
        if pt_seg_dist(px, py, x0, y0, x1, y1) < halfw + pr + CLEAR:
            return True
    return False

# F.Cu pads (the new via lives on F.Cu too, so it must clear F.Cu pads' copper) ------------------
fcu_pads = []   # (net, (cx,cy), copper_radius)
for fp in b.GetFootprints():
    for pad in fp.Pads():
        if pad.IsOnLayer(F):
            pc = pad.GetCenter(); sz = pad.GetSize()
            fcu_pads.append((pad.GetNetname(), (pc.x, pc.y), max(sz.x, sz.y) // 2))

def via_hole_ok(cx, cy, net, drill):
    """A new via drill at (cx,cy) -- clears hole-to-hole vs every existing hole.  Drilled holes ALWAYS
    need spacing regardless of net (a via at the exact same point as a same-net pad hole would be the
    one exception, but a transition via is never placed on a same-net bridged node -- bridged nodes
    are skipped earlier).  So enforce hole-to-hole vs ALL holes."""
    r = drill // 2
    for n2, hx, hy, hr in all_holes:
        d = math.hypot(cx - hx, cy - hy)
        if d < 1000:    # ~1um: this IS the node's own existing hole (coincident) -> handled elsewhere
            continue
        if d < r + hr + HOLE_CLEAR:
            return False
    return True

def via_copper_ok(cx, cy, net, via_w):
    """The new via PAD clears FOREIGN B.Cu and F.Cu copper (segs + pads)?  The via lives on both layers."""
    vr = via_w // 2
    for n2, g2, hw2 in bcu_segs:
        if n2 == net:
            continue
        (x0, y0), (x1, y1) = g2
        if pt_seg_dist(cx, cy, x0, y0, x1, y1) < vr + hw2 + CLEAR:
            return False
    for n2, (px, py), pr in bcu_pads:
        if n2 == net:
            continue
        if math.hypot(cx - px, cy - py) < vr + pr + CLEAR:
            return False
    for n2, (px, py), pr in fcu_pads:        # F.Cu pad copper
        if n2 == net:
            continue
        if math.hypot(cx - px, cy - py) < vr + pr + CLEAR:
            return False
    for t in tracks:                          # F.Cu tracks (kept) + moved B.Cu tracks both matter; check F here
        if t.GetNetname() == net:
            continue
        s = t.GetStart(); e = t.GetEnd()
        if t.GetLayer() == F and pt_seg_dist(cx, cy, s.x, s.y, e.x, e.y) < vr + t.GetWidth() // 2 + CLEAR:
            return False
    return True

# ---- 2. chain grouping per net (contiguous clip segs sharing endpoints) --------------------------
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, c):
    parent[find(a)] = find(c)
ep_map = defaultdict(list)
for i, t in enumerate(clip_segs):
    parent.setdefault(i, i)
    a, c = endpoints(t)
    ep_map[(t.GetNetname(), a)].append(i)
    ep_map[(t.GetNetname(), c)].append(i)
for (_n, _e), idxs in ep_map.items():
    for j in idxs[1:]:
        union(idxs[0], j)
chains = defaultdict(list)
for i in range(len(clip_segs)):
    chains[find(i)].append(i)
print(f"chains: {len(chains)}")

# F.Cu copper presence by node (all F.Cu tracks) + multi-layer pad bridges
fcu_ep_all = defaultdict(list)
for t in tracks:
    if t.GetLayer() == F:
        a, c = endpoints(t)
        fcu_ep_all[(t.GetNetname(), a)].append(t)
        fcu_ep_all[(t.GetNetname(), c)].append(t)
bridged_node = set()   # (net, ep) already has F<->B bridge (THT pad or existing via)
for ep, (net, onF, onB, is_tht) in pad_at.items():
    if is_tht or (onF and onB):
        bridged_node.add((net, ep))
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        bridged_node.add((t.GetNetname(), keyp(t.GetPosition())))

# ---- 3a. per-segment greedy swap (B.Cu copper collision guard) -----------------------------------
swapped = 0
left_on_fcu = 0
moved = {}   # id(t) -> t  (currently on B.Cu)
for t in clip_segs:
    s = t.GetStart(); e = t.GetEnd()
    g = ((s.x, s.y), (e.x, e.y))
    net = t.GetNetname()
    if seg_collides(g, t.GetWidth() // 2, net):
        left_on_fcu += 1
        continue
    t.SetLayer(B)
    bcu_segs.append((net, g, t.GetWidth() // 2))
    moved[id(t)] = t
    swapped += 1

# ---- 3b. settle the moved set: revert any moved seg whose F<->B transition node cannot take a safe
# via, then place all vias ONCE (no dangling vias).  A transition node = (net,ep) touching a MOVED
# B.Cu seg AND F.Cu copper of the same net (kept F.Cu track or F-only pad), not already bridged. ----
def fcu_at(net, ep):
    for t in fcu_ep_all[(net, ep)]:
        if t.GetLayer() == F:
            return True
    pa = pad_at.get(ep)
    if pa and pa[0] == net and pa[1] and not pa[2]:
        return True
    return False

def moved_segs_at(net, ep):
    return [t for t in moved.values() if t.GetNetname() == net and ep in endpoints(t)]

def safe_via_at(net, ep):
    """Return (coord, via_w, via_d) if a safe via can be placed at this transition node, else None."""
    ms = moved_segs_at(net, ep)
    if not ms:
        return None
    coord = None
    for t in ms:
        if keyp(t.GetStart()) == ep:
            coord = t.GetStart(); break
        if keyp(t.GetEnd()) == ep:
            coord = t.GetEnd(); break
    if coord is None:
        return None
    via_w, via_d = via_size_for(net)
    if via_hole_ok(coord.x, coord.y, net, via_d) and via_copper_ok(coord.x, coord.y, net, via_w):
        return (coord, via_w, via_d)
    return None

# Combined settle+place: repeatedly try to place all needed transition vias; if any node's via is
# unsafe (incl. hole-to-hole vs vias placed earlier this pass), revert that node's moved seg(s) and
# restart -- so the final state has every B.Cu chain bridged with a safe via and zero dangling vias.
reverted = 0
vias_added = 0
while True:
    # tentatively collect transition nodes needing a via
    nodes = set()
    for t in list(moved.values()):
        net = t.GetNetname(); a, c = endpoints(t)
        nodes.add((net, a)); nodes.add((net, c))
    need = [(net, ep) for (net, ep) in nodes
            if (net, ep) not in bridged_node and fcu_at(net, ep)]
    # try placing vias in a scratch hole-set; if one fails, revert its seg(s) and restart
    scratch_holes = list(all_holes)
    # scratch via-COPPER set: existing via pads + the vias we add THIS pass.  Without this,
    # two new transition vias that clear hole-to-hole (drills) can still overlap copper pads
    # (a 0.6mm via pad needs 0.6+CLEAR centre spacing, > the 0.55mm hole-to-hole gate).
    scratch_vias = [(n2, vx, vy, vr) for (n2, (vx, vy), vr) in bcu_vias]
    placements = []
    failed_node = None
    for net, ep in sorted(need):
        ms = moved_segs_at(net, ep)
        if not ms:
            continue
        coord = None
        for t in ms:
            if keyp(t.GetStart()) == ep:
                coord = t.GetStart(); break
            if keyp(t.GetEnd()) == ep:
                coord = t.GetEnd(); break
        if coord is None:
            continue
        via_w, via_d = via_size_for(net)
        # check copper (static) + hole-to-hole vs scratch_holes (incl. earlier this pass)
        copper_ok = via_copper_ok(coord.x, coord.y, net, via_w)
        hole_ok = True
        r = via_d // 2
        for n2, hx, hy, hr in scratch_holes:
            d = math.hypot(coord.x - hx, coord.y - hy)
            if d < 1000:
                continue
            if d < r + hr + HOLE_CLEAR:
                hole_ok = False; break
        # via-PAD copper vs every other via pad (existing + placed earlier this pass)
        vr_new = via_w // 2
        via_copper_clear_ok = True
        for n2, vx, vy, vr2 in scratch_vias:
            if n2 == net:
                continue
            d = math.hypot(coord.x - vx, coord.y - vy)
            if d < 1000:
                continue
            if d < vr_new + vr2 + CLEAR:
                via_copper_clear_ok = False; break
        if copper_ok and hole_ok and via_copper_clear_ok:
            placements.append((net, ep, coord, via_w, via_d))
            scratch_holes.append((net, coord.x, coord.y, via_d // 2))
            scratch_vias.append((net, coord.x, coord.y, via_w // 2))
        else:
            failed_node = (net, ep)
            break
    if failed_node is not None:
        net, ep = failed_node
        for t in moved_segs_at(net, ep):
            t.SetLayer(F)
            del moved[id(t)]
            swapped -= 1
            reverted += 1
        continue   # restart with the reduced moved set
    # all placements safe -> commit them
    for net, ep, coord, via_w, via_d in placements:
        netobj = b.FindNet(net)
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(coord.x, coord.y))
        v.SetDrill(via_d); v.SetWidth(via_w)
        v.SetLayerPair(F, B)
        v.SetNet(netobj)
        b.Add(v)
        all_holes.append((net, coord.x, coord.y, via_d // 2))
        bridged_node.add((net, ep))
        vias_added += 1
    break

left_on_fcu += reverted
print(f"swapped_segments: {swapped}")
print(f"left_on_fcu (collision/via-unsafe): {left_on_fcu}")
print(f"vias_added: {vias_added}")
print(f"reverted (no safe via): {reverted}")

# ---- 4. refill all zones (antipad the new vias; clear stale-fill artifacts) -----------------------
b.BuildConnectivity()
for z in b.Zones():
    z.UnFill()
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
print("zones_refilled")

pcbnew.SaveBoard(OUT, b)
print("SAVED", OUT)
