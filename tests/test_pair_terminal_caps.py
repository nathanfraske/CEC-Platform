"""Finite paired caps are not a centreline capsule or a clearance waiver."""
import math

import pcbnew
import pytest
import cec_fr as fr
import cec_field_coupling as field
import cec_pair_terminal_caps as caps
import cec_precision_route as route


def fixture(angle,mirror):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    board.GetDesignSettings().m_HoleClearance = 200000
    foreign = pcbnew.NETINFO_ITEM(board,'RENAMED_GROUND_RETURN'); board.Add(foreign)
    def point(x,y):
        x = -x if mirror else x
        c,s = math.cos(math.radians(angle)),math.sin(math.radians(angle))
        return (10+x*c-y*s,10+x*s+y*c)
    via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(*point(1,0)))
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetWidth(600000); via.SetDrill(300000); via.SetNet(foreign); board.Add(via)
    return board,via,point


@pytest.mark.parametrize('angle,mirror', [(0,False),(90,False),(180,False),(270,False),
    (0,True),(90,True),(180,True),(270,True)])
def test_actual_two_lane_caps_can_clear_a_real_via_that_blocks_combined_capsule(angle,mirror):
    board,via,point = fixture(angle,mirror)
    before = field._field_snapshot_inventory(board)
    zones,copper = fr._foreign_shape_indexes(board,pcbnew.In2_Cu,set())
    a,b = point(0,0),point(.23,0)
    assert not fr._snapshot_foreign_clear(pcbnew.VECTOR2I_MM(*a),pcbnew.VECTOR2I_MM(*b),
        740004,200000,zones,copper)
    assert caps.clear(a,b,width_mm=.2,gap_mm=.340004,clearance_nm=200000,
        zone_rows=zones,copper_rows=copper)
    assert before == field._field_snapshot_inventory(board)


@pytest.mark.parametrize('fault',['real_lane_hit','increased_gap_obligation','increased_member_width'])
def test_exact_caps_never_ignore_real_native_foreign_copper_or_changed_dimensions(fault):
    board,via,point = fixture(0,False)
    width,gap = .2,200000
    if fault == 'real_lane_hit': via.SetPosition(pcbnew.VECTOR2I_MM(*point(.5,.27)))
    if fault == 'increased_gap_obligation': gap = 450000
    if fault == 'increased_member_width': width = 1.2
    zones,copper = fr._foreign_shape_indexes(board,pcbnew.In2_Cu,set())
    assert not caps.clear(point(0,0),point(.23,0),width_mm=width,gap_mm=.340004,
        clearance_nm=gap,zone_rows=zones,copper_rows=copper)


@pytest.mark.parametrize('angle,mirror', [(0,False),(90,False),(180,False),(270,False),
    (0,True),(90,True),(180,True),(270,True)])
def test_production_coupled_grid_refines_only_native_terminal_caps_without_writing_copper(angle,mirror):
    board,via,point = fixture(angle,mirror)
    via.SetPosition(pcbnew.VECTOR2I_MM(*point(5.77,0)))
    codes=[]
    for name in ('RENAMED_LANE_P','RENAMED_LANE_N'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);codes.append(net.GetNetCode())
    for a,b in (((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    origin,tip=point(0,0),point(1,0)
    heading=tuple(x-y for x,y in zip(tip,origin))
    before=field._field_snapshot_inventory(board);detail={}
    result=route._grid_coupled_path(board,start_center=point(-5,0),end_center=point(5,0),
        p_start=point(-5,.270002),n_start=point(-5,-.270002),
        p_end=point(5,.270002),n_end=point(5,-.270002),layer_id=pcbnew.In2_Cu,
        width=.2,gap=.34,clearance=.2,own=set(codes),pair_net_codes=tuple(codes),
        portal_mode=True,portal_start_heading=heading,portal_end_heading=heading,
        step=.25,strict_taper_continuation=True,diagnostics=detail)
    assert result,detail
    assert detail['rejection_counts']['exact_native_terminal_caps_clear']>0
    for lane in result[:2]:
        assert route._polyline_is_octilinear(lane)
        assert sum(route._dist(a,b) for a,b in zip(lane,lane[1:])) == pytest.approx(10,abs=1e-5)
        assert all(fr._tap_foreign_clear(board,pcbnew.VECTOR2I_MM(*a),pcbnew.VECTOR2I_MM(*b),
            200000,pcbnew.In2_Cu,200000,set(codes),foreign_cache={})
            for a,b in zip(lane,lane[1:]))
    assert before == field._field_snapshot_inventory(board)
