"""One fixed-port path engine, explicit independently proved owner strategy."""
import copy,runpy
from pathlib import Path
import pytest
import cec_force_current as force
from test_planar_consumer_reconstruction_tool import case as grouped_case,BUILD
from test_retained_consumer_planar_reflow_tool import case as retained_case
from test_consumer_path_reflow_tool import baseline

TOOL=Path(__file__).resolve().parents[1]/'ops/cec_consumer_path_reflow.py'


@pytest.mark.parametrize('ownership',['planar_nonplane','retained_planar_island'])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_face_owned_path_keeps_exact_allocation_budget_contacts_and_source(tmp_path,monkeypatch,ownership,quarter,mirror):
    fixture=retained_case if ownership=='retained_planar_island' else grouped_case
    source,b,ids,row,domain,downstream=fixture(tmp_path,monkeypatch,quarter,mirror)
    before=source.read_bytes();budget=copy.deepcopy((row,domain,downstream));api=runpy.run_path(str(TOOL))
    result=api['run'](source,tmp_path/'work',board_hint='synthetic',expected_source_sha256=force._hash(source),
        grade=baseline(tmp_path,source),reporting_build=BUILD,allow_locked_source=True,source_ownership=ownership)
    assert result['changed'] and result['ok'] and result['complete'],result
    proof=result['independent_source_consumer_receiving'];assert proof['ok'] and proof['complete'] and not proof['errors']
    assert proof['independently_rederived_native_contacts'] and proof['source_candidate_and_code_unchanged']
    owned=proof['source_consumer_receiving'];assert owned['actual_face_current_floor_rederived']
    assert owned['all_original_surviving_partitions_preserved'] and owned['exact_native_ground_refill_replayed']
    assert owned['source_scope']['source_budget']['current_authority']['amps']==.3004
    assert owned['source_scope']['source_budget']['aggregate_current_authority']['amps']==20.
    assert not owned['source_current_reduced'] and not owned['branch_sharing_assumed'] and not owned['incoming_via_uuids']
    if ownership=='retained_planar_island':assert owned['exact_allocation_group_preserved']
    assert result['actual_length_removed_mm']>0 and result['removed_source_strokes']>0 and result['removed_bend_flags']>0
    assert result['attempts'][-1]['opens']==0 and not result['attempts'][-1]['new_native_faults']
    assert result['records'][0]['plan']['source_ownership']==ownership and source.read_bytes()==before
    assert result['source_family_and_code_unchanged'] and budget==(row,domain,downstream)
    assert not result['fab_ready'] and not result['release_authority']


def test_path_baseline_cannot_silently_change_source_ownership_strategy(tmp_path):
    source=tmp_path/'source';source.write_text('only a synthetic identity')
    api=runpy.run_path(str(TOOL));epoch=force._code_identity()
    data=dict(tool_kind='source_consumer_path_reflow',source_ownership='strict_outer')
    with pytest.raises(ValueError,match='baseline_owner_changed'):
        api['baseline'](data,source,epoch,'retained_planar_island')


@pytest.mark.parametrize('ownership',['planar_nonplane','retained_planar_island'])
def test_path_does_not_borrow_the_other_ownership_domain(tmp_path,monkeypatch,ownership):
    fixture=grouped_case if ownership=='retained_planar_island' else retained_case
    source,b,*_=fixture(tmp_path,monkeypatch);api=runpy.run_path(str(TOOL))
    menu=api['inventory'](b,source,board_hint='synthetic',allow_locked_source=True,source_ownership=ownership)
    assert not menu['offers'] and not menu['source_mutated']
