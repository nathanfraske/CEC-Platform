#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed electro-thermal screening for bolted XFCN daughterboards.

This is a computational design gate, not a substitute for incoming inspection,
four-wire coupon resistance/temperature-rise tests, torque qualification, or a
3-D assembly solve.  It deliberately injects current on the physical F.Cu clamp
face and lets current reach other layers only through modeled plated barrels.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import cec_thermal2d as thermal  # noqa: E402


DEFAULT_COPPER_NOMINAL_MM = {
    "F.Cu": 0.070,
    "In1.Cu": 0.035,
    "In2.Cu": 0.035,
    "B.Cu": 0.070,
}
DEFAULT_DIELECTRIC_NOMINAL_MM = {
    ("F.Cu", "In1.Cu"): 0.200,
    ("In1.Cu", "In2.Cu"): 1.065,
    ("In2.Cu", "B.Cu"): 0.200,
}


PROJECTS = {
    "atx-db": {
        "board": "beta/output-daughterboards/atx24-out-db/atx24-out-db-board.kicad_pcb",
        "currents_A": {
            "+12V": 20.0, "+5V": 37.5, "+3V3": 30.0,
            "+5VSB": 7.5, "GND": 72.5,
        },
        "overrides": {
            "+12V": {"refs_src": ["J10"], "refs_sink": ["J1"],
                      "source_layers": ["F.Cu"]},
            "+5V": {"refs_src": ["J11"], "refs_sink": ["J1"],
                     "source_layers": ["F.Cu"]},
            "+3V3": {"refs_src": ["J13"], "refs_sink": ["J1"],
                      "source_layers": ["F.Cu"]},
            "+5VSB": {"refs_src": ["J15"], "refs_sink": ["J1"],
                       "source_layers": ["F.Cu"]},
            "GND": {"refs_src": ["J1"], "refs_sink": ["J16", "J19"],
                    "sink_layers": ["F.Cu"]},
        },
        # Conservative allowed current imbalance for the two parallel GND joints.
        "contact_branch_A": {
            "J10": 20.0, "J11": 37.5, "J13": 30.0, "J15": 7.5,
            "J16": 40.0, "J19": 32.5,
        },
        # This is the JLCPCB-supported 4-layer, 1.6 mm, 2 oz outer/inner
        # construction.  The exact pressed dielectric geometry is deliberately
        # left at the board declaration until it is confirmed by the quote/CAM
        # stackup; the electrical screen depends on the declared copper weights.
        "copper_nominal_mm": {
            "F.Cu": 0.070, "In1.Cu": 0.070,
            "In2.Cu": 0.070, "B.Cu": 0.070,
        },
        # Per-path allocation, not a universal voltage-regulation limit.  It
        # is deliberately tighter on the three major rails and allows the
        # lower-current standby rail a little more absolute routing loss.
        "max_copper_drop_mV": {
            "+12V": 35.0, "+5V": 35.0, "+3V3": 25.0,
            "+5VSB": 45.0, "GND": 35.0,
        },
        "fab_stackup": "JLCPCB 4L 1.6mm JLC3313 2oz outer/inner",
    },
    "eps-db": {
        "board": "beta/output-daughterboards/eps-out-db/eps-out-db-board.kicad_pcb",
        "currents_A": {"+12V": 65.0, "GND": 65.0},
        "overrides": {
            "+12V": {"refs_src": ["J13", "J14"], "refs_sink": ["J1"],
                      "source_layers": ["F.Cu"]},
            "GND": {"refs_src": ["J1"], "refs_sink": ["J10", "J11"],
                    "sink_layers": ["F.Cu"]},
        },
        # One member may reach the 40 A part rating; the other carries remainder.
        "contact_branch_A": {"J13": 40.0, "J14": 25.0,
                             "J10": 40.0, "J11": 25.0},
        "max_copper_drop_mV": 25.0,
    },
    "pcie-db": {
        "board": "beta/output-daughterboards/pcie-out-db/pcie-out-db-board.kicad_pcb",
        "currents_A": {"+12V": 48.75, "GND": 48.75},
        "overrides": {
            "+12V": {"refs_src": ["J10"], "refs_sink": ["J1"],
                      "source_layers": ["F.Cu"]},
            "GND": {"refs_src": ["J1"], "refs_sink": ["J13"],
                    "sink_layers": ["F.Cu"]},
        },
        "contact_branch_A": {"J10": 48.75, "J13": 48.75},
        "max_copper_drop_mV": 25.0,
    },
}


