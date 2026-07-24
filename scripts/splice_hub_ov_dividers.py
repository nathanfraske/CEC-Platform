#!/usr/bin/env python3
# One-shot splice: hub-standard-rev2 OV1 dividers on EVERY TPS2121 stage (U5,
# U7, and the new U11 KVM stage), per the owner ruling landed 2026-07-24 in
# docs/owner-queue.md (commit 8c8ca46f, "Finding 3 SIGNED OFF: hub OV dividers
# on every TPS2121 stage (U5/U7 + the new KVM stage), same 47k/10k ~6.04V
# posture as the module package -- LUMPED into the running schematic pass"),
# reinforced by the SPICE follow-up (commit 9c6083ae /
# docs/spice-backfeed-verify-2026-07-24.md marginal (F): the TPS2121's OV
# response time is UNDOCUMENTED and a real 0.8-7.4us over-6.5V-abs-max
# excursion on the LP5907 was measured under a fast cross-rail fault -- an
# OV1 pin hard-grounded (the as-built state on all three stages, verified
# below) gives that protection path NOTHING to trigger on, so having a real,
# correctly-tuned divider on every stage is the mitigation, not optional.
#
# Verified live before writing (per the instruction: confirm each stage's OV1
# pin isn't committed to a conflicting function first) -- all three are
# genuinely simple GND power-symbol ties today, nothing else on that node:
#   U5.pin5  (OV1) -> GND, at (424.18, 105.41)
#   U7.pin5  (OV1) -> GND, at (140.97, 361.95)
#   U11.pin5 (OV1) -> GND, at (701.04, 52.07)   (my own build -- mirrored the
#     as-built U5/U7 hard-GND style per the delta doc's ORIGINAL instruction,
#     which predates this ruling; now brought into line with it)
# None are a conflict -- each converts cleanly from a bare GND tie to a real
# divider tapping that STAGE'S OWN IN1 net (the same "OV1 divider off IN1"
# posture used on every module's own mux, spec Sec 6.14):
#   U5:  IN1 = /5VSB_RAW   -> R33 (47k) / R34 (10k)
#   U7:  IN1 = /MAIN_5V_RAW -> R35 (47k) / R36 (10k)
#   U11: IN1 = /PSU_5V     -> R37 (47k) / R38 (10k)
# All three IN1 nets are plain same-sheet LOCAL LABELS on this flat board
# (verified: 0 power-symbol instances for any of the three names), so the
# divider top ties via a plain label, same mechanism as everything else.
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch  # noqa: E402
import splice_usb_ingress_common as sc  # noqa: E402

SCH = os.path.join(HERE, "..", "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")
PROJECT = "hub-standard-rev2"
ROOT_UUID = "aa22b2b4-0e2b-481a-a188-ee3f43fcbaa8"

FP_R0402 = "cec-Resistor_SMD:R_0402_1005Metric"

STAGES = [
    # (mux_ref, ov1_stub_xy, in1_net, div_net, top_ref, bot_ref, top_flag_ref, bot_gnd_ref)
    ("U5", (424.18, 105.41), "5VSB_RAW", "U5_OV1", "R33", "R34", "#PWR9210", "#PWR9211"),
    ("U7", (140.97, 361.95), "MAIN_5V_RAW", "U7_OV1", "R35", "R36", "#PWR9212", "#PWR9213"),
    ("U11", (701.04, 52.07), "PSU_5V", "U11_OV1", "R37", "R38", "#PWR9214", "#PWR9215"),
]

PLACEMENT = {
    "R33": (660.0, 150.0), "R34": (660.0, 165.0),
    "R35": (700.0, 150.0), "R36": (700.0, 165.0),
    "R37": (740.0, 150.0), "R38": (740.0, 165.0),
}

if __name__ == "__main__":
    txt = open(SCH).read()
    if '(property "Reference" "R33"' in txt:
        raise SystemExit("REFUSE: R33 already present -- splice already applied?")

    r_pins = sc.get_pin_table(txt, "cec-vendor:R_Small")
    blob = []

    for mux_ref, (sx, sy), in1_net, div_net, top_ref, bot_ref, top_pwr, bot_pwr in STAGES:
        txt, kind, info = sc.remove_terminal_at(txt, sx, sy)
        assert kind == "power" and info[1] == "GND", (mux_ref, kind, info)
        # pin5 (OV1) is defined at local angle 180 on the shared symbol, and
        # all three mux instances sit at placement rotation 0, so the true
        # outward direction is IDENTICAL for all three (dx>0 -> label angle 0)
        blob.append(cec_sch.emit_label(div_net, sx, sy, 0))
        print(f"{mux_ref}.OV1: GND tie ({info[0]}) removed -> label {div_net!r}, "
              f"divider will tap {in1_net!r}")

        tx, ty = sc.gsnap(PLACEMENT[top_ref][0]), sc.gsnap(PLACEMENT[top_ref][1])
        bx_, by_ = sc.gsnap(PLACEMENT[bot_ref][0]), sc.gsnap(PLACEMENT[bot_ref][1])
        blob.append(cec_sch.emit_symbol(
            top_ref, "cec-vendor", "R_Small", "47kΩ", tx, ty, sorted(r_pins.keys()),
            PROJECT, ROOT_UUID, fp=FP_R0402,
            props=dict(Manufacturer="UNI-ROYAL", MPN="0402WGF4702TCE", LCSC="C25792",
                       Note=f"{mux_ref} OV1 divider top ({in1_net} side) -- owner ruling "
                            f"2026-07-24, docs/owner-queue.md commit 8c8ca46f (Finding 3): "
                            f"same 47k/10k ~6.04V posture as the module package, on every "
                            f"hub TPS2121 stage.")))
        blob.append(sc.wire_and_label(r_pins, top_ref, "1", tx, ty, in1_net))
        blob.append(sc.wire_and_label(r_pins, top_ref, "2", tx, ty, div_net))

        blob.append(cec_sch.emit_symbol(
            bot_ref, "cec-vendor", "R_Small", "10kΩ", bx_, by_, sorted(r_pins.keys()),
            PROJECT, ROOT_UUID, fp=FP_R0402,
            props=dict(Manufacturer="UNI-ROYAL", MPN="0402WGF1002TCE", LCSC="C25744",
                       Note=f"{mux_ref} OV1 divider bottom (GND side) -> ~6.04V typical "
                            f"cutoff -- same owner ruling as {top_ref}.")))
        blob.append(sc.wire_and_label(r_pins, bot_ref, "1", bx_, by_, div_net))
        blob.append(sc.wire_and_power(r_pins, bot_ref, "2", bx_, by_, "GND", PROJECT, ROOT_UUID, bot_pwr))

    new_content = "\n".join(blob) + "\n"
    idx = txt.rindex("\t(sheet_instances")
    txt = txt[:idx] + new_content + txt[idx:]
    open(SCH, "w").write(txt)
    print(f"hub-standard-rev2.kicad_sch: wrote {len(blob)} new elements (3 OV1 dividers)")
    print("Hub OV1-divider splice complete.")
