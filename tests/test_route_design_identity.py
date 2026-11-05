"""Bound policy context survives private routing without granting admission."""
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_portal_cpu_portfolio as cpu
import cec_ordinary_signal_completion as ordinary
from cec_route_proposal_guard import RouteProposalGuard
from test_ordinary_native_portals import fixture
from test_field_refill_proposals import ground_fixture,proposal,via,signature


@pytest.mark.parametrize('identity',[True,1,{},'', '  '])
def test_malformed_design_identity_refuses_before_native_access(identity):
    with pytest.raises(ValueError,match='explicit_proposal_design_identity'):
        RouteProposalGuard(None,'/CONTROL',board_hint=identity)


@pytest.mark.parametrize('identity',[None,'RENAMED_DESIGN'])
def test_bound_identity_reaches_field_and_never_overrides_refusal(tmp_path,monkeypatch,identity):
    source,b,net=fixture(tmp_path);before=source.read_bytes();seen=[]
    def refused(board,tracks,**kwargs):
        seen.append(kwargs['board_hint'])
        return dict(ok=False,complete=True,reason='actual_unshielded_geometry')
    monkeypatch.setattr(field,'assess_proposed_route',refused)
    guard=RouteProposalGuard(b,net,board_path=str(source),board_hint=identity)
    ops=[('trk',pcbnew.VECTOR2I_MM(5,10),pcbnew.VECTOR2I_MM(15,10),220000,pcbnew.F_Cu)]
    assert guard.prepare(ops)is None
    assert seen==[identity]and guard.counts['refused']==1
    assert guard.report()['source_design_identity']==identity
    assert source.read_bytes()==before


def test_design_identity_is_part_of_exact_plan_positive_cache(tmp_path,monkeypatch):
    source,b,net=fixture(tmp_path)
    monkeypatch.setattr(field,'assess_proposed_route',lambda *a,**k:dict(ok=True,complete=True))
    guard=RouteProposalGuard(b,net,board_path=str(source),board_hint='first',memoize_exact_positive=True)
    ops=[('trk',pcbnew.VECTOR2I_MM(5,10),pcbnew.VECTOR2I_MM(15,10),220000,pcbnew.F_Cu)]
    assert guard.prepare(ops)
    guard.board_hint='second'
    assert guard.prepare(ops)is None
    assert guard.last_attempt()['reason']=='plan_source_or_policy_epoch_changed'
    assert guard.memo_hits==0


def test_cpu_offer_carries_fresh_call_context_not_request_or_path(tmp_path):
    source,b,net=fixture(tmp_path)
    q=cpu.offer(source,board_hint='synthetic',net=net,maximum_lanes=1)
    assert q['complete']and q['target']['source_board_hint']=='synthetic'
    request=dict(q['request'],source_board_hint='forged_request_field')
    explicit=cpu._target(b,request,board_hint='caller-bound')
    assert explicit['source_board_hint']=='caller-bound'
    assert 'source_board_hint'not in cpu._target(b,request)
    assert not q['routing_admitted']


@pytest.mark.parametrize('mode',['portal','splice'])
def test_real_workers_carry_identity_through_guard_and_saved_finalize(tmp_path,monkeypatch,mode):
    import cec_route_proposal_guard as guards
    import cec_additive_pair_repair as additions
    import cec_native_portal_geometry as geometry
    import cec_native_frontier_splice as splice
    import cec_additive_route_receiving as additive
    from test_native_frontier_splice import reports_for
    source,b,net=fixture(tmp_path)
    q=ordinary.plan(b,source,board_hint='synthetic',net=net)
    target=cpu._target(b,q['request'],board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'child');before=force._family(source,'synthetic')
    guard_class=guards.RouteProposalGuard;finalize=additions.save_native_additions;seen=[]
    class RecordedGuard(guard_class):
        def __init__(self,*args,**kwargs):
            seen.append(('guard',kwargs.get('board_hint')))
            super().__init__(*args,**kwargs)
    def recorded_finalize(*args,**kwargs):
        seen.append(('finalize',kwargs.get('board_hint')))
        return finalize(*args,**kwargs)
    monkeypatch.setattr(guards,'RouteProposalGuard',RecordedGuard)
    monkeypatch.setattr(additions,'save_native_additions',recorded_finalize)
    report=(geometry.apply_native_portals(child,target,10.)if mode=='portal'else
        splice.apply(child,target,10.,reports_for(b,target,0)))
    assert report['closed']==1,report
    assert ('guard','synthetic')in seen and ('finalize','synthetic')in seen
    for module in (ordinary,additive):
        kwargs={'net':net}if module is ordinary else{}
        proof=module.receive(source,child,board_hint='synthetic',timeout_s=10.,**kwargs)
        assert proof['ok']and proof['complete'],proof
    assert force._family(source,'synthetic')==before


def test_early_field_refill_uses_same_initialized_selected_subset_as_saved_receiver(tmp_path,monkeypatch):
    import cec_zone_fill as fill
    source,b=ground_fixture(tmp_path);before=signature(b);seen=[];compile=fill.compile_selected
    def checked(owner,selected,**kwargs):
        seen.append(dict(initialize=kwargs.get('initialize_selected'),
            nets=[z.GetNetname()for z in selected],timeout_s=kwargs.get('timeout_s')))
        return compile(owner,selected,**kwargs)
    monkeypatch.setattr(fill,'compile_selected',checked)
    result=field.assess_proposed_route(b,[proposal('/CONTROL',(10,14),(12,14))],
        proposed_vias=[via()],board_path=source,board_hint='synthetic',deadline=time.monotonic()+5.)
    assert result['ok']and result['complete'],result
    assert seen and all(r['initialize']is True and set(r['nets'])=={'GND'}
        and 0<r['timeout_s']<=5. for r in seen)
    assert signature(b)==before and not result['inherited_debt_qualified']
