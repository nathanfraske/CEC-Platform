#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_thermal_accuracy.py -- the instrument-accuracy loop (Tier-0).
# ============================================================================
# Wave-1 T0 deliverable per
# docs/standard-tier-review/thermal-capabilities-implementation-2026-07-06.md,
# closing Appendix B section G (G1-G5, the "measurement/instrumentation
# physics -- closing the temperature<->accuracy loop" gap) from
# docs/standard-tier-review/thermal-solve-completeness-2026-07-06.md: "the
# solve computes real temperatures at real locations... nothing in the
# current list feeds those temperatures back into what the board's own
# sensors report."
#
# OWN-MODULE ISOLATION: standalone. Does NOT import cec_synth_pipeline.py or
# cec_thermal2d.py (or cec_thermal_sources.py -- deliberately independent so
# this module can be unit-tested and consumed on its own). Every function
# here CONSUMES TEMPERATURES AS PLAIN INPUTS (a dict of {ref/location: T_C}),
# so it works with any solver's output -- cec_synth_pipeline.ThermalResult,
# cec_thermal2d.ThermalResult, or a hand-built dict, are all equally valid
# callers; this module runs no solver itself.
#
# CITATION DISCIPLINE: every physical constant cites its source -- a vendored
# datasheet under lib/datasheets/ (table/line referenced) or a named
# published-literature source; anything not traceable is marked UNVERIFIED.
# ============================================================================
"""
cec_thermal_accuracy
======================

Five closed-form error contributors (Appendix B section G, items G1-G5),
each a small pure function taking a temperature (or temperature GRADIENT)
as input, plus a report generator that combines them per channel:

  (a) shunt_tcr_error_pct(...)      -- G1: shunt TCR reading error
  (b) thermal_emf_false_current(...) -- G4: Seebeck EMF at Kelvin junctions,
                                        expressed as equivalent false amps
  (c) sense_amp_drift(...)          -- G2: current-sense-amp offset+gain TC
  (d) reference_adc_drift(...)      -- G3: REF3030 TC (+ ESP32 ADC, UNVERIFIED)
  (e) accuracy_vs_load_report(...)  -- per-channel total error budget vs the
                                        platform's stated accuracy claims

INPUT CONTRACT: every function that needs "how hot is it" takes a plain
float T_C (an ABSOLUTE local temperature) or dT_C (a temperature RISE/
GRADIENT, always named distinctly) -- never a solver object. The report
generator `accuracy_vs_load_report()` additionally takes a `temps` dict
keyed by whatever location labels the caller's solver uses (e.g. a shunt
ref, a net name, a component ref); ChannelSpec.shunt_T_key / amp_T_key index
into that dict, so this module has zero coupling to any particular solver's
internal naming.
"""
import math
from dataclasses import dataclass, field


