"""No-good proposals must use actual field failures, not false shielding."""
import time
from unittest.mock import patch
import pcbnew
import pytest
import cec_field_coupling as field
import cec_pair_field_search as search
import cec_precision_route as route


def fixture(turn=0,mirror=False):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    def xy(p):
        x,y=p[0]-15,p[1]-10
        if mirror:x=-x
        for _ in range(turn):x,y=-y,x
        return x+20,y+20
    def point(p):return pcbnew.VECTOR2I(*(round(x*1e6) for x in xy(p)))
    for a,z in (((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))):
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z))
        edge.SetLayer(pcbnew.Edge_Cuts);b.Add(edge)
    nets={}
    for name in ('renamed-USB_D_P','renamed-USB_D_N','arbitrary-SENSE-input'):
        nets[name]=pcbnew.NETINFO_ITEM(b,name);b.Add(nets[name])
    t=pcbnew.PCB_TRACK(b);t.SetNet(nets['arbitrary-SENSE-input'])
    t.SetStart(point((12,11.25)));t.SetEnd(point((18,11.25)))
    t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);b.Add(t)
    pair=dict(p='renamed-USB_D_P',n='renamed-USB_D_N',width=.2,gap=.2)
    pp=[xy((5,9.8)),xy((25,9.8))];nn=[xy((5,10.2)),xy((25,10.2))]
    return b,pair,pp,nn


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_field_failure_is_a_finite_directional_no_good(turn,mirror):
    b,pair,pp,nn=fixture(turn,mirror);binding=field._field_snapshot_inventory(b)
    g=search.Guide(b,pair,layer=pcbnew.F_Cu,step_mm=.5,deadline=time.monotonic()+10)
    assert not g.paths(pp,nn)['ok']
    assert g.no_goods and g.proofs[-1]['complete']
    mid=tuple((x+y)/2 for x,y in zip(pp[0],nn[0]))
    end=tuple((x+y)/2 for x,y in zip(pp[1],nn[1]))
    assert not g.edge(mid,end)
    v=(end[0]-mid[0],end[1]-mid[1]);c=tuple((x+y)/2 for x,y in zip(mid,end))
    assert g.edge((c[0]-v[1]/2,c[1]+v[0]/2),(c[0]+v[1]/2,c[1]-v[0]/2))
    assert field._field_snapshot_inventory(b)==binding
    assert not g.report()['release_authority'] and not g.report()['no_path_proof']


def test_grid_replay_finds_a_clear_coupled_route_without_writing_copper():
    b,pair,pp,nn=fixture();before=field._field_snapshot_inventory(b);detail={}
    options=dict(start_center=(10,20),end_center=(30,20),p_start=pp[0],n_start=nn[0],
        p_end=pp[-1],n_end=nn[-1],layer_id=pcbnew.F_Cu,width=.2,gap=.2,clearance=.2,
        own={b.GetNetcodeFromNetname(pair[k]) for k in ('p','n')},portal_mode=True,
        portal_start_heading=(1,0),portal_end_heading=(1,0),step=.5,
        initial_turn_steps=0,terminal_turn_steps=0,strict_taper_continuation=True)
    result=search.coupled_path(b,pair=pair,deadline=time.monotonic()+10,
        diagnostics=detail,**options)
    assert result,detail
    assert detail['field_guidance']['no_goods']>0
    assert detail['field_guidance']['complete_route_proofs'][-1]['ok'] is True
    assert field._field_snapshot_inventory(b)==before and len(list(b.GetTracks()))==1
    assert route._polyline_is_octilinear(result[0]) and route._polyline_is_octilinear(result[1])


def test_unknown_field_proof_is_not_learned_or_accepted():
    b,pair,pp,nn=fixture();g=search.Guide(b,pair,layer=0,step_mm=.5,deadline=time.monotonic()+10)
    with patch.object(field,'assess_proposed_tracks',return_value=dict(ok=None,complete=False,
            reason='bounded_work_exhausted',new_blockers=[])):
        assert not g.paths(pp,nn)['ok']
    assert g.incomplete and not g.no_goods and not g.edge(pp[0],pp[1])


def test_public_pair_search_preserves_explicit_design_identity():
    b,pair,pp,nn=fixture();before=field._field_snapshot_inventory(b)
    def inspect_grid(_board,**kwargs):
        with patch.object(field,'assess_proposed_tracks',
                return_value=dict(ok=True,complete=True,new_blockers=[])) as assess:
            assert kwargs['path_validator'](pp,nn)['ok']
            assert assess.call_args.kwargs['board_hint']=='renamed-design-authority'
        return pp,nn,20.
    with patch.object(route,'_grid_coupled_path',side_effect=inspect_grid):
        assert search.coupled_path(b,pair=pair,board_hint='renamed-design-authority',
            layer_id=0,step=.5,deadline=time.monotonic()+10)
    assert field._field_snapshot_inventory(b)==before


def test_native_pad_rejection_cannot_be_relabelled_as_a_field_no_good():
    b,pair,pp,nn=fixture();g=search.Guide(b,pair,layer=0,step_mm=.5,
        deadline=time.monotonic()+10,native_validator=lambda _p,_n:dict(ok=False,reason='pad_collision'))
    assert not g.paths(pp,nn)['ok']
    assert not g.proofs and not g.no_goods


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_failed_long_run_does_not_erase_the_exact_mandatory_throat(turn,mirror):
    b,pair,pp,nn=fixture(turn,mirror)
    start=tuple((x+y)/2 for x,y in zip(pp[0],nn[0]))
    end=tuple((x+y)/2 for x,y in zip(pp[-1],nn[-1]))
    ux,uy=((end[i]-start[i])/20 for i in (0,1))
    tip=(start[0]+ux*.5,start[1]+uy*.5)
    g=search.Guide(b,pair,layer=0,step_mm=.5,deadline=time.monotonic()+10,
        mandatory_throats_mm=((start,tip),))
    g.no_goods=[(start,end)]
    binding=field._field_snapshot_inventory(b)
    assert g.edge(start,tip)
    assert not g.edge(tip,(tip[0]+ux*.5,tip[1]+uy*.5))
    assert not g.edge(start,end)
    assert g.report()['retained_mandatory_throat_edges']==1
    assert field._field_snapshot_inventory(b)==binding
    # Preserving a proposal edge never accepts its failed complete route.
    assert not g.paths(pp,nn)['ok'] and g.proofs[-1]['complete']


