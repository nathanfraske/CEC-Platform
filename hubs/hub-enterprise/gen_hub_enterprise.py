#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ENT Hub schematic capture -- sheet 01 (power input) + the hierarchical
# scaffold (root + placeholder sheets 02-09), per hubs/hub-enterprise/
# SCHEMATIC-PLAN.md and docs/enterprise-requirements/spec-sheets/bom-detailed/
# bom-d-power.md.
#
# FORMAT CORRECTION (owner, 2026-07-02): sheet 01 is captured as a genuine
# THREE-level hierarchy -- root -> 01-power-input.kicad_sch (a THIN PARENT:
# sheet symbols only, no components, no dashed frames) -> seven LEAF sheets
# (01a-efuse-main, 01b-efuse-5vsb, 01c-efuse-ext, 01d-cascade, 01e-holdup,
# 01f-buck-3v3, 01g-rail-sense), each one functional block, on its own file,
# with a proper title. This supersedes the prior single flat 01-power-input
# capture that grouped those same seven blocks as dashed-frame SECTIONS on
# one sheet ("weird sub-sheets", per the owner) -- same parts, same nets, same
# wiring; only the sheet boundaries moved. See build_lib.py's module docstring
# for the addressing rules this relies on (component instance-path chains,
# sheet_instances path chains, hierarchical-label/sheet-pin name matching).
#
# Reuses scripts/cec_sch.py's low-level symbol/wire/label helpers (pin
# geometry, wire routing, power-symbol embedding) but does NOT use its
# build_schematic() top-level driver (assumes a flat single-sheet project).
#
# Run: python3 hubs/hub-enterprise/gen_hub_enterprise.py
# Validate: kicad-cli sch erc ... (see scripts/check_hub_ent_sch.py)
import os, sys, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTDIR, "scripts"))
import cec_sch  # noqa: E402
import cec_sch_layout  # noqa: E402  -- the T1 engine (nudge_texts finishing pass)
import cec_sch_compose  # noqa: E402  -- the shared composition engine (T4)
import cec_sch_archetypes as arch  # noqa: E402  -- T4 block templates

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
SHEET01_OWN_UUID = "1b2c3d4e-5f60-4171-9b2c-4d5e6f708192"  # 01-power-input.kicad_sch's own file identity (thin parent)

# 01a-01g: sheet-symbol uuid (as placed IN the 01-power-input parent) + this
# leaf file's own top-level identity uuid. Both fixed/stable, per the same
# convention as SHEET_UUIDS/SHEET01_OWN_UUID above.
LEAF_SYM_UUIDS = {
    "01a": "1a2b3c4d-5e6f-40a1-9b1a-2c3d4e5f60a1",
    "01b": "1a2b3c4d-5e6f-40a2-9b1a-2c3d4e5f60a2",
    "01c": "1a2b3c4d-5e6f-40a3-9b1a-2c3d4e5f60a3",
    "01d": "1a2b3c4d-5e6f-40a4-9b1a-2c3d4e5f60a4",
    "01e": "1a2b3c4d-5e6f-40a5-9b1a-2c3d4e5f60a5",
    "01f": "1a2b3c4d-5e6f-40a6-9b1a-2c3d4e5f60a6",
    "01g": "1a2b3c4d-5e6f-40a7-9b1a-2c3d4e5f60a7",
}
LEAF_OWN_UUIDS = {
    "01a": "2b3c4d5e-6f70-41a1-8c2b-3d4e5f6071a1",
    "01b": "2b3c4d5e-6f70-41a2-8c2b-3d4e5f6071a2",
    "01c": "2b3c4d5e-6f70-41a3-8c2b-3d4e5f6071a3",
    "01d": "2b3c4d5e-6f70-41a4-8c2b-3d4e5f6071a4",
    "01e": "2b3c4d5e-6f70-41a5-8c2b-3d4e5f6071a5",
    "01f": "2b3c4d5e-6f70-41a6-8c2b-3d4e5f6071a6",
    "01g": "2b3c4d5e-6f70-41a7-8c2b-3d4e5f6071a7",
}

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

UR = "UNI-ROYAL"
SAM = "Samsung"
TI = "Texas Instruments"

POWER_PORTS = {"GND": "GND", "+3V3": "+3V3", "+5VSB": "+5VSB",
               "+5V_MAIN": "+5V_MAIN", "+5V_SYS": "+5V_SYS"}

# ===========================================================================
# a "Leaf" is one functional-block sheet (01a..01g): its own parts/nets.
# (data holder promoted to cec_sch_compose 2026-07-03; identical class)
# ===========================================================================
Leaf = cec_sch_compose.Leaf


LEAVES = {}


def leaf(id_, filename, sheetname, desc):
    lf = Leaf(id_, filename, sheetname, desc)
    LEAVES[id_] = lf
    return lf


L01A = leaf("01a", "01a-efuse-main.kicad_sch", "01a-efuse-main",
            "MAIN_5V eFuse front (TPS25940, ILIM 24.9k -> 3.53A typ)")
L01B = leaf("01b", "01b-efuse-5vsb.kicad_sch", "01b-efuse-5vsb",
            "+5VSB eFuse front (TPS25940, ILIM 42.2k -> 2.08A typ)")
L01C = leaf("01c", "01c-efuse-ext.kicad_sch", "01c-efuse-ext",
            "EXT eFuse front + TVS (TPS25940, ILIM 42.2k -> 2.08A typ, SMAJ5.0A + PJ-002AH)")
L01D = leaf("01d", "01d-cascade.kicad_sch", "01d-cascade",
            "Priority cascade (2x TPS2121): 5VSB>EXT stage A, MAIN_5V>stage-A-out stage B")
L01E = leaf("01e", "01e-holdup.kicad_sch", "01e-holdup",
            "Hold-up reservoir: 2x 4700uF + 470uF bulk, isolation Schottky")
L01F = leaf("01f", "01f-buck-3v3.kicad_sch", "01f-buck-3v3",
            "TLV62569 3.3V hub-logic buck + FB divider + TPS3839K33 supervisor")
L01G = leaf("01g", "01g-rail-sense.kicad_sch", "01g-rail-sense",
            "4x 47k/10k rail-sense dividers: raw MAIN/SVB/EXT + merged +5V_SYS")

# ---------------------------------------------------------------------------
# 01a -- MAIN_5V eFuse front (U101)
# ---------------------------------------------------------------------------
GX, GY = 20, 40
L01A.add_part("J101", "cec", "CEC_PWR_IN_2P", "CEC_PWR_IN_2P", GX, GY + 25,
          "cec-Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal",
          {"Manufacturer": "JST", "MPN": "S2B-XH-A(LF)(SN)", "LCSC": "C157931",
           "Description": "MAIN_5V power-in, 2-pin JST-XH -- reuse platform J_5V"})
L01A.add_part("R101", "cec-vendor", "R_Small", "45.3k", GX + 40, GY - 10,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4532TCE",
           "Description": "UVLO/OVLO divider top, MAIN_5V eFuse"})
L01A.add_part("R102", "cec-vendor", "R_Small", "2.80k", GX + 40, GY + 5,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2801TCE",
           "Description": "UVLO/OVLO divider mid, MAIN_5V eFuse"})
L01A.add_part("R103", "cec-vendor", "R_Small", "10k", GX + 40, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "UVLO/OVLO divider bottom, MAIN_5V eFuse"})
L01A.add_part("U101", "cec-ent-power", "TPS25940LRVCR", "TPS25940LRVCR", GX + 85, GY + 15,
          "cec-Package_DFN_QFN:WQFN-20_L4.0-W3.0-P0.50-BL-EP",
          {"Manufacturer": TI, "MPN": "TPS25940LRVCR", "LCSC": "C2867756",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps25940.pdf",
           "Description": "eFuse front, MAIN_5V, ILIM 24.9k->3.53A typ"})
L01A.add_part("R104", "cec-vendor", "R_Small", "24.9k", GX + 130, GY - 15,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2492TCE",
           "Description": "R_ILIM MAIN_5V -> 3.53A typ"})
L01A.add_part("C101", "cec-vendor", "C_Small", "10n", GX + 130, GY,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B103KB5NNNC", "LCSC": "C15195",
           "Description": "dVdT soft-start ramp cap, MAIN_5V eFuse"})
L01A.add_part("R105", "cec-vendor", "R_Small", "10k", GX + 130, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "PGOOD pull-up, MAIN_5V eFuse"})
L01A.add_part("R106", "cec-vendor", "R_Small", "10k", GX + 130, GY + 35,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "FLT pull-up, MAIN_5V eFuse"})
L01A.add_part("C102", "cec-vendor", "C_Small", "100n", GX, GY + 60,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B104KO5NNNC", "LCSC": "C1525",
           "Description": "input noise-suppression cap, MAIN_5V eFuse"})
L01A.add_part("C103", "cec-vendor", "C_Small", "1u", GX + 130, GY - 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A105KB8NNNC", "LCSC": "C15849",
           "Description": "local output bypass, MAIN_5V eFuse"})

L01A.net("+5V_MAIN", ("J101", "1"), ("R101", "1"), ("U101", "9"), ("U101", "10"),
    ("U101", "11"), ("U101", "12"), ("U101", "13"), ("C102", "1"))
L01A.net("GND", ("J101", "2"))
L01A.net("UVLO_MAIN", ("R101", "2"), ("R102", "1"), ("U101", "14"))
L01A.net("OVP_MAIN", ("R102", "2"), ("R103", "1"), ("U101", "15"))
L01A.net("GND", ("R103", "2"))
L01A.net("ILIM_MAIN", ("R104", "1"), ("U101", "17"))
L01A.net("GND", ("R104", "2"))
L01A.net("DVDT_MAIN", ("C101", "1"), ("U101", "18"))
L01A.net("GND", ("C101", "2"))
L01A.net("PG_MAIN", ("U101", "2"), ("R105", "1"))
L01A.net("+3V3", ("R105", "2"))
L01A.net("FLT_MAIN", ("U101", "20"), ("R106", "1"))
L01A.net("+3V3", ("R106", "2"))
L01A.net("GND", ("C102", "2"), ("U101", "16"), ("U101", "21"), ("U101", "1"))  # GND, EP, DEVSLP->GND
L01A.net("MAIN_EF_OUT", ("U101", "4"), ("U101", "5"), ("U101", "6"), ("U101", "7"),
    ("U101", "8"), ("U101", "3"), ("C103", "1"))  # OUT x5 + PGTH tied to OUT directly
L01A.net("GND", ("C103", "2"))

L01A.hier_exports = {
    "PG_MAIN":     ("output", ("R105", "1")),
    "FLT_MAIN":    ("output", ("R106", "1")),
    "MAIN_EF_OUT": ("output", ("U101", "4")),
}
L01A.powerflag_nets = ["GND", "+5V_MAIN"]

# ---------------------------------------------------------------------------
# 01b -- 5VSB eFuse front (U102)
# ---------------------------------------------------------------------------
GX, GY = 20, 40
L01B.add_part("J102", "cec", "CEC_PWR_IN_2P", "CEC_PWR_IN_2P", GX, GY + 25,
          "cec-Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal",
          {"Manufacturer": "JST", "MPN": "S2B-XH-A(LF)(SN)", "LCSC": "C157931",
           "Description": "+5VSB power-in (24-pin module feed), 2-pin JST-XH -- reuse platform J_5VSB"})
L01B.add_part("R107", "cec-vendor", "R_Small", "45.3k", GX + 40, GY - 10,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4532TCE",
           "Description": "UVLO/OVLO divider top, 5VSB eFuse"})
L01B.add_part("R108", "cec-vendor", "R_Small", "2.80k", GX + 40, GY + 5,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2801TCE",
           "Description": "UVLO/OVLO divider mid, 5VSB eFuse"})
