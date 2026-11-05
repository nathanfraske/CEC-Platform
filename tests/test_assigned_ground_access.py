"""Manufacturer grounds use their own bypass, not a ratsnest/refdes shortcut."""
import math
from unittest import mock

import pcbnew
import pytest

import cec_ground_reference_access as ground
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from cec_native_items import discard_items


def fixture(tmp_path, *, turn=0, layer=pcbnew.F_Cu, names=('OWNER_ANY', 'C_BYPASS_ANY')):
    b = pcbnew.BOARD(); b.SetCopperLayerCount(6)
    b.GetDesignSettings().m_ViasMinSize = 500000
    b.GetDesignSettings().m_MinThroughDrill = 300000
    b.GetDesignSettings().m_TrackMinWidth = 200000
    for s, t in [((0,0),(40,0)),((40,0),(40,40)),((40,40),(0,40)),((0,40),(0,0))]:
        e = pcbnew.PCB_SHAPE(b); e.SetLayer(pcbnew.Edge_Cuts); e.SetShape(pcbnew.SHAPE_T_SEGMENT)
        e.SetStart(pcbnew.VECTOR2I_MM(*s)); e.SetEnd(pcbnew.VECTOR2I_MM(*t)); b.Add(e)
    nets = {}
    for name in ('GND', '/RENAMED_DEVICE_RAIL'):
        net = pcbnew.NETINFO_ITEM(b, name); b.Add(net); nets[name] = net
    angle = turn * 90
    def at(x, y):
        dx, dy = x-20, y-20
        for _ in range(turn): dx, dy = dy, -dx
        return pcbnew.VECTOR2I_MM(20+dx, 20+dy)
    def part(ref, value, pads, footprint=''):
        fp = pcbnew.FOOTPRINT(b); fp.SetReference(ref); fp.SetValue(value); fp.SetLayer(layer)
        if footprint: fp.SetFPID(pcbnew.LIB_ID(*footprint.split(':')))
        b.Add(fp)
        for number, net, x, y in pads:
            p = pcbnew.PAD(fp); p.SetNumber(number); p.SetNet(nets[net])
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetSize(pcbnew.VECTOR2I_MM(.3,.5)); p.SetPosition(at(x,y)); p.SetOrientationDegrees(angle)
            ls = pcbnew.LSET(); ls.AddLayer(layer); p.SetLayerSet(ls); fp.Add(p)
        return fp
    owner = part(names[0], 'INA238', [('6','/RENAMED_DEVICE_RAIL',14.75,16.5),
        ('7','GND',15.25,16.5)], 'cec-Package_SO:VSSOP-10_3x3mm_P0.5mm')
    cap = part(names[1], '100nF', [('1','/RENAMED_DEVICE_RAIL',14.75,18.7),
        ('2','GND',15.25,18.7)], 'Capacitor_SMD:C_0402_1005Metric')
    def route(net, s, t):
        item = pcbnew.PCB_TRACK(b); item.SetNet(nets[net]); item.SetLayer(layer); item.SetWidth(200000)
        item.SetStart(at(*s)); item.SetEnd(at(*t)); b.Add(item); return item
    stub = route('GND',(15.25,16.5),(15.25,17.1))
    route('GND',(15.25,18.7),(15.25,19.5))
    route('/RENAMED_DEVICE_RAIL',(14.75,16.5),(14.75,18.7))
    via = pcbnew.PCB_VIA(b); via.SetNet(nets['GND']); via.SetPosition(at(15.25,19.5))
    via.SetWidth(600000); via.SetDrill(300000); via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); b.Add(via)
    source = tmp_path/'source.kicad_pcb'; field._save_field_snapshot(b,source)
    return source, b, owner, cap, stub, via


@pytest.mark.parametrize('turn,layer,names',[
    (0,pcbnew.F_Cu,('OWNER_ANY','C_BYPASS_ANY')),
    (1,pcbnew.F_Cu,('OTHER_CHIP','C_LOCAL_OTHER')),
    (2,pcbnew.B_Cu,('DEVICE_ALIAS','C_RENAMED')),
    (3,pcbnew.B_Cu,('MODULE_ALIAS','C_ALTERNATE'))])
