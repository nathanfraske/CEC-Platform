"""Manufacturing legend corrections cannot move electrical/mechanical geometry."""
import hashlib
import json

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fab_check as fab
import cec_fab_native_geometry as native
import cec_legend_repair as repair


def rules():
    return fab.profile_rules(fab.PROFILES['jlcpcb'],1.,'jlcpcb_6l_pofv_signal')


def fixture(angle, shift):
    b=pcbnew.CreateEmptyBoard()
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('RENAMED123');fp.SetValue('arbitrary');b.Add(fp)
    fp.Value().SetVisible(False)
    text=fp.Reference();text.SetLayer(pcbnew.F_SilkS);text.SetVisible(True)
    text.SetTextSize(pcbnew.VECTOR2I_MM(.72,.8));text.SetTextThickness(pcbnew.FromMM(.12))
    text.SetPosition(pcbnew.VECTOR2I_MM(10,12));text.SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    pad=pcbnew.PAD(fp);pad.SetNumber('7');pad.SetSize(pcbnew.VECTOR2I_MM(.6,.8))
    pad.SetPosition(pcbnew.VECTOR2I_MM(10,10));fp.Add(pad)
    line=pcbnew.PCB_SHAPE(fp);line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetLayer(pcbnew.F_SilkS)
    line.SetStart(pcbnew.VECTOR2I_MM(9,9));line.SetEnd(pcbnew.VECTOR2I_MM(11,9));line.SetWidth(pcbnew.FromMM(.12));fp.Add(line)
    edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
    edge.SetStart(pcbnew.VECTOR2I_MM(0,0));edge.SetEnd(pcbnew.VECTOR2I_MM(20,0));edge.SetWidth(pcbnew.FromMM(.05));b.Add(edge)
    fp.Move(pcbnew.VECTOR2I_MM(*shift))
    return b,fp,text,pad,line,edge


@pytest.mark.parametrize('angle,shift',[(0,(0,0)),(45,(22,-13)),(90,(-5,20)),(137,(99,12))])
def test_only_visible_legend_dimensions_change_and_second_pass_is_noop(angle,shift):
    b,fp,text,pad,line,edge=fixture(angle,shift)
    protected=(fp.GetPosition(),fp.GetOrientationDegrees(),pad.GetPosition(),pad.GetSize(),
               edge.GetStart(),edge.GetEnd(),edge.GetWidth(),text.GetPosition(),text.GetTextAngle().AsDegrees(),
               text.GetText(),text.IsMirrored(),fp.Value().GetTextSize(),fp.Value().GetTextThickness())
    result=repair.repair_dimension_minima(b,rules())
    assert result['applied_count']==2,result
    assert result['dimension_findings_before']==3 and result['dimension_findings_after']==0
    assert result['release_authority'] is False
    assert line.GetWidth()==150000
    assert text.GetTextSize().y==1000000 and text.GetTextSize().x==900000
    assert protected==(fp.GetPosition(),fp.GetOrientationDegrees(),pad.GetPosition(),pad.GetSize(),
               edge.GetStart(),edge.GetEnd(),edge.GetWidth(),text.GetPosition(),text.GetTextAngle().AsDegrees(),
               text.GetText(),text.IsMirrored(),fp.Value().GetTextSize(),fp.Value().GetTextThickness())
    assert native.audit_legend(b,rules())['complete']
    assert repair.repair_dimension_minima(b,rules())['applied_count']==0


def test_locked_text_requires_explicit_graphic_authority():
    b,fp,text,pad,line,edge=fixture(0,(0,0));text.SetLocked(True)
    result=repair.repair_dimension_minima(b,rules())
    assert result['applied_count']==1 and text.GetTextSize().y==800000
    assert result['refused'][0]['reason']=='locked_legend_item'
    result=repair.repair_dimension_minima(b,rules(),allow_locked_graphic_uuids=[text.m_Uuid.AsString()])
    assert result['applied_count']==1 and text.GetTextSize().y==1000000


def test_budget_exhaustion_leaves_board_untouched():
    b,fp,text,pad,line,edge=fixture(0,(0,0))
    result=repair.repair_dimension_minima(b,rules(),timeout_s=0)
    assert not result['complete'] and result['applied_count']==0
    assert line.GetWidth()==120000 and text.GetTextSize().y==800000


def test_invalid_floor_does_not_partially_mutate_board():
    b,fp,text,pad,line,edge=fixture(0,(0,0))
    policy=rules();policy['silk_height']=float('nan')
    result=repair.repair_dimension_minima(b,policy)
    assert not result['complete'] and result['applied_count']==0
    assert line.GetWidth()==120000 and text.GetTextSize().y==800000
