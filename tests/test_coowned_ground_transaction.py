"""Explicit cohort scope dispatch is exact and cannot import permissions."""
from unittest import mock
import pytest
import cec_force_current as force
from test_detached_passive_transaction import wrapper


def test_cohort_dispatch_rederives_saved_scope_and_original_ten_second_lease(tmp_path):
    op=wrapper();parent=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    parent.write_text('source');child.write_text('candidate')
    row=dict(kind='coowned_input_control_ground',candidate=str(child),candidate_sha256=force._hash(child),pad_uuid='actual-pad')
    assert op.validate_phases([row])==['coowned_input_control_ground']
    with mock.patch.object(op.coowned_ground,'receive',return_value=dict(ok=True,complete=True,release_authority=False))as call:
        target,proof=op.receive_phase(parent,parent,row,'renamed-board')
        call.assert_called_once_with(parent,child,board_hint='renamed-board',pad_uuid='actual-pad',timeout_s=10.)
        assert target==child and not proof['release_authority']


@pytest.mark.parametrize('extra',[{'amps':1},{'timeout_s':30},{'width':.1},{'low_power':True},{'allow_unknown':True}])
def test_no_caller_current_or_role_or_geometry_overrides(extra):
    op=wrapper();row=dict(kind='coowned_input_control_ground',candidate='child.kicad_pcb',
        candidate_sha256='a'*64,pad_uuid='actual-pad')
    with pytest.raises(ValueError):op.validate_phases([dict(row,**extra)])
    with pytest.raises(ValueError):op.validate_phases([row,row])
    with pytest.raises(ValueError):op.validate_phases([row]*5)


def test_scope_failure_is_not_promoted_by_dispatch(tmp_path):
    op=wrapper();parent=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    parent.write_text('source');child.write_text('candidate')
    row=dict(kind='coowned_input_control_ground',candidate=str(child),candidate_sha256=force._hash(child),pad_uuid='actual-pad')
    with mock.patch.object(op.coowned_ground,'receive',return_value=dict(ok=False,complete=False,errors=['actual refusal'])):
        with pytest.raises(AssertionError):op.receive_phase(parent,parent,row,'renamed-board')
