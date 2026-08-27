#!/usr/bin/env python3
"""Apply the protected USB service-power ingress to manifest-current EPS Rev3.

This is deliberately separate from the historical ``splice_usb_ingress_eps``
helper: that older one targets ``beta/eps-8pin`` and must never be used as an
authority for the only current EPS product.  The topology applied here is:

    RJ45 5V -> TPS2121 IN1
    USB VBUS -> 750 mA / 16 V PTC -> TPS2121 IN2
    TPS2121 OUT -> +5VSB

The mux has exact local input capacitors, soft-start/current-limit straps and a
43.2 k / 10 k OV1 divider.  All edits are fail-closed and idempotence-guarded.
"""
from __future__ import annotations

import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cec_beta_manifest  # noqa: E402
import cec_sch  # noqa: E402
import cec_sch_layout  # noqa: E402
import splice_usb_ingress_common as sc  # noqa: E402


BOARD = "eps-8pin-rev3"
ENTRY = cec_beta_manifest.BY_BOARD[BOARD]
ROOT_DIR = os.path.abspath(os.path.join(HERE, "..", "beta", ENTRY["directory"]))
USB_SCH = os.path.join(ROOT_DIR, "05-usb-service.kicad_sch")
HUB_SCH = os.path.join(ROOT_DIR, "01-hub-can.kicad_sch")
DONOR = os.path.join(HERE, "..", "beta", "pcie-8pin-3port", "07-usb-flash.kicad_sch")

PROJECT = "eps-8pin-rev3"
ROOT_UUID = "ef7f6c4c-2dd9-4559-b472-96b33604786a"
USB_SHEET_UUID = "a18073cb-af35-5864-98f8-48efb88e5d99"
HUB_SHEET_UUID = "ef5c2d96-f002-5929-9940-f7976e9dfcc0"
USB_PATH = f"{ROOT_UUID}/{USB_SHEET_UUID}"
HUB_PATH = f"{ROOT_UUID}/{HUB_SHEET_UUID}"

VCC_RJ45 = "VCC_RJ45"
VBUS_FUSED = "VBUS_FUSED"

FP_R0402 = "cec-Resistor_SMD:R_0402_1005Metric"
FP_C0402 = "cec-Capacitor_SMD:C_0402_1005Metric"
FP_C0603 = "cec-Capacitor_SMD:C_0603_1608Metric"
FP_C0805 = "cec-Capacitor_SMD:C_0805_2012Metric"

