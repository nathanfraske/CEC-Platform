import math
import time
import pytest
from cec_endpoint_roadmap import search
import cec_precision_route as route
import cec_endpoint_roadmap as roadmap
from unittest.mock import patch


def test_exact_off_grid_end_and_deterministic():
    args=((0.,0.),(3.13,1.07),lambda a,b:True)
    a,e=search(*args)
    b,f=search(*args)
    assert a==b and e==f and a[0]==args[0] and a[-1]==args[1]
    assert route._polyline_is_octilinear(a)
    assert not route._polyline_has_reverse_bend(a)


def test_no_false_success_for_enclosed_pin():
    path,report=search((0.,0.),(3.,1.),lambda a,b:False)
    assert path is None and report['visited']==1


def test_foreign_blockage_is_preserved_after_chamfer():
    def clear(a,b):
        return route._seg_seg_dist(a,b,(1.5,-.5),(1.5,.5))>.15
    path,report=search((0.,0.),(3.,0.),clear)
    assert path and all(clear(a,b) for a,b in zip(path,path[1:]))


def test_anchor_spacing_and_endpoint_identity():
    anchor=[(0.,0.),(4.,0.)]
    path,_=search((0.,.8),(4.,.8),lambda a,b:True,anchor=anchor,
                  width=.25,gap=.25,coupling_weight=2.)
    assert path and path[0]==(0.,.8) and path[-1]==(4.,.8)
    assert all(route._seg_seg_dist(a,b,*anchor)>=.5-1e-6 for a,b in zip(path,path[1:]))


def test_explicit_bounds_and_deadline():
    path,report=search((0.,0.),(3.,1.),lambda a,b:True,max_visited=1)
    assert path is None and report['visit_budget_exhausted']
    path,report=search((0.,0.),(3.,1.),lambda a,b:True,deadline=time.monotonic()-1)
    assert path is None and report['deadline_exhausted']


@pytest.mark.parametrize('transform',[
    lambda p:(p[0]+23.,p[1]-17.),
    lambda p:(-p[1],p[0]),
    lambda p:(-p[0],p[1]),
])
def test_domain_is_not_tied_to_origin_or_orientation(transform):
    start,end=transform((0.,0.)),transform((3.13,1.07))
    obstacle=[transform(p) for p in ((1.5,-.5),(1.5,.5))]
    clear=lambda a,b:route._seg_seg_dist(a,b,*obstacle)>.15
    path,_=search(start,end,clear)
    assert path and path[0]==start and path[-1]==end
    assert route._polyline_is_octilinear(path)
    assert all(clear(a,b) for a,b in zip(path,path[1:]))


def test_clearance_is_authoritative_even_if_coupling_is_attractive():
    calls=[]
    def clear(a,b):
        calls.append((a,b))
        return False
    path,_=search((0.,.8),(4.,.8),clear,anchor=[(0.,0.),(4.,0.)],
                  coupling_weight=100.)
    assert path is None and calls


