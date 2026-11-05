"""Source-native current bus taps, including rotated and flipped physical CAD."""
import math
from unittest import mock

import pcbnew
import pytest
import cec_native_bus_column as column
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_fab_profile as fab
from cec_route_dimensions import current_trace_widths


def fixture(tmp_path,angle=0,back=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);b.SetFileName(str(tmp_path/'fixture.kicad_pcb'))
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    settings=b.GetDesignSettings();settings.m_TrackMinWidth=200000;settings.m_MinClearance=200000
    settings.m_ViasMinSize=500000;settings.m_MinThroughDrill=300000;settings.m_ViasMinAnnularWidth=100000
    supply=pcbnew.NETINFO_ITEM(b,'/renamed/FEED');ground=pcbnew.NETINFO_ITEM(b,'GND')
    b.Add(supply);b.Add(ground)
    cap=pcbnew.FOOTPRINT(b);cap.SetReference('OTHER_CAP_7');cap.SetValue('100nF')
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0402_1005Metric'));cap.SetPosition(pcbnew.VECTOR2I_MM(10,10));b.Add(cap)
    pads=[]
    for number,x,net in [('1',10.48,supply),('2',9.52,ground)]:
        p=pcbnew.PAD(cap);p.SetNumber(number);p.SetNet(net);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetSize(pcbnew.VECTOR2I_MM(.62,.56));p.SetPosition(pcbnew.VECTOR2I_MM(x,10));cap.Add(p);pads.append(p)
    owner=pcbnew.FOOTPRINT(b);owner.SetReference('RENAMED_OWNER');owner.SetValue('TPS2121RUXR')
    owner.SetPosition(pcbnew.VECTOR2I_MM(14.5,10));b.Add(owner)
    p=pcbnew.PAD(owner);p.SetNumber('8');p.SetNet(supply);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I_MM(1,.8));p.SetPosition(owner.GetPosition());owner.Add(p)
    bus=pcbnew.PCB_TRACK(b);bus.SetStart(pcbnew.VECTOR2I_MM(11,10));bus.SetEnd(pcbnew.VECTOR2I_MM(15,10))
    bus.SetWidth(500000);bus.SetLayer(pcbnew.B_Cu);bus.SetNet(supply);b.Add(bus)
    for start,end in [((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))]:
        edge=pcbnew.PCB_SHAPE();edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*start));edge.SetEnd(pcbnew.VECTOR2I_MM(*end));b.Add(edge)
    for f in b.GetFootprints():
        if back:f.Flip(pcbnew.VECTOR2I_MM(10,10),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if angle:f.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    if back:bus.Flip(pcbnew.VECTOR2I_MM(10,10),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if angle:bus.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    authority=dict(amps=1.1,geometry_margin=1.25,margin_included=False,source='component_power_budget')
    profile='jlcpcb_6l_pofv_signal'
    widths=current_trace_widths(authority,tuple(fab.enabled_copper_layers(b)),profile,rise_c=30.)
    current=dict(current_authority=authority,profile=profile,
        required_by_layer_nm={b.GetLayerID(n):math.ceil(w*1e6) for n,w in widths.items()})
    return b,p,pads[0],bus,current


def call(b,owner,cap,*,construct=False,**kwargs):
    return (column.construct if construct else column.plan)(b,owner,cap,source=b.GetFileName(),
        board_hint='synthetic-source',timeout_s=2.,**kwargs)


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,False),(270,False),
    (0,True),(90,True),(180,True),(270,True)])
