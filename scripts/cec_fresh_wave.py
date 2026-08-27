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
    python3 scripts/cec_fresh_wave.py --boards eps-8pin-rev3,pcie-8pin-2port
        [--seeds 0,1,2,3] [--passes 16] [--opt 20] [--out build/fresh]

The variant set is deliberately structure-first (the 2026-06-30 placer-feasibility
finding: partitions/intents move the needle, absolute-coord jitter does not).
"""
import argparse
import copy
import glob
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _reexec_workspace_python():
    """Run an executable wave in the repository's managed Python runtime.

    The route-awareness CUDA stack is deliberately installed once, in
    ``.venv``.  A direct ``python3 scripts/cec_fresh_wave.py`` invocation must
    therefore select that runtime just like the canonical full-pipeline entry
    point does; otherwise a healthy accelerator silently degrades to the CPU
    backend for the entire wave.  Importers and controlled interpreter-ablation
    tests are unaffected.
    """
    if os.environ.get("CEC_KEEP_CALLER_PYTHON") == "1":
        return
    workspace = os.path.join(ROOT, ".venv")
    candidate = os.path.join(workspace, "bin", "python")
    same = os.path.realpath(sys.prefix) == os.path.realpath(workspace)
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK) and not same:
        os.execv(candidate, [candidate, os.path.abspath(__file__), *sys.argv[1:]])


# Select the managed runtime before importing wx/pcbnew or any CUDA-aware
# pipeline module.  Besides making acceleration available, this avoids loading
# KiCad's SWIG bindings twice around the exec boundary.
if __name__ == "__main__":
    _reexec_workspace_python()

# KiCad's SWIG layer repeatedly registers the same wx image handlers in every
# placement/authority worker. At wx's debug level that emits thousands of
# non-actionable lines per wave and needlessly grows unattended journals.
try:
    import wx
    wx.Log.SetLogLevel(wx.LOG_Error)
except Exception:                                      # noqa: BLE001
    pass

sys.path.insert(0, HERE)

import cec_synth_pipeline as csp                       # noqa: E402
import cec_score                                       # noqa: E402
import cec_fr                                          # noqa: E402
import cec_mezz_contract as mezz                       # noqa: E402
import cec_beta_manifest                              # noqa: E402
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


def _completion_guidance_from_env():
    """Load optional prior-route evidence for the next placement wave.

    The report is advisory input only. Every proposed move still passes the
    normal materialized placement and route authorities before adoption.
    """
    path = os.environ.get("CEC_PLACEMENT_COMPLETION_REPORT", "").strip()
    if not path:
        return None
    try:
        if os.path.getsize(path) > 32 * 1024 * 1024:
            raise ValueError("completion report exceeds 32 MiB")
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


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
        # STACK PANEL: front/back renders plus every copper layer. Six-layer
        # boards render a 4x2 tile so In3/In4 are visible during the wave too.
        hexp = cec_render.hex_panel(routed,
                                    os.path.join(work_root, board, f"{label}-hex.png"),
                                    side_pngs={"top": png})
        if hexp:
            png = hexp
    except Exception:                                  # noqa: BLE001
        png = None
    star = "★ new best — " if best else ""
    th = (v.get("thermal") or {})
    detail = (f"gate={v.get('gate')} kelvin={v.get('kelvin_ok')} diff={v.get('diffpair_ok')} "
              f"drc={v.get('drc')} unconn={v.get('unconnected')} "
              f"foreign={(v.get('foreign') or {}).get('tracks')}t dT={th.get('dT')} "
              f"({v.get('route_s')}s route)"
              # the 9999-with-no-reason class (owner, 2026-07-20): a refused/failed
              # variant's error was in the dict but never displayed anywhere
              + (f" ERR={str(v.get('error'))[:140]}" if v.get("error") else ""))
    _wlog(f"{star}{board} {label}", tag="wave", detail=detail,
          image=_snap_into_repo(png, board))
    if best and dual:
        pngb = os.path.join(work_root, board, f"{label}-bottom.png")
        try:
            import cec_render
            pngb = cec_render.render(routed, pngb, side="bottom")
            if pngb:
                _stamp_back_face(pngb)
                _wlog(f"{board} {label} — BACK FACE (mirrored view)", tag="wave",
                      detail="bottom view: left/right appear MIRRORED vs the top view. " + detail,
                      image=_snap_into_repo(pngb, board))
        except Exception:                              # noqa: BLE001
            pass


def _snap_into_repo(png, board):
    """Worklog images must live INSIDE the repo -- the host dashboard serves
    /artifact paths repo-relative, and a work_root outside the repo (the night
    chains' container /tmp) produced ../tmp/... paths the dash 404s ('image
    failed to load', owner report 2026-07-19). Copy the snapshot into
    build/wave-snaps/<board>/ and return that path; a repo-internal png passes
    through unchanged."""
    if not (png and os.path.isfile(png)):
        return None
    ap = os.path.abspath(png)
    if ap.startswith(ROOT + os.sep):
        return png
    try:
        import shutil
        dst_dir = os.path.join(ROOT, "build", "wave-snaps", board)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(png))
        shutil.copy(ap, dst)
        return dst
    except Exception:                                  # noqa: BLE001
        return None


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

def mating_frame_pins(W, H, contract, side):
    """SHARED MATING FRAME derivation (owner 2026-07-20: mezzanine first, but
    "that derivation methodology can also be used for all of the daughterboards
    and the eventual psu tester pipeline" -- keep it general). The contract
    declares, in SHARED assembly coordinates (offsets from the ATX nominal-
    frame center), EITHER the v2
    segment-list form (structural segmented mezz, owner GO 2026-07-22,
    docs/mezz-structural-segments-2026-07-22.md):
      {"conns": [{"ref": .., "dc": (dx, dy), "rot": deg}, ...],
       "mount_dc": ((dx, dy), ...),     # required fitted lug for this contract
       "mount_fp": "lib:footprint",     # optional per-contract mount land (e.g. M2)
       "mount_net": "GND",              # optional electrical role for every mount land
       "sides": {name: {"mount_refs": (..), "mirror_x": bool,
                         "assembly_dc": (board_center_dx, board_center_dy)}}}
    OR the legacy single-connector form:
      {"conn_dc": (dx, dy), "conn_rot": deg,
       "rect_dc": (x0, y0, x1, y1),     # the standoff datum rectangle
       "sides": {name: {"conn_ref": .., "mount_refs": (..), "mirror_x": bool}}}
    A side with mirror_x=True flips to mate. Each shared point is first made
    relative to that board's assembly-center offset, then its X is reflected;
    connector orientation becomes ``180deg - rot``. Returns
    {"anchor_pins": .., "mount_pos_override": .., ["mount_fp_override": ..]}
    for that side -- feed into BOARD_PARAMS. One declaration, every mating
    side derived; the mating refs are alignment DATUM (exempt from
    nudge/anneal by the pipeline). MATE INVARIANT (the property that matters):
    after applying each side's assembly translation/reflection, every mating
    field is coincident."""
    sd = contract["sides"][side]
    m = -1.0 if sd.get("mirror_x") else 1.0
    ax, ay = sd.get("assembly_dc", (0.0, 0.0))
    cx, cy = W / 2.0, H / 2.0
    if "conns" in contract:                       # v2: N structural segments
        pins = {c["ref"]: (cx + m * (c["dc"][0] - ax),
                           cy + c["dc"][1] - ay,
                           ((180.0 - c.get("rot", 0)) % 360.0
                            if sd.get("mirror_x") else c.get("rot", 0)))
                for c in contract["conns"]}
    else:                                         # legacy single connector
        dx, dy = contract["conn_dc"]
        _rot = contract.get("conn_rot", 0)
        pins = {sd["conn_ref"]: (cx + m * (dx - ax), cy + dy - ay,
                                 ((180.0 - _rot) % 360.0
                                  if sd.get("mirror_x") else _rot))}
    # standoffs: an explicit "mount_dc" POINT LIST (possibly EMPTY -- the R1
    # structural-segment form carries stability in the segments themselves; a
    # single point = the R2 provisioned DNP-able land) or the legacy "rect_dc"
    # 4-corner rectangle.
    if "mount_dc" in contract:
        pts = [(cx + m * (mx - ax), cy + my - ay)
               for (mx, my) in contract["mount_dc"]]
    elif "rect_dc" in contract:
        x0, y0, x1, y1 = contract["rect_dc"]
        pts = [(cx + m * (mx - ax), cy + my - ay)
               for (mx, my) in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    else:
        pts = []
    mounts = {}
    for ref, (px, py) in zip(sd.get("mount_refs", ()), sorted(pts)):
        mounts[ref] = (px, py)
    out = {"anchor_pins": pins, "mount_pos_override": mounts}
    if mounts and contract.get("mount_fp"):
        out["mount_fp_override"] = {r: contract["mount_fp"] for r in mounts}
    return out


# THE HUB-ON-24PIN MEZZANINE CONTRACT.  The current dead-bug assembly reflects
# the Hub about the physical Y axis: Hub F.Cu faces ATX F.Cu, while the Hub
# B.Cu/logo/LED windows face outward.  The canonical segment coordinates are
# the ATX face; the Hub transform mirrors X and connector rotations.  This is
# deliberately encoded here so every placement, render, and mating audit uses
# the same physical transform.
# conn geometry: the 2x8's 14mm pad field extends along LOCAL +y from the
# anchor (measured); rot 180 points it -y, so the anchor sits at the field's
# BOTTOM -- dc y +17.5 centers the barrels on the y-31..45 strip (between the
# standoffs, clear of the sink bands' x-range). The 24-pin overlap zone
# belongs to J1/J2, which are DNP in the stacked variant (doc §5 XOR).
# MEASURED RE-DERIVATION (2026-07-20, owner: mounts "not going to fit as is...
# middle of the board"; "drop the top right mount [on the hub] if that is
# tripping you up"): joint point-legality over BOTH probe boards (anchors:
# jacks/headers/TB/fiducials, 3.2mm M3 clearance, stack offset (+7,+3.5)) shows
# TL is impossible (the 24-pin's OWN left jacks J1/J2) while TR is legal on both
# (24-pin blocker was only the movable FID2; hub spot sits 3+mm below its jack
# row) -- so the 3 standoffs are BL/BR/TR, spread 65x30. J6 moves to the RIGHT
# flank between TR and BR (left flank now hosts the 24-pin jack column; the old
# left-flank spot rammed the hub's C1 zone). Probe = the arbiter: rails 4/4 +
# no-overlap on both boards gate any future change to these numbers.
MEZZ_HUB_24PIN = {
    # STRUCTURAL SEGMENTED MEZZ (owner GO 2026-07-22, R1 + the R2 provision --
    # docs/mezz-structural-segments-2026-07-22.md): the single 2x8 J6 + the
    # H1-H3 M3 standoff trio are RETIRED; three KEYED segments (J6P 2x3 power /
    # J6C 2x4 comms / J6D 2x2 ID, Appendix A pin maps) ARE the mounting system.
    # SEATS R3/R4 (2026-08-03): exact pad-derived force-rail boxes + real asymmetric
    # header/socket courtyards, intersected across 3 placements per side.  An
    # explicit 70..86mm width sweep kept internal macros movable; 85mm had no
    # stable balanced support set, while 86mm produced the four-quadrant field
    # below across all six substrates.  Different pin counts retain insertion
    # keying. Report: /tmp/balanced-w86.json.
    "conns": [{"ref": s["ref"], "dc": s["dc"], "rot": s["rot"]}
              for s in mezz.SEGMENTS],
    # FITTED GROUND LUG: ONE populated M2 land. The production contract
    # requires conductive hardware at this shared seat. The seat is
    # lower-left support vertex (the X-mirror of J6C), jointly hard-legal across the same six probe
    # substrates. R4 moves the J6C/H1 support row 5mm inward after the real
    # force-rail lay proved the former J6C GND barrel occupied the 3V3 sink
    # band; both boards remain placement-clean. The pre-route courtyard gate
    # remains the release arbiter.
    "mount_dc": (mezz.GROUND_LUG["dc"],),
    "mount_fp": mezz.GROUND_LUG["footprint"],
    # This is an electrical part of the mating contract.  A populated metal M2
    # fastener bonds the coincident plated lands on both boards as an inter-board
    # ground lug.  It supplements the GND pins in J6P/J6C/J6D; it is not a
    # substitute for those current-return paths.
    "mount_net": mezz.GROUND_LUG["net"],
    "mount_function": mezz.GROUND_LUG["function"],
    "mount_electrical_role": mezz.GROUND_LUG["electrical_role"],
    "mount_population": mezz.GROUND_LUG["population"],
    "mount_contact": mezz.GROUND_LUG["contact"],
    "stack": mezz.STACK,
    "sides": {
        "atx-24pin-rev3": {"mount_refs": ("H1",), "mirror_x": False,
                            "assembly_dc": (0.0, 0.0)},
        "hub-standard-rev2": {"mount_refs": ("H1",), "mirror_x": True,
                              "assembly_dc": mezz.STACK["hub_assembly_dc_mm"]},
    },
}

# Working W x H per board (mm): the committed boards' envelope as the STARTING size
# (the shrink pass comes after a gate-clean baseline exists; SHUNT_GAP may grow H).
BOARD_WH = {
    # HUB REV2 (owner directive 2026-07-15: "get the Hub down properly ... start from
    # just the connectors and go from there"): proto-V1 is ~120x95-class; the 4-jack
    # row (~4x16mm + gaps) floors one edge at ~70mm. Aggressive seed; refusals teach.
    # H 62->70 (MEASURED SIZE WEDGE, 2026-07-20): with every deliberate macro seated
    # (4-jack row, WROOM cluster ~48x41, LED ring, bottom J_KVM/J_USB, mezz J6+datum)
    # the 21x17mm C1 hold-up cap measured ZERO free cells at every stage -- the board
    # was genuinely full, every hub variant refused. 8mm of height is the cap's row.
    "hub-standard-rev2": (86.0, 74.0),
    # Current and only BETA EPS source. Keep this explicit: falling through to the
    # generic 100x44 default silently routes a different placement problem.
    "eps-8pin-rev3": (96.0, 40.0),
    "pcie-8pin-2port": (86.5, 44.0),
    "pcie-8pin-3port": (103.5, 56.0),
    # owner 2026-07-08 "way too large -- tone it down": geometry floor is J3 (~63mm) and
    # the blade row + signal stub (~59mm); dual-sided chains + no mounts + full overhang
    # make 70x55 the aggressive seed (the shrink pass walks further once gate-clean).
    # SINGLE-SIDED AT 70x55 (owner ruling 2026-07-19: "size up is the last lever in
    # the ladder for a reason -- just let it try"): the one-probe residual 35 at this
    # size (16 at 76x60/80x62) is the PIPELINE'S problem to grind down, not a board
    # grow; the wave's strategy/seed/intent variance + p8b + proposal chaining are
    # the levers. Size-up only after the search levers are exhausted.
    # W 70->74 (2026-07-19 late, the lever EARNED -- rungs exhausted with named
    # numbers): after the jack tuck + per-column drop + outlier/live-span bands
    # + handedness + stub clamps, the four-rail wedge chain still measures
    # J1 field 14.4 + stub 2.45 + 3x11.85 pitch + cell bank 9.4 + array 3.05 +
    # J6 field 17.4 = 82.2mm > 70, every remaining assignment 0.03-0.6mm short
    # (probe series s0d..s0u). W74 clears the chain with 3.2mm spare. The
    # 12vhpwr 62x62->62x66 measured-capacity precedent applies.
    # DEAD-BUG STACK R3: 86mm is the measured balanced-mezz width floor.  H=95
    # is the analytical cable-access floor: the Hub is offset -0.7mm so its
    # 9.8/11.2mm exposed bands clear the 8.35/9.75mm connector reaches plus
    # the 1.2mm planar guard.  This is not a placer-driven size increase.
    "atx-24pin-rev3": (86.0, 95.0),
    # owner fun-run 2026-07-09: "tear the 12VHPWR down to just its connectors, compact it
    # down as much as possible" -- committed hand board is 58x80 (fanned); 60x40 = ~half
    # the area as the aggressive seed. Analog-pin board (INA240 lanes, no I2C family).
    # H 62->66 (2026-07-19, MEASURED capacity limit): at 62x62 the last jellybean
    # (D2, 7x3.5 SMA diode) has 2248 part-free cells but ZERO corridor-free ones --
    # the corridor/cell reservations own every hole, so it parks overlapping (the
    # owner-flagged overlap class). +4mm height = the smallest admit; still -13%
    # area vs the 58x80 hand board; the shrink pass walks it back after gate-clean.
    "12vhpwr-standard": (62.0, 66.0),  # ALPHA-DOCTRINE floorplan (owner Option-A ruling 2026-07-12: lanes left-of-center at lane_center, ESP/CAN/RJ-45 logic column right -- centered lanes + the 16.1mm ESP measured impossible at W=60). Prior: (owner 2026-07-11: cells board-centered,
    # RJ45/USB movable): 6 lanes at 6.8 = 43.5mm span leaves no flank for the
    # 16x21 ESP on W60 -- it seats ABOVE the lane field beside J3. Geometry:
    # J3 y0-9 / ESP+periph band / lanes centered / J4 band. Still -20% area vs
    # the 58x80 hand board; the shrink pass walks it down after gate-clean.
}

# Per-board owner-ratified placement params (2026-07-08, 24-pin ground-up remake):
# full connector overhang (J3's NPTH stabilizers off-board -- not used), NO mounting
# holes, rounded corners; dual-sided placement is authorized for this board with the
# same-side-per-rail sensing constraint (mechanism pending -- the wave is GATED on the
# shared-bus per-rail corridor package, see TODO).
BOARD_PARAMS = {
    # PCIe 3-PORT SEAT CONFLICT -- diagnosed, NOT fixed (2026-07-26). Why that
    # board publishes only placement-only skeletons: the third cable's cell seats
    # at x~87.5 while the RJ-45's default seat spans x 82.9-101.7 / y 11.6-28.6,
    # so U32 (SOT-23-5) lands ENTIRELY inside the jack -- "courtyard overlaps
    # J1|U32" on every variant and seed. The obvious fix (pin the jack below the
    # cell row, y 31-35, which is geometrically clear) was TRIED and REVERTED:
    # anchor_pins does not place in the frame this measurement assumed, and every
    # trial failed EARLIER with "J1 1 pad(s) out of bounds". Left as-is rather
    # than traded for a worse failure; the anchor_pins frame needs checking first.
    # HUB REV2 (2026-07-15): connector-first, no force lanes (no shunt corridors on a
    # hub) -- the MCU/fan seats stay dormant by their force_lanes gate; hub-specific
    # rungs (LED-ring centerpiece macro, WROOM seat) get added from wave-1 evidence.
    # Mezz segments are DNP but their LANDS place like any part; positions are the
    # stack ALIGNMENT CONTRACT with the 24-pin (MEZZ_HUB_24PIN, dead-bug flip,
    # segmented form -- J6P/J6C/J6D + the one provisioned M2).
    "hub-standard-rev2": {"wave_fr_timeout": 1500,
                          # Progressive route effort: candidate probes stay
                          # shallow; only the selected close winner earns this
                          # genuinely deeper polish. The unattended manager's
                          # CLI controls the probe (10/12 by default).
                          "polish_passes": 24,
                          "polish_opt": 30,
                          "polish_unconnected_max": 40,
                          # Functional safety/control intent is explicit. These
                          # nets look like ordinary low-speed signals to a
                          # generic router, but together they are the selected-
                          # 5VSB dropout chain that must remain reachable before
                          # the hold-up reservoir discharges. Leaf selectors are
                          # resolved against the hierarchical PCB names and fail
                          # closed if absent or ambiguous.
                          "critical_route_nets": (
                              "BLACKOUT_SENSE", "COMP_THRESH",
                              "PWR_FAIL_INT"),
                          # When the priority preflight names a blocked launch,
                          # spend bounded placement effort on the named blocker
                          # before allocating a multi-minute FR worker. Each
                          # accepted move must improve the full route-capacity
                          # key and preserve device/decoupler adjacency.
                          "placement_route_repair_trials": 16,
                          "placement_route_repair_rounds": 2,
                          "placement_route_repair_full_evals": 4,
                          # Route-aware two-stage placement tournament. All
                          # variants get the cheap 1.0 mm CPU proof; only this
                          # bounded shortlist gets the authoritative .5 mm
                          # CUDA proof before the final route allocation. This
                          # spends tens of seconds to avoid spending 4-25
                          # minutes on a geometrically inferior FR candidate.
                          "placement_route_aware_shortlist": 6,
                          "placement_route_aware_grid_mm": 0.5,
                          "placement_route_aware_iters": 3,
                          # RECALIBRATED 100 -> 150 (wall probe 2026-07-23):
                          # the first fix-wave killed variants flat at togo
                          # 104-112, and the full-effort probe routed that
                          # exact board to unconn 17 -- FR's mid-route flat
                          # phases reach ~110 and recover (A/B cleared both
                          # netclasses and locked copper as causes; it is
                          # seed-ordering phase behavior). 150 covers the
                          # measured recoverable band (34->7, 112->17);
                          # winners finish at unconn 7-36.
                          "wave_plateau_floor": 150,
                          # HUB POWER RUNG (2026-07-23, owner "power is a rung
                          # there... tune that rung up"): the hub is the ONE
                          # board with no pour machinery -- FR was handed the
                          # whole 51-connection power tree raw, and the wall
                          # probe's residual unconn was exactly these nets +
                          # GND. Post-route ADDITIVE floods per power net
                          # (evac=False: copper-only, no placement eviction --
                          # the additive-pour-after-route doctrine; a pour on
                          # a routed net can only ADD copper, 2026-06-07).
                          # Boxes auto-derive from each net's pads.
                          # SIX-LAYER POWER LAYER: In3 is the dedicated power
                          # routing and pour layer. F/In2/B remain available to
                          # the signal router, while In1/In4 remain solid GND.
                          # SMD pads connect through qualified through POFV or
                          # ordinary through-via pickups.
                          "pour_asks": [
                              {"net": n, "region_hint": None,
                               "layers": ("In3.Cu",), "shape": "rect",
                               "priority": 2, "provenance": "placer_ask",
                               "evac": False}
                              for n in ("+5VSB", "+5V_SYS", "/PSU_5V_KVM",
                                        "/+5V_HOLD", "/VCC_P1", "/VCC_P2",
                                        "/VCC_P3", "/VCC_P4")],
                          # Treat each power pour as a routed object. The old
                          # same-layer fair-share slabs split +5VSB into nine
                          # disconnected anchor islands on this compact board.
                          # Over-under finds one continuous corridor and uses a
                          # compact via field only when a real obstruction
                          # requires a layer transition. USB_VBUS is intentionally
                          # not a pour request: at 0.5A its 1.0mm Power-class
                          # ordinary route is ample and avoids a pointless plane.
                          "overunder": True,
                          # The routed-object contract is incomplete unless
                          # Freerouting receives the solved corridor as a real
                          # keepout. Without this flag, post-route realization
                          # can refill around foreign tracks and appear DRC-clean
                          # while those tracks still cut through the rail's
                          # reserved outline. This is a hard Hub release gate.
                          "pour_reserve": True,
                          # + the pickup stitch: SMD pads the route never
                          # reached get stub+via into the covering flood /
                          # GND plane at import (rung part 2 -- the floods
                          # alone cannot reach an F.Cu pad from B.Cu).
                          "power_pickup": True,
                          "plane_tht_exclude": True,
                          # LAST-MILE COMPLETER (2026-07-23, from the s120
                          # residual autopsy: 13 of 30 unconn were <=5mm
                          # same-net gaps FR left in dense fields -- incl.
                          # BOTH GND criticals, each a pad 1-2mm from a
                          # plane-connected via). Guarded straight/L closure
                          # + the over-the-top bridge (stub+via -> empty
                          # In2/B leg -> back down); measured on s120: 8
                          # closed, unconn 30->22, zero new DRC of any class.
                          "lastmile": True,
                          # Post-route connectivity is measured between copper
                          # islands, not between the two objects KiCad happens
                          # to cite in its ratline.  Wave 68 proved several
                          # apparently sub-mm residuals had nearest connectable
                          # islands 18-45mm apart.  The bounded guarded maze at
                          # 50mm closed four of those (23 -> 19) with an
                          # identical DRC-type/count vector after plane refill;
                          # at 50mm no residual cluster remained distance-only.
                          "lastmile_max_mm": 50.0,
                          # Four nearest-anchor attempts are enough to rank the
                          # parallel fanout. Wave 68 proved that eight attempts
                          # on the selected board close two more legal bridges
                          # with the exact same DRC vector. Keep that measured
                          # depth, but pay for it once after selection instead
                          # of in every one of the 16 route workers.
                          "lastmile_attempts": 4,
                          "lastmile_final_attempts": 8,
                          # Exhaustive whole-board exact maze completion is a
                          # winner-only expense. Ordinary probes retain the
                          # measured 50mm canonical/bridge pass; the selected
                          # deep polish may brute-force low-risk control nets
                          # across the full Hub diagonal and must report every
                          # refusal explicitly.
                          "lastmile_final_winner": True,
                          "lastmile_final_max_mm": 100.0,
                          "lastmile_final_maze_max_mm": 100.0,
                          "lastmile_final_maze_margin_mm": 8.0,
                          # In2 remains a real signal layer in the approved
                          # six-layer profile. The legacy flag stays enabled for
                          # compatibility with four-layer seed boards only.
                          "inner_power_routing": True,
                          **mating_frame_pins(86.0, 74.0, MEZZ_HUB_24PIN,
                                              "hub-standard-rev2"),
                          # Only true mechanical/UI datums are hard-pinned.
                          # Large electrical parts remain movable so the craft
                          # placer can jointly satisfy their mechanical body
                          # clearance and current-loop locality.  C1 used to be
                          # pinned here; after the mezzanine frame moved that
                          # stale seat made the hold-up capacitor 30.3 mm from
                          # its nearest +5V_HOLD device and rendered every
                          # otherwise-clean placement inadmissible.
                          "anchor_pins": {
                              **mating_frame_pins(
                                  86.0, 74.0, MEZZ_HUB_24PIN,
                                  "hub-standard-rev2")["anchor_pins"],
                              # Top-side debug access near the upper-right
                              # edge; no second-side PCBA operation for two
                              # buttons that are used only while disassembled.
                              "SW_RESET": (75.0, 20.0, 0.0),
                              "SW_BOOT": (75.0, 27.0, 0.0),
                          },
                          "mount_holes": "corners", "connector_overhang": "edge",
                          "corner_radius": 2.5,   # owner 2026-07-15: rounded edges
                          # owner batch 2026-07-15: WROOM ON the edge, antenna OUT.
                          # 21.5mm allowance = keepout-drawing depth (27.75) minus the
                          # pad row (5.26) minus 1mm guard -- pads stay on-board.
                          "mcu_cluster_seat": True,
                          "antenna_overhang": 6.5,
                          # wave-6 root cause was the stock WROOM courtyard (48x41 antenna
                          # keepout wing, dropped per beta ruling W9 -> _NoAntKeepout
                          # variant); overhang rescaled 21.5->6.5 for the body-only
                          # courtyard (top -13.0, pads -5.26, >=1.2mm inside the edge).
                          "mcu_slim_axis": "y",  # sideways pack: antenna column stays clean for the edge seat
                          "respect_antenna_keepout": False,   # W9/D-6a: no Wi-Fi ever
                          "anchor_roles": {"J_USB": "usb",
                                           "J2": "host", "J3": "host",
                                           "J4": "host", "J5": "host",
                                           "J_KVM": "host",
                                           # board-to-board mezz segments, interior --
                                           # never an edge (2026-07-22 segmented split)
                                           "J6P": "free", "J6C": "free",
                                           "J6D": "free"},
                          # Native Hub top view: four jacks face LEFT. Reflecting
                          # the populated Hub to mate makes their mouths face RIGHT
                          # with ATX IN at bottom and OUT at top. Four 18.5mm
                          # courtyards require the 74mm edge.
                          "edge_override": {"J2": "left", "J3": "left", "J4": "left",
                                            "J5": "left", "J_USB": "bottom",
                                            "J_KVM": "bottom"},
                          # Connector-local high-speed cell. The USBLC6 is a
                          # flow-through part: rotate it so the reversible
                          # Type-C pair enters one pin row and leaves the other,
                          # while the CC pull-downs flank (rather than block)
                          # the differential breakout corridor. Coordinates
                          # are in J_USB's local frame and follow any future
                          # edge/orientation transform of the connector.
                          "anchor_local_placements": {
                              "D6": {"owner": "J_USB", "offset": (0.85, -8.425),
                                     "rotation": 270.0},
                              # Keep the two CC pull-downs symmetric outside
                              # the connector's VBUS banks.  The former -2.25
                              # mm X offset put R9 directly under the left
                              # VBUS escape; four legal router searches then
                              # had no path between the reversible connector's
                              # two power-pad clusters.  The symmetric flank
                              # preserves the differential corridor and leaves
                              # room for a two-via SIG2 VBUS bridge.
                              # CC1's A5 land exits between the left VBUS bank
                              # and the connector body.  The prior seat still
                              # overlapped J_USB's courtyard and aimed the
                              # resistor across that bank.  Move it 0.425 mm
                              # inward: the body clears the connector and
                              # A5 gains a proved 0/45/90 escape.  CC2 keeps its
                              # established seat because the reversible pin
                              # field is not geometrically mirror-symmetric.
                              "R9": {"owner": "J_USB", "offset": (-3.45, -6.25),
                                     "rotation": 90.0},
                              "R10": {"owner": "J_USB", "offset": (3.45, -5.825),
                                      "rotation": 90.0},
                          },
                          # Centerpiece (owner: "the center logo and LEDs"): six LEDs
                          # (DL1-5,DL7) plus their six dedicated 100nF bypass capacitors
                          # form one rigid macro. Each capacitor is 2.95mm above its LED:
                          # about 0.9mm clear of the internal Edge.Cuts aperture while
                          # remaining close to the opposite-diagonal VDD/GND pads.
                          # Logo = BACK copper, outward after the dead-bug flip.
                          "rigid_groups": [{"score": "center", "logo": True, "offsets": {
                              # Rotate the serial-data lands tangentially
                              # around the physical chain.  Identical 0-degree
                              # rotations aimed three DIN/DOUT links through
                              # the logo/LED apertures and made the two outer
                              # gaps 13.74/14.27 mm.  These orientations retain
                              # the exact ring centres while reducing every
                              # inter-LED data span below 8 mm.
                              "DL1": (-0.08, -10.42, 90), "DL2": (7.42, -4.32, 90),
                              "DL3": (9.92, 5.68, 0), "DL4": (-0.08, 7.68, 0),
                              "DL5": (-10.08, 5.68, 270), "DL7": (-7.08, -4.32, 270),
                              # Rotating the rectangular reverse LEDs swaps
                              # their courtyard axes.  Keep each bypass cap
                              # outside that real courtyard and aim its +5VSB
                              # land back at pad 4; every rail-pad span remains
                              # <=2.5 mm on the four rotated LEDs.  DL3/DL4
                              # retain their already legal inner seats so the
                              # ring/logo macro does not claim extra board
                              # area merely for visual radial spacing.
                              "C29": (2.92, -11.92, 270), "C30": (8.67, -8.57, 0),
                              "C31": (9.92, 8.63, 0), "C32": (-0.08, 10.63, 0),
                              "C33": (-11.33, 9.93, 180), "C34": (-10.08, -2.07, 90)}}],
                          "logo_at": "ring",
                          "logo_side": "back",
                          "fixed_back_refs": (),
                          "stack_gap_mm": mezz.STACK["board_gap_mm"],
                          "stack_inward_height_mm": mezz.STACK["inward_component_height_mm"],
                          "logo_ring_refs": ("DL1", "DL2", "DL3", "DL4", "DL5", "DL7")},
    "12vhpwr-standard": {"mount_holes": "none", "connector_overhang": "edge",
                         "respect_antenna_keepout": False,
                         # PRECISION RE-ENABLED (2026-07-14, same day as the stopgap):
                         # the bulldozer was CONVICTED as route_tiered routing its
                         # refused-pair tier BLIND to locked cell/lane copper (the
                         # restriction strips foreign pin lists; FR 1.7.0 drops
                         # protect wires of pin-less nets -- pre-tier DRC 13 -> 219
                         # structural, M3 24 vs M4 80). CURED: the tier now bakes
                         # locked-copper keepouts + a refuse-loud structural gate
                         # (cec_staged_fr). Precision-first stays the architecture
                         # per the owner's blind-AB ruling (important routes only).
                         "wave_precision": True,
                         "wave_pair_grid": True,
                         # straight-through power path (owner): 12V-2x6 IN top, OUT
                         # bottom -- J3/J4 defeat the net-role classifier (both stacked
                         # at origin, measured), so pin them explicitly.
                         "anchor_roles": {"J3": "power_in", "J4": "power_out"},
                         # J2 fan header PINNED beside the lane-6 pre-shunt tap
                         # (owner GO 2026-07-15): internal + DNP, position free by
                         # ruling; here /FAN_12V is a ~4mm spur instead of the
                         # cross-board fat net that stranded critical every wave
                         # (and poisoned the lane-6 kelvin pair check via its HI
                         # alias). The net-keyed fan-gate seat follows J2.
                         "anchor_pins": {"J2": (48.5, 23.5, 90)},
                         "straight_through": True,
                         # force lanes: lay the DRC-proven fat J3->RS->J4 copper LOCKED at
                         # materialize + reserve its corridors at placement (owner 2026-07-11,
                         # "set and not infringed on")
                         "force_lanes": True,
                         # OPTION A (owner 2026-07-12): lane axis at x=22 (span 5..39), logic
                         # column right (~x43..62). J3/J4 pad fields + cells center on THIS,
                         # not W/2.
                         "lane_center": float(os.environ.get("CEC_LANE_CENTER", "22.0")),  # 0 = board-centered (A/B knob, owner 2026-07-12 "try both")
                         "lane_pitch": 6.8,   # B7 blueprint copper spans 6.25mm across-pitch (MEASURED; gnd vias + tap waypoints) + 0.45 clearance + slack. The
                         # refiner scoring gap (pitch counted parts only) is FOLLOWUPS --
                         # a copper-aware re-refine should get back to the hand 6.0.
                         "wave_passes": 8, "wave_opt": 10, "wave_fr_timeout": 1200},
    # OWNER LADDER RULING (2026-07-11, "start with the connectors placed only ...
    # then the sensing frontend ... ladder up the importance list"): the fresh
    # 12vhpwr build stamps the six refined sensing cells as RIGID blueprint
    # blocks (internal copper laid + LOCKED at materialize; ideal_internal False
    # keeps the B7 refined routing -- textbook taps + GND vias + mitre).
    # blueprint_cells is injected below (needs the lane loop).
    "atx-24pin-rev3": {
                       # MEZZANINE ALIGNMENT CONTRACT (owner 2026-07-20 "they
                       # need to be cross-coordinated"; SEGMENTED 2026-07-22):
                       # the Hub stacks on the 24-pin CENTER-ALIGNED and reflected;
                       # the shared frame = MEZZ_HUB_24PIN's three structural
                       # segments (v4: J6P/J6D right column, J6C top strip)
                       # + one provisioned M2. NOTE the frame math uses
                       # the STATIC BOARD_WH (86x95); a runtime H-grow (e.g.
                       # SHUNT_GAP -> 59) only biases the stack's centering
                       # over the 24-pin, never the mate (constant-translation
                       # invariant, test_mating_frame).
                       **mating_frame_pins(86.0, 95.0, MEZZ_HUB_24PIN,
                                           "atx-24pin-rev3"),
                       # Only mechanical stack datums are pinned.  U1 remains a
                       # movable macro so seed-era placer limits cannot inflate
                       # the board-size floor.
                       "anchor_pins": {**mating_frame_pins(
                           86.0, 95.0, MEZZ_HUB_24PIN,
                           "atx-24pin-rev3")["anchor_pins"]},
                       "corner_radius": 2.5,
                       "connector_overhang": "edge",
                       # Assembly datum: 24-pin PSU input at the BOTTOM, output
                       # blade field at the TOP.  J2 is the remaining Hub power
                       # connector; obsolete RJ-45 J1 is retired at source.
                       "anchor_roles": {"J3": "power_in", "J2": "power_out"},
                       "edge_override": {**{f"TB{i}": "top" for i in range(1, 11)},
                                         "J_SIG1": "top", "J3": "bottom",
                                         "J2": "right"},
                       # wireless unpopulated: NO antenna keepout (owner 2026-07-08); the module's
                       # physical antenna section just rides at an edge like any body extent.
                       "respect_antenna_keepout": False,
                       # SINGLE-SIDED (owner 2026-07-19: "make it single sided" --
                       # supersedes the 2026-07-08 F/B alternation GO). Going single-
                       # sided also removes the dual-sided y-stagger repair, which is
                       # exactly the interplay that broke the straight-through centroid
                       # shunt columns (v3-a, measured residual 3->22 then reverted).
                       "dual_sided": False,
                       # ZONE CREATOR (owner GO 2026-07-19): per-rail force trunks
                       # (cec_force_rails -- J3 group -> straddle shunt -> TBs) laid
                       # locked at materialize; refusals teach the placer.
                       "force_rails": True,
                       # B.Cu trunk mirror (owner 2026-07-19: single-sided
                       # assembly leaves the bottom free -- twin the In2
                       # trunks there, bonded by the through arrays/barrels)
                       "rail_mirror_bcu": True,
                       # FR headroom under parallel-chain contention (filed
                       # 2026-07-20: 900s sentinel-timed-out a loaded route)
                       "wave_fr_timeout": 1500,
                       # winner band 146-158 unconn vs true collapse flat at
                       # 190-230 (attribution matrix 2026-07-20) -- 170 splits
                       "wave_plateau_floor": 170,
                       # LAYER-CROSSING RAILS (owner 2026-07-19: "it should be able
                       # to cross layers with via arrays ... keep one INNER layer
                       # as GND, use the other for power routing"): In1 = the solid
                       # GND plane, In2 = the rail alt layer -- bands/sinks on In2
                       # direct into the J3/TB THT barrels, via arrays only at the
                       # SMD shunt stubs. inner_power_routing frees In2 in
                       # build_board (the board-class stackup exception made real).
                       "inner_power_routing": True,
                       "rail_alt_layer": "In3.Cu",
                       # RUNG 2 (2026-07-23, scoped on s213 with the fixed
                       # guards): the 20 critical-net pads outside every rail
                       # flood are SCATTERED logic-side decoupling/taps --
                       # region extension would be the mega-pour anti-pattern;
                       # the right tools are the stitch (dry-fired 12 on s213)
                       # + the lastmile completer (kelvin nets excluded inside
                       # it -- sense connects only through authored taps).
                       "power_pickup": True,
                       "plane_tht_exclude": True,
                       # FULL SLAB A/B LIVE (owner GO 2026-07-24 "implement it all"):
                       # rail dicts slab-shave too -- the widest bonded In2 primary
                       # is the unconn-recovery + deficit-closure path
                       "slab_pour": True,
                       # OVER-UNDER POURS (owner GO 2026-07-24 "Yes, let's do
                       # it"): v2 routed-object pours -- single-layer lanes +
                       # via bridges at snags, vacated layer carries nothing
                       # (docs/slab-pour-design-2026-07-24.md v2). With
                       # slab_pour=True above, CEC_OVERUNDER takes precedence
                       # in import_ses' conversion branch; slab shave stays
                       # the fallback when over-under finds no path.
                       "overunder": True,
                       # PRE-FR CORRIDOR RESERVATION A/B (agent-landed
                       # 2026-07-25, e2e-proven: 5/9 nets reserved ~1.6s,
                       # realized 5/5 s416 / 4/5 s435, no completion
                       # collapse, DRC even improved on s435): corridors
                       # baked as DSN keepouts pre-route, pour-owned pads
                       # excluded from FR -- "the pour takes priority and
                       # gets its route first."
                       "pour_reserve": True,
                       # POUR-FIRST PLACEMENT RUNG (owner ruling 2026-07-25,
                       # docs/slab-pour-design-2026-07-24.md v3/v3.1): pours
                       # are solved + SET IN STONE on the anchor-only board
                       # (connectors + blueprint stamps + MCU) right after
                       # seating, then everything else re-adds AROUND the
                       # frozen state -- csp.pour_first_stage in
                       # _build_session freezes route-side state + placer
                       # avoid boxes + the owner-review POURFIRST artifact.
                       # slab_pour/overunder/pour_reserve above stay the
                       # live machinery for UN-frozen nets (and the whole
                       # board when this is off -- the A/B lever).
                       "pour_first": True,
                       # v4 TERRITORY POUR PLANNER (owner GO 2026-07-25,
                       # docs/slab-pour-design-2026-07-24.md v4): the
                       # pour-first solve runs cec_pour_plan.plan_pours --
                       # straight geometric corridors + exact layer
                       # assignment + compact labeled via fields; the
                       # direction-state Dijkstra is DEMOTED to loud
                       # per-net fallback inside the planner. Acceptance
                       # measured on the s464 skeleton 2026-07-25: 7/9
                       # planned (over-under baseline 6/9), zero mid-span
                       # via fields, every field at a terminal.
                       "pour_plan": True,
                       "lastmile": True,
                       # LOGIC-RAIL FLOODS (2026-07-24, from the s230 residual:
                       # +3V3 alone = 20 unconn items, +5VSB/+5V_MAIN 4+4 --
                       # scattered logic-side supply pads with NO flood for the
                       # stitch to bond into; the rail compiler only floods the
                       # J3/TB/trunk regions. The hub pattern: additive In2
                       # asks, regions auto-derived from each net's pads,
                       # post-route only (evac False).
                       "pour_asks": [
                           {"net": n, "region_hint": None,
                            "layers": ("In3.Cu",), "shape": "rect",
                            "priority": 2, "provenance": "placer_ask",
                            "evac": False}
                           for n in ("+3V3", "+5VSB", "+5V_MAIN")],
                       # LED-chain-class gaps sit at 7-10mm (measured s140/s120:
                       # DL* daisy links just past the 5mm default)
                       "lastmile_max_mm": 8.0,
                       # 4.2 (atx24-out-db as-built) predates the iteration-7 TE 63969
                       # receptacle swap -- its 4.29mm courtyard cannot pack at 4.2. Use the
                       # eps-proven 4.7 contiguous; the DRAFT daughterboard re-pitches to
                       # match (owner-queued 2026-07-08).
                       "blade_pitch": 4.7, "blade_group_gap": 4.7,
                       # 96-part dual-sided board: FR pass time ~16-21s (measured); the eps
                       # effort (16/20) blows the 600s budget. 8/10 completes in ~2-4 min.
                       "wave_passes": 8, "wave_opt": 10, "wave_fr_timeout": 1200},
}

# Approved 2026-08-01 six-layer fabrication policy. The Hub keeps 1 oz
# outers; every high-current module uses 2 oz outers. Both profiles reserve
# In1/In4 as ground, route signals on F/In2/B, and place power copper on In3.
for _board_name in ("eps-8pin-rev3",
                    "pcie-8pin-2port", "pcie-8pin-3port",
                    "12vhpwr-standard", "atx-24pin-rev3"):
    _p = BOARD_PARAMS.setdefault(_board_name, {})
    _p["stackup_profile"] = "jlcpcb_6l_pofv_high_current"
    _p["power_pour_layers"] = ("In3.Cu", "B.Cu", "F.Cu", "In2.Cu")
    _p["thermal_board_hint"] = _board_name

# PCIe cable interposers use mixed-net edge headers and one Kelvin shunt per
# cable.  A bounding-box pour is not a valid implementation of that topology:
# it blankets the header's GND row, forces antipad throats, and used to leave a
# stale slab behind whenever the terminal row moved.  Give both SKUs the same
# routed-object pour flow.  The placement solve freezes the current corridors
# first, reserves their exact geometry from the signal router, and the import
# stage replaces (rather than accumulates) the generated force-net zones.
for _board_name in ("pcie-8pin-2port", "pcie-8pin-3port"):
    _p = BOARD_PARAMS[_board_name]
    _p.update({
        # Four true corner mounts leave the board centre available to routing
        # and restore the mechanically symmetric four-screw pattern.  The MCU
        # macro solver below then co-optimizes the radio plus its owned local
        # passives and rotates the antenna outward at a board edge instead of
        # letting an ordinary free-IC placement consume central routing area.
        "mount_holes": "4_corner",
        "mcu_cluster_seat": True,
        "mcu_slim_axis": "x",
        "mcu_antenna_edge": "left",
        "antenna_overhang": 5.0,
        "respect_antenna_keepout": True,
        "inner_power_routing": True,
        "rail_alt_layer": "In3.Cu",
        "slab_pour": True,
        "overunder": True,
        "pour_reserve": True,
        "pour_first": True,
        "pour_plan": True,
        "power_pickup": True,
        "plane_tht_exclude": True,
        "lastmile": True,
        # Keep the ordinary import pass local, then spend whole-board exact
        # maze effort on the selected/polish context.  This is the same
        # low-risk completion contract used on the Hub: differential,
        # Kelvin/sense, ground, clock, and power-width nets remain owned by
        # their specialized compilers, while ordinary GPIO/status/control
        # ratlines are not allowed to survive merely because their component
        # islands are more than the historical 5 mm apart.
        "lastmile_max_mm": 8.0,
        "lastmile_attempts": 4,
        "lastmile_final_attempts": 8,
        "lastmile_final_winner": True,
        "lastmile_final_max_mm": 100.0,
        "lastmile_final_maze_max_mm": 100.0,
        "lastmile_final_maze_margin_mm": 8.0,
        # At the 39 A cable design basis, the 1.25 geometry margin makes a
        # single 2 oz outer conductor wider than the compact board permits.
        # Route one obstacle-cleared geometry on both outers and prove each
        # layer for half of the margin-inclusive 48.75 A geometry basis. This
        # is 125% aggregate capacity versus the 39 A cable rating; the 25%
        # reserve also covers current-share mismatch. The exact 0.51 probe no
        # longer fits, so increasing this fraction would be a false contract.
        "power_parallel_layers": ("B.Cu", "F.Cu"),
        "power_parallel_fraction": 0.50,
        "power_parallel_min_amps": 20.0,
        # Cable mouths are mechanically fixed to the top edge and outward
        # orientation, but their coordinate ALONG that edge is not a mating
        # datum. Let the exact parallel-pour solver slide only that declared
        # degree of freedom when a current corridor is otherwise impossible.
        # The generic repair engine retains the smallest improving slide and
        # still requires final courtyard/electrical-craft closure.
        "power_corridor_anchor_slides": {
            "J_IN1": {"axis": "x", "step_mm": 4.0, "max_mm": 12.0},
            "J_IN2": {"axis": "x", "step_mm": 4.0, "max_mm": 12.0},
        },
        "power_corridor_placement_rounds": 4,
        "power_corridor_placement_trials": 96,
        "power_corridor_placement_step_mm": 4.0,
        "power_corridor_placement_max_mm": 8.0,
        # Service ports share the right edge with the removable output
        # terminal/daughterboard interface.  Preserve at least 1 mm between
        # their physical courtyards in both axes so a cable shell cannot foul
        # insertion or removal.  The repair is footprint/edge driven and is
        # reusable by any board that declares this mechanical margin.
        "service_interface_clearance_mm": 1.0,
    })

# The two-port layout has a mechanically clear upper-left service pocket.
# Keep BOOT/RESET together there on the assembly side; the generic corner-seat
# solver still derives exact coordinates from courtyards, mounts, and
# fiducials, so this is a board intent rather than a coordinate special case.
BOARD_PARAMS["pcie-8pin-2port"]["button_pair_corner"] = "top_left"
BOARD_PARAMS["pcie-8pin-2port"]["button_pair_corner_inset_mm"] = 10.0
BOARD_PARAMS["pcie-8pin-2port"]["button_pair_target_mm"] = (9.0, 14.0)

# The two-port board's lower component band follows the removable terminal
# edge, so retaining the original 55.7 mm outline after that band was packed
# left an unearned strip of laminate.  Ask the generic outline-floor search to
# test height-only reductions and move only footprints that explicitly belong
# to the receding bottom edge.  J5 sits above the automatic 15 mm band but must
# follow it to preserve the declared terminal/service-port clearance.  The
# generic collision-graph repacker may evacuate only the new local overlaps,
# preserving bypass cells and intentional connector body overhang.  Exact
# materialization still rejects any pad, courtyard, craft, route-authority, or
# service-clearance blocker.  A 0.5 mm sweep retains assembly margin instead of
# skipping the true physical floor.  The admitted 50.2 mm candidate still left
# 4.85 mm below the terminal courtyards; extend the bounded search to 46.5 mm,
# where the 0.5 mm lattice can test 46.7 mm with about 1.35 mm of courtyard
# margin.  This is a measured search bound, not a forced board dimension.
BOARD_PARAMS["pcie-8pin-2port"]["outline_compaction"] = {
    "enabled": True,
    "step_mm": 0.5,
    "max_steps": 15,
    "minimum_height_mm": 46.5,
    "shrink_axes": ("height",),
    # Fiducials are optical registration features, not mechanical datums.
    # Keep them available to the generic corner reseater when an outline or
    # route corridor changes; never inherit a prior rigid edge-follow claim.
    "edge_follow_exclude_refs": ("FID1", "FID2", "FID3"),
    "edge_follow": (
        {
            "edge": "bottom", "refs": ("H3", "H4"),
            "mode": "rigid",
        },
        {
            "edge": "bottom", "margin_mm": 15.0, "refs": ("J5",),
            "exclude_refs": ("H3", "H4", "FID1", "FID2", "FID3"),
            "mode": "contain", "clearance_mm": 0.05,
        },
    ),
    # Preserve the already admitted macro topology while discovering its
    # outline floor.  A fresh global placement remains available as a separate
    # deliberate search mode instead of being conflated with edge compaction.
    "include_incremental": True,
    "include_fresh_placement": False,
    "repack_collisions": True,
    "repack_max_steps": 8,
    "repack_beam_width": 32,
    "repack_max_variants": 4,
    "repack_clearance_mm": 0.10,
    # Outline variants receive the cheap physical/craft screen.  Only the
    # selected smallest legal candidate pays for exact power authority and
    # important-route proof at the canonical placement boundary.
    "probe_route_repair_trials": 0,
    # Compare hard route feasibility before area, then use soft congestion
    # only after area.  This makes the result the smallest routable outline,
    # rather than simply the smallest mechanically legal outline.
    "probe_route_preflight": True,
}

# The current-path anchors come from the XFCN integration authority, not a
# second set of coordinates in the placer.  Pinning only J_IN/RS while leaving
# the replacement terminals movable let the generic edge packer collapse a
# valid 12 mm pair into overlapping 4.7 mm seats on the first full run.
import cec_xfcn_contract as _xfcn_contract             # noqa: E402
for _board_name, _project_name in (
        ("pcie-8pin-2port", "pcie2-main"),
        ("pcie-8pin-3port", "pcie3-main")):
    BOARD_PARAMS[_board_name]["anchor_pins"] = (
        _xfcn_contract.power_path_anchor_placements(
            _xfcn_contract.PROJECTS[_project_name]))
    _channel_count = 2 if _board_name == "pcie-8pin-2port" else 3
    # The input-to-shunt conductors are the pin-escape-critical commodities.
    # Claim their corridors before the downstream distribution paths when all
    # have the same design current.  This is topology intent, not a planner
    # special case, and any future board can declare its own ordering.
    BOARD_PARAMS[_board_name]["power_route_priority_nets"] = tuple(
        [f"/SENSEC{n}_HI" for n in range(1, _channel_count + 1)]
        + [f"/SENSEC{n}_LO" for n in range(1, _channel_count + 1)])

BOARD_PARAMS["hub-standard-rev2"]["stackup_profile"] = \
    "jlcpcb_6l_pofv_signal"
BOARD_PARAMS["hub-standard-rev2"]["power_pour_layers"] = \
    ("In3.Cu", "B.Cu", "F.Cu")
BOARD_PARAMS["hub-standard-rev2"]["thermal_board_hint"] = \
    "hub-standard-rev2"

# The six refined sensing cells (owner ladder ruling 2026-07-11): rigid blueprint
# stamps anchored on the placer's own lane seats (RS{n}), inheriting each seat's
# rotation; cable_index drives the per-lane net map; ideal_internal False keeps
# the B7 refined copper verbatim.
_SENSE_LANE_BP = "beta/12vhpwr-standard/blueprints/sense-lane-rs4-b7.json"
try:
    import json as _json
    with open(os.path.join(ROOT, _SENSE_LANE_BP)) as _f:
        _BP_ROLES = _json.load(_f)["net_roles"]
except Exception:                                  # noqa: BLE001 -- board sans blueprint still works
    _BP_ROLES = {}


def _lane_net_map(n):
    """Per-lane net map (net_map_for_index's rule, pcbnew-free so this module
    stays host-importable) + the beta sheets' lane-6 exception: J2's fan feed
    taps PRE-SHUNT lane 6 (spec enclosed menu), so that node is /FAN_12V, not
    /SENSEP6_HI (measured: lane 6 refused 'net not on destination board')."""
    m = {role: (role.format(n=n) if role.count("{n}") == 1 else lit)
         for role, lit in _BP_ROLES.items()}
    if n == 6 and "/SENSEP{n}_HI" in m:
        m["/SENSEP{n}_HI"] = "/FAN_12V"
    return m


# 24-PIN SENSE-CELL STAMPS (owner ask 2026-07-19 "it needs to stamp out the
# INA238 and INA181 blueprint" -- the rung had NEVER fired on this board): one
# v0 template (scripts/gen_24pin_sense_cell.py -- RS + INA238 + INA181A2 +
# TLV7011, parts packed PERPENDICULAR to the pad axis so both pad-axis
# approaches stay free for the force-rail stubs/arrays, the v3-keystone rule),
# four stamps anchored at the blade-row shunt seats. ideal_internal synthesizes
# the one internal net (DETAMP: 181-out -> 7011-in); kelvin copper stays the
# precision tap pass's job. Bypass/threshold passives keep auto_cluster
# ownership (they cluster to these stamped positions).
_SENSE_RAIL_BP_24 = os.path.join(ROOT, "beta", "atx-24pin-rev3",
                                 "blueprints", "sense-rail-v0.json")
_SENSE_RAIL_BP_24_LEFT = os.path.join(ROOT, "beta", "atx-24pin-rev3",
                                      "blueprints", "sense-rail-v0-left.json")
_SENSE_RAIL_BP_24_TAPS = os.path.join(ROOT, "beta", "atx-24pin-rev3",
                                      "blueprints", "sense-rail-v0-taps.json")
_BP_RAILS_24 = {
    "RS1": ({"RS2": "RS1", "U11": "U10", "U65V1": "U612V1", "U75V1": "U712V1"},
            {"CELL_HI": "/SENSE12V_HI", "CELL_LO": "/SENSE12V_LO",
             "CELL_DET": "/DET12V", "CELL_DETAMP": "/DETAMP12V"}),
    "RS2": ({"RS2": "RS2", "U11": "U11", "U65V1": "U65V1", "U75V1": "U75V1"},
            {"CELL_HI": "/SENSE5V_HI", "CELL_LO": "+5V_MAIN",
             "CELL_DET": "/DET5V", "CELL_DETAMP": "/DETAMP5V"}),
    "RS3": ({"RS2": "RS3", "U11": "U12", "U65V1": "U63V31", "U75V1": "U73V31"},
            {"CELL_HI": "/SENSE3V3_HI", "CELL_LO": "/SENSE3V3_LO",
             "CELL_DET": "/DET3V3", "CELL_DETAMP": "/DETAMP3V3"}),
    "RS4": ({"RS2": "RS4", "U11": "U13", "U65V1": "U65VSB1", "U75V1": "U75VSB1"},
            {"CELL_HI": "+5VSB", "CELL_LO": "/SENSE5VSB_LO",
             "CELL_DET": "/DET5VSB", "CELL_DETAMP": "/DETAMP5VSB"}),
}
BOARD_PARAMS["atx-24pin-rev3"]["blueprint_cells"] = [
    # PER-RAIL BANK HANDEDNESS (owner render pass 2026-07-19, the J1/J6
    # wedge): the bank lands board-RIGHT of the column at the 270 seats, so
    # the rightmost rails take the MIRRORED bank-left template (parts-only
    # for now) while RS3 -- whose left flank is J1 -- keeps the bank-right
    # v0 with the authored Kelvin-90 taps.
    # UNIFORM bank-right AUTHORED cells (owner render report 2026-07-19
    # evening: the route-time fallback taps were diagonal/wraparound spaghetti
    # -- the textbook-90 authored cell is now stampable because the
    # TLV-BESIDE redesign dropped its deep reach ~9.75 -> ~7.9, inside the
    # 11.9 walk pitch; the per-pair coverage guard then skips route-time
    # synthesis for these pairs). Mixed handedness still faces two banks in
    # one pitch -- uniform-right + the J1 tuck stands.
    {"template": _SENSE_RAIL_BP_24_TAPS, "anchor_ref": rs, "ideal_internal": True,
     "ref_map": rm, "net_map": nm}
    for rs, (rm, nm) in _BP_RAILS_24.items()]

BOARD_PARAMS["12vhpwr-standard"]["blueprint_cells"] = [
    {"template": _SENSE_LANE_BP, "anchor_ref": f"RS{n}", "net_map": _lane_net_map(n),
     "ideal_internal": False,
     "ref_map": {"RS4": f"RS{n}", "RFH4": f"RFH{n}", "RFL4": f"RFL{n}",
                 "CF4": f"CF{n}", "U13": f"U{9 + n}", "C13": f"C{9 + n}"}}
    for n in range(1, 7)]


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
    # straight_through boards (owner, 12vhpwr fun-run 2026-07-09): drop the periph
    # x-band partitions -- they relocate the power connectors into a side column,
    # defeating the top->bottom flow the global role edges give.
    if (BOARD_PARAMS.get(board) or {}).get("straight_through"):
        return [x for x in base if x[0] == "plain"]
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


def _board_params(board):
    """Resolve the shared board contract for serial and parallel paths.

    Legacy ``BOARD_PARAMS`` and manifest directives remain compatibility
    inputs; the declarative board-local policy is authoritative over both.
    """
    # Several placement contracts contain nested maps (anchor_pins,
    # mount_pos_override, role_keepouts).  A shallow copy lets a size sweep
    # accidentally mutate the process-global BOARD_PARAMS declaration.
    p = copy.deepcopy(BOARD_PARAMS.get(board) or {})
    mf = next((m for m in (os.path.join(ROOT, r, board, "board-manifest.json")
                           for r in ("beta", "modules", "hubs"))
               if os.path.isfile(m)),
              os.path.join(ROOT, "beta", board, "board-manifest.json"))
    if os.path.isfile(mf):
        try:
            with open(mf, encoding="utf-8") as f:
                pd = (json.load(f) or {}).get("placement_directives") or {}
            p.update({k: v for k, v in pd.items()
                      if not k.startswith("_") and not k.endswith(("_note", "_rules", "provenance"))})
        except Exception:                                  # noqa: BLE001
            pass
    import cec_board_policy
    p = cec_board_policy.merge_params(p, board, board_hint=board)
    # Pin-access ownership is a generic routing stage, not a Hub-only feature.
    # Boards may explicitly opt out while migrating, but an absent policy must
    # not hand dense IC launches straight to the global router and hope that a
    # late last-mile pass can recover them after congestion is established.
    p.setdefault("automatic_pin_escape_tier", True)
    # thermal config resolves by BOARD NAME, not the variant filename (wave variants
    # are plain-<strat>-s<seed>.kicad_pcb -> basename keying missed, the solve ran
    # configless and the new-best stamp mirage-FAILED dT~0 on its first live target,
    # 2026-07-19). Set HERE so BOTH the parent (_new_best_thermal) and the spawn
    # workers (_build_session -> grade -> _oracle_env) export CEC_THERMAL_BOARD_HINT.
    p.setdefault("thermal_board_hint", board)
    return p


def _placement_params(board, W, H):
    """Return the live, size-specific placement contract for *board*.

    This is the single public construction point for consumers that need the
    same BETA placement recipe as :func:`_build_session` without constructing a
    PlacementSession (notably the dedicated Hub closure runner).  Keeping the
    mating-frame resize here prevents those runners from silently falling back
    to the oracle's historical absolute connector seats.
    """
    p = _board_params(board)
    # Size sweeps must move the complete mating datum with the candidate
    # outline.  BOARD_PARAMS holds the nominal snapshot for consumers that do
    # not pass W/H, but using those absolute pins here made smaller-board probes
    # test stale connector coordinates instead of the requested geometry.
    if board in MEZZ_HUB_24PIN["sides"]:
        mf = mating_frame_pins(W, H, MEZZ_HUB_24PIN, board)
        p["mount_pos_override"] = mf["mount_pos_override"]
        if "mount_fp_override" in mf:
            p["mount_fp_override"] = mf["mount_fp_override"]
        anchors = dict(p.get("anchor_pins") or {})
        for ref in ("J6P", "J6C", "J6D"):
            anchors.pop(ref, None)
        anchors.update(mf["anchor_pins"])
        if board == "atx-24pin-rev3":
            # The legacy absolute U1 pin was a small-frame placer workaround,
            # not a mechanical datum. Let each sweep solve the MCU honestly.
            anchors.pop("U1", None)
        p["anchor_pins"] = anchors
    return p


def _build_session(board, W, H, iname, strat, seed, proposal=None, *,
                   pourfirst_artifact=True):
    """The variant's PlacementSession, identically for the place-only (prune) and
    full-grade phases -- factored so the two can never drift. *proposal* = a
    VALIDATED seat proposal dict (cec_wave_intents), applied instead of a named
    hand intent; its role_keepouts merge into params (the params-level lever)."""
    _p = _placement_params(board, W, H)
    if proposal is not None and proposal.get("role_keepouts"):
        _p = dict(_p)
        _p["role_keepouts"] = dict(proposal["role_keepouts"])
    # anchor_pins (owner GO 2026-07-15, J2-near-lane-6): hard user pins for
    # role-anchored connectors whose default edge seat is wrong for the design
    # (J2 is internal + DNP; beside the lane-6 tap /FAN_12V collapses to a local
    # spur -- the every-wave #1 critical strand + the kelvin-gate poisoner).
    _pins = dict(_p.pop("anchor_pins", {}) or {})
    s = PlacementSession(board, W=W, H=H, strat=strat, seed=seed, params=_p, pins=_pins)
    if proposal is not None:
        import cec_wave_intents
        cec_wave_intents.apply_proposal(s, proposal)
    else:
        dict(_intents_for(board))[iname](s)
    # POUR-FIRST RUNG (owner ruling 2026-07-25, docs/slab-pour-design-
    # 2026-07-24.md v3/v3.1; param "pour_first"): solve + FREEZE the pours on
    # the variant's anchor-only board BEFORE general placement/routing. Runs
    # in BOTH the prune and grade phases (this shared builder) so the cheap
    # place key ranks the same avoid-box placement the grade routes -- the
    # no-drift rule this function exists for. The owner-review artifact
    # (board + hex render into build/wave-snaps/<board>/) is written only on
    # the grade side (pourfirst_artifact; pure output, placement-inert).
    if _p.get("pour_first"):
        csp.pour_first_stage(
            s, out_dir=os.path.join(ROOT, "build", "wave-snaps", board),
            label=f"{iname}-{strat}-s{seed}", artifact=pourfirst_artifact)
        _rep = getattr(s, "pourfirst_report", None) or {}
        if _rep.get("error"):
            # FAIL-CLOSED on the grade side (owner ruling 2026-07-25: "none
            # of this is going to even be a shippable candidate ever until
            # [the new pour pipeline] is here" -- a variant whose pour stage
            # ERRORED must never become a publishable winner on the old
            # machinery via a silent revert). Prune side stays fail-open
            # (ranking only). CEC_POURFIRST_SOFT=1 = debug escape hatch.
            if pourfirst_artifact and os.environ.get(
                    "CEC_POURFIRST_SOFT") != "1":
                raise RuntimeError(
                    f"pour-first stage ERROR on {iname}-{strat}-s{seed}: "
                    f"{_rep['error']} (fail-closed: the pour pipeline is "
                    f"load-bearing; no old-machinery candidates)")
            print(f"[wave] {board} {iname}-{strat}-s{seed}: pour-first stage "
                  f"ERROR ({_rep['error']}) -- prune-side rank only",
                  flush=True)
    return s, _p


def _nested_craft_worker_budget(outer_workers, *, cpu_count=None):
    """Bound each candidate's inner craft pool to one share of the CPUs.

    Candidate placement and exact craft evaluation are both process-parallel.
    Without a nested budget, ``N`` outer candidates each start the full
    16-worker inner pool and oversubscribe even a large workstation.  Compute
    allocation changes latency only; proposal construction and deterministic
    admission keys remain identical.
    """
    cpus = max(1, int(cpu_count if cpu_count is not None
                      else (os.cpu_count() or 1)))
    outer = max(1, int(outer_workers or 1))
    return max(1, min(csp.MAX_PLACEMENT_CRAFT_EVAL_WORKERS,
                      cpus // outer))


def _route_repair_required(evidence, *, completion_hint_count=0):
    """Whether measured placement evidence requires bounded route repair.

    Critical pair, Kelvin, and route-quality refusals are placement failures
    even when ordinary pin-access and congestion counters are zero.  Omitting
    them from the dispatch predicate let a CAN launch reach detailed routing
    with no legal coupled portal although the exact repair engine and blocker
    evidence already existed.
    """
    evidence = evidence if isinstance(evidence, dict) else {}
    counters = (
        "critical_pin_access_blocked_count",
        "critical_pair_refused_count",
        "critical_kelvin_refused_count",
        "critical_route_quality_refused_count",
        "critical_unroutable_count",
        "future_critical_corridor_conflicts",
        "future_overflow_units",
    )
    return (int(completion_hint_count or 0) > 0 or any(
        int(evidence.get(key, 0) or 0) > 0 for key in counters))


def _persist_pourfirst_state(params, placed_board):
    """Publish ephemeral pour-first authority beside a resumable placement."""
    state_path = str((params or {}).get("pourfirst_state") or "")
    if not state_path or not placed_board or not os.path.isfile(state_path):
        return None
    with open(state_path, encoding="utf-8") as source:
        state = json.load(source)
    base = str(placed_board)[:-len(".kicad_pcb")]
    skeleton = str(state.get("skeleton") or "")
    if skeleton and os.path.isfile(skeleton):
        stable_skeleton = base + ".pourfirst-skeleton.kicad_pcb"
        shutil.copy2(skeleton, stable_skeleton)
        cec_fr.copy_project_sidecars(skeleton, stable_skeleton)
        state["skeleton"] = stable_skeleton
    stable_state = base + ".pourfirst-state.json"
    temporary = stable_state + ".tmp-%s" % os.getpid()
    with open(temporary, "w", encoding="utf-8") as destination:
        json.dump(state, destination, indent=2, sort_keys=True, default=str)
        destination.write("\n")
    os.replace(temporary, stable_state)
    params["pourfirst_state"] = stable_state
    return stable_state


def _pourfirst_resume_state_status(params):
    """Validate the authority needed to route a persisted placement."""
    params = params or {}
    if not params.get("pour_first"):
        return {"ok": True, "applicable": False}
    path = str(params.get("pourfirst_state") or "")
    if not path:
        return {"ok": False, "applicable": True,
                "reason": "missing_pourfirst_state"}
    try:
        with open(path, encoding="utf-8") as source:
            state = json.load(source)
    except Exception as exc:                              # noqa: BLE001
        return {"ok": False, "applicable": True, "path": path,
                "reason": "unreadable_pourfirst_state",
                "error": "%s: %s" % (type(exc).__name__, exc)}
    required = ("pours", "vias", "frozen_nets", "corridors",
                "exclude_pins", "reserve_report", "placements")
    missing = [key for key in required if key not in state]
    if missing:
        return {"ok": False, "applicable": True, "path": path,
                "reason": "incomplete_pourfirst_state",
                "missing": missing}
    if state.get("placement_scope") != "complete":
        return {"ok": False, "applicable": True, "path": path,
                "reason": "non_authoritative_pourfirst_placement_scope",
                "placement_scope": state.get("placement_scope")}
    frozen = list(state.get("frozen_nets") or ())
    if not frozen:
        return {"ok": False, "applicable": True, "path": path,
                "reason": "empty_pourfirst_authority"}
    if any(str((row or {}).get("provenance") or "") == "uniform_stamp"
           for row in state.get("pours") or ()):
        return {"ok": False, "applicable": True, "path": path,
                "reason": "legacy_uniform_stamp_authority"}
    reserved = state.get("reserve_report") or {}
    missing_reservations = sorted(
        net for net in frozen
        if not (reserved.get(net) or {}).get("reserved"))
    if missing_reservations or not state.get("corridors"):
        return {"ok": False, "applicable": True, "path": path,
                "reason": "incomplete_pourfirst_reservation",
                "nets": missing_reservations}
    return {"ok": True, "applicable": True, "path": path,
            "schema": state.get("schema"), "frozen_nets": frozen,
            "placement_scope": state.get("placement_scope")}


def _place_variant(board, W, H, iname, strat, seed, proposal=None,
                   work_root=None, craft_workers=None):
    """PRUNE PHASE 1 (roadmap throughput lever 1, owner GO 2026-07-17): compile the
    PLACEMENT only (seconds) and return the cheap production key -- the same
    csp._candidate_sort_key place_candidates ranks by (residual, corridor-aware,
    corridor, proxy). NO route, NO oracle: this exists so the wave can spend its
    FR minutes on the variants whose placements earn it. Errors return an
    error row -- the caller treats those FAIL-OPEN (never silently pruned on an
    infrastructure error; ranking-fidelity is the cost being managed, roadmap
    false-summit caveat)."""
    label = f"{iname}-{strat}-s{seed}"
    t0 = time.monotonic()
    try:
        s, _p = _build_session(board, W, H, iname, strat, seed, proposal,
                               pourfirst_artifact=False)
        pourfirst_report = copy.deepcopy(
            getattr(s, "pourfirst_report", None))
        if (s.cfg and (s.cfg.params or {}).get("pour_first")
                and (pourfirst_report or {}).get("error")):
            # A prune-side infrastructure/closure error is deliberately
            # fail-open in the *selection* sense: its row must reach the full
            # grade retry.  Continuing craft repair and future-route analysis
            # cannot make the already-invalid freeze rankable and used to
            # duplicate minutes of work before that guaranteed retry.  Return
            # the diagnostic error row immediately; _prune_variants retains
            # all such rows by contract.
            return {
                "label": label, "iname": iname, "strat": strat,
                "seed": seed, "place_key": None,
                "error": "pour-first: %s" % pourfirst_report["error"],
                "pourfirst": pourfirst_report,
                "place_wall_s": round(time.monotonic() - t0, 1),
            }
        if s.cfg and craft_workers is not None:
            # A board may explicitly request a smaller pool.  The wave owns
            # only the default allocation and never widens a declared limit.
            s.cfg.params.setdefault("placement_craft_eval_workers",
                                    max(1, int(craft_workers)))
        with csp._oracle_env(s.cfg.params if s.cfg else None):
            cand = s.compile()
            placed = None
            if work_root:
                placed = os.path.join(work_root, board,
                                      f"{label}-placed.kicad_pcb")
                os.makedirs(os.path.dirname(placed), exist_ok=True)
                s.materialize(placed, cand=cand)
                _persist_pourfirst_state(s.cfg.params, placed)
        craft_repair = None
        craft_trials = int((s.cfg.params if s.cfg else {}).get(
            # Electrical craft admission is a general pipeline contract, not a
            # Hub-only option.  A board without a local policy previously got
            # the detector but not its bounded monotonic repair, so the EPS
            # trial rejected three otherwise usable placements for an orphaned
            # rail bulk capacitor without ever attempting the repair that was
            # already implemented.  Boards may still override this budget.
            "placement_craft_repair_trials", 48) or 0)
        if placed and s.cfg and craft_trials > 0:
            with csp._oracle_env(s.cfg.params):
                repaired, craft_repair = csp.repair_placement_craft_epochs(
                    s.cfg, cand, max_trials=craft_trials,
                    rounds=int(s.cfg.params.get(
                        "placement_craft_repair_rounds", 2)),
                    epochs=int(s.cfg.params.get(
                        # The epoch engine stops immediately on a clean gate
                        # or a certified plateau.  Two epochs cut off the PCIe
                        # multi-rail cell while every epoch was still making a
                        # monotonic improvement; use the already-enforced hard
                        # ceiling so hard cells get a finite continuation,
                        # never an unattended open loop.
                        "placement_craft_repair_epochs", 4)))
            if craft_repair.get("changed"):
                cand = repaired
                with csp._oracle_env(s.cfg.params):
                    if s.cfg.params.get("pour_first"):
                        csp.pour_first_stage(
                            s, label=label, artifact=False,
                            candidate=cand)
                        if (s.pourfirst_report or {}).get("error"):
                            raise RuntimeError(
                                "post-craft pour-first regeneration failed: %s"
                                % s.pourfirst_report["error"])
                        cand = getattr(s, "pourfirst_candidate", cand)
                    s.materialize(placed, cand=cand)
                    _persist_pourfirst_state(s.cfg.params, placed)
        # Compile placement evidence under the same scoped route recipe used by
        # the later detailed route. Previously this call happened after the
        # recipe context closed, so the placer never saw CEC_POUR_RESERVE even
        # though Freerouting did.
        with csp._oracle_env(s.cfg.params if s.cfg else None):
            future_route = _future_route_preflight(
                placed, critical_nets=tuple(
                    (s.cfg.params if s.cfg else {}).get(
                        "critical_route_nets", ()) or ())) if placed else None
        route_repair = None
        completion_guidance = _completion_guidance_from_env()
        completion_hint_count = 0
        if completion_guidance:
            try:
                import cec_completion_evidence
                completion_hint_count = int(
                    cec_completion_evidence.placement_hints(
                        completion_guidance,
                        critical_nets=tuple((s.cfg.params if s.cfg else {}).get(
                            "critical_route_nets", ()) or ())).get(
                                "hint_count", 0) or 0)
            except Exception:                              # noqa: BLE001
                completion_hint_count = 0
        repair_trials = int(os.environ.get(
            "CEC_PLACEMENT_ROUTE_REPAIR_TRIALS",
            (s.cfg.params if s.cfg else {}).get(
                # Exact route-aware placement is a pipeline invariant, just
                # like craft repair. Leaving the default at zero meant
                # ordinary boards measured critical failures but never acted.
                "placement_route_repair_trials", 48) or 0))
        if (placed and s.cfg and repair_trials > 0
                and _route_repair_required(
                    future_route,
                    completion_hint_count=completion_hint_count)):
            # The placed board and Candidate stay coupled: the grade phase
            # reuses this file, so an accepted repair must be materialized here
            # rather than merely recorded as a better abstract placement.
            cand.route_preflight = dict(future_route)
            with csp._oracle_env(s.cfg.params):
                repaired, route_repair = csp.repair_route_preflight_iterative(
                    s.cfg, cand,
                    max_trials=repair_trials,
                    rounds=int(os.environ.get(
                        "CEC_PLACEMENT_ROUTE_REPAIR_ROUNDS",
                        s.cfg.params.get(
                            "placement_route_repair_rounds", 2))),
                    full_evals=int(os.environ.get(
                        "CEC_PLACEMENT_ROUTE_REPAIR_FULL_EVALS",
                        s.cfg.params.get(
                            "placement_route_repair_full_evals", 4))),
                    grid_mm=float(os.environ.get(
                        "CEC_WAVE_FUTURE_GRID_MM", "1.0")),
                    iters=int(os.environ.get(
                        "CEC_WAVE_FUTURE_ITERS", "4")),
                    backend="auto", multiresolution=False,
                    completion_report=completion_guidance)
            if route_repair.get("changed"):
                cand = repaired
                with csp._oracle_env(s.cfg.params):
                    s.materialize(placed, cand=cand)
                future_route = dict(cand.route_preflight or {})
        base_key = list(csp._candidate_sort_key(cand))
        # Physical craft is ranked before route capacity.  A placement with a
        # stranded functional part or a selected bypass capacitor outside its
        # device limit cannot become releasable merely because it is easier to
        # route, so do not spend the routed shortlist on that false summit.
        craft = (csp.placement_craft_evidence(placed, cfg=s.cfg)
                 if placed else None)
        craft_key = list(csp.placement_craft_key(craft))
        import cec_route_preflight
        # Use the exact same fail-closed fanout/access/reachability/capacity
        # definition as the core placer. A missing proof therefore cannot look
        # better merely because its tuple is shorter than a measured candidate.
        future_key = list(cec_route_preflight.placement_evidence_key(
            future_route))
        key = base_key[:1] + craft_key + future_key + base_key[1:]
        return {"label": label, "iname": iname, "strat": strat, "seed": seed,
                "place_key": [float(k) for k in key],
                "place_key_base": [float(k) for k in base_key],
                "place_craft_key": [float(k) for k in craft_key],
                "placement_craft": craft,
                "craft_repair": craft_repair,
                "residual": cand.residual, "corridor_cross": cand.corridor_cross,
                "placed": placed,
                "future_route": future_route,
                "route_repair": route_repair,
                "cfg_params": copy.deepcopy(s.cfg.params),
                "intent_log": list(s.log),
                "pourfirst": copy.deepcopy(
                    getattr(s, "pourfirst_report", None)),
                "place_wall_s": round(time.monotonic() - t0, 1)}
    except Exception as e:                                  # noqa: BLE001 -- fail-open
        return {"label": label, "iname": iname, "strat": strat, "seed": seed,
                "place_key": None, "error": "%s: %s" % (type(e).__name__, e),
                "place_wall_s": round(time.monotonic() - t0, 1)}


def _future_route_preflight(placed_board, *, critical_nets=(), grid_mm=None,
                            iters=None, multiresolution=None, backend=None):
    """Cheap, deterministic future-capacity proof used by placement pruning.

    This is the same hard foreign-copper/layer-aware negotiated router exposed
    by the dashboard, run at a deliberately coarse grid and four iterations.
    It does not lay copper.  Its role is to stop a visually compact placement
    from winning the prune phase when its remaining pin topology already
    contains unreachable connections or severe shared-corridor overuse.
    """
    if not placed_board or not os.path.isfile(str(placed_board)):
        return None
    try:
        import cec_route_preflight
        grid = (float(os.environ.get("CEC_WAVE_FUTURE_GRID_MM", "1.0"))
                if grid_mm is None else float(grid_mm))
        # Future-capacity evidence needs at least one negotiation pass.  An
        # access-only zero-iteration request otherwise returns no congestion
        # state and used to fail later with an opaque NoneType error.
        route_iters = max(
            1, (int(os.environ.get("CEC_WAVE_FUTURE_ITERS", "4"))
                if iters is None else int(iters)))
        use_multiresolution = (
            os.environ.get("CEC_WAVE_FUTURE_MULTIRESOLUTION", "0") != "0"
            if multiresolution is None else bool(multiresolution))
        has_multiresolution = hasattr(
            cec_route_preflight, "analyze_multiresolution")
        analyzer = (cec_route_preflight.analyze_multiresolution
                    if use_multiresolution and has_multiresolution
                    else cec_route_preflight.analyze)
        route_backend = (backend if backend is not None else
                         ("auto" if use_multiresolution
                          and has_multiresolution else "cpu"))
        analyze_kwargs = {
            "grid_mm": grid, "iters": route_iters,
            "backend": route_backend,
            **({} if use_multiresolution and has_multiresolution
               else {"run_congestion": True,
                     "run_future_congestion": True}),
        }
        analyze_kwargs.setdefault("run_future_congestion", True)
        # Preserve compatibility with analysis adapters that predate declared
        # route intent; an empty declaration carries no information and should
        # not force every dashboard/test double to grow the new keyword.
        if critical_nets:
            analyze_kwargs["critical_nets"] = tuple(critical_nets)
        report = analyzer(str(placed_board), **analyze_kwargs)
        evidence = cec_route_preflight.compact_placement_evidence(report)
        return {
            "grid_mm": grid,
            "iters": route_iters,
            "multiresolution_enabled": use_multiresolution,
            **evidence,
        }
    except Exception as exc:                              # noqa: BLE001
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _prune_variants(variants, placed_rows, k):
    """The prune DECISION (pure -- unit-tested): keep the top-*k* variants by their
    cheap place_key; a variant whose placement phase ERRORED stays in the route set
    (fail-open). Returns (route_variants, pruned_rows). k<=0 or fewer variants than
    k -> everything routes (byte-identical legacy wave).

    INTENT-CLASS FLOOR (first live firing, work14 2026-07-19): the raw top-K pruned
    ALL 12 seat-proposal variants and routed only the 4 plains -- the cheap key does
    not predict routability (the documented false-summit), and the pruned class is
    exactly the one that has been WINNING waves since 2026-07-14 (wave-3 winner = a
    seat proposal). Every intent class (v[0]) therefore keeps its best-by-key variant
    IN ADDITION to the top-K, so a proposal class can never be silently eliminated
    before it ever routes. CEC_WAVE_PRUNE_CLASS_FLOOR=0 restores the raw top-K."""
    if k <= 0 or len(variants) <= k:
        return list(variants), []
    by_label = {r["label"]: r for r in placed_rows}

    def _label(v):
        return f"{v[0]}-{v[1]}-s{v[2]}"

    keyed, erred = [], []
    for v in variants:
        row = by_label.get(_label(v))
        if row is None or row.get("place_key") is None:
            erred.append(v)                                  # fail-open: route it
        else:
            keyed.append((tuple(row["place_key"]), _label(v), v))
    keyed.sort(key=lambda t: (t[0], t[1]))
    keep = keyed[:max(0, k - len(erred))] if len(erred) < k else []
    if os.environ.get("CEC_WAVE_PRUNE_CLASS_FLOOR", "1") != "0":
        kept_classes = {v[0] for _key, _lbl, v in keep} | {v[0] for v in erred}
        for _key, _lbl, v in keyed:                          # sorted: first hit = class best
            if v[0] not in kept_classes:
                keep.append((_key, _lbl, v))
                kept_classes.add(v[0])
    route = [v for _key, _lbl, v in keep] + erred
    kept_labels = {_label(v) for v in route}
    pruned = [dict(by_label[_label(v)], pruned=True) for v in variants
              if _label(v) not in kept_labels]
    return route, pruned


def _refine_route_aware_shortlist(variants, placed_rows, shortlist_k, *,
                                  grid_mm=0.5, iters=3):
    """Coarse tournament followed by equal-resolution physical re-ranking.

    It is invalid to compare a .5 mm congestion residual directly with an
    unrefined 1.0 mm residual: the denser grid naturally has a different cell
    count and capacity scale.  Therefore the ordinary coarse key first chooses
    a bounded shortlist (retaining the existing error and intent-class floors),
    every measurable member of that shortlist receives the SAME fine proof,
    and only those rows proceed to the final prune.  A fine-analysis failure is
    marked unkeyed so the existing fail-open rule routes it.
    """
    if shortlist_k <= 0 or len(variants) <= shortlist_k:
        shortlist, coarse_pruned = list(variants), []
    else:
        shortlist, coarse_pruned = _prune_variants(
            variants, placed_rows, shortlist_k)
        for row in coarse_pruned:
            row["prune_stage"] = "coarse-route-aware-shortlist"
    by_label = {row.get("label"): row for row in placed_rows}
    refined = 0
    failed = 0
    started = time.monotonic()
    import cec_route_preflight
    future_key_len = len(cec_route_preflight.placement_evidence_key(None))
    for iname, strat, seed, _proposal in shortlist:
        label = f"{iname}-{strat}-s{seed}"
        row = by_label.get(label)
        if row is None or row.get("place_key") is None:
            continue
        placed = row.get("placed")
        if not placed or not os.path.isfile(str(placed)):
            row["place_key"] = None
            row["route_awareness_refine_error"] = "placed board is unavailable"
            failed += 1
            continue
        params = row.get("cfg_params") or {}
        fine = _future_route_preflight(
            str(placed), critical_nets=tuple(
                params.get("critical_route_nets", ()) or ()),
            grid_mm=grid_mm, iters=iters,
            multiresolution=False, backend="auto")
        row["future_route_coarse"] = copy.deepcopy(row.get("future_route"))
        row["route_awareness_refine"] = {
            "grid_mm": float(grid_mm), "iters": int(iters),
            "backend": (fine or {}).get("backend"),
            "service": copy.deepcopy(
                (fine or {}).get("route_awareness_service") or {}),
        }
        if not isinstance(fine, dict) or fine.get("error"):
            row["place_key"] = None                    # fail-open: route it
            row["route_awareness_refine_error"] = (
                (fine or {}).get("error") if isinstance(fine, dict)
                else "missing fine route-awareness proof")
            failed += 1
            continue
        base_key = row.get("place_key_base")
        craft_key = row.get("place_craft_key")
        if craft_key is None:
            craft = csp.placement_craft_evidence(str(placed), cfg=None)
            craft_key = list(csp.placement_craft_key(craft))
            row["placement_craft"] = craft
            row["place_craft_key"] = [float(k) for k in craft_key]
        if base_key is None:
            old_key = list(row.get("place_key") or ())
            craft_len = len(csp.placement_craft_key(None))
            base_key = (old_key[:1]
                        + old_key[1 + craft_len + future_key_len:]
                        if len(old_key) > craft_len + future_key_len else old_key)
        fine_key = list(cec_route_preflight.placement_evidence_key(fine))
        row["place_key"] = [float(k) for k in (
            list(base_key)[:1] + list(craft_key) + fine_key
            + list(base_key)[1:])]
        row["future_route"] = fine
        refined += 1
    return shortlist, coarse_pruned, {
        "enabled": True,
        "shortlist_requested": int(shortlist_k),
        "shortlist_actual": len(shortlist),
        "coarse_pruned": len(coarse_pruned),
        "refined": refined,
        "failed": failed,
        "grid_mm": float(grid_mm),
        "iters": int(iters),
        "wall_s": round(time.monotonic() - started, 3),
    }


def _grade_variant(board, W, H, iname, strat, seed, passes, opt, work_root, proposal=None,
                   polish=False, placed_row=None, coord_nets=None):
    """Grade ONE (intent, strat, seed) variant. Module-level + name-keyed intent lookup so
    it pickles into a spawn worker (intents are closures; spawn is REQUIRED -- pcbnew/wx is
    not fork-safe, the cec_fr.generate_batch precedent).

    polish=True (the winner-polish stage, 2026-07-23): the effort args are taken
    VERBATIM (wave_passes/wave_opt board params normally override them -- a polish
    at 16/20 must not be silently clamped back to the wave's 8/10), the FR timeout
    doubles, and the label gets a -polish suffix so its work files never clobber
    the original grade."""
    label = f"{iname}-{strat}-s{seed}" + ("-polish" if polish else "")
    t0 = time.monotonic()
    # The wave is the consumer that WANTS the fork's real seed-diversity axis
    # (R-01); everything else stays stock-order unless it opts in (see cec_fr
    # run_freerouting CEC_FR_SEED_AXIS note, 2026-07-14). RESTORED after the
    # grade (codex stack-audit 2026-07-19 #24: the unrestored process-global
    # leaked the wave-only axis + plateau-kill into any later same-process
    # route, e.g. a golden run).
    _env_prev = {k: os.environ.get(k) for k in ("CEC_FR_SEED_AXIS",
                                                "CEC_FR_PLATEAU_KILL",
                                                "CEC_FR_PLATEAU_FLOOR",
                                                "CEC_FR_PLATEAU_GRACES")}
    os.environ["CEC_FR_SEED_AXIS"] = "1"
    # Plateau-kill (external stage-0 pre-kill on the cec2 CEC_PASS telemetry): a
    # candidate whose failed-count sits flat for 4 passes is a loser -- kill the
    # JVM, grade it failed, spend the wall-clock on live candidates instead.
    os.environ.setdefault("CEC_FR_PLATEAU_KILL", "4")
    reuse_placed = bool(placed_row and placed_row.get("placed")
                        and os.path.isfile(str(placed_row.get("placed"))))
    if reuse_placed:
        _p = copy.deepcopy(placed_row.get("cfg_params") or
                           _placement_params(board, W, H))
        s = None
    else:
        s, _p = _build_session(board, W, H, iname, strat, seed, proposal)
    if _p.get("lastmile_final_winner"):
        _p["lastmile_final"] = bool(polish)
    # PLATEAU FLOOR (probe 2026-07-23: a togo-34 hub "plateau" recovered to
    # unconn 7 with the kill off -- the flat streak fires on FR's normal
    # terminal-grind/rip-up phases, discarding boards in the winner band). A
    # plateau at togo <= floor finishes and grades; above it the kill stands
    # (true collapses sit flat at 190+). Per-board: hub winners live at 7-36,
    # 24-pin winners 146-158 vs collapse 190-230 -> wave_plateau_floor.
    os.environ.setdefault("CEC_FR_PLATEAU_FLOOR",
                          str(int(_p.get("wave_plateau_floor", 100))))
    os.environ.setdefault("CEC_FR_PLATEAU_GRACES",
                          str(int(_p.get("wave_plateau_graces", 1))))
    out = (str(placed_row["placed"]) if reuse_placed else
           os.path.join(work_root, board, f"{label}.kicad_pcb"))
    if reuse_placed:
        resume_state = _pourfirst_resume_state_status(_p)
        if not resume_state.get("ok"):
            for _ek, _ev in _env_prev.items():
                if _ev is None:
                    os.environ.pop(_ek, None)
                else:
                    os.environ[_ek] = _ev
            return {
                "label": label, "placed": out, "placement_reused": True,
                "gate": False, "gates_pass": False,
                "routing_complete": False, "routed": None,
                "failure_stage": "pourfirst_resume_state",
                "error": ("resumed routing refused: %s" %
                          resume_state.get("reason")),
                "pourfirst_resume_state": resume_state,
                "wall_s": round(time.monotonic() - t0, 1),
            }
    grade_kw = dict(
        passes=(int(passes) if polish
                else int(_p.get("wave_passes", passes))),
        opt=(int(opt) if polish else int(_p.get("wave_opt", opt))),
        fr_timeout=(2 * int(_p.get("wave_fr_timeout", 900)) if polish
                    else int(_p.get("wave_fr_timeout", 900))),
        seed=seed, unconn_finish_tol=0, thermal="lazy",
        precision=bool(_p.get("wave_precision", True)),
        # The route pipeline reserves complete decoupler cells before any
        # signal tier.  Let that mandatory, fail-closed stage own local
        # dogbones and via-in-pad ground returns; placement admission still
        # blocks missing/distant capacitors and every nonlocal defect.
        allow_route_access_repair=bool(
            _p.get("pre_route_decoupler_repair", True)))
    if reuse_placed:
        cfg = csp.Config.load(board, params=_p)
        route_input = out
        protect_nets = ()
        coordination = None
        if coord_nets:
            try:
                import shutil
                import cec_coord_hints
                coordinated = os.path.join(
                    work_root, board, f"{label}-coordinated.kicad_pcb")
                coordination = cec_coord_hints.stub_board(
                    out, coordinated, k=min(8, len(set(coord_nets))),
                    iters=8, grid_mm=0.75, backend="auto",
                    preferred_nets=set(coord_nets))
                protect_nets = tuple(coordination.get("nets") or ())
                if protect_nets:
                    for ext in (".kicad_pro", ".kicad_dru"):
                        source = out[:-len(".kicad_pcb")] + ext
                        if os.path.isfile(source):
                            shutil.copy(
                                source,
                                coordinated[:-len(".kicad_pcb")] + ext)
                    route_input = coordinated
            except Exception as exc:                       # noqa: BLE001
                coordination = {"error": "%s: %s" %
                                (type(exc).__name__, exc), "nets": []}
        with csp._oracle_env(_p):
            v = csp.route_oracle_grade(
                route_input, cfg=cfg, route=True, keep=True,
                protect_nets=protect_nets, **grade_kw)
        v["intent_log"] = list(placed_row.get("intent_log") or ())
        v["placement_reused"] = True
        v["future_route"] = copy.deepcopy(
            placed_row.get("future_route"))
        v["route_repair"] = copy.deepcopy(
            placed_row.get("route_repair"))
        v["placement_craft"] = copy.deepcopy(
            placed_row.get("placement_craft"))
        v["place_craft_key"] = copy.deepcopy(
            placed_row.get("place_craft_key"))
        v["craft_repair"] = copy.deepcopy(
            placed_row.get("craft_repair"))
        if coordination is not None:
            v["coordination"] = {
                "nets": list(protect_nets),
                "negotiation": coordination.get("negotiation"),
                "compiled": coordination.get("compiled"),
                "error": coordination.get("error"),
            }
    else:
        v = s.grade(out=out, keep=True, **grade_kw)
        v["placement_reused"] = False
    _inc = (v.get("incursion") or {})
    if _inc and (_inc.get("n_parts", 0) or _inc.get("n_tracks", 0) or _inc.get("n_vias", 0)):
        print(f"[wave] {board} {label}: POUR INCURSION parts={_inc.get('n_parts')} "
              f"tracks={_inc.get('n_tracks')} vias={_inc.get('n_vias')} "
              f"(owner rule: nothing places inside a pour)", flush=True)
    v["label"] = label
    v["placed"] = out
    v["wall_s"] = round(time.monotonic() - t0, 1)
    # POUR-FIRST per-net report rides the verdict into the wave log/report
    # (path_found / segments / bridges / layers / bottleneck per net)
    _pfr = ((placed_row or {}).get("pourfirst") if reuse_placed else
            getattr(s, "pourfirst_report", None))
    if _pfr is not None:
        v["pourfirst"] = _pfr
        print(f"[wave] {board} {label}: pour-first paths "
              f"{len(_pfr.get('path_found', ()))}/{len(_pfr.get('nets', {}))} "
              f"no-path={_pfr.get('no_path') or 'none'} "
              f"artifact={os.path.basename(str(_pfr.get('artifact') or ''))} "
              + (f"ERR={_pfr.get('error')}" if _pfr.get("error") else ""),
              flush=True)
    for _ek, _ev in _env_prev.items():          # restore (audit #24)
        if _ev is None:
            os.environ.pop(_ek, None)
        else:
            os.environ[_ek] = _ev
    return v


def _prev_best_key(pub_dir):
    """Sort_key of the board's INCUMBENT best: the latest previously-published
    wave-report in *pub_dir* (chained waves share out_root). None = no incumbent."""
    try:
        reports = sorted(glob.glob(os.path.join(pub_dir, "*-wave-report.json")))
        if not reports:
            return None
        with open(reports[-1]) as fh:
            k = ((json.load(fh).get("best") or {}).get("sort_key"))
        return tuple(k) if k else None
    except Exception:                                   # noqa: BLE001 -- fail-safe
        return None


CANDIDATE_DIR = "candidate"
CANDIDATE_META = "candidate.json"
_CANDIDATE_README = """# `candidate/`: the current best diagnostic board for this module

ONE board file, kept current by the wave (owner directive 2026-07-25: "the current
best should be placed into a candidate folder per board and kept current with only
one board ideally so we have a reference").

`<board>-candidate.kicad_pcb` (+ its `.kicad_pro` / `.kicad_dru` sidecars) is a COPY
of the best board the wave has ever published for this module, with `candidate.json`
recording where it came from and how it graded. Open it to see the real current
state of the layout without digging through `build/fresh-wave-*/`.

IMPORTANT: `candidate/` is a diagnostic-reference channel, not a release-acceptance
channel. A routed board remains here when its route gate fails so reviewers can see
and improve the best failure. `candidate.json` therefore records
`candidate_role: diagnostic-reference`, `release_accepted: false`, and the distinct
`route_gate_passed` result. Only the aggregate release pipeline may accept a board.

RULES the wave enforces on every publish:
  * SCHEMATIC FRESHNESS outranks score: a winner matching more of the CURRENT
    component signatures replaces the reference even on a worse score, and a
    staler board never replaces a fresher one. The signature covers value,
    footprint, and numbered-pad nets. `schematic_match` and `schematic_exact` in
    `candidate.json` record the result. A board that grades well but predates a
    schematic or footprint change is the worse reference;
  * otherwise it replaces this file only when the new winner BEATS the recorded
    `sort_key` (lower is better -- the same ranking the wave itself uses);
  * a board satisfying the CURRENT segmented-mezzanine geometry replaces one
    that violates it, independent of route score; an obsolete mechanical datum
    is stale in the same way an obsolete component signature is stale;
  * a routed winner always beats a placement-only one, and a placement-only winner
    NEVER overwrites a routed reference;
  * exactly one `.kicad_pcb` lives here -- stale board files are pruned.

`candidate.json` is also refreshable without publishing a board. Consumers that
use a candidate as a placement oracle or materialization template MUST require
`schematic_exact: true` after a current refresh. A stale candidate remains useful
for historical outline, connector, mount, and copper review, but it is not a
component-inventory or pin/net authority.

This is a REFERENCE, not the board of record: it is machine-written, so never hand-edit
it (edits are silently overwritten by the next better wave). The authoritative
schematic + the module's own project files stay in the parent directory.
"""


def _board_refs(pcb_path):
    """Physical component signatures of a board, or None if unreadable.

    Freshness cannot be a reference-only comparison. A board with all the same
    references can still be electrically stale after a footprint or pin-to-net
    change. Each signature therefore includes value, footprint library item,
    and the deduplicated numbered-pad net map.
    """
    try:
        import pcbnew
    except ImportError:                                    # host-side tests
        return None
    try:
        b = pcbnew.LoadBoard(str(pcb_path))
        signatures = {}
        for fp in b.GetFootprints():
            ref = str(fp.GetReference())
            footprint = str(fp.GetFPID().GetLibItemName())
            pins = {
                (str(pad.GetNumber()), str(pad.GetNetname()))
                for pad in fp.Pads()
                if (str(pad.GetNumber()) and str(pad.GetNetname()) and
                    not str(pad.GetNetname()).startswith("unconnected-"))
            }
            signatures[ref] = (
                str(fp.GetValue()),
                footprint,
                tuple(sorted(pins)),
            )
        return signatures
    except Exception:                                      # noqa: BLE001
        return None


def _netlist_refs(board):
    """Component signatures the CURRENT schematic expects, or None.

    Goes through `_ensure_netlist_path`, NOT `cfg.net` directly: most boards
    carry no committed .net file, so the direct read returned None for every
    board and silently reduced the freshness rule to a no-op (measured -- every
    board reported `schematic=0%`). `_ensure_netlist_path` exports it once from
    the schematic, which is what makes "current" mean current.
    """
    try:
        cfg = csp.Config.load(board)
        net = ""
        try:
            net = csp._ensure_netlist_path(cfg) or ""
        except Exception:                                  # noqa: BLE001
            net = getattr(cfg, "net", "") or ""
        if not (net and os.path.isfile(net)):
            return None
        parsed = csp.Netlist.from_file(net)
        # Only physical schematic components belong in a PCB freshness
        # denominator.  Legacy generated power symbols can carry ordinary
        # PWR201-style references in a netlist even though they have no
        # footprint and must never appear on the board.
        physical = {
            ref: comp for ref, comp in parsed.comps.items()
            if str(comp.footprint or "").strip()
        }
        pins_by_ref = {ref: set() for ref in physical}
        for net_name, nodes in parsed.nets.items():
            if not net_name or str(net_name).startswith("unconnected-"):
                continue
            for ref, pin in nodes:
                if ref in pins_by_ref and pin:
                    pins_by_ref[ref].add((str(pin), str(net_name)))
        signatures = {
            ref: (
                str(comp.value),
                str(comp.footprint).rsplit(":", 1)[-1],
                tuple(sorted(pins_by_ref[ref])),
            )
            for ref, comp in physical.items()
        }
        return signatures or None
    except Exception:                                      # noqa: BLE001
        return None


def _schematic_match(pcb_path, want_refs):
    """How much of the current schematic this board exactly carries (0..1).

    The reason this is a RULE and not a nicety: "best by sort_key" can be a board
    that predates a schematic change. Measured 2026-07-25 -- the 12VHPWR winner
    with the best score was routed 07-19, before the USB-ingress parts landed in
    the schematic, so a purely score-ranked reference would show a board missing
    U5/F1 entirely while claiming to be current. A reference that is numerically
    better but electrically out of date is the worse reference.
    """
    if not want_refs:
        return None
    have = _board_refs(pcb_path)
    if have is None:
        return None
    # Tests and host fallbacks may still supply simple reference sets. Keep
    # that compatibility path explicit, but live pcbnew/netlist reads return
    # dictionaries and require exact component signatures.
    if isinstance(want_refs, set) and isinstance(have, set):
        return len(want_refs & have) / float(len(want_refs))
    if not isinstance(want_refs, dict) or not isinstance(have, dict):
        return None
    matches = sum(
        ref in have and have[ref] == signature
        for ref, signature in want_refs.items()
    )
    return matches / float(len(want_refs))


def _mezz_contract_status(pcb_path):
    """True/False for a Hub/ATX segmented-mezz candidate, else None.

    Candidate freshness used to cover only electrical inventory. That allowed
    a mechanically obsolete stack seat to remain incumbent unless a new route
    also happened to beat its score. Treat the shared physical datum as another
    freshness axis; unrelated boards remain unaffected.
    """
    norm = os.path.normpath(str(pcb_path or "")).lower()
    if not any(name in norm for name in ("atx-24pin-rev3", "hub-standard-rev2")):
        return None
    try:
        import pcbnew
        import cec_constraints
        pcb = pcbnew.LoadBoard(str(pcb_path))
        ok, _detail = cec_constraints._chk_mezzanine_segment_contract(
            pcb, str(pcb_path), {})
        return bool(ok) if ok is not None else None
    except Exception:                                  # noqa: BLE001 -- fail closed
        return False


def refresh_candidate_metadata(board):
    """Recompute a committed candidate's freshness against TODAY's schematic.

    Candidate metadata used to be stamped only when a wave published. A later
    schematic edit could therefore leave `schematic_exact: true` in JSON even
    though the PCB no longer carried the current component signatures. Refresh
    is deliberately metadata-only: it never edits or replaces the PCB.
    """
    board_dir = os.path.join(ROOT, "beta", board)
    cdir = os.path.join(board_dir, CANDIDATE_DIR)
    pcb_path = os.path.join(cdir, f"{board}-candidate.kicad_pcb")
    meta_path = os.path.join(cdir, CANDIDATE_META)
    if not (os.path.isfile(pcb_path) and os.path.isfile(meta_path)):
        return None
    try:
        with open(meta_path) as fh:
            meta = json.load(fh) or {}
    except Exception:                                    # noqa: BLE001
        meta = {}
    want = _netlist_refs(board)
    match = _schematic_match(pcb_path, want)
    exact = match is not None and abs(match - 1.0) <= 1e-9
    meta.update({
        "candidate_role": "diagnostic-reference",
        "release_accepted": False,
        "route_gate_passed": bool((meta.get("grade") or {}).get("gate")),
        "schematic_match": (round(match, 4) if match is not None else None),
        "schematic_exact": exact,
        "schematic_parts": (len(want) if want else None),
        "schematic_status": ("exact" if exact else
                             "stale" if match is not None else "unknown"),
        "freshness_checked": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mezzanine_contract_ok": _mezz_contract_status(pcb_path),
    })
    # Refresh the numbers from the PCB reviewers actually open. This is still
    # metadata-only: candidate copper is never edited here. Older metadata may
    # predate post-publish hygiene rescoring, so incomplete legacy gate evidence
    # stays fail-closed.
    if meta.get("routed"):
        grade = dict(meta.get("grade") or {})
        probe = {
            **grade,
            "sort_key": meta.get("sort_key"),
            "foreign": grade.get("foreign") or {},
            "thermal": meta.get("thermal") or {},
            "rails": grade.get("rails") or {},
            "gate_terms": meta.get("gate_terms") or {},
            "reasons": [],
        }
        try:
            _rescore_published(probe, pcb_path)
            grade.update({k: probe.get(k) for k in
                          ("gate", "kelvin_ok", "diffpair_ok", "drc", "drc_types",
                           "unconnected", "unconn_critical", "foreign", "thermal_ok",
                           "rails")})
            meta["grade"] = grade
            meta["sort_key"] = list(
                probe.get("sort_key") or meta.get("sort_key") or [])
            meta["route_gate_passed"] = bool(probe.get("gate"))
            meta["live_score_checked"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            meta.pop("live_score_error", None)
        except Exception as exc:                           # noqa: BLE001 -- fail closed
            meta["route_gate_passed"] = False
            meta["live_score_error"] = f"{type(exc).__name__}: {exc}"
    tmp_path = meta_path + ".tmp"
    with open(tmp_path, "w") as fh:
        json.dump(meta, fh, indent=1, sort_keys=True, default=str)
        fh.write("\n")
    os.replace(tmp_path, meta_path)
    with open(os.path.join(cdir, "README.md"), "w") as fh:
        fh.write(_CANDIDATE_README)
    print(f"[candidate] {board}: freshness={meta['schematic_status']} "
          f"match={meta['schematic_match']}", flush=True)
    return meta


def _candidate_update(board, published_pcb, best, *, out_root=None):
    """Keep `beta/<board>/candidate/` pointing at the CURRENT BEST board.

    Called at the publish site with the already-hygiene-cleaned artifact, so the
    reference carries exactly what the owner would review. Fail-safe by
    construction: any problem here prints and returns, never breaks a wave.
    """
    try:
        board_dir = os.path.join(ROOT, "beta", board)
        if not os.path.isdir(board_dir):
            return None                        # never invent a board directory
        if not (published_pcb and os.path.isfile(str(published_pcb))):
            return None
        cdir = os.path.join(board_dir, CANDIDATE_DIR)
        os.makedirs(cdir, exist_ok=True)
        meta_path = os.path.join(cdir, CANDIDATE_META)
        dst_pcb = os.path.join(cdir, f"{board}-candidate.kicad_pcb")

        routed_now = bool(best.get("routed") and os.path.isfile(str(best.get("routed"))))
        key_now = tuple(best.get("sort_key") or (9,))
        prev = {}
        if os.path.isfile(meta_path):
            try:
                with open(meta_path) as fh:
                    prev = json.load(fh) or {}
            except Exception:                              # noqa: BLE001
                prev = {}
        have = os.path.isfile(dst_pcb)
        prev_routed = bool(prev.get("routed"))
        prev_key = tuple(prev.get("sort_key") or (9,))

        # SCHEMATIC FRESHNESS outranks score (see _schematic_match): a reference
        # that is missing parts the schematic now has is stale no matter how well
        # it graded. Both sides are measured against TODAY's netlist, so this
        # compares like with like; when the netlist or pcbnew is unavailable the
        # term drops out entirely and the score rules stand unchanged.
        want = _netlist_refs(board)
        fresh_now = _schematic_match(published_pcb, want)
        fresh_prev = _schematic_match(dst_pcb, want) if os.path.isfile(dst_pcb) else None
        mech_now = _mezz_contract_status(published_pcb)
        mech_prev = _mezz_contract_status(dst_pcb) if os.path.isfile(dst_pcb) else None
        fresher = staler = False
        if fresh_now is not None and fresh_prev is not None:
            fresher = fresh_now > fresh_prev + 1e-9
            staler = fresh_now < fresh_prev - 1e-9

        if not have:
            why = "first candidate"
        elif fresher:
            why = (f"matches more of the current schematic "
                   f"({fresh_now:.0%} vs {fresh_prev:.0%} of {len(want)} parts)")
        elif staler:
            print(f"[wave] {board} candidate: kept (this winner carries only "
                  f"{fresh_now:.0%} of the current schematic vs the reference's "
                  f"{fresh_prev:.0%} -- a staler board never replaces a fresher one)",
                  flush=True)
            return None
        elif mech_now is True and mech_prev is False:
            why = "matches the current segmented-mezzanine mechanical datum"
        elif mech_now is False and mech_prev is True:
            print(f"[wave] {board} candidate: kept (winner violates the current "
                  f"segmented-mezzanine mechanical datum)", flush=True)
            return None
        elif routed_now and not prev_routed:
            why = "routed beats placement-only"
        elif prev_routed and not routed_now:
            # A placement-only winner must never clobber real copper.
            print(f"[wave] {board} candidate: kept (routed reference beats a "
                  f"placement-only winner)", flush=True)
            return None
        elif key_now < prev_key:
            why = f"sort_key {list(key_now)} < {list(prev_key)}"
        else:
            print(f"[wave] {board} candidate: kept (incumbent {list(prev_key)} "
                  f"<= this wave's {list(key_now)})", flush=True)
            return None

        import shutil
        shutil.copy(str(published_pcb), dst_pcb)
        src_base = str(published_pcb)[:-len(".kicad_pcb")]
        for ext in (".kicad_pro", ".kicad_dru"):
            if os.path.isfile(src_base + ext):
                shutil.copy(src_base + ext, dst_pcb[:-len(".kicad_pcb")] + ext)
        # ONE board file (owner: "only one board ideally"): drop anything stale.
        for stale in glob.glob(os.path.join(cdir, "*.kicad_pcb")):
            if os.path.abspath(stale) != os.path.abspath(dst_pcb):
                os.remove(stale)
        readme = os.path.join(cdir, "README.md")
        with open(readme, "w") as fh:
            fh.write(_CANDIDATE_README)
        meta = {
            "schema": 1,
            "board": board,
            "candidate_role": "diagnostic-reference",
            "release_accepted": False,
            "route_gate_passed": bool(best.get("gate")),
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "reason": why,
            "routed": routed_now,
            "source": os.path.relpath(str(published_pcb), ROOT),
            "wave_out_root": (os.path.relpath(str(out_root), ROOT) if out_root else None),
            "label": best.get("label"),
            "sort_key": list(key_now),
            "schematic_match": (round(fresh_now, 4) if fresh_now is not None else None),
            "schematic_exact": (fresh_now is not None and
                                abs(fresh_now - 1.0) <= 1e-9),
            "schematic_status": ("exact" if fresh_now is not None and
                                 abs(fresh_now - 1.0) <= 1e-9 else
                                 "stale" if fresh_now is not None else "unknown"),
            "freshness_checked": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "schematic_parts": (len(want) if want else None),
            "mezzanine_contract_ok": mech_now,
            "grade": {k: best.get(k) for k in
                      ("gate", "kelvin_ok", "diffpair_ok", "drc", "unconnected",
                       "unconn_critical", "drc_types", "foreign", "thermal_ok",
                       "rails")},
            "thermal": best.get("thermal"),
        }
        try:                                               # provenance, best-effort
            meta["commit"] = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=False,
                capture_output=True, text=True).stdout.strip() or None
        except Exception:                                  # noqa: BLE001
            meta["commit"] = None
        with open(meta_path, "w") as fh:
            json.dump(meta, fh, indent=1, sort_keys=True, default=str)
        print(f"[wave] {board} candidate: UPDATED ({why}) -> "
              f"{os.path.relpath(dst_pcb, ROOT)}", flush=True)
        return dst_pcb
    except Exception as e:                                 # noqa: BLE001 -- fail-safe
        print(f"[wave] {board} candidate update skipped ({type(e).__name__}: {e})",
              flush=True)
        return None


def _rescore_published(best, published_pcb):
    """Re-score the exact saved artifact after every publish-time copper repair.

    The route oracle originally graded the work-board, then publish hygiene and
    fab repair mutated a copy before it reached ``candidate/``.  A connectivity
    repair is supposed to be topology-preserving, but accepting that promise as
    evidence allowed candidate.json to disagree with the board a reviewer opened.
    This pass makes the saved PCB authoritative: DRC, ratlines, pair gates, and
    the failure-tier sort key are rebuilt from one fresh score.  Non-copper oracle
    terms (placement, pours, thermal, etc.) remain the values already adjudicated;
    if their complete gate-term record is absent the aggregate gate fails closed.
    """
    if not (published_pcb and os.path.isfile(str(published_pcb))):
        return best
    before = {k: best.get(k) for k in
              ("gate", "kelvin_ok", "diffpair_ok", "drc", "unconnected")}
    rules = cec_score.Rules.from_board(str(published_pcb))
    metrics = cec_score.score(str(published_pcb), rules)
    unconn_nets = sorted(metrics.detail.get("unconn_nets") or [])
    crit, sig = csp._classify_unconnected(unconn_nets, rules)
    best.update({
        "routed": str(published_pcb),
        "gates_pass": bool(metrics.gates_pass),
        "kelvin_ok": bool(metrics.kelvin_ok),
        "diffpair_ok": bool(metrics.diffpair_ok),
        "drc": int(metrics.drc),
        "drc_clean": metrics.drc == 0,
        "drc_finishing_only": metrics.drc == 0,
        "drc_types": dict(metrics.drc_types),
        "unconnected": int(metrics.unconnected),
        "unconn_nets": unconn_nets,
        "unconn_critical": crit,
        "unconn_signal": sig,
        "routing_complete": metrics.unconnected == 0,
        "vias": int(metrics.vias),
        "tracks": int(metrics.tracks),
        "length": round(float(metrics.length), 2),
        "route_quality": dict(metrics.detail.get("route_quality") or {}),
    })

    gate_terms = dict(best.get("gate_terms") or {})
    if gate_terms:
        gate_terms["gates_pass"] = bool(metrics.gates_pass)
        gate_terms["routing_complete"] = metrics.unconnected == 0
        best["gate_terms"] = gate_terms
        try:
            best["gate"] = bool(csp._route_oracle_accepts(gate_terms))
        except ValueError:
            # A partial/legacy verdict cannot prove the complete conjunction.
            best["gate"] = False
    else:
        best["gate"] = False

    rails = best.get("rails") or {}
    rails_refused = max(0, int(rails.get("total", 0)) - int(rails.get("laid", 0)))
    safety_fails = ((0 if metrics.kelvin_ok else 1)
                    + (0 if metrics.diffpair_ok else 1) + rails_refused)
    foreign = best.get("foreign") or {}
    foreign_total = int(foreign.get("tracks", 0)) + int(foreign.get("vias", 0))
    thermal = best.get("thermal") or {}
    dT = thermal.get("dT")
    dT = float(dT) if dT is not None else 1e6
    if best["gate"]:
        silk = best.get("silk_score") or {}
        silk_key = silk.get("score_per_fp")
        silk_key = float(silk_key) if silk_key is not None else 99.0
        best["sort_key"] = (0, round(dT, 1), metrics.vias,
                            round(silk_key, 1), round(metrics.length, 1), 0)
    else:
        best["sort_key"] = (1, safety_fails, len(crit), foreign_total,
                            metrics.unconnected, metrics.drc, round(dT, 1))

    after = {k: best.get(k) for k in before}
    if before != after:
        note = ("published-artifact rescore after hygiene: "
                f"gate {before['gate']}->{after['gate']}, "
                f"kelvin {before['kelvin_ok']}->{after['kelvin_ok']}, "
                f"diff {before['diffpair_ok']}->{after['diffpair_ok']}, "
                f"DRC {before['drc']}->{after['drc']}, "
                f"unconnected {before['unconnected']}->{after['unconnected']}")
        best.setdefault("reasons", []).append(note)
        print(f"[wave] {note}", flush=True)
    return best


def _new_best_thermal(best, pub_dir, board_params, *, solve=None, env=None):
    """NEW-BEST THERMAL (owner design call 2026-07-17: 'thermal fires on every wave
    that produces a new best'). The per-candidate lazy skip stands (the solve costs
    5-17s GPU / ~97s CPU-AMG, measured -- too much x N variants), but no fresh
    candidate reaches gate-clean today, so the lazy path never fired and every
    published best carried dT=None (the roadmap's silent-skip finding). This stamp
    closes that: a wave whose winner BEATS the board's incumbent (or has none)
    runs the SAME fail-closed, mirage-guarded, double-solve-confirmed oracle term
    the gate uses (_oracle_thermal, route_oracle_grade's default 50C/30C/0.4mm),
    under the same recipe env, on the PUBLISHED routed board. A thermal FAIL
    publishes LOUD in the verdict/report/print -- never silently dropped; the
    sort_key is NOT retroactively rewritten (grading already happened; this is
    the publish-time evidence behind the claim). Returns the new-best flag."""
    prev = _prev_best_key(pub_dir)
    new_best = prev is None or tuple(best.get("sort_key") or (9,)) < prev
    th = best.get("thermal") or {}
    routed = best.get("routed")
    if not new_best or th.get("dT") is not None:
        return new_best
    if not (routed and os.path.isfile(str(routed))):
        best["thermal"] = {"ok": False, "dT": None, "max_T": None,
                           "note": "new best has no routed board -- thermal not solvable"}
        return new_best
    # COARSE-ON-CPU knob (owner ask 2026-07-18): CEC_WAVE_THERMAL_GRID_MM coarsens the
    # wave stamp's grid (0.4 = the gate default; 0.8 ~= 4x fewer cells, which also lands
    # the solve under the GPU auto-engage floor -> fast CPU-AMG); pair with
    # CEC_THERMAL_BACKEND=cpu to pin the backend. PROVENANCE: grid_mm + backend are
    # stamped into the result so a coarse CPU number is never read as the 0.4 mm gate
    # figure (a coarse grid under-resolves thin necks -> optimistic dT; the mirage
    # guard + double-solve confirm still apply, but gate-grade thermal stays 0.4).
    grid_mm = float(os.environ.get("CEC_WAVE_THERMAL_GRID_MM", "0.4"))
    solve = solve or (lambda p: csp._oracle_thermal(p, ambient=50.0, gate_dt=30.0,
                                                    grid_mm=grid_mm))
    env = env or csp._oracle_env
    try:
        with env(board_params):
            therm = solve(str(routed))
    except Exception as e:                              # noqa: BLE001 -- FAIL-CLOSED
        therm = {"ok": False, "dT": None, "max_T": None, "gate_dt": 30.0,
                 "error": "%s: %s" % (type(e).__name__, e)}
    if isinstance(therm, dict):
        therm.setdefault("grid_mm", grid_mm)
        _be = os.environ.get("CEC_THERMAL_BACKEND", "").strip().lower()
        therm.setdefault("backend", _be or "auto")
        if grid_mm > 0.4:
            therm.setdefault("provenance", "coarse (%.1fmm > 0.4mm gate grid)" % grid_mm)
    best["thermal"] = therm
    best["thermal_ok"] = bool(therm.get("ok"))
    return new_best


def _wave_workers():
    """Candidate-level parallelism (profiling 2026-07-08: the wave was FULLY SERIAL while
    FR -- 71-95% of each candidate -- is single-threaded). The routing container has ALL
    18 host cores (`nproc` reads 4 only because OMP_NUM_THREADS=4 masks it -- measured;
    the OMP cap usefully bounds each worker's BLAS instead). Default: 6 workers, leaving
    headroom for the orchestrator/renders + the GPU thermal confirms. CEC_WAVE_WORKERS=1
    restores the serial wave (wave-to-wave comparability runs)."""
    try:
        return max(1, int(os.environ.get("CEC_WAVE_WORKERS", 0))) \
            if os.environ.get("CEC_WAVE_WORKERS") else max(1, min(6, (os.cpu_count() or 4) - 2))
    except ValueError:
        return 1


def _polish_decision(best, board_params, wave_passes, wave_opt):
    """Return ``(run, reason)`` for the serial winner-polish route.

    A polish is useful only when it adds effort to a close, routed candidate.
    Re-running 16/20 after every candidate already received 40/60 consumed
    13--22 serial minutes per Hub wave and repeatedly worsened connectivity.
    """
    if not board_params.get("wave_polish", True):
        return False, "disabled by board policy"
    unconnected = best.get("unconnected")
    if unconnected is None or best.get("error"):
        return False, "winner has no successful route verdict"
    if int(unconnected) == 0:
        return False, "winner is already connected"
    limit = int(board_params.get("polish_unconnected_max", 40))
    if int(unconnected) > limit:
        return False, "winner is not within the polish band (%d > %d)" % (
            int(unconnected), limit)
    regular_passes = int(board_params.get("wave_passes", wave_passes))
    regular_opt = int(board_params.get("wave_opt", wave_opt))
    polish_passes = int(board_params.get("polish_passes", 16))
    polish_opt = int(board_params.get("polish_opt", 20))
    if polish_passes <= regular_passes and polish_opt <= regular_opt:
        return False, ("polish adds no effort (%d/%d after %d/%d)" %
                       (polish_passes, polish_opt, regular_passes, regular_opt))
    return True, "adds effort to a close routed winner"


def _coord_polish_enabled(board_params):
    """Whether a deep wave may bind negotiated corridors as protected stubs.

    The 2026-08-05 Hub control compiled seven legal stubs but regressed the
    selected placement from 25/8 (unconnected/DRC) to 31/14 at higher effort.
    Congestion analysis remains active; hard copper constraints stay opt-in
    until a pinned, same-effort A/B proves them for a board.  The environment
    override is intended for precisely those experiments.
    """
    env = os.environ.get("CEC_WAVE_COORD_POLISH")
    if env is not None:
        return env == "1"
    return bool(board_params.get("wave_coord_polish", False))


def run_board(board, seeds, passes, opt, out_root, work_root):
    if board not in cec_beta_manifest.WAVE_BOARDS:
        raise ValueError(
            f"{board!r} is not a current manifest-declared BETA wave board; "
            f"choose one of {', '.join(cec_beta_manifest.WAVE_BOARDS)}"
        )
    W, H = BOARD_WH.get(board, (100.0, 44.0))
    if os.environ.get("CEC_BOARD_W"):
        W = float(os.environ["CEC_BOARD_W"])                # A/B knob (owner 2026-07-12)
    if os.environ.get("CEC_BOARD_H"):
        H = float(os.environ["CEC_BOARD_H"])
    workers = _wave_workers()
    # One CUDA owner is inherited by every spawned placement/grade worker via
    # CEC_COORD_SERVICE_SOCKET.  Coarse problems remain local CPU work; only
    # route-awareness tensors above the measured crossover enter this serial
    # queue.  Startup is fail-open because CUDA is an accelerator, never a
    # correctness dependency.
    route_service = None
    try:
        import cec_route_awareness_service
        route_service = cec_route_awareness_service.ensure_service()
        if route_service.get("enabled"):
            print("[wave] route-awareness CUDA owner: pid=%s prewarm=%ss "
                  "cache=%sMiB" % (
                      route_service.get("pid"),
                      route_service.get("prewarm_s"),
                      round(float(route_service.get(
                          "cache_limit_bytes", 0)) / (1024 * 1024), 1)),
                  flush=True)
    except Exception as exc:                              # noqa: BLE001
        os.environ.pop("CEC_COORD_SERVICE_SOCKET", None)
        route_service = {
            "enabled": False,
            "error": "%s: %s" % (type(exc).__name__, exc),
        }
        print("[wave] route-awareness CUDA owner unavailable; deterministic "
              "local backend remains active (%s)" % route_service["error"],
              flush=True)
    _wlog(f"wave started: {board}", tag="wave",
          detail=f"{len(_intents_for(board))} intents x 2 strats x {len(seeds)} seeds at {W}x{H}mm, "
                 f"passes {passes}/opt {opt}, workers {workers}")
    os.makedirs(os.path.join(work_root, board), exist_ok=True)
    results = []
    _bp = _board_params(board)      # carries thermal_board_hint (set in _board_params)
    variants = [(iname, strat, seed, None) for iname, _fn in _intents_for(board)
                for strat in ("dataflow", "compact") for seed in seeds]
    # SEAT PROPOSALS (owner GO 2026-07-08): validated intents from the previous wave's
    # verdicts join the grid BESIDE the hand intents (steer, never gate; labels carry
    # prop- provenance). CEC_WAVE_INTENTS=0 kills both consumption and generation.
    if os.environ.get("CEC_WAVE_INTENTS", "1") != "0":
        try:
            import cec_wave_intents
            for p in cec_wave_intents.load(out_root, board):
                variants += [(f"prop-{p['name']}", strat, seed, p)
                             for strat in ("dataflow", "compact") for seed in seeds]
        except Exception as e:                              # noqa: BLE001 -- fail-safe
            print(f"[wave] {board}: proposals unavailable ({e})", flush=True)

    # PRUNE -> ADJUDICATE (roadmap throughput lever 1, owner GO 2026-07-17): compile
    # ALL variants' placements cheaply first (seconds each), FR-route only the top-K
    # by the production cheap key (csp._candidate_sort_key -- the same ranking
    # place_candidates/adjudicate_candidates already use). The FR route is 71-95% of
    # candidate cost (roadmap profile), so K=4 on the recent 16-32-variant grids is
    # the ~8x saving. Fidelity cost is managed, not hidden: pruned variants are
    # RECORDED in the wave report with their placement keys (no silent caps), a
    # placement-phase ERROR routes anyway (fail-open), and CEC_WAVE_PRUNE=0 restores
    # the route-everything wave byte-identically.
    pruned_rows = []
    placed_rows = []
    aware_report = None
    prune_k = int(os.environ.get("CEC_WAVE_PRUNE", "4"))
    if prune_k > 0 and len(variants) > prune_k:
        _t0p = time.monotonic()
        active_outer_workers = min(max(1, workers), len(variants))
        craft_workers = _nested_craft_worker_budget(active_outer_workers)
        if workers <= 1:
            placed_rows = [_place_variant(board, W, H, i, st, sd, prop,
                                          work_root, craft_workers)
                           for i, st, sd, prop in variants]
        else:
            import concurrent.futures as _cf
            import multiprocessing as _mp
            _ctx = _mp.get_context("spawn")                    # pcbnew is NOT fork-safe
            with _cf.ProcessPoolExecutor(max_workers=workers, mp_context=_ctx) as _pool:
                placed_rows = list(_pool.map(
                    _place_variant,
                    *zip(*[(board, W, H, i, st, sd, prop, work_root,
                            craft_workers)
                           for i, st, sd, prop in variants])))
        aware_default = int(_bp.get(
            "placement_route_aware_shortlist", 0) or 0)
        aware_k = int(os.environ.get(
            "CEC_WAVE_AWARE_SHORTLIST", str(aware_default)))
        aware_allowed = (bool((route_service or {}).get("enabled")) or
                         os.environ.get(
                             "CEC_WAVE_AWARE_WITHOUT_SERVICE", "0") == "1")
        if aware_k > prune_k and aware_allowed:
            aware_grid = float(os.environ.get(
                "CEC_WAVE_AWARE_GRID_MM",
                str(_bp.get("placement_route_aware_grid_mm", 0.5))))
            aware_iters = int(os.environ.get(
                "CEC_WAVE_AWARE_ITERS",
                str(_bp.get("placement_route_aware_iters", 3))))
            variants, coarse_pruned, aware_report = (
                _refine_route_aware_shortlist(
                    variants, placed_rows, aware_k,
                    grid_mm=aware_grid, iters=aware_iters))
            pruned_rows.extend(coarse_pruned)
            print("[wave] %s route-aware shortlist: %s/%s fine proofs at "
                  "%smm x %s iterations; %s coarse candidate(s) retired "
                  "[%ss]" % (
                      board, aware_report["refined"],
                      aware_report["shortlist_actual"], aware_grid,
                      aware_iters, aware_report["coarse_pruned"],
                      aware_report["wall_s"]), flush=True)
        variants, final_pruned = _prune_variants(
            variants, placed_rows, prune_k)
        for row in final_pruned:
            row["prune_stage"] = ("fine-route-aware-final"
                                  if aware_report else "coarse-final")
        pruned_rows.extend(final_pruned)
        for row in pruned_rows:
            placed = row.get("placed")
            if not placed:
                continue
            base = (str(placed)[:-len(".kicad_pcb")]
                    if str(placed).endswith(".kicad_pcb") else str(placed))
            for path in (str(placed), base + ".kicad_pro", base + ".kicad_dru"):
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except OSError:
                    pass
        print(f"[wave] {board} prune: routing {len(variants)}/{len(placed_rows)} "
              f"variant(s) by cheap placement key ({len(pruned_rows)} pruned, recorded "
              f"in the report; CEC_WAVE_PRUNE=0 routes all) "
              f"[{round(time.monotonic() - _t0p, 1)}s]", flush=True)

    placed_by_label = {row.get("label"): row for row in placed_rows
                       if row.get("placed") and
                       os.path.isfile(str(row.get("placed")))}

    def _placed_row(iname, strat, seed):
        return placed_by_label.get(f"{iname}-{strat}-s{seed}")

    def _consume(v):
        _was_best = (not results or
                     tuple(v.get("sort_key") or (9,)) <
                     min(tuple(r.get("sort_key") or (9,)) for r in results))
        results.append(v)
        _snapshot(board, v["label"], v, work_root, best=_was_best,
                  dual=bool(_bp.get("dual_sided")))
        print(f"[wave] {board} {v['label']}: gate={v.get('gate')} "
              f"kelvin={v.get('kelvin_ok')} unconn={v.get('unconnected')} "
              f"foreign={v.get('foreign',{}).get('tracks')}t "
              f"dT={((v.get('thermal') or {}).get('dT'))} "
              f"({v.get('wall_s')}s)"
              + (f" ERR={str(v.get('error'))[:140]}" if v.get("error") else ""),
              flush=True)

    if workers <= 1:
        for iname, strat, seed, prop in variants:
            try:
                _consume(_grade_variant(board, W, H, iname, strat, seed, passes, opt,
                                        work_root, proposal=prop,
                                        placed_row=_placed_row(iname, strat, seed)))
            except Exception as e:                              # noqa: BLE001
                print(f"[wave] {board} {iname}-{strat}-s{seed}: ERROR {type(e).__name__}: {e}",
                      flush=True)
    else:
        import concurrent.futures as cf
        import multiprocessing as mp
        ctx = mp.get_context("spawn")                          # pcbnew is NOT fork-safe
        with cf.ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
            futs = {pool.submit(_grade_variant, board, W, H, iname, strat, seed,
                                passes, opt, work_root, prop, False,
                                _placed_row(iname, strat, seed)):
                    (iname, strat, seed)
                    for iname, strat, seed, prop in variants}
            for fut in cf.as_completed(futs):
                iname, strat, seed = futs[fut]
                try:
                    _consume(fut.result())
                except Exception as e:                          # noqa: BLE001
                    print(f"[wave] {board} {iname}-{strat}-s{seed}: ERROR "
                          f"{type(e).__name__}: {e}", flush=True)
    if not results:
        return None
    results.sort(key=lambda v: tuple(v.get("sort_key") or (9,)))
    best = results[0]
    # WINNER POLISH (2026-07-23): re-grade the winning variant once at HIGH FR
    # effort before publishing -- probes at 16/20 consistently land 21-26 unconn
    # where wave-effort bests land 30+ (the s70/s120 ladder). One extra route
    # per wave, winner-only; adopted only when it actually sorts better.
    polish_info = None
    _polish, _polish_reason = _polish_decision(best, _bp, passes, opt)
    if _polish:
        _mt = [t for t in variants
               if f"{t[0]}-{t[1]}-s{t[2]}" == best.get("label")]
        if _mt:
            _pi, _ps, _pseed, _pprop = _mt[0]
            try:
                _coord_enabled = _coord_polish_enabled(_bp)
                pv = _grade_variant(board, W, H, _pi, _ps, _pseed,
                                    int(_bp.get("polish_passes", 16)),
                                    int(_bp.get("polish_opt", 20)),
                                    work_root, proposal=_pprop, polish=True,
                                    placed_row=_placed_row(_pi, _ps, _pseed),
                                    coord_nets=((best.get("unconn_nets") or ())
                                                if _coord_enabled else ()))
                polish_info = {"label": pv.get("label"),
                               "unconnected": pv.get("unconnected"),
                               "drc": pv.get("drc"),
                               "sort_key": pv.get("sort_key"),
                               "route_s": pv.get("route_s"),
                               "route_stage_s": pv.get("route_stage_s"),
                               "wall_s": pv.get("wall_s"),
                               "unconn_nets": pv.get("unconn_nets"),
                               "unconn_signature_sha256":
                                   pv.get("unconn_signature_sha256"),
                               "coordination": pv.get("coordination"),
                               "coordination_policy":
                                   ("reactive-hard-stubs"
                                    if _coord_enabled else "diagnostic-only"),
                               "adopted": False}
                if tuple(pv.get("sort_key") or (9,)) \
                        < tuple(best.get("sort_key") or (9,)):
                    polish_info["adopted"] = True
                    results.insert(0, pv)
                    best = pv
                print(f"[wave] {board} polish: unconn "
                      f"{polish_info['unconnected']} drc {polish_info['drc']} "
                      f"({'ADOPTED' if polish_info['adopted'] else 'kept original'})",
                      flush=True)
            except Exception as e:                              # noqa: BLE001
                polish_info = {"error": f"{type(e).__name__}: {e}"}
                print(f"[wave] {board} polish ERROR {polish_info['error']}",
                      flush=True)
    else:
        polish_info = {"skipped": True, "reason": _polish_reason}
        print(f"[wave] {board} polish skipped: {_polish_reason}", flush=True)
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
        # PUBLISH HYGIENE (2026-07-25, measured on the pass-2 winner: a
        # zero-fill `pourplan:` zone survived to the published board --
        # whichever stage wrote LAST is not guaranteed to have run the
        # cleanup chain, so the published artifact runs it itself; fresh
        # cycles, owner-review surface = the enforcement surface).
        try:
            import cec_slab_pour as _csp2
            _csp2.cleanup_floating_zones(dst)
            if _bp.get("pour_first") or _bp.get("slab_pour") \
                    or _bp.get("overunder"):
                _csp2.reap_nowhere_zones(dst)
        except Exception as _ce:                            # noqa: BLE001
            print(f"[wave] {board} publish hygiene skipped ({_ce})",
                  flush=True)
    # FAB REPAIR (owner 2026-07-27: "wire it in so that those things are actually
    # fixed instead of just acting as a gate with no teeth"). Runs on the
    # PUBLISHED artifact, after the hygiene chain, so the candidate reference and
    # anything sent to a fab house carry the repaired copper. Only the
    # deterministic, connectivity-safe repairs: sub-minimum track widths snapped
    # to the floor, duplicate/backtrack segments removed, zone priorities
    # deconflicted. Fail-safe -- a repair problem must never lose a routed board.
    if os.environ.get("CEC_FAB_REPAIR", "1") == "1" and src \
            and os.path.isfile(str(dst)):
        try:
            import cec_fab_repair
            _fr = cec_fab_repair.repair_admitted(str(dst))
            print("[wave] %s fab repair admission: chosen=%s adopted=%s "
                  "drc %s->%s unconnected %s->%s topology %s->%s"
                  % (board, _fr.get("chosen"), _fr.get("adopted"),
                     _fr["baseline"].get("drc"), _fr["after"].get("drc"),
                     _fr["baseline"].get("unconnected"),
                     _fr["after"].get("unconnected"),
                     _fr["baseline"].get("route_advisory"),
                     _fr["after"].get("route_advisory")), flush=True)
        except Exception as _fe:                            # noqa: BLE001
            print(f"[wave] {board} fab repair skipped ({type(_fe).__name__}: {_fe})",
                  flush=True)
    if src and os.path.isfile(str(dst)):
        try:
            _rescore_published(best, dst)
        except Exception as _re:                            # noqa: BLE001 -- fail closed
            best["gate"] = False
            best.setdefault("reasons", []).append(
                "published-artifact rescore ERROR (gate forced false): "
                f"{type(_re).__name__}: {_re}")
            print(f"[wave] {board} published rescore ERROR; gate forced false "
                  f"({type(_re).__name__}: {_re})", flush=True)
    new_best = _new_best_thermal(best, pub_dir, _bp)
    # CURRENT-BEST REFERENCE (owner directive 2026-07-25): mirror the published
    # winner into beta/<board>/candidate/ so every module has ONE stable, current
    # board to open -- the reason beta/ looked stale was that every routed
    # artifact lived only under build/. Runs after the hygiene chain and after
    # the thermal stamp, so the reference carries the reviewed artifact + its grade.
    candidate_path = _candidate_update(
        board, dst if (src and os.path.isfile(str(src))) else None,
        best, out_root=out_root)
    if new_best:
        _th = best.get("thermal") or {}
        print(f"[wave] {board} NEW BEST -> thermal: ok={_th.get('ok')} "
              f"dT={_th.get('dT')} "
              f"({_th.get('error') or _th.get('note') or _th.get('cooling')})",
              flush=True)
    report = {"board": board, "ts": ts, "W": W, "H": H, "passes": passes, "opt": opt,
              "published": os.path.relpath(dst, ROOT) if src else None,
              "new_best": new_best,
              # This is the durable improvement signal for loop managers.
              # ``new_best`` above is only relative to reports in this output
              # directory and must never be mistaken for canonical admission.
              "candidate_updated": bool(candidate_path),
              "candidate": (os.path.relpath(candidate_path, ROOT)
                            if candidate_path else None),
              "polish": polish_info,
              "prune": {"k": prune_k, "routed": len(results),
                        "pruned": len(pruned_rows)} if pruned_rows else None,
              "route_awareness": {
                  "service": {key: (route_service or {}).get(key)
                              for key in ("enabled", "pid", "prewarm_s",
                                          "cache_limit_bytes", "gpu", "error")},
                  "tournament": aware_report,
              },
              "best": {k: best.get(k) for k in
                       ("label", "gate", "kelvin_ok", "diffpair_ok", "drc", "unconnected",
                        "unconn_critical", "drc_types", "foreign", "thermal_ok",
                        "thermal", "rails", "sort_key", "reasons", "route_s",
                        "route_stage_s", "wall_s", "placement_reused",
                        "future_route", "route_repair", "completion_report",
                        "placement_craft", "place_craft_key",
                        "craft_repair",
                        "error", "route_quality", "gate_terms",
                        "stage_trace", "blockers", "blocker_summary",
                        "blocker_evidence",
                        "unconn_nets",
                        "unconn_signature", "unconn_signature_sha256",
                        "coordination")},
              "ranking": ([{"label": v["label"], "gate": v.get("gate"),
                            "sort_key": v.get("sort_key"),
                            "unconnected": v.get("unconnected"),
                            "drc": v.get("drc"), "route_s": v.get("route_s"),
                            "wall_s": v.get("wall_s"),
                            "route_stage_s": v.get("route_stage_s"),
                            "placement_reused": v.get("placement_reused"),
                            "future_route": v.get("future_route"),
                            "route_repair": v.get("route_repair"),
                            "placement_craft": v.get("placement_craft"),
                            "place_craft_key": v.get("place_craft_key"),
                            "craft_repair": v.get("craft_repair"),
                            "completion_report": v.get("completion_report"),
                            "error": v.get("error"),
                            "reasons": v.get("reasons"),
                            "route_quality": v.get("route_quality"),
                            "gate_terms": v.get("gate_terms"),
                            "stage_trace": v.get("stage_trace"),
                            "blockers": v.get("blockers"),
                            "blocker_summary": v.get("blocker_summary"),
                            "blocker_evidence": v.get("blocker_evidence"),
                            "unconn_nets": v.get("unconn_nets"),
                            "unconn_signature": v.get("unconn_signature"),
                            "unconn_signature_sha256":
                                v.get("unconn_signature_sha256"),
                            "coordination": v.get("coordination")}
                           for v in results]
                          + [{"label": r["label"], "pruned": True,
                              "place_key": r.get("place_key"),
                              "place_craft_key": r.get("place_craft_key"),
                              "placement_craft": r.get("placement_craft"),
                              "craft_repair": r.get("craft_repair"),
                              "future_route": r.get("future_route"),
                              "route_repair": r.get("route_repair"),
                              "error": r.get("error")} for r in pruned_rows])}
    # Wave evidence contains exact placement-craft certificates and blocker
    # traces. Pretty-print indentation inflated a representative six-variant
    # PCIe report from about 3.9 MiB of evidence to 10.4 MiB without adding any
    # information, and unattended loops multiplied that waste. Keep the same
    # lossless JSON schema in compact form; dashboard/readers parse JSON rather
    # than depending on whitespace.
    with open(os.path.join(pub_dir, f"{ts}-wave-report.json"), "w") as fh:
        json.dump(report, fh, separators=(",", ":"), default=str)
        fh.write("\n")
    print(f"[wave] {board} BEST={best['label']} gate={best.get('gate')} -> {dst}", flush=True)
    _wlog(f"wave done: {board} best={best['label']} gate={best.get('gate')}", tag="wave",
          detail=f"kelvin={best.get('kelvin_ok')} unconn={best.get('unconnected')} "
                 f"foreign={ (best.get('foreign') or {}).get('tracks') }t; published {os.path.relpath(dst, ROOT)}")
    # SEAT: propose intents for the NEXT wave from this wave's verdicts (local
    # cec-worker-quality, nothink -- owner seat policy 2026-07-08). Fail-safe by
    # construction; the proposals file steers the next run_board of this board.
    if os.environ.get("CEC_WAVE_INTENTS", "1") != "0":
        try:
            import cec_wave_intents
            ran = {v["label"].rsplit("-", 2)[0] for v in results}
            props, plog = cec_wave_intents.propose(board, results, W, H, ran)
            # A2 SNAGFIX -- first live wiring (owner GO 2026-07-09): compile the BEST
            # verdict's STRUCTURED violations into a deterministic proposal through the
            # SAME validated channel (prop-snagfix provenance). The judgment seat and
            # the mechanical compiler now feed the same next-wave grid.
            try:
                import cec_snag_compiler
                sf = cec_snag_compiler.compile_validated(best, board)
                if sf.get("proposal"):
                    sf["proposal"]["name"] = "snagfix"
                    props = list(props) + [sf["proposal"]]
                    plog.append("snagfix: %d near / %d assign intents from the best verdict"
                                % (len(sf["proposal"].get("near") or ()),
                                   len(sf["proposal"].get("assign") or ())))
            except Exception as e:                          # noqa: BLE001 -- fail-safe
                plog.append(f"snagfix unavailable: {e}")
            if props:
                path = cec_wave_intents.save(out_root, board, props, plog,
                                             meta={"from_wave": ts})
                _wlog(f"{board}: seat proposed {len(props)} intent(s) for the next wave",
                      tag="wave", detail="; ".join(p["name"] + " -- " + p["rationale"][:90]
                                                   for p in props) + f" [{path}]")
            print(f"[wave] {board} intent seat: " + " | ".join(plog[-2:]), flush=True)
        except Exception as e:                              # noqa: BLE001 -- fail-safe
            print(f"[wave] {board} intent seat unavailable: {e}", flush=True)
    return report


def main():
    ap = argparse.ArgumentParser(description="fresh-board synthesis wave (run in-container)")
    ap.add_argument("--boards", default="eps-8pin-rev3")
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
