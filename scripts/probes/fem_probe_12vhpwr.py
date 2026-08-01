#!/usr/bin/env python3
"""Steady-state 2.5D field probe for the 12VHPWR Standard board.

The scenario is one JSON object passed as argv[1]:

  {"name": "balanced", "pin_A": {"1": 8.0, ...}, "gnd_A": 48.0,
   "ambient_env": "enclosed_passive", "grid_mm": 0.3,
   "backend": "auto"}

Currents are explicit because this board models each lane separately. The probe
refuses transient scenarios: cec_thermal2d is a steady-state field solver and a
transient value would otherwise be silently ignored. Exit 0 means both complete
current injection and zero blocking physics flags. Exit 2 means incomplete
injection. Exit 3 means the solve completed but failed a physics gate.
"""

import json
import math
import os
import sys


VALID_PINS = {str(index) for index in range(1, 7)}
VALID_BACKENDS = {"auto", "cpu", "gpu"}
VALID_AMBIENT_ENVS = {"enclosed_passive", "airflow", "worst_case"}
USAGE = "usage: fem_probe_12vhpwr.py '<scenario-json>'"


def parse_scenario(raw):
    """Parse and validate the complete electrical input before solving."""
    scenario = json.loads(raw)
    if not isinstance(scenario, dict):
        raise ValueError("scenario must be a JSON object")
    name = scenario.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("scenario.name must be a non-empty string")
    pins = scenario.get("pin_A")
    if not isinstance(pins, dict) or not pins:
        raise ValueError("scenario.pin_A must be a non-empty object")
    unknown = sorted(set(map(str, pins)) - VALID_PINS)
    if unknown:
        raise ValueError("unsupported 12VHPWR pin lane(s): %s" % ", ".join(unknown))

    normalized = {}
    for pin, value in pins.items():
        try:
            amps = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("pin_A[%s] must be numeric" % pin) from exc
        if not math.isfinite(amps) or amps <= 0:
            raise ValueError("pin_A[%s] must be finite and greater than zero" % pin)
        normalized[str(pin)] = amps

    try:
        gnd = float(scenario.get("gnd_A"))
    except (TypeError, ValueError) as exc:
        raise ValueError("scenario.gnd_A must be numeric") from exc
    if not math.isfinite(gnd) or gnd <= 0:
        raise ValueError("scenario.gnd_A must be finite and greater than zero")
    lane_total = sum(normalized.values())
    if not math.isclose(gnd, lane_total, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError(
            "gnd_A %.9g A does not equal the %.9g A lane-current sum" %
            (gnd, lane_total))
    if scenario.get("transient") is not None:
        raise ValueError(
            "transient input is unsupported by the steady-state cec_thermal2d field solver")

    backend = str(scenario.get("backend", "auto"))
    if backend not in VALID_BACKENDS:
        raise ValueError("backend must be one of: auto, cpu, gpu")
    ambient_env = str(scenario.get("ambient_env", "enclosed_passive"))
    if ambient_env not in VALID_AMBIENT_ENVS:
        raise ValueError(
            "ambient_env must be one of: airflow, enclosed_passive, worst_case")
    grid = scenario.get("grid_mm")
    if grid is not None:
        try:
            grid = float(grid)
        except (TypeError, ValueError) as exc:
            raise ValueError("grid_mm must be numeric") from exc
        if not math.isfinite(grid) or grid <= 0:
            raise ValueError("grid_mm must be finite and greater than zero")

    result = dict(scenario)
    result["name"] = name.strip()
    result["pin_A"] = normalized
    result["gnd_A"] = gnd
    result["backend"] = backend
    result["ambient_env"] = ambient_env
    result["grid_mm"] = grid
    return result


def apply_scenario(cfg, scenario, ambient_by_env):
    """Apply every validated scenario input to the actual solver config."""
    currents = {}
    for pin, amps in scenario["pin_A"].items():
        currents["/SENSEP%s_HI" % pin] = amps
        currents["/SENSEP%s_LO" % pin] = amps
    currents["GND"] = scenario["gnd_A"]
    env = scenario["ambient_env"]
    if env not in ambient_by_env:
        raise ValueError("solver has no ambient mapping for %s" % env)
    cfg.params["net_currents"] = currents
    cfg.params["thermal_env"] = env
    cfg.params["ambient_C"] = float(ambient_by_env[env])
    return currents


def injection_report(field):
    """Return fail-closed current-injection accounting for one field result."""
    requested = dict(field.nets_requested)
    dropped = dict(field.nets_dropped)
    absent = dict(field.nets_absent)
    injected = {
        net: amps for net, amps in requested.items()
        if net not in dropped and net not in absent
    }
    return {
        "complete": bool(requested) and not dropped and not absent,
        "requested_A": requested,
        "injected_A": injected,
        "dropped": dropped,
        "absent": absent,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["-h"], ["--help"]):
        print(__doc__.strip())
        print("\n" + USAGE)
        return 0
    if len(argv) != 1:
        raise SystemExit(USAGE)
    scenario = parse_scenario(argv[0])

    scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    sys.path.insert(0, scripts)
    import cec_synth_pipeline as sp

    cfg = sp.Config.load("12vhpwr-standard")
    apply_scenario(cfg, scenario, sp._AMBIENT)

    result = sp.field_electrothermal_solve(
        cfg.pcb, cfg, grid_mm=scenario["grid_mm"],
        backend=scenario["backend"])
    field = result.field
    injection = injection_report(field)
    flags = sp.physics_gates(result, cfg)
    blocking_flags = [flag for flag in flags if flag.binding == "gate"]

    nets = []
    for net, data in result.nets.items():
        if data.get("I", 0) > 0:
            nets.append({
                "net": net,
                **{key: (round(value, 3) if isinstance(value, float) else value)
                   for key, value in data.items()},
            })
    nets.sort(key=lambda item: -item.get("dT", 0))
    complete = injection["complete"]
    physics_ok = not blocking_flags
    output = {
        "ok": complete and physics_ok,
        "scenario": scenario["name"],
        "solver": "cec_thermal2d 2.5D steady-state field",
        "calibration": result.calibration,
        "backend_requested": scenario["backend"],
        "backend_resolved": field.meta.get("backend"),
        "cooling": result.cooling,
        "grid_mm": result.grid_mm,
        "ambient_C": result.ambient,
        "max_T_C": round(result.max_T, 1),
        "max_dT_C": round(result.max_dT, 1),
        "joule_W": round(field.total_joule_W, 6),
        "thermal_loss_W": round(field.total_convected_W, 6),
        "nets": nets,
        "injection": injection,
        "physics": {
            "ok": physics_ok,
            "blocking_flags": [{
                "name": flag.name,
                "where": str(flag.where),
                "kind": flag.kind.value,
                "detail": flag.detail,
            } for flag in blocking_flags],
        },
    }
    print(json.dumps(output, indent=1, default=str))
    if not complete:
        return 2
    return 0 if physics_ok else 3


if __name__ == "__main__":
    sys.exit(main())
