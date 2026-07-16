#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generates testers/tester-standard/ (ST-1000/ST-1300 tester main board) as a
# genuine hierarchy through the shared composition engine (scripts/cec_sch.py
# + cec_sch_layout.py + cec_sch_compose.py + cec_sch_archetypes.py), mirroring
# hubs/hub-enterprise/gen_hub_enterprise.py and modules/ent-common/
# gen_p4_t1_block.py. Root = thin parent (tester-standard.kicad_sch), no
# components of its own, fanning out to leaf sheets:
#
#   01-link         RJ-45 FTP + PoE-safe mis-plug chain + DETECT (2.2k ST
#                   code) + pin-7 conditioning + TJA1051T/3 + LP5907 3V3 LDO
#   02-power        USB-C PD (CH224K, 20V request) + USBLC6 + 2x TPS54331
#                   bucks (+12V_FAN, +5V_LOGIC) + 12V aux barrel OR
#   03-mcu          ESP32-C6-MINI-1-N4 core, BOOT/RESET, 4x PWM+RC setpoint
#                   networks, fan PWM+tach headers, NTC dividers, bimetal
#                   de-gate header, service button
#   04a-04d         4x CC loop leaves (12V/5V/3V3/5VSB-peak), one template
#                   function, 4 generated files (repeated-leaf convention)
#   05a-05e         5x R-bank leaves (12V/5V/3V3/5VSB/-12V), one template
#                   function, 5 generated files
#   06a-06c         3x SCP crowbar blocks (12V/5V/3V3), one template
#                   function, 3 generated files
#   07-displays     main SPI LCD header + 74HC595 CS chain + 6 bay-LCD
#                   headers + backlight PWM
#   08-deck-io      board-to-deck connectors: load-bus (labeled, mechanical),
#                   bay-LCD harness pass-through, tester-link pass-through
#
# SPLIT-ARCHITECTURE READINESS (mid-flight owner directive, 2026-07-16, see
# README.md "Split architecture"): every 04/05/06 leaf's hot cluster (switch/
# fuse/shunt/trip/local-gate-driver) sits behind a keyed CEC_CONN_1x{n}
# harness-boundary connector -- ONLY logic-level CTRL (enable/PWM) in and a
# digital TRIP_OUT (wired-OR per rail) out cross it; GND + a local +3V3_LOGIC
# feed also cross (a quiet DC feed, not "gate charge"); Kelvin sense pairs
# and the CC op-amp loop stay entirely on the hot side. De-gate pull-downs
# are placed AFTER (hot side of) every such connector -- see
# scripts/check_tester_st_sch.py's degate-pulldown-hot-side assertion.
#
#   python3 testers/tester-standard/gen_tester_st.py
#
# Validate: python3 scripts/check_tester_st_sch.py
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTDIR, "scripts"))
import cec_sch            # noqa: E402
import cec_sch_layout     # noqa: E402
import cec_sch_compose    # noqa: E402
import cec_sch_archetypes as arch  # noqa: E402

PROJECT = "tester-standard"
REV = "DRAFT"

# Fixed root identity (this project's own uuid; stable across regenerations).
ROOT_UUID = "8a1b2c3d-4e5f-4061-9a1b-2c3d4e5f6001"

LIBS = {
    "cec":            open(f"{ROOTDIR}/lib/cec.kicad_sym").read(),
    "cec-vendor":     open(f"{ROOTDIR}/lib/vendor/cec-vendor.kicad_sym").read(),
    "power":          open(f"{ROOTDIR}/lib/vendor/cec-power.kicad_sym").read(),
    "cec-ent-power":  open(f"{ROOTDIR}/lib/cec-ent-power.kicad_sym").read(),
    "cec-tester":     open(f"{ROOTDIR}/lib/cec-tester.kicad_sym").read(),
}

POWER_PORTS = {"GND": "GND", "+3V3": "+3V3", "+5VSB": "+5VSB",
               "+12V": "+12V", "-12V": "-12V"}
UR = "Uni-Royal"   # Yageo/Uni-Royal 0402 resistor manufacturer shorthand,
                   # matches the platform convention (gen_hub_enterprise.py)

# ---------------------------------------------------------------------------
# ESP32-C6-MINI-1-N4 name -> pin-number lookup (same technique as
# gen_p4_t1_block.py's P4 map).
def name_to_number(block):
    m = {}
    for mm in re.finditer(r'\(pin\s+\S+\s+\S+\s*\(at[^)]*\)\s*\(length[^)]*\)', block):
        seg = block[mm.start(): mm.start() + 400]
        nm = re.search(r'\(name "([^"]+)"', seg)
        nu = re.search(r'\(number "([^"]+)"', seg)
        if nm and nu:
            m[nm.group(1)] = nu.group(1)
    return m


C6_BLOCK = cec_sch.symbol_block(LIBS["cec-vendor"], "ESP32-C6-MINI-1-N4")
C6 = name_to_number(C6_BLOCK)

Leaf = cec_sch_compose.Leaf
LEAVES = {}


def leaf(id_, filename, sheetname, desc):
    lf = Leaf(id_, filename, sheetname, desc)
    LEAVES[id_] = lf
    return lf


FOOTPRINTS = {
    # 01-link (platform-reused parts; footprints match the precedent boards
    # exactly -- gen_hub_enterprise.py / modules/ent-common/gen_p4_t1_block.py)
    "J1": "cec:RJ45_FTP_Shielded_Horizontal",
    "D1": "cec-Diode_SMD:D_SMA_SMAJ58A_L4.4-W2.6-LS5.0",
    "D2": "cec-Diode_SMD:D_SMA_SS110_L4.3-W2.6-LS5.2",
    "D5": "cec-Diode_SMD:D_SMA_SMAJ58A_L4.4-W2.6-LS5.0",
    "D4": "cec-Diode_SMD:D_SOD-323",
    "U1": "cec-Package_DFN_QFN:VSON-10_DRC0010J_L3.0-W3.0-P0.50-EP",
    "U2": "cec-Package_TO_SOT_SMD:SOT-23-5",
    "U3": "cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "D3": "cec-Diode_SMD:D_SOD-323",
}


def fp_for(ref, lib, name, val):
    if ref in FOOTPRINTS:
        return FOOTPRINTS[ref]
    if name == "R_Small":
        return "cec-Resistor_SMD:R_0402_1005Metric"
    if name == "C_Small":
        return {"10u": "cec-Capacitor_SMD:C_0805_2012Metric",
                "1u":  "cec-Capacitor_SMD:C_0603_1608Metric",
                "100n": "cec-Capacitor_SMD:C_0402_1005Metric",
                "10n": "cec-Capacitor_SMD:C_0402_1005Metric",
                "1n": "cec-Capacitor_SMD:C_0402_1005Metric",
                }.get(val, "cec-Capacitor_SMD:C_0402_1005Metric")
    if name == "D_Schottky":
        return "cec-Diode_SMD:D_SOD-323"
    if name == "SW_Push":
        return "cec-Button_Switch_SMD:TS-1088-AR02016"
    if name == "Thermistor_NTC":
        return "cec-Resistor_SMD:NTC_0402_1005Metric"
    return ""