# ============================================================ (a) shunt TCR
# Bourns CSS2H-2512 series -- the platform's OQ-11 shunt candidate (spec §6.4;
# CSS2H-2512R-L500F for EPS/PCIe and CSS2H-2512R-1L00F for 12VHPWR are already
# spec-locked per CLAUDE.md 2026-07-02). TCR figures read directly from the
# vendored datasheet's "Electrical Characteristics" table, "Temperature
# Coefficient including Copper Terminals" row (lib/datasheets/Bourns_CSS2H-2512.pdf,
# the table printed near the part-numbering diagram).
SHUNT_TCR_TABLE = {
    # key -> {R_ohm, tcr_ppm_C, mpn, citation, boards}
    "css2h_2512_0m5": {
        "R_ohm": 0.5e-3, "tcr_ppm_C": 100.0, "mpn": "CSS2H-2512R-L500F",
        "citation": "Bourns CSS2H-2512 datasheet, lib/datasheets/Bourns_CSS2H-2512.pdf, "
                    "'Electrical Characteristics' table: model CSS2H-2512R-L500x, "
                    "'Temperature Coefficient including Copper Terminals' = ±100 PPM/°C.",
        "boards": "EPS 8-pin / PCIe 8-pin per-cable shunt (spec §6.4)",
    },
    "css2h_2512_1m0": {
        "R_ohm": 1.0e-3, "tcr_ppm_C": 75.0, "mpn": "CSS2H-2512R-1L00F",
        "citation": "Bourns CSS2H-2512 datasheet, lib/datasheets/Bourns_CSS2H-2512.pdf, "
                    "same table: model CSS2H-2512R-1L00x TCR = ±75 PPM/°C.",
        "boards": "12VHPWR Standard per-pin shunt (spec §6.4) -- the µV-level signal case "
                 "the task calls out explicitly.",
    },
    "css2h_2512_2m0": {
        "R_ohm": 2.0e-3, "tcr_ppm_C": 75.0, "mpn": "CSS2H-2512K-2L00x",
        "citation": "Bourns CSS2H-2512 datasheet, lib/datasheets/Bourns_CSS2H-2512.pdf, "
                    "same table: model CSS2H-2512K-2L00x (K material type, <5nH) TCR = "
                    "±75 PPM/°C.",
        "boards": "24-pin ATX 12V/5V/3V3 rail shunt (spec §6.4).",
    },
    "css2h_2512_25m0_proxy": {
        "R_ohm": 25.0e-3, "tcr_ppm_C": 75.0, "mpn": "UNVERIFIED (OQ-11 open, no CSS2H "
                                                     "part at 25 mOhm)",
        "citation": "UNVERIFIED PROXY -- the 24-pin ATX 5VSB shunt is 25 mOhm (spec §6.4), "
                    "which is OUTSIDE the vendored Bourns CSS2H-2512 table's resistance "
                    "range (0.1 mOhm to 5.0 mOhm). No locked/vendored shunt part exists for "
                    "this value (OQ-11 remains open for it). This entry borrows the closest "
                    "same-technology proxy: Vishay WSL-2512 family 'component temperature "
                    "coefficient (including terminal)' bucket '7 mOhm to 500 mOhm: ±75 ppm/°C' "
                    "(lib/datasheets/WSL-30100.pdf, 'WSL RESISTOR CHARACTERISTICS' table) -- a "
                    "DIFFERENT manufacturer/part family used only as an order-of-magnitude "
                    "stand-in. Do not treat as a sourcing decision.",
        "boards": "24-pin ATX 5VSB shunt (spec §6.4) -- OQ-11 open for this value.",
    },
}

# Vishay WSL/WSK family (Power Metal Strip(R)) -- the DECLINED 4-terminal Kelvin
# alternative (CLAUDE.md: "shunt land = honest 2-pad R_2512 ... NOT the 4-terminal
# WSK2512"). Not the shipped part, but its published COMPONENT TCR table (which
# separates the resistive-ELEMENT TCR from the copper-TERMINAL-dominated total) is
# useful context: it shows component TCR rising sharply as R falls below a few mOhm
# (terminal resistance becomes an increasing fraction of a very-low-value element).
# lib/datasheets/WSL-30100.pdf, 'WSL RESISTOR CHARACTERISTICS' table (WSL0805/1206/
# 2010/2512/2816 column):
WSK_FAMILY_TCR_BUCKETS = (
    # (R_low_ohm, R_high_ohm, component_tcr_ppm_C)
    (7e-3, 500e-3, 75.0),
    (5e-3, 6.9e-3, 110.0),
    (3e-3, 4.9e-3, 150.0),
    (1e-3, 2.9e-3, 275.0),
    (0.5e-3, 0.99e-3, 400.0),
)
WSK_ELEMENT_TCR_PPM_C = 20.0   # "Element TCR ... < 20 ppm/°C" -- the alloy alone, terminal-excluded
WSK_FAMILY_CITATION = (
    "Vishay WSL-30100 datasheet, lib/datasheets/WSL-30100.pdf, 'WSL RESISTOR "
    "CHARACTERISTICS' table: 'Component temperature coefficient (including terminal)' "
    "buckets by resistance value, and 'Element TCR ... < 20 ppm/°C'. Cited here to show "
    "WHY a very-low-value 2-terminal shunt's TOTAL TCR (element + copper terminals) can "
    "run far above the alloy's own TCR -- context for the 24-pin 5VSB proxy entry above, "
    "not a sourcing recommendation (this is the declined 4-terminal WSK family, not the "
    "shipped CSS2H 2-pad part).")


