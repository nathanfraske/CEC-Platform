#!/usr/bin/env python3
# One-shot splice: EPS 8-pin USB-ingress TPS2121 mux (spec v1.6.0 Sec 6.14; owner
# rulings 2026-07-24; docs/usb-ingress-bom-delta-2026-07-24.md Sec 3.1).
#
# Replaces the D2 SS34 ORing diode (VBUS -> +5VSB, unlimited forward path into a
# faulted PSU's 5VSB bulk -- the back-feed hazard) with U4 = TPS2121RUXR:
#   IN1 (pin 7) = the module's own 5VSB source, taken from the RJ-45 VCC feed
#                 AFTER FB2 (today's board-internal +5VSB tie point) -- this net
#                 crosses from 01-hub-link.kicad_sch into 07-usb-flash.kicad_sch,
#                 so it rides a GLOBAL LABEL "VCC_RJ45" (cec_sch.emit_global_label's
#                 documented purpose: a net crossing sibling leaf sheets with no
#                 direct parent/child sheet-pin relationship -- this board's own
#                 title-block convention otherwise uses drawn sheet-pin lanes for
#                 cross-leaf nets, but adding a new sheet-pin lane pair correctly
#                 requires editing the root sheet-symbol's pin list geometry too;
#                 the global label is the documented-correct, lower-risk primitive
#                 for a single new crossing net -- FLAGGED as a design choice, not
#                 silently assumed).
#   IN2 (pin 2) = VBUS, now behind a NEW polyfuse F1 inserted in series ahead of
#                 the existing FB1 bead (wiring order per Sec 6.14: connector ->
#                 ESD clamp (D3, unchanged) -> F1 (new) -> FB1 (existing) -> mux).
#   OUT (1,8)   = +5VSB (the same global rail every other load already sits on).
#   CP2/OV2/ST -> GND, OV1/PR1 -> real dividers off IN1, per the datasheet pin
#                 table and this delta's per-module strap plan (distinct from the
#                 hub's own "mirror the as-built" instruction, which does not
#                 apply to new MODULE-side instances).
#
# Refdes: the doc's proposed R13/C41 (ILIM/SS) collided with unrelated existing
# parts (an existing 10k/100nF pair on 04-mcu.kicad_sch, landed since the doc's
# 2026-07-24 refdes check) -- shifted to the next free numbers, R14-R18/C42-C44,
# preserving the doc's internal ordering (ILIM, OV1 top/bottom, PR1 top/bottom;
# SS, IN2 bypass, IN2 bulk). U4/F1 were free as proposed.
#
# Verified idempotent-guarded; ERC + netlist verified by the caller.
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch  # noqa: E402
import splice_usb_ingress_common as sc  # noqa: E402

ROOT_DIR = os.path.join(HERE, "..", "beta", "eps-8pin")
USB_SCH = os.path.join(ROOT_DIR, "07-usb-flash.kicad_sch")
HUBLINK_SCH = os.path.join(ROOT_DIR, "01-hub-link.kicad_sch")
DONOR = os.path.join(HERE, "..", "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")

PROJECT = "eps8pin-module"
ROOT_UUID = "ef7f6c4c-2dd9-4559-b472-96b33604786a"
USB_SHEET_UUID = "8adba108-789d-4153-ad59-e74c8138b4d8"
HUBLINK_SHEET_UUID = "67f50ca3-8cb0-4aa6-9a3f-011faa4ff8d7"
USB_PATH = f"{ROOT_UUID}/{USB_SHEET_UUID}"
HUBLINK_PATH = f"{ROOT_UUID}/{HUBLINK_SHEET_UUID}"

