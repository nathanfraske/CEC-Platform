#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render comparable qualification and hotspot maps for XFCN validation cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402
import numpy as np  # noqa: E402
import pcbnew  # noqa: E402

import cec_thermal2d as thermal  # noqa: E402
import cec_xfcn_thermal_validate as validation  # noqa: E402


def solve_nominal(project: str, grid_mm: float = 0.25, contact_mohm: float = 0.2):
    cfg = validation.PROJECTS[project]
    scenario = validation.SCENARIOS["nominal_still_air"]
    stackup_oz = {
        layer: thickness_mm / (thermal.OZ_M * 1e3)
        for layer, thickness_mm in validation._copper_nominal_mm(cfg).items()
    }
    component_power = {
        ref: current_A * current_A * contact_mohm * 1e-3
        for ref, current_A in cfg["contact_branch_A"].items()
    }
    result = thermal.solve_board_thermal(
        str(ROOT / cfg["board"]),
        stackup_oz=stackup_oz,
        dielectric_mm=validation._dielectric_nominal_mm(cfg),
        net_currents=cfg["currents_A"],
        src_sink_override=cfg["overrides"],
        component_power=component_power,
        ambient=scenario["ambient_C"],
        grid_mm=grid_mm,
        t_plating_um=scenario["plating_um"],
        nonlinear=True,
        c_nat=scenario["c_nat"],
        eps_rad=scenario["eps_rad"],
        backend="cpu",
        include_traces=True,
        area_injection=True,
        ideal_pad_faces=False,
        rho_T=True,
        board_mask_enable=True,
        verbose=False,
    )
    return result, component_power


def _ref_positions(board_path: Path, refs):
    board = pcbnew.LoadBoard(str(board_path))
    out = {}
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        if ref in refs or ref == "J1":
            pos = footprint.GetPosition()
            out[ref] = (pos.x / 1e6, pos.y / 1e6)
    return out


