"""Real native source cycles; no ordinary, power, or GPIO-mode override."""
from pathlib import Path
import copy
import json
import os
import pcbnew
import pytest
import cec_sensitive_redundant_span as op
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_sensitive_scalar_corner_stage import fixture as sensitive_fixture
from test_field_proposals import track


def fixture(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu,alternative=True):
    b,source,old,fp,net=sensitive_fixture(tmp_path,angle=angle,mirror=mirror,layer=layer)
    def at(x,y):
        x,y=round((x-20)*1e6),round((y-20)*1e6)
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return ((20000000+x)/1e6,(20000000+y)/1e6)
    discard_items(b,old)
    b.FindFootprintByReference('X2').SetPosition(pcbnew.VECTOR2I_MM(*at(20,20)))
    cut=[track(b,net,at(*s),at(*z),layer=layer,width=.2) for s,z in
        (((15,15),(20,15)),((20,15),(20,20)))]
    kept=track(b,net,at(15,15),at(20,20),layer=layer,width=.2) if alternative else None
    for t in cut:t.SetLocked(True)
    field._save_field_snapshot(b,source)
    # KiCad assigns the custom MPN field's default stroke on first load.
    # Stabilize this synthetic API-built source before freezing it; the
    # production receiver must never waive changed original field material.
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    return b,source,cut,kept,net,at


def saved(tmp_path,**kwargs):
    b,source,cut,kept,net,at=fixture(tmp_path,**kwargs)
    ids=sorted(force._uid(t) for t in cut)
    proposal=op.plan(source,board_hint='synthetic',retired_track_uuids=ids,allow_locked_source=True)
    child=force._copy_family(source,tmp_path/'child')
    b=op.construct(proposal);op.additive._ground_refill(b);field._save_field_snapshot(b,child)
    return source,child,proposal,ids


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_saved_sensitive_cycle_retirement_keeps_every_native_component_and_pad_path(tmp_path,angle,mirror,layer):
    source,child,proposal,ids=saved(tmp_path,angle=angle,mirror=mirror,layer=layer)
    before=(source.read_bytes(),child.read_bytes())
    r=op.receive(source,child,board_hint='synthetic',retired_track_uuids=ids,allow_locked_source=True)
    assert r['ok'] and r['complete'],r
    assert r['retired_length_mm']==10. and r['added_native_uuids']==[]
    assert r['every_retained_native_component_identical'] and r['every_source_pad_pair_path_proved_nonworse']
    assert r['proposal']['terminal_paths'][0]['before_mm']==r['proposal']['terminal_paths'][0]['after_mm']
    assert not r['ordinary_reclassification'] and not r['GPIO_mode_or_load_assumed']
    assert not r['current_qualified'] and not r['fab_ready'] and not r['release_authority']
    assert before==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('fault',['only_connection','shorter_path','side_terminal','unknown_paths',
    'not_sensitive','USB_pin','power_type','current_budget','pair','analogue_pair','unknown_package',
    'group','mask','locked','mixed_layer','mixed_width','duplicate','unknown_id'])
def test_source_ownership_connectivity_and_path_quality_are_independent(tmp_path,monkeypatch,fault):
    b,source,cut,kept,net,at=fixture(tmp_path,alternative=fault!='only_connection')
    ids=sorted(force._uid(t) for t in cut);unlock=True
    if fault=='shorter_path':ids=[force._uid(kept)]
    elif fault=='side_terminal':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference('SIDE')
        p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(cut[0].GetNet());p.SetPosition(pcbnew.VECTOR2I_MM(*at(20,15)))
        p.SetSize(pcbnew.VECTOR2I(100000,100000));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers)
    elif fault=='unknown_paths':monkeypatch.setattr(op.cells,'_shortest_track_path_mm',lambda *a,**k:None)
    elif fault=='not_sensitive':monkeypatch.setattr(op.sensitive,'eligible_nets',lambda *a,**k:{})
    elif fault=='USB_pin':next(iter(b.FindFootprintByReference('X1').Pads())).SetNumber('18')
    elif fault=='power_type':next(iter(b.FindFootprintByReference('X1').Pads())).SetPinType('power_in')
    elif fault=='current_budget':monkeypatch.setattr(op.sensitive.synth,'spec_net_current_contract',lambda *a,**k:dict(amps=.001))
    elif fault=='pair':monkeypatch.setattr(op.sensitive.precision,'derive_coupled_pairs',lambda *a,**k:[dict(p=net,n='/mate')])
    elif fault=='analogue_pair':monkeypatch.setattr(op.sensitive.semantics,'analog_input_pairs',lambda *a,**k:[dict(p=net,n='/mate')])
    elif fault=='unknown_package':b.FindFootprintByReference('X1').SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8'))
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(cut[0])
    elif fault=='mask':cut[0].SetHasSolderMask(True)
    elif fault=='locked':unlock=False
    elif fault=='mixed_layer':cut[0].SetLayer(pcbnew.B_Cu)
    elif fault=='mixed_width':cut[0].SetWidth(210000)
    elif fault=='duplicate':ids=[ids[0],ids[0]]
    elif fault=='unknown_id':ids[0]='not-native'
    field._save_field_snapshot(b,source)
    with pytest.raises((ValueError,RuntimeError)):
        op.plan(source,board_hint='synthetic',retired_track_uuids=ids,allow_locked_source=unlock)


