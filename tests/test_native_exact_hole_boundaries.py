"""Literal native boundary decoding must neither change copper nor hide faults."""
import time
import pcbnew
import pytest
from shapely.geometry import Polygon
import cec_native_fill_geometry as native
import cec_kelvin_copper_cut as cut
import cec_rectilinear_copper as owner
from test_native_hole_bridge_decode import holed


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_native_saved_bridges_preserve_source_copper_under_all_rigid_frames(angle,mirror):
    shape=holed(angle=angle,mirror=mirror);expected=cut._poly(shape,cut._Work(time.monotonic()+2.))
    shape.Fracture(False);old=shape.Format()
    decoded,proof=native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    assert proof['bridge_count']==2 and proof['zero_native_loss'] and proof['zero_native_spill']
    assert proof['exact_native_directed_edges_preserved'] and not proof['native_unfracture_used']
    assert cut._poly(decoded,cut._Work(time.monotonic()+2.)).equals(expected)
    assert shape.Format()==old and not proof['new_capacity_credited'] and not proof['release_authority']


def test_subdivided_bridge_is_one_topological_bridge_not_two_segments():
    points=[(0,0),(10,0),(10,5),(9,5),(8,5),(8,2),(2,2),(2,8),(8,8),
        (8,5),(9,5),(10,5),(10,10),(0,10)]
    shape=owner._poly(points);old=shape.Format()
    decoded,proof=native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    assert proof['bridge_count']==1 and proof['paired_bridge_segments']==2
    expected=Polygon([(0,0),(10,0),(10,10),(0,10)], [[(2,2),(2,8),(8,8),(8,2)]])
    assert cut._poly(decoded,cut._Work(time.monotonic()+2.)).equals(expected) and shape.Format()==old


def test_exact_decoder_does_not_call_the_edge_mutating_native_unfracture(monkeypatch):
    shape=holed();shape.Fracture(False);old=shape.Format()
    def forbidden(*args):raise AssertionError('Unfracture must not be used')
    monkeypatch.setattr(pcbnew.SHAPE_POLY_SET,'Unfracture',forbidden)
    decoded,proof=native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    assert decoded.HoleCount(0)==2 and shape.Format()==old


@pytest.mark.parametrize('points',[
    [(0,0),(10,0),(10,10),(5,10),(5,5),(5,10),(0,10)],
    [(0,0),(10,0),(10,10),(0,10),(10,10),(10,0)],
    [(0,0),(10,0),(10,0),(10,10),(0,10)],
    [(0,0),(10,10),(0,10),(10,0)],
])
def test_malformed_fold_zero_and_crossing_geometry_is_not_made_valid(points):
    shape=owner._poly(points);old=shape.Format()
    with pytest.raises(owner.Refused):native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    assert shape.Format()==old


def test_independent_zero_loss_checks_cannot_be_skipped(monkeypatch):
    shape=holed();shape.Fracture(False);old=shape.Format()
    def not_empty(self,other,*args):
        # A nonempty native set difference must remain a refusal, even if
        # edge inventories and cycle topology appeared valid earlier.
        self.RemoveAllContours();self.Append(owner._poly([(0,0),(1,0),(1,1),(0,1)]))
    monkeypatch.setattr(pcbnew.SHAPE_POLY_SET,'BooleanSubtract',not_empty)
    with pytest.raises(owner.Refused):native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    assert shape.Format()==old


def test_one_nm_emission_error_is_refused_by_literal_directed_edge_inventory(monkeypatch):
    shape=holed();shape.Fracture(False);old=shape.Format()
    original=pcbnew.SHAPE_POLY_SET.Append
    def displaced(self,*args):
        if len(args)>=2 and type(args[0]) is int:args=(args[0]+1,*args[1:])
        return original(self,*args)
    monkeypatch.setattr(pcbnew.SHAPE_POLY_SET,'Append',displaced)
    with pytest.raises(owner.Refused,match='exact_native_boundary_edges_changed'):
        native.decode_exact_hole_boundaries(shape,time.monotonic()+2.)
    assert shape.Format()==old


def test_budget_exhaustion_never_returns_clean_geometry():
    shape=holed();shape.Fracture(False)
    with pytest.raises(owner.Refused):native.decode_exact_hole_boundaries(shape,time.monotonic()-1.)
    with pytest.raises(owner.Refused):native.decode_exact_hole_boundaries(shape,time.monotonic()+2.,max_vertices=3)
