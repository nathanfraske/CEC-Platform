#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ENT Hub schematic capture -- sheet 01 (power input) + the hierarchical
# scaffold (root + placeholder sheets 02-09), per hubs/hub-enterprise/
# SCHEMATIC-PLAN.md and docs/enterprise-requirements/spec-sheets/bom-detailed/
# bom-d-power.md. Reuses scripts/cec_sch.py's low-level symbol/wire/label
# helpers (pin geometry, wire routing, power-symbol embedding) but does NOT
# use its build_schematic() top-level driver, because that function assumes
# a FLAT single-sheet project (its own file IS the project root). This is a
# genuine two-level hierarchy: hub-enterprise.kicad_sch (root) instantiates
# 01-power-input.kicad_sch (+ 8 placeholder sheets) via real KiCad `sheet`
# symbols with hierarchical-label pins, so symbol `instances` paths and the
# child's own `sheet_instances` block must reference the ROOT's uuid + the
# sheet-symbol's uuid, not the child file's own identity.
#
# Run: python3 hubs/hub-enterprise/gen_hub_enterprise.py
# Validate: kicad-cli sch erc ... (see scripts/check_hub_ent_sch.py)
import os, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTDIR, "scripts"))
import cec_sch  # noqa: E402

PROJECT = "hub-enterprise"

# ---------------------------------------------------------------------------
# fixed identity uuids (stable across regenerations so the project doesn't
# re-annotate references every run). Generated once; do not reshuffle.
# ---------------------------------------------------------------------------
ROOT_UUID = "8f2a1c40-6e11-4b8a-9d3a-1a2b3c4d5e6f"
SHEET_UUIDS = {
    "01": "0a1b2c3d-4e5f-4061-8a2b-3c4d5e6f7081",
    "02": "0a1b2c3d-4e5f-4062-8a2b-3c4d5e6f7082",
    "03": "0a1b2c3d-4e5f-4063-8a2b-3c4d5e6f7083",
    "04": "0a1b2c3d-4e5f-4064-8a2b-3c4d5e6f7084",
    "05": "0a1b2c3d-4e5f-4065-8a2b-3c4d5e6f7085",
    "06": "0a1b2c3d-4e5f-4066-8a2b-3c4d5e6f7086",
    "07": "0a1b2c3d-4e5f-4067-8a2b-3c4d5e6f7087",
    "08": "0a1b2c3d-4e5f-4068-8a2b-3c4d5e6f7088",
    "09": "0a1b2c3d-4e5f-4069-8a2b-3c4d5e6f7089",
}
SHEET01_OWN_UUID = "1b2c3d4e-5f60-4171-9b2c-4d5e6f708192"  # 01-power-input.kicad_sch's own file identity

SHEET_TITLES = {
    "02": ("02-compute-core", "MPFS095Tx FCVG484 compute core (boot straps, JTAG, clock, decoupling)"),
    "03": ("03-compute-rails", "MIC22705YML-TR core buck + bank rails + sequencing/PG chain"),
    "04": ("04-storage", "W25Q256JV QSPI NOR + eMMC 5.1 (FW/tamper log/bulk storage)"),
    "05": ("05-module-ports", "8x RJ-45 FTP module ports, DETECT/pin-7, TJA1051T/3, ADS7830"),
    "06": ("06-t1-dataplane", "2x LAN9370 100BASE-T1 fabric switch"),
    "07": ("07-uplink", "DP83869HM GbE uplink PHY + magnetics/protection"),
    "08": ("08-secio-aux", "RJ-11 security I/O, NanoKVM aux, SK6812 chain, service button"),
    "09": ("09-watchdog", "S32K3xx supervisory watchdog (MC/MC-Max only)"),
}

# ---------------------------------------------------------------------------
# libraries
# ---------------------------------------------------------------------------
LIBS = {
    "cec":            open(f"{ROOTDIR}/lib/cec.kicad_sym").read(),
    "cec-vendor":      open(f"{ROOTDIR}/lib/vendor/cec-vendor.kicad_sym").read(),
    "power":           open(f"{ROOTDIR}/lib/vendor/cec-power.kicad_sym").read(),
    "cec-ent-power":   open(f"{ROOTDIR}/lib/cec-ent-power.kicad_sym").read(),
    "cec-ent-hub-local": open(f"{HERE}/lib-local.kicad_sym").read(),
}

