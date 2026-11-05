"""Typed column scopes compose with print, not receipt-based admission."""
import copy
import pytest
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import root_receive_local_transaction_20261022 as transaction
from test_ordinary_power_columns import fixture


def row(net='arbitrary_supply', **extra):
    return dict(kind='ordinary_columns', net=net, candidate='/actual/child', candidate_sha256='a'*64, **extra)


def test_column_phase_and_print_keep_existing_finite_transaction_bound():
    phases=[row(),dict(kind='print_context',candidate='/actual/print',candidate_sha256='b'*64,proposal='/actual/proposal')]
    assert transaction.validate_phases(phases)==['ordinary_columns','print_context']


@pytest.mark.parametrize('fault',['same_net','mixed_same_net','past_print','extra_proof','missing_net','too_many'])
def test_repeated_or_claimed_column_authority_is_not_a_transaction(fault):
    phases=[row()]
    if fault=='same_net':phases.append(row())
    elif fault=='mixed_same_net':phases.append(dict(row(),kind='ordinary_join'))
    elif fault=='past_print':phases.insert(0,dict(kind='print_context',candidate='/actual/print',candidate_sha256='b'*64,proposal='/actual/proposal'))
    elif fault=='extra_proof':phases[0]['capacity_qualified']=True
    elif fault=='missing_net':phases[0].pop('net')
    else:phases=[row('net'+str(i))for i in range(transaction.MAX_LOCAL_PHASES+1)]
    with pytest.raises(ValueError):transaction.validate_phases(phases)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_saved_column_cut_is_rederived_not_a_worker_pass(tmp_path,monkeypatch,quarter,back):
    parent,child,source,added,contract=fixture(tmp_path,monkeypatch,quarter,back)
    candidate=tmp_path/'child.kicad_pcb';field._save_field_snapshot(child,candidate)
    phase=dict(row(),candidate=str(candidate),candidate_sha256=force._hash(candidate))
    original=source.read_bytes()
    selected,proof=transaction.receive_phase(source,source,phase,'synthetic')
    assert selected==candidate and proof['ok'] and proof['complete']
    assert proof['source_policy_column_capacity_received']
    assert proof['every_single_credited_vertical_barrel_loss_preserves_whole_current_path']
    assert not proof['current_qualified'] and not proof['release_authority']
    assert source.read_bytes()==original
    forged=copy.deepcopy(phase);forged['net']='another_rail'
    with pytest.raises(AssertionError):transaction.receive_phase(source,source,forged,'synthetic')


def test_single_unrated_barrel_cannot_enter_through_transaction_schema(tmp_path,monkeypatch):
    parent,child,source,added,contract=fixture(tmp_path,monkeypatch)
    added[0].SetDrill(300000);added[0].SetWidth(600000)
    candidate=tmp_path/'child.kicad_pcb';field._save_field_snapshot(child,candidate)
    phase=dict(row(),candidate=str(candidate),candidate_sha256=force._hash(candidate))
    with pytest.raises(AssertionError):transaction.receive_phase(source,source,phase,'synthetic')
