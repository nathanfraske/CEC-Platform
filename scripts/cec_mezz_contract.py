#!/usr/bin/env python3
"""Electrical and physical contract for the segmented Hub/24-pin mezzanine."""

def local_contacts(segment):
    """Canonical header-side numbering; socket local X is its mirror.

    Pin numbers are project contact identities, not automatically inferred
    nearest neighbours. SSQ PCB layout and KiCad socket handedness were checked.
    """
    return [dict(id=str(pin), xy=[2.54*((pin-1) % 2), 2.54*((pin-1)//2)], role=role)
            for pin, role in sorted(segment["pin_roles"].items())]

SEGMENTS = (
    {
        # Canonical coordinates are the ATX face. Repaired 2026-09-22 from
        # actual numbered contact geometry and joint native clearance replay.
        # These seats do not certify the still-open whole-stack access/height.
        "ref": "J6P", "dc": (-32.066501, 25.168201), "rot": 90.0,
        "pin_roles": {1: "5V", 2: "GND", 3: "5V", 4: "GND",
                      5: "5V", 6: "GND"},
        "footprint_token": "2X03_P2.54MM",
    },
    {
        # Reversing the field direction avoids an RJ45 collision after the
        # correct dead-bug contact reflection. H1 retains the mirrored seat.
        "ref": "J6C", "dc": (25.0, -27.340101), "rot": 270.0,
        "pin_roles": {1: "GND", 2: "GND", 3: "CAN_H", 4: "NC",
                      5: "CAN_L", 6: "NC", 7: "GND", 8: "GND"},
        "footprint_token": "2X04_P2.54MM",
    },
    {
        "ref": "J6D", "dc": (22.989999, 22.0), "rot": 90.0,
        "pin_roles": {1: "DETECT", 2: "GND", 3: "NC", 4: "GND"},
        "footprint_token": "2X02_P2.54MM",
    },
)

GROUND_LUG = {
    "ref": "H1",
    # X-mirror of J6C: the upper support pair is symmetric while the three
    # differently sized electrical fields remain intentionally keyed.
    "dc": (-25.0, -27.340101),
    "footprint": "cec-MountingHole:MountingHole_2.2mm_M2_Pad_Via_Slim_6mm_Hardware",
    "net": "GND",
    "function": "inter-board-ground-lug",
    "electrical_role": "supplemental-ground-bond",
    "population": "fit",
    "contact": "conductive-fastener-on-exposed-copper",
    "drill_mm": 2.2,
    "land_mm": 4.4,
    "hardware_envelope_diameter_mm": 6.0,
    "hardware_envelope_qualified": False,
}

# Mechanical stack contract.  The Hub's component face points toward the ATX
# board. The legacy 18mm spacer over-inserts the -17 mating posts; it is NOT
# qualified. Selected ASB-2022E support is 22+/-0.1mm; LOCAL assembled gap
# still includes seating/bow and requires incoming/first-article verification.
STACK = {
    "board_gap_mm": 22.0,
    # Largest inward body is now the 17mm maximum reservoir, plus a proposed
    # 0.2mm seating allocation. This is not a measured assembly tolerance.
    "inward_component_height_mm": 17.2,
    "nominal_height_margin_mm": 4.8,
    "release_qualified": False,
    "qualification_status": "selected_hardware_and_3d_placement_envelope_first_article_pending",
    # Ratified coordinate datums, NOT measured candidate contours. Native
    # paired CAD study is 84x72.2 Hub / 82x95 ATX; access.evaluate() reads its
    # real recessed contour. Do not use these datum dimensions as the outline.
    "hub_outline_mm": (86.0, 74.0),
    "atx_outline_mm": (86.0, 95.0),
    # Historical 74mm-frame estimates only. These do NOT certify the actual
    # 80mm retained Hub. Keep the datum stable; use actual paired access gates.
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
    "socket_family": "SSQ-10x-01-G-D",
    "standoff_mpn": "ASB-2022E",
    "standoff_thread": "M2",
    "screw_mpn": "SSCF-M2-5-A2",
    "screw_size": "M2x5",
    "retired_hardware": {"standoff_mpn": "R25-1001802", "screw_mpn": "MP006553",
                         "reason": "18mm over-insertion; M2.5 not the target M2 hardware"},
}

# Assembly-side policy belongs with the mating contract, not in the generic
# constraint engine.  The engine selects a role from fitted hardware; only this
# domain file knows which current products populate headers versus sockets.
SIDES = {
    "header": {
        "datum_origin_mm": (0.0, 0.0),
        "mirror_x": False,
        "component_layer": "F.Cu",
        "assembly_dc": (0.0, 0.0),
        "nominal_outline": STACK["atx_outline_mm"],
    },
    "socket": {
        "datum_origin_mm": (0.0, 0.0),
        "mirror_x": True,
        "component_layer": "F.Cu",
        "footprint_mirror_axis": "x",
        "assembly_dc": STACK["hub_assembly_dc_mm"],
        "nominal_outline": STACK["hub_outline_mm"],
    },
}

PRODUCT_SIDE = {
    "atx-24pin-rev3": "header",
    "hub-standard-rev2": "socket",
}


def side_for_path(path):
    """Legacy archive fallback when fitted mating hardware is unavailable."""
    identity = str(path or "").replace("\\", "/").lower()
    match = next((role for product, role in PRODUCT_SIDE.items()
                  if product in identity), None)
    return SIDES.get(match) if match else None


def path_is_stack_member(path):
    identity = str(path or "").replace("\\", "/").lower()
    return any(product in identity for product in PRODUCT_SIDE)


def hardware_release_requirements(board, schematic):
    """Assembly-specific policy consumed by the generic hardware release gate.

    Routing may explore a mechanically valid placement; manufacturing cannot
    silently promote a nominal-only stack. Certification must bind the exact
    pair, not merely a historical connector family or a hand-edited pass flag.
    """
    from pathlib import Path
    if not path_is_stack_member(schematic):
        return []
    root=Path(__file__).resolve().parents[1]
    status_path=root/'docs/hub-atx-stack-qualification-status.json'
    import json
    dependencies=[str(root/'beta/atx-24pin-rev3/assembly-access.json')]
    try:
        declared_pair=json.loads(status_path.read_text()).get('qualified_pair') or {}
        dependencies.extend(str(root/r['path']) for r in declared_pair.values())
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        pass  # evaluate() still refuses missing/malformed certification
    def verify():
        import json,hashlib
        import cec_assembly_access
        status=json.loads(status_path.read_text())
        pair=status.get('qualified_pair') or {}
        if set(pair)!= {'carrier','cover'}:
            return dict(ok=False,reason='exact qualified assembly pair missing')
        paths=[]
        for side in ('carrier','cover'):
            record=pair[side];path=root/record['path']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
                return dict(ok=False,reason='qualified assembly source changed')
            paths.append(path)
        digest=hashlib.sha256(Path(board).read_bytes()).hexdigest()
        if digest not in {r['sha256'] for r in pair.values()}:
            return dict(ok=False,reason='candidate is not a qualified assembly member')
        return cec_assembly_access.evaluate(*paths,json.loads(
            (root/'beta/atx-24pin-rev3/assembly-access.json').read_text()))
    return [dict(id='hub-atx-deadbug-stack',
        footprints=[f'Pin{kind}_2x0{n}_P2.54mm_Vertical'
                    for kind in ('Header','Socket') for n in (2,3,4)],
        status_path=str(status_path),
        candidate_dependencies=dependencies,
        required_gates=['contact_geometry','connector_tolerances','vent_path',
            'hardware','port_access','opposing_bodies','capacitor_eco','physical_fit'],
        verify_candidate=verify)]
