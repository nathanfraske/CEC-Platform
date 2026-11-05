import copy
import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_joint_connection_search as joint


def fixture(monkeypatch, prefix='arbitrary'):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(6)
    nets = {}
    for name in ('GND', 'RAIL', 'OUT', 'INPUT_P', 'INPUT_N'):
        net = pcbnew.NETINFO_ITEM(board, name); board.Add(net); nets[name] = net
    def footprint(ref, value, at, pads):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value)
        fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD', 'SOT-23-5'))
        fp.SetPosition(pcbnew.VECTOR2I_MM(*at));board.Add(fp)
        for pin, netname, offset in pads:
            p = pcbnew.PAD(fp); p.SetNumber(pin); p.SetNet(nets[netname])
            p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
            p.SetLayerSet(pcbnew.PAD.SMDMask()); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            fp.Add(p); p.SetPosition(pcbnew.VECTOR2I_MM(at[0]+offset[0], at[1]+offset[1]))
        return fp
    owner = prefix+'_owner'; cap = prefix+'_cap'
    fp = footprint(owner, 'TLV7011DBVR', (10,10), [
        ('1','OUT',(-1,-1)),('2','GND',(-1,0)),('3','INPUT_P',(-1,1)),
        ('4','INPUT_N',(1,1)),('5','RAIL',(1,-1))])
    cf = footprint(cap, '100nF', (12,9), [('1','RAIL',(-.5,0)),('2','GND',(.5,0))])
    assignment = dict(assigned={'selected':dict(cap_ref=cap,
        requirement=dict(ref=owner, pin='5', rail='RAIL', return_rail='GND'))})
    monkeypatch.setattr(escape.constraints, '_device_bypass_assignment', lambda *a, **kw:assignment)
    monkeypatch.setattr(escape.topology, 'board_current_domains', lambda *a, **kw:{})
    monkeypatch.setattr(escape.fr, 'coupled_pair_nets', lambda *a, **kw:set())
    poses = {ref:[f.GetPosition().x/1e6,f.GetPosition().y/1e6+1,f.GetOrientationDegrees()]
        for ref,f in [(owner,fp),(cap,cf)]}
    return board, poses, fp, cf


@pytest.mark.parametrize('prefix',['testA','different_names'])
def test_complete_source_owned_cell_is_rederived_before_private_motion(monkeypatch,prefix):
    board,poses,fp,cap = fixture(monkeypatch,prefix)
    before = row._source_binding(board)
    proposal = escape.prepare(board,poses,board_hint='opaque-board-hint')
    assert row._source_binding(board) == before
    assert not proposal['routing_admitted'] and not proposal['release_authority']
    assert proposal['requires_new_placement_power_and_independent_saved_board_receiving']
    escape.apply_private(board,proposal)
    assert abs(fp.GetPosition().y/1e6-poses[fp.GetReference()][1]) < 1e-6
    assert cap.GetReference() in proposal['selected_bypasses']


@pytest.mark.parametrize('prefix',['different_bounded_names','other_bounded_cell'])
@pytest.mark.parametrize('quarter',range(4))
def test_explicit_larger_complete_cohort_keeps_default_and_all_contact_obligations(monkeypatch,prefix,quarter):
    board,poses,owner,cap=fixture(monkeypatch,prefix)
    for target in poses.values():
        target[0]+=18.
        target[2]+=quarter*90
    before=row._source_binding(board)
    with pytest.raises(ValueError):
        escape.prepare(board,poses,board_hint='opaque')
    proposal=escape.prepare(board,poses,board_hint='opaque',max_shift_mm=24.)
    assert row._source_binding(board)==before
    assert proposal['max_shift_mm']==24.
    assert cap.GetReference() in proposal['selected_bypasses']
    assert not proposal['routing_admitted'] and not proposal['release_authority']
    assert proposal['requires_new_placement_power_and_independent_saved_board_receiving']
    forged=copy.deepcopy(proposal);forged['max_shift_mm']=16.
    with pytest.raises(ValueError):escape.apply_private(board,forged)
    assert row._source_binding(board)==before
    escape.apply_private(board,proposal)
    assert tuple(owner.GetPosition())==tuple(round(v*1e6) for v in poses[owner.GetReference()][:2])


@pytest.mark.parametrize('limit',[0.,-1.,32.000001,float('nan'),float('inf'),True])
def test_complete_cohort_translation_budget_is_always_explicit_finite_and_bounded(monkeypatch,limit):
    board,poses,owner,cap=fixture(monkeypatch)
    before=row._source_binding(board)
    with pytest.raises(ValueError):escape.prepare(board,poses,board_hint='opaque',max_shift_mm=limit)
    assert row._source_binding(board)==before


