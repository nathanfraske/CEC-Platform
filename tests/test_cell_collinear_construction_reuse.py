"""Source/full-width copper is reused without adding segmented duplicate launches."""
import pcbnew
import pytest
import cec_additive_portal_compaction as coverage
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_route_quality as craft
from test_field_proposals import track


def fixture(quarter=0,back=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for net in ('OPAQUE_RAIL','OTHER'):board.Add(pcbnew.NETINFO_ITEM(board,net))
    def at(x,y):
        for _ in range(quarter):x,y=-y,x
        return (10000000+round(x*1e6),10000000+round(y*1e6))
    return board,at,pcbnew.B_Cu if back else pcbnew.F_Cu


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('long_first',[False,True])
def test_long_and_segmented_independent_demands_reuse_exact_union_in_either_order(quarter,back,long_first):
    board,at,face=fixture(quarter,back)
    full=[['trk',at(0,0),at(2,0),500000,face]]
    split=[['trk',at(0,0),at(.5,0),500000,face],['trk',at(.5,0),at(2,0),500000,face]]
    first,second=(full,split)if long_first else(split,full)
    made=escape._native_ops(board,first,'OPAQUE_RAIL');before=row._source_binding(board)
    assert escape._native_ops(board,second,'OPAQUE_RAIL')==[]
    assert row._source_binding(board)==before
    assert len(list(board.GetTracks()))==len(made)==(1 if long_first else 2)
    assert craft.analyze_board(board)['issue_count']==0


@pytest.mark.parametrize('fault',['gap','off_axis','width','net','layer','partial'])
def test_a_single_nanometre_or_role_difference_cannot_supply_coverage(fault):
    board,at,face=fixture()
    old=escape._native_ops(board,[['trk',at(0,0),at(1,0),500000,face],
        ['trk',at(1,0),at(2,0),500000,face]],'OPAQUE_RAIL')
    query=pcbnew.PCB_TRACK(board);query.SetStart(pcbnew.VECTOR2I(*at(0,0)))
    query.SetEnd(pcbnew.VECTOR2I(*at(2,0)));query.SetWidth(500000);query.SetLayer(face)
    query.SetNetCode(board.GetNetcodeFromNetname('OPAQUE_RAIL'))
    if fault=='gap':old[1].SetStart(old[1].GetStart()+pcbnew.VECTOR2I(1,0))
    elif fault=='off_axis':old[1].Move(pcbnew.VECTOR2I(0,1))
    elif fault=='width':old[1].SetWidth(499999)
    elif fault=='net':old[1].SetNetCode(board.GetNetcodeFromNetname('OTHER'))
    elif fault=='layer':old[1].SetLayer(pcbnew.B_Cu)
    else:old[1].SetEnd(pcbnew.VECTOR2I(*at(1.9,0)))
    before=row._source_binding(board)
    assert coverage.covered_by_collinear_union(query,old)is None
    assert row._source_binding(board)==before


def test_existing_wider_native_capsule_can_cover_new_narrower_demand_without_editing_source():
    board,at,face=fixture()
    source=escape._native_ops(board,[['trk',at(0,0),at(2,0),600000,face]],'OPAQUE_RAIL')
    source[0].SetLocked(True)
    group=pcbnew.PCB_GROUP(board);group.SetName('PROTECTED_SOURCE');board.Add(group);group.AddItem(source[0])
    before=row._source_binding(board)
    assert escape._native_ops(board,[['trk',at(.25,0),at(1.5,0),500000,face]],'OPAQUE_RAIL')==[]
    assert before==row._source_binding(board)
    assert source[0].IsLocked()and group.ContainsItem(source[0])and source[0].GetWidth()==600000


def test_partial_overlap_is_constructed_and_remains_subject_to_whole_board_craft():
    board,at,face=fixture()
    escape._native_ops(board,[['trk',at(0,0),at(1,0),500000,face]],'OPAQUE_RAIL')
    made=escape._native_ops(board,[['trk',at(.5,0),at(2,0),500000,face]],'OPAQUE_RAIL')
    assert len(made)==1 and len(list(board.GetTracks()))==2
