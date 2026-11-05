"""Hardware-typed sense aliases stay sensitive, not ordinary or power-owned."""
import copy
import pcbnew
import pytest
import cec_sensitive_scalar_corner_stage as stage
import cec_sensitive_divider_role as divider
import cec_device_power_roles as roles
import cec_force_current as force
import cec_field_coupling as field
from test_sensitive_scalar_corner_stage import fixture as scalar_fixture
from test_field_proposals import add_net,track
from test_resistive_sensing_fanout import sensing_fixture


def fixture(tmp_path,*,quarter=0,mirror=False,face=pcbnew.F_Cu):
    net='/unrelated/VDD_ADC';b,source,edges,gpio,_=scalar_fixture(tmp_path,net=net,layer=face)
    for n in ('GND','annotated_source_rail'):add_net(b,n)
    corner,terminal=edges[0].GetEnd(),edges[1].GetEnd()
    at=pcbnew.VECTOR2I(corner.x+10*(terminal.x-corner.x),corner.y+10*(terminal.y-corner.y))
    edges[0].SetEnd(at);edges[1].SetStart(at)
    def land(fp,pin,name,xy,power=False):
        p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(b.FindNet(name));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
        layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers);p.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        if power:p.SetPinType('power_out')
        fp.Add(p);return p
    bottom=b.FindFootprintByReference('X2');bottom.SetValue('10kΩ');bottom.SetField('MPN','0402WGF1002TCE')
    bottom.SetFPID(pcbnew.LIB_ID('unrelated_library','R_0402_1005Metric'))
    land(bottom,'2','GND',(terminal.x/1e6+.96,terminal.y/1e6))
    top=pcbnew.FOOTPRINT(b);top.SetReference('arbitrary_top_resistor');top.SetValue('47kΩ')
    top.SetField('MPN','0402WGF4702TCE');top.SetFPID(pcbnew.LIB_ID('another_library','R_0402_1005Metric'));b.Add(top)
    land(top,'1','annotated_source_rail',(13.04,15));land(top,'2',net,(14,15))
    track(b,net,(14,15),(15,15),layer=face,width=.2)
    source_fp=pcbnew.FOOTPRINT(b);source_fp.SetReference('native_annotated_power');b.Add(source_fp)
    # A minimal native pin-role API fixture, not a qualified regulator or a
    # newly invented numerical source/load model. This rail is not edited.
    land(source_fp,'1','annotated_source_rail',(12.5,15),power=True)
    track(b,'annotated_source_rail',(12.5,15),(13.04,15),layer=face,width=.2)
    if mirror:
        for fp in b.GetFootprints():
            points={force._uid(p):tuple(p.GetPosition()) for p in fp.Pads()}
            fp.SetPosition(pcbnew.VECTOR2I(40000000-fp.GetPosition().x,fp.GetPosition().y))
            for p in fp.Pads():
                x,y=points[force._uid(p)];p.SetPosition(pcbnew.VECTOR2I(40000000-x,y))
        for t in b.GetTracks():
            s,z=t.GetStart(),t.GetEnd();t.SetStart(pcbnew.VECTOR2I(40000000-s.x,s.y));t.SetEnd(pcbnew.VECTOR2I(40000000-z.x,z.y))
    if quarter:
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings(),*b.Zones()]:
            item.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    field._save_field_snapshot(b,source)
    return b,source,net,gpio,top,bottom,source_fp,land


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_closed_divider_alias_has_exact_saved_sensitive_miter_and_no_current_claim(tmp_path,quarter,mirror,face):
    _,source,net,*_=fixture(tmp_path,quarter=quarter,mirror=mirror,face=face)
    b=pcbnew.LoadBoard(str(source));role=field.classify_net(net);assert role['power'] and role['victim']
    terminals=[p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()==net]
    graph=stage.fr._read_only_route_connectivity(b)
    reached={force._uid(p) for p in graph.GetConnectedItems(terminals[0])}|{force._uid(terminals[0])}
    assert {force._uid(p) for p in terminals}<=reached
    inv=stage.inventory(b,source,'synthetic',geometry_policy='right_angle_chamfer')
    assert len(inv['selected'])==1,inv
    witness=inv['source_sensitive_scalar_witnesses'][net][0]['source_closed_passive_divider']
    assert witness['every_native_node_terminal_accounted'] and not witness['current_budget_voltage_or_input_mode_inferred']
    made=stage.geometry.construct(b,inv['selected'],set(inv['source_sensitive_scalar_witnesses']),
        geometry_policy='right_angle_chamfer',allow_locked_source=True)
    assert made['chamfered']==1
    child=force._copy_family(source,tmp_path/'child');stage.additive._ground_refill(b);field._save_field_snapshot(b,child)
    r=stage.receive(source,child,made['retired_track_uuids'],board_hint='synthetic',allow_locked_source=True,
        geometry_policy='right_angle_chamfer')
    assert r['ok'] and r['complete'],r
    assert r['selected_geometry_findings_before_after']==[1,0] and r['native_source_contact_preservation']['ok']
    assert r['whole_source_current_receiving']['ok'] and r['physical_kelvin_preservation']['same_evidence']
    assert field.classify_net(net)==role and not r['ordinary_reclassification'] and not r['current_qualified']
    assert not r['GPIO_application_mode_or_current_authority_assumed'] and not r['release_authority']


