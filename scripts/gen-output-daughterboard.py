#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  gen-output-daughterboard -- §2.8 v1.4.0 output-connector daughterboards
# ============================================================================
# Builds the three passive-daughterboard projects under
# modules/output-daughterboards/ (24-pin ATX / EPS 8-pin per-cable / PCIe
# 8-pin per-cable, the last shared unmodified by the 2-port and 3-port SKUs).
# Per family: TE 63951-1 right-angle FASTON tabs (input side; blades point
# straight DOWN past the board's bottom edge and drop into the MAIN board's
# Keystone universal blade clips top-entry, per the owner's 2026-07-05
# sketch -- clips NOT built here, no main-board PCB placement exists yet)
# fan out in copper to a bare THT solder field (output side, spec §2.8's
# "one field, two/three uses": bare pigtail, or a MODDIY-class vertical
# header where the field is dimensionally compatible -- see
# gen-daughterboard-libassets.py's field footprints). NO active or passive
# components (ratified: "no components beyond the connector body and its
# fan-out copper"). Read CEC-Platform-Ground-Truth-Spec.md §2.8 v1.4.0 +
# OQ-87/88/89, docs/standard-tier-review/output-daughterboard-study-
# 2026-07-04.md, and blade-fit-check-2026-07-04.md (addenda) before
# changing any net map, joint count, or tab geometry below.
#
#   python3 scripts/gen-output-daughterboard.py <family> [--force]
#   family: atx24-out-db | eps-out-db | pcie-out-db | all
import math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import cec_sch as cs   # noqa: E402
import cec_pcb as cp   # noqa: E402 -- place/parse_netlist/ff/U/LAYERS/stackup/local_pads/courtyard_bbox

LIBS = {
    "cec":        open(f"{ROOT}/lib/cec.kicad_sym").read(),
    "cec-vendor": open(f"{ROOT}/lib/vendor/cec-vendor.kicad_sym").read(),
    # cec_sch._power_block() looks up the internal key "power" (the embedded
    # instance lib_id namespace is separately hardcoded there as "cec-power:...").
    "power":      open(f"{ROOT}/lib/vendor/cec-power.kicad_sym").read(),
}

# TE 63951-1 -- RIGHT-ANGLE FASTON .250 PC board tab, per the owner's
# 2026-07-05 rulings (the SKETCH ruling, later the same day, fixed the part
# MODEL/orientation; the part itself was picked by the same day's earlier
# connector-form hunt, superseding the morning's TE 63849-1 straight tab).
# Same .250 width class, App Spec 114-2115, and 5.08mm leg pitch / 1.40mm
# hole pattern as 63849-1, but a flat IN-PLANE L stamping: the blade runs
# along the leg-pitch axis past the blade-side leg, standing 2.54-8.89mm off
# the seating face (TE dwg C=63951 rev L2, lib/datasheets/TE_63951-1.pdf --
# full geometry derivation in the footprint's descr). Mounted legs-
# horizontal / pitch-vertical / blade-down per the owner's sketch: the
# assembly drops vertically, blades entering the main-board Keystone clips
# top-entry, the board's own bottom edge floating clear. See
# docs/standard-tier-review/blade-fit-check-2026-07-04.md addenda (hunt +
# the addendum-3 geometry record). TE_63849-1 remains vendored (harmless;
# unreferenced by this generator).
TE_TAB = ("cec-vendor", "TE_63951-1_FASTON_Tab", "TE 63951-1")
TE_TAB_FP = "cec-Connector_Blade:TE_63951-1_FASTON_Tab_250x032_RA_THT"

POWER_PORTS = {"GND": "GND", "+3V3": "+3V3", "+5V": "+5V", "+5VSB": "+5VSB", "+12V": "+12V"}

# ============================================================================
# Per-family data. Joint counts + net maps are per CLAUDE.md/spec §2.8 v1.4.0
# and the study's §1/§6/§8.9 (ratified blade config, per-cable shape).
# ============================================================================
FAMILIES = {}

# ---- 24-pin ATX: 9 blade joints (12V x1, 5V x2, 3.3V x1, 5VSB x1, GND x4) +
# a 2x5 signal header (PWR_OK, PS_ON#, -12V, GND-ref, 6 reserved/sense-return-
# provision spares) + the full 24-circuit output field (reuses cec:CEC_ATX_24,
# the SAME symbol the platform's own J3/old-J4 ATX connectors use, so the pin
# NAMES/MAP are inherited verbatim -- only the FOOTPRINT differs: a bare
# solder field instead of a Mini-Fit Jr male header shroud).
ATX24_FIELD_NET = {  # ATX-24 pin -> net (None = NC/reserved, matches the real
    1: "+3V3", 2: "+3V3", 3: "GND", 4: "+5V", 5: "GND", 6: "+5V", 7: "GND",
    8: "PWR_OK", 9: "+5VSB", 10: "+12V", 11: "+12V", 12: "+3V3", 13: "+3V3",
    14: "-12V", 15: "GND", 16: "PS_ON#", 17: "GND", 18: "GND", 19: "GND",
    20: None, 21: "+5V", 22: "+5V", 23: "+5V", 24: "GND",
}
ATX24_TABS = [  # (ref, net) -- 9 tabs, asymmetric group sizes 1/2/1/1/4 (keying)
    ("J10", "+12V"), ("J11", "+5V"), ("J12", "+5V"), ("J13", "+3V3"),
    ("J14", "+5VSB"), ("J15", "GND"), ("J16", "GND"), ("J17", "GND"), ("J18", "GND"),
]
# SIGNAL STUB, iteration 5 (owner: 1x4 blind-mate, superseding the 2x5 --
# blade-fit memo addendum 5): a RIGHT-ANGLE Dupont-class 1x4 pin header,
# pins pointing straight DOWN past the bottom edge parallel to the blades,
# mating a vertical female socket on the main board in the same single
# drop. Only the 4 LIVE circuits ride it (netlist-verified: -12V/PS_ON#/
# PWR_OK each have exactly one field pin; +GND reference); the 2x5's six
# reserved positions move to DNP solder pads SR1-6 (OQ-88 provision FORM
# only -- the sense-return decision itself stays open, owner's). PIN ORDER
# is NEW and routing-derived (supersedes the 2x5's order, which dies with
# that part): pads left-to-right = -12V, PS_ON#, PWR_OK, GND -- the three
# signals' field-column order (c1/c3/c7), which lets the fan-down nest
# without crossings (see route_atx24). The main-board J_SIG mate MIRRORS
# this map when it is reworked to the matching 1x4 female socket.
ATX24_HEADER_NET = {1: "-12V", 2: "PS_ON#", 3: "PWR_OK", 4: "GND"}

FAMILIES["atx24-out-db"] = dict(
    dirn="output-daughterboards/atx24-out-db", base="atx24-out-db-board",
    field_ref="J1", field_symbol=("cec", "CEC_ATX_24"),
    field_fp="cec-Connector_Generic:ATX24_Daughterboard_Field_P4.20mm",
    field_net=ATX24_FIELD_NET, field_value="ATX24 OUT FIELD",
    tabs=ATX24_TABS,
    header=dict(ref="J20", symbol=("cec", "CEC_CONN_1x4"),
                fp="cec-Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Horizontal_LongPin",
                net=ATX24_HEADER_NET, value="SIGNAL STUB (1x4 blind-mate)"),
    W=140.0, H=75.0,
)

