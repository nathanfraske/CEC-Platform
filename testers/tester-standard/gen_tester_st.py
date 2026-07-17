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


def all_pins_named(block, name):
    """Every pin NUMBER sharing a given NAME (name_to_number collapses
    duplicates to the last match -- fine for the single-instance signals
    this leaf cares about, WRONG for GND: the ESP32-C6-MINI-1-N4 exposes 22
    separate GND pins/pads, not one. Discovered when the exported netlist
    showed 20 of them as `unconnected-(U8-GND-PadN)` -- only the one
    C6["GND"] happened to collapse to (pin 53) was ever actually wired."""
    out = []
    for mm in re.finditer(r'\(pin\s+\S+\s+\S+\s*\(at[^)]*\)\s*\(length[^)]*\)', block):
        seg = block[mm.start(): mm.start() + 400]
        nm = re.search(r'\(name "([^"]+)"', seg)
        nu = re.search(r'\(number "([^"]+)"', seg)
        if nm and nu and nm.group(1) == name:
            out.append(nu.group(1))
    return out


C6_BLOCK = cec_sch.symbol_block(LIBS["cec-vendor"], "ESP32-C6-MINI-1-N4")
C6 = name_to_number(C6_BLOCK)
C6_GND_PINS = all_pins_named(C6_BLOCK, "GND")   # all 22, not just C6["GND"]

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
    # ---- 04-08 additions (2026-07-17, continuation capture): name-based so
    # every instance across the load-plane/display/deck leaves picks up the
    # right land with no per-ref FOOTPRINTS bookkeeping.
    if name == "IRLB3034":
        return "cec-tester:TO-220-3_L10.2-W4.5-P2.54-L"
    if name == "IRLZ44N":
        return "cec-tester:TO-220-3_L10.2-W4.5-P2.54-L"
    if name == "IXTH75N10L2":
        return "cec-tester:TO-247-3_L15.9-W20.8-P5.45-Vertical"
    if name == "AOD4184A":
        return "cec-tester:TO-252-2_L6.6-W6.1-P4.57-LS9.9-TL-CW"
    if name == "OPA2277UA":
        return "cec-tester:SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL"
    if name == "INA181A2IDBVR":
        return "cec-Package_TO_SOT_SMD:SOT-23-6"
    if name == "TLV7011DBVR":
        return "cec-Package_TO_SOT_SMD:SOT-23-5"
    if name == "SN74AHCT1G08":
        return "cec-Package_TO_SOT_SMD:SOT-23-5"
    if name == "3557-10":
        return "cec-tester:FUSE-TH_4P-L19.8-W6.7_3557-2"
    if name == "SMCJ15A-13-F":
        return "cec-tester:SMC_L7.1-W6.2-LS8.1-FD"
    if name == "CEC_CONN_1x4":
        return "cec-tester:PinHeader_1x04_P2.54mm_Vertical"
    if name == "CEC_CONN_1x8":
        return "cec-tester:PinHeader_1x08_P2.54mm_Vertical"
    if name == "CEC_CONN_1x12":
        return "cec-tester:PinHeader_1x12_P2.54mm_Vertical"
    return ""


# ===========================================================================
# Shared ref allocator for 04-08 (2026-07-17 continuation). 01-link/02-power/
# 03-mcu used R1-R56 (gaps), C1-C64 (gaps), U1-U17, D1-D6, J1-J7, SW3-SW5,
# TH1-TH6 -- every new leaf below draws from ONE counter per class, starting
# well clear of that range, shared across ALL of 04-08 so two leaves can
# never collide even by mistake (refs must be unique project-wide once the
# root composes all 17 leaves together). "Q" and "F" are fresh ref classes
# (FETs, fuses) -- 01/02/03 never used them, so they start at 1.
# ===========================================================================
_REF_NEXT = {"R": 100, "C": 100, "U": 100, "Q": 1, "D": 100, "F": 1, "J": 100}


def nref(cls):
    n = _REF_NEXT[cls]
    _REF_NEXT[cls] = n + 1
    return f"{cls}{n}"


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


# ===========================================================================
# 03 -- mcu: ESP32-C6-MINI-1-N4 core + the GPIO-budget shift-register
# expansion bus that the ST board's raw signal count forces (see pin-audit-
# review-2026-07-16.txt addenda 1/2 for the full derivation; this leaf
# CAPTURES that already-reviewed design, it does not re-decide it).
#
# GPIO MAP -- FINAL, ALL 20 GPIOs COMMITTED, ZERO SPARE (tightened from the
# addenda's "17 of 20 / 3 spare" by two real findings made DURING capture,
# both logged in the audit review, not silently absorbed):
#   (a) the coordinator's ladder v1.1 scope update upgraded the 5VSB loop to
#       a full analog CC channel needing its own PWM setpoint -- +1 GPIO.
#   (b) 74HC165 has NO output-enable/tri-state pin (verified against the
#       promoted symbol -- pins are ~PL/CP/D0-D7/~Q7/Q7/DS/~CE/VCC only), so
#       the addenda's "DATA reverses direction, half-duplex" plan for the
#       shift bus is NOT buildable as a single wire: the last 165's Q7
#       output would permanently contend with the MCU driving the same node
#       for the 595 side. Split into SHIFT_DATA_OUT (MCU->595 chain) +
#       SHIFT_DATA_IN (165 chain->MCU) -- +1 GPIO. RXD0/TXD0 are separate
#       dedicated UART0 pins (not part of the 20-GPIO count), so the debug
#       console costs nothing from this budget.
#   IO0  ADC_MUX_IN (CD4051 COM, analog in: DETECT_SENSE relay + 6 local NTC)
#   IO1  PWM_SETPOINT_5VSB   IO2  BACKLIGHT_PWM (real PWM, not a 595 bit --
#        LCD dimming wants continuous control, a shift bit is only on/off)
#   IO3  TRIP_ANY (direct GPIO interrupt, diode-OR'd project-wide)
#   IO4  SCP_FIRE_SHARED (direct GPIO, ANDed per-block with its expander ARM)
#   IO5  DEGATE_DRIVE (direct GPIO, in series through the bimetal backstop
#        header to DEGATE_RAIL)
#   IO6  SHIFT_OE# (direct GPIO, PULLED UP = safe Hi-Z default)
#   IO7  SHIFT_DATA_IN (165 chain -> MCU)      IO8  FAN_PWM (shared, all fans)
#   IO9  BOOT strap (button to GND)
#   IO12 USB_D_N   IO13 USB_D_P (native USB, SHARED with 02-power's J2/CH224K
#        port -- global_nets, not hier_exports: this is a genuine 2-endpoint
#        bus between exactly 02-power and 03-mcu, simpler to declare
#        symmetrically as a global net than to reason about hier_exports
#        parent/child direction for a peer-to-peer link)
#   IO14 SHIFT_SCK   IO15 SHIFT_DATA_OUT   IO18 SHIFT_STROBE (595 STCP AND
#        165 ~PL share this wire -- legitimate double-duty, firmware never
#        needs both phases at once; see the addenda)
#   IO19 PWM_SETPOINT_12V   IO20 CAN_TX   IO21 CAN_RX (hier_exports, joins
#        01-link's TJA1051T/3 at the root)   IO22 PWM_SETPOINT_5V
#   IO23 PWM_SETPOINT_3V3
# FOLLOWUPS.md carries the zero-spare-margin flag (a future feature needing
# one more direct GPIO has no room without trimming an existing one).
#
# SHIFT-REGISTER BIT MAP (32 out / 16 in, see the per-net tables below for
# the exact generated names) -- fits EXACTLY, no spare bit either:
#   595 chain (U9->U10->U11->U12, DS/Q7S cascade): 19 bank-group CTRL bits
#     (12V x6 / 5V x4 / 3V3 x4 / 5VSB x3 / -12V x2, ladder v1.1 counts) +
#     3 SCP arm bits (12V/5V/3V3) + 7 LCD CS bits (main + 6 bay) + 3 CD4051
#     mux-select bits (A/B/C) = 32.
#   165 chain (U13->U14, Q7/DS cascade): 12 trip-detail bits (4 loop + 5
#     bank + 3 SCP) + 3 fan-tach bits + 1 service-button bit = 16.
# Both counts were arrived at by first listing every signal the brief and
# the ladder v1.1 respec actually require, THEN checking it against the
# fixed 32/16 hardware budget -- they fit exactly by construction, not by
# coincidence (see the note() on the sheet for the itemized list).
#
# TRIP_ANY / SCP_FIRE_SHARED / DEGATE_RAIL -- this leaf provides the SHARED
# node (pulldown default + the direct-GPIO tie) but NOT the per-source
# diodes or per-block AND-gates: those are DISTRIBUTED onto the leaves that
# actually own each trip comparator / SCP block (04a-04d, 05a-05e, 06a-06c)
# per the orchestrator's "protection paths never transit the expander"
# review -- declared here as `global_nets` bus members so those leaves can
# tap in when built.
# ===========================================================================
L03 = leaf("03", "03-mcu.kicad_sch", "03-mcu",
           "ESP32-C6-MINI-1-N4 core + shift-register expansion bus (4x "
           "74HC595 / 2x 74HC165 / 2x MM74HC273 trip latches / CD4051 "
           "analog mux) + 4x PWM setpoint RC + fan PWM/tach + NTC dividers "
           "+ bimetal de-gate backstop + BOOT/RESET/service buttons")

FOOTPRINTS.update({
    "U8":  "cec-RF_Module:ESP32-C6-MINI-1",
    "U9":  "cec-tester:SOIC-16_L9.9-W3.9-P1.27-LS6.0-BL",
    "U10": "cec-tester:SOIC-16_L9.9-W3.9-P1.27-LS6.0-BL",
    "U11": "cec-tester:SOIC-16_L9.9-W3.9-P1.27-LS6.0-BL",
    "U12": "cec-tester:SOIC-16_L9.9-W3.9-P1.27-LS6.0-BL",
    "U13": "cec-tester:SOIC-16_L9.9-W3.9-P1.27-LS6.0-BL",
    "U14": "cec-tester:SOIC-16_L9.9-W3.9-P1.27-LS6.0-BL",
    "U15": "cec-tester:SOIC-20_L13.0-W7.6-P1.27-LS10.3-BL",
    "U16": "cec-tester:SOIC-20_L13.0-W7.6-P1.27-LS10.3-BL",
    "U17": "cec-tester:SOIC-16_L9.9-W3.9-P1.27-LS6.0-BL",
    "J4":  "cec-tester:PinHeader_1x04_P2.54mm_Vertical",
    "J5":  "cec-tester:PinHeader_1x04_P2.54mm_Vertical",
    "J6":  "cec-tester:PinHeader_1x04_P2.54mm_Vertical",
    "J7":  "cec-tester:PinHeader_1x04_P2.54mm_Vertical",
})

ap(L03, "U8", "cec-vendor", "ESP32-C6-MINI-1-N4", "ESP32-C6-MINI-1-N4",
   {"Manufacturer": "Espressif", "MPN": "ESP32-C6-MINI-1-N4",
    "Description": "tester core MCU -- 20 GPIO, all committed (see the "
                    "leaf header note)"})
