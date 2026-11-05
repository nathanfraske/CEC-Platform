"""Search reservations cannot relabel an allocated load or mutate source copper."""
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
from cec_typed_leaf_reservation import MonitorAccessGuard
from test_pass_through_supply_branch import fixture as consumer_fixture


def fixture(monkeypatch,tmp_path,*,angle=0,mirrored=False):
    b,power,anchor,owner,cap,tracks,trunk,group,*_ = consumer_fixture(monkeypatch,tmp_path)
    divider=pcbnew.NETINFO_ITEM(b,'/not_board_specific/THRESHOLD');b.Add(divider)
    def land(fp,pin,net,xy):
        p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNet(net)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
        p.SetPosition(pcbnew.VECTOR2I_MM(*xy));fp.Add(p);return p
    top=pcbnew.FOOTPRINT(b);top.SetReference('ARBITRARY_DIVIDER_TOP');top.SetValue('100k')
    top.SetFPID(pcbnew.LIB_ID('fixture','R_0402_1005Metric'));top.SetField('MPN','0402WGF1003TCE');b.Add(top)
    root=land(top,'1',power.GetNet(),(10,18));land(top,'2',divider,(10,20))
    bottom=pcbnew.FOOTPRINT(b);bottom.SetReference('ARBITRARY_BOTTOM');bottom.SetValue('33k')
    bottom.SetFPID(pcbnew.LIB_ID('fixture','R_0402_1005Metric'));bottom.SetField('MPN','0402WGF3302TCE');b.Add(bottom)
    land(bottom,'1',divider,(5,12));land(bottom,'2',b.FindNet('GND'),(5,14))
    land(owner,'6',divider,(5,10))
    def transform(xy):
        x,y=xy
        for _ in range(angle//90):x,y=y,-x
        if mirrored:x=-x
        return round(x*1e6),round(y*1e6)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        if angle:item.Rotate(pcbnew.VECTOR2I_MM(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirrored:item.Flip(pcbnew.VECTOR2I_MM(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source=tmp_path/'typed-source.kicad_pcb';field._save_field_snapshot(b,source)
    assert transform((5,8))==tuple(power.GetPosition())
    return b,root,tracks,source,transform,owner.GetLayer()


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirrored',[False,True])
def test_native_allocation_is_not_an_interchangeable_same_net_trunk(monkeypatch,tmp_path,angle,mirrored):
    b,root,tracks,source,xy,layer=fixture(monkeypatch,tmp_path,angle=angle,mirrored=mirrored)
    original=source.read_bytes();before=field._field_snapshot_inventory(b)
    guard=MonitorAccessGuard(b,source,root_pad_uuid=force._uid(root),board_hint='unrelated_identity')
    assert not guard(xy((10,8)),xy((11,8)),200000,int(layer))
    assert guard(xy((30,8)),xy((35,8)),200000,int(layer))
    assert guard(xy((25,9)),xy((25,8)),200000,int(layer))
    opposite=pcbnew.F_Cu if layer==pcbnew.B_Cu else pcbnew.B_Cu
    assert guard(xy((10,8)),xy((11,8)),200000,int(opposite))
    report=guard.report();assert report['complete'] and report['refused']==1
    assert report['shared_bus_taps_only'] and not report['current_qualified']
    assert not report['admission_authority'] and not report['aggregate_rail_or_consumer_load_budget_modified']
    assert source.read_bytes()==original and field._field_snapshot_inventory(b)==before


def test_unreceived_allocation_cannot_be_treated_as_empty_space(monkeypatch,tmp_path):
    b,root,tracks,source,_,_=fixture(monkeypatch,tmp_path)
    tracks[0].SetWidth(1000)
    with pytest.raises(ValueError,match='current_consumer_scope_inventory_required'):
        MonitorAccessGuard(b,source,root_pad_uuid=force._uid(root),board_hint='unrelated_identity')


def test_untyped_root_cannot_borrow_a_monitor_reservation(monkeypatch,tmp_path):
    b,root,_,source,_,_=fixture(monkeypatch,tmp_path)
    root.GetParentFootprint().SetField('MPN','UNKNOWN')
    with pytest.raises(ValueError,match='positive_selected_monitor_resistor_required'):
        MonitorAccessGuard(b,source,root_pad_uuid=force._uid(root),board_hint='unrelated_identity')


@pytest.mark.parametrize('budget',[0,True,float('nan'),11])
def test_reservation_work_is_explicit_and_bounded(monkeypatch,tmp_path,budget):
    b,root,_,source,_,_=fixture(monkeypatch,tmp_path)
    with pytest.raises(ValueError,match='bounded_positive_monitor_scope_reservation_required'):
        MonitorAccessGuard(b,source,root_pad_uuid=force._uid(root),board_hint='unrelated_identity',timeout_s=budget)
