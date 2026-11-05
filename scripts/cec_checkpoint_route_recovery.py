"""Recover bounded route proposals from electrically compatible checkpoints.

The current board, not the donor, owns parts, dimensions, rules and ratings.
Only complete planar source chains between independently identified live
native terminals may be proposed. No donor pose, via, zone, rule, ownership
group or inferred THT transition is imported. Saved receiving is mandatory.
"""
from collections import defaultdict, Counter
import math
import time


def chains(rows, anchors, *, max_items=8192, max_chains=1024):
    """Pure exact endpoint-chain extraction; not connectivity authority."""
    if not isinstance(rows, (list, tuple)) or len(rows) > max_items:
        raise ValueError('bounded_donor_track_inventory_required')
    if not isinstance(anchors, (set, frozenset, dict)) or len(anchors) > 32768:
        raise ValueError('bounded_exact_anchor_inventory_required')
    adjacency = defaultdict(list)
    by_id = {}
    for row in rows:
        uid = row.get('uuid')
        net, layer = row.get('net'), row.get('layer')
        points = [row.get('start_nm'), row.get('end_nm')]
        if (not isinstance(uid, str) or not uid or uid in by_id
                or not isinstance(net, str) or not net or type(layer) is not int
                or any(not isinstance(p, (tuple, list)) or len(p) != 2
                    or any(type(v) is not int or abs(v) > 2_000_000_000 for v in p) for p in points)
                or points[0] == points[1] or type(row.get('width_nm')) is not int
                or row['width_nm'] <= 0):
            raise ValueError('exact_unique_donor_track_required')
        keys = [(net, layer, *point) for point in points]
        by_id[uid] = (row, keys)
        for key in keys:
            adjacency[key].append(uid)
    visited = set()
    output = []
    # Native mapped anchors terminate a chain even when degree is two.
    stops = sorted(k for k in adjacency if k in anchors or len(adjacency[k]) != 2)
    for start in stops:
        for seed in sorted(adjacency[start]):
            if seed in visited:
                continue
            point, edge = start, seed
            members, points = [], [start[-2:]]
            while edge not in visited:
                visited.add(edge)
                row, keys = by_id[edge]
                members.append(row)
                point = keys[1] if keys[0] == point else keys[0]
                points.append(point[-2:])
                if point in anchors or len(adjacency[point]) != 2:
                    break
                edge = next(uid for uid in adjacency[point] if uid != edge)
            if start in anchors and point in anchors and start != point:
                if len(output) >= max_chains:
                    raise ValueError('donor_complete_chain_bound')
                output.append(dict(net=start[0], layer=start[1], points_nm=points,
                    rows=members, anchor_keys=[start, point]))
    return output


def rigid_path(points, first, last):
    """Exact quarter-turn/translation fit. No scaling or deformation."""
    if len(points) < 2:
        raise ValueError('nondegenerate_donor_path_required')
    a, z = points[0], points[-1]
    delta = (z[0]-a[0], z[1]-a[1])
    target = (last[0]-first[0], last[1]-first[1])
    rotations = (lambda p: p, lambda p: (-p[1], p[0]),
                 lambda p: (-p[0], -p[1]), lambda p: (p[1], -p[0]))
    for turn, rotate in enumerate(rotations):
        if rotate(delta) != target:
            continue
        origin = rotate(a)
        shift = (first[0]-origin[0], first[1]-origin[1])
        result = [tuple(v+s for v, s in zip(rotate(p), shift)) for p in points]
        if result[0] != tuple(first) or result[-1] != tuple(last):
            raise ValueError('native_rigid_path_replay_mismatch')
        return result, dict(quarter_turns=turn, shift_nm=list(shift))
    return None, None


def _uid(item):
    return str(item.m_Uuid.AsString())