ap(L03, "C40", "cec-vendor", "C_Small", "10u")   # 3V3 bulk
ap(L03, "C41", "cec-vendor", "C_Small", "100n")  # 3V3 bypass
ap(L03, "R40", "cec-vendor", "R_Small", "10k")   # EN pullup
ap(L03, "C42", "cec-vendor", "C_Small", "100n")  # EN cap (reset delay)
ap(L03, "SW3", "cec-vendor", "SW_Push", "TS-1088-AR02016")  # RESET (EN)
ap(L03, "R41", "cec-vendor", "R_Small", "10k")   # BOOT/IO9 pullup
ap(L03, "SW4", "cec-vendor", "SW_Push", "TS-1088-AR02016")  # BOOT (IO9)

for u in ("U9", "U10", "U11", "U12"):
    ap(L03, u, "cec-tester", "74HC595D,118", "74HC595D,118",
       {"Manufacturer": "Nexperia", "MPN": "74HC595D,118", "LCSC": "C5947",
        "Description": "shift-out expander (bank CTRL / SCP arm / LCD CS / "
                        "mux select), cascaded DS->Q7S"})
for u in ("U13", "U14"):
    ap(L03, u, "cec-tester", "74HC165D,653", "74HC165D,653",
       {"Manufacturer": "Nexperia", "MPN": "74HC165D,653", "LCSC": "C5613",
        "Description": "shift-in expander (trip detail / fan tach / "
                        "service button), cascaded Q7->DS"})
for u in ("U15", "U16"):
    ap(L03, u, "cec-tester", "MM74HC273WM", "MM74HC273WM",
       {"Manufacturer": "ON Semi/Fairchild", "MPN": "MM74HC273WM",
        "LCSC": "C906662",
        "Description": "trip-snapshot octal D-latch, D tied HIGH so "
                        "TRIP_ANY's own rising edge self-clocks a permanent "
                        "capture (un-decayed between 165 polls); shared "
                        "async CLEAR is an expander bit"})
ap(L03, "U17", "cec-tester", "CD4051BM96", "CD4051BM96",
   {"Manufacturer": "TI", "MPN": "CD4051BM96", "LCSC": "C21379",
    "Description": "8:1 analog mux, DETECT_SENSE relay + 6 local NTC -> 1 "
                    "ADC channel; 3 select lines on the expander (slow, "
                    "non-critical)"})
for i, u in enumerate(("U9", "U10", "U11", "U12", "U13", "U14", "U15", "U16", "U17")):
    ap(L03, f"C{43+i}", "cec-vendor", "C_Small", "100n")  # per-IC bypass

ap(L03, "R42", "cec-vendor", "R_Small", "10k")   # TRIP_ANY pulldown (default safe/no-trip)
ap(L03, "R43", "cec-vendor", "R_Small", "10k")   # SCP_FIRE_SHARED pulldown (default off)
ap(L03, "R44", "cec-vendor", "R_Small", "10k")   # DEGATE_RAIL pulldown (default no-load)
ap(L03, "R45", "cec-vendor", "R_Small", "10k")   # SHIFT_OE# pullup (default Hi-Z/safe)

for i in range(1, 7):
    ap(L03, f"TH{i}", "cec-vendor", "Thermistor_NTC", "NCP15XH103F03RC",
       {"Manufacturer": "Murata", "MPN": "NCP15XH103F03RC", "LCSC": "C77131"})
    ap(L03, f"R{45+i}", "cec-vendor", "R_Small", "10k")   # NTC divider pulldown

ap(L03, "J4", "cec-tester", "CEC_CONN_1x4", "Fan1")
ap(L03, "J5", "cec-tester", "CEC_CONN_1x4", "Fan2")
ap(L03, "J6", "cec-tester", "CEC_CONN_1x4", "Fan3")
ap(L03, "J7", "cec-tester", "CEC_CONN_1x4", "Bimetal de-gate backstop",
   {"Description": "series loop out to the remote plate-mounted 120C "
                    "bimetal thermal switches (DESIGN-SHEET.md sec 3b/G) -- "
                    "pins 1/2 used (DEGATE_DRIVE out / DEGATE_RAIL return), "
                    "3/4 spare for a second independent loop. ANY open "
                    "switch de-gates regardless of MCU state (R44 pulldown "
                    "makes an open loop -- switch tripped OR header "
                    "unplugged -- read as the safe/no-load default)."})
ap(L03, "SW5", "cec-vendor", "SW_Push", "TS-1088-AR02016")  # service button
ap(L03, "R52", "cec-vendor", "R_Small", "10k")   # service button pullup

for name, val in (("R53", "10k"), ("R54", "10k"), ("R55", "10k"), ("R56", "10k")):
    ap(L03, name, "cec-vendor", "R_Small", val)   # PWM setpoint RC series R
for name in ("C61", "C62", "C63", "C64"):
    ap(L03, name, "cec-vendor", "C_Small", "100n")  # PWM setpoint RC shunt C

L03.net("+3V3", ("U8", C6["3V3"]), ("C40", "1"), ("C41", "1"), ("R40", "1"),
        *[(u, "16") for u in ("U9", "U10", "U11", "U12", "U13", "U14")],
        *[(u, "20") for u in ("U15", "U16")], ("U17", "16"),
        *[(f"C{43+i}", "1") for i in range(9)],
        ("R41", "1"), ("R45", "1"), ("R52", "1"),
        # NTC divider high sides (TH1-TH6 pin1 -> +3V3)
        *[(f"TH{i}", "1") for i in range(1, 7)])
        # MM74HC273 D-inputs are NOT +3V3 members (superseded design fix,
        # see pin-audit-review-2026-07-16.txt addendum 4): 12 read their
        # real TRIP_* source, 4 spare ones are tied GND instead (added to
        # the GND net table below, near the trip-latch stage).
L03.net("GND", ("C40", "2"), ("C41", "2"), ("C42", "2"), ("SW3", "2"),
        ("SW4", "2"),
        *[(u, "8") for u in ("U9", "U10", "U11", "U12", "U13", "U14")],
        *[(u, "10") for u in ("U15", "U16")], ("U17", "8"), ("U17", "7"),
        *[(f"C{43+i}", "2") for i in range(9)],
        ("R42", "1"),   # TRIP_ANY pulldown -- MUST be GND, not +3V3 (default
                         # LOW/no-trip, rising edge on any trip): a copy-paste
                         # slip first put it in the +3V3 list, which would
                         # have made it a pullup and inverted the whole
                         # TRIP_ANY safety convention; caught before layout
                         # left the sheet, not by ERC (both are valid nets,
                         # ERC has no way to know which polarity was intended).
        ("R43", "2"), ("R44", "2"),
        ("J4", "2"), ("J5", "2"), ("J6", "2"), ("SW5", "2"),
        *[(f"TH{i}", "2") for i in range(1, 7)],
        *[(f"R{45+i}", "2") for i in range(1, 7)],
        ("U13", "15"), ("U14", "15"),          # ~CE tied always-enabled
        *[(f"C{61+i}", "2") for i in range(4)],
        *[("U8", p) for p in C6_GND_PINS])
L03.net("EN", ("U8", C6["EN"]), ("R40", "2"), ("C42", "1"), ("SW3", "1"))
L03.net("BOOT_STRAP", ("U8", C6["IO9"]), ("R41", "2"), ("SW4", "1"))

L03.net("ADC_MUX_IN", ("U8", C6["IO0"]), ("U17", "3"))
L03.net("BACKLIGHT_PWM", ("U8", C6["IO2"]))
L03.net("TRIP_ANY", ("U8", C6["IO3"]), ("R42", "2"),
        ("U15", "11"), ("U16", "11"))          # shared CLOCK, both latches
L03.net("SCP_FIRE_SHARED", ("U8", C6["IO4"]), ("R43", "1"))
L03.net("DEGATE_DRIVE", ("U8", C6["IO5"]), ("J7", "1"))
L03.net("DEGATE_RAIL", ("J7", "2"), ("R44", "1"))   # global_nets member (fans out to every hot cluster)
L03.net("SHIFT_OE#", ("U8", C6["IO6"]), ("R45", "2"),
        *[(u, "13") for u in ("U9", "U10", "U11", "U12")])
L03.net("SHIFT_DATA_IN", ("U8", C6["IO7"]), ("U13", "9"))    # last-in-chain 165's Q7
L03.net("FAN_PWM", ("U8", C6["IO8"]), ("J4", "3"), ("J5", "3"), ("J6", "3"))
L03.net("USB_D_N", ("U8", C6["IO12"]))         # global_nets: joins 02-power's J2/U5
L03.net("USB_D_P", ("U8", C6["IO13"]))
L03.net("SHIFT_SCK", ("U8", C6["IO14"]),
        *[(u, "11") for u in ("U9", "U10", "U11", "U12")],
        ("U13", "2"), ("U14", "2"))
L03.net("SHIFT_DATA_OUT", ("U8", C6["IO15"]), ("U9", "14"))
L03.net("SHIFT_STROBE", ("U8", C6["IO18"]),
        *[(u, "12") for u in ("U9", "U10", "U11", "U12")],
        ("U13", "1"), ("U14", "1"))
L03.net("PWM_SETPOINT_12V", ("U8", C6["IO19"]), ("R53", "1"))
L03.net("CAN_TX", ("U8", C6["IO20"]))          # hier_export, joins 01-link
L03.net("CAN_RX", ("U8", C6["IO21"]))
L03.net("PWM_SETPOINT_5V", ("U8", C6["IO22"]), ("R54", "1"))
L03.net("PWM_SETPOINT_3V3", ("U8", C6["IO23"]), ("R55", "1"))
L03.net("PWM_SETPOINT_5VSB", ("U8", C6["IO1"]), ("R56", "1"))

# RC setpoint filters (series R into a shunt C, PWM duty -> analog DC level
# for each loop's OPA2277 setpoint input -- 04a-04d's own leaf reads the
# filtered node by name).
L03.net("SETPOINT_12V", ("R53", "2"), ("C61", "1"))
L03.net("SETPOINT_5V", ("R54", "2"), ("C62", "1"))
L03.net("SETPOINT_3V3", ("R55", "2"), ("C63", "1"))
L03.net("SETPOINT_5VSB", ("R56", "2"), ("C64", "1"))

# 595 cascade (DS -> Q7S chain) + 165 cascade (Q7 -> DS chain)
L03.net("SHIFT595_A_B", ("U9", "9"), ("U10", "14"))
L03.net("SHIFT595_B_C", ("U10", "9"), ("U11", "14"))
L03.net("SHIFT595_C_D", ("U11", "9"), ("U12", "14"))
L03.net("SHIFT165_B_A", ("U14", "9"), ("U13", "10"))
# U13 pin9 (Q7, the near-MCU chip's own serial output) is NOT a separate
# net -- it IS SHIFT_DATA_IN (declared above with the direct-GPIO nets),
# the 165 chain's final output back to the MCU.

