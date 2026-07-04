#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  gen-module-beta -- round-4 Wave 2 parametric hierarchical converter for the
#  cable-i2c module family (eps-8pin / pcie-8pin-2port / pcie-8pin-3port).
# ============================================================================
# Plan of record: docs/standard-tier-review/round4-hier-conversion-2026-07-04.md
# (ZERO-RENAME policy, gates G1-G11). Converts the CURRENT COMMITTED flat beta
# schematic (BETA-1, the standard-tier-review pass) into a genuine hierarchy
# (thin-parent root, same filename, in place) + one leaf per functional block,
# via scripts/cec_sch_compose.py (build_leaf/build_thin_parent, incl. this
# session's A1 `lane_labels` / A2 `name_pin_nets` extensions).
#
# EXTRACTION is FROM THE LIVE SCHEMATIC, never a stale snapshot: component
# inventory via cec_sch_gates.inventory (catches DNP parts a netlist alone
# would hide -- FL1 is DNP here) and connectivity via kicad-cli netlist
# (cec_pcb_reconcile.netlist_groups). The classify_ref() partition is a
# GENERIC anchor + ref-pattern rule (mirrors gen-module-rev2.py's role model:
# anchors U1=MCU, U2=CAN, U3=LDO, J1=hub-link, J5=usb-flash; the per-cable
# families U1x/U2x/U3x+RS*+C1x/C2x/C3x scale to any cable count), so the SAME
# script is expected to carry over to the two PCIe SKUs in Wave 3 (not
# validated on them yet -- eps-8pin is this session's proof board).
#
# PARTITION (7 literal leaf sheets; every net is either a genuine 2-leaf PAIR,
# routed as a real drawn lane with lane_labels=True so it keeps its exact flat
# name, or a single-leaf INTERNAL net force-exported via name_pin_nets so IT
# ALSO keeps its exact flat name -- the round-4 zero-rename policy applies to
# EVERY named net, not just the ones that happen to cross sheets):
#   01-hub-link    J1, D1, R1, R7, FB2, C6           (RJ-45 + DETECT + 5VSB bead)
#   02-can         U2, C4, C8, FL1, R11, R12         (TJA1051T/3 + CMC/bypass)
#   03-ldo         U3, C1, C2                        (LP5907 3V3, no cross-sheet nets)
#   04-mcu         U1, C3, C5, C7, R2, SW1, SW2       (ESP32-C6 + BOOT/RESET)
#   05-sensing     U1x/U2x/U3x (INA238/INA181/TLV7011) + C1x/C2x/C3x + R10/C40/R3/R4
#   06-cable-power J_IN*/J_OUT* + RS*                (cable interposer + shunts)
#   07-usb-flash   J5, D2, D3, FB1, C9, R8, R9        (USB-C flash/debug front end)
#
#   python3 scripts/gen-module-beta.py [board]   (default: eps-8pin)
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cec_sch                # noqa: E402
import cec_sch_compose as C   # noqa: E402
import cec_sch_layout as L    # noqa: E402
import cec_sch_gates as G     # noqa: E402
import cec_pcb_reconcile as R  # noqa: E402

LIBS = {
    "cec":        open(f"{ROOT}/lib/cec.kicad_sym").read(),
    "cec-vendor": open(f"{ROOT}/lib/vendor/cec-vendor.kicad_sym").read(),
    "power":      open(f"{ROOT}/lib/vendor/cec-power.kicad_sym").read(),
}
POWER_PORTS = {"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"}
POWER_NETS = set(POWER_PORTS)

