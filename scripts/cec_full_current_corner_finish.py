"""Native full-width power miters with independently rederived current ownership.

The ordinary/sensitive defaults remain narrow. This separate owner may only
chamfer existing, complete, full-current planar traces. No neck-down, load
division, new face, hole, pour, pose, budget change or release follows. Real
exposed native copper must change; hidden centerline bookkeeping is refused.
"""
from collections import Counter
import json
from pathlib import Path
import tempfile
import time
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_copper_echo as syntax
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_full_current_planar_reflow as full
import cec_native_scalar_corner_scope as corners
import cec_native_fill_geometry as fills
import cec_precision_route as precision
import cec_rated_supply_corner_finish as signatures
import cec_rectilinear_copper as copper
from cec_native_items import discard_items


def _settings(allow_locked_source, maximum_nm, minimum_nm):
    if (type(allow_locked_source) is not bool or any(type(v) is not int for v in (maximum_nm, minimum_nm))
            or not 1 <= minimum_nm <= maximum_nm <= 2000000):
        raise ValueError('explicit_bounded_full_current_corner_settings_required')


def _fully_hidden_source(board, items, cache, deadline):
    """Skip only source capsules wholly covered by actual same-net fill.

    A source-local cache is discarded with this immutable inventory. A zone
    name, outline, bbox, other net/face or unfilled zone is never coverage.
    This is scheduling, not permission to change any source material.
    """
    key=(str(items[0].GetNetname()),int(items[0].GetLayer()))
    if key not in cache:
        zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==key[0] and z.IsOnLayer(key[1])]
        actual=pcbnew.SHAPE_POLY_SET()
        for zone in zones:
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(key[1]):
                cache[key]=None;break
            poly=zone.GetFilledPolysList(key[1]);fills.identity(poly,deadline);actual.BooleanAdd(poly)
        else:cache[key]=actual
    actual=cache[key]
    if actual is None or not actual.OutlineCount():return False
    source=pcbnew.SHAPE_POLY_SET()
    for item in items:
        if time.monotonic()>=deadline:raise ValueError('full_current_corner_inventory_deadline')
        source.BooleanAdd(copper._native_capsule(item))
    source.BooleanSubtract(actual)
    return not source.OutlineCount()


def _retained_corner_keepers(board, row, item, deadline):
    """Literal pour ownership at a turn cannot be left at its old pose.

    Even a partly exposed old trace may share its corner with a shaped
    keeper. Moving ONLY the centerline can leave that keeper as a spur or
    tooth. This operator owns no pour retirement: require a composed contour
    owner rather than hiding the spur behind a successful track-only check.
    """
    cap=item.Duplicate();at=pcbnew.VECTOR2I(*row['at_nm']);cap.SetStart(at);cap.SetEnd(at)
    disk=copper._native_capsule(cap);records=[]
    for zone in board.Zones():
        if time.monotonic()>=deadline:raise ValueError('full_current_corner_inventory_deadline')
        if zone.GetIsRuleArea() or zone.GetNetname()!=row['net'] or not zone.IsOnLayer(row['layer']):continue
        actual=zone.IsFilled() and zone.HasFilledPolysForLayer(row['layer'])
        shape=zone.GetFilledPolysList(row['layer']) if actual else zone.Outline()
        fills.identity(shape,deadline)
        overlap=disk.CloneDropTriangulation();overlap.BooleanIntersection(shape)
        if overlap.OutlineCount():records.append(dict(zone_uuid=force._uid(zone),
            zone_name=str(zone.GetZoneName()),actual_native_fill=bool(actual),
            native_corner_disk_intersects_retained_owner=True,requires_composed_contour_owner=True))
    return records


