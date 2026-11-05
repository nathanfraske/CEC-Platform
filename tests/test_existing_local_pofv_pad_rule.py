"""Actual native local-rule parity, no global floor or pad/clearance waiver."""
import json
import os
from pathlib import Path
import pcbnew
import pytest
import cec_existing_local_pofv_pad_rule as rule
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
import cec_native_drc_runner as native
from test_pair_package_via_floor import package_board


def case(tmp_path,angle=0,face=pcbnew.F_Cu,profile='jlcpcb_6l_pofv_signal'):
    b,_=package_board(angle,pad_size=.4,profile=profile)
    fp=next(iter(b.GetFootprints()))
    for p in fp.Pads():
        if face==pcbnew.B_Cu:
            mask=pcbnew.LSET();mask.AddLayer(face);p.SetLayerSet(mask)
    if face==pcbnew.B_Cu:fp.SetLayer(face)
    pads={p.GetNumber():p for p in fp.Pads()};target,seed=pads['1'],pads['2']
    for pad in (target,seed):pad.SetNet(b.FindNet('GND'))
    v=pcbnew.PCB_VIA(b);v.SetPosition(seed.GetPosition());v.SetNet(seed.GetNet())
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetWidth(300000);v.SetDrill(200000);b.Add(v)
    evidence=fr.group_local_pofv_signal_vias(b,[v]);assert evidence
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({
        'net_settings':{'classes':[dict(name='Default',track_width=.2,clearance=.2,
            via_diameter=.6,via_drill=.3)]},
        'board':{'design_settings':{'rules':{
        'min_via_diameter':.5,'min_through_hole_diameter':.3,'min_via_annular_width':.1,
        'min_hole_to_hole':.254,'min_clearance':.2}}}}))
    fr.ensure_local_pofv_signal_via_rule(str(source),dict(local_pofv_signal_vias=evidence))
    c=pcbnew.LoadBoard(str(source));target=next(p for f in c.GetFootprints() for p in f.Pads() if p.m_Uuid==target.m_Uuid)
    return c,source,target


def seat(b,pad,**kwargs):
    return fr._via_spot_clear(b,pad.GetPosition(),350000,200000,{pad.GetNetCode()},
        drill_nm=250000,net_code=pad.GetNetCode(),**kwargs)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_explicit_cardinal_source_package_projection_keeps_the_actual_existing_native_rule(tmp_path,angle,face):
    import cec_smd_macro_transport as transport
    b,source,pad=case(tmp_path,angle,face);fp=pad.GetParentFootprint()
    # The intentionally minimal package fixture starts with its anchor at
    # (0,0). Rebase that anchor without changing any actual source land.
    original={p.m_Uuid.AsString():tuple(p.GetPosition()) for p in fp.Pads()}
    fp.SetPosition(pad.GetPosition())
    for p in fp.Pads():p.SetPosition(pcbnew.VECTOR2I(*original[p.m_Uuid.AsString()]))
    field._save_field_snapshot(b,source);parent=pcbnew.LoadBoard(str(source))
    fp.Move(pcbnew.VECTOR2I_MM(2,1));fp.SetOrientationDegrees(fp.GetOrientationDegrees()+90)
    pose=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
    transport.apply(parent,b,allow_cardinal_rotations=True,maximum_shift_mm=8.)
    assert rule.resolve(b,pad) is None and not seat(b,pad,local_pofv_pad=pad)
    old=rule._floors(b);raw=source.read_bytes()
    rule.bind_projected_source_poses(b,{fp.GetReference():pose})
    context=rule.resolve(b,pad)
    assert context and context['projected_native_source_package']['entire_source_native_package_rederived']
    assert not context['projected_native_source_package']['placement_authority']
    assert seat(b,pad,local_pofv_pad=pad)
    assert rule._floors(b)==old and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['pose','shape','other_land','value','field','angle','lock','profile','floor','missing_rule'])
def test_projected_pad_context_never_certifies_a_modified_package_or_missing_rule(tmp_path,fault):
    b,source,pad=case(tmp_path);fp=pad.GetParentFootprint();fp.Move(pcbnew.VECTOR2I_MM(2,0))
    pose=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()]
    rule.bind_projected_source_poses(b,{fp.GetReference():pose})
    if fault=='pose':fp.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='shape':pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='other_land':next(p for p in fp.Pads() if p.m_Uuid!=pad.m_Uuid).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='value':fp.SetValue('changed_part')
    elif fault=='field':fp.Value().SetText('changed_part')
    elif fault=='angle':fp.SetOrientationDegrees(fp.GetOrientationDegrees()+1)
    elif fault=='lock':fp.SetLocked(True)
    elif fault=='profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='missing';b.SetProperties(props)
    elif fault=='floor':b.GetDesignSettings().m_ViasMinSize+=1
    else:source.with_suffix('.kicad_dru').unlink()
    before=rule._floors(b)
    assert rule.resolve(b,pad) is None and not seat(b,pad,local_pofv_pad=pad)
    assert rule._floors(b)==before


