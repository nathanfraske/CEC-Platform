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


class TestTextbookTap(unittest.TestCase):
    """Owner ruling 2026-07-10: taps exit ACROSS the pad's inner edge, run inward,
    then ONE perpendicular 90 -- textbook-or-refuse."""

    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")

    def test_tap_first_stroke_is_inward(self):
        routes = cr.synth_routes(self.model, self.model.base_pose)
        for role in self.model.tap_roles:
            s0 = routes[role][0]
            self.assertAlmostEqual(s0[1], s0[3], places=6,
                                   msg=f"{role} first stroke not along the pad row")
            (r1, p1), _ = sorted(self.model.role_pads[role],
                                 key=lambda rp: rp[0] != self.model.anchor)
            ax, _ay, _hw, _hh = self.model.pad_at(self.model.base_pose, r1, p1)
            inward = (s0[2] - s0[0]) * (0.0 - ax)                # toward anchor centre x=0
            self.assertGreater(inward, 0, f"{role} first stroke exits OUTWARD")

    def test_tap_second_stroke_perpendicular(self):
        routes = cr.synth_routes(self.model, self.model.base_pose)
        for role in self.model.tap_roles:
            segs = [s for s in routes[role] if cr._seg_len(s) > 1e-9]
            s1 = segs[1]
            self.assertAlmostEqual(s1[0], s1[2], places=6,
                                   msg=f"{role} second stroke is not the perpendicular 90")

    def test_blocked_inner_gap_refuses(self):
        pose = dict(self.model.base_pose)
        # park the 0603 ON pad-2's inner-edge exit path (its pads straddle every
        # inset the textbook stub can take) -- textbook-or-refuse, no fallback
        pose["CF"] = (1.9, 0.0, 0.0)
        with self.assertRaises(cr.Refusal):
            cr.synth_routes(self.model, pose)


class TestTextbookProtection(unittest.TestCase):
    """Owner 2026-07-10 (B3 review): lint/mitre must never touch the textbook
    strokes -- B3's lint shortcut an inward exit into a direct outward run and
    its mitre chamfered the perpendicular 90 into 45 ramps."""

    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")
        self.routes = cr.synth_routes(self.model, self.model.base_pose)

    def _assert_textbook(self, routes):
        for role in self.model.tap_roles:
            s0, s1 = routes[role][0], routes[role][1]
            self.assertAlmostEqual(s0[1], s0[3], places=6, msg=f"{role} stroke0 not row-axis")
            self.assertAlmostEqual(s1[0], s1[2], places=6, msg=f"{role} stroke1 not perpendicular")
            # the two textbook corners stay square (no 45 ramp replaced them)
            self.assertAlmostEqual(s0[2], s1[0], places=6)
            self.assertAlmostEqual(s0[3], s1[1], places=6)

    def test_lint_then_mitre_preserve_textbook(self):
        linted = cr.lint_routes(self.model, self.model.base_pose, self.routes)
        self._assert_textbook(linted)
        mitred = cr.mitre_routes(self.model, self.model.base_pose, linted)
        self._assert_textbook(mitred)

    def test_nonanchor_pad_on_own_lane_clashes(self):
        t = lane_template()
        # LO-net lane track right where RFL could be packed
        t["standins"] = [{"net_role": "/SENSEP{n}_LO", "kind": "track", "layer": "F.Cu",
                          "start_rel_mm": [5.0, -8.0], "end_rel_mm": [5.0, 0.0],
                          "width_mm": 2.5}]
        m = cr.CellModel(t)
        pose = dict(m.base_pose)
        pose["RFL"] = (5.0, -3.0, 0.0)             # RFL pad1 (same net!) onto the lane
        try:
            routes = cr.synth_routes(m, pose)
        except cr.Refusal:
            return
        fails = cr.gates(m, pose, routes)
        self.assertTrue(any(f.startswith("standin_clash:RFL") for f in fails), fails)


