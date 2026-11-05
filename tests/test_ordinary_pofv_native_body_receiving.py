"""Ordinary receiving must agree with its existing additive/factory body proof."""
import time
from unittest.mock import patch
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from test_local_pofv_body_contact import body_fixture


def inspect(parent, child, via):
    parent.SetProperties(child.GetProperties())
    with patch.object(ordinary, 'eligible_nets', return_value={'/ARBITRARY'}):
        return ordinary._incoming_ordinary_pofv_contacts(parent, child, [force._uid(via)],
            source='synthetic', board_hint='synthetic', deadline=time.monotonic()+2.)


@pytest.mark.parametrize('angle', [0,90,180,270])
@pytest.mark.parametrize('mirror', [False,True])
@pytest.mark.parametrize('layer', [pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_native_body_contact_is_received_without_duplicate_stubs(angle,mirror,layer):
    child, via, track, pad = body_fixture(angle,mirror,layer)
    parent = pcbnew.CreateEmptyBoard()
    via.SetLocked(True)
    group = pcbnew.PCB_GROUP(child);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
    child.Add(group);group.AddItem(via)
    before = field._field_snapshot_inventory(child)
    assert inspect(parent,child,via) == {force._uid(via)}
    assert field._field_snapshot_inventory(child) == before


@pytest.mark.parametrize('fault', ['unlocked','ungrouped','profile','drill','gap','wrong_face',
    'wrong_net','no_smd_owner','unowned_endpoint','too_far','partial_pad','noncanonical'])
def test_group_name_or_nearness_cannot_authorize_a_barrel(fault):
    child, via, track, pad = body_fixture()
    parent = pcbnew.CreateEmptyBoard();via.SetLocked(True)
    group = pcbnew.PCB_GROUP(child);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
    child.Add(group);group.AddItem(via)
    if fault == 'unlocked':via.SetLocked(False)
    elif fault == 'ungrouped':group.RemoveItem(via)
    elif fault == 'profile':
        props=child.GetProperties();props['CEC_FAB_PROFILE']='';child.SetProperties(props)
    elif fault == 'drill':via.SetDrill(1000)
    elif fault == 'gap':via.Move(pcbnew.VECTOR2I_MM(0,.4))
    elif fault == 'wrong_face':track.SetLayer(pcbnew.B_Cu)
    elif fault == 'wrong_net':
        net=pcbnew.NETINFO_ITEM(child,'/OTHER');child.Add(net);track.SetNet(net)
    elif fault == 'no_smd_owner':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault == 'unowned_endpoint':track.SetStart(pad.GetPosition()+pcbnew.VECTOR2I_MM(-2,0))
    elif fault == 'too_far':via.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I_MM(2,0))
    elif fault == 'partial_pad':via.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I_MM(.4,0))
    else:track.SetEnd(track.GetStart()+pcbnew.VECTOR2I_MM(5,1))
    before=field._field_snapshot_inventory(child)
    assert inspect(parent,child,via) == set()
    assert field._field_snapshot_inventory(child) == before


def test_ordinary_eligibility_is_not_granted_by_body_process_geometry():
    child,via,track,pad=body_fixture();parent=pcbnew.CreateEmptyBoard();via.SetLocked(True)
    parent.SetProperties(child.GetProperties())
    group=pcbnew.PCB_GROUP(child);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
    child.Add(group);group.AddItem(via)
    with patch.object(ordinary,'eligible_nets',return_value=set()):
        assert not ordinary._incoming_ordinary_pofv_contacts(parent,child,[force._uid(via)],
            source='synthetic',board_hint='synthetic',deadline=time.monotonic()+2.)
