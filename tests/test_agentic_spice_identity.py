"""Real-solver topology identities and fail-closed operating-point evidence."""
import math
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_spice as analog
import cec_spice_sanity as sanity


@pytest.mark.parametrize('names', [
    ['/SIGNAL-A', '/SIGNAL_A', '/signal_a'],
    ['A/B', 'A_B', 'A-B', 'A B', 'a_b'],
    ['Δ', 'δ', '/', '_', '0', 'gnd', 'GND', 'n_2f', 'x\nVfake n 0 9']])
def test_schematic_net_identity_is_injective_under_spice_case_folding(names):
    deck = sanity.Deck()
    nodes = [deck.n(net).lower() for net in names]
    assert len(set(nodes)) == len(names)
    assert deck.n('GND') == '0'
    assert all(node == '0' or node.startswith('n_') and node[2:].isalnum() for node in nodes)
    assert [sanity.Deck().n(net) for net in reversed(names)] == list(reversed(nodes))


def test_explicit_source_zero_ohm_alias_is_preserved():
    deck = sanity.build_deck({'R1':'0R'}, {
        '/A-B':[('R1','1')], '/a_b':[('R1','2')], 'GND':[]})
    assert deck.n('/A-B') == deck.n('/a_b')
    assert deck.n('/A_B') != deck.n('/A-B')


def test_real_ngspice_does_not_invent_short_between_sanitizer_or_case_aliases():
    deck = sanity.Deck(); deck.add('* three independent analytic dividers')
    source = deck.n('VIN')
    names = ['/SIGNAL-A', '/SIGNAL_A', '/signal_a']
    deck.add(f'Vsrc0 {source} 0 5')
    for index, (name, upper, lower) in enumerate(zip(names, [1000,1000,4000], [1000,4000,1000])):
        node = deck.n(name)
        deck.add(f'Rtop{index} {source} {node} {upper}')
        deck.add(f'Rbottom{index} {node} 0 {lower}')
    result, _, _ = sanity.run_deck(deck, [deck.n(name) for name in names])
    for name, expected in zip(names, [2.5,4.,1.]):
        assert result[f'v({deck.n(name)})'] == pytest.approx(expected, abs=1e-6)
    assert result['i(vsrc0)'] == pytest.approx(-.0045, abs=1e-9)
    assert all(math.isfinite(value) for value in result.values())


@pytest.mark.parametrize('output,reason', [
    ('v(n_probe) = 1\n', 'incomplete'),
    ('i(vsrc0) = -.001\n', 'incomplete'),
    ('v(n_probe) = nan\ni(vsrc0) = -.001\n', 'nonfinite'),
    ('v(n_probe) = 1\ni(vsrc0) = inf\n', 'nonfinite'),
    ('v(n_probe) = 1\ni(vsrc0) = -1e999\n', 'nonfinite'),
    ('v(n_probe) = 1\nv(n_probe) = 2\ni(vsrc0) = -.001\n', 'contradictory'),
    ('v(n_probe) = 1garbage\ni(vsrc0) = -.001\n', 'invalid')])
def test_sanity_never_accepts_partial_nonfinite_or_contradictory_source_measurements(output, reason):
    deck = sanity.Deck(); deck.add('Vsrc0 n_probe 0 1')
    process = SimpleNamespace(returncode=0,stdout=output,stderr='')
    with mock.patch.object(sanity.subprocess,'run',return_value=process):
        with pytest.raises(RuntimeError,match=reason):
            sanity.run_deck(deck,['n_probe'])


@pytest.mark.parametrize('output,reason', [
    ('v(ncsa) = 1\n', 'incomplete'),
    ('v(nout) = 0\n', 'incomplete'),
    ('v(ncsa) = nan\nv(nout) = 0\n', 'nonfinite'),
    ('v(ncsa) = 1\nv(nout) = inf\n', 'nonfinite'),
    ('v(ncsa) = 1\nv(nout) = 0\nv(nout) = 1\n', 'contradictory')])
def test_analog_never_treats_missing_comparator_output_as_no_trip(output, reason):
    process = SimpleNamespace(returncode=0,stdout=output,stderr='')
    with mock.patch.object(analog.subprocess,'run',return_value=process):
        with pytest.raises(RuntimeError,match=reason):
            analog.trip_current(.002,50,1.65)


def test_actual_behavioral_analog_trip_matches_declared_linear_model():
    point = analog._run(analog._cell_cir(.002,50,.5,10.))
    assert point['ncsa'] == pytest.approx(1.,abs=1e-6)
    assert point['nout'] == 1.
    assert analog.trip_current(.002,50,1.65) == pytest.approx(16.5,abs=.001)
    assert analog.saturation_current(.025,50) == pytest.approx(2.6,abs=.005)