def ap(lf, ref, lib, name, val, props=None):
    """add_part with a dummy position (the compose pass places everything)."""
    lf.add_part(ref, lib, name, val, 0, 0, fp_for(ref, lib, name, val), props)


class _Compose(cec_sch_compose.Compose):
    def __init__(self, lf):
        super().__init__(lf, LIBS)


# ===========================================================================
# 01 -- link: RJ-45 FTP + PoE-safe mis-plug chain (owner directive, sec 12b:
# "copy the ENT pattern exactly") + DETECT (2.2k ST/CAN-only code, spec
# sec2.3) + pin-7 protection-only (consumer tier keeps pin 7 a RESERVED
# SPARE per the LOCKED pin table -- v1.2.0's "consumer keeps reserved-spare/
# NC, ENT = SYNC/FREEZE" edit; only ENT wires it to an MCU function) +
# TJA1051T/3 CAN + LP5907 3V3 LDO. Pins 4/5 (STREAM_P/N) unused at Standard
# tier per the locked pin table ("Standard tier leaves pair 2 unused,
# terminated at the module side").
#
# Mis-plug chain topology (VERBATIM from hubs/hub-enterprise/
# gen_hub_enterprise.py compose_port(), REQ-HUB-COMMON-110 / REQ-MOD-COMMON-
# 053 / survey 11): jack pin1 -> SMAJ58A shunt-to-GND (tail-risk TVS) +
# SS110 series block (K toward the jack, 100V, blocks a mis-plugged
# EXTERNAL over-voltage from reaching the board) -> TPS26621 60V auto-retry
# active eFuse (module-side active-OVP layer, ahead of the LDO per REQ-MOD-
# COMMON-053) -> LP5907 LDO -> +3V3. The tester additionally OR's its own
# USB-C-PD-derived +5V_LOGIC (from 02-power) into the SAME post-eFuse node
# via a Schottky (mission note: "the RJ-45/mezzanine VCC pin must NOT
# back-feed -- ORing per the module USB pattern (D_Schottky)", matching
# modules/ent-common's 06-usb-debug D3/SS34 precedent) -- ONE shared
# +3V3_LOGIC rail for the whole board from whichever source is live.
# ===========================================================================
L01 = leaf("01", "01-link.kicad_sch", "01-link",
           "RJ-45 FTP + PoE-safe mis-plug chain (SMAJ58A+SS110+TPS26621, "
           "copied from the ENT hub per-port pattern) + DETECT 2.2k (ST/"
           "CAN-only code) + pin-7 protection-only (reserved spare, "
           "consumer tier) + TJA1051T/3 + LP5907 3V3 LDO")
ap(L01, "J1", "cec", "CEC_RJ45_8P8C_FTP", "TO-HUB",
   {"Manufacturer": "Kinghelm", "MPN": "KH-RJ45-58-8P8C", "LCSC": "C2683360",
    "Description": "Tester link port, FTP RJ-45 8P8C, SH1/SH2->GND (sec2.1 "
                    "lock); Z1 deck-edge per DESIGN-SHEET.md sec C.6"})
ap(L01, "D1", "cec-ent-power", "SMAJ58A", "SMAJ58A",
   {"Manufacturer": "Littelfuse", "MPN": "SMAJ58A", "LCSC": "C499822",
    "Description": "pin-1 VCC tail-risk TVS (REQ-HUB-COMMON-110 pattern, "
                    "cross-lib reuse per sec12b owner directive)"})
ap(L01, "D2", "cec-ent-power", "SS110", "SS110",
   {"Manufacturer": "MDD (Nanjing Silicon Chuang Tech)", "MPN": "SS110",
    "LCSC": "C2482",
    "Description": "pin-1 VCC 100V series blocking Schottky, K toward the "
                    "jack (REQ-HUB-COMMON-110 pattern)"})
ap(L01, "U1", "cec-ent-power", "TPS26621DRCT", "TPS26621DRCT",
   {"Manufacturer": "Texas Instruments", "MPN": "TPS26621DRCT",
    "LCSC": "", "Description": "60V auto-retry active eFuse ahead of the "
                                "LDO (REQ-MOD-COMMON-053)"})
ap(L01, "R1", "cec-vendor", "R_Small", "100k")   # UVLO divider top [placeholder]
ap(L01, "R2", "cec-vendor", "R_Small", "20k")    # UVLO divider bottom
ap(L01, "R3", "cec-vendor", "R_Small", "100k")   # OVP divider top [placeholder]
ap(L01, "R4", "cec-vendor", "R_Small", "10k")    # OVP divider bottom
ap(L01, "R5", "cec-vendor", "R_Small", "10k")    # ILIM set [placeholder]
ap(L01, "C1", "cec-vendor", "C_Small", "1n")     # dVdT slew cap [placeholder]
ap(L01, "R6", "cec-vendor", "R_Small", "10k")    # FLT pull-up -> +3V3
ap(L01, "C2", "cec-vendor", "C_Small", "1u")     # eFuse IN bulk
ap(L01, "C3", "cec-vendor", "C_Small", "1u")     # eFuse OUT bulk
ap(L01, "D3", "cec-vendor", "D_Schottky", "SS34",
   {"Description": "ORs the tester's own USB-C-PD-derived +5V_LOGIC into "
                    "the mis-plug-protected node so the RJ-45/mezzanine "
                    "VCC pin never back-feeds (mission note); platform "
                    "USB-ORing pattern (modules/ent-common 06-usb-debug D3)"})
ap(L01, "U2", "cec-vendor", "LP5907MFX-1.2", "LP5907MFX-3.3")
ap(L01, "C4", "cec-vendor", "C_Small", "1u")     # LDO VIN bulk
ap(L01, "C5", "cec-vendor", "C_Small", "1u")     # LDO VOUT bulk
ap(L01, "R7", "cec-vendor", "R_Small", "1k")     # DETECT series R_s [wb]
ap(L01, "D4", "cec-vendor", "PESD5V0S1UL", "PESD5V0S1BA",
   {"Manufacturer": "Nexperia", "MPN": "PESD5V0S1BA", "LCSC": "C5261083",
    "Description": "DETECT pin-8 ESD clamp (LOCKED sec2.4)"})
ap(L01, "R8", "cec-vendor", "R_Small", "2k2")    # DETECT ST/CAN-only code
ap(L01, "R9", "cec-vendor", "R_Small", "100k")   # DETECT poke-and-ack tap
ap(L01, "R10", "cec-vendor", "R_Small", "100")   # pin-7 series R [placeholder]
ap(L01, "D5", "cec-ent-power", "SMAJ58A", "SMAJ58A",
   {"Manufacturer": "Littelfuse", "MPN": "SMAJ58A", "LCSC": "C499822",
    "Description": "pin-7 tail-risk TVS (mission: 'pin-7 R_SYNC+SMAJ58A "
                    "conditioning', ENT pattern); pin 7 stays a RESERVED "
                    "SPARE at consumer/Standard tier (spec sec2.3, LOCKED) "
                    "-- protected but NOT wired to an MCU GPIO (only ENT "
                    "redefines pin 7 as SYNC/FREEZE)"})
