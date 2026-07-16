#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  gen-12vhpwr-beta -- round-4 Wave 3b hierarchical converter for
#  modules/12vhpwr-standard (a SPECIFIC board, not a parametric family --
#  unlike gen-module-beta.py's cable-i2c family, this board has a fixed
#  6-channel INA240 sensing front end + a hand-maintained, hand-spliced
#  schematic; 85 refs / 87 netlist groups, CI-gated, routed PCB).
# ============================================================================
# Plan of record: docs/standard-tier-review/round4-hier-conversion-2026-07-04.md
# (ZERO-RENAME policy, gates G1-G11). A SIBLING of scripts/gen-module-beta.py:
# reuses the SAME shared engine (cec_sch / cec_sch_compose / cec_sch_layout /
# cec_sch_gates / cec_pcb_reconcile) and the SAME extraction/compose pattern,
# but is deliberately self-contained rather than importing gen-module-beta.py
# (a dash-named file, not import-able by a normal `import` statement without
# importlib gymnastics) -- per the task's own instruction not to restructure
# that proven driver. The only engine change this board needed was ADDITIVE:
# cec_sch_compose.PAPER gained "A1"/"A0" entries (this board's 11-leaf,
# hub-and-spoke fan-out needs more page than A2 offers); verified byte-
# identical (masked-uuid) regeneration of ent-common (7 files), hub-enterprise
# (27 files), and eps-8pin (8 files) with vs without that addition.
#
# PARTITION (11 literal leaf sheets; every net verified computationally, BEFORE
# composing, to touch <=2 leaves -- see the module docstring of `extract()`):
#   01-input     J2, J3, R10-R13         (12V-2x6 IN + fan header + sideband
#                                         series taps -- taps MUST sit with J3,
#                                         not with the MCU, or the 3-member
#                                         SB_* base net would span 3 leaves)
#   02-lanes     RS1-6, RFH1-6, RFL1-6,  (shunts + per-channel RC filters +
#                CF1-6, R5, R6, C24       the rail-divider R5/R6/C24 -- pulled
#                                         in here, not with U4/rail-ref, so
#                                         /FAN_12V stays a 2-leaf net)
#   03-output    J4                       (12V-2x6 OUT captive pigtail)
#   04-ina       U10-U15, C10-C15         (6x INA240 + bypass caps)
#   05-mcu       U1, C3, C5, C7, R2,      (ESP32-S3-MINI-1 + BOOT/RESET + EN RC)
#                SW1, SW2
#   06-can       U2, C4, C8, FL1,         (TJA1051T/3 + CMC position + the
#                R22, R23                 H3a-PATTERN 0R bypasses)
#   07-ldo       U3, C1, C2               (LP5907 3V3 -- NO cross-sheet nets)
#   08-usb       J5, D2, D3, D4, FB1,     (USB-C flash/debug + H3 USB ESD/EMC
#                C9, R8, R9               suite: USBLC6-2SC6 + VBUS bead + PESD)
#   09-hub-link  J1, D1, R1, R7, FB2, C6  (RJ-45 + DETECT chain + 5VSB bead)
#   10-temp      TH1, TH2, R20, R21,      (board-temp NTC dividers)
#                C20, C21
#   11-rail-ref  U4, C22, C23             (REF3030 ratiometric ADC reference)
#
# Verified partition satisfies the <=2-leaf rule for all 49 cross nets + 10
# leaf-internal (name-pinned) nets; 07-ldo carries zero named signal nets (no
# hier_exports at all, matching gen-module-beta.py's eps 03-ldo precedent).
#
#   python3 scripts/gen-12vhpwr-beta.py [--force]
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

BOARD = "12vhpwr-standard"
BOARD_DIR = os.path.join(ROOT, "modules", BOARD)
FLAT_SCH = os.path.join(BOARD_DIR, "12vhpwr-standard-module.kicad_sch")
PROJECT_NAME = "12vhpwr-standard-module"

LIBS = {
    "cec":        open(f"{ROOT}/lib/cec.kicad_sym").read(),
    "cec-vendor": open(f"{ROOT}/lib/vendor/cec-vendor.kicad_sym").read(),
    "power":      open(f"{ROOT}/lib/vendor/cec-power.kicad_sym").read(),
}
POWER_PORTS = {"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"}
POWER_NETS = set(POWER_PORTS)

