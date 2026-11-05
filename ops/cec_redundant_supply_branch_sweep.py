"""Finite finishing search for obsolete, already full-load supply branches.

Endpoint graphs propose complete small paths, not deletion permission. The
unchanged distributed-supply receiver must prove every retained native and
full-load terminal partition, original boundary, current contract and source
item. Saved native DRC then rejects dangling tails or new faults. No board,
reference, net-name, coordinate, guessed load or barrel-sharing special case.
"""
import argparse
from collections import defaultdict,deque
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_additive_portal_compaction as portal
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
import cec_redundant_rated_branch as owner
import cec_route_quality as quality
import cec_stage_admission as admission
import cec_native_retirement_screen as retirement_screen
from cec_native_items import discard_items


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_requests(board, source, *, board_hint, allow_locked_source=False,
                    max_requests=24, max_path_tracks=8, include_source_subpaths=False,
                    max_source_width_mm=.35):
    source_ceiling=owner.rated.source_width_mm(max_source_width_mm)
    require(type(allow_locked_source) is bool and type(max_requests) is int
        and 1 <= max_requests <= 32 and type(max_path_tracks) is int
        and 1 <= max_path_tracks <= 8 and type(include_source_subpaths) is bool,
        'finite_explicit_supply_branch_search_required')
    require(Path(board.GetFileName()).resolve() == Path(source).resolve()
        and type(board_hint) is str and bool(board_hint), 'actual_supply_branch_source_required')
    epoch = force._code_identity()
    family = force._family(source, board_hint)
    with force._thermal_hint(board_hint):
        catalog = owner.rated.topology.distributed_supply_contracts(board, board_hint,
            netclass_resolver=owner.rated.fr._project_netclass_resolver(str(source)))
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    _, nodes = additive._nodes(source)
    tracks = {}
    for t in board.GetTracks():
        uid = force._uid(t)
        if (t.GetClass() != 'PCB_TRACK' or uid in grouped or t.GetParentGroup()
                or t.HasSolderMask() or t.IsLocked() and not allow_locked_source
                or t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)
                or not 0 < t.GetLength() <= 8000000 or not 0 < t.GetWidth() <= math.floor(source_ceiling*1e6)):
            continue
        contract = catalog['contracts'].get(str(t.GetNetname())) or {}
        authority = contract.get('current_authority') or {}
        floor = contract.get('required_by_layer_mm', {}).get(board.GetLayerName(t.GetLayer()))
        fields = {q[0] if isinstance(q, list) else q for q in nodes[uid][1:]}
        if (contract.get('role') != 'all_terminal_conservative_aggregate'
                or type(authority.get('amps')) not in (int, float)
                or not math.isfinite(authority['amps']) or authority['amps'] <= 0
                or type(floor) not in (int, float) or not math.isfinite(floor)
                or not 0 < math.ceil(floor*1e6) <= t.GetWidth()
                or not fields <= {'start', 'end', 'width', 'layer', 'net', 'uuid', 'locked'}):
            continue
        tracks[uid] = t
    require(len(tracks) <= 16384, 'supply_branch_inventory_bound')
    incident = defaultdict(set)
    for uid, t in tracks.items():
        for at in (tuple(t.GetStart()), tuple(t.GetEnd())):
            incident[(t.GetNetCode(), int(t.GetLayer()), int(t.GetWidth()), at)].add(uid)
    audit = quality.analyze_board(board, min_open_angle_deg=134.999)
    scopes = set()
    refused = []
    subpath_limit_reached=False
    for issue in audit['issues']:
        seed = set(issue['track_uuids'])
        if not seed <= tracks.keys():
            continue
        if include_source_subpaths:
            if len(seed)>max_path_tracks:continue
            # Maximal degree-two paths may include an essential continuation
            # even though a shorter prefix is obsolete. Enumerate bounded
            # exact subpaths too; no endpoint/overlap graph grants a cut.
            pending_scopes=deque([frozenset(seed)]);local_seen=set()
            while pending_scopes and len(scopes)<128:
                selected=pending_scopes.popleft()
                if selected in local_seen:continue
                local_seen.add(selected);scopes.add(tuple(sorted(selected)))
                if len(selected)>=max_path_tracks:continue
                for uid in sorted(selected):
                    t=tracks[uid]
                    for at in (tuple(t.GetStart()),tuple(t.GetEnd())):
                        peers=incident[(t.GetNetCode(),int(t.GetLayer()),int(t.GetWidth()),at)]
                        if len(peers)==2:
                            for other in sorted(peers-selected):
                                pending_scopes.append(selected|{other})
            if pending_scopes:subpath_limit_reached=True
        # Follow degree-two exact endpoint paths as a whole. A body contact,
        # pad, near miss, locked/grouped neighbor or arbitrary proximity is
        # never inferred as a graph edge or deletion authority.
        scope = set(seed)
        pending = list(sorted(seed))
        while pending and len(scope) <= max_path_tracks:
            t = tracks[pending.pop()]
            for at in (tuple(t.GetStart()), tuple(t.GetEnd())):
                peers = incident[(t.GetNetCode(), int(t.GetLayer()), int(t.GetWidth()), at)]
                if len(peers) == 2:
                    for uid in sorted(peers-scope):
                        scope.add(uid)
                        pending.append(uid)
        if len(scope) > max_path_tracks:
            refused.append(dict(reason='whole_source_path_exceeds_finite_work_bound',
                source_track_uuids=sorted(seed)))
            continue
        key=tuple(sorted(scope))
        if include_source_subpaths and key not in scopes and len(scopes)>=128:
            subpath_limit_reached=True
            continue
        scopes.add(key)
    requests = []
    for scope in sorted(scopes):
        rows = [tracks[u] for u in scope]
        if len({(t.GetNetCode(), int(t.GetLayer())) for t in rows}) != 1:
            continue
        affected = sum(bool(set(q['track_uuids']) & set(scope)) for q in audit['issues'])
        requests.append(dict(net=str(rows[0].GetNetname()), source_track_uuids=list(scope),
            allow_locked_track_uuids=sorted(force._uid(t) for t in rows if t.IsLocked()),
            observed_source_bends_touched=affected,
            source_length_mm=sum(t.GetLength() for t in rows)/1e6))
    # Avoid spending the strongest current/drilled-copper receivers on
    # repeatedly essential paths while a short redundant path waits behind
    # long ones. A screen only ranks effort: uncertainty is kept, and every
    # selected candidate still runs all original independent receivers.
    screen_deadline=time.monotonic()+8.
    for request in requests:
        lease=min(.25,screen_deadline-time.monotonic())
        request['native_retirement_effort_screen']=(retirement_screen.screen(board,
            request['source_track_uuids'],timeout_s=lease) if lease>.001 else dict(state='unknown',complete=False,
            reason='finite_discovery_screen_work_budget',admission_or_deletion_authority=False))
    rank={'preserved':0,'unknown':1,'lost':2}
    requests.sort(key=lambda r: (rank[r['native_retirement_effort_screen']['state']],-r['observed_source_bends_touched'],
        -r['source_length_mm'], r['source_track_uuids']))
    require(epoch == force._code_identity() and family == force._family(source, board_hint),
        'supply_branch_source_changed_during_read_only_discovery')
    return dict(requests=requests[:max_requests], skipped=refused,
        finite_request_bound=max_requests, whole_path_track_bound=max_path_tracks,
        requests_outside_work_bound=max(0, len(requests)-max_requests),
        source_bend_count=len(audit['issues']), source_mutated=False,
        source_subpaths_included=include_source_subpaths,
        source_subpath_window_bound=128,source_subpath_window_bound_reached=subpath_limit_reached,
        explicit_source_width_work_ceiling_mm=source_ceiling,
        deletion_or_current_authority_granted=False)