@pytest.mark.parametrize('fault',['missing_cap','missing_owner','wrong_package','bad_cap_net','shift','forgery'])
def test_incomplete_untyped_or_forged_cell_never_moves_source(monkeypatch,fault):
    board,poses,fp,cap = fixture(monkeypatch)
    if fault == 'missing_cap': del poses[cap.GetReference()]
    elif fault == 'missing_owner': del poses[fp.GetReference()]
    elif fault == 'wrong_package': fp.SetFPID(pcbnew.LIB_ID('Package','SC-70-5'))
    elif fault == 'bad_cap_net': next(iter(cap.Pads())).SetNet(board.FindNet('OUT'))
    elif fault == 'shift': poses[fp.GetReference()][1] += 20
    before = row._source_binding(board)
    with pytest.raises(ValueError):
        proposal = escape.prepare(board,poses,board_hint='opaque-board-hint')
        proposal['retired_track_uuids'].append('worker-made-up-deletion')
        escape.apply_private(board,proposal)
    assert row._source_binding(board) == before


def test_incomplete_stale_or_invalid_operation_cannot_leave_partial_copper(monkeypatch):
    board,poses,fp,cap = fixture(monkeypatch)
    one = dict(id='one', cost=1, net='OUT', clearance_nm=200000,
        ops=[['trk',[5000000,5000000],[6000000,5000000],200000,pcbnew.F_Cu]])
    two = dict(id='two', cost=1, net='OUT', clearance_nm=200000,
        ops=[['bad',[7000000,5000000],1,2]])
    packet = dict(domains={'one':[one],'two':[two]},source_native_binding=row._source_binding(board))
    selection = joint.solve(packet['domains'],conflicts=lambda a,b:False)
    before = row._source_binding(board)
    with pytest.raises(ValueError): escape.construct_private(board,packet,selection)
    assert row._source_binding(board) == before
    selection['complete'] = False
    with pytest.raises(ValueError): escape.construct_private(board,packet,selection)
    assert row._source_binding(board) == before
    packet['source_native_binding'] = 'stale'
    with pytest.raises(ValueError): escape.choose(board,packet)


def test_actual_layer_width_and_same_net_drill_spacing_are_future_obstacles(monkeypatch):
    board,*_ = fixture(monkeypatch)
    conflicts = escape.conflict_oracle(board)
    a = dict(net='OUT',clearance_nm=200000,
        ops=[['trk',[1000000,1000000],[4000000,1000000],800000,pcbnew.F_Cu]])
    b = dict(net='INPUT_N',clearance_nm=200000,
        ops=[['trk',[2000000,0],[2000000,2000000],200000,pcbnew.F_Cu]])
    assert conflicts(a,b)
    separated = copy.deepcopy(b); separated['ops'][0][4] = pcbnew.B_Cu
    assert not conflicts(a,separated)
    v1 = dict(net='GND',clearance_nm=200000,ops=[['via',[5000000,5000000],.3,.6]])
    v2 = dict(net='GND',clearance_nm=200000,ops=[['via',[5100000,5000000],.3,.6]])
    assert conflicts(v1,v2)


def test_stationary_owner_is_supply_witness_not_measurement_or_ground_ripup(monkeypatch):
    board,poses,owner,cap=fixture(monkeypatch)
    poses[owner.GetReference()]=[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,
        owner.GetOrientationDegrees()]
    before=row._source_binding(board)
    proposal=escape.prepare(board,poses,board_hint='opaque')
    assert proposal['stationary_device_owners']==[owner.GetReference()]
    assert proposal['measurement_leaves']==proposal['ground_leaves']==[]
    assert row._source_binding(board)==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('moving_owner',[False,True])
