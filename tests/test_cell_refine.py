# SPDX-License-Identifier: Apache-2.0
# Teeth for scripts/cec_cell_refine.py (owner GO 2026-07-10: blueprint refinement loop).
# Host-runnable: the search is pure geometry over cec_pcb-parsed footprints; pcbnew
# legs (extract/emit/DRC) are container-only and exercised by the CLI run, not here.
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import cec_cell_refine as cr                                     # noqa: E402
import cec_synth_pipeline as sp                                  # noqa: E402


def lane_template():
    """A synthetic 12vhpwr-lane-shaped template built on REAL library footprints
    (shunt + RFH/RFL + CF + INA + bypass) with a sane hand-ish baseline."""
    P = {
        "RS": ("cec-Resistor_SMD:R_2512_6332Metric", (0.0, 0.0), 0.0),
        "RFH": ("cec-Resistor_SMD:R_0402_1005Metric", (8.0, 1.6), 0.0),
        "RFL": ("cec-Resistor_SMD:R_0402_1005Metric", (8.0, -1.6), 0.0),
        "CF": ("cec-Capacitor_SMD:C_0603_1608Metric", (11.6, 1.4), 0.0),
        "U": ("cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", (17.0, 0.0), 180.0),
        "CB": ("cec-Capacitor_SMD:C_0402_1005Metric", (12.15, -0.6), 180.0),
    }

    def rel(ref, pad):
        fp, off, rot = P[ref]
        lx, ly, _hw, _hh = cr.local_pads_sized(fp)[pad]
        px, py = cr._rot(lx, ly, rot)
        return [round(off[0] + px, 6), round(off[1] + py, 6)]

    def pads(*rp):
        return [{"ref": r, "pad": p, "rel_mm": rel(r, p)} for r, p in rp]

    return {
        "anchor": {"ref": "RS", "footprint": P["RS"][0], "value": "1m", "flipped": False},
        "parts": {r: {"offset_mm": list(off), "rot_delta": rot, "flipped": False,
                      "footprint": fp, "value": r}
                  for r, (fp, off, rot) in P.items()},
        "internal_tracks": [], "vias": [],
        "ports": {
            "/SENSEP{n}_HI": {"net": "/SENSEP1_HI", "pads": pads(("RS", "1"), ("RFH", "1"))},
            "/SENSEP{n}_LO": {"net": "/SENSEP1_LO", "pads": pads(("RS", "2"), ("RFL", "1"))},
            "+{n}V{n}": {"net": "+3V3", "pads": pads(("U", "6"), ("CB", "1"))},
            "GND": {"net": "GND", "pads": pads(("U", "2"), ("U", "3"), ("CB", "2"))},
            "/ISENSEP{n}": {"net": "/ISENSEP1", "pads": pads(("U", "5"))},
        },
        "internal_pads": {
            "/IN{n}_P": {"net": "/IN1_P", "pads": pads(("RFH", "2"), ("CF", "1"), ("U", "8"))},
            "/IN{n}_N": {"net": "/IN1_N", "pads": pads(("RFL", "2"), ("CF", "2"), ("U", "1"))},
        },
        "net_roles": {"/SENSEP{n}_HI": "/SENSEP1_HI", "/SENSEP{n}_LO": "/SENSEP1_LO",
                      "+{n}V{n}": "+3V3", "GND": "GND", "/ISENSEP{n}": "/ISENSEP1",
                      "/IN{n}_P": "/IN1_P", "/IN{n}_N": "/IN1_N"},
        "meta": {"source_board": "synthetic", "anchor_ref": "RS"},
    }


class TestModelAndRouting(unittest.TestCase):
    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")

    def test_route_roles_classified(self):
        self.assertEqual(sorted(self.model.tap_roles), ["/SENSEP{n}_HI", "/SENSEP{n}_LO"])
        self.assertEqual(self.model.link_roles, ["+{n}V{n}"])
        self.assertEqual(sorted(self.model.internal_roles), ["/IN{n}_N", "/IN{n}_P"])
        self.assertNotIn("GND", self.model.route_roles)          # plane-served, never in-cell
        self.assertNotIn("/ISENSEP{n}", self.model.route_roles)  # single in-cell pad = board-side

    def test_baseline_routes_and_gates(self):
        routes = cr.synth_routes(self.model, self.model.base_pose)
        self.assertEqual(set(routes), set(self.model.route_roles))
        self.assertEqual(cr.gates(self.model, self.model.base_pose, routes), [])

    def test_overlap_gate_fires(self):
        pose = dict(self.model.base_pose)
        pose["RFH"] = pose["RFL"]                                # same spot -> courtyard overlap
        try:
            routes = cr.synth_routes(self.model, pose)
        except cr.Refusal:
            return                                               # refusal is an equally-hard stop
        fails = cr.gates(self.model, pose, routes)
        self.assertTrue(any(f.startswith("overlap:") for f in fails), fails)

    def test_refusal_on_blocked_tap(self):
        pose = dict(self.model.base_pose)
        pose["CF"] = (4.7, 2.0, 90.0)                            # park the 0603 ON the HI tap runs
        with self.assertRaises(cr.Refusal):
            cr.synth_routes(self.model, pose)

    def test_flipped_part_refused(self):
        t = lane_template()
        t["parts"]["CF"]["flipped"] = True
        with self.assertRaises(ValueError):                      # dual-side deferred (owner ruling)
            cr.CellModel(t)


