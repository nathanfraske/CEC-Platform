#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_constraints -- the CEC platform DESIGN-CONSTRAINT REGISTRY + checkers
#                     + the directive consumer (violation -> placement directive).
# ============================================================================
# The single source of truth for "project structure" rules a constraint-aware
# placer/router must keep -- what the connectivity placer was blind to.
#
#   * REGISTRY  -- curated, ratifiable canonical constraints (id, severity,
#                  checkability, the placement DIRECTIVE to emit on violation,
#                  source, status[ratified|proposed], params). Curated from the
#                  269-row extraction in scripts/constraints/corpus-extracted.json.
#   * CHECKERS  -- deterministic checks (pcbnew geometry / net topology / DRC),
#                  self-gating (return None = N/A when the relevant parts are
#                  absent). The "discover -> ratify -> enforce" migration:
#                  what an LLM/human spots becomes a deterministic checker here.
#   * directives(rows) -- turns FAILs into TYPED placement directives an
#                  auto-placer consumes (pin/adjacent/region/keepout/separate/align).
#
#   python3 scripts/cec_constraints.py <board.kicad_pcb> [...] [--radio] [--json]
# ============================================================================
import os, re, sys, json, math, collections, subprocess, tempfile
from dataclasses import dataclass, field, asdict

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_dispatch   # noqa: E402  -- _locus_is_finishing, _bracket_nets (drc_types moved to cec_score, R-02)
import cec_score      # noqa: E402  -- _derive_pairs (Kelvin _HI/_LO, diff _P/_N)


# ===========================================================================
#  Registry
# ===========================================================================
@dataclass
class Constraint:
    id: str
    title: str
    category: str
    severity: str               # hard | strong | soft | advisory
    checkable: str              # yes | partial | no
    directive: str              # pin | adjacent | region | keepout | separate | align | none
    rule: str
    source: str
    status: str = "proposed"    # ratified | proposed
    params: dict = field(default_factory=dict)
    checker: str = ""           # registered checker id (defaults to .id)
    # CL-03 Ruling 2: registry <-> corpus reconciliation fields. corpus_id links
    # a row to its corpus-entry source (set in the entry's PROMOTION PR -- the
    # "linked" parity tier). superseded_by TOMBSTONES the row: authority moved
    # to the named promoted entry; the row is EXCLUDED from blocking, in the
    # same human-merged diff as the promotion (retirement is never automatic).
    corpus_id: str = ""
    superseded_by: str = ""


def C(**kw):
    return Constraint(**kw)


REGISTRY = [
    # ---- high-current / shunt / Kelvin -------------------------------------------------
    C(id="kelvin-sense-fcu-no-via", title="Kelvin sense pair stays on F.Cu, no vias",
      category="high-current", severity="hard", checkable="yes", directive="none",
      rule="The Kelvin sense pair (*_HI/*_LO) stays short and local on the TOP layer (F.Cu) with ZERO "
           "vias -- never routed to a signal layer and back (that folds via inductance into the sense).",
      source="spec §6.8 (LOCKED, verbatim)", status="ratified"),
    C(id="kelvin-sense-adjacent-shunt", title="Sense IC within 5mm of its shunt",
      category="high-current", severity="hard", checkable="yes", directive="adjacent",
      rule="The current-sense IC (INA228/238/181) sits within max_mm of its shunt (short Kelvin loop). "
           "Threshold calibrated to the as-built boards (ratified 5mm).",
      source="spec §6.8 + as-built calibration", status="ratified", params={"max_mm": 5.0}),
    C(id="shunt-inline-in-corridor", title="Shunt sits inline in the J_IN->J_OUT current path",
      category="high-current", severity="strong", checkable="yes", directive="region",
      rule="Each cable/pin shunt lies between its input and output connector pads, so current flows "
           "through it with no bypass.", source="spec §6.7; user-named", status="ratified",
      params={"tol_mm": 2.0}),
    C(id="high-current-corridor-keepout", title="High-current corridor clear of foreign signals",
      category="high-current", severity="strong", checkable="yes", directive="keepout",
      rule="The J_IN->shunt->J_OUT corridor carries no foreign-net via/track (reserved for the pour).",
      source="CLAUDE.md considerations", status="ratified"),
    C(id="high-current-pour-present", title="High-current nets carried by a filled pour",
      category="high-current", severity="strong", checkable="yes", directive="keepout",
      rule="High-current nets (12V/*_HI) carried by a filled pour of adequate area (route-time step).",
      source="CLAUDE.md route-to-clean; user-named", status="ratified", params={"min_area_mm2": 20.0}),
    C(id="shunt-values-per-table", title="Shunt values per the §6.4 table",
      category="high-current", severity="hard", checkable="partial", directive="none",
      rule="EPS/PCIe per-cable 0.5mOhm; 12VHPWR per-pin 1mOhm; 24-pin 2mOhm rails / 25mOhm 5VSB.",
      source="spec §6.4 (LOCKED)", status="ratified"),
    C(id="high-current-stackup-2oz", title="4-layer, 2oz outer, 12V on outers",
      category="high-current", severity="hard", checkable="no", directive="none",
      rule="High-current modules: 4-layer, 2oz outer copper, 12V on outers, GND on inners.",
      source="spec §6.7", status="ratified"),
    C(id="high-current-pour-integrity", title="No same-layer trace cuts the high-current pour",
      category="high-current", severity="hard", checkable="yes", directive="keepout",
      rule="A foreign-net trace on the SAME layer as a 12V/_HI/_LO pour must not pass through it -- the "
           "fill carves a clearance gap around the trace, splitting the pour and necking the current "
           "path. Route foreign signals on another layer or around the pour region.",
      source="user review 2026-06-07; spec §6.7 (current = copper area)", status="ratified"),
    C(id="no-foreign-on-high-current-pour",
      title="High-current pour is an ABSOLUTE keepout (no foreign track/via)",
      category="high-current", severity="hard", checkable="yes", directive="keepout",
      rule="THE authoritative high-current-pour keepout (owner directive 2026-06-27). The pour region -- "
           "cec_fr.derive_power_pours, the SAME rectangles add_power_pours fills and sense-body-clear-of-pour "
           "checks -- is reserved for its OWN net's copper plus the inner-edge Kelvin sense tap. NO foreign-net "
           "TRACK (on the pour's layer) or VIA may cross it, EVER. GND and the power rails ARE foreign here: a "
           "foreign trace on the pour layer forces the zone filler to carve an antipad that necks/fragments the "
           "40A fill -- and KiCad DRC is BLIND to that (no clearance error), so 'drc==0' can never catch it. The "
           "check is GEOMETRIC (sampled against the pour RECTANGLE), never DRC-derived. ONE region the placer, "
           "router AND accept gate all obey -- it SUBSUMES high-current-pour-integrity + high-current-corridor- "
           "keepout into a single region-keyed FAIL gate (wired into cec_router.independent_drc like via-on-pad, "
           "and into intake_gate). SCOPE: genuine per-cable interposer corridors (EPS/PCIe -- the measured "
           "51-foreign-crossing failure mode). Shared-bus per-pin (12VHPWR J3/J4) and per-rail (24-pin J3/J4) "
           "boards pack their lane/rail with the sense chain by design -> N/A (vacuous PASS), same scope as "
           "high-current-corridor-keepout. The placer keeps foreign BODIES out (sense-body-clear-of-pour); the "
           "router keeps foreign TRACKS out (the two-pass corridor protect); this rule is the gate that fails the "
           "board when either lets foreign copper land on the pour.",
      source="owner directive 2026-06-27 (absolute pour keepout); measured eps-rev3 68-track/13-via",
      status="ratified", params={"sample_pts": 11}),
    C(id="min-pour-cross-section", title="High-current pour cross-section adequate (DC field solve)",
      category="high-current", severity="advisory", checkable="yes", directive="keepout",
      rule="Each poured high-current net's BOTTLENECK copper cross-section -- from the cec_dcir 2.5D DC "
           "IR-drop / current-density field solve on the routed copper -- keeps peak current density at or "
           "below j_max_A_mm2 for its design current (eff_cross >= I / j_max). ADVISORY + CALIBRATION: the "
           "solver is not yet bench-validated, so this SURFACES OQ-10 (copper coin / filled-via field) and "
           "OQ-12 (high-current stackup) with real numbers (IR drop, J, bottleneck cross-section) -- it does "
           "NOT resolve those OQs or hard-gate a release. The spec_to_dru/DRC enforce-leg (a ratified "
           "min-width on the carved high-current netclass) is the follow-up, once a bench measurement "
           "calibrates the dt_ipc k / shunt_rth placeholders (docs/local-compute-exploration.md Thrust B).",
      source="docs/local-compute-exploration.md Thrust B; scripts/cec_dcir.py; physics_gates J_max=100",
      status="proposed", params={"j_max_A_mm2": 100.0, "grid_mm": 0.4, "oz_outer": 2.0, "oz_inner": 1.0}),
    C(id="kelvin-sense-from-inner-pad", title="Kelvin sense tapped from the shunt inner edge",
      category="high-current", severity="strong", checkable="yes", directive="inner_tap",
      rule="The Kelvin sense trace leaves the shunt pad from its INNER edge (the sense point facing the "
           "other terminal), not an arbitrary side, and runs as a DIRECT F.Cu stub (no via) to the "
           "current-sense IC input pad on that net (HI-inner -> IN+, LO-inner -> IN-) -- §6.8 four-wire "
           "sense taps the shunt element only. BUILT generatively at route time by "
           "cec_fr.synthesize_kelvin_taps (directive=inner_tap) into the open window "
           "cec_fr.derive_power_pours leaves at the shunt; FULLY checked (checkable=yes) -- the generative "
           "tap guarantees a resolvable thin stub, so the old checked==0 N/A escape no longer fires.",
      source="user review 2026-06-07; spec §6.8; generative tap 2026-06-27", status="ratified",
      params={"inner_min_mm": 0.1, "ina_reach_mm": 0.9}),
    C(id="kelvin-sense-no-connector-tap",
      title="Kelvin sense input connects to the heavy net by the shunt tap ALONE (no parallel tap)",
      category="high-current", severity="strong", checkable="yes", directive="inner_tap",
      rule="The current-sense IC INPUT pad (IN+/IN-) on a SENSEC _HI/_LO net must have EXACTLY ONE copper "
           "connection: a single via-less F.Cu inner-edge stub landing on the 2-pad Kelvin shunt's pad. "
           "Then the sense reaches the heavy net only through the shunt terminal and carries no load "
           "current (four-wire). FAIL when the input pad carries a SECOND incident copper stub, or a via, "
           "or its lone stub does not land on the shunt -- the kelvin-from-connector defect: the router "
           "satisfied the input pad's same-net connectivity by ALSO wiring it to the nearest net point "
           "(the connector / a second pour point), so the sense pad is tied to two points of the "
           "current-carrying copper, the stub spans the connector->shunt IR drop + contact R and carries "
           "current. (A correct tap reaches the connector THROUGH the shunt terminal too -- that is fine; "
           "the defect is the PARALLEL second connection, detected as stub-count > 1.) The Vbus pad "
           "(INA238/228 pad 8) is a high-Z VOLTAGE tap, legitimately FR-routed, and is NOT a Kelvin "
           "input, so it is never flagged. Prevented at route time by cec_fr.export_dsn excluding these "
           "pads from FR (kelvin_sense_pins); this is the independent post-route gate that complements "
           "kelvin-sense-from-inner-pad (which verifies the GOOD tap exists but is blind to a parallel "
           "bad connection).",
      source="owner directive 2026-06-28 (kelvin-from-connector bug)", status="ratified",
      params={"pad_reach_extra_mm": 0.15, "stub_far_cluster_mm": 0.5}),
    C(id="sense-body-clear-of-pour", title="Sense IC body clear of the high-current pour",
      category="high-current", severity="strong", checkable="yes", directive="none",
      rule="The current-sense IC (INA228/238/181) is seated HARD against its shunt's inner edge for the "
           "Kelvin tap, but its BODY (courtyard) must stay OUT of the SENSEC high-current pour region "
           "(cec_fr.derive_power_pours) so it does not block the fill or neck the current path. The IC "
           "body sits perpendicular to the J_IN->shunt->J_OUT corridor, in the un-poured NOTCH between "
           "the HI and LO pour boxes: courtyard CENTROID outside every pour box, and courtyard overlap "
           "with the pour <= max_overlap_mm2. The tolerance is a board-calibrated graze allowance (a "
           "SOT-23-6 INA181 body is 4.19mm vs the ~3.925mm notch the ratified 1.0mm pour margin opens, "
           "so it overshoots ~0.13mm/side = ~0.9mm^2 -- accepted as a footprint-edge graze, NOT a "
           "body-in-pour; a buried body overlaps several mm^2). The owner-ratification item to fully "
           "clear the INA181 is a smaller per-shunt pour margin (~0.67mm) or a local pour clip -- a "
           "constraint/route-time change, surfaced not silently applied.",
      source="owner directive 2026-06-27; spec §6.8 + as-built notch calibration", status="ratified",
      params={"max_overlap_mm2": 2.0}),

    # ---- thermal -----------------------------------------------------------------------
    C(id="hot-sensitive-separation", title="Hot parts separated from temp-sensitive parts",
      category="thermal", severity="strong", checkable="yes", directive="separate",
      rule="Hot parts (shunts, high-current connectors -- the small LP5907 LDO scoped OUT "
           "2026-07-08: at 8.0 the checker false-fired on the hand 12vhpwr's as-built "
           "U4(REF3030)<->U3(LDO)=6.10mm, and a 150mA SOT-23 LDO is not a shunt-class heat "
           "source; actual thermal risk is carried by the fail-closed thermal gate) kept "
           ">= sep_mm from temp-sensitive parts (ambient NTC, the reference, the ESP).",
      source="spec §6.6; opus fundamentals audit 2026-07-08", status="proposed",
      params={"sep_mm": 8.0}),
    C(id="ntc-board-temp-by-shunt", title="Board-temp NTC adjacent to the shunt row",
      category="thermal", severity="strong", checkable="yes", directive="adjacent",
      rule="The board-temp NTC sits within max_mm of a shunt; the ambient NTC sits away from heat.",
      source="spec §6.6; as-built", status="proposed", params={"max_mm": 5.0}),

    # ---- EMC / RF / SI -----------------------------------------------------------------
    C(id="esp-antenna-keepout", title="ESP PCB-antenna keepout clear (if radio populated)",
      category="EMC/RF", severity="hard", checkable="partial", directive="keepout",
      rule="If the on-board radio is used, the ESP antenna keepout carries no copper/vias/parts. "
           "Wired-only board -> keepout DROPPABLE (area win).",
      source="ESP datasheet; CLAUDE.md respect_antenna_keepout; user-named", status="ratified",
      params={"gated_on": "radio"}),
    C(id="usb-diffpair-routed-coupled", title="USB D+/D- routed, 0 unconnected (hard gate)",
      category="EMC/RF", severity="hard", checkable="yes", directive="adjacent",
      rule="USB_D_P/_N both routed with 0 unconnected ratlines.", source="spec §3; cec_score",
      status="ratified", checker="diffpair-gate"),
    C(id="diffpair-pn-naming", title="Diff pairs use the _P/_N suffix convention",
      category="EMC/RF", severity="strong", checkable="yes", directive="none",
      rule="Differential pairs use the _P/_N suffix (e.g. /USB_D_P, /USB_D_N) so KiCad's diff-pair "
           "router auto-recognizes them -- NOT /USB_DP //USB_DM.",
      source="repo convention; CLAUDE.md (EPS renamed, PCIe pending)", status="ratified"),
    C(id="can-coupled-no-module-term", title="CAN coupled; 120R split termination at Hub only",
      category="EMC/RF", severity="hard", checkable="partial", directive="none",
      rule="CAN_H/CAN_L coupled; split 120R termination only at the Hub, never a module.",
      source="spec §3.1 (LOCKED)", status="ratified"),

    # ---- connectors / mechanical -------------------------------------------------------
    C(id="rj45-link-pinmap", title="RJ-45 link; pins per the locked allocation",
      category="connectors", severity="hard", checkable="yes", directive="none",
      rule="Module<->Hub link is RJ-45 (never Mini-Fit Jr); pin1 VCC, pin2 GND, pin3 CAN_H, pin6 "
           "CAN_L, pin7 reserved (NOT AUX_REF), pin8 DETECT.", source="spec §2.1/§2.2 (LOCKED)",
      status="ratified"),
    C(id="connector-mouth-faces-edge", title="Connector mouth faces the nearest board edge",
      category="connectors", severity="hard", checkable="partial", directive="pin",
      rule="Each cable/power connector opens toward (and overhangs) the nearest board edge.",
      source="user-named (rotation); as-built", status="ratified", params={"edge_mm": 6.0}),
    C(id="connector-overhang-bounded", title="Connector overhang bounded (all pads on-board)",
      category="connectors", severity="strong", checkable="yes", directive="region",
      rule="A connector may overhang an edge, but ALL its pads stay on-board AND the body overhang "
           "does not exceed the part's shroud depth.", source="user-named (overhang amount)",
      status="ratified"),
    C(id="mount-holes-present-clear", title="M3 mounts present, GND-tied, clear of connectors",
      category="connectors", severity="hard", checkable="yes", directive="pin",
      rule="The board carries its M3 mounts (chassis-grounded), clear of connector courtyards.",
      source="user-named; as-built", status="ratified", params={"min_count": 3, "clear_mm": 2.0}),
    C(id="detect-esd-diode-pin8", title="DETECT pin-8 ESD diode present (PESD SOD-323)",
      category="connectors", severity="hard", checkable="yes", directive="adjacent",
      rule="A low-cap ESD diode (PESD5V0S1BA, SOD-323) clamps the DETECT line on every Hub/module.",
      source="spec §2.4 (LOCKED v2.0)", status="ratified"),

    # ---- placement / passives ----------------------------------------------------------
    C(id="decoupling-cap-owner", title="Decoupling cap at its owner IC power pad",
      category="placement", severity="strong", checkable="yes", directive="adjacent",
      rule="Each decoupling cap sits within max_mm of an IC pad on the same power net.",
      source="cec_pcb verify_passives", status="ratified", params={"max_mm": 3.5}),
    C(id="trace-width-high-current", title="No too-thin trace on a high-current net",
      category="placement", severity="strong", checkable="yes", directive="none",
      rule="No track on a 12V/*_HI net is thinner than min_mm unless the net is carried by a pour.",
      source="user-named (trace widths); .kicad_dru", status="ratified", params={"min_mm": 1.0}),
    C(id="ic-power-ground-connected", title="Every IC's power + GND pins are connected",
      category="placement", severity="hard", checkable="yes", directive="power_escape",
      rule="No IC (U*) has an unconnected power(+3V3/+5VSB/VBUS/VCC/VDD) or GND pad -- a stranded supply or "
           "ground pin is an unpowered / floating part (a dead sensor). A TIGHT Kelvin/adjacency placement "
           "that boxes a sense IC against its shunt must still let that IC's shunt-facing power/GND pins "
           "escape (via to a plane / short stub), or the loop's own power-escape pass connects them.",
      source="adversarial verify-workflow 2026-06-07 (lens-3: tight-Kelvin INA238 +3V3/GND stranded)",
      status="ratified"),
    C(id="board-routing-complete", title="0 unconnected ratlines (fully routed)",
      category="placement", severity="strong", checkable="yes", directive="none",
      rule="The routed board has 0 unconnected ratlines. A 'clean' claim MUST verify UNCONNECTED, not just "
           "shorts/clearance/dangling -- a board with open nets is non-functional even at 0 DRC shorts. "
           "(Reported with a per-net tally so finishing residual is distinguishable from a structural gap.)",
      source="adversarial verify-workflow 2026-06-07 (lens-1: 'clean' overclaimed past 32 ratlines)",
      status="ratified"),
    C(id="ina-lane-symmetry-12vhpwr", title="12VHPWR 6 INA lanes equal-pitch",
      category="placement", severity="strong", checkable="partial", directive="align",
      rule="The six INA240 per-pin lanes are equal pitch, each its own column, symmetric.",
      source="CLAUDE.md considerations; as-built", status="ratified", params={"pitch_tol_mm": 0.5}),

    # ---- finishing / decorative --------------------------------------------------------
    C(id="logo-bcu-keepout", title="Decorative LOGO copper must not cross functional nets",
      category="finishing", severity="hard", checkable="yes", directive="keepout",
      rule="The decorative B.Cu LOGO polygon is a routing keepout (or GND-assigned): no functional-net "
           "copper may short to it. (LOGO-vs-GND only is finishing-acceptable.)",
      source="discovered by the route loop 2026-06-07; verified", status="ratified"),
    C(id="via-on-pad", title="No via copper overlapping a pad (via-in-pad / short)",
      category="finishing", severity="hard", checkable="yes", directive="none",
      rule="A via whose copper (drill + annular ring) overlaps a PAD's copper on a shared copper layer "
           "is a fault KiCad DRC does NOT flag by default. SAME-net overlap = via-in-pad: the open barrel "
           "wicks solder, so it needs tenting / plugging / POFV fill and is generally not allowed unhandled "
           "-- the layer-swap / B.Cu-mirror finishing stages drop 1-6 of these (a via punched dead-centre "
           "into a decoupling-cap or sense pad to reach B.Cu). DIFF-net overlap = a hard short. Reported "
           "per overlap with ref/pad/net/coords; route()'s independent verdict folds it into gates_pass so "
           "a via-in-pad board can never pass silently.",
      source="owner review 2026-06-27 (layer-swap/mirror via-in-pad; KiCad DRC blind spot)",
      status="ratified"),
    C(id="footprint-matches-datasheet", title="Footprint land matches the MPN datasheet",
      category="finishing", severity="hard", checkable="partial", directive="none",
      rule="Each footprint's pad pitch/drill/size/row matches the part datasheet land. Unverified MPNs "
           "are flagged, not passed.", source="user-named; CLAUDE.md Molex 45586 fix", status="ratified"),
    C(id="fiducials-present", title="Fiducials present (3x)",
      category="finishing", severity="strong", checkable="yes", directive="none",
      rule="Three fiducials (board-only, excl-BOM).", source="as-built", status="proposed",
      params={"min_count": 3}),

    # ---- assembly/DFM protocols (STANDARD-DESIGN-SHEET §K, 2026-07-17) -----------------
    # The K-protocol mechanization set (sheet §J.6). All ADVISORY + proposed: the sheet's
    # numbers are tagged [wb] and the owner has not ratified the mechanized thresholds;
    # these AUDIT and report, they do not gate. Corpus rows:
    # corpus/staging/general/design-sheet-k-protocols.json.
    C(id="fiducial-protocol", title="Fiducial protocol: 3x, asymmetric, edge margin, clear zone",
      category="assembly-dfm", severity="advisory", checkable="yes", directive="none",
      rule="Given fiducials are placed (presence is fiducials-present's gate), the GLOBAL set per "
           "assembled side is exactly 3, placed ASYMMETRICALLY (the set must not map onto itself "
           "under 180-degree rotation about the board centre -- symmetry leaves a vision "
           "ambiguity), each >= edge_min_mm from every board edge and with no foreign pad inside "
           "clear_mm (copper/silk clear zone). N/A on a board with no fiducials yet.",
      source="STANDARD-DESIGN-SHEET §K.4 [wb] + IPC-7351B/JLC (I.11/I.17); 12VHPWR precedent "
             "measured 2026-07-17: asymmetry PASSES, min edge margin 2.9mm vs the 5.0 target",
      status="proposed", params={"count": 3, "edge_min_mm": 5.0, "clear_mm": 3.0,
                                 "sym_tol_mm": 1.0}),
    C(id="mlcc-edge-orientation", title="MLCC near a board edge lies parallel to it",
      category="assembly-dfm", severity="strong", checkable="yes", directive="none",
      rule="An MLCC (C* on an 0402/0603/0805 land) whose courtyard comes within edge_band_mm of a "
           "board edge must orient its LONG axis PARALLEL to that edge (depanel/handling flex "
           "cracks the terminations of a perpendicular part; the K.1 rule also keeps them >= 1mm "
           "in). N/A when no MLCC sits in the band.",
      source="STANDARD-DESIGN-SHEET §K.1 + MLCC flex-crack vendor guidance (I.15); RATIFIED "
             "2026-07-19 (owner GO after fleet calibration: zero alpha false-positives, all "
             "N/A; caught a real fresh-wave defect C22-perpendicular-at-edge)",
      status="ratified", params={"edge_band_mm": 1.0}),
    C(id="ecap-edge-distance", title="Large SMD electrolytic clear of board edges",
      category="assembly-dfm", severity="strong", checkable="yes", directive="none",
      rule="A large SMD aluminum-electrolytic can (>= min_uf uF, or a CP_Elec-class land) sits "
           ">= edge_min_mm from every board edge (base-weld flex + V-cut rule; the vent/enclosure "
           "and reflow rules are BOM/enclosure-side, sheet §K.8). N/A when the board carries none.",
      source="STANDARD-DESIGN-SHEET §K.8 + SMD e-cap vendor reflow/lifetime guidance (I.16); "
             "hub-standard C1 measured 12.05mm 2026-07-17 (passes); RATIFIED 2026-07-19 "
             "(owner GO after fleet calibration: only e-cap board PASSES, rest N/A)",
      status="ratified", params={"edge_min_mm": 5.0, "min_uf": 470.0}),
    C(id="decoupler-adjacency-k5", title="Decoupling loop length vs the K.5 target (audit)",
      category="assembly-dfm", severity="advisory", checkable="yes", directive="adjacent",
      rule="AUDIT of the K.5 geometry target: every 100nF-class decoupler's power pad sits within "
           "target_mm (pad-to-pad) of its IC power pin. Distinct from decoupling-cap-owner (the "
           "ratified as-built 3.5mm ownership gate): this reports the gap to the sheet's tighter "
           "protocol target so beta layouts can close it; it never blocks.",
      source="STANDARD-DESIGN-SHEET §K.5 [wb] + Ott ch.11 / Bogatin PDN loop-inductance basis "
             "(I.2-class); as-built calibration remains decoupling-cap-owner's 3.5mm",
      status="proposed", params={"target_mm": 1.5}),

    # ---- schematic / BOM conformance ---------------------------------------------------
    C(id="detect-resistor-code", title="DETECT code resistor per §2.3",
      category="conformance", severity="hard", checkable="yes", directive="none",
      rule="DETECT resistor encodes link capability on the 10k/3.3V divider: CAN-only 2.2k, "
           "CAN+RS-485 4.7k.", source="spec §2.3 (LOCKED, OQ-6)", status="ratified",
      params={"expect_k": 2.2}),
    C(id="can-transceiver-tja1051t3", title="CAN transceiver is TJA1051T/3",
      category="conformance", severity="hard", checkable="yes", directive="none",
      rule="Every board carrying the transceiver uses TJA1051T/3 (classical CAN).",
      source="spec §3.1 (LOCKED v3.5)", status="ratified"),

    # ---- CL-25 audit-derived check pack (closed-loop framework, 2026-06-10) -------------
    # The six audit classes as STABLE IDs. Three are NEW below; three map to checks that
    # already existed (see CL25_CLASSES) -- the class names stay stable either way.
    C(id="netclass-geometry-conformance", title="Per-net via/track geometry meets its netclass minima",
      category="conformance", severity="hard", checkable="yes", directive="none",
      rule="Every net resolves to its intended netclass (.kicad_pro patterns/assignments) and every "
           "track/via on it meets the class minima (track width, via diameter, via drill). Freerouting "
           "provably ignores netclass widths (measured), so this is the post-route ENFORCEMENT the "
           "router cannot provide -- the 12VHPWR audit's 136 signal-size lane vias are this class. "
           "On a SHARED force+sense net (an INA sense input lives on it) track width is checker-exempt "
           "(the deliberate ~0.25mm Kelvin stubs; same split as derive_cross_section_dru) -- vias still "
           "checked.", source="closed-loop CL-25; 12VHPWR audit (lane vias); CLAUDE.md FR-ignores-widths",
      status="ratified", params={"tol_mm": 0.001}),
    C(id="bom-field-lint", title="No placeholder/empty BOM fields on assembly-relevant parts",
      category="conformance", severity="strong", checkable="yes", directive="none",
      rule="No BOM-relevant footprint carries a placeholder Value (*_Small, '~', empty, TODO/TBD/FIXME) "
           "or an empty source field where sourcing is expected. Documented-open gaps (OQ-11 shunts, "
           "consigned THT power headers) are NOTED, not failed -- only UNEXPECTED holes fail.",
      source="closed-loop CL-25; Hub audit (BOM lint class); 12VHPWR TH1/TH2 R_Small case",
      status="ratified"),
    C(id="sch-pcb-sync", title="Schematic and PCB reference sets in sync (no stale board)",
      category="conformance", severity="strong", checkable="yes", directive="none",
      rule="The PCB carries a footprint for every schematic symbol (and no orphans): a symbol present "
           "in the .kicad_sch but absent from the .kicad_pcb means Update-PCB-from-Schematic is "
           "pending -- routing a stale board all night produces perfectly routed WRONG boards. "
           "Board-only refs (LOGO/FID/H/MK/TP) and power symbols excluded. Freshness (sch newer than "
           "pcb) is reported in the detail.", source="closed-loop CL-25; Hub audit (desync class)",
      status="ratified"),
]

