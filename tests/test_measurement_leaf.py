import pcbnew
import pytest

import cec_measurement_leaf as leaf
import cec_force_current as force
from cec_native_items import discard_items


def fixture(renamed='ordinary_name', quarter=0):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    net = pcbnew.NETINFO_ITEM(board, renamed); board.Add(net)
    def xy(point):
        x, y = point
        for _ in range(quarter):
            x, y = 30-y, x
        return pcbnew.VECTOR2I_MM(x, y)
    for a, b in [((0, 0), (30, 0)), ((30, 0), (30, 30)),
                 ((30, 30), (0, 30)), ((0, 30), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(board); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT); edge.SetStart(xy(a)); edge.SetEnd(xy(b)); board.Add(edge)
    def pad(ref, value, pin, at):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); fp.SetValue(value); board.Add(fp)
        p = pcbnew.PAD(fp); p.SetNumber(pin); p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetSize(pcbnew.VECTOR2I_MM(.5, .5)); p.SetPosition(xy(at)); p.SetNet(net); fp.Add(p)
        return p
    selected = pad('RENAMED_OWNER', 'INA181A2IDBVR', '3', (10, 10))
    anchor = pad('FIXED', 'test', '1', (20, 10))
    tracks = []
    for a, b in [((10, 10), (15, 10)), ((15, 10), (20, 10))]:
        t = pcbnew.PCB_TRACK(board); t.SetStart(xy(a)); t.SetEnd(xy(b))
        t.SetWidth(200000); t.SetLayer(pcbnew.F_Cu); t.SetNet(net); t.SetLocked(True)
        board.Add(t); tracks.append(t)
    return board, selected, anchor, tracks, xy


@pytest.mark.parametrize('name', ['ordinary_name', '+5V_MAIN', '/renamed/Rail'])
@pytest.mark.parametrize('quarter', range(4))
def test_source_role_not_ref_coordinate_or_net_name_owns_linear_leaf(name, quarter):
    board, pad, anchor, tracks, _ = fixture(name, quarter)
    before = leaf._binding(board)
    proposal = leaf.plan(board, force._uid(pad))
    assert proposal['track_uuids'] == [force._uid(t) for t in tracks]
    assert proposal['boundary_uuids'] == [force._uid(anchor)]
    assert proposal['source_native_binding'] == before == leaf._binding(board)
    assert not proposal['current_authority'] and not proposal['kelvin_qualified']


@pytest.mark.parametrize('quarter',range(4))
def test_moved_measurement_endpoint_uses_actual_direct_search_lower_bound(quarter):
    board,pad,anchor,tracks,xy=fixture('/arbitrary/measurement',quarter)
    proposal=leaf.plan(board,force._uid(pad));old_length=proposal['source_length_mm']
    discard_items(board,tracks);pad.SetPosition(xy((1,10)))
    moved=dict(proposal,points_nm=[list(pad.GetPosition()),*proposal['points_nm'][1:]])
    before=leaf._binding(board)
    assert leaf._replacement_length_basis_mm(moved)==19.
    assert moved['source_length_mm']==old_length==10.
    paths=leaf.menus(moved,offset_mm=1)
    assert paths and any(leaf.path_clear(board,moved,path) for path in paths)
    proof=leaf.search(board,moved,timeout_s=2.)
    assert proof['points_nm'] and proof['native_maze_found_path']
    assert leaf.path_clear(board,moved,proof['points_nm'])
    assert leaf._binding(board)==before and not moved['kelvin_qualified']


def test_stationary_measurement_keeps_historical_length_basis():
    board,pad,_,_,_=fixture()
    proposal=leaf.plan(board,force._uid(pad))
    assert leaf._replacement_length_basis_mm(proposal)==proposal['source_length_mm']


@pytest.mark.parametrize('quarter',range(4))
def test_canonical_detour_has_the_same_sixteen_edge_bound_as_native_leaf(quarter):
    board,pad,_,tracks,xy=fixture('/independent/aliased_input',quarter)
    proposal=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    points=[list(xy((10,10)))]+[list(xy((10+i,11))) for i in range(9)]+[
        list(xy((19,11))),list(xy((20,10)))]
    assert len(points)>8 and len(points)<=17
    assert leaf.path_clear(board,proposal,points)
    over=[list(xy((10,10)))]+[list(xy((10+i/2,11))) for i in range(16)]+[
        list(xy((20,10)))]
    with pytest.raises(ValueError,match='invalid_measurement_detour_bounds'):
        leaf.path_clear(board,proposal,over)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('name',['unrelated_alias','+5V_MAIN','/nested/renamed'])
