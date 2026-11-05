"""Readable maps are annotation transactions, never footprint/copper repair."""
import copy,json
from pathlib import Path
import pcbnew,pytest
import cec_dense_reference_mapping as maps
import cec_field_coupling as field
import cec_force_current as force
from test_lastmile import _board


def fixture(tmp_path, *, quarter=0, back=False, roomy=False):
    edge=(0,0,60,60) if roomy else (15,15,25,25)
    b=_board([],edge=edge);b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    library=Path(__file__).resolve().parents[1]/'lib/vendor/Package_SO.pretty'
    fp=pcbnew.FootprintLoad(str(library),'SOIC-8_3.9x4.9mm_P1.27mm')
    assert fp is not None
    b.Add(fp);fp.SetReference('Z77');fp.SetValue('UNCHANGED-TEST-VALUE');fp.SetField('MPN','UNCHANGED-TEST-MPN')
    fp.SetPosition(pcbnew.VECTOR2I_MM(20,20))
    if back:fp.Flip(fp.GetPosition(),False)
    fp.SetOrientationDegrees(quarter*90)
    fp.Value().SetLayer(pcbnew.B_Fab if back else pcbnew.F_Fab)
    fp.GetField('MPN').SetLayer(pcbnew.B_Fab if back else pcbnew.F_Fab)
    fp.Reference().SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
    fp.Reference().SetVisible(True);fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(1,1))
    fp.Reference().SetTextThickness(150000)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    report=tmp_path/'source-native.json'
    force._write(report,dict(violations=[dict(type='silk_overlap',severity='warning',
        items=[dict(uuid=force._uid(fp.Reference()))])],unconnected_items=[]))
    # Deliberately synthetic discovery evidence, never a hardware DRC claim.
    producer=dict(ok=True,complete=True,native_inventory=dict(potentially_truncated=False),
        report=str(report),report_sha256=force._hash(report),source_files={str(source):force._hash(source)})
    grade=tmp_path/'discovery-only-grade.json'
    force._write(grade,dict(code_identity=force._code_identity(),boards=dict(candidate=dict(
        sha256=force._hash(source),native_producer=producer))))
    return source,grade,force._uid(fp)


def saved(tmp_path,**kwargs):
    source,grade,uid=fixture(tmp_path,**kwargs)
    q=maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend',maximum_components=1)
    q=json.loads(json.dumps(q));b,m=maps.construct(source,q)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(b,child)
    return source,child,q,uid,m


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_opposite_face_projection_is_readable_and_preserves_complete_native_source(tmp_path,quarter,back):
    source,child,q,uid,m=saved(tmp_path,quarter=quarter,back=back)
    before=source.read_bytes();r=maps.receive(source,child,q)
    assert r['ok'] and r['complete'],r
    assert q['mode']=='opposite_face_projected_courtyard'
    assert len(q['front_mapping_trials'])==12 and all(not row['fits'] for row in q['front_mapping_trials'])
    b=pcbnew.LoadBoard(str(child));f=next(fp for fp in b.GetFootprints() if force._uid(fp)==uid)
    assert f.GetValue()=='UNCHANGED-TEST-VALUE' and f.GetField('MPN').GetText()=='UNCHANGED-TEST-MPN'
    assert not f.Reference().IsVisible() and f.GetReference()=='Z77'
    text=next(d for d in f.GraphicalItems() if d.GetClass()=='PCB_TEXT' and d.GetLayer()==q['target_layer_id'])
    assert text.GetText()=='Z77' and text.IsMirrored() is (not back)
    assert text.GetLayer()==(pcbnew.F_SilkS if back else pcbnew.B_SilkS)
    assert text.GetTextSize().y>=1000000 and text.GetTextThickness()>=150000
    assert len(m['added_annotation_uuids'])==q['added_item_count']
    assert source.read_bytes()==before and not r['release_authority']


def test_readable_nearby_map_is_preferred_over_back_side_when_local_space_exists(tmp_path):
    source,child,q,_,_=saved(tmp_path,roomy=True)
    assert q['mode']=='nearby_front_mapping_chart'
    assert any(row['fits'] for row in q['front_mapping_trials'])
    assert q['target_layer_id']==pcbnew.F_SilkS
    b=pcbnew.LoadBoard(str(child))
    assert 'REF MAP' in [d.GetText() for d in b.GetDrawings() if d.GetClass()=='PCB_TEXT']
    assert maps.receive(source,child,q)['ok']


