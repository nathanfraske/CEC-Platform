"""Rail-island construction cannot borrow a local endpoint current waiver."""
from unittest import mock

import pcbnew
import pytest

import cec_decoupler_cell as cells
import cec_retained_supply_port as ports
from test_retained_supply_port import fixture


@pytest.mark.parametrize('angle,back,netname,ref', [
    (0, False, '/supply/A', 'UNKNOWN_A'),
    (90, False, 'SERVICE_OTHER', 'UNKNOWN_B'),
    (180, True, '/different/RAIL', 'UNKNOWN_C'),
    (270, True, 'SUPPLY_D', 'UNKNOWN_D'),
])
def test_untyped_whole_rail_endpoints_receive_full_class_and_current_width(
        angle, back, netname, ref):
    board, roots, columns, tails, current = fixture(
        angle=angle, back=back, netname=netname, ref=ref)
    for item in [*columns, *tails]:
        board.Remove(item)
    original = cells.cec_fr._guarded_profiled_lastmile_legs
    searches = []
    def search(*args, **kwargs):
        width = args[3]
        assert kwargs['start_escape'] is None and kwargs['end_escape'] is None
        validator = kwargs['path_validator']
        assert validator([(args[1], args[2], width)]) is True
        assert validator([(args[1], args[2], width - 1)]) is False
        searches.append(args[4])
        return original(*args, **kwargs)
    with mock.patch.object(cells, '_supply_current_widths', return_value=current), \
            mock.patch.object(cells, '_netclass', return_value=dict(
                width=1000000, clearance=200000, via_dia=.8, via_drill=.4)), \
            mock.patch.object(ports, 'plan_rail', return_value=(None, None)), \
            mock.patch.object(cells, '_canonical_whole_rail_surface', return_value=None), \
            mock.patch.object(cells.cec_fr, '_guarded_profiled_lastmile_legs', side_effect=search):
        result, error = cells._add_supply_link(board, *roots, lock=True,
            rail_completion=True, search_timeout_s=2., search_work_limit=8192)
    assert error is None and result['status'] == 'linked'
    assert searches
    assert result['neckdown_widths_mm'] == []
    assert all(t.GetClass() == 'PCB_TRACK' and t.GetWidth() >= max(1000000,
        current['required_by_layer_nm'][int(t.GetLayer())]) for t in result['items'])
    assert cells._shortest_track_path_mm(board, *roots) is not None


def test_whole_rail_endpoint_cannot_commit_under_current_bridge_or_partial_copper():
    board, roots, columns, tails, current = fixture(netname='RENAMED_POWER')
    for item in [*columns, *tails]:
        board.Remove(item)
    thin = [('trk', roots[0].GetPosition(), roots[1].GetPosition(),
             200000, pcbnew.F_Cu)]
    captured = []
    def pofv(*args, **kwargs):
        captured.append(kwargs['ops_ok'](thin))
        return thin, dict()
    with mock.patch.object(cells, '_supply_current_widths', return_value=current), \
            mock.patch.object(cells, '_netclass', return_value=dict(
                width=1000000, clearance=200000, via_dia=.8, via_drill=.4)), \
            mock.patch.object(ports, 'plan_rail', return_value=(None, None)), \
            mock.patch.object(cells, '_canonical_whole_rail_surface', return_value=None), \
            mock.patch.object(cells.cec_fr, '_guarded_profiled_lastmile_legs', return_value=None), \
            mock.patch.object(cells, '_pofv_supply_bridge_ops', side_effect=pofv), \
            mock.patch.object(cells.cec_fr, '_lastmile_bridge', return_value=None):
        result, error = cells._add_supply_link(board, *roots, lock=True,
            rail_completion=True, search_timeout_s=2., search_work_limit=8192)
    assert result is None and error
    assert captured and all(v is False for v in captured)
    assert list(board.GetTracks()) == []


def test_planar_rail_uses_actual_face_current_floor_not_preferred_class_only():
    board, roots, columns, tails, current = fixture()
    for item in [*columns, *tails]:
        board.Remove(item)
    current['required_by_layer_nm'][pcbnew.F_Cu] = 1100001
    with mock.patch.object(cells, '_supply_current_widths', return_value=current), \
            mock.patch.object(cells, '_netclass', return_value=dict(
                width=1000000, clearance=200000, via_dia=.8, via_drill=.4)), \
            mock.patch.object(ports, 'plan_rail', return_value=(None, None)):
        result, error = cells._add_supply_link(board, *roots, lock=True,
            rail_completion=True, search_timeout_s=2., search_work_limit=8192)
    assert error is None and result
    assert all(t.GetLayer() == pcbnew.F_Cu and t.GetWidth() >= 1100001
        for t in result['items'])
