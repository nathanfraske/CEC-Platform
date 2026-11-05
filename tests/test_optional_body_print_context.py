"""Approved body omission keeps same-FPID physical/library authority literal."""
import copy
from pathlib import Path

import pcbnew
import pytest
import cec_nonpolar_print_context as op
import cec_optional_body_ink_contract as body
import cec_field_coupling as field
import cec_force_current as force
from test_optional_body_ink_contract import fixture as body_fixture


def fixture(tmp_path,turn=0,back=False):
    origin=tmp_path/'source';origin.mkdir()
    source,table,uid=body_fixture(origin,turn,back)
    board=pcbnew.LoadBoard(str(source))
    terminal=next(iter(board.GetFootprints()));body_fpid=terminal.GetFPIDAsString()
    lib=body.ROOT/'lib/vendor/Resistor_SMD.pretty'
    resistor=pcbnew.FootprintLoad(str(lib),'R_0402_1005Metric');board.Add(resistor)
    resistor.SetFPID(pcbnew.LIB_ID('cec-Resistor_SMD','R_0402_1005Metric'))
    resistor.SetReference('ANOTHER_LABEL');resistor.SetValue('source-authored')
    resistor.SetPosition(pcbnew.VECTOR2I_MM(10,10));resistor.SetOrientationDegrees(turn)
    field._save_field_snapshot(board,source)
    text=table.read_text();i=text.rfind(')')
    table.write_text(text[:i]+'(lib (name "cec-Resistor_SMD") (type "KiCad") (uri "'+str(lib)+'") (options "") (descr "original"))'+text[i:])
    ids=sorted([uid,force._uid(resistor)])
    return source,table,ids,[body_fpid,resistor.GetFPIDAsString()],body_fpid


def planned(source,table,ids,fpids,body_fpid):
    return op.plan(source,library_table=table,footprint_ids=fpids,
        expected_instance_uuids=ids,board_hint='synthetic',optional_body_footprint_ids=[body_fpid])


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_mixed_body_and_nonpolar_context_replays_with_all_functional_marks_and_fab(tmp_path,turn,back):
    source,table,ids,fpids,body_fpid=fixture(tmp_path,turn,back);raw=source.read_bytes()
    q=planned(source,table,ids,fpids,body_fpid)
    assert q['optional_body_footprint_ids']==[body_fpid]
    record=next(r for r in q['records']if r['fpid']==body_fpid)
    assert len(record['graphic_uuids'])==3 and record['source_optional_body_contract']['preserved_nonoptional_silk_count']==5
    artifact=op.construct_private(source,q,tmp_path/'private');child=Path(artifact['candidate'])
    received=op.receive(source,child,q)
    assert received['ok']and received['complete'],received
    assert not received['admitted']and received['source_physical_identity_unchanged']
    board=pcbnew.LoadBoard(str(child));terminal=next(f for f in board.GetFootprints()if f.GetFPIDAsString()==body_fpid)
    face=pcbnew.B_SilkS if back else pcbnew.F_SilkS
    assert len([g for g in terminal.GraphicalItems()if g.GetLayer()==face])==5
    # Future passes rederive Original-minus-approved-body, never interpret
    # an absence of ink or a previous receipt as new omission authority.
    again=planned(child,table,ids,fpids,body_fpid)
    body_record=next(r for r in again['records']if r['fpid']==body_fpid)
    assert body_record['graphic_uuids']==[] and body_record['source_optional_body_state']=='already_omitted_approved_body'
    replay=op.construct_private(child,again,tmp_path/'next-private')
    assert Path(replay['candidate']).read_bytes()==child.read_bytes()
    assert op.receive(child,replay['candidate'],again)['ok']
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['functional_mark','pad','fab','courtyard','model','body_library','wrong_fpid','forged_role'])
def test_mixed_body_context_cannot_erase_unowned_art_or_mutate_physical_material(tmp_path,fault):
    source,table,ids,fpids,body_fpid=fixture(tmp_path)
    q=planned(source,table,ids,fpids,body_fpid)
    if fault=='forged_role':
        q=copy.deepcopy(q);record=next(r for r in q['records']if r['fpid']==body_fpid)
        record['graphic_uuids'].append('unowned-functional-mark')
        with pytest.raises(ValueError):op.construct_private(source,q,tmp_path/'private')
        return
    artifact=op.construct_private(source,q,tmp_path/'private');child=Path(artifact['candidate'])
    if fault=='body_library':
        alias,item=body_fpid.split(':',1);path=Path(artifact['new_library_context']['rows'][alias]['path'])/(item+'.kicad_mod')
        path.write_text(path.read_text()+'\n# changed template\n')
    else:
        board=pcbnew.LoadBoard(str(child));fp=next(f for f in board.GetFootprints()if f.GetFPIDAsString()==body_fpid)
        if fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='model':m=pcbnew.FP_3DMODEL();m.m_Filename='changed.step';fp.Models().push_back(m)
        elif fault=='wrong_fpid':fp.SetFPID(pcbnew.LIB_ID('different','body'))
        else:
            layer={'functional_mark':pcbnew.F_SilkS,'fab':pcbnew.F_Fab,'courtyard':pcbnew.F_CrtYd}[fault]
            next(g for g in fp.GraphicalItems()if g.GetLayer()==layer).Move(pcbnew.VECTOR2I(1,0))
        field._save_field_snapshot(board,child)
    assert op.receive(source,child,q)['ok']is False


@pytest.mark.parametrize('flag',[True,None,'terminal',[False],['not-selected:body']])
def test_body_policy_is_an_explicit_finite_fpid_subset_not_a_truthy_permission(tmp_path,flag):
    source,table,ids,fpids,body_fpid=fixture(tmp_path)
    with pytest.raises(ValueError):
        op.plan(source,library_table=table,footprint_ids=fpids,expected_instance_uuids=ids,
            board_hint='synthetic',optional_body_footprint_ids=flag)
