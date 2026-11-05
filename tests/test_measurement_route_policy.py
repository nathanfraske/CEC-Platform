"""Placement escapes obey the same unconditional Kelvin ownership as DSN."""
import pcbnew
import pytest
import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_measurement_leaf_bridge as bridge
import cec_measurement_route_policy as policy
from cec_native_items import discard_items
from test_measurement_leaf import fixture


def shunt_fixture(quarter):
    board,pad,anchor,tracks,xy=fixture('/renamed/positive',quarter)
    negative=pcbnew.NETINFO_ITEM(board,'unrelated_negative_alias');board.Add(negative)
    owner=pad.GetParentFootprint()
    peer=pcbnew.PAD(owner);peer.SetNumber('4');peer.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    peer.SetShape(pcbnew.PAD_SHAPE_RECT);peer.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    peer.SetLayerSet(pcbnew.PAD.SMDMask());peer.SetNet(negative)
    peer.SetPosition(xy((10,12)));owner.Add(peer)
    for index,pin in enumerate(('1','2','5','6')):
        other=pcbnew.PAD(owner);other.SetNumber(pin)
        other.SetAttribute(pcbnew.PAD_ATTRIB_SMD);other.SetShape(pcbnew.PAD_SHAPE_RECT)
        other.SetSize(pcbnew.VECTOR2I_MM(.5,.5));other.SetLayerSet(pcbnew.PAD.SMDMask())
        other.SetPosition(xy((4+index,25)));owner.Add(other)
    shunt=anchor.GetParentFootprint();shunt.SetReference('UNRELATED_PICKUP')
    shunt.SetValue('0.001R')
    far=pcbnew.PAD(shunt);far.SetNumber('2');far.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    far.SetShape(pcbnew.PAD_SHAPE_RECT);far.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    far.SetLayerSet(pcbnew.PAD.SMDMask());far.SetNet(negative)
    far.SetPosition(xy((20,12)));shunt.Add(far)
    return board,pad,anchor,tracks,xy


@pytest.mark.parametrize('quarter',range(4))
def test_true_shunt_input_does_not_gain_layer_routing_after_motion_or_surface_failure(quarter):
    board,pad,anchor,tracks,xy=shunt_fixture(quarter)
    q=leaf.plan(board,force._uid(pad));discard_items(board,tracks)
    pad.SetPosition(xy((1,10)))  # Distance never removes Kelvin ownership.
    q=dict(q,points_nm=[list(pad.GetPosition()),*q['points_nm'][1:]])
    before=leaf._binding(board);contract=policy.input_contract(board,force._uid(pad))
    assert contract['kind']=='shunt_kelvin_front_no_via'
    assert contract['permitted_layers']==[int(pcbnew.F_Cu)]
    with pytest.raises(ValueError,match='front_copper_without_vias'):
        bridge.search(board,q,timeout_s=1.,include_power_layer=True)
    # Refusal precedes contact search, including an isolated-input proposal.
    with pytest.raises(ValueError,match='front_copper_without_vias'):
        bridge.search_isolated(board,{'pad_uuid':force._uid(pad)},width_nm=200000)
    assert before==leaf._binding(board) and not contract['release_authority']


@pytest.mark.parametrize('quarter',range(4))
def test_non_shunt_measurement_keeps_multilayer_search_without_qualification(quarter):
    board,pad,anchor,tracks,xy=fixture('/arbitrary/voltage_monitor',quarter)
    contract=policy.require_layer_bridge(board,force._uid(pad))
    assert contract['allow_layer_bridge'] and contract['permitted_layers'] is None
    assert not contract['current_authority'] and not contract['kelvin_qualified']
