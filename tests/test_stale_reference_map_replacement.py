import pcbnew
import pytest
import cec_stale_reference_map_replacement as op
import cec_force_current as force
import cec_field_coupling as field
from test_source_reference_group_transport import fixture


def stale(tmp_path,fault=None):
    source,owner,group=fixture(tmp_path,fault)
    board=pcbnew.LoadBoard(str(source));fp=next(i for i in board.GetFootprints() if force._uid(i)==owner)
    fp.Move(pcbnew.VECTOR2I_MM(2,1))
    for item in board.GetDrawings():item.SetLocked(True)
    field._save_field_snapshot(board,source)
    return source,owner,group


def test_exact_annotation_repair_preserves_every_other_source_byte(tmp_path):
    source,owner,group=stale(tmp_path);before=source.read_bytes()
    q=op.plan(source,source_sha256=force._hash(source),owner_uuid=owner,group_uuid=group)
    candidate=force._copy_family(source,tmp_path/'candidate')
    op.write_private(source,candidate,q)
    result=op.receive(source,candidate,q)
    assert result['ok'] and result['all_other_source_bytes_exact'] and source.read_bytes()==before
    assert len(q['annotation_uuids'])==5 and q['delta_nm']==[2000000,1000000]
    assert op.ast._nodes(source)[1][owner]==op.ast._nodes(candidate)[1][owner]


@pytest.mark.parametrize('fault',['copper','secondfp','wrongtext','name','layer','mirror','nested','court'])
def test_foreign_functional_or_ambiguous_source_is_refused(tmp_path,fault):
    source,owner,group=stale(tmp_path,fault)
    with pytest.raises(ValueError):op.plan(source,source_sha256=force._hash(source),owner_uuid=owner,group_uuid=group)


def test_hash_unchanged_and_changed_material_refused(tmp_path):
    source,owner,group=stale(tmp_path)
    with pytest.raises(ValueError):op.plan(source,source_sha256='0'*64,owner_uuid=owner,group_uuid=group)
    q=op.plan(source,source_sha256=force._hash(source),owner_uuid=owner,group_uuid=group)
    candidate=force._copy_family(source,tmp_path/'child')
    with pytest.raises(ValueError):op.receive(source,candidate,q)
    op.write_private(source,candidate,q)
    candidate.write_text(candidate.read_text().replace('(generator ', '(generator changed_',1))
    with pytest.raises(ValueError):op.receive(source,candidate,q)


def test_nonstale_map_is_not_replacement_authority(tmp_path):
    source,owner,group=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(source,source_sha256=force._hash(source),owner_uuid=owner,group_uuid=group)


def test_extra_functional_mark_is_not_nearest_reference_leader(tmp_path):
    source,owner,group=stale(tmp_path)
    board=pcbnew.LoadBoard(str(source));g=next(i for i in board.Groups() if force._uid(i)==group)
    line=pcbnew.PCB_SHAPE(board);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.B_SilkS)
    line.SetStart(pcbnew.VECTOR2I_MM(9,9));line.SetEnd(pcbnew.VECTOR2I_MM(10,9));line.SetWidth(120000);line.SetLocked(True)
    board.Add(line);g.AddItem(line);field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):op.plan(source,source_sha256=force._hash(source),owner_uuid=owner,group_uuid=group)


def test_changed_rule_companion_cannot_be_annotation_only(tmp_path):
    source,owner,group=stale(tmp_path)
    q=op.plan(source,source_sha256=force._hash(source),owner_uuid=owner,group_uuid=group)
    candidate=force._copy_family(source,tmp_path/'child');op.write_private(source,candidate,q)
    candidate.with_suffix('.kicad_dru').write_text('(version 1)')
    with pytest.raises(ValueError):op.receive(source,candidate,q)