ap(L01, "U3", "cec-vendor", "TJA1051T-3", "TJA1051T/3")
ap(L01, "C6", "cec-vendor", "C_Small", "100n")   # CAN VCC bypass
ap(L01, "C7", "cec-vendor", "C_Small", "100n")   # CAN VIO bypass

L01.net("VCC_RAW", ("J1", "1"), ("D1", "2"), ("D2", "1"))
L01.net("VCC_PROT", ("D2", "2"), ("U1", "1"), ("R1", "1"), ("R3", "1"), ("U1", "4"), ("C2", "1"))
L01.net("+5V_PROT", ("U1", "10"), ("C3", "1"), ("D3", "1"), ("U3", "3"), ("C6", "1"),
        ("C4", "1"), ("U2", "1"), ("U2", "3"))
L01.net("+5V_LOGIC", ("D3", "2"))                # OR input from 02-power
# D3 (SS34, D_Schottky): pin1=K(cathode) on the SHARED rail (+5V_PROT), pin2=
# A(anode) on the DEDICATED source (+5V_LOGIC) -- standard diode-OR polarity
# (anode faces its own source, cathode faces the shared rail it feeds INTO),
# so +5V_LOGIC can push current into +5V_PROT but +5V_PROT can never push
# backward into the tester's own local buck2 output.
L01.net("+3V3", ("U2", "5"), ("C5", "1"), ("R6", "1"), ("R9", "2"), ("U3", "5"), ("C7", "1"))
L01.net("GND", ("J1", "2"), ("J1", "SH1"), ("J1", "SH2"),
        ("D1", "1"), ("U1", "5"), ("U1", "6"), ("U1", "11"),
        ("R2", "2"), ("R4", "2"), ("R5", "2"), ("C1", "2"),
        ("U2", "2"), ("C2", "2"), ("C3", "2"), ("C4", "2"), ("C5", "2"),
        ("D4", "2"), ("R8", "2"), ("D5", "2"),
        ("U3", "2"), ("U3", "8"), ("C6", "2"), ("C7", "2"))
L01.net("EF_UVLO", ("U1", "2"), ("R1", "2"), ("R2", "1"))
L01.net("EF_OVP",  ("U1", "3"), ("R3", "2"), ("R4", "1"))
L01.net("EF_ILIM", ("U1", "7"), ("R5", "1"))
L01.net("EF_DVDT", ("U1", "8"), ("C1", "1"))
L01.net("EF_FLT",  ("U1", "9"), ("R6", "2"))
L01.net("CAN_H_RJ", ("J1", "3"), ("U3", "7"))
L01.net("CAN_L_RJ", ("J1", "6"), ("U3", "6"))
L01.net("PAIR2_NC_A", ("J1", "4"))    # STREAM_P, unused at Standard tier
L01.net("PAIR2_NC_B", ("J1", "5"))    # STREAM_N, unused at Standard tier
L01.net("SYNC7_RAW", ("J1", "7"), ("R10", "1"))
L01.net("SYNC7_PROT", ("R10", "2"), ("D5", "1"))   # reserved spare, no MCU tap
L01.net("DETECT_RAW", ("J1", "8"), ("R7", "1"))
L01.net("DETECT_A", ("R7", "2"), ("D4", "1"), ("R8", "1"))
L01.net("DETECT_SENSE", ("R9", "1"))
L01.net("CAN_TX", ("U3", "1"))
L01.net("CAN_RX", ("U3", "4"))
L01.hier_exports = {
    "+5V_LOGIC":     ("output", ("D3", "2")),
    "+3V3":          ("output", ("U2", "5")),
    "CAN_TX":        ("output", ("U3", "1")),
    "CAN_RX":        ("output", ("U3", "4")),
    "DETECT_SENSE":  ("output", ("R9", "1")),
}
FOOTPRINTS.update({
    # 02-power
    "J2": "cec-Connector_USB:USB_C_Receptacle_XKB_U262-16XN-4BVC11",
    "U4": "cec-tester:ESSOP-10_L4.9-W3.9-P1.0-LS6.0-TL-EP",
    "U5": "cec-Package_TO_SOT_SMD:SOT-23-6",
    "U6": "cec-tester:SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL",
    "U7": "cec-tester:SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL",
    "J3": "cec-tester:DC-IN-TH_DC-005-5A-2.0",
    "D6": "cec-Diode_SMD:D_SOD-323",
})

L01.powerflag_nets = ["GND", "VCC_PROT"]
# GND is fed only by the jack shell (passive); VCC_PROT is fed only through
# the SS110/SMAJ58A mis-plug chain from the jack's pin 1 -- an externally-
# fed net with no on-board "Output Power" pin ahead of it, same class as the
# platform's own +5VSB-off-a-jack precedent (modules/ent-common 01-power).
# +3V3 is DRIVEN here (LP5907 output, a real regulator), so it needs no flag.


