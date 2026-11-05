"""A legacy empty native group is not permission to lose real PCB evidence."""
import copy
import pcbnew,pytest
import cec_annotation_group_roundtrip as repair
import cec_dense_reference_mapping as maps
import cec_field_coupling as field
import cec_force_current as force
from test_dense_reference_mapping import saved
from test_field_proposals import track


def legacy(tmp_path,quarter=0,back=False):
    source,child,q,uid,manifest=saved(tmp_path,quarter=quarter,back=back)
    b=pcbnew.LoadBoard(str(child));fp=next(f for f in b.GetFootprints() if force._uid(f)==uid)
    g=pcbnew.PCB_GROUP(b);g.SetName(maps.GROUP);g.SetLocked(True);b.Add(g)
    ids=set(manifest['added_annotation_uuids'])
    for item in fp.GraphicalItems():
        if force._uid(item) in ids:g.AddItem(item)
    group_uid=force._uid(g);field._save_field_snapshot(b,child)
    reloaded=pcbnew.LoadBoard(str(child));native=next(g for g in reloaded.Groups() if force._uid(g)==group_uid)
    assert not list(native.GetItems())
    assert repair.additive._members(repair.additive._nodes(child)[1][group_uid])
    return child,uid,group_uid


def repaired(tmp_path,**kwargs):
    source,uid,group_uid=legacy(tmp_path,**kwargs)
    q=repair.plan(source,board_hint='synthetic_annotation_roundtrip')
    b=repair.construct(source,q);child=force._copy_family(source,tmp_path/'repaired')
    field._save_field_snapshot(b,child)
    return source,child,uid,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_only_nonfunctional_legacy_group_is_retired_with_every_real_child_preserved(tmp_path,quarter,back):
    source,child,uid,q=repaired(tmp_path,quarter=quarter,back=back);original=source.read_bytes()
    r=repair.receive(source,child,q,board_hint='synthetic_annotation_roundtrip')
    assert r['ok'] and r['complete'] and r['second_native_roundtrip_stable'],r
    assert r['every_source_item_except_exact_broken_group_metadata_identical']
    assert r['no_copper_pad_pose_glyph_field_rule_or_valid_group_change']
    b=pcbnew.LoadBoard(str(child));fp=next(f for f in b.GetFootprints() if force._uid(f)==uid)
    assert not fp.Reference().IsVisible() and fp.GetReference()=='Z77'
    assert not list(b.Groups()) and list(fp.GraphicalItems())
    assert source.read_bytes()==original and not r['release_authority']


@pytest.mark.parametrize('fault',['copper','pad','pose','glyph','reference','value','mpn','sidecar'])
def test_group_repair_rejects_every_unowned_saved_physical_or_bom_change(tmp_path,fault):
    source,child,uid,q=repaired(tmp_path);b=pcbnew.LoadBoard(str(child));fp=next(f for f in b.GetFootprints() if force._uid(f)==uid)
    if fault=='copper':track(b,'GND',(18,18),(19,18),width=.2)
    elif fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='glyph':next(g for g in fp.GraphicalItems() if g.GetClass()=='PCB_TEXT').SetText('not_the_source_glyph')
    elif fault=='reference':fp.Reference().SetVisible(True)
    elif fault=='value':fp.SetValue('not_the_source_value')
    elif fault=='mpn':fp.GetField('MPN').SetText('not_the_source_mpn')
    field._save_field_snapshot(b,child)
    if fault=='sidecar':force._write(child.with_suffix('.kicad_pro'),{})
    r=repair.receive(source,child,q,board_hint='synthetic_annotation_roundtrip')
    assert not r['ok'] and not r['complete'] and r['errors']


@pytest.mark.parametrize('fault',['group_name','unlocked_group','copper_child','source_ref_visible','functional_group'])
def test_unknown_or_functional_ownership_is_never_retired_as_legacy_metadata(tmp_path,fault):
    source,child,q,uid,manifest=saved(tmp_path)
    b=pcbnew.LoadBoard(str(child));fp=next(f for f in b.GetFootprints() if force._uid(f)==uid)
    g=pcbnew.PCB_GROUP(b);g.SetName(maps.GROUP if fault!='group_name' else 'unknown_owner');g.SetLocked(True);b.Add(g)
    selected=[i for i in fp.GraphicalItems() if force._uid(i) in set(manifest['added_annotation_uuids'])]
    if fault=='copper_child':selected[0].SetLayer(pcbnew.F_Cu)
    elif fault=='source_ref_visible':fp.Reference().SetVisible(True)
    if fault=='functional_group':g.AddItem(fp)
    else:
        for item in selected:g.AddItem(item)
    if fault=='unlocked_group':g.SetLocked(False)
    field._save_field_snapshot(b,child)
    with pytest.raises(ValueError):repair.plan(child,board_hint='synthetic_annotation_roundtrip')


@pytest.mark.parametrize('fault',['source_hash','retirement','member','context'])
def test_stale_or_forged_group_migration_is_not_construction_authority(tmp_path,fault):
    source,child,uid,q=repaired(tmp_path);q=copy.deepcopy(q)
    if fault=='source_hash':q['source_sha256']='0'*64
    elif fault=='retirement':q['retired_group_uuids']=[]
    elif fault=='member':q['groups'][0]['raw_member_uuids']=[]
    else:q['board_hint']=''
    with pytest.raises(ValueError):repair.construct(source,q)


def test_new_legend_producer_refuses_to_silently_drop_legacy_source_group(tmp_path):
    source,uid,group_uid=legacy(tmp_path)
    report=tmp_path/'synthetic-native-discovery.json'
    force._write(report,dict(violations=[],unconnected_items=[]))
    grade=tmp_path/'synthetic-discovery-context.json'
    force._write(grade,dict(code_identity=force._code_identity(),boards=dict(candidate=dict(
        sha256=force._hash(source),native_producer=dict(ok=True,complete=True,
            native_inventory=dict(potentially_truncated=False),report=str(report),
            report_sha256=force._hash(report),source_files={str(source):force._hash(source)})))))
    original=source.read_bytes()
    with pytest.raises(ValueError,match='source_contains_nonroundtrip_group_requires_separate_repair'):
        maps.plan(source,grade=grade,board_hint='synthetic_annotation_roundtrip')
    assert source.read_bytes()==original
