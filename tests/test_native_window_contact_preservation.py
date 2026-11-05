"""Native-seeded public contact comparator controls; no saved scope supplied.

The seed is real native force/sense evidence. Synthetic metadata below tests
the pure whitelist only; the public saved-window/replay owns its provenance.
"""
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import cec_native_window_contact_preservation as prototype
from test_kelvin_scope_admission import receipts

ZONE = {'uuid': 'synthetic-window-zone', 'net': 'RENAMED_FEED', 'layer': 0}


@pytest.fixture(scope='module')
def seed(tmp_path_factory):
    before, _ = receipts(tmp_path_factory.mktemp('private-window-comparison'))
    native = before['clipped_isolation']['details'][0]['native']
    native['exact_linear_refinements'].append(dict(kind='filled_zone_integer_axis_bounds', applied=True,
        identity=dict(kind='ZONE', uuid=ZONE['uuid'], net=ZONE['net']), layer=0,
        bounds_nm=[0, 0, 100, 100], geometry_sha256='a'*64,
        native_filled_polygon_sha256='b'*64, provenance='synthetic_whitelist_fixture'))
    for witness in native['baseline_geometry']['witnesses']:
        witness['path'][0]['contributors'].append(dict(kind='ZONE', uuid=ZONE['uuid'], net=ZONE['net']))
    assert prototype.sense.admit_changed_net(before, before, ZONE['net'])['ok']
    return before


@pytest.fixture
def pair(seed):
    before, after = copy.deepcopy(seed), copy.deepcopy(seed)
    native = after['clipped_isolation']['details'][0]['native']
    native['exact_linear_refinements'][-1].update(geometry_sha256='c'*64, native_filled_polygon_sha256='d'*64)
    for witness in native['baseline_geometry']['witnesses']:
        witness['path'][0]['component'] = 'native-copper-0-' + 'e'*64
    return before, after


def compare(pair, faces=None, modified=None):
    return prototype._compare_known_window_legs(*pair,
        [copy.deepcopy(ZONE)] if faces is None else faces,
        [ZONE['net']] if modified is None else modified, [])


def refused(pair, faces=None, modified=None):
    try:
        result = compare(pair, faces, modified)
    except (AssertionError, KeyError, TypeError, ValueError):
        return
    assert not result['same_evidence'], result
    strict = result['strict_unaffected_preservation']
    assert strict.get('reason') or strict.get('errors') or strict.get('preservation'), result


def test_positive_exact_zone_hash_and_baseline_token_only(pair):
    frozen = copy.deepcopy(pair)
    result = compare(pair)
    assert result['same_evidence'] and result['comparison_complete'], result
    assert len(result['independent_absolute_known_legs']) == 1
    assert result['independent_absolute_known_legs'][0]['independent_absolute_before']['ok']
    assert not result['release_authority'] and not result['current_qualification']
    assert pair == frozen


@pytest.mark.parametrize('mutation', ['numerical_guard_nm', 'approximation_error_nm', 'runtime',
    'model', 'source', 'sense', 'authority', 'tracks_clipped', 'complete',
    'exact_linear_identity_verified', 'row_status', 'source_pad', 'input_matrix',
    'missing_demand', 'duplicate_demand', 'coverage', 'geometry_policy', 'lineage'])
def test_safety_contracts_refuse(pair, mutation):
    after = pair[1]
    row = after['clipped_isolation']['details'][0]
    native = row['native']
    if mutation in ('numerical_guard_nm', 'approximation_error_nm'): native[mutation] += 1
    elif mutation == 'runtime': native['runtime']['kicad'] += '-forged'
    elif mutation == 'model': native['new_model_permission'] = True
    elif mutation in ('source', 'sense'): native[mutation]['uuid'] = 'forged'
    elif mutation == 'authority': native['authority'][0]['uuid'] = 'forged'
    elif mutation in ('tracks_clipped', 'complete', 'exact_linear_identity_verified'): native[mutation] = False
    elif mutation == 'row_status': row['status'] = 'unknown'
    elif mutation == 'source_pad': row['source_pad']['uuid'] = 'forged'
    elif mutation == 'input_matrix': after['same_net_connectivity']['details'][0]['ok'] = False
    elif mutation == 'missing_demand': after['same_net_connectivity']['details'].pop(0)
    elif mutation == 'duplicate_demand': after['same_net_connectivity']['details'].append(copy.deepcopy(after['same_net_connectivity']['details'][0]))
    elif mutation == 'coverage': after['clipped_isolation']['expected'] += 1
    elif mutation == 'geometry_policy': after['geometry_policy']['forged'] = True
    elif mutation == 'lineage': after['lineage']['resolved'] = 0
    refused(pair)