def render_project(project: str, out_dir: Path, grid_mm: float, contact_mohm: float):
    result, contact_power = solve_nominal(project, grid_mm, contact_mohm)
    cfg = validation.PROJECTS[project]
    positions = _ref_positions(ROOT / cfg["board"], cfg["contact_branch_A"])
    xmin, ymin, xmax, ymax = result.extent_mm
    extent = [xmin, xmax, ymax, ymin]
    dT = np.maximum(result.T - result.ambient, 1e-3)
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.2), constrained_layout=True)

    qual = axes[0].imshow(
        result.T, origin="upper", extent=extent, aspect="equal",
        cmap="inferno", vmin=result.ambient, vmax=105.0)
    axes[0].set_title("Qualification scale (50–105 °C)\n≥105 °C is saturated")
    fig.colorbar(qual, ax=axes[0], shrink=0.78, label="Temperature (°C)")

    hot = axes[1].imshow(
        dT, origin="upper", extent=extent, aspect="equal",
        cmap="magma", norm=LogNorm(vmin=max(float(dT.min()), 0.1),
                                   vmax=max(float(dT.max()), 1.0)))
    axes[1].set_title("Relative hotspot pattern (log ΔT)\nabove-gate values are not material predictions")
    fig.colorbar(hot, ax=axes[1], shrink=0.78, label="Temperature rise (°C, log scale)")

    for axis in axes:
        if result.T.min() <= result.ambient + 30.0 <= result.T.max():
            axis.contour(result.T, levels=[result.ambient + 30.0], colors="cyan",
                         linewidths=1.2, origin="upper", extent=extent)
        for ref, (x, y) in positions.items():
            axis.plot(x, y, marker="o", markersize=3.5, color="cyan")
            axis.annotate(ref, (x, y), xytext=(3, 3), textcoords="offset points",
                          color="cyan", fontsize=7, weight="normal")
        axis.set_xlabel("Board X (mm)")
        axis.set_ylabel("Board Y (mm)")
        axis.set_xlim(xmin, xmax)
        axis.set_ylim(ymax, ymin)

    injected = not result.nets_dropped and not result.nets_absent
    fig.suptitle(
        f"{project} — current PCB, nominal still air, {contact_mohm:g} mΩ/interface\n"
        f"model max {result.max_T:.1f} °C (ΔT {result.max_T-result.ambient:.1f} °C); "
        f"total heat {result.total_joule_W:.3f} W; injection {'complete' if injected else 'INCOMPLETE'}",
        fontsize=12)
    out_path = out_dir / f"{project}-nominal-thermal.png"
    fig.savefig(out_path, dpi=150, facecolor="white")
    plt.close(fig)

    # Preserve the electrical field instead of asking the temperature map to
    # imply where the copper narrowed.  A separate subplot per physical layer
    # makes zone-clearance necks, signal-cut pours, and PTH transfer regions
    # directly reviewable.
    layer_order = [name for name in thermal.STACK_ORDER
                   if name in result.layer_current_density]
    ncols = 2
    nrows = max(1, int(np.ceil(len(layer_order) / ncols)))
    jfig, jaxes = plt.subplots(
        nrows, ncols, figsize=(12.8, 4.6 * nrows), constrained_layout=True)
    jaxes = np.atleast_1d(jaxes).ravel()
    positive_parts = [
        field[field > 0] for field in result.layer_current_density.values()
        if np.any(field > 0)
    ]
    positive = np.concatenate(positive_parts) if positive_parts else np.array([])
    jmin = max(float(np.percentile(positive, 2.0)), 0.1) if positive.size else 0.1
    jmax = max(float(positive.max()), jmin * 10.0) if positive.size else 1.0
    last_im = None
    for axis, layer in zip(jaxes, layer_order):
        field = result.layer_current_density[layer]
        shown = np.ma.masked_less_equal(field, 0.0)
        last_im = axis.imshow(
            shown, origin="upper", extent=extent, aspect="equal", cmap="turbo",
            norm=LogNorm(vmin=jmin, vmax=jmax))
        copper = result.layer_copper_mask.get(layer)
        if copper is not None and copper.any() and (~copper).any():
            axis.contour(copper.astype(float), levels=[0.5], colors="black",
                         linewidths=0.35, origin="upper", extent=extent)
        records = [row for row in result.current_bottlenecks
                   if row.get("kind") == "sheet" and row.get("layer") == layer]
        seen = []
        for row in records:
            x, y = row["x_mm"], row["y_mm"]
            if any((x - px) ** 2 + (y - py) ** 2 < 2.0 ** 2 for px, py in seen):
                continue
            seen.append((x, y))
            axis.plot(x, y, marker="x", markersize=5, color="black")
            axis.annotate(
                f"{row['net']}\n{row['J_A_per_mm2']:.0f} A/mm^2", (x, y),
                xytext=(4, 4), textcoords="offset points", fontsize=7,
                color="black", bbox={"facecolor": "white", "alpha": 0.75,
                                     "edgecolor": "none", "pad": 1.0})
            if len(seen) >= 4:
                break
        axis.set_title(f"{layer} - peak {float(field.max()):.1f} A/mm^2")
        axis.set_xlabel("Board X (mm)")
        axis.set_ylabel("Board Y (mm)")
        axis.set_xlim(xmin, xmax)
        axis.set_ylim(ymax, ymin)
    for axis in jaxes[len(layer_order):]:
        axis.set_visible(False)
    if last_im is not None:
        jfig.colorbar(last_im, ax=list(jaxes[:len(layer_order)]), shrink=0.82,
                      label="Planar current density (A/mm^2, log scale)")
    jfig.suptitle(
        f"{project} - current-density / copper-neck diagnostic\n"
        "black outlines are the solved copper boundaries; x marks rank constriction links",
        fontsize=12)
    current_path = out_dir / f"{project}-current-density.png"
    jfig.savefig(current_path, dpi=150, facecolor="white")
    plt.close(jfig)
    return {
        "project": project,
        "path": str(out_path),
        "current_density_path": str(current_path),
        "max_T_C": round(result.max_T, 4),
        "delta_T_C": round(result.max_T - result.ambient, 4),
        "total_heat_W": round(result.total_joule_W, 6),
        "contact_heat_W": round(sum(contact_power.values()), 6),
        "injection_complete": injected,
        "max_current_density_A_per_mm2": {
            net: round(value, 3) for net, value in result.per_net_maxJ.items()},
        "top_current_bottlenecks": result.current_bottlenecks[:32],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", choices=sorted(validation.PROJECTS))
    parser.add_argument("--grid-mm", type=float, default=0.25)
    parser.add_argument("--contact-mohm", type=float, default=0.2)
    parser.add_argument("--output-dir", default="output/xfcn-electrothermal-20260812/renders")
    args = parser.parse_args(argv)
    out_dir = ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [render_project(project, out_dir, args.grid_mm, args.contact_mohm)
            for project in (args.project or sorted(validation.PROJECTS))]
    (out_dir / "render-index.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
