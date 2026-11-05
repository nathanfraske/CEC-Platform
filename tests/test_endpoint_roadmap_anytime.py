"""Spend bounded endpoint effort on exact admission before optional refinement.

Controlled clocks/search offers test scheduling, not electrical signoff. The
real joint selector and unchanged local contracts remain authoritative here.
"""
import math

import pytest
import cec_endpoint_roadmap as roadmap
import cec_precision_route as route
from test_endpoint_roadmap import refine_fixture


TRANSFORMS = [lambda p:p,lambda p:(p[0]+31,p[1]-17),
              lambda p:(-p[1],p[0]),lambda p:(-p[0],p[1])]


def fixture(transform=lambda p:p):
    p,n,kw=refine_fixture()
    p,n=list(map(transform,p)),list(map(transform,n))
    kw=dict(kw,endpoints=(p[0],n[0],p[-1],n[-1]))
    # The existing context is used only for its complete-pair contract. Its
    # station spread is irrelevant to these parallel, renamed native ports.
    kw['context']=dict(kw['context'],endpoint_stations=[])
    return p,n,kw


@pytest.mark.parametrize('transform',TRANSFORMS)
def test_existing_admitted_domain_is_checked_before_any_new_query(monkeypatch,transform):
    p,n,kw=fixture(transform)
    monkeypatch.setattr(roadmap,'search',lambda *a,**k:pytest.fail('optional query'))
    selected,e=roadmap.refine([p],[n],None,**kw)
    assert selected==(p,n) and e['selected_contract']['ok']
    assert e['selected_stage']=='initial-domain' and e['queries']==[]
    assert e['selection']['admitted_pairs']==1


@pytest.mark.parametrize('transform',TRANSFORMS)
def test_coarse_complete_pair_is_admitted_before_fine_or_anchored_query(monkeypatch,transform):
    p,n,kw=fixture(transform);calls=[];clock=[20.]
    monkeypatch.setattr(roadmap.time,'monotonic',lambda:clock[0])
    def offer(start,end,clear,**options):
        calls.append(options)
        assert not options['anchor'] and options['step']==.4
        assert 20.<options['deadline']<28.
        clock[0]+=.2
        return [start,end],dict(visited=1,queries=1)
    monkeypatch.setattr(roadmap,'search',offer)
    selected,e=roadmap.refine([],[],None,deadline=28.,**kw)
    assert selected==(p,n) and len(calls)==2
    assert e['selected_stage']=='unanchored-member'
    assert e['expanded_domain_sizes']==[1,1]
    assert len(e['selection_attempts'])==1
    assert e['selection']['path_pairs_checked']==1


@pytest.mark.parametrize('transform',TRANSFORMS)
def test_query_expiry_leaves_same_parent_time_for_admitting_a_found_path(monkeypatch,transform):
    p,n,kw=fixture(transform);clock=[20.];calls=[]
    monkeypatch.setattr(roadmap.time,'monotonic',lambda:clock[0])
    def offer(start,end,clear,**options):
        calls.append(options);clock[0]=options['deadline']
        return [start,end],dict(visited=17,queries=20,deadline_exhausted=True)
    monkeypatch.setattr(roadmap,'search',offer)
    selected,e=roadmap.refine([],[n],None,deadline=20.5,**kw)
    assert selected==(p,n) and len(calls)==1
    assert calls[0]['deadline']==pytest.approx(20.45)
    assert e['queries'][0]['selection_reserve_seconds']==pytest.approx(.05)
    assert clock[0]<20.5 and e['selection']['admitted_pairs']==1


@pytest.mark.parametrize('failure',['crossing','gap','skew','coupling','detour'])
def test_early_selection_does_not_waive_any_joint_contract(monkeypatch,failure):
    p,n,kw=fixture();options=dict(kw['options'])
    if failure=='crossing':n=[(10.,10.5),(12.,9.),(14.,10.5)]
    elif failure=='gap':n=[(10.,10.1),(14.,10.1)]
    elif failure=='skew':options['existing_signed_skew_mm']=10.
    elif failure=='coupling':n=[(10.,13.),(14.,13.)]
    else:p=[p[0],(0.,10.),(0.,0.),(14.,0.),p[-1]]
    kw=dict(kw,options=options)
    monkeypatch.setattr(roadmap,'search',lambda *a,**k:(None,{}))
    selected,e=roadmap.refine([p],[n],None,**kw)
    assert selected is None and not e['selected']
    assert len(e['selection_attempts'])==1
    assert not e['selection']['admitted_pairs']