def test_shared_ground_cap_tail_is_only_jointly_owned_when_actual_owner_moves(monkeypatch,quarter,moving_owner):
    board,_,owner,cap=fixture(monkeypatch,prefix='renamed_shared_return')
    root=tuple(owner.FindPadByNumber('2').GetPosition());end=tuple(cap.FindPadByNumber('2').GetPosition())
    points=[root,(root[0],end[1]-1000000),(end[0],end[1]-1000000),end,
        (end[0]+1000000,end[1]),(end[0]+2000000,end[1])]
    tracks=[]
    for a,b in zip(points,points[1:]):
        item=pcbnew.PCB_TRACK(board);item.SetStart(pcbnew.VECTOR2I(*a));item.SetEnd(pcbnew.VECTOR2I(*b))
        item.SetWidth(200000);item.SetLayer(pcbnew.F_Cu);item.SetNet(board.FindNet('GND'))
        item.SetLocked(True);board.Add(item);tracks.append(item)
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*points[-1]))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(board.FindNet('GND'));board.Add(via)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T);pivot=pcbnew.VECTOR2I_MM(20,20)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,angle)
    poses={fp.GetReference():[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,
        fp.GetOrientationDegrees()] for fp in (owner,cap)}
    poses[cap.GetReference()][0]+=.5
    if moving_owner:poses[owner.GetReference()][0]+=.5
    before=row._source_binding(board)
    proposal=escape.prepare(board,poses,board_hint='opaque')
    assert before==row._source_binding(board)
    cap_ground=force._uid(cap.FindPadByNumber('2'))
    matched=[q for q in proposal['ground_leaves'] if q['pad_uuid']==cap_ground]
    if moving_owner:
        assert len(matched)==1
        assert matched[0]['track_uuids']==[force._uid(t) for t in tracks[3:]]
        assert {force._uid(t) for t in tracks}<=set(proposal['retired_track_uuids'])
        assert force._uid(via) not in proposal['retired_track_uuids']
    else:
        assert not matched and proposal['stationary_device_owners']==[owner.GetReference()]
        assert not set(proposal['retired_track_uuids'])&{force._uid(t) for t in tracks}
        assert any(q['pad_uuid']==cap_ground for q in proposal['ground_departures_not_owned'])


@pytest.mark.parametrize('quarter',range(4))
def test_stationary_owner_keeps_its_good_rated_rail_feed_during_bypass_motion(monkeypatch,quarter):
    import cec_decoupler_cell as cell
    board,_,owner,cap=fixture(monkeypatch,prefix='renamed_stationary')
    pad=owner.FindPadByNumber('5');at=pad.GetPosition();tracks=[]
    for a,b in [((at.x,at.y),(at.x,at.y-1500000)),
                ((at.x,at.y-1500000),(at.x,at.y-2500000))]:
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b))
        t.SetWidth(200000);t.SetNetCode(pad.GetNetCode());t.SetLocked(True);board.Add(t);tracks.append(t)
    via=pcbnew.PCB_VIA(board);via.SetPosition(tracks[-1].GetEnd());via.SetNetCode(pad.GetNetCode())
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    if quarter:
        pivot=pcbnew.VECTOR2I_MM(20,20);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,angle)
    monkeypatch.setattr(cell,'_supply_current_widths',lambda *a,**kw:
        dict(required_by_layer_nm={pcbnew.F_Cu:200000},unchanged_aggregate_load=True))
    # Positively show this is an owned, rated departure that the old
    # stationary-owner implementation would unnecessarily retire.
    assert escape.leaf.plan_rated_supply(board,force._uid(pad),board_hint='opaque')['track_uuids']==[
        force._uid(t) for t in tracks]
    poses={fp.GetReference():[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,
        fp.GetOrientationDegrees()] for fp in (owner,cap)}
    poses[cap.GetReference()][0]+=.5
    before=row._source_binding(board)
    proposal=escape.prepare(board,poses,board_hint='opaque')
    assert proposal['stationary_device_owners']==[owner.GetReference()]
    assert not ({force._uid(t) for t in tracks}|{force._uid(via)})&set(proposal['retired_track_uuids'])
    assert not any(q['pad_uuid']==force._uid(pad) for q in proposal['rated_supply_leaves'])
    assert row._source_binding(board)==before
    escape.apply_private(board,proposal)
    assert {force._uid(t) for t in [*tracks,via]}<={force._uid(t) for t in board.GetTracks()}


