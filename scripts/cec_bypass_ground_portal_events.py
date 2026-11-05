"""Supply-bounded capacitor seats around literal saved Ground entries.

These are read-only placement proposals, not via placement or process
authority.  The ordinary supply-centred menu can miss the only usable
barrel corridor beneath a power bus.  Offer exact existing-reference-root
events as well, retaining the source footprint displacement, 3.5 mm supply
assignment and .8 mm octilinear return budgets.  Live courtyards, surface
copper, fabrication and joint return receiving still decide every seat.
"""
import math
import time

import pcbnew
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_ground_return_shortcut as ground


def events(board, cap, supply, source_cap, *, max_shift_mm, deadline,
           max_sites=16, reach_mm=.8):
    """Return one finite current-orientation menu without changing any item."""
    if (type(max_shift_mm) not in (int, float) or not math.isfinite(max_shift_mm)
            or not 0 < max_shift_mm <= 32
            or type(deadline) not in (int, float) or not math.isfinite(deadline)
            or type(max_sites) is not int or not 1 <= max_sites <= 64
            or type(reach_mm) not in (int, float) or not math.isfinite(reach_mm)
            or not 0 < reach_mm <= .8):
        raise ValueError('bounded_native_bypass_ground_portal_events_required')
    result = dict(sites=[], source_reference_portals=0, complete=True,
        deadline_exhausted=False, read_only=True, no_path_proof=False,
        routing_admitted=False, release_authority=False,
        existing_barrel_not_new_hole_or_fabrication_permission=True)
    if time.monotonic() >= deadline:
        result.update(complete=False, deadline_exhausted=True)
        return result
    pads = list(cap.Pads())
    ground_pads = [p for p in pads if p.GetNetname() == 'GND']
    supply_pads = [p for p in pads if p.GetNetname() == supply.GetNetname()]
    if (len(pads) != 2 or len(ground_pads) != 1 or len(supply_pads) != 1
            or supply.GetNetname() == 'GND' or supply.GetNetCode() <= 0
            or force._uid(cap) != force._uid(source_cap) or cap.IsFlipped() != source_cap.IsFlipped()
            or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD for p in pads)):
        raise ValueError('one_literal_two_surface_land_selected_bypass_required')
    gnd, rail = ground_pads[0], supply_pads[0]
    face = cells.cec_return_escape.smd_surface_layer(gnd)
    if face not in (pcbnew.F_Cu, pcbnew.B_Cu) or not rail.IsOnLayer(face):
        raise ValueError('one_actual_bypass_surface_required')
    tracks = list(board.GetTracks())
    if len(tracks) > 16384 or len(list(board.Zones())) > 2048:
        raise ValueError('native_ground_portal_event_inventory_bound')
    at, gp, rp, sp = [tuple(p.GetPosition()) for p in (cap, gnd, rail, supply)]
    old = tuple(source_cap.GetPosition())
    rail_offset = tuple(rp[i] - gp[i] for i in (0, 1))
    # An event outside this radius cannot meet both unchanged budgets.
    radius = 3500000 + reach_mm * 1e6 + math.dist(gp, rp)
    portals = []
    for via in tracks:
        if time.monotonic() >= deadline:
            result.update(complete=False, deadline_exhausted=True)
            break
        if (via.GetClass() != 'PCB_VIA' or via.GetNetname() != 'GND'
                or via.GetNetCode() != gnd.GetNetCode()
                or via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
                or not via.IsOnLayer(face) or math.dist(tuple(via.GetPosition()), sp) > radius):
            continue
        try:
            contacts = ground._reference_contacts(board, via)
        except ValueError:
            # No actual saved reference contact is not a placement root.
            # It also is not evidence that the whole region has no path.
            continue
        portals.append((math.dist(tuple(via.GetPosition()), sp), force._uid(via), via, contacts))
    portals.sort(key=lambda p: (p[0], p[1]))
    result['source_reference_portals'] = len(portals)
    menus = []
    for _, uid, via, contacts in portals:
        if time.monotonic() >= deadline:
            result.update(complete=False, deadline_exhausted=True)
            break
        end = tuple(via.GetPosition())
        diameter = via.GetWidth(face)
        bb = gnd.GetBoundingBox()
        half_x, half_y = bb.GetWidth()/2, bb.GetHeight()/2
        offsets = {(0, 0)}
        # Offer the exact native via/land tangency events too: a .6 mm
        # barrel cannot simply be centred inside a narrower 0402 land.
        # The .01 mm offset is a proposal separation, not a process waiver.
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tangent = diameter/2 + (half_x if dx else half_y) + 10000
            for distance in (tangent, 700000, reach_mm*1e6):
                if 0 < distance <= reach_mm*1e6:
                    offsets.add((round(dx*distance), round(dy*distance)))
        for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            for radius_nm in (600000, reach_mm*1e6):
                delta = round(radius_nm / math.sqrt(2))
                offsets.add((dx*delta, dy*delta))
        menu = []
        for ox, oy in sorted(offsets):
            target_ground = (end[0]+ox, end[1]+oy)
            path_mm = (max(abs(ox), abs(oy)) +
                       (math.sqrt(2)-1)*min(abs(ox), abs(oy))) / 1e6
            target_origin = tuple(at[i]+target_ground[i]-gp[i] for i in (0, 1))
            target_supply = tuple(target_ground[i]+rail_offset[i] for i in (0, 1))
            supply_mm = math.dist(target_supply, sp) / 1e6
            if (path_mm > reach_mm+1e-9 or supply_mm > 3.5
                    or math.dist(target_origin, old) > max_shift_mm*1e6):
                continue
            menu.append(dict(supply_distance_mm=supply_mm,
                position_nm=list(target_origin), orientation_deg=cap.GetOrientationDegrees(),
                ground_nm=list(target_ground), target_via_uuid=uid,
                target_via_nm=list(end), octilinear_return_upper_bound_mm=path_mm,
                actual_saved_reference_contacts=contacts))
        menu.sort(key=lambda r: (r['supply_distance_mm'],
            r['octilinear_return_upper_bound_mm'], r['position_nm']))
        if menu:
            menus.append(menu)
    # Do not spend every slot on the first barrel while another real
    # reference corridor never gets a proposal.  Receiving remains joint.
    seen = set()
    for ordinal in range(max((len(m) for m in menus), default=0)):
        for menu in menus:
            if ordinal >= len(menu):
                continue
            row = menu[ordinal]
            key = (*row['position_nm'], row['orientation_deg'])
            if key in seen:
                continue
            seen.add(key)
            result['sites'].append(row)
            if len(result['sites']) == max_sites:
                return result
    return result
