#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  gen-output-daughterboard -- §2.8 v1.4.0 output-connector daughterboards
# ============================================================================
# Builds the three passive-daughterboard projects under
# beta/output-daughterboards/ (24-pin ATX / EPS 8-pin per-cable / PCIe
# 8-pin per-cable, the last shared unmodified by the 2-port and 3-port SKUs).
# Per family: TE 63951-1 right-angle FASTON tabs (input side; blades point
# straight DOWN past the board's bottom edge and drop into the MAIN board's
# TE 63969-1 FASTON PCB receptacles top-entry, per the owner's 2026-07-05
# sketch + the 2026-07-06 iteration-7 ratification -- receptacles NOT built
# here, no main-board PCB placement exists yet)
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
ATX24_TABS = [  # (ref, net) -- 10 tabs, group sizes 1/2/2/1/4. ITERATION-7
    # COUNT (owner-ratified 2026-07-06): the TE 63969-1 receptacle's 22.9A
    # base rating (108-1706, 30degC-rise method) under the ratified 125%
    # policy allows 18.32A/joint; the 3V3 rail's 4 circuits x the 6A ATX bar
    # = 24.0A no longer fits ONE joint (95%) -> +3V3 gains a second tab
    # (12.0A/joint, 191%). Full per-rail re-derivation: 12V 2x6=12.0A/1
    # joint (191%); 5V 5x6=30.0A/2 (153%); 3V3 24.0A/2 (191%); 5VSB 6.0A/1
    # (382%); GND return = sum 72.0A/4 = 18.0A/joint = 127.2% -- LEGAL but
    # HAIRLINE (0.32A headroom; a 5th GND joint would give 158% at 11 tabs
    # total -- surfaced to the owner, who ratified the policy application at
    # 10). See blade-fit memo addendum 7.
    ("J10", "+12V"), ("J11", "+5V"), ("J12", "+5V"), ("J13", "+3V3"),
    ("J14", "+3V3"), ("J15", "+5VSB"),
    ("J16", "GND"), ("J17", "GND"), ("J18", "GND"), ("J19", "GND"),
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
                net=ATX24_HEADER_NET, value="TSW-104-12-G-S-RA"),
    W=140.0, H=75.0,
)

# ---- EPS 8-pin (per cable): 6 blade joints (3/polarity -- HOLDS at the
# iteration-7 TE 63969-1 rating: 52A cable basis / 3 = 17.33A/joint = 132%
# of 22.9A, above the ratified 125% floor), 4x12V+4xGND field,
# reuses the generic cec:CEC_CONN_2x4 symbol (unnamed pins; nets assigned by
# wiring, matching the platform's own corrected EPS pinout: 1-4=GND,5-8=+12V).
EPS8_FIELD_NET = {1: "GND", 2: "GND", 3: "GND", 4: "GND",
                  5: "+12V", 6: "+12V", 7: "+12V", 8: "+12V"}
