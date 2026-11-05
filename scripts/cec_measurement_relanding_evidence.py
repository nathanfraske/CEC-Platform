"""Fresh absolute known-cut receiving for a stationary inward leaf re-landing.

The public entry point derives the exact Source cut, same physical shunt and
input from the saved native re-landing receiver. Both original and replacement
legs must independently pass absolute clipped-cut admission. Only that one
owned departure, its positively identified observation at still-unconnected
peers, and its requalified geometric cut witness may differ. Unknown/failing
peer coverage, other paths, physical authority, guards and models stay strict.

Raw reports are retained, never edited or asserted equal. This operation
grants neither full Kelvin/current qualification nor release authority.
"""
import copy
import math
from pathlib import Path
import time

import pcbnew
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_measurement_leaf_relanding as reland


def _rows(report, category):
    rows = report[category]['details']
    keys = [(row['input_ref'], row['leg'], row['net']) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError('unique_relanding_physical_leg_inventory_required')
    return {key: (index, row) for index, (key, row) in enumerate(zip(keys, rows))}


def _witness(departure, owned, root):
    paths = departure.get('input_contact_paths')
    if (type(paths) is not dict or set(paths) != {root}
            or departure.get('reachable_input_pad_uuids') != [root]):
        raise ValueError('one_actual_relanding_input_contact_witness_required')
    path = paths[root]
    if (type(path) is not list or not 2 <= len(path) <= 17 or path[-1] != root
            or len(set(path)) != len(path) or path[0] != departure.get('uuid')
            or path[:-1] != list(reversed(owned))[:len(path)-1]):
        raise ValueError('relanding_witness_may_use_only_ordered_Source_owned_leaf')


def _compare(before, after, saved, transforms):
    """Private comparison; saved is produced afresh inside public receive()."""
    for report in (before, after):
        own = sense.compare_contact_preservation(report, report)
        if own['comparison_complete'] is not True or own['same_evidence'] is not True:
            raise ValueError('complete_bound_absolute_relanding_reports_required')
    if before['geometry_policy'] != after['geometry_policy']:
        raise ValueError('relanding_geometry_policy_changed')
    proposal = saved['source_scope']
    original, replacement = proposal['source_leaf'], saved['new_leaf']
    demand = proposal['demand']
    key = (original['owner'], demand['source_segment']['leg'], demand['net'])
    root, target = demand['pad_uuid'], demand['target_uuid']
    for category in ('inner_departure', 'clipped_isolation'):
        if _rows(before, category).keys() != _rows(after, category).keys():
            raise ValueError('relanding_changed_physical_leg_inventory')
    first_index, first = _rows(before, 'inner_departure')[key]
    last_index, last = _rows(after, 'inner_departure')[key]
    if ({k:v for k,v in first.items() if k != 'native'}
            != {k:v for k,v in last.items() if k != 'native'}
            or first.get('ok') is not True or last.get('ok') is not True
            or first['source_pad']['uuid'] != target
            or first['sense_terminal']['uuid'] != root):
        raise ValueError('same_positive_physical_relanding_terminals_required')
    old, new = first['native'], last['native']
    if (old.get('ok') is not True or new.get('ok') is not True
            or old.get('issues') or new.get('issues')
            or len(old.get('departures', [])) != 1 or len(new.get('departures', [])) != 1
            or {k:v for k,v in old.items() if k != 'departures'}
                != {k:v for k,v in new.items() if k != 'departures'}):
        raise ValueError('one_requalified_inward_departure_with_unchanged_contacts_required')
    left, right = old['departures'][0], new['departures'][0]
    if (left['uuid'] not in original['track_uuids']
            or right['uuid'] not in replacement['track_uuids']):
        raise ValueError('actual_Source_owned_departure_and_actual_new_leaf_required')
    _witness(left, original['track_uuids'], root)
    _witness(right, replacement['track_uuids'], root)
    geometry = {'uuid', 'contact_exit_mm', 'inner_projection_mm', 'departure_start_mm',
        'departure_end_mm', 'input_contact_paths', 'transverse_error_nm'}
    if ({k:v for k,v in left.items() if k not in geometry}
            != {k:v for k,v in right.items() if k not in geometry}):
        raise ValueError('relanding_input_face_direction_role_or_association_changed')
    absolute = []
    for current in (before, after):
        proof = sense.admit_changed_net(before, current, demand['net'], input_legs=[list(key[:2])])
        if (proof['ok'] is not True or proof['applicable'] is not True
                or proof['checked'] != 1 or proof['expected_legs'] != [list(key[:2])]):
            raise ValueError('both_original_and_replacement_absolute_clipped_cuts_required')
        absolute.append(proof)
    adjusted = copy.deepcopy(after)
    adjusted['inner_departure']['details'][last_index]['native']['departures'] = copy.deepcopy(old['departures'])
    observations = []
    original_peers = _rows(before, 'inner_departure')
    for index, peer in enumerate(after['inner_departure']['details']):
        peer_key = (peer['input_ref'], peer['leg'], peer['net'])
        if peer_key == key:
            continue
        prior = original_peers[peer_key][1]
        if prior == peer:
            continue
        a, b = prior.get('native'), peer.get('native')
        if (peer['net'] != demand['net'] or peer['source_pad']['uuid'] != target
                or not a or not b or prior.get('ok') is True or peer.get('ok') is True
                or {k:v for k,v in prior.items() if k != 'native'}
                    != {k:v for k,v in peer.items() if k != 'native'}
                or {k:v for k,v in a.items() if k != 'non_sense_departures'}
                    != {k:v for k,v in b.items() if k != 'non_sense_departures'}):
            # Nothing is ignored. The final strict comparator rejects any
            # unmatched difference in this or any unrelated physical leg.
            continue
        old_obs, new_obs = a.get('non_sense_departures', []), b.get('non_sense_departures', [])
        first_obs = [d for d in old_obs if d.get('uuid') == left['uuid']]
        last_obs = [d for d in new_obs if d.get('uuid') == right['uuid']]
        if len(first_obs) != 1 or len(last_obs) != 1:
            continue
        witness = {'reachable_input_pad_uuids', 'input_contact_paths'}
        if any(d.get('reachable_input_pad_uuids') != [] or d.get('input_contact_paths', {}) != {}
                for d in (first_obs[0], last_obs[0])):
            raise ValueError('unconnected_peer_must_not_acquire_a_measurement_path')
        if ( {k:v for k,v in first_obs[0].items() if k not in witness}
                != {k:v for k,v in left.items() if k not in witness}
                or {k:v for k,v in last_obs[0].items() if k not in witness}
                != {k:v for k,v in right.items() if k not in witness}):
            raise ValueError('peer_observation_does_not_match_actual_requalified_departure')
        remaining_old = [d for d in old_obs if d.get('uuid') != left['uuid']]
        remaining_new = [d for d in new_obs if d.get('uuid') != right['uuid']]
        if remaining_old != remaining_new or len(old_obs) != len(new_obs):
            raise ValueError('other_peer_departure_observations_changed')
        adjusted['inner_departure']['details'][index]['native']['non_sense_departures'] = copy.deepcopy(old_obs)
        observations.append(dict(input_ref=peer_key[0], leg=peer_key[1], net=peer_key[2],
            raw_after_ok=peer['ok'], raw_after_status=peer['status'],
            source_pad_uuid=target, actual_requalified_leaf_departure=right['uuid'],
            existing_unknown_or_failure_not_qualified=True))
    old_cut = _rows(before, 'clipped_isolation')[key][1]
    cut_index, new_cut = _rows(after, 'clipped_isolation')[key]
    if ({k:v for k,v in old_cut.items() if k != 'native'}
            != {k:v for k,v in new_cut.items() if k != 'native'}):
        raise ValueError('relanding_clipped_physical_scope_changed')
    geometry_fields = {'elapsed_s', 'vertices_examined', 'contacts_examined',
        'exact_linear_refinements', 'baseline_geometry', 'upper', 'lower'}
    if ({k:v for k,v in old_cut['native'].items() if k not in geometry_fields}
            != {k:v for k,v in new_cut['native'].items() if k not in geometry_fields}):
        raise ValueError('relanding_cut_model_or_guard_changed')
    adjusted['clipped_isolation']['details'][cut_index]['native'] = copy.deepcopy(old_cut['native'])
    strict = sense.compare_contact_preservation(before, adjusted, native_copper_transforms=transforms)
    return dict(comparison_complete=strict['comparison_complete'], same_evidence=strict['same_evidence'],
        strict_unaffected_preservation=strict, independently_absolute_before=absolute[0],
        independently_absolute_after=absolute[1], requalified_input_leg=list(key),
        unchanged_unknown_peer_observations=observations, raw_evidence_equal_claimed=False,
        raw_reports_not_modified=True, full_kelvin_qualification=False,
        current_authority=False, release_authority=False)


def receive(source, candidate, *, board_hint, pad_uuid, timeout_s=10.):
    """Finite ordered composition; each named native constituent <=10 s."""
    result = dict(ok=False, complete=False, comparison_complete=False, same_evidence=False,
        errors=[], scope='saved_inward_leaf_absolute_known_cut_preservation',
        raw_evidence_equal_claimed=False, full_kelvin_qualification=False,
        current_authority=False, release_authority=False, timings_s={})
    try:
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10.):
            raise ValueError('bounded_10s_relanding_contact_constituents_required')
        paths = [Path(v).resolve(strict=True) for v in (source, candidate)]
        if paths[0] == paths[1] or paths[0].samefile(paths[1]):
            raise ValueError('distinct_actual_saved_relanding_contact_endpoints_required')

        def step(name, callback):
            began = time.monotonic()
            value = callback()
            result['timings_s'][name] = time.monotonic()-began
            if result['timings_s'][name] >= timeout_s:
                raise ValueError('relanding_contact_constituent_deadline:'+name)
            return value

        code, families = step('initial_live_saved_guard', lambda: (
            force._code_identity(), [force._family(p, board_hint) for p in paths]))
        saved = step('independent_saved_relanding', lambda: reland.receive(*paths,
            board_hint=board_hint, pad_uuid=pad_uuid, timeout_s=timeout_s))
        result['independent_saved_relanding'] = saved
        if saved.get('ok') is not True or saved.get('complete') is not True:
            raise ValueError('fresh_actual_saved_relanding_scope_required')
        before = step('absolute_original_native_contacts', lambda: sense.replay(paths[0],
            board_hint=board_hint, timeout_s=timeout_s))
        after = step('absolute_replacement_native_contacts', lambda: sense.replay(paths[1],
            board_hint=board_hint, timeout_s=timeout_s))
        if any(v.get('complete') is not True or v.get('identity_stable') is not True
                for v in (before, after)):
            raise ValueError('complete_actual_relanding_contact_audits_required')
        boards = step('load_current_actual_boards', lambda: [pcbnew.LoadBoard(str(p)) for p in paths])
        transforms = step('actual_literal_native_delta', lambda:
            sense.native_copper_transform_inventory(*boards,
                modified_nets=[saved['source_scope']['demand']['net']]))
        comparison = step('absolute_known_and_strict_unaffected', lambda: _compare(before, after, saved, transforms))
        result['comparison'] = comparison
        stable = step('final_live_saved_guard', lambda: code == force._code_identity()
            and families == [force._family(p, board_hint) for p in paths])
        if not stable:
            raise ValueError('relanding_contact_saved_family_or_code_changed')
        result.update(comparison_complete=comparison['comparison_complete'],
            same_evidence=comparison['same_evidence'], complete=True,
            ok=comparison['comparison_complete'] is True and comparison['same_evidence'] is True,
            raw_native_evidence=[before, after], source=str(paths[0]), candidate=str(paths[1]),
            source_sha256=force._hash(paths[0]), candidate_sha256=force._hash(paths[1]),
            code_identity=code, Source_families_and_code_unchanged=True,
            full_original_parent_gates_still_required=True)
    except Exception as exc:
        result.update(ok=False, complete=False, comparison_complete=False, same_evidence=False)
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
