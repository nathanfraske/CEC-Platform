import inspect
import cec_precision_route as route


def test_clearance_is_not_reported_as_impedance_or_a_guaranteed_fallback():
    text=route._coupled_corridor_refusal_message(dict(width=.25,gap=.3,ztarget=120),.2)
    assert 'width 0.25 mm' in text and 'gap 0.3 mm' in text and 'clearance 0.2 mm' in text
    assert '0.2R' not in text and '120R' not in text
    assert 'attempted search' in text and 'may be attempted' in text
    assert 'will route' not in text and 'every candidate' not in text


def test_partial_conflicts_are_sorted_observations_not_an_exhaustiveness_claim():
    text=route._coupled_corridor_refusal_message(dict(width=.18,gap=.22),.15,['B','A','B'])
    assert text.endswith('observed reservation conflicts: A, B')
    assert 'every' not in text and 'impossible' not in text


def test_production_refusal_uses_the_shared_unit_correct_builder():
    source=inspect.getsource(route.route_coupled_pair)
    assert source.count('_coupled_corridor_refusal_message(')==1
    assert 'exact %sR geometry' not in source and 'FR will route' not in source
