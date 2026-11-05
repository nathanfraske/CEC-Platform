"""Inner RC replacements need actual Source stack/reference and width authority."""
import os
from pathlib import Path
import pcbnew
import pytest
import cec_ordinary_rc_reconstruction as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_ordinary_rc_reconstruction import construct


def saved(tmp_path,turn=0,kind='C',profile='jlcpcb_6l_pofv_signal'):
    source,target,uid,fpuid,cuts,_=construct(tmp_path,turn,'RENAMED',transitions=True)
    mpn_identity=None
    for path in (source,target):
        b=pcbnew.LoadBoard(str(path));props=b.GetProperties();props['CEC_FAB_PROFILE']=profile;b.SetProperties(props)
        fp=next(f for f in b.GetFootprints() if force._uid(f)==fpuid)
        if kind=='R':
            fp.SetReference('R'+str(9200+turn));fp.SetValue('100k')
            fp.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_0402_1005Metric'))
            fp.SetField('MPN','0402WGF1003TCE')
            authored=next(f for f in fp.GetFields() if f.GetName()=='MPN')
            authored.SetTextThickness(150000)
            if mpn_identity is None:
                mpn_identity=(force._uid(authored),list(authored.GetPosition()),authored.GetTextAngle().AsDegrees())
            else:
                authored.m_Uuid.Clone(pcbnew.KIID(mpn_identity[0]))
                authored.SetPosition(pcbnew.VECTOR2I(*mpn_identity[1]))
                authored.SetTextAngle(pcbnew.EDA_ANGLE(mpn_identity[2],pcbnew.DEGREES_T))
        if path==target:
            for t in b.GetTracks():
                if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu:t.SetLayer(pcbnew.In2_Cu)
        additive._ground_refill(b);field._save_field_snapshot(b,path)
    return source,target,dict(via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts)


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('kind',['C','R'])
@pytest.mark.parametrize('profile',['jlcpcb_6l_pofv_signal','jlcpcb_6l_pofv_high_current'])
def test_saved_renamed_cap_or_resistor_can_use_only_source_referenced_signal_faces(tmp_path,turn,kind,profile):
    source,target,params=saved(tmp_path,turn,kind,profile);before=(source.read_bytes(),target.read_bytes())
    denied=op.receive(source,target,**params)
    assert not denied['ok'] and 'bounded_full_class_ordinary_RC_replacement_tracks_required' in str(denied['errors'])
    proof=op.receive(source,target,**params,allow_source_signal_inner_layers=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['source_signal_inner_layers_explicit']
    assert set(proof['source_derived_replacement_layer_floors_nm'])=={'0','6','2'}
    assert proof['new_standard_transition_count']==2 and proof['actual_owned_ground_barrel_geometry_preserved']
    assert proof['all_surviving_source_native_partitions_preserved'] and proof['exact_unowned_source_nodes_preserved']
    assert not proof['current_qualified'] and not proof['routing_admitted'] and not proof['release_authority']
    assert before==(source.read_bytes(),target.read_bytes())


@pytest.mark.parametrize('layer',[pcbnew.In1_Cu,pcbnew.In3_Cu,pcbnew.In4_Cu])
def test_ground_power_and_non_copper_faces_remain_protected_even_with_permission(tmp_path,layer):
    source,target,params=saved(tmp_path);b=pcbnew.LoadBoard(str(target))
    for t in b.GetTracks():
        if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.In2_Cu:t.SetLayer(layer)
    field._save_field_snapshot(b,target)
    proof=op.receive(source,target,**params,allow_source_signal_inner_layers=True)
    assert not proof['ok'] and not proof['complete'] and proof['errors']


@pytest.mark.parametrize('value',[None,1,'yes',[]])
def test_inner_permission_is_explicit_not_truthy(tmp_path,value):
    source,target,params=saved(tmp_path)
    proof=op.receive(source,target,**params,allow_source_signal_inner_layers=value)
    assert not proof['ok'] and 'explicit_source_RC_signal_inner_permission_required' in str(proof['errors'])


@pytest.mark.parametrize('fault',['missing_source_profile','candidate_stack','thin_inner','small_via','wrong_net','missing_ground'])
def test_inner_permission_never_waives_source_process_population_or_width(tmp_path,fault):
    source,target,params=saved(tmp_path)
    paths=(source,target) if fault=='missing_source_profile' else (target,)
    for path in paths:
        b=pcbnew.LoadBoard(str(path))
        if fault in ('missing_source_profile','candidate_stack'):
            props=b.GetProperties();props['CEC_FAB_PROFILE']='' if fault=='missing_source_profile' else 'jlcpcb_4l_std'
            b.SetProperties(props)
        elif fault=='thin_inner':
            next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.In2_Cu).SetWidth(199999)
        elif fault=='small_via':
            next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA' and t.GetNetname()!="GND").SetWidth(350000)
        elif fault=='wrong_net':
            next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.In2_Cu).SetNet(b.FindNet('GND'))
        else:b.Remove(next(t for t in b.GetTracks() if force._uid(t)==params['via_uuid']))
        # Deliberately hostile external candidate: the normal constructor
        # already rejects wrong authored-net round trips before receiving.
        if fault=='wrong_net':pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),b)
        else:field._save_field_snapshot(b,path)
    proof=op.receive(source,target,**params,allow_source_signal_inner_layers=True)
    assert not proof['ok'] and not proof['complete'] and proof['errors']


