import copy
import json

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew

import cec_final_residual as residual
import cec_completion_evidence as completion
import cec_score
from test_lastmile import _board


def make_board(tmp_path, *, joined=False, offset=0., rotation=0):
    def xy(x, y):
        if rotation == 90:
            x, y = 20-y, x
        return x+offset, y+offset
    coords=[xy(5,10),xy(15,10),xy(10,10)]
    board=_board([(*coords[0],'TARGET'),(*coords[1],'TARGET'),(*coords[2],'FOREIGN')],
                 edge=(offset,offset,20+offset,20+offset))
    if joined:
        track=pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I_MM(*coords[0]));track.SetEnd(pcbnew.VECTOR2I_MM(*coords[1]))
        track.SetNetCode(board.GetNetcodeFromNetname('TARGET'))
        track.SetWidth(200000);track.SetLayer(pcbnew.F_Cu);board.Add(track)
    for index,fp in enumerate(board.GetFootprints()):
        fp.SetReference('RENAMED_'+str(index))
        for pad in fp.Pads():pad.SetNumber('1')
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default',track_width=.2,clearance=.2,via_diameter=.6,via_drill=.3)]))))
    return path


@pytest.mark.parametrize('rotation,offset',[(0,0.),(90,27.5)])
def test_native_final_survey_covers_actual_open_and_never_claims_search(tmp_path, rotation, offset):
    path=make_board(tmp_path,rotation=rotation,offset=offset)
    before=residual._identity(path)
    report=residual.measure(path)
    assert residual.valid_snapshot(report),report
    assert report['unconnected_count']==1 and report['details_complete']
    assert report['source_identity']==before==residual._identity(path)
    cert=report['residual_details'][0]['certificate']
    assert cert['net']=='TARGET' and cert['width_mm']==.2
    assert cert['search']['performed'] is False
    assert cert['search']['layer_access_proven'] is False
    assert any(row['net']=='FOREIGN' for row in cert['dominant_blockers'])
    assert all(p['uuid'] and p['ref'].startswith('RENAMED_') for p in cert['endpoints'])
    assert all(p['kind']=='pad' for p in cert['endpoints'])
    assert all(p['copper_layers']==['F.Cu'] for p in cert['endpoints'])
    assert len(cert['layers'])==4
    assert not report['release_authority']


def test_clean_connectivity_does_not_claim_other_drc_or_fab_pass(tmp_path):
    path=make_board(tmp_path,joined=True)
    report=residual.measure(path)
    assert residual.valid_snapshot(report) and report['unconnected_count']==0
    assert report['details_complete'] and not report['residual_details']
    assert not report['release_authority']


@pytest.mark.parametrize('kwargs',[dict(max_details=0),dict(wall_timeout_s=0)])
def test_bounded_details_keep_complete_open_inventory(tmp_path,kwargs):
    path=make_board(tmp_path)
    report=residual.measure(path,**kwargs)
    assert residual.valid_snapshot(report)
    assert report['unconnected_count']==report['details_missing']==1
    assert len(report['unconnected_items'])==1
    assert not report['details_complete'] and not report['residual_details']


def test_native_stale_uuid_is_logged_not_guessed(tmp_path,monkeypatch):
    path=make_board(tmp_path)
    monkeypatch.setattr(cec_score,'_run_drc',lambda *args:dict(unconnected_items=[
        dict(items=[dict(uuid='missing',pos=dict(x=5,y=10)),dict(uuid='also_missing')])]))
    report=residual.measure(path)
    assert report['drc_complete'] and not report['details_complete']
    assert not report['residual_details'] and 'UUID' in report['errors'][0]['error']


@pytest.mark.parametrize('suffix',['.kicad_pcb','.kicad_pro','.kicad_dru'])
def test_native_source_mutation_invalidates_whole_survey(tmp_path,monkeypatch,suffix):
    path=make_board(tmp_path)
    real=cec_score._run_drc
    def mutate(*args):
        data=real(*args)
        target=path.with_suffix(suffix)
        target.write_text(target.read_text()+'\n' if target.exists() else '\n')
        return data
    monkeypatch.setattr(cec_score,'_run_drc',mutate)
    report=residual.measure(path)
    assert not residual.valid_snapshot(report) and not report['source_unchanged']
    assert not report['residual_details']


def historical():
    return dict(final_completion=dict(refused_details=[dict(net='OLD',distance_mm=1.,
        certificate=dict(net='OLD',endpoints=[dict(ref='STALE',x_mm=0.,y_mm=0.)]))]))