def test_renamed_rotated_flipped_actual_supply_trunk_contacts(tmp_path,angle,back):
    b,owner,cap,bus,current=fixture(tmp_path,angle,back);before=field._field_snapshot_inventory(b)
    with mock.patch.object(cells,'_supply_current_widths',return_value=current):
        proposal=call(b,owner,cap)
        assert proposal and field._field_snapshot_inventory(b)==before
        assert bus.m_Uuid.AsString() in proposal['retained_bus_track_uuids']
        result=call(b,owner,cap,construct=True)
    assert result and result['status']=='linked-source-native-bus-column'
    assert result['actual_native_supply_contacts']['ok'] and result['actual_native_supply_contacts']['complete']
    assert result['actual_native_supply_contacts']['actual_contact_layers']==['B.Cu','F.Cu']
    assert not result['plated_barrel_ampacity_qualified'] and not result['local_bypass_loop_qualified']
    assert all(t.GetWidth()>=max(200000,current['required_by_layer_nm'][int(t.GetLayer())])
        for t in result['items'] if t.GetClass()=='PCB_TRACK')
    assert bus in list(b.GetTracks()) and bus.GetWidth()==500000


@pytest.mark.parametrize('fault',['no_current','wrong_owner','signal_pin','dnp','non_capacitor',
    'wrong_net','thin_trunk','same_face','foreign_barrel','edge','uncaptured_control','no_feed'])
def test_no_name_or_hint_grants_native_current_access(tmp_path,fault):
    b,owner,cap,bus,current=fixture(tmp_path)
    if fault=='wrong_owner':owner.GetParentFootprint().SetValue('UNKNOWN')
    if fault=='signal_pin':owner.SetNumber('9')
    if fault=='dnp':cap.GetParentFootprint().SetDNP(True)
    if fault=='non_capacitor':cap.GetParentFootprint().SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0402_1005Metric'));cap.GetParentFootprint().SetValue('10k')
    if fault=='wrong_net':owner.SetNetCode(b.GetNetcodeFromNetname('GND'))
    if fault=='thin_trunk':bus.SetWidth(1)
    if fault=='same_face':bus.SetLayer(pcbnew.F_Cu)
    before=field._field_snapshot_inventory(b)
    with mock.patch.object(cells,'_supply_current_widths',return_value=None if fault=='no_current' else current), \
        mock.patch.object(column.fr,'_via_spot_clear',wraps=column.fr._via_spot_clear if fault!='foreign_barrel' else None,
            **({'return_value':False} if fault=='foreign_barrel' else {})), \
        mock.patch.object(column.fr,'_edge_leg_clear',wraps=column.fr._edge_leg_clear if fault!='edge' else None,
            **({'return_value':False} if fault=='edge' else {})), \
        mock.patch.object(column.capture.Guard,'allows_endpoint',return_value=fault!='uncaptured_control'), \
        mock.patch.object(column.fr,'_guarded_profiled_lastmile_legs',wraps=column.fr._guarded_profiled_lastmile_legs if fault!='no_feed' else None,
            **({'return_value':None} if fault=='no_feed' else {})):
        assert call(b,owner,cap) is None
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['fake_floor','fake_profile','unknown_authority'])
def test_independently_recompute_current_dimensions(tmp_path,fault):
    b,owner,cap,bus,current=fixture(tmp_path)
    if fault=='fake_floor':current['required_by_layer_nm'][pcbnew.F_Cu]-=1
    if fault=='fake_profile':current['profile']='wrong'
    if fault=='unknown_authority':current['current_authority']['source']='guessed'
    before=field._field_snapshot_inventory(b)
    with mock.patch.object(cells,'_supply_current_widths',return_value=current),pytest.raises(ValueError):call(b,owner,cap)
    assert before==field._field_snapshot_inventory(b)


def test_failed_actual_contact_web_rolls_back_once(tmp_path):
    b,owner,cap,bus,current=fixture(tmp_path);before=field._field_snapshot_inventory(b)
    with mock.patch.object(cells,'_supply_current_widths',return_value=current), \
        mock.patch.object(column.web,'receive',return_value={'ok':False,'complete':True}), \
        mock.patch.object(column,'discard_items',wraps=column.discard_items) as discard, \
        pytest.raises(ValueError,match='contact_floor'):
        call(b,owner,cap,construct=True)
    assert discard.call_count==1 and before==field._field_snapshot_inventory(b)