# ---------------------------------------------------------------------------
# Board-agnostic PARTITION: fixed anchors + a generic per-cable ref pattern.
# ---------------------------------------------------------------------------
FIXED_LEAF = {
    "J1": "01-hub-link", "D1": "01-hub-link", "R1": "01-hub-link",
    "R7": "01-hub-link", "FB2": "01-hub-link", "C6": "01-hub-link",
    "U2": "02-can", "C4": "02-can", "C8": "02-can",
    "FL1": "02-can", "R11": "02-can", "R12": "02-can",
    "U3": "03-ldo", "C1": "03-ldo", "C2": "03-ldo",
    "U1": "04-mcu", "C3": "04-mcu", "C5": "04-mcu", "C7": "04-mcu",
    "R2": "04-mcu", "SW1": "04-mcu", "SW2": "04-mcu",
    "R10": "05-sensing", "C40": "05-sensing", "R3": "05-sensing", "R4": "05-sensing",
    "J5": "07-usb-flash", "D2": "07-usb-flash", "D3": "07-usb-flash",
    "FB1": "07-usb-flash", "C9": "07-usb-flash", "R8": "07-usb-flash", "R9": "07-usb-flash",
}
# per-cable families: U1x=INA238, U2x=INA181, U3x=TLV7011, C1x/C2x/C3x their
# decoupling; RS*=shunt; J_IN*/J_OUT*=interposer connectors. Scales to any
# cable count (eps=2, pcie-2port=2, pcie-3port=3) with no per-board table.
_CABLE_SENSE_RE = re.compile(r"^(U1\d+|U2\d+|U3\d+|C1\d+|C2\d+|C3\d+)$")
_CABLE_SHUNT_RE = re.compile(r"^RS\d+$")
_CABLE_CONN_RE = re.compile(r"^J_(IN|OUT)\d+$")


def classify_ref(ref):
    if ref in FIXED_LEAF:
        return FIXED_LEAF[ref]
    if _CABLE_SENSE_RE.match(ref):
        return "05-sensing"
    if _CABLE_SHUNT_RE.match(ref) or _CABLE_CONN_RE.match(ref):
        return "06-cable-power"
    return None


LEAF_META = {
    "01-hub-link":    ("01-hub-link.kicad_sch", "01-hub-link",
                       "RJ-45 hub link, DETECT chain, +5VSB entry bead (FB2)"),
    "02-can":         ("02-can.kicad_sch", "02-can",
                       "TJA1051T/3 CAN transceiver + CMC position (FL1, DNP) "
                       "with H3a-PATTERN 0R bypasses R11/R12"),
    "03-ldo":         ("03-ldo.kicad_sch", "03-ldo", "LP5907 3V3 LDO"),
    "04-mcu":         ("04-mcu.kicad_sch", "04-mcu",
                       "ESP32-C6-MINI-1 + BOOT/RESET"),
    "05-sensing":     ("05-sensing.kicad_sch", "05-sensing",
                       "Per-cable INA238 + section 6.13 transient-detection "
                       "front-end (INA181 + TLV7011)"),
    "06-cable-power": ("06-cable-power.kicad_sch", "06-cable-power",
                       "Cable interposer connectors + per-cable shunts"),
    "07-usb-flash":   ("07-usb-flash.kicad_sch", "07-usb-flash",
                       "USB-C 2.0 flash/debug front end (USBLC6-2SC6 + VBUS "
                       "bead FB1)"),
}
LEAF_ORDER = ["01-hub-link", "02-can", "03-ldo", "04-mcu", "05-sensing",
              "06-cable-power", "07-usb-flash"]

# fixed sheet-identity uuids (stable across regenerations; component/wire/
# label uuids stay cec_sch.u()-random each run, matching every other
# generator in this repo -- see round4 plan doc's byte-identity note).
LEAF_SYM_UUIDS = {
    "01-hub-link":    "67f50ca3-8cb0-4aa6-9a3f-011faa4ff8d7",
    "02-can":         "9b7ee0db-a842-437d-bf22-9658a349fa84",
    "03-ldo":         "99f6d174-d4e7-4999-a233-27fadf4a4e91",
    "04-mcu":         "83ceb2d1-e50f-4838-831a-71136b7d1260",
    "05-sensing":     "ca9223a8-32f6-4bda-a693-56772d321af3",
    "06-cable-power": "6f0a23cd-c50e-4d8f-b72e-2dfbfd05f476",
    "07-usb-flash":   "8adba108-789d-4153-ad59-e74c8138b4d8",
}
LEAF_OWN_UUIDS = {
    "01-hub-link":    "63130f89-e306-4331-8e66-e0167f812cd5",
    "02-can":         "dda99919-509e-418b-b8ae-16a2d69a459b",
    "03-ldo":         "a375475f-4e21-4ce5-b5a5-4b5e4564e2e1",
    "04-mcu":         "eec3be0a-fc70-40f0-b993-3e846a6af74d",
    "05-sensing":     "586db8b0-62b6-4eae-a808-7bc337e3c7cb",
    "06-cable-power": "69bf50ba-4b99-434f-a587-d33bc5b8de5c",
    "07-usb-flash":   "7bf63c17-7516-43ff-a8d2-a5b691ee5c36",
}

