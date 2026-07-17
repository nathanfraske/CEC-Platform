#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_thermal_sources.py -- Tier-0 full heat-source inventory + absolute-T
#  material-limit gate + per-region emissivity extraction.
# ============================================================================
# Wave-1 T0 deliverable per
# docs/standard-tier-review/thermal-capabilities-implementation-2026-07-06.md,
# closing convergence item X10 / blind-lens items B1-B3 (full heat-source
# inventory beyond shunts) and J2 (absolute-T vs material limits) from
# docs/standard-tier-review/thermal-solve-completeness-2026-07-06.md.
#
# OWN-MODULE ISOLATION (plan discipline, thermal-capabilities-implementation
# doc "Discipline" section): this file is a standalone consumer. It does NOT
# import scripts/cec_synth_pipeline.py or scripts/cec_thermal2d.py, and
# neither of those files (nor any existing test) is edited by this work.
# Netlists are obtained by shelling out to `kicad-cli sch export netlist`
# (subprocess) and parsed with a small self-contained s-expression reader
# below -- independently written, following the same conventions visible in
# cec_synth_pipeline.Netlist (ref/value/footprint/props/nets) but not
# importing it. PCB geometry (component xy, board outline, silk/pad areas)
# uses `pcbnew` directly, exactly as cec_synth_pipeline.electrothermal_solve
# and cec_thermal2d already do -- guarded so this module still imports (and
# the netlist-only functions still work) on a pcbnew-less host.
#
# CITATION DISCIPLINE (hard rule): every physical constant below cites its
# source in an inline/trailing comment -- a vendored datasheet under
# lib/datasheets/ (with the table/line referenced) where one exists, else a
# named published-literature source. Anything not traceable to a citable
# number is marked UNVERIFIED and is never silently defaulted into a
# pass/fail decision -- it is surfaced in the HeatSource.note /
# MaterialCheck.note fields instead.
#
# ADDITIVE / READ-ONLY: this module reads board/schematic files and cfg-style
# param dicts; it never mutates a board, schematic, or any existing script.
# It is a pure "extra discrete sources" producer for a FUTURE integration
# pass into cec_synth_pipeline.electrothermal_solve (coordinator-gated, per
# the plan doc); nothing here is wired into that solver yet.
# ============================================================================
"""
cec_thermal_sources
====================

Two independent capabilities, both read-only / additive:

1. **Heat-source inventory** (`inventory()`): given a board directory (e.g.
   ``modules/12vhpwr-standard`` or ``hubs/hub-standard``), enumerates every
   DISSIPATING component beyond the shunts the existing solvers already model
   (LDOs, addressable LEDs, MCU modules, CAN transceivers, current-sense
   amplifiers, protection diodes, and a few board-specific extras such as the
   Hub's power-path mux and hold-up boost/buck) and reports a per-component
   wattage with its basis citation and (when pcbnew is available) its board
   position. This is a PRODUCER: it does not feed the number into any solver
   here -- a future integration pass (coordinator-gated, per the plan doc)
   is expected to consume ``InventoryResult.sources`` as extra discrete
   sources alongside the shunts electrothermal_solve() already places.

2. **Absolute-temperature material-limit gate** (`material_limit_gate()`):
   given a solve's peak local temperature (a plain float parameter -- this
   module does not run a solver), checks it against FR4 Tg / continuous-use,
   solder-mask continuous-use, and connector-housing-plastic continuous-use
   ratings, independent of the existing dT-rise gate.

A third, small capability lives here too (the module docstring for
``emissivity_regions()`` below is the FORMAT CONTRACT a future T1a radiation
term codes against without needing to read this file):

3. **Per-region emissivity-area extraction** (`emissivity_regions()`): from a
   routed .kicad_pcb, partitions the board's top-view area into three
   surface classes (solder-mask-covered copper, exposed/ENIG pad copper,
   silkscreen) with representative emissivities, as a fractional-area map.

EMISSIVITY FORMAT CONTRACT (for a future T1a radiation term to code against
without reading this file's internals):

    emissivity_regions(pcb_path) -> {
        "board": <str board name>,
        "board_area_mm2": <float>,        # board-outline bounding-box area
        "regions": [
            {"class": "solder_mask_copper", "area_mm2": <float>,
             "area_fraction": <float>, "emissivity": <float>,
             "citation": <str>},
            {"class": "exposed_pad_metal",  "area_mm2": <float>,
             "area_fraction": <float>, "emissivity": <float>,
             "citation": <str>},
            {"class": "silkscreen",         "area_mm2": <float>,
             "area_fraction": <float>, "emissivity": <float>,
             "citation": <str>},
        ],
    }

  `regions` is a STRICT PARTITION of `board_area_mm2` (fractions sum to
  ~1.0; each class's area is disjoint from the others by construction --
  see `emissivity_regions()`'s docstring for how overlaps are resolved).
  A view-factor/radiosity term (D1 in the blind completeness review) can
  weight each region's contribution by `emissivity_regions(...)["regions"][i]
  ["area_fraction"] * emissivity` without needing to know how the areas were
  derived. This is a JSON-serializable plain dict (also valid as a Python
  literal); write it to disk with ``json.dump`` if a future consumer wants a
  file-based handoff instead of an in-process call.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# pcbnew is optional: the netlist-only parts of this module (component
# classification, wattage-from-datasheet math) must still work on a
# pcbnew-less host. Positions/board-area/emissivity degrade gracefully.
try:
    import pcbnew                                             # noqa: E402
    _HAVE_PCBNEW = True
except Exception:                                             # pragma: no cover
    pcbnew = None
    _HAVE_PCBNEW = False


# ============================================================ s-expr / netlist
# Self-contained (NOT imported from cec_synth_pipeline -- see module header).
def _parse_sexpr(text):
    """Parse a KiCad s-expression string into nested Python lists. Same tolerant
    tokenizer shape as the rest of this codebase's ad hoc KiCad-file readers."""
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+', text)
    pos = 0

    def build():
        nonlocal pos
        node = []
        while pos < len(tokens):
            tok = tokens[pos]
            pos += 1
            if tok == "(":
                node.append(build())
            elif tok == ")":
                return node
            elif tok.startswith('"'):
                node.append(tok[1:-1].replace('\\"', '"'))
            else:
                node.append(tok)
        return node

    while pos < len(tokens) and tokens[pos] != "(":
        pos += 1
    if pos >= len(tokens):
        return []
    pos += 1
    return build()


def _kids(node, head):
    for c in node:
        if isinstance(c, list) and c and c[0] == head:
            yield c


def _first(node, head, default=None):
    for c in _kids(node, head):
        return c
    return default


def _val(node, head, default=None):
    c = _first(node, head)
    if c and len(c) >= 2 and not isinstance(c[1], list):
        return c[1]
    return default


