"""Sensitive scalar ownership never turns into ordinary/power/pair permission."""
import copy
import os
from pathlib import Path

import pcbnew
import wx
import pytest
import cec_sensitive_scalar_corner_stage as stage
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_field_proposals import track
from test_scalar_acute_stage import fixture as acute
quiet=wx.LogNull()


def fixture(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu,net='/renamed/ADC_INPUT'):
    b,net,tracks,at=acute(angle,mirror,layer,net=net)
    fp=b.FindFootprintByReference('X1');fp.SetValue('ESP32-C6-MINI-1-N4')
    fp.SetFPID(pcbnew.LIB_ID('RF_Module','ESP32-C6-MINI-1'))
    fp.SetField('MPN','ESP32-C6-MINI-1-N4')
    next(iter(fp.Pads())).SetNumber('5')
    # Explicit minimal API fixture with the manufacturer's scalar pin role;
    # not a qualified physical module footprint or a real-board load estimate.
    for t in tracks:t.SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    return b,source,tracks,fp,net


def saved(tmp_path,**kwargs):
    b,source,tracks,fp,net=fixture(tmp_path,**kwargs)
    # The saved source, not an unparsed builder's field offsets, is the
    # immutable transaction oracle. Reload before doing the private mutation.
    b=pcbnew.LoadBoard(str(source))
    inv=stage.inventory(b,source,'synthetic');assert len(inv['selected'])==1,inv
    proposal=stage.geometry._construct_acute(b,inv['selected'],deadline=stage.time.monotonic()+10.)
    assert proposal['chamfered']==1,proposal
    child=force._copy_family(source,tmp_path/'child');stage.additive._ground_refill(b)
    field._save_field_snapshot(b,child)
    return source,child,proposal,net


def saved_right_angle(tmp_path,**kwargs):
    b,source,tracks,fp,net=fixture(tmp_path,**kwargs)
    # Reuse the rotated/mirrored source endpoints. The old acute terminal
    # offset is exactly one tenth of the cardinal offset to the new elbow.
    corner=tracks[0].GetEnd();terminal=tracks[1].GetEnd()
    at=pcbnew.VECTOR2I(corner.x+10*(terminal.x-corner.x),corner.y+10*(terminal.y-corner.y))
    tracks[0].SetEnd(at);tracks[1].SetStart(at)
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    inv=stage.inventory(b,source,'synthetic',geometry_policy='right_angle_chamfer')
    assert len(inv['selected'])==1,inv
    proposal=stage.geometry.construct(b,inv['selected'],set(inv['source_sensitive_scalar_witnesses']),
        geometry_policy='right_angle_chamfer',allow_locked_source=True)
    assert proposal['chamfered']==1,proposal
    child=force._copy_family(source,tmp_path/'right-angle-child');stage.additive._ground_refill(b)
    field._save_field_snapshot(b,child)
    return source,child,proposal,net


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_saved_sensitive_right_angle_uses_same_role_and_all_independent_receivers(tmp_path,angle,mirror,layer):
    source,child,proposal,net=saved_right_angle(tmp_path,angle=angle,mirror=mirror,layer=layer)
    before=(source.read_bytes(),child.read_bytes())
    r=stage.receive(source,child,proposal['retired_track_uuids'],board_hint='synthetic',
        allow_locked_source=True,geometry_policy='right_angle_chamfer')
    assert r['ok'] and r['complete'],r
    assert r['selected_geometry_findings_before_after']==[1,0]
    assert r['geometry_policy']=='right_angle_chamfer' and r['shortened_centerline_mm']>.1
    assert len(r['retired_track_uuids'])==2 and len(r['added_native_uuids'])==3
    assert r['physical_kelvin_preservation']['same_evidence'] and r['native_source_contact_preservation']['ok']
    assert not r['ordinary_reclassification'] and not r['GPIO_application_mode_or_current_authority_assumed']
    assert not r['current_qualified'] and not r['fab_ready'] and not r['release_authority']
    assert before==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('fault',['implicit_policy','unknown_policy','power_pin','lock','wrong_cut',
    'width','other_layer','extra_via','part_pose','sidecar','current_unknown','new_field','cut_unknown'])
