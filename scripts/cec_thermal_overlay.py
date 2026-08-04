#!/usr/bin/env python3
"""cec_thermal_overlay.py -- georeferenced electro-thermal heatmap OVER the board.

Runs cec_thermal2d.solve_board_thermal on a board, then renders a single
composite PNG that the live dashboard (scripts/cec_dashboard.py) shows alongside
the plain board render: the board's FILLED copper (drawn from the same polygons
the solver rasterizes) + the board outline, with the steady-state temperature
field alpha-blended on top in `inferno`, a colorbar in degC, and the max T in the
title. Because the background copper and the heatmap share ONE matplotlib axes
with the SAME mm extent, they are pixel-aligned by construction -- no attempt to
register against the raytraced kicad-cli top render (which has its own
perspective/margins).

This helper exists as its own entry point because the solve needs pcbnew + scipy
+ shapely, which live in the routing container; the dashboard invokes it there
via `docker compose exec`. It prints a one-line JSON summary on stdout (the LAST
line) so the caller can surface max_T / dT in the panel header.

Usage (inside the routing container):
  python3 scripts/cec_thermal_overlay.py --board <board.kicad_pcb> --out <overlay.png> \
      [--grid-mm 0.4] [--ambient 50] [--currents '{"GND":29.2,...}'] [--stackup '{...}']

The default currents are the BALANCED EPS case (300-350W CPU): ~14.6 A per cable
on each *_HI/*_LO 12V net and the full ~29 A on the shared GND return. The
default stackup is the cost-down baseline F/B=1oz, In1/In2=0.5oz.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

# matplotlib headless before any pyplot import
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ModuleNotFoundError:                   # viz-only dep: the SOLVE path
    matplotlib = None                         # (_solve_thermal) must never die
    plt = None                                # on a matplotlib-less container;
                                              # render entry points check plt.
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_thermal2d as t2  # noqa: E402
import cec_fab_profile as fab  # noqa: E402


# FEM is a verifier, not a copper generator.  This marker is copied into every
# result so downstream gates and archived dashboards can reject results created
# by the former "derive expected pours while solving" behavior.
THERMAL_GEOMETRY_SOURCE = "source-declared-copper-only:v1"
_TEMP_ANALYSIS_PATHS = set()


class ThermalGeometryError(RuntimeError):
    """The analysis board could not be proven copper-identical to its source."""


def board_fab_profile(board_path, board_hint=None):
    """Return the declared profile, falling back to approved board-family policy.

    Saved-board metadata wins.  The name fallback is needed while evaluating a
    not-yet-materialized placement candidate, whose temporary filename has no
    board properties until the generator writes it.
    """
    hint = board_hint or os.environ.get("CEC_THERMAL_BOARD_HINT") or board_path
    if board_path and os.path.isfile(board_path):
        try:
            import pcbnew
            declared = fab.board_profile_name(pcbnew.LoadBoard(board_path))
            if declared:
                return declared
        except Exception:  # noqa: BLE001
            pass
    return fab.profile_for_board_hint(hint)


def board_dielectric_config(board_path, board_hint=None):
    profile = board_fab_profile(board_path, board_hint=board_hint)
    return fab.dielectric_mm(profile) if profile else None


# Default BALANCED EPS currents (see module docstring): per-cable 12V ~14.6 A,
# shared GND return ~29.2 A. Nets that are not present on a given board are
# simply ignored by the solver.
def default_currents(board):
    """Build balanced currents from the board's actual zone nets so this works on
    any EPS-family interposer regardless of cable count."""
    import pcbnew
    b = pcbnew.LoadBoard(board)
    nets = set()
    for z in b.Zones():
        nets.add(z.GetNetname())
    nc = {}
    cables = 0
    for n in nets:
        if n.endswith("_HI") or n.endswith("_LO"):
            nc[n] = 14.6
            if n.endswith("_HI"):
                cables += 1
    if "GND" in nets:
        nc["GND"] = max(29.2, 14.6 * max(cables, 1) * 2.0 if cables == 0 else 14.6 * cables * 2.0)
        # ~2x14.6 per cable returns through GND; ~29.2 for the 2-cable balanced case
        nc["GND"] = 14.6 * max(cables, 2)
    return nc


def _board_net_names(board_path):
    """Return exact saved-board net names, or an empty set for hint-only calls."""
    if not board_path or not os.path.isfile(board_path):
        return set()
    try:
        import pcbnew
        board = pcbnew.LoadBoard(board_path)
        return {str(net) for net in board.GetNetsByName().keys()}
    except Exception:                                      # noqa: BLE001
        return set()


def _resolve_hierarchical_net(short_name, board_nets):
    """Resolve a schematic-local net name to its unique saved hierarchical name."""
    if not board_nets or short_name in board_nets:
        return short_name
    suffix = short_name if short_name.startswith("/") else "/" + short_name
    matches = sorted(net for net in board_nets if net.endswith(suffix))
    return matches[0] if len(matches) == 1 else short_name


def board_thermal_config(board_path, board_hint=None):
    """Per-board thermal inputs the generic auto-overlay can't infer from the netlist alone. Returns
    (net_currents, stackup_oz, src_sink_override, cooling), any of which may be None to fall back to the
    generic default (default_currents + default cable-board stackup + auto J_IN/J_OUT src/sink + still-air
    no-case). Only boards whose high-current topology differs from the EPS/PCIe cable family need an entry.

    12VHPWR: six per-pin 12V lanes (SENSEP*) routed as TRACES (not pours), fed J3 (12V in) -> shunt -> J4
    (out, not J_IN/J_OUT), and a 2oz-outer / 1oz-dual-inner-GND stackup (owner, 2026-06-20). Current = the
    balanced 600W connector case: 50A / 6 pins = 8.33 A/pin, 50A GND return.

    `cooling` (or None) is the PRODUCTION case-cooling model the owner validated 2026-06-20: the dashboard's
    default still-air + adiabatic-edge boundary gave a misleadingly hot dT99/maxT149 for 12VHPWR; with the
    real production enclosure -- a full metal case, TIM from the RS1-6 shunts to the case, and the M3 mounts
    coupled to the case -- the solver lands at dT~24 / maxT~74 = PASS (same PASS regime as the owner's
    ~14C/64C hand calc, both well under the 30C gate; the 2.5D solver runs ~9C hotter on dT than that
    lumped estimate -- not an exact match). cooling = {shunt_prefix, g_chassis_W_per_K (per-shunt TIM), g_mount_W_per_K (per M3 mount), label}.
    Conservative-TIM / mount-only / still-air bounds are reachable via the CEC_THERMAL_* env knobs in
    render_per_layer. Scoped to 12VHPWR only -- the EPS/PCIe cable boards keep still-air pending owner
    sign-off on whether they share the same enclosure model (FOLLOWUPS)."""
    # CEC_THERMAL_BOARD_HINT (2026-07-19, closes the FOLLOWUPS 2026-07-11 keying gap):
    # wave variants (plain-dataflow-s1.kicad_pcb) and renamed dashboard archives never
    # carry the board name in their basename, so this config silently missed and the
    # solve ran configless -> the impossible dT~0 the mirage guard trips on. Callers
    # that KNOW the board (the wave's _oracle_env exports it from board params) set the
    # hint; the basename stays the fallback for committed boards.
    name = (board_hint or os.environ.get("CEC_THERMAL_BOARD_HINT")
            or os.path.basename(board_path)).lower()
    profile_name = board_fab_profile(board_path, board_hint=board_hint)
    profile_stackup = fab.stackup_oz(profile_name) if profile_name else None
    if "12vhpwr" in name or "12v2x6" in name:
        nc, ov = {}, {}
        # The current BETA sheet renamed lane 6's pre-shunt node to /FAN_12V
        # because the fan feed taps that lane.  Select exactly one lane-6 name
        # from the artifact being verified; requesting both silently double-
        # described one physical lane and made injection accounting fail on the
        # obsolete name.
        board_nets = _board_net_names(board_path)
        for n in range(1, 7):
            hi = "/FAN_12V" if n == 6 and "/FAN_12V" in board_nets else "/SENSEP%d_HI" % n
            nc[hi] = 8.33
            nc["/SENSEP%d_LO" % n] = 8.33
            ov[hi] = {"refs_src": ["J3"], "refs_sink": ["RS%d" % n]}
            ov["/SENSEP%d_LO" % n] = {"refs_src": ["RS%d" % n], "refs_sink": ["J4"]}
        nc["GND"] = 50.0
        ov["GND"] = {"refs_src": ["J4"], "refs_sink": ["J3"]}
        cooling = {"shunt_prefix": "RS", "g_chassis_W_per_K": 0.3, "g_mount_W_per_K": 0.5,
                   "label": "production: metal case (TIM on RS shunts + M3 mounts)"}
        return nc, profile_stackup, ov, cooling
    if "atx-24pin" in name or "atx24" in name:
        # 24-PIN PRODUCTION COOLING (owner ruling 2026-07-20: "24 pin ideally
        # doesn't need anything besides a plastic case for the first prod runs
        # with some vent holes"): a vented plastic enclosure is thermally
        # ~still-air -- no TIM path, no chassis coupling -- so the still-air
        # solve IS the production posture (mild vent convection is margin, not
        # modeled). cooling=None keeps the still-air default; this entry
        # supplies the rail currents + the board-class stackup (one inner GND
        # plane + one inner power-routing layer, 2oz outers) so the solve
        # stops running configless. Rail currents = the owner connector bars
        # (spec §6.4-adjacent, the force-rails RAIL_AMPS table).
        nc = {"/SENSE12V_HI": 12.0, "/SENSE12V_LO": 12.0,
              "/SENSE5V_HI": 20.0, "+5V_MAIN": 20.0,
              "/SENSE3V3_HI": 20.0, "/SENSE3V3_LO": 20.0,
              "+5VSB": 3.0, "/SENSE5VSB_LO": 3.0,
              "GND": 55.0}
        ov = {}
        # Sink = the WHOLE TB blade row, not TB1 (2026-07-22, found by the injection
        # accounting): the wave's straight-through pass chooses the TB net order PER
        # CANDIDATE, so a rail's blade is not always TB1 -- pad lookups are net-scoped,
        # so listing every TB ref is safe (only same-net blades match). GND previously
        # had NO override at all -> fell to the J_IN/J_OUT default (absent on this
        # board) -> the 62A return path never injected on ANY 24-pin solve.
        tb_all = ["TB%d" % i for i in range(1, 11)]
        for hi, lo, rs in (("/SENSE12V_HI", "/SENSE12V_LO", "RS1"),
                           ("/SENSE5V_HI", "+5V_MAIN", "RS2"),
                           ("/SENSE3V3_HI", "/SENSE3V3_LO", "RS3"),
                           ("+5VSB", "/SENSE5VSB_LO", "RS4")):
            ov[hi] = {"refs_src": ["J3"], "refs_sink": [rs]}
            ov[lo] = {"refs_src": [rs], "refs_sink": tb_all}
        ov["GND"] = {"refs_src": tb_all, "refs_sink": ["J3"]}
        return nc, profile_stackup, ov, None
    if "hub-standard" in name or "hub" in name.split("-")[0:1]:
        # The Hub has no J_IN/J_OUT or *_HI cable anatomy, so it needs an
        # explicit source/sink map. Currents remain the existing §2.5/OQ-2
        # design basis: 2.5 A on every mutually-exclusive shared-bus stage,
        # 0.5 A per protected port and on the held logic reservoir, and 0.5 A
        # on USB VBUS. The map below follows the
        # exported rev2 netlist's actual cascade:
        #
        #   U5 OUT -> U11 IN1 -> U11 OUT -> U7 IN2 -> U7 OUT
        #          -> F1..F4 -> J2..J5
        #
        # Stackup comes only from the approved fabrication profile. For the
        # Hub that is JLC06161H-3313: 1 oz outer and 0.5 oz inner copper.
        # cooling=None keeps the still-air bound until the enclosure is known.
        board_nets = _board_net_names(board_path)
        net = lambda short: _resolve_hierarchical_net(short, board_nets)  # noqa: E731
        nc = {net("+5VSB"): 2.5, net("/5VSB_RAW"): 2.5,
              net("/PSU_5V"): 2.5, net("/PSU_5V_KVM"): 2.5,
              net("/MAIN_5V_RAW"): 2.5, net("/+5V_HOLD"): 0.5,
              net("/USB_VBUS"): 0.5,
              net("/VCC_P1"): 0.5, net("/VCC_P2"): 0.5,
              net("/VCC_P3"): 0.5, net("/VCC_P4"): 0.5,
              net("GND"): 2.5}
        # rev2 anatomy: the A4 consolidation makes J_PWR the ONE 3-pin power-in
        # (MAIN_5V / GND / 5VSB) -- there is no J1/J_5V on this board (measured
        # 2026-07-23; the first entry draft used the alpha names and every net
        # dropped "no src/sink terminals").
        ov = {
            net("/5VSB_RAW"): {"refs_src": ["J_PWR"], "refs_sink": ["U5"]},
            net("/PSU_5V"): {"refs_src": ["U5"], "refs_sink": ["U11"]},
            net("/PSU_5V_KVM"): {"refs_src": ["U11"], "refs_sink": ["U7"]},
            net("/MAIN_5V_RAW"): {"refs_src": ["J_PWR"], "refs_sink": ["U7"]},
            net("+5VSB"): {"refs_src": ["U7"], "refs_sink": ["F1", "F2", "F3", "F4"]},
            net("/+5V_HOLD"): {"refs_src": ["D1"], "refs_sink": ["U3"]},
            net("/USB_VBUS"): {"refs_src": ["J_USB"], "refs_sink": ["U5"]},
            net("/VCC_P1"): {"refs_src": ["F1"], "refs_sink": ["J2"]},
            net("/VCC_P2"): {"refs_src": ["F2"], "refs_sink": ["J3"]},
            net("/VCC_P3"): {"refs_src": ["F3"], "refs_sink": ["J4"]},
            net("/VCC_P4"): {"refs_src": ["F4"], "refs_sink": ["J5"]},
            net("GND"): {"refs_src": ["J2", "J3", "J4", "J5", "U1"],
                         "refs_sink": ["J_PWR"]},
        }
        return nc, profile_stackup, ov, None
    return None, profile_stackup, None, None


def _edge_segments(board):
    """Board outline segments (mm) from Edge.Cuts graphics, for the overlay frame."""
    import pcbnew
    segs = []
    for d in board.GetDrawings():
        try:
            if pcbnew.LayerName(d.GetLayer()) != "Edge.Cuts":
                continue
        except Exception:
            continue
        try:
            st, en = d.GetStart(), d.GetEnd()
            segs.append(((st.x / 1e6, st.y / 1e6), (en.x / 1e6, en.y / 1e6)))
        except Exception:
            pass
    return segs


def _copper_patches(board, std_layers):
    """Filled-copper polygons (mm) per std layer, for the grey background."""
    from shapely.geometry import Polygon  # noqa: F401  (only need points)
    out = {std: [] for std in std_layers.values()}
    for z in board.Zones():
        for lid in z.GetLayerSet().Seq():
            std = std_layers.get(lid)
            if std is None:
                continue
            poly = z.GetFilledPolysList(lid)
            for oi in range(poly.OutlineCount()):
                ol = poly.Outline(oi)
                pts = [(ol.CPoint(k).x / 1e6, ol.CPoint(k).y / 1e6)
                       for k in range(ol.PointCount())]
                if len(pts) >= 3:
                    out[std].append(pts)
    return out


def _xy(point):
    return int(point.x), int(point.y)


def _polyset_signature(polyset):
    """JSON-safe signature of source-declared polygon outlines (not fill cache)."""
    polygons = []
    for oi in range(polyset.OutlineCount()):
        outline = polyset.Outline(oi)
        outer = tuple(_xy(outline.CPoint(i)) for i in range(outline.PointCount()))
        holes = []
        for hi in range(polyset.HoleCount(oi)):
            hole = polyset.Hole(oi, hi)
            holes.append(tuple(_xy(hole.CPoint(i)) for i in range(hole.PointCount())))
        polygons.append((outer, tuple(holes)))
    return tuple(polygons)


def _declared_copper_manifest(board):
    """Return the copper topology that a verifier is allowed to consume.

    Filled polygons are deliberately excluded: they are a KiCad-derived cache
    which `_prepare_filled` may refresh.  Zone declarations, tracks/vias and pad
    copper are included, so adding a hypothetical corridor or changing actual
    copper while preparing FEM cannot pass unnoticed.
    """
    zones = []
    zone_rule_getters = (
        "GetFillMode", "GetMinThickness", "GetLocalClearance",
        "GetThermalReliefGap", "GetThermalReliefSpokeWidth", "GetPadConnection",
        "GetCornerSmoothingType", "GetCornerRadius", "GetIslandRemovalMode",
        "GetMinIslandArea", "GetIsRuleArea", "GetDoNotAllowTracks",
        "GetDoNotAllowVias", "GetDoNotAllowPads", "GetDoNotAllowFootprints",
        "GetDoNotAllowZoneFills",
    )
    for zone in board.Zones():
        rules = tuple((name, getattr(zone, name)()) for name in zone_rule_getters)
        zones.append((
            zone.GetNetname(), zone.GetZoneName(), int(zone.GetAssignedPriority()),
            tuple(int(layer) for layer in zone.GetLayerSet().Seq()),
            rules, _polyset_signature(zone.Outline()),
        ))

    tracks = []
    for track in board.GetTracks():
        klass = track.GetClass()
        common = (
            klass, track.GetNetname(),
            tuple(int(layer) for layer in track.GetLayerSet().Seq()),
            _xy(track.GetStart()), _xy(track.GetEnd()), bool(track.IsLocked()),
        )
        if klass == "PCB_VIA":
            layers = tuple(int(layer) for layer in track.GetLayerSet().Seq())
            detail = (
                "via", _xy(track.GetPosition()), int(track.GetDrill()),
                int(track.TopLayer()), int(track.BottomLayer()), int(track.GetViaType()),
                tuple((layer, int(track.GetWidth(layer))) for layer in layers),
            )
        else:
            mid = _xy(track.GetMid()) if hasattr(track, "GetMid") else None
            detail = ("route", int(track.GetLayer()), int(track.GetWidth()), mid)
        tracks.append(common + detail)

    pads = []
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        for pad in footprint.Pads():
            size, drill = pad.GetSize(), pad.GetDrillSize()
            offset, delta = pad.GetOffset(), pad.GetDelta()
            pads.append((
                ref, pad.GetNumber(), pad.GetNetname(),
                tuple(int(layer) for layer in pad.GetLayerSet().Seq()),
                _xy(pad.GetPosition()), (int(size.x), int(size.y)),
                (int(drill.x), int(drill.y)), (int(offset.x), int(offset.y)),
                (int(delta.x), int(delta.y)), int(pad.GetShape()),
                int(pad.GetAttribute()), float(pad.GetOrientation().AsDegrees()),
                bool(pad.IsLocked()),
            ))

    # Board-item ordering is not semantic and KiCad may normalize it on save.
    return {
        "zones": sorted(zones, key=repr),
        "tracks": sorted(tracks, key=repr),
        "pads": sorted(pads, key=repr),
    }


def _manifest_sha256(manifest):
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _assert_geometry_parity(source, analysis):
    if source == analysis:
        return
    counts = lambda m: {kind: len(m.get(kind, ())) for kind in ("zones", "tracks", "pads")}
    raise ThermalGeometryError(
        "FEM preparation changed declared copper geometry: source=%s analysis=%s"
        % (counts(source), counts(analysis)))


def _remove_temp_board_artifacts(board_path):
    """Remove a controlled temp PCB and KiCad sidecars created while saving it."""
    if not board_path:
        return
    base = (board_path[:-len(".kicad_pcb")] if board_path.endswith(".kicad_pcb")
            else board_path)
    for path in (board_path, base + ".kicad_pro", base + ".kicad_prl",
                 base + ".kicad_dru", board_path + "-bak"):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _register_temp_analysis_path(board_path):
    """Delete a worker's reusable analysis board when that worker exits."""
    if board_path in _TEMP_ANALYSIS_PATHS:
        return
    import atexit
    _TEMP_ANALYSIS_PATHS.add(board_path)
    atexit.register(_remove_temp_board_artifacts, board_path)


