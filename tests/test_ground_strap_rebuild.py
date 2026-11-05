"""Logical ground straps are retyped, bounded, and never bypass-return waivers."""
import math
from unittest import mock

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_strap_rebuild as strap
import cec_source_cut_chain as chain
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, rotation=0, ref='U71', *, mesh=False, kernel=False):
    board=_board([(5,10,'GND')],edge=(0,0,30,30));board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    owner=next(iter(board.GetFootprints()));owner.SetReference(ref);owner.SetValue('INA238AIDGST')
    pad=next(iter(owner.Pads()));pad.SetNumber('1')
    edge=track(board,'GND',(5,10),(8,10))
    if kernel:
        from cec_native_items import discard_items
        discard_items(board,[edge])
        for a,z in (((5,10),(6,9)),((6,9),(7.75,9)),((7.75,9),(8,9.25))):
            track(board,'GND',a,z)
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(8,9.25 if kernel else 13 if mesh else 10));via.SetNet(pad.GetNet())
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);board.Add(via)
    if mesh:track(board,'GND',(8,7),(8,13))
    zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.In1_Cu);zone.SetNet(pad.GetNet())
    zone.Outline().NewOutline()
    for p in ((1,1),(29,1),(29,29),(1,29)):zone.Outline().Append(pcbnew.VECTOR2I_MM(*p))
    board.Add(zone)
    if rotation:
        pivot=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,angle)
    additive._ground_refill(board)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    proposal=strap.plan(pcbnew.LoadBoard(str(source)),force._uid(pad))
    child=force._copy_family(source,tmp_path/'trial');b=pcbnew.LoadBoard(str(child));strap.subtract(b,proposal)
    def rotate(x,y):
        a=math.radians(-rotation);return 15+(x-15)*math.cos(a)-(y-15)*math.sin(a),15+(x-15)*math.sin(a)+(y-15)*math.cos(a)
    edges=(((5,10),(5.25,9.75)),((5.25,9.75),(7.8,9.75)),((7.8,9.75),(8,9.55))) if kernel else (((5,10),(5.5,10.5)),((5.5,10.5),(7.5,10.5)),((7.5,10.5),(8,10))) if mesh else (((5,10),(7.7,10)),((7.7,10),(8,10.3)))
    for a,z in edges:track(b,'GND',rotate(*a),rotate(*z))
    if not mesh:
        new=pcbnew.PCB_VIA(b);new.SetPosition(pcbnew.VECTOR2I_MM(*rotate(8,9.55 if kernel else 10.3)));new.SetNetCode(pad.GetNetCode())
        new.SetWidth(600000);new.SetDrill(300000);new.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        new.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(new)
    field._save_field_snapshot(b,child)
    final=additive.finalize_private(source,child,tmp_path/'final')['board']
    return source,final,force._uid(pad),proposal


@pytest.mark.parametrize('rotation,ref',[(0,'U1'),(90,'U_OTHER'),(180,'U99'),(270,'U_RANDOM')])
def test_rotated_renamed_logical_strap_is_received_without_current_credit(tmp_path,rotation,ref):
    source,child,pad,proposal=fixture(tmp_path,rotation,ref);before=source.read_bytes()
    result=strap.receive(source,child,pad_uuid=pad,board_hint='synthetic')
    assert result['ok'] and result['complete'],result
    assert result['entry_mode']=='bounded_ordinary_root_reseat'
    assert result['all_surviving_partitions_and_immediate_returns_preserved']
    assert not result['independently_measured_local_PI_progress']
    assert not result['current_authority'] and not result['release_authority']
    assert source.read_bytes()==before
    assert not additive.receive(source,child)['ok']


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_shared_ground_trunk_and_its_existing_barrel_are_not_ripped_up(tmp_path,rotation):
    source,child,pad,proposal=fixture(tmp_path,rotation,'U_MESH',mesh=True)
    result=strap.receive(source,child,pad_uuid=pad,board_hint='synthetic')
    assert result['ok'] and result['complete'],result
    assert result['entry_mode']=='retained_mesh_logical_leaf'
    assert not result['retired_via_uuids'] and not result['independently_measured_local_PI_progress']
    assert result['all_surviving_partitions_and_immediate_returns_preserved']


