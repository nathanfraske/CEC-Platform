"""Native return kernel ownership, actual plane islands and saved replay."""
import copy
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_redundant_local_ground_return as op
from cec_native_items import discard_items
from test_ground_plane_echo import fixture as planes
from test_field_proposals import track


def fixture(tmp_path,angle=0,overlap=False):
    source,_=planes(tmp_path);b=pcbnew.LoadBoard(str(source))
    discard_items(b,[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND'])
    old=next(f for f in b.GetFootprints() if any(tuple(p.GetPosition())==(10000000,15000000) for p in f.Pads()))
    b.Delete(old)
    b.Add(pcbnew.NETINFO_ITEM(b,'+3V3'))
    cap=pcbnew.FOOTPRINT(b);cap.SetReference('C173');cap.SetValue('1uF')
    cap.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
    for number,net,x in [('1','+3V3',8.4),('2','GND',10.)]:
        p=pcbnew.PAD(cap);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.9,1.))
        p.SetPosition(pcbnew.VECTOR2I_MM(x,15));p.SetNet(b.GetNetsByName()[net])
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers);cap.Add(p)
    b.Add(cap)
    via=pcbnew.PCB_VIA(b);via.SetNet(b.GetNetsByName()['GND'])
    via.SetPosition(pcbnew.VECTOR2I_MM(12,15));via.SetWidth(350000);via.SetDrill(250000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLocked(True);b.Add(via)
    group=pcbnew.PCB_GROUP(b);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);b.Add(group);group.AddItem(via)
    track(b,'GND',(10,15),(11,15));track(b,'GND',(11,15),(12,15))
    if overlap:track(b,'GND',(11.5,15),(12.5,15))
    if angle:
        origin=pcbnew.VECTOR2I_MM(15,15);turn=pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
        for item in [*b.GetFootprints(),*b.GetTracks()]:item.Rotate(origin,turn)
    uid=force._uid(via)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return source,pcbnew.LoadBoard(str(source)),uid


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('overlap',[False,True])
def test_actual_redundant_kernel_preserves_inpad_entry_and_all_plane_islands(tmp_path,angle,overlap):
    source,b,uid=fixture(tmp_path,angle,overlap);before=source.read_bytes()
    q=op.plan(b,source,uid,allow_source_locked=True)
    assert len(q['obsolete_surface_track_uuids'])==(3 if overlap else 2)
    assert len(q['source_minus_kernel_stale_barrel_proof']['saved_plane_witnesses'])==2
    assert not q['ordinary_ground_stitch_retirement_authorized']
    child=force._copy_family(source,tmp_path/'child');op.subtract(b,q)
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['all_surviving_native_partitions_preserved']
    assert len(r['actual_saved_reference_plane_bridges'])==2
    assert not r['release_authority'] and not r['current_qualified']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['group_locked','group_renamed','ungrouped','ordinary_barrel',
    'foreign_track','another_land','another_barrel','inner_departure','loop','width','track_group',
    'not_capacitor','root_no_longer_inpad','missing_reference_plane','unfilled','plane_island',
    'no_lock_authority','unsaved_source'])
def test_live_stitch_mesh_foreign_contact_unknown_geometry_and_unowned_changes_refuse(tmp_path,fault):
    source,b,uid=fixture(tmp_path);v=next(t for t in b.GetTracks() if force._uid(t)==uid)
    group=next(g for g in b.Groups() if g.ContainsItem(v))
    if fault=='group_locked':group.SetLocked(True)
    elif fault=='group_renamed':group.SetName('REAL_STRUCTURAL_OWNER')
    elif fault=='ungrouped':group.RemoveItem(v)
    elif fault=='ordinary_barrel':v.SetWidth(600000);v.SetDrill(300000)
    elif fault=='foreign_track':track(b,'+3V3',(11,14),(11,16))
    elif fault=='another_land':
        f=pcbnew.FOOTPRINT(b);f.SetReference('OTHER_OWNER');p=pcbnew.PAD(f)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetNet(b.GetNetsByName()['GND'])
        p.SetPosition(pcbnew.VECTOR2I_MM(11,15));p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers);f.Add(p);b.Add(f)
    elif fault=='another_barrel':
        n=pcbnew.PCB_VIA(b);n.SetPosition(pcbnew.VECTOR2I_MM(11,15));n.SetWidth(600000);n.SetDrill(300000)
        n.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);n.SetViaType(pcbnew.VIATYPE_THROUGH)
        n.SetNet(b.GetNetsByName()['GND']);b.Add(n)
    elif fault=='inner_departure':track(b,'GND',(12,15),(13,15),layer=pcbnew.In2_Cu)
    elif fault=='loop':
        for a,z in [((11,15),(11,14)),((11,14),(12,14)),((12,14),(12,15))]:track(b,'GND',a,z)
    elif fault=='width':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(500000)
    elif fault=='track_group':
        group.AddItem(next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK'))
    elif fault=='not_capacitor':b.FindFootprintByReference('C173').SetValue('unidentified')
    elif fault=='root_no_longer_inpad':
        next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and tuple(t.GetPosition())==(10000000,15000000)).Move(pcbnew.VECTOR2I_MM(.3,0))
    elif fault=='missing_reference_plane':discard_items(b,[next(iter(b.Zones()))])
    elif fault=='unfilled':next(iter(b.Zones())).UnFill()
    elif fault=='plane_island':
        z=next(iter(b.Zones()));gap=pcbnew.SHAPE_POLY_SET();gap.NewOutline()
        for at in ((11.95,1),(12.05,1),(12.05,29),(11.95,29)):gap.Append(pcbnew.VECTOR2I_MM(*at))
        fill=pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(z.GetLayer()));fill.BooleanSubtract(gap)
        z.SetFilledPolysList(z.GetLayer(),fill);z.SetIsFilled(True)
    elif fault=='unsaved_source':b.FindFootprintByReference('C173').SetValue('2.2uF')
    if fault=='foreign_track':
        # KiCad reload can propagate a literal foreign short's net identity.
        # The strict source inlet must refuse that snapshot, not manufacture
        # a newly same-net branch for the subtraction planner to accept.
        with pytest.raises(field._ProposalUnknown,match='saved_identity'):
            field._save_field_snapshot(b,source)
        with pytest.raises(ValueError):op.plan(b,source,uid,allow_source_locked=True)
        return
    if fault!='unsaved_source':field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.plan(b,source,uid,allow_source_locked=fault!='no_lock_authority')
    assert field._field_snapshot_inventory(b)==before


