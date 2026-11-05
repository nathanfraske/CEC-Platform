import time
import pcbnew
import pytest

import cec_measurement_leaf as leaf
import cec_measurement_leaf_bridge as bridge
import cec_force_current as force
from cec_native_items import discard_items
from test_measurement_leaf import fixture


@pytest.mark.parametrize('name,quarter',[('changed_A',0),('/different/rail',1),('+5V_MAIN',2)])
def test_layer_bridge_cannot_acquire_same_net_force_copper(name,quarter):
    board,pad,anchor,tracks,xy=fixture(name,quarter)
    q=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    before=leaf._binding(board)
    guard=bridge.compile_contact_guard(board,q,deadline=time.monotonic()+10)
    s,t=xy((11,10)),xy((19,10))
    assert guard['planar'](s,t,200000,pcbnew.B_Cu)
    force_track=pcbnew.PCB_TRACK(board);force_track.SetLayer(pcbnew.B_Cu)
    force_track.SetStart(xy((15,8)));force_track.SetEnd(xy((15,12)))
    force_track.SetWidth(1000000);force_track.SetNetCode(pad.GetNetCode());board.Add(force_track)
    guard=bridge.compile_contact_guard(board,q,deadline=time.monotonic()+10)
    assert not guard['planar'](s,t,200000,pcbnew.B_Cu)
    assert not guard['barrel'](xy((15,10)),600000)
    assert not guard['operations']([('trk',s,t,200000,pcbnew.B_Cu)])
    assert guard['counts']['refused_contacts']==3
    discard_items(board,[force_track]);assert leaf._binding(board)==before


def test_foreign_surface_barrier_uses_legal_nonplane_layer_without_editing_source():
    board,pad,anchor,tracks,xy=fixture('arbitrary')
    q=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    foreign=pcbnew.NETINFO_ITEM(board,'unrelated');board.Add(foreign)
    barrier=pcbnew.PCB_TRACK(board);barrier.SetLayer(pcbnew.F_Cu)
    barrier.SetStart(xy((15,1)));barrier.SetEnd(xy((15,29)))
    barrier.SetWidth(200000);barrier.SetNet(foreign);board.Add(barrier)
    before=leaf._binding(board)
    result=bridge.search(board,q,timeout_s=3)
    assert result['ops'] and any(op[0]=='via' for op in result['ops'])
    assert not result['kelvin_qualified'] and not result['routing_admitted']
    assert leaf._binding(board)==before


def test_source_ground_scope_missing_pickup_and_changed_input_fail_closed():
    board,pad,anchor,tracks,xy=fixture()
    q=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    with pytest.raises(ValueError,match='source_typed_measurement_leaf'):
        bridge.compile_contact_guard(board,dict(q,scope='source_typed_thin_device_ground_leaf'),deadline=time.monotonic()+10)
    with pytest.raises(ValueError,match='exact_retained_measurement_pickup_missing'):
        bridge.compile_contact_guard(board,dict(q,boundary_uuids=['worker_made_up']),deadline=time.monotonic()+10)
    q['points_nm'][0]=[1,2]
    with pytest.raises(ValueError,match='measurement_land_binding'):
        bridge.compile_contact_guard(board,q,deadline=time.monotonic()+10)


@pytest.mark.parametrize('quarter',range(4))
def test_source_channel_suffix_is_new_guarded_copper_not_an_existing_anchor(monkeypatch,quarter):
    board,pad,anchor,tracks,xy=fixture('renamed_source_channel',quarter)
    q=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    before=leaf._binding(board);calls=[]
    def bridge_producer(board,a,al,b,bl,width,code,layers,gap,**kw):
        calls.append(tuple(b))
        candidate=[('trk',tuple(a),tuple(b),width,pcbnew.F_Cu)]
        return candidate if kw['ops_ok'](candidate) else None
    monkeypatch.setattr(bridge.fr,'_lastmile_bridge',bridge_producer)
    result=bridge.search(board,q,timeout_s=2)
    assert calls==[tuple(xy((15,10)))]
    assert len(result['ops'])==2
    assert result['ops'][-1][1:3]==(tuple(xy((15,10))),tuple(xy((20,10))))
    assert result['diagnostics']['source_channel_trials'][0]['replayed_source_segments']==1
    assert before==leaf._binding(board) and not result['routing_admitted']