# ===========================================================================
# SHEET 01 -- power input. Parts, per BOM-D refs namespaced U101../R101../
# C101../D101../L101/J101...
# ===========================================================================

PARTS = {}
NETS = {}
FOOTPRINTS = {}
PROPS = {}
PLACEMENT = {}
NC_SKIP = set()

def add_part(ref, lib, name, value, x, y, fp, props=None):
    PARTS[ref] = (lib, name, value)
    PLACEMENT[ref] = (x, y)
    FOOTPRINTS[ref] = fp
    if props:
        PROPS[ref] = props

def net(name, *conns):
    NETS.setdefault(name, [])
    for c in conns:
        NETS[name].append(c)

UR = "UNI-ROYAL"
SAM = "Samsung"
TI = "Texas Instruments"

# ---- MAIN_5V eFuse front (U101) -------------------------------------------
GX, GY = 20, 40
add_part("J101", "cec", "CEC_PWR_IN_2P", "CEC_PWR_IN_2P", GX, GY + 25,
          "cec-Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal",
          {"Manufacturer": "JST", "MPN": "S2B-XH-A(LF)(SN)", "LCSC": "C157931",
           "Description": "MAIN_5V power-in, 2-pin JST-XH -- reuse platform J_5V"})
add_part("R101", "cec-vendor", "R_Small", "45.3k", GX + 40, GY - 10,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4532TCE",
           "Description": "UVLO/OVLO divider top, MAIN_5V eFuse"})
add_part("R102", "cec-vendor", "R_Small", "2.80k", GX + 40, GY + 5,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2801TCE",
           "Description": "UVLO/OVLO divider mid, MAIN_5V eFuse"})
add_part("R103", "cec-vendor", "R_Small", "10k", GX + 40, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "UVLO/OVLO divider bottom, MAIN_5V eFuse"})
add_part("U101", "cec-ent-power", "TPS25940LRVCR", "TPS25940LRVCR", GX + 85, GY + 15,
          "cec-Package_DFN_QFN:WQFN-20_L4.0-W3.0-P0.50-BL-EP",
          {"Manufacturer": TI, "MPN": "TPS25940LRVCR", "LCSC": "C2867756",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps25940.pdf",
           "Description": "eFuse front, MAIN_5V, ILIM 24.9k->3.53A typ"})
add_part("R104", "cec-vendor", "R_Small", "24.9k", GX + 130, GY - 15,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2492TCE",
           "Description": "R_ILIM MAIN_5V -> 3.53A typ"})
add_part("C101", "cec-vendor", "C_Small", "10n", GX + 130, GY,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B103KB5NNNC", "LCSC": "C15195",
           "Description": "dVdT soft-start ramp cap, MAIN_5V eFuse"})
add_part("R105", "cec-vendor", "R_Small", "10k", GX + 130, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "PGOOD pull-up, MAIN_5V eFuse"})
add_part("R106", "cec-vendor", "R_Small", "10k", GX + 130, GY + 35,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "FLT pull-up, MAIN_5V eFuse"})
add_part("C102", "cec-vendor", "C_Small", "100n", GX, GY + 60,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B104KO5NNNC", "LCSC": "C1525",
           "Description": "input noise-suppression cap, MAIN_5V eFuse"})
add_part("C103", "cec-vendor", "C_Small", "1u", GX + 130, GY - 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A105KB8NNNC", "LCSC": "C15849",
           "Description": "local output bypass, MAIN_5V eFuse"})

net("+5V_MAIN", ("J101", "1"), ("R101", "1"), ("U101", "9"), ("U101", "10"),
    ("U101", "11"), ("U101", "12"), ("U101", "13"), ("C102", "1"))
