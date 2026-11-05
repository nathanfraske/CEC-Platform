"""Immutable-parent signal screens prune work, never authorize copper."""
from unittest.mock import Mock
import pcbnew
import pytest
import cec_precision_route as route
import cec_fr
from cec_local_copper_cell import copper_inventory
from cec_native_items import discard_items


@pytest.mark.parametrize('blocked', [1, 2, 3])
def test_negative_parent_screens_keep_both_witnesses_without_mutation(blocked):
    calls=[]
    def screen(point, code, *, report):
        calls.append(code)
        report.update(ok=not bool(blocked & code), blockers=[dict(code=code)])
        return not bool(blocked & code)
    add, returns=Mock(),Mock()
    result=route._probe_matched_transition_field(dict(
        p=(4.,4.),n=(4.,4.8),center=(4.,4.4),side='start'),
        p_code=1,n_code=2,route_axis=(1.,0.),screen_signal_via=screen,
        add_signal_via=add,add_return_via=returns)
    assert not result['ok'] and calls==[1,2]
    assert result['p_via']['blockers']==[dict(code=1)]
    assert result['n_via']['blockers']==[dict(code=2)]
    add.assert_not_called();returns.assert_not_called()


def test_positive_parent_screen_cannot_skip_sequential_mutual_clearance():
    add=Mock(side_effect=[object(),None]);returns=Mock()
    result=route._probe_matched_transition_field(dict(
        p=(4.,4.),n=(4.,4.1),center=(4.,4.05),side='end'),
        p_code=1,n_code=2,route_axis=(1.,0.),
        screen_signal_via=Mock(return_value=True),
        add_signal_via=add,add_return_via=returns)
    assert not result['ok'] and add.call_count==2
    returns.assert_not_called()


@pytest.mark.parametrize('layer', ['F.Cu','In2.Cu','B.Cu'])
@pytest.mark.parametrize('quarter', [0,1])
def test_loaded_native_parent_screen_matches_exhaustive_and_preserves_copper(tmp_path,layer,quarter):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    for name in ('RENAMED_P','RENAMED_N','OBSTACLE','GND'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('UNRELATED_NAME');board.Add(fp)
    for index,name in enumerate(('RENAMED_P','RENAMED_N','GND')):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(index+1));pad.SetNet(board.FindNet(name))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(5+index*2,5));fp.Add(pad)
    def pose(point):
        x,y=point
        return (20-y,20+x) if quarter else (20+x,20+y)
    obstacle=pcbnew.PCB_TRACK(board)
    obstacle.SetNet(board.FindNet('OBSTACLE'))
    obstacle.SetStart(pcbnew.VECTOR2I_MM(*pose((0,-2))))
    obstacle.SetEnd(pcbnew.VECTOR2I_MM(*pose((0,2))))
    obstacle.SetWidth(pcbnew.FromMM(.3));obstacle.SetLayer(board.GetLayerID(layer))
    obstacle.SetLocked(True);board.Add(obstacle)
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    parent=pcbnew.LoadBoard(str(path));original=copper_inventory(parent)
    cache={};screens=0
    p_code=parent.GetNetcodeFromNetname('RENAMED_P')
    n_code=parent.GetNetcodeFromNetname('RENAMED_N')
    def screen(point,code,*,report):
        nonlocal screens
        screens+=1
        assert copper_inventory(parent)==original
        return cec_fr._via_spot_clear(parent,pcbnew.VECTOR2I_MM(*point),
            pcbnew.FromMM(.6),pcbnew.FromMM(.2),{code},
            drill_nm=pcbnew.FromMM(.3),net_code=code,
            foreign_cache=cache,report=report)
    def add(point,code,*,report):
        at=pcbnew.VECTOR2I_MM(*point)
        if not cec_fr._via_spot_clear(parent,at,pcbnew.FromMM(.6),
            pcbnew.FromMM(.2),{code},drill_nm=pcbnew.FromMM(.3),
            net_code=code,report=report):return None
        via=pcbnew.PCB_VIA(parent);via.SetNetCode(code);via.SetPosition(at)
        via.SetWidth(pcbnew.FromMM(.6));via.SetDrill(pcbnew.FromMM(.3))
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        parent.Add(via);return via
    def reset():
        discard_items(parent,[t for t in parent.GetTracks() if t.m_Uuid.AsString() not in original])
        assert copper_inventory(parent)==original
    # First two fail against immutable native copper, third is clear, last
    # individually clears the parent but fails against its new partner barrel.
    for raw_p,raw_n,expected in (
        ((0,0),(1,0),False),((1,0),(0,0),False),
        ((3,0),(3,1),True),((3,0),(3,.1),False)):
        p,n=pose(raw_p),pose(raw_n)
        row=dict(p=p,n=n,center=tuple((a+b)/2 for a,b in zip(p,n)),side='start')
        outcomes=[]
        for cached in (False,True):
            returns=Mock(return_value=([], 'covered'))
            result=route._probe_matched_transition_field(row,
                p_code=p_code,n_code=n_code,route_axis=(1.,0.),
                add_signal_via=add,add_return_via=returns,
                **(dict(screen_signal_via=screen) if cached else {}))
            outcomes.append(result['ok'])
            assert bool(returns.call_count)==expected
            reset()
        assert outcomes==[expected,expected]
    assert screens==8 and cache