# ---- EPS 8-pin (per cable): 6 blade joints (3/polarity), 4x12V+4xGND field,
# reuses the generic cec:CEC_CONN_2x4 symbol (unnamed pins; nets assigned by
# wiring, matching the platform's own corrected EPS pinout: 1-4=GND,5-8=+12V).
EPS8_FIELD_NET = {1: "GND", 2: "GND", 3: "GND", 4: "GND",
                  5: "+12V", 6: "+12V", 7: "+12V", 8: "+12V"}
EPS8_TABS = [  # 6 tabs, groups of 3 (GND then 12V) -- keying: different pitch/
    # gap signature + tab count (6) vs the other two families.
    ("J10", "GND"), ("J11", "GND"), ("J12", "GND"),
    ("J13", "+12V"), ("J14", "+12V"), ("J15", "+12V"),
]
FAMILIES["eps-out-db"] = dict(
    dirn="output-daughterboards/eps-out-db", base="eps-out-db-board",
    field_ref="J1", field_symbol=("cec", "CEC_CONN_2x4"),
    field_fp="cec-Connector_Generic:EPS8_Daughterboard_Field_P4.20mm",
    field_net=EPS8_FIELD_NET, field_value="EPS8 OUT FIELD",
    tabs=EPS8_TABS, header=None,
    W=95.0, H=65.0,
)

# ---- PCIe 8-pin (per cable, shared by 2-port/3-port): 4 blade joints
# (2/polarity), 3x12V+3xGND+2 sense field (SENSE0/1 tied to the GND net
# directly -- "tied per the PCIe CEM convention on the daughterboard copper",
# spec §2.8 v1.4.0; no dedicated blade tab, negligible current).
PCIE8_FIELD_NET = {1: "+12V", 2: "+12V", 3: "+12V",
                   4: "GND", 5: "GND", 6: "GND", 7: "GND", 8: "GND"}
PCIE8_TABS = [  # 4 tabs, groups of 2 (12V then GND) -- distinct pitch/gap
    # signature + tab count (4) vs EPS(6)/24-pin(9).
    ("J10", "+12V"), ("J11", "+12V"), ("J12", "GND"), ("J13", "GND"),
]
FAMILIES["pcie-out-db"] = dict(
    dirn="output-daughterboards/pcie-out-db", base="pcie-out-db-board",
    field_ref="J1", field_symbol=("cec", "CEC_CONN_2x4"),
    field_fp="cec-Connector_Generic:PCIe8_Daughterboard_Field_P4.20mm",
    field_net=PCIE8_FIELD_NET, field_value="PCIE8 OUT FIELD",
    tabs=PCIE8_TABS, header=None,
    W=75.0, H=60.0,
)


def _board_dir(fam):
    return f"{ROOT}/modules/{FAMILIES[fam]['dirn']}"


def _bootstrap_sch(path):
    """cec_sch.build_schematic reads the ROOT uuid from an EXISTING file (it
    regenerates in place); a brand-new project needs a one-line stub first."""
    if not os.path.exists(path):
        import uuid
        open(path, "w").write(f'(kicad_sch (uuid "{uuid.uuid4()}"))\n')


def build_nets(fam):
    """Assemble the nets dict: field-connector pins + tabs (+ header pins)."""
    cfg = FAMILIES[fam]
    nets = {}
    for pin, net in cfg["field_net"].items():
        if net:
            nets.setdefault(net, []).append((cfg["field_ref"], str(pin)))
    for ref, net in cfg["tabs"]:
        nets.setdefault(net, []).append((ref, "1"))
    if cfg["header"]:
        h = cfg["header"]
        for pin, net in h["net"].items():
            if net:
                nets.setdefault(net, []).append((h["ref"], str(pin)))
    return nets


def build_parts(fam):
    cfg = FAMILIES[fam]
    parts = {cfg["field_ref"]: (*cfg["field_symbol"], cfg["field_value"])}
    for ref, _net in cfg["tabs"]:
        parts[ref] = TE_TAB
    if cfg["header"]:
        h = cfg["header"]
        parts[h["ref"]] = (*h["symbol"], h["value"])
    return parts


def build_footprints(fam):
    cfg = FAMILIES[fam]
    fps = {cfg["field_ref"]: cfg["field_fp"]}
    for ref, _net in cfg["tabs"]:
        fps[ref] = TE_TAB_FP
    if cfg["header"]:
        fps[cfg["header"]["ref"]] = cfg["header"]["fp"]
    return fps


TE_TAB_PROPS = {
    "LCSC": "C591344", "MPN": "63951-1", "Manufacturer": "TE Connectivity",
    "Description": "FASTON .250 RIGHT-ANGLE PCB tab (in-plane L stamping, "
                   "male blade). Mounted legs-horizontal / pitch-vertical / "
                   "blade-down (owner sketch 2026-07-05): the blade descends "
                   "past the board's bottom edge at a 2.54-8.89mm standoff "
                   "and drops top-entry into the main board's Keystone "
                   "universal blade clip -- spec Sec. 2.8 v1.4.0 / docs/"
                   "standard-tier-review/output-daughterboard-study-2026-07-"
                   "04.md Sec.8.9-8.10 / blade-fit-check-2026-07-04.md "
                   "addenda (addendum 3 = this geometry).",
}
FIELD_PROPS = {
    "Manufacturer": "CEC (in-house)", "LCSC": "",
    "Description": "Bare THT solder field, no housing/shroud -- CEC-authored "
                   "footprint (lib/vendor/Connector_Generic.pretty), NOT a "
                   "stocked/purchased part. Populate with a hand-soldered "
                   "pigtail (default), OR (bring-up samples only, provenance-"
                   "UNVERIFIED, OQ-88) a MODDIY-class vertical female header "
                   "if the pitch/hole pattern proves compatible on the sample "
                   "fit check -- no MODDIY footprint exists in this library "
                   "and none is placed here.",
}
HEADER_PROPS = {
    "Manufacturer": "generic", "LCSC": "",
    "Description": "1x4 2.54mm RIGHT-ANGLE Dupont-class pin header, LONG "
                   "mating tails (10-15mm class) -- blind-mate signal stub, "
                   "pins down past the bottom edge parallel to the blades, "
                   "mating the main board's vertical 1x4 female socket in "
                   "the same drop (owner, 2026-07-05; memo addendum 5). "
                   "Commodity class at LCSC (Ckmtw/Cankemeng RA lines); the "
                   "specific long-pin MPN is pinned at the OQ-89 SKU pass; "
                   "consigned acceptable. Keyed-JST-PH (S4B/B4B-PH-K-S, the "
                   "Hub J_KVM family) is the demoted cabled fallback if the "
                   "blind-mate tolerance fails the fit check.",
}


def build_bom_props(fam):
    cfg = FAMILIES[fam]
    props = {cfg["field_ref"]: dict(FIELD_PROPS)}
    for ref, _net in cfg["tabs"]:
        props[ref] = dict(TE_TAB_PROPS)
    if cfg["header"]:
        props[cfg["header"]["ref"]] = dict(HEADER_PROPS)
    return props


