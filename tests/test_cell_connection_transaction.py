"""Failed explicit route batches cannot contaminate later candidate attempts."""
import pcbnew
import pytest
import uuid
from cec_pipeline import cells


@pytest.fixture
def board(tmp_path):
    board = pcbnew.BOARD()
    board.SetFileName(str(tmp_path / 'synthetic.kicad_pcb'))
    for name in ('SIGNAL', 'FOREIGN'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    for a, b in (((0,0),(30,0)), ((30,0),(30,30)),
                 ((30,30),(0,30)), ((0,30),(0,0))):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts); board.Add(edge)
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(15, 8)); track.SetEnd(pcbnew.VECTOR2I_MM(15, 12))
    track.SetWidth(200000); track.SetLayer(pcbnew.F_Cu)
    track.SetNet(board.FindNet('FOREIGN')); track.SetLocked(True); board.Add(track)
    return board


def state(board):
    return sorted((str(t.m_Uuid.AsString()), t.GetClass(), tuple(t.GetStart()),
        tuple(t.GetEnd()), t.GetNetname(), t.GetLayer(),
        t.GetWidth(pcbnew.F_Cu) if t.GetClass() == 'PCB_VIA' else t.GetWidth(),
        t.IsLocked()) for t in board.GetTracks())


def route(points, net='SIGNAL'):
    return dict(net=net, layer='F.Cu', width_nm=200000,
        points_nm=[[int(x*1e6), int(y*1e6)] for x,y in points])


def test_later_leg_native_clearance_refusal_rolls_back_earlier_legs(board):
    before = state(board)
    with pytest.raises(ValueError, match='foreign_copper'):
        cells.emit_connections(board, [route([(5,5),(10,5),(15,10),(20,10)])], [], identity='failed')
    assert state(board) == before
    # A subsequent valid batch must behave exactly like a fresh attempt.
    added = cells.emit_connections(board, [route([(5,5),(10,5)])], [], identity='failed')
    assert len(added) == 1 and len(state(board)) == len(before)+1


@pytest.mark.parametrize('fault', ['route', 'via', 'late_via'])
def test_later_batch_refusal_rolls_back_complete_routes_and_vias(board, fault):
    before = state(board)
    routes = [route([(5,5),(10,5)])]
    good = dict(net='SIGNAL', at_nm=[8000000,5000000], diameter_nm=600000, drill_nm=300000)
    bad = dict(good, drill_nm=1000)
    vias = []
    if fault == 'route': routes.append(dict(route([(5,15),(10,15)]), net='missing'))
    elif fault == 'via': vias = [bad]
    else: vias = [good, bad]
    expected = 'literal_source_net' if fault == 'route' else 'saved_process_via_dimensions'
    with pytest.raises(ValueError, match=expected):
        cells.emit_connections(board, routes, vias, identity='failed-batch')
    assert state(board) == before


def test_new_route_is_seen_as_foreign_by_later_route_in_batch(board):
    before = state(board)
    routes = [route([(5,5),(10,5)]), route([(8,3),(8,7)], net='FOREIGN')]
    with pytest.raises(ValueError, match='foreign_copper'):
        cells.emit_connections(board, routes, [], identity='crossing')
    assert state(board) == before


def test_existing_identity_collision_preserves_existing_copper(board):
    routes = [route([(5,5),(10,5)])]
    cells.emit_connections(board, routes, [], identity='same')
    before = state(board)
    with pytest.raises(ValueError, match='must_not_alias'):
        cells.emit_connections(board, routes, [], identity='same')
    assert state(board) == before


def test_success_returns_complete_added_identity_set(board):
    before = state(board)
    routes = [route([(5,5),(10,5),(12,7)])]
    via = dict(net='SIGNAL', at_nm=[12000000,7000000], diameter_nm=600000, drill_nm=300000)
    added = cells.emit_connections(board, routes, [via], identity='success')
    assert len(added) == len(set(added)) == 3
    assert len(state(board)) == len(before)+3
    assert set(added) == {row[0] for row in state(board)} - {row[0] for row in before}


@pytest.mark.parametrize('kind', ['footprint', 'pad', 'field', 'drawing', 'zone', 'group'])
@pytest.mark.parametrize('incoming_kind', ['route', 'via'])
def test_connection_cannot_alias_an_existing_nontrack_item(board, kind, incoming_kind):
    fp = pcbnew.FOOTPRINT(board); board.Add(fp)
    if kind == 'footprint': item = fp
    elif kind == 'pad': item = pcbnew.PAD(fp); fp.Add(item)
    elif kind == 'field': item = fp.Reference()
    elif kind == 'drawing': item = pcbnew.PCB_SHAPE(board); board.Add(item)
    elif kind == 'zone': item = pcbnew.ZONE(board); board.Add(item)
    else: item = pcbnew.PCB_GROUP(board); board.Add(item)
    token = 'alias:route:0:0' if incoming_kind == 'route' else 'alias:via:0'
    item.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL, token))))
    before = state(board)
    routes = [route([(5,5),(10,5)])]
    vias = [] if incoming_kind == 'route' else [dict(net='SIGNAL',
        at_nm=[10000000,5000000], diameter_nm=600000, drill_nm=300000)]
    with pytest.raises(ValueError, match='must_not_alias_existing_native_item'):
        cells.emit_connections(board, routes, vias, identity='alias')
    assert state(board) == before
    assert board.ResolveItem(item.m_Uuid, True) is not None
