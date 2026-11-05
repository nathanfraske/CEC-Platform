"""Bounded two-hop proposal order changes do not freeze a bad supply prefix."""
import copy

import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_force_current as force
import cec_joint_route_negotiation as subject


def fixture(monkeypatch,quarter=0,back=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    board.GetDesignSettings().m_TrackMinWidth=200000
    board.GetDesignSettings().m_MinClearance=200000
    for name in ('GND','SYNTHETIC_RAIL'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    face=int(pcbnew.B_Cu if back else pcbnew.F_Cu)
    def point(x,y):
        for _ in range(quarter):x,y=y,20-x
        if back:x=20-x
        return [round(x*1e6),round(y*1e6)]
    def endpoint(ref,at,net):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
        mask=pcbnew.LSET();mask.AddLayer(face);pad.SetLayerSet(mask);pad.SetNet(board.FindNet(net))
        pad.SetPosition(pcbnew.VECTOR2I(*point(*at)));fp.Add(pad)
        return dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[face])
    ground=endpoint('RENAMABLE_LOW_POWER_GROUND',(10,10),'GND')
    a=endpoint('RENAMABLE_STRAP_A',(9,10.7),'SYNTHETIC_RAIL')
    b=endpoint('RENAMABLE_STRAP_B',(11.6,10.7),'SYNTHETIC_RAIL')
    c=endpoint('RENAMABLE_BYPASS_A',(10.8,9),'SYNTHETIC_RAIL')
    d=endpoint('RENAMABLE_BYPASS_B',(10.8,11.8),'SYNTHETIC_RAIL')
    def edge(start,end):return ['trk',point(*start),point(*end),200000,face]
    requests={'a_strap':dict(kind='source_boundary',net='SYNTHETIC_RAIL',a=a,b=b,width_nm=200000),
        'b_ground':dict(kind='ground',net='GND',a=ground,reach_mm=1.5),
        'z_local':dict(kind='local_supply',net='SYNTHETIC_RAIL',a=c,b=d,width_nm=200000)}
    def choice(uid,net,ops,cost=1):return dict(id=uid,cost=cost,net=net,ops=ops,clearance_nm=200000)
    domains={'a_strap':[choice('held_strap','SYNTHETIC_RAIL',[edge((9,10.7),(11.6,10.7))])],
        'b_ground':[choice('lower_original','GND',[edge((10,10),(10,11.2)),['via',point(10,11.2),.3,.6]]),
            choice('right_original','GND',[edge((10,10),(11.2,10)),['via',point(11.2,10),.3,.6]],cost=2)],
        'z_local':[choice('held_local','SYNTHETIC_RAIL',[edge((10.8,9),(10.8,11.8))])]}
    for start,end in (((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))):
        item=pcbnew.PCB_SHAPE();item.SetShape(pcbnew.SHAPE_T_SEGMENT);item.SetLayer(pcbnew.Edge_Cuts)
        item.SetStart(pcbnew.VECTOR2I(*point(*start)));item.SetEnd(pcbnew.VECTOR2I(*point(*end)));board.Add(item)
    monkeypatch.setattr(escape.cell,'_netclass',lambda *args:dict(width=200000,clearance=200000,via_dia=.6,via_drill=.3))
    contract=dict(current_authority={'source':'explicit_synthetic_fixture_only','amps':.01},
        required_by_layer_nm={int(layer):200000 for layer in board.GetEnabledLayers().CuStack()})
    requests['a_strap']['unchanged_full_rail_current_contract']=copy.deepcopy(contract)
    monkeypatch.setattr(escape.cell,'_supply_current_widths',lambda *args:copy.deepcopy(contract))
    # Both original Ground alternatives must clear ACTUAL native Source
    # pads/edges, not merely the other generated choices. No unsafe anchor
    # can be made plausible by the injected Ground-menu refusal below.
    code=board.GetNetcodeFromNetname('GND')
    for choice in domains['b_ground']:
        for op in choice['ops']:
            if op[0]=='trk':
                assert escape.fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*op[1]),
                    pcbnew.VECTOR2I(*op[2]),op[3],op[4],200000,{code})
            else:
                assert escape.fr._via_spot_clear(board,pcbnew.VECTOR2I(*op[1]),600000,
                    200000,{code},drill_nm=300000,net_code=code,report={})
    packet=dict(domains=domains,source_native_binding=escape.row._source_binding(board))
    failed=escape.choose(board,packet)
    assert not failed['complete']
    failure=failed['failure_frontier'][0]
    assert failure['obligation']=='z_local' and failure['assigned']['b_ground']=='right_original'
    assert failure['assigned']['a_strap']=='held_strap'
    return board,packet,requests,failed


