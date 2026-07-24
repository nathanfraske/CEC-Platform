#!/usr/bin/env python3
# One-shot splice: PCIe 8-pin 2-port USB-ingress TPS2121 mux (spec v1.6.0 Sec
# 6.14; owner rulings 2026-07-24; docs/usb-ingress-bom-delta-2026-07-24.md Sec
# 3.2 -- "Identical to the EPS delta").
#
# Same shape as scripts/splice_usb_ingress_eps.py (see its header for the full
# rationale) with THREE real per-board differences, verified against the live
# file before writing this (not assumed from EPS's structure):
#   - the raw connector-side VBUS net is named "VBUS_J5" here (not
#     "VBUS_RAW"), and FB1's OWN pin-1 stub on this board rides a
#     (hierarchical_label ...) -- a real sheet-pin lane up to the root sheet
#     (root carries a matching "VBUS_J5" output pin on the 07-usb-flash
#     sheet-symbol + its own same-named label) -- NOT a plain (label ...) like
#     EPS. F1's upstream pin therefore also emits a hierarchical_label of the
#     same name (matching this board's own house style for that net) rather
#     than a plain label; either tag joins the same net by name on THIS sheet
#     (the hierarchical half only matters for reaching beyond it, which stays
#     intact since J5's own pins are untouched).
#   - D3 (USBLC6-2SC6) and D4 (PESD5V0S1BA) sit DOWNSTREAM of FB1 here (on the
#     "VBUS" node, both boards' clamp placement is a real per-board layout
#     choice, not a mistake) rather than upstream at the raw connector node
#     like EPS's D3 -- irrelevant to this splice (F1 still inserts between the
#     raw node and FB1 either way; the clamps are untouched).
#   - the RJ-45-side pre-bead net is "VCC_J1" (not "VCC_RJ45_RAW"); FB2's own
#     post-bead stub is a plain (symbol (lib_id "cec-power:+5VSB")) power tie,
#     same mechanism as EPS.
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch  # noqa: E402
import splice_usb_ingress_common as sc  # noqa: E402

ROOT_DIR = os.path.join(HERE, "..", "beta", "pcie-8pin-2port")
USB_SCH = os.path.join(ROOT_DIR, "07-usb-flash.kicad_sch")
HUBLINK_SCH = os.path.join(ROOT_DIR, "01-hub-link.kicad_sch")
DONOR = os.path.join(HERE, "..", "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")

PROJECT = "pcie8pin-2port-module"
ROOT_UUID = "a0c79a2e-4073-4d8d-b0bf-2c2ed1691f64"
USB_SHEET_UUID = "8adba108-789d-4153-ad59-e74c8138b4d8"
HUBLINK_SHEET_UUID = "67f50ca3-8cb0-4aa6-9a3f-011faa4ff8d7"
USB_PATH = f"{ROOT_UUID}/{USB_SHEET_UUID}"
HUBLINK_PATH = f"{ROOT_UUID}/{HUBLINK_SHEET_UUID}"

GLOBAL_VCC_RJ45 = "VCC_RJ45"  # new cross-sheet net name (matches the EPS delta's choice)

BOM = {
    "U4": dict(Manufacturer="Texas Instruments", MPN="TPS2121RUXR", LCSC="C485916"),
    "F1": dict(Manufacturer="Littelfuse", MPN="1206L075/16WR", LCSC="C371166",
               Note="750mA hold/1.5A trip/16V resettable PTC polyfuse, VBUS ingress "
                    "defense layer 2 (spec v1.6.0 Sec 6.14)."),
    "R14": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1003TCE", LCSC="C25741",
                Note="U4 ILIM strap -> ~1.24A typical (I_LIM=65.2/R_kOhm^0.861)."),
    "R15": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF4702TCE", LCSC="C25792",
                Note="U4 OV1 divider top (IN1 side)."),
    "R16": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1002TCE", LCSC="C25744",
                Note="U4 OV1 divider bottom (GND side) -> ~6.04V typical cutoff."),
    "R17": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1003TCE", LCSC="C25741",
                Note="U4 PR1 divider top (IN1 side)."),
    "R18": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF3302TCE", LCSC="C25779",
                Note="U4 PR1 divider bottom (GND side) -> ~4.27V typical validity floor."),
    "C42": dict(Manufacturer="Samsung", MPN="CL10A225KO8NNNC", LCSC="C23630",
                Note="U4 soft-start cap (~10ms output ramp, hub-proven value)."),
    "C43": dict(Manufacturer="Samsung", MPN="CL05B104KO5NNNC", LCSC="C1525",
                Note="U4 IN2 (VBUS) bypass."),
    "C44": dict(Manufacturer="Samsung", MPN="CL21A106KAYNNNE", LCSC="C15850",
                Note="U4 IN2 (VBUS) bulk (additional to the existing C9 on the same node)."),
}