def build_placement(fam):
    """Schematic-only layout (readability, S1/S2 composition standard) --
    independent of the PCB's physical placement. Field top-left, tabs in a
    row below grouped by rail with a visible gap between groups (mirrors the
    PCB's asymmetric keying pattern so the sheet reads the same story), the
    24-pin signal header beside the field."""
    cfg = FAMILIES[fam]
    P = {cfg["field_ref"]: (76.2, 50.8)}
    x = 25.4
    prev_net = None
    for ref, net in cfg["tabs"]:
        if prev_net is not None and net != prev_net:
            x += 12.7          # extra gap between rail groups
        P[ref] = (x, 127.0)
        x += 15.24
        prev_net = net
    if cfg["header"]:
        P[cfg["header"]["ref"]] = (203.2, 50.8)
    return P


def gen_schematic(fam, out=sys.stdout):
    cfg = FAMILIES[fam]
    bdir = _board_dir(fam)
    os.makedirs(bdir, exist_ok=True)
    sch_path = f"{bdir}/{cfg['base']}.kicad_sch"
    _bootstrap_sch(sch_path)
    parts = build_parts(fam)
    nets = build_nets(fam)
    fps = build_footprints(fam)
    placement = build_placement(fam)
    used = cs.load_symbols(LIBS, parts)
    # every power-rail net here is fed ONLY by connector "passive" pins (no
    # active driver anywhere on a passive board) -- PWR_FLAG each rail that
    # rides a power-port symbol, same convention as gen-modules.py.
    powerflag_nets = [n for n in POWER_PORTS if n in nets]
    props = build_bom_props(fam)
    stats = cs.build_schematic(
        sch_path, cfg["base"], parts, nets, used, LIBS, paper="A4",
        power_ports=POWER_PORTS, powerflag_nets=powerflag_nets,
        placement=placement, footprints=fps, props=props)
    print(f"{cfg['dirn']}/{cfg['base']}.kicad_sch  " +
          "  ".join(f"{k}={v}" for k, v in stats.items() if k != "root"), file=out)
    return sch_path


# ============================================================================
# PCB: physical placement -- board STANDS PERPENDICULAR (90 deg) to the main
# board (owner ruling, 2026-07-04/05 -- the board's own standing posture is
# unchanged). Axes, as authored in this 2D file:
#   X = "length", parallel to the main board once installed. FREE dimension,
#       no ceiling -- minimize opportunistically, never at the expense of Y.
#   Y = "height", the board's own vertical extent standing up off the main
#       board. RULED CAP: <=15mm "or so" (owner, 2026-07-05). Y=0 (top of this
#       drawing) is the board's FAR edge (top when installed); Y=H (bottom of
#       this drawing) is the NEAR edge (the board's own Edge.Cuts).
#
# TAB CONNECTOR FORM -- OWNER SKETCH, 2026-07-05 (third and final same-day
# form; supersedes BOTH the morning's TE 63849-1 perpendicular/side-entry
# build AND this generator's brief interim "blade hangs past the bottom
# edge, in-plane" mis-model of the 63951-1 -- see the fit memo's addendum 3
# for the full retirement record). The part STAYS TE 63951-1; what the
# sketch corrected is the PART MODEL and ORIENTATION. The 63951-1 is a flat
# IN-PLANE L stamping: its blade runs ALONG the leg-pitch axis past the
# blade-side leg, standing 2.54-8.89mm OFF the seating face (never lying on
# it) -- dims from TE dwg C=63951 rev L2, lib/datasheets/TE_63951-1.pdf,
# full derivation in the footprint's own descr. Mounted per the sketch:
#   - legs HORIZONTAL through this board's face, leg pitch VERTICAL
#     (the two legs stacked one above the other along Y);
#   - the blade therefore points STRAIGHT DOWN (+Y), descending past the
#     board's bottom edge at a 2.54-8.89mm Z-standoff from the face --
#     "It needs to align vertically so it can actually point down and slot
#     into the clip" (owner);
#   - the whole assembly drops VERTICALLY; each blade enters its main-board
#     Keystone 3586 clip's TOP-entry jaws broadside (the clip's native
#     auto-blade-fuse mode -- a fuse blade dropping straight down is
#     exactly what this clip family was designed around, Keystone dwg 3586);
#   - the daughterboard's own bottom edge FLOATS clear of the main board --
#     "the TAB does the reaching down, not the board" (owner sketch). No
#     part of the board or its copper crosses Edge.Cuts; only the tab's
#     off-board descender (at the Z-standoff) passes below the edge LEVEL,
#     with no material conflict.
# Main-board clip orientation implied: slot axis PERPENDICULAR to this
# board's wall line (the blade's 6.35mm width runs along the wall normal),
# clip's narrow 3.81mm body dimension along the row, clip slot centreline
# offset ~5.72mm from this board's front face (the blade band's centre,
# (2.54+8.89)/2). The main boards carry NO clip placements yet (TB symbols
# exist in their schematics only, no PCB footprints as of this branch), so
# this generator's pcb_placement() remains the authoritative mating drawing.
#
# TWO-BAND LAYOUT (iteration 4, owner follow-up 2026-07-05: "can the agent
# stack the blades right next to each other and put them below the pinout?
# That should tell us how tall these are really going to be"). The solder
# FIELD band sits on top and the TAB ROW sits BELOW it, tabs packed near
# the pitch floor -- superseding iteration 3's side-by-side band (11-13.6mm
# tall but 145mm long on the 24-pin). The <=15mm height cap is EXPLICITLY
# RELAXED by the owner for this form; the deliverable is the honest minimum
# height of the compact layout with length minimized (see pcb_placement's
# derivation -- 20.0mm eps/pcie, 21.4mm atx24). The 24-pin's 2x5 signal
# header still sits beside the field, ROTATED 90 deg, inside the field's
# own Y-band (it costs nothing there).
#
# NO MOUNTING HOLES (owner directive, 2026-07-05). Retention is the Keystone
# clip's own high insertion force (a FEATURE per the owner's 2026-07-04
# ruling -- these joints are not meant for casual swapping) plus chassis
# strain relief on the cable/assembly side, spec Sec.2.8 v1.4.0 (OQ-87 owns
# the numeric pull-force/flex-cycle spec). See each README.
#
# DUAL-FACE TABS: evaluated and REJECTED under the earlier flat-tab model
# (the row-axis shoulder width made cross-face interleaving worth only
# ~5-10%, not the assumed ~50% -- record kept in the READMEs). Under the
# sketch model the question is MOOT a fortiori: each tab is now only
# ~0.84mm thin along the row (stamping plane perpendicular to the face), so
# the row pitch is not body-limited at all -- it is CLIP-limited and
# KEYING-limited (see TAB_PITCH below). Single-face, single-row stands.
# ============================================================================
TAB_PITCH = {   # mm, centre-to-centre, single row -- the per-family KEYING
    # lever (together with tab COUNT and the whole-board no-subset-seating
    # proof in check_output_daughterboards.py).
    # PITCH FLOOR (iteration 5, Keystone 3557 bare clip main-board side,
    # catalog M55 p.41 -- NOT '3557-2', which is the 2-in-1 HOUSED holder,
    # a different line item on the same page): the tab is non-binding
    # (~0.84mm thin; 2.5mm pads). The clip must be rotated so its slot
    # accepts the descending blade BROADSIDE (slot axis // the blade's
    # 6.35mm width = the wall normal -- forced), and in that orientation
    # its LEG PAIR runs ALONG THE ROW. That leg axis was VERIFIED against
    # the mounting details, and it CONTRADICTS the initial working
    # assumption (legs // jaw): the housed 3557-2's detail shows per-clip
    # 3.4mm leg pairs PERPENDICULAR to the 13.5mm fuse axis, and an ATO
    # blade's 5.2mm width runs ALONG the fuse axis (13.5+5.2 = the fuse's
    # ~18.7mm width), so slot // fuse axis, legs PERPENDICULAR to it.
    # Along-row span = the LEG PATTERN, not the 3.8mm body:
    #   floor = 3.4 leg pitch + 2.4 pad (Kd 1.6 drill = the leg dia,
    #           friction fit, +0.4 annulus) = 5.8mm span
    #         + 0.50 stated adjacent-clip solder web (bare brass at
    #           12V-class needs <0.1mm electrically per IPC-2221; 0.5 is
    #           the mechanical/solder number) = 6.3mm
    # (A ~4.5 floor would need a clip with legs INLINE with the slot --
    # this part measurably is not that; vs the 3586's 6.6mm SMD span the
    # 3557 rotation buys only 0.3-0.9mm/pitch. Honest result, reported.)
    # atx24 sits AT the floor -- and 6.3 = 3 x 2.1mm, the field-stub
    # lattice period, so iteration-4's grid alignment carries over (x0 at
    # lattice+1.05; every tab pad/stub/via >=1.05mm off every field
    # stub/via vs the ~0.7mm conflict radius). eps/pcie sit above the
    # floor purely for KEYING deltas.
    # KEYING margins (G/2)*|d| vs the 0.5mm tolerance: eps-in-atx24 (G=5,
    # d=0.4) = 1.00; pcie-in-eps (G=3, d=0.5) = 0.75; pcie-in-atx24
    # (d=0.9) = 1.35 -- all >=1.5x; pattern keying not needed. Teeth
    # re-verified at these pitches (sabotaged eps=7.1, d=0.1 to pcie ->
    # the proof correctly fails).
    "atx24-out-db": 6.3,   # 9 tabs; AT the floor; = 3x2.1 lattice-aligned
    "eps-out-db": 6.7,     # 6 tabs; floor + 0.4 keying delta to atx24
    "pcie-out-db": 7.2,    # 4 tabs; +0.5 to eps, +0.9 to atx24
}

