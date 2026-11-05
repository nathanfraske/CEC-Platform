import copy
import math

import pcbnew
import pytest

import cec_escape_pose_frontier as frontier
import cec_cell_row_rebuild as row
import cec_force_current as force
from test_compact_ground_dogbone import fixture


@pytest.mark.parametrize('name,angle,layer', [('renamed_A',0,pcbnew.F_Cu),
    ('unrelated_name',90,pcbnew.B_Cu)])
def test_actual_factory_return_preflight_is_read_only(name,angle,layer):
    board,pad = fixture(angle=angle,layer=layer)
    pad.GetParentFootprint().SetReference(name)
    before = row._source_binding(board)
    proof = frontier.ground_screen(board,[name],board_path='opaque')
    assert proof['ok'] and proof['required'] == 1
    assert proof['results'][0]['return_proof']['distance_mm'] <= .8
    assert not proof['routing_admitted'] and not proof['release_authority']
    assert row._source_binding(board) == before and not list(board.GetTracks())


@pytest.mark.parametrize('layer',[pcbnew.In2_Cu,pcbnew.B_Cu])
def test_courtyard_legal_surface_land_over_foreign_bus_cannot_get_barrel(layer):
    board,pad = fixture()
    net=pcbnew.NETINFO_ITEM(board,'RENAMED_FORCE');board.Add(net)
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(layer)
    track.SetStart(pcbnew.VECTOR2I_MM(10,15));track.SetEnd(pcbnew.VECTOR2I_MM(20,15))
    track.SetWidth(pcbnew.FromMM(5));track.SetLocked(True);board.Add(track)
    before=row._source_binding(board)
    proof=frontier.ground_screen(board,['IC_RENAMED'],board_path='opaque')
    assert not proof['ok'] and not proof['no_path_proof']
    assert proof['error'] == 'immediate_all_layer_return_refused'
    assert row._source_binding(board) == before
    assert force._uid(track) in {force._uid(t) for t in board.GetTracks()}


def test_return_exception_cannot_leave_private_copper_or_groups(monkeypatch):
    board,pad=fixture();before=row._source_binding(board)
    def throw(board,*a,**kw):
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(20,20));board.Add(via)
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(via)
        raise RuntimeError('injected factory failure')
    monkeypatch.setattr(frontier.cell,'_add_ground_return',throw)
    with pytest.raises(RuntimeError,match='injected factory failure'):
        frontier.ground_screen(board,['IC_RENAMED'],board_path='opaque')
    assert row._source_binding(board) == before


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_whole_cell_quarter_turn_is_native_relationship_preserving(angle):
    board,pad=fixture();owner=pad.GetParentFootprint()
    owner.SetPosition(pcbnew.VECTOR2I_MM(15,15))
    peer=pcbnew.FOOTPRINT(board);peer.SetReference('arbitrary_follower');board.Add(peer)
    peer.SetPosition(pcbnew.VECTOR2I_MM(18,13))
    poses=frontier.rigid_poses(board,[owner.GetReference(),peer.GetReference()],
        owner.GetReference(),(1,2),angle)
    x,y=poses[peer.GetReference()][:2];a,b=poses[owner.GetReference()][:2]
    assert math.dist((x,y),(a,b)) == pytest.approx(math.sqrt(13),abs=1e-5)
    # Compare KiCad's actual transform of the owner's pad vector.
    p0=tuple(pad.GetPosition());o0=tuple(owner.GetPosition())
    owner.SetOrientationDegrees(angle)
    dx,dy=[v-w for v,w in zip(tuple(pad.GetPosition()),tuple(owner.GetPosition()))]
    theta=math.radians(-angle)
    assert dx == pytest.approx((p0[0]-o0[0])*math.cos(theta)-(p0[1]-o0[1])*math.sin(theta),abs=1)
    assert dy == pytest.approx((p0[0]-o0[0])*math.sin(theta)+(p0[1]-o0[1])*math.cos(theta),abs=1)


@pytest.mark.parametrize('delta,rotation',[((17,0),0),((0,0),45),((float('nan'),0),0)])
def test_unbounded_or_noncardinal_pose_is_refused(delta,rotation):
    board,pad=fixture();before=row._source_binding(board)
    with pytest.raises(ValueError):
        frontier.rigid_poses(board,['IC_RENAMED'],'IC_RENAMED',delta,rotation)
    assert row._source_binding(board) == before


def typed_pose_fixture():
    board,_=fixture()
    board.Remove(board.FindFootprintByReference('IC_RENAMED'))
    owner=native_part(board,'arbitrary_typed_owner','TLV7011DBVR',(15,15),
        [('1',-1,-1),('2',-1,0),('3',-1,1),('4',1,1),('5',1,-1)],
        'Package_TO_SOT_SMD','SOT-23-5',1.5,1.5)
    owner.FindPadByNumber('2').SetNet(board.FindNet('GND'))
    return board,owner