def test_loaded_native_foreign_copper_is_never_changed_or_crossed(tmp_path):
    import pcbnew
    import cec_fr
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for name in ('arbitrary-signal','unrelated-obstacle'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    track=pcbnew.PCB_TRACK(board)
    track.SetNet(board.FindNet('unrelated-obstacle'))
    track.SetLayer(pcbnew.F_Cu);track.SetWidth(pcbnew.FromMM(.5))
    track.SetStart(pcbnew.VECTOR2I_MM(12,9));track.SetEnd(pcbnew.VECTOR2I_MM(12,11))
    board.Add(track)
    for index,position in enumerate(((10.,10.),(14.,10.))):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('PORT%d'%index);board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
        pad.SetPosition(pcbnew.VECTOR2I_MM(*position))
        pad.SetNet(board.FindNet('arbitrary-signal'));fp.Add(pad)
    filename=str(tmp_path/'native.kicad_pcb')
    pcbnew.SaveBoard(filename,board)
    loaded=pcbnew.LoadBoard(filename)
    before=[(t.m_Uuid.AsString(),t.GetStart().x,t.GetEnd().y,t.GetWidth()) for t in loaded.GetTracks()]
    cache={}
    def clear(a,b):
        return cec_fr._tap_foreign_clear(loaded,pcbnew.VECTOR2I_MM(*a),
            pcbnew.VECTOR2I_MM(*b),pcbnew.FromMM(.25),pcbnew.F_Cu,
            pcbnew.FromMM(.2),{loaded.GetNetcodeFromNetname('arbitrary-signal')},
            foreign_cache=cache)
    path,_=search((10.,10.),(14.,10.),clear,deadline=time.monotonic()+4.)
    assert path and all(clear(a,b) for a,b in zip(path,path[1:]))
    after=[(t.m_Uuid.AsString(),t.GetStart().x,t.GetEnd().y,t.GetWidth()) for t in loaded.GetTracks()]
    assert before==after


@pytest.mark.parametrize('kwargs',[
    {'step':float('nan')},{'margin':float('inf')},{'gap':-1},
    {'width':0},{'coupling_weight':float('nan')},{'max_visited':1.5},
    {'max_visited':True},{'deadline':float('nan')},
    {'anchor':[(0,float('inf')),(1,0)]},
])
def test_search_rejects_nonfinite_or_invalid_domain(kwargs):
    with pytest.raises(ValueError):
        search((0,0),(2,0),lambda a,b:True,**kwargs)


@pytest.mark.parametrize('kwargs',[
    {'steps':()},{'steps':(float('nan'),)},{'total_seconds':0},
    {'query_seconds':float('inf')},{'anchors_per_member':-1},
    {'max_visited':2.5},{'margin_mm':-1},
])
def test_limits_are_explicit_validated_search_bounds(kwargs):
    with pytest.raises(ValueError):roadmap.Limits(**kwargs)


def fixture():
    import pcbnew
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    pair=dict(name='unnamed',p='arbitrary-plus',n='arbitrary-minus',
              kind='can',width=.25,gap=.25)
    for name in (pair['p'],pair['n']):board.Add(pcbnew.NETINFO_ITEM(board,name))
    for x in (10.,14.):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('NODE%g'%x);board.Add(fp)
        for name,y in ((pair['p'],10.),(pair['n'],10.5)):
            pad=pcbnew.PAD(fp);pad.SetNumber(name)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetPosition(pcbnew.VECTOR2I_MM(x,y))
            layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
            pad.SetNet(board.FindNet(name));fp.Add(pad)
    return board,pair,((10.,10.),(14.,10.),(10.,10.5),(14.,10.5))


def test_complete_scope_is_native_bound_and_skips_virtual_or_partial_legs(tmp_path):
    import pcbnew
    board,pair,endpoints=fixture()
    file=str(tmp_path/'complete.kicad_pcb');pcbnew.SaveBoard(file,board)
    loaded=pcbnew.LoadBoard(file)
    assert roadmap.complete_context(loaded,pair,endpoints)['scope']=='fresh_complete_physical_pair'
    partial=list(endpoints);partial[1]=(12.,10.)
    assert roadmap.complete_context(loaded,pair,partial) is None
    item=pcbnew.PCB_TRACK(loaded);item.SetNet(loaded.FindNet(pair['p']))
    item.SetStart(pcbnew.VECTOR2I_MM(10,10));item.SetEnd(pcbnew.VECTOR2I_MM(10.2,10))
    item.SetWidth(pcbnew.FromMM(.25));loaded.Add(item)
    assert roadmap.complete_context(loaded,pair,endpoints) is None
    assert len(list(loaded.GetTracks()))==1


def refine_fixture():
    board,pair,ends=fixture()
    context=roadmap.complete_context(board,pair,ends)
    p,n=[ends[0],ends[1]],[ends[2],ends[3]]
    options=dict(p_span=4.,n_span=4.,width=.25,gap=.25,max_skew=4.,
        preferred_end_direction=None,minimum_end_coherence=None,
        strict_pair_gap=True,existing_signed_skew_mm=0.)
    kwargs=dict(endpoints=(ends[0],ends[2],ends[1],ends[3]),p_clear=lambda a,b:True,
        n_clear=lambda a,b:True,options=options,context=context)
    return p,n,kwargs


def test_successful_incumbent_and_unscoped_portals_never_launch_roadmap():
    p,n,kwargs=refine_fixture()
    with patch.object(roadmap,'search',side_effect=AssertionError('unneeded search')):
        selected,report=roadmap.refine([p],[n],(p,n),**kwargs)
        assert selected==(p,n) and not report['attempted']
        selected,report=roadmap.refine([p],[n],None,**dict(kwargs,context=None))
        assert selected is None and not report['applicable']


def test_refinement_admits_complete_contract_with_existing_objective():
    p,n,kwargs=refine_fixture()
    bad=[p[0],(8.,10.),(8.,14.),(14.,14.),p[1]]
    def offers(start,end,clear,**options):
        return [start,end],dict(visited=1,queries=1,finite_domain_only=True)
    with patch.object(roadmap,'search',side_effect=offers):
        selected,report=roadmap.refine([bad],[n],(bad,n),**kwargs)
    assert selected==(p,n) and report['selected']
    assert report['selected_contract']['ok']
    assert len(report['queries'])<=8


def test_unqualified_or_expired_domain_retains_original_exactly():
    p,n,kwargs=refine_fixture()
    bad=[p[0],(8.,10.),(8.,14.),(14.,14.),p[1]]
    original=(bad,n)
    with patch.object(roadmap,'search',return_value=(None,{})):
        selected,report=roadmap.refine([bad],[n],original,**kwargs)
        assert selected is original and not report['selected']
    with patch.object(roadmap,'search',side_effect=AssertionError('expired')):
        selected,report=roadmap.refine([bad],[n],original,deadline=time.monotonic()-1,**kwargs)
        assert selected is original and report['reason']=='deadline_exhausted'


def test_ranked_contract_refusal_does_not_commit_first_geometrically_legal_pair():
    p,n,kwargs=refine_fixture()
    other=[p[0],(12.,9.5),p[1]]
    diagnostics={}
    result=route._ranked_joint_escape([p,other],[n],**kwargs['options'],
        diagnostics=diagnostics,pair_admission=lambda pp,nn:tuple(pp)!=tuple(p))
    assert result is not None and result[0]==other
    assert diagnostics['contract_rejected']==1


def test_no_whole_pair_policy_is_implicitly_applied_to_generic_joint_escape():
    with patch.object(roadmap,'refine',side_effect=AssertionError('no physical context')):
        result=route._joint_endpoint_escape((0,0),(0,.5),(4,0),(4,.5),
            width=.25,gap=.25,segment_clear=lambda a,b:True)
    assert result is not None
