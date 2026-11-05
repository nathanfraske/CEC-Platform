"""A saved local process rule owns an exact SMD dogbone, not a free field."""
import json
import os
from pathlib import Path

import pcbnew
import pytest
import cec_existing_local_pofv_pad_rule as rule
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_drc_runner as native
from test_existing_local_pofv_pad_rule import case


def proposal(pad, angle=0, face=pcbnew.F_Cu):
    dx,dy=((750000,0),(0,-750000),(-750000,0),(0,750000))[angle//90]
    at=pad.GetPosition()+pcbnew.VECTOR2I(dx,dy)
    return at,dict(pad=pad,start=pad.GetPosition(),layer=face)


def seat(board,pad,at,context,**kwargs):
    return fr._via_spot_clear(board,at,300000,200000,{pad.GetNetCode()},
        drill_nm=200000,net_code=pad.GetNetCode(),local_pofv_dogbone=context,**kwargs)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('profile',['jlcpcb_6l_pofv_signal','jlcpcb_6l_pofv_high_current'])
def test_saved_dogbone_context_preserves_the_real_rule_and_board_floors(tmp_path,angle,face,profile):
    board,source,pad=case(tmp_path,angle,face,profile);at,context=proposal(pad,angle,face)
    raw=source.read_bytes();floors=rule._floors(board);before=force._sidecars(source)
    assert not fr._via_spot_clear(board,at,300000,200000,{pad.GetNetCode()},
        drill_nm=200000,net_code=pad.GetNetCode())
    detail={};assert seat(board,pad,at,context,report=detail),detail
    proof=detail['existing_native_local_pad_rule']
    assert proof['bounded_source_smd_dogbone']['layer_id']==face
    assert proof['bounded_source_smd_dogbone']['start_nm']==list(pad.GetPosition())
    assert proof['bounded_source_smd_dogbone']['end_nm']==list(at)
    assert not proof['fabrication_or_current_or_release_qualified']
    assert source.read_bytes()==raw and force._sidecars(source)==before and rule._floors(board)==floors


@pytest.mark.parametrize('fault',['far','offpad_start','wrong_face','partial_overlap','inside_pad',
    'noncanonical','missing_start','extra_key','wrong_pad','changed_pad','missing_rule',
    'missing_group','locked_group','profile','mutated_floor','wrong_drill'])
def test_dogbone_context_is_not_an_offpad_or_profile_only_floor_waiver(tmp_path,fault):
    board,source,pad=case(tmp_path);at,context=proposal(pad)
    if fault=='far':at+=pcbnew.VECTOR2I(1000000,0)
    elif fault=='offpad_start':context['start']=pad.GetPosition()+pcbnew.VECTOR2I(300000,0)
    elif fault=='wrong_face':context['layer']=pcbnew.B_Cu
    elif fault=='partial_overlap':at=pad.GetPosition()+pcbnew.VECTOR2I(250000,0)
    elif fault=='inside_pad':at=pad.GetPosition()
    elif fault=='noncanonical':at+=pcbnew.VECTOR2I(0,1)
    elif fault=='missing_start':context.pop('start')
    elif fault=='extra_key':context['waive']=True
    elif fault=='wrong_pad':context['pad']=next(p for f in board.GetFootprints() for p in f.Pads() if p.GetNumber()=='3')
    elif fault=='changed_pad':pad.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='missing_rule':source.with_suffix('.kicad_dru').unlink()
    elif fault=='missing_group':
        group=next(g for g in board.Groups() if g.GetName()==rule.GROUP)
        for item in list(group.GetItems()):group.RemoveItem(item)
        board.Remove(group)
    elif fault=='locked_group':next(g for g in board.Groups() if g.GetName()==rule.GROUP).SetLocked(True)
    elif fault=='profile':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='unknown';board.SetProperties(props)
    elif fault=='mutated_floor':board.GetDesignSettings().m_ViasMinSize+=1
    floors=rule._floors(board);raw=source.read_bytes()
    if fault=='wrong_drill':
        assert not fr._via_spot_clear(board,at,300000,200000,{pad.GetNetCode()},
            drill_nm=100000,net_code=pad.GetNetCode(),local_pofv_dogbone=context)
    else:assert not seat(board,pad,at,context)
    assert source.read_bytes()==raw and rule._floors(board)==floors


@pytest.mark.parametrize('fault',['extra_exemption','pad_context','existing_hole','native_padstack'])
def test_local_dogbone_context_is_exclusive(tmp_path,fault):
    board,source,pad=case(tmp_path);at,context=proposal(pad)
    kwargs={}
    if fault=='pad_context':kwargs['local_pofv_pad']=pad
    elif fault=='existing_hole':kwargs['existing_via_uuid']='not-a-source-hole'
    elif fault=='native_padstack':kwargs['native_padstack_via']=next(iter(board.GetTracks()))
    if fault=='extra_exemption':
        assert not fr._via_spot_clear(board,at,300000,200000,{pad.GetNetCode(),board.FindNet('obstruction').GetNetCode()},
            drill_nm=200000,net_code=pad.GetNetCode(),local_pofv_dogbone=context)
    else:assert not seat(board,pad,at,context,**kwargs)


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.In3_Cu,pcbnew.In4_Cu,pcbnew.B_Cu])
def test_owned_dogbone_still_checks_foreign_copper_on_every_enabled_face(tmp_path,layer):
    board,source,pad=case(tmp_path);at,context=proposal(pad)
    assert seat(board,pad,at,context)
    edge=pcbnew.PCB_TRACK(board);edge.SetLayer(layer);edge.SetNet(board.FindNet('obstruction'))
    edge.SetWidth(200000);edge.SetStart(at-pcbnew.VECTOR2I(0,500000));edge.SetEnd(at+pcbnew.VECTOR2I(0,500000));board.Add(edge)
    detail={};assert not seat(board,pad,at,context,report=detail)
    assert detail['reason']=='foreign copper excludes via land'
    assert detail['blockers'] and detail['blockers'][0]['net']=='obstruction'


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_saved_dogbone_native_rule_needs_membership_and_live_copper_owner(tmp_path,face):
    board,source,pad=case(tmp_path,face=face);at,context=proposal(pad,face=face)
    assert seat(board,pad,at,context)
    edge=pcbnew.PCB_TRACK(board);edge.SetLayer(face);edge.SetNet(pad.GetNet());edge.SetWidth(200000)
    edge.SetStart(context['start']);edge.SetEnd(at);board.Add(edge)
    via=pcbnew.PCB_VIA(board);via.SetNet(pad.GetNet());via.SetPosition(at)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetWidth(300000);via.SetDrill(200000);board.Add(via)
    assert fab.local_pofv_via_decision(board,via)==(True,'bounded same-layer SMD dogbone')
    evidence=fr.group_local_pofv_signal_vias(board,[via]);assert evidence
    child=force._copy_family(source,tmp_path/'owned');field._save_field_snapshot(board,child)
    assert source.with_suffix('.kicad_dru').read_bytes()==child.with_suffix('.kicad_dru').read_bytes()
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('native factory rule control requires explicit native reporting build')
    def faults(path,label):
        output=tmp_path/(label+'.json');result=native.run(path,output,reporting_build=Path(build),timeout_s=10.)
        assert result['ok'] and result['complete'] and not result['native_inventory']['potentially_truncated']
        return {q['type'] for q in json.loads(output.read_text())['violations']
            if q['type'] in ('via_diameter','drill_out_of_range','annular_width')
            and any(item.get('uuid')==force._uid(via) for item in q['items'])}
    assert not faults(child,'with-existing-membership')
    fresh=pcbnew.LoadBoard(str(child));actual=next(v for v in fresh.GetTracks() if force._uid(v)==force._uid(via))
    next(g for g in fresh.Groups() if g.GetName()==rule.GROUP).RemoveItem(actual)
    control=force._copy_family(child,tmp_path/'outside');field._save_field_snapshot(fresh,control)
    assert faults(control,'without-membership')=={'via_diameter','drill_out_of_range','annular_width'}
