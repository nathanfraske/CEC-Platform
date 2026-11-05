"""A refused direct face route must not ban legal face copper from detours."""
import pcbnew
import pytest
import cec_fr as fr
import cec_field_coupling as field
from test_lastmile import _board


def fixture():
    b=_board([],edge=(0,0,8,6));b.SetCopperLayerCount(6)
    for name in ('/N','/OTHER'):
        b.Add(pcbnew.NETINFO_ITEM(b,name))
    # Two bridge layers are physically cut by one immutable foreign wall.
    # F.Cu remains available only after the endpoints' existing B.Cu access.
    for layer in (pcbnew.In2_Cu,pcbnew.B_Cu):
        t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('/OTHER'));t.SetLayer(layer)
        t.SetStart(pcbnew.VECTOR2I_MM(4,-2));t.SetEnd(pcbnew.VECTOR2I_MM(4,8))
        t.SetWidth(600000);b.Add(t)
    return b


def test_native_full_pool_detours_over_immutable_two_layer_wall():
    b=fixture();before=field._field_snapshot_inventory(b);nc=b.GetNetcodeFromNetname('/N')
    layers=[int(pcbnew.B_Cu),int(pcbnew.In2_Cu)]
    def solve(pool):
        return fr._lastmile_bridge(b,(2000000,3000000),{pcbnew.B_Cu},
            (6000000,3000000),{pcbnew.B_Cu},200000,nc,layers,200000,
            leg_ok=lambda a,z,half: fr._edge_leg_clear(b,a,z,half),
            seat_limit=1,allow_maze=True,maze_margin_mm=1,multilayer_lays=pool)
    assert solve(layers) is None
    actual=solve(layers+[int(pcbnew.F_Cu)])
    assert actual and any(op[0]=='trk' and op[4]==pcbnew.F_Cu for op in actual)
    assert sum(op[0]=='via' for op in actual)==2
    assert field._field_snapshot_inventory(b)==before
    for op in actual:
        if op[0]=='via':
            assert fr._via_spot_clear(b,op[1],pcbnew.FromMM(op[3]),200000,{nc},
                drill_nm=pcbnew.FromMM(op[2]),net_code=nc)
        else:
            assert fr._tap_foreign_clear(b,op[1],op[2],op[3],op[4],200000,{nc})


@pytest.mark.parametrize('invalid',[[-1],[999],[True],[]])
def test_invalid_or_incomplete_pool_cannot_authorize_layers(invalid):
    b=fixture()
    with pytest.raises(ValueError,match='authorized non-plane'):
        fr._lastmile_bridge(b,(2000000,3000000),{pcbnew.B_Cu},
            (6000000,3000000),{pcbnew.B_Cu},200000,b.GetNetcodeFromNetname('/N'),
            [int(pcbnew.B_Cu)],200000,multilayer_lays=invalid)


def test_production_ordinary_completion_supplies_full_profile_authority(monkeypatch):
    b=_board([(2,3,'/N'),(6,3,'/N')],edge=(0,0,8,6));b.SetCopperLayerCount(6)
    pools=[]
    def observed(*args,**kwargs):
        pools.append(kwargs['multilayer_lays']);return None
    monkeypatch.setattr(fr,'_lastmile_bridge',observed)
    fr.synthesize_lastmile(b,include_nets=['/N'],max_mm=10,min_w=.2,clearance=.2,
        prefer_bridge=True,maze_max_mm=0,attempts_per_pair=1)
    assert pools and all(pcbnew.F_Cu in pool for pool in pools)
    assert all(pcbnew.In1_Cu not in pool for pool in pools)


@pytest.mark.parametrize('finish_layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_selected_native_launch_layer_omits_only_unused_new_endpoint_barrel(monkeypatch,finish_layer):
    b=_board([(2,3,'/N'),(6,3,'/N')],edge=(0,0,8,6));b.SetCopperLayerCount(6)
    b.BuildConnectivity();before=field._field_snapshot_inventory(b);details={}
    monkeypatch.setattr(fr,'_guarded_lastmile_legs',lambda *args,**kw:None)
    def middle(_board,a,z,nc,layers,clearance,guard,**kw):
        # Start is existing B.Cu access; only the F.Cu endpoint has a proposed
        # in-pad seat. A selected B.Cu finish NEEDS that seat. An F.Cu finish
        # reaches the actual native land without it.
        return [('trk',a,z,200000,finish_layer)]
    monkeypatch.setattr(fr,'_multilayer_maze_lastmile_ops',middle)
    received=[]
    ops=fr._lastmile_bridge(b,(2000000,3000000),{pcbnew.B_Cu},
        (6000000,3000000),{pcbnew.F_Cu},200000,b.GetNetcodeFromNetname('/N'),
        [int(pcbnew.B_Cu),int(pcbnew.In2_Cu)],200000,allow_maze=True,seat_limit=1,
        multilayer_lays=[int(pcbnew.B_Cu),int(pcbnew.In2_Cu),int(pcbnew.F_Cu)],
        ops_ok=lambda plan: received.append(plan) or True,diagnostics=details)
    assert ops and received[-1]==ops
    assert sum(op[0]=='via' for op in ops)==(finish_layer!=pcbnew.F_Cu)
    assert details['counters'].get('unused_proposed_endpoint_vias_omitted',0)==(
        finish_layer==pcbnew.F_Cu)
    assert field._field_snapshot_inventory(b)==before
