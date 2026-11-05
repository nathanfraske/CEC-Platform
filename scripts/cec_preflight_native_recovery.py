"""Bounded additive construction for raster-refused rated obligations.

A failed grid search is not a physical no-path proof. This module tries the
existing exact pin/bridge constructor on a private child, then re-proves that
child after save/refill. It cannot waive preflight, advance residual routing,
resize parent copper, move a part, or certify thermal/fabrication release.
"""
from __future__ import annotations

import hashlib
import math
import os
from contextlib import contextmanager
from pathlib import Path
import shutil
import time


SIDECARS = ('.kicad_pcb', '.kicad_pro', '.kicad_dru', '.pourplan.json',
            '.cellreport.json', '.railreport.json', '.pourfirst-state.json',
            '.pourfirst-skeleton.kicad_pcb', '.priority-replacements.json',
            '.power-prefix.json', '.route-lineage.json')


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def authority_signature(source):
    import cec_full_pipeline as pipeline
    source = Path(source).resolve()
    return pipeline._files_signature([source.with_suffix(suffix)
        for suffix in SIDECARS if source.with_suffix(suffix).is_file()])


def targets(report, *, max_nets=4):
    """Select only explicit critical raster refusals, never warning/net guesses."""
    if type(max_nets) is not int or not 1 <= max_nets <= 16:
        raise ValueError('finite obligation-group bound required')
    if report.get('error') or report.get('gate'):
        return ()
    critical = report.get('criticality') or {}
    if 'criticality' in report:
        failed = critical.get('unroutable_connections') or ()
        declared = set(critical.get('nets') or ())
    else:
        # The placement priority worker returns the standard compact receipt.
        # Use only its explicitly critical rows, never ordinary warnings.
        failed = report.get('critical_unroutable_connections') or ()
        declared = {row.get('net') for row in failed if row.get('net')}
    names = sorted({str(row.get('net')) for row in failed
                    if row.get('net') and row.get('net') in declared})
    return tuple(names) if 0 < len(names) <= max_nets else ()


def placement_eligible(report):
    """Try routing before moving an otherwise legal raster-refused placement."""
    return bool(targets(report) and all(report.get(key) == 0 for key in (
        'critical_route_refused_count', 'critical_declaration_error_count',
        'critical_pin_access_blocked_count', 'fanout_blocked_count')))


def admitted(terms):
    """Missing independent evidence is a refusal, not a solver success."""
    required = ('zones_refilled', 'source_unchanged', 'source_authority_unchanged', 'parent_copper_preserved',
                'placement_unchanged', 'explicit_nets_complete',
                'current_widths_qualified', 'new_geometry_conforms',
                'previous_pairs_preserved', 'structural_admission',
                'connectivity_improved', 'only_requested_nets_added')
    return all(terms.get(key) is True for key in required)


def geometry_scope_ok(gate, new_ids):
    if gate[0] is True:
        return True
    rows = gate[2] if len(gate) > 2 else ()
    return bool(gate[0] is False and rows and all(
        isinstance(row, dict) and row.get('uuids')
        and not (set(row['uuids']) & set(new_ids)) for row in rows))


@contextmanager
def _current_identity(hint):
    key = 'CEC_THERMAL_BOARD_HINT'
    previous = os.environ.get(key)
    if hint and previous and hint != previous:
        raise ValueError('conflicting current-domain identity')
    try:
        if hint:
            os.environ[key] = str(hint)
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def construct(source, out, nets, *, board_hint='', wall_s=90.,
              max_span_mm=50., attempts_per_pair=8):
    """Construct one finite current-aware proposal; admission is prefix-only.

    The caller must run normal whole-board preflight on an admitted child.
    Current widths come from the existing source/sink contract, with its margin
    applied once and actual per-layer copper. Local process-qualified POFV uses
    the existing exact containment/dogbone rules. Barrel thermal/current-field
    qualification remains a mandatory downstream release gate, not a claim
    made by this trace-width/connectivity transaction.
    """
    with _current_identity(board_hint):
        return _construct(source, out, nets, board_hint=board_hint, wall_s=wall_s,
                          max_span_mm=max_span_mm, attempts_per_pair=attempts_per_pair)


