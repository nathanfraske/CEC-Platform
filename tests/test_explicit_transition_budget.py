"""A bounded transition budget changes search, never native geometry authority."""
import time
import inspect
import pytest
import pcbnew
import cec_fr as fr
from test_multilayer_route_graph import board_net


@pytest.mark.parametrize('budget',[2,4])
def test_alternating_corridor_requires_four_guarded_transitions(monkeypatch,budget):
    b,n=board_net();d={};checked=[]
    monkeypatch.setattr(fr,'_foreign_shape_indexes',lambda b,l,*a,**k:(l,[]))
    def planar(a,z,w,g,l,c):
        if a.y or z.y:return False
        lo,hi=sorted((a.x,z.x))
        return any(k*1000000<=lo<=hi<=(k+1)*1000000 and
            l==(pcbnew.F_Cu if k%2==0 else pcbnew.B_Cu) for k in range(5))
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',planar)
    def via(b,p,*a,**k):
        checked.append(tuple(p))
        return p.y==0 and p.x in (1000000,2000000,3000000,4000000)
    monkeypatch.setattr(fr,'_via_spot_clear',via)
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    result=fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),
        pcbnew.VECTOR2I_MM(5,0),n.GetNetCode(),[pcbnew.F_Cu,pcbnew.B_Cu],200000,
        lambda a,z,h:0<=a.x<=5000000 and 0<=z.x<=5000000,
        width_for_layer=lambda l:200000,start_layers=[pcbnew.F_Cu],end_layers=[pcbnew.F_Cu],
        grid_mm=.5,margin_mm=.5,max_vias=budget,diagnostics=d,
        deadline_monotonic=time.monotonic()+2.)
    assert (result is not None)==(budget==4)
    if result:assert sum(op[0]=='via' for op in result)==4
    assert checked and d['max_vias']==budget
    assert not d['release_authority'] and not d['no_path_proof'] and not list(b.GetTracks())


@pytest.mark.parametrize('budget',[True,-1,9,2.5,None,float('nan')])
def test_transition_budgets_are_bounded_integers(budget):
    b,n=board_net()
    with pytest.raises(ValueError,match='transition_budget'):
        fr._multilayer_maze_lastmile_ops(b,pcbnew.VECTOR2I_MM(0,0),pcbnew.VECTOR2I_MM(5,0),
            n.GetNetCode(),[0,2],200000,lambda *a:True,width_for_layer=lambda l:200000,max_vias=budget)
    with pytest.raises(ValueError,match='transition_budget'):
        fr._lastmile_bridge(b,(0,0),[0],(5000000,0),[0],200000,n.GetNetCode(),[0,2],200000,
            middle_max_vias=budget)


@pytest.mark.parametrize('budget',[0,2,6])
def test_bridge_forwards_explicit_middle_budget_without_changing_default(monkeypatch,budget):
    b,n=board_net();seen=[]
    monkeypatch.setattr(fr._fab,'board_profile_name',lambda b:None)
    signature=inspect.signature(fr._multilayer_maze_lastmile_ops)
    def middle(*a,**kw):
        signature.bind(*a,**kw)
        seen.append(kw['max_vias']);return None
    monkeypatch.setattr(fr,'_multilayer_maze_lastmile_ops',middle)
    fr._lastmile_bridge(b,(0,0),[0],(5000000,0),[0],200000,n.GetNetCode(),[0,2],200000,
        _multilayer_only=True,middle_max_vias=budget,deadline_monotonic=time.monotonic()+2.)
    assert seen==[budget]
