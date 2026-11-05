"""Native terminal hooks are part of the path, not a canonical-policy waiver."""
import pytest
import cec_guarded_octilinear_refinement as refinement
import cec_sensitive_scalar_path_reflow as shape


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_complete_off_grid_hook_refinement_keeps_ports_and_removes_ninety_degree_hooks(quarter,mirror):
    def pose(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [10000000+x,10000000+y]
    path=[pose(p) for p in [(0,0),(200000,200000),(200000,400000),(400000,400000),
        (1000000,1000000),(2000100,1000000),(2000100,950000)]]
    original=[p[:] for p in path]
    got=refinement.refine(path,lambda a,z:True)
    assert got['whole_route_canonical'] and got['initial_bad_turns']>=2 and got['remaining_bad_turns']==0
    assert got['points_nm'][0]==path[0] and got['points_nm'][-1]==path[-1]
    shape._points(got['points_nm'])
    assert got['final_length_nm']<=got['initial_length_nm'] and got['source_ports_unchanged']
    assert path==original and not got['partial_route_returned'] and not got['acceptance_or_current_authority_granted']


@pytest.mark.parametrize('value',[False,None,1,'true'])
def test_inconclusive_or_blocked_native_clearance_never_becomes_a_complete_path(value):
    got=refinement.refine([[0,0],[0,200000],[200000,200000]],lambda a,z:value)
    assert not got['whole_route_canonical'] and got['points_nm'] is None
    assert not got['partial_route_returned'] and not got['acceptance_or_current_authority_granted']


def test_no_alternative_corridor_does_not_relabel_an_old_right_angle_as_finished():
    raw=[[0,0],[0,200000],[200000,200000]]
    original={(tuple(a),tuple(z)) for a,z in zip(raw,raw[1:])}
    got=refinement.refine(raw,lambda a,z:(tuple(a),tuple(z)) in original)
    assert got['points_nm'] is None and got['remaining_bad_turns']==1


@pytest.mark.parametrize('options',[dict(max_trials=True),dict(max_trials=0),dict(max_passes=0),dict(timeout_s=float('inf')),
    dict(timeout_s=0),dict(max_points=True),dict(max_points=1)])
def test_work_limits_are_explicit_finite_and_not_geometry_permission(options):
    with pytest.raises(ValueError):
        refinement.refine([[0,0],[100000,100000]],lambda a,z:True,**options)


@pytest.mark.parametrize('raw',[[[0,0],[100000,100001]],[[0,0],[True,1]],[[0,0],[0,0]]])
def test_raw_diagonals_and_bad_coordinates_cannot_be_snapped_silently(raw):
    with pytest.raises(ValueError):
        refinement.refine(raw,lambda a,z:True)


def test_a_tiny_finite_domain_cannot_return_a_partial_uncorrected_hook():
    got=refinement.refine([[0,0],[0,200000],[200000,200000]],lambda a,z:True,max_trials=1,timeout_s=.000001)
    assert got['points_nm'] is None and not got['partial_route_returned']