@pytest.mark.parametrize('throats',[
    (((0,0),(2,0)),),(((0,0),(0,0)),),(((0,0),(float('nan'),1)),),
    (((0,0),(1,0)),)*3])
def test_terminal_throat_preservation_cannot_be_an_unbounded_exclusion(throats):
    b,pair,_,_=fixture()
    with pytest.raises(ValueError,match='bounded_directed_terminal_throats'):
        search.Guide(b,pair,layer=0,step_mm=.5,deadline=time.monotonic()+10,
            mandatory_throats_mm=throats)


@pytest.mark.parametrize('heading',[(1,1),(-1,1),(-1,-1),(1,-1),(.9,1)])
def test_diagonal_mandatory_throat_matches_native_grid_not_unit_length(heading):
    b,pair,_,_=fixture();start=(10.,20.);end=(30.,20.);detail={}
    dx,dy=(1 if v>0 else -1 for v in heading)
    tip=(start[0]+dx*.5,start[1]+dy*.5)
    g=search.Guide(b,pair,layer=0,step_mm=.5,deadline=time.monotonic()+10,
        mandatory_throats_mm=((start,tip),))
    g.no_goods=[(start,(start[0]+dx*10,start[1]+dy*10))]
    assert g.edge(start,tip)
    assert not g.edge(tip,(tip[0]+dx*.5,tip[1]+dy*.5))
    def inspect_grid(_board,**kwargs):
        assert kwargs['edge_validator'](start,tip)
        return None
    original_edge=search.Guide.edge
    def add_no_good(guide,a,z):
        guide.no_goods=[(start,(start[0]+dx*10,start[1]+dy*10))]
        return original_edge(guide,a,z)
    with patch.object(search.Guide,'edge',add_no_good), \
            patch.object(route,'_grid_coupled_path',side_effect=inspect_grid):
        search.coupled_path(b,pair=pair,start_center=start,end_center=end,
            portal_mode=True,portal_start_heading=heading,
            portal_end_heading=heading,initial_turn_steps=0,terminal_turn_steps=0,
            layer_id=0,step=.5,diagnostics=detail)
    assert detail['field_guidance']['mandatory_throats_mm'][0]==(start,tip)


@pytest.mark.parametrize('limit',[0,9,True,1.5])
def test_unbounded_or_malformed_replay_refuses(limit):
    b,pair,_,_=fixture()
    with pytest.raises(ValueError,match='bounded_pair_field_replay'):
        search.coupled_path(b,pair=pair,max_attempts=limit)


@pytest.mark.parametrize('budget',[0,-1,61,True,float('nan'),float('inf')])
def test_field_search_budget_is_explicit_finite_and_bounded(budget):
    b,pair,_,_=fixture()
    with pytest.raises(ValueError,match='finite_bounded_pair_field_search_budget'):
        search.coupled_path(b,pair=pair,layer_id=0,search_budget_s=budget)


@pytest.mark.parametrize('budget,outer,expected',[(10,None,110),(45,None,145),(45,112,112)])
def test_critical_field_search_can_keep_no_goods_in_one_bounded_lease(budget,outer,expected):
    b,pair,_,_=fixture();observed=[]
    def inspect_grid(_board,**kwargs):
        observed.append(kwargs['deadline'])
        return None
    with patch.object(search.time,'monotonic',return_value=100), \
            patch.object(route,'_grid_coupled_path',side_effect=inspect_grid):
        search.coupled_path(b,pair=pair,layer_id=0,search_budget_s=budget,deadline=outer)
    assert observed == [expected]

@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_field_wrapper_binds_actual_ordered_lane_identity(turn,mirror):
    b,pair,_,_=fixture(turn,mirror);before=field._field_snapshot_inventory(b)
    wanted=tuple(b.GetNetcodeFromNetname(pair[k]) for k in ('p','n'))
    def inspect_grid(_board,**kwargs):
        assert kwargs['pair_net_codes']==wanted and kwargs['own']==set(wanted)
        return None
    with patch.object(route,'_grid_coupled_path',side_effect=inspect_grid):
        search.coupled_path(b,pair=pair,layer_id=0,step=.5)
    assert field._field_snapshot_inventory(b)==before

@pytest.mark.parametrize('fault',['reverse','foreign_own','zero','bool','absent_member'])
def test_field_wrapper_never_infers_or_accepts_ambiguous_lane_identity(fault):
    b,pair,_,_=fixture();codes=tuple(b.GetNetcodeFromNetname(pair[k]) for k in ('p','n'))
    kw={}
    if fault=='reverse':kw['pair_net_codes']=tuple(reversed(codes))
    elif fault=='foreign_own':kw['own']={codes[0],b.GetNetcodeFromNetname('arbitrary-SENSE-input')}
    elif fault=='zero':kw['pair_net_codes']=(codes[0],0)
    elif fault=='bool':kw['pair_net_codes']=(True,codes[1])
    else:pair['n']='not-present-native-net'
    with pytest.raises(ValueError):search.coupled_path(b,pair=pair,layer_id=0,**kw)
