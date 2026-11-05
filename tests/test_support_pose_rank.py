"""Placement ordering is generic, immutable and never acceptance authority."""
from copy import deepcopy
import pytest

import cec_support_pose_rank as ranking


def detail():
    return dict(cap_ref='BYPASS', owner_ref='OWNER', owner_pin='7', rail='/RAIL',
        status='assigned', return_gate_mode='absolute_ground_distance',
        owner_supply_position_mm=[0., 0.], cap_supply_position_mm=[1., 0.],
        owner_ground_position_mm=[0., 1.], cap_ground_position_mm=[1., 1.],
        owner_ground_positions_mm=[dict(pin='8', position=[0., 1.])],
        ground_distance_mm=1., return_limit_mm=2.5, supply_excess_limit_mm=.25,
        tangent_target=dict(best_loop=dict(supply_mm=1., loop_proxy_mm=2.)))


def pose(dx, dy=0, **kwargs):
    return dict(dx_mm=dx, dy_mm=dy, rotation_delta_deg=0, **kwargs)


@pytest.mark.parametrize('offset,mirror,rotate', [((0, 0), 1, False),
    ((31, -47), -1, False), ((-83, 12), 1, True)])
def test_native_coordinates_are_invariant_to_translation_rotation_and_backside(offset, mirror, rotate):
    row = detail()
    def vector(p):
        x, y = p[0] * mirror, p[1]
        return [-y, x] if rotate else [x, y]
    def point(p):
        v = vector(p)
        return [v[0] + offset[0], v[1] + offset[1]]
    for key in ('owner_supply_position_mm', 'cap_supply_position_mm',
                'owner_ground_position_mm', 'cap_ground_position_mm'):
        row[key] = point(row[key])
    row['owner_ground_positions_mm'][0]['position'] = point([0, 1])
    row.update(cap_ref='RENAMED_CAP', owner_ref='OTHER_OWNER')
    target = dict(ref='RENAMED_CAP', companion_refs=[])
    bad = vector([.5, 0]); good = vector([-.1, 0])
    menu = [pose(*bad), pose(*good)]
    original = deepcopy((row, target, menu))
    result = ranking.rank([row], target, menu)
    assert [c['electrical_pose_rank']['status'] for c in result['candidates']] == ['nonregressing', 'regressed']
    assert result['reordered'] and result['candidate_count'] == 2
    assert not result['release_authority'] and not result['admission_authority']
    assert (row, target, menu) == original


def test_explicit_stationary_companion_differs_from_inherited_rigid_cell():
    row = detail()
    target = dict(ref='OWNER', companion_refs=['BYPASS'])
    assert ranking.predict([row], target, pose(-.75))['status'] == 'nonregressing'
    prediction = ranking.predict([row], target, pose(-.75, mobility_companion_refs=[]))
    assert prediction['status'] == 'regressed'
    assert not prediction['admission_authority']


def test_nearest_ground_is_reselected_after_translation():
    row = detail()
    row['owner_ground_positions_mm'].append(dict(pin='9', position=[2., 1.]))
    row['return_limit_mm'] = 1.1
    row['supply_excess_limit_mm'] = 2.
    result = ranking.predict([row], dict(ref='BYPASS'), pose(1.))
    assert result['status'] == 'nonregressing'


@pytest.mark.parametrize('change', [dict(status='missing'), dict(tangent_target={}),
    dict(return_gate_mode='rail_to_rail_tangent_loop'), dict(shared_pin_reference={'ok': True}),
    dict(owner_ground_positions_mm=[]), dict(supply_excess_limit_mm=None),
    dict(cap_supply_position_mm=[float('nan'), 0])])
def test_missing_or_ambiguous_reference_keeps_original_order(change):
    rows = [dict(detail(), **change)]
    menu = [pose(.5), pose(-.1)]
    result = ranking.rank(rows, dict(ref='BYPASS'), menu)
    assert result['counts'] == {'unknown': 2} and not result['reordered']
    assert len(result['candidates']) == len(menu)


def test_shared_supply_and_unsupported_rotation_are_not_silently_predicted():
    rows = [detail(), dict(detail(), cap_ref='OTHER_CAP')]
    assert ranking.predict(rows, dict(ref='BYPASS'), pose(.5))['status'] == 'unknown'
    candidate = dict(pose(.5), rotation_delta_deg=180)
    assert ranking.predict([detail()], dict(ref='BYPASS'), candidate)['status'] == 'unknown'


def test_same_counts_cannot_trade_cells_and_good_existing_menu_order_survives():
    first = detail()
    second = deepcopy(first)
    second.update(cap_ref='SECOND', owner_ref='ANOTHER')
    second['cap_supply_position_mm'] = [-1., 0.]
    second['cap_ground_position_mm'] = [-1., 1.]
    result = ranking.predict([first, second],
        dict(ref='BYPASS', companion_refs=['SECOND']), pose(.5))
    assert result['status'] == 'regressed'
    menu = [pose(-.2), pose(-.1), pose(.1)]
    result = ranking.rank([first], dict(ref='BYPASS'), menu)
    assert not result['reordered']
    assert [r['dx_mm'] for r in result['candidates']] == [-.2, -.1, .1]


def test_unrelated_part_has_no_invented_electrical_constraints():
    assert ranking.predict([detail()], dict(ref='OTHER'), pose(.5))['status'] == 'unaffected'


def test_native_wrapper_reads_once_and_preserves_policy(monkeypatch):
    import cec_synth_pipeline as synth
    calls = []
    def adjacency(path, cfg):
        calls.append((path, cfg.params))
        return dict(details=[detail()])
    monkeypatch.setattr(synth, '_oracle_decoupler_adjacency', adjacency)
    policy = {'params': {'decoupler_loop_excess_max_mm': 1.1, 'other_authority': 'unchanged'}}
    result = ranking.rank_candidates('native.kicad_pcb', dict(ref='BYPASS'),
        [pose(.5), pose(-.1)], policy)
    assert calls == [('native.kicad_pcb', policy['params'])]
    assert result['counts'] == {'nonregressing': 2}


def test_native_wrapper_failure_does_not_erase_candidates(monkeypatch):
    import cec_synth_pipeline as synth
    monkeypatch.setattr(synth, '_oracle_decoupler_adjacency', lambda *args: dict(error='unavailable'))
    menu = [pose(.5), pose(-.1)]
    result = ranking.rank_candidates('native.kicad_pcb', dict(ref='BYPASS'), menu)
    assert result['candidates'] == menu and result['error']
