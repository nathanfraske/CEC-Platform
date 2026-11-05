"""An isolated measurement proposal cannot acquire a whole force rail."""
import copy
import math
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_measurement_terminal_route as route
import cec_field_coupling as field
from test_measurement_terminal_access import board_direct,get


def fixture(quarter=0):
    board=board_direct();board.SetCopperLayerCount(6)
    root=board.FindFootprintByReference('MONITOR').FindPadByNumber('8')
    pickup=board.FindFootprintByReference('SHUNT').FindPadByNumber('a')
    for index,pad in enumerate(p for f in board.GetFootprints() for p in f.Pads()):
        pad.SetPosition(pcbnew.VECTOR2I_MM(35+index,35))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    root.SetPosition(pcbnew.VECTOR2I_MM(10,10));pickup.SetPosition(pcbnew.VECTOR2I_MM(20,10))
    # Supply a real inward direction for the direct shunt. The opposite
    # terminal is behind the input, not at an unrelated diagonal coordinate.
    peer=next(p for p in pickup.GetParentFootprint().Pads() if force._uid(p)!=force._uid(pickup))
    peer.SetPosition(pcbnew.VECTOR2I_MM(5,10))
    bus=pcbnew.PCB_TRACK(board);bus.SetNetCode(root.GetNetCode());bus.SetWidth(600000)
    bus.SetLayer(pcbnew.F_Cu);bus.SetStart(pcbnew.VECTOR2I_MM(20,10));bus.SetEnd(pcbnew.VECTOR2I_MM(25,10));board.Add(bus)
    for a,b in [((0,0),(60,0)),((60,0),(60,60)),((60,60),(0,60)),((0,60),(0,0))]:
        edge=pcbnew.PCB_SHAPE(board);edge.SetLayer(pcbnew.Edge_Cuts);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    if quarter:
        pivot=pcbnew.VECTOR2I_MM(30,30);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:item.Rotate(pivot,angle)
    demand=next(d for d in get(board)['requests'] if d['pad_uuid']==force._uid(root))
    return board,demand,root,pickup


@pytest.mark.parametrize('quarter',range(4))
def test_proved_isolated_source_targets_actual_pickup_and_keeps_force_copper(quarter):
    board,demand,root,pickup=fixture(quarter);before=field._field_snapshot_inventory(board)
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+10)
    assert guard['clear']([list(root.GetPosition()),list(pickup.GetPosition())])
    menu=route.menus(board,demand,width_nm=200000,timeout_s=2.)
    assert menu['ops'] and menu['exact_pickup_land_only']
    assert before==field._field_snapshot_inventory(board) and guard['unchanged']()
    assert not menu['release_authority'] and not menu['current_authority']


@pytest.mark.parametrize('fault',['other_land','changed_pickup','wrong_owner','power_input','stranded_stub',
                                  'thin','wide','boolean_width'])
def test_proposal_cannot_invent_terminal_role_target_prefix_or_width(fault):
    board,demand,root,pickup=fixture();demand=copy.deepcopy(demand);width=200000
    if fault=='other_land':demand['target_uuid']=force._uid(board.FindFootprintByReference('SERIES_A').FindPadByNumber('left'))
    elif fault=='changed_pickup':pickup.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='wrong_owner':demand['owner_uuid']='worker_guess'
    elif fault=='power_input':root.SetNumber('6')
    elif fault=='stranded_stub':demand['source_input_island_uuids'].append('unowned')
    elif fault=='thin':width=100000
    elif fault=='wide':width=400000
    else:width=True
    with pytest.raises(ValueError):route.contact_guard(board,demand,width_nm=width,deadline=time.monotonic()+10)


def test_path_cannot_contact_force_bus_outside_the_named_land():
    board,demand,root,pickup=fixture()
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+10)
    assert not guard['clear']([[10000000,10000000],[10000000,9000000],
        [24000000,9000000],[24000000,10000000],[20000000,10000000]])
    assert not guard['clear']([[10000000,10000000],[24000000,10000000]])
    assert not guard['clear']([[10000000,10000000],[15000000,11000000],[20000000,10000000]])


@pytest.mark.parametrize('quarter',range(4))
def test_maze_must_search_around_same_net_force_not_reject_its_shortcut_forever(quarter):
    board,demand,root,pickup=fixture()
    # A finite, retained force branch blocks all of the canonical 1.8 mm
    # doglegs. It is not foreign copper, so ordinary clearance alone offers
    # the invalid shortest path repeatedly. A real legal surface detour
    # exists below its lower end, within the unchanged six-mm search window.
    for a,b in [((15,6),(15,14)),((15,6),(25,6)),((25,6),(25,10))]:
        bus=pcbnew.PCB_TRACK(board);bus.SetNetCode(root.GetNetCode())
        bus.SetWidth(600000);bus.SetLayer(pcbnew.F_Cu)
        bus.SetStart(pcbnew.VECTOR2I_MM(*a));bus.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(bus)
    if quarter:
        pivot=pcbnew.VECTOR2I_MM(30,30)
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            item.Rotate(pivot,angle)
        demand=next(d for d in get(board)['requests'] if d['pad_uuid']==force._uid(root))
    before=field._field_snapshot_inventory(board)
    menu=route.menus(board,demand,width_nm=200000,timeout_s=5.,max_choices=1)
    assert menu['ops'],menu
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+5)
    for ops in menu['ops']:
        points=[ops[0][1],*[op[2] for op in ops]]
        assert guard['clear'](points)
        assert all(op[3]==200000 and op[4]==pcbnew.F_Cu for op in ops)
    assert before==field._field_snapshot_inventory(board)


