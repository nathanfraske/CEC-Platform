"""Private invocation reuse never becomes saved/caller stage authority."""
import copy
import json
from pathlib import Path

import pcbnew
import pytest
import cec_source_linear_power_stage as op
from test_source_linear_power_stage import fixture


def collect(board,poses,root,**kw):
    return op.collect(board,poses,board_hint=str(root),enabled=True,**kw)


def scope(board,poses,root,**kw):
    return op.observation_scope(board,poses,board_hint=str(root),**kw)


def test_one_full_derivation_deepcopy_and_fresh_next_receiver(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with scope(board,poses,root):
        first=collect(board,poses,root);expected=copy.deepcopy(first)
        first[owner.GetReference()]['source_power_nets'].clear()
        second=collect(board,poses,root)
        assert second==expected and len(calls)==3
        second.clear();assert collect(board,poses,root)==expected
        assert op.collect(board,poses,board_hint=str(root),enabled=False)=={}
    with scope(board,poses,root):
        assert collect(board,poses,root)==expected
    assert len(calls)==6
    assert collect(board,poses,root)==expected and len(calls)==9


def test_same_saved_source_other_native_board_is_fresh_miss(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    other=pcbnew.LoadBoard(board.GetFileName())
    with scope(board,poses,root):
        expected=collect(board,poses,root)
        assert collect(other,poses,root)==expected
        assert collect(board,poses,root)==expected
    assert len(calls)==6


def test_different_target_is_fresh_miss_not_alias(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    other=copy.deepcopy(poses);other[owner.GetReference()][0]+=.1
    with scope(board,poses,root):
        first=collect(board,poses,root)
        second=collect(board,other,root)
        assert second[owner.GetReference()]['target_pose']!=first[owner.GetReference()]['target_pose']
        assert collect(board,poses,root)==first
    assert len(calls)==6


def test_nested_scope_is_fresh_then_restores_parent(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with scope(board,poses,root):
        expected=collect(board,poses,root)
        with scope(board,poses,root):assert collect(board,poses,root)==expected
        assert collect(board,poses,root)==expected
    assert len(calls)==6


def test_exception_clears_private_scope(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(RuntimeError,match='caller_failure'):
        with scope(board,poses,root):
            collect(board,poses,root);raise RuntimeError('caller_failure')
    assert op._observations.get()is None
    collect(board,poses,root);assert len(calls)==6


@pytest.mark.parametrize('mutation',['native','source_bytes','project','schematic','exporter','code_epoch'])
def test_every_hit_and_exit_reject_stale_source(tmp_path,monkeypatch,mutation):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    # A synthetic exporter observation points at a real isolated file, never
    # modifies the interpreter or any repository/manufacturer evidence.
    exporter=tmp_path/'synthetic-exporter';exporter.write_bytes(b'fixture exporter identity')
    original=op.canonical._export
    def export(*a,**kw):
        result,metadata=original(*a,**kw);metadata=dict(metadata,exporter=str(exporter),
            exporter_sha256=op.force._hash(exporter))
        return result,metadata
    monkeypatch.setattr(op.canonical,'_export',export)
    with pytest.raises(ValueError,match='immutable_linear_stage'):
        with scope(board,poses,root):
            collect(board,poses,root)
            if mutation=='native':owner.SetValue('changed native value')
            elif mutation=='source_bytes':
                path=Path(board.GetFileName());path.write_bytes(path.read_bytes()+b'\n;changed source bytes\n')
            elif mutation=='project':
                path=Path(board.GetFileName()).with_suffix('.kicad_pro')
                data=json.loads(path.read_text());data['changed_authority']=True;path.write_text(json.dumps(data))
            elif mutation=='schematic':root.write_text(root.read_text()+'\n; changed hierarchy bytes\n')
            elif mutation=='exporter':exporter.write_bytes(b'changed exporter identity')
            else:
                epoch=copy.deepcopy(op.force._code_identity())
                monkeypatch.setattr(op.force,'_code_identity',lambda:dict(changed_synthetic_epoch=epoch))
            with pytest.raises(ValueError,match='immutable_linear_stage'):collect(board,poses,root)
    assert len(calls)==3 and op._observations.get()is None


def test_exit_alone_rejects_mutation_without_second_collect(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='immutable_linear_stage'):
        with scope(board,poses,root):
            collect(board,poses,root);root.write_text(root.read_text()+'\n; changed\n')
    assert op._observations.get()is None


def test_expired_scope_never_returns_cached_proof(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='observation_deadline'):
        with scope(board,poses,root):
            collect(board,poses,root)
            now=op.time.monotonic
            monkeypatch.setattr(op.time,'monotonic',lambda:now()+11)
            with pytest.raises(ValueError,match='observation_deadline'):collect(board,poses,root)
    assert len(calls)==3 and op._observations.get()is None


@pytest.mark.parametrize('seconds',[True,0,-1,10.1,float('nan'),float('inf')])
def test_strict_ten_second_scope_bound(tmp_path,monkeypatch,seconds):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='bounded_linear_stage_observation'):
        with scope(board,poses,root,timeout_s=seconds):pass
    assert not calls


def test_failed_derivation_is_never_cached(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    real=op.full._model
    def fail(*a,**kw):raise ValueError('synthetic_missing_complete_budget')
    monkeypatch.setattr(op.full,'_model',fail)
    with scope(board,poses,root):
        with pytest.raises(ValueError,match='missing_complete_budget'):collect(board,poses,root)
        assert op._observations.get()['result']is None
        monkeypatch.setattr(op.full,'_model',real)
        assert collect(board,poses,root)
    assert len(calls)==3


def test_nested_exception_restores_unmodified_parent_cache(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with scope(board,poses,root):
        expected=collect(board,poses,root)
        with pytest.raises(RuntimeError,match='nested_failure'):
            with scope(board,poses,root):
                collect(board,poses,root);raise RuntimeError('nested_failure')
        assert collect(board,poses,root)==expected
    assert len(calls)==6 and op._observations.get()is None


def test_enabled_scope_option_is_part_of_exact_key(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with scope(board,poses,root,enabled=False):
        collect(board,poses,root);collect(board,poses,root)
        assert op._observations.get()['result']is None
    assert len(calls)==6


def test_short_cached_call_still_has_own_deadline(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with scope(board,poses,root):
        collect(board,poses,root)
        with pytest.raises(ValueError,match='observation_deadline'):
            collect(board,poses,root,timeout_s=.000001)
    assert len(calls)==3


def test_cache_does_not_bypass_reference_scope_validation(tmp_path,monkeypatch):
    board,owner,root,tree,poses,calls=fixture(tmp_path,monkeypatch)
    with scope(board,poses,root):
        collect(board,poses,root)
        with pytest.raises(ValueError):
            collect(board,poses,root,reference_group_uuids=['not-an-authorized-uuid'])
    assert len(calls)==3
