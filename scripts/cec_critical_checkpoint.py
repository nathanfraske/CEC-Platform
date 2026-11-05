"""Independent, monotonic ownership of partial critical-route transactions.

A checkpoint certifies only its explicit completed pairs, never residual-route
or fabrication admission. Every trial starts from the last admitted artifact.
"""
import collections
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import tempfile


def partial_admitted(row):
    """All independent gates are mandatory; solver success alone is not proof."""
    return bool(row.get('new_pairs') and row.get('zones_refilled')
        and row.get('parent_copper', {}).get('ok')
        and row.get('placement_unchanged')
        and row.get('source_unchanged')
        and row.get('baseline_refill', {}).get('source_unchanged')
        and row.get('complete_owned_pairs')
        and row.get('pair_physics', {}).get('applicable')
        and row.get('pair_physics', {}).get('ok')
        and row.get('score_admission', {}).get('accepted'))


def validate(parent, candidate, pairs, *, zones_refilled):
    """Read-only saved-board proof. Preserve *all* parent copper, not just locks."""
    import cec_fr
    import cec_full_pipeline as pipeline
    import cec_staged_fr as staged
    import cec_constraints
    import cec_score
    import cec_stage_admission
    parent, candidate = Path(parent).resolve(), Path(candidate).resolve()
    source_hash = hashlib.sha256(parent.read_bytes()).hexdigest()
    before_owned = set(cec_fr.owned_locked_nets(str(parent)))
    after_owned = set(cec_fr.owned_locked_nets(str(candidate)))
    new_pairs = [dict(pair) for pair in pairs
                 if {pair['p'], pair['n']} <= after_owned
                 and not {pair['p'], pair['n']} <= before_owned]
    if not new_pairs:
        return dict(schema=1, ok=False, admission_scope='critical-prefix',
                    residual_allowed=False, release_accepted=False, new_pairs=[],
                    reason='no_new_complete_owned_pair')
    completed = [pair for pair in pairs
                 if {pair['p'], pair['n']} <= after_owned]
    # Include previously admitted pairs: later return vias must not spoil them.
    nets = {pair[key] for pair in completed for key in ('p', 'n')}
    import pcbnew
    connectivity = {}
    connected, _ = staged.fully_connected_nets(
        pcbnew.LoadBoard(str(candidate)), nets, evidence=connectivity)
    board = pcbnew.LoadBoard(str(parent))
    all_nets = {item.GetNetname() for item in board.GetTracks()}
    _, before_rows = cec_fr._copper_geometry_rows(str(parent), all_nets)
    _, after_rows = cec_fr._copper_geometry_rows(str(candidate), all_nets)
    missing = collections.Counter(before_rows) - collections.Counter(after_rows)
    # Stale source fills must not create a false open-count improvement or
    # hide newly severed plane connections. Compare two freshly filled states;
    # the parent itself remains immutable and still owns all preserved copper.
    import cec_route_progress
    with tempfile.TemporaryDirectory(prefix='cec-critical-refill-proof-') as work:
        refill = cec_route_progress.prepare_refill_control(parent, Path(work)/'control')
        before = cec_score.score(refill['control'])
    baseline_refill = {key: refill[key] for key in (
        'source_sha256', 'control_sha256', 'source_unchanged',
        'source_counts', 'refilled_counts')}
    after = cec_score.score(str(candidate))
    row = dict(schema=1, admission_scope='critical-prefix', residual_allowed=False,
        release_accepted=False, parent=str(parent), board=str(candidate),
        parent_sha256=source_hash,
        board_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
        new_pairs=new_pairs, completed_pairs=completed,
        zones_refilled=bool(zones_refilled),
        parent_copper=dict(ok=not missing, missing_items=sum(missing.values())),
        placement_unchanged=(pipeline._placement_position_signature(parent)
                             == pipeline._placement_position_signature(candidate)),
        complete_owned_pairs=bool(new_pairs) and nets <= connected,
        connectivity=connectivity,
        baseline_refill=baseline_refill,
        pair_physics=staged.tier_pair_physics(
            cec_constraints.high_speed_pair_summary(str(candidate)), nets, completed),
        score_admission=cec_stage_admission.evaluate(before, after),
        counts=dict(before=dict(drc=before.drc, opens=before.unconnected),
                    after=dict(drc=after.drc, opens=after.unconnected)),
        source_unchanged=source_hash == hashlib.sha256(parent.read_bytes()).hexdigest())
    row['ok'] = partial_admitted(row)
    # Bind executable sidecars as well as PCB bytes. The next consumer must
    # not reuse the proof after a project rule or copper authority changes.
    row['artifact_signature'] = pipeline._files_signature([
        candidate.with_suffix(suffix) for suffix in (
            '.kicad_pcb', '.kicad_pro', '.kicad_dru', '.pourplan.json',
            '.railreport.json', '.cellreport.json', '.pourfirst-state.json',
            '.pourfirst-skeleton.kicad_pcb') if candidate.with_suffix(suffix).is_file()])
    return row


