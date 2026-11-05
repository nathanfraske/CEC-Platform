"""Native pad-corner geometry and source-role tests; no hardware load guesses."""
import copy
import os
from pathlib import Path
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_pad_corner as owner
import cec_ordinary_pad_corner_stage as stage
import cec_native_scalar_corner_scope as legacy
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,*,quarter=0,mirror=False,face=pcbnew.F_Cu,width=.2,net='/renamed/SIGNAL'):
    def pose(p):
        x,y=p[0]-20,p[1]-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return 20+x,20+y
    points=[pose(p) for p in ((18,20),(20,20),(20,22))];anchor=pose((19.75,20))
    b=_board([(*points[0],net),(*points[-1],net),(*anchor,net)],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers);p.SetOrientationDegrees(quarter*90)
            if fp.GetReference()=='X3':p.SetSize(pcbnew.VECTOR2I_MM(.6,.64));p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    for a,z in zip(points,points[1:]):track(b,net,a,z,layer=face,width=width).SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    return source,net


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('width',[.15,.2,.3])
def test_saved_contact_aware_miters_preserve_every_native_anchor_web(tmp_path,quarter,mirror,face,width):
    source,net=fixture(tmp_path,quarter=quarter,mirror=mirror,face=face,width=width)
    original=source.read_bytes();b=pcbnew.LoadBoard(str(source))
    assert not legacy.select(b,{net})['selected']
    discovery=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)
    assert len(discovery['requests'])==1,discovery
    proposal=owner.plan(b,source,discovery['requests'],board_hint='synthetic',allow_locked_source=True)
    assert all(c['native_source_contacts']['ok'] for c in proposal['corners'])
    for c in proposal['corners']:
        assert all(c['new_native_anchor_contact_radius_nm'][u]>=r>0 for u,r in c['old_native_anchor_contact_radius_nm'].items())
    made=owner.materialize(b,source,proposal,board_hint='synthetic')
    candidate=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(b,candidate)
    r=owner.receive(source,candidate,proposal,board_hint='synthetic')
    assert r['ok'] and r['complete'] and r['corners']==1,r
    assert r['saved_trace_length_mm']>0 and r['native_anchor_contact_radius_non_decreasing']
    assert r['new_vias']==r['new_holes']==r['pads_moved']==0 and not r['ordinary_role_override']
    assert len(made['retired_track_uuids'])==2 and len(made['added_native_uuids'])==3
    assert r['default_pad_and_via_launch_protection_unchanged'] and not r['release_authority']
    assert source.read_bytes()==original
    saved=pcbnew.LoadBoard(str(candidate))
    assert all(t.GetWidth()==round(width*1e6) and t.GetLayer()==face and t.IsLocked() for t in saved.GetTracks())


@pytest.mark.parametrize('fault',['power','ground','sense','clock','mask','group','drilled_pad','DNP','unsupported_pad',
    'locked','mixed_width','non45','interior_tee','compound_barrel','sensitive_gpio_role'])
def test_source_roles_and_immutable_contacts_are_not_silently_relaxed(tmp_path,fault,monkeypatch):
    source,net=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));tracks=list(b.GetTracks());fp=b.FindFootprintByReference('X3');pad=next(iter(fp.Pads()))
    if fault=='power':pad.SetPinType('power_in')
    elif fault=='ground':
        b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
        for t in tracks:t.SetNet(b.FindNet('GND'))
        for f in b.GetFootprints():
            for p in f.Pads():p.SetNet(b.FindNet('GND'))
    elif fault in ('sense','clock','sensitive_gpio_role'):
        monkeypatch.setattr(owner.ordinary,'eligible_nets',lambda *a,**k:set())
    elif fault=='mask':tracks[0].SetHasSolderMask(True)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(tracks[0])
    elif fault=='drilled_pad':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=='DNP':fp.SetDNP(True)
    elif fault=='unsupported_pad':pad.SetShape(pcbnew.PAD_SHAPE_TRAPEZOID)
    elif fault=='mixed_width':tracks[0].SetWidth(300000)
    elif fault=='non45':tracks[0].SetStart(pcbnew.VECTOR2I(18000000,20000001))
    elif fault=='interior_tee':track(b,net,(19,20),(21,20))
    elif fault=='compound_barrel':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetPosition(pad.GetPosition());v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source));before=source.read_bytes()
    r=owner.discover(b,source,board_hint='synthetic',allow_locked_source=fault!='locked')
    assert not r['requests'] and source.read_bytes()==before,r


