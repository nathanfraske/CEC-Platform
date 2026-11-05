"""A zero-stroke Ground root cannot poison a different real fork cut."""
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as binding
import cec_force_current as force
import cec_fr as fr
from test_cell_escape_replan import fixture
from test_field_proposals import track


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_zero_departure_keeps_ground_obligation_without_poisoning_owned_fork(tmp_path,monkeypatch,quarter,back):
    board,unused,owner,cap=fixture(monkeypatch,prefix='not_a_board_rule')
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    cap_ground=next(p for p in cap.Pads() if p.GetNetname()=='GND')
    owner_ground=next(p for p in owner.Pads() if p.GetNetname()=='GND')
    gp=[v/1e6 for v in cap_ground.GetPosition()]
    edges=[track(board,'GND',gp,(gp[0]+1.,gp[1]),width=.2),
        track(board,'GND',gp,(gp[0],gp[1]+1.),width=.2)]
    vias=[]
    for at,dia,drill in [(tuple(owner_ground.GetPosition()),350000,250000),
        (tuple(edges[0].GetEnd()),600000,300000),(tuple(edges[1].GetEnd()),600000,300000)]:
        v=pcbnew.PCB_VIA(board);v.SetNet(board.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I(*at))
        v.SetWidth(dia);v.SetDrill(drill);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v);vias.append(v)
    assert fr.group_local_pofv_signal_vias(board,vias[:1])
    if back:
        for fp in board.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for p in fp.Pads():
                ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu);p.SetLayerSet(ls)
        for t in edges:t.SetLayer(pcbnew.B_Cu)
    if quarter:
        at=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(at,angle)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    parent=pcbnew.LoadBoard(str(source));before=binding._source_binding(parent)
    poses={fp.GetReference():[fp.GetPosition().x/1e6+.5,fp.GetPosition().y/1e6+.5,
        fp.GetOrientationDegrees()] for fp in parent.GetFootprints()}
    plan=escape.prepare(parent,poses,board_hint='opaque')
    forks=plan.get('source_owned_shared_ground_return_forks',[])
    assert len(forks)==1,plan.get('source_shared_forks_not_owned')
    assert forks[0]['requested_root_pad_uuids']==[force._uid(cap_ground)]
    assert set(forks[0]['track_uuids'])=={force._uid(t) for t in edges}
    assert binding._source_binding(parent)==before
    private=pcbnew.LoadBoard(str(source));escape.apply_private(private,plan)
    requests=escape.obligations(parent,private,plan)
    assert 'ground:'+force._uid(owner_ground) in requests
    assert 'ground:'+force._uid(cap_ground) in requests
    assert not plan['routing_admitted'] and not plan['release_authority']