def test_right_angle_mode_is_not_a_sensitive_or_power_waiver(tmp_path,monkeypatch,fault):
    source,child,proposal,net=saved_right_angle(tmp_path)
    retired=proposal['retired_track_uuids'];params=dict(geometry_policy='right_angle_chamfer',allow_locked_source=True)
    if fault=='implicit_policy':params.pop('geometry_policy')
    elif fault=='unknown_policy':params['geometry_policy']='force-anything'
    elif fault=='lock':params['allow_locked_source']=False
    elif fault=='wrong_cut':retired=['unknown',retired[1]]
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='current_unknown':monkeypatch.setattr(stage.current,'receive',lambda *a,**k:dict(ok=True,complete=False))
    elif fault=='new_field':
        monkeypatch.setattr(stage.field,'field_coupling_summary',lambda p,**k:dict(child=Path(p)==child))
        monkeypatch.setattr(stage.field,'blocker_keys',lambda q:{'new'} if q['child'] else set())
    elif fault=='cut_unknown':monkeypatch.setattr(stage.sense,'compare_contour_preservation',
        lambda *a,**k:dict(same_evidence=True,comparison_complete=False))
    else:
        b=pcbnew.LoadBoard(str(source if fault=='power_pin' else child))
        t=next(iter(b.GetTracks()))
        if fault=='power_pin':next(iter(b.FindFootprintByReference('X1').Pads())).SetPinType('power_in')
        elif fault=='width':t.SetWidth(199999)
        elif fault=='other_layer':t.SetLayer(pcbnew.B_Cu)
        elif fault=='extra_via':
            v=pcbnew.PCB_VIA(b);v.SetNet(t.GetNet());v.SetPosition(t.GetStart());v.SetWidth(600000)
            v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        elif fault=='part_pose':b.FindFootprintByReference('X1').Move(pcbnew.VECTOR2I(1,0))
        field._save_field_snapshot(b,source if fault=='power_pin' else child)
    r=stage.receive(source,child,retired,board_hint='synthetic',**params)
    assert not r['ok'] and not r['complete'] and r['errors'],r
    assert not r['ordinary_reclassification'] and not r['release_authority']


def saved_right_angle_batch(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu):
    b,source,old,fp,net=fixture(tmp_path,angle=angle,mirror=mirror,layer=layer)
    def at(x,y):
        x,y=round((x-20)*1e6),round((y-20)*1e6)
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return ((20000000+x)/1e6,(20000000+y)/1e6)
    discard_items(b,old)
    endpoint=b.FindFootprintByReference('X2');endpoint.SetPosition(pcbnew.VECTOR2I_MM(*at(25,30)))
    points=[at(*p) for p in ((15,15),(20,15),(20,25),(25,25),(25,30))]
    edges=[track(b,net,s,z,layer=layer,width=.2) for s,z in zip(points,points[1:])]
    for t in edges:t.SetLocked(True)
    scopes=[sorted(force._uid(edges[i]) for i in indexes) for indexes in ((0,1),(2,3))]
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    inv=stage.inventory(b,source,'synthetic',geometry_policy='right_angle_chamfer')
    by_scope={tuple(q['source_track_uuids']):q for q in inv['selected']}
    requests=[by_scope[tuple(s)] for s in scopes]
    proposal=stage.geometry.construct(b,requests,set(inv['source_sensitive_scalar_witnesses']),
        geometry_policy='right_angle_chamfer',allow_locked_source=True)
    assert proposal['chamfered']==2,proposal
    child=force._copy_family(source,tmp_path/'batch-child');stage.additive._ground_refill(b)
    field._save_field_snapshot(b,child)
    return source,child,proposal,scopes


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_disjoint_sensitive_corner_batch_replays_adjacent_source_chain(tmp_path,angle,mirror,layer):
    source,child,proposal,scopes=saved_right_angle_batch(tmp_path,angle,mirror,layer)
    before=(source.read_bytes(),child.read_bytes())
    r=stage.receive(source,child,proposal['retired_track_uuids'],board_hint='synthetic',allow_locked_source=True,
        geometry_policy='right_angle_chamfer',max_batch_corners=2,source_corner_scopes=scopes)
    assert r['ok'] and r['complete'],r
    assert r['received_source_corner_count']==2 and r['selected_geometry_findings_before_after']==[3,1]
    assert len(r['retired_track_uuids'])==4 and len(r['added_native_uuids'])==6
    assert r['physical_kelvin_preservation']['same_evidence'] and not r['ordinary_reclassification']
    assert before==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('fault',['implicit_batch','no_scopes','overlapping_scopes','wrong_scopes','missing_scope',
    'bad_bound','boolean_bound','large_bound','acute_batch','unknown_current','unknown_cut'])
