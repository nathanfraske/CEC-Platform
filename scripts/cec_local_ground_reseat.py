"""Bounded reconstruction of ordinary local ground portals in PRIVATE boards.

This constructor is useful when a declared component ECO crowds an existing
return via. It does not authorize that ECO, select a part, change a current
budget, qualify a return loop or admit a candidate. Saved native DRC, exact
source receiving and component/source parity are still mandatory.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

import pcbnew


def _ids(values, name, limit):
    if (type(values) not in (list, tuple, set, frozenset) or not 1 <= len(values) <= limit
            or any(type(value) is not str or not value for value in values)
            or len(set(values)) != len(values)):
        raise ValueError('bounded_literal_' + name + '_required')
    return set(values)


def _number(value, name, low, high):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not low <= value <= high):
        raise ValueError('bounded_' + name + '_required')
    return float(value)


def _uid(item):
    return str(item.m_Uuid.AsString())


def _via_state(via):
    return (str(via.GetNetname()), via.GetNetCode(), via.GetViaType(),
            via.TopLayer(), via.BottomLayer(), via.GetDrillValue(),
            tuple((int(layer), via.GetWidth(layer)) for layer in via.GetLayerSet().CuStack()),
            via.IsLocked())


def _construct(board, *, via_uuids, owner_pad_uuids, project,
               max_shift_mm=1., reach_mm=1.5, minimum_clearance_mm=0.,
               timeout_s=10., max_trials=160):
    import cec_decoupler_cell as cells
    import cec_fab_profile as fab
    import cec_fr as fr
    import cec_route_dimensions as dimensions

    via_ids = _ids(via_uuids, 'ground_portal_inventory', 8)
    pad_ids = _ids(owner_pad_uuids, 'ground_owner_pad_inventory', 32)
    shift = _number(max_shift_mm, 'local_portal_motion', .05, 1.)
    reach = _number(reach_mm, 'immediate_return_reach', .05, 1.5)
    floor = _number(minimum_clearance_mm, 'portal_clearance', 0., 1.)
    lease = _number(timeout_s, 'portal_search_deadline', .001, 10.)
    if (type(max_trials) is not int or not 1 <= max_trials <= 320
            or type(project) is not str or not project):
        raise ValueError('bounded_source_project_and_trials_required')
    deadline = time.monotonic() + lease
    spec = fr._project_netclass_resolver(project)('GND')
    authority = (spec or {}).get('dimension_contract') or {}
    authority_path = Path(authority['source']) if authority.get('source') else None
    if (not spec or not spec.get('track_width') or authority.get('schema') != 1
            or authority.get('role') != 'branch' or authority_path is None
            or authority_path.suffix != '.kicad_pro' or not authority_path.is_file()):
        raise ValueError('explicit_ground_branch_dimension_authority_required')
    branch = dimensions.compile_spec(spec, limits=dimensions.board_limits(board), role='branch')
    width = pcbnew.FromMM(float(branch['track_width']))
    gap = pcbnew.FromMM(max(floor, float(spec.get('clearance') or 0),
                          board.GetDesignSettings().m_MinClearance / 1e6))
    tracks = {_uid(t): t for t in board.GetTracks()}
    pads = {_uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    if not via_ids <= tracks.keys() or not pad_ids <= pads.keys():
        raise ValueError('literal_live_ground_items_required')
    owners = [pads[uid] for uid in sorted(pad_ids)]
    if (len({_uid(p.GetParentFootprint()) for p in owners}) != 1
            or any(p.GetNetname() != 'GND' or p.GetNetCode() <= 0
                   or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD for p in owners)):
        raise ValueError('one_literal_surface_ground_owner_required')
    codes = {p.GetNetCode() for p in owners}
    if len(codes) != 1:
        raise ValueError('single_ground_net_identity_required')
    grouped = {_uid(item) for group in board.Groups() for item in group.GetItems()}
    # Preflight every item before changing ANY geometry. A process exception
    # or an owned native allocation cannot silently inherit this ordinary tier.
    states = {}
    for uid in sorted(via_ids):
        via = tracks[uid]
        if (via.GetClass() != 'PCB_VIA' or via.GetNetname() != 'GND'
                or via.GetNetCode() not in codes or uid in grouped
                or via.GetViaType() != pcbnew.VIATYPE_THROUGH
                or via.TopLayer() != pcbnew.F_Cu or via.BottomLayer() != pcbnew.B_Cu
                or len({via.GetWidth(layer) for layer in board.GetEnabledLayers().CuStack()}) != 1):
            raise ValueError('ungrouped_uniform_ordinary_ground_barrel_required')
        diameter, drill, _ = fab.board_legal_through_via_geometry(
            board, via.GetWidth(via.TopLayer())/1e6, via.GetDrillValue()/1e6)
        if (pcbnew.FromMM(diameter) != via.GetWidth(via.TopLayer())
                or pcbnew.FromMM(drill) != via.GetDrillValue()):
            raise ValueError('ordinary_ground_barrel_below_board_floor')
        if min(math.dist(list(via.GetPosition()), list(p.GetPosition())) for p in owners) > reach*1e6:
            raise ValueError('source_ground_portal_is_not_local_to_declared_owner')
        states[uid] = _via_state(via)

    original_tracks = [t for t in tracks.values()
        if t.GetClass() == 'PCB_TRACK' and t.GetNetname() == 'GND'
        and t.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu)]
    result = dict(schema=1, operation='bounded_ordinary_local_ground_reseat',
        ok=False, complete=False, release_authority=False, routing_admitted=False,
        component_substitution_qualified=False, return_loop_qualified=False,
        scope=dict(via_uuids=sorted(via_ids), owner_pad_uuids=sorted(pad_ids)),
        branch_width_mm=width/1e6, clearance_mm=gap/1e6,
        max_shift_mm=shift, reach_mm=reach, max_trials=max_trials,
        moved_vias=[], created_tracks=[], trials=0, stop=None)
    radii = [r for r in (.05, .1, .15, .2, .25, .3, .35, .4, .45, .5,
                         .6, .7, .8, .9, 1.) if r <= shift + 1e-12]
    for uid in sorted(via_ids):
        via = tracks[uid]
        original = tuple(via.GetPosition())
        accepted = False
        for distance in radii:
            for angle in range(0, 360, 45):
                if time.monotonic() >= deadline or result['trials'] >= max_trials:
                    result['stop'] = 'bounded_search_exhausted'
                    return result
                result['trials'] += 1
                radians = math.radians(angle)
                at = pcbnew.VECTOR2I(round(original[0]+distance*1e6*math.cos(radians)),
                                    round(original[1]+distance*1e6*math.sin(radians)))
                if min(math.dist(list(at), list(p.GetPosition())) for p in owners) > reach*1e6:
                    continue
                via.SetPosition(at)
                valid = (fr._via_spot_clear(board, at, via.GetWidth(via.TopLayer()), gap, codes,
                    drill_nm=via.GetDrillValue(), net_code=via.GetNetCode(),
                    existing_via_uuid=uid) and cells._hole_to_hole_clear(
                    board, at, via.GetDrillValue()/1e6, ignore_via_uuids={uid})[0])
                if not valid:
                    via.SetPosition(pcbnew.VECTOR2I(*original))
                    continue
                # Native area contact, not centre distance, determines whether
                # an old trace already reaches the moved barrel.
                connected = any(t.GetEffectiveShape(t.GetLayer()).Collide(
                    via.GetEffectiveShape(t.GetLayer()), 0) for t in original_tracks)
                bridge = None
                if not connected:
                    anchors = [(pcbnew.VECTOR2I(*original), t.GetLayer(), max(width, t.GetWidth())) for t in original_tracks
                        if t.GetEffectiveShape(t.GetLayer()).Collide(pcbnew.VECTOR2I(*original), 0)]
                    anchors += [(p.GetPosition(), p.GetLayer(), width) for p in owners]
                    # Only axis/45-degree new copper. A non-octilinear owner
                    # chord is not silently treated as a tiny acceptable bend.
                    for start, layer, bridge_width in anchors:
                        dx, dy = abs(start.x-at.x), abs(start.y-at.y)
                        if dx and dy and dx != dy:
                            continue
                        if (fr._tap_foreign_clear(board, start, at, bridge_width, layer, gap, codes)
                                and fr._edge_leg_clear(board, start, at, bridge_width//2)
                                and fr._tap_pair_overlap_clear(board, start, at,
                                    bridge_width, layer, via.GetNetCode(), set())):
                            bridge = pcbnew.PCB_TRACK(board)
                            bridge.SetStart(start); bridge.SetEnd(at)
                            bridge.SetWidth(bridge_width); bridge.SetLayer(layer)
                            bridge.SetNetCode(via.GetNetCode()); bridge.SetLocked(via.IsLocked())
                            break
                    if bridge is None:
                        via.SetPosition(pcbnew.VECTOR2I(*original))
                        continue
                    board.Add(bridge)
                    result['created_tracks'].append(_uid(bridge))
                assert _via_state(via) == states[uid], 'ground_barrel_attributes_changed'
                result['moved_vias'].append(dict(uuid=uid, before_nm=list(original),
                    after_nm=list(at), shift_mm=distance, bridge_uuid=_uid(bridge) if bridge else None))
                accepted = True
                break
            if accepted: break
        if not accepted:
            result['stop'] = 'no_legal_local_portal_in_finite_menu'
            return result
    result.update(ok=True, complete=True, stop='constructed_requires_independent_saved_receiving')
    return result


def construct(board, **kwargs):
    """Transactional native constructor. Any refusal restores the input exactly.

    All added objects are discarded natively and original via poses restored
    on a failed menu/deadline or exception. It never writes a source file.
    """
    from cec_native_items import discard_items
    before = {_uid(item): item for item in board.GetTracks()}
    positions = {uid: tuple(item.GetPosition()) for uid, item in before.items()
                 if item.GetClass() == 'PCB_VIA'}
    def restore():
        discard_items(board, [item for item in board.GetTracks() if _uid(item) not in before])
        for uid, position in positions.items():
            before[uid].SetPosition(pcbnew.VECTOR2I(*position))
    try:
        result = _construct(board, **kwargs)
        if not result['ok']:
            restore()
            result['rolled_back'] = True
        else:
            result['rolled_back'] = False
        return result
    except BaseException:
        restore()
        raise