def _native_anchors(donor, board, deadline):
    """Map exact physical endpoints through matching native identities."""
    import pcbnew
    old_fp = {_uid(fp): fp for fp in donor.GetFootprints()}
    new_fp = {_uid(fp): fp for fp in board.GetFootprints()}
    if old_fp.keys() != new_fp.keys():
        raise ValueError('checkpoint_component_population_changed')
    mapped = defaultdict(list)
    def add(net, layer, old, current, item):
        if (not net or board.GetNetcodeFromNetname(net) <= 0 or not item.IsOnLayer(layer)
                or not item.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*current), 0)):
            return
        mapped[(net, int(layer), *old)].append((tuple(current), item))
    for uid, fp in old_fp.items():
        if time.monotonic() >= deadline:
            raise ValueError('checkpoint_anchor_deadline')
        target = new_fp[uid]
        if (fp.GetReference() != target.GetReference() or fp.GetFPIDAsString() != target.GetFPIDAsString()
                or fp.GetValue() != target.GetValue() or fp.IsDNP() != target.IsDNP()):
            raise ValueError('checkpoint_part_identity_changed')
        old_pads = {_uid(p): p for p in fp.Pads()}
        new_pads = {_uid(p): p for p in target.Pads()}
        if old_pads.keys() != new_pads.keys():
            raise ValueError('checkpoint_terminal_population_changed')
        for puid, pad in old_pads.items():
            child = new_pads[puid]
            signature = lambda p: (p.GetNumber(), p.GetNetname(), p.GetAttribute(), p.GetShape(),
                tuple(p.GetSize()), tuple(p.GetDrillSize()), p.GetPinType(), tuple(p.GetLayerSet().CuStack()))
            if signature(pad) != signature(child):
                raise ValueError('checkpoint_land_or_electrical_role_changed')
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            for layer in pad.GetLayerSet().CuStack():
                add(str(pad.GetNetname()), layer, tuple(pad.GetPosition()), tuple(child.GetPosition()), child)
    native = {_uid(t): t for t in board.GetTracks()}
    for prior in donor.GetTracks():
        if time.monotonic() >= deadline:
            raise ValueError('checkpoint_anchor_deadline')
        child = native.get(_uid(prior))
        if child is None or child.GetClass() != prior.GetClass() or child.GetNetname() != prior.GetNetname():
            continue
        if prior.GetClass() == 'PCB_VIA':
            if (child.GetViaType() != prior.GetViaType() or child.GetDrillValue() != prior.GetDrillValue()
                    or tuple(child.GetLayerSet().CuStack()) != tuple(prior.GetLayerSet().CuStack())):
                continue
            for layer in prior.GetLayerSet().CuStack():
                add(str(prior.GetNetname()), layer, tuple(prior.GetPosition()), tuple(child.GetPosition()), child)
        elif prior.GetClass() == 'PCB_TRACK' and (prior.GetLayer() == child.GetLayer()
                and tuple(prior.GetStart()) == tuple(child.GetStart())
                and tuple(prior.GetEnd()) == tuple(child.GetEnd()) and prior.GetWidth() == child.GetWidth()):
            for point in (prior.GetStart(), prior.GetEnd()):
                add(str(prior.GetNetname()), prior.GetLayer(), tuple(point), tuple(point), child)
    # Coincident historical anchors that split after movement are ambiguous.
    # In particular, no old common THT location can merge different new lands.
    return {key: values for key, values in mapped.items() if len({v[0] for v in values}) == 1}