# CL-25: the six audit-derived check classes -> stable registry IDs. The fixtures (CL-11),
# swarm verifies (CL-24) and triage (CL-22/24) key off these class names.
CL25_CLASSES = {
    "netclass-geometry":   ["netclass-geometry-conformance"],
    "thermal-keep-apart":  ["hot-sensitive-separation", "ntc-board-temp-by-shunt"],
    "cap-to-node":         ["decoupling-cap-owner"],
    "bom-lint":            ["bom-field-lint"],
    "sch-pcb-sync":        ["sch-pcb-sync"],
    "netlist-assertions":  ["rj45-link-pinmap", "detect-resistor-code",
                            "can-transceiver-tja1051t3", "shunt-values-per-table",
                            "detect-esd-diode-pin8"],
}

# CL-25 intake gate: the SCHEMATIC-SIDE subset -- a board failing any of these is refused
# candidate generation (the TPS2121/desync/R1 classes live upstream of layout). PLUS the
# absolute high-current-pour keepout (owner directive 2026-06-27): a floorplan has no tracks/vias
# so it is a vacuous PASS at intake, but if a ROUTED board is ever fed to intake the foreign-on-pour
# refusal fires there too -- the SAME region-keyed rule the route accept gate uses.
INTAKE_CHECKS = (CL25_CLASSES["sch-pcb-sync"] + CL25_CLASSES["bom-lint"]
                 + CL25_CLASSES["netlist-assertions"]
                 + ["no-foreign-on-high-current-pour"])


# ===========================================================================
#  Checker framework
# ===========================================================================
CHECKERS = {}


def checker(cid):
    def deco(fn):
        CHECKERS[cid] = fn
        return fn
    return deco


# -- geometry / topology helpers ---------------------------------------------
def _mm(v):
    return v / 1e6


def _pads_by_net(board):
    d = collections.defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            d[pad.GetNetname()].append((fp.GetReference(), pad, fp))
    return d


def _fps(board):
    return list(board.GetFootprints())


def _min_pad_dist_mm(fpA, fpB):
    best = 1e9
    for pa in fpA.Pads():
        a = pa.GetPosition()
        for pb in fpB.Pads():
            b = pb.GetPosition()
            best = min(best, math.hypot(_mm(a.x - b.x), _mm(a.y - b.y)))
    return best


def _track_count(board):
    return sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T)


def _edge_bbox(board):
    bb = board.GetBoardEdgesBoundingBox()
    return _mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom())


def _val(fp):
    return (fp.GetValue() or "").strip()


def _is(fp, *subs):
    """ref/value/fpid contains any of subs (case-insensitive)."""
    s = (fp.GetReference() + " " + _val(fp) + " " + fp.GetFPIDAsString()).upper()
    return any(x.upper() in s for x in subs)


def _nets(board):
    return [n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()]


def _param(cid, key, default):
    """CL-03 Ruling 7 resolution order: compiled-PROMOTED value if one exists
    (a promoted param entry whose compile params carry registry_param [cid,key]),
    else the hand value in REGISTRY. While the registry is the bootstrap
    authority (R2 phase 0) nothing promoted exists, so hand values govern; a
    promoted param's promotion PR reconciles the hand value (tombstone in the
    same diff), so promoted-vs-active-hand conflict is a lint ERROR, not a
    runtime choice."""
    hand = next((c.params.get(key, default) for c in REGISTRY if c.id == cid), default)
    try:
        import json as _json
        import cec_facts
        rows = _json.load(open(os.path.join(cec_facts.COMPILED_ROOT, "params.json")))
        for row in rows if isinstance(rows, list) else []:
            if (row.get("binding") == "gate"
                    and (row.get("params") or {}).get("registry_param") == [cid, key]):
                return row.get("value", hand)
    except Exception:                                         # noqa: BLE001
        pass
    return hand


def _direct_sense_pairs(board, kelvin):
    """(_HI,_LO,sense_ic) for pairs where a non-resistor IC taps BOTH halves directly
    (INA238/228). On filtered lanes (INA240 behind an RC) the _HI/_LO are FORCE nets and this
    returns [] -> the Kelvin geometry checks N/A out (need a filter-aware scope)."""
    by_net = _pads_by_net(board)
    out = []
    for hi, lo in kelvin:
        hi_refs = {r for r, _, _ in by_net.get(hi, [])}
        lo_refs = {r for r, _, _ in by_net.get(lo, [])}
        ics = [r for r in (hi_refs & lo_refs) if not r.startswith("R")]
        if ics:
            out.append((hi, lo, ics[0]))
    return out


def _sense_nets(board):
    """Nets at the INA current-sense IC INPUT pins -- the real Kelvin sense (direct _HI/_LO on
    INA238/228, or the post-filter IN_P/_N on the filtered INA240 lanes). Power/gnd/ref/output excluded.
    (Calibration from the 12VHPWR swarm review: scope to these, not the force nets. And restrict to the
    analog SENSE-pair suffixes -- an INA238 also has I2C/SCL/SDA/ALERT digital pins that route freely.)"""
    out = set()
    for fp in board.GetFootprints():
        if "INA2" not in _val(fp).upper():
            continue
        for pad in fp.Pads():
            nu = (pad.GetNetname() or "").upper()
            if nu and (nu.endswith("_HI") or nu.endswith("_LO") or nu.endswith("_P") or nu.endswith("_N")):
                out.add(pad.GetNetname())
    return out


