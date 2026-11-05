"""Delete only existing GND metal; virtual detours never waive real returns."""
import copy,os
from pathlib import Path
import pcbnew
import pytest
import cec_native_ground_span_reflow as owner
import cec_retained_ground_path_stage as stage
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,first_via=True):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
    def point(p):
        x,y=p[0]-15000000,p[1]-15000000
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return (15000000+x,15000000+y)
    a,z=(10000000,10000000),(12000000,10000000)
    for i,at in enumerate((a,z)):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('UNRELATED_'+str(i));b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I(600000,600000))
        ls=pcbnew.LSET();ls.AddLayer(layer);p.SetLayerSet(ls);p.SetNet(b.FindNet('GND'))
        p.SetPosition(pcbnew.VECTOR2I(*point(at)));fp.Add(p)
        if i or first_via:
            v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I(*point(at)))
            v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    def edge(a,z):
        t=track(b,'GND',[q/1e6 for q in point(a)],[q/1e6 for q in point(z)],width=.2,layer=layer)
        t.SetLocked(True);return force._uid(t)
    cut=[edge(a,z)];points=[a,(10000000,10400000),(12000000,10400000),z]
    kept=[edge(p,q) for p,q in zip(points,points[1:])]
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        zone=pcbnew.ZONE(b);zone.SetNet(b.FindNet('GND'));zone.SetLayer(face)
        zone.SetLocalClearance(200000);zone.SetMinThickness(100000);zone.Outline().NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):zone.Outline().Append(x*1000000,y*1000000)
        b.Add(zone)
    source=tmp_path/'source.kicad_pcb';additive._ground_refill(b);field._save_field_snapshot(b,source)
    points=[list(point(p)) for p in points]
    if points[0]>points[-1]:points.reverse()
    return b,source,cut,kept,points


def proposal(b,cut,points,**options):
    args=dict(maximum_extra_nm=800000,allow_locked_track_uuids=cut,reuse_retained_source=True,
        retained_path_only=True,retained_cycle_pruning=True,retained_source_pad_portals=True)
    args.update(options);return owner.plan(b,cut,points,**args)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_cycle_pruning_never_adds_the_longer_or_hard90_virtual_witness(tmp_path,quarter,mirror,layer):
    b,source,cut,kept,points=fixture(tmp_path,quarter,mirror,layer);raw=source.read_bytes()
    with pytest.raises(ValueError):proposal(b,cut,points,retained_cycle_pruning=False)
    q=proposal(b,cut,points)
    assert q['retained_cycle_pruning'] and q['source_length_nm']==2000000
    assert q['replacement_length_nm']==2800000 and not q['emitted_segments_nm']
    assert not owner.materialize(b,q)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    r=owner.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'] and not r['errors'],r
    assert r['retained_cycle_pruning'] and r['no_new_tracks_or_holes'] and not r['added_track_uuids']
    assert r['every_source_retained_contact_and_proved_ground_return_preserved']
    assert r['source_span_already_redundant_to_retained_native_copper']
    assert r['exact_saved_source_subtract_add_and_ground_refill']['method']=='entire_native_source_subtraction_saved_tree_and_sidecars_equal'
    assert source.read_bytes()==raw and not r['current_qualified'] and not r['release_authority']


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('quarter',[0,1])
def test_longer_virtual_path_is_refused_if_any_real_source_terminal_return_becomes_longer(tmp_path,layer,quarter):
    b,source,cut,kept,points=fixture(tmp_path,quarter=quarter,layer=layer,first_via=False)
    q=proposal(b,cut,points);owner.materialize(b,q)
    child=force._copy_family(source,tmp_path/'refused');field._save_field_snapshot(b,child)
    r=owner.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and any('existing_return_worsened' in e for e in r['errors']),r


@pytest.mark.parametrize('budget',[0,1,799999,1000001,True,-1])
def test_exact_virtual_work_bound_has_no_one_nm_float_allowance(tmp_path,budget):
    b,source,cut,kept,points=fixture(tmp_path)
    with pytest.raises(ValueError):proposal(b,cut,points,maximum_extra_nm=budget)


@pytest.mark.parametrize('options',[dict(retained_path_only=False),dict(reuse_retained_source=False),
    dict(retained_cycle_pruning=1)])
def test_retained_cycle_mode_cannot_be_used_for_new_routing_or_untyped_policy(tmp_path,options):
    b,source,cut,kept,points=fixture(tmp_path)
    with pytest.raises(ValueError):proposal(b,cut,points,**options)


@pytest.mark.parametrize('fault',['thin','foreign','missing','new_track','forged_flag','forged_bound'])
def test_cycle_receiver_cannot_hide_material_or_policy_tampering(tmp_path,fault):
    b,source,cut,kept,points=fixture(tmp_path);q=proposal(b,cut,points);owner.materialize(b,q)
    live={force._uid(t):t for t in b.GetTracks()}
    if fault=='thin':live[kept[1]].SetWidth(199999)
    elif fault=='foreign':
        b.Add(pcbnew.NETINFO_ITEM(b,'OTHER'));live[kept[1]].SetNet(b.FindNet('OTHER'))
    elif fault=='missing':b.Remove(live[kept[1]])
    elif fault=='new_track':track(b,'GND',(18,18),(19,18),width=.2)
    elif fault=='forged_flag':q=copy.deepcopy(q);q['retained_cycle_pruning']=False
    else:q=copy.deepcopy(q);q['maximum_extra_nm']=799999
    child=force._copy_family(source,tmp_path/'hostile')
    if fault=='foreign':pcbnew.SaveBoard(str(child),b)
    else:field._save_field_snapshot(b,child)
    r=owner.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r


def test_source_material_contacts_remain_explicitly_owned_not_a_legacy_mode_waiver(tmp_path):
    b,source,cut,kept,points=fixture(tmp_path)
    q=proposal(b,cut,points,retained_source_pad_portals=False);owner.materialize(b,q)
    child=force._copy_family(source,tmp_path/'contacts');field._save_field_snapshot(b,child)
    r=owner.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and any('retained_contact_identity_changed' in e for e in r['errors']),r


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_bounded_stage_uses_same_independent_no_new_copper_receiver(tmp_path,layer):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    b,source,cut,kept,points=fixture(tmp_path,layer=layer)
    r=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),allow_locked_source=True,cycle_pruning=True)
    assert r['ok'] and r['complete'] and r['changed'] and not r['errors'],r
    assert r['records'][0]['plan']['retained_cycle_pruning'] and r['new_tracks']==r['new_holes']==0
    assert not r['attempts'][-1]['new_native_fault_ids'] and r['source_family_and_code_unchanged']