class TestRefine(unittest.TestCase):
    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")

    def test_deterministic(self):
        a = cr.refine(self.model, seed=3, starts=2, iters=250)
        b = cr.refine(self.model, seed=3, starts=2, iters=250)
        self.assertEqual(a["best"]["score"], b["best"]["score"])
        self.assertEqual(a["best"]["pose"], b["best"]["pose"])

    def test_never_regresses_feasible_baseline(self):
        r = cr.refine(self.model, seed=0, starts=2, iters=300)
        self.assertIsNotNone(r["best"])
        self.assertLessEqual(tuple(r["best"]["score"]), tuple(r["baseline"]["score"]))

    def test_refined_template_roundtrips(self):
        r = cr.refine(self.model, seed=0, starts=2, iters=250)
        t2 = cr.to_refined_template(self.model, r["best"]["pose"], r["best"]["routes"])
        self.assertTrue(t2["internal_tracks"])                   # copper carried for the stamp
        self.assertEqual(t2["meta"]["refined"]["single_face"], True)
        m2 = cr.CellModel(t2)                                    # refined template re-models cleanly
        routes = cr.synth_routes(m2, m2.base_pose)
        self.assertEqual(cr.gates(m2, m2.base_pose, routes), [])
        # port pad rel_mm moved with the parts
        hi = t2["ports"]["/SENSEP{n}_HI"]["pads"]
        for p in hi:
            if p["ref"] != "RS":
                x, y, _hw, _hh = m2.pad_at(m2.base_pose, p["ref"], p["pad"])
                self.assertAlmostEqual(p["rel_mm"][0], x, places=3)


class TestStandins(unittest.TestCase):
    """Boundary-copper stand-ins (owner 2026-07-10): fixed pour/lane context =
    obstacle for foreign copper + placement no-go + emitted context."""

    def _template_with_lane(self):
        t = lane_template()
        # a 2.5mm HI lane track running vertically through the anchor's pad-1 column
        # (the real 12vhpwr geometry: force copper arrives on the shunt pad)
        t["standins"] = [{"net_role": "/SENSEP{n}_HI", "kind": "track", "layer": "F.Cu",
                          "start_rel_mm": [-2.9, -12.0], "end_rel_mm": [-2.9, 0.0],
                          "width_mm": 2.5}]
        return t

    def test_standin_is_foreign_obstacle(self):
        m = cr.CellModel(self._template_with_lane())
        self.assertEqual(len(m.standin_fcu), 1)
        # foreign role sees it; its own role does not
        hi_boxes = m.foreign_pad_boxes(m.base_pose, "/SENSEP{n}_HI")
        lo_boxes = m.foreign_pad_boxes(m.base_pose, "/SENSEP{n}_LO")
        self.assertEqual(len(lo_boxes), len(hi_boxes) + 1)

    def test_standin_clash_gate_fires(self):
        m = cr.CellModel(self._template_with_lane())
        pose = dict(m.base_pose)
        pose["CB"] = (-2.9, -6.0, 0.0)            # park the +3V3 bypass ON the 12V lane
        try:
            routes = cr.synth_routes(m, pose)
        except cr.Refusal:
            return                                 # equally-hard stop (its own escape clips)
        fails = cr.gates(m, pose, routes)
        self.assertTrue(any(f.startswith("standin_clash:CB") for f in fails), fails)

    def test_own_role_pads_exempt(self):
        # the anchor's own pad-1 sits at the lane's end -- same net, no clash
        m = cr.CellModel(self._template_with_lane())
        routes = cr.synth_routes(m, m.base_pose)
        fails = [f for f in cr.gates(m, m.base_pose, routes) if f.startswith("standin_clash:RS.1")]
        self.assertEqual(fails, [])


