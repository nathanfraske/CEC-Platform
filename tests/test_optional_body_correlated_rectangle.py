"""Separately ratified complete rectangular body, not a duplicate tolerance."""
import copy

import pcbnew
import pytest
import cec_optional_body_ink_contract as op
from test_optional_body_ink_contract import fixture as original_fixture,inspect

NAME='XFCN_T34069_THT_M3_40A'


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_exact_correlated_body_saved_omission_and_continuation(tmp_path,turn,back):
    source,table,uid=original_fixture(tmp_path,turn,back,name=NAME);original=source.read_bytes()
    proof=inspect(source,table,uid)
    assert proof['policy']==op.CORRELATED_POLICY
    assert len(proof['graphic_uuids'])==4 and proof['preserved_nonoptional_silk_count']==0
    expected=op.expected_omission(source,proof);child=tmp_path/'private.kicad_pcb';child.write_text(expected)
    assert op.receive_literal(source,child,proof)['ok']
    # All other root/owner text, Fab datum, reference text, court, pads and
    # opaque historical Source fields remain literally identical by receiver.
    assert 'DB DATUM: SAMPLE'in expected and '${REFERENCE}'in expected
    assert source.read_bytes()==original
    again=op.inspect(child,library_table=table,footprint_uuid=uid,
        expected_source_sha256=op.force._hash(child),allow_already_omitted=True)
    assert again['graphic_uuids']==[] and again['source_optional_body_state']=='already_omitted_approved_body'
    assert op.expected_omission(child,again)==expected


def native_template():
    path=op.ROOT/'lib/vendor/Connector_Screw.pretty'/ (NAME+'.kicad_mod')
    fp=pcbnew.FootprintLoad(str(path.parent),path.stem)
    silk=[g for g in fp.GraphicalItems()if g.GetLayer()==pcbnew.F_SilkS]
    return fp,silk,[(-3125000,-3150000),(5875000,-3150000),(5875000,3150000),(-3125000,3150000)]


@pytest.mark.parametrize('fault',['missing','duplicate','diagonal','open_corner_1nm','unequal_width_1nm',
    'shift_center_1nm','inward','half_stroke','beyond_half_stroke_1nm','extra_key'])
def test_integer_positive_cycle_and_strict_stroke_correlation_reject_forgery(fault):
    fp,silk,fab=native_template()
    if fault=='missing':silk=silk[:-1]
    elif fault=='duplicate':silk[-1]=silk[0]
    elif fault=='diagonal':silk[0].SetEnd(silk[0].GetEnd()+pcbnew.VECTOR2I(1,1))
    elif fault=='open_corner_1nm':silk[0].SetStart(silk[0].GetStart()+pcbnew.VECTOR2I(1,0))
    elif fault=='unequal_width_1nm':silk[0].SetWidth(silk[0].GetWidth()+1)
    elif fault=='shift_center_1nm':
        for line in silk:line.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='extra_key':silk.append(silk[0])
    else:
        # Rebuild a closed symmetric rectangle: topology/center alone are
        # insufficient; correspondence must still be outward and strict.
        delta={'inward':-1,'half_stroke':100000,'beyond_half_stroke_1nm':100001}[fault]
        x0,x1=-3125000-delta,5875000+delta
        points=[(x0,-3150000),(x1,-3150000),(x1,3150000),(x0,3150000)]
        for i,line in enumerate(silk):
            line.SetStart(pcbnew.VECTOR2I(*points[i]));line.SetEnd(pcbnew.VECTOR2I(*points[(i+1)%4]))
    with pytest.raises(ValueError):op._correlated_rectangle_lines(silk,fab)


@pytest.mark.parametrize('fault',['pad_1nm','fab_1nm','silk_1nm','court_1nm','extra_mark',
    'locked_owner','locked_stroke','grouped_owner','unknown_root_setting','wrong_mpn'])