def producer(monkeypatch,*,raise_on_strap=False):
    real=escape.menus;calls=[]
    def run(board,requests,**options):
        calls.append(dict(keys=set(requests),native_tracks=[
            (t.GetNetname(),tuple(t.GetStart()),tuple(t.GetEnd()))for t in board.GetTracks()
            if t.GetClass()=='PCB_TRACK']))
        if set(requests)=={'b_ground'}:
            # Inject only a bounded Ground producer refusal, not success or
            # native/cut/current admission. The alternate strap still uses
            # the actual native guarded route producer and final selector.
            return dict(domains={'b_ground':[]},diagnostics={'b_ground':{'finite_fixture_ground_refusal':True}})
        if raise_on_strap:raise ValueError('injected_cycle_strap_producer_failure')
        return real(board,requests,**options)
    monkeypatch.setattr(escape,'menus',run)
    return calls


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_old_ground_alternative_replans_only_the_actual_conflicting_strap(monkeypatch,quarter,back):
    board,packet,requests,failed=fixture(monkeypatch,quarter,back);calls=producer(monkeypatch)
    old=copy.deepcopy(packet);binding=escape.row._source_binding(board);snapshot=escape.cell._cell_trial_snapshot(board)
    result=subject.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',
        timeout_s=2,max_actions=2)
    actions=result['cooperative_conflict_cluster']['actions']
    assert len(actions)==2 and actions[0]['obligation']=='b_ground',actions
    cycle=actions[1]
    assert cycle['negotiation_basis']=='assigned_ground_alternate_conflict_cycle'
    assert cycle['anchor_obligation']=='b_ground' and cycle['anchor_choice_id']=='lower_original'
    assert cycle['obligation']=='a_strap' and cycle['added_choices']>0,cycle
    assert cycle['failure_frontier_assigned_choices']==failed['failure_frontier'][0]['assigned']
    assert cycle['proposed_cycle_context_choices']['z_local']=='held_local'
    assert 'z_local'not in cycle['failure_frontier_assigned_choices']
    assert {'b_ground','z_local'}<=set(cycle['held_obligations'])
    assert cycle['held_anchor_ground_request_closure']==['b_ground']
    assert [q['keys']for q in calls]==[{'b_ground'},{'a_strap'}]
    assert {q[0]for q in calls[1]['native_tracks']}=={'GND','SYNTHETIC_RAIL'}
    assert result['domains']['b_ground']==old['domains']['b_ground']
    assert result['domains']['z_local']==old['domains']['z_local']
    assert all(q in result['domains']['a_strap']for q in old['domains']['a_strap'])
    assert escape.choose(board,result)['complete']
    assert packet==old and escape.row._source_binding(board)==binding and escape.cell._cell_trial_snapshot(board)==snapshot


def test_more_local_choices_do_not_starve_the_distinct_conflict_cycle(monkeypatch):
    board,packet,requests,failed=fixture(monkeypatch)
    original=packet['domains']['z_local'][0]
    a,b=original['ops'][0][1:3];face=original['ops'][0][4]
    for index in range(1,4):
        delta=index*50000
        path=[a,[a[0]+delta,a[1]+delta],[b[0]+delta,b[1]-delta],b]
        candidate=dict(original,id='distinct_local_'+str(index),cost=1+index,
            ops=[['trk',start,end,200000,face]for start,end in zip(path,path[1:])])
        packet['domains']['z_local'].append(candidate)
    failed=escape.choose(board,packet);assert not failed['complete']
    calls=producer(monkeypatch)
    result=subject.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',
        timeout_s=2,max_actions=2)
    actions=result['cooperative_conflict_cluster']['actions']
    assert len(actions)==2
    assert actions[0]['obligation']=='b_ground'
    assert actions[1]['negotiation_basis']=='assigned_ground_alternate_conflict_cycle'
    assert actions[1]['obligation']=='a_strap'and actions[1]['added_choices']>0
    assert [q['keys']for q in calls]==[{'b_ground'},{'a_strap'}]
    assert escape.choose(board,result)['complete']


@pytest.mark.parametrize('fault',['required_pivot','required_target','budget','forged_assignment','producer_exception','stale_packet'])
def test_cycle_cannot_waive_required_copper_work_bound_or_source_identity(monkeypatch,fault):
    board,packet,requests,failed=fixture(monkeypatch)
    if fault=='required_pivot':requests['b_ground']['required_projected_ground_entry']={'required':True}
    elif fault=='required_target':requests['a_strap']['required_projected_ground_entry']={'required':True}
    elif fault=='forged_assignment':failed['failure_frontier'][0]['assigned']['a_strap']='not_real'
    elif fault=='stale_packet':packet['source_native_binding']='stale'
    calls=producer(monkeypatch,raise_on_strap=fault=='producer_exception')
    old=copy.deepcopy(packet);binding=escape.row._source_binding(board);snapshot=escape.cell._cell_trial_snapshot(board)
    if fault in ('forged_assignment','producer_exception','stale_packet'):
        with pytest.raises(ValueError):
            subject.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',timeout_s=2,max_actions=2)
    else:
        result=subject.propose(board,packet,requests,failed,board_path='opaque',board_hint='opaque',
            timeout_s=2,max_actions=1 if fault=='budget'else 2)
        assert result['domains']==old['domains'] and not escape.choose(board,result)['complete']
        assert all(q['keys']!={'a_strap'}for q in calls)
    assert packet==old and escape.row._source_binding(board)==binding and escape.cell._cell_trial_snapshot(board)==snapshot
