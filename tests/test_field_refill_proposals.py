"""Ordinary routing receives new barrels through actual private GND refill."""
import time

import pcbnew
import pytest

import cec_field_coupling as field
import cec_fr as fr
from test_field_proposals import add_net, native_ground_board, proposal, track
from test_lastmile import _board


def via(net='/CONTROL',at=(12,14),diameter=.6,drill=.3):
    return dict(net=net,at_nm=[round(v*1e6) for v in at],
        diameter_nm=round(diameter*1e6),drill_nm=round(drill*1e6),
        top_layer=int(pcbnew.F_Cu),bottom_layer=int(pcbnew.B_Cu))


def signature(board):
    tracks=[]
    for item in board.GetTracks():
        width=(item.GetWidth(item.TopLayer()) if item.GetClass()=='PCB_VIA'
               else item.GetWidth())
        tracks.append((item.m_Uuid.AsString(),item.GetClass(),item.GetNetname(),
            tuple(item.GetStart()),tuple(item.GetEnd()),width,bool(item.IsLocked())))
    zones=[(z.m_Uuid.AsString(),z.GetNetname(),tuple(z.GetLayerSet().CuStack()),
        z.IsFilled(),tuple((layer,z.GetFilledPolysList(layer).Format())
        for layer in z.GetLayerSet().CuStack())) for z in board.Zones()]
    return tracks,zones,board.GetFileName()


def ground_fixture(tmp_path):
    path,board=native_ground_board(tmp_path)
    # A second retained route really depends on the existing reference plane.
    track(board,'/PWM',(4,8),(20,8))
    track(board,'/CONTROL',(25,16),(25.1,16))
    pcbnew.SaveBoard(str(path),board)
    return path,pcbnew.LoadBoard(str(path))


def test_safe_new_barrel_is_received_without_mutating_source_or_fills(tmp_path):
    path,board=ground_fixture(tmp_path)
    before=signature(board);encoded=path.read_bytes()
    result=field.assess_proposed_route(board,[proposal('/CONTROL',(10,14),(12,14))],
        proposed_vias=[via()],board_path=path,deadline=time.monotonic()+5)
    assert result['complete'] and result['ok'] is True,result
    assert result['ground_zones_refilled_on_private_copy']>0
    assert result['prior_blocking_count']==result['final_blocking_count']==0
    assert result['proposed_via_count']==1 and result['release_authority'] is False
    assert result['board_mutated'] is False and signature(board)==before
    assert path.read_bytes()==encoded


def test_new_neutral_barrel_cut_cannot_launder_retained_shielding(tmp_path):
    path,board=ground_fixture(tmp_path)
    for zone in board.Zones():
        if zone.GetNetname()=='GND':
            zone.SetLocalClearance(pcbnew.FromMM(1));zone.UnFill()
    assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    before=signature(board)
    result=field.assess_proposed_route(board,[proposal('/CONTROL',(12,10),(12,8.85))],
        proposed_vias=[via(at=(12,8.85))],
        board_path=path,deadline=time.monotonic()+5)
    assert result['complete'] and result['ok'] is False,result
    assert result['prior_blocking_count']==0 and result['final_blocking_count']>0
    assert result['new_blockers'][0]['shield']['coverage_pct']<95
    assert set(result['new_blockers'][0]['nets'])=={'/ADC','/PWM'}
    assert signature(board)==before


def test_foreign_short_cannot_be_normalized_into_a_field_pass(tmp_path):
    path,board=ground_fixture(tmp_path);before=signature(board)
    result=field.assess_proposed_route(board,[proposal('/CONTROL',(12,10),(12,8.1))],
        proposed_vias=[via(at=(12,8.1),diameter=3,drill=2.6)],
        board_path=path,deadline=time.monotonic()+5)
    assert result['ok'] is not True and result['complete'] is False,result
    assert 'identity' in result['reason']
    assert signature(board)==before


def test_native_route_uses_supplied_netclass_and_preserves_inherited_debt():
    board=_board([],edge=(0,0,30,30))
    track(board,'/ADC',(5,6),(15,6));add_net(board,'/RENAMED')
    track(board,'/GATE',(5,20),(15,20));track(board,'/REF',(5,20.7),(15,20.7))
    before=signature(board)
    result=field.assess_proposed_route(board,[proposal('/RENAMED',(5,5.3),(15,5.3))],
        proposed_vias=[via('/RENAMED',at=(5,5.3))],
        netclass_resolver=lambda net:{'name':'Clock' if net=='/RENAMED' else 'Default'},
        deadline=time.monotonic()+5)
    assert result['complete'] and result['ok'] is False,result
    assert result['prior_blocking_count']==1 and result['final_blocking_count']==2
    assert len(result['new_blockers'])==1
    assert result['inherited_debt_qualified'] is False and signature(board)==before


