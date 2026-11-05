import pcbnew
import pytest
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_source_reference_group_transport as annotations
from test_source_reference_group_transport import external_fixture


def test_row_default_stays_group_refusal_explicit_scope_moves_whole_map(tmp_path):
    source,owner,group=external_fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));ref=fp.GetReference()
    poses={ref:[10.25,10.,0.]}
    with pytest.raises(ValueError,match='unlocked_translation_only'):
        row.plan(b,poses,{})
    proposal=row.plan(b,poses,{},reference_group_uuids=[group])
    assert proposal['source_reference_group_transports'][ref]['owner_uuid']==owner
    row.apply(b,proposal)
    child=tmp_path/'translated.kicad_pcb';field._save_field_snapshot(b,child)
    proof=annotations.inspect(source,owner_uuid=owner,group_uuid=group)
    assert annotations.verify(source,child,proof,delta_nm=(250000,0))['ok']
    assert next(iter(b.Groups())).IsLocked() and not next(iter(b.GetFootprints())).IsLocked()


@pytest.mark.parametrize('scope',[['missing'],[True],True,['same','same']])
def test_explicit_scope_cannot_be_missing_forged_or_ambiguous(tmp_path,scope):
    source,owner,group=external_fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError):row.plan(b,{'X7':[10.25,10.,0.]},{},reference_group_uuids=scope)


def test_source_annotation_scope_needs_existing_explicit_physical_rotation_policy(tmp_path):
    source,owner,group=external_fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError,match='explicit_cardinal_rotation'):
        row.plan(b,{'X7':[10.25,10.,90.]},{},reference_group_uuids=[group])
    proposal=row.plan(b,{'X7':[10.25,10.,90.]},{},reference_group_uuids=[group],allow_cardinal_rotations=True)
    row.apply(b,proposal)
    child=tmp_path/'quarter.kicad_pcb';field._save_field_snapshot(b,child)
    import cec_complete_macro_cell as complete
    proof=annotations.inspect(source,owner_uuid=owner,group_uuid=group)
    complete._save_cardinal_reference_nodes(child,[(proof,1,(250000,0))])
    assert annotations.verify_cardinal(source,child,proof,quarter_turns=1,delta_nm=(250000,0))['ok']


def test_macro_optin_rederives_whole_root_annotation_frame(tmp_path):
    import cec_smd_macro_transport as macro
    source,owner,group=external_fixture(tmp_path);p=annotations.inspect(source,owner_uuid=owner,group_uuid=group)
    parent=pcbnew.LoadBoard(str(source));child=pcbnew.LoadBoard(str(source))
    annotations.transform(child,p,delta_nm=(250000,0))
    with pytest.raises(ValueError,match='ungrouped_all_smd'):
        macro.apply(parent,child,source_path=source,board_hint='synthetic',retain_source_tracks=True)
    result=macro.apply(parent,child,source_path=source,board_hint='synthetic',retain_source_tracks=True,
        reference_group_uuids=[group])
    assert result
    text=next(i for i in child.GetDrawings()if i.GetClass()=='PCB_TEXT')
    text.Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(ValueError,match='annotation_replay_differs'):
        macro.apply(parent,child,source_path=source,board_hint='synthetic',retain_source_tracks=True,
            reference_group_uuids=[group])


def test_macro_packet_replay_does_not_drop_explicit_reference_scope():
    import cec_cell_macro_requests as compiler
    packet={'explicit_native_macro_options':{'reference_group_uuids':['source-group']}}
    assert compiler.packet_options(packet)['reference_group_uuids']==['source-group']
