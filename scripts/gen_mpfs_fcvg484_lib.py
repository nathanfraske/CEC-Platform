#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Generate the PolarFire SoC MPFS095T FCVG484 KiCad symbol + footprint.
#
# Per docs/enterprise-requirements/board-program/kicad-intake-manifest-2026-07-02.md
# item #8 and hubs/hub-enterprise/SCHEMATIC-PLAN.md section 4: this is a
# 484-ball, 0.8mm-pitch BGA with no EasyEDA/LCSC-native listing, so per
# CLAUDE.md's KiCad-environment convention for this class of part it is
# SCRIPT-GENERATED from the packaging user guide's ball map, never hand-drawn.
#
# Reads the cached ball-map table (lib/vendor-data/mpfs-fcvg484-pins.csv --
# see that file's header for full sourcing/provenance) and emits:
#   lib/cec-ent-compute.kicad_sym
#       ONE multi-unit symbol "MPFS095T_FCVG484", units split by function:
#       fabric HSIO bank 0, fabric GPIO bank 1, MSS I/O (banks 2+4),
#       JTAG/System Controller (bank 3), MSS SGMII/MSS-Ethernet (bank 5),
#       MSS DDR (bank 6), SerDes/XCVR0 (annotated NC on Core/TC parts and on
#       the SerDes-free land), and Power (VDD/VDDI/VSS, stacked-pin
#       representation for the many same-net balls).
#   lib/cec-ent-compute.pretty/BGA-484_19x19mm_P0.8mm_MPFS_FCVG484.kicad_mod
#       22x22 ball grid, 0.8mm pitch, 0.4mm pad / 0.5mm NSMD solder-mask
#       opening (Microchip packaging UG section 7 Table 7-1), 19x19mm body.
#
# This script does NOT touch any other library file, lib table, or board.
#
# Fails loudly (SystemExit, nonzero exit) rather than silently guessing if:
#   - the cached table does not have exactly 484 rows,
#   - any ball designator is duplicated,
#   - the 484 designators are not exactly the full 22(cols 1-22) x
#     22(rows A..AB, JEDEC-skip I/O/Q/S/Z) grid (missing or extra balls),
#   - a row references a category this script does not know how to place.
#
#   python3 scripts/gen_mpfs_fcvg484_lib.py
import csv
import os
import sys

ROOTDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOTDIR, "lib", "vendor-data", "mpfs-fcvg484-pins.csv")
SYM_OUT = os.path.join(ROOTDIR, "lib", "cec-ent-compute.kicad_sym")
FP_DIR = os.path.join(ROOTDIR, "lib", "cec-ent-compute.pretty")
FP_NAME = "BGA-484_19x19mm_P0.8mm_MPFS_FCVG484"

SYMBOL_NAME = "MPFS095T_FCVG484"

DATASHEET_URL = (
    "https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/"
    "ProductDocuments/DataSheets/PolarFire-SoC-Datasheet-DS00004248.pdf"
)
PACKAGING_UG_URL = (
    "https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/"
    "ProductDocuments/UserGuides/"
    "microchip_polarfire_soc_fpga_packaging_and_pin_descriptions_user_guide_vb.pdf"
)

# JEDEC BGA row letters, skipping I, O, Q, S, Z -- 22 rows for a 22x22 grid.
ROW_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N",
               "P", "R", "T", "U", "V", "W", "Y", "AA", "AB"]
N_COLS = 22
PITCH = 0.8            # mm, FCVG484 (spec §13.1 land is SerDes-free/part-agnostic; ball pitch is package-fixed)
BODY_SIZE = 19.0        # mm, FCVG484 package body (Microchip packaging UG Table 1-10)
PAD_DIA = 0.4           # mm, FCVG package recommended ball pad diameter (UG Table 7-1)
MASK_OPENING = 0.5      # mm, FCVG package recommended solder mask opening, NSMD (UG Table 7-1)
MASK_MARGIN = round((MASK_OPENING - PAD_DIA) / 2, 3)   # per-side NSMD margin