def test_source_channel_replay_cannot_acquire_a_new_same_net_pickup(monkeypatch):
    import cec_native_via_frontier as frontier
    board,pad,anchor,tracks,xy=fixture('changed_channel')
    q=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    bus=pcbnew.PCB_TRACK(board);bus.SetStart(xy((17,8)));bus.SetEnd(xy((17,12)))
    bus.SetWidth(1000000);bus.SetLayer(pcbnew.F_Cu);bus.SetNetCode(pad.GetNetCode());board.Add(bus)
    calls=[]
    def refuse(board,a,al,b,*args,**kwargs):calls.append(tuple(b));return None
    monkeypatch.setattr(bridge.fr,'_lastmile_bridge',refuse)
    monkeypatch.setattr(frontier,'sites',lambda *args,**kwargs:dict(sites_nm=[]))
    before=leaf._binding(board);result=bridge.search(board,q)
    assert calls==[tuple(xy((20,10)))] and not result['ops']
    assert before==leaf._binding(board)


@pytest.mark.parametrize('quarter',range(4))
def test_expensive_native_portal_cannot_starve_next_guarded_portal(monkeypatch,quarter):
    import cec_native_via_frontier as frontier
    board,pad,anchor,tracks,xy=fixture('arbitrary_fair_portfolio',quarter)
    q=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    before=leaf._binding(board);clock=[100.];calls=[]
    monkeypatch.setattr(bridge.time,'monotonic',lambda:clock[0])
    sites=[list(xy((14,12))),list(xy((16,12)))]
    monkeypatch.setattr(frontier,'sites',lambda *a,**kw:
        dict(sites_nm=sites,drill_mm=.3,diameter_mm=.6))
    def guarded_stub(board,a,b,width,layer,gap,code,leg_ok,**kw):
        s,t=tuple(a),tuple(b)
        return [(s,t,width)] if leg_ok(a,b,width/2) else None
    monkeypatch.setattr(bridge.fr,'_guarded_profiled_lastmile_legs',guarded_stub)
    def producer(board,a,al,b,bl,width,code,layers,gap,**kw):
        if not kw['allow_maze']:
            clock[0]=kw['deadline_monotonic'];return None
        calls.append((tuple(b),clock[0],kw['deadline_monotonic']))
        assert kw['_multilayer_pair_limit']==2 and kw['_multilayer_only'] and kw['multilayer_lays']
        assert kw['middle_native_board_envelope'] and kw['middle_grid_mm']==.4
        if len(calls)==1:
            clock[0]=kw['deadline_monotonic']+.001;return None
        candidate=[('trk',tuple(a),tuple(b),width,pcbnew.F_Cu)]
        return candidate if kw['ops_ok'](candidate) else None
    monkeypatch.setattr(bridge.fr,'_lastmile_bridge',producer)
    result=bridge.search(board,q,timeout_s=10)
    assert len(calls)==2 and calls[0][2]<calls[1][2]<=110
    assert result['ops'] and any(op[0]=='via' for op in result['ops'])
    assert result['diagnostics']['native_frontier_ready_portals']==2
    assert result['diagnostics']['native_frontier_trials'][1]['found']
    assert bridge.compile_contact_guard(board,q,deadline=111)['operations'](result['ops'])
    assert before==leaf._binding(board) and not result['routing_admitted']


def test_untrusted_portal_does_not_bypass_full_barrel_contact_guard(monkeypatch):
    import cec_native_via_frontier as frontier
    board,pad,anchor,tracks,xy=fixture('arbitrary_refused_portal')
    q=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    bus=pcbnew.PCB_TRACK(board);bus.SetStart(xy((17,8)));bus.SetEnd(xy((17,12)))
    bus.SetWidth(1000000);bus.SetLayer(pcbnew.B_Cu);bus.SetNetCode(pad.GetNetCode());board.Add(bus)
    before=leaf._binding(board);calls=[]
    monkeypatch.setattr(frontier,'sites',lambda *a,**kw:
        dict(sites_nm=[list(xy((17,10)))],drill_mm=.3,diameter_mm=.6))
    monkeypatch.setattr(bridge.fr,'_guarded_profiled_lastmile_legs',
        lambda board,a,b,width,*args,**kw:[(tuple(a),tuple(b),width)])
    def refuse(board,*args,**kw):
        if kw['allow_maze']:calls.append(args)
        return None
    monkeypatch.setattr(bridge.fr,'_lastmile_bridge',refuse)
    result=bridge.search(board,q,timeout_s=2)
    assert not result['ops'] and not calls
    assert result['diagnostics']['native_frontier_ready_portals']==0
    assert result['contact_guard']['refused_contacts']>0
    assert before==leaf._binding(board) and not result['no_path_proof']
