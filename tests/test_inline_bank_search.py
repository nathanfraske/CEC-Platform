"""Native inline topology search without board names or coordinates as policy."""
import math
from unittest.mock import patch
import pytest
import pcbnew
import cec_precision_route as route
import cec_endpoint_roadmap as roadmap
from cec_native_copper_snapshot import CopperSnapshot


def fixture(transform=lambda p:p):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    pair=dict(name='unnamed-pair',p='renamed/positive',n='renamed/negative',
              width=.2,gap=.34,clearance=.2,kind='usb')
    for net in (pair['p'],pair['n'],'reference'):
        board.Add(pcbnew.NETINFO_ITEM(board,net))
    for ref,xs in [('LEFT',(0.,)),('PROTECTOR',(4.,6.)),('RIGHT',(10.,))]:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
        for x in xs:
            for name,y in ((pair['p'],0.),(pair['n'],1.)):
                pad=pcbnew.PAD(fp);pad.SetNumber('%s-%g'%(name,x))
                pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
                pad.SetSize(pcbnew.VECTOR2I_MM(.6,.4))
                layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
                pad.SetPosition(pcbnew.VECTOR2I_MM(*transform((x,y))))
                pad.SetNet(board.FindNet(name));fp.Add(pad)
    return board,pair,route._flow_through_pair_legs(board,pair)


@pytest.mark.parametrize('transform',[
    lambda p:p,lambda p:(p[0]+31,p[1]-17),
    lambda p:(-p[1],p[0]),lambda p:(-p[0],p[1])])
def test_bank_alternatives_preserve_every_physical_contact_and_polarity(transform):
    board,pair,(legs,stations)=fixture(transform)
    variants=list(route._flow_bank_candidates(legs,stations))
    assert len(variants)==2 and variants[0]['legs']==legs
    assert variants[1]['reversed_stations']==stations
    for member in ((0,1),(2,3)):
        assert sorted(p for leg in legs for i,p in enumerate(leg) if i in member)==sorted(
            p for leg in variants[1]['legs'] for i,p in enumerate(leg) if i in member)
    for variant in variants:
        for leg in variant['legs']:
            context=roadmap.inline_context(board,pair,leg,
                minimum_coupled_fraction=.35,clearance_mm=.2)
            assert context['scope']=='physical_inline_leg'
            assert context['minimum_coupled_fraction']==.35
    assert len(list(route._flow_bank_candidates(legs,stations,max_variants=1)))==1


def test_no_exponential_enumeration_for_long_inline_chain():
    legs=[((float(i),0),(float(i)+.5,0),(float(i),1),(float(i)+.5,1)) for i in range(30)]
    variants=list(route._flow_bank_candidates(legs,[str(i) for i in range(29)],max_variants=5))
    assert len(variants)==5


def track(board,net='reference'):
    item=pcbnew.PCB_TRACK(board);item.SetNet(board.FindNet(net))
    item.SetStart(pcbnew.VECTOR2I_MM(20,20));item.SetEnd(pcbnew.VECTOR2I_MM(21,20))
    item.SetWidth(pcbnew.FromMM(.2));item.SetLayer(pcbnew.F_Cu);board.Add(item)
    return item


def test_existing_package_ties_do_not_disable_inline_search_but_virtual_portals_do():
    board,pair,(legs,stations)=fixture()
    track(board,pair['p'])
    assert roadmap.complete_context(board,pair,legs[0]) is None
    assert roadmap.inline_context(board,pair,legs[0],
        minimum_coupled_fraction=.35,clearance_mm=.2)
    virtual=list(legs[0]);virtual[1]=(3.5,0.)
    assert roadmap.inline_context(board,pair,virtual,
        minimum_coupled_fraction=.35,clearance_mm=.2) is None


def test_search_nominal_gap_stays_default_and_explicit_terminal_floor_is_hard():
    anchor=[(0.,0.),(4.,0.)]
    kwargs=dict(anchor=anchor,width=.2,gap=.34,max_visited=1000)
    path,_=roadmap.search((0.,.5),(4.,.5),lambda a,b:True,**kwargs)
    assert path is None
    path,_=roadmap.search((0.,.5),(4.,.5),lambda a,b:True,
        minimum_spacing=.4,**kwargs)
    assert path and all(route._seg_seg_dist(a,b,*anchor)>=.4-1e-6
                        for a,b in zip(path,path[1:]))
    with pytest.raises(ValueError):
        roadmap.search((0.,.5),(4.,.5),lambda a,b:True,
                       minimum_spacing=.1,**kwargs)


def test_rejected_bank_removes_generated_returns_and_restores_package_ties():
    board,pair,(legs,stations)=fixture();parent=track(board)
    parent_id=parent.m_Uuid.AsString();tie=track(board,pair['p'])
    tie_id=tie.m_Uuid.AsString();snapshot=CopperSnapshot(board,{tie_id})
    seen=[]
    def solve(b,p,ends,*args,**kwargs):
        assert {item.m_Uuid.AsString() for item in b.GetTracks()}=={parent_id,tie_id}
        seen.append(ends);track(b)
        return dict(name=pair['name'],segments=2)
    def qualify(result):
        if len(seen)==1:
            from cec_native_items import discard_items
            discard_items(board,[i for i in board.GetTracks() if i.m_Uuid.AsString()==tie_id])
            return dict(result,refused='independent physics failed')
        return result
    with patch.object(route,'_route_flow_leg_orders',side_effect=solve):
        result=route._route_flow_bank_orders(board,pair,legs,stations,
            candidate_qualifier=qualify,restore_parent=snapshot.restore)
    assert len(seen)==2 and not result.get('refused')
    assert result['flow_bank_selection']==stations
    assert result['flow_bank_attempts'][0]['refused']=='independent physics failed'
    assert len(list(board.GetTracks()))==3


def test_successful_first_bank_is_not_mutated_by_exploring_alternatives():
    board,pair,(legs,stations)=fixture();item=track(board)
    with patch.object(route,'_route_flow_leg_orders',return_value={'segments':2}) as solve:
        result=route._route_flow_bank_orders(board,pair,legs,stations)
    assert solve.call_count==1 and result['flow_bank_selection']==[]
    assert len(list(board.GetTracks()))==1


def test_all_failed_banks_are_atomic_and_not_reported_as_success():
    board,pair,(legs,stations)=fixture();parent=track(board)
    def solve(b,*args,**kwargs):
        track(b);return dict(refused='native guard refused')
    with patch.object(route,'_route_flow_leg_orders',side_effect=solve):
        result=route._route_flow_bank_orders(board,pair,legs,stations)
    assert result['refused'] and len(result['flow_bank_attempts'])==2
    assert len(list(board.GetTracks()))==1
