"""Netclass-only pin escapes never reduce actual whole-source current."""
import math

import pcbnew
import pytest

import cec_fr as fr
import cec_full_current_supply_prefix as receiver
from test_supply_retained_plated_throat import fixture


def example(**kwargs):
    board, launch, landing, via, trunk, raw = fixture(**kwargs)
    layer = trunk.GetLayer()
    layer = pcbnew.B_Cu if layer == pcbnew.F_Cu else pcbnew.F_Cu
    prefix = pcbnew.PCB_TRACK(board); prefix.SetStart(launch.GetPosition())
    prefix.SetEnd(via.GetPosition()); prefix.SetLayer(layer)
    prefix.SetWidth(raw['required_by_layer_nm'][layer]); prefix.SetNet(launch.GetNet())
    board.Add(prefix)
    group = pcbnew.PCB_GROUP(board); group.SetName(fr.ENDPOINT_NECKDOWN_GROUP)
    board.Add(group); group.AddItem(prefix)
    names = tuple(board.GetLayerName(l) for l in board.GetEnabledLayers().CuStack()
        if l not in (pcbnew.In1_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu))
    contract = dict(current_authority=dict(raw['current_authority']),
        profile='jlcpcb_6l_pofv_signal', authority_refs=['native_source_domain'],
        routing_layers=names, required_by_layer_mm={n: max(1.,
            raw['required_by_layer_nm'][board.GetLayerID(n)] / 1e6) for n in names})
    return board, launch, via, trunk, prefix, {str(launch.GetNetname()): contract}


def check(board, via, prefix, contracts, **kwargs):
    return receiver.receive(board, contracts,
        track_uuid_scope=[prefix.m_Uuid.AsString()],
        retained_via_uuids=[via.m_Uuid.AsString()], **kwargs)


@pytest.mark.parametrize('back,angle,netname,ref', [(False, 0, 'SUPPLY_A', 'A'),
    (False, 90, '/other/SUPPLY_B', 'B'), (True, 180, 'RENAMED_C', 'C'),
    (True, 270, '/unused/RENAMED_D', 'D')])
def test_whole_current_class_only_escape_is_independently_reproved(back, angle, netname, ref):
    board, launch, via, trunk, prefix, contracts = example(
        back=back, angle=angle, netname=netname, ref=ref)
    before = {t.m_Uuid.AsString() for t in board.GetTracks()}
    result = check(board, via, prefix, contracts)
    assert result['complete'] and result['track_uuids'] == [prefix.m_Uuid.AsString()]
    proof = result['proofs'][0]
    assert prefix.GetWidth() >= proof['actual_whole_current_floor_nm']
    assert proof['unchanged_class_width_nm'] > prefix.GetWidth()
    assert proof['current_authority'] == next(iter(contracts.values()))['current_authority']
    assert proof['full_width_throat_uuids'] == [trunk.m_Uuid.AsString()]
    assert not result['current_budget_lowered'] and not result['barrel_capacity_qualified']
    assert before == {t.m_Uuid.AsString() for t in board.GetTracks()}


@pytest.mark.parametrize('fault', ['below_current', 'too_long', 'untyped',
    'sense_pin', 'dnp', 'no_group', 'no_pofv_group', 'no_throat',
    'thin_throat', 'inner_under_current', 'new_via_not_retained', 'no_authority',
    'no_margin', 'bool_current', 'wrong_profile', 'no_source_refs', 'plane_route'])
