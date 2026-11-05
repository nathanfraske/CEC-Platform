import copy
import math
import subprocess

import pytest

from cec_pipeline import pairs


def report():
    row = dict(kind='can', p='/CAN_P', n='/CAN_N', violations=[],
               skew_mm=1., uncoupled_length_mm=2., vias_p=0, vias_n=0,
               reference_coverage_pct=100., coupled_coverage_pct=98.,
               missing_return_vias=[], transition_reference_samples=0,
               plated_terminal_reference_samples=0)
    return dict(applicable=True, ok=True, pairs=[row])


def test_identical_and_metric_regression():
    a = report()
    assert pairs.compare(a, copy.deepcopy(a))['ok']
    b = copy.deepcopy(a)
    b['pairs'][0]['reference_coverage_pct'] = 99.
    assert not pairs.compare(a, b)['ok']


def test_same_count_issue_substitution_and_inherited_debt():
    a, b = report(), report()
    a['pairs'][0]['violations'] = ['missing return at (1, 2)']
    b['pairs'][0]['violations'] = ['missing return at (3, 4)']
    a['ok'] = b['ok'] = False
    assert not pairs.compare(a, b)['ok']
    result = pairs.compare(a, a)
    assert result['ok'] and result['inherited_debt']


@pytest.mark.parametrize('value', [None, True, math.nan, math.inf, -1])
def test_malformed_metric_fails_closed(value):
    a, b = report(), report()
    b['pairs'][0]['skew_mm'] = value
    with pytest.raises(ValueError):
        pairs.compare(a, b)


def test_unavailable_and_lease_boundaries():
    with pytest.raises(ValueError):
        pairs.compare(dict(applicable=False), report())
    for lease in (10, 0, True, math.nan):
        with pytest.raises(ValueError):
            pairs.receive('unused', 'unused', timeout_s=lease)


def test_same_count_return_fault_location_substitution():
    a, b = report(), report()
    a['ok'] = b['ok'] = False
    for value in (a, b):
        value['pairs'][0]['violations'] = ['one transition has no return via']
    a['pairs'][0]['missing_return_vias'] = [{'at': [1, 2]}]
    b['pairs'][0]['missing_return_vias'] = [{'at': [3, 4]}]
    assert not pairs.compare(a, b)['ok']


def test_aggregate_timeout_is_unavailable_not_pass(tmp_path, monkeypatch):
    source = tmp_path / 'source.kicad_pcb'
    source.touch()

    def timeout(*args, **kwargs):
        assert kwargs['timeout'] == 8.0
        raise subprocess.TimeoutExpired(args[0], 8.0)

    monkeypatch.setattr(subprocess, 'run', timeout)
    result = pairs.receive(source, source)
    assert result['ok'] is False and result['unavailable'] is True
    assert result['complete'] is False


def test_native_arc_midpoint_changes_physical_scope():
    import pcbnew
    from cec_pipeline.legacy import bootstrap
    bootstrap()
    boards = []
    for y in (1000000, 2000000):
        board = pcbnew.BOARD()
        arc = pcbnew.PCB_ARC(board)
        arc.SetStart(pcbnew.VECTOR2I(0, 0))
        arc.SetMid(pcbnew.VECTOR2I(1000000, y))
        arc.SetEnd(pcbnew.VECTOR2I(2000000, 0))
        arc.SetWidth(200000)
        board.Add(arc)
        boards.append(board)
    # UUIDs do not cause this assertion: compare the actual geometry row.
    a, b = [next(iter(pairs._snapshot(board)[0].values())) for board in boards]
    assert a[:-1] == b[:-1] and a[-1] != b[-1]
