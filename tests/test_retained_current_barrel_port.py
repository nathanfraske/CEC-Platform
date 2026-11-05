"""Native bore/land equivalence and saved reflow; no new hardware rating."""
import os,time
from pathlib import Path
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_path_finish as owner
import cec_full_current_path_stage as stage
import cec_retained_current_barrel_port as barrel
from test_full_current_path_finish import fixture as base_fixture
from test_full_current_terminal_trim import authority
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False,face=pcbnew.F_Cu,diameter=.6,drill=.3):
    source,net,ids,points=base_fixture(tmp_path,quarter,mirror,face,.2)
    b=pcbnew.LoadBoard(str(source));other=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    for fp in b.GetFootprints():
        for p in fp.Pads():ls=pcbnew.LSET();ls.AddLayer(other);p.SetLayerSet(ls)
    for t in b.GetTracks():
        if force._uid(t) not in ids:t.SetLayer(other)
    vias=[]
    for point in (points[0],points[-1]):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I(*point));v.SetNet(b.FindNet(net));v.SetWidth(round(diameter*1e6));v.SetDrill(round(drill*1e6))
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetLocked(True);b.Add(v);vias.append(force._uid(v))
    field._save_field_snapshot(b,source);return source,net,ids,points,vias


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('diameter,drill',[(.6,.3),(.35,.25)])
def test_saved_native_rotational_entry_keeps_the_literal_bore_and_existing_debt(tmp_path,quarter,mirror,face,diameter,drill):
    source,net,ids,points,vias=fixture(tmp_path,quarter,mirror,face,diameter,drill);initial=source.read_bytes()
    with authority(net,face):
        b=pcbnew.LoadBoard(str(source))
        with pytest.raises(ValueError):owner.plan(b,source,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True)
        p=owner.plan(b,source,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True,port_policy=barrel.POLICY)
        contacts=p['shape']['native_port_contacts'];assert len(contacts)==2 and {q['uuid'] for q in contacts}==set(vias)
        assert all(q['physical_annular_entry_congruent_under_centered_rotation'] and q['unchanged_bore_is_void_not_copper']
            and q['source_barrel_capacity_debt_not_qualified'] and not q['plating_current_thermal_and_fabrication_authority'] for q in contacts)
        made=owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        r=owner.receive(source,child,p,board_hint='synthetic')
    assert r['ok'] and r['complete'] and r['saved_trace_length_mm']==pytest.approx(4.),r
    assert source.read_bytes()==initial and r['new_vias']==r['new_holes']==r['pads_moved']==0 and not r['current_qualified']


@pytest.mark.parametrize('fault',['offset_port','short_new_launch','short_old_launch','drill_larger_than_land','group','partial_span','backdrill','compound_pad','interior_barrel'])
def test_barrel_policy_does_not_own_padstacks_side_taps_or_grazing_void_contacts(tmp_path,fault):
    source,net,ids,points,vias=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));v=next(t for t in b.GetTracks() if force._uid(t)==vias[0])
    if fault=='offset_port':v.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='short_new_launch':points.insert(1,[points[0][0]+50000,points[0][1]])
    elif fault=='short_old_launch':
        edge=next(t for t in b.GetTracks() if force._uid(t) in ids and tuple(v.GetPosition()) in (tuple(t.GetStart()),tuple(t.GetEnd())))
        near=pcbnew.VECTOR2I(points[0][0]+50000,points[0][1])
        far=edge.GetEnd() if edge.GetStart()==v.GetPosition() else edge.GetStart();middle=next(t for t in b.GetTracks() if force._uid(t) in ids and force._uid(t)!=force._uid(edge) and tuple(far) in (tuple(t.GetStart()),tuple(t.GetEnd())))
        if edge.GetStart()==v.GetPosition():edge.SetEnd(near)
        else:edge.SetStart(near)
        if middle.GetStart()==far:middle.SetStart(near)
        else:middle.SetEnd(near)
    elif fault=='drill_larger_than_land':v.SetDrill(700000)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(v)
    elif fault=='partial_span':v.SetViaType(pcbnew.VIATYPE_BLIND);v.SetLayerPair(pcbnew.F_Cu,pcbnew.In2_Cu)
    elif fault=='backdrill':
        v.SetBackdrillMode(pcbnew.BACKDRILL_MODE_BACKDRILL_TOP);v.SetTopBackdrillLayer(pcbnew.In2_Cu);v.SetTopBackdrillSize(pcbnew.FromMM(.45))
    elif fault=='compound_pad':
        f=pcbnew.FOOTPRINT(b);f.SetReference('COMPOUND');p=pcbnew.PAD(f);p.SetPosition(v.GetPosition());p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetSize(pcbnew.VECTOR2I_MM(.8,.8));ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls);p.SetNet(b.FindNet(net));f.Add(p);b.Add(f)
    else:v.SetPosition(pcbnew.VECTOR2I_MM(20,18))
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    with authority(net):
        with pytest.raises((ValueError,barrel.native.Unknown)):
            owner.plan(b,source,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True,port_policy=barrel.POLICY)


