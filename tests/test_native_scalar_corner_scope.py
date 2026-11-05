"""Native fixtures: scheduling cannot turn immutable launches into authority."""
import pytest
import pcbnew
from root_native_scalar_corner_scope_20261012 import select


def fixture(netname='renamed_scalar', offset=(0, 0), turns=0):
    board = pcbnew.BOARD()
    net = pcbnew.NETINFO_ITEM(board, netname)
    board.Add(net)
    def point(x, y):
        for _ in range(turns):
            x, y = -y, x
        return pcbnew.VECTOR2I(x + offset[0], y + offset[1])
    def leg(a, b):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(point(*a)); t.SetEnd(point(*b))
        t.SetWidth(200000); t.SetLayer(pcbnew.F_Cu); t.SetNetCode(net.GetNetCode())
        board.Add(t)
        return t
    # An earlier lexical corner is a real layer-change launch.
    leg((0, 1000000), (0, 0)); leg((0, 0), (1000000, 0))
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(point(0, 0)); via.SetWidth(600000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNetCode(net.GetNetCode())
    board.Add(via)
    a = leg((2000000, 3000000), (2000000, 2000000))
    b = leg((2000000, 2000000), (3000000, 2000000))
    return board, {netname}, (a, b), point


@pytest.mark.parametrize('turns', range(4))
@pytest.mark.parametrize('netname,offset', [('q', (0, 0)), ('totally_renamed', (5000000, -1000000))])
def test_launches_do_not_starve_later_native_corner(turns, netname, offset):
    board, nets, corner, _ = fixture(netname, offset, turns)
    result = select(board, nets, maximum_candidates=1, maximum_scoped_tracks=2)
    assert result['scope'] == sorted(t.m_Uuid.AsString() for t in corner)
    assert result['skipped']['immutable_launch'] == 1
    assert result['mutation_or_contact_authority_granted'] is False


def test_pad_launch_is_excluded_and_source_unchanged():
    board, nets, corner, point = fixture()
    fp = pcbnew.FOOTPRINT(board); board.Add(fp)
    pad = pcbnew.PAD(fp); pad.SetNumber('9'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
    pad.SetLayerSet(layers); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I(600000, 600000)); pad.SetPosition(point(2000000, 2000000))
    fp.Add(pad)
    before = [(t.m_Uuid.AsString(), tuple(t.GetPosition()), t.IsLocked()) for t in board.GetTracks()]
    result = select(board, nets)
    assert not result['selected'] and result['skipped']['immutable_launch'] == 2
    assert before == [(t.m_Uuid.AsString(), tuple(t.GetPosition()), t.IsLocked()) for t in board.GetTracks()]


def test_short_and_grouped_or_noneligible_corners_never_grant_scope():
    board, nets, corner, _ = fixture()
    assert not select(board, {'different'})['selected']
    assert not select(board, nets, minimum_chamfer_nm=500000)['selected']
    group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(corner[0])
    assert not select(board, nets)['selected']


@pytest.mark.parametrize('turns', range(4))
@pytest.mark.parametrize('netname,offset', [('q', (0, 0)), ('small_renamed', (9000000, -4000000))])
def test_explicit_short_bend_floor_matches_finite_inset_ceiling(turns, netname, offset):
    board, nets, corner, point = fixture(netname, offset, turns)
    corner[0].SetStart(point(2000000, 2080000))
    corner[1].SetEnd(point(2080000, 2000000))
    baseline = select(board, nets)
    assert not baseline['selected'] and baseline['skipped']['too_short'] == 1
    result = select(board, nets, minimum_chamfer_nm=20000)
    assert result['scope'] == sorted(t.m_Uuid.AsString() for t in corner)
    assert result['skipped']['immutable_launch'] == 1
    assert result['mutation_or_contact_authority_granted'] is False
    assert not select(board, nets, minimum_chamfer_nm=32001)['selected']


@pytest.mark.parametrize('kw', [dict(maximum_candidates=True), dict(maximum_scoped_tracks=1),
    dict(maximum_width_nm=float('nan')), dict(timeout_s=float('inf')),
    dict(timeout_s=30), dict(minimum_chamfer_nm=0), dict(junction_tolerance_nm=-1)])
def test_invalid_bounds_refuse(kw):
    board, nets, _, _ = fixture()
    with pytest.raises(ValueError): select(board, nets, **kw)


def test_complete_inventory_bound_and_positive_scope_refuse():
    board, nets, _, _ = fixture()
    with pytest.raises(ValueError): select(board, nets, maximum_items=2)
    with pytest.raises(ValueError): select(board, ['not_positive_set'])


@pytest.mark.parametrize('turns',range(4))
@pytest.mark.parametrize('offset',[(0,0),(9000000,-4000000)])
def test_actual_same_net_body_tee_is_not_retried_as_a_cosmetic_corner(turns,offset):
    board,nets,corner,point=fixture('different_name',offset,turns)
    tap=pcbnew.PCB_TRACK(board);tap.SetNetCode(corner[0].GetNetCode());tap.SetLayer(pcbnew.F_Cu)
    tap.SetStart(point(1500000,1500000));tap.SetEnd(point(2500000,2500000));tap.SetWidth(200000);board.Add(tap)
    before=[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd())) for t in board.GetTracks()]
    result=select(board,nets)
    assert not result['selected'] and result['skipped']['immutable_body_tee']==1
    assert result['immutable_body_tees'][0]['actual_native_body_track_uuids']==[tap.m_Uuid.AsString()]
    assert before==[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd())) for t in board.GetTracks()]


@pytest.mark.parametrize('case',['other_layer','other_net','near_but_not_native_contact','beyond_endpoint'])
def test_bbox_or_another_electrical_node_cannot_supply_a_body_tee_exemption(case):
    board,nets,corner,point=fixture()
    tap=pcbnew.PCB_TRACK(board);tap.SetNetCode(corner[0].GetNetCode());tap.SetLayer(pcbnew.F_Cu)
    tap.SetStart(point(1500000,1500000));tap.SetEnd(point(2500000,2500000));tap.SetWidth(200000)
    if case=='other_layer':tap.SetLayer(pcbnew.B_Cu)
    elif case=='other_net':net=pcbnew.NETINFO_ITEM(board,'other');board.Add(net);tap.SetNet(net)
    elif case=='near_but_not_native_contact':
        tap.SetWidth(1000);tap.SetStart(point(1500000,1510000));tap.SetEnd(point(2500000,2510000))
    elif case=='beyond_endpoint':tap.SetEnd(point(1900000,1900000))
    board.Add(tap);result=select(board,nets)
    assert len(result['selected'])==1 and not result['immutable_body_tees']
