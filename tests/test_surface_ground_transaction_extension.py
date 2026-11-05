"""Exact phase schema plus actual native Ground joins, not mock hardware grades."""
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import root_receive_surface_ground_transaction_20261026 as extension
from test_ground_component_join import construct


def row(candidate='/explicit/board.kicad_pcb', digest='a'*64, uid='Source-pad'):
    return dict(kind=extension.KIND, candidate=str(candidate), candidate_sha256=digest, pad_uuid=uid)


def test_single_Source_identity_and_original_phase_cap_and_print_order():
    item = row()
    assert extension.validate_phases([item]) == [extension.KIND]
    printing = dict(kind='print_context', candidate='/explicit/print.kicad_pcb',
        candidate_sha256='b'*64, proposal='/explicit/print.json')
    assert extension.validate_phases([item,printing]) == [extension.KIND,'print_context']
    for phases in ([item,item], [item]*5, [printing,item], []):
        with pytest.raises(ValueError): extension.validate_phases(phases)


@pytest.mark.parametrize('key',['net','width','clearance','current','via','retired_track_uuids',
    'allow_locked','timeout_s','external_success','waive_native','proposal','callback'])
def test_no_geometric_or_role_or_external_verdict_authority(key):
    with pytest.raises(ValueError): extension.validate_phases([dict(row(), **{key:True})])


@pytest.mark.parametrize('value',[True,None,'',4,[],{}])
def test_literal_Source_land_identity_required(value):
    with pytest.raises(ValueError): extension.validate_phases([dict(row(),pad_uuid=value)])


def test_dispatcher_does_not_modify_frozen_receiver_or_leave_global_registration():
    before = extension.base.validate_phases,extension.base.receive_phase,extension.base.annotation_dependencies
    raw = Path(extension.base.__file__).read_bytes()
    with extension.installed():
        assert extension.base.receive_phase is extension.receive_phase
        assert extension.base.validate_phases([row()]) == [extension.KIND]
        assert extension.dependencies()[str(Path(extension.__file__).resolve())] == force._hash(Path(extension.__file__))
    assert before == (extension.base.validate_phases,extension.base.receive_phase,extension.base.annotation_dependencies)
    assert raw == Path(extension.base.__file__).read_bytes()


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_saved_native_join_receives_original_ground_target(tmp_path,quarter,layer):
    source,child,proposal,added = construct(tmp_path,quarter=quarter,layer=layer)
    board = pcbnew.LoadBoard(str(source))
    owner = next(fp for fp in board.GetFootprints() if fp.GetValue().upper().startswith('INA'))
    pad = next(p for p in owner.Pads() if p.GetNetname() == 'GND')
    before = source.read_bytes(),child.read_bytes()
    candidate,proof = extension.receive_phase(source,source,row(child,force._hash(child),force._uid(pad)),'synthetic')
    assert candidate == child and proof['ok'] is True and proof['complete'] is True
    assert proof['new_holes'] == 0 and proof['requested_Source_target_receiving']['ok'] is True
    assert proof['all_source_partitions_preserved'] and not proof['release_authority']
    assert before == (source.read_bytes(),child.read_bytes())
    bad = row(child,'0'*64,force._uid(pad))
    with pytest.raises(AssertionError): extension.receive_phase(source,source,bad,'synthetic')
    with pytest.raises(AssertionError): extension.receive_phase(source,source,row(child,force._hash(child),'not-a-native-land'),'synthetic')