BOM = {
    "D3": dict(
        Manufacturer="UMW", MPN="USBLC6-2SC6", LCSC="C2687116",
        Datasheet="https://datasheet.lcsc.com/lcsc/2206231215_UMW-Youtai-Semiconductor-Co---Ltd--USBLC6-2SC6_C2687116.pdf",
        Note="Low-capacitance USB D+/D- ESD array with VBUS reference."),
    "U4": dict(
        Manufacturer="Texas Instruments", MPN="TPS2121RUXR", LCSC="C485916",
        Datasheet="https://www.ti.com/lit/ds/symlink/tps2121.pdf",
        Note="Protected USB/RJ45 service-power mux; OUT is the board +5VSB rail."),
    "F1": dict(
        Manufacturer="Littelfuse", MPN="1206L075/16WR", LCSC="C371166",
        Datasheet="https://www.lcsc.com/datasheet/C371166.pdf",
        Note="750mA hold, 1.5A trip, 16V resettable PTC on USB VBUS ingress."),
    "R14": dict(
        Manufacturer="UNI-ROYAL", MPN="0402WGF1003TCE", LCSC="C25741",
        Datasheet="https://www.lcsc.com/product-detail/C25741.html",
        Note="U4 ILIM = 100k, approximately 1.24A typical."),
    "R15": dict(
        Manufacturer="UNI-ROYAL", MPN="0402WGF4322TCE", LCSC="C25894",
        Datasheet="https://www.lcsc.com/product-detail/C25894.html",
        Note="U4 OV1 top; 43.2k/10k gives 5.639V nominal and 5.287..5.948V at specified extremes."),
    "R16": dict(
        Manufacturer="UNI-ROYAL", MPN="0402WGF1002TCE", LCSC="C25744",
        Datasheet="https://www.lcsc.com/product-detail/C25744.html",
        Note="U4 OV1 divider bottom."),
    "R17": dict(
        Manufacturer="UNI-ROYAL", MPN="0402WGF1003TCE", LCSC="C25741",
        Datasheet="https://www.lcsc.com/product-detail/C25741.html",
        Note="U4 PR1 divider top."),
    "R18": dict(
        Manufacturer="UNI-ROYAL", MPN="0402WGF3302TCE", LCSC="C25779",
        Datasheet="https://www.lcsc.com/product-detail/C25779.html",
        Note="U4 PR1 divider bottom; approximately 4.27V validity threshold."),
    "C42": dict(
        Manufacturer="Samsung", MPN="CL10A225KO8NNNC", LCSC="C23630",
        Datasheet="https://product.samsungsem.com/mlcc/CL10A225KO8NNN.do",
        Note="U4 soft-start capacitor."),
    "C43": dict(
        Manufacturer="Samsung", MPN="CL05B104KO5NNNC", LCSC="C1525",
        Datasheet="https://product.samsungsem.com/mlcc/CL05B104KO5NNN.do",
        Note="U4 IN2 local high-frequency bypass; place at IN2 and GND."),
    "C44": dict(
        Manufacturer="Samsung", MPN="CL21A106KAYNNNE", LCSC="C15850",
        Datasheet="https://product.samsungsem.com/mlcc/CL21A106KAYNNN.do",
        Note="U4 IN2 local bulk bypass; place at IN2 and GND."),
    "C45": dict(
        Manufacturer="Samsung", MPN="CL21A106KAYNNNE", LCSC="C15850",
        Datasheet="https://product.samsungsem.com/mlcc/CL21A106KAYNNN.do",
        Note="U4 IN1 local bypass; place at IN1 and GND."),
}


def _append_before_trailer(text: str, blobs) -> str:
    content = "\n".join(blobs) + "\n"
    if "\t(sheet_instances" in text:
        at = text.rindex("\t(sheet_instances")
    else:
        start = text.index("(kicad_sch")
        whole = cec_sch.carve(text, start)
        at = start + len(whole) - 1
    return text[:at] + content + text[at:]


