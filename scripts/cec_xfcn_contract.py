#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed contract for the Standard Beta XFCN terminal integration.

This module is deliberately data-first.  The same project/refdes/net/part
contract drives the schematic splice, PCB placement, and CI audit so a later
board cannot silently drift back to the retired blade count or collapse the
per-cable post-shunt rails.

The XFCN assets are prototype assets.  Passing this audit proves that the ECAD
matches the reviewed integration plan; it does *not* waive the incoming-part,
electrical, or owner-ratification release gates.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import cec_pcb_reconcile  # noqa: E402
import cec_sch_gates  # noqa: E402


LIB = "cec-Connector_Screw"
T340 = "XFCN_T34069"
T340_DB = "XFCN_T34069_DB_BoltPad"
TTR = "XFCN_TTR32100127-0600"
TTR_DB = "XFCN_TTR32100127-0600_DB_BoltPad"
ATX_SIGNAL_DB = "SAMTEC_TSW_102_16_G_D_RA"
ATX_SIGNAL_MAIN = "SAMTEC_SSQ_102_03_G_D"

# The prototype uses the plated terminal face itself as the contact member.
# This is intentionally not a generic "bare copper" joint: the PCB land is
# flat ENIG and the terminal face is the manufacturer's tin-plated brass.
# Interposers and copper coins remain absent unless coupon evidence forces a
# separately reviewed contact-system redesign.
CONTACT_INTERFACE = {
    "profile": "DIRECT_TIN_PLATED_BRASS_TO_ENIG_NO_INTERPOSER",
    "copper_finish": "ENIG",
    "interposer": "NONE",
    "copper_coin": "NOT_FITTED",
    "washer_electrical_credit": False,
}

PARTS = {
    T340: {
        "lib_id": f"{LIB}:{T340}",
        "value": "XFCN T34069",
        "footprint": f"{LIB}:XFCN_T34069_THT_M3_40A",
        "manufacturer": "XFCN",
        "mpn": "T34069",
        "lcsc": "C481452",
        "in_bom": True,
        "datasheet": ROOT / "lib/datasheets/XFCN_T34069_C481452.pdf",
    },
    T340_DB: {
        "lib_id": f"{LIB}:{T340_DB}",
        "value": "T34069 DB M3 PAD",
        "footprint": f"{LIB}:XFCN_T34069_Daughterboard_BoltPad_M3_PROVISIONAL",
        "manufacturer": "",
        "mpn": "",
        "lcsc": "",
        "in_bom": False,
        "datasheet": ROOT / "lib/datasheets/XFCN_T34069_C481452.pdf",
    },
    TTR: {
        "lib_id": f"{LIB}:{TTR}",
        "value": "TTR32100127-0600",
        "footprint": f"{LIB}:XFCN_TTR32100127-0600_THT_M3_60A",
        "manufacturer": "XFCN",
        "mpn": "TTR32100127-0600",
        "lcsc": "C45384691",
        "in_bom": True,
        "datasheet": ROOT / "lib/datasheets/XFCN_TTR32100127-0600_C45384691.pdf",
    },
    TTR_DB: {
        "lib_id": f"{LIB}:{TTR_DB}",
        "value": "TTR32100127-0600 DB M3 PAD",
        "footprint": f"{LIB}:XFCN_TTR32100127-0600_Daughterboard_BoltPad_M3_PROVISIONAL",
        "manufacturer": "",
        "mpn": "",
        "lcsc": "",
        "in_bom": False,
        "datasheet": ROOT / "lib/datasheets/XFCN_TTR32100127-0600_C45384691.pdf",
    },
    ATX_SIGNAL_DB: {
        # The schematic symbol remains a logical four-pin connector so the
        # established readable net order is preserved; the exact physical
        # row/column mapping is carried by this vendor-specific footprint.
        "lib_id": "cec:CEC_CONN_1x4",
        "value": "TSW-102-16-G-D-RA",
        "footprint": (
            "cec-Connector_PinHeader_2.54mm:"
            "Samtec_TSW-102-16-G-D-RA_2x02_P2.54mm_Horizontal"),
        "footprint_dir": ROOT / "lib/vendor/Connector_PinHeader_2.54mm.pretty",
        "manufacturer": "Samtec",
        "mpn": "TSW-102-16-G-D-RA",
        "lcsc": "",
        "in_bom": True,
        "datasheet": ROOT / "lib/datasheets/Samtec_TSW_TH.pdf",
        "datasheet_url": "https://suddendocs.samtec.com/catalog_english/tsw_th.pdf",
        "description": (
            "2x2 2.54 mm right-angle male signal header. Lead style -16 gives "
            "8.13 mm mating length, satisfying the documented >=6.4 mm blind-mate "
            "minimum; double-row odd/even-by-column pin geometry."),
        "note": (
            "Mates SSQ-102-03-G-D; 1=-12V, 2=PS_ON#, 3=PWR_OK, 4=GND. "
            "First-article mated-transform and engagement check required."),
    },
    ATX_SIGNAL_MAIN: {
        "lib_id": "cec:CEC_CONN_1x4",
        "value": "SSQ-102-03-G-D",
        "footprint": (
            "cec-Connector_PinSocket_2.54mm:"
            "Samtec_SSQ-102-03-G-D_2x02_P2.54mm_Vertical"),
        "footprint_dir": ROOT / "lib/vendor/Connector_PinSocket_2.54mm.pretty",
        "manufacturer": "Samtec",
        "mpn": "SSQ-102-03-G-D",
        "lcsc": "",
        "in_bom": True,
        "datasheet": ROOT / "lib/datasheets/Samtec_SSQ.pdf",
        "datasheet_url": (
            "https://suddendocs.samtec.com/prints/"
            "ssq-1xx-xx-xxx-x-xx-xxx-xx-x-mkt.pdf"),
        "description": (
            "2x2 2.54 mm vertical female socket, 8.51 mm body and 10.01 mm "
            "lead-style -03 tail; double-row odd/even-by-column pin geometry."),
        "note": (
            "Mates TSW-102-16-G-D-RA; 1=-12V, 2=PS_ON#, 3=PWR_OK, 4=GND. "
            "First-article mated-transform and engagement check required."),
    },
}


