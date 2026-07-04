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
    "02-can":         (75, 8, 55, 30),
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
def extract(flat_sch):
    inv = G.inventory(flat_sch)
    groups = R.netlist_groups(flat_sch)
    by_name = {}
    for members, name in groups.items():
        if name.startswith("unconnected-"):
            continue
        by_name[name] = sorted(members)

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