EPS8_TABS = [  # 6 tabs, groups of 3 (GND then 12V) -- keying: pitch delta vs
    # pcie (which now ALSO has 6 tabs, iteration 7) + count vs atx24 (10),
    # carried by the checker's no-subset proof.
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

# ---- PCIe 8-pin (per cable, shared by 2-port/3-port): 6 blade joints
# (3/polarity -- ITERATION-7 COUNT, owner-ratified 2026-07-06: the cable's
# ~39A sustained basis over 2 joints = 19.5A/joint = 117% of the TE
# 63969-1's 22.9A rating, under the ratified 125% floor -> 3/polarity =
# 13.0A/joint, 176%), 3x12V+3xGND+2 sense field (SENSE0/1 tied to the GND
# net directly -- "tied per the PCIe CEM convention on the daughterboard
# copper", spec §2.8 v1.4.0; no dedicated blade tab, negligible current).
PCIE8_FIELD_NET = {1: "+12V", 2: "+12V", 3: "+12V",
                   4: "GND", 5: "GND", 6: "GND", 7: "GND", 8: "GND"}
PCIE8_TABS = [  # 6 tabs, groups of 3 (12V then GND). NOTE pcie now has the
    # SAME tab count as EPS (6) -- keying between them rests on the pitch
    # delta alone, carried by the checker's no-subset proof (margin 1.25 =
    # 2.5x the 0.5mm tolerance at d=0.5; see TAB_PITCH).
    ("J10", "+12V"), ("J11", "+12V"), ("J12", "+12V"),
    ("J13", "GND"), ("J14", "GND"), ("J15", "GND"),
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
    # The current production line lives under beta/output-daughterboards.
    # Writing to modules/ silently created a second, untracked tree and left
    # the actual BETA board stale, defeating the generator's own contract.
    return f"{ROOT}/beta/{FAMILIES[fam]['dirn']}"


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
                   "and drops top-entry into the main board's TE 63969-1 "
                   "FASTON PCB receptacle (iteration 7, owner-ratified "
                   "2026-07-06 -- the DESIGNED mate: rev-E dwg note 3 puts "
                   "our 0.81mm blade at its thickness design centre; the "
                   "receptacle's 5.08mm hole pair runs along the blade "
                   "plane, plan-congruent with this tab's own leg holes) -- "
                   "spec Sec. 2.8 v1.4.0 / docs/standard-tier-review/"
                   "output-daughterboard-study-2026-07-04.md Sec.8.9-8.10 / "
                   "blade-fit-check-2026-07-04.md addenda (3 = tab "
                   "geometry, 6-7 = the receptacle study + orientation "
                   "chain).",
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
    "Manufacturer": "Samtec", "MPN": "TSW-104-12-G-S-RA", "LCSC": "",
    "Datasheet": "https://www.samtec.com/products/tsw-104-12-g-s-ra",
    "Description": "1x4 2.54mm RIGHT-ANGLE TSW header with 14.99mm E dimension -- blind-mate signal stub, "
                   "pins down past the bottom edge parallel to the blades, "
                   "mating the main board's vertical 1x4 female socket in "
                   "the same drop (owner, 2026-07-05; memo addendum 5). "
                   "The exact TSW-104-12-G-S-RA ordering code is valid in the Samtec TSW series; "
                   "consigned assembly is acceptable. Keyed-JST-PH (S4B/B4B-PH-K-S, the "
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
# Main-board mate orientation (ITERATION 7, owner-ratified 2026-07-06 --
# supersedes the iteration-5 Keystone 3557 clip): TE 63969-1 FASTON PCB
# receptacle, vertical/top entry. Its slot's WIDE dimension lies in the
# blade's plane -- the blade's 6.35mm width runs along the wall normal, and
# the receptacle's two Ø1.40 PCB holes (5.08mm pitch) run along that SAME
# axis, PERPENDICULAR to the row, plan-congruent with the blade's own leg
# holes ("aligned in the same way as the blade's holes", owner). Only the
# receptacle's un-dimensioned ~3.7mm across-thickness depth lies along the
# row. Slot/hole-pair centreline offset ~5.72mm from this board's front
# face (the blade band's centre, (2.54+8.89)/2). The main boards carry NO
# receptacle placements yet (TB symbols exist in their schematics only, no
# PCB footprints as of this branch), so this generator's pcb_placement()
# remains the authoritative mating drawing, and the checker asserts the
# hole-axis orientation against MAIN_RCPT_FP per position.
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
    # PITCH FLOOR (iteration 7, TE 63969-1 FASTON PCB receptacle main-board
    # side -- owner-ratified 2026-07-06, superseding the iteration-5
    # Keystone 3557 clip; full study = blade-fit memo addendum 6, orientation
    # chain = addendum 7 + the receptacle footprint's own descr): the tab is
    # non-binding (~0.84mm thin; 2.5mm pads). The receptacle is the DESIGNED
    # mate for this exact blade (rev-E dwg note 3: mating tab 0.81+/-0.025 =
    # our thickness AT design centre). ORIENTATION (owner requirement,
    # verified from the rev-E views): the receptacle's two Ø1.40 PCB holes at
    # 5.08mm pitch run ALONG THE TAB-WIDTH AXIS = the WALL NORMAL,
    # perpendicular to the row -- plan-congruent with the blade's own
    # Ø1.40/5.08 leg-hole pair in its vertical stamping plane ("aligned in
    # the same way as the blade's holes"). So NEITHER the leg pattern NOR
    # the 7.42mm roll span lies along the row; the along-row footprint is
    # only the receptacle's ACROSS-THICKNESS DEPTH:
    #   floor = 3.7 depth (UN-DIMENSIONED on rev E -- proportional estimate
    #           from the 8:1 Section A-A, band 3.4-3.7, constructive upper
    #           bound ~4.0; THE #1 OQ-86 SAMPLE ITEM for this part)
    #         + 0.50 bare-brass adjacent-body air gap (different nets;
    #           IPC-2221 needs <0.1mm electrically at 12V-class, 0.5 is the
    #           mechanical/assembly number) = 4.2mm
    # (vs the 3557's 6.3mm leg-pattern floor -- the receptacle's rotation-
    # free hole axis is what buys the 2.1mm/pitch). Pad web is NOT the
    # driver here: pads are Ø2.4 at (0,+/-2.54) along Y, so along-row web =
    # pitch - 2.4 = 1.8mm at the floor. DEPTH GATE: if the sample measures
    # depth > 4.0mm, atx24 falls back to the 6.3mm (3-lattice) pitch; eps/
    # pcie re-derive at measured depth + 0.5 + keying deltas.
    # atx24 sits AT the floor -- and 4.2 = 2 x 2.1mm, the field-stub
    # lattice period, so the grid alignment carries over (x0 at
    # lattice+1.05; every tab pad/stub/via >=1.05mm off every field
    # stub/via vs the ~0.7mm conflict radius). NOTE the iteration-5 descent
    # phase trick (lattice columns landing mid-gap at phase 3.15 of 6.3)
    # does NOT survive a 4.2 pitch -- lattice columns now land at phases
    # 1.05/3.15, both 1.05 from a tab pad centre (pad radius 1.25 =
    # collision), so route_atx24 JOGS each signal descent to a COMPUTED
    # mid-gap column (x0 + 2.1 mod 4.2) at jog_y before it enters the tab
    # band. eps/pcie sit above the floor purely for KEYING deltas.
    # KEYING at the iteration-7 counts (atx24 10 / eps 6 / pcie 6 -- eps and
    # pcie now have EQUAL counts, so pitch differentiation alone carries the
    # no-subset proof between them): worst centred-overlay deviation
    # (G/2)*|d| vs the 0.5mm tolerance: eps-vs-pcie (G=5, d=0.5) = 1.25;
    # eps-in-atx24 (G=5, d=0.5) = 1.25; pcie-in-atx24 (G=5, d=1.0) = 2.50 --
    # all >=2.5x tolerance; pattern keying not needed. Teeth re-verified at
    # these pitches (sabotage: pcie=4.8, d=0.1 to eps -> the proof correctly
    # fails).
    "atx24-out-db": 4.2,   # 10 tabs; AT the floor; = 2x2.1 lattice-aligned
    "eps-out-db": 4.7,     # 6 tabs; floor + 0.5 keying delta to atx24
    "pcie-out-db": 5.2,    # 6 tabs; +0.5 to eps, +1.0 to atx24
}

# TE 63969-1 -- the MAIN-BOARD mate (owner-ratified 2026-07-06, iteration 7;
# blade-fit memo addenda 6-7): FASTON .250/.205 PCB receptacle, vertical/top
# entry, designed for the 63951-1's exact 6.35 x 0.81 blade. Populated
# default 63969-1 (LCSC C2961150, stock ~5 -- restock watch; DigiKey depth
# ~$0.30, owner-acquired path fine); 63968-1 = the LOW-INSERTION-FORCE
# drop-in fallback on the SAME land (catalog 82004 p.46 Style A: identical
# A/L dims and the same recommended 5.08/Ø1.40 hole pair; mate force <=26N
# vs <=44N). The main boards carry this part on their TB refs (schematics
# only -- no main-board PCB placement exists on this branch); this
# generator's pcb_placement() remains the authoritative mating drawing, and
# the checker asserts the hole-axis orientation against this footprint.
MAIN_RCPT_FP = "cec-Connector_Blade:TE_63969_FASTON_Receptacle_250_Vertical_THT"
MAIN_RCPT_HEIGHT = 8.38    # above-board profile (rev E: 12.19 total - 3.81 tails)

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

# atx24 SR1-6 DNP sense-return pads (OQ-88 provision form): 2 cols x 3 rows
# right of the field. ITERATION-7 repack (was 3x2 at 4.0mm columns): the
# board lost ~13mm of length to the 4.2mm pitch, and the old grid's third
# column pushed SR6 onto the Edge.Cuts (2 real copper_edge_clearance hits at
# regen -- caught by DRC, fixed by making pcb_placement() OWN the SR extent
# in W instead of hoping the row length covers it). Pad is 2.0 x 2.5.
_SR_X_OFF, _SR_Y0 = 2.4, 2.6          # grid anchor from (field_right, top)
_SR_COL_PITCH, _SR_ROW_PITCH = 3.2, 4.6
_SR_COLS, _SR_ROWS = 2, 3
_SR_HALF_W = 1.0                      # pad half-width (2.0mm pad)


def _sr_positions(field_right):
    """SR1-6 pad centres (atx24 only)."""
    return [(field_right + _SR_X_OFF + (i % _SR_COLS) * _SR_COL_PITCH,
             _SR_Y0 + (i // _SR_COLS) * _SR_ROW_PITCH) for i in range(6)]


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
        # anchor step = the full pitch (4.2 = 2 lattice periods at iteration
        # 7), NOT the bare 2.1 lattice -- the iteration-5 lesson (a 2.1-step
        # anchor rotated the descent phase onto tab pads, measured as real
        # shorting_items) is kept structurally even though route_atx24 now
        # COMPUTES its mid-gap descent columns from x0 (x0 + 2.1 mod pitch)
        # instead of assuming a fixed lattice phase: full-pitch stepping
        # keeps the mid-gap set itself lattice-stable (every mid-gap X
        # >= 1.05mm from every field stub/via, same guarantee the tabs get).
        step = TAB_PITCH[fam]
        assert abs(step / _STUB_GRID - round(step / _STUB_GRID)) < 1e-9, \
            "atx24 pitch must be a whole number of 2.1mm lattice periods"
        k = math.ceil((base - fx - 1.05) / step - 1e-9)
        tab0_x = fx + 1.05 + step * k
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
    if fam == "atx24-out-db":
        # the SR pad grid is PCB-only (placed in build_pcb_base) but its
        # copper is board content all the same -- W must own it (iteration-7
        # lesson: the shrunken board put SR6 on the edge when W didn't).
        sr_right = max(x for x, _y in _sr_positions(field_right)) + _SR_HALF_W
        right_ref = max(right_ref, sr_right)
    W = max(right_ref, tab_last_x + _TAB_HALF_X) + 1.0
    return W, H, P


def seating_report(tip_clearance=1.0):
    """Per-family seating/float numbers for the README/addendum write-up
    (reporting only -- placement does not consume this). tip_clearance =
    the recommended gap between the seated blade tip and the main-board
    surface (the TE 63969-1 receptacle is open at the bottom between its
    two solder tails, so the tab tip's hard stop is the main-board surface
    itself; the cantilevered floor is a vertical backing plate, not a
    bottom stop -- rev E / 114-2156 Fig 1). rcpt_top_clear = how far the
    board's own bottom edge floats ABOVE the receptacle's 8.38mm top.
    Returns {fam: dict}."""
    out = {}
    for fam in FAMILIES:
        W, H, P = pcb_placement(fam)
        tab_y = P[FAMILIES[fam]["tabs"][0][0]][1]
        leg_height = H - tab_y                      # leg midpoint above the bottom edge
        tip_below_edge = _TAB_TIP_BARE - leg_height  # descender past the edge level
        flt = tip_clearance + tip_below_edge         # bottom-edge float above main board
        out[fam] = dict(W=W, H=H, tab_y=tab_y, leg_height=leg_height,
                        tip_below_edge=tip_below_edge, float_=flt,
                        rcpt_top_clear=flt - MAIN_RCPT_HEIGHT,
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
    cp.export_netlist(f"output-daughterboards/{fam}", cfg["base"], tree="beta")
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
        for i, (sx, sy) in enumerate(_sr_positions(_fr)):
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
    # ZONE_CONNECTION_FULL on both power floods, matching route_atx24's F1-fix
    # rationale (owner observation 2026-07-06: eps/pcie were on the KiCad-default
    # THERMAL RELIEF). A thermal-relief pad necks a high-current joint through
    # four ~0.5mm spokes -- unwanted on a 52A (eps) / 39A (pcie) tab where the pad
    # IS the current path: it raises local J and joint resistance for zero benefit
    # on a hand-assembled THT board (no reflow-soldering thermal-shadow problem to
    # relieve). Solid = the pad's full copper carries the joint.
    import pcbnew as _pcbnew
    zs = [r.zone("GND", rect, layers=("In1.Cu", "In2.Cu"), clearance=0.3, min_width=0.3),
          r.zone("+12V", rect, layers=("F.Cu", "B.Cu"), clearance=0.3, min_width=0.3)]
    for _z in zs:
        _z.SetPadConnection(_pcbnew.ZONE_CONNECTION_FULL)
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


# ---- 24-pin ATX: 8 nets share the board (GND + 7 rails). ITERATION-11
# (2026-07-06, the F1 FIX -- docs/standard-tier-review/blade-interconnect-
# thermal-2026-07-06.md finding F1): the iteration-4/5 corridor of four
# 0.3mm x 1oz In2.Cu LANES carried the full per-rail AGGREGATES (the owner
# design basis puts 12V=12A, 5V=30A, 3V3=24A, 5VSB=6A, GND=72A across this
# board between the tab groups and the output field -- the old comments'
# "modest per-pin fan-out" premise was wrong), measured catastrophic by the
# full-stack solve: DC-IR 384mV @30A on +5V (J~2900 A/mm2, ~7x the fusing
# gate) and a runaway coupled solve. THE FIX IS POURS, the eps/pcie style:
# every terminal on this board is THT (field pins, tab legs, header pins),
# so a full-board flood on ANY single layer connects a rail's whole node
# with ZERO vias -- each of the three big rails gets one WHOLE LAYER:
#
#   F.Cu  (2oz) +5V   30A   flood (+ the 3 signal P2P tracks slot through)
#   In1.Cu(1oz) GND   72A   flood (unchanged from iteration 4)
#   In2.Cu(1oz) +12V  12A   flood
#   B.Cu  (2oz) +3V3  24A   flood (+ the +5VSB track chain slots through)
#
# +5VSB (6A, the smallest rail) is the odd one out (4 big rails, 3 free
# layers): it runs as a DETERMINISTIC B.Cu TRACK CHAIN from its one field
# pin (pin 9) to its one tab (J15), routed EAST-AND-AROUND the field:
# through the inter-row gap band, down the pad-free column EAST of the
# field (past col 11 -- the only place a wide descent clears the 2.7mm-wide
# oval field pads), then WEST through the TAB MID-BAND (between the tab
# pads' upper and lower rows -- empty on B.Cu now that the iteration-5 tab
# bridge tracks are superseded by the floods) into J15's leg pair. Slot
# geometry is chosen so the B.Cu band under row1 (y in [row1 antipad
# bottom, tab antipad top], 2.55mm tall) stays UNCUT west of the descent:
# that band is +3V3's east-pin passage (pin 12, col 11, 6A -- its only
# path west to its tabs) and is asserted below.
#
# HISTORICAL (iterations 4-5, kept so the lesson is not re-learned): a thin
# LANE zone dies by via anti-pad -- a through-via clears every layer it
# spans, and a 0.3mm-tall lane has no "around", so a foreign-layer via
# whose keepout exceeds the lane height severs it (measured as real
# unconnected_items). Full-layer FLOODS change that calculus completely (a
# plane is wide in both directions; and this board now has no vias at
# all), which is why the flood plan is safe where the two-layer lane split
# measurably was not. The corridor BAND geometry itself (ATX24_CORRIDOR_H
# below) is retained: it is frozen board GEOMETRY (it sets tab_y, and the
# F1 fix is a copper change, not a floorplan change) -- the band the lanes
# used to occupy is simply pour area now.
ATX24_BUS_NETS = ["+12V", "+5V", "+3V3", "+5VSB"]
ATX24_P2P_NETS = ["-12V", "PWR_OK", "PS_ON#"]                  # field pin <-> header pin direct
ATX24_FLOOD_LAYER = {"+5V": "F.Cu", "+12V": "In2.Cu", "+3V3": "B.Cu"}  # GND: In1.Cu; +5VSB: tracks
# Retained placement geometry (iteration 4/5): the old lane corridor's band
# height still positions the tab row (pcb_placement reads ATX24_CORRIDOR_H).
_LANE_PITCH, _LANE_HALF = 0.65, 0.15
ATX24_CORRIDOR_H = 4 * _LANE_PITCH - _LANE_PITCH + 2 * _LANE_HALF  # == 2.25, byte-frozen

# kicad-cli's netlist export prefixes a ROOT-SHEET plain text label (no power-
# port symbol behind it) with "/" (the root sheet's own path) -- the power-
# port-backed rails (+12V/+5V/+3V3/+5VSB/GND) are GLOBAL nets and keep their
# bare name, but -12V/PS_ON#/PWR_OK ride plain `label`s (no "-12V"/"PS_ON#"
# power symbol exists in this platform's library) and so come back
# "/-12V"/"/PS_ON#"/"/PWR_OK" on the actual board. Map at the routing layer
# only -- the schematic/config data above stays on the readable bare names.
_PCB_NET = {n: (f"/{n}" if n in ("-12V", "PS_ON#", "PWR_OK") else n)
            for n in ATX24_BUS_NETS + ATX24_P2P_NETS}

# +5VSB chain widths (mm). The A/B run is capped by the inter-row gap band:
# field pads are 2.7 x 3.7 ovals, so the free band between row0/row1
# anti-pads is (5.5 - 3.7 - 0.6) = 1.2mm -- w=1.0 leaves 0.1 each side.
# 6A on 1.0mm 2oz reads ~26C on the (documented-pessimistic, adiabatic
# long-trace) IPC screen; the 2.5D coupled solve is the gate of record.
_VSB_W_BAND, _VSB_W_DESC, _VSB_W_MID, _VSB_W_TAB = 1.0, 2.0, 1.4, 1.6
_FIELD_PAD_HALF_W, _FIELD_PAD_HALF_H = 1.35, 1.85   # 2.7 x 3.7 oval, field fp
_TAB_PAD_R = 1.25                                    # tab pads O2.5
_CLR = 0.3                                           # zone/track clearance used here


def route_atx24():
    fam = "atx24-out-db"
    cfg = FAMILIES[fam]
    out = f"{_board_dir(fam)}/{cfg['base']}.kicad_pcb"
    r = cr.Router(out)
    rect = _board_rect(fam)

    W, H, P = pcb_placement(fam)
    fx, fy, _field_right, field_bottom = _field_geom(fam)

    # --- the per-rail floods (F1 fix) ---
    # GND, +12V, +3V3(B.Cu): full-board. +5V: full-board CLIPPED at pin 23's
    # clearance boundary -- F.Cu east of the last +5V element is dead area
    # for +5V, and that strip is exactly what +3V3 needs (below).
    x5e = fx + 10 * 4.2 + _FIELD_PAD_HALF_W + _CLR     # 47.75: pin 23 east edge + clr
    (rx0, ry0), (rx1, _), (_, ry1), _ = rect
    # ZONE_CONNECTION_FULL on every power flood -- the platform's own
    # power-pour convention (cec_fr.add_power_pours). Measured reason, this
    # board: with THERMAL relief the whole rail necks through 0.5mm spokes
    # at its 2-3 terminal pads (DC-IR J99.5 ~302 A/mm2 on +5V) and the
    # spoke generator itself proved flaky on the O2.5 tab pads (one pad
    # intermittently unconnected per fill run). Solid connection removes
    # both. Hand-solder cost accepted: this THT board is hand-assembled by
    # design (consigned Mini-Fit class parts platform-wide).
    import pcbnew as _pcbnew
    zs = []
    zs.append(r.zone("GND", rect, layers=("In1.Cu",), clearance=0.3, min_width=0.3))
    zs.append(r.zone("+12V", rect, layers=("In2.Cu",), clearance=0.3, min_width=0.3))
    zs.append(r.zone("+3V3", rect, layers=("B.Cu",), clearance=0.3, min_width=0.3))
    zs.append(r.zone("+5V", [(rx0, ry0), (x5e, ry0), (x5e, ry1), (rx0, ry1)],
              layers=("F.Cu",), clearance=0.3, min_width=0.3))
    # +3V3 F.Cu EAST LIMB + via pair -- pin 12's path. TOPOLOGICAL FACT
    # (measured: 3 fill islands, pin 12 stranded): the +5VSB B.Cu chain plus
    # its endpoint anti-pads forms a top-edge-to-bottom-edge wall, so ANY
    # single-layer pin9->J15 route splits B.Cu into an east and a west
    # component -- and +3V3 has elements on BOTH sides (pin 12 east, tabs
    # west). Escape: pin 12 rides an F.Cu limb in the strip +5V vacated,
    # dropping into the B.Cu main pour through a 2-via cluster placed in
    # the window between the PS_ON# and PWR_OK header drops, inside the
    # clean B.Cu band (row1 anti-pad bottom .. tab anti-pad top) WEST of
    # the +5VSB descent.
    limb_x0 = x5e + 0.5                                 # 0.5 zone-poly gap
    zs.append(r.zone("+3V3", [(limb_x0, ry0), (rx1, ry0), (rx1, ry1), (limb_x0, ry1)],
              layers=("F.Cu",), clearance=0.3, min_width=0.3))
    for _z in zs:
        if _z is not None:
            _z.SetPadConnection(_pcbnew.ZONE_CONNECTION_FULL)
    row0_y, row1_y = fy, fy + 5.5
    tab_y = P[cfg["tabs"][0][0]][1]

    # --- +5VSB: pin 9 -> J15 as a B.Cu track chain (see module comment) ---
    p9x = fx + 8 * 4.2                            # pin 9, col 8, row 0
    gap_mid = (row0_y + row1_y) / 2.0             # inter-row gap band centre
    col11_x = fx + 11 * 4.2
    desc_x = col11_x + 3.0                        # pad-free column east of the field
    j15x, j15y, _ = P["J15"]
    assert abs(j15y - tab_y) < 1e-9
    mid_y = tab_y                                  # tab mid-band centreline
    # clearance audit (asserted, not hoped -- real pad sizes):
    band_lo = row0_y + _FIELD_PAD_HALF_H + _CLR   # gap band upper copper bound
    band_hi = row1_y - _FIELD_PAD_HALF_H - _CLR   # gap band lower copper bound
    assert gap_mid - _VSB_W_BAND / 2 >= band_lo - 1e-9 and \
           gap_mid + _VSB_W_BAND / 2 <= band_hi + 1e-9, "gap band overflow"
    assert desc_x - _VSB_W_DESC / 2 - _CLR >= col11_x + _FIELD_PAD_HALF_W, \
        "descent too close to col-11 pads"
    # tab mid-band: between upper-pad bottom and lower-pad top edges
    mb_lo = (tab_y - 2.54) + _TAB_PAD_R + _CLR
    mb_hi = (tab_y + 2.54) - _TAB_PAD_R - _CLR
    assert mid_y - _VSB_W_MID / 2 >= mb_lo and mid_y + _VSB_W_MID / 2 <= mb_hi, \
        "tab mid-band overflow"
    # +3V3's east-pin passage: the B.Cu band below row1 must stay uncut west
    # of the descent (pin 12's 6A crosses it to reach J13/J14) -- nothing in
    # the chain may enter y in [row1 antipad bottom, tab antipad top] at
    # x < desc_x - w/2 - clr:
    band3_lo = row1_y + _FIELD_PAD_HALF_H + _CLR       # 10.40
    band3_hi = (tab_y - 2.54) - _TAB_PAD_R - _CLR      # 12.95
    assert band3_hi - band3_lo >= 2.5, "the +3V3 east passage band shrank"
    assert gap_mid + _VSB_W_BAND / 2 + _CLR <= band3_lo  # A/B stay above it
    assert mid_y - _VSB_W_MID / 2 - _CLR >= band3_hi     # D' stays below it
    vsb = _PCB_NET.get("+5VSB", "+5VSB")
    # A+B as a PRIORITY-1 ZONE riding the whole inter-row gap band (plus the
    # sliver up to pin 9's pad): the 1.0mm track version screened 26C on the
    # IPC leg (the 1.2mm free band caps any single track) -- the zone fills
    # the full 2.4mm band height and weaves the pad-gap columns, ~2.4x the
    # cross-section (screen ~6C). KiCad fills by priority: the +3V3 B.Cu
    # flood (priority 0) is kept clear of this island automatically -- the
    # standard zone-in-plane pattern, no outline surgery. +3V3 loses only
    # band/web area at x in [36..54], where it has nothing to route (pin
    # 12 rides the F.Cu limb; the west main flow is west of x=36).
    zvsb = r.zone(vsb, [(p9x - 1.5, _TOP_MARGIN + 0.5), (desc_x + 1.0, _TOP_MARGIN + 0.5),
                        (desc_x + 1.0, band_hi + 0.4), (p9x - 1.5, band_hi + 0.4)],
                  layers=("B.Cu",), clearance=0.3, min_width=0.3, priority=1)
    zvsb.SetPadConnection(_pcbnew.ZONE_CONNECTION_FULL)
    r.track(vsb, [(desc_x, gap_mid), (desc_x, mid_y)], "B.Cu", _VSB_W_DESC)  # C
    r.track(vsb, [(desc_x, mid_y), (j15x, mid_y)], "B.Cu", _VSB_W_MID)       # D'
    r.track(vsb, [(j15x, tab_y - 2.54), (j15x, tab_y + 2.54)], "B.Cu", _VSB_W_TAB)  # E'

    # --- tab leg-pair bridges (iteration-5 pattern, resurrected) ---
    # The floods DO reach every tab pad, but the Ø2.5 circle pads' thermal
    # spokes proved flaky at regen (KiCad's 45-degree spokes + 0.5 gap: the
    # connectivity engine intermittently reported ONE tab upper pad
    # unconnected -- J10 on one fill run, J12 on the next, with identical
    # geometry). A hard leg-pair bridge on each non-GND tab removes the
    # spoke dependency outright: each bridge is a same-net track inside (or
    # slotting) the B.Cu flood, WEST of the +5VSB mid-band run (J10..J14 x
    # <= 21.95 < 26.15 = D' start), so nothing crosses. GND tabs (J16-J19)
    # stay spoke-connected on the In1 plane -- 8 pads/4 tabs of the same
    # net, never flagged across any fill run (the platform's GND-tab
    # precedent from iteration 4).
    for ref, net in cfg["tabs"]:
        if net in ("GND", "+5VSB"):
            continue                       # GND: In1 plane; J15: E' already spans it
        tx, ty, _rot = P[ref]
        assert tx < j15x, "bridge would cross the +5VSB mid-band run"
        r.track(_PCB_NET.get(net, net), [(tx, ty - 2.54), (tx, ty + 2.54)], "B.Cu", 1.6)

    # +3V3 limb -> B.Cu main-pour via pair (see the limb comment above).
    # Window between the header drops: PS_ON# drop at pad_x2, PWR_OK at
    # pad_x3 (both 0.2mm wide); via dia 1.2 needs centre in
    # [pad_x2 + 0.1 + 0.3 + 0.6, pad_x3 - 0.1 - 0.3 - 0.6].
    href = cfg["header"]["ref"]
    hhx0 = P[href][0]
    px2, px3 = hhx0 + 2.54, hhx0 + 2 * 2.54
    vx_lo, vx_hi = px2 + 0.1 + 0.3 + 0.6, px3 - 0.1 - 0.3 - 0.6
    vx = (vx_lo + vx_hi) / 2.0
    assert vx_hi - vx_lo >= 0.0, "via window between header drops closed"
    assert vx > fx + 10 * 4.2 + _FIELD_PAD_HALF_W, "via must sit east of pin 23"
    row1_apad_bot = (fy + 5.5) + _FIELD_PAD_HALF_H + _CLR      # 10.40
    tab_apad_top = (tab_y - 2.54) - _TAB_PAD_R - _CLR          # 12.95
    for vy in (row1_apad_bot + 0.6, tab_apad_top - 0.75):      # annuli inside the band
        assert row1_apad_bot <= vy - 0.6 and vy + 0.6 <= tab_apad_top
        r.via("+3V3", (vx, vy), drill=0.6, dia=1.2, layers=("F.Cu", "B.Cu"))


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

    # ITERATION-7 descent phase (4.2mm pitch), REVISED at iteration 11 (the
    # F1 pour fix): with the +5V rail now living on a full F.Cu FLOOD, the
    # three signal levels' horizontal slots must NOT sever the +5V tabs'
    # (J11/J12, x 9.35/13.55) inter-pad columns from the flood -- a level
    # slot across those columns strands the tabs' LOWER pads on an F.Cu
    # island (measured at regen: starved_thermal + unconnected_items).
    # So ALL descents now jog EAST to mid-gap columns EAST of J12's
    # anti-pad (>= 15.10 + slack): -12V jogs from its own column (x1 8.30)
    # east to the mid-gap at _midgap(x3) (15.65), PS_ON# to that + one
    # pitch (19.85), PWR_OK keeps its dodge-derived 36.65. Level slots then
    # start at x >= 15.65 and only cross tab columns whose rails live on
    # OTHER layers (+3V3 B.Cu, +5VSB B.Cu, GND In1) -- asserted below.
    # Jogs at jog_y (the band between row1 pads and the old corridor):
    # -12V [8.30..15.65], PS_ON# [16.70..19.85], PWR_OK [35.60..36.65] --
    # pairwise disjoint (min gap 1.05 >= 0.5 needed). Mid-gap columns keep
    # the lattice guarantee (2.1 from every field pad centre; >= 0.15 edge
    # clearance to the nearest tab anti-pads, checked when derived).
    tab0_x = P[cfg["tabs"][0][0]][0]
    pitch = TAB_PITCH[fam]

    def _midgap(x):
        return tab0_x + pitch / 2 + pitch * round((x - tab0_x - pitch / 2) / pitch)

    m1 = _midgap(x3)              # 15.65 -- east of J12's anti-pad (15.10)
    m3 = m1 + pitch               # 19.85
    m7 = _midgap(x7 + 2.1)        # 36.65 (unchanged)
    assert m1 < m3 < m7, f"descent nesting broke: {m1}, {m3}, {m7}"
    j12x = P["J12"][0]
    assert m1 - 0.4 >= j12x + 1.55, "-12V level start severs J12's F.Cu column"
    P2P_TRACK_W = 0.2
    header_paths = {
        "-12V": [(x1, y1), (x1, jog_y), (m1, jog_y),
                 (m1, lvl["-12V"]), (pad_x[1], lvl["-12V"]),
                 (pad_x[1], hhy)],
        "PS_ON#": [(x3, y3), (x3, jog_y), (m3, jog_y),
                   (m3, lvl["PS_ON#"]), (pad_x[2], lvl["PS_ON#"]),
                   (pad_x[2], hhy)],
        "PWR_OK": [(x7, y7), (x7, y7 + 2.2), (x7 + 2.1, y7 + 2.2),
                   (x7 + 2.1, jog_y), (m7, jog_y), (m7, lvl["PWR_OK"]),
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
        header = ("24-pin ATX daughterboard -- 10 blade-tab joints "
                  "(12V x1 / 5V x2 / 3.3V x2 / 5VSB x1 / GND x4; iteration-"
                  "7 count at the TE 63969-1 receptacle's 22.9A rating "
                  "under the ratified 125% policy) + a 1x4 blind-mate "
                  "signal stub (-12V/PS_ON#/PWR_OK/GND), standing "
                  "perpendicular to the main board, tabs blade-down per "
                  "the owner's 2026-07-05 sketch, dropping into TE 63969-1 "
                  "FASTON PCB receptacles (hole pair perpendicular to the "
                  "row, memo addendum 7). COPPER (iteration-11 F1 fix, "
                  "2026-07-06 -- blade-interconnect-thermal memo F1): the "
                  "old 0.3mm In2 lane corridor is RETIRED; each big rail "
                  "floods one whole layer (F.Cu=+5V, In1=GND, In2=+12V, "
                  "B.Cu=+3V3 -- all terminals are THT, zero vias) and "
                  "+5VSB (6A) runs a 1.0-2.0mm B.Cu track chain east "
                  "around the field into J15 through the tab mid-band; "
                  "the 3 signals stay 0.2mm F.Cu point-to-point tracks. "
                  "The Power netclass documents the hand-touch-up floor, "
                  "not the floods (drawn directly by route_atx24()).")
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
