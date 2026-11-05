"""Gap-free, Source-bound pages for the existing native Ground-entry owner.

The historical longest-first search stops after sixteen terminals.  This
extension enumerates the complete finite site menu, not just that prefix.
It changes neither process dimensions nor the independent saved-board owner.
Unknown witnesses stay unknown.  An exhausted menu is never a no-path proof.
"""
import hashlib
import json
import math
import time
from pathlib import Path

import pcbnew
import cec_force_current as force
import cec_source_local_ground_search as original

POLICY = 'literal-source-ground-sites-with-gap-free-continuation-v1'


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()


def _menu(observed, *, reach_mm, offsets_nm, resolve):
    """Pure ordering; no slicing to the longest sixteen Ground terminals."""
    original.sites((0, 0), offsets_nm=offsets_nm, reach_mm=reach_mm)
    _require(type(observed) is dict and len(observed) <= 2048,
        'bounded_native_ground_terminal_inventory_required')
    ordered = sorted((v for v in observed.values() if v['return_mm'] is not None
        and v['return_mm'] > reach_mm + .000001),
        key=lambda v: (-v['return_mm'], v['pad_uuid']))
    rows = []
    for terminal in ordered:
        existing, requested = resolve(terminal['pad_uuid'])
        points = original.sites(terminal['at_nm'], offsets_nm=offsets_nm,
            reach_mm=reach_mm) if existing else [tuple(terminal['at_nm'])]
        for point in points:
            args = dict(pad_uuid=terminal['pad_uuid'], reach_mm=reach_mm,
                use_existing_local_pad_rule=existing)
            if existing and list(point) != terminal['at_nm']:
                args['dogbone_position_nm'] = list(point)
            rows.append(dict(index=len(rows), terminal=terminal, at_nm=list(point),
                requested_geometry_mm=list(requested) if existing else None,
                plan_arguments=args))
    _require(len(rows) <= 8192, 'explicit_ground_site_inventory_bound_exceeded')
    return rows


def _context(source, board_hint, expected_source_sha256, reach_mm, offsets_nm):
    _require(type(board_hint) is str and bool(board_hint),
        'explicit_ground_frontier_context_required')
    source = Path(source).resolve()
    _require(type(expected_source_sha256) is str and len(expected_source_sha256) == 64
        and force._hash(source) == expected_source_sha256,
        'exact_ground_frontier_source_sha256_required')
    original.sites((0, 0), offsets_nm=offsets_nm, reach_mm=reach_mm)
    epoch = force._code_identity(); family = force._family(source, board_hint)
    tools = {str(Path(p).resolve()): force._hash(Path(p))
        for p in (__file__, original.__file__)}
    board = pcbnew.LoadBoard(str(source)); binding = original.row._source_binding(board)
    observed = original.returns._observe(board, 16., time.monotonic()+10.)
    def resolve(uid):
        pad, _ = original.entry._pad(board, uid)
        try:
            _, _, requested = original.entry._existing_pad_rule(board, pad)
            return True, requested
        except ValueError:
            return False, None
    menu = _menu(observed, reach_mm=reach_mm, offsets_nm=offsets_nm, resolve=resolve)
    identity = dict(policy=POLICY, source=str(source), source_sha256=expected_source_sha256,
        board_hint=board_hint, source_family=family, epoch_sha256=_digest(epoch),
        helper_sha256=tools, reach_mm=reach_mm, offsets_nm=list(offsets_nm),
        observed=sorted(observed.values(), key=lambda v: v['pad_uuid']), menu=menu)
    _require(epoch == force._code_identity() and family == force._family(source, board_hint),
        'ground_frontier_source_or_code_changed')
    return board, binding, identity, _digest(identity)


def _index(cursor, inventory_sha256, count):
    if cursor is None:
        return 0
    _require(type(cursor) is dict and set(cursor) == {'inventory_sha256', 'next_index'}
        and cursor['inventory_sha256'] == inventory_sha256
        and type(cursor['next_index']) is int and 0 <= cursor['next_index'] <= count,
        'stale_forged_or_untyped_ground_cursor')
    return cursor['next_index']


def _run_page(board, identity, digest, *, cursor, page_size, timeout_s):
    _require(type(page_size) is int and 1 <= page_size <= 256
        and type(timeout_s) in (int, float) and math.isfinite(timeout_s)
        and 0 < timeout_s <= 45, 'finite_ground_frontier_page_bound_required')
    menu = identity['menu']; start = _index(cursor, digest, len(menu))
    end = min(len(menu), start+page_size); deadline = time.monotonic()+timeout_s
    result = dict(ok=True, complete=True, inventory_sha256=digest, start_index=start,
        next_index=start, inventory_site_count=len(menu), attempts=[], proposal=None,
        finite_page_exhausted=False, global_shortest_or_no_path_proof=False,
        routing_admitted=False, fab_ready=False, release_authority=False)
    cache = {}
    for row in menu[start:end]:
        if time.monotonic() >= deadline:
            break
        pad, _ = original.entry._pad(board, row['terminal']['pad_uuid'])
        attempt = dict(site_index=row['index'], terminal=row['terminal'],
            plan_arguments=row['plan_arguments'], accepted_proposal=False)
        result['attempts'].append(attempt); result['next_index'] = row['index']+1
        try:
            if row['plan_arguments']['use_existing_local_pad_rule']:
                preflight = original._preflight(board, pad, row['at_nm'],
                    row['requested_geometry_mm'], foreign_cache=cache)
                attempt['read_only_native_preflight'] = preflight
                if not preflight['ok']:
                    attempt['refusal'] = 'read_only_native_preflight_refused'
                    continue
            proposal = original.entry.plan(identity['source'],
                board_hint=identity['board_hint'],
                timeout_s=min(10., max(.001, deadline-time.monotonic())),
                **row['plan_arguments'])
            _require(proposal['source_sha256'] == identity['source_sha256']
                and proposal['source_return_witness_mm'] == row['terminal']['return_mm'],
                'ground_frontier_proposal_must_match_actual_source_witness')
            attempt['accepted_proposal'] = True
            result.update(proposal=proposal, plan_arguments=row['plan_arguments'],
                selected_terminal=row['terminal'])
            break
        except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
            attempt['refusal'] = type(exc).__name__+':'+str(exc)
    result['finite_page_exhausted'] = result['next_index'] == end
    result['inventory_exhausted'] = result['next_index'] == len(menu)
    result['continuation'] = dict(inventory_sha256=digest, next_index=result['next_index'])
    return result