# box layout (grid units, x y w h) -- left-to-right flow row 1, row 2 hangs
# parts with no (or few) cross-sheet pins clear of every lane corridor.
BOX = {
    "01-hub-link":    (4, 8, 55, 40),
    # y=30 (not 8, row-aligned with the rest): DETECT_SENSE's hub-link->mcu
    # lane SKIPS OVER this box (can sits between them in x) and its tap
    # routes at hub-link's own pin height (~28mm, the round-4 lane_labels
    # tap mechanics) -- measured live, an y=8 can box of the same height
    # sat exactly in that lane's path. y=30 clears it while can's own two
    # pin pairs (still only 2 rows tall) fit easily.
    "02-can":         (75, 30, 55, 30),
    "04-mcu":         (150, 8, 60, 60),
    "05-sensing":     (240, 8, 55, 44),
    "06-cable-power": (315, 8, 50, 40),
    "03-ldo":         (4, 80, 45, 24),
    "07-usb-flash":   (240, 90, 55, 26),
}
LEAF_PAPER = {
    "01-hub-link": "A4", "02-can": "A4", "03-ldo": "A4", "04-mcu": "A3",
    "05-sensing": "A3", "06-cable-power": "A4", "07-usb-flash": "A4",
}


def find_flat_sch(board_dir):
    cands = [f for f in os.listdir(board_dir) if f.endswith(".kicad_sch")]
    if len(cands) != 1:
        raise SystemExit(f"expected exactly one .kicad_sch in {board_dir}, found {cands}")
    return os.path.join(board_dir, cands[0])


def is_hierarchical(sch_path):
    """A root is already hierarchical if it contains a (sheet ...) block."""
    text = open(sch_path).read()
    work = L._strip_lib_symbols(text)
    return bool(re.search(r'\(sheet\n', work))


# ============================================================================
# EXTRACTION -- direct from the live committed schematic (never a stale
# snapshot / never the *-rev2 extract.json experiment dirs).
# ============================================================================
def _bare_name(name):
    """kicad-cli's netlist export reports a flat (root-sheet) signal net as
    "/BARE_NAME" -- a NETLIST-reporting convention (the root-sheet path
    prefix), not something the schematic's own `(label ...)` text carries.
    Leaf.net()/hier_exports use the bare form throughout this repo (see
    gen-modules.py/gen_p4_t1_block.py), so it is stripped here, once, at
    extraction. Power nets (GND/+3V3/+5VSB) already have no prefix."""
    if name.count("/") > 1:
        raise SystemExit(f"gen-module-beta: net {name!r} has more than one "
                          f"path segment -- the flat-board assumption "
                          f"(root-sheet only) does not hold")
    return name[1:] if name.startswith("/") else name


