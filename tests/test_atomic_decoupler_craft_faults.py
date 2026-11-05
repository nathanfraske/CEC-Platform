"""Partial local-cell repairs must not rename surviving measured failures."""
from copy import deepcopy
import json

import pcbnew
import pytest
import cec_decoupler_cell as cells
import cec_support_craft_gate as craft
import test_decoupler_cell as fixtures


def row(*causes,owner='OWNER_RENAMED',cap='BYPASS_RENAMED'):
    details=[dict(code=code,message=message,severity=severity)
        for code,message,severity in causes]
    return dict(owner=owner,pin='supply',cap=cap,rail='renamed-rail',
        reason='; '.join(d['message']for d in details),reason_details=details)


SUPPLY=('local_supply_missing','no explicit local supply copper',1)
GROUND=('owner_ground_return_missing','owner GND pin has no connected via within 1.50mm',1)
CAP=('capacitor_ground_return_missing','capacitor GND has no connected via within 1.50mm',1)


def measured(rows):
    return dict(ok=True,gates=dict(decoupler_cell_ok=not rows),
        faults=dict(decoupler_cell_ok=craft._decoupler_cell_faults(rows)))


@pytest.mark.parametrize('kept',[(SUPPLY,),(GROUND,),(CAP,),(),(SUPPLY,CAP)])
def test_any_partial_repair_preserves_separate_surviving_fault_identities(kept):
    before=measured([row(SUPPLY,GROUND,CAP)])
    after=measured([row(*kept)]if kept else [])
    unchanged=deepcopy((before,after))
    assert craft.compare(before,after)['accepted']
    assert (before,after)==unchanged


@pytest.mark.parametrize('change',['new_cause','other_owner','other_cap','higher_severity'])
def test_improvement_on_one_cause_cannot_fund_a_different_or_worsened_fault(change):
    before=measured([row(SUPPLY,GROUND)])
    changed=row(SUPPLY)
    if change=='new_cause':changed=row(CAP)
    elif change=='other_owner':changed['owner']='DIFFERENT_OWNER'
    elif change=='other_cap':changed['cap']='DIFFERENT_BYPASS'
    else:changed['reason_details'][0]['severity']=2
    assert not craft.compare(before,measured([changed]))['accepted']


def test_actual_unrounded_excess_does_not_hide_behind_equal_display_text():
    first=('local_supply_length_excess','supply copper 2.000mm exceeds local limit 1.000mm',1.000001)
    worse=(*first[:2],1.000002)
    better=(*first[:2],1.0)
    before=measured([row(first)])
    assert not craft.compare(before,measured([row(worse)]))['accepted']
    assert craft.compare(before,measured([row(better)]))['accepted']


@pytest.mark.parametrize('fault',['empty','tuple','duplicate','partial_message','unknown_code',
    'extra_field','missing_field','boolean_severity','zero','negative','nan','inf'])
def test_partial_or_malformed_atomic_evidence_is_never_a_fault_waiver(fault):
    value=row(SUPPLY,GROUND)
    if fault=='empty':value['reason_details']=[]
    elif fault=='tuple':value['reason_details']=tuple(value['reason_details'])
    elif fault=='duplicate':value['reason_details'][1]['code']=SUPPLY[0]
    elif fault=='partial_message':value['reason_details'].pop()
    elif fault=='unknown_code':value['reason_details'][0]['code']='unrecognized'
    elif fault=='extra_field':value['reason_details'][0]['trust_me']=True
    elif fault=='missing_field':del value['reason_details'][0]['severity']
    else:
        value['reason_details'][0]['severity']={
            'boolean_severity':True,'zero':0,'negative':-1,'nan':float('nan'),'inf':float('inf')}[fault]
    with pytest.raises(ValueError,match='complete_unique_measured'):
        craft._decoupler_cell_faults([value])


def test_legacy_unstructured_failures_keep_the_exact_existing_conservative_identity():
    value=row(SUPPLY,GROUND);del value['reason_details']
    expected=json.dumps([value[k]for k in ('owner','pin','cap','rail','reason')],
        sort_keys=True,separators=(',',':'))
    assert craft._decoupler_cell_faults([value])=={expected:1}
    # An old combined report cannot prove a newly structured partial repair.
    assert not craft.compare(measured([value]),measured([row(SUPPLY)]))['accepted']


def test_native_audit_reports_each_physical_cause_and_partial_ground_repair(monkeypatch):
    board,assignment=fixtures.DecouplerCellTests()._board()
    monkeypatch.setattr(cells.cec_constraints,'_device_bypass_assignment',lambda *a,**k:assignment)
    before=cells.audit_board(board)
    source=before['refused'][0]
    assert {d['code']for d in source['reason_details']}=={
        'local_supply_missing','capacitor_ground_return_missing','owner_ground_return_missing'}
    assert source['reason']=='; '.join(d['message']for d in source['reason_details'])
    ground=board.FindFootprintByReference('U1').FindPadByNumber('1')
    via=pcbnew.PCB_VIA(board);via.SetNet(ground.GetNet());via.SetPosition(ground.GetPosition())
    via.SetWidth(300000);via.SetDrill(200000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    after=cells.audit_board(board)
    assert not after['ok']and after['refused'][0]['supply_path_mm']is None
    assert {d['code']for d in after['refused'][0]['reason_details']}=={
        'local_supply_missing','capacitor_ground_return_missing'}
    assert craft.compare(measured(before['refused']),measured(after['refused']))['accepted']


def test_routed_measure_consumes_native_atomic_rows_without_changing_final_gates(monkeypatch):
    import cec_synth_pipeline as synth
    monkeypatch.setattr(synth,'_oracle_decoupler_adjacency',lambda *a,**k:
        dict(ok=False,details=[],violations=[],all_violations=[]))
    monkeypatch.setattr(synth,'_oracle_netclass_geometry',lambda *a,**k:dict(ok=True,violations=[]))
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda *a:object())
    monkeypatch.setattr(cells,'audit_board',lambda *a,**k:dict(ok=False,refused=[row(SUPPLY,GROUND)]))
    before=craft.measure('synthetic.kicad_pcb')
    monkeypatch.setattr(cells,'audit_board',lambda *a,**k:dict(ok=False,refused=[row(SUPPLY)]))
    after=craft.measure('synthetic.kicad_pcb')
    assert before['gates']==after['gates']==dict(decouple_ok=False,
        decoupler_cell_ok=False,netclass_geometry_ok=True)
    assert len(before['faults']['decoupler_cell_ok'])==2
    assert len(after['faults']['decoupler_cell_ok'])==1
    assert craft.compare(before,after)['accepted']