class TestGndVias(unittest.TestCase):
    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")
        self.routes = cr.synth_routes(self.model, self.model.base_pose)

    def test_vias_synthesized_for_gnd_pads(self):
        vias, stubs, missing = cr.synth_gnd_vias(self.model, self.model.base_pose, self.routes)
        n_gnd = sum(1 for r, _p in self.model.role_pads["GND"] if r != self.model.anchor)
        self.assertEqual(missing, [])
        self.assertEqual(len(vias), n_gnd)
        self.assertEqual(len(stubs), n_gnd)
        # every via clears every foreign pad by CLR
        obstacles = self.model.foreign_pad_boxes(self.model.base_pose, "GND")
        r_via = cr.GND_VIA_DIA / 2.0
        for v in vias:
            vx, vy = v["at_rel_mm"]
            for b in obstacles:
                self.assertTrue(vx + r_via + cr.CLR_MM <= b[0] or vx - r_via - cr.CLR_MM >= b[1] or
                                vy + r_via + cr.CLR_MM <= b[2] or vy - r_via - cr.CLR_MM >= b[3],
                                f"via {v} encroaches {b}")

    def test_deterministic(self):
        a = cr.synth_gnd_vias(self.model, self.model.base_pose, self.routes)
        b = cr.synth_gnd_vias(self.model, self.model.base_pose, self.routes)
        self.assertEqual(a[0], b[0])

    def test_via_barrel_clears_all_layers(self):
        # a B.Cu lane under the cell: through-via barrels must dodge it even
        # though it constrains no F.Cu routing (the B4 shorts, 2026-07-11)
        t = lane_template()
        t["standins"] = [{"net_role": "/SENSEP{n}_LO", "kind": "track", "layer": "B.Cu",
                          "start_rel_mm": [-5.0, -0.6], "end_rel_mm": [25.0, -0.6],
                          "width_mm": 2.5}]
        m = cr.CellModel(t)
        routes = cr.synth_routes(m, m.base_pose)
        vias, _stubs, _missing = cr.synth_gnd_vias(m, m.base_pose, routes)
        lane = next(b for r, b in m.standin_all if r == "/SENSEP{n}_LO")
        r_via = cr.GND_VIA_DIA / 2.0
        for v in vias:
            vx, vy = v["at_rel_mm"]
            self.assertTrue(vx + r_via + cr.CLR_MM <= lane[0] or vx - r_via - cr.CLR_MM >= lane[1] or
                            vy + r_via + cr.CLR_MM <= lane[2] or vy - r_via - cr.CLR_MM >= lane[3],
                            f"via {v} barrel lands on the B.Cu lane")


class TestAcceptanceCheck(unittest.TestCase):
    def test_rejecting_check_blocks_best(self):
        m = cr.CellModel(lane_template(), pitch_axis="y")
        r = cr.refine(m, seed=0, starts=1, iters=100, acceptance_check=lambda p, rt: False)
        self.assertIsNone(r["best"])              # even the feasible baseline is refused

    def test_finalize_cell_grounds_everything(self):
        m = cr.CellModel(lane_template(), pitch_axis="y")
        routes, gvias, gstubs, gmissing = cr.finalize_cell(m, m.base_pose)
        self.assertEqual(gmissing, [])
        self.assertEqual(cr.gates(m, m.base_pose, routes), [])
        self.assertTrue(gvias)


