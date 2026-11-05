"""An existing complete surface path can own an exact deletion, not a waiver."""
import copy,os
from pathlib import Path
import pcbnew
import pytest
import cec_native_ground_span_reflow as owner
import cec_retained_ground_path_stage as stage
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_retained_ground_span_reuse import fixture as partial_fixture
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,planes=True):
    b,source,ids,keeper,points=partial_fixture(tmp_path,quarter,mirror,layer,planes=planes)
    # The previously missing first leg is now literal source copper, too.
    # It is never invented by a plane/nearby-pad/renderer connectivity hint.
    a,z=next((a,z) for a,z in zip(points,points[1:]) if a[0]!=z[0] and a[1]!=z[1])
    diagonal=track(b,'GND',[x/1e6 for x in a],[x/1e6 for x in z],width=.2,layer=layer)
    field._save_field_snapshot(b,source)
    return b,source,ids,keeper,force._uid(diagonal),points


def proposal(b,ids,points):
    return owner.plan(b,ids,points,maximum_extra_nm=0,allow_locked_track_uuids=ids,
        reuse_retained_source=True,retained_path_only=True)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_saved_zero_emission_deletion_preserves_full_width_native_path_and_returns(tmp_path,quarter,mirror,layer):
    b,source,ids,keeper,diagonal,points=fixture(tmp_path,quarter,mirror,layer);raw=source.read_bytes()
    with pytest.raises(ValueError):owner.plan(b,ids,points,maximum_extra_nm=0,allow_locked_track_uuids=ids,reuse_retained_source=True)
    q=proposal(b,ids,points)
    assert not q['emitted_segments_nm'] and q['retained_path_only']
    assert set(q['retained_copper_reuse']['reused_native_uuids'])=={keeper,diagonal}
    assert not owner.materialize(b,q)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    r=owner.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'] and not r['errors'],r
    assert r['retained_path_only'] and not r['added_track_uuids'] and r['retired_track_uuids']==sorted(ids)
    assert r['exact_saved_source_subtract_add_and_ground_refill']['method']=='entire_native_source_subtraction_saved_tree_and_sidecars_equal'
    assert r['every_source_retained_contact_and_proved_ground_return_preserved'] and r['source_span_already_redundant_to_retained_native_copper']
    assert r['no_new_tracks_or_holes'] and r['saved_trace_length_nm']>4000000
    assert not r['current_qualified'] and not r['release_authority'] and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['thin','other_face','foreign','one_nm_off_line','missing_diagonal','missing_keeper','partial_emission','positive_extra','untyped','no_reuse'])
