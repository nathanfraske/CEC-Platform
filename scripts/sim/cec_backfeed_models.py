#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""cec_backfeed_models -- shared ngspice device models + runner/parser for the
2026-07-24 USB-backfeed protection verification (docs/spice-backfeed-verify-2026-07-24.md).

Engine: real ngspice (v44.2, KLU solver), run inside docker-routing-1 (the repo's own
routing container, which already carries ngspice for scripts/cec_spice.py and
scripts/cec_spice_sanity.py -- this module follows their existing subprocess/tempfile
convention). NOT PySpice (PySpice is not installed on the host and would still need to
find/drive a real ngspice binary, which only exists in the container -- calling the
container's ngspice binary directly via ngspice -b is simpler and is the repo's own
established pattern).

Every .model card below cites the datasheet value(s) it is fit to. Where a datasheet
gives only ONE precise point (SS34's IF=3A/VF=0.55V; the 1206L PPTC families' single
'Maximum Time To Trip' row), the remaining SPICE parameters are a documented, physically
reasonable engineering estimate -- flagged as such, never presented as extracted.

Sources (all vendored or fetched 2026-07-24, see the report doc's Sources section):
  - TPS2121RUXR datasheet (TI SLVSEA3F), vendored at lib/datasheets/TPS2121RUXR.pdf.
    RON 56/70mOhm typ/max (Sec 7.5); ILIM law I_LIM=65.2/R_ILIM^0.861 kOhm->A (Sec 9.3.2,
    Eq 2); SS/soft-start slew-rate-vs-CSS Table 9-1; leakage ILK,INx -1/+1uA typ(25C) up
    to -500/+500uA over -40..125C (Sec 7.5); standby ISBY,INx 0-25uA; fast reverse-current
    blocking IRCB 0.2/1/2A min/typ/max, VRCB release 0/25/50mV, tRCB 10us (Sec 7.5, 9.3.6);
    OVx: internal VREF 1.01/1.06/1.10V min/typ/max, disconnect "immediately" on trip (9.3.5,
    no explicit numeric delay given -- modeled with an assumed few-us RC response, flagged).
  - 1206L Series PPTC datasheet (Littelfuse, Rev 02/25/19), fetched 2026-07-24 from the
    LCSC-hosted mirror of the part on our own BOM line (LCSC C371166 = 1206L075/16WR):
    1206L075/16 row: Ihold 0.75A, Itrip 1.50A, Vmax 16V, Pd 0.6W, Maximum-Time-To-Trip
    Current=8.00A/Time=0.20s, Rmin 0.090 Ohm, R1max 0.290 Ohm. 1206L110TH row (same family,
    nearest Ihold=1.10A member, used as the F5/KVM-polyfuse curve stand-in since the
    populated part, FUZETEC FSMD110-16-1206R, has no vendored curve but the same Ihold/Itrip
    class per docs/usb-ingress-bom-delta-2026-07-24.md): Ihold 1.10A, Itrip 2.20A,
    Maximum-Time-To-Trip Current=8.00A/Time=0.10s, Rmin 0.040 Ohm, R1max 0.210 Ohm.
  - SS32-SS3200 datasheet (MDD, Rev 2024A5), fetched 2026-07-24 from the LCSC mirror of our
    own BOM line (LCSC C8678 = MDD SS34): VF max 0.55V @ IF=3.0A, 25C (SS32-SS35 group);
    IR max 0.5mA @ rated VR=40V, 25C (same group); VRRM=40V.
"""
import os
import re
import subprocess

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
SCRATCH = os.path.join(REPO_ROOT, "build", "spice_scratch")
os.makedirs(SCRATCH, exist_ok=True)

# SPICE gotcha (hit + root-caused during development, see the report's Methodology
# section): the FIRST LINE of any .cir deck is unconditionally consumed as the title and
# silently discarded as a circuit element, even if it looks like a valid component line.
# Every deck built by this module's callers MUST start with TITLE (or its own '*' comment)
# -- forgetting it does not error, it just silently deletes your first real source/device,
# which is exactly the kind of failure that looks like a circuit bug instead of a netlist
# bug. TITLE is exported so case scripts open every cir_body with it.
TITLE = "* cec_backfeed_verify deck (see docs/spice-backfeed-verify-2026-07-24.md)\n"

DOCKER_CONTAINER = os.environ.get("CEC_ROUTING_CONTAINER", "docker-routing-1")

# --------------------------------------------------------------------------- runner
def run_ngspice(cir_text, name):
    """Write a deck to build/spice_scratch/<name>.cir (visible in the container at
    /workspace/build/spice_scratch/<name>.cir, since docker-routing-1 mounts the repo
    root at /workspace) and run it via `docker exec ... ngspice -b`. Returns
    (measures_dict, stdout, stderr). Raises on a container/ngspice launch failure (but
    NOT on ngspice printing convergence warnings -- those are surfaced in stderr for the
    caller to inspect)."""
    path = os.path.join(SCRATCH, f"{name}.cir")
    with open(path, "w") as f:
        f.write(cir_text)
    rel = os.path.relpath(path, REPO_ROOT)
    container_path = "/workspace/" + rel.replace(os.sep, "/")
    r = subprocess.run(
        ["docker", "exec", DOCKER_CONTAINER, "ngspice", "-b", container_path],
        capture_output=True, text=True, timeout=180,
    )
    return parse_measures(r.stdout), r.stdout, r.stderr


def parse_measures(stdout):
    """Parse ngspice -b op/print output ('name = value' lines)."""
    out = {}
    for m in re.finditer(r"^(\w+)\s*=\s*(failed|[\-\d.eE+]+)\s*$", stdout, re.M):
        key, val = m.group(1).lower(), m.group(2)
        out[key] = None if val == "failed" else float(val)
    return out


def run_ngspice_tran(cir_body, vectors, name, *, tstep, tstop, extra_control="", uic=True):
    """Run a .tran analysis and pull back the FULL time series via `wrdata` (plain ASCII
    columns), parsed with numpy on the host. This sidesteps ngspice's `.measure`
    interactive-vs-batch quirks entirely (a real friction point hit during development --
    the interactive `meas` command name differs from the `.measure` netlist statement and
    is easy to get wrong inside a `.control` block) in favor of doing every peak/duration/
    charge-integral computation in plain, independently-checkable Python. `cir_body` is
    everything except the .tran/.control/wrdata/.end boilerplate (device lines + models +
    sources only). `vectors` is a list of ngspice vector expressions (e.g. 'i(vsense)',
    'v(out)'). Returns (data, stdout, stderr) where data is a dict {'time': arr, vec: arr,
    ...} (vector names lowercased, as ngspice reports them)."""
    datafile = f"{name}.data"
    data_container_path = "/workspace/" + os.path.relpath(
        os.path.join(SCRATCH, datafile), REPO_ROOT).replace(os.sep, "/")
    vec_list = " ".join(vectors)
    uic_flag = " UIC" if uic else ""
    cir = (
        cir_body
        + f".tran {tstep} {tstop}{uic_flag}\n"
        + ".control\nrun\n"
        + f"wrdata {data_container_path} {vec_list}\n"
        + extra_control
        + "\n.endc\n.end\n"
    )
    meas, out, err = run_ngspice(cir, name)
    data_path = os.path.join(SCRATCH, datafile)
    if not os.path.exists(data_path):
        return None, out, err
    raw = np.loadtxt(data_path)
    # wrdata emits: time v0 v0-dup time v1 v1-dup time v2 ... (each vector re-prints time
    # as a real-valued column pair for complex-vector compatibility) -- take col0 as time,
    # then every 2nd column starting at 1 as the successive vectors' values.
    if raw.ndim == 1:
        raw = raw.reshape(1, -1)
    result = {"time": raw[:, 0]}
    for i, v in enumerate(vectors):
        col = 1 + 2 * i
        result[v.lower()] = raw[:, col]
    return result, out, err


# --------------------------------------------------------------------------- analysis
def peak_abs(data, vec):
    a = np.abs(data[vec])
    i = int(np.argmax(a))
    return a[i], data["time"][i]


def charge_coulombs(data, vec, t_end=None):
    """Trapezoidal ∫|I| dt from 0 to t_end (default: full trace)."""
    t, i = data["time"], np.abs(data[vec])
    if t_end is not None:
        mask = t <= t_end
        t, i = t[mask], i[mask]
    return float(np.trapz(i, t))


def duration_above(data, vec, thresh):
    """Longest contiguous span where |vec| > thresh. Returns (max_duration_s,
    first_crossing_time_or_None)."""
    t, i = data["time"], np.abs(data[vec])
    above = i > thresh
    if not above.any():
        return 0.0, None
    first_t = t[np.argmax(above)]
    # find contiguous run lengths
    idx = np.where(above)[0]
    splits = np.where(np.diff(idx) > 1)[0]
    runs = np.split(idx, splits + 1)
    best = 0.0
    for run in runs:
        span = t[run[-1]] - t[run[0]]
        best = max(best, span)
    return float(best), float(first_t)


# --------------------------------------------------------------------------- SS34
# Fit: N=1.10 (Schottky-typical ideality), RS=25mOhm (typical bulk+contact R for a
# 3A/DO-214AC-SMA die of this class), IS solved so the model reproduces the ONE precise
# datasheet anchor (IF=3.0A -> VF=0.55V max, 25C, MDD SS32-SS3200 Rev2024A5 / LCSC C8678).
# Verified below (SS34_SELFTEST) before use. BV/IBV taken directly from the datasheet
# (VRRM=40V, IR_max=0.5mA at that rated voltage, 25C) for a correct high-voltage reverse
# region; at the low reverse voltages seen in every case here (<=12V) the diode equation's
# own IS sets the leakage, which the report cross-checks against the datasheet's 0.5mA
# rated-voltage MAX as a conservative ceiling (Schottky reverse leakage is not perfectly
# ideal-exponential; the datasheet MAX at full VRRM is the safer number to cite).
SS34_IS = 1.68e-7   # A, solved (see report Methodology / this file's docstring)
SS34_N = 1.10
SS34_RS = 0.025      # ohm
SS34_BV = 40.0        # V, VRRM
SS34_IBV = 0.5e-3     # A, IR_max @ VRRM, 25C

SS34_MODEL = (
    f".model SS34 D(IS={SS34_IS} N={SS34_N} RS={SS34_RS} BV={SS34_BV} IBV={SS34_IBV} "
    f"CJO=250p TT=10n)\n"
)


def ss34_selftest():
    """Confirms the fitted .model reproduces the datasheet anchor (3A -> 0.55V) before
    it is trusted in any case deck. Returns (vf_at_3a, ir_leak_est)."""
    cir = (
        "* SS34 self-test: forward anchor + low-voltage reverse leakage\n"
        + SS34_MODEL
        + "I1 0 a DC 3.0\n"
        "D1 a 0 SS34\n"
        "Vr rc 0 DC 0.5\n"
        "Dr 0 rc SS34\n"
        ".control\nop\nprint v(a)\nprint i(Vr)\n.endc\n.end\n"
    )
    meas, out, err = run_ngspice(cir, "ss34_selftest")
    vf = None
    ir = None
    for m in re.finditer(r"^v\(a\)\s*=\s*([\-\d.eE+]+)", out, re.M):
        vf = float(m.group(1))
    for m in re.finditer(r"^i\(vr\)\s*=\s*([\-\d.eE+]+)", out, re.M):
        ir = float(m.group(1))
    return vf, ir, out, err


# --------------------------------------------------------------------------- polyfuse
# Leaky-integrator (single-pole thermal-analog) I^2t model, per CLAUDE-task wording
# ("polyfuse as resistance-with-i2t-trip from the Littelfuse 1206L075 datasheet curve").
# dE/dt = I(t)^2 - E/tau ; trips when E crosses E_thresh.
# Calibration (two design constraints):
#   (1) E_thresh = I_test^2 * t_test, from the datasheet's single 'Maximum Time To Trip'
#       point (a WORST-CASE max-time guarantee, so this model's trip times are a
#       conservative upper bound -- a real device trips at least this fast, likely faster).
#   (2) tau = E_thresh / Ihold^2, so the model's DC steady-state energy at I=Ihold sits
#       exactly at the trip boundary (matches the datasheet's own definition of Ihold: the
#       current the device holds indefinitely without tripping). Anything sustained below
#       Ihold settles to a steady-state energy strictly below threshold and never trips,
#       no matter how long it runs -- fixes the false-eventual-trip problem a bare (non-
#       leaky) I^2t accumulator would have at any sustained current, however small.
POLYFUSE_PARAMS = {
    # name: (Ihold_A, Itest_A, Ttest_s, Rcold_ohm, note)
    "F1_1206L075_16": (0.75, 8.00, 0.20, 0.150,
                        "Littelfuse 1206L075/16 row: Ihold .75A/Itrip 1.5A/Vmax 16V, "
                        "MaxTimeToTrip 8.00A->0.20s, Rmin .090/R1max .290 Ohm (LCSC "
                        "C371166 mirror, Rev 02/25/19); Rcold=.150 Ohm engineering "
                        "estimate between Rmin/R1max (no separate Rtyp tabulated)."),
    "F5_1206L110TH": (1.10, 8.00, 0.10, 0.070,
                       "Littelfuse 1206L110TH row (nearest-Ihold family member, stand-in "
                       "for the populated FUZETEC FSMD110-16-1206R which has no vendored "
                       "curve; same Ihold/Itrip class per usb-ingress-bom-delta doc): "
                       "Ihold 1.10A/Itrip 2.2A, MaxTimeToTrip 8.00A->0.10s, Rmin .040/"
                       "R1max .210 Ohm; Rcold=.070 Ohm engineering estimate."),
}


def polyfuse_calib(key):
    ihold, itest, ttest, rcold, note = POLYFUSE_PARAMS[key]
    e_thresh = itest * itest * ttest
    tau = e_thresh / (ihold * ihold)
    return {"ihold": ihold, "e_thresh": e_thresh, "tau": tau, "rcold": rcold, "note": note}


def polyfuse_subckt(key, pin_a, pin_b, sense_name, energy_node):
    """Emits SPICE lines for a polyfuse between pin_a/pin_b: a fixed Rcold in series
    (pre-trip resistance is not dynamically switched -- every case here only needs to
    know WHETHER/WHEN the I^2t energy state crosses E_thresh, not the post-trip high-Z
    recovery transient), a zero-volt sense source so the current is readable as
    I(V<sense_name>), and the leaky-integrator energy state on node <energy_node> (a 1F
    cap to ground pumped by I^2 through a G-source, bled by a 1/tau conductance)."""
    c = polyfuse_calib(key)
    mid = f"{pin_a}_{sense_name}_mid"
    return (
        f"* polyfuse {key}: Ihold={c['ihold']}A Rcold={c['rcold']}ohm "
        f"Ethresh={c['e_thresh']:.4g} tau={c['tau']:.4g}s\n"
        f"V{sense_name} {pin_a} {mid} DC 0\n"
        f"R{sense_name}_cold {mid} {pin_b} {c['rcold']}\n"
        f"C{sense_name}_e {energy_node} 0 1 IC=0\n"
        f"G{sense_name}_pump 0 {energy_node} value={{I(V{sense_name})*I(V{sense_name})}}\n"
        f"R{sense_name}_leak {energy_node} 0 {c['tau']}\n"
    )


# --------------------------------------------------------------------------- TPS2121
# Behavioral priority-mux model. RON from datasheet Sec 7.5 (TPS2121, 25C typ). ILIM law
# is NOT actively enforced as a folded-back current source in these decks (see report
# Methodology: every scenario here draws currents 1-2 orders below ILIM by design/by the
# isolation architecture itself -- the owner's own "no single reliance on ILIM" ruling --
# so ILIM is checked post-hoc against the peak current, never the controlling mechanism).
# PR1 valid threshold (~4.27V) and OV1 trip threshold (~6.04V) per
# docs/usb-ingress-bom-delta-2026-07-24.md Section 2's strap-value derivations (100k/33k
# and 47k/10k dividers against the datasheet VREF=1.06V typ, Sec 7.5).
TPS2121_RON = 0.060          # ohm, 56m typ / 70m max @25C, IOUT=200mA, Sec 7.5 -- use typ
TPS2121_PR1_VALID_V = 4.27   # V, usb-ingress-bom-delta.md strap math
TPS2121_OV1_TRIP_V = 6.04    # V, ditto
TPS2121_ILK_TYP_A = 1e-6     # A, ILK,INx typ @25C, |dV|<=22V, Sec 7.5 electrical table
TPS2121_ILK_MAX_A = 500e-6   # A, ILK,INx MAX over -40..125C, Sec 7.5 (conservative bound)
TPS2121_ILIM_100K_TYP_A = 65.2 / (100 ** 0.861)   # ~1.24A, Sec 9.3.2 Eq 2, R_ILIM=100k


def mux_priority_subckt(in1, in2, out, *, ov1_trip=True, ov1_tau_s=2e-6,
                          leak=TPS2121_ILK_TYP_A, out_load_ohm=1e7, sel_ic1=1.0):
    """TWO-input priority mux (IN1=priority/PSU-side, IN2=backup/VBUS-side), matching
    the module-ingress wiring in usb-ingress-bom-delta.md Section 3 (IN1 priority=the
    module's 5VSB source, IN2 backup=VBUS). ONE switch per channel (no cascaded series
    switches -- an earlier two-switch-per-channel design, OV1 gating IN1 ahead of a
    separate PR1 select switch, was numerically fragile/non-convergent and is also not
    how the datasheet describes the behavior: Sec 9.3.5 says an OV-tripped channel gets
    'fast switchover to the other input ... if it is a valid voltage', i.e. OV status
    feeds the SAME selection decision, not a separate series block in front of it).
    IN1 is selected iff V(IN1) is between the ~4.27V PR1-valid floor and (if ov1_trip)
    the ~6.04V OV1 ceiling; IN2 is selected otherwise. The valid/invalid decision is
    RC-filtered (time constant ov1_tau_s) before being thresholded, standing in for the
    datasheet's undocumented-but-implied comparator response time (Sec 9.3.5 states only
    'turns off immediately' with no number given for OV1 specifically, unlike RCB's
    stated 10us -- this file's docstring and the report flag the assumption; ov1_tau_s
    defaults to 2us, the same order as RCB's documented 10us response class).
    sel_ic1 is the initial condition of the (post-filter) select signal: 1.0 = IN1 valid
    at t=0 (the common case -- a healthy PSU/5VSB source already present when the
    simulation starts), 0.0 = IN2 valid at t=0 (use this for a scenario that begins with
    IN1 already dead/absent, so the filter's own turn-on transient does not leak into the
    result). The non-selected channel's switch is OFF (roff=10Meg) with an explicit
    leakage CURRENT SOURCE of magnitude `leak` delivering current INTO the de-selected
    IN node (conservative direction -- current available to backfeed/charge a dead input
    net), per the datasheet's own ILK,INx spec (Sec 7.5): pass TPS2121_ILK_MAX_A for a
    worst-case bound or TPS2121_ILK_TYP_A for a realistic 25C figure. out_load_ohm is a
    weak bleed to ground on OUT so the node is never left undriven before a switch
    closes."""
    lines = []
    lines.append(f"* TPS2121 priority mux: IN1={in1}(priority) IN2={in2}(backup) OUT={out}\n")
    lines.append(f"Rbleed_{out} {out} 0 {out_load_ohm}\n")
    ov_hi = f" * (V({in1}) < {TPS2121_OV1_TRIP_V})" if ov1_trip else ""
    lines.append(f"Bvalidraw_{out} n_{out}_validraw 0 "
                  f"V = (V({in1}) > {TPS2121_PR1_VALID_V}){ov_hi}\n")
    rdelay = 1e3
    cdelay = ov1_tau_s / rdelay
    lines.append(f"Rdelay_{out} n_{out}_validraw n_{out}_valid {rdelay}\n")
    lines.append(f"Cdelay_{out} n_{out}_valid 0 {cdelay} IC={sel_ic1}\n")
    # sel1 = valid - 0.5 (>0 when IN1 selected); sel2 = 0.5 - valid (>0 when IN2 selected)
    lines.append(f"Bsel1_{out} n_{out}_sel1 0 V = V(n_{out}_valid) - 0.5\n")
    lines.append(f"Bsel2_{out} n_{out}_sel2 0 V = 0.5 - V(n_{out}_valid)\n")
    lines.append(f".model SWSEL_{out} SW(vt=0 vh=0.02 ron={TPS2121_RON} roff=10Meg)\n")
    lines.append(f"S1_{out} {in1} {out} n_{out}_sel1 0 SWSEL_{out}\n")
    lines.append(f"S2_{out} {in2} {out} n_{out}_sel2 0 SWSEL_{out}\n")
    # Leakage on the de-selected side: conservative OUT->IN1 and OUT->IN2 current sources
    # of magnitude `leak`, delivering current INTO the IN node (G N+=INx so the source
    # injects into INx, drawing from OUT -- the conservative "could this backfeed/charge
    # a dead input net" direction), always present (negligible once a channel's own RON is
    # active in parallel, dominant when that channel is open) -- models ILK,INx (Sec 7.5).
    lines.append(f"Gleak1_{out} {in1} {out} value={{ {leak} }}\n")
    lines.append(f"Gleak2_{out} {in2} {out} value={{ {leak} }}\n")
    return "".join(lines)
