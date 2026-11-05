"""Private unfinished IR is not an admissible saved routing board."""
import time
import pcbnew
import pytest
import cec_field_coupling as field
import cec_native_construction_frame as frame
from test_return_plane_preview import board_fixture,via
import cec_ground_plane as ground


def unfinished(tmp_path,quarter=0,back=False):
    board=board_fixture();props=board.GetProperties()
    props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    via(board,'GND',(3,3));barrel=via(board,'FOREIGN',(14,10))
    # Rotation and surface placement cannot become an identity waiver.
    if quarter:
        barrel.Rotate(pcbnew.VECTOR2I(10000000,10000000),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('ARBITRARY_IR_OWNER');board.Add(fp)
    p=pcbnew.PAD(fp);p.SetNumber('X');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);p.SetSize(pcbnew.VECTOR2I(700000,500000))
    p.SetRoundRectRadiusRatio(.2);p.SetNet(board.FindNet('FOREIGN'));fp.Add(p)
    p.SetPosition(pcbnew.VECTOR2I(14000000,10000000));p.SetLayerSet(pcbnew.PAD.SMDMask())
    fp.SetPosition(pcbnew.VECTOR2I(14000000,10000000));fp.SetOrientationDegrees(quarter*90)
    if back:fp.Flip(fp.GetPosition(),False)
    fp.SetValue('exact unrelated component value')
    group=pcbnew.PCB_GROUP(board);group.SetName('EXACT_NONFUNCTIONAL_GROUP');board.Add(group)
    group.AddItem(fp);group.SetLocked(True)
    assert ground.fill_board(board)['ok']
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    uid=barrel.m_Uuid.AsString();board=pcbnew.LoadBoard(str(source))
    board.SetFileName(str(source));barrel=next(t for t in board.GetTracks()if t.m_Uuid.AsString()==uid)
    barrel.SetPosition(pcbnew.VECTOR2I(10000000,10000000))
    return board,barrel,source


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_full_native_private_clone_preserves_unfinished_authorship_not_saved_validity(tmp_path,quarter,back):
    board,barrel,source=unfinished(tmp_path,quarter,back);raw=source.read_bytes()
    before=frame.binding(board,time.monotonic()+9.)
    with pytest.raises(ValueError,match='changed_saved_identity'):
        field._save_field_snapshot(board,tmp_path/'NOT-A-CANDIDATE.kicad_pcb')
    clone=frame.clone(board,time.monotonic()+9.)
    assert frame.binding(clone,time.monotonic()+9.)==before
    assert frame.binding(board,time.monotonic()+9.)==before
    assert clone.GetFileName()==board.GetFileName() and source.read_bytes()==raw
    assert barrel.GetNetname()=='FOREIGN'
    assert next(t for t in clone.GetTracks()if t.m_Uuid.AsString()==barrel.m_Uuid.AsString()).GetNetname()=='FOREIGN'
    # The private IR copy has not made stale copper legal or saved-equivalent.
    with pytest.raises(ValueError,match='changed_saved_identity'):
        field._save_field_snapshot(clone,tmp_path/'STILL-NOT-A-CANDIDATE.kicad_pcb')


@pytest.mark.parametrize('fault',['pad_shape','pad_offset','metadata','inner_width','drill','lock','group',
    'new_net','missing_net','zone_clearance','zone_island'])
def test_private_clone_rejects_every_other_native_reload_mutation(tmp_path,monkeypatch,fault):
    board,barrel,_=unfinished(tmp_path);load=pcbnew.LoadBoard
    def corrupt(path):
        child=load(path);fp=child.FindFootprintByReference('ARBITRARY_IR_OWNER');p=next(iter(fp.Pads()))
        v=next(t for t in child.GetTracks()if t.m_Uuid.AsString()==barrel.m_Uuid.AsString())
        if fault=='pad_shape':p.SetShape(pcbnew.PAD_SHAPE_RECT)
        elif fault=='pad_offset':p.SetOffset(pcbnew.VECTOR2I(1,0))
        elif fault=='metadata':fp.SetValue('mutated component value')
        elif fault=='inner_width':
            v.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM);v.SetWidth(pcbnew.In2_Cu,600001)
        elif fault=='drill':v.SetDrill(v.GetDrillValue()+1)
        elif fault=='lock':v.SetLocked(not v.IsLocked())
        elif fault=='group':next(iter(child.Groups())).SetName('mutated')
        elif fault=='new_net':child.Add(pcbnew.NETINFO_ITEM(child,'invented net'))
        elif fault=='missing_net':
            target=child.FindNet('FOREIGN');target.SetNetname('renamed missing net')
        elif fault=='zone_clearance':
            z=next(iter(child.Zones()));z.SetLocalClearance(z.GetLocalClearance()+1)
        else:
            z=next(z for z in child.Zones()if z.IsFilled());z.SetIsIsland(z.GetLayer(),0)
        return child
    monkeypatch.setattr(pcbnew,'LoadBoard',corrupt)
    with pytest.raises(ValueError,match='construction_frame'):
        frame.clone(board,time.monotonic()+9.)


def test_native_writer_failure_cannot_hide_mutated_live_caller(tmp_path,monkeypatch):
    board,barrel,_=unfinished(tmp_path)
    def broken(*args):
        barrel.SetLocked(not barrel.IsLocked());raise RuntimeError('synthetic writer failure')
    monkeypatch.setattr(pcbnew.PCB_IO_KICAD_SEXPR,'SaveBoard',broken)
    with pytest.raises(ValueError,match='construction_frame_changed_caller'):
        frame.clone(board,time.monotonic()+9.)


def test_private_clone_carries_actual_effective_rule_context(tmp_path):
    board,_,_=unfinished(tmp_path);settings=board.GetDesignSettings();settings.m_MinClearance=345678
    native=board.FindNet('FOREIGN').GetNetClassSlow();native.SetClearance(456789);native.SetTrackWidth(765432)
    child=frame.clone(board,time.monotonic()+9.)
    assert child.GetDesignSettings().m_MinClearance==345678
    assert child.FindNet('FOREIGN').GetNetClassSlow().GetClearance()==456789
    assert child.FindNet('FOREIGN').GetNetClassSlow().GetTrackWidth()==765432


def test_expired_transient_copy_never_gains_a_fresh_lease(tmp_path):
    board,_,_=unfinished(tmp_path)
    with pytest.raises(ValueError,match='deadline'):frame.clone(board,time.monotonic())
