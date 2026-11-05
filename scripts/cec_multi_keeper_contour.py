"""Literal connected consolidation of compatible native power contour owners.

Retain every source track and every old filled polygon. Only actual source
strokes may bridge the selected owners; no blanket slab, lowered clearance,
invented current allocation or changed group ownership is permitted. KiCad
serializes one authored outer contour per zone, so disconnected unions are
refused. Whole saved native DRC/current/field/absolute-cut receiving is separate.
An explicit source-preserving contract join retains any source lock and the
largest minimum thickness for NEW fill only. Every other process field stays
exact, and no incumbent copper record is regenerated or eroded.
"""
import math
import hashlib
import tempfile
import time
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_native_fill_geometry as geometry
import cec_native_contour_regions as signed
import cec_pad_bank_collector as bank
import cec_rectilinear_copper as owner
import cec_rounded_landing as landing

SCOPE = 'connected_source_retained_native_keeper_consolidation'
Refused = owner.Refused


def _deadline(seconds):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 10:
        raise Refused('bounded_multi_keeper_work_lease_required')
    return time.monotonic() + seconds


def _process(node, *, compatible_keeper_classes=False,conservative_keeper_contract=False):
    # Compare ALL serialized settings, not only our convenient configuration
    # subset. Thermal, island, hatch and unknown future settings remain exact.
    omitted = {'uuid', 'polygon', 'filled_polygon'}
    if compatible_keeper_classes:
        # Registered generators differ in outline representation,
        # not manufacturing process. Their ACTUAL names remain in the full
        # source snapshots and exact saved replay. This is not permission to
        # discard a group, a process setting or an unknown owner's semantics.
        omitted.add('name')
    if conservative_keeper_contract:
        # Explicit source-preserving reconciliation ONLY: locks are joined
        # by OR and minimum NEW-fill feature thickness by max. Source records
        # remain literal, and no clearance/thermal/priority/group setting is
        # normalized. Both resulting values are independently source-derived.
        omitted.update(('locked','min_thickness'))
    return syntax._freeze([q for q in node if not
        (isinstance(q, list) and q and q[0] in omitted)])


def _snapshot(zone, deadline, *, include_islands=False):
    config = landing._configuration(zone)
    if (len(config['layers']) != 1 or not zone.IsFilled()
            or not zone.HasFilledPolysForLayer(config['layers'][0])):
        raise Refused('actual_filled_single_face_keeper_required')
    result = dict(configuration=config,
        outline=geometry.snapshot(zone.Outline(), deadline),
        fill=geometry.snapshot(zone.GetFilledPolysList(config['layers'][0]), deadline))
    if include_islands:
        result['source_islands']=[bool(zone.IsIsland(config['layers'][0],i)) for i in range(len(result['fill']))]
    return result