L01B.add_part("R109", "cec-vendor", "R_Small", "10k", GX + 40, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "UVLO/OVLO divider bottom, 5VSB eFuse"})
L01B.add_part("U102", "cec-ent-power", "TPS25940LRVCR", "TPS25940LRVCR", GX + 85, GY + 15,
          "cec-Package_DFN_QFN:WQFN-20_L4.0-W3.0-P0.50-BL-EP",
          {"Manufacturer": TI, "MPN": "TPS25940LRVCR", "LCSC": "C2867756",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps25940.pdf",
           "Description": "eFuse front, +5VSB, ILIM 42.2k->2.08A typ"})
L01B.add_part("R110", "cec-vendor", "R_Small", "42.2k", GX + 130, GY - 15,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4222TCE",
           "Description": "R_ILIM 5VSB -> 2.08A typ"})
L01B.add_part("C104", "cec-vendor", "C_Small", "10n", GX + 130, GY,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B103KB5NNNC", "LCSC": "C15195",
           "Description": "dVdT soft-start ramp cap, 5VSB eFuse"})
L01B.add_part("R111", "cec-vendor", "R_Small", "10k", GX + 130, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "PGOOD pull-up, 5VSB eFuse"})
L01B.add_part("R112", "cec-vendor", "R_Small", "10k", GX + 130, GY + 35,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "FLT pull-up, 5VSB eFuse"})
L01B.add_part("C105", "cec-vendor", "C_Small", "100n", GX, GY + 60,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B104KO5NNNC", "LCSC": "C1525",
           "Description": "input noise-suppression cap, 5VSB eFuse"})
L01B.add_part("C106", "cec-vendor", "C_Small", "1u", GX + 130, GY - 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A105KB8NNNC", "LCSC": "C15849",
           "Description": "local output bypass, 5VSB eFuse"})

L01B.net("+5VSB", ("J102", "1"), ("R107", "1"), ("U102", "9"), ("U102", "10"),
    ("U102", "11"), ("U102", "12"), ("U102", "13"), ("C105", "1"))
L01B.net("GND", ("J102", "2"))
L01B.net("UVLO_SVB", ("R107", "2"), ("R108", "1"), ("U102", "14"))
L01B.net("OVP_SVB", ("R108", "2"), ("R109", "1"), ("U102", "15"))
L01B.net("GND", ("R109", "2"))
L01B.net("ILIM_SVB", ("R110", "1"), ("U102", "17"))
L01B.net("GND", ("R110", "2"))
L01B.net("DVDT_SVB", ("C104", "1"), ("U102", "18"))
L01B.net("GND", ("C104", "2"))
L01B.net("PG_SVB", ("U102", "2"), ("R111", "1"))
L01B.net("+3V3", ("R111", "2"))
L01B.net("FLT_SVB", ("U102", "20"), ("R112", "1"))
L01B.net("+3V3", ("R112", "2"))
L01B.net("GND", ("C105", "2"), ("U102", "16"), ("U102", "21"), ("U102", "1"))
L01B.net("SVB_EF_OUT", ("U102", "4"), ("U102", "5"), ("U102", "6"), ("U102", "7"),
    ("U102", "8"), ("U102", "3"), ("C106", "1"))
L01B.net("GND", ("C106", "2"))

L01B.hier_exports = {
    "PG_SVB":     ("output", ("R111", "1")),
    "FLT_SVB":    ("output", ("R112", "1")),
    "SVB_EF_OUT": ("output", ("U102", "4")),
}
L01B.powerflag_nets = ["+5VSB"]

# ---------------------------------------------------------------------------
# 01c -- EXT eFuse front + TVS (U103)
# ---------------------------------------------------------------------------
GX, GY = 20, 40
L01C.add_part("J103", "cec-ent-hub-local", "PJ-002AH", "PJ-002AH", GX, GY + 25,
          "cec-ent-hub-local:PJ-002AH_THT_RA",
          {"Manufacturer": "Same Sky (CUI Devices)", "MPN": "PJ-002AH",
           "Datasheet": "https://www.sameskydevices.com/product/resource/pj-002ah.pdf",
           "Description": "EXT rear-bracket power-in, 5.5/2.1mm barrel jack "
                           "(BOM-D recommendation over a keyed JST -- 'any generic "
                           "5V adapter should work'; owner nod still open, see Open Items). "
                           "No LCSC C-number (DigiKey #408446 only), per BOM-D."})
L01C.add_part("D102", "cec-ent-hub-local", "SMAJ5.0A", "SMAJ5.0A", GX + 15, GY - 25,
          "cec-Diode_SMD:D_SMA_SMAJ58A_L4.4-W2.6-LS5.0",
          {"Manufacturer": "Littelfuse", "MPN": "SMAJ5.0A", "LCSC": "C83329",
           "Datasheet": "https://www.littelfuse.com/products/tvs-diodes/uni-directional/smaj/smaj5-0a",
           "Description": "EXT input TVS, populated on EXT only (mirrors DETECT-pin philosophy)"})
L01C.add_part("R113", "cec-vendor", "R_Small", "45.3k", GX + 45, GY - 10,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4532TCE",
           "Description": "UVLO/OVLO divider top, EXT eFuse"})
L01C.add_part("R114", "cec-vendor", "R_Small", "2.80k", GX + 45, GY + 5,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2801TCE",
           "Description": "UVLO/OVLO divider mid, EXT eFuse"})
L01C.add_part("R115", "cec-vendor", "R_Small", "10k", GX + 45, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "UVLO/OVLO divider bottom, EXT eFuse"})
L01C.add_part("U103", "cec-ent-power", "TPS25940LRVCR", "TPS25940LRVCR", GX + 90, GY + 15,
          "cec-Package_DFN_QFN:WQFN-20_L4.0-W3.0-P0.50-BL-EP",
          {"Manufacturer": TI, "MPN": "TPS25940LRVCR", "LCSC": "C2867756",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps25940.pdf",
           "Description": "eFuse front, EXT, ILIM 42.2k->2.08A typ"})
L01C.add_part("R116", "cec-vendor", "R_Small", "42.2k", GX + 135, GY - 15,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4222TCE",
           "Description": "R_ILIM EXT -> 2.08A typ"})
L01C.add_part("C107", "cec-vendor", "C_Small", "10n", GX + 135, GY,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B103KB5NNNC", "LCSC": "C15195",
           "Description": "dVdT soft-start ramp cap, EXT eFuse"})
L01C.add_part("R117", "cec-vendor", "R_Small", "10k", GX + 135, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "PGOOD pull-up, EXT eFuse"})
L01C.add_part("R118", "cec-vendor", "R_Small", "10k", GX + 135, GY + 35,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "FLT pull-up, EXT eFuse"})
L01C.add_part("C108", "cec-vendor", "C_Small", "100n", GX, GY + 60,
          "cec-Capacitor_SMD:C_0402_1005Metric",
          {"Manufacturer": SAM, "MPN": "CL05B104KO5NNNC", "LCSC": "C1525",
           "Description": "input noise-suppression cap, EXT eFuse"})
L01C.add_part("C109", "cec-vendor", "C_Small", "1u", GX + 135, GY - 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A105KB8NNNC", "LCSC": "C15849",
           "Description": "local output bypass, EXT eFuse"})

L01C.net("EXT_5V", ("J103", "1"), ("D102", "2"), ("R113", "1"), ("U103", "9"),
    ("U103", "10"), ("U103", "11"), ("U103", "12"), ("U103", "13"), ("C108", "1"))
L01C.net("GND", ("J103", "2"), ("D102", "1"))
L01C.net("UVLO_EXT", ("R113", "2"), ("R114", "1"), ("U103", "14"))
L01C.net("OVP_EXT", ("R114", "2"), ("R115", "1"), ("U103", "15"))
L01C.net("GND", ("R115", "2"))
L01C.net("ILIM_EXT", ("R116", "1"), ("U103", "17"))
L01C.net("GND", ("R116", "2"))
L01C.net("DVDT_EXT", ("C107", "1"), ("U103", "18"))
L01C.net("GND", ("C107", "2"))
L01C.net("PG_EXT", ("U103", "2"), ("R117", "1"))
L01C.net("+3V3", ("R117", "2"))
L01C.net("FLT_EXT", ("U103", "20"), ("R118", "1"))
L01C.net("+3V3", ("R118", "2"))
L01C.net("GND", ("C108", "2"), ("U103", "16"), ("U103", "21"), ("U103", "1"))
L01C.net("EXT_EF_OUT", ("U103", "4"), ("U103", "5"), ("U103", "6"), ("U103", "7"),
    ("U103", "8"), ("U103", "3"), ("C109", "1"))
L01C.net("GND", ("C109", "2"))

L01C.hier_exports = {
    "PG_EXT":     ("output", ("R117", "1")),
    "FLT_EXT":    ("output", ("R118", "1")),
    "EXT_EF_OUT": ("output", ("U103", "4")),
    "EXT_5V":     ("output", ("J103", "1")),
}
L01C.powerflag_nets = ["EXT_5V"]

# ---------------------------------------------------------------------------
# 01d -- Priority cascade (U104=stage A, U105=stage B)
# ---------------------------------------------------------------------------
# Pin ties per hub-standard's AS-BUILT netlist (verified via netlist export,
# 2026-07-02): PR1->IN1 and OV1/OV2->GND match BOM-D's own recommendation, but
# CP2 is tied to IN2 (NOT GND) on the real shipping board -- BOM-D explicitly
# flagged its own CP2->GND tie as unverified ("I could not fully re-derive the
# exact wired nets from the raw .kicad_sch"). This generator follows the
# PROVEN as-built wiring (CP2->IN2) rather than BOM-D's independently-reasoned
# but unverified recommendation; see the final report for the full comparison.
GX, GY = 20, 40
L01D.add_part("U104", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR", GX, GY,
          "cec-Package_DFN_QFN:RUX0012A",
          {"Manufacturer": TI, "MPN": "TPS2121RUXR", "LCSC": "C485916",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps2121.pdf",
           "Description": "Priority cascade stage A -- ORs 5VSB(priority) vs EXT "
                           "= existing hub-standard U5 role"})
L01D.add_part("U105", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR", GX + 100, GY,
          "cec-Package_DFN_QFN:RUX0012A",
          {"Manufacturer": TI, "MPN": "TPS2121RUXR", "LCSC": "C485916",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps2121.pdf",
           "Description": "Priority cascade stage B -- ORs MAIN_5V(priority) vs "
                           "stage-A output = existing hub-standard U7 role"})
L01D.add_part("R119", "cec-vendor", "R_Small", "27k", GX - 40, GY + 45,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2702TCE", "LCSC": "C25771",
           "Description": "ILM set, cascade stage A (existing platform value)"})
L01D.add_part("C110", "cec-vendor", "C_Small", "2.2u", GX - 40, GY + 60,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A225KO8NNNC", "LCSC": "C23630",
           "Description": "soft-start cap, cascade stage A (flag: 0 stock at LCSC "
                           "at time of BOM-D check)"})
L01D.add_part("R120", "cec-vendor", "R_Small", "27k", GX + 140, GY + 45,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF2702TCE", "LCSC": "C25771",
           "Description": "ILM set, cascade stage B (existing platform value)"})
L01D.add_part("C111", "cec-vendor", "C_Small", "2.2u", GX + 140, GY + 60,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A225KO8NNNC", "LCSC": "C23630",
           "Description": "soft-start cap, cascade stage B"})

