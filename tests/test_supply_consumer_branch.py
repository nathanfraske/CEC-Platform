"""Local allocations never turn a shared rail or unknown load into a signal."""
import copy
import math
import time
import pcbnew
import pytest
import cec_supply_consumer_branch as branch
import cec_force_current as force
import cec_field_coupling as field
import cec_constraints as constraints
import cec_synth_pipeline as synth
import cec_current_topology as topology
import cec_route_dimensions as dimensions


def fixture(monkeypatch, tmp_path, name='/unrelated/POWER', angle=0, mirror=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    nets={}
    for n in (name,'GND','IO'):
        net=pcbnew.NETINFO_ITEM(b,n);b.Add(net);nets[n]=net
    def fp(ref,value,fpid,mpn,pins):
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetValue(value)
        f.SetFPID(pcbnew.LIB_ID(*fpid.split(':')));b.Add(f)
        if mpn:
            f.SetField('MPN',mpn)
        for pin,n,xy in pins:
            p=pcbnew.PAD(f);p.SetNumber(pin);p.SetNet(nets[n]);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(1,1));p.SetLayerSet(pcbnew.PAD.SMDMask())
            p.SetPosition(pcbnew.VECTOR2I_MM(*xy));f.Add(p)
        return f
    owner=fp('NOT_A_U','TJA1051T/3','Pkg:SOIC-8_3.9x4.9mm_P1.27mm','TJA1051T/3/1J',
        [('3',name,(5,5)),('5','IO',(5,8))])
    cap=fp('NOT_A_C','100nF','Any:C_0402_1005Metric','CL05B104KO5NNNC',
        [('1',name,(7,5)),('2','GND',(7,3))])
    a=fp('ANY_PORT','test','Any:Port',None,[('1',name,(15,5))]).FindPadByNumber('1')
    z=fp('OTHER_PORT','test','Any:Port',None,[('1',name,(18,5))]).FindPadByNumber('1')
    def track(x,y,width=.2):
        t=pcbnew.PCB_TRACK(b);t.SetNet(nets[name]);t.SetLayer(pcbnew.F_Cu);t.SetWidth(round(width*1e6))
        t.SetStart(pcbnew.VECTOR2I_MM(*x));t.SetEnd(pcbnew.VECTOR2I_MM(*y));t.SetLocked(True);b.Add(t);return t
    old=track((5,5),(7,5),.5);trunk=track((15,5),(18,5),.5);new=track((7,5),(15,5))
    row=dict(net=name,device_package='TJA1051T/3 SO8',pin='3',amps=.5,maximum_consumers=1,basis='existing local allocation')
    declaration=dict(params=dict(supply_consumer_allocations=[row]))
    rail=dict(amps=3.,source='board_design_basis',geometry_margin=1.25,margin_included=False)
    monkeypatch.setattr(branch.policy,'load',lambda *a,**k:copy.deepcopy(declaration))
    monkeypatch.setattr(synth,'spec_net_current_contract',lambda *a,**k:dict(rail))
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**k:{})
    monkeypatch.setattr(dimensions,'project_resolver',lambda *a,**k:lambda n:dict(track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3))
    root=owner.FindPadByNumber('3')
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        if angle:item.Rotate(pcbnew.VECTOR2I_MM(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirror:item.Flip(pcbnew.VECTOR2I_MM(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    g=branch.record(b,[new],[],root_pad_uuid=force._uid(root),anchor_uuid=force._uid(a))
    source=tmp_path/'board.kicad_pcb';field._save_field_snapshot(b,source);b.SetFileName(str(source))
    return b,root,a,new,old,trunk,g,row,rail,declaration,cap


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_real_native_exclusive_branch_is_rotation_layer_and_reference_independent(monkeypatch,tmp_path,angle,mirror):
    b,root,a,new,old,trunk,g,row,rail,declaration,cap=fixture(monkeypatch,tmp_path,angle=angle,mirror=mirror)
    before=field._field_snapshot_inventory(b)
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert result['complete'] and result['proofs'],result
    assert set(result['track_requirements'])=={force._uid(new)}
    q=result['proofs'][0];assert q['budget']['current_authority']['amps']==.5
    assert q['budget']['aggregate_current_authority']['amps']==3.
    assert not q['inrush_fault_barrel_and_release_qualified'] and not q['release_authority']
    assert q['physical_trunk_tap_count']==1 and q['shared_terminal_partitions_preserved']
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['missing','too_small','whole_rail','boolean','unknown_package','wrong_pin',
    'wrong_cap','unknown_cap','extra_load','duplicate_group','thin','disconnected','second_tap'])
def test_uncertain_or_nonexclusive_route_keeps_the_full_aggregate_requirement(monkeypatch,tmp_path,fault):
    b,root,a,new,old,trunk,g,row,rail,declaration,cap=fixture(monkeypatch,tmp_path)
    if fault=='missing':declaration['params']['supply_consumer_allocations']=[]
    elif fault=='too_small':row['amps']=.01
    elif fault=='whole_rail':row['amps']=3.
    elif fault=='boolean':row['amps']=True
    elif fault=='unknown_package':
        root.GetParentFootprint().SetValue('UNKNOWN')
        root.GetParentFootprint().SetField('MPN','UNKNOWN')
    elif fault=='wrong_pin':row['pin']='5'
    elif fault=='wrong_cap':cap.FindPadByNumber('2').SetNet(root.GetNet())
    elif fault=='unknown_cap':cap.SetValue('10uF')
    elif fault=='extra_load':
        f=pcbnew.FOOTPRINT(b);f.SetValue('UNKNOWN');b.Add(f);p=pcbnew.PAD(f);f.Add(p);p.SetNet(root.GetNet())
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetPosition(root.GetPosition())
    elif fault=='duplicate_group':
        other=pcbnew.PCB_GROUP(b);other.SetName(g.GetName());b.Add(other)
    elif fault=='thin':new.SetWidth(100000)
    elif fault=='disconnected':new.SetStart(pcbnew.VECTOR2I_MM(10,5))
    else:
        trunk.SetStart(pcbnew.VECTOR2I_MM(10,5))
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert not result['complete'] and not result['track_requirements'] and result['refusals'],result


def test_current_model_sizes_only_the_received_exact_branch_and_leaves_bad_shared_copper_bad(monkeypatch,tmp_path):
    b,root,a,new,old,trunk,g,row,rail,declaration,cap=fixture(monkeypatch,tmp_path)
    trunk.SetWidth(200000)
    monkeypatch.setattr(topology,'current_contract_for_net',lambda *a,**k:dict(rail))
    monkeypatch.setattr(constraints,'_legal_neckdown_uuids',lambda *a,**k:set())
    monkeypatch.setattr(constraints,'_validated_current_supply_escape_uuids',lambda *a,**k:set())
    path=b.GetFileName();field._save_field_snapshot(b,path)
    result=constraints.CHECKERS['trace-width-high-current'](b,path,{})
    assert result[0] is False,result
    faults=[r for r in result[2] if r.get('type')=='keepout']
    assert force._uid(trunk) in {r['uuid'] for r in faults}
    assert force._uid(new) not in {r['uuid'] for r in faults}
    assert next(r for r in result[2] if r.get('type')=='current_debt_inventory')['typed_supply_consumer_receiving']['complete']


def test_expired_native_proof_cannot_grant_an_allocation(monkeypatch,tmp_path):
    b,*_=fixture(monkeypatch,tmp_path)
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=.000001)
    assert not result['complete'] and not result['track_requirements']


def test_display_value_does_not_replace_selected_manufacturer_identity(monkeypatch,tmp_path):
    b,root,*_=fixture(monkeypatch,tmp_path)
    root.GetParentFootprint().SetValue('unrelated display text')
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert result['complete'] and result['proofs'],result


def test_allocation_is_sized_with_the_existing_margin_exactly_once(monkeypatch,tmp_path):
    b,root,a,new,old,trunk,g,row,rail,*_=fixture(monkeypatch,tmp_path)
    result=branch.contract(b,force._uid(root),board_hint='arbitrary')
    expected=dimensions.current_trace_widths(dict(rail,amps=.5),
        tuple(result['required_by_layer_mm']), 'jlcpcb_6l_pofv_signal',rise_c=30.)
    assert result['aggregate_current_authority']==rail
    for layer,width in result['required_by_layer_mm'].items():
        assert width==pytest.approx(max(.2,expected[layer],dimensions.board_limits(b)['track_width']))
    # This profile has 0.5 oz inner copper: an outer-sized branch is not legal
    # merely because the same allocated current has been proved at its root.
    new.SetLayer(pcbnew.In2_Cu)
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert not result['complete'] and not result['track_requirements']


def test_saved_native_group_must_reproduce_the_same_proof(monkeypatch,tmp_path):
    b,root,a,new,*_=fixture(monkeypatch,tmp_path)
    expected=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    loaded=pcbnew.LoadBoard(b.GetFileName())
    actual=branch.inventory(loaded,board_hint='arbitrary',timeout_s=10.)
    assert actual==expected


def test_allocation_cannot_be_reused_for_a_second_selected_consumer(monkeypatch,tmp_path):
    b,root,*_=fixture(monkeypatch,tmp_path)
    f=pcbnew.FOOTPRINT(b);f.SetValue('TJA1051T/3');f.SetReference('OTHER_ARBITRARY_NAME')
    f.SetFPID(pcbnew.LIB_ID('Pkg','SOIC-8_3.9x4.9mm_P1.27mm'));f.SetField('MPN','TJA1051T/3/1J')
    b.Add(f);p=pcbnew.PAD(f);p.SetNumber('3');p.SetNet(root.GetNet());p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(1,1));p.SetPosition(pcbnew.VECTOR2I_MM(25,5));f.Add(p)
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert not result['complete'] and not result['track_requirements']


def test_unknown_capacitor_cross_supply_cannot_be_counted_as_selected_io_bypass(monkeypatch,tmp_path):
    b,root,a,new,old,trunk,g,row,rail,declaration,cap=fixture(monkeypatch,tmp_path)
    net=pcbnew.NETINFO_ITEM(b,'UNRELATED_LOAD_SUPPLY');b.Add(net)
    cap.FindPadByNumber('2').SetNet(net)
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert not result['complete'] and not result['track_requirements']


def track_tap_fixture(monkeypatch,tmp_path):
    b,root,a,new,old,trunk,g,row,rail,declaration,cap=fixture(monkeypatch,tmp_path)
    budget=branch.contract(b,force._uid(root),board_hint='arbitrary')
    trunk.SetWidth(math.ceil(budget['aggregate_required_by_layer_mm']['F.Cu']*1e6))
    def via(x,y):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(x,y));v.SetNet(root.GetNet())
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(v);return v
    via(7,5)  # Retained actual source-island portal, not new trunk capacity.
    tap=via(16.5,5)
    new.SetLayer(pcbnew.In2_Cu);new.SetWidth(500000);new.SetEnd(tap.GetPosition())
    g.SetName(branch.PREFIX+'|'.join((force._uid(root),force._uid(trunk),force._uid(tap))))
    return b,root,new,trunk,g,tap