FP_R0402 = "cec-Resistor_SMD:R_0402_1005Metric"
FP_C0402 = "cec-Capacitor_SMD:C_0402_1005Metric"
FP_C0603 = "cec-Capacitor_SMD:C_0603_1608Metric"
FP_C0805 = "cec-Capacitor_SMD:C_0805_2012Metric"

if __name__ == "__main__":
    txt = open(USB_SCH).read()
    if '(property "Reference" "U4"' in txt:
        raise SystemExit("REFUSE: U4 already present in 07-usb-flash.kicad_sch -- splice already applied?")

    txt, added = sc.ensure_lib_symbol(txt, "cec-vendor:TPS2121RUXR", DONOR)
    print("TPS2121RUXR lib_symbol imported:", added)
    txt, added2 = sc.ensure_lib_symbol(txt, "cec-power:PWR_FLAG", HUBLINK_SCH)
    print("PWR_FLAG lib_symbol imported:", added2)

    r_pins = sc.get_pin_table(txt, "cec-vendor:R_Small")
    c_pins = sc.get_pin_table(txt, "cec-vendor:C_Small")
    mux_pins = sc.get_pin_table(txt, "cec-vendor:TPS2121RUXR")
    flag_pins = sc.get_pin_table(txt, "cec-power:PWR_FLAG")

    # ---------- 1. delete D2 (the retired ORing diode) entirely ----------
    txt, d2_blk = sc.remove_symbol(txt, "D2")
    assert 'Value" "SS34"' in d2_blk
    txt = sc.remove_wire_between(txt, 201.93, 63.5, 198.12, 63.5)
    txt, kind1, info1 = sc.remove_terminal_at(txt, 198.12, 63.5)
    assert kind1 == "power" and info1[1] == "+5VSB", info1
    txt = sc.remove_wire_between(txt, 209.55, 63.5, 213.36, 63.5)
    txt, kind2, info2 = sc.remove_terminal_at(txt, 213.36, 63.5)
    assert kind2 == "label" and info2 == "VBUS", info2
    print("D2 removed; stub terminals:", info1, info2)

    # ---------- 2. insert F1 ahead of FB1 (VBUS_J5 -> F1 -> VBUS_F -> FB1) ----------
    # FB1's own pin-1 stub carries a (hierarchical_label "VBUS_J5" ...) -- a
    # real sheet-pin lane (the root carries a matching "VBUS_J5" output pin +
    # its own same-named label). Renaming that label in place while KEEPING
    # the hierarchical_label tag would orphan it: KiCad flags "hier_label_
    # mismatch, no matching sheet pin" for whatever NEW name it carries, since
    # only "VBUS_J5" has a declared parent-side pin -- confirmed by a first
    # attempt that did exactly that and drew a fresh ERROR. "VBUS_F" is a
    # purely internal new node (nothing outside this sheet needs it), so the
    # fix is to remove the hierarchical_label outright and replace it with a
    # plain same-sheet label instead, matching the EPS delta's own approach.
    txt, kind, old_name = sc.remove_terminal_at(txt, 198.12, 95.25)
    assert kind == "hierarchical_label" and old_name == "VBUS_J5", (kind, old_name)
    F1_X, F1_Y = sc.gsnap(250.0), sc.gsnap(30.0)
    blob = [
        cec_sch.emit_label("VBUS_F", 198.12, 95.25, 180),
        cec_sch.emit_symbol("F1", "cec-vendor", "R_Small", "750mA/16V PTC", F1_X, F1_Y,
                             sorted(r_pins.keys()), PROJECT, USB_PATH,
                             fp="cec-Resistor_SMD:R_1206_3216Metric", props=BOM["F1"]),
        sc.wire_and_hier_label(r_pins, "F1", "1", F1_X, F1_Y, "VBUS_J5"),
        sc.wire_and_label(r_pins, "F1", "2", F1_X, F1_Y, "VBUS_F"),
    ]

    # ---------- 3. place U4 + straps ----------
    UX, UY = sc.gsnap(270.0), sc.gsnap(60.0)
    blob.append(cec_sch.emit_symbol("U4", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR",
                                     UX, UY, sorted(mux_pins.keys()), PROJECT, USB_PATH,
                                     fp="cec-Package_DFN_QFN:RUX0012A", props=BOM["U4"]))
    for pin, ref in (("1", "#PWR7101"), ("8", "#PWR7102")):
        blob.append(sc.wire_and_power(mux_pins, "U4", pin, UX, UY, "+5VSB", PROJECT, USB_PATH, ref))
    blob.append(sc.wire_and_label(mux_pins, "U4", "2", UX, UY, "VBUS"))
    # CP2 (3), OV2 (4) -> GND; GND (12) -> GND; ST (9) -> genuine no_connect
    # (see splice_usb_ingress_eps.py's header for why -- the identical fix
    # applies verbatim here: ST is "Output" typed, hard-grounding it puts a
    # second driver on GND alongside the board's existing PWR_FLAG, a real
    # pin_to_pin ERROR, not the usual benign-warning class).
    for pin, ref in (("3", "#PWR7103"), ("4", "#PWR7104"), ("12", "#PWR7106")):
        blob.append(sc.wire_and_power(mux_pins, "U4", pin, UX, UY, "GND", PROJECT, USB_PATH, ref))
    blob.append(sc.noconnect_pin(mux_pins, "U4", "9", UX, UY))
    blob.append(sc.wire_and_label(mux_pins, "U4", "5", UX, UY, "U4_OV1"))
    blob.append(sc.wire_and_label(mux_pins, "U4", "6", UX, UY, "U4_PR1"))
    blob.append(sc.wire_and_global_label(mux_pins, "U4", "7", UX, UY, GLOBAL_VCC_RJ45))
    blob.append(sc.wire_and_label(mux_pins, "U4", "10", UX, UY, "U4_ILM"))
    blob.append(sc.wire_and_label(mux_pins, "U4", "11", UX, UY, "U4_SS"))

    # ---------- 4. R14 (ILIM 100k) ----------
    RX, RY = sc.gsnap(300.0), sc.gsnap(40.0)
    blob.append(cec_sch.emit_symbol("R14", "cec-vendor", "R_Small", "100kΩ", RX, RY,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R14"]))
    blob.append(sc.wire_and_label(r_pins, "R14", "1", RX, RY, "U4_ILM"))
    blob.append(sc.wire_and_power(r_pins, "R14", "2", RX, RY, "GND", PROJECT, USB_PATH, "#PWR7107"))

    # ---------- 5. R15/R16 (OV1 divider 47k/10k) ----------
    RX2, RY2, RY3 = sc.gsnap(300.0), sc.gsnap(60.0), sc.gsnap(75.0)
    blob.append(cec_sch.emit_symbol("R15", "cec-vendor", "R_Small", "47kΩ", RX2, RY2,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R15"]))
    blob.append(sc.wire_and_global_label(r_pins, "R15", "1", RX2, RY2, GLOBAL_VCC_RJ45))
    blob.append(sc.wire_and_label(r_pins, "R15", "2", RX2, RY2, "U4_OV1"))
    blob.append(cec_sch.emit_symbol("R16", "cec-vendor", "R_Small", "10kΩ", RX2, RY3,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R16"]))
    blob.append(sc.wire_and_label(r_pins, "R16", "1", RX2, RY3, "U4_OV1"))
    blob.append(sc.wire_and_power(r_pins, "R16", "2", RX2, RY3, "GND", PROJECT, USB_PATH, "#PWR7108"))

    # ---------- 6. R17/R18 (PR1 divider 100k/33k) ----------
    RX4, RY4, RY5 = sc.gsnap(300.0), sc.gsnap(95.0), sc.gsnap(110.0)
    blob.append(cec_sch.emit_symbol("R17", "cec-vendor", "R_Small", "100kΩ", RX4, RY4,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R17"]))
    blob.append(sc.wire_and_global_label(r_pins, "R17", "1", RX4, RY4, GLOBAL_VCC_RJ45))
    blob.append(sc.wire_and_label(r_pins, "R17", "2", RX4, RY4, "U4_PR1"))
    blob.append(cec_sch.emit_symbol("R18", "cec-vendor", "R_Small", "33kΩ", RX4, RY5,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R18"]))
    blob.append(sc.wire_and_label(r_pins, "R18", "1", RX4, RY5, "U4_PR1"))
    blob.append(sc.wire_and_power(r_pins, "R18", "2", RX4, RY5, "GND", PROJECT, USB_PATH, "#PWR7109"))

    # ---------- 7. C42 (SS 2.2uF), C43 (IN2 bypass 100nF), C44 (IN2 bulk 10uF) ----------
    CX, CY1, CY2, CY3 = sc.gsnap(250.0), sc.gsnap(60.0), sc.gsnap(90.0), sc.gsnap(105.0)
    blob.append(cec_sch.emit_symbol("C42", "cec-vendor", "C_Small", "2.2uF", CX, CY1,
                                     sorted(c_pins.keys()), PROJECT, USB_PATH, fp=FP_C0603, props=BOM["C42"]))
    blob.append(sc.wire_and_label(c_pins, "C42", "1", CX, CY1, "U4_SS"))
    blob.append(sc.wire_and_power(c_pins, "C42", "2", CX, CY1, "GND", PROJECT, USB_PATH, "#PWR7110"))
    blob.append(cec_sch.emit_symbol("C43", "cec-vendor", "C_Small", "100nF", CX, CY2,
                                     sorted(c_pins.keys()), PROJECT, USB_PATH, fp=FP_C0402, props=BOM["C43"]))
    blob.append(sc.wire_and_label(c_pins, "C43", "1", CX, CY2, "VBUS"))
    blob.append(sc.wire_and_power(c_pins, "C43", "2", CX, CY2, "GND", PROJECT, USB_PATH, "#PWR7111"))
    blob.append(cec_sch.emit_symbol("C44", "cec-vendor", "C_Small", "10uF", CX, CY3,
                                     sorted(c_pins.keys()), PROJECT, USB_PATH, fp=FP_C0805, props=BOM["C44"]))
    blob.append(sc.wire_and_label(c_pins, "C44", "1", CX, CY3, "VBUS"))
    blob.append(sc.wire_and_power(c_pins, "C44", "2", CX, CY3, "GND", PROJECT, USB_PATH, "#PWR7112"))

    # ---------- 8. PWR_FLAG drivers for VBUS and VCC_RJ45 (power_in typed IN1/IN2) ----------
    FX1, FY1 = sc.gsnap(250.0), sc.gsnap(120.0)
    blob.append(cec_sch.emit_symbol("#FLG7101", "cec-power", "PWR_FLAG", "PWR_FLAG", FX1, FY1,
                                     sorted(flag_pins.keys()), PROJECT, USB_PATH, fp=""))
    blob.append(sc.wire_and_label(flag_pins, "#FLG7101", "1", FX1, FY1, "VBUS"))
    FX2, FY2 = sc.gsnap(270.0), sc.gsnap(120.0)
    blob.append(cec_sch.emit_symbol("#FLG7102", "cec-power", "PWR_FLAG", "PWR_FLAG", FX2, FY2,
                                     sorted(flag_pins.keys()), PROJECT, USB_PATH, fp=""))
    blob.append(sc.wire_and_global_label(flag_pins, "#FLG7102", "1", FX2, FY2, GLOBAL_VCC_RJ45))

    new_content = "\n".join(blob) + "\n"
    if "\t(sheet_instances" in txt:
        idx = txt.rindex("\t(sheet_instances")
        txt = txt[:idx] + new_content + txt[idx:]
    else:
        i0 = txt.index("(kicad_sch")
        end = cec_sch.carve(txt, i0)
        pos = i0 + len(end) - 1
        txt = txt[:pos] + new_content + txt[pos:]
    open(USB_SCH, "w").write(txt)
    print(f"07-usb-flash.kicad_sch: wrote {len(blob)} new elements")

    # ---------- 9. 01-hub-link.kicad_sch: retarget FB2's rail-side stub ----------
    txt2 = open(HUBLINK_SCH).read()
    txt2, kind, info = sc.remove_terminal_at(txt2, 185.42, 102.87)
    assert kind == "power" and info[1] == "+5VSB", info
    blob2 = [cec_sch.emit_global_label(GLOBAL_VCC_RJ45, 185.42, 102.87, 180)]
    new_content2 = "\n".join(blob2) + "\n"
    idx2 = txt2.rindex("\t(sheet_instances") if "\t(sheet_instances" in txt2 else None
    if idx2 is None:
        i0 = txt2.index("(kicad_sch")
        end = cec_sch.carve(txt2, i0)
        idx2 = i0 + len(end) - 1
    txt2 = txt2[:idx2] + new_content2 + txt2[idx2:]
    open(HUBLINK_SCH, "w").write(txt2)
    print(f"01-hub-link.kicad_sch: FB2's +5VSB tie ({info[0]}) removed, replaced with "
          f"global_label {GLOBAL_VCC_RJ45!r} at the same point")

    print("PCIe 2-port USB-ingress splice complete.")
