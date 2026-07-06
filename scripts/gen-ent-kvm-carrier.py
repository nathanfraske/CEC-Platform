#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  gen-ent-kvm-carrier -- modules/ent-kvm-carrier (ENT lane, Path C, DRAFT)
# ============================================================================
# THE ENT KVM CARRIER: the owner-ruled Path C realization (2026-07-06 ruling,
# recorded in docs/nanokvm-pro-carrier-exploration-2026-07-06.md Part IV/IV-A
# + docs/owner-queue.md) -- the Sipeed M3C (AX630C) compute module socketed on
# a CEC-designed carrier, fronted by the uniform ENT ESP32-P4 trust endpoint.
# The compute element is a MEASURED, SUPERVISED PERIPHERAL behind the same
# CEC trust hardware every ENT module uses; trust lives in CEC silicon.
#
# Schematic ONLY (no PCB). Hierarchical from birth through the shared T4
# composition engine (scripts/cec_sch_compose.py), reusing the ent-common
# ESP32-P4 + 100BASE-T1 shared module block WHOLESALE (its six leaves are
# regenerated verbatim under this project's root, same parts/nets/layout;
# leaf 04-mcu gains the carrier-supervisor GPIO nets, leaf 06 gains the
# 6.14-suite host-USB hardening and is re-pointed at the USB gate):
#
#   ent-kvm-carrier.kicad_sch        root = thin parent (sheet symbols only)
#     01-power.kicad_sch             [ent-common] RJ-45 + TPS26621 eFuse + 3V3 LDO
#     02-misplug-protection.kicad_sch[ent-common] DETECT 10k ENT class + pin-7
#     03-can.kicad_sch               [ent-common] TJA1051T/3
#     04-mcu.kicad_sch               [ent-common + carrier GPIOs] ESP32-P4
#     05-t1-phy.kicad_sch            [ent-common] DP83TC814S-Q1 100BASE-T1
#     06-usb-host.kicad_sch          [ent-common 06 + 6.14 suite] host-facing USB-C
#     07-usb-gate.kicad_sch          TS3USB221 P4-gated USB topology
#     08-compute-power.kicad_sch     monitored 5V: fuse+TVS -> TPS25940 -> INA238
#     09-m2-module.kicad_sch         2x M.2 M-key 75-pos sockets (M3C), TF boot
#                                    storage, reset/strap supervisor domain
#     10-hdmi-capture.kicad_sch      HDMI-A -> LT6911-class bridge -> MIPI CSI
#
# PRIMARY SOURCES (pin map read page-by-page, this session + Part IV-A):
#   lib/datasheets/Sipeed_M3C_core_module_SCH_378C.pdf  p12 (J1/J2 NGFF_M_KEY
#     finger maps -- the pin tables below are TRANSCRIBED from that page),
#     p4 (boot-config table: BOND1/BOND0 on-module; GPIO3_A3/A2 finger straps;
#     R24-R28 47k on-module strap set; "USB DL or SD Card or UART = X/X/X/0")
#   lib/datasheets/Sipeed_MaixCam2_SCH_379C.pdf  p1 (1:1 mating, VSYS_5V on
#     six 5V-VIN fingers + 2x47uF), p3 (BOOT key pulls GPIO3_A2 low), p5
#     (camera FPC: RX_CD0..CD4 = the CSI pair set; ES3134KZ I2C0 1.8<->3.3
#     shifters), p9 (">=100ms reset at power-on" rule), p12 (TF card wiring:
#     TF-123-ARP9H17, VDD direct 3V3 + 10uF, SWITCH->GND)
#
# CORRECTION TO PART IV-A recorded here: the B-edge carries SIX 5V-VIN fingers
# (B13/15/17/19/21/23), not five -- confirmed on BOTH schematics (378C p12 and
# 379C p1).
#
# NETWORK EGRESS POSTURE (Part III K1 row 12 / spec 13.6): the ONLY network
# silicon on this carrier is the ent-common 100BASE-T1 module link. The
# module's on-die EPHY MDI fingers (A67/69/73/75) are left UNMAGNETIZED AND
# UNCONNECTED (verifiable unpowered/absent by construction); the SDIO (WiFi)
# and RGMII (GbE) finger groups are likewise unconnected. NO local LAN PHY
# exists anywhere on this board -- the KVM's network face IS the ENT hub's
# policy, by construction.
#
#   python3 scripts/gen-ent-kvm-carrier.py
# Validate: python3 modules/ent-kvm-carrier/check_ent_kvm_carrier.py
#
# ---------------------------------------------------------------------------
# ENGINEERING FLAGS (mirrors the ent-common flag discipline -- honest, loud):
#  F1. All ESP32-P4 GPIO assignments are PLACEHOLDER (ent-common flag #1
#      inherited); the carrier additions use GPIO17..23,26..35 (24/25 skipped
#      -- possible USB-JTAG special function, unverified against the TRM).
#  F2. LT6911-class HDMI-RX bridge (U11): LCSC does NOT stock Lontium
#      LT6911-family parts (searched 2026-07-06) -> CONSIGNED/PENDING. The
#      symbol is a FUNCTIONAL-BLOCK placeholder: pin NUMBERS are logical, the
#      physical pinout/power tree (VDD core rails) is NOT captured (datasheet
#      is NDA-channel). Re-pin before any layout. CSI lane count (4-lane) and
#      the finger budget are Part IV-A verified.
#  F3. TS3USB221 (U9) symbol pin NUMBERS are functional placeholders --
#      re-map to the TI package (SCDS266) before layout/BOM lock. LCSC
#      C128396 (TS3USB221ARSER) verified in stock.
#  F4. M.2 M-key 75-pos socket (J4/J5): LCSC candidate HYCW23M-05NGFF-670B
#      (C41430858) -- KEYING (must be M), stack height, and the TWO-SOCKET
#      spacing all pend Sipeed's M3C mechanical drawing (the Part IV-A
#      remaining item). Footprints deliberately unassigned.
#  F5. CSI lane mapping (which RX_CD pair carries the D-PHY CLOCK) is
#      UNVERIFIED: this schematic centers the clock on RX_CD2, data on
#      RX_CD0/1/3/4, mirroring the MaixCam2 camera-FPC pair set (379C p5).
#      The AX630C's combo-PHY lane remap may make this a firmware matter;
#      confirm against Axera MIPI-RX documentation before layout.
#  F6. TPS25940 application values (ILIM/dVdT/PGTH/OVP-disable) and the
#      TPS26621-style dividers are ILLUSTRATIVE PLACEHOLDERS (same class as
#      ent-common flag #6). TPS25940LRVCR LCSC stock is THIN (~25) --
#      restock-watch; TPS25940ARVCR C2653873 is the fallback.
#  F7. LP5907MFX-1.8 (U10): TI original not found on LCSC; XLP5907MFX-1.8
#      clone C51953294 exists -- sourcing decision flagged, not made.
#  F8. Boot policy realized in hardware: Q2 defaults ON -> GPIO3_A2 forced
#      low -> "USB DL or SD Card or UART" ROM path (carrier-owned boot, A5
#      option i). The module's own 47k pull-up (R25-class, 378C p4) is
#      overpowered by the FET. P4 may drive the gate low to re-enable
#      eMMC-boot (policy option ii). ROM search order inside the X/X/X/0
#      composite mode is the standing BENCH item (Part IV-A).
#  F9. Reset contract: Q1 defaults ON -> SYS_RSTN_IN held LOW (asserted)
#      from carrier power-up, independent of P4 state. FIRMWARE CONTRACT
#      (379C p9): hold >=100 ms after compute power good, verify boot storage,
#      THEN drive M2_RSTN_GATE low to release. Assert reset BEFORE M2_PWR_EN.
#  F10. Root plumbing: the six inherited ent-common nets keep their proven
#      drawn sheet-pin wires; ALL new carrier nets cross sheets as GLOBAL
#      LABELS (build_leaf global_nets). Deliberate: the thin-parent lane
#      router composes 1:1 nets only, and the carrier's buses (CSI x10, I2C
#      x3-sheet, supervisor cluster) exceed that shape -- traced two
#      collinear-merge hazards before choosing globals. GUI review item.
#  F11. Bridge control topology (DECISION, flagged): the LT6911's config I2C
#      + RESET_N + INT terminate on the CARRIER P4 (trust endpoint owns
#      capture-enable and bridge config; module I2C0 fingers A43/A45 left
#      unconnected). ALTERNATIVE (Sipeed-stock software compatibility):
#      module-owned I2C0 through an ES3134KZ-class 1.8<->3.3 shifter pair --
#      documented in the README, NOT provisioned (a DNP series shifter would
#      netlist the two buses as one, the H3a rule).
#  F12. HDMI connector HDMI-001 19PCBTP (C138388) is a generic-catalog
#      candidate; land/retention verify at footprint intake. RClamp0524P on
#      TMDS/DDC mirrors the hub-ENT ESD part (C40960).
# ---------------------------------------------------------------------------
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cec_sch            # noqa: E402
import cec_sch_layout     # noqa: E402
import cec_sch_compose    # noqa: E402

OUT = os.path.join(ROOTDIR, "modules", "ent-kvm-carrier")
PROJECT = "ent-kvm-carrier"

# ---------------------------------------------------------------------------
# import the ent-common generator AS A LIBRARY (its __main__ guard keeps it
# from writing files); its Leaf objects + compose functions are the shared
# P4+T1 block, reused wholesale under THIS project's root.
_spec = importlib.util.spec_from_file_location(
    "gen_p4_t1_block",
    os.path.join(ROOTDIR, "modules", "ent-common", "gen_p4_t1_block.py"))
