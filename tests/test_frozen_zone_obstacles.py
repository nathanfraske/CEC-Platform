"""Native local-clearance DSN obstacles preserve holes, layers and source."""
import math
from pathlib import Path

import pcbnew
import pytest

import cec_field_coupling as field
import cec_fr as fr
import cec_frozen_zone_obstacles as obstacles
import cec_copper_echo as sexpr
from test_lastmile import _board


def fixture(tmp_path,rotation=0,prefix='/renamed/',*,layers=(pcbnew.F_Cu,)):
    def rotate(point):
        a=math.radians(rotation);x,y=point[0]-15,point[1]-15
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    net=prefix+'BUS';b=_board([(*rotate((6,6)),net),(25,25,'/CONTROL')],edge=(0,0,30,30))
    if pcbnew.B_Cu in layers:
        pad=next(p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()==net)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    zone=pcbnew.ZONE(b);ls=pcbnew.LSET()
    for layer in layers:ls.AddLayer(layer)
    zone.SetLayerSet(ls);zone.SetNetCode(b.GetNetcodeFromNetname(net))
    zone.SetLocalClearance(pcbnew.FromMM(.5));zone.SetMinThickness(pcbnew.FromMM(.1))
    outline=zone.Outline();oi=outline.NewOutline()
    for point in ((5,5),(15,5),(15,15),(5,15)):outline.Append(pcbnew.VECTOR2I_MM(*rotate(point)))
    hole=outline.NewHole(oi)
    for point in ((8,8),(12,8),(12,12),(8,12)):outline.Append(pcbnew.VECTOR2I_MM(*rotate(point)),oi,hole)
    b.Add(zone);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/'board.kicad_pcb';field._save_field_snapshot(b,path)
    return path,net,rotate


def reconstruct(row):
    shape=pcbnew.SHAPE_POLY_SET();oi=shape.NewOutline()
    for p in row['polygon']:shape.Append(pcbnew.VECTOR2I_MM(*p))
    for points in row['holes']:
        hi=shape.NewHole(oi)
        for p in points:shape.Append(pcbnew.VECTOR2I_MM(*p),oi,hi)
    return shape


@pytest.mark.parametrize('rotation,prefix',[(0,'/a/'),(90,'/partition/x/'),(180,'/different/'),(270,'/last/')])
def test_renamed_rotated_native_halo_keeps_real_holes_and_covers_clearance(tmp_path,rotation,prefix):
    path,net,rotate=fixture(tmp_path,rotation,prefix);before=path.read_bytes()
    report=obstacles.compile(path,routed_nets={'/CONTROL'})
    assert report['sources'][0]['net']==net and report['sources'][0]['clearance_nm']==500000
    assert report['board_mutated'] is False and report['release_authority'] is False
    assert path.read_bytes()==before
    rows=report['keepouts'];assert rows and rows[0]['holes']
    shapes=[reconstruct(row) for row in rows]
    inside=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I_MM(*rotate((10,10))),pcbnew.VECTOR2I_MM(*rotate((10,10))),1)
    assert not any(shape.Collide(inside,0) for shape in shapes)
    b=pcbnew.LoadBoard(str(path));native=next(iter(b.Zones())).GetFilledPolysList(pcbnew.F_Cu)
    for point in ((15.4,10),(15.30,15.30),(8.35,10),(5.1,6.0)):
        pos=pcbnew.VECTOR2I_MM(*rotate(point));probe=pcbnew.SHAPE_SEGMENT(pos,pos,1)
        if native.Collide(probe,500000):assert any(shape.Collide(probe,0) for shape in shapes)
    far=pcbnew.VECTOR2I_MM(*rotate((15.8,10)))
    assert not any(shape.Collide(pcbnew.SHAPE_SEGMENT(far,far,1),0) for shape in shapes)


def test_actual_layer_names_are_kept_without_through_layer_bounding_boxes(tmp_path):
    path,net,_=fixture(tmp_path,layers=(pcbnew.F_Cu,pcbnew.B_Cu))
    b=pcbnew.LoadBoard(str(path));b.SetLayerName(pcbnew.B_Cu,'BACK_SIGNAL');field._save_field_snapshot(b,path)
    report=obstacles.compile(path,routed_nets={'/CONTROL'})
    assert {r['layers'] for r in report['keepouts']}=={('F.Cu',),('BACK_SIGNAL',)}
    assert all(not r['allow_tracks'] and not r['allow_vias'] and not r['block_fills'] for r in report['keepouts'])


@pytest.mark.parametrize('kind',['own','refill','excluded'])
def test_explicit_owner_and_refill_scope_do_not_create_foreign_obstacles(tmp_path,kind):
    path,net,_=fixture(tmp_path)
    args=dict(routed_nets={net} if kind=='own' else {'/CONTROL'},
        refillable_nets={net} if kind=='refill' else (),only_nets=set() if kind=='excluded' else None)
    assert obstacles.compile(path,**args)['keepouts']==[]


def test_unknown_fill_is_not_an_empty_channel(tmp_path):
    path,net,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(path))
    next(iter(b.Zones())).UnFill();field._save_field_snapshot(b,path)
    with pytest.raises(ValueError,match='no_native_fill'):obstacles.compile(path,routed_nets={'/CONTROL'})


@pytest.mark.parametrize('bounds',[{'timeout_s':0},{'timeout_s':float('nan')},{'max_vertices':1}])
def test_invalid_bounds_refuse_before_loading(tmp_path,bounds):
    with pytest.raises(ValueError):obstacles.compile(tmp_path/'absent.kicad_pcb',routed_nets={'/CONTROL'},**bounds)


def test_disposable_dsn_export_includes_guard_and_windows_without_parent_edits(tmp_path):
    path,net,_=fixture(tmp_path);before=path.read_bytes()
    rows=fr.frozen_zone_keepouts(path,routed_nets={'/CONTROL'})
    candidate=tmp_path/'export.kicad_pcb';fr.bake_hints(str(path),str(candidate),keepouts=rows)
    dsn=tmp_path/'route.dsn';fr.export_dsn(str(candidate),str(dsn),plane_to_power=False)
    # KiCad exports rule-area names as an empty DSN name. Prove the actual
    # geometry/layer/window transfer, not a name that the backend never sees.
    text=dsn.read_text().replace('(string_quote ")','(string_quote Q)')
    root=sexpr._parse(sexpr._TOKEN.findall(text))
    structure=next(r for r in root if isinstance(r,list) and r[0]=='structure')
    guards=[r for r in structure if isinstance(r,list) and r[0]=='keepout']
    assert len(guards)==len(rows)
    for row,guard in zip(rows,guards):
        polygon=guard[2];assert polygon[:3]==['polygon',row['layers'][0],'0']
        points=list(zip(map(float,polygon[3::2]),map(float,polygon[4::2])))
        assert points[-1]==points[0]
        assert len(points)-1==len(row['polygon'])
        for point,expected in zip(points,row['polygon']):
            assert point==pytest.approx((expected[0]*1000,-expected[1]*1000),abs=1.)
        windows=[w for w in guard[3:] if w[0]=='window']
        assert len(windows)==len(row['holes'])
        for window,hole in zip(windows,row['holes']):
            assert window[1][:3]==['polygon',row['layers'][0],'0']
            values=window[1][3:]
            points=list(zip(map(float,values[::2]),map(float,values[1::2])))
            assert points[-1]==points[0] and len(points)-1==len(hole)
            for point,expected in zip(points,hole):
                assert point==pytest.approx((expected[0]*1000,-expected[1]*1000),abs=1.)
    assert path.read_bytes()==before
