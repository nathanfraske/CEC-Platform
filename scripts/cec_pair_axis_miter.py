"""Balanced, fixed-port axis-corner refinement of an existing paired draft.

One actual hard 90 and its partner's existing axis/45/axis miter each lose
the SAME exact radical length. Native pair/current/field/fabrication release
checks remain unchanged. An explicit draft-only mode can preserve an already
unsupported source face ONLY with unchanged ground sheets and no additional
physical reference deficit; that mode never qualifies the face or the pair.
"""
import math
import tempfile
import time
from collections import defaultdict
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_pair_local_reference_refinement as owner
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_route_quality as quality
import cec_fr as fr
import cec_native_rule_areas as rules
import cec_paired_route_reconstruction as whole_pair
from cec_native_items import discard_items


def _unit(a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    if (dx == 0) == (dy == 0):
        raise ValueError('nonzero_literal_cardinal_miter_leg_required')
    return (0 if dx == 0 else (1 if dx > 0 else -1), 0 if dy == 0 else (1 if dy > 0 else -1))


def frame(hard, partner, width_nm):
    if (type(width_nm) is not int or not 0 < width_nm <= 1000000
            or type(hard) not in (list, tuple) or len(hard) != 3
            or type(partner) not in (list, tuple) or len(partner) != 4
            or any(type(p) not in (list, tuple) or len(p) != 2
                   or any(type(v) is not int or abs(v) > 2000000000 for v in p) for p in [*hard, *partner])):
        raise ValueError('bounded_literal_two_member_axis_miter_frame_required')
    hard, partner = [list(p) for p in hard], [list(p) for p in partner]
    u, v = _unit(hard[0], hard[1]), _unit(hard[1], hard[2])
    if sum(x*y for x, y in zip(u, v)) or _unit(partner[0], partner[1]) != u or _unit(partner[2], partner[3]) != v:
        raise ValueError('same_oriented_cardinal_pair_corners_required')
    corner = [partner[1][i] if u[i] == 0 else partner[2][i] for i in (0, 1)]
    first = sum((corner[i]-partner[1][i])*u[i] for i in (0, 1))
    last = sum((partner[2][i]-corner[i])*v[i] for i in (0, 1))
    if first != last or first <= 0:
        raise ValueError('literal_equal_axis_existing_partner_miter_required')
    return dict(hard_points_nm=hard, partner_points_nm=partner, width_nm=width_nm,
                incoming_direction=list(u), outgoing_direction=list(v),
                partner_corner_nm=corner, partner_source_retreat_nm=first)


def replacements(source_frame, retreat_nm):
    f = source_frame
    if f != frame(f.get('hard_points_nm'), f.get('partner_points_nm'), f.get('width_nm')):
        raise ValueError('actual_literal_source_axis_miter_frame_required')
    if type(retreat_nm) is not int or not 20000 <= retreat_nm <= 200000:
        raise ValueError('bounded_explicit_balanced_axis_retreat_required')
    # sqrt(2)*r - width/sqrt(2) is the ACTUAL inner flat, not an
    # invisible centerline-only bend. This is an exact integer inequality.
    visible_axis = 2*retreat_nm-f['width_nm']
    if visible_axis <= 0 or visible_axis**2 < 2*20000**2:
        raise ValueError('real_visible_inside_pair_miter_flat_required')
    paths = []
    u, v = f['incoming_direction'], f['outgoing_direction']
    for old, corner, r in ((f['hard_points_nm'], f['hard_points_nm'][1], retreat_nm),
                            (f['partner_points_nm'], f['partner_corner_nm'], f['partner_source_retreat_nm']+retreat_nm)):
        p = [old[0], [corner[i]-u[i]*r for i in (0, 1)], [corner[i]+v[i]*r for i in (0, 1)], old[-1]]
        if (sum((p[1][i]-p[0][i])*u[i] for i in (0, 1)) < 20000
                or sum((p[3][i]-p[2][i])*v[i] for i in (0, 1)) < 20000):
            raise ValueError('balanced_axis_miter_requires_retained_native_leg_floor')
        paths.append(p)
    return paths, dict(exact_equal_member_shortening=True, exact_skew_unchanged=True,
        cardinal_length_removed_nm_each=2*retreat_nm, diagonal_axis_added_nm_each=retreat_nm,
        each_shortening_expression='retreat_nm*(2-sqrt(2))', fixed_native_ports=True,
        visible_inner_flat_minimum_nm=20000, numerical_or_sampling_waiver_used=False)


def discover(board, source, pair, *, allow_locked_source=False):
    if type(allow_locked_source) is not bool:
        raise ValueError('explicit_balanced_axis_source_lock_policy_required')
    deadline = time.monotonic()+10.
    live = {force._uid(t): t for t in board.GetTracks()}
    if len(live) > 16384:
        raise ValueError('bounded_balanced_axis_source_inventory_required')
    _, nodes = additive._nodes(source)
    result = []
    for corner in owner.bend_inventory(board, pair)['selected']:
        hard = [live[u] for u in corner['source_track_uuids']]
        try:
            points = owner._chain(hard)
            if len(points) != 3:
                continue
            u, v = _unit(points[0], points[1]), _unit(points[1], points[2])
        except ValueError:
            continue
        other = pair['n'] if corner['net'] == pair['p'] else pair['p']
        rows = [t for t in live.values() if t.GetClass() == 'PCB_TRACK' and t.GetNetname() == other
                and int(t.GetLayer()) == corner['layer']]
        incidence = defaultdict(list)
        for t in rows:
            for point in (tuple(t.GetStart()), tuple(t.GetEnd())):
                incidence[point].append(t)
        for middle in rows:
            if time.monotonic() >= deadline:
                raise ValueError('balanced_axis_source_inventory_deadline')
            ends = [tuple(middle.GetStart()), tuple(middle.GetEnd())]
            dx, dy = ends[1][0]-ends[0][0], ends[1][1]-ends[0][1]
            if not dx or abs(dx) != abs(dy) or any(len(incidence[p]) != 2 for p in ends):
                continue
            partner = [middle]+[next(t for t in incidence[p] if force._uid(t) != force._uid(middle)) for p in ends]
            try:
                other_points = owner._chain(partner)
                candidates = (other_points, other_points[::-1])
                f = next(frame(points, p, hard[0].GetWidth()) for p in candidates
                         if _unit(p[0], p[1]) == u and _unit(p[2], p[3]) == v)
            except (ValueError, StopIteration):
                continue
            if math.dist(f['hard_points_nm'][1], f['partner_corner_nm']) > 2*(pair['width']+pair['gap'])*1e6:
                continue
            cut = hard+partner
            if (len({force._uid(t) for t in cut}) != 5 or any(t.GetParentGroup() or t.HasSolderMask()
                    or t.GetWidth() != round(pair['width']*1e6) or t.GetLength() > 10000000
                    or t.IsLocked() and not allow_locked_source for t in cut)):
                continue
            if any(len({repr(owner._process(nodes[force._uid(t)])) for t in group}) != 1 for group in (hard, partner)):
                continue
            result.append(dict(primary_net=corner['net'], primary_track_uuids=sorted(force._uid(t) for t in hard),
                partner_track_uuids=sorted(force._uid(t) for t in partner), source_frame=f))
            if len(result) > 128:
                raise ValueError('balanced_axis_source_candidate_bound')
    return result


def _reference(parent, child, cut, fresh, *, board_hint, allow_existing_non_signal_face):
    face = int(cut[0].GetLayer());name = fab.COPPER_LAYER_IDS[face]
    with force._thermal_hint(board_hint):
        profiles = [fab.active_profile_name(b, hint=board_hint) for b in (parent, child)]
    if not profiles[0] or profiles[0] != profiles[1]:
        raise ValueError('same_explicit_native_pair_stack_required')
    roles = fab.get_profile(profiles[0])['roles'];index = fab.COPPER_LAYERS.index(name)
    if 'SIG' in roles[index]:
        return owner.reference_deficit(parent, child, cut, fresh, board_hint=board_hint, deadline=time.monotonic()+10.)
    if not allow_existing_non_signal_face:
        raise ValueError('unqualified_source_face_requires_explicit_draft_only_preservation')
    adjacent = [i for i in range(len(roles)) if abs(i-index) == 1 and roles[i] == 'GND']
    if len(adjacent) != 1:
        raise ValueError('unique_actual_adjacent_source_ground_sheet_required')
    reference = parent.GetLayerID(fab.COPPER_LAYERS[adjacent[0]])
    ground = pcbnew.SHAPE_POLY_SET();identities=[];deadline=time.monotonic()+10.
    for b in (parent, child):
        record={}
        for z in b.Zones():
            if z.GetIsRuleArea() or z.GetNetname() != 'GND' or not z.IsOnLayer(reference):
                continue
            if not z.IsFilled() or not z.HasFilledPolysForLayer(reference):
                raise ValueError('complete_literal_actual_ground_sheet_required')
            poly=z.GetFilledPolysList(reference);record[force._uid(z)]=owner._reference_identity(poly,deadline)
            if b is parent:ground.BooleanAdd(poly)
        identities.append(record)
    if not identities[0] or identities[0] != identities[1]:
        raise ValueError('existing_adjacent_ground_sheet_or_fill_changed')
    old=owner._capsules(cut,face,deadline);new=owner._capsules(fresh,face,deadline)
    old.BooleanSubtract(ground);new.BooleanSubtract(ground)
    extra=new.CloneDropTriangulation();extra.BooleanSubtract(old)
    if extra.OutlineCount():
        raise ValueError('new_physical_unreferenced_pair_copper_not_permitted')
    return dict(ok=True,complete=True,signal_face=name,actual_adjacent_ground_face=fab.COPPER_LAYERS[adjacent[0]],
        exact_existing_reference_sheet_identities=identities[0],new_unreferenced_copper_added=False,
        source_role=roles[index],source_role_not_reclassified=True,
        unsupported_source_role_retained_as_unqualified_debt=True,
        profile_signal_face_qualified=False,pair_qualified=False,release_authority=False)


def construct(board, source, pair, request, retreat_nm, *, allow_locked_source=False):
    """Untrusted private-board construction; independent receiving is mandatory."""
    if request not in discover(board, source, pair, allow_locked_source=allow_locked_source):
        raise ValueError('balanced_axis_request_not_rederived_from_actual_source')
    paths, algebra = replacements(request['source_frame'], retreat_nm)
    live = {force._uid(t): t for t in board.GetTracks()}
    ids = request['primary_track_uuids']+request['partner_track_uuids']
    templates = [live[request['primary_track_uuids'][0]], live[request['partner_track_uuids'][0]]]
    made = []
    for template, points in zip(templates, paths):
        for s, z in zip(points, points[1:]):
            t = template.Duplicate();t.m_Uuid.Clone(pcbnew.KIID())
            t.SetStart(pcbnew.VECTOR2I(*s));t.SetEnd(pcbnew.VECTOR2I(*z));made.append(t)
    for t in made:board.Add(t)
    discard_items(board, [live[u] for u in ids])
    return dict(retired_track_uuids=sorted(ids), incoming_track_uuids=sorted(force._uid(t) for t in made),
                source_request=request, retreat_nm=retreat_nm, algebra=algebra,
                independent_saved_receiving_still_required=True, pair_qualified=False, release_authority=False)


def receive(source, candidate, *, board_hint, pair_name, retired_track_uuids, retreat_nm,
            allow_locked_source=False, allow_existing_non_signal_face=False, timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],scope='source_exact_balanced_axis_pair_draft_refinement',
        pair_qualified=False,routing_admitted=False,fab_ready=False,release_authority=False,
        full_pair_fabrication_and_release_gates_unchanged=True)
    try:
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.:
            raise ValueError('bounded_balanced_axis_receiving_budget_required')
        deadline=time.monotonic()+timeout_s
        if type(allow_existing_non_signal_face) is not bool or type(allow_locked_source) is not bool:
            raise ValueError('explicit_balanced_axis_draft_modes_required')
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        pairs=owner.precision.derive_coupled_pairs(str(source),board=parent)
        if pairs != owner.precision.derive_coupled_pairs(str(candidate),board=child):
            raise ValueError('original_pair_contract_changed')
        pair=next(p for p in pairs if p['name']==pair_name)
        # This read-only whole-pair inventory also rejects power/pour roles,
        # mixed-width or opaque group-owned signal material. It grants no
        # whole-pair retirement to this much narrower local transformation.
        whole_pair.plan(parent,source,board_hint=board_hint,pair_name=pair_name)
        cut_ids=owner.ordinary._ids(retired_track_uuids,'balanced_axis_retirement',5)
        requests=[q for q in discover(parent,source,pair,allow_locked_source=allow_locked_source)
                  if set(q['primary_track_uuids']+q['partner_track_uuids']) == cut_ids]
        if len(requests) != 1:
            raise ValueError('unique_complete_original_balanced_axis_source_scope_required')
        request=requests[0];paths,algebra=replacements(request['source_frame'],retreat_nm)
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        incoming=new.keys()-old.keys()
        if old.keys()-new.keys() != cut_ids or len(incoming) != 6:
            raise ValueError('exact_five_to_six_balanced_axis_native_delta_required')
        before={force._uid(t):t for t in parent.GetTracks()};after={force._uid(t):t for t in child.GetTracks()}
        if not incoming <= after.keys():
            raise ValueError('only_native_paired_tracks_may_be_added')
        cut=[before[u] for u in cut_ids];fresh=[after[u] for u in incoming]
        face=int(cut[0].GetLayer());forbidden=rules.areas(child,'tracks')
        expected={}
        for net,points in zip((request['primary_net'],pair['n'] if request['primary_net']==pair['p'] else pair['p']),paths):
            actual=[t for t in fresh if t.GetNetname()==net]
            wanted=[tuple(p) for p in points]
            if len(actual) != 3 or owner._chain(actual) not in (wanted,wanted[::-1]):
                raise ValueError('saved_balanced_miter_is_not_the_exact_source_transform')
            exemplar=next(t for t in cut if t.GetNetname()==net)
            indexes=fr._foreign_shape_indexes(child,face,{exemplar.GetNetCode()})
            for t in actual:
                if (t.GetClass()!='PCB_TRACK' or t.GetWidth()!=exemplar.GetWidth() or int(t.GetLayer())!=face
                        or owner._process(new[force._uid(t)])!=owner._process(old[force._uid(exemplar)])
                        or not quality.is_canonical_stroke(tuple(t.GetStart()),tuple(t.GetEnd()),tolerance_nm=0)
                        or not fr._snapshot_foreign_clear(t.GetStart(),t.GetEnd(),t.GetWidth(),max(child.GetDesignSettings().m_MinClearance,math.ceil(pair['clearance']*1e6)),*indexes)
                        or not fr._edge_leg_clear(child,t.GetStart(),t.GetEnd(),(t.GetWidth()+1)//2)
                        or any(face in z['layers'] and z['shape'].Collide(t.GetEffectiveShape(face),0) for z in forbidden)):
                    raise ValueError('balanced_axis_native_width_process_clearance_or_rule_changed')
                duplicate=exemplar.Duplicate();duplicate.m_Uuid.Clone(pcbnew.KIID(force._uid(t)))
                duplicate.SetStart(t.GetStart());duplicate.SetEnd(t.GetEnd());expected[force._uid(t)]=duplicate
        # Reconstruct the child from original templates, not arbitrary child
        # native nodes. A changed lock, field, group, pose, rule or power
        # object cannot hide in this exact subtract/add and ground replay.
        with tempfile.TemporaryDirectory(prefix='cec-balanced-axis-replay-') as tmp:
            path=force._copy_family(source,Path(tmp)/'family');basis=pcbnew.LoadBoard(str(path))
            discard_items(basis,[t for t in basis.GetTracks() if force._uid(t) in cut_ids])
            for t in expected.values():basis.Add(t)
            additive._ground_refill(basis);field._save_field_snapshot(basis,path)
            _,nodes=additive._nodes(path)
            if nodes.keys()!=new.keys() or any(syntax._freeze(nodes[u])!=syntax._freeze(new[u]) for u in new):
                raise ValueError('whole_source_exact_balanced_axis_and_ground_replay_differs')
        if force._sidecars(source)!=force._sidecars(candidate) or force._preservation_snapshot(source)[1]!=force._preservation_snapshot(candidate)[1]:
            raise ValueError('source_parts_stack_mating_rules_or_sidecars_changed')
        old_parts=owner.ordinary._partition(parent,time.monotonic()+10.,retired_uuids=cut_ids)
        parts=owner.ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*old_parts))
        if not all(any(p <= q for q in parts) for p in old_parts):
            raise ValueError('surviving_native_pair_or_other_partition_lost')
        completion=owner.precision._native_pair_completion(child,pair)
        if not completion.get('complete') or not completion.get('connected') or any(q.get('disconnected_copper_uuids') for q in completion['nets'].values()):
            raise ValueError('complete_actual_saved_pair_connectivity_required')
        reference=_reference(parent,child,cut,fresh,board_hint=board_hint,allow_existing_non_signal_face=allow_existing_non_signal_face)
        continuous=owner.compare_continuous(owner.continuous_from_board(parent,pair),owner.continuous_from_board(child,pair))
        if not continuous['ok'] or not continuous['complete']:
            raise ValueError('physical_member_uncoupled_length_regressed')
        samples=[]
        for step in (.5,.25,.1):
            with force._thermal_hint(board_hint):
                metrics=[next(q for q in owner.constraints.high_speed_pair_summary(str(p),board=b,sample_mm=step)['pairs']
                    if (q['p'],q['n'])==(pair['p'],pair['n'])) for p,b in ((source,parent),(candidate,child))]
            comparison=owner.metric_progress(*metrics,coupling=continuous)
            if not comparison['ok']:
                raise ValueError('unchanged_full_pair_metric_progress_required:'+str(comparison['errors']))
            samples.append(dict(sample_mm=step,before=metrics[0],after=metrics[1],comparison=comparison))
        bends=[len(owner.bend_inventory(b,pair)['selected']) for b in (parent,child)]
        crafts=[quality.analyze_board(b) for b in (parent,child)]
        if bends[1]>=bends[0] or any(crafts[1][k]>crafts[0][k] for k in ('issue_count','non_octilinear_count')) or crafts[1]['power_contours']['finding_count']>crafts[0]['power_contours']['finding_count']:
            raise ValueError('strict_visible_bend_progress_without_whole_board_craft_regression_required')
        if time.monotonic()>=deadline or epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('balanced_axis_source_child_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            exact_source_request=request,algebra=algebra,retired_track_uuids=sorted(cut_ids),incoming_track_uuids=sorted(incoming),
            added_native_uuids=sorted(incoming),pair=pair,
            reference_copper_preservation=reference,continuous_coupling=continuous,whole_pair_metric_samples=samples,
            exact_native_pair_completion=completion,eligible_hard90_before_after=bends,
            power_copper_barrels_pads_poses_rules_and_mating_unchanged=True,source_candidate_and_code_unchanged=True)
    except Exception as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
