"""An empty proved field inventory needs no run history; active fields do."""
import time
import pcbnew
import pytest
import cec_field_search as search
import cec_fr as fr
from unittest import mock
from test_field_search import fixture


@pytest.mark.parametrize('turn',[0,1,2,3])
@pytest.mark.parametrize('back,mirror',[(False,False),(True,False),(False,True)])
def test_active_callback_keeps_complete_accumulated_parallel_run_checks(turn,back,mirror):
    b,point,_,layer,t=fixture(turn=turn,back=back,mirror=mirror,offset=(23,-7))
    before=(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),force_id(t))
    guard=search.PlanarSearchGuard(b,'renamed-PWM-control');callback=guard.multilayer_callback()
    assert guard.active and callable(callback)
    for start in (10,10.5,11,11.5,12,12.5,13,13.5):
        assert callback(tuple(point(start,10)),tuple(point(start+.5,10)),200000,layer)
    assert not callback(tuple(point(10,10)),tuple(point(14,10)),200000,layer)
    assert callback(tuple(point(10,10)),tuple(point(10,14)),200000,layer)
    assert before==(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),force_id(t))
    assert guard.report()['retained_relation_segments']==1 and not guard.report()['release_authority']


def force_id(item):return item.m_Uuid.AsString()


@pytest.mark.parametrize('own,peer',[('+5V','renamed-SENSE-input'),('neutral-line','renamed-SENSE-input'),
    ('renamed-SENSE-input','renamed-SENSE-input'),('/USB_D_P','/USB_D_N')])
def test_callback_none_requires_an_actually_empty_native_relation_inventory(own,peer):
    b,_,_,_,_=fixture(victim=peer);guard=search.PlanarSearchGuard(b,own)
    assert guard.rows==[] and not guard.active
    assert guard.multilayer_callback() is None
    assert not guard.report()['shielding_qualified'] and not guard.report()['release_authority']


@pytest.mark.parametrize('active',[False,True])
def test_maze_activates_history_exactly_when_native_field_relations_require_it(active):
    b,point,_,layer,_=fixture();own='renamed-PWM-control' if active else '+5V'
    net=pcbnew.NETINFO_ITEM(b,own);b.Add(net)
    guard=search.PlanarSearchGuard(b,own);detail={}
    ops=fr._multilayer_maze_lastmile_ops(b,point(10,8),point(14,8),net.GetNetCode(),[layer],200000,
        lambda *args:True,width_for_layer=lambda _:.2*1000000,start_layers=[layer],end_layers=[layer],
        grid_mm=.5,max_vias=0,allow_single_layer=True,deadline_monotonic=time.monotonic()+1.,
        planar_guard=guard.multilayer_callback(),neutral_state_dominance=True,field_state_dominance=True,diagnostics=detail)
    assert ops
    assert detail['field_state_memory_preserved'] is active
    assert detail['neutral_state_dominance_active'] is not active
    assert detail['field_state_dominance_active'] is active


@pytest.mark.parametrize('active',[False,True])
def test_production_displaced_restore_does_not_invent_field_history_for_dc(active):
    import cec_certificate_repair as repair
    import cec_route_proposal_guard as proposals
    b,point,nets,layer,_=fixture();net='renamed-PWM-control' if active else '+5V'
    if net not in nets:b.Add(pcbnew.NETINFO_ITEM(b,net))
    snapshot=dict(start=point(10,8),end=point(14,8),width=200000,layer=layer,
        net_code=b.GetNetcodeFromNetname(net),net=net,requested_uuid='synthetic-scope',removed_uuids=[],source_length_nm=4000000)
    proposal=mock.Mock();proposal.report.return_value={}
    with mock.patch.object(proposals,'RouteProposalGuard',return_value=proposal), \
            mock.patch.object(fr,'_project_netclass_resolver',return_value=lambda n:dict(name='Default',clearance=.2)), \
            mock.patch.object(fr,'_guarded_profiled_lastmile_legs',return_value=None) as planar, \
            mock.patch.object(fr,'_maze_lastmile_legs',return_value=None), \
            mock.patch.object(fr,'_lastmile_bridge',return_value=None) as bridge:
        okay,_=repair._restore_displaced_branch(b,snapshot,board_path='synthetic.kicad_pcb',maze_margin_mm=2.,deadline_monotonic=time.monotonic()+1.)
    assert not okay
    actual=bridge.call_args.kwargs['planar_guard']
    assert (actual is not None) is active
    if active:assert actual.active and actual.rows
    # The ordinary edge callback also stays callable when no field peer
    # exists; a no-peer optimization must not break same-layer restoration.
    assert planar.call_args.args[7](point(10,8),point(11,8),100000)
