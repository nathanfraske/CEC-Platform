"""Pad containment is process evidence, never a copper-clearance waiver."""
import pcbnew
import pytest

import cec_decoupler_cell as cell
import cec_fr as fr
from cec_local_copper_cell import copper_inventory
from test_compact_ground_dogbone import fixture


POSES=[((15.,15.),0,pcbnew.F_Cu),((32.,23.),90,pcbnew.F_Cu),
       ((25.,35.),180,pcbnew.B_Cu),((12.,29.),270,pcbnew.B_Cu)]


def obstacle(board,point,angle,layer,*,width=.2):
    net=pcbnew.NETINFO_ITEM(board,'/RENAMED/FOREIGN');board.Add(net)
    t=pcbnew.PCB_TRACK(board);t.SetNet(net);t.SetLayer(layer)
    x,y=point
    ends=((x-2,y),(x+2,y)) if angle in (0,180) else ((x,y-2),(x,y+2))
    t.SetStart(pcbnew.VECTOR2I_MM(*ends[0]));t.SetEnd(pcbnew.VECTOR2I_MM(*ends[1]))
    t.SetWidth(pcbnew.FromMM(width));t.SetLocked(True);board.Add(t)
    return t


@pytest.mark.parametrize('center,angle,face',POSES)
@pytest.mark.parametrize('foreign_layer',[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('cached',[False,True])
def test_containment_hint_cannot_hide_foreign_track(center,angle,face,foreign_layer,cached):
    board,pad=fixture(center=center,angle=angle,layer=face)
    pad.SetSize(pcbnew.VECTOR2I_MM(1.,1.))
    foreign=obstacle(board,center,angle,foreign_layer)
    before=copper_inventory(board);report={}
    # Deliberately claim all layers, including ones with no owning SMD pad.
    # No caller can convert that assertion into skip-layer authority.
    okay=fr._via_spot_clear(board,pad.GetPosition(),pcbnew.FromMM(.35),
        pcbnew.FromMM(.20),{pad.GetNetCode()},drill_nm=pcbnew.FromMM(.25),
        net_code=pad.GetNetCode(),contained_layers=board.GetEnabledLayers().CuStack(),
        foreign_cache={} if cached else None,report=report)
    assert okay is False,report
    assert report['reason']=='foreign copper excludes via land'
    assert report['layer']==pcbnew.LayerName(foreign_layer)
    assert any(row.get('uuid')==foreign.m_Uuid.AsString() for row in report['blockers'])
    assert copper_inventory(board)==before


@pytest.mark.parametrize('center,angle,face',POSES)
@pytest.mark.parametrize('cached',[False,True])
def test_clean_native_contained_seat_is_still_available(center,angle,face,cached):
    board,pad=fixture(center=center,angle=angle,layer=face)
    pad.SetSize(pcbnew.VECTOR2I_MM(1.,1.));before=copper_inventory(board)
    report={}
    assert fr._via_spot_clear(board,pad.GetPosition(),pcbnew.FromMM(.35),
        pcbnew.FromMM(.20),{pad.GetNetCode()},drill_nm=pcbnew.FromMM(.25),
        net_code=pad.GetNetCode(),contained_layers={face},
        foreign_cache={} if cached else None,report=report),report
    assert copper_inventory(board)==before


@pytest.mark.parametrize('center,angle,face',POSES)
def test_real_ground_return_emitter_refuses_obstructed_surface_without_trial_copper(center,angle,face):
    board,pad=fixture(center=center,angle=angle,layer=face)
    pad.SetSize(pcbnew.VECTOR2I_MM(1.,1.))
    obstacle(board,center,angle,face,width=6.)
    before=copper_inventory(board);report={}
    result,error=cell._add_ground_return(board,pad,board_path='',reach_mm=1.5,
                                         lock=True,diagnostics=report)
    assert result is None and error
    assert report['pad_center']['copper_admission']['ok'] is False
    assert report['pad_center']['copper_admission']['layer']==pcbnew.LayerName(face)
    assert copper_inventory(board)==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('cached',[False,True])
@pytest.mark.parametrize('delta_nm,expected',[(-1,False),(0,True),(1,True)])
def test_native_circle_has_no_directional_probe_overhang_or_clearance_waiver(quarter,cached,delta_nm,expected):
    """Exact factory gap is legal; one nanometre below it is still refused."""
    board,pad=fixture(center=(15.,15.),angle=quarter*90,layer=pcbnew.F_Cu)
    pad.SetSize(pcbnew.VECTOR2I_MM(1.,1.))
    net=pcbnew.NETINFO_ITEM(board,'renamed_exact_gap_obstacle');board.Add(net)
    t=pcbnew.PCB_TRACK(board);t.SetNet(net);t.SetLayer(pcbnew.In2_Cu);t.SetWidth(200000)
    # .35 mm circle radius + .1 mm track radius + unchanged .2 mm gap.
    offset=475000+delta_nm;cx,cy=tuple(pad.GetPosition())
    if quarter%2:
        sign=1 if quarter==1 else -1
        t.SetStart(pcbnew.VECTOR2I(cx-1000000,cy+sign*offset))
        t.SetEnd(pcbnew.VECTOR2I(cx+1000000,cy+sign*offset))
    else:
        sign=1 if quarter==0 else -1
        t.SetStart(pcbnew.VECTOR2I(cx+sign*offset,cy-1000000))
        t.SetEnd(pcbnew.VECTOR2I(cx+sign*offset,cy+1000000))
    board.Add(t);before=copper_inventory(board);report={}
    result=fr._via_spot_clear(board,pad.GetPosition(),350000,200000,{pad.GetNetCode()},
        drill_nm=250000,net_code=pad.GetNetCode(),foreign_cache={} if cached else None,report=report)
    assert result is expected,report
    if not expected:
        assert report['layer']==pcbnew.LayerName(pcbnew.In2_Cu)
        assert any(r.get('uuid')==t.m_Uuid.AsString() for r in report['blockers'])
    assert copper_inventory(board)==before
