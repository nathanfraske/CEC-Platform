"""Saved-project-class Ground dead-end subtraction; no current authority.

The legacy small-tail API is unchanged. Discovery deliberately repeats its
bounded topology checks, while saved receiving reuses its exact subtraction,
native partitions and already-proved short-return checks.
"""
import math
from pathlib import Path
import time
import tempfile
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ground_dead_end_tail as small
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items

_deadline = small._deadline

def _authority(board, source, ground_net):
    if ground_net != 'GND':
        raise ValueError('explicit_source_ground_net_required')
    source = Path(source).resolve(strict=True)
    project = source.with_suffix('.kicad_pro')
    if source.suffix != '.kicad_pcb' or not project.is_file():
        raise ValueError('saved_source_project_ground_class_required')
    # No caller-supplied width, in-memory borrowed class or stale native board.
    saved = pcbnew.LoadBoard(str(source))
    if _source_binding(saved) != _source_binding(board):
        raise ValueError('exact_saved_source_ground_tail_native_identity_required')
    from cec_route_dimensions import NetclassTable
    spec = NetclassTable.from_board_path(source).resolve(ground_net)
    raw = (spec or {}).get('track_width')
    floor = int(saved.GetDesignSettings().m_TrackMinWidth)
    if (type(raw) not in (int, float) or not math.isfinite(raw)
            or raw <= 0 or round(raw * 1e6) < floor or floor <= 0):
        raise ValueError('positive_saved_source_ground_class_and_floor_required')
    return dict(source_sha256=force._hash(source), project_sha256=force._hash(project),
                width_nm=round(raw * 1e6), setup_floor_nm=floor,
                current_authority=False)

