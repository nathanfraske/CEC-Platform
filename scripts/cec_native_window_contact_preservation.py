"""Independently revalidate known Kelvin cuts after exact local via windows.

Only the saved window receiver derives scope. Native Source/child audits
rebuild every actual conductor, fill and drill. A previously verified affected
leg owes absolute BEFORE and AFTER admission; unknown/failed peers remain
strict and never gain qualification. The narrow first tier permits only the
window zone/face's exact linear fingerprints and corresponding baseline-node
tokens, with identical paths, contributors, bounds, guards and model.

This is not a raw-evidence equality claim, current/thermal qualification or
fabrication permission. All original-parent gates remain mandatory.
"""
import copy
import math
from pathlib import Path
import time

import pcbnew
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_ground_via_clearance_window as ground_window
import cec_signal_via_clearance_window as signal_window


def _compare_known_window_legs(before, after, foreign_zone_faces, modified_nets, manifest):
    """Internal comparison only; the public receiver derives every scope from Source."""
    if not (type(foreign_zone_faces) is list and 1 <= len(foreign_zone_faces) <= 64):
        raise ValueError('checked_window_contact_whitelist_refused')
    if not all((type(v) is dict and set(v) == {'uuid', 'net', 'layer'} and (type(v['uuid']) is str) and v['uuid'] and (type(v['net']) is str) and v['net'] and (v['net'] != 'GND') and (type(v['layer']) is int) and (0 <= v['layer'] < 64) for v in foreign_zone_faces)):
        raise ValueError('checked_window_contact_whitelist_refused')
    zones = {(v['uuid'], v['net'], v['layer']) for v in foreign_zone_faces}
    if not len(zones) == len(foreign_zone_faces):
        raise ValueError('checked_window_contact_whitelist_refused')
    affected_nets = sorted({v['net'] for v in foreign_zone_faces})
    if not set(affected_nets) <= set(modified_nets):
        raise ValueError('checked_window_contact_whitelist_refused')
    for value in (before, after):
        check = sense.compare_contact_preservation(value, value)
        if not (check['same_evidence'] and check['comparison_complete']):
            raise ValueError('checked_window_contact_whitelist_refused')
    if not before['geometry_policy'] == after['geometry_policy']:
        raise ValueError('checked_window_contact_whitelist_refused')
    key = lambda row: (row['input_ref'], row['leg'], row['net'])
    old_rows = before['clipped_isolation']['details']
    new_rows = after['clipped_isolation']['details']
    prior = {key(v): v for v in old_rows}
    actual = {key(v): v for v in new_rows}
    if not (len(prior) == len(old_rows) and len(actual) == len(new_rows)):
        raise ValueError('checked_window_contact_whitelist_refused')
    if not prior.keys() == actual.keys():
        raise ValueError('checked_window_contact_whitelist_refused')
    candidates = sorted((k for k, row in prior.items() if k[2] in affected_nets and row.get('ok') is True and (row.get('status') == 'verified')))
    adjusted = copy.deepcopy(after)
    proof = []

    def sha(value):
        return type(value) is str and len(value) == 64 and all((c in '0123456789abcdef' for c in value))
    for selected in candidates:
        old, new = (prior[selected], actual[selected])
        if not {k: v for k, v in old.items() if k != 'native'} == {k: v for k, v in new.items() if k != 'native'}:
            raise ValueError('checked_window_contact_whitelist_refused')
        original_absolute = sense.admit_changed_net(before, before, selected[2], input_legs=[list(selected[:2])])
        if not (original_absolute['ok'] and original_absolute['applicable'] and (original_absolute['checked'] == 1) and (original_absolute['expected_legs'] == [list(selected[:2])])):
            raise ValueError(original_absolute)
        absolute = sense.admit_changed_net(before, after, selected[2], input_legs=[list(selected[:2])])
        if not (absolute['ok'] and absolute['applicable'] and (absolute['checked'] == 1) and (absolute['expected_legs'] == [list(selected[:2])])):
            raise ValueError(absolute)
        index = next((i for i, row in enumerate(new_rows) if key(row) == selected))
        patched = adjusted['clipped_isolation']['details'][index]['native']
        first, last = (old['native'], new['native'])
        refinements = (first['exact_linear_refinements'], last['exact_linear_refinements'])
        if not len(refinements[0]) == len(refinements[1]):
            raise ValueError('checked_window_contact_whitelist_refused')
        changed_zone_faces = set()
        for i, (left, right) in enumerate(zip(*refinements)):
            if left == right:
                continue
            identity = left.get('identity', {})
            selected_face = (identity.get('uuid'), identity.get('net'), left.get('layer'))
            if not (identity.get('kind') == 'ZONE' and selected_face in zones):
                raise ValueError('checked_window_contact_whitelist_refused')
            mutable = {'geometry_sha256', 'native_filled_polygon_sha256'}
            if not {k: v for k, v in left.items() if k not in mutable} == {k: v for k, v in right.items() if k not in mutable}:
                raise ValueError('checked_window_contact_whitelist_refused')
            if not all((sha(left[k]) and sha(right[k]) for k in mutable)):
                raise ValueError('checked_window_contact_whitelist_refused')
            if not (left['applied'] is True and right['applied'] is True):
                raise ValueError('checked_window_contact_whitelist_refused')
            if not left['kind'] == 'filled_zone_integer_axis_bounds':
                raise ValueError('checked_window_contact_whitelist_refused')
            for name in mutable:
                patched['exact_linear_refinements'][i][name] = left[name]
            changed_zone_faces.add(selected_face)
        models = (first['baseline_geometry'], last['baseline_geometry'])
        if not len(models[0]['witnesses']) == len(models[1]['witnesses']):
            raise ValueError('checked_window_contact_whitelist_refused')
        changed_components = []
        for wi, (left_witness, right_witness) in enumerate(zip(models[0]['witnesses'], models[1]['witnesses'])):
            if not len(left_witness['path']) == len(right_witness['path']):
                raise ValueError('checked_window_contact_whitelist_refused')
            for pi, (left, right) in enumerate(zip(left_witness['path'], right_witness['path'])):
                if left['component'] == right['component']:
                    continue
                if not {k: v for k, v in left.items() if k != 'component'} == {k: v for k, v in right.items() if k != 'component'}:
                    raise ValueError('checked_window_contact_whitelist_refused')
                matching = [z for z in changed_zone_faces if pcbnew.LayerName(z[2]) == left['layer'] and dict(kind='ZONE', uuid=z[0], net=z[1]) in left['contributors']]
                if not matching:
                    raise ValueError('component_change_has_no_exact_Source_window_zone_face')
                layer = matching[0][2]
                prefix = 'native-copper-' + str(layer) + '-'
                if not all((v.startswith(prefix) and sha(v[len(prefix):]) for v in (left['component'], right['component']))):
                    raise ValueError('checked_window_contact_whitelist_refused')
                patched['baseline_geometry']['witnesses'][wi]['path'][pi]['component'] = left['component']
                changed_components.append(dict(witness=wi, path=pi, zone_faces=sorted(matching)))
        proof.append(dict(leg=list(selected), independent_absolute_before=original_absolute, independent_absolute_after=absolute, previously_verified_not_newly_repaired=True, revalidated_zone_faces=sorted(changed_zone_faces), revalidated_baseline_components=changed_components))
    for field in ('expected', 'checked', 'passed', 'failed', 'unknown', 'unresolved_inputs'):
        if not before['clipped_isolation'][field] == after['clipped_isolation'][field]:
            raise ValueError('checked_window_contact_whitelist_refused')
    strict = sense.compare_contact_preservation(before, adjusted, native_copper_transforms=manifest)
    return dict(scope='checked_window_absolute_known_cut_revalidation', comparison_complete=strict['comparison_complete'], same_evidence=strict['same_evidence'], independent_absolute_known_legs=proof, strict_unaffected_preservation=strict, raw_evidence_equal_claimed=False, existing_unknowns_not_qualified=True, full_kelvin_qualification=False, current_qualification=False, release_authority=False)


