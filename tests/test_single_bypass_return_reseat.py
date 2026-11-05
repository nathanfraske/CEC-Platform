"""A sole bypass return may be replaced, never silently deleted."""
from pathlib import Path
import pcbnew
import pytest
import cec_bypass_return_reseat as reseat
import cec_redundant_bypass_ground as deletion
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items
from test_bypass_return_reseat import fixture


def single(tmp_path,rotation=0):
    source,target,pad,edge=fixture(tmp_path,rotation=rotation)
    uid=pcbnew.KIID()
    for path in (source,target):
        board=pcbnew.LoadBoard(str(path));owner=board.FindFootprintByReference('ICA').FindPadByNumber('7')
        cap=board.FindFootprintByReference('CA').FindPadByNumber('2')
        endpoints={tuple(owner.GetPosition()),tuple(cap.GetPosition())}
        links=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND'
               and {tuple(t.GetStart()),tuple(t.GetEnd())}==endpoints]
        assert len(links)==1;discard_items(board,links)
        via=pcbnew.PCB_VIA(board);via.m_Uuid.Clone(uid);via.SetPosition(owner.GetPosition())
        via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(board.GetNetcodeFromNetname('GND'));board.Add(via)
        field._save_field_snapshot(board,path)
    return source,target,pad,edge


@pytest.mark.parametrize('rotation',(0,90,180,270))
def test_rotated_sole_return_reseat_has_full_replacement_and_no_deletion_authority(tmp_path,rotation):
    source,target,pad,edge=single(tmp_path,rotation);before=source.read_bytes()
    parent=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError,match='another_actual_bypass_ground_departure_required'):
        deletion.plan(parent,pad,edge)
    proposal=reseat.plan(parent,pad,edge)
    assert proposal['requires_alternate_ground_departure'] is False
    with pytest.raises(ValueError,match='another_actual_bypass_ground_departure_required'):
        deletion.subtract(parent,proposal)
    proof=reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['new_path_mm']<proof['source_path_mm'] and proof['source_barrel_geometry_preserved']
    assert source.read_bytes()==before and not proof['release_authority']


def test_missing_replacement_barrel_is_not_justified_by_saved_ground_planes(tmp_path):
    source,target,pad,edge=single(tmp_path);board=pcbnew.LoadBoard(str(target))
    original={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    incoming=[t for t in board.GetTracks() if t.GetClass()=='PCB_VIA' and force._uid(t) not in original]
    assert len(incoming)==1;discard_items(board,incoming);field._save_field_snapshot(board,target)
    proof=reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')
    assert not proof['ok'] and any('exactly_one_return_entry' in error for error in proof['errors'])


@pytest.mark.parametrize('rotation',(0,90,180,270))
def test_explicit_qualified_reseat_can_use_its_exact_unchanged_native_ground_land(tmp_path,rotation):
    import cec_additive_route_receiving as additive
    source,unused,pad,edge=fixture(tmp_path,rotation=rotation,local=True,locked=True)
    board=pcbnew.LoadBoard(str(source));options=dict(allow_owned_locked=True,allow_qualified_local_vias=True)
    proposal=reseat.plan(board,pad,edge,**options);reseat.subtract(board,proposal)
    origin=pcbnew.VECTOR2I(*proposal['root_point_nm']);end=pcbnew.VECTOR2I(origin.x+50000,origin.y)
    track=pcbnew.PCB_TRACK(board);track.SetStart(origin);track.SetEnd(end)
    track.SetLayer(proposal['source_layer']);track.SetWidth(proposal['source_width_nm'])
    track.SetNetCode(board.GetNetcodeFromNetname('GND'));board.Add(track)
    via=pcbnew.PCB_VIA(board);via.SetPosition(end);via.SetWidth(proposal['root_diameter_nm'])
    via.SetDrill(proposal['root_drill_nm']);via.SetLayerPair(*proposal['root_layers'])
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetNetCode(board.GetNetcodeFromNetname('GND'));board.Add(via)
    draft=force._copy_family(source,tmp_path/'inpad-draft');field._save_field_snapshot(board,draft)
    target=Path(additive.finalize_private(source,draft,tmp_path/'inpad-final')['board'])
    proof=reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic',**options)
    assert proof['ok'] and proof['complete'],proof
    assert proof['new_path_mm']==.05 and proof['source_barrel_geometry_preserved']
    assert not reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic')['ok']


@pytest.mark.parametrize('fault',('none','offcentre','remote','no_policy'))
def test_true_inpad_replacement_needs_no_fake_zero_length_trace(tmp_path,fault):
    import cec_additive_route_receiving as additive
    import cec_source_cut_chain as chain
    source,unused,pad,edge=fixture(tmp_path,local=True,locked=True)
    board=pcbnew.LoadBoard(str(source));options=dict(allow_owned_locked=True,allow_qualified_local_vias=True)
    proposal=reseat.plan(board,pad,edge,**options);reseat.subtract(board,proposal)
    at=pcbnew.VECTOR2I(*proposal['root_point_nm'])
    if fault=='offcentre':at.x+=50000
    if fault=='remote':at.x+=700000
    via=pcbnew.PCB_VIA(board);via.SetPosition(at);via.SetWidth(proposal['root_diameter_nm'])
    via.SetDrill(proposal['root_drill_nm']);via.SetLayerPair(*proposal['root_layers'])
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetNetCode(board.GetNetcodeFromNetname('GND'));board.Add(via)
    draft=force._copy_family(source,tmp_path/'zero-draft');field._save_field_snapshot(board,draft)
    target=Path(additive.finalize_private(source,draft,tmp_path/'zero-final')['board'])
    if fault=='no_policy':options['allow_qualified_local_vias']=False
    proof=reseat.receive(source,target,pad_uuid=pad,track_uuid=edge,board_hint='synthetic',**options)
    if fault!='none':
        assert not proof['ok'] and proof['errors'],proof
        return
    assert proof['ok'] and proof['complete'] and proof['new_path_mm']==0,proof
    receipt=chain.receive(source,target,board_hint='synthetic',phases=[dict(
        kind='bypass_return_reseat',candidate=str(target),pad_uuid=pad,track_uuid=edge,**options)])
    assert receipt['ok'] and receipt['complete'],receipt
