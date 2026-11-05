"""Finite source-derived ground-entry proposals, never fabrication admission.

Discover every populated SMD ground terminal, including IC pins rather than
only capacitors. Prefer known long returns. Preserve the saved process, use
the existing ground-entry receiver, and retain a bounded refusal receipt.
No board, component name, pin number or placement coordinate is a policy.
"""
import math
import time
from pathlib import Path

import pcbnew
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_ground_access_completion as entry
import cec_ground_return_preservation as returns
import cec_decoupler_cell as cells
import cec_fr as fr


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def sites(at_nm, *, offsets_nm=(400000, 800000, 1000000), reach_mm=1.5):
    """Exact cardinal/45-degree sites, ordered by actual distance then XY.

    Offsets and reach are explicit bounded search settings, not dimensions
    inferred from a part name. Each site still needs all-layer native guards.
    """
    _require(type(at_nm) in (tuple, list) and len(at_nm) == 2
        and all(type(v) is int and abs(v) <= 2000000000 for v in at_nm),
        'literal_integer_source_ground_origin_required')
    _require(type(offsets_nm) in (tuple, list) and 1 <= len(offsets_nm) <= 4
        and all(type(v) is int and 0 < v <= 1500000 for v in offsets_nm)
        and len(set(offsets_nm)) == len(offsets_nm), 'bounded_unique_ground_offsets_required')
    _require(type(reach_mm) in (int, float) and math.isfinite(reach_mm)
        and 0 < reach_mm <= 1.5, 'bounded_ground_search_reach_required')
    points = {tuple(at_nm)}
    for d in offsets_nm:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                (1, 1), (1, -1), (-1, 1), (-1, -1)):
            p = (at_nm[0] + dx*d, at_nm[1] + dy*d)
            if math.dist(at_nm, p) <= reach_mm*1e6 and all(abs(v) <= 2000000000 for v in p):
                points.add(p)
    return sorted(points, key=lambda p: (math.dist(at_nm, p), p))


