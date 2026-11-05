"""Unused-layer widths cannot replace exact saved via contact evidence."""
import copy
import time

import pcbnew
import pytest
import cec_native_supply_via_context as context
import cec_field_coupling as field
import cec_force_current as force
from test_retained_supply_port import fixture


def native_fixture(angle=0,back=False):
    board,roots,vias,tails,_ = fixture(angle=angle,back=back)
    via=vias[0];at=via.GetPosition();layer=pcbnew.F_Cu if back else pcbnew.B_Cu
    t=pcbnew.PCB_TRACK(board);t.SetStart(at);t.SetEnd(pcbnew.VECTOR2I(at.x+1000000,at.y))
    t.SetWidth(500000);t.SetLayer(layer);t.SetNetCode(via.GetNetCode());board.Add(t)
    contract=dict(net=str(via.GetNetname()),current_authority=dict(amps=3.,geometry_margin=1.25,
        margin_included=False,source='synthetic_unchanged_design_authority'),
        required_by_layer_mm={board.GetLayerName(l):.4000001 if l in (pcbnew.F_Cu,pcbnew.B_Cu)
            else 5.719034361 for l in board.GetEnabledLayers().CuStack()},
        routing_layers=[board.GetLayerName(l) for l in board.GetEnabledLayers().CuStack()])
    via.SetWidth(800001);via.SetDrill(400000)
    return board,via,contract


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,True),(270,True)])
def test_actual_outer_contacts_keep_complete_unchanged_current_obligation(angle,back):
    board,via,contract=native_fixture(angle,back);old=field._field_snapshot_inventory(board)
    before=copy.deepcopy(contract)
    result=context.receive(board,force._uid(via),contract)
    assert result['ok'] and result['complete']
    assert result['actual_contact_layers']==['B.Cu','F.Cu']
    assert result['source_required_local_web_nm']==400001
    assert result['unchanged_source_current_authority']==before['current_authority']
    assert len(result['unused_copper_layers_not_assumed_to_carry_current'])==4
    assert not result['plated_barrel_current_qualified'] and not result['electrical_or_thermal_qualified']
    assert not result['release_authority'] and not result['trace_width_obligation_changed']
    assert contract==before and field._field_snapshot_inventory(board)==old


@pytest.mark.parametrize('kind',['track','pad','filled_zone'])
def test_any_real_inner_contact_reinstates_that_layer_full_source_width(kind):
    board,via,contract=native_fixture();at=via.GetPosition()
    if kind=='track':
        item=pcbnew.PCB_TRACK(board);item.SetStart(at)
        item.SetEnd(pcbnew.VECTOR2I(at.x+1000000,at.y));item.SetWidth(200000)
        item.SetLayer(pcbnew.In2_Cu);item.SetNetCode(via.GetNetCode());board.Add(item)
    elif kind=='pad':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('ARBITRARY_INTERNAL_NATIVE_CONTACT');board.Add(fp)
        item=pcbnew.PAD(fp);item.SetNumber('1');item.SetNetCode(via.GetNetCode())
        item.SetAttribute(pcbnew.PAD_ATTRIB_SMD);item.SetPosition(at)
        item.SetSize(pcbnew.VECTOR2I_MM(1.,1.));item.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.In2_Cu);item.SetLayerSet(layers);fp.Add(item)
    else:
        item=pcbnew.ZONE(board);item.SetNet(via.GetNet());item.SetLayer(pcbnew.In2_Cu)
        poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for x,y in ((-1000000,-1000000),(1000000,-1000000),(1000000,1000000),(-1000000,1000000)):
            poly.Outline(0).Append(at.x+x,at.y+y)
        item.Outline().Append(poly)
        item.SetFilledPolysList(pcbnew.In2_Cu,poly);item.SetIsFilled(True);board.Add(item)
    result=context.receive(board,force._uid(via),contract)
    assert result['complete'] and not result['ok']
    assert result['source_required_local_web_nm']==5719035
    assert 'In2.Cu' in result['actual_native_contacts']


def test_one_nm_undersized_web_is_not_rounded_into_acceptance():
    board,via,contract=native_fixture();via.SetWidth(800000)
    result=context.receive(board,force._uid(via),contract)
    assert not result['ok'] and result['source_required_local_web_nm']==400001


@pytest.mark.parametrize('fault',['no_authority','bool_current','wrong_net','missing_layer',
    'unauthorized_contact','blind','no_second_contact','unfilled_zone'])
def test_missing_or_ambiguous_native_context_never_earns_an_exemption(fault):
    board,via,contract=native_fixture()
    if fault=='no_authority':contract['current_authority']={}
    elif fault=='bool_current':contract['current_authority']['amps']=True
    elif fault=='wrong_net':contract['net']='WRONG'
    elif fault=='missing_layer':contract['required_by_layer_mm'].pop('In2.Cu')
    elif fault=='unauthorized_contact':contract['routing_layers'].remove('B.Cu')
    elif fault=='blind':via.SetViaType(pcbnew.VIATYPE_BLIND);via.SetLayerPair(pcbnew.In1_Cu,pcbnew.B_Cu)
    elif fault=='no_second_contact':
        for t in list(board.GetTracks()):
            if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu:board.Remove(t)
    else:
        zone=pcbnew.ZONE(board);zone.SetNet(via.GetNet());zone.SetLayer(pcbnew.In2_Cu)
        zone.SetIsFilled(False);board.Add(zone)
    with pytest.raises(ValueError):context.receive(board,force._uid(via),contract)


@pytest.mark.parametrize('timeout',[0,True,float('nan'),11])
def test_only_finite_bounded_native_inventory_is_allowed(timeout):
    board,via,contract=native_fixture()
    with pytest.raises(ValueError):context.receive(board,force._uid(via),contract,timeout_s=timeout)