def _refs(rows):
    return {ref: {"part": part, "net": net} for ref, part, net in rows}


def project_refs(plan):
    """All physical replacement refs, including non-XFCN companion parts."""
    return {**plan["refs"], **plan.get("aux_refs", {})}


def expectation_nets(expectation):
    if "nets" in expectation:
        return expectation["nets"]
    return {"1": expectation["net"]}


PROJECTS = {
    "atx-main": {
        "kind": "main",
        "root_schematic": "beta/atx-24pin-rev3/24pin-module.kicad_sch",
        "leaf_schematic": "beta/atx-24pin-rev3/01-atx-power-control.kicad_sch",
        "pcb": "beta/atx-24pin-rev3/24pin-module.kicad_pcb",
        "remove_refs": ["TB3", "TB7", "TB8", "TB10"],
        "refs": _refs([
            ("TB1", T340, "/SENSE12V_LO"),
            ("TB2", T340, "+5V_MAIN"),
            ("TB4", T340, "/SENSE3V3_LO"),
            ("TB5", T340, "/SENSE5VSB_LO"),
            ("TB6", TTR, "GND"),
            ("TB9", TTR, "GND"),
        ]),
        "placements_mm": {
            "TB6": (190.0, 74.39, 0), "TB4": (200.5, 74.39, 90),
            "TB2": (208.5, 74.39, 90), "TB1": (216.5, 74.39, 90),
            "TB5": (224.5, 74.39, 90), "TB9": (234.5, 74.39, 0),
            "J_SIG1": (242.295, 81.565, 0),
        },
        "aux_refs": {
            "J_SIG1": {
                "part": ATX_SIGNAL_MAIN,
                "nets": {"1": "/ATX_NEG12V", "2": "/ATX_PSON",
                         "3": "/ATX_PWROK", "4": "GND"},
            },
        },
    },
    "atx-db": {
        "kind": "daughterboard",
        "contact_interface": CONTACT_INTERFACE,
        "root_schematic": "beta/output-daughterboards/atx24-out-db/atx24-out-db-board.kicad_sch",
        "leaf_schematic": "beta/output-daughterboards/atx24-out-db/atx24-out-db-board.kicad_sch",
        "pcb": "beta/output-daughterboards/atx24-out-db/atx24-out-db-board.kicad_pcb",
        # The six legacy OQ-88 sense-return pads were bare, no-net PCB-only
        # provisions.  They did not implement a measurement channel and are
        # retired with the blade interface so they cannot reappear on a
        # regenerated XFCN daughterboard.
        "remove_refs": [
            "J12", "J14", "J17", "J18",
            "SR1", "SR2", "SR3", "SR4", "SR5", "SR6",
        ],
        "refs": _refs([
            ("J10", T340_DB, "+12V"),
            ("J11", T340_DB, "+5V"),
            ("J13", T340_DB, "+3V3"),
            ("J15", T340_DB, "+5VSB"),
            ("J16", TTR_DB, "GND"),
            ("J19", TTR_DB, "GND"),
        ]),
        "placements_mm": {
            "J16": (5.00, 16.50, 0), "J13": (13.35, 18.20, 0),
            "J11": (20.20, 18.20, 0), "J10": (27.05, 18.20, 0),
            "J15": (33.90, 18.20, 0), "J19": (42.25, 16.50, 0),
            "J20": (49.50, 17.40, 0),
        },
        "aux_refs": {
            "J20": {
                "part": ATX_SIGNAL_DB,
                "nets": {"1": "/-12V", "2": "/PS_ON#",
                         "3": "/PWR_OK", "4": "GND"},
            },
        },
        "outline_rect_mm": (0.0, 0.0, 54.0, 21.3),
        # ATX carries five independently high-current domains on four layers.
        # JLCPCB exposes 2 oz internal copper for this exact 4L/1.6 mm/JLC3313
        # construction.  The place step enforces these copper declarations so
        # regeneration cannot silently fall back to 1 oz inner planes.
        "stackup": {
            "profile": "JLCPCB_4L_1P6_JLC3313_2OZ_ALL",
            "copper_mm": {
                "F.Cu": 0.070, "In1.Cu": 0.070,
                "In2.Cu": 0.070, "B.Cu": 0.070,
            },
        },
        "minimum_hole_edge_mm": 0.80,
        # J20's right-angle mating posts deliberately project beyond the
        # daughterboard edge; its four drilled pads remain margin-gated.
        "footprint_outline_exempt_refs": ["J20"],
        # The original field left no legal top-edge routing channel once both
        # the 0.5 mm board-edge and 0.25 mm pad clearances were applied.  A
        # 0.35 mm downward move opens a real, DRC-clean escape channel without
        # increasing the outline or reducing the lower high-current corridor.
        "preserved_moves_mm": {"J1": (4.10, 3.10, 0)},
        "routes_mm": [
            {"net": "/-12V", "layer": "F.Cu", "width": 0.20,
             "points": [(8.30, 8.60), (10.40, 6.50), (10.40, 0.65),
                        (53.20, 0.65), (53.20, 14.00), (48.00, 14.00),
                        (48.00, 15.90), (49.50, 17.40)]},
            {"net": "/PS_ON#", "layer": "B.Cu", "width": 0.20,
             "points": [(16.70, 8.60), (18.80, 6.50), (18.80, 0.65),
                        (52.80, 0.65), (52.80, 14.00), (47.80, 14.00),
                        (47.80, 19.94), (49.50, 19.94)]},
            # PWR_OK is a low-speed status line.  Keeping its route at the
            # extreme top/right edge of In2 makes only an edge notch in the
            # +12V plane; it no longer cuts any power pour across its flow.
            {"net": "/PWR_OK", "layer": "In2.Cu", "width": 0.20,
             "points": [(33.50, 3.10), (35.60, 0.65), (52.80, 0.65),
                        (52.80, 15.80), (52.04, 17.40)]},
            {"net": "+5VSB", "layer": "F.Cu", "width": 0.90,
             "points": [(37.70, 3.10), (39.80, 5.40), (39.80, 10.30)]},
            {"net": "+5VSB", "layer": "In1.Cu", "width": 1.00,
             "points": [(39.80, 10.30), (39.80, 11.20), (35.80, 11.20)]},
            {"net": "+5VSB", "layer": "In1.Cu", "width": 2.00,
             "points": [(35.80, 11.20), (35.00, 13.50)]},
            {"net": "+5VSB", "layer": "B.Cu", "width": 2.00,
             "points": [(35.00, 13.50), (35.00, 16.20)]},
            # Join the F.Cu east limb to the B.Cu main pour and carry the
            # isolated right-edge +3V3 field pin around the +5VSB corridor.
            {"net": "+3V3", "layer": "B.Cu", "width": 0.50,
             "points": [(50.30, 3.10), (48.20, 5.85), (35.00, 5.85)]},
        ],
        "vias_mm": [
            {"net": "+5VSB", "at": (39.80, 10.30),
             "diameter": 1.00, "drill": 0.50},
            {"net": "+5VSB", "at": (35.00, 13.50),
             "diameter": 1.00, "drill": 0.50},
            # Join the legacy +3V3 front/back pours in their shared clear
            # region.  A via-only tie is intentional here; both filled zones
            # provide the current-spreading copper on either side.
            {"net": "+3V3", "at": (51.50, 5.50),
             "diameter": 1.00, "drill": 0.50},
        ],
        "remove_vias_mm": [
            (50.26, 11.00), (58.00, 15.00),
            (36.15, 13.45), (54.00, 12.00), (54.00, 8.00),
            (39.00, 10.40), (39.80, 9.80), (40.50, 9.80),
            (47.00, 12.70), (53.80, 7.00),
        ],
        "remove_track_segments_mm": [
            ((47.00, 12.70), (48.50, 12.70)),
        ],
        "replace_track_nets": ["/-12V", "/PS_ON#", "/PWR_OK",
                               "+5VSB", "+5V", "+3V3"],
    },
    "eps-main": {
        "kind": "main",
        "root_schematic": "beta/eps-8pin-rev3/eps-8pin-rev3.kicad_sch",
        "leaf_schematic": "beta/eps-8pin-rev3/04-cable-power.kicad_sch",
        "pcb": "beta/eps-8pin-rev3/eps-8pin-rev3.kicad_pcb",
        "remove_refs": ["J_OUT1", "J_OUT2"],
        "refs": _refs([
            ("TB11", T340, "/SENSEC1_LO"), ("TB12", T340, "/SENSEC1_LO"),
            ("TB13", T340, "GND"), ("TB14", T340, "GND"),
            ("TB21", T340, "/SENSEC2_LO"), ("TB22", T340, "/SENSEC2_LO"),
            ("TB23", T340, "GND"), ("TB24", T340, "GND"),
        ]),
        "placements_mm": {
            "TB13": (30.0, 35.5, 270), "TB11": (37.75, 35.5, 270),
            "TB12": (45.5, 35.5, 270), "TB14": (53.25, 35.5, 270),
            "TB23": (61.0, 35.5, 270), "TB21": (68.75, 35.5, 270),
            "TB22": (76.5, 35.5, 270), "TB24": (84.25, 35.5, 270),
        },
        "interface_body_overlap_allowance_mm": 0.55,
        "edge_overhang_allowance_mm": 2.30,
        "preserved_moves_mm": {
            "H2": (14.4, 37.0, 0),
            "R8": (87.1804, 28.5, 90),
            "R9": (85.6389, 28.5, 90),
        },
    },
    "eps-db": {
        "kind": "daughterboard",
        "contact_interface": CONTACT_INTERFACE,
        "root_schematic": "beta/output-daughterboards/eps-out-db/eps-out-db-board.kicad_sch",
        "leaf_schematic": "beta/output-daughterboards/eps-out-db/eps-out-db-board.kicad_sch",
        "pcb": "beta/output-daughterboards/eps-out-db/eps-out-db-board.kicad_pcb",
        "remove_refs": ["J12", "J15"],
        "refs": _refs([
            ("J10", T340_DB, "GND"), ("J11", T340_DB, "GND"),
            ("J13", T340_DB, "+12V"), ("J14", T340_DB, "+12V"),
        ]),
        "placements_mm": {
            "J10": (3.5, 15.4, 0), "J13": (10.5, 15.4, 0),
            "J14": (17.5, 15.4, 0), "J11": (24.5, 15.4, 0),
        },
        # Rectangle is the finished Edge.Cuts datum, not its stroked KiCad
        # bounding box.  The row retains 0.5 mm copper-to-side-edge, 0.6 mm
        # copper-to-top-edge, >=0.45 mm courtyard separation, and >=1.4 mm
        # M3-hole-to-edge material after drill radius.
        "outline_rect_mm": (0.0, 0.0, 28.0, 18.5),
        "minimum_hole_edge_mm": 0.80,
        "preserved_moves_mm": {"J1": (7.7, 2.75, 0), "LOGO1": (2.5, 5.0, 0)},
    },
    "pcie2-main": {
        "kind": "main",
        "root_schematic": "beta/pcie-8pin-2port/pcie8pin-2port-module.kicad_sch",
        "leaf_schematic": "beta/pcie-8pin-2port/06-cable-power.kicad_sch",
        "pcb": "beta/pcie-8pin-2port/candidate/pcie-8pin-2port-candidate.kicad_pcb",
        "remove_refs": ["TB12", "TB14", "TB15", "TB16", "TB22", "TB24", "TB25", "TB26"],
        "refs": _refs([
            ("TB11", TTR, "/SENSEC1_LO"), ("TB13", TTR, "GND"),
            ("TB21", TTR, "/SENSEC2_LO"), ("TB23", TTR, "GND"),
        ]),
        # One mechanically identical two-terminal group per cable. Keep each
        # force/return pair compact and symmetric (14 mm M3-axis pitch) while
        # giving adjacent cable groups a slightly wider 15 mm routing throat.
        # The measured 10.59 mm courtyards retain 3.41 mm within a pair and
        # 4.41 mm between the two inner terminals. The matching daughterboard
        # datum below is derived from this same 14 mm interface contract.
        "terminal_pair_pitch_mm": 14.0,
        "terminal_inter_pair_pitch_mm": 15.0,
        "terminal_groups": [
            {"force_ref": "TB11", "return_ref": "TB13",
             "shunt_ref": "RS1", "return_side": -1},
            {"force_ref": "TB21", "return_ref": "TB23",
             "shunt_ref": "RS2", "return_side": 1},
        ],
        "managed_pour_nets": [
            "/SENSEC1_HI", "/SENSEC1_LO",
            "/SENSEC2_HI", "/SENSEC2_LO",
        ],
        # Placement authority owns only the terminal datum. Routed-object
        # pours are compiled and reserved from the complete placement; never
        # preserve or recreate pre-route bounding-box slabs in this source.
        "managed_pour_source": "pipeline",
        "fixed_power_path_placements_mm": {
            # Preserve a real high-current escape channel between the two
            # connector bodies. The prior 0.53 mm body gap became a complete
            # wall after an 8.6 mm, clearance-aware +12 V lane was expanded.
            # This spreads the inputs inside the existing outline while the
            # bolt-terminal row below remains compact and symmetric.
            "J_IN1": (23.7012, 1.8311, 180),
            "J_IN2": (50.5988, 1.8311, 180),
            "RS1": (30.9012, 23.8, -90),
            "RS2": (51.7988, 23.8, -90),
        },
        "placements_mm": {
            "TB13": (20.00, 42.55, 0), "TB11": (34.00, 42.55, 0),
            "TB21": (49.00, 42.55, 0), "TB23": (63.00, 42.55, 0),
        },
    },
    "pcie3-main": {
        "kind": "main",
        "root_schematic": "beta/pcie-8pin-3port/pcie8pin-3port-module.kicad_sch",
        "leaf_schematic": "beta/pcie-8pin-3port/06-cable-power.kicad_sch",
        "pcb": "beta/pcie-8pin-3port/candidate/pcie-8pin-3port-candidate.kicad_pcb",
        "remove_refs": [
            "TB12", "TB14", "TB15", "TB16", "TB22", "TB24", "TB25", "TB26",
            "TB32", "TB34", "TB35", "TB36",
        ],
        "refs": _refs([
            ("TB11", TTR, "/SENSEC1_LO"), ("TB13", TTR, "GND"),
            ("TB21", TTR, "/SENSEC2_LO"), ("TB23", TTR, "GND"),
            ("TB31", TTR, "/SENSEC3_LO"), ("TB33", TTR, "GND"),
        ]),
        "terminal_pair_pitch_mm": 14.0,
        "terminal_inter_pair_pitch_mm": 15.0,
        "terminal_groups": [
            {"force_ref": "TB11", "return_ref": "TB13",
             "shunt_ref": "RS1", "return_side": 1},
            {"force_ref": "TB21", "return_ref": "TB23",
             "shunt_ref": "RS2", "return_side": 1},
            {"force_ref": "TB31", "return_ref": "TB33",
             "shunt_ref": "RS3", "return_side": 1},
        ],
        "managed_pour_nets": [
            "/SENSEC1_HI", "/SENSEC1_LO",
            "/SENSEC2_HI", "/SENSEC2_LO",
            "/SENSEC3_HI", "/SENSEC3_LO",
        ],
        "managed_pour_source": "pipeline",
        "fixed_power_path_placements_mm": {
            # Match the two-port current-escape rule: adjacent connector
            # bodies retain >=6 mm for the margin-sized outer-layer lanes.
            "J_IN1": (18.7524, 1.8, 180),
            "J_IN2": (45.65, 1.8, 180),
            "J_IN3": (72.5476, 1.8, 180),
            "RS1": (19.85, 29.8, -90),
            "RS2": (49.85, 29.8, -90),
            "RS3": (79.85, 29.8, -90),
        },
        "placements_mm": {
            "TB11": (15.75, 54.55, 0), "TB13": (29.75, 54.55, 0),
            "TB21": (44.75, 54.55, 0), "TB23": (58.75, 54.55, 0),
            "TB31": (73.75, 54.55, 0), "TB33": (87.75, 54.55, 0),
        },
    },
    "pcie-db": {
        "kind": "daughterboard",
        "contact_interface": CONTACT_INTERFACE,
        "root_schematic": "beta/output-daughterboards/pcie-out-db/pcie-out-db-board.kicad_sch",
        "leaf_schematic": "beta/output-daughterboards/pcie-out-db/pcie-out-db-board.kicad_sch",
        "pcb": "beta/output-daughterboards/pcie-out-db/pcie-out-db-board.kicad_pcb",
        "remove_refs": ["J11", "J12", "J14", "J15"],
        "refs": _refs([( "J10", TTR_DB, "+12V"), ("J13", TTR_DB, "GND")]),
        "placements_mm": {"J10": (5.25, 15.5, 0), "J13": (19.25, 15.5, 0)},
        # The two 9 x 8 mm bolt pads keep 0.75 mm side copper margin and a
        # large central tool/copper corridor.  Height is already constrained
        # by the connector courtyard plus the washer/contact pad.
        "outline_rect_mm": (0.0, 0.0, 24.5, 20.0),
        "minimum_hole_edge_mm": 0.80,
        "preserved_moves_mm": {"J1": (7.45, 2.75, 0)},
    },
}