def main() -> int:
    expected_root = os.path.abspath(os.path.join(HERE, "..", "beta", "eps-8pin-rev3"))
    if ROOT_DIR != expected_root or "old-revisions" in ROOT_DIR.lower():
        raise SystemExit(f"REFUSE: EPS ingress target is not manifest-current Rev3: {ROOT_DIR}")

    usb = open(USB_SCH, encoding="utf-8").read()
    if '(property "Reference" "U4"' in usb:
        raise SystemExit("REFUSE: U4 already exists in current EPS Rev3 USB sheet")

    usb, _ = sc.ensure_lib_symbol(usb, "cec-vendor:TPS2121RUXR", DONOR)
    usb, _ = sc.ensure_lib_symbol(usb, "cec-vendor:USBLC6-2SC6", DONOR)
    usb, _ = sc.ensure_lib_symbol(usb, "cec-power:PWR_FLAG", DONOR)
    r_pins = sc.get_pin_table(usb, "cec-vendor:R_Small")
    c_pins = sc.get_pin_table(usb, "cec-vendor:C_Small")
    mux_pins = sc.get_pin_table(usb, "cec-vendor:TPS2121RUXR")
    esd_pins = sc.get_pin_table(usb, "cec-vendor:USBLC6-2SC6")
    flag_pins = sc.get_pin_table(usb, "cec-power:PWR_FLAG")
    diode_pins = sc.get_pin_table(usb, "cec-vendor:D_Schottky")

    # Retire the direct VBUS -> +5VSB Schottky path and both of its stubs.
    usb, _kind, info = sc.remove_pin_stub(
        usb, diode_pins, "D2", "1", 127.0, 93.98)
    if not (_kind == "power" and info[1] == "+5VSB"):
        raise SystemExit(f"REFUSE: D2 pin 1 was not the expected +5VSB leg: {_kind} {info}")
    usb, _kind, info = sc.remove_pin_stub(
        usb, diode_pins, "D2", "2", 127.0, 93.98)
    if not (_kind == "label" and info == "VBUS"):
        raise SystemExit(f"REFUSE: D2 pin 2 was not the expected VBUS leg: {_kind} {info}")
    usb, d2 = sc.remove_symbol(usb, "D2")
    if 'Value" "SS34"' not in d2:
        raise SystemExit("REFUSE: D2 was not the expected SS34 legacy ORing diode")

    blobs = []
    # Fuse and mux are grouped as one readable service-power block.
    fx, fy = sc.gsnap(250.0), sc.gsnap(35.0)
    blobs.append(cec_sch.emit_symbol(
        "F1", "cec-vendor", "R_Small", "750mA/16V PTC", fx, fy,
        sorted(r_pins), PROJECT, USB_PATH,
        fp="cec-Resistor_SMD:R_1206_3216Metric", props=BOM["F1"]))
    blobs.append(sc.wire_and_label(r_pins, "F1", "1", fx, fy, "VBUS"))
    blobs.append(sc.wire_and_label(r_pins, "F1", "2", fx, fy, VBUS_FUSED))

    dx, dy = sc.gsnap(190.0), sc.gsnap(135.0)
    blobs.append(cec_sch.emit_symbol(
        "D3", "cec-vendor", "USBLC6-2SC6", "USBLC6-2SC6", dx, dy,
        sorted(esd_pins), PROJECT, USB_PATH,
        fp="cec-Package_TO_SOT_SMD:SOT-23-6", props=BOM["D3"]))
    for pin in ("1", "6"):
        blobs.append(sc.wire_and_label(esd_pins, "D3", pin, dx, dy, "USB_D_P"))
    for pin in ("3", "4"):
        blobs.append(sc.wire_and_label(esd_pins, "D3", pin, dx, dy, "USB_D_N"))
    blobs.append(sc.wire_and_label(esd_pins, "D3", "5", dx, dy, "VBUS"))
    blobs.append(sc.wire_and_power(
        esd_pins, "D3", "2", dx, dy, "GND", PROJECT, USB_PATH, "#PWR540"))

    ux, uy = sc.gsnap(275.0), sc.gsnap(70.0)
    blobs.append(cec_sch.emit_symbol(
        "U4", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR", ux, uy,
        sorted(mux_pins), PROJECT, USB_PATH,
        fp="cec-Package_DFN_QFN:RUX0012A", props=BOM["U4"]))
    for pin, ref in (("1", "#PWR541"), ("8", "#PWR542")):
        blobs.append(sc.wire_and_power(
            mux_pins, "U4", pin, ux, uy, "+5VSB", PROJECT, USB_PATH, ref))
    blobs.append(sc.wire_and_label(mux_pins, "U4", "2", ux, uy, VBUS_FUSED))
    for pin, ref in (("3", "#PWR543"), ("4", "#PWR544"), ("12", "#PWR545")):
        blobs.append(sc.wire_and_power(
            mux_pins, "U4", pin, ux, uy, "GND", PROJECT, USB_PATH, ref))
    blobs.append(sc.noconnect_pin(mux_pins, "U4", "9", ux, uy))
    blobs.append(sc.wire_and_label(mux_pins, "U4", "5", ux, uy, "U4_OV1"))
    blobs.append(sc.wire_and_label(mux_pins, "U4", "6", ux, uy, "U4_PR1"))
    blobs.append(sc.wire_and_global_label(mux_pins, "U4", "7", ux, uy, VCC_RJ45))
    blobs.append(sc.wire_and_label(mux_pins, "U4", "10", ux, uy, "U4_ILIM"))
    blobs.append(sc.wire_and_label(mux_pins, "U4", "11", ux, uy, "U4_SS"))

    # Control passives, arranged top-to-bottom by mux pin function.
    rx = sc.gsnap(315.0)
    for ref, value, y, high, low in (
            ("R14", "100kOhm", 45.0, "U4_ILIM", "GND"),
            ("R15", "43.2kOhm", 65.0, VCC_RJ45, "U4_OV1"),
            ("R16", "10kOhm", 80.0, "U4_OV1", "GND"),
            ("R17", "100kOhm", 100.0, VCC_RJ45, "U4_PR1"),
            ("R18", "33kOhm", 115.0, "U4_PR1", "GND")):
        y = sc.gsnap(y)
        blobs.append(cec_sch.emit_symbol(
            ref, "cec-vendor", "R_Small", value, rx, y, sorted(r_pins),
            PROJECT, USB_PATH, fp=FP_R0402, props=BOM[ref]))
        if high == VCC_RJ45:
            blobs.append(sc.wire_and_global_label(r_pins, ref, "1", rx, y, high))
        else:
            blobs.append(sc.wire_and_label(r_pins, ref, "1", rx, y, high))
        if low == "GND":
            blobs.append(sc.wire_and_power(
                r_pins, ref, "2", rx, y, "GND", PROJECT, USB_PATH,
                f"#PWR54{6 + int(ref[1:])}"))
        else:
            blobs.append(sc.wire_and_label(r_pins, ref, "2", rx, y, low))

    for ref, value, fp, x, y, rail, pwr in (
            ("C42", "2.2uF", FP_C0603, 245.0, 65.0, "U4_SS", "#PWR560"),
            ("C43", "100nF", FP_C0402, 245.0, 90.0, VBUS_FUSED, "#PWR561"),
            ("C44", "10uF", FP_C0805, 245.0, 105.0, VBUS_FUSED, "#PWR562"),
            ("C45", "10uF", FP_C0805, 225.0, 105.0, VCC_RJ45, "#PWR563")):
        x, y = sc.gsnap(x), sc.gsnap(y)
        blobs.append(cec_sch.emit_symbol(
            ref, "cec-vendor", "C_Small", value, x, y, sorted(c_pins),
            PROJECT, USB_PATH, fp=fp, props=BOM[ref]))
        if rail == VCC_RJ45:
            blobs.append(sc.wire_and_global_label(c_pins, ref, "1", x, y, rail))
        else:
            blobs.append(sc.wire_and_label(c_pins, ref, "1", x, y, rail))
        blobs.append(sc.wire_and_power(
            c_pins, ref, "2", x, y, "GND", PROJECT, USB_PATH, pwr))

    for ref, x, net, global_net in (
            ("#FLG551", 250.0, VBUS_FUSED, False),
            ("#FLG552", 275.0, VCC_RJ45, True)):
        x, y = sc.gsnap(x), sc.gsnap(130.0)
        blobs.append(cec_sch.emit_symbol(
            ref, "cec-power", "PWR_FLAG", "PWR_FLAG", x, y,
            sorted(flag_pins), PROJECT, USB_PATH, fp=""))
        if global_net:
            blobs.append(sc.wire_and_global_label(flag_pins, ref, "1", x, y, net))
        else:
            blobs.append(sc.wire_and_label(flag_pins, ref, "1", x, y, net))

    open(USB_SCH, "w", encoding="utf-8").write(_append_before_trailer(usb, blobs))

    # Isolate the RJ45 source from +5VSB: it now feeds U4.IN1 via a project-wide
    # named rail, while U4.OUT alone owns +5VSB.
    hub = open(HUB_SCH, encoding="utf-8").read()
    j_pins = sc.get_pin_table(hub, "cec:CEC_RJ45_8P8C_FTP")
    hub, kind, info = sc.remove_pin_stub(
        hub, j_pins, "J1", "1", 74.93, 90.17)
    if not (kind == "power" and info[1] == "+5VSB"):
        raise SystemExit(f"REFUSE: J1.1 was not the expected direct +5VSB source: {kind} {info}")
    hub_blob = [sc.wire_and_global_label(
        j_pins, "J1", "1", 74.93, 90.17, VCC_RJ45)]
    open(HUB_SCH, "w", encoding="utf-8").write(
        _append_before_trailer(hub, hub_blob))

    # Generated electrical topology is not complete until it also passes the
    # repository-wide readability gate.  Keep this in the source splice so a
    # later clean regeneration cannot restore overlapping fields.
    cec_sch_layout.nudge_texts(USB_SCH, USB_SCH)
    overlaps = cec_sch_layout.detect_overlaps(USB_SCH)
    if overlaps:
        first = overlaps[0]
        raise SystemExit(
            "REFUSE: generated EPS USB ingress is not review-readable: "
            f"{first[0]['label']} overlaps {first[1]['label']}")

    print("current EPS Rev3 protected USB ingress applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
