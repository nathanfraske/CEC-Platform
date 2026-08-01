#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Slab-pour shave teeth (owner concept 2026-07-24 + the appendage addendum:
# "auto-shave any parts sticking out from the main pathway or deviating from
# it without going anywhere"). Pure-raster tests (no pcbnew): dead-end fingers
# prune, anchored fingers (taps) stay, corridors bridging two body lobes stay,
# anchor-less components drop, and the min-width invariant reports honestly.
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_slab_pour import Grid, shave, weighted_fair_masks  # noqa: E402


class _G(Grid):
    """Grid stub with a fixed geometry (no board needed)."""
    def __init__(self, nx, ny, cell=0.8):
        self.x0 = self.y0 = 0.0
        self.cell = cell
        self.nx, self.ny = nx, ny
        self.x1, self.y1 = nx * cell, ny * cell


class TestShave(unittest.TestCase):
    def _run(self, foreign, anchors, g):
        try:
            return shave(foreign, anchors, g)
        except ImportError:
            self.skipTest("scipy not available")

    def test_dead_finger_pruned_anchored_finger_kept(self):
        g = _G(40, 30)
        foreign = np.ones((30, 40), bool)
        foreign[5:25, 5:30] = False        # the body block (open space)
        foreign[10:13, 30:38] = False      # finger A (dead end, no anchor)
        foreign[18:21, 30:38] = False      # finger B (reaches an anchor)
        anchors = np.zeros((30, 40), bool)
        anchors[14:16, 10:12] = True       # body anchor
        anchors[18:21, 36:38] = True       # finger B tip anchor (a tap)
        mask, rep = self._run(foreign, anchors, g)
        self.assertFalse(mask[11, 34], "dead-end finger must be pruned")
        self.assertTrue(mask[19, 34], "anchored finger (tap) must stay")
        self.assertTrue(mask[15, 15], "the body stays")
        self.assertGreaterEqual(rep["appendages_pruned"], 1)

    def test_bridging_corridor_kept(self):
        g = _G(50, 20)
        foreign = np.ones((20, 50), bool)
        foreign[4:16, 2:20] = False        # body lobe 1
        foreign[4:16, 30:48] = False       # body lobe 2
        foreign[7:13, 20:30] = False       # corridor bridging the lobes (4.8mm --
                                           # above the width floor; a sub-floor
                                           # corridor legitimately dies at the
                                           # sliver stage and the invariant
                                           # reports the split)
        anchors = np.zeros((20, 50), bool)
        anchors[8:10, 5:7] = True
        anchors[8:10, 42:44] = True
        mask, rep = self._run(foreign, anchors, g)
        self.assertTrue(mask[9, 25] or mask[10, 25],
                        "a corridor bridging two body lobes must NOT be pruned")

    def test_anchorless_component_dropped(self):
        g = _G(40, 20)
        foreign = np.ones((20, 40), bool)
        foreign[4:16, 2:18] = False        # anchored region
        foreign[4:16, 24:38] = False       # ISOLATED region, no anchors
        anchors = np.zeros((20, 40), bool)
        anchors[8:10, 6:8] = True
        mask, rep = self._run(foreign, anchors, g)
        self.assertTrue(mask[10, 10])
        self.assertFalse(mask[10, 30], "anchor-less component must drop "
                                       "(the floating-zone rule, structural)")


class TestWeightedSlabAllocation(unittest.TestCase):
    def _fixture(self):
        shape = (24, 90)
        candidates = [np.ones(shape, bool) for _ in range(3)]
        anchors = [np.zeros(shape, bool) for _ in range(3)]
        seeds = ((4, 4), (12, 45), (19, 84))
        for i, (r, c) in enumerate(seeds):
            anchors[i][r, c] = True
            # A real raster marks the other nets' pads foreign. Mirror that
            # condition so mandatory anchor ownership cannot overlap.
            for j in range(3):
                if j != i:
                    candidates[j][r, c] = False
        return candidates, anchors

    def test_partition_is_disjoint_and_current_proportional(self):
        candidates, anchors = self._fixture()
        masks, report = weighted_fair_masks(
            candidates, anchors, [3.0, 2.0, 1.0], names=["A", "B", "C"])
        self.assertFalse(any(np.logical_and(masks[i], masks[j]).any()
                             for i in range(3) for j in range(i + 1, 3)))
        union = np.logical_or.reduce(masks)
        self.assertGreater(union.mean(), 0.98)
        counts = np.array([m.sum() for m in masks], dtype=float)
        shares = counts / counts.sum()
        np.testing.assert_allclose(shares, [0.5, 1.0 / 3.0, 1.0 / 6.0],
                                   atol=0.03)
        self.assertTrue(all(r["allocated_cells"] > 0 for r in report))

    def test_result_is_input_order_invariant_by_name(self):
        candidates, anchors = self._fixture()
        names = ["A", "B", "C"]
        weights = [3.0, 2.0, 1.0]
        masks1, _ = weighted_fair_masks(candidates, anchors, weights,
                                        names=names)
        perm = [2, 0, 1]
        masks2, _ = weighted_fair_masks(
            [candidates[i] for i in perm], [anchors[i] for i in perm],
            [weights[i] for i in perm], names=[names[i] for i in perm])
        by_name_1 = dict(zip(names, masks1))
        by_name_2 = dict(zip([names[i] for i in perm], masks2))
        for name in names:
            np.testing.assert_array_equal(by_name_1[name], by_name_2[name])

    def test_non_positive_current_is_rejected(self):
        candidates, anchors = self._fixture()
        with self.assertRaises(ValueError):
            weighted_fair_masks(candidates, anchors, [3.0, 0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
