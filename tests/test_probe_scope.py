"""A partial probe must not get credit for omitting another failed domain."""
import pytest

from cec_probe_scope import affected_pairs, measured_pair_nets, preserve_unmeasured


@pytest.mark.parametrize('prefix', ['', '/nested/', '/alternate/'])
def test_both_sides_of_moved_series_parts_are_rechecked(prefix):
    pairs = [dict(name=prefix+'one', p=prefix+'p1', n=prefix+'n1'),
             dict(name=prefix+'two', p=prefix+'p2', n=prefix+'n2'),
             dict(name=prefix+'other', p=prefix+'p3', n=prefix+'n3')]
    refs = {prefix+'p1': {'driver', 'series_p'}, prefix+'n1': {'driver', 'series_n'},
            prefix+'p2': {'series_p', 'connector'}, prefix+'n2': {'series_n', 'connector'}}
    names = affected_pairs(pairs, refs, ['series_p', 'series_n'], [prefix+'one'])
    assert names == (prefix+'one', prefix+'two')
    assert measured_pair_nets(pairs, names) == sorted(prefix+x for x in ('p1','n1','p2','n2'))
    assert affected_pairs(pairs, refs, ['unrelated'], [prefix+'one']) == (prefix+'one',)
    assert affected_pairs(pairs, refs, [], []) is None


def baseline():
    return dict(critical_route_refused_count=11, critical_kelvin_refused_count=9,
                critical_pair_refused_count=1, critical_pair_remaining_edge_count=1,
                critical_pair_refused=[dict(name='pair_a', endpoint_stations=['a','b'])],
                critical_route_quality_refused_count=1,
                critical_route_quality_refused=[dict(net='independent', type='backtrack')])


def test_unrelated_quality_failure_cannot_disappear_from_partial_pair_score():
    measured = dict(critical_route_refused_count=10, critical_pair_refused_count=1,
                    critical_pair_remaining_edge_count=1)
    row = preserve_unmeasured(baseline(), measured, pair_names=['pair_a'], measured_nets=['a_p','a_n'])
    assert row['critical_route_refused_count'] == 11  # not a false 11 -> 10 gain
    assert row['probe_scope']['carried_quality_refusals'] == 1
    assert not row['probe_scope']['complete_board_authority']
    assert measured['critical_route_refused_count'] == 10


def test_new_shared_pair_failure_is_not_hidden_by_an_omitted_quality_failure():
    row = preserve_unmeasured(baseline(), dict(critical_route_refused_count=11,
        critical_pair_refused_count=2, critical_pair_remaining_edge_count=2),
        pair_names=['pair_a','pair_b'], measured_nets=['a_p','a_n','b_p','b_n'])
    assert row['critical_route_refused_count'] == 12
    assert row['critical_pair_remaining_edge_count'] == 2


def test_kelvin_only_probe_preserves_all_unmeasured_pair_and_quality_failures():
    row = preserve_unmeasured(baseline(), {'critical_route_refused_count': 9},
                              pair_names=(), measured_nets=['sense'])
    assert row['critical_route_refused_count'] == 11
    improved = preserve_unmeasured(baseline(), {'critical_route_refused_count': 7},
                                   pair_names=(), measured_nets=['sense'])
    assert improved['critical_route_refused_count'] == 9


def test_measured_quality_can_improve_and_full_probe_is_not_baseline_floored():
    row = preserve_unmeasured(baseline(), {'critical_route_refused_count': 10},
                              pair_names=['pair_a'], measured_nets=['independent'])
    assert row['critical_route_refused_count'] == 10
    assert preserve_unmeasured(baseline(), {'critical_route_refused_count': 0},
                               pair_names=None)['critical_route_refused_count'] == 0


def test_unknown_or_truncated_legacy_failures_stay_visible():
    base = baseline()
    base.update(critical_pair_refused=[], critical_pair_remaining_edge_count=4,
                critical_route_quality_refused=[])
    row = preserve_unmeasured(base, {'critical_route_refused_count': 9},
                              pair_names=['pair_a'], measured_nets=['independent'])
    assert row['critical_route_refused_count'] == 11
    assert row['critical_pair_remaining_edge_count'] == 4


def test_out_of_scope_pair_edges_are_kept_without_double_counting_measured_rows():
    base = baseline()
    base.update(critical_pair_refused_count=2, critical_pair_remaining_edge_count=4,
                critical_pair_refused=[dict(name='pair_a', remaining_edge_count=1),
                                      dict(name='pair_b', remaining_edge_count=3)])
    row = preserve_unmeasured(base, dict(critical_route_refused_count=1,
        critical_pair_refused_count=1, critical_pair_remaining_edge_count=2),
        pair_names=['pair_a'], measured_nets=['independent'])
    assert row['critical_pair_refused_count'] == 2
    assert row['critical_pair_remaining_edge_count'] == 5
