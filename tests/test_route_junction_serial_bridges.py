"""Nearby endpoint aliases must not turn a real serial edge into a self-loop."""
import itertools

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_route_quality as quality


def native_board(points, face, quarter, mirror, reverse_serialization=False):
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'/renamed_signal',1);board.Add(net)
    def transform(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return x+43000000,y-17000000
    legs=list(zip(map(transform,points),map(transform,points[1:])))
    if reverse_serialization:legs=[(b,a)for a,b in reversed(legs)]
    for a,b in legs:
        track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(face)
        track.SetWidth(200000);track.SetLocked(True)
        track.SetStart(pcbnew.VECTOR2I(*a));track.SetEnd(pcbnew.VECTOR2I(*b));board.Add(track)
    return board


@pytest.mark.parametrize('face',[0,4,6,8,10,2])
@pytest.mark.parametrize('backstep',[False,True])
def test_serial_microedge_keeps_actual_direction_on_every_face(face,backstep):
    for delta,quarter,mirror in itertools.product((1,25,499),range(4),(False,True)):
        if backstep:
            points=[(0,0),(300000,300000),(300000-delta,300000+delta),
                    (2300000-delta,2300000+delta)]
        else:
            points=[(0,0),(300000,300000),(300000+delta,300000+delta),
                    (2300000+delta,300000+delta)]
        for reversed_items in (False,True):
            board=native_board(points,face,quarter,mirror,reversed_items)
            before=[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),t.IsLocked())
                    for t in board.GetTracks()]
            report=quality.analyze_board(board)
            assert report['reverse_diagonal_jog_count']==int(backstep),report
            assert report['craft_ok'] is (not backstep),report
            # No length threshold, snapping, copper deletion or board mutation.
            assert before==[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),t.IsLocked())
                            for t in board.GetTracks()]


def test_subdivided_serial_bridge_cannot_be_folded_indirectly():
    points=[(0,0),(300000,300000),(300001,300001),(300003,300003),
            (300004,300004),(2300004,300004)]
    board=native_board(points,2,1,True)
    rows=[quality._track_row(t)for t in board.GetTracks()]
    _junctions,aliases=quality._native_junction_inventory(rows)
    endpoints={(net,layer,at):key for key,points in aliases.items()
               for net,layer in (key[:2],)for at in points}
    for row in rows:
        assert endpoints[(row['net'],row['layer_id'],row['start'])]!=endpoints[(row['net'],row['layer_id'],row['end'])]
    assert quality.analyze_board(board)['craft_ok']


def test_alias_of_distinct_routes_still_catches_real_covered_contact():
    for delta in (1,25,999):
        board=native_board([(0,0),(2000000,0)],0,0,False)
        first=next(iter(board.GetTracks()));last=pcbnew.PCB_TRACK(board)
        last.SetNet(first.GetNet());last.SetLayer(0);last.SetWidth(200000)
        last.SetStart(pcbnew.VECTOR2I(45000000-delta,-17000000))
        last.SetEnd(pcbnew.VECTOR2I(44000000,-17000000));board.Add(last)
        report=quality.analyze_board(board)
        assert not report['craft_ok']
        assert any(row['type']=='covered_backtrack'and row['native_alias_contact_checked']
                   for row in report['issues'])


def test_distant_endpoints_of_one_route_do_not_prevent_other_native_aliases():
    board=native_board([(0,0),(2000000,0)],0,0,False)
    first=next(iter(board.GetTracks()));last=pcbnew.PCB_TRACK(board)
    last.SetNet(first.GetNet());last.SetLayer(0);last.SetWidth(200000)
    last.SetStart(pcbnew.VECTOR2I(45000001,-17000000))
    last.SetEnd(pcbnew.VECTOR2I(45000001,-15000000));board.Add(last)
    rows=[quality._track_row(t)for t in board.GetTracks()]
    _junctions,aliases=quality._native_junction_inventory(rows)
    assert any(len(points)==2 for points in aliases.values())
    assert quality.analyze_board(board)['craft_ok']