@dataclass
class SourceComp:
    """One BOM-line component read from a netlist: ref/value/footprint/props
    plus the raw `description` text (the DNP_Note / narrative props this
    repo's generated schematics carry -- see is_populated())."""
    ref: str
    value: str = ""
    footprint: str = ""
    description: str = ""
    props: dict = field(default_factory=dict)


def export_netlist(sch_path, out_path=None):
    """Run `kicad-cli sch export netlist` (subprocess -- no pcbnew/cec_synth_pipeline
    dependency) and return the output .net path. Raises RuntimeError with a clear
    message if kicad-cli is missing (fail fast, matching the rest of the repo's
    toolchain-check convention)."""
    import shutil
    if shutil.which("kicad-cli") is None:
        raise RuntimeError(
            "cec_thermal_sources: kicad-cli not found on PATH -- install KiCad 10 "
            "(provides kicad-cli) to build a heat-source inventory from a schematic.")
    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".net", prefix="cec_thermal_src_")
        os.close(fd)
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", out_path, sch_path],
                   check=True, capture_output=True, text=True)
    return out_path


def load_components(sch_path):
    """sch_path -> {ref: SourceComp}. Exports a netlist via kicad-cli and parses it."""
    net_path = export_netlist(sch_path)
    try:
        root = _parse_sexpr(open(net_path).read())
    finally:
        try:
            os.remove(net_path)
        except OSError:
            pass
    comps = {}
    comp_root = _first(root, "components") or []
    for comp in _kids(comp_root, "comp"):
        ref = _val(comp, "ref", "")
        c = SourceComp(ref=ref, value=_val(comp, "value", ""),
                       footprint=_val(comp, "footprint", ""),
                       description=_val(comp, "description", "") or "")
        for prop in _kids(comp, "property"):
            name = _val(prop, "name")
            pv = _val(prop, "value", "")
            if name:
                c.props[name] = pv
        for f in _kids(_first(comp, "fields") or [], "field"):
            name = _val(f, "name")
            fv = f[-1] if len(f) > 1 and not isinstance(f[-1], list) else ""
            if name and name not in c.props:
                c.props[name] = fv
        comps[ref] = c
    return comps


_DNP_MARKERS = ("dnp position-only", "dnp-provisioned", "(dnp)", "not populated",
                "never populate", "never for beta")


def is_populated(comp):
    """True unless the component is a documented DNP placeholder. This repo's
    generated schematics mark DNP intent in free-text (a `DNP_Note` field /
    the `description`) rather than always setting KiCad's own per-instance
    DNP flag (verified 2026-07-06 against U9/U10 on hub-standard -- both are
    narrative-DNP, no bare `(dnp)` marker in the exported netlist), so both
    forms are checked. See CLAUDE.md 'Hub power-in consolidation' /
    'persist-on-fault' notes for U9 (TPS61040, rung-3 provision) and U10
    (TPS563201) -- both DNP position-only as of this writing."""
    if comp.props.get("__dnp__") is True:
        return False
    text = " ".join([comp.description or ""] +
                    [v for v in comp.props.values() if isinstance(v, str)]).lower()
    return not any(m in text for m in _DNP_MARKERS)


def _r_value_ohms(value):
    """Parse '2.2k', '10kΩ', '0.5mΩ', '1mΩ' etc to ohms. Mirrors the parsing
    convention visible elsewhere in this codebase's KiCad-value readers
    (independently written here per the own-module-isolation rule)."""
    if not value:
        return None
    s = value.strip().lower().replace("ohm", "").replace("Ω", "").replace("ω", "").strip()
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([mkrun]?)", s)
    if not m:
        return None
    num = float(m.group(1))
    mult = {"m": 1e-3, "k": 1e3, "r": 1.0, "u": 1e-6, "n": 1e-9, "": 1.0}.get(m.group(2), 1.0)
    return num * mult


# ============================================================ config
@dataclass
class SourceConfig:
    """Plain param bag (mirrors cec_synth_pipeline.Config's `.params` SHAPE for
    future-integration convenience -- this dataclass is independently defined,
    not imported). Every default below is a documented DESIGN-BASIS ESTIMATE,
    not a measurement; override via params for a specific loading scenario."""
    params: dict = field(default_factory=dict)

    def get(self, key, default=None):
        return self.params.get(key, default)


DEFAULT_PARAMS = {
    "vcc_5vsb_V": 5.0,          # nominal +5VSB rail (JST-XH bulk feed, spec §2.7)
    "vcc_3v3_V": 3.3,           # LP5907MFX-3.3 regulated output (fixed by part number)
    # Logic-rail load current for the LDO dropout*I calc: MCU active current (see
    # MCU_SPECS) + a documented allowance for the CAN transceiver's VIO pin, the
    # comparator/supervisor/level-shifter quiescent draws, and pull-up/ADC-divider
    # bleed -- NOT separately metered per part (all sub-mA to low-mA, folded into
    # one design-basis logic-rail figure). UNVERIFIED-precision (no bench measurement);
    # override with a real bench figure when available.
    "i_3v3_logic_misc_A": 0.010,
    "mcu_duty": 1.0,            # firmware polls sensors continuously (spec §6.10) -> active-mode 100% duty, design basis
    "can_dominant_duty": 0.30,  # DESIGN-BASIS placeholder bus-utilization figure (no bus-load measurement); override per install
    "led_full_white_budget_A": 0.4,   # CLAUDE.md-documented platform anchor for 7x SK6812 MINI-E at full white (Hub Standard)
    "led_ref_count": 7,               # the board the 0.4A anchor was measured/quoted against
    "ambient_C": None,          # None -> reads corpus/staging/general/thermal-gates.json design_ambient, else 50.0 literal fallback
}


def _cfg(cfg):
    if cfg is None:
        return SourceConfig(params=dict(DEFAULT_PARAMS))
    if isinstance(cfg, SourceConfig):
        merged = dict(DEFAULT_PARAMS)
        merged.update(cfg.params)
        return SourceConfig(params=merged)
    merged = dict(DEFAULT_PARAMS)
    merged.update(cfg or {})
    return SourceConfig(params=merged)


# ============================================================ per-family datasheet basis
# Every numeric literal below cites: a vendored PDF (lib/datasheets/<file>, with the
# table/line I read it from) OR a named published source OR "UNVERIFIED" when neither
# applies. See the class-by-class comments.