@pytest.mark.parametrize('cap_moves',[False,True])
def test_cell_rebuild_owns_moving_bypass_feed_but_keeps_stationary_feed(monkeypatch,tmp_path,cap_moves):
    import cec_decoupler_cell as cell
    board,poses,owner,cap=fixture(monkeypatch)
    pad=cap.FindPadByNumber('1');at=pad.GetPosition();tracks=[]
    for a,b in [((at.x,at.y),(at.x,at.y-1500000)),
                ((at.x,at.y-1500000),(at.x,at.y-2500000))]:
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b))
        t.SetWidth(200000);t.SetNetCode(pad.GetNetCode());t.SetLocked(True);board.Add(t);tracks.append(t)
    via=pcbnew.PCB_VIA(board);via.SetPosition(tracks[-1].GetEnd());via.SetNetCode(pad.GetNetCode())
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    monkeypatch.setattr(cell,'_supply_current_widths',lambda *a,**kw:
        dict(required_by_layer_nm={pcbnew.F_Cu:200000},unchanged_aggregate_load=True))
    source_path=tmp_path/'synthetic-source.kicad_pcb';pcbnew.SaveBoard(str(source_path),board)
    source=pcbnew.LoadBoard(str(source_path))
    if not cap_moves:
        poses[cap.GetReference()]=[cap.GetPosition().x/1e6,cap.GetPosition().y/1e6,cap.GetOrientationDegrees()]
    before=row._source_binding(board);q=escape.prepare(board,poses,board_hint='opaque')
    owned=set(q['retired_track_uuids']) & {force._uid(t) for t in tracks}
    assert owned==({force._uid(t) for t in tracks} if cap_moves else set())
    assert force._uid(via) not in q['retired_track_uuids']
    assert row._source_binding(board)==before
    escape.apply_private(board,q)
    if cap_moves:
        requests=escape.obligations(source,board,q)
        feed=requests['rated_supply:'+force._uid(pad)]
        assert feed['a']['pad_uuid']==force._uid(pad)
        assert feed['b']['native_uuids']==[force._uid(via)]


def test_joint_owner_motion_rebuilds_scalar_link_between_actual_new_lands(monkeypatch,tmp_path):
    from test_escape_pose_frontier import native_part
    board,poses,owner,cap=fixture(monkeypatch)
    peer=native_part(board,'different_scalar_peer','TLV7011DBVR',(10,13),
        [('1',1,-1),('2',-1,0),('3',-1,1),('4',1,1),('5',1,0)],
        'Package_TO_SOT_SMD','SOT-23-5',1.5,1.5)
    for pin,net in [('1','INPUT_N'),('2','GND'),('3','OUT'),('4','INPUT_P'),('5','RAIL')]:
        peer.FindPadByNumber(pin).SetNet(board.FindNet(net))
    follower=native_part(board,'different_peer_cap','100nF',(12,13),
        [('1',-.5,0),('2',.5,0)],'Capacitor_SMD','C_0603_1608Metric',.7,.4)
    follower.FindPadByNumber('1').SetNet(board.FindNet('RAIL'))
    follower.FindPadByNumber('2').SetNet(board.FindNet('GND'))
    assigned={'one':dict(cap_ref=cap.GetReference(),requirement=dict(
        ref=owner.GetReference(),pin='5',rail='RAIL',return_rail='GND')),
        'two':dict(cap_ref=follower.GetReference(),requirement=dict(
            ref=peer.GetReference(),pin='5',rail='RAIL',return_rail='GND'))}
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**kw:dict(assigned=assigned))
    tracks=[]
    points=[(9,9),(8,9),(8,14),(9,14)]
    for a,b in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*b))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(board.FindNet('OUT'));board.Add(t);tracks.append(t)
    for fp in (peer,follower):
        poses[fp.GetReference()]=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6+1,fp.GetOrientationDegrees()]
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    source=pcbnew.LoadBoard(str(path));before=row._source_binding(board)
    proposal=escape.prepare(board,poses,board_hint='opaque')
    assert len(proposal['scalar_links'])==1
    assert set(proposal['scalar_links'][0]['track_uuids'])=={force._uid(t) for t in tracks}
    assert row._source_binding(board)==before
    escape.apply_private(board,proposal)
    requests=escape.obligations(source,board,proposal)
    request=requests['scalar_link:'+force._uid(owner.FindPadByNumber('1'))]
    assert request['a']['at_nm']==list(owner.FindPadByNumber('1').GetPosition())
    assert request['b']['at_nm']==list(peer.FindPadByNumber('3').GetPosition())
    assert not any(k.startswith('retained:') and v['net']=='OUT' for k,v in requests.items())


def test_impossible_local_ground_menu_defers_routes_and_does_not_claim_no_path(monkeypatch):
    board,poses,fp,cap = fixture(monkeypatch)
    ground = cap.FindPadByNumber('2')
    monkeypatch.setattr(escape.cell,'_add_ground_return',lambda *a,**kw:(None,'bounded return search refused'))
    monkeypatch.setattr(escape.fab,'active_profile_name',lambda *a,**kw:None)
    requests = {'return':dict(kind='ground',net='GND',reach_mm=.8,
        a=dict(pad_uuid=force._uid(ground))),
        'expensive_measurement':dict(kind='measurement',net='INPUT_P')}
    before = row._source_binding(board)
    packet = escape.menus(board,requests,board_path='opaque',board_hint='opaque')
    assert packet['upstream_access_refused']
    assert packet['root_blocking_obligation'] == 'return'
    assert packet['deferred_not_attempted'] == ['expensive_measurement']
    assert packet['all_obligations_present'] and packet['domains']['return'] == []
    assert packet['diagnostics']['expensive_measurement']['deferred_not_attempted']
    result = escape.choose(board,packet)
    assert not result['complete'] and result['selected'] == {} and not result['no_path_proof']
    assert row._source_binding(board) == before


