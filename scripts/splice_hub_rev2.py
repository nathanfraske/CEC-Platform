#!/usr/bin/env python3
# One-shot revision splice: hub-standard-rev2 (owner directive 2026-07-15, "get the
# Hub down properly ... new PCB revision specifically"):
#   (a) LED ring RETIRED: DL1-DL5 + DL7 deleted; DL6 survives as the ONE status LED
#       (owner: "DL6 excluded, to be placed wherever as a status LED"); the chain
#       rewires U6 -> R14 -> /LED_DATA_DIN -> DL6.DIN, DL6.DOUT -> NC. The CEC logo
#       + test points are PCB-only items and simply are not carried to the new board.
#   (b) J6 mezzanine added (CEC_MEZZANINE_16P on PinHeader_2x08_P2.00mm_Vertical,
#       THT, DNP -- owner decides facing at assembly). Pin map = COLUMN-PAIRED
#       (each signal on BOTH rows of one column: 5V/5V/GND/CANH/CANL/DET/GND/GND),
#       which is FLIP-INVARIANT about the header's long axis -- the sandwich stack
#       (Hub upside-down onto the 24-pin, components between the boards) works with
#       the SAME wiring as the normal stack. REQUIRES the 24-pin rev3's J6 to move
#       to the conjugate map (schematic-only there, layout unstarted) -- owner-queue.
#   (c) Everything already spliced into the beta schematic (U8 comparator block,
#       DNP hold-up ladder, J_PWR 3-pin) rides along unchanged.
# Idempotent-guarded; ERC + netlist-diff verified by the runner.
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch

