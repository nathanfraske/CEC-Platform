"""More search effort cannot become geometry, width, or release authority."""
import time
import pcbnew
import pytest
import cec_fr as fr
from test_multilayer_route_graph import board_net


def invoke(board,net,**kw):
    return fr._multilayer_maze_lastmile_ops(board,pcbnew.VECTOR2I_MM(0,0),
        pcbnew.VECTOR2I_MM(8,8),net.GetNetCode(),(pcbnew.F_Cu,pcbnew.B_Cu),200000,
        lambda *a:True,width_for_layer=lambda l:200000,grid_mm=.5,margin_mm=1.,**kw)


def test_explicit_longer_search_keeps_every_native_guard(monkeypatch):
    b,n=board_net();d={};seen=[]
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',lambda *a:(seen.append(a) or False))
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:False)
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    assert invoke(b,n,heuristic_weight=3.,terminal_capture_mm=1.,field_state_dominance=True,
        planar_guard=lambda *a:True,search_wall_cap_s=30.,max_expanded_states=100000,
        deadline_monotonic=time.monotonic()+25.,diagnostics=d) is None
    assert seen and d['hop_refusals']['foreign_copper_or_hole']>0
    assert d['search_wall_cap_s']==30 and d['max_expanded_states']==100000
    assert not d['no_path_proof'] and not d['release_authority'] and not list(b.GetTracks())


@pytest.mark.parametrize('cap,states',[(0,100),(-1,100),(61,100),(float('nan'),100),
    (True,100),(30,None),(30,True),(30,0),(30,1000001)])
def test_larger_effort_requires_finite_explicit_time_and_integer_work(cap,states):
    b,n=board_net()
    with pytest.raises(ValueError):
        invoke(b,n,heuristic_weight=3.,search_wall_cap_s=cap,max_expanded_states=states,
            deadline_monotonic=time.monotonic()+20.)


def test_default_still_refuses_accidentally_long_weighted_work():
    b,n=board_net()
    with pytest.raises(ValueError,match='explicit_short_lease'):
        invoke(b,n,heuristic_weight=3.,deadline_monotonic=time.monotonic()+25.)


def test_state_exhaustion_does_not_claim_a_no_path_proof(monkeypatch):
    b,n=board_net();d={}
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:False)
    monkeypatch.setattr(fr,'_guarded_power_reservations',lambda:[])
    assert invoke(b,n,heuristic_weight=3.,max_expanded_states=1,
        deadline_monotonic=time.monotonic()+2.,diagnostics=d) is None
    assert d['stop']=='explicit_state_budget_exhausted' and d['expanded_states']==1
    assert not d['no_path_proof'] and not d['release_authority']


@pytest.mark.parametrize('deadline',[None,float('nan'),float('inf'),True])
def test_extended_search_requires_wall_deadline_even_when_unweighted(deadline):
    b,n=board_net()
    with pytest.raises(ValueError,match='explicit_wall_and_state_bounds'):
        invoke(b,n,search_wall_cap_s=30.,max_expanded_states=1000,deadline_monotonic=deadline)


def bridge(board, net, **kw):
    return fr._lastmile_bridge(board, (0, 0), [pcbnew.F_Cu],
        (8000000, 8000000), [pcbnew.F_Cu], 200000, net.GetNetCode(),
        [pcbnew.F_Cu, pcbnew.B_Cu], 200000, **kw)


@pytest.mark.parametrize('mode', ['obstacle_channel_axes', 'ordinary_annulus_only'])
def test_bridge_modes_honor_the_same_explicit_work_contract(monkeypatch, mode):
    b, n = board_net(); seen = []
    monkeypatch.setattr(fr, '_snapshot_foreign_clear',
        lambda *a: (seen.append(a) or False))
    monkeypatch.setattr(fr, '_via_spot_clear', lambda *a, **kw: False)
    monkeypatch.setattr(fr, '_guarded_power_reservations', lambda: [])
    before = list(b.GetTracks())
    result = bridge(b, n, **{mode: True}, search_wall_cap_s=30.,
        max_expanded_states=1000, deadline_monotonic=time.monotonic()+25.,
        max_seat_radius_mm=5., allow_lattice=True, allow_maze=True)
    assert result is None and seen and list(b.GetTracks()) == before


@pytest.mark.parametrize('mode', ['obstacle_channel_axes', 'ordinary_annulus_only'])
@pytest.mark.parametrize('cap,states,lease', [(10, None, 25), (30, None, 25),
    (30, 1000, 31), (30, True, 25), (30, 0, 25)])
def test_bridge_mode_cannot_invent_an_unbounded_lease(mode, cap, states, lease):
    b, n = board_net()
    with pytest.raises(ValueError):
        bridge(b, n, **{mode: True}, search_wall_cap_s=cap,
            max_expanded_states=states, deadline_monotonic=time.monotonic()+lease,
            max_seat_radius_mm=5., allow_lattice=True, allow_maze=True)