L01D.net("SVB_EF_OUT", ("U104", "6"), ("U104", "7"))       # PR1->IN1 (priority = 5VSB)
L01D.net("EXT_EF_OUT", ("U104", "2"), ("U104", "3"))       # IN2=EXT, CP2->IN2 (as-built pattern)
L01D.net("GND", ("U104", "4"), ("U104", "5"), ("U104", "12"))  # OV2, OV1, GND
L01D.net("STAGE_A_OUT", ("U104", "1"), ("U104", "8"))
L01D.net("ILM_PC1", ("R119", "1"), ("U104", "10"))
L01D.net("GND", ("R119", "2"))
L01D.net("SS_PC1", ("C110", "1"), ("U104", "11"))
L01D.net("GND", ("C110", "2"))

L01D.net("MAIN_EF_OUT", ("U105", "6"), ("U105", "7"))      # PR1->IN1 (priority = MAIN_5V)
L01D.net("STAGE_A_OUT", ("U105", "2"), ("U105", "3"))      # IN2=stage-A OUT, CP2->IN2
L01D.net("GND", ("U105", "4"), ("U105", "5"), ("U105", "12"))
L01D.net("+5V_SYS", ("U105", "1"), ("U105", "8"))
L01D.net("ILM_PC2", ("R120", "1"), ("U105", "10"))
L01D.net("GND", ("R120", "2"))
L01D.net("SS_PC2", ("C111", "1"), ("U105", "11"))
L01D.net("GND", ("C111", "2"))

L01D.hier_exports = {
    # inputs FROM 01a/01b/01c (both ends of each hop use "output" shape, per
    # this project's established, ERC-verified convention -- see build_lib.py
    # module docstring)
    "SVB_EF_OUT":  ("output", ("U104", "6")),
    "EXT_EF_OUT":  ("output", ("U104", "2")),
    "MAIN_EF_OUT": ("output", ("U105", "6")),
}
L01D.powerflag_nets = ["+5V_SYS", "STAGE_A_OUT"]

# ---------------------------------------------------------------------------
# 01e -- Hold-up reservoir
# ---------------------------------------------------------------------------
GX, GY = 20, 40
L01E.add_part("D101", "cec-vendor", "SB120", "SS14", GX + 30, GY,
          "cec-Diode_SMD:D_SMA",
          {"Manufacturer": "MDD", "MPN": "SS14", "LCSC": "C2480",
           "Datasheet": "https://www.vishay.com/docs/88746/ss12.pdf",
           "Description": "Reservoir back-feed isolation Schottky -- exact platform D1. "
                           "lib_id is the generic SB120 2-pin diode graphic (SS14 is an "
                           "`extends`-only library entry with no pins of its own); Value/"
                           "Footprint overridden to the real SS14/SMA part, matching the "
                           "exact convention hub-standard's own D1 instance uses."})
L01E.add_part("C112", "cec-vendor", "C_Small", "4700u", GX, GY + 30,
          "cec-Capacitor_SMD:CP_Elec_16x17.5",
          {"Manufacturer": "Samxon", "MPN": "VKMI2101C472MV", "LCSC": "C487318",
           "Description": "Persist-on-fault hold-up 1 of 2 -- exact part on shipping Hub Standard"})
L01E.add_part("C113", "cec-vendor", "C_Small", "4700u", GX + 35, GY + 30,
          "cec-Capacitor_SMD:CP_Elec_16x17.5",
          {"Manufacturer": "Samxon", "MPN": "VKMI2101C472MV", "LCSC": "C487318",
           "Description": "Persist-on-fault hold-up 2 of 2"})
L01E.add_part("C114", "cec-vendor", "C_Small", "470u", GX + 70, GY + 30,
          "cec-Capacitor_SMD:CP_Elec_6.3x7.7",
          {"Manufacturer": "Lelon", "MPN": "RVT1A471M0607", "LCSC": "C335982",
           "Description": "Bulk cap, fast-transient support -- exact platform C_bulk1"})

L01E.net("+5V_SYS", ("D101", "2"))    # anode side (input)
L01E.net("+5V_HOLD", ("D101", "1"), ("C112", "1"), ("C113", "1"), ("C114", "1"))
L01E.net("GND", ("C112", "2"), ("C113", "2"), ("C114", "2"))

# no hier_exports: +5V_HOLD is fully local; +5V_SYS is a global power symbol
# consumed here with no anchor (the anchor lives in 01g).

# ---------------------------------------------------------------------------
# 01f -- 3V3 hub-logic buck + supervisor
# ---------------------------------------------------------------------------
GX, GY = 20, 40
L01F.add_part("U106", "cec-ent-hub-local", "TLV62569DBVR", "TLV62569DBVR", GX + 35, GY + 30,
          "cec-Package_TO_SOT_SMD:SOT-23-5",
          {"Manufacturer": TI, "MPN": "TLV62569DBVR", "LCSC": "C141836",
           "Description": "3.3V synchronous buck, hub-logic-rail (CAN xcvr / LED "
                           "chain / DETECT / aux domain)"})
L01F.add_part("L101", "cec-ent-hub-local", "L_Small", "L_VLS252010HBX-2R2M-1", GX + 65, GY + 30,
          "cec-ent-hub-local:L_VLS252010HBX-2R2M-1",
          {"Manufacturer": "TDK", "MPN": "VLS252010HBX-2R2M-1", "LCSC": "C88527",
           "Description": "2.2uH shielded power inductor, buck logic-rail"})
L01F.add_part("C115", "cec-vendor", "C_Small", "10u", GX, GY + 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A106MA8NRNC", "LCSC": "C96446",
           "Description": "buck input cap"})
L01F.add_part("C116", "cec-vendor", "C_Small", "10u", GX + 100, GY + 30,
          "cec-Capacitor_SMD:C_0603_1608Metric",
          {"Manufacturer": SAM, "MPN": "CL10A106MA8NRNC", "LCSC": "C96446",
           "Description": "buck output cap"})
L01F.add_part("R121", "cec-vendor", "R_Small", "453k", GX + 65, GY + 60,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4533TCE",
           "Description": "FB divider top (VOUT node) -- sets VOUT~=3.32V"})
L01F.add_part("R122", "cec-vendor", "R_Small", "100k", GX + 65, GY + 75,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1003TCE", "LCSC": "C25741",
           "Description": "FB divider bottom (to GND)"})
L01F.add_part("U107", "cec-vendor", "TPS3839DBZ", "TPS3839K33", GX + 130, GY + 30,
          "cec-Package_TO_SOT_SMD:SOT-23",
          {"Manufacturer": TI, "MPN": "TPS3839K33DBZR", "LCSC": "C96333",
           "Datasheet": "https://www.ti.com/lit/ds/symlink/tps3839.pdf",
           "Description": "hub-logic +3V3 rail supervisor -- new instance of the "
                           "existing platform part; does NOT supervise the PolarFire "
                           "SoC's own core/I/O rails (subsystem A's own sequencing)"})

L01F.net("+5V_SYS", ("C115", "1"), ("U106", "4"), ("U106", "1"))  # VIN + EN tied to VIN (always-on; no BOM line given for EN, inferred)
L01F.net("GND", ("C115", "2"), ("U106", "2"))
L01F.net("SW_BK", ("U106", "3"), ("L101", "1"))
L01F.net("+3V3", ("L101", "2"), ("C116", "1"), ("R121", "1"), ("U107", "3"))
L01F.net("GND", ("C116", "2"))
L01F.net("FB_BK", ("U106", "5"), ("R121", "2"), ("R122", "1"))
L01F.net("GND", ("R122", "2"))
L01F.net("GND", ("U107", "1"))
L01F.net("RESET_3V3", ("U107", "2"))

L01F.hier_exports = {
    "+3V3": ("output", ("R121", "1")),
}
L01F.powerflag_nets = ["+3V3"]

# ---------------------------------------------------------------------------
# 01g -- Rail-sense dividers (4x: raw MAIN/SVB/EXT + post-cascade +5V_SYS)
# ---------------------------------------------------------------------------
GX, GY = 20, 40
L01G.add_part("R123", "cec-vendor", "R_Small", "47k", GX, GY,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4702TCE", "LCSC": "C25792",
           "Description": "rail-sense divider top, MAIN_5V raw"})
L01G.add_part("R124", "cec-vendor", "R_Small", "10k", GX, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "rail-sense divider bottom, MAIN_5V raw"})
L01G.add_part("R125", "cec-vendor", "R_Small", "47k", GX + 140, GY,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4702TCE", "LCSC": "C25792",
           "Description": "rail-sense divider top, 5VSB raw"})
L01G.add_part("R126", "cec-vendor", "R_Small", "10k", GX + 140, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "rail-sense divider bottom, 5VSB raw"})
L01G.add_part("R127", "cec-vendor", "R_Small", "47k", GX + 280, GY,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4702TCE", "LCSC": "C25792",
           "Description": "rail-sense divider top, EXT raw"})
L01G.add_part("R128", "cec-vendor", "R_Small", "10k", GX + 280, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "rail-sense divider bottom, EXT raw"})
L01G.add_part("R129", "cec-vendor", "R_Small", "47k", GX + 420, GY,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF4702TCE", "LCSC": "C25792",
           "Description": "rail-sense divider top, +5V_SYS (merged system rail)"})
L01G.add_part("R130", "cec-vendor", "R_Small", "10k", GX + 420, GY + 20,
          "cec-Resistor_SMD:R_0402_1005Metric",
          {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
           "Description": "rail-sense divider bottom, +5V_SYS"})

L01G.net("+5V_MAIN", ("R123", "1"))
L01G.net("SENSE_MAIN", ("R123", "2"), ("R124", "1"))
L01G.net("GND", ("R124", "2"))
L01G.net("+5VSB", ("R125", "1"))
L01G.net("SENSE_SVB", ("R125", "2"), ("R126", "1"))
L01G.net("GND", ("R126", "2"))
L01G.net("EXT_5V", ("R127", "1"))
L01G.net("SENSE_EXT", ("R127", "2"), ("R128", "1"))
L01G.net("GND", ("R128", "2"))
L01G.net("+5V_SYS", ("R129", "1"))
L01G.net("SENSE_SYS", ("R129", "2"), ("R130", "1"))
L01G.net("GND", ("R130", "2"))

L01G.hier_exports = {
    # +5V_MAIN / +5VSB / +5V_SYS are NOT anchored here (see GLOBAL_POWER_EXPORTS
    # below): they are real KiCad global power nets (POWER_PORTS), so R123/
    # R125/R129 just use the ordinary global power symbol like every other
    # leaf's own copy of that rail -- no sheet-pin/hierarchical-label plumbing
    # needed or wanted for them. Forcing one, as the pre-restructure flat
    # sheet's single-file "anchor" convention did, does NOT merge with the
    # OTHER leaves' global-symbol copies once split across files: global power
    # symbols and hierarchical labels are different, non-interoperating KiCad
    # mechanisms (verified empirically against a real reference project).
    "EXT_5V":     ("output", ("R127", "1")),
    "SENSE_MAIN": ("output", ("R124", "1")),
    "SENSE_SVB":  ("output", ("R126", "1")),
    "SENSE_EXT":  ("output", ("R128", "1")),
    "SENSE_SYS":  ("output", ("R130", "1")),
}

# ===========================================================================
# COMPOSED LAYOUTS (T1 integration, 2026-07-03 -- the owner's "center them,
# make them not ugly spread out, attach the decouplers with real wires"
# correction). Coordinates are designed in 1.27mm GRID UNITS (u) so every
# wire endpoint, pin, and junction lands exactly on the schematic grid; the
# leaf builder then centers the whole composition on the page. Connectivity
# for every wire below is the SAME net the label-aliased version carried --
# proven by scripts/check_hub_ent_sch.py's 59-component/46-group equivalence
# guard plus a flattened-netlist node-set diff (see the charter, principle 1).
# Pin math is cec_sch_layout.pin_abs_rot (rotation round-trip verified).
# ===========================================================================
U = cec_sch.GRID  # 1.27mm


