"""Exact source-owned redundant force-branch subtraction, never a rating.

The request selects existing native traces, not a board/refdes/coordinate
exception. Complete source current authority remains unchanged. Saved native
receiving preserves every surviving conductor/land partition and every
trace/rated authority connection. Only an exact subtract/refill replay is
allowed; placement, source barrels, zones and all other traces stay owned.
Full DRC, clipped Kelvin, field and release receiving remain mandatory.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_collector_reconstruction as collector
import cec_copper_echo as sexpr
import cec_current_path_receiving as current_paths
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items


def _budget(seconds):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0 < seconds <= 10):
        raise ValueError('bounded_redundant_force_branch_budget_required')
    return time.monotonic() + seconds


def _count(value):
    if type(value) is not int or not 1<=value<=32:
        raise ValueError('bounded_explicit_force_branch_count_required')
    return value


def _ids(values, *, empty=False, maximum=16):
    maximum=_count(maximum)
    if (not isinstance(values, (tuple, list, set, frozenset))
            or any(type(value) is not str or not value for value in values)
            or len(values) != len(set(values)) or not (0 if empty else 1) <= len(values) <= maximum):
        raise ValueError('bounded_exact_force_branch_inventory_required')
    return set(values)


def _model(board, net, hint):
    with force._thermal_hint(hint):
        domain = topology.board_current_domains(board, hint).get(net)
        contract = topology.route_width_contracts(board, hint).get(net)
    if (not domain or domain.get('complete') is not True or not contract
            or not domain.get('source_refs') or not domain.get('sink_refs')
            or contract.get('net') != net or domain.get('net') != net):
        raise ValueError('complete_source_owned_force_domain_required')
    for model in (domain, contract):
        amps = model.get('amps')
        if type(amps) not in (int, float) or not math.isfinite(amps) or amps <= 0:
            raise ValueError('positive_unchanged_source_current_authority_required')
    if domain['amps'] != contract['amps']:
        raise ValueError('source_current_authority_disagreement')
    return domain, contract


def plan(board, track_uuids, *, net, board_hint, allow_locked_track_uuids=(), timeout_s=10.,max_retired_tracks=16):
    """Exact private proposal. Redundancy is NOT inferred from pad counts."""
    deadline = _budget(timeout_s)
    maximum=_count(max_retired_tracks)
    selected = _ids(track_uuids,maximum=maximum)
    unlocked = _ids(allow_locked_track_uuids, empty=True,maximum=maximum)
    if (type(net) is not str or not net or type(board_hint) is not str or not board_hint
            or not unlocked <= selected or net not in board.GetNetsByName()):
        raise ValueError('explicit_source_force_branch_owner_required')
    native, cut = collector.owned_retirement(board, net, track_uuids=sorted(selected),
        timeout_s=min(10., deadline-time.monotonic()))
    domain, contract = _model(board, net, board_hint)
    rows = []
    for item in native:
        if time.monotonic() >= deadline:
            raise ValueError('redundant_force_branch_plan_deadline')
        uid = force._uid(item)
        if (item.IsLocked() and uid not in unlocked or item.GetWidth() <= 0
                or not 0 < item.GetLength() <= 100000000):
            raise ValueError('source_force_branch_lock_or_geometry_refused')
        layer = int(item.GetLayer())
        import cec_fab_profile as fab
        name = fab.COPPER_LAYER_IDS.get(layer)
        required = contract.get('required_by_layer_mm', {}).get(name)
        if (name not in fab.enabled_copper_layers(board)
                or type(required) not in (int, float) or not math.isfinite(required) or required <= 0):
            raise ValueError('native_force_branch_layer_or_current_requirement_unknown')
        rows.append(dict(uuid=uid, net=net, layer_id=layer, layer=name,
            width_nm=item.GetWidth(), source_required_width_mm=required,
            source_locked=bool(item.IsLocked()), start_nm=list(item.GetStart()), end_nm=list(item.GetEnd())))
    if sum(item.GetLength() for item in native) > 256000000:
        raise ValueError('source_force_branch_total_length_bound')
    return dict(schema=1, net=net, board_hint=board_hint, track_uuids=sorted(selected),
        max_retired_tracks=maximum,
        allow_locked_track_uuids=sorted(unlocked), exact_cut=cut, source_tracks=rows,
        source_current_domain=domain, source_current_contract=contract,
        source_binding=field._field_snapshot_inventory(board),
        release_authority=False, current_qualified=False, redundancy_proved=False,
        saved_partition_and_current_receiving_required=True)


def subtract(board, proposal):
    if field._field_snapshot_inventory(board) != proposal.get('source_binding'):
        raise ValueError('force_branch_source_binding_changed')
    rebuilt = plan(board, proposal['track_uuids'], net=proposal['net'],
        board_hint=proposal['board_hint'], allow_locked_track_uuids=proposal['allow_locked_track_uuids'],
        max_retired_tracks=proposal.get('max_retired_tracks',16))
    if rebuilt != proposal:
        raise ValueError('force_branch_source_authority_or_native_scope_changed')
    selected = set(proposal['track_uuids'])
    discard_items(board, [item for item in board.GetTracks() if force._uid(item) in selected])


def preserved_partitions(before, after):
    """All surviving copper-only junctions are vertices, not only pads."""
    if (not isinstance(before, list) or not before or not isinstance(after, list) or not after
            or len(before) > 32768 or len(after) > 32768
            or any(not isinstance(part, set) or not part for part in before + after)):
        raise ValueError('complete_native_force_branch_partitions_required')
    if sum(map(len, before)) != len(set().union(*before)) or sum(map(len, after)) != len(set().union(*after)):
        raise ValueError('ambiguous_native_force_branch_partition')
    return all(any(part <= other for other in after) for part in before)


def receive(source, candidate, *, track_uuids, net, board_hint,
            allow_locked_track_uuids=(), timeout_s=10.,max_retired_tracks=16):
    result = dict(schema=1, ok=False, complete=False, errors=[],
        current_qualified=False, plated_barrel_rating_qualified=False,
        inherited_debt_qualified=False, release_authority=False,
        full_saved_board_receiving_still_required=True)
    started = time.monotonic()
    try:
        deadline = _budget(timeout_s)
        source, candidate = [Path(path).resolve() for path in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_force_branch_candidate_required')
        families = [force._family(path, board_hint) for path in (source, candidate)]
        epoch = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(path)) for path in (source, candidate)]
        proposal = plan(parent, track_uuids, net=net, board_hint=board_hint,
            allow_locked_track_uuids=allow_locked_track_uuids,
            max_retired_tracks=max_retired_tracks,
            timeout_s=min(10., deadline-time.monotonic()))
        retired = set(proposal['track_uuids'])
        _, old = additive._nodes(source)
        _, new = additive._nodes(candidate)
        if old.keys()-new.keys() != retired or new.keys()-old.keys():
            raise ValueError('exact_source_force_branch_subtraction_only')
        before = ordinary._partition(parent, deadline, retired_uuids=retired)
        retained = set().union(*before)
        after = ordinary._partition(child, deadline, retained_keys=retained)
        if not preserved_partitions(before, after):
            raise ValueError('force_branch_cut_lost_surviving_native_partition')
        old_domain, old_contract = _model(parent, net, board_hint)
        new_domain, new_contract = _model(child, net, board_hint)
        if old_domain != new_domain or old_contract != new_contract:
            raise ValueError('force_branch_current_domain_or_contract_changed')
        resolver = fr._project_netclass_resolver(str(source))
        first = force._graph(parent, net, old_domain, old_contract, resolver(net) or {})[0]
        last = force._graph(child, net, new_domain, new_contract, resolver(net) or {})[0]
        paths = current_paths.compare(first, last)
        result['independent_trace_and_rated_authority_partitions'] = paths
        if not paths['ok'] or not paths['complete'] or paths['new_joins']:
            raise ValueError('force_branch_current_path_preservation_refused')
        with tempfile.TemporaryDirectory(prefix='cec-redundant-force-branch-') as work:
            projected = force._copy_family(source, Path(work)/'projected')
            basis = pcbnew.LoadBoard(str(projected))
            subtract(basis, proposal)
            field._save_field_snapshot(basis, projected)
            _, exact = additive._nodes(projected)
            if exact.keys() != old.keys()-retired or any(
                    sexpr._freeze(exact[uid]) != sexpr._freeze(old[uid]) for uid in exact):
                raise ValueError('force_branch_subtraction_changed_unowned_native_material')
            remaining = min(10., deadline-time.monotonic())
            if remaining <= 0:
                raise ValueError('force_branch_saved_replay_deadline')
            replay = additive.receive(projected, candidate, timeout_s=remaining)
            result['independent_source_cut_and_ground_refill_replay'] = replay
            if not replay.get('ok') or not replay.get('complete'):
                raise ValueError('force_branch_exact_saved_replay_refused')
        if (epoch != force._code_identity()
                or families != [force._family(path, board_hint) for path in (source, candidate)]
                or time.monotonic() >= deadline):
            raise ValueError('force_branch_inputs_code_or_deadline_changed')
        result.update(ok=True, complete=True, retired_track_uuids=sorted(retired),
            source_current_domain=old_domain, source_current_contract=old_contract,
            all_surviving_native_partitions_preserved=True,
            all_existing_trace_and_rated_authority_connections_preserved=True,
            remaining_source_current_debt_not_qualified=True)
    except (ValueError, TypeError, KeyError, RuntimeError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s'] = round(time.monotonic()-started, 6)
    return result
