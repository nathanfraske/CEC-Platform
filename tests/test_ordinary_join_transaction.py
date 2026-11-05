"""Ordinary batches retain distinct saved scopes and all actual-parent gates."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_signal_completion as ordinary
import root_receive_local_transaction_20261022 as transaction
from test_ordinary_native_portals import fixture


def row(net='/arbitrary/CONTROL',candidate='/actual/child',**extra):
    return dict(kind='ordinary_join',net=net,candidate=candidate,candidate_sha256='a'*64,**extra)


def test_distinct_saved_ordinary_joins_fit_existing_four_phase_bound():
    phases=[row('/one'),row('/two',candidate='/actual/second'),
        dict(kind='print_context',candidate='/actual/print',candidate_sha256='b'*64,proposal='/actual/proposal')]
    assert transaction.validate_phases(phases)==['ordinary_join','ordinary_join','print_context']


@pytest.mark.parametrize('fault',['same_net','past_print','extra_role','missing_net','too_many','repeat_reference'])
def test_no_repeat_role_override_or_phase_bound_expansion(fault):
    phases=[row()]
    if fault=='same_net':phases.append(row(candidate='/actual/second'))
    elif fault=='past_print':phases=[dict(kind='print_context',candidate='/actual/print',candidate_sha256='b'*64,proposal='/actual/p'),row()]
    elif fault=='extra_role':phases[0]['ordinary_role_claim']=True
    elif fault=='missing_net':phases[0].pop('net')
    elif fault=='too_many':phases=[row('/net'+str(i),candidate='/actual/'+str(i))for i in range(transaction.MAX_LOCAL_PHASES+1)]
    else:phases=[dict(kind='reference_fields',candidate='/actual/a',candidate_sha256='a'*64,proposal='/actual/a.json')]*2
    with pytest.raises(ValueError):transaction.validate_phases(phases)


@pytest.mark.parametrize('net',[None,True,'','x'*257,'/control\nforged'])
def test_exact_literal_net_name_required(net):
    with pytest.raises(ValueError,match='explicit_literal_ordinary_join_net'):
        transaction.validate_phases([row(net)])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_saved_source_receiver_not_a_worker_success_claim(tmp_path,quarter,back):
    source,board,net=fixture(tmp_path,quarter=quarter,back=back)
    q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    child=force._copy_family(source,tmp_path/'child');saved=pcbnew.LoadBoard(str(child))
    ends=ordinary._pads(saved,q['request']);t=pcbnew.PCB_TRACK(saved)
    t.SetNet(ends[0].GetNet());t.SetLayer(next(iter(ends[0].GetLayerSet().CuStack())))
    t.SetStart(ends[0].GetPosition());t.SetEnd(ends[1].GetPosition());t.SetWidth(q['request']['width_nm']);saved.Add(t)
    field._save_field_snapshot(saved,child)
    phase=row(net,candidate=str(child));phase['candidate_sha256']=force._hash(child)
    before=source.read_bytes();parent,proof=transaction.receive_phase(source,source,phase,'synthetic')
    assert parent==child and proof['ok']and proof['complete']and proof['whole_shared_stage_still_required']
    assert proof['source_components']==2 and proof['candidate_components']==1
    assert source.read_bytes()==before
    forged=copy.deepcopy(phase);forged['net']='+3V3'
    with pytest.raises(AssertionError):transaction.receive_phase(source,source,forged,'synthetic')


@pytest.mark.parametrize('quarter',range(4))
def test_one_exact_ordinary_reflow_replays_real_source_cut_and_partitions(tmp_path,quarter):
    from test_ordinary_route_receiving import fixture as reflow_fixture
    source,child,uid,net=reflow_fixture(tmp_path,rotation=quarter*90,prefix='/renamed/')
    phase=dict(kind='ordinary_reflow',net=net,retired_track_uuids=[uid],
        candidate=str(child),candidate_sha256=force._hash(child))
    assert transaction.validate_phases([phase])==['ordinary_reflow']
    original=source.read_bytes();final,proof=transaction.receive_phase(source,source,phase,'synthetic')
    assert final==child and proof['ok']and proof['complete']
    assert proof['all_prior_native_terminal_partitions_preserved']and not proof['power_authority']
    assert source.read_bytes()==original
    forged=copy.deepcopy(phase);forged['net']='+3V3'
    with pytest.raises(ValueError,match='requested_source_net'):
        transaction.receive_phase(source,source,forged,'synthetic')


@pytest.mark.parametrize('fault',['empty','duplicate','oversized','unknown_field','role_claim','repeat_net'])
def test_ordinary_reflow_is_finite_and_not_a_repeated_or_untyped_cut(fault):
    phase=dict(kind='ordinary_reflow',net='/actual/control',retired_track_uuids=['actual-source-edge'],
        candidate='/private/reflow',candidate_sha256='a'*64)
    phases=[phase]
    if fault=='empty':phase['retired_track_uuids']=[]
    elif fault=='duplicate':phase['retired_track_uuids']*=2
    elif fault=='oversized':phase['retired_track_uuids']=[str(i)for i in range(9)]
    elif fault=='unknown_field':phase['timeout_s']=100
    elif fault=='role_claim':phase['ordinary_role']=True
    else:phases.append(row('/actual/control',candidate='/private/second'))
    with pytest.raises(ValueError):transaction.validate_phases(phases)


def test_rated_and_ordinary_preclear_then_measurement_and_print_keep_four_phase_cap():
    phases=[dict(kind='rated_branch',retired_track_uuids=['power-source-edge'],options={},
                 candidate='/private/rated',candidate_sha256='a'*64),
            dict(kind='ordinary_reflow',net='/actual/control',retired_track_uuids=['control-source-edge'],
                 candidate='/private/reflow',candidate_sha256='b'*64),
            dict(kind='isolated_measurement_join',pad_uuid='actual-source-input',
                 candidate='/private/measurement',candidate_sha256='c'*64),
            dict(kind='print_context',proposal='/private/print.json',
                 candidate='/private/print',candidate_sha256='d'*64)]
    assert transaction.validate_phases(phases)==[
        'rated_branch','ordinary_reflow','isolated_measurement_join','print_context']