@pytest.mark.parametrize('side', [0, 1])
@pytest.mark.parametrize('kind', ['cut', 'inner'])
def test_absolute_before_and_after_mandatory(pair, side, kind):
    report = pair[side]
    if kind == 'cut':
        report['clipped_isolation']['details'][0]['native']['ok'] = False
    else:
        report['inner_departure']['details'][0]['ok'] = False
    refused(pair)


@pytest.mark.parametrize('mutation', ['wrong_uuid', 'wrong_net', 'wrong_face', 'bool_face',
    'duplicate', 'empty', 'extra', 'not_modified', 'whole_foreign_net_only'])
def test_exact_fresh_face_inventory_shape(pair, mutation):
    faces = [copy.deepcopy(ZONE)]
    modified = [ZONE['net']]
    if mutation == 'wrong_uuid': faces[0]['uuid'] = 'not-owned'
    elif mutation == 'wrong_net': faces[0]['net'] = 'other'
    elif mutation == 'wrong_face': faces[0]['layer'] = 2
    elif mutation == 'bool_face': faces[0]['layer'] = False
    elif mutation == 'duplicate': faces *= 2
    elif mutation == 'empty': faces = []
    elif mutation == 'extra': faces[0]['caller_allowed'] = True
    elif mutation == 'not_modified': modified = ['other']
    elif mutation == 'whole_foreign_net_only': faces = [{'net': ZONE['net']}]
    refused(pair, faces, modified)


@pytest.mark.parametrize('mutation', ['zone_bounds', 'zone_kind', 'zone_hash', 'zone_extra',
    'path_bounds_with_token', 'path_via_with_token', 'path_contributors_with_token',
    'component_without_changed_zone', 'component_wrong_layer'])
def test_whitelist_structure_refuses(pair, mutation):
    old = pair[0]['clipped_isolation']['details'][0]['native']
    native = pair[1]['clipped_isolation']['details'][0]['native']
    refinement = native['exact_linear_refinements'][-1]
    node = native['baseline_geometry']['witnesses'][0]['path'][0]
    if mutation == 'zone_bounds': refinement['bounds_nm'][0] += 1
    elif mutation == 'zone_kind': refinement['kind'] = 'other'
    elif mutation == 'zone_hash': refinement['geometry_sha256'] = 'not-sha'
    elif mutation == 'zone_extra': refinement['caller_permission'] = True
    elif mutation == 'path_bounds_with_token': node['bounds_nm'][0] += 1
    elif mutation == 'path_via_with_token': node['via'] = 'new-via'
    elif mutation == 'path_contributors_with_token': node['contributors'].pop()
    elif mutation == 'component_without_changed_zone': native['exact_linear_refinements'] = copy.deepcopy(old['exact_linear_refinements'])
    elif mutation == 'component_wrong_layer': node['component'] = 'native-copper-2-' + 'e'*64
    refused(pair)


@pytest.mark.parametrize('mutation', ['upper', 'lower', 'baseline_components',
    'baseline_bounds_unchanged_token', 'baseline_witness_authority', 'contacts_examined',
    'other_known_leg', 'extra_baseline_metadata'])
def test_no_broad_geometry_rebinding_for_all_known_net(pair, mutation):
    native = pair[1]['clipped_isolation']['details'][0]['native']
    if mutation in ('upper', 'lower'): native[mutation]['components'] += 1
    elif mutation == 'baseline_components': native['baseline_geometry']['components'] += 1
    elif mutation == 'baseline_bounds_unchanged_token':
        oldnode = pair[0]['clipped_isolation']['details'][0]['native']['baseline_geometry']['witnesses'][0]['path'][0]
        node = native['baseline_geometry']['witnesses'][0]['path'][0]
        node['component'] = oldnode['component']
        node['bounds_nm'][0] += 1
    elif mutation == 'baseline_witness_authority': native['baseline_geometry']['witnesses'][0]['authority']['uuid'] = 'forged'
    elif mutation == 'contacts_examined': native['contacts_examined'] += 1
    elif mutation == 'other_known_leg': pair[1]['clipped_isolation']['details'][1]['native']['upper']['components'] += 1
    elif mutation == 'extra_baseline_metadata': native['baseline_geometry']['new_property'] = 'unapproved'
    refused(pair)


