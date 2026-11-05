"""An owned input strap is not an aperture over its complete copper island."""
import copy
import time

import pcbnew
import pytest
import cec_force_current as force
import cec_native_items as native
import cec_measurement_terminal_route as route
import cec_cell_row_rebuild as row
from test_measurement_auxiliary_cut import fixture as base
from test_field_proposals import track


def fixture(tmp_path,quarter=0,back=False):
    board,_,owner,strap,departure=base(tmp_path,quarter,back)
    native.discard_items(board,[departure])
    root=owner.FindPadByNumber('9')
    peer=owner.FindPadByNumber('8')
    target=board.FindFootprintByReference('unrelated_external_boundary').FindPadByNumber('1')
    demand=dict(pad_uuid=force._uid(root),target_uuid=force._uid(target),
        owner_uuid=force._uid(owner),input_pin='9',net=root.GetNetname(),
        b_nm=list(target.GetPosition()),source_input_island_uuids=sorted(map(force._uid,[root,peer,strap])),
        source_segment={'end':dict(ref=target.GetParentFootprint().GetReference(),pad='1')})
    return board,demand,root,peer,target,strap


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_source_input_strap_allows_only_a_root_departure(tmp_path,quarter,back):
    board,demand,root,peer,target,strap=fixture(tmp_path,quarter,back)
    before=row._source_binding(board)
    guard=route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+10.)
    assert guard['clear']([list(root.GetPosition()),list(target.GetPosition())])
    assert guard['source_input_component']['exact_literal_auxiliary_strap']
    assert guard['source_input_component']['aperture_only_at_original_root_land']
    assert not guard['clear']([list(root.GetPosition()),list(peer.GetPosition()),list(target.GetPosition())])
    assert guard['unchanged']() and row._source_binding(board)==before


@pytest.mark.parametrize('fault',['fake_singleton','unowned_uuid','omitted_peer','duplicate',
    'external_pickup','wide_strap','extra_stub','unfilled_zone','locked_owner','unknown_model'])
def test_incomplete_or_extended_source_island_is_never_ignored(tmp_path,fault):
    board,demand,root,peer,target,strap=fixture(tmp_path)
    if fault=='fake_singleton':demand['source_input_island_uuids']=[force._uid(root)]
    elif fault=='unowned_uuid':demand['source_input_island_uuids'].append('unowned')
    elif fault=='omitted_peer':demand['source_input_island_uuids'].remove(force._uid(peer))
    elif fault=='duplicate':demand['source_input_island_uuids'].append(force._uid(root))
    elif fault=='external_pickup':
        target.SetPosition(peer.GetPosition())
        demand['b_nm']=list(target.GetPosition())
    elif fault=='wide_strap':strap.SetWidth(400000)
    elif fault=='extra_stub':
        t=track(board,root.GetNetname(),(10.25,10),(10.25,12),width=.2)
        demand['source_input_island_uuids'].append(force._uid(t))
    elif fault=='unfilled_zone':
        zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.F_Cu);zone.SetNet(root.GetNet());zone.Outline().NewOutline()
        for xy in [(9,9),(12,9),(12,11),(9,11)]:zone.Outline().Append(*[round(v*1e6) for v in xy])
        board.Add(zone)
    elif fault=='locked_owner':root.GetParentFootprint().SetLocked(True)
    else:root.GetParentFootprint().SetValue('untyped')
    before=row._source_binding(board)
    with pytest.raises(ValueError):
        route.contact_guard(board,demand,width_nm=200000,deadline=time.monotonic()+10.)
    assert row._source_binding(board)==before