@pytest.mark.parametrize('spec',[dict(track_width=.3),dict(via_diameter=.8),dict(via_drill=.4)])
def test_inherited_undersize_cannot_be_reissued_as_new_ground_material(tmp_path,spec):
    source,child,pad,_=fixture(tmp_path)
    with mock.patch.object(strap.fr,'_project_netclass_resolver',return_value=lambda n:spec):
        result=strap.receive(source,child,pad_uuid=pad,board_hint='synthetic')
    assert not result['ok'] and result['errors'],result


def test_grounded_analog_reference_cannot_use_an_address_straps_length_allowance(tmp_path):
    source,child,pad,_=fixture(tmp_path)
    for path in (source,child):
        b=pcbnew.LoadBoard(str(path));fp=next(iter(b.GetFootprints()))
        fp.SetValue('INA240A3DR');next(iter(fp.Pads())).SetNumber('3')
        field._save_field_snapshot(b,path)
    result=strap.receive(source,child,pad_uuid=pad,board_hint='synthetic')
    assert not result['ok'] and 'reference_ground_return_length_worsened' in result['errors'][0],result


def test_completed_receipt_reuse_rehashes_copper_and_does_not_trust_caller_mutations(tmp_path):
    source,child,pad,_=fixture(tmp_path);phases=[dict(kind='ground_strap',candidate=str(child),pad_uuid=pad)]
    first=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert first['ok'],first
    first['errors'].append('caller annotation')
    second=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert second['ok'] and not second['errors'] and second['independent_geometry_reused_with_fresh_content_binding']
    b=pcbnew.LoadBoard(str(child));next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').SetWidth(500000)
    field._save_field_snapshot(b,child)
    invalid=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert not invalid['ok'] and invalid['errors'],invalid


def test_changed_runtime_context_invalidates_process_local_proof_reuse(tmp_path,monkeypatch):
    source,child,pad,_=fixture(tmp_path);phases=[dict(kind='ground_strap',candidate=str(child),pad_uuid=pad)]
    first=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert first['ok'],first
    monkeypatch.setenv('CEC_SYNTHETIC_RECEIVING_CONTEXT','changed')
    second=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert second['ok'] and not second['independent_geometry_reused_with_fresh_content_binding'],second


def test_a_file_changed_during_cache_rebinding_never_returns_a_positive_receipt(tmp_path):
    source,child,pad,_=fixture(tmp_path);phases=[dict(kind='ground_strap',candidate=str(child),pad_uuid=pad)]
    first=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert first['ok'],first
    original=force._family;calls=[0]
    def raced(path,hint=None):
        calls[0]+=1
        if calls[0]==3:
            b=pcbnew.LoadBoard(str(child));next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').SetWidth(500000)
            field._save_field_snapshot(b,child)
        return original(path,hint)
    with mock.patch.object(force,'_family',side_effect=raced):
        result=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert not result['ok'] and not result['complete'] and result['errors'],result