def test_display_aliases_cannot_change_physical_layer_current_widths(tmp_path):
    b,owner,cap,bus,current=fixture(tmp_path)
    for layer,name in ((pcbnew.In1_Cu,'GND'),(pcbnew.In2_Cu,'SIG2'),
            (pcbnew.In3_Cu,'PWR1'),(pcbnew.In4_Cu,'SIG4')):b.SetLayerName(layer,name)
    with mock.patch.object(cells,'_supply_current_widths',return_value=current):
        result=call(b,owner,cap,construct=True)
    assert result and result['actual_native_supply_contacts']['ok']
    assert result['actual_native_supply_contacts']['unused_copper_layers_not_assumed_to_carry_current']==[
        'In1.Cu','In2.Cu','In3.Cu','In4.Cu']


def test_actual_inner_contact_reinstates_full_inner_width_and_rolls_back(tmp_path):
    b,owner,cap,bus,current=fixture(tmp_path)
    with mock.patch.object(cells,'_supply_current_widths',return_value=current):proposal=call(b,owner,cap)
    point=proposal['via_at_nm'];inner=pcbnew.PCB_TRACK(b)
    inner.SetStart(pcbnew.VECTOR2I(point[0]-500000,point[1]));inner.SetEnd(pcbnew.VECTOR2I(point[0]+500000,point[1]))
    inner.SetLayer(pcbnew.In2_Cu);inner.SetWidth(200000);inner.SetNet(cap.GetNet());b.Add(inner)
    before=field._field_snapshot_inventory(b)
    with mock.patch.object(cells,'_supply_current_widths',return_value=current),pytest.raises(ValueError,match='contact_floor'):
        call(b,owner,cap,construct=True,max_sites=1)
    assert before==field._field_snapshot_inventory(b)


def test_integrated_rail_tier_runs_before_expensive_retained_port_walk(tmp_path):
    b,owner,cap,bus,current=fixture(tmp_path)
    with mock.patch.object(cells,'_supply_current_widths',return_value=current), \
        mock.patch.object(cells,'_canonical_whole_rail_surface',return_value=None), \
        mock.patch.object(cells,'_retained_supply_throat_ops',side_effect=AssertionError('column should precede walk')):
        result,error=cells._add_supply_link(b,owner,cap,lock=True,rail_completion=True,
            search_timeout_s=2.,search_work_limit=64)
    assert error is None and result['status']=='linked-source-native-bus-column'
    assert result['search_work']['work_used']<=64
    assert not result['local_bypass_loop_qualified']


def test_real_cutout_uses_conductor_radius_plus_unchanged_edge_margin_not_foreign_gap(tmp_path):
    b,owner,cap,bus,current=fixture(tmp_path)
    with mock.patch.object(cells,'_supply_current_widths',return_value=current):
        proposed=call(b,owner,cap,max_sites=1)
    assert proposed
    x,y=proposed['via_at_nm'];radius=math.ceil(proposed['via_diameter_nm']/2)
    top=y+radius+500000+100000
    corners=((x-1000000,top),(x+1000000,top),
        (x+1000000,top+1000000),(x-1000000,top+1000000))
    for start,end in zip(corners,(*corners[1:],corners[0])):
        edge=pcbnew.PCB_SHAPE();edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I(*start));edge.SetEnd(pcbnew.VECTOR2I(*end));b.Add(edge)
    if hasattr(b,'_cec_edge_leg_cache'):del b._cec_edge_leg_cache
    point=pcbnew.VECTOR2I(x,y)
    assert column.fr._edge_leg_clear(b,point,point,radius)
    assert not column.fr._edge_leg_clear(b,point,point,radius+200000)
    with mock.patch.object(cells,'_supply_current_widths',return_value=current):
        received=call(b,owner,cap,max_sites=1)
    assert received and received['via_at_nm']==proposed['via_at_nm']


@pytest.mark.parametrize('kwargs',[dict(max_sites=0),dict(max_sites=True),dict(max_sites=65),
    dict(max_feed_mm=2),dict(max_feed_mm=float('inf'))])
def test_bounded_finite_search_required(tmp_path,kwargs):
    b,owner,cap,bus,current=fixture(tmp_path)
    with pytest.raises(ValueError):call(b,owner,cap,**kwargs)
