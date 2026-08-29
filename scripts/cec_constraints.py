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
import cec_fab_profile as cec_fab  # noqa: E402 -- declared stackup/POFV authority
import cec_mezz_contract as cec_mezz  # noqa: E402 -- shared segmented mating contract
import cec_board_geometry  # noqa: E402 -- Edge.Cuts centerline dimensional authority
import cec_toolchain  # noqa: E402 -- cross-platform KiCad executable resolution
import cec_sch_gates  # noqa: E402 -- hierarchy-aware assembly inventory
import cec_spice_sanity  # noqa: E402 -- KiCad netlist parser used for exact freshness
import cec_impedance  # noqa: E402 -- profile-aware coupled-pair geometry
import cec_device_bypass  # noqa: E402 -- shared device/cap rules with placer


# Board geometry is serialized on an integer-nanometre grid, while placement
# transforms and Euclidean reconstruction can accumulate sub-micron residuals.
# Normalize inclusive millimetre rules at one micrometre, far below assembly
# accuracy and three orders of magnitude below the smallest local-cell rule.
# This is not design-rule margin: a candidate more than 1 um outside the stated
# limit remains outside it.
GEOMETRY_COMPARISON_TOLERANCE_MM = 1e-3


def _within_physical_distance_limit(distance_mm, limit_mm):
    """Return whether a measured distance satisfies an inclusive mm limit."""
    return (float(distance_mm)
            <= float(limit_mm) + GEOMETRY_COMPARISON_TOLERANCE_MM)


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
    C(id="high-current-stackup-2oz", title="Approved 6-layer high-current stackup",
      category="high-current", severity="hard", checkable="yes", directive="none",
      rule="High-current modules use JLC06162H-3313: six layers, 70um outer and "
           "15.2um inner copper, with In1/In4 ground and In3 power routing.",
      source="owner approval 2026-08-01; JLCPCB JLC06162H-3313 selector",
      status="ratified"),
    C(id="hub-stackup-6layer", title="Approved 6-layer Hub stackup",
      category="high-current", severity="hard", checkable="yes", directive="none",
      rule="Hub boards use JLC06161H-3313: six layers, 35um outer and "
           "15.2um inner copper, with In1/In4 ground, In2 signal, and In3 power routing.",
      source="owner approval 2026-08-01; JLCPCB JLC06161H-3313 selector",
      status="ratified"),
    C(id="through-vias-only", title="Approved profiles use through vias only",
      category="high-current", severity="hard", checkable="yes", directive="none",
      rule="Boards using the approved JLCPCB six-layer profiles may use ordinary plated "
           "through vias, including qualified POFV. Blind, buried, and microvias are not emitted.",
      source="JLCPCB PCB capabilities table, verified 2026-08-01",
      status="ratified"),
    C(id="mezzanine-segment-contract",
      title="Hub and 24-pin segmented mezzanine fields mate exactly",
      category="mechanical", severity="hard", checkable="yes", directive="pin",
      rule="J6P/J6C/J6D use the ratified 2.54mm segmented pin maps and shared-frame "
           "coordinates. H1 is the coincident plated M2 GND lug on both boards.",
      source="owner ruling 2026-08-01; structural segmented mezzanine contract",
      status="ratified"),
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
    C(id="no-incursion-in-laid-pour",
      title="Actual laid pour outline is reserved from foreign copper and pads",
      category="high-current", severity="hard", checkable="yes", directive="keepout",
      rule="On a routing layer, no foreign pad, track copper, or via copper may overlap the "
           "outline of a laid non-plane pour. Dedicated GND and PWR plane-role layers are excluded.",
      source="owner ruling 2026-07-25; repaired and gated 2026-08-01",
      status="ratified"),
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
      status="proposed", params={"j_max_A_mm2": 100.0, "grid_mm": 0.4}),
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
    C(id="high-speed-pair-physical-integrity",
      title="High-speed/coupled pairs preserve geometry and return path",
      category="EMC/RF", severity="hard", checkable="yes", directive="none",
      rule="USB and CAN pairs use symmetric signal layers and vias (at most two per leg), "
           "meet the project skew/coupling limits, remain above a filled adjacent GND plane, "
           "and place a GND return via within 1.5mm of every signal-pair transition.",
      source="TI SLLU149E/SLLA653 routing guidance; owner pipeline audit 2026-08-02",
      status="ratified"),
    C(id="aggressor-victim-field-coupling",
      title="Fast/noisy routes do not couple into sensitive routes",
      category="EMC/RF", severity="hard", checkable="yes", directive="separate",
      rule="A recognized switch/clock/fast-bus aggressor may not run closely parallel to an "
           "analog sense/reference/thermal or other fast-bus victim. Different routing layers "
           "are shielded only when actual filled GND copper continuously covers the interaction "
           "on a dedicated intermediate plane; an unshielded layer crossing must be at least "
           "75 degrees (nominally 90 degrees). Same-layer copper crossings remain ordinary DRC "
           "failures and are never waived by this rule.",
      source="owner directive 2026-08-12; IPC-2221/industry 3W and orthogonal-layer practice",
      status="ratified"),
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
      rule="Each audited powered device receives a distinct, value-qualified bypass capacitor on "
           "its own supply net. The assignment is one-to-one and uses pad-to-pad distance, so one "
           "capacitor cannot satisfy multiple ICs. The 3.5mm limit is a ratified CEC placement "
           "limit, not a universal datasheet number; device-specific numeric limits override it.",
      source="CEC project placement limit; device capacitor requirements from selected-part datasheets",
      status="ratified", params={"max_mm": 3.5}),
    C(id="buck-switch-cell-placement", title="TLV62569 switching cell is compact",
      category="placement", severity="hard", checkable="yes", directive="adjacent",
      rule="For each fitted TLV62569, the SW pad-to-inductor connection is <=3.0mm and the "
           "inductor output-to-output-capacitor connection is <=3.5mm. The output capacitor "
           "must return directly to GND. This bounds the high-di/dt switch cell before routing.",
      source="TI TLV62569 datasheet application/layout guidance; selected 2.2uH/10uF network",
      status="ratified", params={"sw_to_l_mm": 3.0, "l_to_cout_mm": 3.5}),
    C(id="trace-width-high-current", title="No too-thin trace on a high-current net",
      category="placement", severity="strong", checkable="yes", directive="none",
      rule="Every >=1A current-model track segment meets the profile-aware IPC-2221 width "
           "at 30C rise and 125% current, unless that exact segment is embedded in its own "
           "filled zone. Kelvin sense stubs are owned by the dedicated Kelvin gates.",
      source="owner trace-width audit 2026-08-02; project current model; IPC-2221 conservative model",
      status="ratified"),
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
    C(id="via-on-pad", title="Via-on-pad is shorted or explicitly POFV-qualified",
      category="finishing", severity="hard", checkable="yes", directive="none",
      rule="A via whose copper (drill + annular ring) overlaps a PAD's copper on a shared copper layer "
           "is a fault KiCad DRC does NOT flag by default. SAME-net overlap is permitted only when the board "
           "declares an approved POFV fabrication profile, the via is through-board, its dimensions are in "
           "the vendor window, and the complete via land is contained by the SMD pad. Otherwise the barrel "
           "can wick solder and remains a failure. "
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
                                 "edge_band_max_mm": 8.0,
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
      rule="Historical K.5 proximity audit retained for report compatibility. The former universal "
           "1.5mm target is retired because the cited material supports minimizing loop inductance "
           "but does not establish that number for every selected device and package.",
      source="2026-08-02 guideline audit; numeric acceptance moved to selected-part datasheets and "
             "the explicit CEC project limit",
      status="proposed"),

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


_COMPILED_CONSTRAINT_IR = None


def compiled_constraint_ir():
    """Return the canonical typed registry or raise on an invalid authority.

    Compilation is lazy because this module is also imported by small geometry
    tools. Release and intake entry points call it explicitly and fail closed;
    a malformed severity, directive, provenance source, or duplicate id can no
    longer drift through one checker while another stage interprets it.
    """
    global _COMPILED_CONSTRAINT_IR
    if _COMPILED_CONSTRAINT_IR is None:
        import cec_constraint_ir
        _COMPILED_CONSTRAINT_IR = cec_constraint_ir.compile_registry(REGISTRY)
    return _COMPILED_CONSTRAINT_IR

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

