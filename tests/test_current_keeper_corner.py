"""Synthetic source budgets exercise reconstruction, not hardware ratings."""
import copy,json
import pcbnew
import pytest
import cec_current_keeper_corner as op
import cec_full_current_corner_finish as corners
import cec_field_coupling as field
import cec_force_current as force
import cec_native_contour_regions as regions
import cec_rectilinear_copper as owner
from test_full_current_corner_finish import fixture as current_fixture


def fixture(tmp_path,monkeypatch,*,quarter=0,mirror=False,face=pcbnew.F_Cu,legacy=False):
    source,net,domains,contract=current_fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face,width=.6)
    b=pcbnew.LoadBoard(str(source));tracks=sorted(b.GetTracks(),key=lambda t:force._uid(t));chosen=tracks[:1]
    q=regions.plan(b,[force._uid(t) for t in chosen],required_width_nm=200000,
        clearance_nm=200000,min_thickness_nm=100000,contour_style='chamfer45',contour_grid_nm=1000,
        envelope_margin_nm=1000,fill_envelope_margin_nm=4,
        allow_locked_track_uuids=[force._uid(t) for t in chosen])
    made=regions.materialize(b,q,allow_locked_track_uuids=[force._uid(t) for t in chosen]);regions.fill(b,q,made['zone_uuids'])
    if legacy:next(iter(b.Zones())).SetZoneName(owner.ZONE_NAME)
    field._save_field_snapshot(b,source)
    found=corners.discover(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',allow_locked_source=True)
    assert len(found['composed_power_contour_frontier'])==1
    return source,net,domains,contract,found['composed_power_contour_frontier'][0]['request']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('legacy',[False,True])
def test_saved_combination_preserves_actual_current_and_every_other_native_object(tmp_path,monkeypatch,quarter,mirror,face,legacy):
    source,net,domains,contract,request=fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face,legacy=legacy)
    # Hardware source-domain producers return tuples. Exercise the complete
    # saved JSON transaction, not only an in-process dict with synthetic lists.
    domains[net]['source_refs']=tuple(domains[net]['source_refs'])
    domains[net]['sink_refs']=tuple(domains[net]['sink_refs'])
    domains[net]['missing_refs']=()
    contract['routing_layers']=tuple(contract['routing_layers'])
    contract['authority_refs']=('X1','X2')
    original=source.read_bytes();budget=copy.deepcopy((domains,contract))
    q=op.plan(source,board_hint='synthetic',request=request,allow_locked_source=True)
    plan_path=tmp_path/'saved-worker-plan.json';force._write(plan_path,q)
    q=json.loads(plan_path.read_text())
    assert q==op.plan(source,board_hint='synthetic',request=request,allow_locked_source=True)
    b,made=op.construct(q);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    result=op.receive(source,child,q,board_hint='synthetic')
    assert result['ok'] and result['complete'],result
    assert result['chamfered']==1 and result['saved_trace_length_mm']>0
    assert result['actual_visible_native_material_removed']['ok'] and result['original_native_partitions_identical']
    assert result['source_width_face_and_current_exact'] and result['exact_entire_original_source_reconstruction']
    assert result['new_holes']==result['new_vias']==0 and not result['current_qualified'] and not result['release_authority']
    assert source.read_bytes()==original and (domains,contract)==budget
    saved=pcbnew.LoadBoard(str(child))
    assert all(t.GetWidth()==600000 and t.GetLayer()==face for t in saved.GetTracks())
    assert {force._uid(z) for z in saved.Zones()}=={force._uid(z) for z in pcbnew.LoadBoard(str(source)).Zones()}
    assert next(iter(saved.Zones())).GetZoneName()==(owner.ZONE_NAME if legacy else regions.ZONE_NAME)


