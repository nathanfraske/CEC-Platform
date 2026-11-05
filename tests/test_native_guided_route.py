"""Guides cannot bypass native guards, hide a failed leg, or multiply budgets."""
from unittest.mock import patch
import pcbnew
import pytest
import cec_native_guided_route as guided
import cec_fr as fr
from test_lastmile import _board


def request():
    b=_board([(10,20,'RENAMED')]);code=b.GetNetcodeFromNetname('RENAMED')
    points=[(0,0),(40,0),(40,40),(0,40),(0,0)]
    for start,end in zip(points,points[1:]):
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetWidth(50000);edge.SetStart(pcbnew.VECTOR2I_MM(*start));edge.SetEnd(pcbnew.VECTOR2I_MM(*end));b.Add(edge)
    return b,code,dict(width_for_layer=lambda l:200000,start_layers=[0],end_layers=[0],
        waypoints=[dict(at_nm=[15000000,20000000],layer=0)],drill=.3,dia=.6)


@pytest.mark.parametrize('angle',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_native_complete_guided_search_keeps_faces_width_and_guards(angle,mirror):
    b,code,kw=request()
    def at(x,y):
        if mirror:x=-x
        for _ in range(angle):x,y=-y,x
        return pcbnew.VECTOR2I(20000000+x,20000000+y)
    kw['waypoints'][0]['at_nm']=list(at(0,0))
    detail={};old=len(list(b.GetTracks()))
    ops=guided.plan(b,at(-5000000,0),at(5000000,0),code,[0,2],200000,
        lambda *a:True,diagnostics=detail,**kw)
    assert ops and detail['complete_route'] and not detail['routing_admitted']
    assert all(op[3]==200000 for op in ops if op[0]=='trk')
    assert len(list(b.GetTracks()))==old and not detail['partial_geometry_returned']


def test_a_late_failed_leg_never_returns_the_early_partial_route():
    b,code,kw=request();detail={}
    first=[('trk',pcbnew.VECTOR2I_MM(10,20),pcbnew.VECTOR2I_MM(15,20),200000,0)]
    with patch.object(fr,'_multilayer_maze_lastmile_ops',side_effect=[first,None]) as search:
        ops=guided.plan(b,pcbnew.VECTOR2I_MM(10,20),pcbnew.VECTOR2I_MM(20,20),code,[0,2],
            200000,lambda *a:True,diagnostics=detail,**kw)
    assert ops is None and not detail['complete_route'] and detail['completed_legs']==1
    assert search.call_count==2 and not list(b.GetTracks())


def test_actual_foreign_pad_at_the_final_guide_cannot_be_accepted():
    b,code,kw=request();foreign=pcbnew.NETINFO_ITEM(b,'OTHER');b.Add(foreign)
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);fp.Add(pad)
    pad.SetNet(foreign);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(1,1));pad.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    detail={}
    ops=guided.plan(b,pcbnew.VECTOR2I_MM(10,20),pcbnew.VECTOR2I_MM(20,20),code,[0],200000,
        lambda *a:True,max_expanded_states=50,diagnostics=detail,**kw)
    assert ops is None and detail['legs'][0]['found'] and not detail['complete_route']
    assert not list(b.GetTracks())


def test_via_and_length_budgets_belong_to_the_whole_route_not_each_leg():
    b,code,kw=request();start=pcbnew.VECTOR2I_MM(10,20);mid=pcbnew.VECTOR2I_MM(15,20)
    first=[('via',start,.3,.6),('trk',start,mid,200000,0)]
    with patch.object(fr,'_multilayer_maze_lastmile_ops',side_effect=[first,None]) as search:
        guided.plan(b,start,pcbnew.VECTOR2I_MM(20,20),code,[0,2],200000,lambda *a:True,
            max_vias=1,max_length_nm=12000000,**kw)
    assert search.call_args_list[1].kwargs['max_vias']==0
    assert search.call_args_list[1].kwargs['max_length_nm']==7000000


@pytest.mark.parametrize('fault',['face','boolean','extra','too_many'])
def test_invalid_guides_refuse_before_search(fault):
    b,code,kw=request()
    if fault=='face':kw['waypoints'][0]['layer']=4
    elif fault=='boolean':kw['waypoints'][0]['at_nm'][0]=True
    elif fault=='extra':kw['waypoints'][0]['width_nm']=100000
    else:kw['waypoints']*=9
    with patch.object(fr,'_multilayer_maze_lastmile_ops') as search,pytest.raises(ValueError):
        guided.plan(b,pcbnew.VECTOR2I_MM(10,20),pcbnew.VECTOR2I_MM(20,20),code,[0,2],200000,lambda *a:True,**kw)
    search.assert_not_called()
