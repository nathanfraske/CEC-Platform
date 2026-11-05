"""Ordinary guarded escapes beyond a blocked package-local barrel domain."""
import math
import time

import pcbnew
import pytest

import cec_escape_frontier as frontier
import cec_fr as fr


def test_annulus_is_bounded_deterministic_and_not_a_finer_disk():
    points = frontier.annular_offsets_mm()
    assert points == frontier.annular_offsets_mm()
    assert 0 < len(points) < 1024 and len(set(points)) == len(points)
    assert all(4 < math.hypot(x, y) <= 8 and x*2 == int(x*2) and y*2 == int(y*2)
               for x, y in points)
    assert set(points) == {(-y, x) for x, y in points}
    assert not frontier.annular_offsets_mm(4.)


@pytest.mark.parametrize('kwargs', [dict(radius_mm=8.1), dict(radius_mm=float('nan')),
    dict(inner_mm=2.), dict(step_mm=.25), dict(step_mm=float('inf'))])
def test_unbounded_domains_are_rejected(kwargs):
    with pytest.raises(ValueError):
        frontier.annular_offsets_mm(**kwargs)


def test_sector_budget_cannot_be_consumed_by_one_near_cluster():
    points = [(x, 0) for x in range(5, 40)] + [(0, 70), (-70, 0), (0, -70)]
    chosen = frontier.sector_frontier(points, (0, 0), limit=4)
    assert set(chosen) == {(5, 0), (0, 70), (-70, 0), (0, -70)}
    assert chosen == frontier.sector_frontier(list(reversed(points)), (0, 0), limit=4)
    shifted = [(x+317, y-121) for x, y in points]
    assert [(x+317,y-121) for x,y in chosen] == frontier.sector_frontier(
        shifted, (317,-121), limit=4)
    assert len(frontier.sector_frontier(points*2,(0,0),limit=64)) == len(points)


@pytest.mark.parametrize('points,origin,limit', [([(0,0)]*1025,(0,0),1),
    ([(float('nan'),0)],(0,0),1), ([(0,0)],(0,0),0), ([(0,0)],(0,0),65)])
def test_frontier_rejects_unbounded_or_nonfinite_input(points,origin,limit):
    with pytest.raises(ValueError):
        frontier.sector_frontier(points,origin,limit=limit)


def native_fixture(*, quarter=0, back=False, obstruction=True):
    from test_local_bridge_dogbones import fixture
    board, pad, nc, layer = fixture(quarter=quarter, back=back, profile=False, size=.6)
    pad.GetParentFootprint().SetReference('Unrelated_Name_97')
    origin = pad.GetPosition()
    def transformed(x,y):
        for _ in range(quarter):
            x,y=-y,x
        return origin+pcbnew.VECTOR2I_MM(x,y)
    if obstruction:
        track=pcbnew.PCB_TRACK(board);track.SetNet(board.FindNet('/OTHER'))
        track.SetStart(transformed(-2,0));track.SetEnd(transformed(2,0))
        track.SetWidth(pcbnew.FromMM(8));track.SetLayer(pcbnew.In2_Cu)
        track.SetLocked(True);board.Add(track)
    via=pcbnew.PCB_VIA(board);via.SetNetCode(nc)
    via.SetPosition(transformed(10,0));via.SetWidth(pcbnew.FromMM(.6))
    via.SetDrill(pcbnew.FromMM(.3));via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLocked(True);board.Add(via)
    return board,pad,nc,layer,via


def run_native(board,pad,nc,layer,via,**kwargs):
    details={}
    ops=fr._lastmile_bridge(board,tuple(pad.GetPosition()),{layer},
        tuple(via.GetPosition()),{layer,pcbnew.In3_Cu},200000,nc,[pcbnew.In3_Cu],200000,
        seat_limit=1,leg_ok=lambda *a:True,diagnostics=details,
        deadline_monotonic=time.monotonic()+10,**kwargs)
    return ops,details


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_inner_bus_needs_far_ordinary_barrel_without_moving_copper(quarter,back):
    board,pad,nc,layer,via=native_fixture(quarter=quarter,back=back)
    original=[(t.m_Uuid.AsString(),t.IsLocked()) for t in board.GetTracks()]
    blocked,control=run_native(board,pad,nc,layer,via,max_seat_radius_mm=4)
    assert blocked is None and all(not e['seats'] for e in control['endpoints'] if e['endpoint']=='a')
    ops,details=run_native(board,pad,nc,layer,via)
    assert ops
    barrel=next(op for op in ops if op[0]=='via')
    delta=barrel[1]-pad.GetPosition()
    assert 4e6 < math.hypot(delta.x,delta.y) <= 8e6
    assert barrel[2]>=.3 and barrel[3]>=.6  # ordinary, not a remote POFV exception
    for op in ops:
        if op[0]!='trk':continue
        _,a,b,w,lay=op
        assert w==200000
        assert not (a.x-b.x) or not (a.y-b.y) or abs(a.x-b.x)==abs(a.y-b.y)
        assert fr._tap_foreign_clear(board,a,b,w,lay,200000,{nc})
    assert [(t.m_Uuid.AsString(),t.IsLocked()) for t in board.GetTracks()]==original
    assert pad.GetPosition()==pcbnew.VECTOR2I_MM(30,40)
    assert details['endpoints'][0]['counters']['expanded_radius_nm']==8000000
    assert not details['no_path_proof'] and not details['release_authority']