@pytest.mark.parametrize('fault',['via_moved','via_width','via_drill','witness','policy'])
def test_saved_native_receiving_rederives_every_barrel_and_policy(tmp_path,fault):
    source,net,ids,points,vias=fixture(tmp_path)
    with authority(net):
        b=pcbnew.LoadBoard(str(source));p=owner.plan(b,source,board_hint='synthetic',retired_track_uuids=ids,points_nm=points,allow_locked_source=True,port_policy=barrel.POLICY)
        owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');v=next(t for t in b.GetTracks() if force._uid(t)==vias[0])
        if fault=='via_moved':v.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='via_width':v.SetWidth(601000)
        elif fault=='via_drill':v.SetDrill(301000)
        elif fault=='witness':p['shape']['native_port_contacts'][0]['actual_bore_diameter_nm']+=1
        else:p['port_policy']='tracks_only'
        field._save_field_snapshot(b,child);r=owner.receive(source,child,p,board_hint='synthetic')
    assert not r['ok'] and r['errors'] and not r['release_authority'],r


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_uncapped_native_barrel_campaign_stops_and_keeps_zero_opens(tmp_path,face):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    source,net,ids,points,vias=fixture(tmp_path,face=face)
    with authority(net,face):
        r=stage.run_campaign(source,tmp_path/'campaign',board_hint='synthetic',expected_source_sha256=force._hash(source),
            reporting_build=Path(native),allow_locked_source=True,port_policy=barrel.POLICY,max_passes=2)
    assert r['ok'] and r['complete'] and r['changed'] and len(r['phase_receipts'])==1,r
    assert not r['whole_board_cleanliness_or_no_path_proof'] and not r['fab_ready']