def power_path_anchor_placements(plan):
    """One synthesis anchor map for the whole header-to-terminal current cell."""
    return {
        **plan.get("fixed_power_path_placements_mm", {}),
        **plan.get("placements_mm", {}),
    }


def centered_interface_anchor_placements(plan, outline_width_mm, *,
                                         terminal_edge_y_mm):
    """Translate a qualified interface macro into a fresh board frame.

    Contract placements are often authored in an existing PCB coordinate
    frame.  Their relative terminal spacing, auxiliary-header offset, and
    rotations are mechanical authority; the absolute origin is not.  Center
    the complete macro on the requested outline and place the minimum rotated
    *pad-copper* edge of the primary terminal row at the declared edge datum
    without rescaling or repacking any member.  Footprint origins are not
    mechanical edge datums: a rotated terminal can extend several millimetres
    past its origin even when the origin itself appears to be on the board.
    """
    placements = power_path_anchor_placements(plan)
    if not placements:
        return {}
    primary = [ref for ref in plan.get("refs", {}) if ref in placements]
    if not primary:
        raise ValueError("qualified interface macro has no primary terminals")
    try:
        width = float(outline_width_mm)
        edge_y = float(terminal_edge_y_mm)
    except (TypeError, ValueError) as exc:
        raise ValueError("interface target frame must be numeric") from exc
    if not math.isfinite(width) or width <= 0.0 or not math.isfinite(edge_y):
        raise ValueError("interface target frame must be finite and positive")
    xs = [float(row[0]) for row in placements.values()]
    # Bind the board-edge datum to real electrical copper.  This is computed
    # from the same qualified footprint geometry used by synthesis; per-part
    # magic offsets would become stale as soon as a footprint were revised.
    import cec_pcb

    primary_copper_y = []
    for ref in primary:
        part_key = plan["refs"][ref]["part"]
        footprint = PARTS[part_key]["footprint"]
        rotation = float(placements[ref][2])
        boxes = cec_pcb.local_pad_boxes(footprint)
        if not boxes:
            raise ValueError(
                "qualified interface terminal %s has no electrical pad copper"
                % ref)
        rotated_y = []
        for x0, y0, x1, y1 in boxes:
            for lx, ly in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                _dx, dy_pad = cec_pcb._rot(lx, ly, rotation)
                rotated_y.append(float(dy_pad))
        primary_copper_y.append(
            float(placements[ref][1]) + min(rotated_y))
    dx = width / 2.0 - (min(xs) + max(xs)) / 2.0
    dy = edge_y - min(primary_copper_y)
    return {
        ref: (float(row[0]) + dx, float(row[1]) + dy, float(row[2]))
        for ref, row in placements.items()
    }