def _force_nets(board):
    """Nets carrying high current (poured, or >=1.5mm copper). A shared force+sense net's force leg
    may legitimately run on B.Cu, so off-F.Cu is only a fault on the low-current sense leg."""
    force = set()
    for z in board.Zones():
        try:
            if z.GetFilledArea() > 0:
                force.add(z.GetNetname())
        except Exception:
            force.add(z.GetNetname())
    widest = collections.defaultdict(float)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T:
            widest[t.GetNetname()] = max(widest[t.GetNetname()], _mm(t.GetWidth()))
    force |= {n for n, w in widest.items() if w >= 1.5}
    return force


def _drc_json(path, ctx):
    """kicad-cli DRC json, run ONCE per board and cached on ctx (multiple checkers share it)."""
    key = "_drc_json::" + path
    if key in ctx:
        return ctx[key]
    out = os.path.join(tempfile.gettempdir(), "cec_cons_drc_%d.json" % os.getpid())
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", out, path], capture_output=True)
    try:
        j = json.load(open(out))
    except Exception:
        j = {}
    ctx[key] = j
    return j


def _unconnected(path, ctx):
    """[(net, [descriptions...]), ...] -- the DRC unconnected ratlines (the real connectivity gaps).
    A board can have 0 shorts and still be non-functional with open nets; this is what 'clean' must check."""
    out = []
    for u in _drc_json(path, ctx).get("unconnected_items", []):
        descs = [it.get("description", "") for it in u.get("items", [])]
        net = ""
        for d in descs:
            m = re.search(r"\[([^\]]+)\]", d)
            if m:
                net = m.group(1)
                break
        out.append((net, descs))
    return out


def _dcir_solve(path, ctx):
    """Run the cec_dcir 2.5D DC IR-drop / current-density field solve ONCE per board, cached on ctx
    (shaped like _drc_json so a future second consumer shares it). Returns {net: result|None}, or None
    if the solver / numpy is unavailable -- FALLBACK-SAFE so the checker N/A-s out rather than ERRORing
    on a box without numpy. Params (grid pitch, oz weights) come from the min-pour-cross-section entry."""
    key = "_dcir::" + path
    if key in ctx:
        return ctx[key]
    res = None
    try:
        import cec_dcir
        res = cec_dcir.solve(
            path,
            h=_param("min-pour-cross-section", "grid_mm", 0.4),
            oz_outer=_param("min-pour-cross-section", "oz_outer", 2.0),
            oz_inner=_param("min-pour-cross-section", "oz_inner", 1.0),
        )
    except Exception:
        res = None
    ctx[key] = res
    return res


# -- checkers ----------------------------------------------------------------
@checker("kelvin-sense-fcu-no-via")
def _chk_kelvin_fcu(board, path, ctx):
    sense = _sense_nets(board)
    if not sense:
        return None, "no INA sense-input nets resolved"
    if _track_count(board) == 0:
        return None, "unrouted floorplan (route-time check)"
    force = _force_nets(board)
    bad = []
    for t in board.GetTracks():
        n = t.GetNetname()
        if n not in sense:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            bad.append("via on %s" % n)                        # §6.8: never route the sense down-and-back
        elif t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() != pcbnew.F_Cu and n not in force:
            bad.append("%s off F.Cu" % n)                      # off-F.Cu only faults the low-current sense leg
    if bad:
        return (False, "Kelvin sense not top-layer/no-via: " + "; ".join(sorted(set(bad))[:6]),
                [{"type": "keepout", "reserve": "F.Cu-route", "nets": sorted(sense)}])
    return True, "all %d INA sense-input nets clean (F.Cu / no sense via)" % len(sense)


@checker("kelvin-sense-adjacent-shunt")
def _chk_kelvin_adj(board, path, ctx):
    kelvin, _ = cec_score._derive_pairs(_nets(board))
    by_net = _pads_by_net(board)
    max_mm = _param("kelvin-sense-adjacent-shunt", "max_mm", 5.0)
    direct = _direct_sense_pairs(board, kelvin)
    if direct:
        fails, oks, payload = [], [], []
        for hi, lo, ic_ref in direct:
            hi_fps = {r: fp for r, _, fp in by_net.get(hi, [])}
            sh = [r for r in hi_fps if r.startswith("R")]
            if not sh:
                continue
            d = _min_pad_dist_mm(hi_fps[ic_ref], hi_fps[sh[0]])
            (oks if d <= max_mm else fails).append("%s<->%s %.2f" % (ic_ref, sh[0], d))
            if d > max_mm:
                payload.append({"type": "adjacent", "a": ic_ref, "b": sh[0], "max_mm": max_mm, "got_mm": round(d, 2)})
        if fails:
            return False, "Kelvin loop > %.0fmm: %s" % (max_mm, "; ".join(fails)), payload
        if oks:
            return True, "direct-sense ICs <= %.0fmm from shunt: %s" % (max_mm, "; ".join(oks))
    # filtered lanes (INA240 behind an RC): the sense path is the in-column shunt->filter->INA, so the
    # adjacency that matters is the INA being column-aligned with its shunt (calibration from the swarm review).
    inas = [fp for fp in board.GetFootprints() if "INA2" in _val(fp).upper()]
    shunts = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    if not inas or not shunts:
        return None, "no sense IC / shunt pair to check"
    tol, fails = 1.0, []
    for ina in inas:
        ix = _mm(ina.GetPosition().x)
        s = min(shunts, key=lambda sh: abs(_mm(sh.GetPosition().x) - ix))
        dx = abs(_mm(s.GetPosition().x) - ix)
        if dx > tol:
            fails.append("%s<->%s dX=%.2f" % (ina.GetReference(), s.GetReference(), dx))
    if fails:
        return (False, "filtered lane INA not column-aligned with its shunt: " + "; ".join(fails[:6]),
                [{"type": "align", "a": f.split("<")[0], "axis": "X"} for f in fails[:6]])
    return True, "filtered lanes: all %d INA240 column-aligned with their shunt (<=%.1fmm dX)" % (len(inas), tol)


@checker("logo-bcu-keepout")
def _chk_logo(board, path, ctx):
    if _track_count(board) == 0:
        if any(fp.GetReference().upper().startswith("LOGO") for fp in board.GetFootprints()):
            return None, "unrouted: LOGO needs a routing keepout (can't verify short pre-route)"
        return None, "no LOGO footprint"
    _, loci = cec_score.drc_types(path)   # standalone path-only form (R-02 single-source)
    bad = [lc for lc in loci if "LOGO" in lc["where"].upper() and not cec_dispatch._locus_is_finishing(lc)]
    if bad:
        nets = sorted({n for lc in bad for n in cec_dispatch._bracket_nets(lc["where"])
                       if n not in ("<no net>", "no net", "GND", "")})
        logos = sorted({r for lc in bad for r in cec_dispatch._fp_refs(lc["where"]) if r.upper().startswith("LOGO")})
        return (False, "LOGO shorts functional nets: %s (%d hits)" % (", ".join(nets), len(bad)),
                [{"type": "keepout", "target": logos[0] if logos else "LOGO1", "layer": "B.Cu", "nets": nets}])
    return True, "LOGO touches only GND/no-net (finishing-acceptable)"


# -- via-on-pad (via-in-pad / short) -----------------------------------------
# KiCad DRC does NOT flag a via whose copper overlaps a pad on the SAME net by
# default, yet the layer-swap / B.Cu-mirror finishing stages drop 1-6 of these
# per board (a via punched dead-centre into a decoupling-cap / sense pad to reach
# B.Cu). SAME-net = via-in-pad (open barrel wicks solder -> needs tent/fill);
# DIFF-net = a hard short. Geometry: model the via as its outer-copper circle
# (radius = via diameter / 2) and test copper overlap against each pad's effective
# shape on every SHARED copper layer. A cheap inflated-bbox prefilter keeps the
# scan O(vias) on real boards (and never false-rejects: a real overlap puts the via
# centre within vr of the pad, hence inside the bbox inflated by vr).
def _via_radius_nm(via):
    """Via outer-copper radius (nm). On a PCB_VIA the no-arg GetWidth() asserts on
    debug builds (the documented KiCad-10 runner footgun) -- pass the top layer."""
    try:
        return int(via.GetWidth(via.TopLayer()) / 2)
    except TypeError:
        return int(via.GetWidth() / 2)


def _via_pad_overlaps(board):
    """Geometry core: (same_net, diff_net), each a list of overlap records
    {ref,pad,pad_net,via_net,x,y}. A record is emitted when a via's outer-copper
    circle overlaps a pad's copper on a shared copper layer; the two classes differ
    only in whether the via and pad nets match (SAME = via-in-pad, DIFF = short)."""
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    pads = [(fp.GetReference(), pad) for fp in board.GetFootprints() for pad in fp.Pads()]
    same, diff = [], []
    for via in vias:
        vpos = via.GetPosition()
        vr = _via_radius_nm(via)
        vnet = via.GetNetname()
        vlayers = set(via.GetLayerSet().CuStack())
        for ref, pad in pads:
            bb = pad.GetBoundingBox()
            bb.Inflate(vr)
            if not bb.Contains(vpos):
                continue                              # cheap reject before the per-layer Collide
            shared = vlayers & set(pad.GetLayerSet().CuStack())
            if not shared:
                continue
            hit = False
            for L in shared:
                try:
                    if pad.GetEffectiveShape(L).Collide(vpos, vr):
                        hit = True
                        break
                except Exception:                     # noqa: BLE001 -- a weird pad shape never breaks the scan
                    continue
            if not hit:
                continue
            pnet = pad.GetNetname()
            rec = {"ref": ref, "pad": pad.GetPadName(), "pad_net": pnet, "via_net": vnet,
                   "x": round(_mm(vpos.x), 3), "y": round(_mm(vpos.y), 3)}
            (same if vnet == pnet else diff).append(rec)
    return same, diff


def via_on_pad_summary(board_path):
    """Load a board and summarise its via-on-pad overlaps: {same, diff, n_vias,
    same_detail, diff_detail}. The public entry cec_router.route's INDEPENDENT verdict
    reads so a via-in-pad board can never pass silently. Callers wrap in try/except --
    a verdict must never break on the checker."""
    board = pcbnew.LoadBoard(board_path)
    n_vias = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)
    same, diff = _via_pad_overlaps(board)
    return {"same": len(same), "diff": len(diff), "n_vias": n_vias,
            "same_detail": same, "diff_detail": diff}


def _fmt_vop(r):
    return "%s.%s[%s]@(%.2f,%.2f)" % (r["ref"], r["pad"], r["pad_net"] or "<no net>", r["x"], r["y"])


@checker("via-on-pad")
def _chk_via_on_pad(board, path, ctx):
    if not any(t.Type() == pcbnew.PCB_VIA_T for t in board.GetTracks()):
        return None, "no vias on this board (floorplan or fully-planar route)"
    same, diff = _via_pad_overlaps(board)
    nv = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)
    if not same and not diff:
        return True, "no via copper overlaps a pad (%d vias checked)" % nv
    msgs, payload = [], []
    if same:
        msgs.append("%d SAME-net via-in-pad (tent/fill required): %s%s"
                    % (len(same), ", ".join(_fmt_vop(r) for r in same[:6]),
                       "" if len(same) <= 6 else " (+%d)" % (len(same) - 6)))
        payload += [{"type": "via_on_pad", "kind": "via_in_pad_same_net", **r} for r in same]
    if diff:
        msgs.append("%d DIFF-net via-on-pad (SHORT): %s%s"
                    % (len(diff), ", ".join("%s<-via[%s]" % (_fmt_vop(r), r["via_net"] or "<no net>")
                                            for r in diff[:6]),
                       "" if len(diff) <= 6 else " (+%d)" % (len(diff) - 6)))
        payload += [{"type": "via_on_pad", "kind": "short_diff_net", **r} for r in diff]
    return False, "; ".join(msgs), payload


# ===========================================================================
#  no-foreign-on-high-current-pour -- THE absolute keepout (owner directive 2026-06-27)
# ===========================================================================
# ONE authoritative region = cec_fr.derive_power_pours (the same rectangles add_power_pours
# fills and sense-body-clear-of-pour checks). The placer, router and accept gate all key off
# it. A foreign-net track on the pour layer (or a via in the pour) silently antipads/fragments
# the 40A fill -- KiCad DRC does NOT flag it -- so this gate is GEOMETRIC (sampled against the
# pour rectangle), never DRC-derived. GND + power rails ARE foreign on the single-layer pour.
class PourRegionError(RuntimeError):
    """The high-current pour region-finder (cec_fr.derive_power_pours) failed -- raised or returned
    empty -- on a board that ACTUALLY HAS high-current SENSEC pour copper laid. This is a fail-CLOSED
    condition: a safety keepout gate must NEVER report N/A-pass when there is pour copper it cannot
    locate to protect (owner-flagged fail-open, 2026-06-28). A genuine no-pour board never raises it."""


def _has_sensec_pours(board):
    """True iff the board carries actual high-current SENSEC corridor copper zones -- the additive
    F.Cu/B.Cu pours add_power_pours / synthesize_power_copper lay on the _HI/_LO (and 12V) force nets.
    Read straight from board.Zones(), INDEPENDENT of cec_fr.derive_power_pours, so the SAME SWIG /
    geometry / net-corruption error that breaks the pad-geometry region-finder cannot ALSO hide this
    signal (derive works off connector+shunt PAD geometry; this reads ZONE copper). Uses the same net
    predicate derive_power_pours keys off (the _HI/_LO Kelvin pairs, + the 12V convention) so
    has-pours-but-derive-empty is exactly the placement/geometry inconsistency to fail closed on. Fill
    state is ignored (kicad-cli leaves zones unfilled)."""
    for z in board.Zones():
        if z.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
            continue
        n = z.GetNetname() or ""
        if n.endswith(("_HI", "_LO")) or "12V" in n.upper():
            return True
    return False


def _derive_pour_boxes(board, path):
    """The authoritative per-cable high-current pour rectangles, filtered to genuine cable
    corridors, with the allowed-net set. Returns (boxes, allowed) or (None, None) when GENUINELY N/A
    (no SENSEC pour copper at all, or every derived pour is on a shared-bus per-pin/per-rail connector
    -- 12VHPWR J3/J4, 24-pin J3/J4 -- whose lane/rail legitimately packs the sense chain).
    boxes = [(own_net, layer_id, x0, x1, y0, y1)] (mm).

    FAIL-CLOSED: raises PourRegionError when the board HAS SENSEC pour copper (``_has_sensec_pours``)
    but derive_power_pours raises OR returns empty -- the region the keepout gate must protect exists
    yet is undetectable, so the gate must FAIL, never silently report N/A-pass. A board with no SENSEC
    pours (Hub, or a pre-route floorplan) keeps the benign (None, None) N/A; the all-shared-bus
    ``not boxes`` path is reached only AFTER a successful non-empty derive, so 12VHPWR / 24-pin / Hub
    stay correctly N/A and never false-fire."""
    import cec_fr
    has_pours = _has_sensec_pours(board)
    try:
        pours = cec_fr.derive_power_pours(path, board=board)
    except Exception as e:                                  # noqa: BLE001
        if has_pours:
            raise PourRegionError(
                "derive_power_pours RAISED on a board WITH high-current SENSEC pours: %s: %s"
                % (type(e).__name__, e)) from e
        return None, None                                  # genuine N/A: no pour copper to protect
    if not pours:
        if has_pours:
            raise PourRegionError(
                "board carries high-current SENSEC F.Cu/B.Cu pour zones but derive_power_pours found "
                "NO corridor (placement/geometry inconsistency -- the region the absolute keepout gate "
                "must protect is undetectable)")
        return None, None                                  # genuine N/A: no SENSEC pours at all
    kelvin, _ = cec_score._derive_pairs(_nets(board))
    by_net = _pads_by_net(board)
    shared = _shared_bus_conns(kelvin, by_net)
    layer_id = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    boxes, own = [], set()
    for pr in pours:
        net = pr["net"]
        jrefs = {ref for ref, _, _ in by_net.get(net, []) if ref.upper().startswith("J")}
        if jrefs & shared:
            continue                                       # shared-bus per-pin/per-rail -> N/A
        xs = [p[0] for p in pr["polygon"]]
        ys = [p[1] for p in pr["polygon"]]
        boxes.append((net, layer_id.get(pr["layer"], pcbnew.F_Cu),
                      min(xs), max(xs), min(ys), max(ys)))
        own.add(net)
    if not boxes:
        return None, None
    return boxes, (own | _sense_nets(board))


