#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_fresh_wave -- the fresh-board synthesis WAVE driver (2026-07-07).

For each named beta board: fan out placement variants (strategy x seed x partition
intent) through PlacementSession, grade EVERY variant with the route-oracle (the
real post-route accept conjunction: kelvin AND diffpair AND drc-finishing AND
foreign==0 AND thermal AND routing-complete), keep the best by the oracle
sort_key, and publish ONLY the winner to build/fresh/<board>/ -- the dashboard's
watch glob -- so accepted boards appear in the browser as they are made.
Working candidates stay in build/fresh-work/<board>/ (NOT watched; the dashboard
must not GPU-analyze every loser).

Run INSIDE the routing container:
    python3 scripts/cec_fresh_wave.py --boards eps-8pin,pcie-8pin-2port
        [--seeds 0,1,2,3] [--passes 16] [--opt 20] [--out build/fresh]

The variant set is deliberately structure-first (the 2026-06-30 placer-feasibility
finding: partitions/intents move the needle, absolute-coord jitter does not).
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import cec_synth_pipeline as csp                       # noqa: E402
from cec_placement_session import PlacementSession     # noqa: E402
try:
    import cec_worklog                                 # dashboard activity feed (best-effort)
except Exception:                                      # noqa: BLE001
    cec_worklog = None


def _wlog(title, **kw):
    if cec_worklog is not None:
        try:
            cec_worklog.log(title, **kw)
        except Exception:                              # noqa: BLE001
            pass


def _snapshot(board, label, v, work_root, *, best=False, dual=False):
    """Per-variant REVIEW SNAPSHOT (owner ask 2026-07-08): render the routed candidate and
    feed it to the dashboard ACTIVITY stream with the full verdict, so the wave is
    reviewable AS IT RUNS. Renders are cheap (~3s); the GPU-analyzed archive still gets
    only published winners (the watcher)."""
    routed = v.get("routed") or v.get("placed")
    if not routed or not os.path.isfile(str(routed)):
        _wlog(f"{board} {label}: no board produced", tag="wave", detail=str(v.get("reasons"))[:300])
        return
    png = os.path.join(work_root, board, f"{label}-top.png")
    try:
        import cec_render
        # primary = copper view (no silk, NO BODIES -- owner 2026-07-08); a -bodies twin
        # is rendered alongside for the dash viewer's 3D toggle.
        png = cec_render.render(routed, png, side="top", no_bodies=True)
        if png:
            cec_render.render(routed, png.replace("-top.png", "-top-bodies.png"), side="top")
    except Exception:                                  # noqa: BLE001
        png = None
    star = "★ new best — " if best else ""
    th = (v.get("thermal") or {})
    detail = (f"gate={v.get('gate')} kelvin={v.get('kelvin_ok')} diff={v.get('diffpair_ok')} "
              f"drc={v.get('drc')} unconn={v.get('unconnected')} "
              f"foreign={(v.get('foreign') or {}).get('tracks')}t dT={th.get('dT')} "
              f"({v.get('route_s')}s route)")
    _wlog(f"{star}{board} {label}", tag="wave", detail=detail,
          image=(png if png and os.path.isfile(png) else None))
    if best and dual:
        pngb = os.path.join(work_root, board, f"{label}-bottom.png")
        try:
            import cec_render
            pngb = cec_render.render(routed, pngb, side="bottom")
            if pngb:
                _stamp_back_face(pngb)
                _wlog(f"{board} {label} — BACK FACE (mirrored view)", tag="wave",
                      detail="bottom view: left/right appear MIRRORED vs the top view. " + detail,
                      image=pngb)
        except Exception:                              # noqa: BLE001
            pass


