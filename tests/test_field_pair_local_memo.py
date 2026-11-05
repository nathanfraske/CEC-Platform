"""Pure pair-name work may be shared locally, never geometry or decisions."""
import functools
import time
import pytest
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track,signature,proposal,add_net


def repeated_board(quarter=0,prefix='/renamed/'):
    b=_board([],edge=(0,0,40,40))
    def turn(p):
        x,y=p[0]-20,p[1]-20
        for _ in range(quarter):x,y=y,-x
        return x+20,y+20
    for n in range(6):
        x=5+n*3
        track(b,prefix+'SW',(turn((x,14))),(turn((x+2,14))))
        track(b,prefix+'ADC',(turn((x,14.7))),(turn((x+2,14.7))))
    return b


@pytest.mark.parametrize('quarter',range(4))
def test_repeated_ordered_pair_names_evaluated_once_but_all_work_charged(monkeypatch,quarter):
    b=repeated_board(quarter);before=signature(b);calls=[];native=field._pair_mates
    def counted(a,z):calls.append((a,z));return native(a,z)
    monkeypatch.setattr(field,'_pair_mates',counted)
    work=field._ProposalWork(time.monotonic()+9,8192,100000,100000,10000)
    result=field.field_coupling_summary('',board=b,_work=work)
    assert result['blocking_count']>0
    assert len(calls)==len(set(calls)) and len(calls)<=2
    assert work.counts['pairs']==12*11//2
    assert signature(b)==before


def test_irrelevant_neutral_roles_do_not_need_pair_parsing(monkeypatch):
    b=_board([])
    track(b,'/IO_17',(3,3),(5,3));track(b,'/IO_24',(3,3.5),(5,3.5))
    def never(*args):raise AssertionError('neutral-role pair parsing is redundant')
    monkeypatch.setattr(field,'_pair_mates',never)
    result=field.field_coupling_summary('',board=b)
    assert result['ok'] and result['interaction_count']==0


def test_pair_name_results_are_not_shared_between_summary_invocations(monkeypatch):
    b=repeated_board()
    monkeypatch.setattr(field,'_pair_mates',lambda *args:True)
    first=field.field_coupling_summary('',board=b)
    monkeypatch.setattr(field,'_pair_mates',lambda *args:False)
    second=field.field_coupling_summary('',board=b)
    assert first['blocking_count']==0 and second['blocking_count']>0


def test_cache_eviction_is_bounded_and_does_not_remove_work_or_findings(monkeypatch):
    b=_board([]);caches=[]
    def observed(*args,**kwargs):
        assert kwargs=={'maxsize':4096}and not args
        def wrap(fn):
            cached=functools.lru_cache(**kwargs)(fn);caches.append(cached);return cached
        return wrap
    monkeypatch.setattr(field,'lru_cache',observed)
    for n in range(93):track(b,'/NEUTRAL_%03d'%n,(n*4,3),(n*4+1,3))
    work=field._ProposalWork(time.monotonic()+9,8192,100000,100000,10000)
    result=field.field_coupling_summary('',board=b,_work=work,_netclass_resolver=lambda _:'Clock')
    assert result['ok'] and work.counts['pairs']==93*92//2
    assert len(caches)==1
    info=caches[0].cache_info()
    assert info.maxsize==4096 and info.currsize==4096 and info.misses>4096


@pytest.mark.parametrize('proposal_only',[False,True])
def test_cached_pair_checks_keep_full_report_order_and_budget_accounting(monkeypatch,proposal_only):
    b=repeated_board();add_net(b,'/ALT_CLOCK')
    extra=[proposal('/ALT_CLOCK',(3,14.3),(26,14.3))]if proposal_only else []
    before=signature(b);works=[]
    def run():
        work=field._ProposalWork(time.monotonic()+9,8192,100000,100000,10000);works.append(work)
        return field.field_coupling_summary('',board=b,_proposed_tracks=extra,
            _proposal_only=proposal_only,_work=work)
    cached=run()
    monkeypatch.setattr(field,'lru_cache',lambda **_:lambda fn:fn)
    uncached=run()
    assert cached==uncached and works[0].counts==works[1].counts and signature(b)==before


def test_cache_hits_do_not_bypass_pair_budget_exhaustion(monkeypatch):
    b=repeated_board()
    for wrap in(True,False):
        if not wrap:monkeypatch.setattr(field,'lru_cache',lambda **_:lambda fn:fn)
        work=field._ProposalWork(time.monotonic()+9,8192,3,100000,10000)
        with pytest.raises(field._ProposalUnknown,match='field_proposal_pairs_budget'):
            field.field_coupling_summary('',board=b,_work=work)
        assert work.counts['pairs']==4