# Unit order + display label + pin electrical type. "power" units get the
# stacked/hidden-duplicate treatment; everything else is a flat signal bank.
UNITS = [
    ("HSIO_BANK0", "Fabric HSIO Bank 0", "bidirectional"),
    ("GPIO_BANK1", "Fabric GPIO Bank 1", "bidirectional"),
    ("MSSIO", "MSS I/O (Banks 2 + 4)", "bidirectional"),
    ("JTAG_SYSCTRL", "JTAG / System Controller (Bank 3)", "bidirectional"),
    ("SGMII", "MSS SGMII / MSS-Ethernet (Bank 5)", "bidirectional"),
    ("MSS_DDR", "MSS DDR (Bank 6)", "bidirectional"),
    ("XCVR", "SerDes / XCVR0 -- NC on Core/TC parts and on the SerDes-free land", "bidirectional"),
    ("POWER", "Power (VDD / VDDI / VSS)", "power_in"),
]
UNIT_CODES = [u[0] for u in UNITS]

GRID = 1.27     # schematic pin-stack pitch, matches cec_sch.py's convention
STUB = 5.08     # pin length


def load_balls():
    with open(CSV_PATH, encoding="utf-8") as f:
        data_lines = [ln for ln in f if not ln.startswith("#")]
    reader = csv.DictReader(data_lines)
    rows = list(reader)
    return rows


def validate(rows):
    if len(rows) != 484:
        raise SystemExit(
            f"FATAL: expected exactly 484 balls in {CSV_PATH}, got {len(rows)}")

    seen = {}
    for r in rows:
        d = r["designator"]
        if not d:
            raise SystemExit(f"FATAL: empty designator in row {r!r}")
        if d in seen:
            raise SystemExit(
                f"FATAL: duplicate designator {d!r} -- rows {seen[d]!r} and {r!r}")
        seen[d] = r

    expected = {f"{letter}{col}" for letter in ROW_LETTERS for col in range(1, N_COLS + 1)}
    got = set(seen)
    missing = expected - got
    extra = got - expected
    if missing or extra:
        raise SystemExit(
            "FATAL: ball grid mismatch vs the expected 22x22 JEDEC grid.\n"
            f"  missing ({len(missing)}): {sorted(missing)[:15]}\n"
            f"  extra   ({len(extra)}): {sorted(extra)[:15]}")

    unknown_cats = {r["category"] for r in rows} - set(UNIT_CODES)
    if unknown_cats:
        raise SystemExit(
            f"FATAL: row(s) reference categor(y/ies) this script does not "
            f"know how to place: {sorted(unknown_cats)}. Known: {UNIT_CODES}")

    print(f"[validate] 484 unique designators, full 22x22 grid, "
          f"{len(unknown_cats)} unknown categories -- OK")


# --------------------------------------------------------------------------
# Symbol (.kicad_sym) emission
# --------------------------------------------------------------------------

def _prop(name, value, x, y, hide=True, extra=""):
    hide_s = "\t\t\t\t\t(hide yes)\n" if hide else ""
    return (f'\t\t\t(property "{name}" "{value}"\n'
            f'\t\t\t\t(at {x} {y} 0)\n'
            f'\t\t\t\t(effects\n'
            f'\t\t\t\t\t(font\n'
            f'\t\t\t\t\t\t(size 1.27 1.27)\n'
            f'\t\t\t\t\t)\n'
            f'{extra}'
            f'{hide_s}'
            f'\t\t\t\t)\n'
            f'\t\t\t)\n')


