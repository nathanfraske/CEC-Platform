"""Renamed native banks, both lineage kinds and four board orientations.

Fixture budgets below exercise the receiving contract only. They are not
substituted into any design's actual power or manufacturing authority.
"""
from unittest.mock import patch
import math

import pcbnew
import pytest
import cec_force_bank_repair as bank
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
from test_force_sense_evidence import fixture


def saved_bank(tmp_path,*,angle=0,filtered=True,fault=None):
    source=tmp_path/'source.kicad_pcb'
    domains=fixture(source,angle=angle,filtered=filtered)
    for domain in domains.values():domain['amps']=1.
    b=pcbnew.LoadBoard(str(source))
    outer=max((t for t in b.GetTracks() if str(t.GetNetname())=='RENAMED_FEED'),key=lambda t:t.GetLength())
    start,end=pcbnew.VECTOR2I(*tuple(outer.GetStart())),pcbnew.VECTOR2I(*tuple(outer.GetEnd()))
    vector=end-start;norm=math.hypot(vector.x,vector.y)
    at=pcbnew.VECTOR2I(round(end.x-vector.x/norm*1e6),round(end.y-vector.y/norm*1e6))
    outer.SetEnd(at)
    field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'child')
    b=pcbnew.LoadBoard(str(child))
    incoming=pcbnew.PCB_TRACK(b);incoming.SetNetCode(b.GetNetcodeFromNetname('RENAMED_FEED'))
    incoming.SetStart(at);incoming.SetEnd(end);incoming.SetWidth(600000)
    incoming.SetLayer(pcbnew.F_Cu);incoming.SetLocked(True);b.Add(incoming)
    if fault=='narrow':incoming.SetWidth(400000)
    if fault=='unlocked':incoming.SetLocked(False)
    if fault=='still_open':incoming.SetEnd(at+pcbnew.VECTOR2I(round(vector.x/norm*1e5),round(vector.y/norm*1e5)))
    if fault=='source_edit':b.FindFootprintByReference('POWER_IN').SetValue('unauthorized')
    if fault=='source_removed':
        from cec_native_items import discard_items
        discard_items(b,[next(t for t in b.GetTracks() if force._uid(t)==force._uid(outer))])
    if fault=='unrelated_net':
        incoming.SetNetCode(b.GetNetcodeFromNetname('FILTERED_POS'))
        incoming.SetStart(pcbnew.VECTOR2I_MM(5,5));incoming.SetEnd(pcbnew.VECTOR2I_MM(5,6))
    field._save_field_snapshot(b,child)
    raw={net:dict(net=net,amps=1.,profile='explicit-fixture',authority_refs=domain['authority_refs'],
        routing_layers=['F.Cu','B.Cu'],required_by_layer_mm={'F.Cu':.5,'B.Cu':.5},
        current_authority=dict(amps=1.,geometry_margin=1.,margin_included=False,source='bounded_fixture_only'))
        for net,domain in domains.items()}
    return source,child,domains,raw


def receive_fixture(source,child,domains,raw,*,debt=False):
    # Native additive, partitions, geometric cuts and typed demands are real.
    # Only fixture design-budget lookup is isolated from the production board.
    with patch('cec_current_topology.board_current_domains',return_value=domains), \
         patch('cec_current_topology.route_width_contracts',return_value=raw), \
         patch('cec_fr._project_netclass_resolver',return_value=lambda n:dict(track_width=.2,clearance=.2)), \
         patch('cec_current_debt.receive',return_value=dict(ok=not debt,complete=True,release_authority=False)):
        return bank.receive(source,child,board_hint='explicit-fixture',timeout_s=10.)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('filtered',[False,True])
def test_native_bank_repair_does_not_invent_monitor_input_failure(tmp_path,angle,filtered):
    source,child,domains,raw=saved_bank(tmp_path,angle=angle,filtered=filtered)
    original=(force._hash(source),force._hash(child))
    result=receive_fixture(source,child,domains,raw)
    assert result['ok'] and result['complete'],result['errors']
    before,after=result['source_sense'],result['candidate_sense']
    assert before['same_net_connectivity']['ok'] is True
    assert before['clipped_isolation']['unknown']==1
    assert after['clipped_isolation']['passed']==2
    proof=result['actual_bank_connectivity']['RENAMED_FEED']
    assert len(proof['newly_connected_pairs'])==1 and proof['all_after_pairs_connected']
    assert not result['full_kelvin_qualification'] and not result['release_authority']
    assert original==(force._hash(source),force._hash(child))
    # Original input-lead API must continue to reject this separate bank basis.
    old=sense.compare_repaired_preservation(before,after,repair_nets=['RENAMED_FEED'],
        modified_nets=['RENAMED_FEED'],native_copper_transforms=result['native_count_manifest'])
    assert not old['same_evidence'] and 'actual_newly_connected_input_demand_required:RENAMED_FEED' in old['errors']


