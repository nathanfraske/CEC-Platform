#!/usr/bin/env python3
"""Recompose the current authoritative BETA hierarchies by function.

The live hierarchy is the default electrical/inventory source. Archived flat
captures are accepted only through an explicit --source migration request.
Every orderable property and numbered-pin net membership is gated.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import uuid
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import cec_pcb_reconcile as R  # noqa: E402
import cec_sch  # noqa: E402
import cec_sch_compose as C  # noqa: E402
import cec_sch_gates as G  # noqa: E402
import cec_sch_layout as L  # noqa: E402
import cec_spice_sanity  # noqa: E402

LIBS = {
    "cec": open(os.path.join(ROOT, "lib", "cec.kicad_sym"), encoding="utf-8").read(),
    "cec-vendor": open(os.path.join(ROOT, "lib", "vendor", "cec-vendor.kicad_sym"), encoding="utf-8").read(),
    "power": open(os.path.join(ROOT, "lib", "vendor", "cec-power.kicad_sym"), encoding="utf-8").read(),
}
POWER_PORTS = {name: name for name in ("GND", "+3V3", "+5VSB", "+5V_SYS", "+5V_MAIN")}
POWER_NETS = set(POWER_PORTS)
GLOBAL_NETS = set()
_LABEL_LINE_RE = re.compile(
    r'\t\(label "([^"]+)" \(at ([\d.\-]+) ([\d.\-]+) (\d+)\) \(effects[^\n]*\n')


def rows(*items: str) -> list[list[str]]:
    return [s.split() for s in items]


CONFIG = {
    "hub-standard-rev2": {
        "live": "beta/hub-standard-rev2/hub-standard-rev2.kicad_sch",
        "archive": "old-revisions/beta/hub-standard-rev2-flat-2026-08-02/hub-standard-rev2.kicad_sch",
        # The old H2 boost -> second-buck reservation was deliberately never a
        # complete application circuit (its inductor and several mandatory
        # passives were bench-TBD).  It is preserved in the archived flat
        # capture, but carrying the position-only rung in the live BETA wastes
        # board area and makes an unfinished option look production-capable.
        "retired_refs": {"RJ_BUCK", "U9", "U10", "L2", "R29", "R30", "R31", "R32",
                         # DL6 was the non-ring LED below/right of the logo.
                         # The six-device ring already carries the intended
                         # status language; preserve DL6 only in the archive.
                         "DL6"},
        # Electrically bypass the retired LED in the addressable chain.
        "net_overrides": {("DL7", "3"): "Net-(DL5-DOUT)"},
        "flags": {"01-power-input-selection": ["GND", "+5VSB", "5VSB_RAW", "USB_VBUS", "PSU_5V",
                                                     "MAIN_5V_RAW", "PSU_5V_KVM", "KVM_5V_IN"],
                  "02-holdup-3v3": ["+3V3", "LOGIC_REG_IN"]},
        "property_overrides": {
            **{f"DL{i}": {
                "footprint": "cec-LED_SMD:LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount",
                "props": {"Datasheet": "https://datasheet.lcsc.com/lcsc/1810231311_OPSCO-Optoelectronics-SK6812MINI-E_C5149201.pdf",
                          "MPN": "SK6812MINI-E", "Manufacturer": "OPSCO Optoelectronics",
                          "LCSC": "C5149201"}}
               for i in (1, 2, 3, 4, 5, 7)},
            "C14": {"props": {
                "Note": "SN74AHCT1G08 U6 local 100nF bypass; place directly at VCC/GND."}},
            "J6P": {"footprint": "cec-Connector_PinSocket_2.54mm:PinSocket_2x03_P2.54mm_Vertical",
                    "props": {"MPN": "SSQ-103-03-G-D", "Manufacturer": "Samtec",
                              "Datasheet": "https://suddendocs.samtec.com/catalog_english/ssw_th.pdf",
                              "Note": "Exact 2x3 Hub socket; mates ATX TSW-103-17-G-D in the 18mm dead-bug stack."}},
            "J6C": {"footprint": "cec-Connector_PinSocket_2.54mm:PinSocket_2x04_P2.54mm_Vertical",
                    "props": {"MPN": "SSQ-104-03-G-D", "Manufacturer": "Samtec",
                              "Datasheet": "https://suddendocs.samtec.com/catalog_english/ssw_th.pdf",
                              "Note": "Exact 2x4 Hub socket; mates ATX TSW-104-17-G-D in the 18mm dead-bug stack. STREAM_P/N are intentionally NC on both Standard boards."}},
            "J6D": {"footprint": "cec-Connector_PinSocket_2.54mm:PinSocket_2x02_P2.54mm_Vertical",
                    "props": {"MPN": "SSQ-102-03-G-D", "Manufacturer": "Samtec",
                              "Datasheet": "https://suddendocs.samtec.com/catalog_english/ssw_th.pdf",
                              "Note": "Exact 2x2 Hub socket; mates ATX TSW-102-17-G-D in the 18mm dead-bug stack. RSVD is intentionally NC."}},
            "RJ_HOLD": {"props": {
                "Datasheet": "https://www.lcsc.com/product-detail/C17168.html",
                "Description": "Populated 0-ohm link from the post-diode +5V hold-up reservoir to the complete TLV62569 3.3V buck stage."}},
        },
        "synthetic_parts": {
            f"C{29 + index}": {
                "leaf": "06-status-leds", "lib_id": "cec-vendor:C_Small",
                "value": "100nF", "footprint": "cec-Capacitor_SMD:C_0402_1005Metric",
                "nets": {"1": "+5VSB", "2": "GND"},
                "props": {
                    "Manufacturer": "Samsung", "MPN": "CL05B104KO5NNNC",
                    "LCSC": "C1525",
                    "Datasheet": "https://product.samsungsem.com/mlcc/CL05B104KO5NNN.do",
                    "Note": f"Dedicated 100nF local bypass for DL{led}; place directly at VDD/VSS."
                }
            }
            for index, led in enumerate((1, 2, 3, 4, 5, 7))
        },
        "leaves": [
            ("01-power-input-selection", "POWER INPUT + SOURCE SELECTION",
             "Three TPS2121 stages, protected inputs, current limits, OV thresholds and local reservoirs.",
             rows("J_PWR D8 D9 U5 U7 U11", "C9 C15 C22 C23 C24 C25 C26 C27 C28 C_SS1 C_SS2 C_SS3 C_bulk1",
                  "R_ILIM1 R_ILIM2 R_ILIM3 R33 R34 R35 R36 R37 R38")),
            ("02-holdup-3v3", "HOLD-UP + 3V3 REGULATOR",
             "5VSB loss detection precedes the hold-up diode; shutdown is requested before reservoir or regulator dropout.",
             rows("D1 C1 RJ_HOLD", "U3 L1 C2 C3 U8 C17",
                  "R12 R13 C12 R26 R27 R28 R39 R40")),
            ("03-mcu-usb", "MCU + USB SERVICE PORT",
             "ESP32-S3 control, reset/boot supervision and protected USB-C service ingress.",
             rows("J_USB D6 U1 U4", "C4 C6 C8 C10 C11 C13 R2 R9 R10 R11 SW_BOOT SW_RESET")),
            ("04-can-module-ports", "CAN + FOUR MODULE PORTS + STACK",
             "One shared CAN segment, four fused module feeds, DETECT protection/filtering and the structural stack interface.",
             rows("U2 J2 J3 J4 J5 J6C J6D J6P", "F1 F2 F3 F4 D2 D3 D4 D5",
                  "C5 C7 C18 C19 C20 C21 R3 R4 R5 R6 R7 R8")),
            ("05-kvm-aux-sensors", "KVM AUXILIARY + RAIL SENSING",
             "Fused KVM feed, UART, rail dividers and hub temperature sensing.",
             rows("J_KVM F5 D7 TH1", "C16 R15 R16 R17 R18 R19 R20 R21 R22 R23 R24 R25")),
            ("06-status-leds", "STATUS LED CHAIN",
             "Level-shifted, series-damped six-device addressable status ring.",
             rows("U6 R14 DL1 DL2 DL3 DL4 DL5 DL7", "C14 C29 C30 C31 C32 C33 C34")),
        ],
    },
    "eps-8pin-rev3": {
        "live": "beta/eps-8pin-rev3/eps-8pin-rev3.kicad_sch",
        "archive": "old-revisions/beta/eps-8pin-rev3-flat-2026-08-02/eps-8pin-rev3.kicad_sch",
        "flags": {"02-regulator-mcu": ["GND", "+5VSB"]},
        "leaves": [
            ("01-hub-can", "HUB LINK + CAN", "Protected DETECT input and the module CAN transceiver at the hub connector.",
             rows("J1 D1 R1 R7 U2 C4 C8")),
            ("02-regulator-mcu", "3V3 REGULATOR + MCU", "LP5907 rail, ESP32-C6 control, boot/reset straps and local bypassing.",
             rows("U3 C1 C2", "U1 R2 R19 SW1 SW2 C3 C5 C7")),
            ("03-sensing", "DUAL-CABLE PRECISION + FAST SENSING",
             "Two repeated INA238 / INA181 / TLV7011 channels with a shared threshold and I2C pull-ups.",
             rows("R10 C40 R3 R4", "U10 U20 U30 C10 C20 C30", "U11 U21 U31 C11 C21 C31")),
            ("04-cable-power", "DUAL EPS POWER INTERPOSER",
             "Two independent PSU-to-load paths with Kelvin shunts; there is one EPS product, not a variant family.",
             rows("J_IN1 RS1 J_OUT1", "J_IN2 RS2 J_OUT2")),
            ("05-usb-service", "USB-C SERVICE INGRESS", "USB 2.0 service connector, CC terminations and 5VSB isolation diode.",
             rows("J5 D2 C6 C9 R8 R9")),
        ],
    },
    "atx-24pin-rev3": {
        "live": "beta/atx-24pin-rev3/24pin-module.kicad_sch",
        "archive": "old-revisions/beta/atx-24pin-rev3-flat-2026-08-02/24pin-module.kicad_sch",
        # J1 was the direct RJ-45 Hub link.  The segmented mezzanine now owns
        # that connection, so J1 is intentionally removed during authoritative
        # recomposition rather than left as an attractive obsolete option.
        "retired_refs": {"J1", "U3"},
        "property_overrides": {
            "C1": {"props": {"Manufacturer": "Samsung", "MPN": "CL10B105KA8NNNC",
                               "LCSC": "C29936",
                               "Datasheet": "https://product.samsungsem.com/mlcc/CL10B105KA8NNN.do",
                               "Note": "TLV75533 input local 1uF X7R; place at U3 IN/GND."}},
            **{ref: {"props": {
                "Manufacturer": "Samsung", "MPN": "CL10B105KA8NNNC",
                "LCSC": "C29936",
                "Datasheet": "https://product.samsungsem.com/mlcc/CL10B105KA8NNN.do",
                "Note": "Exact 1uF 25V X7R 0603 local bypass capacitor."
            }} for ref in ("C2", "C15", "C16", "C17", "C24")},
            "C14": {"props": {"Manufacturer": "Samsung", "MPN": "CL10B105KA8NNNC",
                                "LCSC": "C29936",
                                "Datasheet": "https://product.samsungsem.com/mlcc/CL10B105KA8NNN.do",
                                "Note": "TLV75533 output local 1uF X7R; place at U3 OUT/GND."}},
            "C25": {"props": {
                "Manufacturer": "Samsung", "MPN": "CL21A226MAQNNNE",
                "LCSC": "C45783",
                "Datasheet": "https://product.samsungsem.com/mlcc/CL21A226MPCLRN.do",
                "Note": "Exact 22uF 25V X5R 0805 source-mux reservoir capacitor."}},
            **{ref: {"props": {
                "Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1002TCE",
                "LCSC": "C25744",
                "Datasheet": "https://www.lcsc.com/product-detail/C25744.html"
            }} for ref in ("R2", "R10", "R51", "R60", "R61")},
            **{ref: {"props": {
                "Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1003TCE",
                "LCSC": "C25741",
                "Datasheet": "https://www.lcsc.com/product-detail/C25741.html"
            }} for ref in ("R7", "R52")},
            **{ref: {"props": {
                "Manufacturer": "UNI-ROYAL", "MPN": "0402WGF2201TCE",
                "LCSC": "C25879",
                "Datasheet": "https://www.lcsc.com/product-detail/C25879.html"
            }} for ref in ("R1", "R3", "R4")},
            **{ref: {"props": {
                "Manufacturer": "UNI-ROYAL", "MPN": "0402WGF5101TCE",
                "LCSC": "C25905",
                "Datasheet": "https://www.lcsc.com/product-detail/C25905.html"
            }} for ref in ("R8", "R9")},
            "R50": {"props": {
                "Manufacturer": "UNI-ROYAL", "MPN": "0402WGF2002TCE",
                "LCSC": "C25765",
                "Datasheet": "https://www.lcsc.com/product-detail/C25765.html"}},
            "R55": {"value": "43.2kΩ", "props": {
                "Manufacturer": "UNI-ROYAL", "MPN": "0402WGF4322TCE", "LCSC": "C25894",
                "Datasheet": "https://www.lcsc.com/product-detail/C25894.html",
                "Note": "U6 OV1 top: 43.2k/10k gives 5.618V nominal, 5.287..5.948V at 1%/VREF extremes."}},
            "J3": {"props": {
                "Manufacturer": "Molex", "MPN": "39291247",
                "Datasheet": "https://www.molex.com/en-us/products/part-detail/39291247",
                "Note": "24-circuit Mini-Fit Jr right-angle through-hole ATX input header."}},
            "J_SIG1": {
                "value": "SSQ-104-03-G-S",
                "footprint": "cec-Connector_PinSocket_2.54mm:PinSocket_1x04_P2.54mm_Vertical",
                "props": {
                    "Manufacturer": "Samtec", "MPN": "SSQ-104-03-G-S",
                    "Datasheet": "https://www.samtec.com/products/ssq-104-03-g-s",
                    "Note": "Vertical 1x4 socket; mates the daughterboard TSW-104-12-G-S-RA long-tail right-angle header pin-for-pin."}},
            "J6P": {"footprint": "cec-Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical",
                    "props": {"MPN": "TSW-103-17-G-D", "Manufacturer": "Samtec",
                              "Datasheet": "https://suddendocs.samtec.com/catalog_english/tsw_th.pdf",
                              "Note": "Exact 2x3 ATX long-post header; mates Hub SSQ-103-03-G-D in the 18mm dead-bug stack."}},
            "J6C": {"footprint": "cec-Connector_PinHeader_2.54mm:PinHeader_2x04_P2.54mm_Vertical",
                    "props": {"MPN": "TSW-104-17-G-D", "Manufacturer": "Samtec",
                              "Datasheet": "https://suddendocs.samtec.com/catalog_english/tsw_th.pdf",
                              "Note": "Exact 2x4 ATX long-post header; mates Hub SSQ-104-03-G-D in the 18mm dead-bug stack. STREAM_P/N are intentionally NC on both Standard boards."}},
            "J6D": {"footprint": "cec-Connector_PinHeader_2.54mm:PinHeader_2x02_P2.54mm_Vertical",
                    "props": {"MPN": "TSW-102-17-G-D", "Manufacturer": "Samtec",
                              "Datasheet": "https://suddendocs.samtec.com/catalog_english/tsw_th.pdf",
                              "Note": "Exact 2x2 ATX long-post header; mates Hub SSQ-102-03-G-D in the 18mm dead-bug stack. RSVD is intentionally NC."}},
            "C20": {"props": {
                "Datasheet": "https://product.samsungsem.com/mlcc/CL05B104KO5NNN.do",
                "Note": "TPS2121 U5 IN2 / U6 OUT local 100nF bypass on 5VSB_MUX."}},
            "C21": {"props": {
                "Datasheet": "https://product.samsungsem.com/mlcc/CL21A106KAYNNN.do",
                "Note": "TPS2121 U5 IN2 / U6 OUT local 10uF bulk on 5VSB_MUX."}},
        },
        # Repair an old annotation/net mismatch: C20/C21 were described as the
        # second U5 input bank but tied to raw +5VSB.  U5.IN2 is fed from U6.OUT
        # on 5VSB_MUX, so the bypass bank belongs on that inter-mux node.
        "net_overrides": {("C20", "1"): "5VSB_MUX", ("C21", "1"): "5VSB_MUX",
                          ("U5", "5"): "U5_OV1"},
        "synthetic_parts": {
            "U3": {"leaf": "03-regulator-mcu", "lib_id": "cec-vendor:TLV75533PDRVR",
                   "value": "TLV75533PDRVR",
                   "footprint": "cec-Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm",
                   "nets": {"1": "+3V3", "3": "GND", "4": "+5V_SYS",
                            "6": "+5V_SYS", "7": "GND"},
                   "props": {"Manufacturer": "Texas Instruments", "MPN": "TLV75533PDRVR",
                             "LCSC": "C2861750",
                             "Datasheet": "https://www.ti.com/lit/ds/symlink/tlv755p.pdf",
                             "Description": "500mA direct 3.3V LDO with exposed thermal pad"}},
            "R59": {"leaf": "02-power-usb", "lib_id": "cec-vendor:R_Small",
                    "value": "43.2kΩ", "footprint": "cec-Resistor_SMD:R_0402_1005Metric",
                    "nets": {"1": "+5V_MAIN", "2": "U5_OV1"},
                    "props": {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF4322TCE",
                              "LCSC": "C25894", "Datasheet": "https://www.lcsc.com/product-detail/C25894.html",
                              "Note": "U5 OV1 divider top."}},
            "R69": {"leaf": "02-power-usb", "lib_id": "cec-vendor:R_Small",
                    "value": "10kΩ", "footprint": "cec-Resistor_SMD:R_0402_1005Metric",
                    "nets": {"1": "U5_OV1", "2": "GND"},
                    "props": {"Manufacturer": "UNI-ROYAL", "MPN": "0402WGF1002TCE",
                              "LCSC": "C25744", "Datasheet": "https://www.lcsc.com/product-detail/C25744.html",
                              "Note": "U5 OV1 divider bottom."}},
            "C54": {"leaf": "02-power-usb", "lib_id": "cec-vendor:C_Small",
                    "value": "100nF", "footprint": "cec-Capacitor_SMD:C_0402_1005Metric",
                    "nets": {"1": "+5VSB", "2": "GND"},
                    "props": {"Datasheet": "https://product.samsungsem.com/mlcc/CL05B104KO5NNN.do",
                              "Manufacturer": "Samsung", "MPN": "CL05B104KO5NNNC",
                              "LCSC": "C1525", "Note": "TPS2121 U6 IN1 local 100nF bypass."}},
            "C55": {"leaf": "02-power-usb", "lib_id": "cec-vendor:C_Small",
                    "value": "10uF", "footprint": "cec-Capacitor_SMD:C_0805_2012Metric",
                    "nets": {"1": "+5VSB", "2": "GND"},
                    "props": {"Datasheet": "https://product.samsungsem.com/mlcc/CL21A106KAYNNN.do",
                              "Manufacturer": "Samsung", "MPN": "CL21A106KAYNNNE",
                              "LCSC": "C15850", "Note": "TPS2121 U6 IN1 local 10uF bulk."}},
        },
        "flags": {"01-atx-power-control": ["GND", "+5VSB", "+5V_MAIN"],
                  "02-power-usb": ["+5V_SYS", "5VSB_MUX", "VBUS"]},
        "leaves": [
            ("01-atx-power-control", "ATX INTERPOSER + CONTROL SIGNALS",
             "ATX connector, four shunts, output blade terminals, PS_ON#/PWR_OK conditioning and -12V scaling.",
             rows("J3 RS1 RS2 RS3 RS4", "TB1 TB2 TB3 TB4 TB5 TB6 TB7 TB8 TB9 TB10",
                  "J_SIG1 Q1 U4 U8 D3 D4 D5", "C22 C23 C64 R70 R71 R72 R73 R74 R75 R76")),
            ("02-power-usb", "5V SOURCE MUX + USB SERVICE INGRESS",
             "Cascaded TPS2121 source selection and protected USB-C service power/data ingress.",
             rows("U5 U6 J5 D7 D_USB1 F1 FB1", "C1 C4 C6 C9 C18 C19 C20 C21 C24 C25 C50 C51 C52 C53 C54 C55",
                  "R50 R51 R52 R53 R54 R55 R56 R57 R58 R59 R69 R8 R9")),
            ("03-regulator-mcu", "3V3 REGULATOR + MCU", "Thermal-pad TLV75533 rail, ESP32-C6 control and local boot/reset support.",
             rows("U3 U1", "C2 C3 C5 C7 C8 C10 C11 C12 C13 C14 R2 R10 R3 R4 SW1 SW2")),
            ("04-hub-can-stack", "HUB LINK + CAN + STACK",
             "Mezzanine stack interface, optional CAN common-mode choke position and 5V feed bridge.",
             rows("J2 J6C J6D J6P U2", "D1 FB2 FL1 R1 R7 R_BYP_H1 R_BYP_L1")),
            ("05-rail-sensing", "FOUR-RAIL PRECISION + FAST SENSING",
             "Four INA238 measurement channels plus INA181/TLV7011 transient channels and shared threshold conditioning.",
             rows("R60 C60 R61 C61", "U10 U612V1 U712V1 C15 C612V1 C712V1",
                  "U11 U65V1 U75V1 C16 C62 C65V1 C75V1", "U12 U63V31 U73V31 C17 C63 C63V31 C73V31",
                  "U13 U65VSB1 U75VSB1 C65VSB1 C75VSB1")),
        ],
    },
}


def _bare(name: str) -> str:
    name = name.replace("{slash}", "/")
    name = name[1:] if name.startswith("/") else name
    tail = name.rsplit("/", 1)[-1]
    # KiCad prefixes every sheet-local net during hierarchical export.  Feed
    # only the electrical label back into a regenerated leaf; retaining the
    # sheet path as part of the label causes a second regeneration to escape
    # the slash and nest the path again (SHEET{slash}NET).  Duplicate local
    # basenames remain fail-closed in extract(), so this cannot silently merge
    # two unrelated sheet-local nets.
    return tail


def _source_placements(path: str) -> dict[str, tuple[float, float, int]]:
    text = open(path, encoding="utf-8", errors="replace").read()
    work = L._strip_lib_symbols(text)
    return {ref: (x, y, rot) for _s, _e, (x, y), ref, rot, _lib, _mir in L._symbol_spans(work) if not ref.startswith("#")}


def _source_notes(path: str, placement: dict[str, tuple[float, float, int]], leaf_of: dict[str, str]):
    if not placement:
        return defaultdict(list)
    text = open(path, encoding="utf-8", errors="replace").read()
    notes = defaultdict(list)
    for el in L._extract_text_elements(text):
        if el["kind"] != "text":
            continue
        x, y = el["at"][:2]
        ref = min(placement, key=lambda r: (placement[r][0] - x) ** 2 + (placement[r][1] - y) ** 2)
        notes[leaf_of[ref]].append(el["text"])
    return notes


def _route_note(board: str, note: str, fallback: str) -> str:
    """Keep legacy engineering prose on the functional sheet it describes."""
    if board != "atx-24pin-rev3":
        return fallback
    routes = (
        (("ATX POWER", "OUTPUT FORM", "ATX CONTROL"), "01-atx-power-control"),
        (("5V / 5VSB", "FLASH / USB", "MARGIN RESERVOIRS"), "02-power-usb"),
        (("3V3 LDO", "MCU  ESP32"), "03-regulator-mcu"),
        (("HUB LINK", "CAN  TJA", "MEZZANINE", "STANDALONE-MODE"), "04-hub-can-stack"),
        (("RAIL SENSING", "TRANSIENT DETECTION"), "05-rail-sensing"),
    )
    for needles, lid in routes:
        if any(n in note for n in needles):
            return lid
    return fallback


def extract(path: str, leaf_of: dict[str, str], retired_refs=(), synthetic_refs=()):
    retired_refs = set(retired_refs)
    inv_all = G.inventory(path)
    inv = {r: d for r, d in inv_all.items() if r not in retired_refs}
    by_name = {}
    text = open(path, encoding="utf-8", errors="replace").read()
    hierarchical = bool(re.search(r'\(sheet\n', L._strip_lib_symbols(text)))
    if hierarchical:
        fd, net_path = tempfile.mkstemp(prefix="cec_beta_hier_", suffix=".net")
        os.close(fd); os.unlink(net_path)
        try:
            run = subprocess.run(
                ["kicad-cli", "sch", "export", "netlist", "-o", net_path, path],
                capture_output=True, text=True, timeout=120)
            if run.returncode:
                raise SystemExit("current hierarchy netlist export failed: " +
                                 (run.stderr or run.stdout)[-1000:])
            _values, nets = cec_spice_sanity.parse_netlist(net_path)
            for name, members in nets.items():
                if name.startswith("unconnected-"):
                    continue
                members = [(r, p) for r, p in members if r not in retired_refs]
                if not members:
                    continue
                bare = _bare(name)
                if bare in by_name and by_name[bare] != sorted(members):
                    combined = sorted(set(by_name[bare]) | set(members))
                    member_leaves = {leaf_of[ref] for ref, _pin in combined}
                    if len(member_leaves) != 1:
                        raise SystemExit(
                            f"duplicate local net name {bare!r} spans unrelated sheets")
                    # Recover a previously path-qualified local label that was
                    # emitted twice on the same leaf.  In KiCad both spellings
                    # denote the same intended leaf-local electrical net; the
                    # canonical regeneration emits one basename and therefore
                    # reconnects the members instead of compounding the path.
                    by_name[bare] = combined
                    continue
                by_name[bare] = sorted(members)
        finally:
            try:
                os.unlink(net_path)
            except OSError:
                pass
    else:
        for members, name in R.netlist_groups(path).items():
            if not name.startswith("unconnected-"):
                kept = [(r, p) for r, p in members if r not in retired_refs]
                if kept:
                    by_name[_bare(name)] = sorted(kept)
    synthetic_refs = set(synthetic_refs)
    missing = sorted(set(inv) - set(leaf_of))
    extra = sorted(set(leaf_of) - set(inv) - synthetic_refs)
    if missing or extra:
        raise SystemExit(f"partition mismatch: missing={missing}, extra={extra}")
    parts, fps, props = {}, {}, {}
    for ref, d in inv.items():
        lib, name = d["lib_id"].split(":", 1)
        parts[ref], fps[ref], props[ref] = (lib, name, d["value"]), d["footprint"], d["props"]
    spans = {name: {leaf_of[ref] for ref, _pin in members} for name, members in by_name.items()}
    return {"inventory": inv, "parts": parts, "footprints": fps, "props": props, "by_name": by_name, "spans": spans}


def _apply_net_overrides(extracted: dict, leaf_of: dict[str, str], overrides: dict):
    """Apply audited pin-level net repairs before composing and validating."""
    by_name = extracted["by_name"]
    for (ref, pin), new_net in overrides.items():
        member = (ref, str(pin))
        old = [name for name, members in by_name.items() if member in members]
        if len(old) != 1:
            raise SystemExit(f"net override {ref}.{pin}: expected one source net, found {old}")
        by_name[old[0]] = [node for node in by_name[old[0]] if node != member]
        if not by_name[old[0]]:
            del by_name[old[0]]
        by_name.setdefault(new_net, []).append(member)
        by_name[new_net] = sorted(set(by_name[new_net]))
    extracted["spans"] = {
        name: {leaf_of[ref] for ref, _pin in members}
        for name, members in by_name.items()
    }


def _inject_synthetic_parts(extracted: dict, specs: dict):
    """Add newly audited parts until they become self-hosting live source."""
    for ref, spec in specs.items():
        if ref in extracted["inventory"]:
            continue
        props = {"Value": spec["value"], "Footprint": spec["footprint"],
                 **spec.get("props", {})}
        extracted["inventory"][ref] = {
            "lib_id": spec["lib_id"], "sheet": spec["leaf"] + ".kicad_sch",
            "value": spec["value"], "footprint": spec["footprint"],
            "dnp": False, "in_bom": True, "on_board": True, "props": props,
        }
        lib, name = spec["lib_id"].split(":", 1)
        extracted["parts"][ref] = (lib, name, spec["value"])
        extracted["footprints"][ref] = spec["footprint"]
        extracted["props"][ref] = props
        for pin, net in spec.get("nets", {}).items():
            extracted["by_name"].setdefault(net, []).append((ref, str(pin)))
            extracted["by_name"][net] = sorted(set(extracted["by_name"][net]))


def _cap_bank(c: C.Compose, caps: list[str], power: str, x0: int, y0: int):
    caps = [r for r in caps if r in c.lf.parts]
    if len(caps) < 2:
        return set()
    for i, ref in enumerate(caps):
        c.place(ref, x0 + i * 8, y0, 0)
    tops, bots = [c.pin(r, "1") for r in caps], [c.pin(r, "2") for r in caps]
    top_y, bot_y = min(y for _x, y in tops) - 2, max(y for _x, y in bots) + 2
    for ref, (x, y) in zip(caps, tops):
        c.wire((x, y), (x, top_y)); c.use((ref, "1"))
    for ref, (x, y) in zip(caps, bots):
        c.wire((x, y), (x, bot_y)); c.use((ref, "2"))
    # Split the rails at each tap.  KiCad requires a real three-endpoint
    # junction at an interior capacitor drop; one unsplit long segment makes
    # the middle tap look connected but exports it as unconnected.
    for a, b in zip(sorted(x for x, _y in tops), sorted(x for x, _y in tops)[1:]):
        c.wire((a, top_y), (b, top_y))
    for a, b in zip(sorted(x for x, _y in bots), sorted(x for x, _y in bots)[1:]):
        c.wire((a, bot_y), (b, bot_y))
    c.stamp(power, min(x for x, _y in tops), top_y, 180)
    c.stamp("GND", min(x for x, _y in bots), bot_y, 0)
    c.caption(f"{power} LOCAL BYPASS / BULK BANK", x0, y0 - 8, 1.6)
    return set(caps)


def _compose_hub_holdup(c: C.Compose, lf: C.Leaf):
    """Dense, fully drawn active hold-up/regulator/detector islands.

    The DNP boost rung remains a clearly boxed option below the active path.
    This follows the reference schematic language: real local wires within a
    function and hierarchy labels only where signals actually leave the sheet.
    """
    # Active energy path: live +5VSB -> isolation -> reservoir -> fitted
    # RJ_HOLD -> buck -> +3V3.
    c.place_pin("D1", "2", 25, 70, rot=180)
    c.place_pin("C1", "1", 38, 70)
    c.place_pin("RJ_HOLD", "1", 50, 70, rot=90)
    c.place_pin("C2", "1", 65, 70)
    c.place_pin("U3", "4", 80, 70)
    c.place_pin("L1", "1", 100, 70, rot=90)
    c.place_pin("C3", "1", 115, 70)
    c.place_pin("R39", "1", 125, 70)
    c.place_pin("R40", "1", 125, 74)

    live, held = c.pin("D1", "2"), c.pin("D1", "1")
    c1_top, c1_gnd = c.pin("C1", "1"), c.pin("C1", "2")
    rj_hold_in, rj_hold_out = c.pin("RJ_HOLD", "1"), c.pin("RJ_HOLD", "2")
    c2_top, c2_gnd = c.pin("C2", "1"), c.pin("C2", "2")
    en, gnd, sw, vin, fb = (c.pin("U3", p) for p in ("1", "2", "3", "4", "5"))
    l_in, l_out = c.pin("L1", "1"), c.pin("L1", "2")
    c3_top, c3_gnd = c.pin("C3", "1"), c.pin("C3", "2")
    fb_top, fb_mid = c.pin("R39", "1"), c.pin("R39", "2")
    fb_bot_top, fb_gnd = c.pin("R40", "1"), c.pin("R40", "2")

    c.wire(held, c1_top, rj_hold_in)
    c.wire(rj_hold_out, c2_top, vin)
    c.wire(vin, (vin[0] - 4, vin[1]), (vin[0] - 4, en[1]), en)
    c.wire(sw, l_in)
    c.wire(l_out, c3_top, fb_top)
    c.wire(fb, (116, fb[1]), (116, fb_mid[1]), fb_mid, fb_bot_top)
    c.stamp("+5VSB", *live, 0)
    c.stamp("GND", *c1_gnd, 0); c.stamp("GND", *c2_gnd, 0)
    c.stamp("GND", *gnd, 0); c.stamp("GND", *c3_gnd, 0)
    c.stamp("GND", *fb_gnd, 0); c.stamp("+3V3", *l_out, 0)
    c.label("+5V_HOLD", *c1_top, 0)
    c.label("LOGIC_REG_IN", *c2_top, 0)
    c.label("BUCK_SW_3V3", 96, sw[1], 90)
    c.label("BUCK_FB_3V3", 116, fb_mid[1], 90)
    c.use(*[(r, p) for r, pins in {
        "D1": ("1", "2"), "C1": ("1", "2"), "RJ_HOLD": ("1", "2"),
        "C2": ("1", "2"), "U3": ("1", "2", "3", "4", "5"),
        "L1": ("1", "2"), "C3": ("1", "2"),
        "R39": ("1", "2"), "R40": ("1", "2"),
    }.items() for p in pins])
    c.region("ACTIVE HOLD-UP + 3V3 BUCK", 15, 48, 136, 91)

    # 5VSB loss detector. R12/R13/C12 sense the live rail upstream of D1;
    # U8 and its threshold/hysteresis divider remain powered from held +3V3.
    c.place_pin("R12", "2", 40, 129)
    c.place_pin("R13", "1", 40, 129)
    c.place_pin("C12", "1", 55, 129)
    c.place_pin("U8", "3", 75, 129)
    c.place_pin("C17", "1", 100, 125)
    c.place_pin("R28", "1", 82, 108, rot=90)
    c.place_pin("R26", "2", 112, 129)
    c.place_pin("R27", "1", 112, 129)

    r12_hi, sense = c.pin("R12", "1"), c.pin("R12", "2")
    r13_top, r13_gnd = c.pin("R13", "1"), c.pin("R13", "2")
    csense, csense_gnd = c.pin("C12", "1"), c.pin("C12", "2")
    fail, ugnd, u_sense, thresh, uvcc = (c.pin("U8", p) for p in ("1", "2", "3", "4", "5"))
    cvcc, cvcc_gnd = c.pin("C17", "1"), c.pin("C17", "2")
    hyst_out, hyst_thresh = c.pin("R28", "1"), c.pin("R28", "2")
    th_hi, th_node = c.pin("R26", "1"), c.pin("R26", "2")
    th_bot, th_gnd = c.pin("R27", "1"), c.pin("R27", "2")

    c.wire(sense, csense, u_sense)
    c.wire(fail, (78, fail[1]), (78, hyst_out[1]), hyst_out)
    c.wire(hyst_thresh, (96, hyst_thresh[1]), (96, thresh[1]), thresh, th_node)
    c.wire(uvcc, cvcc)
    c.stamp("+5VSB", *r12_hi, 0)
    c.stamp("GND", *r13_gnd, 0); c.stamp("GND", *csense_gnd, 0)
    c.stamp("GND", *ugnd, 0); c.stamp("GND", *cvcc_gnd, 0)
    c.stamp("+3V3", *uvcc, 0); c.stamp("+3V3", *th_hi, 0)
    c.stamp("GND", *th_gnd, 0)
    c.label("COMP_THRESH", 96, 118, 90)
    if "BLACKOUT_SENSE" in lf.hier_exports:
        c.wire(u_sense, (65, u_sense[1]), (65, 145), (25, 145))
        c.hier("BLACKOUT_SENSE", 25, 145, 180)
    if "PWR_FAIL_INT" in lf.hier_exports:
        c.wire(fail, (70, fail[1]), (70, 115), (25, 115))
        c.hier("PWR_FAIL_INT", 25, 115, 180)
    c.use(*[(r, p) for r, pins in {
        "R12": ("1", "2"), "R13": ("1", "2"), "C12": ("1", "2"),
        "U8": ("1", "2", "3", "4", "5"), "C17": ("1", "2"),
        "R28": ("1", "2"), "R26": ("1", "2"), "R27": ("1", "2"),
    }.items() for p in pins])
    c.region("LIVE 5VSB DROPOUT DETECTOR", 15, 92, 130, 153)

    c.note("The incomplete H2 boost/secondary-buck reservation is archived, not fitted on the live BETA.",
           150, 184, 1.05)


def _combine_gnd_array(c: C.Compose, ref: str, pins: list[str]):
    groups = defaultdict(list)
    for pin in pins:
        pt, vec = c.pin_out(ref, pin)
        groups[(int(round(vec[0])), int(round(vec[1])))].append((pin, pt))
    for (dx, dy), members in groups.items():
        if len(members) < 2:
            continue
        outs = []
        for pin, (x, y) in members:
            out = (x + dx * 3, y + dy * 3)
            c.wire((x, y), out); c.use((ref, pin)); outs.append(out)
        if dx:
            tx = min(x for x, _y in outs) if dx < 0 else max(x for x, _y in outs)
            for x, y in outs:
                if x != tx: c.wire((x, y), (tx, y))
            c.wire((tx, min(y for _x, y in outs)), (tx, max(y for _x, y in outs)))
            ey = max(y for _x, y in outs) + 3
            c.wire((tx, max(y for _x, y in outs)), (tx, ey)); c.stamp("GND", tx, ey, 0)
        else:
            ty = min(y for _x, y in outs) if dy < 0 else max(y for _x, y in outs)
            for x, y in outs:
                if y != ty: c.wire((x, y), (x, ty))
            c.wire((min(x for x, _y in outs), ty), (max(x for x, _y in outs), ty))
            ex = max(x for x, _y in outs) + 3
            c.wire((max(x for x, _y in outs), ty), (ex, ty)); c.stamp("GND", ex, ty, 0)


def _combine_repeated(c: C.Compose, net: str, conns: list[tuple[str, str]], side: str, lane: int, hierarchical: bool):
    pts = []
    for ref, pin in conns:
        if (ref, pin) in c.consumed:
            return False
        (x, y), (dx, dy) = c.pin_out(ref, pin)
        out = (x + int(round(dx)) * 3, y + int(round(dy)) * 3)
        c.wire((x, y), out); c.use((ref, pin)); pts.append(out)
    xs = [p[0] for p in pts]
    trunk_x = min(xs) - 8 - 4 * lane if side == "left" else max(xs) + 8 + 4 * lane
    for x, y in pts: c.wire((x, y), (trunk_x, y))
    c.wire((trunk_x, min(y for _x, y in pts)), (trunk_x, max(y for _x, y in pts)))
    anchor = (trunk_x, min(y for _x, y in pts))
    if hierarchical: c.hier(net, *anchor, 180 if side == "left" else 0)
    else: c.label(net, *anchor, 180 if side == "left" else 0)
    return True


def _patch_states(path: str, inv: dict):
    text = open(path, encoding="utf-8").read(); out, pos = [], 0
    for m in re.finditer(r'\t\(symbol\n', text):
        if m.start() < pos: continue
        blk = cec_sch.carve(text, m.start())
        rm = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', blk); ref = rm.group(1) if rm else None
        if ref in inv:
            d = inv[ref]
            new = re.sub(r'\(in_bom\s+(?:yes|no)\)', f'(in_bom {"yes" if d["in_bom"] else "no"})', blk, count=1)
            new = re.sub(r'\(on_board\s+(?:yes|no)\)', f'(on_board {"yes" if d["on_board"] else "no"})', new, count=1)
            new = re.sub(r'\(dnp\s+(?:yes|no)\)', f'(dnp {"yes" if d["dnp"] else "no"})', new, count=1)
            out.append(text[pos:m.start()]); out.append(new); pos = m.start() + len(blk)
    out.append(text[pos:]); open(path, "w", encoding="utf-8", newline="\n").write("".join(out))


def _dedupe_labels(path: str) -> int:
    """Drop only exact duplicate attached labels; keep the first."""
    text = open(path, encoding="utf-8").read(); seen, out, pos, count = set(), [], 0, 0
    hier = {(m.group(1), m.group(2), m.group(3)) for m in re.finditer(
        r'\(hierarchical_label "([^"]+)"[\s\S]*?\(at ([\d.\-]+) ([\d.\-]+) \d+\)', text)}
    for m in _LABEL_LINE_RE.finditer(text):
        key = (m.group(1), m.group(2), m.group(3))
        out.append(text[pos:m.start()])
        if key in seen or key in hier:
            count += 1; pos = m.end(); continue
        seen.add(key); out.append(m.group(0)); pos = m.end()
    out.append(text[pos:])
    if count: open(path, "w", encoding="utf-8", newline="\n").write("".join(out))
    return count


def _canonical_groups(path: str):
    return {frozenset(members): _bare(name) for members, name in R.netlist_groups(path).items() if not name.startswith("unconnected-")}


def _validate(expected: dict, root: str):
    inv_diff = G.check_inventory_equal(expected["inventory"], root)
    src = {frozenset(members): name for name, members in expected["by_name"].items()}
    dst = _canonical_groups(root)
    membership = sorted([sorted(x) for x in set(src) ^ set(dst)])
    def basename(name):
        return name.replace("{slash}", "/").rsplit("/", 1)[-1]
    renamed = sorted((src[k], dst[k]) for k in set(src) & set(dst)
                     if src[k] != dst[k] and basename(src[k]) != basename(dst[k])
                     and not (basename(src[k]).startswith("Net-") or
                              basename(dst[k]).startswith("Net-")))
    if inv_diff or membership or renamed:
        raise SystemExit("hierarchy validation failed:\n" + "\n".join(
            [*("inventory: " + x for x in inv_diff), *("membership: " + repr(x) for x in membership[:20]),
             *(f"renamed: {a!r} -> {b!r}" for a, b in renamed[:20])]))
    return len(src)


def build(board: str, source: str | None = None, out_dir: str | None = None):
    cfg = CONFIG[board]
    source = os.path.abspath(source or os.path.join(ROOT, cfg["live"]))
    if not os.path.isfile(source):
        raise SystemExit(f"authoritative live source not found: {source}; use --source explicitly for a migration")
    out_dir = os.path.abspath(out_dir or os.path.dirname(os.path.join(ROOT, cfg["live"])))
    os.makedirs(out_dir, exist_ok=True)

    leaf_of, leaf_meta = {}, {}
    for lid, title, desc, row_groups in cfg["leaves"]:
        leaf_meta[lid] = (title, desc, row_groups)
        for ref in sum(row_groups, []):
            if ref in leaf_of: raise SystemExit(f"duplicate partition ref {ref}")
            leaf_of[ref] = lid
    extracted = extract(source, leaf_of, cfg.get("retired_refs", ()),
                        cfg.get("synthetic_parts", ()))
    _inject_synthetic_parts(extracted, cfg.get("synthetic_parts", {}))
    _apply_net_overrides(extracted, leaf_of, cfg.get("net_overrides", {}))
    for ref, override in cfg.get("property_overrides", {}).items():
        if ref not in extracted["inventory"]:
            raise SystemExit(f"property override ref absent from source: {ref}")
        if override.get("footprint"):
            extracted["footprints"][ref] = override["footprint"]
            extracted["inventory"][ref]["footprint"] = override["footprint"]
            extracted["inventory"][ref]["props"]["Footprint"] = override["footprint"]
        if override.get("value"):
            value = override["value"]
            lib, name, _old = extracted["parts"][ref]
            extracted["parts"][ref] = (lib, name, value)
            extracted["inventory"][ref]["value"] = value
            extracted["inventory"][ref]["props"]["Value"] = value
            extracted["props"][ref]["Value"] = value
        extracted["props"][ref].update(override.get("props", {}))
        extracted["inventory"][ref]["props"].update(override.get("props", {}))
    source_place = {r: p for r, p in _source_placements(source).items()
                    if r in leaf_of}
    raw_notes = _source_notes(source, source_place, leaf_of)
    source_notes = defaultdict(list)
    for fallback, notes in raw_notes.items():
        for note in notes:
            source_notes[_route_note(board, note, fallback)].append(note)
    root_text = open(source, encoding="utf-8", errors="replace").read()
    root_uuid = re.search(r'\(uuid\s+"([0-9a-fA-F-]+)"\)', root_text).group(1)
    tm, rm = re.search(r'\(title\s+"([^"]*)"\)', root_text), re.search(r'\(rev\s+"([^"]*)"\)', root_text)
    title, rev = (tm.group(1) if tm else board), (rm.group(1) if rm else "DRAFT")
    pro = os.path.splitext(os.path.basename(cfg["live"]))[0]

    leaves, parent_specs = [], []
    all_lids = [x[0] for x in cfg["leaves"]]; x_rank = {lid: i for i, lid in enumerate(all_lids)}
    pair_sides = {}
    for net, ls in extracted["spans"].items():
        if net in POWER_NETS or net in GLOBAL_NETS or len(ls) != 2: continue
        a, b = sorted(ls, key=x_rank.get); pair_sides[net] = {a: "right", b: "left"}
    overwide = {n: sorted(ls) for n, ls in extracted["spans"].items()
                if n not in POWER_NETS and n not in GLOBAL_NETS and len(ls) > 2}
    if overwide: raise SystemExit(f"partition creates >2-leaf signals; repartition required: {overwide}")

    for li, (lid, leaf_title, desc, row_groups) in enumerate(cfg["leaves"]):
        lf = C.Leaf(lid, lid + ".kicad_sch", leaf_title, desc)
        refs = [r for r in extracted["parts"] if leaf_of[r] == lid]
        lf.parts = {r: extracted["parts"][r] for r in refs}; lf.footprints = {r: extracted["footprints"][r] for r in refs}
        lf.props = {r: extracted["props"][r] for r in refs}
        lf.powerflag_nets = list(cfg.get("flags", {}).get(lid, ()))
        for net, members in extracted["by_name"].items():
            here = [(r, p) for r, p in members if r in lf.parts]
            if here: lf.nets[net] = here
        export_nets = []
        for net, members in lf.nets.items():
            if (len(extracted["spans"].get(net, ())) > 1 and
                    net not in POWER_NETS and net not in GLOBAL_NETS and
                    not net.startswith("Net-")):
                export_nets.append(net); lf.hier_exports[net] = ("output", members[0])

        c = C.Compose(lf, LIBS); c.caption(leaf_title, 8, 2, 2.2); c.note(desc, 8, 6, 1.15)
        if lid == "01-power-input-selection":
            # Dense but repetitive source-selection rows. Ten compact
            # columns keep the whole function reviewable on A3 without
            # shrinking its 1.27 mm reference/value text to an A1 thumbnail.
            leaf_paper, ncols, x_pitch, y_pitch = "A3", 10, 29, 22
        elif lid == "06-status-leds":
            leaf_paper, ncols, x_pitch, y_pitch = "A3", 10, 20, 36
        elif len(refs) <= 10:
            leaf_paper, ncols, x_pitch, y_pitch = "A4", 4, 42, 32
        elif len(refs) <= 22:
            leaf_paper, ncols, x_pitch, y_pitch = "A3", 9, 30, 25
        else:
            leaf_paper, ncols, x_pitch, y_pitch = "A3", 10, 29, 22
        if lid.endswith("regulator-mcu"):
            y_pitch = max(y_pitch, 34)
            group_gap = 10
            y_cursor = 45
        else:
            group_gap = 6
            y_cursor = 30
        wide_label_leaves = {
            "01-power-input-selection", "02-holdup-3v3", "02-power-usb", "03-mcu-usb",
            "03-sensing", "05-rail-sensing", "01-atx-power-control",
        }
        group_points = []
        for group in row_groups:
            # Groups containing several ICs/connectors need enough horizontal
            # room for outward pin labels as well as the symbol bodies. Small
            # passive arrays retain the compact pitch and stay consolidated.
            large_symbols = sum(ref.startswith(("U", "J")) for ref in group)
            if lid == "01-power-input-selection":
                min_large_pitch = 52
            else:
                min_large_pitch = 46 if lid in wide_label_leaves else 38
            group_x_pitch = max(x_pitch, min_large_pitch) if large_symbols >= 2 else x_pitch
            points = []
            for gi, ref in enumerate(group):
                x = 18 + (gi % ncols) * group_x_pitch
                y = y_cursor + (gi // ncols) * y_pitch
                c.place(ref, x, y, source_place.get(ref, (0, 0, 0))[2])
                points.append((x, y))
            group_points.append(points)
            y_cursor += ((len(group) + ncols - 1) // ncols) * y_pitch + group_gap
        bank_y = y_cursor + 8

        if board == "hub-standard-rev2" and lid == "02-holdup-3v3":
            _compose_hub_holdup(c, lf)
            bank_y = 234
        else:
            group_titles = {
                "01-power-input-selection": ("SOURCE MUX DEVICES", "LOCAL RESERVOIRS + BYPASS", "CURRENT LIMIT + OVP SETPOINTS"),
                "03-mcu-usb": ("USB SERVICE + CONTROLLER", "LOCAL BYPASS + RESET / BOOT"),
                "04-can-module-ports": ("CAN + MODULE / STACK INTERFACES", "PROTECTION + FUSED FEEDS", "LOCAL FILTER / DETECT BIAS"),
                "05-kvm-aux-sensors": ("KVM + TEMPERATURE", "RAIL SENSE DIVIDERS"),
                "06-status-leds": ("LEVEL SHIFT + SIX-LED CHAIN",),
            }.get(lid, ())
            for gi, points in enumerate(group_points):
                if not points or gi >= len(group_titles):
                    continue
                xs, ys = zip(*points)
                # The USB-C symbol exposes top-edge pin names/numbers. Give
                # that first block a taller title gutter so the section name
                # remains visually separate at dashboard review scale.
                top_pad = 22 if lid == "03-mcu-usb" and gi == 0 else 14
                c.region(group_titles[gi], min(xs) - 10, min(ys) - top_pad,
                         max(xs) + 16, max(ys) + 14)

        if board == "atx-24pin-rev3" and lid == "02-power-usb":
            # U6_PR1 is on a left-facing TPS2121 pin. Its long name needs a
            # short attached stub plus the wider IC pitch: this keeps it clear
            # of both U6's visible pin number and U5_OV1. The label endpoint is
            # still wired; it is not a floating cosmetic move.
            c.stub_label("U6", "6", "U6_PR1", length=2)
        if board == "atx-24pin-rev3" and lid == "04-hub-can-stack":
            # FL1 carries a long, orderable DNP value. Keep its field on the
            # open left side so it remains attached to the part visually and
            # cannot run through the adjacent connector's vertical pin rail.
            c.text_side["FL1"] = "left"

        for power in ("+3V3", "+5VSB"):
            if board == "hub-standard-rev2" and lid == "02-holdup-3v3":
                continue
            caps = []
            for ref in refs:
                if not ref.startswith("C"): continue
                pin_net = {p: n for n, mm in lf.nets.items() for r, p in mm if r == ref}
                if pin_net.get("1") == power and pin_net.get("2") == "GND": caps.append(ref)
            if len(caps) >= 2: _cap_bank(c, caps, power, 18, bank_y); bank_y += 22

        if lid == "06-status-leds":
            # The DOUT->DIN chain is a real left-to-right wire sequence, not
            # a row of repeated anonymous labels.
            for net, members in lf.nets.items():
                if len(members) != 2 or not (net.startswith("Net-(DL") or net in
                                             {"LED_DATA_BUF", "LED_DATA_DIN"}):
                    continue
                (r1, p1), (r2, p2) = members
                a, b = c.pin(r1, p1), c.pin(r2, p2)
                if a[1] == b[1]:
                    joint = ((a[0] + b[0]) // 2, a[1])
                    c.wire(a, joint, b)
                else:
                    mid = (a[0] + b[0]) // 2
                    joint = (mid, (a[1] + b[1]) // 2)
                    c.wire(a, (mid, a[1]), joint, (mid, b[1]), b)
                if net in lf.hier_exports:
                    drop = 18 if net == "LED_DATA_BUF" else 28
                    tap = (joint[0], max(a[1], b[1]) + drop)
                    c.wire(joint, tap); c.hier(net, *tap, 0)
                c.use((r1, p1), (r2, p2))

        # Repeated supply bypass parts are physically and electrically
        # consolidated above.  Other signals keep short, wire-attached
        # labels at their pins; generic long trunks can create accidental
        # junctions when a dense connector fan-out crosses another lane.
        # Board-specific drawn buses may be added only with rendered and
        # netlist-identity evidence.
        combined = set()
        for net in export_nets:
            if net in combined: continue
            # The generic builder puts the hierarchy label on a real pin
            # stub at this anchor.  Do not force a long edge-column route for
            # one/two-pin nets: compact direct labels are clearer and avoid
            # crossing unrelated symbols.  Repeated nets above still get a
            # single explicit external trunk.
            pass

        # Preserve the archived engineering notes, but balance them into two
        # explicit columns instead of a single tall tail. This keeps notes
        # close to their function and makes their 1 mm text readable at the
        # standard 2048 px review width.
        note_y = bank_y + 6
        wrapped_notes = [textwrap.wrap(note, 54, replace_whitespace=False)
                         for note in source_notes.get(lid, [])]
        note_columns = [[], []]
        note_lines = [0, 0]
        for wrapped in wrapped_notes:
            col = 0 if note_lines[0] <= note_lines[1] else 1
            note_columns[col].append(wrapped)
            note_lines[col] += len(wrapped) + 1
        for col, blocks in enumerate(note_columns):
            column_y = note_y
            for wrapped in blocks:
                c.note("\n".join(wrapped), 8 + col * 145, column_y, 1.0)
                column_y += max(7, 2 + 2 * len(wrapped))
        c.done()

        x0, x1, y0, y1 = C.leaf_content_bbox(
            lf.parts, lf.placement, LIBS, lf.layout, lf.powerflag_nets)
        content_w, content_h = x1 - x0, y1 - y0
        for candidate in ("A4", "A3"):
            paper_w, paper_h = C.PAPER[candidate]
            if content_w <= paper_w - 30 and content_h <= paper_h - 30:
                leaf_paper = candidate
                break
        else:
            raise SystemExit(
                f"{board}/{lid}: composed content {content_w:.1f} x {content_h:.1f} mm "
                "does not fit a readable A3 leaf; split or recompose the function")

        leaf_sym = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cec:{board}:{lid}:sheet")); leaf_own = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cec:{board}:{lid}:file"))
        out = os.path.join(out_dir, lf.filename)
        stats = C.build_leaf(lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None, LIBS, pro, path_prefix=f"{root_uuid}/{leaf_sym}",
            sheet_instances_path=leaf_sym, own_uuid=leaf_own, page=str(li + 2), out_path=out, paper=leaf_paper,
            title=f"{title}: {leaf_title}",
            comment1=textwrap.shorten(desc, width=64, placeholder="..."),
            pwr_base=100 * (li + 1), layout=lf.layout,
            global_nets=GLOBAL_NETS & set(lf.nets), rev=rev)
        _patch_states(out, extracted["inventory"]); deduped = _dedupe_labels(out)
        # Collapse the ESP32 exposed-ground flag ladder with the proven
        # guarded mutator.  It only acts when every flag is an isolated stub,
        # refuses a blocked wire corridor, and the final hierarchy-equivalence
        # gate below still independently proves net membership.
        ladder = G.bus_power_ladder(out, "U1", "GND")
        flipped = L.flip_label_collisions(out)
        moved, left = L.nudge_texts(out)
        print(f"{lf.filename}: parts={len(refs)} paper={leaf_paper} wires={stats.get('wires')} "
              f"deduped={deduped} bused={ladder.get('flags_removed', 0)} "
              f"flipped={flipped} nudged={moved} overlaps={left}")
        leaves.append((lf, leaf_sym))

    for li, (lf, leaf_sym) in enumerate(leaves):
        pins = [(net, "output", pair_sides.get(net, {}).get(lf.id) or ("left" if li == 0 else "right")) for net in lf.hier_exports]
        counts = {s: sum(1 for _n, _shape, side in pins if side == s) for s in ("left", "right")}
        h_u = max(28, 10 + max(counts.values(), default=0) * 4)
        parent_specs.append({"id": lf.id, "sym_uuid": leaf_sym, "filename": lf.filename, "sheetname": lf.sheetname,
            "page": str(li + 2), "x": (10 + (li % 3) * 120) * cec_sch.GRID,
            "y": (15 + (li // 3) * 145) * cec_sch.GRID,
            "w": 70 * cec_sch.GRID, "h": h_u * cec_sch.GRID, "pins": pins})

    root_out = os.path.join(out_dir, os.path.basename(cfg["live"]))
    C.build_thin_parent(parent_specs, set(), pro, root_uuid, None, root_uuid, out_path=root_out, title=title,
        paper="A2", libs=LIBS, pwr_base=900, lane_labels=True, pair_labels=True, rev=rev, title_comments=(
            "Authoritative BETA hierarchy; functional leaves only; no legacy project discovery.",
            "Repeated nets use shared trunks; power bypass arrays use real rails; hierarchy labels are wire-attached.",
            "Recomposed from the live current hierarchy and gated by inventory/net/ERC equivalence.",))
    net_count = _validate(extracted, root_out)
    print(f"{os.path.basename(root_out)}: hierarchy valid, {len(extracted['inventory'])} parts, {net_count} connected nets")
    return root_out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument("boards", nargs="+", choices=sorted(CONFIG))
    ap.add_argument("--source"); ap.add_argument("--out-dir"); args = ap.parse_args(argv)
    if (args.source or args.out_dir) and len(args.boards) != 1: ap.error("--source/--out-dir require exactly one board")
    for board in args.boards: build(board, args.source, args.out_dir)
    return 0


if __name__ == "__main__": raise SystemExit(main())
