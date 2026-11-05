"""A retained source barrel is not a new-hole or source-cut permission."""
import copy,os
from pathlib import Path
import pcbnew
import pytest
import wx
import cec_ground_return_shortcut as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_native_ground_terminal_branch import fixture as branch_fixture
from test_field_proposals import track
quiet=wx.LogNull()


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu):
    b,source,ids,points,owner,cap,old=branch_fixture(tmp_path,quarter=quarter,mirror=mirror,layer=layer)
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    via=pcbnew.PCB_VIA(b);via.SetNet(b.FindNet('GND'));via.SetPosition(point(12,8))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True);b.Add(via)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    pad=cap.FindPadByNumber('2')
    params=dict(board_hint='synthetic',pad_uuid=force._uid(pad),target_via_uuid=force._uid(via),
        points_nm=[list(pad.GetPosition()),list(via.GetPosition())])
    return b,source,params,pad,via,point


def saved(tmp_path,**kwargs):
    b,source,params,*_=fixture(tmp_path,**kwargs);q=op.plan(source,**params);child_b=op.construct(q)
    additive._ground_refill(child_b);child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(child_b,child)
    return source,child,params,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_source_pad_and_plane_barrel_gain_a_shorter_return_in_all_rigid_frames(tmp_path,quarter,mirror,layer):
    source,child,params,q=saved(tmp_path,quarter=quarter,mirror=mirror,layer=layer)
    raw=(source.read_bytes(),child.read_bytes());r=op.receive(source,child,**params)
    assert r['ok'] and r['complete'],r
    assert r['source_return_witness_mm']>8 and r['saved_return_witness_mm']==2.5
    assert r['shortened_return_witness_mm']>5 and not r['retired_track_uuids'] and len(r['added_native_uuids'])==1
    assert r['new_holes']==0 and r['every_source_native_partition_identical']
    assert r['native_ground_material_preservation']['every_preexisting_ground_return_path_material_preserved']
    assert r['all_source_barrels_pads_poses_rules_and_power_copper_retained']
    assert not r['current_qualified'] and not r['fab_ready'] and not r['release_authority']
    assert r['witness_is_not_a_global_shortest_path_or_immediate_return_certificate']
    assert raw==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('fault',['new_via','moved_via','hole','width','layer','unlocked','mask','extra_track',
    'extra_via','pose','rules','existing_track','ground_fill','wrong_target','unknown_witness','source_voltage'])
def test_receiver_replays_the_source_and_never_imports_untrusted_copper(tmp_path,monkeypatch,fault):
    source,child,params,q=saved(tmp_path)
    if fault=='rules':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='wrong_target':params['target_via_uuid']='unrelated-source-uuid'
    elif fault=='unknown_witness':monkeypatch.setattr(op.cells,'_existing_return',lambda *a,**k:None)
    else:
        b=pcbnew.LoadBoard(str(child));source_ids={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
        added=next(t for t in b.GetTracks() if force._uid(t) not in source_ids)
        target=next(t for t in b.GetTracks() if force._uid(t)==params['target_via_uuid'])
        if fault=='new_via':target.m_Uuid.Clone(pcbnew.KIID())
        elif fault=='moved_via':target.Move(pcbnew.VECTOR2I(1,0))
        elif fault=='hole':target.SetDrill(200000)
        elif fault=='width':added.SetWidth(199999)
        elif fault=='layer':added.SetLayer(pcbnew.B_Cu)
        elif fault=='unlocked':added.SetLocked(False)
        elif fault=='mask':added.SetHasSolderMask(True)
        elif fault=='extra_track':track(b,'GND',(20,20),(21,20),width=.2)
        elif fault=='extra_via':
            v=target.Duplicate();v.m_Uuid.Clone(pcbnew.KIID());v.Move(pcbnew.VECTOR2I_MM(1,0));b.Add(v)
        elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='existing_track':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and force._uid(t) in source_ids).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='ground_fill':next(iter(b.Zones())).UnFill()
        else:next(iter(b.GetFootprints())).SetValue('different source part')
        field._save_field_snapshot(b,child)
    r=op.receive(source,child,**params)
    assert not r['ok'] and not r['complete'] and r['errors'],r


@pytest.mark.parametrize('fault',['not_ground','plated_pad','DNP','no_profile','no_plane','one_missing_plane',
    'blind_via','foreign_via','missing_via','wrong_port','hard90','raw_diagonal','repeat','outside','foreign_copper','already_covered'])
