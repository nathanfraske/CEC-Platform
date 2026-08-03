#!/usr/bin/env python3
"""Electrical and physical contract for the segmented Hub/24-pin mezzanine."""

SEGMENTS = (
    {
        # Canonical coordinates are the ATX face.  These seats are the smallest
        # jointly stable, mechanically balanced result of the real-courtyard,
        # through-barrel-aware search across three placements per side.
        "ref": "J6P", "dc": (-30.0, 22.0), "rot": 90.0,
        "pin_roles": {1: "5V", 2: "GND", 3: "5V", 4: "GND",
                      5: "5V", 6: "GND"},
        "footprint_token": "2X03_P2.54MM",
    },
    {
        # R4 rail-clear seat (2026-08-03): the jointly legal -30mm row put a
        # J6C GND barrel directly on the ATX 3V3 forced sink band at y=17.6mm.
        # Moving the shared support row 5mm inward clears all four force rails
        # while retaining zero pad/courtyard violations on both stack members.
        "ref": "J6C", "dc": (25.0, -25.0), "rot": 90.0,
        "pin_roles": {1: "GND", 2: "GND", 3: "CAN_H", 4: "NC",
                      5: "CAN_L", 6: "NC", 7: "GND", 8: "GND"},
        "footprint_token": "2X04_P2.54MM",
    },
    {
        "ref": "J6D", "dc": (25.0, 22.0), "rot": 90.0,
        "pin_roles": {1: "DETECT", 2: "GND", 3: "NC", 4: "GND"},
        "footprint_token": "2X02_P2.54MM",
    },
)

GROUND_LUG = {
    "ref": "H1",
    # X-mirror of J6C: the upper support pair is symmetric while the three
    # differently sized electrical fields remain intentionally keyed.
    "dc": (-25.0, -25.0),
    "footprint": "cec-MountingHole:MountingHole_2.7mm_M2.5_Pad_Via",
    "net": "GND",
    "function": "inter-board-ground-lug",
    "electrical_role": "supplemental-ground-bond",
    "population": "fit",
    "contact": "conductive-fastener-on-exposed-copper",
    "drill_mm": 2.7,
    "land_mm": 5.0,
}

# Mechanical stack contract.  The Hub's component face points toward the ATX
# board.  An 18 mm hard standoff therefore leaves 4 mm nominal clearance over
# the approximately 14 mm RJ-45 body.  TSW lead style -17 supplies a 15.74 mm
# mating post (series print), avoiding the marginal engagement of -07/-08 at
# this board separation.
STACK = {
    "board_gap_mm": 18.0,
    "inward_component_height_mm": 14.0,
    "nominal_height_margin_mm": 4.0,
    "hub_outline_mm": (86.0, 74.0),
    "atx_outline_mm": (86.0, 95.0),
    # The 95 mm carrier is the analytical access floor, not a placer grow.
    # Shifting the 74 mm Hub 0.7 mm toward the output side leaves 9.8 mm above
    # and 11.2 mm below.  Each connector courtyard therefore sits fully
    # outside the Hub silhouette with 0.25 mm beyond the 1.2 mm planar guard.
    "atx_top_access_band_mm": 9.8,
    "atx_bottom_access_band_mm": 11.2,
    "atx_planar_guard_mm": 1.2,
    "atx_top_header_inboard_reach_mm": 8.35,
    "atx_bottom_header_inboard_reach_mm": 9.75,
    # Both stack members share an X/center datum.  The taller carrier exposes
    # its 24-pin input/output bands; the Hub's left-edge RJ-45 mouths reflect to
    # assembly-right while USB-C and debug controls remain edge-accessible.
    "hub_assembly_dc_mm": (0.0, -0.7),
    "header_family": "TSW-10x-17-G-D",
    "socket_family": "SSQ-10x-03-G-D",
    "standoff_mpn": "R25-1001802",
    "standoff_thread": "M2.5",
    "screw_mpn": "MP006553",
    "screw_size": "M2.5x6mm",
}