def compose_01():
    c = _Compose(L01)
    # ---- jack (the PLAIN platform cec:CEC_RJ45_8P8C_FTP -- NOT the widened
    # ent-common-local copy the ENT precedent uses; real geometry pulled via
    # c.pin() throughout rather than borrowing ENT's hardcoded coordinates,
    # since the plain symbol's pin pitch/offsets genuinely differ (measured:
    # pins 1-8 at x=22, y=47..61 step 2; SH1/SH2 at x=38, y=53/55) --
    # hardcoding the ENT numbers here silently produced a `pin not connected`
    # class ERC failure on the first pass (caught + root-caused before this
    # note was written).
    c.place("J1", 30, 54)
    p1, p2 = c.pin("J1", "1"), c.pin("J1", "2")
    psh1, psh2 = c.pin("J1", "SH1"), c.pin("J1", "SH2")
    # pin 1 (VCC) -> SMAJ58A shunt-to-GND + SS110 series block (hub-ent
    # per-port pattern, VERBATIM topology)
    c.wire(p1, (14, p1[1]), (14, 40))
    c.use(("J1", "1"))
    c.place_pin("D1", "2", 14, 40, 90)     # K (pin2) exactly on VCC_RAW
    c.use(("D1", "2"))
    c.wire((14, 40), (20, 40))
    c.place("D2", 23, 40, 0)               # native horizontal K(1)@20 A(2)@26
    c.use(("D2", "1"), ("D2", "2"))
    c.wire((26, 40), (32, 40))
    # ---- pin 2 (GND) + shield
    c.wire(p2, (12, p2[1]), (12, 38))
    c.stamp("GND", 12, 38, 180)
    c.use(("J1", "2"))
    c.wire(psh1, (44, psh1[1]))
    c.wire(psh2, (44, psh2[1]))
    c.wire((44, psh1[1]), (46, psh1[1]))
    c.wire((44, psh2[1]), (46, psh2[1]))
    c.wire((46, psh1[1]), (46, psh2[1]))
    c.wire((46, psh1[1]), (46, 40))
    c.stamp("GND", 46, 40, 0)
    c.use(("J1", "SH1"), ("J1", "SH2"))
    # pair 2 (pins 4/5): unused at Standard tier -- S1 left column, plain
    # local labels (not exported; a genuine dead stub -- Standard "terminate
    # at module side" convention)
    p4, p5 = c.pin("J1", "4"), c.pin("J1", "5")
    c.wire(p4, (8, p4[1]))
    c.label("PAIR2_NC_A", 8, p4[1], 180)
    c.use(("J1", "4"))
    c.wire(p5, (8, p5[1]))
    c.label("PAIR2_NC_B", 8, p5[1], 180)
    c.use(("J1", "5"))

    # ---- eFuse (widened TPS26621, same footprint/pin geometry as the ENT
    # precedent: side pins x 76/96, EP at (86,62)). VCC_PROT band drawn as
    # SEGMENTED wires between each tap x -- a pin binds only at a wire
    # ENDPOINT (a long single run merely passing THROUGH a pin's coordinate
    # does NOT connect in KiCad), so every tap (C2, R1, R3, the U1 straps)
    # must be a genuine segment boundary. (Verified against
    # gen_p4_t1_block.py's own working eFuse band, same shape.)
    c.place("U1", 86, 52)
    band = [(32, 40), (48, 40), (56, 40), (64, 40), (70, 40), (72, 40)]
    for a, b in zip(band, band[1:]):
        c.wire(a, b)
    c.wire((70, 40), (70, 54), (76, 54))
    c.use(("U1", "4"))                     # SHDN strapped to VCC_PROT (always-armed)
    c.wire((72, 40), (72, 48), (76, 48))
    c.use(("U1", "1"))
    c.place("C2", 48, 42)                  # pin 1 on the band split (x=48)
    c.use(("C2", "1"))
    c.label("VCC_PROT", 48, 40, 90)        # names the band for the PWR_FLAG
                                            # anchor block below to merge with
                                            # (an externally-fed net, same
                                            # class as the platform's own
                                            # +5VSB-off-a-jack precedent)
    # UVLO + OVP dividers hanging below the VCC_PROT band (pin 1 on the
    # band split, x=56/64)
    for rt, rb, x, tap in (("R1", "R2", 56, "EF_UVLO"), ("R3", "R4", 64, "EF_OVP")):
        c.place(rt, x, 42)
        c.place(rb, x, 48)
        c.text_side[rt] = c.text_side[rb] = "left"
        c.wire((x, 44), (x, 46))
        c.label(tap, x, 46, 180)
        c.use((rt, "1"), (rt, "2"), (rb, "1"))
    # RTN(5)+EP(11) tied under the body, one stamp
    c.wire((76, 56), (74, 56), (74, 62), (86, 62))
    c.wire((86, 62), (86, 64))
    c.stamp("GND", 86, 64, 0)
    c.use(("U1", "5"), ("U1", "11"))
    # GND(6) stamped clear above-right
    c.wire((96, 48), (98, 48), (98, 45))
    c.stamp("GND", 98, 45, 180)
    c.use(("U1", "6"))
    # ILIM(7)/dVdT(8) hangs
    c.place("R5", 102, 54)
    c.wire((96, 50), (102, 50), (102, 52))
    c.use(("U1", "7"), ("R5", "1"))
    c.place("C1", 99, 58)
    c.wire((96, 52), (99, 52), (99, 56))
    c.use(("U1", "8"), ("C1", "1"))
    # FLT pull-up
    c.use(("U1", "9"))
    arch.pullup_hang(c, (96, 54), 108, "R6", rx=106, rail_pin="1", above=True,
                     out=None)
    c.label("EF_FLT", 108, 54, 0)
    # ---- fused rail: OUT(10) -> y=66 baseline, feeds the LDO AND the
    # USB-ORing diode D3 (mission: +5V_LOGIC OR's in here)
    c.wire((96, 56), (98, 56), (98, 66))
    c.wire((98, 66), (104, 66))
    c.place("C3", 104, 68)
    c.wire((104, 66), (106, 66))
    c.use(("U1", "10"), ("C3", "1"))
    c.place("D3", 106, 74, 270)
    # pin1=K(cathode) -> +5V_PROT (shared rail); pin2=A(anode) -> +5V_LOGIC
    # (dedicated source). VERIFIED against the real symbol body (cec-vendor
    # D_Schottky_1_1: pin number "1" name "K", pin number "2" name "A) --
    # an earlier pass had this reversed (variable names `a3`/`k3` assumed
    # pin1=A, which is backwards) and built the diode-OR with its anode on
    # the shared rail instead of the source, i.e. it would have let +5V_PROT
    # push current out through D3 into the tester's own buck2 output instead
    # of blocking that path. ROTATION IS 270, NOT 90: at rot90 pin1(K) is
    # the FAR pin (y=77) and pin2(A) the NEAR one (y=71, between the (106,66)
    # junction and pin1) -- wiring the junction straight to the far pin
    # (pin1) then passes directly THROUGH pin2's own coordinate (both share
    # x=106), which KiCad's connectivity binds as a real pin-on-wire
    # connection (empirically confirmed: ERC's `multiple_net_names` fired,
    # +5V_PROT and +5V_LOGIC merged into one net). At rot270 the near/far
    # order swaps (pin1 near at y=71, pin2 far at y=77), so the same
    # near-pin-to-junction / far-pin-to-riser pattern below is pass-through-
    # free AND lands the correct pin on each net.
    k3, a3 = c.pin("D3", "1"), c.pin("D3", "2")
    c.wire((106, 66), k3)
    c.use(("D3", "1"))
    c.wire(a3, (a3[0], a3[1] + 6))
    c.io("+5V_LOGIC", "left", from_pt=(a3[0], a3[1] + 6))
    c.wire((106, 66), (110, 66))
    c.place("C4", 110, 68)
    c.wire((110, 66), (114, 66))
    c.wire((114, 66), (116, 66))
    c.wire((114, 66), (114, 68), (116, 68))   # EN strapped to IN
    c.use(("C4", "1"), ("U2", "1"), ("U2", "3"))
    # LDO
    c.place_pin("U2", "1", 116, 66)
    gnd = c.pin("U2", "2")
    c.wire(gnd, (gnd[0], gnd[1] + 2))
    c.stamp("GND", gnd[0], gnd[1] + 2, 0)
    c.use(("U2", "2"))
    out5 = c.pin("U2", "5")
    c.wire(out5, (130, 66))
    c.place("C5", 130, 68)
    c.wire((130, 66), (134, 66))
    c.wire((134, 66), (134, 60))
    c.stamp("+3V3", 134, 60, 0)
    c.use(("U2", "5"), ("C5", "1"))

    # ---- DETECT (pin 8): series R -> ESD clamp + 2.2k ST code + poke tap
    p8 = c.pin("J1", "8")
    c.wire(p8, (13, 61))
    c.wire((13, 61), (13, 100))
    c.use(("J1", "8"))
    end8 = arch.protection_chain(c, (13, 100),
                                 [("series", "R7"), ("shunt", "D4"),
                                  ("shunt", "R8"), ("series", "R9")],
                                 "DETECT_SENSE", out_kind="none",
                                 node_label="DETECT_A", pitch=8)
    c.io("DETECT_SENSE", "right", from_pt=end8)

    # ---- pin 7: series R + SMAJ58A clamp (PROTECTED, reserved spare --
    # NOT wired to an MCU GPIO at consumer/Standard tier)
    p7 = c.pin("J1", "7")
    c.wire(p7, (9, 59))
    c.wire((9, 59), (9, 118))
    c.use(("J1", "7"))
    arch.protection_chain(c, (9, 118), [("series", "R10"), ("shunt", "D5")],
                          "SYNC7_PROT", out_kind="label", pitch=8)

    # ---- CAN: TJA1051T/3. U3 sits far from the eFuse/LDO cluster (a wide
    # sheet), so its +5V_PROT supply (pin3, NOT a registered power_port --
    # unlike +3V3, which the generic pass ports for free) reaches the main
    # rail via a NAMED NET LABEL PAIR rather than a physical wire run across
    # unrelated content: one explicit c.label("+5V_PROT", ...) tapped off
    # the already-drawn main rail (at C3's node, before it continues into
    # D3/C4/the LDO) matches another at U3.3's own stub -- KiCad's same-
    # sheet same-name label connectivity joins them exactly like a drawn
    # wire would, without the crossing.
    c.label("+5V_PROT", 104, 66, 0)
    c.place("U3", 150, 40)
    p3, u37 = c.pin("J1", "3"), c.pin("U3", "7")
    c.wire(p3, (p3[0], 30), (u37[0], 30), u37)
    c.use(("J1", "3"), ("U3", "7"))
    p6, u36 = c.pin("J1", "6"), c.pin("U3", "6")
    # routed at y=34, NOT y=32 -- U3 pin 3 (VCC, +5V_PROT) sits at y=32
    # directly above the body; a same-row CAN_L run there would silently
    # MERGE the two nets by label/wire coincidence (caught + root-caused on
    # the first pass: the exported netlist showed J1.6/U3.6 folded into
    # /+5V_PROT).
    c.wire(p6, (p6[0], 34), (u36[0], 34), u36)
    c.use(("J1", "6"), ("U3", "6"))
    c.place("C6", 154, 24)
    u33 = c.pin("U3", "3")
    c6p1 = c.pin("C6", "1")               # C_Small pin1 = 2u ABOVE placement
    c.wire(u33, (u33[0], c6p1[1]), c6p1)
    c.use(("U3", "3"), ("C6", "1"))
    c.label("+5V_PROT", 152, c6p1[1], 0)
    # placed on the wire's HORIZONTAL leg near C6 (150,32)->(150,22)->(154,22)
    # -- not at u33 itself: a label anchored right on the pin, or even a few
    # units up the vertical leg, collides with U3 pin3's own name/number text
    # (VCC sits out to ~y=36.3, pin-number to ~y=33; a rotated 8-character
    # "+5V_PROT" string reaches that far). The horizontal leg is well clear
    # of U3's whole text cluster and still on the same drawn wire, so
    # connectivity is unaffected (cec_sch_layout --check-overlaps confirms).
    # U3 VIO (+3V3): a registered power_port -- a stamp connects project-wide
    # for free, no label pairing needed. Routed straight DOWN, away from
    # pin 4 (which sits directly above pin 5 at the same X -- an upward
    # riser would cross pin 4's own connection point, a real short caught
    # by ERC multiple_net_names on the first pass).
    u35 = c.pin("U3", "5")
    c.wire(u35, (u35[0], u35[1] + 6))
    c.stamp("+3V3", u35[0], u35[1] + 6, 0)
    c.use(("U3", "5"))
    c.place("C7", 158, 46)
    c.io("CAN_TX", "left")
    c.io("CAN_RX", "left")

    c.caption(L01.desc, 6, 8)
    c.note("Mis-plug chain topology copied VERBATIM from hub-enterprise's "
           "per-port pattern (SMAJ58A shunt + SS110 100V series block, K "
           "toward the jack) + TPS26621 60V auto-retry eFuse (REQ-MOD-"
           "COMMON-053). D3 (SS34) ORs the tester's own USB-C-PD-derived "
           "+5V_LOGIC into the post-eFuse node so the RJ-45/mezzanine VCC "
           "pin never back-feeds. DETECT R7=1k [wb] series (bracket "
           "narrower than ENT's 10k since ST codes are lower, 2.2k/4.7k/"
           "10k -- firmware-recalibration item like the ENT precedent). "
           "Pin 7 stays a protected RESERVED SPARE (spec sec2.3 LOCKED, "
           "consumer/Standard tier) -- no MCU GPIO tap.", 6, 130)
    c.done()