entc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entc)

P4 = entc.P4            # ESP32-P4 name -> pin number lookup
Leaf = cec_sch_compose.Leaf

# Fixed identity uuids (stable across regenerations).
ROOT_UUID = "8b3c4d5e-a8c8-4f6d-89f5-b08a2a5a5b60"
LEAF_SYM_UUIDS = {f"{i:02d}": f"5e6f7081-92a3-44c{i % 10}-9d5e-6f708192a3{i:02d}"
                  for i in range(1, 11)}
LEAF_OWN_UUIDS = {f"{i:02d}": f"6f708192-a3b4-45d{i % 10}-8e6f-708192a3b4{i:02d}"
                  for i in range(1, 11)}

# ===========================================================================
# ent-kvm-local.kicad_sym -- project-local symbols (M.2 sockets w/ the M3C
# finger map, LT6911-class functional placeholder, TS3USB221, TF socket,
# HDMI-A, SOT-23 N-FET, PTC fuse, bidirectional TVS).
# ===========================================================================
def _sym(name, refpfx, desc, left, right, top=(), bottom=(), half_w=12.7,
         hide_pin_numbers=False, pitch=2.54):
    """Emit one box symbol. left/right/top/bottom = [(num, name, etype), ...].
    Pin connection points land on the 1.27 grid by construction."""
    rows = max(len(left), len(right))
    half_h = ((rows + 1) * pitch) / 2 + 2.54
    half_h = round(half_h / 1.27) * 1.27
    cols = max(len(top), len(bottom))
    if cols:
        need_w = ((cols + 1) * pitch) / 2 + 2.54
        half_w = max(half_w, round(need_w / 1.27) * 1.27)
    plen = 5.08
    body = []
    y0 = (rows - 1) * pitch / 2
    y0 = round(y0 / 1.27) * 1.27
    for i, (num, pname, et) in enumerate(left):
        body.append((num, pname, et, -half_w - plen, y0 - i * pitch, 0))
    for i, (num, pname, et) in enumerate(right):
        body.append((num, pname, et, half_w + plen, y0 - i * pitch, 180))
    x0t = -(len(top) - 1) * pitch / 2 if top else 0
    x0t = round(x0t / 1.27) * 1.27
    for i, (num, pname, et) in enumerate(top):
        body.append((num, pname, et, x0t + i * pitch, half_h + plen, 270))
    x0b = -(len(bottom) - 1) * pitch / 2 if bottom else 0
    x0b = round(x0b / 1.27) * 1.27
    for i, (num, pname, et) in enumerate(bottom):
        body.append((num, pname, et, x0b + i * pitch, -half_h - plen, 90))
    pins = "\n".join(
        f'\t\t\t(pin {et} line\n'
        f'\t\t\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} {ang})\n'
        f'\t\t\t\t(length {plen})\n'
        f'\t\t\t\t(name "{pname}"\n\t\t\t\t\t(effects (font (size 1.27 1.27)))\n\t\t\t\t)\n'
        f'\t\t\t\t(number "{num}"\n\t\t\t\t\t(effects (font (size 1.27 1.27)))\n\t\t\t\t)\n'
        f'\t\t\t)'
        for (num, pname, et, x, y, ang) in body)
    hidenum = "\t\t(pin_numbers\n\t\t\t(hide yes)\n\t\t)\n" if hide_pin_numbers else ""
    esc = desc.replace('"', "'")
    return (
        f'\t(symbol "{name}"\n'
        f'{hidenum}'
        f'\t\t(pin_names\n\t\t\t(offset 0.254)\n\t\t)\n'
        f'\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n'
        f'\t\t(property "Reference" "{refpfx}"\n\t\t\t(at 0 {cec_sch.f(half_h + 2.54)} 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)))\n\t\t)\n'
        f'\t\t(property "Value" "{name}"\n\t\t\t(at 0 {cec_sch.f(-half_h - 2.54)} 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)))\n\t\t)\n'
        f'\t\t(property "Footprint" ""\n\t\t\t(at 0 0 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n\t\t)\n'
        f'\t\t(property "Datasheet" "~"\n\t\t\t(at 0 0 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n\t\t)\n'
        f'\t\t(property "Description" "{esc}"\n\t\t\t(at 0 0 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n\t\t)\n'
        f'\t\t(symbol "{name}_0_1"\n'
        f'\t\t\t(rectangle\n\t\t\t\t(start {cec_sch.f(-half_w)} {cec_sch.f(half_h)})\n'
        f'\t\t\t\t(end {cec_sch.f(half_w)} {cec_sch.f(-half_h)})\n'
        f'\t\t\t\t(stroke (width 0.254) (type default))\n'
        f'\t\t\t\t(fill (type background))\n\t\t\t)\n'
        f'\t\t)\n'
        f'\t\t(symbol "{name}_1_1"\n{pins}\n\t\t)\n'
        f'\t)')


# --- the M3C finger maps, TRANSCRIBED from Sipeed_M3C_core_module_SCH_378C
# p12 (J1 = A-edge, J2 = B-edge; M.2 M-key: positions 59-66 are the key
# notch, no contacts). Names shortened only where the drawing's own net label
# already shortens them; the full mux strings live in the PDF.
M2A = {  # A-edge (module J1)
    1: "RX_CD4_P", 2: "GPIO1_A1/UART2_RXD", 3: "RX_CD4_N", 4: "GPIO1_A0/UART2_TXD",
    5: "GND", 6: "GPIO0_A31/UART1_RXD", 7: "RX_CD5_P", 8: "GPIO0_A30/UART1_TXD",
    9: "RX_CD5_N", 10: "SYS_RSTN_OUT", 11: "GND", 12: "GPIO0_A22/TCK",
    13: "GPIO0_A8/I2C7_SCL", 14: "GPIO0_A18/MCLK0", 15: "GPIO0_A10/VI_CLK0",
    16: "GPIO3_A3_BOOT", 17: "GPIO0_A7/VI_D7", 18: "GPIO0_A21/TMS",
    19: "GPIO0_A9/I2C7_SDA", 20: "GPIO1_A2/SPI_M2_MOSI", 21: "GPIO0_A5",
    22: "GPIO1_A3/SPI_M2_MISO", 23: "GPIO0_A1/SPI_M1_MISO",
    24: "GPIO0_A27/SPI_M2_CS0", 25: "GND", 26: "GPIO0_A26/SPI_M2_SCLK",
    27: "SDIO_DAT0", 28: "GPIO3_A1/SENSOR_RSTN0", 29: "SDIO_CLK",
    30: "GPIO0_A12/ADC_IN", 31: "SDIO_CMD", 32: "GPIO0_A11/WAKE_UP",
    33: "SDIO_DAT1", 34: "GPIO0_A6/VI_D6", 35: "SDIO_DAT2", 36: "GPIO0_A3",
    37: "SDIO_DAT3", 38: "GPIO0_A2/SPI_M1_CS0", 39: "EPHY_LED1",
    40: "GPIO0_A4/SPI_M1_SCLK", 41: "EPHY_LED0", 42: "GPIO0_A0/SPI_M1_MOSI",
    43: "GPIO0_A24/I2C0_SCL", 44: "NC", 45: "GPIO0_A25/I2C0_SDA", 46: "NC",
    47: "SD_DAT2", 48: "NC", 49: "SD_DAT1", 50: "GPIO1_A10/PPS2_BOOTLOW",
    51: "SD_DAT0", 52: "GPIO0_A23/SD_PWR_EN", 53: "SD_CMD", 54: "NC",
    55: "SD_DAT3", 56: "GPIO1_A9/PPS1", 57: "SD_CLK", 58: "GPIO1_A11/PPS3",
    67: "EPHY_RXP", 68: "GPIO0_A29/UART0_RXD", 69: "EPHY_RXN",
    70: "GPIO0_A28/UART0_TXD", 71: "GND", 72: "SYS_RSTN_IN", 73: "EPHY_TXP",
    74: "GPIO3_A2_BOOT", 75: "EPHY_TXN",
}
M2B = {  # B-edge (module J2)
    1: "GND", 2: "GPIO1_A18/RGMII_TXD0", 3: "GND", 4: "GPIO1_A15/RGMII_RXCLK",
    5: "GND", 6: "GPIO1_A16/RGMII_RXD2", 7: "GND", 8: "GPIO1_A13/RGMII_RXD1",
    9: "GND", 10: "GPIO1_A26/EPHY_CLK", 11: "GND", 12: "GPIO1_A17/RGMII_RXD3",
    13: "5V-VIN", 14: "GPIO1_A24/RGMII_MDCK", 15: "5V-VIN",
    16: "GPIO1_A25/RGMII_MDIO", 17: "5V-VIN", 18: "GND", 19: "5V-VIN",
    20: "USB0_DP", 21: "5V-VIN", 22: "USB0_DM", 23: "5V-VIN", 24: "GND",
    25: "GPIO1_A22/RGMII_TXD2", 26: "GPIO1_A21/RGMII_TXEN",
    27: "GPIO1_A19/RGMII_TXD1", 28: "GPIO1_A23/RGMII_TXD3", 29: "SYS_RSTN_IN",
    30: "GPIO1_A12/RGMII_RXD0", 31: "GPIO1_A20/RGMII_TXCLK",
    32: "GPIO1_A14/RGMII_RXDV", 33: "GPIO1_A8/PPS0", 34: "GND", 35: "MICR_N",
    36: "TX_CD3_N", 37: "MICR_P", 38: "TX_CD3_P", 39: "MICL_N", 40: "GND",
    41: "MICL_P", 42: "TX_CD1_N", 43: "HPR_N", 44: "TX_CD1_P", 45: "HPR_P",
    46: "GND", 47: "GND", 48: "TX_CD0_N", 49: "RX_CD0_P", 50: "TX_CD0_P",
    51: "RX_CD0_N", 52: "GND", 53: "GND", 54: "TX_CLK_N", 55: "RX_CD1_P",
    56: "TX_CLK_P", 57: "RX_CD1_N", 58: "GND", 67: "RX_CD2_P", 68: "TX_CD2_N",
    69: "RX_CD2_N", 70: "TX_CD2_P", 71: "GND", 72: "GND", 73: "RX_CD3_P",
    74: "GPIO1_A27/EPHY_RST", 75: "RX_CD3_N",
}
M2A_GND = [5, 11, 25, 71]
M2B_GND = [1, 3, 5, 7, 9, 11, 18, 24, 34, 40, 46, 47, 52, 53, 58, 71, 72]
M2B_5V = [13, 15, 17, 19, 21, 23]      # SIX fingers (Part IV-A correction)