# ---------------------------------------------------------------------------
# FIXED PARTITION -- this board is not parametric (one specific 6-channel
# schematic), so every ref is listed explicitly (no per-cable regex needed).
# ---------------------------------------------------------------------------
FIXED_LEAF = {}


def _assign(leaf, refs):
    for r in refs:
        assert r not in FIXED_LEAF, f"{r} assigned twice"
        FIXED_LEAF[r] = leaf


_assign("01-input", ["J2", "J3", "R10", "R11", "R12", "R13"])
_assign("02-lanes", [f"RS{i}" for i in range(1, 7)] +
                    [f"RFH{i}" for i in range(1, 7)] +
                    [f"RFL{i}" for i in range(1, 7)] +
                    [f"CF{i}" for i in range(1, 7)] +
                    ["R5", "R6", "C24"])
_assign("03-output", ["J4"])
_assign("04-ina", [f"U1{i}" for i in range(0, 6)] + [f"C1{i}" for i in range(0, 6)])
_assign("05-mcu", ["U1", "C3", "C5", "C7", "R2", "SW1", "SW2"])
_assign("06-can", ["U2", "C4", "C8", "FL1", "R22", "R23"])
_assign("07-ldo", ["U3", "C1", "C2"])
_assign("08-usb", ["J5", "D2", "D3", "D4", "FB1", "C9", "R8", "R9"])
_assign("09-hub-link", ["J1", "D1", "R1", "R7", "FB2", "C6"])
_assign("10-temp", ["TH1", "TH2", "R20", "R21", "C20", "C21"])
_assign("11-rail-ref", ["U4", "C22", "C23"])

assert len(FIXED_LEAF) == 85, len(FIXED_LEAF)


def classify_ref(ref):
    return FIXED_LEAF.get(ref)


# Rank order for the thin-parent's left(source)/right(dest) PAIR_SIDES choice
# (build_thin_parent sorts a 2-endpoint net's pins by X and requires the
# smaller-X pin to be side="right", the larger side="left" -- see that
# function's docstring). This is a pure geometric total order, NOT a signal-
# flow direction (no semantic meaning); any total order works as long as
# every leaf gets a distinct rank, which is what makes every pairwise
# direction choice below consistent and cycle-free. 07-ldo carries no
# cross-sheet nets and is intentionally excluded (no rank needed).
RANK = {
    "01-input": 1, "02-lanes": 2, "03-output": 3, "04-ina": 4, "05-mcu": 5,
    "06-can": 6, "09-hub-link": 7, "08-usb": 8, "10-temp": 9, "11-rail-ref": 10,
}

LEAF_META = {
    "01-input":    ("01-input.kicad_sch", "01-input",
                    "12V-2x6 IN (J3) + fan header (J2, DNP) + sideband series taps"),
    "02-lanes":    ("02-lanes.kicad_sch", "02-lanes",
                    "Per-channel shunts (RS1-6) + INA240 input RC filters "
                    "(RFH/RFL/CF) + rail-voltage divider (R5/R6/C24)"),
    "03-output":   ("03-output.kicad_sch", "03-output",
                    "12V-2x6 OUT captive pigtail (J4)"),
    "04-ina":      ("04-ina.kicad_sch", "04-ina",
                    "6x INA240 per-pin current-sense amplifiers + bypass"),
    "05-mcu":      ("05-mcu.kicad_sch", "05-mcu",
                    "MCU  ESP32-S3-MINI-1 + BOOT/RESET + EN RC"),
    "06-can":      ("06-can.kicad_sch", "06-can",
                    "CAN  TJA1051T/3 + CMC position (FL1, DNP) with the "
                    "H3a-PATTERN 0R bypasses R22/R23"),
    "07-ldo":      ("07-ldo.kicad_sch", "07-ldo", "3V3 LDO"),
    "08-usb":      ("08-usb.kicad_sch", "08-usb",
                    "FLASH / USB-C + H3 standalone-mode USB ESD/EMC suite"),
    "09-hub-link": ("09-hub-link.kicad_sch", "09-hub-link",
                    "HUB LINK  RJ-45 + DETECT"),
    "10-temp":     ("10-temp.kicad_sch", "10-temp",
                    "Board/shunt-row + ambient NTC temperature sensing"),
    "11-rail-ref": ("11-rail-ref.kicad_sch", "11-rail-ref",
                    "RAIL REF  REF3030 ratiometric ADC reference"),
}
LEAF_ORDER = ["01-input", "02-lanes", "03-output", "04-ina", "05-mcu",
              "06-can", "07-ldo", "08-usb", "09-hub-link", "10-temp",
              "11-rail-ref"]