# ===========================================================================
# 02 -- power: USB-C PD self-power. CH224K requests 20V (efficient bucking
# for the 12V/2A fan rail) + USBLC6 ESD on VBUS/D+-/CC1/CC2 + 2x TPS54331
# bucks (VBUS_C(5-20V)->+12V_FAN~2A->+5V_LOGIC) + a 12V aux barrel jack
# diode-OR'd into +12V_FAN (bench-supply option when no USB-C PD source is
# present). +5V_LOGIC crosses into 01-link's mis-plug-protected node
# (D3/SS34) to make the single board-wide +3V3_LOGIC rail.
# ===========================================================================
L02 = leaf("02", "02-power.kicad_sch", "02-power",
           "USB-C PD (CH224K, 20V request) + USBLC6 + 2x TPS54331 bucks "
           "(+12V_FAN ~2A, +5V_LOGIC) + 12V aux barrel OR")
ap(L02, "J2", "cec-vendor", "USB_C_Receptacle_USB2.0_16P", "USB-C 2.0")
ap(L02, "U4", "cec-tester", "CH224K", "CH224K",
   {"Manufacturer": "WCH (Jiangsu Qin Heng)", "MPN": "CH224K", "LCSC": "C970725",
    "Description": "USB-PD/QC sink controller, strapped for 20V request "
                    "[wb, verify CFG1/2/3 code before fab]"})
