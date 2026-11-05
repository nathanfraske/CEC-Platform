"""Exact independent original-template body roles; no native DRC admission."""
import copy
import re
from pathlib import Path

import pcbnew
import pytest
import cec_optional_body_ink_contract as op
import cec_field_coupling as field
import cec_force_current as force


def set_field(fp,name,text):
    field=fp.GetField(name)
    if field is None:
        field=pcbnew.PCB_FIELD(fp,pcbnew.FIELD_T_USER,name);field.SetVisible(False);fp.Add(field)
    field.SetText(text)


def fixture(tmp_path,turn=0,back=False,name='XFCN_TTR32100127-0600_THT_M3_60A'):
    library=op.ROOT/'lib/vendor/Connector_Screw.pretty'
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    fp=pcbnew.FootprintLoad(str(library),name);board.Add(fp)
    fp.SetFPID(pcbnew.LIB_ID('renamed-original-vendor',name));fp.SetReference('ARBITRARY_OWNER')
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(21,19))
    set_field(fp,'historical opaque field','must remain exactly untouched')
    # Author a fresh synthetic saved Source (not a retained-board edit).
    # Back-face custom fields acquire explicit native defaults on first save.
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    table=tmp_path/'fp-lib-table'
    table.write_text('(fp_lib_table (version 7) (lib (name "renamed-original-vendor") '
        '(type "KiCad") (uri "'+str(library)+'") (options "") (descr "explicit source")))')
    return source,table,force._uid(fp)


def inspect(source,table,uid,**kwargs):
    return op.inspect(source,library_table=table,footprint_uuid=uid,
        expected_source_sha256=force._hash(source),**kwargs)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_exact_original_body_role_preserves_all_nonoptional_literals(tmp_path,turn,back):
    source,table,uid=fixture(tmp_path,turn,back);before=source.read_bytes()
    proof=inspect(source,table,uid)
    assert len(proof['graphic_uuids'])==3 and proof['preserved_nonoptional_silk_count']==5
    child=tmp_path/'private.kicad_pcb';child.write_text(op.expected_omission(source,proof))
    r=op.receive_literal(source,child,proof)
    assert r['ok'] and r['scope_only'] and r['native_drc_and_full_context_receiving_required']
    assert not r['physical_change_authority'] and not r['release_authority']
    board=pcbnew.LoadBoard(str(child));fp=next(iter(board.GetFootprints()))
    face=pcbnew.B_SilkS if back else pcbnew.F_SilkS
    assert len([g for g in fp.GraphicalItems()if g.GetLayer()==face])==5
    assert fp.GetFieldText('historical opaque field')=='must remain exactly untouched'
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['pad','hole','mask','fab','notch','extra_mark','model','mpn','group'])
def test_changed_source_physical_or_functional_template_never_qualifies(tmp_path,fault):
    source,table,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    if fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='hole':next(iter(fp.Pads())).SetDrillSize(pcbnew.VECTOR2I_MM(.1,.1))
    elif fault=='mask':next(iter(fp.Pads())).SetLocalSolderMaskMargin(1)
    elif fault=='mpn':set_field(fp,'MPN','not-the-original-manufacturer-part')
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('arbitrary');b.Add(group);group.AddItem(fp)
    elif fault=='model':
        model=pcbnew.FP_3DMODEL();model.m_Filename='unapproved-model.step';fp.Models().push_back(model)
    else:
        lines=[g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_SilkS]
        if fault=='fab':g=next(g for g in fp.GraphicalItems()if hasattr(g,'GetShape')and g.GetLayer()==pcbnew.F_Fab)
        elif fault=='notch':g=next(g for g in lines if g.GetStart().y==21500000 or g.GetEnd().y==21500000)
        else:
            g=pcbnew.PCB_SHAPE(fp);g.SetShape(pcbnew.SHAPE_T_SEGMENT);g.SetLayer(pcbnew.F_SilkS)
            g.SetStart(pcbnew.VECTOR2I(0,0));g.SetEnd(pcbnew.VECTOR2I_MM(1,0));g.SetWidth(200000);fp.Add(g)
        g.Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):inspect(source,table,uid)


