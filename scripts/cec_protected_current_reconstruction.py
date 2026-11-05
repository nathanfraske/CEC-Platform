"""Retain protected copper through an independently received current repair.

This is not a net waiver or a new route owner. A leading, finite sequence of
the existing whole-current planar repairs is re-received from saved native
parents. Only its exact old primitives can leave the original locked prefix;
every replacement primitive becomes obligatory, including unlocked ones.
All other original members and qualified pairs remain mandatory. Final DRC,
current, field, returns, Kelvin, intake and assembly gates are still separate.
"""
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import time

import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_placement_route_prefix as protected
import cec_source_cut_chain as chain


def _saved(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('regular_unaliased_saved_copper_parent_required')
    return path.resolve(strict=True)


def _phases(rows):
    if type(rows) not in (list, tuple) or len(rows) > 4:
        raise ValueError('finite_leading_full_current_reconstruction_required')
    result = []
    retired = set()
    for row in rows:
        expected = {'kind', 'candidate', 'candidate_sha256', 'retired_track_uuids'}
        if (type(row) is not dict or set(row) != expected
                or row['kind'] != 'full_current_planar_reflow'
                or type(row['candidate']) is not str or not row['candidate']
                or type(row['candidate_sha256']) is not str
                or not re.fullmatch('[0-9a-f]{64}', row['candidate_sha256'])):
            raise ValueError('exact_saved_full_current_phase_identity_required')
        ids = ordinary._ids(row['retired_track_uuids'], 'protected_current_cut', 8)
        if not ids or ids & retired:
            raise ValueError('nonempty_disjoint_original_current_cuts_required')
        retired.update(ids)
        path = _saved(row['candidate'])
        if force._hash(path) != row['candidate_sha256']:
            raise ValueError('declared_full_current_phase_changed')
        result.append(dict(row, candidate=path))
    return result


def _digest(row):
    return hashlib.sha256(json.dumps(row, separators=(',', ':'),
        ensure_ascii=True).encode('utf-8')).hexdigest()


def _reconstruct(source, repaired, frozen, proof):
    """Internal native accounting, called only after fresh typed receiving."""
    before, after = [pcbnew.LoadBoard(str(p)) for p in (source, repaired)]
    old, new = [{force._uid(t): t for t in b.GetTracks()} for b in (before, after)]
    retired, added = set(old) - set(new), set(new) - set(old)
    if (retired != set(proof['retired_track_uuids']) or proof['retired_via_uuids']
            or added != set(proof['added_native_uuids'])
            or not 1 <= len(retired) <= 32 or not 1 <= len(added) <= 128
            or any(old[u].GetClass() != 'PCB_TRACK' for u in retired)
            or any(new[u].GetClass() != 'PCB_TRACK' for u in added)):
        raise ValueError('actual_native_current_manifest_differs_from_received_chain')
    # Locked source cuts only. An unlocked coincident copy must not remove a
    # locked member's obligation merely because it has the same geometry.
    _, removed_rows = fr._copper_geometry_rows(str(source), (),
        locked_only=True, item_uuids=retired)
    _, replacement_rows = fr._copper_geometry_rows(str(repaired), (), item_uuids=added)
    if len(replacement_rows) != len(added):
        raise ValueError('every_received_replacement_must_be_native_copper')
    contract = copy.deepcopy(frozen)
    members = Counter(contract['members'])
    member_nets = dict(contract['member_nets'])
    removed = Counter()
    for row in removed_rows:
        digest = _digest(row)
        if members[digest]:
            members[digest] -= 1
            removed[row[1]] += 1
    additions = Counter()
    for row in replacement_rows:
        digest = _digest(row)
        members[digest] += 1
        member_nets[digest] = row[1]
        additions[row[1]] += 1
    members = +members
    by_net = Counter()
    for digest, count in members.items():
        by_net[member_nets[digest]] += count
    nets = sorted(set(contract['nets']) | set(additions))
    contract.update(nets=nets, items=sum(members.values()),
        items_by_net={net: by_net[net] for net in nets},
        members=dict(sorted(members.items())),
        member_nets={digest: member_nets[digest] for digest in sorted(members)},
        retention_only=True, grants_local_copper_ownership=False)
    return contract, dict(retired_original_locked_members=sum(removed.values()),
        retired_original_locked_by_net=dict(sorted(removed.items())),
        retained_original_locked_members=frozen['items'] - sum(removed.values()),
        obligatory_replacement_members=len(replacement_rows),
        obligatory_replacement_by_net=dict(sorted(additions.items())),
        retired_track_uuids=sorted(retired), added_track_uuids=sorted(added),
        grants_routing_or_current_authority=False)


def receive(source, candidate, *, board_hint, phases, timeout_s=10., per_phase_leases=False):
    """Independently retype exact leading repairs, then retain their result.

    Empty phases perform literal retention only. Explicit per-phase leases
    compose existing <=10 second checks; they never enlarge a constituent's
    deadline. No caller contract, permission list or success receipt is input.
    """
    started = time.monotonic()
    result = dict(schema=1, scope='typed_current_reconstruction_and_protected_retention',
        ok=False, complete=False, errors=[], routing_admitted=False,
        current_authority=False, current_qualified=False,
        full_kelvin_qualification=False, release_authority=False,
        all_other_saved_board_receiving_still_required=True)
    try:
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10 or type(per_phase_leases) is not bool
                or type(board_hint) is not str or not board_hint):
            raise ValueError('bounded_identity_bound_retention_receiving_required')
        source, candidate = [_saved(p) for p in (source, candidate)]
        rows = _phases(phases)
        prefix_paths = [source, *[r['candidate'] for r in rows]]
        if (len(set(prefix_paths)) != len(prefix_paths)
                or rows and candidate in prefix_paths[:-1]):
            raise ValueError('current_reconstruction_cannot_revisit_an_earlier_parent')
        paths = list(dict.fromkeys([*prefix_paths, candidate]))
        families = [force._family(p, board_hint) for p in paths]
        epoch = force._code_identity()
        frozen = protected.capture(source, include_local_authority=False)
        literal = fr.check_copper_geometry_prefix(str(candidate), frozen)
        result.update(source=str(source), source_sha256=force._hash(source),
            candidate=str(candidate), candidate_sha256=force._hash(candidate),
            literal_original_prefix=literal, per_phase_leases=per_phase_leases,
            independent_stage_max_seconds=timeout_s,
            total_work_bound_seconds=timeout_s * (len(rows) + 3 if per_phase_leases else 1))
        if time.monotonic() - started >= timeout_s:
            raise ValueError('protected_current_initial_binding_deadline')
        contract = frozen
        if rows:
            remaining = timeout_s if per_phase_leases else timeout_s - (time.monotonic() - started)
            typed = chain.receive(source, rows[-1]['candidate'], board_hint=board_hint,
                phases=[{k: str(v) if k == 'candidate' else v for k, v in row.items()
                    if k != 'candidate_sha256'} for row in rows],
                timeout_s=remaining, per_phase_leases=per_phase_leases)
            result['independent_full_current_chain'] = typed
            if typed.get('ok') is not True or typed.get('complete') is not True:
                raise ValueError('fresh_independent_whole_current_reconstruction_refused')
            final_stage = time.monotonic()
            contract, manifest = _reconstruct(source, rows[-1]['candidate'], frozen, typed)
            result['native_reconstruction_manifest'] = manifest
            result['received_reconstruction_prefix'] = fr.check_copper_geometry_prefix(
                str(rows[-1]['candidate']), contract)
            if result['received_reconstruction_prefix']['ok'] is not True:
                raise ValueError('received_current_reconstruction_lost_untouched_prefix')
        else:
            final_stage = started
        result['source_copper'] = fr.check_copper_geometry_prefix(str(candidate), contract)
        result['qualified_pairs'] = protected.check_qualified_pairs(candidate, frozen)
        if result['source_copper']['ok'] is not True or result['qualified_pairs']['ok'] is not True:
            raise ValueError('final_saved_candidate_lost_obligatory_copper_or_qualified_pair')
        if (families != [force._family(p, board_hint) for p in paths]
                or epoch != force._code_identity()
                or any(force._hash(r['candidate']) != r['candidate_sha256'] for r in rows)):
            raise ValueError('protected_current_source_phase_candidate_or_code_changed')
        elapsed = time.monotonic() - started
        if (time.monotonic() - final_stage >= timeout_s
                or elapsed >= result['total_work_bound_seconds']):
            raise ValueError('protected_current_final_binding_deadline')
        result.update(ok=True, complete=True, source_candidate_and_code_unchanged=True,
            untouched_source_members_exact=True, replacements_are_retention_obligations=True,
            elapsed_s=elapsed)
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
        result['elapsed_s'] = time.monotonic() - started
    return result