def coverage(identity, inventory_sha256, pages):
    """Validate exact contiguous examined rows, never infer routing legality."""
    _require(_digest(identity) == inventory_sha256 and type(pages) is list and len(pages) <= 64,
        'literal_ground_inventory_and_bounded_pages_required')
    cursor = 0; menu = identity['menu']
    for page in pages:
        _require(page['inventory_sha256'] == inventory_sha256 and page['start_index'] == cursor
            and type(page['next_index']) is int and cursor <= page['next_index'] <= len(menu),
            'ground_coverage_gap_overlap_stale_or_out_of_range_page')
        attempts = page['attempts']
        _require(len(attempts) == page['next_index']-cursor,
            'every_ground_site_in_page_prefix_must_have_an_attempt')
        for n, attempt in enumerate(attempts, cursor):
            _require(type(attempt['site_index']) is int and attempt['site_index'] == n
                and attempt['terminal'] == menu[n]['terminal']
                and attempt['plan_arguments'] == menu[n]['plan_arguments'],
                'ground_attempt_not_the_literal_source_menu_row')
        cursor = page['next_index']
    return dict(examined_sites=cursor, inventory_sites=len(menu),
        all_finite_menu_sites_examined=cursor == len(menu), unexamined_sites=len(menu)-cursor,
        no_gap_or_overlap_in_actual_examined_prefix=True,
        search_receipt_not_independent_path_or_refusal_admission=True,
        global_shortest_or_no_path_proof=False, release_authority=False)


def discover_all(source, *, board_hint, expected_source_sha256, reach_mm=.5,
        offsets_nm=(400000, 800000, 1000000), page_size=64, max_pages=32, timeout_s=45.,
        cursor=None):
    _require(type(max_pages) is int and 1 <= max_pages <= 64,
        'finite_ground_frontier_page_count_required')
    started = time.monotonic()
    board, binding, identity, digest = _context(source, board_hint,
        expected_source_sha256, reach_mm, offsets_nm)
    # Caller continuation may start elsewhere, but never claim gap-free full coverage
    # without the actual preceding page records. The ordinary all-menu run starts0.
    beginning = _index(cursor, digest, len(identity['menu'])); pages = []; current = cursor
    for _ in range(max_pages):
        page = _run_page(board, identity, digest, cursor=current,
            page_size=page_size, timeout_s=timeout_s)
        pages.append(page); current = page['continuation']
        if page['proposal'] is not None or page['inventory_exhausted'] or page['next_index'] == page['start_index']:
            break
    checked = coverage(identity, digest, pages) if beginning == 0 else None
    last = pages[-1]; all_attempts = [v for page in pages for v in page['attempts']]
    result = dict(schema=1, policy=POLICY, ok=True, complete=True, source=identity['source'],
        source_sha256=expected_source_sha256, inventory_sha256=digest,
        source_terminal_count=len(identity['observed']),
        unknown_source_return_count=sum(v['return_mm'] is None for v in identity['observed']),
        known_nonlocal_terminal_count=len({v['terminal']['pad_uuid'] for v in identity['menu']}),
        inventory_site_count=len(identity['menu']), attempts=all_attempts, pages=pages,
        coverage=checked, continuation=current, proposal=last['proposal'],
        reach_mm=reach_mm, offsets_nm=list(offsets_nm), helper_sha256=identity['helper_sha256'],
        source_inventory=identity, stopped_reason=('first_source_guarded_proposal' if last['proposal']
            else 'actual_finite_site_menu_exhausted' if last['inventory_exhausted']
            else 'explicit_page_or_time_bound'), elapsed_s=time.monotonic()-started,
        global_shortest_or_no_path_proof=False, source_selected=False,
        routing_admitted=False, fab_ready=False, current_qualified=False, release_authority=False,
        all_saved_native_and_whole_parent_receiving_still_required=True)
    if last['proposal'] is not None:
        result.update(plan_arguments=last['plan_arguments'], selected_terminal=last['selected_terminal'])
    _require(force._family(Path(identity['source']), board_hint) == identity['source_family']
        and _digest(force._code_identity()) == identity['epoch_sha256']
        and all(force._hash(Path(p)) == h for p, h in identity['helper_sha256'].items())
        and binding == original.row._source_binding(board),
        'ground_frontier_source_family_code_helpers_or_native_board_changed')
    result.update(source_family_and_code_unchanged=True, source_physical_items_unchanged=True)
    return result
