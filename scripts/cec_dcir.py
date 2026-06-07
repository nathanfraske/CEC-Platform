#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_dcir -- 2.5D DC IR-drop + current-density field solve on routed copper.
# ============================================================================
# A real field solve to REFINE the weakest term in the analytic electrothermal model
# (cec_synth_pipeline.electrothermal_solve): instead of approximating a high-current net's
# cross-section as (pour planar area / pad-bbox path length) x thickness, this rasterizes the
# net's actual routed copper to a grid, builds a resistor network -- sheet conductance laterally,
# via barrels vertically -- injects the design current between the CONNECTOR pads (J*) and the
# SHUNT pads (RS*) as equipotential terminals, and solves  L v = i  with a masked, numpy-only
# Conjugate-Gradient solve. Per net it returns the IR drop (V), the peak current density
# J (A/mm^2), and the bottleneck effective cross-section (mm^2 = I / J).
#
# DESIGN CHOICES (deliberate, documented):
#   * numpy ONLY (no scipy) -- runs in KiCad's bundled python (which has numpy, not scipy) AND in
#     the Linux compute container. The solve is a Jacobi-preconditioned CG on the graph Laplacian.
#   * FALLBACK-SAFE: returns None for any net it cannot resolve (no filled pour, or no two-terminal
#     connector<->shunt force path), so the caller keeps the analytic estimate for that net.
#   * ADDITIVE: meant to populate a 'dcir' sub-dict ALONGSIDE the existing per-net values, NOT to
#     silently replace the gate-driving J/cross until the solver is validated against a measured
#     board (per docs/local-compute-exploration.md, "stage it as a calibration, not a hard re-gate").
#   * Equipotential pad terminals: each terminal pad's covered cells tie to a virtual node (low-R),
#     so multi-cell / multi-layer (THT) pads inject as a near-equipotential and current spreads into
#     the copper rather than crowding a single grid cell. J is reported as a high percentile (the
#     bottleneck) and the raw max, so a single-cell artifact does not dominate the headline number.
#
# Units are SI internally (metres, amps, ohms, volts); outputs converted to mm^2 / (A/mm^2).
#
#   python3 scripts/cec_dcir.py [board.kicad_pcb] [--h MM] [--current-12v A] ...
#   (default: self-test on modules/atx-24pin-rev2/24pin-module.kicad_pcb)
# ============================================================================
import os
import sys
import math
import argparse

import numpy as np
import pcbnew

# pcbnew is a wxWidgets debug build: a wxASSERT pops a BLOCKING modal dialog on Windows (and aborts
# headless/background/container runs). We guard our own pcbnew calls, but disable wx asserts too so a
# stray one can never stall a run. Harmless if wx/DisableAsserts is unavailable.
try:
    import wx
    wx.DisableAsserts()
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RHO_CU = 1.72e-8            # copper resistivity, ohm.m at ~20 C (matches electrothermal_solve's regime)
CU_OZ_M = 34.8e-6           # copper thickness per oz, metres (0.0348 mm/oz, = cec_synth_pipeline.CU_OZ_MM)
VIA_PLATING_M = 25e-6       # plated barrel wall thickness, metres (matches the via model upstream)
TIE_G = 1.0e4              # virtual pad-terminal tie conductance (S): low-R but bounded for CG conditioning


# --------------------------------------------------------------------------- geometry helpers
def _cu_layers(b):
    """Enabled copper layers as (layer_id, name, is_outer), in stack order."""
    out = []
    for l in b.GetEnabledLayers().Seq():
        if pcbnew.IsCopperLayer(l):
            name = b.GetLayerName(l)
            out.append((l, name, name in ("F.Cu", "B.Cu")))
    return out


def _layer_thickness_m(is_outer, oz_outer, oz_inner):
    return (oz_outer if is_outer else oz_inner) * CU_OZ_M