def test_compiled_contact_screen_matches_fresh_native_paths(name,quarter):
    board,pad,_,tracks,xy=fixture(name,quarter)
    proposal=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    obstacle=pcbnew.PCB_TRACK(board);obstacle.SetNetCode(pad.GetNetCode())
    obstacle.SetLayer(pcbnew.F_Cu);obstacle.SetWidth(800000)
    obstacle.SetStart(xy((14,10)));obstacle.SetEnd(xy((16,10)));board.Add(obstacle)
    before=leaf._binding(board)
    guard=leaf.compile_path_guard(board,proposal)
    assert guard.centerline_boxes and len(guard.centerline_boxes)<=64
    answers=[]
    paths=[*leaf.menus(proposal,max_paths=32,offset_mm=2),
        [tuple(xy(p)) for p in ((10,10),(10,12),(20,12),(20,10))]]
    for path in paths:
        fresh=leaf.path_clear(board,proposal,path)
        cached=leaf.path_clear(board,proposal,path,_compiled_guard=guard)
        assert fresh==cached
        answers.append(fresh)
    assert any(answers) and not all(answers)
    assert before==leaf._binding(board)


@pytest.mark.parametrize('mutation',['foreign_copper','land','proposal','reservation','dict_guard'])
def test_compiled_measurement_contact_screen_refuses_stale_or_worker_guards(mutation):
    from shapely.geometry import LineString
    board,pad,_,tracks,xy=fixture();proposal=leaf.plan(board,force._uid(pad))
    discard_items(board,tracks);guard=leaf.compile_path_guard(board,proposal)
    path=leaf.menus(proposal)[0];avoid=None
    if mutation=='foreign_copper':
        item=pcbnew.PCB_TRACK(board);item.SetStart(xy((15,8)));item.SetEnd(xy((15,12)))
        item.SetWidth(200000);board.Add(item)
    elif mutation=='land':pad.SetPosition(xy((10,11)))
    elif mutation=='proposal':proposal=dict(proposal,width_nm=250000)
    elif mutation=='reservation':avoid=LineString([xy((12,8)),xy((12,12))]).buffer(200000)
    else:guard={'ok':True}
    with pytest.raises(ValueError,match='compiled_measurement_guard|compiled_measurement_guard_source'):
        leaf.path_clear(board,proposal,path,avoid=avoid,_compiled_guard=guard)


def test_compiled_contact_guard_does_not_repolygonize_failed_menu_queries(monkeypatch):
    import cec_kelvin_copper_cut as cut
    board,pad,_,tracks,_=fixture();proposal=leaf.plan(board,force._uid(pad))
    discard_items(board,tracks);guard=leaf.compile_path_guard(board,proposal)
    def forbidden(*a,**kw):raise AssertionError('immutable contact geometry rebuilt')
    monkeypatch.setattr(cut,'_shape',forbidden)
    for path in leaf.menus(proposal,max_paths=16):
        leaf.path_clear(board,proposal,path,_compiled_guard=guard)


@pytest.mark.parametrize('quarter',range(4))
def test_two_segments_inside_one_elongated_land_are_one_exclusive_departure(quarter):
    board,pad,anchor,tracks,xy=fixture('renamed_measurement',quarter)
    pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    internal=pcbnew.PCB_TRACK(board);internal.SetStart(xy((10,10)))
    internal.SetEnd(xy((10.25,10)));internal.SetWidth(200000)
    internal.SetLayer(pcbnew.F_Cu);internal.SetNetCode(pad.GetNetCode());board.Add(internal)
    tracks[0].SetStart(xy((10.25,10)))
    before=leaf._binding(board)
    proposal=leaf.plan(board,force._uid(pad))
    assert proposal['track_uuids']==[force._uid(internal),*[force._uid(t) for t in tracks]]
    assert proposal['boundary_uuids']==[force._uid(anchor)]
    assert proposal['points_nm'][0]==list(pad.GetPosition())
    assert leaf._binding(board)==before


@pytest.mark.parametrize('fault',['fork','gap','wide','group','cycle'])
def test_multiple_pad_touches_never_grant_unowned_chain_retirement(fault):
    board,pad,_,tracks,xy=fixture();pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    internal=pcbnew.PCB_TRACK(board);internal.SetStart(xy((10,10)))
    internal.SetEnd(xy((10.25,10)));internal.SetWidth(200000)
    internal.SetLayer(pcbnew.F_Cu);internal.SetNetCode(pad.GetNetCode());board.Add(internal)
    tracks[0].SetStart(xy((10.25,10)))
    if fault=='fork':
        fork=pcbnew.PCB_TRACK(board);fork.SetStart(xy((10.25,10)));fork.SetEnd(xy((10.25,12)))
        fork.SetWidth(200000);fork.SetNetCode(pad.GetNetCode());board.Add(fork)
    elif fault=='gap':tracks[0].SetStart(xy((10.3,10)))
    elif fault=='wide':internal.SetWidth(800000)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);group.AddItem(internal);board.Add(group)
    elif fault=='cycle':internal.SetEnd(xy((10,10)))
    before=leaf._binding(board)
    with pytest.raises(ValueError):leaf.plan(board,force._uid(pad))
    assert leaf._binding(board)==before


