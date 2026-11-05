import copy

import pytest
import cec_joint_connection_search as joint
import cec_device_power_roles as roles


def option(name, cells, cost=1):
    return dict(id=name, cells=cells, cost=cost)


def collide(a, b):
    return bool(set(a['cells']) & set(b['cells']))


@pytest.mark.parametrize('prefix', ['renamed', 'unrelated_channel'])
def test_forward_checking_preserves_scarce_future_escape(prefix):
    domains = {prefix + 'A': [option('short', [1]), option('detour', [2], 2)],
        prefix + 'B': [option('only-escape', [1])]}
    before = copy.deepcopy(domains)
    result = joint.solve(domains, conflicts=collide)
    assert result['complete'] and result['selected'][prefix + 'A']['id'] == 'detour'
    assert domains == before and result['input_unchanged']
    assert not result['routing_admitted'] and not result['release_authority']


def test_backtracks_earlier_low_cost_choice_when_future_cell_is_starved():
    domains = {'a': [option('bad', [1]), option('good', [2], 2)],
        'b': [option('b1', [1, 3]), option('b2', [1, 4])],
        'c': [option('c1', [3]), option('c2', [4])]}
    result = joint.solve(domains, conflicts=collide)
    assert result['complete'] and result['selected']['a']['id'] == 'good'
    assert result['failure_frontier']


@pytest.mark.parametrize('failure', ['empty', 'incompatible', 'states', 'oracle'])
def test_incomplete_cell_never_returns_partial_routes_or_no_path_claim(failure):
    domains = {'a': [option('a', [1])], 'b': [option('b', [2])]}
    kwargs = {}
    if failure == 'empty': domains['b'] = []
    elif failure == 'incompatible': domains['b'][0]['cells'] = [1]
    elif failure == 'states': kwargs['max_states'] = 1
    elif failure == 'oracle': kwargs['validate_selection'] = lambda selected: False
    result = joint.solve(domains, conflicts=collide, **kwargs)
    assert not result['complete'] and result['selected'] == {}
    assert result['errors'] and not result['no_path_proof']


def test_full_selection_receiver_can_reject_and_search_other_combination():
    calls = []
    def validate(selected):
        assert set(selected) == {'one', 'two'}
        calls.append(selected['one']['id'])
        return selected['one']['id'] == 'qualified'
    result = joint.solve({'one': [option('short', [], 0), option('qualified', [])],
        'two': [option('other', [])]}, conflicts=collide, validate_selection=validate)
    assert result['complete'] and calls == ['short', 'qualified']


def test_mutating_or_ambiguous_oracle_cannot_create_admission():
    domains = {'a': [option('a', [1])], 'b': [option('b', [2])]}
    def mutate(a, b):
        a['cells'].append(99)
        return False
    result = joint.solve(domains, conflicts=mutate)
    assert not result['complete'] and result['selected'] == {}
    assert not result['input_unchanged']
    result = joint.solve({'a': [option('a', [])], 'b': [option('b', [])]},
        conflicts=lambda a, b: None)
    assert not result['complete'] and result['selected'] == {}


def test_wall_budget_includes_conflict_callback(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(joint.time, 'monotonic', lambda: clock[0])
    def expensive(a, b):
        clock[0] += 11
        return False
    result = joint.solve({'a': [option('a', [])], 'b': [option('b', [])]},
        conflicts=expensive, timeout_s=10)
    assert not result['complete'] and result['selected'] == {}
    assert any('deadline' in error for error in result['errors'])


@pytest.mark.parametrize('bounds', [dict(timeout_s=30), dict(max_states=8193),
    dict(max_pair_checks=200001), dict(max_states=True)])
def test_unbounded_search_is_refused(bounds):
    with pytest.raises(ValueError):
        joint.solve({'a': [option('a', [])]}, conflicts=collide, **bounds)


@pytest.mark.parametrize('quarter', range(4))
def test_real_trace_conflicts_are_rotation_invariant(quarter):
    from shapely.geometry import LineString
    def turn(points):
        for _ in range(quarter): points = [[-y, x] for x, y in points]
        return points
    domains = {'v': [dict(id='short', cost=1, path=turn([[0, 0], [0, 4]])),
                     dict(id='detour', cost=2, path=turn([[-2, 0], [-2, 4]]))],
               'h': [dict(id='required', cost=1, path=turn([[-1, 2], [1, 2]]))]}
    result = joint.solve(domains, conflicts=lambda a, b:
        bool(LineString(a['path']).buffer(.2).intersects(LineString(b['path']).buffer(.2))))
    assert result['complete'] and result['selected']['v']['id'] == 'detour'


@pytest.mark.parametrize('mpn', ['TLV7011DBVR', 'TLV7011DBVT'])
def test_exact_comparator_dbv_pin_table_is_not_a_load_rating(mpn):
    model = roles.contract('TLV7011', mpn=mpn, footprint='Package_TO_SOT_SMD:SOT-23-5')
    # VEE is a negative supply return; it is GND only when the actual board
    # positively ties it to GND. Do not invent a universal ground pin.
    assert model['pins'] == {'1': 'signal_output', '2': 'power_return',
        '3': 'signal_input', '4': 'signal_input', '5': 'power_input'}
    assert 'current_max_a' not in model


def test_wrong_comparator_package_or_selected_family_is_not_guessed():
    assert roles.contract('TLV7011', mpn='TLV7011DPWR', footprint='X2SON-5') is None
    assert roles.contract('TLV7011', footprint='Package_TO_SOT_SMD:SOT-23-5') is None
    with pytest.raises(ValueError, match='footprint_mismatch'):
        roles.contract('TLV7011', mpn='TLV7011DBVR', footprint='Package_TO_SOT_SMD:SC-70-5')
    with pytest.raises(ValueError, match='family_mismatch'):
        roles.contract('TLV7011', mpn='INA181A2IDBVR')


def test_invalid_callback_mutation_still_exports_no_partial_selection():
    domains = {'a':[option('a',[])], 'b':[option('b',[])]}
    def mutate(a,b):
        a['unserializable'] = {1,2}
        return False
    result = joint.solve(domains,conflicts=mutate)
    assert result['selected'] == {} and not result['complete']
    assert not result['input_unchanged']
