import json
import os
import pytest
import cec_synth_pipeline as synth


def write_state(tmp_path,monkeypatch,*,complete=True):
    path=tmp_path/'power.json'
    value=dict(placement_scope='complete' if complete else 'anchors',
        frozen_nets=['RAIL'],pours=[dict(net='RAIL',layer='In3.Cu',
            polygon=[[1,1],[2,1],[2,2],[1,2]])],corridors=[])
    path.write_text(json.dumps(value));monkeypatch.setenv('CEC_POURFIRST_STATE',str(path))
    return str(path)


def test_route_time_complete_authority_survives_local_pi_context(tmp_path,monkeypatch):
    path=write_state(tmp_path,monkeypatch)
    with synth._future_power_authority_released(preserve_complete=True):
        assert os.environ['CEC_POURFIRST_STATE']==path
    assert os.environ['CEC_POURFIRST_STATE']==path


@pytest.mark.parametrize('preserve,complete',[(False,True),(False,False),(True,False)])
def test_only_prospective_or_explicit_replan_context_releases(tmp_path,monkeypatch,preserve,complete):
    path=write_state(tmp_path,monkeypatch,complete=complete)
    with synth._future_power_authority_released(preserve_complete=preserve):
        assert 'CEC_POURFIRST_STATE' not in os.environ
    assert os.environ['CEC_POURFIRST_STATE']==path


def test_context_restores_environment_even_on_refusal(tmp_path,monkeypatch):
    path=write_state(tmp_path,monkeypatch)
    with pytest.raises(RuntimeError):
        with synth._future_power_authority_released(preserve_complete=True):
            os.environ['CEC_POURFIRST_STATE']='wrong'
            raise RuntimeError('trial refused')
    assert os.environ['CEC_POURFIRST_STATE']==path
    monkeypatch.delenv('CEC_POURFIRST_STATE')
    with synth._future_power_authority_released():
        os.environ['CEC_POURFIRST_STATE']='temporary'
    assert 'CEC_POURFIRST_STATE' not in os.environ


def test_missing_declared_authority_does_not_turn_into_future_power(tmp_path,monkeypatch):
    monkeypatch.setenv('CEC_POURFIRST_STATE',str(tmp_path/'missing.json'))
    with pytest.raises(RuntimeError,match='cannot be read'):
        with synth._future_power_authority_released(preserve_complete=True):
            pytest.fail('must not generate copper without its declared authority')


def test_production_local_pi_explicitly_preserves_complete_authority():
    import inspect
    source=inspect.getsource(synth)
    at=source.index('def _reserve_decoupler_priority(')
    block=source[at:source.index('else:',source.index('with _future_power_authority_released(',at))]
    assert 'preserve_complete=bool(_pre_power_compile_enabled)' in block


def test_placement_qualification_keeps_the_same_committed_authority(tmp_path,monkeypatch):
    from types import SimpleNamespace
    path=write_state(tmp_path,monkeypatch)
    cfg=SimpleNamespace(params={'pourfirst_state':path})
    seen=[]
    monkeypatch.setattr(synth,'_oracle_decoupler_adjacency',
        lambda *a,**kw:seen.append(os.environ.get('CEC_POURFIRST_STATE')) or {'ok':False})
    assert not synth._decoupler_craft_evidence('candidate.kicad_pcb',cfg)['ok']
    assert seen==[path] and os.environ['CEC_POURFIRST_STATE']==path