def native_part(board,ref,value,at,pins,lib,name,half_x,half_y):
    fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue(value)
    fp.SetFPID(pcbnew.LIB_ID(lib,name));board.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I_MM(*at))
    for pin,dx,dy in pins:
        pad=pcbnew.PAD(fp);pad.SetNumber(pin);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(dx,dy))
        fp.Add(pad)
    corners=[(-half_x,-half_y),(half_x,-half_y),(half_x,half_y),(-half_x,half_y)]
    for a,b in zip(corners,corners[1:]+corners[:1]):
        line=pcbnew.PCB_SHAPE(fp);line.SetLayer(pcbnew.F_CrtYd);line.SetShape(pcbnew.SHAPE_T_SEGMENT)
        line.SetWidth(50000);line.SetStart(fp.GetPosition()+pcbnew.VECTOR2I_MM(*a))
        line.SetEnd(fp.GetPosition()+pcbnew.VECTOR2I_MM(*b));fp.Add(line)
    return fp


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',[pcbnew.In2_Cu,pcbnew.B_Cu])
def test_translation_events_project_native_inner_copper_before_cardinal_pose(quarter,layer):
    board,owner=typed_pose_fixture();origin=owner.GetPosition()
    owner.SetOrientationDegrees(90*quarter)
    pad=owner.FindPadByNumber('2');at=pad.GetPosition()
    net=pcbnew.NETINFO_ITEM(board,'arbitrary_foreign_bus');board.Add(net)
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(layer)
    track.SetWidth(2000000);track.SetStart(pcbnew.VECTOR2I(at.x-10000000,at.y))
    track.SetEnd(pcbnew.VECTOR2I(at.x+10000000,at.y));board.Add(track)
    before=row._source_binding(board)
    proof=frontier.ground_translation_events(board,owner.GetReference(),
        selected_refs=[owner.GetReference()],retired_uuids=[],radius_mm=4,max_sites=8)
    assert proof['deltas_mm'] and proof['native_projected_items']>=1
    assert proof['ground_lands']==1 and proof['declared_portal_geometry_mm']==[.35,.25]
    for dx,dy in proof['deltas_mm']:
        assert math.hypot(dx,dy)<=4
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(
            at.x+round(dx*1e6),at.y+round(dy*1e6)))
        via.SetWidth(350000);via.SetDrill(250000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        assert not track.GetEffectiveShape(layer).Collide(via.GetEffectiveShape(layer),200000)
    assert not proof['no_path_proof'] and not proof['routing_admitted']
    assert row._source_binding(board)==before


def test_ground_translation_requires_manufacturer_package_and_actual_courtyard():
    board,owner=typed_pose_fixture();owner.SetValue('unqualified_generic_part')
    before=row._source_binding(board)
    with pytest.raises(ValueError,match='typed_ground_pose_and_exact_retained_scope_required'):
        frontier.ground_translation_events(board,owner.GetReference(),
            selected_refs=[owner.GetReference()],retired_uuids=[])
    assert row._source_binding(board)==before


@pytest.mark.parametrize('quarter',range(4))
def test_joint_ground_events_screen_actual_lands_before_finite_ranking(quarter):
    board,owner=typed_pose_fixture();owner.SetOrientationDegrees(90*quarter)
    target=owner.FindPadByNumber('1').GetPosition()
    foreign=pcbnew.NETINFO_ITEM(board,'independently_renamed_surface_copper');board.Add(foreign)
    track=pcbnew.PCB_TRACK(board);track.SetNet(foreign);track.SetLayer(pcbnew.F_Cu)
    track.SetWidth(300000);track.SetStart(pcbnew.VECTOR2I(target.x-10000000,target.y))
    track.SetEnd(pcbnew.VECTOR2I(target.x+10000000,target.y));board.Add(track)
    before=row._source_binding(board);origin=tuple(owner.GetPosition())
    common=dict(selected_refs=[owner.GetReference()],retired_uuids=[],
        radius_mm=4.,max_sites=8)
    joint=frontier.ground_translation_events(board,owner.GetReference(),
        **common,surface_proposals=True)
    assert joint['deltas_mm'] and joint['conservative_same_face_copper_events']
    assert joint['native_surface_contacts_projected']>0
    assert row._source_binding(board)==before
    for dx,dy in joint['deltas_mm']:
        owner.SetPosition(pcbnew.VECTOR2I(origin[0]+round(dx*1e6),origin[1]+round(dy*1e6)))
        proof=frontier.surface_screen(board,[owner.GetReference()])
        assert proof['ok'],proof
        owner.SetPosition(pcbnew.VECTOR2I(*origin))
    assert row._source_binding(board)==before
    assert not joint['no_path_proof'] and not joint['routing_admitted']
    assert not joint['release_authority']


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_joint_ground_surface_mode_requires_explicit_boolean(flag):
    board,owner=typed_pose_fixture();before=row._source_binding(board)
    with pytest.raises(ValueError,match='bounded_native_ground_translation_events_required'):
        frontier.ground_translation_events(board,owner.GetReference(),
            selected_refs=[owner.GetReference()],retired_uuids=[],surface_proposals=flag)
    assert row._source_binding(board)==before


def test_joint_ground_surface_mode_cannot_ignore_live_copper_by_uuid():
    board,owner=typed_pose_fixture();net=pcbnew.NETINFO_ITEM(board,'independent_foreign');board.Add(net)
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(pcbnew.F_Cu)
    track.SetStart(pcbnew.VECTOR2I_MM(10,10));track.SetEnd(pcbnew.VECTOR2I_MM(20,10))
    track.SetWidth(300000);board.Add(track);before=row._source_binding(board)
    with pytest.raises(ValueError,match='private_source_cut_native_surface_required'):
        frontier.ground_translation_events(board,owner.GetReference(),
            selected_refs=[owner.GetReference()],retired_uuids=[force._uid(track)],surface_proposals=True)
    assert row._source_binding(board)==before


@pytest.mark.parametrize('quarter',range(4))
def test_measurement_portal_projection_reserves_same_net_force_shadow(quarter):
    board,owner,cap,_=shared_entry_fixture();model=frontier.roles.footprint_contract(owner)
    owner.SetOrientationDegrees(quarter*90)
    measurement=[p for p in owner.Pads() if model['pins'].get(p.GetNumber())=='measurement']
    for index,pad in enumerate(measurement):
        net=pcbnew.NETINFO_ITEM(board,'independently_named_measurement_'+str(index));board.Add(net);pad.SetNet(net)
    pad=measurement[0];at=pad.GetPosition()
    bus=pcbnew.PCB_TRACK(board);bus.SetLayer(pcbnew.B_Cu);bus.SetNetCode(pad.GetNetCode())
    bus.SetStart(pcbnew.VECTOR2I(at.x-10000000,at.y));bus.SetEnd(pcbnew.VECTOR2I(at.x+10000000,at.y))
    bus.SetWidth(4000000);board.Add(bus)
    before=row._source_binding(board)
    proof=frontier.ground_translation_events(board,owner.GetReference(),
        selected_refs=[owner.GetReference()],retired_uuids=[],radius_mm=8,
        surface_proposals=True,measurement_portal_proposals=True)
    assert proof['deltas_mm'] and proof['measurement_portal_proposals']
    assert {w['pad_uuid'] for w in proof['source_typed_measurement_portal_witnesses']}=={force._uid(p) for p in measurement}
    # The source measurement centre lies in the middle of a 4 mm force bar.
    # Every proposed translation must at least have the possibility of an
    # immediate barrel outside it; this is not the final native barrel proof.
    assert all(abs(dy)>1.3 for dx,dy in proof['deltas_mm'])
    assert row._source_binding(board)==before and not proof['routing_admitted']


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_measurement_portal_mode_requires_literal_boolean(flag):
    board,owner=typed_pose_fixture()
    with pytest.raises(ValueError,match='bounded_native_ground_translation_events_required'):
        frontier.ground_translation_events(board,owner.GetReference(),selected_refs=[owner.GetReference()],
            retired_uuids=[],surface_proposals=True,measurement_portal_proposals=flag)


def test_measurement_portals_need_native_surface_scope_and_typed_roots():
    board,owner=typed_pose_fixture();before=row._source_binding(board)
    with pytest.raises(ValueError,match='measurement_portals_require_joint_private_surface_scope'):
        frontier.ground_translation_events(board,owner.GetReference(),selected_refs=[owner.GetReference()],
            retired_uuids=[],measurement_portal_proposals=True)
    with pytest.raises(ValueError,match='typed_measurement_portal_roots_required'):
        frontier.ground_translation_events(board,owner.GetReference(),selected_refs=[owner.GetReference()],
            retired_uuids=[],surface_proposals=True,measurement_portal_proposals=True)
    assert row._source_binding(board)==before


def test_cap_follower_uses_real_supply_pin_and_qualified_ground_after_owner_pose(tmp_path):
    import time
    board,owner=typed_pose_fixture()
    net=pcbnew.NETINFO_ITEM(board,'renamed_supply');board.Add(net)
    owner.FindPadByNumber('5').SetNet(net)
    cap=native_part(board,'arbitrary_bypass','100nF',(19,15),
        [('1',-.5,0),('2',.5,0)],'Capacitor_SMD','C_0603_1608Metric',1.,.55)
    cap.FindPadByNumber('1').SetNet(net)
    cap.FindPadByNumber('2').SetNet(board.FindNet('GND'))
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    source=pcbnew.LoadBoard(str(path));before=force._hash(path)
    owner.SetPosition(pcbnew.VECTOR2I_MM(17,15))
    proof=frontier.follower_frontier(board,source,{cap.GetReference():dict(
        owner=owner.GetReference(),pin='5',rail='renamed_supply')},
        board_path='opaque',max_shift_mm=8,deadline=time.monotonic()+10)
    assert proof['ok'] and not proof['no_path_proof']
    final=cap.FindPadByNumber('1').GetPosition();supply=owner.FindPadByNumber('5').GetPosition()
    assert math.dist(tuple(final),tuple(supply))/1e6<=3.5
    assert proof['trials'][-1]['ground_access']['ok']
    assert force._hash(path)==before


def shared_entry_fixture():
    board, _ = fixture()
    board.Remove(board.FindFootprintByReference('IC_RENAMED'))
    klass = pcbnew.NETCLASS('local_return'); klass.SetTrackWidth(200000)
    klass.SetClearance(200000); board.FindNet('GND').SetNetClass(klass)
    owner = native_part(board,'renamed_sensor','INA181A3IDBVR',(15,15),
        [('1',-1,1.1),('2',0,1.1),('3',1,1.1),('4',1,-1.1),('5',0,-1.1),('6',-1,-1.1)],
        'Package_TO_SOT_SMD','SOT-23-6',1.5,1.4)
    for name in ('supply_rail','output','measure_high','measure_low','foreign_bus'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net)
    for pin,net in [('1','output'),('2','GND'),('3','measure_high'),
                    ('4','measure_low'),('5','GND'),('6','supply_rail')]:
        owner.FindPadByNumber(pin).SetNet(board.FindNet(net))
    cap=native_part(board,'C_renamed','100nF',(14,12.5),[('1',-.5,0),('2',.5,0)],
        'Capacitor_SMD','C_0603_1608Metric',.7,.4)
    cap.FindPadByNumber('1').SetNet(board.FindNet('supply_rail'))
    cap.FindPadByNumber('2').SetNet(board.FindNet('GND'))
    bus=pcbnew.PCB_TRACK(board);bus.SetNet(board.FindNet('foreign_bus'))
    bus.SetLayer(pcbnew.B_Cu);bus.SetWidth(3600000)
    bus.SetStart(pcbnew.VECTOR2I_MM(10,15));bus.SetEnd(pcbnew.VECTOR2I_MM(20,15));board.Add(bus)
    selected={cap.GetReference():dict(owner=owner.GetReference(),pin='6',rail='supply_rail')}
    return board,owner,cap,selected


def test_source_selected_cap_entry_admits_ground_and_reference_without_redundant_barrels():
    board,owner,cap,selected=shared_entry_fixture();before=row._source_binding(board)
    old=frontier.ground_screen(board,[owner.GetReference(),cap.GetReference()],board_path='opaque')
    assert not old['ok']
    proof=frontier.ground_screen(board,[owner.GetReference(),cap.GetReference()],board_path='opaque',
        selected_bypasses=selected)
    assert proof['ok'],proof
    assert proof['required']==3 and not proof['routing_admitted']
    shared=[r for r in proof['results'] if r['return_proof']['status']=='shared-selected-bypass-entry']
    assert {r['pin'] for r in shared}=={'2','5'}
    assert all(r['return_proof']['path_mm']<=4 for r in shared)
    assert row._source_binding(board)==before


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_shared_entry_events_keep_qualified_root_when_ground_centres_are_blocked(rotation):
    board,owner,cap,selected=shared_entry_fixture()
    origin=owner.GetPosition()
    poses=frontier.rigid_poses(board,[owner.GetReference(),cap.GetReference()],
        owner.GetReference(),(0,0),rotation)
    for ref,pose in poses.items():
        fp=board.FindFootprintByReference(ref)
        fp.SetOrientationDegrees(pose[2]);fp.SetPosition(pcbnew.VECTOR2I_MM(*pose[:2]))
    for track in board.GetTracks():
        track.Rotate(origin,pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
    before=row._source_binding(board)
    common=dict(selected_refs=[owner.GetReference(),cap.GetReference()],
        retired_uuids=[],radius_mm=.2,max_sites=8)
    strict=frontier.ground_translation_events(board,owner.GetReference(),**common)
    assert not strict['deltas_mm']
    proposal=frontier.ground_translation_events(board,owner.GetReference(),
        **common,shared_entry_proposals=True)
    assert proposal['deltas_mm'] and proposal['shared_entry_proposals']
    assert proposal['every_final_ground_obligation_still_required']
    assert {q['kind'] for q in proposal['source_ground_root_witnesses']}=={
        'manufacturer_ground','source_selected_bypass'}
    proof=frontier.ground_screen(board,[owner.GetReference(),cap.GetReference()],
        board_path='opaque',selected_bypasses=selected)
    assert proof['ok'],proof
    assert not proposal['routing_admitted'] and not proposal['no_path_proof']
    assert row._source_binding(board)==before


@pytest.mark.parametrize('fault',['missing_selected_cap','untyped_owner','nonboolean'])
def test_shared_ground_event_mode_requires_source_typed_roots(fault):
    board,owner,cap,selected=shared_entry_fixture();before=row._source_binding(board)
    refs=[owner.GetReference(),cap.GetReference()];mode=True
    if fault=='missing_selected_cap':refs.remove(cap.GetReference())
    elif fault=='untyped_owner':owner.SetValue('unqualified');before=row._source_binding(board)
    else:mode=1
    with pytest.raises(ValueError):
        frontier.ground_translation_events(board,owner.GetReference(),
            selected_refs=refs,retired_uuids=[],radius_mm=.2,shared_entry_proposals=mode)
    assert row._source_binding(board)==before


def test_remote_reference_uses_directed_package_ground_then_immediate_selected_cap():
    import cec_cell_escape_replan as escape
    board,owner,cap,selected=shared_entry_fixture()
    cap.SetPosition(pcbnew.VECTOR2I_MM(14,17.8));cap.SetOrientationDegrees(270)
    before=row._source_binding(board)
    entries=escape.assigned_ground_entries(board,selected,board_hint='opaque')
    reference=owner.FindPadByNumber('5');ground=owner.FindPadByNumber('2')
    entry=entries[force._uid(reference)]
    assert entry['typed_reference_or_address_to_package_ground']
    assert entry['portal_pad_uuid']==force._uid(ground)
    assert entry['root_portal_pad_uuid']==force._uid(cap.FindPadByNumber('2'))
    proof=frontier.ground_screen(board,[owner.GetReference(),cap.GetReference()],
        board_path='opaque',selected_bypasses=selected)
    assert proof['ok'],proof
    assert row._source_binding(board)==before


@pytest.mark.parametrize('fault',['other_owner','wrong_pin','wrong_rail','missing_portal','remote'])
def test_ground_dependency_cannot_use_arbitrary_same_net_peer(fault):
    board,owner,cap,selected=shared_entry_fixture()
    if fault=='other_owner':selected[cap.GetReference()]['owner']='imaginary_owner'
    elif fault=='wrong_pin':selected[cap.GetReference()]['pin']='5'
    elif fault=='wrong_rail':selected[cap.GetReference()]['rail']='measure_high'
    elif fault=='remote':cap.SetPosition(pcbnew.VECTOR2I_MM(30,30))
    refs=[owner.GetReference()] if fault=='missing_portal' else [owner.GetReference(),cap.GetReference()]
    before=row._source_binding(board)
    with pytest.raises(ValueError):
        frontier.ground_screen(board,refs,board_path='opaque',selected_bypasses=selected)
    assert row._source_binding(board)==before


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_coordinated_assembly_events_are_native_read_only_and_valid_cardinal_proposals(rotation):
    board,owner=typed_pose_fixture()
    peer=native_part(board,'second_owner','TLV7011DBVR',(20,15),
        [('1',-1,-1),('2',-1,0),('3',-1,1),('4',1,1),('5',1,-1)],
        'Package_TO_SOT_SMD','SOT-23-5',1.5,1.5)
    obstacle=native_part(board,'retained_obstacle','passive',(15,15),[],
        'Test','block',1,1)
    refs=[owner.GetReference(),peer.GetReference()];before=row._source_binding(board)
    proof=frontier.assembly_translation_events(board,refs,selected_refs=refs,
        rotation_deg=rotation,radius_mm=8,max_sites=8)
    assert proof['deltas_mm'] and not proof['routing_admitted']
    assert all(type(v) is float for point in proof['deltas_mm'] for v in point)
    original={ref:(tuple(board.FindFootprintByReference(ref).GetPosition()),
        board.FindFootprintByReference(ref).GetOrientationDegrees()) for ref in refs}
    for delta in proof['deltas_mm']:
        assert math.hypot(*delta)<=8
        poses=frontier.rigid_poses(board,refs,refs[0],delta,rotation)
        for ref,pose in poses.items():
            fp=board.FindFootprintByReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(*pose[:2]))
            fp.SetOrientationDegrees(pose[2])
        assert frontier.courtyard_screen(board,refs)['ok']
        for ref,(at,angle) in original.items():
            fp=board.FindFootprintByReference(ref);fp.SetPosition(pcbnew.VECTOR2I(*at))
            fp.SetOrientationDegrees(angle)
    assert row._source_binding(board)==before
    assert obstacle.GetPosition()==pcbnew.VECTOR2I_MM(15,15)


def foreign_surface_track(board, *, layer=pcbnew.F_Cu):
    net=pcbnew.NETINFO_ITEM(board,'renamed_reserved_feed');board.Add(net)
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(layer)
    track.SetStart(pcbnew.VECTOR2I_MM(10,15));track.SetEnd(pcbnew.VECTOR2I_MM(20,15))
    track.SetWidth(2000000);track.SetLocked(True);board.Add(track)
    return track


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_surface_events_avoid_real_copper_not_just_courtyards(rotation):
    board,owner=typed_pose_fixture();track=foreign_surface_track(board)
    board.GetDesignSettings().m_MinClearance=200000
    refs=[owner.GetReference()];before=row._source_binding(board)
    assert frontier.courtyard_screen(board,refs)['ok']
    assert not frontier.surface_screen(board,refs)['ok']
    proof=frontier.assembly_translation_events(board,refs,selected_refs=refs,
        rotation_deg=rotation,radius_mm=4,max_sites=8)
    assert proof['deltas_mm'] and proof['native_surface_contacts_projected']>0
    assert proof['conservative_same_face_copper_events']
    original=(tuple(owner.GetPosition()),owner.GetOrientationDegrees())
    for delta in proof['deltas_mm']:
        poses=frontier.rigid_poses(board,refs,refs[0],delta,rotation)
        owner.SetPosition(pcbnew.VECTOR2I_MM(*poses[refs[0]][:2]))
        owner.SetOrientationDegrees(poses[refs[0]][2])
        assert frontier.surface_screen(board,refs)['ok']
        assert all(not p.GetEffectiveShape(pcbnew.F_Cu).Collide(
            track.GetEffectiveShape(pcbnew.F_Cu),200000) for p in owner.Pads())
        owner.SetPosition(pcbnew.VECTOR2I(*original[0]));owner.SetOrientationDegrees(original[1])
    assert row._source_binding(board)==before


@pytest.mark.parametrize('layer',[pcbnew.In2_Cu,pcbnew.B_Cu])
def test_surface_map_does_not_turn_another_layer_bus_into_a_body_keepout(layer):
    board,owner=typed_pose_fixture();foreign_surface_track(board,layer=layer)
    refs=[owner.GetReference()];before=row._source_binding(board)
    assert frontier.surface_screen(board,refs)['ok']
    proof=frontier.assembly_translation_events(board,refs,selected_refs=refs,radius_mm=4)
    assert proof['deltas_mm'][0]==[0.,0.]
    assert proof['native_surface_contacts_projected']==0
    # The independent all-layer barrel test still rejects the source pose.
    assert not frontier.ground_screen(board,refs,board_path='opaque')['ok']
    assert row._source_binding(board)==before


def filled_pose_zone(board, *, net='renamed_reserved_feed', layer=pcbnew.F_Cu):
    existing=board.FindNet(net)
    if not existing:
        existing=pcbnew.NETINFO_ITEM(board,net);board.Add(existing)
    item=pcbnew.ZONE(board);item.SetNet(existing);item.SetLayer(layer)
    filled=pcbnew.SHAPE_POLY_SET();i=filled.NewOutline()
    for x,y in ((12,12),(18,12),(18,18),(12,18)):
        filled.Outline(i).Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
    item.Outline().Append(filled);item.SetFilledPolysList(layer,filled)
    item.SetIsFilled(True);board.Add(item)
    return item


@pytest.mark.parametrize('allow_refill',[False,True])
def test_protected_foreign_fill_is_never_antipadded_for_a_pose(allow_refill):
    board,owner=typed_pose_fixture();zone=filled_pose_zone(board)
    refs=[owner.GetReference()];before=row._source_binding(board)
    proof=frontier.surface_screen(board,refs,allow_native_ground_refill=allow_refill)
    assert not proof['ok']
    assert force._uid(zone) in {q['foreign_uuid'] for q in proof['conflicts']}
    events=frontier.assembly_translation_events(board,refs,selected_refs=refs,
        radius_mm=8,allow_native_ground_refill=allow_refill)
    assert [0.,0.] not in events['deltas_mm']
    assert not events['native_ground_refill_still_required']
    assert row._source_binding(board)==before


def test_ground_refill_exclusion_is_explicit_and_carries_a_receiving_obligation():
    board,owner=typed_pose_fixture();zone=filled_pose_zone(board,net='GND')
    refs=[owner.GetReference()];before=row._source_binding(board)
    assert not frontier.surface_screen(board,refs)['ok']
    proof=frontier.surface_screen(board,refs,allow_native_ground_refill=True)
    assert proof['ok'] and proof['native_ground_refill_still_required']==[force._uid(zone)]
    assert not proof['routing_admitted'] and not proof['release_authority']
    assert row._source_binding(board)==before


def test_unfilled_foreign_zone_fails_closed_and_restores_quarter_turned_source():
    board,owner=typed_pose_fixture();zone=filled_pose_zone(board);zone.SetIsFilled(False)
    refs=[owner.GetReference()];before=row._source_binding(board)
    with pytest.raises(ValueError,match='surface_pose_foreign_zone_fill_unknown'):
        frontier.assembly_translation_events(board,refs,selected_refs=refs,rotation_deg=90)
    assert row._source_binding(board)==before


@pytest.mark.parametrize('placement_ban',[False,True])
def test_track_only_keepout_is_not_an_assembly_ban(placement_ban):
    board,owner=typed_pose_fixture();zone=filled_pose_zone(board)
    zone.SetIsRuleArea(True);zone.SetDoNotAllowTracks(True)
    zone.SetDoNotAllowFootprints(placement_ban);refs=[owner.GetReference()]
    before=row._source_binding(board)
    proof=frontier.surface_screen(board,refs)
    assert proof['ok'] is not placement_ban
    assert row._source_binding(board)==before


def test_selected_selected_foreign_lands_are_not_hidden_by_cell_exclusion():
    board,owner=typed_pose_fixture()
    peer=native_part(board,'renamed_peer','passive',(14,15),[('1',0,0)],'Test','one',.3,.3)
    peer.FindPadByNumber('1').SetNet(board.FindNet('GND'))
    # Give the coincident owner land a distinct real net, not an invented
    # connection between two unassigned (net zero) pads.
    pad=owner.FindPadByNumber('2')
    net=pcbnew.NETINFO_ITEM(board,'renamed_signal');board.Add(net);pad.SetNet(net)
    proof=frontier.surface_screen(board,[owner.GetReference(),peer.GetReference()])
    assert not proof['ok'] and proof['conflicts']


def test_rectangular_translation_sweep_preserves_holes_and_concavities():
    import time
    from shapely.geometry import Polygon,Point,box
    import cec_kelvin_copper_cut as cut
    shape=Polygon(box(0,0,10,10).exterior.coords,[box(2,2,8,8).exterior.coords])
    result=frontier._rectangular_sweep(shape,.5,.25,cut._Work(time.monotonic()+10))
    assert result.covers(Point(-.5,5)) and result.covers(Point(5,10.25))
    assert not result.covers(Point(5,5))
    assert result.covers(Point(2.5,5))


def test_unknown_native_surface_geometry_cannot_become_a_legal_event(monkeypatch):
    import cec_kelvin_copper_cut as cut
    board,owner=typed_pose_fixture();foreign_surface_track(board)
    refs=[owner.GetReference()];before=row._source_binding(board)
    def unavailable(*a,**kw):raise cut.Unknown('synthetic_surface_geometry_unknown')
    monkeypatch.setattr(cut,'_shape',unavailable)
    with pytest.raises(cut.Unknown,match='synthetic_surface_geometry_unknown'):
        frontier.assembly_translation_events(board,refs,selected_refs=refs,rotation_deg=270)
    assert row._source_binding(board)==before


def two_follower_fixture(tmp_path):
    board,owner=typed_pose_fixture()
    net=pcbnew.NETINFO_ITEM(board,'arbitrary_supply');board.Add(net)
    owner.FindPadByNumber('5').SetNet(net);selected={};caps=[]
    for index,at in enumerate(((21,14),(21,17))):
        cap=native_part(board,f'arbitrary_follower_{index}','100nF',at,
            [('1',-.5,0),('2',.5,0)],'Capacitor_SMD','C_0603_1608Metric',.7,.4)
        cap.FindPadByNumber('1').SetNet(net);cap.FindPadByNumber('2').SetNet(board.FindNet('GND'))
        selected[cap.GetReference()]=dict(owner=owner.GetReference(),pin='5',rail=net.GetNetname())
        caps.append(cap)
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    return board,pcbnew.LoadBoard(str(path)),selected,caps,path


@pytest.mark.parametrize('failure',['refused_return','unknown_events','unexpected_return_exception'])
def test_failed_follower_search_restores_earlier_success_and_temporary_quarter_turn(
        tmp_path,monkeypatch,failure):
    import time
    import cec_kelvin_copper_cut as cut
    board,source,selected,caps,path=two_follower_fixture(tmp_path)
    before=row._source_binding(board);digest=force._hash(path);seen=[]
    original=tuple(caps[0].GetPosition())
    monkeypatch.setattr(frontier,'_surface_obstacles',lambda *a,**kw:([],[],lambda *a:0))
    monkeypatch.setattr(frontier,'_surface_hits',lambda *a,**kw:[])
    monkeypatch.setattr(frontier,'courtyard_screen',lambda *a,**kw:dict(ok=True))
    def events(board,cap,*a,**kw):
        if cap.GetReference()==caps[1].GetReference() and failure=='unknown_events':
            assert tuple(caps[0].GetPosition())!=original
            raise cut.Unknown('synthetic_follower_geometry_unknown')
        return []
    monkeypatch.setattr(frontier,'_bypass_courtyard_events',events)
    def ground(board,refs,**kw):
        seen.append(refs[0])
        if refs[0]==caps[0].GetReference():return dict(ok=True)
        assert tuple(caps[0].GetPosition())!=original
        if failure=='unexpected_return_exception':raise RuntimeError('synthetic_factory_failure')
        return dict(ok=False,no_path_proof=False)
    monkeypatch.setattr(frontier,'ground_screen',ground)
    kwargs=dict(board_path='opaque',max_shift_mm=8,deadline=time.monotonic()+10)
    if failure=='unknown_events':
        with pytest.raises(cut.Unknown,match='synthetic_follower_geometry_unknown'):
            frontier.follower_frontier(board,source,selected,**kwargs)
    elif failure=='unexpected_return_exception':
        with pytest.raises(RuntimeError,match='synthetic_factory_failure'):
            frontier.follower_frontier(board,source,selected,**kwargs)
    else:
        result=frontier.follower_frontier(board,source,selected,**kwargs)
        assert not result['ok'] and not result['poses'] and not result['no_path_proof']
    assert caps[0].GetReference() in seen
    assert row._source_binding(board)==before and force._hash(path)==digest


def test_surface_snapshot_is_function_local_and_rebuilt_after_each_accepted_follower(
        tmp_path,monkeypatch):
    import time
    board,source,selected,caps,path=two_follower_fixture(tmp_path)
    observations=[];digest=force._hash(path);original=tuple(caps[0].GetPosition())
    def snapshot(board,excluded,*a,**kw):
        observations.append((set(excluded),tuple(caps[0].GetPosition())))
        return [],[],lambda *a:0
    monkeypatch.setattr(frontier,'_surface_obstacles',snapshot)
    monkeypatch.setattr(frontier,'_surface_hits',lambda *a,**kw:[])
    monkeypatch.setattr(frontier,'courtyard_screen',lambda *a,**kw:dict(ok=True))
    monkeypatch.setattr(frontier,'_bypass_courtyard_events',lambda *a,**kw:[])
    monkeypatch.setattr(frontier,'ground_screen',lambda *a,**kw:dict(ok=True))
    proof=frontier.follower_frontier(board,source,selected,board_path='opaque',
        max_shift_mm=8,deadline=time.monotonic()+10)
    assert proof['ok'] and proof['surface_snapshot_builds']==2
    assert observations[0]==({caps[0].GetReference()},original)
    assert observations[1][0]=={caps[1].GetReference()}
    assert observations[1][1]==tuple(caps[0].GetPosition())!=original
    assert force._hash(path)==digest
    # A separate call must not reuse either old function's material epoch.
    again=frontier.follower_frontier(board,source,selected,board_path='opaque',
        max_shift_mm=8,deadline=time.monotonic()+10)
    assert again['ok'] and again['surface_snapshot_builds']==2 and len(observations)==4


def test_expensive_pose_cannot_spend_the_next_poses_lease(tmp_path,monkeypatch):
    board,source,selected,caps,path=two_follower_fixture(tmp_path)
    owner=next(iter(selected.values()))['owner'];clock=[0.]
    monkeypatch.setattr(frontier.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(frontier.force,'_family',lambda *a:force._hash(path))
    monkeypatch.setattr(frontier.force,'_code_identity',lambda:'fixed_test_code_epoch')
    monkeypatch.setattr(frontier.constraints,'_device_bypass_assignment',lambda *a,**kw:dict(
        assigned={i:dict(cap_ref=ref,requirement=dict(ref=owner)) for i,ref in enumerate(selected)}))
    monkeypatch.setattr(frontier.escape,'prepare',lambda *a,**kw:dict(
        stationary_device_owners=[],selected_bypasses=selected))
    monkeypatch.setattr(frontier.escape,'apply_private',lambda *a,**kw:None)
    monkeypatch.setattr(frontier,'courtyard_screen',lambda *a,**kw:dict(ok=True))
    monkeypatch.setattr(frontier,'surface_screen',lambda *a,**kw:dict(ok=True))
    def costly_follower(*a,deadline,**kw):
        clock[0]=deadline
        return dict(ok=False,poses={},no_path_proof=False)
    monkeypatch.setattr(frontier,'follower_frontier',costly_follower)
    digest=force._hash(path)
    result=frontier.frontier(path,[owner],board_hint='opaque',timeout_s=10,
        flexible_bypasses=True,deltas_mm=[(i/10,0) for i in range(8)],rotations=(0,))
    assert len(result['history'])==5
    assert all(q['pose_grant_s']==pytest.approx(2.) for q in result['history'])
    assert result['deadline_exhausted'] and not result['no_path_proof'] and not result['poses']
    assert result['source_and_code_unchanged'] and force._hash(path)==digest


def test_final_pose_rebuilds_private_material_from_its_own_fresh_source_plan(tmp_path,monkeypatch):
    board,source,selected,caps,path=two_follower_fixture(tmp_path)
    marker=pcbnew.PCB_TRACK(board);marker.SetStart(pcbnew.VECTOR2I_MM(30,30))
    marker.SetEnd(pcbnew.VECTOR2I_MM(32,30));marker.SetWidth(200000)
    marker.SetNet(board.FindNet('GND'));board.Add(marker)
    pcbnew.SaveBoard(str(path),board);uid=force._uid(marker);digest=force._hash(path)
    owner=next(iter(selected.values()))['owner'];preparations=[];applied=[];final=[]
    monkeypatch.setattr(frontier.force,'_family',lambda *a:force._hash(path))
    monkeypatch.setattr(frontier.force,'_code_identity',lambda:'fixed_test_code_epoch')
    monkeypatch.setattr(frontier.constraints,'_device_bypass_assignment',lambda *a,**kw:dict(
        assigned={i:dict(cap_ref=ref,requirement=dict(ref=owner)) for i,ref in enumerate(selected)}))
    def prepare(*a,**kw):
        scope=[uid] if not preparations else []
        proposal=dict(stationary_device_owners=[],selected_bypasses=selected,
            retired_track_uuids=scope)
        preparations.append(proposal);return proposal
    monkeypatch.setattr(frontier.escape,'prepare',prepare)
    def apply(board,proposal):
        applied.append(proposal)
        for track in list(board.GetTracks()):
            if force._uid(track) in proposal['retired_track_uuids']:board.Remove(track)
    monkeypatch.setattr(frontier.escape,'apply_private',apply)
    monkeypatch.setattr(frontier,'courtyard_screen',lambda *a,**kw:dict(ok=True))
    def surface(board,refs,**kw):
        if len(refs)>1:final.append({force._uid(t) for t in board.GetTracks()})
        return dict(ok=True)
    monkeypatch.setattr(frontier,'surface_screen',surface)
    monkeypatch.setattr(frontier,'follower_frontier',lambda *a,**kw:dict(ok=True,
        poses={cap.GetReference():[cap.GetPosition().x/1e6,cap.GetPosition().y/1e6,
            cap.GetOrientationDegrees()] for cap in caps}))
    monkeypatch.setattr(frontier,'ground_screen',lambda *a,**kw:dict(ok=True))
    proof=frontier.frontier(path,[owner],board_hint='opaque',timeout_s=10,
        flexible_bypasses=True,deltas_mm=[(.001,0)],rotations=(0,))
    assert proof['poses'] and len(preparations)==len(applied)==2
    assert uid in final[0] and not proof['poses'][0]['proposal']['retired_track_uuids']
    assert force._hash(path)==digest and not proof['routing_admitted']


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('gap_nm',[200000,199999,199900])
def test_guard_boundary_uses_full_native_clearance_not_a_fabrication_epsilon(rotation,gap_nm):
    board,pad=fixture();board.GetDesignSettings().m_MinClearance=200000
    net=pcbnew.NETINFO_ITEM(board,'arbitrary_foreign_feed');board.Add(net)
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(pcbnew.F_Cu)
    track.SetWidth(1000000);y=pad.GetPosition().y+pad.GetSize().y//2+500000+gap_nm
    track.SetStart(pcbnew.VECTOR2I(10000000,y));track.SetEnd(pcbnew.VECTOR2I(20000000,y))
    board.Add(track)
    if rotation:
        pivot=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for item in [pad.GetParentFootprint(),track]:item.Rotate(pivot,angle)
    before=row._source_binding(board)
    proof=frontier.surface_screen(board,['IC_RENAMED'])
    native_clear=not pad.GetEffectiveShape(pcbnew.F_Cu).Collide(track.GetEffectiveShape(pcbnew.F_Cu),200000)
    assert proof['ok']==native_clear==(gap_nm==200000)
    assert row._source_binding(board)==before


def test_stationary_owner_witness_is_not_hidden_from_the_moving_owners_surface_check(
        tmp_path,monkeypatch):
    board,source,selected,caps,path=two_follower_fixture(tmp_path)
    owner=next(iter(selected.values()))['owner'];fixed='unrelated_stationary_witness'
    witness=native_part(board,fixed,'TLV7011DBVR',(25,25),
        [('1',-1,-1),('2',-1,0),('3',-1,1),('4',1,1),('5',1,-1)],
        'Package_TO_SOT_SMD','SOT-23-5',1.5,1.5)
    pcbnew.SaveBoard(str(path),board);digest=force._hash(path)
    monkeypatch.setattr(frontier.force,'_family',lambda *a:force._hash(path))
    monkeypatch.setattr(frontier.force,'_code_identity',lambda:'fixed_test_code_epoch')
    monkeypatch.setattr(frontier.constraints,'_device_bypass_assignment',lambda *a,**kw:dict(
        assigned={i:dict(cap_ref=ref,requirement=dict(ref=owner)) for i,ref in enumerate(selected)}))
    monkeypatch.setattr(frontier.escape,'prepare',lambda *a,**kw:dict(
        stationary_device_owners=[fixed],selected_bypasses=selected))
    monkeypatch.setattr(frontier.escape,'apply_private',lambda *a,**kw:None)
    monkeypatch.setattr(frontier,'courtyard_screen',lambda *a,**kw:dict(ok=True))
    calls=[]
    def surface(board,refs,*,selected_refs,**kw):
        calls.append((refs,selected_refs))
        # A source-stationary owner is fixed material, not an unplaced
        # follower that may be excluded from the collision snapshot.
        assert fixed not in selected_refs and fixed not in refs
        return dict(ok=False,conflicts=[dict(ref=owner,foreign_ref=fixed)])
    monkeypatch.setattr(frontier,'surface_screen',surface)
    def not_reached(*a,**kw):raise AssertionError('routing must not follow a copper-blocked pose')
    monkeypatch.setattr(frontier,'follower_frontier',not_reached)
    proof=frontier.frontier(path,[owner,fixed],board_hint='opaque',timeout_s=10,
        flexible_bypasses=True,deltas_mm=[(.001,0)],rotations=(0,))
    assert len(calls)==1 and proof['history'][0]['reason']=='native_surface_copper_refused'
    assert not proof['poses'] and force._hash(path)==digest
