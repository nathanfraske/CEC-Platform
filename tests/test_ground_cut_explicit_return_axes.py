"""Fresh nonrigid Source axes retain one physical Ground pickup, not authority."""
import copy,time
from pathlib import Path
import pcbnew,pytest
import cec_cell_ground_cut_boundaries as ground
import cec_control_shunt_ground_return_axes as axes
import cec_smd_macro_transport as transport
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_programming_ground_return_axes import case as programming_case
from test_control_shunt_ground_return_axes import case as control_case


def case(tmp_path,monkeypatch,turn=0,back=False,role='ILIM',cut=False):
    if role=='control':
        source,posed,p,request,via,tail=control_case(tmp_path,monkeypatch,turn,back)
    else:
        source,posed,p,request,via,tail,_=programming_case(tmp_path,monkeypatch,turn,back,role=='monitor')
    cut_id=None
    if cut:
        # A mid-pickup branch is deliberately NOT incident on the exclusive
        # barrel or its owner pad. Its separate cut leaves a real fixed debt.
        u=((1,0),(0,1),(-1,0),(0,-1))[turn];v=(-u[1],u[0])
        start=tail.GetStart()+pcbnew.VECTOR2I(*(n*500000 for n in u))
        end=start-pcbnew.VECTOR2I(*(n*2000000 for n in v))
        branch=pcbnew.PCB_TRACK(source);branch.SetNetCode(via.GetNetCode());branch.SetLayer(tail.GetLayer())
        branch.SetWidth(200000);branch.SetStart(start);branch.SetEnd(end);source.Add(branch);cut_id=force._uid(branch)
        fixed=pcbnew.PCB_VIA(source);fixed.SetNetCode(via.GetNetCode());fixed.SetPosition(end)
        fixed.SetWidth(900000);fixed.SetDrill(500000);fixed.SetViaType(pcbnew.VIATYPE_THROUGH)
        fixed.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);source.Add(fixed)
        field._save_field_snapshot(source,source.GetFileName())
        posed=pcbnew.LoadBoard(source.GetFileName())
        for ref,target in p['poses'].items():
            fp=posed.FindFootprintByReference(ref);fp.SetPosition(pcbnew.VECTOR2I(*(round(n*1e6)for n in target[:2])));fp.SetOrientationDegrees(target[2])
    p.update(scope='source_typed_complete_cell_escape_proposal',source_native_binding=ground.row._source_binding(source),
        retired_track_uuids=[] if cut_id is None else [cut_id],selected_bypasses={},device_contracts={})
    packet=transport.apply(source,posed,source_path=Path(source.GetFileName()),board_hint=p['board_hint'],
        source_control_ground_return_axes=[request],timeout_s=9.1)
    if cut_id is not None:discard_items(posed,[t for t in posed.GetTracks()if force._uid(t)==cut_id])
    # Exercise actual saved native geometry, not merely the constructor RAM.
    target=tmp_path/'posed.kicad_pcb'
    try:field._save_field_snapshot(posed,target)
    except ValueError:
        actual=pcbnew.LoadBoard(str(target));before=field._field_snapshot_inventory(posed);after=field._field_snapshot_inventory(actual)
        raise AssertionError([(key,before.get(key),after.get(key))for key in set(before)|set(after)if before.get(key)!=after.get(key)])
    posed=pcbnew.LoadBoard(str(target))
    return source,posed,p,copy.deepcopy(packet['source_process_barrel_motion']),force._uid(via),force._uid(tail)


