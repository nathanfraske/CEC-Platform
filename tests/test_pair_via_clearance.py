import pcbnew
import cec_precision_route as precision


PAIR = dict(name='ANY', p='P', n='N', width=.2, gap=.2, clearance=.2)


def fixture():
    board = pcbnew.BOARD()
    for name in ('P', 'N'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(3, 3))
    via.SetWidth(pcbnew.FromMM(.6))
    via.SetDrill(pcbnew.FromMM(.3))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(board.FindNet('P'))
    board.Add(via)
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(2, 3.5))
    track.SetEnd(pcbnew.VECTOR2I_MM(4, 3.5))
    track.SetWidth(pcbnew.FromMM(.2))
    track.SetLayer(pcbnew.B_Cu)
    track.SetNet(board.FindNet('N'))
    board.Add(track)
    return board, via, track


def test_pair_centerline_gap_cannot_waive_annular_land_clearance():
    board, via, track = fixture()
    # Centreline distance .5 > trace-pair pitch .4, but the actual annular
    # land leaves only .1 clearance, not the required .2.
    created = {via.m_Uuid.AsString(), track.m_Uuid.AsString()}
    report = precision._pair_graph_geometry(board, PAIR, created)
    assert not report['ok']
    assert any(row['type']=='member_via_clearance' and row['layer']=='B.Cu'
               for row in report['issues'])


def test_new_ribbon_sees_existing_via_and_exact_minimum_remains_legal():
    board, via, track = fixture()
    scope = {track.m_Uuid.AsString()}
    assert precision._pair_via_clearance_issues(board, PAIR, scope)
    track.Move(pcbnew.VECTOR2I_MM(0, .1))
    assert not precision._pair_via_clearance_issues(board, PAIR, scope)
    # Existing unrelated debt is not attributed to an empty transaction.
    track.Move(pcbnew.VECTOR2I_MM(0, -.1))
    assert not precision._pair_via_clearance_issues(board, PAIR, set())


def test_opposite_pad_land_is_checked_but_same_net_is_allowed():
    board, via, track = fixture()
    board.Remove(track)
    footprint = pcbnew.FOOTPRINT(board)
    board.Add(footprint)
    pad = pcbnew.PAD(footprint)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.4, .4))
    pad.SetPosition(pcbnew.VECTOR2I_MM(3.6, 3))
    layers = pcbnew.LSET()
    layers.AddLayer(pcbnew.F_Cu)
    pad.SetLayerSet(layers)
    pad.SetNet(board.FindNet('N'))
    footprint.Add(pad)
    scope = {via.m_Uuid.AsString()}
    assert precision._pair_via_clearance_issues(board, PAIR, scope)
    pad.SetNet(board.FindNet('P'))
    assert not precision._pair_via_clearance_issues(board, PAIR, scope)