class TestRenudge(unittest.TestCase):
    """Stamp-time loop-back (owner: 'send it back to the blueprint factory')."""

    def test_recovers_blocked_blueprint(self):
        t = lane_template()
        # destination context: a lane stub NICKING the U pad column. MEASURED
        # geometry (two guessed placements failed): SOIC pad right edge =
        # 19.475 + hw 0.875 = 20.35; lane centre 21.0 (box left 20.5) makes the
        # clash depth 20.55-20.5 = 0.05mm -- squarely nudge-recoverable.
        # (x20.3 needed a 0.75mm shift that CF/CB courtyards block; x17 sat in
        # the SOIC body zone clashing nothing.)
        t["standins"] = [{"net_role": "/SENSEP{n}_HI", "kind": "track", "layer": "F.Cu",
                          "start_rel_mm": [21.0, -6.0], "end_rel_mm": [21.0, 2.0],
                          "width_mm": 1.0}]
        m = cr.CellModel(t)
        try:                                       # broken-at-destination premise:
            base_fails = cr.gates(m, m.base_pose,  # gate fail OR routing refusal
                                  cr.synth_routes(m, m.base_pose))
            self.assertTrue(base_fails,
                            "premise broken: blueprint should fail at the destination")
        except cr.Refusal:
            pass
        r = cr.renudge(m, m.base_pose, budget_evals=800)
        self.assertIsNotNone(r, "renudge failed to seat the blueprint")
        # nudges stayed nudges
        for ref, (dx, dy, rot) in r["pose"].items():
            bx, by, brot = m.base_pose[ref]
            self.assertLessEqual(abs(dx - bx), 0.8 + 1e-9)
            self.assertLessEqual(abs(dy - by), 0.8 + 1e-9)
            self.assertEqual(rot, brot)            # no rotation in a nudge

    def test_returns_none_when_impossible(self):
        t = lane_template()
        # wall off the whole cell body band: nothing a <=0.8mm nudge can fix
        t["standins"] = [{"net_role": "/SENSEP{n}_HI", "kind": "zone", "layer": "F.Cu",
                          "box_rel_mm": [4.0, 30.0, -4.0, 4.0]}]
        m = cr.CellModel(t)
        r = cr.renudge(m, m.base_pose, budget_evals=400)
        self.assertIsNone(r)


class TestLintAndEfficacy(unittest.TestCase):
    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")

    def test_lint_removes_double_back(self):
        routes = cr.synth_routes(self.model, self.model.base_pose)
        role = "/IN{n}_P"
        end = routes[role][-1]
        # plant a synthetic double-back continuing from the chain's end
        ex, ey = end[2], end[3]
        routes = dict(routes)
        routes[role] = routes[role] + [(ex, ey, ex + 1.4, ey), (ex + 1.4, ey, ex + 0.7, ey)]
        before = sum(cr._seg_len(s) for s in routes[role])
        linted = cr.lint_routes(self.model, self.model.base_pose, routes)
        after = sum(cr._seg_len(s) for s in linted[role])
        self.assertLess(after, before - 1.0, "double-back survived lint")

    def test_lint_deterministic_and_gate_clean(self):
        routes = cr.synth_routes(self.model, self.model.base_pose)
        a = cr.lint_routes(self.model, self.model.base_pose, routes)
        b = cr.lint_routes(self.model, self.model.base_pose, routes)
        self.assertEqual(a, b)
        self.assertEqual(cr.gates(self.model, self.model.base_pose, a), [])

    def test_decoupler_loop_gate_fires(self):
        routes = cr.synth_routes(self.model, self.model.base_pose)
        routes = dict(routes)
        role = self.model.link_roles[0]
        s = routes[role][0]
        # replace the link with a wandering 8mm detour between the same pads
        routes[role] = [(s[0], s[1], s[0], s[1] + 4.0), (s[0], s[1] + 4.0, s[2], s[3])]
        fails = cr.gates(self.model, self.model.base_pose, routes)
        self.assertTrue(any(f.startswith("decoupler_loop:") for f in fails), fails)

    def test_refined_template_prunes_far_standins(self):
        t = lane_template()
        t["standins"] = [
            {"net_role": "/SENSEP{n}_HI", "kind": "via", "at_rel_mm": [80.0, 0.0],
             "dia_mm": 0.6, "drill_mm": 0.3, "layers": ["F.Cu", "B.Cu"]},
            {"net_role": "/SENSEP{n}_HI", "kind": "track", "layer": "F.Cu",
             "start_rel_mm": [-2.9, -6.0], "end_rel_mm": [-2.9, 0.0], "width_mm": 2.5},
        ]
        m = cr.CellModel(t, pitch_axis="y")
        routes = cr.synth_routes(m, m.base_pose)
        t2 = cr.to_refined_template(m, m.base_pose, routes)
        kinds = [(s["kind"], s["net_role"]) for s in t2["standins"]]
        self.assertNotIn(("via", "/SENSEP{n}_HI"), kinds)         # 80mm away: pruned
        self.assertIn(("track", "/SENSEP{n}_HI"), kinds)          # at the cell: kept


