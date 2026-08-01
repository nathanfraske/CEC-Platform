#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  gen-daughterboard-libassets -- new library footprints/symbol for the
#  §2.8 v1.4.0 output-daughterboard projects (beta/output-daughterboards/*).
# ============================================================================
# These are the pieces NOT already vendored by the earlier library-intake pass
# (which landed TE_63849-1_FASTON_Tab / Keystone_3557-2 / Keystone_3586 --
# lib/vendor/Connector_Blade.pretty + matching cec-vendor symbols):
#
#   1. Bare THT "solder-field" footprints -- the daughterboard's OUTPUT side,
#      per family. NOT a housing/connector part; a plain pad grid a bare
#      pigtail solders into OR a MODDIY-class vertical female header's own
#      solder tails would land on (same pitch/positions), per the study §4
#      ("one field, two/three uses"). Geometry is MEASURED off this repo's
#      own already-vendored, verified Molex Mini-Fit Jr lands (4.20mm pitch /
#      5.5mm row / 2.7x3.7mm oval pad / 1.8mm drill -- lib/vendor/
#      Connector_Molex.pretty/Molex_Mini-Fit_Jr_5569-{08A2,24A1}...), which is
#      both a real, already-verified 16 AWG-class land in this repo AND the
#      same "5557/5559 family" 4.2mm pitch the study's §4 explicitly
#      recommends for this exact field -- not a fresh invention. Signal-class
#      positions (24-pin's PWR_OK/PS_ON#/-12V/NC-reserved physical slots;
#      PCIe's 2 sense positions) get a smaller 18 AWG-class pad/drill
#      (1.4mm/2.6mm, matching the already-vendored TE_63849-1 tab's own leg
#      size -- an internally consistent choice, not arbitrary).
#   2. A generic 2x5, 2.54mm-pitch THT pin header footprint -- the 24-pin
#      daughterboard's "signal stub" position (PWR_OK/PS_ON#/-12V + a GND
#      reference + reserved/sense-return-provision pins, per the study §8.5's
#      "posts+signal-header hybrid"). Authored to the same well-known KiCad
#      generic-header convention already vendored at
#      lib/vendor/Connector_PinHeader_2.00mm.pretty (itself a stock
#      kicad-footprint-generator part, just cec-namespaced) -- this is a
#      commodity 0.1" header, not a proprietary drawing.
#   3. A matching CEC_CONN_2x5 schematic symbol (cec.kicad_sym), extending the
#      already-vendored generic CEC_CONN_2x4 (itself KiCad's stock
#      Connector_Generic:Conn_02x04_Odd_Even, renamed) by one pin row.
#
# Explicitly NOT done here (STOP-and-report wall, per the task brief): no
# MODDIY-brand footprint is invented -- MODDIY's own part has no published
# drawing (CLAUDE.md/OQ-88), so it is never placed as a component; the bare
# solder field is merely dimensionally compatible (documented in each board's
# README), and MODDIY population stays a DNP/no-footprint note.
#
#   python3 scripts/gen-daughterboard-libassets.py
import os, sys, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ff(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def U():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Generic bare THT solder-field footprint.
# ---------------------------------------------------------------------------
def solder_field(name, descr, pads, *, rows=2, cols=12, pitch_x=4.2, pitch_y=5.5):
    """pads: list of (num, x, y, drill, pad_w, pad_h, shape) -- shape 'oval'|'circle'.
    Bare pad field: silk reference box + F.Fab outline + F.CrtYd, no connector
    body/shroud (this is not a housing part).

    Y-margin is PAD-HEIGHT-based (actual half-height of the widest pad in each
    extreme row + a small fixed process margin), not half-of-row-pitch. This is
    a CEC-authored keepout box with no housing to measure (there is no vendor
    body overhanging the pads on this asset, unlike the real Molex land it
    borrows pitch/pad geometry from) -- so the old half-pitch margin (2.75mm
    each side on a 5.5mm row pitch, +1mm outer = 3.75mm total per side) was
    pure headroom, not a physical requirement, and it was the single largest
    contributor to blowing the owner's 2026-07-05 daughterboard HEIGHT cap
    (the board now stands vertically; this field's row-stack axis IS the
    capped axis). Tightened to pad half-height + 0.5mm: field height on this
    2-row/5.5mm-pitch layout drops from 13.0mm to ~10.2mm. X (the column
    axis) is untouched -- it is the free "length" dimension on the standing
    board, no reason to tighten it and every reason not to touch a dimension
    that isn't the problem."""
    xs = [p[1] for p in pads]; ys = [p[2] for p in pads]
    y_lo, y_hi = min(ys), max(ys)
    h_lo = max(p[5] for p in pads if p[2] == y_lo)
    h_hi = max(p[5] for p in pads if p[2] == y_hi)
    x0, x1 = min(xs) - pitch_x / 2, max(xs) + pitch_x / 2
    y0, y1 = y_lo - h_lo / 2, y_hi + h_hi / 2
    cx0, cx1, cy0, cy1 = x0 - 1.0, x1 + 1.0, y0 - 0.5, y1 + 0.5
    body = [
        f'(footprint "{name}"',
        '\t(version 20260206)',
        '\t(generator "cec_gen-daughterboard-libassets")',
        '\t(generator_version "10.0")',
        '\t(layer "F.Cu")',
        f'\t(descr "{descr}")',
        '\t(tags "CEC daughterboard bare THT solder field, no housing")',
        '\t(property "Reference" "REF**"',
        f'\t\t(at {ff((x0+x1)/2)} {ff(y0-2)} 0)',
        '\t\t(layer "F.SilkS")',
        f'\t\t(uuid "{U()}")',
        '\t\t(effects (font (size 1 1) (thickness 0.15)))',
        '\t)',
        f'\t(property "Value" "{name}"',
        f'\t\t(at {ff((x0+x1)/2)} {ff(y1+2)} 0)',
        '\t\t(layer "F.Fab")',
        f'\t\t(uuid "{U()}")',
        '\t\t(effects (font (size 1 1) (thickness 0.15)))',
        '\t)',
        '\t(attr through_hole)',
        '\t(duplicate_pad_numbers_are_jumpers no)',
    ]
    # silk + fab outline box around the whole field (no plastic body -- a bare
    # pad field's "outline" is just the assembly-reference rectangle)
    for layer in ("F.SilkS", "F.Fab"):
        w = 0.15 if layer == "F.SilkS" else 0.1
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            body.append(f'\t(fp_line (start {ff(ax)} {ff(ay)}) (end {ff(bx)} {ff(by)}) '
                        f'(stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{U()}"))')
    body.append(f'\t(fp_rect (start {ff(cx0)} {ff(cy0)}) (end {ff(cx1)} {ff(cy1)}) '
               f'(stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{U()}"))')
    for num, x, y, drill, pw, ph, shape in pads:
        body.append(f'\t(pad "{num}" thru_hole {shape} (at {ff(x)} {ff(y)}) '
                   f'(size {ff(pw)} {ff(ph)}) (drill {ff(drill)}) '
                   f'(layers "*.Cu" "*.Mask") (remove_unused_layers no) (uuid "{U()}"))')
    body.append('\t(embedded_fonts no)')
    body.append(')')
    return "\n".join(body) + "\n"


POWER = dict(drill=1.8, pw=2.7, ph=3.7, shape="oval")     # 16 AWG-class, = the real Molex 5569 land
SIGNAL = dict(drill=1.4, pw=2.6, ph=2.6, shape="circle")  # 18 AWG-class, matches the TE 63849-1 leg size

# 24-pin ATX field: 2 rows x 12 @ 4.2mm pitch / 5.5mm row (Molex 5569-24A1 grid,
# measured off lib/vendor/Connector_Molex.pretty/...-24A1...). Pin numbering/
# position matches that footprint 1:1 (and so CEC_ATX_24's own named pins),
# row1 y=0 pins 1-12, row2 y=5.5 pins 13-24. Signal-class (18AWG) positions are
# the four non-power ATX circuits: 8=PWR_OK, 14=-12V, 16=PS_ON#, 20=NC(reserved).
ATX24_SIGNAL_PINS = {8, 14, 16, 20}
atx24_pads = []
for i in range(12):
    n = i + 1
    g = SIGNAL if n in ATX24_SIGNAL_PINS else POWER
    atx24_pads.append((str(n), i * 4.2, 0.0, g["drill"], g["pw"], g["ph"], g["shape"]))
for i in range(12):
    n = i + 13
    g = SIGNAL if n in ATX24_SIGNAL_PINS else POWER
    atx24_pads.append((str(n), i * 4.2, 5.5, g["drill"], g["pw"], g["ph"], g["shape"]))

# EPS 8-pin field: 2 rows x 4 @ 4.2mm/5.5mm (Molex 5569-08A2 grid). Per the
# repo's corrected EPS pinout (pins 1-4=GND, 5-8=+12V, see CLAUDE.md "EPS 8-pin
# power-connector pinout fix"), all 8 positions are power-class.
eps8_pads = [(str(n + 1), (n % 4) * 4.2, 0.0 if n < 4 else 5.5, *([POWER["drill"], POWER["pw"],
             POWER["ph"], POWER["shape"]])) for n in range(8)]

# PCIe 8-pin field: same 2x4 grid. Standard PCIe CEM 8-pin motherboard-side map:
# 1-3=+12V, 4-6=GND, 7=SENSE1, 8=SENSE0 -- pins 7/8 are the two "sense tied on
# the daughterboard copper" positions (§2.8 v1.4.0 text), 18AWG-class (near-zero
# current, only there to be strapped to GND by the daughterboard's own copper).
PCIE8_SIGNAL_PINS = {7, 8}
pcie8_pads = []
for n in range(8):
    pin = n + 1
    x = (n % 4) * 4.2; y = 0.0 if n < 4 else 5.5
    g = SIGNAL if pin in PCIE8_SIGNAL_PINS else POWER
    pcie8_pads.append((str(pin), x, y, g["drill"], g["pw"], g["ph"], g["shape"]))

FIELDS = [
    ("ATX24_Daughterboard_Field_P4.20mm", atx24_pads,
     "Bare THT solder field, 24 positions, 2x12 @ 4.20mm pitch / 5.5mm row -- "
     "the §2.8 v1.4.0 24-pin ATX output-daughterboard OUTPUT field. Pad grid "
     "measured off the vendored Molex Mini-Fit Jr 5569-24A1 land (same pitch/"
     "row/pad/drill for the 20 power-class positions, 1.8mm drill / 2.7x3.7mm "
     "oval, 16AWG-class); the 4 non-power ATX circuit positions (8=PWR_OK, "
     "14=-12V, 16=PS_ON#, 20=NC/reserved) are downsized to 1.4mm drill / 2.6mm "
     "round (18AWG-class). No connector body/shroud -- this is the field a "
     "hand-soldered pigtail or a MODDIY-class vertical female header's own "
     "solder tails land on; NOT itself a MODDIY-brand part (no such footprint "
     "is vendored -- OQ-88 provenance gap). See docs/standard-tier-review/"
     "output-daughterboard-study-2026-07-04.md §4."),
    ("EPS8_Daughterboard_Field_P4.20mm", eps8_pads,
     "Bare THT solder field, 8 positions, 2x4 @ 4.20mm pitch / 5.5mm row -- "
     "the §2.8 v1.4.0 EPS 8-pin output-daughterboard OUTPUT field (per cable). "
     "Pin map: 1-4=GND, 5-8=+12V (matches the platform's corrected EPS "
     "pinout). All 8 positions power-class (1.8mm drill / 2.7x3.7mm oval, "
     "16AWG). Pad grid measured off the vendored Molex Mini-Fit Jr 5569-08A2 "
     "land. No connector body/shroud; MODDIY-class vertical header population "
     "is a dimensional-compatibility note only, not a placed footprint."),
    ("PCIe8_Daughterboard_Field_P4.20mm", pcie8_pads,
     "Bare THT solder field, 8 positions, 2x4 @ 4.20mm pitch / 5.5mm row -- "
     "the §2.8 v1.4.0 PCIe 8-pin output-daughterboard OUTPUT field (per "
     "cable, shared by the 2-port and 3-port SKUs). Standard PCIe CEM "
     "motherboard-side map: 1-3=+12V, 4-6=GND (power-class, 1.8mm/2.7x3.7mm "
     "oval), 7=SENSE1, 8=SENSE0 (18AWG-class, 1.4mm/2.6mm round -- tied to "
     "GND on the daughterboard's own copper, no dedicated blade tab). Pad "
     "grid measured off the vendored Molex Mini-Fit Jr 5569-08A2 land. No "
     "connector body/shroud."),
]

OUTDIR = f"{ROOT}/lib/vendor/Connector_Generic.pretty"
os.makedirs(OUTDIR, exist_ok=True)
for name, pads, descr in FIELDS:
    path = f"{OUTDIR}/{name}.kicad_mod"
    open(path, "w").write(solder_field(name, descr, pads))
    print(f"WROTE {os.path.relpath(path, ROOT)}  ({len(pads)} pads)")


# ---------------------------------------------------------------------------
# Generic 2x5, 2.54mm-pitch THT pin header footprint (24-pin signal stub).
# Same stock kicad-footprint-generator convention already vendored at
# lib/vendor/Connector_PinHeader_2.00mm.pretty/PinHeader_2x08_P2.00mm_Vertical
# (a commodity 0.1" header, not a proprietary drawing) -- pad 1.7mm circle
# (pin1 rect), 1.0mm drill, the KiCad-standard PinHeader_2.54mm dimensions.
# ---------------------------------------------------------------------------
def pinheader_2x05():
    rows, cols = 5, 2
    pitch = 2.54
    pads = []
    for r in range(rows):
        for c in range(cols):
            num = r * cols + c + 1
            pads.append((num, c * pitch, r * pitch))
    x0, x1 = -pitch / 2 - 0.5, pitch * 1.5 + 0.5
    y0, y1 = -pitch / 2 - 0.5, pitch * (rows - 1) + pitch / 2 + 0.5
    lines = [
        '(footprint "PinHeader_2x05_P2.54mm_Vertical"',
        '\t(version 20260206)',
        '\t(generator "cec_gen-daughterboard-libassets")',
        '\t(generator_version "10.0")',
        '\t(layer "F.Cu")',
        '\t(descr "Through hole straight pin header, 2x05, 2.54mm pitch, double '
        'rows -- 24-pin ATX daughterboard signal stub (PWR_OK/PS_ON#/-12V/GND-ref/'
        'reserved), §2.8 v1.4.0 posts+signal-header hybrid, output-daughterboard-'
        'study-2026-07-04.md §8.5")',
        '\t(tags "Through hole pin header THT 2x05 2.54mm double row")',
        f'\t(property "Reference" "REF**" (at {ff(x0)} {ff(y0-1)} 0) (layer "F.SilkS") '
        f'(uuid "{U()}") (effects (font (size 1 1) (thickness 0.15))))',
        f'\t(property "Value" "PinHeader_2x05_P2.54mm_Vertical" (at {ff(x0)} {ff(y1+1)} 0) '
        f'(layer "F.Fab") (uuid "{U()}") (effects (font (size 1 1) (thickness 0.15))))',
        '\t(attr through_hole)',
        '\t(duplicate_pad_numbers_are_jumpers no)',
        f'\t(fp_rect (start {ff(x0)} {ff(y0)}) (end {ff(x1)} {ff(y1)}) '
        f'(stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS") (uuid "{U()}"))',
        f'\t(fp_rect (start {ff(x0-0.4)} {ff(y0-0.4)}) (end {ff(x1+0.4)} {ff(y1+0.4)}) '
        f'(stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{U()}"))',
        f'\t(fp_rect (start {ff(x0)} {ff(y0)}) (end {ff(x1)} {ff(y1)}) '
        f'(stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab") (uuid "{U()}"))',
    ]
    for num, x, y in pads:
        shape = "rect" if num == 1 else "circle"
        lines.append(f'\t(pad "{num}" thru_hole {shape} (at {ff(x)} {ff(y)}) '
                    f'(size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") '
                    f'(remove_unused_layers no) (uuid "{U()}"))')
    lines.append('\t(embedded_fonts no)')
    lines.append(')')
    return "\n".join(lines) + "\n"


PHDIR = f"{ROOT}/lib/vendor/Connector_PinHeader_2.54mm.pretty"
os.makedirs(PHDIR, exist_ok=True)
ph_path = f"{PHDIR}/PinHeader_2x05_P2.54mm_Vertical.kicad_mod"
open(ph_path, "w").write(pinheader_2x05())
print(f"WROTE {os.path.relpath(ph_path, ROOT)}  (10 pads)")


# ---------------------------------------------------------------------------
# CEC_CONN_2x5 schematic symbol: CEC_CONN_2x4 (itself the stock KiCad generic
# Connector_Generic:Conn_02x04_Odd_Even, cec-renamed) extended by one pin row,
# same body-rectangle / pin-stub convention.
# ---------------------------------------------------------------------------
def cec_conn_2x5():
    rows_y = [2.54, 0.0, -2.54, -5.08, -7.62]
    body_y0, body_y1 = 3.81, -8.89
    lines = [
        '\t(symbol "CEC_CONN_2x5"',
        '\t\t(pin_names (offset 1.016) (hide yes))',
        '\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (in_pos_files yes)',
        '\t\t(duplicate_pin_numbers_are_jumpers no)',
        '\t\t(property "Reference" "J" (at 1.27 5.08 0) (show_name no) '
        '(do_not_autoplace no) (effects (font (size 1.27 1.27))))',
        '\t\t(property "Value" "CEC_CONN_2x5" (at 1.27 -10.16 0) (show_name no) '
        '(do_not_autoplace no) (effects (font (size 1.27 1.27))))',
        '\t\t(property "Footprint" "" (at 0 0 0) (show_name no) (do_not_autoplace no) '
        '(hide yes) (effects (font (size 1.27 1.27))))',
        '\t\t(property "Datasheet" "" (at 0 0 0) (show_name no) (do_not_autoplace no) '
        '(hide yes) (effects (font (size 1.27 1.27))))',
        '\t\t(property "Description" "Generic connector, double row, 02x05, odd/even '
        'pin numbering scheme (row 1 odd numbers, row 2 even numbers) -- extends the '
        'vendored CEC_CONN_2x4 by one row for the 24-pin ATX daughterboard signal '
        'stub (§2.8 v1.4.0)." (at 0 0 0) (show_name no) (do_not_autoplace no) '
        '(hide yes) (effects (font (size 1.27 1.27))))',
        '\t\t(property "ki_keywords" "connector" (at 0 0 0) (show_name no) '
        '(do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))',
        '\t\t(property "ki_fp_filters" "Connector*:*_2x??_*" (at 0 0 0) (show_name no) '
        '(do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))',
        '\t\t(symbol "CEC_CONN_2x5_1_1"',
        f'\t\t\t(rectangle (start -1.27 {ff(body_y0)}) (end 3.81 {ff(body_y1)}) '
        '(stroke (width 0.254) (type default)) (fill (type background)))',
    ]
    for y in rows_y:
        lines.append(f'\t\t\t(rectangle (start -1.27 {ff(y+0.127)}) (end 0 {ff(y-0.127)}) '
                     '(stroke (width 0.1524) (type default)) (fill (type none)))')
        lines.append(f'\t\t\t(rectangle (start 3.81 {ff(y+0.127)}) (end 2.54 {ff(y-0.127)}) '
                     '(stroke (width 0.1524) (type default)) (fill (type none)))')
    for i, y in enumerate(rows_y):
        n1, n2 = i * 2 + 1, i * 2 + 2
        lines.append(f'\t\t\t(pin passive line (at -5.08 {ff(y)} 0) (length 3.81) '
                     f'(name "Pin_{n1}" (effects (font (size 1.27 1.27)))) '
                     f'(number "{n1}" (effects (font (size 1.27 1.27)))))')
        lines.append(f'\t\t\t(pin passive line (at 7.62 {ff(y)} 180) (length 3.81) '
                     f'(name "Pin_{n2}" (effects (font (size 1.27 1.27)))) '
                     f'(number "{n2}" (effects (font (size 1.27 1.27)))))')
    lines.append('\t\t)')
    lines.append('\t\t(embedded_fonts no)')
    lines.append('\t)')
    return "\n".join(lines)


sympath = f"{ROOT}/lib/cec.kicad_sym"
symtext = open(sympath).read()
if '"CEC_CONN_2x5"' not in symtext:
    block = cec_conn_2x5()
    # insert right before the final closing paren of the (kicad_symbol_lib ...) file
    idx = symtext.rstrip().rfind(")")
    symtext = symtext.rstrip()[:idx] + block + "\n)\n"
    open(sympath, "w").write(symtext)
    print(f"WROTE {os.path.relpath(sympath, ROOT)}  (+CEC_CONN_2x5)")
else:
    print(f"SKIP {os.path.relpath(sympath, ROOT)}  (CEC_CONN_2x5 already present)")
