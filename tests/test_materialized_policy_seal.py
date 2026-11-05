"""Native-save side effects must not erase a resumed candidate's rule policy."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import cec_synth_pipeline as synth


def policy():
    return {'meta':{'filename':'source.kicad_pro'},
        'net_settings':{'classes':[{'name':'Default','clearance':.2},
            {'name':'DIFFERENTIAL','diff_pair_width':.2,'diff_pair_gap':.37}],
            'netclass_patterns':[{'pattern':'arbitrary/*','netclass':'DIFFERENTIAL'}]},
        'board':{'design_settings':{'rules':{'min_clearance':.17,'min_through_hole_diameter':.3}}}}


@pytest.mark.parametrize('atomic',[False,True])
@pytest.mark.parametrize('in_place',[False,True])
def test_rule_policy_survives_late_native_default_write(tmp_path,monkeypatch,atomic,in_place):
    source=tmp_path/'source.kicad_pcb';source.write_text('source geometry')
    project=source.with_suffix('.kicad_pro');project.write_text(json.dumps(policy()))
    source.with_suffix('.kicad_dru').write_text('(version 1)\n(rule "existing qualified process")\n')
    expected=project.read_bytes();out=source if in_place else tmp_path/'target.kicad_pcb'
    def defaults(path):
        Path(path).with_suffix('.kicad_pro').write_text(json.dumps(
            {'net_settings':{'classes':[{'name':'Default','diff_pair_gap':.25}]}}))
    def emit(cand,cfg,path):
        Path(path).write_text('candidate geometry');defaults(path);return path
    monkeypatch.setattr(synth,'_materialize_rehydrated_board',emit)
    monkeypatch.setattr(synth,'_normalize_materialized_item_ids',defaults)
    monkeypatch.setattr(synth,'_admit_materialized_power_prefix',lambda c,p:defaults(p))
    candidate=SimpleNamespace(source_board=str(source),protected_power_prefix={'items':1} if atomic else {})
    synth.materialize(candidate,SimpleNamespace(),str(out))
    result=json.loads(out.with_suffix('.kicad_pro').read_text())
    assert result['net_settings']==policy()['net_settings']
    assert result['board']['design_settings']==policy()['board']['design_settings']
    assert out.with_suffix('.kicad_dru').read_bytes()==source.with_suffix('.kicad_dru').read_bytes()
    assert project.read_bytes()==expected


def test_rule_authority_change_during_transaction_refuses_publication(tmp_path,monkeypatch):
    source=tmp_path/'source.kicad_pcb';source.write_text('source')
    project=source.with_suffix('.kicad_pro');project.write_text(json.dumps(policy()))
    out=tmp_path/'incumbent.kicad_pcb';out.write_text('incumbent')
    def emit(cand,cfg,path):
        Path(path).write_text('proposal')
        changed=policy();changed['net_settings']['classes'][1]['diff_pair_gap']=.12
        project.write_text(json.dumps(changed));return path
    monkeypatch.setattr(synth,'_materialize_rehydrated_board',emit)
    monkeypatch.setattr(synth,'_normalize_materialized_item_ids',lambda p:None)
    monkeypatch.setattr(synth,'_admit_materialized_power_prefix',lambda *a:None)
    candidate=SimpleNamespace(source_board=str(source),protected_power_prefix={'items':1})
    with pytest.raises(ValueError,match='rule authority changed'):
        synth.materialize(candidate,SimpleNamespace(),str(out))
    assert out.read_text()=='incumbent'


def test_fresh_native_default_shell_resolves_only_explicit_config_policy(tmp_path):
    import cec_project_policy_seal as seal
    source=tmp_path/'fresh.kicad_pcb';source.write_text('fresh unbound geometry')
    source.with_suffix('.kicad_pro').write_text(json.dumps(
        {'net_settings':{'classes':[{'name':'Default'}]}}))
    configured=tmp_path/'configured.kicad_pcb'
    configured.with_suffix('.kicad_pro').write_text(json.dumps(policy()))
    configured.with_suffix('.kicad_dru').write_text('(version 1)\n')
    snapshot=seal.capture(source,fallback_board=configured)
    assert snapshot['source']==configured.resolve()
    # Without that explicit fresh-placement authorization, even the native
    # shell remains the captured policy: routed recovery cannot silently adopt
    # a different rule donor.
    assert seal.capture(source)['source']==source.resolve()


def test_named_bindings_and_existing_custom_rules_never_use_fresh_fallback(tmp_path):
    import cec_project_policy_seal as seal
    source=tmp_path/'source.kicad_pcb';source.write_text('source')
    configured=tmp_path/'configured.kicad_pcb'
    configured.with_suffix('.kicad_pro').write_text(json.dumps(policy()))
    source.with_suffix('.kicad_pro').write_text(json.dumps(policy()))
    assert seal.capture(source,fallback_board=configured)['source']==source.resolve()
    source.with_suffix('.kicad_pro').write_text(json.dumps(
        {'net_settings':{'classes':[{'name':'Default'}]}}))
    source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    assert seal.capture(source,fallback_board=configured)['source']==source.resolve()


def test_fresh_missing_custom_file_is_bound_to_explicit_config_bytes(tmp_path):
    import cec_project_policy_seal as seal
    source=tmp_path/'source.kicad_pcb';source.write_text('source')
    source.with_suffix('.kicad_pro').write_text(json.dumps(policy()))
    configured=tmp_path/'configured.kicad_pcb'
    configured.with_suffix('.kicad_dru').write_text('(version 1)\n')
    snapshot=seal.capture(source,fallback_board=configured)
    target=tmp_path/'target.kicad_pcb'
    target.with_suffix('.kicad_dru').write_text('unexpected donor')
    seal.restore(snapshot,target)
    assert target.with_suffix('.kicad_dru').read_bytes()==configured.with_suffix('.kicad_dru').read_bytes()
    assert target.with_suffix('.kicad_pro').read_bytes()==source.with_suffix('.kicad_pro').read_bytes()
    configured.with_suffix('.kicad_dru').write_text('changed mid-transaction')
    with pytest.raises(ValueError,match='rule authority changed'):
        seal.restore(snapshot,target)