def emit_symbol(rows):
    by_unit = {code: [] for code in UNIT_CODES}
    for r in rows:
        by_unit[r["category"]].append(r)
    # deterministic within-unit order (already alphabetical by designator from
    # the cached CSV; re-sort defensively so re-runs are byte-identical
    # regardless of csv row order).
    for code in UNIT_CODES:
        by_unit[code].sort(key=lambda r: r["designator"])

    out = []
    out.append("(kicad_symbol_lib\n")
    out.append("\t(version 20241209)\n")
    out.append('\t(generator "gen_mpfs_fcvg484_lib")\n')
    out.append(f'\t(symbol "{SYMBOL_NAME}"\n')
    out.append("\t\t(exclude_from_sim no)\n")
    out.append("\t\t(in_bom yes)\n")
    out.append("\t\t(on_board yes)\n")
    out.append(_prop("Reference", "U", 0, 12.7, hide=False))
    out.append(_prop("Value", SYMBOL_NAME, 0, 10.16, hide=False))
    out.append(_prop("Footprint", f"cec-ent-compute:{FP_NAME}", 0, 7.62))
    out.append(_prop("Datasheet", DATASHEET_URL, 0, 5.08))
    out.append(_prop(
        "Description",
        "PolarFire SoC FPGA, 484-ball FCVG484 (19x19mm, 0.8mm pitch) BGA -- "
        "part-agnostic SerDes-free land: population baseline MPFS095TC "
        "(Core), MPFS095TS (S-grade Athena/HS) fits the same footprint, and "
        "the land is shared across the 025/095/160/250 density ladder in "
        "this package (Microchip: devices in the same package type are pin "
        "compatible).", 0, 2.54))
    out.append(_prop(
        "MPN",
        "MPFS095TC-FCVG484x (Core baseline) / MPFS095TS-FCVG484x (S-grade "
        "Athena, HS population option) -- part-agnostic FCVG484 land, "
        "025/095/160/250T(S) ladder shares this footprint; exact "
        "temp-grade/speed suffix TBD at buy time", 0, 0))
    out.append(_prop("Manufacturer", "Microchip Technology", 0, -2.54))
    out.append(_prop(
        "ki_keywords",
        "FPGA SoC RISC-V PolarFire PolarFireSoC BGA FCVG484 MPFS095T "
        "MPFS095TC MPFS095TS", 0, 0))
    out.append(_prop("ki_fp_filters", f"{FP_NAME}*", 0, 0))

    for uidx, (code, label, pin_type) in enumerate(UNITS, start=1):
        balls = by_unit[code]
        out.append(f'\t\t(symbol "{SYMBOL_NAME}_{uidx}_1"\n')
        n = len(balls)
        height = max(n, 1) * GRID
        top = height / 2 + GRID
        width = 60.0
        out.append("\t\t\t(rectangle\n")
        out.append(f"\t\t\t\t(start 0 {f(top)})\n")
        out.append(f"\t\t\t\t(end {f(width)} {f(-top)})\n")
        out.append("\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n")
        out.append("\t\t\t\t(fill\n\t\t\t\t\t(type background)\n\t\t\t\t)\n")
        out.append("\t\t\t)\n")
        out.append(f'\t\t\t(text "{label}"\n')
        out.append(f"\t\t\t\t(at 1.27 {f(top + 1.27)} 0)\n")
        out.append("\t\t\t\t(effects\n\t\t\t\t\t(font\n\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t)\n\t\t\t\t\t(justify left bottom)\n\t\t\t\t)\n")
        out.append("\t\t\t)\n")

        emitted_names = {}   # name -> visible y-position, for POWER stacking
        y = top - GRID
        for r in balls:
            desig = r["designator"]
            name = r["name"] or desig
            stack_hidden = False
            pin_y = y
            if code == "POWER":
                if name in emitted_names:
                    stack_hidden = True
                    pin_y = emitted_names[name]
                else:
                    emitted_names[name] = y
            hide_line = "\n\t\t\t\t(hide yes)" if stack_hidden else ""
            out.append(f"\t\t\t(pin {pin_type} line\n")
            out.append(f"\t\t\t\t(at 0 {f(pin_y)} 0)\n")
            out.append(f"\t\t\t\t(length {STUB})\n{hide_line}\n")
            out.append(f'\t\t\t\t(name "{esc(name)}"\n')
            out.append("\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n")
            out.append("\t\t\t\t)\n")
            out.append(f'\t\t\t\t(number "{desig}"\n')
            out.append("\t\t\t\t\t(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t\t\t)\n\t\t\t\t\t)\n")
            out.append("\t\t\t\t)\n")
            out.append("\t\t\t)\n")
            if not stack_hidden:
                y -= GRID
        out.append("\t\t)\n")

    out.append("\t)\n")
    out.append(")\n")

    os.makedirs(os.path.dirname(SYM_OUT), exist_ok=True)
    with open(SYM_OUT, "w", encoding="utf-8") as fh:
        fh.write("".join(out))
    total_pins = sum(len(by_unit[c]) for c in UNIT_CODES)
    print(f"[symbol] wrote {SYM_OUT} -- {len(UNITS)} units, {total_pins} pins")


