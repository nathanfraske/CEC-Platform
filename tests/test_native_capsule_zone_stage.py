"""Real saved capsule containment, exact phase replay and unchanged authority."""
import copy
import math
import os
import re
from pathlib import Path

import pcbnew
import pytest
import cec_native_capsule_zone_stage as stage
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,monkeypatch,angle=0,mirror=False,layer=pcbnew.F_Cu,net='/renamed/DECLARED_SUPPLY'):
    def at(x,y):
        x,y=x-20,y-20
        if mirror:x=-x
        a=math.radians(angle)
        return round(20+x*math.cos(a)-y*math.sin(a),6),round(20+x*math.sin(a)+y*math.cos(a),6)
    b=_board([(*at(10,15),net),(*at(16,21),net)],edge=(0,0,40,40))
    for fp in b.GetFootprints():
        p=next(iter(fp.Pads()));p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));p.SetLayerSet(pcbnew.LSET.AllCuMask())
    ts=[track(b,net,at(*a),at(*z),layer=layer,width=1.) for a,z in
        (((10.7,15),(16,15)),((16,15),(16,20.3)))]
    face=b.GetLayerName(layer)
    # Explicit SYNTHETIC API context; no real-board power budget or qualification.
    domain=dict(net=net,complete=True,missing_refs=[],source_refs=['X1'],sink_refs=['X2'],amps=.1)
    contract=dict(net=net,amps=.1,routing_layers=[face],required_by_layer_mm={face:.2})
    domains={net:domain};contracts={net:contract}
    monkeypatch.setattr(stage.topology,'board_current_domains',lambda *a,**k:copy.deepcopy(domains))
    monkeypatch.setattr(stage.topology,'route_width_contracts',lambda *a,**k:copy.deepcopy(contracts))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    return b,source,ts,domains,contracts


def saved(tmp_path,monkeypatch,*,retain_source_tracks=False,**kwargs):
    b,source,ts,domains,contracts=fixture(tmp_path,monkeypatch,**kwargs)
    ids=[force._uid(t) for t in ts]
    proposal=stage.plan(b,source,ids,board_hint='synthetic',retain_source_tracks=retain_source_tracks)
    made=stage.owner.materialize(b,proposal);stage.owner.fill(b,proposal,made['zone_uuid'],timeout_s=10.)
    stage.additive._ground_refill(b)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(b,child)
    return source,child,[dict(plan=proposal,materialized=made)],domains,contracts


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('retain',[False,True])
def test_rotated_mirrored_saved_native_phase_preserves_full_capsules(tmp_path,monkeypatch,angle,mirror,layer,retain):
    source,child,rows,_,_=saved(tmp_path,monkeypatch,angle=angle,mirror=mirror,layer=layer,retain_source_tracks=retain)
    old=(source.read_bytes(),child.read_bytes())
    proof=stage.receive_literal_phase(source,child,rows,board_hint='synthetic',retain_source_tracks=retain)
    assert proof['ok'] and proof['complete'],proof
    assert proof['exact_source_phase_and_native_ground_refill_received']
    assert proof['saved_full_original_capsule_receiving'][0]['verified_track_count']==2
    ids={q['uuid'] for q in rows[0]['plan']['source_tracks']}
    actual={force._uid(t) for t in pcbnew.LoadBoard(str(child)).GetTracks()}
    assert (ids<=actual) if retain else not (ids & actual)
    assert set(proof['retained_track_uuids'])==(ids if retain else set())
    assert set(proof['retired_track_uuids'])==(set() if retain else ids)
    assert not proof['current_qualified'] and not proof['release_authority']
    assert old==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('bad',['domain_missing','domain_incomplete','missing_refs','empty_source','empty_sink',
    'wrong_domain_net','domain_amps','bool_amps','disagree','contract_missing','face_missing','below_floor',
    'reference_face','mask','group','locked','non45','zero','duplicate','missing'])