@pytest.mark.parametrize('value',[True,0,-.1,float('nan'),'0.25',[]])
def test_per_face_source_width_is_not_a_candidate_waiver(tmp_path,monkeypatch,value):
    source,target,params=saved(tmp_path)
    monkeypatch.setattr(op.fr,'_project_netclass_resolver',lambda *a,**k:
        lambda net:dict(track_width=.2,track_width_by_layer_mm={'In2.Cu':value}))
    proof=op.receive(source,target,**params,allow_source_signal_inner_layers=True)
    assert not proof['ok'] and proof['errors']


def test_source_inner_width_floor_is_enforced_independently(tmp_path,monkeypatch):
    source,target,params=saved(tmp_path)
    monkeypatch.setattr(op.fr,'_project_netclass_resolver',lambda *a,**k:
        lambda net:dict(track_width=.2,track_width_by_layer_mm={'In2.Cu':.25}))
    assert not op.receive(source,target,**params,allow_source_signal_inner_layers=True)['ok']
    b=pcbnew.LoadBoard(str(target))
    for t in b.GetTracks():
        if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.In2_Cu:t.SetWidth(250000)
    field._save_field_snapshot(b,target)
    proof=op.receive(source,target,**params,allow_source_signal_inner_layers=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['source_derived_replacement_layer_floors_nm']['6']==250000


@pytest.mark.parametrize('mapping',[[],False,''])
def test_even_empty_malformed_source_width_maps_are_not_missing_authority(tmp_path,monkeypatch,mapping):
    source,target,params=saved(tmp_path)
    monkeypatch.setattr(op.fr,'_project_netclass_resolver',lambda *a,**k:
        lambda net:dict(track_width=.2,track_width_by_layer_mm=mapping))
    proof=op.receive(source,target,**params,allow_source_signal_inner_layers=True)
    assert not proof['ok'] and 'source_RC_per_face_width_map_required' in str(proof['errors'])


def test_a_signal_role_without_source_ground_reference_is_not_eligible(tmp_path,monkeypatch):
    source,target,params=saved(tmp_path)
    monkeypatch.setattr(op.fab,'referenced_signal_layers',lambda *a,**k:('F.Cu','B.Cu'))
    proof=op.receive(source,target,**params,allow_source_signal_inner_layers=True)
    assert not proof['ok'] and 'bounded_full_class_ordinary_RC_replacement_tracks_required' in str(proof['errors'])


def test_canonical_and_native_layer_names_keep_the_stricter_source_floor(tmp_path,monkeypatch):
    source,_,_=saved(tmp_path);b=pcbnew.LoadBoard(str(source));b.SetLayerName(pcbnew.In2_Cu,'Renamed_SIG')
    monkeypatch.setattr(op.fr,'_project_netclass_resolver',lambda *a,**k:
        lambda net:dict(track_width_by_layer_mm={'In2.Cu':.2,'Renamed_SIG':.3}))
    policy=op._replacement_faces(b,source,'/SERVICE_TIMING',200000,True)
    assert policy[int(pcbnew.In2_Cu)]==300000


def test_inner_rc_delta_has_no_new_native_clearance_or_connection_fault(tmp_path):
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('explicit native DRC build required')
    import json
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    source,target,params=saved(tmp_path)
    proof=op.receive(source,target,**params,allow_source_signal_inner_layers=True)
    assert proof['ok'],proof
    reports=[]
    for label,path in (('source',source),('candidate',target)):
        output=tmp_path/('native-'+label+'.json')
        producer=native.run(path,output,reporting_build=Path(build),timeout_s=10.)
        assert producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated'],json.dumps(producer)
        reports.append(json.loads(output.read_text()))
    assert not reports[1]['unconnected_items']
    before={admission._canonical_identity(v) for v in reports[0]['violations']}
    assert not {admission._canonical_identity(v) for v in reports[1]['violations']}-before