class TestMitre(unittest.TestCase):
    """45-degree corner chamfer on ACCEPTED routes (owner: 'only routing 90s')."""

    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")
        self.routes = cr.synth_routes(self.model, self.model.base_pose)

    def test_mitre_produces_diagonals_and_shortens(self):
        before = sum(cr._seg_len(s) for ss in self.routes.values() for s in ss)
        m = cr.mitre_routes(self.model, self.model.base_pose, self.routes)
        after = sum(cr._seg_len(s) for ss in m.values() for s in ss)
        diag = [s for ss in m.values() for s in ss
                if abs(s[2] - s[0]) > 1e-6 and abs(s[3] - s[1]) > 1e-6]
        self.assertTrue(diag, "no 45-degree segment produced")
        self.assertLess(after, before)             # chamfers only ever cut corners
        self.assertEqual(cr.gates(self.model, self.model.base_pose, m), [])

    def test_mitre_deterministic(self):
        a = cr.mitre_routes(self.model, self.model.base_pose, self.routes)
        b = cr.mitre_routes(self.model, self.model.base_pose, self.routes)
        self.assertEqual(a, b)


class TestBudget(unittest.TestCase):
    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")

    def test_budget_deterministic_and_bounded(self):
        a = cr.refine(self.model, seed=1, iters=150, budget_evals=1200)
        b = cr.refine(self.model, seed=1, iters=150, budget_evals=1200)
        self.assertEqual(a["best"]["pose"], b["best"]["pose"])
        self.assertEqual(a["n_evals"], b["n_evals"])
        # budget is a cap up to one in-flight start/iteration of overshoot
        self.assertLess(a["n_evals"], 1200 + 2 * 150 + 4)

    def test_budget_never_regresses(self):
        r = cr.refine(self.model, seed=0, iters=150, budget_evals=900)
        self.assertIsNotNone(r["best"])
        self.assertLessEqual(tuple(r["best"]["score"]), tuple(r["baseline"]["score"]))


class TestFinder(unittest.TestCase):
    def _nl(self):
        comps, nets = {}, {}
        FP = {"RS": "cec-Resistor_SMD:R_2512_6332Metric", "RF": "cec-Resistor_SMD:R_0402_1005Metric",
              "U": "cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"}
        for lane in (1, 2, 3):
            for ref, fp, val in ((f"RS{lane}", FP["RS"], "1m"), (f"RFH{lane}", FP["RF"], "10"),
                                 (f"RFL{lane}", FP["RF"], "10"), (f"U1{lane}", FP["U"], "INA240A3")):
                comps[ref] = sp.Comp(ref=ref, value=val, footprint=fp)
            nets[f"/SENSEP{lane}_HI"] = [(f"RS{lane}", "1"), (f"RFH{lane}", "1"), ("J3", str(lane))]
            nets[f"/SENSEP{lane}_LO"] = [(f"RS{lane}", "2"), (f"RFL{lane}", "1"), ("J4", str(lane))]
            nets[f"/IN{lane}_P"] = [(f"RFH{lane}", "2"), (f"U1{lane}", "8")]
            nets[f"/IN{lane}_N"] = [(f"RFL{lane}", "2"), (f"U1{lane}", "1")]
            nets[f"/ISENSEP{lane}"] = [(f"U1{lane}", "5"), ("MCU", str(lane))]
        comps["MCU"] = sp.Comp(ref="MCU", value="ESP32", footprint=FP["U"])
        comps["J3"] = sp.Comp(ref="J3", value="12V2x6", footprint=FP["U"])
        comps["J4"] = sp.Comp(ref="J4", value="12V2x6", footprint=FP["U"])
        # hub-degree drivers: MCU + J3/J4 each touch >= 6 distinct signal nets
        for extra in range(1, 5):
            nets[f"/AUX{extra}"] = [("MCU", str(10 + extra)), ("J3", str(10 + extra)),
                                    ("J4", str(10 + extra))]
        nets["GND"] = [(r, "99") for r in comps]
        nets["+3V3"] = [(r, "98") for r in comps]
        return sp.Netlist(comps=comps, nets=nets)

    def test_finds_repeated_lane_class(self):
        cells = cr.find_cells(nl=self._nl(), hub_degree=6)
        self.assertTrue(cells, "no classes found")
        top = cells[0]
        self.assertEqual(top["n"], 3)                            # three isomorphic lanes
        self.assertEqual(top["parts_per_instance"], 4)
        self.assertIn("RS1", top["instances"][0])
        self.assertEqual(top["suggested_anchor"][:2], "RS")      # largest courtyard = the shunt

    def test_hub_drop_is_load_bearing(self):
        # without hub removal the MCU/connectors weld every lane into one blob
        cells = cr.find_cells(nl=self._nl(), hub_degree=10_000)
        self.assertFalse(any(c["n"] >= 3 and c["parts_per_instance"] == 4 for c in cells))


if __name__ == "__main__":
    unittest.main()
