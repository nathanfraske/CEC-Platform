"""Typed fixed-input finishing cannot move a force bus or its pickup."""
import copy,json,math
import pcbnew
import pytest
import cec_measurement_leaf_finish as finish
import cec_measurement_leaf as leaf
import cec_force_current as force
import cec_field_coupling as field
from test_local_branch_access import fixture


def polyline(quarter=0,mirror=False,width=250000,diagonal=False):
    points=[(2000000,2000000),(2000000,4000000),(6000000,4000000),(6000000,6000000)]
    if diagonal:points=[(2000000,2000000),(4000000,4000000),(6000000,2000000)]
    def transform(p):
        x,y=p
        if mirror:x=8000000-x
        for _ in range(quarter):x,y=8000000-y,x
        return [x,y]
    return dict(scope='source_typed_thin_measurement_leaf',width_nm=width,points_nm=[transform(p) for p in points])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('width',[200000,350000])
def test_full_width_source_corner_geometry_is_frame_invariant_and_shorter(quarter,mirror,width):
    q=polyline(quarter,mirror,width);frozen=copy.deepcopy(q);offers=finish.paths(q)
    assert offers and q==frozen
    for choice in offers:
        p=choice['points_nm'];assert p[0]==q['points_nm'][0] and p[-1]==q['points_nm'][-1]
        assert choice['visible_source_corners']==2 and finish.right_angles(p)==0
        assert choice['minimum_full_width_inner_flat_nm']==20000
        assert all(a[0]==b[0] or a[1]==b[1] or abs(a[0]-b[0])==abs(a[1]-b[1]) for a,b in zip(p,p[1:]))
        assert sum(math.dist(a,b) for a,b in zip(p,p[1:]))<sum(math.dist(a,b) for a,b in zip(q['points_nm'],q['points_nm'][1:]))


@pytest.mark.parametrize('quarter',range(4))
def test_diagonal_right_angle_has_a_cardinal_full_width_flat(quarter):
    q=polyline(quarter=quarter,diagonal=True);offers=finish.paths(q);assert offers
    assert all(c['visible_source_corners']==1 and finish.right_angles(c['points_nm'])==0 for c in offers)


@pytest.mark.parametrize('fault',['scope','width_zero','width_bool','width_wide','too_many','zero_edge','coordinate_bool','coordinate_float','missing'])
def test_geometry_menu_is_bounded_and_never_generic_net_ripup_authority(fault):
    q=polyline()
    if fault=='scope':q['scope']='ordinary_force_net'
    elif fault=='width_zero':q['width_nm']=0
    elif fault=='width_bool':q['width_nm']=True
    elif fault=='width_wide':q['width_nm']=350001
    elif fault=='too_many':q['points_nm']*=5
    elif fault=='zero_edge':q['points_nm'][1]=q['points_nm'][0]
    elif fault=='coordinate_bool':q['points_nm'][0][0]=True
    elif fault=='coordinate_float':q['points_nm'][0][0]=1.
    else:q.pop('points_nm')
    with pytest.raises(ValueError):finish.paths(q)


def test_source_elbow_too_small_to_show_full_width_flat_is_not_progress():
    q=polyline(width=350000);q['points_nm']=[[0,0],[0,100000],[100000,100000]]
    assert not finish.paths(q)


def prepare_source(tmp_path,quarter=0,back=False):
    source,unused,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));origin=pcbnew.VECTOR2I_MM(15,15)
    # The older access fixture intentionally leaves a PLUS/GND crossing as
    # unrelated inherited debt while it tests ONLY MINUS. A two-leaf finish
    # must not bless that short: start this native fixture with a clean PLUS
    # path through the actual open left side of its Ground loop instead.
    from cec_native_items import discard_items
    from test_field_proposals import track
    discard_items(b,[t for t in b.GetTracks() if t.GetNetname()=='MEASURE_PLUS'])
    points=[(16,15),(16,14.2),(13,14.2),(13,18),(24,18),(24,17)]
    for a,z in zip(points,points[1:]):track(b,'MEASURE_PLUS',a,z,width=.2)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(face);z.SetLocalClearance(200000)
        z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    import cec_additive_route_receiving as additive
    additive._ground_refill(b)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
        item.Rotate(origin,pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:item.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    b.FindFootprintByReference('U_RENAMED').SetReference('SENSOR_WITH_UNRELATED_NAME')
    field._save_field_snapshot(b,source)
    return source,uid


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_stage_is_source_role_selected_and_independently_received_without_holes_or_motion(tmp_path,quarter,back):
    source,uid=prepare_source(tmp_path,quarter,back);raw=source.read_bytes()
    r=finish.run(source,tmp_path/'finishing',board_hint='fixture')
    assert r['ok'] and r['complete'] and r['changed'],r
    plan=r['records'][0]['plan'];saved=finish.receive(source,r['candidate'],board_hint='fixture',**json.loads(json.dumps(plan)))
    assert saved['ok'] and saved['complete'],saved
    assert sum(x['source_right_angles']-x['candidate_right_angles'] for x in saved['source_owned_measurement_progress'])>0
    assert saved['exact_force_copper_barrels_and_component_poses_preserved'] and not saved['retired_via_uuids']
    assert not saved['current_authority'] and not saved['kelvin_qualified'] and not saved['release_authority']
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['pose','barrel','force_track','width','retained_pickup','free_nonmiter_path'])
def test_saved_receiving_rejects_unowned_mutations_or_nonfinishing_reflow(tmp_path,fault):
    source,uid=prepare_source(tmp_path);r=finish.run(source,tmp_path/'finishing',board_hint='fixture');assert r['changed']
    b=pcbnew.LoadBoard(r['candidate']);params=r['records'][0]['plan']
    if fault=='pose':b.FindFootprintByReference('SENSOR_WITH_UNRELATED_NAME').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(3,3));v.SetNet(b.FindNet('GND'));v.SetWidth(600000);v.SetDrill(300000);b.Add(v)
    elif fault=='force_track':
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(3,3));t.SetEnd(pcbnew.VECTOR2I_MM(4,3));t.SetWidth(200000);t.SetNet(b.FindNet('+3V3'));b.Add(t)
    elif fault=='width':next(t for t in b.GetTracks() if force._uid(t) in r['records'][0]['materialized']['added_native_uuids']).SetWidth(199999)
    elif fault=='retained_pickup':b.FindFootprintByReference('FIXED').Move(pcbnew.VECTOR2I(1,0))
    else:
        from cec_native_items import discard_items
        p=leaf.plan(b,params['pad_uuids'][0]);discard_items(b,[t for t in b.GetTracks() if force._uid(t) in p['track_uuids']])
        leaf.add_path(b,p,p['points_nm'][:1]+[[16000000,14000000],[10000000,14000000]]+p['points_nm'][-1:])
    field._save_field_snapshot(b,r['candidate']);result=finish.receive(source,r['candidate'],board_hint='fixture',**params)
    assert not result['ok'] and result['errors'] and not result['release_authority']


@pytest.mark.parametrize('value',[True,False,0,11,float('nan'),float('inf')])
def test_receiving_never_extends_an_invalid_or_boolean_work_lease(tmp_path,value):
    source,uid=prepare_source(tmp_path)
    r=finish.receive(source,source,board_hint='fixture',pad_uuids=[uid],timeout_s=value)
    assert not r['ok'] and r['errors']
