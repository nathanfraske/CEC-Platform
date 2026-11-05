"""Synthetic caption scope tests; discovery stubs are not real native DRC."""
import copy
import json

import pcbnew
import pytest
from shapely.geometry import box
import cec_root_caption_seating as op
from test_dense_reference_mapping import fixture as reference_fixture


def refresh(source,grade,uid):
    g=json.loads(grade.read_text());p=g['boards']['candidate']['native_producer']
    report=op.Path(p['report']);op.force._write(report,dict(violations=[dict(
        type='silk_over_copper',severity='warning',items=[dict(uuid=uid)])],unconnected_items=[]))
    p['report_sha256']=op.force._hash(report);p['source_files']={str(source):op.force._hash(source)}
    g['boards']['candidate']['sha256']=op.force._hash(source)
    g['code_identity']=op.force._code_identity();op.force._write(grade,g)


def fixture(tmp_path,back=False,angle=0,text='Arbitrary caption 739'):
    source,grade,_=reference_fixture(tmp_path,roomy=True,back=back)
    board=pcbnew.LoadBoard(str(source));caption=pcbnew.PCB_TEXT(board)
    caption.SetText(text);caption.SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    caption.SetMirrored(back);caption.SetTextSize(pcbnew.VECTOR2I_MM(1,1))
    caption.SetTextThickness(150000);caption.SetTextPos(pcbnew.VECTOR2I_MM(40,40))
    caption.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T));board.Add(caption)
    op.seats.field._save_field_snapshot(board,source);uid=op.force._uid(caption);refresh(source,grade,uid)
    args=dict(grade=grade,board_hint='explicit_synthetic_legend',caption_uuid=uid,
        expected_text=text,caption_scope=op.POLICY)
    return source,grade,args


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,37,90,180])
def test_arbitrary_caption_translation_preserves_style_raw_source_and_two_saves(tmp_path,back,angle):
    source,_,args=fixture(tmp_path,back,angle);original=source.read_bytes()
    p=op.plan(source,**args);child=op.force._copy_family(source,tmp_path/'child')
    op.write_private(source,child,json.loads(json.dumps(p)))
    result=op.receive(source,child,p);assert result['ok']and result['complete'],result
    assert source.read_bytes()==original
    old=pcbnew.LoadBoard(str(source));new=pcbnew.LoadBoard(str(child))
    a=next(i for i in old.GetDrawings()if op.force._uid(i)==args['caption_uuid'])
    b=next(i for i in new.GetDrawings()if op.force._uid(i)==args['caption_uuid'])
    assert tuple(a.GetPosition())!=tuple(b.GetPosition())
    assert a.GetText()==b.GetText()and a.GetTextAngle().AsDegrees()==b.GetTextAngle().AsDegrees()
    assert tuple(a.GetTextSize())==tuple(b.GetTextSize())and a.GetTextThickness()==b.GetTextThickness()
    assert a.GetLayer()==b.GetLayer()and a.IsMirrored()==b.IsMirrored()
    assert p['semantic_scope_is_external_review_not_auto_classification']
    assert not result['release_authority']


@pytest.mark.parametrize('fault',['wrong_uuid','wrong_text','scope','locked','grouped','hidden',
    'grade','report','no_finding','unknown_body','font_floor'])
def test_scope_and_live_source_eligibility_fail_closed(tmp_path,fault,monkeypatch):
    source,grade,args=fixture(tmp_path)
    if fault=='wrong_uuid':args['caption_uuid']='not-the-caption'
    elif fault=='wrong_text':args['expected_text']='not-the-caption'
    elif fault=='scope':args['caption_scope']='automatic_nonfunctional_text'
    elif fault=='grade':g=json.loads(grade.read_text());g['code_identity']={};op.force._write(grade,g)
    elif fault=='report':op.Path(json.loads(grade.read_text())['boards']['candidate']['native_producer']['report']).write_text('{}')
    elif fault=='no_finding':
        refresh(source,grade,'unrelated-uuid')
    else:
        b=pcbnew.LoadBoard(str(source));t=next(i for i in b.GetDrawings()if op.force._uid(i)==args['caption_uuid'])
        if fault=='locked':t.SetLocked(True)
        elif fault=='hidden':t.SetVisible(False)
        elif fault=='font_floor':t.SetTextThickness(1000)
        elif fault=='grouped':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
        else:
            fp=next(iter(b.GetFootprints()))
            for i in list(fp.GraphicalItems()):
                if i.GetLayer()in(pcbnew.F_CrtYd,pcbnew.B_CrtYd):fp.Remove(i)
        op.seats.field._save_field_snapshot(b,source);refresh(source,grade,args['caption_uuid'])
        if fault=='hidden':
            # Root gr_text visibility is not serialized by KiCad. Exercise
            # the native predicate directly, without claiming a saved hide.
            original=op.seats.dense.source_context
            def hidden(*a,**k):
                context=original(*a,**k)
                next(i for i in context[0].GetDrawings()if op.force._uid(i)==args['caption_uuid']).SetVisible(False)
                return context
            monkeypatch.setattr(op.seats.dense,'source_context',hidden)
    with pytest.raises(ValueError):op.plan(source,**args)


