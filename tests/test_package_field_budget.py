"""A bounded native field check inherits real available time, never a waiver."""
import math,time
import pytest
import cec_fr as fr
import cec_field_coupling as field
from test_local_link_field_admission import fixture
from test_field_proposals import signature


@pytest.mark.parametrize('value',[0,-1,31,True,'10',float('nan'),float('inf')])
def test_invalid_budget_rejected_before_any_mutation(value):
    b,pair,resolver=fixture();before=signature(b)
    with pytest.raises(ValueError,match='bounded_package_field_budget'):
        fr.synthesize_same_footprint_links(b,field_timeout_s=value)
    assert signature(b)==before


@pytest.mark.parametrize('value',[True,'100',float('nan'),float('inf')])
def test_invalid_shared_deadline_rejected_before_any_mutation(value):
    b,pair,resolver=fixture();before=signature(b)
    with pytest.raises(ValueError,match='bounded_package_field_budget'):
        fr.synthesize_same_footprint_links(b,deadline_monotonic=value)
    assert signature(b)==before


@pytest.mark.parametrize('budget,shared_remaining',[(10.,None),(10.,3.),(4.,20.)])
def test_real_field_checker_receives_bounded_available_slice(monkeypatch,budget,shared_remaining):
    b,pair,resolver=fixture();before=signature(b);observed=[]
    def decline(*args,**kwargs):
        left=kwargs['deadline']-time.monotonic();observed.append(left)
        return dict(complete=True,ok=False,reason='unit field refusal')
    monkeypatch.setattr(field,'assess_proposed_route',decline)
    deadline=None if shared_remaining is None else time.monotonic()+shared_remaining
    r=fr.synthesize_same_footprint_links(b,max_mm=6,include_nets={pair['p'],pair['n']},
        pair_declarations=[pair],netclass_resolver=resolver,allow_maze=False,
        field_timeout_s=budget,deadline_monotonic=deadline)
    limit=budget if shared_remaining is None else min(budget,shared_remaining)
    assert observed and all(0<v<=limit for v in observed)
    assert max(observed)>limit-.5
    assert not r['field_guard']['search_inconclusive'] and signature(b)==before


def test_expired_shared_budget_never_calls_native_field_tool_or_emits_copper(monkeypatch):
    b,pair,resolver=fixture();before=signature(b)
    def unexpected(*args,**kwargs):raise AssertionError('native tool started after shared deadline')
    monkeypatch.setattr(field,'assess_proposed_route',unexpected)
    r=fr.synthesize_same_footprint_links(b,max_mm=6,include_nets={pair['p'],pair['n']},
        pair_declarations=[pair],netclass_resolver=resolver,allow_maze=False,
        deadline_monotonic=time.monotonic()-1)
    assert r['field_guard']['unknown'] and r['field_guard']['search_inconclusive']
    assert signature(b)==before
    from cec_search_completion import annotate_refusal
    refusal=annotate_refusal(dict(refused='package closure unavailable',package_pad_preclosure=r))
    assert refusal['search_inconclusive'] and refusal['search_completion']['inconclusive']


def test_unknown_non_budget_field_geometry_still_cannot_be_called_no_path(monkeypatch):
    b,pair,resolver=fixture();before=signature(b)
    monkeypatch.setattr(field,'assess_proposed_route',lambda *a,**kw:
        dict(complete=False,ok=None,reason='unknown native field geometry'))
    r=fr.synthesize_same_footprint_links(b,max_mm=6,include_nets={pair['p'],pair['n']},
        pair_declarations=[pair],netclass_resolver=resolver,allow_maze=False)
    assert r['field_guard']['unknown'] and r['field_guard']['search_inconclusive']
    assert signature(b)==before


@pytest.mark.parametrize('complete,ok',[(False,True),(False,False),(False,None),(None,True),(True,None)])
def test_incomplete_or_unknown_field_verdict_is_neither_pass_nor_negative_geometry(monkeypatch,complete,ok):
    b,pair,resolver=fixture();before=signature(b)
    monkeypatch.setattr(field,'assess_proposed_route',lambda *a,**kw:
        dict(complete=complete,ok=ok,reason='inconsistent or unknown unit proof'))
    r=fr.synthesize_same_footprint_links(b,max_mm=6,include_nets={pair['p'],pair['n']},
        pair_declarations=[pair],netclass_resolver=resolver,allow_maze=False)
    assert r['field_guard']['unknown'] and not r['field_guard']['passed'] and not r['field_guard']['refused']
    assert r['field_guard']['search_inconclusive'] and not r['pair_linked'] and signature(b)==before
