from fractions import Fraction
import pcbnew
import pytest
import cec_trace_clearance as audit


@pytest.mark.parametrize('geometry,expected', [
    (((0,0),(3,0),(1,-1),(1,1)), 0),
    (((0,0),(3,0),(4,0),(5,0)), 1),
    (((0,0),(3,0),(1,2),(5,2)), 4),
    (((0,0),(2,2),(1,0),(2,1)), Fraction(1,2)),
    (((1,1),(1,1),(0,0),(2,0)), 1),
    (((0,0),(3,0),(1,0),(2,0)), 0)])
def test_exact_segment_distance(geometry, expected):
    assert audit.segment_distance_sq(*geometry) == expected


def make_board(separation=400000, *, layer=pcbnew.F_Cu, same_net=False):
    b = pcbnew.BOARD()
    for code, name in ((1, '/ODD_P'), (2, '/ODD_N')):
        b.Add(pcbnew.NETINFO_ITEM(b, name, code))
        t = pcbnew.PCB_TRACK(b)
        t.SetNetCode(1 if same_net else code)
        t.SetLayer(pcbnew.F_Cu if code == 1 else layer)
        y = 0 if code == 1 else separation
        t.SetStart(pcbnew.VECTOR2I(0, y)); t.SetEnd(pcbnew.VECTOR2I(1000000, y))
        t.SetWidth(200000); b.Add(t)
    return b


@pytest.mark.parametrize('separation,violations', [(400000,0), (399999,1), (401000,0), (0,1)])
def test_actual_edge_gap_no_pair_name_exemption_or_rounding_waiver(separation, violations):
    report = audit.analyze(make_board(separation), netclass_resolver=lambda n: {'clearance': .2})
    assert report['complete'] and report['tested_pairs'] == 1
    assert report['violation_count'] == violations
    assert report['nearest'][0]['gap_mm'] == pytest.approx(separation/1e6-.2)


def test_larger_of_both_netclass_clearances_is_binding():
    report = audit.analyze(make_board(), netclass_resolver=lambda n: {'clearance': .3 if n.endswith('_N') else .2})
    assert report['violation_count'] == 1 and report['nearest'][0]['required_mm'] == .3


@pytest.mark.parametrize('board', [make_board(same_net=True), make_board(layer=pcbnew.B_Cu)])
def test_only_shared_layer_foreign_net_pairs_are_tested(board):
    assert audit.analyze(board, netclass_resolver=lambda n: {'clearance': .2})['tested_pairs'] == 0


@pytest.mark.parametrize('spec', [None, {}, {'clearance': -1}, {'clearance': float('nan')}])
def test_missing_rules_fail_closed(spec):
    report = audit.analyze(make_board(), netclass_resolver=lambda n: spec)
    assert not report['ok'] and not report['complete'] and report['errors']


def test_sub_database_unit_rounding_is_reported_not_silently_waived():
    b = make_board()
    tracks = list(b.GetTracks())
    tracks[0].SetStart(pcbnew.VECTOR2I(0, 0))
    tracks[0].SetEnd(pcbnew.VECTOR2I(1000000, 1000000))
    tracks[1].SetStart(pcbnew.VECTOR2I(0, 565685))
    tracks[1].SetEnd(pcbnew.VECTOR2I(1000000, 1565685))
    result = audit.analyze(b, netclass_resolver=lambda n: {'clearance': .2})
    assert result['violation_count'] == 1 and result['sub_database_unit_shortfalls'] == 1
    assert not result['ok'] and result['shortfalls_at_least_one_nm'] == 0


def test_zero_detail_limit_keeps_counts_without_detail_rows():
    result = audit.analyze(make_board(0), netclass_resolver=lambda n: {'clearance': .2}, detail_limit=0)
    assert result['violation_count'] == 1 and not result['nearest'] and not result['violations']


@pytest.mark.parametrize('limit', [-1, 1.5, True])
def test_invalid_detail_limit_fails_closed(limit):
    with pytest.raises(ValueError):
        audit.analyze(make_board(), netclass_resolver=lambda n: {'clearance': .2}, detail_limit=limit)