def plan(source, track_uuids, *, allow_locked_source=False, timeout_s=10.,fill_policy='native',
         clip_native_additions=False,native_addition_inset_nm=0,allow_compatible_keeper_classes=False,
         allow_conservative_keeper_contract=False,allow_single_keeper_extension=False,
         retain_source_track_groups=False):
    """Derive a connected owner transaction from a literal SAVED source."""
    deadline = _deadline(timeout_s)
    if type(allow_locked_source) is not bool:
        raise Refused('explicit_multi_keeper_lock_policy_required')
    if type(fill_policy) is not str or fill_policy not in ('native','source_preserving_regions'):
        raise Refused('explicit_multi_keeper_fill_policy_required')
    preserving=fill_policy=='source_preserving_regions'
    if (type(allow_single_keeper_extension) is not bool or type(retain_source_track_groups) is not bool
            or (allow_single_keeper_extension or retain_source_track_groups) and not preserving):
        raise Refused('explicit_source_preserving_owner_extension_and_group_retention_required')
    if (type(allow_conservative_keeper_contract) is not bool
            or allow_conservative_keeper_contract and (not preserving or not allow_locked_source)):
        raise Refused('explicit_locked_source_preserving_conservative_keeper_contract_required')
    if (type(allow_compatible_keeper_classes) is not bool
            or allow_compatible_keeper_classes and not preserving):
        raise Refused('explicit_source_preserving_compatible_keeper_class_policy_required')
    if type(clip_native_additions) is not bool or clip_native_additions and not preserving:
        raise Refused('explicit_source_preserving_native_addition_clip_policy_required')
    if (type(native_addition_inset_nm) is not int or not 0<=native_addition_inset_nm<=10
            or native_addition_inset_nm and not clip_native_additions):
        raise Refused('bounded_new_material_inset_not_source_loss_tolerance_required')
    ids = list(track_uuids)
    if (not 1 <= len(ids) <= 16 or len(set(ids)) != len(ids)
            or any(type(u) is not str or not u for u in ids)):
        raise Refused('bounded_exact_multi_keeper_source_strokes_required')
    source = Path(source).resolve(); board = pcbnew.LoadBoard(str(source))
    _, nodes = additive._nodes(source)
    native = list(board.GetTracks()); tracks = {force._uid(t): t for t in native}
    zones = list(board.Zones()); by_id = {force._uid(z): z for z in zones}
    if (len(native) > 16384 or len(tracks) != len(native) or not set(ids) <= tracks.keys()
            or len(zones) > 8192 or len(by_id) != len(zones)):
        raise Refused('bounded_unique_actual_multi_keeper_inventory_required')
    selected = [tracks[u] for u in sorted(ids)]
    if (any(t.GetClass() != 'PCB_TRACK' or not t.GetNetname()
            or t.GetParentGroup() and not retain_source_track_groups
            or t.IsLocked() and not allow_locked_source for t in selected)
            or len({(str(t.GetNetname()), int(t.GetLayer())) for t in selected}) != 1):
        raise Refused('one_ungrouped_source_net_face_and_explicit_lock_authority_required')
    retained_groups=[]
    if retain_source_track_groups:
        groups={force._uid(g):g for g in board.Groups()}
        if len(groups)>8192:raise Refused('retained_source_track_group_inventory_bound')
        for uid in sorted({owner._group_uuid(t) for t in selected if t.GetParentGroup()}):
            owner._check_deadline(deadline)
            if uid not in groups or uid not in nodes or nodes[uid][0]!='group':
                raise Refused('actual_serialized_source_track_group_required')
            members={force._uid(t) for t in groups[uid].GetItems()}
            if len(members)>16384 or any(force._uid(t) not in members for t in selected
                    if t.GetParentGroup() and owner._group_uuid(t)==uid):
                raise Refused('complete_retained_source_track_group_membership_required')
            # Bind ALL serialized settings and members, not merely a known
            # group name. No selected or unrelated source member is retired,
            # moved or reparented; no new keeper is put into this track group.
            retained_groups.append(dict(uuid=uid,native_group_sha256=
                hashlib.sha256(repr(syntax._freeze(nodes[uid])).encode()).hexdigest()))
    net = str(selected[0].GetNetname()); layer = int(selected[0].GetLayer())
    if net.rsplit('/', 1)[-1] == 'GND':
        raise Refused('ground_or_reference_plane_consolidation_not_authorized')
    # A solid pad-bank collector is an existing keeper, not a different
    # process. Joining it is opt-in and source-preserving ONLY, just like the
    # other cross-generator joins. Its literal lands, source fill (including
    # holes), process and ownership are still independently replayed. This
    # does not admit arbitrary named planes or authorize new bank geometry.
    names = (owner.ZONE_NAME, signed.ZONE_NAME)
    if allow_compatible_keeper_classes:
        names += (bank.ZONE_NAME,)
    contacting = [z for z in zones if not z.GetIsRuleArea() and z.GetNetname() == net
        and (not preserving or z.GetAssignedPriority()==0)
        and z.IsOnLayer(layer) and z.HasFilledPolysForLayer(layer)
        and any(z.GetFilledPolysList(layer).Collide(t.GetEffectiveShape(layer), 0) for t in selected)]
    if not (1 if allow_single_keeper_extension else 2) <= len(contacting) <= 8:
        raise Refused('two_to_eight_actual_contacting_keeper_owners_required')
    chosen = {force._uid(z): z for z in contacting}
    profile = pcbnew.SHAPE_POLY_SET()
    for track in selected:
        cap = owner._native_capsule(track)
        envelope = owner._poly(owner.purposeful_envelope(cap, style='chamfer45', margin_nm=1000, grid_nm=1000))
        profile.BooleanAdd(envelope)
    reference = _process(nodes[min(chosen)],compatible_keeper_classes=allow_compatible_keeper_classes,
        conservative_keeper_contract=allow_conservative_keeper_contract)
    for _ in range(9):
        owner._check_deadline(deadline)
        for uid, z in sorted(chosen.items()):
            c = landing._configuration(z)
            if (c['name'] not in names or c['layers'] != [layer] or c['rule_area']
                    or c['priority'] != 0 or c['connection'] != int(pcbnew.ZONE_CONNECTION_FULL)
                    or c['smoothing'] or c['group_uuid'] or c['locked'] and not allow_locked_source
                    or c['clearance_nm'] < board.GetDesignSettings().m_MinClearance
                    or _process(nodes[uid],compatible_keeper_classes=allow_compatible_keeper_classes,
                        conservative_keeper_contract=allow_conservative_keeper_contract) != reference):
                raise Refused('exact_compatible_ungrouped_keeper_process_required')
            if allow_conservative_keeper_contract and not 1<=c['min_thickness_nm']<=1000000:
                raise Refused('bounded_positive_source_keeper_feature_floor_required')
            _snapshot(z, deadline); profile.BooleanAdd(z.Outline())
        # A bridge can reach another same-priority owner. Expand the exact
        # compatible owner closure, never hide it under a new overlapping zone.
        extra = []
        for z in zones:
            if (force._uid(z) in chosen or z.GetIsRuleArea() or z.GetNetname() != net
                    or not z.IsOnLayer(layer) or z.GetAssignedPriority() != 0):
                continue
            overlap = z.Outline().CloneDropTriangulation(); overlap.BooleanIntersection(profile)
            if overlap.OutlineCount(): extra.append(z)
        if not extra: break
        chosen.update({force._uid(z): z for z in extra})
        if len(chosen) > 8: raise Refused('multi_keeper_compatible_owner_closure_bound')
    else: raise Refused('multi_keeper_owner_closure_did_not_converge')
    if profile.OutlineCount() != 1:
        raise Refused('one_connected_literal_saved_keeper_outline_required')
    if profile.HoleCount(0):
        # KiCad 10.0.5's predicate flattens ring edges but identifies adjacent
        # closing edges using the TOTAL edge count, not each ring's count
        # (shape_poly_set.cpp:IsPolygonSelfIntersecting). A valid window can
        # therefore look self-intersecting at its own shared closing vertex.
        # Replace that holed-polygon predicate with strict INTEGER topology,
        # preserving every coordinate and every hole. No native violation or
        # clipping/clearance/current check is waived by this authoring guard.
        import cec_exact_outline_topology as topology
        try:
            topology.require_one_polygon(geometry.snapshot(profile,deadline,
                max_vertices=8192,max_polygons=1),deadline_monotonic=deadline)
        except ValueError as exc:
            raise Refused('invalid_literal_signed_keeper_topology:'+str(exc)) from exc
    elif profile.IsSelfIntersecting():
        raise Refused('one_connected_literal_saved_keeper_outline_required')
    for i in range(profile.OutlineCount()):
        for ring in [profile.Outline(i), *[profile.Hole(i,j) for j in range(profile.HoleCount(i))]]:
            pts = [tuple(ring.CPoint(j)) for j in range(ring.PointCount())]
            if ring.ArcCount() or any(a == b or (a[0] != b[0] and a[1] != b[1]
                    and abs(a[0]-b[0]) != abs(a[1]-b[1])) for a,b in zip(pts, pts[1:]+pts[:1])):
                raise Refused('literal_octilinear_consolidated_outline_required')
    snapshots = [_snapshot(z, deadline,include_islands=preserving) for _, z in sorted(chosen.items())]
    for row in snapshots:
        old = geometry.reconstruct(row['outline'], deadline); old.BooleanSubtract(profile)
        if old.OutlineCount(): raise Refused('consolidation_lost_source_authored_outline')
    owner._require_unoccupied_outline(board, profile, net, layer, deadline, allow_native_hole_bridges=True)
    result = dict(schema=1, scope=SCOPE, net=net, layer_id=layer,
        source_tracks=[owner._track_row(t) for t in selected], source_zones=snapshots,
        keeper_uuid=min(chosen), retired_zone_uuids=sorted(set(chosen)-{min(chosen)}),
        profile=geometry.snapshot(profile, deadline), allow_locked_source=allow_locked_source,
        source_process_sha256=hashlib.sha256(repr(reference).encode()).hexdigest(),
        retained_every_source_track=True, new_capacity_credited=False, release_authority=False)
    if allow_compatible_keeper_classes:
        result['allow_compatible_keeper_classes']=True
    if allow_single_keeper_extension:
        result['allow_single_keeper_extension']=True
    if retain_source_track_groups:
        result.update(retain_source_track_groups=True,retained_source_track_groups=retained_groups)
    if allow_conservative_keeper_contract:
        result.update(allow_conservative_keeper_contract=True,
            retained_keeper_locked=any(row['configuration']['locked'] for row in snapshots),
            retained_keeper_min_thickness_nm=max(row['configuration']['min_thickness_nm'] for row in snapshots),
            original_positive_copper_records_not_refiltered=True)
    if preserving:
        protected=[]
        for z in sorted(zones,key=force._uid):
            if (force._uid(z) in chosen or z.GetIsRuleArea() or z.GetNetname()!=net
                    or not z.IsOnLayer(layer) or z.GetAssignedPriority()<=0):continue
            overlap=z.Outline().CloneDropTriangulation();overlap.BooleanIntersection(profile)
            if not overlap.OutlineCount():continue
            row=_snapshot(z,deadline)
            row['process_sha256']=hashlib.sha256(repr(_process(nodes[force._uid(z)])).encode()).hexdigest()
            protected.append(row)
            if len(protected)>64:raise Refused('multi_keeper_protected_region_bound')
            void=z.Outline().CloneDropTriangulation();void.BooleanSubtract(z.GetFilledPolysList(layer))
            for old in snapshots:
                intrusion=geometry.reconstruct(old['fill'],deadline);intrusion.BooleanIntersection(void)
                if intrusion.OutlineCount():raise Refused('old_multi_keeper_fill_conflicts_with_protected_void')
        result.update(fill_policy=fill_policy,protected_source_regions=protected)
        if clip_native_additions:result['clip_native_additions']=True
        if native_addition_inset_nm:result['native_addition_inset_nm']=native_addition_inset_nm
    result['plan_sha256'] = owner._digest(result)
    owner._check_deadline(deadline)
    return result