def unknown_pair(seed):
    before = copy.deepcopy(seed)
    row = before['clipped_isolation']['details'][0]
    row.update(ok=None, status='unknown')
    row['native'].update(ok=None, complete=False, reason='synthetic_unobserved_cut')
    before['clipped_isolation']['passed'] -= 1
    before['clipped_isolation']['unknown'] += 1
    return before, copy.deepcopy(before)


def test_unchanged_unknown_is_preserved_not_qualified(seed):
    reports = unknown_pair(seed)
    result = compare(reports)
    assert result['same_evidence'] and result['comparison_complete'], result
    assert result['independent_absolute_known_legs'] == []
    assert result['existing_unknowns_not_qualified']
    assert reports[1]['clipped_isolation']['details'][0]['ok'] is None


@pytest.mark.parametrize('mutation', ['unknown_promoted', 'unknown_native_change', 'other_leg', 'coverage'])
def test_unknown_and_sibling_evidence_stays_strict(seed, mutation):
    reports = unknown_pair(seed)
    after = reports[1]
    unknown = after['clipped_isolation']['details'][0]
    if mutation == 'unknown_promoted': unknown.update(ok=True, status='verified')
    elif mutation == 'unknown_native_change': unknown['native']['reason'] += '-forged'
    elif mutation == 'other_leg': after['clipped_isolation']['details'][1]['native']['numerical_guard_nm'] += 1
    elif mutation == 'coverage': after['clipped_isolation']['unknown'] -= 1
    refused(reports)


@pytest.fixture(scope='module')
def native_window(tmp_path_factory):
    from test_ground_via_clearance_window_purpose import local_saved
    return local_saved(tmp_path_factory.mktemp('public-contact-local-window'))


def receive_native(native_window, **options):
    source, child, args, _, _ = native_window
    # Explicit synthetic catalog: this fixture has no current/sense devices.
    # Both public native audits execute; neither saved receiver is mocked.
    with patch('cec_current_topology.board_current_domains', return_value={}):
        return prototype.receive(source, child, operation='ground_local_return', **args, **options)


def test_public_saved_local_ground_window_replays_fresh(native_window):
    source, child, args, proposal, foreign = native_window
    raw = (source.read_bytes(), child.read_bytes())
    result = receive_native(native_window)
    assert result['ok'] and result['complete'] and result['same_evidence'], result
    assert result['independently_received_saved_window']['purpose'] == 'local_return_completion'
    assert result['actual_foreign_zone_faces'] == [dict(uuid=foreign,
        net='obstruction', layer=proposal['foreign_zones'][0]['faces'][0]['layer'])]
    assert len(result['raw_native_evidence']) == 2
    assert all(row['complete'] and row['identity_stable'] for row in result['raw_native_evidence'])
    assert result['Source_candidate_families_and_code_unchanged']
    assert result['all_original_parent_gates_still_required']
    assert not result['release_authority'] and not result['current_capacity_qualified']
    assert raw == (source.read_bytes(), child.read_bytes())


@pytest.mark.parametrize('operation', [None, False, True, 0, '', 'local_return_completion', 'Ground_local_return', 'quiet_signal'])
def test_public_operation_never_accepts_role_alias_or_bool(tmp_path, operation):
    result = prototype.receive(tmp_path/'missing', tmp_path/'other', board_hint='synthetic',
        pad_uuid='untrusted', operation=operation)
    assert not result['ok'] and not result['complete']
    assert any('explicit_Source_window_contact_operation_required' in e for e in result['errors']), result


@pytest.mark.parametrize('limit', [False, True, 0, -1, 10.001, float('nan'), float('inf'), '10'])
def test_public_deadline_cannot_be_disabled_or_enlarged(tmp_path, limit):
    result = prototype.receive(tmp_path/'missing', tmp_path/'other', board_hint='synthetic',
        pad_uuid='untrusted', operation='ground_local_return', timeout_s=limit)
    assert not result['ok'] and not result['complete']
    assert any('bounded_10s_window_contact_constituents_required' in e for e in result['errors']), result


@pytest.mark.parametrize('operation,position', [('ground_local_return',[0,0]),
    ('ground_island_join',[0,0]), ('ordinary_signal',None), ('ordinary_signal',[True,0]),
    ('ordinary_signal',(0,0)), ('ordinary_signal',[2000000001,0])])