def _foreign_pour_records(board, path):
    """(tracks, vias) -- foreign-net copper intruding the authoritative pour boxes, each a
    record {net, pour[, x, y]}. A track counts when any of `sample_pts` points along it lands
    in a box ON THE BOX'S LAYER; a via counts when it sits in a box and its barrel reaches the
    box layer. FOREIGN = not the pour's own net and not an INA sense-input net (the deliberate
    Kelvin tap); GND/power INCLUDED. N/A -> (None, None)."""
    boxes, allowed = _derive_pour_boxes(board, path)
    if boxes is None:
        return None, None
    n_samp = int(_param("no-foreign-on-high-current-pour", "sample_pts", 11))

    def _foreign(n):
        return bool(n) and n not in allowed and "unconnected-" not in n.lower()

    tracks, vias = [], []
    for t in board.GetTracks():
        n = t.GetNetname()
        if not _foreign(n):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            vstack = set(t.GetLayerSet().CuStack())
            vp = t.GetPosition()
            for net, lid, x0, x1, y0, y1 in boxes:
                if lid in vstack and x0 <= _mm(vp.x) <= x1 and y0 <= _mm(vp.y) <= y1:
                    vias.append({"net": n, "pour": net,
                                 "x": round(_mm(vp.x), 2), "y": round(_mm(vp.y), 2)})
                    break
        elif t.Type() == pcbnew.PCB_TRACE_T:
            lid = t.GetLayer()
            s, e = t.GetStart(), t.GetEnd()
            for net, blid, x0, x1, y0, y1 in boxes:
                if lid != blid:
                    continue
                hit = False
                for k in range(n_samp):
                    px = s.x + (e.x - s.x) * k // (n_samp - 1)
                    py = s.y + (e.y - s.y) * k // (n_samp - 1)
                    if x0 <= _mm(px) <= x1 and y0 <= _mm(py) <= y1:
                        hit = True
                        break
                if hit:
                    tracks.append({"net": n, "pour": net})
                    break
    return tracks, vias


def _foreign_by_pour(tracks, vias):
    by = collections.defaultdict(collections.Counter)
    for r in tracks:
        by[r["pour"]][r["net"]] += 1
    for r in vias:
        by[r["pour"]]["via:" + r["net"]] += 1
    return {k: dict(v) for k, v in by.items()}


def foreign_on_pour_summary(board_path):
    """Public summary (mirrors via_on_pad_summary): {applicable, status, n_tracks, n_vias, by_pour,
    tracks, vias, n_pours}. cec_router.route()'s INDEPENDENT verdict folds status=='error' AND
    n_tracks+n_vias into gates_pass so a foreign-on-pour board can never pass silently.

    status:
      "ok"    -- the region was derived; n_tracks/n_vias are the real foreign-crossing counts.
      "na"    -- genuinely not applicable (no SENSEC pour copper / all-shared-bus) -> applicable=False.
      "error" -- FAIL-CLOSED: the board HAS SENSEC pours but the region-finder raised/returned empty.
                 applicable=True (NOT a vacuous N/A) so the router fold fails the verdict instead of
                 passing silently. counts are 0 (the region could not be derived to count against)."""
    board = pcbnew.LoadBoard(board_path)
    try:
        tracks, vias = _foreign_pour_records(board, board_path)
    except PourRegionError as e:
        return {"applicable": True, "status": "error", "error": str(e),
                "n_tracks": 0, "n_vias": 0, "by_pour": {}, "tracks": [], "vias": [], "n_pours": 0}
    if tracks is None:
        return {"applicable": False, "status": "na", "n_tracks": 0, "n_vias": 0,
                "by_pour": {}, "tracks": [], "vias": [], "n_pours": 0}
    boxes, _ = _derive_pour_boxes(board, board_path)
    return {"applicable": True, "status": "ok", "n_tracks": len(tracks), "n_vias": len(vias),
            "by_pour": _foreign_by_pour(tracks, vias),
            "tracks": tracks[:60], "vias": vias[:60], "n_pours": len(boxes or [])}


@checker("no-foreign-on-high-current-pour")
def _chk_foreign_on_pour(board, path, ctx):
    """ABSOLUTE high-current-pour keepout (owner directive 2026-06-27). For each authoritative
    derive_power_pours box (genuine per-cable corridor), assert ZERO foreign-net track (same
    layer) or via crosses it -- GND/power INCLUDED. Geometric, not DRC-derived (KiCad's zone
    filler carves antipads around a foreign trace with NO clearance error, so ~80% of the
    crossings are invisible to drc==0). The placer keeps foreign BODIES out via
    sense-body-clear-of-pour; this rule is the gate for foreign TRACKS/VIAS. N/A on shared-bus /
    non-cable boards (12VHPWR per-pin, 24-pin per-rail, Hub).

    FAIL-CLOSED (owner-flagged fail-open, 2026-06-28): if the board HAS SENSEC pour copper but the
    region-finder raises/returns empty, FAIL (the keepout cannot be verified) instead of skipping N/A."""
    try:
        tracks, vias = _foreign_pour_records(board, path)
    except PourRegionError as e:
        return (False, "FAIL-CLOSED: high-current pour region-finder errored on a board WITH SENSEC "
                "pours -- the absolute keepout cannot be verified (a missed intrusion would necks/"
                "fragments the 40A fill): %s" % e)
    if tracks is None:
        return None, "no per-cable high-current pour region (shared-bus / non-cable board)"
    if not tracks and not vias:
        return True, "no foreign track/via crosses any high-current pour region"
    by_pour = _foreign_by_pour(tracks, vias)
    msg = "; ".join("%s<-%s" % (p, c) for p, c in sorted(by_pour.items()))
    payload = [{"type": "keepout", "reserve": "high-current-pour-foreign",
                "pour": p, "foreign": c} for p, c in sorted(by_pour.items())]
    return (False, "foreign copper crosses a high-current pour (ABSOLUTE keepout): %d track(s), "
            "%d via(s) -- %s" % (len(tracks), len(vias), msg[:240]), payload)


@checker("high-current-pour-present")
def _chk_pour(board, path, ctx):
    hc = [n for n in _nets(board) if "12V" in n.upper() or n.endswith("_HI")]
    if not hc:
        return None, "no high-current nets"
    if _track_count(board) == 0:
        return None, "floorplan: pours are a route-time step"
    poured = set()
    for z in board.Zones():
        try:
            if z.GetFilledArea() > 0:
                poured.add(z.GetNetname())
        except Exception:
            poured.add(z.GetNetname())
    widest = collections.defaultdict(float)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T:
            widest[t.GetNetname()] = max(widest[t.GetNetname()], _mm(t.GetWidth()))
    # carried = poured OR routed with adequate-width copper (>=1.5mm wide trace, e.g. 12VHPWR lanes)
    missing = sorted({n for n in hc if n not in poured and widest.get(n, 0.0) < 1.5})
    if missing:
        return (False, "high-current nets not carried by a pour or wide copper: %s" % ", ".join(missing[:6]),
                [{"type": "keepout", "reserve": "pour_or_wide", "nets": missing}])
    return True, "all %d high-current nets carried (pour/wide copper)" % len(set(hc))