def construct(board, proposal, *, timeout_s=10.):
    """Private materialization; caller MUST independently replay and receive."""
    deadline = _deadline(timeout_s)
    copied = dict(proposal); digest = copied.pop('plan_sha256', None)
    if digest != owner._digest(copied) or proposal.get('scope') != SCOPE:
        raise Refused('multi_keeper_plan_identity_required')
    # A rehashed worker polygon is not source authority. Re-derive from the
    # actual untouched caller before the first native mutation.
    with tempfile.TemporaryDirectory(prefix='cec-multi-keeper-bind-') as tmp:
        snapshot = Path(tmp)/'board.kicad_pcb'
        field._save_field_snapshot(board, snapshot)
        fresh = plan(snapshot, [t['uuid'] for t in proposal['source_tracks']],
            allow_locked_source=proposal['allow_locked_source'],
            timeout_s=max(.001, deadline-time.monotonic()),fill_policy=proposal.get('fill_policy','native'),
            clip_native_additions=proposal.get('clip_native_additions',False),
            native_addition_inset_nm=proposal.get('native_addition_inset_nm',0),
            allow_compatible_keeper_classes=proposal.get('allow_compatible_keeper_classes',False),
            allow_conservative_keeper_contract=proposal.get('allow_conservative_keeper_contract',False),
            allow_single_keeper_extension=proposal.get('allow_single_keeper_extension',False),
            retain_source_track_groups=proposal.get('retain_source_track_groups',False))
    if fresh != proposal: raise Refused('multi_keeper_plan_not_derived_from_actual_source')
    native = {force._uid(z): z for z in board.Zones()}
    for row in proposal['source_zones']:
        uid = row['configuration']['uuid']
        if uid not in native or _snapshot(native[uid], deadline,
                include_islands=proposal.get('fill_policy')=='source_preserving_regions') != row:
            raise Refused('actual_multi_keeper_source_changed')
    tracks = {force._uid(t): t for t in board.GetTracks()}
    if any(row['uuid'] not in tracks or owner._track_row(tracks[row['uuid']]) != row
            for row in proposal['source_tracks']):
        raise Refused('actual_multi_keeper_source_stroke_changed')
    keeper = native[proposal['keeper_uuid']]
    # Retain an actual original native source for component anchoring. Board
    # proxies are not used after discard_items destroys retired zone objects.
    original_source=None
    if proposal.get('fill_policy')=='source_preserving_regions':
        with tempfile.TemporaryDirectory(prefix='cec-multi-keeper-source-') as tmp:
            original=Path(tmp)/'board.kicad_pcb';field._save_field_snapshot(board,original)
            original_source=pcbnew.LoadBoard(str(original))
    if proposal.get('allow_conservative_keeper_contract',False):
        keeper.SetLocked(proposal['retained_keeper_locked'])
        keeper.SetMinThickness(proposal['retained_keeper_min_thickness_nm'])
    keeper.UnFill(); keeper.Outline().RemoveAllContours()
    keeper.Outline().Append(geometry.reconstruct(proposal['profile'], deadline))
    from cec_native_items import discard_items
    discard_items(board, [native[u] for u in proposal['retired_zone_uuids']])
    import cec_zone_fill
    selected = pcbnew.ZONES(); selected.append(keeper); board.BuildConnectivity()
    cec_zone_fill.compile_selected(board, selected, timeout_s=max(.001, deadline-time.monotonic()))
    actual = keeper.GetFilledPolysList(proposal['layer_id'])
    if not keeper.IsFilled() or not keeper.HasFilledPolysForLayer(proposal['layer_id']):
        raise Refused('actual_consolidated_keeper_fill_required')
    if proposal.get('fill_policy')=='source_preserving_regions':
        made=_preserve_source_regions(original_source,keeper,proposal,deadline)
        actual=keeper.GetFilledPolysList(proposal['layer_id'])
    else:made=None
    for old in proposal['source_zones']:
        old_shape=geometry.reconstruct(old['fill'],deadline)
        if made is not None:
            import cec_regional_fill as regional
            if not regional.exact_source_contour_present(actual,old_shape,deadline):
                raise Refused('multi_keeper_literal_source_fill_record_lost')
        else:
            missing=old_shape.CloneDropTriangulation();missing.BooleanSubtract(actual)
            if missing.OutlineCount(): raise Refused('consolidation_lost_actual_old_filled_copper')
    if made is None:
        spill = actual.CloneDropTriangulation()
        spill.BooleanSubtract(geometry.reconstruct(proposal['profile'], deadline))
        if spill.OutlineCount(): raise Refused('consolidation_fill_outside_literal_profile')
    additive._ground_refill(board)
    owner._check_deadline(deadline)
    result=dict(keeper_uuid=proposal['keeper_uuid'], retired_zone_uuids=proposal['retired_zone_uuids'],
        every_source_track_and_old_fill_retained=True, release_authority=False, new_capacity_credited=False)
    if made is not None:result['source_preserving_native_fill']=made
    return result


