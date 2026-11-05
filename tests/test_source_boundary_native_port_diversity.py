"""Real plated source access must not be crowded out by nearby track aliases."""
import time

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_native_component_ports as ports
import cec_native_via_frontier as frontier


def fixture(monkeypatch, name, quarter, plated):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    board.GetDesignSettings().m_TrackMinWidth = 200000
    board.GetDesignSettings().m_MinClearance = 200000
    net = pcbnew.NETINFO_ITEM(board, name)
    foreign = pcbnew.NETINFO_ITEM(board, 'unrelated_wall')
    board.Add(net)
    board.Add(foreign)

    def pad(x, y, *, through=False):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference('renamed_contact_' + str(x) + '_' + str(y))
        board.Add(fp)
        item = pcbnew.PAD(fp)
        item.SetNumber('1')
        item.SetNet(net)
        item.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        item.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
        item.SetAttribute(pcbnew.PAD_ATTRIB_PTH if through else pcbnew.PAD_ATTRIB_SMD)
        item.SetLayerSet(pcbnew.LSET.AllCuMask() if through else pcbnew.PAD.SMDMask())
        if through:
            item.SetDrillSize(pcbnew.VECTOR2I_MM(.4, .4))
        fp.Add(item)
        item.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        return item

    def via(x, y):
        item = pcbnew.PCB_VIA(board)
        item.SetPosition(pcbnew.VECTOR2I_MM(x, y))
        item.SetWidth(600000)
        item.SetDrill(300000)
        item.SetViaType(pcbnew.VIATYPE_THROUGH)
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetNet(net)
        board.Add(item)
        return item

    def track(start, end, *, wall=False):
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(*start))
        item.SetEnd(pcbnew.VECTOR2I_MM(*end))
        item.SetWidth(600000 if wall else 200000)
        item.SetNet(foreign if wall else net)
        item.SetLayer(pcbnew.F_Cu)
        board.Add(item)

    anchor = pad(20, 10)
    target = via(30, 10)
    root = (via(10, 10) if plated == 'via' else
        pad(10, 10, through=plated == 'pth'))
    track((10, 10), (20, 10))
    for index in range(20):
        track((20 + index*.001, 10), (20.001 + index*.001, 10))
    # This wall reaches the board edges, so top copper cannot go around it.
    track((25, 0), (25, 30), wall=True)
    island = via(28, 18)  # Same net, not this retained component.
    for a, b in [((0, 0), (40, 0)), ((40, 0), (40, 30)),
                 ((40, 30), (0, 30)), ((0, 30), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        board.Add(edge)
    if quarter:
        angle = pcbnew.EDA_ANGLE(quarter*90, pcbnew.DEGREES_T)
        centre = pcbnew.VECTOR2I_MM(20, 15)
        for item in [*board.GetFootprints(), *board.GetTracks(), *board.GetDrawings()]:
            item.Rotate(centre, angle)

    def endpoint(item):
        return dict(at_nm=list(item.GetPosition()), layers=[int(pcbnew.F_Cu)],
            native_uuids=[force._uid(item)])
    request = dict(kind='source_boundary', net=name, a=endpoint(anchor),
        b=endpoint(target), width_nm=200000)
    # These tests isolate native existing-contact scheduling. The native
    # copper/edge guards are real; no new-hole or fallback route is supplied.
    monkeypatch.setattr(escape.cell, '_supply_current_widths', lambda *a, **k:None)
    monkeypatch.setattr(escape.cell, '_netclass',
        lambda *a, **k:dict(width=200000, clearance=200000))
    monkeypatch.setattr(escape.fr, '_lastmile_bridge', lambda *a, **k:None)
    monkeypatch.setattr(escape.fr, '_guarded_profiled_lastmile_legs', lambda *a, **k:None)
    monkeypatch.setattr(frontier, 'sites', lambda *a, **k:dict(sites_nm=[]))
    return board, request, root, island


@pytest.mark.parametrize('name', ['opaque_control', '/other/renamed_terminal'])
@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('plated', ['via', 'pth'])
@pytest.mark.parametrize('binding', ['native_item', 'literal_pad'])
def test_scalar_menu_uses_real_plated_exit_before_near_aliases(monkeypatch, name, quarter, plated, binding):
    board, request, root, island = fixture(monkeypatch, name, quarter, plated)
    if binding == 'literal_pad':
        request['a']['pad_uuid'] = request['a'].pop('native_uuids')[0]
    before = row._source_binding(board)
    nearest = ports.endpoints(board, name, request['a'], toward_nm=request['b']['at_nm'],
        deadline=time.monotonic()+2.)
    assert force._uid(root) not in {u for p in nearest for u in p.get('native_uuids', [])}
    choices = []
    detail = {}
    permitted = [int(pcbnew.In2_Cu), int(pcbnew.B_Cu)]
    escape._connection_menu(board, request, board_hint='opaque_fixture',
        deadline=time.monotonic()+2., layers=permitted, append=choices.append, detail=detail)
    assert choices, detail
    routes = [ops for ops in choices if ops and all(op[0] == 'trk' for op in ops)
        and any(op[4] in permitted for op in ops)]
    assert routes, detail
    assert any(tuple(ops[0][1]) == tuple(root.GetPosition()) for ops in routes)
    assert all(op[4] in [int(pcbnew.F_Cu), *permitted] for ops in choices for op in ops)
    assert all(op[3] == 200000 for ops in routes for op in ops)
    assert all(tuple(op[1]) != tuple(island.GetPosition()) and
        tuple(op[2]) != tuple(island.GetPosition()) for ops in routes for op in ops)
    assert row._source_binding(board) == before


@pytest.mark.parametrize('fault', ['missing', 'track_not_pad', 'wrong_net', 'off_material'])
def test_literal_pad_contact_cannot_forge_a_native_component(monkeypatch, fault):
    board, request, root, island = fixture(monkeypatch, 'literal_pad_identity', 0, 'via')
    uid = request['a'].pop('native_uuids')[0]
    request['a']['pad_uuid'] = uid
    if fault == 'missing':
        request['a']['pad_uuid'] = 'not_a_native_pad'
    elif fault == 'track_not_pad':
        request['a']['pad_uuid'] = force._uid(next(iter(board.GetTracks())))
    elif fault == 'wrong_net':
        pad = next(p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p) == uid)
        pad.SetNet(board.FindNet('unrelated_wall'))
    else:
        request['a']['at_nm'][1] += 2000000
    before = row._source_binding(board)
    with pytest.raises(ValueError):
        escape._connection_menu(board, request, board_hint='opaque_fixture',
            deadline=time.monotonic()+1., layers=[int(pcbnew.B_Cu)],
            append=lambda ops:pytest.fail('forged native pad produced copper'), detail={})
    assert row._source_binding(board) == before


@pytest.mark.parametrize('quarter', range(4))
def test_smd_component_or_unconnected_same_net_via_cannot_invent_layer_access(monkeypatch, quarter):
    board, request, root, island = fixture(monkeypatch, 'no_ghost_barrel', quarter, 'smd')
    before = row._source_binding(board)
    choices = []
    escape._connection_menu(board, request, board_hint='opaque_fixture',
        deadline=time.monotonic()+1., layers=[int(pcbnew.In2_Cu), int(pcbnew.B_Cu)],
        append=choices.append, detail={})
    assert not choices
    assert row._source_binding(board) == before