@pytest.mark.parametrize('quarter',range(4))
def test_same_net_force_channel_hints_are_not_contact_or_no_path_authority(quarter):
    board,demand,root,pickup=fixture(quarter)
    before=field._field_snapshot_inventory(board)
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+2)
    hints=guard['centerline_contact_boxes']
    assert hints and len(hints)<=64
    assert all(len(b)==4 and all(math.isfinite(v)for v in b)
        and b[0]<b[2]and b[1]<b[3]for b in hints)
    # The real pickup still accepts its valid direct input path; the same
    # live guard still rejects a path onto forbidden force metal. Proposal
    # boxes are not an AABB replacement for those exact physical predicates.
    assert guard['clear']([tuple(root.GetPosition()),tuple(pickup.GetPosition())])
    force_point=tuple(next(t for t in board.GetTracks()if t.GetNetname()==root.GetNetname()).GetEnd())
    assert not guard['clear']([tuple(root.GetPosition()),force_point,tuple(pickup.GetPosition())])
    assert before==field._field_snapshot_inventory(board)and guard['unchanged']()


@pytest.mark.parametrize('quarter',range(4))
def test_filtered_isolated_input_uses_real_layer_bridge_without_inventing_source_leaf(quarter):
    import cec_measurement_leaf_bridge as bridge
    board,demand,root,pickup=fixture()
    # A direct shunt input now correctly inherits the ratified via-less
    # front-layer policy. A filtered input has a different, schematic-named
    # series-resistor pickup and may still explore native layer escapes.
    pickup.SetPosition(pcbnew.VECTOR2I_MM(46,35))
    root.SetNet(board.FindNet('INPUT_A'))
    pickup=board.FindFootprintByReference('SERIES_A').FindPadByNumber('right')
    pickup.SetPosition(pcbnew.VECTOR2I_MM(20,10))
    for track in board.GetTracks():track.SetNet(root.GetNet())
    demand=next(d for d in get(board)['requests'] if d['pad_uuid']==force._uid(root))
    assert demand['source_topology']['kind']=='filtered'
    net=pcbnew.NETINFO_ITEM(board,'unrelated_surface_barrier');board.Add(net)
    wall=pcbnew.PCB_TRACK(board);wall.SetNet(net);wall.SetWidth(200000);wall.SetLayer(pcbnew.F_Cu)
    wall.SetStart(pcbnew.VECTOR2I_MM(15,1));wall.SetEnd(pcbnew.VECTOR2I_MM(15,59));board.Add(wall)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T);pivot=pcbnew.VECTOR2I_MM(30,30)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:item.Rotate(pivot,angle)
        demand=next(d for d in get(board)['requests'] if d['pad_uuid']==force._uid(root))
    before=field._field_snapshot_inventory(board)
    result=bridge.search_isolated(board,demand,width_nm=200000,timeout_s=3.)
    assert result['ops'] and any(op[0]=='via' for op in result['ops']),result
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+3.)
    assert guard['operations'](result['ops'])
    assert not result['source_owned_channel'] and not result['retirement_authority']
    assert not result['current_authority'] and not result['kelvin_qualified']
    assert before==field._field_snapshot_inventory(board)


@pytest.mark.parametrize('quarter',range(4))
def test_surface_pickup_does_not_license_same_net_force_contacts_underneath(quarter):
    board,demand,root,pickup=fixture()
    bus=pcbnew.PCB_TRACK(board);bus.SetNetCode(root.GetNetCode());bus.SetLayer(pcbnew.B_Cu)
    bus.SetWidth(1000000);bus.SetStart(pcbnew.VECTOR2I_MM(19,10));bus.SetEnd(pcbnew.VECTOR2I_MM(22,10));board.Add(bus)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T);pivot=pcbnew.VECTOR2I_MM(30,30)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:item.Rotate(pivot,angle)
        demand=next(d for d in get(board)['requests'] if d['pad_uuid']==force._uid(root))
    before=field._field_snapshot_inventory(board)
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+3.)
    at=tuple(pickup.GetPosition())
    assert guard['clear']([tuple(root.GetPosition()),at])
    assert not guard['barrel'](at,600000)
    assert not guard['operations']([('via',at,.3,.6)])
    assert before==field._field_snapshot_inventory(board)


@pytest.mark.parametrize('quarter',range(4))
def test_explicit_saved_length_domain_reaches_native_search_without_raising_bound(quarter):
    board,demand,root,pickup=fixture(quarter)
    before=field._field_snapshot_inventory(board)
    menu=route.menus(board,demand,width_nm=200000,timeout_s=2.,max_length_nm=11000000)
    assert menu['ops'] and menu['proposal_length_bound_nm']==11000000
    assert all(sum(math.dist(op[1],op[2])for op in ops)<=11000000 for ops in menu['ops'])
    assert before==field._field_snapshot_inventory(board)
    refused=route.menus(board,demand,width_nm=200000,timeout_s=.5,max_length_nm=9000000)
    assert not refused['ops'] and not refused['no_path_proof']
    assert refused['length_bound_refusals']>0
    assert before==field._field_snapshot_inventory(board)


@pytest.mark.parametrize('value',[True,-1,float('nan'),float('inf')])
def test_bad_saved_length_scope_is_never_silently_ignored(value):
    board,demand,root,pickup=fixture()
    with pytest.raises(ValueError):route.menus(board,demand,width_nm=200000,max_length_nm=value)