def complete_reference_planes(source, destination, solved):
    """Close the existing profile-owned reference stage before pair signoff.

    A placement-only board may not yet have its declared GND layers filled.
    That is a missing prerequisite, not permission to waive pair coverage or
    dangling returns. Use the normal plane stage and keep its exact evidence.
    No new signal layer, power slab, via exemption or fabrication rule is made.
    """
    import cec_full_pipeline as pipeline
    import cec_ground_plane
    source,destination=Path(source),Path(destination)
    pipeline._copy_sidecars(source,destination)
    ground = cec_ground_plane.fill_and_admit(str(source),str(destination),
        required_via_uuids=(solved.get('local_pair_return_vias') or {}).get('uuids') or ())
    if ground.get('ok'):
        ground['generated_terminal_cleanup'] = cleanup_generated_terminals(
            destination, solved)
    return ground


def cleanup_generated_terminals(board_path, solved):
    """Normalize only this completed transaction's native-proven track tails.

    A constructive escape can join an earlier package tie before reaching its
    nominal pad-center goal. Whole-net connectivity then passes but native DRC
    identifies the excess as a dangling tail. Reuse the monotonic native repair
    at this producer handoff, not a board/refdes-specific deletion. Preserve all
    inherited copper, every via, and all non-pair nets. Independent checkpoint
    validation remains mandatory after the repair, including every old pair.
    """
    import pcbnew
    import cec_synth_pipeline as synth
    pair_nets = {row[key] for row in (solved.get('pairs') or {}).get('routed', ())
                 for key in ('p', 'n') if row.get(key)}
    generated = {row['uuid']: row for row in solved.get('generated_items', ())
                 if row.get('uuid') and row.get('kind') == 'PCB_TRACK'
                 and row.get('net') in pair_nets}
    if not generated:
        return dict(applicable=False, removed_count=0)
    board = pcbnew.LoadBoard(str(board_path))
    all_ids = {item.m_Uuid.AsString() for item in board.GetTracks()}
    writable = {item.m_Uuid.AsString() for item in board.GetTracks()
                if item.m_Uuid.AsString() in generated
                and item.GetClass() == 'PCB_TRACK'
                and item.GetNetname() == generated[item.m_Uuid.AsString()]['net']}
    if not writable:
        return dict(applicable=False, removed_count=0)
    report, _score = synth._prune_structural_dangling_transactionally(
        str(board_path), preserve_uuids=all_ids-writable,
        max_rounds=4, refill_zones=True)
    return dict(report, applicable=True, writable_count=len(writable),
                preserved_count=len(all_ids-writable),
                scope='exact-generated-pair-tracks-only')


