"""Own-face reference positioning preserves source identity and factory gates."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest
from shapely.geometry import box
import cec_additive_route_receiving as ast
import cec_field_coupling as field
import cec_force_current as force
import cec_reference_field_seating as seats
import cec_source_retaining_ses_import as raw
from test_dense_reference_mapping import fixture


def prepared(tmp_path,**kwargs):
    source,grade,uid=fixture(tmp_path,roomy=True,**kwargs)
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',maximum_components=1)
    child=force._copy_family(source,tmp_path/'seated')
    seats.write_private(source,child,json.loads(json.dumps(q)))
    return source,child,q,uid,grade


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_reference_stays_visible_readable_and_owner_local_through_native_receiving(tmp_path,quarter,back):
    source,child,q,uid,_=prepared(tmp_path,quarter=quarter,back=back)
    digest=force._hash(source);r=seats.receive(source,child,q)
    assert r['ok']and r['complete'],r
    parent,board=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    fp=next(fp for fp in board.GetFootprints()if force._uid(fp)==uid);ref=fp.Reference()
    assert ref.IsVisible()and ref.GetLayer()==(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    assert ref.IsMirrored()is back and ref.GetText()=='Z77'
    assert ref.GetTextSize().x>=q['binding']['factory_legend']['height']*1e6
    assert ref.GetTextThickness()>=q['binding']['factory_legend']['stroke']*1e6
    assert not list(board.Groups())and len(list(board.GetDrawings()))==len(list(parent.GetDrawings()))
    assert fp.GetValue()=='UNCHANGED-TEST-VALUE'and fp.GetField('MPN').GetText()=='UNCHANGED-TEST-MPN'
    assert digest==force._hash(source)and not r['release_authority']
    old,new=ast._nodes(source)[1],ast._nodes(child)[1]
    assert old.keys()==new.keys()and all(old[u]==new[u]for u in old if u!=uid)


@pytest.mark.parametrize('fault',['pad','pose','value','reference','visibility','field_position','field_font','new_copper','sidecar'])
def test_every_unowned_or_forged_candidate_change_is_refused(tmp_path,fault):
    source,child,q,uid,_=prepared(tmp_path);board=pcbnew.LoadBoard(str(child))
    fp=next(fp for fp in board.GetFootprints()if force._uid(fp)==uid)
    if fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='value':fp.SetValue('WRONG')
    elif fault=='reference':fp.SetReference('WRONG')
    elif fault=='visibility':fp.Reference().SetVisible(False)
    elif fault=='field_position':fp.Reference().Move(pcbnew.VECTOR2I(1,0))
    elif fault=='field_font':fp.Reference().SetTextThickness(10000)
    elif fault=='new_copper':
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(1,1));t.SetEnd(pcbnew.VECTOR2I_MM(2,1));t.SetWidth(200000);board.Add(t)
    field._save_field_snapshot(board,child)
    if fault=='sidecar':force._write(child.with_suffix('.kicad_pro'),{})
    proof=seats.receive(source,child,q)
    assert not proof['ok']and proof['errors']


@pytest.mark.parametrize('fault',['position','angle','font','reference','field_uuid','source_hash','dependency','request'])
def test_json_plan_does_not_grant_annotation_authority(tmp_path,fault):
    source,child,q,_,_=prepared(tmp_path);bad=copy.deepcopy(q)
    if fault=='position':bad['records'][0]['at_nm'][0]+=1
    elif fault=='angle':bad['records'][0]['angle_degrees']=45
    elif fault=='font':bad['records'][0]['size_nm']=[200000,200000]
    elif fault=='reference':bad['records'][0]['reference']='FORGED'
    elif fault=='field_uuid':bad['records'][0]['reference_field_uuid']='FORGED'
    elif fault=='source_hash':bad['binding']['source_sha256']='0'*64
    elif fault=='dependency':bad['dependencies'][next(iter(bad['dependencies']))]='0'*64
    else:bad['request']['max_gap_mm']=3.
    with pytest.raises(ValueError):
        seats.construct(source,bad)


@pytest.mark.parametrize('kwargs',[dict(maximum_components=0),dict(maximum_components=17),
    dict(seed_index=-1),dict(seed_index=128),dict(timeout_s=11),dict(max_gap_mm=3),
    dict(owner_uuid_scope=['a','a']),dict(owner_uuid_scope=[''])])
def test_explicit_finite_source_scope_is_required(tmp_path,kwargs):
    source,grade,_=fixture(tmp_path,roomy=True)
    with pytest.raises(ValueError,match='bounded'):
        seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',**kwargs)


def test_exact_owner_scope_only_narrows_actual_reported_reference_fields(tmp_path):
    source,grade,uid=fixture(tmp_path,roomy=True)
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',owner_uuid_scope=[uid])
    assert [r['footprint_uuid']for r in q['records']]==[uid]
    with pytest.raises(ValueError,match='not_reported_eligible'):
        seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',owner_uuid_scope=['unreported'])


def test_mask_artwork_or_ambiguous_owner_cannot_be_treated_as_empty_space(tmp_path,monkeypatch):
    source,grade,_=fixture(tmp_path,roomy=True)
    monkeypatch.setattr(seats.masks,'native_mask_artwork',lambda b,f:(box(0,0,60,60),{}))
    with pytest.raises(ValueError,match='no_readable_clear'):
        seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend')


@pytest.mark.parametrize('fault',['hidden','locked','grouped','grade_epoch','empty_faults'])
def test_no_reference_can_be_repositioned_without_live_eligibility(tmp_path,fault):
    source,grade,_=fixture(tmp_path,roomy=True);board=pcbnew.LoadBoard(str(source));fp=next(iter(board.GetFootprints()))
    if fault=='hidden':fp.Reference().SetVisible(False)
    elif fault=='locked':fp.SetLocked(True)
    elif fault=='grouped':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(fp)
    if fault in('hidden','locked','grouped'):
        field._save_field_snapshot(board,source)
        report=grade.parent/'source-native.json';g=json.loads(grade.read_text());g['boards']['candidate']['sha256']=force._hash(source)
        g['boards']['candidate']['native_producer']['source_files']={str(source):force._hash(source)};force._write(grade,g)
    elif fault=='grade_epoch':g=json.loads(grade.read_text());g['code_identity']={};force._write(grade,g)
    else:
        report=grade.parent/'source-native.json';r=json.loads(report.read_text());r['violations']=[];force._write(report,r)
        g=json.loads(grade.read_text());g['boards']['candidate']['native_producer']['report_sha256']=force._hash(report);force._write(grade,g)
    with pytest.raises(ValueError):seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend')


def test_unknown_effect_metadata_cannot_disappear_in_an_annotation_edit(tmp_path):
    source,grade,uid=fixture(tmp_path,roomy=True)
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend')
    text=source.read_text();a,z=raw.inventory(text)[uid];node=copy.deepcopy(ast._nodes(source)[1][uid])
    prop=next(c for c in node if isinstance(c,list)and c[:2]==['property','"Reference"'])
    next(c for c in prop if isinstance(c,list)and c and c[0]=='effects').append(['future_text_metadata','KEEP'])
    dirty=text[:a]+ast._render(node)+text[z:]
    with pytest.raises(ValueError,match='opaque_reference_effects'):
        seats._literal(dirty,text,q)
    assert source.read_text()==text


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_source_keep_upright_false_is_literal_and_second_roundtrip_immutable(tmp_path,quarter,back):
    source,grade,uid=fixture(tmp_path,roomy=True,quarter=quarter,back=back)
    board=pcbnew.LoadBoard(str(source));owner=next(f for f in board.GetFootprints()if force._uid(f)==uid)
    owner.Reference().SetKeepUpright(False);field._save_field_snapshot(board,source)
    # Refresh only deliberately synthetic discovery binding after this known
    # source edit. This is not a relabelled physical/native grade.
    g=json.loads(grade.read_text());g['boards']['candidate']['sha256']=force._hash(source)
    g['boards']['candidate']['native_producer']['source_files']={str(source):force._hash(source)}
    force._write(grade,g);original=source.read_bytes()
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',maximum_components=1)
    child=force._copy_family(source,tmp_path/'source-upright-false')
    seats.write_private(source,child,q)
    proof=seats.receive(source,child,q)
    assert proof['ok']and proof['complete'],proof
    assert proof['whole_saved_second_native_roundtrip_stable']
    def reference_node(path):
        fpnode=ast._nodes(path)[1][uid]
        return next(n for n in fpnode if isinstance(n,list)and n[:2]==['property','"Reference"'])
    assert ['unlocked','yes']in reference_node(source)
    assert ['unlocked','yes']in reference_node(child)
    paths=[child]
    for index in(1,2):
        saved=tmp_path/('upright-false-save-'+str(index)+'.kicad_pcb')
        field._save_field_snapshot(pcbnew.LoadBoard(str(paths[-1])),saved);paths.append(saved)
    record=q['records'][0]
    for path in paths:
        fp=next(f for f in pcbnew.LoadBoard(str(path)).GetFootprints()if force._uid(f)==uid);ref=fp.Reference()
        assert ref.IsKeepUpright()is False and ref.IsVisible()
        assert ref.IsMirrored()is back
        assert ref.GetTextAngleDegrees()==record['angle_degrees']and record['angle_degrees']in(0,90)
        assert ref.GetDrawRotation().AsDegrees()%360 in(0,90)
        assert ['unlocked','yes']in reference_node(path)
        assert ref.GetTextSize().y>=q['binding']['factory_legend']['height']*1e6
        assert ref.GetTextThickness()>=q['binding']['factory_legend']['stroke']*1e6
    assert source.read_bytes()==original


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90])
def test_pinned_native_readable_angle_does_not_require_changing_source_keep_upright(tmp_path,quarter,back,angle):
    source,_,uid=fixture(tmp_path,roomy=True,quarter=quarter,back=back)
    board=pcbnew.LoadBoard(str(source));fp=next(f for f in board.GetFootprints()if force._uid(f)==uid)
    ref=fp.Reference();ref.SetKeepUpright(False)
    seats._stamp(ref,dict(at_nm=list(ref.GetPosition()),angle_degrees=angle,
        size_nm=[1000000,1000000],stroke_nm=150000,layer_id=pcbnew.B_SilkS if back else pcbnew.F_SilkS))
    assert ref.IsKeepUpright()is False
    assert ref.GetTextAngleDegrees()==angle
    assert ref.GetDrawRotation().AsDegrees()%360==angle
    assert ref.IsMirrored()is back


def test_second_native_save_reloads_the_first_saved_output(tmp_path,monkeypatch):
    source,child,q,_,_=prepared(tmp_path)
    original=field._save_field_snapshot;saves=[]
    def tracked(board,path,*args,**kwargs):
        saves.append((Path(board.GetFileName()),Path(path)))
        return original(board,path,*args,**kwargs)
    monkeypatch.setattr(field,'_save_field_snapshot',tracked)
    proof=seats.receive(source,child,q)
    assert proof['ok'],proof
    chain=[(i,o)for i,o in saves if o.parent.name.startswith('cec-reference-field-receiving-')and o.name in('first.kicad_pcb','second.kicad_pcb')]
    assert len(chain)==2 and chain[0][0]==child and chain[1][0]==chain[0][1]


def test_native_mask_bore_geometry_dependency_is_bound_and_rechecked(tmp_path,monkeypatch):
    source,child,q,_,_=prepared(tmp_path)
    authority=str(Path(seats.ink.__file__).resolve())
    assert authority in q['dependencies']
    original=seats.dependencies
    monkeypatch.setattr(seats,'dependencies',lambda:dict(original(),**{authority:'0'*64}))
    with pytest.raises(ValueError,match='stale_or_forged'):
        seats.construct(source,q)