def removed_material(parent, child, scope):
    """Positive lower bound, not an area tolerance or current-capacity claim."""
    deadline = time.monotonic()+10.
    live = {force._uid(t): t for t in parent.GetTracks()}
    cut = [live[u] for u in scope]
    net = cut[0].GetNetCode(); face = cut[0].GetLayer()
    missing = pcbnew.SHAPE_POLY_SET()
    for t in cut:
        p = pcbnew.SHAPE_POLY_SET()
        t.TransformShapeToPolygon(p, face, 0, 1, pcbnew.ERROR_INSIDE, False)
        missing.BooleanAdd(p)
    peers = [*child.GetTracks(), *(p for f in child.GetFootprints() for p in f.Pads()), *child.Zones()]
    for item in peers:
        require(time.monotonic() < deadline, 'supply_branch_material_observation_deadline')
        if item.GetNetCode() != net or not item.IsOnLayer(face):
            continue
        if item.GetClass() == 'ZONE':
            if item.GetIsRuleArea():
                continue
            require(item.IsFilled() and item.HasFilledPolysForLayer(face),
                'supply_branch_actual_fill_unknown')
            p = item.GetFilledPolysList(face)
        else:
            p = pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(p, face, 0, 1, pcbnew.ERROR_OUTSIDE, False)
        missing.BooleanSubtract(p)
        if not missing.OutlineCount():
            return dict(positive_material_removed=False, release_authority=False)
    # Raw land set difference alone can count substrate cut-outs or drill
    # voids as "removed copper". Intersect actual substrate and subtract all
    # physical bores, including netless/foreign NPTHs, before claiming gain.
    import cec_board_geometry as geometry
    import cec_kelvin_copper_cut as drills
    missing.BooleanIntersection(geometry.outline_material(parent))
    checked_holes = 0
    for item in [*child.GetTracks(), *(p for f in child.GetFootprints() for p in f.Pads())]:
        require(time.monotonic() < deadline, 'supply_branch_drill_observation_deadline')
        if item.GetClass() != 'PCB_VIA' and not (item.GetClass() == 'PAD' and item.HasHole()):
            continue
        require(drills._simple_drill(item, tuple(child.GetEnabledLayers().CuStack())),
            'actual_simple_supply_cleanup_bore_required')
        hole = pcbnew.SHAPE_POLY_SET()
        item.GetEffectiveHoleShape().TransformToPolygon(hole, 1, pcbnew.ERROR_OUTSIDE)
        require(bool(hole.OutlineCount()), 'supply_cleanup_native_bore_polygon_unavailable')
        missing.BooleanSubtract(hole); checked_holes += 1
    return dict(positive_material_removed=bool(missing.OutlineCount()),
        lower_bound_area_mm2=missing.Area()/1e12, native_curve_error_nm=1,
        actual_substrate_intersection_and_global_bores_subtracted=True,
        actual_native_bores_checked=checked_holes,
        full_current_capacity_not_inferred=True, release_authority=False)