def test_failed_barrel_reports_actual_inner_layer_obstacle_without_mutation(monkeypatch):
    board,poses,fp,cap = fixture(monkeypatch)
    ground = cap.FindPadByNumber('2'); at = ground.GetPosition()
    track = pcbnew.PCB_TRACK(board); track.SetStart(pcbnew.VECTOR2I(at.x-1000000,at.y))
    track.SetEnd(pcbnew.VECTOR2I(at.x+1000000,at.y)); track.SetWidth(800000)
    track.SetLayer(pcbnew.In2_Cu); track.SetNet(board.FindNet('INPUT_N')); board.Add(track)
    before = row._source_binding(board)
    blockers = escape.native_barrel_blockers(board,tuple(at),'GND',diameter_mm=.35)
    assert any(b['layer'] == board.GetLayerName(pcbnew.In2_Cu)
        and b['native'].get('uuid') == force._uid(track) for b in blockers)
    assert row._source_binding(board) == before


@pytest.mark.parametrize('explicit',[False,True])
def test_nonplane_role_breadth_is_explicit_and_never_includes_ground_planes(monkeypatch,explicit):
    board,*_ = fixture(monkeypatch)
    before = row._source_binding(board)
    monkeypatch.setattr(escape.fr,'_lastmile_route_layers',lambda *a,**kw:[pcbnew.B_Cu])
    monkeypatch.setattr(escape.fr,'plane_layers',lambda *a:['In1.Cu'])
    monkeypatch.setattr(escape.fab,'routing_layers',lambda *a,**kw:[
        'F.Cu','In1.Cu','In2.Cu','B.Cu'])
    seen = []
    monkeypatch.setattr(escape,'_connection_menu',lambda *a,**kw:seen.extend(kw['layers']))
    packet=escape.menus(board,{'connection':dict(kind='source_boundary',net='OUT')},
        board_path='opaque',board_hint='opaque',include_power_layer=explicit)
    assert packet['explicit_nonplane_power_role_policy'] is explicit
    assert seen == ([pcbnew.In2_Cu,pcbnew.B_Cu] if explicit else [pcbnew.B_Cu])
    assert row._source_binding(board) == before


def test_coupled_connections_cannot_use_ordinary_cell_role_breadth(monkeypatch):
    board,*_ = fixture(monkeypatch)
    monkeypatch.setattr(escape.fr,'coupled_pair_nets',lambda *a:{'OUT'})
    monkeypatch.setattr(escape,'_connection_menu',lambda *a,**kw:pytest.fail('coupled scalar search'))
    packet=escape.menus(board,{'connection':dict(kind='source_boundary',net='OUT')},
        board_path='opaque',board_hint='opaque')
    assert packet['domains']['connection'] == []
    assert packet['diagnostics']['connection']['error']=='complete_cell_coupled_route_authority_missing'


@pytest.mark.parametrize('flag',[None,1,'yes'])
def test_nonplane_role_breadth_requires_an_explicit_boolean(monkeypatch,flag):
    board,*_ = fixture(monkeypatch)
    with pytest.raises(ValueError,match='bounded_cell_menu_budget_required'):
        escape.menus(board,{},board_path='opaque',board_hint='opaque',include_power_layer=flag)


def dependency_packet():
    from test_escape_pose_frontier import shared_entry_fixture
    board,owner,cap,selected=shared_entry_fixture()
    entries=escape.assigned_ground_entries(board,selected,board_hint='opaque')
    pad=owner.FindPadByNumber('5');portal=cap.FindPadByNumber('2')
    requests={}
    for p in (pad,portal):
        request=dict(kind='ground',net='GND',reach_mm=.8,
            a=dict(pad_uuid=force._uid(p)))
        if p==pad:request['selected_bypass_entry']=entries[force._uid(p)]
        requests['ground:'+force._uid(p)]=request
    before=row._source_binding(board)
    packet=escape.menus(board,requests,board_path='opaque',board_hint='opaque')
    assert row._source_binding(board)==before
    return board,owner,cap,packet