class _Compose(cec_sch_compose.Compose):
    """The shared grid-unit composition collector (promoted to
    cec_sch_compose 2026-07-03), bound to this generator's LIBS."""

    def __init__(self, lf):
        super().__init__(lf, LIBS)


def compose_efuse(lf, J, Rt, Rm, Rb, Uef, Ril, Cdv, Rpg, Rflt, Cin, Cout,
                  rail, sfx, out_net, pg_net, flt_net, tvs=None,
                  ilim_desc=""):
    """Shared composition for the three structurally identical eFuse leaves
    (01a/01b/01c), REBUILT 2026-07-03 to the composition standard (S1/S2/S3;
    the owner's Nuand TPS2115A reference shape): the raw rail is ONE
    horizontal band across the top (connector -> stamp -> [TVS] -> input cap
    -> UVLO/OVLO divider -> IN riser), the widened TPS25940 sits BELOW the
    band, strap parts (ILIM/dVdT) hang down-right, PG/FLT pull-ups exit right
    at pin-row height, and all three exports gather in the S1 right-edge io
    column. `rail` = global power-port name or None for 01c's EXT_5V."""
    c = _Compose(lf)
    c.place(Uef, 80, 84)
    # ---- top band, y=64: J.1 -> stamp/label -> [tvs] -> Cin tap -> divider
    # tap -> IN riser at x65
    if tvs:
        # PJ-002AH's SLEEVE (GND) pin exits its RIGHT side at the same local
        # row as TIP -- placing TIP directly on the band put SLEEVE ON the
        # band's copper (measured 2026-07-03: KiCad CONNECTS a pin sitting
        # under a wire INTERIOR; ERC multiple_net_names GND<->EXT_5V). Seat
        # the jack one row lower and jog up into the band instead.
        c.place_pin(J, "1", 24, 66)
        c.wire((24, 66), (26, 66), (26, 64))
        splits = [(26, 64), (28, 64), (36, 64), (40, 64)]
        c.place(tvs, 36, 67, 90)          # rail pin (2) lands at (36,64)
        c.use((tvs, "2"))
    else:
        c.place_pin(J, "1", 24, 64)
        splits = [(24, 64), (28, 64)]
    splits += [(48, 64), (56, 64), (65, 64)]
    for a, b in zip(splits, splits[1:]):
        c.wire(a, b)
    if rail:
        c.stamp(rail, 28, 64, 0)
    else:
        # EXT_5V: named local rail (label placed CLEAR of the widened jack
        # body) + its hierarchical export routed to the top-left, columnar
        # with nothing else on that edge
        c.label("EXT_5V", 40, 64, 0)
        c.wire((28, 64), (28, 60), (24, 60))
        c.hier("EXT_5V", 24, 60, 180)
    c.use((J, "1"))
    # input cap on the band
    c.place(Cin, 48, 68)
    c.wire((48, 64), (48, 66))
    c.use((Cin, "1"))
    # UVLO/OVLO divider chain hanging from the band (3 resistors, 2 taps;
    # Rt's pin 1 sits DIRECTLY on the band split point). Tap rows 70/76 keep
    # the ang-180 tap labels clear of the PGTH/EN/OVP stub-label rows 80-84.
    c.place(Rt, 56, 66); c.place(Rm, 56, 72); c.place(Rb, 56, 78)
    c.text_side[Rt] = c.text_side[Rm] = c.text_side[Rb] = "left"
    c.wire(c.pin(Rt, "2"), (56, 70), c.pin(Rm, "1"))
    c.label(f"UVLO_{sfx}", 56, 70, 180)
    c.wire(c.pin(Rm, "2"), (56, 76), c.pin(Rb, "1"))
    c.label(f"OVP_{sfx}", 56, 76, 180)
    c.use((Rt, "1"), (Rt, "2"), (Rm, "1"), (Rm, "2"), (Rb, "1"))
    # IN riser + IN pin bus (5 pins, x=69, y=86..94)
    c.wire((65, 64), (65, 86), (69, 86))
    for yy in range(86, 94, 2):
        c.wire((69, yy), (69, yy + 2))
    c.use(*[(Uef, str(p)) for p in (9, 10, 11, 12, 13)])
    # DEVSLP (pin 1, y=78) tied to GND, stamped clear above-left
    c.wire((69, 78), (67, 78), (67, 74))
    c.stamp("GND", 67, 74, 180)
    c.use((Uef, "1"))
    # ---- bottom: GND (16) + EP (21) tied, one stamp
    c.wire((77, 104), (77, 106), (80, 106))
    c.wire((83, 104), (83, 106), (80, 106))
    c.wire((80, 106), (80, 108))
    c.stamp("GND", 80, 108, 0)
    c.use((Uef, "16"), (Uef, "21"))
    # ---- right side: OUT bus -> out rail (+cap) -> io; PG/FLT pull-ups; ILIM/
    # dVdT strap hangs
    for yy in range(80, 88, 2):
        c.wire((91, yy), (91, yy + 2))
    c.place(Cout, 95, 84)
    c.wire((91, 80), (95, 80), (99, 80))
    c.wire((95, 80), (95, 82))
    c.use((Cout, "1"), *[(Uef, str(p)) for p in (4, 5, 6, 7, 8)])
    c.io(out_net, "right", from_pt=(99, 80))
    # PGOOD pull-up (pin 2, y=76)
    c.use((Uef, "2"))
    arch.pullup_hang(c, (91, 76), 107, Rpg, rx=105, rail_pin="1", above=True)
    c.io(pg_net, "right", from_pt=(107, 76))
    # ILIM (pin 17, y=90): keeps its NAME via the label (the checker asserts
    # ILIM_MAIN/ILIM_SVB/ILIM_EXT by name)
    c.place(Ril, 97, 100)
    c.wire((91, 90), (93, 90))
    c.label(f"ILIM_{sfx}", 93, 90, 0)
    c.wire((93, 90), (97, 90), (97, 98))
    c.use((Uef, "17"), (Ril, "1"))
    # dVdT (pin 18, y=92); crossings over the ILIM riser are mid-segment
    c.place(Cdv, 101, 100)
    c.text_side[Cdv] = "left"
    c.wire((91, 92), (101, 92), (101, 98))
    c.use((Uef, "18"), (Cdv, "1"))
    # FLT pull-up (pin 20, y=96) exits right at pin-row height
    c.use((Uef, "20"))
    arch.pullup_hang(c, (91, 96), 107, Rflt, rx=105, rail_pin="1", above=True)
    c.io(flt_net, "right", from_pt=(107, 96))
    # ---- captions + notes (S3/S10: strings from the existing desc/BOM-D)
    c.caption(lf.desc, 22, 52)
    c.note("UVLO/OVLO divider 45.3k/2.80k/10k -> 4.49V UV / 5.75V OV; "
           + (ilim_desc or "ILIM per BOM-D") + " (bom-d-power.md)", 22, 112)
    return c


def compose_01a():
    c = compose_efuse(L01A, "J101", "R101", "R102", "R103", "U101", "R104",
                      "C101", "R105", "R106", "C102", "C103",
                      "+5V_MAIN", "MAIN", "MAIN_EF_OUT", "PG_MAIN", "FLT_MAIN",
                      ilim_desc="ILIM 24.9k -> 3.53A typ")
    c.done()


def compose_01b():
    c = compose_efuse(L01B, "J102", "R107", "R108", "R109", "U102", "R110",
                      "C104", "R111", "R112", "C105", "C106",
                      "+5VSB", "SVB", "SVB_EF_OUT", "PG_SVB", "FLT_SVB",
                      ilim_desc="ILIM 42.2k -> 2.08A typ")
    c.done()


def compose_01c():
    c = compose_efuse(L01C, "J103", "R113", "R114", "R115", "U103", "R116",
                      "C107", "R117", "R118", "C108", "C109",
                      None, "EXT", "EXT_EF_OUT", "PG_EXT", "FLT_EXT",
                      tvs="D102", ilim_desc="ILIM 42.2k -> 2.08A typ")
    c.note("SMAJ5.0A input TVS populated on EXT only (mirrors the DETECT-pin "
           "philosophy); PJ-002AH barrel jack per BOM-D", 22, 116)
    c.done()


def compose_01d():
    lf = L01D
    c = _Compose(lf)
    c.place("U104", 52, 80); c.place("U105", 100, 80)
    c.place("R119", 68, 92); c.place("C110", 72, 88)
    c.place("R120", 116, 92); c.place("C111", 120, 88)
    c.text_side["R119"] = c.text_side["R120"] = "left"

    # stage A inputs: drawn pin buses + hier labels at the bus ends
    c.wire(c.pin("U104", "7"), (34, 64))
    c.wire(c.pin("U104", "6"), (34, 74))
    c.wire((34, 64), (34, 74))
    c.hier("SVB_EF_OUT", 34, 64, 180)
    c.wire(c.pin("U104", "3"), (34, 82))
    c.wire(c.pin("U104", "2"), (34, 86))
    c.wire((34, 82), (34, 86))
    c.hier("EXT_EF_OUT", 34, 86, 180)
    c.use(("U104", "6"), ("U104", "7"), ("U104", "2"), ("U104", "3"))

    # stage A OUT -> stage B IN2/CP2: the cascade chain, drawn
    c.wire(c.pin("U104", "1"), (76, 64))
    c.wire(c.pin("U104", "8"), (76, 66))
    c.wire((76, 64), (76, 66), (76, 90), (82, 90), (82, 86), (82, 82))
    c.wire(c.pin("U105", "3"), (82, 82))
    c.wire(c.pin("U105", "2"), (82, 86))
    c.label("STAGE_A_OUT", 76, 64, 0)
    c.use(("U104", "1"), ("U104", "8"), ("U105", "2"), ("U105", "3"))

    # stage B priority input bus; its hier label joins the LEFT column at
    # x=34 (S1: one scannable edge column -- MAIN 58 / SVB 64 / EXT 86),
    # routed above both ICs (their bodies start at y~64)
    c.wire(c.pin("U105", "7"), (82, 64))
    c.wire(c.pin("U105", "6"), (82, 74))
    c.wire((82, 64), (82, 74))
    c.wire((82, 64), (82, 58), (34, 58))
    c.hier("MAIN_EF_OUT", 34, 58, 180)
    c.use(("U105", "6"), ("U105", "7"))
    c.caption(lf.desc, 20, 48)
    c.note("PR1->IN1 + CP2->IN2 per the AS-BUILT hub-standard netlist "
           "(BOM-D's CP2->GND was flagged unverified by its own author)", 20, 114)

    # merged system rail out
    c.wire(c.pin("U105", "1"), (118, 64))
    c.wire(c.pin("U105", "8"), (118, 66))
    c.wire((118, 64), (118, 66))
    c.wire((118, 64), (118, 60))
    c.stamp("+5V_SYS", 118, 60, 0)
    c.use(("U105", "1"), ("U105", "8"))

    # per-stage ILM resistor + soft-start cap wired to their pins, with a
    # shared drawn GND return per stage (ILM bottom + SS bottom + the GND
    # pin 12 join one short rail with a single stamp -- keeps the parts clear
    # of pin 12's own graphic, which the first cut of this layout sat on)
    for Ua, Rilm, Css, x0 in (("U104", "R119", "C110", 66),
                               ("U105", "R120", "C111", 114)):
        rl, cl = x0 + 2, x0 + 6          # R lane, C lane
        c.wire(c.pin(Ua, "11"), (cl, 84), c.pin(Css, "1"))
        c.wire(c.pin(Ua, "10"), (rl, 88), c.pin(Rilm, "1"))
        c.wire(c.pin(Rilm, "2"), (rl, 96), (rl, 98))       # split at pin-12 tap
        c.wire(c.pin(Ua, "12"), (rl, 96))
        c.wire(c.pin(Css, "2"), (cl, 98))
        c.wire((rl, 98), (cl, 98), (cl + 4, 98))
        c.stamp("GND", cl + 4, 98, 0)
        c.use((Ua, "11"), (Css, "1"), (Ua, "10"), (Rilm, "1"),
              (Ua, "12"), (Rilm, "2"), (Css, "2"))
    c.done()


