"""Native compact GND escapes use existing POFV authority, never a size waiver."""
import math
from unittest import mock

import pcbnew
import pytest

import cec_decoupler_cell as cell
import cec_fab_profile as fab
import cec_fr
from cec_local_copper_cell import copper_inventory
from cec_native_items import discard_items


def fixture(*, center=(15., 15.), angle=0, layer=pcbnew.F_Cu,
            profile='jlcpcb_6l_pofv_signal', loaded_path=None):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    props = board.GetProperties(); props['CEC_FAB_PROFILE'] = profile
    board.SetProperties(props)
    board.GetDesignSettings().m_TrackMinWidth = pcbnew.FromMM(.20)
    for a, b in (((0,0),(50,0)), ((50,0),(50,50)),
                 ((50,50),(0,50)), ((0,50),(0,0))):
        edge = pcbnew.PCB_SHAPE(board); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
    net = pcbnew.NETINFO_ITEM(board, 'GND'); board.Add(net)
    klass = pcbnew.NETCLASS('Return'); klass.SetTrackWidth(pcbnew.FromMM(.5))
    klass.SetClearance(pcbnew.FromMM(.20)); klass.SetViaDiameter(pcbnew.FromMM(.6))
    klass.SetViaDrill(pcbnew.FromMM(.3)); net.SetNetClass(klass)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('IC_RENAMED'); fp.SetLayer(layer)
    pad = pcbnew.PAD(fp); pad.SetPadName('G'); pad.SetNet(net)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.6, .2)); pad.SetPosition(pcbnew.VECTOR2I_MM(*center))
    pad.SetOrientationDegrees(angle)
    layers = pcbnew.LSET(); layers.AddLayer(layer); pad.SetLayerSet(layers)
    fp.Add(pad); board.Add(fp)
    if loaded_path:
        pcbnew.SaveBoard(str(loaded_path), board)
        board = pcbnew.LoadBoard(str(loaded_path))
        pad = board.FindFootprintByReference('IC_RENAMED').FindPadByNumber('G')
    return board, pad


def add(board, pad, **kwargs):
    return cell._add_ground_return(board, pad, board_path='', reach_mm=1.5,
                                   lock=True, **kwargs)


@pytest.mark.parametrize('center,angle,layer', [
    ((15.,15.),0,pcbnew.F_Cu), ((32.,23.),90,pcbnew.F_Cu),
    ((25.,35.),180,pcbnew.B_Cu), ((12.,29.),45,pcbnew.B_Cu)])
def test_narrow_native_land_gets_octilinear_qualified_compact_dogbone(center,angle,layer,tmp_path):
    board,pad = fixture(center=center,angle=angle,layer=layer,loaded_path=tmp_path/'b.kicad_pcb')
    detail={}; result,error=add(board,pad,diagnostics=detail)
    assert error is None, (error,detail)
    assert result['status']=='dogbone'
    assert result['endpoint_limited_local_via']
    assert result['diameter_mm']==.35 and result['drill_mm']==.25
    via=next(item for item in result['items'] if item.GetClass()=='PCB_VIA')
    track=next(item for item in result['items'] if item.GetClass()=='PCB_TRACK')
    assert track.GetLayer()==layer
    dx=abs(track.GetEnd().x-track.GetStart().x);dy=abs(track.GetEnd().y-track.GetStart().y)
    assert min(dx,dy)<=1 or abs(dx-dy)<=1
    assert math.hypot(dx,dy)/1e6<=1.5
    assert fab.via_at_pad_conflicts(board,via.GetPosition(),via.GetWidth(layer),
                                  via.GetDrillValue(),via.GetNetCode())==(None,[])
    assert fab.local_pofv_via_decision(board,via)[0]
    ownership=cec_fr.group_local_pofv_signal_vias(board,[via])
    assert via.m_Uuid.AsString() in ownership['uuids']
    saved=tmp_path/'generated.kicad_pcb';pcbnew.SaveBoard(str(saved),board)
    reloaded=pcbnew.LoadBoard(str(saved))
    assert via.m_Uuid.AsString() in cell.cec_constraints._validated_local_pofv_signal_uuids(
        reloaded,str(saved),{})
    discard_items(reloaded,[t for t in reloaded.GetTracks() if t.GetClass()=='PCB_TRACK'])
    assert not cell.cec_constraints._validated_local_pofv_signal_uuids(reloaded,str(saved),{})