def extract(flat_sch):
    inv = G.inventory(flat_sch)
    groups = R.netlist_groups(flat_sch)
    by_name = {}
    for members, name in groups.items():
        if name.startswith("unconnected-"):
            continue
        by_name[_bare_name(name)] = sorted(members)

    parts, footprints, props, dnp_refs = {}, {}, {}, set()
    for ref, d in inv.items():
        lib, name = d["lib_id"].split(":", 1)
        parts[ref] = (lib, name, d["value"])
        footprints[ref] = d["footprint"]
        props[ref] = d["props"]
        if d["dnp"]:
            dnp_refs.add(ref)

    leaf_of = {}
    for ref in parts:
        lid = classify_ref(ref)
        if lid is None:
            raise SystemExit(f"gen-module-beta: unclassified ref {ref!r} -- "
                              f"extend classify_ref()")
        leaf_of[ref] = lid

    pairs, internals = {}, {}
    for name, members in by_name.items():
        if name in POWER_NETS:
            continue
        by_leaf = {}
        for ref, pin in members:
            by_leaf.setdefault(leaf_of[ref], []).append((ref, pin))
        if len(by_leaf) == 1:
            (lid, conns), = by_leaf.items()
            internals[name] = (lid, conns)
        elif len(by_leaf) == 2:
            pairs[name] = by_leaf
        else:
            raise SystemExit(f"gen-module-beta: net {name!r} spans "
                              f"{len(by_leaf)} leaves {sorted(by_leaf)} -- "
                              f"only 1 or 2 supported; repartition or add a "
                              f"global_nets bus")

    power_members = {}
    for name in POWER_NETS:
        power_members[name] = by_name.get(name, [])

    return {
        "parts": parts, "footprints": footprints, "props": props,
        "dnp_refs": dnp_refs, "leaf_of": leaf_of,
        "pairs": pairs, "internals": internals, "power_members": power_members,
    }


def leaf_nets(extracted, lid):
    """{net_name: [(ref,pin),...]} for everything touching leaf `lid`
    (power nets excluded -- those go through power_ports uniformly)."""
    nets = {}
    for name, (owner_lid, conns) in extracted["internals"].items():
        if owner_lid == lid:
            nets[name] = list(conns)
    for name, by_leaf in extracted["pairs"].items():
        if lid in by_leaf:
            nets[name] = list(by_leaf[lid])
    for name in POWER_NETS:
        conns = [(ref, pin) for ref, pin in extracted["power_members"][name]
                 if extracted["leaf_of"][ref] == lid]
        if conns:
            nets[name] = conns
    return nets


def leaf_parts(extracted, lid):
    return {ref: pn for ref, pn in extracted["parts"].items()
            if extracted["leaf_of"][ref] == lid}


def _patch_dnp(path, dnp_refs):
    """Post-write patch: flip (dnp no) -> (dnp yes) for the given refs. Kept
    OUT of cec_sch_compose.py deliberately -- Part A's engine surface is
    scoped to lane_labels/name_pin_nets only; DNP is a board-driver concern
    (only FL1 on this board) applied as a targeted text splice, mirroring
    the same carve()-based technique cec_sch_gates.py already uses."""
    if not dnp_refs:
        return 0
    text = open(path).read()
    n = 0
    out, pos = [], 0
    for m in re.finditer(r'\t\(symbol\n', text):
        if m.start() < pos:
            continue
        blk = cec_sch.carve(text, m.start())
        rm = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', blk)
        if rm and rm.group(1) in dnp_refs and "(dnp no)" in blk:
            out.append(text[pos:m.start()])
            out.append(blk.replace("(dnp no)", "(dnp yes)", 1))
            pos = m.start() + len(blk)
            n += 1
    out.append(text[pos:])
    if n:
        open(path, "w").write("".join(out))
    return n