def extend_causal_tail_scope(parent, source, scope, violations, *, board_hint,
                            allow_locked_source=False,max_source_width_mm=.35):
    """Only native-identified original plain tails may join the next trial.

    This is neither warning suppression nor deletion admission. The next
    saved candidate is reconstructed from the ORIGINAL parent and the whole
    enlarged cut must pass the unchanged full-load receiver and native DRC.
    """
    require(type(allow_locked_source) is bool and type(violations) is list
        and 1 <= len(violations) <= 8, 'finite_actual_native_tail_faults_required')
    old = set(owner.ordinary._ids(scope, 'causal_supply_tail_scope', 8))
    live = {force._uid(t):t for t in parent.GetTracks()}
    require(bool(old) and old <= live.keys(), 'actual_original_supply_path_scope_required')
    net_face = {(live[u].GetNetCode(), int(live[u].GetLayer())) for u in old}
    require(len(net_face) == 1, 'one_source_supply_face_for_causal_tails_required')
    incoming = set()
    for fault in violations:
        require(type(fault) is dict and fault.get('type') == 'track_dangling'
            and type(fault.get('items')) is list and 1 <= len(fault['items']) <= 8,
            'only_actual_native_dangling_track_faults_are_causal_tail_requests')
        for item in fault['items']:
            require(type(item) is dict and type(item.get('uuid')) is str,
                'actual_native_tail_identity_required')
            incoming.add(item['uuid'])
    require(bool(incoming) and not old & incoming and incoming <= live.keys()
        and len(old | incoming) <= 8, 'causal_tail_original_inventory_or_work_bound_refused')
    grouped = {force._uid(i) for g in parent.Groups() for i in g.GetItems()}
    _, nodes = additive._nodes(source)
    for uid in incoming:
        t = live[uid]
        fields = {q[0] if isinstance(q, list) else q for q in nodes[uid][1:]}
        require(t.GetClass() == 'PCB_TRACK' and not t.HasSolderMask()
            and uid not in grouped and not t.GetParentGroup()
            and (not t.IsLocked() or allow_locked_source)
            and (t.GetNetCode(), int(t.GetLayer())) in net_face
            and fields <= {'start','end','width','layer','net','uuid','locked'},
            'causal_tail_has_no_plain_compatible_original_source_scope')
    result = sorted(old | incoming)
    owner.rated.plan(parent, source, board_hint=board_hint, retired_track_uuids=result,
        max_source_track_mm=8., max_retired_tracks=8, max_source_width_mm=max_source_width_mm)
    return result