def shunt_wsk_component_tcr_ppm_C(R_ohm):
    """Interpolate-by-bucket the Vishay WSL/WSK 'component TCR including terminal'
    figure for a given resistance (context function -- see WSK_FAMILY_TCR_BUCKETS)."""
    for lo, hi, tcr in WSK_FAMILY_TCR_BUCKETS:
        if lo <= R_ohm <= hi:
            return tcr
    return None


def shunt_tcr_error_pct(shunt_key, T_shunt_C, T_cal_C=25.0):
    """G1: %-reading-error from shunt TCR at a computed shunt temperature.
    %error = TCR[ppm/°C] * (T_shunt_C - T_cal_C) / 1e4 (ppm -> %). A positive
    dT gives a positive %error (the shunt resistance rose, so a fixed-gain
    firmware reading UNDER-reports true current unless compensated -- sign
    convention: this returns the magnitude of the resistance shift, the
    consuming firmware/report layer decides over- vs under-read)."""
    spec = SHUNT_TCR_TABLE[shunt_key]
    dT = T_shunt_C - T_cal_C
    return spec["tcr_ppm_C"] * dT / 1e4


# ============================================================ (b) thermal EMF (Seebeck)
# G4: dissimilar-metal junctions in the Kelvin sense path generate a parasitic
# thermoelectric voltage proportional to the temperature GRADIENT across the
# junction pair (NOT the absolute temperature -- a uniformly hot but gradient-free
# junction produces zero Seebeck voltage). Two junction pairs, per the task:
SEEBECK_JUNCTIONS = {
    "shunt_element_vs_cu_terminal": {
        "uV_per_C": 3.0,
        "citation": "Vishay WSL-30100 datasheet, lib/datasheets/WSL-30100.pdf, front-page "
                    "feature bullet: 'Low thermal EMF (< 3 uV/°C)' -- this is the "
                    "resistive-alloy-ELEMENT-to-copper-TERMINAL junction pair inherent to "
                    "every Power-Metal-Strip-class Kelvin current-sense shunt. Bourns' own "
                    "CSS2H-2512 datasheet (lib/datasheets/Bourns_CSS2H-2512.pdf) lists "
                    "'Low thermal EMF' as a feature bullet but publishes no number, so the "
                    "Vishay same-technology-class figure is used as the representative "
                    "conservative (upper-bound) value. The alloy element itself is not "
                    "necessarily branded Manganin, but is the same class of low-TCR/"
                    "low-thermal-EMF current-sense alloy the task's 'Manganin/similar' "
                    "language refers to; true Manganin (Cu86Mn12Ni2) is separately "
                    "documented in resistance-alloy manufacturer literature (e.g. "
                    "Isabellenhuette technical data) with thermal EMF vs copper in the "
                    "same ~1-3 uV/°C order of magnitude -- consistent, not independently "
                    "re-verified here (UNVERIFIED-exact-alloy).",
        "unverified": True,
    },
    "cu_vs_snpb_solder": {
        "uV_per_C": 3.0,
        "citation": "Published metrology-industry reference (Keithley/Tektronix 'Low "
                    "Level Measurements Handbook', a standard public reference for "
                    "thermal-EMF-vs-copper values of common junction-pair materials): "
                    "Cu-to-Sn/Pb-solder thermal EMF is commonly cited in the ~1-3 uV/°C "
                    "range. NOT vendored in this repo's lib/datasheets/ -- a named "
                    "published-literature source per the citation-discipline hard rule. "
                    "Upper end of the cited range (3 uV/°C) used, conservatively, matching "
                    "the WSL shunt-element figure's order of magnitude.",
        "unverified": True,
    },
}


