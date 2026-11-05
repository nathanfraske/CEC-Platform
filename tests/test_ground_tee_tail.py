"""Dead placement leftovers may not claim adjoining live returns or mesh."""
import copy,json
import pcbnew,pytest
import cec_ground_tee_tail as worker
import cec_ground_dead_end_tail as original
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
from test_ground_dead_end_tail import fixture as root_fixture
from test_field_proposals import track


def fixture(tmp_path,angle=0,back=False,locked=False):
    source,b,body,tip,root,xy=root_fixture(tmp_path,angle)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    branch=track(b,'GND',xy((3,0)),xy((3,-2)))
    owner=pcbnew.FOOTPRINT(b);owner.SetReference('RETAINED_TEST_LOAD');b.Add(owner)
    pad=pcbnew.PAD(owner);owner.Add(pad);pad.SetNumber('1');pad.SetPosition(pcbnew.VECTOR2I_MM(*xy((3,-2))))
    pad.SetNetCode(root.GetNetCode());pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetLayerSet(pcbnew.PAD.SMDMask())
    if back:
        for t in (body,tip,branch):t.SetLayer(pcbnew.B_Cu)
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(mask)
    tip.SetLocked(locked)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));additive._ground_refill(b);field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    return source,b,live[force._uid(body)],live[force._uid(tip)],live[force._uid(root)],live[force._uid(branch)],xy


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('locked',[False,True])
def test_saved_tee_leaf_preserves_both_live_returns_and_reference_planes(tmp_path,angle,back,locked):
    source,b,body,tip,root,branch,_=fixture(tmp_path,angle,back,locked);raw=source.read_bytes()
    locks=[force._uid(tip)] if locked else []
    q=worker.plan(b,force._uid(tip),allow_locked_track_uuids=locks)
    assert q['retired_track_uuids']==[force._uid(tip)]
    assert set(q['retained_tee_track_uuids'])=={force._uid(body),force._uid(branch)}
    assert q['retained_root_via_uuid']==force._uid(root) and q['root_plane_contacts']
    q=json.loads(json.dumps(q));worker.subtract(b,q)
    child=force._copy_family(source,tmp_path/'child');additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=worker.receive(source,child,q,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_surviving_native_partitions_preserved'] and not proof['release_authority']
    assert source.read_bytes()==raw
    with pytest.raises(ValueError):original.plan(pcbnew.LoadBoard(str(source)),force._uid(tip))


@pytest.mark.parametrize('fault',['land','foreign_land','foreign_track','group','unrequested_lock','wide','missing_reference',
    'unknown_fill','exposed','body_tee','nearby_not_literal_tee','nonexact_lock_scope'])
def test_native_leaf_requires_no_load_no_foreign_contact_and_one_real_root(tmp_path,fault):
    source,b,body,tip,root,branch,xy=fixture(tmp_path)
    if fault in ('land','foreign_land'):
        owner=pcbnew.FOOTPRINT(b);owner.SetReference('DO_NOT_DELETE');b.Add(owner)
        pad=pcbnew.PAD(owner);owner.Add(pad);pad.SetNumber('1');pad.SetPosition(tip.GetEnd())
        pad.SetNetCode(b.GetNetcodeFromNetname('GND' if fault=='land' else '/CONTROL'))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetLayerSet(pcbnew.PAD.SMDMask())
    elif fault=='foreign_track':track(b,'/CONTROL',xy((3.4,.7)),xy((4.1,.1)))
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('protected_unknown_owner');b.Add(g);g.AddItem(tip)
    elif fault=='unrequested_lock':tip.SetLocked(True)
    elif fault=='wide':tip.SetWidth(500000)
    elif fault=='missing_reference':root.SetPosition(pcbnew.VECTOR2I_MM(28,28))
    elif fault=='unknown_fill':
        for z in b.Zones():z.UnFill()
    elif fault=='exposed':tip.SetHasSolderMask(True)
    elif fault=='body_tee':track(b,'GND',xy((3.5,.5)),xy((3.5,2)))
    elif fault=='nearby_not_literal_tee':branch.SetStart(pcbnew.VECTOR2I_MM(*xy((3.08,0))))
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):
        worker.plan(b,force._uid(tip),allow_locked_track_uuids=[force._uid(body)] if fault=='nonexact_lock_scope' else [])
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['stale','forged'])
def test_stale_or_forged_leaf_plan_cannot_change_the_retained_junction(tmp_path,fault):
    source,b,body,tip,root,branch,_=fixture(tmp_path)
    q=worker.plan(b,force._uid(tip))
    if fault=='stale':branch.SetWidth(250000)
    else:q=copy.deepcopy(q);q['retired_track_uuids'].append(force._uid(body))
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='stale_or_forged'):worker.subtract(b,q)
    assert field._field_snapshot_inventory(b)==before


def test_saved_leaf_receiver_does_not_accept_a_changed_retained_barrel(tmp_path):
    source,b,body,tip,root,branch,_=fixture(tmp_path);q=worker.plan(b,force._uid(tip));worker.subtract(b,q)
    root.SetDrill(350000);child=force._copy_family(source,tmp_path/'hostile')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    proof=worker.receive(source,child,q,board_hint='synthetic')
    assert not proof['ok'] and proof['errors'] and not proof['release_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_subwidth_source_connector_caps_do_not_become_a_fake_retained_tee(tmp_path,angle,back):
    from cec_native_items import discard_items
    source,b,body,tip,root,branch,_=fixture(tmp_path,back=back)
    discard_items(b,[tip]);face=pcbnew.B_Cu if back else pcbnew.F_Cu
    points=[(15,14),(15,17),(15.1393,17),(15.6393,17.5)]
    edges=[track(b,'GND',a,z,layer=face) for a,z in zip(points,points[1:])]
    if angle:
        origin=pcbnew.VECTOR2I_MM(15,14);turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
        for obj in [body,root,branch,b.FindFootprintByReference('RETAINED_TEST_LOAD'),*edges]:obj.Rotate(origin,turn)
    additive._ground_refill(b);field._save_field_snapshot(b,source);before=field._field_snapshot_inventory(b)
    q=worker.plan(b,force._uid(edges[-1]))
    assert set(q['retired_track_uuids'])=={force._uid(t) for t in edges}
    assert set(q['retained_tee_track_uuids'])=={force._uid(body),force._uid(branch)}
    assert field._field_snapshot_inventory(b)==before