@pytest.mark.parametrize('update',[
    {'net':'/ABSENT'},{'at_nm':[True,1]},{'at_nm':[1]},
    {'diameter_nm':True},{'drill_nm':0},{'drill_nm':600000},
    {'top_layer':int(pcbnew.In1_Cu)},{'bottom_layer':True},
])
def test_invalid_via_geometry_never_mutates_native_board(update):
    board=_board([],edge=(0,0,30,30));add_net(board,'/CONTROL')
    row=via();row.update(update);before=signature(board)
    result=field.assess_proposed_route(board,[proposal('/CONTROL',(10,14),(12,14))],
        proposed_vias=[row],deadline=time.monotonic()+5)
    assert result['ok'] is None and not result['complete']
    assert 'invalid' in result['reason'] and signature(board)==before


def test_timeout_and_failed_fill_are_unknown_not_admission(tmp_path,monkeypatch):
    path,board=ground_fixture(tmp_path);before=signature(board)
    track_rows=[proposal('/CONTROL',(10,14),(12,14))]
    expired=field.assess_proposed_route(board,track_rows,proposed_vias=[via()],deadline=0)
    assert expired['ok'] is None and not expired['complete']
    class FailedFill:
        def __init__(self,board):pass
        def Fill(self,zones):return False
    monkeypatch.setattr(pcbnew,'ZONE_FILLER',FailedFill)
    failed=field.assess_proposed_route(board,track_rows,proposed_vias=[via()],
        board_path=path,deadline=time.monotonic()+5)
    assert failed['ok'] is None and failed['reason']=='native_field_delta_ground_fill_refused'
    assert signature(board)==before


def test_live_router_constructs_and_receives_new_vias(monkeypatch):
    board=_board([(5,5,'/CONTROL'),(8,5,'/CONTROL')],edge=(0,0,15,15))
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda *a,**k:None)
    seen=[]
    def bridge(*args,**kwargs):
        net_code=board.GetNetcodeFromNetname('/CONTROL')
        start,end=pcbnew.VECTOR2I_MM(5,5),pcbnew.VECTOR2I_MM(8,5)
        ops=[('via',start,.3,.6),('via',end,.3,.6),
             ('trk',start,end,200000,pcbnew.B_Cu)]
        if kwargs['ops_ok'](ops):
            seen.append(net_code);return ops
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    board.BuildConnectivity()
    result=fr.synthesize_lastmile(board,include_nets=['/CONTROL'],max_mm=5,cap=1,
        attempts_per_pair=1,maze_max_mm=0,field_guard=True,wall_timeout_s=5,
        netclass_resolver=lambda net:{'name':'Default','track_width':.2,'clearance':.2})
    assert seen and result['closed']==1,result
    assert result['field_guard']['capabilities']['new_vias'] is True
    assert result['field_guard']['portfolio_preflight_skipped']==0
    assert sum(t.GetClass()=='PCB_VIA' for t in board.GetTracks())==2
    assert fr.net_connectivity_component_count(board,board.GetNetcodeFromNetname('/CONTROL'))==1


def test_live_router_unknown_native_refill_cannot_commit(monkeypatch):
    board=_board([(5,5,'/CONTROL'),(8,5,'/CONTROL')],edge=(0,0,15,15))
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda *a,**k:None)
    monkeypatch.setattr(field,'assess_native_additions',lambda *a,**k:
        dict(ok=None,complete=False,reason='test_refill_missing'))
    def bridge(*args,**kwargs):
        start,end=pcbnew.VECTOR2I_MM(5,5),pcbnew.VECTOR2I_MM(8,5)
        ops=[('via',start,.3,.6),('via',end,.3,.6),
             ('trk',start,end,200000,pcbnew.B_Cu)]
        return ops if kwargs['ops_ok'](ops) else None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    board.BuildConnectivity();before=signature(board)
    result=fr.synthesize_lastmile(board,include_nets=['/CONTROL'],max_mm=5,cap=1,
        attempts_per_pair=1,maze_max_mm=0,field_guard=True,wall_timeout_s=5,
        netclass_resolver=lambda net:{'track_width':.2,'clearance':.2})
    assert result['closed']==0 and result['field_guard']['unknown']>0
    assert signature(board)==before