def _terminals(b, net):
    """Classify the net's force-path terminal pads: connectors (ref J*) vs shunts (ref RS*). INA/IC
    sense pads (Kelvin taps) carry ~0 current and are intentionally NOT terminals (they sit on the
    copper as dead-end branches). Returns (conn_pads, shunt_pads) or None if not a 2-terminal path."""
    conn, shunt = [], []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            if p.GetNetname() != net:
                continue
            if ref.startswith("RS"):
                shunt.append(p)
            elif ref.startswith("J"):
                conn.append(p)
    if conn and shunt:
        return conn, shunt
    return None


def _pad_cells(pad, li_layer, x0, y0, h, nx, ny):
    """Grid cells (ix,iy) whose centre is inside this pad on layer li_layer."""
    if not pad.IsOnLayer(li_layer):
        return []
    bb = pad.GetBoundingBox()
    ix0 = max(0, int((bb.GetLeft() / 1e6 - x0) / h) - 1)
    ix1 = min(nx - 1, int((bb.GetRight() / 1e6 - x0) / h) + 1)
    iy0 = max(0, int((bb.GetTop() / 1e6 - y0) / h) - 1)
    iy1 = min(ny - 1, int((bb.GetBottom() / 1e6 - y0) / h) + 1)
    cells = []
    for ix in range(ix0, ix1 + 1):
        for iy in range(iy0, iy1 + 1):
            xpt = int(round((x0 + ix * h) * 1e6))
            ypt = int(round((y0 + iy * h) * 1e6))
            if pad.HitTest(pcbnew.VECTOR2I(xpt, ypt), 0):
                cells.append((ix, iy))
    return cells


def _net_bbox(b, net, layers):
    """Union bbox (mm) of the net's zones + tracks + terminal pads. None if no copper found."""
    lo = [1e18, 1e18]
    hi = [-1e18, -1e18]
    found = False

    def grow(bb):
        nonlocal found
        found = True
        lo[0] = min(lo[0], bb.GetLeft() / 1e6); lo[1] = min(lo[1], bb.GetTop() / 1e6)
        hi[0] = max(hi[0], bb.GetRight() / 1e6); hi[1] = max(hi[1], bb.GetBottom() / 1e6)

    for z in b.Zones():
        if z.GetNetname() == net:
            grow(z.GetBoundingBox())
    for t in b.GetTracks():
        if t.GetNetname() == net:
            grow(t.GetBoundingBox())
    if not found:
        return None
    return lo[0], lo[1], hi[0], hi[1]


def _raster(b, net, layers, x0, y0, h, nx, ny):
    """Boolean copper mask per layer: cell is copper if inside any filled zone on that layer, or
    within w/2 of any track on that layer. Returns {layer_id: bool ndarray (nx,ny)}. Zones use the
    pcbnew SHAPE_POLY_SET.Contains (holes handled); tracks are rasterized analytically in numpy."""
    masks = {li: np.zeros((nx, ny), dtype=bool) for (li, _, _) in layers}
    gx = x0 + np.arange(nx) * h
    gy = y0 + np.arange(ny) * h
    GX, GY = np.meshgrid(gx, gy, indexing="ij")        # (nx,ny) cell-centre coords in mm

    # zones: SHAPE_POLY_SET.Contains per cell within the zone bbox (the dominant copper)
    for z in b.Zones():
        if z.GetNetname() != net:
            continue
        for li in z.GetLayerSet().Seq():       # ONLY the zone's own layers: GetFilledPolysList()
            if li not in masks:                  # C++ asserts (aborts the process) on a foreign layer
                continue
            try:
                sps = z.GetFilledPolysList(li)
            except Exception:
                continue
            if sps is None or sps.OutlineCount() == 0:
                continue
            bb = z.GetBoundingBox()
            ix0 = max(0, int((bb.GetLeft() / 1e6 - x0) / h))
            ix1 = min(nx - 1, int((bb.GetRight() / 1e6 - x0) / h))
            iy0 = max(0, int((bb.GetTop() / 1e6 - y0) / h))
            iy1 = min(ny - 1, int((bb.GetBottom() / 1e6 - y0) / h))
            m = masks[li]
            for ix in range(ix0, ix1 + 1):
                xpt = int(round((x0 + ix * h) * 1e6))
                for iy in range(iy0, iy1 + 1):
                    if m[ix, iy]:
                        continue
                    ypt = int(round((y0 + iy * h) * 1e6))
                    if sps.Contains(pcbnew.VECTOR2I(xpt, ypt)):
                        m[ix, iy] = True

    # tracks: vectorized distance from every cell centre to the segment <= w/2 + h/2
    for t in b.GetTracks():
        if t.GetNetname() != net or t.Type() != pcbnew.PCB_TRACE_T:
            continue
        li = t.GetLayer()
        if li not in masks:
            continue
        ax, ay = t.GetStart().x / 1e6, t.GetStart().y / 1e6
        bx, by = t.GetEnd().x / 1e6, t.GetEnd().y / 1e6
        half = (t.GetWidth() / 1e6) / 2.0 + h / 2.0
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        if seg2 < 1e-12:
            d2 = (GX - ax) ** 2 + (GY - ay) ** 2
        else:
            tt = np.clip(((GX - ax) * dx + (GY - ay) * dy) / seg2, 0.0, 1.0)
            px, py = ax + tt * dx, ay + tt * dy
            d2 = (GX - px) ** 2 + (GY - py) ** 2
        masks[li] |= (d2 <= half * half)
    return masks