QUALIFICATION_STATUS = ROOT / "docs/standard-xfcn-terminal-qualification-status.json"
REQUIRED_GATES = (
    "owner_ratification",
    "incoming_t34069_measurements",
    "incoming_ttr32100127_0600_measurements",
    "computational_electrothermal_screen",
    "representative_coupon_electrical_test",
    "fastener_and_torque_release",
    "contact_interface_finish_release",
    "jlc_tht_process_confirmation",
)


def project_path(project, key):
    return ROOT / PROJECTS[project][key]


def expected_source_refs():
    return {ref for plan in PROJECTS.values() for ref in project_refs(plan)}


def _ref_nets(root_schematic):
    result = {}
    for members, net in cec_pcb_reconcile.netlist_groups(str(root_schematic)).items():
        for ref, pin in members:
            result[(ref, str(pin))] = net
    return result


def audit_project(name):
    plan = PROJECTS[name]
    root_sch = ROOT / plan["root_schematic"]
    findings = []
    if not root_sch.is_file():
        return [f"{name}: missing root schematic {root_sch}"]
    inventory = cec_sch_gates.inventory(str(root_sch))
    nets = _ref_nets(root_sch)
    for ref, expectation in project_refs(plan).items():
        part = PARTS[expectation["part"]]
        row = inventory.get(ref)
        if not row:
            findings.append(f"{name}: missing {ref}")
            continue
        for field, actual, expected in (
            ("lib_id", row["lib_id"], part["lib_id"]),
            ("value", row["value"], part["value"]),
            ("footprint", row["footprint"], part["footprint"]),
            ("in_bom", row["in_bom"], part["in_bom"]),
            ("Manufacturer", row["props"].get("Manufacturer", ""), part["manufacturer"]),
            ("MPN", row["props"].get("MPN", ""), part["mpn"]),
            ("LCSC", row["props"].get("LCSC", ""), part["lcsc"]),
        ):
            if actual != expected:
                findings.append(f"{name}: {ref} {field}={actual!r}, expected {expected!r}")
        for pin, expected_net in expectation_nets(expectation).items():
            actual_net = nets.get((ref, pin))
            # A local label in a nested hierarchical sheet is exported with its
            # full sheet path.  The electrical contract is the terminal leaf name;
            # never require a human-facing sheet title to remain frozen forever.
            net_matches = (
                actual_net == expected_net or
                (expected_net.startswith("/") and actual_net is not None and
                 actual_net.endswith(expected_net)))
            if not net_matches:
                findings.append(
                    f"{name}: {ref}.{pin} net={actual_net!r}, expected {expected_net!r}")
    for ref in plan["remove_refs"]:
        if ref in inventory:
            findings.append(f"{name}: retired interface reference {ref} remains in source")
    return findings