def test_fresh_final_only_supersedes_all_historical_endpoint_hints(tmp_path):
    report=residual.measure(make_board(tmp_path))
    data=dict(historical(),final_residual=report)
    pairs=completion.refusal_certificates(data)
    assert len(pairs)==1 and pairs[0][1]['net']=='TARGET'
    hints=completion.placement_hints(data)
    assert 'STALE' not in {row['ref'] for row in hints['hints']}
    assert hints['final_residual_scope']['valid']
    assert not hints['final_residual_scope']['historical_fallback']
    assert completion.placement_hints(historical())['hints'][0]['ref']=='STALE'
    import cec_certificate_repair as repair
    route_rows=repair.refusal_certificates(dict(completion_report=data))
    assert len(route_rows)==1 and route_rows[0]['certificate']['net']=='TARGET'
    # A later live route probe supersedes even this final snapshot; it must
    # not shadow a newly connected net or more recent blocking geometry.
    refreshed=repair._planning_completion_with_live_report(
        dict(completion_report=data),[],dict(refused_details=[]))
    assert 'final_residual' not in refreshed
    assert repair.refusal_certificates(refreshed)==[]


@pytest.mark.parametrize('state',['clean','partial','tampered','failed','none'])
def test_no_fallback_to_stale_attempts_when_final_is_empty_or_failed(tmp_path,state):
    report=residual.measure(make_board(tmp_path,joined=state=='clean'),max_details=0)
    if state=='tampered':report['unconnected_count']+=1
    if state=='failed':report['source_unchanged']=False
    if state=='none':report=None
    assert completion.refusal_certificates(dict(historical(),final_residual=report))==[]


def test_malformed_digest_payload_refuses_without_crashing():
    report=dict(schema=1,source_unchanged=True,drc_complete=True,
                source_identity={'.kicad_pcb':'source'},unconnected_count=0,
                unconnected_items=[],residual_details=[],bad=float('nan'))
    assert not residual.valid_snapshot(report)


def test_clear_ray_projection_respects_smd_and_through_layer_access():
    cert=dict(endpoints=[dict(endpoint='a',copper_layers=['F.Cu']),
                         dict(endpoint='b',copper_layers=['F.Cu','SIG2','B.Cu'])],
              layers=[dict(layer='F.Cu',endpoint_escape=[
                  dict(endpoint='a',clear_rays=['N']),dict(endpoint='b',clear_rays=['S'])]),
                      dict(layer='SIG2',endpoint_escape=[
                  dict(endpoint='a',clear_rays=['E']),dict(endpoint='b',clear_rays=['W'])])])
    rays=completion._endpoint_clear_rays(cert)
    assert rays['a']=={'N'} and rays['b']=={'S','W'}


def test_loaded_through_pad_advertises_all_actual_copper_layers(tmp_path):
    path=make_board(tmp_path)
    board=pcbnew.LoadBoard(str(path))
    target=next(pad for fp in board.GetFootprints() for pad in fp.Pads()
                if pad.GetNetname()=='TARGET')
    target.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    target.SetLayerSet(pcbnew.LSET.AllCuMask());target.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    pcbnew.SaveBoard(str(path),board,True)
    report=residual.measure(path)
    assert report['details_complete']
    lengths=[len(row['copper_layers']) for row in report['residual_details'][0]['certificate']['endpoints']]
    assert sorted(lengths)==[1,4]


def test_final_diagnostic_consistency_is_a_required_release_gate():
    import cec_synth_pipeline as synth
    terms={key:True for key in synth._ROUTE_ORACLE_GATE_TERMS}
    terms['final_residual_consistent']=False
    assert not synth._route_oracle_accepts(terms)
    terms.pop('final_residual_consistent')
    with pytest.raises(ValueError):synth._route_oracle_accepts(terms)


def test_native_final_trace_joins_exact_endpoints_without_claiming_causal_origin(tmp_path):
    import cec_blocker_provenance as provenance
    report=residual.measure(make_board(tmp_path))
    rows=residual.trace_rows(report)
    assert len(rows)==1 and len(rows[0]['uuids'])==2
    blockers=provenance.final_blockers(dict(unconnected_items=report['unconnected_items']))
    joined=provenance.join_events(blockers,rows)
    assert joined[0]['causal_chain'][0]['stage']=='final_endpoint_geometry'
    assert joined[0]['causal_chain'][0]['certainty']=='associated'
    assert not joined[0]['origin_known']
    assert rows[0]['detail']['report_ref']=='completion_report.final_residual'


def test_production_dispatch_recognizes_fresh_only_and_refuses_stale_fallback(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import cec_synth_pipeline as synth
    path=make_board(tmp_path)
    report=residual.measure(path)
    calls=[]
    def run(*args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1,stdout='',stderr='intentional worker stand-in')
    monkeypatch.setattr(synth.subprocess,'run',run)
    _,result=synth._route_oracle_certificate_repair(str(path),dict(final_residual=report),str(tmp_path))
    assert len(calls)==1 and 'error' in result
    calls.clear()
    _,result=synth._route_oracle_certificate_repair(str(path),dict(historical(),final_residual=None),str(tmp_path))
    assert not calls and result['skipped']=='no_refusal_certificates'