def extend_causal_covered_scope(parent,source,scope,candidate,*,board_hint,allow_locked_source=False,max_source_width_mm=.35):
    """Propose only an exact original capsule hidden by a retained peer.

    A cut can expose an old collinear duplicate as a new backtrack. Do not
    accept a lower broad bend count while introducing another craft fault.
    The enlarged original-parent cut must still repeat every full-load gate.
    """
    require(type(allow_locked_source) is bool,'explicit_causal_covered_source_lock_scope_required')
    cut=set(owner.ordinary._ids(scope,'causal_covered_supply_cut',8))
    child=pcbnew.LoadBoard(str(candidate));live={force._uid(t):t for t in parent.GetTracks()}
    retained={force._uid(t):t for t in child.GetTracks()}
    key=lambda row:(row['type'],row['net'],row['layer'],tuple(row['at_mm']),tuple(sorted(row['track_uuids'])))
    known={key(row) for row in quality.analyze_board(parent)['issues']}
    fresh=[row for row in quality.analyze_board(child)['issues'] if key(row) not in known]
    require(1<=len(fresh)<=8 and cut<=live.keys(),'actual_new_bounded_craft_faults_required_for_covered_cleanup')
    grouped={force._uid(i) for g in parent.Groups() for i in g.GetItems()}
    _,nodes=additive._nodes(source);extra=set();witnesses={}
    def stroke(t):
        return (t.GetClass(),t.GetNetname(),int(t.GetLayer()),int(t.GetWidth()),
            tuple(t.GetStart()),tuple(t.GetEnd()),bool(t.IsLocked()),bool(t.HasSolderMask()))
    for fault in fresh:
        require(fault['type']=='covered_backtrack' and len(fault['track_uuids'])==2,
            'only_exact_new_covered_backtracks_have_a_causal_source_cut')
        ids=set(fault['track_uuids'])
        require(ids<=live.keys() and ids<=retained.keys() and not ids&cut,
            'covered_cleanup_must_use_literal_retained_original_source_tracks')
        pair=sorted((live[u] for u in ids),key=lambda t:(t.GetLength(),force._uid(t)))
        small,large=pair;uid=force._uid(small);peer=force._uid(large)
        require(all(t.GetClass()=='PCB_TRACK' and stroke(t)==stroke(retained[force._uid(t)]) for t in pair),
            'covered_cleanup_candidate_cannot_modify_original_source_strokes')
        fields={q[0] if isinstance(q,list) else q for q in nodes[uid][1:]}
        require(uid not in grouped and not small.GetParentGroup() and not small.HasSolderMask()
            and (not small.IsLocked() or allow_locked_source)
            and fields<={'start','end','width','layer','net','uuid','locked'}
            and portal._covered_by_source(small,[large])==peer,
            'complete_exact_native_capsule_coverage_and_source_ownership_required')
        extra.add(uid);witnesses[uid]=peer
    result=sorted(cut|extra)
    require(bool(extra) and len(result)<=8 and not (cut|extra)&set(witnesses.values()),
        'covered_cleanup_requires_a_retained_cover_and_the_original_cut_bound')
    owner.rated.plan(parent,source,board_hint=board_hint,retired_track_uuids=result,
        max_source_track_mm=8.,max_retired_tracks=8,max_source_width_mm=max_source_width_mm)
    return result