def scalar_fixture(quarter=0):
    board,pad,anchor,tracks,xy=fixture('renamed_scalar',quarter)
    pad.SetNumber('1')
    anchor.GetParentFootprint().SetValue('TLV7011DBVR')
    anchor.GetParentFootprint().SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-5'))
    anchor.SetNumber('3');anchor.SetPosition(xy((14,10)))
    tracks[0].SetEnd(xy((12,10)))
    tracks[1].SetStart(xy((12,10)));tracks[1].SetEnd(xy((14,10)))
    for track in tracks:track.SetLocked(False)
    return board,pad,anchor,tracks,xy


@pytest.mark.parametrize('quarter',range(4))
def test_exclusive_scalar_link_owns_only_typed_group_endpoints(quarter):
    board,pad,anchor,tracks,_=scalar_fixture(quarter)
    before=leaf._binding(board)
    proposal=leaf.plan_scalar_link(board,force._uid(pad),
        owner_refs=[p.GetParentFootprint().GetReference() for p in (pad,anchor)])
    assert proposal['scope']=='source_typed_exclusive_moved_scalar_link'
    assert proposal['peer_pad_uuid']==force._uid(anchor)
    assert proposal['track_uuids']==[force._uid(t) for t in tracks]
    assert not proposal['current_authority'] and leaf._binding(board)==before


@pytest.mark.parametrize('fault',['locked','third_party','wrong_peer_role','fork','wide','group'])
def test_scalar_motion_cannot_cut_protected_or_shared_departures(fault):
    board,pad,anchor,tracks,xy=scalar_fixture()
    owners=[p.GetParentFootprint().GetReference() for p in (pad,anchor)]
    if fault=='locked':tracks[0].SetLocked(True)
    elif fault=='third_party':owners[1]='different_fixed_owner'
    elif fault=='wrong_peer_role':anchor.SetNumber('5')
    elif fault=='wide':tracks[0].SetWidth(800000)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);group.AddItem(tracks[0]);board.Add(group)
    else:
        fork=pcbnew.PCB_TRACK(board);fork.SetStart(xy((12,10)));fork.SetEnd(xy((12,12)))
        fork.SetWidth(200000);fork.SetNetCode(pad.GetNetCode());board.Add(fork)
    before=leaf._binding(board)
    with pytest.raises(ValueError):leaf.plan_scalar_link(board,force._uid(pad),owner_refs=owners)
    assert leaf._binding(board)==before


@pytest.mark.parametrize('fault',[None,'unrated','undersized','wrong_role','wide'])
def test_supply_leaf_requires_source_full_rail_current_not_guessed_ic_load(monkeypatch,fault):
    import cec_decoupler_cell as cell
    board,pad,_,tracks,xy=fixture('renamed_supply')
    pad.SetNumber('6' if fault!='wrong_role' else '1')
    tracks[0].SetEnd(xy((12,10)));tracks[1].SetStart(xy((12,10)))
    tracks[1].SetEnd(xy((14,10)))
    anchor=board.FindFootprintByReference('FIXED').FindPadByNumber('1')
    anchor.SetPosition(xy((14,10)))
    if fault=='wide':
        for t in tracks:t.SetWidth(800000)
    rated=None if fault=='unrated' else dict(required_by_layer_nm={pcbnew.F_Cu:
        300000 if fault=='undersized' else 200000},source_load_unchanged=True)
    monkeypatch.setattr(cell,'_supply_current_widths',lambda *a,**kw:rated)
    before=leaf._binding(board)
    if fault is None:
        q=leaf.plan_rated_supply(board,force._uid(pad),board_hint='opaque')
        assert q['unchanged_full_rail_current_contract']==rated
        assert q['track_uuids']==[force._uid(t) for t in tracks]
    else:
        with pytest.raises(ValueError):leaf.plan_rated_supply(board,force._uid(pad),board_hint='opaque')
    assert leaf._binding(board)==before


def bypass_feed_fixture(monkeypatch,quarter=0):
    import cec_decoupler_cell as cell
    from test_escape_pose_frontier import shared_entry_fixture
    board,owner,cap,_=shared_entry_fixture()
    owner.SetReference('sensor_without_board_name');cap.SetReference('arbitrary_owned_bypass')
    supply=cap.FindPadByNumber('1');a=tuple(supply.GetPosition())
    tracks=[]
    for s,t in [(a,(a[0]-1000000,a[1])),((a[0]-1000000,a[1]),(a[0]-2000000,a[1]))]:
        edge=pcbnew.PCB_TRACK(board);edge.SetStart(pcbnew.VECTOR2I(*s));edge.SetEnd(pcbnew.VECTOR2I(*t))
        edge.SetWidth(200000);edge.SetLayer(pcbnew.F_Cu);edge.SetNetCode(supply.GetNetCode())
        edge.SetLocked(True);board.Add(edge);tracks.append(edge)
    via=pcbnew.PCB_VIA(board);via.SetPosition(tracks[-1].GetEnd());via.SetWidth(600000)
    via.SetDrill(300000);via.SetNetCode(supply.GetNetCode())
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T);pivot=pcbnew.VECTOR2I_MM(20,20)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,angle)
    rating=dict(required_by_layer_nm={pcbnew.F_Cu:200000},unchanged_aggregate_load=True)
    monkeypatch.setattr(cell,'_supply_current_widths',lambda *a,**kw:rating)
    return board,owner,cap,supply,tracks,via,rating


