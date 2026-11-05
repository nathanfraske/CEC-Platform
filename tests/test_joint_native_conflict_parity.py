"""Joint proposals use manufactured native geometry, not polygon inflation."""
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row


@pytest.mark.parametrize('kind',['tracks','track_via','vias'])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('slack_nm',[-1,1,1001,3000])
def test_foreign_proposal_capsules_have_exact_native_clearance(kind,quarter,slack_nm):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    def xy(x,y):
        for _ in range(quarter):x,y=-y,x
        return [10000000+x,10000000+y]
    first=['trk',xy(-1000000,0),xy(1000000,0),200000,pcbnew.F_Cu]
    last=['trk',xy(-1000000,400000+slack_nm),xy(1000000,400000+slack_nm),200000,pcbnew.F_Cu]
    if kind=='track_via':last=['via',xy(0,600000+slack_nm),.3,.6]
    if kind=='vias':
        first=['via',xy(0,0),.3,.6];last=['via',xy(0,800000+slack_nm),.3,.6]
    a=dict(net='a',ops=[first],clearance_nm=200000)
    b=dict(net='b',ops=[last],clearance_nm=200000)
    before=row._source_binding(board)
    assert escape.conflict_oracle(board)(a,b)==(slack_nm<0)
    assert row._source_binding(board)==before


@pytest.mark.parametrize('same_net',[False,True])
@pytest.mark.parametrize('slack_nm',[-1,1])
def test_same_net_does_not_waive_native_new_drill_spacing(same_net,slack_nm):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    board.GetDesignSettings().m_HoleToHoleMin=250000
    a=dict(net='a',ops=[['via',[10000000,10000000],.3,.6]],clearance_nm=0)
    b=dict(net='a' if same_net else 'b',ops=[['via',[10550000+slack_nm,10000000],.3,.6]],clearance_nm=0)
    # For the foreign-net case copper itself also collides; this cannot
    # become legal just because the drill-to-drill distance clears.
    assert escape.conflict_oracle(board)(a,b)==(not same_net or slack_nm<0)


def test_separate_faces_do_not_create_a_false_planar_conflict():
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    a=dict(net='a',ops=[['trk',[10000000,10000000],[12000000,10000000],200000,pcbnew.F_Cu]],clearance_nm=200000)
    b=dict(net='b',ops=[['trk',[11000000,9000000],[11000000,11000000],200000,pcbnew.B_Cu]],clearance_nm=200000)
    assert not escape.conflict_oracle(board)(a,b)
