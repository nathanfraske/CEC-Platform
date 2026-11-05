"""Literal existing-rule VIP replaces only a positively owned local return."""
import json
from pathlib import Path
import pcbnew
import pytest
import cec_bypass_return_reseat as op
import cec_force_current as force
import cec_field_coupling as field
import cec_existing_local_pofv_pad_rule as rule
import cec_additive_route_receiving as additive
from test_full_class_bypass_return_reseat import fixture as full_fixture

OPTIONS=dict(allow_owned_locked=True,allow_qualified_local_vias=True,
    source_full_class=True,source_local_pad_entry=True)


def fixture(tmp_path,quarter=0,back=False):
    b,source,pad,edge,*_=full_fixture(tmp_path,quarter=quarter,back=back)
    holder=pcbnew.FOOTPRINT(b);holder.SetReference('FACTORY_SEED');b.Add(holder)
    p=pcbnew.PAD(holder);p.SetNumber('1');p.SetNetCode(b.GetNetcodeFromNetname('+3V3'))
    p.SetPosition(pcbnew.VECTOR2I_MM(24,24));p.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());holder.Add(p)
    seed=pcbnew.PCB_VIA(b);seed.SetPosition(p.GetPosition());seed.SetNet(p.GetNet());seed.SetWidth(500000);seed.SetDrill(300000)
    seed.SetViaType(pcbnew.VIATYPE_THROUGH);seed.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(seed)
    g=pcbnew.PCB_GROUP(b);g.SetName(rule.GROUP);b.Add(g);g.AddItem(seed)
    source.with_suffix('.kicad_dru').write_text('(version 1)\n(rule "CEC local POFV signal via" '
        '(condition "A.Type == \'Via\' && A.memberOfGroup(\'CEC_LOCAL_POFV_SIGNAL_VIA\')") '
        '(constraint via_diameter (min 0.5mm)) (constraint hole_size (min 0.3mm)) '
        '(constraint annular_width (min 0.1mm)))\n')
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return b,source,pad,edge


def saved(tmp_path,**kwargs):
    b,source,pad,edge=fixture(tmp_path,**kwargs);q=op.plan(b,pad,edge,**OPTIONS)
    child=force._copy_family(source,tmp_path/'local-entry-child');actual=pcbnew.LoadBoard(str(child));op.subtract(actual,q)
    entry=q['replacement_source_local_pad_entry'];v=pcbnew.PCB_VIA(actual)
    v.SetNetCode(actual.GetNetcodeFromNetname('GND'));v.SetPosition(pcbnew.VECTOR2I(*entry['at_nm']))
    v.SetWidth(entry['diameter_nm']);v.SetDrill(entry['drill_nm']);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLocked(True);actual.Add(v)
    next(g for g in actual.Groups()if force._uid(g)==entry['group_uuid']).AddItem(v)
    field._save_field_snapshot(actual,child)
    final=Path(additive.finalize_private(source,child,tmp_path/'local-entry-final')['board'])
    return source,final,pad,edge,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_saved_source_pad_rule_is_recompiled_across_private_family_paths(tmp_path,quarter,back):
    source,child,pad,edge,q=saved(tmp_path,quarter=quarter,back=back);raw=(source.read_bytes(),child.read_bytes())
    r=op.receive(source,child,pad_uuid=pad,track_uuid=edge,board_hint='synthetic',**OPTIONS)
    assert r['ok']and r['complete'],r
    assert r['new_path_mm']==0 and r['replacement_uses_only_exact_existing_source_pad_rule']
    assert not r['source_barrel_geometry_preserved']and not r['new_barrel_ampacity_credited']
    assert not r['current_authority']and not r['release_authority']
    assert r['replacement_barrel_native_clearance']['ok']
    assert raw==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('fault',['no_full_class','no_process','nonbool','missing_rule','missing_group',
    'locked_group','below_setup','source_land_too_small','power_owner'])