# fixed sheet-identity uuids (stable across regenerations; component/wire/
# label uuids stay cec_sch.u()-random each run, matching every other
# generator in this repo).
LEAF_SYM_UUIDS = {
    "01-input":    "1a9d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a01",
    "02-lanes":    "2b9d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a02",
    "03-output":   "3c9d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a03",
    "04-ina":      "4d9d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a04",
    "05-mcu":      "5e9d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a05",
    "06-can":      "6f9d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a06",
    "07-ldo":      "709d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a07",
    "08-usb":      "819d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a08",
    "09-hub-link": "929d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a09",
    "10-temp":     "a39d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a10",
    "11-rail-ref": "b49d5a2e-6b0a-4b6b-9a7a-2f7a7a8a1a11",
}
LEAF_OWN_UUIDS = {
    "01-input":    "c59d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a01",
    "02-lanes":    "d69d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a02",
    "03-output":   "e79d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a03",
    "04-ina":      "f89d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a04",
    "05-mcu":      "099d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a05",
    "06-can":      "1a8d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a06",
    "07-ldo":      "2b8d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a07",
    "08-usb":      "3c8d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a08",
    "09-hub-link": "4d8d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a09",
    "10-temp":     "5e8d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a10",
    "11-rail-ref": "6f8d5a2e-6b0a-4b6b-9a7a-2f7a7a8a2a11",
}

# Root-sheet box layout (grid units; 1u = cec_sch.GRID = 1.27mm), designed so
# every 2-leaf net's source/dest X ordering matches RANK (see build_thin_
# parent's docstring) AND no unrelated leaf sits geometrically between a
# pair's source/dest at a Y that a lane's horizontal leg would cross (the
# "hop-over" hazard gen-module-beta.py's own comments document): 05-mcu's
# five right-side destinations (06-can/08-usb/09-hub-link/10-temp/11-rail-
# ref) are stacked in DISTINCT, non-overlapping Y rows below mcu's own pin-
# cluster band, so their relative X doesn't matter for collision-avoidance,
# only for RANK direction (06-can/09-hub-link differ in X because they ALSO
# share a direct edge, CAN_H/CAN_L).
BOX = {
    # GROUP A -- the main flow chain (01-input -> 02-lanes -> {03-output,
    # 04-ina} -> 05-mcu). Several edges SKIP an intermediate leaf (e.g.
    # 01-input->03-output skips over 02-lanes; 01-input/02-lanes->05-mcu
    # skip over 04-ina), and build_thin_parent's lane wires travel the FULL
    # X-span between source and dest at the SOURCE's own row height -- if an
    # intermediate leaf's box Y-range happens to include that height, the
    # wire crosses it (measured live: "wire ... crosses sheet box 02-lanes").
    # Fix: give every group-A leaf a Y-STAIRCASE (monotonically increasing,
    # non-overlapping bands) so a skip-ahead wire (confined to ITS SOURCE's
    # own narrow row-band) can never reach an intermediate leaf's Y-range,
    # regardless of X overlap.
    "01-input":    (4,   8,   50, 70),
    "02-lanes":    (80,  95,  65, 100),
    "03-output":   (180, 210, 45, 50),
    "04-ina":      (260, 275, 60, 70),
    "05-mcu":      (360, 360, 80, 70),
    # GROUP B -- 05-mcu's five "spoke" destinations. Each connects ONLY to
    # mcu (06-can also directly to 09-hub-link), never to group A, so they
    # can safely reuse group A's ORIGINAL y=8 band: mcu's own outgoing wires
    # run at MCU's row-band (y ~ 366-394), a completely different Y-range
    # than y=8, so group B's boxes at y=8 never intersect them regardless of
    # X. Increasing X (with a lane-sized gap after each) keeps 06-can/09-hub-
    # link's direct edge AND every mcu-spoke edge in the required
    # source-x < dest-x order, and keeps each spoke clear of its neighbors.
    "06-can":      (470, 8, 50, 40),
    "09-hub-link": (560, 8, 50, 50),
    "08-usb":      (650, 8, 50, 40),
    "10-temp":     (740, 8, 45, 32),
    "11-rail-ref": (825, 8, 45, 32),
    # 07-ldo carries NO cross-sheet nets at all (matches gen-module-beta.py's
    # eps 03-ldo precedent) -- placed well clear of every other leaf's row
    # band and X span, so it can never be hit by any lane wire.
    "07-ldo":      (4,   460, 45, 26),
}
LEAF_PAPER = {lid: ("A2" if lid in ("02-lanes", "04-ina")
                    else "A3" if lid == "05-mcu" else "A4")
              for lid in LEAF_ORDER}
