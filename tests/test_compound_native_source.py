"""Repeated regional native fill preserves every source record and hole."""
import copy
import time
import pcbnew
import pytest
import cec_native_fill_geometry as native
import cec_regional_fill as regions
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from test_regional_fill import snapshot,regional_plan
from test_native_landing_union import keeper_setup


def test_literal_compound_topology_roundtrip_includes_holes_and_bridge_vertices():
    polygons=[[[[0,0],[20,0],[20,20],[0,20]],[[4,4],[4,6],[6,6],[6,4]]],
              [[[30,30],[40,30],[40,40],[30,40]]]]
    deadline=time.monotonic()+2
    shape=native.reconstruct(polygons,deadline)
    assert shape.OutlineCount()==2 and shape.HoleCount(0)==1
    assert native.snapshot(shape,deadline)==polygons
    rebuilt=native.reconstruct(native.snapshot(shape,deadline),deadline)
    assert native.identity(shape,deadline)==native.identity(rebuilt,deadline)
    assert regions.exact_source_contour_present(rebuilt,shape,deadline)
    lost=rebuilt.CloneDropTriangulation();lost.RemoveOutline(1)
    assert not regions.exact_source_contour_present(lost,shape,deadline)
    changed=copy.deepcopy(polygons);changed[0][1][0][0]+=1
    assert not regions.exact_source_contour_present(native.reconstruct(changed,deadline),shape,deadline)


@pytest.mark.parametrize('fault',['boolean','coordinate','empty','both'])
def test_invalid_compound_source_refuses_without_authority(fault):
    source={'fill_polygons_nm':[[[[0,0],[10,0],[10,10],[0,10]]]]}
    if fault=='boolean':source['fill_polygons_nm'][0][0][0][0]=False
    elif fault=='coordinate':source['fill_polygons_nm'][0][0][0][0]=2_000_000_001
    elif fault=='empty':source['fill_polygons_nm']=[]
    else:source['fill_nm']=[[0,0],[1,0],[0,1]]
    with pytest.raises(owner.Refused):native.source_fill(source,time.monotonic()+2)


def test_native_second_and_third_regional_pass_receive_their_own_output(tmp_path):
    b,t,z,_=keeper_setup();source=snapshot(tmp_path,b)
    t_id=t.m_Uuid.AsString();z_id=z.m_Uuid.AsString()
    for pass_index in range(3):
        before=copper_inventory(source)
        child_path=tmp_path/f'pass-{pass_index}.kicad_pcb'
        pcbnew.SaveBoard(str(child_path),source);child=pcbnew.LoadBoard(str(child_path))
        track=next(t for t in child.GetTracks() if t.m_Uuid.AsString()==t_id)
        zone=next(z for z in child.Zones() if z.m_Uuid.AsString()==z_id)
        p=regional_plan(child,track,zone)
        if pass_index:assert 'fill_polygons_nm' in p['replacement_source_zone']
        e=owner.materialize(child,p);owner.fill(child,p,e['zone_uuid'],regional_source=source)
        pcbnew.SaveBoard(str(child_path),child);saved=pcbnew.LoadBoard(str(child_path))
        result=owner.receive(saved,p,e['zone_uuid'],regional_source=source,timeout_s=10)
        assert result['ok'] and result['complete'],result
        assert copper_inventory(source)==before
        assert not result['new_capacity_credited'] and not result['release_authority']
        source=saved