def construct(board, donor, *, source_path, board_hint, include_nets=None,
              timeout_s=10., max_joins=32, max_new_tracks=512,
              allow_maze=False, max_pair_s=.35):
    """Bounded additive proposal on a caller-owned PRIVATE native board."""
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_current_topology as topology
    import cec_route_dimensions as dimensions
    import cec_ordinary_route_receiving as native
    import cec_route_quality as quality
    import cec_fab_profile as fab
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10
            or type(max_joins) is not int or not 1 <= max_joins <= 64
            or type(max_new_tracks) is not int or not 1 <= max_new_tracks <= 1024
            or type(allow_maze) is not bool or type(max_pair_s) not in (int, float)
            or not math.isfinite(max_pair_s) or not 0 < max_pair_s <= .75):
        raise ValueError('bounded_checkpoint_recovery_required')
    deadline = time.monotonic()+timeout_s
    anchors = _native_anchors(donor, board, deadline)
    existing = {_uid(t) for t in board.GetTracks()}
    grouped = {_uid(i) for g in donor.Groups() for i in g.GetItems()}
    wanted = None if include_nets is None else set(include_nets)
    rows = []
    for t in donor.GetTracks():
        if (t.GetClass() != 'PCB_TRACK' or _uid(t) in existing or _uid(t) in grouped
                or not t.GetNetname() or wanted is not None and t.GetNetname() not in wanted):
            continue
        rows.append(dict(uuid=_uid(t), net=str(t.GetNetname()), layer=int(t.GetLayer()),
            start_nm=list(t.GetStart()), end_nm=list(t.GetEnd()), width_nm=int(t.GetWidth())))
    portfolio = chains(rows, anchors)
    resolver = dimensions.project_resolver(source_path, board=board)
    limits = dimensions.board_limits(board)
    aggregate = topology.route_width_contracts(board, board_hint)
    distributed = topology.distributed_supply_contracts(board, board_hint,
        include_nets=sorted({row['net'] for row in portfolio}), netclass_resolver=resolver)['contracts']
    contracts = {**distributed, **aggregate}
    refusals = Counter()
    report = dict(joins=0, proposals=[], created_uuids=[], refusals={},
        complete_donor_chains=len(portfolio), no_path_proof=False,
        source_poses_imported=False, vias_added=0, zones_added=0, rules_changed=False,
        current_qualified=False, routing_admitted=False, release_authority=False,
        bounded_search_attempts=[])
    portfolio.sort(key=lambda row: (math.dist(anchors[row['anchor_keys'][0]][0][0],
        anchors[row['anchor_keys'][1]][0][0]), row['net'], row['anchor_keys']))
    for chain in portfolio:
        if time.monotonic() >= deadline or report['joins'] >= max_joins:
            report['stop'] = 'bounded_chain_recovery_lease'; break
        layer, net = chain['layer'], chain['net']
        name = board.GetLayerName(layer)
        canonical = fab.COPPER_LAYER_IDS.get(layer)
        if layer not in board.GetEnabledLayers().CuStack():
            refusals['current_layer_absent'] += 1; continue
        original, target = [anchors[key] for key in chain['anchor_keys']]
        first, last = original[0][0], target[0][0]
        if first == last:
            refusals['coincident_current_anchors'] += 1; continue
        # An exhausted search lease must not erase a productive private
        # prefix. It is still only a proposal, with independent saved
        # receiving required; an incomplete search is never a no-path proof.
        try:
            parts = native._partition(board, deadline)
        except ValueError as exc:
            if str(exc) != 'ordinary_receiving_deadline':
                raise
            report['stop'] = 'bounded_native_partition_lease'
            break
        indices = {key: index for index, part in enumerate(parts) for key in part}
        start_parts = {indices[force._item_key(item)] for _, item in original}
        end_parts = {indices[force._item_key(item)] for _, item in target}
        if start_parts & end_parts:
            refusals['anchors_already_native_connected'] += 1; continue
        spec = resolver(net)
        if not isinstance(spec.get('track_width'), (int, float)):
            refusals['current_netclass_unresolved'] += 1; continue
        width = math.ceil(max(spec['track_width'], limits['track_width'])*1e6)
        if net in contracts:
            required = contracts[net]['required_by_layer_mm'].get(canonical)
            if required is None:
                refusals['current_layer_rating_unresolved'] += 1; continue
            width = max(width, math.ceil(required*1e6))
        width = max(width, *(row['width_nm'] for row in chain['rows']))
        clearance = math.ceil(max(spec.get('clearance') or 0,
            board.GetDesignSettings().m_MinClearance/1e6)*1e6)
        rigid, transform = rigid_path(chain['points_nm'], first, last)
        paths = ([rigid] if rigid is not None else []) + fr._canonical_45_xy_paths(first, last)[:2]
        cache = {}
        def clear(A, B):
            return fr._tap_foreign_clear(board, pcbnew.VECTOR2I(*A), pcbnew.VECTOR2I(*B),
                width, layer, clearance, {board.GetNetcodeFromNetname(net)}, foreign_cache=cache) and \
                fr._edge_leg_clear(board, pcbnew.VECTOR2I(*A), pcbnew.VECTOR2I(*B), (width+1)//2)
        chosen = None
        for path in paths:
            if time.monotonic() >= deadline:
                break
            path = quality.compact_collinear_path(path)
            if any(not quality.canonical_heading(A, B)['ok'] or not clear(A, B)
                    for A, B in zip(path, path[1:])):
                continue
            proposed = [dict(net=net, layer=layer, width_nm=width, start_nm=list(A), end_nm=list(B))
                for A, B in zip(path, path[1:])]
            craft = quality.assess_proposed_route(board, proposed, deadline=deadline)
            if not craft['complete'] or craft['ok'] is not True:
                refusals['prospective_route_craft_refused'] += 1; continue
            chosen = proposed; break
        if chosen is None:
            if allow_maze and time.monotonic() < deadline-.05:
                pair_deadline = min(deadline-.01, time.monotonic()+max_pair_s)
                diagnostics = {}
                def leg_ok(A, B, radius):
                    return 2*radius >= width and clear(tuple(A), tuple(B))
                legs = fr._maze_lastmile_legs(board, pcbnew.VECTOR2I(*first), pcbnew.VECTOR2I(*last),
                    width, layer, clearance, board.GetNetcodeFromNetname(net), leg_ok,
                    grid_mm=.2, margin_mm=4., foreign_cache=cache,
                    deadline_monotonic=pair_deadline, diagnostics=diagnostics)
                report['bounded_search_attempts'].append(dict(net=net, layer=name,
                    source_anchor_nm=list(first), target_anchor_nm=list(last), width_nm=width,
                    donor_track_uuids=[row['uuid'] for row in chain['rows']],
                    diagnostics=diagnostics, found=bool(legs)))
                if legs and all(w == width for _, _, w in legs):
                    proposed = [dict(net=net, layer=layer, width_nm=width,
                        start_nm=list(A), end_nm=list(B)) for A, B, _ in legs]
                    craft = quality.assess_proposed_route(board, proposed, deadline=deadline)
                    if craft['complete'] and craft['ok'] is True:
                        chosen = proposed
            if chosen is None:
                refusals['bounded_source_chain_geometry_not_found'] += 1; continue
        if len(report['created_uuids'])+len(chosen) > max_new_tracks:
            report['stop'] = 'bounded_chain_track_inventory'; break
        items = []
        for row in chosen:
            track = pcbnew.PCB_TRACK(board)
            track.SetNetCode(board.GetNetcodeFromNetname(net)); track.SetLayer(layer)
            track.SetWidth(width); track.SetStart(pcbnew.VECTOR2I(*row['start_nm']))
            track.SetEnd(pcbnew.VECTOR2I(*row['end_nm'])); track.SetLocked(True)
            board.Add(track); items.append(track)
        report['joins'] += 1
        ids = [_uid(t) for t in items]
        report['created_uuids'].extend(ids)
        report['proposals'].append(dict(net=net, layer=name,
            donor_track_uuids=[row['uuid'] for row in chain['rows']],
            current_anchor_uuids=[[ _uid(item) for _, item in original],[_uid(item) for _, item in target]],
            rigid_transform=transform if rigid is not None and chosen[0]['start_nm'] == list(rigid[0]) else None,
            tracks=[dict(row, uuid=uid) for row, uid in zip(chosen, ids)]))
    report['refusals'] = dict(refusals)
    return report


def prune_incoming_dead_ends(board, incoming_uuids, *, source_uuids,
                            timeout_s=10., max_passes=1024):
    """Discard only new private proposals using KiCad's native inspector.

    No source conductor, source via, group or rule is removable. This is proposal
    cleanup, not a connectivity/DRC waiver. Independent saved receiving must
    still preserve every source partition and reject every new native fault.
    """
    import pcbnew
    from cec_native_items import discard_items
    if (type(incoming_uuids) not in (set, list, tuple) or len(incoming_uuids) > 1024
            or type(source_uuids) not in (set, list, tuple) or len(source_uuids) > 16384
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(max_passes) is not int or not 1 <= max_passes <= 1024):
        raise ValueError('finite_private_proposal_prune_scope_required')
    wanted = set(incoming_uuids)
    if wanted & set(source_uuids) or len(wanted) != len(incoming_uuids):
        raise ValueError('source_material_cannot_be_proposal_pruned')
    selected = {_uid(t): t for t in board.GetTracks() if _uid(t) in wanted}
    if set(selected) != wanted or any(t.GetClass() not in ('PCB_TRACK', 'PCB_VIA')
            or t.GetParentGroup() is not None for t in selected.values()):
        raise ValueError('exact_ungrouped_new_track_or_via_scope_required')
    deadline = time.monotonic()+timeout_s
    report = dict(removed_uuids=[], passes=0, complete=False,
        inspector='native_CONNECTIVITY_DATA_TestTrackEndpointDangling_ignoreTracksInPads_true',
        source_material_removed=False, release_authority=False)
    for _ in range(max_passes):
        if time.monotonic() >= deadline:
            break
        copper = list(board.GetTracks()) + [z for z in board.Zones() if not z.GetIsRuleArea()]
        pads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetCode() > 0]
        if len(copper)+len(pads) > 32768:
            raise ValueError('proposal_native_graph_inventory_bound')
        conn = pcbnew.CONNECTIVITY_DATA()
        for item in [*pads, *copper]:
            if time.monotonic() >= deadline or not conn.Add(item):
                raise ValueError('proposal_native_inspector_unknown')
        if not selected:
            report['complete'] = True; break
        conn.GetConnectedItems(next(iter(selected.values())))
        dead = [t for t in selected.values() if conn.TestTrackEndpointDangling(t, True, pcbnew.VECTOR2I())]
        report['passes'] += 1
        if not dead:
            report['complete'] = True; break
        ids = set(map(_uid, dead))
        report['removed_uuids'].extend(sorted(ids))
        # Destroy the private graph before its borrowed native items.
        del conn
        selected = {uid: item for uid, item in selected.items() if uid not in ids}
        discard_items(board, dead)
    return report