def discover(board, source, *, board_hint, allow_locked_source=False, maximum_nm=2000000, minimum_nm=50000):
    _settings(allow_locked_source, maximum_nm, minimum_nm)
    if (type(board_hint) is not str or not board_hint or
            Path(board.GetFileName()).resolve() != Path(source).resolve()):
        raise ValueError('actual_source_full_current_corner_context_required')
    deadline = time.monotonic()+10.
    with force._thermal_hint(board_hint):
        domains = topology.board_current_domains(board, board_hint)
        supplies = topology.distributed_supply_contracts(board, board_hint,
            netclass_resolver=fr._project_netclass_resolver(str(source),board=board))
    nets = (set(domains)|set(supplies['contracts']))-{'GND'}
    pairs = precision.derive_coupled_pairs(str(source), board=board)
    nets -= {n for pair in pairs for n in (pair['p'], pair['n'])}
    inventory = corners.select(board, nets, minimum_chamfer_nm=minimum_nm,
        maximum_chamfer_nm=maximum_nm, maximum_width_nm=10000000,
        maximum_candidates=128, maximum_scoped_tracks=256, timeout_s=max(.001, deadline-time.monotonic()))
    if not inventory['inventory_complete']: raise ValueError('complete_full_current_corner_inventory_required')
    live = {force._uid(t):t for t in board.GetTracks()}; rows = []; refusals = Counter()
    models={};fill_cache={};contour_frontier=[]
    for row in inventory['selected']:
        if time.monotonic() >= deadline: raise ValueError('full_current_corner_inventory_deadline')
        items = [live[u] for u in row['source_track_uuids']]
        if any(t.HasSolderMask() or t.GetParentGroup() or t.IsLocked() and not allow_locked_source for t in items):
            refusals['source_process_or_lock_scope'] += 1; continue
        try:
            # Read-only preflight only. Every selected batch and every saved
            # receiver still invokes full.plan afresh, including boundaries.
            if row['net'] not in models:
                try:models[row['net']]=full._model(board,source,row['net'],board_hint)
                except ValueError as exc:models[row['net']]=str(exc)
            model=models[row['net']]
            if type(model) is str:raise ValueError(model)
            floor=full._source_width_floor(board,source,model[2],row['layer'])
            width=int(items[0].GetWidth())
            if (not floor<=width<=10000000 or any(not 0<t.GetLength()<=32000000 for t in items)
                    or sum(t.GetLength() for t in items)>48000000):
                raise ValueError('bounded_unchanged_full_current_planar_width_and_span_required')
            if _fully_hidden_source(board,items,fill_cache,deadline):
                raise ValueError('source_full_current_corner_already_inside_actual_native_fill')
            keepers=_retained_corner_keepers(board,row,items[0],deadline)
            if keepers:
                contour_frontier.append(dict(request=row,retained_native_corner_owners=keepers,
                    typed_current_floor_nm=floor,source_width_nm=width))
                raise ValueError('source_corner_requires_owner_synchronized_power_contour_refresh')
        except ValueError as exc:
            refusals[str(exc)] += 1; continue
        rows.append(dict(row, width_nm=width, full_current_floor_nm=floor))
    rows.sort(key=lambda r: (-r['width_nm'], r['net'], r['layer'], r['at_nm']))
    if time.monotonic() >= deadline: raise ValueError('full_current_corner_inventory_deadline')
    return dict(complete=True, requests=rows, refusals=dict(refusals), native_inventory=inventory,
        composed_power_contour_frontier=contour_frontier,
        current_budget_changed=False, ordinary_reclassification=False, release_authority=False)


def plan(board, source, requests, *, board_hint, allow_locked_source=False, maximum_nm=2000000, minimum_nm=50000):
    if type(requests) is not list or not 1 <= len(requests) <= 4:
        raise ValueError('bounded_one_to_four_full_current_corners_required')
    inventory = discover(board, source, board_hint=board_hint, allow_locked_source=allow_locked_source,
        maximum_nm=maximum_nm, minimum_nm=minimum_nm)
    if (any(r not in inventory['requests'] for r in requests) or
            len({tuple(r['source_track_uuids']) for r in requests}) != len(requests)):
        raise ValueError('literal_distinct_source_full_current_corners_required')
    ids = sorted({u for r in requests for u in r['source_track_uuids']})
    owner = full.plan(board, source, board_hint=board_hint, retired_track_uuids=ids,
        max_source_track_mm=32., max_source_cut_mm=48.)
    return dict(schema=1, requests=json.loads(json.dumps(requests)), source_sha256=force._hash(Path(source)),
        source_binding=binding._source_binding(board), full_current_proposal=json.loads(json.dumps(owner)),
        allow_locked_source=allow_locked_source, maximum_nm=maximum_nm, minimum_nm=minimum_nm,
        new_capacity_or_sharing_authority=False, ordinary_reclassification=False, release_authority=False)


