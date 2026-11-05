"""Declared positive native polygons are not one concatenated ring.

Repeated edges across intact positive source polygons grant no permission to
ignore actual copper, repair a malformed component, move a source boundary,
change an obstacle clearance or claim current capacity.
"""
import time
import pcbnew
import pytest

import cec_rectilinear_copper as owner
import cec_native_fill_geometry as native
from test_native_hole_bridge_decode import holed
from test_lastmile import _board


def at(point, quarter=0, mirror=False):
    x,y=point
    if mirror:x=-x
    for _ in range(quarter):x,y=-y,x
    return [round((x+30)*1e6),round((y+30)*1e6)]


def compound(quarter=0,mirror=False,kind='duplicate'):
    shape=holed(angle=90*quarter,mirror=mirror);shape.Fracture(False)
    if kind=='duplicate':shape.Append(shape.CloneDropTriangulation())
    else:
        # Share a literal outer edge, but retain two independently declared
        # positive source polygons rather than pretending they are one ring.
        shape.Append(owner._poly([at(p,quarter,mirror) for p in ((0,0),(10,0),(10,5),(0,5))]))
    return shape


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
@pytest.mark.parametrize('kind',('duplicate','overlap'))
def test_compound_identity_keeps_all_original_positive_polygons(quarter,mirror,kind):
    shape=compound(quarter,mirror,kind);before=shape.Format()
    # The old compound decoder conflates across-polygon and within-ring edges.
    with pytest.raises(owner.Refused):
        native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    result=owner._validated_native_fill_identity(shape,time.monotonic()+2.)
    assert result==native.identity(shape,time.monotonic()+2.)
    assert shape.Format()==before and shape.OutlineCount()==2
    with pytest.raises(owner.Refused,match='unsupported_supporting_native_ring'):
        owner._shape_identity(shape,time.monotonic()+2.)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
def test_positive_island_inside_peer_hole_remains_real_foreign_copper(tmp_path,quarter,mirror):
    board=_board([(1,1,'SUPPLY'),(2,1,'FOREIGN')],edge=(-20,-20,80,80))
    zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.F_Cu);zone.SetNet(board.FindNet('FOREIGN'))
    zone.Outline().Append(owner._poly([at(p,quarter,mirror) for p in ((0,0),(10,0),(10,10),(0,10))]))
    shape=compound(quarter,mirror)
    shape.Append(owner._poly([at(p,quarter,mirror) for p in ((1.4,1.4),(2.6,1.4),(2.6,2.6),(1.4,2.6))]))
    zone.SetFilledPolysList(pcbnew.F_Cu,shape);zone.SetIsFilled(True);board.Add(zone)
    # Use a native save/load boundary, not only an in-memory fake obstacle.
    source=tmp_path/'compound.kicad_pcb';pcbnew.SaveBoard(str(source),board,True)
    saved=source.read_bytes();board=pcbnew.LoadBoard(str(source))
    zone=next(z for z in board.Zones() if z.GetNetname()=='FOREIGN');before=zone.GetFilledPolysList(pcbnew.F_Cu).Format()
    clear=owner._poly([at(p,quarter,mirror) for p in ((6.5,6.5),(7.5,6.5),(7.5,7.5),(6.5,7.5))])
    owner._require_unoccupied_outline(board,clear,'SUPPLY',pcbnew.F_Cu,time.monotonic()+2.,clearance_nm=200000)
    occupied=owner._poly([at(p,quarter,mirror) for p in ((1.75,1.75),(2.25,1.75),(2.25,2.25),(1.75,2.25))])
    with pytest.raises(owner.Refused,match='foreign_native_zone_inside_proposed'):
        owner._require_unoccupied_outline(board,occupied,'SUPPLY',pcbnew.F_Cu,time.monotonic()+2.,clearance_nm=200000)
    with pytest.raises(owner.Refused,match='foreign_native_zone_inside_proposed'):
        owner._require_unoccupied_outline(board,clear,'SUPPLY',pcbnew.F_Cu,time.monotonic()+2.,clearance_nm=600000)
    assert zone.GetFilledPolysList(pcbnew.F_Cu).Format()==before and source.read_bytes()==saved