_TAB_CY = cp.courtyard_bbox(TE_TAB_FP)
# Footprint local frame (see the .kicad_mod descr): origin = leg-pair
# midpoint, pads at (0, +/-2.54), +Y = blade/descend direction. The
# courtyard is a thin vertical band (pad envelope +/-1.5mm at the legs,
# +/-0.67mm elsewhere) running from the carrier stub (-4.82) down to the
# blade tip (+16.0) -- deliberately including the descender, which will
# cross the board's bottom edge in 2D (off-board at the Z-standoff; the
# courtyard is kept honest rather than clipped so any future co-planar
# part placed under the descender is flagged). Constants read from the
# footprint, never hand-copied, so a footprint edit cannot desync this:
#   _TAB_HALF_X   row-axis half-extent (pad envelope, 1.5)
#   _TAB_TOP_EXT  extent ABOVE the leg midpoint (carrier stub + margin,
#                 4.82) -- pins the row's Y: tab_y = _TOP_MARGIN + this
#   _TAB_TIP_EXT  extent BELOW the leg midpoint to the blade tip (+16.0
#                 incl. courtyard margin; bare tip +15.75) -- reporting
#                 only (float/seating math), never a board-size driver
_TAB_HALF_X = _TAB_CY[1]
_TAB_TOP_EXT = -_TAB_CY[2]
_TAB_TIP_EXT = _TAB_CY[3]
_TAB_TIP_BARE = 15.75      # dwg-derived blade tip below the leg midpoint
_TAB_BLADE_STANDOFF = (2.54, 8.89)   # blade band off the front face (dwg)

_LEFT_MARGIN, _TOP_MARGIN, _BOTTOM_MARGIN = 1.0, 0.4, 0.4
_FIELD_GAP = 0.1           # field courtyard bottom -> corridor top (atx24 only)


def _field_geom(fam):
    """(fx, fy, field_right, field_bottom) for a family's field connector,
    top-left-anchored at (_LEFT_MARGIN, _TOP_MARGIN)."""
    cfg = FAMILIES[fam]
    bb = cp.courtyard_bbox(cfg["field_fp"])
    fx, fy = _LEFT_MARGIN - bb[0], _TOP_MARGIN - bb[2]
    return fx, fy, fx + bb[1], fy + bb[3]


# Two-band vertical stack constants (iteration 4):
_TAB_PAD_EXT = 2.54 + 1.25   # leg-pair midpoint -> lower pad's copper edge
_TAB_EDGE_MARGIN = 0.55      # lower pad edge -> Edge.Cuts (board-setup
                             # copper-to-edge constraint is 0.5; +0.05 slack
                             # -- the iteration-3 copper_edge lesson applied
                             # up front instead of re-learned)
_BAND_GAP = 0.25             # field courtyard bottom -> tab courtyard top
                             # (courtyard_overlap is a real DRC error class,
                             # so the courtyards may not touch)
_LANE_PAD_CLR = 0.3          # deepest lane band -> tab upper pad edge
                             # (>0.2 zone clearance so the fill never sits at
                             # exact tangency with the pad anti-pad)
_STUB_GRID = 2.1             # the atx24 field-stub X lattice: 4.2mm columns
                             # + the +2.1mm dodge => every field stub/via X
                             # is fx + k*2.1. Tab row anchors mid-window
                             # (lattice + 1.05) so tab stubs/vias clear every
                             # field stub by >= 1.05mm (conflict radius is
                             # ~0.7mm: 0.25 half-width each side + 0.2 clr).