def _prepare_filled(board_path, *, return_provenance=False):
    """Fill only source-declared zones and prove copper-geometry parity.

    Unfilled zone polygons are declarations of real intended copper, so KiCad's
    fill cache may be refreshed for the solver.  No zone, trace, via or pad may
    be synthesized here.  Any load/fill/save/parity error is verification-fatal
    rather than silently falling back to a different analysis artifact.
    """
    import pcbnew
    import tempfile

    stage = None
    try:
        source_path = os.path.abspath(board_path)
        if not os.path.isfile(source_path):
            raise ThermalGeometryError("FEM source board does not exist: %s" % source_path)
        board = pcbnew.LoadBoard(source_path)
        if board is None:
            raise ThermalGeometryError("KiCad could not load FEM source board: %s" % source_path)
        source_manifest = _declared_copper_manifest(board)
        source_sha = _manifest_sha256(source_manifest)

        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        _assert_geometry_parity(source_manifest, _declared_copper_manifest(board))

        # One bounded, overwritten cache entry per process/thread avoids both
        # basename collisions and a new multi-megabyte board for every wave.
        # Pipeline workers are separate processes; dashboard analysis is
        # single-flight.  A thread id also keeps an accidental in-process
        # parallel solve from overwriting another thread's render input.
        import threading
        worker_key = "%d_%d" % (os.getpid(), threading.get_ident())
        out = os.path.join(
            tempfile.gettempdir(),
            "thermal_filled_%s.kicad_pcb" % worker_key,
        )
        fd, stage = tempfile.mkstemp(
            prefix=".%s." % os.path.basename(out), suffix=".kicad_pcb",
            dir=tempfile.gettempdir())
        os.close(fd)
        pcbnew.SaveBoard(stage, board)
        if not os.path.isfile(stage) or os.path.getsize(stage) == 0:
            raise ThermalGeometryError("KiCad did not save the filled FEM analysis board")
        saved = pcbnew.LoadBoard(stage)
        if saved is None:
            raise ThermalGeometryError("KiCad could not reload the filled FEM analysis board")
        saved_manifest = _declared_copper_manifest(saved)
        _assert_geometry_parity(source_manifest, saved_manifest)
        analysis_sha = _manifest_sha256(saved_manifest)
        os.replace(stage, out)
        _register_temp_analysis_path(out)
        _remove_temp_board_artifacts(stage)  # PCB was moved; removes SaveBoard's .pro/.prl sidecars
        stage = None

        provenance = {
            "geometry_source": THERMAL_GEOMETRY_SOURCE,
            "source_geometry_sha256": source_sha,
            "analysis_geometry_sha256": analysis_sha,
            "geometry_counts": {
                kind: len(source_manifest[kind]) for kind in ("zones", "tracks", "pads")
            },
        }
        return (out, provenance) if return_provenance else out
    except ThermalGeometryError:
        raise
    except Exception as exc:                                  # noqa: BLE001
        raise ThermalGeometryError(
            "could not prepare source-only FEM geometry: %s: %s"
            % (type(exc).__name__, exc)) from exc
    finally:
        _remove_temp_board_artifacts(stage)


