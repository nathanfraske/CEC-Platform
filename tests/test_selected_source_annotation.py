"""Existing print authority is freshly received, never inferred or forwarded."""
import ast,importlib.util
from pathlib import Path
import pytest

P=Path(__file__).resolve().parents[1]/'build/root_receive_local_transaction_20261022.py'
spec=importlib.util.spec_from_file_location('tested_selected_source_annotation',P)
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)


def test_plain_selected_source_needs_no_private_authority(monkeypatch):
    monkeypatch.setattr(op.annotations,'receive_row',lambda *a,**k:pytest.fail('plain Source guessed private context'))
    assert op.selected_source_annotation(Path('/source'),{},board_hint='renamed',kinds=['complete_macro'])is None


@pytest.mark.parametrize('kind',op.annotations.KINDS)
def test_typed_selected_source_requires_own_explicit_candidate_print(monkeypatch,kind):
    row={kind:{'opaque':'source-owned declaration'}}
    monkeypatch.setattr(op.annotations,'receive_row',lambda *a,**k:pytest.fail('missing candidate phase reached source replayer'))
    with pytest.raises(ValueError,match='explicit_candidate_print_context'):
        op.selected_source_annotation(Path('/source'),row,board_hint='renamed',kinds=['complete_macro'])


@pytest.mark.parametrize('kind',op.annotations.KINDS)
def test_actual_saved_source_row_and_bounded_public_receiver_are_used(monkeypatch,kind):
    row={kind:{'opaque':'source-owned declaration'}};seen=[];expected=dict(ok=True,complete=True,candidate_identity={'actual':'private-context'})
    def receive(*args,**kwargs):seen.append((args,kwargs));return expected
    monkeypatch.setattr(op.annotations,'receive_row',receive)
    assert op.selected_source_annotation(Path('/literal/source'),row,board_hint='renamed',kinds=['complete_macro','print_context'])is expected
    assert seen==[((Path('/literal/source'),row),dict(board_hint='renamed',timeout_s=10.))]


@pytest.mark.parametrize('proof',[{},dict(ok=True),dict(ok=True,complete=False),dict(ok=1,complete=True)])
def test_stale_incomplete_or_truthy_source_authority_refuses(monkeypatch,proof):
    row={op.annotations.KINDS[0]:{}}
    monkeypatch.setattr(op.annotations,'receive_row',lambda *a,**k:proof)
    with pytest.raises(ValueError,match='not_independently_received'):
        op.selected_source_annotation(Path('/source'),row,board_hint='renamed',kinds=['print_context'])


def test_before_after_final_replay_and_bound_actual_native_args_are_mandatory():
    tree=ast.parse(P.read_text());calls=[n for n in ast.walk(tree)if isinstance(n,ast.Call)]
    assert len([n for n in calls if ast.unparse(n.func)=='selected_source_annotation'])==3
    text=P.read_text()
    assert "source_typed['candidate_native_arguments']"in text
    assert "print_runtime.observe(path,a.out/(label+'-runtime')"in text
    assert 'print_runtime.quarantine(baseline,a.out'not in text
    assert 'source_annotation_deps==annotations.dependencies()'in text
    assert "annotations.same_replay(final_source,source_typed)"in text
    assert "annotations.same_replay(live_source,source_typed)"in text
