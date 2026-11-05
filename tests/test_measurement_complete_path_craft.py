"""The fixed pickup tail cannot hide an acute reversal in a valid prefix."""
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_measurement_terminal_route as route
import cec_isolated_measurement_completion as isolated
from test_measurement_terminal_route import fixture
from test_isolated_measurement_completion import case


def rotate(points,quarter):
    result=[]
    for x,y in points:
        x-=30000000;y-=30000000
        # Match KiCad's native screen-coordinate positive rotation.
        for _ in range(quarter):x,y=y,-x
        result.append((x+30000000,y+30000000))
    return result


def bad_points(quarter):
    return rotate([(10000000,10000000),(17000000,10000000),
        (18000000,9000000),(18000000,10000000),(20000000,10000000)],quarter)


def ops(points):
    return [['trk',list(a),list(b),200000,int(pcbnew.F_Cu)]for a,b in zip(points,points[1:])]


@pytest.mark.parametrize('quarter',range(4))
def test_complete_pickup_tail_refuses_backtrack_even_when_contact_and_prefix_pass(quarter):
    board,demand,root,pickup=fixture(quarter);before=field._field_snapshot_inventory(board)
    path=bad_points(quarter)
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+10.)
    assert guard['clear'](path), 'This fixture isolates craft, not a contact or policy failure'
    prefix=route.assess_path_craft(board,ops(path[:3]),net=demand['net'],deadline=time.monotonic()+10.)
    assert prefix['ok']and prefix['complete'],prefix
    full=route.assess_path_craft(board,ops(path),net=demand['net'],deadline=time.monotonic()+10.)
    assert full['complete']and full['ok']is False
    assert any(i['type']=='acute_backtrack'for i in full['issues']),full
    assert field._field_snapshot_inventory(board)==before and guard['unchanged']()


@pytest.mark.parametrize('quarter',range(4))
def test_saved_receiver_independently_rejects_worker_authored_bad_tail(tmp_path,monkeypatch,quarter):
    source,uid,target=case(tmp_path,monkeypatch,quarter)
    candidate=force._copy_family(source,tmp_path/'bad-tail');board=pcbnew.LoadBoard(str(candidate))
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==uid)
    for op in ops(bad_points(quarter)):
        track=pcbnew.PCB_TRACK(board);track.SetNet(pad.GetNet());track.SetLayer(op[4])
        track.SetWidth(op[3]);track.SetStart(pcbnew.VECTOR2I(*op[1]));track.SetEnd(pcbnew.VECTOR2I(*op[2]));board.Add(track)
    field._save_field_snapshot(board,candidate);before=[p.read_bytes()for p in(source,candidate)]
    q=isolated.receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=uid)
    assert q['ok']is False and q['complete']is False
    assert any('pickup_tail_loses_route_craft'in e for e in q['errors']),q
    assert q['complete_saved_path_craft']['complete']and q['complete_saved_path_craft']['ok']is False
    assert [p.read_bytes()for p in(source,candidate)]==before


def test_maze_validator_includes_tail_and_continues_past_bad_arrival(monkeypatch):
    board,demand,root,pickup=fixture();before=field._field_snapshot_inventory(board)
    # Force the genuine native maze validator boundary rather than passing a
    # fake successful menu. Geometry/contact/craft receivers remain real.
    monkeypatch.setattr(route.fr,'_canonical_45_xy_paths',lambda *a:[])
    monkeypatch.setattr(route.fr,'_offset_manhattan_xy_paths',lambda *a:[])
    observed=[]
    def search(b,start,end,width,layer,gap,net,edge_guard,**kw):
        a,z=tuple(start),tuple(end)
        path=[a,(16000000,a[1]),(16000000,z[1]+2000000),
            (z[0]+1000000,z[1]+2000000),(z[0]+1000000,z[1]+1000000),z]
        bad=[(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*q))for p,q in zip(path,path[1:])]
        assert kw['path_validator'](bad)is False
        good=[(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z))]
        assert kw['path_validator'](good)is True
        observed.append(True);return good
    monkeypatch.setattr(route.fr,'_guarded_profiled_lastmile_legs',search)
    menu=route.menus(board,demand,width_nm=200000,timeout_s=5.,max_choices=1)
    assert observed and menu['ops'],menu
    assert menu['complete_path_craft']['refusals']>=1
    assert menu['complete_path_craft']['fixed_pickup_tail_included']
    assert field._field_snapshot_inventory(board)==before