def materialize(board, source, proposal, *, board_hint):
    deadline = time.monotonic()+10.
    settings = {k:proposal[k] for k in ('allow_locked_source', 'maximum_nm', 'minimum_nm')}
    if plan(board, source, proposal['requests'], board_hint=board_hint, **settings) != proposal:
        raise ValueError('stale_or_forged_full_current_corner_plan')
    source_items = {force._uid(t):t for t in board.GetTracks()}
    old = {u:(tuple(t.GetStart()), tuple(t.GetEnd())) for u,t in source_items.items() if t.GetClass() == 'PCB_TRACK'}
    cut = set(proposal['full_current_proposal']['retired_track_uuids']); details = []
    for row in proposal['requests']:
        if time.monotonic() >= deadline: raise ValueError('full_current_corner_construction_deadline')
        live = {force._uid(t):t for t in board.GetTracks()}; locks = {u:bool(t.IsLocked()) for u,t in live.items()}
        try:
            for uid,t in live.items():
                if uid not in row['source_track_uuids']: t.SetLocked(True)
            result = fr.chamfer_unlocked_right_angles(board,
                max_chamfer_mm=proposal['maximum_nm']/1e6, min_chamfer_mm=proposal['minimum_nm']/1e6,
                max_width_mm=10., allow_locked_track_uuids=row['source_track_uuids'] if proposal['allow_locked_source'] else (),
                exclude_nets={str(t.GetNetname()) for t in live.values()}-{row['net']},
                timeout_s=min(10., max(.001,deadline-time.monotonic())), max_corners=8192, max_chamfers=1)
        finally:
            for t in board.GetTracks():
                if force._uid(t) in locks: t.SetLocked(locks[force._uid(t)])
        if result['chamfered'] != 1: raise ValueError('full_current_native_contact_or_clearance_refused')
        details.append(dict(request=row, native_geometry=result))
    changed = {force._uid(t) for t in board.GetTracks() if force._uid(t) in old and
        (tuple(t.GetStart()),tuple(t.GetEnd())) != old[force._uid(t)]}
    if changed != cut: raise ValueError('exact_full_current_corner_cut_not_materialized')
    replacement = []
    for uid in sorted(changed):
        t = source_items[uid]; new = t.Duplicate(); new.m_Uuid.Clone(pcbnew.KIID()); board.Add(new); replacement.append(t)
    discard_items(board, replacement)
    additive._ground_refill(board)
    if time.monotonic() >= deadline: raise ValueError('full_current_corner_construction_deadline')
    return dict(retired_track_uuids=sorted(cut), added_native_uuids=sorted(
        force._uid(t) for t in board.GetTracks() if force._uid(t) not in source_items),
        chamfered=len(details), details=details, current_budget_changed=False, release_authority=False)


def _visible_removed(parent, old, new, retired, *, deadline):
    face = int(old[0].GetLayer()); net = str(old[0].GetNetname()); removed = pcbnew.SHAPE_POLY_SET()
    def polygon(item, error):
        poly = pcbnew.SHAPE_POLY_SET(); item.TransformShapeToPolygon(poly, face, 0, 1000, error)
        fills.identity(poly, deadline); return poly
    for t in old: removed.BooleanAdd(polygon(t, pcbnew.ERROR_INSIDE))
    for t in new: removed.BooleanSubtract(polygon(t, pcbnew.ERROR_OUTSIDE))
    witnesses = []
    shapes = [t.GetEffectiveShape(face) for t in old]
    material = [*parent.GetTracks(), *(p for fp in parent.GetFootprints() for p in fp.Pads()), *parent.Zones()]
    if len(material) > 16384: raise ValueError('visible_full_current_corner_material_bound')
    for item in material:
        if time.monotonic() >= deadline: raise ValueError('visible_full_current_corner_deadline')
        uid = force._uid(item)
        if uid in retired or str(item.GetNetname()) != net or not item.IsOnLayer(face): continue
        if item.GetClass() == 'ZONE':
            if item.GetIsRuleArea(): continue
            if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                raise ValueError('unknown_same_net_fill_cannot_prove_visible_corner_progress')
            poly = item.GetFilledPolysList(face); fills.identity(poly, deadline)
        else:
            if not any(s.Collide(item.GetEffectiveShape(face), 0) for s in shapes): continue
            poly = polygon(item, pcbnew.ERROR_OUTSIDE)
        removed.BooleanSubtract(poly); witnesses.append(uid)
    if not removed.OutlineCount(): raise ValueError('full_current_corner_change_hidden_by_retained_native_copper')
    digest, vertices = fills.identity(removed, deadline)
    return dict(ok=True, complete=True, removed_native_polygon_sha256=digest, removed_native_vertices=vertices,
        retained_contact_and_fill_uuids=sorted(witnesses), polygon_error_nm=1000,
        method='inside_old_minus_outside_new_retained_contacts_and_actual_native_fills', release_authority=False)