def _construct(source, out, nets, *, board_hint, wall_s, max_span_mm,
               attempts_per_pair):
    if (type(wall_s) not in (int, float) or not math.isfinite(wall_s)
            or not 0 < wall_s <= 300 or type(max_span_mm) not in (int, float)
            or not math.isfinite(max_span_mm) or not 0 < max_span_mm <= 100
            or type(attempts_per_pair) is not int
            or not 1 <= attempts_per_pair <= 32):
        raise ValueError('finite native construction policy required')
    wanted = tuple(sorted({str(net) for net in nets if net}))
    if not 0 < len(wanted) <= 4:
        raise ValueError('one bounded explicit obligation group required')
    import pcbnew
    import cec_fr as fr
    import cec_current_topology as topology
    import cec_route_dimensions as dimensions
    import cec_precision_route as precision
    import cec_full_pipeline as pipeline
    import cec_constraints as constraints
    import cec_staged_fr as staged
    import cec_score
    import cec_stage_admission
    import cec_route_progress
    from cec_placement_checkpoint import atomic_json
    from cec_search_completion import search_completion_evidence

    source, out = Path(source).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    start, source_hash = time.monotonic(), _sha(source)
    suffixes = SIDECARS
    source_signature = authority_signature(source)
    board = pcbnew.LoadBoard(str(source))
    domains = topology.board_current_domains(board, board_hint=board_hint)
    contracts = topology.route_width_contracts(board, board_hint=board_hint)
    paired = precision.derive_coupled_pairs(str(source), board=board)
    paired_nets = {pair[key] for pair in paired for key in ('p', 'n')}
    ineligible = [net for net in wanted if net in paired_nets
                  or not (domains.get(net) or {}).get('complete')
                  or net not in contracts]
    report = dict(schema=1, ok=False, source=str(source),
        source_sha256=source_hash, nets=list(wanted), board=None,
        admission_scope='native-obligation-prefix', residual_allowed=False,
        release_accepted=False, thermal_qualified=False, current_contracts={
            net: contracts[net] for net in wanted if net in contracts},
        source_authority_signature=source_signature,
        policy=dict(wall_s=wall_s, max_span_mm=max_span_mm,
                    attempts_per_pair=attempts_per_pair))
    if ineligible:
        report.update(reason='missing_rated_domain_or_precision_owned',
                      ineligible_nets=ineligible, source_unchanged=_sha(source)==source_hash)
        atomic_json(out/'report.json', report)
        return report

    all_nets = {str(item.GetNetname()) for item in board.GetTracks()}
    prefix = fr.copper_geometry_prefix_contract(str(source), all_nets)
    parent_positions = pipeline._placement_position_signature(source)
    owned = fr.owned_locked_nets_board(board)
    retained_pairs = [pair for pair in paired
                      if {pair['p'], pair['n']} <= owned]
    before_ids = {item.m_Uuid.AsString() for item in board.GetTracks()}
    target = out/'board.kicad_pcb'
    shutil.copy2(source, target)
    fr.copy_project_sidecars(str(source), str(target))
    atomic_json(out/'report.json', dict(report, status='running'))
    try:
        # This is the ordinary exact constructor, not a relaxed routing backend.
        # Its source graph includes all local leaves but only the trunk width
        # metadata carries aggregate current. No new branch load is invented.
        resolver = dimensions.with_trunk_contracts(
            dimensions.project_resolver(str(source), board=board), contracts)
        solved = fr.synthesize_lastmile(board, include_nets=wanted,
            max_mm=max_span_mm, cap=24, attempts_per_pair=attempts_per_pair,
            min_w=dimensions.board_limits(board)['track_width'], clearance=0.,
            netclass_resolver=resolver, lock=True,
            maze_max_mm=max_span_mm, maze_margin_mm=4.,
            wall_timeout_s=wall_s, per_net_timeout_s=wall_s/len(wanted))
        pcbnew.SaveBoard(str(target), board)
        fr.ensure_endpoint_neckdown_rule(str(target), solved)
        fr.ensure_local_pofv_signal_via_rule(str(target), solved)
        refilled = fr.refill_zones(str(target))
        saved = pcbnew.LoadBoard(str(target))
        connection_evidence = {}
        complete, incomplete = staged.fully_connected_nets(
            saved, wanted, evidence=connection_evidence)
        new_items = [item for item in saved.GetTracks()
                     if item.m_Uuid.AsString() not in before_ids]
        copper = fr.check_copper_geometry_prefix(str(target), prefix)
        # Both states are freshly filled, so stale source zones cannot be
        # attributed to newly routed copper.
        refill = cec_route_progress.prepare_refill_control(source, out/'control')
        before = cec_score.score(refill['control'])
        after = cec_score.score(str(target))
        score_admission = cec_stage_admission.evaluate(before, after)
        pair_nets = {pair[key] for pair in retained_pairs for key in ('p', 'n')}
        pair_physics = staged.tier_pair_physics(
            constraints.high_speed_pair_summary(str(target)), pair_nets, retained_pairs)
        width_gate = constraints._chk_tw(saved, str(target),
            dict(current_domain_include_nets=wanted))
        geometry_gate = constraints._chk_netclass_geom(saved, str(target), {})
        new_ids = {item.m_Uuid.AsString() for item in new_items}
        # Existing geometry debt is retained, not silently repaired or waived.
        # A new object must conform; complete independent release still checks
        # all inherited objects and the physical barrel current field.
        new_geometry_faults = [row for row in
            (geometry_gate[2] if len(geometry_gate)>2 else ())
            if new_ids & set(row.get('uuids') or ())]
        terms = dict(zones_refilled=bool(refilled),
            source_unchanged=bool(_sha(source)==source_hash and refill['source_unchanged']),
            source_authority_unchanged=source_signature == authority_signature(source),
            parent_copper_preserved=bool(copper['ok']),
            placement_unchanged=parent_positions==pipeline._placement_position_signature(target),
            explicit_nets_complete=set(wanted)<=complete,
            current_widths_qualified=width_gate[0] is True,
            new_geometry_conforms=geometry_scope_ok(geometry_gate, new_ids),
            previous_pairs_preserved=bool(pair_physics.get('ok')) if retained_pairs else True,
            structural_admission=bool(score_admission['accepted']),
            connectivity_improved=after.unconnected<before.unconnected,
            only_requested_nets_added=bool(new_items) and all(
                item.GetNetname() in wanted for item in new_items))
        report.update(ok=admitted(terms), status='finished', terms=terms,
            proposal=str(target), proposal_sha256=_sha(target),
            solver=solved, complete=sorted(complete), incomplete=sorted(incomplete),
            connectivity=connection_evidence, parent_copper=copper,
            current_width_gate=width_gate, new_geometry_faults=new_geometry_faults,
            pair_physics=pair_physics, score_admission=score_admission,
            added_items=len(new_items), counts=dict(
                before=dict(opens=before.unconnected,drc=before.drc),
                after=dict(opens=after.unconnected,drc=after.drc)),
            baseline_refill={key:refill[key] for key in (
                'source_sha256','control_sha256','source_unchanged',
                'source_counts','refilled_counts')})
        if report['ok']:
            report['board'] = str(target)
        report['search_completion'] = search_completion_evidence(solved)
        report['search_inconclusive'] = bool(not report['ok']
            and report['search_completion']['inconclusive'])
    except Exception as exc:
        report.update(status='failed', error=type(exc).__name__+': '+str(exc))
    report.update(elapsed_s=time.monotonic()-start,
                  source_unchanged=_sha(source)==source_hash)
    signed = [path.with_suffix(suffix) for path in (source, target)
              for suffix in suffixes
              if path.with_suffix(suffix).is_file()]
    report['artifact_signature'] = pipeline._files_signature(signed)
    atomic_json(out/'report.json', report)
    return report


def main():
    import argparse
    import json
    import cec_swig_guard
    cec_swig_guard.pin()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--nets-json', required=True)
    parser.add_argument('--board-hint', default='')
    parser.add_argument('--wall-s', type=float, default=90.)
    parser.add_argument('--max-span-mm', type=float, default=50.)
    parser.add_argument('--attempts-per-pair', type=int, default=8)
    args = parser.parse_args()
    nets = json.loads(args.nets_json)
    if not isinstance(nets, list) or any(not isinstance(net, str) for net in nets):
        raise ValueError('explicit JSON net-name list required')
    report = construct(args.source, args.out, nets, board_hint=args.board_hint,
        wall_s=args.wall_s, max_span_mm=args.max_span_mm,
        attempts_per_pair=args.attempts_per_pair)
    print(json.dumps({key:report.get(key) for key in (
        'ok','board','reason','error','counts','terms','elapsed_s')}, indent=2))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
