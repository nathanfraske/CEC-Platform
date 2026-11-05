"""Typed dispatch boundaries only; no mocked board/model admission claim."""
import copy
import json
from pathlib import Path
import math

import pytest
import cec_component_metadata_transition as op
import cec_suite_annotation_transition as annotations
import cec_force_current as force


def declaration(tmp_path):
    paths = [tmp_path / name for name in ('source.kicad_pcb', 'child.kicad_pcb', 'proposal.json')]
    for path in paths: path.write_text('untrusted fixture; not a board/model proof')
    source, child, proposal = paths
    bound = lambda p: dict(path=str(p), sha256=force._hash(p))
    row = dict(board='arbitrary-board', path=str(source), sha256=force._hash(source),
               print_context_transition={})
    return child, dict(source=bound(source), proposal=bound(proposal), source_row=row)


@pytest.mark.parametrize('old_kind', annotations.KINDS[:-1])
def test_exact_one_level_recipe_schema_accepts_only_a_bound_source_row(tmp_path, old_kind):
    child, d = declaration(tmp_path)
    d['source_row'].pop('print_context_transition')
    d['source_row'][old_kind] = {}
    source, proposal, candidate = op.validate(child, d, 'arbitrary-board')
    assert source != candidate and proposal != candidate
    # Schema validation is deliberately not receiving or model authority.
    with pytest.raises((ValueError, KeyError, RuntimeError, OSError)):
        op.receive(child, d, board_hint='arbitrary-board')


@pytest.mark.parametrize('fault', [
    'extra', 'missing', 'source_hash', 'proposal_hash', 'row_hash', 'row_path',
    'board', 'recursive', 'ambiguous', 'no_recipe', 'same_boundary', 'symlink',
])
def test_no_context_verdict_callback_or_recursive_authority(tmp_path, fault):
    child, d = declaration(tmp_path)
    if fault == 'extra': d['trusted_context'] = {'ok': True}
    elif fault == 'missing': d.pop('proposal')
    elif fault == 'source_hash': d['source']['sha256'] = '0' * 64
    elif fault == 'proposal_hash': d['proposal']['sha256'] = '0' * 64
    elif fault == 'row_hash': d['source_row']['sha256'] = '0' * 64
    elif fault == 'row_path': d['source_row']['path'] = str(child)
    elif fault == 'board': d['source_row']['board'] = 'another-board'
    elif fault == 'recursive':
        d['source_row'].pop('print_context_transition')
        d['source_row'][op.KIND] = copy.deepcopy(d)
    elif fault == 'ambiguous': d['source_row']['annotation_transition'] = {}
    elif fault == 'no_recipe': d['source_row'].pop('print_context_transition')
    elif fault == 'same_boundary': child = Path(d['source']['path'])
    elif fault == 'symlink':
        link = tmp_path / 'alias'; link.symlink_to(d['source']['path']); d['source']['path'] = str(link)
    with pytest.raises(ValueError): op.validate(child, d, 'arbitrary-board')


@pytest.mark.parametrize('seconds', [True, 0, -1, 10.01, float('nan'), float('inf')])
def test_dispatch_keeps_original_constituent_limit(seconds):
    with pytest.raises(ValueError, match='bounded_internal_connection_constituent_required'):
        op.receive('/unavailable', {}, board_hint='arbitrary-board', timeout_s=seconds)


def test_dispatch_executes_fresh_original_recipe_before_model_receiving(tmp_path, monkeypatch):
    child, d = declaration(tmp_path)
    calls = []
    def refuse(*args, **kwargs): calls.append('original_recipe'); return dict(ok=False, complete=False)
    def forbidden(*args, **kwargs): raise AssertionError('model cannot bypass refused source recipe')
    monkeypatch.setattr(annotations, 'receive_row', refuse)
    monkeypatch.setattr(op.component, 'receive', forbidden)
    with pytest.raises(ValueError, match='fresh_original_annotation_scope_required'):
        op.receive(child, d, board_hint='arbitrary-board')
    assert calls == ['original_recipe']


def test_new_kind_is_exclusive_and_unknown_old_flag_is_not_authority():
    row = {op.KIND: {}, 'arbitrary_ok': True}
    assert annotations.kind(row) == op.KIND
    with pytest.raises(ValueError, match='ambiguous'):
        annotations.kind(dict(row, print_context_transition={}))
    assert annotations.kind({'arbitrary_ok': True}) is None


@pytest.mark.parametrize('damage', ['missing', 'false', 'extended', 'nan', 'infinite', 'boolean'])
def test_repeat_comparison_cannot_accept_unbounded_or_failed_evidence(damage):
    q = dict(ok=True, complete=True, bounded_composition=dict(
        kind='fresh_original_recipe_then_component_scope_then_identity', per_constituent_limit_s=10.),
        timings_s=dict(source_recipe=1., component_scope=1., identity_live=1.))
    if damage == 'missing': q.pop('bounded_composition')
    elif damage == 'false': q['ok'] = False
    elif damage == 'extended': q['bounded_composition']['per_constituent_limit_s'] = 10.1
    elif damage == 'nan': q['timings_s']['component_scope'] = float('nan')
    elif damage == 'infinite': q['timings_s']['identity_live'] = float('inf')
    elif damage == 'boolean': q['timings_s']['component_scope'] = True
    assert not op.same_replay(q, q)
