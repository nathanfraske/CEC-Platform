"""An identical saved family cannot acquire geometry debt from clock jitter."""
from copy import deepcopy
import pcbnew
import pytest
import cec_constraints as constraints
import cec_current_debt as debt
import cec_force_current as force
from test_current_debt import result,trace


BRANCHES=('typed_measurement_branch_receiving','typed_resistive_monitor_receiving',
    'typed_control_branch_receiving','typed_supply_consumer_receiving')


@pytest.mark.parametrize('kind',BRANCHES)
@pytest.mark.parametrize('side',['source','candidate'])
def test_partial_branch_fallback_is_unknown_not_new_or_repaired_copper(kind,side):
    before=result(trace());after=result(trace(),trace('apparent-new'))
    target=before if side=='source' else after
    target[2][0][kind]=dict(complete=False,uuids=[])
    verdict=debt.evaluate(before,after)
    assert not verdict['ok'] and not verdict['complete']
    assert verdict['new_faults']==verdict['worsened_faults']==[]
    assert verdict['errors']==['current_debt_branch_inventory_incomplete:'+kind]
    assert not verdict['current_qualified'] and not verdict['release_authority']


def source_file(tmp_path):
    path=tmp_path/'unfamiliar.kicad_pcb'
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);pcbnew.SaveBoard(str(path),b)
    return path


@pytest.mark.parametrize('qualified',[False,True])
def test_identical_path_uses_one_fresh_complete_snapshot_not_two_timed_models(tmp_path,monkeypatch,qualified):
    path=source_file(tmp_path);digest=force._hash(path);calls=[]
    packet=(True,'full aggregate current model passes') if qualified else result(trace())
    def checker(*args):
        calls.append(args[1]);assert len(calls)==1
        return deepcopy(packet)
    monkeypatch.setitem(constraints.CHECKERS,'trace-width-high-current',checker)
    report=debt.receive(path,path,board_hint='opaque')
    assert report['ok'] and report['complete'] and report['independent_native_evaluations']==1
    assert report['exact_identical_saved_path_snapshot_reused'] and calls==[str(path.resolve())]
    assert report['before_result']==report['after_result']
    # deepcopy may correctly reuse an immutable two-item PASS tuple. The
    # structured mutable failure payload must never be aliased, however.
    if not qualified:assert report['before_result'][2] is not report['after_result'][2]
    assert report['current_qualified']==qualified and not report['release_authority']
    assert force._hash(path)==digest


def test_distinct_identical_pcb_files_still_receive_both_native_models(tmp_path,monkeypatch):
    path=source_file(tmp_path);candidate=tmp_path/'separate.kicad_pcb'
    candidate.write_bytes(path.read_bytes());calls=[]
    def checker(*args):
        calls.append(args[1]);return result(trace()) if len(calls)==1 else result(trace(),trace('new'))
    monkeypatch.setitem(constraints.CHECKERS,'trace-width-high-current',checker)
    report=debt.receive(path,candidate,board_hint='opaque')
    assert report['complete'] and not report['ok'] and report['new_faults']
    assert report['independent_native_evaluations']==2 and not report['exact_identical_saved_path_snapshot_reused']
    assert calls==[str(path.resolve()),str(candidate.resolve())]


def test_identical_path_partial_snapshot_is_never_accepted(tmp_path,monkeypatch):
    path=source_file(tmp_path);packet=result(trace())
    packet[2][0][BRANCHES[0]]=dict(complete=False)
    monkeypatch.setitem(constraints.CHECKERS,'trace-width-high-current',lambda *a:deepcopy(packet))
    report=debt.receive(path,path,board_hint='opaque')
    assert not report['ok'] and not report['complete'] and report['errors']
    assert report['exact_identical_saved_path_snapshot_reused']


def test_fresh_family_mutation_is_not_hidden_by_identical_path_reuse(tmp_path,monkeypatch):
    path=source_file(tmp_path)
    def checker(*args):
        changed=pcbnew.LoadBoard(str(path));changed.SetCopperLayerCount(4)
        pcbnew.SaveBoard(str(path),changed)
        return result(trace())
    monkeypatch.setitem(constraints.CHECKERS,'trace-width-high-current',checker)
    report=debt.receive(path,path,board_hint='opaque')
    assert not report['ok'] and not report['source_candidate_and_code_unchanged']
    assert 'current_debt_source_candidate_or_code_changed' in report['errors']
