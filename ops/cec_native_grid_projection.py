"""One-grid correction of complete existing native endpoint components.

No new strokes/jogs, width changes, vias, parts, groups or planes are allowed.
The floating-point optimizer proposes bounded integer endpoint translations;
the independent integer checker owns heading/topology acceptance. Actual
saved-board current, pair/reference, native DRC and Kelvin gates still apply.
"""
from collections import defaultdict
import math
from pathlib import Path
import tempfile
import time
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as current
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_pair_axis_miter as pair_reference
import cec_pair_local_reference_refinement as pairs

POLICY = 'literal-native-one-grid-endpoint-projection-v1'
MAX_COMPONENT_EDGES = 512


def require(value, message):
    if not value:
        raise ValueError(message)


def heading(a, z):
    require(all(type(v) is int and abs(v) <= 2000000000 for v in (*a, *z)), 'literal_bounded_integer_source_points_required')
    dx, dy = z[0]-a[0], z[1]-a[1]
    require(max(abs(dx), abs(dy)) > 0, 'positive_literal_source_stroke_required')
    error, kind = min((abs(dx), 'vertical'), (abs(dy), 'horizontal'), (abs(abs(dx)-abs(dy)), 'diagonal'))
    require(error <= 1, 'projection_cannot_reclassify_a_real_non_octilinear_source_stroke')
    return kind, (1 if dx*dy > 0 else -1), error


def check_projection(edges, points, fixed, replacements):
    require(type(edges) is list and 1 <= len(edges) <= MAX_COMPONENT_EDGES, 'finite_native_grid_component_required')
    require(type(points) is list and 2 <= len(points) <= 2*MAX_COMPONENT_EDGES
        and len({tuple(p) for p in points}) == len(points), 'unique_literal_native_grid_vertices_required')
    require(type(replacements) is list and len(replacements) == len(points), 'complete_projected_vertex_inventory_required')
    require(type(fixed) in (list, tuple) and len(set(fixed)) == len(fixed)
        and all(type(i) is int and 0 <= i < len(points) for i in fixed), 'actual_bounded_fixed_grid_vertices_required')
    for index, (old, new) in enumerate(zip(points, replacements)):
        require(type(new) is list and len(new) == 2 and all(type(v) is int for v in new)
            and all(abs(a-z) <= 1 for a, z in zip(old, new)), 'projected_coordinates_must_stay_within_one_native_grid')
        require(index not in fixed or old == new, 'physical_pad_via_or_arc_port_cannot_move')
    require(len({tuple(p) for p in replacements}) == len(replacements), 'projection_cannot_merge_distinct_source_vertices')
    for edge in edges:
        require(type(edge) is list and len(edge) == 2 and all(type(i) is int and 0 <= i < len(points) for i in edge)
            and edge[0] != edge[1], 'actual_complete_source_edge_incidence_required')
        a, z = [points[i] for i in edge]
        b, y = [replacements[i] for i in edge]
        kind, sign, _ = heading(a, z)
        dx, dy = y[0]-b[0], y[1]-b[1]
        require((kind == 'vertical' and dx == 0) or (kind == 'horizontal' and dy == 0)
            or (kind == 'diagonal' and dy == sign*dx), 'every_projected_source_stroke_must_be_exactly_cardinal_or_45')
        require((z[0]-a[0])*dx+(z[1]-a[1])*dy > 0, 'source_stroke_direction_or_positive_length_changed')
    return True