def test_no_profile_permission_does_not_shrink_ordinary_return():
    board,pad=fixture(profile='jlcpcb_4l_standard')
    result,error=add(board,pad)
    assert error is None
    assert result['diameter_mm']>=.6 and result['drill_mm']>=.3
    assert not result.get('endpoint_limited_local_via')


def test_ordinary_back_land_also_uses_actual_copper_layer():
    board,pad=fixture(profile='jlcpcb_4l_standard',layer=pcbnew.B_Cu)
    result,error=add(board,pad)
    assert error is None
    assert all(item.GetLayer()==pcbnew.B_Cu for item in result['items']
               if item.GetClass()=='PCB_TRACK')


def test_compact_process_does_not_bypass_unmaterialized_power_guard():
    board,pad=fixture();before=copper_inventory(board);detail={}
    reservation=dict(net='FUTURE_POWER',layer='In3.Cu',x0=10,y0=10,x1=20,y1=20)
    with mock.patch.object(cec_fr,'_guarded_power_reservations',return_value=[reservation]):
        result,error=add(board,pad,diagnostics=detail)
    assert result is None and error
    assert copper_inventory(board)==before
    assert any(blocker['kind']=='pour_first_reservation'
        for attempt in detail['compact_dogbone_attempts']
        for seat in attempt['evidence']['dogbone_candidates']
        for blocker in (seat.get('copper_admission') or {}).get('blockers',[]))


def test_filename_hint_cannot_grant_compact_offpad_permission():
    board,pad=fixture(profile='')
    with mock.patch.object(fab,'active_profile_name',return_value='jlcpcb_6l_pofv_signal'):
        result,error=add(board,pad)
    assert error is None
    assert result['diameter_mm']>=.6


def test_failed_preferred_geometry_tries_explicit_process_floor():
    board,pad=fixture()
    actual=cec_fr._via_spot_clear
    def restrict(*args,**kwargs):
        return args[2]<=pcbnew.FromMM(.30) and actual(*args,**kwargs)
    with mock.patch.object(cec_fr,'_via_spot_clear',side_effect=restrict):
        result,error=add(board,pad)
    assert error is None
    assert (result['diameter_mm'],result['drill_mm'])==(.30,.20)


def test_fixed_geometry_request_does_not_secretly_shrink_further():
    board,pad=fixture()
    actual=cec_fr._via_spot_clear
    def restrict(*args,**kwargs):
        return args[2]<=pcbnew.FromMM(.30) and actual(*args,**kwargs)
    before=copper_inventory(board)
    with mock.patch.object(cec_fr,'_via_spot_clear',side_effect=restrict):
        result,error=add(board,pad,pofv_geometry=(.35,.25))
    assert result is None and error
    assert copper_inventory(board)==before


def test_failed_live_qualification_cleans_loaded_native_trials(tmp_path):
    board,pad=fixture(loaded_path=tmp_path/'input.kicad_pcb')
    before=copper_inventory(board);snapshot=cell._cell_trial_snapshot(board)
    # Also refuse ordinary sites: otherwise a legal ordinary fallback should win.
    actual=cec_fr._via_spot_clear
    def restrict(*args,**kwargs):
        return args[2]<pcbnew.FromMM(.6) and actual(*args,**kwargs)
    with mock.patch.object(fab,'local_pofv_via_decision',return_value=(False,'test refusal')), \
         mock.patch.object(cec_fr,'_via_spot_clear',side_effect=restrict):
        result,error=add(board,pad)
    assert result is None and error
    assert copper_inventory(board)==before
    assert cell._cell_trial_snapshot(board)==snapshot
    pcbnew.SaveBoard(str(tmp_path/'after.kicad_pcb'),board)
    assert not list(pcbnew.LoadBoard(str(tmp_path/'after.kicad_pcb')).GetTracks())


def test_live_qualification_exception_leaves_no_native_trial():
    board,pad=fixture();before=copper_inventory(board)
    with mock.patch.object(fab,'local_pofv_via_decision',side_effect=RuntimeError('failed proof')):
        with pytest.raises(RuntimeError,match='failed proof'):
            add(board,pad)
    assert copper_inventory(board)==before


