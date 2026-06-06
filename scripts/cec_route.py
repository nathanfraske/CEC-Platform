#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_route -- pcbnew-backed REAL-COPPER routing primitives for the candidate
#               routing sub-agent pass (companion to cec_pcb.py).
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
import os, sys, json, subprocess, math
import pcbnew

MM = 1_000_000                       # nm per mm
def _nm(v): return int(round(v * MM))
def _vec(x, y): return pcbnew.VECTOR2I(_nm(x), _nm(y))

class Router:
    """Thin pcbnew wrapper: load a board, lay real tracks/vias/zones, fill, verify."""
    def __init__(self, path):
        self.path = path
        self.b = pcbnew.LoadBoard(path)
        self._nets = {n.GetNetname(): n.GetNetCode()
                      for n in self.b.GetNetInfo().NetsByNetcode().values()}
        self.added = {"tracks": 0, "vias": 0, "zones": 0}

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

    # ---- engine ops ----
    def fill(self):
        """Fill every zone with the real ZONE_FILLER (the GUI's engine). UnFill first:
        re-filling an already-filled multi-layer zone in the same process segfaults."""
        for z in self.b.Zones():
            z.UnFill()
        return pcbnew.ZONE_FILLER(self.b).Fill(self.b.Zones())

    def save(self, path=None):
        pcbnew.SaveBoard(path or self.path, self.b)

    def verify(self, tmp="/tmp/cec_route_drc.json"):
        """Save + run the real DRC/connectivity engine (kicad-cli). Returns a dict
        with structural violations and unconnected ratlines -- the snag inputs."""
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
    test = "/tmp/cec_route_smoke.kicad_pcb"; shutil.copy(src, test)
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