def test_source_must_remain_exact_original_manufacturer_body(tmp_path,fault):
    source,table,uid=original_fixture(tmp_path,name=NAME)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    if fault=='pad_1nm':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='locked_owner':fp.SetLocked(True)
    elif fault=='wrong_mpn':fp.GetField('MPN').SetText('unknown')
    elif fault=='grouped_owner':
        group=pcbnew.PCB_GROUP(board);group.SetName('not-annotation-authority');board.Add(group);group.AddItem(fp)
    elif fault=='extra_mark':
        shape=pcbnew.PCB_SHAPE(fp);shape.SetShape(pcbnew.SHAPE_T_SEGMENT);shape.SetLayer(pcbnew.F_SilkS)
        shape.SetStart(pcbnew.VECTOR2I_MM(20,20));shape.SetEnd(pcbnew.VECTOR2I_MM(21,20));shape.SetWidth(200000);fp.Add(shape)
    elif fault=='unknown_root_setting':
        # A real physical setting, not a Source field with instance metadata.
        fp.SetLocalClearance(1)
    else:
        layer={'fab_1nm':pcbnew.F_Fab,'court_1nm':pcbnew.F_CrtYd}.get(fault,pcbnew.F_SilkS)
        shape=next(g for g in fp.GraphicalItems()if g.GetLayer()==layer and hasattr(g,'GetShape'))
        if fault=='locked_stroke':shape.SetLocked(True)
        else:shape.Move(pcbnew.VECTOR2I(1,0))
    pcbnew.SaveBoard(str(source),board)
    with pytest.raises(ValueError):inspect(source,table,uid)


def test_template_geometry_does_not_bypass_hash_or_borrow_functional_roles(tmp_path):
    source,table,uid=original_fixture(tmp_path,name=NAME);proof=inspect(source,table,uid)
    forged=copy.deepcopy(proof);forged['template_sha256']='0'*64
    with pytest.raises(ValueError,match='contract_changed'):op.expected_omission(source,forged)
    derivative=op.template_omission(proof['template'])
    assert len(derivative['graphic_ids'])==4 and derivative['preserved_functional_silk_lines']==0
    # Existing TTR path remains exact-duplicate (3 lines), never the new
    # offset-correlation policy or a whole-template/body replacement.
    ttr=op.ROOT/'lib/vendor/Connector_Screw.pretty/XFCN_TTR32100127-0600_THT_M3_60A.kicad_mod'
    assert len(op.template_omission(ttr)['graphic_ids'])==3


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_original_fab_labels_keep_exact_cardinal_instance_reading_angles(tmp_path,turn,back):
    source,table,uid=original_fixture(tmp_path,turn,back,name=NAME)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    face=pcbnew.B_Fab if back else pcbnew.F_Fab
    labels=[g for g in fp.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetLayer()==face]
    assert len(labels)==2
    for i,label in enumerate(labels):label.SetTextAngle(pcbnew.EDA_ANGLE(i*90,pcbnew.DEGREES_T))
    pcbnew.SaveBoard(str(source),board);original=source.read_bytes();proof=inspect(source,table,uid)
    candidate=tmp_path/'private.kicad_pcb';candidate.write_text(op.expected_omission(source,proof))
    assert op.receive_literal(source,candidate,proof)['ok']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['font_1nm','position_1nm','text','noncardinal_angle','duplicate'])
def test_fab_reading_angle_scope_never_accepts_other_label_changes(tmp_path,fault):
    source,table,uid=original_fixture(tmp_path,name=NAME)
    board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    label=next(g for g in fp.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetLayer()==pcbnew.F_Fab)
    if fault=='font_1nm':label.SetTextSize(label.GetTextSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='position_1nm':label.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='text':label.SetText('other datum')
    elif fault=='noncardinal_angle':label.SetTextAngle(pcbnew.EDA_ANGLE(45,pcbnew.DEGREES_T))
    else:fp.Add(pcbnew.PCB_TEXT(label))
    pcbnew.SaveBoard(str(source),board)
    with pytest.raises(ValueError):inspect(source,table,uid)