# --------------------------------------------------------------------------- solver
def _pcg(matvec, b, diag, fixed, tol=1e-9, maxit=6000):
    """Jacobi-preconditioned CG for the SPD free-node system; `fixed` nodes held at 0. Returns
    (solution, final relative residual). A disconnected source/sink leaves a large residual -> the
    caller rejects the net rather than trusting a divergent potential."""
    invd = np.zeros_like(b)
    nz = (diag > 0) & (~fixed)
    invd[nz] = 1.0 / diag[nz]
    x = np.zeros_like(b)
    r = b.copy(); r[fixed] = 0.0
    b0 = float(r @ r)
    if b0 <= 0:
        return x, 0.0
    z = invd * r
    p = z.copy()
    rz = float(r @ z)
    rel = 1.0
    for _ in range(maxit):
        Ap = matvec(p); Ap[fixed] = 0.0
        denom = float(p @ Ap)
        if denom <= 0:
            break
        a = rz / denom
        x += a * p
        r -= a * Ap
        rel = float(r @ r) / b0
        if rel < tol * tol:
            break
        z = invd * r
        rz_new = float(r @ z)
        p = z + (rz_new / rz) * p
        rz = rz_new
    return x, math.sqrt(max(rel, 0.0))


def solve_net(b, net, I, layers, h, *, oz_outer=2.0, oz_inner=1.0, via_sep_m=0.4e-3):
    """DC field solve for one high-current force net. Returns a dict (ir_drop_V, j_max_A_mm2,
    j_p995_A_mm2, eff_cross_mm2, n_nodes, n_lat_edges, n_vias, layers) or None if unresolvable."""
    terms = _terminals(b, net)
    if terms is None:
        return None
    conn_pads, shunt_pads = terms
    bbox = _net_bbox(b, net, layers)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    pad = 1.0
    x0 -= pad; y0 -= pad; x1 += pad; y1 += pad
    nx = int(math.ceil((x1 - x0) / h)) + 1
    ny = int(math.ceil((y1 - y0) / h)) + 1
    if nx * ny > 4_000_000:                       # guard: refuse an absurd grid (raise h instead)
        return None

    masks = _raster(b, net, layers, x0, y0, h, nx, ny)
    lset = [(li, name, outer) for (li, name, outer) in layers if masks[li].any()]
    if not lset:
        return None

    # node ids: per-layer (nx,ny) int array, -1 = no copper. Plus two virtual terminal nodes.
    nid = {li: -np.ones((nx, ny), dtype=np.int64) for (li, _, _) in lset}
    n = 0
    for (li, _, _) in lset:
        m = masks[li]
        idx = np.where(m.reshape(-1))[0]
        ids = np.arange(n, n + idx.size)
        flat = nid[li].reshape(-1)
        flat[idx] = ids
        n += idx.size
    if n < 4:
        return None
    S = n; K = n + 1                               # virtual source / sink terminal nodes
    N = n + 2

    ea, eb, eg, et = [], [], [], []                # lateral+via edges: from,to,conductance,thickness(0=via)

    # lateral edges (right + down neighbour) per layer, sheet conductance g = t/rho (per square)
    for (li, _, outer) in lset:
        t_m = _layer_thickness_m(outer, oz_outer, oz_inner)
        g = t_m / RHO_CU
        idl = nid[li]
        a = idl[:-1, :]; b2 = idl[1:, :]           # horizontal neighbours
        mask = (a >= 0) & (b2 >= 0)
        ea.append(a[mask]); eb.append(b2[mask])
        eg.append(np.full(mask.sum(), g)); et.append(np.full(mask.sum(), t_m))
        a = idl[:, :-1]; b2 = idl[:, 1:]           # vertical neighbours
        mask = (a >= 0) & (b2 >= 0)
        ea.append(a[mask]); eb.append(b2[mask])
        eg.append(np.full(mask.sum(), g)); et.append(np.full(mask.sum(), t_m))

    # via edges: link the via's cell across consecutive copper layers it spans (barrel conductance)
    order = [li for (li, _, _) in lset]
    n_vias = 0
    for t in b.GetTracks():
        if t.GetNetname() != net or t.Type() != pcbnew.PCB_VIA_T:
            continue
        ix = int(round((t.GetPosition().x / 1e6 - x0) / h))
        iy = int(round((t.GetPosition().y / 1e6 - y0) / h))
        if not (0 <= ix < nx and 0 <= iy < ny):
            continue
        d = t.GetDrillValue() / 1e6 / 1000.0       # mm -> m
        g_via = (math.pi * d * VIA_PLATING_M) / (RHO_CU * via_sep_m) if d > 0 else TIE_G
        present = [li for li in order if nid[li][ix, iy] >= 0]
        for li_a, li_b in zip(present, present[1:]):
            ea.append(np.array([nid[li_a][ix, iy]])); eb.append(np.array([nid[li_b][ix, iy]]))
            eg.append(np.array([g_via])); et.append(np.array([0.0]))   # 0 thickness => excluded from J
            n_vias += 1

    # virtual terminal ties: connector pads -> S, shunt pads -> K
    def tie(pads, node):
        cnt = 0
        for p in pads:
            for (li, _, _) in lset:
                for (ix, iy) in _pad_cells(p, li, x0, y0, h, nx, ny):
                    j = nid[li][ix, iy]
                    if j >= 0:
                        ea.append(np.array([j])); eb.append(np.array([node]))
                        eg.append(np.array([TIE_G])); et.append(np.array([0.0])); cnt += 1
        return cnt

    if tie(conn_pads, S) == 0 or tie(shunt_pads, K) == 0:
        return None

    ea = np.concatenate(ea); eb = np.concatenate(eb)
    eg = np.concatenate(eg); et = np.concatenate(et)

    diag = np.zeros(N)
    np.add.at(diag, ea, eg); np.add.at(diag, eb, eg)

    def matvec(x):
        y = np.zeros_like(x)
        flow = eg * (x[ea] - x[eb])
        np.add.at(y, ea, flow); np.add.at(y, eb, -flow)
        return y

    rhs = np.zeros(N)
    rhs[S] = I                                     # inject I at the source terminal; sink K pinned to 0
    fixed = np.zeros(N, dtype=bool); fixed[K] = True
    v, rel = _pcg(matvec, rhs, diag, fixed)

    # Robustness gate: a disconnected connector<->shunt path (e.g. a pour neck thinner than the grid)
    # leaves CG non-converged and the potential divergent. Verify by KCL -- the current arriving at the
    # pinned sink must equal the injected I -- plus finiteness + a sane IR-drop bound. Else None (the
    # caller keeps the analytic estimate for this net rather than emitting garbage).
    into_K = (eb == K)
    sink_I = float(np.sum(eg[into_K] * (v[ea[into_K]] - v[K])))
    ir_drop = float(v[S] - v[K])                   # = v[S]; K pinned at 0
    if (not np.isfinite(v).all()) or rel > 1e-3 or ir_drop <= 0 or ir_drop > 5.0 \
            or abs(sink_I - I) > 0.05 * max(I, 1e-9):
        return None

    flow = eg * (v[ea] - v[eb])                    # A per edge
    lat = et > 0
    area = et[lat] * h * 1e-3                      # edge cross-section m^2 (thickness * cell width)
    J = np.abs(flow[lat]) / np.where(area > 0, area, 1.0) / 1e6   # A/mm^2
    if J.size == 0:
        return None
    return {
        "ir_drop_V": round(ir_drop, 5),
        "j_max_A_mm2": round(float(J.max()), 1),
        "j_p995_A_mm2": round(float(np.percentile(J, 99.5)), 1),
        "eff_cross_mm2": round(I / max(float(np.percentile(J, 99.5)), 1e-6), 4),
        "n_nodes": int(n), "n_lat_edges": int(lat.sum()), "n_vias": n_vias,
        "layers": [name for (_, name, _) in lset], "I": round(I, 1), "grid_mm": h,
    }