def _m2_sym(name, table, desc):
    evens = [(str(n), table[n], "passive") for n in sorted(table) if n % 2 == 0]
    odds = [(str(n), table[n], "passive") for n in sorted(table) if n % 2 == 1]
    return _sym(name, "J", desc, evens, odds, half_w=22.86)


def build_local_lib():
    syms = []
    syms.append(_m2_sym(
        "M2_MKEY_A_M3C", M2A,
        "M.2/NGFF M-KEY 75-position socket, A-EDGE of the Sipeed M3C (AX630C) core module. "
        "Pin map transcribed from Sipeed_M3C_core_module_SCH_378C.pdf p12 (J1 NGFF_M_KEY). "
        "Key notch = positions 59-66 (no contacts). Socket candidate HYCW23M-05NGFF-670B "
        "(LCSC C41430858) -- keying/stack-height/two-socket spacing pend the Sipeed mechanical drawing (flag F4)."))
    syms.append(_m2_sym(
        "M2_MKEY_B_M3C", M2B,
        "M.2/NGFF M-KEY 75-position socket, B-EDGE of the Sipeed M3C core module (dual-edge "
        "gold-finger module; the MaixCam2 base board mates both edges 1:1, 379C p1). Pin map "
        "from 378C p12 (J2 NGFF_M_KEY). Six 5V-VIN fingers (13/15/17/19/21/23) -- corrects "
        "Part IV-A's 'five pins'. Same socket part as the A-edge (flag F4)."))
    syms.append(_sym(
        "LT6911_FUNC", "U",
        "LT6911-CLASS HDMI-to-MIPI-CSI bridge -- FUNCTIONAL-BLOCK PLACEHOLDER (flag F2): pin "
        "numbers are LOGICAL, physical pinout + full power tree NOT captured (Lontium datasheet "
        "is NDA-channel; LCSC does not stock the family -> consigned). 4-lane CSI out per the "
        "Part IV-A finger budget. Re-pin against the real package before any layout.",
        left=[("1", "HDMI_D2_P", "input"), ("2", "HDMI_D2_N", "input"),
              ("3", "HDMI_D1_P", "input"), ("4", "HDMI_D1_N", "input"),
              ("5", "HDMI_D0_P", "input"), ("6", "HDMI_D0_N", "input"),
              ("7", "HDMI_CK_P", "input"), ("8", "HDMI_CK_N", "input"),
              ("9", "DDC_SCL", "bidirectional"), ("10", "DDC_SDA", "bidirectional"),
              ("11", "HPD", "output"), ("12", "CEC", "bidirectional"),
              ("13", "HDMI_5V_DET", "input")],
        right=[("14", "CSI_CLK_P", "output"), ("15", "CSI_CLK_N", "output"),
               ("16", "CSI_D0_P", "output"), ("17", "CSI_D0_N", "output"),
               ("18", "CSI_D1_P", "output"), ("19", "CSI_D1_N", "output"),
               ("20", "CSI_D2_P", "output"), ("21", "CSI_D2_N", "output"),
               ("22", "CSI_D3_P", "output"), ("23", "CSI_D3_N", "output"),
               ("24", "I2C_SCL", "input"), ("25", "I2C_SDA", "bidirectional"),
               ("26", "RESET_N", "input"), ("27", "INT", "open_collector")],
        top=[("28", "VDD33_1", "power_in"), ("29", "VDD33_2", "power_in")],
        bottom=[("30", "GND1", "power_in"), ("31", "GND2", "power_in")],
        half_w=17.78))
    syms.append(_sym(
        "TS3USB221_FUNC", "U",
        "TI TS3USB221A USB 2.0 high-speed 1:2 analog mux/demux (LCSC C128396). PIN NUMBERS ARE "
        "FUNCTIONAL PLACEHOLDERS (flag F3) -- re-map to the real UQFN-10 package (TI SCDS266) "
        "before layout/BOM lock. S low selects the D1 port (VERIFY against datasheet). OE# high "
        "= both ports disconnected (the attested-session hardware default).",
        left=[("1", "D+", "bidirectional"), ("2", "D-", "bidirectional"),
              ("3", "S", "input"), ("4", "OE#", "input")],
        right=[("5", "D1+", "bidirectional"), ("6", "D1-", "bidirectional"),
               ("7", "D2+", "bidirectional"), ("8", "D2-", "bidirectional")],
        top=[("9", "VCC", "power_in")], bottom=[("10", "GND", "power_in")],
        half_w=10.16))
    syms.append(_sym(
        "TF_CARD_TF123", "J",
        "TF/microSD socket, Lianjie TF-123-ARP9H17 (LCSC C2982548) -- the exact part the "
        "MaixCam2 base board wires to these same SD fingers (379C p12): VDD direct 3V3 + 10uF, "
        "SWITCH (card-detect) to GND, shell tabs 10-13 to GND. The carrier-owned boot storage "
        "(A5 option i).",
        left=[("1", "DAT2", "bidirectional"), ("2", "CD/DAT3", "bidirectional"),
              ("3", "CMD", "bidirectional"), ("4", "VDD", "power_in"),
              ("5", "CLK", "input"), ("6", "VSS", "power_in"),
              ("7", "DAT0", "bidirectional"), ("8", "DAT1", "bidirectional"),
              ("9", "SWITCH", "passive")],
        right=[("10", "SHELL", "passive"), ("11", "SHELL", "passive"),
               ("12", "SHELL", "passive"), ("13", "SHELL", "passive")],
        half_w=10.16))
    syms.append(_sym(
        "HDMI_A_19P", "J",
        "HDMI type-A receptacle, standard 19-pin map (candidate HDMI-001 19PCBTP, LCSC C138388 "
        "-- generic-catalog part, land/retention verify at footprint intake, flag F12).",
        left=[("1", "TMDS_D2+", "passive"), ("2", "D2_SHIELD", "passive"),
              ("3", "TMDS_D2-", "passive"), ("4", "TMDS_D1+", "passive"),
              ("5", "D1_SHIELD", "passive"), ("6", "TMDS_D1-", "passive"),
              ("7", "TMDS_D0+", "passive"), ("8", "D0_SHIELD", "passive"),
              ("9", "TMDS_D0-", "passive"), ("10", "TMDS_CK+", "passive"),
              ("11", "CK_SHIELD", "passive"), ("12", "TMDS_CK-", "passive")],
        right=[("13", "CEC", "passive"), ("14", "UTILITY", "passive"),
               ("15", "DDC_SCL", "passive"), ("16", "DDC_SDA", "passive"),
               ("17", "DDC/CEC_GND", "passive"), ("18", "+5V", "passive"),
               ("19", "HPD", "passive"),
               ("SH1", "SHELL", "passive"), ("SH2", "SHELL", "passive"),
               ("SH3", "SHELL", "passive"), ("SH4", "SHELL", "passive")],
        half_w=12.7))
    syms.append(_sym(
        "Q_NMOS_GSD", "Q",
        "Small-signal N-FET, SOT-23 (1=G 2=S 3=D -- the real 2N7002/BSS138 pinout). Used for "
        "the open-drain supervisor drives (2N7002, LCSC C8545 Basic) and the 1.8V->3.3V "
        "RSTN_OUT sense shift (BSS138, C112239 -- Vth fits the 1.8V gate rail).",
        left=[("1", "G", "input")],
        right=[("3", "D", "passive")],
        bottom=[("2", "S", "passive")],
        half_w=5.08))
    syms.append(_sym(
        "FUSE_PTC", "F",
        "Resettable PTC fuse (MF-MSMF200-2, 2A hold, 1812, LCSC C210837) -- the 379C base "
        "board's fuse+TVS input posture, kept per Part IV-A A6 ('cheap, good').",
        left=[("1", "1", "passive")], right=[("2", "2", "passive")],
        half_w=3.81, hide_pin_numbers=True))
    syms.append(_sym(
        "D_TVS_BIDIR", "D",
        "Bidirectional TVS, SOD-123FL (SMF5.0CA, LCSC C19077498 preferred-stocked) -- 5V rail "
        "clamp at the compute-power input.",
        left=[("1", "1", "passive")], right=[("2", "2", "passive")],
        half_w=3.81, hide_pin_numbers=True))
    text = ('(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kicad_symbol_editor")\n'
            '\t(generator_version "10.0")\n' + "\n".join(syms) + "\n)\n")
    with open(os.path.join(OUT, "ent-kvm-local.kicad_sym"), "w") as f:
        f.write(text)
    return text


