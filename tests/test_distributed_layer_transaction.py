"""Exact pair-only layer-join dispatch; no new role/current permissions."""
from unittest import mock
import pytest
import cec_force_current as force
from test_detached_passive_transaction import wrapper


def row():
    return dict(kind='distributed_supply_layer_join',candidate='child.kicad_pcb',
        candidate_sha256='a'*64,net='/arbitrary/rail',pad_uuids=['first','second'])


@pytest.mark.parametrize('extra',[{'amps':1},{'timeout_s':30},{'width':.1},{'via_ampacity':True},
    {'allow_unknown':True},{'role':'ordinary'},{'layers':['B.Cu']},{'retired_track_uuids':[]}])
def test_caller_cannot_supply_electrical_geometry_or_retirement_permissions(extra):
    with pytest.raises(ValueError):wrapper().validate_phases([dict(row(),**extra)])


def test_distinct_pairs_may_share_one_rail_but_cannot_repeat_the_same_work():
    op=wrapper();one=row();two=dict(row(),pad_uuids=['third','second'])
    assert op.validate_phases([one,two])==['distributed_supply_layer_join']*2
    for repeat in (one,dict(one,pad_uuids=list(reversed(one['pad_uuids'])))):
        with pytest.raises(ValueError):op.validate_phases([one,repeat])
    with pytest.raises(ValueError):op.validate_phases([row()]*5)


def test_dispatch_only_freshly_receives_actual_saved_pair_and_ten_second_lease(tmp_path):
    op=wrapper();parent=tmp_path/'source.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    parent.write_text('source');child.write_text('candidate')
    request=dict(row(),candidate=str(child),candidate_sha256=force._hash(child))
    with mock.patch.object(op.distributed_layer_join,'receive',return_value=dict(
            ok=True,complete=True,release_authority=False,plated_barrel_current_qualified=False))as call:
        target,proof=op.receive_phase(parent,parent,request,'renamed-source')
    call.assert_called_once_with(parent,child,board_hint='renamed-source',net='/arbitrary/rail',
                                 pad_uuids=['first','second'],timeout_s=10.)
    assert target==child and not proof['release_authority']and not proof['plated_barrel_current_qualified']
    with mock.patch.object(op.distributed_layer_join,'receive',return_value=dict(ok=False,complete=False)):
        with pytest.raises(AssertionError):op.receive_phase(parent,parent,request,'renamed-source')