@pytest.mark.parametrize('fault',['extra_track','extra_via','part_pose','source_copper','sidecar','wrong_cut','unknown_epoch'])
def test_child_cannot_smuggle_other_copper_parts_or_rules(tmp_path,monkeypatch,fault):
    source,child,proposal,ids=saved(tmp_path)
    if fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='wrong_cut':ids=[ids[0]]
    elif fault=='unknown_epoch':
        original=op.force._code_identity;counter=[0]
        def changed():
            counter[0]+=1
            return dict(original(),testing_epoch=str(counter[0]))
        monkeypatch.setattr(op.force,'_code_identity',changed)
    else:
        b=pcbnew.LoadBoard(str(child));t=next(iter(b.GetTracks()));net=str(t.GetNetname())
        if fault=='extra_track':track(b,net,(10,10),(11,10),width=.2)
        elif fault=='extra_via':
            v=pcbnew.PCB_VIA(b);v.SetNet(t.GetNet());v.SetPosition(t.GetStart());v.SetWidth(600000)
            v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        elif fault=='part_pose':b.FindFootprintByReference('X1').Move(pcbnew.VECTOR2I(1000,0))
        elif fault=='source_copper':t.SetWidth(210000)
        field._save_field_snapshot(b,child)
    r=op.receive(source,child,board_hint='synthetic',retired_track_uuids=ids,allow_locked_source=True)
    assert not r['ok'] and not r['complete'] and r['errors'],r


def test_discovery_funds_eligible_native_paths_not_out_of_bound_routes(tmp_path):
    b,source,cut,kept,net,at=fixture(tmp_path)
    before=source.read_bytes()
    result=op.discover(source,board_hint='synthetic',allow_locked_source=True)
    assert result['plans'] and result['complete'],result
    assert all(p['every_original_retained_native_component_identical'] for p in result['plans'])
    assert not result['mutation_or_retirement_admission_granted']
    assert source.read_bytes()==before


@pytest.mark.parametrize('kwargs',[dict(timeout_s=0),dict(timeout_s=True),dict(allow_locked_source=1),
    dict(board_hint=''),dict(retired_track_uuids=[]),dict(retired_track_uuids=['a']*17)])
def test_invalid_context_is_not_retirement_authority(tmp_path,kwargs):
    params=dict(board_hint='synthetic',retired_track_uuids=['a'])
    params.update(kwargs)
    with pytest.raises((ValueError,FileNotFoundError)):
        op.plan(tmp_path/'missing',**params)


def test_typed_original_source_cut_chain_does_not_require_token_replacement_copper(tmp_path):
    import cec_source_cut_chain as chain
    source,child,proposal,ids=saved(tmp_path)
    phase=dict(kind='sensitive_redundant_span',candidate=str(child),retired_track_uuids=ids,allow_locked_source=True)
    r=chain.receive(source,child,board_hint='synthetic',phases=[phase],timeout_s=10.,per_phase_leases=True)
    assert r['ok'] and r['complete'],r
    assert r['phase_receiving'][0]['proof']['every_source_pad_pair_path_proved_nonworse']
    assert not r['phase_receiving'][0]['proof']['ordinary_reclassification']