@checker("high-current-pour-integrity")
def _chk_pour_integrity(board, path, ctx):
    if _track_count(board) == 0:
        return None, "floorplan (pours are route-time)"
    zones = [z for z in board.Zones()
             if "12V" in z.GetNetname().upper() or z.GetNetname().endswith("_HI") or z.GetNetname().endswith("_LO")]
    if not zones:
        return None, "no high-current pour"
    cut = set()
    for z in zones:
        zn, zl, outline = z.GetNetname(), z.GetLayer(), z.Outline()
        for t in board.GetTracks():
            if t.Type() != pcbnew.PCB_TRACE_T or t.GetNetname() == zn or t.GetLayer() != zl:
                continue   # same net merges into the pour; a different layer is fine
            s, e = t.GetStart(), t.GetEnd()
            mid = pcbnew.VECTOR2I((s.x + e.x) // 2, (s.y + e.y) // 2)
            for pt in (s, e, mid):
                try:
                    if outline.Contains(pt):
                        cut.add((zn, t.GetNetname()))
                        break
                except Exception:
                    pass
    if cut:
        return (False, "12V pour cut by a same-layer foreign trace: " + "; ".join("%s<-%s" % (a, b) for a, b in sorted(cut)[:6]),
                [{"type": "keepout", "reserve": "pour-region-foreign-signal", "nets": sorted({a for a, _ in cut})}])
    return True, "no foreign same-layer trace cuts a high-current pour"


def _shared_bus_conns(kelvin, by_net):
    """Connector refs that serve MORE THAN ONE Kelvin pair -- a shared-bus / multi-rail connector
    (the 24-pin ATX J3/J4, the 12VHPWR J3/J4). The per-cable J_IN->shunt->J_OUT corridor model does
    NOT apply to those (they use a Phase-5 per-pin variant); the checkers N/A any pair on one."""
    serves = collections.defaultdict(set)
    for hi, lo in kelvin:
        for ref, _p, _fp in by_net.get(hi, []) + by_net.get(lo, []):
            if ref.upper().startswith("J"):
                serves[ref].add(hi[:-3])
    return {ref for ref, pairs in serves.items() if len(pairs) > 1}


def _corridor_bands(board):
    """(bands, corridor_nets): per per-cable Kelvin pair the band = bbox over the cable CONNECTOR
    (J*) + 2-pad shunt pads on its HI/LO nets -- the J_IN->shunt->J_OUT current path. The INA's SMD
    sense pads are EXCLUDED (matching cec_fr.derive_power_pours: THT connector + 2-pad shunt), so the
    band is not inflated to swallow the sense fan-out. A pair on a SHARED-BUS connector (24-pin /
    12VHPWR) or whose band is DEGENERATE (wider than ~half the board -> shunt not inline / connectors
    not aligned) is dropped -- the per-cable corridor does not apply there."""
    kelvin, _ = cec_score._derive_pairs(_nets(board))
    by_net = _pads_by_net(board)
    l, _t, r, _b = _edge_bbox(board)
    board_w = max(1.0, r - l)
    shared = _shared_bus_conns(kelvin, by_net)
    padn = {fp.GetReference(): len(list(fp.Pads())) for fp in board.GetFootprints()}
    bands, corridor = {}, set()
    for hi, lo in kelvin:
        hi_nodes, lo_nodes = by_net.get(hi, []), by_net.get(lo, [])
        corridor |= {hi, lo}
        refs_hi = {ref for ref, _, _ in hi_nodes}
        refs_lo = {ref for ref, _, _ in lo_nodes}
        jrefs = {ref for ref in (refs_hi | refs_lo) if ref.upper().startswith("J")}
        if jrefs & shared:
            continue                                   # shared-bus connector -> Phase-5 variant
        straddle = refs_hi & refs_lo
        shunt = next((x for x in sorted(straddle) if x.upper().startswith("RS") and padn.get(x) == 2),
                     next((x for x in sorted(straddle) if x.startswith("R") and padn.get(x) == 2), None))
        band_refs = set(jrefs) | ({shunt} if shunt else set())
        pts = [p.GetPosition() for ref, p, _ in (hi_nodes + lo_nodes) if ref in band_refs]
        if not pts:
            continue
        xs = [_mm(p.x) for p in pts]
        ys = [_mm(p.y) for p in pts]
        if (max(xs) - min(xs)) > 0.55 * board_w:       # degenerate: not a tight per-cable column
            continue
        bands[hi[:-3]] = (min(xs) - 1.5, max(xs) + 1.5, min(ys), max(ys))
    return bands, corridor


def _is_corridor_signal(net, corridor, sense=()):
    """A foreign net that can intrude the corridor: not a corridor force net, not GND/a power rail
    (those legitimately stitch/pour), not an INA SENSE net (*sense* = the INA input nets incl. the
    12VHPWR _P/_N), not a KiCad auto-named floating net -- i.e. a real routed control/signal net."""
    if net in corridor or net in sense or not net:
        return False
    if "unconnected-" in net.lower():
        return False
    base = net.rsplit("/", 1)[-1].upper()
    if base in ("GND",) or re.search(r"(^|/)\+?(3V3|5VSB|5V|12V|VBUS|VCC)$", net, re.I):
        return False
    if net.endswith(("_HI", "_LO")) or base.startswith(("SENSEC", "ISENSE")):
        return False
    return True


@checker("shunt-inline-in-corridor")
def _chk_shunt_inline(board, path, ctx):
    """PLACEMENT check (no route needed): each cable shunt RS{n} lies between its J_IN (force-in,
    on _HI) and J_OUT (force-out, on _LO) connector pads, so current flows THROUGH it with no
    bypass (spec §6.7). The shunt centroid must fall inside the bbox spanned by the in/out
    connector force-pad centroids (+tol). N/A on shared-bus connectors (24-pin / 12VHPWR fan-out),
    whose per-pin path the connector-centroid test cannot model -- a Phase-5 per-pin variant."""
    kelvin, _ = cec_score._derive_pairs(_nets(board))
    if not kelvin:
        return None, "no Kelvin pair (board carries no high-current cable)"
    by_net = _pads_by_net(board)
    shared = _shared_bus_conns(kelvin, by_net)
    tol = _param("shunt-inline-in-corridor", "tol_mm", 2.0)
    fails, oks, checked = [], [], 0
    for hi, lo in kelvin:
        hi_nodes, lo_nodes = by_net.get(hi, []), by_net.get(lo, [])
        hi_refs = {r for r, _, _ in hi_nodes}
        lo_refs = {r for r, _, _ in lo_nodes}
        jrefs = {r for r in (hi_refs | lo_refs) if r.upper().startswith("J")}
        if jrefs & shared:
            continue                                   # shared-bus fan-out -> centroid test N/A
        straddle = sorted(hi_refs & lo_refs)
        shunt = next((r for r in straddle if r.upper().startswith("RS")),
                     next((r for r in straddle if r.startswith("R")), None))
        jin = [p.GetPosition() for r, p, _ in hi_nodes if r.upper().startswith("J")]
        jout = [p.GetPosition() for r, p, _ in lo_nodes if r.upper().startswith("J")]
        if not shunt or not jin or not jout:
            continue
        sh_fp = next(fp for r, _p, fp in (hi_nodes + lo_nodes) if r == shunt)
        sx, sy = _mm(sh_fp.GetPosition().x), _mm(sh_fp.GetPosition().y)
        ix = sum(_mm(p.x) for p in jin) / len(jin)
        iy = sum(_mm(p.y) for p in jin) / len(jin)
        ox = sum(_mm(p.x) for p in jout) / len(jout)
        oy = sum(_mm(p.y) for p in jout) / len(jout)
        checked += 1
        inline = (min(ix, ox) - tol <= sx <= max(ix, ox) + tol and
                  min(iy, oy) - tol <= sy <= max(iy, oy) + tol)
        (oks if inline else fails).append("%s @(%.1f,%.1f) in[%s] out[%s]"
                                          % (shunt, sx, sy, hi[1:], lo[1:]))
    if checked == 0:
        return None, "no per-cable shunt with both in/out connector pads (shared-bus or absent)"
    if fails:
        return (False, "shunt not inline in the J_IN->J_OUT current path: " + "; ".join(fails[:6]),
                [{"type": "region", "reserve": "shunt-on-current-axis"}])
    return True, "all %d shunts inline between their in/out connectors" % len(oks)


@checker("high-current-corridor-keepout")
def _chk_corridor_keepout(board, path, ctx):
    """ROUTE-time check: no foreign signal track/via inside a per-cable J_IN->shunt->J_OUT band (it
    is reserved for the pour; a foreign trace there cuts the fill -- the eps-8pin failure mode).
    The post-route teeth for the placer's corridor_cross_count. N/A on shared-bus / degenerate
    boards (no per-cable band resolved)."""
    if _track_count(board) == 0:
        return None, "floorplan (corridor keepout is a route-time check)"
    bands, corridor = _corridor_bands(board)
    if not bands:
        return None, "no per-cable high-current corridor (shared-bus / degenerate)"
    sense = _sense_nets(board)                          # INA input nets (incl. 12VHPWR _P/_N) -- not foreign
    intruders = set()
    for t in board.GetTracks():
        n = t.GetNetname()
        if not _is_corridor_signal(n, corridor, sense):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            pts = [t.GetPosition()]
        else:
            s, e = t.GetStart(), t.GetEnd()
            pts = [s, e, pcbnew.VECTOR2I((s.x + e.x) // 2, (s.y + e.y) // 2)]
        for base, (X0, X1, Y0, Y1) in bands.items():
            if any(X0 <= _mm(p.x) <= X1 and Y0 <= _mm(p.y) <= Y1 for p in pts):
                intruders.add((base, n))
    if intruders:
        return (False, "foreign signal inside a high-current corridor: "
                + "; ".join("%s<-%s" % (b, n) for b, n in sorted(intruders)[:6]),
                [{"type": "keepout", "reserve": "corridor-foreign-signal",
                  "bands": sorted(bands)}])
    return True, "no foreign signal track/via inside a high-current corridor (%d band(s))" % len(bands)


@checker("min-pour-cross-section")
def _chk_min_cross(board, path, ctx):
    """ADVISORY: run the cec_dcir DC field solve and flag any poured high-current net whose bottleneck
    cross-section runs the current density past j_max (= eff_cross < I/j_max). Surfaces OQ-10/OQ-12
    numbers; does NOT hard-gate (severity advisory). FAIL emits a 'reserve more pour' placer keepout."""
    if _track_count(board) == 0:
        return None, "floorplan: cross-section is a route-time field solve"
    hc_poured = {z.GetNetname() for z in board.Zones()
                 if "12V" in z.GetNetname().upper() or z.GetNetname().endswith(("_HI", "_LO"))}
    if not hc_poured:
        return None, "no poured high-current net"
    res = _dcir_solve(path, ctx)
    if res is None:
        return None, "DC field solver unavailable (numpy/cec_dcir)"
    solved = {n: r for n, r in res.items() if r}
    if not solved:
        return None, "no net resolved a 2-terminal force path (no field solution)"
    j_max = _param("min-pour-cross-section", "j_max_A_mm2", 100.0)
    fails, payload, worst = [], [], []
    for net, r in sorted(solved.items()):
        j, cur = r["j_p995_A_mm2"], r["I"]
        need, got = round(cur / j_max, 3), r["eff_cross_mm2"]
        worst.append((j, net))
        if j > j_max:
            fails.append("%s I=%.0fA J=%.0f>%.0f (cross %.3f<%.3f mm^2, IRdrop %.0fmV)"
                         % (net, cur, j, j_max, got, need, r["ir_drop_V"] * 1000))
            payload.append({"type": "keepout", "reserve": "pour-cross-section", "net": net,
                            "got_mm2": got, "need_mm2": need, "j_p995_A_mm2": j, "j_max_A_mm2": j_max})
    if fails:
        return (False, "pour cross-section under J<=%.0f A/mm^2 (advisory; OQ-10/12 input): %s"
                % (j_max, "; ".join(fails[:6])), payload)
    hi = max(worst)
    return True, ("all %d solved high-current nets within J<=%.0f A/mm^2 (worst %s J=%.0f)"
                  % (len(solved), j_max, hi[1], hi[0]))


@checker("kelvin-sense-from-inner-pad")
def _chk_kelvin_inner(board, path, ctx):
    """FULL §6.8 four-wire tap check (the directive=inner_tap ENFORCE leg). For each 2-pad shunt sense
    pad, a thin F.Cu stub must (a) LEAVE FROM THE INNER EDGE (inner-ness >= inner_min_mm), (b) run as a
    DIRECT F.Cu segment (no via -- a single track has none) whose far end TERMINATES ON an INA input pad
    on that net (HI->IN+, LO->IN-). The generative builder cec_fr.synthesize_kelvin_taps lays exactly
    this, so build and check agree by construction; a centre/outer tap or a stub that never reaches the
    IN+/IN- pad FAILs. On FAIL we emit an inner_tap payload so the route-time synth can (re)build it."""
    if _track_count(board) == 0:
        return None, "floorplan (route-time)"
    shunts = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    sense = _sense_nets(board)
    if not shunts or not sense:
        return None, "no shunt / sense nets"
    inner_min = _param("kelvin-sense-from-inner-pad", "inner_min_mm", 0.1)
    ina_reach = _param("kelvin-sense-from-inner-pad", "ina_reach_mm", 0.9)
    # INA input pads on each sense net -- the topology TARGET the tap must terminate on.
    ina_pads = collections.defaultdict(list)                 # net -> [(x_mm, y_mm)]
    for fp in board.GetFootprints():
        if not _is(fp, "INA2", "INA181"):
            continue
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn in sense:
                pp = p.GetPosition()
                ina_pads[nn].append((_mm(pp.x), _mm(pp.y)))
    # the tap stubs: thin tracks on a sense net, restricted to F.Cu (no-via leg of §6.8 -- a via is not
    # a PCB_TRACE_T, and an off-F.Cu sense trace is the down-and-back the tap must replace).
    thin = collections.defaultdict(list)
    for t in board.GetTracks():
        if (t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() in sense
                and _mm(t.GetWidth()) <= 0.4 and t.GetLayer() == pcbnew.F_Cu):
            thin[t.GetNetname()].append(t)
    bad, checked, payload = [], 0, []
    for sh in shunts:
        pads = list(sh.Pads())
        if len(pads) < 2:
            continue
        cen = [p.GetPosition() for p in pads]
        for i, pad in enumerate(pads):
            net = pad.GetNetname()
            if net not in sense:
                continue
            targets = ina_pads.get(net, [])
            if not targets:
                continue                                     # no INA input pad on this net -> N/A here
            pc, other = pad.GetPosition(), cen[1 - i] if len(pads) == 2 else cen[(i + 1) % len(pads)]
            ix, iy = _mm(other.x) - _mm(pc.x), _mm(other.y) - _mm(pc.y)   # inner direction (toward other terminal)
            inn = math.hypot(ix, iy) or 1.0
            ix, iy = ix / inn, iy / inn
            sz = pad.GetSize()
            diag = math.hypot(_mm(sz.x), _mm(sz.y)) / 2 + 0.3
            best_inner, tap_to_ina = None, False
            for t in thin.get(net, []):
                ends = (t.GetStart(), t.GetEnd())
                for j, end in enumerate(ends):
                    ex, ey = _mm(end.x) - _mm(pc.x), _mm(end.y) - _mm(pc.y)
                    if math.hypot(ex, ey) > diag:            # this end is not on/near the shunt pad
                        continue
                    inner = ex * ix + ey * iy                # connection point's inner-ness (mm toward the sense edge)
                    best_inner = inner if best_inner is None else max(best_inner, inner)
                    far = ends[1 - j]                        # the stub's OTHER end -> must reach an INA input pad
                    if (inner >= inner_min
                            and any(math.hypot(_mm(far.x) - tx, _mm(far.y) - ty) <= ina_reach
                                    for tx, ty in targets)):
                        tap_to_ina = True
            if best_inner is None:
                continue                                     # no stub resolvable on this pad -> not checked
            checked += 1
            if tap_to_ina:
                continue
            why = "not inner edge" if best_inner < inner_min else "no direct F.Cu tap to IN+/IN-"
            bad.append("%s pad %s (%s)" % (sh.GetReference(), pad.GetPadName(), why))
            payload.append({"type": "inner_tap", "shunt": sh.GetReference(),
                            "pad": pad.GetPadName(), "net": net, "why": why})
    if checked == 0:
        return None, "no thin Kelvin sense stub resolvable (sense merged with the force pour?)"
    if bad:
        return (False, "Kelvin sense not tapped from the inner shunt edge to IN+/IN-: "
                + "; ".join(bad[:6]), payload)
    return True, "Kelvin inner-edge -> IN+/IN- F.Cu taps verified (%d shunt pad(s))" % checked


# IN+/IN- input pad NAME per current-sense part (Vbus is deliberately absent -- it is a high-Z
# voltage tap, not a Kelvin current-sense input, so it is allowed to FR-route to the connector).
_KELVIN_INPAD = {"INA238": {"_HI": "10", "_LO": "9"},
                 "INA228": {"_HI": "10", "_LO": "9"},
                 "INA181": {"_HI": "3", "_LO": "4"}}


def _kelvin_input_pad_name(fp, net):
    val = _val(fp).upper()
    role = "_HI" if net.endswith("_HI") else ("_LO" if net.endswith("_LO") else None)
    if role is None:
        return None
    for key, m in _KELVIN_INPAD.items():
        if key in val:
            return m.get(role)
    return None


@checker("kelvin-sense-no-connector-tap")
def _chk_kelvin_no_connector_tap(board, path, ctx):
    """The kelvin-from-connector GATE (owner directive 2026-06-28). For each current-sense IC INPUT pad
    (IN+/IN-, by pin function) on a SENSEC _HI/_LO net, count the DISTINCT copper stubs incident on the
    pad (tracks clustered by far endpoint, + vias). A true four-wire Kelvin has EXACTLY ONE via-less F.Cu
    stub landing on the 2-pad shunt's pad; a SECOND stub (FR wiring the same-net pad to the connector / a
    second pour point), a via, or a lone stub that misses the shunt is the defect -- the sense pad is then
    tied to >1 point of the current-carrying copper and the stub carries load current.

    A correct tap legitimately reaches the connector THROUGH the shunt terminal (the HI pour ties the
    shunt terminal to the connector), so 'reaches the connector' is NOT the test -- the parallel SECOND
    connection is. Geometry-local, no fail-open: a board where the only stub lands on the shunt PASSES.
    Self-gating N/A on a floorplan (no tracks) or a board with no 2-pad shunt / INA input on a sense net."""
    if _track_count(board) == 0:
        return None, "floorplan (route-time)"
    sense = _sense_nets(board)
    shunt_pads = collections.defaultdict(list)                  # net -> [(x,y,reach_mm)] of the 2-pad shunt
    for fp in board.GetFootprints():
        if not (fp.GetReference().upper().startswith("RS") and fp.GetPadCount() == 2):
            continue
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn in sense:
                pos = p.GetPosition(); sz = p.GetSize()
                shunt_pads[nn].append((_mm(pos.x), _mm(pos.y), math.hypot(_mm(sz.x), _mm(sz.y)) / 2.0 + 0.3))
    if not sense or not shunt_pads:
        return None, "no 2-pad shunt / sense nets"
    extra = _param("kelvin-sense-no-connector-tap", "pad_reach_extra_mm", 0.15)
    cluster = _param("kelvin-sense-no-connector-tap", "stub_far_cluster_mm", 0.5)
    # index tracks/vias by net once
    net_tracks = collections.defaultdict(list)
    for t in board.GetTracks():
        nn = t.GetNetname()
        if nn in sense:
            net_tracks[nn].append(t)
    bad, checked = [], 0
    for fp in board.GetFootprints():
        if not _is(fp, "INA2", "INA181"):
            continue
        for p in fp.Pads():
            net = p.GetNetname()
            if net not in sense or net not in shunt_pads:
                continue
            want = _kelvin_input_pad_name(fp, net)
            if want is not None and p.GetPadName() != want:
                continue                                       # only the IN+/IN- pad (never Vbus / digital)
            pos = p.GetPosition(); pc = (_mm(pos.x), _mm(pos.y))
            sz = p.GetSize(); reach = math.hypot(_mm(sz.x), _mm(sz.y)) / 2.0 + extra
            fars, vias = [], 0                                  # far endpoints of incident stubs; incident vias
            for t in net_tracks.get(net, []):
                if t.Type() == pcbnew.PCB_VIA_T:
                    vp = t.GetPosition()
                    if math.hypot(_mm(vp.x) - pc[0], _mm(vp.y) - pc[1]) <= reach:
                        vias += 1
                    continue
                ends = ((_mm(t.GetStart().x), _mm(t.GetStart().y)),
                        (_mm(t.GetEnd().x), _mm(t.GetEnd().y)))
                for k, end in enumerate(ends):
                    if math.hypot(end[0] - pc[0], end[1] - pc[1]) <= reach:
                        fars.append(ends[1 - k])               # this stub touches the pad; record its far end
            if not fars and not vias:
                continue                                       # unconnected input -> board-routing-complete owns it
            checked += 1
            # cluster the far endpoints so a split-but-collinear single tap counts once
            clusters = []
            for f in fars:
                if not any(math.hypot(f[0] - c[0], f[1] - c[1]) <= cluster for c in clusters):
                    clusters.append(f)
            n_conn = len(clusters) + vias
            on_shunt = (len(clusters) == 1 and vias == 0
                        and any(math.hypot(clusters[0][0] - sx, clusters[0][1] - sy) <= sr
                                for sx, sy, sr in shunt_pads[net]))
            if n_conn == 1 and on_shunt:
                continue                                       # clean single inner-edge tap to the shunt
            if vias:
                why = "via on the sense input (tap must be via-less F.Cu)"
            elif n_conn >= 2:
                why = "%d parallel stubs (only the single shunt tap is allowed)" % n_conn
            else:
                why = "lone stub does not land on the shunt pad"
            bad.append("%s.%s on %s: %s" % (fp.GetReference(), p.GetPadName(), net, why))
    if checked == 0:
        return None, "no resolvable INA input stub on a sense net"
    if bad:
        return (False, "Kelvin sense input has a parallel/non-shunt connection (carries load current -- "
                "not four-wire): " + "; ".join(bad[:6]),
                [{"type": "inner_tap", "why": "connector_tap", "detail": d} for d in bad])
    return True, "Kelvin sense inputs connect by the single shunt tap alone (%d input pad(s))" % checked


def _fp_courtyard_bbox(fp):
    """Global courtyard bbox (x0,x1,y0,y1) of a footprint (mm). Falls back to the part bbox."""
    xs, ys = [], []
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        sh = fp.GetCourtyard(layer)
        if sh and sh.OutlineCount():
            bb = sh.BBox()
            xs += [_mm(bb.GetLeft()), _mm(bb.GetRight())]
            ys += [_mm(bb.GetTop()), _mm(bb.GetBottom())]
    if not xs:
        bb = fp.GetBoundingBox()
        return (_mm(bb.GetLeft()), _mm(bb.GetRight()), _mm(bb.GetTop()), _mm(bb.GetBottom()))
    return (min(xs), max(xs), min(ys), max(ys))


@checker("sense-body-clear-of-pour")
def _chk_sense_body_clear(board, path, ctx):
    """The current-sense IC sits hard against its shunt (Kelvin), but its BODY must clear the SENSEC
    high-current pour. Build the same pour rectangles the router lays (cec_fr.derive_power_pours) and
    assert each sense IC's courtyard centroid is in the un-poured notch AND its courtyard overlaps the
    pour by <= max_overlap_mm2. This is the geometric ENFORCE leg of the placer's _seat_sense_ics.

    FAIL-CLOSED on the same region-finder hole as no-foreign-on-high-current-pour: a board WITH SENSEC
    pour copper whose region-finder raises/returns empty FAILS (the body-clear cannot be verified),
    never N/A-pass. Genuine no-pour boards keep their N/A skip."""
    import cec_fr
    has_pours = _has_sensec_pours(board)
    try:
        pours = cec_fr.derive_power_pours(path, board=board)
    except Exception as e:                                       # noqa: BLE001
        if has_pours:
            return (False, "FAIL-CLOSED: sense-body-clear region-finder errored on a board WITH SENSEC "
                    "pours (%s) -- cannot verify the sense IC body clears the high-current pour"
                    % type(e).__name__)
        return None, "derive_power_pours unavailable (%s)" % type(e).__name__
    if not pours:
        if has_pours:
            return (False, "FAIL-CLOSED: board has SENSEC pour zones but derive_power_pours found no "
                    "corridor -- cannot verify the sense IC body clears the high-current pour")
        return None, "no SENSEC high-current pour region (shared-bus / non-cable board)"
    box_by_net = collections.defaultdict(list)
    for pr in pours:
        xs = [p[0] for p in pr["polygon"]]; ys = [p[1] for p in pr["polygon"]]
        box_by_net[pr["net"]].append((min(xs), max(xs), min(ys), max(ys)))
    tol = _param("sense-body-clear-of-pour", "max_overlap_mm2", 2.0)
    fails, oks, payload = [], [], []
    for fp in board.GetFootprints():
        if not _is(fp, "INA2", "INA181"):
            continue
        nets = {(p.GetNetname() or "").upper() for p in fp.Pads()}
        boxes = [b for net, bx in box_by_net.items()
                 for b in bx if net.upper() in nets]            # pour boxes on THIS IC's force nets
        if not boxes:
            continue                                            # filtered-lane INA (no _HI/_LO pour) -> N/A
        cy = _fp_courtyard_bbox(fp)
        cx0, cy0 = (cy[0] + cy[1]) / 2.0, (cy[2] + cy[3]) / 2.0
        ov = sum(max(0.0, min(cy[1], b[1]) - max(cy[0], b[0]))
                 * max(0.0, min(cy[3], b[3]) - max(cy[2], b[2])) for b in boxes)
        in_pour = any(b[0] <= cx0 <= b[1] and b[2] <= cy0 <= b[3] for b in boxes)
        ref = fp.GetReference()
        if in_pour or ov > tol:
            why = "centroid in pour" if in_pour else "%.2fmm^2 > %.1f" % (ov, tol)
            fails.append("%s (%s)" % (ref, why))
            payload.append({"type": "separate", "a": ref, "from": "SENSEC-pour",
                            "overlap_mm2": round(ov, 2), "centroid_in_pour": in_pour})
        else:
            oks.append("%s %.2fmm^2" % (ref, ov))
    if not oks and not fails:
        return None, "no sense IC tapping a SENSEC pour net"
    if fails:
        return (False, "sense IC body sits in the SENSEC pour: " + "; ".join(fails[:6]), payload)
    return True, "all %d sense IC bodies clear of the SENSEC pour (<= %.1fmm^2 graze): %s" % (
        len(oks), tol, "; ".join(oks))


@checker("diffpair-gate")
def _chk_diffpair(board, path, ctx):
    m = cec_score.score(path)
    if not m.detail.get("diff_pairs"):
        return None, "no _P/_N diff pairs on this board"
    return m.diffpair_ok, "diffpair_ok=%s" % m.diffpair_ok


@checker("diffpair-pn-naming")
def _chk_pn_naming(board, path, ctx):
    nets = set(_nets(board))
    # USB present? look for any USB data net
    usb = [n for n in nets if "USB_D" in n.upper()]
    if not usb:
        return None, "no USB data nets"
    good = any(n.endswith("_P") or n.endswith("_N") for n in usb)
    bad = [n for n in usb if re.search(r"USB_D[PM]$", n.upper())]
    if bad and not good:
        return (False, "USB diff pair uses DP/DM not _P/_N (router can't auto-recognize): %s" % ", ".join(sorted(bad)),
                [{"type": "rename", "nets": sorted(bad), "to": "_P/_N suffix"}])
    return True, "USB diff pair uses _P/_N convention"


@checker("mount-holes-present-clear")
def _chk_mounts(board, path, ctx):
    want = _param("mount-holes-present-clear", "min_count", 3)
    clear = _param("mount-holes-present-clear", "clear_mm", 2.0)
    mounts = [fp for fp in board.GetFootprints() if _is(fp, "MountingHole", "MOUNT")]
    if len(mounts) < want:
        return (False, "found %d mounts, expect >= %d" % (len(mounts), want),
                [{"type": "add", "what": "mounting_hole", "need": want - len(mounts)}])
    conns = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("J") and list(fp.Pads())]
    near = [(mh.GetReference(), j.GetReference(), _min_pad_dist_mm(mh, j))
            for mh in mounts for j in conns if _min_pad_dist_mm(mh, j) < clear]
    if near:
        return (False, "mount too close to connector: " + "; ".join("%s~%s %.2f" % n for n in near[:4]),
                [{"type": "pin", "target": n[0], "hint": "move clear of %s" % n[1]} for n in near])
    return True, "%d mounts present, clear" % len(mounts)


@checker("fiducials-present")
def _chk_fid(board, path, ctx):
    want = _param("fiducials-present", "min_count", 3)
    fids = [fp for fp in board.GetFootprints() if _is(fp, "Fiducial", "FID")]
    if len(fids) < want:
        return False, "found %d fiducials, expect >= %d" % (len(fids), want)
    return True, "%d fiducials present" % len(fids)


@checker("fiducial-protocol")
def _chk_fid_protocol(board, path, ctx):
    want = _param("fiducial-protocol", "count", 3)
    edge_min = _param("fiducial-protocol", "edge_min_mm", 5.0)
    clear = _param("fiducial-protocol", "clear_mm", 3.0)
    tol = _param("fiducial-protocol", "sym_tol_mm", 1.0)
    fids = [fp for fp in board.GetFootprints()
            if fp.GetReference().upper().startswith("FID") and not fp.IsFlipped()]
    if not fids:
        return None, "no fiducials placed (presence is fiducials-present's gate)"
    fails = []
    if len(fids) != want:
        fails.append("count %d != %d (three corners, never four)" % (len(fids), want))
    L, T, R, B = _edge_bbox(board)
    cx, cy = (L + R) / 2.0, (T + B) / 2.0
    pts = [(_mm(fp.GetPosition().x), _mm(fp.GetPosition().y)) for fp in fids]
    # 180-degree vision ambiguity: the set maps onto itself under rotation about centre
    rot = [(2 * cx - x, 2 * cy - y) for (x, y) in pts]
    if all(any(math.hypot(rx - x, ry - y) <= tol for (x, y) in pts) for (rx, ry) in rot):
        fails.append("fiducial set is 180-degree symmetric about the board centre "
                     "(vision ambiguity) within %.1fmm" % tol)
    for fp, (x, y) in zip(fids, pts):
        m = min(x - L, R - x, y - T, B - y)
        if m < edge_min:
            fails.append("%s %.1fmm from an edge (< %.1f)" % (fp.GetReference(), m, edge_min))
        near = min((_min_pad_dist_mm(fp, o) for o in board.GetFootprints()
                    if o is not fp and list(o.Pads()) and not o.GetReference().upper().startswith("FID")),
                   default=1e9)
        if near < clear:
            fails.append("%s clear zone %.1fmm (< %.1f)" % (fp.GetReference(), near, clear))
    if fails:
        return False, "fiducial protocol (§K.4): " + "; ".join(fails[:6])
    return True, "%d fiducials, asymmetric, edge >= %.1fmm, clear >= %.1fmm" % (
        len(fids), edge_min, clear)


_MLCC_LANDS = ("_0402_1005", "_0603_1608", "_0805_2012")


@checker("mlcc-edge-orientation")
def _chk_mlcc_edge(board, path, ctx):
    band = _param("mlcc-edge-orientation", "edge_band_mm", 1.0)
    L, T, R, B = _edge_bbox(board)
    in_band, bad = [], []
    for fp in board.GetFootprints():
        if not fp.GetReference().upper().startswith("C"):
            continue
        if not any(s in fp.GetFPIDAsString() for s in _MLCC_LANDS):
            continue
        pads = list(fp.Pads())
        if len(pads) != 2:
            continue
        xs = [_mm(p.GetPosition().x) for p in pads]
        ys = [_mm(p.GetPosition().y) for p in pads]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        margins = {"L": x0 - L, "R": R - x1, "T": y0 - T, "B": B - y1}
        edge, m = min(margins.items(), key=lambda kv: kv[1])
        if m > band:
            continue
        if m < -2.0:
            continue        # parked off-board mid-layout -- courtyard/edge DRC's business, not K.1's
        in_band.append(fp.GetReference())
        axis_vertical = abs(y1 - y0) > abs(x1 - x0)
        edge_vertical = edge in ("L", "R")
        if axis_vertical != edge_vertical:
            bad.append("%s perpendicular to the %s edge at %.2fmm" % (fp.GetReference(), edge, m))
    if not in_band:
        return None, "no 2-pad MLCC within %.1fmm of a board edge" % band
    if bad:
        return False, "MLCC long axis must parallel a near edge (§K.1 flex-crack): " + "; ".join(bad[:6])
    return True, "%d MLCC(s) in the %.1fmm edge band, all parallel" % (len(in_band), band)


@checker("ecap-edge-distance")
def _chk_ecap_edge(board, path, ctx):
    edge_min = _param("ecap-edge-distance", "edge_min_mm", 5.0)
    min_uf = _param("ecap-edge-distance", "min_uf", 470.0)

    def _is_big_ecap(fp):
        if "CP_Elec" in fp.GetFPIDAsString():
            return True
        m = re.match(r"([\d.]+)\s*[uµ]F", _val(fp))
        return bool(m) and float(m.group(1)) >= min_uf

    caps = [fp for fp in board.GetFootprints()
            if fp.GetReference().upper().startswith("C") and _is_big_ecap(fp)]
    if not caps:
        return None, "no large SMD electrolytic on this board"
    L, T, R, B = _edge_bbox(board)
    bad = []
    for fp in caps:
        x, y = _mm(fp.GetPosition().x), _mm(fp.GetPosition().y)
        m = min(x - L, R - x, y - T, B - y)
        if m < edge_min:
            bad.append("%s (%s) %.1fmm from an edge (< %.1f)" % (
                fp.GetReference(), _val(fp), m, edge_min))
    if bad:
        return False, "large e-cap edge rule (§K.8): " + "; ".join(bad)
    return True, "%d large e-cap(s) all >= %.1fmm from every edge" % (len(caps), edge_min)


@checker("decoupler-adjacency-k5")
def _chk_decap_k5(board, path, ctx):
    target = _param("decoupler-adjacency-k5", "target_mm", 1.5)
    POWER = ("+3V3", "+5VSB", "VBUS", "VREF", "+3.3", "VDD", "VCC")
    by_net = _pads_by_net(board)
    ic_pad_by_net = collections.defaultdict(list)
    for n, lst in by_net.items():
        if any(p in n.upper() for p in POWER):
            for r, pad, fp in lst:
                if r.startswith("U"):
                    ic_pad_by_net[n].append((pad, r))
    if not ic_pad_by_net:
        return None, "no IC power pads resolved"
    worst, over = [], []
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if not r.startswith("C"):
            continue
        val = _val(fp).lower().replace("µ", "u")
        if not (("n" in val and "u" not in val) or "0.1u" in val):
            continue
        best, owner = 1e9, None
        for cpad in fp.Pads():
            for ipad, iref in ic_pad_by_net.get(cpad.GetNetname(), []):
                a, b = cpad.GetPosition(), ipad.GetPosition()
                dd = math.hypot(_mm(a.x - b.x), _mm(a.y - b.y))
                if dd < best:
                    best, owner = dd, iref
        if owner is None or best > 1e8:
            continue
        worst.append(best)
        if best > target:
            over.append((r, best, owner))
    if not worst:
        return None, "no decoupler-to-IC loop resolved"
    if over:
        over.sort(key=lambda t: -t[1])
        return (False, "K.5 audit: %d/%d decoupler(s) beyond the %.1fmm pad-to-pad target "
                "(as-built gate stays decoupling-cap-owner @3.5): %s"
                % (len(over), len(worst), target,
                   ", ".join("%s %.1fmm (%s)" % o for o in over[:8])))
    return True, "all %d decoupler loops within the %.1fmm K.5 target" % (len(worst), target)


@checker("rj45-link-pinmap")
def _chk_rj45(board, path, ctx):
    rj = [fp for fp in board.GetFootprints() if _is(fp, "RJ45")]
    if not rj:
        return None, "no RJ-45 on this board"
    want = {"1": ("5VSB", "VCC"), "2": ("GND",), "3": ("CAN_H", "CAN1_H"),
            "6": ("CAN_L", "CAN1_L"), "8": ("DETECT",)}
    fp = rj[0]
    padnet = {p.GetPadName(): (p.GetNetname() or "").upper() for p in fp.Pads()}
    wrong = []
    for pin, subs in want.items():
        net = padnet.get(pin, "")
        if net and not any(s in net for s in subs):
            wrong.append("pin%s=%s (want %s)" % (pin, net, "/".join(subs)))
    if wrong:
        return False, "RJ-45 pinmap mismatch: " + "; ".join(wrong)
    return True, "RJ-45 pin map matches the locked allocation"


@checker("detect-resistor-code")
def _chk_detect_r(board, path, ctx):
    by_net = _pads_by_net(board)
    det = [n for n in by_net if "DETECT" in n.upper() and "SENSE" not in n.upper()]
    if not det:
        return None, "no DETECT net"
    rs = {r for n in det for r, _, fp in by_net[n] if r.startswith("R")}
    if not rs:
        return None, "no resistor on DETECT (Hub-side pullup board?)"
    vals = {r: _val(fp) for fp in board.GetFootprints() for r in [fp.GetReference()] if r in rs}
    # HUB side (multiple RJ-45 ports => multiple DETECT nets): §2.3 specifies the FIXED
    # 10k pull-up to the 3.3V ADC reference, one per port -- the code resistor lives on
    # the MODULE. A module board (single DETECT net) carries the §2.3 code value.
    n_rj45 = sum(1 for fp in board.GetFootprints()
                 if "RJ45" in (str(fp.GetFPID().GetLibItemName()) + _val(fp)).upper())
    if n_rj45 >= 2 or len(det) >= 2:
        ok = all(re.search(r"^10\s*k", v, re.I) for v in vals.values())
        if not ok:
            return False, "Hub DETECT pull-up not 10k (spec §2.3): %s" % vals
        return True, "Hub: %d DETECT 10k pull-up(s) per §2.3" % len(vals)
    expect_k = _param("detect-resistor-code", "expect_k", 2.2)
    ok = any(re.search(r"2\.?2\s*k", v, re.I) or "2k2" in v.lower() for v in vals.values())
    if not ok:
        return False, "DETECT resistor not %.1fk (CAN-only): %s" % (expect_k, vals)
    return True, "DETECT code resistor = %.1fk (CAN-only)" % expect_k


@checker("detect-esd-diode-pin8")
def _chk_detect_esd(board, path, ctx):
    by_net = _pads_by_net(board)
    det = [n for n in by_net if "DETECT" in n.upper() and "SENSE" not in n.upper()]
    if not det:
        return None, "no DETECT net"
    ds = [(r, _val(fp)) for n in det for r, _, fp in by_net[n] if r.startswith("D")]
    if not ds:
        return False, "no ESD diode on DETECT pin-8", [{"type": "add", "what": "PESD5V0S1BA", "net": det[0]}]
    pesd = any("PESD" in v.upper() for _, v in ds)
    return (pesd, "DETECT ESD diode: %s%s" % (ds, "" if pesd else " (not a PESD part!)"))


@checker("can-transceiver-tja1051t3")
def _chk_can_xcvr(board, path, ctx):
    xcvr = [fp for fp in board.GetFootprints() if "TJA10" in (_val(fp)).upper()]
    if not xcvr:
        return None, "no CAN transceiver placed on this board"
    bad = [_val(fp) for fp in xcvr if "1051T/3" not in _val(fp) and "1051T3" not in _val(fp).replace("/", "")]
    if bad:
        return False, "transceiver not TJA1051T/3: %s" % bad
    return True, "CAN transceiver = TJA1051T/3"


@checker("shunt-values-per-table")
def _chk_shunt_val(board, path, ctx):
    rs = [(fp.GetReference(), _val(fp)) for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    if not rs:
        return None, "no RS* shunts on this board"
    # accept any explicit milliohm-style value; FAIL only obviously-wrong (no mOhm marker)
    bad = [r for r in rs if not re.search(r"(0?\.5|1|2|25)\s*m", r[1], re.I) and "R0" not in r[1].upper()]
    if bad:
        return False, "shunt value not a §6.4 mOhm value: %s" % bad
    return True, "shunt values look like §6.4 mOhm parts: %s" % rs


@checker("decoupling-cap-owner")
def _chk_decap(board, path, ctx):
    max_mm = _param("decoupling-cap-owner", "max_mm", 3.5)
    POWER = ("+3V3", "+5VSB", "VBUS", "VREF", "+3.3", "VDD", "VCC")
    by_net = _pads_by_net(board)
    ic_pad_by_net = collections.defaultdict(list)   # power net -> [(IC pad, IC ref)]  (real bypass loop)
    for n, lst in by_net.items():
        if any(p in n.upper() for p in POWER):
            for r, pad, fp in lst:
                if r.startswith("U"):
                    ic_pad_by_net[n].append((pad, r))
    if not ic_pad_by_net:
        return None, "no IC power pads resolved"
    fails = []
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if not r.startswith("C"):
            continue
        val = _val(fp).lower().replace("µ", "u")
        # only DECOUPLING caps (nF range / 0.1u) own an IC; bulk/hold-up caps (>=1uF) sit off-IC
        if not (("n" in val and "u" not in val) or "0.1u" in val):
            continue
        # measure the actual bypass loop: cap power pad -> the IC power pad on the SAME net (not IC centre)
        best, owner = 1e9, None
        for cpad in fp.Pads():
            cn = cpad.GetNetname()
            for ipad, iref in ic_pad_by_net.get(cn, []):
                a, b = cpad.GetPosition(), ipad.GetPosition()
                dd = math.hypot(_mm(a.x - b.x), _mm(a.y - b.y))
                if dd < best:
                    best, owner = dd, iref
        if best < 1e8 and best > max_mm and owner:
            fails.append((r, best, owner))
    if fails:
        return (False, "decoupling caps far from their IC power pad (>%.1fmm bypass loop): %s"
                % (max_mm, ", ".join("%s %.1fmm" % (f[0], f[1]) for f in fails[:8])),
                [{"type": "adjacent", "a": f[0], "b": f[2], "max_mm": max_mm} for f in fails[:8]])
    return True, "decoupling caps within %.1fmm of their IC power pad" % max_mm


@checker("ic-power-ground-connected")
def _chk_ic_power(board, path, ctx):
    if _track_count(board) == 0:
        return None, "floorplan (route-time connectivity check)"
    POWER = ("+3V3", "+5VSB", "+5V", "VBUS", "VCC", "VDD", "+3.3")
    bad = []                                                  # (ic_ref, net)
    for net, descs in _unconnected(path, ctx):
        nu = (net or "").upper()
        if not (nu == "GND" or any(p in nu for p in POWER)):
            continue
        for d in descs:
            m = re.search(r"of (U\w+)\b", d)                  # "Pad 6 [+3V3] of U10 on F.Cu"
            if m:
                bad.append((m.group(1), net))
    bad = sorted(set(bad))
    if bad:
        ics = sorted({r for r, _ in bad})
        more = "" if len(bad) <= 8 else " (+%d more)" % (len(bad) - 8)
        return (False, "IC power/ground STRANDED (unpowered/floating pin) [%d]: " % len(bad)
                + ", ".join("%s[%s]" % (r, n) for r, n in bad[:8]) + more,
                [{"type": "power_escape", "ic": r, "nets": sorted({n for rr, n in bad if rr == r})}
                 for r in ics])
    return True, "every IC power + GND pad is connected"


@checker("board-routing-complete")
def _chk_routed(board, path, ctx):
    if _track_count(board) == 0:
        return None, "floorplan (route-time)"
    unc = _unconnected(path, ctx)
    if not unc:
        return True, "0 unconnected ratlines (fully routed)"
    by_net = collections.Counter(n for n, _ in unc)
    top = ", ".join("%s x%d" % (k, v) for k, v in by_net.most_common(8))
    more = "" if len(by_net) <= 8 else " (+%d nets)" % (len(by_net) - 8)
    return False, "%d unconnected ratlines across %d nets (not fully routed): %s%s" % (len(unc), len(by_net), top, more)


@checker("trace-width-high-current")
def _chk_tw(board, path, ctx):
    if _track_count(board) == 0:
        return None, "floorplan (no tracks)"
    min_mm = _param("trace-width-high-current", "min_mm", 1.0)
    # exempt nets carried by a pour
    poured = set()
    for z in board.Zones():
        try:
            if z.GetFilledArea() / 1e12 > 5:
                poured.add(z.GetNetname())
        except Exception:
            pass
    thin = collections.defaultdict(float)
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_TRACE_T:
            continue
        n = t.GetNetname()
        if not ("12V" in n.upper() or n.endswith("_HI")) or n in poured:
            continue
        thin[n] = max(thin[n], _mm(t.GetWidth()))
    bad = sorted(n for n, w in thin.items() if w < min_mm)
    if bad:
        return (False, "high-current nets routed thinner than %.1fmm (and not poured): %s" % (min_mm, ", ".join(bad[:6])),
                [{"type": "keepout", "reserve": "pour_or_widen", "nets": bad}])
    return True, "no too-thin high-current trace"


@checker("hot-sensitive-separation")
def _chk_hotsep(board, path, ctx):
    sep = _param("hot-sensitive-separation", "sep_mm", 8.0)
    shunts = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    hot = [fp for fp in board.GetFootprints()
           if fp.GetReference().upper().startswith("RS")
           or (fp.GetReference().upper().startswith("J") and _is(fp, "Mini-Fit", "12V2x6", "12V-2x6", "Molex", "2191", "pigtail"))]

    def _board_temp_ntc(fp):
        # an NTC intentionally AT the shunt row (board-temp, e.g. TH1) is NOT a "sensitive" part
        return bool(shunts) and min(_min_pad_dist_mm(fp, s) for s in shunts) <= 6.0
    sens = [fp for fp in board.GetFootprints()
            if (fp.GetReference().upper().startswith("TH") or _is(fp, "REF3030", "REF3033", "Thermistor"))
            and not _board_temp_ntc(fp)]
    if not hot or not sens:
        return None, "no hot/sensitive pair to separate on this board"
    fails = []
    for h in hot:
        for s in sens:
            d = _min_pad_dist_mm(h, s)
            if d < sep:
                fails.append((s.GetReference(), h.GetReference(), d))
    if fails:
        return (False, "temp-sensitive part too close to a hot part (<%.0fmm): %s" % (sep, "; ".join("%s~%s %.1f" % f for f in fails[:5])),
                [{"type": "separate", "a": f[0], "b": f[1], "min_mm": sep} for f in fails[:5]])
    return True, "temp-sensitive parts >= %.0fmm from hot parts" % sep


@checker("ntc-board-temp-by-shunt")
def _chk_ntc(board, path, ctx):
    max_mm = _param("ntc-board-temp-by-shunt", "max_mm", 5.0)
    ntcs = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("TH") or _is(fp, "Thermistor", "NTC")]
    shunts = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    if not ntcs or not shunts:
        return None, "no NTC + shunt pair on this board"
    near = any(min(_min_pad_dist_mm(t, s) for s in shunts) <= max_mm for t in ntcs)
    if not near:
        d = min(min(_min_pad_dist_mm(t, s) for s in shunts) for t in ntcs)
        return False, "no board-temp NTC within %.0fmm of a shunt (nearest %.1fmm)" % (max_mm, d)
    return True, "a board-temp NTC sits within %.0fmm of a shunt" % max_mm


@checker("connector-overhang-bounded")
def _chk_overhang(board, path, ctx):
    l, t, r, b = _edge_bbox(board)
    off = []
    for fp in board.GetFootprints():
        if not (fp.GetReference().upper().startswith("J") and list(fp.Pads())):
            continue
        for pad in fp.Pads():
            name = (pad.GetPadName() or "").strip()
            # only ELECTRICAL contacts must stay on-board; shield/mounting-peg pads may overhang
            if not name or name.upper().startswith(("SH", "MP", "MH")):
                continue
            p = pad.GetPosition()
            x, y = _mm(p.x), _mm(p.y)
            if x < l - 0.05 or x > r + 0.05 or y < t - 0.05 or y > b + 0.05:
                off.append("%s pad %s" % (fp.GetReference(), name))
                break
    if off:
        return (False, "connector electrical pads off the board edge: " + "; ".join(off[:5]),
                [{"type": "region", "target": o.split()[0], "hint": "pull electrical pads on-board"} for o in off[:5]])
    return True, "all connector electrical pads on-board"


@checker("connector-mouth-faces-edge")
def _chk_mouth(board, path, ctx):
    edge_mm = _param("connector-mouth-faces-edge", "edge_mm", 6.0)
    l, t, r, b = _edge_bbox(board)
    interior = []
    cab = [fp for fp in board.GetFootprints()
           if fp.GetReference().upper().startswith("J") and _is(fp, "RJ45", "Mini-Fit", "12V2x6", "USB", "Molex", "JST")]
    if not cab:
        return None, "no edge connectors resolved"
    for fp in cab:
        # the nearest PAD reaching the edge (large connectors have an inboard centre but edge-reaching pads)
        nd = 1e9
        for pad in fp.Pads():
            p = pad.GetPosition()
            x, y = _mm(p.x), _mm(p.y)
            nd = min(nd, x - l, r - x, y - t, b - y)
        if nd > edge_mm:
            interior.append("%s(%.1f)" % (fp.GetReference(), nd))
    if interior:
        return (False, "connector(s) not reaching a board edge (mouth can't seat a cable): %s" % ", ".join(interior),
                [{"type": "pin", "target": ref.split("(")[0], "hint": "move to nearest edge, mouth outward"} for ref in interior])
    return True, "all edge connectors reach a board edge"


@checker("footprint-matches-datasheet")
def _chk_fp_ds(board, path, ctx):
    # reporter: which placed parts carry an MPN but have no datasheet-land verification record yet.
    db = ctx.get("datasheet_db", {})  # mpn -> verified land (future: kicad-happy datasheets skill)
    unverified = []
    for fp in board.GetFootprints():
        mpn = ""
        for k in ("MPN", "Manufacturer_Part_Number", "LCSC"):
            try:
                if fp.HasField(k):
                    mpn = fp.GetFieldText(k)
                    break
            except Exception:
                pass
        if not mpn:
            mpn = _val(fp)
        if mpn and mpn not in db and fp.GetReference()[0] in "UJDQ":
            unverified.append("%s(%s)" % (fp.GetReference(), mpn[:18]))
    if unverified:
        return None, "%d part(s) need datasheet-land verification (no DB record): %s" % (len(unverified), ", ".join(unverified[:8]))
    return True, "all placed MPNs have a datasheet-land record"


# ===========================================================================
#  CL-25 audit-derived check pack (closed-loop framework, 2026-06-10)
# ===========================================================================
# The three NEW classes (netclass-geometry, bom-lint, sch-pcb-sync) -- the other
# three map to pre-existing checkers (see CL25_CLASSES). Plus the INTAKE GATE:
# the loop refuses candidate generation for a board failing the schematic-side
# subset (a loop that routes a broken netlist all night produces perfectly
# routed WRONG boards).

def _project_file(board_path, ext):
    """Sibling project file (.kicad_pro / .kicad_sch) for a board: same stem first,
    else the single file of that ext in the dir, else None."""
    d = os.path.dirname(os.path.abspath(board_path))
    stem = os.path.basename(board_path)
    if stem.endswith(".kicad_pcb"):
        stem = stem[:-len(".kicad_pcb")]
    cand = os.path.join(d, stem + ext)
    if os.path.isfile(cand):
        return cand
    hits = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(ext)]
    return hits[0] if len(hits) == 1 else None


def _netclass_rules(board_path):
    """Parse the sibling .kicad_pro net_settings: returns (classes, resolve) where
    classes = {name: {track_width, via_diameter, via_drill}} and resolve(net) -> class
    name (explicit assignment first, then first matching wildcard pattern, else Default).
    None if no project file / no classes (self-gating)."""
    import fnmatch
    pro = _project_file(board_path, ".kicad_pro")
    if not pro:
        return None
    try:
        ns = json.load(open(pro)).get("net_settings", {})
    except Exception:
        return None
    classes = {}
    for c in ns.get("classes", []):
        classes[c.get("name", "")] = {k: c[k] for k in ("track_width", "via_diameter", "via_drill")
                                      if k in c}
    if not classes:
        return None
    assignments = ns.get("netclass_assignments") or {}
    patterns = [(p.get("netclass"), p.get("pattern")) for p in (ns.get("netclass_patterns") or [])
                if p.get("netclass") in classes and p.get("pattern")]

    def resolve(net):
        a = assignments.get(net)
        if a:
            name = a[0] if isinstance(a, list) else a
            if name in classes:
                return name
        for name, pat in patterns:
            if fnmatch.fnmatchcase(net, pat):
                return name
        return "Default"
    return classes, resolve


def _via_width_mm(t):
    """PCB_VIA width with the KiCad-10 layer-arg form (no-arg GetWidth() asserts on
    debug builds -- the documented runner blocker)."""
    try:
        return _mm(t.GetWidth(t.TopLayer()))
    except TypeError:
        return _mm(t.GetWidth())


@checker("netclass-geometry-conformance")
def _chk_netclass_geom(board, path, ctx):
    nc = _netclass_rules(path)
    if nc is None:
        return None, "no .kicad_pro netclasses found (project file absent or empty net_settings)"
    classes, resolve = nc
    if not any(t.Type() == pcbnew.PCB_TRACE_T or isinstance(t, pcbnew.PCB_VIA)
               for t in board.GetTracks()):
        return None, "unrouted floorplan (no tracks/vias to conform)"
    tol = _param("netclass-geometry-conformance", "tol_mm", 0.001)
    sense = _sense_nets(board)            # SHARED force+sense: track width checker-exempt
    bad = collections.defaultdict(lambda: collections.Counter())
    for t in board.GetTracks():
        net = t.GetNetname()
        if not net:
            continue
        cls = resolve(net)
        minima = classes.get(cls, {})
        if isinstance(t, pcbnew.PCB_VIA):
            d = minima.get("via_diameter")
            dr = minima.get("via_drill")
            if d and _via_width_mm(t) < d - tol:
                bad[(net, cls)]["via_dia"] += 1
            if dr and _mm(t.GetDrillValue()) < dr - tol:
                bad[(net, cls)]["via_drill"] += 1
        elif t.Type() == pcbnew.PCB_TRACE_T:
            w = minima.get("track_width")
            if net in sense:
                continue                  # deliberate ~0.25mm Kelvin stub on the force net
            if w and _mm(t.GetWidth()) < w - tol:
                bad[(net, cls)]["track"] += 1
    if bad:
        worst = sorted(bad.items(), key=lambda kv: -sum(kv[1].values()))
        det = "; ".join("%s[%s] %s" % (net, cls, ",".join("%s x%d" % (k, n) for k, n in cnt.items()))
                        for (net, cls), cnt in worst[:6])
        total = sum(sum(c.values()) for c in bad.values())
        # payload: per-(net,class,kind) counts -- the CL-11 fixture invariants assert these
        # NET-SCOPED (e.g. zero via hits on /SENSEP* post-fix while GND track hits remain).
        payload = [{"net": net, "class": cls, "kind": k, "count": n}
                   for (net, cls), cnt in bad.items() for k, n in cnt.items()]
        return False, "%d under-minima feature(s) on %d net(s): %s" % (total, len(bad), det), payload
    return True, "all tracks/vias meet their netclass minima (%d classes; sense-stub exemption on %d net(s))" % (
        len(classes), len(sense))


# bom-field-lint: assembly-irrelevant refs + the DOCUMENTED-open sourcing gaps.
_BOM_KNOWN_OPEN = ("RS", "J_IN", "J_OUT")     # OQ-11 shunts + consigned THT power headers
_BOM_PLACEHOLDER = re.compile(r"(^$|^~$|_Small$|\b(TODO|TBD|FIXME|PLACEHOLDER|APPROXIMATE)\b)", re.I)


@checker("bom-field-lint")
def _chk_bom_lint(board, path, ctx):
    placeholders, unsourced_known = [], []
    n_parts = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if _board_only_ref(ref):
            continue
        n_parts += 1
        val = _val(fp)
        if _BOM_PLACEHOLDER.search(val or ""):
            placeholders.append("%s(%s)" % (ref, (val or "<empty>")[:20]))
        elif ref.startswith(_BOM_KNOWN_OPEN):
            unsourced_known.append(ref)
    if n_parts == 0:
        return None, "no BOM-relevant footprints on the board"
    if placeholders:
        return False, "%d placeholder/empty value(s): %s" % (len(placeholders), ", ".join(placeholders[:8]))
    note = (" (known-open gaps noted, not failed: %s)" % ", ".join(unsourced_known[:6])
            if unsourced_known else "")
    return True, "no placeholder/empty BOM fields on %d part(s)%s" % (n_parts, note)


_SCH_REF_RE = re.compile(r'\(property\s+"Reference"\s+"([^"]+)"')
_BOARD_ONLY_RE = re.compile(r"^(M|H|MK|FID|TP)\w*\d|^(LOGO|TP_)")


def _board_only_ref(ref):
    """Refs that legitimately exist on only one side: mounts (M1/H1/MK1), fiducials,
    test points (GUI-added, never in the sch), logos, power/flag symbols."""
    return ref.startswith("#") or ref.startswith("REF*") or bool(_BOARD_ONLY_RE.match(ref))


def _strip_lib_symbols(text):
    """Drop the (lib_symbols ...) block by paren-span -- its symbol DEFINITIONS carry
    placeholder Reference properties (bare 'R'/'U'/'J_KVM'-style prefixes would otherwise
    be indistinguishable from instances by pattern alone)."""
    i = text.find("(lib_symbols")
    if i < 0:
        return text
    depth, j = 0, i
    while j < len(text):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return text[:i] + text[j + 1:]


def _sch_refs(sch_path):
    """Instance references from a .kicad_sch: regex over the text AFTER excising the
    lib_symbols definitions block; unannotated ('?'-suffixed), power/flag, and
    board-only refs dropped."""
    refs = set()
    try:
        text = _strip_lib_symbols(open(sch_path, encoding="utf-8", errors="replace").read())
    except OSError:
        return refs
    for r in _SCH_REF_RE.findall(text):
        if r.endswith("?") or _board_only_ref(r):
            continue
        refs.add(r)
    return refs


@checker("sch-pcb-sync")
def _chk_sch_pcb_sync(board, path, ctx):
    sch = ctx.get("sch") or _project_file(path, ".kicad_sch")
    if not sch:
        return None, "no sibling .kicad_sch found"
    sch_refs = _sch_refs(sch)
    if not sch_refs:
        return None, "schematic parsed to 0 instance refs (unexpected format)"
    pcb_refs = {fp.GetReference() for fp in board.GetFootprints()
                if not _board_only_ref(fp.GetReference())}
    sch_only = sorted(sch_refs - pcb_refs)
    pcb_only = sorted(pcb_refs - sch_refs)
    fresh = ""
    try:
        if os.path.getmtime(sch) > os.path.getmtime(path):
            fresh = "; sch is NEWER than pcb (Update-PCB-from-Schematic may be pending)"
    except OSError:
        pass
    if sch_only or pcb_only:
        parts = []
        if sch_only:
            parts.append("in sch NOT on pcb (stale board): %s" % ", ".join(sch_only[:10]))
        if pcb_only:
            parts.append("on pcb NOT in sch (orphans): %s" % ", ".join(pcb_only[:10]))
        return False, "; ".join(parts) + fresh
    return True, "ref sets in sync (%d refs)%s" % (len(pcb_refs), fresh)


# ---------------------------------------------------------------------------
# CL-25 intake gate
# ---------------------------------------------------------------------------
_BENIGN_ERC_TYPES = ("lib_symbol_mismatch", "unconnected_wire_endpoint")


def _erc_errors(sch_path):
    """Run a live ERC (kicad-cli) and return the count of severity-ERROR violations
    excluding the documented-benign types (the R-03 CI posture: errors gate, warnings
    are the documented noise). None = kicad-cli unavailable (degrade, R-05 posture)."""
    import shutil
    if not shutil.which("kicad-cli"):
        return None
    out = os.path.join(tempfile.gettempdir(), "cec_intake_erc_%d.json" % os.getpid())
    subprocess.run(["kicad-cli", "sch", "erc", "--format", "json", "-o", out, sch_path],
                   capture_output=True)
    try:
        j = json.load(open(out))
    except Exception:
        return None
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    n = 0
    sheets = j.get("sheets", []) or [j]
    for sh in sheets:
        for v in sh.get("violations", []):
            if v.get("severity") == "error" and v.get("type") not in _BENIGN_ERC_TYPES:
                n += 1
    return n


def intake_gate(board_path, ctx=None):
    """CL-25 intake gate: the SCHEMATIC-SIDE subset (sync, ERC freshness, BOM lint,
    netlist assertions). Returns {"ok", "reasons", "results"}; the route loop refuses
    candidate generation on ok=False (override: CEC_SKIP_INTAKE=1). Named reasons only --
    a refusal the owner can act on, never a bare False."""
    ctx = ctx or {}
    board = pcbnew.LoadBoard(board_path)
    by_id = {c.id: c for c in REGISTRY}
    results, reasons = {}, []
    for cid in INTAKE_CHECKS:
        fn = CHECKERS.get(cid)
        c = by_id.get(cid)
        if not fn or not c:
            continue
        try:
            res = fn(board, board_path, ctx)
            ok, detail = res[0], res[1]
        except Exception as e:
            ok, detail = None, "%s: %s" % (type(e).__name__, e)
        status = "N/A" if ok is None else ("PASS" if ok else "FAIL")
        results[cid] = (status, detail)
        if ok is False:
            reasons.append("%s [%s]: %s" % (cid, c.severity, detail))
    # ERC freshness (live; degrades when kicad-cli is absent -- R-05 posture).
    # DRAFT boards skip ERC by repo convention (the cec_synth_pipeline is_draft rule).
    sch = ctx.get("sch") or _project_file(board_path, ".kicad_sch")
    if os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(board_path)), "DRAFT")):
        results["erc"] = ("N/A", "DRAFT board: ERC skipped by repo convention")
    elif sch:
        n = _erc_errors(sch)
        if n is None:
            results["erc"] = ("N/A", "kicad-cli unavailable (degraded; not a refusal)")
        elif n > 0:
            results["erc"] = ("FAIL", "%d ERROR-severity ERC violation(s)" % n)
            reasons.append("erc [hard]: %d ERROR-severity violation(s) on %s"
                           % (n, os.path.basename(sch)))
        else:
            results["erc"] = ("PASS", "0 ERROR-severity violations")
    else:
        results["erc"] = ("N/A", "no sibling .kicad_sch")
    # CL-03 R4: the ADVISORY set is REPORTED here, never gated on -- the intake
    # refusal logic above sees gate-class checks only. Informational summary of
    # the compiled advisory artifacts applicable to this board (empty when the
    # corpus compiler has not run -- degrade, never refuse).
    advisory = {"n": 0, "entries": []}
    try:
        import cec_corpus_compile
        bname = os.path.basename(os.path.dirname(os.path.abspath(board_path)))
        arts = cec_corpus_compile.load_board_artifacts(bname)
        rows = [r for rows in arts.values() for r in rows
                if isinstance(r, dict) and r.get("binding") == "advisory"]
        advisory = {"n": len(rows),
                    "entries": sorted({r.get("entry_id") for r in rows})[:20]}
    except Exception:                                         # noqa: BLE001
        pass
    return {"ok": not reasons, "reasons": reasons, "results": results,
            "advisory": advisory, "board": os.path.basename(board_path)}


