import numpy as np
import pytest
from shapely.geometry import Polygon,box
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_power_body as bodies
import cec_slab_pour as slab
import cec_pour_plan as exact


class Grid(slab.Grid):
    def __init__(self):
        self.x0=self.y0=0.;self.cell=.25;self.nx=self.ny=120
        self.x1=self.y1=30.


def fixture(back=False,own=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for name in ('rail','other'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('BULK');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetSize(pcbnew.VECTOR2I_MM(1,1))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
    pad.SetLayerSet(layers);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetPosition(pcbnew.VECTOR2I_MM(8,10));pad.SetNetCode(board.GetNetcodeFromNetname('rail' if own else 'other'));fp.Add(pad)
    for a,b in [((6,6),(14,6)),((14,6),(14,14)),((14,14),(6,14)),((6,14),(6,6))]:
        edge=pcbnew.PCB_SHAPE(fp);edge.SetLayer(pcbnew.F_CrtYd);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));edge.SetWidth(pcbnew.FromMM(.05));fp.Add(edge)
    if back:fp.Flip(pcbnew.VECTOR2I_MM(10,10),False)
    return board


@pytest.mark.parametrize('back',[False,True])
def test_exact_raster_and_vector_body_reservations_match(back):
    board=fixture(back);net=board.GetNetcodeFromNetname('rail')
    layer='B.Cu' if back else 'F.Cu';opposite='F.Cu' if back else 'B.Cu'
    expected=bodies.foreign_regions(board,net,layer=layer,margin_mm=.2)
    assert len(expected)==1
    records=exact._geo_obstacle_records(board,net,(layer,opposite,'In2.Cu'),.2,0.)
    body_records=[r for r in records[layer] if r['kind']=='footprint_body']
    assert len(body_records)==1 and body_records[0]['geometry'].equals(box(*expected[0]['box']))
    for name in (layer,opposite,'In2.Cu'):
        foreign,_=slab.rasterize(board,net,board.GetLayerID(name),Grid(),.2)
        assert bool(foreign[40,40])==(name==layer)
    rows=[dict(net='rail',layer=name,polygon=[[4,4],[16,4],[16,16],[4,16]])
          for name in (layer,opposite,'In2.Cu')]
    clipped,count=slab._clip_pours_around_foreign_copper(board,rows,clearance_mm=.2)
    assert count==1
    for row in clipped:
        shape=Polygon(row['polygon'],row.get('holes') or ())
        if row['layer']==layer:assert shape.intersection(box(*expected[0]['box'])).area<1e-8
        else:assert shape.area==144


def test_same_net_body_exemption_is_retained():
    board=fixture(own=True);net=board.GetNetcodeFromNetname('rail')
    assert bodies.foreign_regions(board,net)==[]
    foreign,_=slab.rasterize(board,net,pcbnew.F_Cu,Grid(),.2)
    assert not foreign[40,40]


@pytest.mark.parametrize('back', [False, True])
def test_field_land_collar_uses_only_the_actual_transition_faces(back):
    board = fixture(back)
    net = board.GetNetcodeFromNetname('rail')
    regions = bodies.foreign_regions(board, net, margin_mm=.3)
    face = 'B.Cu' if back else 'F.Cu'
    other = 'F.Cu' if back else 'B.Cu'
    x0, y0, x1, y1 = regions[0]['box']
    y = (y0 + y1) / 2
    assert not bodies.landing_clear(regions, x1 + .49, y, (face, 'In2.Cu'), radius_mm=.5)
    assert bodies.landing_clear(regions, x1 + .51, y, (face, 'In2.Cu'), radius_mm=.5)
    assert bodies.landing_clear(regions, (x0+x1)/2, y, (other, 'In2.Cu'), radius_mm=.5)
    own = bodies.foreign_regions(fixture(back, own=True), net, margin_mm=.3)
    assert bodies.landing_clear(own, (x0+x1)/2, y, (face, 'In2.Cu'), radius_mm=.5)


@pytest.mark.parametrize('offset', [0, 17])
def test_realizer_applies_landing_policy_to_reseated_field_members(offset):
    grid = Grid()
    grid.x0 += offset
    field = (70, 70, 'F.Cu', 'In2.Cu', 1, 0)
    threshold = grid.x0 + (70.5 * grid.cell)
    details = []
    _, points, _ = slab.realize_overunder_rects(
        [], [field], {'F.Cu': 1.2, 'In2.Cu': 1.2}, grid,
        bridge_via_count=3, strict_bridges=True, via_details_out=details,
        landing_allow=lambda x, y, layers: x > threshold + .1)
    assert len(points) == len(details) == 3
    assert all(x > threshold + .1 for x, _ in points)
    assert all(row['from_layer'] == 'F.Cu' and row['to_layer'] == 'In2.Cu' for row in details)