# ---------------------------------------------------------------------------
# PAIR_SIDES: for every 2-leaf net, which side ("right"=source/leftward box,
# "left"=dest/rightward box) each leaf declares, matching the BOX x-ordering
# below (hub-link < can < mcu < sensing < cable-power; usb-flash sits right
# of mcu). Derived once from the box layout -- see the module docstring.
# ---------------------------------------------------------------------------
PAIR_SIDES = {
    "CAN_H_RJ":     {"01-hub-link": "right", "02-can": "left"},
    "CAN_L_RJ":     {"01-hub-link": "right", "02-can": "left"},
    "DETECT_SENSE": {"01-hub-link": "right", "04-mcu": "left"},
    "CAN_TX":       {"02-can": "right", "04-mcu": "left"},
    "CAN_RX":       {"02-can": "right", "04-mcu": "left"},
    "SENSEC1_HI":   {"05-sensing": "right", "06-cable-power": "left"},
    "SENSEC1_LO":   {"05-sensing": "right", "06-cable-power": "left"},
    "SENSEC2_HI":   {"05-sensing": "right", "06-cable-power": "left"},
    "SENSEC2_LO":   {"05-sensing": "right", "06-cable-power": "left"},
    "THRESH_PWM":   {"04-mcu": "right", "05-sensing": "left"},
    "I2C_SDA":      {"04-mcu": "right", "05-sensing": "left"},
    "I2C_SCL":      {"04-mcu": "right", "05-sensing": "left"},
    "DETC1":        {"04-mcu": "right", "05-sensing": "left"},
    "DETC2":        {"04-mcu": "right", "05-sensing": "left"},
    "USB_D_P":      {"04-mcu": "right", "07-usb-flash": "left"},
    "USB_D_N":      {"04-mcu": "right", "07-usb-flash": "left"},
}

# G8 prose preservation: the flat BETA-1 sheet's section captions, carried
# verbatim onto the corresponding new leaf(s) (a string need only appear
# SOMEWHERE across the new sheet set, not on a specific one).
FLAT_CAPTIONS = {
    "01-hub-link": ["HUB LINK  RJ-45 + DETECT"],
    "02-can": ["CAN  TJA1051",
               "H3 STANDALONE-MODE SUITE (USB ESD/EMC + CAN CMC)"],
    "03-ldo": ["3V3 LDO"],
    "04-mcu": ["MCU  ESP32-C6-MINI-1"],
    "05-sensing": ["PER-CABLE SENSING  INA238",
                   "6.13 TRANSIENT DETECTION  cable 1",
                   "6.13 TRANSIENT DETECTION  cable 2"],
    "06-cable-power": [],
    "07-usb-flash": ["FLASH / USB-C"],
}


def _auto_io(c, hier_exports):
    """Standard S1: gather every hier-exported net to the leaf's own left/
    right edge column by the anchor pin's NATURAL stub direction (mirrors
    ent-common compose_04/compose_05's pattern). This is a LEAF-internal
    layout choice, independent of the ROOT box side in PAIR_SIDES."""
    for net, (_shape, (ref, pin)) in hier_exports.items():
        _pt, (dx, _dy) = c.pin_out(ref, pin)
        c.io(net, "left" if dx < 0 else "right")


