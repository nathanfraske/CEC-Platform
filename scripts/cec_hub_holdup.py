#!/usr/bin/env python3
"""Deterministic Hub selected-rail dropout and hold-up design model.

This is a bounded engineering model, not a substitute for OQ-56 bench data.
It intentionally uses the selected capacitor's -20% tolerance, the SS14's
specified 0.55 V maximum forward drop at 1 A, a 50 mV source-path reserve,
the reviewed +3V3 load including 20% margin, and an 85% conversion floor.
"""
from __future__ import annotations

import argparse
import json
import math


HUB_LOAD_A = 0.215386
VOUT_V = 3.3
EFFICIENCY_FLOOR = 0.85
CAP_NOMINAL_F = 4700e-6
CAP_TOLERANCE = 0.20
SELECTED_RAIL_MIN_V = 4.75
SS14_VF_MAX_V = 0.55
SOURCE_PATH_RESERVE_V = 0.05
REGULATION_FLOOR_V = 3.45
PERSIST_BUDGET_MS = 10.0

SENSE_TOP_OHM = 47e3
SENSE_BOTTOM_OHM = 27e3
SENSE_CAP_F = 10e-9
REF_TOP_OHM = 11e3
REF_BOTTOM_OHM = 10e3
HYSTERESIS_OHM = 1e6
V3V3_NOMINAL_V = 3.318
V3V3_MIN_V = 3.199
V3V3_MAX_V = 3.440
RESISTOR_TOLERANCE = 0.01
COMPARATOR_ERROR_V = 0.015  # +/-8 mV VOS plus half of 14 mV max hysteresis.
VOH_FLOOR_RATIO = 0.94      # conservative ratio from the 5 V / 3 mA limit.


def _reference_ratio(r_top: float, r_bottom: float, r_hyst: float,
                     output_ratio: float) -> float:
    """COMP_THRESH / +3V3 while the comparator output is still high."""
    return ((1.0 / r_top) + (output_ratio / r_hyst)) / (
        (1.0 / r_top) + (1.0 / r_bottom) + (1.0 / r_hyst)
    )


def model() -> dict[str, float]:
    c_min = CAP_NOMINAL_F * (1.0 - CAP_TOLERANCE)
    start_v = SELECTED_RAIL_MIN_V - SS14_VF_MAX_V - SOURCE_PATH_RESERVE_V
    output_power = VOUT_V * HUB_LOAD_A
    usable_j = 0.5 * c_min * (start_v ** 2 - REGULATION_FLOOR_V ** 2)
    hold_ms = EFFICIENCY_FLOOR * usable_j / output_power * 1e3

    sense_nom = SENSE_BOTTOM_OHM / (SENSE_TOP_OHM + SENSE_BOTTOM_OHM)
    ref_nom = _reference_ratio(
        REF_TOP_OHM, REF_BOTTOM_OHM, HYSTERESIS_OHM, 1.0)
    trip_nom = V3V3_NOMINAL_V * ref_nom / sense_nom

    tol = RESISTOR_TOLERANCE
    sense_min = (SENSE_BOTTOM_OHM * (1 - tol)) / (
        SENSE_TOP_OHM * (1 + tol) + SENSE_BOTTOM_OHM * (1 - tol))
    sense_max = (SENSE_BOTTOM_OHM * (1 + tol)) / (
        SENSE_TOP_OHM * (1 - tol) + SENSE_BOTTOM_OHM * (1 + tol))
    ref_min = _reference_ratio(
        REF_TOP_OHM * (1 + tol), REF_BOTTOM_OHM * (1 - tol),
        HYSTERESIS_OHM * (1 + tol), VOH_FLOOR_RATIO)
    ref_max = _reference_ratio(
        REF_TOP_OHM * (1 - tol), REF_BOTTOM_OHM * (1 + tol),
        HYSTERESIS_OHM * (1 - tol), 1.0)
    trip_min = (V3V3_MIN_V * ref_min - COMPARATOR_ERROR_V) / sense_max
    trip_max = (V3V3_MAX_V * ref_max + COMPARATOR_ERROR_V) / sense_min

    source_headroom = trip_min - SS14_VF_MAX_V - REGULATION_FLOOR_V
    r_thevenin = SENSE_TOP_OHM * SENSE_BOTTOM_OHM / (
        SENSE_TOP_OHM + SENSE_BOTTOM_OHM)
    sense_tau_ms = r_thevenin * SENSE_CAP_F * 1e3
    step_crossing_us = r_thevenin * SENSE_CAP_F * math.log(
        5.0 / trip_nom) * 1e6

    return {
        "load_with_20pct_margin_A": HUB_LOAD_A,
        "cap_min_F": c_min,
        "reservoir_start_bound_V": start_v,
        "regulation_floor_bound_V": REGULATION_FLOOR_V,
        "sudden_loss_hold_ms": hold_ms,
        "persist_budget_ms": PERSIST_BUDGET_MS,
        "sudden_loss_margin_ms": hold_ms - PERSIST_BUDGET_MS,
        "trip_nominal_V": trip_nom,
        "trip_min_V": trip_min,
        "trip_max_V": trip_max,
        "trip_to_regulation_headroom_min_V": source_headroom,
        "sense_tau_ms": sense_tau_ms,
        "five_volt_step_crossing_us": step_crossing_us,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = model()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key, value in result.items():
            print(f"{key}: {value:.6g}")
    return 1 if (result["sudden_loss_margin_ms"] <= 0 or
                 result["trip_to_regulation_headroom_min_V"] <= 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