# Geometry defects on an explicitly admitted derived/routed input belong to
# the route repair stage, not source admission.  Keep this allow-list narrow:
# schematic/netlist/BOM/authority failures remain hard intake blockers, and
# every deferred checker is run again by the normal route/release gates.
ROUTE_REPAIRABLE_INTAKE_CHECKS = frozenset({
    "no-foreign-on-high-current-pour",
})


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
    return cec_board_geometry.outline_bbox_mm(board)


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
        with open(os.path.join(cec_facts.COMPILED_ROOT, "params.json"), encoding="utf-8") as source:
            rows = _json.load(source)
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
    cli = cec_toolchain.kicad_cli()
    if not cli:
        raise RuntimeError("kicad-cli unavailable")
    fd, out = tempfile.mkstemp(prefix="cec_cons_drc_", suffix=".json")
    os.close(fd)
    try:
        proc = subprocess.run([cli, "pcb", "drc", "--format", "json",
                               "-o", out, path], capture_output=True, text=True,
                              timeout=300)
        if proc.returncode:
            raise RuntimeError("kicad-cli DRC exited %d: %s"
                               % (proc.returncode, (proc.stderr or proc.stdout).strip()[:500]))
        with open(out, encoding="utf-8") as f:
            j = json.load(f)
        if (not isinstance(j, dict)
                or not isinstance(j.get("violations"), list)
                or not isinstance(j.get("unconnected_items"), list)):
            raise ValueError("kicad-cli DRC JSON lacks violations/unconnected_items lists")
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
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
    on a box without numpy. The board's fabrication profile supplies exact copper and dielectric
    thicknesses; only the grid pitch comes from the constraint entry."""
    key = "_dcir::" + path
    if key in ctx:
        return ctx[key]
    res = None
    try:
        import cec_dcir
        res = cec_dcir.solve(
            path,
            h=_param("min-pour-cross-section", "grid_mm", 0.4),
        )
    except Exception:
        res = None
    ctx[key] = res
    return res


# -- fabrication profile / stackup -------------------------------------------
def _balanced_sexp(text, marker):
    """Return the balanced s-expression beginning at *marker*, or empty."""
    start = text.find(marker)
    if start < 0:
        return ""
    depth = 0
    quoted = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def _fab_profile_errors(board, path, expected):
    profile = cec_fab.get_profile(expected)
    errors = []
    declared = cec_fab.board_profile_name(board)
    if declared != expected:
        errors.append("CEC_FAB_PROFILE=%r, expected %r" % (declared, expected))
    try:
        props = {str(k): str(v) for k, v in
                 board.GetProperties().asdict().items()}
    except Exception:                                  # noqa: BLE001
        props = {}
    required_props = cec_fab.board_properties(expected)
    for key, want in required_props.items():
        if props.get(key) != want:
            errors.append("%s=%r, expected %r" % (key, props.get(key), want))

    enabled = cec_fab.enabled_copper_layers(board)
    if enabled != cec_fab.COPPER_LAYERS:
        errors.append("enabled copper layers %s, expected %s" %
                      (enabled, cec_fab.COPPER_LAYERS))
    role_map = dict(zip(cec_fab.COPPER_LAYERS, profile["roles"]))
    for layer in cec_fab.COPPER_LAYERS:
        lid = board.GetLayerID(layer)
        if lid < 0:
            continue
        want_power_kind = role_map[layer] == "GND"
        is_power_kind = int(board.GetLayerType(lid)) == 1
        if want_power_kind != is_power_kind:
            errors.append("%s layer kind is %s, expected %s" %
                          (layer, "power" if is_power_kind else "signal",
                           "power" if want_power_kind else "signal"))

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            board_text = fh.read()
        stack = _balanced_sexp(board_text, "(stackup")
    except OSError as exc:
        return errors + ["cannot read stackup: %s" % exc]
    if not stack:
        return errors + ["board setup has no stackup section"]
    if profile.get("pofv"):
        for feature in ("capping", "filling"):
            if not re.search(r'\(%s\s+yes\)' % feature, board_text):
                errors.append("POFV board setup does not enable %s" % feature)
    copper_rows = re.findall(
        r'\(layer\s+"(F\.Cu|In[1-4]\.Cu|B\.Cu)"\s+'
        r'\(type\s+"copper"\)\s+\(thickness\s+([0-9.eE+-]+)\)', stack)
    copper = {name: float(value) for name, value in copper_rows}
    for layer in cec_fab.COPPER_LAYERS:
        want = cec_fab.copper_thickness_mm(expected, layer)
        got = copper.get(layer)
        if got is None or abs(got - want) > 1e-6:
            errors.append("%s copper thickness %rmm, expected %.4fmm" %
                          (layer, got, want))
    dielectric_rows = re.findall(
        r'\(layer\s+"dielectric\s+\d+"\s+\(type\s+"(prepreg|core)"\)\s+'
        r'\(thickness\s+([0-9.eE+-]+)\)\s+\(material\s+"([^"]+)"\)', stack)
    got_dielectrics = [(kind, float(thick), material)
                       for kind, thick, material in dielectric_rows]
    want_dielectrics = [(kind, float(thick), material)
                        for kind, thick, material, _er in profile["dielectrics"]]
    if len(got_dielectrics) != len(want_dielectrics):
        errors.append("dielectric layer count %d, expected %d" %
                      (len(got_dielectrics), len(want_dielectrics)))
    else:
        for idx, (got, want) in enumerate(zip(got_dielectrics,
                                              want_dielectrics), 1):
            if (got[0] != want[0] or got[2] != want[2]
                    or abs(got[1] - want[1]) > 1e-6):
                errors.append("dielectric %d %r, expected %r" %
                              (idx, got, want))
    return errors


def _check_expected_fab_profile(board, path, expected):
    errors = _fab_profile_errors(board, path, expected)
    if errors:
        return False, "; ".join(errors[:8]) + (
            " (+%d more)" % (len(errors) - 8) if len(errors) > 8 else "")
    p = cec_fab.get_profile(expected)
    return True, "%s exact six-layer profile and buildup verified" % p["vendor_stackup"]


@checker("high-current-stackup-2oz")
def _chk_high_current_stackup(board, path, ctx):
    expected = cec_fab.profile_for_board_hint(path)
    declared = cec_fab.board_profile_name(board)
    target = "jlcpcb_6l_pofv_high_current"
    if expected != target and declared != target:
        return None, "not an approved high-current board family"
    return _check_expected_fab_profile(board, path, target)


@checker("hub-stackup-6layer")
def _chk_hub_stackup(board, path, ctx):
    expected = cec_fab.profile_for_board_hint(path)
    declared = cec_fab.board_profile_name(board)
    target = "jlcpcb_6l_pofv_signal"
    if expected != target and declared != target:
        return None, "not a Hub board"
    return _check_expected_fab_profile(board, path, target)


@checker("through-vias-only")
def _chk_through_vias_only(board, path, ctx):
    profile = cec_fab.board_profile_name(board)
    expected = cec_fab.profile_for_board_hint(path)
    if profile not in cec_fab.PROFILES and expected not in cec_fab.PROFILES:
        return None, "no approved six-layer fabrication profile"
    profile_name = profile if profile in cec_fab.PROFILES else expected
    profile_spec = cec_fab.get_profile(profile_name)
    bad = []
    for via in (t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T):
        try:
            if int(via.GetViaType()) != int(pcbnew.VIATYPE_THROUGH):
                q = via.GetPosition()
                bad.append("%s@(%.2f,%.2f)" %
                           (via.GetNetname() or "<no net>", _mm(q.x), _mm(q.y)))
                continue
            drill = _mm(via.GetDrillValue())
            dia = _via_width_mm(via)
            annular = (dia - drill) / 2.0
            aspect = profile_spec["board_thickness_mm"] / max(drill, 1e-9)
            problems = []
            if drill < profile_spec["pofv_drill_min_mm"] - 1e-6:
                problems.append("drill %.3f<%.3fmm" %
                                (drill, profile_spec["pofv_drill_min_mm"]))
            if annular < profile_spec["pofv_annular_min_mm"] - 1e-6:
                problems.append("annular %.3f<%.3fmm" %
                                (annular, profile_spec["pofv_annular_min_mm"]))
            if aspect > 8.0 + 1e-6:
                problems.append("aspect %.2f:1>8:1" % aspect)
            if problems:
                q = via.GetPosition()
                bad.append("%s@(%.2f,%.2f) %s" %
                           (via.GetNetname() or "<no net>", _mm(q.x), _mm(q.y),
                            ",".join(problems)))
        except Exception as exc:                        # noqa: BLE001
            return False, "cannot verify via type/dimensions: %s" % exc
    if bad:
        return False, "%d illegal via type/dimension(s): %s%s" % (
            len(bad), ", ".join(bad[:8]),
            " (+%d)" % (len(bad) - 8) if len(bad) > 8 else "")
    return True, "all vias are plated through-board and profile-dimensional (%d checked)" % sum(
        1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)


_MEZZ_SEGMENTS = {
    s["ref"]: ((s["dc"][0], s["dc"][1], s["rot"]),
               dict(s["pin_roles"]), s["footprint_token"])
    for s in cec_mezz.SEGMENTS
}

# The mating datum is derived from the nominal stack boards, not from a runtime
# routing-growth outline.  The ATX force-rail wave may add height below the
# nominal 74x55 frame; that must not silently move the already-authoritative
# mating seats.  The Hub is physically reflected about X for the face-to-face
# dead-bug assembly, so both its offsets and connector angles are conjugated.
_MEZZ_SIDES = {
    "atx-24pin-rev3": {"mirror_x": False, "assembly_dc": (0.0, 0.0)},
    "hub-standard-rev2": {"mirror_x": True,
                          "assembly_dc": cec_mezz.STACK["hub_assembly_dc_mm"]},
}


def _mezz_side(by_ref, path):
    """Resolve the assembly side from fitted hardware before the filename.

    Optimizer and review artifacts are routinely written under temporary
    names.  A pathname-only discriminator therefore mirrored legitimate Hub
    sockets as if they were ATX headers.  The mating hardware is an intrinsic,
    unambiguous board property; the path is retained only as a legacy fallback.
    """
    j6p = by_ref.get("J6P")
    token = j6p.GetFPIDAsString().upper() if j6p is not None else ""
    if "PINSOCKET" in token:
        return _MEZZ_SIDES["hub-standard-rev2"]
    if "PINHEADER" in token:
        return _MEZZ_SIDES["atx-24pin-rev3"]
    norm = os.path.normpath(path).lower()
    return next((v for k, v in _MEZZ_SIDES.items() if k in norm), None)


def _mezz_net_role(net):
    n = (net or "").upper().replace("~", "")
    if not n or "UNCONNECTED-" in n:
        return "NC"
    if n.rsplit("/", 1)[-1] == "GND":
        return "GND"
    if "CAN_H" in n:
        return "CAN_H"
    if "CAN_L" in n:
        return "CAN_L"
    if "DETECT" in n:
        return "DETECT"
    if "5V" in n:
        return "5V"
    return n


@checker("mezzanine-segment-contract")
def _chk_mezzanine_segment_contract(board, path, ctx):
    """Validate both halves against one center-relative mating definition.

    A per-board shared-frame check is sufficient: if each board has the same
    segment offsets, rotations, and role-normalized pin map, translating their
    board centers makes all three connector fields and H1 coincident.
    """
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    present = set(_MEZZ_SEGMENTS) & set(by_ref)
    target_path = any(s in os.path.normpath(path).lower()
                      for s in ("atx-24pin-rev3", "hub-standard-rev2"))
    if not present and not target_path:
        return None, "not a segmented Hub/24-pin mezzanine board"
    errors = []
    missing = sorted(set(_MEZZ_SEGMENTS) - set(by_ref))
    if missing:
        errors.append("missing segment(s) %s" % ",".join(missing))
    x0, y0, x1, y1 = _edge_bbox(board)
    side = _mezz_side(by_ref, path)
    if side:
        # Size sweeps derive their mating pins from the candidate W/H.  Check
        # against that board's actual outline center; a compiled-in nominal
        # size made every legitimate shrink candidate fail this gate.
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        mirror_x = bool(side["mirror_x"])
        ax, ay = side.get("assembly_dc", (0.0, 0.0))
    else:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        mirror_x = False
        ax, ay = 0.0, 0.0
    tol = 0.05
    for ref, (seat, pin_roles, fp_token) in _MEZZ_SEGMENTS.items():
        fp = by_ref.get(ref)
        if fp is None:
            continue
        pos = fp.GetPosition()
        got = (_mm(pos.x), _mm(pos.y), float(fp.GetOrientationDegrees()) % 360.0)
        want = (cx + (-(seat[0] - ax) if mirror_x else seat[0] - ax),
                cy + seat[1] - ay,
                ((180.0 - seat[2]) if mirror_x else seat[2]) % 360.0)
        if (abs(got[0] - want[0]) > tol or abs(got[1] - want[1]) > tol
                or abs(((got[2] - want[2] + 180.0) % 360.0) - 180.0) > 0.01):
            errors.append("%s seat (%.2f,%.2f,%.1f), expected (%.2f,%.2f,%.1f)" %
                          ((ref,) + got + want))
        if fp_token not in fp.GetFPIDAsString().upper():
            errors.append("%s footprint %s, expected %s" %
                          (ref, fp.GetFPIDAsString(), fp_token))
        got_roles = {int(p.GetNumber()): _mezz_net_role(p.GetNetname())
                     for p in fp.Pads() if str(p.GetNumber()).isdigit()}
        if got_roles != pin_roles:
            errors.append("%s pin roles %r, expected %r" %
                          (ref, got_roles, pin_roles))

    lug = by_ref.get("H1")
    if lug is None:
        errors.append("missing shared H1 M2 ground lug")
    else:
        pos = lug.GetPosition()
        lug_dx, lug_dy = cec_mezz.GROUND_LUG["dc"]
        want = (cx + (-(lug_dx - ax) if mirror_x else lug_dx - ax),
                cy + lug_dy - ay)
        if abs(_mm(pos.x) - want[0]) > tol or abs(_mm(pos.y) - want[1]) > tol:
            errors.append("H1 seat (%.2f,%.2f), expected (%.2f,%.2f)" %
                          (_mm(pos.x), _mm(pos.y), want[0], want[1]))
        if cec_mezz.GROUND_LUG["footprint"].split(":", 1)[-1].upper() \
                not in lug.GetFPIDAsString().upper():
            errors.append("H1 is not the plated M2 Pad_Via footprint")
        pads = list(lug.Pads())
        if not pads or any(_mezz_net_role(p.GetNetname()) != "GND" for p in pads):
            errors.append("H1 pad set is not entirely GND")
        enabled_cu = list(board.GetEnabledLayers().CuStack())
        if not pads or any(p.GetDrillSize().x <= 0
                           or not all(p.GetLayerSet().Contains(layer)
                                      for layer in enabled_cu)
                           for p in pads):
            errors.append("H1 is not plated through-board copper")
        center = max(pads, key=lambda p: p.GetDrillSize().x, default=None)
        if (center is None
                or abs(_mm(center.GetDrillSize().x) - cec_mezz.GROUND_LUG["drill_mm"]) > 0.01
                or abs(_mm(center.GetSize().x) - cec_mezz.GROUND_LUG["land_mm"]) > 0.01):
            errors.append("H1 lacks the specified 2.7mm M2.5 hole / 5.0mm lug land")
        if (center is None or not center.GetLayerSet().Contains(pcbnew.F_Mask)
                or not center.GetLayerSet().Contains(pcbnew.B_Mask)):
            errors.append("H1 lug land is not exposed on both outer faces")

    if errors:
        return False, "; ".join(errors[:8]) + (
            " (+%d more)" % (len(errors) - 8) if len(errors) > 8 else "")
    return True, "J6P/J6C/J6D seats and pin roles match; H1 is a coincident plated GND lug"


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
        if t.Type() == pcbnew.PCB_VIA_T and n not in force:
            # A shared force/sense net legitimately carries current-path via
            # arrays away from the measurement tap.  Pad-local tap topology is
            # independently checked below; only a via on a low-current-only
            # sense leg is an unconditional violation here.
            bad.append("via on %s" % n)
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
    """Geometry core: (same_net, diff_net, allowed_pofv), each a list of records
    {ref,pad,pad_net,via_net,x,y}. A record is emitted when a via's outer-copper
    circle overlaps a pad's copper on a shared copper layer; the two classes differ
    only in whether the via and pad nets match (SAME = via-in-pad, DIFF = short)."""
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    pads = [(fp.GetReference(), pad) for fp in board.GetFootprints() for pad in fp.Pads()]
    same, diff, allowed = [], [], []
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
            if vnet != pnet:
                diff.append(rec)
                continue
            try:
                drill_nm = int(via.GetDrillValue())
                through = int(via.GetViaType()) == int(pcbnew.VIATYPE_THROUGH)
            except Exception:                         # noqa: BLE001
                drill_nm, through = 0, False
            ok, why = cec_fab.via_pad_decision(
                board, pad, vpos, vr * 2, drill_nm, via.GetNetCode())
            if not through:
                ok, why = False, "POFV profile permits through vias only"
            rec["reason"] = why
            (allowed if ok else same).append(rec)
    return same, diff, allowed


def via_on_pad_summary(board_path):
    """Load a board and summarise its via-on-pad overlaps: {same, diff, n_vias,
    same_detail, diff_detail}. The public entry cec_router.route's INDEPENDENT verdict
    reads so a via-in-pad board can never pass silently. Callers wrap in try/except --
    a verdict must never break on the checker."""
    board = pcbnew.LoadBoard(board_path)
    n_vias = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)
    same, diff, allowed = _via_pad_overlaps(board)
    return {"same": len(same), "diff": len(diff), "n_vias": n_vias,
            "allowed_pofv": len(allowed), "same_detail": same,
            "diff_detail": diff, "allowed_pofv_detail": allowed}


def _fmt_vop(r):
    return "%s.%s[%s]@(%.2f,%.2f)" % (r["ref"], r["pad"], r["pad_net"] or "<no net>", r["x"], r["y"])


@checker("via-on-pad")
def _chk_via_on_pad(board, path, ctx):
    if not any(t.Type() == pcbnew.PCB_VIA_T for t in board.GetTracks()):
        return None, "no vias on this board (floorplan or fully-planar route)"
    same, diff, allowed = _via_pad_overlaps(board)
    nv = sum(1 for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T)
    if not same and not diff:
        return True, ("no unqualified via copper overlaps a pad (%d vias checked, "
                      "%d qualified POFV overlap(s))" % (nv, len(allowed)))
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


def canonical_high_current_pours(path, *, board=None):
    """Derive the pipeline-owned cable pours under one launch-invariant recipe.

    The ratified route flow uses the wide shunt tap gap and derive-once/stamp-N
    cable uniformity.  Dashboard, placement, routing, and signoff must therefore
    see the same shapes regardless of the invoking shell's environment.

    A complete pour-first state is stronger than a fresh pad-derived estimate:
    it is the exact concave/Manhattan copper the route will materialize.  Prefer
    that authority from the active recipe or the board-owned sidecar.  Falling
    back to a bounding rectangle here recreates phantom solid slabs in hook
    pockets and falsely removes legal signal/PI copper from those empty areas.
    """
    import cec_fr
    state = {}
    state_path = os.environ.get("CEC_POURFIRST_STATE", "").strip()
    if state_path:
        state = cec_fr._pourfirst_state()
    else:
        sidecar = (path[:-len(".kicad_pcb")] + ".pourfirst-state.json"
                   if str(path).endswith(".kicad_pcb") else
                   os.path.splitext(str(path))[0] +
                   ".pourfirst-state.json")
        if os.path.isfile(sidecar):
            with open(sidecar, encoding="utf-8") as source:
                state = json.load(source) or {}
    if state:
        if state.get("placement_scope") != "complete":
            raise ValueError(
                "pour-first state is not complete-placement authority")
        frozen = {str(net) for net in state.get("frozen_nets") or ()}
        pours = [dict(row) for row in state.get("pours") or ()
                 if str((row or {}).get("net") or "") in frozen]
        if not frozen or not pours:
            raise ValueError("pour-first state has no frozen pour geometry")
        if any(str(row.get("provenance") or "") == "uniform_stamp"
               for row in pours):
            raise ValueError(
                "legacy uniform_stamp geometry is not route authority")
        return pours
    recipe = {
        "CEC_SHUNT_GAP": "1",
        "CEC_SHUNT_GAP_MM": "6.5",
        "CEC_POUR_UNIFORM": "1",
        "CEC_POUR_LANES": "0",
        "CEC_INNER_POURS": "0",
        "CEC_LANE_W_JSON": "",
    }
    saved = {key: os.environ.get(key) for key in recipe}
    try:
        os.environ.update(recipe)
        return cec_fr.derive_power_pours(path, board=board)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _exact_pour_rectangles(pours):
    """Decompose authoritative Manhattan pours without filling their pockets.

    The checker/router interfaces consume rectangles for fast capsule tests.
    Concave copper therefore becomes an exact rectangle union, never one
    bounding slab.  Malformed/non-Manhattan input retains the shared geometry
    helper's fail-safe bounding-box behavior rather than under-reserving.
    """
    import cec_synth_pipeline

    rows = []
    for pour in pours or ():
        polygon = pour.get("polygon") or ()
        if not polygon:
            continue
        rectangles, approximate = (
            cec_synth_pipeline._orthogonal_polygon_rectangles(polygon))
        for x0, y0, x1, y1 in rectangles:
            row = {
                "net": str(pour.get("net") or ""),
                "layer": str(pour.get("layer") or "F.Cu"),
                "name": str(pour.get("name") or pour.get("net") or
                            "high-current-pour"),
                "x0": float(x0), "x1": float(x1),
                "y0": float(y0), "y1": float(y1),
            }
            if approximate:
                row["approximation"] = "bbox_non_orthogonal"
            rows.append(row)
    return rows


def _derive_pour_boxes(board, path):
    """The authoritative per-cable high-current pour rectangle union, filtered to genuine cable
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
    has_pours = _has_sensec_pours(board)
    # This checker is consumed outside the route-oracle context by the
    # dashboard, archive jobs, and standalone audits.  Its geometry must not
    # change with the launch shell.  Current cable-interposer pours are placed
    # and routed with the ratified wide shunt notch; cec_synth_pipeline's
    # canonical recipe likewise forces CEC_SHUNT_GAP=1.  Apply that authority
    # locally and restore the caller exactly.  Shared-bus boards remain N/A.
    try:
        pours = canonical_high_current_pours(path, board=board)
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
    shared_force_nets = _shared_bus_force_nets(by_net, shared)
    layer_id = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    boxes, own = [], set()
    for pr in pours:
        net = pr["net"]
        jrefs = {ref for ref, _, _ in by_net.get(net, []) if ref.upper().startswith("J")}
        if jrefs & shared or net in shared_force_nets:
            continue                                       # shared-bus per-pin/per-rail -> N/A
        own.add(net)
    owned_pours = [pr for pr in pours if pr.get("net") in own]
    for region in _exact_pour_rectangles(owned_pours):
        boxes.append((
            region["net"],
            layer_id.get(region["layer"], pcbnew.F_Cu),
            region["x0"], region["x1"],
            region["y0"], region["y1"]))
    if not boxes:
        return None, None
    return boxes, (own | _sense_nets(board))


def _point_segment_distance(px, py, ax, ay, bx, by):
    """Shortest Euclidean distance from a point to a finite segment (mm)."""
    vx, vy = bx - ax, by - ay
    length2 = vx * vx + vy * vy
    if length2 <= 1e-24:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / length2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _orientation(ax, ay, bx, by, cx, cy):
    value = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    if abs(value) <= 1e-12:
        return 0
    return 1 if value > 0 else -1


def _on_segment(ax, ay, bx, by, px, py):
    return (min(ax, bx) - 1e-12 <= px <= max(ax, bx) + 1e-12
            and min(ay, by) - 1e-12 <= py <= max(ay, by) + 1e-12)


def _segments_intersect(a, b, c, d):
    """Closed finite-segment intersection for four ``(x, y)`` mm points."""
    o1 = _orientation(*a, *b, *c)
    o2 = _orientation(*a, *b, *d)
    o3 = _orientation(*c, *d, *a)
    o4 = _orientation(*c, *d, *b)
    if o1 != o2 and o3 != o4:
        return True
    return ((o1 == 0 and _on_segment(*a, *b, *c))
            or (o2 == 0 and _on_segment(*a, *b, *d))
            or (o3 == 0 and _on_segment(*c, *d, *a))
            or (o4 == 0 and _on_segment(*c, *d, *b)))


def _segment_distance(a, b, c, d):
    if _segments_intersect(a, b, c, d):
        return 0.0
    return min(_point_segment_distance(*a, *c, *d),
               _point_segment_distance(*b, *c, *d),
               _point_segment_distance(*c, *a, *b),
               _point_segment_distance(*d, *a, *b))


