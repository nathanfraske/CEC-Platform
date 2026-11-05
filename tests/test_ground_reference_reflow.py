"""Reference returns may free a corridor only with shorter native returns."""
from unittest import mock
import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_ground_reference_reflow as reflow
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_field_proposals import track
from test_local_branch_access import fixture as base_fixture


def fixture(tmp_path, rotation=0):
    source, _, _ = base_fixture(tmp_path)
    board = pcbnew.LoadBoard(str(source)); cap = board.FindFootprintByReference('C_RENAMED')
    cap.Move(pcbnew.VECTOR2I_MM(0,1.5))
    discard_items(board, [t for t in board.GetTracks() if t.GetNetname() in ('GND','MEASURE_MINUS')])
    for a,b in zip([(15,11.5),(18,11.5),(18,16),(15,16)],[(18,11.5),(18,16),(15,16),(15,15)]):
        track(board,'GND',a,b)
    old = track(board,'GND',(15,13),(15,15)); uid = force._uid(old)
    if rotation:
        pivot = pcbnew.VECTOR2I_MM(15,15); angle = pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]: item.Rotate(pivot,angle)
    for fp in board.GetFootprints():
        if fp.GetReference()=='U_RENAMED': fp.SetReference('RENAMED_SENSOR')
        if fp.GetReference()=='C_RENAMED': fp.SetReference('C_RENAMED_BYPASS')
    field._save_field_snapshot(board,source)
    pad_uid = force._uid(board.FindFootprintByReference('RENAMED_SENSOR').FindPadByNumber('5'))
    candidate = force._copy_family(source,tmp_path/'reflow'); child = pcbnew.LoadBoard(str(candidate))
    discard_items(child,[t for t in child.GetTracks() if force._uid(t)==uid])
    start = child.FindFootprintByReference('RENAMED_SENSOR').FindPadByNumber('5').GetPosition()
    end = child.FindFootprintByReference('C_RENAMED_BYPASS').FindPadByNumber('2').GetPosition()
    edge = track(child,'GND',tuple(v/1e6 for v in start),tuple(v/1e6 for v in end))
    field._save_field_snapshot(child,candidate)
    return source,candidate,pad_uid,uid,force._uid(edge)


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_rotated_renamed_reference_can_return_to_its_already_grounded_bypass(tmp_path,rotation):
    source,child,pad,uid,_ = fixture(tmp_path,rotation); immutable = source.read_bytes()
    proof = reflow.receive(source,child,pad_uuid=pad,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['retired_track_uuids']==[uid] and proof['return_length_nonworsening']
    assert proof['received_return']['saved_native_path_mm']==pytest.approx(1.5)
    assert proof['all_surviving_native_partitions_preserved']
    assert not proof['current_authority'] and not proof['release_authority']
    assert source.read_bytes()==immutable


def test_locked_reference_requires_the_exact_source_leaf_allowlist(tmp_path):
    source,child,pad,uid,_ = fixture(tmp_path); board=pcbnew.LoadBoard(str(source))
    next(t for t in board.GetTracks() if force._uid(t)==uid).SetLocked(True);field._save_field_snapshot(board,source)
    assert not reflow.receive(source,child,pad_uuid=pad,board_hint='synthetic')['ok']
    proof=reflow.receive(source,child,pad_uuid=pad,board_hint='synthetic',allow_locked_track_uuids=[uid])
    assert proof['ok'],proof
    assert not reflow.receive(source,child,pad_uuid=pad,board_hint='synthetic',allow_locked_track_uuids=[uid,'unowned'])['ok']


@pytest.mark.parametrize('fault',['longer','narrow','barrel','spur','wrong_destination','pose','extra_cut',
    'source_group','power_ground','unknown_model','lost_source_ground','internal_tee','budget'])
def test_reflow_does_not_grant_general_ground_or_power_ripup(tmp_path,fault):
    source,child,pad,uid,new_uid=fixture(tmp_path); parent=pcbnew.LoadBoard(str(source));b=pcbnew.LoadBoard(str(child))
    edge=next(t for t in b.GetTracks() if force._uid(t)==new_uid)
    if fault=='longer':
        discard_items(b,[edge])
        for a,z in [((15,13),(13.5,13)),((13.5,13),(13.5,11.5)),((13.5,11.5),(15,11.5))]: track(b,'GND',a,z)
    elif fault=='narrow': edge.SetWidth(100000)
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(15,11.5));v.SetWidth(600000);v.SetDrill(300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetNetCode(edge.GetNetCode());b.Add(v)
    elif fault=='spur': track(b,'GND',(15,11.5),(16,11.5))
    elif fault=='wrong_destination': edge.SetEnd(pcbnew.VECTOR2I_MM(15,12))
    elif fault=='pose': b.FindFootprintByReference('RENAMED_SENSOR').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='extra_cut': discard_items(b,[next(t for t in b.GetTracks() if t.GetNetname()=='MEASURE_PLUS')])
    elif fault=='source_group':
        g=pcbnew.PCB_GROUP(parent);g.SetName('PROTECTED');parent.Add(g)
        g.AddItem(next(t for t in parent.GetTracks() if force._uid(t)==uid))
    elif fault=='power_ground': pad=force._uid(parent.FindFootprintByReference('RENAMED_SENSOR').FindPadByNumber('2'))
    elif fault=='unknown_model': parent.FindFootprintByReference('RENAMED_SENSOR').SetValue('UNKNOWN')
    elif fault=='lost_source_ground': discard_items(parent,[next(t for t in parent.GetTracks() if t.GetStart()==pcbnew.VECTOR2I_MM(15,11.5))])
    elif fault=='internal_tee': track(parent,'GND',(15,14),(14,14))
    field._save_field_snapshot(parent,source);field._save_field_snapshot(b,child)
    proof=reflow.receive(source,child,pad_uuid=pad,board_hint='synthetic',timeout_s=0 if fault=='budget' else 10.)
    assert not proof['ok'] and proof['errors'],proof


def test_typed_cut_chain_receives_reference_reflow_without_a_worker_waiver(tmp_path):
    source,child,pad,uid,_=fixture(tmp_path)
    phases=[dict(kind='ground_reference_reflow',candidate=str(child),pad_uuid=pad,allow_locked_track_uuids=[])]
    proof=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert proof['ok'] and proof['complete'],proof
    assert proof['retired_track_uuids']==[uid] and not proof['current_authority']


def test_automatic_constructor_shortens_the_source_selected_reference_return(tmp_path):
    source,_,pad,uid,_=fixture(tmp_path); before=source.read_bytes()
    result=reflow.run(source,tmp_path/'automatic',board_hint='synthetic',pad_uuid=pad,
        source_sha256=force._hash(source))
    assert result['ok'] and result['independent_receiving']['return_length_nonworsening'],result
    assert result['independent_receiving']['received_return']['saved_native_path_mm']<=2.
    assert not result['measured_open_progress'] and not result['routing_admitted']
    assert source.read_bytes()==before
