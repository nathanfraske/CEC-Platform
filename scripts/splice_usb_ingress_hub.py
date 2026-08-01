#!/usr/bin/env python3
# One-shot splice: hub-standard-rev2 THIRD TPS2121 cascade stage -- KVM half of
# the USB-ingress package (spec v1.6.0 Sec 2.9; owner rulings 2026-07-24;
# docs/usb-ingress-bom-delta-2026-07-24.md Sec 3.5).
#
# The as-built hub already cascades two stages: U5 (5VSB x USB -> /PSU_5V) then
# U7 (MAIN_5V x /PSU_5V -> +5VSB). J_KVM pin 1 (the NanoKVM aux header's 5V
# line) was, before this splice, a RAW +5VSB power-symbol tap -- exactly the
# hazard spec Sec 2.9's v1.6.0 entry describes (a powered Hub could back-drive
# the NanoKVM's own USB port; a PC-USB-powered NanoKVM faced the Hub's whole
# 4700uF + module 5VSB tree with nothing in series). This splice adds U11 as a
# THIRD cascade stage, making KVM the lowest-priority input:
#   MAIN_5V (U7) > 5VSB/USB (U5, via U7.IN2) > wall-wart/KVM (U11, via U7.IN2
#   -- U11 replaces U5's direct feed into U7 with its own OR'd output).
#   - U11.IN1 (pin 7) = /PSU_5V (U5's EXISTING output net -- U11 just becomes
#     one more consumer of it; U5 itself is untouched).
#   - U11.IN2 (pin 2) = new /KVM_5V_IN, fed from J_KVM.pin1 through new
#     polyfuse F5 (defense layer 2, same pattern as every module's F1).
#   - U11.OUT (1,8) = new /PSU_5V_KVM, which REPLACES U7.pin2's (IN2) AND
#     U7.pin3's (CP2) existing "/PSU_5V" tie -- both pins share that net today
#     (U7's own as-built style hard-ties CP2 to IN2, verified live), so BOTH
#     move to "/PSU_5V_KVM" together, completing the NET MOVE the delta doc
#     specifies for U7.pin2 (a detail the doc's own text doesn't call out for
#     CP2, but leaving it on the old /PSU_5V net would just short U11's whole
#     OUT stage back onto U5's output around U7's own mux -- verified as the
#     as-built pattern, not silently invented).
#
# Strap style: per the doc, "mirror the as-built U5/U7 strap style" -- NOT the
# per-module package's strict datasheet-default posture. Verified live (both
# U5 and U7): CP2 hard-tied to IN2's own net, OV1/OV2 -> GND, PR1 hard-tied to
# IN1's own net, ST left a genuine no_connect (not GND-strapped). U11 mirrors
# this EXACTLY -- no OV1 divider is added here (that would be the per-module
# package's posture, not this board's own precedent, and the coordinator's
# mid-task request to add one to the EXISTING U5/U7 as well was declined as
# out of the actual work order -- see the final report).
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch  # noqa: E402
import splice_usb_ingress_common as sc  # noqa: E402

SCH = os.path.join(HERE, "..", "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")

PROJECT = "hub-standard-rev2"  # matches the most recent splice's own instance-name choice
ROOT_UUID = "aa22b2b4-0e2b-481a-a188-ee3f43fcbaa8"

BOM = {
    "U11": dict(Manufacturer="Texas Instruments", MPN="TPS2121RUXR", LCSC="C485916"),
    "F5": dict(Manufacturer="FUZETEC", MPN="FSMD110-16-1206R", LCSC="C5707763",
               Note="1.1A hold/2.2A trip/16V resettable PTC polyfuse, KVM 5V ingress "
                    "defense layer 2 (spec Sec 2.9 v1.6.0). F1-F4 are the 2026-07-15 "
                    "per-port 500mA PTCs -- unrelated position."),
    "R_ILIM3": dict(Manufacturer="UNI-ROYAL", MPN="0402WGF2702TCE", LCSC="C25771",
                     Note="U11 ILIM strap, mirrors R_ILIM1/R_ILIM2 (~3.8A) -- F5's own "
                          "1.1A hold is the tighter element toward the wall-wart."),
    "C_SS3": dict(Manufacturer="Samsung", MPN="CL10A225KO8NNNC", LCSC="C23630",
                   Note="U11 soft-start cap, mirrors C_SS1/C_SS2 (hub-proven ~10ms ramp)."),
    "C22": dict(Manufacturer="Samsung", MPN="CL05B104KO5NNNC", LCSC="C1525",
                Note="U11 IN2 (KVM 5V) bypass."),
    "C23": dict(Manufacturer="Samsung", MPN="CL21A106KAYNNNE", LCSC="C96446",
                Note="U11 IN2 (KVM 5V) bulk -- the hub's own 0603 10uF line."),
}

FP_R0402 = "cec-Resistor_SMD:R_0402_1005Metric"
FP_C0402 = "cec-Capacitor_SMD:C_0402_1005Metric"
FP_C0603 = "cec-Capacitor_SMD:C_0603_1608Metric"

