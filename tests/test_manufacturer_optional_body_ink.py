"""Registered nonpolar body role, without board/refdes/current exceptions."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_manufacturer_land_pattern as manufacturer
import cec_nonpolar_print_context as printing
import cec_optional_body_ink_contract as body
from test_manufacturer_shunt_land_pattern import fixture as predecessor_fixture

ITEM='R_Bourns_CSS2H-2512R_L500'
FPID='cec-Resistor_SMD:'+ITEM


def fixture(tmp_path,turn=0,back=False,origin='recipe',copied=True):
    root=tmp_path/'source';root.mkdir()
    if origin=='recipe':
        source,uid=predecessor_fixture(root,turn,back,name='ANY_SELECTED_NONPOLAR_OWNER')
        board=pcbnew.LoadBoard(str(source))
        manufacturer.materialize(board,manufacturer.plan(board,[uid]))
        fp=next(iter(board.GetFootprints()))
    else:
        board=pcbnew.BOARD();board.SetCopperLayerCount(6)
        fp=pcbnew.FootprintLoad(str(body.ROOT/'lib/vendor/Resistor_SMD.pretty'),ITEM);board.Add(fp)
        fp.SetFPIDAsString(FPID);fp.SetField('MPN','CSS2H-2512R-L500F');fp.SetValue('0.5mΩ')
        fp.SetReference('DIFFERENT_LABEL_WITHOUT_HEURISTICS')
        if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
        fp.SetOrientationDegrees(turn);fp.SetPosition(pcbnew.VECTOR2I_MM(43.7,29.2))
        for pad in fp.Pads():
            net=pcbnew.NETINFO_ITEM(board,'UNRELATED_NET_'+pad.GetNumber());board.Add(net);pad.SetNet(net)
        uid=force._uid(fp);source=root/'source.kicad_pcb'
    # Preserve arbitrary instance properties as well as functional labels.
    fp.SetField('opaque source label','retained exactly, not optional body ink')
    field._save_field_snapshot(board,source)
    library=body.ROOT/'lib/vendor/Resistor_SMD.pretty'
    if copied:
        target=tmp_path/'independently-copied-original.pretty';target.mkdir()
        (target/(ITEM+'.kicad_mod')).write_bytes((library/(ITEM+'.kicad_mod')).read_bytes());library=target
    table=root/'fp-lib-table';table.write_text('(fp_lib_table (version 7) (lib (name "cec-Resistor_SMD") '
        '(type "KiCad") (uri '+json.dumps(str(library))+') (options "") (descr "explicit source")))')
    return source,table,uid


def inspect(source,table,uid,**kw):
    return body.inspect(source,library_table=table,footprint_uuid=uid,
        expected_source_sha256=force._hash(source),**kw)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('origin',['recipe','canonical'])
def test_two_strokes_are_registered_nonpolar_not_duplicate_fab_edges(tmp_path,turn,back,origin):
    source,table,uid=fixture(tmp_path,turn,back,origin);before=source.read_bytes()
    proof=inspect(source,table,uid)
    assert proof['policy']==body.MANUFACTURER_NONPOLAR_POLICY
    assert proof['policy']not in(body.POLICY,body.CORRELATED_POLICY)
    expected='independent_manufacturer_recipe'if origin=='recipe'else'independent_original_defaults'
    assert proof['independently_reproduced_metadata_origins']==[expected]
    assert len(proof['graphic_uuids'])==2 and proof['preserved_nonoptional_silk_count']==0
    assert Path(proof['canonical_template']).is_relative_to(body.ROOT/'lib/vendor')
    assert proof['template']!=proof['canonical_template']
    assert all(force._hash(p)==h for p,h in proof['template_input_sha256'].items())
    assert not proof['physical_change_authority']and not proof['current_authority']
    child=tmp_path/'private.kicad_pcb';child.write_text(body.expected_omission(source,proof))
    assert body.receive_literal(source,child,proof)['ok']
    with pytest.raises(ValueError):inspect(child,table,uid)
    again=inspect(child,table,uid,allow_already_omitted=True)
    assert again['graphic_uuids']==[] and body.expected_omission(child,again)==child.read_text()
    assert source.read_bytes()==before


@pytest.mark.parametrize('origin',['recipe','canonical'])
@pytest.mark.parametrize('back',[False,True])
def test_saved_print_context_roundtrip_rederives_complete_original_and_metadata(tmp_path,origin,back):
    source,table,uid=fixture(tmp_path,90,back,origin)
    options=dict(library_table=str(table),footprint_ids=[FPID],expected_instance_uuids=[uid],
        board_hint='arbitrary-synthetic-board',optional_body_footprint_ids=[FPID])
    q=printing.plan(source,**options);q=json.loads(json.dumps(q))
    artifact=printing.construct_private(source,q,tmp_path/'private')
    child=Path(artifact['candidate']);before=source.read_bytes()
    r=printing.receive_staged(source,child,q)
    assert r['ok']and r['complete'],r
    assert r['scope_only']and not r['admitted']and not r['release_authority']
    assert r['source_physical_identity_unchanged']
    assert all(force._hash(p)==h for p,h in q['dependency_sha256'].items())
    source_board=pcbnew.LoadBoard(str(source));candidate_board=pcbnew.LoadBoard(str(child))
    left=next(iter(source_board.GetFootprints()));right=next(iter(candidate_board.GetFootprints()))
    assert left.GetFPIDAsString()==right.GetFPIDAsString()==FPID
    assert left.GetReference()==right.GetReference()
    assert left.GetFieldText('opaque source label')==right.GetFieldText('opaque source label')
    assert [(force._uid(p),manufacturer._pad(p),p.GetNetname())for p in left.Pads()]==[
        (force._uid(p),manufacturer._pad(p),p.GetNetname())for p in right.Pads()]
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['pad','drill','mask','courtyard','fab','model','unknown_mark',
    'mpn','nearby_mpn','value','dnp','locked_owner','locked_line','group','partial_body','fab_angle',
    'unknown_setting','unknown_tags'])
def test_no_physical_functional_or_unknown_metadata_is_covered(tmp_path,fault):
    source,table,uid=fixture(tmp_path)
    if fault in('unknown_setting','unknown_tags'):
        text=source.read_text()
        if fault=='unknown_setting':text=text.replace('(duplicate_pad_numbers_are_jumpers no)',
            '(duplicate_pad_numbers_are_jumpers yes)',1)
        else:text=text.replace('(tags "resistor")','(tags "resistor unreviewed")',1)
        source.write_text(text)
    else:
        board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()));pad=fp.FindPadByNumber('1')
        if fault=='pad':pad.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='drill':
            # A drill on an SMD pad is discarded by native serialization.
            # Author an actual drilled-pad mutation so the saved Source is
            # representable and the body-role receiver must reject it.
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetLayerSet(pcbnew.PAD.PTHMask())
            pad.SetDrillSize(pcbnew.VECTOR2I(400000,400000))
        elif fault=='mask':pad.SetLocalSolderMaskMargin(1)
        elif fault=='mpn':fp.SetField('MPN','not-selected')
        elif fault=='nearby_mpn':fp.SetField('MPN','CSS2H-2512R-L300F')
        elif fault=='value':fp.SetValue('0.5Ω')
        elif fault=='dnp':fp.SetDNP(True)
        elif fault=='locked_owner':fp.SetLocked(True)
        elif fault=='group':
            group=pcbnew.PCB_GROUP(board);group.SetName('unowned');board.Add(group);group.AddItem(fp)
        elif fault=='model':
            model=pcbnew.FP_3DMODEL();model.m_Filename='unknown.step';fp.Models().push_back(model)
        elif fault=='unknown_mark':
            shape=pcbnew.PCB_SHAPE(fp);shape.SetShape(pcbnew.SHAPE_T_SEGMENT);shape.SetLayer(pcbnew.F_SilkS)
            shape.SetStart(pcbnew.VECTOR2I_MM(0,0));shape.SetEnd(pcbnew.VECTOR2I_MM(1,0));shape.SetWidth(120000);fp.Add(shape)
        else:
            if fault=='courtyard':g=next(g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_CrtYd)
            elif fault in('fab','fab_angle'):
                g=next(g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_Fab
                    and (fault!='fab_angle'or g.GetClass()=='PCB_TEXT'))
            else:g=next(g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_SilkS)
            if fault=='fab_angle':g.SetTextAngle(pcbnew.EDA_ANGLE(13,pcbnew.DEGREES_T))
            elif fault=='locked_line':g.SetLocked(True)
            elif fault=='partial_body':body.ink.discard_footprint_children(board,fp,[g])
            else:g.Move(pcbnew.VECTOR2I(1,0))
        field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):inspect(source,table,uid,allow_already_omitted=True)


@pytest.mark.parametrize('fault',['original','predecessor','drawing','copy'])
def test_all_independent_registered_inputs_are_live_not_prior_receipt_authority(tmp_path,monkeypatch,fault):
    source,table,uid=fixture(tmp_path);proof=inspect(source,table,uid)
    targets={'original':Path(proof['canonical_template']),
        'predecessor':body.ROOT/'lib/vendor/Resistor_SMD.pretty/R_2512_6332Metric.kicad_mod',
        'drawing':body.ROOT/'lib/datasheets/Bourns_CSS2H-2512.pdf','copy':Path(proof['template'])}
    changed=targets[fault].resolve();original=force._hash
    monkeypatch.setattr(force,'_hash',lambda p:'0'*64 if Path(p).resolve()==changed else original(p))
    with pytest.raises(ValueError):body.expected_omission(source,proof)


@pytest.mark.parametrize('fault',['body_uuid','role','canonical','drawing','authority'])
def test_worker_cannot_expand_role_or_use_serialized_success_as_authority(tmp_path,fault):
    source,table,uid=fixture(tmp_path)
    q=printing.plan(source,library_table=table,footprint_ids=[FPID],expected_instance_uuids=[uid],
        board_hint='synthetic',optional_body_footprint_ids=[FPID]);q=copy.deepcopy(q)
    proof=q['records'][0]['source_optional_body_contract']
    if fault=='body_uuid':q['records'][0]['graphic_uuids'].append('unknown-child')
    elif fault=='role':proof['policy']=body.POLICY
    elif fault=='canonical':proof['canonical_template']=proof['template']
    elif fault=='drawing':proof['template_input_sha256'][str(body.ROOT/'lib/datasheets/Bourns_CSS2H-2512.pdf')]='0'*64
    else:proof['physical_change_authority']=True
    with pytest.raises(ValueError):printing.construct_private(source,q,tmp_path/'private')


@pytest.mark.parametrize('fault',['pad','fab','metadata','reference','template','extra_file'])
def test_saved_receiver_rejects_unowned_child_and_library_changes(tmp_path,fault):
    source,table,uid=fixture(tmp_path)
    q=printing.plan(source,library_table=table,footprint_ids=[FPID],expected_instance_uuids=[uid],
        board_hint='synthetic',optional_body_footprint_ids=[FPID])
    artifact=printing.construct_private(source,q,tmp_path/'private');child=Path(artifact['candidate'])
    if fault=='template':
        library=Path(artifact['new_library_context']['rows']['cec-Resistor_SMD']['path'])/(ITEM+'.kicad_mod')
        library.write_text(library.read_text()+'\n# unowned\n')
    elif fault=='extra_file':(child.parent/'unowned').write_text('unowned')
    elif fault=='metadata':child.write_text(child.read_text().replace('(tags "resistor")','(tags "different")',1))
    else:
        board=pcbnew.LoadBoard(str(child));fp=next(iter(board.GetFootprints()))
        if fault=='pad':fp.FindPadByNumber('1').Move(pcbnew.VECTOR2I(1,0))
        elif fault=='reference':fp.SetReference('not-source')
        else:next(g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_Fab).Move(pcbnew.VECTOR2I(1,0))
        field._save_field_snapshot(board,child)
    result=printing.receive_staged(source,child,q)
    assert result['ok']is False and result['complete']is False


def test_missing_source_mpn_does_not_inherit_role_from_filename_or_template(tmp_path):
    source,table,uid=fixture(tmp_path,origin='canonical',copied=False)
    original=pcbnew.FootprintLoad(str(body.ROOT/'lib/vendor/Resistor_SMD.pretty'),ITEM)
    assert not original.HasField('MPN')
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()));fp.SetField('MPN','')
    field._save_field_snapshot(board,source)
    with pytest.raises(ValueError):inspect(source,table,uid)
