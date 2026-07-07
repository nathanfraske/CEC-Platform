#!/usr/bin/env python3
# One-shot splice: add INA181A2 + TLV7011 fast-detection cells on the 24-pin's
# 3V3 and 5VSB rails, so all four rails carry the §6.13-style detection front end
# (owner 2026-07-07: "add the INA181 + comparator to the two remaining rails ...
# we are a total monitor anyway"). Mirrors the existing 12V/5V cells exactly
# (INA181A2 amp taps the same shunt Kelvin pair -> TLV7011 comparator vs the
# board-shared /THRESH -> a free MCU GPIO). Label-driven, like the flat sheet.
# Idempotent-guarded: refuses to run if the new refs already exist.
import sys, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch

SCH = os.path.join(HERE, "..", "modules", "atx-24pin-rev3", "24pin-module.kicad_sch")
PROJECT = "24pin-module"
ROOT = "a4774022-41d4-4be7-85b6-fed5477a3f9f"
GRID = 1.27

txt = open(SCH).read()

# ---- IC pin local geometry, carved from the file's own lib_symbols cache ----
def carve(t, i):
    d = 0
    for j in range(i, len(t)):
        if t[j] == '(':
            d += 1
        elif t[j] == ')':
            d -= 1
            if d == 0:
                return t[i:j+1]
    return None

def pins_of(libname):
    m = re.search(r'\(symbol "' + re.escape(libname) + r'"', txt)
    return cec_sch.pin_table(carve(txt, m.start()))

PIN = {
    "INA181": pins_of("cec-vendor:INA181A2IDBVR"),
    "TLV":    pins_of("cec-vendor:TLV7011DBVR"),
    "C":      pins_of("cec-vendor:C_Small"),
    "MCU":    pins_of("cec-vendor:ESP32-C6-MINI-1-N4"),
}

# ---- refs / placement ----
# Two cells, continuing the amp(x=294.64)/comp(x=364.49) column below the 5V cell.
CELLS = [
    dict(rail="3V3",  y=142.24, amp="U63V31",  comp="U73V31",  cap="C63V31",
         hi="SENSE3V3_HI",  lo="SENSE3V3_LO",  detamp="DETAMP3V3",  det="DET3V3",  mcu_pin="15"),
    dict(rail="5VSB", y=161.29, amp="U65VSB1", comp="U75VSB1", cap="C65VSB1",
         hi="SENSE5VSB_HI", lo="SENSE5VSB_LO", detamp="DETAMP5VSB", det="DET5VSB", mcu_pin="16"),
]
AMP_X, COMP_X, CAP_X = 294.64, 364.49, 323.85
FP_INA = "cec-Package_TO_SOT_SMD:SOT-23-6"
FP_TLV = "cec-Package_TO_SOT_SMD:SOT-23-5"
FP_C   = "cec-Capacitor_SMD:C_0402_1005Metric"

# idempotency guard
for c in CELLS:
    for r in (c["amp"], c["comp"], c["cap"]):
        if re.search(r'"' + re.escape(r) + r'"', txt):
            raise SystemExit(f"REFUSE: {r} already present -- splice already applied?")

pwr_n = [910]  # next #PWR number (max in file = 905)

def gsnap(v):
    return round(v / GRID) * GRID

def stub_and_target(ax, ay, ang, L=2.54):
    """Stub from a pin's abs connection point outward; return (endx,endy,labelang)."""
    if ang == 0:      # pin body extends +x, connection point on left -> outward -x
        return gsnap(ax - L), gsnap(ay), 180
    if ang == 180:    # outward +x
        return gsnap(ax + L), gsnap(ay), 0
    if ang == 270:    # cap top pin -> outward -y (up)
        return gsnap(ax), gsnap(ay - L), 90
    if ang == 90:     # cap bottom pin -> outward +y (down)
        return gsnap(ax), gsnap(ay + L), 270
    raise ValueError(ang)

out = []

