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

from cec_slab_pour import Grid, shave                  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
