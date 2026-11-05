"""Legacy contours need exact source geometry, not a generator-name waiver."""
import copy
import pcbnew
import pytest
import cec_owned_contour_refresh as refresh
import cec_native_contour_regions as regions
import cec_rectilinear_copper as owner
from test_owned_contour_refresh import fixture,filled


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_legacy_source_name_follows_same_literal_motion_and_saved_fill(tmp_path,angle,mirror,layer):
    source,child,args=fixture(tmp_path,angle=angle,mirror=mirror,layer=layer)
    for b in (source,child):next(iter(b.Zones())).SetZoneName(owner.ZONE_NAME)
    q=refresh.plan(source,child,**args);refresh.materialize(child,q,source=source);filled(child,q)
    path=tmp_path/'legacy-child.kicad_pcb';pcbnew.SaveBoard(str(path),child)
    received=refresh.receive(pcbnew.LoadBoard(str(path)),q,source=source)
    assert received['ok'] and received['complete'],received
    assert not received['current_qualified'] and not received['release_authority']
    assert next(iter(child.Zones())).GetZoneName()==owner.ZONE_NAME
    assert q['source_zone']['uuid']==args['zone_uuid']


def test_only_exact_redundant_collinear_vertices_are_normalized():
    a=[dict(outer_nm=[[0,0],[100,0],[100,100],[0,100]],holes_nm=[])]
    b=copy.deepcopy(a);b[0]['outer_nm'].insert(1,[20,0])
    assert refresh._same_regions(a,b)
    b[0]['outer_nm'][1][1]=1
    assert not refresh._same_regions(a,b)
    b[0]['outer_nm'][1][1]=-1
    assert not refresh._same_regions(a,b)


@pytest.mark.parametrize('fault',['source_point','source_name','child_name','missing_hole','source_clearance'])
def test_legacy_label_cannot_authorize_even_one_nm_of_unrelated_geometry(tmp_path,fault):
    source,child,args=fixture(tmp_path)
    for b in (source,child):next(iter(b.Zones())).SetZoneName(owner.ZONE_NAME)
    z=next(iter(source.Zones()));c=next(iter(child.Zones()))
    if fault=='source_point':z.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='source_name':z.SetZoneName('unrelated generated slab')
    elif fault=='child_name':c.SetZoneName(regions.ZONE_NAME)
    elif fault=='missing_hole':z.Outline().RemoveAllContours();z.Outline().NewOutline();[z.Outline().Append(*p) for p in ((20000000,20000000),(45000000,20000000),(45000000,45000000),(20000000,45000000))]
    elif fault=='source_clearance':z.SetLocalClearance(z.GetLocalClearance()+1)
    with pytest.raises(owner.Refused):refresh.plan(source,child,**args)


@pytest.mark.parametrize('name',[None,regions.ZONE_NAME,'anything else',True])
def test_native_region_receiver_default_remains_strict_and_unknown_name_is_not_permission(tmp_path,name):
    source,child,args=fixture(tmp_path)
    for b in (source,child):next(iter(b.Zones())).SetZoneName(owner.ZONE_NAME)
    q=refresh.plan(source,child,**args);refresh.materialize(child,q,source=source);filled(child,q)
    p=q['parameters'];native=dict(schema=1,scope=regions.SCOPE,source_tracks=q['candidate_tracks'],
        regions_nm=q['candidate_regions_nm'],actual_fill_regions_nm=q['actual_fill_regions_nm'],supporting_zones=[],
        source_geometry_binding=q['candidate_geometry_binding'],net=q['source_zone']['net'],layer_id=q['source_zone']['layer_id'],
        group_uuid=None,locked=q['source_zone']['locked'],**p,priority=0,source_tracks_retained=True,
        separate_regions_electrically_connected_inferred=False,filled_copper_received=False,new_capacity_credited=False,release_authority=False)
    native['plan_sha256']=owner._digest(native)
    assert not regions.receive(child,native,[args['zone_uuid']],expected_zone_name=name)['ok']
    assert regions.receive(child,native,[args['zone_uuid']],expected_zone_name=owner.ZONE_NAME)['ok']
