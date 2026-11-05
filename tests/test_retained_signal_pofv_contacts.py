"""Source-qualified signal continuity is not a new/rated barrel waiver."""
import time
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as receiving
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, angle=0, net='/RENAMED_SIGNAL', qualified=True):
    board=_board([(5,10,net),(15,10,net)],edge=(0,0,20,20))
    if qualified:
        props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current'
        board.SetProperties(props)
    for fp in board.GetFootprints():
        list(fp.Pads())[0].SetPadName('1')
    cut=track(board,net,(5,10),(15,10),width=.2)
    ids=[]
    for x in (5,15):
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(x,10))
        via.SetWidth(350000);via.SetDrill(250000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(board.FindNet(net));board.Add(via)
        ids.append(force._uid(via))
    if angle:
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(board,source)
    child=pcbnew.LoadBoard(str(source))
    old=next(t for t in board.GetTracks() if force._uid(t)==force._uid(cut))
    discard_items(child,[t for t in child.GetTracks() if force._uid(t)==force._uid(cut)])
    edge=pcbnew.PCB_TRACK(child);edge.SetStart(old.GetStart());edge.SetEnd(old.GetEnd())
    edge.SetLayer(pcbnew.B_Cu);edge.SetWidth(200000);edge.SetNetCode(old.GetNetCode());child.Add(edge)
    return source,board,child,old,ids


@pytest.mark.parametrize('angle,net',[(0,'/a'),(90,'/other'),(180,'/renamed/x'),(270,'/fourth')])
def test_exact_source_qualified_signal_barrels_restore_native_boundaries(tmp_path,angle,net):
    source,parent,child,old,ids=fixture(tmp_path,angle,net)
    before=source.read_bytes()
    with pytest.raises(ValueError,match='retired_endpoint_pair_not_restored'):
        receiving._boundaries(parent,child,[old],time.monotonic()+5)
    proof=receiving._boundaries(parent,child,[old],time.monotonic()+5,
        ordinary_source=source,board_hint='synthetic')
    assert proof[0]['restored'] and set(proof[0]['retained_qualified_signal_via_contacts'])==set(ids)
    destination=tmp_path/'candidate'/'board.kicad_pcb';destination.parent.mkdir()
    field._save_field_snapshot(child,destination)
    receipt=receiving.receive(source,destination,retired_track_uuids=[force._uid(old)],board_hint='synthetic')
    assert receipt['ok'] and receipt['power_authority'] is False,receipt
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['new','moved','width','drill','locked','unqualified','power','removed_owner'])
def test_new_changed_unqualified_or_specialized_contacts_never_get_source_credit(tmp_path,fault):
    source,parent,child,old,ids=fixture(tmp_path,net='+5V' if fault=='power' else '/control',
        qualified=fault!='unqualified')
    via=next(t for t in child.GetTracks() if force._uid(t)==ids[0])
    if fault=='new':via.m_Uuid.Clone(pcbnew.KIID())
    elif fault=='moved':via.Move(pcbnew.VECTOR2I_MM(.001,0))
    elif fault=='width':via.SetWidth(360000)
    elif fault=='drill':via.SetDrill(240000)
    elif fault=='locked':via.SetLocked(True)
    elif fault=='removed_owner':
        next(fp for fp in child.GetFootprints() if fp.GetPosition()==via.GetPosition()).Move(pcbnew.VECTOR2I_MM(1,0))
    contacts=receiving._retained_ordinary_pofv_contacts(parent,child,
        source=source,board_hint='synthetic',deadline=time.monotonic()+5)
    assert ids[0] not in contacts
    if fault in ('power','unqualified'):assert not contacts
    with pytest.raises(ValueError):
        receiving._boundaries(parent,child,[old],time.monotonic()+5,
            ordinary_source=source,board_hint='synthetic')