def plan(board, source, seed_uuid, *, ground_net='GND', timeout_s=10.,
         max_tracks=8, max_length_mm=12., allow_locked_track_uuids=()):
    deadline = _deadline(timeout_s)
    authority = _authority(board, source, ground_net)
    source_family = force._family(Path(source), str(source))
    epoch = force._code_identity()
    if (type(seed_uuid) is not str or not seed_uuid or type(ground_net) is not str
            or not ground_net or type(max_tracks) is not int or not 1 <= max_tracks <= 8
            or type(max_length_mm) not in (int, float) or not math.isfinite(max_length_mm)
            or not 0 < max_length_mm <= 12):
        raise ValueError('bounded_explicit_ground_dead_end_scope_required')
    tracks = list(board.GetTracks())
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    zones = [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == ground_net]
    if len(tracks) + len(pads) + len(zones) > 16384:
        raise ValueError('ground_dead_end_native_inventory_bound')
    matches = [t for t in tracks if force._uid(t) == seed_uuid]
    if len(matches) != 1:
        raise ValueError('unique_native_ground_dead_end_seed_required')
    seed = matches[0]
    if seed.GetClass() != 'PCB_TRACK' or seed.GetNetname() != ground_net:
        raise ValueError('native_ground_track_seed_required')
    layer, width = int(seed.GetLayer()), int(seed.GetWidth())
    if width != authority['width_nm'] or any(not z.IsFilled() for z in zones):
        raise ValueError('small_tail_and_known_saved_ground_fill_required')
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    import cec_ordinary_route_receiving as ordinary
    allowed=ordinary._ids(allow_locked_track_uuids,'source_class_ground_tail_exact_lock_scope',8)
    own = [t for t in tracks if t.GetNetname() == ground_net and t.IsOnLayer(layer)]

    def check_time():
        if time.monotonic() >= deadline:
            raise ValueError('ground_dead_end_inventory_deadline')

    def contacts(edge, point=None):
        shape = (edge.GetEffectiveShape(layer) if point is None else
                 pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*point), pcbnew.VECTOR2I(*point), 0))
        result = []
        for other in own:
            check_time()
            if force._uid(other) != force._uid(edge) and shape.Collide(other.GetEffectiveShape(layer), 0):
                result.append(other)
        return result

    ends = [tuple(seed.GetStart()), tuple(seed.GetEnd())]
    free = [point for point in ends if not contacts(seed, point)]
    short_cap_leaf=None
    if len(free) != 1:
        # A sub-radius terminal nub may have both centre points inside the
        # retained round caps. Require its sole unmatched exact endpoint and
        # an entirely outward cap-only seat on EVERY actual retained track.
        # Never infer an interior bridge, pad, barrel, plane or mesh leaf.
        exact_free=[point for point in ends if not any(point in
            (tuple(t.GetStart()),tuple(t.GetEnd()))for t in own if force._uid(t)!=seed_uuid)]
        peers=contacts(seed)
        if free or len(exact_free)!=1 or not 0<seed.GetLength()<=width/2 or not peers:
            raise ValueError('exactly_one_free_native_ground_tail_tip_required')
        seats=[]
        for peer in peers:
            if peer.GetClass()!='PCB_TRACK'or peer.GetWidth()!=width:
                raise ValueError('short_ground_nub_requires_uniform_retained_endpoint_caps')
            options=[];vertices=[tuple(peer.GetStart()),tuple(peer.GetEnd())]
            for at in vertices:
                other=vertices[1]if at==vertices[0]else vertices[0]
                inward=(other[0]-at[0],other[1]-at[1])
                cap=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*at),width)
                if (seed.GetEffectiveShape(layer).Collide(cap,0)
                        and all((p[0]-at[0])*inward[0]+(p[1]-at[1])*inward[1]<=0 for p in ends)):
                    options.append(at)
            if len(options)!=1:
                raise ValueError('short_ground_nub_has_retained_interior_body_contact')
            seats.append(dict(retained_track_uuid=force._uid(peer),endpoint_nm=list(options[0])))
        free=exact_free
        short_cap_leaf=dict(subradius_terminal_nub=True,whole_retained_endpoint_caps=sorted(
            seats,key=lambda row:row['retained_track_uuid']),
            literal_unmatched_tip_nm=list(free[0]),native_centres_not_assumed_disconnected=True)
    point = free[0]
    current = seed
    retired, length, root = [], 0., None
    junction=None
    native_cap_links=[]
    while True:
        check_time()
        uid = force._uid(current)
        ends = [tuple(current.GetStart()), tuple(current.GetEnd())]
        if (current.GetClass() != 'PCB_TRACK' or current.IsLocked() and uid not in allowed or uid in grouped
                or current.GetParentGroup() is not None or current.GetWidth() != width
                or current.GetLayer() != layer or current.GetNetname() != ground_net
                or point not in ends or ends[0] == ends[1] or uid in retired):
            raise ValueError('unlocked_ungrouped_uniform_endpoint_tail_required')
        length += current.GetLength()/1e6
        retired.append(uid)
        if len(retired) > max_tracks or length > max_length_mm:
            raise ValueError('ground_dead_end_tail_scope_bound')
        material = current.GetEffectiveShape(layer)
        for other in [*pads, *zones]:
            check_time()
            if not other.IsOnLayer(layer):
                continue
            shape = (other.GetFilledPolysList(layer) if other.GetClass() == 'ZONE'
                     else other.GetEffectiveShape(layer))
            if material.Collide(shape, 0):
                raise ValueError('ground_tail_has_actual_land_or_plane_contact')
        far = ends[1] if point == ends[0] else ends[0]
        next_items = [i for i in contacts(current) if force._uid(i) not in retired]
        if len(next_items)>1:
            # A true free leaf may meet a retained tee instead of a lone
            # barrel. Keep every tee conductor; require actual native contact
            # at the root cap and independently trace the retained component
            # through per-filled-island native nodes to a real plane barrel.
            # Integer endpoint differences are NOT snapped or rounded.
            cap=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*far),pcbnew.VECTOR2I(*far),width)
            if any(t.GetClass()not in ('PCB_TRACK','PCB_VIA')
                    or not cap.Collide(t.GetEffectiveShape(layer),0) for t in next_items):
                raise ValueError('ground_tail_has_unowned_interior_root_contacts')
            probe=pcbnew.LoadBoard(str(Path(source).resolve()))
            discard_items(probe,[t for t in probe.GetTracks()if force._uid(t)in retired])
            import cec_native_partition_pair as partitions
            inventory=partitions._inventory(probe,deadline,
                dict(items=16384,polygons=4096,vertices=200000))
            keys={force._item_key(t)for t in next_items}
            parts=[part for part in inventory['components']if keys<=part]
            if len(parts)!=1:
                raise ValueError('ground_tail_retained_tee_contacts_not_one_actual_component')
            import cec_ground_return_shortcut as reference
            witnesses=[]
            for item in inventory['objects']:
                check_time()
                if (item.GetClass()!='PCB_VIA'or force._item_key(item)not in parts[0]
                        or item.GetViaType()!=pcbnew.VIATYPE_THROUGH):continue
                try:planes=reference._reference_contacts(probe,item)
                except ValueError:continue
                witnesses.append((force._uid(item),planes))
            if not witnesses:
                raise ValueError('ground_tail_retained_tee_has_no_actual_plane_barrel')
            root_uid,reference_planes=min(witnesses,key=lambda row:row[0])
            root=next(t for t in board.GetTracks()if force._uid(t)==root_uid)
            junction=dict(position_nm=list(far),retained_contact_uuids=sorted(force._uid(t)for t in next_items),
                one_retained_actual_native_component=True,whole_zone_uuid_credit=False,
                reference_plane_contacts=reference_planes)
            break
        if len(next_items) != 1:
            raise ValueError('ground_tail_has_branch_or_missing_endpoint_root')
        following = next_items[0]
        if not following.GetEffectiveShape(layer).Collide(
                pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*far), pcbnew.VECTOR2I(*far), width), 0):
            raise ValueError('ground_tail_has_interior_contact')
        if following.GetClass() == 'PCB_VIA':
            if (tuple(following.GetPosition()) != far
                    or following.GetViaType() != pcbnew.VIATYPE_THROUGH):
                raise ValueError('exact_retained_through_via_endpoint_required')
            root = following
            break
        if following.GetClass() != 'PCB_TRACK':
            raise ValueError('ground_tail_terminates_at_unowned_interior_junction')
        following_ends=[tuple(following.GetStart()),tuple(following.GetEnd())]
        near=far
        if far not in following_ends:
            # Native round caps can join with distinct centreline endpoints.
            # Do not snap either endpoint or mistake the whole width-sized
            # tip disc for its centre. Only an outward, unique endpoint-cap
            # contact is walkable; body/interior/branch contacts stay refused.
            options=[]
            for endpoint in following_ends:
                other=following_ends[1]if endpoint==following_ends[0]else following_ends[0]
                delta=(far[0]-endpoint[0],far[1]-endpoint[1])
                inward=(other[0]-endpoint[0],other[1]-endpoint[1])
                approach=(far[0]-point[0],far[1]-point[1])
                bridge=(endpoint[0]-far[0],endpoint[1]-far[1])
                endpoint_cap=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*endpoint),
                    pcbnew.VECTOR2I(*endpoint),width)
                centre=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*far),pcbnew.VECTOR2I(*far),0)
                if (delta[0]*inward[0]+delta[1]*inward[1]<=0
                        and approach[0]*bridge[0]+approach[1]*bridge[1]>0
                        and centre.Collide(endpoint_cap,0)):
                    options.append(endpoint)
            if len(options)!=1:
                raise ValueError('ground_tail_terminates_at_unowned_interior_junction')
            near=options[0]
            native_cap_links.append(dict(from_track_uuid=uid,to_track_uuid=force._uid(following),
                from_position_nm=list(far),to_position_nm=list(near),
                actual_native_outward_endpoint_cap_contact=True,endpoint_snap=False))
        current, point = following, near
    planes = []
    for zone in zones:
        check_time()
        for lid in board.GetEnabledLayers().CuStack():
            if zone.IsOnLayer(lid) and root.IsOnLayer(lid) and zone.GetFilledPolysList(lid).Collide(
                    root.GetEffectiveShape(lid), 0):
                planes.append(force._uid(zone))
                break
    if not planes:
        raise ValueError('retained_root_has_no_actual_saved_ground_plane_contact')
    if allowed!={u for u in retired if next(t for t in tracks if force._uid(t)==u).IsLocked()}:
        raise ValueError('only_exact_retired_source_class_ground_locks_may_be_authorized')
    if (force._family(Path(source), str(source)) != source_family
            or epoch != force._code_identity() or time.monotonic() >= deadline):
        raise ValueError('source_class_ground_tail_live_epoch_changed')
    return dict(schema=1, kind='source_class_pad_free_native_ground_dead_end_tail',
                source=str(Path(source).resolve()), source_authority=authority,
                seed_uuid=seed_uuid, ground_net=ground_net, max_tracks=max_tracks,
                allow_locked_track_uuids=sorted(allowed),
                max_length_mm=max_length_mm, source_binding=_source_binding(board),
                retired_track_uuids=retired, retained_root_via_uuid=force._uid(root),
                source_layer=layer, source_width_nm=width, source_length_mm=length,
                root_plane_uuids=sorted(planes),retained_native_junction=junction,
                retained_native_cap_links=native_cap_links,
                short_native_cap_leaf=short_cap_leaf,
                current_qualified=False, release_authority=False)