def receive(source, candidate, *, board_hint, pad_uuid, operation,
            position_nm=None, timeout_s=10.):
    """A finite composition of independently bounded saved/native checks.

    No caller witness, net/leg allowlist, polygon, callback or time extension.
    Each constituent has the caller's limit, which may never exceed 10 s.
    """
    result = dict(ok=False, complete=False, comparison_complete=False,
        same_evidence=False, errors=[], release_authority=False,
        raw_evidence_equal_claimed=False, full_kelvin_qualification=False,
        current_capacity_qualified=False,
        all_original_parent_gates_still_required=True,
        scope='Source_checked_via_window_known_cut_preservation',
        timings_s={}, native_constituent_limit_s=timeout_s)
    try:
        if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10.):
            raise ValueError('bounded_10s_window_contact_constituents_required')
        if (type(operation) is not str or operation not in
                ('ground_island_join', 'ground_local_return', 'ordinary_signal')):
            raise ValueError('explicit_Source_window_contact_operation_required')
        if (type(board_hint) is not str or not board_hint or type(pad_uuid) is not str
                or not pad_uuid or operation != 'ordinary_signal' and position_nm is not None):
            raise ValueError('exact_Source_window_contact_identity_required')
        if operation == 'ordinary_signal' and (type(position_nm) is not list
                or len(position_nm) != 2 or any(type(v) is not int
                    or abs(v) > 2000000000 for v in position_nm)):
            raise ValueError('exact_integer_Source_signal_window_axis_required')
        paths = [Path(v).resolve(strict=True) for v in (source, candidate)]
        if paths[0] == paths[1] or paths[0].samefile(paths[1]):
            raise ValueError('distinct_saved_Source_window_contact_endpoints_required')
        def step(name, function):
            start = time.monotonic()
            value = function()
            elapsed = time.monotonic() - start
            result['timings_s'][name] = elapsed
            if elapsed >= timeout_s:
                raise ValueError('Source_window_contact_constituent_deadline:' + name)
            return value

        epoch, families = step('initial_saved_identity_guard', lambda: (
            force._code_identity(), [force._family(v, board_hint) for v in paths]))
        if operation == 'ordinary_signal':
            received = step('independent_saved_window', lambda: signal_window.receive(
                *paths, board_hint=board_hint, pad_uuid=pad_uuid,
                position_nm=position_nm, timeout_s=timeout_s))
        else:
            purpose = ('local_return_completion' if operation == 'ground_local_return'
                       else 'island_join')
            received = step('independent_saved_window', lambda: ground_window.receive(
                *paths, board_hint=board_hint, pad_uuid=pad_uuid,
                purpose=purpose, timeout_s=timeout_s))
        if received.get('ok') is not True or received.get('complete') is not True:
            raise ValueError('exact_saved_Source_window_receiving_required:' +
                             repr(received.get('errors')))
        fresh = received['plan']
        bound = step('fresh_window_saved_boundary', lambda: (
            fresh['source'] == str(paths[0]) and fresh['source_sha256'] == force._hash(paths[0])
            and fresh['board_hint'] == board_hint and fresh['pad_uuid'] == pad_uuid
            and received['candidate_sha256'] == force._hash(paths[1])))
        if not bound:
            raise ValueError('fresh_Source_window_contact_boundary_required')
        faces = [dict(uuid=z['uuid'], net=z['net'], layer=face['layer'])
            for z in fresh['foreign_zones'] for face in z['faces']]
        before = step('actual_Source_contact_cut', lambda: sense.replay(
            paths[0], board_hint=board_hint, timeout_s=timeout_s))
        after = step('actual_child_contact_cut', lambda: sense.replay(
            paths[1], board_hint=board_hint, timeout_s=timeout_s))
        if any(v.get('complete') is not True or v.get('identity_stable') is not True
               for v in (before, after)):
            raise ValueError('complete_bound_actual_window_contact_audits_required')
        # The saved window receiver has already proved exact literal material
        # ownership and old partitions. It adds only its one new Ground or
        # ordinary via. Foreign force/sense objects retain exact identities.
        # Derive identity deltas from the actual saved boards nevertheless.
        boards = step('load_actual_endpoints', lambda: [
            pcbnew.LoadBoard(str(v)) for v in paths])
        import cec_field_coupling as field
        def changed():
            prior, child = [field._field_snapshot_inventory(v) for v in boards]
            nets = set()
            for key in prior.keys() | child.keys():
                if prior.get(key) == child.get(key):
                    continue
                for row in (prior.get(key), child.get(key)):
                    if row is not None:
                        net = row[1] if key[0] == 'track' else row[0]
                        if type(net) is not str or not net:
                            raise ValueError('changed_window_material_without_positive_net')
                        nets.add(net)
            if len(nets) > 64:
                raise ValueError('bounded_actual_window_modified_nets_required')
            return sorted(nets)
        modified = step('actual_modified_nets', changed)
        manifest = step('actual_native_identity_delta', lambda:
            sense.native_copper_transform_inventory(*boards, modified_nets=modified))
        comparison = step('absolute_known_and_strict_unaffected', lambda:
            _compare_known_window_legs(before, after, faces, modified, manifest))
        stable = step('final_saved_identity_guard', lambda: (
            epoch == force._code_identity()
            and families == [force._family(v, board_hint) for v in paths]))
        if not stable:
            raise ValueError('Source_window_contact_family_or_code_changed')
        result.update(complete=True, comparison_complete=comparison['comparison_complete'],
            same_evidence=comparison['same_evidence'],
            ok=comparison['comparison_complete'] and comparison['same_evidence'],
            independently_received_saved_window=received,
            independently_revalidated_known_cuts=comparison,
            raw_native_evidence=[before, after], actual_foreign_zone_faces=faces,
            actual_modified_nets=modified, actual_native_identity_transforms=manifest,
            Source_candidate_families_and_code_unchanged=True)
    except Exception as exc:
        result.update(ok=False, complete=False, comparison_complete=False, same_evidence=False)
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result