# ===========================================================================
#  min-pour-cross-section ENFORCE LEG: field solve -> ratified DRC rule
# ===========================================================================
# discover -> ratify -> enforce, completing the min-pour-cross-section migration.
#   * DISCOVER: cec_dcir's field solve finds each high-current net's bottleneck cross-section.
#   * the deterministic ENFORCEMENT splits by net topology (a platform fact, empirically verified):
#       - SHARED force+sense net (an INA sense input lives ON it -> thin ~0.25mm Kelvin stubs): a
#         geometric DRC width rule (track_width OR connection_width) FALSE-FLAGS those stubs
#         (verified 2026-06-07: connection_width min 2.86mm fired on the 0.2-0.3mm sense taps). The
#         cec_dcir CHECKER is the correct enforcement -- it injects current only connector<->shunt, so
#         a zero-current sense branch is never scored as a 'neck'. EVERY current CEC high-current net
#         is this kind (the INA senses across the shunt = on the force net), so today this is the
#         universal path: enforcement = the min-pour-cross-section checker, ratified per board.
#       - FORCE-ONLY net (no sense tap on it -- e.g. a future plane tapped by a Hall sensor): safe to
#         enforce in the DRC. derive_cross_section_dru() emits a KiCad `connection_width` rule (min =
#         the physics-required width) that flows through cec_router.spec_to_dru / a .kicad_dru into the
#         DRC. (connection_width is the right primitive: it measures copper width INCLUDING zone fills,
#         so it catches a thin POUR neck, which track_width cannot.)
#   * RATIFY is the HUMAN's act (CLAUDE.md board-specific human-ratification boundary): ratify_cross_
#     section(write=True) appends the force-only rules to a board's committed .kicad_dru. Promoting the
#     checker itself from advisory->gating is the human's separate bench-validated call (the solver's
#     dt_ipc/shunt_rth are not yet bench-calibrated; per cec_dcir, "calibration, not a hard re-gate").
CU_OZ_MM = 0.0348   # copper thickness per oz, mm (= cec_dcir.CU_OZ_M / cec_synth_pipeline.CU_OZ_MM)