def audit_release_gate():
    findings = []
    if not QUALIFICATION_STATUS.is_file():
        return [f"missing qualification status {QUALIFICATION_STATUS}"]
    status = json.loads(QUALIFICATION_STATUS.read_text(encoding="utf-8"))
    gates = status.get("gates", {})
    for gate in REQUIRED_GATES:
        if gate not in gates:
            findings.append(f"qualification status omits gate {gate}")
    if status.get("release_status") not in {"PROTOTYPE_BLOCKED", "QUALIFIED"}:
        findings.append("qualification status has an unknown release_status")
    if status.get("release_status") == "QUALIFIED" and not all(
            gates.get(gate, {}).get("passed") is True for gate in REQUIRED_GATES):
        findings.append("release marked QUALIFIED without every mandatory gate passing")
    return findings


def audit_daughterboard_solid_power_connections():
    """Require solid, never thermal-relief, copper at every XFCN bolt land.

    This is deliberately checked from KiCad's parsed zone/pad semantics instead
    of trusting comments or searching the serialized text.  A future refill or
    footprint replacement must therefore preserve the high-current contact rule.
    """
    try:
        import pcbnew
    except ImportError:
        return ["cannot verify XFCN solid pad-to-pour connections without pcbnew"]
    full = int(pcbnew.ZONE_CONNECTION_FULL)
    inherited = int(pcbnew.ZONE_CONNECTION_INHERITED)
    findings = []
    for name, plan in PROJECTS.items():
        if plan["kind"] != "daughterboard":
            continue
        board = pcbnew.LoadBoard(str(ROOT / plan["pcb"]))
        zones_by_net = {}
        for zone in board.Zones():
            zones_by_net.setdefault(zone.GetNetname(), []).append(zone)
        footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
        for ref, expectation in plan["refs"].items():
            if expectation["part"] not in {T340_DB, TTR_DB}:
                continue
            net = expectation["net"]
            zones = zones_by_net.get(net, [])
            if not zones:
                findings.append(f"{name}: {ref}/{net} has no power zone")
                continue
            for zone in zones:
                if int(zone.GetPadConnection()) != full:
                    findings.append(
                        f"{name}: {ref}/{net} zone uses non-solid pad connection")
            footprint = footprints.get(ref)
            if footprint is None:
                findings.append(f"{name}: missing PCB footprint {ref}")
                continue
            for pad in footprint.Pads():
                local = int(pad.GetLocalZoneConnection())
                if local not in {inherited, full}:
                    findings.append(
                        f"{name}: {ref}.{pad.GetNumber()} locally overrides solid "
                        "zone connection")
    return findings