ap(L02, "R11", "cec-vendor", "R_Small", "10k")   # CFG1 strap [wb]
ap(L02, "R12", "cec-vendor", "R_Small", "10k")   # CFG2 strap [wb]
ap(L02, "R13", "cec-vendor", "R_Small", "10k")   # CFG3 strap [wb]
ap(L02, "R14", "cec-vendor", "R_Small", "100k")  # PG pull-up (test point)
ap(L02, "U5", "cec-vendor", "USBLC6-2SC6", "USBLC6-2SC6")
ap(L02, "C8", "cec-vendor", "C_Small", "10u")    # VBUS_C bulk
ap(L02, "R15", "cec-vendor", "R_Small", "5k1")   # CC1 pulldown (UFP sink)
ap(L02, "R16", "cec-vendor", "R_Small", "5k1")   # CC2 pulldown (UFP sink)
ap(L02, "U6", "cec-tester", "TPS54331DR", "TPS54331DR",
   {"Manufacturer": "Texas Instruments", "MPN": "TPS54331DR", "LCSC": "C9865",
    "Description": "buck #1: VBUS_C (5-20V) -> +12V_FAN ~2A"})
ap(L02, "L1", "cec-vendor", "R_Small", "10uH")   # buck1 inductor [wb value]
ap(L02, "C9", "cec-vendor", "C_Small", "100n")   # buck1 BOOT cap
ap(L02, "C10", "cec-vendor", "C_Small", "10u")   # buck1 VIN bulk
ap(L02, "C11", "cec-vendor", "C_Small", "10u")   # buck1 VOUT bulk
ap(L02, "R17", "cec-vendor", "R_Small", "14k")   # buck1 fb top [wb]
ap(L02, "R18", "cec-vendor", "R_Small", "1k")    # buck1 fb bottom [wb, ~12V]
ap(L02, "C16", "cec-vendor", "C_Small", "1n")    # buck1 SS cap [wb]
ap(L02, "R21", "cec-vendor", "R_Small", "10k")   # buck1 COMP R [wb]
ap(L02, "C17", "cec-vendor", "C_Small", "1n")    # buck1 COMP C [wb]
ap(L02, "U7", "cec-tester", "TPS54331DR", "TPS54331DR",
   {"Manufacturer": "Texas Instruments", "MPN": "TPS54331DR", "LCSC": "C9865",
    "Description": "buck #2: +12V_FAN -> +5V_LOGIC"})
ap(L02, "L2", "cec-vendor", "R_Small", "10uH")   # buck2 inductor [wb value]
ap(L02, "C12", "cec-vendor", "C_Small", "100n")  # buck2 BOOT cap
ap(L02, "C13", "cec-vendor", "C_Small", "10u")   # buck2 VIN bulk
ap(L02, "C14", "cec-vendor", "C_Small", "10u")   # buck2 VOUT bulk
ap(L02, "R19", "cec-vendor", "R_Small", "5k23")  # buck2 fb top [wb]
ap(L02, "R20", "cec-vendor", "R_Small", "1k")    # buck2 fb bottom [wb, ~5V]
ap(L02, "C18", "cec-vendor", "C_Small", "1n")    # buck2 SS cap [wb]
ap(L02, "R22", "cec-vendor", "R_Small", "10k")   # buck2 COMP R [wb]
ap(L02, "C19", "cec-vendor", "C_Small", "1n")    # buck2 COMP C [wb]
ap(L02, "J3", "cec-tester", "DC-005-5A-2.0", "DC-005-5A-2.0",
   {"Manufacturer": "XKB Connectivity", "MPN": "DC-005-5A-2.0", "LCSC": "C381116",
    "Description": "12V aux barrel input, diode-OR'd into +12V_FAN (bench-"
                    "supply option when no USB-C PD source is present)"})
ap(L02, "D6", "cec-vendor", "D_Schottky", "SS34",
   {"Description": "12V aux barrel ORing diode into +12V_FAN"})
ap(L02, "C15", "cec-vendor", "C_Small", "10u")   # aux barrel input bulk

L02.net("VBUS_C", ("J2", "A4"), ("J2", "A9"), ("J2", "B4"), ("J2", "B9"),
        ("U5", "5"), ("C8", "1"), ("U4", "1"), ("U4", "8"),
        ("U6", "2"), ("C10", "1"), ("U6", "3"))   # EN strapped to VIN (always-armed)
L02.net("USB_D_P", ("J2", "A6"), ("J2", "B6"), ("U5", "1"))
L02.net("USB_D_N", ("J2", "A7"), ("J2", "B7"), ("U5", "3"))
L02.net("USB_CC1", ("J2", "A5"), ("U4", "7"), ("R15", "1"), ("U5", "4"))
L02.net("USB_CC2", ("J2", "B5"), ("U4", "6"), ("R16", "1"), ("U5", "6"))
L02.net("CH224_CFG1", ("U4", "9"), ("R11", "1"))
L02.net("CH224_CFG2", ("U4", "2"), ("R12", "1"))
L02.net("CH224_CFG3", ("U4", "3"), ("R13", "1"))
L02.net("CH224_PG", ("U4", "10"), ("R14", "1"))
L02.net("GND", ("J2", "A1"), ("J2", "A12"), ("J2", "B1"), ("J2", "B12"),
        ("J2", "S1"), ("U5", "2"), ("C8", "2"), ("R15", "2"), ("R16", "2"),
        ("R11", "2"), ("R12", "2"), ("R13", "2"), ("R14", "2"),
        ("U6", "7"), ("C10", "2"), ("C11", "2"), ("R18", "2"),
        ("C16", "2"), ("C17", "2"),
        ("U7", "7"), ("C13", "2"), ("C14", "2"), ("R20", "2"),
        ("C18", "2"), ("C19", "2"),
        ("J3", "2"), ("C15", "2"))
L02.net("BUCK1_SW", ("U6", "8"), ("L1", "1"), ("C9", "2"))   # PH also feeds the BOOT cap
L02.net("+12V_FAN", ("L1", "2"), ("C11", "1"), ("R17", "1"), ("D6", "1"),
        ("U7", "2"), ("U7", "3"), ("C13", "1"))  # buck2's VIN/EN(strapped)/VIN-bulk