@pytest.mark.parametrize('fault',['position','content','font','layer','mirror','angle','other_geometry','sidecar'])
def test_candidate_may_change_only_exact_root_xy_tokens(tmp_path,fault):
    source,_,args=fixture(tmp_path);p=op.plan(source,**args)
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,p)
    b=pcbnew.LoadBoard(str(child));t=next(i for i in b.GetDrawings()if op.force._uid(i)==args['caption_uuid'])
    if fault=='position':t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='content':t.SetText('changed')
    elif fault=='font':t.SetTextThickness(160000)
    elif fault=='layer':t.SetLayer(pcbnew.F_Fab)
    elif fault=='mirror':t.SetMirrored(True)
    elif fault=='angle':t.SetTextAngle(pcbnew.EDA_ANGLE(23,pcbnew.DEGREES_T))
    elif fault=='other_geometry':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    else:op.force._write(child.with_suffix('.kicad_pro'),{})
    if fault!='sidecar':op.seats.field._save_field_snapshot(b,child)
    assert not op.receive(source,child,p)['ok']


@pytest.mark.parametrize('fault',['position','request','dependency','binding','text'])
def test_serialized_plan_is_not_authority(tmp_path,fault):
    source,_,args=fixture(tmp_path);p=op.plan(source,**args);q=copy.deepcopy(p)
    if fault=='position':q['at_nm'][0]+=1
    elif fault=='request':q['request']['caption_scope']='other'
    elif fault=='dependency':q['dependencies'][next(iter(q['dependencies']))]='0'*64
    elif fault=='binding':q['binding']['source_sha256']='0'*64
    else:q['expected_text']='forged'
    with pytest.raises(ValueError):op.construct(source,q)


@pytest.mark.parametrize('extra',[dict(timeout_s=11),dict(maximum_candidates=0),dict(step_mm=.01),
    dict(max_translation_mm=11),dict(max_translation_mm=10,step_mm=.1),
    dict(reviewed_courtyard_contract_ids=['a','a'])])
def test_finite_work_limits(tmp_path,extra):
    source,_,args=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(source,**args,**extra)


def test_mask_artwork_is_hard_obstacle_and_failure_does_not_mutate(tmp_path,monkeypatch):
    source,_,args=fixture(tmp_path);before=source.read_bytes()
    monkeypatch.setattr(op.seats.masks,'native_mask_artwork',lambda b,f:(box(-100,-100,100,100),{}))
    with pytest.raises(ValueError,match='no_readable_clear_source_caption_seat'):op.plan(source,**args)
    assert source.read_bytes()==before


def test_source_change_invalidates_native_finding_binding(tmp_path):
    source,_,args=fixture(tmp_path);p=op.plan(source,**args)
    b=pcbnew.LoadBoard(str(source));next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    op.seats.field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.construct(source,p)


def test_footprint_field_cannot_become_root_caption_by_declaring_text(tmp_path):
    source,grade,args=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));ref=next(iter(b.GetFootprints())).Reference()
    args.update(caption_uuid=op.force._uid(ref),expected_text=ref.GetText())
    refresh(source,grade,args['caption_uuid'])
    with pytest.raises(ValueError,match='root_caption'):op.plan(source,**args)


def test_opaque_unowned_caption_metadata_remains_literal(tmp_path):
    source,_,args=fixture(tmp_path);before=source.read_text()
    a,z=op._root_text(before,args['caption_uuid'])
    opaque=before[:z-1]+' (future_caption_metadata "KEEP")'+before[z-1:]
    moved=op._translated(opaque,args['caption_uuid'],[39000000,40000000])
    assert '(future_caption_metadata "KEEP")'in moved
    old_node=opaque[a:op._root_text(opaque,args['caption_uuid'])[1]]
    new_node=moved[a:op._root_text(moved,args['caption_uuid'])[1]]
    assert old_node.replace('(at 40 40','(at 39 40')==new_node