def _track_capsule_hits_box(start, end, radius, box):
    """Exact capsule-vs-axis-aligned-rectangle test in millimetres.

    The former 11-point centreline sampler missed short and edge-grazing copper.
    A zone filler clears around the *whole* track, not sampled centre points, so
    acceptance must measure the same physical capsule that can neck the pour.
    """
    x0, x1, y0, y1 = box
    a, b = start, end
    if ((x0 <= a[0] <= x1 and y0 <= a[1] <= y1)
            or (x0 <= b[0] <= x1 and y0 <= b[1] <= y1)):
        return True
    edges = (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
             ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0)))
    return any(_segment_distance(a, b, c, d) <= radius + 1e-12
               for c, d in edges)


def _circle_hits_box(x, y, radius, box):
    x0, x1, y0, y1 = box
    nearest_x = min(max(x, x0), x1)
    nearest_y = min(max(y, y0), y1)
    return math.hypot(x - nearest_x, y - nearest_y) <= radius + 1e-12


def _foreign_pour_records(board, path):
    """Return exact foreign copper primitives intruding authoritative pours.

    Each physical track/via appears once and carries every pour it touches plus
    stable UUID and geometry evidence.  Tracks use their full copper capsule;
    vias use their full annulus on every reached copper layer.  This replaces
    the old centre-point sampler, which could miss a narrow or grazing crossing.
    FOREIGN = not a pour force net and not an intentional INA Kelvin input.
    GND and other power rails are foreign.  N/A -> ``(None, None)``.
    """
    boxes, allowed = _derive_pour_boxes(board, path)
    if boxes is None:
        return None, None
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
            x, y = _mm(vp.x), _mm(vp.y)
            # PCB_VIA::GetWidth requires the layer in KiCad 10 (calling the
            # inherited no-argument TRACK overload emits an assertion even
            # though it happens to return the annulus diameter).
            diameter = max(t.GetWidth(lid) for lid in vstack)
            radius = _mm(diameter) / 2.0
            hit_pours = [net for net, lid, x0, x1, y0, y1 in boxes
                         if lid in vstack and _circle_hits_box(
                             x, y, radius, (x0, x1, y0, y1))]
            if hit_pours:
                vias.append({
                    "uuid": t.m_Uuid.AsString(), "net": n,
                    "pour": hit_pours[0], "pours": hit_pours,
                    "x": round(x, 4), "y": round(y, 4),
                    "diameter_mm": round(radius * 2.0, 4),
                    "layers": [board.GetLayerName(lid) for lid in vstack],
                    "locked": bool(t.IsLocked()),
                })
        elif t.Type() == pcbnew.PCB_TRACE_T:
            lid = t.GetLayer()
            s, e = t.GetStart(), t.GetEnd()
            start = (_mm(s.x), _mm(s.y))
            end = (_mm(e.x), _mm(e.y))
            radius = _mm(t.GetWidth()) / 2.0
            hit_pours = [net for net, blid, x0, x1, y0, y1 in boxes
                         if lid == blid and _track_capsule_hits_box(
                             start, end, radius, (x0, x1, y0, y1))]
            if hit_pours:
                tracks.append({
                    "uuid": t.m_Uuid.AsString(), "net": n,
                    "pour": hit_pours[0], "pours": hit_pours,
                    "layer": board.GetLayerName(lid),
                    "start": [round(start[0], 4), round(start[1], 4)],
                    "end": [round(end[0], 4), round(end[1], 4)],
                    "width_mm": round(radius * 2.0, 4),
                    "locked": bool(t.IsLocked()),
                })
    return tracks, vias


def _foreign_by_pour(tracks, vias):
    by = collections.defaultdict(collections.Counter)
    for r in tracks:
        for pour in r.get("pours") or (r["pour"],):
            by[pour][r["net"]] += 1
    for r in vias:
        for pour in r.get("pours") or (r["pour"],):
            by[pour]["via:" + r["net"]] += 1
    return {k: dict(v) for k, v in by.items()}


def high_current_pour_regions(board_path):
    """Return the checker-authoritative high-current pour rectangles in mm.

    Routing stages must consume the geometry measured by the independent
    foreign-copper checker, not a separately clipped corridor approximation.
    The serializable boundary also lets non-pcbnew workers receive the exact
    obstacle set without reimplementing extraction.
    """
    board = pcbnew.LoadBoard(board_path)
    boxes, _allowed = _derive_pour_boxes(board, board_path)
    if boxes is None:
        return []
    return [
        {
            "net": net,
            "layer": board.GetLayerName(layer),
            "x0": float(x0), "x1": float(x1),
            "y0": float(y0), "y1": float(y1),
        }
        for net, layer, x0, x1, y0, y1 in boxes
    ]


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
    # High-current rails are the nets on the two-terminal measurement shunts.
    # A substring search for "12V" incorrectly promoted low-current monitor
    # nets such as NEG12V_DIV, DET12V, DETAMP12V and NEG12V_ADC into pour rails.
    hc = sorted({p.GetNetname()
                 for fp in board.GetFootprints()
                 if fp.GetReference().upper().startswith("RS") and fp.GetPadCount() == 2
                 for p in fp.Pads() if p.GetNetname()})
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


def _shared_bus_force_nets(by_net, shared_connectors):
    """Both sides of every shunt fed by a shared multi-rail connector.

    The old N/A filter looked for the connector on each individual pour net.
    That catches the source side of a shunt but not its load side, even though
    both are the same per-rail shared-bus path.  Discover the two-pad shunt from
    the connector-side net, then return every net on that shunt.
    """
    fed_shunts = set()
    for _net, nodes in by_net.items():
        refs = {ref for ref, _p, _fp in nodes}
        if refs & set(shared_connectors):
            fed_shunts.update(ref for ref in refs if ref.upper().startswith("RS"))
    return {_net for _net, nodes in by_net.items()
            if any(ref in fed_shunts for ref, _p, _fp in nodes)}


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
    """ROUTE-time check against the exact authoritative pour polygons.

    Placement still uses a cheap corridor band as a congestion proxy, but a
    post-route release decision must never promote that rectangular proxy to
    physical copper authority.  Concave hook/notch pours intentionally leave
    usable pockets inside their broad connector-to-shunt band.  Reuse the same
    exact capsule/circle oracle as ``no-foreign-on-high-current-pour`` so a
    legal route in one of those pockets is not reported as an intrusion and a
    grazing track cannot be missed by centre-point sampling.
    """
    if _track_count(board) == 0:
        return None, "floorplan (corridor keepout is a route-time check)"
    try:
        tracks, vias = _foreign_pour_records(board, path)
    except PourRegionError as exc:
        return (False,
                "FAIL-CLOSED: exact high-current corridor authority is unavailable: %s"
                % exc)
    if tracks is None:
        return None, "no per-cable high-current corridor (shared-bus / degenerate)"
    if tracks or vias:
        by_pour = _foreign_by_pour(tracks, vias)
        return (False,
                "foreign copper inside exact high-current corridor polygon: "
                + "; ".join("%s<-%s" % (pour, counts)
                            for pour, counts in sorted(by_pour.items())[:6]),
                [{"type": "keepout",
                  "reserve": "corridor-foreign-copper-exact",
                  "pour": pour, "foreign": counts}
                 for pour, counts in sorted(by_pour.items())])
    boxes, _allowed = _derive_pour_boxes(board, path)
    return (True,
            "no foreign track/via crosses the exact high-current corridor "
            "polygon (%d rectangle cell(s))" % len(boxes or ()))


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