net("GND", ("J101", "2"))
net("UVLO_MAIN", ("R101", "2"), ("R102", "1"), ("U101", "14"))
net("OVP_MAIN", ("R102", "2"), ("R103", "1"), ("U101", "15"))
net("GND", ("R103", "2"))
net("ILIM_MAIN", ("R104", "1"), ("U101", "17"))
net("GND", ("R104", "2"))
net("DVDT_MAIN", ("C101", "1"), ("U101", "18"))
net("GND", ("C101", "2"))
net("PG_MAIN", ("U101", "2"), ("R105", "1"))
net("+3V3", ("R105", "2"))
net("FLT_MAIN", ("U101", "20"), ("R106", "1"))
net("+3V3", ("R106", "2"))
net("GND", ("C102", "2"), ("U101", "16"), ("U101", "21"), ("U101", "1"))  # GND, EP, DEVSLP->GND
net("MAIN_EF_OUT", ("U101", "4"), ("U101", "5"), ("U101", "6"), ("U101", "7"),
    ("U101", "8"), ("U101", "3"), ("C103", "1"))  # OUT x5 + PGTH tied to OUT directly
net("GND", ("C103", "2"))

# ---- 5VSB eFuse front (U102) -----------------------------------------------
GX, GY = 200, 40
add_part("J102", "cec", "CEC_PWR_IN_2P", "CEC_PWR_IN_2P", GX, GY + 25,
          "cec-Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal",
          {"Manufacturer": "JST", "MPN": "S2B-XH-A(LF)(SN)", "LCSC": "C157931",
           "Description": "+5VSB power-in (24-pin module feed), 2-pin JST-XH -- reuse platform J_5VSB"})
add_part("R107", "cec-vendor", "R_Small", "45.3k", GX + 40, GY - 10,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4532TCE",
           "Description": "UVLO/OVLO divider top, 5VSB eFuse"})
add_part("R108", "cec-vendor", "R_Small", "2.80k", GX + 40, GY + 5,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2801TCE",
           "Description": "UVLO/OVLO divider mid, 5VSB eFuse"})
add_part("R109", "cec-vendor", "R_Small", "10k", GX + 40, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "UVLO/OVLO divider bottom, 5VSB eFuse"})
add_part("U102", "cec-ent-power", "TPS25940LRVCR", "TPS25940LRVCR", GX + 85, GY + 15,
          "cec-Package_DFN_QFN:WQFN-20_L4.0-W3.0-P0.50-BL-EP",
          {"Manufacturer": TI, "MPN": "TPS25940LRVCR", "LCSC": "C2867756",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps25940.pdf",
           "Description": "eFuse front, +5VSB, ILIM 42.2k->2.08A typ"})
add_part("R110", "cec-vendor", "R_Small", "42.2k", GX + 130, GY - 15,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4222TCE",
           "Description": "R_ILIM 5VSB -> 2.08A typ"})
add_part("C104", "cec-vendor", "C_Small", "10n", GX + 130, GY,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B103KB5NNNC", "LCSC": "C15195",
           "Description": "dVdT soft-start ramp cap, 5VSB eFuse"})
add_part("R111", "cec-vendor", "R_Small", "10k", GX + 130, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "PGOOD pull-up, 5VSB eFuse"})
add_part("R112", "cec-vendor", "R_Small", "10k", GX + 130, GY + 35,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "FLT pull-up, 5VSB eFuse"})
add_part("C105", "cec-vendor", "C_Small", "100n", GX, GY + 60,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B104KO5NNNC", "LCSC": "C1525",
           "Description": "input noise-suppression cap, 5VSB eFuse"})
add_part("C106", "cec-vendor", "C_Small", "1u", GX + 130, GY - 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A105KB8NNNC", "LCSC": "C15849",
           "Description": "local output bypass, 5VSB eFuse"})

net("+5VSB", ("J102", "1"), ("R107", "1"), ("U102", "9"), ("U102", "10"),
    ("U102", "11"), ("U102", "12"), ("U102", "13"), ("C105", "1"))