def test_public_process_axis_schema_is_operation_specific(tmp_path, operation, position):
    result = prototype.receive(tmp_path/'missing', tmp_path/'other', board_hint='synthetic',
        pad_uuid='untrusted', operation=operation, position_nm=position)
    assert not result['ok'] and not result['complete'] and result['errors'], result


def test_public_island_mode_cannot_adopt_local_return_progress(native_window):
    source, child, args, _, _ = native_window
    result = prototype.receive(source, child, operation='ground_island_join', **args)
    assert not result['ok'] and not result['complete'], result
    assert any('exact_saved_Source_window_receiving_required' in e for e in result['errors'])
    assert 'actual_Source_contact_cut' not in result['timings_s']


def test_public_ordinary_operation_cannot_adopt_ground_pad(native_window):
    source, child, args, proposal, _ = native_window
    result = prototype.receive(source, child, operation='ordinary_signal',
        position_nm=proposal['at_nm'], **args)
    assert not result['ok'] and not result['complete'] and result['errors'], result
    assert 'actual_Source_contact_cut' not in result['timings_s']


def test_public_saved_source_and_child_must_be_distinct(native_window):
    source, _, args, _, _ = native_window
    result = prototype.receive(source, source, operation='ground_local_return', **args)
    assert not result['ok'] and not result['complete'], result
    assert any('distinct_saved_Source_window_contact_endpoints_required' in e for e in result['errors'])


@pytest.mark.parametrize('identity', ['code', 'family'])
def test_public_final_live_source_barrier_is_mandatory(native_window, monkeypatch, identity):
    if identity == 'code':
        real = prototype.force._code_identity
        count = [0]
        def drift():
            value = real()
            count[0] += 1
            # Introduce drift only after real saved receiving and both audits.
            if any(frame.function == 'receive' and frame.filename == prototype.__file__
                   and 'comparison' in frame.frame.f_locals for frame in __import__('inspect').stack()):
                return dict(value, injected_test_only='changed')
            return value
        monkeypatch.setattr(prototype.force, '_code_identity', drift)
    else:
        real = prototype.force._family
        def drift(*args, **kwargs):
            value = real(*args, **kwargs)
            if any(frame.function == 'receive' and frame.filename == prototype.__file__
                   and 'comparison' in frame.frame.f_locals for frame in __import__('inspect').stack()):
                return dict(value, injected_test_only='changed')
            return value
        monkeypatch.setattr(prototype.force, '_family', drift)
    result = receive_native(native_window)
    assert not result['ok'] and not result['complete'], result
    assert any('Source_window_contact_family_or_code_changed' in e for e in result['errors'])


def test_public_over_budget_saved_stage_cannot_start_contact_audits(native_window, monkeypatch):
    real = prototype.ground_window.receive
    clock = [0.]
    def delayed(*args, **kwargs):
        value = real(*args, **kwargs)
        clock[0] = 11.
        return value
    monkeypatch.setattr(prototype, 'time', SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(prototype.ground_window, 'receive', delayed)
    result = receive_native(native_window)
    assert not result['ok'] and not result['complete'], result
    assert any('Source_window_contact_constituent_deadline:independent_saved_window' in e for e in result['errors'])
    assert 'actual_Source_contact_cut' not in result['timings_s']


def test_public_wrapper_cannot_accept_caller_scope(native_window):
    source, child, args, _, _ = native_window
    with pytest.raises(TypeError):
        prototype.receive(source, child, operation='ground_local_return',
            foreign_zone_faces=[dict(ZONE)], **args)


def test_public_final_identity_scan_is_also_bounded(native_window, monkeypatch):
    real_family = prototype.force._family
    clock = [0.]
    def final_slow_family(*args, **kwargs):
        value = real_family(*args, **kwargs)
        if any(frame.function == 'receive' and frame.filename == prototype.__file__
               and 'comparison' in frame.frame.f_locals for frame in __import__('inspect').stack()):
            clock[0] = 11.
        return value
    monkeypatch.setattr(prototype.force, '_family', final_slow_family)
    monkeypatch.setattr(prototype, 'time', SimpleNamespace(monotonic=lambda:clock[0]))
    result = receive_native(native_window)
    assert clock[0] == 11.
    assert not result['ok'] and not result['complete'], result
    assert any('deadline' in e for e in result['errors']), result
