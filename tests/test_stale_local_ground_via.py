import copy
from unittest.mock import patch
import pcbnew,pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_stale_local_ground_via as op
from test_ground_plane_echo import fixture as ground_planes
from test_field_proposals import track
from cec_native_items import discard_items


def fixture(tmp_path,angle=0):
    source,_=ground_planes(tmp_path);b=pcbnew.LoadBoard(str(source))
    discard_items(b,[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND'])
    v=pcbnew.PCB_VIA(b);v.SetNet(b.GetNetsByName()['GND']);v.SetPosition(pcbnew.VECTOR2I_MM(12,15))
    v.SetWidth(350000);v.SetDrill(250000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLocked(True);b.Add(v)
    g=pcbnew.PCB_GROUP(b);g.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);b.Add(g);g.AddItem(v)
    if angle:
        origin=pcbnew.VECTOR2I_MM(15,15);turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
        for item in [*b.GetFootprints(),*b.GetTracks()]:item.Rotate(origin,turn)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    uid=force._uid(v);b=pcbnew.LoadBoard(str(source))
    v=next(t for t in b.GetTracks() if force._uid(t)==uid)
    g=next(g for g in b.Groups() if g.ContainsItem(v))
    return source,b,v,g


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_stranded_factory_tag_not_a_ground_stitch_or_live_return(tmp_path,angle):
    source,b,v,g=fixture(tmp_path,angle);before=source.read_bytes()
    p=op.plan(b,force._uid(v),allow_source_locked=True)
    assert len(p['saved_plane_witnesses'])==2 and p['retired_via_uuids']==[force._uid(v)]
    op.subtract(b,p);child=force._copy_family(source,tmp_path/'child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    r=op.receive(source,child,p,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert not r['ordinary_ground_stitch_retirement_authorized']
    assert source.read_bytes()==before and not r['release_authority']


@pytest.mark.parametrize('bad',['group_locked','group_renamed','ungrouped','ordinary','live_route',
    'foreign_route','no_bridge','one_plane','unfilled','plane_gap','not_ground','no_lock_authority'])
def test_refuse_live_function_unowned_geometry_and_unknown_plane_witness(tmp_path,bad):
    source,b,v,g=fixture(tmp_path);uid=force._uid(v)
    if bad=='group_locked':g.SetLocked(True)
    elif bad=='group_renamed':g.SetName('user protected')
    elif bad=='ungrouped':g.RemoveItem(v)
    elif bad=='ordinary':v.SetWidth(600000);v.SetDrill(300000)
    elif bad=='live_route':track(b,'GND',(12,15),(13,15))
    elif bad=='foreign_route':track(b,'TEST_SIGNAL',(12,15),(13,15))
    elif bad=='no_bridge':
        for other in b.GetTracks():
            if other.GetClass()=='PCB_VIA' and force._uid(other)!=uid:other.SetPosition(pcbnew.VECTOR2I_MM(25,25))
    elif bad=='one_plane':discard_items(b,[next(iter(b.Zones()))])
    elif bad=='unfilled':next(iter(b.Zones())).UnFill()
    elif bad=='plane_gap':
        z=next(iter(b.Zones()));gap=pcbnew.SHAPE_POLY_SET();gap.NewOutline()
        for at in ((10.8,14),(11.2,14),(11.2,16),(10.8,16)):gap.Append(pcbnew.VECTOR2I_MM(*at))
        fill=pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(z.GetLayer()));fill.BooleanSubtract(gap)
        z.SetFilledPolysList(z.GetLayer(),fill);z.SetIsFilled(True)
    elif bad=='not_ground':v.SetNet(b.GetNetsByName()['TEST_SIGNAL'])
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,uid,allow_source_locked=bad!='no_lock_authority')
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('bad',['source','proposal'])
def test_rederive_the_whole_source_before_deleting_native_items(tmp_path,bad):
    source,b,v,g=fixture(tmp_path);p=op.plan(b,force._uid(v),allow_source_locked=True)
    if bad=='source':next(iter(b.Zones())).SetAssignedPriority(2)
    else:p=copy.deepcopy(p);p['retired_track_uuids'].append(p['retained_root_via_uuid'])
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.subtract(b,p)
    assert field._field_snapshot_inventory(b)==before


def test_current_error_discovery_deduplicates_and_retypes_native_objects(tmp_path):
    source,b,v,g=fixture(tmp_path);uid=force._uid(v)
    raw=dict(violations=[dict(type='clearance',items=[dict(uuid=uid)]) for _ in range(6)])
    r=op.discover_from_drc(b,raw,authorize_source_locked=True)
    assert r['complete'] and len(r['plans'])==1 and not r['errors']
    track(b,'GND',(12,15),(13,15))
    r=op.discover_from_drc(b,raw,authorize_source_locked=True)
    assert r['complete'] and not r['plans'] and r['refused']


def test_certificate_worker_receives_the_saved_plane_bridge_before_adoption(tmp_path):
    import cec_certificate_repair as repair
    source,b,v,g=fixture(tmp_path);uid=force._uid(v)
    raw=dict(violations=[dict(type='clearance',items=[dict(uuid=uid)])],unconnected_items=[])
    with patch.object(repair,'_run_drc',side_effect=[raw,dict(violations=[],unconnected_items=[])]) as run_drc:
        changed,r=repair._drc_dangling_cleanup_worker(str(source),max_iterations=2)
    assert changed and r['removed_count']==1
    assert r['stale_local_ground_proofs'][0]['receiving']['ok']
    assert run_drc.call_count==1 and r['stop']=='single_received_stale_local_ground_step'
    assert not any(force._uid(t)==uid for t in pcbnew.LoadBoard(str(source)).GetTracks())
    assert r['full_board_admission_still_required']


def test_one_zone_uuid_does_not_hide_a_second_island_only_joined_by_the_retired_via(tmp_path):
    source,b,v,g=fixture(tmp_path);z=next(iter(b.Zones()))
    gap=pcbnew.SHAPE_POLY_SET();gap.NewOutline()
    for at in ((11.95,1),(12.05,1),(12.05,29),(11.95,29)):gap.Append(pcbnew.VECTOR2I_MM(*at))
    fill=pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(z.GetLayer()));fill.BooleanSubtract(gap)
    z.SetFilledPolysList(z.GetLayer(),fill);z.SetIsFilled(True)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,force._uid(v),allow_source_locked=True)
    assert field._field_snapshot_inventory(b)==before