net("GND", ("J102", "2"))
net("UVLO_SVB", ("R107", "2"), ("R108", "1"), ("U102", "14"))
net("OVP_SVB", ("R108", "2"), ("R109", "1"), ("U102", "15"))
net("GND", ("R109", "2"))
net("ILIM_SVB", ("R110", "1"), ("U102", "17"))
net("GND", ("R110", "2"))
net("DVDT_SVB", ("C104", "1"), ("U102", "18"))
net("GND", ("C104", "2"))
net("PG_SVB", ("U102", "2"), ("R111", "1"))
net("+3V3", ("R111", "2"))
net("FLT_SVB", ("U102", "20"), ("R112", "1"))
net("+3V3", ("R112", "2"))
net("GND", ("C105", "2"), ("U102", "16"), ("U102", "21"), ("U102", "1"))
net("SVB_EF_OUT", ("U102", "4"), ("U102", "5"), ("U102", "6"), ("U102", "7"),
    ("U102", "8"), ("U102", "3"), ("C106", "1"))
net("GND", ("C106", "2"))

# ---- EXT eFuse front + TVS (U103) ------------------------------------------
GX, GY = 380, 40
add_part("J103", "cec-ent-hub-local", "PJ-002AH", "PJ-002AH", GX, GY + 25,
          "cec-ent-hub-local:PJ-002AH_THT_RA",
          {"Manufacturer": "Same Sky (CUI Devices)", "MPN": "PJ-002AH",
           "Datasheet": "https://www.sameskydevices.com/product/resource/pj-002ah.pdf",
           "Description": "EXT rear-bracket power-in, 5.5/2.1mm barrel jack "
                           "(BOM-D recommendation over a keyed JST -- 'any generic "
                           "5V adapter should work'; owner nod still open, see Open Items). "
                           "No LCSC C-number (DigiKey #408446 only), per BOM-D."})
add_part("D102", "cec-ent-hub-local", "SMAJ5.0A", "SMAJ5.0A", GX + 15, GY - 25,
          "cec-Diode_SMD:D_SMA_SMAJ58A_L4.4-W2.6-LS5.0",
          {"Manufacturer": "Littelfuse", "MPN": "SMAJ5.0A", "LCSC": "C83329",
           "Datasheet": "https://www.littelfuse.com/products/tvs-diodes/uni-directional/smaj/smaj5-0a",
           "Description": "EXT input TVS, populated on EXT only (mirrors DETECT-pin philosophy)"})
add_part("R113", "cec-vendor", "R_Small", "45.3k", GX + 45, GY - 10,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4532TCE",
           "Description": "UVLO/OVLO divider top, EXT eFuse"})
add_part("R114", "cec-vendor", "R_Small", "2.80k", GX + 45, GY + 5,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2801TCE",
           "Description": "UVLO/OVLO divider mid, EXT eFuse"})
add_part("R115", "cec-vendor", "R_Small", "10k", GX + 45, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "UVLO/OVLO divider bottom, EXT eFuse"})
add_part("U103", "cec-ent-power", "TPS25940LRVCR", "TPS25940LRVCR", GX + 90, GY + 15,
          "cec-Package_DFN_QFN:WQFN-20_L4.0-W3.0-P0.50-BL-EP",
          {"Manufacturer": TI, "MPN": "TPS25940LRVCR", "LCSC": "C2867756",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps25940.pdf",
           "Description": "eFuse front, EXT, ILIM 42.2k->2.08A typ"})
add_part("R116", "cec-vendor", "R_Small", "42.2k", GX + 135, GY - 15,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4222TCE",
           "Description": "R_ILIM EXT -> 2.08A typ"})
add_part("C107", "cec-vendor", "C_Small", "10n", GX + 135, GY,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B103KB5NNNC", "LCSC": "C15195",
           "Description": "dVdT soft-start ramp cap, EXT eFuse"})
add_part("R117", "cec-vendor", "R_Small", "10k", GX + 135, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "PGOOD pull-up, EXT eFuse"})
add_part("R118", "cec-vendor", "R_Small", "10k", GX + 135, GY + 35,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "FLT pull-up, EXT eFuse"})
add_part("C108", "cec-vendor", "C_Small", "100n", GX, GY + 60,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B104KO5NNNC", "LCSC": "C1525",
           "Description": "input noise-suppression cap, EXT eFuse"})
add_part("C109", "cec-vendor", "C_Small", "1u", GX + 135, GY - 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A105KB8NNNC", "LCSC": "C15849",
           "Description": "local output bypass, EXT eFuse"})

