"""Fund complete inline hypotheses without replenishing their parent lease.

The controlled solver below models effort only, not electrical qualification.
Real native ports, scope/rollback and the external qualifier remain distinct.
"""
import math
import pytest
import cec_precision_route as route
import cec_field_coupling as field
from test_inline_bank_search import fixture


@pytest.mark.parametrize('choices',[1,2,3,8,32])
@pytest.mark.parametrize('remaining',[.1,1.,8.,100.])
def test_complete_attempt_is_not_divided_by_alternative_count(choices,remaining):
    end=route._inline_alternative_deadline(20.+remaining,choices,now=20.)
    assert end==min(20.+remaining,30.)
    assert end<=20.+remaining and end-20.<=10.


@pytest.mark.parametrize('policy',['complete-attempt','legacy-fair'])
def test_nested_alternative_calls_never_replenish_the_original_lease(policy):
    first=route._inline_alternative_deadline(28.,2,policy=policy,now=20.)
    second=route._inline_alternative_deadline(first,3,policy=policy,now=20.2)
    leaf=route._inline_alternative_deadline(second,3,policy=policy,now=20.3)
    assert 20.3<=leaf<=second<=first<=28.
    assert route._inline_alternative_deadline(19.,3,policy=policy,now=20.)==19.


def test_mandatory_work_is_shared_once_not_multiplied_by_topology_alternatives():
    def leaf(policy):
        bank=route._inline_alternative_deadline(8.,2,policy=policy,now=0.)
        order=route._inline_alternative_deadline(bank,3,policy=policy,now=0.)
        mandatory=route._fair_subdeadline(order,2,now=0.)
        return route._inline_alternative_deadline(mandatory,3,policy=policy,now=0.)
    assert leaf('complete-attempt')==4.
    assert leaf('legacy-fair')==pytest.approx(8./36.)


@pytest.mark.parametrize('policy',['complete-attempt','legacy-fair'])
def test_missing_parent_still_has_a_finite_ten_second_constituent(policy):
    assert route._inline_alternative_deadline(None,3,policy=policy,now=20.)==30.


@pytest.mark.parametrize('kwargs',[
    dict(policy=False),dict(policy='unknown'),dict(policy={}),
    dict(remaining_choices=True),dict(remaining_choices=0),dict(remaining_choices=33),
    dict(max_attempt_s=True),dict(max_attempt_s=0),dict(max_attempt_s=11),
    dict(max_attempt_s=math.inf),dict(max_attempt_s=math.nan),
    dict(now=True),dict(now=math.nan),dict(now=math.inf),
    dict(absolute_deadline=True),dict(absolute_deadline=math.nan),dict(absolute_deadline=math.inf)])
def test_invalid_policy_context_refuses(kwargs):
    values=dict(absolute_deadline=28.,remaining_choices=2,now=20.)
    values.update(kwargs)
    with pytest.raises(ValueError,match='bounded_inline_alternative_budget'):
        route._inline_alternative_deadline(**values)


TRANSFORMS=[lambda p:p,lambda p:(p[0]+31,p[1]-17),
            lambda p:(-p[1],p[0]),lambda p:(-p[0],p[1])]


@pytest.mark.parametrize('transform',TRANSFORMS)
@pytest.mark.parametrize('policy',['complete-attempt','legacy-fair'])
def test_native_inline_ports_reach_a_complete_effort_attempt_before_qualifier(monkeypatch,transform,policy):
    board,pair,(legs,stations)=fixture(transform)
    before=field._field_snapshot_inventory(board);clock=[20.];calls=[];qualified=[]
    monkeypatch.setattr(route.time,'monotonic',lambda:clock[0])
    def solve(_board,_pair,**kw):
        available=kw['deadline']-clock[0]
        calls.append(dict(start=clock[0],deadline=kw['deadline'],available=available))
        assert 0<available<=10. and kw['deadline']<=28.
        assert kw['minimum_coupled_fraction']==.35
        if available<2.:
            clock[0]=kw['deadline']+.000001
            return dict(refused='controlled effort exhausted',search_budget_exhausted=True)
        clock[0]+=2.
        return dict(name=pair['name'],p=pair['p'],n=pair['n'],segments=0,
            length_mm=1.,coupled_len_mm=1.)
    def qualify(result):
        qualified.append(result)
        return dict(result,refused='independent whole-pair qualifier refuses',
            release_authority=False)
    monkeypatch.setattr(route,'route_coupled_pair',solve)
    result=route._route_flow_bank_orders(board,pair,legs,stations,deadline=28.,
        alternative_budget_policy=policy,candidate_qualifier=qualify)
    assert result.get('refused')and field._field_snapshot_inventory(board)==before
    assert qualified if policy=='complete-attempt'else not qualified
    assert all(r['budget']['attempt_deadline']<=28. for r in result['flow_bank_attempts'])


@pytest.mark.parametrize('transform',TRANSFORMS)
def test_required_legs_keep_fair_effort_within_one_complete_attempt(monkeypatch,transform):
    board,pair,(legs,stations)=fixture(transform);clock=[20.];seen=[]
    monkeypatch.setattr(route.time,'monotonic',lambda:clock[0])
    def solve(_board,_pair,**kw):
        seen.append(kw['deadline']);clock[0]+=1.
        return dict(segments=0,length_mm=1.,coupled_len_mm=1.)
    monkeypatch.setattr(route,'route_coupled_pair',solve)
    result=route._route_flow_leg_orders(board,pair,legs,stations,deadline=28.)
    assert not result.get('refused')and len(seen)==2
    assert seen==[24.,28.]
    assert result['flow_order_attempts'][0]['alternative_budget_policy']=='complete-attempt'


def test_expiry_never_starts_another_bank_order_or_layer(monkeypatch):
    board,pair,(legs,stations)=fixture();before=field._field_snapshot_inventory(board)
    clock=[20.];calls=[]
    monkeypatch.setattr(route.time,'monotonic',lambda:clock[0])
    def expire(_board,_pair,**kw):
        calls.append(kw);clock[0]=29.
        return dict(refused='controlled outer expiry',search_budget_exhausted=True)
    monkeypatch.setattr(route,'route_coupled_pair',expire)
    result=route._route_flow_bank_orders(board,pair,legs,stations,deadline=28.)
    assert len(calls)==1 and result.get('refused')
    assert field._field_snapshot_inventory(board)==before