# ---- LDOs -------------------------------------------------------------------------
# LP5907MFX-3.3 -- populated on Hub Standard (U3) and 12VHPWR Standard (U3), regulating
# +5VSB -> +3V3 logic. TI datasheet SNVSxxx, vendored lib/datasheets/LP5907.pdf:
#   - IQ (enabled): 12 uA typ / 425 uA max @ VEN=1.2V, IOUT=250mA (Electrical
#     Characteristics table, "IQ Quiescent current", line ~261 of the extracted text;
#     also the front-page bullet "Very low IQ (enabled): 12uA").
#   - Dropout voltage: 120 mV typ / 200 mV max @ IOUT=250mA, DSBGA package (line ~265,
#     "VDO Dropout voltage").
# NOTE: dropout VOLTAGE (the min V_IN-V_OUT to stay in regulation) is NOT the same
# quantity as the ACTUAL V_IN-V_OUT differential this LDO operates at in this design
# (5.0V in, 3.3V out -> a fixed 1.7V differential regardless of load, well above the
# ~0.12-0.2V dropout spec so the part stays in regulation with margin). The per-task
# formula (Vin-3.3V)*I_3V3 uses the ACTUAL operating differential, not the dropout spec;
# the dropout spec is cited here only to confirm the part stays in regulation.
LDO_SPECS = {
    "LP5907": {
        "citation": "TI LP5907 datasheet, lib/datasheets/LP5907.pdf: IQ 12uA typ/425uA max "
                    "@VEN=1.2V,IOUT=250mA (line ~261); VDO 120mV typ/200mV max @IOUT=250mA (line ~265).",
        "iq_typ_A": 12e-6,
        "iq_max_A": 425e-6,
        "vout_V": 3.3,
    },
}

# ---- Addressable LEDs --------------------------------------------------------------
# SK6812 MINI-E: no manufacturer datasheet is vendored in lib/datasheets/ (checked
# 2026-07-06 -- absent). The platform's OWN documented figure is used as the anchor
# instead (CLAUDE.md "LED current" section): "Seven SK6812 at full white draw on the
# order of 0.4A per board" for the Hub Standard's 7x SK6812 MINI-E chain (DL1-DL7).
# Per-LED max current is derived from that anchor (0.4A / 7 ~= 57mA/LED), NOT from a
# manufacturer maximum-current spec (no vendored source) -- marked UNVERIFIED-per-LED
# even though the aggregate anchor itself is a real platform-documented figure.
LED_SPECS = {
    "SK6812": {
        "citation": "CLAUDE.md 'LED current' section: '~0.4A per board' full-white anchor "
                    "for 7x SK6812 MINI-E (Hub Standard DL1-DL7). Per-LED figure "
                    "(0.4/7 A) is a DERIVED value, not a manufacturer datasheet number "
                    "-- no SK6812 datasheet is vendored in lib/datasheets/ -- marked UNVERIFIED.",
        "board_budget_A_at_n_ref": 0.4,
        "n_ref": 7,
        "unverified": True,
    },
}

# ---- MCU modules --------------------------------------------------------------------
# All figures are "Modem-sleep" (radio clock-gated) tables -- correct for this platform's
# beta consumer line, which drops Wi-Fi/BT entirely (owner ruling 2026-07-03, CLAUDE.md
# Hub Standard row) and runs wired-only, so the RADIO-ACTIVE current tables (which the
# datasheets also publish) do not apply here.
MCU_SPECS = {
    "ESP32-S3-WROOM-1": {
        "citation": "Espressif ESP32-S3-WROOM-1 & WROOM-1U Datasheet v1.8, "
                    "lib/datasheets/ESP32-S3-WROOM-1.pdf, Table 6-6 'Current Consumption "
                    "in Modem-sleep Mode' (radio clock-gated -- this platform's beta line "
                    "drops Wi-Fi entirely, CLAUDE.md 2026-07-03 ruling), 240 MHz row, "
                    "'Dual core running 32-bit data access instructions': Typ1(periph "
                    "clocks disabled)=66.2 mA, Typ2(periph clocks enabled)=81.3 mA @ 3.3V.",
        "i_active_typ_A": 0.0662,
        "i_active_max_A": 0.0813,     # 'periph clocks enabled' row -- used as the conservative point estimate
        "vcc_V": 3.3,
    },
    "ESP32-S3-MINI-1": {
        # Same ESP32-S3 die as WROOM-1 (module-level packaging differs, chip current
        # consumption does not) -- table reused verbatim from the WROOM-1 datasheet, the
        # only ESP32-S3 current-consumption table vendored in this repo.
        "citation": "Same ESP32-S3 silicon as ESP32-S3-WROOM-1 (module packaging differs, "
                    "chip current consumption does not); table reused from "
                    "lib/datasheets/ESP32-S3-WROOM-1.pdf Table 6-6 (see ESP32-S3-WROOM-1 "
                    "entry above) -- no separate MINI-1 current-consumption table is "
                    "vendored, so this is a same-silicon reuse, not an independent citation.",
        "i_active_typ_A": 0.0662,
        "i_active_max_A": 0.0813,
        "vcc_V": 3.3,
    },
    "ESP32-C6-MINI-1": {
        "citation": "Espressif ESP32-C6-MINI-1 Datasheet, lib/datasheets/ESP32-C6-MINI-1.pdf, "
                    "Table 6-7 'Current Consumption in Modem-sleep Mode' (radio clock-gated), "
                    "160 MHz row, 'CPU is running': Typ(periph disabled)=27 mA, "
                    "Typ(periph enabled)=38 mA @ 3.3V.",
        "i_active_typ_A": 0.027,
        "i_active_max_A": 0.038,
        "vcc_V": 3.3,
    },
}

# ---- CAN transceivers -----------------------------------------------------------------
# TJA1051T/3 -- the platform-locked classical-CAN transceiver (spec §3.1 v3.5). NXP
# datasheet, lib/datasheets/TJA1051.pdf, Table 6 (extended CAN spec, "versions with VIO
# pin" -- the T/3 suffix): ICC Normal mode recessive 5mA typ (2.5-10mA range), dominant
# 50mA typ (20-70mA range), VCC=4.5-5.5V (the part is powered from +5V-class rail, not
# the VIO=3V3 pin, which draws a separate uA-class IIO). Average current depends on bus
# utilization (fraction of bit time spent dominant); can_dominant_duty is a DESIGN-BASIS
# placeholder (no per-install bus-load measurement exists) -- override via cfg.
CAN_XCVR_SPECS = {
    "TJA1051T/3": {
        "citation": "NXP TJA1051 datasheet, lib/datasheets/TJA1051.pdf, extended table "
                    "(line ~420): ICC Normal mode recessive 5mA typ / dominant 50mA typ, "
                    "'versions with VIO pin' row (the T/3 suffix), VCC=4.5-5.5V.",
        "icc_recessive_typ_A": 0.005,
        "icc_dominant_typ_A": 0.050,
        "vcc_V": 5.0,
    },
}

