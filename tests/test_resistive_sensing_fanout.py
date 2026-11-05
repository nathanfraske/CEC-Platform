"""Source-typed ADC/comparator/filter leaves are not whole-rail load paths."""
import pcbnew
import pytest
import cec_device_power_roles as roles
import cec_resistive_monitor_branch as branch
import cec_force_current as force
import cec_field_coupling as field
import cec_constraints as constraints
from test_force_current import authority
from test_resistive_monitor_branch import fixture


def sensing_fixture(tmp_path, *, filtered=False, transition=False):
    source,b,top,bottom,mux,domains,owned,trunk,via=fixture(tmp_path,transition=transition)
    mux.SetField('MPN','TPS2121RUXR')
    mux.FindPadByNumber('6').SetNet(b.FindNet('OTHER'))
    logic=pcbnew.NETINFO_ITEM(b,'independent_logic_supply');b.Add(logic)
    def land(fp,pin,net,at):
        p=pcbnew.PAD(fp);p.SetNumber(str(pin));p.SetNet(b.FindNet(net))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetPosition(pcbnew.VECTOR2I_MM(*at));fp.Add(p);return p
    for n in range(1,13):
        if mux.FindPadByNumber(str(n)) is None:
            land(mux,n,'GND' if n==12 else 'OTHER',(40+n,30))
    def device(ref,value,mpn,package,pins):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value);fp.SetField('MPN',mpn)
        fp.SetFPID(pcbnew.LIB_ID('arbitrary_library',package));b.Add(fp)
        for n,net,at in pins:land(fp,n,net,at)
        return fp
    adc=device('not_hub_or_U1','ESP32-S3-WROOM-1','ESP32-S3-WROOM-1-N16R8',
        'ESP32-S3-WROOM-1_NoAntKeepout',[
            (n,'arbitrary_divider' if n==17 else 'independent_logic_supply' if n==2
             else 'GND' if n in (1,40,41) else 'OTHER',(100+n,50)) for n in range(1,42)])
    adc.FindPadByNumber('17').SetPosition(pcbnew.VECTOR2I_MM(8,9))
    comparator=cap=None
    if filtered:
        comparator=device('comparator_any_ref','TLV7011DBVR','TLV7011DBVR','SOT-23-5',[
            (n,'arbitrary_divider' if n==3 else 'independent_logic_supply' if n==5
             else 'GND' if n==2 else 'OTHER',(150+n,50)) for n in range(1,6)])
        cap=device('filter_not_a_special_ref','10nF','CL05B103KB5NNNC','C_0402_1005Metric',
            [(1,'arbitrary_divider',(160,50)),(2,'GND',(161,50))])
    field._save_field_snapshot(b,source)
    return source,b,top,bottom,mux,adc,comparator,cap,domains,owned,trunk,via,land


@pytest.mark.parametrize('filtered',[False,True])
@pytest.mark.parametrize('transition',[False,True])
def test_selected_adc_and_filtered_comparator_are_bounded_not_full_rail(tmp_path,filtered,transition):
    source,b,top,_,_,adc,_,_,domains,owned,trunk,_,_=sensing_fixture(
        tmp_path,filtered=filtered,transition=transition)
    original=source.read_bytes();q=branch.source_contract(b,force._uid(top.FindPadByNumber('1')))
    assert q['current_upper_bound_a']==pytest.approx(24.3/(100000*.99*(1-.013)))
    assert len(q['monitor_endpoint_contracts'])==1+filtered
    assert len(q['shunt_filter_contracts'])==filtered
    assert q['source_power_voltage_contract']['voltage_bound_not_a_physical_clamp']
    assert not q['gpio_high_impedance_or_equal_load_sharing_assumed']
    assert not q['numeric_rail_load_budget_modified'] and not q['release_authority']
    assert q['associated_supply_pad_uuid']!=force._uid(adc.FindPadByNumber('2'))
    result=branch.inventory(b,source,domains)
    assert result['complete'] and set(result['uuids'])==set(owned),result
    assert result['proofs'][0]['partitions_unchanged_after_collective_removal']
    with authority('arbitrary_rail',amps=3.,source='SOURCE',sink='SINK'):
        check=constraints.CHECKERS['trace-width-high-current'](pcbnew.LoadBoard(str(source)),str(source),{})
    faults=[r for r in check[2] if r.get('type')=='current_domain_path']
    assert faults and trunk in {r['uuid'] for r in faults[0]['undersized_segments']}
    assert not set(owned)&{r['uuid'] for r in faults[0]['undersized_segments']}
    assert check[0] is False and source.read_bytes()==original


@pytest.mark.parametrize('fault',[
    'adc_unknown','adc_wrong_package','adc_wrong_family','adc_uncovered_variant','adc_usb',
    'adc_missing_ground','adc_power_on_node','adc_dnp','adc_drilled_signal','adc_drilled_power','mux_unknown','mux_ground_wrong',
    'mux_wrong_package','mux_incomplete','mux_dnp','comp_output','comp_unknown','comp_wrong_package',
    'comp_ground_wrong','comp_dnp','cap_unknown','cap_wrong_value','cap_cross_rail','cap_dnp',
    'bottom_cross_rail','extra_unowned_land','top_dnp','underwidth','source_control_not_power'])