def f(x):
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def esc(s):
    return s.replace('"', '\\"')


# --------------------------------------------------------------------------
# Footprint (.kicad_mod) emission
# --------------------------------------------------------------------------

def ball_xy(designator):
    """(x, y) in mm for a ball designator, top-view, A1 at top-left.

    Per the Microchip packaging UG Figure 1-17 (FCVG484 bottom view,
    rasterized + visually inspected -- no extractable text layer): columns
    are numbered 1..22 increasing RIGHT-TO-LEFT and rows A..AB top-to-bottom
    AS SEEN FROM THE BOTTOM, with "A1 BALLPAD CORNER" at the top-right in
    that view. Mirrored left-right for the top-view/silkscreen convention
    (the way a footprint is authored), A1 lands at TOP-LEFT with columns
    1..22 increasing LEFT-TO-RIGHT and rows A..AB top-to-bottom -- the
    standard JEDEC top-view BGA convention.
    """
    for i, letter in enumerate(ROW_LETTERS):
        if designator.startswith(letter) and designator[len(letter):].isdigit():
            col = int(designator[len(letter):])
            row_idx = i
            break
    else:
        raise SystemExit(f"FATAL: cannot parse designator {designator!r}")
    span = (N_COLS - 1) * PITCH
    x = -span / 2 + (col - 1) * PITCH
    y = -span / 2 + row_idx * PITCH
    return x, y