def test_no_labels_or_class_exception_can_waive_current_or_owned_throat(fault):
    board, launch, via, trunk, prefix, contracts = example()
    contract = next(iter(contracts.values()))
    if fault == 'below_current': prefix.SetWidth(prefix.GetWidth() - 1)
    if fault == 'too_long': prefix.SetStart(pcbnew.VECTOR2I_MM(8, 10))
    if fault == 'untyped': launch.GetParentFootprint().SetValue('UNKNOWN')
    if fault == 'sense_pin': launch.SetNumber('3')
    if fault == 'dnp': launch.GetParentFootprint().SetDNP(True)
    if fault == 'no_group': prefix.GetParentGroup().RemoveItem(prefix)
    if fault == 'no_pofv_group': via.GetParentGroup().RemoveItem(via)
    if fault == 'no_throat': board.Remove(trunk)
    if fault == 'thin_throat': trunk.SetWidth(900000)
    if fault == 'inner_under_current': trunk.SetLayer(pcbnew.In2_Cu)
    if fault == 'no_authority': contract['current_authority'] = {}
    if fault == 'no_margin': contract['current_authority'].pop('margin_included')
    if fault == 'bool_current': contract['current_authority']['amps'] = True
    if fault == 'wrong_profile': contract['profile'] = 'other_profile'
    if fault == 'no_source_refs': contract['authority_refs'] = []
    if fault == 'plane_route': contract['routing_layers'] = ('In1.Cu',)
    if fault == 'new_via_not_retained':
        result = receiver.receive(board, contracts,
            track_uuid_scope=[prefix.m_Uuid.AsString()], retained_via_uuids=[])
    else:
        result = check(board, via, prefix, contracts)
    assert result['complete'] and not result['track_uuids']


@pytest.mark.parametrize('seconds', [0, -1, True, math.inf, math.nan, 10.1])
def test_receiving_is_bounded_and_cannot_mutate_source(seconds):
    board, _, via, _, prefix, contracts = example()
    with pytest.raises(ValueError, match='bounded_full_current_prefix'):
        check(board, via, prefix, contracts, timeout_s=seconds)


def ceramic(board, launch):
    fp=launch.GetParentFootprint();fp.SetValue('100nF')
    fp.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0402_1005Metric'));launch.SetNumber('1')
    ground=pcbnew.NETINFO_ITEM(board,'GND');board.Add(ground)
    pad=pcbnew.PAD(fp);pad.SetNumber('2');pad.SetNet(ground);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(launch.GetSize());pad.SetLayerSet(launch.GetLayerSet())
    pad.SetPosition(launch.GetPosition()+pcbnew.VECTOR2I_MM(0,2));fp.Add(pad)
    return pad


@pytest.mark.parametrize('back,angle',[(False,0),(False,90),(True,180),(True,270)])
def test_grounded_ceramic_prefix_still_carries_entire_unchanged_source_current(back,angle):
    board,launch,via,trunk,prefix,contracts=example(back=back,angle=angle,
        netname='/renamed/SHARED_RAIL',ref='ARBITRARY_SHUNT')
    ceramic(board,launch)
    result=check(board,via,prefix,contracts)
    assert result['complete'] and result['track_uuids']==[prefix.m_Uuid.AsString()]
    proof=result['proofs'][0]
    assert set(proof['launch_terminal_roles'].values())=={'value_qualified_grounded_ceramic_supply_terminal'}
    assert prefix.GetWidth()>=proof['actual_whole_current_floor_nm']
    assert not result['current_budget_lowered'] and not result['barrel_capacity_qualified']


@pytest.mark.parametrize('fault',['rail_to_rail','resistor','unknown_value','dnp','three_pads',
    'tht','wrong_face','below_current','long_prefix','no_throat','ground_terminal'])
def test_a_passive_label_is_not_supply_prefix_authority(fault):
    board,launch,via,trunk,prefix,contracts=example();ground=ceramic(board,launch)
    fp=launch.GetParentFootprint()
    if fault=='rail_to_rail':
        other=pcbnew.NETINFO_ITEM(board,'OTHER_RAIL');board.Add(other);ground.SetNet(other)
    if fault=='resistor':fp.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0402_1005Metric'));fp.SetValue('10k')
    if fault=='unknown_value':fp.SetValue('UNSPECIFIED')
    if fault=='dnp':fp.SetDNP(True)
    if fault=='three_pads':fp.Add(pcbnew.PAD(fp))
    if fault=='tht':launch.SetAttribute(pcbnew.PAD_ATTRIB_PTH);launch.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    if fault=='wrong_face':
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);layers.AddLayer(pcbnew.B_Mask);ground.SetLayerSet(layers)
    if fault=='below_current':prefix.SetWidth(prefix.GetWidth()-1)
    if fault=='long_prefix':prefix.SetStart(pcbnew.VECTOR2I_MM(8,10))
    if fault=='no_throat':board.Remove(trunk)
    if fault=='ground_terminal':
        assert receiver.supply_terminal_role(ground) is None
        return
    result=check(board,via,prefix,contracts)
    assert result['complete'] and not result['track_uuids']