def audit_daughterboard_contact_interfaces():
    """Fail closed on finish, mask exposure, and forbidden interposers.

    The flat terminal face must meet the exposed land directly.  Requiring the
    board metadata and the actual pad layer set prevents a regenerated board
    from retaining the right footprint name while masking one contact face or
    reverting the board finish.
    """
    try:
        import pcbnew
    except ImportError:
        return ["cannot verify XFCN contact interface without pcbnew"]

    findings = []
    property_keys = {
        "CEC_XFCN_CONTACT_INTERFACE": CONTACT_INTERFACE["profile"],
        "CEC_XFCN_CONTACT_INTERPOSER": CONTACT_INTERFACE["interposer"],
        "CEC_XFCN_COPPER_COIN": CONTACT_INTERFACE["copper_coin"],
    }
    required_layers = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.F_Mask, pcbnew.B_Mask)
    forbidden_layers = (pcbnew.F_Paste, pcbnew.B_Paste)

    for name, plan in PROJECTS.items():
        interface = plan.get("contact_interface")
        if not interface:
            continue
        pcb_path = ROOT / plan["pcb"]
        text = pcb_path.read_text(encoding="utf-8")
        finish_token = f'(copper_finish "{interface["copper_finish"]}")'
        if finish_token not in text:
            findings.append(
                f"{name}: copper finish is not {interface['copper_finish']}")
        for key, value in property_keys.items():
            if f'(property "{key}" "{value}")' not in text:
                findings.append(f"{name}: missing board property {key}={value}")

        board = pcbnew.LoadBoard(str(pcb_path))
        footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
        for ref, expectation in plan["refs"].items():
            if expectation["part"] not in {T340_DB, TTR_DB}:
                continue
            footprint = footprints.get(ref)
            if footprint is None:
                findings.append(f"{name}: missing PCB footprint {ref}")
                continue
            pads = list(footprint.Pads())
            if len(pads) != 1:
                findings.append(
                    f"{name}: {ref} contact land has {len(pads)} pads, expected one")
                continue
            layers = pads[0].GetLayerSet()
            for layer in required_layers:
                if not layers.Contains(layer):
                    findings.append(
                        f"{name}: {ref} contact land omits {board.GetLayerName(layer)}")
            for layer in forbidden_layers:
                if layers.Contains(layer):
                    findings.append(
                        f"{name}: {ref} contact land incorrectly includes "
                        f"{board.GetLayerName(layer)}")
    return findings


def audit_all(projects=None):
    findings = []
    for part in PARTS.values():
        if not Path(part["datasheet"]).is_file():
            findings.append(f"missing local source drawing {part['datasheet']}")
    for name in projects or PROJECTS:
        findings.extend(audit_project(name))
    findings.extend(audit_daughterboard_solid_power_connections())
    findings.extend(audit_daughterboard_contact_interfaces())
    findings.extend(audit_release_gate())
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", choices=sorted(PROJECTS))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    findings = audit_all(args.project)
    payload = {
        "status": "PASS" if not findings else "FAIL",
        "release_status": json.loads(QUALIFICATION_STATUS.read_text()).get(
            "release_status", "MISSING") if QUALIFICATION_STATUS.is_file() else "MISSING",
        "projects": args.project or list(PROJECTS),
        "findings": findings,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"xfcn_contract={payload['status']}")
        print(f"release_status={payload['release_status']}")
        for finding in findings:
            print(f"FAIL: {finding}")
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