def test_one_actual_barrel_lands_on_retained_rated_track_without_redundant_tail(monkeypatch,tmp_path):
    b,root,new,trunk,g,tap=track_tap_fixture(monkeypatch,tmp_path)
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert result['complete'] and result['proofs'],result
    q=result['proofs'][0]
    assert q['tap_capture_mode']=='retained_track_single_ordinary_barrel'
    assert q['tap_capture_via_uuid']==force._uid(tap)
    assert q['physical_trunk_tap_count']==1 and q['aggregate_rail_budget_unchanged']
    assert set(result['track_requirements'])=={force._uid(new)}
    assert not q['inrush_fault_barrel_and_release_qualified'] and not q['release_authority']


def test_capture_self_intersection_is_exact_identity_at_translated_native_coordinates(monkeypatch,tmp_path):
    b,root,new,trunk,g,tap=track_tap_fixture(monkeypatch,tmp_path)
    displacement=pcbnew.VECTOR2I_MM(39.25,54.2)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Move(displacement)
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert result['complete'] and result['proofs'],result
    assert result['proofs'][0]['tap_capture_via_uuid']==force._uid(tap)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('second_contact',[False,True])
def test_retained_capture_intersection_identity_does_not_waive_other_shared_contacts(
        monkeypatch,tmp_path,quarter,second_contact):
    from shapely.geometry.base import BaseGeometry
    import cec_kelvin_copper_cut as cut
    b,root,new,trunk,g,tap=track_tap_fixture(monkeypatch,tmp_path)
    # The barrel already exists in the source. It is the tap aperture, NOT
    # an incoming barrel in the consumer's proposed material group.
    g.SetName(branch.PREFIX+'|'.join((force._uid(root),force._uid(tap),'')))
    if second_contact:
        retained=pcbnew.PCB_TRACK(b);retained.SetNet(root.GetNet())
        retained.SetLayer(pcbnew.In2_Cu);retained.SetWidth(500000)
        retained.SetStart(tap.GetPosition());retained.SetEnd(pcbnew.VECTOR2I_MM(10,5))
        b.Add(retained)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I(41273001,-8137703))
    captured=cut._shape(tap,pcbnew.In2_Cu,False,
        cut._Work(time.monotonic()+2.))
    original=BaseGeometry.covers
    injected=[]
    def unreliable_self_boundary(shape,other):
        # Reproduce the floating-predicate failure at an exact capture
        # intersection without broadening copper or adding any epsilon.
        if shape.wkb==captured.wkb:
            injected.append(True)
            return False
        return original(shape,other)
    monkeypatch.setattr(BaseGeometry,'covers',unreliable_self_boundary)
    before=field._field_snapshot_inventory(b)
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    if second_contact:
        assert not result['complete'] and not result['track_requirements']
        assert any('consumer_has_second_physical_shared_rail_tap' in r['reason']
            for r in result['refusals'])
        assert injected  # Other UUID contacts still receive strict containment.
    else:
        assert result['complete'] and result['proofs'],result
        assert not injected  # A intersect capture is a subset by identity.
        assert result['proofs'][0]['physical_trunk_tap_count']==1
        assert result['proofs'][0]['aggregate_rail_budget_unchanged']
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['oversized_aperture','undersized_shared_anchor','second_contact','second_barrel','off_track_capture'])
def test_track_tap_cannot_hide_a_second_trunk_tap_or_undersized_shared_material(monkeypatch,tmp_path,fault):
    b,root,new,trunk,g,tap=track_tap_fixture(monkeypatch,tmp_path)
    if fault=='oversized_aperture':tap.SetWidth(800000)
    elif fault=='undersized_shared_anchor':trunk.SetWidth(200000)
    elif fault=='off_track_capture':
        tap.Move(pcbnew.VECTOR2I(0,trunk.GetWidth()+tap.GetWidth(tap.TopLayer())))
    elif fault=='second_contact':
        t=pcbnew.PCB_TRACK(b);t.SetNet(root.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
        t.SetStart(tap.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(18,5));b.Add(t);g.AddItem(t)
    else:
        other=pcbnew.PCB_VIA(b);other.SetNet(root.GetNet());other.SetPosition(pcbnew.VECTOR2I_MM(15,5))
        other.SetWidth(600000);other.SetDrill(300000);other.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        other.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(other)
        g.SetName(g.GetName()+','+force._uid(other))
    result=branch.inventory(b,board_hint='arbitrary',timeout_s=10.)
    assert not result['complete'] and not result['track_requirements'] and result['refusals'],result
