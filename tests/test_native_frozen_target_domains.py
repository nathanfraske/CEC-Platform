"""Moved target anchors are checked placements, never unchanged-Source waivers."""
import copy
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_force_current as force
import cec_native_cell_pose_domains as domains
from test_complete_macro_cell import fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_target_anchor_stays_moved_and_all_native_guards_receive_it(tmp_path,monkeypatch,quarter,back):
    source,parent,unused,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    raw=source.read_bytes();cap=next(iter(packet['source_plan']['selected_bypasses']))
    seed=packet['source_plan']['poses'];calls=[];actual=compiler.compile
    def observed(*args,**kwargs):
        calls.append(copy.deepcopy(kwargs));return actual(*args,**kwargs)
    monkeypatch.setattr(compiler,'compile',observed)
    result=domains.propose(source,seed,board_hint='opaque',transport_source_barrels=True,
        frozen_target_refs=[cap],max_obstacle_track_mm=24.,max_obstacle_tracks=12,
        radius_mm=.25,grid_mm=.25,max_candidates=16,max_results=4)
    assert result['offers'],{k:result[k] for k in ('domain_stages','fresh_receiving','search')}
    assert result['frozen_target_reference_refs']==[cap] and result['fixed_source_reference_refs']==[]
    choice=result['domains'][cap]
    assert len(choice)==1 and choice[0]['pose']==seed[cap]
    assert not choice[0]['exact_source_anchor_not_new_placement']
    assert choice[0]['frozen_target_requires_new_native_placement_checks']
    assert all(q['poses'][cap]==seed[cap] for q in result['offers'])
    assert len(calls)>=2 and all(q['max_obstacle_track_mm']==24. and q['max_obstacle_tracks']==12 for q in calls)
    assert result['fresh_receiving'][-1]['source_owned_macro_native_frame']['ok']
    assert source.read_bytes()==raw and not result['routing_admitted']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_frozen_pivot_preserves_its_entire_original_ground_entry(tmp_path,monkeypatch,quarter,back):
    import cec_field_coupling as field
    from cec_native_items import discard_items
    source,parent,unused,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    cap_ref=next(iter(packet['source_plan']['selected_bypasses']));cap=parent.FindFootprintByReference(cap_ref)
    gp=next(p for p in cap.Pads() if p.GetNetname()=='GND');old=tuple(cap.GetPosition());at=tuple(gp.GetPosition())
    # A direct Source in-pad root, not the independent extra Ground
    # dogbone that the other macro fixture intentionally also supplies.
    discard_items(parent,[t for t in parent.GetTracks() if t.GetNetname()=='GND' and
        (t.GetClass()=='PCB_VIA' and t.GetDrillValue()==300000
        or t.GetClass()=='PCB_TRACK' and at in (tuple(t.GetStart()),tuple(t.GetEnd())))])
    field._save_field_snapshot(parent,source)
    seed=copy.deepcopy(packet['source_plan']['poses'])
    seed[cap_ref]=[(2*at[i]-old[i])/1e6 for i in (0,1)]+[cap.GetOrientationDegrees()+180.]
    selected=packet['source_plan']['selected_bypasses'][cap_ref]
    owner=parent.FindFootprintByReference(selected['owner']);supply=owner.FindPadByNumber(selected['pin'])
    future=pcbnew.FOOTPRINT(cap);future.SetPosition(pcbnew.VECTOR2I_MM(*seed[cap_ref][:2]))
    future.SetOrientationDegrees(seed[cap_ref][2])
    target=next(p for p in future.Pads() if p.GetNetname()==selected['rail'])
    delta=[target.GetPosition()[i]-supply.GetPosition()[i] for i in (0,1)]
    length=sum(v*v for v in delta)**.5
    seed[selected['owner']]=[(owner.GetPosition()[i]+500000*delta[i]/length)/1e6 for i in (0,1)]+[owner.GetOrientationDegrees()]
    raw=source.read_bytes()
    result=domains.propose(source,seed,board_hint='opaque',transport_source_barrels=True,
        frozen_target_refs=[cap_ref],radius_mm=.25,grid_mm=.25,max_candidates=16,max_results=4)
    assert result['offers'],{k:result[k] for k in ('domain_stages','fresh_receiving','search')}
    witness=result['independently_retained_frozen_ground_entries'][cap_ref]
    assert witness['saved_return_mm']==0. and witness['full_class_direct_reference_reach_proved']
    assert source.read_bytes()==raw and not result['routing_admitted']


