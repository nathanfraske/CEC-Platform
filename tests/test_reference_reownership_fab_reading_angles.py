"""Fab reading presentation is not permission to ignore package content."""
import copy
from pathlib import Path

import pcbnew
import pytest
import cec_reference_map_reownership as op
import cec_field_coupling as field
import cec_force_current as force
from test_reference_map_reownership import fixture,proposal


def tree(label='LED FACES DOWN'):
    return ['footprint','"package"', ['layer','"F.Cu"'],['at','0','0'],
        ['attr','smd'],['duplicate_pad_numbers_are_jumpers','no'],
        ['fp_text','user','"'+label+'"',['at','0','0','0'],['layer','"F.Fab"'],
            ['effects',['font',['size','.55','.55'],['thickness','.09']]]],
        ['fp_rect',['start','-1','-2'],['end','1','2'],['layer','"F.CrtYd"']],
        ['pad','"1"','smd','rect',['at','1','0'],['size','1','1'],
            ['layers','"F.Cu"','"F.Mask"','"F.Paste"']],
        ['model','"actual.step"',['scale',['xyz','1','1','1']]]]


def label_node(node):
    return next(n for n in node if isinstance(n,list) and n[:2]==['fp_text','user'])


@pytest.mark.parametrize('angle',['0','90','180','270','-90'])
@pytest.mark.parametrize('literal',['LED FACES DOWN','${REFERENCE}','PIN ONE'])
def test_only_unique_same_literal_cardinal_reading_angle_projects(angle,literal):
    template=tree(literal);actual=copy.deepcopy(template)
    next(n for n in label_node(actual) if isinstance(n,list) and n[:1]==['at'])[3]=angle
    before=copy.deepcopy(actual)
    assert op._body_tree_key(actual,set())==op._body_tree_key(template,set())
    assert actual==before


@pytest.mark.parametrize('fault',['position','font','text','size','stroke','layer','mirror',
    'visibility','locked','bold','italic','attribute','unknown_setting','unknown_attribute',
    'pad','court','model','functional_art','added_label','nonlabel_text'])
def test_complete_body_or_non_angle_text_difference_cannot_match(fault):
    original=tree();bad=copy.deepcopy(original);label=label_node(bad)
    effects=next(c for c in label if isinstance(c,list) and c[:1]==['effects'])
    font=next(c for c in effects if isinstance(c,list) and c[:1]==['font'])
    if fault=='position':next(c for c in label if isinstance(c,list) and c[:1]==['at'])[1]='.000001'
    elif fault=='font':font.append(['face','"Other Font"'])
    elif fault=='text':label[2]='"LED FACES UP"'
    elif fault=='size':next(c for c in font if isinstance(c,list) and c[:1]==['size'])[1]='.550001'
    elif fault=='stroke':next(c for c in font if isinstance(c,list) and c[:1]==['thickness'])[1]='.090001'
    elif fault=='layer':next(c for c in label if isinstance(c,list) and c[:1]==['layer'])[1]='"B.Fab"'
    elif fault=='mirror':effects.append(['justify','mirror'])
    elif fault=='visibility':label.append(['hide','yes'])
    elif fault=='locked':label.append(['locked','yes'])
    elif fault in ('bold','italic'):font.append(fault)
    elif fault=='attribute':next(c for c in bad if isinstance(c,list) and c[:1]==['attr']).append('exclude_from_bom')
    elif fault=='unknown_setting':bad.append(['future_native_physical_setting','42'])
    elif fault=='unknown_attribute':label.append(['future_native_text_attribute','42'])
    elif fault=='pad':next(c for c in bad if isinstance(c,list) and c[:1]==['pad']).append(['solder_mask_margin','.01'])
    elif fault=='court':next(c for c in bad if isinstance(c,list) and c[:1]==['fp_rect'])[1][1]='-1.1'
    elif fault=='model':next(c for c in bad if isinstance(c,list) and c[:1]==['model'])[1]='"other.step"'
    elif fault=='functional_art':bad.append(['fp_circle',['center','0','0'],['end','1','0'],['layer','"F.SilkS"']])
    elif fault=='added_label':
        extra=copy.deepcopy(label);extra[2]='"SECOND INSTRUCTION"';bad.append(extra)
    else:label[1]='value'
    assert op._body_tree_key(bad,set())!=op._body_tree_key(original,set())


@pytest.mark.parametrize('fault',['noncardinal','nan','duplicate','duplicate_at','missing_at'])
def test_ambiguous_or_noncardinal_fab_label_inventory_refuses(fault):
    bad=tree();label=label_node(bad);at=next(c for c in label if isinstance(c,list) and c[:1]==['at'])
    if fault=='noncardinal':at[3]='45'
    elif fault=='nan':at[3]='nan'
    elif fault=='duplicate':bad.append(copy.deepcopy(label))
    elif fault=='duplicate_at':label.append(copy.deepcopy(at))
    else:label.remove(at)
    with pytest.raises(ValueError):op._body_tree_key(bad,set())


