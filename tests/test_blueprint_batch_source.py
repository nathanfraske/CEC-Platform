"""Share source only inside one blueprint batch; never retain stale netlists."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import cec_synth_pipeline as synth


@pytest.mark.parametrize('consumer', ['stamps','refs'])
def test_blueprint_batch_reads_source_once_and_reloads_on_next_call(monkeypatch, consumer):
    reads = []
    compiled = []
    def view(_cfg):
        value = object()
        reads.append(value)
        return SimpleNamespace(nl=value)
    monkeypatch.setattr(synth, 'View', view)
    def compile(cfg, cell, *, nl=None):
        if nl is None:
            nl = synth.View(cfg).nl
        compiled.append(nl)
        return {'parts':{}}
    monkeypatch.setattr(synth, '_compiled_blueprint_template', compile)
    cfg = SimpleNamespace(sch='current.sch', params={'blueprint_cells':[
        {'template':{}, 'anchor_at':(i,0)} for i in range(3)]})
    def run():
        return (synth._declared_blueprint_stamps(cfg,{}) if consumer == 'stamps'
                else synth._declared_blueprint_refs(cfg))
    run()
    assert len(reads) == 1 and all(value is reads[0] for value in compiled)
    run()
    assert len(reads) == 2 and all(value is reads[1] for value in compiled[3:])
    assert reads[0] is not reads[1]


@pytest.mark.parametrize('consumer', ['stamps','refs'])
def test_empty_blueprint_batch_does_not_export_any_source(monkeypatch, consumer):
    view = Mock(side_effect=AssertionError('empty batch exported source'))
    monkeypatch.setattr(synth, 'View', view)
    cfg = SimpleNamespace(sch='current.sch',params={})
    if consumer == 'stamps':
        assert synth._declared_blueprint_stamps(cfg,{}) == []
    else:
        assert synth._declared_blueprint_refs(cfg) == set()
    view.assert_not_called()