def test_sensitive_batch_cannot_own_ambiguous_or_unbounded_source_material(tmp_path,monkeypatch,fault):
    source,child,proposal,scopes=saved_right_angle_batch(tmp_path)
    params=dict(geometry_policy='right_angle_chamfer',max_batch_corners=2,source_corner_scopes=scopes)
    if fault=='implicit_batch':params.pop('max_batch_corners')
    elif fault=='no_scopes':params.pop('source_corner_scopes')
    elif fault=='overlapping_scopes':params['source_corner_scopes']=[scopes[0],scopes[0]]
    elif fault=='wrong_scopes':params['source_corner_scopes']=[scopes[0],['foreign','unknown']]
    elif fault=='missing_scope':params['source_corner_scopes']=[scopes[0]]
    elif fault=='bad_bound':params['max_batch_corners']=0
    elif fault=='boolean_bound':params['max_batch_corners']=True
    elif fault=='large_bound':params['max_batch_corners']=9
    elif fault=='acute_batch':params['geometry_policy']='acute_shortcut'
    elif fault=='unknown_current':monkeypatch.setattr(stage.current,'receive',lambda *a,**k:dict(ok=True,complete=False))
    elif fault=='unknown_cut':monkeypatch.setattr(stage.sense,'compare_contour_preservation',
        lambda *a,**k:dict(same_evidence=True,comparison_complete=False))
    r=stage.receive(source,child,proposal['retired_track_uuids'],board_hint='synthetic',allow_locked_source=True,**params)
    assert not r['ok'] and not r['complete'] and r['errors'],r


def test_sensitive_right_angle_must_change_actual_full_width_copper_not_only_centerline(tmp_path):
    source,child,proposal,net=saved_right_angle(tmp_path)
    b=pcbnew.LoadBoard(str(source))
    inv=stage.inventory(b,source,'synthetic',geometry_policy='right_angle_chamfer')
    tiny=stage.geometry.construct(b,inv['selected'],set(inv['source_sensitive_scalar_witnesses']),
        geometry_policy='right_angle_chamfer',allow_locked_source=True,minimum_nm=50000,maximum_nm=50000)
    assert tiny['chamfered']==1
    stage.additive._ground_refill(b);field._save_field_snapshot(b,child)
    r=stage.receive(source,child,tiny['retired_track_uuids'],board_hint='synthetic',allow_locked_source=True,
        geometry_policy='right_angle_chamfer')
    assert not r['ok'] and not r['complete'] and r['errors'],r


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_saved_rotated_mirrored_sensitive_scalar_has_no_mode_or_current_inference(tmp_path,angle,mirror,layer):
    source,child,proposal,net=saved(tmp_path,angle=angle,mirror=mirror,layer=layer)
    before=(source.read_bytes(),child.read_bytes())
    r=stage.receive(source,child,proposal['retired_track_uuids'],board_hint='synthetic',allow_locked_source=True)
    assert r['ok'] and r['complete'],r
    assert r['source_width_nm']==200000 and r['shortened_centerline_mm']>0
    assert r['source_pin_witnesses'][0]['manufacturer_pin']['function']=='IO2'
    assert not r['ordinary_reclassification'] and not r['GPIO_application_mode_or_current_authority_assumed']
    assert not r['current_qualified'] and not r['release_authority']
    assert r['native_source_contact_preservation']['ok'] and r['physical_kelvin_preservation']['same_evidence']
    assert before==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('fault',['unknown_model','wrong_package','wrong_display','USB_pin','duplicate_pin','DNP',
    'drilled_gpio','power_pin_type','power_model','domain','budget','coupled_pair','analog_pair','unresolved_monitor',
    'owned_zone','not_sensitive','clock','power_name','reference_plane'])
def test_source_semantics_cannot_be_waived_by_a_sense_spelling(tmp_path,monkeypatch,fault):
    rename={'not_sensitive':'/renamed/CONTROL','clock':'/renamed/ADC_CLK','power_name':'/renamed/ADC_VDD'}
    b,source,tracks,fp,net=fixture(tmp_path,net=rename.get(fault,'/renamed/ADC_INPUT'))
    pad=next(iter(fp.Pads()))
    if fault=='unknown_model':fp.SetValue('unselected');fp.SetField('MPN','unselected')
    elif fault=='wrong_package':fp.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8'))
    elif fault=='wrong_display':fp.SetValue('OTHER_DEVICE')
    elif fault=='USB_pin':pad.SetNumber('18')
    elif fault=='duplicate_pin':duplicate=pad.Duplicate();duplicate.m_Uuid.Clone(pcbnew.KIID());fp.Add(duplicate)
    elif fault=='DNP':fp.SetDNP(True)
    elif fault=='drilled_gpio':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=='power_pin_type':pad.SetPinType('power_in')
    elif fault=='power_model':monkeypatch.setattr(stage.roles,'footprint_contract',lambda _fp:dict(pins={'5':'power_input'}))
    elif fault=='domain':monkeypatch.setattr(stage.topology,'board_current_domains',lambda *a,**k:{net:dict(complete=True)})
    elif fault=='budget':monkeypatch.setattr(stage.synth,'spec_net_current_contract',lambda *a,**k:dict(amps=.001))
    elif fault=='coupled_pair':monkeypatch.setattr(stage.precision,'derive_coupled_pairs',lambda *a,**k:[dict(p=net,n='/mate')])
    elif fault=='analog_pair':monkeypatch.setattr(stage.semantics,'analog_input_pairs',lambda *a:[dict(p=net,n='/mate')])
    elif fault=='unresolved_monitor':monkeypatch.setattr(stage.semantics,'unresolved_current_monitor_nets',lambda *a:{net})
    elif fault=='owned_zone':z=pcbnew.ZONE(b);z.SetNet(tracks[0].GetNet());z.SetLayer(pcbnew.F_Cu);b.Add(z)
    elif fault=='reference_plane':
        for t in tracks:t.SetLayer(pcbnew.In1_Cu)
    before=field._field_snapshot_inventory(b)
    assert not stage.inventory(b,source,'synthetic')['selected']
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['locked','duplicate','wrong_cut','width','face','mask','group','other_net',
    'moved_pad','added_via','metadata','sidecar','changed_pin','current_unknown','field','absolute_unknown'])
