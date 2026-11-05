"""Direction-dependent route style must remain in the search state."""
import math
import time
import pcbnew
import pytest
import cec_fr as fr


def test_style_frontier_does_not_dominate_another_arrival_heading():
    a=(1,2,pcbnew.F_Cu,0,0);b=(1,2,pcbnew.F_Cu,4,0)
    assert fr._multilayer_dominance_key(a)==fr._multilayer_dominance_key(b)
    assert fr._multilayer_dominance_key(a,heading_memory=True)!=fr._multilayer_dominance_key(b,heading_memory=True)


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('capture',[0.,1.])
def test_search_and_terminal_capture_do_not_emit_internal_acute_backtracks(monkeypatch,rotation,capture):
    b=pcbnew.BOARD();n=pcbnew.NETINFO_ITEM(b,'/other/renamed/control');b.Add(n)
    def pt(x,y):
        for _ in range(rotation):x,y=y,-x
        return pcbnew.VECTOR2I_MM(x,y)
    # Short tempting route has an acute join; a longer complete alternative
    # exists. Guards admit only these whole segments (and their subsegments).
    paths=[[(0,0),(1,1),(.5,1),(.5,2),(2,2),(2,1)],
           [(0,0),(0,-1),(3,-1),(3,1),(2,1)]]
    segments=[(pt(*a),pt(*c)) for path in paths for a,c in zip(path,path[1:])]
    def contained(p,a,c):
        dx,dy=c.x-a.x,c.y-a.y;px,py=p.x-a.x,p.y-a.y
        return dx*py==dy*px and 0<=px*dx+py*dy<=dx*dx+dy*dy
    def clear(a,c,*args):
        return any(contained(a,p,q) and contained(c,p,q) for p,q in segments)
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',clear)
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:False)
    s,t=pt(0,0),pt(2,1)
    def run(mode):
        return fr._multilayer_maze_lastmile_ops(b,s,t,n.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),
            200000,lambda *a:True,width_for_layer=lambda _:200000,
            start_layers=(pcbnew.F_Cu,),end_layers=(pcbnew.F_Cu,),grid_mm=.5,
            max_vias=0,margin_mm=1,heuristic_weight=3.,terminal_capture_mm=capture,
            neutral_state_dominance=True,deadline_monotonic=time.monotonic()+2,
            canonical_turns_only=mode)
    def turns(ops):
        vectors=[(o[2].x-o[1].x,o[2].y-o[1].y) for o in ops]
        return [sum(x*y for x,y in zip(a,c)) for a,c in zip(vectors,vectors[1:])]
    legacy=run(False);ops=run(True)
    assert legacy and min(turns(legacy))<0
    assert ops and min(turns(ops))>=0 and all(clear(o[1],o[2]) for o in ops)
    assert tuple(ops[0][1])==tuple(s) and tuple(ops[-1][2])==tuple(t)
    assert not list(b.GetTracks())


@pytest.mark.parametrize('bad',[None,1,'yes'])
def test_canonical_turn_mode_requires_explicit_boolean(bad):
    with pytest.raises(ValueError,match='explicit_multilayer_canonical_turns_required'):
        fr._multilayer_maze_lastmile_ops(pcbnew.BOARD(),pcbnew.VECTOR2I(0,0),pcbnew.VECTOR2I(1,1),
            1,(pcbnew.F_Cu,pcbnew.B_Cu),200000,lambda *a:True,
            width_for_layer=lambda _:200000,canonical_turns_only=bad)