def run(source, out, *, board_hint, grade, expected_source_sha256,
        reporting_build, allow_locked_source=False, max_trials=16, cut_receive_timeout_s=10.,
        include_source_subpaths=True,max_source_width_mm=.35):
    source_ceiling=owner.rated.source_width_mm(max_source_width_mm)
    source = Path(source).resolve(); out = Path(out)
    require(not out.exists() and type(max_trials) is int and 1 <= max_trials <= 32,
        'fresh_finite_supply_branch_sweep_required')
    require(type(cut_receive_timeout_s) in (int, float) and math.isfinite(cut_receive_timeout_s)
        and 0 < cut_receive_timeout_s <= 30, 'finite_existing_supply_cut_receiving_lease_required')
    require(force._hash(source) == expected_source_sha256, 'supply_branch_source_hash_mismatch')
    epoch = force._code_identity(); family = force._family(source, board_hint)
    inputs = {str(Path(__file__).resolve()): force._hash(Path(__file__)),
        str(Path(retirement_screen.__file__).resolve()):force._hash(Path(retirement_screen.__file__)),
        str(Path(grade).resolve()): force._hash(Path(grade))}
    grade = json.loads(Path(grade).read_text())
    require(grade['code_identity'] == epoch, 'source_grade_code_changed')
    side = next(k for k in ('candidate', 'source') if grade['boards'][k]['sha256'] == force._hash(source))
    producer = grade['boards'][side]['native_producer']
    require(producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated'],
        'complete_uncapped_source_native_report_required')
    report = Path(producer['report'])
    require(force._hash(report) == producer['report_sha256'], 'source_native_report_hash_changed')
    inputs[str(report.resolve())] = producer['report_sha256']
    baseline = json.loads(report.read_text())
    prior = {admission._canonical_identity(v) for v in baseline['violations']}
    parent = pcbnew.LoadBoard(str(source))
    source_default=quality.analyze_board(parent)
    craft_key=lambda row:(row['type'],row['net'],row['layer'],tuple(row['at_mm']),tuple(sorted(row['track_uuids'])))
    source_default_keys={craft_key(row) for row in source_default['issues']}
    inventory = source_requests(parent, source, board_hint=board_hint,
        allow_locked_source=allow_locked_source, max_requests=max_trials,
        include_source_subpaths=include_source_subpaths,max_source_width_mm=source_ceiling)
    out.mkdir()
    result = dict(ok=False, complete=False, changed=False, errors=[], source=str(source),
        source_sha256=force._hash(source), code_identity=epoch, input_sha256=inputs,
        inventory=inventory, attempts=[], source_selected=False, routing_admitted=False,
        fab_ready=False, release_authority=False)
    for index, request in enumerate(inventory['requests']):
        row = dict(request=request, accepted=False); result['attempts'].append(row)
        try:
            cut = set(request['source_track_uuids'])
            params = dict(retired_track_uuids=sorted(cut),
                allow_locked_track_uuids=request['allow_locked_track_uuids'], timeout_s=cut_receive_timeout_s,
                max_source_track_mm=8., max_retired_tracks=8, max_source_width_mm=source_ceiling,
                allow_rated_source_inner_layers=False)
            row['causal_tail_trials'] = []
            for closure in range(5):
                # Every causal retry starts from the same immutable source,
                # never from an unadmitted dangling-prefix candidate.
                child = force._copy_family(source, out/('UNADMITTED-obsolete-supply-path-'+str(index)+'-tail-'+str(closure)))
                board = pcbnew.LoadBoard(str(child))
                params['retired_track_uuids'] = sorted(cut)
                params['allow_locked_track_uuids'] = sorted(u for u in cut if
                    next(t for t in parent.GetTracks() if force._uid(t) == u).IsLocked())
                owner.rated.plan(parent, source, board_hint=board_hint,
                    **{k:v for k,v in params.items() if k not in ('allow_locked_track_uuids', 'timeout_s')},
                    timeout_s=min(10., cut_receive_timeout_s))
                discard_items(board, [t for t in board.GetTracks() if force._uid(t) in cut])
                additive._ground_refill(board); field._save_field_snapshot(board, child)
                # The SAME saved-geometry improvement predicate was formerly
                # evaluated only after expensive full-current receiving. A
                # losing saved shape cannot be accepted later in this trial;
                # reject it before funding native/current work. This is not
                # an acceptance shortcut: every surviving offer still runs
                # all original independent receivers and native DRC below.
                saved = pcbnew.LoadBoard(str(child))
                bends = quality.analyze_board(saved, min_open_angle_deg=134.999)
                trial = dict(cut=sorted(cut), saved_geometry_preflight=dict(
                    candidate_sha256=force._hash(child), source_bend_count=inventory['source_bend_count'],
                    candidate_bend_count=len(bends['issues']), independent_current_receiving_run=False,
                    acceptance_or_current_authority_granted=False))
                row['causal_tail_trials'].append(trial)
                row['remaining_bend_count'] = len(bends['issues'])
                require(len(bends['issues']) < inventory['source_bend_count'], 'no_observed_bend_improvement')
                # A different primitive count can be invisible because a
                # retained pad/via/peer already covers all retired copper.
                # Reject that non-polish BEFORE the expensive current proof.
                # Positive lower material bounds still subtract substrate and
                # every real bore, and grant no cut/capacity authority.
                material=removed_material(parent,saved,sorted(cut));row['material']=material
                trial['saved_geometry_preflight']['actual_native_material_observation']=material
                require(material['positive_material_removed'],'only_representation_changed_not_physical_polish')
                proof = owner.receive(source, child, board_hint=board_hint, **params)
                trial['independent_full_load_cut'] = proof
                trial['saved_geometry_preflight']['independent_current_receiving_run'] = True
                require(proof['ok'] and proof['complete'] and not proof['errors'], str(proof['errors']))
                require(force._hash(child)==trial['saved_geometry_preflight']['candidate_sha256'],
                    'saved_shape_changed_during_independent_current_receiving')
                actual_default=quality.analyze_board(saved)
                new_default=[q for q in actual_default['issues'] if craft_key(q) not in source_default_keys]
                trial['new_default_craft_issues']=new_default
                if new_default:
                    require(closure<4,'finite_native_causal_craft_retry_bound')
                    extended=set(extend_causal_covered_scope(parent,source,sorted(cut),child,
                        board_hint=board_hint,allow_locked_source=allow_locked_source,max_source_width_mm=source_ceiling))
                    trial['causal_exact_covered_source_tracks']=sorted(extended-cut)
                    cut=extended
                    print(json.dumps(dict(attempt=index,exact_covered_source_retry=closure+1,
                        whole_original_cut_tracks=len(cut))),flush=True)
                    continue
                require(actual_default['non_octilinear_count']<=source_default['non_octilinear_count'],
                    'new_default_non_octilinear_geometry_refused')
                require(force._hash(child)==trial['saved_geometry_preflight']['candidate_sha256'],
                    'material_or_native_craft_observation_changed_saved_candidate')
                shadow = force._copy_family(child, out/('native-input-'+str(index)+'-tail-'+str(closure)))
                report = out/('native-'+str(index)+'-tail-'+str(closure)+'.json')
                produced = native.run(shadow, report, reporting_build=Path(reporting_build), timeout_s=10.)
                require(produced['ok'] and produced['complete'] and not produced['native_inventory']['potentially_truncated'],
                    'complete_saved_candidate_native_report_required')
                after = json.loads(report.read_text())
                fresh = [v for v in after['violations'] if admission._canonical_identity(v) not in prior]
                trial.update(new_native_faults=fresh, opens=len(after['unconnected_items']), native_producer=produced)
                require(not trial['opens'], 'native_open_refused')
                if not fresh:
                    row.update(independent_full_load_cut=proof, new_native_faults=[], opens=0,
                        native_producer=produced)
                    break
                require(closure < 4, 'finite_native_causal_tail_retry_bound')
                cut = set(extend_causal_tail_scope(parent, source, sorted(cut), fresh,
                    board_hint=board_hint, allow_locked_source=allow_locked_source,max_source_width_mm=source_ceiling))
                print(json.dumps(dict(attempt=index, native_causal_tail_retry=closure+1,
                    whole_original_cut_tracks=len(cut))), flush=True)
            row['accepted'] = True
            result.update(ok=True, changed=True, candidate=str(child), candidate_sha256=force._hash(child),
                records=[dict(plan=params, materialized=dict(retired_track_uuids=sorted(cut),
                    added_native_uuids=[]))], actual_removed_material=material,
                source_bend_count=inventory['source_bend_count'], remaining_bend_count=len(bends['issues']))
            break
        except (ValueError, RuntimeError) as exc:
            row['refusal'] = str(exc)
        print(json.dumps(dict(attempt=index, accepted=row['accepted'], refusal=row.get('refusal'))), flush=True)
    require(epoch == force._code_identity() and family == force._family(source, board_hint),
        'supply_branch_source_family_or_code_changed')
    require(all(force._hash(Path(p)) == h for p,h in inputs.items()), 'supply_branch_input_or_tool_changed')
    result.update(complete=True, source_family_and_code_unchanged=True)
    if not result['ok']:
        result['errors'] = ['finite_obsolete_supply_path_domain_exhausted']
    force._write(out/'stage.json', result)
    return result


