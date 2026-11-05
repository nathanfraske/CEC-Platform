"""Readable board-specific references must not alter library footprint art."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest

import cec_dense_reference_mapping as original
import cec_mask_search_reference_mapping as maps
import cec_force_current as force
import cec_field_coupling as field
import cec_source_retaining_ses_import as raw
from test_dense_reference_mapping import fixture
from test_mask_search_reference_mapping import refresh_grade


def saved(tmp_path,**kwargs):
    source,grade,uid=fixture(tmp_path,**kwargs)
    q=maps.plan(source,grade=grade,board_hint='explicit_root_mapping_fixture',maximum_components=1,
        reverse_ownership='rigid_root_group_per_component')
    candidate=force._copy_family(source,tmp_path/'literal-root-map')
    m=maps.write_private(source,candidate,q)
    return source,candidate,q,uid,m


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('roomy',[False,True])
def test_root_owned_ink_has_rigid_native_owner_and_exact_physical_library_art(tmp_path,quarter,back,roomy):
    source,candidate,q,uid,m=saved(tmp_path,quarter=quarter,back=back,roomy=roomy)
    proof=maps.receive(source,candidate,q);assert proof['ok']and proof['complete'],proof
    old,new=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
    a=next(f for f in old.GetFootprints()if force._uid(f)==uid)
    b=next(f for f in new.GetFootprints()if force._uid(f)==uid)
    assert {force._uid(g)for g in a.GraphicalItems()}=={force._uid(g)for g in b.GraphicalItems()}
    group=next(g for g in new.Groups()if any(force._uid(i)==uid for i in g.GetItems()))
    assert b.GetParentGroup()is not None and group.IsLocked()
    assert b.IsLocked()==a.IsLocked()
    assert not b.Reference().IsVisible()and b.GetReference()==a.GetReference()
    assert not m['reverse_annotations_are_native_footprint_children']
    texts=[d for d in new.GetDrawings()if d.GetClass()=='PCB_TEXT'and d.GetText()==a.GetReference()]
    assert len(texts)==1 and texts[0].IsMirrored()==(q['target_layer_id']==pcbnew.B_SilkS)
    assert texts[0].GetTextSize().y>=1000000 and texts[0].GetTextThickness()>=150000
    for g in new.Groups():
        ids={force._uid(i)for i in g.GetItems()}
        assert uid in ids and any(force._uid(t)in ids for t in texts)
    # Group movement, not an unowned standalone drawing, preserves mapping.
    before=tuple(texts[0].GetPosition());delta=pcbnew.VECTOR2I_MM(1,-2)
    group.Move(delta)
    assert tuple(texts[0].GetPosition())==(before[0]+delta.x,before[1]+delta.y)
    assert tuple(b.GetPosition())==(a.GetPosition().x+delta.x,a.GetPosition().y+delta.y)


def test_literal_root_mapping_retains_native_omitted_empty_metadata(tmp_path):
    import uuid
    source,grade,uid=fixture(tmp_path)
    text=source.read_text();a,z=raw.inventory(text)[uid];node=text[a:z]
    metadata='(property "CEC Opaque" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "'+str(uuid.uuid4())+'") (effects (font (size 1 1))))'
    at=node.rfind(')');source.write_text(text[:a]+node[:at]+metadata+node[at:]+text[z:])
    refresh_grade(source,grade)
    q=maps.plan(source,grade=grade,board_hint='explicit_root_mapping_fixture',maximum_components=1,
        reverse_ownership='rigid_root_group_per_component')
    child=force._copy_family(source,tmp_path/'opaque');maps.write_private(source,child,q)
    assert metadata in child.read_text();proof=maps.receive(source,child,q);assert proof['ok'],proof
    field._save_field_snapshot(pcbnew.LoadBoard(str(child)),child)
    assert not maps.receive(source,child,q)['ok']


@pytest.mark.parametrize('fault',['reference','ink','group','pad','mirror'])
def test_root_mapping_receiver_refuses_unowned_visibility_copper_and_group_mutation(tmp_path,fault):
    source,candidate,q,uid,m=saved(tmp_path);b=pcbnew.LoadBoard(str(candidate))
    fp=next(f for f in b.GetFootprints()if force._uid(f)==uid)
    t=next(d for d in b.GetDrawings()if d.GetClass()=='PCB_TEXT')
    if fault=='reference':fp.Reference().SetVisible(True)
    elif fault=='ink':t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group':next(iter(b.Groups())).SetLocked(False)
    elif fault=='pad':next(iter(fp.Pads())).Move(pcbnew.VECTOR2I(1,0))
    else:t.SetMirrored(not t.IsMirrored())
    field._save_field_snapshot(b,candidate)
    assert not maps.receive(source,candidate,q)['ok']


@pytest.mark.parametrize('fault',['none','key','path','hash','epoch','partial','source_drift','truncated'])
def test_completed_suite_receipt_requires_exact_named_source_and_native_epoch(tmp_path,fault):
    source,grade,uid=fixture(tmp_path);j=json.loads(grade.read_text());old=j['boards']['candidate']
    row=dict(sha256=old['sha256'],path=str(source),producer=old['native_producer'],
        source_unchanged=True,source_family_unchanged=True,source_inputs_unchanged=True,source_intake_ok=True)
    j.update(kind='fresh-native-parity-and-early-intake',code_unchanged=True,plan_unchanged=True,
        boards={'synthetic_named_board':row})
    if fault=='key':j['boards']={'wrong_named_board':row}
    elif fault=='path':row['path']=str(source.parent/'not-source.kicad_pcb')
    elif fault=='hash':row['sha256']='0'*64
    elif fault=='epoch':j['code_identity']={}
    elif fault=='partial':j['code_unchanged']=False
    elif fault=='source_drift':row['source_inputs_unchanged']=False
    elif fault=='truncated':row['producer']['native_inventory']['potentially_truncated']=True
    force._write(grade,j)
    if fault=='none':
        b,f,report,binding=original.source_context(source,grade,'synthetic_named_board')
        assert binding['source_sha256']==force._hash(source)
    else:
        with pytest.raises(ValueError):original.source_context(source,grade,'synthetic_named_board')


@pytest.mark.parametrize('policy',[None,True,'unowned_board_text'])
def test_reverse_ownership_cannot_be_guessed_or_disabled(tmp_path,policy):
    source,grade,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='explicit_reverse_annotation_ownership'):
        maps.plan(source,grade=grade,board_hint='explicit_root_mapping_fixture',reverse_ownership=policy)


def test_unknown_front_body_refuses_front_map_without_hiding_a_valid_reverse_solution(tmp_path):
    source,grade,uid=fixture(tmp_path,roomy=True);b=pcbnew.LoadBoard(str(source))
    unknown=pcbnew.FOOTPRINT(b);unknown.SetReference('UNKNOWN_BODY');unknown.SetPosition(pcbnew.VECTOR2I_MM(40,40))
    for f in unknown.GetFields():f.SetVisible(False)
    b.Add(unknown);field._save_field_snapshot(b,source);refresh_grade(source,grade)
    q=maps.plan(source,grade=grade,board_hint='explicit_root_mapping_fixture',maximum_components=1,
        reverse_ownership='rigid_root_group_per_component',via_ink_policy='native_mask_and_bore')
    assert q['mode']=='opposite_face_projected_courtyard'
    assert all('front_mapping_body_inventory_refused'in r['reason']for r in q['front_mapping_trials'])
    child=force._copy_family(source,tmp_path/'unknown-front');maps.write_private(source,child,q)
    assert maps.receive(source,child,q)['ok']


@pytest.mark.parametrize('bore_at_corner',[False,True])
def test_reference_mask_policy_uses_native_tenting_but_retains_drill_obstacles(tmp_path,bore_at_corner):
    source,grade,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));fp=next(iter(b.GetFootprints()))
    x0,y0,x1,y1=original.court(fp).bounds
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(x1+.1 if bore_at_corner else x1+.5,
        y1 if bore_at_corner else(y0+y1)/2));v.SetWidth(1200000);v.SetDrill(500000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetFrontTentingMode(pcbnew.TENTING_MODE_TENTED);v.SetBackTentingMode(pcbnew.TENTING_MODE_TENTED);b.Add(v)
    field._save_field_snapshot(b,source);refresh_grade(source,grade)
    args=dict(grade=grade,board_hint='explicit_root_mapping_fixture',maximum_components=1,
        reverse_ownership='rigid_root_group_per_component',via_ink_policy='native_mask_and_bore')
    if bore_at_corner:
        with pytest.raises(ValueError,match='no_readable_clear_opposite_face'):maps.plan(source,**args)
    else:
        q=maps.plan(source,**args);assert q['records'][0]['outline_style']=='complete'
        child=force._copy_family(source,tmp_path/'native-apertures');maps.write_private(source,child,q)
        assert maps.receive(source,child,q)['ok']


def test_existing_native_root_group_survives_next_literal_mapping_prefix(tmp_path):
    source,grade,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    line=pcbnew.PCB_SHAPE(b);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.Cmts_User)
    line.SetStart(pcbnew.VECTOR2I_MM(16,16));line.SetEnd(pcbnew.VECTOR2I_MM(17,16));line.SetWidth(150000);b.Add(line)
    group=pcbnew.PCB_GROUP(b);group.SetName('Prior durable owner');b.Add(group);group.AddItem(line)
    field._save_field_snapshot(b,source);refresh_grade(source,grade)
    q=maps.plan(source,grade=grade,board_hint='explicit_root_mapping_fixture',maximum_components=1,
        reverse_ownership='rigid_root_group_per_component',via_ink_policy='native_mask_and_bore')
    child=force._copy_family(source,tmp_path/'next-prefix');maps.write_private(source,child,q)
    assert maps.receive(source,child,q)['ok']
    saved_board=pcbnew.LoadBoard(str(child));assert len(list(saved_board.Groups()))==2
    prior=next(g for g in saved_board.Groups()if g.GetName()=='Prior durable owner')
    assert {force._uid(i)for i in prior.GetItems()}=={force._uid(line)}
    prior.SetName('Changed unowned name');field._save_field_snapshot(saved_board,child)
    assert not maps.receive(source,child,q)['ok']


def test_group_order_canonicalization_preserves_complete_membership_and_other_root_order():
    a=['kicad_pcb',['version','20260206'],['group','"A"',['uuid','"a"'],['members','"x"']],
        ['group','"B"',['uuid','"b"'],['members','"y"']],['setup','retained']]
    b=copy.deepcopy(a);b[2],b[3]=b[3],b[2]
    assert original._root_annotation_order(a)==original._root_annotation_order(b)
    b[2][-1].append('"forged_member"')
    assert original._root_annotation_order(a)!=original._root_annotation_order(b)
    b=copy.deepcopy(a);b[1],b[-1]=b[-1],b[1]
    assert original._root_annotation_order(a)!=original._root_annotation_order(b)
    a=['kicad_pcb',['gr_text','"R1"',['uuid','"a"']],['gr_text','"C2"',['uuid','"b"']]]
    b=copy.deepcopy(a);b[1],b[2]=b[2],b[1]
    assert original._root_annotation_order(a)==original._root_annotation_order(b)
    b[1][1]='"WRONG"'
    assert original._root_annotation_order(a)!=original._root_annotation_order(b)
