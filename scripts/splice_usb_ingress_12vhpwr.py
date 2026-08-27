#!/usr/bin/env python3
# One-shot splice: 12VHPWR Standard USB-ingress TPS2121 mux (spec v1.6.0 Sec
# 6.14; owner rulings 2026-07-24; docs/usb-ingress-bom-delta-2026-07-24.md Sec
# 3.3).
#
# Same shape as scripts/splice_usb_ingress_eps.py (see its header for the
# rationale in full). Verified against the live file before writing (not
# assumed): D2/FB1's own stubs on THIS board are plain (label ...) instances,
# same mechanism as EPS (D3/D4 sit upstream of FB1 too, also matching EPS) --
# the one real per-board difference is FB2's pin ASSIGNMENT: its rail-side pin
# is pin 1 here (not pin 2 like EPS/PCIe), same rotation, just wired the other
# way around at schematic-capture time (netlist-verified: FB2 = {1:+5VSB,
# 2:/VCC_RAW} on this board vs {1:/VCC_*_RAW, 2:+5VSB} on EPS/PCIe).
#
# Refdes: U5 (not U4 -- U1-U4 are the ESP32/REF3030/etc, U10-U15 are the six
# INA240 sense amps per the delta doc's own note). R24/C25 collided with an
# unrelated existing pair (same class of collision as every other board) --
# shifted to R25-R29/C26-C28, free as verified live.
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch  # noqa: E402
import splice_usb_ingress_common as sc  # noqa: E402

ROOT_DIR = os.path.join(HERE, "..", "beta", "12vhpwr-standard")
USB_SCH = os.path.join(ROOT_DIR, "08-usb.kicad_sch")
HUBLINK_SCH = os.path.join(ROOT_DIR, "09-hub-link.kicad_sch")
DONOR = os.path.join(HERE, "..", "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")

PROJECT = "12vhpwr-standard-module"
ROOT_UUID = "436b24cb-7227-4a56-93c7-4c5d9a5d0058"
USB_SHEET_UUID = "819d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a08"
HUBLINK_SHEET_UUID = "929d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a09"
USB_PATH = f"{ROOT_UUID}/{USB_SHEET_UUID}"
HUBLINK_PATH = f"{ROOT_UUID}/{HUBLINK_SHEET_UUID}"

GLOBAL_VCC_RJ45 = "VCC_RJ45"

BOM = {
    "U5": dict(Manufacturer="Texas Instruments", MPN="TPS2121RUXR", LCSC="C485916"),
    "F1": dict(Manufacturer="Littelfuse", MPN="1206L075/16WR", LCSC="C371166",
               Note="750mA hold/1.5A trip/16V resettable PTC polyfuse, VBUS ingress "
                    "defense layer 2 (spec v1.6.0 Sec 6.14)."),
    "R25": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1003TCE", LCSC="C25741",
                Note="U5 ILIM strap -> ~1.24A typical (I_LIM=65.2/R_kOhm^0.861)."),
    "R26": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF4322TCE", LCSC="C25894",
                Datasheet="https://www.lcsc.com/product-detail/C25894.html",
                Note="U5 OV1 top; 43.2k/10k gives 5.639V nominal and 5.287..5.948V "
                     "at specified resistor/VREF extremes."),
    "R27": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1002TCE", LCSC="C25744",
                Note="U5 OV1 divider bottom (GND side) -> ~6.04V typical cutoff."),
    "R28": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1003TCE", LCSC="C25741",
                Note="U5 PR1 divider top (IN1 side)."),
    "R29": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF3302TCE", LCSC="C25779",
                Note="U5 PR1 divider bottom (GND side) -> ~4.27V typical validity floor."),
    "C26": dict(Manufacturer="Samsung", MPN="CL10A225KO8NNNC", LCSC="C23630",
                Note="U5 soft-start cap (~10ms output ramp, hub-proven value)."),
    "C27": dict(Manufacturer="Samsung", MPN="CL05B104KO5NNNC", LCSC="C1525",
                Note="U5 IN2 (VBUS) bypass."),
    "C28": dict(Manufacturer="Samsung", MPN="CL21A106KAYNNNE", LCSC="C15850",
                Note="U5 IN2 (VBUS) bulk (additional to the existing C9 on the same node)."),
}

FP_R0402 = "cec-Resistor_SMD:R_0402_1005Metric"
FP_C0402 = "cec-Capacitor_SMD:C_0402_1005Metric"
FP_C0603 = "cec-Capacitor_SMD:C_0603_1608Metric"
FP_C0805 = "cec-Capacitor_SMD:C_0805_2012Metric"