GLOBAL_VCC_RJ45 = "VCC_RJ45"

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

    # ---------- 0. bring in the TPS2121RUXR symbol definition ----------
    txt, added = sc.ensure_lib_symbol(txt, "cec-vendor:TPS2121RUXR", DONOR)
    print("TPS2121RUXR lib_symbol imported:", added)
    txt, added2 = sc.ensure_lib_symbol(txt, "cec-power:PWR_FLAG", HUBLINK_SCH)
    print("PWR_FLAG lib_symbol imported:", added2)

    r_pins = sc.get_pin_table(txt, "cec-vendor:R_Small")
    c_pins = sc.get_pin_table(txt, "cec-vendor:C_Small")
    fb_pins = sc.get_pin_table(txt, "cec-vendor:FerriteBead_Small")
    mux_pins = sc.get_pin_table(txt, "cec-vendor:TPS2121RUXR")
    flag_pins = sc.get_pin_table(txt, "cec-power:PWR_FLAG")

    # ---------- 1. delete D2 (the retired ORing diode) entirely ----------
    txt, d2_blk = sc.remove_symbol(txt, "D2")
    assert 'Value" "SS34"' in d2_blk
    # its two stubs: pin1 -> +5VSB power symbol at (198.12,72.39); pin2 -> label
    # "VBUS" at (213.36,72.39) -- both hand-verified against the live file.
    txt = sc.remove_wire_between(txt, 201.93, 72.39, 198.12, 72.39)
    txt, kind1, info1 = sc.remove_terminal_at(txt, 198.12, 72.39)
    assert kind1 == "power" and info1[1] == "+5VSB", info1
    txt = sc.remove_wire_between(txt, 209.55, 72.39, 213.36, 72.39)
    txt, kind2, info2 = sc.remove_terminal_at(txt, 213.36, 72.39)
    assert kind2 == "label" and info2 == "VBUS", info2
    print("D2 removed:", d2_blk.count("uuid"), "uuid refs cleared; stub terminals:", info1, info2)

    # ---------- 2. insert F1 ahead of FB1 (VBUS_RAW -> F1 -> VBUS_F -> FB1) ----------
    txt, old_lbl, old_tag = sc.rename_label_at(txt, 198.12, 104.14, "VBUS_F")
    assert old_lbl == "VBUS_RAW" and old_tag == "label", (old_lbl, old_tag)
    F1_X, F1_Y = sc.gsnap(250.0), sc.gsnap(30.0)
    blob = [
        cec_sch.emit_symbol("F1", "cec-vendor", "R_Small", "750mA/16V PTC", F1_X, F1_Y,
                             sorted(r_pins.keys()), PROJECT, USB_PATH,
                             fp="cec-Resistor_SMD:R_1206_3216Metric", props=BOM["F1"]),
        sc.wire_and_label(r_pins, "F1", "1", F1_X, F1_Y, "VBUS_RAW"),
        sc.wire_and_label(r_pins, "F1", "2", F1_X, F1_Y, "VBUS_F"),
    ]

    # ---------- 3. place U4 + straps ----------
    UX, UY = sc.gsnap(270.0), sc.gsnap(60.0)
    blob.append(cec_sch.emit_symbol("U4", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR",
                                     UX, UY, sorted(mux_pins.keys()), PROJECT, USB_PATH,
                                     fp="cec-Package_DFN_QFN:RUX0012A", props=BOM["U4"]))
    # OUT (1,8) -> +5VSB
    for pin, ref in (("1", "#PWR7101"), ("8", "#PWR7102")):
        blob.append(sc.wire_and_power(mux_pins, "U4", pin, UX, UY, "+5VSB", PROJECT, USB_PATH, ref))
    # IN2 (pin 2) -> VBUS (local; F1/FB1 already carry it upstream on this sheet)
    blob.append(sc.wire_and_label(mux_pins, "U4", "2", UX, UY, "VBUS"))
    # CP2 (3), OV2 (4) -> GND; GND (12) -> GND. ST (9, "Output" pin type) is left
    # a genuine no_connect rather than hard-grounded: the datasheet's own pin
    # table lumps ST in with the true CONTROL inputs ("connect to GND if not
    # required"), but ST is an open-drain STATUS OUTPUT, not an input -- tying
    # it to GND put a second driver ("Output") on the same net as the board's
    # existing GND PWR_FLAG ("Power output"), a real pin_to_pin ERROR (not the
    # usual benign warning class), where a true no_connect is the datasheet's
    # own alternative for an unused pin and exactly matches the hub's own
    # as-built U5/U7 precedent for this same pin. Flagged as a deviation from
    # the delta doc's literal "CP2, OV2, ST -> GND" text, not a silent one.
    for pin, ref in (("3", "#PWR7103"), ("4", "#PWR7104"), ("12", "#PWR7106")):
        blob.append(sc.wire_and_power(mux_pins, "U4", pin, UX, UY, "GND", PROJECT, USB_PATH, ref))
    blob.append(sc.noconnect_pin(mux_pins, "U4", "9", UX, UY))
    # OV1 (5) -> divider node; PR1 (6) -> divider node; IN1 (7) -> GLOBAL "VCC_RJ45"
    blob.append(sc.wire_and_label(mux_pins, "U4", "5", UX, UY, "U4_OV1"))
    blob.append(sc.wire_and_label(mux_pins, "U4", "6", UX, UY, "U4_PR1"))
    blob.append(sc.wire_and_global_label(mux_pins, "U4", "7", UX, UY, GLOBAL_VCC_RJ45))
    # ILIM (10) -> R14; SS (11) -> C42
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

    # ---------- 8. PWR_FLAG drivers -- U4.IN1/IN2 are power_in typed pins, and
    # ERC wants an Output Power pin driving whatever net they sit on. VBUS and
    # the new VCC_RJ45 (global) nets never had one before (their only prior
    # consumers were passive/diode pins), so stamp one on each, mirroring
    # cec_sch.build_schematic's own PWR_FLAG-stamp convention. ----------
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
        # this leaf file (unlike its pcie2/pcie3 siblings) carries no
        # sheet_instances trailer -- insert right before the file's own final
        # top-level closing paren instead.
        i0 = txt.index("(kicad_sch")
        end = cec_sch.carve(txt, i0)
        pos = i0 + len(end) - 1  # index of the final ')'
        txt = txt[:pos] + new_content + txt[pos:]
    open(USB_SCH, "w").write(txt)
    print(f"07-usb-flash.kicad_sch: wrote {len(blob)} new elements")

    # ---------- 8. 01-hub-link.kicad_sch: retarget FB2's rail-side stub ----------
    txt2 = open(HUBLINK_SCH).read()
    txt2, kind, info = sc.remove_terminal_at(txt2, 185.42, 113.03)
    assert kind == "power" and info[1] == "+5VSB", info
    blob2 = [cec_sch.emit_global_label(GLOBAL_VCC_RJ45, 185.42, 113.03, 180)]
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

    print("EPS USB-ingress splice complete.")
