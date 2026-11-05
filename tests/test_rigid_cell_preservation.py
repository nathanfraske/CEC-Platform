"""Cell motion is re-proved independently, not whitelisted by a move report."""
import pytest
import pcbnew
import cec_support_branch_preservation as preservation
import cec_local_copper_cell as cell
from test_local_copper_cell import native_cell


@pytest.mark.parametrize('angle,offset,back',[(0,0,False),(90,31,False),(180,-11,True)])
@pytest.mark.parametrize('fault',['none','nonrigid_peer','width','layer','net','lock','group',
                                 'nonrigid_track','lost_boundary','unrelated_rewrite'])
def test_independent_rigid_path_and_complete_external_component(tmp_path,angle,offset,back,fault):
    names=('ARBITRARY_A','ARBITRARY_B')
    board,fps,internal,external,make_pad,make_track=native_cell(offset=offset,names=names)
    stub=make_track((5,5),(0,4))
    other=pcbnew.NETINFO_ITEM(board,'/OTHER');board.Add(other)
    foreign=make_pad('UNMOVED',40,40);next(iter(foreign.Pads())).SetNet(other)
    via=pcbnew.PCB_VIA(board);via.SetNet(stub.GetNet());via.SetPosition(stub.GetEnd())
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    if back:
        for fp in fps:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for item in [*internal,stub]:item.SetLayer(pcbnew.B_Cu)
    if fault=='lock':internal[0].SetLocked(True)
    if fault=='group':
        group=pcbnew.PCB_GROUP(board);group.SetName('arbitrary-owned-group');board.Add(group);group.AddItem(internal[0])
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    original=source.read_bytes();first=pcbnew.LoadBoard(str(source));last=pcbnew.LoadBoard(str(source))
    ids={item.m_Uuid.AsString() for item in internal}
    anchor=last.FindFootprintByReference(names[0]).GetPosition()
    delta=pcbnew.VECTOR2I_MM(.5,1)
    for ref in names:
        fp=last.FindFootprintByReference(ref)
        fp.Rotate(anchor,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T));fp.Move(delta)
    last_tracks={t.m_Uuid.AsString():t for t in last.GetTracks()}
    for uid in ids:
        item=last_tracks[uid];item.Rotate(anchor,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T));item.Move(delta)
    last.Delete(last_tracks[stub.m_Uuid.AsString()])
    if fault!='lost_boundary':
        track=pcbnew.PCB_TRACK(last);track.SetNet(last.FindNet(stub.GetNetCode()))
        track.SetLayer(stub.GetLayer());track.SetWidth(stub.GetWidth())
        track.SetStart(last.FindFootprintByReference(names[0]).GetPosition());track.SetEnd(via.GetPosition());last.Add(track)
    item=last_tracks[internal[0].m_Uuid.AsString()]
    if fault=='nonrigid_peer':last.FindFootprintByReference(names[1]).Move(pcbnew.VECTOR2I_MM(.1,0))
    if fault=='width':item.SetWidth(item.GetWidth()+1)
    if fault=='layer':item.SetLayer(pcbnew.B_Cu if not back else pcbnew.F_Cu)
    if fault=='nonrigid_track':item.Move(pcbnew.VECTOR2I(1,0))
    if fault=='unrelated_rewrite':last_tracks[external.m_Uuid.AsString()].Move(delta)
    candidate=tmp_path/'candidate.kicad_pcb';pcbnew.SaveBoard(str(candidate),last)
    final=pcbnew.LoadBoard(str(candidate))
    if fault=='net':
        # KiCad save can propagate connected pad net assignments back onto
        # tracks. Challenge the native proof before that normalization.
        changed=next(t for t in final.GetTracks() if t.m_Uuid.AsString()==internal[0].m_Uuid.AsString())
        changed.SetNet(final.FindNet('/OTHER'))
        assert changed.GetNetname()=='/OTHER'
    proof=preservation.prove(first,final,names)
    assert proof['ok'] is (fault=='none'),proof
    assert not proof['release_authority'] and source.read_bytes()==original
    if fault=='none':
        assert proof['rigid_internal_copper']['proved'][0]['coordinate_tolerance_nm']==0
        assert {r['uuid'] for r in proof['proved']}==ids|{stub.m_Uuid.AsString()}


@pytest.mark.parametrize('delta_nm',[1,47,120000])
def test_internal_path_uses_real_offcenter_pad_contact(delta_nm):
    board,fps,internal,_,_,_=native_cell()
    internal[0].SetStart(internal[0].GetStart()+pcbnew.VECTOR2I(0,delta_nm))
    internal[-1].SetEnd(internal[-1].GetEnd()+pcbnew.VECTOR2I(0,-delta_nm))
    result=cell.plan(board,fps)
    assert set(result['internal_track_uuids'])=={t.m_Uuid.AsString() for t in internal}
