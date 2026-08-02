#!/usr/bin/env python3
# One-shot splice: 24-pin ATX rev3 USB-ingress TPS2121 mux, SECOND cascade stage
# (spec v1.6.0 Sec 6.14; owner rulings 2026-07-24;
# docs/usb-ingress-bom-delta-2026-07-24.md Sec 3.4).
#
# Unlike EPS/PCIe/12VHPWR (a single new mux replacing D2 outright), the 24-pin
# already muxes MAIN_5V x 5VSB via the EXISTING U5 (R50 ILIM 20k / R52+R53 PR1
# 100k/33k / C50 SS 2.2uF -- a real divider-style PR1, not the hub's hard-tie
# shortcut). Per the doc: "The new stage inserts IN THE 5VSB LEG... total
# priority MAIN_5V > 5VSB > USB." Concretely:
#   - NEW U6: IN1 (pin 7) = +5VSB (the module's own sensed/global 5VSB rail,
#     the SAME net that already feeds C20/C21/J3.9/RS4.1/U13.10 -- unchanged,
#     just one more consumer); IN2 (pin 2) = VBUS behind new polyfuse F1 ahead
#     of the existing FB1 bead; OUT (1,8) = a NEW net "5VSB_MUX".
#   - U5.pin 2 (IN2) NET MOVE: was tied directly to the +5VSB power symbol;
#     that tie is removed and replaced with a label joining "5VSB_MUX" (U6's
#     output) instead -- this is the actual "leg insertion", verified against
#     the live file (U5.pin2's own stub, not touched anywhere else).
#   - D2 (the old standalone-mode ORing diode, +5V_SYS <- VBUS, entirely
#     separate from/parallel to U5) is deleted outright, same as every other
#     board.
#   - C50/R53 ANNOTATE: back-fill LCSC (+MPN/Manufacturer for completeness)
#     onto U5's own existing, LCSC-blank support parts. C50's selected C23630
#     is a 0603 part, so the generator and authoritative schematic must use a
#     0603 footprint. The earlier 0402 footprint was not assembly-compatible.
#   - CP2/OV2/ST straps: the per-board table has no explicit STRAP row for U6
#     (unlike EPS/PCIe/12VHPWR's tables, which each have one) -- applying spec
#     Sec 2's general datasheet rule ("CP2, OV2 ... and ST strap to GND per
#     the pin table") here too, since nothing suggests U6 is exempt and every
#     sibling module gets it; ST is left a genuine no_connect for the same
#     pin_to_pin-ERROR reason recorded on every other board (flagged, not
#     silently assumed -- the doc's own table is silent on this specific
#     point for U6).
#
# This board's file is FLAT (no hierarchy), so unlike EPS/PCIe/12VHPWR there is
# no cross-sheet net and no global_label is needed anywhere in this splice.
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch  # noqa: E402
import splice_usb_ingress_common as sc  # noqa: E402

SCH = os.path.join(HERE, "..", "beta", "atx-24pin-rev3", "24pin-module.kicad_sch")
DONOR = os.path.join(HERE, "..", "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")

PROJECT = "24pin-module"
ROOT_UUID = "a4774022-41d4-4be7-85b6-fed5477a3f9f"

BOM = {
    "U6": dict(Manufacturer="Texas Instruments", MPN="TPS2121RUXR", LCSC="C485916"),
    "F1": dict(Manufacturer="Littelfuse", MPN="1206L075/16WR", LCSC="C371166",
               Note="750mA hold/1.5A trip/16V resettable PTC polyfuse, VBUS ingress "
                    "defense layer 2 (spec v1.6.0 Sec 6.14). Order: J5 -> D3(PESD) -> "
                    "F1 -> FB1 -> U6.IN2."),
    "R54": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1003TCE", LCSC="C25741",
                Note="U6 ILIM strap -> ~1.24A typical (I_LIM=65.2/R_kOhm^0.861)."),
    "R55": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF4702TCE", LCSC="C25792",
                Note="U6 OV1 divider top (IN1/+5VSB side)."),
    "R56": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1002TCE", LCSC="C25744",
                Note="U6 OV1 divider bottom (GND side) -> ~6.04V typical cutoff, "
                     "faulty-PSU-5VSB-tap disconnect."),
    "R57": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1003TCE", LCSC="C25741",
                Note="U6 PR1 divider top (IN1/+5VSB side) -- mirrors U5's own R52 style."),
    "R58": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF3302TCE", LCSC="C25779",
                Note="U6 PR1 divider bottom (GND side) -> ~4.27V typical validity floor "
                     "-- mirrors U5's own R53 style."),
    "C51": dict(Manufacturer="Samsung", MPN="CL10A225KO8NNNC", LCSC="C23630",
                Note="U6 soft-start cap (~10ms output ramp, hub-proven value)."),
    "C52": dict(Manufacturer="Samsung", MPN="CL05B104KO5NNNC", LCSC="C1525",
                Note="U6 IN2 (VBUS) bypass."),
    "C53": dict(Manufacturer="Samsung", MPN="CL21A106KAYNNNE", LCSC="C15850",
                Note="U6 IN2 (VBUS) bulk (additional to the existing C9 on the same node)."),
}