def receive(source, candidate, proposal, *, board_hint):
    result = dict(ok=False, complete=False, errors=[], release_authority=False, current_qualified=False)
    try:
        source, candidate = map(Path, (source, candidate)); epoch = force._code_identity()
        families = [force._family(path, board_hint) for path in (source,candidate)]
        parent, child = [pcbnew.LoadBoard(str(path)) for path in (source,candidate)]
        settings = {k:proposal[k] for k in ('allow_locked_source','maximum_nm','minimum_nm')}
        if plan(parent, source, proposal['requests'], board_hint=board_hint, **settings) != proposal:
            raise ValueError('saved_full_current_corner_source_plan_changed')
        _, old = additive._nodes(source); got_root, got = additive._nodes(candidate)
        retired = set(old)-set(got); added = set(got)-set(old)
        if retired != set(proposal['full_current_proposal']['retired_track_uuids']):
            raise ValueError('saved_full_current_corner_cut_changed')
        with tempfile.TemporaryDirectory(prefix='cec-full-current-corner-') as tmp:
            expected_path = force._copy_family(source, Path(tmp)/'expected')
            expected = pcbnew.LoadBoard(str(expected_path))
            q = plan(expected, expected_path, proposal['requests'], board_hint=board_hint, **settings)
            made = materialize(expected, expected_path, q, board_hint=board_hint)
            field._save_field_snapshot(expected, expected_path); want_root, want = additive._nodes(expected_path)
            want_added = set(want)-set(old)
            if (signatures._header(want_root,want) != signatures._header(got_root,got) or
                    set(want)&set(old) != set(got)&set(old) or
                    any(syntax._freeze(want[u]) != syntax._freeze(got[u]) for u in set(want)&set(old)) or
                    Counter(signatures._signature(want[u]) for u in want_added) !=
                    Counter(signatures._signature(got[u]) for u in added)):
                raise ValueError('exact_independent_saved_full_current_corner_replay_differs')
        proof = full.receive(source,candidate,board_hint=board_hint,retired_track_uuids=sorted(retired),
            max_source_track_mm=32.,max_source_cut_mm=48.)
        result['independent_full_current_planar_receiving'] = proof
        if not proof['ok'] or not proof['complete']: raise ValueError('full_current_corner_owner_refused:'+str(proof['errors']))
        before = {force._uid(t):t for t in parent.GetTracks()}; after = {force._uid(t):t for t in child.GetTracks()}
        old_items = [before[u] for u in sorted(retired)]; new_items = [after[u] for u in sorted(added)]
        delta = sum(t.GetLength() for t in old_items)-sum(t.GetLength() for t in new_items)
        if delta <= 0: raise ValueError('full_current_corner_must_strictly_shorten_actual_tracks')
        visible = _visible_removed(parent,old_items,new_items,retired,deadline=time.monotonic()+10.)
        if epoch != force._code_identity() or families != [force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('full_current_corner_source_family_or_code_changed')
        result.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate),retired_track_uuids=sorted(retired),added_native_uuids=sorted(added),
            source_family_and_code_unchanged=True,chamfered=made['chamfered'],saved_trace_length_mm=delta/1e6,
            actual_visible_native_material_removed=visible,source_width_face_and_current_exact=True,
            new_holes=0,new_vias=0,ordinary_reclassification=False,
            full_native_current_field_absolute_cuts_pairs_stack_and_release_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