def project(edges, points, fixed=(), *, preferred_direction=None, preferred_vertex=None):
    """Finite MILP proposal. No floating-point feasibility result is trusted."""
    import numpy as np
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix
    require(1 <= len(edges) <= MAX_COMPONENT_EDGES and 2 <= len(points) <= 2*MAX_COMPONENT_EDGES,
        'finite_projection_solver_work_domain_required')
    require(preferred_direction is None or type(preferred_direction) in (tuple, list)
        and len(preferred_direction) == 2
        and all(type(v) is int and -1 <= v <= 1 for v in preferred_direction),
        'finite_literal_grid_search_direction_required')
    require(preferred_vertex is None or type(preferred_vertex) is int
        and 0 <= preferred_vertex < len(points) and preferred_direction is not None,
        'actual_bounded_grid_preference_vertex_required')
    count = len(points)*2
    matrix = lil_matrix((len(edges)+2*count, 2*count), dtype=float)
    low = np.zeros(matrix.shape[0]); high = np.zeros(matrix.shape[0])
    for row, (first, last) in enumerate(edges):
        a, z = points[first], points[last]
        kind, sign, _ = heading(a, z)
        if kind == 'horizontal': weights = (0, 1)
        elif kind == 'vertical': weights = (1, 0)
        else: weights = (-sign, 1)
        for axis, weight in enumerate(weights):
            matrix[row, 2*last+axis] += weight
            matrix[row, 2*first+axis] -= weight
        low[row] = high[row] = -sum((z[i]-a[i])*weights[i] for i in (0, 1))
    for i in range(count):
        row = len(edges)+2*i
        matrix[row, i] = 1; matrix[row, count+i] = -1
        matrix[row+1, i] = -1; matrix[row+1, count+i] = -1
        low[row:row+2] = -np.inf
        high[row:row+2] = 0
    lower = np.r_[np.full(count, -1.), np.zeros(count)]
    upper = np.ones(2*count)
    for index in fixed:
        lower[2*index:2*index+2] = 0
        upper[2*index:2*index+2] = 0
    bias = np.zeros(count) if preferred_direction is None else np.tile(preferred_direction, len(points))*2.
    if preferred_vertex is not None:
        bias[:] = 0
        bias[2*preferred_vertex:2*preferred_vertex+2] = np.array(preferred_direction)*2.
    cost = np.r_[bias, np.ones(count)+np.arange(count)*1e-7]
    result = milp(cost, integrality=np.r_[np.ones(count), np.zeros(count)],
        bounds=Bounds(lower, upper), constraints=LinearConstraint(matrix.tocsr(), low, high),
        options=dict(time_limit=3., node_limit=4096, presolve=True))
    require(result.x is not None and result.status == 0, 'bounded_one_grid_projection_not_solved')
    delta = [int(round(x)) for x in result.x[:count]]
    replacements = [[p[axis]+delta[2*i+axis] for axis in (0, 1)] for i, p in enumerate(points)]
    check_projection(edges, points, list(fixed), replacements)
    return replacements