def compose_01e():
    lf = L01E
    c = _Compose(lf)
    c.place("D101", 56, 84, 180)     # input left (pin 2 = +5V_SYS), out right
    # initial cap positions = where place_decouplers will put them (the rail
    # runs through the T1 engine's place_decouplers/wire_decouplers pair, so
    # the caps are ATTACHED: one drawn rail off D101's cathode, GND stubs)
    c.place("C112", 71, 78); c.place("C113", 83, 78); c.place("C114", 95, 78)
    # decoupler-cluster archetype (shared Compose.rail wrapping the T1
    # place_decouplers/wire_decouplers pair) -- consumes D101.1 + cap pins
    c.rail("D101", "1", ["C112", "C113", "C114"], pitch=15.24)
    c.wire((95, 73), (99, 73))       # rail extension carrying the net name
    c.label("+5V_HOLD", 99, 73, 0)
    c.caption(lf.desc, 40, 60)
    c.done()


def compose_01f():
    lf = L01F
    c = _Compose(lf)
    c.place("U106", 72, 80)
    c.place("C115", 56, 84)
    c.place("L101", 86, 78, 90)
    c.place("C116", 89, 82)
    c.text_side["C116"] = "left"
    c.place("R121", 95, 84); c.place("R122", 95, 94)
    c.place("U107", 106, 84)

    # VIN entry: EN strapped to VIN, input cap wired onto the entry node
    c.wire(c.pin("U106", "1"), (60, 78), (60, 82), c.pin("U106", "4"))
    c.wire((60, 82), c.pin("C115", "1"))
    c.wire((60, 78), (60, 74))
    c.stamp("+5V_SYS", 60, 74, 0)
    c.use(("U106", "1"), ("U106", "4"), ("C115", "1"))

    # SW node: buck -> inductor, direct
    c.wire(c.pin("U106", "3"), c.pin("L101", "1"))
    c.use(("U106", "3"), ("L101", "1"))

    # +3V3 output rail: inductor -> caps/divider/supervisor, one drawn rail
    c.wire(c.pin("L101", "2"), (89, 78), (95, 78), (98, 78),
           c.pin("U107", "3"), (110, 78))
    c.wire((89, 78), c.pin("C116", "1"))
    c.wire((95, 78), c.pin("R121", "1"))
    c.wire((98, 78), (98, 74))
    c.stamp("+3V3", 98, 74, 0)
    c.io("+3V3", "right", from_pt=(110, 78))
    c.use(("L101", "2"), ("C116", "1"), ("R121", "1"), ("U107", "3"))
    c.caption(lf.desc, 48, 62)
    c.note("FB divider 453k/100k -> VOUT ~3.32V; TPS3839K33 supervises the "
           "hub-logic +3V3 only (not the SoC rails)", 48, 104)

    # FB divider: drawn chain + FB sense run back to the buck
    c.wire(c.pin("R121", "2"), c.pin("R122", "1"))
    c.wire(c.pin("U106", "5"), (82, 82), (82, 92), c.pin("R122", "1"))
    c.use(("R121", "2"), ("R122", "1"), ("U106", "5"))
    c.done()


def compose_01g():
    lf = L01G
    cols = [("R123", "R124", "+5V_MAIN", "SENSE_MAIN", 48),
            ("R125", "R126", "+5VSB", "SENSE_SVB", 68),
            ("R127", "R128", None, "SENSE_EXT", 88),
            ("R129", "R130", "+5V_SYS", "SENSE_SYS", 108)]
    c = _Compose(lf)
    for rt, rb, rail, sense, x in cols:
        c.place(rt, x, 68); c.place(rb, x, 76)
        c.wire((x, 64), c.pin(rt, "1"))
        if rail:
            c.stamp(rail, x, 64, 0)
        else:
            c.hier("EXT_5V", x, 64, 0)     # EXT_5V: hier export at the top
        c.wire(c.pin(rt, "2"), (x, 72), c.pin(rb, "1"))
        c.wire((x, 72), (x + 4, 72))
        c.hier(sense, x + 4, 72, 0)
        c.use((rt, "1"), (rt, "2"), (rb, "1"))
    # S4 note: the four cells stamp on one fixed pitch with the tap at the
    # SAME relative position -- a uniform repeated-cell grid; the SENSE taps
    # deliberately stay per-cell (each cell scans identically) rather than
    # fanning into one edge column across the row.
    c.caption(lf.desc, 44, 58)
    c.done()


for _fn in (compose_01a, compose_01b, compose_01c, compose_01d,
            compose_01e, compose_01f, compose_01g):
    _fn()


# ===========================================================================
# 05 -- module ports: thin parent -> 8x 05a-port{n} + 05b-can-frontend +
# 05c-detect-adc, per SCHEMATIC-PLAN.md sheet 05.
#
# INSTANCE MECHANISM (flagged per the task brief): the SCHEMATIC-PLAN.md
# "repeated-sheet" ideal is ONE 05a-port.kicad_sch file instantiated 8x (a
# single leaf FILE, eight distinct sheet-symbol placements). That needs, per
# instance: its own `sheet_instances` (path,page) entry in the shared file's
# footer AND its own `instances.path` entry on every component inside it
# (KiCad's real repeated-sheet annotation model). Neither `build_leaf` (one
# `sheet_instances_path`/`page` per call, one `instances.path` per component)
# nor `build_thin_parent` (one `(sheet ...)` box per `leaves` entry, but every
# box may point at a DIFFERENT file) support multi-instance-of-one-file
# today -- extending that shared, multi-board machinery for this one
# repeated-sheet case is out of scope here. This generator therefore takes
# the documented fallback: 8 GENERATED LEAF FILES from one template function
# (`compose_port`), each with its own refs -- exactly the platform's existing
# per-instance ref-class convention (J_PORT1..8, R_DET1..8, D_DET1..8 etc.,
# per bom-c-module-if-base-secio.md Sec1 and hub-ent-bom-detailed.md Sec6a).
#
# CAN BUS FAN-OUT (also flagged): CAN_H/CAN_L are a genuine N-way bus shared
# by all 8 port leaves PLUS 05b-can-frontend's transceiver -- 9 sheet-pin
# occurrences of the SAME net, which `build_thin_parent`'s 1:1/2-endpoint
# sheet-pin fan-out cannot express (it raises on >2 occurrences by design;
# see its own docstring). Resolved with a new shared-engine primitive: a real
# KiCad `global_label` at every occurrence (`cec_sch.emit_global_label` +
# `cec_sch_compose.build_leaf`'s new `global_nets` param) -- project-wide
# connectivity by name, exactly like a power symbol, with NO sheet-pin
# plumbing at all. T1 pairs / pin-7 SYNC / CAN_TX/RX / DETECT_SDA/SCL are
# each single-occurrence-per-leaf at this thin parent (a port's own T1 pair
# only appears once here; the far end is sheet 06, not yet captured) or a
# clean 2-endpoint pair (DETECT_A: one port leaf + 05c), so those DO fit the
# existing sheet-pin mechanism unchanged and climb to the ROOT as exports
# (mirroring sheet 01's own pattern of exporting to a not-yet-consuming box).
# ===========================================================================
SHEET05_LEAF_IDS = [f"05a{n}" for n in range(1, 9)] + ["05b", "05c"]


def _stable_uuid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"cec-hub-enterprise-{name}"))


SHEET05_LEAF_SYM_UUIDS = {lid: _stable_uuid(f"05-leaf-sym-{lid}") for lid in SHEET05_LEAF_IDS}
SHEET05_LEAF_OWN_UUIDS = {lid: _stable_uuid(f"05-leaf-own-{lid}") for lid in SHEET05_LEAF_IDS}
SHEET05_OWN_UUID = _stable_uuid("05-module-ports-thin-parent")

SHEET05_LEAVES = {}


def leaf05(id_, filename, sheetname, desc):
    lf = Leaf(id_, filename, sheetname, desc)
    SHEET05_LEAVES[id_] = lf
    return lf


