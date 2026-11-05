"""World-fixed Source port corrections belong in the complete search sweep."""
import math
import pytest
from shapely import affinity
from shapely.geometry import Point,box
import cec_native_cell_pose_domains as poses


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_shifted_region_contains_actual_world_fixed_port_for_every_cardinal_pose(quarter,back):
    # A Source barrel rigidly 1.2 mm from the owner is reseated by 0.8 mm.
    # Those are synthetic geometry inputs, not a production process waiver.
    # Opposing rotation can undo the current geometric cancellation.
    shape=Point(-.4,0).buffer(.2)
    shape=affinity.rotate(shape,90*quarter,origin=(0,0))
    offset=[round(800000*math.cos(math.pi*quarter/2)),round(800000*math.sin(math.pi*quarter/2))]
    if back:
        shape=affinity.scale(shape,xfact=-1,origin=(0,0));offset[0]*=-1
    member=dict(geometry=shape,native_world_signal_offset_nm=offset)
    moving={'arbitrary_owner':[member]};centre=(20.,15.);radius=.25
    region=box(*poses._pose_search_bounds(moving,{'arbitrary_owner':(0,0)},
        {'arbitrary_owner':centre},radius))
    for turn in range(0,360,45):
        actual=poses._rotated_member(member,turn,(0,0))['geometry']
        for dx,dy in ((radius,0),(-radius,0),(0,radius),(0,-radius)):
            translated=affinity.translate(actual,centre[0]+dx,centre[1]+dy)
            assert region.covers(translated),(quarter,back,turn,region.bounds,translated.bounds)
