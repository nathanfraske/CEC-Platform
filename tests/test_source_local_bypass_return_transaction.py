"""Local Source return is one fixed typed phase, never a process/current waiver."""
import copy
import pytest
import cec_force_current as force
import root_receive_local_transaction_20261022 as transaction
from test_source_local_bypass_return_replacement import saved


def row(pad='literal-pad',track='literal-track',candidate='/actual/private'):
    return dict(kind='source_local_bypass_return',pad_uuid=pad,track_uuid=track,
        candidate=candidate,candidate_sha256='a'*64)


@pytest.mark.parametrize('fault',['width','drill','current','point','rule','timeout','role',
    'flags','missing','empty','bool','same','repeat'])
def test_schema_never_supplies_geometry_roles_or_repeated_work(fault):
    phase=row();phases=[phase]
    extras=dict(width=1,drill=1,current=True,point=[0,0],rule='new',timeout=100,role='power',flags={})
    if fault in extras:phase[fault]=extras[fault]
    elif fault=='missing':phase.pop('track_uuid')
    elif fault=='empty':phase['track_uuid']=''
    elif fault=='bool':phase['track_uuid']=True
    elif fault=='same':phase['track_uuid']=phase['pad_uuid']
    else:phases.append(row(candidate='/another/private'))
    with pytest.raises(ValueError):transaction.validate_phases(phases)


@pytest.mark.parametrize('quarter',range(4))
def test_phase_recompiles_actual_source_bypass_factory_and_saved_native_return(tmp_path,quarter):
    source,child,pad,edge,q=saved(tmp_path,quarter=quarter)
    phase=row(pad,edge,str(child));phase['candidate_sha256']=force._hash(child)
    assert transaction.validate_phases([phase])==['source_local_bypass_return']
    actual,proof=transaction.receive_phase(source,source,phase,'synthetic')
    assert actual==child and proof['ok']and proof['complete'],proof
    assert proof['replacement_uses_only_exact_existing_source_pad_rule']
    assert not proof['new_barrel_ampacity_credited']and not proof['release_authority']
    forged=copy.deepcopy(phase);forged['track_uuid']='not-an-actual-source-track'
    with pytest.raises(AssertionError):transaction.receive_phase(source,source,forged,'synthetic')


def test_return_reconstruction_cannot_follow_a_received_measurement_as_a_shortcut(tmp_path):
    phases=[dict(kind='measurement_quiet_fanout',pad_uuid='p',peer_pad_uuid='q',candidate='/m',candidate_sha256='a'*64),
        row(candidate='/r'),dict(kind='print_context',candidate='/f',candidate_sha256='b'*64,proposal='/p')]
    with pytest.raises(ValueError):transaction.isolated_measurement_contact_transition(
        tmp_path/'source',tmp_path/'final',phases,[],board_hint='synthetic')