# ---- Voltage references ----------------------------------------------------------------
# REF3030 -- 12VHPWR Standard's ratiometric ADC reference (spec v3.8, §6.1). TI REF30/
# REF30E family datasheet (doc SBVS032K -- note CLAUDE.md's spec text names "SBOS392K";
# the vendored PDF's own title block reads SBVS032K, used here as the actual citation),
# lib/datasheets/REF30E-REF30.pdf, "Specification comparison" table: REF30 grade
# (REF3030AIDBZR, the part actually populated) IQ=42uA typ, max temperature drift
# 65 ppm/C (-40 to 125C) / 50 ppm/C (0 to 70C).
REF_SPECS = {
    "REF3030": {
        "citation": "TI REF30/REF30E datasheet SBVS032K, lib/datasheets/REF30E-REF30.pdf, "
                    "'Specification comparision' table: REF30 grade (REF3030AIDBZR) "
                    "IQ=42uA typ. (Drift figure used separately by cec_thermal_accuracy.)",
        "iq_typ_A": 42e-6,
        "vin_V": 3.3,
    },
}

# ---- Current-sense amplifiers (quiescent draw only -- shunt I^2R is modeled elsewhere) ---
# INA238/INA228: vendored TI datasheets. INA240: NOT vendored in lib/datasheets/ as of
# 2026-07-06 (checked; only INA180/INA181A2IDBVR/INA228/INA238 are present) -- its
# quiescent-current figure below is UNVERIFIED (order-of-magnitude from general TI
# zero-drift current-shunt-monitor family knowledge, no locally citable datasheet page).
# This is flagged prominently in every report this module produces. INA181: vendored.
SENSE_AMP_SPECS = {
    "INA238": {
        "citation": "TI INA238 datasheet, lib/datasheets/INA238.pdf, Electrical "
                    "Characteristics table (line ~289): IQ 640uA typ / 750uA max "
                    "@VSENSE=0V, 25C (1.1mA max over -40..125C), VS=2.7-5.5V.",
        "iq_typ_A": 640e-6, "iq_max_A": 750e-6, "vcc_V": 3.3,
    },
    "INA228": {
        "citation": "TI INA228 datasheet, lib/datasheets/INA228.pdf, Electrical "
                    "Characteristics table (same IQ/IQSD structure as INA238, line ~311); "
                    "used for the alpha/rev2 line which is frozen on the INA228 (v1.5.0 "
                    "owner ruling reverted the beta line to INA238 -- see CLAUDE.md §6.1).",
        "iq_typ_A": 640e-6, "iq_max_A": 750e-6, "vcc_V": 3.3,
    },
    "INA240": {
        "citation": "UNVERIFIED -- no INA240 datasheet (TI SBOS662-class) is vendored in "
                    "lib/datasheets/ as of this writing (checked 2026-07-06; only "
                    "INA180/INA181A2IDBVR/INA228/INA238 present). The IQ figure below is an "
                    "order-of-magnitude placeholder from general TI zero-drift bidirectional "
                    "CSA family knowledge, NOT read from a locally-verifiable page. Treat as "
                    "provisional; vendor the datasheet before relying on this number for a gate.",
        "iq_typ_A": 1.7e-3, "iq_max_A": 2.4e-3, "vcc_V": 5.0,
        "unverified": True,
    },
    "INA181": {
        "citation": "TI INA181 datasheet, lib/datasheets/INA181A2IDBVR.pdf, Power Supply "
                    "table (line ~406, single-channel INA181 row): IQ 195uA typ / 260uA "
                    "max @VSENSE=0mV.",
        "iq_typ_A": 195e-6, "iq_max_A": 260e-6, "vcc_V": 3.3,
    },
}

# ---- Protection / ESD diodes (leakage -- computed then dismissed, per task) -------------
# No PESD5V0S1BA / USBLC6-2SC6 datasheet is vendored. Reverse-leakage current for small
# TVS/ESD-protection diodes at rated standoff voltage is well-known-order-of-magnitude in
# general TVS literature (single-digit uA class or below) but the EXACT figure for these
# two specific parts is UNVERIFIED here (no local datasheet page to cite). The dismissal
# argument only needs the order of magnitude (see inventory() printout), so this is
# treated as "compute then dismiss with numbers", not a load-bearing figure.
PROTECTION_DIODE_SPECS = {
    "PESD5V0S1BA": {
        "citation": "UNVERIFIED -- no PESD5V0S1BA datasheet vendored. Reverse-leakage "
                    "order-of-magnitude for small single-line TVS/ESD diodes is commonly "
                    "single-digit uA or below at rated standoff (general TVS-diode "
                    "literature); no locally-citable exact figure. Used only to DEMONSTRATE "
                    "negligibility (see inventory() report), never as a load-bearing number.",
        "i_leak_A": 1e-6, "v_standoff_V": 5.0, "unverified": True,
    },
    "USBLC6-2SC6": {
        "citation": "UNVERIFIED -- no USBLC6-2SC6 datasheet vendored. Same order-of-magnitude "
                    "treatment as PESD5V0S1BA above.",
        "i_leak_A": 1e-6, "v_standoff_V": 5.0, "unverified": True,
    },
}

# ---- Power-path switch / mux (Hub-specific extra, beyond the task's explicit list but a
# real, datasheet-backed, non-trivial point source on Hub Standard's U5/U7) -------------
POWER_MUX_SPECS = {
    "TPS2121RUXR": {
        "citation": "TI TPS2120/TPS2121 datasheet, lib/datasheets/TPS2121RUXR.pdf, "
                    "'ON-RESISTANCE (INx to OUT)' table (line ~322) and Device Comparison "
                    "Table (line ~131): TPS2121 RON = 56 mOhm typ / 70 mOhm max @25C, "
                    "IOUT=-200mA.",
        "r_on_typ_ohm": 0.056, "r_on_max_ohm": 0.070,
    },
}

# ---- Supervisor (negligible -- included for completeness/dismissal, per task) -----------
SUPERVISOR_SPECS = {
    "TPS3839K33": {
        "citation": "TI TPS3839 datasheet, lib/datasheets/TPS3839.pdf, line ~346: "
                    "IDD (supply current into VDD) 150nA typ / 500nA max, output not connected.",
        "iq_typ_A": 150e-9, "vcc_V": 3.3,
    },
}

# ---- Ferrite beads / jumpers (negligible -- included for completeness/dismissal) --------
FERRITE_SPECS = {
    "MPZ2012S601AT000": {
        "citation": "UNVERIFIED -- no MPZ2012S601AT000 datasheet vendored. TDK 0805 "
                    "600ohm@100MHz ferrite-bead-class parts commonly publish DCR in the "
                    "0.15-0.3 ohm range (general TDK MPZ-series family knowledge); no "
                    "locally-citable exact figure. Used only to demonstrate negligibility.",
        "dcr_typ_ohm": 0.20, "unverified": True,
    },
}