def test_exact_native_owner_scope_narrows_real_reported_eligibility_and_replays(tmp_path):
    source,grade,uid=fixture(tmp_path)
    proposal=maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend',
        maximum_components=1,owner_uuid_scope=[uid])
    assert proposal['owner_uuid_scope']==[uid]
    assert {r['footprint_uuid']for r in proposal['records']}=={uid}
    b,manifest=maps.construct(source,json.loads(json.dumps(proposal)))
    child=force._copy_family(source,tmp_path/'exact-owner-candidate');field._save_field_snapshot(b,child)
    assert maps.receive(source,child,proposal)['ok']
    forged=copy.deepcopy(proposal);forged['owner_uuid_scope']=['unreported-owner']
    with pytest.raises(ValueError,match='not_source_native_fault_eligible'):
        maps.construct(source,forged)


@pytest.mark.parametrize('scope',['any',None,['duplicate','duplicate'],[''],[True],list(map(str,range(9)))])
def test_invalid_owner_scope_never_grants_reference_visibility_permission(tmp_path,scope):
    source,grade,_=fixture(tmp_path);before=source.read_bytes()
    with pytest.raises(ValueError,match='bounded_exact_native_reference_owner_scope'):
        maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend',owner_uuid_scope=scope)
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['copper','pad','pose','reference','value','mpn','text','mirror',
    'height','stroke','outline','group_lock','source_ref_visibility','sidecar'])
def test_projection_receiver_rejects_every_unowned_electrical_or_annotation_change(tmp_path,fault):
    source,child,q,uid,m=saved(tmp_path,roomy=fault=='group_lock')
    b=pcbnew.LoadBoard(str(child));fp=next(fp for fp in b.GetFootprints() if force._uid(fp)==uid)
    text=next(d for d in fp.GraphicalItems() if d.GetClass()=='PCB_TEXT' and d.GetLayer()==q['target_layer_id']) if fault!='group_lock' else None
    if fault=='copper':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(18,18));t.SetEnd(pcbnew.VECTOR2I_MM(19,18))
        t.SetWidth(200000);b.Add(t)
    elif fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='reference':fp.SetReference('WRONG')
    elif fault=='value':fp.SetValue('WRONG')
    elif fault=='mpn':fp.GetField('MPN').SetText('WRONG')
    elif fault=='text':text.SetText('WRONG')
    elif fault=='mirror':text.SetMirrored(not text.IsMirrored())
    elif fault=='height':text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8))
    elif fault=='stroke':text.SetTextThickness(80000)
    elif fault=='outline':next(d for d in b.GetDrawings() if d.GetClass()=='PCB_SHAPE').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group_lock':next(iter(b.Groups())).SetLocked(False)
    elif fault=='source_ref_visibility':fp.Reference().SetVisible(True)
    field._save_field_snapshot(b,child)
    if fault=='sidecar':force._write(child.with_suffix('.kicad_pro'),{})
    r=maps.receive(source,child,q)
    assert not r['ok'] and r['errors'],r


@pytest.mark.parametrize('fault',['policy','source_hash','glyph','mirror','position','new_rule'])
def test_literal_saved_plan_cannot_be_repurposed_for_a_different_rule_or_geometry(tmp_path,fault):
    source,child,q,uid,m=saved(tmp_path);bad=copy.deepcopy(q)
    if fault=='policy':bad['policy']='anything'
    elif fault=='source_hash':bad['binding']['source_sha256']='0'*64
    elif fault=='glyph':bad['records'][0]['reference']='WRONG'
    elif fault=='mirror':bad['records'][0]['text_mirrored']=not bad['records'][0]['text_mirrored']
    elif fault=='position':bad['records'][0]['text_xy_mm'][0]+=.000001
    else:bad['binding']['factory_legend']['height']=.6
    with pytest.raises(ValueError,match='stale_or_forged'):
        maps.construct(source,bad)


@pytest.mark.parametrize('fault',['hidden','locked','group_ref','empty_faults','no_profile',
    'grade_epoch','truncated','source_hash'])