net("EXT_5V", ("J103", "1"), ("D102", "2"), ("R113", "1"), ("U103", "9"),
    ("U103", "10"), ("U103", "11"), ("U103", "12"), ("U103", "13"), ("C108", "1"))
net("GND", ("J103", "2"), ("D102", "1"))
net("UVLO_EXT", ("R113", "2"), ("R114", "1"), ("U103", "14"))
net("OVP_EXT", ("R114", "2"), ("R115", "1"), ("U103", "15"))
net("GND", ("R115", "2"))
net("ILIM_EXT", ("R116", "1"), ("U103", "17"))
net("GND", ("R116", "2"))
net("DVDT_EXT", ("C107", "1"), ("U103", "18"))
net("GND", ("C107", "2"))
net("PG_EXT", ("U103", "2"), ("R117", "1"))
net("+3V3", ("R117", "2"))
net("FLT_EXT", ("U103", "20"), ("R118", "1"))
net("+3V3", ("R118", "2"))
net("GND", ("C108", "2"), ("U103", "16"), ("U103", "21"), ("U103", "1"))
net("EXT_EF_OUT", ("U103", "4"), ("U103", "5"), ("U103", "6"), ("U103", "7"),
    ("U103", "8"), ("U103", "3"), ("C109", "1"))
net("GND", ("C109", "2"))

# ---- Priority cascade (U104=stage A, U105=stage B) -------------------------
# Pin ties per hub-standard's AS-BUILT netlist (verified via netlist export,
# 2026-07-02): PR1->IN1 and OV1/OV2->GND match BOM-D's own recommendation, but
# CP2 is tied to IN2 (NOT GND) on the real shipping board -- BOM-D explicitly
# flagged its own CP2->GND tie as unverified ("I could not fully re-derive the
# exact wired nets from the raw .kicad_sch"). This generator follows the
# PROVEN as-built wiring (CP2->IN2) rather than BOM-D's independently-reasoned
# but unverified recommendation; see the final report for the full comparison.
GX, GY = 540, 60
add_part("U104", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR", GX, GY,
          "cec-Package_DFN_QFN:RUX0012A",
          {"Manufacturer": TI, "MPN": "TPS2121RUXR", "LCSC": "C485916",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps2121.pdf",
           "Description": "Priority cascade stage A -- ORs 5VSB(priority) vs EXT "
                           "= existing hub-standard U5 role"})
add_part("U105", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR", GX + 100, GY,
          "cec-Package_DFN_QFN:RUX0012A",
          {"Manufacturer": TI, "MPN": "TPS2121RUXR", "LCSC": "C485916",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps2121.pdf",
           "Description": "Priority cascade stage B -- ORs MAIN_5V(priority) vs "
                           "stage-A output = existing hub-standard U7 role"})
add_part("R119", "cec-vendor", "R_Small", "27k", GX - 40, GY + 45,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2702TCE", "LCSC": "C25771",
           "Description": "ILM set, cascade stage A (existing platform value)"})
add_part("C110", "cec-vendor", "C_Small", "2.2u", GX - 40, GY + 60,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A225KO8NNNC", "LCSC": "C23630",
           "Description": "soft-start cap, cascade stage A (flag: 0 stock at LCSC "
                           "at time of BOM-D check)"})
add_part("R120", "cec-vendor", "R_Small", "27k", GX + 140, GY + 45,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2702TCE", "LCSC": "C25771",
           "Description": "ILM set, cascade stage B (existing platform value)"})
add_part("C111", "cec-vendor", "C_Small", "2.2u", GX + 140, GY + 60,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A225KO8NNNC", "LCSC": "C23630",
           "Description": "soft-start cap, cascade stage B"})

net("SVB_EF_OUT", ("U104", "6"), ("U104", "7"))       # PR1->IN1 (priority = 5VSB)
net("EXT_EF_OUT", ("U104", "2"), ("U104", "3"))       # IN2=EXT, CP2->IN2 (as-built pattern)
net("GND", ("U104", "4"), ("U104", "5"), ("U104", "12"))  # OV2, OV1, GND
net("STAGE_A_OUT", ("U104", "1"), ("U104", "8"))
net("ILM_PC1", ("R119", "1"), ("U104", "10"))
net("GND", ("R119", "2"))
net("SS_PC1", ("C110", "1"), ("U104", "11"))
net("GND", ("C110", "2"))

