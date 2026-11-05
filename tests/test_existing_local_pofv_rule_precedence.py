"""Source-order parity with native rules, not a new rule or floor waiver."""
import json
import os

import pcbnew
import pytest

import cec_existing_local_pofv_pad_rule as rule
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_drc_runner as native
from test_existing_local_pofv_pad_rule import case,seat


EARLIER = '''
(rule "source current lane barrel"
  (constraint via_diameter (min 0.6mm))
  (condition "A.NetClass == 'Power12V'"))
(rule "source pair returns"
  (condition "A.Type == 'Via' && A.memberOfGroup('OTHER_RETURN_GROUP')")
  (constraint hole_size (min 0.3mm))
  (constraint annular_width (min 0.15mm)))
'''


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_earlier_barrel_rules_cannot_shadow_later_exact_saved_local_dimensions(tmp_path,face,angle):
    b,source,pad=case(tmp_path,angle,face)
    path=source.with_suffix('.kicad_dru')
    path.write_text(path.read_text().replace('(version 1)','(version 1)'+EARLIER))
    source_bytes=source.read_bytes();rule_bytes=path.read_bytes();floors=rule._floors(b)
    context=rule.resolve(b,pad)
    assert context and context['minimum_nm']==dict(via_diameter=300000,hole_size=200000,annular_width=50000)
    assert not seat(b,pad) and seat(b,pad,local_pofv_pad=pad)
    assert source.read_bytes()==source_bytes and path.read_bytes()==rule_bytes and rule._floors(b)==floors


@pytest.mark.parametrize('constraint',[
    '(constraint via_diameter (min .6mm))',
    '(constraint hole_size (min .3mm))',
    '(constraint annular_width (min .15mm))'])
def test_same_dimension_rule_after_local_rule_is_never_guessed_away(tmp_path,constraint):
    b,source,pad=case(tmp_path);path=source.with_suffix('.kicad_dru')
    path.write_text(path.read_text()+'\n(rule "later dimension" (condition "A.Type == \'Via\'") '+constraint+')')
    assert rule.resolve(b,pad) is None and not seat(b,pad,local_pofv_pad=pad)


@pytest.mark.parametrize('other',[
    '(rule "x" (condition "A.Type == \'Via\'") (constraint via_diameter (max .6mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint hole_size (min .3mm) (max .5mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint annular_width (min -1mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint hole_size (min NaNmm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint clearance (min .3mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint disallow via))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint via_diameter (min .6mm)) (severity ignore))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint hole_size (min .3mm)) (layer outer))',
    '(rule "x" (constraint hole_size (min .3mm)))',
    '(rule "x" (condition "") (constraint hole_size (min .3mm)))',
    '(rule "x" (condition "A.Type == \'Via\'") (constraint hole_size (min .3mm)) (constraint hole_size (min .4mm)))',
])
def test_unknown_earlier_constraint_cannot_claim_shadowed_dimension_authority(tmp_path,other):
    b,source,pad=case(tmp_path);path=source.with_suffix('.kicad_dru')
    path.write_text(path.read_text().replace('(version 1)','(version 1)\n'+other))
    assert rule.resolve(b,pad) is None and not seat(b,pad,local_pofv_pad=pad)


def test_saved_rule_at_or_above_all_setup_floors_needs_no_subfloor_seed(tmp_path):
    b,source,pad=case(tmp_path)
    floors=rule._floors(b)
    # Source ordinary geometry is not an exemption. Grow both actual lands
    # and its existing seed, without editing ANY board floor.
    fp=pad.GetParentFootprint()
    for p in fp.Pads():p.SetSize(pcbnew.VECTOR2I(800000,800000))
    seed=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA');seed.SetWidth(500000);seed.SetDrill(300000)
    field._save_field_snapshot(b,source)
    path=source.with_suffix('.kicad_dru')
    path.write_text(path.read_text().replace('0.300mm','0.500mm')
        .replace('0.200mm','0.300mm').replace('0.050mm','0.100mm'))
    context=rule.resolve(b,pad)
    assert context and context['all_local_dimensions_at_or_above_ordinary_setup']
    assert rule.geometry(context,(.3,.2))==(.5,.3)
    assert rule._floors(b)==floors and floors[:3]==(500000,300000,100000)


def test_actual_native_before_after_rule_order_and_outside_group_control(tmp_path):
    b,source,pad=case(tmp_path);path=source.with_suffix('.kicad_dru')
    # A condition that really matches this barrel: precedence, not a claim
    # that the earlier source rule's condition is false.
    earlier='(rule "earlier via" (condition "A.Type == \'Via\'") (constraint hole_size (min 0.3mm)))'
    path.write_text(path.read_text().replace('(version 1)','(version 1)\n'+earlier))
    assert rule.resolve(b,pad)
    result,error=cells._add_ground_return(b,pad,board_path=str(source),reach_mm=.1,lock=True)
    assert error is None and result['status']=='via-in-pad'
    via=next(t for t in b.GetTracks() if force._uid(t)==result['via_uuid'])
    assert fr.group_local_pofv_signal_vias(b,[via])
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('explicit native reporting build required')
    def findings(board,name):
        output=tmp_path/(name+'.json')
        proof=native.run(board,output,reporting_build=build,timeout_s=10.)
        assert proof['ok'] and proof['complete'] and not proof['native_inventory']['potentially_truncated'],proof
        return {r['type'] for r in json.loads(output.read_text())['violations']
            if any(i.get('uuid')==force._uid(via) for i in r['items'])}
    assert not findings(child,'earlier')&{'drill_out_of_range','via_diameter','annular_width'}
    later=force._copy_family(child,tmp_path/'later')
    later.with_suffix('.kicad_dru').write_text(child.with_suffix('.kicad_dru').read_text()+'\n'+earlier.replace('earlier via','later via'))
    assert 'drill_out_of_range' in findings(later,'later')
    outside=pcbnew.LoadBoard(str(child));actual=next(t for t in outside.GetTracks() if force._uid(t)==force._uid(via))
    next(g for g in outside.Groups() if g.GetName()==rule.GROUP).RemoveItem(actual)
    control=force._copy_family(child,tmp_path/'outside');field._save_field_snapshot(outside,control)
    assert {'drill_out_of_range','via_diameter','annular_width'}<=findings(control,'outside')
