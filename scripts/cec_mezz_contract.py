#!/usr/bin/env python3
"""Electrical and physical contract for the segmented Hub/24-pin mezzanine."""

SEGMENTS = (
    {
        "ref": "J6P", "dc": (31.2, -1.2), "rot": 0.0,
        "pin_roles": {1: "5V", 2: "GND", 3: "5V", 4: "GND",
                      5: "5V", 6: "GND"},
        "footprint_token": "2X03_P2.54MM",
    },
    {
        "ref": "J6C", "dc": (11.2, -12.2), "rot": 90.0,
        "pin_roles": {1: "GND", 2: "GND", 3: "CAN_H", 4: "NC",
                      5: "CAN_L", 6: "NC", 7: "GND", 8: "GND"},
        "footprint_token": "2X04_P2.54MM",
    },
    {
        "ref": "J6D", "dc": (30.2, -11.2), "rot": 0.0,
        "pin_roles": {1: "DETECT", 2: "GND", 3: "NC", 4: "GND"},
        "footprint_token": "2X02_P2.54MM",
    },
)

GROUND_LUG = {
    "ref": "H1",
    "dc": (-20.0, 14.0),
    "footprint": "cec-MountingHole:MountingHole_2.2mm_M2_Pad_Via",
    "net": "GND",
    "function": "inter-board-ground-lug",
    "electrical_role": "supplemental-ground-bond",
    "population": "fit",
    "contact": "conductive-fastener-on-exposed-copper",
    "drill_mm": 2.2,
    "land_mm": 4.4,
}