# ===========================================================================
# LIBS: ent-common's set + the local lib (superset passed to every build_leaf)
# ===========================================================================
os.makedirs(OUT, exist_ok=True)
LOCAL_LIB_TEXT = build_local_lib()
LIBS = dict(entc.LIBS)
LIBS["ent-kvm-local"] = LOCAL_LIB_TEXT

POWER_PORTS = {"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"}

# ---------------------------------------------------------------------------
# Carrier GPIO map (ALL PLACEHOLDER, flag F1). GPIO24/25 deliberately skipped.
GP_KVM = {
    "I2C_SDA": 17, "I2C_SCL": 18, "INA_ALERT": 19, "M2_PWR_EN": 20,
    "M2_RSTN_GATE": 21, "M2_RSTN_OUT_3V3": 22, "M2_BOOTSTRAP_GATE": 23,
    "USB_MUX_SEL": 26, "USB_MUX_OE_N": 27, "M2_PGOOD": 28,
    "M2_UART0_RXD": 29, "M2_UART0_TXD": 30, "M2_UART2_RXD": 31,
    "M2_UART2_TXD": 32, "M2_PPS0": 33, "LT_RESET_N": 34, "LT_INT": 35,
}

# ---------------------------------------------------------------------------
# LEAF 04 (ent-common mcu) -- EXTEND with the carrier-supervisor GPIO nets.
# USB_D_P/N leave the hier-export set (they become globals: the P4's USB now
# feeds the TS3USB221 gate on sheet 07, not the USB-C directly).
L04 = entc.L04
for _net, _gp in GP_KVM.items():
    L04.net(_net, ("U1", P4[f"GPIO{_gp}"]))
del L04.hier_exports["USB_D_P"]
del L04.hier_exports["USB_D_N"]
GLOBALS_04 = {"USB_D_P", "USB_D_N"} | set(GP_KVM)

# ---------------------------------------------------------------------------
# LEAF 06 (ent-common usb-debug) -- becomes 06-usb-host: the host-facing
# USB-C (the KVM's attested-HID/console face AND the P4 flash/debug port,
# one physical connector) + the 6.14 module hardening suite (USBLC6-2SC6
# ESD array, MPZ2012S601AT000 VBUS bead). D+/D- now route to the sheet-07
# TS3USB221 gate as globals.
L06 = entc.L06
L06.filename = "06-usb-host.kicad_sch"
L06.sheetname = "06-usb-host"
L06.desc = ("Host-facing USB-C (attested-HID face + P4 flash/debug): 6.14 suite "
            "(USBLC6-2SC6 + VBUS bead), CC pulldowns, VBUS ORs into pre-eFuse +5VSB")
L06.add_part("FB1", "cec-vendor", "FerriteBead_Small", "MPZ2012S601AT000", 0, 0,
             "cec-Capacitor_SMD:C_0805_2012Metric",
             props={"LCSC": "C21519", "MPN": "MPZ2012S601AT000", "Manufacturer": "TDK"})
L06.add_part("D5", "cec-vendor", "USBLC6-2SC6", "USBLC6-2SC6", 0, 0,
             "cec-Package_TO_SOT_SMD:SOT-23-6",
             props={"LCSC": "C2687116", "MPN": "USBLC6-2SC6", "Manufacturer": "UMW"})
L06.nets = {
    "+5VSB": [("D3", "1")],
    "VBUS_C": [("J2", "A4"), ("J2", "A9"), ("J2", "B4"), ("J2", "B9"),
               ("FB1", "1"), ("D5", "5")],
    "VBUS": [("FB1", "2"), ("D3", "2"), ("C19", "1")],
    "USB_HOST_D_P": [("J2", "A6"), ("J2", "B6"), ("D5", "1"), ("D5", "6")],
    "USB_HOST_D_N": [("J2", "A7"), ("J2", "B7"), ("D5", "3"), ("D5", "4")],
    "USB_CC1": [("J2", "A5"), ("R13", "1")],
    "USB_CC2": [("J2", "B5"), ("R14", "1")],
    "GND": [("J2", "A1"), ("J2", "A12"), ("J2", "B1"), ("J2", "B12"),
            ("J2", "S1"), ("C19", "2"), ("R13", "2"), ("R14", "2"), ("D5", "2")],
}
L06.hier_exports = {}
GLOBALS_06 = {"USB_HOST_D_P", "USB_HOST_D_N"}


def compose_06():
    """06-usb-host: the ent-common compose_06 geometry + FB1/D5 (6.14 suite)."""
    c = cec_sch_compose.Compose(L06, LIBS)
    c.place("J2", 16, 36)
    c.place("FB1", 34, 10)
    c.place("D3", 46, 16)
    c.place("C19", 54, 18)
    c.place("D5", 44, 44)
    c.place("R13", 38, 58, 90)
    c.place("R14", 38, 64, 90)
    c.caption("Host-facing USB-C -- the KVM's attested-HID/console face toward the "
              "SUPERVISED HOST + the P4 flash/debug port (one connector)", 4, -2)
    c.note("6.14 suite: USBLC6-2SC6 on D+/D-/VBUS + MPZ2012S601AT000 VBUS bead;\n"
           "VBUS ORs into pre-eFuse +5VSB through D3 (SS34); CC1/CC2 5.1k = UFP sink.\n"
           "D+/D- leave this sheet as USB_HOST_D_P/N globals INTO the sheet-07 TS3USB221\n"
           "gate -- the host NEVER sees the compute module's USB directly (P4 in the\n"
           "control path; OE# default-disconnected).", 4, 76)
    c.use(("J2", "A9"), ("J2", "B4"), ("J2", "B9"),
          ("J2", "B1"), ("J2", "A12"), ("J2", "B12"))
    c.done()


# ===========================================================================
# LEAF 07 -- usb-gate: TS3USB221 P4-gated USB topology.
# ===========================================================================
L07 = Leaf("07", "07-usb-gate.kicad_sch", "07-usb-gate",
           "TS3USB221 1:2 HS mux: P4 USB <-> {host USB-C (attested HID/debug) | "
           "module USB0 AXDL flash/verify}; OE# default-disconnected")
L07.add_part("U9", "ent-kvm-local", "TS3USB221_FUNC", "TS3USB221ARSER", 0, 0, "",
             props={"LCSC": "C128396", "MPN": "TS3USB221ARSER", "Manufacturer": "TI",
                    "Note": "pin numbers FUNCTIONAL PLACEHOLDER (flag F3)"})
L07.add_part("C35", "cec-vendor", "C_Small", "100n", 0, 0,
             "cec-Capacitor_SMD:C_0402_1005Metric")
L07.add_part("R30", "cec-vendor", "R_Small", "100k", 0, 0,
             "cec-Resistor_SMD:R_0402_1005Metric")   # SEL pulldown: default = host port
L07.add_part("R31", "cec-vendor", "R_Small", "100k", 0, 0,
             "cec-Resistor_SMD:R_0402_1005Metric")   # OE# pullup: default DISCONNECTED
L07.net("USB_D_P", ("U9", "1"))
L07.net("USB_D_N", ("U9", "2"))
L07.net("USB_HOST_D_P", ("U9", "5"))
L07.net("USB_HOST_D_N", ("U9", "6"))
L07.net("M2_USB_D_P", ("U9", "7"))
L07.net("M2_USB_D_N", ("U9", "8"))
L07.net("USB_MUX_SEL", ("U9", "3"), ("R30", "1"))
L07.net("USB_MUX_OE_N", ("U9", "4"), ("R31", "1"))
L07.net("+3V3", ("U9", "9"), ("C35", "1"), ("R31", "2"))
L07.net("GND", ("U9", "10"), ("C35", "2"), ("R30", "2"))
GLOBALS_07 = {"USB_D_P", "USB_D_N", "USB_HOST_D_P", "USB_HOST_D_N",
              "M2_USB_D_P", "M2_USB_D_N", "USB_MUX_SEL", "USB_MUX_OE_N"}


def compose_07():
    c = cec_sch_compose.Compose(L07, LIBS)
    c.place("U9", 30, 30)
    c.place("C35", 52, 14)
    c.place("R30", 12, 48, 90)
    c.place("R31", 12, 54, 90)
    c.caption("P4-gated USB topology (attested-HID session model)", 0, -2)
    c.note("ONE P4 USB port, TWO gated faces: D1 = host USB-C (06, HID/console/debug),\n"
           "D2 = module USB0 (09, AXDL flash/verify -- the P4 is the flashing HOST).\n"
           "Hardware defaults: OE# pulled HIGH = both faces DISCONNECTED until the P4\n"
           "grants a session; S pulled LOW = host face when enabled [verify S polarity,\n"
           "flag F3]. The module NEVER connects to the host directly. ALTERNATIVES\n"
           "(flagged, not chosen): dual dedicated P4 ports (symbol exposes one pair);\n"
           "discrete load switches per face (more parts, same trust posture).", 0, 62)
    c.done()


# ===========================================================================
# LEAF 08 -- compute-power: monitored 5V feed -> P4-gated switch -> INA238.
# ===========================================================================
L08 = Leaf("08", "08-compute-power.kicad_sch", "08-compute-power",
           "MAIN_5V feed -> PTC fuse + TVS -> TPS25940 (P4 EN, default OFF) -> "
           "25m shunt + INA238 (K1 row 8 physics sensor) -> M2_5V")
def _p8(ref, lib, name, val, fp, props=None):
    L08.add_part(ref, lib, name, val, 0, 0, fp, props=props)
_p8("J3", "cec", "CEC_PWR_IN_2P", "S2B-XH-A",
    "cec-Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal",
    {"LCSC": "C157931", "MPN": "S2B-XH-A(LF)(SN)", "Manufacturer": "JST",
     "Note": "MAIN_5V tap fed from the 24-pin module's monitored 5V (OQ-13 posture)"})
