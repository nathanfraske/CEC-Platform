"""Native C6 physical lands: identities are never collapsed by pin number."""
import copy
import pcbnew
import pytest
import cec_device_power_roles as roles


GROUND={'1','2','11','14'}|{str(n)for n in range(36,54)}
NC={'4','7','21','32','33','34','35'}
FUNCTIONS={**{n:'GND'for n in GROUND},**{n:'NC'for n in NC},
    '3':'3V3','8':'EN','5':'IO2','6':'IO3','9':'IO4','10':'IO5',
    '12':'IO0','13':'IO1','15':'IO6','16':'IO7','17':'IO12','18':'IO13',
    '19':'IO14','20':'IO15','22':'IO8','23':'IO9','24':'IO18','25':'IO19',
    '26':'IO20','27':'IO21','28':'IO22','29':'IO23','30':'RXD0','31':'TXD0'}


def fixture(quarter=0,back=False):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);board.Add(fp)
    fp.SetReference('arbitrary_radio_'+str(quarter));fp.SetPosition(pcbnew.VECTOR2I_MM(31.7,24.3))
    fp.SetValue('ESP32-C6-MINI-1-N4');fp.SetField('MPN','ESP32-C6-MINI-1-N4')
    fp.SetField('Manufacturer','Espressif Systems')
    fp.SetFPID(pcbnew.LIB_ID('unrelated_vendor','ESP32-C6-MINI-1'))
    nets={}
    for number in range(1,54):
        name='GND'if str(number)in GROUND else '/opaque_source_'+str(number)
        if name not in nets:nets[name]=pcbnew.NETINFO_ITEM(board,name);board.Add(nets[name])
        for physical in range(9 if number==49 else 1):
            p=pcbnew.PAD(fp);p.SetNumber(str(number));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.7,.7))
            p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(pcbnew.VECTOR2I_MM(
                20+(number%10)*1.7+physical*.8,15+(number//10)*1.9))
            p.SetNet(nets[name]);p.SetPinFunction(FUNCTIONS[str(number)])
            p.SetPinType('power_in'if str(number)in GROUND or number==3 else
                'no_connect'if str(number)in NC else 'input'if number==8 else 'bidirectional')
            fp.Add(p)
    fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    return board,fp


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_renamed_cardinal_native_map_keeps_every_physical_land(quarter,back):
    _,fp=fixture(quarter,back);model=roles.footprint_contract(fp)
    native=list(fp.Pads());before=[(p.m_Uuid.AsString(),tuple(p.GetPosition()))for p in native]
    result=roles.physical_pinmap(fp,model)
    assert set(result)=={str(n)for n in range(1,54)}
    assert len(result['49'])==9 and sum(map(len,result.values()))==61
    assert len({p.m_Uuid.AsString()for lands in result.values()for p in lands})==61
    assert sum(len(result[n])for n in GROUND)==30
    assert all(type(lands)is tuple for lands in result.values())
    assert before==[(p.m_Uuid.AsString(),tuple(p.GetPosition()))for p in fp.Pads()]
    assert model['native_pin_functions']==FUNCTIONS and model['common_domains']==[]
    assert model['physical_ground_land_counts']=={'49':9}


@pytest.mark.parametrize('fault',['wrong_part','wrong_package','wrong_mfr','missing_mpn','missing_mfr','missing_fpid'])
def test_exact_selected_manufacturer_identity_is_mandatory(fault):
    _,fp=fixture()
    if fault=='wrong_part':fp.SetValue('ESP32-C6-MINI-1-N8');fp.SetField('MPN','ESP32-C6-MINI-1-N8')
    elif fault=='wrong_package':fp.SetFPID(pcbnew.LIB_ID('RF_Module','ESP32-C6-MINI-1U'))
    elif fault=='wrong_mfr':fp.SetField('Manufacturer','different manufacturer')
    elif fault=='missing_mpn':fp.SetField('MPN','')
    elif fault=='missing_mfr':fp.SetField('Manufacturer','')
    else:fp.SetFPID(pcbnew.LIB_ID())
    with pytest.raises(ValueError):
        roles.physical_pinmap(fp,roles.footprint_contract(fp))


@pytest.mark.parametrize('number',['3','8','17','18','1','51','49'])
@pytest.mark.parametrize('action',['missing','duplicate'])
def test_missing_or_duplicate_nonaliased_land_and_ground49_count(number,action):
    _,fp=fixture();pad=next(p for p in fp.Pads()if p.GetNumber()==number)
    if action=='missing':fp.Remove(pad)
    else:
        extra=pcbnew.PAD(fp);extra.SetNumber(number);extra.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        extra.SetLayerSet(pad.GetLayerSet());extra.SetNet(pad.GetNet())
        extra.SetPinFunction(pad.GetPinFunction());extra.SetPinType(pad.GetPinType());fp.Add(extra)
    with pytest.raises(ValueError):roles.physical_pinmap(fp,roles.footprint_contract(fp))


@pytest.mark.parametrize('fault',['extra_number','ground_to_signal','signal_to_ground','zero_net',
    'wrong_function','wrong_type','other_face','through_hole','drilled_smd','duplicate_uuid'])
def test_native_label_net_face_drill_and_uuid_cannot_forge_the_manufacturer_map(fault):
    board,fp=fixture();pad=next(p for p in fp.Pads()if p.GetNumber()=='51')
    signal=next(p for p in fp.Pads()if p.GetNumber()=='17')
    if fault=='extra_number':pad.SetNumber('54')
    elif fault=='ground_to_signal':pad.SetNet(signal.GetNet())
    elif fault=='signal_to_ground':signal.SetNet(pad.GetNet())
    elif fault=='zero_net':pad.SetNetCode(0)
    elif fault=='wrong_function':pad.SetPinFunction('GPIO51')
    elif fault=='wrong_type':signal.SetPinType('output')
    elif fault=='other_face':
        layer=pcbnew.LSET();layer.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(layer)
    elif fault=='through_hole':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='drilled_smd':pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    else:pad.m_Uuid.Clone(pcbnew.KIID(signal.m_Uuid.AsString()))
    with pytest.raises(ValueError):roles.physical_pinmap(fp,roles.footprint_contract(fp))


def test_pin_catalog_grants_neither_numeric_power_nor_pair_routing_authority():
    _,fp=fixture();model=roles.footprint_contract(fp)
    assert model['pin_roles_do_not_supply_current_or_routing_authority'] is True
    assert model['pins']['3']=='power_input'
    assert model['pins']['17']==model['pins']['18']=='signal_io'
    assert not any(k in model for k in ('amps','current_contract','pair_contract','routing_layers'))
    forged=copy.deepcopy(model);forged['common_domains']=[{'name':'false-sharing','pins':['17','18']}]
    with pytest.raises(ValueError):roles.physical_pinmap(fp,forged)


@pytest.mark.parametrize('fault',['custom','circle','roundrect','zero_x','zero_y','negative_size',
    'offset_x','offset_y','internal_jumpers'])
@pytest.mark.parametrize('back',[False,True])
def test_literal_rectangular_positive_size_zero_offset_and_no_internal_jumpers(fault,back):
    _,fp=fixture(back=back);pad=next(p for p in fp.Pads()if p.GetNumber()=='49')
    if fault=='custom':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='circle':pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    elif fault=='roundrect':pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    elif fault=='zero_x':pad.SetSize(pcbnew.VECTOR2I(0,700000))
    elif fault=='zero_y':pad.SetSize(pcbnew.VECTOR2I(700000,0))
    elif fault=='negative_size':pad.SetSize(pcbnew.VECTOR2I(-1,700000))
    elif fault=='offset_x':pad.SetOffset(pcbnew.VECTOR2I(1,0))
    elif fault=='offset_y':pad.SetOffset(pcbnew.VECTOR2I(0,1))
    else:fp.SetDuplicatePadNumbersAreJumpers(True)
    with pytest.raises(ValueError):roles.physical_pinmap(fp,roles.footprint_contract(fp))


def test_pure_manufacturer_table_without_footprint_stays_metadata_only():
    model=roles.contract('ESP32-C6-MINI-1-N4')
    assert model and model['pin_roles_do_not_supply_current_or_routing_authority']
    assert model['common_domains']==[]


@pytest.mark.parametrize('number',['3','8','17','18','4','49'])
@pytest.mark.parametrize('fault',['zero_net','function','type'])
def test_each_role_category_requires_its_literal_native_name_type_and_net(number,fault):
    _,fp=fixture();pad=next(p for p in fp.Pads()if p.GetNumber()==number)
    if fault=='zero_net':pad.SetNetCode(0)
    elif fault=='function':pad.SetPinFunction('a_plausible_but_wrong_label')
    else:pad.SetPinType('passive')
    with pytest.raises(ValueError):roles.physical_pinmap(fp,roles.footprint_contract(fp))


def test_unknown_catalog_and_legacy_unique_number_rule_remain_fail_closed():
    _,fp=fixture();fp.SetValue('Unknown-53-pin-part');fp.SetField('MPN','Unknown-53-pin-part')
    with pytest.raises(ValueError):roles.physical_pinmap(fp,roles.footprint_contract(fp))
    fp.SetValue('TLV7011DBVR');fp.SetField('MPN','TLV7011DBVR')
    fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-5'))
    for p in list(fp.Pads()):
        if p.GetNumber()not in ('1','2','3','4','5'):fp.Remove(p)
    model=roles.footprint_contract(fp);assert model
    assert roles.physical_pinmap(fp,model)
    extra=pcbnew.PAD(fp);extra.SetNumber('3');fp.Add(extra)
    with pytest.raises(ValueError,match='unaliased'):roles.physical_pinmap(fp,model)