def compose_port(n):
    """05a-port{n}: RJ-45 FTP jack + mis-plug protection (REQ-HUB-COMMON-110)
    + DETECT/pin-7 chains (REQ-HUB-COMMON-042/112/114). One of 8 IDENTICAL
    leaves (the repeated-sheet case, see the module note above) built from
    this ONE template function, per-port refs J_PORT{n}/D_TVS{n}/D_VCC{n}/
    R_DSER{n}/D_DET{n}/R_DET{n}/R_SYNC{n}/D_SYNC{n}."""
    lf = leaf05(f"05a{n}", f"05a-port{n}.kicad_sch", f"05a-port{n}",
               f"Port {n}: RJ-45 FTP + mis-plug protection + DETECT/pin-7 chains "
               "(REQ-HUB-COMMON-042/110/112/114)")
    J = f"J_PORT{n}"
    DTVS, DVCC = f"D_TVS{n}", f"D_VCC{n}"
    RDSER, DDET, RDET = f"R_DSER{n}", f"D_DET{n}", f"R_DET{n}"
    RSYNC, DSYNC = f"R_SYNC{n}", f"D_SYNC{n}"

    lf.add_part(J, "cec-ent-hub-local", "CEC_RJ45_8P8C_FTP", f"PORT{n}", 0, 0,
                "cec:RJ45_FTP_Shielded_Horizontal",
                {"Manufacturer": "Kinghelm", "MPN": "KH-RJ45-58-8P8C", "LCSC": "C2683360",
                 "Description": f"Module port {n}, FTP RJ-45 8P8C, SH1/SH2->GND (Sec2.1 lock); "
                                 "widened local symbol copy for pin-glyph clearance at 8-port density"})
    lf.add_part(DTVS, "cec-ent-power", "SMAJ58A", "SMAJ58A", 0, 0,
                "cec-Diode_SMD:D_SMA_SMAJ58A_L4.4-W2.6-LS5.0",
                {"Manufacturer": "Littelfuse", "MPN": "SMAJ58A", "LCSC": "C499822",
                 "Description": "pin-1 VCC tail-risk TVS (REQ-HUB-COMMON-110; hub-ent-bom-detailed Sec6a)"})
    lf.add_part(DVCC, "cec-ent-power", "SS110", "SS110", 0, 0,
                "cec-Diode_SMD:D_SMA_SS110_L4.3-W2.6-LS5.2",
                {"Manufacturer": "MDD (Nanjing Silicon Chuang Tech)", "MPN": "SS110", "LCSC": "C2482",
                 "Description": "pin-1 VCC 100V series blocking Schottky, K toward the port "
                                 "(REQ-HUB-COMMON-110 per-pin analysis)"})
    lf.add_part(RDSER, "cec-vendor", "R_Small", "10k", 0, 0,
                "cec-Resistor_SMD:R_0402_1005Metric",
                {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
                 "Description": "DETECT series R ahead of the ESD clamp (REQ-HUB-COMMON-110; "
                                 "hub-ent-bom-detailed Sec6a names ~10k/1206 -- captured here as "
                                 "0402 [package flagged, not the BOM's 1206] pending bench calibration"})
    lf.add_part(DDET, "cec-vendor", "PESD5V0S1UL", "PESD5V0S1BA", 0, 0,
                "cec-Diode_SMD:D_SOD-323",
                {"Manufacturer": "Nexperia", "MPN": "PESD5V0S1BA", "LCSC": "C5261083",
                 "Description": "DETECT pin-8 ESD clamp (LOCKED Sec2.4)"})
    lf.add_part(RDET, "cec-vendor", "R_Small", "10k", 0, 0,
                "cec-Resistor_SMD:R_0402_1005Metric",
                {"Manufacturer": UR, "MPN": "0402WGF1002TCE", "LCSC": "C25744",
                 "Description": "DETECT pull-up to +3V3, Sec2.3 code table (10k/3.3V divider read)"})
    lf.add_part(RSYNC, "cec-vendor", "R_Small", "100", 0, 0,
                "cec-Resistor_SMD:R_0402_1005Metric",
                {"Manufacturer": UR, "MPN": "0402WGF1000TCE",
                 "Description": "pin-7 SYNC/FREEZE series R [illustrative value -- schematic-capture/"
                                 "bench-calibration task per hub-ent-bom-detailed Sec6a] (REQ-HUB-COMMON-112/114)"})
    lf.add_part(DSYNC, "cec-ent-power", "SMAJ58A", "SMAJ58A", 0, 0,
                "cec-Diode_SMD:D_SMA_SMAJ58A_L4.4-W2.6-LS5.0",
                {"Manufacturer": "Littelfuse", "MPN": "SMAJ58A", "LCSC": "C499822",
                 "Description": "pin-7 SYNC/FREEZE tail-risk TVS, >=60V-tolerant per the "
                                 "REQ-HUB-COMMON-110 per-pin analysis (the part's own vendored "
                                 "Description names both 'hub/module pin-1 VCC AND pin-7 "
                                 "SYNC/FREEZE' -- NOTE ent-common's module-side D2 instead used a "
                                 "plain low-cap PESD5V0S1BA clamp there; flagged, not reconciled here)"})

    lf.net(f"P{n}_VCC_RAW", (J, "1"), (DTVS, "2"), (DVCC, "1"))
    lf.net("+5VSB", (DVCC, "2"))
    lf.net("GND", (J, "2"), (J, "SH1"), (J, "SH2"), (DTVS, "1"), (DDET, "2"), (DSYNC, "1"))
    lf.net("+3V3", (RDET, "2"))
    lf.net("CAN_H", (J, "3"))
    lf.net("CAN_L", (J, "6"))
    lf.net(f"P{n}_T1_A", (J, "4"))
    lf.net(f"P{n}_T1_B", (J, "5"))
    lf.net(f"P{n}_SYNC7_RAW", (J, "7"), (RSYNC, "1"))
    lf.net(f"P{n}_SYNC7", (RSYNC, "2"), (DSYNC, "2"))
    lf.net(f"P{n}_DETECT_RAW", (J, "8"), (RDSER, "1"))
    lf.net(f"P{n}_DETECT_A", (RDSER, "2"), (DDET, "1"), (RDET, "1"))

    lf.hier_exports = {
        f"P{n}_T1_A":      ("output", (J, "4")),
        f"P{n}_T1_B":      ("output", (J, "5")),
        f"P{n}_SYNC7":     ("output", (RSYNC, "2")),
        f"P{n}_DETECT_A":  ("output", (RDSER, "2")),
    }

    c = _Compose(lf)
    c.place(J, 30, 54)
    # ---- pin 1 (VCC): jack -> SMAJ58A tail-risk shunt -> SS110 series block
    # -> +5VSB. (Drawn source-to-sink left-to-right for readability; the hub
    # actually SOURCES +5VSB onto this node, so the real current direction is
    # the mirror of the drawing -- noted in the caption below.)
    c.wire((16, 47), (14, 47), (14, 40))
    c.use((J, "1"))
    c.place_pin(DTVS, "2", 14, 40, 90)     # K (pin2) exactly on the VCC_RAW node
    c.use((DTVS, "2"))
    c.wire((14, 40), (20, 40))
    c.place(DVCC, 23, 40, 0)               # native horizontal: K(1)@(20,40) A(2)@(26,40)
    c.use((DVCC, "1"), (DVCC, "2"))
    c.wire((26, 40), (32, 40))
    c.stamp("+5VSB", 32, 40, 0)
    # ---- pin 2 (GND) + shield (SH1/SH2) -- same idiom as ent-common's 01-power
    c.wire((16, 49), (12, 49), (12, 38))
    c.stamp("GND", 12, 38, 180)
    c.use((J, "2"))
    c.wire((44, 53), (46, 53))
    c.wire((44, 55), (46, 55))
    c.wire((46, 53), (46, 55), (46, 60))
    c.stamp("GND", 46, 60, 0)
    c.use((J, "SH1"), (J, "SH2"))
    # ---- CAN_H/CAN_L (pins 3/6): left UNCONSUMED -- build_leaf's global_nets
    # path fires automatically (default stub + a global_label, no plumbing).
    # ---- T1 pair (pins 4/5): raw pass-through, S1 left column (protection
    # lives on sheet 06's per-port MDI frontend -- REQ-HUB-COMMON-110)
    c.io(f"P{n}_T1_A", "left")
    c.io(f"P{n}_T1_B", "left")
    # ---- pin 7: SYNC/FREEZE series R + tail-risk TVS (hand-wired: SMAJ58A's
    # pin1=A/pin2=K is the OPPOSITE of protection_chain's shunt-branch
    # assumption, which is shaped for D_Schottky-style pin1=K parts)
    p7 = c.pin(J, "7")
    c.wire(p7, (9, 59))
    c.wire((9, 59), (9, 90))
    c.use((J, "7"))
    c.place(RSYNC, 14, 90, 90)
    a7, b7 = c.pin(RSYNC, "1"), c.pin(RSYNC, "2")
    c.wire((9, 90), a7)
    c.use((RSYNC, "1"), (RSYNC, "2"))
    node_x = b7[0] + 8
    c.wire(b7, (node_x, 90))
    c.place_pin(DSYNC, "2", node_x, 90, 90)
    c.use((DSYNC, "2"))
    end7 = (node_x + 8, 90)
    c.wire((node_x, 90), end7)
    c.hier(f"P{n}_SYNC7", *end7, 0)
    # ---- pin 8: DETECT series R + ESD clamp + pull-up (Sec2.3 code read) --
    # PESD5V0S1BA is pin1=K, matching protection_chain's shunt assumption, so
    # this chain uses the shared archetype unchanged.
    p8 = c.pin(J, "8")
    c.wire(p8, (13, 61))
    c.wire((13, 61), (13, 115))
    c.use((J, "8"))
    arch.protection_chain(c, (13, 115),
                          [("series", RDSER), ("shunt", DDET), ("shunt", RDET)],
                          f"P{n}_DETECT_A", out_kind="hier", pitch=8)
    c.caption(lf.desc, 8, 22)
    c.note("VCC: SS110 100V series block + SMAJ58A tail-risk TVS (REQ-HUB-COMMON-110); "
           "DETECT: 10k series R [BOM names 1206 pkg, captured as 0402 here -- flagged] "
           "-> PESD5V0S1BA (LOCKED Sec2.4) + 10k pull-up to +3V3 (Sec2.3 code read); "
           "pin-7: 100R series R [illustrative] + SMAJ58A tail-risk clamp "
           "(REQ-HUB-COMMON-112/114). All pin-7/DETECT-series values are a "
           "schematic-capture/bench-calibration task per hub-ent-bom-detailed Sec6a, "
           "not bench-verified here.", 8, 128)
    c.done()
    return lf


for _n in range(1, 9):
    compose_port(_n)


def compose_can_frontend():
    """05b-can-frontend: TJA1051T/3 + 120ohm split termination, the SHARED
    front end for all 8 ports' CAN_H/CAN_L bus (REQ-HUB-COMMON-041/043)."""
    lf = leaf05("05b", "05b-can-frontend.kicad_sch", "05b-can-frontend",
               "TJA1051T/3 CAN transceiver + 120ohm split termination, shared 8-port bus "
               "(REQ-HUB-COMMON-041/043)")
    lf.add_part("U_CAN", "cec-vendor", "TJA1051T-3", "TJA1051T/3", 0, 0,
               "cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
               {"Manufacturer": "NXP", "MPN": "TJA1051T/3", "LCSC": "C38695",
                "Description": "Platform-locked classical CAN transceiver (Sec3.1 v3.5), "
                                "shared bus front end for all 8 module ports"})
    lf.add_part("R_CANT1", "cec-vendor", "R_Small", "60.4", 0, 0,
               "cec-Resistor_SMD:R_0402_1005Metric",
               {"Manufacturer": "Viking Tech", "MPN": "GR0402F60R4TAG00", "LCSC": "C49654185",
                "Description": "split termination, CAN_H leg"})
    lf.add_part("R_CANT2", "cec-vendor", "R_Small", "60.4", 0, 0,
               "cec-Resistor_SMD:R_0402_1005Metric",
               {"Manufacturer": "Viking Tech", "MPN": "GR0402F60R4TAG00", "LCSC": "C49654185",
                "Description": "split termination, CAN_L leg"})
    lf.add_part("C_CANT", "cec-vendor", "C_Small", "4n7", 0, 0,
               "cec-Capacitor_SMD:C_0402_1005Metric",
               {"Manufacturer": "Fenghua", "MPN": "0402B472K500NT", "LCSC": "C1538",
                "Description": "split-termination center cap"})
    lf.add_part("C_CANVCC", "cec-vendor", "C_Small", "100n", 0, 0,
               "cec-Capacitor_SMD:C_0402_1005Metric",
               {"Manufacturer": SAM, "MPN": "CL05B104KO5NNNC", "LCSC": "C1525",
                "Description": "U_CAN VCC decoupling"})
    lf.add_part("C_CANVIO", "cec-vendor", "C_Small", "100n", 0, 0,
               "cec-Capacitor_SMD:C_0402_1005Metric",
               {"Manufacturer": SAM, "MPN": "CL05B104KO5NNNC", "LCSC": "C1525",
                "Description": "U_CAN VIO decoupling"})

    lf.net("+5VSB", ("U_CAN", "3"), ("C_CANVCC", "1"))
    lf.net("+3V3", ("U_CAN", "5"), ("C_CANVIO", "1"))
    lf.net("GND", ("U_CAN", "2"), ("U_CAN", "8"), ("C_CANVCC", "2"), ("C_CANVIO", "2"),
           ("C_CANT", "2"))
    lf.net("CAN_TX", ("U_CAN", "1"))
    lf.net("CAN_RX", ("U_CAN", "4"))
    lf.net("CAN_H", ("U_CAN", "7"), ("R_CANT1", "1"))
    lf.net("CAN_L", ("U_CAN", "6"), ("R_CANT2", "2"))
    lf.net("CANT_CTR", ("R_CANT1", "2"), ("R_CANT2", "1"), ("C_CANT", "1"))

    lf.hier_exports = {
        "CAN_TX": ("output", ("U_CAN", "1")),
        "CAN_RX": ("output", ("U_CAN", "4")),
    }

    c = _Compose(lf)
    c.place("U_CAN", 40, 50)
    c.io("CAN_TX", "left")
    c.io("CAN_RX", "left")
    s_pin = c.pin("U_CAN", "8")
    c.wire(s_pin, (s_pin[0] - 4, s_pin[1]))
    c.stamp("GND", s_pin[0] - 4, s_pin[1], 180)
    c.use(("U_CAN", "8"))
    vio = c.pin("U_CAN", "5")
    cvio = c.place_pin("C_CANVIO", "2", vio[0] - 4, vio[1], 0)
    c.wire(vio, cvio)
    c.use(("U_CAN", "5"), ("C_CANVIO", "2"))
    cvio1 = c.pin("C_CANVIO", "1")
    c.wire(cvio1, (cvio1[0], cvio1[1] - 4))
    c.stamp("+3V3", cvio1[0], cvio1[1] - 4, 0)
    c.use(("C_CANVIO", "1"))
    vcc = c.pin("U_CAN", "3")
    c.wire(vcc, (vcc[0], vcc[1] - 6))
    cvcc = c.place_pin("C_CANVCC", "2", vcc[0], vcc[1] - 6, 0)
    c.use(("U_CAN", "3"), ("C_CANVCC", "2"))
    cvcc1 = c.pin("C_CANVCC", "1")
    c.wire(cvcc1, (cvcc1[0], cvcc1[1] - 4))
    c.stamp("+5VSB", cvcc1[0], cvcc1[1] - 4, 0)
    c.use(("C_CANVCC", "1"))
    canh = c.pin("U_CAN", "7")
    canl = c.pin("U_CAN", "6")
    c.place("R_CANT1", canh[0] + 8, canh[1], 90)
    r1a, r1b = c.pin("R_CANT1", "1"), c.pin("R_CANT1", "2")
    c.wire(canh, r1a)
    c.use(("U_CAN", "7"), ("R_CANT1", "1"), ("R_CANT1", "2"))
    c.place("R_CANT2", canl[0] + 8, canl[1], 90)
    r2a, r2b = c.pin("R_CANT2", "1"), c.pin("R_CANT2", "2")
    c.wire(canl, r2b)
    c.use(("U_CAN", "6"), ("R_CANT2", "1"), ("R_CANT2", "2"))
    ctr_x = max(r1b[0], r2a[0]) + 4
    c.wire(r1b, (ctr_x, r1b[1]))
    c.wire(r2a, (ctr_x, r2a[1]))
    c.wire((ctr_x, r1b[1]), (ctr_x, r2a[1]))
    c.place("C_CANT", ctr_x + 6, r1b[1], 90)
    cct1 = c.pin("C_CANT", "1")
    c.wire((ctr_x, r1b[1]), cct1)
    c.use(("C_CANT", "1"))
    cct2 = c.pin("C_CANT", "2")
    c.wire(cct2, (cct2[0], cct2[1] + 4))
    c.stamp("GND", cct2[0], cct2[1] + 4, 0)
    c.use(("C_CANT", "2"))
    c.caption(lf.desc, 10, 20)
    c.note("120ohm split term (60.4x2 + 4n7 center cap); S(STB) tied GND -- normal/"
           "active mode. CAN_H/CAN_L are GLOBAL LABELS binding to all 8 port leaves "
           "(build_thin_parent's sheet-pin fan-out is 1:1/2-endpoint only -- see "
           "cec_sch_compose.build_leaf's global_nets parameter).", 10, 92)
    c.done()
    return lf