def _grid_place(c, refs, x0, y0, cols, dx=16, dy=16):
    for i, ref in enumerate(refs):
        c.place(ref, x0 + (i % cols) * dx, y0 + (i // cols) * dy)


def _ladder_column(c, pins, offset_dx):
    """Jog each (ref,pin) in `pins` (already ordered along ONE physical
    column) out to a shared offset column `offset_dx` grid units from its
    own connection point, then chain the jog points with real wire segments
    -- the round-4 owner item 2 GND-bus-to-one-link treatment, generalizing
    ent-common's 3-pin g17/g18/g37 precedent to a full N-pin ladder. Marks
    every pin `consumed` (the generic per-pin stub+port pass skips them).
    Returns the ordered jog points [(x,y), ...] (first/last are the chain's
    free ends, for the caller to extend/stamp)."""
    pts = []
    for ref, pin in pins:
        (px, py), _dv = c.pin_out(ref, pin)
        gx = px + offset_dx
        c.wire((px, py), (gx, py))
        c.use((ref, pin))
        pts.append((gx, py))
    for a, b in zip(pts, pts[1:]):
        c.wire(a, b)
    return pts


# ============================================================================
# LEAF COMPOSERS
# ============================================================================
def compose_hub_link(c, lf):
    c.place("J1", 40, 45)
    c.place("D1", 75, 20)
    c.place("R1", 90, 20)
    c.place("R7", 105, 20)
    c.place("FB2", 75, 55)
    c.place("C6", 95, 55)
    # J1 pins 4/5/7 (STREAM_P/N, RSVD) are unused at Standard tier -- left
    # untouched (no net membership) so build_leaf's generic pass emits their
    # no_connect flags automatically, matching the flat baseline exactly.
    _auto_io(c, lf.hier_exports)
    c.caption(FLAT_CAPTIONS["01-hub-link"][0], 20, 8)
    c.done()


def compose_can(c, lf):
    c.place("U2", 45, 30)
    c.place("C4", 80, 15)
    c.place("C8", 80, 45)
    c.place("FL1", 45, 65)
    c.place("R11", 65, 65)
    c.place("R12", 85, 65)
    _auto_io(c, lf.hier_exports)
    for txt in FLAT_CAPTIONS["02-can"]:
        c.caption(txt, 10, 8 + FLAT_CAPTIONS["02-can"].index(txt) * 5)
    c.done()


def compose_ldo(c, lf):
    c.place("U3", 40, 30)
    c.place("C1", 65, 18)
    c.place("C2", 65, 42)
    c.caption(FLAT_CAPTIONS["03-ldo"][0], 10, 8)
    c.done()


def compose_mcu(c, lf):
    U1X, U1Y = 80, 45
    c.place("U1", U1X, U1Y)
    used_entry = c.used[("cec-vendor", "ESP32-C6-MINI-1-N4")]
    body = L.body_box_abs(used_entry["block"], U1X * cec_sch.GRID, U1Y * cec_sch.GRID, 0)
    body_bottom = round(body[3] / cec_sch.GRID)

    left_pins = [("U1", "1"), ("U1", "2"), ("U1", "11"), ("U1", "14")]
    right_pins = [("U1", str(p)) for p in range(36, 54)]
    left_pts = _ladder_column(c, left_pins, -2)
    right_pts = _ladder_column(c, right_pins, 2)
    wrap_y = body_bottom + 3
    lx, ly = left_pts[-1]
    rx, ry = right_pts[0]
    c.wire((lx, ly), (lx, wrap_y))
    c.wire((lx, wrap_y), (rx, wrap_y))
    c.wire((rx, wrap_y), (rx, ry))
    ex, ey = right_pts[-1]
    c.wire((ex, ey), (ex, ey + 3))
    c.stamp("GND", ex, ey + 3, 0)

    _grid_place(c, ["C3", "C5", "C7", "R2", "SW1", "SW2"], 30, wrap_y + 12, 6, dx=16)
    _auto_io(c, lf.hier_exports)
    c.caption(FLAT_CAPTIONS["04-mcu"][0], 20, 8)
    c.note("EN/GPIO0 are BOOT/RESET straps (SW1/SW2) -- leaf-internal, "
           "name-pinned to keep their bare net names", 30, wrap_y + 30)
    c.done()


def compose_sensing(c, lf, cable_labels):
    # LEFT column exits toward the MCU leaf (THRESH_PWM/I2C/DETC*); RIGHT
    # column exits toward the cable-power leaf (SENSEC*_HI/_LO). Placement
    # follows that flow directly (cmp_/R10/C40/R3/R4 left, ina right) so the
    # io-column router's wire stays short. INA226 (ina) is placed rot=180:
    # its Vin+/Vin- pins (8/9/10, the SENSEC anchors) are symbol-authored on
    # the LEFT (angle 0) -- measured live, a naive rot=0 placement sent the
    # SENSEC wire straight through the SAME part's own body trying to reach
    # the right-side column. rot=180 flips them to the right (its I2C/addr/
    # alert pins move left in exchange, harmless: their own hier anchors are
    # R3/R4, not U1x, so U1x's copies just carry a plain same-name label).
    _grid_place(c, ["R10", "C40", "R3", "R4"], 15, 8, 4, dx=16, dy=16)
    y = 40
    for i, label in enumerate(cable_labels):
        ina, amp, cmp_ = f"U1{i}", f"U2{i}", f"U3{i}"
        dec, ca, cb = f"C1{i}", f"C2{i}", f"C3{i}"
        c.place(cmp_, 15, y)
        c.place(cb, 15, y + 20)
        c.place(amp, 55, y)
        c.place(ca, 55, y + 20)
        c.place(ina, 100, y, 180)
        c.place(dec, 100, y + 20)
        y += 45
    for net in lf.hier_exports:
        c.io(net, "right" if re.match(r"^SENSEC", net) else "left")
    for i, txt in enumerate(FLAT_CAPTIONS["05-sensing"]):
        c.caption(txt, 10 + i * 2, 8 - (2 if i == 0 else 0))
    c.done()


def compose_cable_power(c, lf, cable_labels):
    # Both J_IN and J_OUT's SENSE pins are symbol-authored on the LEFT
    # (angle 0) -- the SAME direction the io side ("left", toward sensing)
    # needs -- so both connectors share ONE x column (stacked vertically);
    # the shunt (no cross-sheet net of its own beyond what the connectors
    # already carry) sits clear to the RIGHT, out of the left-bound path
    # (placing it directly between the connectors and the left edge, as an
    # earlier attempt did, sent the io-column wire straight through its
    # body -- measured live).
    y = 20
    for i in range(len(cable_labels)):
        c.place(f"J_IN{i + 1}", 15, y)
        c.place(f"J_OUT{i + 1}", 15, y + 20)
        c.place(f"RS{i + 1}", 45, y + 10)
        y += 45
    _auto_io(c, lf.hier_exports)
    c.done()


def compose_usb_flash(c, lf):
    # D3 (USBLC6-2SC6) carries the USB_D_P/USB_D_N hier anchors on ITS OWN
    # LEFT pins (1/3) -- placed leftmost so the io-column wire has nothing
    # else to cross (measured live: with J2/D2 to its left, the wire clipped
    # a foreign pin along the way).
    c.place("D3", 15, 45)
    c.place("J5", 70, 45)
    c.place("D2", 100, 20)
    c.place("FB1", 100, 45)
    c.place("C9", 100, 70)
    c.place("R8", 120, 20)
    c.place("R9", 120, 70)
    _auto_io(c, lf.hier_exports)
    c.caption(FLAT_CAPTIONS["07-usb-flash"][0], 20, 8)
    c.done()


# ============================================================================
# DRIVER
# ============================================================================
def _cable_labels(extracted):
    """Cable node labels (e.g. ["C1","C2"]) from the SENSEC*_HI net names
    touching the sensing leaf -- board-agnostic (works for 2 or 3 cables)."""
    labels = set()
    for name in extracted["pairs"]:
        m = re.match(r"^SENSEC(\w+)_HI$", name)
        if m:
            labels.add(m.group(1))
    return sorted(labels, key=lambda s: (len(s), s))


def build(board, force=False):
    board_dir = os.path.join(ROOT, "modules", board)
    flat_sch = find_flat_sch(board_dir)
    if is_hierarchical(flat_sch) and not force:
        raise SystemExit(f"{flat_sch} is already hierarchical -- refusing to "
                          f"run (pass --force to regenerate anyway)")

    root_uuid = re.search(r'\(uuid\s+"([0-9a-fA-F-]+)"\)', open(flat_sch).read()).group(1)
    title_m = re.search(r'\(title\s+"([^"]*)"\)', open(flat_sch).read())
    rev_m = re.search(r'\(rev\s+"([^"]*)"\)', open(flat_sch).read())
    title = title_m.group(1) if title_m else board
    rev = rev_m.group(1) if rev_m else "DRAFT"

    extracted = extract(flat_sch)
    cable_labels = _cable_labels(extracted)

    LEAVES = {}
    for lid in LEAF_ORDER:
        fname, sheetname, desc = LEAF_META[lid]
        lf = C.Leaf(lid, fname, sheetname, desc)
        lf.parts = leaf_parts(extracted, lid)
        lf.nets = leaf_nets(extracted, lid)
        lf.footprints = {r: extracted["footprints"][r] for r in lf.parts}
        lf.props = {r: extracted["props"][r] for r in lf.parts if extracted["props"][r]}
        lf.placement = {}
        hx = {}
        for net, sides in PAIR_SIDES.items():
            if lid in sides and net in lf.nets:
                hx[net] = ("output", lf.nets[net][0])
        lf.hier_exports = hx
        lf.powerflag_nets = ["+5VSB", "GND"] if lid == "01-hub-link" else []
        LEAVES[lid] = lf

    name_pin_nets = {}
    for name, (owner_lid, _conns) in extracted["internals"].items():
        name_pin_nets.setdefault(owner_lid, []).append(name)

    stats = {}
    for lid in LEAF_ORDER:
        lf = LEAVES[lid]
        c = C.Compose(lf, LIBS)
        if lid == "01-hub-link":
            compose_hub_link(c, lf)
        elif lid == "02-can":
            compose_can(c, lf)
        elif lid == "03-ldo":
            compose_ldo(c, lf)
        elif lid == "04-mcu":
            compose_mcu(c, lf)
        elif lid == "05-sensing":
            compose_sensing(c, lf, cable_labels)
        elif lid == "06-cable-power":
            compose_cable_power(c, lf, cable_labels)
        elif lid == "07-usb-flash":
            compose_usb_flash(c, lf)

        out_path = os.path.join(board_dir, lf.filename)
        st = C.build_leaf(
            lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None,
            LIBS, board, path_prefix=f"{root_uuid}/{LEAF_SYM_UUIDS[lid]}",
            sheet_instances_path=LEAF_SYM_UUIDS[lid],
            own_uuid=LEAF_OWN_UUIDS[lid], page=str(LEAF_ORDER.index(lid) + 2),
            out_path=out_path, paper=LEAF_PAPER[lid],
            title=f"{title}: {lf.sheetname}", comment1=lf.desc,
            pwr_base=100 * (LEAF_ORDER.index(lid) + 1), layout=lf.layout,
            name_pin_nets=name_pin_nets.get(lid))
        n_moved, still = L.nudge_texts(out_path)
        st["nudged"], st["text_overlaps_left"] = n_moved, still
        dnp_here = extracted["dnp_refs"] & set(lf.parts)
        st["dnp_patched"] = _patch_dnp(out_path, dnp_here)
        stats[lid] = st
        print(f"{lf.filename}  " + "  ".join(f"{k}={v}" for k, v in st.items()))

    u = cec_sch.GRID
    leaves_for_parent = []
    for lid in LEAF_ORDER:
        lf = LEAVES[lid]
        bx, by, bw, bh = BOX[lid]
        pins = []
        for net, sides in PAIR_SIDES.items():
            if lid in sides:
                pins.append((net, lf.hier_exports[net][0], sides[lid]))
        leaves_for_parent.append({
            "id": lid, "sym_uuid": LEAF_SYM_UUIDS[lid], "filename": lf.filename,
            "sheetname": lf.sheetname, "page": str(LEAF_ORDER.index(lid) + 2),
            "x": bx * u, "y": by * u, "w": bw * u, "h": bh * u, "pins": pins,
        })

    root_path = flat_sch
    parent_stats = C.build_thin_parent(
        leaves_for_parent, set(), board, root_uuid, None, root_uuid,
        out_path=root_path, title=title, paper="A2", libs=LIBS,
        pwr_base=900, lane_labels=True, name_pin_nets=name_pin_nets,
        title_comments=(
            f"Thin parent (round-4 hierarchical conversion, Rev {rev}) -- "
            "sheet-symbol fan-out/fan-in only, no components",
            "Leaf sheets: " + ", ".join(lf.sheetname for lf in LEAVES.values()),
            "GND/+3V3/+5VSB are global power nets (per-leaf symbols); every "
            "other crossing is a real drawn sheet-pin lane carrying its "
            "exact flat-schematic net name (lane_labels)"))
    print(f"{os.path.basename(root_path)} (thin parent)  " +
          "  ".join(f"{k}={v}" for k, v in parent_stats.items()))
    return stats, parent_stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("board", nargs="?", default="eps-8pin")
    ap.add_argument("--force", action="store_true",
                     help="regenerate even if the root is already hierarchical")
    args = ap.parse_args(argv)
    build(args.board, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
