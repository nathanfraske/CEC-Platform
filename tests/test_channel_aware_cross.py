#!/usr/bin/env python3
"""close-the-loop (2026-06-27): the channel-aware corridor predictor reaches 0 where the OLD metric
cannot. The old corridor_cross_count is unreachable-to-0 because the hub->per-cable fan-out is a
topological x-straddle invariant; the channel-aware metric counts a straddle ONLY when it can't escape
via a body-clear top/bottom channel (the keepout clips to the pad rows, so the channels are clear).
Pure geometry -> host-side, no pcbnew."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import cec_synth_pipeline as sp

# synthetic eps: 2 cables -> 2 corridor bands (x-range, y-range); board 80x40
W, H = 80.0, 40.0
BANDS = {"SENSEC1": (20, 30, 10, 30), "SENSEC2": (50, 60, 10, 30)}
CORRIDOR_NETS = {"/SENSEC1_HI", "/SENSEC1_LO", "/SENSEC2_HI", "/SENSEC2_LO"}


def test_channel_aware_reaches_zero():
    # /DETC1: cable-1 amp (inside band1) + ESP (right block) -> x-span [25,70] straddles band2.
    pads = {"/DETC1": [(25, 20), (70, 20)], "/SENSEC1_HI": [(25, 20), (20, 15)]}
    bodies = [(65, 75, 15, 25)]                              # ESP right block: NOT in the top/bottom channels
    old = sp.corridor_cross_count(pads, BANDS, CORRIDOR_NETS, board_w=W)
    new = sp.corridor_cross_channel_aware(pads, BANDS, CORRIDOR_NETS, bodies, W, H, board_w=W)
    assert old >= 1, f"old metric must COUNT the fan-out straddle (the unreachable floor), got {old}"
    assert new == 0, f"channel-aware must be 0 -- the straddle escapes via the clear channel, got {new}"
    print(f"  clean placement: old corridor_cross={old}  channel-aware={new}  (the honest metric = 0)")


def test_channel_aware_has_teeth():
    # block BOTH channels over the net's x-span -> the straddle is genuinely forced through a pour.
    pads = {"/DETC1": [(25, 20), (70, 20)]}
    bodies = [(40, 50, 3, 7), (40, 50, 33, 37)]              # one body in the top channel, one in the bottom
    new = sp.corridor_cross_channel_aware(pads, BANDS, CORRIDOR_NETS, bodies, W, H, board_w=W)
    assert new == 1, f"both channels blocked -> the straddle MUST count, got {new}"
    print(f"  both channels blocked: channel-aware={new}  (the metric has teeth)")


def test_channels_geometry():
    top, bot = sp.channels_of(BANDS, W, H, board_w=W)
    assert top == (1.0, 9.0), top                            # above the highest band top (Y0=10)
    assert bot == (31.0, 39.0), bot                          # below the lowest band bottom (Y1=30)
    assert sp.channels_feasible(BANDS, W, H, board_w=W)
    assert not sp.channels_feasible(BANDS, W, 32.0, board_w=W)  # too short -> grow trigger
    print(f"  channels: top={top} bot={bot}  feasible@H40=True  feasible@H32=False (grow trigger)")


if __name__ == "__main__":
    for t in (test_channels_geometry, test_channel_aware_reaches_zero, test_channel_aware_has_teeth):
        print(t.__name__); t()
    print("ALL PASS")
