"""Keep the strict source AST gate; fix the constructor's hidden-field order."""
import copy

import pcbnew
import pytest
import cec_additive_route_receiving as ast
import cec_source_reference_group_transport as reference
import cec_source_retaining_ses_import as raw
import cec_field_coupling as field
import cec_force_current as force
from test_source_reference_group_transport import fixture


def source_with_appended_hide(tmp_path):
    source,owner,group=fixture(tmp_path)
    text=raw.raw_text(source);nodes=ast._nodes(source)[1];node=copy.deepcopy(nodes[owner])
    prop=next(c for c in node if isinstance(c,list)and c[:2]==['property','"Reference"'])
    hide=next(c for c in prop if isinstance(c,list)and c and c[0]=='hide')
    prop.remove(hide);prop.append(hide)
    a,z=raw.inventory(text)[owner];raw.write_raw(source,text[:a]+ast._render(node)+text[z:])
    proof=reference.inspect(source,owner_uuid=owner,group_uuid=group)
    board=pcbnew.LoadBoard(str(source));reference.transform(board,proof,delta_nm=(250000,0))
    candidate=tmp_path/'candidate.kicad_pcb';field._save_field_snapshot(board,candidate)
    return source,candidate,owner,proof


def test_native_save_order_is_restored_instead_of_weakening_literal_receiving(tmp_path):
    source,candidate,owner,proof=source_with_appended_hide(tmp_path)
    source_sha=force._hash(source);before=field._field_snapshot_inventory(pcbnew.LoadBoard(str(candidate)))
    with pytest.raises(ValueError,match='source_expected_annotation_translation_differs'):
        reference.verify(source,candidate,proof,delta_nm=(250000,0))
    report=reference.preserve_literal_hidden_field_order(candidate,[(proof,(250000,0))])
    assert report['restored_source_literal_node_uuids']==[owner]
    assert report['saved_receiving_not_relaxed']and not report['routing_admitted']
    assert reference.verify(source,candidate,proof,delta_nm=(250000,0))['ok']
    assert source_sha==force._hash(source)
    assert before==field._field_snapshot_inventory(pcbnew.LoadBoard(str(candidate)))


@pytest.mark.parametrize('fault',['visibility','pad','font','duplicate_hide','unknown_property'])
def test_no_part_ink_or_visibility_change_can_be_repaired_as_writer_order(tmp_path,fault):
    source,candidate,owner,proof=source_with_appended_hide(tmp_path)
    board=pcbnew.LoadBoard(str(candidate));fp=next(f for f in board.GetFootprints()if force._uid(f)==owner)
    if fault=='visibility':fp.Reference().SetVisible(True)
    elif fault=='pad':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(.9,.9))
    elif fault=='font':next(i for i in board.GetDrawings()if i.GetClass()=='PCB_TEXT').SetTextThickness(130000)
    if fault in ('visibility','pad','font'):field._save_field_snapshot(board,candidate)
    else:
        text=raw.raw_text(candidate);node=copy.deepcopy(ast._nodes(candidate)[1][owner])
        prop=next(c for c in node if isinstance(c,list)and c[:2]==['property','"Reference"'])
        prop.append(['hide','yes']if fault=='duplicate_hide'else['unknown','authored'])
        a,z=raw.inventory(text)[owner];raw.write_raw(candidate,text[:a]+ast._render(node)+text[z:])
    before=force._hash(candidate)
    with pytest.raises(ValueError):reference.preserve_literal_hidden_field_order(candidate,[(proof,(250000,0))])
    assert before==force._hash(candidate)


def test_unrelated_new_copper_and_candidate_raw_text_remain_literal(tmp_path):
    from test_field_proposals import track
    source,candidate,owner,proof=source_with_appended_hide(tmp_path)
    board=pcbnew.LoadBoard(str(candidate));new=track(board,'/N',(20,20),(21,20),width=.2)
    field._save_field_snapshot(board,candidate)
    text=raw.raw_text(candidate);span=raw.inventory(text)[force._uid(new)];literal=text[slice(*span)]
    reference.preserve_literal_hidden_field_order(candidate,[(proof,(250000,0))])
    after=raw.raw_text(candidate);span=raw.inventory(after)[force._uid(new)]
    assert literal==after[slice(*span)]