def thermal_emf_false_current_A(dT_junction_C, shunt_R_ohm, *, junction="shunt_element_vs_cu_terminal"):
    """G4: Seebeck EMF at a Kelvin junction pair, expressed as an EQUIVALENT FALSE
    READING in amps at the given shunt's V/A scale (the natural unit for comparing
    against a real current reading, since the Kelvin sense path measures V=I*R and
    a parasitic series EMF is indistinguishable from a real IR drop of the same
    sign). dT_junction_C is the temperature GRADIENT ACROSS the junction pair (not
    an absolute temperature) -- the solver's own two nearby-node temperatures,
    differenced by the caller."""
    spec = SEEBECK_JUNCTIONS[junction]
    emf_V = spec["uV_per_C"] * abs(dT_junction_C) * 1e-6
    return emf_V / shunt_R_ohm if shunt_R_ohm > 0 else float("inf")


# ============================================================ (c) sense-amp drift
# G2: current-sense-amplifier offset + gain temperature coefficients, applied at
# the amplifier's OWN local temperature (which the solve's discrete-source model
# --  cec_thermal_sources' sense_amp entries -- places it at, including its own
# self-heating -- G5, folded in by the CALLER passing the right T_C, not by this
# module, which stays solver-agnostic).
SENSE_AMP_DRIFT = {
    "INA238": {
        "vos_shunt_drift_nV_C": 20.0,      # max, TA=-40..125C
        "vos_bus_drift_uV_C": 40.0,        # max
        "gain_drift_ppm_C": 25.0,          # max, shunt and bus gain error drift both ±25ppm/°C
        "citation": "TI INA238 datasheet, lib/datasheets/INA238.pdf, Electrical "
                    "Characteristics: dVos/dT (shunt) ±2 typ/±20 max nV/°C (line ~232); "
                    "dVos/dT (VBUS) ±4 typ/±40 max uV/°C (line ~235); GS_DRFT/GB_DRFT "
                    "±25 ppm/°C max (lines ~243, ~245).",
    },
    "INA228": {
        "vos_shunt_drift_nV_C": 10.0,
        "vos_bus_drift_uV_C": 20.0,
        "gain_drift_ppm_C": 20.0,
        "citation": "TI INA228 datasheet, lib/datasheets/INA228.pdf, Electrical "
                    "Characteristics: dVos/dT (shunt) ±2 typ/±10 max nV/°C (line ~253); "
                    "dVos/dT (VBUS) ±4 typ/±20 max uV/°C (line ~256); GS_DRFT/GB_DRFT "
                    "±20 ppm/°C max (lines ~264, ~266).",
    },
    "INA240": {
        "vos_shunt_drift_nV_C": 200.0,
        "vos_bus_drift_uV_C": None,      # INA240 has no VBUS pin (a CSA, not a power monitor)
        "gain_drift_ppm_C": 50.0,
        "citation": "UNVERIFIED -- no INA240 datasheet (TI SBOS662-class) is vendored in "
                    "lib/datasheets/ as of this writing. Figures are order-of-magnitude "
                    "placeholders from general TI zero-drift bidirectional CSA family "
                    "knowledge (typically higher offset drift but comparable-or-better "
                    "gain drift than the INA23x power-monitor family, since it is a "
                    "simpler analog-output part with no internal ADC path). Treat as "
                    "provisional; vendor the datasheet before relying on this for a gate.",
        "unverified": True,
    },
    "INA181": {
        "vos_shunt_drift_nV_C": 300.0,
        "vos_bus_drift_uV_C": None,
        "gain_drift_ppm_C": 40.0,
        "citation": "UNVERIFIED-partial -- lib/datasheets/INA181A2IDBVR.pdf documents IQ "
                    "precisely (see cec_thermal_sources.SENSE_AMP_SPECS) but the offset/"
                    "gain DRIFT figures used here were not located in the extracted text "
                    "at review time; order-of-magnitude placeholders pending a targeted "
                    "re-read of the full datasheet's Electrical Characteristics table.",
        "unverified": True,
    },
}


