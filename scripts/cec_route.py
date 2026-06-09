#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_route -- pcbnew-backed REAL-COPPER routing primitives for the candidate
#               routing sub-agent pass (companion to cec_pcb.py).
# ============================================================================
# NOT cec_routeR: you may want the other file (R-10). cec_route (this file) =
# hand-routing PRIMITIVES (track/via/zone/fill/verify) for a sub-agent pass;
# cec_router.py = the route() ORCHESTRATION loop (Freerouting candidates +
# gates + decision log) that route.yml runs.
# ============================================================================
# Unlike cec_pcb.guides() (non-copper guide graphics on user layers), this emits
# ACTUAL routed copper through the real KiCad 10 engine (the same one the GUI uses):
#   * PCB_TRACK segments with net + width + layer,
#   * PCB_VIA with drill/pad/net/layer-pair,
#   * ZONE pours that are FILLED by the real ZONE_FILLER (kicad-cli cannot fill).
# Verification is the real connectivity + DRC engine (via kicad-cli on the saved board).
#
# This is the engine the ROUTING SUB-AGENT drives to realize a routing game-plan as
# real copper, find the snags (DRC shorts / clearance / unroutable escapes / unfilled
# ratlines), and report what the footprint/placement or game-plan agents must change.
# See the workflow + go-ahead in CLAUDE.md ("Sub-agent routing pass").
#
# CLEANLINESS RULES (candidate routing = CLEAN, not COMPLETE). The goal is to keep the
# VITAL runs' areas clean and fit the non-vital, annoying-to-place runs into the leftover
# space without intruding -- not to route every net. The Router enforces/verifies:
#   R1 vital keep-out  -- mark_vital()+keepout(): non-vital runs may not enter the reserved
#                         vital areas (12V pours, Kelvin windows, GND fanouts); run() reports
#                         any keep-out hit, check_keepouts() verifies the final result.
#   R2 layer complement-- route non-vital on the layer the vital copper isn't using in a region.
#   R3 lane discipline -- lanes(): one lane per net so same-layer runs don't overlap/criss-cross.
#   R4 clean terminate -- to_pad(): a run ends on a layer its target pad is ON; a layer change
#                         vias in clear channel space, never on a fine-pitch pad, and never a
#                         track ending inside a pad on the wrong layer. check_terminations() finds
#                         that bug. Route the vital nets FIRST (reserve), then the non-vital ones.
import os, sys, json, subprocess, math, tempfile
import pcbnew

MM = 1_000_000                       # nm per mm
def _nm(v): return int(round(v * MM))
def _vec(x, y): return pcbnew.VECTOR2I(_nm(x), _nm(y))

def _seg_seg(a, b, c, d):
    def ccw(p, q, r): return (r[1]-p[1])*(q[0]-p[0]) - (q[1]-p[1])*(r[0]-p[0])
    return (ccw(a, c, d) * ccw(b, c, d) <= 0) and (ccw(a, b, c) * ccw(a, b, d) <= 0)

def _seg_box(p1, p2, box):
    """True if segment p1-p2 intersects/enters the axis-aligned box (x0,y0,x1,y1)."""
    x0, y0, x1, y1 = box
    for (px, py) in (p1, p2):
        if x0 <= px <= x1 and y0 <= py <= y1:
            return True
    e = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    return any(_seg_seg(p1, p2, s, t) for s, t in e)

def lanes(nets, y0, dy):
    """Rule helper -- one lane per net so same-layer runs don't overlap: {net: y0 + i*dy}."""
    return {n: y0 + i * dy for i, n in enumerate(nets)}