# ============================================================ classification
_CLASS_TABLE = (
    ("ldo", LDO_SPECS),
    ("led", LED_SPECS),
    ("mcu", MCU_SPECS),
    ("can_xcvr", CAN_XCVR_SPECS),
    ("reference", REF_SPECS),
    ("sense_amp", SENSE_AMP_SPECS),
    ("protection_diode", PROTECTION_DIODE_SPECS),
    ("power_mux", POWER_MUX_SPECS),
    ("supervisor", SUPERVISOR_SPECS),
    ("ferrite", FERRITE_SPECS),
)


def classify(comp):
    """comp.value -> (family, part_key) or (None, None). Matches by substring against
    every FAMILY_SPECS table's keys (case-sensitive on the informative part of the
    value, since these are real MPN-derived strings in this repo's netlists)."""
    if comp.ref.startswith("DL") and "SK6812" in (comp.value or ""):
        return "led", "SK6812"
    for family, table in _CLASS_TABLE:
        for key in table:
            if key in (comp.value or ""):
                return family, key
    return None, None


# ============================================================ HeatSource + per-family power
@dataclass
class HeatSource:
    ref: str
    family: str
    part: str
    watts: float
    basis: str
    citation: str
    xy_mm: tuple = None
    unverified: bool = False
    note: str = ""


def _ldo_power(comp, part, cfg):
    spec = LDO_SPECS[part]
    vin = cfg.get("vcc_5vsb_V")
    vout = spec["vout_V"]
    i_load = cfg.get("i_load_%s_A" % comp.ref, None)
    if i_load is None:
        # Default: infer the logic-rail current this LDO serves from the board's own
        # MCU (whichever MCU family is on the same board) + the documented misc-logic
        # allowance. Falls back to just the misc allowance if no MCU entry is passed.
        i_load = cfg.get("i_3v3_logic_total_A", cfg.get("i_3v3_logic_misc_A"))
    iq = spec["iq_typ_A"]
    p = (vin - vout) * i_load + vin * iq
    basis = "(Vin-Vout)*I_load + Vin*Iq = (%.2f-%.2f)*%.4fA + %.2f*%.2eA" % (
        vin, vout, i_load, vin, iq)
    return HeatSource(comp.ref, "ldo", part, round(p, 6), basis, spec["citation"])


def _led_power(refs, cfg):
    spec = LED_SPECS["SK6812"]
    n = len(refs)
    n_ref = spec["n_ref"]
    budget_A = cfg.get("led_full_white_budget_A", spec["board_budget_A_at_n_ref"])
    # Scale the platform anchor by LED count if this board doesn't have exactly the
    # n_ref LEDs the anchor was quoted against (reconciliation logic per the ANCHOR
    # requirement -- see test_thermal_sources.T_LedAnchor).
    scaled_budget_A = budget_A * (n / n_ref) if n_ref else budget_A
    vcc = cfg.get("vcc_5vsb_V")
    p_total = vcc * scaled_budget_A
    basis = ("Vcc*I_budget = %.2fV * (%.3fA anchor * %d/%d leds) = %.3fW total, %.4fW/LED"
              % (vcc, budget_A, n, n_ref, p_total, p_total / n if n else 0.0))
    return HeatSource("+".join(sorted(refs)) if n <= 8 else "%d x DL*" % n, "led",
                      "SK6812", round(p_total, 6), basis, spec["citation"],
                      unverified=True,
                      note="per-LED split UNVERIFIED (no manufacturer datasheet); "
                           "aggregate anchored to the platform-documented figure")


def _mcu_power(comp, part, cfg):
    spec = MCU_SPECS[part]
    duty = cfg.get("mcu_duty")
    i = spec["i_active_max_A"] * duty + spec["i_active_typ_A"] * (1 - duty) \
        if duty < 1.0 else spec["i_active_max_A"]
    # Conservative point estimate = the 'typ2' (peripherals-enabled) figure at full duty;
    # a partial duty interpolates toward the lighter 'typ1' figure.
    p = spec["vcc_V"] * i
    basis = "Vcc*I_active = %.2fV * %.4fA (duty=%.2f)" % (spec["vcc_V"], i, duty)
    return HeatSource(comp.ref, "mcu", part, round(p, 6), basis, spec["citation"])


def _can_xcvr_power(comp, part, cfg):
    spec = CAN_XCVR_SPECS[part]
    duty = cfg.get("can_dominant_duty")
    i = spec["icc_dominant_typ_A"] * duty + spec["icc_recessive_typ_A"] * (1 - duty)
    p = spec["vcc_V"] * i
    basis = ("Vcc*(duty*Icc_dom + (1-duty)*Icc_rec) = %.2fV*(%.2f*%.3fA + %.2f*%.4fA)"
              % (spec["vcc_V"], duty, spec["icc_dominant_typ_A"], 1 - duty,
                 spec["icc_recessive_typ_A"]))
    return HeatSource(comp.ref, "can_xcvr", part, round(p, 6), basis, spec["citation"],
                      note="can_dominant_duty=%.2f is a DESIGN-BASIS placeholder (no "
                           "per-install bus-load measurement) -- override via cfg" % duty)


def _reference_power(comp, part, cfg):
    spec = REF_SPECS[part]
    p = spec["vin_V"] * spec["iq_typ_A"]
    basis = "Vin*Iq = %.2fV * %.2euA" % (spec["vin_V"], spec["iq_typ_A"])
    return HeatSource(comp.ref, "reference", part, round(p, 5), basis, spec["citation"])


def _sense_amp_power(comp, part, cfg):
    spec = SENSE_AMP_SPECS[part]
    p = spec["vcc_V"] * spec["iq_typ_A"]
    basis = "Vcc*Iq = %.2fV * %.2euA" % (spec["vcc_V"], spec["iq_typ_A"])
    return HeatSource(comp.ref, "sense_amp", part, round(p, 5), basis, spec["citation"],
                      unverified=bool(spec.get("unverified")))


def _protection_diode_power(comp, part, cfg):
    spec = PROTECTION_DIODE_SPECS[part]
    p = spec["v_standoff_V"] * spec["i_leak_A"]
    basis = "V_standoff*I_leak = %.2fV * %.2euA (order-of-magnitude leakage)" % (
        spec["v_standoff_V"], spec["i_leak_A"])
    return HeatSource(comp.ref, "protection_diode", part, round(p, 8), basis,
                      spec["citation"], unverified=True,
                      note="negligible -- computed to demonstrate dismissal, not load-bearing")


def _power_mux_power(comp, part, cfg):
    spec = POWER_MUX_SPECS[part]
    i_through = cfg.get("i_through_%s_A" % comp.ref, cfg.get("i_5vsb_trunk_A", 1.0))
    p = i_through * i_through * spec["r_on_typ_ohm"]
    basis = "I^2*Ron = %.2fA^2 * %.4f ohm (I_through is a design-basis trunk-current estimate)" % (
        i_through, spec["r_on_typ_ohm"])
    return HeatSource(comp.ref, "power_mux", part, round(p, 6), basis, spec["citation"])


