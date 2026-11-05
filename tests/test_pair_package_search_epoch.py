"""Package search reuse is epoch-local, physical and deadline bounded."""
import time
import pcbnew
import pytest
import cec_fr as fr
import cec_field_coupling as field
from test_pair_package_via_floor import package_board, construct
from test_pair_package_preclosure import fixture
from test_field_proposals import signature


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('profile',['jlcpcb_6l_pofv_signal','jlcpcb_6l_pofv_high_current'])
def test_impossible_literal_columns_are_not_reprobed_for_every_bridge(angle,profile):
    board,pair=package_board(angle,pad_size=.32,profile=profile)
    before=signature(board)
    result=construct(board,pair)
    row=next(r for r in result['detail']if r.get('pofv_escape'))
    assert result['pair_refused']==2 and not result['pair_linked']
    assert row['pofv_escape']['native_via_probe_count']==1
    assert row['pofv_escape']['native_via_refusal_counts']=={'pad or hole excludes via land':1}
    proof=row['local_search']['fixed_column_preflight']
    assert proof['complete']and not proof['ok']and not proof['routing_admitted']
    assert signature(board)==before


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_positive_columns_are_rechecked_with_actual_candidate_copper(monkeypatch,angle):
    board,pair=package_board(angle)
    calls=[];native=fr._via_spot_clear
    def inspect(*args,**kwargs):
        calls.append(len(list(board.GetTracks())))
        return native(*args,**kwargs)
    monkeypatch.setattr(fr,'_via_spot_clear',inspect)
    result=construct(board,pair)
    row=next(r for r in result['detail']if r.get('pofv_escape'))
    assert result['pair_linked']==2 and not result['pair_refused']
    assert row['local_search']['fixed_column_preflight']['ok']
    assert row['pofv_escape']['native_via_probe_count']>=8
    assert len(calls)>=8 and max(calls)>min(calls)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('names',[('/USB_DP','/USB_DM'),('declared_a','declared_b')])
def test_repeated_u_shapes_reuse_only_this_unchanged_package_frame(monkeypatch,angle,names):
    board,_,pair=fixture(angle,names)
    before=signature(board)
    monkeypatch.setattr(field,'assess_proposed_route',lambda *a,**kw:
        dict(complete=True,ok=False,reason='synthetic field refusal'))
    def run():
        result=fr.synthesize_same_footprint_links(board,include_nets=set(names),
            pair_declarations=[pair],allow_maze=False)
        return next(r['local_search']for r in result['detail']if 'local_search'in r)
    one=run();two=run()
    assert one['u_plan_cache_hits']>0 and two['u_plan_cache_hits']>0
    assert 0<one['u_plan_native_searches']<=16
    assert two['u_plan_native_searches']==one['u_plan_native_searches']
    assert signature(board)==before


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('field_guard',[False,True])
def test_expired_shared_lease_never_starts_native_geometry(monkeypatch,angle,field_guard):
    board,_,pair=fixture(angle,('arbitrary_p','arbitrary_n'))
    before=signature(board)
    def unexpected(*a,**kw):raise AssertionError('geometry after caller deadline')
    monkeypatch.setattr(fr,'_via_spot_clear',unexpected)
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',unexpected)
    monkeypatch.setattr(fr,'_tap_foreign_clear',unexpected)
    monkeypatch.setattr(field,'assess_proposed_route',unexpected)
    result=fr.synthesize_same_footprint_links(board,include_nets={pair['p'],pair['n']},
        pair_declarations=[pair],field_guard=field_guard,deadline_monotonic=time.monotonic()-1.)
    assert result['field_guard']['search_inconclusive']and result['field_guard']['unknown']
    assert result['pair_refused']==2 and not result['pair_linked']
    assert signature(board)==before


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_partial_column_preflight_always_rolls_back(monkeypatch,angle):
    board,pair=package_board(angle)
    before=signature(board);calls=[]
    def veto_second(*a,**kw):
        calls.append(1)
        if len(calls)==1:return True
        if kw.get('report')is not None:kw['report'].update(reason='synthetic second-column veto')
        return False
    monkeypatch.setattr(fr,'_via_spot_clear',veto_second)
    result=construct(board,pair)
    assert len(calls)==2 and result['pair_refused']==2
    assert signature(board)==before


@pytest.mark.parametrize('remaining',[.5,2.,20.])
def test_asymmetric_bridge_inherits_shared_lease_and_ten_second_ceiling(monkeypatch,remaining):
    board,pair=package_board()
    edge=pcbnew.PCB_TRACK(board);edge.SetNet(board.FindNet(pair['p']));edge.SetLayer(pcbnew.F_Cu)
    edge.SetWidth(pcbnew.FromMM(.2));edge.SetStart(pcbnew.VECTOR2I_MM(15,15))
    edge.SetEnd(pcbnew.VECTOR2I_MM(17.2,15));board.Add(edge)
    board.BuildConnectivity();before=signature(board);seen=[]
    deadline=time.monotonic()+remaining
    def bridge(*a,**kw):
        seen.append(kw['deadline_monotonic'])
        assert time.monotonic()<kw['deadline_monotonic']<=min(deadline,time.monotonic()+10.)
        return None
    monkeypatch.setenv('CEC_PAIR_CLOSURE_TIMEOUT','60')
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    result=fr.synthesize_same_footprint_links(board,include_nets={pair['p'],pair['n']},
        pair_declarations=[pair],field_guard=False,deadline_monotonic=deadline)
    assert seen and result['pair_refused']and signature(board)==before


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('flip',[False,True])
def test_world_normal_escape_does_not_use_unrotated_package_land_size(monkeypatch,angle,flip):
    board,_,pair=fixture(angle,('not_spelled_as_p','not_spelled_as_n'))
    if flip:
        for fp in board.GetFootprints():
            fp.Flip(fp.GetPosition(),True)
    before=signature(board);lengths=[]
    def no_route(_board,a,b,*args,**kwargs):
        lengths.append(round(((b.x-a.x)**2+(b.y-a.y)**2)**.5))
        return None
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',no_route)
    result=fr.synthesize_same_footprint_links(board,include_nets={pair['p'],pair['n']},
        pair_declarations=[pair],field_guard=False,allow_maze=False)
    assert result['pair_refused']==2 and signature(board)==before
    # Same long native pad normal, class width and clearance on all cardinal
    # orientations / actual surfaces. Native bbox has at most1nm rounding.
    assert lengths and all(any(abs(n-want)<=1 for want in (925000,1175000,1425000,1675000))for n in lengths)
    assert {round(n/1000)for n in lengths}=={925,1175,1425,1675}
