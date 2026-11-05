"""Board-scale planar search is an explicit bounded reuse, never via credit."""
import math
import time
import pcbnew
import pytest
import cec_fr as fr


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_native_single_face_escapes_endpoint_window_without_width_or_layer_change(turn,mirror,face):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'/renamed/power');foreign=pcbnew.NETINFO_ITEM(board,'/different/blocker')
    board.Add(net);board.Add(foreign)
    def pt(x,y):
        if mirror:x=-x
        for _ in range(turn):x,y=-y,x
        return pcbnew.VECTOR2I_MM(25+x,25+y)
    corners=[pt(0,0),pt(20,0),pt(20,12),pt(0,12)]
    for a,b in zip(corners,corners[1:]+corners[:1]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(a);edge.SetEnd(b);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(50000);board.Add(edge)
    wall=pcbnew.PCB_TRACK(board);wall.SetStart(pt(10,0));wall.SetEnd(pt(10,8))
    wall.SetWidth(800000);wall.SetLayer(face);wall.SetNetCode(foreign.GetNetCode());board.Add(wall)
    source,target=pt(6,6),pt(14,6)
    original=(wall.m_Uuid.AsString(),tuple(wall.GetStart()),tuple(wall.GetEnd()),wall.GetWidth(),wall.GetLayer(),wall.GetNetCode())
    def run(enabled,envelope):
        detail={}
        ops=fr._multilayer_maze_lastmile_ops(board,source,target,net.GetNetCode(),[face],200000,
            lambda a,b,h:fr._edge_leg_clear(board,a,b,h),width_for_layer=lambda _:400000,
            start_layers=[face],end_layers=[face],grid_mm=.5,margin_mm=1,max_vias=0,
            deadline_monotonic=time.monotonic()+2.,canonical_turns_only=True,
            native_board_envelope=envelope,allow_single_layer=enabled,diagnostics=detail)
        return ops,detail
    legacy,legacy_detail=run(False,True)
    assert legacy is None and legacy_detail['stop']=='insufficient_layers'
    limited,limited_detail=run(True,False)
    assert limited is None and limited_detail['stop']=='bounded_graph_exhausted'
    ops,detail=run(True,True)
    assert ops and detail['stop']=='found' and detail['single_layer_mode_active']
    assert not detail['no_path_proof'] and not detail['release_authority']
    assert tuple(ops[0][1])==tuple(source) and tuple(ops[-1][2])==tuple(target)
    for op in ops:
        assert op[0]=='trk' and op[3]==400000 and op[4]==face
        a,b=op[1:3];dx,dy=b.x-a.x,b.y-a.y
        assert dx==0 or dy==0 or abs(dx)==abs(dy)
        assert fr._edge_leg_clear(board,a,b,200000)
        assert fr._tap_foreign_clear(board,a,b,400000,face,200000,{net.GetNetCode()})
    assert len(list(board.GetTracks()))==1
    assert (wall.m_Uuid.AsString(),tuple(wall.GetStart()),tuple(wall.GetEnd()),wall.GetWidth(),wall.GetLayer(),wall.GetNetCode())==original


@pytest.mark.parametrize('bad',[None,0,1,'yes',float('nan')])
def test_single_face_policy_is_not_truthy_inferred(bad):
    with pytest.raises(ValueError,match='explicit_bounded_single_layer_search_required'):
        fr._multilayer_maze_lastmile_ops(pcbnew.BOARD(),pcbnew.VECTOR2I(0,0),pcbnew.VECTOR2I(1,1),
            1,[pcbnew.F_Cu],200000,lambda *a:True,width_for_layer=lambda _:200000,allow_single_layer=bad)


@pytest.mark.parametrize('vias,deadline',[(1,1.),(0,None),(0,float('inf')),(0,20.)])
def test_single_face_does_not_infer_transition_or_work_permission(vias,deadline):
    lease=time.monotonic()+deadline if deadline is not None else None
    with pytest.raises(ValueError,match='single_layer_search_requires_zero_vias_and_explicit_lease'):
        fr._multilayer_maze_lastmile_ops(pcbnew.BOARD(),pcbnew.VECTOR2I(0,0),pcbnew.VECTOR2I(1,1),
            1,[pcbnew.F_Cu],200000,lambda *a:True,width_for_layer=lambda _:200000,
            max_vias=vias,deadline_monotonic=lease,allow_single_layer=True)


def test_one_face_does_not_create_other_endpoint_access():
    report={}
    assert fr._multilayer_maze_lastmile_ops(pcbnew.BOARD(),pcbnew.VECTOR2I(0,0),pcbnew.VECTOR2I(1,1),
        1,[pcbnew.F_Cu],200000,lambda *a:True,width_for_layer=lambda _:200000,
        start_layers=[pcbnew.B_Cu],max_vias=0,deadline_monotonic=time.monotonic()+1.,
        allow_single_layer=True,diagnostics=report) is None
    assert report['stop']=='no_endpoint_layer_access' and report['tested_hops']==0


def test_unenabled_layer_refuses_without_native_hop():
    report={}
    assert fr._multilayer_maze_lastmile_ops(pcbnew.BOARD(),pcbnew.VECTOR2I(0,0),pcbnew.VECTOR2I(1,1),
        1,[pcbnew.In2_Cu],200000,lambda *a:True,width_for_layer=lambda _:200000,
        max_vias=0,deadline_monotonic=time.monotonic()+1.,allow_single_layer=True,diagnostics=report) is None
    assert report['stop']=='single_layer_not_enabled_or_is_plane' and report['tested_hops']==0
