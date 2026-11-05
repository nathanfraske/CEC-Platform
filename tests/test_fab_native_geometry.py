"""Factory physical-drill and legend witnesses are native, typed and bounded."""
import math

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fab_check as fab
import cec_fab_native_geometry as native


def rules():
    return fab.profile_rules(fab.PROFILES['jlcpcb'], 1., 'jlcpcb_6l_pofv_signal')


def board():
    value = pcbnew.CreateEmptyBoard()
    value.SetCopperLayerCount(6)
    value.GetDesignSettings().m_HoleToHoleMin = 0
    value.Add(pcbnew.NETINFO_ITEM(value, 'arbitrary_same_net'))
    return value


def pad(b, x, y, *, drill=(.6, 1.9), angle=90, plated=True, ref='RENAMED'):
    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference(ref)
    b.Add(fp)
    p = pcbnew.PAD(fp)
    p.SetNumber('1')
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if plated else pcbnew.PAD_ATTRIB_NPTH)
    p.SetShape(pcbnew.PAD_SHAPE_OVAL)
    p.SetSize(pcbnew.VECTOR2I_MM(drill[0]+.5, drill[1]+.5))
    p.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_CIRCLE if drill[0] == drill[1]
                    else pcbnew.PAD_DRILL_SHAPE_OBLONG)
    p.SetDrillSize(pcbnew.VECTOR2I_MM(*drill))
    p.SetOrientationDegrees(angle)
    p.SetPosition(pcbnew.VECTOR2I_MM(x, y))
    if plated:
        p.SetNet(b.FindNet('arbitrary_same_net'))
    fp.Add(p)
    return fp, p


def via(b, x, y, *, drill=.6):
    value = pcbnew.PCB_VIA(b)
    value.SetViaType(pcbnew.VIATYPE_THROUGH)
    value.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    value.SetPosition(pcbnew.VECTOR2I_MM(x, y))
    value.SetDrill(pcbnew.FromMM(drill))
    value.SetWidth(pcbnew.FromMM(drill+.3))
    value.SetNet(b.FindNet('arbitrary_same_net'))
    b.Add(value)
    return value


@pytest.mark.parametrize('angle,shift', [(0,(20,30)), (45,(42,-13)), (90,(-5,20)), (137,(99,12))])
@pytest.mark.parametrize('plated', [False, True])
def test_parallel_slot_overlap_is_found_after_native_rotation_translation(angle, shift, plated):
    b = board()
    # Native pad rotation is clockwise; the short axis rotates with it.
    theta = math.radians(angle)
    dx, dy = .5*math.cos(theta), -.5*math.sin(theta)
    owners = [pad(b,*shift,angle=angle,plated=plated,ref='A'),
              pad(b,shift[0]+dx,shift[1]+dy,angle=angle,plated=plated,ref='B')]
    result = native.audit_holes(b, rules())
    assert result['complete'], result
    assert result['examined_pairs'] == 1
    assert len(result['findings']) == 1
    assert result['findings'][0]['signed_gap_mm'] == pytest.approx(-.1, abs=3e-6)
    assert result['findings'][0]['floor_mm'] == .45
    assert result['same_net_pairs'] == 1
    assert owners  # keep native parents alive


@pytest.mark.parametrize('kind,gap,blocked', [
    ('via_via',.249999,True), ('via_via',.25,False),
    ('pad_pad',.449999,True), ('pad_pad',.45,False),
    ('via_pad',.449999,True), ('via_pad',.45,False),
])
def test_typed_circle_pair_floors_not_process_overlay_alone(kind,gap,blocked):
    b = board()
    owners = []
    for index, typ in enumerate(kind.split('_')):
        if typ == 'pad':
            owners.append(pad(b,10+index*(.6+gap),10,drill=(.6,.6)))
        else:
            owners.append(via(b,10+index*(.6+gap),10))
    result = native.audit_holes(b,rules())
    assert result['complete'],result
    assert bool(result['findings']) is blocked


def test_actual_board_filled_default_makes_mixed_factory_floor_strict():
    b = board()
    b.GetDesignSettings().m_FillVias = True
    owners = [via(b,10,10),pad(b,11.05,10,drill=(.6,.6))]
    result = native.audit_holes(b,rules())
    assert result['complete'],result
    assert result['findings'][0]['comparator'] == '>'
    assert result['inventory'][0]['uuid']
    assert owners


@pytest.mark.parametrize('mode,strict',[(1,True),(2,False)])
def test_actual_native_fill_override_beats_inherited_default(mode,strict):
    b=board(); b.GetDesignSettings().m_FillVias=True
    v=via(b,10,10); v.SetFillingMode(mode)
    owners=[v,pad(b,11.05,10,drill=(.6,.6))]
    result=native.audit_holes(b,rules())
    assert result['complete'],result
    assert bool(result['findings']) is strict
    assert owners


def test_native_slots_do_not_use_enclosing_radius_false_positive():
    b = board()
    owners = [pad(b,10,10),pad(b,10,11.05)]
    result = native.audit_holes(b,rules())
    assert result['complete'] and not result['findings'],result
    assert owners


def test_board_and_all_numeric_intent_floors_only_strengthen_factory(tmp_path):
    b=board()
    b.GetDesignSettings().m_HoleToHoleMin=pcbnew.FromMM(.7)
    owners=[via(b,10,10),via(b,11.3,10)]
    path=tmp_path/'b.kicad_pcb'
    path.with_suffix('.kicad_dru').write_text('''(version 1)
(rule conditional_stricter (condition "A.NetName == 'unrelated'")
 (constraint hole_to_hole (min 0.8mm)))
''')
    result=native.audit_holes(b,rules(),board_path=path)
    assert result['complete'] and result['findings'][0]['floor_mm']==.8
    assert result['source_dru']['method']=='maximum_numeric_minimum_across_all_conditions'
    assert owners