net("MAIN_EF_OUT", ("U105", "6"), ("U105", "7"))      # PR1->IN1 (priority = MAIN_5V)
net("STAGE_A_OUT", ("U105", "2"), ("U105", "3"))      # IN2=stage-A OUT, CP2->IN2
net("GND", ("U105", "4"), ("U105", "5"), ("U105", "12"))
net("+5V_SYS", ("U105", "1"), ("U105", "8"))
net("ILM_PC2", ("R120", "1"), ("U105", "10"))
net("GND", ("R120", "2"))
net("SS_PC2", ("C111", "1"), ("U105", "11"))
net("GND", ("C111", "2"))

# ---- Hold-up reservoir ------------------------------------------------------
GX, GY = 540, 170
add_part("D101", "cec-vendor", "SB120", "SS14", GX + 30, GY,
          "cec-Diode_SMD:D_SMA",
          {"Manufacturer": "MDD", "MPN": "SS14", "LCSC": "C2480",
           "Datasheet": "https://www.vishay.com/docs/88746/ss12.pdf",
           "Description": "Reservoir back-feed isolation Schottky -- exact platform D1. "
                           "lib_id is the generic SB120 2-pin diode graphic (SS14 is an "
                           "`extends`-only library entry with no pins of its own); Value/"
                           "Footprint overridden to the real SS14/SMA part, matching the "
                           "exact convention hub-standard's own D1 instance uses."})
add_part("C112", "cec-vendor", "C_Small", "4700u", GX, GY + 30,
          "cec-Capacitor_SMD:CP_Elec_16x17.5",
          {"Manufacturer": "Samxon", "MPN": "VKMI2101C472MV", "LCSC": "C487318",
           "Description": "Persist-on-fault hold-up 1 of 2 -- exact part on shipping Hub Standard"})
add_part("C113", "cec-vendor", "C_Small", "4700u", GX + 35, GY + 30,
          "cec-Capacitor_SMD:CP_Elec_16x17.5",
          {"Manufacturer": "Samxon", "MPN": "VKMI2101C472MV", "LCSC": "C487318",
           "Description": "Persist-on-fault hold-up 2 of 2"})
add_part("C114", "cec-vendor", "C_Small", "470u", GX + 70, GY + 30,
          "cec-Capacitor_SMD:CP_Elec_6.3x7.7",
          {"Manufacturer": "Lelon", "MPN": "RVT1A471M0607", "LCSC": "C335982",
           "Description": "Bulk cap, fast-transient support -- exact platform C_bulk1"})

net("+5V_SYS", ("D101", "2"))    # anode side (input)
net("+5V_HOLD", ("D101", "1"), ("C112", "1"), ("C113", "1"), ("C114", "1"))
net("GND", ("C112", "2"), ("C113", "2"), ("C114", "2"))

# ---- 3V3 hub-logic buck + supervisor ---------------------------------------
GX, GY = 700, 60
add_part("U106", "cec-ent-hub-local", "TLV62569DBVR", "TLV62569DBVR", GX + 35, GY + 30,
          "cec-Package_TO_SOT_SMD:SOT-23-5",
          {"Manufacturer": TI, "MPN": "TLV62569DBVR", "LCSC": "C141836",
           "Description": "3.3V synchronous buck, hub-logic-rail (CAN xcvr / LED "
                           "chain / DETECT / aux domain)"})
add_part("L101", "cec-ent-hub-local", "L_Small", "L_VLS252010HBX-2R2M-1", GX + 65, GY + 30,
          "cec-ent-hub-local:L_VLS252010HBX-2R2M-1",
          {"Manufacturer": "TDK", "MPN": "VLS252010HBX-2R2M-1", "LCSC": "C88527",
           "Description": "2.2uH shielded power inductor, buck logic-rail"})