def test_zero_emission_is_not_permission_for_virtual_thin_or_incomplete_carriers(tmp_path,fault):
    b,source,ids,keeper,diagonal,points=fixture(tmp_path);live={force._uid(t):t for t in b.GetTracks()};extra=0;mode=True;reuse=True
    if fault=='thin':live[diagonal].SetWidth(199999)
    elif fault=='other_face':live[diagonal].SetLayer(pcbnew.B_Cu)
    elif fault=='foreign':
        net=pcbnew.NETINFO_ITEM(b,'UNRELATED');b.Add(net);live[diagonal].SetNet(net)
    elif fault=='one_nm_off_line':live[diagonal].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='missing_diagonal':b.Remove(live[diagonal])
    elif fault=='missing_keeper':b.Remove(live[keeper])
    elif fault=='partial_emission':live[diagonal].SetStart(pcbnew.VECTOR2I(*[(a+z)//2 for a,z in zip(points[0],points[1])]))
    elif fault=='positive_extra':extra=1
    elif fault=='untyped':mode=1
    else:reuse=False
    with pytest.raises(ValueError):owner.plan(b,ids,points,maximum_extra_nm=extra,allow_locked_track_uuids=ids,
        reuse_retained_source=reuse,retained_path_only=mode)


@pytest.mark.parametrize('fault',['extra_track','moved_keeper','thin_keeper','missing_keeper','pad','part_value','sidecar','plane','forged_flag','forged_path','forged_carrier'])
def test_zero_addition_receiver_still_replays_every_native_object_and_unknown_metadata(tmp_path,fault):
    b,source,ids,keeper,diagonal,points=fixture(tmp_path);q=proposal(b,ids,points);owner.materialize(b,q)
    if fault=='extra_track':track(b,'GND',(18,18),(19,18),width=.2)
    elif fault=='moved_keeper':next(t for t in b.GetTracks() if force._uid(t)==keeper).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='thin_keeper':next(t for t in b.GetTracks() if force._uid(t)==diagonal).SetWidth(199999)
    elif fault=='missing_keeper':b.Remove(next(t for t in b.GetTracks() if force._uid(t)==keeper))
    elif fault=='pad':next(p for f in b.GetFootprints() for p in f.Pads()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='part_value':next(iter(b.GetFootprints())).SetValue('unknown changed part')
    elif fault=='plane':next(iter(b.Zones())).UnFill()
    elif fault=='forged_flag':q=copy.deepcopy(q);q.pop('retained_path_only')
    elif fault=='forged_path':q=copy.deepcopy(q);q['replacement_points_nm'][1][0]+=1
    elif fault=='forged_carrier':q=copy.deepcopy(q);q['retained_copper_reuse']['reused_native_uuids']=['invented']
    child=force._copy_family(source,tmp_path/'hostile');field._save_field_snapshot(b,child)
    if fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    r=owner.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r


def test_even_a_complete_retained_surface_path_does_not_waive_actual_reference_planes(tmp_path):
    b,source,ids,keeper,diagonal,points=fixture(tmp_path,planes=False);q=proposal(b,ids,points);owner.materialize(b,q)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    r=owner.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and any('two_actual_saved_ground_reference_planes_required' in e for e in r['errors']),r


@pytest.mark.parametrize('quarter',[0,2])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_generic_endpoint_graph_and_real_native_stage_remove_visible_copper_without_new_tracks(tmp_path,quarter,layer):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    b,source,ids,keeper,diagonal,points=fixture(tmp_path,quarter=quarter,layer=layer);raw=source.read_bytes()
    r=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),allow_locked_source=True)
    assert r['ok'] and r['complete'] and r['changed'] and not r['errors'],r
    assert r['removed_trace_mm']>0 and r['new_tracks']==r['new_holes']==0 and not r['attempts'][-1]['new_native_fault_ids']
    assert r['source_family_and_code_unchanged'] and source.read_bytes()==raw and not r['release_authority']


@pytest.mark.parametrize('options',[dict(board_hint=''),dict(expected_source_sha256='x'*64),dict(reporting_build=None),
    dict(allow_locked_source=1),dict(max_trials=True),dict(max_trials=0),dict(max_trials=9)])
def test_invalid_or_unbounded_zero_emission_stage_cannot_create_any_output(tmp_path,options):
    args=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native');args.update(options)
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',tmp_path/'never',**args)
    assert not (tmp_path/'never').exists()


def pad_bridge_fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
    def point(p):
        x,y=p[0]-15000000,p[1]-15000000
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return (15000000+x,15000000+y)
    a=(10000000,10000000);centre=(9999999,10220800);end=(10862400,12090000);projected=(10000000,10220801)
    def part(ref,at,size):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue('native geometry only');b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(b.FindNet('GND'));p.SetPosition(pcbnew.VECTOR2I(*point(at)))
        p.SetSize(pcbnew.VECTOR2I(*size));p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);p.SetRoundRectRadiusRatio(.1)
        p.SetOrientationDegrees(quarter*90);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);ls=pcbnew.LSET();ls.AddLayer(layer);p.SetLayerSet(ls);fp.Add(p)
        return p
    portal=part('UNRELATED_PORTAL',centre,(560000,620000));part('UNRELATED_RETURN',end,(600000,450000))
    def edge(left,right):
        t=track(b,'GND',[x/1e6 for x in point(left)],[x/1e6 for x in point(right)],width=.2,layer=layer);t.SetLocked(True);return force._uid(t)
    incoming=edge((9400000,9400000),a)
    old=[edge(a,(10000000,11227600)),edge((10000000,11227600),end)]
    carriers=[edge(centre,(10862400,11083201)),edge((10862400,11083201),end)]
    via=pcbnew.PCB_VIA(b);via.SetNet(b.FindNet('GND'));via.SetPosition(pcbnew.VECTOR2I(*point(centre)))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(face);z.SetLocalClearance(200000);z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    source=tmp_path/'source.kicad_pcb';additive._ground_refill(b);field._save_field_snapshot(b,source)
    points=[list(point(p)) for p in (a,projected,(10862400,11083201),end)]
    cut=[t for t in b.GetTracks() if force._uid(t) in old]
    if points[0]!=list(owner._chain(cut)[0]):points.reverse()
    return b,source,old,points,force._uid(portal),incoming,carriers


