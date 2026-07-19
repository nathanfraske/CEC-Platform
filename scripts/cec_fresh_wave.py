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
import glob
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
        # HEX PANEL (owner ask 2026-07-15): the dash tile = 3x2 array -- front/back
        # renders | L1/L4 plots | In1/In2 plots, aligned orientation, ruled dividers.
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
    # HUB REV2 (owner directive 2026-07-15: "get the Hub down properly ... start from
    # just the connectors and go from there"): proto-V1 is ~120x95-class; the 4-jack
    # row (~4x16mm + gaps) floors one edge at ~70mm. Aggressive seed; refusals teach.
    "hub-standard-rev2": (88.0, 62.0),
    "eps-8pin": (96.0, 37.0),
    "pcie-8pin-2port": (86.5, 44.0),
    "pcie-8pin-3port": (103.5, 56.0),
    # owner 2026-07-08 "way too large -- tone it down": geometry floor is J3 (~63mm) and
    # the blade row + signal stub (~59mm); dual-sided chains + no mounts + full overhang
    # make 70x55 the aggressive seed (the shrink pass walks further once gate-clean).
    "atx-24pin-rev3": (70.0, 55.0),
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
    # HUB REV2 (2026-07-15): connector-first, no force lanes (no shunt corridors on a
    # hub) -- the MCU/fan seats stay dormant by their force_lanes gate; hub-specific
    # rungs (LED-ring centerpiece macro, WROOM seat) get added from wave-1 evidence.
    # J6 mezzanine is DNP but its LAND places like any part; its position becomes the
    # stack ALIGNMENT CONTRACT with the 24-pin once a layout freezes (FOLLOWUPS).
    "hub-standard-rev2": {"mount_holes": "corners", "connector_overhang": "edge",
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
                          "anchor_roles": {"J_PWR": "power_in", "J_USB": "usb",
                                           "J2": "host", "J3": "host",
                                           "J4": "host", "J5": "host",
                                           "J_KVM": "host",
                                           # board-to-board, interior -- never an edge
                                           "J6": "free"},
                          # owner catch on wave-1 snapshots (2026-07-15): jacks were
                          # seated on the RIGHT (the host-role default edge) -- the
                          # 4-jack row belongs on the long TOP edge like the proto;
                          # USB + KVM bottom, power feed right.
                          "edge_override": {"J2": "top", "J3": "top", "J4": "top",
                                            "J5": "top", "J_USB": "bottom",
                                            "J_KVM": "bottom", "J_PWR": "right"},
                          # centerpiece (owner: "the center logo and LEDs"): the ring
                          # (DL1-5,DL7) as a RIGID group, offsets lifted verbatim from
                          # the proto board's ring; scored to board center. DL6 is NOT
                          # in the group = the free status LED. Logo = FRONT copper at
                          # the seated ring's centroid (materialize logo_at=ring).
                          "rigid_groups": [{"score": "center", "logo": True, "offsets": {
                              "DL1": (-0.08, -10.42, 0), "DL2": (7.42, -4.32, 0),
                              "DL3": (9.92, 5.68, 0), "DL4": (-0.08, 7.68, 0),
                              "DL5": (-10.08, 5.68, 0), "DL7": (-7.08, -4.32, 0)}}],
                          "logo_at": "ring",
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

# The six refined sensing cells (owner ladder ruling 2026-07-11): rigid blueprint
# stamps anchored on the placer's own lane seats (RS{n}), inheriting each seat's
# rotation; cable_index drives the per-lane net map; ideal_internal False keeps
# the B7 refined copper verbatim.
_SENSE_LANE_BP = "modules/12vhpwr-standard/blueprints/sense-lane-rs4-b7.json"
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
    """The BOARD_PARAMS + board-manifest placement_directives merge (shared by the serial
    and parallel candidate paths)."""
    p = dict(BOARD_PARAMS.get(board) or {})
    mf = os.path.join(ROOT, "modules", board, "board-manifest.json")
    if os.path.isfile(mf):
        try:
            pd = (json.load(open(mf)) or {}).get("placement_directives") or {}
            p.update({k: v for k, v in pd.items()
                      if not k.startswith("_") and not k.endswith(("_note", "_rules", "provenance"))})
        except Exception:                                  # noqa: BLE001
            pass
    # thermal config resolves by BOARD NAME, not the variant filename (wave variants
    # are plain-<strat>-s<seed>.kicad_pcb -> basename keying missed, the solve ran
    # configless and the new-best stamp mirage-FAILED dT~0 on its first live target,
    # 2026-07-19). Set HERE so BOTH the parent (_new_best_thermal) and the spawn
    # workers (_build_session -> grade -> _oracle_env) export CEC_THERMAL_BOARD_HINT.
    p.setdefault("thermal_board_hint", board)
    return p


def _build_session(board, W, H, iname, strat, seed, proposal=None):
    """The variant's PlacementSession, identically for the place-only (prune) and
    full-grade phases -- factored so the two can never drift. *proposal* = a
    VALIDATED seat proposal dict (cec_wave_intents), applied instead of a named
    hand intent; its role_keepouts merge into params (the params-level lever)."""
    _p = _board_params(board)
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
    return s, _p


def _place_variant(board, W, H, iname, strat, seed, proposal=None):
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
        s, _p = _build_session(board, W, H, iname, strat, seed, proposal)
        with csp._oracle_env(s.cfg.params if s.cfg else None):
            cand = s.compile()
        key = csp._candidate_sort_key(cand)
        return {"label": label, "iname": iname, "strat": strat, "seed": seed,
                "place_key": [float(k) for k in key],
                "residual": cand.residual, "corridor_cross": cand.corridor_cross,
                "place_wall_s": round(time.monotonic() - t0, 1)}
    except Exception as e:                                  # noqa: BLE001 -- fail-open
        return {"label": label, "iname": iname, "strat": strat, "seed": seed,
                "place_key": None, "error": "%s: %s" % (type(e).__name__, e),
                "place_wall_s": round(time.monotonic() - t0, 1)}


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


def _grade_variant(board, W, H, iname, strat, seed, passes, opt, work_root, proposal=None):
    """Grade ONE (intent, strat, seed) variant. Module-level + name-keyed intent lookup so
    it pickles into a spawn worker (intents are closures; spawn is REQUIRED -- pcbnew/wx is
    not fork-safe, the cec_fr.generate_batch precedent)."""
    label = f"{iname}-{strat}-s{seed}"
    t0 = time.monotonic()
    # The wave is the consumer that WANTS the fork's real seed-diversity axis
    # (R-01); everything else stays stock-order unless it opts in (see cec_fr
    # run_freerouting CEC_FR_SEED_AXIS note, 2026-07-14).
    os.environ["CEC_FR_SEED_AXIS"] = "1"
    # Plateau-kill (external stage-0 pre-kill on the cec2 CEC_PASS telemetry): a
    # candidate whose failed-count sits flat for 4 passes is a loser -- kill the
    # JVM, grade it failed, spend the wall-clock on live candidates instead.
    os.environ.setdefault("CEC_FR_PLATEAU_KILL", "4")
    s, _p = _build_session(board, W, H, iname, strat, seed, proposal)
    out = os.path.join(work_root, board, f"{label}.kicad_pcb")
    v = s.grade(out=out, keep=True,
                passes=int(_p.get("wave_passes", passes)),
                opt=int(_p.get("wave_opt", opt)),
                fr_timeout=int(_p.get("wave_fr_timeout", 900)),
                seed=seed,              # pin FR seed: wave-to-wave comparability
                unconn_finish_tol=2,
                # owner 2026-07-08: the 5-17s thermal solve runs ONLY on a would-be
                # gate-clean candidate (all other terms green) -- a published best
                # always has a REAL solve behind it.
                thermal="lazy",
                # owner blind verdict 2026-07-09: PRECISION-FIRST ON (kelvin taps +
                # coupled pairs deterministic + locked, refused pairs solo-tiered,
                # FR residual-only). wave_precision=False in params restores bare.
                precision=bool(_p.get("wave_precision", True)))
    v["label"] = label
    v["placed"] = out
    v["wall_s"] = round(time.monotonic() - t0, 1)
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


def run_board(board, seeds, passes, opt, out_root, work_root):
    W, H = BOARD_WH.get(board, (100.0, 44.0))
    if os.environ.get("CEC_BOARD_W"):
        W = float(os.environ["CEC_BOARD_W"])                # A/B knob (owner 2026-07-12)
    workers = _wave_workers()
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
    prune_k = int(os.environ.get("CEC_WAVE_PRUNE", "4"))
    if prune_k > 0 and len(variants) > prune_k:
        _t0p = time.monotonic()
        if workers <= 1:
            placed_rows = [_place_variant(board, W, H, i, st, sd, prop)
                           for i, st, sd, prop in variants]
        else:
            import concurrent.futures as _cf
            import multiprocessing as _mp
            _ctx = _mp.get_context("spawn")                    # pcbnew is NOT fork-safe
            with _cf.ProcessPoolExecutor(max_workers=workers, mp_context=_ctx) as _pool:
                placed_rows = list(_pool.map(
                    _place_variant,
                    *zip(*[(board, W, H, i, st, sd, prop) for i, st, sd, prop in variants])))
        variants, pruned_rows = _prune_variants(variants, placed_rows, prune_k)
        print(f"[wave] {board} prune: routing {len(variants)}/{len(placed_rows)} "
              f"variant(s) by cheap placement key ({len(pruned_rows)} pruned, recorded "
              f"in the report; CEC_WAVE_PRUNE=0 routes all) "
              f"[{round(time.monotonic() - _t0p, 1)}s]", flush=True)

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
              f"({v.get('wall_s')}s)", flush=True)

    if workers <= 1:
        for iname, strat, seed, prop in variants:
            try:
                _consume(_grade_variant(board, W, H, iname, strat, seed, passes, opt,
                                        work_root, proposal=prop))
            except Exception as e:                              # noqa: BLE001
                print(f"[wave] {board} {iname}-{strat}-s{seed}: ERROR {type(e).__name__}: {e}",
                      flush=True)
    else:
        import concurrent.futures as cf
        import multiprocessing as mp
        ctx = mp.get_context("spawn")                          # pcbnew is NOT fork-safe
        with cf.ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
            futs = {pool.submit(_grade_variant, board, W, H, iname, strat, seed,
                                passes, opt, work_root, prop): (iname, strat, seed)
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
    new_best = _new_best_thermal(best, pub_dir, _bp)
    if new_best:
        _th = best.get("thermal") or {}
        print(f"[wave] {board} NEW BEST -> thermal: ok={_th.get('ok')} "
              f"dT={_th.get('dT')} "
              f"({_th.get('error') or _th.get('note') or _th.get('cooling')})",
              flush=True)
    report = {"board": board, "ts": ts, "W": W, "H": H, "passes": passes, "opt": opt,
              "published": os.path.relpath(dst, ROOT) if src else None,
              "new_best": new_best,
              "prune": {"k": prune_k, "routed": len(results),
                        "pruned": len(pruned_rows)} if pruned_rows else None,
              "best": {k: best.get(k) for k in
                       ("label", "gate", "kelvin_ok", "diffpair_ok", "drc", "unconnected",
                        "unconn_critical", "foreign", "thermal_ok", "thermal", "sort_key",
                        "reasons")},
              "ranking": ([{"label": v["label"], "gate": v.get("gate"),
                            "sort_key": v.get("sort_key")} for v in results]
                          + [{"label": r["label"], "pruned": True,
                              "place_key": r.get("place_key"),
                              "error": r.get("error")} for r in pruned_rows])}
    with open(os.path.join(pub_dir, f"{ts}-wave-report.json"), "w") as fh:
        json.dump(report, fh, indent=2, default=str)
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