def _solve_thermal(board_path, currents=None, stackup=None, ambient=50.0,
                   grid_mm=0.3, h_eff=15.0, src_sink_override=None,
                   time_budget_s=None, backend="auto", board_hint=None):
    """Shared SOLVE recipe for the dashboard thermal renders (render_per_layer +
    render_thermal_detail). Reads the per-board config, fills source-declared zones, applies
    the owner-validated production case-cooling model (with the CEC_THERMAL_* env-knob
    overrides), and runs the 2.5D field solver. Returns (res, filled_board_path, cool_label).
    Factored out so the per-layer raster and the full-detail copper map solve ONCE and share
    the exact same field (no double solve, no drift between the two views)."""
    import pcbnew
    cfg_nc, cfg_stack, cfg_ov, cfg_cool = board_thermal_config(
        board_path, board_hint=board_hint)   # read BEFORE _prepare_filled renames
    dielectric = board_dielectric_config(board_path, board_hint=board_hint)
    profile_name = board_fab_profile(board_path, board_hint=board_hint)
    board_path, geometry = _prepare_filled(board_path, return_provenance=True)
    if currents is None:
        currents = cfg_nc if cfg_nc is not None else default_currents(board_path)
    if stackup is None:
        stackup = cfg_stack                              # 12VHPWR -> 2oz/1oz; cable boards -> None (solver default)
    if src_sink_override is None:
        src_sink_override = cfg_ov                        # 12VHPWR -> J3/J4 lanes; cable boards -> auto J_IN/J_OUT

    cool_kw, cool_label = {}, "still-air (no case)"
    if cfg_cool and os.environ.get("CEC_THERMAL_NO_COOLING", "") not in ("1", "true", "True"):
        g_tim = float(os.environ.get("CEC_THERMAL_TIM_WK", cfg_cool["g_chassis_W_per_K"]))
        g_mnt = float(os.environ.get("CEC_THERMAL_MOUNT_WK", cfg_cool["g_mount_W_per_K"]))
        pre = cfg_cool.get("shunt_prefix", "RS").upper()
        _b = pcbnew.LoadBoard(board_path)
        shunt_refs = sorted(fp.GetReference() for fp in _b.GetFootprints()
                            if (fp.GetReference() or "").upper().startswith(pre))
        if shunt_refs and g_tim > 0:
            cool_kw["chassis_refs"] = shunt_refs
            cool_kw["g_chassis_W_per_K"] = g_tim
        if g_mnt > 0:
            cool_kw["g_mount_W_per_K"] = g_mnt
        cool_kw["t_chassis"] = ambient
        cool_label = cfg_cool.get("label", "production case-cooled")
        if g_tim != cfg_cool["g_chassis_W_per_K"] or g_mnt != cfg_cool["g_mount_W_per_K"]:
            cool_label += " [TIM=%.2f mount=%.2f W/K]" % (g_tim, g_mnt)
    res = t2.solve_board_thermal(
        board_path, stackup_oz=stackup, net_currents=currents,
        ambient=ambient, h_eff=h_eff, grid_mm=grid_mm, verbose=False,
        src_sink_override=src_sink_override, time_budget_s=time_budget_s,
        dielectric_mm=dielectric,
        backend=backend,
        gnd_inner_layers=(("In1.Cu", "In4.Cu") if profile_name else
                          ("In1.Cu", "In2.Cu")),
        **cool_kw)
    res.meta.update(geometry)
    return res, board_path, cool_label


def _pil_font(sz, bold=True):
    """A TrueType PIL font that is actually present in the routing container -- matplotlib bundles
    DejaVu, so resolve it through font_manager rather than guessing system paths (load_default is the
    last-ditch fallback so the render never hard-fails on a missing font)."""
    from PIL import ImageFont
    try:
        import matplotlib.font_manager as fm
        fp = fm.findfont(fm.FontProperties(family="DejaVu Sans",
                                           weight=("bold" if bold else "normal")))
        return ImageFont.truetype(fp, sz)
    except Exception:                                        # noqa: BLE001
        try:
            return ImageFont.truetype("DejaVuSans.ttf", sz)
        except Exception:                                    # noqa: BLE001
            return ImageFont.load_default()


def _draw_thermal_detail(board_path, res, out_png, cool_label="still-air (no case)",
                         gate_dt=30.0, cmap_name="turbo", width=1500, title=None):
    """Draw a FULL-DETAIL electro-thermal copper map (the cec_plot.copper_plot style, but coloured by
    the solved temperature field instead of fixed layer colours), given an ALREADY-SOLVED ThermalResult.

    Every copper feature is rendered at REAL geometry -- filled zone pours (with their clearance voids),
    routed tracks at real width, pads, and vias -- and the copper is coloured by the temperature SAMPLED
    (bilinear) from the 2.5D solver's T grid through a perceptual `turbo` map (cool copper = blue/green,
    hot = red; NOT inferno-black-on-dark). F.Cu gets a faint warm wash and B.Cu a faint cool wash so the
    two outer layers stay distinguishable while the temperature still reads through. A vertical colorbar
    (ambient->peak) and a per-net hottest-list legend sit on the right. Returns out_png.

    The temperature field is a SINGLE 2.5D in-plane field (layers are coupled through real vias inside the
    solver), so a given (x,y) has one temperature regardless of layer -- the F/B wash conveys geometry, the
    fill colour conveys heat."""
    import pcbnew
    from PIL import Image, ImageDraw

    b = pcbnew.LoadBoard(board_path)
    bb = b.GetBoardEdgesBoundingBox()
    minx, miny = bb.GetLeft() / 1e6 - 2.0, bb.GetTop() / 1e6 - 2.0
    maxx, maxy = bb.GetRight() / 1e6 + 2.0, bb.GetBottom() / 1e6 + 2.0
    scale = width / max(maxx - minx, 1e-6)
    top, legw = 72, 340
    bw, bh = int((maxx - minx) * scale), int((maxy - miny) * scale)
    W, H = bw + legw, bh + top

    # ---- colormap LUT + scale. CONTRAST-STRETCH the scale to the copper temperature DISTRIBUTION (low/high
    #      percentile) rather than ambient->max: a well-coppered board is near-isothermal (e.g. this eps board
    #      is ~58-62C), so an ambient->peak scale crushes every feature into the same orange and the gradient
    #      is unreadable. Stretching to the copper p2..p98 spreads the real range across turbo so the
    #      GND-plane gradient + hot necks separate. vmin is FLOORED at ambient (so "cool/blue" never claims to
    #      be below ambient) and the absolute ambient + true peak stay in the title/colorbar labels, so the
    #      stretch is a visualization aid, not a misrepresentation. Knobs: CEC_THERMAL_VMIN_PCT / _VMAX_PCT.
    cu_any = res.copper_mask
    _vmin_pct = float(os.environ.get("CEC_THERMAL_VMIN_PCT", "2"))
    _vmax_pct = float(os.environ.get("CEC_THERMAL_VMAX_PCT", "98"))
    if cu_any is not None and cu_any.any():
        cuT = res.T[cu_any]
        vmin = max(float(res.ambient), float(np.percentile(cuT, _vmin_pct)))
        vmax = max(float(np.percentile(cuT, _vmax_pct)), vmin + 1.0)
    else:
        vmin = float(res.ambient)
        vmax = max(float(res.max_T), vmin + 1.0)
    cmap = plt.get_cmap(cmap_name)
    lut = (np.asarray(cmap(np.linspace(0, 1, 256)))[:, :3] * 255.0).astype(np.uint8)

    def tcolor(T):
        f = (float(T) - vmin) / max(vmax - vmin, 1e-6)
        return tuple(int(v) for v in lut[int(np.clip(f, 0.0, 1.0) * 255)])

    # ---- per-pixel temperature field over the board region (bilinear sample of res.T)
    rxmin, rymin, _rxmax, _rymax = res.extent_mm
    gm, (ny, nx) = res.grid_mm, res.T.shape
    px = (np.arange(bw) + 0.5) / scale + minx
    py = (np.arange(bh) + 0.5) / scale + miny
    cols = np.broadcast_to((px[None, :] - rxmin) / gm - 0.5, (bh, bw))
    rows = np.broadcast_to((py[:, None] - rymin) / gm - 0.5, (bh, bw))
    c0 = np.clip(np.floor(cols).astype(int), 0, nx - 1); c1 = np.clip(c0 + 1, 0, nx - 1)
    r0 = np.clip(np.floor(rows).astype(int), 0, ny - 1); r1 = np.clip(r0 + 1, 0, ny - 1)
    fc = np.clip(cols - np.floor(cols), 0.0, 1.0); fr = np.clip(rows - np.floor(rows), 0.0, 1.0)
    T = res.T
    Tf = (T[r0, c0] * (1 - fr) * (1 - fc) + T[r0, c1] * (1 - fr) * fc +
          T[r1, c0] * fr * (1 - fc) + T[r1, c1] * fr * fc)
    tn = np.clip((Tf - vmin) / max(vmax - vmin, 1e-6), 0.0, 1.0)
    field_rgb = lut[(tn * 255).astype(np.uint8)]              # (bh, bw, 3)

    # ---- rasterize each copper layer's geometry into a board-sized mask (no top offset)
    def Xs(x): return (x / 1e6 - minx) * scale
    def Ys(y): return (y / 1e6 - miny) * scale

    CU = [pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu]
    masks = {lid: Image.new("L", (bw, bh), 0) for lid in CU}
    md = {lid: ImageDraw.Draw(masks[lid]) for lid in CU}

    for z in b.Zones():                                       # filled pours (honour clearance voids)
        for lid in z.GetLayerSet().Seq():
            if lid not in md:
                continue
            poly = z.GetFilledPolysList(lid)
            for oi in range(poly.OutlineCount()):
                ol = poly.Outline(oi)
                pts = [(Xs(ol.CPoint(k).x), Ys(ol.CPoint(k).y)) for k in range(ol.PointCount())]
                if len(pts) >= 3:
                    md[lid].polygon(pts, fill=255)
                try:
                    for hi in range(poly.HoleCount(oi)):
                        hl = poly.Hole(oi, hi)
                        hp = [(Xs(hl.CPoint(k).x), Ys(hl.CPoint(k).y)) for k in range(hl.PointCount())]
                        if len(hp) >= 3:
                            md[lid].polygon(hp, fill=0)
                except Exception:                            # noqa: BLE001 -- holes are a refinement, never block
                    pass

    for tk in b.GetTracks():                                  # routed tracks at real width + arcs
        tp = tk.Type()
        if tp == pcbnew.PCB_VIA_T:
            continue
        lid = tk.GetLayer()
        if lid not in md:
            continue
        w = max(1, int(round(tk.GetWidth() / 1e6 * scale)))
        if tp == pcbnew.PCB_ARC_T:
            try:
                s, mid, e = tk.GetStart(), tk.GetMid(), tk.GetEnd()
                ch = t2._arc_chords(s.x / 1e6, s.y / 1e6, mid.x / 1e6, mid.y / 1e6, e.x / 1e6, e.y / 1e6)
            except Exception:                                # noqa: BLE001
                s, e = tk.GetStart(), tk.GetEnd()
                ch = [(s.x / 1e6, s.y / 1e6), (e.x / 1e6, e.y / 1e6)]
            pts = [((x - minx) * scale, (y - miny) * scale) for (x, y) in ch]
            if len(pts) >= 2:
                md[lid].line(pts, fill=255, width=w, joint="curve")
        else:
            s, e = tk.GetStart(), tk.GetEnd()
            a, c = (Xs(s.x), Ys(s.y)), (Xs(e.x), Ys(e.y))
            md[lid].line([a, c], fill=255, width=w)
            r = w / 2.0                                       # round the trace ends so widths read true
            for (xx, yy) in (a, c):
                md[lid].ellipse([xx - r, yy - r, xx + r, yy + r], fill=255)

    for fp in b.GetFootprints():                              # pads
        for pad in fp.Pads():
            ls = pad.GetLayerSet()
            cx, cy = Xs(pad.GetPosition().x), Ys(pad.GetPosition().y)
            sz = pad.GetSize()
            hw, hh = sz.x / 1e6 * scale / 2.0, sz.y / 1e6 * scale / 2.0
            for lid in CU:
                if ls.Contains(lid):
                    md[lid].rectangle([cx - hw, cy - hh, cx + hw, cy + hh], fill=255)

    Marr = {lid: (np.asarray(masks[lid]) > 0) for lid in CU}
    union = np.zeros((bh, bw), dtype=bool)
    for lid in CU:
        union |= Marr[lid]

    # ---- composite: dark substrate + a PURE temperature fill on every copper pixel. We deliberately do NOT
    #      hue-wash the fill per layer: turbo already uses blue=cool / red=hot, so a blue/red layer wash would
    #      be misread as temperature. Layer identity is carried by the pour EDGE colour instead (drawn below).
    comp = np.empty((bh, bw, 3), np.uint8)
    comp[:] = np.array([13, 17, 23], np.uint8)
    comp[union] = field_rgb[union]

    # ---- canvas + overlay vectors (board outline, pour edges, vias) drawn with the top-offset transform
    canvas = Image.new("RGB", (W, H), (16, 20, 24))
    canvas.paste(Image.fromarray(comp), (0, top))
    g = ImageDraw.Draw(canvas)

    def X(x): return (x / 1e6 - minx) * scale
    def Y(y): return (y / 1e6 - miny) * scale + top
    def P(pt): return (X(pt.x), Y(pt.y))

    for s in b.GetDrawings():                                 # board outline
        if s.GetLayer() != pcbnew.Edge_Cuts:
            continue
        try:
            if s.GetShape() == pcbnew.SHAPE_T_RECT:
                a, c = P(s.GetStart()), P(s.GetEnd())
                g.rectangle([min(a[0], c[0]), min(a[1], c[1]), max(a[0], c[0]), max(a[1], c[1])],
                            outline=(128, 203, 196), width=2)
            else:
                g.line([P(s.GetStart()), P(s.GetEnd())], fill=(128, 203, 196), width=2)
        except Exception:                                    # noqa: BLE001
            pass

    edge_col = {pcbnew.F_Cu: (255, 120, 120), pcbnew.B_Cu: (120, 160, 255)}  # outer pour edges -> lanes pop
    for z in b.Zones():
        for lid in z.GetLayerSet().Seq():
            if lid not in edge_col:
                continue
            poly = z.GetFilledPolysList(lid)
            for oi in range(poly.OutlineCount()):
                ol = poly.Outline(oi)
                pts = [P(ol.CPoint(k)) for k in range(ol.PointCount())]
                if len(pts) >= 2:
                    g.line(pts + [pts[0]], fill=edge_col[lid], width=2)

    for tk in b.GetTracks():                                  # vias on top
        if tk.Type() != pcbnew.PCB_VIA_T:
            continue
        try:
            dia = tk.GetWidth(tk.TopLayer()) / 1e6
        except Exception:                                    # noqa: BLE001
            dia = 0.6
        c = P(tk.GetPosition()); r = dia * scale / 2.0
        g.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(26, 26, 30), outline=(96, 100, 108))

    # ---- title / verdict
    dt = res.max_T - res.ambient
    verdict = "PASS" if dt <= gate_dt else "FAIL"
    vcol = (165, 214, 167) if verdict == "PASS" else (239, 154, 154)
    g.text((14, 9), title or os.path.basename(out_png), fill=(236, 239, 241), font=_pil_font(22))
    g.text((14, 42),
           f"electro-thermal copper map   peak {res.max_T:.1f}°C   dT {dt:.1f}°C "
           f"(gate {gate_dt:.0f})   [{verdict}]   {cool_label}",
           fill=vcol, font=_pil_font(15, False))

    # ---- colorbar (vertical, ambient->peak)
    lx = bw + 18
    cb_x, cb_y, cb_w, cb_h = lx, top + 34, 26, int(bh * 0.46)
    for i in range(max(cb_h, 1)):
        col = tuple(int(v) for v in lut[int((1 - i / max(cb_h - 1, 1)) * 255)])
        g.line([(cb_x, cb_y + i), (cb_x + cb_w, cb_y + i)], fill=col)
    g.rectangle([cb_x, cb_y, cb_x + cb_w, cb_y + cb_h], outline=(120, 130, 140))
    fsmall = _pil_font(13, False)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        tval = vmin + frac * (vmax - vmin)
        yy = cb_y + int((1 - frac) * cb_h)
        g.line([(cb_x + cb_w, yy), (cb_x + cb_w + 5, yy)], fill=(150, 160, 170))
        g.text((cb_x + cb_w + 9, yy - 8), f"{tval:.0f}", fill=(207, 216, 220), font=fsmall)
    g.text((cb_x, cb_y - 24), "copper T (°C)", fill=(207, 216, 220), font=_pil_font(14))
    sub = f"ambient {res.ambient:.0f}°C  ·  peak {res.max_T:.1f}°C"
    if vmin > res.ambient + 0.5 or vmax < res.max_T - 0.5:
        sub += f"  ·  scale {vmin:.0f}–{vmax:.0f} (contrast)"
    g.text((cb_x, cb_y + cb_h + 7), sub, fill=(144, 164, 174), font=_pil_font(11, False))

    # ---- per-net hottest legend (filters out unrouted "unconnected-..." pseudo-nets)
    nets = sorted(((n, v) for n, v in res.per_net_maxT.items() if not n.startswith("unconnected-")),
                  key=lambda kv: -kv[1])
    ny0 = cb_y + cb_h + 38
    g.text((lx, ny0 - 22), "hottest nets (max °C)", fill=(207, 216, 220), font=_pil_font(14))
    for i, (n, v) in enumerate(nets[:16]):
        yy = ny0 + i * 19
        g.rectangle([lx, yy + 2, lx + 15, yy + 15], fill=tcolor(v), outline=(60, 60, 60))
        nm = n if len(n) <= 27 else n[:25] + "…"
        g.text((lx + 21, yy), nm, fill=(207, 216, 220), font=fsmall)
        g.text((W - 56, yy), f"{v:.1f}", fill=(255, 204, 128), font=fsmall)

    ky = ny0 + min(len(nets), 16) * 19 + 16
    g.text((lx, ky), "pour edge:", fill=(207, 216, 220), font=fsmall)
    g.rectangle([lx + 86, ky + 1, lx + 100, ky + 14], fill=(235, 70, 70), outline=(60, 60, 60))
    g.text((lx + 104, ky), "F.Cu", fill=(207, 216, 220), font=fsmall)
    g.rectangle([lx + 156, ky + 1, lx + 170, ky + 14], fill=(70, 120, 235), outline=(60, 60, 60))
    g.text((lx + 174, ky), "B.Cu", fill=(207, 216, 220), font=fsmall)

    canvas.save(out_png)
    return out_png