def _preserve_source_regions(source,keeper,proposal,deadline):
    """Literal incumbent records plus real, bounded, anchored native additions.

    No rounded Boolean union may replace an incumbent polygon. New material
    is a subset of a fresh native fill, clipped to stronger same-net regional
    voids and the existing feature floor. Every final positive record is
    reconstructed from these exact sources by the independent saved replay.
    """
    import cec_regional_fill as regional
    layer=proposal['layer_id'];compiled=keeper.GetFilledPolysList(layer).CloneDropTriangulation()
    compiled_id=geometry.identity(compiled,deadline)[0]
    profile=geometry.reconstruct(proposal['profile'],deadline)
    if proposal.get('clip_native_additions',False):
        # Set intersection only REMOVES material from a fresh, independent
        # native addition. It is not a spill tolerance or an incumbent edit.
        domain=profile.CloneDropTriangulation();inset=proposal.get('native_addition_inset_nm',0)
        if inset:domain.Inflate(-inset,pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,1)
        compiled.BooleanIntersection(domain)
    spill=compiled.CloneDropTriangulation();spill.BooleanSubtract(profile)
    if spill.OutlineCount():raise Refused('native_multi_keeper_addition_outside_authored_domain')
    for region in proposal['protected_source_regions']:
        void=geometry.reconstruct(region['outline'],deadline)
        void.BooleanSubtract(geometry.reconstruct(region['fill'],deadline));compiled.BooleanSubtract(void)
    # Only NEW additions are subject to feature filtering. A positive literal
    # source record is never eroded, buffered or counted twice as capacity.
    minimum=proposal.get('retained_keeper_min_thickness_nm',
        proposal['source_zones'][0]['configuration']['min_thickness_nm']);radius=(minimum+1)//2
    usable=compiled.CloneDropTriangulation()
    usable.Inflate(-radius,pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,1)
    usable.Inflate(radius,pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS,1)
    usable.BooleanIntersection(compiled)
    result=regional.anchored_native_additions(source,usable,net=proposal['net'],layer=layer,
        source_zone_uuids=[r['configuration']['uuid'] for r in proposal['source_zones']],deadline=deadline)
    result.Fracture();added_count=result.OutlineCount();flags=[]
    for row in proposal['source_zones']:
        result.Append(geometry.reconstruct(row['fill'],deadline));flags.extend(row['source_islands'])
    if result.OutlineCount()>256:raise Refused('multi_keeper_literal_fill_component_bound')
    geometry.identity(result,deadline)
    keeper.UnFill();keeper.SetFilledPolysList(layer,result);keeper.SetIsFilled(True)
    for i,island in enumerate(flags):
        if island:keeper.SetIsIsland(layer,added_count+i)
    return dict(compiled_native_fill_sha256=compiled_id,
        exact_result_sha256=geometry.identity(result,deadline)[0],
        every_incumbent_positive_record_preserved=True,all_additions_from_anchored_native_fill=True,
        protected_region_count=len(proposal['protected_source_regions']),
        new_capacity_credited=False,release_authority=False)