_p8("F1", "ent-kvm-local", "FUSE_PTC", "MF-MSMF200-2", "",
    {"LCSC": "C210837", "MPN": "MF-MSMF200-2", "Manufacturer": "Bourns"})
_p8("D6", "ent-kvm-local", "D_TVS_BIDIR", "SMF5.0CA", "",
    {"LCSC": "C19077498", "MPN": "SMF5.0CA", "Manufacturer": "-"})
_p8("C30", "cec-vendor", "C_Small", "10u", "cec-Capacitor_SMD:C_0805_2012Metric")
_p8("U7", "cec-ent-power", "TPS25940LRVCR", "TPS25940LRVCR",
    "cec-Package_DFN_QFN:WQFN-20_L4.0-W3.0-P0.50-BL-EP",
    {"LCSC": "C2867756", "MPN": "TPS25940LRVCR", "Manufacturer": "TI",
     "Note": "stock ~25 = restock-watch; fallback TPS25940ARVCR C2653873 (flag F6)"})
_p8("RS1", "cec-vendor", "CEC_SHUNT_2T", "25m",
    "cec-Resistor_SMD:R_2512_6332Metric",
    {"Note": "compute-rail sense shunt; 25m @ 2A max = 50mV/100mW; MPN pends the OQ-11 class"})
_p8("U8", "cec-vendor", "INA226", "INA238AIDGSR",
    "cec-Package_SO:VSSOP-10_3x3mm_P0.5mm",
    {"LCSC": "C2868250", "MPN": "INA238AIDGSR", "Manufacturer": "TI",
     "Note": "INA226 symbol body = INA238 pinout (platform convention); addr A1=A0=GND = 0x40"})
for _r, _v in [("R21", "100k"), ("R22", "1k"), ("R23", "10k"), ("R24", "100k"),
               ("R25", "100k"), ("R26", "100k"), ("R27", "4k7"), ("R28", "4k7"),
               ("R29", "10k")]:
    _p8(_r, "cec-vendor", "R_Small", _v, "cec-Resistor_SMD:R_0402_1005Metric")
