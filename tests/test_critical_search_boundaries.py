import math
from unittest.mock import Mock,patch
import pcbnew
import pytest
import cec_precision_route as route


@pytest.mark.parametrize('side',('start','end'))
@pytest.mark.parametrize('octant',range(8))
def test_return_probe_uses_local_rotated_throat(side,octant):
    theta=math.pi*octant/4
    heading=(math.cos(theta),math.sin(theta))
    row=dict(side=side,route_heading=heading,p=(1,2),n=(1,3),center=(1,2.5))
    returns=Mock(return_value=([], 'covered'))
    result=route._probe_matched_transition_field(row,p_code=1,n_code=2,
        route_axis=(1,1),add_signal_via=Mock(return_value=object()),add_return_via=returns)
    sign=1 if side=='start' else -1
    assert result['ok']
    assert returns.call_args.kwargs['route_axis']==tuple(sign*v for v in heading)


def test_return_heading_fallback_and_malformed_authority():
    assert route._portal_return_route_axis({},(1,0))==(1,0)
    for heading in ((0,0),(math.nan,1),(1,),()):
        with pytest.raises(ValueError):
            route._portal_return_route_axis(dict(side='start',route_heading=heading),(1,0))


def test_unreachable_terminal_heading_refuses_before_board_scale_search():
    board=pcbnew.BOARD()
    for a,b in (((0,0),(30,0)),((30,0),(30,20)),((30,20),(0,20)),((0,20),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    def clear(a,b,*args,**kwargs):
        return not (abs(a.y/1e6-10)<1e-6 and abs(b.y/1e6-10)<1e-6
                    and max(a.x,b.x)>pcbnew.FromMM(27.75))
    diagnostics={}
    with patch.object(route.cec_fr,'_snapshot_foreign_clear',side_effect=clear), \
         patch.object(route.heapq,'heappop',side_effect=AssertionError('must not search')):
        result=route._grid_coupled_path(board,start_center=(2,10),end_center=(28,10),
            p_start=(2,9.73),n_start=(2,10.27),p_end=(28,9.73),n_end=(28,10.27),
            layer_id=pcbnew.F_Cu,width=.2,gap=.34,clearance=.2,own=set(),
            portal_mode=True,portal_start_heading=(1,0),portal_end_heading=(1,0),
            diagnostics=diagnostics)
    assert result is None
    assert diagnostics['status']=='terminal_heading_blocked'
    assert diagnostics['visited']==0
    assert diagnostics['endpoint_heading_edges']=={'start':[0],'end':[]}


def pair_board(*,long=False,partial=False):
    b=pcbnew.BOARD()
    for index,name in enumerate(('p','n')):
        net=pcbnew.NETINFO_ITEM(b,name);b.Add(net);y=2+index
        for x in (2,10):
            fp=pcbnew.FOOTPRINT(b);fp.SetReference(name+str(x));b.Add(fp)
            pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(net)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetPosition(pcbnew.VECTOR2I_MM(x,y))
            layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers);fp.Add(pad)
        points=([(2,y),(2,10+index),(10,10+index),(10,y)] if long else [(2,y),(10,y)])
        if partial and name=='n':points=[(2,y),(3,y)]
        for a,z in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(pcbnew.F_Cu)
            t.SetWidth(pcbnew.FromMM(.2));t.SetStart(pcbnew.VECTOR2I_MM(*a))
            t.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(t)
    return b


@pytest.mark.parametrize('long,partial,applicable,ok',[(False,False,True,True),
    (True,False,True,False),(True,True,False,True)])
def test_complete_candidate_uses_final_detour_gate_without_claiming_partial_tree(long,partial,applicable,ok):
    board=pair_board(long=long,partial=partial)
    before={(t.m_Uuid.AsString(),t.GetNetname(),t.GetLength()) for t in board.GetTracks()}
    result=route._complete_pair_candidate_detour(board,dict(p='p',n='n'))
    assert result['applicable']==applicable and result['ok']==ok
    assert before=={(t.m_Uuid.AsString(),t.GetNetname(),t.GetLength()) for t in board.GetTracks()}
