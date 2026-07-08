#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
PlacementSession -- the declarative INTENT-COMPILER for structure-first placement
(placer-feasibility SLICE-1b; docs/placer-feasibility-2026-06-30.md).

This is NOT a new placement engine. It is a thin DECLARATIVE BUILDER over the EXISTING
cec_synth_pipeline primitives, adding the one lever the 2026-06-14 corridor-reseed anneal
lacked and graded the wrong way:

  (1) a GLOBAL, agent-issued PARTITION -- free parts assigned to named regions, enforced
      as PROACTIVE HARD containment (seeded in-region before the anneal, confined by every
      legalize pass), NOT a reactive per-part evict / SA jitter; and
  (2) grading by the ROUTE-ORACLE (cec_synth_pipeline.route_oracle_grade -- the real
      post-route accept conjunction), NOT HPWL / corridor_cross (the documented false summits).

The session compiles to a cec_synth_pipeline.Candidate via synth_one(partition=...): all the
proven assembly (seat corridors -> seat kelvin -> seat antenna -> cluster -> relative-place ->
anneal -> evacuate -> legalize) is REUSED unchanged; the partition only adds region containment,
gated so partition=None is byte-identical to the un-partitioned placer.

Typical agent use (issue intents, then grade; fan out over orderings with snapshot/rollback):

    s = PlacementSession("eps-8pin", W=96, H=37)
    s.half("periph", "x", 0.58, 1.00)          # right ~42% half-plane = the electronics core
    s.half("cables", "x", 0.00, 0.58)          # left = the per-cable corridors
    s.assign(s.peripheral_ics(), "periph")     # ESP / CAN / LDO / buttons -> right
    s.assign(s.cable_parts(),    "cables")     # INA / comparator / shunts  -> left
    cand    = s.compile()                      # -> cec_synth_pipeline.Candidate
    verdict = s.grade()                        # -> route_oracle_grade dict (the real gate)

    snap = s.snapshot(); s.assign(["U2"], "cables"); v2 = s.grade(); s.rollback(snap)

