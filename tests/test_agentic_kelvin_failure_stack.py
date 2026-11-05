"""A contour refusal retains the causal replay failure without changing gates."""
from copy import deepcopy

import pytest
import cec_force_sense_evidence as evidence
import test_force_sense_evidence as fixture


@pytest.mark.parametrize('side',['source','candidate'])
@pytest.mark.parametrize('fault',['incomplete','unbound'])
def test_contour_refusal_names_failed_input_and_keeps_self_validation_cause(side,fault):
    before=fixture.contact_comparison_fixture();after=deepcopy(before)
    damaged=before if side=='source' else after
    if fault=='incomplete':
        damaged['complete']=False
        damaged['stop']='native_work_deadline'
    else:
        damaged['identity_stable']=False
    original=deepcopy((before,after))
    proof=evidence.compare_contour_preservation(before,after,modified_nets=['RENAMED_FORCE'])
    assert not proof['comparison_complete'] and not proof['same_evidence']
    assert proof['reason']=='contour_evidence_rebinding_refused'
    failed=proof['input_validation'][-1]
    assert failed['side']==side and not failed['comparison_complete']
    assert failed['errors']==['incomplete_or_unbound_contact_replay']
    assert failed['replay_stop']==('native_work_deadline' if fault=='incomplete' else None)
    assert not proof['full_kelvin_qualification'] and not proof['release_authority']
    assert (before,after)==original