@pytest.mark.parametrize('quarter',range(4))
def test_unique_native_bypass_owns_only_its_fully_rated_stub(monkeypatch,quarter):
    board,owner,cap,pad,tracks,via,rating=bypass_feed_fixture(monkeypatch,quarter)
    before=leaf._binding(board)
    q=leaf.plan_rated_bypass_supply(board,force._uid(pad),board_hint='opaque')
    assert q['scope']=='source_typed_full_load_rated_bypass_supply_leaf'
    assert q['source_selected_bypass']['owner']==owner.GetReference()
    assert q['track_uuids']==[force._uid(t) for t in tracks]
    assert q['boundary_uuids']==[force._uid(via)]
    assert q['unchanged_full_rail_current_contract']==rating
    assert force._uid(via) not in q['track_uuids']
    assert not q['current_authority'] and leaf._binding(board)==before


@pytest.mark.parametrize('fault',['unrated','undersized','untyped_owner','wrong_return',
    'partner_hole','interior_tap','grouped','wide','missing_boundary','root_barrel'])
def test_bypass_feed_policy_cannot_grant_shared_unrated_or_untyped_ripup(monkeypatch,fault):
    import cec_decoupler_cell as cell
    board,owner,cap,pad,tracks,via,_=bypass_feed_fixture(monkeypatch)
    if fault=='unrated':monkeypatch.setattr(cell,'_supply_current_widths',lambda *a,**kw:None)
    elif fault=='undersized':monkeypatch.setattr(cell,'_supply_current_widths',lambda *a,**kw:
        dict(required_by_layer_nm={pcbnew.F_Cu:300000}))
    elif fault=='untyped_owner':owner.SetValue('not_manufacturer_qualified')
    elif fault=='wrong_return':cap.FindPadByNumber('2').SetNet(board.FindNet('measure_low'))
    elif fault=='partner_hole':
        partner=cap.FindPadByNumber('2');partner.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        partner.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='interior_tap':
        tap=pcbnew.PCB_TRACK(board);at=pad.GetPosition()
        tap.SetStart(pcbnew.VECTOR2I(at.x-500000,at.y));tap.SetEnd(pcbnew.VECTOR2I(at.x-500000,at.y-1000000))
        tap.SetWidth(200000);tap.SetNetCode(pad.GetNetCode());board.Add(tap)
    elif fault=='grouped':
        group=pcbnew.PCB_GROUP(board);group.AddItem(tracks[0]);board.Add(group)
    elif fault=='wide':tracks[0].SetWidth(800000)
    elif fault=='missing_boundary':board.Remove(via)
    else:
        extra=pcbnew.PCB_VIA(board);extra.SetPosition(pad.GetPosition());extra.SetWidth(350000)
        extra.SetDrill(250000);extra.SetNetCode(pad.GetNetCode())
        extra.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(extra)
    before=leaf._binding(board)
    with pytest.raises(ValueError):leaf.plan_rated_bypass_supply(board,force._uid(pad),board_hint='opaque')
    assert leaf._binding(board)==before


def test_bypass_leaf_stops_at_first_real_fork_and_keeps_both_shared_branches(monkeypatch):
    board,_,_,pad,tracks,_,_=bypass_feed_fixture(monkeypatch)
    fork=pcbnew.PCB_TRACK(board);at=tracks[0].GetEnd()
    fork.SetStart(at);fork.SetEnd(pcbnew.VECTOR2I(at.x,at.y-1000000))
    fork.SetWidth(200000);fork.SetNetCode(pad.GetNetCode());board.Add(fork)
    before=leaf._binding(board)
    q=leaf.plan_rated_bypass_supply(board,force._uid(pad),board_hint='opaque')
    assert q['track_uuids']==[force._uid(tracks[0])]
    assert set(q['boundary_uuids'])=={force._uid(tracks[1]),force._uid(fork)}
    assert leaf._binding(board)==before


def bypass_return_fixture(monkeypatch,quarter=0):
    board,owner,cap,_,tracks,via,_=bypass_feed_fixture(monkeypatch)
    ground=cap.FindPadByNumber('2');at=tuple(ground.GetPosition())
    for index,edge in enumerate(tracks):
        edge.SetStart(pcbnew.VECTOR2I(at[0],at[1]+index*1000000))
        edge.SetEnd(pcbnew.VECTOR2I(at[0],at[1]+(index+1)*1000000))
        edge.SetNetCode(ground.GetNetCode())
    via.SetPosition(tracks[-1].GetEnd());via.SetNetCode(ground.GetNetCode())
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T);pivot=pcbnew.VECTOR2I_MM(20,20)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,angle)
    return board,owner,cap,ground,tracks,via


