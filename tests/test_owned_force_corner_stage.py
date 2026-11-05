"""Source-domain finishing is not a narrow ordinary-current workaround."""
import copy
import os
from pathlib import Path
import pcbnew
import pytest
import cec_owned_force_corner_stage as stage
import cec_force_current as force
import cec_field_coupling as field
from test_scalar_acute_stage import fixture


def context(board,net):
    # Synthetic API authority, NOT a hardware load estimate or qualification.
    # Physical controls separately replay the real source catalog unchanged.
    faces=[board.GetLayerName(t.GetLayer()) for t in board.GetTracks()]
    domain=dict(complete=True,missing_refs=[],source_refs=['X1'],sink_refs=['X2'],current_a=3.,
        scope='synthetic_declared_source_for_API_regression_not_hardware_evidence')
    contract=dict(net=net,routing_layers=sorted(set(faces)),
        required_by_layer_mm={face:.5 for face in faces})
    return {net:domain},{net:contract}


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_renamed_native_domain_scope_is_read_only_and_has_no_board_orientation_policy(angle,mirror,layer):
    b,net,tracks,at=fixture(angle,mirror,layer,net='/arbitrary/LOAD')
    for t in tracks:t.SetWidth(600000);t.SetLocked(True)
    domains,contracts=context(b,net);prior=copy.deepcopy((domains,contracts))
    old=field._field_snapshot_inventory(b)
    r=stage.requests(b,domains,contracts,allow_locked_source=True)
    assert r['complete'] and len(r['requests'])==1 and not r['release_authority']
    assert r['requests'][0]['source_track_uuids']==sorted(force._uid(t) for t in tracks)
    assert (domains,contracts)==prior and old==field._field_snapshot_inventory(b)
    assert not stage.geometry.inventory(b,{net},geometry_policy='acute_shortcut')['selected']


@pytest.mark.parametrize('mode',['missing_domain','incomplete','missing_refs','missing_contract','malformed_contract',
    'below_full_floor','missing_face','wrong_net','nan_floor','locked','group','mask','mixed_width','non45','aliased','reference_plane'])
def test_unknown_or_unowned_geometry_cannot_borrow_source_width_or_ordinary_permission(mode):
    b,net,tracks,at=fixture(net='/random/LOAD')
    for t in tracks:t.SetWidth(600000)
    domains,contracts=context(b,net)
    if mode=='missing_domain':domains={}
    elif mode=='incomplete':domains[net]['complete']=False
    elif mode=='missing_refs':domains[net]['missing_refs']=['UNAVAILABLE']
    elif mode=='missing_contract':contracts={}
    elif mode=='malformed_contract':contracts[net]='not-a-contract'
    elif mode=='below_full_floor':contracts[net]['required_by_layer_mm']['F.Cu']=.600001
    elif mode=='missing_face':contracts[net]['required_by_layer_mm']={}
    elif mode=='wrong_net':contracts[net]['net']='/other/LOAD'
    elif mode=='nan_floor':contracts[net]['required_by_layer_mm']['F.Cu']=float('nan')
    elif mode=='locked':tracks[0].SetLocked(True)
    elif mode=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(tracks[0])
    elif mode=='mask':tracks[0].SetHasSolderMask(True)
    elif mode=='mixed_width':tracks[0].SetWidth(700000)
    elif mode=='non45':tracks[0].SetStart(pcbnew.VECTOR2I_MM(15,15.1))
    elif mode=='aliased':tracks[0].SetEnd(pcbnew.VECTOR2I(20000000,20000001))
    else:
        for t in tracks:t.SetLayer(pcbnew.In1_Cu)
        contracts[net].update(routing_layers=['In1.Cu'],required_by_layer_mm={'In1.Cu':.5})
    before=field._field_snapshot_inventory(b)
    r=stage.requests(b,domains,contracts)
    assert r['complete'] and not r['requests'] and before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('kwargs',[dict(allow_locked_source=1),dict(max_requests=0),dict(max_requests=9),
    dict(max_requests=True),dict(sense_timeout_s=0),dict(sense_timeout_s=float('nan')),
    dict(sense_timeout_s=61),dict(expected_source_sha256='not-a-digest')])
def test_invalid_run_context_never_creates_a_family(tmp_path,kwargs):
    defaults=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native')
    defaults.update(kwargs);dest=tmp_path/'not-created'
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',dest,**defaults)
    assert not dest.exists()


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('angle',[0,90])
def test_saved_native_domain_phase_has_full_width_and_independent_existing_force_receiving(tmp_path,monkeypatch,layer,angle):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    b,net,tracks,at=fixture(angle,False,layer,net='/source/DECLARED_LOAD')
    for t in tracks:t.SetWidth(600000);t.SetLocked(True)
    domains,contracts=context(b,net)
    monkeypatch.setattr(stage.topology,'board_current_domains',lambda *a,**k:copy.deepcopy(domains))
    monkeypatch.setattr(stage.topology,'route_width_contracts',lambda *a,**k:copy.deepcopy(contracts))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    old=source.read_bytes();r=stage.run(source,tmp_path/'stage',board_hint='synthetic',
        expected_source_sha256=force._hash(source),reporting_build=Path(native),allow_locked_source=True)
    assert r['ok'] and r['complete'] and r['changed'],r
    assert r['before_craft']==1 and r['after_craft']==0 and r['source_family_and_code_unchanged']
    proof=r['independent_force_receiving']
    assert proof['ok'] and proof['complete'] and not proof['branch_sharing_assumed']
    assert proof['preserved_authored_source_width_nm']==600000 and proof['new_field_blockers']==[]
    saved=pcbnew.LoadBoard(r['candidate'])
    assert all(t.GetWidth()==600000 and t.GetLayer()==layer and t.IsLocked() for t in saved.GetTracks())
    assert r['all_eligible_owned_force_requests_clean'] and not r['routing_admitted'] and not r['fab_ready']
    assert source.read_bytes()==old and not source.with_suffix('.kicad_pro').exists()


def test_expired_geometry_inventory_remains_unknown_even_with_no_findings(monkeypatch):
    b,net,tracks,at=fixture();clock=[0.]
    monkeypatch.setattr(stage.time,'monotonic',lambda:clock[0])
    def expired(board):clock[0]=11.;return dict(issues=[])
    monkeypatch.setattr(stage.quality,'analyze_board',expired)
    with pytest.raises(ValueError,match='complete_owned_force_corner_inventory_required'):
        stage.requests(b,{}, {})