def test_no_invented_authority_or_ordinary_route_escape_hatch(tmp_path,monkeypatch,bad):
    b,source,ts,domains,contracts=fixture(tmp_path,monkeypatch);net=ts[0].GetNetname()
    ids=[force._uid(t) for t in ts]
    if bad=='domain_missing':domains.clear()
    elif bad=='domain_incomplete':domains[net]['complete']=False
    elif bad=='missing_refs':domains[net]['missing_refs']=['not_present']
    elif bad=='empty_source':domains[net]['source_refs']=[]
    elif bad=='empty_sink':domains[net]['sink_refs']=[]
    elif bad=='wrong_domain_net':domains[net]['net']='/other'
    elif bad=='domain_amps':domains[net]['amps']=float('nan')
    elif bad=='bool_amps':contracts[net]['amps']=True
    elif bad=='disagree':contracts[net]['amps']=.2
    elif bad=='contract_missing':contracts.clear()
    elif bad=='face_missing':contracts[net]['required_by_layer_mm'].clear()
    elif bad=='below_floor':contracts[net]['required_by_layer_mm']['F.Cu']=1.000001
    elif bad=='reference_face':
        for t in ts:t.SetLayer(pcbnew.In1_Cu)
        contracts[net].update(routing_layers=['In1.Cu'],required_by_layer_mm={'In1.Cu':.2})
    elif bad=='mask':ts[0].SetHasSolderMask(True)
    elif bad=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(ts[0])
    elif bad=='locked':ts[0].SetLocked(True)
    elif bad=='non45':ts[0].SetStart(ts[0].GetStart()+pcbnew.VECTOR2I(1,1))
    elif bad=='zero':ts[0].SetEnd(ts[0].GetStart())
    elif bad=='duplicate':ids=[ids[0]]*2
    else:ids[0]='not_a_native_source'
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):stage.plan(b,source,ids,board_hint='synthetic')
    assert field._field_snapshot_inventory(b)==before and not list(b.Zones())


@pytest.mark.parametrize('fault',['empty','duplicate','source_changed','plan_polygon','plan_width',
    'worker_pass','wrong_zone','missing_zone','unfilled','via','pad','metadata','sidecar','unlisted_track'])
@pytest.mark.parametrize('retain',[False,True])
def test_worker_flags_or_rehashed_recipes_cannot_launder_other_saved_changes(tmp_path,monkeypatch,fault,retain):
    source,child,rows,_,_=saved(tmp_path,monkeypatch,retain_source_tracks=retain);rows=copy.deepcopy(rows)
    if fault=='empty':rows=[]
    elif fault=='duplicate':rows*=2
    elif fault=='source_changed':
        b=pcbnew.LoadBoard(str(source));next(iter(b.GetTracks())).SetWidth(1100000)
        field._save_field_snapshot(b,source)
    elif fault in ('plan_polygon','plan_width'):
        p=rows[0]['plan']
        if fault=='plan_polygon':p['polygon_nm'][0][0]-=1000000
        else:p['required_width_nm']-=1
        unsigned=dict(p);unsigned.pop('plan_sha256');p['plan_sha256']=stage.owner._digest(unsigned)
        rows[0]['materialized']['plan_sha256']=p['plan_sha256']
    elif fault=='worker_pass':rows[0]['materialized']['new_capacity_credited']=True
    elif fault=='wrong_zone':rows[0]['materialized']['zone_uuid']='not_the_saved_zone'
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    else:
        b=pcbnew.LoadBoard(str(child));zone=next(iter(b.Zones()))
        if fault=='missing_zone':discard_items(b,[zone])
        elif fault=='unfilled':zone.UnFill()
        elif fault=='via':
            v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(8,8));v.SetNet(zone.GetNet())
            v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        elif fault=='pad':next(iter(next(iter(b.GetFootprints())).Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
        elif fault=='metadata':b.SetCopperLayerCount(6)
        else:track(b,zone.GetNetname(),(28,28),(29,28),width=.2)
        field._save_field_snapshot(b,child)
    old=(source.read_bytes(),child.read_bytes())
    proof=stage.receive_literal_phase(source,child,rows,board_hint='synthetic',retain_source_tracks=retain)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    assert not proof['release_authority'] and old==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('kwargs',[dict(max_changes=0),dict(max_changes=True),dict(max_fills=17),
    dict(max_fills=1),dict(allow_locked_source=1),dict(sense_timeout_s=float('nan')),
    dict(reporting_build=None),dict(board_hint=''),dict(expected_source_sha256='not-a-hash'),
    dict(retain_source_tracks=1),dict(retain_source_tracks=None),dict(retain_source_tracks='true')])
def test_invalid_bounded_stage_context_creates_no_family(tmp_path,kwargs):
    params=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native')
    params.update(kwargs);dest=tmp_path/'not_created'
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',dest,**params)
    assert not dest.exists()


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('retain',[False,True])
def test_saved_phase_reaches_full_native_zero_open_stage_without_current_sharing(tmp_path,monkeypatch,layer,retain):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    b,source,ts,_,_=fixture(tmp_path,monkeypatch,layer=layer)
    before=source.read_bytes()
    result=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),max_changes=1,max_fills=2,retain_source_tracks=retain)
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['after_contours']['finding_count']<result['before_contours']['finding_count']
    assert result['independent_whole_source_receiving']['ok']
    assert result['source_family_and_code_unchanged'] and source.read_bytes()==before
    assert not result['branch_sharing_assumed'] and not result['routing_admitted'] and not result['fab_ready']


