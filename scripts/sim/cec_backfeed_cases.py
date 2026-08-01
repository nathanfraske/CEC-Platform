#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""cec_backfeed_cases -- the six verification cases (A-F) for the 2026-07-24 USB-backfeed
protection package. Run directly: `python3 scripts/sim/cec_backfeed_cases.py [case letter
...]` (default: all). Prints a results table per case; full detail is assembled into
docs/spice-backfeed-verify-2026-07-24.md separately (this script is the evidence source,
not the report -- every number quoted in the doc traces back to a function here).

Engine: ngspice 44.2 (KLU) inside docker-routing-1, driven via cec_backfeed_models.
"""
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from cec_backfeed_models import (
    TITLE, SS34_MODEL, run_ngspice, run_ngspice_tran, peak_abs, charge_coulombs,
    duration_above, polyfuse_subckt, polyfuse_calib, mux_priority_subckt,
    TPS2121_ILK_TYP_A, TPS2121_ILK_MAX_A, TPS2121_ILIM_100K_TYP_A, TPS2121_RON,
    TPS2121_PR1_VALID_V, TPS2121_OV1_TRIP_V,
)

EFUSE_HARD_TRIP_A = 2.5     # host eFuse fast-trip current, per task spec
EFUSE_HARD_TRIP_S = 1e-3    # ... sustained this long
EFUSE_BUDGET_C = 50e-6      # host inrush charge budget, per task spec (~10uF*5V heuristic)
RSRC_USB = 0.12              # ohm, USB 5V incl. cable, per task spec (case A/B)

# CORRECTED 2026-07-24 (datasheet-provenance audit): was 6.5V, an assumed figure that
# crossed agent boundaries without being checked against the vendored datasheet. The real
# LP5907 abs-max V(IN) is 6.0V (lib/datasheets/LP5907.pdf Sec 5.1: VIN -0.3 to 6V; no
# transient/time-dimension allowance -- abs-max is abs-max). Already corrected in
# docs/usb-ingress-bom-delta-2026-07-24.md's CORRECTION section; this was the one call
# site that still used the wrong 6.5V figure operationally (not just in prose). See
# docs/datasheet-provenance-audit-2026-07-24.md.
LP5907_ABSMAX_V = 6.0


# =========================================================================== CASE A
def case_a(caps_uF=(100, 470, 1000, 3300), rfault=2.0, tstop=0.06):
    """Baseline UNMITIGATED module: USB 5V (Rsrc~0.12 incl cable) -> SS34 -> module rail
    -> 25mOhm shunt -> faulty-PSU 5VSB bulk, swept over cap value x {caps-only, 2ohm
    parallel fault}."""
    results = []
    for c_uF in caps_uF:
        for fault in (False, True):
            name = f"caseA_{c_uF}uF_{'fault' if fault else 'nofault'}"
            body = (
                TITLE + SS34_MODEL
                + f"Vusb usbraw 0 PWL(0 0 100n 5 {tstop} 5)\n"
                + f"Rsrc usbraw a1 {RSRC_USB}\n"
                + "Vamm a1 a DC 0\n"      # 0V ammeter: plain R has no i() in this build
                + "D2 a rail SS34\n"
                + "Rshunt rail psu 0.025\n"
                + f"Cbulk psu 0 {c_uF}u IC=0\n"
            )
            if fault:
                body += "Rfault psu 0 2.0\n"
            data, out, err = run_ngspice_tran(
                body, ["i(vamm)", "v(psu)"], name, tstep="2u", tstop=str(tstop))
            if data is None:
                results.append({"cap_uF": c_uF, "fault": fault, "error": err[:500]})
                continue
            ipk, tpk = peak_abs(data, "i(vamm)")
            dur, t_first = duration_above(data, "i(vamm)", EFUSE_HARD_TRIP_A)
            hard_trip = dur >= EFUSE_HARD_TRIP_S
            # charge up to hard-trip point if it trips, else over the full window
            t_end = (t_first + EFUSE_HARD_TRIP_S) if hard_trip else None
            q = charge_coulombs(data, "i(vamm)", t_end=t_end)
            q_full = charge_coulombs(data, "i(vamm)")
            v_final = data["v(psu)"][-1]
            results.append({
                "cap_uF": c_uF, "fault": fault, "ipk_A": round(ipk, 2),
                "tpk_s": tpk, "hard_trip_2p5A_1ms": hard_trip,
                "t_first_cross_2p5A_s": t_first,
                "q_to_trip_or_window_C": q, "q_full_window_C": round(q_full, 6),
                "v_psu_final": round(v_final, 3),
                "over_50uC_budget": q_full > EFUSE_BUDGET_C,
            })
    return results


# =========================================================================== CASE B
def case_b_inrush(c_local_uF=30, tramp_ms=10.0, tstop_ms=None):
    """MITIGATED module, item 1: port-side inrush charging the module's own local bulk
    (~30uF, post-mux) through the TPS2121's C_SS-controlled soft-start ramp. Modeled as a
    slew-rate-limited ideal source (Sec 9.3.1 of TPS2121RUXR.pdf: during soft start the
    device regulates OUTPUT VOLTAGE SLEW, current is whatever the load needs to track it)
    driving the local cap through the channel RON -- valid as long as that current never
    approaches ILIM (verified post-hoc below), which the task's own local-cap budget
    guarantees. tramp_ms is swept by the caller: 10ms (repo's own 'hub-proven' figure) vs
    ~125ms (this project's own datasheet Table 9-1 slew-rate-vs-CSS interpolation at
    C_SS=2.2uF, VIN~5V -- see report Methodology for the derivation and the discrepancy
    note)."""
    tstop_ms = tstop_ms if tstop_ms is not None else tramp_ms * 1.5
    name = f"caseB_inrush_tramp{tramp_ms}ms"
    body = (
        TITLE
        + f"Vout_ramp nramp 0 PWL(0 0 {tramp_ms}m 5 {tstop_ms}m 5)\n"
        + f"Rseries nramp o1 {TPS2121_RON}\n"
        + "Vamm o1 out DC 0\n"    # 0V ammeter: plain R has no i() in this build
        + f"Clocal out 0 {c_local_uF}u IC=0\n"
    )
    data, out, err = run_ngspice_tran(
        body, ["i(vamm)", "v(out)"], name, tstep=f"{tramp_ms/2000}m", tstop=f"{tstop_ms}m")
    if data is None:
        return {"error": err[:800]}
    ipk, tpk = peak_abs(data, "i(vamm)")
    q = charge_coulombs(data, "i(vamm)")
    return {
        "tramp_ms": tramp_ms, "c_local_uF": c_local_uF, "ipk_A": ipk, "tpk_s": tpk,
        "q_C": q, "ilim_100k_A": TPS2121_ILIM_100K_TYP_A,
        "ilim_margin_x": TPS2121_ILIM_100K_TYP_A / ipk if ipk else None,
        "efuse_hard_trip": ipk > EFUSE_HARD_TRIP_A,
        "over_50uC_budget": q > EFUSE_BUDGET_C,
    }


def case_b_leakage(dwell_s=(0.001, 0.01, 0.1, 1.0, 10.0), leak=TPS2121_ILK_MAX_A):
    """MITIGATED module, item 1b: the ORIGINAL backfeed threat under the mitigated
    design. IN1 (dead/faulty PSU bulk) is DISCONNECTED (S1 open, PR1 invalid) while IN2
    (VBUS) drives OUT; the only residual path is the datasheet's own ILK,INx leakage
    spec. Report charge accumulated on a representative dead-PSU bulk cap (470uF) at
    several dwell times, at the conservative full-temp-range MAX leakage figure."""
    rows = []
    for t_s in dwell_s:
        q_worst = leak * t_s   # constant-current approx (valid: t_s << C*V/leak in every
        # row here, i.e. the dead cap never gets anywhere near fully charged at uA-class
        # current over these dwell times, so it truly is ~constant-current, not RC-decaying)
        q_typ = TPS2121_ILK_TYP_A * t_s
        rows.append({"dwell_s": t_s, "q_worst_C": q_worst, "q_typ_C": q_typ,
                      "over_50uC_budget_worst": q_worst > EFUSE_BUDGET_C})
    return {"leak_worst_A": leak, "leak_typ_A": TPS2121_ILK_TYP_A, "rows": rows}


def case_b_nuisance_trip(burst_A=0.5, idle_A=0.12, burst_ms=50, period_ms=500,
                          n_cycles=8):
    """MITIGATED module, item 2: does F1 (750mA-hold polyfuse, ahead of the mux) nuisance
    -trip on normal module operation? Representative ESP flash-burst profile: idle_A
    baseline with periodic burst_A peaks (duty ~= burst_ms/period_ms), run for n_cycles
    and check the polyfuse's I^2t energy state stays below its trip threshold
    throughout."""
    calib = polyfuse_calib("F1_1206L075_16")
    period_s = period_ms / 1000.0
    tstop = n_cycles * period_s
    # PULSE(V1 V2 TD TR TF PW PER): idle_A baseline, burst_A pulses of width burst_ms
    body = (
        TITLE
        + polyfuse_subckt("F1_1206L075_16", "a", "b", "f1", "e_f1")
        + f"Iload 0 a PULSE({idle_A} {burst_A} 0 10u 10u {burst_ms}m {period_ms}m)\n"
        + "Rb b 0 1meg\n"
    )
    data, out, err = run_ngspice_tran(
        body, ["v(e_f1)", "i(vf1)"], "caseB_nuisance", tstep=f"{period_ms/400}m",
        tstop=str(tstop))
    if data is None:
        return {"error": err[:800]}
    e_max = float(data["v(e_f1)"].max())
    i_pk = float(np.abs(data["i(vf1)"]).max())
    return {
        "burst_A": burst_A, "idle_A": idle_A, "duty_pct": 100 * burst_ms / period_ms,
        "n_cycles": n_cycles, "e_max": e_max, "e_thresh": calib["e_thresh"],
        "margin_pct": 100 * (1 - e_max / calib["e_thresh"]), "i_pk_seen": i_pk,
        "nuisance_trip": e_max >= calib["e_thresh"],
    }


# =========================================================================== CASE C
def case_c_old_d2(v_psu=5.5, v_vbus=5.0):
    """REVERSE (PSU->USB) across the OLD D2 (SS34, still-shipping pre-mitigation
    topology): PSU rail elevated to v_psu, VBUS at nominal v_vbus. D2 is oriented
    anode=VBUS-side, cathode=rail-side (spec text: 'the diode blocks only the reverse
    direction (PSU->USB)'), so v_psu > v_vbus reverse-biases it -- quantify the leakage."""
    body = (
        TITLE + SS34_MODEL
        + f"Vpsu psu 0 DC {v_psu}\n"
        + f"Vvbus vbus 0 DC {v_vbus}\n"
        + "D2 vbus psu SS34\n"   # anode=vbus, cathode=psu (rail side)
    )
    cir = (body + ".control\nop\nprint i(Vvbus)\n.endc\n.end\n")
    meas, out, err = run_ngspice(cir, "caseC_old_d2")
    ivbus = None
    for m in re.finditer(r"^i\(vvbus\)\s*=\s*([\-\d.eE+]+)", out, re.M):
        ivbus = float(m.group(1))
    return {"v_psu": v_psu, "v_vbus": v_vbus, "reverse_bias_V": v_psu - v_vbus,
            "i_leak_spice_A": ivbus, "i_leak_datasheet_max_A_at_40V": 0.5e-3,
            "note": "SPICE value is this file's fitted model at the ACTUAL (small) "
                    "reverse bias; the datasheet MAX is IR@VRRM=40V,25C, used as a "
                    "deliberately conservative ceiling since Schottky reverse leakage "
                    "is not perfectly ideal-exponential at low reverse bias."}


def case_c_mux(v_psu=5.5, v_vbus=5.0):
    """REVERSE (PSU->USB) across the MITIGATED mux, powered case: does the elevated PSU
    rail backfeed onto VBUS/IN2? v_psu=5.5V sits BELOW the ~6.04V OV1 threshold, so IN1
    stays selected normally -- IN2/VBUS sees only the same ILK,INx leakage class as case
    B (not a new mechanism), verified here directly in the full mux model."""
    body = (
        TITLE
        + f"Vin1 in1 0 DC {v_psu}\n"
        + f"Vin2 in2 0 DC {v_vbus}\n"
        + mux_priority_subckt("in1", "in2", "out", leak=TPS2121_ILK_MAX_A)
        + "Cout out 0 1u IC=0\n"
    )
    data, out, err = run_ngspice_tran(
        body, ["v(out)", "i(vin2)"], "caseC_mux", tstep="1u", tstop="200u")
    if data is None:
        return {"error": err[:800]}
    i_final = float(data["i(vin2)"][-1])
    return {"v_psu": v_psu, "v_vbus": v_vbus, "v_out_final": float(data["v(out)"][-1]),
            "i_into_vbus_A": -i_final, "ov1_tripped": v_psu > TPS2121_OV1_TRIP_V,
            "leak_used_A": TPS2121_ILK_MAX_A}


# =========================================================================== CASE D
def case_d_i(rsrc=0.15, c_hub_uF=4700.0, tstop=0.03):
    """KVM path (i): PC-USB-powered NanoKVM into the hub 4700uF + 5VSB tree, UNMITIGATED
    (today's raw rail tap, 'nothing in series' per owner-queue). Same physics as case A
    but with NO diode at all -- a direct tap -- and the hub's fixed 4700uF hold-up."""
    body = (
        TITLE
        + f"Vusb usbraw 0 PWL(0 0 100n 5 {tstop} 5)\n"
        + f"Rsrc usbraw a1 {rsrc}\n"
        + "Vamm a1 a DC 0\n"    # 0V ammeter: plain R has no i() in this build
        + f"Chub a 0 {c_hub_uF}u IC=0\n"
    )
    data, out, err = run_ngspice_tran(
        body, ["i(vamm)"], "caseD_i_raw", tstep="1u", tstop=str(tstop))
    if data is None:
        return {"error": err[:800]}
    ipk, tpk = peak_abs(data, "i(vamm)")
    dur, t_first = duration_above(data, "i(vamm)", EFUSE_HARD_TRIP_A)
    hard_trip = dur >= EFUSE_HARD_TRIP_S
    t_end = (t_first + EFUSE_HARD_TRIP_S) if hard_trip else None
    q = charge_coulombs(data, "i(vamm)", t_end=t_end)
    return {"rsrc": rsrc, "c_hub_uF": c_hub_uF, "ipk_A": ipk, "tpk_s": tpk,
            "hard_trip": hard_trip, "t_first_cross_A": t_first, "q_to_trip_C": q}


def case_d_ii_inrush(c_local_uF=30.0, tramp_ms=10.0, tstop_ms=None):
    """KVM path (ii): with the third cascade stage (U11) + 1.1A polyfuse (F5) -- port-
    side inrush, same soft-start-ramp construction as case_b_inrush (same TPS2121
    part/C_SS)."""
    return case_b_inrush(c_local_uF=c_local_uF, tramp_ms=tramp_ms, tstop_ms=tstop_ms)


def case_d_ii_nuisance(kvm_A=0.6, idle_A=0.15, burst_ms=200, period_ms=1000, n_cycles=6):
    """KVM path (ii): does F5 (1.1A-hold) nuisance-trip on normal NanoKVM draw? Repo-cited
    figure: ~0.5-1A for the original/base NanoKVM the J_KVM header was designed against
    (docs/24pin-rev3-respin-2026-06-24.md); use 0.6A representative continuous-class draw
    as the burst level (NanoKVM is not truly 'bursty' like an MCU flash write -- it is a
    small always-on Linux/RTOS SBC -- so this is a near-worst-case duty assumption, not a
    generous one)."""
    calib = polyfuse_calib("F5_FSMD110_16_1206R")
    period_s = period_ms / 1000.0
    tstop = n_cycles * period_s
    body = (
        TITLE
        + polyfuse_subckt("F5_FSMD110_16_1206R", "a", "b", "f5", "e_f5")
        + f"Iload 0 a PULSE({idle_A} {kvm_A} 0 10u 10u {burst_ms}m {period_ms}m)\n"
        + "Rb b 0 1meg\n"
    )
    data, out, err = run_ngspice_tran(
        body, ["v(e_f5)"], "caseD_ii_nuisance", tstep=f"{period_ms/400}m", tstop=str(tstop))
    if data is None:
        return {"error": err[:800]}
    e_max = float(data["v(e_f5)"].max())
    return {"kvm_A": kvm_A, "idle_A": idle_A, "duty_pct": 100 * burst_ms / period_ms,
            "e_max": e_max, "e_thresh": calib["e_thresh"],
            "margin_pct": 100 * (1 - e_max / calib["e_thresh"]),
            "nuisance_trip": e_max >= calib["e_thresh"]}


def case_d_iii(rsrc=0.15, c_host_uF=20.0, tstop=0.01):
    """KVM path (iii): a powered Hub back-drives a PC port through the KVM.
    BEFORE (raw tap): Hub's healthy +5VSB (regulated, ~0 source Z) hits the NanoKVM's
    header-5V==VBUS net directly ('nothing in series'); model the host port's own small
    local decoupling (c_host_uF) as the thing that sees an inrush transient at the
    moment of connection.
    AFTER (3rd stage + polyfuse): the header pin is INBOUND-ONLY by construction (the
    mux's OUT never routes back to IN2/KVM) -- verified via the same mux leakage
    methodology as case B/C, not a new mechanism."""
    body_before = (
        TITLE
        + "Vhub hubrail 0 DC 5.05\n"    # Hub's own regulated 5VSB, slightly above nominal
        + f"Rsrc hubrail a1 {rsrc}\n"
        + "Vamm a1 a DC 0\n"    # 0V ammeter: plain R has no i() in this build
        + f"Chost a 0 {c_host_uF}u IC=0\n"
    )
    data, out, err = run_ngspice_tran(
        body_before, ["i(vamm)"], "caseD_iii_before", tstep="0.2u", tstop=str(tstop))
    before = {"error": err[:800]} if data is None else {
        "ipk_A": peak_abs(data, "i(vamm)")[0],
        "hard_trip": duration_above(data, "i(vamm)", EFUSE_HARD_TRIP_A)[0] >= EFUSE_HARD_TRIP_S,
        "q_C": charge_coulombs(data, "i(vamm)"),
    }
    after = {
        "mechanism": "architectural elimination: KVM_5V_IN is only ever U11.IN2; U11.OUT "
                     "feeds U7.IN2 (toward MAIN_5V stage), never back to KVM_5V_IN -- no "
                     "conductive path exists for the Hub to drive the KVM pin regardless "
                     "of mux state. Residual exposure is the same ILK,INx leakage class "
                     "as case B (max 500uA, typ 1uA) -- see case_b_leakage rows.",
        "leak_worst_A": TPS2121_ILK_MAX_A, "leak_typ_A": TPS2121_ILK_TYP_A,
    }
    return {"before": before, "after": after}


# =========================================================================== CASE E
def case_e_bound(vf_body_diode=0.6, f1_key="F1_1206L075_16"):
    """UNPOWERED-reverse bench gap: OUT driven at 5V, both mux inputs dead. Datasheet
    (TPS2121RUXR.pdf) coverage check + a worst-case PAPER BOUND. Sec 7.5's RCB spec
    (IRCB 0.2/1/2A, tRCB 10us) and Sec 10.6's reverse-polarity-protection section both
    implicitly assume an operating (biased) device -- neither states a both-inputs-dead
    condition. Physical reasoning bound: the device's 'back-to-back-FET' input isolation
    (spec text) needs an ACTIVE comparator (RCB) to block reverse conduction at all --
    Sec 9.3.6 describes RCB as something that must SENSE and then ACT ('the channel will
    switch off to stop the reverse current'), which only makes sense if the passive
    fallback (no bias available to run that comparator) would otherwise conduct. Bounding
    assumption: worst case, an unbiased channel's series FET pair degrades to a single
    forward-biased body diode from OUT back into the dead input net (typical power-FET
    body-diode Vf ~0.5-0.7V, no active current limiting) -- but F1 (or F5) is STILL
    physically in series on that path (a polyfuse's operation does not depend on the
    mux's own bias), so it still bounds the worst case. Compute the resulting current family
    and where F1 would land against its own I^2t curve."""
    calib = polyfuse_calib(f1_key)
    # crude bound: OUT(5V) - Vf(bodydiode) across F1's cold R + assumed small board/trace R
    r_trace = 0.05
    v_avail = 5.0 - vf_body_diode
    r_total = calib["rcold"] + r_trace
    i_bound = v_avail / r_total
    # is this current itself steady-state safe under F1's Ihold, or would it eventually trip?
    e_ss = i_bound ** 2 * calib["tau"]
    trips = e_ss > calib["e_thresh"]
    # closed-form leaky-integrator step response: E(t)=I^2*tau*(1-exp(-t/tau)); solve for
    # t at E=e_thresh (None if it never gets there, i.e. i_bound <= Ihold).
    if trips:
        ratio = 1 - calib["e_thresh"] / e_ss
        t_trip = -calib["tau"] * math.log(ratio)
    else:
        t_trip = None
    return {
        "datasheet_covers_this_state": False,
        "datasheet_citations": [
            "Sec 7.5 FAST REVERSE CURRENT BLOCKING (RCB): IRCB 0.2/1/2A min/typ/max, "
            "tRCB 10us -- condition 'VOUT > VINx', device power state unstated.",
            "Sec 9.3.6: 'Each channel has the always on reverse current blocking. If "
            "the output is forced above the selected input by VIRCB, the channel will "
            "switch off to stop the reverse current' -- an ACTIVE sense-then-act "
            "description, implying a passive/unbiased fallback would NOT already block.",
            "Sec 10.6 Reverse Polarity Protection: describes an external GND-diode "
            "mitigation for a mis-wired LIVE supply -- does not address a fully "
            "unbiased device.",
        ],
        "worst_case_bound": {
            "assumed_body_diode_vf_V": vf_body_diode, "r_trace_ohm": r_trace,
            "f1_rcold_ohm": calib["rcold"], "i_bound_A": i_bound,
            "f1_e_thresh": calib["e_thresh"], "f1_e_ss_at_i_bound": e_ss,
            "f1_would_eventually_trip": trips, "f1_trip_time_s": t_trip,
        },
        "best_case": "internal gate pull-downs hold both series FETs fully off even "
                      "unbiased (a common load-switch design pattern) -- residual current "
                      "bounded only by ESD-network leakage (nA-class); UNVERIFIED, no "
                      "datasheet support either way.",
        "verdict": "remains a first-article bench gate per the existing owner ruling -- "
                    "not resolvable on paper. F1/F5 provide a real, TPS2121-datasheet-"
                    "INDEPENDENT backstop even under the worst-case bound.",
    }


# =========================================================================== CASE F
def case_f(v_fault=12.0, t_edge_ns=(1000, 100, 10)):
    """OVP: a cross-railed 12V-on-5VSB event at the mux input. Sweep the fault EDGE RATE
    (a mis-wire/connector-mate event's real rise time is not specified anywhere -- sweep
    it to show how the exposure window depends on this unstated variable) and report the
    peak voltage reaching OUT (-> the LP5907's input) and the duration above its
    LP5907_ABSMAX_V (6.0V, CORRECTED 2026-07-24 -- was 6.5V, see module docstring/that
    constant's comment) abs-max, against the datasheet's own undocumented OV1
    response-time assumption (modeled at ov1_tau_s=2us, the same order as RCB's stated
    10us class -- see mux_priority_subckt docstring)."""
    rows = []
    for edge_ns in t_edge_ns:
        edge_s = edge_ns * 1e-9
        t0 = 1e-6
        body = (
            TITLE
            + f"Vin1 in1 0 PWL(0 5 {t0} 5 {t0+edge_s} {v_fault} 40u {v_fault})\n"
            + "Vin2 in2 0 DC 5\n"
            + mux_priority_subckt("in1", "in2", "out", ov1_tau_s=2e-6)
            + "Cout out 0 1u IC=0\n"
        )
        step = min(edge_s / 20, 5e-9) if edge_s > 0 else 5e-9
        data, out, err = run_ngspice_tran(
            body, ["v(in1)", "v(out)"], f"caseF_edge{edge_ns}ns",
            tstep=f"{step}", tstop="40u")
        if data is None:
            rows.append({"edge_ns": edge_ns, "error": err[:500]})
            continue
        vpk = float(data["v(out)"].max())
        dur, t_first = duration_above(data, "v(out)", LP5907_ABSMAX_V)
        rows.append({
            "edge_ns": edge_ns, "v_out_peak": vpk, "duration_above_absmax_s": dur,
            "first_cross_absmax_s": t_first,
            "lp5907_absmax_V": LP5907_ABSMAX_V, "exceeds_absmax": vpk > LP5907_ABSMAX_V,
        })
    # sensitivity: the rows above show duration is nearly edge-rate-independent (all land
    # ~1.4-1.5us) -- it is dominated by the ASSUMED (datasheet-undocumented) OV1 response
    # tau, not the fault edge. Sweep tau itself at a fixed representative 100ns edge to
    # show that dependency directly.
    tau_rows = []
    for tau_s in (1e-6, 2e-6, 5e-6, 10e-6):
        edge_s = 100e-9
        t0 = 1e-6
        body = (
            TITLE
            + f"Vin1 in1 0 PWL(0 5 {t0} 5 {t0+edge_s} {v_fault} 40u {v_fault})\n"
            + "Vin2 in2 0 DC 5\n"
            + mux_priority_subckt("in1", "in2", "out", ov1_tau_s=tau_s)
            + "Cout out 0 1u IC=0\n"
        )
        data, out, err = run_ngspice_tran(
            body, ["v(out)"], f"caseF_tau{int(tau_s*1e9)}ns", tstep="5n", tstop="40u")
        if data is None:
            tau_rows.append({"tau_s": tau_s, "error": err[:400]})
            continue
        dur, t_first = duration_above(data, "v(out)", LP5907_ABSMAX_V)
        tau_rows.append({"tau_s": tau_s, "duration_above_absmax_s": dur})
    return {"v_fault": v_fault, "ov1_response_tau_s_used_in_edge_sweep": 2e-6,
            "edge_rate_sweep": rows, "ov1_tau_sensitivity_sweep": tau_rows}


# =========================================================================== driver
def case_b():
    return {
        "inrush_10ms": case_b_inrush(tramp_ms=10.0),
        "inrush_125ms": case_b_inrush(tramp_ms=125.0),
        "leakage": case_b_leakage(),
        "nuisance_trip": case_b_nuisance_trip(),
    }


def case_c():
    return {"old_d2": case_c_old_d2(), "mux": case_c_mux()}


def case_d():
    return {
        "i_unmitigated": case_d_i(),
        "ii_inrush_10ms": case_d_ii_inrush(tramp_ms=10.0),
        "ii_inrush_125ms": case_d_ii_inrush(tramp_ms=125.0),
        "ii_nuisance": case_d_ii_nuisance(),
        "iii_backdrive": case_d_iii(),
    }


CASES = {
    "A": case_a, "B": case_b, "C": case_c, "D": case_d,
    "E": case_e_bound, "F": case_f,
}


def main():
    which = sys.argv[1:] or ["A"]
    for c in which:
        fn = CASES.get(c.upper())
        if not fn:
            print(f"unknown case {c}")
            continue
        print(f"=== CASE {c.upper()} ===")
        print(json.dumps(fn(), indent=1, default=str))


if __name__ == "__main__":
    main()
