"""Grouped supply routes can move only with an exact, fresh electrical proof."""
import pcbnew
import pytest
import wx
quiet=wx.LogNull()

import cec_consumer_group_reconstruction as reconstruction
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_pass_through_supply_branch import fixture


def case(monkeypatch,tmp_path,angle=0,mirror=False):
    board,root,_,_,_,tracks,_,_,_,_,_=fixture(monkeypatch,tmp_path,angle,mirror)
    old=tracks[0];start,end=tuple(old.GetStart()),tuple(old.GetEnd())
    for at in (start,end):
        via=pcbnew.PCB_VIA(board);via.SetNet(root.GetNet());via.SetPosition(pcbnew.VECTOR2I(*at))
        via.SetWidth(800000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    source=tmp_path/'source.kicad_pcb'
    loaded=field._save_field_snapshot(board,source);field._save_field_snapshot(loaded,source)
    board=pcbnew.LoadBoard(str(source));uid=force._uid(old)
    source_item=next(t for t in board.GetTracks() if force._uid(t)==uid)
    other=pcbnew.B_Cu if source_item.GetLayer()==pcbnew.F_Cu else pcbnew.F_Cu
    return source,board,uid,other,start,end


def child(monkeypatch,tmp_path,angle=0,mirror=False):
    source,board,uid,other,start,end=case(monkeypatch,tmp_path,angle,mirror)
    scope=reconstruction.plan(board,source,board_hint='synthetic',retired_track_uuids=[uid])
    reconstruction.subtract(board,scope)
    track=pcbnew.PCB_TRACK(board);track.SetNetCode(board.GetNetcodeFromNetname(scope['net']))
    track.SetLayer(other);track.SetStart(pcbnew.VECTOR2I(*start));track.SetEnd(pcbnew.VECTOR2I(*end))
    track.SetWidth(scope['required_by_layer_nm'][board.GetLayerName(other)]);board.Add(track)
    incoming=force._uid(track);reconstruction.assign(board,scope,[incoming],[])
    path=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(board,path)
    return source,path,uid,incoming,scope


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_real_group_reconstruction_replays_same_root_tap_budget_and_retained_copper(monkeypatch,tmp_path,angle,mirror):
    source,candidate,uid,incoming,scope=child(monkeypatch,tmp_path,angle,mirror)
    saved=source.read_bytes()
    result=reconstruction.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid])
    assert result['ok'] and result['complete'],result
    assert result['incoming_track_uuids']==[incoming] and not result['incoming_via_uuids']
    assert result['source_scope']['source_budget']['current_authority']['amps']==3.0004
    assert result['source_scope']['source_budget']['aggregate_current_authority']['amps']==20.
    assert result['source_scope']['anchor_uuid']==scope['anchor_uuid']
    assert result['all_original_surviving_partitions_preserved']
    assert result['exact_native_ground_refill_replayed']
    assert not any(result[k] for k in ('source_current_reduced','branch_sharing_assumed',
        'terminal_or_barrel_ampacity_qualified','release_authority'))
    assert source.read_bytes()==saved


def test_generic_native_delete_keeps_rejecting_allocation_members(monkeypatch,tmp_path):
    source,board,uid,*_=case(monkeypatch,tmp_path)
    saved=source.read_bytes()
    with pytest.raises(ValueError,match='breaks_typed_supply_annotation'):
        discard_items(board,[t for t in board.GetTracks() if force._uid(t)==uid])
    assert source.read_bytes()==saved


@pytest.mark.parametrize('fault',['thin','wrong_net','missing_member','tap','group_uuid','pose','foreign_item'])
def test_proposed_group_cannot_approve_its_own_current_or_source_delta(monkeypatch,tmp_path,fault):
    source,candidate,uid,incoming,scope=child(monkeypatch,tmp_path)
    board=pcbnew.LoadBoard(str(candidate));track=next(t for t in board.GetTracks() if force._uid(t)==incoming)
    group=next(g for g in board.Groups() if force._uid(g)==scope['group_uuid'])
    if fault=='thin':track.SetWidth(200000)
    elif fault=='wrong_net':
        track.SetNetCode(board.GetNetcodeFromNetname('OTHER'))
        track.SetStart(pcbnew.VECTOR2I_MM(2,2));track.SetEnd(pcbnew.VECTOR2I_MM(3,2))
    elif fault=='missing_member':group.RemoveItem(track)
    elif fault=='tap':group.SetName(group.GetName().replace(scope['anchor_uuid'],scope['root_pad_uuid']))
    elif fault=='group_uuid':group.m_Uuid.Clone(pcbnew.KIID())
    elif fault=='pose':
        owner=next(fp for fp in board.GetFootprints() if fp.GetReference()=='NO_PREFIX_OWNER')
        owner.Move(pcbnew.VECTOR2I(100000,0))
    else:
        extra=pcbnew.PCB_TRACK(board);extra.SetNetCode(board.GetNetcodeFromNetname('OTHER'))
        extra.SetLayer(pcbnew.B_Cu);extra.SetWidth(200000);extra.SetStart(pcbnew.VECTOR2I_MM(2,2))
        extra.SetEnd(pcbnew.VECTOR2I_MM(3,2));board.Add(extra)
    field._save_field_snapshot(board,candidate)
    result=reconstruction.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid])
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('fault',['opaque_owner','all_members','unknown_identity','underwidth'])
def test_only_partial_tracks_of_one_already_positive_group_are_offered(monkeypatch,tmp_path,fault):
    source,board,uid,*_=case(monkeypatch,tmp_path)
    group=next(g for g in board.Groups() if g.ContainsItem(next(t for t in board.GetTracks() if force._uid(t)==uid)))
    cuts=[uid]
    if fault=='opaque_owner':group.SetName('unrelated electrical owner')
    elif fault=='all_members':cuts=[force._uid(t) for t in group.GetItems()]
    elif fault=='unknown_identity':cuts=['not-an-existing-track']
    else:next(t for t in board.GetTracks() if force._uid(t)==uid).SetWidth(100000)
    field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):
        reconstruction.plan(board,source,board_hint='synthetic',retired_track_uuids=cuts)