@pytest.mark.parametrize('fault',['current_unknown','field_blocker','absolute_evidence_unavailable','absolute_comparison'])
@pytest.mark.parametrize('retain',[False,True])
def test_saved_full_capsules_cannot_override_other_independent_receivers(tmp_path,monkeypatch,fault,retain):
    source,child,rows,_,_=saved(tmp_path,monkeypatch,retain_source_tracks=retain)
    if fault=='current_unknown':
        monkeypatch.setattr(stage.current,'receive',lambda *a,**k:dict(ok=True,complete=False))
    elif fault=='field_blocker':
        monkeypatch.setattr(stage.field,'field_coupling_summary',lambda p,**k:dict(candidate=Path(p)==child))
        monkeypatch.setattr(stage.field,'blocker_keys',lambda r:{'new_blocker'} if r['candidate'] else set())
    elif fault=='absolute_evidence_unavailable':
        def unavailable(*a,**k):raise ValueError('injected_native_absolute_evidence_unavailable')
        monkeypatch.setattr(stage.sense,'replay',unavailable)
    else:
        monkeypatch.setattr(stage.sense,'compare_contour_preservation',lambda *a,**k:
            dict(comparison_complete=True,same_evidence=False))
    before=(source.read_bytes(),child.read_bytes())
    result=stage.receive(source,child,rows,board_hint='synthetic',retain_source_tracks=retain)
    assert not result['ok'] and not result['complete'] and result['errors'],result
    assert result['independent_saved_phase']['ok']
    assert not result['new_capacity_credited'] and not result['release_authority']
    assert before==(source.read_bytes(),child.read_bytes())


@pytest.mark.parametrize('retain',[False,True])
def test_retention_mode_is_an_explicit_receiving_contract_not_a_worker_claim(tmp_path,monkeypatch,retain):
    source,child,rows,_,_=saved(tmp_path,monkeypatch,retain_source_tracks=retain)
    for claimed in (not retain,1,None,'true'):
        proof=stage.receive_literal_phase(source,child,rows,board_hint='synthetic',retain_source_tracks=claimed)
        assert not proof['ok'] and not proof['complete'] and proof['errors']


@pytest.mark.parametrize('fault',['remove','width','net','locked'])
def test_retained_native_tracks_are_exact_not_a_drawing_or_capacity_echo(tmp_path,monkeypatch,fault):
    source,child,rows,_,_=saved(tmp_path,monkeypatch,retain_source_tracks=True)
    b=pcbnew.LoadBoard(str(child));uid=rows[0]['plan']['source_tracks'][0]['uuid']
    t=next(t for t in b.GetTracks() if force._uid(t)==uid)
    if fault=='remove':discard_items(b,[t])
    elif fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='net':
        # Inject at the saved boundary: KiCad's load/save path can reassign a
        # deliberately shorted foreign track. The literal receiver must also
        # refuse authored tampering, irrespective of native normalization.
        text,stored,_=stage.syntax._read(child)
        record=next(q for q in stored if q['uuid'].strip('"')==uid)
        block=text[record['start']:record['end']]
        altered,n=re.subn(r'\(net\s+(?:"(?:[^"\\]|\\.)*"|[^\s()]+)\s*\)',
            '(net "/synthetic/FOREIGN_SUPPLY")',block,count=1)
        assert n==1 and altered!=block
        child.write_text(text[:record['start']]+altered+text[record['end']:])
    else:t.SetLocked(not t.IsLocked())
    if fault!='net':field._save_field_snapshot(b,child)
    proof=stage.receive_literal_phase(source,child,rows,board_hint='synthetic',retain_source_tracks=True)
    assert not proof['ok'] and not proof['complete'] and proof['errors']


def test_local_field_refusal_is_screened_before_it_can_poison_a_whole_batch(tmp_path,monkeypatch):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    b,source,_,_,_=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(stage.field,'field_coupling_summary',lambda p,**k:dict(candidate=Path(p)!=source))
    monkeypatch.setattr(stage.field,'blocker_keys',lambda r:{'new_blocker'} if r['candidate'] else set())
    result=stage.run(source,tmp_path/'refused',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),max_changes=1,max_fills=2)
    assert result['ok'] and result['complete'] and not result['changed'] and result['candidate']==str(source)
    assert not result['records'] and any('field_screen_refused' in row.get('refusal','') for row in result['attempts'])
    assert all(not row['accepted'] for row in result['attempts'])
