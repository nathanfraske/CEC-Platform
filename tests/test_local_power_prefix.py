from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import pytest
import cec_local_power_prefix as prefix


@pytest.fixture(autouse=True)
def isolate_mocked_oracle_environment(monkeypatch):
    # Several transaction tests replace the real environment-restoring oracle
    # context with nullcontext. Restore the newly published authority as the
    # real context does, so it cannot leak into unrelated native regressions.
    monkeypatch.setenv('CEC_POURFIRST_STATE', '')


def complete():
    return dict(source_unchanged=True, placement_unchanged=True,
                parent_copper={'ok':True}, power={'exact_admission':{'passed':True}},
                power_obligations={'ok':True},
                ground={'ok':True}, local_pi_final={'ok':True},
                kelvin_final={'ok':True}, qualified_pairs={'ok':True},
                score_admission={'accepted':True})


def test_only_local_pi_first_production_schedule_gets_the_new_barrier():
    args=dict(power_enabled=True, local_pi={'ok':True},policy='critical-first')
    assert prefix.eligible(**args)
    for changes in ({'enabled':False},{'power_enabled':False},{'local_pi':None},
                    {'local_pi':{'ok':False}},{'local_pi':{'ok':True,'rolled_back':True}},
                    {'policy':'power-first'}):
        assert not prefix.eligible(**dict(args,**changes))


@pytest.mark.parametrize('field',list(complete()))
def test_missing_or_failed_independent_proof_cannot_admit(field):
    row=complete();assert prefix.admitted(row)
    row.pop(field);assert not prefix.admitted(row)
    row=complete()
    if field=='power':row[field]['exact_admission']['passed']=False
    elif isinstance(row[field],dict):row[field]={k:False for k in row[field]}
    else:row[field]=False
    assert not prefix.admitted(row)


def test_constructor_error_cannot_be_hidden_by_other_passing_terms():
    row=complete();row['error']='native worker failed'
    assert not prefix.admitted(row)


def test_proof_has_no_board_reference_or_coordinate_dependence():
    for board,refs,xy in [('alpha',['U900','C875'],[10,20]),('beta',['DEVICE','BYPASS'],[-40,80])]:
        row=complete();row.update(board=board,refs=refs,position=xy)
        assert prefix.admitted(row)


def test_power_reuse_requires_every_domain_and_native_connection():
    assert prefix.power_connected({'x':{'available':True,'connected':True}},['x'],['x'])
    assert not prefix.power_connected({'x':{'available':True,'connected':False}},['x'],[])
    assert not prefix.power_connected({},['x'],[])
    assert prefix.power_connected({'x':{'available':False}},['x'],[])
    assert not prefix.power_connected({'x':{'available':False}},['x'],['x'])


def test_failed_local_pi_is_rejected_before_any_native_file_work(tmp_path):
    with pytest.raises(ValueError,match='complete admitted local PI'):
        prefix.construct(None,tmp_path/'missing.kicad_pcb',tmp_path/'out',local_pi={'ok':False})
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('failure',[None,'hash','zone','copper','placement','pair','score','power','refill'])
def test_reuse_revalidates_each_saved_boundary(tmp_path,monkeypatch,failure):
    import hashlib
    import pcbnew,cec_fr,cec_full_pipeline as pipeline,cec_synth_pipeline as synth
    import cec_ground_plane as ground,cec_score,cec_stage_admission
    import cec_placement_route_prefix as pairs
    parent=tmp_path/'parent.kicad_pcb';parent.write_bytes(b'parent')
    source=tmp_path/'paired.kicad_pcb';source.write_bytes(b'paired')
    state=tmp_path/'state.json';state.write_bytes(b'authority')
    evidence=complete()
    evidence.update(ok=True,selected=str(parent),state=str(state),
        selected_sha256=hashlib.sha256(parent.read_bytes()).hexdigest(),
        state_sha256=hashlib.sha256(state.read_bytes()).hexdigest())
    evidence['power']['frozen_nets']=['RAIL']
    if failure=='hash':
        state.write_bytes(b'changed')
        with pytest.raises(ValueError,match='evidence changed'):
            prefix.reuse(None,source,tmp_path/'out',evidence)
        assert not (tmp_path/'out').exists()
        return
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda p:SimpleNamespace(path=p,GetTracks=lambda:[]))
    monkeypatch.setattr(cec_fr,'copy_project_sidecars',lambda *a:None)
    monkeypatch.setattr(cec_fr,'refill_zones',lambda p:failure!='refill')
    monkeypatch.setattr(cec_fr,'copper_geometry_prefix_contract',lambda *a:{})
    monkeypatch.setattr(cec_fr,'check_copper_geometry_prefix',lambda *a:{'ok':failure!='copper'})
    monkeypatch.setattr(pairs,'capture',lambda *a:{})
    monkeypatch.setattr(pairs,'check_qualified_pairs',lambda *a:{'ok':failure!='pair'})
    monkeypatch.setattr(ground,'_zone_declaration_signature',
        lambda board:[['zone','RAIL',1 if failure=='zone' and board.path!=str(parent) else 0]])
    monkeypatch.setattr(pipeline,'_placement_position_signature',
        lambda p:('moved' if failure=='placement' and p!=parent else 'poses'))
    monkeypatch.setattr(synth,'_oracle_env',lambda p:nullcontext())
    monkeypatch.setattr(synth,'_priority_power_authority_isolated',
        lambda *a:{'RAIL':{'available':True,'connected':failure!='power'}})
    monkeypatch.setattr(cec_score,'score',lambda p:SimpleNamespace(drc=0,unconnected=3,detail={}))
    monkeypatch.setattr(cec_stage_admission,'evaluate',lambda *a:{'accepted':failure!='score'})
    result=prefix.reuse(SimpleNamespace(params={}),source,tmp_path/'out',evidence)
    assert result['ok']==(failure is None)
    assert bool(result['selected'])==(failure is None)
    assert not result['release_accepted'] and not result['residual_allowed']
    assert source.read_bytes()==b'paired' and parent.read_bytes()==b'parent'