@pytest.mark.parametrize('fault',['narrow','unlocked','still_open','source_edit','source_removed','unrelated_net'])
def test_exact_additive_authority_and_real_closure_required(tmp_path,fault):
    source,child,domains,raw=saved_bank(tmp_path,fault=fault)
    result=receive_fixture(source,child,domains,raw)
    assert not result['ok'] and result['errors'],result
    assert not result['release_authority']


def test_bank_repair_cannot_waive_current_debt(tmp_path):
    source,child,domains,raw=saved_bank(tmp_path)
    result=receive_fixture(source,child,domains,raw,debt=True)
    assert not result['ok'] and 'ValueError:source_bank_current_debt_changed_or_worsened' in result['errors']


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_common_pipeline_receiving_derives_real_bank_basis_without_worker_flag(tmp_path,angle):
    import cec_received_route_evidence as received
    source,child,domains,raw=saved_bank(tmp_path,angle=angle)
    with patch('cec_current_topology.board_current_domains',return_value=domains), \
         patch('cec_current_topology.route_width_contracts',return_value=raw), \
         patch('cec_fr._project_netclass_resolver',return_value=lambda n:dict(track_width=.2,clearance=.2)), \
         patch('cec_current_debt.receive',return_value=dict(ok=True,complete=True,release_authority=False)):
        before,after=[sense.replay(p,board_hint='explicit-fixture',timeout_s=10.) for p in (source,child)]
        result=received.compare(source,child,before,after,timeout_s=10.)
    assert result['ok'] and result['complete'],result['errors']
    assert result['derived_repaired_input_nets']==[]
    assert result['derived_force_bank_repair_nets']==['RENAMED_FEED']
    assert result['independent_native_force_bank_receiving']['actual_bank_connectivity']['RENAMED_FEED']['native_bank_closed']
    assert not result['release_authority'] and not result['full_kelvin_qualification']


@pytest.mark.parametrize('missing',['before','after'])
def test_actual_new_copper_still_requires_both_raw_cut_inventories(tmp_path,missing):
    import cec_received_route_evidence as received
    source,child,domains,raw=saved_bank(tmp_path)
    with patch('cec_current_topology.board_current_domains',return_value=domains), \
         patch('cec_current_topology.route_width_contracts',return_value=raw), \
         patch('cec_fr._project_netclass_resolver',return_value=lambda n:dict(track_width=.2,clearance=.2)), \
         patch('cec_current_debt.receive',return_value=dict(ok=True,complete=True,release_authority=False)):
        before,after=[sense.replay(p,board_hint='explicit-fixture',timeout_s=10.) for p in (source,child)]
        del (before if missing=='before' else after)['clipped_isolation']
        result=received.compare(source,child,before,after,timeout_s=10.)
    assert not result['ok'] and not result['complete'] and result['errors']
    assert not result['release_authority'] and not result['full_kelvin_qualification']


@pytest.mark.parametrize('fault',['unknown_reason','bypass','lost_authority','model_guard','count','unaffected'])
def test_raw_typed_cut_contract_is_not_a_normalization_allowlist(tmp_path,fault):
    source,child,domains,raw=saved_bank(tmp_path)
    real=bank.sense.replay
    def replay(path,**kw):
        report=real(path,**kw)
        selected='RENAMED_LOAD' if fault=='unaffected' else 'RENAMED_FEED'
        row=next(r for r in report['clipped_isolation']['details'] if r['net']==selected)
        before=path.resolve()==source.resolve()
        if fault=='unknown_reason' and before:row['native']['reason']='deadline_exhausted'
        elif fault=='bypass' and before:row['native']['physical_bypass_proved']=True
        elif fault=='lost_authority' and not before:row['native']['authority']=[]
        elif fault in ('model_guard','unaffected') and not before:row['native']['numerical_guard_nm']+=1
        elif fault=='count' and not before:report['clipped_isolation']['passed']-=1
        return report
    with patch('cec_force_sense_evidence.replay',side_effect=replay):
        result=receive_fixture(source,child,domains,raw)
    assert not result['ok'] and result['errors'],result
    assert not result['release_authority']