def manufacturer_bridge(board,launch,*,owner_value='TJA1051T/3',wrong_pin=False):
    peer=ceramic(board,launch)
    other=pcbnew.NETINFO_ITEM(board,'RENAMED_OTHER_SUPPLY');board.Add(other);peer.SetNet(other)
    owner=pcbnew.FOOTPRINT(board);owner.SetReference('RENAMED_OWNER')
    owner.SetValue(owner_value);owner.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
    board.Add(owner)
    for number,net in [('3',launch.GetNet()),('5' if not wrong_pin else '6',peer.GetNet())]:
        pad=pcbnew.PAD(owner);pad.SetNumber(number);pad.SetNet(net)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.6,1.));pad.SetLayerSet(launch.GetLayerSet())
        pad.SetPosition(launch.GetPosition()+pcbnew.VECTOR2I_MM(1.,float(number)))
        owner.Add(pad)
    return peer,owner


@pytest.mark.parametrize('back,angle,netname,ref',[
    (False,0,'SUPPLY_ALIAS_A','SHUNT_A'),(False,90,'/scope/RAIL_B','SHUNT_B'),
    (True,180,'RENAMED_C','SHUNT_C'),(True,270,'/renamed/D','SHUNT_D')])
def test_modeled_two_supply_emc_prefix_preserves_the_entire_source_budget(back,angle,netname,ref):
    board,launch,via,trunk,prefix,contracts=example(back=back,angle=angle,netname=netname,ref=ref)
    manufacturer_bridge(board,launch)
    before={t.m_Uuid.AsString() for t in board.GetTracks()}
    result=check(board,via,prefix,contracts)
    assert result['complete'] and result['track_uuids']==[prefix.m_Uuid.AsString()]
    proof=result['proofs'][0]
    assert set(proof['launch_terminal_roles'].values())=={'manufacturer_supply_to_supply_bypass_terminal'}
    assert prefix.GetWidth()>=proof['actual_whole_current_floor_nm']
    assert proof['current_authority']==next(iter(contracts.values()))['current_authority']
    assert before=={t.m_Uuid.AsString() for t in board.GetTracks()}
    assert not result['current_budget_lowered'] and not result['barrel_capacity_qualified']


@pytest.mark.parametrize('fault',['no_owner','unmodeled_variant','wrong_pin','different_net',
    'wrong_package','wrong_value','owner_dnp','ambiguous_owner','below_current','long_prefix','no_throat'])
def test_two_supply_cap_label_cannot_invent_manufacturer_or_source_authority(fault):
    board,launch,via,trunk,prefix,contracts=example()
    peer,owner=manufacturer_bridge(board,launch)
    if fault=='no_owner':board.Remove(owner)
    elif fault=='unmodeled_variant':owner.SetValue('TJA1051T/E')
    elif fault=='wrong_pin':next(p for p in owner.Pads() if p.GetNumber()=='5').SetNumber('6')
    elif fault=='different_net':next(p for p in owner.Pads() if p.GetNumber()=='5').SetNet(launch.GetNet())
    elif fault=='wrong_package':owner.SetFPID(pcbnew.LIB_ID('Package_SO','TSSOP-8'))
    elif fault=='wrong_value':launch.GetParentFootprint().SetValue('10uF')
    elif fault=='owner_dnp':owner.SetDNP(True)
    elif fault=='ambiguous_owner':
        duplicate=owner.Duplicate(False);duplicate.m_Uuid.Clone(pcbnew.KIID());board.Add(duplicate)
    elif fault=='below_current':prefix.SetWidth(prefix.GetWidth()-1)
    elif fault=='long_prefix':prefix.SetStart(pcbnew.VECTOR2I_MM(8,10))
    elif fault=='no_throat':board.Remove(trunk)
    try:result=check(board,via,prefix,contracts)
    except ValueError:
        assert fault=='wrong_package'
        return
    assert result['complete'] and not result['track_uuids']