def test_joint_ground_choice_receives_real_cap_barrel_and_visible_link():
    board,owner,cap,packet=dependency_packet();before=row._source_binding(board)
    selection=escape.choose(board,packet)
    assert selection['complete'],selection
    assert any(c.get('requires_ground_entry') for c in selection['selected'].values())
    assert row._source_binding(board)==before
    escape.construct_private(board,packet,selection)
    portal=cap.FindPadByNumber('2');pad=owner.FindPadByNumber('5')
    assert escape.cell._existing_return(board,portal,.8) is not None
    assert escape.cell._shortest_track_path_mm(board,pad,portal,snap_mm=.000001)<=4


@pytest.mark.parametrize('fault',['missing_barrel','missing_link','looser_limit','different_pad','cycle'])
def test_joint_ground_dependency_cannot_be_satisfied_by_floating_or_forged_copper(fault):
    board,owner,cap,packet=dependency_packet();before=row._source_binding(board)
    selected={key:copy.deepcopy(values[0]) for key,values in packet['domains'].items()}
    dependent=next(c for c in selected.values() if c.get('requires_ground_entry'))
    entry=dependent['requires_ground_entry'];portal=selected[entry['portal_obligation']]
    if fault=='missing_barrel':portal['ops']=[]
    elif fault=='missing_link':dependent['ops']=[]
    elif fault=='looser_limit':entry['max_link_mm']=40
    elif fault=='different_pad':entry['owner_ground_pad_uuid']=force._uid(owner.FindPadByNumber('2'))
    elif fault=='cycle':portal['requires_ground_entry']=copy.deepcopy(entry)
    assert not escape._ground_dependencies_received(board,selected,board_hint='opaque')
    assert row._source_binding(board)==before


def test_voltage_measurement_is_not_a_shunt_leaf_and_existing_open_is_not_completed(monkeypatch,tmp_path):
    from test_escape_pose_frontier import native_part
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for a,b in [((0,0),(50,0)),((50,0),(50,50)),((50,50),(0,50)),((0,50),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    for name in ('GND','RAIL','LO','HI','OUT','SDA','SCL'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    pins=[(str(i),-1,-1+.5*(i-1)) for i in range(1,6)]
    pins += [(str(i),1,1-.5*(i-6)) for i in range(6,11)]
    owner=native_part(board,'arbitrary_monitor','INA238',(20,20),pins,
        'Package_SO','VSSOP-10_3x3mm_P0.5mm',1.5,1.5)
    for pad in owner.Pads():pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
    for pin,net in [('1','RAIL'),('2','GND'),('3','OUT'),('4','SDA'),('5','SCL'),
                    ('6','RAIL'),('7','GND'),('8','LO'),('9','LO'),('10','HI')]:
        owner.FindPadByNumber(pin).SetNet(board.FindNet(net))
    cap=native_part(board,'C_selected','100nF',(23,21),[('1',-.5,0),('2',.5,0)],
        'Capacitor_SMD','C_0603_1608Metric',.7,.4)
    cap.FindPadByNumber('1').SetNet(board.FindNet('RAIL'))
    cap.FindPadByNumber('2').SetNet(board.FindNet('GND'))
    link=pcbnew.PCB_TRACK(board);link.SetStart(owner.FindPadByNumber('9').GetPosition())
    link.SetEnd(owner.FindPadByNumber('8').GetPosition());link.SetWidth(200000)
    link.SetLayer(pcbnew.F_Cu);link.SetNet(board.FindNet('LO'));board.Add(link)
    assignment=dict(assigned={'opaque':dict(cap_ref=cap.GetReference(),
        requirement=dict(ref=owner.GetReference(),pin='6',rail='RAIL',return_rail='GND'))})
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**kw:assignment)
    monkeypatch.setattr(escape.topology,'board_current_domains',lambda *a,**kw:{})
    monkeypatch.setattr(escape.fr,'coupled_pair_nets',lambda *a,**kw:set())
    poses={fp.GetReference():[fp.GetPosition().x/1e6+1,fp.GetPosition().y/1e6,
        fp.GetOrientationDegrees()] for fp in (owner,cap)}
    before=row._source_binding(board);proposal=escape.prepare(board,poses,board_hint='opaque')
    assert row._source_binding(board)==before
    assert [p['pin'] for p in proposal['preserved_nonpair_measurement_contacts']]==['8']
    assert [p['pin'] for p in proposal['inherited_unrouted_measurement_lands']]==['10']
    assert proposal['inherited_unrouted_measurement_lands'][0]['route_authority'] is False
    assert [q['pin'] for q in proposal['measurement_leaves']]==['9']
    saved=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(saved),board)
    source=pcbnew.LoadBoard(str(saved))
    original_points={p.GetNumber():list(p.GetPosition()) for p in owner.Pads()}
    escape.apply_private(board,proposal)
    # For this internal link, the final boundary follows its real owner too.
    assert list(owner.FindPadByNumber('8').GetPosition()) != original_points['8']
    # This fixture also has a source-isolated INA238 address land on RAIL.
    # Its new complete obligation needs explicit positive fixture current
    # authority, never an implicit guess derived from the test's net name.
    import cec_decoupler_cell as cells
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a,**kw:dict(
        current_authority={'source':'synthetic fixture only'},
        required_by_layer_nm={pcbnew.F_Cu:200000}))
    requests=escape.obligations(source,board,proposal)
    request=requests['measurement:'+force._uid(owner.FindPadByNumber('9'))]
    assert request['b']['at_nm']==list(owner.FindPadByNumber('8').GetPosition())
    assert request['source_leaf']['source_boundary_entry_nm']==[
        list(owner.FindPadByNumber('9').GetPosition()),list(owner.FindPadByNumber('8').GetPosition())]
    diagnostic={}
    assert escape.leaf.path_clear(board,request['source_leaf'],request['source_leaf']['points_nm'],
        diagnostics=diagnostic),diagnostic


