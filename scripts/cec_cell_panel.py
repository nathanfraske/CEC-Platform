#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_cell_panel -- owner BEFORE/AFTER panel for a cell-refinement run (host leg,
# PIL only). Composes: [hand cell IN CONTEXT (source-board render crop)] |
# [baseline microboard = the extracted hand cell] | [refined microboard], with
# the refine-report metrics as captions. The OWNER denotes improvements
# (2026-07-10 ruling); this panel is the artifact that ritual runs on.
#
#   python3 scripts/cec_cell_panel.py build/cell-refine/hpwr-RS4-deep \
#       [-o build/cell-refine-panel.png] [--log "title for the dash feed"]
import argparse
import json
import os
import subprocess
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description="compose the owner before/after cell panel")
    ap.add_argument("run_dir", help="a refine run's --out dir (refine-report.json + renders)")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--log", default=None, help="also log to the dashboard feed with this title")
    args = ap.parse_args(argv)

    from PIL import Image, ImageDraw

    rep = json.load(open(os.path.join(args.run_dir, "refine-report.json")))
    tiles = []
    for stem, label in (("context-top.png", "HAND, IN CONTEXT (source board)"),
                        ("baseline-top.png", "BASELINE microboard (hand cell + stand-ins)"),
                        ("refined-top.png", "REFINED-BEST microboard (searched + mitred)")):
        p = os.path.join(args.run_dir, stem)
        if os.path.exists(p):
            tiles.append((Image.open(p), label))
    if not tiles:
        sys.exit("no renders in " + args.run_dir)

    H = 900
    scaled = [(im.resize((max(1, int(im.width * H / im.height)), H)), lab) for im, lab in tiles]
    cap, foot, gap = 96, 30, 12
    W = sum(im.width for im, _ in scaled) + gap * (len(scaled) + 1)
    img = Image.new("RGB", (W, H + cap + foot + 24), (24, 24, 28))
    dr = ImageDraw.Draw(img)

    hm = rep.get("hand_baseline_metrics") or {}
    bm = rep.get("best_metrics") or {}
    lines = [
        "HAND: %s | taps %s skew %.2f | scored score %s" % (
            _ext(hm), _taps(hm), hm.get("tap_skew_mm", 0.0),
            rep.get("hand_baseline_score")),
        "REFINED-BEST (%s evals, %ss): %s | taps %s skew %.2f | score %s | mitre %s" % (
            rep.get("n_evals"), rep.get("wall_s"), _ext(bm), _taps(bm),
            bm.get("tap_skew_mm", 0.0), rep.get("best_score"), rep.get("mitre", "off")),
        "VERDICT: improved_vs_resynth=%s  improved_vs_hand=%s | stand-ins %s (%s on F.Cu)" % (
            rep.get("improved"), rep.get("improved_vs_hand"),
            rep.get("standins"), rep.get("standins_fcu")),
    ]
    for i, ln in enumerate(lines):
        dr.text((12, 8 + 18 * i), ln, fill=(255, 196, 120) if ln.startswith("VERDICT") else (235, 235, 235))
    x = gap
    for im, lab in scaled:
        img.paste(im, (x, cap))
        dr.text((x + 4, cap - 16), lab, fill=(128, 203, 196))
        x += im.width + gap
    dr.text((12, H + cap + 4),
            "%s %s anchor %s | owner denotes improvements (machine score ranks only)" % (
                os.path.basename(rep.get("board", "?")), rep.get("refs"), rep.get("anchor")),
            fill=(150, 150, 160))

    out = args.out or os.path.join("build", "cell-panel-" + os.path.basename(
        os.path.normpath(args.run_dir)) + ".png")
    img.save(out)
    print("panel:", out, img.size)
    if args.log:
        subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "cec_worklog.py"),
                        args.log, "--tag", "blueprint", "--image", out,
                        "--detail", lines[2]], check=False)
    return 0


def _ext(m):
    return "%.1fx%.1fmm cu %.1fmm" % (m.get("extent_x_mm", 0), m.get("extent_y_mm", 0),
                                      m.get("copper_mm", 0))


def _taps(m):
    t = m.get("tap_lens_mm") or {}
    return "/".join("%.1f" % v for v in t.values()) or "-"


if __name__ == "__main__":
    sys.exit(main())