@pytest.mark.parametrize('role',['ILIM','monitor','control'])
@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_saved_axis_and_pickup_keep_physical_keys_with_one_fresh_replay(tmp_path,monkeypatch,role,turn,back):
    source,posed,p,proofs,vid,tid=case(tmp_path,monkeypatch,turn,back,role)
    old={force._uid(t):t for t in source.GetTracks()};new={force._uid(t):t for t in posed.GetTracks()}
    before=[ground.row._source_binding(b)for b in(source,posed)];saved=[Path(b.GetFileName()).read_bytes()for b in(source,posed)]
    original=axes.derive;calls=[]
    def observe(*a,**kw):calls.append(copy.deepcopy(a[3]));return original(*a,**kw)
    monkeypatch.setattr(axes,'derive',observe)
    mapping=ground._transported_barrel_keys(source,posed,proofs,time.monotonic()+9.1,source_proposal=p)
    assert calls==[[{k:proofs[0]['source_control_shunt_return_axis'][k]for k in('owner_pad_uuid','position_nm')}]]
    assert mapping=={force._item_key(new[u]):force._item_key(old[u])for u in(vid,tid)}
    assert before==[ground.row._source_binding(b)for b in(source,posed)]
    assert saved==[Path(b.GetFileName()).read_bytes()for b in(source,posed)]


@pytest.mark.parametrize('fault',['default','producer_role','producer_target','producer_bool','producer_extra','outer_uuid',
    'outer_owner','outer_footprint','basis','rigid_flag','count_flag','target','tail_width','tail_layer','tail_lock',
    'tail_mask','tail_group','tail_endpoint','tail_missing','via_width','via_inner_width','via_drill','via_lock','pad_size',
    'class','source_tail','proposal_pose'])
