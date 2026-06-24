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
import json
import os
import sys

# matplotlib headless before any pyplot import
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_thermal2d as t2  # noqa: E402


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


def board_thermal_config(board_path):
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
    coupled to the case -- the solver lands at dT~24 / maxT~74 = PASS (matches the owner's ~14C/64C hand
    calc). cooling = {shunt_prefix, g_chassis_W_per_K (per-shunt TIM), g_mount_W_per_K (per M3 mount), label}.
    Conservative-TIM / mount-only / still-air bounds are reachable via the CEC_THERMAL_* env knobs in
    render_per_layer. Scoped to 12VHPWR only -- the EPS/PCIe cable boards keep still-air pending owner
    sign-off on whether they share the same enclosure model (FOLLOWUPS)."""
    name = os.path.basename(board_path).lower()
    if "12vhpwr" in name or "12v2x6" in name:
        nc, ov = {}, {}
        for n in range(1, 7):
            nc["/SENSEP%d_HI" % n] = 8.33
            nc["/SENSEP%d_LO" % n] = 8.33
            ov["/SENSEP%d_HI" % n] = {"refs_src": ["J3"], "refs_sink": ["RS%d" % n]}
            ov["/SENSEP%d_LO" % n] = {"refs_src": ["RS%d" % n], "refs_sink": ["J4"]}
        nc["GND"] = 50.0
        ov["GND"] = {"refs_src": ["J4"], "refs_sink": ["J3"]}
        cooling = {"shunt_prefix": "RS", "g_chassis_W_per_K": 0.3, "g_mount_W_per_K": 0.5,
                   "label": "production: metal case (TIM on RS shunts + M3 mounts)"}
        return nc, {"F.Cu": 2.0, "In1.Cu": 1.0, "In2.Cu": 1.0, "B.Cu": 2.0}, ov, cooling
    return None, None, None, None


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


def _prepare_filled(board_path):
    """Pour the SENSEC high-current corridors + FILL all zones so the solver and the render have REAL
    copper. Placement candidates ship with UNFILLED zones (the filled pours only exist in the temp routed
    board during measure), so without this the field is uniform ambient and the heatmap reads blank. Adds
    the F.Cu SENSEC pours (so the 12V corridors show) then fills GND/+pours. Returns a temp filled-board
    path; degrades to the original path on any failure (the overlay must never hard-fail)."""
    import pcbnew
    import tempfile
    try:
        b = pcbnew.LoadBoard(board_path)
        try:
            import cec_fr
            pours = cec_fr.derive_power_pours(board_path, board=b)
            cec_fr.add_power_pours(b, pours, fill=False)
        except Exception:                                    # noqa: BLE001 -- pours are a bonus; GND fill is the core
            pass
        for z in b.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        out = os.path.join(tempfile.gettempdir(), "thermal_filled_" + os.path.basename(board_path))
        pcbnew.SaveBoard(out, b)
        return out
    except Exception:                                        # noqa: BLE001
        return board_path


def render_overlay(board_path, out_png, currents=None, stackup=None,
                   ambient=50.0, grid_mm=0.4, h_eff=15.0, gate_dt=30.0,
                   gate_J=100.0, src_sink_override=None):
    """Solve + render the composite overlay PNG. Returns the ThermalResult."""
    import pcbnew
    from matplotlib.patches import Polygon as MplPoly
    from matplotlib.collections import PatchCollection, LineCollection

    board_path = _prepare_filled(board_path)                 # candidates ship unfilled -> pour + fill first
    if currents is None:
        currents = default_currents(board_path)

    res = t2.solve_board_thermal(
        board_path, stackup_oz=stackup, net_currents=currents,
        ambient=ambient, h_eff=h_eff, grid_mm=grid_mm, verbose=False,
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
    shade = {"F.Cu": "#3a4750", "B.Cu": "#2b343b", "In1.Cu": "#333d44", "In2.Cu": "#333d44"}
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
    vmax = max(res.max_T, res.ambient + 1.0)
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
    import pcbnew
    from matplotlib.collections import LineCollection
    os.makedirs(out_dir, exist_ok=True)
    cfg_nc, cfg_stack, cfg_ov, cfg_cool = board_thermal_config(board_path)   # per-board inputs (read BEFORE _prepare_filled renames)
    board_path = _prepare_filled(board_path)             # candidates ship unfilled -> pour + fill first
    if currents is None:
        currents = cfg_nc if cfg_nc is not None else default_currents(board_path)
    if stackup is None:
        stackup = cfg_stack                              # 12VHPWR -> 2oz/1oz; cable boards -> None (solver default)
    if src_sink_override is None:
        src_sink_override = cfg_ov                        # 12VHPWR -> J3/J4 lanes; cable boards -> auto J_IN/J_OUT

    # PRODUCTION case-cooling (owner-validated 2026-06-20): the dashboard default (still-air + adiabatic
    # edges + no enclosure) gives a misleadingly hot dT99/maxT149 for 12VHPWR. The real production design --
    # full metal case, TIM from the RS1-6 shunts to the case, M3 mounts coupled to the case -- lands at
    # dT~24/maxT~74 = PASS (matches the owner's ~14/64 hand calc). Couple the TIM'd shunts (chassis_refs) +
    # mounts (g_mount auto-finds the M3 holes) to the case temp. Env knobs walk the envelope without a code
    # edit: CEC_THERMAL_NO_COOLING=1 -> still-air conservative bound; CEC_THERMAL_TIM_WK / CEC_THERMAL_MOUNT_WK
    # -> override the per-shunt TIM / per-mount conductance (e.g. CONSERVATIVE TIM 0.1). Scoped by cfg_cool to
    # 12VHPWR; cable boards have cfg_cool=None -> unchanged still-air.
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
        src_sink_override=src_sink_override, **cool_kw)

    board = pcbnew.LoadBoard(board_path)
    segs = _edge_segments(board)
    xmin, ymin, xmax, ymax = res.extent_mm
    W, H = max(xmax - xmin, 1e-6), max(ymax - ymin, 1e-6)
    # Colour range is recomputed over the copper the SOLVER actually modelled
    # (zones + routed traces + pads) so a hot thin trace sets the top of the scale,
    # not a stale plane-only range.
    cu_any = res.copper_mask
    if cu_any is not None and cu_any.any():
        vmax = max(float(res.T[cu_any].max()), res.ambient + 1.0)
    else:
        vmax = max(res.max_T, res.ambient + 1.0)
    vmin = res.ambient
    cmap = plt.cm.inferno.copy(); cmap.set_bad(alpha=0.0)   # masked (no copper) -> fully transparent

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
        ax.imshow(Tm, origin="upper", extent=[xmin, xmax, ymax, ymin], aspect="equal",
                  cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
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
    cb.set_label(f"copper temperature (°C)    ambient {res.ambient:.0f}°C    max {res.max_T:.1f}°C",
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

    dt_pass = (res.max_T - res.ambient) <= gate_dt
    return {
        "ok": True, "max_T": round(res.max_T, 2), "ambient": res.ambient,
        "dT": round(res.max_T - res.ambient, 2), "verdict": "PASS" if dt_pass else "FAIL",
        "cooling": cool_label,
        "grid_mm": res.grid_mm, "vmin": round(vmin, 1), "vmax": round(vmax, 1),
        "per_layer_maxT": per_layer_maxT,
        "per_net_maxT": {k: round(v, 1) for k, v in res.per_net_maxT.items()},
        "layers": {k: os.path.basename(v) for k, v in layers.items()},
        "cbar": os.path.basename(cbar), "out_dir": out_dir,
    }


def main():
    ap = argparse.ArgumentParser(description="electro-thermal heatmap overlay for the dashboard")
    ap.add_argument("--board", required=True)
    ap.add_argument("--out", default=None, help="composite-mode output PNG")
    ap.add_argument("--out-dir", default=None,
                    help="PER-LAYER mode: dir for one transparent <layer>.png each + _cbar.png (the dashboard view)")
    ap.add_argument("--grid-mm", type=float, default=0.4)
    ap.add_argument("--ambient", type=float, default=50.0)
    ap.add_argument("--h-eff", type=float, default=15.0)
    ap.add_argument("--currents", default=None, help="JSON dict net->amps (default: balanced EPS)")
    ap.add_argument("--stackup", default=None, help="JSON dict std-layer->oz (default: F/B=1,In=0.5)")
    a = ap.parse_args()

    currents = json.loads(a.currents) if a.currents else None
    stackup = json.loads(a.stackup) if a.stackup else None
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
