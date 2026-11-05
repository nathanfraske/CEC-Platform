"""A failing label/count cannot hide a new current-model fault."""
from copy import deepcopy
from unittest import mock

import pcbnew
import pytest

import cec_constraints as constraints
import cec_current_debt as debt
import cec_current_topology as topology


def authority():
    return dict(amps=3.,margin_included=False,geometry_margin=1.25,source='ratified_fixture')


def trace(uid='existing',*,actual=.2,required=.477):
    return dict(type='keepout',reserve='pour_or_widen',net='/renamed/rail',uuid=uid,
        layer='F.Cu',actual_mm=actual,required_mm=required,current_authority=authority())


def domain(*ids):
    return dict(type='current_domain_path',net='/renamed/rail',current_authority=authority(),
        removed_undersized_segments=len(ids),undersized_segments=[dict(uuid=uid,layer='F.Cu',
            actual_mm=.2,required_mm=.477) for uid in ids],
        original_connectivity=dict(available=True,connected=True),
        rated_connectivity=dict(available=True,connected=False))


def result(*rows):
    nt=sum(row['type']=='keepout' for row in rows);nd=sum(row['type']=='current_domain_path' for row in rows)
    return (False,'Existing and new faults may share this FAIL label',[
        dict(type='current_debt_inventory',schema=1,complete=True,violation_count=nt+nd,
            trace_fault_count=nt,domain_fault_count=nd),*rows])


@pytest.mark.parametrize('before,after',[
    (result(trace()),result(trace(),trace('new'))),
    (result(trace()),result(trace('replacement'))),
    (result(domain('a')),result(domain('a','b'))),
    (result(domain('a')),result(domain('b')))])
def test_new_objects_are_refused_even_when_failure_count_or_check_label_is_unchanged(before,after):
    verdict=debt.evaluate(before,after)
    assert verdict['complete'] and not verdict['ok'] and verdict['new_faults']
    assert not verdict['current_qualified'] and not verdict['release_authority']


@pytest.mark.parametrize('change',['narrower','requirement','authority','disconnect'])
def test_persistent_faults_must_not_become_worse_or_change_their_current_basis(change):
    row=domain('a') if change=='disconnect' else trace()
    newer=deepcopy(row)
    if change=='narrower':newer['actual_mm']=.1
    if change=='requirement':newer['required_mm']=.3  # Lowering authority is not a repair either.
    if change=='authority':newer['current_authority']['amps']=.5
    if change=='disconnect':newer['original_connectivity']['connected']=False
    verdict=debt.evaluate(result(row),result(newer))
    assert verdict['complete'] and not verdict['ok'] and verdict['worsened_faults']


def test_unchanged_or_improved_known_debt_is_not_misrepresented_as_qualified():
    for after in (result(trace()),result(trace(actual=.3)),(True,'current width passed')):
        verdict=debt.evaluate(result(trace()),after)
        assert verdict['ok'] and verdict['complete'] and not verdict['release_authority']
        assert verdict['current_qualified']==(after[0] is True)
    assert debt.evaluate(result(domain('a','b')),result(domain('a')))['ok']


@pytest.mark.parametrize('fault',['legacy','summary','count','domain_count','missing_uuid','duplicate','unknown_type','unknown_current'])
def test_incomplete_or_ambiguous_inventory_fails_closed(fault):
    old=result(trace());new=deepcopy(old)
    if fault=='legacy':new[2].pop(0)
    if fault=='summary':new[2][0]['complete']=False
    if fault=='count':new[2][0]['violation_count']=2
    if fault=='domain_count':new=result(domain('a'));new[2][1]['removed_undersized_segments']=2
    if fault=='missing_uuid':new[2][1].pop('uuid')
    if fault=='duplicate':new=result(trace(),trace())
    if fault=='unknown_type':new[2][1]['type']='legacy_exception'
    if fault=='unknown_current':new[2][1]['required_mm']=None
    verdict=debt.evaluate(old,new)
    assert not verdict['ok'] and not verdict['complete'] and verdict['errors']


def test_current_analysis_cannot_go_missing_to_hide_failed_model():
    assert not debt.evaluate(result(trace()),(None,'no model'))['ok']
    assert not debt.evaluate((None,'no model'),(None,'different unknown'))['ok']
    verdict=debt.evaluate((None,'same non-applicable analysis'),(None,'same non-applicable analysis'))
    assert verdict['ok'] and verdict['complete'] and not verdict['current_qualified']


def test_native_checker_emits_all_25_track_identities_without_the_old_20_row_truncation(tmp_path):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    net=pcbnew.NETINFO_ITEM(board,'unfamiliar_power_name');board.Add(net)
    for index in range(25):
        track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(index*2,5));track.SetEnd(pcbnew.VECTOR2I_MM(index*2+1,5))
        track.SetWidth(pcbnew.FromMM(.1));board.Add(track)
    path=tmp_path/'arbitrary.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    with mock.patch.object(topology,'board_current_domains',return_value={}), \
         mock.patch.object(topology,'current_contract_for_net',return_value=authority()):
        packet=constraints.CHECKERS['trace-width-high-current'](board,str(path),{})
    rows=[row for row in packet[2] if row['type']=='keepout']
    assert len(rows)==25 and {row['uuid'] for row in rows}=={t.m_Uuid.AsString() for t in board.GetTracks()}
    verdict=debt.evaluate(packet,packet)
    assert verdict['ok'] and verdict['complete'] and verdict['after_fault_objects']==25
