"""POFV opt-in must not silently create native absolute-minimum DRC faults."""
import pcbnew
import pytest

import cec_fab_profile as fab
import cec_fr as fr


def board(diameter=.5,drill=.2,annular=.1):
    b=pcbnew.CreateEmptyBoard(); b.SetCopperLayerCount(6)
    settings=b.GetDesignSettings()
    settings.m_ViasMinSize=pcbnew.FromMM(diameter)
    settings.m_MinThroughDrill=pcbnew.FromMM(drill)
    settings.m_ViasMinAnnularWidth=pcbnew.FromMM(annular)
    props=b.GetProperties(); props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal'; b.SetProperties(props)
    return b


@pytest.mark.parametrize('geometry',[(.5,.2,.1),(.5,.3,.1),(.6,.35,.15),(.3,.2,.05)])
@pytest.mark.parametrize('web',[0,100000,477370])
def test_local_menus_keep_both_native_floors_and_requested_web(geometry,web):
    b=board(*geometry); p=fab.get_profile('jlcpcb_6l_pofv_signal')
    menu=fab.local_pofv_geometry_candidates(p,board=b,minimum_web_nm=web)
    assert menu
    for diameter,drill in menu:
        assert pcbnew.FromMM(diameter)>=pcbnew.FromMM(geometry[0])
        assert pcbnew.FromMM(drill)>=pcbnew.FromMM(geometry[1])
        assert pcbnew.FromMM(diameter)-pcbnew.FromMM(drill)>=2*pcbnew.FromMM(geometry[2])
        assert round((diameter-drill)*1e6)>=web
        assert fab.pofv_dimensions(p,diameter,drill)[0]


def test_process_drill_maximum_is_not_relaxed_to_meet_an_impossible_project_floor():
    b=board(drill=.6)
    assert not fab.local_pofv_geometry_candidates(fab.get_profile('jlcpcb_6l_pofv_signal'),board=b)


@pytest.mark.parametrize('diameter,drill,reason',[
    (.35,.25,'land'),(.5,.19,'drill'),(.5,.4,'annulus')])
def test_global_new_hole_guard_refuses_an_undersized_qualified_local_request(diameter,drill,reason):
    b=board(); r={}
    assert not fr._via_spot_clear(b,pcbnew.VECTOR2I_MM(20,20),pcbnew.FromMM(diameter),
        200000,{0},drill_nm=pcbnew.FromMM(drill),net_code=0,report=r)
    assert reason in r['reason'] and 'native board absolute minimum' in r['reason']
    assert not list(b.GetTracks())


def test_explicitly_fine_native_board_can_still_use_its_qualified_small_dimensions():
    b=board(.3,.2,.05); p=fab.get_profile('jlcpcb_6l_pofv_signal')
    assert fab.local_pofv_geometry_candidates(p,board=b)==fab.local_pofv_geometry_candidates(p)


def test_native_integer_ring_floor_survives_float_to_native_conversion():
    b=board(.6,.35,.15)
    diameter,drill,_=fab.board_legal_through_via_geometry(b,.35,.25)
    assert pcbnew.FromMM(diameter)-pcbnew.FromMM(drill)>=300000