def test_refinement_continues_only_after_exact_initial_contract_refusal(monkeypatch):
    p,n,kw=fixture();bad=[n[0],(10.,14.),(14.,14.),n[-1]];calls=[]
    def offer(start,end,clear,**options):
        calls.append(options)
        return [start,end],dict(visited=1,queries=1)
    monkeypatch.setattr(roadmap,'search',offer)
    selected,e=roadmap.refine([p],[bad],None,**kw)
    assert selected==(p,n) and len(calls)==2
    assert len(e['selection_attempts'])==2
    assert not e['selection_attempts'][0]['diagnostics']['admitted_pairs']
    assert e['selection_attempts'][1]['diagnostics']['admitted_pairs']==1


def test_unknown_query_does_not_become_a_completed_negative_or_replace_incumbent(monkeypatch):
    p,n,kw=fixture();bad=[p[0],(8.,10.),(8.,14.),(14.,14.),p[-1]]
    incumbent=(bad,n);clock=[20.]
    monkeypatch.setattr(roadmap.time,'monotonic',lambda:clock[0])
    def expire(*a,**k):
        clock[0]=29.
        return None,dict(deadline_exhausted=True)
    monkeypatch.setattr(roadmap,'search',expire)
    selected,e=roadmap.refine([bad],[n],incumbent,deadline=28.,**kw)
    assert selected is incumbent and not e['selected']
    assert e['search_inconclusive'] and e['deadline_exhausted']
    assert e['reason']=='deadline_exhausted' and len(e['queries'])==1


@pytest.mark.parametrize('value',[True,-1,11,math.inf,math.nan])
def test_invalid_selection_reserve_is_rejected(value):
    with pytest.raises(ValueError):roadmap.Limits(selection_reserve_seconds=value)


@pytest.mark.parametrize('reserve',[0.,.01,.1,10.])
def test_reserve_is_search_effort_only_and_never_extends_parent(monkeypatch,reserve):
    p,n,kw=fixture();clock=[20.];deadlines=[]
    monkeypatch.setattr(roadmap.time,'monotonic',lambda:clock[0])
    def offer(start,end,clear,**options):
        deadlines.append(options['deadline']);clock[0]+=.01
        return [start,end],{}
    monkeypatch.setattr(roadmap,'search',offer)
    selected,e=roadmap.refine([],[],None,deadline=20.5,
        limits=roadmap.Limits(selection_reserve_seconds=reserve),**kw)
    assert selected==(p,n) and all(20.<d<=20.5 for d in deadlines)
    assert e['selected_contract']['ok']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
def test_actual_native_member_guards_and_joint_selector_leave_saved_board_unchanged(tmp_path,quarter,face):
    import time
    import pcbnew
    import cec_fr
    from test_endpoint_roadmap import fixture as native_fixture
    b,pair,ends=native_fixture();lid=b.GetLayerID(face)
    def xy(p):
        x,y=p
        for _ in range(quarter):x,y=-y,x
        return x+70,y+70
    layers=pcbnew.LSET();layers.AddLayer(lid)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            pos=pad.GetPosition();pad.SetPosition(route._v(*xy((pos.x/route.MM,pos.y/route.MM))))
            pad.SetLayerSet(layers)
    ends=tuple(map(xy,ends))
    source=tmp_path/'saved-native.kicad_pcb';pcbnew.SaveBoard(str(source),b)
    b=pcbnew.LoadBoard(str(source));before=source.read_bytes()
    context=roadmap.complete_context(b,pair,ends);assert context
    options=dict(p_span=math.dist(ends[0],ends[1]),n_span=math.dist(ends[2],ends[3]),
        width=.25,gap=.25,max_skew=4.,preferred_end_direction=None,
        minimum_end_coherence=None,strict_pair_gap=True,existing_signed_skew_mm=0.)
    calls=[];cache={}
    def guard(net,a,z):
        calls.append((net,a,z))
        return cec_fr._tap_foreign_clear(b,route._v(*a),route._v(*z),250000,lid,200000,
            {b.GetNetcodeFromNetname(net)},foreign_cache=cache)
    selected,e=roadmap.refine([],[],None,
        endpoints=(ends[0],ends[2],ends[1],ends[3]),
        p_clear=lambda a,z:guard(pair['p'],a,z),n_clear=lambda a,z:guard(pair['n'],a,z),
        options=options,context=context,deadline=time.monotonic()+3.)
    assert selected and calls and e['selected_contract']['ok']
    assert e['selected_stage']=='unanchored-member' and len(e['queries'])==2
    assert not list(b.GetTracks()) and source.read_bytes()==before
    for net,path in zip((pair['p'],pair['n']),selected):
        assert all(guard(net,a,z) for a,z in zip(path,path[1:]))