compose_can_frontend()


def compose_detect_adc():
    """05c-detect-adc: ADS7830 8-ch I2C ADC digitizing each port's DETECT_A
    analog node (REQ-HUB-COMMON-042). FLAG: bom-c-module-if-base-secio.md
    Sec5 names ADS7830 an 'alternative not chosen' vs a per-channel
    comparator bank and marks the whole DETECT read-path question open;
    SCHEMATIC-PLAN.md Sec1 nonetheless plans this exact leaf/part, and the
    symbol is already T2-audited/vendored for precisely this role (its own
    Description says 'NOT YET RATIFIED, owner/firmware call'). Captured here
    per the plan with the ratification gap flagged, not silently resolved."""
    lf = leaf05("05c", "05c-detect-adc.kicad_sch", "05c-detect-adc",
               "ADS7830 8-ch I2C ADC: 8x DETECT_A -> DETECT_SDA/SCL (REQ-HUB-COMMON-042; "
               "NOT YET RATIFIED -- bom-c-module-if-base-secio.md Sec5)")
    lf.add_part("U_ADC", "cec-ent-power", "ADS7830IPWR", "ADS7830IPWR", 0, 0,
               "cec-Package_SO:TSSOP-16_ADS7830IPWR_L5.0-W4.4-P0.65",
               {"Manufacturer": TI, "MPN": "ADS7830IPWR", "LCSC": "C161747",
                "Description": "candidate DETECT/rail-sense ADC -- NOT YET RATIFIED "
                                "(owner/firmware call, bom-c-module-if-base-secio.md Sec5)"})
    lf.add_part("C_ADCVDD", "cec-vendor", "C_Small", "100n", 0, 0,
               "cec-Capacitor_SMD:C_0402_1005Metric",
               {"Manufacturer": SAM, "MPN": "CL05B104KO5NNNC", "LCSC": "C1525",
                "Description": "+VDD bypass"})
    lf.add_part("C_ADCREF", "cec-vendor", "C_Small", "1u", 0, 0,
               "cec-Capacitor_SMD:C_0603_1608Metric",
               {"Manufacturer": SAM, "MPN": "CL10A105KB8NNNC", "LCSC": "C15849",
                "Description": "internal-reference bypass, REFIN_REFOUT [value illustrative]"})
    lf.add_part("R_I2CSDA", "cec-vendor", "R_Small", "4.7k", 0, 0,
               "cec-Resistor_SMD:R_0402_1005Metric",
               {"Manufacturer": UR, "MPN": "0402WGF4701TCE",
                "Description": "I2C SDA pull-up [value illustrative]"})
    lf.add_part("R_I2CSCL", "cec-vendor", "R_Small", "4.7k", 0, 0,
               "cec-Resistor_SMD:R_0402_1005Metric",
               {"Manufacturer": UR, "MPN": "0402WGF4701TCE",
                "Description": "I2C SCL pull-up [value illustrative]"})

    lf.net("+3V3", ("U_ADC", "16"), ("C_ADCVDD", "1"), ("R_I2CSDA", "1"), ("R_I2CSCL", "1"))
    lf.net("GND", ("U_ADC", "9"), ("U_ADC", "11"), ("U_ADC", "12"), ("U_ADC", "13"),
           ("C_ADCVDD", "2"), ("C_ADCREF", "2"))
    lf.net("ADC_REF", ("U_ADC", "10"), ("C_ADCREF", "1"))
    lf.net("DETECT_SDA", ("U_ADC", "15"), ("R_I2CSDA", "2"))
    lf.net("DETECT_SCL", ("U_ADC", "14"), ("R_I2CSCL", "2"))
    for n in range(1, 9):
        lf.net(f"P{n}_DETECT_A", ("U_ADC", str(n)))

    lf.hier_exports = {f"P{n}_DETECT_A": ("output", ("U_ADC", str(n))) for n in range(1, 9)}
    lf.hier_exports["DETECT_SDA"] = ("output", ("U_ADC", "15"))
    lf.hier_exports["DETECT_SCL"] = ("output", ("U_ADC", "14"))

    c = _Compose(lf)
    c.place("U_ADC", 60, 60)
    for n in range(1, 9):
        c.io(f"P{n}_DETECT_A", "left")
    # both conns (U_ADC pin + the I2C pull-up) get consumed below, so the
    # default anchor-stub mechanism has no unconsumed pin to attach from --
    # give the io router an explicit from_pt (the SDA/SCL pin itself).
    c.io("DETECT_SDA", "right", from_pt=c.pin("U_ADC", "15"))
    c.io("DETECT_SCL", "right", from_pt=c.pin("U_ADC", "14"))
    gnd9 = c.pin("U_ADC", "9")
    c.wire(gnd9, (gnd9[0] + 4, gnd9[1]))
    c.stamp("GND", gnd9[0] + 4, gnd9[1], 0)
    c.use(("U_ADC", "9"))
    for pin in ("11", "12", "13"):
        p = c.pin("U_ADC", pin)
        c.wire(p, (p[0] + 4, p[1]))
        c.stamp("GND", p[0] + 4, p[1], 0)
        c.use(("U_ADC", pin))
    ref = c.pin("U_ADC", "10")
    cr2 = c.place_pin("C_ADCREF", "2", ref[0] + 6, ref[1], 0)
    c.wire(ref, cr2)
    c.use(("U_ADC", "10"), ("C_ADCREF", "2"))
    cr1 = c.pin("C_ADCREF", "1")
    c.wire(cr1, (cr1[0], cr1[1] - 4))
    c.stamp("GND", cr1[0], cr1[1] - 4, 180)
    c.use(("C_ADCREF", "1"))
    vdd = c.pin("U_ADC", "16")
    cv2 = c.place_pin("C_ADCVDD", "2", vdd[0] + 6, vdd[1], 0)
    c.wire(vdd, cv2)
    c.use(("U_ADC", "16"), ("C_ADCVDD", "2"))
    cv1 = c.pin("C_ADCVDD", "1")
    c.wire(cv1, (cv1[0], cv1[1] - 4))
    c.stamp("GND", cv1[0], cv1[1] - 4, 180)
    c.use(("C_ADCVDD", "1"))
    scl = c.pin("U_ADC", "14")
    c.place("R_I2CSCL", scl[0] + 8, scl[1] - 2, 0)
    r_scl1, r_scl2 = c.pin("R_I2CSCL", "1"), c.pin("R_I2CSCL", "2")
    c.wire(scl, r_scl2)
    c.wire(r_scl1, (r_scl1[0], r_scl1[1] - 4))
    c.stamp("+3V3", r_scl1[0], r_scl1[1] - 4, 0)
    c.use(("U_ADC", "14"), ("R_I2CSCL", "1"), ("R_I2CSCL", "2"))
    sda = c.pin("U_ADC", "15")
    c.place("R_I2CSDA", sda[0] + 8, sda[1] - 2, 0)
    r_sda1, r_sda2 = c.pin("R_I2CSDA", "1"), c.pin("R_I2CSDA", "2")
    c.wire(sda, r_sda2)
    c.wire(r_sda1, (r_sda1[0], r_sda1[1] - 4))
    c.stamp("+3V3", r_sda1[0], r_sda1[1] - 4, 0)
    c.use(("U_ADC", "15"), ("R_I2CSDA", "1"), ("R_I2CSDA", "2"))
    c.caption(lf.desc, 10, 22)
    c.note("NOT YET RATIFIED -- bom-c-module-if-base-secio.md Sec5 names ADS7830 an "
           "'alternative not chosen' vs a per-channel comparator bank; SCHEMATIC-PLAN.md "
           "Sec1 plans this leaf anyway and the part is T2-audited/vendored for exactly "
           "this role, so it is captured here with the ratification gap flagged, not "
           "silently resolved. A0/A1/COM tied GND (fixed I2C address, single-ended mode).",
           10, 100)
    c.done()
    return lf


compose_detect_adc()


# ---------------------------------------------------------------------------
# the 15 exports at the ROOT boundary -- UNCHANGED from the pre-restructure
# generator (same names, same shapes; build_root() and the root sheet's own
# 15 pins are therefore byte-identical to before). Only WHERE each anchor
# physically lives moved (now inside a leaf file instead of the flat sheet).
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
ROOT_EXPORT_NETS = set(HIER_EXPORTS)

# root-exports that reach root via a REAL KiCad global power symbol placed
# directly in the thin parent (no leaf sheet-pin at all -- see the note on
# L01G.hier_exports above). net_name -> power-symbol name (same for all three,
# but kept as a mapping for generality / a future net whose symbol name
# differs from its net name).
GLOBAL_POWER_EXPORTS = {n: n for n in ("+5V_MAIN", "+5VSB", "+5V_SYS")}

