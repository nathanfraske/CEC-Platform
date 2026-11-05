"""Three read-only proof steps never extend a constituent or admit a prefix."""
from unittest import mock
import pytest
import cec_rated_branch_repair as rated


def run(rows,ticks):
    state=dict(closed=False)
    def steps(**kwargs):
        try:yield from rows
        finally:state['closed']=True
    with mock.patch.object(rated,'_receive_steps',side_effect=steps), \
         mock.patch.object(rated.time,'monotonic',side_effect=ticks):
        result=rated.receive('unused-source','unused-child',board_hint='synthetic',retired_track_uuids=['x'],
            retire_obsolete_terminal_vias=True)
    assert state['closed']
    return result


STAGES=['source_inventory','saved_native_material','final_current_and_identity']


def test_three_distinct_bounded_steps_may_total_more_than_one_native_lease():
    result=run([(STAGES[0],None),(STAGES[1],None),(STAGES[2],dict(ok=True,complete=True,release_authority=False))],
        [0,9,9,18,18,27])
    assert result['ok']and result['complete']and result['maximum_verification_leases']==3
    assert [r['stage']for r in result['explicit_independent_verification_leases']]==STAGES
    assert all(r['elapsed_s']==9 and r['maximum_s']==10 for r in result['explicit_independent_verification_leases'])
    assert result['no_intermediate_receiving_authority']and not result['release_authority']


@pytest.mark.parametrize('failed',[0,1,2])
def test_an_exhausted_constituent_cannot_borrow_time_from_other_steps(failed):
    rows=[(name,None if i<2 else dict(ok=True,complete=True))for i,name in enumerate(STAGES)]
    ticks=[];clock=0
    for i in range(3):ticks.extend([clock,clock+(10 if i==failed else 1)]);clock=ticks[-1]
    r=run(rows,ticks)
    assert not r['ok']and not r['complete']and any('constituent_deadline:'+STAGES[failed]in e for e in r['errors'])
    assert len(r['explicit_independent_verification_leases'])==failed+1


@pytest.mark.parametrize('prefix',[0,1])
def test_a_complete_looking_prefix_is_never_final_receiving(prefix):
    rows=[(STAGES[i],None)for i in range(prefix)]+[(STAGES[prefix],dict(ok=True,complete=True))]
    r=run(rows,list(range(2*(prefix+1))))
    assert not r['ok']and any('intermediate_cannot_be_complete'in e for e in r['errors'])


def test_missing_or_out_of_order_steps_never_complete():
    for rows in ([(STAGES[1],None)],[(STAGES[0],None)],[(STAGES[0],None),(STAGES[0],None)]):
        r=run(rows,list(range(8)))
        assert not r['ok']and r['errors']


@pytest.mark.parametrize('failed',[0,1,2])
def test_failed_step_keeps_exact_error_without_advancing(failed):
    rows=[(STAGES[i],None)for i in range(failed)]+[(STAGES[failed],dict(ok=False,complete=False,errors=['actual_failure']))]
    r=run(rows,list(range(2*(failed+1))))
    assert not r['ok']and not r['complete']and r['errors']==['actual_failure']
    assert len(r['explicit_independent_verification_leases'])==failed+1