def sense_amp_drift(part, T_local_C, T_cal_C=25.0, *, channel="shunt"):
    """G2 (+G5 by construction -- T_local_C is whatever the caller's solve says
    the amp's OWN node runs at, self-heating included): returns
    {offset_V, gain_pct} at the given local temperature vs calibration."""
    spec = SENSE_AMP_DRIFT[part]
    dT = T_local_C - T_cal_C
    if channel == "shunt":
        offset_V = spec["vos_shunt_drift_nV_C"] * 1e-9 * dT
    else:
        vb = spec.get("vos_bus_drift_uV_C")
        offset_V = (vb * 1e-6 * dT) if vb is not None else 0.0
    gain_pct = spec["gain_drift_ppm_C"] * dT / 1e4
    return {"offset_V": offset_V, "gain_pct": gain_pct,
           "unverified": bool(spec.get("unverified")), "citation": spec["citation"]}


# ============================================================ (d) reference / ADC drift
# G3: REF3030 (12VHPWR Standard's ratiometric ADC reference, spec v3.8 §6.1) TC, plus
# the ESP32 SAR-ADC's own gain/offset temperature behavior -- marked UNVERIFIED, no
# citable coefficient found in the vendored module datasheets (checked
# lib/datasheets/ESP32-S3-WROOM-1.pdf: pin-mux table only, no ADC electrical-
# characteristics table with a TC figure; Espressif's own errata/characterization
# notes describe the SAR ADC as non-linear and calibrated via on-chip eFuse curves
# at the driver level [esp_adc_cal], not a simple ppm/°C datasheet spec).
REF_DRIFT = {
    "REF3030": {
        "drift_ppm_C_full_temp": 65.0,   # max, -40..125C (REF30 grade, not REF30E)
        "drift_ppm_C_0_70": 50.0,        # max, 0..70C -- the realistic PC-interior operating band
        "citation": "TI REF30/REF30E datasheet SBVS032K, lib/datasheets/REF30E-REF30.pdf, "
                    "'Specification comparision' table: REF30 grade (REF3030AIDBZR, the "
                    "part actually populated) max temperature drift 65 ppm/°C (-40 to "
                    "125°C) / 50 ppm/°C (0 to 70°C).",
    },
}
ESP32_ADC_DRIFT_UNVERIFIED = {
    "citation": "UNVERIFIED -- no ADC gain/offset temperature-coefficient figure is "
               "documented in the vendored module datasheets (lib/datasheets/"
               "ESP32-S3-WROOM-1.pdf / ESP32-C6-MINI-1.pdf carry only the pin-mux "
               "tables). Espressif's own SAR-ADC characterization is non-linear and is "
               "normally corrected in firmware via the eFuse-based esp_adc_cal curves, "
               "not expressed as a single ppm/°C datasheet spec. This module reports "
               "the ESP32 ADC contribution as an explicit 'UNVERIFIED, not modeled' "
               "line in accuracy_vs_load_report() rather than silently omitting or "
               "guessing a number.",
}


def reference_drift_pct(part, T_local_C, T_cal_C=25.0, *, band="0_70"):
    spec = REF_DRIFT[part]
    key = "drift_ppm_C_0_70" if band == "0_70" else "drift_ppm_C_full_temp"
    dT = T_local_C - T_cal_C
    return spec[key] * dT / 1e4


# ============================================================ (e) per-board accuracy-vs-load report
@dataclass
class ChannelSpec:
    """One current-sense channel's error-budget inputs. `shunt_T_key` /
    `amp_T_key` index into the `temps` dict accuracy_vs_load_report() is
    called with -- decoupling this module from any particular solver's
    location-naming convention."""
    name: str
    shunt_key: str
    I_nominal_A: float
    sense_amp_part: str = None
    shunt_T_key: str = None
    amp_T_key: str = None
    junction_dT_C: float = 0.0          # gradient ACROSS the Kelvin junction pair (G4 input)
    uses_ref3030: bool = False
    ref_part: str = "REF3030"
    T_cal_C: float = 25.0