def test_no_claim_or_material_change_can_turn_a_reseat_into_a_comparison_alias(tmp_path,monkeypatch,fault):
    source,posed,p,proofs,vid,tid=case(tmp_path,monkeypatch)
    record=proofs[0]['source_control_shunt_return_axis'];new={force._uid(t):t for t in posed.GetTracks()}
    tail=new[tid];via=new[vid];pad=next(pad for fp in posed.GetFootprints()for pad in fp.Pads()if force._uid(pad)==record['owner_pad_uuid'])
    supplied=p
    if fault=='default':supplied=None
    elif fault=='producer_role':record['source_programming_resistor']['current_authority']=True
    elif fault=='producer_target':record['position_nm'][0]+=1000
    elif fault=='producer_bool':record['maximum_return_nm']=True
    elif fault=='producer_extra':record['permit']=True
    elif fault=='outer_uuid':proofs[0]['uuid']='not-the-physical-Source-barrel'
    elif fault=='outer_owner':proofs[0]['source_owner_pad_uuids']=['not-a-pad']
    elif fault=='outer_footprint':proofs[0]['owner_footprint_uuids']=['not-the-owner']
    elif fault=='basis':proofs[0]['actual_source_ownership_basis']='nearby-same-Ground'
    elif fault=='rigid_flag':proofs[0]['original_barrel_geometry_count_and_relative_owner_seat_preserved']=True
    elif fault=='count_flag':proofs[0]['original_barrel_geometry_and_count_preserved']=1
    elif fault=='target':via.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='tail_width':tail.SetWidth(tail.GetWidth()+1)
    elif fault=='tail_layer':tail.SetLayer(pcbnew.In2_Cu)
    elif fault=='tail_lock':tail.SetLocked(not tail.IsLocked())
    elif fault=='tail_mask':tail.SetHasSolderMask(not tail.HasSolderMask())
    elif fault=='tail_group':
        group=pcbnew.PCB_GROUP(posed);group.SetName('foreign retained pickup');posed.Add(group);group.AddItem(tail)
    elif fault=='tail_endpoint':tail.SetEnd(tail.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='tail_missing':discard_items(posed,[tail])
    elif fault=='via_width':via.SetWidth(via.GetWidth(pcbnew.F_Cu)+1)
    elif fault=='via_inner_width':via.SetWidth(pcbnew.In2_Cu,via.GetWidth(pcbnew.In2_Cu)+1)
    elif fault=='via_drill':via.SetDrill(via.GetDrillValue()+1)
    elif fault=='via_lock':via.SetLocked(not via.IsLocked())
    elif fault=='pad_size':pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='class':
        path=Path(source.GetFileName()).with_suffix('.kicad_pro');path.write_text(path.read_text().replace('"track_width": 0.5','"track_width": 0.51'))
    elif fault=='source_tail':next(t for t in source.GetTracks()if force._uid(t)==tid).SetWidth(499999)
    elif fault=='proposal_pose':p['poses'][pad.GetParentFootprint().GetReference()][0]+=.01
    before=[ground.row._source_binding(b)for b in(source,posed)]
    with pytest.raises(ValueError):ground._transported_barrel_keys(source,posed,proofs,time.monotonic()+9.1,source_proposal=supplied)
    assert before==[ground.row._source_binding(b)for b in(source,posed)]


@pytest.mark.parametrize('monitor',[False,True])
@pytest.mark.parametrize('back',[False,True])
def test_actual_saved_Ground_requests_restore_retained_fragment_after_nonrigid_pickup(tmp_path,monkeypatch,monitor,back):
    source,posed,p,proofs,vid,tid=case(tmp_path,monkeypatch,back=back,role='monitor'if monitor else'ILIM',cut=True)
    original=axes.derive;calls=[]
    def observe(*a,**kw):calls.append(True);return original(*a,**kw)
    monkeypatch.setattr(axes,'derive',observe)
    before=[ground.row._source_binding(b)for b in(source,posed)]
    requests=ground.requests(source,posed,p,timeout_s=9.1,transported_source_barrels=proofs)
    assert len(calls)==1 and len(requests)==1
    request=next(iter(requests.values()));fragment=request['retained_source_ground_fragment']
    assert request['kind']=='ground_boundary'and request['width_nm']==500000
    assert fragment['retired_ground_track_uuids']==p['retired_track_uuids']
    assert fragment['actual_fixed_source_contacts_not_same_net_proximity']
    assert fragment['low_power_source_cut_restoration_not_aggregate_ground_rating']
    assert fragment['whole_original_current_plane_and_saved_partition_receiving_required']
    assert before==[ground.row._source_binding(b)for b in(source,posed)]


@pytest.mark.parametrize('monitor',[False,True])
@pytest.mark.parametrize('back',[False,True])
def test_saved_mapped_resistor_axis_rederives_actual_closed_reference_authorization(tmp_path,monkeypatch,monitor,back):
    from test_programming_ground_reference_group import mapped_case
    source,posed,p,request,gid,vid,tid=mapped_case(tmp_path,monkeypatch,turn=1,back=back,monitor=monitor)
    p.update(scope='source_typed_complete_cell_escape_proposal',source_native_binding=ground.row._source_binding(source),
        retired_track_uuids=[],selected_bypasses={},device_contracts={})
    packet=transport.apply(source,posed,source_path=Path(source.GetFileName()),board_hint=p['board_hint'],
        reference_group_uuids=p['reference_group_uuids'],source_control_ground_return_axes=[request],timeout_s=9.1)
    target=tmp_path/'saved-mapped-pose.kicad_pcb';field._save_field_snapshot(posed,target);posed=pcbnew.LoadBoard(str(target))
    proofs=packet['source_process_barrel_motion'];original=axes.derive;calls=[]
    def observe(*a,**kw):
        assert a[2]['reference_group_uuids']==[gid]
        calls.append(True);return original(*a,**kw)
    monkeypatch.setattr(axes,'derive',observe)
    old={force._uid(t):t for t in source.GetTracks()};new={force._uid(t):t for t in posed.GetTracks()}
    before=[ground.row._source_binding(b)for b in(source,posed)]
    mapping=ground._transported_barrel_keys(source,posed,proofs,time.monotonic()+9.1,source_proposal=p)
    assert len(calls)==1 and mapping=={force._item_key(new[u]):force._item_key(old[u])for u in(vid,tid)}
    role=proofs[0]['source_control_shunt_return_axis']['source_programming_resistor']
    assert role['source_reference_group_authorization']['group_uuid']==gid
    assert len(list(next(g for g in posed.Groups()if force._uid(g)==gid).GetItems()))==6
    assert before==[ground.row._source_binding(b)for b in(source,posed)]