def _net_cu_thickness_mm(layers, oz_outer, oz_inner):
    """Total copper thickness (mm) a net's copper occupies, summed over the layers it is on
    (F.Cu/B.Cu = oz_outer, inner = oz_inner). The required min width = required_cross / this."""
    t = sum((oz_outer if ln in ("F.Cu", "B.Cu") else oz_inner) * CU_OZ_MM for ln in layers)
    return t or (oz_outer * CU_OZ_MM)


def derive_cross_section_dru(board_path, *, j_max=None, oz_outer=2.0, oz_inner=1.0):
    """ENFORCE-LEG derive (writes nothing). Run the cec_dcir DC field solve and, per high-current net
    over the j_max current-density limit, decide HOW to enforce its cross-section:
      FORCE-ONLY  -> a KiCad connection_width DRU rule (min = physics-required width) for spec_to_dru.
      SHARED f+s  -> CHECKER-enforced (a DRC width rule would false-flag the Kelvin sense tap).
    Returns {"rules":[(name,constraint,condition)...], "checker_enforced":[net...], "notes":[str...],
             "j_max":float}. Fallback-safe -> {"rules":[],...,"error":..} if numpy/cec_dcir absent."""
    if j_max is None:
        j_max = _param("min-pour-cross-section", "j_max_A_mm2", 100.0)
    try:
        import cec_dcir
        res = cec_dcir.solve(board_path, oz_outer=oz_outer, oz_inner=oz_inner)
    except Exception as e:
        return {"rules": [], "checker_enforced": [], "notes": [], "j_max": j_max, "error": repr(e)}
    board = pcbnew.LoadBoard(board_path)
    sense = _sense_nets(board)            # nets present at an INA sense input pin (the Kelvin taps)
    rules, checker, notes = [], [], []
    for net, r in sorted((res or {}).items()):
        if not r or r["j_p995_A_mm2"] <= j_max:
            continue
        need_cross = r["I"] / j_max
        need_w = round(need_cross / _net_cu_thickness_mm(r["layers"], oz_outer, oz_inner), 3)
        if net in sense:
            checker.append(net)
            notes.append("%s SHARED force+sense -> CHECKER-enforced (need cross %.3f mm^2; a DRC width "
                         "rule would false-flag the ~0.25mm Kelvin tap on this net)" % (net, need_cross))
        else:
            rules.append(("HC cross-section %s" % net.replace("/", "").replace(" ", "_"),
                          "connection_width (min %.3fmm)" % need_w,
                          "A.NetName == '%s'" % net))
            notes.append("%s FORCE-ONLY -> connection_width min %.3fmm (need cross %.3f mm^2 over %s)"
                         % (net, need_w, need_cross, "+".join(r["layers"])))
    return {"rules": rules, "checker_enforced": checker, "notes": notes, "j_max": j_max}