@pytest.mark.parametrize('quarter',range(4))
def test_selected_bypass_ground_owns_stub_not_existing_barrel(monkeypatch,quarter):
    board,owner,cap,pad,tracks,via=bypass_return_fixture(monkeypatch,quarter)
    before=leaf._binding(board)
    q=leaf.plan_bypass_ground(board,force._uid(pad),board_hint='opaque')
    assert q['scope']=='source_typed_thin_bypass_ground_leaf'
    assert q['source_selected_bypass']['owner']==owner.GetReference()
    assert q['track_uuids']==[force._uid(t) for t in tracks]
    assert q['boundary_uuids']==[force._uid(via)]
    assert force._uid(via) not in q['track_uuids']
    assert not q['current_authority'] and leaf._binding(board)==before


def shared_owner_bypass_return_fixture(monkeypatch,quarter=0):
    board,owner,cap,pad,tracks,via=bypass_return_fixture(monkeypatch)
    start=tuple(owner.FindPadByNumber('5').GetPosition());end=tuple(pad.GetPosition())
    incoming=[]
    for a,b in [(start,(start[0],end[1])),((start[0],end[1]),end)]:
        edge=pcbnew.PCB_TRACK(board);edge.SetStart(pcbnew.VECTOR2I(*a));edge.SetEnd(pcbnew.VECTOR2I(*b))
        edge.SetLayer(pcbnew.F_Cu);edge.SetWidth(200000);edge.SetNetCode(pad.GetNetCode())
        edge.SetLocked(True);board.Add(edge);incoming.append(edge)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T);pivot=pcbnew.VECTOR2I_MM(20,20)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pivot,angle)
    return board,owner,cap,pad,tracks,via,incoming


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('prefix',['independent_sensor','renamed_again'])
def test_moving_owner_shared_cap_return_retypes_exact_owner_leaf_without_mesh_ripup(monkeypatch,quarter,prefix):
    board,owner,cap,pad,tracks,via,incoming=shared_owner_bypass_return_fixture(monkeypatch,quarter)
    owner.SetReference(prefix);before=leaf._binding(board)
    with pytest.raises(ValueError):leaf.plan_bypass_ground(board,force._uid(pad),board_hint='opaque')
    q=leaf.plan_bypass_ground(board,force._uid(pad),board_hint='opaque',moving_owner_ref=prefix)
    assert q['track_uuids']==[force._uid(t) for t in tracks]
    assert q['boundary_uuids']==[force._uid(via)]
    owners=q['source_resolved_moving_owner_ground_leaves']
    assert len(owners)==1 and owners[0]['track_uuids']==[force._uid(t) for t in incoming]
    assert force._uid(pad) in owners[0]['boundary_uuids']
    assert not set(q['track_uuids'])&set(owners[0]['track_uuids'])
    assert q['source_native_binding']==before==leaf._binding(board)
    assert not q['release_authority'] and not q['current_authority']


@pytest.mark.parametrize('fault',['wrong_owner','boolean_owner','grouped_owner_leaf','owner_fork',
    'unowned_incoming','wrong_manufacturer_ground_pin'])
def test_moving_cap_policy_cannot_exclude_unowned_or_stationary_shared_copper(monkeypatch,fault):
    board,owner,cap,pad,tracks,via,incoming=shared_owner_bypass_return_fixture(monkeypatch)
    selected=owner.GetReference()
    if fault=='wrong_owner':selected=cap.GetReference()
    elif fault=='boolean_owner':selected=True
    elif fault=='grouped_owner_leaf':
        group=pcbnew.PCB_GROUP(board);group.SetName('protected_native_group')
        group.AddItem(incoming[0]);board.Add(group)
    elif fault=='wrong_manufacturer_ground_pin':owner.FindPadByNumber('5').SetNumber('3')
    else:
        at=tuple(incoming[0].GetStart()) if fault=='owner_fork' else tuple(pad.GetPosition())
        if fault=='owner_fork':at=(at[0],at[1]-500000)
        extra=pcbnew.PCB_TRACK(board);extra.SetStart(pcbnew.VECTOR2I(*at))
        extra.SetEnd(pcbnew.VECTOR2I(at[0]+1000000,at[1]));extra.SetWidth(200000)
        extra.SetLayer(pcbnew.F_Cu);extra.SetNetCode(pad.GetNetCode());board.Add(extra)
    before=leaf._binding(board)
    with pytest.raises(ValueError):leaf.plan_bypass_ground(board,force._uid(pad),
        board_hint='opaque',moving_owner_ref=selected)
    assert before==leaf._binding(board)