def _preflight(board, pad, point, requested, *, foreign_cache):
    """Read-only pruning, NOT authority to construct or skip saved replay.

    Reuse only native foreign-shape indices from this one unchanged board.
    Literal blocker IDs/layers are retained rather than repeating an opaque
    'site blocked' message. Positive sites still get a fresh entry.plan.
    """
    face = cells.cec_return_escape.smd_surface_layer(pad)
    at = pcbnew.VECTOR2I(*point); start = pad.GetPosition()
    centre = tuple(start) == tuple(point)
    spec = cells._netclass(board, 'GND')
    gap = max(200000, int(spec['clearance']), int(board.GetDesignSettings().m_MinClearance))
    width = max(int(spec['width']), int(board.GetDesignSettings().m_TrackMinWidth))
    diameter, drill = [round(v*1e6) for v in requested]
    context = dict(local_pofv_pad=pad) if centre else dict(
        local_pofv_dogbone=dict(pad=pad, start=start, layer=face))
    detail = {}
    edge = fr._edge_leg_clear(board, start, at, diameter//2 if centre else width/2+gap)
    hole, conflicts = cells._hole_to_hole_clear(board, at, requested[1])
    via = fr._via_spot_clear(board, at, diameter, gap, {pad.GetNetCode()},
        drill_nm=drill, net_code=pad.GetNetCode(), foreign_cache=foreign_cache,
        report=detail, **context)
    surface = centre or fr._tap_foreign_clear(board, start, at, width, face, gap, {pad.GetNetCode()})
    resolved = detail.pop('existing_native_local_pad_rule', None)
    return dict(ok=bool(edge and hole and via and surface), edge_clear=bool(edge),
        hole_clear=bool(hole), hole_conflicts=conflicts, via_clear=bool(via),
        surface_clear=bool(surface), native_via_report=detail,
        source_local_rule_sha256=resolved['rule_sha256'] if resolved else None,
        positive_preflight_does_not_authorize_construction=True)


def discover(source, *, board_hint, expected_source_sha256, reach_mm=1.5,
        offsets_nm=(400000, 800000, 1000000), max_terminals=8,
        max_attempts=200, timeout_s=90.):
    """Return at most one unchanged-receiver proposal plus refusal evidence.

    Unknown return witnesses are declared, not treated as infinity or opens.
    A bounded stop is neither an unroutability nor a shortest-path proof.
    """
    _require(type(board_hint) is str and bool(board_hint), 'explicit_ground_search_context_required')
    _require(type(max_terminals) is int and 1 <= max_terminals <= 16
        and type(max_attempts) is int and 1 <= max_attempts <= 256
        and type(timeout_s) in (int, float) and math.isfinite(timeout_s)
        and 0 < timeout_s <= 120, 'finite_ground_search_budget_required')
    # Validate all caller settings even when the source has no eligible pad.
    sites((0, 0), offsets_nm=offsets_nm, reach_mm=reach_mm)
    source = Path(source).resolve()
    _require(type(expected_source_sha256) is str and len(expected_source_sha256) == 64
        and force._hash(source) == expected_source_sha256, 'exact_ground_search_source_sha256_required')
    epoch = force._code_identity(); family = force._family(source, board_hint)
    tool = Path(__file__).resolve(); tool_hash = force._hash(tool)
    board = pcbnew.LoadBoard(str(source)); binding = row._source_binding(board)
    start = time.monotonic(); deadline = start + timeout_s
    observed = returns._observe(board, 16., min(deadline, start + 10.))
    candidates = sorted((v for v in observed.values()
        if v['return_mm'] is not None and v['return_mm'] > reach_mm + .000001),
        key=lambda v: (-v['return_mm'], v['pad_uuid']))
    result = dict(schema=1, ok=True, complete=True, proposal=None, attempts=[],
        source=str(source), source_sha256=expected_source_sha256, code_identity=epoch,
        input_sha256={str(tool): tool_hash}, source_terminal_count=len(observed),
        unknown_source_return_count=sum(v['return_mm'] is None for v in observed.values()),
        known_nonlocal_terminal_count=len(candidates), max_terminals=max_terminals,
        max_attempts=max_attempts, reach_mm=reach_mm, offsets_nm=list(offsets_nm),
        stopped_reason='finite_terminal_menu_exhausted', release_authority=False,
        fab_ready=False, current_qualified=False, global_shortest_or_no_path_proof=False)
    for terminal in candidates[:max_terminals]:
        pad, _ = entry._pad(board, terminal['pad_uuid'])
        try:
            _, _, requested = entry._existing_pad_rule(board, pad)
            existing_rule = True
        except ValueError:
            existing_rule = False
        menu = sites(terminal['at_nm'], offsets_nm=offsets_nm, reach_mm=reach_mm) if existing_rule else [tuple(terminal['at_nm'])]
        foreign_cache = {}
        for point in menu:
            if len(result['attempts']) >= max_attempts or time.monotonic() >= deadline:
                result['stopped_reason'] = 'explicit_attempt_or_time_bound'
                break
            args = dict(pad_uuid=terminal['pad_uuid'], reach_mm=reach_mm,
                use_existing_local_pad_rule=existing_rule)
            if existing_rule and list(point) != terminal['at_nm']:
                args['dogbone_position_nm'] = list(point)
            attempt = dict(terminal=terminal, plan_arguments=args, accepted_proposal=False)
            result['attempts'].append(attempt)
            try:
                if existing_rule:
                    preflight = _preflight(board, pad, point, requested, foreign_cache=foreign_cache)
                    attempt['read_only_native_preflight'] = preflight
                    if not preflight['ok']:
                        attempt['refusal'] = 'read_only_native_preflight_refused'
                        continue
                proposal = entry.plan(source, board_hint=board_hint,
                    timeout_s=min(10., max(.001, deadline-time.monotonic())), **args)
                _require(proposal['source_sha256'] == expected_source_sha256
                    and proposal['source_return_witness_mm'] == terminal['return_mm'],
                    'ground_search_proposal_must_match_actual_source_witness')
                result.update(proposal=proposal, plan_arguments=args, selected_terminal=terminal,
                    stopped_reason='first_source_guarded_proposal')
                attempt['accepted_proposal'] = True
                break
            except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
                attempt['refusal'] = type(exc).__name__ + ':' + str(exc)
        if result['proposal'] is not None or result['stopped_reason'] == 'explicit_attempt_or_time_bound':
            break
    _require(epoch == force._code_identity() and family == force._family(source, board_hint)
        and tool_hash == force._hash(tool) and binding == row._source_binding(board),
        'ground_search_source_family_code_or_tool_changed')
    result.update(elapsed_s=time.monotonic()-start, source_family_and_code_unchanged=True,
        source_physical_items_unchanged=True, all_saved_native_and_whole_parent_receiving_still_required=True)
    return result