if __name__ == "__main__":
    txt = open(USB_SCH).read()
    if '(property "Reference" "U5"' in txt:
        raise SystemExit("REFUSE: U5 already present in 08-usb.kicad_sch -- splice already applied?")

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
    txt = sc.remove_wire_between(txt, 194.31, 59.69, 190.5, 59.69)
    txt, kind1, info1 = sc.remove_terminal_at(txt, 190.5, 59.69)
    assert kind1 == "power" and info1[1] == "+5VSB", info1
    txt = sc.remove_wire_between(txt, 201.93, 59.69, 205.74, 59.69)
    txt, kind2, info2 = sc.remove_terminal_at(txt, 205.74, 59.69)
    assert kind2 == "label" and info2 == "VBUS", info2
    print("D2 removed; stub terminals:", info1, info2)

    # ---------- 2. insert F1 ahead of FB1 (VBUS_RAW -> F1 -> VBUS_F -> FB1) ----------
    txt, old_lbl, old_tag = sc.rename_label_at(txt, 190.5, 91.44, "VBUS_F")
    assert old_lbl == "VBUS_RAW" and old_tag == "label", (old_lbl, old_tag)
    F1_X, F1_Y = sc.gsnap(255.0), sc.gsnap(20.0)
    blob = [
        cec_sch.emit_symbol("F1", "cec-vendor", "R_Small", "750mA/16V PTC", F1_X, F1_Y,
                             sorted(r_pins.keys()), PROJECT, USB_PATH,
                             fp="cec-Resistor_SMD:R_1206_3216Metric", props=BOM["F1"]),
        sc.wire_and_label(r_pins, "F1", "1", F1_X, F1_Y, "VBUS_RAW"),
        sc.wire_and_label(r_pins, "F1", "2", F1_X, F1_Y, "VBUS_F"),
    ]

    # ---------- 3. place U5 + straps ----------
    UX, UY = sc.gsnap(280.0), sc.gsnap(50.0)
    blob.append(cec_sch.emit_symbol("U5", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR",
                                     UX, UY, sorted(mux_pins.keys()), PROJECT, USB_PATH,
                                     fp="cec-Package_DFN_QFN:RUX0012A", props=BOM["U5"]))
    for pin, ref in (("1", "#PWR8101"), ("8", "#PWR8102")):
        blob.append(sc.wire_and_power(mux_pins, "U5", pin, UX, UY, "+5VSB", PROJECT, USB_PATH, ref))
    blob.append(sc.wire_and_label(mux_pins, "U5", "2", UX, UY, "VBUS"))
    # CP2 (3), OV2 (4) -> GND; GND (12) -> GND; ST (9) -> genuine no_connect
    # (see splice_usb_ingress_eps.py's header -- the identical pin_to_pin ERROR
    # class applies here since ST is "Output" typed).
    for pin, ref in (("3", "#PWR8103"), ("4", "#PWR8104"), ("12", "#PWR8106")):
        blob.append(sc.wire_and_power(mux_pins, "U5", pin, UX, UY, "GND", PROJECT, USB_PATH, ref))
    blob.append(sc.noconnect_pin(mux_pins, "U5", "9", UX, UY))
    blob.append(sc.wire_and_label(mux_pins, "U5", "5", UX, UY, "U5_OV1"))
    blob.append(sc.wire_and_label(mux_pins, "U5", "6", UX, UY, "U5_PR1"))
    blob.append(sc.wire_and_global_label(mux_pins, "U5", "7", UX, UY, GLOBAL_VCC_RJ45))
    blob.append(sc.wire_and_label(mux_pins, "U5", "10", UX, UY, "U5_ILM"))
    blob.append(sc.wire_and_label(mux_pins, "U5", "11", UX, UY, "U5_SS"))

    # ---------- 4. R25 (ILIM 100k) ----------
    RX, RY = sc.gsnap(305.0), sc.gsnap(30.0)
    blob.append(cec_sch.emit_symbol("R25", "cec-vendor", "R_Small", "100kΩ", RX, RY,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R25"]))
    blob.append(sc.wire_and_label(r_pins, "R25", "1", RX, RY, "U5_ILM"))
    blob.append(sc.wire_and_power(r_pins, "R25", "2", RX, RY, "GND", PROJECT, USB_PATH, "#PWR8107"))

    # ---------- 5. R26/R27 (OV1 divider 43.2k/10k) ----------
    RX2, RY2, RY3 = sc.gsnap(305.0), sc.gsnap(50.0), sc.gsnap(65.0)
    blob.append(cec_sch.emit_symbol("R26", "cec-vendor", "R_Small", "43.2kΩ", RX2, RY2,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R26"]))
    blob.append(sc.wire_and_global_label(r_pins, "R26", "1", RX2, RY2, GLOBAL_VCC_RJ45))
    blob.append(sc.wire_and_label(r_pins, "R26", "2", RX2, RY2, "U5_OV1"))
    blob.append(cec_sch.emit_symbol("R27", "cec-vendor", "R_Small", "10kΩ", RX2, RY3,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R27"]))
    blob.append(sc.wire_and_label(r_pins, "R27", "1", RX2, RY3, "U5_OV1"))
    blob.append(sc.wire_and_power(r_pins, "R27", "2", RX2, RY3, "GND", PROJECT, USB_PATH, "#PWR8108"))

    # ---------- 6. R28/R29 (PR1 divider 100k/33k) ----------
    RX4, RY4, RY5 = sc.gsnap(305.0), sc.gsnap(85.0), sc.gsnap(100.0)
    blob.append(cec_sch.emit_symbol("R28", "cec-vendor", "R_Small", "100kΩ", RX4, RY4,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R28"]))
    blob.append(sc.wire_and_global_label(r_pins, "R28", "1", RX4, RY4, GLOBAL_VCC_RJ45))
    blob.append(sc.wire_and_label(r_pins, "R28", "2", RX4, RY4, "U5_PR1"))
    blob.append(cec_sch.emit_symbol("R29", "cec-vendor", "R_Small", "33kΩ", RX4, RY5,
                                     sorted(r_pins.keys()), PROJECT, USB_PATH, fp=FP_R0402, props=BOM["R29"]))
    blob.append(sc.wire_and_label(r_pins, "R29", "1", RX4, RY5, "U5_PR1"))
    blob.append(sc.wire_and_power(r_pins, "R29", "2", RX4, RY5, "GND", PROJECT, USB_PATH, "#PWR8109"))

    # ---------- 7. C26 (SS 2.2uF), C27 (IN2 bypass 100nF), C28 (IN2 bulk 10uF) ----------
    CX, CY1, CY2, CY3 = sc.gsnap(255.0), sc.gsnap(50.0), sc.gsnap(80.0), sc.gsnap(95.0)
    blob.append(cec_sch.emit_symbol("C26", "cec-vendor", "C_Small", "2.2uF", CX, CY1,
                                     sorted(c_pins.keys()), PROJECT, USB_PATH, fp=FP_C0603, props=BOM["C26"]))
    blob.append(sc.wire_and_label(c_pins, "C26", "1", CX, CY1, "U5_SS"))
    blob.append(sc.wire_and_power(c_pins, "C26", "2", CX, CY1, "GND", PROJECT, USB_PATH, "#PWR8110"))
    blob.append(cec_sch.emit_symbol("C27", "cec-vendor", "C_Small", "100nF", CX, CY2,
                                     sorted(c_pins.keys()), PROJECT, USB_PATH, fp=FP_C0402, props=BOM["C27"]))
    blob.append(sc.wire_and_label(c_pins, "C27", "1", CX, CY2, "VBUS"))
    blob.append(sc.wire_and_power(c_pins, "C27", "2", CX, CY2, "GND", PROJECT, USB_PATH, "#PWR8111"))
    blob.append(cec_sch.emit_symbol("C28", "cec-vendor", "C_Small", "10uF", CX, CY3,
                                     sorted(c_pins.keys()), PROJECT, USB_PATH, fp=FP_C0805, props=BOM["C28"]))
    blob.append(sc.wire_and_label(c_pins, "C28", "1", CX, CY3, "VBUS"))
    blob.append(sc.wire_and_power(c_pins, "C28", "2", CX, CY3, "GND", PROJECT, USB_PATH, "#PWR8112"))

    # ---------- 8. PWR_FLAG drivers for VBUS and VCC_RJ45 ----------
    FX1, FY1 = sc.gsnap(255.0), sc.gsnap(110.0)
    blob.append(cec_sch.emit_symbol("#FLG8101", "cec-power", "PWR_FLAG", "PWR_FLAG", FX1, FY1,
                                     sorted(flag_pins.keys()), PROJECT, USB_PATH, fp=""))
    blob.append(sc.wire_and_label(flag_pins, "#FLG8101", "1", FX1, FY1, "VBUS"))
    FX2, FY2 = sc.gsnap(280.0), sc.gsnap(110.0)
    blob.append(cec_sch.emit_symbol("#FLG8102", "cec-power", "PWR_FLAG", "PWR_FLAG", FX2, FY2,
                                     sorted(flag_pins.keys()), PROJECT, USB_PATH, fp=""))
    blob.append(sc.wire_and_global_label(flag_pins, "#FLG8102", "1", FX2, FY2, GLOBAL_VCC_RJ45))

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
    print(f"08-usb.kicad_sch: wrote {len(blob)} new elements")

    # ---------- 9. 09-hub-link.kicad_sch: retarget FB2's rail-side stub (pin 1 here) ----------
    txt2 = open(HUBLINK_SCH).read()
    txt2, kind, info = sc.remove_terminal_at(txt2, 170.18, 113.03)
    assert kind == "power" and info[1] == "+5VSB", info
    blob2 = [cec_sch.emit_global_label(GLOBAL_VCC_RJ45, 170.18, 113.03, 180)]
    new_content2 = "\n".join(blob2) + "\n"
    idx2 = txt2.rindex("\t(sheet_instances") if "\t(sheet_instances" in txt2 else None
    if idx2 is None:
        i0 = txt2.index("(kicad_sch")
        end = cec_sch.carve(txt2, i0)
        idx2 = i0 + len(end) - 1
    txt2 = txt2[:idx2] + new_content2 + txt2[idx2:]
    open(HUBLINK_SCH, "w").write(txt2)
    print(f"09-hub-link.kicad_sch: FB2's +5VSB tie ({info[0]}) removed, replaced with "
          f"global_label {GLOBAL_VCC_RJ45!r} at the same point")

    print("12VHPWR Standard USB-ingress splice complete.")
