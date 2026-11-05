"""Explicit local sizes retain ordinary board floors and every native guard."""
import time
import pytest
import cec_measurement_leaf as leaf
import cec_native_via_frontier as frontier
from test_measurement_leaf import fixture


@pytest.mark.parametrize('requested,expected',[
    ((.5,.3),(.5,.3)),((.3,.2),(.5,.3)),((.5,.4),(.6,.4)),((.7,.3),(.7,.3))])
@pytest.mark.parametrize('quarter',[0,1,2,3])
def test_actual_requested_geometry_is_clamped_not_replaced_by_remote_preference(requested,expected,quarter):
    board,pad,_,_,xy=fixture('renamed_geometry_policy',quarter)
    s=board.GetDesignSettings();s.m_ViasMinSize=500000;s.m_MinThroughDrill=300000;s.m_ViasMinAnnularWidth=100000
    before=leaf._binding(board);calls=[]
    def guard(at,dia):calls.append((tuple(at),dia));return True
    result=frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
        radius_mm=4,max_sites=4,deadline=time.monotonic()+2.,diameter_mm=requested[0],
        drill_mm=requested[1],preserve_requested_geometry=True,barrel_guard=guard)
    assert (result['diameter_mm'],result['drill_mm'])==expected
    assert result['sites_nm'] and calls
    assert all(dia==round(expected[0]*1e6) for _,dia in calls)
    assert result['requested_geometry_preserved_subject_to_ordinary_board_floors']
    assert not result['routing_admitted'] and not result['release_authority']
    assert leaf._binding(board)==before


def test_default_remote_request_preference_is_unchanged():
    board,pad,_,_,xy=fixture('legacy_preference')
    s=board.GetDesignSettings();s.m_ViasMinSize=500000;s.m_MinThroughDrill=300000;s.m_ViasMinAnnularWidth=100000
    result=frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
        radius_mm=4,max_sites=4,deadline=time.monotonic()+2.,diameter_mm=.3,drill_mm=.2)
    assert (result['diameter_mm'],result['drill_mm'])==(.6,.3)
    assert not result['requested_geometry_preserved_subject_to_ordinary_board_floors']


@pytest.mark.parametrize('flag',[None,1,'yes'])
def test_local_requested_geometry_policy_is_literal_boolean(flag):
    board,pad,_,_,xy=fixture()
    with pytest.raises(ValueError):
        frontier.sites(board,pad.GetNetCode(),list(xy((12,10))),clearance_nm=200000,
            deadline=time.monotonic()+2.,preserve_requested_geometry=flag)