ANNOTATE = {
    "C50": dict(LCSC="C23630", MPN="CL10A225KO8NNNC", Manufacturer="Samsung"),
    "R53": dict(LCSC="C25779", MPN="0402WGF3302TCE", Manufacturer="UNI-ROYAL"),
}

FP_R0402 = "cec-Resistor_SMD:R_0402_1005Metric"
FP_C0402 = "cec-Capacitor_SMD:C_0402_1005Metric"
FP_C0603 = "cec-Capacitor_SMD:C_0603_1608Metric"
FP_C0805 = "cec-Capacitor_SMD:C_0805_2012Metric"

if __name__ == "__main__":
    txt = open(SCH).read()
    if '(property "Reference" "U6"' in txt:
        raise SystemExit("REFUSE: U6 already present -- splice already applied?")

    txt, added = sc.ensure_lib_symbol(txt, "cec-vendor:TPS2121RUXR", DONOR)
    print("TPS2121RUXR lib_symbol imported:", added)
    txt, added2 = sc.ensure_lib_symbol(txt, "cec-power:PWR_FLAG", DONOR)
    print("PWR_FLAG lib_symbol imported:", added2)

    r_pins = sc.get_pin_table(txt, "cec-vendor:R_Small")
    c_pins = sc.get_pin_table(txt, "cec-vendor:C_Small")
    mux_pins = sc.get_pin_table(txt, "cec-vendor:TPS2121RUXR")
    flag_pins = sc.get_pin_table(txt, "cec-power:PWR_FLAG")

    # ---------- 0. C50/R53 ANNOTATE: back-fill LCSC/MPN/Manufacturer ----------
    for ref, props in ANNOTATE.items():
        txt = sc.add_hidden_properties(txt, ref, props)
    print("Annotated (LCSC/MPN/Manufacturer back-filled):", list(ANNOTATE))

    # ---------- 1. delete D2 (the old standalone-mode ORing diode) entirely ----------
    txt, d2_blk = sc.remove_symbol(txt, "D2")
    assert 'Value" "SS34"' in d2_blk
    txt = sc.remove_wire_between(txt, 86.36, 267.97, 82.55, 267.97)
    txt, kind1, info1 = sc.remove_terminal_at(txt, 82.55, 267.97)
    assert kind1 == "power" and info1[1] == "+5V_SYS", info1
    txt = sc.remove_wire_between(txt, 93.98, 267.97, 97.79, 267.97)
    txt, kind2, info2 = sc.remove_terminal_at(txt, 97.79, 267.97)
    assert kind2 == "label" and info2 == "VBUS", info2
    print("D2 removed; stub terminals:", info1, info2)

    # ---------- 2. insert F1 ahead of FB1 (VBUS_RAW -> F1 -> VBUS_F -> FB1) ----------
    txt, old_lbl, old_tag = sc.rename_label_at(txt, 82.55, 335.28, "VBUS_F")
    assert old_lbl == "VBUS_RAW" and old_tag == "label", (old_lbl, old_tag)
    F1_X, F1_Y = sc.gsnap(470.0), sc.gsnap(20.0)
    blob = [
        cec_sch.emit_symbol("F1", "cec-vendor", "R_Small", "750mA/16V PTC", F1_X, F1_Y,
                             sorted(r_pins.keys()), PROJECT, ROOT_UUID,
                             fp="cec-Resistor_SMD:R_1206_3216Metric", props=BOM["F1"]),
        sc.wire_and_label(r_pins, "F1", "1", F1_X, F1_Y, "VBUS_RAW"),
        sc.wire_and_label(r_pins, "F1", "2", F1_X, F1_Y, "VBUS_F"),
    ]

    # ---------- 3. U5.pin2 NET MOVE: +5VSB (direct) -> 5VSB_MUX (U6's output) ----------
    txt, kind3, info3 = sc.remove_terminal_at(txt, 34.29, 209.55)
    assert kind3 == "power" and info3[1] == "+5VSB", info3
    blob.append(cec_sch.emit_label("5VSB_MUX", 34.29, 209.55, 90))
    print("U5.pin2 net move: was +5VSB direct tie", info3, "-> now label 5VSB_MUX")

    # ---------- 4. place U6 + straps ----------
    UX, UY = sc.gsnap(490.0), sc.gsnap(50.0)
    blob.append(cec_sch.emit_symbol("U6", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR",
                                     UX, UY, sorted(mux_pins.keys()), PROJECT, ROOT_UUID,
                                     fp="cec-Package_DFN_QFN:RUX0012A", props=BOM["U6"]))
    # OUT (1,8) -> 5VSB_MUX (joins U5.pin2 by name, both now on the new net)
    blob.append(sc.wire_and_label(mux_pins, "U6", "1", UX, UY, "5VSB_MUX"))
    blob.append(sc.wire_and_label(mux_pins, "U6", "8", UX, UY, "5VSB_MUX"))
    # IN2 (pin 2) -> VBUS (local; F1/FB1 already carry it upstream)
    blob.append(sc.wire_and_label(mux_pins, "U6", "2", UX, UY, "VBUS"))
    # CP2 (3), OV2 (4) -> GND; GND (12) -> GND; ST (9) -> genuine no_connect
    for pin, ref in (("3", "#PWR9101"), ("4", "#PWR9102"), ("12", "#PWR9104")):
        blob.append(sc.wire_and_power(mux_pins, "U6", pin, UX, UY, "GND", PROJECT, ROOT_UUID, ref))
    blob.append(sc.noconnect_pin(mux_pins, "U6", "9", UX, UY))
    # OV1 (5) -> divider node; PR1 (6) -> divider node; IN1 (7) -> +5VSB (global power)
    blob.append(sc.wire_and_label(mux_pins, "U6", "5", UX, UY, "U6_OV1"))
    blob.append(sc.wire_and_label(mux_pins, "U6", "6", UX, UY, "U6_PR1"))
    blob.append(sc.wire_and_power(mux_pins, "U6", "7", UX, UY, "+5VSB", PROJECT, ROOT_UUID, "#PWR9105"))
    # ILIM (10) -> R54; SS (11) -> C51
    blob.append(sc.wire_and_label(mux_pins, "U6", "10", UX, UY, "U6_ILM"))
    blob.append(sc.wire_and_label(mux_pins, "U6", "11", UX, UY, "U6_SS"))

    # ---------- 5. R54 (ILIM 100k) ----------
    RX, RY = sc.gsnap(520.0), sc.gsnap(30.0)
    blob.append(cec_sch.emit_symbol("R54", "cec-vendor", "R_Small", "100kΩ", RX, RY,
                                     sorted(r_pins.keys()), PROJECT, ROOT_UUID, fp=FP_R0402, props=BOM["R54"]))
    blob.append(sc.wire_and_label(r_pins, "R54", "1", RX, RY, "U6_ILM"))
    blob.append(sc.wire_and_power(r_pins, "R54", "2", RX, RY, "GND", PROJECT, ROOT_UUID, "#PWR9106"))

    # ---------- 6. R55/R56 (OV1 divider 47k/10k, from +5VSB) ----------
    RX2, RY2, RY3 = sc.gsnap(520.0), sc.gsnap(50.0), sc.gsnap(65.0)
    blob.append(cec_sch.emit_symbol("R55", "cec-vendor", "R_Small", "47kΩ", RX2, RY2,
                                     sorted(r_pins.keys()), PROJECT, ROOT_UUID, fp=FP_R0402, props=BOM["R55"]))
    blob.append(sc.wire_and_power(r_pins, "R55", "1", RX2, RY2, "+5VSB", PROJECT, ROOT_UUID, "#PWR9107"))
    blob.append(sc.wire_and_label(r_pins, "R55", "2", RX2, RY2, "U6_OV1"))
    blob.append(cec_sch.emit_symbol("R56", "cec-vendor", "R_Small", "10kΩ", RX2, RY3,
                                     sorted(r_pins.keys()), PROJECT, ROOT_UUID, fp=FP_R0402, props=BOM["R56"]))
    blob.append(sc.wire_and_label(r_pins, "R56", "1", RX2, RY3, "U6_OV1"))
    blob.append(sc.wire_and_power(r_pins, "R56", "2", RX2, RY3, "GND", PROJECT, ROOT_UUID, "#PWR9108"))

    # ---------- 7. R57/R58 (PR1 divider 100k/33k, from +5VSB) ----------
    RX4, RY4, RY5 = sc.gsnap(520.0), sc.gsnap(85.0), sc.gsnap(100.0)
    blob.append(cec_sch.emit_symbol("R57", "cec-vendor", "R_Small", "100kΩ", RX4, RY4,
                                     sorted(r_pins.keys()), PROJECT, ROOT_UUID, fp=FP_R0402, props=BOM["R57"]))
    blob.append(sc.wire_and_power(r_pins, "R57", "1", RX4, RY4, "+5VSB", PROJECT, ROOT_UUID, "#PWR9109"))
    blob.append(sc.wire_and_label(r_pins, "R57", "2", RX4, RY4, "U6_PR1"))
    blob.append(cec_sch.emit_symbol("R58", "cec-vendor", "R_Small", "33kΩ", RX4, RY5,
                                     sorted(r_pins.keys()), PROJECT, ROOT_UUID, fp=FP_R0402, props=BOM["R58"]))
    blob.append(sc.wire_and_label(r_pins, "R58", "1", RX4, RY5, "U6_PR1"))
    blob.append(sc.wire_and_power(r_pins, "R58", "2", RX4, RY5, "GND", PROJECT, ROOT_UUID, "#PWR9110"))

    # ---------- 8. C51 (SS 2.2uF), C52 (IN2 bypass 100nF), C53 (IN2 bulk 10uF) ----------
    CX, CY1, CY2, CY3 = sc.gsnap(470.0), sc.gsnap(50.0), sc.gsnap(80.0), sc.gsnap(95.0)
    blob.append(cec_sch.emit_symbol("C51", "cec-vendor", "C_Small", "2.2uF", CX, CY1,
                                     sorted(c_pins.keys()), PROJECT, ROOT_UUID, fp=FP_C0603, props=BOM["C51"]))
    blob.append(sc.wire_and_label(c_pins, "C51", "1", CX, CY1, "U6_SS"))
    blob.append(sc.wire_and_power(c_pins, "C51", "2", CX, CY1, "GND", PROJECT, ROOT_UUID, "#PWR9111"))
    blob.append(cec_sch.emit_symbol("C52", "cec-vendor", "C_Small", "100nF", CX, CY2,
                                     sorted(c_pins.keys()), PROJECT, ROOT_UUID, fp=FP_C0402, props=BOM["C52"]))
    blob.append(sc.wire_and_label(c_pins, "C52", "1", CX, CY2, "VBUS"))
    blob.append(sc.wire_and_power(c_pins, "C52", "2", CX, CY2, "GND", PROJECT, ROOT_UUID, "#PWR9112"))
    blob.append(cec_sch.emit_symbol("C53", "cec-vendor", "C_Small", "10uF", CX, CY3,
                                     sorted(c_pins.keys()), PROJECT, ROOT_UUID, fp=FP_C0805, props=BOM["C53"]))
    blob.append(sc.wire_and_label(c_pins, "C53", "1", CX, CY3, "VBUS"))
    blob.append(sc.wire_and_power(c_pins, "C53", "2", CX, CY3, "GND", PROJECT, ROOT_UUID, "#PWR9113"))

    # ---------- 9. PWR_FLAG drivers for VBUS and 5VSB_MUX (power_in typed
    # IN2/OUT nets with no genuine power_out pin anywhere on them; +5VSB
    # itself already has a driver elsewhere on this board -- J3's own ATX
    # 5VSB pin -- confirmed by baseline ERC carrying zero power_pin_not_driven
    # hits despite U13/RS4 already power_in-consuming it, so it needs no new
    # flag here). ----------
    FX1, FY1 = sc.gsnap(470.0), sc.gsnap(110.0)
    blob.append(cec_sch.emit_symbol("#FLG9101", "cec-power", "PWR_FLAG", "PWR_FLAG", FX1, FY1,
                                     sorted(flag_pins.keys()), PROJECT, ROOT_UUID, fp=""))
    blob.append(sc.wire_and_label(flag_pins, "#FLG9101", "1", FX1, FY1, "VBUS"))
    FX2, FY2 = sc.gsnap(490.0), sc.gsnap(110.0)
    blob.append(cec_sch.emit_symbol("#FLG9102", "cec-power", "PWR_FLAG", "PWR_FLAG", FX2, FY2,
                                     sorted(flag_pins.keys()), PROJECT, ROOT_UUID, fp=""))
    blob.append(sc.wire_and_label(flag_pins, "#FLG9102", "1", FX2, FY2, "5VSB_MUX"))

    new_content = "\n".join(blob) + "\n"
    if "\t(sheet_instances" in txt:
        idx = txt.rindex("\t(sheet_instances")
        txt = txt[:idx] + new_content + txt[idx:]
    else:
        i0 = txt.index("(kicad_sch")
        end = cec_sch.carve(txt, i0)
        pos = i0 + len(end) - 1
        txt = txt[:pos] + new_content + txt[pos:]
    open(SCH, "w").write(txt)
    print(f"24pin-module.kicad_sch: wrote {len(blob)} new elements")
    print("24-pin ATX rev3 USB-ingress splice complete.")