@pytest.mark.parametrize('fault',['budget','routing_face','source_owner','keeper_scope'])
def test_saved_json_authority_is_rederived_not_trusted_or_dropped(tmp_path,monkeypatch,fault):
    source,net,domains,contract,request=fixture(tmp_path,monkeypatch,legacy=True)
    contract['routing_layers']=tuple(contract['routing_layers'])
    domains[net]['source_refs']=tuple(domains[net]['source_refs'])
    q=op.plan(source,board_hint='synthetic',request=request,allow_locked_source=True)
    q=json.loads(json.dumps(q,allow_nan=False))
    if fault=='budget':q['full_current_plan']['contract']['current_authority']['amps']/=2
    elif fault=='routing_face':q['full_current_plan']['contract']['routing_layers']=['B.Cu']
    elif fault=='source_owner':q['full_current_plan']['domain']['source_refs']=['X2']
    else:q['keeper_contexts'][0]['allow_locked_zone']=False
    with pytest.raises(ValueError,match='stale_or_forged'):
        op.construct(q)


@pytest.mark.parametrize('fault',['track_width','track_motion','part_motion','zone_priority','zone_outline','zone_name',
    'extra_track','extra_via','missing_track','source_plan'])
def test_saved_worker_cannot_forge_a_partial_or_unrelated_transaction(tmp_path,monkeypatch,fault):
    source,net,domains,contract,request=fixture(tmp_path,monkeypatch,legacy=True)
    q=op.plan(source,board_hint='synthetic',request=request,allow_locked_source=True);b,made=op.construct(q)
    t=next(iter(b.GetTracks()));z=next(iter(b.Zones()))
    if fault=='track_width':t.SetWidth(t.GetWidth()-1)
    elif fault=='track_motion':t.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='part_motion':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='zone_priority':z.SetAssignedPriority(1)
    elif fault=='zone_outline':z.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='zone_name':z.SetZoneName('unrelated slab')
    elif fault=='extra_track':
        extra=t.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());extra.Move(pcbnew.VECTOR2I_MM(1,1));b.Add(extra)
    elif fault=='extra_via':
        via=pcbnew.PCB_VIA(b);via.SetNet(t.GetNet());via.SetPosition(pcbnew.VECTOR2I_MM(35,35));via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(0,2);b.Add(via)
    elif fault=='missing_track':b.Delete(t)
    else:q['full_current_plan']['contract']['current_authority']['amps']/=2
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    result=op.receive(source,child,q,board_hint='synthetic')
    assert not result['ok'] and result['errors']


@pytest.mark.parametrize('fault',['unknown_budget','underwidth','no_lock_scope','source_point','source_name','source_priority'])
def test_source_contradiction_has_no_constructor_authority(tmp_path,monkeypatch,fault):
    source,net,domains,contract,request=fixture(tmp_path,monkeypatch,legacy=True)
    b=pcbnew.LoadBoard(str(source));z=next(iter(b.Zones()))
    if fault=='unknown_budget':contract['current_authority']['source']='guess'
    elif fault=='underwidth':contract['required_by_layer_mm']['F.Cu']=.600001
    elif fault=='source_point':z.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='source_name':z.SetZoneName('unqualified generated shape')
    elif fault=='source_priority':z.SetAssignedPriority(1)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',request=request,allow_locked_source=fault!='no_lock_scope')


@pytest.mark.parametrize('bad',['not-a-uuid',None,True])
def test_replacement_identity_is_not_a_worker_escape_hatch(tmp_path,monkeypatch,bad):
    source,net,domains,contract,request=fixture(tmp_path,monkeypatch)
    q=op.plan(source,board_hint='synthetic',request=request,allow_locked_source=True)
    with pytest.raises((ValueError,TypeError)):
        op.construct(q,incoming_uuids=[bad,bad,bad])


@pytest.mark.parametrize('kwargs',[dict(max_trials=0),dict(max_trials=9),dict(max_trials=True),dict(allow_locked_source=1),dict(expected_source_sha256='guess')])
def test_generic_stage_rejects_bad_work_limits_before_writing_a_family(tmp_path,kwargs):
    import cec_current_keeper_corner_stage as stage
    settings=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native')
    settings.update(kwargs);out=tmp_path/'no-output'
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',out,**settings)
    assert not out.exists()