def test_local_success_does_not_run_exceptional_domain():
    board,pad,nc,layer,via=native_fixture(obstruction=False)
    ops,details=run_native(board,pad,nc,layer,via)
    assert ops and all('expanded_radius_nm' not in e['counters'] for e in details['endpoints'])


@pytest.mark.parametrize('kwargs',[dict(allow_lattice=False),dict(allow_maze=False),
    dict(max_length_nm=3000000),dict(max_seat_radius_mm=4.)])
def test_extension_cannot_override_search_or_length_contract(kwargs):
    board,pad,nc,layer,via=native_fixture()
    ops,_=run_native(board,pad,nc,layer,via,**kwargs)
    assert ops is None and len(list(board.GetTracks()))==2


def test_future_power_reservation_still_excludes_expanded_barrels(monkeypatch):
    board,pad,nc,layer,via=native_fixture()
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[dict(
        net='/OTHER',layer='In3.Cu',x0=21,y0=31,x1=39,y1=49)])
    ops,details=run_native(board,pad,nc,layer,via)
    assert ops is None
    endpoint=next(e for e in details['endpoints'] if e['endpoint']=='a')
    assert endpoint['counters']['expanded_canonical_position_trials']<=1024
    assert endpoint['via_refusal_causes']['expanded_canonical'][
        'foreign pour-first reservation excludes via land']['count']>0
    assert len(list(board.GetTracks()))==2


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('endpoint',['a','both'])
def test_legal_local_seat_does_not_starve_explicit_secondary_portfolio(quarter,back,endpoint):
    board,pad,nc,layer,via=native_fixture(quarter=quarter,back=back,obstruction=False)
    original=[(t.m_Uuid.AsString(),t.GetNetname(),tuple(t.GetStart()),tuple(t.GetEnd())) for t in board.GetTracks()]
    # A complete-route predicate can reject a perfectly legal local seat.
    # Its existence must not turn the distinct secondary domain into a repeat
    # of the failed local portfolio. No native guard is mocked here.
    def complete(ops):
        return all(math.dist(tuple(o[1]),tuple(pad.GetPosition()))>4000000
                   for o in ops if o[0]=='via')
    blocked,control=run_native(board,pad,nc,layer,via,ops_ok=complete)
    assert blocked is None and any(e['seats'] for e in control['endpoints'])
    ops,details=run_native(board,pad,nc,layer,via,ops_ok=complete,ordinary_annulus_only=True,
                          ordinary_annulus_endpoint=endpoint)
    assert ops and complete(ops) and details['ordinary_annulus_only']
    assert all(o[2]>=.3 and o[3]>=.6 for o in ops if o[0]=='via')
    for o in ops:
        if o[0]=='trk':assert fr._tap_foreign_clear(board,o[1],o[2],o[3],o[4],200000,{nc})
    assert [(t.m_Uuid.AsString(),t.GetNetname(),tuple(t.GetStart()),tuple(t.GetEnd())) for t in board.GetTracks()]==original
    assert not details['no_path_proof'] and not details['release_authority']


@pytest.mark.parametrize('kwargs',[dict(allow_lattice=False),dict(allow_maze=False),
    dict(max_seat_radius_mm=4.)])
def test_secondary_escape_requires_its_bounded_explicit_domain(kwargs):
    board,pad,nc,layer,via=native_fixture(obstruction=False)
    with pytest.raises(ValueError,match='bounded_explicit_fallback'):
        run_native(board,pad,nc,layer,via,ordinary_annulus_only=True,**kwargs)


def test_secondary_endpoint_choice_cannot_replace_the_other_local_portfolio():
    board,pad,nc,layer,via=native_fixture(obstruction=False)
    def complete(ops):return all(math.dist(tuple(o[1]),tuple(pad.GetPosition()))>4000000 for o in ops if o[0]=='via')
    ops,details=run_native(board,pad,nc,layer,via,ops_ok=complete,ordinary_annulus_only=True,
                          ordinary_annulus_endpoint='b')
    assert ops is None and details['ordinary_annulus_endpoint']=='b'
    assert all('expanded_radius_nm' not in e['counters'] for e in details['endpoints'] if e['endpoint']=='a')