# The platform's own stated accuracy claims (spec v3.4/v3.8, CLAUDE.md "12VHPWR
# Standard: six INA240 ... Accuracy ~+/-1%, see OQ-8" and "REF3030 ratiometric... lifting
# ... currents from ~+/-1% to ~+/-0.3-0.5%"). Reused here as the reconciliation target,
# not re-derived.
PLATFORM_ACCURACY_CLAIM_PCT = {"baseline": 1.0, "with_ref3030": 0.5}
PLATFORM_ACCURACY_CLAIM_CITATION = (
    "CLAUDE.md '12VHPWR Standard' row: 'six INA240 per-pin current-sense amps ... "
    "Accuracy ~+/-1%, see OQ-8' and the v3.8 REF3030 addition note: 'lifting the rail "
    "divider + all 6 INA240 currents from ~+/-1% to ~+/-0.3-0.5%'. This module "
    "reconciles its computed error budget against 1.0% (no ref3030) / 0.5% (with "
    "ref3030, upper end of the cited 0.3-0.5% band -- conservative choice).")


def channel_error_budget(spec, temps, cfg=None):
    """One channel's error contributors + an RSS-combined total. Every
    contributor is independently reported (not just summed) so a caller can
    see WHICH term dominates."""
    shunt_spec = SHUNT_TCR_TABLE[spec.shunt_key]
    R = shunt_spec["R_ohm"]
    T_shunt = temps.get(spec.shunt_T_key, spec.T_cal_C) if spec.shunt_T_key else spec.T_cal_C

    tcr_pct = shunt_tcr_error_pct(spec.shunt_key, T_shunt, spec.T_cal_C)

    emf_A = thermal_emf_false_current_A(spec.junction_dT_C, R)
    emf_pct = 100.0 * emf_A / spec.I_nominal_A if spec.I_nominal_A > 0 else 0.0

    contributors = [
        {"term": "shunt_tcr", "pct": abs(tcr_pct), "unverified": False,
         "citation": shunt_spec["citation"]},
        {"term": "thermal_emf", "pct": abs(emf_pct),
         "unverified": SEEBECK_JUNCTIONS["shunt_element_vs_cu_terminal"]["unverified"],
         "citation": SEEBECK_JUNCTIONS["shunt_element_vs_cu_terminal"]["citation"]},
    ]

    if spec.sense_amp_part:
        T_amp = temps.get(spec.amp_T_key, spec.T_cal_C) if spec.amp_T_key else spec.T_cal_C
        d = sense_amp_drift(spec.sense_amp_part, T_amp, spec.T_cal_C, channel="shunt")
        # offset error expressed as equivalent %-of-nominal-reading at this shunt's V/A scale
        offset_pct = 100.0 * abs(d["offset_V"]) / (spec.I_nominal_A * R) if (spec.I_nominal_A * R) > 0 else 0.0
        contributors.append({"term": "sense_amp_offset", "pct": offset_pct,
                             "unverified": d["unverified"], "citation": d["citation"]})
        contributors.append({"term": "sense_amp_gain", "pct": abs(d["gain_pct"]),
                             "unverified": d["unverified"], "citation": d["citation"]})

    if spec.uses_ref3030:
        T_ref = temps.get(spec.amp_T_key, spec.T_cal_C) if spec.amp_T_key else spec.T_cal_C
        ref_pct = reference_drift_pct(spec.ref_part, T_ref, spec.T_cal_C)
        contributors.append({"term": "reference_tc", "pct": abs(ref_pct), "unverified": False,
                             "citation": REF_DRIFT[spec.ref_part]["citation"]})

    contributors.append({"term": "esp32_adc", "pct": 0.0, "unverified": True,
                         "citation": ESP32_ADC_DRIFT_UNVERIFIED["citation"],
                         "note": "not modeled -- no citable coefficient; reported as an "
                                 "explicit gap, not folded into the RSS total below."})

    modeled = [c for c in contributors if c["term"] != "esp32_adc"]
    rss_pct = math.sqrt(sum(c["pct"] ** 2 for c in modeled))
    any_unverified = any(c["unverified"] for c in contributors)
    return {"name": spec.name, "I_nominal_A": spec.I_nominal_A,
           "contributors": contributors, "rss_pct": round(rss_pct, 5),
           "any_unverified": any_unverified}


