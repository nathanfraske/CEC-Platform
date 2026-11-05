"""All-layer priority checks precede macro boundary reconstruction."""
import pcbnew
import pytest
import cec_macro_priority_preflight as priority
import cec_smd_macro_transport as macro
import cec_field_coupling as field
import cec_force_current as force
from test_local_pofv_ownership import fixture


def native_pair(tmp_path,monkeypatch,layer,at=(21,30),mode='basis'):
    a,v=fixture(offset=(0,0),connected=False)
    net=pcbnew.NETINFO_ITEM(a,'/UNRELATED_HOT');a.Add(net)
    t=pcbnew.PCB_TRACK(a);t.SetStart(pcbnew.VECTOR2I_MM(at[0],at[1]-2));t.SetEnd(pcbnew.VECTOR2I_MM(at[0],at[1]+2))
    t.SetWidth(600000);t.SetLayer(layer);t.SetNet(net);a.Add(t)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(a,path)
    a,b=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0));r=macro.apply(a,b)
    monkeypatch.setattr(priority.topology,'route_width_contracts',lambda *a,**k:{
        '/UNRELATED_HOT':dict(current_authority=dict(source='board_design_basis' if mode=='basis' else 'component_power_budget'))})
    monkeypatch.setattr(priority.fr,'locked_pour_authority_nets_board',lambda *a,**k:
        {'/UNRELATED_HOT'} if mode=='pour' else set())
    return a,b,r,t.m_Uuid.AsString()


@pytest.mark.parametrize('layer',[0,2,6,8])
@pytest.mark.parametrize('mode',['basis','pour'])
def test_a_moved_barrel_cannot_drill_another_faces_priority_trace(tmp_path,monkeypatch,layer,mode):
    a,b,r,uid=native_pair(tmp_path,monkeypatch,layer,mode=mode)
    before=field._field_snapshot_inventory(b)
    result=priority.inspect(a,b,r,board_hint='SYNTHETIC')
    assert result['complete'] and not result['ok']
    assert any(q['retained_priority_uuid']==uid and q['layer_id']==layer for q in result['conflicts'])
    assert before==field._field_snapshot_inventory(b)
    assert not result['routing_admitted'] and not result['current_or_clearance_qualified']


@pytest.mark.parametrize('layer',[0,2,6,8])
def test_native_clearance_not_a_big_placement_bbox_decides_free_space(tmp_path,monkeypatch,layer):
    a,b,r,uid=native_pair(tmp_path,monkeypatch,layer,at=(26,30))
    result=priority.inspect(a,b,r,board_hint='SYNTHETIC')
    assert result['ok'] and not result['conflicts'] and not result['release_authority']


def test_component_budget_is_not_silently_promoted_to_board_force_bus_authority(tmp_path,monkeypatch):
    a,b,r,uid=native_pair(tmp_path,monkeypatch,8,mode='component')
    result=priority.inspect(a,b,r,board_hint='SYNTHETIC')
    assert result['ok'] and not result['protected_nets']
    assert not result['current_or_clearance_qualified']


def test_existing_priority_track_cannot_be_moved_out_of_the_obstacle_inventory(tmp_path,monkeypatch):
    a,b,r,uid=native_pair(tmp_path,monkeypatch,8)
    r['changes'].append(dict(uuid=uid))
    result=priority.inspect(a,b,r,board_hint='SYNTHETIC')
    assert not result['ok'] and result['moved_priority_source_conductor_uuids']==[uid]


def local_escape_pair(tmp_path,monkeypatch,shift=(0,-.2),layer=pcbnew.B_Cu):
    a,v=fixture(offset=(0,0),connected=False)
    t=pcbnew.PCB_TRACK(a);t.SetStart(v.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(20,34))
    t.SetLayer(layer);t.SetWidth(600000);t.SetNetCode(v.GetNetCode());a.Add(t)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(a,path)
    a,b=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(*shift));r=macro.apply(a,b)
    monkeypatch.setattr(priority.topology,'route_width_contracts',lambda *a,**k:{
        '/ARBITRARY':dict(current_authority=dict(source='board_design_basis'))})
    monkeypatch.setattr(priority.fr,'locked_pour_authority_nets_board',lambda *a,**k:set())
    return a,b,r,force._uid(t),force._uid(v)


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,6,8])
def test_positive_local_escape_extension_keeps_every_original_priority_pixel(tmp_path,monkeypatch,layer):
    a,b,r,t,v=local_escape_pair(tmp_path,monkeypatch,layer=layer)
    strict=priority.inspect(a,b,r,board_hint='SYNTHETIC')
    assert not strict['ok']
    before=field._field_snapshot_inventory(b)
    result=priority.inspect(a,b,r,board_hint='SYNTHETIC',extend_owned_local_power_escapes=True)
    assert result['ok'] and result['saved_current_receiving_required']
    assert result['source_owned_local_power_escape_extensions'][0]['uuid']==t
    assert result['rederived_local_power_owner_barrels'][0]['uuid']==v
    assert before==field._field_snapshot_inventory(b)
    assert not result['current_or_clearance_qualified'] and not result['routing_admitted']