def test_a_worker_cannot_expand_the_independently_typed_cut(tmp_path):
    source,b,uid=fixture(tmp_path);q=op.plan(b,source,uid,allow_source_locked=True)
    forged=copy.deepcopy(q);forged['retired_track_uuids'].append(q['retained_root_via_uuid'])
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):op.subtract(b,forged)
    assert before==field._field_snapshot_inventory(b)


def test_actual_certificate_worker_stops_after_one_independently_received_kernel(tmp_path):
    from unittest.mock import patch
    import cec_certificate_repair as repair
    source,b,uid=fixture(tmp_path)
    raw=dict(violations=[dict(type='via_dangling',items=[dict(uuid=uid)])],unconnected_items=[])
    with patch.object(repair,'_run_drc',return_value=raw) as drc:
        changed,r=repair._drc_dangling_cleanup_worker(str(source),max_iterations=2)
    assert changed and r['removed_count']==3 and drc.call_count==1
    assert r['stop']=='single_received_obsolete_ground_kernel_step'
    assert r['obsolete_local_ground_kernel_proofs'][0]['receiving']['ok']
    assert r['full_board_admission_still_required']
    assert not any(force._uid(t)==uid for t in pcbnew.LoadBoard(str(source)).GetTracks())


def test_native_drc_discovery_deduplicates_and_rejects_a_plain_stitch(tmp_path):
    source,b,uid=fixture(tmp_path)
    raw=dict(violations=[dict(type='via_dangling',items=[dict(uuid=uid)]) for _ in range(3)])
    r=op.discover_from_drc(b,source,raw,authorize_source_locked=True)
    assert r['complete'] and len(r['plans'])==1 and not r['errors']
    other=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and force._uid(t)!=uid)
    r=op.discover_from_drc(b,source,dict(violations=[dict(type='via_dangling',
        items=[dict(uuid=force._uid(other))])]),authorize_source_locked=True)
    assert r['complete'] and not r['plans'] and r['refused']


def test_unknown_native_kernel_geometry_is_a_refusal_not_a_constructive_plan(tmp_path):
    from unittest.mock import patch
    source,b,uid=fixture(tmp_path);before=field._field_snapshot_inventory(b)
    with patch.object(op.physical,'_poly',side_effect=op.physical.Unknown('bounded_fixture_unknown')):
        with pytest.raises(ValueError,match='actual_geometry_unknown'):
            op.plan(b,source,uid,allow_source_locked=True)
    assert before==field._field_snapshot_inventory(b)


def test_actual_generated_factory_debt_does_not_need_a_native_drc_whitelist_failure(tmp_path):
    source,b,uid=fixture(tmp_path);empty=dict(violations=[])
    assert not op.discover_from_drc(b,source,empty,authorize_source_locked=True)['plans']
    r=op.discover_from_drc(b,source,empty,authorize_source_locked=True,include_source_factory_debt=True)
    assert r['complete'] and len(r['plans'])==1 and r['plans'][0]['via_uuid']==uid


def test_exact_source_proposal_replays_on_an_identical_private_family_copy(tmp_path):
    source,b,uid=fixture(tmp_path);q=op.plan(b,source,uid,allow_source_locked=True)
    copied=force._copy_family(source,tmp_path/'identical-source')
    private=pcbnew.LoadBoard(str(copied))
    assert op.plan(private,copied,uid,allow_source_locked=True)==q
    op.subtract(private,q)
    assert not any(force._uid(t)==uid for t in private.GetTracks())


def test_discovery_returns_first_complete_scope_without_spending_lease_on_later_candidates(tmp_path):
    from unittest.mock import patch
    source,b,uid=fixture(tmp_path)
    other=next(force._uid(t) for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and force._uid(t)!=uid)
    raw=dict(violations=[dict(type='via_dangling',items=[dict(uuid=v)]) for v in (uid,other)])
    with patch.object(op,'plan',wraps=op.plan) as retype:
        r=op.discover_from_drc(b,source,raw,authorize_source_locked=True)
    assert r['complete'] and r['stopped_after_first_received_scope'] and len(r['plans'])==1
    assert retype.call_args.args[2]==uid
    assert retype.call_count==sorted((uid,other)).index(uid)+1
    assert r['remaining_candidate_count']==2-retype.call_count