def accuracy_gate(rss_pct, *, uses_ref3030=False, claim_pct=None):
    """Pass/fail against the platform's own stated accuracy claim (or an
    explicit override). Returns (passed, limit_pct)."""
    if claim_pct is None:
        claim_pct = (PLATFORM_ACCURACY_CLAIM_PCT["with_ref3030"] if uses_ref3030
                    else PLATFORM_ACCURACY_CLAIM_PCT["baseline"])
    return rss_pct <= claim_pct, claim_pct


def accuracy_vs_load_report(board, channels, temps, cfg=None):
    """Per-board accuracy-vs-load report: one channel_error_budget() per
    ChannelSpec in `channels`, plus the platform-claim reconciliation gate."""
    rows = []
    for spec in channels:
        row = channel_error_budget(spec, temps, cfg)
        passed, limit = accuracy_gate(row["rss_pct"], uses_ref3030=spec.uses_ref3030)
        row["claim_limit_pct"] = limit
        row["within_claim"] = passed
        rows.append(row)
    return {"board": board, "channels": rows,
           "claim_citation": PLATFORM_ACCURACY_CLAIM_CITATION}


def format_accuracy_table(report):
    lines = ["Accuracy-vs-load report: %s" % report["board"]]
    for row in report["channels"]:
        verdict = "WITHIN CLAIM" if row["within_claim"] else "EXCEEDS CLAIM"
        lines.append("  %-14s I_nom=%6.2fA  RSS_error=%.4f%%  claim<=%.2f%%  %s%s" %
                     (row["name"], row["I_nominal_A"], row["rss_pct"],
                      row["claim_limit_pct"], verdict,
                      " [contains UNVERIFIED terms]" if row["any_unverified"] else ""))
        for c in row["contributors"]:
            flag = " [UNVERIFIED]" if c["unverified"] else ""
            note = "  (%s)" % c["note"] if c.get("note") else ""
            lines.append("      %-16s %8.5f%%%s%s" % (c["term"], c["pct"], flag, note))
    return "\n".join(lines)


# ============================================================ CLI self-test / demo
def main():
    # 12VHPWR Standard @ its 600W design point: cased dT~23C per CLAUDE.md's
    # committed thermal number (12vhpwr-standard PCB finish note: "maxT 72.95C /
    # dT 22.95C = PASS at balanced 600W/50A", metal-case TIM-cooled). Ambient in
    # that same result is the enclosed_passive design bucket (~50C, matching
    # cec_synth_pipeline._AMBIENT["enclosed_passive"] -- reused here as a
    # LITERAL for isolation, not imported).
    ambient_C = 50.0
    T_shunt_hot = ambient_C + 22.95      # the committed cased dT figure (CLAUDE.md)
    temps = {"RS1_hot": T_shunt_hot, "U10_amp": T_shunt_hot - 3.0}  # amp sits slightly
    # cooler than the shunt it's Kelvin-sensing (a few mm of copper away) -- a
    # documented ESTIMATE (no per-component nodal split from a single dT figure),
    # not a modeled result.
    channels = [
        ChannelSpec(name="pin1", shunt_key="css2h_2512_1m0", I_nominal_A=8.33,
                    sense_amp_part="INA240", shunt_T_key="RS1_hot", amp_T_key="U10_amp",
                    junction_dT_C=3.0, uses_ref3030=True),
    ]
    report = accuracy_vs_load_report("12vhpwr-standard", channels, temps)
    print(format_accuracy_table(report))


if __name__ == "__main__":
    main()
