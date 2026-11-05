"""Axis motion cannot skew shoulders, tear holes or authorize copper cuts."""
import copy
import pytest
from root_axis_boundary_transport_20261013 import plan,plan_strokes


def shoulder():
    return [dict(outer_nm=[[0,0],[10,0],[10,8],[8,10],[8,20],[2,20],[2,10],[0,8]],holes_nm=[])]


def orient(p,turn,shift=(70,55)):
    x,y=p
    for _ in range(turn//90):x,y=-y,x
    return [x+shift[0],y+shift[1]]


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('shift',[(70,55),(-120,37),(2,-60)])
def test_source_shoulders_move_whole_and_parallel_stems_remain_canonical(turn,shift):
    regions=shoulder()
    regions[0]['outer_nm']=[orient(p,turn,shift) for p in regions[0]['outer_nm']]
    bounds=[orient(p,turn,shift) for p in [(-5,9),(15,25)]]
    box=[min(p[0] for p in bounds),min(p[1] for p in bounds),max(p[0] for p in bounds),max(p[1] for p in bounds)]
    end=orient([0,-2],turn,shift);origin=orient([0,0],turn,shift)
    delta=[end[i]-origin[i] for i in range(2)]
    before=copy.deepcopy(regions)
    result=plan(regions,box,delta,maximum_extension_nm=4)
    assert regions==before
    assert any(r['closure_outside_requested_window'] for r in result['transported_vertices'])
    for ring in [r['outer_nm'] for r in result['regions_nm']]:
        for a,b in zip(ring,ring[1:]+ring[:1]):
            dx,dy=b[0]-a[0],b[1]-a[1]
            assert not dx or not dy or abs(dx)==abs(dy)
    assert not result['current_qualified'] and not result['release_authority']


def test_literal_round_keepout_polygon_moves_rigidly_not_as_a_power_diagonal():
    region=[dict(outer_nm=[[0,0],[30,0],[30,40],[0,40]],
        holes_nm=[[[12,22],[17,21],[19,25],[16,29],[11,27]]])]
    before=copy.deepcopy(region)
    result=plan(region,[-1,24,31,41],[0,-2],maximum_extension_nm=6)
    assert result['regions_nm'][0]['holes_nm'][0]==[[x,y-2] for x,y in before[0]['holes_nm'][0]]
    assert region==before


@pytest.mark.parametrize('fault',['extension','collapse','diagonal_delta','bad_point','noncanonical','no_motion','hole_collision'])
def test_unknown_extent_skew_or_invalid_material_topology_refuses(fault):
    regions=shoulder();box=[-5,9,15,25];delta=[0,-2];extent=4
    if fault=='extension':extent=0
    if fault=='collapse':delta=[0,-8]
    if fault=='diagonal_delta':delta=[1,-2]
    if fault=='bad_point':regions[0]['outer_nm'][0][0]=True
    if fault=='noncanonical':regions[0]['outer_nm'][3]=[7,10]
    if fault=='no_motion':box=[100,100,120,120]
    if fault=='hole_collision':regions[0]['holes_nm']=[[[3,0],[7,0],[7,9],[3,9]]]
    with pytest.raises(ValueError):plan(regions,box,delta,maximum_extension_nm=extent)


@pytest.mark.parametrize('turn',[0,90,180,270])
def test_shared_shoulders_slide_and_parallel_stems_resize_without_false_obstacles(turn):
    nodes=[orient(p,turn) for p in [(6,20),(0,14),(0,0),(6,0)]]
    corners=[orient(p,turn) for p in [(-1,16),(7,25)]]
    window=[min(p[0] for p in corners),min(p[1] for p in corners),
        max(p[0] for p in corners),max(p[1] for p in corners)]
    delta=[b-a for a,b in zip(orient((0,0),turn),orient((0,-2),turn))]
    result=plan_strokes(nodes,[(0,1),(1,2),(2,3)],window,delta,maximum_extension_nm=3)
    assert result['node_offsets_nm']==[delta,delta,[0,0],[0,0]]
    assert not result['current_qualified'] and not result['release_authority']


def test_rigid_actual_barrel_links_move_both_domain_junctions_together():
    result=plan_strokes([[0,20],[6,26],[0,20],[0,0]],[(0,1),(2,3)],
        [-1,24,7,28],[0,-2],rigid_links=[(0,2)],maximum_extension_nm=5)
    assert result['node_offsets_nm']==[[0,-2],[0,-2],[0,-2],[0,0]]


@pytest.mark.parametrize('turn',[0,90,180,270])
def test_explicit_source_body_contact_freezes_its_connected_motion_without_fake_barrel(turn):
    nodes=[orient(p,turn) for p in [(0,0),(0,20),(2,10),(2,24)]]
    corners=[orient(p,turn) for p in [(-1,17),(4,26)]]
    window=[min(p[0] for p in corners),min(p[1] for p in corners),
        max(p[0] for p in corners),max(p[1] for p in corners)]
    delta=[b-a for a,b in zip(orient((0,0),turn),orient((0,-2),turn))]
    before=copy.deepcopy(nodes)
    result=plan_strokes(nodes,[(0,1),(2,3)],window,delta,fixed_nodes=[0],
        source_body_links=[(0,1),(0,2),(0,3)],maximum_extension_nm=24)
    assert nodes==before and result['node_offsets_nm']==[[0,0]]*4
    assert result['refused_components'] and result['source_body_links']==[[0,1],[0,2],[0,3]]
    with pytest.raises(ValueError):plan_strokes(nodes,[(0,1),(2,3)],window,delta,rigid_links=[(0,2)])


@pytest.mark.parametrize('fault',['fixed','extent'])
def test_protected_or_outside_components_refuse_instead_of_skewing(fault):
    result=plan_strokes([[0,0],[6,6],[6,20]],[(0,1),(1,2)],[-1,5,7,25],[0,-2],
        maximum_extension_nm=0 if fault=='extent' else 8,fixed_nodes=[0] if fault=='fixed' else [])
    assert result['node_offsets_nm'][:2]==[[0,0],[0,0]]
    assert result['refused_components']


@pytest.mark.parametrize('fault',['bad_index','false_barrel','noncanonical','collapse'])
def test_unknown_edges_links_and_collapsing_stems_refuse(fault):
    nodes=[[0,0],[0,3],[3,6]];edges=[(0,1),(1,2)];links=[];delta=[0,-1]
    if fault=='bad_index':edges.append((True,2))
    if fault=='false_barrel':links=[(0,2)]
    if fault=='noncanonical':nodes[2]=[4,6]
    if fault=='collapse':delta=[0,-3]
    with pytest.raises(ValueError):plan_strokes(nodes,edges,[-1,2,5,7],delta,rigid_links=links)


def test_explicit_native_serialization_distance_is_not_an_angular_waiver():
    nodes=[[0,0],[1000000,1000025],[1000000,5000000]]
    result=plan_strokes(nodes,[(0,1),(1,2)],[-1,1000001,1000001,6000000],[0,-1000],
        maximum_extension_nm=1100000,canonical_tolerance_nm=25)
    assert result['canonical_tolerance_nm']==25
    with pytest.raises(ValueError):plan_strokes(nodes,[(0,1),(1,2)],[-1,1000001,1000001,6000000],
        [0,-1000],maximum_extension_nm=1100000,canonical_tolerance_nm=24)
    with pytest.raises(ValueError):plan_strokes([[0,0],[100000000,100000030]],[(0,1)],
        [-1,-1,100000001,100000031],[0,-1000],canonical_tolerance_nm=25)


def test_explicit_short_stem_closure_moves_whole_corner_instead_of_reversing_it():
    nodes=[[0,0],[0,3],[3,6]]
    result=plan_strokes(nodes,[(0,1),(1,2)],[-1,2,5,7],[0,-3],close_short_stems=True)
    assert result['closed_short_stem_edges']==[[0,1]]
    assert result['node_offsets_nm']==[[0,-3]]*3
    protected=plan_strokes(nodes,[(0,1),(1,2)],[-1,2,5,7],[0,-3],close_short_stems=True,fixed_nodes=[0])
    assert protected['node_offsets_nm']==[[0,0]]*3
    assert protected['refused_components'][0]['reasons']==['stationary_native_contact']