def _kelvin_thin_components(board, sense, *, max_width_mm=0.4):
    """Connected F.Cu thin-track components for each force/sense net.

    Connectivity includes T-junctions whose endpoint lands on the middle of
    another segment.  The old check treated every segment independently, so a
    perfectly valid bent or branched Kelvin tree could never "directly" reach
    both the precision and fast-sense inputs.
    """
    by_net = collections.defaultdict(list)
    for t in board.GetTracks():
        if (t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() in sense
                and t.GetLayer() == pcbnew.F_Cu
                and _mm(t.GetWidth()) <= max_width_mm):
            s, e = t.GetStart(), t.GetEnd()
            by_net[t.GetNetname()].append((
                (_mm(s.x), _mm(s.y), _mm(e.x), _mm(e.y)), t))

    def _intersects(a, b, tol=0.03):
        def _orient(p, q, r):
            return ((q[0] - p[0]) * (r[1] - p[1])
                    - (q[1] - p[1]) * (r[0] - p[0]))
        ap, aq = (a[0], a[1]), (a[2], a[3])
        bp, bq = (b[0], b[1]), (b[2], b[3])
        o1, o2 = _orient(ap, aq, bp), _orient(ap, aq, bq)
        o3, o4 = _orient(bp, bq, ap), _orient(bp, bq, aq)
        if ((o1 <= 0 <= o2 or o2 <= 0 <= o1)
                and (o3 <= 0 <= o4 or o4 <= 0 <= o3)):
            # Bounding boxes reject collinear-but-disjoint extensions.
            if (max(min(a[0], a[2]), min(b[0], b[2]))
                    <= min(max(a[0], a[2]), max(b[0], b[2])) + tol
                    and max(min(a[1], a[3]), min(b[1], b[3]))
                    <= min(max(a[1], a[3]), max(b[1], b[3])) + tol):
                return True
        return min(_point_segment_mm(ap, b), _point_segment_mm(aq, b),
                   _point_segment_mm(bp, a), _point_segment_mm(bq, a)) <= tol

    out = collections.defaultdict(list)
    for net, rows in by_net.items():
        parent = list(range(len(rows)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            a, b = find(i), find(j)
            if a != b:
                parent[b] = a

        for i, (a, _ta) in enumerate(rows):
            for j in range(i + 1, len(rows)):
                if _intersects(a, rows[j][0]):
                    union(i, j)
        groups = collections.defaultdict(list)
        for i, row in enumerate(rows):
            groups[find(i)].append(row)
        out[net] = [{"segments": [r[0] for r in group],
                     "tracks": [r[1] for r in group]}
                    for group in groups.values()]
    return out


def _kelvin_component_touches(comp, pad, extra=0.15):
    pos, size = pad.GetPosition(), pad.GetSize()
    point = (_mm(pos.x), _mm(pos.y))
    reach = math.hypot(_mm(size.x), _mm(size.y)) / 2.0 + extra
    return any(_point_segment_mm(point, seg) <= reach for seg in comp["segments"])


def _filtered_kelvin_force_stub_uuids(board):
    """Prove thin force-net branches that feed filtered high-Z INA inputs.

    A series input resistor gives the short shunt-side stub the *force* net
    name even though it carries only amplifier bias current.  Classify that
    copper by topology, never a refdes list: one two-terminal resistor bridges
    a force net to a verified high-impedance INA input net; its thin F.Cu
    component must touch a shunt terminal, must not touch a connector or other
    active/load pad, and must contain no via.  The independent Kelvin gates
    still own origin, input reach, and bypass correctness.
    """
    highz_nets = set()
    for fp in board.GetFootprints():
        highz = cec_score.ina_highz_pad_names(fp)
        if not highz:
            continue
        highz_nets.update(
            pad.GetNetname() for pad in fp.Pads()
            if pad.GetPadName() in highz and pad.GetNetname())
    if not highz_nets:
        return set()

    bridges = []
    for fp in board.GetFootprints():
        ref = fp.GetReference().upper()
        pads = list(fp.Pads())
        if not ref.startswith("R") or ref.startswith("RS") or len(pads) != 2:
            continue
        for force_pad, sense_pad in ((pads[0], pads[1]), (pads[1], pads[0])):
            force_net = force_pad.GetNetname()
            if (sense_pad.GetNetname() in highz_nets and force_net
                    and force_net != sense_pad.GetNetname()):
                bridges.append((force_net, fp, force_pad))
    if not bridges:
        return set()

    force_nets = {row[0] for row in bridges}
    components = _kelvin_thin_components(board, force_nets)
    pads_by_net = collections.defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() in force_nets:
                pads_by_net[pad.GetNetname()].append((fp, pad))
    vias_by_net = collections.defaultdict(list)
    for item in board.GetTracks():
        if item.Type() == pcbnew.PCB_VIA_T and item.GetNetname() in force_nets:
            vias_by_net[item.GetNetname()].append(item)

    qualified = set()
    for force_net, bridge_fp, force_pad in bridges:
        for component in components.get(force_net, ()):
            if not _kelvin_component_touches(component, force_pad):
                continue
            touched = [(fp, pad) for fp, pad in pads_by_net[force_net]
                       if _kelvin_component_touches(component, pad)]
            if not any(fp.GetReference().upper().startswith("RS")
                       for fp, _pad in touched):
                continue
            if any(fp.GetReference().upper().startswith("J")
                   for fp, _pad in touched):
                continue
            allowed_refs = {bridge_fp.GetReference().upper()}
            forbidden = False
            for fp, _pad in touched:
                ref = fp.GetReference().upper()
                if (ref in allowed_refs or ref.startswith("RS")
                        or ref.startswith(("R", "C"))):
                    continue
                forbidden = True
                break
            if forbidden:
                continue
            if any(any(
                    _point_segment_mm(
                        (_mm(via.GetPosition().x), _mm(via.GetPosition().y)),
                        segment) <= 0.03
                    for segment in component["segments"])
                   for via in vias_by_net[force_net]):
                continue
            qualified.update(
                track.m_Uuid.AsString() for track in component["tracks"])
    return qualified


@checker("kelvin-sense-from-inner-pad")
def _chk_kelvin_inner(board, path, ctx):
    """Verify each Kelvin tree leaves the inner shunt edge and reaches every sense input.

    A valid tap may be bent and may branch to both the precision and fast-sense
    amplifiers.  Therefore the electrical object checked here is a connected
    thin-track F.Cu tree, not one artificially straight segment.
    """
    if _track_count(board) == 0:
        return None, "floorplan (route-time)"
    shunts = [fp for fp in board.GetFootprints() if fp.GetReference().upper().startswith("RS")]
    sense = _sense_nets(board)
    if not shunts or not sense:
        return None, "no shunt / sense nets"
    inner_min = _param("kelvin-sense-from-inner-pad", "inner_min_mm", 0.1)
    # Current-sense input pads on each net.  VBUS and digital pins are excluded
    # by the per-part pin-function table below.
    ina_pads = collections.defaultdict(list)
    for fp in board.GetFootprints():
        if not _is(fp, "INA2", "INA181"):
            continue
        for p in fp.Pads():
            nn = p.GetNetname()
            want = _kelvin_input_pad_name(fp, nn)
            if nn in sense and want is not None and p.GetPadName() == want:
                ina_pads[nn].append((fp, p))
    components = _kelvin_thin_components(board, sense)
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
            pad_reach = math.hypot(_mm(sz.x), _mm(sz.y)) / 2.0 + 0.3
            touching = [comp for comp in components.get(net, [])
                        if _kelvin_component_touches(comp, pad, extra=0.3)]
            if not touching:
                continue                                     # no stub resolvable on this pad -> not checked
            checked += 1
            best_inner = None
            valid_tree = None
            for comp in touching:
                # The shunt-side endpoint must start on the pad's inward half;
                # merely crossing the pad centre is not a Kelvin inner-edge tap.
                for seg in comp["segments"]:
                    for ex_abs, ey_abs in ((seg[0], seg[1]), (seg[2], seg[3])):
                        ex, ey = ex_abs - _mm(pc.x), ey_abs - _mm(pc.y)
                        if math.hypot(ex, ey) <= pad_reach:
                            inner = ex * ix + ey * iy
                            best_inner = inner if best_inner is None else max(best_inner, inner)
                if (best_inner is not None and best_inner >= inner_min
                        and all(_kelvin_component_touches(comp, target)
                                for _target_fp, target in targets)):
                    valid_tree = comp
                    break
            if valid_tree is not None:
                continue
            why = ("not inner edge" if best_inner is None or best_inner < inner_min
                   else "F.Cu Kelvin tree does not reach every IN+/IN- input")
            bad.append("%s pad %s (%s)" % (sh.GetReference(), pad.GetPadName(), why))
            payload.append({"type": "inner_tap", "shunt": sh.GetReference(),
                            "pad": pad.GetPadName(), "net": net, "why": why})
    if checked == 0:
        return None, "no thin Kelvin sense stub resolvable (sense merged with the force pour?)"
    if bad:
        return (False, "Kelvin sense not tapped from the inner shunt edge to every IN+/IN-: "
                + "; ".join(bad[:6]), payload)
    return True, "Kelvin inner-edge F.Cu trees reach every IN+/IN- (%d shunt pad(s))" % checked


# IN+/IN- input pad NAME per current-sense part (Vbus is deliberately absent -- it is a high-Z
# voltage tap, not a Kelvin current-sense input, so it is allowed to FR-route to the connector).
_KELVIN_INPAD = {"INA238": {"_HI": "10", "_LO": "9"},
                 "INA228": {"_HI": "10", "_LO": "9"},
                 "INA181": {"_HI": "3", "_LO": "4"},
                 "INA240": {"_HI": "8", "_LO": "1"}}


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
    """Reject a connector/via tap while accepting one branched shunt-origin tree.

    Multiple current-sense inputs may share the same Kelvin tree.  What is not
    allowed is a second tree at an input, a via at an input, no shunt origin,
    more than one shunt origin, or any direct connector-pad touch.
    """
    if _track_count(board) == 0:
        return None, "floorplan (route-time)"
    sense = _sense_nets(board)
    shunt_pads = collections.defaultdict(list)
    for fp in board.GetFootprints():
        if not (fp.GetReference().upper().startswith("RS") and fp.GetPadCount() == 2):
            continue
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn in sense:
                shunt_pads[nn].append((fp, p))
    if not sense or not shunt_pads:
        return None, "no 2-pad shunt / sense nets"
    extra = _param("kelvin-sense-no-connector-tap", "pad_reach_extra_mm", 0.15)
    components = _kelvin_thin_components(board, sense)
    connector_pads = collections.defaultdict(list)
    for fp in board.GetFootprints():
        if not fp.GetReference().upper().startswith("J"):
            continue
        for p in fp.Pads():
            if p.GetNetname() in sense:
                connector_pads[p.GetNetname()].append((fp, p))
    vias = collections.defaultdict(list)
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() in sense:
            vias[t.GetNetname()].append(t)
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
            touching = [comp for comp in components.get(net, [])
                        if _kelvin_component_touches(comp, p, extra=extra)]
            pad_vias = []
            for via in vias.get(net, []):
                vp = via.GetPosition()
                if math.hypot(_mm(vp.x) - pc[0], _mm(vp.y) - pc[1]) <= reach:
                    pad_vias.append(via)
            if not touching and not pad_vias:
                continue                                       # unconnected input -> board-routing-complete owns it
            checked += 1
            shunt_origins, connector_taps = [], []
            if len(touching) == 1:
                comp = touching[0]
                shunt_origins = [(owner, sp) for owner, sp in shunt_pads[net]
                                 if _kelvin_component_touches(comp, sp, extra=0.3)]
                connector_taps = [(owner, cp) for owner, cp in connector_pads.get(net, [])
                                  if _kelvin_component_touches(comp, cp, extra=extra)]
            if (len(touching) == 1 and not pad_vias
                    and len(shunt_origins) == 1 and not connector_taps):
                continue
            if pad_vias:
                why = "via on the sense input (tap must be via-less F.Cu)"
            elif len(touching) != 1:
                why = "%d separate F.Cu trees at input (exactly one allowed)" % len(touching)
            elif connector_taps:
                why = "Kelvin tree directly touches connector pad(s): %s" % ",".join(
                    "%s.%s" % (owner.GetReference(), cp.GetPadName())
                    for owner, cp in connector_taps[:4])
            elif len(shunt_origins) > 1:
                why = "Kelvin tree has %d shunt origins (exactly one allowed)" % len(shunt_origins)
            else:
                why = "Kelvin tree has no shunt-pad origin"
            bad.append("%s.%s on %s: %s" % (fp.GetReference(), p.GetPadName(), net, why))
    if checked == 0:
        return None, "no resolvable INA input stub on a sense net"
    if bad:
        return (False, "Kelvin sense input has a parallel/non-shunt connection (carries load current -- "
                "not four-wire): " + "; ".join(bad[:6]),
                [{"type": "inner_tap", "why": "connector_tap", "detail": d} for d in bad])
    return True, "Kelvin inputs use one via-less, connector-free shunt tree (%d input pad(s))" % checked


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


def _clip_polygon_axis(poly, axis, bound, keep_greater):
    """Clip one simple polygon to an axis-aligned half-plane."""
    if not poly:
        return []

    def inside(point):
        return (point[axis] >= bound - 1e-12 if keep_greater
                else point[axis] <= bound + 1e-12)

    out = []
    previous = poly[-1]
    previous_inside = inside(previous)
    for current in poly:
        current_inside = inside(current)
        if current_inside != previous_inside:
            denominator = current[axis] - previous[axis]
            ratio = ((bound - previous[axis]) / denominator
                     if abs(denominator) > 1e-18 else 0.0)
            out.append((
                previous[0] + ratio * (current[0] - previous[0]),
                previous[1] + ratio * (current[1] - previous[1])))
        if current_inside:
            out.append(current)
        previous = current
        previous_inside = current_inside
    return out


def _polygon_box_overlap_area(poly, box):
    """Exact area of a simple polygon inside ``(x0,x1,y0,y1)``."""
    x0, x1, y0, y1 = map(float, box)
    clipped = list(poly)
    for axis, bound, keep_greater in (
            (0, x0, True), (0, x1, False),
            (1, y0, True), (1, y1, False)):
        clipped = _clip_polygon_axis(
            clipped, axis, bound, keep_greater)
        if not clipped:
            return 0.0
    return abs(sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(clipped, clipped[1:] + clipped[:1]))) / 2.0


def _fp_courtyard_polygons(fp):
    """Return exact courtyard outlines in global millimetres.

    Courtyards commonly include pad-side notches.  Their bounding boxes can
    overstate body/pour overlap by several square millimetres, which is enough
    to turn a deliberately notched current corridor into a false blocker.
    """
    try:
        courtyard = fp.GetCourtyard(
            pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        polygons = []
        for outline_index in range(courtyard.OutlineCount()):
            outline = courtyard.Outline(outline_index)
            polygon = [
                (_mm(outline.CPoint(index).x),
                 _mm(outline.CPoint(index).y))
                for index in range(outline.PointCount())]
            if len(polygon) >= 3:
                polygons.append(polygon)
        if polygons:
            return polygons
    except Exception:                                  # noqa: BLE001
        pass
    x0, x1, y0, y1 = _fp_courtyard_bbox(fp)
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


@checker("sense-body-clear-of-pour")
def _chk_sense_body_clear(board, path, ctx):
    """The current-sense IC sits hard against its shunt (Kelvin), but its BODY must clear the SENSEC
    high-current pour. Build the same pour rectangles the router lays (cec_fr.derive_power_pours) and
    assert each sense IC's courtyard centroid is in the un-poured notch AND its courtyard overlaps the
    pour by <= max_overlap_mm2. This is the geometric ENFORCE leg of the placer's _seat_sense_ics.

    FAIL-CLOSED on the same region-finder hole as no-foreign-on-high-current-pour: a board WITH SENSEC
    pour copper whose region-finder raises/returns empty FAILS (the body-clear cannot be verified),
    never N/A-pass. Genuine no-pour boards keep their N/A skip."""
    try:
        filtered, _allowed = _derive_pour_boxes(board, path)
    except PourRegionError as e:
        return (False, "FAIL-CLOSED: sense-body-clear region-finder errored on a board WITH SENSEC "
                "pours -- cannot verify the sense IC body clears the high-current pour: %s" % e)
    if filtered is None:
        return None, "no per-cable SENSEC high-current pour region (shared-bus / non-cable board)"
    box_by_net = collections.defaultdict(list)
    for net, lid, x0, x1, y0, y1 in filtered:
        box_by_net[net].append((lid, (x0, x1, y0, y1)))
    tol = _param("sense-body-clear-of-pour", "max_overlap_mm2", 2.0)
    fails, oks, payload = [], [], []
    for fp in board.GetFootprints():
        if not _is(fp, "INA2", "INA181"):
            continue
        nets = {(p.GetNetname() or "").upper() for p in fp.Pads()}
        body_layer = pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
        boxes = [box for net, regions in box_by_net.items()
                 for lid, box in regions
                 if net.upper() in nets and lid == body_layer]
        # A body on F.Cu cannot obstruct a B.Cu pour (and vice versa).  The
        # former checker dropped the region layer while grouping by net, then
        # added both surface overlaps.  On a six-layer board this turned a
        # legal notched F.Cu placement into a false double-area blocker.
        if not boxes:
            continue                                            # filtered-lane INA (no _HI/_LO pour) -> N/A
        cy = _fp_courtyard_bbox(fp)
        cx0, cy0 = (cy[0] + cy[1]) / 2.0, (cy[2] + cy[3]) / 2.0
        courtyard_polygons = _fp_courtyard_polygons(fp)
        ov = sum(_polygon_box_overlap_area(polygon, box)
                 for box in boxes for polygon in courtyard_polygons)
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


def _coupled_pair_names(board):
    """Return USB naming variants plus CAN_H/CAN_L as physical pairs.

    CAN is deliberately included even though KiCad's ``_P/_N`` auto-pair
    convention does not discover it.
    """
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values()
             if n.GetNetname()}
    pairs, seen = [], set()

    def add(kind, p, n):
        key = frozenset((p, n))
        if p in names and n in names and key not in seen:
            pairs.append((kind, p, n))
            seen.add(key)

    _kelvin, derived = cec_score._derive_pairs(names)
    for p, n in derived:
        kind = "usb" if "USB" in p.upper() else ("can" if "CAN" in p.upper() else "diff")
        add(kind, p, n)
    def add_leaf_pair(kind, p_leaf, n_leaf):
        """Pair special-name leaves without discarding hierarchy.

        KiCad saves a hierarchical CAN bus as ``/sheet/CAN_H`` and
        ``/sheet/CAN_L``.  Exact comparisons against ``/CAN_H`` silently made
        those nets invisible to the physical pair gate, even though the later
        signoff skew audit found them.  Derive the mate in the *same hierarchy*
        so repeated sheet-local buses remain distinct and unambiguous.
        """
        for p in sorted(names):
            leaf = p.rsplit("/", 1)[-1]
            if leaf != p_leaf:
                continue
            prefix = p[:-len(p_leaf)] if p_leaf else p
            add(kind, p, prefix + n_leaf)

    for p_leaf, n_leaf in (("USB_DP", "USB_DM"),
                           ("USB_D+", "USB_D-")):
        add_leaf_pair("usb", p_leaf, n_leaf)
    for p_leaf, n_leaf in (("CAN_H", "CAN_L"),
                           ("CAN_H_BUS", "CAN_L_BUS")):
        add_leaf_pair("can", p_leaf, n_leaf)
    return pairs


def _point_segment_mm(point, segment):
    px, py = point
    x0, y0, x1, y1 = segment
    vx, vy = x1 - x0, y1 - y0
    length2 = vx * vx + vy * vy
    u = 0.0 if length2 == 0 else max(0.0, min(1.0,
        ((px - x0) * vx + (py - y0) * vy) / length2))
    return math.hypot(px - (x0 + u * vx), py - (y0 + u * vy))


def _pair_netclass_geometry(path, kind):
    classes = cec_impedance._netclasses(path)
    spec = next((v for k, v in classes.items() if kind in (k or "").lower()), {})
    width = spec.get("diff_width") or spec.get("width")
    gap = spec.get("diff_gap")
    clearance = spec.get("clearance")
    if kind == "usb":
        return (float(width or 0.20), float(gap or 0.13),
                float(clearance or 0.20))
    if kind == "can":
        return (float(width or 0.25), float(gap or 0.20),
                float(clearance or 0.20))
    return (float(width or 0.20), float(gap or 0.20),
            float(clearance or 0.20))


def _partition_pair_vias(board, vias):
    """Return ``(endpoint_pofv, serial_route_vias)`` for one pair member.

    The distinction is physical, never provenance-based: every endpoint item
    must independently pass the central profile, dimension, net, SMD, and
    containment decision.  Everything else remains a serial transition.
    """
    endpoint, route = [], []
    for via in vias:
        blocking, allowed = cec_fab.via_at_pad_conflicts(
            board, via.GetPosition(), via.GetWidth(via.TopLayer()),
            via.GetDrillValue(), via.GetNetCode())
        (endpoint if blocking is None and allowed else route).append(via)
    return endpoint, route


def _net_pad_mst_mm(board, net_name):
    """Return a topology-safe lower bound for one routed net's pad span.

    Pair members are normally point-to-point, but CAN variants may contain
    multiple same-net connector lands.  A Euclidean minimum spanning tree is a
    valid lower bound for both cases and avoids pretending the first/last pad
    ordering is authoritative.
    """
    points = []
    seen = set()
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetNetname() != net_name:
                continue
            position = pad.GetPosition()
            point = (position.x / 1e6, position.y / 1e6)
            key = (round(point[0], 6), round(point[1], 6))
            if key not in seen:
                seen.add(key)
                points.append(point)
    if len(points) < 2:
        return 0.0
    connected = {0}
    remaining = set(range(1, len(points)))
    length = 0.0
    while remaining:
        distance, index = min(
            (math.hypot(points[source][0] - points[target][0],
                        points[source][1] - points[target][1]), target)
            for source in connected for target in remaining)
        length += distance
        connected.add(index)
        remaining.remove(index)
    return length


def _pair_contract_stations(board, pnet, nnet, *, split_limit_mm=8.0):
    """Return the endpoint geometry needed by the coupled-length contract.

    A pair normally terminates on one footprint at each end.  Series or split
    termination networks instead end on two adjacent, matching footprints.
    That split is a physical fan-out requirement, not an arbitrary routing
    choice.  Preserve only the small geometry vocabulary needed by admission;
    the precision router retains the richer placement certificate.
    """
    by_net = {pnet: collections.defaultdict(list),
              nnet: collections.defaultdict(list)}
    footprints = {}
    for footprint in board.GetFootprints():
        ref = str(footprint.GetReference())
        footprints[ref] = footprint
        for pad in footprint.Pads():
            net = str(pad.GetNetname() or "")
            if net not in by_net:
                continue
            at = pad.GetPosition()
            by_net[net][ref].append((at.x / 1e6, at.y / 1e6))

    def centre(points):
        return (sum(row[0] for row in points) / len(points),
                sum(row[1] for row in points) / len(points))

    def station(kind, refs, p_points, n_points):
        pc, nc = centre(p_points), centre(n_points)
        center = ((pc[0] + nc[0]) / 2.0, (pc[1] + nc[1]) / 2.0)
        return {
            "kind": kind, "physical_refs": sorted(refs),
            "center": [round(center[0], 6), round(center[1], 6)],
            "member_pitch_mm": round(math.hypot(
                pc[0] - nc[0], pc[1] - nc[1]), 6),
        }

    p_by_ref, n_by_ref = by_net[pnet], by_net[nnet]
    stations = [
        station("same-footprint-pair", (ref,), p_by_ref[ref], n_by_ref[ref])
        for ref in sorted(set(p_by_ref) & set(n_by_ref))]
    unmatched_p = sorted(set(p_by_ref) - set(n_by_ref))
    unmatched_n = sorted(set(n_by_ref) - set(p_by_ref))

    def signature(ref):
        prefix = re.match(r"[A-Za-z]+", ref)
        try:
            item = str(footprints[ref].GetFPID().GetLibItemName())
        except Exception:                              # noqa: BLE001
            item = ""
        return ((prefix.group(0).upper() if prefix else ""), item)

    candidates = []
    for p_ref in unmatched_p:
        if len(p_by_ref[p_ref]) != 1:
            continue
        for n_ref in unmatched_n:
            if len(n_by_ref[n_ref]) != 1:
                continue
            ps, ns = signature(p_ref), signature(n_ref)
            if (not ps[0] or ps[0] != ns[0]
                    or (ps[1] and ns[1] and ps[1] != ns[1])):
                continue
            distance = math.hypot(
                p_by_ref[p_ref][0][0] - n_by_ref[n_ref][0][0],
                p_by_ref[p_ref][0][1] - n_by_ref[n_ref][0][1])
            if distance <= float(split_limit_mm) + 1e-9:
                candidates.append((round(distance, 6), p_ref, n_ref))
    used_p, used_n = set(), set()
    for _distance, p_ref, n_ref in sorted(candidates):
        if p_ref in used_p or n_ref in used_n:
            continue
        used_p.add(p_ref); used_n.add(n_ref)
        stations.append(station(
            "split-member-footprints", (p_ref, n_ref),
            p_by_ref[p_ref], n_by_ref[n_ref]))
    return sorted(stations, key=lambda row: (
        row["center"][0], row["center"][1], row["physical_refs"]))


def pair_coupling_contract(kind, coupling, member_lengths,
                           *, endpoint_stations=None,
                           local_cell_limit_mm=8.0):
    """Apply one coupled-length contract to routing and final signoff.

    USB always retains its strict percentage/absolute limit.  CAN permits a
    geometry-derived local-cell exception only when exactly two endpoint
    stations are present, at least one station is a split-member termination,
    and their centres are within the bounded local fan-out radius.  The
    effective uncoupled budget is then the same 2x endpoint-span detour bound
    enforced independently on both members.  This admits unavoidable package
    fan-out without waiving coupling on a real trunk or on an arbitrary short
    route that lacks the physical split-terminal witness.
    """
    kind = str(kind or "diff").lower()
    minimum_fraction = 0.60 if kind == "can" else 0.80
    base_budget_mm = 2.0 if kind == "can" else 0.75
    fraction = float((coupling or {}).get("fraction") or 0.0)
    maximum_length = max(
        (float(value) for value in (member_lengths or {}).values()),
        default=0.0)
    uncoupled_mm = maximum_length * (1.0 - fraction)
    stations = [row for row in (endpoint_stations or ())
                if isinstance(row, dict)
                and isinstance(row.get("center"), (list, tuple))
                and len(row["center"]) >= 2]
    local_span = None
    forced_local_fanout = False
    effective_budget_mm = base_budget_mm
    if kind == "can" and len(stations) == 2 and any(
            row.get("kind") == "split-member-footprints"
            for row in stations):
        local_span = math.hypot(
            float(stations[1]["center"][0])
            - float(stations[0]["center"][0]),
            float(stations[1]["center"][1])
            - float(stations[0]["center"][1]))
        if local_span <= float(local_cell_limit_mm) + 1e-9:
            forced_local_fanout = True
            effective_budget_mm = max(base_budget_mm, 2.0 * local_span)
    sampled = int((coupling or {}).get("total_samples") or 0) > 0
    ok = bool(sampled and (
        fraction + 1e-9 >= minimum_fraction
        or uncoupled_mm <= effective_budget_mm + 1e-9))
    return {
        "schema": 2, "ok": ok, "kind": kind,
        "coupled_coverage_pct": round(100.0 * fraction, 1),
        "minimum_coupled_coverage_pct": round(
            100.0 * minimum_fraction, 1),
        "member_lengths_mm": {
            str(net): round(float(length), 6)
            for net, length in sorted((member_lengths or {}).items())},
        "uncoupled_length_mm": round(uncoupled_mm, 6),
        "base_uncoupled_length_budget_mm": base_budget_mm,
        "uncoupled_length_budget_mm": round(effective_budget_mm, 6),
        "forced_endpoint_fanout": forced_local_fanout,
        "endpoint_station_span_mm": (
            None if local_span is None else round(local_span, 6)),
        "local_cell_limit_mm": float(local_cell_limit_mm),
        "sampled": sampled,
    }


def high_speed_pair_summary(board_path, *, board=None, sample_mm=0.5):
    """Physical USB/CAN route-quality verdict for the final filled board.

    This intentionally goes beyond connectivity/DRC: it measures skew, coupling,
    layer/via symmetry, adjacent-reference legality, actual filled-GND coverage,
    and transition return vias. Closed-form impedance remains an advisory because
    fabrication confirmation (or a calibrated 2-D solver) is still required.
    """
    b = board or pcbnew.LoadBoard(board_path)
    pairs = _coupled_pair_names(b)
    if not pairs:
        return {"applicable": False, "ok": True, "pairs": [], "violations": []}
    profile_name = cec_fab.active_profile_name(b, hint=board_path)
    if not profile_name:
        return {"applicable": False, "ok": True, "pairs": [], "violations": [],
                "note": "no active fabrication profile; legacy board is outside current BETA gate"}
    profile = cec_fab.get_profile(profile_name)
    roles = dict(zip(cec_fab.COPPER_LAYERS, profile["roles"]))
    layers = cec_fab.COPPER_LAYERS

    tracks_by_net, vias_by_net = collections.defaultdict(list), collections.defaultdict(list)
    gnd_vias = []
    for item in b.GetTracks():
        name = item.GetNetname() or ""
        if item.GetClass() == "PCB_TRACK":
            tracks_by_net[name].append(item)
        elif item.GetClass() == "PCB_VIA":
            vias_by_net[name].append(item)
            if name == "GND":
                gnd_vias.append(item.GetPosition())

    gnd_polys = {}

    # Connectivity/skew/coupling can all pass while a member locally doubles
    # back.  Precompute the exact-junction topology audit once and fold matching
    # evidence into each physical pair verdict.
    import cec_route_quality
    pair_nets = {net for _kind, pnet, nnet in pairs for net in (pnet, nnet)}
    topology = cec_route_quality.analyze_board(b, critical_nets=pair_nets)
    topology_by_net = collections.defaultdict(list)
    for issue in topology.get("issues", ()):
        if issue.get("severity") == "blocking":
            topology_by_net[issue.get("net")].append(issue)

    def reference_layer(signal_layer):
        if signal_layer not in layers or "SIG" not in roles.get(signal_layer, ""):
            return None
        i = layers.index(signal_layer)
        adjacent = []
        if i > 0:
            adjacent.append(layers[i - 1])
        if i + 1 < len(layers):
            adjacent.append(layers[i + 1])
        return next((layer for layer in adjacent if roles.get(layer) == "GND"), None)

    def filled_gnd(layer):
        if layer in gnd_polys:
            return gnd_polys[layer]
        lid = b.GetLayerID(layer)
        polys = []
        for zone in b.Zones():
            if zone.GetNetname() != "GND" or not zone.IsOnLayer(lid):
                continue
            poly = zone.GetFilledPolysList(lid)
            if poly.OutlineCount() > 0:
                polys.append(poly)
        gnd_polys[layer] = polys
        return polys

    def layer_name(track):
        lid = int(track.GetLayer())
        return cec_fab.COPPER_LAYER_IDS.get(lid, b.GetLayerName(lid))

    def segment(track):
        s, e = track.GetStart(), track.GetEnd()
        return (s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6)

    pair_rows, all_violations = [], []
    for kind, pnet, nnet in pairs:
        p_tracks, n_tracks = tracks_by_net[pnet], tracks_by_net[nnet]
        violations = []
        p_len = sum(math.hypot(t.GetEnd().x - t.GetStart().x,
                               t.GetEnd().y - t.GetStart().y) / 1e6 for t in p_tracks)
        n_len = sum(math.hypot(t.GetEnd().x - t.GetStart().x,
                               t.GetEnd().y - t.GetStart().y) / 1e6 for t in n_tracks)
        # The release oracle has always used 4.0mm for CAN, calibrated from
        # the 2.8mm hand-routed boards.  Use that same authority here so an
        # intermediate pair candidate cannot pass a looser 5.0mm gate and then
        # fail signoff without any intervening geometry change.
        skew_limit = 3.81 if kind == "usb" else 4.0
        skew = abs(p_len - n_len)
        p_span = _net_pad_mst_mm(b, pnet)
        n_span = _net_pad_mst_mm(b, nnet)
        detour_limit = 2.0
        p_detour = p_len / p_span if p_span >= 2.0 else None
        n_detour = n_len / n_span if n_span >= 2.0 else None
        if not p_tracks or not n_tracks:
            violations.append("one or both legs have no routed track segments")
        if skew > skew_limit + 1e-6:
            violations.append("skew %.2fmm exceeds %.2fmm" % (skew, skew_limit))
        if any(value is not None and value > detour_limit + 1e-9
               for value in (p_detour, n_detour)):
            violations.append(
                "route detour P=%s N=%s exceeds %.2fx endpoint-MST span" % (
                    ("n/a" if p_detour is None else "%.2fx" % p_detour),
                    ("n/a" if n_detour is None else "%.2fx" % n_detour),
                    detour_limit))
        for issue in (list(topology_by_net.get(pnet, ()))
                      + list(topology_by_net.get(nnet, ()))):
            violations.append("route topology: %s" % issue["message"])

        p_layers = {layer_name(t) for t in p_tracks}
        n_layers = {layer_name(t) for t in n_tracks}
        if p_layers != n_layers:
            violations.append("asymmetric layer sets P=%s N=%s" %
                              (sorted(p_layers), sorted(n_layers)))
        used_layers = p_layers | n_layers
        bad_layers = [layer for layer in used_layers if reference_layer(layer) is None]
        if bad_layers:
            violations.append("route layer(s) lack adjacent GND reference: %s" %
                              ", ".join(sorted(bad_layers)))

        p_vias, n_vias = vias_by_net[pnet], vias_by_net[nnet]

        # A qualified via-in-pad on an endpoint land is an alternate entry
        # into the same net (not an additional serial corridor transition).
        # Keep it in total-via symmetry and return-path checks, but do not
        # count it against the two series layer-change budget.
        p_endpoint_vias, p_route_vias = _partition_pair_vias(b, p_vias)
        n_endpoint_vias, n_route_vias = _partition_pair_vias(b, n_vias)
        matched_transition_spacing = []
        if len(p_vias) != len(n_vias):
            violations.append("asymmetric via count P=%d N=%d" % (len(p_vias), len(n_vias)))
        if len(p_endpoint_vias) != len(n_endpoint_vias):
            violations.append(
                "asymmetric endpoint POFV fan-in P=%d N=%d" %
                (len(p_endpoint_vias), len(n_endpoint_vias)))
        if len(p_route_vias) != len(n_route_vias):
            violations.append(
                "asymmetric route-transition via count P=%d N=%d" %
                (len(p_route_vias), len(n_route_vias)))
        elif p_route_vias:
            remaining = list(n_route_vias)
            for p_via in sorted(
                    p_route_vias,
                    key=lambda via: (via.GetPosition().x, via.GetPosition().y)):
                p_at = p_via.GetPosition()
                mate = min(
                    remaining,
                    key=lambda via: math.hypot(
                        p_at.x - via.GetPosition().x,
                        p_at.y - via.GetPosition().y))
                n_at = mate.GetPosition()
                spacing = math.hypot(
                    p_at.x - n_at.x, p_at.y - n_at.y) / 1e6
                matched_transition_spacing.append(spacing)
                remaining.remove(mate)
            if any(value > 1.5 + 1e-9
                   for value in matched_transition_spacing):
                violations.append(
                    "signal vias do not form matched transitions "
                    "(spacing=%smm, limit=1.50mm)" %
                    [round(value, 3)
                     for value in matched_transition_spacing])
        if max(len(p_route_vias), len(n_route_vias)) > 2:
            violations.append(
                "more than two route-transition vias per leg P=%d N=%d" %
                (len(p_route_vias), len(n_route_vias)))
        missing_returns = []
        endpoint_ids = {
            via.m_Uuid.AsString()
            for via in p_endpoint_vias + n_endpoint_vias}
        for via in p_vias + n_vias:
            at = via.GetPosition()
            nearest = min((math.hypot(at.x - gv.x, at.y - gv.y) / 1e6
                           for gv in gnd_vias), default=float("inf"))
            if nearest > 1.5 + 1e-9:
                missing_returns.append({
                    "net": via.GetNetname(),
                    "at_mm": [round(at.x / 1e6, 6),
                              round(at.y / 1e6, 6)],
                    "nearest_gnd_mm": (None if not math.isfinite(nearest)
                                       else round(nearest, 6)),
                    "endpoint_pofv": (
                        via.m_Uuid.AsString() in endpoint_ids),
                    "uuid": via.m_Uuid.AsString(),
                })
        if missing_returns:
            violations.append("%d transition via(s) lack a GND return via within 1.5mm" %
                              len(missing_returns))

        width, nominal_gap, pair_clearance = _pair_netclass_geometry(
            board_path, kind)
        coupled, coupled_total = 0, 0
        ref_covered, ref_total = 0, 0
        transition_reference_samples = 0
        return_supported_vias = []
        for via in p_vias + n_vias:
            at = via.GetPosition()
            nearest_return = min((
                math.hypot(at.x - ground.x, at.y - ground.y) / 1e6
                for ground in gnd_vias), default=float("inf"))
            if nearest_return <= 1.5 + 1e-9:
                return_supported_vias.append((
                    at.x / 1e6, at.y / 1e6,
                    _via_width_mm(via) / 2.0
                    + pair_clearance + float(sample_mm) / 2.0))
        for track in p_tracks + n_tracks:
            seg = segment(track)
            x0, y0, x1, y1 = seg
            length = math.hypot(x1 - x0, y1 - y0)
            count = max(1, int(math.ceil(length / sample_mm)))
            layer = layer_name(track)
            ref = reference_layer(layer)
            polys = filled_gnd(ref) if ref else []
            for i in range(count):
                u = (i + 0.5) / count
                x, y = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
                point = pcbnew.VECTOR2I(int(round(x * 1e6)), int(round(y * 1e6)))
                filled_reference = any(poly.Contains(point) for poly in polys)
                # The signal-via antipad is intentionally not filled GND.  Its
                # field return is the nearby GND barrel checked above, so do
                # not score the bounded transition cell a second time as a
                # missing plane.  The sample half-cell term prevents a sample
                # whose represented interval overlaps the antipad from being
                # misclassified due to midpoint quantization.  A transition
                # without the required return via receives no exclusion.
                transition_cell = (not filled_reference and any(
                    math.hypot(x - vx, y - vy) <= radius + 1e-9
                    for vx, vy, radius in return_supported_vias))
                if transition_cell:
                    transition_reference_samples += 1
                else:
                    ref_total += 1
                if filled_reference:
                    ref_covered += 1
                # Coupling is sampled in both directions. Use the opposite leg,
                # not the current net; rebuild its table for N samples below.
                opposite = n_tracks if track.GetNetname() == pnet else p_tracks
                opp_segments = [segment(o) for o in opposite if layer_name(o) == layer]
                coupled_total += 1
                if opp_segments:
                    center = min(_point_segment_mm((x, y), other) for other in opp_segments)
                    edge_gap = center - width
                    if -0.03 <= edge_gap <= (2.5 * nominal_gap + 0.15):
                        coupled += 1
        ref_fraction = ref_covered / max(1, ref_total)
        coupled_fraction = coupled / max(1, coupled_total)
        coupling_admission = pair_coupling_contract(
            kind, {"fraction": coupled_fraction,
                   "total_samples": coupled_total},
            {pnet: p_len, nnet: n_len},
            endpoint_stations=_pair_contract_stations(b, pnet, nnet))
        uncoupled_budget_mm = coupling_admission[
            "uncoupled_length_budget_mm"]
        uncoupled_mm = coupling_admission["uncoupled_length_mm"]
        if ref_total and ref_fraction < 0.95:
            violations.append("filled adjacent-GND coverage %.1f%% is below 95%%" %
                              (100.0 * ref_fraction))
        if coupled_total and not coupling_admission["ok"]:
            violations.append("coupled-route coverage %.1f%% is below %.0f%%" %
                              (100.0 * coupled_fraction,
                               coupling_admission[
                                   "minimum_coupled_coverage_pct"]))

        stackups = {}
        for layer in sorted(used_layers):
            if reference_layer(layer):
                stackups[layer] = cec_impedance.stackup_for_board(
                    board_path, board=b, layer=layer)
        row = {"kind": kind, "p": pnet, "n": nnet,
               "length_p_mm": round(p_len, 3), "length_n_mm": round(n_len, 3),
               "endpoint_mst_p_mm": round(p_span, 3),
               "endpoint_mst_n_mm": round(n_span, 3),
               "detour_ratio_p": (None if p_detour is None
                                   else round(p_detour, 3)),
               "detour_ratio_n": (None if n_detour is None
                                   else round(n_detour, 3)),
               "detour_ratio_limit": detour_limit,
               "skew_mm": round(skew, 3), "layers": sorted(used_layers),
               "vias_p": len(p_vias), "vias_n": len(n_vias),
               "endpoint_pofv_p": len(p_endpoint_vias),
               "endpoint_pofv_n": len(n_endpoint_vias),
               "route_transition_vias_p": len(p_route_vias),
               "route_transition_vias_n": len(n_route_vias),
               "transition_pair_spacing_mm": [
                   round(value, 3)
                   for value in matched_transition_spacing],
               "missing_return_vias": missing_returns,
               "reference_coverage_pct": round(100.0 * ref_fraction, 1),
               "transition_reference_samples": transition_reference_samples,
               "coupled_coverage_pct": round(100.0 * coupled_fraction, 1),
               "uncoupled_length_mm": round(uncoupled_mm, 3),
               "uncoupled_length_budget_mm": uncoupled_budget_mm,
               "coupling_admission": coupling_admission,
               "stackups": stackups, "violations": violations}
        pair_rows.append(row)
        all_violations.extend("%s %s/%s: %s" % (kind.upper(), pnet, nnet, msg)
                              for msg in violations)
    return {"applicable": True, "ok": not all_violations,
            "profile": profile_name, "pairs": pair_rows,
            "violations": all_violations,
            "route_quality": topology}


@checker("high-speed-pair-physical-integrity")
def _chk_high_speed_pair_physical(board, path, ctx):
    rep = high_speed_pair_summary(path, board=board)
    if not rep.get("applicable"):
        return None, rep.get("note", "no USB/CAN physical pair on this board")
    if not rep["ok"]:
        return False, "; ".join(rep["violations"][:8])
    return True, "%d pair(s) meet skew/layer/via/coupling/reference-return contract" % len(rep["pairs"])


@checker("aggressor-victim-field-coupling")
def _chk_aggressor_victim_field_coupling(board, path, ctx):
    import cec_field_coupling
    rep = cec_field_coupling.field_coupling_summary(path, board=board)
    if not rep.get("applicable"):
        return None, "no classified aggressor/victim routed nets"
    if not rep["ok"]:
        return False, "; ".join(rep["violations"][:8])
    return True, ("%d routed aggressor/victim interaction(s) meet "
                  "separation/shield/orthogonal-crossing policy" %
                  rep["interaction_count"])


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
        # Dead-bug stack alternative: three independently located plated
        # mezzanine segments provide the multi-point structural restraint and
        # H1 is the plated M2.5 ground/retention lug.  Counting only standalone
        # M3 footprints incorrectly rejects this intentional retention system.
        segs = {fp.GetReference(): fp for fp in board.GetFootprints()
                if fp.GetReference() in ("J6P", "J6C", "J6D")}
        lug = next((fp for fp in mounts if fp.GetReference() == "H1"
                    and any((p.GetNetname() or "").upper() == "GND"
                            and p.GetDrillSize().x > 0 for p in fp.Pads())), None)
        plated = (len(segs) == 3 and all(
            list(fp.Pads()) and all(p.GetDrillSize().x > 0 for p in fp.Pads())
            for fp in segs.values()))
        if lug is None or not plated:
            return (False, "found %d mounts, expect >= %d (and no complete J6P/J6C/J6D + H1 "
                    "stack-retention alternative)" % (len(mounts), want),
                    [{"type": "add", "what": "mounting_hole", "need": want - len(mounts)}])
        return True, ("segmented stack retention present: plated J6P/J6C/J6D at three locations "
                      "+ GND-tied M2.5 H1 lug")
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
    edge_max = _param("fiducial-protocol", "edge_band_max_mm", 8.0)
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
        if m > edge_max:
            fails.append("%s %.1fmm from nearest edge (> %.1f edge band)" %
                         (fp.GetReference(), m, edge_max))
        near = min((_min_pad_dist_mm(fp, o) for o in board.GetFootprints()
                    if o is not fp and list(o.Pads()) and not o.GetReference().upper().startswith("FID")),
                   default=1e9)
        if near < clear:
            fails.append("%s clear zone %.1fmm (< %.1f)" % (fp.GetReference(), near, clear))
    if fails:
        return False, "fiducial protocol (§K.4): " + "; ".join(fails[:6])
    return True, ("%d fiducials, asymmetric, %.1f..%.1fmm edge band, "
                  "clear >= %.1fmm" % (len(fids), edge_min, edge_max, clear))


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


def _capacitance_f_board(value):
    """Parse the compact capacitance notation used on the PCB footprints."""
    return cec_device_bypass.capacitance_f(value)


def _ground_net(net):
    return net == "GND" or bool(net and net.endswith("/GND"))


def _numbered_pad(fp, number):
    return next((pad for pad in fp.Pads() if str(pad.GetNumber()) == str(number)), None)


def _device_bypass_assignment(board, *, project_max_mm=3.5):
    """Resolve distinct capacitor ownership for selected powered devices.

    The result is board-only and deterministic.  It matches capacitors to the
    selected device's actual supply pad and rail, then enforces either a
    manufacturer numeric limit or the explicit CEC project placement limit.
    """
    caps = []
    for fp in board.GetFootprints():
        if not fp.GetReference().startswith("C"):
            continue
        dnp, excluded = _fp_assembly_state(fp)
        if dnp or excluded:
            continue
        pads = list(fp.Pads())
        if len(pads) != 2:
            continue
        connected = [pad for pad in pads if pad.GetNetname()]
        net_pads = {pad.GetNetname(): pad for pad in connected}
        farads = _capacitance_f_board(_val(fp))
        if (len(connected) == 2 and len(net_pads) == 2
                and farads is not None):
            grounded = [pad for pad in connected
                        if _ground_net(pad.GetNetname())]
            powered = [pad for pad in connected
                       if not _ground_net(pad.GetNetname())]
            caps.append({
                "ref": fp.GetReference(), "fp": fp,
                "net_pads": net_pads, "farads": farads,
                # Compatibility fields for diagnostics which display the
                # ordinary rail/GND orientation.  Matching below uses
                # net_pads, so a rail-to-rail capacitor has no ambiguous
                # synthetic "ground" terminal.
                "pad": powered[0] if len(grounded) == 1 and powered else None,
                "rail": (powered[0].GetNetname()
                         if len(grounded) == 1 and powered else None),
                # A nearby hold-up or distribution electrolytic is not the
                # high-frequency local bypass named by this contract.  Keep
                # bulk energy storage available to the PDN/hold-up audits,
                # but never let it steal one-to-one ownership from the small
                # ceramic that must sit at the device pins.
                "local_bypass_technology":
                    cec_device_bypass.local_bypass_technology(
                        _val(fp), fp.GetFPIDAsString()),
            })

    requirements = []
    for fp in board.GetFootprints():
        ref, value = fp.GetReference(), _val(fp)
        if not ref.startswith("U"):
            continue
        dnp, excluded = _fp_assembly_state(fp)
        if dnp or excluded:
            continue
        for pin_number, kind, max_mm, source in \
                cec_device_bypass.requirements_for_value(value, project_max_mm):
            pad = _numbered_pad(fp, pin_number)
            if pad and pad.GetNetname() and not _ground_net(pad.GetNetname()):
                requirements.append({
                    "id": "%s:%s:%s" % (ref, pin_number, kind),
                    "ref": ref, "pin": pin_number, "pad": pad,
                    "rail": pad.GetNetname(), "kind": kind,
                    "return_rail": "GND", "return_pin": None,
                    "return_pad": None,
                    "max_mm": max_mm, "source": source,
                })
        for pin_number, return_pin, kind, max_mm, source in \
                cec_device_bypass.rail_to_rail_requirements_for_value(
                    value, project_max_mm):
            pad = _numbered_pad(fp, pin_number)
            return_pad = _numbered_pad(fp, return_pin)
            if (pad and return_pad and pad.GetNetname()
                    and return_pad.GetNetname()
                    and pad.GetNetname() != return_pad.GetNetname()):
                requirements.append({
                    "id": "%s:%s:%s:%s" % (
                        ref, pin_number, return_pin, kind),
                    "ref": ref, "pin": pin_number, "pad": pad,
                    "rail": pad.GetNetname(), "kind": kind,
                    "return_pin": return_pin,
                    "return_pad": return_pad,
                    "return_rail": return_pad.GetNetname(),
                    "max_mm": max_mm, "source": source,
                })

    def compatible(req, cap):
        if (req["rail"] not in cap["net_pads"]
                or req.get("return_rail", "GND") not in cap["net_pads"]):
            return False
        if not cap.get("local_bypass_technology", True):
            return False
        return cec_device_bypass.kind_compatible(req["kind"], cap["farads"])

    def distance(req, cap):
        a = req["pad"].GetPosition()
        b = cap["net_pads"][req["rail"]].GetPosition()
        return math.hypot(_mm(a.x - b.x), _mm(a.y - b.y))

    edges = {}
    compatible_all = {}
    # Preserve the same narrow reference-affinity ownership used by the
    # netlist placer.  Without this reservation a later geometric repair can
    # swap two electrically identical common-rail capacitors, then optimize
    # the wrong pair and physically pull the intended bypass away from its IC.
    # Affinity is not required: designs that do not number Cx with Ux retain
    # the ordinary maximum-cardinality proximity matcher below.
    raw_compatible = {}
    for index, req in enumerate(requirements):
        raw_compatible[index] = [
            (cap_index, distance(req, cap))
            for cap_index, cap in enumerate(caps) if compatible(req, cap)
        ]
    owner_requirement_count = {}
    for req in requirements:
        owner_requirement_count[req["ref"]] = (
            owner_requirement_count.get(req["ref"], 0) + 1)
    reserved_caps = {
        cap_index
        for req_index, req in enumerate(requirements)
        for cap_index, _dist in raw_compatible[req_index]
        if (owner_requirement_count.get(req["ref"]) == 1
            and cec_device_bypass.reference_affinity(
                caps[cap_index]["ref"], req["ref"]))
    }
    for index, req in enumerate(requirements):
        affinity = [
            item for item in raw_compatible[index]
            if (owner_requirement_count.get(req["ref"]) == 1
                and cec_device_bypass.reference_affinity(
                    caps[item[0]]["ref"], req["ref"]))
        ]
        all_candidates = affinity or [
            item for item in raw_compatible[index]
            if item[0] not in reserved_caps
        ]
        all_candidates.sort(key=lambda item: (item[1], caps[item[0]]["ref"]))
        compatible_all[index] = all_candidates
        edges[index] = [
            item for item in all_candidates
            if _within_physical_distance_limit(item[1], req["max_mm"])
        ]

    cap_owner = {}
    assigned_index = {}

    def augment(req_index, seen_caps):
        for cap_index, dist in edges[req_index]:
            if cap_index in seen_caps:
                continue
            seen_caps.add(cap_index)
            previous = cap_owner.get(cap_index)
            if previous is None or augment(previous, seen_caps):
                cap_owner[cap_index] = req_index
                assigned_index[req_index] = (cap_index, dist)
                if previous is not None:
                    assigned_index.pop(previous, None)
                return True
        return False

    for req_index in sorted(range(len(requirements)), key=lambda i: (
            len(edges[i]), requirements[i]["rail"], requirements[i]["ref"],
            requirements[i]["pin"])):
        augment(req_index, set())

    assigned = {}
    missing = []
    for req_index, req in enumerate(requirements):
        if req_index in assigned_index:
            cap_index, dist = assigned_index[req_index]
            assigned[req["id"]] = {
                "requirement": req, "cap_ref": caps[cap_index]["ref"],
                "distance_mm": dist,
            }
            continue
        miss = dict(req)
        if compatible_all[req_index]:
            cap_index, nearest = compatible_all[req_index][0]
            miss["nearest_ref"] = caps[cap_index]["ref"]
            miss["nearest_mm"] = nearest
        else:
            miss["nearest_ref"] = None
            miss["nearest_mm"] = None
        missing.append(miss)
    return {"requirements": requirements, "assigned": assigned, "missing": missing}


@checker("decoupler-adjacency-k5")
def _chk_decap_k5(board, path, ctx):
    measured = _device_bypass_assignment(
        board, project_max_mm=_param("decoupling-cap-owner", "max_mm", 3.5)
    )
    if not measured["requirements"]:
        return None, "no audited powered devices resolved"
    distances = [item["distance_mm"] for item in measured["assigned"].values()]
    worst = max(distances, default=0.0)
    return None, (
        "historical universal 1.5mm K.5 target retired; device-specific one-to-one "
        "audit resolved %d/%d requirements, worst assigned pad distance %.2fmm" %
        (len(measured["assigned"]), len(measured["requirements"]), worst)
    )


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
    measured = _device_bypass_assignment(board, project_max_mm=max_mm)
    requirements = measured["requirements"]
    if not requirements:
        return None, "no audited powered devices resolved"
    missing = measured["missing"]
    if missing:
        details = []
        payload = []
        for req in missing[:12]:
            nearest = req.get("nearest_mm")
            reason = "no compatible capacitor on %s" % req["rail"]
            if nearest is not None:
                reason = "nearest compatible capacitor %.2fmm away (limit %.2fmm)" % (
                    nearest, req["max_mm"])
            details.append("%s.%s %s" % (req["ref"], req["pin"], reason))
            payload.append({
                "type": "adjacent",
                "a": req.get("nearest_ref") or "unassigned-cap",
                "b": req["ref"],
                "max_mm": req["max_mm"],
            })
        return False, (
            "%d/%d device-specific bypass requirement(s) lack a distinct in-limit capacitor: %s" %
            (len(missing), len(requirements), "; ".join(details))
        ), payload
    worst = max(
        measured["assigned"].values(), key=lambda item: item["distance_mm"]
    )
    return True, (
        "%d one-to-one bypass assignments pass; worst is %s to %s at %.2fmm" %
        (len(requirements), worst["cap_ref"], worst["requirement"]["ref"],
         worst["distance_mm"])
    )


@checker("buck-switch-cell-placement")
def _chk_buck_switch_cell(board, path, ctx):
    """Measure the two placement-critical TLV62569 switching-cell legs."""
    bucks = [fp for fp in board.GetFootprints()
             if "TLV62569" in _val(fp) and not any(_fp_assembly_state(fp))]
    if not bucks:
        return None, "no fitted TLV62569"

    max_sw_l = _param("buck-switch-cell-placement", "sw_to_l_mm", 3.0)
    max_l_c = _param("buck-switch-cell-placement", "l_to_cout_mm", 3.5)

    def pad_distance(a, b):
        pa, pb = a.GetPosition(), b.GetPosition()
        return math.hypot(_mm(pa.x - pb.x), _mm(pa.y - pb.y))

    failures = []
    passes = []
    footprints = list(board.GetFootprints())
    for buck in bucks:
        ref = buck.GetReference()
        sw = _numbered_pad(buck, "3")
        if sw is None or not sw.GetNetname():
            failures.append(f"{ref} SW pin 3 has no net")
            continue
        inductors = []
        for fp in footprints:
            if not fp.GetReference().startswith("L") or any(_fp_assembly_state(fp)):
                continue
            pads = list(fp.Pads())
            sw_pads = [pad for pad in pads if pad.GetNetname() == sw.GetNetname()]
            if len(pads) == 2 and len(sw_pads) == 1:
                other = pads[0] if pads[1] is sw_pads[0] else pads[1]
                if other.GetNetname() and not _ground_net(other.GetNetname()):
                    inductors.append((pad_distance(sw, sw_pads[0]), fp, other))
        if not inductors:
            failures.append(f"{ref} SW net {sw.GetNetname()} has no two-pad output inductor")
            continue
        sw_l, inductor, lout = min(inductors, key=lambda row: row[0])
        if sw_l > max_sw_l:
            failures.append(f"{ref}->{inductor.GetReference()} SW leg {sw_l:.2f}mm > {max_sw_l:.2f}mm")

        output_caps = []
        for fp in footprints:
            if not fp.GetReference().startswith("C") or any(_fp_assembly_state(fp)):
                continue
            pads = list(fp.Pads())
            rail = [pad for pad in pads if pad.GetNetname() == lout.GetNetname()]
            gnd = [pad for pad in pads if _ground_net(pad.GetNetname())]
            if len(pads) == 2 and len(rail) == 1 and len(gnd) == 1:
                farads = _capacitance_f_board(_val(fp))
                if farads is not None and farads + 1e-15 >= 10e-6:
                    output_caps.append((pad_distance(lout, rail[0]), fp))
        if not output_caps:
            failures.append(f"{inductor.GetReference()} output {lout.GetNetname()} has no >=10uF GND-return capacitor")
            continue
        l_c, cap = min(output_caps, key=lambda row: row[0])
        if l_c > max_l_c:
            failures.append(f"{inductor.GetReference()}->{cap.GetReference()} output leg {l_c:.2f}mm > {max_l_c:.2f}mm")
        passes.append(f"{ref}-{inductor.GetReference()}-{cap.GetReference()} {sw_l:.2f}/{l_c:.2f}mm")

    if failures:
        return False, "TLV62569 switch-cell placement: " + "; ".join(failures)
    return True, "TLV62569 switch cells compact: " + "; ".join(passes)


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


def _legal_neckdown_uuids(path, ctx):
    """Return exact track UUIDs wholly contained by bounded pin escapes.

    Both current-density and netclass signoff must interpret the physical
    exception identically.  Cache the read-only classifier because a full
    checklist invokes both consumers on the same artifact.
    """
    key = "_legal_neckdowns::" + os.path.abspath(path)
    if key in ctx:
        return set(ctx[key])
    legal = set()
    try:
        import cec_fr
        probe = pcbnew.LoadBoard(path)
        report = cec_fr.normalize_netclass_geometry(probe, path)
        legal.update(report.get("legal_neckdown_uuids") or ())
    except Exception:                                    # noqa: BLE001
        legal = set()
    ctx[key] = sorted(legal)
    return legal


@checker("trace-width-high-current")
def _chk_tw(board, path, ctx):
    if _track_count(board) == 0:
        return None, "floorplan (no tracks)"
    profile_name = cec_fab.active_profile_name(board, hint=path)
    if not profile_name:
        return None, "no current fabrication profile for current-density width model"
    # Design-basis current is one source of truth shared with DCIR/thermal.
    import cec_synth_pipeline as csp
    names = _nets(board)
    include_current_nets = {
        str(net) for net in (ctx.get("current_domain_include_nets") or ())
        if str(net)}
    gnd_current = csp.spec_gnd_current(path, names)
    try:
        import cec_current_topology
        current_domains = cec_current_topology.board_current_domains(
            board, board_hint=path)
    except Exception:                                  # noqa: BLE001
        cec_current_topology = None
        current_domains = {}

    def current_contract(net):
        if net.rsplit("/", 1)[-1] == "GND":
            static = (None if gnd_current is None else {
                "amps": gnd_current, "geometry_margin": 1.25,
                "margin_included": False, "source": "board_return_basis",
            })
        else:
            static = csp.spec_net_current_contract(path, net)
        if static is not None:
            return static
        # Isolated routing workers deliberately use anonymous artifact names.
        # The exact source/sink authority is already identity-stable through
        # CEC_THERMAL_BOARD_HINT; width signoff must consume that same current
        # rather than silently degrade to "no rated net" after a board copy.
        domain = current_domains.get(net) or {}
        amps = domain.get("amps")
        if not domain.get("complete") or amps is None:
            return None
        return {
            "amps": float(amps),
            "geometry_margin": 1.25,
            "margin_included": False,
            "source": "current_domain_authority",
        }

    # A track fully embedded in its own filled zone is not the load-bearing
    # cross-section; the zone/pour-width gates own that copper. Merely having a
    # zone somewhere on the net is no exemption.
    zone_polys = collections.defaultdict(list)
    distributed_ground_nets = set()
    for zone in board.Zones():
        if zone.GetIsRuleArea() or not zone.GetNetname():
            continue
        for lid in board.GetEnabledLayers().CuStack():
            if not zone.IsOnLayer(lid):
                continue
            poly = zone.GetFilledPolysList(lid)
            if poly.OutlineCount():
                zone_polys[(zone.GetNetname(), int(lid))].append(poly)
                # A filled inner GND plane is the aggregate return conductor.
                # Its many outer pad/via entry stubs do not each carry the
                # board's entire return current.  Current-injection accounting
                # plus the DCIR/plane gates own their combined bottleneck.
                if (zone.GetNetname().rsplit("/", 1)[-1] == "GND"
                        and int(lid) not in (pcbnew.F_Cu, pcbnew.B_Cu)):
                    distributed_ground_nets.add(zone.GetNetname())

    def embedded(track):
        polys = zone_polys.get((track.GetNetname(), int(track.GetLayer())), ())
        if not polys:
            return False
        s, e = track.GetStart(), track.GetEnd()
        mid = pcbnew.VECTOR2I((s.x + e.x) // 2, (s.y + e.y) // 2)
        return all(any(poly.Contains(point) for poly in polys)
                   for point in (s, mid, e))

    sense = _sense_nets(board)
    legal_neckdowns = _legal_neckdown_uuids(path, ctx)
    filtered_kelvin = _filtered_kelvin_force_stub_uuids(board)
    bad, checked, poured = [], 0, 0
    distributed_returns = pin_neckdowns = kelvin_stubs = 0
    domain_removed = collections.defaultdict(set)
    domain_requirements = collections.defaultdict(list)
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_TRACE_T:
            continue
        n = t.GetNetname()
        if include_current_nets and n not in include_current_nets:
            continue
        contract = current_contract(n)
        amps = contract.get("amps") if contract else None
        if amps is None or amps < 1.0:
            continue
        checked += 1
        if n in distributed_ground_nets:
            distributed_returns += 1
            continue
        if t.m_Uuid.AsString() in legal_neckdowns:
            # A physically unavoidable fine-pitch prefix is checked by the
            # exact bounded graph classifier shared with netclass signoff.  It
            # is not a waiver for the rest of the route: long locked segments
            # are deliberately absent from this UUID set.
            pin_neckdowns += 1
            continue
        if t.m_Uuid.AsString() in filtered_kelvin:
            kelvin_stubs += 1
            continue
        if embedded(t):
            poured += 1
            continue
        # Direct INA2xx Kelvin stubs can share the force net name. Their
        # zero-via/F.Cu/inner-pad topology is independently hard-gated.
        if n in sense:
            continue
        lid = int(t.GetLayer())
        layer = cec_fab.COPPER_LAYER_IDS.get(lid, board.GetLayerName(lid))
        try:
            required = cec_fab.ipc2221_required_width_mm(
                amps, layer, profile_name=profile_name, rise_c=30.0,
                margin=float(contract.get("geometry_margin", 1.25)))
        except ValueError as exc:
            bad.append((n, layer, _mm(t.GetWidth()), None, str(exc)))
            continue
        actual = _mm(t.GetWidth())
        if actual + 0.001 < required:
            domain = current_domains.get(n) or {}
            if domain.get("complete"):
                domain_removed[n].add(t.m_Uuid.AsString())
                domain_requirements[n].append(required)
                continue
            bad.append((n, layer, actual, required,
                        "not inside its own filled zone; basis=%s" %
                        contract.get("source", "unknown")))
    domain_bad = []
    domain_proofs = {}
    if domain_removed and cec_current_topology is not None:
        probe = pcbnew.LoadBoard(path)
        remove_ids = set().union(*domain_removed.values())
        for item in list(probe.GetTracks()):
            try:
                uuid = item.m_Uuid.AsString()
            except Exception:                          # noqa: BLE001
                continue
            if uuid in remove_ids:
                probe.Remove(item)
        # KiCad's in-process connectivity object may retain removed SWIG
        # items. Serialize/reload the throwaway artifact before the proof; the
        # production artifact is never changed.
        with tempfile.TemporaryDirectory(prefix="cec-current-domain-") as tmp:
            filtered_path = os.path.join(tmp, "rated-subgraph.kicad_pcb")
            pcbnew.SaveBoard(filtered_path, probe)
            filtered = pcbnew.LoadBoard(filtered_path)
            for net in sorted(domain_removed):
                proof = cec_current_topology.authority_connectivity(
                    filtered, net, board_hint=path)
                domain_proofs[net] = proof
                if not proof.get("connected"):
                    domain_bad.append((
                        net,
                        max(domain_requirements.get(net) or (0.0,)),
                        len(domain_removed[net]),
                        proof.get("reason") or "aggregate_current_path_open",
                    ))
    if bad or domain_bad:
        detail = "; ".join("%s %s %.3fmm<%smm (%s)" %
                           (n, layer, actual,
                            ("?" if required is None else "%.3f" % required), why)
                           for n, layer, actual, required, why in bad[:8])
        domain_detail = "; ".join(
            "%s has no source-to-sink path after removing %d segment(s) "
            "below %.3fmm (%s)" % (net, count, required, reason)
            for net, required, count, reason in domain_bad[:8])
        joined = "; ".join(part for part in (detail, domain_detail) if part)
        return (False, "%d current-model violation(s): %s" %
                (len(bad) + len(domain_bad), joined),
                [{"type": "keepout", "reserve": "pour_or_widen", "net": n,
                  "layer": layer, "actual_mm": actual, "required_mm": required}
                 for n, layer, actual, required, _why in bad[:20]]
                + [{"type": "current_domain_path", "net": net,
                    "required_mm": required,
                    "removed_undersized_segments": count,
                    "reason": reason}
                   for net, required, count, reason in domain_bad[:20]])
    if checked == 0:
        return None, "no routed net with a ratified >=1A current model"
    return True, ("%d current-model trace segment(s) checked against %s; %d embedded in "
                  "their own filled zone; %d bounded pin neck-down(s); %d "
                  "topology-proven filtered Kelvin stub(s); %d "
                  "distributed GND entry segment(s) delegated to current-"
                  "injection/DCIR plane gates; %d undersized side-branch "
                  "segment(s) removed while proving %d aggregate current "
                  "domain(s)" %
                  (checked, profile_name, poured, pin_neckdowns, kelvin_stubs,
                   distributed_returns,
                   sum(len(rows) for rows in domain_removed.values()),
                   len(domain_proofs)))


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
        with open(pro, encoding="utf-8") as f:
            ns = json.load(f).get("net_settings", {})
    except Exception:
        return None
    classes = {}
    for c in ns.get("classes", []):
        classes[c.get("name", "")] = {k: c[k] for k in
                                      ("track_width", "via_diameter", "via_drill",
                                       "diff_pair_width", "diff_pair_gap")
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
    pair_nets = {net for _kind, p, n in _coupled_pair_names(board) for net in (p, n)}
    # The final geometry normalizer owns the narrowly-scoped physical exception
    # to a class minimum: <=1.5 mm from a fine-pitch SMD pad, or <=2.5 mm from a
    # constrained PTH escape whose full class width would collide with a foreign
    # pad.  Re-run that exact classifier on a throwaway board and exempt only the
    # UUIDs it proves legal.  This keeps conformance aligned with fabrication
    # normalization without duplicating (and eventually drifting from) its graph
    # distance and collision logic.  Any classifier error fails closed below.
    legal_neckdowns = _legal_neckdown_uuids(path, ctx)
    bad = collections.defaultdict(lambda: collections.Counter())
    qualified_pofv = 0
    for t in board.GetTracks():
        net = t.GetNetname()
        if not net:
            continue
        cls = resolve(net)
        minima = classes.get(cls, {})
        if isinstance(t, pcbnew.PCB_VIA):
            blocking, allowed = cec_fab.via_at_pad_conflicts(
                board, t.GetPosition(), t.GetWidth(t.TopLayer()),
                t.GetDrillValue(), t.GetNetCode())
            if blocking is None and allowed:
                qualified_pofv += 1
                continue
            d = minima.get("via_diameter")
            dr = minima.get("via_drill")
            if d and _via_width_mm(t) < d - tol:
                bad[(net, cls)]["via_dia"] += 1
            if dr and _mm(t.GetDrillValue()) < dr - tol:
                bad[(net, cls)]["via_drill"] += 1
        elif t.Type() == pcbnew.PCB_TRACE_T:
            w = (minima.get("diff_pair_width") if net in pair_nets else None) \
                or minima.get("track_width")
            if net in sense:
                continue                  # deliberate ~0.25mm Kelvin stub on the force net
            if t.m_Uuid.AsString() in legal_neckdowns:
                continue                  # bounded, classifier-proven pin escape
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
    return True, ("all tracks/vias meet assigned track/diff/via minima (%d classes; "
                  "%d physical pair net(s); sense-stub exemption on %d net(s); "
                  "%d bounded pin-neckdown track(s); %d profile-qualified POFV)" %
                  (len(classes), len(pair_nets), len(sense),
                   len(legal_neckdowns), qualified_pofv))


# bom-field-lint: assembly-irrelevant refs + the DOCUMENTED-open sourcing gaps.
_BOM_KNOWN_OPEN = ("RS", "J_IN", "J_OUT")     # OQ-11 shunts + consigned THT power headers
_BOM_PLACEHOLDER = re.compile(r"(^$|^~$|_Small$|\b(TODO|TBD|FIXME|PLACEHOLDER|APPROXIMATE)\b)", re.I)


def _schematic_for_board(path, ctx):
    """Resolve a project's root schematic, including candidate subfolders."""
    if ctx.get("sch"):
        return ctx["sch"]
    directory = os.path.dirname(os.path.abspath(path))
    for candidate_dir in (directory, os.path.dirname(directory)):
        sch = cec_toolchain.find_root_sch(candidate_dir)
        if sch:
            return sch
    return _project_file(path, ".kicad_sch")


def _schematic_inventory_for_board(path, ctx):
    sch = _schematic_for_board(path, ctx)
    if not sch:
        return None, None
    key = "_sch_inventory::" + os.path.abspath(sch)
    if key not in ctx:
        ctx[key] = cec_sch_gates.inventory(sch)
    return sch, ctx[key]


def _fp_assembly_state(fp):
    """Return (DNP, excluded-from-BOM), tolerating older pcbnew bindings."""
    dnp_fn = getattr(fp, "IsDNP", None)
    bom_fn = getattr(fp, "IsExcludedFromBOM", None)
    return (bool(dnp_fn()) if dnp_fn else False,
            bool(bom_fn()) if bom_fn else False)


@checker("bom-field-lint")
def _chk_bom_lint(board, path, ctx):
    placeholders, unsourced_known = [], []
    n_parts = 0
    _sch, sch_inventory = _schematic_inventory_for_board(path, ctx)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if _board_only_ref(ref):
            continue
        pcb_dnp, pcb_excluded = _fp_assembly_state(fp)
        sch_rec = (sch_inventory or {}).get(ref)
        sch_excluded = bool(sch_rec and (
            sch_rec.get("dnp") or not sch_rec.get("in_bom", True)
            or not sch_rec.get("on_board", True)))
        if pcb_dnp or pcb_excluded or sch_excluded:
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
        with open(sch_path, encoding="utf-8", errors="replace") as f:
            text = _strip_lib_symbols(f.read())
    except OSError:
        return refs
    for r in _SCH_REF_RE.findall(text):
        if r.endswith("?") or _board_only_ref(r):
            continue
        refs.add(r)
    return refs


def _pcb_component_signatures(board):
    """Value, footprint item, and connected numbered-pad nets by reference."""
    signatures = {}
    for fp in board.GetFootprints():
        ref = str(fp.GetReference())
        if _board_only_ref(ref):
            continue
        pins = {
            (str(pad.GetNumber()), str(pad.GetNetname()))
            for pad in fp.Pads()
            if (str(pad.GetNumber()) and str(pad.GetNetname()) and
                not str(pad.GetNetname()).startswith("unconnected-"))
        }
        signatures[ref] = (
            str(fp.GetValue()),
            str(fp.GetFPID().GetLibItemName()),
            tuple(sorted(pins)),
        )
    return signatures


def _schematic_component_signatures(sch, inventory, ctx):
    """Export the current schematic and build the same signature as the PCB.

    A reference-only comparison is insufficient: a board can retain every
    reference while carrying an old value, footprint, or pin-to-net mapping.
    The result is cached because intake also runs ERC on the same schematic.
    """
    key = "_sch_component_signatures::" + os.path.abspath(sch)
    if key in ctx:
        return ctx[key]
    cli = cec_toolchain.kicad_cli()
    if not cli:
        raise RuntimeError("kicad-cli unavailable for exact schematic/PCB sync")
    fd, out = tempfile.mkstemp(prefix="cec_sync_", suffix=".net")
    os.close(fd)
    try:
        proc = subprocess.run(
            [cli, "sch", "export", "netlist", "-o", out, sch],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode:
            raise RuntimeError(
                "netlist export exited %d: %s" %
                (proc.returncode, (proc.stderr or proc.stdout).strip()[:500])
            )
        _components, nets = cec_spice_sanity.parse_netlist(out)
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    pins_by_ref = collections.defaultdict(set)
    for net, nodes in nets.items():
        if not net or str(net).startswith("unconnected-"):
            continue
        for ref, pin in nodes:
            if pin:
                pins_by_ref[ref].add((str(pin), str(net)))
    signatures = {}
    for ref, rec in inventory.items():
        if (_board_only_ref(ref) or
                rec.get("lib_id", "").startswith(("cec-power:", "power:")) or
                not rec.get("on_board", True)):
            continue
        signatures[ref] = (
            str(rec.get("value", "")),
            str(rec.get("footprint", "")).rsplit(":", 1)[-1],
            tuple(sorted(pins_by_ref.get(ref, set()))),
        )
    ctx[key] = signatures
    return signatures


@checker("sch-pcb-sync")
def _chk_sch_pcb_sync(board, path, ctx):
    sch, sch_inventory = _schematic_inventory_for_board(path, ctx)
    if not sch:
        return None, "no sibling .kicad_sch found"
    sch_refs = ({
        ref for ref, rec in sch_inventory.items()
        if (not _board_only_ref(ref)
            and not rec.get("lib_id", "").startswith(("cec-power:", "power:"))
            and rec.get("on_board", True))
    }
                if sch_inventory is not None else _sch_refs(sch))
    if not sch_refs:
        return None, "schematic parsed to 0 instance refs (unexpected format)"
    pcb_by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()
                  if not _board_only_ref(fp.GetReference())}
    pcb_refs = set(pcb_by_ref)
    sch_only = sorted(sch_refs - pcb_refs)
    pcb_only = sorted(pcb_refs - sch_refs)
    state_mismatches = []
    if sch_inventory is not None:
        for ref in sorted(sch_refs & pcb_refs):
            rec = sch_inventory[ref]
            actual_dnp, actual_excluded = _fp_assembly_state(pcb_by_ref[ref])
            expected_dnp = bool(rec.get("dnp"))
            expected_excluded = not bool(rec.get("in_bom", True))
            if actual_dnp != expected_dnp:
                state_mismatches.append(
                    "%s DNP sch=%s pcb=%s" %
                    (ref, "yes" if expected_dnp else "no",
                     "yes" if actual_dnp else "no"))
            if actual_excluded != expected_excluded:
                state_mismatches.append(
                    "%s BOM-excluded sch=%s pcb=%s" %
                    (ref, "yes" if expected_excluded else "no",
                     "yes" if actual_excluded else "no"))
    fresh = ""
    try:
        if os.path.getmtime(sch) > os.path.getmtime(path):
            fresh = "; sch is NEWER than pcb (Update-PCB-from-Schematic may be pending)"
    except OSError:
        pass
    if sch_only or pcb_only or state_mismatches:
        parts = []
        if sch_only:
            parts.append("in sch NOT on pcb (stale board): %s" % ", ".join(sch_only[:10]))
        if pcb_only:
            parts.append("on pcb NOT in sch (orphans): %s" % ", ".join(pcb_only[:10]))
        if state_mismatches:
            parts.append("assembly-state mismatch: %s" %
                         ", ".join(state_mismatches[:10]))
        return False, "; ".join(parts) + fresh
    expected = _schematic_component_signatures(sch, sch_inventory, ctx)
    actual = _pcb_component_signatures(board)
    mismatches = []
    for ref in sorted(expected):
        if ref not in actual:
            continue
        fields = []
        if expected[ref][0] != actual[ref][0]:
            fields.append("value")
        if expected[ref][1] != actual[ref][1]:
            fields.append("footprint")
        if expected[ref][2] != actual[ref][2]:
            fields.append("pad nets")
        if fields:
            mismatches.append("%s(%s)" % (ref, "/".join(fields)))
    if mismatches:
        matched = len(expected) - len(mismatches)
        ratio = matched / float(len(expected)) if expected else 0.0
        return False, (
            "component signatures are stale: %d/%d exact (%.3f); mismatches: %s%s" %
            (matched, len(expected), ratio, ", ".join(mismatches[:10]), fresh)
        )
    return True, "exact value/footprint/pad-net signatures and assembly state in sync (%d refs)%s" % (
        len(pcb_refs), fresh)


# ---------------------------------------------------------------------------
# CL-25 intake gate
# ---------------------------------------------------------------------------
_BENIGN_ERC_TYPES = ("lib_symbol_mismatch", "unconnected_wire_endpoint")


def _erc_errors(sch_path):
    """Run a live ERC (kicad-cli) and return the count of severity-ERROR violations
    excluding the documented-benign types. Missing tools, nonzero exits, and invalid
    output raise so the intake caller can refuse the board explicitly."""
    cli = cec_toolchain.kicad_cli()
    if not cli:
        raise RuntimeError("kicad-cli unavailable")
    fd, out = tempfile.mkstemp(prefix="cec_intake_erc_", suffix=".json")
    os.close(fd)
    try:
        proc = subprocess.run([cli, "sch", "erc", "--format", "json",
                               "-o", out, sch_path], capture_output=True, text=True,
                              timeout=300)
        if proc.returncode:
            raise RuntimeError("kicad-cli ERC exited %d: %s"
                               % (proc.returncode, (proc.stderr or proc.stdout).strip()[:500]))
        with open(out, encoding="utf-8") as f:
            j = json.load(f)
        if not isinstance(j, dict):
            raise ValueError("kicad-cli ERC JSON is not an object")
        sheets = j.get("sheets", []) or [j]
        if (not isinstance(sheets, list)
                or any(not isinstance(sh, dict)
                       or not isinstance(sh.get("violations", []), list)
                       for sh in sheets)):
            raise ValueError("kicad-cli ERC JSON lacks valid violations lists")
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    n = 0
    for sh in sheets:
        for v in sh.get("violations", []):
            if v.get("severity") == "error" and v.get("type") not in _BENIGN_ERC_TYPES:
                n += 1
    return n


def intake_gate(board_path, ctx=None, *, defer_route_geometry=False):
    """CL-25 intake gate: the SCHEMATIC-SIDE subset (sync, ERC freshness, BOM lint,
    netlist assertions). Returns {"ok", "reasons", "results"}; the route loop refuses
    candidate generation on ok=False (override: CEC_SKIP_INTAKE=1). Named reasons only --
    a refusal the owner can act on, never a bare False."""
    ctx = ctx or {}
    try:
        constraint_ir = compiled_constraint_ir()
    except Exception as exc:                              # noqa: BLE001
        detail = "%s: %s" % (type(exc).__name__, exc)
        return {
            "ok": False,
            "reasons": ["constraint-ir [hard]: %s" % detail],
            "results": {"constraint-ir": ("ERROR", detail)},
            "advisory": {"n": 0, "entries": []},
            "constraint_ir": {"schema": 1, "error": detail},
            "board": os.path.basename(board_path),
        }
    board = pcbnew.LoadBoard(board_path)
    by_id = {c.id: c for c in REGISTRY}
    results, reasons, deferred_to_route = {}, [], []
    for cid in INTAKE_CHECKS:
        fn = CHECKERS.get(cid)
        c = by_id.get(cid)
        if not fn or not c:
            detail = "required intake checker is missing from the registry or implementation"
            results[cid] = ("ERROR", detail)
            reasons.append("%s [hard]: %s" % (cid, detail))
            continue
        try:
            res = fn(board, board_path, ctx)
            ok, detail = res[0], res[1]
        except Exception as e:
            ok, detail = None, "%s: %s" % (type(e).__name__, e)
            status = "ERROR"
            results[cid] = (status, detail)
            reasons.append("%s [%s]: %s" % (cid, c.severity, detail))
            continue
        status = "N/A" if ok is None else ("PASS" if ok else "FAIL")
        results[cid] = (status, detail)
        if ok is False:
            reason = "%s [%s]: %s" % (cid, c.severity, detail)
            if defer_route_geometry and cid in ROUTE_REPAIRABLE_INTAKE_CHECKS:
                deferred_to_route.append({
                    "id": cid,
                    "severity": c.severity,
                    "detail": detail,
                    "reason": reason,
                })
            else:
                reasons.append(reason)
    # ERC freshness is a hard intake requirement. A DRAFT marker changes release
    # status, not electrical evidence, so it does not waive ERC.
    # Use the same candidate-aware resolver as sch-pcb-sync/BOM lint.  Looking
    # only beside the PCB rejects every valid ``candidate/`` artifact even
    # after its parent project schematic has already proven an exact match.
    sch = _schematic_for_board(board_path, ctx)
    if sch:
        try:
            n = _erc_errors(sch)
        except Exception as e:
            detail = "%s: %s" % (type(e).__name__, e)
            results["erc"] = ("ERROR", detail)
            reasons.append("erc [hard]: %s" % detail)
        else:
            if n > 0:
                results["erc"] = ("FAIL", "%d ERROR-severity ERC violation(s)" % n)
                reasons.append("erc [hard]: %d ERROR-severity violation(s) on %s"
                               % (n, os.path.basename(sch)))
            else:
                results["erc"] = ("PASS", "0 ERROR-severity violations")
    else:
        results["erc"] = ("ERROR", "no sibling .kicad_sch")
        reasons.append("erc [hard]: no sibling .kicad_sch for %s"
                       % os.path.basename(board_path))
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
            "deferred_to_route": deferred_to_route,
            "advisory": advisory,
            "constraint_ir": constraint_ir.as_dict(include_records=False),
            "board": os.path.basename(board_path)}


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


def _net_cu_thickness_mm(layers, oz_outer, oz_inner,
                         copper_thickness_mm=None):
    """Total copper thickness (mm) a net's copper occupies, summed over the layers it is on
    (F.Cu/B.Cu = oz_outer, inner = oz_inner). The required min width = required_cross / this."""
    if copper_thickness_mm:
        missing = [ln for ln in layers if ln not in copper_thickness_mm]
        if missing:
            raise ValueError("missing modeled copper thickness: %s" % missing)
        t = sum(float(copper_thickness_mm[ln]) for ln in layers)
    else:
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
        need_w = round(need_cross / _net_cu_thickness_mm(
            r["layers"], oz_outer, oz_inner,
            r.get("copper_thickness_mm")), 3)
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
        if os.path.exists(dru):
            with open(dru, encoding="utf-8") as f:
                existing = f.read()
        else:
            existing = "(version 1)\n"
        blocks = ["", "# ENFORCE-LEG (ratify_cross_section): physics-required cross-section on a force-only",
                  "# high-current net, from the cec_dcir DC field solve (j_max=%g A/mm^2)." % d["j_max"]]
        for name, constraint, cond in d["rules"]:
            if ('"%s"' % name) in existing:
                continue
            blocks.append('(rule "%s"\n\t(constraint %s)\n\t(condition "%s"))' % (name, constraint, cond))
            written += 1
        if written:
            with open(dru, "w", encoding="utf-8") as f:
                f.write(existing.rstrip() + "\n" + "\n".join(blocks) + "\n")
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


POST_ROUTE_EXCLUSIONS = frozenset({
    # Intake already proved the authoritative schematic/netlist relationship.
    # Routed artifacts live in build/run directories without a sibling schematic,
    # so re-running this path-based checker here would be a false release failure.
    "sch-pcb-sync",
    # These two rows are future-route reservation authorities.  Their geometry
    # is derived before the final orthogonal pour outline exists and may cover
    # a deliberate hook pocket that contains no fabricated copper.  Final
    # release is instead fail-closed on high-current-pour-integrity,
    # no-incursion-in-laid-pour, current cross-section, and thermal evidence.
    "high-current-corridor-keepout",
    "no-foreign-on-high-current-pour",
})


def blocking_rows(rows, *, phase="post_route"):
    """All ratified, deterministic hard/strong failures for a release phase."""
    excluded = POST_ROUTE_EXCLUSIONS if phase == "post_route" else frozenset()
    return [(c, status, detail, payload) for c, status, detail, payload in rows
            if c.id not in excluded
            and c.status == "ratified"
            and c.checkable == "yes"
            and c.severity in ("hard", "strong")
            and status in ("FAIL", "ERROR")]


def release_gate(board_path, ctx=None, *, phase="post_route"):
    """Fail-closed aggregate gate over every ratified deterministic contract."""
    try:
        constraint_ir = compiled_constraint_ir()
    except Exception as exc:                              # noqa: BLE001
        detail = "%s: %s" % (type(exc).__name__, exc)
        return {
            "ok": False,
            "phase": phase,
            "checked": 0,
            "constraint_ir": {"schema": 1, "error": detail},
            "blockers": [{"id": "constraint-ir", "severity": "hard",
                          "status": "ERROR", "detail": detail}],
        }
    rows = run(board_path, ctx)
    blocked = blocking_rows(rows, phase=phase)
    return {
        "ok": not blocked,
        "phase": phase,
        "checked": len(rows),
        "constraint_ir": constraint_ir.as_dict(include_records=False),
        "blockers": [{"id": c.id, "severity": c.severity,
                      "status": status, "detail": detail}
                     for c, status, detail, _payload in blocked],
    }


def report(board_path, ctx, as_json=False):
    rows = run(board_path, ctx)
    if as_json:
        return {"board": os.path.basename(board_path),
                "constraint_ir": compiled_constraint_ir().as_dict(
                    include_records=False),
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
    strict = "--strict" in argv
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
    strict_rc = 0
    for b in boards:
        if as_json:
            blobs.append(report(b, ctx, as_json=True))
        else:
            report(b, ctx)
            print()
        if strict:
            gate = release_gate(b, ctx, phase="post_route")
            strict_rc = strict_rc or (0 if gate["ok"] else 1)
            if not as_json:
                print("STRICT RELEASE :: %s -> %s (%d blocker(s))" %
                      (os.path.basename(b), "PASS" if gate["ok"] else "FAIL",
                       len(gate["blockers"])))
                for blocker in gate["blockers"][:16]:
                    print("  [%s] %-32s %s" %
                          (blocker["status"][0], blocker["id"],
                           str(blocker["detail"])[:100]))
            else:
                blobs[-1]["strict_release"] = gate
    if as_json:
        print(json.dumps(blobs, indent=1))
    return strict_rc


def laid_pour_incursion_summary(board_path, *, exclude_plane=True,
                                item_limit=60):
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
    board = pcbnew.LoadBoard(board_path) if isinstance(board_path, str) else board_path
    plane_role_layers = set()
    if exclude_plane:
        declared_profile = cec_fab.board_profile_name(board)
        if declared_profile:
            roles = dict(zip(cec_fab.COPPER_LAYERS,
                             cec_fab.get_profile(declared_profile)["roles"]))
            # Exact plane roles only. SIG/PWR outer layers remain eligible because they carry
            # segmented routing pours, while dedicated GND and PWR layers are board planes.
            plane_role_layers = {layer for layer, role in roles.items()
                                 if role in ("GND", "PWR")}
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
            canonical_layer = cec_fab.COPPER_LAYER_IDS.get(int(lid), board.GetLayerName(lid))
            if exclude_plane and canonical_layer in plane_role_layers:
                continue
            outline = z.Outline()
            if outline.OutlineCount() > 0:
                zones.append((net, lid, name, outline))
    if not zones:
        return {"applicable": False, "status": "na", "n_parts": 0, "n_tracks": 0,
                "n_vias": 0, "items": []}
    items, n_parts, n_tracks, n_vias = [], 0, 0, 0
    for net, lid, name, outline in zones:
        for fp in board.GetFootprints():
            for pd in fp.Pads():
                if not pd.IsOnLayer(lid) or pd.GetNetname() == net:
                    continue
                if outline.Collide(pd.GetEffectiveShape(lid), 0):
                    n_parts += 1
                    items.append({"kind": "pad", "pour": name,
                                  "ref": fp.GetReference(), "net": pd.GetNetname()})
        for t in board.GetTracks():
            if t.GetNetname() == net:
                continue
            if t.GetClass() == "PCB_TRACK" and t.GetLayer() == lid:
                # Use KiCad's actual copper shape, including the real track width. The previous
                # centerline-only test missed a wide track whose edge cut into the reserved pour.
                if outline.Collide(t.GetEffectiveShape(lid), 0):
                    n_tracks += 1
                    items.append({
                        "kind": "track", "pour": name,
                        "pour_net": net, "net": t.GetNetname(),
                        "uuid": t.m_Uuid.AsString(),
                        "layer": board.GetLayerName(lid),
                        "locked": bool(t.IsLocked()),
                    })
            elif t.GetClass() == "PCB_VIA" and t.IsOnLayer(lid):
                # GetEffectiveShape reads the actual layer-specific via diameter. Do not assume a
                # fixed 0.9 mm via when POFV profiles deliberately use other dimensions.
                if outline.Collide(t.GetEffectiveShape(lid), 0):
                    n_vias += 1
                    items.append({
                        "kind": "via", "pour": name,
                        "pour_net": net, "net": t.GetNetname(),
                        "uuid": t.m_Uuid.AsString(),
                        "layer": board.GetLayerName(lid),
                        "locked": bool(t.IsLocked()),
                    })
    visible = items if item_limit is None else items[:int(item_limit)]
    return {"applicable": True, "status": "ok", "n_parts": n_parts,
            "n_tracks": n_tracks, "n_vias": n_vias, "items": visible}


@checker("no-incursion-in-laid-pour")
def _chk_laid_pour_incursion(board, path, ctx):
    """Owner ruling 2026-07-25: nothing is ever placed inside a pour. The pour is
    set first; a placement that cannot work without encroaching sends the POURS
    back to be redone, never the rule bent. See laid_pour_incursion_summary."""
    rep = laid_pour_incursion_summary(path)
    if not rep.get("applicable"):
        return None, "no reserved laid signal/power pour on this board"
    if rep.get("status") == "error":
        return False, "laid-pour analysis error: %s" % rep.get("error", "unknown")
    out = ["%s %s [%s] inside pour %s"
           % (it["kind"], it.get("ref", ""), it.get("net", ""), it["pour"])
           for it in rep["items"]]
    if out:
        return (False, "; ".join(out[:12]),
                [{"type": "separate", "target": it.get("ref") or it.get("net"),
                  "from": it["pour"]} for it in rep["items"][:12]])
    return True, "no parts, foreign tracks, or vias inside laid reserved pours"


if __name__ == "__main__":
    sys.exit(main())