@pytest.mark.parametrize('fault',['untyped_owner','wrong_return','wide','grouped',
    'interior_tap','missing_boundary','root_barrel'])
def test_bypass_return_refuses_unowned_shared_or_in_pad_departures(monkeypatch,fault):
    board,owner,cap,pad,tracks,via=bypass_return_fixture(monkeypatch)
    if fault=='untyped_owner':owner.SetValue('not_manufacturer_qualified')
    elif fault=='wrong_return':
        pad.SetNet(board.FindNet('measure_low'))
        for item in [*tracks,via]:item.SetNetCode(pad.GetNetCode())
    elif fault=='wide':tracks[0].SetWidth(800000)
    elif fault=='grouped':
        group=pcbnew.PCB_GROUP(board);group.AddItem(tracks[0]);board.Add(group)
    elif fault=='interior_tap':
        tap=pcbnew.PCB_TRACK(board);at=pad.GetPosition()
        tap.SetStart(pcbnew.VECTOR2I(at.x,at.y+500000))
        tap.SetEnd(pcbnew.VECTOR2I(at.x+1000000,at.y+500000))
        tap.SetWidth(200000);tap.SetNetCode(pad.GetNetCode());board.Add(tap)
    elif fault=='missing_boundary':board.Remove(via)
    else:
        extra=pcbnew.PCB_VIA(board);extra.SetPosition(pad.GetPosition());extra.SetWidth(350000)
        extra.SetDrill(250000);extra.SetNetCode(pad.GetNetCode())
        extra.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(extra)
    before=leaf._binding(board)
    with pytest.raises(ValueError):leaf.plan_bypass_ground(board,force._uid(pad),board_hint='opaque')
    assert leaf._binding(board)==before


def test_selected_bypass_return_stops_at_first_shared_mesh_contact(monkeypatch):
    board,_,_,pad,tracks,via=bypass_return_fixture(monkeypatch)
    fork=pcbnew.PCB_TRACK(board);at=tracks[0].GetEnd()
    fork.SetStart(at);fork.SetEnd(pcbnew.VECTOR2I(at.x+1000000,at.y))
    fork.SetWidth(200000);fork.SetNetCode(pad.GetNetCode());board.Add(fork)
    before=leaf._binding(board)
    q=leaf.plan_bypass_ground(board,force._uid(pad),board_hint='opaque')
    assert q['track_uuids']==[force._uid(tracks[0])]
    assert set(q['boundary_uuids'])=={force._uid(tracks[1]),force._uid(fork)}
    assert force._uid(via) not in q['track_uuids']
    assert leaf._binding(board)==before


def test_ground_leaf_keeps_real_barrel_overlapping_long_pad():
    board,pad,anchor,tracks,xy=fixture('GND')
    pad.SetNumber('2');pad.SetSize(pcbnew.VECTOR2I_MM(1.5,.5))
    board.Remove(anchor.GetParentFootprint());discard_items(board,tracks[1:])
    tracks[0].SetEnd(xy((10.9,10)))
    via=pcbnew.PCB_VIA(board);via.SetPosition(xy((10.9,10)))
    via.SetWidth(600000);via.SetDrill(300000);via.SetNetCode(pad.GetNetCode())
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH);board.Add(via)
    before=leaf._binding(board)
    q=leaf.plan_ground(board,force._uid(pad))
    assert q['track_uuids']==[force._uid(tracks[0])]
    assert q['boundary_uuids']==[force._uid(via)]
    assert leaf._binding(board)==before


@pytest.mark.parametrize('fault', ['wide', 'group', 'wrong_role', 'fork_at_land', 'interior_tap'])
def test_unowned_wide_grouped_or_nontyped_departure_refuses(fault):
    board, pad, _, tracks, xy = fixture()
    if fault == 'wide':
        tracks[0].SetWidth(750000)
    elif fault == 'group':
        group = pcbnew.PCB_GROUP(board); group.SetName('force_owned')
        group.AddItem(tracks[0]); board.Add(group)
    elif fault == 'wrong_role':
        pad.SetNumber('6')
    else:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(xy((10 if fault == 'fork_at_land' else 13, 10)))
        t.SetEnd(xy((10 if fault == 'fork_at_land' else 13, 12)))
        t.SetWidth(200000); t.SetNetCode(pad.GetNetCode()); t.SetLayer(pcbnew.F_Cu); board.Add(t)
    before = leaf._binding(board)
    with pytest.raises(ValueError):
        leaf.plan(board, force._uid(pad))
    assert leaf._binding(board) == before


def test_detour_cannot_acquire_same_net_force_contact_or_lose_boundary():
    board, pad, _, tracks, xy = fixture('+5V_MAIN')
    proposal = leaf.plan(board, force._uid(pad))
    discard_items(board, tracks)
    good = [tuple(xy(p)) for p in [(10, 10), (10, 12), (20, 12), (20, 10)]]
    assert leaf.path_clear(board, proposal, good)
    shifted = [*good[:-1], tuple(xy((20, 10.1)))]
    assert not leaf.path_clear(board, proposal, shifted)
    bus = pcbnew.PCB_TRACK(board); bus.SetStart(xy((12, 12))); bus.SetEnd(xy((18, 12)))
    bus.SetWidth(1000000); bus.SetLayer(pcbnew.F_Cu); bus.SetNetCode(pad.GetNetCode()); board.Add(bus)
    assert not leaf.path_clear(board, proposal, good)