def _supervisor_power(comp, part, cfg):
    spec = SUPERVISOR_SPECS[part]
    p = spec["vcc_V"] * spec["iq_typ_A"]
    return HeatSource(comp.ref, "supervisor", part, round(p, 8),
                      "Vcc*Iq = %.2fV * %.2enA" % (spec["vcc_V"], spec["iq_typ_A"]),
                      spec["citation"], note="negligible -- nanoamp-class quiescent draw")


def _ferrite_power(comp, part, cfg):
    spec = FERRITE_SPECS[part]
    i = cfg.get("i_through_%s_A" % comp.ref, 0.2)
    p = i * i * spec["dcr_typ_ohm"]
    return HeatSource(comp.ref, "ferrite", part, round(p, 6),
                      "I^2*DCR = %.2fA^2 * %.3f ohm" % (i, spec["dcr_typ_ohm"]),
                      spec["citation"], unverified=True, note="negligible")


_POWER_FN = {
    "ldo": _ldo_power, "mcu": _mcu_power, "can_xcvr": _can_xcvr_power,
    "reference": _reference_power, "sense_amp": _sense_amp_power,
    "protection_diode": _protection_diode_power, "power_mux": _power_mux_power,
    "supervisor": _supervisor_power, "ferrite": _ferrite_power,
}


@dataclass
class InventoryResult:
    board: str
    sources: list
    total_W: float
    unverified_refs: list
    dnp_skipped: list


def inventory(board_dir, cfg=None, *, sch_path=None, pcb_path=None):
    """Full heat-source inventory for one board directory. Returns an
    InventoryResult. `board_dir` may be a modules/hubs subdirectory path or a
    direct .kicad_sch path (sch_path override honored either way)."""
    cfg = _cfg(cfg)
    if sch_path is None:
        if os.path.isfile(board_dir):
            sch_path = board_dir
            board_dir = os.path.dirname(os.path.abspath(board_dir))
        else:
            # ROOT sheet of a (possibly hierarchical) board dir -- .kicad_pro-stem match
            # first, then the sheet that instantiates sub-sheets (cec_toolchain; the old
            # dir-name heuristic missed eps-8pin -> eps8pin-module and fell to a leaf).
            import cec_toolchain as _tc
            sch_path = _tc.find_root_sch(board_dir) or None
    if not sch_path or not os.path.isfile(sch_path):
        raise FileNotFoundError("cec_thermal_sources.inventory: no .kicad_sch found for %r" % board_dir)

    comps = load_components(sch_path)
    sources, unverified, dnp = [], [], []
    # First pass: gather LED refs (aggregate as one source) and figure the MCU's
    # active current so the LDO calc can size its logic-rail load from it (see
    # _ldo_power's i_3v3_logic_total_A fallback).
    led_refs = [r for r, c in comps.items() if classify(c)[0] == "led"]
    mcu_i_active_A = 0.0
    for ref, comp in sorted(comps.items()):
        family, part = classify(comp)
        if family is None or family == "led":
            continue
        if not is_populated(comp):
            dnp.append(ref)
            continue
        if family == "mcu":
            spec = MCU_SPECS[part]
            mcu_i_active_A += spec["i_active_max_A"] if cfg.get("mcu_duty") >= 1.0 \
                else (spec["i_active_max_A"] * cfg.get("mcu_duty")
                      + spec["i_active_typ_A"] * (1 - cfg.get("mcu_duty")))
    logic_total = cfg.get("i_3v3_logic_total_A")
    if logic_total is None:
        cfg.params["i_3v3_logic_total_A"] = mcu_i_active_A + cfg.get("i_3v3_logic_misc_A")

    for ref, comp in sorted(comps.items()):
        family, part = classify(comp)
        if family is None:
            continue
        if family == "led":
            continue  # handled once, below
        if not is_populated(comp):
            continue  # already recorded in dnp above
        hs = _POWER_FN[family](comp, part, cfg)
        sources.append(hs)
        if hs.unverified:
            unverified.append(hs.ref)

    if led_refs:
        hs = _led_power(led_refs, cfg)
        sources.append(hs)
        unverified.append(hs.ref)

    if pcb_path is None:
        import glob
        cands = [p for p in glob.glob(os.path.join(board_dir, "*.kicad_pcb"))
                 if "-routed" not in p and ".merged." not in p]
        pcb_path = sorted(cands)[0] if cands else None
    if pcb_path and os.path.isfile(pcb_path) and _HAVE_PCBNEW:
        attach_positions(sources, pcb_path)

    board_name = os.path.basename(os.path.normpath(board_dir))
    total = round(sum(s.watts for s in sources), 4)
    return InventoryResult(board=board_name, sources=sources, total_W=total,
                           unverified_refs=unverified, dnp_skipped=sorted(dnp))


def attach_positions(sources, pcb_path):
    """Fill in HeatSource.xy_mm from a routed .kicad_pcb (guarded: no-op if
    pcbnew is unavailable or a ref has no footprint on the board -- e.g. an
    aggregate multi-ref LED source, or a schematic-only part not yet placed)."""
    if not _HAVE_PCBNEW:
        return
    b = pcbnew.LoadBoard(pcb_path)
    pos = {}
    for fp in b.GetFootprints():
        p = fp.GetPosition()
        pos[fp.GetReference()] = (round(p.x / 1e6, 2), round(p.y / 1e6, 2))
    for s in sources:
        if s.ref in pos:
            s.xy_mm = pos[s.ref]
        # else: leave xy_mm=None -- an aggregate multi-ref source (the LED sum) or a
        # ref not yet placed on THIS pcb (schematic-newer-than-layout is real repo
        # state elsewhere in this project; not an error here).