# ~MR (595 master reset) tied inactive -- OE# pulled-up already guarantees
# the safe Hi-Z power-up state (see the leaf header note); a hardware MR
# pulse is not needed for that guarantee, so it is simply tied to +3V3
# (real fix: an earlier pass declared this as its OWN isolated net instead
# of actually joining +3V3, leaving all four ~MR pins tied together but
# floating -- an undriven CMOS reset input is a real noise-susceptibility
# risk, not just a cosmetic gap. Found via the exported netlist showing
# "SHIFT_MR_INACTIVE" as a genuinely separate 4-member net with no path to
# any rail at all.)
L03.net("+3V3", *[(u, "10") for u in ("U9", "U10", "U11", "U12")])

# ---- 595 CHAIN A (U9): 19 bank-group CTRL bits + 3 SCP arm bits (22 of 32)
_BANK_GROUPS = (("12V", 6), ("5V", 4), ("3V3", 4), ("5VSB", 3), ("N12V", 2))
_U9_BITS = ["Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]
_U10_BITS = list(_U9_BITS)
_U11_BITS = list(_U9_BITS)
_U12_BITS = list(_U9_BITS)
_PIN_OF = {"Q0": "15", "Q1": "1", "Q2": "2", "Q3": "3", "Q4": "4", "Q5": "5",
           "Q6": "6", "Q7": "7"}
_bank_ctrl_names = []
for rail, n in _BANK_GROUPS:
    for g in range(1, n + 1):
        _bank_ctrl_names.append(f"BANK_{rail}_G{g}_CTRL")
_scp_arm_names = ["SCP_12V_ARM", "SCP_5V_ARM", "SCP_3V3_ARM"]
# LCD_CS_MAIN is NOT a 595 bit (real budget finding, see below): the main
# display is the one SPI device that is always present and sits on its own
# header, not the fanned-out bay-LCD chain -- with nothing else sharing
# that bus it needs no chip-select at all (07-displays hardwires its CS pin
# tied active/GND). That freed exactly the ONE bit CLEAR_SHARED needed: the
# MM74HC273 trip latches' async CLEAR (found missing during 03-mcu capture
# -- both chips' CLEAR pins were floating, undriven, in the first pass) has
# nowhere else to live (all 20 direct GPIOs and, without this trim, all 32
# 595 bits were already committed). CLEAR_SHARED defaults safe the same way
# every other 595 output does: OE# stays pulled up (Hi-Z) until firmware
# has written a known pattern (CLEAR_SHARED inactive-HIGH included) and
# only then asserts OE# -- so an undefined power-up shift-register content
# never actually drives the pin.
_lcd_cs_names = [f"LCD_CS_BAY{i}" for i in range(1, 7)]
_mux_sel_names = ["MUX_SEL_A", "MUX_SEL_B", "MUX_SEL_C"]
_595_BITS = _bank_ctrl_names + _scp_arm_names + _lcd_cs_names + _mux_sel_names + ["CLEAR_SHARED"]
assert len(_595_BITS) == 32, len(_595_BITS)
_595_CHIPS = [("U9", _U9_BITS), ("U10", _U10_BITS), ("U11", _U11_BITS), ("U12", _U12_BITS)]
_bi = 0
for chip, bits in _595_CHIPS:
    for bit in bits:
        L03.net(_595_BITS[_bi], (chip, _PIN_OF[bit]))
        _bi += 1
# CLEAR_SHARED's 595 driver pin was just added above (U12's last bit); add
# the actual consumers -- both MM74HC273 CLEAR pins -- to that same net.
L03.net("CLEAR_SHARED", ("U15", "1"), ("U16", "1"))

# ---- 165 CHAIN (U13/U14): 12 trip-DETAIL (latched, see below) + 3
# fan-tach + 1 service-button (16 of 16)
_165_PIN_OF = {"D0": "11", "D1": "12", "D2": "13", "D3": "14", "D4": "3",
               "D5": "4", "D6": "5", "D7": "6"}
_165_BITS = ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7"]
_trip_detail_names = (
    [f"TRIP_LOOP_{r}" for r in ("12V", "5V", "3V3", "5VSB")] +
    [f"TRIP_BANK_{r}" for r in ("12V", "5V", "3V3", "5VSB", "N12V")] +
    [f"TRIP_SCP_{r}" for r in ("12V", "5V", "3V3")])
assert len(_trip_detail_names) == 12, len(_trip_detail_names)
_fan_tach_names = ["FAN_TACH_1", "FAN_TACH_2", "FAN_TACH_3"]
_165_BIT_NAMES = _trip_detail_names + _fan_tach_names + ["SVC_BUTTON"]
assert len(_165_BIT_NAMES) == 16, len(_165_BIT_NAMES)
_165_CHIPS = [("U14", _165_BITS), ("U13", _165_BITS)]   # U14 = far chip (loaded first), U13 = near chip (closest to MCU)

# ---- MM74HC273 trip-snapshot latch stage -- REAL DESIGN, not the "D tied
# HIGH" placeholder an earlier pass in this same file wrote. Tying every D
# HIGH would make every Q latch HIGH on ANY single trip (CLOCK=TRIP_ANY
# fires for ALL of them at once), destroying the whole point of the
# addendum's own "per-leg detail read via comparator-side LATCHES" design
# -- there would be no way to tell WHICH rail tripped from the latch
# outputs. The correct wiring: each trip source's RAW signal (the 12
# `_trip_detail_names`, global_nets) drives its OWN D-input; TRIP_ANY
# (shared CLOCK) captures ALL 12 D states into their Qs at the instant of
# the FIRST trip; each Q -- the LATCHED value, un-decayed until the shared
# CLEAR -- then feeds the 74HC165 poll chain, LOCALLY (no cross-sheet name
# needed, both chains live on this one leaf). 4 of the 16 D/Q pairs have no
# trip source (12 real signals, 16 hardware bits) -- their D inputs are
# tied GND (never float an unused digital input); their Q outputs are
# genuinely left unconnected (an unused OUTPUT driving nothing is normal,
# not a float risk the way an input is).
_273_DQ = [("3", "2"), ("4", "5"), ("7", "6"), ("8", "9"),
           ("13", "12"), ("14", "15"), ("17", "16"), ("18", "19")]
_273_FLAT = [("U15", d, q) for d, q in _273_DQ] + [("U16", d, q) for d, q in _273_DQ]
_latch_of = {}   # trip name -> (chip165, dpin165) already resolved below
for i, name in enumerate(_trip_detail_names):
    chip273, dpin273, qpin273 = _273_FLAT[i]
    L03.net(name, (chip273, dpin273))            # global_net: raw source -> D
    _latch_of[name] = (chip273, qpin273)          # remember the Q for the 165 wiring
_spare_dq = _273_FLAT[12:]                        # 4 unused D/Q pairs
L03.net("GND",
        *[(chip, d) for chip, d, _q in _spare_dq])   # tie spare D's, not left floating
# (appended to the existing "GND" net table entry above via a second
# L03.net("GND", ...) call -- Leaf.net() appends rather than replacing, see
# its definition in cec_sch_compose.py, so this is additive, not a
# silent overwrite of the earlier, larger GND member list.)

_ti = 0
for chip, bits in _165_CHIPS:
    for bit in bits:
        if chip == "U13" and bit == "D0":
            # SVC_BUTTON is hand-wired to the service button, not left for
            # the generic pass (needs the pullup R52 + SW5 topology drawn).
            L03.net("SVC_BUTTON", ("U13", _165_PIN_OF[bit]), ("SW5", "1"), ("R52", "2"))
        elif _ti < 12:
            # trip-detail bit: read the MM74HC273 Q output, not the raw
            # source directly -- LOCAL net (both ends on this leaf).
            name = _165_BIT_NAMES[_ti]
            chip273, qpin273 = _latch_of[name]
            L03.net(f"{name}_LATCH", (chip273, qpin273), (chip, _165_PIN_OF[bit]))
        else:
            L03.net(_165_BIT_NAMES[_ti], (chip, _165_PIN_OF[bit]))
        _ti += 1

# fan tach inputs (open-collector fan tach pulled up locally at the header;
# each header's TACH pin IS its own net member here)
L03.net("FAN_TACH_1", ("J4", "4"))
L03.net("FAN_TACH_2", ("J5", "4"))
L03.net("FAN_TACH_3", ("J6", "4"))
# +12V_FAN feeds the fan headers' pin1 -- cross-sheet from 02-power
L03.net("+12V_FAN", ("J4", "1"), ("J5", "1"), ("J6", "1"))

# CD4051 8:1 mux channels: 6 local NTC taps (CH0-5) + DETECT_SENSE relayed
# from 01-link (CH6) + 1 spare (CH7, left unconnected on the mux side --
# ~{CH7} is simply never selected by firmware, no netlist entry needed).
_CD4051_CH_PIN = {0: "13", 1: "14", 2: "15", 3: "12", 4: "1", 5: "5", 6: "2"}
for i in range(1, 7):
    L03.net(f"NTC{i}_TAP", (f"R{45+i}", "1"), ("U17", _CD4051_CH_PIN[i - 1]))
L03.net("DETECT_SENSE", ("U17", _CD4051_CH_PIN[6]))   # hier_export from 01-link

L03.hier_exports = {
    "CAN_TX": ("input", ("U8", C6["IO20"])),
    "CAN_RX": ("input", ("U8", C6["IO21"])),
    "DETECT_SENSE": ("input", ("U17", _CD4051_CH_PIN[6])),
}
L03.powerflag_nets = ["+12V_FAN", "+3V3", "GND"]
# +12V_FAN has no on-board Output-Power pin (it is entirely cross-sheet,
# sourced by 02-power's buck1) -- same externally-fed-net class as this
# leaf's other cross-board rails. +3V3/GND ALSO belong here for the same
# reason: this leaf has no local regulator of its own -- +3V3 is 01-link's
# LP5907 output, GND is the RJ-45 jack shell, both arriving purely via
# cross-sheet global-power-symbol name-merging once the root thin-parent
# exists. Root-caused via a real puzzle: ERC flagged exactly ONE
# `power_pin_not_driven` instance each for +3V3 and GND (out of 47 and 77
# same-named members respectively) -- not "these 2 pins are special", but
# ERC reporting ONE representative violation per UNDRIVEN NET, and neither
# net has an Output-Power-typed pin ANYWHERE in this leaf (verified via the
# exported netlist: both nets are fully, correctly merged -- the finding
# was never about connectivity). Exactly the same class 01-link's
# VCC_PROT/02-power's VBUS_C already needed a powerflag for; this leaf is
# just the first one where EVERY rail (not only one) is cross-sheet-only.
L03.global_nets = {"USB_D_P", "USB_D_N", "DEGATE_RAIL", "SCP_FIRE_SHARED",
                    "TRIP_ANY"}
L03.global_nets |= set(_bank_ctrl_names) | set(_scp_arm_names) | \
                    set(_lcd_cs_names) | set(_mux_sel_names) | \
                    set(_trip_detail_names) | {"BACKLIGHT_PWM"}
# every OTHER 595/165 bit + the 4 PWM setpoints + DEGATE_RAIL/SCP_FIRE_
# SHARED/TRIP_ANY are real project-wide buses (the whole point of the
# shared expander): each one's OTHER endpoint lives on a 04-08 leaf not yet
# built. FAN_TACH_*/SVC_BUTTON/SETPOINT_* stay LOCAL to this leaf (no other
# leaf needs them -- tach/button/setpoint-filter are entirely 03-mcu-side;
# 04a-04d read PWM_SETPOINT_* directly, which the leaf's `note()` documents
# still needs those 4 names added to global_nets once 04a-04d exist and
# actually consume them -- tracked in FOLLOWUPS.md).


def compose_03():
    c = _Compose(L03)
    c.place("U8", 140, 140)
    u8 = lambda p: c.pin("U8", p)   # noqa: E731

    # ---- EN (reset) circuit: pullup (pin1 = +3V3, LEFT UNCONSUMED so the
    # generic pass auto-flags it -- this is the fix, not a style choice: an
    # earlier pass wired the MCU pin to R40's pin1 while the net table
    # declared pin1 a +3V3 member, then marked pin1 "consumed" so the auto-
    # flag never fired -- the pullup's actual copper never reached +3V3 at
    # all, EN legs.pin1 = C_Small (undriven except by the button). Caught
    # by re-deriving the exported +3V3 net membership and finding U8/C40/
    # R40/R41 entirely missing from it, not by a top-line ERC message.)
    # + cap + button on the EN node (pin2).
    c.place("R40", 100, 100, 90)
    c.place("C42", 100, 112)
    c.place("SW3", 90, 112)
    en = u8(C6["EN"])
    r40_2 = c.pin("R40", "2")
    c.wire(en, (100, en[1]), (100, r40_2[1]), r40_2)
    c.use((("U8", C6["EN"])), ("R40", "2"))
    c42_1 = c.pin("C42", "1")
    c.wire(r40_2, (r40_2[0], c42_1[1]), c42_1)
    c.use(("C42", "1"))
    # R40 pin1 (+3V3) and SW3 pin1 (EN, same node as r40_2/c42_1) both stay
    # UNCONSUMED for the generic pass -- SW3.1 shares "EN" by net-table
    # membership + auto-label, same technique used throughout this file.

    # ---- BOOT (IO9) strap: pullup (pin1 = +3V3, unconsumed, same fix) +
    # button on the BOOT_STRAP node (pin2).
    c.place("R41", 100, 128, 90)
    c.place("SW4", 90, 136)
    io9 = u8(C6["IO9"])
    r41_2 = c.pin("R41", "2")
    c.wire(io9, (100, io9[1]), (100, r41_2[1]), r41_2)
    c.use((("U8", C6["IO9"])), ("R41", "2"))
    # R41 pin1 (+3V3) and SW4 pin1 (BOOT_STRAP) stay UNCONSUMED.

    # ---- bulk/bypass decoupling at the 3V3 pin -- U8's own 3V3 pin and
    # C40/C41 all stay UNCONSUMED (same fix): each independently auto-flags
    # "+3V3" and merges by shared power-symbol name, exactly like the 9
    # per-IC bypass caps below already do. (No hand-wiring needed here at
    # all -- the earlier hand-wired version was the bug, not a simplification
    # of it.)
    c.place("C40", 100, 150)
    c.place("C41", 100, 158)

    # ---- ADC mux input (IO0 -> CD4051 COM)
    c.place("U17", 260, 260)
    io0 = u8(C6["IO0"])
    u17c = c.pin("U17", "3")
    c.wire(io0, (io0[0], 200), (u17c[0], 200), u17c)
    c.use((("U8", C6["IO0"])), ("U17", "3"))

    # ---- 4x PWM setpoint RC filters (series R off the direct GPIO, shunt C
    # to GND at the filtered node -- 04a-04d's own CC-loop leaf reads
    # SETPOINT_{rail} at its own OPA2277 non-inverting input)
    _pwm_rows = (("R53", "C61", C6["IO19"], 40), ("R54", "C62", C6["IO22"], 48),
                 ("R55", "C63", C6["IO23"], 56), ("R56", "C64", C6["IO1"], 64))
    for rref, cref, pinnum, yoff in _pwm_rows:
        c.place(rref, 40, yoff, 90)
        c.place(cref, 48, yoff + 4)
        gp = u8(pinnum)
        rp1 = c.pin(rref, "1")
        c.wire(gp, (40, gp[1]), (40, rp1[1]), rp1)
        c.use((("U8", pinnum)), (rref, "1"))
        rp2, cp1 = c.pin(rref, "2"), c.pin(cref, "1")
        c.wire(rp2, (cp1[0], rp2[1]), cp1)
        c.use((rref, "2"), (cref, "1"))

    # ---- 74HC595 cascade (bank CTRL / SCP arm / LCD CS / mux select),
    # placed as a row; SCK/STROBE/OE#/MR bussed vertically across all four.
    # Q7S(9) and DS(14) are BOTH on each chip's RIGHT edge (real 74HC595
    # pinout: 9 is bottom-right, 14 is upper-right, only 15/16 above it) --
    # a same-row left-to-right chain therefore can't join them with a
    # straight or single-jog wire (DS never faces the chip to its left).
    # Routed instead via a corridor BELOW the whole row, offset clear of
    # each chip's own right-edge pin column (which would otherwise be
    # passed straight through -- the same class of accidental-short the
    # 01-link/02-power passes already found and fixed).
    _595_x = {"U9": 200, "U10": 240, "U11": 280, "U12": 320}
    for u, x in _595_x.items():
        c.place(u, x, 40)
    for a, b in (("U9", "U10"), ("U10", "U11"), ("U11", "U12")):
        pa, pb = c.pin(a, "9"), c.pin(b, "14")
        cx = pb[0] + 6                          # clear of chip b's own pin column
        c.wire(pa, (pa[0] + 4, pa[1]), (pa[0] + 4, 20), (cx, 20), (cx, pb[1]), pb)
        c.use((a, "9"), (b, "14"))

    # ---- 74HC165 cascade (trip detail / fan tach / service button). Q7(9)
    # is bottom-right, DS(10) is on the RIGHT too (just above Q7) -- same
    # same-edge issue as the 595s, same corridor-detour fix.
    c.place("U14", 200, 90)
    c.place("U13", 280, 90)
    p14q7, p13ds = c.pin("U14", "9"), c.pin("U13", "10")
    cx165 = p13ds[0] + 6
    c.wire(p14q7, (p14q7[0] + 4, p14q7[1]), (p14q7[0] + 4, 110),
           (cx165, 110), (cx165, p13ds[1]), p13ds)
    c.use(("U14", "9"), ("U13", "10"))

    # ---- MM74HC273 trip-snapshot latches. All D/Q/CLEAR pins are left
    # UNCONSUMED (each is a real net member per the tables above -- 12 D's
    # on their own TRIP_* global net, 4 spare D's on GND, 12 Q's on their
    # own local *_LATCH net shared with the matching 165 D-input, CLEAR on
    # CLEAR_SHARED); the generic per-net pass auto-labels every one. (The
    # 4 spare Q's are in NO net at all, by design -- an unused digital
    # OUTPUT driving nothing is a normal, safe end state, unlike a floating
    # input.)
    # (widened from the original 40-unit U15<->U16 gap -- with 8 real
    # trip-source D-pins plus 8 latched Q-pins per chip, each independently
    # auto-labeled at the real 2.54mm IC pin pitch, the tight gap put the
    # two chips' own label clusters and pin-number text on top of each
    # other; cec_sch_layout --check-overlaps.)
    c.place("U15", 200, 140)
    c.place("U16", 280, 140)

    # ---- per-IC bypass caps (C43-C51, one per U9-U17) -- placed just above
    # each chip, left UNCONSUMED (both pins are +3V3/GND net members
    # already, per the leaf's net tables) for the generic per-net pass.
    _bypass_xy = {
        "C43": (200, 26), "C44": (240, 26), "C45": (280, 26), "C46": (320, 26),
        "C47": (280, 76), "C48": (200, 76),
        "C49": (200, 126), "C50": (280, 126),
        "C51": (272, 246),
    }
    for cref, (x, y) in _bypass_xy.items():
        c.place(cref, x, y)

    # ---- direct-GPIO pulldown/pullup quartet (TRIP_ANY / SCP_FIRE_SHARED /
    # DEGATE_RAIL / SHIFT_OE#) -- placed near the ESP32's own left-side pin
    # column since all four originate there; each is a 2-member net already
    # (signal + rail) so no further hand-wiring is needed beyond placement.
    c.place("R42", 40, 180, 90)
    c.place("R43", 40, 188, 90)
    c.place("R44", 40, 196, 90)
    c.place("R45", 40, 204, 90)

    # ---- fan headers x3 + bimetal de-gate backstop header
    # (moved well clear of the 595 row -- the original y=40 placement put
    # J4-J6's own 4-pin label cluster directly on top of U10/U11/U12's own
    # SHCP/STCP/DS pin text, cec_sch_layout --check-overlaps caught it)
    c.place("J4", 40, 300)
    c.place("J5", 80, 300)
    c.place("J6", 120, 300)
    c.place("J7", 40, 220)

    # ---- service button (pulls SVC_BUTTON, the 165 D0 bit, low on press;
    # R52 pullup already placed with the other direct-signal pulldown/
    # pullup quartet's net membership pattern)
    c.place("SW5", 40, 212)
    c.place("R52", 48, 212, 90)

    # ---- NTC dividers (+3V3 -> TH -> node(->CD4051 channel) -> R -> GND)
    for i in range(1, 7):
        x = 260 + (i - 1) * 14
        thref, rref = f"TH{i}", f"R{45+i}"
        c.place(thref, x, 200, 90)
        c.place(rref, x, 216, 90)
        th1, th2 = c.pin(thref, "1"), c.pin(thref, "2")
        r1 = c.pin(rref, "1")
        c.stamp("+3V3", th1[0], th1[1], 90)
        c.use((thref, "1"))
        c.wire(th2, (th2[0], r1[1]), r1)
        c.use((thref, "2"), (rref, "1"))

    c.caption(L03.desc, 6, 8)
    c.note(
        "GPIO map, shift-register bit map, and the real findings made "
        "DURING capture (not just planned in advance) are in this file's "
        "own header comment above compose_03() and in pin-audit-review-"
        "2026-07-16.txt addendum 4: the 5VSB setpoint upgrade + 165 having "
        "no tri-state (needs a separate DATA_IN line) used up the last "
        "spare GPIO; the MM74HC273 D-inputs were first captured tied HIGH "
        "(would have made every latch fire identically on ANY trip, "
        "destroying the whole point of per-source detail) and the CLEAR "
        "pins were found entirely unwired -- fixed by reading the real "
        "trip source into each D, the matching Q into the 165 chain, and "
        "trimming LCD_CS_MAIN (the main display has no bus-mate, needs no "
        "chip-select bit at all -- 07-displays hardwires it) to free the "
        "one CLEAR_SHARED bit. 595 chain A order (U9->U10->U11->U12): 19 "
        "bank-group CTRL (12V G1-6, 5V G1-4, 3V3 G1-4, 5VSB G1-3, -12V "
        "G1-2), 3 SCP arm (12V/5V/3V3), 6 bay LCD CS, 3 CD4051 mux-select "
        "(A/B/C), 1 CLEAR_SHARED (MM74HC273 async clear). 165 chain (U14 "
        "far -> U13 near-MCU): 12 trip-detail (4 loop + 5 bank + 3 SCP, "
        "each reading its MM74HC273 Q, not the raw source), 3 fan tach, 1 "
        "service button. All 595/165/MM74HC273 data pins except the "
        "cascade taps and the service button are left UNCONSUMED for the "
        "generic per-net pass (matches 01/02's proven-safer philosophy) -- "
        "each net name is listed in the GENERATOR SOURCE, not hand-typed "
        "here, to guarantee the sheet and the bit-count assertions in "
        "scripts/check_tester_st_sch.py never drift apart. TRIP_ANY / "
        "SCP_FIRE_SHARED / DEGATE_RAIL: this sheet provides the shared "
        "node only (pulldown default + the direct-GPIO "
        "tie) -- the per-source diodes / per-block AND-gates live on the "
        "leaf that owns each trip comparator or SCP block, never on the "
        "expander (orchestrator safety review, addendum 2).", 6, 420)
    c.done()


# ===========================================================================
# 04 -- CC loops (12V / 5V / 3V3 / 5VSB), ONE template function building all
# 4 files (repeated-leaf convention, matching hub-enterprise's compose_port()
# / leaf05() pattern -- see that file's own module note). Split-architecture
# readiness (this file's header, mid-flight owner directive 2026-07-16): a
# keyed CEC_CONN_1x8 harness-boundary connector carries GND / +3V3 /
# DEGATE_RAIL / PWM_SETPOINT_{rail} in, and this loop's own TRIP_LOOP_{rail}
# out; the op-amp CC loop, Kelvin shunt, and trip-watch stay entirely on the
# hot side, per the connector.
#
# CELL (identical shape across all 4 -- differs only in FET part/count and
# whether a ballast resistor is needed for paralleled devices):
#   PWM_SETPOINT_{rail} (global, RAW pre-filter PWM off 03-mcu's own IO19/
#     22/23/1) AND DEGATE_RAIL (global, the bimetal dead-man rail) feed a
#     local SN74AHCT1G08 2-input AND (U_AND) -- de-gate qualifies the PWM
#     BEFORE it is filtered to an analog level, so an unplugged harness or a
#     tripped bimetal forces 0% duty -> a genuine 0V reference, not just an
#     unplugged pull-down fighting an actively-driven op-amp output. A local
#     RC (R_SP/C_SP, 10k/100n) then filters the qualified PWM into an
#     analog SETPOINT node.
#   OPA2277UA channel A (channel B intentionally left NC, Phase-A engine-
#     limit note): INA+ <- SETPOINT; INA- <- the shunt's HI terminal
#     (classic e-load feedback: the shunt's own I*R IS the regulated
#     quantity); OUTA -> R_GATE (series, Gate netclass) -> the FET gate(s);
#     a local comp cap (C_COMP) ties OUTA back to INA- for loop stability;
#     R_PD is a hard gate-to-GND pulldown at every FET gate (DESIGN-SHEET
#     C.10 "gate pull-down at the gate pin"), independent of DEGATE_RAIL,
#     so an unpowered/disconnected op-amp still leaves the gate defined.
#   RAIL_{rail} (global, the DUT's own rail under test, sourced by
#     08-deck-io) -> FET drain(s) -> source(s) [-> ballast R, 04a's 2x
#     paralleled verniers only, DESIGN-SHEET C.10 current-share] -> the
#     loop's own Kelvin shunt (R_Small on the R_2512 land, Kelvin taps in
#     copper at layout -- the platform's DOMINANT convention per EPS/PCIe/
#     24-pin RS1-3, not the rarer 24-pin RS4 4-terminal CEC_SHUNT_4T
#     exception; see the leaf's own note()) -> GND.
#   Trip-watch: the SAME shunt feeds an INA181A2IDBVR (gain 50, platform
#     sec6.13 CSA) -> TLV7011DBVR hysteresis comparator vs a LOCAL FIXED
#     R-divider threshold (R_TH1/R_TH2, +3V3/2) -- there is no spare GPIO
#     for a firmware-programmable PWM threshold DAC the way the platform's
#     per-cable MODULE sec6.13 cell gets one (04-08's fixed pin/bit budget,
#     HARD CONSTRAINT) -- flagged as a known simplification vs. the module
#     precedent, [wb] bench-calibrate the divider ratio. Comparator OUT ->
#     TRIP_LOOP_{rail} (global, lands on 03-mcu's MM74HC273 D-input) AND a
#     local diode (anode on TRIP_LOOP_{rail}, cathode on TRIP_ANY) ORs it
#     into the shared TRIP_ANY node -- the orchestrator's addendum-2 rule
#     ("per-source diodes live on the leaf that owns the comparator, never
#     the expander").
#
# NOTE on cross-leaf wiring: PWM_SETPOINT_{rail}, DEGATE_RAIL, TRIP_LOOP_
# {rail}, TRIP_ANY, and RAIL_{rail} are all GLOBAL nets (real KiCad
# global_label, project-wide-by-name -- see cec_sch.emit_global_label /
# cec_sch_compose.build_leaf's global_nets param). PWM_SETPOINT_* was added
# to 03-mcu's OWN global_nets set at the root-assembly pass (a genuine two-
# sided touch this file's header + pin-audit-review-2026-07-16.txt addendum
# 7 both call out) so this leaf's stub actually binds to 03-mcu's
# already-placed pin; RAIL_* is sourced by 08-deck-io (also built at this
# pass). +3V3/GND are platform POWER_PORTS (auto-global via power symbols,
# no global_nets bookkeeping needed at all).
# ===========================================================================
_LOOP_RAILS = [
    ("04a", "04a-loop-12v", "12V", ["IXTH75N10L2", "IXTH75N10L2"], True),
    ("04b", "04b-loop-5v", "5V", ["IRLZ44N"], False),
    ("04c", "04c-loop-3v3", "3V3", ["IRLZ44N"], False),
    ("04d", "04d-loop-5vsb", "5VSB", ["IRLZ44N"], False),
]


def compose_04(rid, fid, rail, fets, ballast):
    n = len(fets)
    lf = leaf(rid, f"{fid}.kicad_sch", fid,
              f"CC loop, {rail} rail -- OPA2277 + {n}x {fets[0]} + Kelvin "
              "shunt + INA181/TLV7011 trip-watch; CEC_CONN_1x8 harness-"
              "boundary connector (split-arch readiness)")
    J = nref("J")
    U_AND = nref("U")
    R_SP, C_SP = nref("R"), nref("C")
    U_OP = nref("U")
    C_OPB = nref("C")
    R_GATE = nref("R")
    R_PD = nref("R")
    C_COMP = nref("C")
    fet_refs = [nref("Q") for _ in fets]
    ballast_refs = [nref("R") for _ in fets] if ballast else []
    RS = nref("R")
    U_INA, U_CMP = nref("U"), nref("U")
    C_INA, C_CMP = nref("C"), nref("C")
    R_TH1, R_TH2 = nref("R"), nref("R")
    D_OR = nref("D")

    ap(lf, J, "cec-tester", "CEC_CONN_1x8", "J_HARN",
       {"Description": f"Harness-boundary connector (split-arch readiness): "
                        f"1=GND 2=+3V3 3=DEGATE_RAIL 4=PWM_SETPOINT_{rail}"
                        f"(in) 5=TRIP_LOOP_{rail}(out) 6-8=spare. [wb] real "
                        "keyed-connector class/MPN pending split-arch "
                        "ratification (README.md)"})
    ap(lf, U_AND, "cec-vendor", "SN74AHCT1G08", "SN74AHCT1G08",
       {"Manufacturer": "Texas Instruments", "MPN": "SN74AHCT1G08DBVR",
        "Description": f"AND(PWM_SETPOINT_{rail}, DEGATE_RAIL) -- de-gate "
                        "qualifier ahead of the RC setpoint filter (this "
                        "loop's own de-gate mechanism: a REGULATED-to-zero "
                        "soft-kill, since the FET is analog-driven, not a "
                        "hard clamp like the bank/SCP AND-cells -- R_PD's "
                        "gate pulldown is the hard backup). Same platform "
                        "part Hub-Standard uses as an LED level-shift "
                        "buffer, reused here with two genuinely different "
                        "inputs."})
    ap(lf, R_SP, "cec-vendor", "R_Small", "10k")
    ap(lf, C_SP, "cec-vendor", "C_Small", "100n")
    ap(lf, U_OP, "cec-tester", "OPA2277UA", "OPA2277UA-2K5",
       {"Manufacturer": "Texas Instruments", "MPN": "OPA2277UA-2K5", "LCSC": "C24460",
        "Description": "CC loop error amp, channel A only (channel B "
                        "intentionally NC, Phase-A engine-limit note)"})
    ap(lf, C_OPB, "cec-vendor", "C_Small", "100n")
    ap(lf, R_GATE, "cec-vendor", "R_Small", "100",
       {"Description": "Gate-class series R at the driver end (DESIGN-SHEET "
                        "sec D) [wb value]"})
    ap(lf, R_PD, "cec-vendor", "R_Small", "10k",
       {"Description": "hard gate-to-GND pulldown, independent of DEGATE_"
                        "RAIL (DESIGN-SHEET C.10 'gate pull-down at the "
                        "gate pin')"})
    ap(lf, C_COMP, "cec-vendor", "C_Small", "1n",
       {"Description": "loop dominant-pole compensation (OUTA -> INA-) "
                        "[wb value, bench-tune]"})
    for i, fref in enumerate(fet_refs):
        ap(lf, fref, "cec-tester", fets[i], fets[i],
           {"Description": f"CC loop pass FET {i + 1}/{n}" +
                           (" -- Linear-L2 vernier (TO-247)" if fets[i] == "IXTH75N10L2"
                            else " -- logic-level TO-220 (rule 25(b) packaging corollary)")})
    if ballast:
        for bref in ballast_refs:
            ap(lf, bref, "cec-vendor", "R_Small", "0R1",
               {"Description": "source-degeneration ballast, current-share "
                                "across paralleled verniers (DESIGN-SHEET "
                                "C.10, Array 3711A precedent) [wb value]"})
    ap(lf, RS, "cec-vendor", "R_Small", "1m",
       {"Manufacturer": "Bourns", "MPN": "CSS2H-2512R-1L00F", "LCSC": "C4175647",
        "Description": f"{rail} loop Kelvin shunt -- honest 2-pad R_2512 "
                        "land, Kelvin taps in copper at layout (platform's "
                        "DOMINANT shunt convention: EPS/PCIe/24-pin RS1-3 -- "
                        "NOT the rarer 24-pin RS4 4-terminal CEC_SHUNT_4T "
                        "exception, which would need a genuine Vishay "
                        "WSK2512-family MPN, not this Bourns 2-terminal "
                        "part)"})
    ap(lf, U_INA, "cec-vendor", "INA181A2IDBVR", "INA181A2IDBVR",
       {"Manufacturer": "Texas Instruments", "MPN": "INA181A2IDBVR", "LCSC": "C2058784",
        "Description": "trip-watch CSA, gain 50 (platform sec6.13 pattern)"})
    ap(lf, C_INA, "cec-vendor", "C_Small", "100n")
    ap(lf, U_CMP, "cec-vendor", "TLV7011DBVR", "TLV7011DBVR",
       {"Manufacturer": "Texas Instruments", "MPN": "TLV7011DBVR", "LCSC": "C702117",
        "Description": "trip-watch hysteresis comparator vs a LOCAL fixed "
                        "threshold divider -- no spare GPIO for a firmware "
                        "PWM threshold DAC (unlike the platform per-cable "
                        "module precedent); [wb] bench-calibrate R_TH1/"
                        "R_TH2's ratio"})
    ap(lf, C_CMP, "cec-vendor", "C_Small", "100n")
    ap(lf, R_TH1, "cec-vendor", "R_Small", "10k")
    ap(lf, R_TH2, "cec-vendor", "R_Small", "10k")
    ap(lf, D_OR, "cec-vendor", "D_Schottky", "SS34",
       {"Description": f"diode-ORs this loop's own TRIP_LOOP_{rail} into "
                        "the shared TRIP_ANY node (orchestrator safety "
                        "review addendum 2 -- per-source diodes live on "
                        "the leaf that owns the comparator, never the "
                        "expander). Pin1=K(cathode)->TRIP_ANY, "
                        f"pin2=A(anode)<-TRIP_LOOP_{rail} -- verified vs "
                        "the real cec-vendor D_Schottky symbol body per "
                        "the addendum-4 lesson (never assume pin1=A)."})

    hi = f"{rail}_LOOP_HI"        # local: shunt HI / opamp feedback / INA IN+
    gate_n = f"{rail}_LOOP_GATE"  # local: op-amp OUTA -> R_GATE -> FET gate(s)
    sp_gated = f"{rail}_SP_GATED"  # local: AND output (qualified PWM)
    sp = f"{rail}_SETPOINT"        # local: RC-filtered analog setpoint
    detamp = f"{rail}_DETAMP"      # local: INA181 OUT -> comparator IN+
    thresh = f"{rail}_THRESH"      # local: fixed threshold divider tap
    trip = f"TRIP_LOOP_{rail}"     # GLOBAL: raw comparator output

    # NOTE (real bug, caught by netlist re-derivation, same class as the
    # pin-audit log's addendum-4 lesson): U_INA pin4 (IN-) was FIRST omitted
    # from this net table entirely -- the exported netlist showed
    # "unconnected-(U102-IN--Pad4)", a genuinely floating differential input
    # on the trip-watch CSA (undefined/noisy amplifier behavior, not just a
    # cosmetic gap). Fixed: IN- ties to GND, matching the platform's own
    # sec6.13 INA181 precedent (gen-modules.py: SENSE_LO -> amp pin 4) --
    # this design's shunt LO terminal is itself GND-referenced (2-terminal
    # R_2512 land, Kelvin-in-copper), so IN- reads the same GND node.
    lf.net("GND", (J, "1"), (U_AND, "3"), (C_SP, "2"), (U_OP, "4"),
           (C_OPB, "2"), (R_PD, "2"), (RS, "2"), (U_INA, "2"), (U_INA, "4"),
           (U_INA, "5"), (C_INA, "2"), (U_CMP, "2"), (C_CMP, "2"), (R_TH2, "2"))
    lf.net("+3V3", (J, "2"), (U_AND, "5"), (U_OP, "8"), (C_OPB, "1"),
           (U_INA, "6"), (C_INA, "1"), (U_CMP, "5"), (C_CMP, "1"), (R_TH1, "1"))
    lf.net("DEGATE_RAIL", (J, "3"), (U_AND, "2"))
    lf.net(f"PWM_SETPOINT_{rail}", (J, "4"), (U_AND, "1"))
    lf.net(sp_gated, (U_AND, "4"), (R_SP, "1"))
    lf.net(sp, (R_SP, "2"), (C_SP, "1"), (U_OP, "3"))
    # FET pin numbers (verified against every promoted symbol -- AOD4184A/
    # IRLB3034/IRLZ44N/IXTH75N10L2 all share the standard TO-220/247/252
    # 3-pin numbering 1=G 2=D 3=S; using the NAME string here instead of the
    # NUMBER raised a real KeyError in cec_sch_layout.pin_abs_rot (pin
    # tables are keyed by number, not name -- caught by the very first
    # generator run, before any gate).
    lf.net(hi, (RS, "1"), (U_OP, "2"), (U_INA, "3"), (C_COMP, "2"),
           *([(b, "2") for b in ballast_refs] if ballast
             else [(fet_refs[0], "3")]))
    lf.net("RAIL_" + rail, *[(f_, "2") for f_ in fet_refs])
    lf.net(gate_n, (U_OP, "1"), (R_GATE, "1"), (C_COMP, "1"))
    lf.net(f"{rail}_GATE_DRIVE", (R_GATE, "2"), (R_PD, "1"),
           *[(f_, "1") for f_ in fet_refs])
    lf.net(detamp, (U_INA, "1"), (U_CMP, "3"))
    lf.net(thresh, (R_TH1, "2"), (R_TH2, "1"), (U_CMP, "4"))
    lf.net(trip, (U_CMP, "1"), (J, "5"), (D_OR, "2"))
    lf.net("TRIP_ANY", (D_OR, "1"))
    if ballast:
        for i, f_ in enumerate(fet_refs):
            lf.net(f"{rail}_BALLAST{i}", (f_, "3"), (ballast_refs[i], "1"))

    lf.hier_exports = {}
    lf.global_nets = {f"PWM_SETPOINT_{rail}", "DEGATE_RAIL", trip, "TRIP_ANY",
                       "RAIL_" + rail}
    # this leaf has NO local regulator (like 03-mcu): +3V3 is 01-link's LDO
    # output, GND is the RJ-45 shell, both purely cross-sheet -- same
    # externally-fed-net class 03-mcu's own +3V3/GND powerflag_nets entry
    # documents (ERC power_pin_not_driven, one representative hit per net).
    lf.powerflag_nets = ["GND", "+3V3"]

    def _compose():
        c = _Compose(lf)
        c.place(J, 20, 60)
        c.place(U_AND, 60, 40)
        c.place(R_SP, 90, 40, 90)
        c.place(C_SP, 100, 50)
        c.place(U_OP, 135, 60)
        c.place(C_OPB, 135, 40)
        c.place(R_GATE, 170, 52, 90)
        c.place(R_PD, 170, 70, 90)
        c.place(C_COMP, 155, 84)
        fx0 = 200
        fx_pitch = 44
        for i, f_ in enumerate(fet_refs):
            c.place(f_, fx0 + i * fx_pitch, 60, 90)
        if ballast:
            for i, b in enumerate(ballast_refs):
                c.place(b, fx0 + i * fx_pitch, 88, 90)
        c.place(RS, fx0 + (n - 1) * fx_pitch // 2 + 15, 112)
        c.place(U_INA, 200, 140)
        c.place(C_INA, 200, 126)
        c.place(U_CMP, 232, 140)
        c.place(C_CMP, 232, 126)
        c.place(R_TH1, 254, 132, 90)
        c.place(R_TH2, 254, 150, 90)
        c.place(D_OR, 254, 162, 270)

        # ---- AND -> RC filter -> op-amp setpoint chain: hand-wired (not
        # left for the generic per-net pass) so the 2/3-member local nets
        # each get ONE visible run instead of 2-3 independent auto-labels
        # landing close enough on the SAME leaf to collide (measured:
        # cec_sch_layout --check-overlaps caught "{rail}_SP_GATED"/
        # "{rail}_SETPOINT" self-collisions on the first pass -- both nets'
        # members sit close together at this leaf's compact scale).
        a4 = c.pin(U_AND, "4")
        r1 = c.pin(R_SP, "1")
        c.wire(a4, (a4[0] + 3, a4[1]), (a4[0] + 3, r1[1]), r1)
        c.use((U_AND, "4"), (R_SP, "1"))
        # explicit label at the mid-run corner: both endpoints of this net
        # are now hand-consumed, so without an explicit label the exported
        # netlist would show only KiCad's own auto-derived name (the SAME
        # class of cosmetic gap the pin-audit log's addendum 4 already
        # documents for 02-power's D6/+12V_AUX_RAW run) instead of the
        # intended sp_gated name this leaf's own note()/checker reference.
        c.label(sp_gated, a4[0] + 3, a4[1], 90)
        r2 = c.pin(R_SP, "2")
        cs1 = c.pin(C_SP, "1")
        op3 = c.pin(U_OP, "3")
        # single T: r2 -> tap (at C_SP's x) -> drop to C_SP.1; tap -> continue
        # right to U_OP.3 -- avoids drawing two overlapping horizontal runs
        # from the same start point (both reaching a shared row).
        tap = (cs1[0], r2[1])
        c.wire(r2, tap)
        c.wire(tap, cs1)
        c.wire(tap, (op3[0], r2[1]), op3)
        c.use((R_SP, "2"), (C_SP, "1"), (U_OP, "3"))
        c.label(sp, tap[0], tap[1], 90)

        c.caption(lf.desc, 6, 8)
        c.note(
            f"{rail} CC loop. Harness-boundary CEC_CONN_1x8 (split-arch "
            "readiness, README.md): pins 1-5 real, 6-8 spare. De-gate is a "
            "REGULATED-to-zero soft-kill (AND on the RAW pre-filter PWM, "
            "before the RC) backed by R_PD's hard gate pulldown. Shunt "
            "Kelvin taps are a PCB-layout-time concern (R_2512 land, "
            "platform's dominant 2-terminal shunt convention). Trip "
            "threshold is a LOCAL FIXED divider (R_TH1/R_TH2), not a "
            "firmware PWM DAC -- 03-mcu's fixed pin/bit budget has no "
            "spare channel for one (HARD CONSTRAINT); [wb] bench-"
            "calibrate. TRIP_LOOP_" + rail + " diode-ORs into the shared "
            "TRIP_ANY node (orchestrator addendum 2).", 6, 170)
        c.done()

    return lf, _compose


LOOP_LEAVES = {}
for _rid, _fid, _rail, _fets, _ballast in _LOOP_RAILS:
    _lf, _fn = compose_04(_rid, _fid, _rail, _fets, _ballast)
    LOOP_LEAVES[_rid] = (_lf, _fid, _fn)


# ===========================================================================
# 05 -- R-banks, LADDER v1.1 [wb] (README.md "R-bank ladder proposal v1.1" --
# pending owner nod, marked [wb] on every caption per the build order). ONE
# template function building all 5 rail leaves. Per group (NOT per leg,
# DESIGN-SHEET C.12): AOD4184A low-side switch, sized-on-TIME 3557-10 ATOF
# fuse UPSTREAM of the FET, and a local SN74AHCT1G08 AND(BANK_{rail}_G{g}_
# CTRL, DEGATE_RAIL) gate driver (VCC=+5V_LOGIC -- unlike the loops' +3V3
# AND-cell, this one drives a POWER FET gate directly, so the higher rail
# gives better RDS(on); see the addendum). Trip-watch is SHARED PER RAIL,
# not per group (see the addendum's "trip-watch granularity" note) -- one
# Kelvin shunt in the common FET-source return bus, one INA181+TLV7011
# cell, exactly matching 03-mcu's committed TRIP_BANK_{rail} budget (one
# bit per rail, five total). ST-1000 BASELINE LEG COUNTS drawn (32/8/8/4/2
# = 54 legs); the ST-1300 population variant (+12 legs in 12V's group 6,
# 16->28, "never in copper" per README) is NOT physically drawn this pass
# -- documented, deferred population-only extension (see the addendum).
# ===========================================================================
_BANK_RAILS = [
    ("05a", "05a-bank-12v", "12V", [1, 1, 2, 4, 8, 16], "6R0"),
    ("05b", "05b-bank-5v", "5V", [1, 1, 2, 4], "1R0"),
    ("05c", "05c-bank-3v3", "3V3", [1, 1, 2, 4], "0R68"),
    ("05d", "05d-bank-5vsb", "5VSB", [1, 1, 2], "3R3"),
    ("05e", "05e-bank-n12v", "N12V", [1, 1], "47"),
]


def compose_05(rid, fid, rail, groups, leg_value):
    ng = len(groups)
    total_legs = sum(groups)
    lf = leaf(rid, f"{fid}.kicad_sch", fid,
              f"R-bank, {rail} rail -- LADDER v1.1 [wb]: {ng} groups "
              f"({'+'.join(str(g) for g in groups)} legs, {total_legs} "
              f"total, {leg_value} each) x AOD4184A+3557-10 fuse+local "
              "AND gate driver, shared Kelvin shunt + INA181/TLV7011 "
              "trip-watch per rail; CEC_CONN harness-boundary connector")

    # harness pins: GND, +3V3, DEGATE_RAIL, one CTRL per group, TRIP_OUT
    n_harn = 3 + ng + 1
    harn_kind = "CEC_CONN_1x12" if n_harn > 8 else "CEC_CONN_1x8"
    J = nref("J")
    ctrl_names = [f"BANK_{rail}_G{g}_CTRL" for g in range(1, ng + 1)]
    trip = f"TRIP_BANK_{rail}"

    ap(lf, J, "cec-tester", harn_kind, "J_HARN",
       {"Description": f"Harness-boundary connector (split-arch readiness): "
                        f"1=GND 2=+3V3 3=DEGATE_RAIL 4..{3 + ng}="
                        f"{','.join(ctrl_names)}(in) {4 + ng}={trip}(out) "
                        f"{5 + ng}..{'12' if harn_kind.endswith('12') else '8'}"
                        "=spare. [wb] real keyed-connector class/MPN pending "
                        "split-arch ratification"})

    # per-group parts + local wiring
    fet_refs, fuse_refs, and_refs, gr_refs, pd_refs = [], [], [], [], []
    leg_refs_by_group = []
    for gi, count in enumerate(groups):
        gnum = gi + 1
        legs = []
        for _ in range(count):
            r = nref("R")
            ap(lf, r, "cec-vendor", "R_Small", leg_value,
               {"Manufacturer": "[wb]", "MPN": "HoRX-50W-class [wb exact "
                                                "LCSC line pending BOM lock]",
                "Description": f"{rail} bank leg, group {gnum} -- chassis-"
                                "mounted, off-board (DESIGN-SHEET 22b "
                                "wall-cartridge form); this pad is the "
                                "wire-lug landing, not the resistor body"})
            FOOTPRINTS[r] = "cec-tester:HoRX_50W_WireLug_2Pin"
            legs.append(r)
        leg_refs_by_group.append(legs)
        f_ = nref("F")
        ap(lf, f_, "cec-tester", "3557-10", f"ATOF-[wb]",
           {"Manufacturer": "Keystone", "MPN": "3557-10", "LCSC": "C3205403",
            "Description": f"group {gnum} ATOF fuse holder, sized on TIME "
                            "(carries the ms-scale test surge, blows on "
                            "seconds-scale cook) -- UPSTREAM of the FET "
                            "(DESIGN-SHEET C.12); [wb] exact amperage per "
                            "group current"})
        fuse_refs.append(f_)
        q = nref("Q")
        ap(lf, q, "cec-tester", "AOD4184A", "AOD4184A",
           {"Manufacturer": "Alpha & Omega", "MPN": "AOD4184A", "LCSC": "C99124",
            "Description": f"group {gnum} low-side bank switch"})
        fet_refs.append(q)
        u = nref("U")
        ap(lf, u, "cec-vendor", "SN74AHCT1G08", "SN74AHCT1G08",
           {"Manufacturer": "Texas Instruments", "MPN": "SN74AHCT1G08DBVR",
            "Description": f"AND(BANK_{rail}_G{gnum}_CTRL, DEGATE_RAIL) -- "
                            "hard gate qualifier + level-shift-up-to-5V "
                            "drive in one part (VCC=+5V_LOGIC, unlike the "
                            "loops' +3V3 AND-cell -- this output drives a "
                            "power FET gate directly)"})
        and_refs.append(u)
        gr = nref("R")
        ap(lf, gr, "cec-vendor", "R_Small", "100",
           {"Description": "Gate-class series R at the driver end [wb value]"})
        gr_refs.append(gr)
        pd = nref("R")
        ap(lf, pd, "cec-vendor", "R_Small", "10k",
           {"Description": "hard gate-to-GND pulldown, independent of "
                            "DEGATE_RAIL (DESIGN-SHEET C.10 pattern, "
                            "applied here to the bank switch FET)"})
        pd_refs.append(pd)

    RS = nref("R")
    ap(lf, RS, "cec-vendor", "R_Small", "1m",
       {"Manufacturer": "Bourns", "MPN": "CSS2H-2512R-1L00F", "LCSC": "C4175647",
        "Description": f"{rail} bank RAIL-LEVEL Kelvin shunt (shared "
                        "across all groups' common FET-source return -- "
                        "trip-watch granularity is per-RAIL not per-GROUP, "
                        "matching 03-mcu's committed 1-bit-per-rail TRIP_"
                        "BANK budget; per-group fusing is the real per-leg "
                        "protection element, see the addendum). Honest "
                        "2-pad R_2512 land, same platform-dominant "
                        "convention as the CC loops."})
    U_INA, U_CMP = nref("U"), nref("U")
    C_INA, C_CMP = nref("C"), nref("C")
    R_TH1, R_TH2 = nref("R"), nref("R")
    D_OR = nref("D")
    ap(lf, U_INA, "cec-vendor", "INA181A2IDBVR", "INA181A2IDBVR",
       {"Manufacturer": "Texas Instruments", "MPN": "INA181A2IDBVR", "LCSC": "C2058784",
        "Description": "rail trip-watch CSA, gain 50 (platform sec6.13 pattern)"})
    ap(lf, C_INA, "cec-vendor", "C_Small", "100n")
    ap(lf, U_CMP, "cec-vendor", "TLV7011DBVR", "TLV7011DBVR",
       {"Manufacturer": "Texas Instruments", "MPN": "TLV7011DBVR", "LCSC": "C702117",
        "Description": "rail trip-watch comparator vs a LOCAL fixed "
                        "threshold divider; [wb] bench-calibrate"})
    ap(lf, C_CMP, "cec-vendor", "C_Small", "100n")
    ap(lf, R_TH1, "cec-vendor", "R_Small", "10k")
    ap(lf, R_TH2, "cec-vendor", "R_Small", "10k")
    ap(lf, D_OR, "cec-vendor", "D_Schottky", "SS34",
       {"Description": f"diode-ORs this rail's own {trip} into the shared "
                        "TRIP_ANY node (orchestrator addendum 2). "
                        "Pin1=K(cathode)->TRIP_ANY, pin2=A(anode)<-"
                        f"{trip} -- verified vs the real symbol body per "
                        "the addendum-4 lesson."})

    ret = f"{rail}_BANK_RETURN"
    detamp = f"{rail}_BANK_DETAMP"
    thresh = f"{rail}_BANK_THRESH"

    lf.net("GND", (J, "1"), (RS, "2"), (U_INA, "2"), (U_INA, "4"), (U_INA, "5"),
           (C_INA, "2"), (U_CMP, "2"), (C_CMP, "2"), (R_TH2, "2"),
           *[(u, "3") for u in and_refs], *[(pd, "2") for pd in pd_refs])
    lf.net("+3V3", (J, "2"), (U_INA, "6"), (C_INA, "1"), (U_CMP, "5"),
           (C_CMP, "1"), (R_TH1, "1"))
    lf.net("+5V_LOGIC", *[(u, "5") for u in and_refs])
    lf.net("DEGATE_RAIL", (J, "3"), *[(u, "2") for u in and_refs])
    for gi in range(ng):
        lf.net(ctrl_names[gi], (J, str(4 + gi)), (and_refs[gi], "1"))
    lf.net(ret, (RS, "1"), (U_INA, "3"), *[(q, "3") for q in fet_refs])
    lf.net(detamp, (U_INA, "1"), (U_CMP, "3"))
    lf.net(thresh, (R_TH1, "2"), (R_TH2, "1"), (U_CMP, "4"))
    lf.net(trip, (U_CMP, "1"), (J, str(4 + ng)), (D_OR, "2"))
    lf.net("TRIP_ANY", (D_OR, "1"))
    lf.net("RAIL_" + rail, *[(r, "1") for legs in leg_refs_by_group for r in legs])
    for gi in range(ng):
        legs = leg_refs_by_group[gi]
        lf.net(f"{rail}_G{gi + 1}_NODE",
               *[(r, "2") for r in legs], (fuse_refs[gi], "1"), (fuse_refs[gi], "2"))
        lf.net(f"{rail}_G{gi + 1}_FUSED",
               (fuse_refs[gi], "3"), (fuse_refs[gi], "4"), (fet_refs[gi], "2"))
        lf.net(f"{rail}_G{gi + 1}_GATE",
               (and_refs[gi], "4"), (gr_refs[gi], "1"))
        lf.net(f"{rail}_G{gi + 1}_GATE_DRIVE",
               (gr_refs[gi], "2"), (pd_refs[gi], "1"), (fet_refs[gi], "1"))

    lf.hier_exports = {}
    lf.global_nets = set(ctrl_names) | {"DEGATE_RAIL", trip, "TRIP_ANY",
                                        "RAIL_" + rail, "+5V_LOGIC"}
    lf.powerflag_nets = ["GND", "+3V3", "+5V_LOGIC"]

    def _compose():
        c = _Compose(lf)
        c.place(J, 20, 40)
        leg_pitch, group_gap = 8, 6
        x = 60
        group_x0 = []
        for gi, count in enumerate(groups):
            group_x0.append(x)
            legs = leg_refs_by_group[gi]
            for li, r in enumerate(legs):
                c.place(r, x, 40)
                x += leg_pitch
            x += group_gap
        # ALL legs share one row (y=40, rot=0 vertical) so every pin1 sits
        # on the exact same absolute Y. FIRST ATTEMPT drew ONE long bus wire
        # from the leftmost to the rightmost leg, relying on "KiCad binds a
        # pin wherever a drawn wire's path touches it, not only at declared
        # endpoints" (the addendum-4 lesson, there observed on a 2-endpoint
        # wire that happened to pass through a THIRD, unrelated pin). That
        # does NOT generalize to a bus serving MANY intermediate pins on one
        # long segment -- re-verified against the real netlist/ERC: kicad-
        # cli's `pin_not_connected` fired on most of the interior legs (e.g.
        # 05b's group-4 row, all 4 legs on one 30mm run: R183/184/185 each
        # partly unconnected, only the two segment ENDPOINTS reliably
        # bound). FIX: chain the bus as ADJACENT-PAIR segments (leg[i] to
        # leg[i+1], matching this file's own established archetypes --
        # divider_chain/protection_chain build their runs the same way) so
        # EVERY leg pin is a genuine wire ENDPOINT for at least one segment,
        # never just a mid-span pass-through.
        all_legs = [r for legs in leg_refs_by_group for r in legs]
        p1_all = [c.pin(r, "1") for r in all_legs]
        rail_bus_y = p1_all[0][1]
        for a, b in zip(all_legs, all_legs[1:]):
            c.wire(c.pin(a, "1"), c.pin(b, "1"))
        c.label("RAIL_" + rail, p1_all[0][0], rail_bus_y, 90)
        for gi, count in enumerate(groups):
            legs = leg_refs_by_group[gi]
            for a, b in zip(legs, legs[1:]):
                c.wire(c.pin(a, "2"), c.pin(b, "2"))
            c.use(*[(r, "1") for r in legs], *[(r, "2") for r in legs])

        # Per-group control cluster: EVERY group's fuse/FET/AND-gate/gate-R/
        # pulldown sits in its OWN narrow x-column (gx, the group's own
        # anchor) so no group's wiring ever needs a wide horizontal span
        # that could reach into a neighboring group. ALSO staggers each
        # group's row by `row_stagger` grid units as a second, independent
        # safety margin. BOTH were needed: a first pass placed every
        # group's AND-gate/gate-R far to the group's OWN right edge (at
        # `gx + leg_pitch*count`) while its FET stayed at `gx` -- the
        # resulting gr-to-FET-gate wire spanned nearly the group's full
        # width, and at tight group pitches (adjacent single-leg groups
        # only ~14 units apart) that span COLLIDED, COLLINEARLY, with the
        # next group's own same-shape wire on the SAME y row: KiCad merges
        # overlapping collinear wire segments regardless of where their
        # OWN endpoints are, so two different groups' gate-drive nets
        # silently shorted together (ERC caught it as `pin_to_pin` "Output
        # and Output are connected" between two different AND-gate Y
        # pins -- a real cross-group short, not a cosmetic finding).
        row_stagger = 50   # generous -- > the vertical extent of one
                            # group's own fuse/FET/AND/gateR/pulldown
                            # cluster PLUS the nudge pass's own search
                            # radius, so adjacent groups' clusters never
                            # share a row AND nudge has clear room to push
                            # each part's self-colliding Value/Ref text
                            # into (a first, tighter attempt left several
                            # small parts' OWN Value-text self-colliding
                            # with their OWN pin labels unresolved -- not a
                            # cross-part issue, but nudge needs empty space
                            # nearby to resolve even a self-collision into)
        for gi, count in enumerate(groups):
            gnum = gi + 1
            legs = leg_refs_by_group[gi]
            gx = group_x0[gi]
            ry = 60 + gi * row_stagger
            f_, q, u, gr, pd = fuse_refs[gi], fet_refs[gi], and_refs[gi], gr_refs[gi], pd_refs[gi]
            c.place(f_, gx, ry)
            c.place(q, gx, ry + 22, 90)
            c.place(u, gx + 24, ry)
            c.place(gr, gx + 24, ry + 16, 90)
            c.place(pd, gx + 40, ry + 16, 90)
            # group node: leg pin2 row -> fuse pin1/2. Every hand-consumed
            # net gets an explicit c.label() at its tap point -- without
            # one, a fully hand-wired net exports only under KiCad's own
            # auto-derived name (e.g. "Net-(F1-Pad1)"), the same class
            # this file's own addendum 7 already documents for the loop
            # leaves' SP_GATED/SETPOINT nets; the checker script (build
            # order item 7) needs these names to actually mean something.
            p2mid = c.pin(legs[len(legs) // 2], "2")
            f1, f2 = c.pin(f_, "1"), c.pin(f_, "2")
            c.wire(p2mid, (p2mid[0], f1[1]), f1)
            c.wire(f1, f2)
            c.use((legs[len(legs) // 2], "2"), (f_, "1"), (f_, "2"))
            c.label(f"{rail}_G{gnum}_NODE", f1[0], f1[1], 90)
            # fuse out -> FET drain
            f3, f4 = c.pin(f_, "3"), c.pin(f_, "4")
            qd = c.pin(q, "2")
            c.wire(f3, f4)
            c.wire(f4, (f4[0], qd[1]), qd)
            c.use((f_, "3"), (f_, "4"), (q, "2"))
            c.label(f"{rail}_G{gnum}_FUSED", f4[0], f4[1], 90)
            # AND -> gate R -> FET gate; also gate pulldown -- all within
            # this group's own tight column now (gx..gx+30), never
            # reaching toward gx of any neighboring group.
            u4 = c.pin(u, "4")
            gr1 = c.pin(gr, "1")
            c.wire(u4, (u4[0], gr1[1]), gr1)
            c.use((u, "4"), (gr, "1"))
            c.label(f"{rail}_G{gnum}_GATE", u4[0], u4[1], 90)
            gr2 = c.pin(gr, "2")
            qg = c.pin(q, "1")
            pd1 = c.pin(pd, "1")
            c.wire(gr2, (qg[0], gr2[1]), qg)
            c.wire(gr2, (pd1[0], gr2[1]), pd1)
            c.use((gr, "2"), (q, "1"), (pd, "1"))
            c.label(f"{rail}_G{gnum}_GATE_DRIVE", gr2[0], gr2[1], 90)

        # ---- shared rail-level shunt + trip-watch, placed clear below
        # EVERY group's row (dynamic on group count, not a fixed guess --
        # a fixed sy=100 collided with the later-staggered groups once
        # row_stagger grew past 100/ng).
        sy = 60 + ng * row_stagger + 20
        # SAME relative offsets as compose_04's already-clean (0-overlap)
        # trip-watch cell, just re-based at (100, sy) -- reusing proven
        # geometry rather than re-deriving new spacing from scratch.
        c.place(RS, 60, sy)
        c.place(U_INA, 100, sy + 20)
        c.place(C_INA, 100, sy + 6)
        c.place(U_CMP, 132, sy + 20)
        c.place(C_CMP, 132, sy + 6)
        c.place(R_TH1, 154, sy + 12, 90)
        c.place(R_TH2, 154, sy + 30, 90)
        c.place(D_OR, 154, sy + 42, 270)

        c.caption(lf.desc, 6, 8)
        c.note(
            f"{rail} R-bank, LADDER v1.1 [wb] (README.md, pending owner "
            f"nod): {ng} groups, {'+'.join(str(g) for g in groups)} legs "
            f"({total_legs} total @ {leg_value} each), ST-1000 baseline "
            "drawn -- the ST-1300 population variant (12V group "
            f"{ng if rail == '12V' else '-'} +12 legs, 16->28) is a "
            "population-only BOM extension, not physically drawn this "
            "pass (\"never in copper\" per README -- deferred, see the "
            "pin-audit addendum). Fuse UPSTREAM of FET (DESIGN-SHEET "
            "C.12). Trip-watch is PER-RAIL (one shared Kelvin shunt in "
            "the common FET-source return), not per-group -- matches "
            "03-mcu's committed 1-bit TRIP_BANK budget; per-group ATOF "
            "fusing is the real per-leg protection. Harness-boundary "
            f"{harn_kind}: pins 1-{3 + ng} real, rest spare.", 6,
            sy + 60)
        c.done()

    return lf, _compose


BANK_LEAVES = {}
for _rid, _fid, _rail, _groups, _legval in _BANK_RAILS:
    _lf, _fn = compose_05(_rid, _fid, _rail, _groups, _legval)
    BANK_LEAVES[_rid] = (_lf, _fid, _fn)


if __name__ == "__main__":
    compose_01()
    compose_02()
    compose_03()
    # PHASE-1 STANDALONE BUILD LIST (2026-07-17 continuation): every leaf
    # below 03-mcu is still built the SAME "TESTROOT" placeholder way 01/02/
    # 03 were -- each file gets its own individual-leaf ERC/lint/overlap/
    # netlist gate before it is trusted, exactly matching the established
    # per-leaf workflow. This list grows as each build-order group (04, 05,
    # 06, 07, 08) lands; the FINAL step (root composition) throws this whole
    # block away and rebuilds every leaf with real path_prefix/sheet_
    # instances_path/own_uuid chains + the actual thin-parent root, per
    # build_thin_parent's own convention (modules/ent-common/
    # gen_p4_t1_block.py's __main__ is the worked example).
    _STANDALONE_BUILD = [(L01, "01-link"), (L02, "02-power"), (L03, "03-mcu")]
    for _rid in ("04a", "04b", "04c", "04d"):
        _lf, _fid, _fn = LOOP_LEAVES[_rid]
        _fn()
        _STANDALONE_BUILD.append((_lf, _fid))
    for _rid in ("05a", "05b", "05c", "05d", "05e"):
        _lf, _fid, _fn = BANK_LEAVES[_rid]
        _fn()
        _STANDALONE_BUILD.append((_lf, _fid))

    _PAPER = {"03-mcu": "A1", "05a-bank-12v": "A1", "05b-bank-5v": "A2",
              "05c-bank-3v3": "A2", "05d-bank-5vsb": "A2", "05e-bank-n12v": "A2"}
    for lf, fname in _STANDALONE_BUILD:
        stats = cec_sch_compose.build_leaf(
            lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None,
            LIBS, PROJECT, path_prefix="TESTROOT", sheet_instances_path="TESTROOT",
            own_uuid="11111111-1111-1111-1111-111111111111",
            page="2", out_path=f"{HERE}/{fname}.kicad_sch",
            paper=_PAPER.get(fname, "A3"),
            title="TEST", comment1=lf.desc, pwr_base=100, layout=lf.layout,
            global_nets=getattr(lf, "global_nets", None))
        print(f"{fname}:", stats)
