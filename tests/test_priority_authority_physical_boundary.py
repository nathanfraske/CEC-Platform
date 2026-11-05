"""New power authority must requalify every physical gate before selection."""
from unittest.mock import Mock

import pytest

import cec_full_pipeline as pipeline


def physical(*, pads=True, courtyards=True, craft=True, constraints=True):
    return ({'ok':pads}, {'ok':courtyards}, {'ok':craft}, False,
            {'ok':craft,'blockers':[] if craft else ['local return unavailable']},
            {'ok':constraints}, pads and courtyards and craft and constraints)


@pytest.mark.parametrize('failed', ['pads','courtyards','craft','constraints'])
def test_successful_power_solve_cannot_reuse_pre_rebuild_physical_gate(failed):
    before=physical()
    after=physical(**{failed:False})
    calls=[]
    def ensure():
        calls.append('freeze')
        return {'ok':True,'changed':False,'same_board_hash':True}
    def measure():
        assert calls==['freeze']
        calls.append('measure')
        return after
    authority,result,proof=pipeline._placement_authority_physical_boundary(before,ensure,measure)
    assert calls==['freeze','measure'] and authority['ok']
    assert not result[-1] and not proof['physical_after_ok']
    assert proof['measured_after_authority'] and not proof['release_authority']
    assert before[-1]  # no mutation or waiver of original evidence


def test_complete_composition_can_proceed_to_existing_exact_priority_selection():
    after=physical()
    authority,result,proof=pipeline._placement_authority_physical_boundary(
        physical(),lambda:{'ok':True},lambda:after)
    assert authority['ok'] and result is after and proof['physical_after_ok']


def test_failed_physical_precondition_does_not_run_power_or_followup_measurement():
    ensure,measure=Mock(),Mock()
    before=physical(craft=False)
    authority,result,proof=pipeline._placement_authority_physical_boundary(before,ensure,measure)
    assert not authority['ok'] and result is before
    ensure.assert_not_called();measure.assert_not_called()
    assert not proof['measured_after_authority']


def test_failed_power_does_not_claim_any_post_authority_physical_proof():
    measure=Mock()
    authority,result,proof=pipeline._placement_authority_physical_boundary(
        physical(),lambda:{'ok':False},measure)
    assert not authority['ok'] and proof['physical_after_ok'] is None
    assert not proof['measured_after_authority']
    measure.assert_not_called()


def test_measurement_exception_cannot_return_successful_admission():
    def fail():
        raise RuntimeError('native checker failed')
    with pytest.raises(RuntimeError,match='native checker failed'):
        pipeline._placement_authority_physical_boundary(physical(),lambda:{'ok':True},fail)
