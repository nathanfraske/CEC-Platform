"""Outline search must minimize area without outranking physical legality."""

import os
import sys
import unittest
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_outline_compaction as compact  # noqa: E402


def _candidate(score=10, residual=0, corridor=0, positions=None):
    return SimpleNamespace(
        residual=residual, corridor_cross=corridor,
        corridor_cross_aware=corridor,
        proxy={"proxy_score": score},
        P=positions or {"R1": (1.0, 2.0, 0.0)})


class OutlineCompactionTest(unittest.TestCase):
    def test_candidates_are_compact_first_with_bounded_fallbacks(self):
        rows = compact.outline_candidates(80, 60, {
            "enabled": True, "step_mm": 2, "max_steps": 3,
            "fallback_steps_mm": [3, 6]})
        self.assertEqual(rows, [
            (74.0, 54.0), (76.0, 56.0), (78.0, 58.0),
            (80.0, 60.0), (83.0, 63.0), (86.0, 66.0)])

    def test_legality_and_corridors_dominate_area_then_proxy(self):
        compact_legal = (_candidate(score=100), 70, 50)
        large_legal = (_candidate(score=1), 80, 60)
        tiny_illegal = (_candidate(score=0, residual=1), 60, 40)
        ordered = sorted(
            [large_legal, tiny_illegal, compact_legal],
            key=compact.placement_key)
        self.assertIs(ordered[0], compact_legal)
        self.assertIs(ordered[-1], tiny_illegal)

    def test_probe_pool_deduplicates_aliases_and_keeps_outline_fallback(self):
        first = (_candidate(positions={"R1": (1, 2, 0)}), 70, 50)
        alias = (_candidate(positions={"R1": (1, 2, 0)}), 70, 50)
        distinct = (_candidate(positions={"R1": (2, 2, 0)}), 70, 50)
        larger = (_candidate(), 74, 54)
        selected = compact.placement_probe_pool(
            [first, alias, distinct, larger], 2, fallbacks=2)
        self.assertEqual(selected, [first, distinct, larger])

    def test_height_only_candidates_do_not_spend_unneeded_width(self):
        rows = compact.outline_candidates(76.1, 55.7, {
            "enabled": True, "step_mm": 2.0, "max_steps": 2,
            "minimum_height_mm": 50.0,
            "shrink_axes": ["height"],
        })
        self.assertEqual(rows, [
            (76.1, 51.7), (76.1, 53.7), (76.1, 55.7)])

    def test_bottom_edge_band_follows_height_without_moving_interior(self):
        poses = {
            "TB1": (20.0, 42.55, 0.0),
            "H1": (3.5, 52.2, 0.0),
            "U1": (30.0, 25.0, 90.0),
        }
        moved, report = compact.edge_follow_positions(
            poses, (76.1, 55.7), (76.1, 51.7), {
                "edge_follow": [{"edge": "bottom", "margin_mm": 15.0}],
            })
        self.assertEqual(moved["TB1"], (20.0, 38.55, 0.0))
        self.assertEqual(moved["H1"], (3.5, 48.2, 0.0))
        self.assertEqual(moved["U1"], poses["U1"])
        self.assertEqual(set(report["moved_refs"]), {"TB1", "H1"})

    def test_explicit_edge_group_moves_only_declared_refs(self):
        poses = {"J1": (70.0, 10.0, 0), "R1": (72.0, 10.0, 0)}
        moved, _report = compact.edge_follow_positions(
            poses, (80, 40), (76, 40), {
                "edge_follow": [{"edge": "right", "refs": ["J1"]}],
            })
        self.assertEqual(moved["J1"], (66.0, 10.0, 0.0))
        self.assertEqual(moved["R1"], (72.0, 10.0, 0))

    def test_containment_follow_consumes_existing_edge_slack(self):
        poses = {
            "H1": (3.5, 52.2, 0.0),
            "TB1": (20.0, 42.0, 0.0),
        }
        moved, report = compact.edge_follow_positions(
            poses, (80.0, 55.7), (80.0, 53.7), {
                "edge_follow": [{
                    "edge": "bottom", "margin_mm": 15.0,
                    "mode": "contain", "clearance_mm": 0.05,
                }],
            }, extent_by_ref={
                "H1": (0.05, 6.95, 48.75, 55.65),
                "TB1": (15.0, 25.0, 39.0, 45.0),
            })
        self.assertAlmostEqual(moved["H1"][0], 3.5)
        self.assertAlmostEqual(moved["H1"][1], 50.2)
        self.assertAlmostEqual(moved["H1"][2], 0.0)
        self.assertEqual(moved["TB1"], poses["TB1"])
        self.assertEqual(
            set(report["selected_refs"]), {"H1", "TB1"})
        self.assertEqual(set(report["moved_refs"]), {"H1"})

    def test_excluded_rigid_datums_do_not_get_reclaimed_by_slack_band(self):
        poses = {"H1": (3.5, 52.2, 0.0), "TB1": (20.0, 42.0, 0.0)}
        moved, report = compact.edge_follow_positions(
            poses, (80.0, 55.7), (80.0, 53.7), {
                "edge_follow": [
                    {"edge": "bottom", "refs": ["H1"]},
                    {"edge": "bottom", "margin_mm": 15.0,
                     "exclude_refs": ["H1"], "mode": "contain",
                     "clearance_mm": 0.05},
                ],
            }, extent_by_ref={
                "H1": (0.05, 6.95, 48.75, 55.65),
                "TB1": (15.0, 25.0, 39.0, 45.0),
            })
        self.assertAlmostEqual(moved["H1"][1], 50.2)
        self.assertEqual(moved["TB1"], poses["TB1"])
        self.assertEqual(report["selected_refs"]["H1"]["mode"], "rigid")

    def test_global_release_keeps_movable_fiducial_out_of_edge_follow(self):
        poses = {"H1": (3.5, 52.2, 0.0),
                 "FID2": (72.0, 50.0, 0.0)}
        moved, report = compact.edge_follow_positions(
            poses, (80.0, 55.7), (80.0, 51.7), {
                "edge_follow_exclude_refs": ["FID2"],
                "edge_follow": [{
                    "edge": "bottom", "refs": ["H1", "FID2"],
                    "mode": "rigid",
                }],
            })
        self.assertEqual(moved["H1"], (3.5, 48.2, 0.0))
        self.assertEqual(moved["FID2"], poses["FID2"])
        self.assertNotIn("FID2", report["selected_refs"])
        self.assertEqual(report["released_refs"], ["FID2"])


if __name__ == "__main__":
    unittest.main()
