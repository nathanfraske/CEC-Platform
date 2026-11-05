import time
import pytest
import pcbnew
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from test_native_pending_joint_cohort import row
from cec_native_branch_forest import plan
from cec_native_retained_port_islands import collapse


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_disconnected_same_zone_polygons_do_not_collapse_distinct_ports(face):
    import cec_native_fill_geometry as fill
    from test_native_zone_islands import fixture as zone_fixture
    b,z=zone_fixture(face=face)
    z.m_Uuid.Clone(pcbnew.KIID('00000000-0000-4000-8000-000000000001'))
    cut=track(b,'GND',(.5,.5),(6.5,.5),layer=face,width=.2)
    points,receipt=collapse(b,net_code=int(z.GetNetCode()),layer=int(face),width_nm=200000,
        points_nm=[[500000,500000],[6500000,500000]],retired_uuids={force._uid(cut)},deadline=time.monotonic()+5.)
    assert len(points)==2 and receipt['distinct_actual_retained_components']==2
    assert all(p['exact_native_zone_islands']for p in receipt['contacts'])


def test_hole_point_cannot_borrow_other_fill_polygon_material():
    from test_native_zone_islands import fixture as zone_fixture
    b,z=zone_fixture(hole=True);cut=track(b,'GND',(.5,.5),(6.5,.5),width=.2)
    with pytest.raises(ValueError,match='missing_or_ambiguous_actual_material'):
        collapse(b,net_code=int(z.GetNetCode()),layer=int(pcbnew.F_Cu),width_nm=100000,
            points_nm=[[2000000,2000000],[6500000,500000]],retired_uuids={force._uid(cut)},deadline=time.monotonic()+5.)


def fixture(quarter=0,shift=(0,0),foreign=False):
    b=_board([(10,20,'STATE'),(30,20,'STATE'),(20,30,'STATE'),(20,20,'OTHER')])
    cut=[track(b,'STATE',(10,20),(20,20)),track(b,'STATE',(20,20),(30,20)),
        track(b,'STATE',(20,20),(20,30))]
    bridge=[track(b,'OTHER' if foreign else 'STATE',(10,20),(10,30)),
        track(b,'OTHER' if foreign else 'STATE',(10,30),(20,30))]
    for i in [*b.GetFootprints(),*b.GetTracks()]:
        i.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        i.Move(pcbnew.VECTOR2I_MM(*shift))
    return b,cut,bridge


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('shift',[(0,0),(3,-2)])
def test_branch_planning_uses_actual_retained_islands_not_duplicate_ports(quarter,shift):
    b,cut,bridge=fixture(quarter,shift)
    snapshot=[(force._uid(t),tuple(t.GetStart()),tuple(t.GetEnd())) for t in b.GetTracks()]
    _,old,_=plan(b,[row(cut[0])],clearance_for=lambda n:200000)
    _,new,proof=plan(b,[row(cut[0])],clearance_for=lambda n:200000,
        collapse_retained_native_ports=True)
    assert len(old[0]['route_rows'])==2 and len(new[0]['route_rows'])==1
    receipt=new[0]['retained_native_port_island_collapse']
    assert receipt['input_port_count']==3 and receipt['distinct_actual_retained_components']==2
    assert set(proof['exact_retired_uuids'])=={force._uid(t) for t in cut}
    assert snapshot==[(force._uid(t),tuple(t.GetStart()),tuple(t.GetEnd())) for t in b.GetTracks()]
    assert not receipt['release_authority'] and not receipt['native_geometry_mutated']


def collapse_args(b,cut):
    return dict(net_code=int(b.GetNetcodeFromNetname('STATE')),layer=int(pcbnew.F_Cu),
        width_nm=200000,points_nm=[[10000000,20000000],[30000000,20000000],[20000000,30000000]],
        retired_uuids={force._uid(t) for t in cut},deadline=time.monotonic()+2.)


@pytest.mark.parametrize('defect',['foreign','other_face','pending','stale_id','deadline','duplicate','all_one'])
def test_no_label_projected_face_pending_or_missing_material_credit(defect):
    b,cut,bridge=fixture(foreign=defect=='foreign')
    a=collapse_args(b,cut)
    if defect=='other_face':
        for t in bridge:t.SetLayer(pcbnew.B_Cu)
    elif defect=='pending':a['provisional_uuids']=[force._uid(t) for t in bridge]
    elif defect=='stale_id':a['retired_uuids']=['stale']
    elif defect=='deadline':a['deadline']=time.monotonic()-1
    elif defect=='duplicate':a['points_nm'][1]=list(a['points_nm'][0])
    elif defect=='all_one':
        track(b,'STATE',(10,30),(30,30));track(b,'STATE',(30,30),(30,20))
    if defect in ('foreign','other_face','pending'):
        result,receipt=collapse(b,**a)
        assert len(result)==3 and receipt['distinct_actual_retained_components']==3
    else:
        with pytest.raises(ValueError):collapse(b,**a)