def _copper_nominal_mm(cfg):
    return cfg.get("copper_nominal_mm", DEFAULT_COPPER_NOMINAL_MM)


def _dielectric_nominal_mm(cfg):
    return cfg.get("dielectric_nominal_mm", DEFAULT_DIELECTRIC_NOMINAL_MM)


SCENARIOS = {
    "nominal_still_air": {
        "ambient_C": 50.0,
        "copper_factor": 1.0,
        "plating_um": 25.0,
        "c_nat": 1.40,
        # Area-weighted approximation: mostly black mask, small exposed ENIG lands.
        "eps_rad": 0.75,
    },
    "worst_material_restricted_air": {
        "ambient_C": 60.0,
        "copper_factor": 0.80,
        "plating_um": 20.0,
        # Conservative restricted-natural-convection and low-radiation bounds.
        "c_nat": 1.00,
        "eps_rad": 0.10,
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _declared_stackup(path: Path, layers):
    text = path.read_text(encoding="utf-8")
    copper = {}
    for layer in layers:
        match = re.search(
            r'\(layer\s+"' + re.escape(layer) +
            r'"\s+\(type\s+"copper"\)\s+\(thickness\s+([0-9.]+)\)',
            text, re.DOTALL)
        if match:
            copper[layer] = float(match.group(1))
    dielectrics = [float(v) for v in re.findall(
        r'\(layer\s+"dielectric\s+\d+".*?\(thickness\s+([0-9.]+)\).*?'
        r'\(material\s+"FR4"\)', text, re.DOTALL)]
    finish = re.search(r'\(copper_finish\s+"([^"]+)"\)', text)
    return copper, dielectrics, finish.group(1) if finish else None


def preflight_project(name: str) -> dict:
    cfg = PROJECTS[name]
    board = ROOT / cfg["board"]
    expected_copper = _copper_nominal_mm(cfg)
    expected_dielectric_map = _dielectric_nominal_mm(cfg)
    copper, dielectrics, finish = _declared_stackup(board, expected_copper)
    errors = []
    if copper != expected_copper:
        errors.append(f"declared copper {copper!r} != required {expected_copper!r}")
    expected_dielectrics = list(expected_dielectric_map.values())
    if dielectrics[:3] != expected_dielectrics:
        errors.append(
            f"declared FR4 dielectric {dielectrics[:3]!r} != {expected_dielectrics!r}")
    if finish != "ENIG":
        errors.append(f"copper finish {finish!r} != current ENIG declaration")
    text = board.read_text(encoding="utf-8")
    for ref in cfg["contact_branch_A"]:
        if f'property "Reference" "{ref}"' not in text:
            errors.append(f"missing modeled bolt-land reference {ref}")
    return {
        "project": name,
        "board": cfg["board"],
        "board_sha256": _sha256(board),
        "declared_copper_mm": copper,
        "declared_dielectric_mm": dielectrics[:3],
        "required_copper_mm": expected_copper,
        "required_dielectric_mm": expected_dielectrics,
        "fab_stackup": cfg.get("fab_stackup"),
        "finish": finish,
        "errors": errors,
        "pass": not errors,
    }


def _run_case(spec: dict) -> dict:
    name = spec["project"]
    cfg = PROJECTS[name]
    scenario = SCENARIOS[spec["scenario"]]
    contact_mohm = spec["contact_mohm"]
    factor = scenario["copper_factor"]
    stackup_oz = {
        layer: thickness_mm * factor / (thermal.OZ_M * 1e3)
        for layer, thickness_mm in _copper_nominal_mm(cfg).items()
    }
    component_power = {
        ref: current_A * current_A * contact_mohm * 1e-3
        for ref, current_A in cfg["contact_branch_A"].items()
    }
    board = ROOT / cfg["board"]
    result = thermal.solve_board_thermal(
        str(board), stackup_oz=stackup_oz,
        dielectric_mm=_dielectric_nominal_mm(cfg),
        net_currents=cfg["currents_A"],
        src_sink_override=cfg["overrides"],
        component_power=component_power,
        ambient=scenario["ambient_C"], grid_mm=spec["grid_mm"],
        t_plating_um=scenario["plating_um"],
        nonlinear=True, c_nat=scenario["c_nat"], eps_rad=scenario["eps_rad"],
        backend="cpu", include_traces=True, area_injection=True, rho_T=True,
        board_mask_enable=True, verbose=False)
    dropped = {**result.nets_absent, **result.nets_dropped}
    dt = result.max_T - result.ambient
    return {
        **spec,
        "max_T_C": round(result.max_T, 4),
        "delta_T_C": round(dt, 4),
        "total_joule_W": round(result.total_joule_W, 6),
        "copper_joule_W": round(result.meta.get("copper_joule_W", math.nan), 6),
        "contact_heat_W": round(sum(component_power.values()), 6),
        "contact_heat_by_ref_W": {k: round(v, 6) for k, v in component_power.items()},
        "per_net_max_T_C": {k: round(v, 4) for k, v in result.per_net_maxT.items()},
        "per_net_max_J_A_per_mm2": {
            k: round(v, 3) for k, v in result.per_net_maxJ.items()},
        "top_current_bottlenecks": result.current_bottlenecks[:32],
        "nets_dropped_or_absent": dropped,
        "injection_complete": not dropped,
        "thermal_gate_pass": not dropped and dt <= 30.0 and result.max_T <= 105.0,
        "scenario_inputs": scenario,
    }


def _run_dcir_project(spec: dict) -> dict:
    """Isothermal 20 C copper resistance, isolated per net for diagnosis."""
    name = spec["project"]
    grid_mm = spec["grid_mm"]
    cfg = PROJECTS[name]
    stackup_oz = {
        layer: thickness_mm / (thermal.OZ_M * 1e3)
        for layer, thickness_mm in _copper_nominal_mm(cfg).items()
    }
    board = ROOT / cfg["board"]
    nets = {}
    for net, current in cfg["currents_A"].items():
        result = thermal.solve_board_thermal(
            str(board), stackup_oz=stackup_oz,
            dielectric_mm=_dielectric_nominal_mm(cfg),
            net_currents={net: current},
            src_sink_override={net: cfg["overrides"][net]},
            ambient=20.0, grid_mm=grid_mm, t_plating_um=25.0,
            nonlinear=False, h_eff=15.0, backend="cpu",
            include_traces=True, area_injection=True, ideal_pad_faces=False,
            rho_T=False, board_mask_enable=True, verbose=False)
        power = result.meta["copper_joule_W"]
        resistance = power / (current * current)
        drop_mV = resistance * current * 1e3
        configured_limit = cfg.get("max_copper_drop_mV", math.inf)
        drop_limit_mV = float(
            configured_limit.get(net, math.inf)
            if isinstance(configured_limit, dict) else configured_limit)
        injection_complete = not result.nets_dropped and not result.nets_absent
        nets[net] = {
            "current_A": current,
            "copper_power_W": round(power, 6),
            "copper_resistance_mohm": round(resistance * 1e3, 6),
            "copper_drop_mV": round(drop_mV, 6),
            "copper_drop_limit_mV": drop_limit_mV,
            "max_J_A_per_mm2": round(result.per_net_maxJ.get(net, 0.0), 3),
            "top_current_bottlenecks": result.current_bottlenecks[:16],
            "injection_complete": injection_complete,
            "copper_path_gate_pass": bool(
                injection_complete and drop_mV <= drop_limit_mV),
            "dropped_or_absent": {**result.nets_absent, **result.nets_dropped},
        }
    return {
        "project": name,
        "grid_mm": grid_mm,
        "nets": nets,
        "total_copper_power_W": round(
            sum(row["copper_power_W"] for row in nets.values()), 6),
        "copper_path_gate_pass": all(
            row["copper_path_gate_pass"] for row in nets.values()),
    }


def _case_key(row):
    return (row["project"], row["scenario"], row["grid_mm"], row["contact_mohm"])


def build_cases(projects, fine_grid, convergence_grids, contact_sweep):
    cases = []
    for project in projects:
        # Nominal reality check at the final grid.
        cases.append({"project": project, "scenario": "nominal_still_air",
                      "grid_mm": fine_grid, "contact_mohm": 0.2,
                      "purpose": "nominal"})
        # Grid convergence at a midrange interface resistance.
        for grid in convergence_grids:
            cases.append({"project": project,
                          "scenario": "worst_material_restricted_air",
                          "grid_mm": grid, "contact_mohm": 0.2,
                          "purpose": "grid_convergence"})
        # Contact-resistance sensitivity on the finest grid.
        for resistance in contact_sweep:
            cases.append({"project": project,
                          "scenario": "worst_material_restricted_air",
                          "grid_mm": fine_grid, "contact_mohm": resistance,
                          "purpose": "contact_sweep"})
    # Deduplicate overlaps such as fine-grid/0.2 mOhm.
    unique = {_case_key(case): case for case in cases}
    return [unique[key] for key in sorted(unique)]


def summarize(preflight, cases, dcir, convergence_grids, contact_sweep):
    projects = sorted({row["project"] for row in cases})
    summary = {}
    for name in projects:
        rows = [row for row in cases if row["project"] == name]
        worst_rows = [row for row in rows
                      if row["scenario"] == "worst_material_restricted_air"]
        convergence = sorted(
            [row for row in worst_rows if row["contact_mohm"] == 0.2 and
             row["grid_mm"] in convergence_grids],
            key=lambda row: row["grid_mm"], reverse=True)
        # Convergence is judged on the two finest meshes. Coarser meshes are
        # diagnostic only because a grid at/above a narrow trace width can lose
        # topology even when the source board is connected.
        finest = sorted(convergence, key=lambda row: row["grid_mm"])[:2]
        conv_delta = conv_relative = None
        if len(finest) >= 2:
            conv_delta = abs(finest[0]["max_T_C"] - finest[1]["max_T_C"])
            conv_relative = conv_delta / max(abs(finest[0]["max_T_C"]), 1.0)
        sweep = sorted(
            [row for row in worst_rows if row["grid_mm"] == min(convergence_grids)
             and row["contact_mohm"] in contact_sweep],
            key=lambda row: row["contact_mohm"])
        passing = [row["contact_mohm"] for row in sweep if row["thermal_gate_pass"]]
        gate_rows = [row for row in rows if row["purpose"] != "grid_convergence"] + finest
        summary[name] = {
            "preflight_pass": next(row["pass"] for row in preflight
                                   if row["project"] == name),
            "injection_complete_gate_cases": all(
                row["injection_complete"] for row in gate_rows),
            "grid_convergence_span_C": None if conv_delta is None else round(conv_delta, 4),
            "grid_convergence_relative": (
                None if conv_relative is None else round(conv_relative, 6)),
            "grid_convergence_pass": (
                conv_delta is not None and (conv_delta <= 2.0 or conv_relative <= 0.05)),
            "largest_tested_contact_resistance_passing_mohm": max(passing) if passing else None,
            "all_0p2_mohm_cases_pass": all(
                row["thermal_gate_pass"] for row in rows
                if row["contact_mohm"] == 0.2),
            "copper_path_gate_pass": dcir[name]["copper_path_gate_pass"],
        }
        summary[name]["computational_screen_pass"] = all((
            summary[name]["preflight_pass"],
            summary[name]["injection_complete_gate_cases"],
            summary[name]["grid_convergence_pass"],
            summary[name]["all_0p2_mohm_cases_pass"],
            summary[name]["copper_path_gate_pass"],
        ))
    return summary


def markdown_report(payload):
    lines = [
        "# XFCN bolted daughterboard electro-thermal validation",
        "",
        f"Generated: {payload['generated']}",
        "",
        "> Scope: conservative 2.5-D field screening of the current committed daughterboard copper. "
        "This is not a 3-D terminal/body/contact solve and does not release the physical joint.",
        "",
        "## Outcome",
        "",
        "| Board | Computational screen | Fine-grid span (C / relative) | Largest tested Rcontact passing (mohm/interface) |",
        "|---|---:|---:|---:|",
    ]
    for name, row in payload["summary"].items():
        limit = row["largest_tested_contact_resistance_passing_mohm"]
        lines.append(
            f"| {name} | {'PASS' if row['computational_screen_pass'] else 'FAIL'} | "
            f"{row['grid_convergence_span_C']} / {row['grid_convergence_relative']} | "
            f"{limit if limit is not None else 'none'} |")
    lines.extend([
        "",
        "## Contact-system decision",
        "",
        "The primary electrical and thermal interface is direct contact between the flat, plated "
        "terminal face and the exposed F.Cu clamp land. The screw supplies preload; the washer "
        "distributes preload on the opposite face. No soft thermal pad, conductive elastomer, "
        "grease, or unspecified conforming interposer is credited electrically or thermally.",
        "",
        "Production release remains blocked until incoming geometry, surface finish, flatness, "
        "fastener stack, torque retention, four-wire joint resistance, thermal rise, cycling, "
        "and JLC THT/process compatibility are measured on representative coupons.",
        "",
        "Temperatures above the 105 C gate are fail indicators, not material predictions: the "
        "linear copper TCR and simplified boundary model are intentionally not extrapolated as "
        "qualified physics at destructive temperatures.",
        "",
        "## Isothermal copper-path diagnosis (20 C)",
        "",
        "| Board | Net | Current A | Rcu mOhm | Drop / limit mV | Copper heat W | Path gate |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for project in sorted(payload.get("dcir", {})):
        for net, row in payload["dcir"][project]["nets"].items():
            lines.append(
                f"| {project} | {net} | {row['current_A']} | "
                f"{row['copper_resistance_mohm']} | {row['copper_drop_mV']} / "
                f"{row['copper_drop_limit_mV']} | {row['copper_power_W']} | "
                f"{'PASS' if row['copper_path_gate_pass'] else 'FAIL'} |")
    lines.extend([
        "",
        "## Detailed cases",
        "",
        "| Board | Scenario | Grid mm | Rcontact mohm | Tmax C | dT C | Heat W | Injected | Gate |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in sorted(payload["cases"], key=_case_key):
        lines.append(
            f"| {row['project']} | {row['scenario']} | {row['grid_mm']} | "
            f"{row['contact_mohm']} | {row['max_T_C']} | {row['delta_T_C']} | "
            f"{row['total_joule_W']} | {'yes' if row['injection_complete'] else 'NO'} | "
            f"{'PASS' if row['thermal_gate_pass'] else 'FAIL'} |")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", choices=sorted(PROJECTS))
    parser.add_argument("--fine-grid-mm", type=float, default=0.25)
    parser.add_argument("--convergence-grids-mm", default="0.50,0.35,0.25")
    parser.add_argument("--contact-sweep-mohm", default="0,0.1,0.2,0.5,1.0")
    parser.add_argument("--jobs", type=int, default=min(3, os.cpu_count() or 1))
    parser.add_argument("--output-dir", default="output/xfcn-electrothermal-20260812")
    args = parser.parse_args(argv)

    projects = args.project or sorted(PROJECTS)
    grids = sorted({float(v) for v in args.convergence_grids_mm.split(",")}, reverse=True)
    if args.fine_grid_mm not in grids:
        grids.append(args.fine_grid_mm)
        grids.sort(reverse=True)
    contacts = sorted({float(v) for v in args.contact_sweep_mohm.split(",")})
    out_dir = ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    preflight = [preflight_project(name) for name in projects]
    if not all(row["pass"] for row in preflight):
        payload = {"generated": "2026-08-12", "preflight": preflight,
                   "cases": [], "summary": {}, "production_release": False}
    else:
        specs = build_cases(projects, args.fine_grid_mm, grids, contacts)
        with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            cases = list(pool.map(_run_case, specs))
        with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            dcir_rows = list(pool.map(
                _run_dcir_project,
                ({"project": project, "grid_mm": args.fine_grid_mm}
                 for project in projects)))
        payload = {
            "schema_version": 1,
            "generated": "2026-08-12",
            "solver": "scripts/cec_thermal2d.py 2.5-D steady-state field",
            "solver_sha256": _sha256(HERE / "cec_thermal2d.py"),
            "preflight": preflight,
            "cases": cases,
            "dcir": {row["project"]: row for row in dcir_rows},
            "summary": summarize(
                preflight, cases, {row["project"]: row for row in dcir_rows},
                grids, contacts),
            "thermal_gate": {"max_delta_T_C": 30.0, "max_absolute_T_C": 105.0},
            "copper_path_gate": {
                "method": "per-net isothermal 20 C DC field solve",
                "default_max_drop_mV": 25.0,
            },
            "production_release": False,
            "release_blockers": [
                "incoming terminal geometry and finish measurements",
                "3-D terminal/body/contact constriction model or correlated coupon data",
                "four-wire joint resistance and temperature-rise coupon testing",
                "fastener, washer, torque-retention, cycling, and reuse qualification",
                "JLC THT process confirmation",
            ],
        }
    (out_dir / "results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps({"output": str(out_dir), "summary": payload["summary"],
                      "production_release": False}, indent=2))
    return 0 if payload.get("summary") and all(
        row["computational_screen_pass"] for row in payload["summary"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