# ---------------------------------------------------------------------------
#  BLENDED detail render -- the "between" view the owner asked for.
#
#  It marries the two good reference renders:
#    (1) eps-thermal-detail.png  (render_thermal_detail / _draw_thermal_detail):
#        a SMOOTH continuous field across the whole board -> heat pooling is
#        instantly readable, but the copper geometry is washed out.
#    (2) eps-render-thermal.png  (the standalone build/render-thermal.py):
#        TRANSLUCENT STACKED copper layers (all enabled layers visible at once,
#        overlaps show through) with distinct pad/trace/via/pour treatments and
#        PROMINENT via rings -- crisp copper structure, but heat reads only as a
#        per-feature tint, not a field.
#
#  The blend draws the SMOOTH field as a (slightly dimmed) BASE LAYER over the
#  whole board, then composites the translucent stacked copper -- given a small
#  brightness lift so it pops against the same-hue base -- crisply ON TOP, with
#  prominent vias / pad outlines / per-layer pour edges last. Neither washes the
#  other out: the field shows through the translucent pours while the structure
#  (which layers are present, where they overlap, every via) stays legible.
#
#  The SAME routine renders the CURRENT TWIN (mode="current"): identical geometry
#  / layers / features / vias, but every copper region is coloured by the CURRENT
#  of its NET (default_currents) through a current LUT + legend instead of the
#  temperature field -- a cross-check (heat should track current).
# ---------------------------------------------------------------------------
_BLEND_STACK_BU = ["B.Cu", "In4.Cu", "In3.Cu", "In2.Cu", "In1.Cu", "F.Cu"]
_BLEND_LEDGE = {"F.Cu": (255, 96, 72), "In1.Cu": (90, 214, 120),     # pour-edge identity colour
                "In2.Cu": (214, 110, 236), "In3.Cu": (246, 181, 72),
                "In4.Cu": (72, 210, 202), "B.Cu": (84, 150, 255)}
_BLEND_LTINT = {"F.Cu": (255, 138, 120), "In1.Cu": (150, 238, 175),  # soft per-layer fill tint
                "In2.Cu": (226, 150, 240), "In3.Cu": (250, 205, 120),
                "In4.Cu": (132, 232, 224), "B.Cu": (130, 182, 255)}


def _blend_thermal_verdict(res, gate_dt):
    """Fail the rendered verdict closed when requested current was not injected."""
    dt = res.max_T - res.ambient
    incomplete = bool((getattr(res, "nets_dropped", None) or {})
                      or (getattr(res, "nets_absent", None) or {}))
    return ("PASS" if dt <= gate_dt and not incomplete else "FAIL"), incomplete


