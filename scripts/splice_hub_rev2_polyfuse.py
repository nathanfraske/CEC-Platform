#!/usr/bin/env python3
# One-shot splice: per-port RJ45-VCC polyfuses on hub-standard-rev2 (owner ruling
# 2026-07-15, "per-port RJ45-VCC polyfuses"):
#   Today each RJ-45 jack's pin 1 (VCC) ties directly to +5VSB. Insert one
#   polyfuse in series per port:
#     +5VSB -- F1 -- /VCC_P1 -- J2 pin 1
#     +5VSB -- F2 -- /VCC_P2 -- J3 pin 1
#     +5VSB -- F3 -- /VCC_P3 -- J4 pin 1
#     +5VSB -- F4 -- /VCC_P4 -- J5 pin 1
#   Rationale (Note prop on each F): fault isolation -- a shorted patch cable or
#   failed module trips ONE port instead of browning out the shared 5VSB system;
#   the TPS2121 limit is total, not per-port. ~150mV drop at load absorbed by
#   module LDO headroom.
# Part: LCSC C46640983, MPN SMD0805-050-6 (0805 PTC resettable fuse, 500mA hold,
# 6V rated -- meets the >=6V floor), generic/JLC catalog, stock 47440 (2026-07-15
# jlcsearch.tscircuit.com query). Symbol cec-vendor:R_Small (2-pin passive, already
# in this file's lib_symbols); footprint cec-Resistor_SMD:R_0805_2012Metric.
#
# Surgery: each RJ-45 jack's pin-1 stub wire already runs from the pin to a short
# stub end where a +5VSB power-symbol instance sits (found by direct coordinate
# lookup, not by #PWR numbering -- the file's #PWR refs are not reliably ordered
# per-connector). DELETE that power-symbol instance and put a LABEL /VCC_Pn at the
# same stub-end point instead (the stub wire itself is untouched). Then place
# F1..F4 in the measured-EMPTY region x440-520 / y230-300, each wired pin1 ->
# label /VCC_Pn, pin2 -> global power +5VSB (per the brief's explicit pin
# assignment).
#
# Idempotent-guarded; ERC + netlist-diff verified by the runner (see
# build/polyfuse-splice-verification.txt).
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch

SCH = os.path.join(HERE, "..", "hubs", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")
PROJECT = "hub-standard-rev2"     # matches the most recent splice's (project "hub-standard-rev2" ...)
                                   # instances (J6/etc.); the file's OLDER parts still carry the
                                   # pre-fork "hub-standard" instance name, which KiCad tolerates
                                   # (verified: that mismatch already exists and ERC/netlist are clean)
GRID = 1.27

txt = open(SCH).read()
ROOT = re.search(r'\(uuid "([0-9a-f-]{36})"\)', txt).group(1)

if re.search(r'\(property "Reference" "F1"', txt):
    raise SystemExit("REFUSE: F1 already present -- splice already applied?")


def carve(t, i):
    d = 0
    for j in range(i, len(t)):
        if t[j] == '(':
            d += 1
        elif t[j] == ')':
            d -= 1
            if d == 0:
                return t[i:j + 1]


def remove_power_symbol_at(t, x, y):
    """Remove the (symbol (lib_id "cec-power:+5VSB") (at x y 0) ...) instance
    whose (at) matches exactly, returning (new_text, removed_pwr_ref)."""
    needle = f'(lib_id "cec-power:+5VSB")\n\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} 0)\n'
    m = t.find(needle)
    if m < 0:
        raise SystemExit(f"REFUSE: no +5VSB power symbol found at ({x},{y})")
    i = t.rindex("\t(symbol\n", 0, m)
    blk = carve(t, i)
    refm = re.search(r'\(property "Reference" "(#PWR\d+)"', blk)
    ref = refm.group(1) if refm else "?"
    return t.replace(blk, "", 1), ref


def gsnap(v):
    return round(v / GRID) * GRID


# ---------- 1. pin geometry for the RJ-45 (pin 1) and R_Small ----------
rj45_sym = re.search(r'\(symbol "cec:CEC_RJ45_8P8C_FTP"', txt)
rj45_pins = cec_sch.pin_table(carve(txt, rj45_sym.start()))
rsmall_sym = re.search(r'\(symbol "cec-vendor:R_Small"', txt)
R_PINS = cec_sch.pin_table(carve(txt, rsmall_sym.start()))


def stub_and_target(ax, ay, ang, L=2.54):
    if ang == 0:
        return gsnap(ax - L), gsnap(ay), 180
    if ang == 180:
        return gsnap(ax + L), gsnap(ay), 0
    if ang == 270:
        return gsnap(ax), gsnap(ay - L), 90
    if ang == 90:
        return gsnap(ax), gsnap(ay + L), 270
    raise ValueError(ang)


# J2..J5 placements (measured from the file: all rot 0)
JACKS = {
    "J2": (560.07, 44.45),
    "J3": (560.07, 95.25),
    "J4": (560.07, 149.86),
    "J5": (560.07, 204.47),
}

out = []
pwr_n = [9101]   # #PWR9101.. -- verified unused in this file (existing max namespaces:
                 # #PWR01.. / #PWR011xx / #PWR9001-9009)
removed_refs = []

lx1, ly1, ang1, _len1 = rj45_pins["1"]

for i, (jref, (jx, jy)) in enumerate(sorted(JACKS.items()), start=1):
    ax, ay = jx + lx1, jy - ly1
    ex, ey, lang = stub_and_target(ax, ay, ang1)   # existing stub end (matches file: 3.81mm, but
                                                    # gsnap uses L=2.54 default -- override below
    # The file's own stub length for these jacks is 3.81 (cec_sch.STUB), not the
    # 2.54 default used elsewhere -- recompute with the observed length so ex,ey
    # matches the EXISTING stub-end coordinate exactly (verified against the file
    # by direct grep before writing this script).
    ex, ey, lang = stub_and_target(ax, ay, ang1, L=cec_sch.STUB)

    # remove the +5VSB power symbol sitting at the stub end; keep the stub wire
    txt, pwr_ref = remove_power_symbol_at(txt, ex, ey)
    removed_refs.append((jref, pwr_ref, ex, ey))

    # add the /VCC_Pn label at the same point
    out.append(cec_sch.emit_label(f"VCC_P{i}", ex, ey, lang))

    # ---------- place Fi in the measured-empty region x440-520 / y230-300 ----------
    fx = gsnap(452.12 + (i - 1) * 20.32)   # 452.12, 472.44, 492.76, 513.08 -- unique, well spaced
    fy = gsnap(260.35)
    fref = f"F{i}"
    props = {
        "MPN": "SMD0805-050-6", "Manufacturer": "generic (JLC catalog)",
        "LCSC": "C46640983",
        "Note": ("Per-port RJ45-VCC polyfuse (owner ruling 2026-07-15): fault "
                 "isolation -- a shorted patch cable or failed module trips ONE "
                 "port instead of browning out the shared 5VSB system (the "
                 "TPS2121 limit is total, not per-port). 0805 PTC, 500mA hold, "
                 "6V rated. ~150mV drop at load absorbed by module LDO headroom."),
    }
    out.append(cec_sch.emit_symbol(fref, "cec-vendor", "R_Small", "PTC 500mA",
                                   fx, fy, sorted(R_PINS.keys()), PROJECT, ROOT,
                                   fp="cec-Resistor_SMD:R_0805_2012Metric",
                                   props=props))

    # pin 1 -> label /VCC_Pn (toward J's pin 1, matches the brief's F.pin1 side)
    plx, ply, pang, _pl = R_PINS["1"]
    pax, pay = fx + plx, fy - ply
    pex, pey, plang = stub_and_target(pax, pay, pang)
    out.append(cec_sch.emit_wire(pax, pay, pex, pey))
    out.append(cec_sch.emit_label(f"VCC_P{i}", pex, pey, plang))

    # pin 2 -> global power +5VSB
    plx2, ply2, pang2, _pl2 = R_PINS["2"]
    pax2, pay2 = fx + plx2, fy - ply2
    pex2, pey2, _plang2 = stub_and_target(pax2, pay2, pang2)
    out.append(cec_sch.emit_wire(pax2, pay2, pex2, pey2))
    ref = f"#PWR{pwr_n[0]}"; pwr_n[0] += 1
    out.append(cec_sch.emit_global_power("+5VSB", pex2, pey2, PROJECT, ROOT, ref))

blob = "\n".join(out) + "\n"
idx = txt.rindex("\t(sheet_instances")
txt = txt[:idx] + blob + txt[idx:]
open(SCH, "w").write(txt)

print("removed +5VSB power symbols:", removed_refs)
print(f"hub-rev2 polyfuse splice: F1-F4 inserted, J2-J5 pin1 rewired to /VCC_P1-4 "
      f"({len(out)} elements)")
