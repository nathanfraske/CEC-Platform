import pytest
from shapely.geometry import Polygon,box
from cec_assembly_access import screen


@pytest.mark.parametrize('shift',[(0,0),(37,-19)])
def test_current_cover_growth_is_caught_despite_unchanged_mating_datums(shift):
    x,y=shift
    carrier=[(8+x,2+y),(2+x,2+y),(2+x,8+y)]
    cover=[(2,2),(8,2),(8,8)]
    port={'ref':'PORT','edge':'bottom','clearance_mm':1.,
          'courtyard_xyxy':[3+x,12+y,7+x,14+y]}
    short=screen(carrier,cover,box(0,0,10,10),[port],mirror_x=True)
    tall=screen(carrier,cover,box(0,0,10,13),[port],mirror_x=True)
    assert short['ok'] and short['ports'][0]['gap_mm']==2
    assert not tall['ok'] and tall['ports'][0]['gap_mm']==-1
    assert not short['release_accepted']


@pytest.mark.parametrize('edge,envelope',[
    ('top',[3,-3,7,-1]),('bottom',[3,11,7,13]),
    ('left',[-3,3,-1,7]),('right',[11,3,13,7])])
def test_all_declared_edges_honor_clearance_boundary(edge,envelope):
    points=[(2,2),(8,2),(2,8)]
    row={'ref':'EDGE','edge':edge,'clearance_mm':1.,'courtyard_xyxy':envelope}
    assert screen(points,points,box(0,0,10,10),[row])['ok']
    assert not screen(points,points,box(0,0,10,10),[{**row,'clearance_mm':1.01}])['ok']


def test_misaligned_datums_are_not_averaged_into_a_pass():
    result=screen([(1,1),(8,2),(2,8)],[(2,2),(8,2),(2,8)],box(0,0,10,10),[])
    assert not result['ok'] and result['reason']=='mating_datums_disagree'


def test_actual_contour_not_an_unrelated_bounding_rectangle():
    points=[(2,2),(8,2),(2,8)]
    cover=Polygon([(0,0),(10,0),(10,10),(7,10),(7,5),(0,5)])
    port={'ref':'RECESS','edge':'bottom','clearance_mm':.5,'courtyard_xyxy':[1,6,5,8]}
    assert screen(points,points,cover,[port])['ok']


@pytest.mark.parametrize('points',[[(0,0),(1,1)],[(0,0),(1,1),(2,2)]])
def test_underconstrained_datums_refused(points):
    with pytest.raises(ValueError): screen(points,points,box(0,0,10,10),[])


@pytest.mark.parametrize('clearance',[-1,float('nan'),float('inf')])
def test_invalid_clearance_refused(clearance):
    points=[(2,2),(8,2),(2,8)]
    with pytest.raises(ValueError):
        screen(points,points,box(0,0,10,10),[{
            'ref':'P','edge':'top','clearance_mm':clearance,'courtyard_xyxy':[1,-3,3,-1]}])