@pytest.mark.parametrize('quarter',range(4))
def test_moving_selected_bypass_preserves_mixed_pad_and_retained_feed_boundary(monkeypatch,tmp_path,quarter):
    """A moved local pair still owes its exact stationary supply feed."""
    board,_,owner,cap=fixture(monkeypatch,prefix='offcentre_feed')
    supply=owner.FindPadByNumber('5');positive=cap.FindPadByNumber('1')
    root=tuple(supply.GetPosition());land=tuple(positive.GetPosition())
    split=(land[0]-200000,land[1]+100000)
    def stroke(a,b):
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(supply.GetNet());board.Add(t)
        return t
    owned=stroke(root,split)
    retained=stroke(split,land)
    # Two real outgoing feeds keep the cap's fork out of exclusive linear
    # ownership. Neither can disappear when the selected cap is moved.
    stroke(land,(land[0],land[1]-2000000))
    stroke(land,(land[0]+2000000,land[1]))
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T);pivot=pcbnew.VECTOR2I_MM(20,20)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,angle)
    monkeypatch.setattr(escape.cell,'_supply_current_widths',lambda *a,**kw:
        dict(required_by_layer_nm={pcbnew.F_Cu:200000},unchanged_aggregate_load=True))
    poses={fp.GetReference():[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6+2,
        fp.GetOrientationDegrees()] for fp in (owner,cap)}
    saved=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(saved),board)
    source=pcbnew.LoadBoard(str(saved));source_binding=row._source_binding(source)
    proposal=escape.prepare(board,poses,board_hint='opaque')
    q=next(q for q in proposal['rated_supply_leaves'] if q['pad_uuid']==force._uid(supply))
    assert q['boundary_uuids']==sorted([force._uid(positive),force._uid(retained)])
    assert force._uid(owned) in proposal['retired_track_uuids']
    assert force._uid(retained) not in proposal['retired_track_uuids']
    escape.apply_private(board,proposal);binding=row._source_binding(board)
    requests=escape.obligations(source,board,proposal)
    local=requests['local_supply:'+force._uid(supply)]
    feed=requests['rated_supply:'+force._uid(supply)]
    assert local['b']['pad_uuid']==force._uid(positive)
    assert feed['b']['at_nm']==q['points_nm'][-1]
    assert feed['b']['native_uuids']==[force._uid(retained)]
    assert feed['unchanged_full_rail_current_contract']==q['unchanged_full_rail_current_contract']
    assert row._source_binding(source)==source_binding and row._source_binding(board)==binding


