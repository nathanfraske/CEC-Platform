"""Real hole-bridge copper is an obstacle with holes, never a solid bbox.

The new identity boundary preserves native source encoding. These tests do
not grant release, current capacity, or authority to alter a source plane.
"""
import time
import math
from pathlib import Path

import pcbnew
import pytest

import cec_rectilinear_copper as owner
import cec_native_fill_geometry as native
import cec_native_capsule_zone_stage as stage
import cec_force_current as force
import cec_field_coupling as field
from test_native_hole_bridge_decode import holed
from test_native_capsule_zone_stage import fixture
from test_lastmile import _board


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
def test_saved_native_bridge_identity_keeps_literal_source_and_strict_authored_ring(quarter,mirror):
    shape=holed(angle=quarter*90,mirror=mirror);shape.Fracture(False);before=shape.Format()
    with pytest.raises(owner.Refused,match='unsupported_supporting_native_ring'):
        owner._shape_identity(shape,time.monotonic()+2.)
    actual=owner._validated_native_fill_identity(shape,time.monotonic()+2.)
    assert actual==native.identity(shape,time.monotonic()+2.)
    assert shape.Format()==before


@pytest.mark.parametrize('points',(
    ((0,0),(10,0),(10,10),(5,10),(5,5),(5,10),(0,10)),
    ((0,0),(10,0),(10,10),(0,10),(10,10),(10,0)),
))
def test_repeated_vertex_is_not_automatically_a_legal_hole(points):
    shape=owner._poly(points);before=shape.Format()
    with pytest.raises(owner.Refused):
        owner._validated_native_fill_identity(shape,time.monotonic()+2.)
    assert shape.Format()==before


def test_actual_native_zero_edge_is_refused_not_simplified():
    shape=owner._poly(((0,0),(10,0),(10,10),(0,10)))
    shape.Outline(0).SetPoint(1,pcbnew.VECTOR2I(0,0));before=shape.Format()
    with pytest.raises(owner.Refused):
        owner._validated_native_fill_identity(shape,time.monotonic()+2.)
    assert shape.Format()==before


@pytest.mark.parametrize('failure',('deadline','vertices','set_loss'))
def test_exhausted_or_inexact_bridge_proof_is_not_a_clean_obstacle(monkeypatch,failure):
    shape=holed();shape.Fracture(False);before=shape.Format()
    if failure=='set_loss':
        original=native.decode_exact_hole_boundaries
        def changed(*a,**k):
            decoded,proof=original(*a,**k);proof['zero_native_loss']=False;return decoded,proof
        monkeypatch.setattr(native,'decode_exact_hole_boundaries',changed)
    with pytest.raises(owner.Refused):
        owner._validated_native_fill_identity(shape,
            time.monotonic()+(-1 if failure=='deadline' else 2),
            max_vertices=3 if failure=='vertices' else 200000)
    assert shape.Format()==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',(False,True))
def test_native_foreign_hole_is_clear_but_its_actual_copper_and_edge_are_not(quarter,mirror):
    def at(x,y):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [round((x+30)*1e6),round((y+30)*1e6)]
    board=_board([(1,1,'SUPPLY'),(2,1,'FOREIGN')],edge=(-20,-20,80,80))
    zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.F_Cu);zone.SetNet(board.FindNet('FOREIGN'))
    outline=owner._poly([at(0,0),at(10,0),at(10,10),at(0,10)])
    zone.Outline().Append(outline);fill=holed(angle=quarter*90,mirror=mirror);fill.Fracture(False)
    zone.SetFilledPolysList(pcbnew.F_Cu,fill);zone.SetIsFilled(True);board.Add(zone)
    before=zone.GetFilledPolysList(pcbnew.F_Cu).Format()
    hole=owner._poly([at(1.5,1.5),at(2.5,1.5),at(2.5,2.5),at(1.5,2.5)])
    owner._require_unoccupied_outline(board,hole,'SUPPLY',pcbnew.F_Cu,time.monotonic()+2.,clearance_nm=200000)
    occupied=owner._poly([at(4,4),at(5,4),at(5,5),at(4,5)])
    with pytest.raises(owner.Refused,match='foreign_native_zone_inside_proposed'):
        owner._require_unoccupied_outline(board,occupied,'SUPPLY',pcbnew.F_Cu,time.monotonic()+2.,clearance_nm=200000)
    with pytest.raises(owner.Refused,match='foreign_native_zone_inside_proposed'):
        owner._require_unoccupied_outline(board,hole,'SUPPLY',pcbnew.F_Cu,time.monotonic()+2.,clearance_nm=600000)
    assert zone.GetFilledPolysList(pcbnew.F_Cu).Format()==before


@pytest.mark.parametrize('minimum',(0,-.1,float('nan'),float('inf'),True,None,'small',101))
def test_invalid_inventory_floor_never_creates_a_family(tmp_path,minimum):
    out=tmp_path/'never-created'
    with pytest.raises(ValueError):
        stage.run(tmp_path/'absent',out,board_hint='synthetic',expected_source_sha256='0'*64,
            reporting_build=tmp_path/'native',min_width_mm=minimum)
    assert not out.exists()


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',(pcbnew.F_Cu,pcbnew.B_Cu))
def test_fine_floor_uses_same_full_native_receivers_not_a_drawing_only_pass(tmp_path,monkeypatch,quarter,layer):
    import os
    native_build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native_build:pytest.skip('uncapped native DRC build not configured')
    board,source,tracks,_,_=fixture(tmp_path,monkeypatch,angle=quarter*90,layer=layer)
    pads=[p.GetPosition() for fp in board.GetFootprints() for p in fp.Pads()]
    for track in tracks:
        track.SetWidth(600000)
        # The original 1 mm fixture used side-overlap contacts .7 mm from
        # its pads. Extend these NEW synthetic .6 mm conductors to the actual
        # terminals rather than starting this test with two known opens.
        for getter,setter in ((track.GetStart,track.SetStart),(track.GetEnd,track.SetEnd)):
            at=getter();closest=min(pads,key=lambda p:math.dist(tuple(at),tuple(p)))
            if math.dist(tuple(at),tuple(closest))<1000000:setter(closest)
    field._save_field_snapshot(board,source);before=source.read_bytes()
    result=stage.run(source,tmp_path/'fine',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native_build),max_changes=1,max_fills=2,retain_source_tracks=True,min_width_mm=.5)
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['contour_inventory_min_width_mm']==.5
    assert result['after_contours']['finding_count']<result['before_contours']['finding_count']
    assert result['independent_whole_source_receiving']['ok'] and source.read_bytes()==before
    assert not result['new_capacity_credited'] and not result['fab_ready']