@pytest.mark.parametrize('fault',['notch','pad','root','field','courtyard','extra_body_uuid'])
def test_saved_scope_cannot_hide_any_unowned_change_or_forge_role(tmp_path,fault):
    source,table,uid=fixture(tmp_path);proof=inspect(source,table,uid)
    child=tmp_path/'private.kicad_pcb';text=op.expected_omission(source,proof)
    if fault=='extra_body_uuid':
        proof=copy.deepcopy(proof);proof['graphic_uuids'].append('invented-functional-mark')
    elif fault=='field':text=text.replace('must remain exactly untouched','changed',1)
    elif fault=='root':text=text.replace('(generator ', '(generator changed_',1)
    else:
        a,b=op.raw.inventory(text)[uid];owner=text[a:b]
        tag={'notch':'fp_line','pad':'pad','courtyard':'fp_rect'}[fault]
        x,y=next((x,y)for x,y in op.raw.children(owner)if op.ink._node(owner[x:y])[0]==tag)
        part=owner[x:y]
        number=re.search(r'\((?:start|at)\s+(-?[0-9.]+)',part)
        assert number is not None
        old=number.group(1);new='%.6f'%(float(old)+.000001)
        changed=part[:number.start(1)]+new+part[number.end(1):]
        text=text[:a+x]+changed+text[a+y:]
    child.write_text(text)
    with pytest.raises(ValueError):op.receive_literal(source,child,proof)


def test_t34069_offset_silhouette_uses_separate_positive_correlated_body_contract(tmp_path):
    source,table,uid=fixture(tmp_path,name='XFCN_T34069_THT_M3_40A')
    proof=inspect(source,table,uid)
    assert proof['policy']==op.CORRELATED_POLICY and proof['policy']!=op.POLICY
    assert len(proof['graphic_uuids'])==4
    assert proof['physical_change_authority'] is False
    assert proof['complete_fab_and_courtyard_must_survive'] is True


def test_source_and_table_epochs_are_bound(tmp_path):
    source,table,uid=fixture(tmp_path);proof=inspect(source,table,uid)
    table.write_text(table.read_text().replace('explicit source','changed epoch'))
    with pytest.raises(ValueError,match='contract_changed'):op.expected_omission(source,proof)
    with pytest.raises(ValueError,match='exact_saved_optional_body_source'):
        op.inspect(source,library_table=table,footprint_uuid=uid,expected_source_sha256='0'*64)


@pytest.mark.parametrize('seconds',[True,0,11,float('nan')])
def test_bound_cannot_be_relaxed(seconds):
    with pytest.raises(ValueError):op.inspect('missing',library_table='missing',footprint_uuid='x',
        expected_source_sha256='0'*64,timeout_s=seconds)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_already_omitted_body_needs_complete_original_derivative_and_explicit_opt_in(tmp_path,turn,back):
    source,table,uid=fixture(tmp_path,turn,back);proof=inspect(source,table,uid)
    child=tmp_path/'original-minus-body.kicad_pcb';child.write_text(op.expected_omission(source,proof))
    with pytest.raises(ValueError):inspect(child,table,uid)
    replay=inspect(child,table,uid,allow_already_omitted=True)
    assert replay['graphic_uuids']==[] and replay['preserved_nonoptional_silk_count']==5
    assert replay['source_optional_body_state']=='already_omitted_approved_body'
    assert op.expected_omission(child,replay)==child.read_text()


@pytest.mark.parametrize('fault',['locked_owner','locked_body','partial_body','root_physical_setting'])
def test_locked_partial_or_unknown_native_source_setting_is_not_optional_body_authority(tmp_path,fault):
    source,table,uid=fixture(tmp_path)
    if fault=='root_physical_setting':
        text=source.read_text();assert '(duplicate_pad_numbers_are_jumpers no)'in text
        source.write_text(text.replace('(duplicate_pad_numbers_are_jumpers no)',
            '(duplicate_pad_numbers_are_jumpers yes)',1))
    else:
        board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
        if fault=='locked_owner':fp.SetLocked(True)
        else:
            original=inspect(source,table,uid)
            shape=next(g for g in fp.GraphicalItems()if force._uid(g)in original['graphic_uuids'])
            if fault=='locked_body':shape.SetLocked(True)
            else:op.ink.discard_footprint_children(board,fp,[shape])
        field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):inspect(source,table,uid,allow_already_omitted=True)


def test_template_derivative_is_only_three_literal_lines_not_functional_or_physical_nodes(tmp_path):
    source,table,uid=fixture(tmp_path);proof=inspect(source,table,uid)
    derivative=op.template_omission(proof['template'])
    assert len(derivative['graphic_ids'])==3 and derivative['preserved_functional_silk_lines']==5
    text=Path(proof['template']).read_text();changes=[]
    for a,b in op.raw.children(text):
        node=op.ink._node(text[a:b])
        identity=op.ink._uid(node)or 'literal:'+op.ink._digest(text[a:b])
        if identity in derivative['graphic_ids']:
            assert node[0]=='fp_line';changes.append((a,b,''))
    assert len(changes)==3 and op.ink._edits(text,changes)==derivative['derivative_text']