_p8("C31", "cec-vendor", "C_Small", "10n", "cec-Capacitor_SMD:C_0402_1005Metric")
_p8("C32", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric")
_p8("C33", "cec-vendor", "C_Small", "10u", "cec-Capacitor_SMD:C_0805_2012Metric")
_p8("C34", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric")

L08.net("MAIN5V_IN", ("J3", "1"), ("F1", "1"))
L08.net("MAIN5V_F", ("F1", "2"), ("D6", "1"), ("C30", "1"),
        ("U7", "9"), ("U7", "10"), ("U7", "11"), ("U7", "12"), ("U7", "13"))
L08.net("M2_5V_SW", ("U7", "4"), ("U7", "5"), ("U7", "6"), ("U7", "7"),
        ("U7", "8"), ("RS1", "1"), ("R25", "1"), ("U8", "10"))
L08.net("M2_5V", ("RS1", "2"), ("U8", "9"), ("U8", "8"), ("C33", "1"), ("C34", "1"))
L08.net("M2_PWR_EN", ("U7", "14"), ("R21", "1"))
L08.net("M2_PGOOD", ("U7", "2"), ("R24", "1"))
L08.net("EF2_PGTH", ("U7", "3"), ("R25", "2"), ("R26", "1"))
L08.net("EF2_ILIM", ("U7", "17"), ("R22", "1"))
L08.net("EF2_IMON", ("U7", "19"), ("R23", "1"))
L08.net("EF2_DVDT", ("U7", "18"), ("C31", "1"))
L08.net("I2C_SDA", ("U8", "4"), ("R27", "1"))
L08.net("I2C_SCL", ("U8", "5"), ("R28", "1"))
L08.net("INA_ALERT", ("U8", "3"), ("R29", "1"))
L08.net("+3V3", ("U8", "6"), ("C32", "1"), ("R24", "2"), ("R27", "2"),
        ("R28", "2"), ("R29", "2"))
L08.net("GND", ("J3", "2"), ("D6", "2"), ("C30", "2"), ("U7", "16"), ("U7", "21"),
        ("U7", "1"), ("U7", "15"), ("R21", "2"), ("R22", "2"), ("R23", "2"),
        ("R26", "2"), ("C31", "2"), ("C32", "2"), ("C33", "2"), ("C34", "2"),
        ("U8", "7"), ("U8", "1"), ("U8", "2"))
L08.powerflag_nets = ["MAIN5V_F"]
GLOBALS_08 = {"M2_5V", "M2_PWR_EN", "M2_PGOOD", "INA_ALERT", "I2C_SDA", "I2C_SCL"}


def compose_08():
    c = cec_sch_compose.Compose(L08, LIBS)
    c.place("J3", 4, 24)
    c.place("F1", 20, 20)
    c.place("D6", 30, 28, 90)
    c.place("C30", 38, 28)
    c.place("U7", 62, 38)
    c.place("RS1", 96, 20)
    c.place("U8", 96, 52)
    # tie the stacked IN pins (9-13) with drawn wires. The label leaves from
    # pin 13 (the BOTTOM of the stack) -- pins 14/15 (EN/OVP) sit directly
    # ABOVE pin 9 in the symbol's left column, so an upward tap would land
    # exactly on pin 15's connection point (measured: it merged MAIN5V_F into
    # the OVP/GND strap on the first pass).
    pin13 = c.pin("U7", "13")
    for a, b in (("9", "10"), ("10", "11"), ("11", "12"), ("12", "13")):
        c.wire(c.pin("U7", a), c.pin("U7", b))
    c.wire(pin13, (pin13[0], pin13[1] + 2))
    c.label("MAIN5V_F", pin13[0], pin13[1] + 2, 90)
    c.use(("U7", "9"), ("U7", "10"), ("U7", "11"), ("U7", "12"), ("U7", "13"))
    # tie the stacked OUT pins (4-8); pin 17 (ILIM) sits directly below pin 8,
    # so the tap leaves UPWARD from pin 4 (pin 2 is 2 rows above -- clear).
    pin4 = c.pin("U7", "4")
    for a, b in (("4", "5"), ("5", "6"), ("6", "7"), ("7", "8")):
        c.wire(c.pin("U7", a), c.pin("U7", b))
    c.wire(pin4, (pin4[0], pin4[1] - 2))
    c.label("M2_5V_SW", pin4[0], pin4[1] - 2, 270)
    c.use(("U7", "4"), ("U7", "5"), ("U7", "6"), ("U7", "7"), ("U7", "8"))
    # rot-90 passives need >=12u pitch: the stub end of one lands on the
    # neighbor's stub wire at 8u (measured net-merge, first pass)
    c.place("R21", 26, 58, 90)
    c.place("R22", 38, 58, 90)
    c.place("R23", 50, 58, 90)
    c.place("C31", 62, 58)
    c.place("R25", 92, 29, 90)   # odd-u rows: clear of U7's right pin rows
    c.place("R26", 92, 37, 90)
    c.place("R24", 116, 31, 90)
    c.place("R27", 116, 45, 90)
    c.place("R28", 128, 45, 90)
    c.place("R29", 140, 45, 90)
    c.place("C32", 108, 66)
    c.place("C33", 118, 74)
    c.place("C34", 130, 74)
    c.caption("Compute-rail power: monitored MAIN_5V -> fuse+TVS -> TPS25940 eFuse "
              "(P4 EN) -> 25m shunt + INA238 -> M2_5V", 0, -2)
    c.note("K1 row 8: the AX630C's draw is a locally MEASURED signature (INA238 @ 0x40,\n"
           "ALERT -> P4). M2_PWR_EN pulled LOW = compute OFF by default (13.4 STANDBY\n"
           "posture: P4 trust endpoint lives on RJ-45 5VSB, compute rail on MAIN_5V, S0\n"
           "only). Design point ~1A avg / 2A fuse+ILIM; 6x 5V-VIN fingers on 09.\n"
           "TPS25940 app values ILLUSTRATIVE (flag F6): ILIM/dVdT/PGTH/OVP-to-GND all\n"
           "pend datasheet sizing. Assume-bad actuation: P4 can hard power-cycle the\n"
           "module into a freshly-measured state at any time (C2 row 14).", 0, 84)
    c.done()


# ===========================================================================
# LEAF 09 -- m2-module: the two M.2 M-key sockets (M3C dual-edge), TF boot
# storage, the 1.8V supervisor control domain (reset/straps/RSTN_OUT).
# ===========================================================================
L09 = Leaf("09", "09-m2-module.kicad_sch", "09-m2-module",
           "Sipeed M3C dual M.2 M-key sockets: 6x 5V-VIN, carrier-owned boot "
           "(TF on SD fingers + strap-forced X/X/X/0), P4-owned reset, EPHY dark")
def _p9(ref, lib, name, val, fp, props=None):
    L09.add_part(ref, lib, name, val, 0, 0, fp, props=props)
_p9("J4", "ent-kvm-local", "M2_MKEY_A_M3C", "M2-MKEY-75P-A", "",
    {"LCSC": "C41430858", "MPN": "HYCW23M-05NGFF-670B", "Manufacturer": "HYCW",
     "Note": "socket candidate -- M-keying/height/spacing pend Sipeed mech drawing (flag F4)"})
_p9("J5", "ent-kvm-local", "M2_MKEY_B_M3C", "M2-MKEY-75P-B", "",
    {"LCSC": "C41430858", "MPN": "HYCW23M-05NGFF-670B", "Manufacturer": "HYCW",
     "Note": "same socket part as J4 (flag F4)"})
_p9("J6", "ent-kvm-local", "TF_CARD_TF123", "TF-123-ARP9H17", "",
    {"LCSC": "C2982548", "MPN": "TF-123-ARP9H17", "Manufacturer": "Lianjie",
     "Note": "carrier boot storage (A5 option i); industrial-grade card at BOM lock"})
_p9("U10", "cec-vendor", "LP5907MFX-1.2", "LP5907MFX-1.8",
    "cec-Package_TO_SOT_SMD:SOT-23-5",
    {"MPN": "LP5907MFX-1.8", "Manufacturer": "TI",
     "Note": "1.8V control-domain LDO; TI part LCSC-unlisted -- XLP5907MFX-1.8 C51953294 "
             "clone or consign (flag F7); always-on (EN=IN)"})
_p9("Q1", "ent-kvm-local", "Q_NMOS_GSD", "2N7002",
    "cec-Package_TO_SOT_SMD:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR",
    {"LCSC": "C8545", "MPN": "2N7002", "Manufacturer": "-",
     "Note": "reset drive: default ON -> SYS_RSTN_IN held LOW (verify-then-release, flag F9)"})
_p9("Q2", "ent-kvm-local", "Q_NMOS_GSD", "2N7002",
    "cec-Package_TO_SOT_SMD:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR",
    {"LCSC": "C8545", "MPN": "2N7002", "Manufacturer": "-",
     "Note": "boot strap: default ON -> GPIO3_A2 low = SD/USB ROM path (flag F8)"})
_p9("Q3", "ent-kvm-local", "Q_NMOS_GSD", "BSS138",
    "cec-Package_TO_SOT_SMD:SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR",
    {"LCSC": "C112239", "MPN": "BSS138", "Manufacturer": "-",
     "Note": "SYS_RSTN_OUT 1.8->3.3 level shift (BSS138 Vth fits the 1.8V gate rail)"})
for _r, _v, _note in [
        ("R32", "100k", "Q1 gate pull-up -> default reset-asserted"),
        ("R33", "10k", "SYS_RSTN_IN pull-up to +1V8_CTL (release level)"),
        ("R34", "100k", "Q2 gate pull-up -> default strap-forced"),
        ("R36", "10k", "RSTN_OUT_3V3 pull-up"),
        ("R37", "10k DNP", "GPIO3_A3 pull-up provision: populate + module R24->NC "
                           "for NOR boot ONLY (not a CEC-supported path; 378C p4 note)"),
        ("R38", "33", "UART0 series"), ("R39", "33", "UART0 series"),
        ("R40", "33", "UART2 series"), ("R41", "33", "UART2 series"),
        ("R42", "33", "PPS0 series")]:
    _p9(_r, "cec-vendor", "R_Small", _v, "cec-Resistor_SMD:R_0402_1005Metric",
        {"Note": _note} if _note else None)
_p9("C36", "cec-vendor", "C_Small", "1u", "cec-Capacitor_SMD:C_0603_1608Metric")
_p9("C37", "cec-vendor", "C_Small", "1u", "cec-Capacitor_SMD:C_0603_1608Metric")
_p9("C38", "cec-vendor", "C_Small", "47u", "cec-Capacitor_SMD:C_1210_3225Metric",
    {"Note": "M2_5V bulk (mirrors 379C p1 C198/C199)"})
_p9("C39", "cec-vendor", "C_Small", "47u", "cec-Capacitor_SMD:C_1210_3225Metric")
_p9("C40", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric")
_p9("C41", "cec-vendor", "C_Small", "10u", "cec-Capacitor_SMD:C_0805_2012Metric")
_p9("C42", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric")

L09.net("M2_5V", *([("J5", str(n)) for n in M2B_5V]
                   + [("C38", "1"), ("C39", "1"), ("C40", "1")]))
L09.net("M2_USB_D_P", ("J5", "20"))
L09.net("M2_USB_D_N", ("J5", "22"))
L09.net("M2_SYS_RSTN", ("J4", "72"), ("J5", "29"), ("Q1", "3"), ("R33", "1"))
L09.net("M2_RSTN_GATE", ("Q1", "1"), ("R32", "1"))
L09.net("M2_BOOT_A2", ("J4", "74"), ("Q2", "3"))
L09.net("M2_BOOTSTRAP_GATE", ("Q2", "1"), ("R34", "1"))
L09.net("M2_BOOT_A3", ("J4", "16"), ("R37", "1"))
L09.net("M2_RSTN_OUT_A", ("J4", "10"), ("Q3", "2"))
L09.net("M2_RSTN_OUT_3V3", ("Q3", "3"), ("R36", "1"))
L09.net("M2_UART0_RXD_A", ("J4", "68"), ("R38", "1"))
L09.net("M2_UART0_RXD", ("R38", "2"))
L09.net("M2_UART0_TXD_A", ("J4", "70"), ("R39", "1"))
L09.net("M2_UART0_TXD", ("R39", "2"))
L09.net("M2_UART2_RXD_A", ("J4", "2"), ("R40", "1"))
L09.net("M2_UART2_RXD", ("R40", "2"))
L09.net("M2_UART2_TXD_A", ("J4", "4"), ("R41", "1"))
L09.net("M2_UART2_TXD", ("R41", "2"))
L09.net("M2_PPS0_B", ("J5", "33"), ("R42", "1"))
L09.net("M2_PPS0", ("R42", "2"))
# MIPI CSI lane set (flag F5: clock centered on RX_CD2, camera-FPC pair set)
L09.net("M2_CSI_D0_P", ("J5", "49"))
L09.net("M2_CSI_D0_N", ("J5", "51"))
L09.net("M2_CSI_D1_P", ("J5", "55"))
L09.net("M2_CSI_D1_N", ("J5", "57"))
L09.net("M2_CSI_CLK_P", ("J5", "67"))
L09.net("M2_CSI_CLK_N", ("J5", "69"))
L09.net("M2_CSI_D2_P", ("J5", "73"))
L09.net("M2_CSI_D2_N", ("J5", "75"))
L09.net("M2_CSI_D3_P", ("J4", "1"))
L09.net("M2_CSI_D3_N", ("J4", "3"))
# carrier-owned boot storage on the SD fingers (A5 option i)
L09.net("M2_SD_DAT0", ("J4", "51"), ("J6", "7"))
L09.net("M2_SD_DAT1", ("J4", "49"), ("J6", "8"))
L09.net("M2_SD_DAT2", ("J4", "47"), ("J6", "1"))
L09.net("M2_SD_DAT3", ("J4", "55"), ("J6", "2"))
L09.net("M2_SD_CMD", ("J4", "53"), ("J6", "3"))
L09.net("M2_SD_CLK", ("J4", "57"), ("J6", "5"))
L09.net("+1V8_CTL", ("U10", "5"), ("C37", "1"), ("R33", "2"), ("Q3", "1"),
        ("R37", "2"))
L09.net("+3V3", ("U10", "1"), ("U10", "3"), ("C36", "1"),
        ("R32", "2"), ("R34", "2"), ("R36", "2"),
        ("J6", "4"), ("C41", "1"), ("C42", "1"))
L09.net("GND", *([("J4", str(n)) for n in M2A_GND]
                 + [("J5", str(n)) for n in M2B_GND]
                 + [("Q1", "2"), ("Q2", "2"), ("U10", "2"),
                    ("C36", "2"), ("C37", "2"), ("C38", "2"), ("C39", "2"),
                    ("C40", "2"), ("C41", "2"), ("C42", "2"),
                    ("J6", "6"), ("J6", "9"),
                    ("J6", "10"), ("J6", "11"), ("J6", "12"), ("J6", "13")]))
GLOBALS_09 = ({"M2_5V", "M2_USB_D_P", "M2_USB_D_N", "M2_RSTN_GATE",
               "M2_BOOTSTRAP_GATE", "M2_RSTN_OUT_3V3", "M2_UART0_RXD",
               "M2_UART0_TXD", "M2_UART2_RXD", "M2_UART2_TXD", "M2_PPS0"}
              | {f"M2_CSI_{x}_{pn}" for x in ("D0", "D1", "D2", "D3", "CLK")
                 for pn in ("P", "N")})


def compose_09():
    c = cec_sch_compose.Compose(L09, LIBS)
    c.place("J4", 36, 56)
    c.place("J5", 120, 56)
    c.place("J6", 186, 24)
    c.place("U10", 186, 56)
    c.place("C36", 172, 66)
    c.place("C37", 200, 66)
    c.place("Q1", 176, 92)
    c.place("R32", 164, 90, 90)
    c.place("R33", 190, 84, 90)
    c.place("Q2", 176, 112)
    c.place("R34", 164, 110, 90)
    c.place("R37", 190, 104, 90)
    c.place("Q3", 176, 132)
    c.place("R36", 190, 126, 90)
    c.place("R38", 24, 118, 90)
    c.place("R39", 32, 118, 90)
    c.place("R40", 40, 118, 90)
    c.place("R41", 48, 118, 90)
    c.place("R42", 56, 118, 90)
    c.place("C38", 108, 118)
    c.place("C39", 116, 118)
    c.place("C40", 124, 118)
    c.place("C41", 132, 118)
    c.place("C42", 140, 118)
    c.caption("Sipeed M3C compute module -- dual M.2 M-key 75-pos sockets "
              "(A-edge J4 / B-edge J5, 378C p12)", 0, -6)
    c.region("Supervisor control domain (P4-owned reset/straps, 1.8V via U10)",
             158, 76, 210, 142)
    c.note("BOOT POLICY (F8, owner-ruled carrier-owned boot): Q2 default-ON forces\n"
           "GPIO3_A2=0 -> ROM 'USB DL or SD Card or UART' path -> boots the CARRIER TF\n"
           "card (J6) or the P4-gated USB0 (AXDL). Module eMMC boot = P4 drives\n"
           "M2_BOOTSTRAP_GATE low (policy option ii). GPIO3_A3 default 0 on-module\n"
           "(R24 47k); R37 = DNP NOR-boot provision only.\n"
           "RESET CONTRACT (F9): Q1 default-ON holds SYS_RSTN_IN low; firmware holds\n"
           ">=100ms after power-good (379C p9), verifies boot storage, THEN releases.\n"
           "Assert reset BEFORE M2_PWR_EN. SYS_RSTN_OUT returns via Q3 (1.8->3.3).",
           0, 112)
    c.note("ZERO-EGRESS RULE (K1 row 12 / spec 13.6) -- VERIFIABLE ABSENCE:\n"
           "EPHY MDI fingers A67/69/73/75 UNCONNECTED + NO magnetics anywhere = the\n"
           "on-die 100M PHY is dark by construction. SDIO group (A27..A37 odd, the\n"
           "MaixCam2 WiFi bus) UNCONNECTED -- no radio is mountable. RGMII bank (B-edge\n"
           "GPIO1 group) UNCONNECTED -- no GbE PHY exists. I2C0 (A43/A45) unconnected --\n"
           "bridge config is P4-owned (F11). A50 'keep low during booting' left open.\n"
           "TX_CD (DSI/BT656) + audio (MIC/HP) groups unconnected -- no function in the\n"
           "KVM role. Every no-connect X on J4/J5 is part of the auditable statement.",
           88, 130)
    c.done()


# ===========================================================================
# LEAF 10 -- hdmi-capture: HDMI-A -> ESD -> LT6911-class bridge -> CSI.
# ===========================================================================
L10 = Leaf("10", "10-hdmi-capture.kicad_sch", "10-hdmi-capture",
           "HDMI-A input -> RClamp0524P ESD -> LT6911-class HDMI-to-CSI bridge "
           "(consigned, flag F2) -> 4-lane MIPI CSI to the M3C RX_CD fingers")
def _p10(ref, lib, name, val, fp, props=None):
    L10.add_part(ref, lib, name, val, 0, 0, fp, props=props)
_p10("J7", "ent-kvm-local", "HDMI_A_19P", "HDMI-A", "",
     {"LCSC": "C138388", "MPN": "HDMI-001 19PCBTP", "Manufacturer": "-",
      "Note": "generic-catalog candidate, land verify at footprint intake (flag F12)"})
_p10("U11", "ent-kvm-local", "LT6911_FUNC", "LT6911-CLASS", "",
     {"MPN": "LT6911C/UXC-class (TBD)", "Manufacturer": "Lontium",
      "Note": "CONSIGNED/PENDING -- not LCSC-stocked; functional placeholder symbol (flag F2)"})
for _d in ("D7", "D8", "D9"):
    _p10(_d, "cec-ent-net", "RClamp0524PATCT", "RClamp0524P",
         "cec-ent-net:DIO-DT-SMD-3P_L7.5-W5.0" if False else "",
         {"LCSC": "C40960", "MPN": "RClamp0524PATCT", "Manufacturer": "Semtech"})
_p10("R43", "cec-vendor", "R_Small", "10k", "cec-Resistor_SMD:R_0402_1005Metric")
_p10("R44", "cec-vendor", "R_Small", "10k", "cec-Resistor_SMD:R_0402_1005Metric")
_p10("R48", "cec-vendor", "R_Small", "10k", "cec-Resistor_SMD:R_0402_1005Metric",
     {"Note": "bridge RESET_N pull-down: capture held in reset until the P4 enables it"})
_p10("R49", "cec-vendor", "R_Small", "10k", "cec-Resistor_SMD:R_0402_1005Metric")
_p10("C43", "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric")
_p10("C44", "cec-vendor", "C_Small", "10u", "cec-Capacitor_SMD:C_0805_2012Metric")
for _c in ("C45", "C46", "C47"):
    _p10(_c, "cec-vendor", "C_Small", "100n", "cec-Capacitor_SMD:C_0402_1005Metric")

L10.net("HDMI_D2_P", ("J7", "1"), ("D7", "1"), ("U11", "1"))
L10.net("HDMI_D2_N", ("J7", "3"), ("D7", "2"), ("U11", "2"))
L10.net("HDMI_D1_P", ("J7", "4"), ("D7", "4"), ("U11", "3"))
L10.net("HDMI_D1_N", ("J7", "6"), ("D7", "5"), ("U11", "4"))
L10.net("HDMI_D0_P", ("J7", "7"), ("D8", "1"), ("U11", "5"))
L10.net("HDMI_D0_N", ("J7", "9"), ("D8", "2"), ("U11", "6"))
L10.net("HDMI_CK_P", ("J7", "10"), ("D8", "4"), ("U11", "7"))
L10.net("HDMI_CK_N", ("J7", "12"), ("D8", "5"), ("U11", "8"))
L10.net("HDMI_CEC", ("J7", "13"), ("D9", "1"), ("U11", "12"))
L10.net("HDMI_SCL", ("J7", "15"), ("D9", "2"), ("U11", "9"))
L10.net("HDMI_SDA", ("J7", "16"), ("D9", "4"), ("U11", "10"))
L10.net("HDMI_HPD", ("J7", "19"), ("D9", "5"), ("U11", "11"))
L10.net("HDMI_5V", ("J7", "18"), ("R43", "1"), ("C43", "1"))
L10.net("HDMI_5V_DIV", ("R43", "2"), ("R44", "1"), ("U11", "13"))
L10.net("LT_RESET_N", ("U11", "26"), ("R48", "1"))
L10.net("LT_INT", ("U11", "27"), ("R49", "1"))
L10.net("I2C_SCL", ("U11", "24"))
L10.net("I2C_SDA", ("U11", "25"))
for _lane, _pp, _pn in (("CLK", "14", "15"), ("D0", "16", "17"),
                        ("D1", "18", "19"), ("D2", "20", "21"),
                        ("D3", "22", "23")):
    L10.net(f"M2_CSI_{_lane}_P", ("U11", _pp))
    L10.net(f"M2_CSI_{_lane}_N", ("U11", _pn))
L10.net("+3V3", ("U11", "28"), ("U11", "29"), ("C44", "1"), ("C45", "1"),
        ("C46", "1"), ("C47", "1"), ("R49", "2"))
L10.net("GND", ("J7", "2"), ("J7", "5"), ("J7", "8"), ("J7", "11"), ("J7", "17"),
        ("J7", "SH1"), ("J7", "SH2"), ("J7", "SH3"), ("J7", "SH4"),
        ("D7", "3"), ("D7", "8"), ("D8", "3"), ("D8", "8"), ("D9", "3"), ("D9", "8"),
        ("R44", "2"), ("R48", "2"), ("C43", "2"), ("C44", "2"), ("C45", "2"),
        ("C46", "2"), ("C47", "2"), ("U11", "30"), ("U11", "31"))
L10.powerflag_nets = ["HDMI_5V"]
GLOBALS_10 = ({"LT_RESET_N", "LT_INT", "I2C_SDA", "I2C_SCL"}
              | {f"M2_CSI_{x}_{pn}" for x in ("D0", "D1", "D2", "D3", "CLK")
                 for pn in ("P", "N")})


def compose_10():
    c = cec_sch_compose.Compose(L10, LIBS)
    c.place("J7", 20, 40)
    c.place("D7", 52, 78, 0)
    c.place("D8", 66, 78, 0)
    c.place("D9", 80, 78, 0)
    c.place("U11", 84, 36)
    c.place("R43", 46, 6, 90)
    c.place("R44", 54, 6, 90)
    c.place("C43", 62, 8)
    c.place("R48", 116, 66, 90)
    # R49 (LT_INT pull-up) sits one row up from R48 (GND). Keeping both on the
    # same compose row put R49's LT_INT horizontal stub and R48's GND stub on the
    # SAME y-line with a GND power stamp between them; the two auto-routed stubs
    # overlapped (267.97..270.51 @ y161.29) and merged GND into LT_INT (150-node
    # collapse). Different row = the LT_INT wiring gets its own y-line, no overlap.
    c.place("R49", 124, 54, 90)
    c.place("C44", 108, 78)
    c.place("C45", 116, 82)
    c.place("C46", 124, 78)
    c.place("C47", 132, 82)
    c.caption("HDMI capture front-end -- the C4 architecture: HDMI-RX bridge into the "
              "module's CSI fingers", 0, -4)
    c.note("Bridge control is P4-OWNED (flag F11): I2C + RESET_N (R48 pull-down =\n"
           "capture dead until the trust endpoint enables it) + INT terminate on the\n"
           "P4, not the module -- the module receives configured CSI only. The\n"
           "runtime-ingress surface is the HDMI path itself (EDID/InfoFrame parsing of\n"
           "hostile host output) -- named in the C2 row-14 honest-limits language.\n"
           "CSI lane map: CLK on RX_CD2, data on RX_CD0/1/3/4 -- UNVERIFIED (flag F5).\n"
           "LT6911-class part is CONSIGNED (flag F2): logical pins, re-pin at intake;\n"
           "power tree modeled as VDD33-only pending the real datasheet.", 0, 96)
    c.done()


# ===========================================================================
# BUILD -- leaves then the thin-parent root.
# ===========================================================================
LEAVES = {"01": entc.L01, "02": entc.L02, "03": entc.L03, "04": L04,
          "05": entc.L05, "06": L06, "07": L07, "08": L08, "09": L09, "10": L10}
COMPOSES = {"01": entc.compose_01, "02": entc.compose_02, "03": entc.compose_03,
            "04": entc.compose_04, "05": entc.compose_05, "06": compose_06,
            "07": compose_07, "08": compose_08, "09": compose_09, "10": compose_10}
GLOBALS = {"01": set(), "02": set(), "03": set(), "04": GLOBALS_04, "05": set(),
           "06": GLOBALS_06, "07": GLOBALS_07, "08": GLOBALS_08, "09": GLOBALS_09,
           "10": GLOBALS_10}
LEAF_PAPER = {"01": "A4", "02": "A4", "03": "A4", "04": "A3", "05": "A4",
              "06": "A4", "07": "A4", "08": "A3", "09": "A2", "10": "A3"}

# Root sheet-pin sets: the six inherited ent-common nets keep their drawn
# wires (proven geometry); 04 loses its USB pair (global now); 06/07/08/09/10
# are pinless boxes (all carrier nets are globals, flag F10).
PARENT_PINS = {
    "01": entc.PARENT_PINS["01"],
    "02": entc.PARENT_PINS["02"],
    "03": entc.PARENT_PINS["03"],
    "04": [(n, s) for (n, s) in entc.PARENT_PINS["04"]
           if n not in ("USB_D_P", "USB_D_N")],
    "05": entc.PARENT_PINS["05"],
    "06": [], "07": [], "08": [], "09": [], "10": [],
}
BOX = {  # grid units; 01-05 keep the proven ent-common root geometry
    "01": (4, 8, 44, 36),
    "02": (60, 24, 40, 16),
    "03": (60, 56, 40, 22),
    "04": (112, 24, 48, 56),
    "05": (196, 8, 44, 68),
    "06": (4, 112, 44, 16),
    "07": (60, 112, 40, 16),
    "08": (112, 112, 48, 16),
    "09": (172, 112, 48, 20),
    "10": (232, 112, 44, 16),
}
SHEET_DESC = {
    "06": "host USB-C (6.14)", "07": "TS3USB221 USB gate",
    "08": "monitored compute 5V", "09": "M3C sockets + boot + reset",
    "10": "HDMI -> CSI bridge",
}


def main():
    for lid in sorted(COMPOSES):
        COMPOSES[lid]()

    total_parts = 0
    for li, lid in enumerate(sorted(LEAVES)):
        lf = LEAVES[lid]
        assert {n for n, _s in PARENT_PINS[lid]} == set(lf.hier_exports), lid
        stats = cec_sch_compose.build_leaf(
            lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None,
            LIBS, PROJECT,
            path_prefix=f"{ROOT_UUID}/{LEAF_SYM_UUIDS[lid]}",
            sheet_instances_path=LEAF_SYM_UUIDS[lid],
            own_uuid=LEAF_OWN_UUIDS[lid],
            page=str(li + 2), out_path=os.path.join(OUT, lf.filename),
            paper=LEAF_PAPER[lid],
            title=f"CEC ENT KVM carrier: {lf.sheetname}",
            comment1=lf.desc,
            pwr_base=100 * (li + 1), layout=lf.layout,
            global_nets=GLOBALS[lid])
        total_parts += stats["parts"]
        n_moved, still = cec_sch_layout.nudge_texts(os.path.join(OUT, lf.filename))
        stats["nudged"], stats["text_overlaps_left"] = n_moved, still
        print(f"{lf.filename}  " + "  ".join(f"{k}={v}" for k, v in stats.items()))

    u = cec_sch.GRID
    leaves_for_parent = []
    for li, lid in enumerate(sorted(LEAVES)):
        lf = LEAVES[lid]
        bx, by, bw, bh = BOX[lid]
        leaves_for_parent.append({
            "id": lid, "sym_uuid": LEAF_SYM_UUIDS[lid], "filename": lf.filename,
            "sheetname": lf.sheetname, "page": str(li + 2),
            "x": bx * u, "y": by * u, "w": bw * u, "h": bh * u,
            "pins": [(name, lf.hier_exports[name][0], side)
                     for name, side in PARENT_PINS[lid]],
        })
    parent_stats = cec_sch_compose.build_thin_parent(
        leaves_for_parent, set(), PROJECT, ROOT_UUID,
        None, ROOT_UUID, out_path=os.path.join(OUT, f"{PROJECT}.kicad_sch"),
        title="CEC ENT KVM carrier -- Path C (M3C on CEC carrier, P4-fronted)",
        paper="A2", global_power_exports=None, libs=LIBS, pwr_base=700,
        title_comments=(
            "DRAFT / ENT lane. Owner ruling 2026-07-06: Path C -- Sipeed M3C compute "
            "module on a CEC carrier behind the uniform P4 trust endpoint",
            "Sheets 01-05 = the ent-common P4+T1 block (reused wholesale; 04 gains "
            "supervisor GPIOs); 06-10 = carrier: USB gate, compute power, sockets, HDMI",
            "Inherited nets cross as drawn sheet-pin wires; ALL new carrier nets are "
            "GLOBAL LABELS (flag F10 -- the 1:1 lane router cannot express the buses)",
            "Zero-egress: T1 is the ONLY network silicon; module EPHY unmagnetized, "
            "SDIO/RGMII dark (verifiable absence, spec 13.6)"))
    print(f"{PROJECT}.kicad_sch (root thin parent)  "
          + "  ".join(f"{k}={v}" for k, v in parent_stats.items())
          + f"  total_leaf_parts={total_parts}")

    # ---- project scaffolding -------------------------------------------
    with open(os.path.join(OUT, f"{PROJECT}.kicad_pro"), "w") as f:
        f.write('{\n  "meta": {\n    "filename": "%s.kicad_pro",\n    "version": 1\n  }\n}\n'
                % PROJECT)
    with open(os.path.join(OUT, "sym-lib-table"), "w") as f:
        f.write("""(sym_lib_table
  (version 7)
  (lib (name "cec")(type "KiCad")(uri "${KIPRJMOD}/../../lib/cec.kicad_sym")(options "")(descr "CEC shared symbols"))
  (lib (name "cec-vendor")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/cec-vendor.kicad_sym")(options "")(descr "Vendored official symbols, pinned"))
  (lib (name "cec-power")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/cec-power.kicad_sym")(options "")(descr "Vendored power/ground symbols, pinned"))
  (lib (name "cec-ent-power")(type "KiCad")(uri "${KIPRJMOD}/../../lib/cec-ent-power.kicad_sym")(options "")(descr "ENT library intake: power group"))
  (lib (name "cec-ent-net")(type "KiCad")(uri "${KIPRJMOD}/../../lib/cec-ent-net.kicad_sym")(options "")(descr "ENT library intake: network group"))
  (lib (name "cec-ent-mcu")(type "KiCad")(uri "${KIPRJMOD}/../../lib/cec-ent-mcu.kicad_sym")(options "")(descr "ENT library intake: MCU group"))
  (lib (name "ent-common-local")(type "KiCad")(uri "${KIPRJMOD}/../ent-common/ent-common-local.kicad_sym")(options "")(descr "ent-common project-local stopgaps (Crystal_Small, widened RJ45)"))
  (lib (name "ent-kvm-local")(type "KiCad")(uri "${KIPRJMOD}/ent-kvm-local.kicad_sym")(options "")(descr "ent-kvm-carrier project-local parts: M3C M.2 socket pin maps, LT6911-class + TS3USB221 functional placeholders, TF/HDMI/FET/fuse/TVS"))
)
""")
    with open(os.path.join(OUT, "fp-lib-table"), "w") as f:
        f.write("""(fp_lib_table
  (version 7)
  (lib (name "cec")(type "KiCad")(uri "${KIPRJMOD}/../../lib/cec.pretty")(options "")(descr "CEC shared footprints"))
  (lib (name "cec-Package_SO")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Package_SO.pretty")(options "")(descr ""))
  (lib (name "cec-Package_TO_SOT_SMD")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Package_TO_SOT_SMD.pretty")(options "")(descr ""))
  (lib (name "cec-Package_DFN_QFN")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Package_DFN_QFN.pretty")(options "")(descr ""))
  (lib (name "cec-Resistor_SMD")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Resistor_SMD.pretty")(options "")(descr ""))
  (lib (name "cec-Capacitor_SMD")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Capacitor_SMD.pretty")(options "")(descr ""))
  (lib (name "cec-Diode_SMD")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Diode_SMD.pretty")(options "")(descr ""))
  (lib (name "cec-Connector_USB")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Connector_USB.pretty")(options "")(descr ""))
  (lib (name "cec-Connector_JST")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Connector_JST.pretty")(options "")(descr ""))
  (lib (name "cec-Button_Switch_SMD")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Button_Switch_SMD.pretty")(options "")(descr ""))
  (lib (name "cec-ent-mcu")(type "KiCad")(uri "${KIPRJMOD}/../../lib/cec-ent-mcu.pretty")(options "")(descr ""))
  (lib (name "cec-ent-net")(type "KiCad")(uri "${KIPRJMOD}/../../lib/cec-ent-net.pretty")(options "")(descr ""))
)
""")
    with open(os.path.join(OUT, "DRAFT"), "w") as f:
        f.write("ENT KVM carrier -- schematic-only DRAFT (Path C, owner ruling "
                "2026-07-06). No PCB exists. Fit-check/consigned-part flags open; "
                "see README.md FLAGS.\n")


if __name__ == "__main__":
    main()