def test_unsupported_dimensional_expression_is_not_zero(tmp_path):
    path=tmp_path/'b.kicad_pcb'
    path.with_suffix('.kicad_dru').write_text('''(version 1)
(rule computed (constraint hole_to_hole (min "0.2mm + 0.1mm")))''')
    result=native.audit_holes(board(),rules(),board_path=path)
    assert result['complete'] is False
    assert 'unsupported_hole_rule_minimum' in result['error']


def test_partial_barrel_and_pair_budget_and_parent_expiry_are_incomplete(monkeypatch):
    b=board()
    v=via(b,10,10)
    v.SetViaType(pcbnew.VIATYPE_BLIND)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu)
    result=native.audit_holes(b,rules())
    assert not result['complete'] and result['unsupported']
    b=board(); owners=[via(b,10,10),via(b,11,10)]
    result=native.audit_holes(b,rules(),max_pairs=0)
    assert not result['complete'] and 'pair_budget' in result['error']
    monkeypatch.setenv('CEC_OPERATION_DEADLINE_EPOCH','1')
    result=native.audit_holes(b,rules())
    assert not result['complete'] and 'enclosing' in result['error']
    assert owners


def test_dense_hole_report_budget_preserves_proven_blocker_without_claiming_complete():
    b=board(); owners=[via(b,10,10),via(b,10.1,10),via(b,10.2,10)]
    result=native.audit_holes(b,rules(),max_findings=1)
    assert not result['complete'] and len(result['findings'])==1
    assert 'finding_report_budget' in result['error']
    assert owners


def test_legend_minima_are_independent_of_board_warning_configuration():
    b=board()
    t=pcbnew.PCB_TEXT(b)
    t.SetLayer(pcbnew.F_SilkS);t.SetText('Native tiny legend')
    t.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8));t.SetTextThickness(pcbnew.FromMM(.12));b.Add(t)
    result=native.audit_legend(b,rules())
    assert result['complete'],result
    assert {v['dimension'] for v in result['findings']}=={'height_mm','stroke_mm'}
    assert all(v['item']['uuid']==t.m_Uuid.AsString() for v in result['findings'])


@pytest.mark.parametrize('angle,shift', [(0,(0,0)), (45,(22,-13)), (90,(-5,20)), (137,(99,12))])
@pytest.mark.parametrize('shape', ['circle', 'rectangle'])
def test_solid_primitive_legend_has_a_native_minimum_feature_witness(angle, shift, shape):
    b=board()
    p=pcbnew.PCB_SHAPE(b);p.SetLayer(pcbnew.B_SilkS)
    p.SetShape(pcbnew.SHAPE_T_CIRCLE if shape=='circle' else pcbnew.SHAPE_T_RECT)
    p.SetStart(pcbnew.VECTOR2I_MM(10,10))
    p.SetEnd(pcbnew.VECTOR2I_MM(10.2,10) if shape=='circle' else pcbnew.VECTOR2I_MM(11,10.4))
    p.SetWidth(pcbnew.FromMM(.12));p.SetFilled(True);b.Add(p)
    p.Rotate(pcbnew.VECTOR2I_MM(0,0), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    p.Move(pcbnew.VECTOR2I_MM(*shift))
    result=native.audit_legend(b,rules())
    if shape=='rectangle' and angle % 90:
        # KiCad materializes non-cardinal rectangles as native polygons.
        # Do not recast that unsupported ink from its bounding box.
        assert p.GetShape()==pcbnew.SHAPE_T_POLY
        assert result['complete'] is False and result['unsupported']
        return
    assert result['complete'],result
    assert not result['unsupported'] and not result['findings']
    assert result['inventory'][0]['feature_mm'] >= .39999
    assert result['inventory'][0]['feature_witness'].startswith('native_solid_')


@pytest.mark.parametrize('shape', ['circle','rectangle'])
def test_tiny_solid_primitive_legend_cannot_hide_behind_its_filled_flag(shape):
    b=board()
    p=pcbnew.PCB_SHAPE(b);p.SetLayer(pcbnew.F_SilkS)
    p.SetShape(pcbnew.SHAPE_T_CIRCLE if shape=='circle' else pcbnew.SHAPE_T_RECT)
    p.SetStart(pcbnew.VECTOR2I_MM(10,10))
    p.SetEnd(pcbnew.VECTOR2I_MM(10.02,10) if shape=='circle' else pcbnew.VECTOR2I_MM(11,10.04))
    p.SetWidth(0);p.SetFilled(True);b.Add(p)
    result=native.audit_legend(b,rules())
    assert result['complete'],result
    assert len(result['findings'])==1
    assert result['findings'][0]['dimension']=='feature_mm'
    assert result['findings'][0]['actual_mm']==pytest.approx(.04)


def test_degenerate_filled_silk_cannot_silently_pass_unproved_minimum_feature():
    b=board()
    p=pcbnew.PCB_SHAPE(b);p.SetLayer(pcbnew.B_SilkS);p.SetShape(pcbnew.SHAPE_T_RECT)
    p.SetStart(pcbnew.VECTOR2I_MM(10,10));p.SetEnd(pcbnew.VECTOR2I_MM(10,11));p.SetFilled(True);b.Add(p)
    result=native.audit_legend(b,rules())
    assert not result['complete']
    assert result['unsupported']


@pytest.mark.parametrize('field,value', [('silk',0),('silk',float('nan')),('silk_height',-1)])
def test_invalid_legend_floor_cannot_pass_an_empty_inventory(field,value):
    policy=rules();policy[field]=value
    result=native.audit_legend(board(),policy)
    assert result['complete'] is False