@pytest.mark.parametrize('angle',[0,90])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('profile',['jlcpcb_6l_pofv_signal','jlcpcb_6l_pofv_high_current'])
@pytest.mark.parametrize('mixed_rules',[False,True])
def test_saved_pad_rule_constructs_small_inpad_via_and_native_group_control_is_decisive(tmp_path,angle,face,profile,mixed_rules):
    b,source,pad=case(tmp_path,angle,face,profile);before=source.read_bytes()
    if mixed_rules:
        path=source.with_suffix('.kicad_dru');text=path.read_text()
        text=text.replace('(version 1)', '(version 1)\n(rule "track only" '
            '(condition "A.Type == \'Track\'") (constraint track_width (min 0.2mm)))')
        text+='\n(rule "pair only" (condition "A.Type == \'Track\'") (constraint diff_pair_gap (min 0.12mm) (max 0.2mm)))'
        text+='\n(rule "edge only" (condition "A.Type == \'Via\'") (constraint edge_clearance (min 0.25mm)))'
        text+='\n(rule "hole only" (condition "A.Type == \'Via\'") (constraint hole_clearance (min 0.15mm)))'
        path.write_text(text)
    ordinary=rule._floors(b);assert ordinary[:3]==(500000,300000,100000)
    context=rule.resolve(b,pad);assert context and context['minimum_nm']==dict(
        via_diameter=300000,hole_size=200000,annular_width=50000)
    assert not seat(b,pad)
    assert seat(b,pad,local_pofv_pad=pad)
    result,error=cells._add_ground_return(b,pad,board_path=str(source),reach_mm=.1,lock=True)
    assert error is None and result['status']=='via-in-pad',result
    via=next(t for t in b.GetTracks() if force._uid(t)==result['via_uuid'])
    assert (via.GetWidth(pcbnew.F_Cu),via.GetDrillValue())==(350000,250000)
    assert result['existing_native_local_pad_rule']['rule_sha256']==context['rule_sha256']
    ev=fr.group_local_pofv_signal_vias(b,[via]);assert ev
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    assert source.read_bytes()==before and rule._floors(b)==ordinary
    assert source.with_suffix('.kicad_dru').read_bytes()==child.with_suffix('.kicad_dru').read_bytes()
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('native factory rule control requires explicit native reporting build')
    def violations(path,label):
        output=tmp_path/(label+'.json');r=native.run(path,output,reporting_build=Path(build),timeout_s=10.)
        assert r['ok'] and r['complete'] and not r['native_inventory']['potentially_truncated']
        return [q for q in json.loads(output.read_text())['violations']
            if q['type'] in ('via_diameter','drill_out_of_range','annular_width')
            and any(item.get('uuid')==force._uid(via) for item in q['items'])]
    assert not violations(child,'in-existing-group')
    c=pcbnew.LoadBoard(str(child));actual=next(v for v in c.GetTracks() if force._uid(v)==force._uid(via))
    next(g for g in c.Groups() if g.GetName()==rule.GROUP).RemoveItem(actual)
    control=force._copy_family(child,tmp_path/'outside-group');field._save_field_snapshot(c,control)
    assert {v['type'] for v in violations(control,'outside-existing-group')}=={
        'via_diameter','drill_out_of_range','annular_width'}


@pytest.mark.parametrize('fault',['missing_rule','extra_rule','malformed_rule','wrong_condition','weaker_process',
    'no_group','moved_pad','resized_pad','profile','floors','no_saved_file','offcenter','wrong_net',
    'small_annulus','extra_exemption','offpad','too_small_pad','stronger_local_rule'])