if __name__ == "__main__":
    txt = open(SCH).read()
    if '(property "Reference" "U11"' in txt:
        raise SystemExit("REFUSE: U11 already present -- splice already applied?")

    r_pins = sc.get_pin_table(txt, "cec-vendor:R_Small")
    c_pins = sc.get_pin_table(txt, "cec-vendor:C_Small")
    mux_pins = sc.get_pin_table(txt, "cec-vendor:TPS2121RUXR")
    flag_pins = sc.get_pin_table(txt, "cec-power:PWR_FLAG")

    # ---------- 1. J_KVM.pin1 NET MOVE: +5VSB (raw tap) -> /KVM_5V_RAW (pre-fuse) ----------
    txt, kind1, info1 = sc.remove_terminal_at(txt, 347.98, 354.33)
    assert kind1 == "power" and info1[1] == "+5VSB", info1
    blob = [cec_sch.emit_label("KVM_5V_RAW", 347.98, 354.33, 180)]
    print("J_KVM.pin1: raw +5VSB tie", info1, "removed -> label KVM_5V_RAW")

    # ---------- 2. F5 (KVM polyfuse): KVM_5V_RAW -> F5 -> KVM_5V_IN ----------
    F5_X, F5_Y = sc.gsnap(655.0), sc.gsnap(40.0)
    blob.append(cec_sch.emit_symbol("F5", "cec-vendor", "R_Small", "1.1A/16V PTC", F5_X, F5_Y,
                                     sorted(r_pins.keys()), PROJECT, ROOT_UUID,
                                     fp="cec-Resistor_SMD:R_1206_3216Metric", props=BOM["F5"]))
    blob.append(sc.wire_and_label(r_pins, "F5", "1", F5_X, F5_Y, "KVM_5V_RAW"))
    blob.append(sc.wire_and_label(r_pins, "F5", "2", F5_X, F5_Y, "KVM_5V_IN"))

    # ---------- 3. U7.pin2 (IN2) AND U7.pin3 (CP2) NET MOVE: /PSU_5V -> /PSU_5V_KVM
    # (both pins share the as-built "/PSU_5V" label today -- U7.CP2 is hard-tied
    # to U7.IN2's own net, the as-built style; verified live, both are plain
    # (label "PSU_5V" ...) instances at their own distinct coordinates). ----------
    txt, old2, tag2 = sc.rename_label_at(txt, 97.79, 377.19, "PSU_5V_KVM")
    assert old2 == "PSU_5V" and tag2 == "label", (old2, tag2)
    txt, old3, tag3 = sc.rename_label_at(txt, 97.79, 372.11, "PSU_5V_KVM")
    assert old3 == "PSU_5V" and tag3 == "label", (old3, tag3)
    print("U7.pin2/pin3: /PSU_5V ties renamed -> /PSU_5V_KVM (both)")

    # ---------- 4. place U11 + straps, mirroring the as-built U5/U7 style ----------
    UX, UY = sc.gsnap(680.0), sc.gsnap(60.0)
    blob.append(cec_sch.emit_symbol("U11", "cec-vendor", "TPS2121RUXR", "TPS2121RUXR",
                                     UX, UY, sorted(mux_pins.keys()), PROJECT, ROOT_UUID,
                                     fp="cec-Package_DFN_QFN:RUX0012A", props=BOM["U11"]))
    # OUT (1,8) -> PSU_5V_KVM (joins U7.pin2/pin3 by name)
    blob.append(sc.wire_and_label(mux_pins, "U11", "1", UX, UY, "PSU_5V_KVM"))
    blob.append(sc.wire_and_label(mux_pins, "U11", "8", UX, UY, "PSU_5V_KVM"))
    # IN2 (2) -> KVM_5V_IN (post-F5); CP2 (3) -> hard-tied to IN2's own net too
    # (as-built U5/U7 style: CP2 mirrors IN2, not GND)
    blob.append(sc.wire_and_label(mux_pins, "U11", "2", UX, UY, "KVM_5V_IN"))
    blob.append(sc.wire_and_label(mux_pins, "U11", "3", UX, UY, "KVM_5V_IN"))
    # OV2 (4) -> GND; OV1 (5) -> GND (as-built style: both grounded, no divider)
    for pin, ref in (("4", "#PWR9201"), ("5", "#PWR9202")):
        blob.append(sc.wire_and_power(mux_pins, "U11", pin, UX, UY, "GND", PROJECT, ROOT_UUID, ref))
    # PR1 (6) -> hard-tied to IN1's own net (as-built style: mirrors IN1, not a divider)
    blob.append(sc.wire_and_label(mux_pins, "U11", "6", UX, UY, "PSU_5V"))
    # IN1 (7) -> PSU_5V (U5's existing OUT net, unchanged, one more consumer)
    blob.append(sc.wire_and_label(mux_pins, "U11", "7", UX, UY, "PSU_5V"))
    # ST (9) -> genuine no_connect (matches U5/U7's own as-built treatment)
    blob.append(sc.noconnect_pin(mux_pins, "U11", "9", UX, UY))
    # ILIM (10) -> R_ILIM3; SS (11) -> C_SS3; GND (12) -> GND
    blob.append(sc.wire_and_label(mux_pins, "U11", "10", UX, UY, "U11_ILM"))
    blob.append(sc.wire_and_label(mux_pins, "U11", "11", UX, UY, "U11_SS"))
    blob.append(sc.wire_and_power(mux_pins, "U11", "12", UX, UY, "GND", PROJECT, ROOT_UUID, "#PWR9203"))

    # ---------- 5. R_ILIM3 (27k, mirrors R_ILIM1/R_ILIM2) ----------
    RX, RY = sc.gsnap(710.0), sc.gsnap(50.0)
    blob.append(cec_sch.emit_symbol("R_ILIM3", "cec-vendor", "R_Small", "27kΩ", RX, RY,
                                     sorted(r_pins.keys()), PROJECT, ROOT_UUID, fp=FP_R0402, props=BOM["R_ILIM3"]))
    blob.append(sc.wire_and_label(r_pins, "R_ILIM3", "1", RX, RY, "U11_ILM"))
    blob.append(sc.wire_and_power(r_pins, "R_ILIM3", "2", RX, RY, "GND", PROJECT, ROOT_UUID, "#PWR9204"))

    # ---------- 6. C_SS3 (2.2uF, mirrors C_SS1/C_SS2) ----------
    CSX, CSY = sc.gsnap(710.0), sc.gsnap(65.0)
    blob.append(cec_sch.emit_symbol("C_SS3", "cec-vendor", "C_Small", "2.2uF", CSX, CSY,
                                     sorted(c_pins.keys()), PROJECT, ROOT_UUID, fp=FP_C0603, props=BOM["C_SS3"]))
    blob.append(sc.wire_and_power(c_pins, "C_SS3", "1", CSX, CSY, "GND", PROJECT, ROOT_UUID, "#PWR9205"))
    blob.append(sc.wire_and_label(c_pins, "C_SS3", "2", CSX, CSY, "U11_SS"))

    # ---------- 7. C22 (IN2 bypass 100nF), C23 (IN2 bulk 10uF, hub's own 0603 line) ----------
    CX, CY1, CY2 = sc.gsnap(655.0), sc.gsnap(80.0), sc.gsnap(95.0)
    blob.append(cec_sch.emit_symbol("C22", "cec-vendor", "C_Small", "100nF", CX, CY1,
                                     sorted(c_pins.keys()), PROJECT, ROOT_UUID, fp=FP_C0402, props=BOM["C22"]))
    blob.append(sc.wire_and_label(c_pins, "C22", "1", CX, CY1, "KVM_5V_IN"))
    blob.append(sc.wire_and_power(c_pins, "C22", "2", CX, CY1, "GND", PROJECT, ROOT_UUID, "#PWR9206"))
    blob.append(cec_sch.emit_symbol("C23", "cec-vendor", "C_Small", "10uF", CX, CY2,
                                     sorted(c_pins.keys()), PROJECT, ROOT_UUID, fp=FP_C0603, props=BOM["C23"]))
    blob.append(sc.wire_and_label(c_pins, "C23", "1", CX, CY2, "KVM_5V_IN"))
    blob.append(sc.wire_and_power(c_pins, "C23", "2", CX, CY2, "GND", PROJECT, ROOT_UUID, "#PWR9207"))

    # ---------- 8. PWR_FLAG drivers for /PSU_5V_KVM and /KVM_5V_IN -- both are
    # power_in-only nets now (U11's OUT pins are themselves "power_in" typed
    # on this symbol, same as every other board's mux; U7.pin2/U11.pin2 add no
    # driver either) -- measured via ERC (power_pin_not_driven on U7.Pin2 and
    # U11.Pin2), fixed the same way as every module board in this package. ----------
    FX1, FY1 = sc.gsnap(680.0), sc.gsnap(110.0)
    blob.append(cec_sch.emit_symbol("#FLG9208", "cec-power", "PWR_FLAG", "PWR_FLAG", FX1, FY1,
                                     sorted(flag_pins.keys()), PROJECT, ROOT_UUID, fp=""))
    blob.append(sc.wire_and_label(flag_pins, "#FLG9208", "1", FX1, FY1, "PSU_5V_KVM"))
    FX2, FY2 = sc.gsnap(655.0), sc.gsnap(110.0)
    blob.append(cec_sch.emit_symbol("#FLG9209", "cec-power", "PWR_FLAG", "PWR_FLAG", FX2, FY2,
                                     sorted(flag_pins.keys()), PROJECT, ROOT_UUID, fp=""))
    blob.append(sc.wire_and_label(flag_pins, "#FLG9209", "1", FX2, FY2, "KVM_5V_IN"))

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
    print(f"hub-standard-rev2.kicad_sch: wrote {len(blob)} new elements")
    print("Hub KVM third-cascade-stage splice complete.")
