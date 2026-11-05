"""Exact passive steering identity is not a bypass/load/pose permission."""
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest

import cec_device_power_roles as roles
import cec_measurement_leaf as leaf


def protector_fixture(quarter=0, mirror=False, face=pcbnew.F_Cu):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    nets={}
    for name in ('GND','/unrelated/data_a','/unrelated/data_b','/unrelated/clamp'):
        nets[name]=pcbnew.NETINFO_ITEM(b,name);b.Add(nets[name])
    def xy(point):
        x,y=point
        if mirror:x=30-x
        for _ in range(quarter):x,y=30-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference('ARBITRARY_PROTECTOR')
    fp.SetValue('USBLC6-2SC6');fp.SetFPID(pcbnew.LIB_ID('independent-library','SOT-23-6'))
    fp.SetField('MPN','USBLC6-2SC6');fp.SetField('Manufacturer','UMW');fp.SetField('LCSC','C2687116')
    fp.SetLayer(face);fp.SetOrientationDegrees(quarter*90);fp.SetPosition(xy((12,12)))
    points={'1':(10.9,11.05),'2':(10.9,12),'3':(10.9,12.95),
            '4':(13.1,12.95),'5':(13.1,12),'6':(13.1,11.05)}
    names={'1':'/unrelated/data_a','6':'/unrelated/data_a','3':'/unrelated/data_b',
           '4':'/unrelated/data_b','2':'GND','5':'/unrelated/clamp'}
    for pin,point in points.items():
        p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.8,.7))
        layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers)
        p.SetOrientationDegrees(quarter*90);p.SetNet(nets[names[pin]])
        fp.Add(p);p.SetPosition(xy(point))
    return b,fp,nets,xy


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_passive_bank_roles_survive_native_frames(quarter,mirror,face):
    b,fp,_,_=protector_fixture(quarter,mirror,face);before=leaf._binding(b)
    q=roles.passive_steering_protector_contract(fp)
    assert q and q['io_banks']==[['1','6'],['3','4']]
    assert q['pins']['2']=='ground' and q['pins']['5']=='clamp_reference'
    assert q['ground_pin']=='2' and q['clamp_reference_pin']=='5'
    assert q['internal_conduction_is_not_native_PCB_connection']
    assert not q['current_authority'] and not q['load_budget_declared']
    assert not q['bypass_owner'] and not q['pose_or_pair_reconstruction_authority']
    assert not q['release_authority'] and roles.footprint_contract(fp)is None
    assert leaf._binding(b)==before


@pytest.mark.parametrize('native_type',['','passive'])
@pytest.mark.parametrize('functions',[False,True])
def test_only_blank_or_matching_passive_native_metadata_is_accepted(native_type,functions):
    b,fp,_,_=protector_fixture()
    names={'1':'I/O1','6':'I/O1','3':'I/O2','4':'I/O2','2':'GND','5':'VBUS'}
    for p in fp.Pads():
        p.SetPinType(native_type)
        p.SetPinFunction(names[p.GetNumber()]if functions else'')
    assert roles.passive_steering_protector_contract(fp)


@pytest.mark.parametrize('fault',[
    'family','mpn','supplier','lcsc','package','package_suffix','missing_mpn','missing_supplier',
    'missing_lcsc','missing_pin','duplicate_pin','extra_pin','dnp','pth','hole','mixed_face',
    'multiface','unknown_net','wrong_ground','broken_bank_a','broken_bank_b','collapsed_banks',
    'clamp_ground','clamp_data','native_type','ground_type','clamp_power_type','native_function',
    'ground_function','clamp_function'])
def test_contradictory_identity_native_geometry_or_bank_nets_confer_no_contract(fault):
    b,fp,nets,_=protector_fixture();p=fp.FindPadByNumber('1')
    if fault=='family':fp.SetValue('USBLC6-2P6')
    elif fault=='mpn':fp.SetField('MPN','USBLC6-2P6')
    elif fault=='supplier':fp.SetField('Manufacturer','STMicroelectronics')
    elif fault=='lcsc':fp.SetField('LCSC','C9999999')
    elif fault=='package':fp.SetFPID(pcbnew.LIB_ID('independent-library','SOT-23-5'))
    elif fault=='package_suffix':fp.SetFPID(pcbnew.LIB_ID('independent-library','SOT-23-6_Custom'))
    elif fault=='missing_mpn':fp.SetField('MPN','')
    elif fault=='missing_supplier':fp.SetField('Manufacturer','')
    elif fault=='missing_lcsc':fp.SetField('LCSC','')
    elif fault=='missing_pin':fp.Remove(fp.FindPadByNumber('6'))
    elif fault=='duplicate_pin':fp.FindPadByNumber('6').SetNumber('1')
    elif fault=='extra_pin':
        q=p.Duplicate();q.m_Uuid.Clone(pcbnew.KIID());q.SetNumber('7');fp.Add(q)
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='pth':p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='hole':p.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='mixed_face':
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);p.SetLayerSet(layers)
    elif fault=='multiface':
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);layers.AddLayer(pcbnew.B_Cu);p.SetLayerSet(layers)
    elif fault=='unknown_net':p.SetNetCode(0)
    elif fault=='wrong_ground':fp.FindPadByNumber('2').SetNet(nets['/unrelated/clamp'])
    elif fault=='broken_bank_a':fp.FindPadByNumber('6').SetNet(nets['/unrelated/data_b'])
    elif fault=='broken_bank_b':fp.FindPadByNumber('4').SetNet(nets['/unrelated/data_a'])
    elif fault=='collapsed_banks':
        for pin in ('3','4'):fp.FindPadByNumber(pin).SetNet(nets['/unrelated/data_a'])
    elif fault=='clamp_ground':fp.FindPadByNumber('5').SetNet(nets['GND'])
    elif fault=='clamp_data':fp.FindPadByNumber('5').SetNet(nets['/unrelated/data_a'])
    elif fault=='native_type':p.SetPinType('input')
    elif fault=='ground_type':fp.FindPadByNumber('2').SetPinType('power_in')
    elif fault=='clamp_power_type':fp.FindPadByNumber('5').SetPinType('power_in')
    elif fault=='native_function':p.SetPinFunction('I/O2')
    elif fault=='ground_function':fp.FindPadByNumber('2').SetPinFunction('VSS')
    else:fp.FindPadByNumber('5').SetPinFunction('VDD')
    before=leaf._binding(b)
    assert roles.passive_steering_protector_contract(fp)is None
    assert leaf._binding(b)==before


def test_refdes_or_clamp_rail_name_is_not_identity_or_a_load_budget():
    b,fp,nets,_=protector_fixture();fp.SetReference('not_a_D_ref')
    renamed=pcbnew.NETINFO_ITEM(b,'+5V_POWER_LIKE_NAME');b.Add(renamed)
    fp.FindPadByNumber('5').SetNet(renamed)
    q=roles.passive_steering_protector_contract(fp)
    assert q and q['clamp_net']=='+5V_POWER_LIKE_NAME'
    assert q['pins']['5']=='clamp_reference' and not q['current_authority']
    assert roles.footprint_contract(fp)is None
