"""Cheap routing order is not a clearance/current/connectivity waiver."""
import time
from unittest import mock

import pcbnew
import pytest

import cec_decoupler_cell as cells
import cec_search_budget as budget
from test_retained_supply_port import fixture


@pytest.mark.parametrize('angle,back', [(0, False), (90, False),
    (180, True), (270, True)])
def test_native_renamed_rotated_full_face_precheck_is_read_only(angle, back):
    board, roots, _, _, current = fixture(angle=angle, back=back,
        netname='/arbitrary/LOAD_RAIL', ref='NEW_OWNER_')
    old = {t.m_Uuid.AsString() for t in board.GetTracks()}
    face = pcbnew.B_Cu if back else pcbnew.F_Cu
    with budget.scoped(64):
        result = cells._canonical_whole_rail_surface(board,
            *(p.GetPosition() for p in roots), [face],
            net_code=roots[0].GetNetCode(), class_width_nm=1000000,
            clearance_nm=200000, current_widths=current,
            deadline_monotonic=time.monotonic()+2., max_length_nm=10000000,
            foreign_cache={})
    assert result and result[1] == face
    assert all(w >= max(1000000, current['required_by_layer_nm'][face])
        for a, b, w in result[0])
    assert old == {t.m_Uuid.AsString() for t in board.GetTracks()}


def test_inner_planes_are_not_cheap_surface_or_borrowed_outer_width():
    board, roots, _, _, current = fixture()
    assert cells._canonical_whole_rail_surface(board,
        *(p.GetPosition() for p in roots), [pcbnew.In2_Cu],
        net_code=roots[0].GetNetCode(), class_width_nm=1000000,
        clearance_nm=200000, current_widths=current,
        deadline_monotonic=time.monotonic()+2., max_length_nm=10000000,
        foreign_cache={}) is None


@pytest.mark.parametrize('case', ['foreign', 'edge', 'deadline', 'length', 'authority'])
def test_fail_closed_precheck_never_mutates_or_waives(case):
    board, roots, _, _, current = fixture()
    old = {t.m_Uuid.AsString() for t in board.GetTracks()}
    with mock.patch.object(cells.cec_fr, '_tap_foreign_clear', return_value=case!='foreign'), \
            mock.patch.object(cells.cec_fr, '_edge_leg_clear', return_value=case!='edge'), \
            budget.scoped(64):
        result = cells._canonical_whole_rail_surface(board,
            *(p.GetPosition() for p in roots), [pcbnew.F_Cu],
            net_code=roots[0].GetNetCode(), class_width_nm=1000000,
            clearance_nm=200000, current_widths=None if case=='authority' else current,
            deadline_monotonic=time.monotonic()+(-1 if case=='deadline' else 2.),
            max_length_nm=1 if case=='length' else 10000000, foreign_cache={})
    assert result is None and old == {t.m_Uuid.AsString() for t in board.GetTracks()}


def test_integrated_clear_surface_precedes_slow_retained_column_walks():
    board, roots, _, _, current = fixture(netname='/different/PWR', ref='ALT')
    old = {t.m_Uuid.AsString() for t in board.GetTracks()}
    with mock.patch.object(cells, '_supply_current_widths', return_value=current), \
            mock.patch.object(cells, '_netclass', return_value=dict(
                width=1000000, clearance=200000, via_dia=.8, via_drill=.4)), \
            mock.patch.object(cells, '_retained_supply_throat_ops',
                side_effect=AssertionError('cheap surface should run first')):
        result, error = cells._add_supply_link(board, *roots, lock=True,
            rail_completion=True, search_timeout_s=2., search_work_limit=64)
    assert error is None and result['status']=='linked-full-current-surface'
    assert result['vias']==0 and old <= {t.m_Uuid.AsString() for t in board.GetTracks()}
    assert all(t.GetClass()=='PCB_TRACK' and t.GetWidth()>=1000000 for t in result['items'])


@pytest.mark.parametrize('angle,back', [(0, False), (90, False), (180, True), (270, True)])
def test_class_only_launch_preserves_full_current_and_bounded_full_width_throat(angle, back):
    board, roots, _, _, current = fixture(angle=angle, back=back,
        netname='/new/POWER', ref='OTHER_')
    face = pcbnew.B_Cu if back else pcbnew.F_Cu
    floor = current['required_by_layer_nm'][face]
    assert floor < 1000000
    def native_clear(_board, a, b, width, _layer, *_args, **_kwargs):
        # Simulate narrow native landing windows only near both endpoints.
        # The middle is available for the unchanged one-millimetre trunk.
        at_land = any(tuple(p.GetPosition()) in (tuple(a), tuple(b)) for p in roots)
        return width == floor if at_land else True
    with mock.patch.object(cells.cec_fr, '_tap_foreign_clear', side_effect=native_clear), \
            budget.scoped(64):
        result = cells._canonical_whole_rail_surface(board,
            *(p.GetPosition() for p in roots), [face],
            net_code=roots[0].GetNetCode(), class_width_nm=1000000,
            clearance_nm=200000, current_widths=current,
            deadline_monotonic=time.monotonic()+2., max_length_nm=10000000,
            foreign_cache={}, endpoint_pads=roots)
    assert result and result[1] == face
    widths = {w for a, b, w in result[0]}
    assert min(widths)==floor and max(widths)==1000000
    assert all(w>=floor for a, b, w in result[0])
    narrow = [t for t in result[0] if t[2]<1000000]
    assert len(narrow)==2
    assert all(((a.x-b.x)**2+(a.y-b.y)**2)**.5 <= 1500000.000001 for a,b,w in narrow)


def test_current_floor_cannot_be_lowered_to_fit_class_only_landing():
    board, roots, _, _, current = fixture()
    current['required_by_layer_nm'][pcbnew.F_Cu]=1100000
    with mock.patch.object(cells.cec_fr, '_tap_foreign_clear',
            side_effect=lambda b,a,z,w,*args,**kwargs:w<1100000):
        assert cells._canonical_whole_rail_surface(board,
            *(p.GetPosition() for p in roots), [pcbnew.F_Cu],
            net_code=roots[0].GetNetCode(), class_width_nm=1000000,
            clearance_nm=200000, current_widths=current,
            deadline_monotonic=time.monotonic()+2., max_length_nm=10000000,
            foreign_cache={}, endpoint_pads=roots) is None


def test_refused_surface_additions_are_discarded_once_before_fallback():
    board, roots, _, _, current = fixture()
    old = {t.m_Uuid.AsString() for t in board.GetTracks()}
    def refuse(b, items, *_args, **_kwargs):
        cells.discard_items(b, items)
        return False, dict(qualified=False, rejected=['fixture refusal'])
    with mock.patch.object(cells, '_supply_current_widths', return_value=current), \
            mock.patch.object(cells, '_netclass', return_value=dict(
                width=1000000, clearance=200000, via_dia=.8, via_drill=.4)), \
            mock.patch.object(cells, '_admit_link_neckdowns', side_effect=refuse), \
            mock.patch.object(cells, 'discard_items', wraps=cells.discard_items) as discard, \
            mock.patch.object(cells, '_retained_supply_throat_ops',
                side_effect=RuntimeError('stop fixture at fallback')):
        with pytest.raises(RuntimeError, match='stop fixture at fallback'):
            cells._add_supply_link(board, *roots, lock=True,
                rail_completion=True, search_timeout_s=2., search_work_limit=64)
    assert discard.call_count==1
    assert old == {t.m_Uuid.AsString() for t in board.GetTracks()}
