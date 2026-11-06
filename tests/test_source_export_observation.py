"""Actual KiCad CLI export observations; no acceptance predicate stubs."""
import copy
import time
import uuid
from pathlib import Path

import pcbnew
import pytest
import cec_source_ground_leaf as op
from test_programming_resistor_placement import fixture as source_fixture

REAL_EXPORT=op._export


def fixture(tmp_path,monkeypatch):
    board,owner,cap,root,tree,poses=source_fixture(tmp_path,monkeypatch)
    # A complete native empty schematic is enough for the export-only API;
    # it grants no role or native-board/source component acceptance.
    root.write_text('(kicad_sch (version 20250114) (generator "eeschema") '
        '(uuid "'+str(uuid.uuid4())+'") (paper "A4") (lib_symbols) (embedded_fonts no))')
    # Restore the production observer: these tests run actual KiCad export.
    monkeypatch.setattr(op,'_export',REAL_EXPORT)
    calls=[];run=op.subprocess.run
    def observe(*a,**kw):calls.append(a[0]);return run(*a,**kw)
    monkeypatch.setattr(op.subprocess,'run',observe)
    return board,owner,root,calls


def scope(board,root,**kw):return op.observation_scope(board,board_hint=str(root),**kw)
def export(root):return op._export(root,time.monotonic()+10.)


def test_actual_cli_once_defensive_copy_new_receiver_fresh(tmp_path,monkeypatch):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    with scope(board,root):
        first=export(root);expected=copy.deepcopy(first)
        first[0].append(['forged']);first[1]['exporter']='forged'
        assert export(root)==expected and len(calls)==1
    with scope(board,root):
        second=export(root)
        assert op._tables(second[0])==op._tables(expected[0])
    assert len(calls)==2
    export(root);assert len(calls)==3


def test_actual_nested_scope_fresh_then_parent_restored(tmp_path,monkeypatch):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    with scope(board,root):
        expected=export(root)
        with scope(board,root):export(root)
        assert export(root)==expected
    assert len(calls)==2


def test_exception_cleanup_and_nested_parent_restoration(tmp_path,monkeypatch):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    with scope(board,root):
        expected=export(root)
        with pytest.raises(RuntimeError,match='caller_failure'):
            with scope(board,root):
                export(root);raise RuntimeError('caller_failure')
        assert export(root)==expected
    assert len(calls)==2 and op._export_observations.get()is None


@pytest.mark.parametrize('mutation',['native','source_path','source_bytes','project','schematic',
    'root_project','library_table','environment','code_epoch','exporter'])
def test_stale_inputs_rejected_on_hit_and_exit(tmp_path,monkeypatch,mutation):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='immutable_canonical_export'):
        with scope(board,root):
            export(root)
            if mutation=='native':owner.SetValue('changed native identity')
            elif mutation=='source_path':board.SetFileName(str(tmp_path/'different.kicad_pcb'))
            elif mutation=='source_bytes':
                p=Path(board.GetFileName());p.write_bytes(p.read_bytes()+b'\n; changed Source bytes\n')
            elif mutation=='project':Path(board.GetFileName()).with_suffix('.kicad_pro').write_text('{"changed":true}')
            elif mutation=='schematic':root.write_text(root.read_text()+'\n; hierarchy mutation\n')
            elif mutation=='root_project':root.with_suffix('.kicad_pro').write_text('{"text_variables":{"NEW":"changed"}}')
            elif mutation=='library_table':(root.parent/'sym-lib-table').write_text('(sym_lib_table)')
            elif mutation=='environment':monkeypatch.setenv('CEC_TEST_SOURCE_EXPORT_EPOCH','changed')
            elif mutation=='code_epoch':
                epoch=copy.deepcopy(op.force._code_identity())
                monkeypatch.setattr(op.force,'_code_identity',lambda:dict(synthetic_epoch_change=epoch))
            else:
                # Change only the observed exporter resolver, never a binary.
                import cec_toolchain as tc
                changed=tmp_path/'other-cli';changed.write_text('not the observed exporter')
                monkeypatch.setattr(tc,'require_kicad_cli',lambda *a:str(changed))
            with pytest.raises(ValueError,match='immutable_canonical_export'):export(root)
    assert len(calls)==1 and op._export_observations.get()is None


def test_exit_checks_even_without_second_export(tmp_path,monkeypatch):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='immutable_canonical_export'):
        with scope(board,root):
            export(root);root.write_text(root.read_text()+'\n; changed on exit\n')
    assert len(calls)==1 and op._export_observations.get()is None


def test_requested_other_root_is_never_aliased(tmp_path,monkeypatch):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    other=tmp_path/'other.kicad_sch';other.write_text(root.read_text())
    with scope(board,root):
        export(root)
        with pytest.raises(ValueError,match='requested_root_mismatch'):export(other)
    assert len(calls)==1


def test_failed_actual_export_is_not_cached(tmp_path,monkeypatch):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    # Structurally readable hierarchy, but not a valid KiCad source grammar.
    root.write_text(root.read_text()[:-1]+' (invalid_export_fixture no))')
    with scope(board,root):
        for _ in range(2):
            with pytest.raises(ValueError,match='fresh_export_refused'):export(root)
            assert op._export_observations.get()['result']is None
    assert len(calls)==2


def test_deadline_fails_on_hit_and_exit(tmp_path,monkeypatch):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='source_ground_leaf_deadline'):
        with scope(board,root):
            export(root);now=time.monotonic
            monkeypatch.setattr(op.time,'monotonic',lambda:now()+11)
            with pytest.raises(ValueError,match='source_ground_leaf_deadline'):export(root)
    assert len(calls)==1 and op._export_observations.get()is None


def test_actual_child_hierarchy_bytes_rechecked(tmp_path,monkeypatch):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    child=tmp_path/'child.kicad_sch';child.write_text(root.read_text().replace(
        op.sch.find_uuid(root.read_text()),str(uuid.uuid4()),1))
    sheet='(sheet (at 0 0) (size 10 10) (uuid "'+str(uuid.uuid4())+'") '
    for key,value in(('Sheetname','Child'),('Sheetfile',child.name)):
        sheet+='(property "'+key+'" "'+value+'" (at 0 0 0) (effects (font (size 1 1)))) '
    root.write_text(root.read_text()[:-1]+' '+sheet+'))')
    with pytest.raises(ValueError,match='immutable_canonical_export_hierarchy'):
        with scope(board,root):
            export(root)
            child.write_text(child.read_text()+'\n; child alone changed\n')
            with pytest.raises(ValueError,match='immutable_canonical_export_hierarchy'):export(root)
    assert len(calls)==1


def test_per_call_deadline_still_applies_to_cache_hit(tmp_path,monkeypatch):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    with scope(board,root):
        export(root)
        with pytest.raises(ValueError,match='source_ground_leaf_deadline'):
            op._export(root,time.monotonic()+.000001)
    assert len(calls)==1


@pytest.mark.parametrize('seconds',[True,0,-1,10.1,float('nan'),float('inf')])
def test_strict_ten_second_scope_bound(tmp_path,monkeypatch,seconds):
    board,owner,root,calls=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='bounded_canonical_export'):
        with scope(board,root,timeout_s=seconds):pass
    assert not calls
