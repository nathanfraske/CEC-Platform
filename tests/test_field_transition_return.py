"""Renamed and translated native transition/return regression fixtures."""
import sys
from pathlib import Path
import pytest
import pcbnew
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tests'))
import cec_field_transition_return as returns
import cec_field_coupling as field
import cec_zone_fill
from test_field_coupling import FieldCouplingTest


def fixture(tmp_path, shift=0., suffix='ALT'):
    path=FieldCouplingTest()._board(str(tmp_path),[
        ('/SENSOR_SENSE_'+suffix,'B.Cu',(10.+shift,8.4),(10.5+shift,7.9)),
        ('/CLK_'+suffix,'F.Cu',(10.7+shift,4.),(10.7+shift,8.))])
    board=pcbnew.LoadBoard(path)
    track=next(t for t in board.GetTracks() if 'SENSOR' in t.GetNetname())
    via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetPosition(track.GetStart());via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetWidth(600_000);via.SetDrill(300_000);via.SetNetCode(track.GetNetCode())
    via.SetLocked(True);board.Add(via)
    for z in board.Zones():z.UnFill()
    cec_zone_fill.fill(board)
    target=next(r for r in field.field_coupling_summary(path,board=board)['interactions'] if r['blocking'])
    return board,target


@pytest.mark.parametrize('shift,suffix',[(0.,'ALPHA'),(4.,'BETA'),(8.,'GAMMA')])
def test_added_return_is_generic_and_leaves_original_copper_untouched(tmp_path,shift,suffix):
    board,target=fixture(tmp_path,shift,suffix)
    before={t.m_Uuid.AsString():(t.GetNetname(),tuple(t.GetStart()),tuple(t.GetEnd()),
                               t.IsLocked(),t.GetLayer()) for t in board.GetTracks()}
    result=returns.add_returns(board,target)
    assert result['added']==1
    for t in board.GetTracks():
        if t.m_Uuid.AsString() in before:
            assert before[t.m_Uuid.AsString()]==(t.GetNetname(),tuple(t.GetStart()),
                tuple(t.GetEnd()),t.IsLocked(),t.GetLayer())
        else:assert t.GetNetname()=='GND'
    for z in board.Zones():z.UnFill()
    cec_zone_fill.fill(board)
    assert returns.verify_contacts(board,result)['ok']
    assert field.field_coupling_summary(board.GetFileName(),board=board)['blocking_count']==0


def test_no_fill_is_not_synthesized_or_treated_as_contact(tmp_path):
    board,target=fixture(tmp_path)
    before=len(list(board.GetTracks()))
    for z in board.Zones():z.UnFill()
    with pytest.raises(ValueError,match='actual filled'):
        returns.add_returns(board,target)
    assert len(list(board.GetTracks()))==before


def test_stale_identity_is_refused_before_mutation(tmp_path):
    board,target=fixture(tmp_path)
    before=len(list(board.GetTracks()))
    target=dict(target,track_uuids=['not-a-current-track',target['track_uuids'][1]])
    with pytest.raises(ValueError,match='stale'):
        returns.add_returns(board,target)
    assert len(list(board.GetTracks()))==before


def test_same_layer_field_is_not_repaired_by_return_via(tmp_path):
    board,target=fixture(tmp_path)
    target=dict(target,layers=['F.Cu','F.Cu'])
    assert returns.add_returns(board,target)['added']==0


def test_postfill_witness_cannot_pass_without_native_copper(tmp_path):
    board,target=fixture(tmp_path)
    result=returns.add_returns(board,target)
    for z in board.Zones():z.UnFill()
    with pytest.raises(ValueError,match='actual filled'):
        returns.verify_contacts(board,result)


@pytest.mark.parametrize('options',[{'return_reach_mm':2.},{'return_reach_mm':float('nan')},
    {'via_drill_mm':.9},{'via_diameter_mm':True},{'clearance_mm':0}])
def test_invalid_geometry_refuses_without_accessing_board(options):
    with pytest.raises(ValueError,match='bounded'):
        returns.add_returns(None,{},**options)
