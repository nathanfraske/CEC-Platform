"""Renamed native tracks: bounded canonical offsets and protected copper."""
import math
import sys
from pathlib import Path
import pytest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cec_field_coupling_repair as repair


@pytest.mark.parametrize('direction',[(1,0),(-1,0),(0,1),(0,-1),
                                    (1,1),(-1,1),(1,-1),(-1,-1)])
@pytest.mark.parametrize('offset',[-.5,.5])
def test_all_octilinear_headings_keep_exact_graph_endpoints(direction,offset):
    start=(17_000_000,29_000_000)
    end=tuple(start[i]+direction[i]*5_000_000 for i in (0,1))
    first,second=repair.offset_points_nm(start,end,offset)
    points=[start,first,second,end]
    for a,b in zip(points,points[1:]):
        dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
        assert max(dx,dy)>0 and (dx==0 or dy==0 or dx==dy)
    v=(end[0]-start[0],end[1]-start[1])
    gap=abs(v[0]*(first[1]-start[1])-v[1]*(first[0]-start[0]))/math.hypot(*v)
    assert gap==pytest.approx(abs(offset)*1e6,abs=1.)


@pytest.mark.parametrize('end,offset',[( (0,0),.5),((4_000_000,2_000_000),.5),
    ((500_000,500_000),.5),((5_000_000,5_000_000),float('nan')),
    ((5_000_000,5_000_000),100)])
def test_noncanonical_or_unbounded_inputs_refused(end,offset):
    with pytest.raises(ValueError):repair.offset_points_nm((0,0),end,offset)


def test_native_diagonal_preserves_identity_layer_net_and_width():
    import pcbnew
    board=pcbnew.BOARD()
    net=pcbnew.NETINFO_ITEM(board,'SYNTHETIC_SENSOR_39',1);board.Add(net)
    track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I_MM(10,20))
    track.SetEnd(pcbnew.VECTOR2I_MM(15,25));track.SetLayer(pcbnew.B_Cu)
    track.SetWidth(200_000);track.SetNetCode(1);board.Add(track)
    uid=track.m_Uuid.AsString()
    report=repair.offset_straight_track(board,uid,.5)
    assert report['source_uuid']==uid and len(list(board.GetTracks()))==3
    assert all(t.GetLayer()==pcbnew.B_Cu and t.GetNetCode()==1 and t.GetWidth()==200_000
               for t in board.GetTracks())


@pytest.mark.parametrize('protection',['locked','grouped'])
def test_protected_native_copper_refused_before_mutation(protection):
    import pcbnew
    board=pcbnew.BOARD();track=pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(10,20));track.SetEnd(pcbnew.VECTOR2I_MM(15,25))
    board.Add(track)
    if protection=='locked':track.SetLocked(True)
    else:
        group=pcbnew.PCB_GROUP(board);group.AddItem(track);board.Add(group)
    before=(tuple(track.GetStart()),tuple(track.GetEnd()))
    with pytest.raises(ValueError,match='protected'):
        repair.offset_straight_track(board,track.m_Uuid.AsString(),.5)
    assert before==(tuple(track.GetStart()),tuple(track.GetEnd()))
    assert len(list(board.GetTracks()))==1


def test_board_trials_keep_shared_executable_sidecars():
    with mock.patch('cec_certificate_repair._copy_board_family') as copy:
        repair._copy_board_family('source.kicad_pcb','trial.kicad_pcb')
    copy.assert_called_once_with('source.kicad_pcb','trial.kicad_pcb')


def test_cross_layer_departures_try_both_geometric_roles_without_changing_electrical_roles():
    target=dict(layers=['F.Cu','B.Cu'],nets=['FAST_EDGE','SENSOR'],
                track_uuids=['edge-id','sensor-id'],victim='SENSOR',aggressor='FAST_EDGE')
    with mock.patch.object(repair,'_departure_trial',return_value={'safe':False}) as trial:
        rows=repair._departure_trials('board',target,{}, {},'work',0,.1)
    assert len(rows)==2
    assert [call.args[-2:] for call in trial.call_args_list]==[
        ('sensor-id','edge-id'),('edge-id','sensor-id')]
    assert target['victim']=='SENSOR' and target['aggressor']=='FAST_EDGE'


def test_same_layer_does_not_schedule_cross_layer_departure():
    with mock.patch.object(repair,'_departure_trial') as trial:
        assert repair._departure_trials('board',dict(layers=['F.Cu','F.Cu']),{}, {},'work',0,.1)==[]
    trial.assert_not_called()


@pytest.mark.parametrize('rounds,margin',[(0,.1),(17,.1),(1,-.1),(1,float('nan')),(1,3)])
def test_repair_bound_is_validated_before_touching_files(rounds,margin):
    with mock.patch.object(repair.os,'makedirs') as mkdir:
        with pytest.raises(ValueError):
            repair.repair_admitted('does-not-exist',max_rounds=rounds,margin_mm=margin)
    mkdir.assert_not_called()