# ---------------------------------------------------------------------------
# 05's own root-level exports: each port's raw T1 pair + pin-7 SYNC (awaiting
# sheet 06/02/09 capture), the CAN transceiver's digital TX/RX, and the
# DETECT ADC's I2C bus. Mirrors sheet 01's own pattern of exporting to a box
# that has nothing wired to its pins yet (02/06/09 remain placeholders).
# ---------------------------------------------------------------------------
HIER_EXPORTS_05 = {}
for _n in range(1, 9):
    HIER_EXPORTS_05[f"P{_n}_T1_A"] = ("output", (f"J_PORT{_n}", "4"))
    HIER_EXPORTS_05[f"P{_n}_T1_B"] = ("output", (f"J_PORT{_n}", "5"))
    HIER_EXPORTS_05[f"P{_n}_SYNC7"] = ("output", (f"R_SYNC{_n}", "2"))
HIER_EXPORTS_05["CAN_TX"] = ("output", ("U_CAN", "1"))
HIER_EXPORTS_05["CAN_RX"] = ("output", ("U_CAN", "4"))
HIER_EXPORTS_05["DETECT_SDA"] = ("output", ("U_ADC", "15"))
HIER_EXPORTS_05["DETECT_SCL"] = ("output", ("U_ADC", "14"))
ROOT_EXPORT_NETS_05 = set(HIER_EXPORTS_05)


if __name__ == "__main__":
    from build_lib import build_root, build_leaf, build_placeholder, build_thin_parent

    LEAF_ORDER = ["01a", "01b", "01c", "01d", "01e", "01f", "01g"]
    leaf_page = {lid: f"2.{i+1}" for i, lid in enumerate(LEAF_ORDER)}

    total_parts = 0
    for li, lid in enumerate(LEAF_ORDER):
        lf = LEAVES[lid]
        path_prefix = f"{ROOT_UUID}/{SHEET_UUIDS['01']}/{LEAF_SYM_UUIDS[lid]}"
        sheet_instances_path = f"{SHEET_UUIDS['01']}/{LEAF_SYM_UUIDS[lid]}"
        stats = build_leaf(
            lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None,
            LIBS, PROJECT, path_prefix, sheet_instances_path, LEAF_OWN_UUIDS[lid],
            # A4 per leaf (was A3): each functional block is a compact
            # composition now, and a centered A4 page reads far better than a
            # mostly empty A3 (the owner's "middle of the sheets" ask).
            page=leaf_page[lid], out_path=f"{HERE}/{lf.filename}", paper="A4",
            title=f"CEC Hub -- Enterprise (ENT): {lf.sheetname}", comment1=lf.desc,
            # disjoint 100-block per leaf: #PWR/#FLG refs must be unique across
            # the FLATTENED design or kicad-cli reports annotation errors
            pwr_base=100 * (li + 1), layout=lf.layout)
        total_parts += stats["parts"]
        # T1 finishing pass: deterministic field-text collision resolution
        n_moved, still = cec_sch_layout.nudge_texts(f"{HERE}/{lf.filename}")
        stats["nudged"], stats["text_overlaps_left"] = n_moved, still
        print(f"{lf.filename}  " + "  ".join(f"{k}={v}" for k, v in stats.items()))

    # thin-parent sheet-box arrangement (flow, left -> right): the three eFuse
    # fronts feed the cascade with REAL drawn wires; cascade output cascades
    # to hold-up + buck below it; rail-sense on the right; EXT_5V runs under
    # the middle column to rail-sense. Sides are part of the pin spec; box
    # geometry is grid-aligned so sheet-pin stubs land on-grid (kills the old
    # endpoint_off_grid ERC/lint class without violating the pin-on-box-edge
    # exactness rule).
    PARENT_PINS = {
        "01a": [("PG_MAIN", "right"), ("FLT_MAIN", "right"), ("MAIN_EF_OUT", "right")],
        "01b": [("PG_SVB", "right"), ("FLT_SVB", "right"), ("SVB_EF_OUT", "right")],
        "01c": [("PG_EXT", "right"), ("FLT_EXT", "right"), ("EXT_EF_OUT", "right"),
                 ("EXT_5V", "right")],
        "01d": [("MAIN_EF_OUT", "left"), ("SVB_EF_OUT", "left"), ("EXT_EF_OUT", "left")],
        "01e": [],
        "01f": [("+3V3", "right")],
        "01g": [("EXT_5V", "left"), ("SENSE_MAIN", "right"), ("SENSE_SVB", "right"),
                 ("SENSE_EXT", "right"), ("SENSE_SYS", "right")],
    }
    for lid in LEAF_ORDER:
        assert {n for n, _s in PARENT_PINS[lid]} == set(LEAVES[lid].hier_exports), lid
    u = cec_sch.GRID
    BOX = {  # (x, y, h) in grid units; w uniform
        "01a": (16, 16, 24), "01b": (16, 48, 24), "01c": (16, 80, 28),
        "01d": (112, 16, 24), "01e": (112, 48, 16), "01f": (112, 72, 16),
        "01g": (208, 16, 28),
    }
    leaves_for_parent = []
    for lid in LEAF_ORDER:
        lf = LEAVES[lid]
        bx, by, bh = BOX[lid]
        leaves_for_parent.append({
            "id": lid, "sym_uuid": LEAF_SYM_UUIDS[lid], "filename": lf.filename,
            "sheetname": lf.sheetname, "page": leaf_page[lid],
            "x": bx * u, "y": by * u, "w": 70 * u, "h": bh * u,
            "pins": [(name, lf.hier_exports[name][0], side)
                      for name, side in PARENT_PINS[lid]],
        })

    parent_stats = build_thin_parent(
        leaves_for_parent, ROOT_EXPORT_NETS, PROJECT, ROOT_UUID, SHEET_UUIDS["01"],
        SHEET01_OWN_UUID, out_path=f"{HERE}/01-power-input.kicad_sch",
        title="CEC Hub -- Enterprise (ENT): 01-power-input (thin parent)", paper="A3",
        global_power_exports=GLOBAL_POWER_EXPORTS, libs=LIBS,
        pwr_base=100 * (len(LEAF_ORDER) + 1),
        gp_block_xy=(194 * u, 112 * u))
    print("01-power-input.kicad_sch (thin parent)  " +
          "  ".join(f"{k}={v}" for k, v in parent_stats.items()) +
          f"  total_leaf_parts={total_parts}")

    # ---- sheet 05: module ports (8x 05a-port{n} + 05b-can-frontend + 05c-detect-adc)
    LEAF_ORDER_05 = SHEET05_LEAF_IDS
    leaf_page_05 = {lid: f"3.{i+1}" for i, lid in enumerate(LEAF_ORDER_05)}
    total_parts_05 = 0
    for li, lid in enumerate(LEAF_ORDER_05):
        lf = SHEET05_LEAVES[lid]
        path_prefix = f"{ROOT_UUID}/{SHEET_UUIDS['05']}/{SHEET05_LEAF_SYM_UUIDS[lid]}"
        sheet_instances_path = f"{SHEET_UUIDS['05']}/{SHEET05_LEAF_SYM_UUIDS[lid]}"
        global_nets = {"CAN_H", "CAN_L"} if lid.startswith("05a") or lid == "05b" else set()
        stats = build_leaf(
            lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None,
            LIBS, PROJECT, path_prefix, sheet_instances_path, SHEET05_LEAF_OWN_UUIDS[lid],
            page=leaf_page_05[lid], out_path=f"{HERE}/{lf.filename}", paper="A4",
            title=f"CEC Hub -- Enterprise (ENT): {lf.sheetname}", comment1=lf.desc,
            # 1000-block, disjoint from sheet 01's leaves (100-800) + its
            # thin parent (800): #PWR/#FLG refs must stay unique across the
            # flattened design.
            pwr_base=1000 + 100 * li, layout=lf.layout, global_nets=global_nets)
        total_parts_05 += stats["parts"]
        n_moved, still = cec_sch_layout.nudge_texts(f"{HERE}/{lf.filename}")
        stats["nudged"], stats["text_overlaps_left"] = n_moved, still
        print(f"{lf.filename}  " + "  ".join(f"{k}={v}" for k, v in stats.items()))

    PARENT_PINS_05 = {}
    for _n in range(1, 9):
        PARENT_PINS_05[f"05a{_n}"] = [
            (f"P{_n}_T1_A", "right"), (f"P{_n}_T1_B", "right"),
            (f"P{_n}_SYNC7", "right"), (f"P{_n}_DETECT_A", "right"),
        ]
    PARENT_PINS_05["05b"] = [("CAN_TX", "right"), ("CAN_RX", "right")]
    PARENT_PINS_05["05c"] = ([(f"P{_n}_DETECT_A", "left") for _n in range(1, 9)]
                             + [("DETECT_SDA", "right"), ("DETECT_SCL", "right")])
    for lid in LEAF_ORDER_05:
        assert {n for n, _s in PARENT_PINS_05[lid]} == set(SHEET05_LEAVES[lid].hier_exports), lid

    BOX_05 = {f"05a{_n}": (16, 16 + i * 36, 24) for i, _n in enumerate(range(1, 9))}
    BOX_05["05b"] = (140, 16, 16)
    BOX_05["05c"] = (140, 50, 44)

    leaves_for_parent_05 = []
    for lid in LEAF_ORDER_05:
        lf = SHEET05_LEAVES[lid]
        bx, by, bh = BOX_05[lid]
        leaves_for_parent_05.append({
            "id": lid, "sym_uuid": SHEET05_LEAF_SYM_UUIDS[lid], "filename": lf.filename,
            "sheetname": lf.sheetname, "page": leaf_page_05[lid],
            "x": bx * u, "y": by * u, "w": 70 * u, "h": bh * u,
            "pins": [(name, lf.hier_exports[name][0], side)
                      for name, side in PARENT_PINS_05[lid]],
        })

    parent_stats_05 = build_thin_parent(
        leaves_for_parent_05, ROOT_EXPORT_NETS_05, PROJECT, ROOT_UUID, SHEET_UUIDS["05"],
        SHEET05_OWN_UUID, out_path=f"{HERE}/05-module-ports.kicad_sch",
        title="CEC Hub -- Enterprise (ENT): 05-module-ports (thin parent)", paper="A2",
        libs=LIBS, pwr_base=2000, page="3")
    print("05-module-ports.kicad_sch (thin parent)  " +
          "  ".join(f"{k}={v}" for k, v in parent_stats_05.items()) +
          f"  total_leaf_parts={total_parts_05}")

    # ---- root: 01-power-input (page 2) + 05-module-ports (page 3, NEW) +
    # 7 remaining placeholders (page 4+; "05" is no longer a placeholder)
    root_extra_sheets = [{
        "hier_exports": HIER_EXPORTS_05, "sym_uuid": SHEET_UUIDS["05"],
        "sheetname": "05-module-ports", "sheetfile": "05-module-ports.kicad_sch",
        "geom": (20, 120, 70, 180), "page": "3",
    }]
    placeholder_uuids = {n: SHEET_UUIDS[n] for n in SHEET_TITLES if n != "05"}
    build_root(HIER_EXPORTS, PROJECT, ROOT_UUID, SHEET_UUIDS["01"],
               placeholder_uuids, SHEET_TITLES,
               out_path=f"{HERE}/hub-enterprise.kicad_sch", paper="A2",
               extra_sheets=root_extra_sheets, first_placeholder_page=4)
    print("hub-enterprise.kicad_sch  sheets=2(power-input+module-ports parents)+7(placeholder)")

    remaining = sorted(k for k in SHEET_TITLES if k != "05")
    for i, num in enumerate(remaining):
        name, desc = SHEET_TITLES[num]
        page = 4 + i
        build_placeholder(num, SHEET_UUIDS[num], name, desc, PROJECT, page,
                           out_path=f"{HERE}/{name}.kicad_sch", paper="A4")
    print("Generated 7 placeholder sheets: " + ", ".join(SHEET_TITLES[n][0] for n in remaining))
