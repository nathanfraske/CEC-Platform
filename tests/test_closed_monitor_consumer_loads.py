"""Closed input dividers add load; they never erase the shared-rail budget."""
import math
import pcbnew
import pytest
import cec_supply_consumer_branch as branch
import cec_resistive_monitor_branch as monitors
import cec_field_coupling as field
import cec_force_current as force
from test_pass_through_supply_branch import fixture as base_fixture


def fixture(monkeypatch,tmp_path,count=2,angle=0,mirrored=False):
    b,root,anchor,owner,cap,tracks,trunk,group,row,domain,downstream=base_fixture(monkeypatch,tmp_path)
    selected=[];tails=[]
    def part(ref,value,mpn,pins):
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetValue(value)
        f.SetFPID(pcbnew.LIB_ID('arbitrary_library','R_0402_1005Metric'));f.SetField('MPN',mpn);b.Add(f)
        for number,net,xy in pins:
            p=pcbnew.PAD(f);p.SetNumber(number);p.SetNet(net);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));p.SetPosition(pcbnew.VECTOR2I_MM(*xy));f.Add(p)
        return f
    for index,pin in enumerate(('6','5')[:count]):
        y=14+index*4
        net=pcbnew.NETINFO_ITEM(b,'unrelated_closed_divider_'+str(index));b.Add(net)
        top=part('MONITOR_TOP_'+str(index),'100k','0402WGF1003TCE',[
            ('1',root.GetNet(),(3.5,y)),('2',net,(4.8,y))])
        bottom=part('MONITOR_BOTTOM_'+str(index),'33k','0402WGF3302TCE',[
            ('1',net,(7.4,y)),('2',b.FindNet('GND'),(8.5,y))])
        p=pcbnew.PAD(owner);p.SetNumber(pin);p.SetNet(net);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));p.SetPosition(pcbnew.VECTOR2I_MM(6,y));owner.Add(p)
        for a,z in (((5,8),(2,11)),((2,11),(2,y)),((2,y),(3.5,y))):
            t=pcbnew.PCB_TRACK(b);t.SetNet(root.GetNet());t.SetWidth(600000);t.SetLayer(pcbnew.F_Cu)
            t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(t);tails.append(t)
        selected.append((top,bottom,p))
    for t in tracks:t.SetWidth(600000)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        if angle:item.Rotate(pcbnew.VECTOR2I_MM(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirrored:item.Flip(pcbnew.VECTOR2I_MM(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,b.GetFileName())
    return b,root,tracks,trunk,row,selected,tails


@pytest.mark.parametrize('count',[1,2])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirrored',[False,True])
def test_native_same_input_closed_monitors_are_added_to_not_spent_from_allowance(
        monkeypatch,tmp_path,count,angle,mirrored):
    b,root,tracks,trunk,row,selected,tails=fixture(monkeypatch,tmp_path,count,angle,mirrored)
    before=field._field_snapshot_inventory(b)
    r=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert r['complete'] and len(r['proofs'])==1,r
    budget=r['proofs'][0]['budget']
    expected=math.fsum(monitors.source_contract(b,force._uid(f.FindPadByNumber('1')))['current_upper_bound_a']
        for f,_,_ in selected)
    assert budget['additional_monitor_current_bound_a']==pytest.approx(expected)
    assert budget['current_authority']['amps']==pytest.approx(3.0004+expected)
    assert budget['base_consumer_current_authority']['amps']==3.0004
    assert budget['declaration']==row and row['amps']==3.0004
    assert budget['aggregate_current_authority']['amps']==20.
    assert budget['pass_through_input_bound']['output_current_authority']['amps']==3.
    assert len(budget['closed_monitor_loads'])==count
    assert budget['existing_consumer_declaration_unchanged'] and not budget['aggregate_current_budget_modified']
    assert force._uid(trunk) not in r['all_owned_track_requirements']
    assert {force._uid(t) for t in tails} <= r['retained_island_track_requirements'].keys()
    assert field._field_snapshot_inventory(b)==before
    loaded=pcbnew.LoadBoard(b.GetFileName())
    assert branch.inventory(loaded,board_hint='arbitrary',timeout_s=10.)==r


@pytest.mark.parametrize('fault',['unknown_top','wrong_value','bottom_unknown','bottom_not_ground',
    'node_extra_load','top_dnp','bottom_dnp','monitor_wrong_pin','wrong_associated_input',
    'summed_load_reaches_aggregate','old_device_only_width'])
def test_unknown_or_undersized_monitored_islands_never_receive_a_local_floor(monkeypatch,tmp_path,fault):
    b,root,tracks,trunk,row,selected,tails=fixture(monkeypatch,tmp_path)
    top,bottom,pin=selected[0]
    if fault=='unknown_top':top.SetField('MPN','unknown')
    elif fault=='wrong_value':top.SetValue('10k')
    elif fault=='bottom_unknown':bottom.SetField('MPN','unknown')
    elif fault=='bottom_not_ground':bottom.FindPadByNumber('2').SetNet(b.FindNet('OTHER'))
    elif fault=='node_extra_load':
        other=pcbnew.FOOTPRINT(b);other.SetReference('UNOWNED_NODE_LOAD');b.Add(other)
        p=pcbnew.PAD(other);p.SetNumber('1');p.SetNet(pin.GetNet());other.Add(p)
    elif fault=='top_dnp':top.SetDNP(True)
    elif fault=='bottom_dnp':bottom.SetDNP(True)
    elif fault=='monitor_wrong_pin':pin.SetNumber('10')
    elif fault=='wrong_associated_input':
        root.GetParentFootprint().FindPadByNumber('2').SetNumber('7')
        root.SetNumber('2');row['pin']='2'
        # The chosen input itself remains positively allowed. Its PR1
        # divider still belongs to the other manufacturer's input, not it.
        assert branch.contract(b,force._uid(root),board_hint='arbitrary')['declaration']['pin']=='2'
    elif fault=='summed_load_reaches_aggregate':row['amps']=19.9998
    else:
        old=branch.contract(b,force._uid(root),board_hint='arbitrary')
        tracks[0].SetWidth(math.ceil(old['required_by_layer_mm']['F.Cu']*1e6))
    r=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert not r['complete'] and not r['all_owned_track_requirements'] and r['refusals'],r


def test_unmonitored_leaf_budget_is_not_changed(monkeypatch,tmp_path):
    b,root,*_=base_fixture(monkeypatch,tmp_path)
    r=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert r['complete'],r
    budget=r['proofs'][0]['budget']
    assert budget['current_authority']['amps']==3.0004
    assert 'closed_monitor_loads' not in budget