def _draw_detail_blend(board_path, res, out_png, mode="thermal", currents=None,
                       cool_label="still-air (no case)", gate_dt=30.0,
                       cmap_name="turbo", final_board_w=1180, ss=2, title=None):
    """Draw the blended smooth-field + translucent-stacked-copper detail map for an ALREADY-SOLVED board.

    mode="thermal"  -> colour = the solved temperature field (smooth spatial base + copper coloured by the
                       field it sits in); contrast-stretched copper percentile scale + hottest-net (°C) legend.
    mode="current"  -> colour = per-net CURRENT (from `currents`, default default_currents): the base field is
                       the dominant (max) net current per pixel, each stacked copper layer is coloured by ITS
                       OWN net's current, 0..max(A) scale + per-net (A) legend. Same geometry/vias as thermal.

    Drawn at ss x supersample then downsampled LANCZOS for crisp edges. Returns out_png."""
    import pcbnew
    from PIL import Image, ImageDraw

    b = pcbnew.LoadBoard(board_path)
    STD = t2.STD_CU_LAYERS                       # lid -> standard copper-layer name
    STD_BY_NAME = {v: k for k, v in STD.items()}
    blend_stack = [name for name in _BLEND_STACK_BU
                   if name in STD_BY_NAME and b.IsLayerEnabled(STD_BY_NAME[name])]

    # ---- geometry transform (working == FINAL * ss) ------------------------
    bb = b.GetBoardEdgesBoundingBox()
    minx, miny = bb.GetLeft() / 1e6 - 2.0, bb.GetTop() / 1e6 - 2.0
    maxx, maxy = bb.GetRight() / 1e6 + 2.0, bb.GetBottom() / 1e6 + 2.0
    bw_mm, bh_mm = maxx - minx, maxy - miny
    scale = final_board_w * ss / bw_mm                       # working px per mm
    bw, bh = int(round(bw_mm * scale)), int(round(bh_mm * scale))
    TITLE_H, LEG_W = 96, 372
    top, legw = TITLE_H * ss, LEG_W * ss

    def Xb(x_nm): return (x_nm / 1e6 - minx) * scale
    def Yb(y_nm): return (y_nm / 1e6 - miny) * scale

    # ---- per-net current lookup (current mode) -----------------------------
    is_cur = (mode == "current")
    if is_cur and currents is None:
        # The current panel is a cross-check of THIS solved field, so its
        # labels/colors must use the exact scenario sent to the solver. Falling
        # back to basename-derived defaults after the board was renamed to a
        # temp path previously mislabeled ATX as balanced EPS.
        currents = dict(getattr(res, "nets_requested", None) or {})
        if not currents:
            cfg_nc, _stk, _ss, _cool = board_thermal_config(board_path)
            currents = cfg_nc if cfg_nc else default_currents(board_path)
    currents = currents or {}

    def cur_of(net):
        if net in currents:
            return float(currents[net])
        n2 = (net or "").lstrip("/")
        for k, v in currents.items():
            if k.lstrip("/") == n2:
                return float(v)
        return 0.0

    cmap = plt.get_cmap(cmap_name)
    lut = (np.asarray(cmap(np.linspace(0, 1, 256)))[:, :3] * 255.0).astype(np.uint8)

    def colorize(arr, vlo, vhi):
        f = np.clip((arr - vlo) / max(vhi - vlo, 1e-6), 0.0, 1.0)
        return lut[(f * 255).astype(np.uint8)].astype(np.float32)

    def vcolor(v, vlo, vhi):
        f = (float(v) - vlo) / max(vhi - vlo, 1e-6)
        return tuple(int(x) for x in lut[int(np.clip(f, 0.0, 1.0) * 255)])

    # ---- value scale -------------------------------------------------------
    if is_cur:
        vlo, vhi = 0.0, max([max(currents.values()) if currents else 1.0, 1.0])
    else:
        cu_any = res.copper_mask
        _vmin_pct = float(os.environ.get("CEC_THERMAL_VMIN_PCT", "2"))
        _vmax_pct = float(os.environ.get("CEC_THERMAL_VMAX_PCT", "98"))
        if cu_any is not None and cu_any.any():
            cuT = res.T[cu_any]
            vlo = max(float(res.ambient), float(np.percentile(cuT, _vmin_pct)))
            vhi = max(float(np.percentile(cuT, _vmax_pct)), vlo + 1.0)
        else:
            vlo, vhi = float(res.ambient), max(float(res.max_T), float(res.ambient) + 1.0)

    # ---- the SMOOTH base field (thermal: bilinear T everywhere; current: dominant net current) --
    if not is_cur:
        rxmin, rymin, _rxmax, _rymax = res.extent_mm
        gm, (ny, nx) = res.grid_mm, res.T.shape
        px = (np.arange(bw) + 0.5) / scale + minx
        py = (np.arange(bh) + 0.5) / scale + miny
        cols = np.broadcast_to((px[None, :] - rxmin) / gm - 0.5, (bh, bw))
        rows = np.broadcast_to((py[:, None] - rymin) / gm - 0.5, (bh, bw))
        c0 = np.clip(np.floor(cols).astype(int), 0, nx - 1); c1 = np.clip(c0 + 1, 0, nx - 1)
        r0 = np.clip(np.floor(rows).astype(int), 0, ny - 1); r1 = np.clip(r0 + 1, 0, ny - 1)
        fc = np.clip(cols - np.floor(cols), 0.0, 1.0); fr = np.clip(rows - np.floor(rows), 0.0, 1.0)
        T = res.T
        Tf = (T[r0, c0] * (1 - fr) * (1 - fc) + T[r0, c1] * (1 - fr) * fc +
              T[r1, c0] * fr * (1 - fc) + T[r1, c1] * fr * fc)
        field_rgb = colorize(Tf, vlo, vhi)                   # (bh, bw, 3) -- the per-pixel spatial field

    # ---- rasterise per-(layer, feature-type) UNION masks (alpha) + (current) per-layer value masks --
    masks = {std: {"pour": Image.new("L", (bw, bh), 0),
                   "trace": Image.new("L", (bw, bh), 0),
                   "pad": Image.new("L", (bw, bh), 0)} for std in STD.values()}
    md = {std: {k: ImageDraw.Draw(v) for k, v in masks[std].items()} for std in masks}
    pour_edges = {std: [] for std in STD.values()}
    cur_lv = {std: {} for std in STD.values()}               # std -> {current_value: (Image, Draw)}

    def cur_draw(std, net):
        if not is_cur:
            return None
        cv = cur_of(net)
        d = cur_lv[std]
        if cv not in d:
            img = Image.new("L", (bw, bh), 0)
            d[cv] = (img, ImageDraw.Draw(img))
        return d[cv][1]

    # filled pours (honour clearance voids = holes)
    for z in b.Zones():
        net = z.GetNetname()
        for lid in z.GetLayerSet().Seq():
            std = STD.get(lid)
            if std is None:
                continue
            cd = cur_draw(std, net)
            poly = z.GetFilledPolysList(lid)
            for oi in range(poly.OutlineCount()):
                ol = poly.Outline(oi)
                pts = [(Xb(ol.CPoint(k).x), Yb(ol.CPoint(k).y)) for k in range(ol.PointCount())]
                if len(pts) >= 3:
                    md[std]["pour"].polygon(pts, fill=255)
                    if cd is not None:
                        cd.polygon(pts, fill=255)
                    pour_edges[std].append(pts)
                try:
                    for hi in range(poly.HoleCount(oi)):
                        hl = poly.Hole(oi, hi)
                        hp = [(Xb(hl.CPoint(k).x), Yb(hl.CPoint(k).y)) for k in range(hl.PointCount())]
                        if len(hp) >= 3:
                            md[std]["pour"].polygon(hp, fill=0)
                            if cd is not None:
                                cd.polygon(hp, fill=0)
                            pour_edges[std].append(hp)
                except Exception:                            # noqa: BLE001
                    pass

    # routed tracks at real width (+ arcs), rounded ends; vias collected for the top overlay
    vias = []
    for tk in b.GetTracks():
        tp = tk.Type()
        if tp == pcbnew.PCB_VIA_T:
            try:
                dia = tk.GetWidth(tk.TopLayer()) / 1e6
            except Exception:                                # noqa: BLE001
                dia = 0.6
            try:
                drill = tk.GetDrill() / 1e6
            except Exception:                                # noqa: BLE001
                drill = dia * 0.5
            vias.append((Xb(tk.GetPosition().x), Yb(tk.GetPosition().y),
                         dia * scale / 2.0, max(drill, 0.2) * scale / 2.0))
            continue
        std = STD.get(tk.GetLayer())
        if std is None:
            continue
        try:
            net = tk.GetNetname()
        except Exception:                                    # noqa: BLE001
            net = ""
        cd = cur_draw(std, net)
        w = max(1, int(round(tk.GetWidth() / 1e6 * scale)))
        if tp == pcbnew.PCB_ARC_T:
            try:
                s, m, e = tk.GetStart(), tk.GetMid(), tk.GetEnd()
                ch = t2._arc_chords(s.x / 1e6, s.y / 1e6, m.x / 1e6, m.y / 1e6, e.x / 1e6, e.y / 1e6)
                pts = [((x - minx) * scale, (y - miny) * scale) for (x, y) in ch]
            except Exception:                                # noqa: BLE001
                s, e = tk.GetStart(), tk.GetEnd()
                pts = [(Xb(s.x), Yb(s.y)), (Xb(e.x), Yb(e.y))]
            if len(pts) >= 2:
                md[std]["trace"].line(pts, fill=255, width=w, joint="curve")
                if cd is not None:
                    cd.line(pts, fill=255, width=w, joint="curve")
        else:
            s, e = tk.GetStart(), tk.GetEnd()
            a, c = (Xb(s.x), Yb(s.y)), (Xb(e.x), Yb(e.y))
            md[std]["trace"].line([a, c], fill=255, width=w)
            if cd is not None:
                cd.line([a, c], fill=255, width=w)
            r = w / 2.0
            for (xx, yy) in (a, c):
                md[std]["trace"].ellipse([xx - r, yy - r, xx + r, yy + r], fill=255)
                if cd is not None:
                    cd.ellipse([xx - r, yy - r, xx + r, yy + r], fill=255)

    # pads (real shape: rect / roundrect -> rect, circle / oval -> ellipse)
    pad_outlines = []
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            ls = pad.GetLayerSet()
            try:
                net = pad.GetNetname()
            except Exception:                                # noqa: BLE001
                net = ""
            cx, cy = Xb(pad.GetPosition().x), Yb(pad.GetPosition().y)
            sz = pad.GetSize()
            hw, hh = sz.x / 1e6 * scale / 2.0, sz.y / 1e6 * scale / 2.0
            try:
                shp = pad.GetShape()
                is_round = shp in (pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL)
            except Exception:                                # noqa: BLE001
                is_round = False
            box = [cx - hw, cy - hh, cx + hw, cy + hh]
            for lid in STD:
                if ls.Contains(lid):
                    std = STD[lid]
                    cd = cur_draw(std, net)
                    if is_round:
                        md[std]["pad"].ellipse(box, fill=255)
                        if cd is not None:
                            cd.ellipse(box, fill=255)
                    else:
                        md[std]["pad"].rectangle(box, fill=255)
                        if cd is not None:
                            cd.rectangle(box, fill=255)
            pad_outlines.append((box, is_round))

    # ---- per-layer VALUE colour arrays -------------------------------------
    #   thermal: every layer uses the spatial field at each pixel.
    #   current: each layer is coloured by its OWN net current; the base is the dominant (max) current.
    layer_color = {}
    if is_cur:
        base_cur = np.zeros((bh, bw), np.float32)
        for std in STD.values():
            cf = np.zeros((bh, bw), np.float32)
            for cv in sorted(cur_lv[std]):                   # ascending -> higher current overwrites (== max)
                m = np.asarray(cur_lv[std][cv][0]) > 127
                cf[m] = cv
            layer_color[std] = colorize(cf, vlo, vhi)
            base_cur = np.maximum(base_cur, cf)
        base_rgb = colorize(base_cur, vlo, vhi)
    else:
        for std in STD.values():
            layer_color[std] = field_rgb
        base_rgb = field_rgb

    # ---- COMPOSITE: dimmed smooth base + translucent stacked copper (lifted so it pops) ----
    # alphas: pours stay see-through so the base field reads through them; traces/pads near-opaque.
    if is_cur:
        A_POUR_OUTER, A_POUR_INNER, A_TRACE, A_PAD = 0.60, 0.32, 0.90, 0.97
        BASE_DIM, COPPER_GAIN, K_TINT = 0.66, 1.05, 0.14
    else:
        A_POUR_OUTER, A_POUR_INNER, A_TRACE, A_PAD = 0.40, 0.30, 0.86, 0.97
        BASE_DIM, COPPER_GAIN, K_TINT = 0.66, 1.12, 0.20

    canvas_f = base_rgb * BASE_DIM                           # the smooth field, dimmed -> copper has headroom to pop
    for std in blend_stack:
        m = masks[std]
        pour = np.asarray(m["pour"]) > 127
        trace = np.asarray(m["trace"]) > 127
        pad = np.asarray(m["pad"]) > 127
        a_pour = A_POUR_OUTER if std in ("F.Cu", "B.Cu") else A_POUR_INNER
        alpha = np.zeros((bh, bw), np.float32)
        alpha[pour] = a_pour
        alpha = np.maximum(alpha, trace.astype(np.float32) * A_TRACE)
        alpha = np.maximum(alpha, pad.astype(np.float32) * A_PAD)
        tint = np.array(_BLEND_LTINT[std], np.float32)
        lc = np.clip(layer_color[std] * COPPER_GAIN, 0, 255)
        layer_rgb = lc * (1.0 - K_TINT) + tint[None, None, :] * K_TINT
        a3 = alpha[..., None]
        canvas_f = layer_rgb * a3 + canvas_f * (1.0 - a3)
    board_img = Image.fromarray(np.clip(canvas_f, 0, 255).astype(np.uint8), "RGB")

    # ---- full canvas + vector overlays -------------------------------------
    BG = (15, 18, 24)
    W = bw + legw
    nets_T = sorted(((n, v) for n, v in res.per_net_maxT.items() if not n.startswith("unconnected-")),
                    key=lambda kv: -kv[1])
    legend_nets = (sorted(currents.items(), key=lambda kv: -kv[1]) if is_cur else nets_T)
    NSHOW = min(len(legend_nets), 13)
    cbh = int(bh * 0.32)
    legend_h = 14 * ss + cbh + (250 + 20 * NSHOW) * ss
    H = max(bh, legend_h) + top + 22 * ss

    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(board_img, (0, top))
    g = ImageDraw.Draw(canvas, "RGBA")

    def X(x_nm): return (x_nm / 1e6 - minx) * scale
    def Y(y_nm): return (y_nm / 1e6 - miny) * scale + top
    def P(pt): return (X(pt.x), Y(pt.y))

    for s in b.GetDrawings():                                 # board outline
        if s.GetLayer() != pcbnew.Edge_Cuts:
            continue
        try:
            if s.GetShape() == pcbnew.SHAPE_T_RECT:
                a, c = P(s.GetStart()), P(s.GetEnd())
                g.rectangle([min(a[0], c[0]), min(a[1], c[1]), max(a[0], c[0]), max(a[1], c[1])],
                            outline=(150, 214, 208), width=2 * ss)
            else:
                g.line([P(s.GetStart()), P(s.GetEnd())], fill=(150, 214, 208), width=2 * ss)
        except Exception:                                    # noqa: BLE001
            pass

    for std in blend_stack:                                   # per-layer pour EDGES (layer identity)
        outer = std in ("F.Cu", "B.Cu")
        col = _BLEND_LEDGE[std] + (235 if outer else 150,)
        ew = (ss + 1) if outer else max(1, ss)
        for pts in pour_edges[std]:
            pp = [(x, y + top) for (x, y) in pts]
            if len(pp) >= 2:
                g.line(pp + [pp[0]], fill=col, width=ew)

    for box, is_round in pad_outlines:                        # pad terminal outlines (gold ring)
        bx = [box[0], box[1] + top, box[2], box[3] + top]
        if is_round:
            g.ellipse(bx, outline=(255, 218, 130, 255), width=ss + 1)
        else:
            g.rectangle(bx, outline=(255, 218, 130, 255), width=ss)

    for (vx, vy, rad, drill) in vias:                         # PROMINENT via rings, drawn LAST
        cx, cy = vx, vy + top
        rad = max(rad, 2.0 * ss)
        g.ellipse([cx - rad - ss, cy - rad - ss, cx + rad + ss, cy + rad + ss], fill=(20, 22, 28, 235))
        g.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(245, 248, 252), width=max(2, ss + 1))
        dr = max(drill, 1.0 * ss)
        g.ellipse([cx - dr, cy - dr, cx + dr, cy + dr], fill=(40, 44, 52, 255))

    # ---- title -------------------------------------------------------------
    dt = res.max_T - res.ambient
    verdict, injection_incomplete = _blend_thermal_verdict(res, gate_dt)
    base_title = title or os.path.basename(board_path)
    if is_cur:
        g.text((14 * ss, 10 * ss),
               "%s  -  per-net CURRENT cross-check (heat should track current)" % base_title,
               fill=(238, 241, 244), font=_pil_font(22 * ss))
        topcur = "  ·  ".join("%s %.1fA" % (k.lstrip("/"), v)
                              for k, v in legend_nets[:4])
        g.text((14 * ss, 44 * ss),
               "colour = current carried by each net's copper   ·   %s" % topcur,
               fill=(180, 196, 208), font=_pil_font(15 * ss, False))
        g.text((14 * ss, 68 * ss),
               "smooth dominant-current base + translucent stacked copper (each layer = its own net's current)   ·   "
               "twin of the temperature map -- compare the hot regions",
               fill=(150, 165, 178), font=_pil_font(13 * ss, False))
    else:
        vcol = (165, 220, 167) if verdict == "PASS" else (239, 154, 154)
        g.text((14 * ss, 10 * ss),
               "%s  -  electro-thermal copper map (smooth field + detailed copper)" % base_title,
               fill=(238, 241, 244), font=_pil_font(22 * ss))
        g.text((14 * ss, 44 * ss),
               "colour = local copper temperature (turbo)   ·   peak %.1f°C   dT %.1f°C (gate %d)   [%s]%s   %s"
               % (res.max_T, dt, gate_dt, verdict,
                  "  INJECTION INCOMPLETE" if injection_incomplete else "", cool_label),
               fill=vcol, font=_pil_font(15 * ss, False))
        g.text((14 * ss, 68 * ss),
               "smooth field base + %d copper layers drawn translucent & stacked (overlaps show through)   ·   "
               "ambient %.0f°C   ·   grid %.2f mm"
               % (len(blend_stack), res.ambient, res.grid_mm),
               fill=(150, 165, 178), font=_pil_font(13 * ss, False))

    # ---- legend column -----------------------------------------------------
    lx = bw + 20 * ss
    fsm = _pil_font(13 * ss, False)
    fmd = _pil_font(14 * ss)
    cby = top + 14 * ss
    cbw = 30 * ss
    for i in range(cbh):                                      # colorbar (top = high)
        col = tuple(int(v) for v in lut[int((1 - i / max(cbh - 1, 1)) * 255)])
        g.line([(lx, cby + i), (lx + cbw, cby + i)], fill=col)
    g.rectangle([lx, cby, lx + cbw, cby + cbh], outline=(120, 132, 142), width=ss)
    cb_label = "net current (A)" if is_cur else "copper T (°C)"
    g.text((lx, cby - 22 * ss), cb_label, fill=(210, 218, 222), font=fmd)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        tval = vlo + frac * (vhi - vlo)
        yy = cby + int((1 - frac) * cbh)
        g.line([(lx + cbw, yy), (lx + cbw + 6 * ss, yy)], fill=(150, 162, 172), width=ss)
        g.text((lx + cbw + 10 * ss, yy - 8 * ss), "%.1f" % tval, fill=(208, 217, 220), font=fsm)
    if is_cur:
        g.text((lx, cby + cbh + 8 * ss), "scale 0–%.1f A" % vhi, fill=(146, 166, 176), font=fsm)
        g.text((lx, cby + cbh + 26 * ss),
               "same net-current scenario used by FEM", fill=(146, 166, 176), font=fsm)
    else:
        g.text((lx, cby + cbh + 8 * ss),
               "scale %.1f–%.1f (contrast-stretched)" % (vlo, vhi), fill=(146, 166, 176), font=fsm)
        g.text((lx, cby + cbh + 26 * ss),
               "ambient %.0f°C  ·  TRUE peak %.1f°C" % (res.ambient, res.max_T), fill=(146, 166, 176), font=fsm)

    # feature-type legend
    fy = cby + cbh + 58 * ss
    g.text((lx, fy), "FEATURE TYPES", fill=(210, 218, 222), font=fmd)
    fy += 24 * ss
    sw = 26 * ss
    demoV = vlo + 0.62 * (vhi - vlo)
    fc_demo = vcolor(demoV, vlo, vhi)
    g.rectangle([lx, fy, lx + sw, fy + 16 * ss], fill=fc_demo + (int(255 * A_POUR_OUTER),))
    g.text((lx + sw + 10 * ss, fy), "filled pour (translucent field)", fill=(208, 217, 220), font=fsm)
    fy += 24 * ss
    g.line([(lx + 2 * ss, fy + 8 * ss), (lx + sw - 2 * ss, fy + 8 * ss)], fill=fc_demo, width=6 * ss)
    g.text((lx + sw + 10 * ss, fy), "routed trace (real width)", fill=(208, 217, 220), font=fsm)
    fy += 24 * ss
    g.rectangle([lx + 3 * ss, fy + 1 * ss, lx + sw - 3 * ss, fy + 15 * ss],
                fill=fc_demo + (245,), outline=(255, 224, 150), width=max(1, ss))
    g.text((lx + sw + 10 * ss, fy), "pad / terminal", fill=(208, 217, 220), font=fsm)
    fy += 24 * ss
    vcx, vcy = lx + sw // 2, fy + 8 * ss
    vr = 8 * ss
    g.ellipse([vcx - vr, vcy - vr, vcx + vr, vcy + vr], outline=(245, 248, 252), width=max(2, ss + 1))
    g.ellipse([vcx - 3 * ss, vcy - 3 * ss, vcx + 3 * ss, vcy + 3 * ss], fill=(40, 44, 52))
    g.text((lx + sw + 10 * ss, fy), "via (ringed, layer-spanning)", fill=(208, 217, 220), font=fsm)

    # layer legend (identity edge colours)
    fy += 38 * ss
    g.text((lx, fy), "COPPER LAYERS (edge = layer)", fill=(210, 218, 222), font=fmd)
    fy += 24 * ss
    for std in reversed(blend_stack):
        col = _BLEND_LEDGE[std]
        g.rectangle([lx, fy + 2 * ss, lx + sw, fy + 15 * ss],
                    fill=col + (int(255 * 0.55),), outline=col, width=max(1, ss))
        lid = STD_BY_NAME.get(std)
        rn = b.GetLayerName(lid) if lid is not None else std
        lab = "%s  (%s)" % (std, rn) if rn and rn != std else std
        g.text((lx + sw + 10 * ss, fy), lab, fill=(208, 217, 220), font=fsm)
        fy += 22 * ss

    # per-net hottest / highest-current legend
    fy += 16 * ss
    g.text((lx, fy), ("HIGHEST-CURRENT NETS (A)" if is_cur else "HOTTEST NETS (max °C)"),
           fill=(210, 218, 222), font=fmd)
    fy += 24 * ss
    for (n, v) in legend_nets[:NSHOW]:
        g.rectangle([lx, fy + 2 * ss, lx + 16 * ss, fy + 15 * ss],
                    fill=vcolor(v, vlo, vhi), outline=(70, 70, 70))
        nm = n if len(n) <= 24 else n[:22] + "…"
        g.text((lx + 22 * ss, fy), nm, fill=(208, 217, 220), font=fsm)
        g.text((W - 56 * ss, fy), ("%.1f" % v), fill=(255, 206, 130), font=fsm)
        fy += 20 * ss

    final = canvas.resize((W // ss, H // ss), Image.LANCZOS)
    final.save(out_png)
    return out_png


def render_detail_blend(board_path, out_png, mode="thermal", currents=None, stackup=None,
                        ambient=50.0, grid_mm=0.3, h_eff=15.0, gate_dt=30.0,
                        src_sink_override=None, cmap_name="turbo", final_board_w=1180):
    """Solve + draw the blended detail map (mode='thermal') or its current twin (mode='current').
    Returns a summary dict. The current twin reuses the exact currents recorded by the solve."""
    res, fpath, cool_label = _solve_thermal(board_path, currents=currents, stackup=stackup,
                                            ambient=ambient, grid_mm=grid_mm, h_eff=h_eff,
                                            src_sink_override=src_sink_override)
    leg_cur = (dict(res.nets_requested) if mode == "current" else None)
    _draw_detail_blend(fpath, res, out_png, mode=mode, currents=leg_cur, cool_label=cool_label,
                       gate_dt=gate_dt, cmap_name=cmap_name, final_board_w=final_board_w,
                       title=os.path.basename(board_path))
    dt_pass = (res.max_T - res.ambient) <= gate_dt
    out = {
        "ok": True, "mode": mode, "max_T": round(res.max_T, 2), "ambient": res.ambient,
        "dT": round(res.max_T - res.ambient, 2), "verdict": "PASS" if dt_pass else "FAIL",
        "cooling": cool_label, "grid_mm": res.grid_mm, "png": out_png,
        "geometry_source": res.meta.get("geometry_source"),
        "source_geometry_sha256": res.meta.get("source_geometry_sha256"),
        "analysis_geometry_sha256": res.meta.get("analysis_geometry_sha256"),
        "geometry_counts": res.meta.get("geometry_counts"),
    }
    if mode == "current":
        out["currents"] = {k: round(float(v), 2) for k, v in (leg_cur or {}).items()}
    else:
        out["per_net_maxT"] = {k: round(v, 1) for k, v in res.per_net_maxT.items()}
    return out


def render_thermal_detail(board_path, out_png, currents=None, stackup=None,
                          ambient=50.0, grid_mm=0.3, h_eff=15.0, gate_dt=30.0,
                          src_sink_override=None, cmap_name="turbo", width=1500):
    """Solve + draw the full-detail electro-thermal copper map for ONE board. Returns a summary dict.
    Now renders the BLENDED smooth-field + translucent-stacked-copper map (the owner's "between" view)."""
    res, fpath, cool_label = _solve_thermal(board_path, currents=currents, stackup=stackup,
                                            ambient=ambient, grid_mm=grid_mm, h_eff=h_eff,
                                            src_sink_override=src_sink_override)
    _draw_detail_blend(fpath, res, out_png, mode="thermal", cool_label=cool_label, gate_dt=gate_dt,
                       cmap_name=cmap_name, title=os.path.basename(board_path))
    dt_pass = (res.max_T - res.ambient) <= gate_dt
    return {
        "ok": True, "max_T": round(res.max_T, 2), "ambient": res.ambient,
        "dT": round(res.max_T - res.ambient, 2), "verdict": "PASS" if dt_pass else "FAIL",
        "cooling": cool_label, "grid_mm": res.grid_mm, "png": out_png,
        "geometry_source": res.meta.get("geometry_source"),
        "source_geometry_sha256": res.meta.get("source_geometry_sha256"),
        "analysis_geometry_sha256": res.meta.get("analysis_geometry_sha256"),
        "geometry_counts": res.meta.get("geometry_counts"),
        "per_net_maxT": {k: round(v, 1) for k, v in res.per_net_maxT.items()},
    }


def render_overlay(board_path, out_png, currents=None, stackup=None,
                   ambient=50.0, grid_mm=0.4, h_eff=15.0, gate_dt=30.0,
                   gate_J=100.0, src_sink_override=None):
    """Solve + render the composite overlay PNG. Returns the ThermalResult."""
    if plt is None:
        raise RuntimeError("matplotlib unavailable -- overlay render needs it (solve path is unaffected)")
    import pcbnew
    from matplotlib.patches import Polygon as MplPoly
    from matplotlib.collections import PatchCollection, LineCollection

    res, board_path, _cool_label = _solve_thermal(
        board_path, currents=currents, stackup=stackup, ambient=ambient,
        grid_mm=grid_mm, h_eff=h_eff,
        src_sink_override=src_sink_override)

    board = pcbnew.LoadBoard(board_path)
    xmin, ymin, xmax, ymax = res.extent_mm
    w, h = max(xmax - xmin, 1.0), max(ymax - ymin, 1.0)
    fig_w = 9.0
    fig_h = max(2.5, fig_w * h / w * 1.06)            # +colorbar/title headroom
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor("#101418")
    ax.set_facecolor("#0d1117")

    # ---- background: filled copper (grey), drawn low alpha so the heat reads
    cu = _copper_patches(board, t2.STD_CU_LAYERS)
    shade = {"F.Cu": "#3a4750", "B.Cu": "#2b343b",
             "In1.Cu": "#333d44", "In2.Cu": "#333d44",
             "In3.Cu": "#333d44", "In4.Cu": "#333d44"}
    for std, polys in cu.items():
        patches = [MplPoly(p, closed=True) for p in polys]
        if patches:
            ax.add_collection(PatchCollection(
                patches, facecolor=shade.get(std, "#333"), edgecolor="none", alpha=0.55))

    # ---- heatmap: temperature field, alpha-blended on top. Mask the cool
    #      bare-FR4 background so the overlay highlights the actual hot copper.
    T = res.T
    dT = T - res.ambient
    # only show where it is meaningfully above ambient OR there is copper
    cu_mask = res.copper_mask
    if cu_mask is None:
        cu_mask = np.ones_like(T, dtype=bool)
    show = (dT > 0.5) | cu_mask
    Tm = np.ma.array(T, mask=~show)
    vmin = res.ambient
    # clip vmax to a percentile so one hot neck does not crush the pours (see render_per_layer)
    _vmax_pct = float(os.environ.get("CEC_THERMAL_VMAX_PCT", "96"))
    _cuT = T[cu_mask] if (cu_mask is not None and cu_mask.any()) else T[show]
    vmax = (max(float(np.percentile(_cuT, _vmax_pct)), res.ambient + 1.0)
            if _cuT.size else max(res.max_T, res.ambient + 1.0))
    im = ax.imshow(Tm, origin="upper",
                   extent=[xmin, xmax, ymax, ymin], aspect="equal",
                   cmap="inferno", vmin=vmin, vmax=vmax, alpha=0.78,
                   interpolation="bilinear")

    # ---- board outline
    segs = _edge_segments(board)
    if segs:
        ax.add_collection(LineCollection(segs, colors="#80cbc4", linewidths=1.2, alpha=0.9))

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymax, ymin)        # y-down (KiCad)
    ax.set_xlabel("x (mm)", color="#cfd8dc")
    ax.set_ylabel("y (mm)", color="#cfd8dc")
    ax.tick_params(colors="#90a4ae", labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#37474f")

    # gate status in the title. The solver's per_net_maxJ is a GRID-DIVERGENT point singularity at pad
    # cells (a mesh artifact, established in the solver validation), NOT a physical current density, so we
    # do NOT gate on it -- the real J gate uses the analytic solid-annulus value (~28 A/mm2 at 0.5oz, well
    # under 100). The displayed verdict is therefore the BULK-TEMPERATURE gate only; maxJ is shown for
    # reference, flagged as a local mesh value.
    maxJ = max(res.per_net_maxJ.values()) if res.per_net_maxJ else 0.0
    dt_pass = (res.max_T - res.ambient) <= gate_dt
    verdict = "PASS" if dt_pass else "FAIL"
    vcol = "#a5d6a7" if verdict == "PASS" else "#ef9a9a"
    ax.set_title(
        f"electro-thermal overlay   max_T={res.max_T:.1f} C  "
        f"dT={res.max_T - res.ambient:.1f} C  (gate {gate_dt:.0f})   maxJ~{maxJ:.0f}(mesh)   [{verdict}]",
        color=vcol, fontsize=10)

    cb = fig.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
    cb.set_label("Temperature (C)", color="#cfd8dc")
    cb.ax.yaxis.set_tick_params(color="#90a4ae")
    plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color="#cfd8dc")

    fig.tight_layout()
    fig.savefig(out_png, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    return res, verdict, maxJ


def _layer_mask(polys, res):
    """Boolean mask (== res.T.shape) of a layer's filled-copper polygons rasterized onto the solver grid."""
    from matplotlib.path import Path
    xmin, ymin, xmax, ymax = res.extent_mm
    ny, nx = res.T.shape
    gx, gy = np.meshgrid(np.linspace(xmin, xmax, nx), np.linspace(ymin, ymax, ny))
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    m = np.zeros(pts.shape[0], dtype=bool)
    for poly in polys:
        a = np.asarray(poly, dtype=float)
        if a.shape[0] >= 3:
            m |= Path(a).contains_points(pts)
    return m.reshape(ny, nx)


def _track_mask_for_layer(board, lid, res):
    """Boolean mask of a single physical copper layer's ROUTED TRACKS (PCB_TRACK +
    PCB_ARC), rasterized by their real width onto the solver grid. Used by the
    per-layer fallback so traces are NEVER dropped -- even on a copper layer the
    solver's std-layer map (F/B/In1/In2) does not key (e.g. extra signal inners)."""
    import pcbnew
    xmin, ymin, xmax, ymax = res.extent_mm
    ny, nx = res.T.shape
    grid = t2.Grid(xmin, ymin, xmax, ymax, res.grid_mm)
    segs = []
    for tk in board.GetTracks():
        tp = tk.Type()
        if tp not in (pcbnew.PCB_TRACE_T, pcbnew.PCB_ARC_T):
            continue
        if tk.GetLayer() != lid:
            continue
        try:
            w = tk.GetWidth() / 1e6
        except Exception:
            w = 0.0
        if w <= 0:
            continue
        if tp == pcbnew.PCB_ARC_T:
            try:
                s, mid, e = tk.GetStart(), tk.GetMid(), tk.GetEnd()
                pts = t2._arc_chords(s.x / 1e6, s.y / 1e6, mid.x / 1e6, mid.y / 1e6,
                                     e.x / 1e6, e.y / 1e6)
            except Exception:
                s, e = tk.GetStart(), tk.GetEnd()
                pts = [(s.x / 1e6, s.y / 1e6), (e.x / 1e6, e.y / 1e6)]
            for i in range(len(pts) - 1):
                (x0, y0), (x1, y1) = pts[i], pts[i + 1]
                segs.append((x0, y0, x1, y1, w))
        else:
            s, e = tk.GetStart(), tk.GetEnd()
            segs.append((s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6, w))
    if not segs:
        return np.zeros((ny, nx), dtype=bool)
    tmask, _twf = t2._rasterize_tracks(segs, grid)
    # the solver grid (Grid.ny/nx) matches res.T.shape; guard just in case
    if tmask.shape != res.T.shape:
        return np.zeros((ny, nx), dtype=bool)
    return tmask


def render_per_layer(board_path, out_dir, currents=None, stackup=None,
                     ambient=50.0, grid_mm=0.4, h_eff=15.0, gate_dt=30.0, src_sink_override=None):
    """Produce ONE clean, TRANSPARENT thermal PNG per copper layer -- the temperature field masked to that
    layer's OWN copper, nothing else, transparent elsewhere -- plus a colorbar strip. "That layer's copper"
    is FILLED ZONES *AND* ROUTED TRACKS (PCB_TRACK/PCB_ARC, rasterized by width) *AND* PADS: the mask is the
    solver's trace+zone+pad layer_copper_mask, so routed traces show up in the heatmap coloured by their
    temperature (a signal trace carrying ~0 A reads near ambient; a current-carrying power trace heats up).
    A fallback (for a copper layer the solver does not key) rasterizes that layer's zones+tracks directly so
    traces are never dropped. All PNGs share the SAME board extent + pixel size so the dashboard stacks/
    toggles them exactly like the plot layers (mix-blend-mode:lighten). This replaces the muddy single
    composite (grey copper + a semi-transparent heatmap over ALL layers at once). Keyed by the board's REAL
    layer names (F.Cu / GND / 12V / B.Cu -> F_Cu/GND/12V/B_Cu) so they line up with the dashboard's layer
    checkboxes. Returns a summary dict."""
    if plt is None:
        raise RuntimeError("matplotlib unavailable -- overlay render needs it (solve path is unaffected)")
    import pcbnew
    from matplotlib.collections import LineCollection
    os.makedirs(out_dir, exist_ok=True)
    # Solve via the shared recipe (per-board config + pour/fill + production case-cooling env-knobs); the
    # cooling rationale is documented on _solve_thermal / board_thermal_config. board_path is rebound to the
    # filled copy the solver used so the per-layer masks below read the SAME copper.
    res, board_path, cool_label = _solve_thermal(
        board_path, currents=currents, stackup=stackup, ambient=ambient,
        grid_mm=grid_mm, h_eff=h_eff, src_sink_override=src_sink_override)

    board = pcbnew.LoadBoard(board_path)
    segs = _edge_segments(board)
    xmin, ymin, xmax, ymax = res.extent_mm
    W, H = max(xmax - xmin, 1e-6), max(ymax - ymin, 1e-6)
    # Colour range over the copper the SOLVER actually modelled (zones + routed
    # traces + pads). CLIP vmax to a high PERCENTILE, not the raw max: a single
    # blazing-hot neck (a few cells at 1000+ C in the still-air bound) otherwise
    # owns the whole 50->max scale and crushes every current-carrying POUR into the
    # black/background end -> the pours read as "absent" even though they carry the
    # entire load. With the percentile, the necks saturate (bright) and the pour
    # gradient is visible. The TRUE peak stays in the colorbar label + summary max_T.
    # CEC_THERMAL_VMAX_PCT tunes it (default 96); with no hot outlier the percentile
    # ~= the max, so this is a no-op on well-behaved boards.
    cu_any = res.copper_mask
    _vmax_pct = float(os.environ.get("CEC_THERMAL_VMAX_PCT", "96"))
    if cu_any is not None and cu_any.any():
        vmax = max(float(np.percentile(res.T[cu_any], _vmax_pct)), res.ambient + 1.0)
    else:
        vmax = max(res.max_T, res.ambient + 1.0)
    vmin = res.ambient
    cmap = plt.cm.inferno.copy(); cmap.set_bad(alpha=0.0)   # masked (no copper) -> fully transparent
    # COPPER-GEOMETRY BASE + alpha-ramped heatmap: the inferno low end is near-black,
    # so cool POUR copper (away from the hot necks) vanished into the dark dashboard
    # ("pours not on the dash"). Draw the layer's copper as a dim slate BASE so its
    # SHAPE is always visible, then ride the heatmap on top with an alpha ramp -- cool
    # copper shows the slate base, warm->hot copper saturates to inferno.
    from matplotlib.colors import ListedColormap
    base_cmap = ListedColormap(["#5d6e7a"])                 # dim slate, visible on the dark panel
    _heat = plt.cm.inferno(np.linspace(0, 1, 256))
    _heat[:, 3] = np.clip(np.linspace(-0.15, 1.25, 256), 0.0, 1.0)   # transparent cool -> opaque hot
    heat_cmap = ListedColormap(_heat); heat_cmap.set_bad(alpha=0.0)

    # per-layer copper masks INCLUDING traces (from the solver), keyed by std-layer
    lcm = res.layer_copper_mask or {}

    layers, per_layer_maxT = {}, {}
    for lid in board.GetEnabledLayers().CuStack():
        name = board.GetLayerName(lid)
        # prefer the solver's trace+zone+pad mask for this layer; fall back to
        # zones+tracks (so routed traces are NEVER dropped, even on a copper
        # layer the solver's std-layer map does not key).
        std = t2.STD_CU_LAYERS.get(lid)
        mask = lcm.get(std) if std else None
        if mask is None or not mask.any():
            polys = []
            for z in board.Zones():
                if z.IsOnLayer(lid):
                    pl = z.GetFilledPolysList(lid)
                    for oi in range(pl.OutlineCount()):
                        ol = pl.Outline(oi)
                        pts = [(ol.CPoint(k).x / 1e6, ol.CPoint(k).y / 1e6)
                               for k in range(ol.PointCount())]
                        if len(pts) >= 3:
                            polys.append(pts)
            mask = _layer_mask(polys, res) if polys else \
                np.zeros(res.T.shape, dtype=bool)
            mask = mask | _track_mask_for_layer(board, lid, res)
        if not mask.any():
            continue
        key = name.replace(".", "_").replace(" ", "_")
        per_layer_maxT[name] = round(float(res.T[mask].max()), 1)
        Tm = np.ma.array(res.T, mask=~mask)
        fig = plt.figure(figsize=(8.0, 8.0 * H / W), dpi=130)
        ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
        base = np.ma.array(np.zeros_like(res.T), mask=~mask)   # this layer's copper SHAPE -> dim slate base
        ax.imshow(base, origin="upper", extent=[xmin, xmax, ymax, ymin], aspect="equal",
                  cmap=base_cmap, vmin=0, vmax=1, interpolation="nearest")
        ax.imshow(Tm, origin="upper", extent=[xmin, xmax, ymax, ymin], aspect="equal",
                  cmap=heat_cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
        # POUR OUTLINES: trace this layer's filled ZONE boundaries in bright cyan so the
        # wide pours are UNMISTAKABLE as copper regions on the heatmap, not lost among the
        # equally-warm traces (the owner's "I can't see the pours on the dash").
        zsegs = []
        for z in board.Zones():
            if not z.IsOnLayer(lid):
                continue
            pl = z.GetFilledPolysList(lid)
            for oi in range(pl.OutlineCount()):
                ol = pl.Outline(oi)
                pts = [(ol.CPoint(k).x / 1e6, ol.CPoint(k).y / 1e6) for k in range(ol.PointCount())]
                for i in range(len(pts)):
                    zsegs.append((pts[i], pts[(i + 1) % len(pts)]))
        if zsegs:
            ax.add_collection(LineCollection(zsegs, colors="#00e5ff", linewidths=0.5, alpha=0.85))
        if segs:
            ax.add_collection(LineCollection(segs, colors="#80cbc4", linewidths=0.8, alpha=0.55))
        ax.set_xlim(xmin, xmax); ax.set_ylim(ymax, ymin)
        p = os.path.join(out_dir, key + ".png")
        fig.savefig(p, dpi=130, transparent=True); plt.close(fig)
        layers[key] = p

    import matplotlib as mpl
    cbar = os.path.join(out_dir, "_cbar.png")
    fig = plt.figure(figsize=(8.0, 0.62), dpi=130); fig.patch.set_facecolor("#101418")
    cax = fig.add_axes([0.04, 0.5, 0.92, 0.32])
    cb = mpl.colorbar.ColorbarBase(cax, cmap=plt.cm.inferno,
                                   norm=mpl.colors.Normalize(vmin=vmin, vmax=vmax), orientation="horizontal")
    _clip = f"  scale→{vmax:.0f}°C (clipped)" if vmax < res.max_T - 0.5 else ""
    cb.set_label(f"copper temp (°C)   ambient {res.ambient:.0f}°C{_clip}   peak {res.max_T:.1f}°C   [{cool_label}]",
                 color="#cfd8dc", fontsize=9)
    cax.tick_params(colors="#cfd8dc", labelsize=8)
    fig.savefig(cbar, dpi=130, facecolor="#101418"); plt.close(fig)

    # HOVER DATA: dump the full temperature field so the dashboard can read off T(x,y) on mouseover. The
    # per-layer PNGs fill the figure axes [0,0,1,1] with imshow extent=[xmin,xmax,ymax,ymin], so the PNG
    # pixels map 1:1 to the board extent -- the frontend maps cursor-fraction -> (row,col) -> T directly.
    try:
        Tg = res.T
        with open(os.path.join(out_dir, "thermal-grid.json"), "w") as f:
            json.dump({"extent": [round(xmin, 2), round(ymin, 2), round(xmax, 2), round(ymax, 2)],
                       "shape": [int(Tg.shape[0]), int(Tg.shape[1])], "grid_mm": round(res.grid_mm, 3),
                       "ambient": round(res.ambient, 1), "vmin": round(vmin, 1), "vmax": round(vmax, 1),
                       "T": [round(float(v), 1) for v in Tg.flatten()]}, f)
    except Exception:                                        # noqa: BLE001 -- hover data is a bonus, never block
        pass

    # FULL-DETAIL composite (the owner's primary thermal view) + its CURRENT TWIN cross-check. BOTH are the
    # BLENDED smooth-field + translucent-stacked-copper map drawn from the SAME `res` + filled board (no second
    # solve): _detail.png = temperature, _current.png = per-net current. Each degrades to None on failure so
    # the per-layer raster (and the rest of the dashboard) never break.
    detail_name = None
    try:
        detail = os.path.join(out_dir, "_detail.png")
        _draw_detail_blend(board_path, res, detail, mode="thermal", cool_label=cool_label, gate_dt=gate_dt)
        detail_name = os.path.basename(detail)
    except Exception:                                        # noqa: BLE001
        detail_name = None

    current_name = None
    try:
        current = os.path.join(out_dir, "_current.png")
        _draw_detail_blend(board_path, res, current, mode="current", currents=currents,
                           cool_label=cool_label, gate_dt=gate_dt)
        current_name = os.path.basename(current)
    except Exception:                                        # noqa: BLE001
        current_name = None

    dt_pass = (res.max_T - res.ambient) <= gate_dt
    return {
        "ok": True, "max_T": round(res.max_T, 2), "ambient": res.ambient,
        "dT": round(res.max_T - res.ambient, 2), "verdict": "PASS" if dt_pass else "FAIL",
        "cooling": cool_label,
        "grid_mm": res.grid_mm, "vmin": round(vmin, 1), "vmax": round(vmax, 1),
        "per_layer_maxT": per_layer_maxT,
        "per_net_maxT": {k: round(v, 1) for k, v in res.per_net_maxT.items()},
        "layers": {k: os.path.basename(v) for k, v in layers.items()},
        "detail": detail_name,
        "current": current_name,
        "cbar": os.path.basename(cbar), "out_dir": out_dir,
    }


def main():
    ap = argparse.ArgumentParser(description="electro-thermal heatmap overlay for the dashboard")
    ap.add_argument("--board", required=True)
    ap.add_argument("--out", default=None, help="composite-mode output PNG")
    ap.add_argument("--out-dir", default=None,
                    help="PER-LAYER mode: dir for one transparent <layer>.png each + _cbar.png (the dashboard view)")
    ap.add_argument("--detail", default=None,
                    help="DETAIL mode: blended smooth-field + detailed-copper map coloured by temperature -> this PNG")
    ap.add_argument("--current", default=None,
                    help="CURRENT-TWIN mode: the same blended map coloured by per-net current -> this PNG")
    ap.add_argument("--cmap", default="turbo", help="detail-mode colormap (default turbo)")
    ap.add_argument("--grid-mm", type=float, default=0.4)
    ap.add_argument("--ambient", type=float, default=50.0)
    ap.add_argument("--h-eff", type=float, default=15.0)
    ap.add_argument("--currents", default=None, help="JSON dict net->amps (default: balanced EPS)")
    ap.add_argument("--stackup", default=None, help="JSON dict std-layer->oz (default: F/B=1,In=0.5)")
    a = ap.parse_args()

    currents = json.loads(a.currents) if a.currents else None
    stackup = json.loads(a.stackup) if a.stackup else None
    if a.detail or a.current:                                # DETAIL / CURRENT-TWIN mode (the blended copper map)
        mode = "current" if a.current else "thermal"
        out_png = a.current or a.detail
        try:
            out = render_detail_blend(a.board, out_png, mode=mode, currents=currents, stackup=stackup,
                                      ambient=a.ambient, grid_mm=a.grid_mm, h_eff=a.h_eff, cmap_name=a.cmap)
        except Exception as e:                              # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})); sys.exit(2)
        print(json.dumps(out)); return
    if a.out_dir:                                            # PER-LAYER mode (the dashboard's view)
        try:
            out = render_per_layer(a.board, a.out_dir, currents=currents, stackup=stackup,
                                   ambient=a.ambient, grid_mm=a.grid_mm, h_eff=a.h_eff)
        except Exception as e:                              # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"})); sys.exit(2)
        print(json.dumps(out)); return
    if not a.out:
        print(json.dumps({"ok": False, "error": "need --out or --out-dir"})); sys.exit(2)
    try:
        res, verdict, maxJ = render_overlay(
            a.board, a.out, currents=currents, stackup=stackup,
            ambient=a.ambient, grid_mm=a.grid_mm, h_eff=a.h_eff)
    except Exception as e:
        # emit a structured failure on the LAST line so the caller can degrade
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        sys.exit(2)

    out = {
        "ok": True,
        "max_T": round(res.max_T, 2),
        "ambient": res.ambient,
        "dT": round(res.max_T - res.ambient, 2),
        "maxJ_A_per_mm2": round(maxJ, 1),
        "verdict": verdict,
        "grid_mm": res.grid_mm,
        "joule_W": round(res.total_joule_W, 3),
        "per_net_maxT": {k: round(v, 1) for k, v in res.per_net_maxT.items()},
        "currents": currents or default_currents(a.board),
        "png": a.out,
    }
    print(json.dumps(out))      # LAST line = parseable summary


if __name__ == "__main__":
    main()