def _stamp_back_face(png):
    """Banner the render itself (owner ask 2026-07-08: a mirrored bottom view read as
    'jacks on the wrong side') -- the label must live ON the image, not just the feed row."""
    try:
        from PIL import Image, ImageDraw
        im = Image.open(png).convert("RGB")
        d = ImageDraw.Draw(im)
        h = max(28, im.height // 24)
        d.rectangle([0, 0, im.width, h], fill=(180, 60, 20))
        msg = "BACK FACE - MIRRORED VIEW (left/right flipped vs top view)"
        d.text((12, h // 4), msg, fill=(255, 255, 255))
        im.save(png)
    except Exception:                                  # noqa: BLE001
        pass

# Working W x H per board (mm): the committed boards' envelope as the STARTING size
# (the shrink pass comes after a gate-clean baseline exists; SHUNT_GAP may grow H).
BOARD_WH = {
    "eps-8pin": (96.0, 37.0),
    "pcie-8pin-2port": (86.5, 44.0),
    "pcie-8pin-3port": (103.5, 56.0),
    # owner 2026-07-08 "way too large -- tone it down": geometry floor is J3 (~63mm) and
    # the blade row + signal stub (~59mm); dual-sided chains + no mounts + full overhang
    # make 70x55 the aggressive seed (the shrink pass walks further once gate-clean).
    "atx-24pin-rev3": (70.0, 55.0),
}

# Per-board owner-ratified placement params (2026-07-08, 24-pin ground-up remake):
# full connector overhang (J3's NPTH stabilizers off-board -- not used), NO mounting
# holes, rounded corners; dual-sided placement is authorized for this board with the
# same-side-per-rail sensing constraint (mechanism pending -- the wave is GATED on the
# shared-bus per-rail corridor package, see TODO).
BOARD_PARAMS = {
    "atx-24pin-rev3": {"mount_holes": "none", "corner_radius": 2.5,
                       "connector_overhang": "edge",
                       # wireless unpopulated: NO antenna keepout (owner 2026-07-08); the module's
                       # physical antenna section just rides at an edge like any body extent.
                       "respect_antenna_keepout": False,
                       # owner GO 2026-07-08: alternate rail chains F/B (same-side-per-rail)
                       "dual_sided": True,
                       # 4.2 (atx24-out-db as-built) predates the iteration-7 TE 63969
                       # receptacle swap -- its 4.29mm courtyard cannot pack at 4.2. Use the
                       # eps-proven 4.7 contiguous; the DRAFT daughterboard re-pitches to
                       # match (owner-queued 2026-07-08).
                       "blade_pitch": 4.7, "blade_group_gap": 4.7,
                       # 96-part dual-sided board: FR pass time ~16-21s (measured); the eps
                       # effort (16/20) blows the 600s budget. 8/10 completes in ~2-4 min.
                       "wave_passes": 8, "wave_opt": 10, "wave_fr_timeout": 1200},
}


def _intents():
    """Named structure-first partition intents. Each takes a session and mutates it."""
    def none(s):
        return s

    def periph_right(s):
        s.half("periph", "x", 0.58, 1.00)
        s.half("cables", "x", 0.00, 0.58)
        s.assign(s.peripheral_ics(), "periph")
        return s

    def periph_left(s):
        s.half("periph", "x", 0.00, 0.42)
        s.half("cables", "x", 0.42, 1.00)
        s.assign(s.peripheral_ics(), "periph")
        return s

    return [("plain", none), ("periph-right", periph_right), ("periph-left", periph_left)]


def _intents_for(board):
    """Board-aware intent set: the generic trio plus per-board STRUCTURE-FIRST partitions
    (owner 2026-07-08: 'this board needs a lot more placement work... the placer pipeline
    is always the bottleneck'). The 24-pin anatomy: J3 top, blade row + stub bottom, hub
    jacks left -- so the sensing chains belong in the HORIZONTAL BAND between J3 and the
    blades (containing the stray INA181s the seat missed, 16-23mm off), and the MCU core /
    USB front-end zone RIGHT where their connectors live."""
    base = _intents()
    if board != "atx-24pin-rev3":
        return base

    def sense_band(s):
        s.half("band", "y", 0.30, 0.72)
        s.half("core", "x", 0.58, 1.00)
        s.assign(s.cable_parts(), "band")
        s.assign([r for r in s.peripheral_ics()
                  if "TJA" not in (s.nl.comps[r].value or "").upper()], "core")
        return s

    def sense_band_tight(s):
        s.half("band", "y", 0.36, 0.66)
        s.half("core", "x", 0.62, 1.00)
        s.assign(s.cable_parts(), "band")
        s.assign([r for r in s.peripheral_ics()
                  if "TJA" not in (s.nl.comps[r].value or "").upper()], "core")
        return s

    def band_core_mid(s):
        # core BETWEEN the band and the USB edge, sensing band wider: tests whether the
        # peripherals do better center-right (shorter MCU fanout) than hard-right.
        s.half("band", "y", 0.32, 0.70)
        s.half("core", "x", 0.50, 0.85)
        s.assign(s.cable_parts(), "band")
        s.assign([r for r in s.peripheral_ics()
                  if "TJA" not in (s.nl.comps[r].value or "").upper()], "core")
        return s

    return base + [("sense-band", sense_band), ("sense-band-tight", sense_band_tight),
                   ("band-core-mid", band_core_mid)]


def run_board(board, seeds, passes, opt, out_root, work_root):
    W, H = BOARD_WH.get(board, (100.0, 44.0))
    _wlog(f"wave started: {board}", tag="wave",
          detail=f"{len(_intents_for(board))} intents x 2 strats x {len(seeds)} seeds at {W}x{H}mm, passes {passes}/opt {opt}")
    os.makedirs(os.path.join(work_root, board), exist_ok=True)
    results = []
    for iname, intent in _intents_for(board):
        for strat in ("dataflow", "compact"):
            for seed in seeds:
                label = f"{iname}-{strat}-s{seed}"
                t0 = time.monotonic()
                try:
                    _p = dict(BOARD_PARAMS.get(board) or {})
                    _mf = os.path.join(ROOT, "modules", board, "board-manifest.json")
                    if os.path.isfile(_mf):
                        try:
                            _pd = (json.load(open(_mf)) or {}).get("placement_directives") or {}
                            _p.update({k: v for k, v in _pd.items()
                                       if not k.startswith("_") and not k.endswith(("_note", "_rules", "provenance"))})
                        except Exception:                  # noqa: BLE001
                            pass
                    s = PlacementSession(board, W=W, H=H, strat=strat, seed=seed, params=_p)
                    intent(s)
                    out = os.path.join(work_root, board, f"{label}.kicad_pcb")
                    _bp = _p or {}
                    v = s.grade(out=out, keep=True,
                                passes=int(_bp.get("wave_passes", passes)),
                                opt=int(_bp.get("wave_opt", opt)),
                                fr_timeout=int(_bp.get("wave_fr_timeout", 900)),
                                seed=seed,          # pin FR seed: wave-to-wave comparability
                                unconn_finish_tol=2,
                                # owner 2026-07-08: the 5-17s thermal solve runs ONLY on a
                                # would-be gate-clean candidate (all other terms green) --
                                # a published best always has a REAL solve behind it.
                                thermal="lazy")
                    v["label"] = label
                    v["placed"] = out
                    _was_best = (not results or
                                 tuple(v.get("sort_key") or (9,)) <
                                 min(tuple(r.get("sort_key") or (9,)) for r in results))
                    results.append(v)
                    _snapshot(board, label, v, work_root, best=_was_best,
                              dual=bool(_bp.get("dual_sided")))
                    print(f"[wave] {board} {label}: gate={v.get('gate')} "
                          f"kelvin={v.get('kelvin_ok')} unconn={v.get('unconnected')} "
                          f"foreign={v.get('foreign',{}).get('tracks')}t "
                          f"dT={((v.get('thermal') or {}).get('dT'))} "
                          f"({round(time.monotonic()-t0,1)}s)", flush=True)
                except Exception as e:                              # noqa: BLE001
                    print(f"[wave] {board} {label}: ERROR {type(e).__name__}: {e}", flush=True)
    if not results:
        return None
    results.sort(key=lambda v: tuple(v.get("sort_key") or (9,)))
    best = results[0]
    # publish ONLY the winner (routed board if the route produced one, else the placement)
    pub_dir = os.path.join(out_root, board)
    os.makedirs(pub_dir, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M")
    src = best.get("routed") if best.get("routed") and os.path.isfile(str(best.get("routed"))) \
        else best.get("placed")
    dst = os.path.join(pub_dir, f"{ts}-{best['label']}.kicad_pcb")
    if src and os.path.isfile(str(src)):
        import shutil
        shutil.copy(str(src), dst)
        base = str(src)[:-len(".kicad_pcb")]
        for ext in (".kicad_pro", ".kicad_dru"):
            if os.path.isfile(base + ext):
                shutil.copy(base + ext, dst[:-len(".kicad_pcb")] + ext)
    report = {"board": board, "ts": ts, "W": W, "H": H, "passes": passes, "opt": opt,
              "published": os.path.relpath(dst, ROOT) if src else None,
              "best": {k: best.get(k) for k in
                       ("label", "gate", "kelvin_ok", "diffpair_ok", "drc", "unconnected",
                        "unconn_critical", "foreign", "thermal_ok", "sort_key", "reasons")},
              "ranking": [{"label": v["label"], "gate": v.get("gate"),
                           "sort_key": v.get("sort_key")} for v in results]}
    with open(os.path.join(pub_dir, f"{ts}-wave-report.json"), "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(f"[wave] {board} BEST={best['label']} gate={best.get('gate')} -> {dst}", flush=True)
    _wlog(f"wave done: {board} best={best['label']} gate={best.get('gate')}", tag="wave",
          detail=f"kelvin={best.get('kelvin_ok')} unconn={best.get('unconnected')} "
                 f"foreign={ (best.get('foreign') or {}).get('tracks') }t; published {os.path.relpath(dst, ROOT)}")
    return report


def main():
    ap = argparse.ArgumentParser(description="fresh-board synthesis wave (run in-container)")
    ap.add_argument("--boards", default="eps-8pin")
    ap.add_argument("--seeds", default="0,1,2,3")
    ap.add_argument("--passes", type=int, default=16)
    ap.add_argument("--opt", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "fresh"))
    ap.add_argument("--work", default=os.path.join(ROOT, "build", "fresh-work"))
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",") if x.strip() != ""]
    for board in [b.strip() for b in a.boards.split(",") if b.strip()]:
        run_board(board, seeds, a.passes, a.opt, a.out, a.work)


if __name__ == "__main__":
    main()