L02.net("U6_FB", ("U6", "5"), ("R17", "2"), ("R18", "1"))
L02.net("BUCK1_BOOT", ("U6", "1"), ("C9", "1"))
L02.net("BUCK1_SS", ("U6", "4"), ("C16", "1"))
L02.net("BUCK1_COMP", ("U6", "6"), ("R21", "1"))
L02.net("BUCK1_COMP2", ("R21", "2"), ("C17", "1"))
L02.net("+12V_AUX_RAW", ("J3", "1"), ("D6", "2"), ("C15", "1"))
L02.net("BUCK2_SW", ("U7", "8"), ("L2", "1"), ("C12", "2"))
L02.net("+5V_LOGIC", ("L2", "2"), ("C14", "1"), ("R19", "1"))
L02.net("U7_FB", ("U7", "5"), ("R19", "2"), ("R20", "1"))
L02.net("BUCK2_BOOT", ("U7", "1"), ("C12", "1"))
L02.net("BUCK2_SS", ("U7", "4"), ("C18", "1"))
L02.net("BUCK2_COMP", ("U7", "6"), ("R22", "1"))
L02.net("BUCK2_COMP2", ("R22", "2"), ("C19", "1"))
L02.hier_exports = {
    "+5V_LOGIC": ("output", ("L2", "2")),
}
L02.powerflag_nets = ["GND", "VBUS_C", "+12V_FAN"]
# VBUS_C is fed only through the USB-C connector's own (Passive-typed) pins
# -- an externally-fed net with no on-board "Output Power" pin ahead of it,
# same class as 01-link's VCC_PROT. +12V_AUX_RAW is fed only through the
# barrel jack + diode -- externally-fed too, but NOT flagged: it is an
# OPTIONAL/absent-by-default source (the board's real supply is USB-C PD),
# so an un-driven state when the jack is empty is the CORRECT default, not
# an ERC-worthy omission. +12V_FAN IS flagged: it is buck1's real regulated
# output (EN strapped high = always-armed whenever VBUS_C is present), but
# the only path from U6 to it runs THROUGH L1 (an inductor, correctly typed
# Passive) -- ERC cannot trace a driven rail through a passive part, so the
# same "downstream of an inductor needs an explicit flag" rule that applies
# to every buck/LDO-behind-a-filter output applies here (buck2's own output,
# +5V_LOGIC, needs no flag only because nothing IN THIS LEAF types a
# power-input pin onto it -- U7.VIN is on +12V_FAN, not +5V_LOGIC).


def _buck_stage(c, u, l, cin, cout, rfb_top, rfb_bot, cboot, css, rcomp,
                ccomp, x0, y0, out_net):
    """One TPS54331 buck stage, placed as a compact cluster at (x0,y0).
    Only the CRITICAL FLOW is hand-wired (VIN->IC->L->Vout, feedback
    divider tap, EN/BOOT straps); GND/SS/COMP/decoupling pins are left to
    the generic per-net stub+label pass (simpler and less collision-prone
    than hand-routing every tap -- 01-link's own debugging found several
    real shorts from over-eager hand-wiring; this leaf deliberately hand-
    wires LESS)."""
    c.place(u, x0, y0)
    c.place(l, x0 + 18, y0 - 4, 90)
    # cin's own unconsumed pin1 (a VIN-net member, auto-labeled) sits close
    # enough to the VIN/EN/SS pin cluster at the original y0+8 offset to
    # collide with SS(4)'s pin-name text; dropped further down/left for
    # clearance (still reads as "the VIN bulk cap next to VIN", just with
    # more room under the package).
    c.place(cin, x0 - 14, y0 + 14)
    c.place(cout, x0 + 28, y0 - 4)
    c.place(rfb_top, x0 + 32, y0 - 2)
    c.place(rfb_bot, x0 + 32, y0 + 4)
    c.text_side[rfb_top] = c.text_side[rfb_bot] = "left"
    c.wire((x0 + 32, y0), (x0 + 32, y0 + 2))
    c.label(f"{u}_FB", x0 + 32, y0 + 2, 180)
    c.use((rfb_top, "2"), (rfb_bot, "1"))
    # rfb_top pin1 (the divider's OUTPUT-rail tap) is deliberately left
    # UNCONSUMED: it is already a member of `out_net`'s net table (the
    # regulator's own output rail), so the generic per-net stub+label pass
    # auto-labels it there -- matching the inductor's own out pin handling
    # below. (Earlier bug: marking it "used" here without ever drawing a
    # wire/label to it left it a bare unconnected pin -- ERC caught it as
    # `pin_not_connected` on R17/R19 pin1.)
    # cboot (the BOOT-PH bootstrap cap) sits near the pins it actually
    # bridges -- BOOT(1)/PH(8) are BOTH on the RIGHT side of the package
    # (x0+12); the original x0-4 placement tucked it in near the LEFT-side
    # VIN/EN/SS cluster instead, and its own unconsumed pin2 (a BUCK1_SW/
    # BUCK2_SW member, auto-labeled) landed close enough to VIN's pin-name
    # text to collide (cec_sch_layout --check-overlaps caught it).
    c.place(cboot, x0 + 12, y0 - 14)
    c.place(css, x0 - 4, y0 + 14)
    c.place(rcomp, x0 + 8, y0 + 16, 90)    # horizontal: pin1 left, pin2 right
    c.place(ccomp, x0 + 14, y0 + 16, 90)
    rc1, rc2 = c.pin(rcomp, "1"), c.pin(rcomp, "2")
    cc1 = c.pin(ccomp, "1")
    ucomp = c.pin(u, "6")
    c.wire(ucomp, (ucomp[0], rc1[1]), rc1)
    c.use((u, "6"), (rcomp, "1"))
    c.wire(rc2, cc1)
    c.use((rcomp, "2"), (ccomp, "1"))
    # EN (pin 3) is STRAPPED to VIN (pin 2) with a real short wire -- both
    # are adjacent left-side pins 4 units apart at the same x. (An earlier
    # pass left EN fully unconsumed, relying on the generic per-net pass to
    # auto-stub+label it separately from VIN's own auto-stub next door --
    # legal, but at SOIC-8 pin pitch the two independent stubs/labels landed
    # close enough to collide with pin4 (SS)'s own name text, caught by
    # cec_sch_layout --check-overlaps. A direct strap plus ONE explicit
    # label reads more like a hand-drawn "EN tied to VIN" strap anyway.)
    vin_net = next(n for n, conns in c.lf.nets.items() if (u, "2") in conns)
    p2, p3 = c.pin(u, "2"), c.pin(u, "3")
    c.wire(p3, p2)
    c.wire(p2, (p2[0] - 10, p2[1]))
    c.label(vin_net, p2[0] - 10, p2[1], 180)
    c.use((u, "2"), (u, "3"))
    # (Earlier bug, now also fixed: `c.use((u, "3"))` alone marked it
    # consumed without ever drawing a wire/label -- ERC caught it as
    # `pin_not_connected` + `pin_not_driven` on U6/U7 pin 3.)
    if out_net in c.lf.hier_exports:
        # the hier_exports anchor pin must be explicitly consumed (else the
        # generic per-pin pass ALSO fires on it, double-emitting a label) --
        # the io() column mechanism draws its own wire from from_pt, which
        # IS the pin's only connection. Jogged UP to y0-8 first: a straight
        # shot from the inductor's own row runs directly through the
        # feedback divider's own pin (measured: `io column: wire passes
        # through pin` on the first pass).
        lp = c.pin(l, "2")
        jog = (lp[0], y0 - 8)
        c.wire(lp, jog)
        c.use((l, "2"))
        c.io(out_net, "right", from_pt=jog)
    # else: the inductor's output pin (l, "2") is left UNCONSUMED -- the
    # generic per-net pass auto-stubs+labels it with `out_net`'s own name,
    # simpler and less collision-prone than hand-placed labels (01-link's
    # debugging found several real shorts from over-eager hand-wiring).