def test_source_dangling_ground_stub_is_discovered_without_pad_named_airwire(tmp_path,turn,layer,names):
    source,b,owner,cap,stub,via = fixture(tmp_path,turn=turn,layer=layer,names=names)
    before = field._field_snapshot_inventory(b)
    rows = ground.assigned_ground_tasks(b,'unrelated-board')
    assert len(rows)==1, rows
    row = rows[0]
    assert row['owner']==names[0] and row['cap']==names[1] and row['pin']=='7'
    assert row['role']=='manufacturer_ground' and row['qualified_existing_ground_via_uuid']==force._uid(via)
    assert row['pad_uuid']!=force._uid(stub) and not row['local_ground_quality_qualified']
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['unknown_device','no_barrel','disconnected_barrel','too_small_barrel',
    'too_small_drill','changed_return_net','different_surface','already_connected','duplicate_ground_number'])
def test_unqualified_or_unowned_returns_never_enable_ground_routing(tmp_path,fault):
    source,b,owner,cap,stub,via=fixture(tmp_path)
    if fault=='unknown_device': owner.SetValue('UNKNOWN_PASSIVE')
    elif fault=='no_barrel': discard_items(b,[via])
    elif fault=='disconnected_barrel': via.Move(pcbnew.VECTOR2I_MM(3,0))
    elif fault=='too_small_barrel': via.SetWidth(400000)
    elif fault=='too_small_drill': via.SetDrill(200000)
    elif fault=='changed_return_net': cap.FindPadByNumber('2').SetNet(b.FindNet('/RENAMED_DEVICE_RAIL'))
    elif fault=='different_surface':
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu);owner.FindPadByNumber('7').SetLayerSet(ls)
    elif fault=='duplicate_ground_number':
        p=pcbnew.PAD(owner);p.SetNumber('7');p.SetNet(b.FindNet('GND'))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(.3,.5));p.SetPosition(owner.FindPadByNumber('7').GetPosition())
        p.SetLayerSet(pcbnew.PAD.SMDMask());owner.Add(p)
    else:
        t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('GND'));t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
        t.SetStart(owner.FindPadByNumber('7').GetPosition());t.SetEnd(cap.FindPadByNumber('2').GetPosition());b.Add(t)
    before=field._field_snapshot_inventory(b)
    assert not ground.assigned_ground_tasks(b,'arbitrary-design')
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('kwargs',[dict(timeout_s=0),dict(timeout_s=True),dict(timeout_s=math.nan),
    dict(timeout_s=11),dict(limit=0),dict(limit=True),dict(limit=65)])
def test_discovery_bounds_fail_before_mutation(tmp_path,kwargs):
    _,b,*_=fixture(tmp_path);before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError): ground.assigned_ground_tasks(b,'arbitrary-design',**kwargs)
    assert before==field._field_snapshot_inventory(b)


def test_source_assigned_ground_constructor_receives_stationary_track_only_completion(tmp_path):
    source,b,*_=fixture(tmp_path)
    original=source.read_bytes()
    result=ground.run(source,tmp_path/'constructed',board_hint='arbitrary-design',source_sha256=force._hash(source))
    assert result['ok'],result
    assert result['opens'] < result['source_opens']
    assert result['proposed_board_is_not_admitted'] and not result['release_authority']
    assert source.read_bytes()==original
    proof=result['receiving']
    assert proof['gained_references'][0]['task']['role']=='manufacturer_ground'
    assert proof['exact_parent_material_and_poses_preserved']


def test_default_receiver_still_refuses_whole_board_placement_blockers(tmp_path):
    source,b,*_=fixture(tmp_path)
    with mock.patch.object(ground.geometry,'evaluate',return_value={'ok':False}):
        result=ground.run(source,tmp_path/'blocked-placement',board_hint='arbitrary-design',source_sha256=force._hash(source))
    assert not result['ok'] and result['proposed_board_is_not_admitted']
    assert 'reference_return_physical_placement_refused' in str(result['receiving']['errors'])
    assert not result['release_authority']
