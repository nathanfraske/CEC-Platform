"""A new trunk cannot inherit false spacing failures from terminal fanouts."""
import pytest
import pcbnew
import cec_precision_route as route


def fixture(transform=lambda xy: xy, spacing=.4):
    board = pcbnew.BOARD(); board.SetCopperLayerCount(4)
    pair = dict(name='arbitrary', p='DATA+', n='DATA-', width=.2, gap=.34,
                clearance=.2)
    for net in (pair['p'], pair['n']):
        board.Add(pcbnew.NETINFO_ITEM(board, net))
    def track(net, a, b, layer):
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(*transform(a)))
        item.SetEnd(pcbnew.VECTOR2I_MM(*transform(b)))
        item.SetWidth(pcbnew.FromMM(.2)); item.SetLayer(layer)
        item.SetNet(board.FindNet(net)); board.Add(item)
        return item.m_Uuid.AsString()
    old = {track(pair['p'], (10,10), (11,10), pcbnew.F_Cu),
           track(pair['n'], (10,10+spacing), (11,10+spacing), pcbnew.F_Cu)}
    new = {track(pair['p'], (20,20), (30,20), pcbnew.B_Cu),
           track(pair['n'], (20,20.54), (30,20.54), pcbnew.B_Cu)}
    return board, pair, old, new, track


@pytest.mark.parametrize('transform', [lambda p:p, lambda p:(p[0]+8,p[1]+7),
    lambda p:(-p[1],p[0]), lambda p:(-p[0],p[1])])
def test_unchanged_terminal_taper_does_not_reject_unrelated_new_trunk(transform):
    board,pair,old,new,_ = fixture(transform)
    assert not route._pair_graph_geometry(board,pair,old|new)['ok']
    assert route._pair_graph_geometry(board,pair,old|new,strict_ids=new)['ok']


def test_unchanged_native_clearance_failure_is_not_waived():
    board,pair,old,new,_ = fixture(spacing=.39)
    report = route._pair_graph_geometry(board,pair,old|new,strict_ids=new)
    assert not report['ok']
    assert report['issues'][0]['type']=='member_clearance'


def test_new_to_old_interaction_still_holds_full_electrical_gap():
    board,pair,old,new,track = fixture()
    extra = track(pair['n'], (10,9.5), (11,9.5), pcbnew.F_Cu)
    new.add(extra)
    report = route._pair_graph_geometry(board,pair,old|new,strict_ids=new)
    assert not report['ok']
    assert any(row.get('n_uuid')==extra and row['minimum_mm']>.53
               for row in report['issues'])


def test_new_member_crossing_is_never_excluded():
    board,pair,old,new,track = fixture()
    extra = track(pair['n'], (10.5,9), (10.5,11), pcbnew.F_Cu)
    new.add(extra)
    report = route._pair_graph_geometry(board,pair,old|new,strict_ids=new)
    assert not report['ok']
    assert any(row['type']=='member_crossing' for row in report['issues'])


@pytest.mark.parametrize('transform', [lambda p:p,lambda p:(p[0]+40,p[1]+30),
    lambda p:(-p[1],p[0]),lambda p:(-p[0],p[1])])
def test_nanometre_tail_cannot_hide_an_acute_reversal(transform):
    # The old absolute dot-product epsilon accepted this near-180 turn.
    path=[transform(p) for p in [(0,0),(0,1),(1e-6,1-1e-6)]]
    assert route._polyline_has_reverse_bend(path)
    assert route._polyline_min_opening_angle(path)<89


def test_self_crossing_member_is_filtered_before_joint_selection():
    loop=[(0,0),(2,0),(2,2),(-1,2),(-1,1),(1,1),(1,-1)]
    assert route._polyline_has_self_crossing(loop)
    legal=[(0,0),(0,-1),(1,-1)]
    partner=[(0,-3),(1,-3)]
    selected=route._ranked_joint_escape([loop,legal],[partner],
        p_span=1.,n_span=1.,width=.2,gap=.2)
    assert selected==(legal,partner)


def test_right_angle_and_45_degree_bends_remain_available():
    for path in [[(0,0),(0,1),(1,1)],[(0,0),(0,1),(1,2)]]:
        assert not route._polyline_has_reverse_bend(path)
        assert not route._polyline_has_self_crossing(path)