def compose_02():
    c = _Compose(L02)
    c.place("J2", 16, 40)
    # USB_D_P/N, USB_CC1/2 are purely internal to this leaf (CH224K + USBLC6
    # + the connector all live here) -- no io() needed, the generic per-net
    # pass auto-stubs+labels them.
    # J2's four VBUS_C pins (A4/A9/B4/B9, the USB-C mirrored-orientation
    # duplicates) are drawn COINCIDENT by the symbol itself -- all four
    # query to the exact same (x,y). Left fully unconsumed, the generic pass
    # still fires once per net MEMBER (not per unique point), so it stamped
    # 4 independent "VBUS_C" stub+labels on top of each other (cec_sch_layout
    # --check-overlaps: identical-coordinate self-collisions). Consuming 3 of
    # the 4 with NO wire is safe here specifically because they already sit
    # at A4's own coordinate -- KiCad joins same-point pins exactly like a
    # drawn wire would, so this is not the earlier "marked used but never
    # wired" bug (that bug was pins that do NOT coincide with anything).
    c.use(("J2", "A9"), ("J2", "B4"), ("J2", "B9"))
    # same pattern, same fix, for J2's four GND-return pins (A1/A12/B1/B12,
    # also coincident in the symbol at one point distinct from the shield
    # pin S1) -- left fully unconsumed they stamped 4 overlapping GND power-
    # flag glyphs on top of each other (cec_sch_layout --check-wires:
    # GLYPH-CLIP). S1 (shield, a separate coordinate) keeps its own flag.
    c.use(("J2", "A12"), ("J2", "B1"), ("J2", "B12"))

    # ---- CH224K PD sink + USBLC6 + CC pulldowns + CFG straps
    # (spacing widened from the original tight cluster -- U5/J2/U4/R15-16
    # were close enough that their independently-unconsumed VBUS_C/USB_CC1/
    # USB_CC2/USB_D_N pins' auto-labels collided with each other and with
    # neighboring pin name/number text; cec_sch_layout --check-overlaps.)
    c.place("U4", 66, 40)
    c.place("U5", 34, 62)                 # USBLC6, pulled clear of J2's pin-text column
    c.place("C8", 48, 56)
    # (moved down 6 units from the original y=50 -- C8 pin1's own auto-stub
    # for VBUS_C was landing at the same real Y as U4 pin8's VBUS auto-stub,
    # two independent-but-same-net labels converging with facing
    # justification; cec_sch_layout --check-overlaps caught it.)
    c.place("R15", 50, 26, 90)
    c.place("R16", 50, 30, 90)
    for rref, x in (("R11", 80), ("R12", 100), ("R13", 120)):
        c.place(rref, x, 30)
        c.text_side[rref] = "left"
    c.place("R14", 80, 60)

    # ---- buck 1: VBUS_C -> +12V_FAN (out_net not a hier_export, no io())
    _buck_stage(c, "U6", "L1", "C10", "C11", "R17", "R18", "C9", "C16",
               "R21", "C17", 110, 50, "+12V_FAN")

    # ---- buck 2: +12V_FAN -> +5V_LOGIC (a real hier_export)
    _buck_stage(c, "U7", "L2", "C13", "C14", "R19", "R20", "C12", "C18",
               "R22", "C19", 110, 90, "+5V_LOGIC")

    # ---- 12V aux barrel OR into +12V_FAN
    c.place("J3", 16, 90)
    # D6 (SS34, D_Schottky): rotated 180 so its pin2=A(anode) -- the real
    # symbol's anode, VERIFIED against cec-vendor D_Schottky_1_1 (pin number
    # "1" name "K", pin number "2" name "A") -- lands on the LEFT, facing the
    # jack/source (+12V_AUX_RAW); pin1=K(cathode) lands on the RIGHT, facing
    # the shared rail (+12V_FAN). Standard diode-OR polarity: anode faces its
    # own dedicated source, cathode faces the shared rail it feeds INTO, so
    # the barrel jack can push current into +12V_FAN but +12V_FAN (buck1's
    # own regulated output) can never push backward out through the jack.
    # (Earlier pass had this at rotation 0 with pin1/K wired to the jack --
    # backwards, same swapped-pin assumption as 01-link's D3; caught here
    # first via ERC's power_pin_not_driven on U7.VIN, then root-caused
    # against the real symbol body once +12V_FAN's own drive path was
    # checked end to end.)
    c.place("D6", 34, 90, 180)
    c.place("C15", 16, 100)
    j31 = c.pin("J3", "1")
    d6a = c.pin("D6", "2")                 # anode, faces the jack
    c.wire(j31, (24, j31[1]), (24, 90), d6a)
    c.use(("J3", "1"), ("D6", "2"))
    c15p1 = c.pin("C15", "1")
    c.wire((24, j31[1]), (24, c15p1[1]), c15p1)   # tap C15 onto the same run
    c.use(("C15", "1"))
    c.label("+12V_AUX_RAW", 24, 96, 90)
    # this whole run (J3.1 - D6 anode - C15.1) is entirely hand-wired/
    # consumed, so it never gets the generic pass's own auto-label -- without
    # this explicit one the exported netlist showed it only as the KiCad
    # auto-name "Net-(D6-A)" (electrically correct, just unlabeled/opaque).
    # D6 pin 1 (cathode, +12V_FAN) left UNCONSUMED -- auto-labeled by the
    # generic pass, merging with buck1's own (also unconsumed) L1 pin 2 by
    # shared net name, same technique as the buck-stage helper above.

    c.caption(L02.desc, 6, 8)
    c.note("CFG1/2/3 straps [wb] -- select the CH224K 20V request code, "
           "verify against the datasheet Table before fab. Buck feedback "
           "dividers + SS/COMP RC values ALL [wb] -- schematic-capture "
           "placeholders per TI's typical application circuit, bench-tune "
           "at layout (same discipline as every other [wb] value in this "
           "capture). +12V_AUX_RAW (barrel jack) is diode-OR'd into "
           "+12V_FAN -- an OPTIONAL bench-supply path, not flagged for "
           "PWR_FLAG (absent-by-default is correct, USB-C PD is the real "
           "supply).", 6, 110)
    c.done()



if __name__ == "__main__":
    compose_01()
    compose_02()
    for lf, fname in ((L01, "01-link"), (L02, "02-power")):
        stats = cec_sch_compose.build_leaf(
            lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None,
            LIBS, PROJECT, path_prefix="TESTROOT", sheet_instances_path="TESTROOT",
            own_uuid="11111111-1111-1111-1111-111111111111",
            page="2", out_path=f"{HERE}/{fname}.kicad_sch", paper="A3",
            title="TEST", comment1=lf.desc, pwr_base=100, layout=lf.layout)
        print(f"{fname}:", stats)