def main():
    import cec_swig_guard
    cec_swig_guard.pin()
    import wx
    quiet = wx.LogNull()
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'out', 'grade', 'reporting-build'):
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--hint', required=True)
    p.add_argument('--expected-source-sha256', required=True)
    p.add_argument('--allow-locked-source', action='store_true')
    p.add_argument('--max-trials', type=int, default=16)
    p.add_argument('--max-source-width-mm',type=float,default=.35,
        help='Explicit finite source geometry work ceiling, at most 1 mm; unchanged current/catalog receiving remains mandatory')
    p.add_argument('--whole-paths-only',action='store_true',help='Disable bounded source subpaths; original full-load receivers remain mandatory either way')
    p.add_argument('--cut-receive-timeout-s', type=float, default=10.,
        help='Explicit bounded lease for the unchanged receiver, at most 30 seconds; no gate bypass')
    a = p.parse_args()
    r = run(a.source, a.out, board_hint=a.hint, grade=a.grade,
        expected_source_sha256=a.expected_source_sha256, reporting_build=a.reporting_build,
        allow_locked_source=a.allow_locked_source, max_trials=a.max_trials,
        cut_receive_timeout_s=a.cut_receive_timeout_s,include_source_subpaths=not a.whole_paths_only,
        max_source_width_mm=a.max_source_width_mm)
    print(json.dumps(dict(report=str(a.out/'stage.json'), ok=r['ok'], changed=r['changed'],
        attempts=len(r['attempts']))), flush=True)


if __name__ == '__main__':
    main()
