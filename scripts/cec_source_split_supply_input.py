"""Two existing short input arms, not a new neckdown or current split.

This internal compiler helper may identify a manufacturer power-input land
which is literally the middle of two independently bounded Source chains.
Both fixed full-current carriers remain and BOTH reconstruction demands
carry the unchanged WHOLE rail requirement. It neither rewrites Source nor
qualifies inherited thin copper. A one-arm input keeps its historical owner.
"""
import pcbnew
import cec_force_current as force
import cec_route_quality as quality
import cec_source_ground_leaf as source


def _polygon(item, face, *, outside):
    result = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(result, face, 0, 1,
        pcbnew.ERROR_OUTSIDE if outside else pcbnew.ERROR_INSIDE)
    if not result.OutlineCount():
        raise ValueError('split_input_actual_native_metal_required')
    return result


def chains(board, pad, new, incident, *, authority, contract, source_floor,
           allow_locked, deadline):
    """Return two separate positive cuts, or None outside this exact type.

    The enclosing owner MUST have just freshly proved the complete native,
    exported, embedded-symbol and manufacturer identity. No public request
    can supply this authority or a current/length/width override.
    """
    source._tick(deadline)
    if authority.get('scope') != 'fresh_source_manufacturer_power_input':
        return None
    roots = [t for t in incident if t.GetClass() == 'PCB_TRACK'
        and t.GetParentGroup() is not None and 0 < t.GetWidth() <= 350000]
    if len(roots) != 2:
        return None
    common = set((tuple(roots[0].GetStart()), tuple(roots[0].GetEnd()))) & set(
        (tuple(roots[1].GetStart()), tuple(roots[1].GetEnd())))
    common = {at for at in common if pad.HitTest(pcbnew.VECTOR2I(*at), 0)}
    if len(common) != 1:
        return None
    root = next(iter(common)); face = int(pad.GetParentFootprint().GetLayer())
    groups = list(board.Groups()); tracks = list(board.GetTracks())
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    zones = [z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(tracks) + len(pads) + len(zones) > 16384:
        raise ValueError('split_input_native_inventory_bound')
    selected_groups = {force._uid(g): g for g in groups
        if any(g.ContainsItem(t) for t in roots)}
    if len(selected_groups) != 1:
        raise ValueError('split_input_one_actual_Source_group_required')
    group = next(iter(selected_groups.values())); members = list(group.GetItems())
    if (group.GetName() != 'CEC_LOCAL_ENDPOINT_NECKDOWN' or group.IsLocked()
            or group.GetParentGroup() is not None or not 1 <= len(members) <= 512
            or any(t.GetClass() != 'PCB_TRACK' for t in members)):
        raise ValueError('split_input_plain_existing_endpoint_group_required')
    cohort = {force._uid(t): t for t in members if t.GetNetCode() == pad.GetNetCode()
        and int(t.GetLayer()) == face and 0 < t.GetWidth() <= 350000}
    full, gap = source_floor(roots[0])
    if type(full) is not int or type(gap) is not int or full <= 0 or gap < 0:
        raise ValueError('split_input_literal_Source_dimensions_required')
    if (face not in contract['required_by_layer_nm']
            or type(contract['required_by_layer_nm'][face]) is not int
            or contract['required_by_layer_nm'][face] <= 0):
        raise ValueError('split_input_unchanged_whole_current_face_required')
    width = max(full, contract['required_by_layer_nm'][face])
    # Walk from the physical land only as far as the FIRST retained literal
    # full-width endpoint. A grouped thin overshoot beyond that carrier is
    # retained Source copper, never a reason to expand the cut/length bound.
    adjacency = {}
    for uid, t in cohort.items():
        a, b = tuple(t.GetStart()), tuple(t.GetEnd())
        adjacency.setdefault(a, []).append((b, uid))
        adjacency.setdefault(b, []).append((a, uid))
    if len(adjacency.get(root, [])) != 2:
        raise ValueError('split_input_exactly_two_Source_land_departures_required')
    arms = []; chosen = {}
    for following, first in adjacency[root]:
        walked = []; previous, at, incoming = root, following, first
        seen = {root}
        while True:
            source._tick(deadline)
            if at in seen or incoming in walked:
                raise ValueError('split_input_each_arm_must_be_acyclic')
            seen.add(at); walked.append(incoming)
            if (len(walked) > 4
                    or sum(cohort[uid].GetLength() for uid in walked) > 1500000):
                raise ValueError('split_input_each_original_short_chain_bound_required')
            fixed = [t for t in tracks if t.GetClass() == 'PCB_TRACK'
                and force._uid(t) not in cohort and t.GetNetCode() == pad.GetNetCode()
                and int(t.GetLayer()) == face and t.GetWidth() >= width
                and at in (tuple(t.GetStart()), tuple(t.GetEnd()))]
            if fixed:
                if (not 1 <= len(fixed) <= 4 or pad.HitTest(pcbnew.VECTOR2I(*at), 0)
                        or new.HitTest(pcbnew.VECTOR2I(*at), 0)):
                    raise ValueError('split_input_two_fixed_external_full_current_throats_required')
                arms.append(dict(ids=sorted(walked), throat=at,
                    carriers=sorted(force._uid(t) for t in fixed)))
                chosen.update((uid, cohort[uid]) for uid in walked)
                break
            steps = [(other, uid) for other, uid in adjacency.get(at, []) if uid != incoming]
            if len(steps) != 1:
                raise ValueError('split_input_unbranched_arm_to_first_fixed_carrier_required')
            other, uid = steps[0]; previous, at, incoming = at, other, uid
    for uid, t in chosen.items():
        source._tick(deadline)
        a, b = tuple(t.GetStart()), tuple(t.GetEnd())
        if (t.HasSolderMask() or t.GetWidth() < board.GetDesignSettings().m_TrackMinWidth
                or t.IsLocked() and not allow_locked or t.GetLength() <= 0
                or not quality.is_canonical_stroke(a, b, tolerance_nm=0)
                or [force._uid(g) for g in groups if g.ContainsItem(t)] != [force._uid(group)]):
            raise ValueError('split_input_plain_canonical_uniquely_grouped_edges_required')
    if (set(arms[0]['ids']) & set(arms[1]['ids'])
            or set().union(*(set(q['ids']) for q in arms)) != set(chosen)):
        raise ValueError('split_input_complete_disjoint_arm_inventory_required')
    if any(source_floor(t) != (full, gap) for t in chosen.values()):
        raise ValueError('split_input_one_literal_Source_dimension_contract_required')
    fixed_ids = {uid for arm in arms for uid in arm['carriers']}
    if (arms[0]['throat'] == arms[1]['throat']
            or set(arms[0]['carriers']) & set(arms[1]['carriers'])):
        raise ValueError('split_input_distinct_fixed_full_current_ports_required')
    # The arms may meet ONLY in the actual original pad metal. A native
    # crossing or side contact away from that land is not a two-arm owner.
    aperture = _polygon(pad, face, outside=False)
    for uid in arms[0]['ids']:
        for other in arms[1]['ids']:
            source._tick(deadline)
            if not chosen[uid].GetEffectiveShape(face).Collide(
                    chosen[other].GetEffectiveShape(face), 0):
                continue
            overlap = _polygon(chosen[uid], face, outside=True)
            overlap.BooleanIntersection(_polygon(chosen[other], face, outside=True))
            overlap.BooleanSubtract(aperture)
            if overlap.OutlineCount():
                raise ValueError('split_input_arms_touch_outside_actual_Source_land')
    # Other Source tracks may physically overlap the departing arms ONLY
    # inside unchanged full-current carrier metal (or the owned root land).
    # Thus a short retained overshoot is not accidentally retired, while an
    # interior side tap outside actual retained metal still fails closed.
    retained_aperture = pcbnew.SHAPE_POLY_SET(aperture)
    body = pcbnew.SHAPE_POLY_SET()
    for t in chosen.values():
        body.BooleanAdd(_polygon(t, face, outside=True))
    for t in tracks:
        if force._uid(t) in fixed_ids:
            retained_aperture.BooleanAdd(_polygon(t, face, outside=False))
    retained_contacts = set()
    for t in chosen.values():
        source._tick(deadline); shape = t.GetEffectiveShape(face)
        if any(force._uid(p) != force._uid(pad) and p.IsOnLayer(face)
                and shape.Collide(p.GetEffectiveShape(face), 0) for p in pads):
            raise ValueError('split_input_unowned_land_contact')
        for peer in tracks:
            if (force._uid(peer) in set(chosen) | fixed_ids or not peer.IsOnLayer(face)
                    or not shape.Collide(peer.GetEffectiveShape(face), 0)):
                continue
            if (peer.GetClass() != 'PCB_TRACK' or peer.GetNetCode() != pad.GetNetCode()
                    or peer.HasSolderMask()):
                raise ValueError('split_input_unowned_conductor_contact')
            overlap = _polygon(peer, face, outside=True)
            overlap.BooleanIntersection(body); overlap.BooleanSubtract(retained_aperture)
            if overlap.OutlineCount():
                raise ValueError('split_input_retained_contact_outside_actual_full_current_metal')
            retained_contacts.add(force._uid(peer))
        for zone in zones:
            if not zone.IsOnLayer(face):
                continue
            if not zone.IsFilled():
                raise ValueError('split_input_unknown_surface_fill')
            if (zone.HasFilledPolysForLayer(face)
                    and zone.GetFilledPolysList(face).Collide(shape, 0)):
                raise ValueError('split_input_surface_pour_contact_not_owned')
    all_ids = sorted(chosen)
    summary = dict(kind='two_Source_short_input_arms_two_fixed_full_current_ports',
        pad_uuid=force._uid(pad), source_common_land_point_nm=list(root),
        source_group_uuid=force._uid(group), complete_retired_track_uuids=all_ids,
        complete_retained_carrier_uuids=sorted(fixed_ids),
        other_retained_contact_uuids=sorted(retained_contacts),
        first_literal_full_current_junctions_only=True,
        other_contacts_remain_inside_actual_retained_full_current_metal=True,
        per_arm_original_limits=dict(maximum_edges=4, maximum_length_nm=1500000),
        both_replacements_carry_whole_rail_current=True, current_sharing_assumed=False,
        inherited_thin_copper_not_qualified=True, release_authority=False)
    remaining = sorted(force._uid(t) for t in members if force._uid(t) not in chosen)
    result = []
    for arm in sorted(arms, key=lambda q: q['ids']):
        result.append(dict(kind='source_supply_pad_contact_lead_restoration',
            retired_track_uuids=arm['ids'], pad_uuid=force._uid(pad), net=pad.GetNetname(),
            layer_id=face, retained_throat_nm=list(arm['throat']),
            retained_throat_track_uuids=arm['carriers'], source_group_uuid=force._uid(group),
            remaining_group_members=remaining,
            source_edges=[dict(uuid=uid, source_nm=[list(chosen[uid].GetStart()),
                list(chosen[uid].GetEnd())], width_nm=chosen[uid].GetWidth(),
                locked=bool(chosen[uid].IsLocked())) for uid in arm['ids']],
            source_width_nm=min(chosen[uid].GetWidth() for uid in arm['ids']),
            source_authority=authority, source_split_supply_input=summary,
            unchanged_full_rail_current_contract=contract, width_nm=width, clearance_nm=gap,
            old_oversized_neckdown_not_qualified=True, new_thin_allowance=False,
            new_prefix_requires_independent_whole_current_receiving=True,
            saved_candidate_authorized=False))
    source._tick(deadline)
    return result
