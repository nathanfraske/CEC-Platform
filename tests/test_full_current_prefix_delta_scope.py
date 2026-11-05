"""An inherited pin lead is not part of a new cap-to-trunk proof."""
import pcbnew
import pytest

import cec_fr as fr
import cec_full_current_supply_prefix as receiver
import cec_local_copper_cell as copper
from test_full_current_supply_prefix import example


def legacy_lead(board,launch,prefix):
    old=pcbnew.PCB_TRACK(board);old.SetStart(launch.GetPosition())
    direction=prefix.GetEnd()-prefix.GetStart()
    dx,dy=int(direction.x),int(direction.y)
    old.SetEnd(pcbnew.VECTOR2I(launch.GetPosition().x-dx//2,
        launch.GetPosition().y-dy//2))
    old.SetLayer(prefix.GetLayer());old.SetWidth(prefix.GetWidth()-1)
    old.SetNet(prefix.GetNet());old.SetLocked(True);board.Add(old)
    prefix.GetParentGroup().AddItem(old)
    return old


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_actual_new_full_current_prefix_is_separate_from_uncredited_old_pin_lead(angle,back):
    board,launch,via,trunk,prefix,contracts=example(back=back,angle=angle,
        netname='/arbitrary/POWER_FEED',ref='UNRELATED_DEVICE')
    old=legacy_lead(board,launch,prefix);before=copper.copper_inventory(board)
    result=receiver.receive(board,contracts,track_uuid_scope=[prefix.m_Uuid.AsString()],
        retained_via_uuids=[via.m_Uuid.AsString()])
    assert result['complete'] and result['track_uuids']==[prefix.m_Uuid.AsString()]
    assert old.m_Uuid.AsString() not in result['proofs'][0]['track_uuids']
    assert result['unscoped_grouped_copper_current_credited'] is False
    assert result['current_budget_lowered'] is False
    assert result['proofs'][0]['current_authority']==next(iter(contracts.values()))['current_authority']
    assert before==copper.copper_inventory(board)
    # Requiring that old conductor to carry the same source is still a fail.
    result=receiver.receive(board,contracts,
        track_uuid_scope=[prefix.m_Uuid.AsString(),old.m_Uuid.AsString()],
        retained_via_uuids=[via.m_Uuid.AsString()])
    assert result['complete'] and not result['track_uuids']


@pytest.mark.parametrize('fault',['thin_requested','untyped','no_throat','thin_throat','no_group'])
def test_delta_is_not_a_current_role_or_throat_waiver(fault):
    board,launch,via,trunk,prefix,contracts=example();legacy_lead(board,launch,prefix)
    if fault=='thin_requested':prefix.SetWidth(prefix.GetWidth()-1)
    if fault=='untyped':launch.GetParentFootprint().SetValue('UNMODELED')
    if fault=='no_throat':board.Remove(trunk)
    if fault=='thin_throat':trunk.SetWidth(900000)
    if fault=='no_group':prefix.GetParentGroup().RemoveItem(prefix)
    result=receiver.receive(board,contracts,track_uuid_scope=[prefix.m_Uuid.AsString()],
        retained_via_uuids=[via.m_Uuid.AsString()])
    assert result['complete'] and not result['track_uuids']


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_omitted_thin_middle_cannot_become_a_full_class_throat(angle):
    board,launch,via,trunk,prefix,contracts=example(angle=angle)
    group=prefix.GetParentGroup();original_end=prefix.GetEnd()
    middle=pcbnew.VECTOR2I((prefix.GetStart().x+original_end.x)//2,
        (prefix.GetStart().y+original_end.y)//2)
    prefix.SetEnd(middle)
    hidden=pcbnew.PCB_TRACK(board);hidden.SetStart(middle);hidden.SetEnd(original_end)
    hidden.SetLayer(prefix.GetLayer());hidden.SetWidth(prefix.GetWidth()-1)
    hidden.SetNet(prefix.GetNet());board.Add(hidden);group.AddItem(hidden)
    result=receiver.receive(board,contracts,track_uuid_scope=[prefix.m_Uuid.AsString()],
        retained_via_uuids=[via.m_Uuid.AsString()])
    assert result['complete'] and not result['track_uuids']
