"""Source-typed quiet-peer duplicate material, not electrical cut authority.

Only a freshly compiled manufacturer input/quiet-peer relationship can select
work.  The existing exact native pad-union receiver owns the physical proof;
the subsequent fanout still owes its unchanged receiver and absolute AFTER
evidence.  Callers cannot supply cuts, lock permissions, widths or roles.
"""
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as binding
import cec_force_current as force
import cec_measurement_quiet_fanout as fanout
import cec_pad_contained_track_retirement as retirement
import cec_source_literal_retirement as literal


def _deadline(timeout_s):
    return retirement._deadline(timeout_s)


def _left(deadline):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise ValueError('quiet_pad_cleanup_deadline')
    return min(10., remaining)


def plan(board, source, *, board_hint, input_pad_uuid, peer_pad_uuid, timeout_s=10.):
    deadline = _deadline(timeout_s)
    if (any(type(v) is not str or not v for v in
            (board_hint, input_pad_uuid, peer_pad_uuid)) or input_pad_uuid == peer_pad_uuid):
        raise ValueError('distinct_actual_quiet_input_and_peer_identities_required')
    source = Path(source).resolve(strict=True)
    epoch = force._code_identity(); family = force._family(source, board_hint)
    native = binding._source_binding(board)
    if native != binding._source_binding(pcbnew.LoadBoard(str(source))):
        raise ValueError('exact_saved_quiet_pad_cleanup_source_required')
    quiet = fanout.plan(board, source, board_hint=board_hint,
        pad_uuid=input_pad_uuid, peer_pad_uuid=peer_pad_uuid, timeout_s=_left(deadline))
    if quiet.get('complete') is not True or quiet.get('peer_pad_uuid') != peer_pad_uuid:
        raise ValueError('fresh_manufacturer_input_and_qualified_quiet_peer_required')
    tree = quiet['source_quiet_tree']
    demand = quiet['source_request']['request']['demand']
    if (tree.get('exact_direct_lineage_rederived_for_all_inputs') is not True
            or tree.get('inward_departure', {}).get('ok') is not True
            or tree.get('via_uuids') or peer_pad_uuid not in tree['leaf_pad_uuids']
            or tree.get('exact_shunt_pad_uuid') != demand['target_uuid']):
        raise ValueError('actual_front_only_manufacturer_quiet_tree_required')
    ids = tree.get('fully_land_contained_track_uuids', [])
    if (type(ids) is not list or not 1 <= len(ids) <= 8 or len(set(ids)) != len(ids)
            or not set(ids) <= set(tree['track_uuids'])):
        raise ValueError('bounded_source_owned_quiet_pad_duplicates_required')
    pads = {force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    peer = pads[peer_pad_uuid]
    tracks = {force._uid(t):t for t in board.GetTracks()}
    for uid in ids:
        _left(deadline)
        item = tracks[uid]
        if (item.GetClass() != 'PCB_TRACK' or item.GetLayer() != pcbnew.F_Cu
                or item.GetNetCode() != peer.GetNetCode() or item.GetNetname() != demand['net']
                or item.HasSolderMask() or any(g.ContainsItem(item) for g in board.Groups())):
            raise ValueError('ungrouped_unmasked_actual_peer_quiet_material_required')
    physical = retirement.plan(board, ids, allow_owned_locked=True, timeout_s=_left(deadline))
    if any({p['pad_uuid'] for p in row['containing_source_pads']} != {peer_pad_uuid}
            for row in physical['records']):
        raise ValueError('entire_duplicate_must_belong_to_exact_qualified_peer_land')
    result = dict(schema=1, complete=True, scope='source_qualified_quiet_input_pad_cleanup', source=str(source),
        board_hint=board_hint, input_pad_uuid=input_pad_uuid, peer_pad_uuid=peer_pad_uuid,
        source_native_binding=native, source_family=family, code_identity=epoch,
        source_input_demand=demand, source_quiet_tree=tree, retirement=physical,
        retired_track_uuids=physical['track_uuids'], physical_copper_union_unchanged=True,
        current_authority=False, electrical_retirement_authority=False,
        routing_admitted=False, kelvin_qualified=False, release_authority=False,
        subsequent_unmodified_fanout_and_absolute_after_receiving_required=True)
    if (native != binding._source_binding(board) or family != force._family(source, board_hint)
            or epoch != force._code_identity()):
        raise ValueError('quiet_pad_cleanup_source_epoch_changed')
    _left(deadline)
    return result


def materialize(board, source, proposal, *, timeout_s=10.):
    deadline = _deadline(timeout_s)
    fresh = plan(board, source, board_hint=proposal['board_hint'],
        input_pad_uuid=proposal['input_pad_uuid'], peer_pad_uuid=proposal['peer_pad_uuid'],
        timeout_s=_left(deadline))
    if fresh != proposal:
        raise ValueError('stale_or_forged_source_quiet_pad_cleanup')
    proof = retirement.materialize(board, fresh['retirement'], timeout_s=_left(deadline))
    if (fresh['source_family'] != force._family(Path(source), fresh['board_hint'])
            or fresh['code_identity'] != force._code_identity()):
        raise ValueError('quiet_pad_materialization_source_epoch_changed')
    _left(deadline)
    return proof


def construct_private(source, candidate, proposal, *, timeout_s=10.):
    deadline = _deadline(timeout_s)
    source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
    if source == candidate or force._hash(source) != force._hash(candidate):
        raise ValueError('exact_private_quiet_cleanup_source_copy_required')
    epoch = force._code_identity(); family = force._family(source, proposal['board_hint'])
    if force._sidecars(source) != force._sidecars(candidate):
        raise ValueError('quiet_cleanup_private_sidecars_changed')
    board = pcbnew.LoadBoard(str(source))
    proof = materialize(board, source, proposal, timeout_s=_left(deadline))
    projected = literal.write_native_projection(source, candidate, proof['retired_track_uuids'], board)
    digest = force._hash(candidate)
    if epoch != force._code_identity() or family != force._family(source, proposal['board_hint']):
        raise ValueError('quiet_cleanup_construction_source_epoch_changed')
    _left(deadline)
    return dict(complete=True, physical_copper_union_unchanged=True, materialized=proof,
        literal_projection=projected, candidate_sha256=digest,
        independent_saved_receiving_required=True, release_authority=False)


def receive(source, candidate, *, board_hint, input_pad_uuid, peer_pad_uuid, timeout_s=10.):
    deadline = _deadline(timeout_s)
    result = dict(ok=False, complete=False, errors=[], scope='saved_source_quiet_input_pad_cleanup',
        physical_copper_union_unchanged=False, current_authority=False,
        electrical_retirement_authority=False, routing_admitted=False,
        kelvin_qualified=False, release_authority=False,
        subsequent_unmodified_fanout_and_absolute_after_receiving_required=True)
    try:
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        epoch = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        fresh = plan(pcbnew.LoadBoard(str(source)), source, board_hint=board_hint,
            input_pad_uuid=input_pad_uuid, peer_pad_uuid=peer_pad_uuid, timeout_s=_left(deadline))
        proof = retirement.receive(source, candidate, fresh['retirement'], timeout_s=_left(deadline))
        if not proof.get('ok') or not proof.get('complete'):
            raise ValueError('independent_pad_union_retirement_refused:'+str(proof.get('errors')))
        if epoch != force._code_identity() or families != [force._family(p, board_hint) for p in (source, candidate)]:
            raise ValueError('saved_quiet_cleanup_source_epoch_changed')
        _left(deadline)
        result.update(ok=True, complete=True, independently_compiled_source_scope=fresh,
            physical_receiving=proof, physical_copper_union_unchanged=True,
            retired_track_uuids=fresh['retired_track_uuids'])
    except (ValueError, RuntimeError, TypeError, KeyError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