def emit_footprint(rows):
    half = BODY_SIZE / 2
    crtyd_margin = 0.25
    crtyd = half + crtyd_margin

    out = []
    out.append(f'(footprint "{FP_NAME}"\n')
    out.append("\t(version 20240108)\n")
    out.append('\t(generator "gen_mpfs_fcvg484_lib")\n')
    out.append('\t(generator_version "10.0")\n')
    out.append('\t(layer "F.Cu")\n')
    out.append(
        '\t(descr "Microchip PolarFire SoC FCVG484, 484-ball 0.8mm-pitch '
        "BGA, 19x19mm body, part-agnostic SerDes-free land (population "
        "baseline MPFS095TC / HS option MPFS095TS); ball pad 0.4mm, NSMD "
        f'solder mask opening 0.5mm per the packaging UG (Table 7-1). '
        f'Datasheet: {PACKAGING_UG_URL}")\n')
    out.append('\t(tags "BGA FCVG484 PolarFire PolarFireSoC MPFS095T 484-ball")\n')
    out.append("\t(attr smd)\n")

    out.append(f'\t(property "Reference" "REF**"\n\t\t(at 0 {f(-crtyd - 1.5)} 0)\n'
                '\t\t(layer "F.SilkS")\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')
    out.append(f'\t(property "Value" "{FP_NAME}"\n\t\t(at 0 {f(crtyd + 1.5)} 0)\n'
                '\t\t(layer "F.Fab")\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n')
    out.append('\t(property "Datasheet" ""\n\t\t(at 0 0 0)\n\t\t(layer "F.Fab")\n\t\t(hide yes)\n'
                '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t)\n\t)\n')
    out.append('\t(property "Description" ""\n\t\t(at 0 0 0)\n\t\t(layer "F.Fab")\n\t\t(hide yes)\n'
                '\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t)\n\t)\n')

    # Body outline on F.Fab
    out.append('\t(fp_rect\n')
    out.append(f"\t\t(start {f(-half)} {f(-half)})\n\t\t(end {f(half)} {f(half)})\n")
    out.append('\t\t(stroke\n\t\t\t(width 0.1)\n\t\t\t(type default)\n\t\t)\n\t\t(fill none)\n\t\t(layer "F.Fab")\n\t\t(uuid "'
                + fp_uuid() + '")\n\t)\n')
    # Courtyard
    out.append('\t(fp_rect\n')
    out.append(f"\t\t(start {f(-crtyd)} {f(-crtyd)})\n\t\t(end {f(crtyd)} {f(crtyd)})\n")
    out.append('\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type default)\n\t\t)\n\t\t(fill none)\n\t\t(layer "F.CrtYd")\n\t\t(uuid "'
                + fp_uuid() + '")\n\t)\n')
    # Silkscreen body outline (kept clear of the ball field, drawn at the body edge)
    out.append('\t(fp_rect\n')
    out.append(f"\t\t(start {f(-half)} {f(-half)})\n\t\t(end {f(half)} {f(half)})\n")
    out.append('\t\t(stroke\n\t\t\t(width 0.12)\n\t\t\t(type default)\n\t\t)\n\t\t(fill none)\n\t\t(layer "F.SilkS")\n\t\t(uuid "'
                + fp_uuid() + '")\n\t)\n')
    # Pin-1 (A1) marker: small filled silkscreen triangle at the top-left corner,
    # just outside the ball field, per the packaging UG's "A1 BALLPAD CORNER" mark.
    a1x, a1y = ball_xy("A1")
    mx, my = a1x - PITCH * 0.65, a1y - PITCH * 0.65
    out.append('\t(fp_poly\n\t\t(pts\n')
    out.append(f"\t\t\t(xy {f(mx)} {f(my)}) (xy {f(mx + 1.0)} {f(my)}) (xy {f(mx)} {f(my + 1.0)})\n")
    out.append('\t\t)\n\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(fill yes)\n\t\t(layer "F.SilkS")\n\t\t(uuid "'
                + fp_uuid() + '")\n\t)\n')

    for r in sorted(rows, key=lambda r: r["designator"]):
        desig = r["designator"]
        x, y = ball_xy(desig)
        out.append(f'\t(pad "{desig}" smd circle\n')
        out.append(f"\t\t(at {f(x)} {f(y)})\n")
        out.append(f"\t\t(size {PAD_DIA} {PAD_DIA})\n")
        out.append('\t\t(layers "F.Cu" "F.Paste" "F.Mask")\n')
        out.append(f"\t\t(solder_mask_margin {MASK_MARGIN})\n")
        out.append('\t\t(uuid "' + fp_uuid() + '")\n')
        out.append("\t)\n")

    out.append(f'\t(model "${{KIPRJMOD}}/../../lib/3dmodels/cec-ent-compute.3dshapes/{FP_NAME}.step"\n'
                '\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t\t(scale\n\t\t\t(xyz 1 1 1)\n\t\t)\n\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)\n')
    out.append(")\n")

    os.makedirs(FP_DIR, exist_ok=True)
    fp_path = os.path.join(FP_DIR, f"{FP_NAME}.kicad_mod")
    with open(fp_path, "w", encoding="utf-8") as fh:
        fh.write("".join(out))
    print(f"[footprint] wrote {fp_path} -- {len(rows)} pads, {PITCH}mm pitch, "
          f"{PAD_DIA}mm pad / {MASK_OPENING}mm NSMD mask opening")


_uuid_counter = [0]


def fp_uuid():
    # Deterministic pseudo-UUIDs so re-runs are byte-identical (real UUID4
    # would churn the file on every regen for no reason -- this is a
    # generated, reproducible artifact, not hand-edited).
    import hashlib
    _uuid_counter[0] += 1
    h = hashlib.sha1(f"mpfs-fcvg484-{_uuid_counter[0]}".encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def main():
    rows = load_balls()
    validate(rows)
    emit_symbol(rows)
    emit_footprint(rows)
    print("[done] no other library file or lib table was touched.")


if __name__ == "__main__":
    sys.exit(main())