@pytest.mark.parametrize('fault',['top_mpn','top_value','bottom_mpn','bottom_peer','top_peer','dnp','unowned_pad',
    'power_pin','extra_gpio','unknown_gpio','duplicate_gpio_pin','source_is_not_power','node_is_power'])
def test_power_like_name_never_substitutes_for_complete_positive_divider_topology(tmp_path,fault):
    b,source,net,gpio,top,bottom,source_fp,land=fixture(tmp_path)
    if fault=='top_mpn':top.SetField('MPN','UNKNOWN')
    elif fault=='top_value':top.SetValue('4.7kΩ')
    elif fault=='bottom_mpn':bottom.SetField('MPN','UNKNOWN')
    elif fault=='bottom_peer':bottom.FindPadByNumber('2').SetNet(b.FindNet('annotated_source_rail'))
    elif fault=='top_peer':top.FindPadByNumber('1').SetNet(b.FindNet('GND'))
    elif fault=='dnp':top.SetDNP(True)
    elif fault=='unowned_pad':land(source_fp,'spurious',net,(24,24))
    elif fault=='power_pin':next(iter(gpio.Pads())).SetPinType('power_in')
    elif fault=='extra_gpio':land(gpio,'6',net,(24,24))
    elif fault=='unknown_gpio':gpio.SetField('MPN','UNKNOWN')
    elif fault=='duplicate_gpio_pin':land(gpio,'5',net,(24,24))
    elif fault=='source_is_not_power':source_fp.FindPadByNumber('1').SetPinType('')
    elif fault=='node_is_power':land(source_fp,'spurious',net,(24,24),power=True)
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    assert net not in stage.eligible_nets(b,source,'synthetic')
    assert field.classify_net(net)['power'] and field.classify_net(net)['victim']


@pytest.mark.parametrize('pin',['4','5','6','7','8','9','10','11','12','15','17','18','19','20','21','22','38','39'])
def test_s3_adc_capable_pin_role_reuses_existing_complete_manufacturer_contract(tmp_path,pin):
    _,_,_,_,_,adc,*_=sensing_fixture(tmp_path)
    # Bind the selected native signal to this tested GPIO while preserving
    # the module's complete manufacturer pad-number and ground inventory.
    previous=adc.FindPadByNumber('17');target=adc.FindPadByNumber(pin)
    old_net=previous.GetNet();previous.SetNet(adc.FindPadByNumber('16').GetNet());target.SetNet(old_net)
    q=roles.scalar_gpio_pin(adc,pin);contract=roles.resistive_sensing_endpoint_contract(adc,pin)
    assert q and q['function']==contract['function'] and q['source']==contract['source']
    assert not q['gpio_application_mode_or_high_impedance_assumed'] and not q['release_authority']


@pytest.mark.parametrize('pin',['1','2','3','13','14','16','23','25','40','41','missing'])
def test_s3_power_enable_usb_and_uncovered_pins_are_not_scalar_shortcut_authority(tmp_path,pin):
    _,_,_,_,_,adc,*_=sensing_fixture(tmp_path)
    assert roles.scalar_gpio_pin(adc,pin) is None


@pytest.mark.parametrize('fault',['mpn','value','footprint','missing_ground','drilled_pin','power_on_node','duplicate_pin','dnp'])
def test_s3_native_package_contradictions_do_not_get_a_gpio_witness(tmp_path,fault):
    _,b,_,_,_,adc,*rest=sensing_fixture(tmp_path);land=rest[-1]
    if fault=='mpn':adc.SetField('MPN','ESP32-S3-WROOM-1-N16R16V')
    elif fault=='value':adc.SetValue('ESP32-C6-MINI-1')
    elif fault=='footprint':adc.SetFPID(pcbnew.LIB_ID('x','UNKNOWN'))
    elif fault=='missing_ground':adc.FindPadByNumber('40').SetNet(b.FindNet('OTHER'))
    elif fault=='drilled_pin':adc.FindPadByNumber('17').SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='power_on_node':adc.FindPadByNumber('2').SetNet(adc.FindPadByNumber('17').GetNet())
    elif fault=='duplicate_pin':land(adc,'17','arbitrary_divider',(204,50))
    elif fault=='dnp':adc.SetDNP(True)
    assert roles.scalar_gpio_pin(adc,'17') is None


@pytest.mark.parametrize('filters',[0,1,2])
def test_optional_selected_shunt_filters_keep_the_bounded_role_without_rating_a_rail(tmp_path,filters):
    b,_,net,_,_,_,_,land=fixture(tmp_path)
    for i in range(filters):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('any_filter_'+str(i));fp.SetValue('100nF')
        fp.SetField('MPN','CL05B104KO5NNNC');fp.SetFPID(pcbnew.LIB_ID('x','C_0402_1005Metric'));b.Add(fp)
        land(fp,'1',net,(27+i,27));land(fp,'2','GND',(27+i,28))
    q=divider.witness(b,net,power_nets={'GND','annotated_source_rail'})
    assert q and len(q['shunt_filters'])==filters and not q['current_budget_voltage_or_input_mode_inferred']


@pytest.mark.parametrize('power_nets',[True,[],{'GND',1},{''}])
def test_divider_context_does_not_coerce_a_power_net_authority(tmp_path,power_nets):
    b,_,net,*_=fixture(tmp_path)
    with pytest.raises(ValueError):divider.witness(b,net,power_nets=power_nets)