@pytest.mark.parametrize('back',[False,True])
def test_same_source_ground_barrel_reuse_does_not_invent_a_second_hole(tmp_path,monkeypatch,back):
    import cec_additive_route_receiving as additive
    import cec_field_coupling as field
    from cec_native_items import discard_items
    source,parent,unused,packet=fixture(tmp_path,monkeypatch,back=back)
    cap_ref=next(iter(packet['source_plan']['selected_bypasses']));cap=parent.FindFootprintByReference(cap_ref)
    gp=next(p for p in cap.Pads() if p.GetNetname()=='GND')
    discard_items(parent,[v for v in parent.GetTracks() if v.GetClass()=='PCB_VIA'
        and tuple(v.GetPosition())==tuple(gp.GetPosition())])
    gp.SetSize(pcbnew.VECTOR2I_MM(.9,.9))
    via=next(v for v in parent.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()=='GND'
        and v.GetDrillValue()==300000)
    old=tuple(cap.GetPosition());point=tuple(gp.GetPosition());at=tuple(via.GetPosition())
    additive._ground_refill(parent);field._save_field_snapshot(parent,source)
    raw=source.read_bytes()
    seed=copy.deepcopy(packet['source_plan']['poses'])
    # The entire 0.6 mm stationary disk fits this 0.9 mm land even with
    # a 0.1 mm offset. This is full material, not centre/proximity credit.
    seed[cap_ref]=[(at[i]-point[i]+old[i]+(100000 if i==0 else 0))/1e6 for i in (0,1)]+[cap.GetOrientationDegrees()]
    result=domains.propose(source,seed,board_hint='opaque',transport_source_barrels=True,
        frozen_target_refs=[cap_ref],reuse_ground_barrels=[dict(uuid=force._uid(via),owner_pad_uuid=force._uid(gp))],
        radius_mm=.25,grid_mm=.25,max_candidates=16,max_results=4)
    assert result['offers'],{k:result[k] for k in ('domain_stages','fresh_receiving','search')}
    witness=result['independently_retained_frozen_ground_entries'][cap_ref]
    assert witness['saved_return_mm']==0. and witness['via_uuid']==force._uid(via)
    assert result['fresh_receiving'][-1]['source_owned_macro_native_frame']['ok']
    assert source.read_bytes()==raw
    assert not result['routing_admitted'] and not result['release_authority']


@pytest.mark.parametrize('fault',['courtyard','copper','fresh_guard','pre_refill'])
def test_target_anchor_never_bypasses_native_or_fresh_receiving(tmp_path,monkeypatch,fault):
    import cec_field_coupling as field
    source,parent,unused,packet=fixture(tmp_path,monkeypatch)
    seed=packet['source_plan']['poses'];cap=next(iter(packet['source_plan']['selected_bypasses']))
    target=seed[cap];fp=parent.FindFootprintByReference(cap)
    if fault=='fresh_guard':
        monkeypatch.setattr(compiler,'native_pose_screen',lambda *a,**k:dict(ok=False,refusals=['required_test_refusal']))
    elif fault=='pre_refill':
        monkeypatch.setattr(compiler,'pre_refill_barrel_screen',lambda *a,**k:dict(ok=False,refusals=['required_test_refusal']))
    elif fault=='copper':
        item=pcbnew.PCB_TRACK(parent);item.SetNet(parent.FindNet('INPUT_P'));item.SetLayer(pcbnew.F_Cu)
        item.SetStart(pcbnew.VECTOR2I_MM(target[0]-.6,target[1]));item.SetEnd(pcbnew.VECTOR2I_MM(target[0]-.4,target[1]))
        item.SetWidth(200000);parent.Add(item);field._save_field_snapshot(parent,source)
    else:
        other=pcbnew.FOOTPRINT(parent);other.SetReference('IMMOVABLE_OTHER_BODY');parent.Add(other)
        shape=pcbnew.PCB_SHAPE(other);shape.SetShape(pcbnew.SHAPE_T_RECT);shape.SetLayer(pcbnew.F_CrtYd)
        shape.SetStart(pcbnew.VECTOR2I_MM(target[0]-.15,target[1]-.15))
        shape.SetEnd(pcbnew.VECTOR2I_MM(target[0]+.15,target[1]+.15));shape.SetWidth(50000);other.Add(shape)
        field._save_field_snapshot(parent,source)
    raw=source.read_bytes()
    result=domains.propose(source,seed,board_hint='opaque',transport_source_barrels=True,
        frozen_target_refs=[cap],radius_mm=.25,grid_mm=.25,max_candidates=16,max_results=4)
    assert not result['offers'] and not result['routing_admitted']
    if fault=='courtyard':assert result['domains'][cap]==[]
    if fault in ('fresh_guard','pre_refill'):
        assert result['fresh_receiving'] and all(not q['ok'] for q in result['fresh_receiving'])
    if fault=='pre_refill':
        assert all('actual_joint_bypass_ground_access' not in q for q in result['fresh_receiving'])
    assert source.read_bytes()==raw


@pytest.mark.parametrize('options',[
    dict(frozen_target_refs=None),dict(frozen_target_refs=True),dict(frozen_target_refs=['missing']),
    dict(frozen_target_refs=['owner','owner']),dict(frozen_target_refs=['owner'],fixed_refs=['owner']),
    dict(frozen_target_refs=['owner']),dict(reuse_ground_barrels=True),dict(ordinary_via_poses=True),
    dict(max_obstacle_track_mm=True),dict(max_obstacle_track_mm=33),dict(max_obstacle_track_mm=float('nan')),
    dict(max_obstacle_tracks=True),dict(max_obstacle_tracks=17),dict(max_obstacle_tracks=0),
    dict(max_obstacle_track_mm=24.),dict(ordinary_via_poses=[{}]),dict(reuse_ground_barrels=[{}]),
])
def test_anchor_and_explicit_work_options_refuse_invalid_scope_before_native_read(options):
    with pytest.raises(ValueError):
        domains.propose('not-a-source',{'owner':[0,0,0]},board_hint='opaque',**options)