def pcb_placement(fam):
    """TWO-BAND stack (iteration 4, carried into 5): field band on top; the
    single packed tab row BELOW it, every tab at rot 0 (footprint authored
    in mounted orientation: legs stacked vertically at (0,+/-2.54), blade
    descending +Y past the bottom edge). Returns (W, H, P). No mounts.

    tab_y (leg-pair midpoint): eps/pcie = field courtyard bottom +
    _BAND_GAP + the tab's own top extent (carrier stub); atx24 = below the
    corridor instead, with _LANE_PAD_CLR between the deepest lane band and
    the tab's upper pad edge (the pad's In2 anti-pad must never bite a
    lane). H = tab_y + _TAB_PAD_EXT + _TAB_EDGE_MARGIN -- the tab band is
    the lowest thing on every board, so the leg height above the bottom
    edge is a UNIFORM _TAB_PAD_EXT + _TAB_EDGE_MARGIN = 4.34mm platform-
    wide (the seating invariant the checker asserts).

    atx24 x0 is GRID-ALIGNED: smallest x >= _LEFT_MARGIN + _TAB_HALF_X with
    (x - fx) mod _STUB_GRID = 1.05 -- with the 6.3 = 3*2.1 pitch EVERY tab
    sits mid-window between field-stub lattice lines (see TAB_PITCH).

    ITERATION-5 additions (atx24 only): the signal stub J20 (1x4 RA blind-
    mate header, pins down past the edge) sits in the BOTTOM band to the
    RIGHT of the tab row, pad row at H-1.4 (pad bottom edge at the same
    0.55 edge margin as the tabs), pad1 x at tab_last + 3.5 (courtyard-to-
    courtyard clear of the last GND tab); and six DNP sense-return pads
    SR1-6 (CEC_SR_Pad_DNP, PCB-only like the old mounting holes) sit in
    the TOP band's free zone right of the field, 2 rows x 3."""
    cfg = FAMILIES[fam]
    pitch = TAB_PITCH[fam]
    fx, fy, field_right, field_bottom = _field_geom(fam)
    P = {cfg["field_ref"]: (fx, fy, 0)}

    n = len(cfg["tabs"])
    if fam == "atx24-out-db":
        lanes_bottom = field_bottom + _FIELD_GAP + ATX24_CORRIDOR_H
        # upper pad top edge sits _LANE_PAD_CLR below the deepest lane band;
        # _TAB_PAD_EXT is symmetric (2.54 + 1.25 above AND below the midpoint)
        tab_y = lanes_bottom + _LANE_PAD_CLR + _TAB_PAD_EXT
        base = _LEFT_MARGIN + _TAB_HALF_X
        k = math.ceil((base - fx - 1.05) / _STUB_GRID - 1e-9)
        tab0_x = fx + 1.05 + _STUB_GRID * k
    else:
        tab_y = field_bottom + _BAND_GAP + _TAB_TOP_EXT
        tab0_x = _LEFT_MARGIN + _TAB_HALF_X
    tab_last_x = tab0_x + (n - 1) * pitch
    for i, (ref, _net) in enumerate(cfg["tabs"]):
        P[ref] = (tab0_x + i * pitch, tab_y, 0)

    H = tab_y + _TAB_PAD_EXT + _TAB_EDGE_MARGIN
    right_ref = field_right
    if cfg["header"]:
        h = cfg["header"]
        hx = tab_last_x + 3.5                # courtyard-clear of the last tab
        hy = H - 1.4                          # pad bottom edge at H-0.55
        P[h["ref"]] = (hx, hy, 0)
        right_ref = max(right_ref, hx + cp.courtyard_bbox(h["fp"])[1])
    W = max(right_ref, tab_last_x + _TAB_HALF_X) + 1.0
    return W, H, P


def seating_report(tip_clearance=1.0):
    """Per-family seating/float numbers for the README/addendum write-up
    (reporting only -- placement does not consume this). tip_clearance =
    the recommended gap between the seated blade tip and the main-board
    surface (hard stop ~0.4-0.5mm when the tip meets the clip's own SMT
    base metal). Returns {fam: dict}."""
    out = {}
    for fam in FAMILIES:
        W, H, P = pcb_placement(fam)
        tab_y = P[FAMILIES[fam]["tabs"][0][0]][1]
        leg_height = H - tab_y                      # leg midpoint above the bottom edge
        tip_below_edge = _TAB_TIP_BARE - leg_height  # descender past the edge level
        flt = tip_clearance + tip_below_edge         # bottom-edge float above main board
        out[fam] = dict(W=W, H=H, tab_y=tab_y, leg_height=leg_height,
                        tip_below_edge=tip_below_edge, float_=flt,
                        top_above_main=flt + H)
    return out


# A plain 4-layer stack, no net-name hints on the inner layers (unlike
# gen-module-pcb.py's shared LAYERS, which hardcodes In1.Cu="GND" and
# In2.Cu="12V" for the IC-based cable modules -- these daughterboards use
# In2.Cu for SEVERAL different rails on the 24-pin board, so a fixed "12V"
# display-name hint on that layer is actively misleading here).
LAYERS_4L = """\t(layers
\t\t(0 "F.Cu" signal)
\t\t(4 "In1.Cu" signal)
\t\t(6 "In2.Cu" signal)
\t\t(2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)
\t)"""