ROOT_PAPER = "A0"


# ============================================================================
# EXTRACTION -- direct from the live committed schematic (never a stale
# snapshot). Mirrors gen-module-beta.py's extract()/leaf_nets()/leaf_parts()
# exactly (same connectivity-derivation approach), adapted for this board's
# fixed (non-parametric) partition.
# ============================================================================
def is_hierarchical(sch_path):
    text = open(sch_path).read()
    work = L._strip_lib_symbols(text)
    return bool(re.search(r'\(sheet\n', work))


def _bare_name(name):
    if name.count("/") > 1:
        raise SystemExit(f"gen-12vhpwr-beta: net {name!r} has more than one "
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
            raise SystemExit(f"gen-12vhpwr-beta: unclassified ref {ref!r} -- "
                              f"extend FIXED_LEAF")
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
            raise SystemExit(f"gen-12vhpwr-beta: net {name!r} spans "
                              f"{len(by_leaf)} leaves {sorted(by_leaf)} -- "
                              f"only 1 or 2 supported; repartition")

    power_members = {}
    for name in POWER_PORTS:   # dict, insertion-ordered -- see gen-module-
        power_members[name] = by_name.get(name, [])   # beta.py's non-determinism note

    return {
        "parts": parts, "footprints": footprints, "props": props,
        "dnp_refs": dnp_refs, "leaf_of": leaf_of,
        "pairs": pairs, "internals": internals, "power_members": power_members,
    }


def leaf_nets(extracted, lid):
    nets = {}
    for name, (owner_lid, conns) in extracted["internals"].items():
        if owner_lid == lid:
            nets[name] = list(conns)
    for name, by_leaf in extracted["pairs"].items():
        if lid in by_leaf:
            nets[name] = list(by_leaf[lid])
    for name in POWER_PORTS:   # insertion-ordered dict -- deterministic across runs
        conns = [(ref, pin) for ref, pin in extracted["power_members"][name]
                 if extracted["leaf_of"][ref] == lid]
        if conns:
            nets[name] = conns
    return nets


def leaf_parts(extracted, lid):
    return {ref: pn for ref, pn in extracted["parts"].items()
            if extracted["leaf_of"][ref] == lid}


def compute_pair_sides(pairs):
    """{net_name: {leaf_id: 'left'|'right'}} derived purely from RANK (see
    that dict's comment) -- the smaller-rank leaf of each 2-leaf net is
    'right' (source), the larger is 'left' (dest). Both leaves of every pair
    must carry a rank (07-ldo never appears here, since it has no pairs)."""
    sides = {}
    for name, by_leaf in pairs.items():
        lids = sorted(by_leaf, key=lambda l: RANK[l])
        sides[name] = {lids[0]: "right", lids[1]: "left"}
    return sides


def _patch_dnp(path, dnp_refs):
    """Post-write patch: flip (dnp no) -> (dnp yes) for the given refs (this
    board's only DNP part is FL1, the CAN CMC position). Mirrors gen-module-
    beta.py's identical helper -- kept OUT of cec_sch_compose.py deliberately."""
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


_LABEL_LINE_RE = re.compile(
    r'\t\(label "([^"]+)" \(at ([\d.\-]+) ([\d.\-]+) (\d+)\) '
    r'\(effects[^\n]*\n')


def _dedupe_labels(path):
    """Post-write patch: drop duplicate (name,x,y) label lines stacked on an
    identical point (a safe cosmetic dedupe -- see gen-module-beta.py's
    identical helper for the full rationale, measured live there)."""
    text = open(path).read()
    seen = set()
    out = []
    n = 0
    pos = 0
    for m in _LABEL_LINE_RE.finditer(text):
        key = (m.group(1), m.group(2), m.group(3))
        out.append(text[pos:m.start()])
        if key in seen:
            n += 1
            pos = m.end()
            continue
        seen.add(key)
        out.append(m.group(0))
        pos = m.end()
    out.append(text[pos:])
    if n:
        open(path, "w").write("".join(out))
    return n


def _grid_place(c, refs, x0, y0, cols, dx=16, dy=16):
    for i, ref in enumerate(refs):
        c.place(ref, x0 + (i % cols) * dx, y0 + (i // cols) * dy)


def _auto_io(c, hier_exports):
    """Standard S1: gather every hier-exported net to the leaf's own left/
    right edge column by the anchor pin's natural stub direction. A LEAF-
    internal layout choice, independent of the ROOT box side in PAIR_SIDES."""
    for net, (_shape, (ref, pin)) in hier_exports.items():
        _pt, (dx, _dy) = c.pin_out(ref, pin)
        c.io(net, "left" if dx < 0 else "right")


def _ladder_column(c, pins, offset_dx):
    """Jog each (ref,pin) in `pins` (already ordered along ONE physical
    column) out to a shared offset column, then chain the jog points with
    real wire segments -- the owner's GND-bus item, generalizing ent-
    common's small-N precedent to a full N-pin ladder. Marks every pin
    `consumed`. Returns the ordered jog points."""
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


# G8 prose preservation: the flat sheet's 8 measured section captions,
# carried onto the new leaf whose content best matches (a string need only
# appear SOMEWHERE across the new sheet set -- see gen-module-beta.py's
# identical FLAT_CAPTIONS precedent/comment). "RAIL REF + SIDEBAND  REF3030"
# is placed on 11-rail-ref even though the sideband series taps (R10-R13)
# physically moved to 01-input for the <=2-leaf constraint (see the module
# docstring) -- the caption STRING is what G8 checks, not co-location.
FLAT_CAPTIONS = {
    "09-hub-link": "HUB LINK  RJ-45 + DETECT",
    "07-ldo": "3V3 LDO",
    "06-can": "CAN  TJA1051",
    "05-mcu": "MCU  ESP32-S3-MINI-1",
    "04-ina": "6-CHANNEL PER-PIN SENSING  6x INA240",
    "11-rail-ref": "RAIL REF + SIDEBAND  REF3030",
    "08-usb": "FLASH / USB-C",
    "02-lanes": "H3 STANDALONE-MODE SUITE (USB ESD/EMC)",
}


# ============================================================================
# LEAF COMPOSERS
# ============================================================================
def compose_ldo(c, lf):
    c.place("U3", 40, 30)
    c.place("C1", 65, 18)
    c.place("C2", 65, 42)
    c.caption(FLAT_CAPTIONS["07-ldo"], 10, 8)
    c.done()


def compose_output(c, lf):
    c.place("J4", 40, 40)
    _auto_io(c, lf.hier_exports)
    c.done()


def compose_rail_ref(c, lf):
    c.place("U4", 40, 30)
    c.place("C22", 65, 18)
    c.place("C23", 65, 42)
    _auto_io(c, lf.hier_exports)
    c.caption(FLAT_CAPTIONS["11-rail-ref"], 10, 8)
    c.done()


def compose_temp(c, lf):
    # TEMP1 (anchor C20.1) and TEMP2 (anchor C21.1) are this leaf's only two
    # hier-exports -- staggered in Y (channel 2's row +30 below channel 1's,
    # not side-by-side at an identical Y) per the compose_lanes fix above:
    # `_route_io_columns` ties nets with an IDENTICAL attach Y into the same
    # sort bucket, and their resulting wire legs can overlap and merge.
    c.place("TH1", 40, 20)
    c.place("R20", 40, 40)
    c.place("C20", 65, 40)
    c.place("TH2", 40, 70)
    c.place("R21", 40, 90)
    c.place("C21", 65, 90)
    _auto_io(c, lf.hier_exports)
    c.done()


def compose_hub_link(c, lf):
    c.place("J1", 40, 45)
    c.place("D1", 75, 20)
    c.place("R1", 90, 20)
    c.place("R7", 105, 20)
    c.place("FB2", 75, 55)
    c.place("C6", 95, 55)
    # J1 pins 4/5/7 (STREAM_P/N, RSVD) are unused at Standard tier -- left
    # untouched (no net membership), so build_leaf's generic pass emits their
    # no_connect flags automatically, matching the flat baseline exactly.
    _auto_io(c, lf.hier_exports)
    c.caption(FLAT_CAPTIONS["09-hub-link"], 20, 8)
    c.done()


def compose_can(c, lf):
    c.place("U2", 45, 30)
    c.place("C4", 80, 15)
    c.place("C8", 80, 45)
    c.place("FL1", 45, 65)
    c.place("R22", 65, 65)
    c.place("R23", 85, 65)
    _auto_io(c, lf.hier_exports)
    c.caption(FLAT_CAPTIONS["06-can"], 10, 8)
    c.done()


def compose_usb(c, lf):
    # D3 (USBLC6-2SC6) carries the USB_D_P/USB_D_N hier anchors on its own
    # left pins -- placed leftmost so the io-column wire has nothing else to
    # cross (mirrors gen-module-beta.py's eps 07-usb-flash precedent).
    c.place("D3", 15, 45)
    c.place("J5", 70, 45)
    c.place("D2", 100, 20)
    c.place("FB1", 100, 45)
    c.place("D4", 100, 90)
    c.place("C9", 130, 20)
    c.place("R8", 130, 45)
    c.place("R9", 130, 90)
    _auto_io(c, lf.hier_exports)
    c.caption(FLAT_CAPTIONS["08-usb"], 20, 8)
    c.done()


def compose_input(c, lf):
    c.place("J3", 20, 40)
    c.place("J2", 90, 15)
    _grid_place(c, ["R10", "R11", "R12", "R13"], 90, 60, 1, dx=16, dy=16)
    _auto_io(c, lf.hier_exports)
    c.done()


def compose_lanes(c, lf):
    # Six per-channel ROWS (shunt + RC input filter), stacked VERTICALLY --
    # NOT side-by-side columns. MEASURED LIVE (round-4 12vhpwr wave-3b): a
    # side-by-side layout (each channel at a distinct X but the SAME Y as
    # every other channel) ties every channel's anchor pin to an IDENTICAL
    # attach-Y in `_route_io_columns`' per-side sort; its "already on this
    # row" direct-connect shortcut then draws several channels' horizontal
    # legs at that SAME Y with OVERLAPPING X ranges (each leg runs from its
    # own far-apart X out to a lane near the shared column), and KiCad treats
    # collinear overlapping segments as ONE conductor -- silently MERGING
    # every channel's IN{n}_P (and _N) into a single net (confirmed via
    # `kicad-cli sch export netlist`: all six CF{n}.1/RFH{n}.2 pins landed on
    # one "/IN1_P" node). Vertical stacking gives every channel a genuinely
    # DISTINCT Y, matching the single-part-many-pins shape this router is
    # designed for (same fix as `compose_ina`, same root cause).
    y = 30
    for i in range(1, 7):
        c.place(f"RS{i}", 60, y)
        c.place(f"RFH{i}", 20, y - 8)
        c.place(f"RFL{i}", 20, y + 8)
        c.place(f"CF{i}", 100, y)
        y += 30
    # Rail-voltage divider (R5/R6/C24): R5 taps the SAME pre-shunt node as
    # RS6/RFH6 (channel 6's SENSEP6_HI/FAN_12V), R6 to GND, C24 filters the
    # midpoint (VRAIL_DIV) out to 05-mcu's ADC. Own row, clear of the stack.
    c.place("R5", 60, y + 15)
    c.place("R6", 60, y + 30)
    c.place("C24", 100, y + 30)
    for net in lf.hier_exports:
        c.io(net, "left" if net in ("FAN_12V",) or net.endswith("_HI") else "right")
    c.caption(FLAT_CAPTIONS["02-lanes"], 10, 2)
    c.done()


def compose_ina(c, lf):
    # INA240 (cec-vendor:INA240) is native rot=0 IN-(1)/IN+(8) on the LEFT,
    # OUT(5) on the RIGHT (measured from the vendored symbol's local pin
    # table) -- exactly matching this leaf's own flow (IN_P/IN_N arrive from
    # 02-lanes on the left, ISENSEP exits to 05-mcu on the right), so NO
    # rotation is needed (unlike gen-module-beta.py's INA226 precedent,
    # which needed rot=180 for the opposite reason). VERTICAL stack (not
    # side-by-side): `_auto_io` gathers every "left"/"right" net into ONE
    # shared edge column for the WHOLE leaf, so 6 side-by-side channels would
    # force channel 5's wire to cross channels 0-4's bodies to reach that
    # shared column (measured live: "IN2_P wire passes through pin"). Stacked
    # vertically, every channel's own left/right pins already sit close to
    # the shared column, matching the single-part-many-pins shape `_auto_io`
    # is designed for.
    y = 15
    for i in range(0, 6):
        c.place(f"U1{i}", 60, y)
        c.place(f"C1{i}", 100, y - 5)
        y += 42
    for net in lf.hier_exports:
        c.io(net, "left" if net.startswith("IN") else "right")
    c.caption(FLAT_CAPTIONS["04-ina"], 10, 2)
    c.done()


def compose_mcu(c, lf):
    c.place("U1", 80, 60)
    _grid_place(c, ["C3", "C5", "C7", "R2", "SW1", "SW2"], 30, 160, 6, dx=16)
    _auto_io(c, lf.hier_exports)
    c.caption(FLAT_CAPTIONS["05-mcu"], 20, 8)
    c.note("EN/GPIO0 are BOOT/RESET straps (SW1/SW2) -- leaf-internal, "
           "name-pinned to keep their bare net names", 30, 180)
    c.done()


COMPOSERS = {
    "01-input": compose_input, "02-lanes": compose_lanes,
    "03-output": compose_output, "04-ina": compose_ina, "05-mcu": compose_mcu,
    "06-can": compose_can, "07-ldo": compose_ldo, "08-usb": compose_usb,
    "09-hub-link": compose_hub_link, "10-temp": compose_temp,
    "11-rail-ref": compose_rail_ref,
}

# GND arrays bused to one link (owner directive, round-4 plan doc item 2):
# applied as a POST-PROCESS mutation via cec_sch_gates.bus_power_ladder
# (the Wave-1 tool built for exactly this -- see its docstring) rather than
# a compose-time _ladder_column, since it is REUSE of the already-verified
# tool (same one applied to atx-24pin-rev3/hub-standard) instead of a
# hand-rolled equivalent. U1 (ESP32-S3-MINI-1) carries 24 GND pins; each
# INA240 (U10-U15) carries 4 (pins 2/3/4/7 -- REF1/REF2 tied to GND per the
# unidirectional-sensing config, spec-noted).
GND_BUS_TARGETS = {"05-mcu": ["U1"], "04-ina": [f"U1{i}" for i in range(0, 6)]}


def build(force=False):
    board_dir = BOARD_DIR
    if is_hierarchical(FLAT_SCH) and not force:
        raise SystemExit(f"{FLAT_SCH} is already hierarchical -- refusing to "
                          f"run (pass --force to regenerate anyway)")

    root_uuid = re.search(r'\(uuid\s+"([0-9a-fA-F-]+)"\)', open(FLAT_SCH).read()).group(1)
    text0 = open(FLAT_SCH).read()
    title_m = re.search(r'\(title\s+"([^"]*)"\)', text0)
    rev_m = re.search(r'\(rev\s+"([^"]*)"\)', text0)
    title = title_m.group(1) if title_m else BOARD
    rev = rev_m.group(1) if rev_m else "DRAFT"

    extracted = extract(FLAT_SCH)
    pair_sides = compute_pair_sides(extracted["pairs"])

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
        for net, sides in pair_sides.items():
            if lid in sides and net in lf.nets:
                hx[net] = ("output", lf.nets[net][0])
        lf.hier_exports = hx
        lf.powerflag_nets = ["+5VSB", "GND"] if lid == "09-hub-link" else []
        LEAVES[lid] = lf

    name_pin_nets = {}
    for name, (owner_lid, _conns) in extracted["internals"].items():
        name_pin_nets.setdefault(owner_lid, []).append(name)

    stats = {}
    for lid in LEAF_ORDER:
        lf = LEAVES[lid]
        c = C.Compose(lf, LIBS)
        COMPOSERS[lid](c, lf)

        out_path = os.path.join(board_dir, lf.filename)
        st = C.build_leaf(
            lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None,
            LIBS, PROJECT_NAME, path_prefix=f"{root_uuid}/{LEAF_SYM_UUIDS[lid]}",
            sheet_instances_path=LEAF_SYM_UUIDS[lid],
            own_uuid=LEAF_OWN_UUIDS[lid], page=str(LEAF_ORDER.index(lid) + 2),
            out_path=out_path, paper=LEAF_PAPER[lid],
            title=f"{title}: {lf.sheetname}", comment1=lf.desc,
            pwr_base=100 * (LEAF_ORDER.index(lid) + 1), layout=lf.layout,
            name_pin_nets=name_pin_nets.get(lid), rev=rev)
        n_moved, still = L.nudge_texts(out_path)
        st["nudged"], st["text_overlaps_left"] = n_moved, still
        dnp_here = extracted["dnp_refs"] & set(lf.parts)
        st["dnp_patched"] = _patch_dnp(out_path, dnp_here)
        st["labels_deduped"] = _dedupe_labels(out_path)
        for ref in GND_BUS_TARGETS.get(lid, ()):
            res = G.bus_power_ladder(out_path, ref, "GND")
            st.setdefault("gnd_bus", []).append((ref, res["applied"],
                                                  res.get("flags_removed", 0)))
        try:
            st["flags_spread"] = len(L.spread_power_flags(out_path) or ())
        except Exception:
            st["flags_spread"] = "n/a"
        try:
            st["flags_deduped"] = len(L.dedupe_power_flags(out_path) or ())
        except Exception:
            st["flags_deduped"] = "n/a"
        try:
            st["labels_flipped"] = len(L.flip_label_collisions(out_path) or ())
        except Exception:
            st["labels_flipped"] = "n/a"
        L.nudge_texts(out_path)
        stats[lid] = st
        print(f"{lf.filename}  " + "  ".join(f"{k}={v}" for k, v in st.items()))

    u = cec_sch.GRID
    leaves_for_parent = []
    for lid in LEAF_ORDER:
        lf = LEAVES[lid]
        bx, by, bw, bh = BOX[lid]
        pins = []
        for net, sides in pair_sides.items():
            if lid in sides:
                pins.append((net, lf.hier_exports[net][0], sides[lid]))
        leaves_for_parent.append({
            "id": lid, "sym_uuid": LEAF_SYM_UUIDS[lid], "filename": lf.filename,
            "sheetname": lf.sheetname, "page": str(LEAF_ORDER.index(lid) + 2),
            "x": bx * u, "y": by * u, "w": bw * u, "h": bh * u, "pins": pins,
        })

    root_path = FLAT_SCH
    parent_stats = C.build_thin_parent(
        leaves_for_parent, set(), PROJECT_NAME, root_uuid, None, root_uuid,
        out_path=root_path, title=title, paper=ROOT_PAPER, libs=LIBS,
        pwr_base=900, lane_labels=True, name_pin_nets=name_pin_nets, rev=rev,
        title_comments=(
            f"Thin parent (round-4 hierarchical conversion, Rev {rev}) -- "
            "sheet-symbol fan-out/fan-in only, no components",
            "Leaf sheets: " + ", ".join(lf.sheetname for lf in LEAVES.values()),
            "GND/+3V3/+5VSB are global power nets (per-leaf symbols); every "
            "other crossing is a real drawn sheet-pin lane carrying its "
            "exact flat-schematic net name (lane_labels)"))
    print(f"{os.path.basename(root_path)} (thin parent)  " +
          "  ".join(f"{k}={v}" for k, v in parent_stats.items()))

    # ---- ERC posture for the name-pin stubs (measured, KiCad 10.0.4 -- see
    # gen-module-beta.py's identical comment for the full false-positive
    # rationale): downgrade label_dangling to warning in THIS board's
    # .kicad_pro only; real dangling labels stay policed by audit-sch.py.
    if name_pin_nets:
        import json as _json
        pro_path = os.path.join(board_dir, f"{PROJECT_NAME}.kicad_pro")
        if os.path.isfile(pro_path):
            with open(pro_path) as fh:
                pro = _json.load(fh)
            sev = pro.setdefault("erc", {}).setdefault("rule_severities", {})
            if sev.get("label_dangling") != "warning":
                sev["label_dangling"] = "warning"
                with open(pro_path, "w") as fh:
                    _json.dump(pro, fh, indent=2)
                    fh.write("\n")
                print(f"{os.path.basename(pro_path)}: erc.rule_severities."
                      f"label_dangling -> warning (name-pin stub class)")
    return stats, parent_stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                     help="regenerate even if the root is already hierarchical")
    args = ap.parse_args(argv)
    build(force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