def receive(source, candidate, records, *, board_hint, sense_timeout_s=40.):
    """Reconstruct the WHOLE original transaction, not merely a child delta."""
    result = dict(ok=False, complete=False, errors=[], release_authority=False, new_capacity_credited=False,
        current_qualified=False, thermal_qualified=False, full_native_DRC_and_stack_receiving_required=True)
    try:
        if type(records) is not list or not 1 <= len(records) <= 4:
            raise Refused('bounded_multi_keeper_phase_records_required')
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        if source == candidate: raise Refused('distinct_saved_multi_keeper_source_and_candidate_required')
        epoch = force._code_identity(); families = [force._family(p, board_hint) for p in (source, candidate)]
        before, after = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        with tempfile.TemporaryDirectory(prefix='cec-multi-keeper-') as tmp:
            expected = force._copy_family(source, Path(tmp)/'replay')
            for row in records:
                if set(row) != {'plan', 'materialized'}: raise Refused('literal_multi_keeper_record_required')
                fresh = plan(expected, [t['uuid'] for t in row['plan']['source_tracks']],
                    allow_locked_source=row['plan']['allow_locked_source'],
                    fill_policy=row['plan'].get('fill_policy','native'),
                    clip_native_additions=row['plan'].get('clip_native_additions',False),
                    native_addition_inset_nm=row['plan'].get('native_addition_inset_nm',0),
                    allow_compatible_keeper_classes=row['plan'].get('allow_compatible_keeper_classes',False),
                    allow_conservative_keeper_contract=row['plan'].get('allow_conservative_keeper_contract',False),
                    allow_single_keeper_extension=row['plan'].get('allow_single_keeper_extension',False),
                    retain_source_track_groups=row['plan'].get('retain_source_track_groups',False))
                if fresh != row['plan']: raise Refused('multi_keeper_plan_not_derived_from_actual_source')
                replayed = pcbnew.LoadBoard(str(expected))
                if construct(replayed, fresh) != row['materialized']:
                    raise Refused('multi_keeper_materialized_identity_changed')
                field._save_field_snapshot(replayed, expected)
            expected_root, _ = additive._nodes(expected); actual_root, _ = additive._nodes(candidate)
            if (syntax._freeze(expected_root) != syntax._freeze(actual_root)
                    or force._sidecars(source) != force._sidecars(candidate)):
                raise Refused('whole_original_multi_keeper_saved_replay_differs')
        debt = current.receive(source, candidate, board_hint=board_hint)
        result['whole_source_current_debt'] = debt
        if not debt['ok'] or not debt['complete']: raise Refused('whole_source_multi_keeper_current_debt_refused')
        with force._thermal_hint(board_hint):
            delta = sorted(field.blocker_keys(field.field_coupling_summary(str(candidate))) -
                field.blocker_keys(field.field_coupling_summary(str(source))))
        result['new_field_blocker_keys'] = delta
        if delta: raise Refused('new_multi_keeper_field_blocker')
        nets = sorted({r['plan']['net'] for r in records})
        first, last = [sense.replay(p, board_hint=board_hint, timeout_s=sense_timeout_s) for p in (source,candidate)]
        cuts = sense.compare_contour_preservation(first, last, modified_nets=nets,
            native_copper_transforms=sense.native_copper_transform_inventory(before, after, modified_nets=nets))
        result['absolute_native_cut_preservation'] = cuts
        if not cuts['same_evidence'] or not cuts['comparison_complete']:
            raise Refused('multi_keeper_absolute_native_cut_preservation_refused')
        if epoch != force._code_identity() or families != [force._family(p,board_hint) for p in (source,candidate)]:
            raise Refused('multi_keeper_source_candidate_or_code_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(source), candidate_sha256=force._hash(candidate),
            code_identity=epoch, whole_original_saved_replay_equal=True, every_source_track_and_old_fill_retained=True)
    except (ValueError, RuntimeError, TypeError, KeyError, OSError, Refused) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