add_part("C115", "cec-vendor", "C_Small", "10u", GX, GY + 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A106MA8NRNC", "LCSC": "C96446",
           "Description": "buck input cap"})
add_part("C116", "cec-vendor", "C_Small", "10u", GX + 100, GY + 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A106MA8NRNC", "LCSC": "C96446",
           "Description": "buck output cap"})
add_part("R121", "cec-vendor", "R_Small", "453k", GX + 65, GY + 60,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4533TCE",
           "Description": "FB divider top (VOUT node) -- sets VOUT~=3.32V"})
add_part("R122", "cec-vendor", "R_Small", "100k", GX + 65, GY + 75,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1003TCE", "LCSC": "C25741",
           "Description": "FB divider bottom (to GND)"})
add_part("U107", "cec-vendor", "TPS3839DBZ", "TPS3839K33", GX + 130, GY + 30,
          "cec-Package_TO_SOT_SMD:SOT-23",
          {"Manufacturer": TI, "MPN": "TPS3839K33DBZR", "LCSC": "C96333",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps3839.pdf",
           "Description": "hub-logic +3V3 rail supervisor -- new instance of the "
                           "existing platform part; does NOT supervise the PolarFire "
                           "SoC's own core/I/O rails (subsystem A's own sequencing)"})

net("+5V_SYS", ("C115", "1"), ("U106", "4"), ("U106", "1"))  # VIN + EN tied to VIN (always-on; no BOM line given for EN, inferred)
net("GND", ("C115", "2"), ("U106", "2"))
net("SW_BK", ("U106", "3"), ("L101", "1"))
net("+3V3", ("L101", "2"), ("C116", "1"), ("R121", "1"), ("U107", "3"))
net("GND", ("C116", "2"))
net("FB_BK", ("U106", "5"), ("R121", "2"), ("R122", "1"))
net("GND", ("R122", "2"))
net("GND", ("U107", "1"))
net("RESET_3V3", ("U107", "2"))

# ---- Rail-sense dividers (4x: raw MAIN/SVB/EXT + post-cascade +5V_SYS) -----
GX, GY = 20, 260
add_part("R123", "cec-vendor", "R_Small", "47k", GX, GY,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4702TCE", "LCSC": "C25792",
           "Description": "rail-sense divider top, MAIN_5V raw"})
add_part("R124", "cec-vendor", "R_Small", "10k", GX, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "rail-sense divider bottom, MAIN_5V raw"})
add_part("R125", "cec-vendor", "R_Small", "47k", GX + 140, GY,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4702TCE", "LCSC": "C25792",
           "Description": "rail-sense divider top, 5VSB raw"})
add_part("R126", "cec-vendor", "R_Small", "10k", GX + 140, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "rail-sense divider bottom, 5VSB raw"})
add_part("R127", "cec-vendor", "R_Small", "47k", GX + 280, GY,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4702TCE", "LCSC": "C25792",
           "Description": "rail-sense divider top, EXT raw"})
add_part("R128", "cec-vendor", "R_Small", "10k", GX + 280, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "rail-sense divider bottom, EXT raw"})
add_part("R129", "cec-vendor", "R_Small", "47k", GX + 420, GY,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4702TCE", "LCSC": "C25792",
           "Description": "rail-sense divider top, +5V_SYS (merged system rail)"})
add_part("R130", "cec-vendor", "R_Small", "10k", GX + 420, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "rail-sense divider bottom, +5V_SYS"})

net("+5V_MAIN", ("R123", "1"))
net("SENSE_MAIN", ("R123", "2"), ("R124", "1"))
net("GND", ("R124", "2"))
net("+5VSB", ("R125", "1"))
net("SENSE_SVB", ("R125", "2"), ("R126", "1"))
net("GND", ("R126", "2"))
net("EXT_5V", ("R127", "1"))
net("SENSE_EXT", ("R127", "2"), ("R128", "1"))
net("GND", ("R128", "2"))
net("+5V_SYS", ("R129", "1"))
net("SENSE_SYS", ("R129", "2"), ("R130", "1"))
net("GND", ("R130", "2"))