def test_menu_is_finite_octilinear_and_cannot_hide_raw_diagonal():
    board, pad, _, tracks, xy = fixture()
    proposal = leaf.plan(board, force._uid(pad))
    menu = leaf.menus(proposal, max_paths=8)
    assert 0 < len(menu) <= 8
    assert all(path[0] == tuple(pad.GetPosition()) for path in menu)
    discard_items(board, tracks)
    odd = [tuple(xy(p)) for p in [(10, 10), (12, 13), (20, 10)]]
    assert not leaf.path_clear(board, proposal, odd)


def test_actual_endcap_contact_does_not_require_equal_centerline_endpoints():
    board, pad, anchor, tracks, xy = fixture()
    board.Remove(anchor.GetParentFootprint())
    fixed = pcbnew.PCB_TRACK(board)
    fixed.SetStart(xy((20, 10.14))); fixed.SetEnd(xy((20, 15)))
    fixed.SetWidth(200000); fixed.SetLayer(pcbnew.F_Cu); fixed.SetNetCode(pad.GetNetCode())
    board.Add(fixed)
    proposal = leaf.plan(board, force._uid(pad))
    assert proposal['track_uuids'] == [force._uid(t) for t in tracks]
    assert proposal['boundary_uuids'] == [force._uid(fixed)]


@pytest.mark.parametrize('quarter', range(4))
def test_menu_funds_two_independent_cross_axes_after_rotation(quarter):
    from shapely.geometry import LineString
    board, pad, _, tracks, xy = fixture('unrelated_label', quarter)
    proposal = leaf.plan(board, force._uid(pad))
    discard_items(board, tracks)
    # Neither the cross channel at y=10.5 nor its approach at x=19.75
    # belongs to the original source's axis set. One-axis menus cannot
    # express this short route. Both orientations are needed after rotation.
    path = [tuple(xy(p)) for p in [(10,10),(10,10.5),(19.75,10.5),(19.75,10),(20,10)]]
    avoid = LineString([tuple(xy((11,10))), tuple(xy((19,10)))]).buffer(300000)
    menu = leaf.menus(proposal, avoid=avoid)
    assert path in menu
    assert leaf.path_clear(board, proposal, path)
    assert len(menu) <= 96 and len({tuple(p) for p in menu}) == len(menu)
    for points in menu:
        for a, b, c in zip(points, points[1:], points[2:]):
            u=(b[0]-a[0], b[1]-a[1]); v=(c[0]-b[0], c[1]-b[1])
            assert u[0]*v[1] != u[1]*v[0]


def test_diagnostic_names_actual_foreign_pad_without_changing_source():
    board, pad, _, tracks, xy = fixture()
    proposal = leaf.plan(board, force._uid(pad)); discard_items(board, tracks)
    foreign = pcbnew.NETINFO_ITEM(board, 'FOREIGN'); board.Add(foreign)
    obstacle = pcbnew.PAD(pad.GetParentFootprint()); obstacle.SetNumber('BARRIER')
    obstacle.SetAttribute(pcbnew.PAD_ATTRIB_SMD); obstacle.SetLayerSet(pcbnew.PAD.SMDMask())
    obstacle.SetShape(pcbnew.PAD_SHAPE_RECT); obstacle.SetSize(pcbnew.VECTOR2I_MM(1, 1))
    obstacle.SetPosition(xy((15, 12))); obstacle.SetNet(foreign); pad.GetParentFootprint().Add(obstacle)
    before = leaf._binding(board); diagnostic = {}
    path = [tuple(xy(p)) for p in [(10, 10), (10, 12), (20, 12), (20, 10)]]
    assert not leaf.path_clear(board, proposal, path, diagnostics=diagnostic)
    assert diagnostic['reason'] == 'native_foreign_copper_or_rule_area'
    assert any(b.get('pad') == 'BARRIER' for b in diagnostic['blockers'])
    assert leaf._binding(board) == before


