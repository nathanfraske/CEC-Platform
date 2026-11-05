import pytest
import cec_route_progress as progress


CONTROL = dict(source_counts=dict(opens=100,drc=0),refilled_counts=dict(opens=80,drc=0))


def test_refill_cannot_claim_routing_progress_even_with_positive_raw_delta():
    row = progress.classify(CONTROL,dict(opens=80,drc=0),same_as_refill=True,
                            added_items=0,removed_items=0,admitted=False)
    assert row['classification']=='refill_only'
    assert row['raw_open_reduction']==20
    assert row['refill_adjusted_open_reduction']==0
    assert row['qualified_routing_open_reduction']==0


@pytest.mark.parametrize('admitted', [False,True])
def test_track_change_is_not_qualified_without_admission(admitted):
    row = progress.classify(CONTROL,dict(opens=75,drc=0),same_as_refill=False,
                            added_items=3,removed_items=0,admitted=admitted)
    assert row['refill_adjusted_open_reduction']==5
    assert row['qualified_routing_open_reduction']==(5 if admitted else 0)
    assert not row['release_accepted']


def test_changed_serialization_and_negative_progress_are_not_credit():
    row = progress.classify(CONTROL,dict(opens=81,drc=0),same_as_refill=False,
                            added_items=0,removed_items=0,admitted=True)
    assert row['classification']=='no_track_via_change'
    assert row['refill_adjusted_open_reduction']==-1
    assert row['qualified_routing_open_reduction']==0


def test_identical_already_filled_board_is_unchanged():
    row = progress.classify(dict(source_counts={'opens':80},refilled_counts={'opens':80}),
        dict(opens=80,drc=0),same_as_refill=True,added_items=0,removed_items=0,admitted=False)
    assert row['classification']=='unchanged' and row['qualified_routing_open_reduction']==0