def emit_ic(ref, lib, name, val, ox, oy, fp):
    """emit_symbol with COMPACT ref/value text (match the hand cells: ~above the part)."""
    s = cec_sch.emit_symbol(ref, lib, name, val, ox, oy, list(PIN_KEYS[name]),
                            PROJECT, ROOT, fp=fp)
    # relocate Reference (default y-15.24 -> y-10.16) and Value (y+15.24 -> y-7.62)
    s = s.replace(f'(at {cec_sch.f(ox)} {cec_sch.f(oy-15.24)} 0)',
                  f'(at {cec_sch.f(ox)} {cec_sch.f(oy-10.16)} 0)', 1)
    s = s.replace(f'(at {cec_sch.f(ox)} {cec_sch.f(oy+15.24)} 0)',
                  f'(at {cec_sch.f(ox)} {cec_sch.f(oy-7.62)} 0)', 1)
    out.append(s)

PIN_KEYS = {"INA181A2IDBVR": ["1","2","3","4","5","6"],
            "TLV7011DBVR":   ["1","2","3","4","5"],
            "C_Small":       ["1","2"]}

def wire_pin(part_pins, ref_placement_xy, pinnum, net_or_power):
    """Emit stub wire + a label (str net) or power symbol (('PWR', symname))."""
    ox, oy = ref_placement_xy
    lx, ly, ang, _len = part_pins[pinnum]
    ax, ay = ox + lx, oy - ly
    ex, ey, lang = stub_and_target(ax, ay, ang)
    out.append(cec_sch.emit_wire(ax, ay, ex, ey))
    if isinstance(net_or_power, tuple):
        _, symname = net_or_power
        ref = f"#PWR0{pwr_n[0]}"; pwr_n[0] += 1
        out.append(cec_sch.emit_global_power(symname, ex, ey, PROJECT, ROOT, ref))
    else:
        out.append(cec_sch.emit_label(net_or_power, ex, ey, lang))

for c in CELLS:
    y = c["y"]
    # --- INA181 amp ---
    emit_ic(c["amp"], "cec-vendor", "INA181A2IDBVR", "INA181A2IDBVR", AMP_X, y, FP_INA)
    ap = (AMP_X, y)
    wire_pin(PIN["INA181"], ap, "1", c["detamp"])          # OUT
    wire_pin(PIN["INA181"], ap, "2", ("PWR", "GND"))       # GND
    wire_pin(PIN["INA181"], ap, "3", c["hi"])              # IN+  shunt HI
    wire_pin(PIN["INA181"], ap, "4", c["lo"])              # IN-  shunt LO (Kelvin)
    wire_pin(PIN["INA181"], ap, "5", ("PWR", "GND"))       # REF -> GND (unidir)
    wire_pin(PIN["INA181"], ap, "6", ("PWR", "+3V3"))      # VS
    # --- bypass cap ---
    emit_ic(c["cap"], "cec-vendor", "C_Small", "100n", CAP_X, y, FP_C)
    cp = (CAP_X, y)
    wire_pin(PIN["C"], cp, "1", ("PWR", "+3V3"))
    wire_pin(PIN["C"], cp, "2", ("PWR", "GND"))
    # --- TLV7011 comparator ---
    emit_ic(c["comp"], "cec-vendor", "TLV7011DBVR", "TLV7011DBVR", COMP_X, y, FP_TLV)
    tp = (COMP_X, y)
    wire_pin(PIN["TLV"], tp, "1", c["det"])                # OUT -> MCU GPIO
    wire_pin(PIN["TLV"], tp, "2", ("PWR", "GND"))          # GND
    wire_pin(PIN["TLV"], tp, "3", c["detamp"])             # IN+ = amp OUT
    wire_pin(PIN["TLV"], tp, "4", "THRESH")                # IN- = shared threshold
    wire_pin(PIN["TLV"], tp, "5", ("PWR", "+3V3"))         # VCC

# --- MCU DET stubs (U1 at 275.59,204.47 rot0) ---
MCU_XY = (275.59, 204.47)
for c in CELLS:
    lx, ly, ang, _l = PIN["MCU"][c["mcu_pin"]]
    ax, ay = MCU_XY[0] + lx, MCU_XY[1] - ly
    ex, ey, lang = stub_and_target(ax, ay, ang)
    out.append(cec_sch.emit_wire(ax, ay, ex, ey))
    out.append(cec_sch.emit_label(c["det"], ex, ey, lang))

blob = "\n".join(out) + "\n"
# splice before the final (sheet_instances ...)
idx = txt.rindex("\t(sheet_instances")
new = txt[:idx] + blob + txt[idx:]
open(SCH, "w").write(new)
print(f"spliced {len(out)} s-expr elements; file {len(txt)} -> {len(new)} bytes")