def solve(board_path, *, currents=None, h=0.4, oz_outer=2.0, oz_inner=1.0, verbose=False):
    """Solve every poured, non-GND high-current force net on a routed board. `currents` maps
    net -> design amps (else a name-based default). Returns {net: result|None}."""
    b = pcbnew.LoadBoard(board_path)
    layers = _cu_layers(b)
    names = sorted({ni.GetNetname() for ni in b.GetNetInfo().NetsByNetcode().values() if ni.GetNetname()})
    poured = {z.GetNetname() for z in b.Zones()}

    def default_current(net):
        leaf = net.rsplit("/", 1)[-1]
        if leaf == "GND":
            return 0.0
        if "12V" in net:
            return 15.0
        if "5VSB" in net:
            return 3.0
        if net.endswith(("5V_HI", "5V_LO")) or "RAIL5V" in net:
            return 20.0
        if "3V3" in net:
            return 20.0
        if net.endswith(("_HI", "_LO")):
            return 40.0
        return 0.0

    out = {}
    for net in names:
        if net.rsplit("/", 1)[-1] == "GND" or net not in poured:
            continue
        I = (currents or {}).get(net, default_current(net))
        if I <= 0:
            continue
        try:
            res = solve_net(b, net, I, layers, h, oz_outer=oz_outer, oz_inner=oz_inner)
        except Exception as e:
            res = None
            if verbose:
                print(f"  {net}: solver error: {e}")
        out[net] = res
        if verbose and res:
            print(f"  {net:18s} I={res['I']:5.1f}A  IRdrop={res['ir_drop_V']*1000:6.1f} mV  "
                  f"J(99.5%)={res['j_p995_A_mm2']:6.1f} (max {res['j_max_A_mm2']:.0f}) A/mm^2  "
                  f"eff_cross={res['eff_cross_mm2']:.3f} mm^2  [{','.join(res['layers'])}]  "
                  f"nodes={res['n_nodes']} vias={res['n_vias']}")
        elif verbose:
            print(f"  {net:18s} -> None (no 2-terminal force path / no copper)")
    return out


def _main(argv=None):
    ap = argparse.ArgumentParser(description="2.5D DC IR-drop / current-density field solve on routed copper.")
    ap.add_argument("board", nargs="?",
                    default=os.path.join(ROOT, "modules", "atx-24pin-rev2", "24pin-module.kicad_pcb"))
    ap.add_argument("--h", type=float, default=0.4, help="grid pitch (mm); finer = slower, more faithful necking")
    ap.add_argument("--oz-outer", type=float, default=2.0, help="outer-layer copper weight (oz)")
    ap.add_argument("--oz-inner", type=float, default=1.0, help="inner-layer copper weight (oz)")
    a = ap.parse_args(argv)
    print(f"DC IR-drop solve: {os.path.relpath(a.board, ROOT)}  (grid {a.h} mm, "
          f"{a.oz_outer}oz outer / {a.oz_inner}oz inner)")
    res = solve(a.board, h=a.h, oz_outer=a.oz_outer, oz_inner=a.oz_inner, verbose=True)
    n_ok = sum(1 for v in res.values() if v)
    print(f"\nsolved {n_ok}/{len(res)} poured high-current nets")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
