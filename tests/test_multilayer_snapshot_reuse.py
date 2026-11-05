"""Plan-local acceleration must preserve native geometry and via refusals."""
import pcbnew
import pytest
import cec_fr as fr
import cec_field_coupling as field
from test_lastmile import _board


def solve(board):
    return fr._multilayer_maze_lastmile_ops(board,
        pcbnew.VECTOR2I_MM(1,2),pcbnew.VECTOR2I_MM(5,2),
        board.GetNetcodeFromNetname('/N'),(pcbnew.F_Cu,pcbnew.B_Cu),200000,
        lambda *args:True,width_for_layer=lambda layer:200000,
        start_layers=(pcbnew.F_Cu,),end_layers=(pcbnew.B_Cu,),
        grid_mm=.5,margin_mm=1,max_vias=1)


def ops_key(operations):
    return [[tuple(v) if isinstance(v,pcbnew.VECTOR2I) else v for v in op]
            for op in operations] if operations else None


@pytest.mark.parametrize('obstacle',['none','foreign_copper','foreign_hole'])
def test_native_cached_transition_plan_matches_exhaustive_guard(monkeypatch,obstacle):
    b=_board([(1,2,'/N'),(5,2,'/N')],edge=(0,0,6,4))
    other=pcbnew.NETINFO_ITEM(b,'/OTHER');b.Add(other)
    if obstacle=='foreign_copper':
        t=pcbnew.PCB_TRACK(b);t.SetNet(other);t.SetLayer(pcbnew.In2_Cu)
        t.SetStart(pcbnew.VECTOR2I_MM(3,1));t.SetEnd(pcbnew.VECTOR2I_MM(3,3))
        t.SetWidth(400000);b.Add(t)
    if obstacle=='foreign_hole':
        v=pcbnew.PCB_VIA(b);v.SetNet(other);v.SetPosition(pcbnew.VECTOR2I_MM(3,2))
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(900000);v.SetDrill(600000);b.Add(v)
    before=field._field_snapshot_inventory(b)
    native=fr._via_spot_clear;calls=[]
    def observed(*args,**kwargs):
        assert kwargs['foreign_cache'] is not None and kwargs['_via_holes'] is not None
        calls.append((kwargs['foreign_cache'],kwargs['_via_holes']))
        return native(*args,**kwargs)
    monkeypatch.setattr(fr,'_via_spot_clear',observed)
    cached=solve(b)
    assert calls and all(cache is calls[0][0] and holes is calls[0][1]
                         for cache,holes in calls)
    def exhaustive(*args,**kwargs):
        kwargs.pop('foreign_cache');kwargs.pop('_via_holes')
        return native(*args,**kwargs)
    monkeypatch.setattr(fr,'_via_spot_clear',exhaustive)
    plain=solve(b)
    assert cached and ops_key(cached)==ops_key(plain)
    assert field._field_snapshot_inventory(b)==before
    for op in cached:
        if op[0]=='via':
            assert native(b,op[1],pcbnew.FromMM(op[3]),200000,
                {b.GetNetcodeFromNetname('/N')},drill_nm=pcbnew.FromMM(op[2]),
                net_code=b.GetNetcodeFromNetname('/N'))


def test_each_new_multilayer_plan_rebuilds_after_same_count_hole_move(monkeypatch):
    b=_board([(1,2,'/N'),(5,2,'/N')],edge=(0,0,6,4))
    v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('/N'));v.SetPosition(pcbnew.VECTOR2I_MM(3,2))
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(600000);v.SetDrill(300000);b.Add(v)
    capture=[];snapshot=fr._via_hole_snapshot
    def observed(board):
        result=snapshot(board);capture.append(result);return result
    monkeypatch.setattr(fr,'_via_hole_snapshot',observed)
    assert solve(b)
    v.SetPosition(pcbnew.VECTOR2I_MM(3,3))
    assert solve(b)
    assert len(capture)==2 and capture[0] is not capture[1]
    assert len(capture[0].rows)==len(capture[1].rows)==1
    assert capture[0].rows[0].y!=capture[1].rows[0].y
