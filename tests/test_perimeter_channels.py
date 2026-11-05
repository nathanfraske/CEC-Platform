"""Outside-spine breadth is a bounded proposal, never a native guard bypass."""
import time

import pcbnew
import pytest

import cec_fr as fr
import cec_maze_channels as channels
from test_lastmile import _board
from test_field_proposals import track


@pytest.mark.parametrize('swap,sign',[(False,1),(True,1),(False,-1),(True,-1)])
def test_perimeter_covers_extremes_without_board_or_axis_special_cases(swap,sign):
    def point(p):return tuple(sign*v for v in (p[::-1] if swap else p))
    source,end=point((4_000_000,6_000_000)),point((16_000_000,4_000_000))
    paths=channels.perimeter_channel_paths(source,end,[],(-20_000_000,)*2+(20_000_000,)*2,inflation=200000)
    assert paths and len(paths)<=256
    assert all(p[0]==source and p[-1]==end for p in paths)
    assert all(a[0]==b[0] or a[1]==b[1] for p in paths for a,b in zip(p,p[1:]))
    assert any(any(abs(v)==20_000_000 for v in q) for p in paths for q in p[1:-1])


def test_native_enclosure_can_be_escaped_without_rasterizing_the_whole_board():
    board=_board([(5,10,'/SCALAR'),(20,5,'/SCALAR')],edge=(0,0,30,30))
    board.Add(pcbnew.NETINFO_ITEM(board,'+BUS'))
    track(board,'+BUS',(8,3),(8,18),width=1)
    start,end=pcbnew.VECTOR2I_MM(5,10),pcbnew.VECTOR2I_MM(20,5)
    native_calls=[]
    def receiver(legs):
        native_calls.append(legs)
        return True
    result=fr._guarded_profiled_lastmile_legs(board,start,end,200000,pcbnew.F_Cu,
        200000,board.GetNetcodeFromNetname('/SCALAR'),
        lambda a,b,h:fr._edge_leg_clear(board,a,b,h+200000),
        allow_maze=False,maze_margin_mm=8,foreign_cache={},
        deadline_monotonic=time.monotonic()+3,perimeter_channels=True,path_validator=receiver)
    assert result and native_calls
    assert all(a.x==b.x or a.y==b.y or abs(a.x-b.x)==abs(a.y-b.y) for a,b,_ in result)
    # This is still native guard + receiver evidence, not a shortest/no-path claim.
    assert any(a.y<2_300_000 or b.y<2_300_000 for a,b,_ in result)


@pytest.mark.parametrize('value',[1,'yes',None])
def test_perimeter_requires_explicit_bounded_opt_in(value):
    board=_board([(5,5,'/S'),(10,10,'/S')],edge=(0,0,20,20))
    with pytest.raises(ValueError,match='explicit_bounded_maze_refinement_mode_required'):
        fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I_MM(5,5),
            pcbnew.VECTOR2I_MM(10,10),200000,pcbnew.F_Cu,200000,
            board.GetNetcodeFromNetname('/S'),lambda *a:True,perimeter_channels=value)


def test_outside_spines_cannot_waive_outline_or_receiver_refusal():
    board=_board([(5,5,'/S'),(10,10,'/S')],edge=(0,0,20,20))
    seen=[]
    result=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I_MM(5,5),
        pcbnew.VECTOR2I_MM(10,10),200000,pcbnew.F_Cu,200000,
        board.GetNetcodeFromNetname('/S'),lambda a,b,h:fr._edge_leg_clear(board,a,b,h+200000),
        allow_maze=False,maze_margin_mm=8,perimeter_channels=True,
        deadline_monotonic=time.monotonic()+2,path_validator=lambda legs:seen.append(legs) or False)
    assert result is None and seen
    assert all(.3e6<=p.x<=19.7e6 and .3e6<=p.y<=19.7e6
        for legs in seen for a,b,_ in legs for p in (a,b))


def test_full_native_inventory_uses_256_box_bound_not_64_contact_hint_bound():
    boxes=[(i*1000,10000,i*1000+500,11000) for i in range(256)]
    assert channels.perimeter_channel_paths((0,0),(300000,300000),boxes,
        (-50000,-50000,350000,350000),inflation=1000)
    with pytest.raises(ValueError):
        channels.perimeter_channel_paths((0,0),(300000,300000),boxes+[boxes[0]],
            (-50000,-50000,350000,350000),inflation=1000)
