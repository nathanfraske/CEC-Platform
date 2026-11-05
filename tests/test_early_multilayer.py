"""A bounded multi-layer pilot gets work before the deep seat product."""
import time

import pcbnew
import pytest

import cec_field_coupling as field
import cec_fr as fr
from test_full_signal_layer_detour import fixture


@pytest.mark.parametrize('turn',[0,90,180,270])
def test_real_native_wall_uses_full_authorized_pool_before_depth_without_moving_any_copper(turn,monkeypatch):
    board=fixture();center=pcbnew.VECTOR2I_MM(4,3)
    a,b=pcbnew.VECTOR2I_MM(2,3),pcbnew.VECTOR2I_MM(6,3)
    for item in [*board.GetTracks(),*board.GetDrawings()]:
        item.Rotate(center,pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    for _ in range(turn//90):
        a=pcbnew.VECTOR2I(center.x+a.y-center.y,center.y-a.x+center.x)
        b=pcbnew.VECTOR2I(center.x+b.y-center.y,center.y-b.x+center.x)
    original=field._field_snapshot_inventory(board)
    seen=[];native=fr._guarded_lastmile_legs
    def observe(*args,**kwargs):
        seen.append(kwargs['allow_maze']);return native(*args,**kwargs)
    monkeypatch.setattr(fr,'_guarded_lastmile_legs',observe)
    report={};received=[]
    result=fr._lastmile_bridge(board,tuple(a),{pcbnew.B_Cu},tuple(b),{pcbnew.B_Cu},
        200000,board.GetNetcodeFromNetname('/N'),[int(pcbnew.B_Cu),int(pcbnew.In2_Cu)],200000,
        leg_ok=lambda x,y,half:fr._edge_leg_clear(board,x,y,half),
        seat_limit=1,allow_maze=True,maze_margin_mm=1,
        multilayer_lays=[int(pcbnew.B_Cu),int(pcbnew.In2_Cu),int(pcbnew.F_Cu)],
        early_multilayer_pairs=2,deadline_monotonic=time.monotonic()+3.,
        ops_ok=lambda ops:received.append(ops) or True,diagnostics=report)
    assert result and report['early_multilayer_search']['found']
    assert seen and not any(seen), 'Deep same-layer maze monopolized work before pilot'
    assert received[-1]==result and any(op[0]=='trk' and op[4]==pcbnew.F_Cu for op in result)
    assert field._field_snapshot_inventory(board)==original
    assert not report['early_multilayer_search']['release_authority']
    for op in result:
        if op[0]=='via':
            assert fr._via_spot_clear(board,op[1],pcbnew.FromMM(op[3]),200000,
                {board.GetNetcodeFromNetname('/N')},drill_nm=pcbnew.FromMM(op[2]),
                net_code=board.GetNetcodeFromNetname('/N'))
        else:
            assert op[3]==200000 and fr._tap_foreign_clear(board,op[1],op[2],op[3],op[4],
                200000,{board.GetNetcodeFromNetname('/N')})


def test_pilot_does_not_bypass_complete_proposal_or_field_receiving():
    board=fixture();before=field._field_snapshot_inventory(board);report={};seen=[]
    result=fr._lastmile_bridge(board,(2000000,3000000),{pcbnew.B_Cu},
        (6000000,3000000),{pcbnew.B_Cu},200000,board.GetNetcodeFromNetname('/N'),
        [int(pcbnew.B_Cu),int(pcbnew.In2_Cu)],200000,seat_limit=1,allow_maze=True,
        maze_margin_mm=1,multilayer_lays=[int(pcbnew.B_Cu),int(pcbnew.In2_Cu),int(pcbnew.F_Cu)],
        early_multilayer_pairs=1,deadline_monotonic=time.monotonic()+1.,
        ops_ok=lambda ops:seen.append(ops) or False,diagnostics=report)
    assert result is None and seen and not report['early_multilayer_search']['found']
    assert field._field_snapshot_inventory(board)==before


@pytest.mark.parametrize('value',[True,-1,9,None])
def test_pilot_breadth_is_finite_and_explicit(value):
    board=fixture()
    with pytest.raises(ValueError,match='finite early multilayer breadth required'):
        fr._lastmile_bridge(board,(2000000,3000000),{pcbnew.B_Cu},
            (6000000,3000000),{pcbnew.B_Cu},200000,board.GetNetcodeFromNetname('/N'),
            [int(pcbnew.B_Cu)],200000,early_multilayer_pairs=value)


def test_expired_pilot_has_no_work_or_global_no_path_claim():
    board=fixture();report={}
    result=fr._lastmile_bridge(board,(2000000,3000000),{pcbnew.B_Cu},
        (6000000,3000000),{pcbnew.B_Cu},200000,board.GetNetcodeFromNetname('/N'),
        [int(pcbnew.B_Cu),int(pcbnew.In2_Cu)],200000,early_multilayer_pairs=2,
        deadline_monotonic=time.monotonic()-1,diagnostics=report)
    assert result is None and not report['layers'] and not report['no_path_proof']