def test_source_evidence_and_explicit_ownership_are_required_before_hiding_any_reference(tmp_path,fault):
    source,grade,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    if fault=='hidden':fp.Reference().SetVisible(False)
    elif fault in ('locked','group_ref'):
        # KiCad does not persist PCB_FIELD editor locks or field-only group
        # membership. Use actual saved footprint ownership, not a transient
        # in-memory flag that disappears before the Source is inspected.
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(fp);g.SetLocked(fault=='locked')
    elif fault=='no_profile':
        props=b.GetProperties();del props['CEC_FAB_PROFILE'];b.SetProperties(props)
    field._save_field_snapshot(b,source)
    j=json.loads(grade.read_text());entry=j['boards']['candidate']
    entry['sha256']=force._hash(source);producer=entry['native_producer']
    producer['source_files'][str(source)]=entry['sha256']
    if fault=='empty_faults':
        force._write(Path(producer['report']),dict(violations=[],unconnected_items=[]))
        producer['report_sha256']=force._hash(Path(producer['report']))
    elif fault=='grade_epoch':j['code_identity']={}
    elif fault=='truncated':producer['native_inventory']['potentially_truncated']=True
    elif fault=='source_hash':entry['sha256']='0'*64
    force._write(grade,j);before=source.read_bytes()
    with pytest.raises(ValueError):maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend')
    assert source.read_bytes()==before


@pytest.mark.parametrize('key,value',[('maximum_components',True),('maximum_components',0),
    ('maximum_components',9),('seed_index',True),('seed_index',-1),('seed_index',32)])
def test_finite_geometry_work_bounds_are_not_truthy_policy_permission(tmp_path,key,value):
    source,grade,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='finite_dense_reference_mapping_domain_required'):
        maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend',**{key:value})


def test_tiny_projection_keeps_readable_font_and_uses_an_unambiguous_outside_leader(tmp_path):
    from shapely.geometry import box,GeometryCollection
    source,grade,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    f=maps.floors(b,source)
    items,ink,rows=maps.reverse_component(b,(fp,box(10,10,11.9,11)),pcbnew.B_SilkS,f,
        GeometryCollection(),box(0,0,40,40),GeometryCollection())
    assert rows[0]['leader_xy_mm'] and rows[0]['text_mirrored']
    text=next(item for item in items if item.GetClass()=='PCB_TEXT')
    assert text.GetTextSize().y>=1000000 and text.GetTextThickness()>=150000


def test_courtyard_opening_conflict_uses_exact_four_corners_not_a_moved_or_invented_body(tmp_path):
    from shapely.geometry import box,Point,GeometryCollection
    source,grade,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()));f=maps.floors(b,source)
    actual=box(10,10,14,14);opening=Point(10,12).buffer(.2)
    items,ink,rows=maps.reverse_component(b,(fp,actual),pcbnew.B_SilkS,f,
        opening,box(0,0,40,40),GeometryCollection())
    assert rows[0]['outline_style']=='four_exact_corner_brackets'
    assert rows[0]['courtyard_xy_mm']==[list(p) for p in actual.exterior.coords]
    assert len(rows[0]['outline_segments_xy_mm'])==8 and not ink.intersects(opening)


@pytest.mark.parametrize('quarter',range(4))
def test_back_legend_follows_real_component_motion_instead_of_becoming_a_stale_board_drawing(tmp_path,quarter):
    source,child,q,uid,m=saved(tmp_path,quarter=quarter)
    b=pcbnew.LoadBoard(str(child));fp=next(fp for fp in b.GetFootprints() if force._uid(fp)==uid)
    text=next(g for g in fp.GraphicalItems() if g.GetClass()=='PCB_TEXT' and g.GetLayer()==q['target_layer_id'])
    before=tuple(text.GetPosition());delta=pcbnew.VECTOR2I_MM(2,-1)
    fp.Move(delta)
    assert tuple(text.GetPosition())==(before[0]+delta.x,before[1]+delta.y)
    assert m['reverse_annotations_are_native_footprint_children'] and not m['added_root_annotation_uuids']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('roomy',[False,True])
def test_second_native_save_retains_entire_board_and_actual_annotation_ownership(tmp_path,quarter,back,roomy):
    source,child,q,uid,m=saved(tmp_path,quarter=quarter,back=back,roomy=roomy)
    b=pcbnew.LoadBoard(str(child));groups=list(b.Groups())
    if q['mode']=='opposite_face_projected_courtyard':
        assert m['added_group_uuid'] is None and not groups
    else:
        assert len(groups)==1 and groups[0].IsLocked() and list(groups[0].GetItems())
    second=force._copy_family(child,tmp_path/'second-roundtrip')
    field._save_field_snapshot(b,second)
    assert maps.syntax._freeze(maps.additive._nodes(child)[0])==maps.syntax._freeze(maps.additive._nodes(second)[0])
    proof=maps.receive(source,second,q)
    assert proof['ok'] and proof['complete'] and proof['whole_saved_second_native_roundtrip_stable'],proof
