"""Smaller inner annuli never erase holes, outer lands or native floors."""
import pcbnew
import pytest
import cec_fr as fr
import cec_native_via_land_context as native
from test_lastmile import _board
from test_field_proposals import track


def fixture(rotation=0):
    board=_board([],edge=(0,0,25,25));board.SetCopperLayerCount(6)
    for name in ('/ordinary','/foreign'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(10,10));via.SetDrill(300000)
    via.SetNetCode(board.GetNetcodeFromNetname('/ordinary'));via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.Padstack().SetMode(pcbnew.PADSTACK.MODE_FRONT_INNER_BACK)
    for layer in board.GetEnabledLayers().CuStack():via.SetWidth(layer,3600000 if layer in (pcbnew.F_Cu,pcbnew.B_Cu) else 600000)
    track(board,'/foreign',(9,9),(11,9),layer=pcbnew.In2_Cu)
    if rotation:
        via.Rotate(pcbnew.VECTOR2I_MM(12,12),pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
        for item in board.GetTracks():item.Rotate(pcbnew.VECTOR2I_MM(12,12),pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
    return board,via


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_clearance_checks_the_real_land_on_every_actual_face(rotation):
    board,via=fixture(rotation);code=via.GetNetCode();at=via.GetPosition();report={}
    assert not fr._via_spot_clear(board,at,3600000,200000,{code},drill_nm=300000,net_code=code,foreign_cache={})
    assert fr._via_spot_clear(board,at,3600000,200000,{code},drill_nm=300000,net_code=code,
        foreign_cache={},native_padstack_via=via,report=report),report
    assert len(report['actual_native_land_diameters_nm'])==6
    assert report['actual_native_land_diameters_nm']['F.Cu']==3600000
    assert sorted(report['actual_native_land_diameters_nm'].values())==[600000]*4+[3600000]*2
    assert not list(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')


@pytest.mark.parametrize('fault',['outer_collision','inner_collision','hole','net','at','drill',
    'maximum','inner_floor','inner_annulus','mode','blind','hole_clearance'])
def test_actual_outer_copper_full_depth_bore_and_process_floors_cannot_be_omitted(fault):
    board,via=fixture();code=via.GetNetCode();at=pcbnew.VECTOR2I(*via.GetPosition());drill=300000;maximum=3600000
    if fault=='outer_collision':track(board,'/foreign',(9,9),(11,9),layer=pcbnew.F_Cu)
    elif fault=='inner_collision':track(board,'/foreign',(9,9.6),(11,9.6),layer=pcbnew.In1_Cu)
    elif fault=='hole':
        other=pcbnew.PCB_VIA(board);other.SetPosition(at);other.SetWidth(600000);other.SetDrill(300000)
        other.SetNetCode(code);other.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(other)
    elif fault=='net':via.SetNetCode(board.GetNetcodeFromNetname('/foreign'))
    elif fault=='at':via.SetPosition(pcbnew.VECTOR2I_MM(10.1,10))
    elif fault=='drill':drill=400000
    elif fault=='maximum':maximum=3500000
    elif fault=='inner_floor':
        board.GetDesignSettings().m_ViasMinSize=700000
    elif fault=='inner_annulus':via.SetWidth(pcbnew.In1_Cu,400000)
    elif fault=='mode':via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM)
    elif fault=='blind':via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault=='hole_clearance':board.GetDesignSettings().m_HoleClearance=600000
    assert not fr._via_spot_clear(board,at,maximum,200000,{code},drill_nm=drill,net_code=code,
        foreign_cache={},native_padstack_via=via)


def test_actual_padstack_dimensions_survive_native_save_and_reload(tmp_path):
    board,via=fixture();board.Add(via);path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    loaded=pcbnew.LoadBoard(str(path));actual=next(t for t in loaded.GetTracks() if t.GetClass()=='PCB_VIA')
    widths=native.inspect(loaded,actual,at=actual.GetPosition(),maximum_diameter_nm=3600000,
        drill_nm=300000,net_code=actual.GetNetCode(),clearance_nm=200000)
    assert sorted(widths.values())==[600000]*4+[3600000]*2 and actual.GetDrillValue()==300000
