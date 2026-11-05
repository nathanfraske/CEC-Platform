"""Early craft cannot pass a demand the actual tap constructor cannot reach."""
import copy
from pathlib import Path

import pytest

import cec_terminal_range as reach
import cec_synth_pipeline as synth
from test_terminal_pin_contract import fixture, evidence
from test_terminal_range import native_fixture


@pytest.mark.parametrize('angle', [0, 90, 180, 270, 31])
@pytest.mark.parametrize('reflected', [False, True])
def test_long_actual_inputs_fail_before_route_and_unknown_nearby_pad_does_not_hide_them(angle, reflected):
    data = fixture(offset=(127, -51), angle=angle, reflected=reflected)
    owner = data[-2]
    x, y, rotation = data[2][owner]
    data[2][owner] = (x+30, y+30, rotation)
    result = evidence(data)
    assert not result['ok'] and result['crossing_count'] == 0
    assert result['range_violation_count'] == 2
    assert {row['target_pad'] for row in result['range_refusals']} == {'9', '10'}
    assert all(row['required_closer_mm'] > 0 for row in result['range_refusals'])
    certificate = synth.placement_craft_blocker_certificate({'critical_terminal_order': result})
    assert 'critical_terminal_order' in certificate['required_stages']


def test_healthy_range_unchanged_and_unknown_or_filtered_not_qualified_by_new_gate():
    assert evidence(fixture())['range_violation_count'] == 0
    data = fixture(value='UNKNOWN_MONITOR')
    owner = data[-2]
    data[2][owner] = (90, 90, 0)
    result = evidence(data)
    assert result['range_evidence']['checked'] == 0
    filtered = dict(result['details'][0], relation_kind='filtered',
                    follower_pad_contract={'one': '1', 'two': '2'})
    assert reach.direct_range_evidence([filtered])['skipped_relations'] == 1


@pytest.mark.parametrize('maximum', [0, -1, float('nan'), float('inf')])
def test_invalid_range_never_disables_check(maximum):
    with pytest.raises(ValueError): reach.direct_range_evidence([], max_distance_mm=maximum)


def test_incomplete_known_input_geometry_is_not_a_pass():
    row = evidence(fixture())['details'][0]
    row['terminal_correspondences'].pop()
    with pytest.raises(ValueError, match='complete actual'):
        reach.direct_range_evidence([row])


def bound_craft(source, candidate, rows, details):
    import cec_placement_evidence_identity as identity
    return dict(input_identity=dict(files=dict(board=dict(path=str(source), sha256=identity.digest(source)))),
                critical_terminal_order=dict(range_refusals=rows, details=details),
                decoupler=dict(details=[dict(status='assigned', owner_ref='owner', cap_ref='bypass')]))


@pytest.mark.parametrize('flipped', [False, True])
def test_same_native_solver_dispatched_in_early_craft_with_complete_bypass_cell(tmp_path, flipped):
    source, board, candidate, rows, details = native_fixture(tmp_path, flipped)
    craft = bound_craft(source, candidate, rows, details)
    before = source.read_bytes()
    diagnostic = {}
    proposals = synth._placement_craft_move_specs(candidate, craft,
        required_stages=['critical_terminal_order'], proposal_diagnostics=diagnostic)
    selected = [row for row in proposals if row['kind'] == 'terminal_range_order_closure']
    assert selected and diagnostic['terminal_range']['proposals'] == len(selected)
    assert all(set(row['placements']) == {'owner', 'bypass'} for row in selected)
    assert all(max(row['terminal_distances_mm']) <= 8.7+1e-8 for row in selected)
    assert source.read_bytes() == before


@pytest.mark.parametrize('fault', ['no_identity', 'mutated_source', 'changed_during_measurement', 'fixed_bypass'])
def test_stale_or_ineligible_craft_does_not_generate_placement_authority(tmp_path, fault):
    source, board, candidate, rows, details = native_fixture(tmp_path)
    craft = bound_craft(source, candidate, rows, details)
    fixed = []
    if fault == 'no_identity': craft.pop('input_identity')
    elif fault == 'mutated_source': source.write_bytes(source.read_bytes()+b'\n')
    elif fault == 'changed_during_measurement': craft['input_identity_after'] = {'changed': True}
    else: fixed = ['bypass']
    assert reach.from_craft_evidence(candidate, craft, immutable=fixed) == []


def test_tap_construction_and_early_geometry_share_unchanged_limit():
    import inspect
    import cec_fr
    assert reach.MAX_TAP_DISTANCE_MM == 9.
    assert inspect.signature(cec_fr.synthesize_kelvin_taps).parameters['max_ic_mm'].default == reach.MAX_TAP_DISTANCE_MM


def test_early_proposal_quota_reaches_each_owner_before_second_variant(tmp_path, monkeypatch):
    # Stub the already-tested geometry solver to test scheduling alone.
    source, board, candidate, rows, details = native_fixture(tmp_path)
    craft = bound_craft(source, candidate, rows, details)
    proposals = [dict(ref=owner, variant=index)
                 for owner in ('cell-z', 'cell-a', 'cell-q') for index in range(4)]
    monkeypatch.setattr(reach, 'from_native_relations', lambda *a, **k: proposals)
    selected = reach.from_craft_evidence(candidate, craft)
    assert [(row['ref'], row['variant']) for row in selected[:6]] == [
        ('cell-z', 0), ('cell-a', 0), ('cell-q', 0),
        ('cell-z', 1), ('cell-a', 1), ('cell-q', 1)]