def test_unknown_loaded_and_miswired_fanouts_are_never_exempted(tmp_path,fault):
    source,b,top,bottom,mux,adc,comp,cap,domains,owned,_,_,land=sensing_fixture(tmp_path,filtered=True)
    if fault=='adc_unknown':adc.SetField('MPN','UNKNOWN')
    elif fault=='adc_wrong_package':adc.SetFPID(pcbnew.LIB_ID('fixture','ESP32-C6-MINI-1'))
    elif fault=='adc_wrong_family':adc.SetValue('ESP32-C6-MINI-1')
    elif fault=='adc_uncovered_variant':adc.SetField('MPN','ESP32-S3-WROOM-1-N16R16V')
    elif fault=='adc_usb':adc.FindPadByNumber('17').SetNumber('13')
    elif fault=='adc_missing_ground':adc.FindPadByNumber('41').SetNet(b.FindNet('OTHER'))
    elif fault=='adc_power_on_node':adc.FindPadByNumber('2').SetNet(b.FindNet('arbitrary_divider'))
    elif fault=='adc_dnp':adc.SetDNP(True)
    elif fault in ('adc_drilled_signal','adc_drilled_power'):
        p=adc.FindPadByNumber('17' if fault=='adc_drilled_signal' else '2')
        # Preserve the electrical net while corrupting the surface land.
        # KiCad drops an NPTH land's net during native serialization; then
        # it is absent from the fanout, not an unknown electrical endpoint.
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='mux_unknown':mux.SetField('MPN','UNKNOWN')
    elif fault=='mux_ground_wrong':mux.FindPadByNumber('12').SetNet(b.FindNet('OTHER'))
    elif fault=='mux_wrong_package':mux.SetFPID(pcbnew.LIB_ID('fixture','UNKNOWN'))
    elif fault=='mux_incomplete':mux.Remove(mux.FindPadByNumber('11'))
    elif fault=='mux_dnp':mux.SetDNP(True)
    elif fault=='comp_output':comp.FindPadByNumber('3').SetNumber('1')
    elif fault=='comp_unknown':comp.SetField('MPN','UNKNOWN')
    elif fault=='comp_wrong_package':comp.SetFPID(pcbnew.LIB_ID('fixture','SOT-23-6'))
    elif fault=='comp_ground_wrong':comp.FindPadByNumber('2').SetNet(b.FindNet('OTHER'))
    elif fault=='comp_dnp':comp.SetDNP(True)
    elif fault=='cap_unknown':cap.SetField('MPN','UNKNOWN')
    elif fault=='cap_wrong_value':cap.SetValue('100nF')
    elif fault=='cap_cross_rail':cap.FindPadByNumber('2').SetNet(b.FindNet('OTHER'))
    elif fault=='cap_dnp':cap.SetDNP(True)
    elif fault=='bottom_cross_rail':bottom.FindPadByNumber('2').SetNet(b.FindNet('OTHER'))
    elif fault=='extra_unowned_land':land(comp,'unowned','arbitrary_divider',(180,50))
    elif fault=='top_dnp':top.SetDNP(True)
    elif fault=='underwidth':
        for t in b.GetTracks():
            if force._uid(t) in owned:t.SetWidth(1000)
    elif fault=='source_control_not_power':
        mux.FindPadByNumber('7').SetNet(b.FindNet('OTHER'))
        mux.FindPadByNumber('6').SetNet(b.FindNet('arbitrary_rail'))
    field._save_field_snapshot(b,source)
    result=branch.inventory(b,source,domains)
    assert not result['uuids'],result


def test_adc_physical_ground_lands_and_mechanical_holes_are_not_duplicate_signal_pins(tmp_path):
    source,b,top,_,_,adc,_,_,domains,owned,_,_,land=sensing_fixture(tmp_path)
    p=land(adc,'41','GND',(200,50));p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2));p.SetLayerSet(pcbnew.LSET.AllCuMask())
    p=land(adc,'','OTHER',(202,50));p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    p.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    assert roles.resistive_sensing_endpoint_contract(adc,'17') is not None
    land(adc,'17','arbitrary_divider',(204,50))
    assert roles.resistive_sensing_endpoint_contract(adc,'17') is None


def test_fanout_identity_survives_rotation_and_back_face_without_refs_or_coordinates(tmp_path):
    source,b,_,_,_,_,_,_,domains,owned,_,_,_=sensing_fixture(tmp_path,filtered=True,transition=True)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90,pcbnew.DEGREES_T))
        item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,source)
    q=branch.inventory(b,source,domains)
    assert q['complete'] and set(q['uuids'])==set(owned),q


def test_proved_resistive_leaf_not_inherited_full_power_width_preference(tmp_path,monkeypatch):
    source,b,top,_,_,_,_,_,domains,owned,trunk,_,_=sensing_fixture(tmp_path,filtered=True)
    import cec_fr as fr
    real=fr._project_netclass_resolver
    def resolver(path):
        fallback=real(path)
        return lambda net:dict(fallback(net) or {},name='Power',track_width=1.,clearance=.25)
    monkeypatch.setattr(fr,'_project_netclass_resolver',resolver)
    spec,demand=branch.route_spec(b,source,force._uid(top.FindPadByNumber('1')))
    assert spec['track_width']==pytest.approx(.2) and spec['clearance']==pytest.approx(.25)
    assert spec['dimension_contract']['parent_net_preferred_track_width_mm']==1.
    assert not spec['dimension_contract']['full_rail_load_budget_or_trunk_width_modified']
    q=branch.inventory(b,source,domains)
    assert q['complete'] and set(q['uuids'])==set(owned),q
    # This API cannot manufacture leaf authority for an actual source pad.
    with pytest.raises(ValueError):
        branch.route_spec(b,source,force._uid(next(f for f in b.GetFootprints()
            if f.GetReference()=='SOURCE').FindPadByNumber('1')))
    # A genuinely higher fabrication minimum remains a hard refusal.
    b.GetDesignSettings().m_TrackMinWidth=250000
    assert branch.route_spec(b,source,demand['pad_uuid'])[0]['track_width']==pytest.approx(.25)
    assert not branch.inventory(b,source,domains)['uuids']