@pytest.mark.parametrize('fault',['missing_cut','fake_bool','unknown_override','empty_cut','duplicate','wrong_kind'])
def test_typed_phase_schema_has_no_ordinary_or_current_override(tmp_path,fault):
    import cec_source_cut_chain as chain
    phase=dict(kind='sensitive_redundant_span',candidate=str(tmp_path/'child.kicad_pcb'),
        retired_track_uuids=['native'],allow_locked_source=True)
    if fault=='missing_cut':phase.pop('retired_track_uuids')
    elif fault=='fake_bool':phase['allow_locked_source']=1
    elif fault=='unknown_override':phase['assume_zero_current']=True
    elif fault=='empty_cut':phase['retired_track_uuids']=[]
    elif fault=='duplicate':phase['retired_track_uuids']=['native']*2
    elif fault=='wrong_kind':phase['kind']='ordinary_redundant_cut'
    with pytest.raises(ValueError):chain._phases([phase],tmp_path/'child.kicad_pcb')


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_real_uncapped_native_reports_stay_zero_open_and_gain_no_faults(tmp_path,layer):
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('uncapped native DRC build not configured')
    source,child,proposal,ids=saved(tmp_path,layer=layer)
    reports=[]
    for label,path in (('source',source),('child',child)):
        out=tmp_path/(label+'.drc.json')
        proof=native.run(path,out,reporting_build=Path(build),timeout_s=10.)
        assert proof['ok'] and proof['complete'] and not proof['native_inventory']['potentially_truncated']
        reports.append(json.loads(out.read_text()))
    assert all(not q['unconnected_items'] for q in reports)
    assert not {admission._canonical_identity(v) for v in reports[1]['violations']}-{
        admission._canonical_identity(v) for v in reports[0]['violations']}


def test_first_positive_discovery_stops_without_reusing_a_failed_or_mutated_board(tmp_path):
    b,source,cut,kept,net,at=fixture(tmp_path)
    before=source.read_bytes()
    r=op.discover(source,board_hint='synthetic',allow_locked_source=True,stop_after_first=True)
    assert len(r['plans'])==1 and r['stop_after_first_proved_plan'] and source.read_bytes()==before


def trim_fixture(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu,split_contact=False):
    b,source,old,kept,net,old_at=fixture(tmp_path,layer=layer)
    def at(x,y):
        x,y=round((x-20)*1e6),round((y-20)*1e6)
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return ((20000000+x)/1e6,(20000000+y)/1e6)
    discard_items(b,[*old,kept])
    b.FindFootprintByReference('X1').SetPosition(pcbnew.VECTOR2I_MM(*at(10,20)))
    b.FindFootprintByReference('X2').SetPosition(pcbnew.VECTOR2I_MM(*at(25,10)))
    fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference('X3');fp.SetPosition(pcbnew.VECTOR2I_MM(*at(15,25)))
    p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(b.GetNetsByName()[net]);p.SetNumber('1')
    p.SetPosition(fp.GetPosition());p.SetSize(pcbnew.VECTOR2I(100000,100000));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET();layers.AddLayer(layer);p.SetLayerSet(layers)
    points=[at(*q) for q in ((15,20),(25,20),(28,17),(28,10),(25,10))]
    removed=[track(b,net,s,z,layer=layer,width=.2) for s,z in zip(points,points[1:])]
    for t in removed:t.SetLocked(True)
    track(b,net,at(10,20),at(15,20),layer=layer,width=.2)
    if split_contact:
        contact=track(b,net,at(15,25),at(20,20),layer=layer,width=.2)
        track(b,net,at(20,20),at(25,15),layer=layer,width=.2)
    else:contact=track(b,net,at(15,25),at(25,15),layer=layer,width=.2)
    track(b,net,at(25,15),at(25,10),layer=layer,width=.2)
    trim=dict(source_track_uuid=force._uid(removed[0]),
        keep_endpoint_nm=[round(v*1e6) for v in at(15,20)],contact_point_nm=[round(v*1e6) for v in at(20,20)],
        retained_contact_track_uuid=force._uid(contact))
    field._save_field_snapshot(b,source);field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    ids=sorted(force._uid(t) for t in removed)
    params=dict(retired_track_uuids=ids,allow_locked_source=True,source_contained_trim=trim)
    proposal=op.plan(source,board_hint='synthetic',**params)
    child=force._copy_family(source,tmp_path/'trim-child')
    rebuilt=op.construct(proposal);op.additive._ground_refill(rebuilt);field._save_field_snapshot(rebuilt,child)
    return source,child,params,proposal


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('split_contact',[False,True])
def test_source_subset_trim_retains_real_body_or_split_junction_without_overhang(tmp_path,angle,mirror,layer,split_contact):
    source,child,params,proposal=trim_fixture(tmp_path,angle,mirror,layer,split_contact)
    before=(source.read_bytes(),child.read_bytes())
    r=op.receive(source,child,board_hint='synthetic',**params)
    assert r['ok'] and r['complete'],r
    assert len(r['retired_track_uuids'])==4 and len(r['added_native_uuids'])==1
    assert r['replacement_is_only_exact_source_capsule_subset']
    assert r['retired_length_mm']>19 and r['every_source_pad_pair_path_proved_nonworse']
    assert proposal['source_contained_replacement_length_mm']==5.
    assert not r['ordinary_reclassification'] and not r['current_qualified'] and not r['release_authority']
    assert before==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('fault',['outside','noninteger','wrong_keep','missing_contact','retired_contact',
    'unknown_key','thinner_contact','wrong_width','off_source','missing_replacement','extra_replacement','retained_pose'])