def ratify_cross_section(board_path, *, write=False, j_max=None, oz_outer=2.0, oz_inner=1.0):
    """ENFORCE-LEG ratify+enforce (the HUMAN's board-specific act). Derive the rules and, if write=True,
    APPEND the force-only connection_width rules to the board's committed .kicad_dru -- text-append that
    PRESERVES the existing hand rules (spec_to_dru would rewrite the whole file, dropping them). Idempotent:
    a rule already present by name is skipped. Returns the derivation + the .kicad_dru path + n written."""
    d = derive_cross_section_dru(board_path, j_max=j_max, oz_outer=oz_outer, oz_inner=oz_inner)
    dru = (board_path[:-len(".kicad_pcb")] if board_path.endswith(".kicad_pcb") else board_path) + ".kicad_dru"
    written = 0
    if write and d["rules"]:
        existing = open(dru).read() if os.path.exists(dru) else "(version 1)\n"
        blocks = ["", "# ENFORCE-LEG (ratify_cross_section): physics-required cross-section on a force-only",
                  "# high-current net, from the cec_dcir DC field solve (j_max=%g A/mm^2)." % d["j_max"]]
        for name, constraint, cond in d["rules"]:
            if ('"%s"' % name) in existing:
                continue
            blocks.append('(rule "%s"\n\t(constraint %s)\n\t(condition "%s"))' % (name, constraint, cond))
            written += 1
        if written:
            open(dru, "w").write(existing.rstrip() + "\n" + "\n".join(blocks) + "\n")
    return {**d, "dru": dru, "written": written}


# ===========================================================================
#  directive consumer
# ===========================================================================
def directives(rows):
    """Turn FAIL rows into typed placement directives an auto-placer consumes."""
    out = []
    for c, status, detail, payload in rows:
        if status != "FAIL":
            continue
        if payload:
            for p in payload:
                out.append({"constraint": c.id, "severity": c.severity, "directive": p.get("type", c.directive), **p})
        else:
            out.append({"constraint": c.id, "severity": c.severity, "directive": c.directive, "detail": detail[:120]})
    return out


# ===========================================================================
#  run / report
# ===========================================================================
STATUS_ORDER = {"FAIL": 0, "PASS": 1, "DECLARED": 2, "N/A": 3, "ERROR": 4}


def run(board_path, ctx=None):
    ctx = ctx or {}
    board = pcbnew.LoadBoard(board_path)
    out = []
    for c in REGISTRY:
        if c.superseded_by:
            # CL-03 R2: tombstoned row -- authority moved to the promoted corpus
            # entry; excluded from blocking (reported, never FAIL).
            out.append((c, "TOMBSTONE", "superseded by corpus entry %s" % c.superseded_by, None))
            continue
        fn = CHECKERS.get(c.checker or c.id)
        if not fn:
            out.append((c, "DECLARED", "recorded; deterministic checker pending", None))
            continue
        try:
            res = fn(board, board_path, ctx)
            ok, detail = res[0], res[1]
            payload = res[2] if len(res) > 2 else None
            status = "N/A" if ok is None else ("PASS" if ok else "FAIL")
            out.append((c, status, detail, payload))
        except Exception as e:
            out.append((c, "ERROR", "%s: %s" % (type(e).__name__, e), None))
    return out


def report(board_path, ctx, as_json=False):
    rows = run(board_path, ctx)
    if as_json:
        return {"board": os.path.basename(board_path),
                "verdicts": [{"id": c.id, "severity": c.severity, "status": s, "detail": d} for c, s, d, _ in rows],
                "directives": directives(rows)}
    print("=" * 96)
    print("CONSTRAINT REPORT :: %s   (radio=%s)" % (os.path.basename(board_path), ctx.get("radio", False)))
    print("=" * 96)
    rows_s = sorted(rows, key=lambda r: (STATUS_ORDER.get(r[1], 9), r[0].category))
    icon = {"FAIL": "[X]", "PASS": "[v]", "DECLARED": "[.]", "N/A": "[-]", "ERROR": "[!]"}
    for c, status, detail, _ in rows_s:
        print("%s %-9s %-30s %s" % (icon.get(status, "[?]"), status, c.id, str(detail)[:110]))
    n = collections.Counter(r[1] for r in rows)
    print("-" * 96)
    print("  FAIL=%d PASS=%d N/A=%d DECLARED=%d ERROR=%d  (%d canonical; corpus 269)"
          % (n["FAIL"], n["PASS"], n["N/A"], n["DECLARED"], n["ERROR"], len(REGISTRY)))
    ds = directives(rows)
    if ds:
        print("  DIRECTIVES (%d) for the placer:" % len(ds))
        for d in ds[:12]:
            print("    -> %s" % json.dumps(d))
    return rows


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    ctx = {"radio": "--radio" in argv}
    as_json = "--json" in argv
    boards = [a for a in argv if not a.startswith("--")]

    # CL-25 INTAKE GATE CLI: the schematic-side refuse-candidates subset.
    if "--intake" in argv:
        rc = 0
        blobs = []
        for b in boards:
            g = intake_gate(b, ctx)
            if as_json:
                blobs.append(g)
            else:
                print("INTAKE :: %s -> %s" % (g["board"], "ADMIT" if g["ok"] else "REFUSE"))
                for cid, (status, detail) in g["results"].items():
                    print("  [%s] %-32s %s" % (status[0], cid, str(detail)[:100]))
            rc = rc or (0 if g["ok"] else 1)
        if as_json:
            print(json.dumps(blobs, indent=1))
        return rc

    # ENFORCE-LEG CLI: derive (or --write to ratify) the min-pour-cross-section DRC rules.
    if "--enforce-cross-section" in argv:
        write = "--write" in argv
        blobs = []
        for b in boards:
            d = ratify_cross_section(b, write=write)
            if as_json:
                blobs.append({"board": os.path.basename(b), **d})
                continue
            print("ENFORCE-LEG :: %s  (j_max=%g A/mm^2)" % (os.path.basename(b), d["j_max"]))
            for n in d["notes"]:
                print("  " + n)
            print("  DRC rules (force-only, -> spec_to_dru/.kicad_dru): %d%s" % (
                len(d["rules"]), ("  WROTE %d to %s" % (d["written"], os.path.relpath(d["dru"], ROOT)))
                if write else "  (dry run; --write to ratify)"))
            print("  checker-enforced (shared force+sense / Kelvin): %d net(s)%s" % (
                len(d["checker_enforced"]),
                "" if d["rules"] else "  [-> the min-pour-cross-section checker is the enforcement]"))
            print()
        if as_json:
            print(json.dumps(blobs, indent=1, default=str))
        return 0

    blobs = []
    for b in boards:
        if as_json:
            blobs.append(report(b, ctx, as_json=True))
        else:
            report(b, ctx)
            print()
    if as_json:
        print(json.dumps(blobs, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())


def laid_pour_incursion_summary(board_path, *, exclude_plane=True):
    """Anything sitting inside a pour's OWN reserved region: parts, tracks, vias.

    Owner ruling 2026-07-25: "prevent anything from ever placing inside a pour --
    the pour is set first and should never be incurred upon."

    Why this exists alongside no-foreign-on-high-current-pour: that rule measures a
    RE-DERIVED corridor box, so it reports 0 while the pour that was actually laid
    is being encroached. Measured on the eps winner -- `foreign=0t` in the verdict,
    and against the laid pours: 4 foreign pads (C1, C20), 7 tracks, 4 vias. This
    check reads the zones ON THE BOARD, which is the only geometry the rule can
    honestly be about.

    Measured against the zone OUTLINE, not its fill: the filler voids around every
    obstacle, so "nothing inside the fill" is true by construction and says nothing
    about whether the region was respected.

    Own-net items are never incursions -- a pour must reach its own pads. The GND
    plane is skipped by default (it is the board-wide reference, not a reserved
    corridor).

    Returns {"applicable", "status", "n_parts", "n_tracks", "n_vias", "items"}.
    """
    try:
        from shapely.geometry import Polygon, box as _box, LineString
        from shapely.ops import unary_union
    except ImportError:
        return {"applicable": False, "status": "na", "reason": "shapely absent",
                "n_parts": 0, "n_tracks": 0, "n_vias": 0, "items": []}
    board = pcbnew.LoadBoard(board_path) if isinstance(board_path, str) else board_path
    zones = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        net = z.GetNetname() or ""
        name = z.GetZoneName() or ""
        if exclude_plane and (net == "GND" or name.startswith("GND Plane")):
            continue
        for lid in board.GetEnabledLayers().CuStack():
            if not z.IsOnLayer(lid):
                continue
            o = z.Outline()
            ps = []
            for i in range(o.OutlineCount()):
                oo = o.Outline(i)
                pts = [(oo.CPoint(k).x / 1e6, oo.CPoint(k).y / 1e6)
                       for k in range(oo.PointCount())]
                if len(pts) >= 3:
                    ps.append(Polygon(pts).buffer(0))
            if ps:
                zones.append((net, lid, name, unary_union(ps)))
    if not zones:
        return {"applicable": False, "status": "na", "n_parts": 0, "n_tracks": 0,
                "n_vias": 0, "items": []}
    items, n_parts, n_tracks, n_vias = [], 0, 0, 0
    for net, lid, name, g in zones:
        for fp in board.GetFootprints():
            for pd in fp.Pads():
                if not pd.IsOnLayer(lid) or pd.GetNetname() == net:
                    continue
                pb = pd.GetBoundingBox()
                r = _box(pb.GetLeft() / 1e6, pb.GetTop() / 1e6,
                         pb.GetRight() / 1e6, pb.GetBottom() / 1e6)
                if g.intersects(r) and g.intersection(r).area > 0.001:
                    n_parts += 1
                    items.append({"kind": "pad", "pour": name,
                                  "ref": fp.GetReference(), "net": pd.GetNetname()})
        for t in board.GetTracks():
            if t.GetNetname() == net:
                continue
            if t.GetClass() == "PCB_TRACK" and t.GetLayer() == lid:
                s_, e_ = t.GetStart(), t.GetEnd()
                ln = LineString([(s_.x / 1e6, s_.y / 1e6), (e_.x / 1e6, e_.y / 1e6)])
                if g.intersects(ln):
                    n_tracks += 1
                    items.append({"kind": "track", "pour": name, "net": t.GetNetname()})
            elif t.GetClass() == "PCB_VIA" and t.IsOnLayer(lid):
                p = t.GetPosition()
                r = _box(p.x / 1e6 - 0.45, p.y / 1e6 - 0.45,
                         p.x / 1e6 + 0.45, p.y / 1e6 + 0.45)
                if g.intersects(r):
                    n_vias += 1
                    items.append({"kind": "via", "pour": name, "net": t.GetNetname()})
    return {"applicable": True, "status": "ok", "n_parts": n_parts,
            "n_tracks": n_tracks, "n_vias": n_vias, "items": items[:60]}


@checker("no-incursion-in-laid-pour")
def _chk_laid_pour_incursion(board, path, ctx):
    """Owner ruling 2026-07-25: nothing is ever placed inside a pour. The pour is
    set first; a placement that cannot work without encroaching sends the POURS
    back to be redone, never the rule bent. See laid_pour_incursion_summary."""
    rep = laid_pour_incursion_summary(path)
    if not rep.get("applicable"):
        return []
    out = []
    for it in rep["items"]:
        out.append("%s %s [%s] inside pour %s"
                   % (it["kind"], it.get("ref", ""), it.get("net", ""), it["pour"]))
    return out