@pytest.mark.parametrize('tamper',['narrow','layer','pad','sidecar','via','unowned_track','source_request','contact_witness'])
def test_exact_saved_receiver_rejects_changed_source_or_added_authority(tmp_path,tamper):
    source,net=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    rows=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)['requests']
    proposal=owner.plan(b,source,rows,board_hint='synthetic',allow_locked_source=True)
    owner.materialize(b,source,proposal,board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'child')
    if tamper=='narrow':next(iter(b.GetTracks())).SetWidth(199999)
    elif tamper=='layer':next(iter(b.GetTracks())).SetLayer(pcbnew.B_Cu)
    elif tamper=='pad':b.FindFootprintByReference('X3').Move(pcbnew.VECTOR2I(1,0))
    elif tamper=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif tamper=='via':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetPosition(pcbnew.VECTOR2I_MM(19,20));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif tamper=='unowned_track':track(b,'/OTHER',(30,30),(31,30))
    elif tamper=='source_request':proposal['requests'][0]['at_nm'][0]+=1
    else:proposal['corners'][0]['new_native_anchor_contact_radius_nm']={}
    field._save_field_snapshot(b,child);r=owner.receive(source,child,proposal,board_hint='synthetic')
    assert not r['ok'] and r['errors'] and not r['release_authority'],r


@pytest.mark.parametrize('kwargs',[dict(allow_locked_source=1),dict(max_trials=0),dict(max_trials=17),dict(max_trials=True),dict(expected_source_sha256='bad')])
def test_invalid_stage_context_never_creates_a_family(tmp_path,kwargs):
    args=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native');args.update(kwargs)
    out=tmp_path/'never-created'
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',out,**args)
    assert not out.exists()


def test_portfolio_refuses_grazing_capture_even_when_simple_adjacency_survives(tmp_path):
    source,net=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    rows=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)['requests']
    proposal=owner.plan(b,source,rows,board_hint='synthetic',allow_locked_source=True)
    corner=proposal['corners'][0]
    assert any(t.get('refusal')=='native_pad_contact_web_would_shrink' for t in corner['trials'])
    assert corner['trials'][-1]['accepted']
    assert corner['native_source_contacts']['ok'] and corner['actual_visible_native_material_removed']['ok']


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
def test_corner_wholly_inside_actual_fixed_pad_is_purposeful_not_a_missing_mutation(tmp_path,quarter,mirror):
    source,net=fixture(tmp_path,quarter=quarter,mirror=mirror)
    b=pcbnew.LoadBoard(str(source));p=next(iter(b.FindFootprintByReference('X3').Pads()))
    p.SetSize(pcbnew.VECTOR2I_MM(.9,.9));field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    old=source.read_bytes();r=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)
    assert not r['requests'] and len(r['purposeful_fixed_pad_corners'])==1
    assert r['purposeful_fixed_pad_corners'][0]['complete_native_corner_cap_inside_actual_fixed_pad_copper']
    assert source.read_bytes()==old


def test_two_disjoint_nets_are_replayed_as_one_exact_ordinary_pad_batch(tmp_path):
    b=_board([],edge=(0,0,45,45));b.SetCopperLayerCount(6)
    for i,(net,c) in enumerate((('/SIG_A',12),('/SIG_B',30))):
        for j,at in enumerate(((c-2,c),(c,c+2),(c-.25,c))):
            f=pcbnew.FOOTPRINT(b);f.SetReference('P'+str(i*3+j));f.SetPosition(pcbnew.VECTOR2I_MM(*at))
            p=pcbnew.PAD(f);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetSize(pcbnew.VECTOR2I_MM(.6,.64));p.SetPosition(f.GetPosition());ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls)
            if net not in b.GetNetsByName():b.Add(pcbnew.NETINFO_ITEM(b,net))
            p.SetNet(b.FindNet(net));f.Add(p);b.Add(f)
        track(b,net,(c-2,c),(c,c)).SetLocked(True);track(b,net,(c,c),(c,c+2)).SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    rows=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)['requests'];assert len(rows)==2
    proposal=owner.plan(b,source,rows,board_hint='synthetic',allow_locked_source=True)
    made=owner.materialize(b,source,proposal,board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(b,child)
    r=owner.receive(source,child,proposal,board_hint='synthetic')
    assert r['ok'] and r['complete'] and r['corners']==2,r
    assert len(made['retired_track_uuids'])==4 and len(made['added_native_uuids'])==6


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('quarter',[0,2])
def test_full_native_stage_keeps_zero_opens_and_original_pad_pose(tmp_path,face,quarter):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    source,net=fixture(tmp_path,face=face,quarter=quarter);before=source.read_bytes()
    result=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),allow_locked_source=True)
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['corners']==1 and result['source_family_and_code_unchanged']
    assert result['independent_saved_receiving']['native_anchor_contact_radius_non_decreasing']
    assert all(r['ok'] and r['complete'] and not r['native_inventory']['potentially_truncated'] for r in result['native_producers'].values())
    assert not result['attempts'][0]['new_native_fault_ids'] and source.read_bytes()==before
