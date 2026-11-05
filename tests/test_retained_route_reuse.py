"""No board/refdes/coordinate special case in native departure reuse."""
import pytest
from cec_retained_route_reuse import uncovered_segments, native_uncovered_plan


@pytest.mark.parametrize('a,b,cut,expected', [
    ((0,0),(10,0),((0,0),(4,0)),[((4,0),(10,0),2)]),
    ((10,0),(0,0),((10,0),(6,0)),[((6,0),(0,0),2)]),
    ((0,0),(0,-10),((0,0),(0,-4)),[((0,-4),(0,-10),2)]),
    ((0,0),(10,10),((3,3),(7,7)),[((0,0),(3,3),2),((7,7),(10,10),2)]),
    ((0,0),(-10,10),((-7,7),(-3,3)),[((0,0),(-3,3),2),((-7,7),(-10,10),2)]),
])
def test_exact_integer_coverage_preserves_direction(a,b,cut,expected):
    assert uncovered_segments([(a,b,2)], [(*cut,2)]) == expected


def test_union_never_duplicates_overlapping_coverage():
    assert uncovered_segments([((0,0),(10,0),2)], [
        ((-2,0),(4,0),3),((3,0),(6,0),2),((6,0),(20,0),2)]) == []


@pytest.mark.parametrize('retained', [
    [((0,0),(10,0),1)],  # Not enough width.
    [((0,1),(10,1),2)],  # Nearby, but not exact collinear coverage.
    [((5,-2),(5,2),2)],  # A crossing does not cover any interval.
    [((5,0),(5,0),2)],  # Round endpoint is not a track body.
])
def test_no_geometric_or_width_credit_without_exact_coverage(retained):
    plan=[((0,0),(10,0),2)]
    assert uncovered_segments(plan,retained)==plan


def test_profiled_widths_are_not_relaxed():
    assert uncovered_segments([((0,0),(4,0),2),((4,0),(10,0),4)],
        [((0,0),(10,0),2)]) == [((4,0),(10,0),4)]


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('names',[('/LINK_P','/LINK_N'),('/DATA_A','/DATA_B')])
def test_partial_native_departure_closes_missing_duplicate_without_overlapping_source(angle,names):
    import pcbnew
    import cec_fr
    from test_pair_package_preclosure import fixture
    board,groups,pair=fixture(angle,names)
    # Complete one member with the native atomic constructor; remove just the
    # other member's middle bridge. The retained departures are source copper.
    initial=cec_fr.synthesize_same_footprint_links(board,pair_declarations=[pair])
    assert initial['pair_linked']==2
    member=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==names[1]]
    pads=groups[names[1]]
    delta=pads[1].GetPosition()-pads[0].GetPosition()
    middle=[t for t in member if
            (t.GetEnd().x-t.GetStart().x)*delta.y
            ==(t.GetEnd().y-t.GetStart().y)*delta.x]
    assert len(middle)==1
    board.Remove(middle[0]);board.BuildConnectivity()
    before={t.m_Uuid.AsString(): (t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth())
            for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'}
    report=cec_fr.synthesize_same_footprint_links(board,pair_declarations=[pair])
    assert report['pair_linked']==1 and report['pair_refused']==0
    incoming=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.m_Uuid.AsString() not in before]
    assert len(incoming)==1
    assert incoming[0].GetNetname()==names[1]
    for t in board.GetTracks():
        if t.m_Uuid.AsString() in before:
            assert before[t.m_Uuid.AsString()]==(t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth())
    board.BuildConnectivity()
    assert pads[1].m_Uuid.AsString() in {i.m_Uuid.AsString()
        for i in board.GetConnectivity().GetConnectedItems(pads[0])}


@pytest.mark.parametrize('fault',['layer','net','thin'])
def test_native_layer_net_and_width_binding(fault):
    import pcbnew
    board=pcbnew.BOARD()
    for name in ('A','B'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(0,0));t.SetEnd(pcbnew.VECTOR2I(10,0))
    t.SetNet(board.FindNet('B' if fault=='net' else 'A'))
    t.SetLayer(pcbnew.B_Cu if fault=='layer' else pcbnew.F_Cu)
    t.SetWidth(1 if fault=='thin' else 2);board.Add(t)
    plan=[(pcbnew.VECTOR2I(0,0),pcbnew.VECTOR2I(10,0),2)]
    out=native_uncovered_plan(board,'A',plan,pcbnew.F_Cu)
    assert [(a.x,a.y,b.x,b.y,w) for a,b,w in out]==[(0,0,10,0,2)]