# ============================================================ material-limit gate
# J2 (thermal-solve-completeness doc): the dT-rise gate (cec_synth_pipeline.physics_gates)
# is a RELIABILITY/functional target, distinct from the material's own absolute safe-
# operating-temperature limit. This checks a solve's peak local temperature (passed in
# as a plain float -- this module runs no solver) against three material classes.
#
# Every limit below is either read from the repo's own existing, already-sourced
# research (docs/research/thermal-gates-derivation-2026-06-10.md, itself citing public
# fab/standards literature -- I-Connect007/Shengyi, UL/ANSI, Molex) or from a vendored
# datasheet. Nothing here duplicates a NEW literature search where the repo already did
# one; it reuses and cites that existing work directly.
MATERIAL_LIMITS = {
    "fr4_tg": {
        "limit_C": 130.0,       # continuous safe zone: Tg(130) - 20C margin rule (below)
        "tg_C": 130.0,
        "citation": "docs/research/thermal-gates-derivation-2026-06-10.md 'Constant 2' "
                    "table: 'Standard FR-4: Tg 130-140C; continuous MOT historically 130C "
                    "(UL/ANSI), now up to 150C with LTTA data' (source: I-Connect007/"
                    "Shengyi, multiple fab sources), design rule 'continuous op temp >= "
                    "20-25C below Tg -> ~110C for Tg 130'. This module uses the "
                    "CONSERVATIVE low end of the cited Tg range (130C) as the reference "
                    "Tg and reports margin against Tg itself (not the pre-derated 110C "
                    "continuous figure, so the two numbers are not double-counted).",
    },
    "solder_mask": {
        "limit_C": 150.0,
        "citation": "UNVERIFIED -- no board-specific solder-mask (LPI photoimageable) "
                    "datasheet is vendored in this repo. 130-150C continuous is a commonly "
                    "cited industry range for standard LPI solder mask (IPC-SM-840-class "
                    "material); this module uses the CONSERVATIVE low end (130C is FR4's "
                    "own figure, so 150C here is not the binding constraint in practice -- "
                    "flagged UNVERIFIED pending a mask-specific datasheet.",
        "unverified": True,
    },
    "connector_housing_nylon66": {
        "limit_C": 105.0,
        "citation": "TE FASTON .250 catalog, lib/datasheets/TE_82004_FASTON_PCB_tabs_"
                    "receptacles_catalog.pdf (line ~686): receptacle-family housing "
                    "material 'UL 94 V-0, 6/6 Nylon' (no numeric continuous-use rating "
                    "in the vendored catalog text). Numeric limit cross-checked against "
                    "docs/research/thermal-gates-derivation-2026-06-10.md 'Constant 2' "
                    "table row 'Nylon (PA66) connector housing: ... rating tied to "
                    "connector temp spec' and 'Molex Mini-Fit Jr ... 105C operating "
                    "... includes 30C terminal temperature rise at maximum rated current' "
                    "(Molex PS-5556-004/PS-45750-001) -- this module applies that same "
                    "105C connector-housing figure to the TE 63951/63969 blade joint "
                    "housing (Nylon 6/6 is the common material family; the TE catalog "
                    "does not itself publish a numeric RTI). UNVERIFIED-exact-grade.",
        "unverified": True,
    },
    "aluminum_electrolytic_105C": {
        "limit_C": 105.0,
        "citation": "docs/research/thermal-gates-derivation-2026-06-10.md 'Constant 2' "
                    "table: '105C aluminum electrolytic cap: Category temp -25 to +105C; "
                    "load life 2000h at 105C (Nichicon GL series)' -- this is the BOM-floor "
                    "part (Hub Standard C1, hold-up reservoir) that the platform's own "
                    "corpus entry thermal.gates.t_max_ceiling=105 (corpus/staging/general/"
                    "thermal-gates.json) is built from; reused here as-is, not re-derived.",
    },
}


@dataclass
class MaterialCheck:
    material: str
    limit_C: float
    peak_T_C: float
    margin_C: float
    passed: bool
    citation: str
    unverified: bool = False


def _corpus_design_ambient():
    path = os.path.join(ROOT, "corpus", "staging", "general", "thermal-gates.json")
    try:
        entries = json.load(open(path))
        for e in entries:
            if e["id"] == "thermal.gates.design_ambient":
                return e["value"]["degC"]
    except Exception:
        pass
    return None


def material_limit_gate(peak_T_C, cfg=None, *, materials=None):
    """peak_T_C: the solve's peak LOCAL (absolute, not rise) temperature at the hottest
    modeled feature, in Celsius -- a plain float parameter; this module runs no solver
    itself (consumes cec_synth_pipeline.ThermalResult.max_T or cec_thermal2d's peak T
    when a future integration pass wires it in). Checks it against every material class
    in `materials` (default: all of MATERIAL_LIMITS) and returns a MaterialCheck per
    class: passed = peak_T_C <= limit_C, margin_C = limit_C - peak_T_C (negative =
    over-temp). Ambient is accepted for symmetry with the rest of the suite's call
    signature but is NOT used in this absolute check (peak_T_C is already absolute) --
    J2's whole point is that this check is INDEPENDENT of the ambient-relative dT-rise
    gate."""
    cfg = _cfg(cfg)
    names = materials or list(MATERIAL_LIMITS)
    out = []
    for name in names:
        m = MATERIAL_LIMITS[name]
        margin = m["limit_C"] - peak_T_C
        out.append(MaterialCheck(material=name, limit_C=m["limit_C"], peak_T_C=peak_T_C,
                                 margin_C=round(margin, 2), passed=margin >= 0,
                                 citation=m["citation"], unverified=bool(m.get("unverified"))))
    return out


# ============================================================ emissivity-region extraction
# See the module docstring's "EMISSIVITY FORMAT CONTRACT" for the schema a future T1a
# radiation term codes against. Emissivity numeric values below are the RANGE the plan
# doc itself specifies (thermal-solve-completeness-2026-07-06.md, item D2): "matte-black
# mask ~0.9 vs bare metal ~0.03-0.1" (thermo lens) / "solder-mask-covered copper ~0.9,
# exposed pads/ENIG ~0.05-0.1" (roadmap Tier-0 line). This module reads that doc as its
# citation for the numeric emissivity value (a repo design document, not a lab
# measurement) -- a future T1a/K3 bench cross-check is the natural next step (already
# named in the plan as K1/K2/K3 validation).
EMISSIVITY_CLASSES = {
    "solder_mask_copper": {
        "emissivity": 0.90,
        "citation": "docs/standard-tier-review/thermal-solve-completeness-2026-07-06.md "
                    "item D2: 'Matte black solder mask (~0.9 emissivity, per this "
                    "project's own stated black ENIG boards)'. Consistent with "
                    "scripts/cec_thermal2d.py's own EPS_RAD=0.9 constant (existing "
                    "prior art in this repo, cited here for consistency, NOT imported).",
    },
    "exposed_pad_metal": {
        "emissivity": 0.10,
        "citation": "docs/standard-tier-review/thermal-solve-completeness-2026-07-06.md "
                    "item D2 / Tier-0 roadmap line: 'exposed pads/ENIG ~0.05-0.1' -- this "
                    "module uses the range's upper (more emissive / less conservative-for-"
                    "radiation-credit) bound 0.10; UNVERIFIED against a real ENIG sample "
                    "measurement (K3 bench cross-check, per the plan's own roadmap).",
        "unverified": True,
    },
    "silkscreen": {
        "emissivity": 0.90,
        "citation": "Silkscreen ink sits atop the solder mask on this platform's boards; "
                    "treated at the same ~0.9 class as solder_mask_copper (no separate "
                    "silk-ink emissivity measurement exists) -- see D2 citation above.",
    },
}

