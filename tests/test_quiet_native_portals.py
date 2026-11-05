"""Typed quiet ports may change search order, never their receiving authority."""
from types import SimpleNamespace
import pcbnew
import pytest
import cec_quiet_signal_completion as op
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
from test_quiet_signal_requests import fixture


def target_for(board, proposal):
    return dict(target_net=proposal['net'],width_mm=proposal['request']['width_nm']/1e6,
        clearance_mm=proposal['request']['clearance_nm']/1e6,
        route_endpoints=[dict(uuid=force._uid(p),kind='pad',x_mm=p.GetPosition().x/1e6,
            y_mm=p.GetPosition().y/1e6)for p in op._pads(board,proposal['request'])])


@pytest.mark.parametrize('strategy',[None,True,'invented',7])
def test_unknown_portfolio_cannot_launch_or_write(strategy):
    with pytest.raises(ValueError,match='geometry_strategy'):
        op.construct_private('missing','missing',{'net':'/N'},board_hint='opaque',strategy=strategy)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',[0,1])
@pytest.mark.parametrize('fail_first',[False,True])
def test_native_portal_dispatch_retains_exact_saved_quiet_receiver(tmp_path,monkeypatch,back,quarter,fail_first):
    # Only the path proposer is substituted. Saved native connectivity,
    # source/package typing, literal net and the actual quiet receiver run.
    import cec_route_proposal_guard as guards
    import cec_field_search as search
    board,source,root,*_=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    board.SetCopperLayerCount(6);field._save_field_snapshot(board,source)
    proposal=op.plan(board,source,board_hint=str(root),net='/renamed_quiet');assert proposal['complete']
    candidate=force._copy_family(source,tmp_path/'private')
    captured=[]
    class Guard:
        def __init__(self,*a,**k):self.counts={};captured.append(('guard',k))
        def __call__(self,ops):captured.append(('final_guard',len(ops)));return True
    monkeypatch.setattr(guards,'RouteProposalGuard',Guard)
    monkeypatch.setattr(search,'PlanarSearchGuard',lambda *a,**k:SimpleNamespace(active=False))
    monkeypatch.setattr(fr,'_lastmile_route_layers',lambda b,**k:[pcbnew.In2_Cu] if k['exclude_front']else[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
    def bridge(b,A,al,B,bl,width,nc,layers,clearance,**kwargs):
        captured.append(('bridge',kwargs));assert al==bl
        call=sum(k=='bridge'for k,_ in captured)
        expected=op._pads(b,proposal['request'])[1 if call==1 else 0]
        assert A==tuple(expected.GetPosition())
        if fail_first and call==1:return None
        # Fixture endpoints lie on one native straight axis in every pose.
        assert A[0]==B[0] or A[1]==B[1]
        return [('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,next(iter(al)))]
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    before=source.read_bytes()
    result=op._native_portal_worker(candidate,target_for(board,proposal),5.)
    assert result['closed']==1 and result['components_after']<result['components_before']
    kw=next(v for k,v in captured if k=='bridge')
    assert kw['native_endpoint_seeds'] and kw['_multilayer_only'] and kw['middle_native_board_envelope']
    assert kw['canonical_turns_only'] and kw['obstacle_channel_axes'] and kw['middle_max_vias']==2
    assert kw['search_wall_cap_s']==10. and kw['max_expanded_states']==50000
    assert any(k=='final_guard'for k,_ in captured)
    searches=[v for k,v in captured if k=='bridge']
    assert len(searches)==(2 if fail_first else 1)
    assert len({v['deadline_monotonic']for v in searches})==1
    assert [d['launch']for d in result['directions']]==(['input_first','output_first']if fail_first else['input_first'])
    proof=op.receive(source,candidate,board_hint=str(root),net=proposal['net'])
    assert proof['ok'] and proof['whole_shared_stage_still_required'],proof
    assert source.read_bytes()==before and not result['release_authority']


@pytest.mark.parametrize('fault',['stale_uuid','wrong_net','wrong_position','below_width','below_clearance','wrong_class'])
def test_native_ports_reject_stale_or_underqualified_search_targets_before_mutation(tmp_path,monkeypatch,fault):
    board,source,root,tree,spec,*_=fixture(tmp_path,monkeypatch)
    proposal=op.plan(board,source,board_hint=str(root),net='/renamed_quiet')
    candidate=force._copy_family(source,tmp_path/'private');target=target_for(board,proposal)
    if fault=='stale_uuid':target['route_endpoints'][0]['uuid']='invented'
    elif fault=='wrong_net':target['target_net']='+3V3'
    elif fault=='wrong_position':target['route_endpoints'][0]['x_mm']+=.001
    elif fault=='below_width':target['width_mm']=.05
    elif fault=='below_clearance':target['clearance_mm']=.05
    else:spec['name']='Default'
    before=candidate.read_bytes()
    with pytest.raises(ValueError):op._native_portal_worker(candidate,target,5.)
    assert candidate.read_bytes()==before


@pytest.mark.parametrize('seconds',[True,0,-1,11,float('nan'),float('inf')])
def test_native_portal_search_cannot_reset_or_extend_ten_second_lease(seconds):
    with pytest.raises(ValueError,match='bounded_quiet_signal_work_lease'):
        op._native_portal_worker('missing',{},seconds)


def test_existing_constructor_recompiles_scope_before_dispatching_new_search(tmp_path,monkeypatch):
    import cec_certificate_repair as repair
    board,source,root,*_=fixture(tmp_path,monkeypatch)
    candidate=force._copy_family(source,tmp_path/'private');seen=[]
    def refuse(worker,args,**kwargs):
        seen.append((worker,args,kwargs));return {'closed':0}
    monkeypatch.setattr(repair,'_spawn_apply',refuse)
    proof=op.construct_private(source,candidate,{'net':'/renamed_quiet'},board_hint=str(root),strategy='native_portals')
    assert not proof['complete'] and proof['geometry_strategy']=='native_portals'
    assert seen[0][0] is op._native_portal_worker and seen[0][1][2]<=10.
    assert seen[0][2]['search_budget_arg']==2
    target=seen[0][1][1]
    assert target['source_local_pad_rule_launches']is True
    assert target['retained_same_face_track_ends']and target['retained_barrel_face_access']
    assert target['width_mm']==proposal_width(source,root,proposal_net='/renamed_quiet')


def proposal_width(source,root,*,proposal_net):
    import pcbnew
    return op.plan(pcbnew.LoadBoard(str(source)),source,board_hint=str(root),net=proposal_net)['request']['width_nm']/1e6