def test_bounded_native_maze_preserves_source_and_does_not_waive_owned_contact():
    board, pad, _, tracks, xy = fixture()
    proposal = leaf.plan(board, force._uid(pad)); discard_items(board, tracks)
    before = leaf._binding(board)
    found = leaf.search(board, proposal, timeout_s=2)
    assert found['points_nm'] and not found['no_path_proof']
    assert leaf.path_clear(board, proposal, found['points_nm'])
    assert leaf._binding(board) == before


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('width', [200000, 800000])
def test_exact_original_t_junction_replays_without_a_whole_landing_waiver(quarter, width):
    board, pad, anchor, tracks, xy = fixture('+5V_MAIN', quarter)
    board.Remove(anchor.GetParentFootprint())
    boundary = pcbnew.PCB_TRACK(board)
    boundary.SetStart(xy((20, 10))); boundary.SetEnd(xy((24, 10)))
    boundary.SetWidth(width); boundary.SetNetCode(pad.GetNetCode())
    boundary.SetLayer(pcbnew.F_Cu); board.Add(boundary)
    fork = pcbnew.PCB_TRACK(board)
    fork.SetStart(xy((20,10))); fork.SetEnd(xy((20,14)))
    fork.SetWidth(width); fork.SetNetCode(pad.GetNetCode())
    fork.SetLayer(pcbnew.F_Cu); board.Add(fork)
    # End the source leaf orthogonally into a retained horizontal landing.
    tracks[0].SetEnd(xy((10, 8)))
    extra = pcbnew.PCB_TRACK(board); extra.SetStart(xy((10, 8))); extra.SetEnd(xy((20, 8)))
    extra.SetWidth(200000); extra.SetNetCode(pad.GetNetCode()); extra.SetLayer(pcbnew.F_Cu)
    board.Add(extra); tracks[1].SetStart(xy((20, 8))); tracks[1].SetEnd(xy((20, 10)))
    proposal = leaf.plan(board, force._uid(pad))
    discard_items(board, [t for t in board.GetTracks() if force._uid(t) in proposal['track_uuids']])
    original = proposal['points_nm']
    diagnostic = {}
    assert leaf.path_clear(board, proposal, original, diagnostics=diagnostic), diagnostic
    same_contact = [tuple(xy(p)) for p in [(10,10),(10,7),(20,7),(20,10)]]
    assert leaf.path_clear(board, proposal, same_contact)
    # The exact same retained boundary UUID is not permission to track along
    # its length and enlarge the original electrical pickup footprint.
    acquired = [tuple(xy(p)) for p in [(10,10),(10,7),(23,7),(23,10),(20,10)]]
    assert not leaf.path_clear(board, proposal, acquired)
    assert leaf._source_boundary_kernel(proposal).bounds


def test_missing_or_displaced_source_boundary_aperture_is_not_guessed():
    board, pad, _, tracks, _ = fixture()
    proposal = leaf.plan(board, force._uid(pad)); discard_items(board, tracks)
    without = {k:v for k,v in proposal.items() if k != 'source_boundary_entry_nm'}
    with pytest.raises(ValueError, match='exact_source_boundary_entry_required'):
        leaf.path_clear(board, without, proposal['points_nm'])
    wrong = dict(proposal, source_boundary_entry_nm=[[15000000,10000000],[20000000,10000001]])
    with pytest.raises(ValueError, match='exact_source_boundary_entry_required'):
        leaf.search(board, wrong)


@pytest.mark.parametrize('quarter', range(4))
def test_source_ground_leaf_owns_complete_linear_departure_not_entire_mesh(quarter):
    board, pad, anchor, tracks, xy = fixture('GND', quarter)
    pad.SetNumber('2')
    fork = pcbnew.PCB_TRACK(board); fork.SetStart(xy((20, 10))); fork.SetEnd(xy((20, 14)))
    fork.SetNetCode(pad.GetNetCode()); fork.SetWidth(200000); board.Add(fork)
    before = leaf._binding(board)
    proposal = leaf.plan_ground(board, force._uid(pad))
    assert proposal['scope'] == 'source_typed_thin_device_ground_leaf'
    assert proposal['track_uuids'] == [force._uid(t) for t in tracks]
    assert set(proposal['boundary_uuids']) == {force._uid(anchor), force._uid(fork)}
    assert force._uid(fork) not in proposal['track_uuids']
    assert before == leaf._binding(board)
    with pytest.raises(ValueError): leaf.plan(board, force._uid(pad))


@pytest.mark.parametrize('fault', ['wrong_pin', 'not_ground_net', 'wide', 'interior_tap', 'fork_at_land'])
def test_ground_departure_needs_manufacturer_identity_and_exclusive_native_ownership(fault):
    board, pad, anchor, tracks, xy = fixture('GND' if fault != 'not_ground_net' else 'OTHER')
    pad.SetNumber('6' if fault == 'wrong_pin' else '2')
    if fault == 'wide': tracks[0].SetWidth(800000)
    if fault in ('interior_tap', 'fork_at_land'):
        t = pcbnew.PCB_TRACK(board); x = 13 if fault == 'interior_tap' else 10
        t.SetStart(xy((x,10))); t.SetEnd(xy((x,12))); t.SetWidth(200000)
        t.SetNetCode(pad.GetNetCode()); board.Add(t)
    before = leaf._binding(board)
    with pytest.raises(ValueError): leaf.plan_ground(board, force._uid(pad))
    assert before == leaf._binding(board)
