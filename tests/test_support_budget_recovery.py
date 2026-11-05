"""One timed-out target may reclaim unused support leases, never extra time."""
import pcbnew
import pytest
import cec_certificate_repair as repair


def native_fixture(tmp_path, translated=False):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    target_net='/RENAMED' if translated else '/TARGET'
    support_net='/RETURN_OTHER' if translated else '/RETURN'
    nets={name:pcbnew.NETINFO_ITEM(board,name) for name in (target_net,support_net)}
    for net in nets.values():board.Add(net)
    ref='OTHER_CELL' if translated else 'CELL'
    owner=pcbnew.FOOTPRINT(board);owner.SetReference(ref)
    origin=pcbnew.VECTOR2I_MM(37,-14) if translated else pcbnew.VECTOR2I_MM(10,10)
    owner.SetPosition(origin);board.Add(owner)
    for index in range(4):
        pad=pcbnew.PAD(owner);pad.SetNumber(str(index+1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.6,.4))
        pad.SetPosition(origin+pcbnew.VECTOR2I_MM(0,index))
        pad.SetNet(nets[target_net if index==0 else support_net]);owner.Add(pad)
    if translated:owner.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    path=str(tmp_path/'board.kicad_pcb');pcbnew.SaveBoard(path,board)
    target=repair.asdict(repair.FootprintRepairTarget(ref=ref,target_net=target_net,
        endpoint_ref='REMOTE',endpoint_pad='1',endpoint_x_mm=origin.x/1e6+4,
        endpoint_y_mm=origin.y/1e6,hit_count=1,distance_mm=4,priority=(0,)))
    anchors=[dict(ref=ref,pad=str(i+1),net=support_net,
        x_mm=origin.x/1e6+4,y_mm=origin.y/1e6+i,track_uuid='boundary-'+str(i))
        for i in range(1,4)]
    return path,target,dict(preserved_anchors=anchors,affected_nets=[support_net])


def run(tmp_path,monkeypatch,*,translated=False,refusal='certificate_pair_search_timeout',
        target_success=False,retry_success=True,support_success=True,support_time=.25,
        options=None,missing_support=False):
    path,target,move=native_fixture(tmp_path,translated)
    if missing_support:move['preserved_anchors'][-1]['ref']='ABSENT'
    clock=[100.];calls=[];target_calls=[]
    def close(_board,window,**kwargs):
        allowance=kwargs['wall_timeout_s'];elapsed=clock[0]-100.
        assert 0<allowance<=35.-elapsed+1e-9
        calls.append((window,allowance))
        if window.net==target['target_net']:
            target_calls.append((window,allowance))
            clock[0]+=allowance
            success=target_success if len(target_calls)==1 else retry_success
            return success,dict(closed=int(success),refusal=refusal,
                timed_out=refusal=='certificate_pair_search_timeout')
        clock[0]+=min(support_time,allowance)
        return support_success,dict(closed=int(support_success),refusal='support_refused')
    monkeypatch.setattr(repair.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(repair,'_close_certificate_component_pair',close)
    monkeypatch.setattr(repair,'_save_with_reconciled_endpoint_neckdowns',lambda *_:None)
    # Explicit equal-share ablation exercises the older recovery mechanism;
    # default critical-first behavior has independent scheduling regressions.
    report=repair._exact_relocated_connections_worker(path,target,move,35.,
        **({'target_budget_fraction':0.0} | (options or {})))
    assert clock[0]-100.<=35.+1e-9
    return report,calls,target_calls


@pytest.mark.parametrize('translated',[False,True])
@pytest.mark.parametrize('success',[False,True])
def test_larger_single_retry_uses_same_islands_and_one_budget(tmp_path,monkeypatch,translated,success):
    report,calls,target_calls=run(tmp_path,monkeypatch,translated=translated,retry_success=success)
    recovery=report['target_budget_recovery']
    assert recovery['attempted'] and recovery['wall_budget_s']==20.
    assert recovery['initial_budget_s']==8.75
    assert report['support_expected']==report['support_closed']==3
    assert len(target_calls)==2 and len(calls)==5
    assert target_calls[0][0]==target_calls[1][0]
    assert calls[-1][0].net==target_calls[0][0].net
    assert report['target_closed'] is success
    assert len([r for r in report['refused'] if r['role']=='target'])==int(not success)
    assert len([r for r in report['closed_details'] if r['role']=='target'])==int(success)
    assert recovery['initial_completion']['refusal']=='certificate_pair_search_timeout'
    assert not recovery['release_authority']


@pytest.mark.parametrize('kwargs,stop',[
    (dict(options={'recover_target_budget':False}),'disabled'),
    (dict(target_success=True),'target_closed_or_not_timed_out'),
    (dict(refusal='certificate_pair_no_exact_clear_path'),'target_closed_or_not_timed_out'),
    (dict(refusal='certificate_endpoint_not_live'),'target_closed_or_not_timed_out'),
    (dict(support_success=False),'support_restoration_incomplete'),
    (dict(missing_support=True),'support_restoration_incomplete'),
    (dict(support_time=8.),'no_larger_remaining_lease'),
    (dict(options={'pair_budget_cap_s':8.75}),'no_larger_remaining_lease'),
])
def test_no_unsupported_or_identical_retry(tmp_path,monkeypatch,kwargs,stop):
    report,_calls,target_calls=run(tmp_path,monkeypatch,**kwargs)
    assert len(target_calls)==1
    assert not report['target_budget_recovery']['attempted']
    assert report['target_budget_recovery']['stop']==stop


@pytest.mark.parametrize('kwargs',[
    dict(wall_timeout_s=0),dict(wall_timeout_s=float('nan')),
    dict(recover_target_budget=1),dict(pair_budget_cap_s=0),
    dict(pair_budget_cap_s=121),dict(pair_budget_cap_s=float('inf')),
    dict(recovery_min_gain_s=0),dict(recovery_min_gain_s=float('nan')),
    dict(target_budget_fraction=-.1),dict(target_budget_fraction=.91),
    dict(target_budget_fraction=float('nan')),dict(target_budget_fraction=True),
])
def test_invalid_limits_fail_before_loading_a_board(kwargs):
    with pytest.raises(ValueError,match='budgets'):
        repair._exact_relocated_connections_worker('unused',{}, {},**kwargs)