def inventory(source):
    board = pcbnew.LoadBoard(str(source))
    live = [t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK']
    require(len(live) <= 16384, 'bounded_literal_native_grid_track_inventory_required')
    incidence = defaultdict(list)
    def key(t, p): return (str(t.GetNetname()), int(t.GetLayer()), tuple(p))
    seeds = []
    for track in live:
        a, z = list(track.GetStart()), list(track.GetEnd())
        if min(abs(z[0]-a[0]), abs(z[1]-a[1]), abs(abs(z[0]-a[0])-abs(z[1]-a[1]))) != 0:
            heading(a, z)
            seeds.append(track)
        for point in (a, z): incidence[key(track, point)].append(track)
    require(seeds and len(seeds) <= 128, 'bounded_nonempty_literal_one_grid_source_debt_required')
    components = []; seen = set()
    for seed in sorted(seeds, key=force._uid):
        if force._uid(seed) in seen: continue
        stack = [seed]; selected = {}
        while stack:
            track = stack.pop(); uid = force._uid(track)
            if uid in selected: continue
            selected[uid] = track; seen.add(uid)
            require(len(selected) <= MAX_COMPONENT_EDGES, 'source_grid_component_exceeds_finite_work_bound')
            for point in (track.GetStart(), track.GetEnd()): stack.extend(incidence[key(track, point)])
        tracks = [selected[u] for u in sorted(selected)]
        net, face = tracks[0].GetNetname(), int(tracks[0].GetLayer())
        points = [list(p) for p in sorted({tuple(p) for t in tracks for p in (t.GetStart(), t.GetEnd())})]
        by_point = {tuple(p): i for i, p in enumerate(points)}
        edges = [[by_point[tuple(t.GetStart())], by_point[tuple(t.GetEnd())]] for t in tracks]
        fixed = set()
        for pad in board.GetPads():
            point = tuple(pad.GetPosition())
            if pad.GetNetname() == net and pad.IsOnLayer(face) and point in by_point: fixed.add(by_point[point])
        for item in board.GetTracks():
            if item.GetNetname() != net or not item.IsOnLayer(face): continue
            positions = [item.GetPosition()] if item.GetClass() == 'PCB_VIA' else (
                [item.GetStart(), item.GetEnd()] if item.GetClass() == 'PCB_ARC' else [])
            for point in positions:
                if tuple(point) in by_point: fixed.add(by_point[tuple(point)])
        for edge in edges:
            a, z = [points[i] for i in edge]
            heading(a, z)
            # Existing microscopic native joints are not routing freedom.
            # Freeze both ends so a projection cannot erase/reverse them or
            # invent a new tiny jog to make its heading counter look better.
            if max(abs(z[i]-a[i]) for i in (0, 1)) <= 4:
                fixed.update(edge)
        components.append(dict(net=str(net), layer=face, track_uuids=[force._uid(t) for t in tracks],
            points_nm=points, edges=edges, fixed_vertex_indices=sorted(fixed)))
    return board, components, len(seeds)


def plan(source, *, board_hint, allow_locked_source=False):
    source = Path(source).resolve()
    require(type(board_hint) is str and board_hint and type(allow_locked_source) is bool,
        'explicit_saved_grid_projection_context_required')
    epoch = force._code_identity(); family = force._family(source, board_hint)
    board, components, count = inventory(source)
    live = {force._uid(t): t for t in board.GetTracks()}
    for component in components:
        require(all(not live[u].IsLocked() or allow_locked_source for u in component['track_uuids']),
            'explicit_permission_for_each_source_locked_projection_required')
        component['projected_points_nm'] = project(component['edges'], component['points_nm'], component['fixed_vertex_indices'])
    require(epoch == force._code_identity() and family == force._family(source, board_hint), 'grid_projection_source_or_runtime_changed')
    return dict(policy=POLICY, source_sha256=force._hash(source), code_identity=epoch,
        authority_sha256=force._hash(Path(__file__)), board_hint=board_hint,
        allow_locked_source=allow_locked_source, source_noncanonical_strokes=count,
        maximum_coordinate_change_nm=1, components=components,
        no_added_segments_or_jogs=True, current_pair_or_fab_qualified=False, release_authority=False)


def construct(source, proposal):
    require(type(proposal.get('allow_locked_source')) is bool
        and proposal.get('maximum_coordinate_change_nm') == 1
        and proposal.get('no_added_segments_or_jogs') is True,
        'exact_one_grid_process_and_explicit_lock_policy_required')
    require(proposal['policy'] == POLICY and proposal['source_sha256'] == force._hash(Path(source))
        and proposal['authority_sha256'] == force._hash(Path(__file__))
        and proposal['code_identity'] == force._code_identity(), 'stale_or_repurposed_grid_projection_proposal')
    board, components, count = inventory(source)
    require(len(components) == len(proposal['components']) and count == proposal['source_noncanonical_strokes'],
        'actual_complete_grid_projection_source_component_inventory_required')
    live = {force._uid(t): t for t in board.GetTracks()}; changed = []
    for source_component, record in zip(components, proposal['components']):
        require({k: v for k, v in record.items() if k != 'projected_points_nm'} == source_component,
            'grid_projection_source_incidence_or_fixed_ports_changed')
        require(all(not live[u].IsLocked() or proposal['allow_locked_source'] for u in record['track_uuids']),
            'locked_grid_projection_permission_missing')
        check_projection(record['edges'], record['points_nm'], record['fixed_vertex_indices'], record['projected_points_nm'])
        for uid, edge in zip(record['track_uuids'], record['edges']):
            track = live[uid]
            a, z = [record['projected_points_nm'][i] for i in edge]
            if list(track.GetStart()) != a or list(track.GetEnd()) != z:
                changed.append(uid)
                track.SetStart(pcbnew.VECTOR2I(*a)); track.SetEnd(pcbnew.VECTOR2I(*z))
    require(changed, 'literal_grid_projection_must_repair_actual_source_debt')
    return board, sorted(changed)


def receive(source, candidate, proposal, *, board_hint):
    result = dict(ok=False, complete=False, errors=[], current_pair_or_fab_qualified=False, release_authority=False)
    try:
        source, candidate = [Path(q).resolve() for q in (source, candidate)]
        epoch = force._code_identity(); families = [force._family(q, board_hint) for q in (source, candidate)]
        require(source != candidate and proposal['board_hint'] == board_hint, 'actual_distinct_grid_projection_boards_required')
        replay, changed = construct(source, proposal)
        with tempfile.TemporaryDirectory(prefix='cec-native-grid-projection-') as work:
            expected = force._copy_family(source, Path(work)/'expected')
            field._save_field_snapshot(replay, expected)
            require(syntax._freeze(additive._nodes(expected)[0]) == syntax._freeze(additive._nodes(candidate)[0]),
                'saved_grid_projection_changed_unowned_native_board_evidence')
        require(force._sidecars(source) == force._sidecars(candidate)
            and force._preservation_snapshot(source)[1] == force._preservation_snapshot(candidate)[1],
            'grid_projection_parts_fields_outlines_rules_or_mating_changed')
        boards = [pcbnew.LoadBoard(str(q)) for q in (source, candidate)]
        parts = ordinary._partition(boards[0], time.monotonic()+10.)
        after = ordinary._partition(boards[1], time.monotonic()+10., retained_keys=set().union(*parts))
        require(all(any(p <= q for q in after) for p in parts), 'grid_projection_lost_actual_native_partition')
        debt = current.receive(source, candidate, board_hint=board_hint)
        require(debt['ok'] and debt['complete'], 'grid_projection_current_debt_regressed_or_unknown')
        old_pairs = pairs.precision.derive_coupled_pairs(str(source), board=boards[0])
        require(old_pairs == pairs.precision.derive_coupled_pairs(str(candidate), board=boards[1]), 'grid_projection_pair_contract_changed')
        pair_proofs = []
        for pair in old_pairs:
            old = [t for t in boards[0].GetTracks() if t.GetNetname() in (pair['p'], pair['n'])]
            new = [t for t in boards[1].GetTracks() if t.GetNetname() in (pair['p'], pair['n'])]
            continuous = pairs.compare_continuous(*[pairs.continuous_from_board(b, pair) for b in boards])
            require(continuous['ok'] and continuous['complete'], 'grid_projection_continuous_pair_deficit_regressed')
            faces = sorted({int(t.GetLayer()) for t in old if t.GetClass() == 'PCB_TRACK'})
            references = [pair_reference._reference(boards[0], boards[1],
                [t for t in old if t.GetClass() == 'PCB_TRACK' and int(t.GetLayer()) == face],
                [t for t in new if t.GetClass() == 'PCB_TRACK' and int(t.GetLayer()) == face],
                board_hint=board_hint, allow_existing_non_signal_face=True) for face in faces]
            samples = []
            for step in (.5, .25, .1):
                with force._thermal_hint(board_hint):
                    metrics = [next(row for row in pairs.constraints.high_speed_pair_summary(str(q), board=b, sample_mm=step)['pairs']
                        if (row['p'], row['n']) == (pair['p'], pair['n'])) for q, b in zip((source, candidate), boards)]
                comparison = pairs.metric_progress(*metrics, coupling=continuous)
                require(comparison['ok'], 'grid_projection_full_pair_metrics_regressed:'+str(comparison['errors']))
                samples.append(dict(sample_mm=step, before=metrics[0], after=metrics[1], comparison=comparison))
            pair_proofs.append(dict(pair=pair, continuous=continuous, references=references, sampled_metrics=samples))
        require(epoch == force._code_identity() and families == [force._family(q, board_hint) for q in (source, candidate)],
            'grid_projection_source_candidate_or_runtime_changed')
        result.update(ok=True, complete=True, source_sha256=force._hash(source), candidate_sha256=force._hash(candidate),
            code_identity=epoch, modified_track_uuids=changed, new_tracks_vias_or_jogs=0,
            every_source_native_partition_preserved=True, exact_saved_native_source_reconstruction=True,
            original_current_budgets_widths_faces_locks_groups_pads_planes_and_rules_preserved=True,
            whole_parent_current_receiving=debt, full_pair_preservation=pair_proofs,
            native_drc_clipped_kelvin_ground_and_whole_parent_receiving_still_required=True)
    except (ValueError, RuntimeError, AssertionError, KeyError, TypeError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