@pytest.mark.parametrize('fault',('dangling_fold','zero_edge','one_nm_copy','arc_report'))
def test_valid_peer_polygon_cannot_hide_malformed_native_component(monkeypatch,fault):
    shape=compound()
    if fault=='dangling_fold':
        shape.Append(owner._poly(((0,0),(10,0),(10,10),(5,10),(5,5),(5,10),(0,10))))
    elif fault=='zero_edge':
        bad=owner._poly(((0,0),(10,0),(10,10),(0,10)))
        bad.Outline(0).SetPoint(1,pcbnew.VECTOR2I(0,0));shape.Append(bad)
    elif fault=='one_nm_copy':
        original=pcbnew.SHAPE_POLY_SET.AddOutline
        def moved(self,chain):
            result=original(self,chain);p=self.Outline(0).CPoint(0)
            self.Outline(0).SetPoint(0,pcbnew.VECTOR2I(p.x+1,p.y));return result
        monkeypatch.setattr(pcbnew.SHAPE_POLY_SET,'AddOutline',moved)
    else:
        # Inject an unsupported native API response; this is a guard unit
        # test, not a claim that an arc-bearing source was manufactured.
        monkeypatch.setattr(pcbnew.SHAPE_LINE_CHAIN,'ArcCount',lambda self:1)
    before=shape.Format()
    with pytest.raises(owner.Refused):
        owner._validated_native_fill_identity(shape,time.monotonic()+2.)
    assert shape.Format()==before


@pytest.mark.parametrize('fault',('deadline','vertices','polygons'))
def test_compound_budget_never_skips_a_component(fault):
    shape=compound()
    if fault=='polygons':
        seed=owner._poly(((0,0),(10,0),(10,10),(0,10)))
        for _ in range(255):shape.Append(seed)
    before=shape.Format()
    with pytest.raises(owner.Refused):
        owner._validated_native_fill_identity(shape,time.monotonic()+(-1 if fault=='deadline' else 2.),
            max_vertices=32 if fault=='vertices' else 200000)
    assert shape.Format()==before


@pytest.mark.parametrize('flag',('zero_native_loss','zero_native_spill','exact_native_directed_edges_preserved'))
def test_each_component_requires_every_exact_decoder_proof(monkeypatch,flag):
    shape=compound();before=shape.Format();original=native.decode_exact_hole_boundaries;calls=[]
    def incomplete(*a,**kwargs):
        decoded,proof=original(*a,**kwargs);calls.append(True)
        if len(calls)==2:proof[flag]=False
        return decoded,proof
    monkeypatch.setattr(native,'decode_exact_hole_boundaries',incomplete)
    with pytest.raises(owner.Refused,match='native_fill_bridge_topology_or_set_change'):
        owner._validated_native_fill_identity(shape,time.monotonic()+2.)
    assert len(calls)==2 and shape.Format()==before


@pytest.mark.parametrize('layer',(pcbnew.F_Cu,pcbnew.B_Cu))
def test_support_receipt_binds_literal_complete_compound_fill(layer):
    board=_board([(1,1,'FOREIGN')]);zone=pcbnew.ZONE(board)
    zone.SetNet(board.FindNet('FOREIGN'));zone.SetLayer(layer)
    zone.Outline().Append(owner._poly(((30000000,30000000),(40000000,30000000),(40000000,40000000),(30000000,40000000))))
    shape=compound();zone.SetFilledPolysList(layer,shape);zone.SetIsFilled(True);board.Add(zone)
    row=owner._support_row(zone,layer,time.monotonic()+2.)
    proposal=dict(net='FOREIGN',layer_id=layer,supporting_zones=[row])
    assert owner._receive_support(board,proposal,time.monotonic()+2.)[0]==[zone]
    changed=shape.CloneDropTriangulation();p=changed.Outline(1).CPoint(0)
    changed.Outline(1).SetPoint(0,pcbnew.VECTOR2I(p.x+1,p.y));zone.SetFilledPolysList(layer,changed)
    with pytest.raises(owner.Refused):owner._receive_support(board,proposal,time.monotonic()+2.)