@pytest.mark.parametrize('shift',[(0,.2),(1,0),(0,-1.1)])
def test_cut_shift_and_excess_local_power_motion_are_never_escape_extensions(tmp_path,monkeypatch,shift):
    a,b,r,t,v=local_escape_pair(tmp_path,monkeypatch,shift=shift)
    result=priority.inspect(a,b,r,board_hint='SYNTHETIC',extend_owned_local_power_escapes=True)
    assert not result['ok'] and not result['source_owned_local_power_escape_extensions']


def test_a_forged_report_does_not_grant_unowned_priority_barrel_motion(tmp_path,monkeypatch):
    a,b,r,t,v=local_escape_pair(tmp_path,monkeypatch)
    by={force._uid(x):x for x in b.GetTracks()};by[v].Move(pcbnew.VECTOR2I_MM(.1,0))
    result=priority.inspect(a,b,r,board_hint='SYNTHETIC',extend_owned_local_power_escapes=True)
    assert not result['ok'] and not result['source_owned_local_power_escape_extensions']


def test_thinning_an_extended_priority_escape_is_refused(tmp_path,monkeypatch):
    a,b,r,t,v=local_escape_pair(tmp_path,monkeypatch)
    next(x for x in b.GetTracks() if force._uid(x)==t).SetWidth(599999)
    result=priority.inspect(a,b,r,board_hint='SYNTHETIC',extend_owned_local_power_escapes=True)
    assert not result['ok']


def test_untyped_escape_extension_option_is_refused(tmp_path,monkeypatch):
    a,b,r,t,v=local_escape_pair(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='bounded_source_macro_priority_preflight'):
        priority.inspect(a,b,r,board_hint='SYNTHETIC',extend_owned_local_power_escapes=1)


def measurement_pair(tmp_path,monkeypatch,quarter=0):
    from test_measurement_leaf import fixture as measurement
    import cec_measurement_leaf as leaf
    a,pad,anchor,tracks,xy=measurement('/renamed/actual_force_net',quarter)
    path=tmp_path/'measurement-source.kicad_pcb';a.SetFileName(str(path));field._save_field_snapshot(a,path)
    parent=pcbnew.LoadBoard(str(path));child=pcbnew.LoadBoard(str(path))
    child.FindFootprintByReference('RENAMED_OWNER').Move(pcbnew.VECTOR2I_MM(.5,.5))
    transport=macro.apply(parent,child)
    q=leaf.plan(parent,force._uid(pad))
    monkeypatch.setattr(priority.topology,'route_width_contracts',lambda *a,**k:{
        q['net']:dict(current_authority=dict(source='board_design_basis'))})
    monkeypatch.setattr(priority.fr,'locked_pour_authority_nets_board',lambda *a,**k:{q['net']})
    return parent,child,transport,q


@pytest.mark.parametrize('quarter',range(4))
def test_exact_manufacturer_input_leaf_is_not_the_bus_with_the_same_net_name(tmp_path,monkeypatch,quarter):
    a,b,r,q=measurement_pair(tmp_path,monkeypatch,quarter)
    assert not priority.inspect(a,b,r,board_hint='opaque')['ok']
    before=field._field_snapshot_inventory(b)
    result=priority.inspect(a,b,r,board_hint='opaque',source_measurement_leaves=[q],
        retired_source_track_uuids=q['track_uuids'])
    assert result['ok'] and result['source_measurement_retirement_is_not_force_bus_retirement']
    assert result['independently_typed_source_measurement_reconstruction']==[q]
    assert result['protected_nets']==[q['net']] and not result['current_or_clearance_qualified']
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['scope','width','binding','point','track','pad','cut','duplicate','stationary'])
def test_priority_input_reconstruction_needs_the_entire_rederived_source_leaf(tmp_path,monkeypatch,fault):
    import copy
    a,b,r,q=measurement_pair(tmp_path,monkeypatch);q=copy.deepcopy(q)
    leaves=[q];retired=list(q['track_uuids'])
    if fault=='scope':q['scope']='arbitrary_net_waiver'
    elif fault=='width':q['width_nm']-=1
    elif fault=='binding':q['source_native_binding']='forged'
    elif fault=='point':q['points_nm'][0][0]+=1
    elif fault=='track':q['track_uuids'].pop()
    elif fault=='pad':q['pad_uuid']='foreign'
    elif fault=='cut':retired.pop()
    elif fault=='duplicate':leaves.append(copy.deepcopy(q))
    else:r['moved_owner_footprint_uuids']=[force._uid(a.FindFootprintByReference('FIXED'))]
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):priority.inspect(a,b,r,board_hint='opaque',
        source_measurement_leaves=leaves,retired_source_track_uuids=retired)
    assert before==field._field_snapshot_inventory(b)