The AUTONOMY test (the milestone's falsifiable primary) fans out over intent ORDERINGS/
GROUPINGS an AGENT proposes, grading every survivor by the oracle and keeping the best by
its sort_key -- see autonomy_search().
"""
import copy
import dataclasses
import os
import sys
import tempfile
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_synth_pipeline as csp


# Nets that are board-global rails/buses (high fan-out) -- excluded when walking the per-cable
# sense chain so the BFS does not bleed from a shunt into the ESP/CAN/LDO via a shared rail.
_GLOBAL_NET_HINTS = ("GND", "+3V3", "+5VSB", "+5V", "VBUS", "VCC", "VDD",
                     "I2C", "SCL", "SDA", "CAN", "USB", "EN", "BOOT", "3V3")


class PlacementSession:
    """A declarative placement-intent builder. Holds the netlist context + the agent's partition
    (regions + assignment); compile()/grade() run the real placer + the route-oracle."""

    def __init__(self, board, W, H, *, profile="consumer", params=None, pins=None,
                 strat="dataflow", seed=0):
        self.cfg = csp.Config.load(board, profile=profile,
                                   params=dict(params or {}), pins=dict(pins or {}))
        self.board = board
        self.W, self.H = float(W), float(H)
        self.strat, self.seed = strat, int(seed)
        self.nl = csp.View(self.cfg).nl
        self.anchors_roles, self.ics, self.shunts, self.passives = csp._classify(self.nl)
        self._regions = {}        # name -> (x0, y0, x1, y1)  (absolute mm)
        self._assign = {}         # ref  -> region name        (the partition)
        self.log = []
        self._near = []
        self._order = []             # intent trace (reproducibility / audit)

    # ----------------------------------------------------------------- region geometry
    def region(self, name, box):
        """Define a named region as an absolute (x0, y0, x1, y1) box (mm)."""
        x0, y0, x1, y1 = box
        self._regions[name] = (float(x0), float(y0), float(x1), float(y1))
        self.log.append(("region", name, self._regions[name]))
        return self

    def frac(self, fx0, fy0, fx1, fy1):
        """A box from board FRACTIONS -> absolute mm (0,0 = top-left, KiCad y-down)."""
        return (fx0 * self.W, fy0 * self.H, fx1 * self.W, fy1 * self.H)

    def half(self, name, axis, lo, hi):
        """Define a region as a fractional half-plane band. axis 'x' -> vertical band [lo,hi]*W
        spanning full height; axis 'y' -> horizontal band [lo,hi]*H spanning full width."""
        if axis in ("x", "X"):
            return self.region(name, (lo * self.W, 0.0, hi * self.W, self.H))
        return self.region(name, (0.0, lo * self.H, self.W, hi * self.H))

    # ----------------------------------------------------------------- assignment (partition)
    def assign(self, refs, region):
        """Assign part(s) to a region (HARD containment). The region must already be defined."""
        if region not in self._regions:
            raise KeyError("assign to undefined region %r -- define it first" % region)
        if isinstance(refs, str):
            refs = [refs]
        refs = list(refs)
        for r in refs:
            self._assign[r] = region
        self.log.append(("assign", refs, region))
        return self

    def near(self, ref, target, *, gap=0.8):
        """ADJACENCY intent (owner lever pass 2026-07-08): place *ref* directly beside
        *target* (a seated/placed part), at the nearest lane-free slot. Compiles through
        cfg.params['near_intents']; inert when unused (golden safety)."""
        self._near.append((str(ref), str(target), float(gap)))
        self.log.append(("near", ref, target, gap))
        return self

    def order(self, refs, axis="x"):
        """ORDERING intent: the refs' final positions along *axis* preserve the given
        sequence (a permutation fix after placement -- positions are re-assigned among
        the same slots, so density/overlap character is unchanged)."""
        self._order.append((list(refs), str(axis)))
        self.log.append(("order", list(refs), axis))
        return self

    def unassign(self, refs):
        if isinstance(refs, str):
            refs = [refs]
        for r in refs:
            self._assign.pop(r, None)
        self.log.append(("unassign", list(refs)))
        return self

    # ----------------------------------------------------------------- part-set ergonomics
    def _local_nets(self, max_fanout=4):
        """Per-cable sense nets are low fan-out (a shunt tap touches 2-3 parts); the power/GND/I2C/
        CAN rails touch many. 'Local' nets = low fan-out AND not a named global rail."""
        out = set()
        for net, members in self.nl.nets.items():
            nm = (net or "").upper()
            if any(h in nm for h in _GLOBAL_NET_HINTS):
                continue
            if 0 < len(members) <= max_fanout:
                out.add(net)
        return out

    def antenna_ics(self):
        """The RF-module IC(s) (ESP32) -- seated at the antenna edge by the placer, so NOT freely
        partition-able (matches synth_one's _seat_antenna_ic / drop_kc keyed on 'esp32')."""
        comps = csp._fp_of(self.nl)
        return [r for r in self.ics if "esp32" in str(comps.get(r, "")).lower()]

    def cable_part_set(self):
        """The per-cable sense/detection chain {shunts + INA238 + INA181 + comparator}, derived
        structurally (position-free): SEED from the shunts plus every IC on a Kelvin/SENSEC net
        (the INA238/INA181 that tap the shunt -- the SENSEC force net is too high-fan-out to walk),
        then BFS one+ hops over LOCAL low-fan-out non-rail nets to catch the downstream comparator
        (INA181 -> DETAMP -> TLV). Stays out of the ESP/CAN/LDO (they connect only via rails)."""
        kelvin_nets = {n for pair in (csp._kelvin_pairs(self.nl) or []) for n in pair}
        # WALLS: stop the BFS at the antenna ESP and the buttons -- the detection signal path
        # (TLV DET -> ESP GPIO, button BOOT -> ESP GPIO) would otherwise bleed the core Ics into
        # the cable chain. Reach them but never expand THROUGH them; drop them from the result.
        walls = set(self.antenna_ics()) | {r for r in self.ics if r.startswith("SW")}
        seed = set(self.shunts)
        for net, members in self.nl.nets.items():
            if net in kelvin_nets:
                seed |= {ref for ref, _p in members if ref in self.ics}
        local = self._local_nets()
        comp_nets = defaultdict(set)
        net_comps = defaultdict(set)
        for net, members in self.nl.nets.items():
            if net not in local:
                continue
            for ref, _pad in members:
                comp_nets[ref].add(net)
                net_comps[net].add(ref)
        seen = set(seed)
        frontier = set(seed) - walls
        while frontier:
            nxt = set()
            for c in frontier:
                for net in comp_nets.get(c, ()):
                    nxt |= (net_comps[net] - seen)
            seen |= nxt
            frontier = nxt - walls               # reach a wall but do not expand through it
        return sorted(r for r in seen if (r in self.ics or r in self.shunts) and r not in walls)

    def cable_parts(self):
        return self.cable_part_set()

    def peripheral_ics(self):
        """The FREE electronics-core ICs (CAN / LDO / buttons) -- ICs that are NEITHER in the
        per-cable sense chain NOR the antenna-seated ESP. These are the parts the partition can
        actually push to the periphery region (the seated cable chain + ESP are pinned by seats)."""
        excluded = set(self.cable_part_set()) | set(self.antenna_ics())
        return [r for r in self.ics if r not in excluded]

    def seated_refs(self):
        """The placer's FIXED set (connectors + seated cable chain + antenna ESP): these are pinned
        by seats, so a partition assignment is INERT for them (reported, not a containment failure)."""
        return set(self.anchors_roles) | set(self.cable_part_set()) | set(self.antenna_ics())

    # ----------------------------------------------------------------- the partition spec
    def partition(self):
        """The {regions, assignment} dict consumed by synth_one(partition=...). {} regions -> None
        (no containment), so a session with no assign() compiles byte-identically to the placer."""
        if not self._assign:
            return None
        return {"regions": dict(self._regions), "assignment": dict(self._assign)}

    # ----------------------------------------------------------------- snapshot / rollback
    def snapshot(self):
        """Capture the partition state (regions + assignment + log) for rollback during fan-out."""
        return (copy.deepcopy(self._regions), copy.deepcopy(self._assign), list(self.log))

    def rollback(self, snap):
        self._regions = copy.deepcopy(snap[0])
        self._assign = copy.deepcopy(snap[1])
        self.log = list(snap[2])
        return self

    # ----------------------------------------------------------------- compile / materialize / grade
    def _cfg_dict(self):
        d = dataclasses.asdict(self.cfg)
        if self._near:
            d.setdefault("params", {})["near_intents"] = list(self._near)
        if self._order:
            d.setdefault("params", {})["order_intents"] = list(self._order)
        return d

    def compile(self, *, strat=None, seed=None):
        """Run the real placer with the agent's partition -> a cec_synth_pipeline.Candidate.
        partition=None (no assign) is byte-identical to the un-partitioned placer."""
        return csp.synth_one(self._cfg_dict(), self.W, self.H,
                             strat or self.strat, self.seed if seed is None else seed,
                             partition=self.partition())

    def materialize(self, out, *, cand=None):
        """Write the compiled placement to a real .kicad_pcb (for routing / grading / render)."""
        cand = cand or self.compile()
        return csp.materialize(cand, self.cfg, out)

    def containment_report(self, cand=None):
        """Audit the HARD containment. For every assigned ref: {ref: (region, inside, governed, (ccx,ccy))}
        where *governed* is True for a FREE part (the partition can move it -> inside MUST hold) and
        False for a SEAT-pinned part (connector / cable chain / ESP -- the assignment is inert, inside
        is informational). free_violations() is the real teeth: a governed part outside its region."""
        cand = cand or self.compile()
        seated = self.seated_refs()
        rep = {}
        comps = csp._fp_of(self.nl)
        for ref, region in self._assign.items():
            if ref not in cand.P or ref not in comps:
                continue
            x, y, rot = cand.P[ref]
            cx, cy, _hw, _hh = csp._courtyard_info(comps[ref], rot)
            ccx, ccy = x + cx, y + cy
            x0, y0, x1, y1 = self._regions[region]
            inside = (x0 <= ccx <= x1) and (y0 <= ccy <= y1)
            rep[ref] = (region, inside, ref not in seated, (round(ccx, 2), round(ccy, 2)))
        return rep

    def free_violations(self, cand=None):
        """The partition's correctness check: FREE (partition-governed) assigned refs that ended
        OUTSIDE their region. Empty == hard containment held for everything the partition governs."""
        return {r: info for r, info in self.containment_report(cand).items()
                if info[2] and not info[1]}

    def grade(self, *, out=None, keep=False, **grade_kw):
        """Materialize + route-oracle grade -> the real post-route accept verdict (the selection
        key). Compiles + materializes UNDER the oracle recipe env so the placement geometry (e.g.
        the CEC_SHUNT_GAP board grow) matches what the route then expects."""
        with csp._oracle_env(self.cfg.params if self.cfg else None):               # recipe env (CEC_SHUNT_GAP=1 etc.) for placement+route parity
            tmp = out or tempfile.mkstemp(prefix="cec_sess_", suffix=".kicad_pcb")[1]
            board = self.materialize(tmp)
            res = csp.route_oracle_grade(board, cfg=self.cfg, route=True, keep=keep, **grade_kw)
        res["intent_log"] = list(self.log)
        return res


def autonomy_search(make_session, intents, *, k=1, grade_kw=None, verbose=False):
    """The AUTONOMY fan-out (placer-feasibility primary metric). *intents* is a list of callables,
    each taking a fresh PlacementSession (from make_session()) and issuing a structure-first
    partition (the AGENT's proposal -- an ordering/grouping). Each is compiled + ROUTE-ORACLE
    graded; the survivors are ranked by the oracle sort_key (gate-clean first). Returns the sorted
    list of {name, verdict} so the caller sees whether ANY agent-proposed partition reaches the
    gate without a human authoring it -- the falsifiable autonomy claim.

    This is the harness, not the agent: the *intents* are where an LLM swarm's proposals plug in."""
    grade_kw = grade_kw or {}
    results = []
    for i, fn in enumerate(intents):
        name = getattr(fn, "__name__", "intent%d" % i)
        try:
            s = make_session()
            fn(s)
            v = s.grade(**grade_kw)
            v["name"] = name
            results.append(v)
            if verbose:
                print("  [autonomy] %-22s gate=%s sort_key=%s" % (name, v.get("gate"), v.get("sort_key")))
        except Exception as e:                 # noqa: BLE001 -- a broken intent ranks worst, never aborts the sweep
            results.append({"name": name, "gate": False, "error": "%s: %s" % (type(e).__name__, e),
                            "sort_key": (1, 9, 9999, 9999, 9999, 1e6)})
            if verbose:
                print("  [autonomy] %-22s ERROR %s" % (name, e))
    results.sort(key=lambda r: r.get("sort_key", (1, 9, 9999, 9999, 9999, 1e6)))
    return results[:k] if k else results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="PlacementSession smoke: compile a partitioned eps placement + report containment")
    ap.add_argument("board", nargs="?", default="eps-8pin")
    ap.add_argument("--W", type=float, default=96.0)
    ap.add_argument("--H", type=float, default=37.0)
    ap.add_argument("--grade", action="store_true", help="also route-oracle grade (slow, real route)")
    a = ap.parse_args()
    s = PlacementSession(a.board, a.W, a.H)
    s.half("periph", "x", 0.58, 1.00)
    s.half("cables", "x", 0.00, 0.58)
    s.assign(s.peripheral_ics(), "periph")
    s.assign(s.cable_parts(), "cables")
    print("peripheral_ics:", s.peripheral_ics())
    print("cable_parts   :", s.cable_parts())
    cand = s.compile()
    print("compiled: residual=%d  parts=%d" % (cand.residual, len(cand.P)))
    rep = s.containment_report(cand)
    gov = {r: v for r, v in rep.items() if v[2]}
    print("containment: %d governed assigned refs, %d inside; FREE violations=%s"
          % (len(gov), sum(1 for v in gov.values() if v[1]), s.free_violations(cand)))
    if a.grade:
        v = s.grade()
        print("ORACLE gate=%s sort_key=%s reasons=%s" % (v.get("gate"), v.get("sort_key"), v.get("reasons")))
