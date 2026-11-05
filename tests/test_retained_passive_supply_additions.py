"""Explicit synthetic current catalogs, real native Source-owned cap links."""
import copy
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_retained_passive_supply_additions as additions
import cec_pose_additive_reconstruction as receiving
from test_stationary_output_capacitor_owner import fixture as output_fixture
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    b,_,owner,cap,model,assignment=output_fixture(monkeypatch,'TPS2121RUXR')
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
    pin=assignment['assigned']['source_output']['requirement']['pin']
    power=owner.FindPadByNumber(pin);at=power.GetPosition()
    cap.SetPosition(pcbnew.VECTOR2I(at.x+1500000,at.y))
    for p in cap.Pads():
        p.SetPosition(pcbnew.VECTOR2I(at.x+(1000000 if p.GetNetname()!='GND' else 2000000),at.y))
    t=track(b,power.GetNetname(),tuple(v/1e6 for v in at),(at.x/1e6+1,at.y/1e6),width=.3)
    if back:
        for fp in (owner,cap):fp.Flip(pcbnew.VECTOR2I_MM(10,10),False)
        t.SetLayer(pcbnew.B_Cu)
        t.SetStart(power.GetPosition());t.SetEnd(next(p for p in cap.Pads() if p.GetNetname()!='GND').GetPosition())
    if quarter:
        pivot=pcbnew.VECTOR2I_MM(10,10);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in (owner,cap,t):item.Rotate(pivot,angle)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    old,child=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    cap=child.FindFootprintByReference(cap.GetReference())
    oldpad=next(p for p in cap.Pads() if p.GetNetname()!='GND')
    previous=tuple(oldpad.GetPosition());cap.Move(pcbnew.VECTOR2I(0,200000))
    pad=next(p for p in cap.Pads() if p.GetNetname()!='GND')
    new=track(child,pad.GetNetname(),tuple(v/1e6 for v in previous),
        tuple(v/1e6 for v in pad.GetPosition()),width=.3,layer=pcbnew.B_Cu if back else pcbnew.F_Cu)
    current=dict(required_by_layer_nm={int(pcbnew.F_Cu):230000,int(pcbnew.B_Cu):230000},
        current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='synthetic_test_only'))
    monkeypatch.setattr(additions.cells,'_supply_current_widths',lambda *a,**kw:copy.deepcopy(current))
    return old,child,force._uid(cap),new,current


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_native_output_cap_link_preserves_full_catalog_and_source_launch_width(
        tmp_path,monkeypatch,quarter,back):
    old,child,uid,new,current=fixture(tmp_path,monkeypatch,quarter,back)
    before=[field._field_snapshot_inventory(q) for q in (old,child)]
    r=additions.inspect(old,child,[uid],[force._uid(new)],board_hint='synthetic')
    root=r['components'][0]['source_selected_supply_roots'][0]
    assert root['source_owner_role']=='power_output'
    assert root['unchanged_full_rail_current_contract']==current
    assert root['width_floor_nm']==300000
    assert r['no_source_supply_conductor_barrel_or_pour_change_authorized']
    assert not r['routing_admitted'] and not r['release_authority']
    assert before==[field._field_snapshot_inventory(q) for q in (old,child)]


@pytest.mark.parametrize('flag',[1,'true',True])
def test_explicit_supply_tier_requires_the_actual_grounded_passive_mode(flag):
    r=receiving.receive('missing_source','missing_child',selected_footprint_uuids=['unknown'],
        board_hint='synthetic',allow_retained_capacitor_supply_additions=flag)
    assert not r['ok'] and r['errors']==['ValueError:bounded_explicit_connected_pose_scope_required']


def test_saved_atomic_capacitor_reconnection_is_opt_in_and_replays_all_source_material(tmp_path,monkeypatch):
    import cec_additive_route_receiving as additive
    import cec_smd_macro_transport as transport
    from test_retained_copper_passive_pose import fixture as retained_fixture
    source,_,uid,_=retained_fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));cap=next(f for f in b.GetFootprints() if force._uid(f)==uid)
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'));cap.SetValue('100nF')
    owner=pcbnew.FOOTPRINT(b);owner.SetReference('independent_owner');owner.SetValue('TLV7011DBVR')
    owner.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-5'))
    owner.SetPosition(pcbnew.VECTOR2I_MM(12,12));b.Add(owner)
    for pin,net,xy in [('1','/CONTROL',(10,10)),('2','GND',(11,10)),('3','/CONTROL',(12,10)),
            ('4','/CONTROL',(13,10)),('5','/CONTROL',(14.6,14))]:
        pad=pcbnew.PAD(owner);pad.SetNumber(pin);pad.SetNet(b.FindNet(net))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        owner.Add(pad);pad.SetPosition(pcbnew.VECTOR2I_MM(*xy))
    assignment=dict(assigned={'literal':dict(cap_ref=cap.GetReference(),requirement=dict(
        ref=owner.GetReference(),pin='5',rail='/CONTROL',kind='100n',return_rail='GND',
        return_pin=None,max_mm=3.5,source='synthetic_test_only'))})
    monkeypatch.setattr(additions.constraints,'_device_bypass_assignment',lambda *a,**kw:assignment)
    monkeypatch.setattr(additions.cells,'_supply_current_widths',lambda *a,**kw:dict(
        required_by_layer_nm={int(pcbnew.F_Cu):200000},current_authority=dict(
            amps=.5,geometry_margin=1.25,margin_included=False,source='synthetic_test_only')))
    field._save_field_snapshot(b,source)
    target=force._copy_family(source,tmp_path/'atomic-child')
    old,child=[pcbnew.LoadBoard(str(q)) for q in (source,target)]
    cap=next(f for f in child.GetFootprints() if force._uid(f)==uid)
    cap.Move(pcbnew.VECTOR2I_MM(.6,0))
    transport.apply(old,child,source_path=source,board_hint='synthetic',maximum_shift_mm=1.,
        allow_cardinal_rotations=True,retain_source_tracks=True,carry_ground_barrels_only=True)
    track(child,'/CONTROL',(15.2,14),(15.8,14),width=.2)
    additive._ground_refill(child);field._save_field_snapshot(child,target)
    before=[q.read_bytes() for q in (source,target)]
    options=dict(selected_footprint_uuids=[uid],board_hint='synthetic',max_shift_mm=1.,
        allow_source_ground_barrel_motion=True)
    denied=receiving.receive(source,target,**options)
    assert not denied['ok'] and denied['errors']==['ValueError:retained_copper_passive_pose_cannot_add_conductors']
    r=receiving.receive(source,target,**options,allow_retained_capacitor_supply_additions=True)
    assert r['ok'] and r['complete'],r
    assert r['all_original_terminal_and_copper_partitions_preserved']
    assert r['all_source_tracks_and_arcs_retained_exactly']
    assert r['no_source_power_or_signal_barrel_motion_authorized']
    assert r['source_owned_capacitor_supply_additions']['added_track_count']==1
    assert before==[q.read_bytes() for q in (source,target)]


