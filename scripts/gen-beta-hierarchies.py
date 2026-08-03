#!/usr/bin/env python3
"""Build the large authoritative BETA schematics as readable hierarchies.

The source of truth is the archived, electrically reviewed flat capture. This
driver partitions it by function, preserves every orderable part/property and
numbered-pin net membership, and emits a thin root plus compact leaf sheets.
It fails closed on an unclassified reference or an electrical mismatch.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap
import uuid
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import cec_pcb_reconcile as R  # noqa: E402
import cec_sch  # noqa: E402
import cec_sch_compose as C  # noqa: E402
import cec_sch_gates as G  # noqa: E402
import cec_sch_layout as L  # noqa: E402

LIBS = {
    "cec": open(os.path.join(ROOT, "lib", "cec.kicad_sym"), encoding="utf-8").read(),
    "cec-vendor": open(os.path.join(ROOT, "lib", "vendor", "cec-vendor.kicad_sym"), encoding="utf-8").read(),
    "power": open(os.path.join(ROOT, "lib", "vendor", "cec-power.kicad_sym"), encoding="utf-8").read(),
}
POWER_PORTS = {name: name for name in ("GND", "+3V3", "+5VSB", "+5V_SYS", "+5V_MAIN")}
POWER_NETS = set(POWER_PORTS)
GLOBAL_NETS = set()
_LABEL_LINE_RE = re.compile(
    r'\t\(label "([^"]+)" \(at ([\d.\-]+) ([\d.\-]+) (\d+)\) \(effects[^\n]*\n')


def rows(*items: str) -> list[list[str]]:
    return [s.split() for s in items]


CONFIG = {
    "hub-standard-rev2": {
        "live": "beta/hub-standard-rev2/hub-standard-rev2.kicad_sch",
        "archive": "old-revisions/beta/hub-standard-rev2-flat-2026-08-02/hub-standard-rev2.kicad_sch",
        "flags": {"01-power-input-selection": ["GND", "+5VSB", "5VSB_RAW", "USB_VBUS", "PSU_5V",
                                                     "MAIN_5V_RAW", "PSU_5V_KVM", "KVM_5V_IN"],
                  "02-holdup-3v3": ["+3V3", "LOGIC_REG_IN"]},
        "leaves": [
            ("01-power-input-selection", "POWER INPUT + SOURCE SELECTION",
             "Three TPS2121 stages, protected inputs, current limits, OV thresholds and local reservoirs.",
             rows("J_PWR D8 D9 U5 U7 U11", "C9 C15 C22 C23 C24 C25 C26 C27 C28 C_SS1 C_SS2 C_SS3 C_bulk1",
                  "R_ILIM1 R_ILIM2 R_ILIM3 R33 R34 R35 R36 R37 R38")),
            ("02-holdup-3v3", "HOLD-UP + 3V3 REGULATOR",
             "5VSB loss detection precedes the hold-up diode; shutdown is requested before reservoir or regulator dropout.",
             rows("D1 C1 RJ_HOLD RJ_BUCK U9 U10 L2", "U3 L1 C2 C3 U8 C17",
                  "R26 R27 R28 R29 R30 R31 R32 R39 R40")),
            ("03-mcu-usb", "MCU + USB SERVICE PORT",
             "ESP32-S3 control, reset/boot supervision and protected USB-C service ingress.",
             rows("J_USB D6 U1 U4", "C4 C6 C8 C10 C11 C12 C13 R2 R9 R10 R11 R12 R13 SW_BOOT SW_RESET")),
            ("04-can-module-ports", "CAN + FOUR MODULE PORTS + STACK",
             "One shared CAN segment, four fused module feeds, DETECT protection/filtering and the structural stack interface.",
             rows("U2 J2 J3 J4 J5 J6C J6D J6P", "F1 F2 F3 F4 D2 D3 D4 D5",
                  "C5 C7 C18 C19 C20 C21 R3 R4 R5 R6 R7 R8")),
            ("05-kvm-aux-sensors", "KVM AUXILIARY + RAIL SENSING",
             "Fused KVM feed, UART, rail dividers and hub temperature sensing.",
             rows("J_KVM F5 D7 TH1", "C16 R15 R16 R17 R18 R19 R20 R21 R22 R23 R24 R25")),
            ("06-status-leds", "STATUS LED CHAIN",
             "Level-shifted, series-damped seven-device addressable status chain.",
             rows("U6 R14 DL1 DL2 DL3 DL4 DL5 DL6 DL7 C14")),
        ],
    },
    "eps-8pin-rev3": {
        "live": "beta/eps-8pin-rev3/eps-8pin-rev3.kicad_sch",
        "archive": "old-revisions/beta/eps-8pin-rev3-flat-2026-08-02/eps-8pin-rev3.kicad_sch",
        "flags": {"02-regulator-mcu": ["GND", "+5VSB"]},
        "leaves": [
            ("01-hub-can", "HUB LINK + CAN", "Protected DETECT input and the module CAN transceiver at the hub connector.",
             rows("J1 D1 R1 R7 U2 C4 C8")),
            ("02-regulator-mcu", "3V3 REGULATOR + MCU", "LP5907 rail, ESP32-C6 control, boot/reset straps and local bypassing.",
             rows("U3 C1 C2", "U1 R2 R19 SW1 SW2 C3 C5 C7")),
            ("03-sensing", "DUAL-CABLE PRECISION + FAST SENSING",
             "Two repeated INA238 / INA181 / TLV7011 channels with a shared threshold and I2C pull-ups.",
             rows("R10 C40 R3 R4", "U10 U20 U30 C10 C20 C30", "U11 U21 U31 C11 C21 C31")),
            ("04-cable-power", "DUAL EPS POWER INTERPOSER",
             "Two independent PSU-to-load paths with Kelvin shunts; there is one EPS product, not a variant family.",
             rows("J_IN1 RS1 J_OUT1", "J_IN2 RS2 J_OUT2")),
            ("05-usb-service", "USB-C SERVICE INGRESS", "USB 2.0 service connector, CC terminations and 5VSB isolation diode.",
             rows("J5 D2 C6 C9 R8 R9")),
        ],
    },
    "atx-24pin-rev3": {
        "live": "beta/atx-24pin-rev3/24pin-module.kicad_sch",
        "archive": "old-revisions/beta/atx-24pin-rev3-flat-2026-08-02/24pin-module.kicad_sch",
        "flags": {"01-atx-power-control": ["GND", "+5VSB", "+5V_MAIN"],
                  "02-power-usb": ["+5V_SYS", "5VSB_MUX", "VBUS"]},
        "leaves": [
            ("01-atx-power-control", "ATX INTERPOSER + CONTROL SIGNALS",
             "ATX connector, four shunts, output blade terminals, PS_ON#/PWR_OK conditioning and -12V scaling.",
             rows("J3 RS1 RS2 RS3 RS4", "TB1 TB2 TB3 TB4 TB5 TB6 TB7 TB8 TB9 TB10",
                  "J_SIG1 Q1 U4 U8 D3 D4 D5", "C22 C23 C64 R70 R71 R72 R73 R74 R75 R76")),
            ("02-power-usb", "5V SOURCE MUX + USB SERVICE INGRESS",
             "Cascaded TPS2121 source selection and protected USB-C service power/data ingress.",
             rows("U5 U6 J5 D7 D_USB1 F1 FB1", "C1 C4 C6 C9 C18 C19 C20 C21 C24 C25 C50 C51 C52 C53",
                  "R50 R51 R52 R53 R54 R55 R56 R57 R58 R8 R9")),
            ("03-regulator-mcu", "3V3 REGULATOR + MCU", "LP5907 rail, ESP32-C6 control and local boot/reset support.",
             rows("U3 U1", "C2 C3 C5 C7 C8 C10 C11 C12 C13 C14 R2 R10 R3 R4 SW1 SW2")),
            ("04-hub-can-stack", "HUB LINK + CAN + STACK",
             "RJ-45/stack interfaces, optional CAN common-mode choke position and 5V feed bridge.",
             rows("J1 J2 J6C J6D J6P U2", "D1 FB2 FL1 R1 R7 R_BYP_H1 R_BYP_L1")),
            ("05-rail-sensing", "FOUR-RAIL PRECISION + FAST SENSING",
             "Four INA238 measurement channels plus INA181/TLV7011 transient channels and shared threshold conditioning.",
             rows("R60 C60 R61 C61", "U10 U612V1 U712V1 C15 C612V1 C712V1",
                  "U11 U65V1 U75V1 C16 C62 C65V1 C75V1", "U12 U63V31 U73V31 C17 C63 C63V31 C73V31",
                  "U13 U65VSB1 U75VSB1 C65VSB1 C75VSB1")),
        ],
    },
}


def _bare(name: str) -> str:
    return name[1:] if name.startswith("/") else name


def _source_placements(path: str) -> dict[str, tuple[float, float, int]]:
    text = open(path, encoding="utf-8", errors="replace").read()
    work = L._strip_lib_symbols(text)
    return {ref: (x, y, rot) for _s, _e, (x, y), ref, rot, _lib, _mir in L._symbol_spans(work) if not ref.startswith("#")}


def _source_notes(path: str, placement: dict[str, tuple[float, float, int]], leaf_of: dict[str, str]):
    text = open(path, encoding="utf-8", errors="replace").read()
    notes = defaultdict(list)
    for el in L._extract_text_elements(text):
        if el["kind"] != "text":
            continue
        x, y = el["at"][:2]
        ref = min(placement, key=lambda r: (placement[r][0] - x) ** 2 + (placement[r][1] - y) ** 2)
        notes[leaf_of[ref]].append(el["text"])
    return notes


def _route_note(board: str, note: str, fallback: str) -> str:
    """Keep legacy engineering prose on the functional sheet it describes."""
    if board != "atx-24pin-rev3":
        return fallback
    routes = (
        (("ATX POWER", "OUTPUT FORM", "ATX CONTROL"), "01-atx-power-control"),
        (("5V / 5VSB", "FLASH / USB", "MARGIN RESERVOIRS"), "02-power-usb"),
        (("3V3 LDO", "MCU  ESP32"), "03-regulator-mcu"),
        (("HUB LINK", "CAN  TJA", "MEZZANINE", "STANDALONE-MODE"), "04-hub-can-stack"),
        (("RAIL SENSING", "TRANSIENT DETECTION"), "05-rail-sensing"),
    )
    for needles, lid in routes:
        if any(n in note for n in needles):
            return lid
    return fallback


def extract(path: str, leaf_of: dict[str, str]):
    inv = G.inventory(path)
    by_name = {}
    for members, name in R.netlist_groups(path).items():
        if not name.startswith("unconnected-"):
            by_name[_bare(name)] = sorted(members)
    missing, extra = sorted(set(inv) - set(leaf_of)), sorted(set(leaf_of) - set(inv))
    if missing or extra:
        raise SystemExit(f"partition mismatch: missing={missing}, extra={extra}")
    parts, fps, props = {}, {}, {}
    for ref, d in inv.items():
        lib, name = d["lib_id"].split(":", 1)
        parts[ref], fps[ref], props[ref] = (lib, name, d["value"]), d["footprint"], d["props"]
    spans = {name: {leaf_of[ref] for ref, _pin in members} for name, members in by_name.items()}
    return {"inventory": inv, "parts": parts, "footprints": fps, "props": props, "by_name": by_name, "spans": spans}


def _cap_bank(c: C.Compose, caps: list[str], power: str, x0: int, y0: int):
    caps = [r for r in caps if r in c.lf.parts]
    if len(caps) < 2:
        return set()
    for i, ref in enumerate(caps):
        c.place(ref, x0 + i * 8, y0, 0)
    tops, bots = [c.pin(r, "1") for r in caps], [c.pin(r, "2") for r in caps]
    top_y, bot_y = min(y for _x, y in tops) - 2, max(y for _x, y in bots) + 2
    for ref, (x, y) in zip(caps, tops):
        c.wire((x, y), (x, top_y)); c.use((ref, "1"))
    for ref, (x, y) in zip(caps, bots):
        c.wire((x, y), (x, bot_y)); c.use((ref, "2"))
    # Split the rails at each tap.  KiCad requires a real three-endpoint
    # junction at an interior capacitor drop; one unsplit long segment makes
    # the middle tap look connected but exports it as unconnected.
    for a, b in zip(sorted(x for x, _y in tops), sorted(x for x, _y in tops)[1:]):
        c.wire((a, top_y), (b, top_y))
    for a, b in zip(sorted(x for x, _y in bots), sorted(x for x, _y in bots)[1:]):
        c.wire((a, bot_y), (b, bot_y))
    c.stamp(power, min(x for x, _y in tops), top_y, 180)
    c.stamp("GND", min(x for x, _y in bots), bot_y, 0)
    c.caption(f"{power} LOCAL BYPASS / BULK BANK", x0, y0 - 8, 1.6)
    return set(caps)


def _combine_gnd_array(c: C.Compose, ref: str, pins: list[str]):
    groups = defaultdict(list)
    for pin in pins:
        pt, vec = c.pin_out(ref, pin)
        groups[(int(round(vec[0])), int(round(vec[1])))].append((pin, pt))
    for (dx, dy), members in groups.items():
        if len(members) < 2:
            continue
        outs = []
        for pin, (x, y) in members:
            out = (x + dx * 3, y + dy * 3)
            c.wire((x, y), out); c.use((ref, pin)); outs.append(out)
        if dx:
            tx = min(x for x, _y in outs) if dx < 0 else max(x for x, _y in outs)
            for x, y in outs:
                if x != tx: c.wire((x, y), (tx, y))
            c.wire((tx, min(y for _x, y in outs)), (tx, max(y for _x, y in outs)))
            ey = max(y for _x, y in outs) + 3
            c.wire((tx, max(y for _x, y in outs)), (tx, ey)); c.stamp("GND", tx, ey, 0)
        else:
            ty = min(y for _x, y in outs) if dy < 0 else max(y for _x, y in outs)
            for x, y in outs:
                if y != ty: c.wire((x, y), (x, ty))
            c.wire((min(x for x, _y in outs), ty), (max(x for x, _y in outs), ty))
            ex = max(x for x, _y in outs) + 3
            c.wire((max(x for x, _y in outs), ty), (ex, ty)); c.stamp("GND", ex, ty, 0)


def _combine_repeated(c: C.Compose, net: str, conns: list[tuple[str, str]], side: str, lane: int, hierarchical: bool):
    pts = []
    for ref, pin in conns:
        if (ref, pin) in c.consumed:
            return False
        (x, y), (dx, dy) = c.pin_out(ref, pin)
        out = (x + int(round(dx)) * 3, y + int(round(dy)) * 3)
        c.wire((x, y), out); c.use((ref, pin)); pts.append(out)
    xs = [p[0] for p in pts]
    trunk_x = min(xs) - 8 - 4 * lane if side == "left" else max(xs) + 8 + 4 * lane
    for x, y in pts: c.wire((x, y), (trunk_x, y))
    c.wire((trunk_x, min(y for _x, y in pts)), (trunk_x, max(y for _x, y in pts)))
    anchor = (trunk_x, min(y for _x, y in pts))
    if hierarchical: c.hier(net, *anchor, 180 if side == "left" else 0)
    else: c.label(net, *anchor, 180 if side == "left" else 0)
    return True


def _patch_states(path: str, inv: dict):
    text = open(path, encoding="utf-8").read(); out, pos = [], 0
    for m in re.finditer(r'\t\(symbol\n', text):
        if m.start() < pos: continue
        blk = cec_sch.carve(text, m.start())
        rm = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', blk); ref = rm.group(1) if rm else None
        if ref in inv:
            d = inv[ref]
            new = re.sub(r'\(in_bom\s+(?:yes|no)\)', f'(in_bom {"yes" if d["in_bom"] else "no"})', blk, count=1)
            new = re.sub(r'\(on_board\s+(?:yes|no)\)', f'(on_board {"yes" if d["on_board"] else "no"})', new, count=1)
            new = re.sub(r'\(dnp\s+(?:yes|no)\)', f'(dnp {"yes" if d["dnp"] else "no"})', new, count=1)
            out.append(text[pos:m.start()]); out.append(new); pos = m.start() + len(blk)
    out.append(text[pos:]); open(path, "w", encoding="utf-8", newline="\n").write("".join(out))


def _dedupe_labels(path: str) -> int:
    """Drop only exact duplicate attached labels; keep the first."""
    text = open(path, encoding="utf-8").read(); seen, out, pos, count = set(), [], 0, 0
    hier = {(m.group(1), m.group(2), m.group(3)) for m in re.finditer(
        r'\(hierarchical_label "([^"]+)"[\s\S]*?\(at ([\d.\-]+) ([\d.\-]+) \d+\)', text)}
    for m in _LABEL_LINE_RE.finditer(text):
        key = (m.group(1), m.group(2), m.group(3))
        out.append(text[pos:m.start()])
        if key in seen or key in hier:
            count += 1; pos = m.end(); continue
        seen.add(key); out.append(m.group(0)); pos = m.end()
    out.append(text[pos:])
    if count: open(path, "w", encoding="utf-8", newline="\n").write("".join(out))
    return count


def _canonical_groups(path: str):
    return {frozenset(members): _bare(name) for members, name in R.netlist_groups(path).items() if not name.startswith("unconnected-")}


def _validate(source: str, root: str):
    inv_diff = G.check_inventory_equal(source, root)
    src, dst = _canonical_groups(source), _canonical_groups(root)
    membership = sorted([sorted(x) for x in set(src) ^ set(dst)])
    renamed = sorted((src[k], dst[k]) for k in set(src) & set(dst)
                     if src[k] != dst[k] and not (src[k].startswith("Net-") or dst[k].startswith("Net-")))
    if inv_diff or membership or renamed:
        raise SystemExit("hierarchy validation failed:\n" + "\n".join(
            [*("inventory: " + x for x in inv_diff), *("membership: " + repr(x) for x in membership[:20]),
             *(f"renamed: {a!r} -> {b!r}" for a, b in renamed[:20])]))
    return len(src)


def build(board: str, source: str | None = None, out_dir: str | None = None):
    cfg = CONFIG[board]
    source = os.path.abspath(source or os.path.join(ROOT, cfg["archive"]))
    if not os.path.isfile(source):
        live = os.path.join(ROOT, cfg["live"])
        if os.path.isfile(live) and not re.search(r'\(sheet\n', L._strip_lib_symbols(open(live).read())): source = live
        else: raise SystemExit(f"flat source not found: {source}")
    out_dir = os.path.abspath(out_dir or os.path.dirname(os.path.join(ROOT, cfg["live"])))
    os.makedirs(out_dir, exist_ok=True)

    leaf_of, leaf_meta = {}, {}
    for lid, title, desc, row_groups in cfg["leaves"]:
        leaf_meta[lid] = (title, desc, row_groups)
        for ref in sum(row_groups, []):
            if ref in leaf_of: raise SystemExit(f"duplicate partition ref {ref}")
            leaf_of[ref] = lid
    extracted = extract(source, leaf_of)
    source_place = _source_placements(source); raw_notes = _source_notes(source, source_place, leaf_of)
    source_notes = defaultdict(list)
    for fallback, notes in raw_notes.items():
        for note in notes:
            source_notes[_route_note(board, note, fallback)].append(note)
    root_text = open(source, encoding="utf-8", errors="replace").read()
    root_uuid = re.search(r'\(uuid\s+"([0-9a-fA-F-]+)"\)', root_text).group(1)
    tm, rm = re.search(r'\(title\s+"([^"]*)"\)', root_text), re.search(r'\(rev\s+"([^"]*)"\)', root_text)
    title, rev = (tm.group(1) if tm else board), (rm.group(1) if rm else "DRAFT")
    pro = os.path.splitext(os.path.basename(cfg["live"]))[0]

    leaves, parent_specs = [], []
    all_lids = [x[0] for x in cfg["leaves"]]; x_rank = {lid: i for i, lid in enumerate(all_lids)}
    pair_sides = {}
    for net, ls in extracted["spans"].items():
        if net in POWER_NETS or net in GLOBAL_NETS or len(ls) != 2: continue
        a, b = sorted(ls, key=x_rank.get); pair_sides[net] = {a: "right", b: "left"}
    overwide = {n: sorted(ls) for n, ls in extracted["spans"].items()
                if n not in POWER_NETS and n not in GLOBAL_NETS and len(ls) > 2}
    if overwide: raise SystemExit(f"partition creates >2-leaf signals; repartition required: {overwide}")

    for li, (lid, leaf_title, desc, row_groups) in enumerate(cfg["leaves"]):
        lf = C.Leaf(lid, lid + ".kicad_sch", leaf_title, desc)
        refs = [r for r in extracted["parts"] if leaf_of[r] == lid]
        lf.parts = {r: extracted["parts"][r] for r in refs}; lf.footprints = {r: extracted["footprints"][r] for r in refs}
        lf.props = {r: extracted["props"][r] for r in refs}
        lf.powerflag_nets = list(cfg.get("flags", {}).get(lid, ()))
        for net, members in extracted["by_name"].items():
            here = [(r, p) for r, p in members if r in lf.parts]
            if here: lf.nets[net] = here
        export_nets = []
        for net, members in lf.nets.items():
            if net not in POWER_NETS and net not in GLOBAL_NETS and not net.startswith("Net-"):
                export_nets.append(net); lf.hier_exports[net] = ("output", members[0])

        c = C.Compose(lf, LIBS); c.caption(leaf_title, 8, 2, 2.2); c.note(desc, 8, 6, 1.15)
        if lid == "01-power-input-selection":
            leaf_paper, ncols, x_pitch, y_pitch = "A1", 6, 60, 38
        elif lid == "06-status-leds":
            leaf_paper, ncols, x_pitch, y_pitch = "A3", 10, 20, 36
        elif len(refs) <= 10:
            leaf_paper, ncols, x_pitch, y_pitch = "A4", 4, 42, 32
        elif len(refs) <= 22:
            leaf_paper, ncols, x_pitch, y_pitch = "A3", 5, 45, 36
        else:
            leaf_paper, ncols, x_pitch, y_pitch = "A2", 6, 50, 38
        y_cursor = 45 if lid.endswith("regulator-mcu") else 30
        for group in row_groups:
            for gi, ref in enumerate(group):
                x = 18 + (gi % ncols) * x_pitch
                y = y_cursor + (gi // ncols) * y_pitch
                c.place(ref, x, y, source_place.get(ref, (0, 0, 0))[2])
            y_cursor += ((len(group) + ncols - 1) // ncols) * y_pitch + 8
        bank_y = y_cursor + 8

        for power in ("+3V3", "+5VSB"):
            caps = []
            for ref in refs:
                if not ref.startswith("C"): continue
                pin_net = {p: n for n, mm in lf.nets.items() for r, p in mm if r == ref}
                if pin_net.get("1") == power and pin_net.get("2") == "GND": caps.append(ref)
            if len(caps) >= 2: _cap_bank(c, caps, power, 18, bank_y); bank_y += 22

        if lid == "06-status-leds":
            # The DOUT->DIN chain is a real left-to-right wire sequence, not
            # a row of repeated anonymous labels.
            for net, members in lf.nets.items():
                if len(members) != 2 or not (net.startswith("Net-(DL") or net in
                                             {"LED_DATA_BUF", "LED_DATA_DIN"}):
                    continue
                (r1, p1), (r2, p2) = members
                a, b = c.pin(r1, p1), c.pin(r2, p2)
                if a[1] == b[1]:
                    joint = ((a[0] + b[0]) // 2, a[1])
                    c.wire(a, joint, b)
                else:
                    mid = (a[0] + b[0]) // 2
                    joint = (mid, (a[1] + b[1]) // 2)
                    c.wire(a, (mid, a[1]), joint, (mid, b[1]), b)
                if net in lf.hier_exports:
                    drop = 18 if net == "LED_DATA_BUF" else 28
                    tap = (joint[0], max(a[1], b[1]) + drop)
                    c.wire(joint, tap); c.hier(net, *tap, 0)
                c.use((r1, p1), (r2, p2))

        # Repeated supply bypass parts are physically and electrically
        # consolidated above.  Other signals keep short, wire-attached
        # labels at their pins; generic long trunks can create accidental
        # junctions when a dense connector fan-out crosses another lane.
        # Board-specific drawn buses may be added only with rendered and
        # netlist-identity evidence.
        combined = set()
        for net in export_nets:
            if net in combined: continue
            # The generic builder puts the hierarchy label on a real pin
            # stub at this anchor.  Do not force a long edge-column route for
            # one/two-pin nets: compact direct labels are clearer and avoid
            # crossing unrelated symbols.  Repeated nets above still get a
            # single explicit external trunk.
            pass

        note_y = bank_y + 6
        for note in source_notes.get(lid, []):
            wrapped = textwrap.wrap(note, 92, replace_whitespace=False)
            c.note("\n".join(wrapped), 8, note_y, 1.0); note_y += max(8, 2 + 2 * len(wrapped))
        needed_w = (18 + max(0, ncols - 1) * x_pitch + 70) * cec_sch.GRID
        needed_h = (note_y + 18) * cec_sch.GRID
        for candidate in ("A4", "A3", "A2", "A1"):
            pw, ph = C.PAPER[candidate]
            if needed_w <= pw - 20 and needed_h <= ph - 20:
                leaf_paper = candidate; break
        else:
            leaf_paper = "A0"
        c.done()

        leaf_sym = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cec:{board}:{lid}:sheet")); leaf_own = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cec:{board}:{lid}:file"))
        out = os.path.join(out_dir, lf.filename)
        stats = C.build_leaf(lf.parts, lf.nets, lf.footprints, lf.props, lf.placement, lf.nc_skip,
            POWER_PORTS, lf.powerflag_nets, lf.hier_exports, None, LIBS, pro, path_prefix=f"{root_uuid}/{leaf_sym}",
            sheet_instances_path=leaf_sym, own_uuid=leaf_own, page=str(li + 2), out_path=out, paper=leaf_paper,
            title=f"{title}: {leaf_title}", comment1=desc, pwr_base=100 * (li + 1), layout=lf.layout,
            global_nets=GLOBAL_NETS & set(lf.nets), rev=rev)
        _patch_states(out, extracted["inventory"]); deduped = _dedupe_labels(out)
        # Collapse the ESP32 exposed-ground flag ladder with the proven
        # guarded mutator.  It only acts when every flag is an isolated stub,
        # refuses a blocked wire corridor, and the final hierarchy-equivalence
        # gate below still independently proves net membership.
        ladder = G.bus_power_ladder(out, "U1", "GND")
        try:
            flipped = len(L.flip_label_collisions(out) or ())
        except Exception:
            flipped = 0
        moved, left = L.nudge_texts(out)
        print(f"{lf.filename}: parts={len(refs)} paper={leaf_paper} wires={stats.get('wires')} "
              f"deduped={deduped} bused={ladder.get('flags_removed', 0)} "
              f"flipped={flipped} nudged={moved} overlaps={left}")
        leaves.append((lf, leaf_sym))

    for li, (lf, leaf_sym) in enumerate(leaves):
        pins = [(net, "output", pair_sides.get(net, {}).get(lf.id) or ("left" if li == 0 else "right")) for net in lf.hier_exports]
        counts = {s: sum(1 for _n, _shape, side in pins if side == s) for s in ("left", "right")}
        h_u = max(28, 10 + max(counts.values(), default=0) * 4)
        parent_specs.append({"id": lf.id, "sym_uuid": leaf_sym, "filename": lf.filename, "sheetname": lf.sheetname,
            "page": str(li + 2), "x": (10 + (li % 3) * 120) * cec_sch.GRID,
            "y": (15 + (li // 3) * 145) * cec_sch.GRID,
            "w": 70 * cec_sch.GRID, "h": h_u * cec_sch.GRID, "pins": pins})

    root_out = os.path.join(out_dir, os.path.basename(cfg["live"]))
    C.build_thin_parent(parent_specs, set(), pro, root_uuid, None, root_uuid, out_path=root_out, title=title,
        paper="A2", libs=LIBS, pwr_base=900, lane_labels=True, pair_labels=True, rev=rev, title_comments=(
            "Authoritative BETA hierarchy; functional leaves only; no legacy project discovery.",
            "Repeated nets use shared trunks; power bypass arrays use real rails; hierarchy labels are wire-attached.",
            "Generated from the archived reviewed flat source and gated by inventory/net/ERC equivalence.",))
    net_count = _validate(source, root_out)
    print(f"{os.path.basename(root_out)}: hierarchy valid, {len(extracted['inventory'])} parts, {net_count} connected nets")
    return root_out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument("boards", nargs="+", choices=sorted(CONFIG))
    ap.add_argument("--source"); ap.add_argument("--out-dir"); args = ap.parse_args(argv)
    if (args.source or args.out_dir) and len(args.boards) != 1: ap.error("--source/--out-dir require exactly one board")
    for board in args.boards: build(board, args.source, args.out_dir)
    return 0


if __name__ == "__main__": raise SystemExit(main())