def test_local_context_cannot_be_a_profile_name_or_global_minimum_bypass(tmp_path,fault):
    b,source,pad=case(tmp_path);path=source.with_suffix('.kicad_dru')
    if fault=='missing_rule':path.unlink()
    elif fault=='extra_rule':path.write_text(path.read_text()+'\n(rule "unknown" (constraint via_diameter (min .6mm)))\n')
    elif fault=='malformed_rule':path.write_text(path.read_text().replace('0.300mm','unknown'))
    elif fault=='wrong_condition':path.write_text(path.read_text().replace("A.Type == 'Via' && ",''))
    elif fault=='weaker_process':path.write_text(path.read_text().replace('0.200mm','0.100mm'))
    elif fault=='no_group':
        s=pcbnew.LoadBoard(str(source));g=next(iter(s.Groups()))
        for item in list(g.GetItems()):g.RemoveItem(item)
        field._save_field_snapshot(s,source)
    elif fault=='moved_pad':pad.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I(1,0))
    elif fault=='resized_pad':pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='missing';b.SetProperties(props)
    elif fault=='floors':b.GetDesignSettings().m_ViasMinSize+=1
    elif fault=='no_saved_file':b.SetFileName('')
    elif fault=='stronger_local_rule':path.write_text(path.read_text().replace('0.050mm','0.100mm'))
    elif fault=='too_small_pad':
        pad.SetSize(pcbnew.VECTOR2I(290000,290000));field._save_field_snapshot(b,source)
    before=rule._floors(b);kwargs=dict(local_pofv_pad=pad)
    if fault in ('offcenter','offpad','wrong_net','small_annulus','extra_exemption'):
        at=pad.GetPosition()+pcbnew.VECTOR2I(1 if fault=='offcenter' else 1000000 if fault=='offpad' else 0,0)
        code=pad.GetNetCode()+(1 if fault=='wrong_net' else 0)
        assert not fr._via_spot_clear(b,at,300000 if fault=='small_annulus' else 350000,200000,
            {code,code+1} if fault=='extra_exemption' else {code},drill_nm=250000,net_code=code,**kwargs)
    else:assert not seat(b,pad,**kwargs)
    assert before==rule._floors(b)


@pytest.mark.parametrize('constraint',[
    '(constraint track_width (min 0.2mm))',
    '(constraint diff_pair_gap (min 0.12mm) (max 0.2mm))',
    '(constraint edge_clearance (min 0.25mm))',
    '(constraint hole_clearance (min 0.15mm))'])
@pytest.mark.parametrize('before',[False,True])
def test_other_constraint_types_do_not_hide_existing_native_barrel_rule(tmp_path,constraint,before):
    b,source,pad=case(tmp_path);path=source.with_suffix('.kicad_dru');old=path.read_text()
    floors=rule._floors(b)
    other='(rule "separate native rule" (condition "A.Type == \'Track\'") '+constraint+')\n'
    if before:
        old=old.replace('(version 1)','(version 1)\n'+other)
    else:old+=other
    path.write_text(old)
    context=rule.resolve(b,pad)
    assert context and context['minimum_nm']==dict(via_diameter=300000,hole_size=200000,annular_width=50000)
    assert not seat(b,pad) and seat(b,pad,local_pofv_pad=pad)
    assert rule._floors(b)==floors


@pytest.mark.parametrize('other',[
    '(rule "x" (condition "A.Type == \'Via\'") (constraint via_diameter (min .6mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint hole_size (min .3mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint annular_width (min .1mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint clearance (min .3mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint disallow via))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint track_width (min .2mm)) (constraint hole_size (min .3mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (condition "A.Type == \'Pad\'") (constraint track_width (min .2mm)))',
    '(rule "x" (constraint track_width (min .2mm)))',
    '(rule "x" (condition "") (constraint track_width (min .2mm)))',
    '(rule "x" (condition "A.Type == \'Track\'") (constraint track_width (min -1mm)))',
    '(rule "x" (condition "A.Type == \'Track\'") (constraint track_width (min .3mm) (max .2mm)))',
    '(rule "x" (condition "A.Type == \'Track\'") (constraint track_width (min .2mm)) (severity ignore))',
    '(rule "x" (condition "A.Type == \'Track\'") (constraint track_width (min .2mm)) (constraint track_width (min .3mm)))',
    '(rule "x" (condition "A.Type == \'Track\'") (constraint track_width (min .2mil)))',
    '(rule "x" (condition "A.Type == \'Track\'") (constraint track_width (min NaNmm)))'])
def test_unknown_or_mixed_dimension_rules_remain_fail_closed(tmp_path,other):
    b,source,pad=case(tmp_path);path=source.with_suffix('.kicad_dru')
    path.write_text(path.read_text()+'\n'+other+'\n')
    assert rule.resolve(b,pad) is None and not seat(b,pad,local_pofv_pad=pad)


def test_duplicate_existing_local_rule_is_not_a_precedence_guess(tmp_path):
    b,source,pad=case(tmp_path);path=source.with_suffix('.kicad_dru');text=path.read_text()
    path.write_text(text+'\n'+text.replace('(version 1)',''))
    assert rule.resolve(b,pad) is None