def test_locked_foreign_copper_remains_a_hard_obstacle():
    board,pad=fixture()
    net=pcbnew.NETINFO_ITEM(board,'FOREIGN_POWER');board.Add(net)
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(pcbnew.B_Cu)
    track.SetStart(pcbnew.VECTOR2I_MM(10,15));track.SetEnd(pcbnew.VECTOR2I_MM(20,15))
    track.SetWidth(pcbnew.FromMM(5));track.SetLocked(True);board.Add(track)
    before=copper_inventory(board);detail={}
    result,error=add(board,pad,diagnostics=detail)
    assert result is None and error
    assert copper_inventory(board)==before
    assert len(detail['compact_dogbone_attempts'])==2
    assert all(row['evidence']['dogbone_sites']<=64 for row in detail['compact_dogbone_attempts'])


def test_failing_neckdown_cannot_admit_compact_current_return():
    board,pad=fixture();before=copper_inventory(board)
    with mock.patch.object(cec_fr,'_qualified_endpoint_neckdown_tracks',
                           return_value=([],[{'reason':'not an endpoint neckdown'}])):
        # Force the wider class stub to fail too, exercising actual trial cleanup.
        actual=cec_fr._tap_foreign_clear
        def narrow(*args,**kwargs):
            return args[3]<=pcbnew.FromMM(.2) and actual(*args,**kwargs)
        with mock.patch.object(cec_fr,'_tap_foreign_clear',side_effect=narrow):
            result,error=add(board,pad)
    assert result is None and error
    assert copper_inventory(board)==before


def retained_via(board,pad,offset=.8):
    at=pad.GetPosition();via=pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(at.x+pcbnew.FromMM(offset),at.y))
    via.SetWidth(600000);via.SetDrill(300000);via.SetNetCode(pad.GetNetCode())
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLocked(True);board.Add(via)
    return via


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_nearby_real_ground_barrel_gets_short_class_width_link_without_duplicate_hole(layer):
    board,pad=fixture(layer=layer);via=retained_via(board,pad)
    identity=(via.m_Uuid.AsString(),tuple(via.GetPosition()),via.GetWidth(layer),
        via.GetDrillValue(),via.GetNetCode(),via.IsLocked())
    result=cell._reconnect_existing_ground_via(board,pad,reach_mm=.8,lock=True)
    assert result and result['status']=='reused-ground-barrel'
    assert all(t.GetClass()=='PCB_TRACK' for t in result['items'])
    assert len([t for t in board.GetTracks() if t.GetClass()=='PCB_VIA'])==1
    assert (via.m_Uuid.AsString(),tuple(via.GetPosition()),via.GetWidth(layer),
        via.GetDrillValue(),via.GetNetCode(),via.IsLocked())==identity
    assert all(t.GetWidth()>=cell._netclass(board,'GND')['width'] for t in result['items'])
    assert cell._existing_return(board,pad,.8) is not None


@pytest.mark.parametrize('fault',['remote','wrong_net','inner_foreign','bad_process','new_hole'])
def test_existing_ground_barrel_proximity_never_bypasses_qualification(fault):
    board,pad=fixture();via=retained_via(board,pad,offset=1.0 if fault=='remote' else .8)
    if fault in ('wrong_net','inner_foreign'):
        foreign=pcbnew.NETINFO_ITEM(board,'ARBITRARY_FOREIGN');board.Add(foreign)
        if fault=='wrong_net':via.SetNet(foreign)
        else:
            t=pcbnew.PCB_TRACK(board);at=via.GetPosition()
            t.SetStart(pcbnew.VECTOR2I(at.x-1000000,at.y));t.SetEnd(pcbnew.VECTOR2I(at.x+1000000,at.y))
            t.SetLayer(pcbnew.In2_Cu);t.SetWidth(1000000);t.SetNet(foreign);board.Add(t)
    elif fault=='bad_process':via.SetWidth(200000);via.SetDrill(150000)
    elif fault=='new_hole':
        other=retained_via(board,pad,offset=.95)
        other.SetPosition(pcbnew.VECTOR2I(via.GetPosition().x,via.GetPosition().y+100000))
    before=copper_inventory(board)
    assert cell._reconnect_existing_ground_via(board,pad,reach_mm=.8,lock=True) is None
    assert copper_inventory(board)==before


def test_retained_ground_reconnect_proof_exception_rolls_back_only_new_links():
    board,pad=fixture();retained_via(board,pad);before=copper_inventory(board)
    with mock.patch.object(cell,'_existing_return',side_effect=RuntimeError('proof failure')):
        with pytest.raises(RuntimeError,match='proof failure'):
            cell._reconnect_existing_ground_via(board,pad,reach_mm=.8,lock=True)
    assert copper_inventory(board)==before
