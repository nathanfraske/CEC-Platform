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
# Per family: TE 63849-1 FASTON tabs (input side, mate the MAIN board's
# Keystone universal blade clips -- NOT built here, see CLAUDE.md "Outstanding
# board actions" item 6, a separate task) fan out in copper to a bare THT
# solder field (output side, spec §2.8's "one field, two/three uses": bare
# pigtail, or a MODDIY-class vertical header where the field is dimensionally
# compatible -- see gen-daughterboard-libassets.py's field footprints). NO
# active or passive components (ratified: "no components beyond the connector
# body and its fan-out copper"). Read CEC-Platform-Ground-Truth-Spec.md §2.8
# v1.4.0 + OQ-87/88/89 and docs/standard-tier-review/output-daughterboard-
# study-2026-07-04.md before changing any net map or joint count below.
#
#   python3 scripts/gen-output-daughterboard.py <family> [--force]
#   family: atx24-out-db | eps-out-db | pcie-out-db | all
import os, re, sys

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

TE_TAB = ("cec-vendor", "TE_63849-1_FASTON_Tab", "TE 63849-1")
TE_TAB_FP = "cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT"

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
ATX24_HEADER_NET = {1: "PWR_OK", 2: "PS_ON#", 3: "-12V", 4: "GND",
                    5: None, 6: None, 7: None, 8: None, 9: None, 10: None}