def segmented_fixture(tmp_path,quarter=0,mirror=False,face=pcbnew.F_Cu):
    source,net,ids,unused,vias=fixture(tmp_path,quarter,mirror,face)
    b=pcbnew.LoadBoard(str(source));owner.discard_items(b,[t for t in b.GetTracks() if force._uid(t) in ids])
    def pose(p):
        x,y=p[0]-20,p[1]-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return (20+x,20+y)
    # The first 0.1 mm stroke and its following diagonal both touch the
    # annulus. They must survive literally, not be silently rotated or lost.
    old=[pose(p) for p in [(16,20),(16.1,20),(18,18.1),(20,18.1),(22,20.1),(24,20.1),(24,24)]]
    ids=[]
    for a,z in zip(old,old[1:]):
        t=track(b,net,a,z,layer=face,width=.2);t.SetLocked(True);ids.append(force._uid(t))
    points=[[round(x*1e6),round(y*1e6)] for x,y in [pose(p) for p in [(16,20),(16.1,20),(18,18.1),(20,18.1),(24,22.1),(24,24)]]]
    field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));cut=[t for t in b.GetTracks() if force._uid(t) in ids]
    if points[0]!=list(owner.chain._chain(cut)[0]):points.reverse()
    return source,net,ids,points,vias


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_saved_native_segmented_annular_escape_is_protected_not_assumed_rotatable(tmp_path,quarter,mirror,face):
    source,net,ids,points,vias=segmented_fixture(tmp_path,quarter,mirror,face);initial=source.read_bytes()
    with authority(net,face):
        b=pcbnew.LoadBoard(str(source));p=owner.plan(b,source,board_hint='synthetic',retired_track_uuids=ids,
            points_nm=points,allow_locked_source=True,port_policy=barrel.POLICY)
        records=[r for r in p['shape']['native_port_contacts'] if r['source_contact']['method']=='identical_actual_native_annular_escape_fragments']
        assert len(records)==1 and len(records[0]['source_contact']['stroke_geometry_nm'])==2
        assert records[0]['source_contact']==records[0]['candidate_contact']
        cut=[t for t in b.GetTracks() if force._uid(t) in ids];old=[list(q) for q in owner.chain._chain(cut)]
        contacts=owner._contacts(b,cut,old,time.monotonic()+10.,barrel.POLICY)
        v=next(t for t in b.GetTracks() if force._uid(t)==records[0]['uuid'])
        paths=owner._candidate_paths(b,cut,old,contacts,barrel.POLICY,time.monotonic()+10.)
        assert any(barrel.contact_strokes(v,face,path,200000,time.monotonic()+10.)==records[0]['source_contact']['stroke_geometry_nm'] for path in paths)
        owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        r=owner.receive(source,child,p,board_hint='synthetic')
    assert r['ok'] and r['complete'] and r['native_strokes_before_after']==[6,5],r
    assert r['saved_trace_length_mm']>1. and r['new_vias']==r['new_holes']==0 and source.read_bytes()==initial


@pytest.mark.parametrize('fault',['escape_changed','extra_annular_touch','hole_only'])
def test_literal_escape_witness_cannot_count_drill_void_or_accept_different_fragments(tmp_path,fault):
    source,net,ids,points,vias=segmented_fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    v=next(t for t in b.GetTracks() if force._uid(t)==vias[0]);cut=[t for t in b.GetTracks() if force._uid(t) in ids]
    old=[list(q) for q in owner.chain._chain(cut)]
    if fault=='escape_changed':points[1][0]+=1
    elif fault=='extra_annular_touch':points.insert(-1,[16050000,20050000])
    else:old=points=[[16000000,20000000],[16010000,20000000]]
    with pytest.raises(ValueError):barrel.contact(b,v,pcbnew.F_Cu,old,points,200000,time.monotonic()+10.)


@pytest.mark.parametrize('value',[None,True,[],{},'unknown'])
@pytest.mark.parametrize('operation',[stage.run,stage.run_campaign])
def test_unknown_or_untyped_barrel_policy_is_refused_before_creating_outputs(tmp_path,value,operation):
    with pytest.raises(ValueError):operation(tmp_path/'missing',tmp_path/'never',board_hint='synthetic',
        expected_source_sha256='0'*64,reporting_build=tmp_path/'native',port_policy=value)
    assert not (tmp_path/'never').exists()


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_discovery_retains_short_escape_and_receives_actual_zero_open_candidate(tmp_path,face):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    source,net,ids,points,vias=segmented_fixture(tmp_path,face=face)
    with authority(net,face):
        r=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
            reporting_build=Path(native),allow_locked_source=True,port_policy=barrel.POLICY)
    assert r['ok'] and r['complete'] and r['changed'] and not r['attempts'][0]['new_native_fault_ids'],r
    assert r['independent_saved_receiving']['new_holes']==0 and r['saved_trace_length_mm']>0
