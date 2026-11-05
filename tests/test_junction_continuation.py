"""Board-independent reach and ranking regressions for paired local stars."""
import math
import pytest
import cec_precision_route as p


def geometry(scale=1.0, angle=0.0, translation=(0.0, 0.0)):
    def point(x, y):
        return (translation[0] + scale * (x * math.cos(angle) - y * math.sin(angle)),
                translation[1] + scale * (x * math.sin(angle) + y * math.cos(angle)))
    plan = {'ports': {'node': {'center': point(0, 0)},
                      'left': {'center': point(-2, 0)},
                      'right': {'center': point(0, 2)}}}
    pair = {'width': 0.2 * scale, 'gap': 0.25 * scale}
    junction = {'center': point(0, 0), 'p': point(-0.225, 0),
                'n': point(0.225, 0), 'embedding_sign': 1, 'distance_mm': scale * 1.5}
    edges = [{'a': 'node', 'b': peer, 'length_mm': 2 * scale}
             for peer in ('left', 'right')]
    embedding = {('node', 'F.Cu'): {'through': ['left', 'right']}}
    return plan, pair, junction, edges, embedding


@pytest.mark.parametrize('angle', [0, math.pi/4, math.pi/2, math.pi])
@pytest.mark.parametrize('scale', [0.5, 1.0, 2.0])
def test_short_junction_runways_reserve_peer_corridor(angle, scale):
    plan, pair, junction, edges, embedding = geometry(scale, angle, (41, -17))
    cell = p._mitered_junction_candidate(plan, pair, 'node', 'F.Cu',
                                        junction, edges, embedding)
    for peer, throat in cell['_junction_throats'].items():
        center = cell['center']
        heading = throat['route_heading']
        projection = sum((plan['ports'][peer]['center'][i] - center[i]) * heading[i]
                         for i in (0, 1))
        assert p._dist(throat['center'], center) <= 0.45 * projection + 1e-5
        assert p._dist(throat['p'], throat['n']) == pytest.approx(pair['width'] + pair['gap'])
        for member in ('p', 'n'):
            assert p._polyline_is_octilinear([throat['_runway_origin'][member], throat[member]])


@pytest.mark.parametrize('fraction', [0, -0.1, 0.51, float('nan'), float('inf')])
def test_invalid_runway_policy_refuses(fraction):
    plan, pair, junction, edges, embedding = geometry()
    with pytest.raises(ValueError, match='edge fraction'):
        p._mitered_junction_candidate(plan, pair, 'node', 'F.Cu', junction,
                                     edges, embedding, max_edge_fraction=fraction)


def test_continuation_rank_counts_both_members_and_only_new_copper():
    pcb = p.pcbnew
    board = pcb.BOARD()
    nets = {}
    for code, name in enumerate(('POS', 'NEG', 'FIXED'), 1):
        nets[name] = pcb.NETINFO_ITEM(board, name, code)
        board.Add(nets[name])
    scope = set()
    for name, length, include in [('POS', 2, True), ('NEG', 5, True),
                                  ('FIXED', 100, True), ('NEG', 100, False)]:
        item = pcb.PCB_TRACK(board)
        item.SetNet(nets[name]); item.SetLayer(pcb.F_Cu); item.SetWidth(200000)
        item.SetStart(pcb.VECTOR2I(0, 0))
        item.SetEnd(pcb.VECTOR2I(length * 1000000, 0))
        board.Add(item)
        if include: scope.add(item.m_Uuid.AsString())
    pair = {'p': 'POS', 'n': 'NEG', 'width': .2, 'gap': .25}
    plan = {'ports': {'node': {'center': (0, 0)},
                      'peer': {'p': (5, 0), 'n': (7, 1)}}}
    rank = p._junction_continuation_rank(board, pair, plan, 'node',
        {'center': (0, 0)}, {'peer': {'p': (2, 0), 'n': (5, 1)}}, scope)
    # Two of the 14 scoped samples lie just past the shorter member's end.
    assert rank == (round(5*(1-2/14),6), 7, 12, 0)


def test_rank_prefers_balanced_members_over_smaller_sum():
    class Board:
        def GetTracks(self): return []
    pair = {'p': 'POS', 'n': 'NEG'}
    plan = {'ports': {'node': {'center': (0, 0)},
                      'peer': {'p': (0, 0), 'n': (0, 1)}}}
    def rank(p_x, n_x):
        return p._junction_continuation_rank(Board(), pair, plan, 'node',
            {'center': (0, 0)}, {'peer': {'p': (p_x, 0), 'n': (n_x, 1)}}, set())
    assert rank(5, 5) < rank(1, 8)


def test_rank_prefers_less_separated_copper_not_a_better_percentage(monkeypatch):
    pcb = p.pcbnew
    board = pcb.BOARD()
    pair = {'p':'X','n':'Y','width':.2,'gap':.25}
    scope = set()
    for name in ('X','Y'):
        net = pcb.NETINFO_ITEM(board,name);board.Add(net)
        track = pcb.PCB_TRACK(board);track.SetNet(net)
        track.SetStart(pcb.VECTOR2I(0,0));track.SetEnd(pcb.VECTOR2I(10000000,0))
        board.Add(track);scope.add(track.m_Uuid.AsString())
    plan = {'ports':{'junction':{'center':(0,0)}}}
    def rank(fraction):
        monkeypatch.setattr(p,'_pair_coupling_summary',lambda *a,**k:{'fraction':fraction})
        return p._junction_continuation_rank(board,pair,plan,'junction',{'center':(0,0)},{},scope)
    assert rank(.8) < rank(.5)
    good = rank(.8)
    # A longer loop with a higher percentage but MORE separated millimetres
    # does not dominate the short star (100mm x 5% versus 10mm x 20%).
    for item in board.GetTracks():item.SetEnd(pcb.VECTOR2I(100000000,0))
    assert good < rank(.95)