def test_contained_trim_is_not_permission_for_other_signal_geometry(tmp_path,fault):
    source,child,params,proposal=trim_fixture(tmp_path)
    trim=params['source_contained_trim']
    if fault=='outside':trim['contact_point_nm']=[5000000,5000000]
    elif fault=='noninteger':trim['contact_point_nm']=[20000000.5,20000000]
    elif fault=='wrong_keep':trim['keep_endpoint_nm']=[15000000,20000001]
    elif fault=='missing_contact':trim['retained_contact_track_uuid']='unknown'
    elif fault=='retired_contact':trim['retained_contact_track_uuid']=params['retired_track_uuids'][0]
    elif fault=='unknown_key':trim['assume_GPIO_zero_current']=True
    else:
        path=source if fault=='thinner_contact' else child
        b=pcbnew.LoadBoard(str(path));original_ids={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
        changed=[t for t in b.GetTracks() if force._uid(t) not in original_ids]
        if fault=='thinner_contact':
            next(t for t in b.GetTracks() if force._uid(t)==trim['retained_contact_track_uuid']).SetWidth(199999)
        elif fault=='wrong_width':changed[0].SetWidth(199999)
        elif fault=='off_source':changed[0].SetEnd(changed[0].GetEnd()+pcbnew.VECTOR2I(0,1))
        elif fault=='missing_replacement':discard_items(b,changed)
        elif fault=='extra_replacement':
            duplicate=changed[0].Duplicate();duplicate.m_Uuid.Clone(pcbnew.KIID());b.Add(duplicate)
        elif fault=='retained_pose':b.FindFootprintByReference('X1').Move(pcbnew.VECTOR2I(1,0))
        field._save_field_snapshot(b,path)
    r=op.receive(source,child,board_hint='synthetic',**params)
    assert not r['ok'] and not r['complete'] and r['errors'],r


def test_typed_cut_chain_receives_only_the_source_derived_junction_remnant(tmp_path):
    import cec_source_cut_chain as chain
    source,child,params,proposal=trim_fixture(tmp_path,split_contact=True)
    phase=dict(kind='sensitive_redundant_span',candidate=str(child),**params)
    r=chain.receive(source,child,board_hint='synthetic',phases=[phase],timeout_s=10.,per_phase_leases=True)
    assert r['ok'] and r['complete'],r
    assert len(r['added_native_uuids'])==1 and r['independently_received_source_sensitive_redundancy']
    assert not r['independently_received_subtraction_only_ordinary_cleanup']


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_source_contained_trim_has_no_new_native_opens_or_dangling_tail(tmp_path,layer):
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('uncapped native DRC build not configured')
    source,child,params,proposal=trim_fixture(tmp_path,layer=layer,split_contact=True)
    reports=[]
    for label,path in (('source',source),('child',child)):
        dest=tmp_path/(label+'.drc.json');producer=native.run(path,dest,reporting_build=Path(build),timeout_s=10.)
        assert producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated']
        reports.append(json.loads(dest.read_text()))
    assert not reports[1]['unconnected_items']
    assert not {admission._canonical_identity(v) for v in reports[1]['violations']}-{
        admission._canonical_identity(v) for v in reports[0]['violations']}