def pad_proposal(b,ids,points):
    return owner.plan(b,ids,points,maximum_extra_nm=0,allow_locked_track_uuids=ids,reuse_retained_source=True,
        retained_path_only=True,retained_source_pad_portals=True)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_one_nm_export_difference_is_bridged_by_actual_full_width_land_not_snapping(tmp_path,quarter,mirror,layer):
    import cec_source_guided_ordinary_detour as exact
    b,source,ids,points,pad_uid,incoming,carriers=pad_bridge_fixture(tmp_path,quarter,mirror,layer);raw=source.read_bytes()
    with pytest.raises(ValueError):owner.plan(b,ids,points,maximum_extra_nm=0,allow_locked_track_uuids=ids,reuse_retained_source=True,retained_path_only=True)
    q=pad_proposal(b,ids,points)
    assert exact.length_terms(q['source_points_nm'])==exact.length_terms(q['replacement_points_nm'])
    assert q['native_solid_smd_pad_copper_witnesses'] and q['retained_source_pad_contact_covers']
    assert any(k['uuid']==incoming for w in q['native_solid_smd_pad_copper_witnesses'] for k in w['endpoint_disk_sources'])
    assert not owner.materialize(b,q)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    r=owner.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'] and not r['errors'],r
    assert not r['added_track_uuids'] and r['no_new_junction_or_current_rights_from_virtual_contacts']
    assert r['every_source_retained_contact_and_proved_ground_return_preserved'] and source.read_bytes()==raw
    assert not r['current_qualified'] and not r['release_authority']


@pytest.mark.parametrize('fault',['narrow_pad','foreign_pad','other_pad_face','plated_pad','DNP','custom_pad','thin_endpoint_kernel','one_nm_kernel_offset'])
def test_pad_portal_cannot_hide_a_narrow_neck_wrong_layer_hole_or_rounded_endpoint_gap(tmp_path,fault):
    b,source,ids,points,pad_uid,incoming,carriers=pad_bridge_fixture(tmp_path)
    pad=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==pad_uid);kernel=next(t for t in b.GetTracks() if force._uid(t)==incoming)
    if fault=='narrow_pad':pad.SetSize(pcbnew.VECTOR2I(50000,620000))
    elif fault=='foreign_pad':net=pcbnew.NETINFO_ITEM(b,'UNRELATED');b.Add(net);pad.SetNet(net)
    elif fault=='other_pad_face':ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(ls)
    elif fault=='plated_pad':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I(100000,100000));pad.SetLayerSet(pcbnew.PAD.PTHMask())
    elif fault=='DNP':pad.GetParentFootprint().SetDNP(True)
    elif fault=='custom_pad':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='thin_endpoint_kernel':kernel.SetWidth(199999)
    else:kernel.Move(pcbnew.VECTOR2I(1,0))
    with pytest.raises(ValueError):pad_proposal(b,ids,points)


@pytest.mark.parametrize('quarter',[0,2])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_discovery_derives_in_land_exact_lattice_projection_and_removes_the_detour(tmp_path,quarter,layer):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    b,source,ids,points,pad_uid,incoming,carriers=pad_bridge_fixture(tmp_path,quarter=quarter,layer=layer);raw=source.read_bytes()
    r=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),allow_locked_source=True)
    assert r['ok'] and r['complete'] and r['changed'] and not r['errors'],r
    assert r['removed_trace_mm']>2 and r['new_tracks']==r['new_holes']==0
    assert r['discovery']['exact_lattice_solid_native_smd_portals_not_coordinate_snapping']
    assert source.read_bytes()==raw and r['source_family_and_code_unchanged']