FAMILIES["atx24-out-db"] = dict(
    dirn="output-daughterboards/atx24-out-db", base="atx24-out-db-board",
    field_ref="J1", field_symbol=("cec", "CEC_ATX_24"),
    field_fp="cec-Connector_Generic:ATX24_Daughterboard_Field_P4.20mm",
    field_net=ATX24_FIELD_NET, field_value="ATX24 OUT FIELD",
    tabs=ATX24_TABS,
    header=dict(ref="J20", symbol=("cec", "CEC_CONN_2x5"),
                fp="cec-Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical",
                net=ATX24_HEADER_NET, value="SIGNAL STUB (2x5)"),
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
    stats = cs.build_schematic(
        sch_path, cfg["base"], parts, nets, used, LIBS, paper="A4",
        power_ports=POWER_PORTS, powerflag_nets=powerflag_nets,
        placement=placement, footprints=fps)
    print(f"{cfg['dirn']}/{cfg['base']}.kicad_sch  " +
          "  ".join(f"{k}={v}" for k, v in stats.items() if k != "root"), file=out)
    return sch_path


# ============================================================================
# PCB: physical placement (field + tabs [+ 24-pin signal header] + M3 mounts).
# ============================================================================
TAB_PITCH_GAP = {  # (within-group pitch mm, extra gap between rail groups mm)
    # distinct per family -- part of the §2.8 v1.4.0 KEYING pattern (asymmetric
    # tab spacing so a wrong-family daughterboard cannot seat on another
    # family's main-board clip pattern; joint COUNT differs too: 9/6/4).
    "atx24-out-db": (9.0, 15.0),
    "eps-out-db": (9.0, 13.0),
    "pcie-out-db": (9.0, 10.0),
}


def pcb_placement(fam):
    cfg = FAMILIES[fam]
    pitch, gap = TAB_PITCH_GAP[fam]
    P = {}
    # field connector: local pin1 at the footprint origin -> global (fx, fy)
    fx, fy = 45.0, 15.0
    P[cfg["field_ref"]] = (fx, fy, 0)
    # tabs: one row, grouped by net with a wider gap between groups (keying).
    # atx24 reserves the left margin for the signal header (below), so its
    # tab row starts further right than the other two families'.
    tab_x0 = 45.0 if fam == "atx24-out-db" else 12.0
    x = tab_x0
    prev_net = None
    tab_row_y = {"atx24-out-db": 62.0, "eps-out-db": 52.0, "pcie-out-db": 48.0}[fam]
    for i, (ref, net) in enumerate(cfg["tabs"]):
        if prev_net is not None and net != prev_net:
            x += gap
        if fam == "atx24-out-db" and i == 1:
            # after the first tab (+12V), jump clear of the field connector's
            # own X-span (its 24 columns + the +-2.1mm dodge offsets occupy
            # roughly fx .. fx+48.3mm) so no tab's stub column can land near
            # a field-pin descent column -- verified against the full
            # occupied-column list in the generator's own dev notes.
            x = max(x, fx + 58.0)
        P[ref] = (x, tab_row_y, 0)
        x += pitch
        prev_net = net
    tabs_right = x - pitch
    if cfg["header"]:
        # Placed BELOW the In2 rail bands (like the tabs), not beside/within
        # them -- its own stubs then only ever run "up" toward a band, same
        # topology as a tab's stub, clear of the corner M3 mounts.
        P[cfg["header"]["ref"]] = (20.0, 58.0, 0)
    W = max(fx + 52.45, tabs_right + 15.0) + 12.0
    H = tab_row_y + 15.0
    inset = 9.0
    mounts = [(inset, inset), (W - inset, inset), (inset, H - inset), (W - inset, H - inset)]
    return W, H, P, mounts, tab_row_y


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
    if not os.path.exists(netf):
        cp.export_netlist(f"output-daughterboards/{fam}", cfg["base"])
    comps, vals, nets = cp.parse_netlist(netf)
    names = [x for x in sorted(nets) if x]
    code_of = {x: i + 1 for i, x in enumerate(names)}
    padnet = {(r, p): (code_of[x], x) for x, nodes in nets.items() if x for (r, p) in nodes}
    W, H, P, mounts, _tab_y = pcb_placement(fam)
    fps = []
    for ref, (x, y, rot) in P.items():
        lib = comps.get(ref)
        if not lib:
            print(f"  WARN no footprint for {ref}", file=sys.stderr); continue
        fps.append(cp.place(lib, ref, x, y, rot, padnet, code_of, val=vals.get(ref)))
    for i, (x, y) in enumerate(mounts, 1):
        fps.append(cp.place("cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via", f"H{i}", x, y, 0,
                            padnet, code_of, gnd_all=True))
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
    _W, _H, _P, _m, _ty = pcb_placement(fam)
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


# ---- 24-pin ATX: 8 nets share the board (GND + 7 rails), so the simple
# full-board-flood trick (2-net-only) doesn't apply -- GND floods In1.Cu
# ALONE (leaving In2.Cu free), and each of the 7 remaining rails gets its own
# horizontal BAND (a zone confined to its own Y-slice of In2.Cu, stacked
# non-overlapping) fed by individual F.Cu stub tracks + a via per pin.
#
# The real ATX-24 pinout INTERLEAVES rails column-by-column (row1 y=0 /
# row2 y=5.5 share the same 12 X-positions), so a field pin's straight-down
# stub can run directly into the OPPOSITE row's pad if that pad is a
# DIFFERENT net -- verified against every column (12 of them; see the
# generator's own dev notes / the board's README "keying/fan-out" section):
# only ROW1 pins ever need to dodge (row2 has nothing below it at its own
# column except the clear inter-row gap), and only when its own net differs
# from the row2 pin sharing that column. The dodge is a single +2.1mm (half
# the 4.20mm pitch) sideways jog -- landing dead-centre in the gap between
# two adjacent pad columns, symmetric ~0.75mm clear of both neighbours' pad
# edges -- taken PERMANENTLY (not jogged back), which keeps every column's
# own stub on its own unique X for its whole length and so never collides
# with a NEIGHBOURING column's stub either.
ATX24_NONGND_NETS = ["+12V", "+5V", "+3V3", "+5VSB", "-12V", "PWR_OK", "PS_ON#"]
# kicad-cli's netlist export prefixes a ROOT-SHEET plain text label (no power-
# port symbol behind it) with "/" (the root sheet's own path) -- the power-
# port-backed rails (+12V/+5V/+3V3/+5VSB/GND) are GLOBAL nets and keep their
# bare name, but -12V/PS_ON#/PWR_OK ride plain `label`s (no "-12V"/"PS_ON#"
# power symbol exists in this platform's library) and so come back
# "/-12V"/"/PS_ON#"/"/PWR_OK" on the actual board. Map at the routing layer
# only -- the schematic/config data above stays on the readable bare names.
_PCB_NET = {n: (f"/{n}" if n in ("-12V", "PS_ON#", "PWR_OK") else n) for n in ATX24_NONGND_NETS}


def route_atx24():
    fam = "atx24-out-db"
    cfg = FAMILIES[fam]
    out = f"{_board_dir(fam)}/{cfg['base']}.kicad_pcb"
    r = cr.Router(out)
    rect = _board_rect(fam)
    r.zone("GND", rect, layers=("In1.Cu",), clearance=0.3, min_width=0.3)

    W, H, P, mounts, tab_row_y = pcb_placement(fam)
    fx, fy, _ = P[cfg["field_ref"]]

    band_top, band_pitch, band_half = 30.0, 4.0, 1.4
    band_y = {net: band_top + i * band_pitch for i, net in enumerate(ATX24_NONGND_NETS)}
    hx0 = P[cfg["header"]["ref"]][0]
    band_x0, band_x1 = min(fx - 4.0, hx0 - 4.0), W - 6.0
    for net, by in band_y.items():
        pn = _PCB_NET.get(net, net)
        r.zone(pn, [(band_x0, by - band_half), (band_x1, by - band_half),
                   (band_x1, by + band_half), (band_x0, by + band_half)],
               layers=("In2.Cu",), clearance=0.2, min_width=0.25)

    # field pins (1-24): row1 = pins 1-12 @ local y=0, row2 = pins 13-24 @ y=5.5
    for pin, net in cfg["field_net"].items():
        if net in (None, "GND"):
            continue
        pn = _PCB_NET.get(net, net)
        row = 0 if pin <= 12 else 1
        col = (pin - 1) % 12
        x, y = fx + col * 4.2, fy + (0.0 if row == 0 else 5.5)
        opp_net = cfg["field_net"][pin + 12 if row == 0 else pin - 12]
        conflict = (row == 0) and (opp_net != net)
        by = band_y[net]
        if conflict:
            pts = [(x, y), (x, y + 2.2), (x + 2.1, y + 2.2), (x + 2.1, by)]
        else:
            pts = [(x, y), (x, by)]
        r.track(pn, pts, "F.Cu", 0.5)
        r.via(pn, pts[-1], drill=0.5, dia=0.9, layers=("F.Cu", "B.Cu"))

    # tabs: straight stub up to their own net's band (nothing else occupies
    # F.Cu between the tab row and the bands -- the bands live on In2.Cu).
    # The TE_63849-1 footprint has TWO physical pads, both numbered "1" (one
    # electrical node per its own vendored description), but "same pad
    # number" is a netlist LABEL, not copper -- the footprint has no internal
    # bridge between them, so both need real copper: a short bridge track
    # between the two pads (tx-2.54 to tx+2.54), then the up-stub off the
    # +2.54 one (the placement origin between them has no copper at all).
    for ref, net in cfg["tabs"]:
        if net == "GND":
            continue
        pn = _PCB_NET.get(net, net)
        tx, ty, _ = P[ref]
        by = band_y[net]
        r.track(pn, [(tx - 2.54, ty), (tx + 2.54, ty)], "F.Cu", 0.5)
        r.track(pn, [(tx + 2.54, ty), (tx + 2.54, by)], "F.Cu", 0.5)
        r.via(pn, (tx + 2.54, by), drill=0.5, dia=0.9, layers=("F.Cu", "B.Cu"))

    # 2x5 signal header (PWR_OK/PS_ON#/-12V/GND-ref/6 reserved), placed BELOW
    # the bands: pin1 PWR_OK (row0,col0), pin2 PS_ON# (row0,col1), pin3 -12V
    # (row1,col0 -- SAME column as pin1), pin4 GND (row1,col1, no route). Only
    # pin3 needs a dodge (it shares pin1's column and must pass its Y on the
    # way up to a band); pin1/pin2 have clear runs since nothing else sits
    # above the header at their own X. Explicit per-net paths (only 3 nets,
    # tightly packed at 2.54mm pitch -- the generic per-pin loop used for the
    # much coarser 4.20mm field/tab pitch is too tight here).
    h = cfg["header"]; hx, hy, _ = P[h["ref"]]
    header_paths = {
        "PWR_OK": [(hx, hy), (hx, band_y["PWR_OK"])],
        "PS_ON#": [(hx + 2.54, hy), (hx + 2.54, band_y["PS_ON#"])],
        "-12V": [(hx, hy + 2.54), (hx, hy + 1.3), (hx + 1.27, hy + 1.3), (hx + 1.27, band_y["-12V"])],
    }
    for net, pts in header_paths.items():
        pn = _PCB_NET.get(net, net)
        r.track(pn, pts, "F.Cu", 0.4)
        r.via(pn, pts[-1], drill=0.5, dia=0.9, layers=("F.Cu", "B.Cu"))

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