@contextmanager
def frozen_power_context(board, cfg):
    """Bind committed power for a constructive dependency, not a new auction.

    The ordinary critical-first search may negotiate prospective power. A
    reconstruction called after power admission owes that exact authority.
    Instance-owned paths override inherited environment only within this
    transaction and are revalidated for each newly admitted pair parent.
    """
    if cfg is None:
        yield None
        return
    import cec_synth_pipeline as synth
    bound, binding = synth.config_with_board_route_authority(cfg, str(board))
    if not binding.get('ok') or not binding.get('bound'):
        raise ValueError('committed power authority cannot bind: %s' % binding)
    params = dict(bound.params)
    params.pop('placement_route_pair_timeout_s', None)
    overrides = {'CEC_POURFIRST_STATE': str(binding['state']),
                 'CEC_POUR_RESERVE': '1', 'CEC_ROUTE_PRIORITY_POLICY': 'power-first'}
    with synth._oracle_env(params):
        saved = {key: os.environ.get(key) for key in overrides}
        try:
            os.environ.update(overrides)
            yield binding
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def construct(source, out, pairs, *, frozen_route_config=None):
    """Bounded per-pair transactions using the production precision solver.

    Pair declarations, pads and policy come from the board/project. Failed
    trials are retained as evidence but never become the next trial's parent.
    """
    import cec_fr
    import cec_precision_route as precision
    import cec_route_preflight as preflight
    import cec_operation_budget as budget
    from cec_placement_checkpoint import atomic_json
    source, out = Path(source).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    current = source
    report = dict(schema=1, admission_scope='critical-prefix', residual_allowed=False,
                  release_accepted=False, attempts=[], selected=None, ok=False)
    for index, pair in enumerate(pairs):
        owned = set(cec_fr.owned_locked_nets(str(current)))
        if {pair['p'], pair['n']} <= owned:
            continue
        target = out / ('pair-%02d' % index) / 'board.kicad_pcb'
        target.parent.mkdir()
        row = dict(pair=pair, parent=str(current), board=str(target), status='routing')
        budget.progress('critical_checkpoint_pair_search', pair=pair['name'], directory=str(out))
        print('[critical-checkpoint] pair %s from %s' % (pair['name'], current), flush=True)
        report['attempts'].append(row)
        atomic_json(out/'checkpoint.json', report)
        try:
            with frozen_power_context(current, frozen_route_config) as binding:
                reservations = preflight.compile_route_reservations(str(current))
                if binding and not reservations.get('enabled'):
                    raise ValueError('committed power reservations were disabled')
                avoid = preflight.priority_pair_avoid(str(current), reservations,
                    policy='power-first' if binding else None)
                row['reservation_authority'] = {
                    'binding': binding, 'enabled': reservations.get('enabled',False),
                    'policy': 'power-first' if binding else preflight.route_priority_policy(),
                    'fingerprint': reservations.get('fingerprint'),
                    'corridors': len(reservations.get('corridors') or ()),
                    'avoid_rectangles': len(avoid)}
                atomic_json(out/'checkpoint.json', report)
                try:
                    solved = precision.precision_route(str(current), str(target),
                        do_kelvin=False, pair_grid=True,
                        include_pair_names=[pair['name']], avoid=avoid)
                except precision.PrecisionRouteRefused as exc:
                    solved = exc.report
            row['solver'] = solved
            row['status'] = 'solver-returned'
            atomic_json(out/'checkpoint.json', report)
            refilled=solved.get('zones_refilled')
            if solved.get('pairs_ok'):
                budget.progress('critical_checkpoint_reference_fill', pair=pair['name'])
                referenced=target.with_name('referenced.kicad_pcb')
                ground=complete_reference_planes(target,referenced,solved)
                row['reference_stage']=ground
                if not ground.get('ok'):
                    raise ValueError('critical prefix reference stage refused: %s' %
                                     (ground.get('reasons') or ground.get('reason')))
                target=referenced
                row['board']=str(target)
                refilled=True
            budget.progress('critical_checkpoint_independent_proof', pair=pair['name'])
            row['proof'] = validate(current, target, pairs,
                                    zones_refilled=refilled)
            row['ok'] = row['proof']['ok']
            if row['ok']:
                current = target
                report.update(ok=True, selected=str(target), proof=row['proof'])
            row['status'] = 'prefix-admitted' if row['ok'] else 'refused'
        except Exception as exc:
            row.update(ok=False, status='failed', error=type(exc).__name__+': '+str(exc))
        atomic_json(out/'checkpoint.json', report)
        budget.progress('critical_checkpoint_pair_complete', pair=pair['name'], status=row['status'])
        print('[critical-checkpoint] pair %s: %s' % (pair['name'], row['status']), flush=True)
    atomic_json(out/'checkpoint.json', report)
    return report
