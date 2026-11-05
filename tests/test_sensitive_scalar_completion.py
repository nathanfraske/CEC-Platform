"""Sensitive scalar completion keeps authored class and manufacturer scope."""
import json
from unittest import mock
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_sensitive_scalar_completion as op
import cec_received_private_stage as stage
from cec_native_items import discard_items
from test_sensitive_scalar_corner_stage import fixture


def case(tmp_path,angle=0,layer=pcbnew.F_Cu):
    b,source,tracks,fp,net=fixture(tmp_path,angle=angle,layer=layer)
    discard_items(b,tracks)
    field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{
        'classes':[{'name':'Default','track_width':.2,'clearance':.2}]}}))
    return source,net


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_positive_native_scalar_scope_is_not_ordinary_reclassification(tmp_path,angle,layer):
    source,net=case(tmp_path,angle,layer);b=pcbnew.LoadBoard(str(source));before=source.read_bytes()
    r=op.plan(b,source,board_hint='synthetic',net=net)
    assert r['complete'],r
    assert r['manufacturer_scalar_pin_witnesses']
    assert not r['ordinary_reclassification'] and not r['GPIO_application_mode_or_current_assumed']
    assert r['request']['width_nm']==200000 and source.read_bytes()==before


@pytest.mark.parametrize('fault',['power_pin','dnp','wrong_mpn','wrong_package','aggressor','no_gpio','missing_current_context'])
def test_no_name_or_caller_claim_can_create_scalar_scope(tmp_path,fault,monkeypatch):
    import cec_sensitive_scalar_corner_stage as owner
    source,net=case(tmp_path);b=pcbnew.LoadBoard(str(source));fp=b.FindFootprintByReference('X1')
    if fault=='power_pin':next(iter(fp.Pads())).SetPinType('power_in')
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='wrong_mpn':fp.SetValue('NOT_A_MANUFACTURER_MODEL');fp.SetField('MPN','unknown')
    elif fault=='wrong_package':fp.SetFPID(pcbnew.LIB_ID('fixture','unknown'))
    elif fault=='no_gpio':next(iter(fp.Pads())).SetNumber('1')
    elif fault=='aggressor':monkeypatch.setattr(owner.field,'classify_net',lambda *a,**k:dict(victim=True,aggressor=True,power=False))
    else:monkeypatch.setattr(owner,'eligible_nets',lambda *a,**k:{})
    r=op.plan(b,source,board_hint='synthetic',net=net)
    assert not r['complete'] and not r['ordinary_reclassification']


@pytest.mark.parametrize('width',[.22,.25,.3])
def test_actual_sensitive_authored_width_is_not_replaced_with_default(tmp_path,width):
    source,net=case(tmp_path)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{
        'classes':[{'name':'Default','track_width':.2},{'name':'Sense','track_width':width,'clearance':.2}],
        'netclass_assignments':{net:['Sense']}}}))
    r=op.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',net=net)
    assert r['complete'] and r['request']['width_nm']==round(width*1e6)
    assert r['request']['source_class']=='Sense'


@pytest.mark.parametrize('fault',[None,'wrong_width','foreign_net','new_barrel'])
def test_saved_actual_scalar_join_and_negative_delta_controls(tmp_path,fault):
    source,net=case(tmp_path);b=pcbnew.LoadBoard(str(source));plan=op.plan(b,source,board_hint='synthetic',net=net)
    assert plan['complete'];pads=op._pads(b,plan['request'])
    child=force._copy_family(source,tmp_path/'child')
    if fault=='new_barrel':
        via=pcbnew.PCB_VIA(b);via.SetPosition(pads[0].GetPosition());via.SetWidth(600000)
        via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(pads[0].GetNet());b.Add(via)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pads[0].GetPosition());t.SetEnd(pads[1].GetPosition())
    t.SetWidth(250000 if fault=='wrong_width'else 200000);t.SetLayer(pcbnew.F_Cu)
    t.SetNetCode(0 if fault=='foreign_net'else pads[0].GetNetCode());b.Add(t)
    if fault=='foreign_net':
        # The identity-preserving saver already refuses an authored unnetted
        # short; do not weaken that earlier guard merely to reach a later one.
        with pytest.raises(field._ProposalUnknown):field._save_field_snapshot(b,child)
        return
    field._save_field_snapshot(b,child)
    r=op.receive(source,child,board_hint='synthetic',net=net)
    if fault in ('wrong_width','foreign_net'):assert not r['ok'],r
    else:
        # Scope receiving alone never grants barrel/process or field/current
        # acceptance. Those independent shared gates must still pass.
        assert r['ok']and not r['release_authority'],r
        assert not stage.admitted({'operator':True})


@pytest.mark.parametrize('net',[None,'',False,3])
def test_stage_requires_explicit_sensitive_source_net_before_namespace(tmp_path,net):
    with pytest.raises(ValueError,match='explicit_bounded_received_operator'):
        stage.run(tmp_path/'absent',tmp_path/'out',board_hint='synthetic',
            expected_source_sha256='0'*64,operator='sensitive_scalar',net=net)


def test_worker_refused_scalar_plan_does_not_construct_or_publish(tmp_path,monkeypatch):
    source,net=case(tmp_path)
    monkeypatch.setattr(stage,'identity',lambda *a:{'epoch':'exact'})
    monkeypatch.setattr(op,'plan',lambda *a,**k:{'complete':False})
    monkeypatch.setattr(op,'construct_private',lambda *a,**k:pytest.fail('no positive Source scope'))
    r=stage.worker(dict(source=str(source),directory=str(tmp_path),board_hint='synthetic',
        assembly_instance=None,identity={'epoch':'exact'},operator='sensitive_scalar',net=net))
    assert r['gates']=={} and not(tmp_path/'publication.json').exists()
