"""Native child destruction must not hand borrowed proxies to Python."""
import gc
import pcbnew
import pytest
from cec_native_items import discard_footprint_children
from test_lastmile import _board


def test_repeated_private_pad_deletion_keeps_native_type_registry_usable():
    for index in range(128):
        b=_board([(5,5,'/N')],edge=(0,0,10,10));fp=next(iter(b.GetFootprints()));pad=next(iter(fp.Pads()))
        assert discard_footprint_children(b,fp,[pad,pad])==1
        assert not list(fp.Pads()) and list(b.GetFootprints())
        assert hasattr(b.GetNetInfo(),'NetsByNetcode')
        assert b.GetBoardEdgesBoundingBox().GetWidth()>0
        if index%16==0:gc.collect()
    assert hasattr(b.GetNetInfo(),'NetsByNetcode')


def test_child_parent_is_native_identity_not_a_reused_serialized_uuid():
    first=_board([(5,5,'/A')],edge=(0,0,10,10));second=_board([(5,5,'/B')],edge=(0,0,10,10))
    a=next(iter(first.GetFootprints()));b=next(iter(second.GetFootprints()));pad=next(iter(b.Pads()))
    b.m_Uuid.Clone(pcbnew.KIID(a.m_Uuid.AsString()))
    with pytest.raises(ValueError,match='literal_native_footprint_child_parent_required'):
        discard_footprint_children(first,a,[pad])
    assert len(list(a.Pads()))==len(list(b.Pads()))==1


def test_footprint_on_another_private_board_cannot_be_destroyed_by_uuid_alias():
    first=_board([(5,5,'/A')],edge=(0,0,10,10));second=_board([(5,5,'/B')],edge=(0,0,10,10))
    fp=next(iter(second.GetFootprints()));pad=next(iter(fp.Pads()))
    with pytest.raises(ValueError,match='literal_native_footprint_board_parent_required'):
        discard_footprint_children(first,fp,[pad])
    assert len(list(fp.Pads()))==1