class TestCompaction(unittest.TestCase):
    """Slide-to-contact compaction (owner 2026-07-10: 'not moving placements
    at all to compact it down')."""

    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")

    def test_slide_reaches_contact_not_overlap(self):
        pose = dict(self.model.base_pose)
        pose["U"] = (30.0, 0.0, 180.0)             # park the SOIC far out +x
        slid = cr._slide_to_contact(self.model, pose, "U", 0, -1.0)
        self.assertIsNotNone(slid)
        self.assertLess(slid[0], 30.0)             # moved toward the anchor
        pose["U"] = slid
        fails = [f for f in cr.gates(self.model, pose, {}) if f.startswith("overlap:U")]
        self.assertEqual(fails, [], "slide must stop at contact, never overlap")

    def test_slide_ignores_obstacles_behind(self):
        pose = dict(self.model.base_pose)
        pose["U"] = (30.0, 0.0, 180.0)
        # CB sits behind U (x ~12): sliding U further +x must not be blocked by it
        slid = cr._slide_to_contact(self.model, pose, "U", 0, 1.0)
        self.assertIsNone(slid)                    # nothing ahead within 25mm -> no move

    def test_search_compacts_spread_template(self):
        t = lane_template()
        for ref in ("RFH", "RFL", "CF", "U", "CB"):  # scatter the cell wide
            off = t["parts"][ref]["offset_mm"]
            t["parts"][ref]["offset_mm"] = [off[0] * 1.8, off[1] * 1.8]
        m = cr.CellModel(t, pitch_axis="y")
        r = cr.refine(m, seed=0, iters=400, budget_evals=2500)
        self.assertIsNotNone(r["best"])
        base_w, base_h = cr.parts_extents(m, m.base_pose)
        best_w, best_h = cr.parts_extents(m, r["best"]["pose"])
        self.assertLess(best_w * best_h, base_w * base_h,
                        f"no compaction: {base_w:.1f}x{base_h:.1f} -> {best_w:.1f}x{best_h:.1f}")


class TestGradedRefusal(unittest.TestCase):
    """synth_routes_partial + graded soft cost (2026-07-10): an infeasible pose
    must cost MORE the more roles refuse, and partial routes are never accepted."""

    def setUp(self):
        self.model = cr.CellModel(lane_template(), pitch_axis="y")

    def test_partial_keeps_going(self):
        pose = dict(self.model.base_pose)
        pose["CF"] = (4.7, 2.0, 90.0)             # kills the HI tap region
        routes, refused = cr.synth_routes_partial(self.model, pose)
        self.assertTrue(refused)
        self.assertTrue(routes, "partial must still carry the routable roles")
        refused_roles = {r for r, _ in refused}
        self.assertTrue(set(routes) | refused_roles <= set(self.model.route_roles))

    def test_cost_monotone_in_refusals(self):
        c_feas, r = cr._soft_cost(self.model, self.model.base_pose)
        self.assertTrue(r)                         # feasible pose returns its routes
        pose = dict(self.model.base_pose)
        pose["CF"] = (4.7, 2.0, 90.0)
        c_blocked, r2 = cr._soft_cost(self.model, pose)
        self.assertIsNone(r2)                      # partial never offered as acceptable
        self.assertLess(c_feas, c_blocked)


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
