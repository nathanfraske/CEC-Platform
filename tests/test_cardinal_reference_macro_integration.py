import copy
import pcbnew
import pytest
import cec_cell_row_rebuild as row
import cec_smd_macro_transport as transport
import cec_complete_macro_cell as macro
import cec_source_reference_group_transport as reference
import cec_control_shunt_placement as shunt
import cec_field_coupling as field
import cec_force_current as force
import cec_cell_macro_requests as compiler
from test_source_reference_group_cardinal import fixture
from test_control_shunt_reference_group import fixture as shunt_fixture


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[1,2,3])
def test_complete_macro_actual_frame_preserves_requested_cardinal_angle(tmp_path,monkeypatch,back,turn):
    source,proof=fixture(tmp_path,back=back,source_turn=270,external=True)
    parent=pcbnew.LoadBoard(str(source));fp=next(iter(parent.GetFootprints()))
    poses={fp.GetReference():[10.25,9.75,(270+turn*90)%360]}
    plan=row.plan(parent,poses,{},reference_group_uuids=[proof['group_uuid']],allow_cardinal_rotations=True)
    proposal=dict(poses=poses,row_plan=plan,board_hint='synthetic',max_shift_mm=16.,
        allow_owned_locked_escapes=True,
        reference_group_uuids=[proof['group_uuid']])
    # A genuinely unwired frame needs no fabricated old conductor. The real
    # compiler must independently select strict retain-all-old-copper mode.
    actual,received=compiler._frame(parent,source,proposal)
    assert received and next(iter(actual.GetFootprints())).GetOrientationDegrees()%360==poses[fp.GetReference()][2]
    import cec_source_reference_group_cardinal_batch as batch
    assert batch.verify_native(source,actual,[(proof,turn,(250000,-250000))])['ok']


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[1,2,3])
def test_row_native_transport_and_exact_saved_map(tmp_path,back,turn):
    source,proof=fixture(tmp_path,back=back,source_turn=270,external=True)
    parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(source))
    fp=next(iter(child.GetFootprints()));poses={fp.GetReference():[10.25,9.75,(270+turn*90)%360]}
    plan=row.plan(child,poses,{},reference_group_uuids=[proof['group_uuid']],allow_cardinal_rotations=True)
    row.apply(child,plan)
    result=transport.apply(parent,child,source_path=source,board_hint='synthetic',retain_source_tracks=True,
        reference_group_uuids=[proof['group_uuid']],allow_cardinal_rotations=True)
    assert result
    candidate=tmp_path/'candidate.kicad_pcb'
    packet=dict(scope='source_typed_complete_native_macro_requests',source=str(source),source_sha256=force._hash(source),
        code_identity=force._code_identity(),source_plan=dict(poses=poses,row_plan=plan,max_shift_mm=16.))
    saved=macro.save_private(child,candidate,packet)
    assert saved['literal_source_reference_save']['independent_native_and_exact_writer_inventory_received']
    assert reference.verify_cardinal(source,candidate,proof,quarter_turns=turn,delta_nm=(250000,-250000))['ok']
    assert next(iter(child.Groups())).IsLocked()and not fp.IsLocked()


@pytest.mark.parametrize('fault',['no_policy','noncardinal','flip','ink','locked'])
def test_cardinal_group_does_not_waive_physical_transport_guards(tmp_path,fault):
    source,proof=fixture(tmp_path);parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(source))
    reference.transform_cardinal(child,proof,quarter_turns=1)
    if fault=='noncardinal':next(iter(child.GetFootprints())).SetOrientationDegrees(45)
    elif fault=='flip':next(iter(child.GetFootprints())).Flip(pcbnew.VECTOR2I(0,0),False)
    elif fault=='ink':next(iter(child.GetDrawings())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='locked':next(iter(child.GetFootprints())).SetLocked(True)
    with pytest.raises(ValueError):transport.apply(parent,child,source_path=source,board_hint='synthetic',
        retain_source_tracks=True,reference_group_uuids=[proof['group_uuid']],allow_cardinal_rotations=fault!='no_policy')


@pytest.mark.parametrize('turn',[1,3])
def test_canonical_shunt_fresh_source_role_allows_only_cardinal_map_motion(tmp_path,monkeypatch,turn):
    b,root,poses,gid=shunt_fixture(tmp_path,monkeypatch)
    next(iter(poses.values()))[2]=turn*90
    selected=shunt.plan(b,poses,board_hint=str(root),reference_group_uuids=[gid])
    child=pcbnew.LoadBoard(b.GetFileName());proof=next(iter(selected.values()))['source_reference_group_authorization']
    reference.transform_cardinal(child,proof,quarter_turns=turn,delta_nm=(500000,0))
    proposal=dict(poses=poses,selected_control_shunts=selected,board_hint=str(root),reference_group_uuids=[gid])
    assert shunt.requests(b,child,proposal)
    forged=copy.deepcopy(selected);next(iter(forged.values()))['source_reference_group_authorization']['member_uuids'].append('forged')
    with pytest.raises(ValueError):shunt.requests(b,child,dict(proposal,selected_control_shunts=forged))


@pytest.mark.parametrize('fault',['pad','property','unknown','font','leader'])
def test_cardinal_constructor_writer_repair_never_accepts_changed_material(tmp_path,fault):
    source,proof=fixture(tmp_path,external=True);b=pcbnew.LoadBoard(str(source))
    reference.transform_cardinal(b,proof,quarter_turns=1);candidate=tmp_path/'bad.kicad_pcb'
    if fault=='pad':next(iter(next(iter(b.GetFootprints())).Pads())).SetSize(pcbnew.VECTOR2I_MM(.9,.9))
    elif fault=='property':next(iter(b.GetFootprints())).SetValue('wrong')
    elif fault=='unknown':next(iter(b.GetFootprints())).SetField('unknown','not Source')
    elif fault=='font':next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT').SetTextThickness(130000)
    else:next(i for i in b.GetDrawings()if i.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(b,candidate);before=force._hash(candidate)
    with pytest.raises(ValueError):macro._save_cardinal_reference_nodes(candidate,[(proof,1,(0,0))])
    assert force._hash(candidate)==before