@pytest.mark.parametrize('fail_stage',[None,'kelvin','power','ground','local_pi','parent','source','obligation'])
def test_transaction_order_and_failure_boundary(tmp_path,monkeypatch,fail_stage):
    import pcbnew,cec_fr,cec_full_pipeline as pipeline,cec_synth_pipeline as synth
    import cec_precision_route as precision,cec_route_preflight as preflight
    import cec_decoupler_cell as cells,cec_ground_plane as ground,cec_score
    import cec_placement_route_prefix as pairs,cec_stage_admission
    source=tmp_path/'source.kicad_pcb';source.write_bytes(b'immutable-source')
    cfg=SimpleNamespace(params={});seen=[]
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda p:SimpleNamespace(GetTracks=lambda:[]))
    monkeypatch.setattr(pipeline,'_placement_position_signature',lambda p:('poses',))
    monkeypatch.setattr(synth,'config_with_board_route_authority',lambda cfg,p:(cfg,{'ok':True}))
    monkeypatch.setattr(synth,'_oracle_env',lambda p:nullcontext())
    monkeypatch.setattr(synth,'_priority_power_authority_isolated',
        lambda path,nets:{net:dict(available=True,connected=net!='OMITTED') for net in nets})
    monkeypatch.setattr(cec_fr,'_pourfirst_state',
        lambda:dict(frozen_nets=['OMITTED']) if fail_stage=='obligation' else {})
    monkeypatch.setattr(cec_fr,'copper_geometry_prefix_contract',lambda *a:{})
    monkeypatch.setattr(cec_fr,'check_copper_geometry_prefix',lambda *a:{'ok':fail_stage!='parent'})
    monkeypatch.setattr(pairs,'capture',lambda *a:{})
    monkeypatch.setattr(pairs,'check_qualified_pairs',lambda *a:{'ok':True})
    monkeypatch.setattr(preflight,'compile_route_reservations',lambda p:{'enabled':True})
    monkeypatch.setattr(preflight,'priority_kelvin_avoid',lambda *a,**kw:())
    monkeypatch.setattr(cec_score,'score',lambda p:SimpleNamespace(drc=0,unconnected=3,kelvin_ok=True,detail={}))
    monkeypatch.setattr(cec_stage_admission,'evaluate',lambda *a:{'accepted':True})
    monkeypatch.setattr(cells,'audit_board',lambda *a,**kw:{'ok':fail_stage!='local_pi'})
    def kelvin(src,dst,**kw):
        seen.append('kelvin');assert kw['do_pairs'] is False
        Path(dst).write_bytes(b'kelvin')
        if fail_stage=='source':source.write_bytes(b'changed-by-test')
        return {'kelvin':{'refused':{'RAIL':['endpoint']} if fail_stage=='kelvin' else {}},'locked_nets':['RAIL']}
    def power(src,pours,state,dst):
        seen.append('power');assert Path(src).read_bytes()==b'kelvin'
        Path(dst).write_bytes(b'power')
        return {'exact_admission':{'passed':fail_stage!='power'},'frozen_nets':['RAIL']}
    def plane(src,dst,**kw):
        seen.append('ground');assert kw['required_via_uuids']==['owned-return']
        Path(dst).write_bytes(b'filled-power');Path(dst).with_suffix('.pourfirst-state.json').write_text('{}')
        return {'ok':fail_stage!='ground'}
    monkeypatch.setattr(precision,'precision_route',kelvin)
    monkeypatch.setattr(synth,'_compile_post_priority_power_state',power)
    monkeypatch.setattr(ground,'fill_and_admit',plane)
    result=prefix.construct(cfg,source,tmp_path/'run',local_pi={'ok':True,'required_via_uuids':['owned-return']})
    expected=['kelvin'] if fail_stage=='kelvin' else ['kelvin','power'] if fail_stage=='power' else ['kelvin','power','ground']
    assert seen==expected
    assert result['ok']==(fail_stage is None)
    assert bool(result['selected'])==(fail_stage is None)
    assert not result['release_accepted'] and not result['residual_allowed']
    assert (tmp_path/'run'/'report.json').is_file()
    if fail_stage!='source':assert source.read_bytes()==b'immutable-source'