def subtract(board, proposal, *, timeout_s=10.):
    fresh = plan(board, proposal['source'], proposal['seed_uuid'],
        ground_net=proposal['ground_net'], timeout_s=timeout_s,
        max_tracks=proposal['max_tracks'], max_length_mm=proposal['max_length_mm'],
        allow_locked_track_uuids=proposal['allow_locked_track_uuids'])
    if fresh != proposal:
        raise ValueError('source_class_ground_tail_stale_or_forged_plan')
    live = {force._uid(t): t for t in board.GetTracks()}
    discard_items(board, [live[u] for u in fresh['retired_track_uuids']])

def receive(source, candidate, proposal, *, board_hint, timeout_s=10.):
    # Bind the callback to the actual independent parent, not proposal paths.
    source = Path(source).resolve()
    if str(source) != proposal.get('source'):
        return dict(ok=False, complete=False, errors=['saved_ground_tail_source_mismatch'],
                    current_qualified=False, release_authority=False)
    return _receive_exact_subtraction(source, candidate, proposal,
        board_hint=board_hint, subtractor=subtract, timeout_s=timeout_s)

def _receive_exact_subtraction(source, candidate, proposal, *, board_hint,
                              subtractor, timeout_s=10.):
    """Shared saved replay; the typed operator still derives its own cut."""
    result = dict(schema=1, ok=False, complete=False, errors=[], current_qualified=False,
                  inherited_debt_qualified=False, release_authority=False,
                  full_saved_board_receiving_still_required=True)
    try:
        deadline = _deadline(timeout_s)
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_ground_tail_candidates_required')
        families = [force._family(p, board_hint) for p in (source, candidate)]
        epoch = force._code_identity()
        before, after = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        retired = set(proposal['retired_track_uuids'])
        import cec_native_partition_pair as partitions
        partition = partitions.compare(before, after, retired_uuids=retired,
            timeout_s=max(.001, deadline-time.monotonic()))
        if partition.get('available') is not True or partition.get('preserved') is not True:
            raise ValueError('ground_tail_cut_lost_surviving_native_partition')
        new_pads = {force._uid(p): p for f in after.GetFootprints() for p in f.Pads()}
        returns = []
        for fp in before.GetFootprints():
            for pad in fp.Pads():
                if time.monotonic() >= deadline:
                    raise ValueError('ground_tail_return_receiving_deadline')
                if pad.GetNetname() != proposal['ground_net']:
                    continue
                prior = cells._existing_return(before, pad, 3.5)
                if prior is None:
                    continue
                child = new_pads.get(force._uid(pad))
                current = cells._existing_return(after, child, 3.5) if child is not None else None
                if current is None or current[0] > prior[0] + 1e-6:
                    raise ValueError('ground_tail_cut_worsened_proved_local_return')
                returns.append(dict(pad_uuid=force._uid(pad), before_mm=prior[0], after_mm=current[0]))
        with tempfile.TemporaryDirectory(prefix='cec-ground-tail-receiving-') as work:
            expected = force._copy_family(source, Path(work)/'expected')
            basis = pcbnew.LoadBoard(str(source))
            subtractor(basis, proposal, timeout_s=max(.001, deadline-time.monotonic()))
            additive._ground_refill(basis)
            field._save_field_snapshot(basis, expected)
            # This operator owns no group edits: every retired stroke is
            # independently proved ungrouped. Native IO can reorder an
            # unrelated group's members. Rebuild the EXPECTED Source group
            # nodes literally instead of granting the child any ordering,
            # membership, lock, name or opaque-metadata normalization.
            import cec_source_literal_additions as literal
            import cec_source_retaining_ses_import as raw
            original = raw.raw_text(source)
            inventory, *_ = literal._inventory(original)
            source_groups = {uid for uid, (_, _, node) in inventory.items()
                if raw.kind(node) == 'group'}
            if source_groups:
                raw.write_raw(expected, raw.retain_replay_source_nodes(original,
                    raw.raw_text(expected), source_groups, set()))
            _, old_nodes = additive._nodes(expected)
            _, new_nodes = additive._nodes(candidate)
            if old_nodes.keys() != new_nodes.keys() or any(
                    syntax._freeze(old_nodes[u]) != syntax._freeze(new_nodes[u]) for u in old_nodes):
                raise ValueError('ground_tail_not_exact_native_subtract_and_refill')
            if (force._preservation_snapshot(expected)[1] != force._preservation_snapshot(candidate)[1]
                    or force._sidecars(expected) != force._sidecars(candidate)):
                raise ValueError('ground_tail_outline_rules_or_sidecars_changed')
        if (families != [force._family(p, board_hint) for p in (source, candidate)]
                or epoch != force._code_identity() or time.monotonic() >= deadline):
            raise ValueError('ground_tail_source_code_or_lease_changed')
        result.update(ok=True, complete=True, retired_track_uuids=sorted(retired),
                      retained_root_via_uuid=proposal['retained_root_via_uuid'],
                      all_surviving_native_partitions_preserved=True,
                      proved_short_ground_returns_preserved=returns,
                      exact_subtraction_and_ground_refill_received=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result