@pytest.mark.parametrize('quarter',range(4))
def test_direct_output_barrel_is_retained_but_becomes_mandatory_after_owner_motion(monkeypatch,tmp_path,quarter):
    board,_,owner,cap=fixture(monkeypatch,prefix='renamed_direct_barrel')
    output=owner.FindPadByNumber('1')
    via=pcbnew.PCB_VIA(board);via.SetPosition(output.GetPosition()+pcbnew.VECTOR2I_MM(.1,.1))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNet(output.GetNet());board.Add(via)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T);pivot=pcbnew.VECTOR2I_MM(20,20)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,angle)
    poses={fp.GetReference():[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6+2,
        fp.GetOrientationDegrees()] for fp in (owner,cap)}
    saved=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(saved),board);source=pcbnew.LoadBoard(str(saved))
    before=row._source_binding(board);source_before=row._source_binding(source)
    proposal=escape.prepare(board,poses,board_hint='opaque')
    assert row._source_binding(board)==before and force._uid(via) not in proposal['retired_track_uuids']
    contacts=proposal['row_plan']['source_native_barrel_boundaries']
    assert [(q['pad_uuid'],q['via_uuid']) for q in contacts]==[(force._uid(output),force._uid(via))]
    escape.apply_private(board,proposal);binding=row._source_binding(board)
    requests=escape.obligations(source,board,proposal)
    request=requests['retained_barrel:'+force._uid(output)+':'+force._uid(via)]
    assert request['a']['at_nm']==list(output.GetPosition())
    assert request['b']['at_nm']==list(via.GetPosition())
    assert request['b']['native_uuids']==[force._uid(via)]
    assert request['b']['layers']==list(map(int,via.GetLayerSet().CuStack()))
    assert request['width_nm']>=200000 and via.GetNetname()=='OUT'
    assert row._source_binding(board)==binding and row._source_binding(source)==source_before


@pytest.mark.parametrize('quarter',range(4))
def test_joint_frontier_reroutes_ordinary_boundary_around_mandatory_future_copper(monkeypatch,quarter):
    board,_,owner,_=fixture(monkeypatch,prefix='future_contact')
    for a,b in [((0,0),(60,0)),((60,0),(60,60)),((60,60),(0,60)),((0,60),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('exact_stationary_sink');board.Add(fp)
    target=pcbnew.PAD(fp);target.SetNumber('1');target.SetShape(pcbnew.PAD_SHAPE_RECT)
    target.SetSize(pcbnew.VECTOR2I_MM(.8,.8));target.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    target.SetLayerSet(pcbnew.PAD.SMDMask());target.SetNet(board.FindNet('OUT'));fp.Add(target)
    target.SetPosition(pcbnew.VECTOR2I_MM(20,9))
    def xy(p):
        x,y=p
        for _ in range(quarter):x,y=y,60-x
        return [round(x*1e6),round(y*1e6)]
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T);pivot=pcbnew.VECTOR2I_MM(30,30)
        for item in [*board.GetFootprints(),*board.GetDrawings()]:item.Rotate(pivot,angle)
    root=owner.FindPadByNumber('1')
    assert list(root.GetPosition())==xy((9,9))
    wall=dict(id='0',cost=0,net='INPUT_P',clearance_nm=200000,
        ops=[['trk',xy((15,1)),xy((15,59)),200000,pcbnew.F_Cu]])
    options=[dict(id=str(i),cost=11+i,net='OUT',clearance_nm=200000,
        ops=[['trk',xy(a),xy(b),200000,pcbnew.F_Cu] for a,b in zip(path,path[1:])])
        for i,path in enumerate([[(9,9),(20,9)],[(9,9),(9,8),(20,8),(20,9)]])]
    packet=dict(domains={'fixed':[wall],'move':options},source_native_binding=row._source_binding(board))
    requests={'fixed':dict(kind='source_boundary',net='INPUT_P'),
        'move':dict(kind='source_boundary',net='OUT',width_nm=200000,
            a=dict(pad_uuid=force._uid(root),at_nm=list(root.GetPosition()),layers=[pcbnew.F_Cu]),
            b=dict(pad_uuid=force._uid(target),at_nm=list(target.GetPosition()),layers=[pcbnew.F_Cu]))}
    before=row._source_binding(board);original=copy.deepcopy(packet)
    failed=escape.choose(board,packet,timeout_s=2.)
    assert not failed['complete'] and failed['failure_frontier']
    refined=escape.refine_conflict_frontier(board,packet,requests,failed,board_path='opaque',
        board_hint='opaque',timeout_s=3.,include_power_layer=True)
    assert refined['conflict_aware_refinement']['trials'][0]['added_choices']>0
    complete=escape.choose(board,refined,timeout_s=3.)
    assert complete['complete'],complete
    assert complete['selected']['fixed']==wall
    assert any(op[0]=='via' for op in complete['selected']['move']['ops'])
    assert packet==original and row._source_binding(board)==before
    assert refined['conflict_aware_refinement']['one_bounded_pass_only']
