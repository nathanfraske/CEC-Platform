import pcbnew,pytest
import wx
quiet=wx.LogNull()
import cec_smd_macro_transport as macro
import cec_force_current as force
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_fr as fr
from test_local_pofv_ownership import fixture
from test_smd_macro_transport import inventory


def source(tmp_path,rotation=0,ambiguous=False):
    b,v=fixture(offset=(0,0),connected=False);cap=next(iter(b.GetFootprints()));cap.SetReference('LOCAL_LAND')
    pad=next(iter(cap.Pads()));at=pcbnew.VECTOR2I(v.GetPosition())
    cap.SetPosition(at);pad.SetPosition(at)
    other=pcbnew.FOOTPRINT(b);other.SetReference('NEIGHBOR')
    other.SetPosition(at if ambiguous else at+pcbnew.VECTOR2I_MM(-1.1,0))
    p=pcbnew.PAD(other);p.SetNumber('1');p.SetPosition(other.GetPosition())
    p.SetSize(pcbnew.VECTOR2I_MM(.6,.4));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetLayerSet(pad.GetLayerSet());p.SetNetCode(pad.GetNetCode());other.Add(p);b.Add(other)
    t=pcbnew.PCB_TRACK(b);t.SetStart(p.GetPosition());t.SetEnd(at);t.SetLayer(pcbnew.F_Cu)
    t.SetWidth(200000);t.SetNetCode(pad.GetNetCode());b.Add(t)
    fr.group_local_pofv_signal_vias(b,[v])
    for i in [*b.GetFootprints(),*b.GetTracks()]:
        i.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(rotation*90,pcbnew.DEGREES_T))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    return [pcbnew.LoadBoard(str(path)) for _ in range(2)],force._uid(cap),force._uid(other),force._uid(v),force._uid(t)


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('turn',[0,90,180])
def test_inpad_axis_follows_its_containing_land_not_a_neighbor_dogbone(tmp_path,rotation,turn):
    (a,b),cap,other,via,edge=source(tmp_path,rotation)
    before=inventory(a);fp=next(f for f in b.GetFootprints() if force._uid(f)==cap)
    fp.SetOrientationDegrees(fp.GetOrientationDegrees()+turn);fp.Move(pcbnew.VECTOR2I_MM(2,1))
    neighbor=next(f for f in b.GetFootprints() if force._uid(f)==other);neighbor.Move(pcbnew.VECTOR2I_MM(-1,0))
    result=macro.apply(a,b,allow_cardinal_rotations=True)
    proof=next(r for r in result['source_process_barrel_motion'] if r['uuid']==via)
    assert proof['owner_footprint_uuids']==[cap]
    assert proof['actual_source_ownership_basis']=='complete_native_in_pad_containment'
    assert proof['independently_reconstructed_inter_owner_dogbone_uuids']==[edge]
    v=next(t for t in b.GetTracks() if force._uid(t)==via)
    assert tuple(v.GetPosition())==tuple(next(iter(fp.Pads())).GetPosition())
    assert fab.local_pofv_via_decision(b,v)[0]
    assert edge in result['transient_rebuild_required_uuids']
    assert before==inventory(a) and not result['saved_candidate_authorized']


def test_multiple_disagreeing_containing_lands_are_still_ambiguous(tmp_path):
    (a,b),cap,other,via,edge=source(tmp_path,ambiguous=True)
    next(f for f in b.GetFootprints() if force._uid(f)==cap).Move(pcbnew.VECTOR2I_MM(1,0))
    next(f for f in b.GetFootprints() if force._uid(f)==other).Move(pcbnew.VECTOR2I_MM(-1,0))
    before=inventory(b)
    with pytest.raises(ValueError,match='ambiguous_barrel_owner'):macro.apply(a,b)
    assert before==inventory(b)
