"""Physical fill changes cannot hide a Source component split."""
import time
import tempfile
from pathlib import Path
import pcbnew
import pytest
import cec_native_partition_pair as pair
import cec_native_fill_geometry as fill
import cec_force_current as force
from test_native_zone_islands import fixture
from cec_native_items import discard_items


def rect(x0,y0,x1,y1):return [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
SPLIT=[[rect(0,0,4000000,4000000)],[rect(6000000,0,10000000,4000000)]]
SOLID=[[rect(0,0,10000000,4000000)]]


def clone(board):
    import cec_field_coupling as field
    with tempfile.TemporaryDirectory(prefix='cec-paired-synthetic-')as directory:
        path=Path(directory)/'fixture.kicad_pcb'
        field._save_field_snapshot(board,path)
        return pcbnew.LoadBoard(str(path))


def setfill(zone,rings):
    face=zone.GetLayer();shape=fill.reconstruct(rings,time.monotonic()+5.)
    zone.SetFilledPolysList(face,shape);zone.SetIsFilled(True);zone.CacheTriangulation(face)


def board(face=pcbnew.F_Cu,solid=False,first=True):
    b,z=fixture(face=face)
    # A real zone has one authored contour but may have several fill islands.
    z.Outline().RemoveAllContours();z.Outline().Append(fill.reconstruct(SOLID,time.monotonic()+5.))
    z.m_Uuid.Clone(pcbnew.KIID('00000000-0000-4000-8000-000000000001'if first else'ffffffff-ffff-4fff-8fff-ffffffffffff'))
    if solid:setfill(z,SOLID)
    for n,t in enumerate(b.GetTracks()):
        t.m_Uuid.Clone(pcbnew.KIID('11111111-1111-4111-8111-'+str(n+1).zfill(12)))
    return b,z


def bridge(b,z):
    t=pcbnew.PCB_TRACK(b);t.SetLayer(z.GetLayer());t.SetNet(z.GetNet());t.SetWidth(200000)
    t.SetStart(pcbnew.VECTOR2I(500000,500000));t.SetEnd(pcbnew.VECTOR2I(6500000,500000));b.Add(t)
    return t


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('first',[True,False])
def test_uuid_order_never_collapses_two_actual_islands(face,first):
    a,z=board(face,first=first);b=clone(a)
    r=pair.compare(a,b)
    assert r['preserved'] and r['source_component_count']==r['child_component_count']==2
    assert not r['whole_zone_uuid_connectivity_credit'] and not r['current_capacity_qualified']


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_bridge_removal_demotion_is_not_hidden_by_zone_uuid(face):
    a,z=board(face);t=bridge(a,z);b=clone(a)
    discard_items(b,[next(t2 for t2 in b.GetTracks()if force._uid(t2)==force._uid(t))])
    r=pair.compare(a,b,retired_uuids={force._uid(t)})
    assert not r['preserved'] and len(r['demoted_parts'])==1


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_fill_split_creates_multiple_tokens_in_original_component(face):
    a,z=board(face,solid=True);b=clone(a);setfill(next(iter(b.Zones())),SPLIT)
    r=pair.compare(a,b)
    assert not r['preserved'] and r['overlap_token_count']==2
    assert r['source_component_count']==1 and r['child_component_count']==2


@pytest.mark.parametrize('merge',['fill','track'])
def test_actual_merge_permitted_without_rating_or_release_credit(merge):
    a,z=board();b=clone(a);zz=next(iter(b.Zones()))
    if merge=='fill':setfill(zz,SOLID)
    else:bridge(b,zz)
    r=pair.compare(a,b)
    assert r['preserved'] and r['source_component_count']==2 and r['child_component_count']==1
    assert not r['routing_admitted'] and not r['release_authority']


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_antipad_hole_changes_hash_but_not_component(face):
    a,z=board(face,solid=True);b=clone(a)
    setfill(next(iter(b.Zones())),[[rect(0,0,10000000,4000000),rect(4500000,1500000,5500000,2500000)]])
    r=pair.compare(a,b)
    assert r['preserved'] and r['source_component_count']==r['child_component_count']==1
    tokens=[k for part in r['source_parts']for k in part if k[0]=='zone_overlap']
    assert len(tokens)==1 and tokens[0][-2]!=tokens[0][-1]


@pytest.mark.parametrize('fault',['deleted','foreign_net','foreign_face','unfilled','duplicate'])
def test_unknown_or_changed_parent_zone_identity_refuses(fault):
    a,z=board();b=clone(a);zz=next(iter(b.Zones()))
    if fault=='deleted':discard_items(b,[zz])
    elif fault=='foreign_net':
        b.Add(pcbnew.NETINFO_ITEM(b,'OTHER'));zz.SetNet(b.FindNet('OTHER'))
    elif fault=='foreign_face':zz.SetLayer(pcbnew.B_Cu)
    elif fault=='unfilled':zz.UnFill()
    else:
        duplicate=pcbnew.ZONE(a);duplicate.m_Uuid.Clone(z.m_Uuid);a.Add(duplicate)
    with pytest.raises((ValueError,RuntimeError)):pair.compare(a,b)


@pytest.mark.parametrize('kind',['tangent','hole','lost_island'])
def test_no_positive_area_overlap_is_not_surviving_source_material(kind):
    a,z=board(solid=True);b=clone(a);zz=next(iter(b.Zones()))
    if kind=='tangent':setfill(zz,[[rect(10000000,0,12000000,4000000)]])
    elif kind=='hole':
        setfill(z,[[rect(0,0,10000000,4000000),rect(3000000,1000000,7000000,3000000)]])
        setfill(zz,[[rect(3500000,1500000,6500000,2500000)]])
    else:setfill(z,SPLIT);setfill(zz,[SPLIT[0]])
    with pytest.raises(ValueError,match='no_positive_surviving_overlap'):pair.compare(a,b)


def test_exact_integer_positive_area_not_bbox_or_tangent():
    a=fill.reconstruct([[rect(0,0,100,100)]],time.monotonic()+2.)
    for x,expected in [(100,False),(99,True),(101,False)]:
        b=fill.reconstruct([[rect(x,0,x+100,100)]],time.monotonic()+2.)
        assert pair._positive_overlap(a,b,time.monotonic()+2.)is expected


def test_moved_pad_exact_key_rebinding_is_not_pose_authority():
    a,z=board();fp=pcbnew.FOOTPRINT(a);fp.SetReference('P');a.Add(fp)
    p=pcbnew.PAD(fp);p.SetNumber('1');p.SetSize(pcbnew.VECTOR2I(200000,200000))
    p.SetPosition(pcbnew.VECTOR2I(500000,500000));p.SetNet(z.GetNet());fp.Add(p)
    b=clone(a);q=next(iter(b.FindFootprintByReference('P').Pads()));q.SetPosition(pcbnew.VECTOR2I(600000,500000))
    with pytest.raises(ValueError,match='surviving_source_conductor_missing'):pair.compare(a,b)
    r=pair.compare(a,b,identity_rebindings={force._item_key(q):force._item_key(p)})
    assert r['preserved'] and r['independent_delta_pose_current_receiving_still_required']
    with pytest.raises(ValueError,match='rebinding'):
        pair.compare(a,b,identity_rebindings={force._item_key(next(iter(b.GetTracks()))):force._item_key(p)})


@pytest.mark.parametrize('kwargs',[{'timeout_s':True},{'timeout_s':11},{'max_items':1},
    {'max_polygons':1},{'max_vertices':31},{'retired_uuids':['invented']},
    {'retained_keys':{('copper','invented')}}])
def test_bounds_and_unknown_comparison_authority_fail_closed(kwargs):
    a,z=board();b=clone(a)
    with pytest.raises(ValueError):pair.compare(a,b,**kwargs)


def test_comparison_reads_do_not_mutate_original_fill_or_native_identities():
    import cec_cell_row_rebuild as row
    a,z=board();b=clone(a);before=[row._source_binding(x)for x in(a,b)]
    assert pair.compare(a,b)['preserved']
    assert before==[row._source_binding(x)for x in(a,b)]


def test_existing_source_track_net_cannot_change_under_same_uuid():
    a,z=board();b=clone(a);b.Add(pcbnew.NETINFO_ITEM(b,'OTHER'))
    next(iter(b.GetTracks())).SetNet(b.FindNet('OTHER'))
    with pytest.raises(ValueError,match='net_changed'):pair.compare(a,b)


def test_only_retired_copper_is_removed_from_comparison_not_old_reachability():
    a,z=board();t=bridge(a,z);b=clone(a)
    r=pair.compare(a,b,retired_uuids={force._uid(t)},retained_keys=set())
    assert r['preserved'] and r['source_component_count']==1
    assert all(k[0]=='zone_overlap'for p in r['source_parts']for k in p)


def test_island_in_old_hole_never_acquires_old_component_token():
    a,z=board(solid=True)
    b=clone(a);zz=next(iter(b.Zones()))
    setfill(z,[[rect(0,0,10000000,4000000),rect(3000000,1000000,7000000,3000000)]])
    # Keep all original material; add a disconnected island wholly in its hole.
    setfill(zz,[[rect(0,0,10000000,4000000),rect(3000000,1000000,7000000,3000000)],
        [rect(4000000,1500000,6000000,2500000)]])
    r=pair.compare(a,b)
    assert r['preserved'] and r['overlap_token_count']==1
    assert r['child_component_count']==1  # New-only material gets no Source key.
    assert r['native_child_component_count']==2


def test_foreign_face_track_cannot_repair_an_actual_fill_split():
    a,z=board(solid=True);b=clone(a);zz=next(iter(b.Zones()));setfill(zz,SPLIT)
    t=bridge(b,zz);t.SetLayer(pcbnew.B_Cu)
    r=pair.compare(a,b)
    assert not r['preserved'] and len(r['demoted_parts'])==1


def test_new_foreign_net_track_is_not_reachability_credit():
    a,z=board(solid=True);b=clone(a);zz=next(iter(b.Zones()));setfill(zz,SPLIT)
    t=bridge(b,zz);b.Add(pcbnew.NETINFO_ITEM(b,'OTHER'));t.SetNet(b.FindNet('OTHER'))
    assert not pair.compare(a,b)['preserved']


def test_expired_shared_deadline_is_unknown_not_preserved(monkeypatch):
    a,z=board();b=clone(a);clock=iter([0.,20.])
    monkeypatch.setattr(pair.time,'monotonic',lambda:next(clock,20.))
    with pytest.raises(ValueError,match='deadline'):pair.compare(a,b,timeout_s=1.)


def test_missing_literal_fill_and_unassigned_material_refuse():
    a,z=board();b=clone(a)
    z.SetFilledPolysList(z.GetLayer(),pcbnew.SHAPE_POLY_SET())
    with pytest.raises((ValueError,RuntimeError)):pair.compare(a,b)
    a,z=board();next(iter(a.GetTracks())).SetNetCode(0)
    with pytest.raises(ValueError,match='unknown_native_conductor_net'):pair.compare(a,b)


def test_exact_limit_succeeds_but_combined_polygon_bound_still_applies():
    a,z=board();b=clone(a)
    assert pair.compare(a,b,max_vertices=32,max_polygons=4)['preserved']
    with pytest.raises(ValueError,match='total_fill_complexity_bound'):
        pair.compare(a,b,max_polygons=3)


def test_cloned_pad_uuid_distinct_actual_owners_is_not_ambiguous():
    a,z=board();pads=[]
    for n,x in enumerate([500000,6500000]):
        fp=pcbnew.FOOTPRINT(a);fp.SetReference('CLONE'+str(n));a.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetSize(pcbnew.VECTOR2I(200000,200000))
        p.SetPosition(pcbnew.VECTOR2I(x,500000));p.SetNet(z.GetNet())
        p.m_Uuid.Clone(pcbnew.KIID('33333333-3333-4333-8333-333333333333'));fp.Add(p);pads.append(p)
    b=clone(a);r=pair.compare(a,b)
    assert r['preserved'] and r['source_component_count']==2
    assert len({force._item_key(p)for p in pads})==2


@pytest.mark.parametrize('kind',['track','zone'])
def test_cross_class_pad_uuid_alias_still_refuses(kind):
    a,z=board();fp=pcbnew.FOOTPRINT(a);fp.SetReference('CLONE');a.Add(fp)
    p=pcbnew.PAD(fp);p.SetNumber('1');p.SetPosition(pcbnew.VECTOR2I(500000,500000))
    p.SetNet(z.GetNet());p.m_Uuid.Clone(z.m_Uuid if kind=='zone'else next(iter(a.GetTracks())).m_Uuid);fp.Add(p)
    with pytest.raises(ValueError,match='ambiguous_native_parent_identity'):pair.compare(a,a)