def test_exact_source_saved_delta_and_other_receivers_remain_independent(tmp_path,monkeypatch,fault):
    source,child,proposal,net=saved(tmp_path);retired=proposal['retired_track_uuids'];unlock=True
    if fault=='locked':unlock=False
    elif fault=='duplicate':retired=[retired[0]]*2
    elif fault=='wrong_cut':retired=['not-source',retired[1]]
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='current_unknown':monkeypatch.setattr(stage.current,'receive',lambda *a,**k:dict(ok=True,complete=False))
    elif fault=='field':
        monkeypatch.setattr(stage.field,'field_coupling_summary',lambda p,**k:dict(candidate=Path(p)==child))
        monkeypatch.setattr(stage.field,'blocker_keys',lambda r:{'new'} if r['candidate'] else set())
    elif fault=='absolute_unknown':
        monkeypatch.setattr(stage.sense,'compare_contour_preservation',lambda *a,**k:dict(comparison_complete=False,same_evidence=True))
    else:
        b=pcbnew.LoadBoard(str(child));t=next(iter(b.GetTracks()))
        if fault=='width':t.SetWidth(199999)
        elif fault=='face':t.SetLayer(pcbnew.B_Cu)
        elif fault=='mask':t.SetHasSolderMask(True)
        elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
        elif fault=='other_net':other=pcbnew.NETINFO_ITEM(b,'/OTHER');b.Add(other);t.SetNet(other)
        elif fault=='moved_pad':next(iter(next(iter(b.GetFootprints())).Pads())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='added_via':
            v=pcbnew.PCB_VIA(b);v.SetNet(t.GetNet());v.SetPosition(t.GetStart());v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            v.SetWidth(600000);v.SetDrill(300000);b.Add(v)
        elif fault=='metadata':b.SetCopperLayerCount(4)
        elif fault=='changed_pin':next(iter(b.FindFootprintByReference('X1').Pads())).SetNumber('18')
        if fault=='other_net':
            # A foreign short can be relabeled by native LoadBoard. The
            # ordinary snapshot boundary rightly refuses that round trip;
            # also present the raw external file to the saved delta receiver.
            pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),b)
        else:field._save_field_snapshot(b,child)
    r=stage.receive(source,child,retired,board_hint='synthetic',allow_locked_source=unlock)
    assert not r['ok'] and not r['complete'] and r['errors'],r
    assert not r['release_authority'] and not r['ordinary_reclassification']


@pytest.mark.parametrize('kwargs',[dict(board_hint=''),dict(expected_source_sha256='bad'),dict(max_requests=0),
    dict(max_requests=True),dict(allow_locked_source=1),dict(reporting_build=None),dict(sense_timeout_s=61)])
def test_invalid_context_creates_no_candidate(tmp_path,kwargs):
    params=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native')
    params.update(kwargs);out=tmp_path/'not-created'
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',out,**params)
    assert not out.exists()


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('geometry_policy',['acute_shortcut','right_angle_chamfer'])
def test_complete_native_stage_is_zero_open_without_sensitive_role_override(tmp_path,layer,geometry_policy):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    if geometry_policy=='right_angle_chamfer':source,child,proposal,net=saved_right_angle(tmp_path,layer=layer)
    else:b,source,tracks,fp,net=fixture(tmp_path,layer=layer)
    before=source.read_bytes()
    r=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),allow_locked_source=True,max_requests=1,geometry_policy=geometry_policy)
    assert r['ok'] and r['complete'] and r['changed'],r
    assert not r['after']['selected'] and r['source_family_and_code_unchanged']
    assert r['independent_sensitive_receiving']['ok'] and not r['ordinary_reclassification']
    assert not r['routing_admitted'] and not r['fab_ready'] and source.read_bytes()==before