SCH = os.path.join(HERE, "..", "hubs", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")
PROJECT = "hub-standard-rev2"

txt = open(SCH).read()
ROOT = re.search(r'\(uuid "([0-9a-f-]{36})"\)', txt).group(1)

if re.search(r'\(property "Reference" "J6"', txt):
    raise SystemExit("REFUSE: J6 already present -- splice already applied?")


def carve(t, i):
    d = 0
    for j in range(i, len(t)):
        if t[j] == '(':
            d += 1
        elif t[j] == ')':
            d -= 1
            if d == 0:
                return t[i:j + 1]


def remove_symbol(t, ref):
    m = re.search(r'\(property "Reference" "' + re.escape(ref) + '"', t)
    if not m:
        raise SystemExit(f"REFUSE: {ref} not found")
    i = t.rindex("\t(symbol\n", 0, m.start())
    blk = carve(t, i)
    return t.replace(blk, "", 1)


# ---------- (a) retire DL1-DL5, DL7 ----------
for ref in ("DL1", "DL2", "DL3", "DL4", "DL5", "DL7"):
    txt = remove_symbol(txt, ref)

# The chain labels: /LED_DATA_DIN fed DL1.DIN; DL5.DOUT fed DL6.DIN via the local
# net Net-(DL5-DOUT). With the ring gone, DL6's DIN must carry /LED_DATA_DIN.
# DL6 pin geometry: find its instance, then relabel by adding a wire+label at its
# DIN pin and a no-connect at DOUT. Simplest robust approach on this hand file:
# the chain connectivity is by WIRES between adjacent LEDs (netlist shows local
# Net-(DLx-DOUT) names = wired, not labeled). Removing DL1-5/DL7 leaves dangling
# wires; rather than surgically tracing wires, relabel DL6's pins directly:
m = re.search(r'\(property "Reference" "DL6"', txt)
i = txt.rindex("\t(symbol\n", 0, m.start())
blk = carve(txt, i)
at = re.search(r'\(at ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)\)', blk)
dx, dy, drot = float(at.group(1)), float(at.group(2)), float(at.group(3))

# SK6812 MINI symbol pin table from the file's own lib cache
msym = re.search(r'\(symbol "cec-vendor:SK6812MINI"', txt) or \
       re.search(r'\(symbol "[^"]*SK6812[^"]*"', txt)
pins = cec_sch.pin_table(carve(txt, msym.start()))
# pins: 1=DOUT, 2=GND(?), 3=DIN, 4=VDD per the netlist read (DL6: 4=+5VSB, 2=GND,
# 3=DIN-chain, 1=DOUT-chain)


def pin_abs(pnum):
    lx, ly, ang, _l = pins[pnum]
    import math
    r = math.radians(drot)
    # KiCad symbol rotation: (lx,ly) rotates by rot, y-flip convention as in cec_sch
    if drot == 0:
        return dx + lx, dy - ly, ang
    if drot == 90:
        return dx + ly, dy + lx, (ang + 90) % 360
    if drot == 180:
        return dx - lx, dy + ly, (ang + 180) % 360
    return dx - ly, dy - lx, (ang + 270) % 360


out = []
GRID = 1.27


def gsnap(v):
    return round(v / GRID) * GRID


# DIN (pin 3): wire stub + /LED_DATA_DIN label
ax, ay, ang = pin_abs("3")
ex, ey = gsnap(ax - 2.54 if ang == 0 else ax + 2.54), gsnap(ay)
out.append(cec_sch.emit_wire(ax, ay, ex, ey))
out.append(cec_sch.emit_label("LED_DATA_DIN", ex, ey, 180 if ang == 0 else 0))
# DOUT (pin 1): no-connect
bx, by, _ = pin_abs("1")
out.append(cec_sch.emit_noconnect(bx, by))

# Cull now-dangling ring WIRES: every wire whose BOTH endpoints fall inside the
# removed LEDs' bounding region would be guesswork on a hand file -- instead rely
# on ERC to surface dangling wires; the readability pass owns cosmetics. But the
# DANGLING ELECTRICAL risk (a wire end touching something else) is nil here: the
# ring wires connect only removed-LED pin positions. Deliberately left; DRAFT
# board, ERC-checked below by the runner.

# ---------- (b) J6 mezzanine, column-paired flip-invariant map ----------
# Symbol: cec:CEC_MEZZANINE_16P (numbered 1..16, odd=row A / even=row B per column).
MEZZ = "CEC_MEZZANINE_16P"
libtxt = open(os.path.join(HERE, "..", "lib", "cec.kicad_sym")).read()
if f'(symbol "cec:{MEZZ}"' not in txt:
    blk2 = cec_sch.symbol_block(libtxt, MEZZ)
    nb = cec_sch.reindent(cec_sch._namespace(blk2, MEZZ, "cec"), 2)
    i = txt.index("\t(lib_symbols")
    lib_blk = carve(txt, i)
    txt = txt.replace(lib_blk, lib_blk[:-2].rstrip() + "\n" + nb + "\n\t)", 1)

mzpins = cec_sch.pin_table(carve(txt, re.search(r'\(symbol "cec:%s"' % MEZZ, txt).start()))
# Column-paired map: col c = pins (2c-1, 2c) carry the SAME net.
COLMAP = {1: "+5VSB", 2: "+5VSB", 3: "GND", 4: "CAN_H",
          5: "CAN_L", 6: "DETECT1", 7: "GND", 8: "GND"}
MX, MY = 355.6, 264.16  # free sheet region (measured clear: x320-420 y230-300 empty)
props = {"MPN": "PinHeader 2x08 2.00mm THT (generic)", "LCSC": "",
         "Manufacturer": "generic",
         "Note": ("MEZZANINE (OQ-77) Hub side, owner directive 2026-07-15: THT + "
                  "DNP -- facing chosen at assembly (up = normal stack, down = the "
                  "SANDWICH: Hub flipped onto the 24-pin, components between "
                  "boards). Pin map is COLUMN-PAIRED (both rows of a column carry "
                  "one signal: 5V|5V|GND|CANH|CANL|DETECT1|GND|GND) = flip-"
                  "invariant about the header long axis, so BOTH facings mate "
                  "correctly -- CONTRACT: the 24-pin rev3 J6 must move to the "
                  "conjugate column-paired map (owner-queue row, its layout is "
                  "unstarted). +5V pins tie to the +5VSB rail: the 24-pin feeds "
                  "PRE-MUXED +5V_SYS; the Hub's own TPS2121s block reverse.")}
sym = cec_sch.emit_symbol("J6", "cec", MEZZ, "TO-24PIN-STACK", MX, MY,
                          sorted(mzpins, key=lambda p: int(p)), PROJECT, ROOT,
                          fp="cec-Connector_PinHeader_2.00mm:PinHeader_2x08_P2.00mm_Vertical",
                          props=props)
# mark DNP + exclude from pos/bom-fab (keep in bom listing as DNP)
sym = sym.replace("(dnp no)", "(dnp yes)", 1)
out.append(sym)
pwr_n = [1100]
for pnum in sorted(mzpins, key=lambda p: int(p)):
    n = int(pnum)
    col = (n + 1) // 2
    net = COLMAP[col]
    lx, ly, ang, _l = mzpins[pnum]
    ax2, ay2 = MX + lx, MY - ly
    if ang == 0:
        ex2, ey2, lang = gsnap(ax2 - 2.54), gsnap(ay2), 180
    else:
        ex2, ey2, lang = gsnap(ax2 + 2.54), gsnap(ay2), 0
    out.append(cec_sch.emit_wire(ax2, ay2, ex2, ey2))
    if net in ("GND", "+5VSB"):
        ref = f"#PWR0{pwr_n[0]}"; pwr_n[0] += 1
        out.append(cec_sch.emit_global_power(net if net != "GND" else "GND",
                                             ex2, ey2, PROJECT, ROOT, ref))
    else:
        out.append(cec_sch.emit_label(net, ex2, ey2, lang))

blob = "\n".join(out) + "\n"
idx = txt.rindex("\t(sheet_instances")
txt = txt[:idx] + blob + txt[idx:]
open(SCH, "w").write(txt)
print(f"hub-rev2 splice: ring retired (6 LEDs), DL6 relabeled, J6 mezz added "
      f"({len(out)} elements)")
