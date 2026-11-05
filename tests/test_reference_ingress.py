"""A positive scalar reference witness never exempts loaded or paired nets."""
import pcbnew
import pytest
from unittest import mock

import cec_reference_ingress as ingress
import cec_fr as fr
import cec_force_current as force
import cec_field_coupling as field


def fixture(tmp_path, *, vendored=False):
    b=pcbnew.BOARD();b.SetFileName(str(tmp_path/'arbitrary-reference.kicad_pcb'))
    names=('/arbitrary SENSE context/5V_REFERENCE','ADC_FILTER','GND','OTHER_SUPPLY')
    nets={}
    for n in names:
        nets[n]=pcbnew.NETINFO_ITEM(b,n);b.Add(nets[n])
    def part(ref,value,lib,item,pins,mpn=None,maker=None,drilled=False):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value)
        fp.SetFPID(pcbnew.LIB_ID(('cec-' if vendored else '')+lib,item));b.Add(fp)
        if mpn:fp.SetField('MPN',mpn)
        if maker:fp.SetField('Manufacturer',maker)
        for pin,net in pins:
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(nets[net])
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
            p.SetPosition(pcbnew.VECTOR2I_MM(int(pin)*2,2*len(list(b.GetFootprints()))))
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if drilled else pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.PTHMask() if drilled else pcbnew.PAD.SMDMask())
            if drilled:p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
            fp.Add(p)
        return fp
    top=part('TOP_RANDOM','47k','Resistor_SMD','R_0402_1005Metric',[
        ('1',names[0]),('2',names[1])],'0402WGF4702TCE')
    bottom=part('BOTTOM_RANDOM','10k','Resistor_SMD','R_0402_1005Metric',[
        ('1',names[1]),('2','GND')],'0402WGF1002TCE')
    connector=part('PORT_RANDOM','JST','Connector_JST','JST_PH_1x02',[
        ('1',names[0]),('2','GND')],drilled=True)
    esd=part('CLAMP_RANDOM','PESD5V0S1BA','Diode_SMD','D_SOD-323',[
        ('1',names[0]),('2','GND')],'PESD5V0S1BA','HXY MOSFET')
    device=part('INPUT_RANDOM','TLV7011DBVR','Package_TO_SOT_SMD','SOT-23-5',[
        ('1','OTHER_SUPPLY'),('2','GND'),('3',names[1]),('4','OTHER_SUPPLY'),('5','OTHER_SUPPLY')],
        'TLV7011DBVR')
    return b,names[0],top,bottom,connector,esd,device


@pytest.mark.parametrize('vendored',[False,True])
@pytest.mark.parametrize('angle,back',[(0,False),(90,True),(180,False)])
def test_scalar_reference_is_typed_without_new_voltage_or_load(tmp_path,vendored,angle,back):
    b,net,*parts=fixture(tmp_path,vendored=vendored)
    for fp in parts:
        fp.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if back:fp.Flip(pcbnew.VECTOR2I_MM(10,10),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    before=field._field_snapshot_inventory(b)
    q=ingress.source_contract(b,net)
    assert q and q['role']=='native_closed_scalar_reference_ingress'
    assert not q['numeric_load_or_rail_budget_modified'] and not q['gpio_high_impedance_assumed']
    assert not q['whole_current_or_precision_net_ownership_overridden']
    assert before==field._field_snapshot_inventory(b)
    with mock.patch('cec_synth_pipeline.spec_net_current_contract',return_value=None):
        assert net in fr._ordinary_final_completion_nets(b,lambda net:{'track_width':.2})
        assert net not in fr._ordinary_final_completion_nets(b,lambda net:{'track_width':.5})


@pytest.mark.parametrize('fault',['top_unknown','top_contradiction','top_dnp','bottom_unknown',
    'bottom_not_ground','clamp_unknown','clamp_maker','clamp_package','clamp_not_ground',
    'connector_unknown','connector_dnp','unplated','extra_external','extra_downstream',
    'device_output','device_dnp'])
def test_unqualified_or_loaded_topology_retains_conservative_exclusion(tmp_path,fault):
    b,net,top,bottom,conn,esd,device=fixture(tmp_path)
    if fault=='top_unknown':top.SetField('MPN','UNSPECIFIED')
    if fault=='top_contradiction':top.SetValue('1k')
    if fault=='top_dnp':top.SetDNP(True)
    if fault=='bottom_unknown':bottom.SetField('MPN','UNSPECIFIED')
    if fault=='bottom_not_ground':bottom.FindPadByNumber('2').SetNet(b.FindNet('OTHER_SUPPLY'))
    if fault=='clamp_unknown':esd.SetField('MPN','UNSPECIFIED')
    if fault=='clamp_maker':esd.SetField('Manufacturer','UNSPECIFIED')
    if fault=='clamp_package':esd.SetFPID(pcbnew.LIB_ID('Diode_SMD','SMA'))
    if fault=='clamp_not_ground':esd.FindPadByNumber('2').SetNet(b.FindNet('OTHER_SUPPLY'))
    if fault=='connector_unknown':conn.SetFPID(pcbnew.LIB_ID('Unknown','Unknown'))
    if fault=='connector_dnp':conn.SetDNP(True)
    if fault=='unplated':conn.FindPadByNumber('1').SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    if fault.startswith('extra_'):
        p=pcbnew.PAD(conn);p.SetNumber('77');p.SetNet(b.FindNet(net if fault=='extra_external' else 'ADC_FILTER'))
        conn.Add(p)
    if fault=='device_output':device.FindPadByNumber('3').SetNumber('7')
    if fault=='device_dnp':device.SetDNP(True)
    before=field._field_snapshot_inventory(b)
    assert ingress.source_contract(b,net) is None
    with mock.patch('cec_synth_pipeline.spec_net_current_contract',return_value=None):
        assert net not in fr._ordinary_final_completion_nets(b,lambda net:{'track_width':.2})
    assert before==field._field_snapshot_inventory(b)


def test_positive_reference_cannot_override_whole_current_or_kelvin_identity(tmp_path):
    b,net,*_=fixture(tmp_path)
    with mock.patch('cec_synth_pipeline.spec_net_current_contract',return_value={'amps':2.}):
        assert net not in fr._ordinary_final_completion_nets(b,lambda net:{'track_width':.2})
    with mock.patch.object(fr,'_board_kelvin_pairs',return_value=[(net,'OTHER_SUPPLY')]):
        assert net not in fr._ordinary_final_completion_nets(b,lambda net:{'track_width':.2})


@pytest.mark.parametrize('bound',[True,0,-1,11,float('inf')])
def test_unknown_bounds_refuse(tmp_path,bound):
    b,net,*_=fixture(tmp_path)
    with pytest.raises(ValueError):ingress.source_contract(b,net,timeout_s=bound)