def test_global_supply_connectivity_does_not_authorize_a_dangling_old_capacitor_pickup(tmp_path,monkeypatch):
    old,child,uid,new,current=fixture(tmp_path,monkeypatch)
    cap=next(f for f in child.GetFootprints() if force._uid(f)==uid)
    cap.Move(pcbnew.VECTOR2I(0,600000))
    pad=next(p for p in cap.Pads() if p.GetNetname()!='GND')
    owner=child.FindFootprintByReference('unrelated_names_owner')
    supply=next(p for p in owner.Pads() if p.GetNumber()=='1')
    new.SetStart(pad.GetPosition());new.SetEnd(pcbnew.VECTOR2I(supply.GetPosition().x,pad.GetPosition().y))
    tail=track(child,pad.GetNetname(),tuple(v/1e6 for v in new.GetEnd()),
        tuple(v/1e6 for v in supply.GetPosition()),width=.3)
    positive=next(p for f in old.GetFootprints() if force._uid(f)==uid for p in f.Pads() if p.GetNetname()!='GND')
    ports=additions.detached_leaf_ports(old,child,force._uid(positive))
    assert len(ports)==1 and ports[0]['at_nm']==list(positive.GetPosition())
    with pytest.raises(ValueError,match='detached_source_capacitor_pickup_must_be_rejoined'):
        additions.inspect(old,child,[uid],[force._uid(new),force._uid(tail)],board_hint='synthetic')


@pytest.mark.parametrize('fault',['narrow','foreign','wrong_layer','off_angle','remote','unattached',
    'barrel','old_identity','duplicate','owner_motion','unknown_owner','no_current','output_to_switch'])
def test_additive_permission_never_owns_other_nets_vias_motion_or_undersized_links(tmp_path,monkeypatch,fault):
    old,child,uid,new,current=fixture(tmp_path,monkeypatch)
    ids=[force._uid(new)]
    if fault=='narrow':new.SetWidth(299999)
    elif fault=='foreign':new.SetNet(child.FindNet('GND'))
    elif fault=='wrong_layer':new.SetLayer(pcbnew.In2_Cu)
    elif fault=='off_angle':new.SetEnd(new.GetEnd()+pcbnew.VECTOR2I(10000,0))
    elif fault in ('remote','unattached'):new.Move(pcbnew.VECTOR2I_MM(10 if fault=='remote' else 1,0))
    elif fault=='barrel':
        via=pcbnew.PCB_VIA(child);via.SetNet(new.GetNet());via.SetPosition(new.GetStart())
        via.SetWidth(600000);via.SetDrill(300000);child.Add(via);ids=[force._uid(via)]
    elif fault=='old_identity':ids=[force._uid(next(iter(old.GetTracks())))]
    elif fault=='duplicate':ids+=ids
    elif fault=='owner_motion':child.FindFootprintByReference('unrelated_names_owner').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='unknown_owner':child.FindFootprintByReference('unrelated_names_owner').SetValue('UNKNOWN')
    elif fault=='no_current':monkeypatch.setattr(additions.cells,'_supply_current_widths',lambda *a,**kw:None)
    elif fault=='output_to_switch':
        original=additions.roles.footprint_contract
        def changed(fp):
            model=original(fp)
            if model:
                model=copy.deepcopy(model)
                for pin,role in list(model['pins'].items()):
                    if role=='power_output':model['pins'][pin]='switch'
            return model
        monkeypatch.setattr(additions.roles,'footprint_contract',changed)
    before=[field._field_snapshot_inventory(q) for q in (old,child)]
    with pytest.raises(ValueError):additions.inspect(old,child,[uid],ids,board_hint='synthetic')
    assert before==[field._field_snapshot_inventory(q) for q in (old,child)]