def test_new_mode_cannot_infer_an_smd_owner_or_introduce_a_factory_waiver(tmp_path,fault):
    b,source,pad,edge=fixture(tmp_path);options=dict(OPTIONS)
    if fault=='no_full_class':options['source_full_class']=False
    elif fault=='no_process':options['allow_qualified_local_vias']=False
    elif fault=='nonbool':options['source_local_pad_entry']=1
    elif fault=='missing_rule':source.with_suffix('.kicad_dru').unlink()
    elif fault=='missing_group':
        from cec_native_items import discard_items
        group=next(g for g in b.Groups()if g.GetName()==rule.GROUP)
        for t in list(group.GetItems()):group.RemoveItem(t)
        discard_items(b,[group]);field._save_field_snapshot(b,source)
    elif fault=='locked_group':
        next(g for g in b.Groups()if g.GetName()==rule.GROUP).SetLocked(True);field._save_field_snapshot(b,source)
    elif fault=='below_setup':
        path=source.with_suffix('.kicad_dru');path.write_text(path.read_text().replace('0.5mm','0.4mm'))
    elif fault=='source_land_too_small':
        next(p for f in b.GetFootprints()for p in f.Pads()if force._uid(p)==pad).SetSize(pcbnew.VECTOR2I_MM(.49,.49))
        field._save_field_snapshot(b,source)
    else:b.FindFootprintByReference('ICA').SetValue('TLV62569DBVR');field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(b,pad,edge,**options)


@pytest.mark.parametrize('fault',['diameter','drill','remote','missing_membership','changed_pad','extra_track'])
def test_saved_replacement_must_be_one_actual_contained_source_rule_member(tmp_path,fault):
    source,child,pad,edge,q=saved(tmp_path);actual=pcbnew.LoadBoard(str(child))
    old={force._uid(t)for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    via=next(t for t in actual.GetTracks()if force._uid(t)not in old)
    if fault=='diameter':via.SetWidth(600000)
    elif fault=='drill':via.SetDrill(200000)
    elif fault=='remote':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='missing_membership':next(g for g in actual.Groups()if g.ContainsItem(via)).RemoveItem(via)
    elif fault=='changed_pad':next(p for f in actual.GetFootprints()for p in f.Pads()if force._uid(p)==pad).Move(pcbnew.VECTOR2I(1,0))
    else:
        t=pcbnew.PCB_TRACK(actual);t.SetNet(via.GetNet());t.SetWidth(500000);t.SetLayer(pcbnew.F_Cu)
        t.SetStart(via.GetPosition());t.SetEnd(via.GetPosition()+pcbnew.VECTOR2I(100000,0));actual.Add(t)
    field._save_field_snapshot(actual,child)
    r=op.receive(source,child,pad_uuid=pad,track_uuid=edge,board_hint='synthetic',**OPTIONS)
    assert not r['ok']and r['errors'],r


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_public_constructor_derives_all_geometry_and_preserves_opaque_source(tmp_path,quarter,back):
    b,source,pad,edge=fixture(tmp_path,quarter=quarter,back=back);raw=source.read_bytes()
    candidate=force._copy_family(source,tmp_path/'public-constructor')
    r=op.construct_source_local_pad_entry(source,candidate,board_hint='synthetic',pad_uuid=pad,track_uuid=edge)
    assert r['complete']and r['source_and_code_unchanged']and source.read_bytes()==raw
    assert all(p['elapsed_s']<10 for p in r['phases'])
    proof=op.receive(source,candidate,pad_uuid=pad,track_uuid=edge,board_hint='synthetic',**OPTIONS)
    assert proof['ok']and proof['complete'],proof
    assert not r['release_authority']and not r['current_authority']and not r['source_selected']


@pytest.mark.parametrize('fault',['overwrite','not_copy','changed_rules','no_identity','caller_geometry'])
def test_constructor_requires_an_exact_private_family_and_no_geometry_override(tmp_path,fault):
    b,source,pad,edge=fixture(tmp_path);raw=source.read_bytes()
    candidate=force._copy_family(source,tmp_path/'refused-constructor');options=dict(
        board_hint='synthetic',pad_uuid=pad,track_uuid=edge)
    if fault=='overwrite':candidate=source
    elif fault=='not_copy':candidate.write_text(candidate.read_text()+'\n')
    elif fault=='changed_rules':candidate.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='no_identity':options['board_hint']=''
    else:options['diameter_nm']=1
    with pytest.raises((ValueError,TypeError)):op.construct_source_local_pad_entry(source,candidate,**options)
    assert source.read_bytes()==raw