def build_pcb_base(fam, out_override=None):
    """Assemble the .kicad_pcb: 4-layer stackup (F.Cu / In1.Cu / In2.Cu / B.Cu,
    reusing the platform's existing stackup()), footprints placed + net-
    assigned, NO copper yet (route_pcb lays real copper next, via cec_route)."""
    cfg = FAMILIES[fam]
    bdir = _board_dir(fam)
    netf = f"{bdir}/{cfg['base']}.net"
    # ALWAYS re-export (never trust a stale .net) -- a schematic edit (e.g. a
    # pin/net remap) that isn't followed by a fresh export silently leaves
    # footprints net-tagged from the OLD netlist while any routing code reads
    # the CURRENT config, so the routed copper and the pad disagree; KiCad's
    # own connectivity then "corrects" the mismatch by silently reassigning
    # the track's displayed net to whatever it's actually touching on
    # save/reload (documented elsewhere in this repo as exactly this
    # footgun). Cheap to always regenerate; never worth the staleness risk.
    cp.export_netlist(f"output-daughterboards/{fam}", cfg["base"])
    comps, vals, nets = cp.parse_netlist(netf)
    names = [x for x in sorted(nets) if x]
    code_of = {x: i + 1 for i, x in enumerate(names)}
    padnet = {(r, p): (code_of[x], x) for x, nodes in nets.items() if x for (r, p) in nodes}
    W, H, P = pcb_placement(fam)
    fps = []
    for ref, (x, y, rot) in P.items():
        lib = comps.get(ref)
        if not lib:
            print(f"  WARN no footprint for {ref}", file=sys.stderr); continue
        fps.append(cp.place(lib, ref, x, y, rot, padnet, code_of, val=vals.get(ref)))
    # NO mounting holes -- owner directive 2026-07-05 (see the placement-
    # section docstring above): retention is the Keystone clip's own high
    # insertion force + chassis strain relief on the cable/assembly side, not
    # M3 hardware on this small a board.
    # ITERATION-5 (atx24 only): 6 DNP sense-return pads SR1-6, PCB-only
    # mechanical footprints (no netlist entry, no net -- same convention the
    # mounting holes used). 2 rows x 3 in the top band's free zone right of
    # the field. This is the OQ-88 provision-FORM change only (the old 2x5
    # header's 6 reserved pins); the sense-return decision stays open.
    if fam == "atx24-out-db":
        _fx, _fy, _fr, _fb = _field_geom(fam)
        for i in range(6):
            sx = _fr + 3.0 + (i % 3) * 4.0
            sy = 2.6 + (i // 3) * 4.6
            fps.append(cp.place("cec-Connector_Generic:CEC_SR_Pad_DNP",
                                f"SR{i+1}", sx, sy, 0, padnet, code_of, val=None))
    e = []
    pts = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        e.append(f'\t(gr_line (start {cp.ff(x1)} {cp.ff(y1)}) (end {cp.ff(x2)} {cp.ff(y2)}) '
                 f'(stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{cp.U()}"))')
    netdecl = '\t(net 0 "")\n' + "\n".join(f'\t(net {code_of[x]} "{x}")' for x in names)
    doc = (f"(kicad_pcb\n\t(version 20260206)\n\t(generator \"cec-gen-output-daughterboard\")\n"
           "\t(generator_version \"10.0\")\n\t(general\n\t\t(thickness 1.6)\n"
           "\t\t(legacy_teardrops no)\n\t)\n\t(paper \"A4\")\n" + LAYERS_4L +
           "\n\t(setup\n" + cp.stackup() + "\n\t\t(pad_to_mask_clearance 0)\n"
           "\t\t(allow_soldermask_bridges_in_footprints no)\n\t)\n"
           + netdecl + "\n" + "\n".join(fps) + "\n" + "\n".join(e) +
           "\n\t(embedded_fonts no)\n)\n")
    out = out_override or f"{bdir}/{cfg['base']}.kicad_pcb"
    if os.path.exists(out) and re.search(r"\n\s*\((?:segment|via)\b", open(out).read()) \
            and "--force" not in sys.argv:
        print(f"  SKIP {os.path.relpath(out, ROOT)}: already routed; pass --force"); return out
    open(out, "w").write(doc)
    print(f"WROTE {os.path.relpath(out, ROOT)}  board={W:.1f}x{H:.1f}mm  parts={len(fps)}")
    return out


# ============================================================================
# PCB: real-copper synthesis (cec_route.py, per the repo's routing GO-AHEAD --
# fills real zones via pcbnew's ZONE_FILLER, which kicad-cli cannot do).
#
# Every field-connector and blade-tab pad here is a bare THROUGH-HOLE pad (no
# SMD parts on this board at all), so it carries copper on *every* copper
# layer by construction. That makes a full-board same-net zone auto-clear
# around every FOREIGN-net pad within its outline (the real ZONE_FILLER's
# ordinary pad-clearance behaviour -- the same mechanism an ordinary GND
# plane already relies on) and auto-connect to every pad that IS on its own
# net -- so EPS/PCIe (exactly 2 nets: GND + one power rail) need NO explicit
# tracks/vias at all: GND floods both inner layers (In1.Cu + In2.Cu, matching
# this platform's own EPS/PCIe cable-power convention -- "two GND inners...
# 12V lives on the OUTERS", gen-module-pcb.py's gnd_planes() docstring), and
# the rail floods both outer layers (F.Cu + B.Cu).
# ============================================================================
import importlib.util as _ilu
_s = _ilu.spec_from_file_location("cec_route", f"{HERE}/cec_route.py")
cr = _ilu.module_from_spec(_s); _s.loader.exec_module(cr)


def _board_rect(fam, margin=0.5):
    _W, _H, _P = pcb_placement(fam)
    return [(margin, margin), (_W - margin, margin), (_W - margin, _H - margin), (margin, _H - margin)]


def route_simple(fam):
    """EPS / PCIe: 2-net boards, full-board floods on both layer pairs."""
    out = f"{_board_dir(fam)}/{FAMILIES[fam]['base']}.kicad_pcb"
    r = cr.Router(out)
    rect = _board_rect(fam)
    r.zone("GND", rect, layers=("In1.Cu", "In2.Cu"), clearance=0.3, min_width=0.3)
    r.zone("+12V", rect, layers=("F.Cu", "B.Cu"), clearance=0.3, min_width=0.3)
    r.fill()
    res = r.verify()
    print(f"{fam}: structural={res['n_struct']} unconnected={res['n_unconnected']}")
    if res["structural"]:
        for v in res["structural"][:10]:
            print("  ", v.get("type"), v.get("description"))
    if res["unconnected"]:
        for v in res["unconnected"][:10]:
            print("  UNCONN", v)
    return res


# ---- 24-pin ATX: 8 nets share the board (GND + 7 rails). GND floods In1.Cu
# alone. Of the 7 rails, only FOUR are real multi-point BUSSES (+12V/+5V/
# +3V3/+5VSB: several field pins, one or two tabs each) -- the other THREE
# (-12V/PWR_OK/PS_ON#) are a plain 2-terminal net apiece (exactly one field
# pin to the one matching J_SIG header pin, no tab at all, verified against
# the netlist), so they route as direct point-to-point tracks and need no
# lane/zone at all. That split matters a lot here: it is what makes a
# <=15mm-class board height achievable, and a two-LAYER lane split (tried
# first, reverted) does NOT help the way it looks like it should -- see below.
#
# THE BUG A FIRST PASS SHIPPED (recorded so it is not repeated): parking
# +12V's lane on In2.Cu and +5V's on B.Cu at the SAME nominal corridor Y
# (thinking two layers halve the stack depth) is UNSAFE for a THIN zone. A
# via is a THROUGH feature -- it exists on every copper layer it spans, so a
# +5V via (F.Cu-B.Cu) also crosses In2.Cu at that (x,y), and KiCad's
# ZONE_FILLER auto-clears (anti-pads) it there. That auto-clearance is
# normally harmless (it is exactly how a signal via safely crosses a GND
# plane, platform-wide) BUT only because a plane is wide in BOTH directions:
# copper can route around the clearance hole. A 0.3mm-tall LANE has no
# "around" -- a via whose keepout diameter (dia + 2*clearance, ~0.9mm here)
# exceeds the lane's own height clears the lane's FULL height at that one X,
# severing it into a left island and a right island. Measured DRC symptom:
# real "unconnected_items" between two ends of the SAME zone/net that should
# obviously be one piece. Putting the two layers' slots at DIFFERENT Y (half
# a pitch apart) does not fix it either: the safe stand-off a via needs from
# a FOREIGN-layer lane it merely passes near is via_keepout_radius +
# lane_half_height + min_width (~0.45+0.15+0.2 = 0.8mm here) -- i.e. the same
# separation the four real lanes already need from EACH OTHER on one layer.
# Two layers buy nothing once every "slot" carries a via; the fix is fewer
# lanes (drop the 3 point-to-point signals out of the lane scheme entirely),
# not more layers.
#
# The real ATX-24 pinout INTERLEAVES rails column-by-column (row0 y=0 / row1
# y=5.5 share the same 12 X-positions), so a field pin's straight-down stub
# can run directly into the OPPOSITE row's pad if that pad is a DIFFERENT
# net. Only ROW0 pins ever need to dodge (row1 has nothing below it at its
# own column except the clear corridor). The dodge is a single +2.1mm (half
# the 4.20mm pitch) sideways jog -- landing dead-centre in the gap between
# two adjacent pad columns, symmetric ~0.75mm clear of both neighbours' pad
# edges -- taken PERMANENTLY, which keeps every column's own stub on a
# unique X for its whole length (0.5mm steps can never coincide with another
# column's integer-pitch X, so dodged and undodged stubs never collide).
ATX24_BUS_NETS = ["+12V", "+5V", "+3V3", "+5VSB"]              # get a corridor lane
ATX24_P2P_NETS = ["-12V", "PWR_OK", "PS_ON#"]                  # field pin <-> header pin direct
ATX24_LANE_SLOT = {net: i for i, net in enumerate(ATX24_BUS_NETS)}   # slot 0 = nearest the field
_LANE_PITCH, _LANE_HALF = 0.65, 0.15    # 0.3mm-wide lane zone, single layer (In2.Cu)
ATX24_CORRIDOR_H = (len(ATX24_BUS_NETS) - 1) * _LANE_PITCH + 2 * _LANE_HALF
# Lane-entry via: SMALLER than the platform-default 0.5/0.9mm power via on
# purpose -- adjacent slots at 0.65mm pitch cannot safely hold 0.9mm-diameter
# vias. 0.3/0.5mm is close to this repo's own existing "Sense"/small-signal
# via convention (modules/12vhpwr-standard's Sense netclass, 0.6/0.3) sized
# down slightly further; currents here are the modest per-pin fan-out
# figures documented in the board README, never the rail's own aggregate
# (that rides the 9 blade-clip joints, sized separately).
_LANE_VIA_DRILL, _LANE_VIA_DIA = 0.3, 0.5


def _atx24_lane_y(field_bottom, net):
    """Y of a bus rail's lane centreline in the corridor (single layer, In2.Cu)."""
    return field_bottom + _FIELD_GAP + _LANE_HALF + ATX24_LANE_SLOT[net] * _LANE_PITCH


# kicad-cli's netlist export prefixes a ROOT-SHEET plain text label (no power-
# port symbol behind it) with "/" (the root sheet's own path) -- the power-
# port-backed rails (+12V/+5V/+3V3/+5VSB/GND) are GLOBAL nets and keep their
# bare name, but -12V/PS_ON#/PWR_OK ride plain `label`s (no "-12V"/"PS_ON#"
# power symbol exists in this platform's library) and so come back
# "/-12V"/"/PS_ON#"/"/PWR_OK" on the actual board. Map at the routing layer
# only -- the schematic/config data above stays on the readable bare names.
_PCB_NET = {n: (f"/{n}" if n in ("-12V", "PS_ON#", "PWR_OK") else n)
            for n in ATX24_BUS_NETS + ATX24_P2P_NETS}


def route_atx24():
    fam = "atx24-out-db"
    cfg = FAMILIES[fam]
    out = f"{_board_dir(fam)}/{cfg['base']}.kicad_pcb"
    r = cr.Router(out)
    rect = _board_rect(fam)
    r.zone("GND", rect, layers=("In1.Cu",), clearance=0.3, min_width=0.3)

    W, H, P = pcb_placement(fam)
    fx, fy, _field_right, field_bottom = _field_geom(fam)

    lane_x0, lane_x1 = 2.0, W - 2.0
    for net in ATX24_BUS_NETS:
        ly = _atx24_lane_y(field_bottom, net)
        pn = _PCB_NET.get(net, net)
        r.zone(pn, [(lane_x0, ly - _LANE_HALF), (lane_x1, ly - _LANE_HALF),
                   (lane_x1, ly + _LANE_HALF), (lane_x0, ly + _LANE_HALF)],
               layers=("In2.Cu",), clearance=0.2, min_width=0.2)

    # field pins (1-24): row0 = pins 1-12 @ local y=0, row1 = pins 13-24 @
    # y=5.5 -- see the module-level comment above for the dodge rationale.
    # BUS nets (+12V/+5V/+3V3/+5VSB) run down into their In2.Cu lane. P2P
    # nets (-12V/PWR_OK/PS_ON#) stay entirely within the field's own row-gap
    # (y in [row0, row1], never entering the corridor at all) and connect
    # straight across to their header pin -- see the header block below.
    via_seen = set()
    for pin, net in cfg["field_net"].items():
        if net is None or net == "GND" or net in ATX24_P2P_NETS:
            continue
        pn = _PCB_NET.get(net, net)
        by = _atx24_lane_y(field_bottom, net)
        row = 0 if pin <= 12 else 1
        col = (pin - 1) % 12
        x, y = fx + col * 4.2, fy + (0.0 if row == 0 else 5.5)
        opp_net = cfg["field_net"][pin + 12 if row == 0 else pin - 12]
        conflict = (row == 0) and (opp_net != net)
        if conflict:
            pts = [(x, y), (x, y + 2.2), (x + 2.1, y + 2.2), (x + 2.1, by)]
        else:
            pts = [(x, y), (x, by)]
        r.track(pn, pts, "F.Cu", 0.5)
        via_pt = (round(pts[-1][0], 3), round(pts[-1][1], 3), net)
        if via_pt not in via_seen:
            r.via(pn, pts[-1], drill=_LANE_VIA_DRILL, dia=_LANE_VIA_DIA, layers=("F.Cu", "B.Cu"))
            via_seen.add(via_pt)

    # tabs (all 4 BUS nets have >=1): legs stacked VERTICALLY at
    # (tx, tab_y +/- 2.54) per the sketch-model footprint, sitting BELOW the
    # corridor in the iteration-4 two-band stack (tab_y ~17.0, lanes
    # ~10.9-12.8), sharing the corridor's X range with the FIELD's own
    # dodge-stubs/vias -- which is exactly why the row is GRID-ALIGNED (see
    # TAB_PITCH/_STUB_GRID): every tab X sits 1.05mm off the field-stub
    # lattice, so these F.Cu stubs/vias clear every field stub/via by
    # >=1.05mm against a ~0.7-0.75mm conflict radius. Each tab's stub runs
    # UP from its UPPER leg pad into its net's lane. The TE_63951-1
    # footprint has TWO physical pads, both numbered "1" (one electrical
    # node), but "same pad number" is a netlist LABEL, not copper -- the
    # footprint has no internal bridge, so both need real copper: a vertical
    # bridge track between the two legs -- on B.Cu as of iteration 5, so the
    # signal stub's F.Cu mid-band runs (below) cross the bridges layer-clean
    # -- plus the F.Cu up-stub off the upper leg + a via at its own lane's
    # centreline (clearing the 0.65mm-pitch neighbours by the same measured
    # 0.25mm the field vias rely on). The tab pads' own In2 anti-pads stay
    # _LANE_PAD_CLR clear of the deepest lane band by placement.
    for ref, net in cfg["tabs"]:
        if net == "GND":
            continue
        pn = _PCB_NET.get(net, net)
        tx, ty, _ = P[ref]
        by = _atx24_lane_y(field_bottom, net)
        r.track(pn, [(tx, ty - 2.54), (tx, ty + 2.54)], "B.Cu", 0.5)
        r.track(pn, [(tx, ty - 2.54), (tx, by)], "F.Cu", 0.5)
        r.via(pn, (tx, by), drill=_LANE_VIA_DRILL, dia=_LANE_VIA_DIA, layers=("F.Cu", "B.Cu"))

    # 1x4 blind-mate signal stub (iteration 5, memo addendum 5): J20's pads
    # sit in the BOTTOM band right of the tab row (pins point down past the
    # edge). The 3 signals fan DOWN from their field pins on F.Cu, through
    # the corridor band (crossing In2 lanes on a different layer, ZERO
    # vias -- every endpoint is a THT pad) and through the tab band, then
    # run RIGHT in the tab band's inter-pad window and drop onto the
    # header pads. Deterministic collision-freedom, all hand-derived:
    #   - DESCENT XS: -12V straight down its own column c1; PS_ON# down c3
    #     then a -2.1 jog at y=10.55 (the 0.6mm band between row1 pads and
    #     the first lane -- legal because the lanes are In2 and this is
    #     F.Cu; only F.Cu items constrain, and no bus stub X lands inside
    #     either jog span); PWR_OK (a row0 pin) takes the standard +2.1
    #     dodge past pin 20's NC pad, jogs back to c7 at y=10.55. All
    #     three descents are then ~ (lattice) x's == phase 3.15 of the
    #     6.3mm tab grid (x0 anchors at lattice+1.05), i.e. dead-centre of
    #     the tab-pad gaps: 3.15mm to the nearest tab pad (need 1.55),
    #     3.15 to tab stubs (F.Cu, need 0.7), >=2.1 to every bus stub/via.
    #   - MID-BAND WINDOW: between the tab pads' inner edges
    #     [upper 15.75+0.3, lower 18.33-0.3] = [16.05, 18.03]; levels
    #     16.55/17.05/17.55 (0.5 steps). The tab BRIDGES were moved to
    #     B.Cu above precisely so these F.Cu runs cross them layer-clean.
    #   - NESTING: leftmost descent = deepest level AND leftmost header
    #     pad; descents c1 < c3-2.1 < c7 map to pads 1..3 = -12V, PS_ON#,
    #     PWR_OK (the ATX24_HEADER_NET order -- chosen FOR this). Each
    #     horizontal then passes only descents/drops whose spans it clears
    #     by >=0.3 (checked pairwise when this was derived).
    #   - DROPS: from each level down to the header pad row (hy). GND
    #     (pad 4) rides the In1 plane; no track.
    h = cfg["header"]; hhx, hhy, _ = P[h["ref"]]
    pad_x = {i + 1: hhx + 2.54 * i for i in range(4)}
    jog_y = 10.55
    lvl = {"-12V": 17.55, "PS_ON#": 17.05, "PWR_OK": 16.55}

    def _col_xy(net):
        pin = [p for p, n in cfg["field_net"].items() if n == net][0]
        row = 0 if pin <= 12 else 1
        col = (pin - 1) % 12
        return fx + col * 4.2, fy + (0.0 if row == 0 else 5.5)

    x1, y1 = _col_xy("-12V")     # c1, row1
    x3, y3 = _col_xy("PS_ON#")   # c3, row1
    x7, y7 = _col_xy("PWR_OK")   # c7, row0
    P2P_TRACK_W = 0.2
    header_paths = {
        "-12V": [(x1, y1), (x1, lvl["-12V"]), (pad_x[1], lvl["-12V"]),
                 (pad_x[1], hhy)],
        "PS_ON#": [(x3, y3), (x3, jog_y), (x3 - 2.1, jog_y),
                   (x3 - 2.1, lvl["PS_ON#"]), (pad_x[2], lvl["PS_ON#"]),
                   (pad_x[2], hhy)],
        "PWR_OK": [(x7, y7), (x7, y7 + 2.2), (x7 + 2.1, y7 + 2.2),
                   (x7 + 2.1, jog_y), (x7, jog_y), (x7, lvl["PWR_OK"]),
                   (pad_x[3], lvl["PWR_OK"]), (pad_x[3], hhy)],
    }
    for net, pts in header_paths.items():
        pn = _PCB_NET.get(net, net)
        r.track(pn, pts, "F.Cu", P2P_TRACK_W)

    r.fill()
    res = r.verify()
    print(f"{fam}: structural={res['n_struct']} unconnected={res['n_unconnected']}")
    if res["structural"]:
        for v in res["structural"][:20]:
            print("  ", v.get("type"), v.get("description"))
    if res["unconnected"]:
        for v in res["unconnected"][:20]:
            print("  UNCONN", v)
    return res


# ============================================================================
# Netclasses / DRU -- sized to what was actually routed above (§1's per-family
# current targets; the ratified 125% margin, no reservation on the pigtail/
# MODDIY THT field itself, which is a hand-solder/press-fit destination, not
# a routed net).
# ============================================================================
def write_rules(fam):
    cfg = FAMILIES[fam]
    bdir = _board_dir(fam)
    pro = f"{bdir}/{cfg['base']}.kicad_pro"
    dru = f"{bdir}/{cfg['base']}.kicad_dru"
    if fam == "atx24-out-db":
        classes = [cp.netclass("Default", 0.25, 0.6, 0.3, 2147483647),
                   cp.netclass("Power", 0.5, 0.9, 0.5, 1, clr=0.25),
                   cp.netclass("Signal", 0.4, 0.9, 0.5, 2, clr=0.2)]
        patterns = [("Power", "+12V"), ("Power", "+5V"), ("Power", "+3V3"),
                    ("Power", "+5VSB"), ("Power", "GND"),
                    ("Signal", "/-12V"), ("Signal", "/PWR_OK"), ("Signal", "/PS_ON#")]
        header = ("24-pin ATX daughterboard -- 9 blade-tab joints "
                  "(12V x1 / 5V x2 / 3.3V x1 / 5VSB x1 / GND x4) + a 2x5 "
                  "signal stub (PWR_OK/PS_ON#/-12V + GND-ref + 6 reserved), "
                  "standing perpendicular to the main board, tabs blade-"
                  "down per the owner's 2026-07-05 sketch. Power netclass "
                  "0.5mm/0.9-0.5mm via matches the 0.5mm stub tracks laid "
                  "by route_atx24(); each of the 4 bus rails also gets its "
                  "own thin In2.Cu lane zone in the corridor below the "
                  "field (0.3mm wide, 0.65mm pitch -- not netclass-"
                  "controlled, drawn directly; see ATX24_LANE_SLOT), which "
                  "the tab row's down-stubs and the field's dodge-stubs "
                  "meet through 0.3/0.5mm vias.")
    else:
        rail = "+12V"
        classes = [cp.netclass("Default", 0.25, 0.6, 0.3, 2147483647),
                   cp.netclass("Power", 1.0, 0.9, 0.5, 1, clr=0.3)]
        patterns = [("Power", rail), ("Power", "GND")]
        header = (f"{fam}: 2-net board (GND + {rail}), both flooded full-"
                  f"board on their own layer pair (GND: In1.Cu+In2.Cu; "
                  f"{rail}: F.Cu+B.Cu) -- the Power netclass documents the "
                  f"floor width/via for any hand-touch-up, not the pours "
                  f"themselves (drawn directly by route_simple()).")
    cp.write_netclasses(pro, classes, patterns)
    cp.write_dru(dru, [("Power min width", "track_width (min 0.4mm)",
                        "A.NetClass == 'Power'")], header=header)


if __name__ == "__main__":
    fams = sys.argv[1:2]
    fams = list(FAMILIES) if (not fams or fams[0] in ("all", "--force")) else fams
    for fam in fams:
        if fam not in FAMILIES:
            raise SystemExit(f"unknown family: {fam} (choices: {', '.join(FAMILIES)}, all)")
        gen_schematic(fam)
        build_pcb_base(fam)
        if fam == "atx24-out-db":
            route_atx24()
        else:
            route_simple(fam)
        write_rules(fam)