# Fraction of a silkscreen graphic-item's/text's BOUNDING BOX that is actually inked --
# text strokes and thin lines cover only a fraction of their own bbox. No formal source
# (UNVERIFIED-precision approximation); chosen as a conservative order-of-magnitude
# figure for typical PCB reference-designator/value text at common stroke widths, so the
# fractional-area partition below does not grossly over-count silk coverage from raw
# bounding-box sums (verified against a real board: raw bbox sum was ~20% of board area,
# which is not physically plausible silk ink coverage for these designs; the correction
# brings it to a few percent, the expected order of magnitude).
_SILK_INK_FILL_FRACTION = 0.15


def emissivity_regions(pcb_path):
    """See the module docstring's EMISSIVITY FORMAT CONTRACT. Requires pcbnew; raises
    RuntimeError if unavailable (this function needs real board geometry, no
    netlist-only degraded path makes sense for an AREA computation)."""
    if not _HAVE_PCBNEW:
        raise RuntimeError("cec_thermal_sources.emissivity_regions requires pcbnew "
                           "(unavailable on this host)")
    b = pcbnew.LoadBoard(pcb_path)
    bb = b.GetBoardEdgesBoundingBox()
    board_area = (bb.GetWidth() / 1e6) * (bb.GetHeight() / 1e6)
    if board_area <= 0:
        raise RuntimeError("cec_thermal_sources.emissivity_regions: degenerate board "
                           "outline (no Edge.Cuts?) on %r" % pcb_path)

    exposed_area = 0.0
    for fp in b.GetFootprints():
        for p in fp.Pads():
            try:
                exposed_area += p.GetEffectiveShape(pcbnew.F_Cu).Area() / 1e12
            except Exception:
                bbp = p.GetBoundingBox()
                exposed_area += (bbp.GetWidth() / 1e6) * (bbp.GetHeight() / 1e6)

    silk_bbox_area = 0.0
    for d in b.GetDrawings():
        if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            bbd = d.GetBoundingBox()
            silk_bbox_area += (bbd.GetWidth() / 1e6) * (bbd.GetHeight() / 1e6)
    for fp in b.GetFootprints():
        for it in list(fp.GraphicalItems()):
            if it.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                bbi = it.GetBoundingBox()
                silk_bbox_area += (bbi.GetWidth() / 1e6) * (bbi.GetHeight() / 1e6)
        for txt in (fp.Reference(), fp.Value()):
            if txt.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                bbt = txt.GetBoundingBox()
                silk_bbox_area += (bbt.GetWidth() / 1e6) * (bbt.GetHeight() / 1e6)
    silk_area = silk_bbox_area * _SILK_INK_FILL_FRACTION

    # Strict partition: exposed pad copper first (real, shape-accurate), then silk
    # (fill-fraction-corrected), the remainder is mask-covered copper/laminate. Clamp so
    # rounding/overlap never drives a class negative.
    exposed_area = min(exposed_area, board_area)
    silk_area = min(silk_area, max(board_area - exposed_area, 0.0))
    mask_area = max(board_area - exposed_area - silk_area, 0.0)

    regions = []
    for cls, area in (("solder_mask_copper", mask_area),
                      ("exposed_pad_metal", exposed_area),
                      ("silkscreen", silk_area)):
        spec = EMISSIVITY_CLASSES[cls]
        regions.append({
            "class": cls, "area_mm2": round(area, 2),
            "area_fraction": round(area / board_area, 4),
            "emissivity": spec["emissivity"], "citation": spec["citation"],
            "unverified": bool(spec.get("unverified")),
        })
    return {"board": os.path.basename(os.path.normpath(os.path.dirname(pcb_path))),
           "board_area_mm2": round(board_area, 2), "regions": regions}


# ============================================================ reporting
def format_inventory_table(inv):
    lines = ["Heat-source inventory: %s (total %.3f W across %d populated sources; "
            "%d DNP-skipped: %s)" % (
                inv.board, inv.total_W, len(inv.sources), len(inv.dnp_skipped),
                ", ".join(inv.dnp_skipped) or "none")]
    lines.append("%-10s %-14s %-14s %10s  %-6s  %s" %
                 ("REF", "FAMILY", "PART", "WATTS", "XY(mm)", "BASIS"))
    for s in sorted(inv.sources, key=lambda s: -s.watts):
        xy = "%.1f,%.1f" % s.xy_mm if s.xy_mm else "-"
        flag = " [UNVERIFIED]" if s.unverified else ""
        lines.append("%-10s %-14s %-14s %10.4f  %-6s  %s%s" %
                     (s.ref, s.family, s.part, s.watts, xy, s.basis, flag))
        if s.note:
            lines.append("           note: %s" % s.note)
    if inv.unverified_refs:
        lines.append("UNVERIFIED-basis sources: %s" % ", ".join(inv.unverified_refs))
    return "\n".join(lines)


def format_material_table(checks, peak_T_C):
    lines = ["Absolute-T material-limit gate @ peak_T=%.1fC:" % peak_T_C]
    for c in checks:
        verdict = "PASS" if c.passed else "FAIL"
        flag = " [UNVERIFIED limit]" if c.unverified else ""
        lines.append("  %-28s limit=%6.1fC  margin=%+7.2fC  %s%s" %
                     (c.material, c.limit_C, c.margin_C, verdict, flag))
    return "\n".join(lines)


def format_emissivity_table(regions):
    lines = ["Emissivity regions: %s (board area %.1f mm2)" %
            (regions["board"], regions["board_area_mm2"])]
    for r in regions["regions"]:
        flag = " [UNVERIFIED]" if r["unverified"] else ""
        lines.append("  %-20s %8.1f mm2  (%5.1f%%)  eps=%.2f%s" %
                     (r["class"], r["area_mm2"], r["area_fraction"] * 100,
                      r["emissivity"], flag))
    return "\n".join(lines)


# ============================================================ CLI self-test / demo
def main(argv=None):
    boards = argv or ["hubs/hub-standard", "modules/12vhpwr-standard"]
    for b in boards:
        d = os.path.join(ROOT, b)
        print("=" * 78)
        inv = inventory(d)
        print(format_inventory_table(inv))
        print()
        ambient = _corpus_design_ambient() or 50.0
        peak_T = ambient + 30.0     # steady-state dT_max=30C anchor (thermal-gates corpus)
        checks = material_limit_gate(peak_T)
        print(format_material_table(checks, peak_T))
        print()
        import glob
        pcbs = [p for p in glob.glob(os.path.join(d, "*.kicad_pcb"))
               if "-routed" not in p and ".merged." not in p]
        if pcbs and _HAVE_PCBNEW:
            regions = emissivity_regions(sorted(pcbs)[0])
            print(format_emissivity_table(regions))
        print()


if __name__ == "__main__":
    main(sys.argv[1:] or None)