@pytest.mark.parametrize('fault',['width','barrel','root_distance','open','pose','outline','foreign_barrel'])
def test_unqualified_or_unrelated_replacement_is_refused(tmp_path,fault):
    source,child,pad,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(child))
    if fault=='width':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(150000)
    elif fault=='barrel':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').SetWidth(500000)
    elif fault=='root_distance':next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').Move(pcbnew.VECTOR2I_MM(2,0))
    elif fault=='open':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').Move(pcbnew.VECTOR2I_MM(0,2))
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,.1))
    elif fault=='outline':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I_MM(.1,0))
    else:
        # An ordinary barrel must be guarded on every copper layer, even if
        # a malformed constructor tried to rely only on the surface strap.
        parent=pcbnew.LoadBoard(str(source));n=pcbnew.NETINFO_ITEM(parent,'ZZ_PROTECTED');parent.Add(n)
        t=track(parent,'ZZ_PROTECTED',(8,10.85),(9,10.85),layer=pcbnew.In2_Cu)
        field._save_field_snapshot(parent,source)
        copied=t.Duplicate();copied.m_Uuid.Clone(t.m_Uuid);b.Add(pcbnew.NETINFO_ITEM(b,'ZZ_PROTECTED'));copied.SetNetCode(b.GetNetcodeFromNetname('ZZ_PROTECTED'));b.Add(copied)
    field._save_field_snapshot(b,child)
    result=strap.receive(source,child,pad_uuid=pad,board_hint='synthetic')
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('fault',['power_ground','capacitor','tee','protected','source_binding','budget'])
def test_source_typing_does_not_authorize_arbitrary_ground_ripup(tmp_path,fault):
    source,_child,pad,proposal=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    if fault=='power_ground':next(iter(b.GetFootprints())).FindPadByNumber('1').SetNumber('4')
    elif fault=='capacitor':next(iter(b.GetFootprints())).SetValue('100nF')
    elif fault=='tee':track(b,'GND',(7,10),(7,12))
    elif fault=='protected':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').SetLocked(True)
    elif fault=='source_binding':
        next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
        with pytest.raises(ValueError,match='source_binding'):strap.subtract(b,proposal)
        return
    with pytest.raises(ValueError):strap.plan(b,pad,timeout_s=0 if fault=='budget' else 10)


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_locked_logical_leaf_requires_exact_source_owned_scope(tmp_path,rotation):
    source,child,pad,_=fixture(tmp_path,rotation,'ARBITRARY_ADDRESS_OWNER')
    b=pcbnew.LoadBoard(str(source));tracks=[];via=None
    for item in b.GetTracks():
        item.SetLocked(True)
        if item.GetClass()=='PCB_TRACK':tracks.append(force._uid(item))
        else:via=force._uid(item)
    field._save_field_snapshot(b,source)
    assert not strap.receive(source,child,pad_uuid=pad,board_hint='synthetic')['ok']
    scope=dict(allow_locked_track_uuids=tracks,allow_locked_via_uuid=via)
    result=strap.receive(source,child,pad_uuid=pad,board_hint='synthetic',**scope)
    assert result['ok'] and result['complete'],result
    row=dict(kind='ground_strap',candidate=str(child),pad_uuid=pad,**scope)
    result=chain.receive(source,child,board_hint='synthetic',phases=[row])
    assert result['ok'] and result['complete'],result


@pytest.mark.parametrize('fault',['power_ground','unknown','unowned_track','unowned_via','forged_subtraction'])
def test_lock_scope_never_replaces_actual_ground_leaf_ownership(tmp_path,fault):
    source,child,pad,_=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));tracks=[];via=None
    for item in b.GetTracks():
        item.SetLocked(True)
        if item.GetClass()=='PCB_TRACK':tracks.append(force._uid(item))
        else:via=force._uid(item)
    scope=dict(allow_locked_track_uuids=tracks,allow_locked_via_uuid=via)
    if fault=='power_ground':next(iter(b.GetFootprints())).FindPadByNumber('1').SetNumber('7')
    elif fault=='unknown':next(iter(b.GetFootprints())).SetValue('UNKNOWN')
    elif fault=='unowned_track':scope['allow_locked_track_uuids']+=['00000000-0000-0000-0000-000000000001']
    elif fault=='unowned_via':scope['allow_locked_via_uuid']='00000000-0000-0000-0000-000000000001'
    else:
        proposal=strap.plan(b,pad,**scope)
        proposal['retired_track_uuids']=[]
        with pytest.raises(ValueError,match='exact_source_scope'):strap.subtract(b,proposal)
        return
    with pytest.raises(ValueError):strap.plan(b,pad,**scope)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('locked',[False,True])
def test_real_overlapping_via_end_kernel_is_not_a_ground_mesh_or_second_branch(tmp_path,rotation,locked):
    source,child,pad,proposal=fixture(tmp_path,rotation,'UNRELATED_LOGICAL_NAME',kernel=True)
    assert len(proposal['retired_track_uuids'])==3
    scope={}
    if locked:
        b=pcbnew.LoadBoard(str(source))
        for t in b.GetTracks():t.SetLocked(True)
        field._save_field_snapshot(b,source)
        scope=dict(allow_locked_track_uuids=proposal['retired_track_uuids'],
            allow_locked_via_uuid=proposal['retired_via_uuid'])
    result=strap.receive(source,child,pad_uuid=pad,board_hint='synthetic',**scope)
    assert result['ok'] and result['complete'],result
    assert not result['current_authority'] and not result['release_authority']