class Router:
    """Thin pcbnew wrapper: load a board, lay real tracks/vias/zones, fill, verify."""
    def __init__(self, path):
        self.path = path
        self.b = pcbnew.LoadBoard(path)
        self._nets = {n.GetNetname(): n.GetNetCode()
                      for n in self.b.GetNetInfo().NetsByNetcode().values()}
        self.added = {"tracks": 0, "vias": 0, "zones": 0}
        self.vital = set()       # nets whose copper must stay clean (12V/Kelvin/GND)
        self.keepouts = []       # (name, x0,y0,x1,y1, {layer_ids}) reserved for the vital runs
        self._runs = []          # (net, layer_name, [pts]) -- recorded for the rule checks

    # ---- lookups ----
    def net(self, name):
        if name not in self._nets:
            raise KeyError(f"net {name!r} not on board (have {len(self._nets)} nets)")
        return self._nets[name]

    def layer(self, name):
        lid = self.b.GetLayerID(name)
        if lid < 0:
            raise KeyError(f"layer {name!r} not found")
        return lid

    def pad(self, ref, padnum):
        """Pad centre (mm, mm) of footprint `ref` pad `padnum`."""
        fp = self.b.FindFootprintByReference(ref)
        if not fp:
            raise KeyError(f"footprint {ref!r} not found")
        p = fp.FindPadByNumber(str(padnum))
        if not p:
            raise KeyError(f"{ref} pad {padnum} not found")
        pos = p.GetPosition()
        return (pos.x / MM, pos.y / MM)

    # ---- emit copper ----
    def track(self, net, pts, layer="F.Cu", width=0.25):
        nc, ly, w = self.net(net), self.layer(layer), _nm(width)
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(_vec(x1, y1)); t.SetEnd(_vec(x2, y2))
            t.SetWidth(w); t.SetLayer(ly); t.SetNetCode(nc)
            self.b.Add(t); self.added["tracks"] += 1

    def via(self, net, at, drill=0.5, dia=0.9, layers=("F.Cu", "B.Cu")):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(_vec(*at)); v.SetDrill(_nm(drill)); v.SetWidth(_nm(dia))
        v.SetLayerPair(self.layer(layers[0]), self.layer(layers[1]))
        v.SetNetCode(self.net(net)); self.b.Add(v); self.added["vias"] += 1

    def zone(self, net, poly, layers=("F.Cu",), clearance=0.2, min_width=0.25, priority=0):
        """Add a copper pour (filled later by fill())."""
        z = pcbnew.ZONE(self.b)
        ls = pcbnew.LSET()
        for L in layers:
            ls.AddLayer(self.layer(L))
        z.SetLayerSet(ls)
        z.SetNetCode(self.net(net))
        z.SetLocalClearance(_nm(clearance))
        z.SetMinThickness(_nm(min_width))
        z.SetAssignedPriority(priority)
        # Append straight into the zone's OWN outline. SetOutline(<external SHAPE_POLY_SET>)
        # ALIASES (not deep-copies) in this KiCad-10 SWIG build, so an external poly goes
        # empty when GC'd -> ZONE_FILLER then segfaults. Appending in place avoids that.
        # (Validity is FullPointCount(), not GetOutlineArea() -- the latter reads a stale
        # cache and returns 0 right after Append even with a valid outline.)
        o = z.Outline(); o.NewOutline()
        for (x, y) in poly:
            o.Append(_nm(x), _nm(y))
        if z.Outline().FullPointCount() < 3:
            raise RuntimeError(f"zone outline for net {net} has < 3 points")
        self.b.Add(z); self.added["zones"] += 1
        return z

    # ---- routing rules: keep the non-vital runs out of the vital areas, terminate clean ----
    # Goal: CLEAN candidate, not COMPLETE routing. Reserve the vital runs (12V pours, the Kelvin
    # sense windows, the GND fanouts) as keep-outs; fit the non-vital signal runs into the
    # leftover channels WITHOUT entering those keep-outs, each in its own lane, ending on a layer
    # its target pad is actually on. The two checks verify the rules held.
    def mark_vital(self, *nets):
        """Declare nets whose copper is VITAL (must stay clean)."""
        self.vital.update(nets); return self

    def keepout(self, name, x0, y0, x1, y1, layers=("F.Cu", "B.Cu")):
        """Reserve a vital area: non-vital runs may not enter (x0,y0)-(x1,y1) on `layers`.
        Register the 12V pour columns, the Kelvin windows, and any must-stay-clear region."""
        self.keepouts.append((name, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1),
                              {self.layer(L) for L in layers}))
        return self

    def pad_layers(self, ref, num):
        """Copper-layer ids a pad connects on (F.Cu only for a front SMD pad; all for THT)."""
        fp = self.b.FindFootprintByReference(ref); p = fp.FindPadByNumber(str(num))
        return {L for L in p.GetLayerSet().Seq() if pcbnew.IsCopperLayer(L)}

    def run(self, net, pts, layer="F.Cu", width=0.25):
        """Lay a non-vital signal run + RECORD it for the rule checks. Returns the keep-out
        segments it hit (empty list == clean) so the caller can re-route before committing."""
        self.track(net, pts, layer, width)
        ly = self.layer(layer); self._runs.append((net, layer, list(pts)))
        hit = []
        if net not in self.vital:
            for a, c in zip(pts, pts[1:]):
                for ko in self.keepouts:
                    if ly in ko[5] and _seg_box(a, c, ko[1:5]):
                        hit.append({"net": net, "keepout": ko[0], "seg": (a, c)})
        return hit

    def to_pad(self, net, ref, num, approach, approach_layer="F.Cu", width=0.25, drill=0.4, dia=0.7):
        """Terminate a run INTO a pad on a layer the pad is on. If `approach_layer` isn't a pad
        layer, the layer-change VIA goes at `approach` (clear channel space) and the FINAL segment
        runs on the pad's layer -- never a via on a fine-pitch pad, never a track ending inside a
        pad on a layer the pad isn't on. Returns the pad centre."""
        pc = self.pad(ref, num); pls = self.pad_layers(ref, num); al = self.layer(approach_layer)
        if al in pls:
            self.run(net, [approach, pc], approach_layer, width)
        else:
            dst = "F.Cu" if self.layer("F.Cu") in pls else ("B.Cu" if self.layer("B.Cu") in pls else approach_layer)
            self.via(net, approach, drill, dia, (approach_layer, dst))
            self.run(net, [approach, pc], dst, width)
        return pc

    def check_keepouts(self):
        """Rule 1+2: every recorded non-vital run vs the vital keep-outs. Returns violations."""
        bad = []
        for net, layer, pts in self._runs:
            if net in self.vital:
                continue
            ly = self.layer(layer)
            for a, c in zip(pts, pts[1:]):
                for ko in self.keepouts:
                    if ly in ko[5] and _seg_box(a, c, ko[1:5]):
                        bad.append({"net": net, "keepout": ko[0], "layer": layer, "seg": (a, c)})
        return bad

    def check_terminations(self):
        """Rule 4: find track endpoints that land INSIDE a pad on a layer the pad is NOT on
        (the 'run terminates in a pad on the wrong layer' bug). Returns violations."""
        bad = []
        pads = [p for fp in self.b.GetFootprints() for p in fp.Pads()]
        for t in self.b.GetTracks():
            if t.Type() != pcbnew.PCB_TRACE_T:        # skip vias/arcs
                continue
            ly = t.GetLayer()
            for end in (t.GetStart(), t.GetEnd()):
                on = [p for p in pads if p.HitTest(end)]
                if on and not any(p.IsOnLayer(ly) for p in on):
                    bad.append({"net": t.GetNetname(), "layer": self.b.GetLayerName(ly),
                                "at": (end.x / MM, end.y / MM),
                                "pads": sorted({p.GetParentFootprint().GetReference() + "." + p.GetNumber() for p in on})})
        return bad

    # ---- engine ops ----
    def fill(self):
        """Fill every zone with the real ZONE_FILLER (the GUI's engine). UnFill first:
        re-filling an already-filled multi-layer zone in the same process segfaults."""
        for z in self.b.Zones():
            z.UnFill()
        return pcbnew.ZONE_FILLER(self.b).Fill(self.b.Zones())

    def save(self, path=None):
        pcbnew.SaveBoard(path or self.path, self.b)

    def verify(self, tmp=None):
        """Save + run the real DRC/connectivity engine (kicad-cli). Returns a dict
        with structural violations and unconnected ratlines -- the snag inputs."""
        if tmp is None:                       # cross-platform (no hardcoded /tmp -- absent on Windows)
            tmp = os.path.join(tempfile.gettempdir(), "cec_route_drc.json")
        self.save()
        subprocess.run(["kicad-cli", "pcb", "drc", "--exit-code-violations",
                        "--format", "json", "-o", tmp, self.path],
                       capture_output=True)
        d = json.load(open(tmp))
        v = d.get("violations", [])
        cosmetic = ("silk_overlap", "silk_over_copper", "silk_edge_clearance",
                    "lib_footprint_mismatch", "lib_footprint_issues")
        struct = [x for x in v if x["type"] not in cosmetic]
        return {"structural": struct, "unconnected": d.get("unconnected_items", []),
                "n_struct": len(struct), "n_unconnected": len(d.get("unconnected_items", []))}

if __name__ == "__main__":
    # smoke test on the EPS board: fill the existing GND zone, lay one track + via, verify.
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    import shutil
    src = f"{ROOT}/modules/eps-8pin/eps8pin-module.kicad_pcb"
    test = os.path.join(tempfile.gettempdir(), "cec_route_smoke.kicad_pcb"); shutil.copy(src, test)
    # the .kicad_pro/.dru sit next to the source; copy DRC context too
    for ext in (".kicad_pro", ".kicad_dru"):
        s = src.replace(".kicad_pcb", ext)
        if os.path.exists(s): shutil.copy(s, test.replace(".kicad_pcb", ext))
    r = Router(test)
    print("nets:", len(r._nets), "| fill:", r.fill())
    r.track("GND", [r.pad("J_IN1", "1"), (r.pad("J_IN1", "1")[0], r.pad("J_IN1", "1")[1] + 2)], "F.Cu", 0.5)
    r.via("GND", (r.pad("J_IN1", "1")[0], r.pad("J_IN1", "1")[1] + 2))
    print("added:", r.added)
    res = r.verify()
    print(f"verify: structural={res['n_struct']}  unconnected={res['n_unconnected']}")
