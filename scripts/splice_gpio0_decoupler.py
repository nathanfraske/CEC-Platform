#!/usr/bin/env python3
# One-shot splice: add the GPIO0 (BOOT strapping pin) decoupler -- a 0.1uF cap
# GPIO0->GND + a 10k pull-up GPIO0->+3V3 -- to each beta sensing module's MCU
# sheet, matching the Hub (C8 + R11). Owner directive 2026-07-07. The modules
# already carry BOOT+RESET buttons and the EN reset RC; this adds the Espressif-
# recommended strapping-pin RC (debounce / noise immunity against spurious
# download-mode entry). Label-driven, per-sheet; idempotency-guarded.
import sys, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch

CAP_FP = "cec-Capacitor_SMD:C_0402_1005Metric"
RES_FP = "cec-Resistor_SMD:R_0402_1005Metric"
GRID = 1.27

MODS = [
    dict(file="beta/atx-24pin-rev3/24pin-module.kicad_sch", project="24pin-module",
         root="a4774022-41d4-4be7-85b6-fed5477a3f9f",
         cap="C61", res="R61", pwr0=930, cap_xy=(69.85, 300.99), res_xy=(78.74, 300.99)),
    dict(file="beta/eps-8pin-rev3/02-regulator-mcu.kicad_sch", project="eps-8pin-rev3",
         root="ef7f6c4c-2dd9-4559-b472-96b33604786a/26d53442-a9ff-5508-b459-d1a1a45026fa",
         cap="C41", res="R13", pwr0=720, cap_xy=(199.39, 110.49), res_xy=(209.55, 110.49)),
    dict(file="beta/pcie-8pin-2port/04-mcu.kicad_sch", project="pcie8pin-2port-module",
         root="a0c79a2e-4073-4d8d-b0bf-2c2ed1691f64/83ceb2d1-e50f-4838-831a-71136b7d1260",
         cap="C41", res="R13", pwr0=720, cap_xy=(199.39, 110.49), res_xy=(209.55, 110.49)),
    dict(file="beta/pcie-8pin-3port/04-mcu.kicad_sch", project="pcie8pin-3port-module",
         root="a8ecf94e-f41a-4523-8cf1-1d72f47f3e7e/83ceb2d1-e50f-4838-831a-71136b7d1260",
         cap="C41", res="R13", pwr0=720, cap_xy=(200.66, 110.49), res_xy=(210.82, 110.49)),
    dict(file="beta/12vhpwr-standard/05-mcu.kicad_sch", project="12vhpwr-standard-module",
         root="436b24cb-7227-4a56-93c7-4c5d9a5d0058/5e9d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a05",
         cap="C25", res="R24", pwr0=1120, cap_xy=(241.30, 113.03), res_xy=(251.46, 113.03)),
]

# C_Small / R_Small pin geometry is identical everywhere: pin1 top(0,2.54,270),
# pin2 bottom(0,-2.54,90).
def gsnap(v):
    return round(v / GRID) * GRID

def stub(ax, ay, ang, L=2.54):
    if ang == 270:   # top pin, outward up
        return gsnap(ax), gsnap(ay - L), 90
    if ang == 90:    # bottom pin, outward down
        return gsnap(ax), gsnap(ay + L), 270
    raise ValueError(ang)

for m in MODS:
    path = os.path.join(HERE, "..", m["file"])
    txt = open(path).read()
    if re.search(r'"' + re.escape(m["cap"]) + r'"', txt) or re.search(r'"' + re.escape(m["res"]) + r'"', txt):
        print(f"SKIP {m['file']}: {m['cap']}/{m['res']} already present")
        continue
    pwr = [m["pwr0"]]
    out = []

    def emit_part(ref, name, val, ox, oy, fp):
        s = cec_sch.emit_symbol(ref, "cec-vendor", name, val, ox, oy, ["1", "2"],
                                m["project"], m["root"], fp=fp)
        # compact ref/value text (default y-/+15.24 -> tight, avoids sprawl)
        s = s.replace(f'(at {cec_sch.f(ox)} {cec_sch.f(oy-15.24)} 0)',
                      f'(at {cec_sch.f(ox)} {cec_sch.f(oy-6.35)} 0)', 1)
        s = s.replace(f'(at {cec_sch.f(ox)} {cec_sch.f(oy+15.24)} 0)',
                      f'(at {cec_sch.f(ox)} {cec_sch.f(oy+6.35)} 0)', 1)
        out.append(s)

    def wire_pin(ox, oy, pin_top, net_or_power):
        # pin_top=True -> top pin (ang270), else bottom pin (ang90)
        ly, ang = (2.54, 270) if pin_top else (-2.54, 90)
        ax, ay = ox, oy - ly
        ex, ey, lang = stub(ax, ay, ang)
        out.append(cec_sch.emit_wire(ax, ay, ex, ey))
        if isinstance(net_or_power, tuple):
            ref = f"#PWR0{pwr[0]}"; pwr[0] += 1
            out.append(cec_sch.emit_global_power(net_or_power[1], ex, ey, m["project"], m["root"], ref))
        else:
            out.append(cec_sch.emit_label(net_or_power, ex, ey, lang))

    # cap: pin1(top)->GPIO0, pin2(bottom)->GND
    cx, cy = m["cap_xy"]
    emit_part(m["cap"], "C_Small", "100n", cx, cy, CAP_FP)
    wire_pin(cx, cy, True, "GPIO0")
    wire_pin(cx, cy, False, ("PWR", "GND"))
    # resistor: pin1(top)->+3V3, pin2(bottom)->GPIO0
    rx, ry = m["res_xy"]
    emit_part(m["res"], "R_Small", "10k", rx, ry, RES_FP)
    wire_pin(rx, ry, True, ("PWR", "+3V3"))
    wire_pin(rx, ry, False, "GPIO0")

    blob = "\n".join(out) + "\n"
    idx = txt.rindex("\t(sheet_instances")
    open(path, "w").write(txt[:idx] + blob + txt[idx:])
    print(f"{m['file']}: added {m['cap']} (100nF GPIO0->GND) + {m['res']} (10k +3V3->GPIO0)")