@pytest.mark.parametrize('attribute',['net','uuid','pinfunction','pintype'])
def test_unknown_nested_physical_metadata_cannot_borrow_native_assignment_projection(attribute):
    original=tree();changed=copy.deepcopy(original)
    original.append(['future_physical_setting',[attribute,'original']])
    changed.append(['future_physical_setting',[attribute,'different']])
    assert op._body_tree_key(original,set())!=op._body_tree_key(changed,set())


def test_only_actual_pad_assignment_fields_are_projected():
    original=tree();changed=copy.deepcopy(original)
    for value,name in((original,'source'),(changed,'template')):
        pad=next(n for n in value if isinstance(n,list)and n[:1]==['pad'])
        pad.extend([['net',name],['pinfunction',name],['pintype',name],['uuid',name]])
    assert op._body_tree_key(original,set())==op._body_tree_key(changed,set())


@pytest.mark.parametrize('package',[('LED_SMD','LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount'),
    ('Capacitor_SMD','C_0603_1608Metric')],ids=['literal_instruction','reference_field'])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_template_both_faces_all_cardinal_poses_no_source_art_mutation(tmp_path,package,quarter,back):
    source,uid,_=fixture(tmp_path,quarter=quarter,back=back,reference='PART',package=package)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    fab=pcbnew.B_Fab if back else pcbnew.F_Fab
    texts=[g for g in fp.GraphicalItems() if g.GetClass()=='PCB_TEXT' and g.GetLayer()==fab]
    assert len(texts)==1
    texts[0].SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
    excluded={force._uid(g) for g in fp.GraphicalItems() if g.GetLayer()==(pcbnew.F_SilkS if back else pcbnew.B_SilkS)}
    before=field._field_snapshot_inventory(board);literal=source.read_bytes()
    directory=op.ROOT/'lib/vendor'/(package[0]+'.pretty');template=pcbnew.FootprintLoad(str(directory),package[1])
    assert op._body_key(fp,excluded)==op._body_key(template,set())
    assert before==field._field_snapshot_inventory(board) and source.read_bytes()==literal


def test_literal_unsupported_source_setting_is_not_lost_to_native_parser(tmp_path):
    source,_,_=fixture(tmp_path);board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    _,nodes=op.ast._nodes(source);literal=copy.deepcopy(nodes[force._uid(fp)])
    literal.append(['future_physical_setting','yes'])
    excluded={force._uid(g) for g in fp.GraphicalItems() if g.GetLayer()==pcbnew.B_SilkS}
    with pytest.raises(ValueError,match='literal_source_body_setting_not_received_by_native'):
        op._body_key(fp,excluded,source_node=literal)


def test_noncardinal_part_is_not_normalized_into_an_eligible_package(tmp_path):
    source,_,_=fixture(tmp_path);board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    fp.SetOrientationDegrees(45)
    with pytest.raises(ValueError,match='cardinal_manufacturer_body_pose'):
        op._body_key(fp,set())


def instruction_case(tmp_path):
    source,owner,table=fixture(tmp_path,quarter=1,reference='DL1',
        package=('LED_SMD','LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount'))
    b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    next(g for g in fp.GraphicalItems() if g.GetClass()=='PCB_TEXT' and g.GetLayer()==pcbnew.F_Fab).SetTextAngle(pcbnew.EDA_ANGLE(0,pcbnew.DEGREES_T))
    field._save_field_snapshot(b,source)
    return source,owner,table


def test_stock_saved_receiver_retains_entire_instruction_and_exact_world_map(tmp_path):
    source,owner,table=instruction_case(tmp_path);literal=source.read_bytes();q=proposal(source,owner,table)
    child=tmp_path/'private'/'board.kicad_pcb';op.construct(source,child,q)
    receiving=op.receive(source,child,q,board_hint='synthetic',timeout_s=9.1)
    assert receiving['ok'] and receiving['complete'],receiving
    before,after=[pcbnew.LoadBoard(str(p)) for p in (source,child)]
    labels=[next(g for fp in b.GetFootprints() for g in fp.GraphicalItems() if g.GetClass()=='PCB_TEXT' and g.GetText()=='LED FACES DOWN') for b in (before,after)]
    assert op._geometry(labels[0])==op._geometry(labels[1]) and source.read_bytes()==literal
    assert not receiving['native_drc_qualified'] and not receiving['release_authority']


@pytest.mark.parametrize('fault',['source','proposal'])
def test_same_literal_reading_projection_never_bypasses_fresh_source_or_proposal(tmp_path,fault):
    source,owner,table=instruction_case(tmp_path);q=proposal(source,owner,table)
    if fault=='source':source.write_text(source.read_text().replace('LED FACES DOWN','LED FACES UP'))
    else:q['expected_text']+=' '
    child=tmp_path/'forged'/'board.kicad_pcb'
    with pytest.raises(ValueError):op.construct(source,child,q)
    assert not child.exists()
