"""A route rejected for a backwards notch must not end an easy search."""
import time
from pathlib import Path
import pcbnew
import pytest
import cec_fr as fr
import cec_route_quality as quality
import cec_field_coupling as field
import cec_force_current as force
import cec_native_portal_geometry as portal
import cec_ordinary_signal_completion as ordinary
from test_native_portal_independent_lanes import contained_control_fixture,lane
from test_ordinary_native_portals import target


DIRECTIONS=((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1))


def test_all_direction_histories_match_the_independent_saved_geometry_policy():
    for previous,u in enumerate(DIRECTIONS):
        for prior,v in enumerate(DIRECTIONS):
            for direction,w in enumerate(DIRECTIONS):
                points=[(0,0),u,(u[0]+v[0],u[1]+v[1]),
                    (u[0]+v[0]+w[0],u[1]+v[1]+w[1])]
                refused=sum(a*b for a,b in zip(v,w))<0 or quality._reverse_route_notch(
                    *points,tolerance_nm=0)
                actual=fr._multilayer_canonical_history_step(previous,prior,direction)
                assert (actual is None)==refused,(previous,prior,direction)
                if actual is not None:assert actual==(previous if prior==direction else prior)
    for sentinel in(-1,-2):
        for direction in range(8):assert fr._multilayer_canonical_history_step(-1,sentinel,direction)==-1


def test_search_dominance_retains_both_distinct_arrival_runs():
    a=(1,2,pcbnew.F_Cu,4,0,5);b=(1,2,pcbnew.F_Cu,4,0,0)
    assert fr._multilayer_dominance_key(a,heading_memory=True)==fr._multilayer_dominance_key(b,heading_memory=True)
    assert fr._multilayer_dominance_key(a,heading_memory=True,jog_memory=True)!=fr._multilayer_dominance_key(
        b,heading_memory=True,jog_memory=True)


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('reflect',[False,True])
@pytest.mark.parametrize('capture',[0.,1.])
def test_search_keeps_alternative_when_cheaper_path_has_reverse_notch(monkeypatch,rotation,reflect,capture):
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'/renamed_control');board.Add(net)
    def pt(x,y):
        if reflect:x=-x
        for _ in range(rotation):x,y=y,-x
        return pcbnew.VECTOR2I_MM(x,y)
    paths=[[(0,0),(1,-1),(2,0),(3,-1),(4,-1)],[(0,0),(0,2),(4,2),(4,-1)]]
    segments=[(pt(*a),pt(*b))for path in paths for a,b in zip(path,path[1:])]
    def contained(p,a,b):
        dx,dy=b.x-a.x,b.y-a.y;px,py=p.x-a.x,p.y-a.y
        return dx*py==dy*px and 0<=px*dx+py*dy<=dx*dx+dy*dy
    def clear(a,b,*args):return any(contained(a,p,q)and contained(b,p,q)for p,q in segments)
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',clear)
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**kw:False)
    def run(mode):
        return fr._multilayer_maze_lastmile_ops(board,pt(0,0),pt(4,-1),net.GetNetCode(),
            (pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,width_for_layer=lambda _:200000,
            start_layers=(pcbnew.F_Cu,),end_layers=(pcbnew.F_Cu,),grid_mm=.5,max_vias=0,
            margin_mm=2,heuristic_weight=3.,terminal_capture_mm=capture,neutral_state_dominance=True,
            canonical_turns_only=mode,deadline_monotonic=time.monotonic()+2.)
    def notches(ops):
        points=[tuple(ops[0][1])]+[tuple(o[2])for o in ops]
        return [quality._reverse_route_notch(*points[i:i+4],tolerance_nm=0)for i in range(len(points)-3)]
    old=run(False);new=run(True)
    assert old and any(notches(old))
    assert new and not any(notches(new))and all(clear(o[1],o[2])for o in new)
    assert tuple(new[0][1])==tuple(pt(0,0))and tuple(new[-1][2])==tuple(pt(4,-1))
    assert not list(board.GetTracks())


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('smd_first',[False,True])
def test_fixed_uuid_orders_both_launch_directions_receive_real_saved_join(tmp_path,face,reverse,smd_first):
    source,board,net,request=contained_control_fixture(tmp_path,face)
    pads={p.GetNumber():p for f in board.GetFootprints()for p in f.Pads()if p.GetNetname()==net}
    assert set(pads)=={'1','2'}
    # Deliberately exercise both Source identity orders, rather than relying
    # on a random UUID to choose the direction that happens to succeed.
    pads['1'].m_Uuid.Clone(pcbnew.KIID('10000000-0000-4000-8000-00000000000'+('1'if smd_first else'2')))
    pads['2'].m_Uuid.Clone(pcbnew.KIID('10000000-0000-4000-8000-00000000000'+('2'if smd_first else'1')))
    field._save_field_snapshot(board,source);board=pcbnew.LoadBoard(str(source))
    q=ordinary.plan(board,source,board_hint='synthetic',net=net);assert q['complete']
    request=target(board,q);request.update(retained_same_face_track_ends=True,
        retained_barrel_face_access=True,source_local_pad_rule_launches=True,
        source_local_contained_intervals_only=True)
    route_face=int(pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu)
    child=force._copy_family(source,tmp_path/'fixed-order-child');before=source.read_bytes()
    result=portal.apply_native_portals(child,request,9.,lane=lane(
        'source_local_face',first=route_face,last=route_face,reverse=reverse))
    assert result['closed']==1,result
    import cec_additive_route_receiving as additive
    for receiver in(ordinary,additive):
        options=dict(net=net)if receiver is ordinary else{}
        proof=receiver.receive(source,child,board_hint='synthetic',timeout_s=9.,**options)
        assert proof['complete']and proof['ok'],proof
    assert source.read_bytes()==before
    assert result['proposal_guard']['passed']>0
    assert result['source_local_pad_rule_launches']['attempts'][0]['proposal_guard_last_attempt']
