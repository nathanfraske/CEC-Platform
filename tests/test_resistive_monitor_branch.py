"""A selected divider is not a full-current power path or a guessed load."""
import pcbnew
import pytest
import cec_resistive_monitor_branch as branch
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_constraints as constraints
from test_force_current import authority


def fixture(tmp_path,*,transition=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    nets={}
    for name in ('arbitrary_rail','arbitrary_divider','GND','OTHER'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
    def part(ref,value,footprint,pins,mpn=None):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue(value)
        fp.SetFPID(pcbnew.LIB_ID('fixture',footprint));board.Add(fp)
        if mpn:fp.SetField('MPN',mpn)
        for pin,net,x,y in pins:
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(nets[net]);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
            p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetPosition(pcbnew.VECTOR2I_MM(x,y));fp.Add(p)
        return fp
    top=part('not_a_special_ref','100k','R_0402_1005Metric',[
        ('1','arbitrary_rail',10,10),('2','arbitrary_divider',9,10)],'0402WGF1003TCE')
    bottom=part('another_random_ref','33k','R_0402_1005Metric',[
        ('1','arbitrary_divider',8,10),('2','GND',7,10)],'0402WGF3302TCE')
    device=part('mux_any_name','TPS2121RUXR','RUX0012A',[
        ('6','arbitrary_divider',8,9),('7','arbitrary_rail',20,12),('2','OTHER',20,13)])
    part('SOURCE','test','Test',[('1','arbitrary_rail',20,12)])
    part('SINK','test','Test',[('1','arbitrary_rail',20,20)])
    def trace(points,layer):
        ids=[]
        for a,b in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(board);t.SetNet(nets['arbitrary_rail']);t.SetWidth(200000);t.SetLayer(layer)
            t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(t);ids.append(force._uid(t))
        return ids
    owned=trace([(10,10),(20,10),(20,12)],pcbnew.In2_Cu if transition else pcbnew.F_Cu)
    via=None
    if transition:
        via=pcbnew.PCB_VIA(board);via.SetNet(nets['arbitrary_rail']);via.SetPosition(pcbnew.VECTOR2I_MM(10,10))
        via.SetWidth(450000);via.SetDrill(250000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetViaType(pcbnew.VIATYPE_THROUGH);board.Add(via)
        retained=pcbnew.PCB_VIA(board);retained.SetNet(nets['arbitrary_rail'])
        retained.SetPosition(pcbnew.VECTOR2I_MM(20,12));retained.SetWidth(900000);retained.SetDrill(500000)
        retained.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);retained.SetViaType(pcbnew.VIATYPE_THROUGH);board.Add(retained)
    trunk=trace([(20,12),(20,20)],pcbnew.F_Cu)[0]
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    domains={'arbitrary_rail':dict(complete=True,authority_refs=['SOURCE','SINK'],
        source_refs=['SOURCE'],sink_refs=['SINK'])}
    return source,board,top,bottom,device,domains,owned,trunk,via


@pytest.mark.parametrize('transition',[False,True])
def test_native_exclusive_divider_not_the_real_underwidth_power_trunk(tmp_path,transition):
    source,b,top,_,_,domains,owned,trunk,via=fixture(tmp_path,transition=transition)
    original=source.read_bytes();contract=branch.source_contract(b,force._uid(top.FindPadByNumber('1')))
    assert contract['current_upper_bound_a']==pytest.approx(24.3/(100000*.99*(1-.013)))
    assert not contract['numeric_rail_load_budget_modified'] and not contract['release_authority']
    proposal=branch.plan(b,contract['pad_uuid'])
    assert set(proposal['track_uuids'])==set(owned) and trunk not in proposal['native_removed_material_uuids']
    assert bool(proposal['via_uuids'])==transition and not proposal['retirement_authority']
    result=branch.inventory(b,source,domains)
    assert result['complete'] and set(result['uuids'])==set(owned),result
    assert result['proofs'][0]['partitions_unchanged_after_collective_removal']
    assert not result['current_path_qualified'] and not result['release_authority']
    with authority('arbitrary_rail',amps=3.,source='SOURCE',sink='SINK'):
        check=constraints.CHECKERS['trace-width-high-current'](pcbnew.LoadBoard(str(source)),str(source),{})
    assert check[0] is False
    faults=[r for r in check[2] if r.get('type')=='current_domain_path']
    assert faults and faults[0]['rated_connectivity']['connected'] is False
    assert trunk in {r['uuid'] for r in faults[0]['undersized_segments']}
    assert not set(owned)&{r['uuid'] for r in faults[0]['undersized_segments']}
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['unknown_mpn','contradictory_value','wrong_resistor_package',
    'wrong_monitor_package','unsupported_control','wrong_associated_rail','extra_node_land',
    'bottom_unknown','bottom_not_ground','top_dnp','bottom_dnp','device_dnp','current_terminal',
    'low_resistance','underwidth','unqualified_via','interior_contact','partition_change'])
def test_unverified_loaded_or_unqualified_taps_have_no_current_exemption(tmp_path,fault,monkeypatch):
    source,b,top,bottom,device,domains,owned,trunk,via=fixture(tmp_path,transition=fault=='unqualified_via')
    if fault=='unknown_mpn':top.SetField('MPN','UNKNOWN')
    elif fault=='contradictory_value':top.SetValue('10k')
    elif fault=='wrong_resistor_package':top.SetFPID(pcbnew.LIB_ID('fixture','R_0603_1608Metric'))
    elif fault=='wrong_monitor_package':device.SetFPID(pcbnew.LIB_ID('fixture','UNKNOWN'))
    elif fault=='unsupported_control':device.FindPadByNumber('6').SetNumber('3')
    elif fault=='wrong_associated_rail':device.FindPadByNumber('7').SetNet(b.FindNet('OTHER'))
    elif fault=='extra_node_land':
        p=pcbnew.PAD(device);p.SetNumber('extra');p.SetNet(b.FindNet('arbitrary_divider'));device.Add(p)
    elif fault=='bottom_unknown':bottom.SetField('MPN','UNKNOWN')
    elif fault=='bottom_not_ground':bottom.FindPadByNumber('2').SetNet(b.FindNet('OTHER'))
    elif fault=='top_dnp':top.SetDNP(True)
    elif fault=='bottom_dnp':bottom.SetDNP(True)
    elif fault=='device_dnp':device.SetDNP(True)
    elif fault=='current_terminal':domains['arbitrary_rail']['authority_refs'].append(top.GetReference())
    elif fault=='low_resistance':top.SetValue('10');top.SetField('MPN','0402WGF0100TCE')
    elif fault=='underwidth':
        for t in b.GetTracks():
            if force._uid(t) in owned:t.SetWidth(1000)
    elif fault=='unqualified_via':via.SetDrill(100000);via.SetWidth(180000)
    elif fault=='interior_contact':
        t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('arbitrary_rail'));t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu)
        t.SetStart(pcbnew.VECTOR2I_MM(15,10));t.SetEnd(pcbnew.VECTOR2I_MM(15,11));b.Add(t)
    else:
        actual=branch.plan
        def forged(*args,**kwargs):
            q=actual(*args,**kwargs);q['native_removed_material_uuids'].append(trunk);return q
        monkeypatch.setattr(branch,'plan',forged)
    field._save_field_snapshot(b,source)
    result=branch.inventory(b,source,domains)
    assert not result['uuids'],result


def test_classification_survives_arbitrary_rotation_and_back_face(tmp_path):
    source,b,top,_,_,domains,owned,_,_=fixture(tmp_path,transition=True)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90,pcbnew.DEGREES_T))
        item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,source)
    result=branch.inventory(b,source,domains)
    assert result['complete'] and set(result['uuids'])==set(owned),result


def test_custom_layer_names_do_not_change_thickness_authority(tmp_path):
    source,b,_,_,_,domains,owned,_,_=fixture(tmp_path,transition=True)
    assert b.SetLayerName(pcbnew.In2_Cu,'SIG_CUSTOM')
    field._save_field_snapshot(b,source)
    result=branch.inventory(b,source,domains)
    assert result['complete'] and set(result['uuids'])==set(owned),result


@pytest.mark.parametrize('bad',[True,-1,0,float('nan'),float('inf'),11])
def test_inventory_and_plan_have_finite_explicit_bounds(tmp_path,bad):
    source,b,top,_,_,domains,_,_,_=fixture(tmp_path)
    with pytest.raises(ValueError):branch.inventory(b,source,domains,timeout_s=bad)
    with pytest.raises(ValueError):branch.plan(b,force._uid(top.FindPadByNumber('1')),timeout_s=bad)