def test_source_ownership_reference_material_fixed_ports_and_clearance_are_required(tmp_path,fault):
    b,source,params,pad,via,point=fixture(tmp_path)
    if fault=='not_ground':pad.SetNet(b.FindNet('+3V3'))
    elif fault=='plated_pad':
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2));pad.SetLayerSet(pcbnew.PAD.PTHMask())
    elif fault=='DNP':pad.GetParentFootprint().SetDNP(True)
    elif fault=='no_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='';b.SetProperties(props)
    elif fault=='no_plane':
        for z in b.Zones():z.UnFill()
    elif fault=='one_missing_plane':next(iter(b.Zones())).UnFill()
    elif fault=='blind_via':via.SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu);via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault=='foreign_via':
        via.SetNet(b.FindNet('+3V3'));additive._ground_refill(b)
    elif fault=='missing_via':params['target_via_uuid']='not-in-source'
    elif fault=='wrong_port':params['points_nm'][0][0]+=1
    elif fault=='hard90':params['points_nm']=[[9500000,8000000],[9500000,9000000],[12000000,9000000],[12000000,8000000]]
    elif fault=='raw_diagonal':params['points_nm']=[[9500000,8000000],[11000000,8000001],[12000000,8000000]]
    elif fault=='repeat':params['points_nm'].insert(1,params['points_nm'][0])
    elif fault=='outside':params['points_nm']=[[9500000,8000000],[-1000000,8000000],[12000000,8000000]]
    elif fault=='foreign_copper':track(b,'+3V3',(10.5,7.5),(10.5,8.5),width=.2)
    else:track(b,'GND',(9.5,8),(12,8),width=.2)
    # These are deliberately hostile external source files, not accepted
    # native-field transactions. Save/reload their actual negative condition
    # rather than asking the valid-construction serializer to admit it.
    pcbnew.SaveBoard(str(source),b)
    actual=pcbnew.LoadBoard(str(source))
    if fault=='foreign_via':assert next(t for t in actual.GetTracks() if force._uid(t)==params['target_via_uuid']).GetNetname()=='+3V3'
    if fault=='plated_pad':assert next(p for fp in actual.GetFootprints() for p in fp.Pads() if force._uid(p)==params['pad_uuid']).GetAttribute()==pcbnew.PAD_ATTRIB_PTH
    with pytest.raises((ValueError,RuntimeError)):op.plan(source,**params)


@pytest.mark.parametrize('options',[dict(board_hint=''),dict(pad_uuid=''),dict(target_via_uuid=''),
    dict(timeout_s=0),dict(timeout_s=True),dict(timeout_s=11),dict(timeout_s=float('nan')),dict(points_nm=[])])
def test_empty_unknown_or_unbounded_plan_context_is_not_authority(tmp_path,options):
    b,source,params,*_=fixture(tmp_path);params.update(options)
    with pytest.raises((ValueError,RuntimeError)):op.plan(source,**params)


def test_read_only_automatic_discovery_does_not_need_a_component_name_or_target_hint(tmp_path):
    b,source,params,*_=fixture(tmp_path);raw=source.read_bytes()
    q=op.discover(source,board_hint='synthetic')
    assert q['plans'] and not q['source_geometry_mutated'],q
    assert any(p['pad_uuid']==params['pad_uuid'] and p['target_via_uuid']==params['target_via_uuid'] for p in q['plans'])
    assert source.read_bytes()==raw and q['finite_portfolio_not_a_no_path_proof']


def test_known_blocked_start_does_not_exhaust_pad_funding_on_its_remote_targets(tmp_path,monkeypatch):
    b,source,params,pad,via,point=fixture(tmp_path);actual=op.fr._tap_foreign_clear
    def clear(board,a,z,*args,**kwargs):
        if a==z and list(a)==params['points_nm'][0]:return False
        return actual(board,a,z,*args,**kwargs)
    monkeypatch.setattr(op.fr,'_tap_foreign_clear',clear)
    q=op.discover(source,board_hint='synthetic',maximum_pads=1)
    assert q['funded_pad_cohorts']==1 and q['plans'],q
    assert any(r['pad_uuid']==params['pad_uuid'] for r in q['refused_source_launches'])
    assert all(r['pad_uuid']!=params['pad_uuid'] for r in q['trials'])
    assert q['plans'][0]['pad_uuid']!=params['pad_uuid'] and not q['source_geometry_mutated']


def test_one_blocked_terminal_does_not_starve_other_terminal_target_cohorts(tmp_path,monkeypatch):
    b,source,params,pad,via,point=fixture(tmp_path);actual=op.fr._guarded_profiled_lastmile_legs
    def route(board,start,*args,**kwargs):
        if list(start)==params['points_nm'][0]:return None
        return actual(board,start,*args,**kwargs)
    monkeypatch.setattr(op.fr,'_guarded_profiled_lastmile_legs',route)
    q=op.discover(source,board_hint='synthetic',maximum_pads=2)
    assert q['plans'] and q['round_robin_target_cohorts_share_one_deadline'],q
    assert q['trials'][0]['pad_uuid']==params['pad_uuid'] and q['trials'][0]['cohort_round']==0
    assert q['trials'][1]['pad_uuid']!=params['pad_uuid'] and q['trials'][1]['cohort_round']==0


@pytest.mark.parametrize('fault',[dict(maximum_pads=True),dict(maximum_pads=0),dict(maximum_pads=9),
    dict(maximum_targets=0),dict(maximum_targets=25),dict(minimum_return_mm=True),dict(minimum_return_mm=0),dict(minimum_return_mm=float('inf'))])