# ---------------------------------------------------------------------------
# hierarchical exports at the sheet-01 boundary. Every one is "output" shape
# (sheet01 is the power SOURCE stage -- nothing on this sheet consumes a
# signal from elsewhere yet). anchor = ONE (ref,pin) already in that net's
# connection list, which gets a hierarchical_label instead of its normal
# label/power-port treatment; every OTHER connection on the same net keeps
# its normal treatment (both merge by name match within the sheet).
# ---------------------------------------------------------------------------
HIER_EXPORTS = {
    "+5V_MAIN":  ("output", ("R123", "1")),
    "+5VSB":     ("output", ("R125", "1")),
    "EXT_5V":    ("output", ("R127", "1")),
    "+5V_SYS":   ("output", ("R129", "1")),
    "+3V3":      ("output", ("R121", "1")),
    "PG_MAIN":   ("output", ("R105", "1")),
    "FLT_MAIN":  ("output", ("R106", "1")),
    "PG_SVB":    ("output", ("R111", "1")),
    "FLT_SVB":   ("output", ("R112", "1")),
    "PG_EXT":    ("output", ("R117", "1")),
    "FLT_EXT":   ("output", ("R118", "1")),
    "SENSE_MAIN": ("output", ("R124", "1")),
    "SENSE_SVB":  ("output", ("R126", "1")),
    "SENSE_EXT":  ("output", ("R128", "1")),
    "SENSE_SYS":  ("output", ("R130", "1")),
}

POWER_PORTS = {"GND": "GND", "+3V3": "+3V3", "+5VSB": "+5VSB",
               "+5V_MAIN": "+5V_MAIN", "+5V_SYS": "+5V_SYS"}
POWERFLAG_NETS = ["GND", "+3V3", "+5VSB", "+5V_MAIN", "EXT_5V", "+5V_SYS", "STAGE_A_OUT"]

SECTIONS = {
    "MAIN_5V EFUSE FRONT (U_EF1)":  (10, 5, 175, 110),
    "5VSB EFUSE FRONT (U_EF2)":     (190, 5, 355, 110),
    "EXT EFUSE FRONT + TVS (U_EF3)": (370, 5, 545, 110),
    "PRIORITY CASCADE (TPS2121 x2, U_PC1/U_PC2)": (490, 45, 690, 145),
    "HOLD-UP RESERVOIR (+5V_HOLD)": (500, 155, 640, 210),
    "3V3 HUB-LOGIC BUCK + SUPERVISOR": (680, 45, 850, 145),
    "RAIL-SENSE DIVIDERS (raw MAIN/SVB/EXT + merged +5V_SYS)": (10, 245, 490, 300),
}

if __name__ == "__main__":
    from build_lib import build_root, build_sheet01, build_placeholder

    stats = build_sheet01(
        PARTS, NETS, FOOTPRINTS, PROPS, PLACEMENT, NC_SKIP,
        POWER_PORTS, POWERFLAG_NETS, HIER_EXPORTS, SECTIONS,
        LIBS, PROJECT, ROOT_UUID, SHEET_UUIDS["01"], SHEET01_OWN_UUID,
        page="2", out_path=f"{HERE}/01-power-input.kicad_sch", paper="A0")
    print("01-power-input.kicad_sch  " + "  ".join(f"{k}={v}" for k, v in stats.items()))

    placeholder_uuids = {n: SHEET_UUIDS[n] for n in SHEET_TITLES}
    build_root(HIER_EXPORTS, PROJECT, ROOT_UUID, SHEET_UUIDS["01"],
               placeholder_uuids, SHEET_TITLES,
               out_path=f"{HERE}/hub-enterprise.kicad_sch", paper="A3")
    print("hub-enterprise.kicad_sch  sheets=1(real)+8(placeholder)")

    for num, (name, desc) in SHEET_TITLES.items():
        page = 3 + list(sorted(SHEET_TITLES)).index(num)
        build_placeholder(num, SHEET_UUIDS[num], name, desc, PROJECT, page,
                           out_path=f"{HERE}/{name}.kicad_sch", paper="A4")
    print("Generated 8 placeholder sheets: " + ", ".join(SHEET_TITLES[n][0] for n in sorted(SHEET_TITLES)))
