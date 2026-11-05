import copy
import pytest
from shapely.geometry import box,mapping
from cec_assembly_envelope import screen

def board(ref='part',height=5):
    return dict(outline=mapping(box(0,0,20,20)),missing=[],bodies=[dict(
        ref=ref,footprint='test-package',height_max_mm=height,inward=True,
        xy=mapping(box(3,4,7,8)),basis='design_allocation')])

def run(a,b,**kw):
    return screen(a,b,transform=[-1,0,0,1,10,0],gap=[12,12.2],
                  xy_allowance_mm=.1,clearance_mm=.5,**kw)

def test_opposing_collision_and_separation():
    assert run(board(),board())['ok']
    assert not run(board(height=7),board(height=7))['ok']
    assert not run(board(),board())['release_accepted']

def test_missing_part_not_dropped():
    b=board();b['missing']=[dict(ref='unknown')]
    assert not run(board(),b)['ok']

def test_vent_is_extra_space_not_just_body_fit():
    a=board(height=5);a['bodies'][0]['vent_min_mm']=3
    r=run(a,board())
    assert not r['ok'] and r['violations'][0]['kind']=='opposing_bodies'

def test_mate_needs_independent_contact_proof():
    with pytest.raises(ValueError):run(board('a'),board('b'),mating_pairs=[['a','b']])
    assert run(board('a',7),board('b',7),mating_pairs=[['a','b']],contacts_verified=True)['ok']

def test_body_hits_laminate_without_opposing_components():
    empty=board();empty['bodies']=[]
    assert not run(board(height=12),empty)['ok']

def test_flipped_y_axis_not_in_plane_rotation():
    a=board();b=board();b['bodies'][0]['height_max_mm']=9
    assert not run(a,b)['ok']
    assert screen(a,b,transform=[-1,0,0,-1,10,20],gap=[12,12],
        xy_allowance_mm=.1,clearance_mm=.5)['ok']

@pytest.mark.parametrize('value',[-1,float('nan'),float('inf')])
def test_bad_budget(value):
    with pytest.raises(ValueError):screen(board(),board(),transform=[1,0,0,1,0,0],
        gap=[12,12],xy_allowance_mm=value,clearance_mm=.5)

def test_planar_art_is_covered_but_not_a_body():
    a=board();a['bodies'][0].update(height_max_mm=0)
    assert run(a,board())['ok']


@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('lateral,vertical,expected',[(.4,-.5,False),(.6,-.5,True),
    (.3,.3,False),(.4,.4,True)])
def test_near_misses_need_actual_spatial_body_clearance_not_only_disjoint_xy(mirror,angle,lateral,vertical,expected):
    from shapely import affinity
    a=board('a',6);b=board('b',6)
    first=box(3,4,7,8);second=box(7+.2+lateral,4,11+.2+lateral,8)
    def pose(geom):
        if mirror:geom=affinity.scale(geom,xfact=-1,yfact=1,origin=(10,10))
        return affinity.rotate(geom,angle,origin=(10,10))
    a['bodies'][0]['xy']=mapping(pose(first));b['bodies'][0]['xy']=mapping(pose(second))
    a['outline']=b['outline']=mapping(box(-20,-20,40,40))
    r=screen(a,b,transform=[1,0,0,1,0,0],gap=[12+vertical,12.2+vertical],
        xy_allowance_mm=.1,clearance_mm=.5)
    assert r['ok'] is expected
    if not expected:
        hit=next(v for v in r['violations'] if v['kind']=='opposing_body_edge_clearance')
        assert hit['spatial_clearance_mm']<.5 and hit['lateral_free_mm']==pytest.approx(lateral)


@pytest.mark.parametrize('lateral,vertical,expected',[(.4,-.5,False),(.6,-.5,True),(.3,.3,False),(.4,.4,True)])
def test_body_near_opposing_laminate_edge_also_needs_spatial_clearance(lateral,vertical,expected):
    a=board('a',12);b=board('b');b['bodies']=[]
    b['outline']=mapping(box(7+.1+lateral,0,20,20))
    r=screen(a,b,transform=[1,0,0,1,0,0],gap=[12+vertical,12.2+vertical],
        xy_allowance_mm=.1,clearance_mm=.5)
    assert r['ok'] is expected
    if not expected:assert r['violations'][0]['kind']=='body_to_laminate_edge_clearance'