def test_discovery_has_finite_explicit_work_and_does_not_mutate_source(tmp_path,fault):
    b,source,*_=fixture(tmp_path);raw=source.read_bytes()
    with pytest.raises(ValueError):op.discover(source,board_hint='synthetic',**fault)
    assert source.read_bytes()==raw


def test_real_native_stage_receives_all_current_field_and_cut_checks(tmp_path):
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('native DRC reporting build not configured')
    b,source,*_=fixture(tmp_path);raw=source.read_bytes()
    q=op.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),reporting_build=Path(build))
    assert q['ok'] and q['complete'] and q['changed'],q
    r=q['attempts'][-1];assert r['accepted'] and not r['errors'] and r['opens']==0 and not r['new_native_fault_ids']
    assert r['whole_parent_current_receiving']['ok'] and r['whole_parent_current_receiving']['complete']
    assert r['whole_parent_clipped_preservation']['same_evidence'] and not r['new_field_blockers']
    assert source.read_bytes()==raw and q['source_family_and_code_unchanged'] and not q['release_authority']


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_unchanged_already_antipadded_barrel_is_not_a_new_hole_in_a_reserved_power_region(tmp_path,layer):
    import cec_fr as routing
    import cec_zone_fill
    b,source,params,pad,via,point=fixture(tmp_path,layer=layer)
    face=pcbnew.B_Cu if layer==pcbnew.F_Cu else pcbnew.F_Cu
    z=pcbnew.ZONE(b);z.SetNet(b.FindNet('+3V3'));z.SetLayer(face)
    z.SetZoneName('CEC_RECTILINEAR_POWER_CONTOUR');z.SetLocalClearance(200000);z.SetMinThickness(100000)
    z.Outline().NewOutline()
    for x,y in ((10,6),(14,6),(14,10),(10,10)):z.Outline().Append(x*1000000,y*1000000)
    b.Add(z);cec_zone_fill.fill(b);field._save_field_snapshot(b,source)
    before=source.read_bytes();details={}
    assert not routing._via_spot_clear(b,via.GetPosition(),600000,200000,{pad.GetNetCode()},
        drill_nm=300000,net_code=pad.GetNetCode(),existing_via_uuid=force._uid(via),foreign_cache={},report=details)
    assert details['reason']=='foreign copper excludes via land'
    q=op.plan(source,**params);child_b=op.construct(q);additive._ground_refill(child_b)
    child=force._copy_family(source,tmp_path/'reserved-power-candidate');field._save_field_snapshot(child_b,child)
    r=op.receive(source,child,**params)
    assert r['ok'] and r['complete'] and r['new_holes']==0,r
    assert r['all_source_barrels_pads_poses_rules_and_power_copper_retained'] and source.read_bytes()==before
    assert not r['current_qualified'] and r['whole_current_fields_uncapped_native_DRC_absolute_cuts_and_release_still_required']


@pytest.mark.parametrize('fault',['current','field','native','clipped'])
def test_stage_success_flags_cannot_bypass_any_saved_whole_parent_gate(tmp_path,monkeypatch,fault):
    import cec_current_debt as current
    import cec_force_sense_evidence as sense
    import cec_native_drc_runner as native
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('native DRC reporting build not configured')
    b,source,*_=fixture(tmp_path);raw=source.read_bytes()
    if fault=='current':monkeypatch.setattr(current,'receive',lambda *a,**k:dict(ok=True,complete=False))
    elif fault=='field':
        monkeypatch.setattr(field,'field_coupling_summary',lambda p,**k:dict(candidate=Path(p).resolve()!=source.resolve()))
        monkeypatch.setattr(field,'blocker_keys',lambda q:{'new_actual_blocker'} if q['candidate'] else set())
    elif fault=='native':monkeypatch.setattr(native,'run',lambda *a,**k:dict(ok=True,complete=False))
    else:monkeypatch.setattr(sense,'compare_contour_preservation',lambda *a,**k:dict(same_evidence=True,comparison_complete=False))
    q=op.run(source,tmp_path/'refused-stage',board_hint='synthetic',expected_source_sha256=force._hash(source),reporting_build=Path(build))
    assert q['ok'] and q['complete'] and not q['changed'] and q['candidate']==str(source.resolve()),q
    assert q['attempts'] and not any(r['accepted'] for r in q['attempts']) and q['source_family_and_code_unchanged']
    assert source.read_bytes()==raw and not q['release_authority']


@pytest.mark.parametrize('options',[dict(board_hint=''),dict(expected_source_sha256='bad'),dict(reporting_build=None),
    dict(maximum_candidates=True),dict(maximum_candidates=0),dict(maximum_candidates=5)])
def test_bad_or_unbounded_stage_policy_creates_no_output(tmp_path,options):
    b,source,*_=fixture(tmp_path);params=dict(board_hint='synthetic',expected_source_sha256=force._hash(source),reporting_build=tmp_path/'unused')
    params.update(options)
    with pytest.raises(ValueError):op.run(source,tmp_path/'no-stage',**params)
    assert not (tmp_path/'no-stage').exists()
