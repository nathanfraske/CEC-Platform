#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_spice -- SCHEMATIC-side analog-cell verification through ngspice (owner GO,
2026-07-08: "yes the SPICE solver should be added" -- cross-check against proper reality).

Scope (the roadmap's rung 2, docs/pipeline-solver-roadmap.md): SPICE verifies the ANALOG
CELLS' circuit math -- trip thresholds, gains, saturation, tolerance spreads -- once per
SCHEMATIC change (the MEASURE stage), never per placement candidate. It is NOT a board/
field solver (no layout geometry; that's the PDN/electrostatic rungs).

PILOT: the sec6.13 transient-detection chain (shunt -> INA181Ax gain -> TLV7011
comparator vs the THRESH PWM-DAC), per rail of the 24-pin rev3. MODELS are BEHAVIORAL
(TI's PSpice models are encrypted for ngspice): the CSA is a gain-limited controlled
source with datasheet Vos/gain-error bands, the comparator an offset-banded ideal switch
-- exactly enough physics for DC thresholds + Monte Carlo, refined only if a calibration
run ever demands more. Datasheet bands used (TI INA181 SBOS793, TLV7011 SBOS589):
INA181 gain error +/-1%, Vos RTI +/-150uV; TLV7011 Vos +/-5mV (max band); shunts +/-1%
(sec6.4 class); THRESH DAC = 3.3V * duty through R60 10k / C60 100n (DC = duty*3.3).

Verified against the standing HAND analysis (the reality cross-check teeth): the 5VSB
cell (A2 gain 50 on 25mOhm) saturates at ~2.64A -- SPICE must reproduce it.
"""
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile

NGSPICE = os.environ.get("CEC_NGSPICE", "ngspice")

# sec6.13 cells on the 24-pin rev3 (spec sec6.4 shunts; INA181A2 = gain 50 platform pick,
# deliberately kept on 5VSB per the G-pass gain-math ruling)
CELLS_24PIN = {
    "12V":  {"rshunt": 0.002, "gain": 50.0},
    "5V":   {"rshunt": 0.002, "gain": 50.0},
    "3V3":  {"rshunt": 0.002, "gain": 50.0},
    "5VSB": {"rshunt": 0.025, "gain": 50.0},
}
VS = 3.3          # CSA + comparator supply
SWING = 0.05      # INA181 swing-to-rail headroom (datasheet class)


def _cell_cir(rshunt, gain, vthresh, iload, *, vos_ina=0.0, gerr=0.0, vos_cmp=0.0,
              rtol=0.0):
    """One DC operating point of the detection chain at load current *iload*.
    B-source CSA: out = clamp(gain*(1+gerr)*(vsense + vos_ina), SWING, VS-SWING).
    Comparator: out = 1 when (csa - (vthresh + vos_cmp)) > 0."""
    rs = rshunt * (1.0 + rtol)
    return f"""* cec sec6.13 detection cell (behavioral)
I1 0 nhi DC {iload}
Rs nhi 0 {rs}
BCSA ncsa 0 V=min(max({gain * (1.0 + gerr)}*(V(nhi)+{vos_ina}), {SWING}), {VS - SWING})
BCMP nout 0 V=(V(ncsa) > {vthresh + vos_cmp}) ? 1 : 0
.control
op
print v(ncsa) v(nout)
.endc
.end
"""


def _run(cir):
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
        fh.write(cir)
        path = fh.name
    try:
        out = subprocess.run([NGSPICE, "-b", path], capture_output=True, text=True,
                             timeout=30).stdout
    finally:
        os.unlink(path)
    vals = {}
    for m in re.finditer(r"v\((\w+)\)\s*=\s*([-\d.eE+]+)", out):
        vals[m.group(1)] = float(m.group(2))
    return vals


def trip_current(rshunt, gain, vthresh, *, tol=0.001, imax=60.0, **err):
    """The load current at which the comparator trips (bisection over DC points)."""
    lo, hi = 0.0, imax
    if _run(_cell_cir(rshunt, gain, vthresh, hi, **err)).get("nout", 0) < 0.5:
        return None                                   # never trips inside range
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if _run(_cell_cir(rshunt, gain, vthresh, mid, **err)).get("nout", 0) > 0.5:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return round((lo + hi) / 2.0, 4)


def saturation_current(rshunt, gain, *, imax=200.0, tol=0.005):
    """Where the CSA output hits its TOP clamp (the measurable-range ceiling) --
    bisection on v(ncsa) >= VS-SWING. The 5VSB hand-math cross-check: (3.3-0.05)V /
    (50 * 25mOhm) ~= 2.6A. (A first walk-up detector false-fired on the LOW swing
    clamp at tiny currents -- teeth caught it.)"""
    ceiling = VS - SWING - 1e-3
    if _run(_cell_cir(rshunt, gain, 99.0, imax)).get("ncsa", 0.0) < ceiling:
        return None
    lo, hi = 0.0, imax
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if _run(_cell_cir(rshunt, gain, 99.0, mid)).get("ncsa", 0.0) >= ceiling:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return round((lo + hi) / 2.0, 3)


def monte_carlo(rshunt, gain, vthresh, *, n=120, seed=0):
    """Trip-current distribution over the datasheet tolerance bands: shunt +/-1%,
    gain +/-1%, INA Vos +/-150uV RTI, comparator Vos +/-5mV (uniform worst-case bands
    -- the conservative read; swap for gaussians when a calibration says so)."""
    rnd = random.Random(seed)
    trips = []
    for _ in range(n):
        t = trip_current(rshunt, gain, vthresh,
                         rtol=rnd.uniform(-0.01, 0.01),
                         gerr=rnd.uniform(-0.01, 0.01),
                         vos_ina=rnd.uniform(-150e-6, 150e-6),
                         vos_cmp=rnd.uniform(-5e-3, 5e-3))
        if t is not None:
            trips.append(t)
    if not trips:
        return {"n": 0}
    trips.sort()
    mean = sum(trips) / len(trips)
    var = sum((x - mean) ** 2 for x in trips) / len(trips)
    return {"n": len(trips), "mean_A": round(mean, 3), "sigma_A": round(math.sqrt(var), 4),
            "min_A": trips[0], "max_A": trips[-1],
            "spread_pct": round(100 * (trips[-1] - trips[0]) / mean, 1)}


def audit_detection_chain(cells=None, *, duty=0.5, mc_n=120):
    """The MEASURE-stage report: per rail, nominal trip vs analytic, the Monte Carlo
    band the FIRMWARE must expect, and the measurable-range ceiling (saturation)."""
    cells = cells or CELLS_24PIN
    vth = duty * VS
    rows = {}
    for rail, c in cells.items():
        analytic = vth / (c["gain"] * c["rshunt"])
        nom = trip_current(c["rshunt"], c["gain"], vth)
        sat = saturation_current(c["rshunt"], c["gain"])
        mc = monte_carlo(c["rshunt"], c["gain"], vth, n=mc_n)
        rows[rail] = {"vthresh": round(vth, 3), "analytic_A": round(analytic, 3),
                      "spice_trip_A": nom,
                      "agree_pct": (round(100 * (nom - analytic) / analytic, 2)
                                    if nom else None),
                      "saturation_A": sat, "monte_carlo": mc}
    return {"duty": duty, "vs": VS, "rails": rows}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="SPICE verification of the sec6.13 detection chain")
    ap.add_argument("--duty", type=float, default=0.5, help="THRESH PWM duty (DC = duty*3.3V)")
    ap.add_argument("--mc", type=int, default=120)
    a = ap.parse_args()
    print(json.dumps(audit_detection_chain(duty=a.duty, mc_n=a.mc), indent=1))


if __name__ == "__main__":
    main()
