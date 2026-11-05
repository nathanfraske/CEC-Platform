"""Broader physical search must preserve force widths, guards and deadlines."""
from unittest import mock
import pytest
import cec_fr
import cec_field_coupling as field
import cec_force_current as force
from test_force_current import _component_family_fixture


@pytest.mark.parametrize('margin,perimeter',[(.25,False),(2.,False),(12.,True),(6,True)])
def test_bounded_channel_policy(margin,perimeter):
    result=force._force_channel_policy(margin,perimeter)
    assert result['maze_margin_mm']==float(margin)
    assert result['perimeter_channels'] is perimeter
    assert result['unchanged_current_width_and_clearance']
    assert not result['physical_no_path_proof']


@pytest.mark.parametrize('margin,perimeter',[(True,False),(0,False),(.249,False),
    (12.001,False),(float('nan'),False),(float('inf'),False),('2',False),
    (2,0),(2,1),(2,None),(2,'yes')])
def test_unknown_or_unbounded_search_is_not_permission(margin,perimeter):
    with pytest.raises(ValueError,match='bounded_explicit_force_channel_policy'):
        force._force_channel_policy(margin,perimeter)


@pytest.mark.parametrize('renamed,reverse',[(False,False),(True,True)])
def test_native_force_router_receives_search_policy_without_dimension_relief(tmp_path,renamed,reverse):
    path=tmp_path/'native_channels.kicad_pcb'
    board,row,domain,contract=_component_family_fixture(path,renamed=renamed,reverse=reverse)
    inventory=field._field_snapshot_inventory(board)
    calls=[]
    def route(*args,**kwargs):
        calls.append((args,kwargs))
        return None
    with mock.patch.object(cec_fr,'_guarded_lastmile_legs',side_effect=route):
        plan=force._construct(board,str(path),row['net'],domain,contract,
            max_pairs=6,max_bridges=4,deadline=force.time.monotonic()+5.,allow_maze=True,
            maze_margin_mm=12.,perimeter_channels=True)
    assert calls
    for args,kwargs in calls:
        assert kwargs['maze_margin_mm']==12. and kwargs['perimeter_channels'] is True
        assert kwargs['deadline_monotonic'] <= plan['phase_wall_budgets'][0]['global_deadline_monotonic']
        assert args[3] >= min(int(x*1e6) for x in contract['required_by_layer_mm'].values())
        assert callable(args[7])
    assert plan['bridge_count']==0 and not plan['physical_no_path_proof']
    assert field._field_snapshot_inventory(board)==inventory


def test_default_channel_policy_is_unchanged():
    assert force._force_channel_policy(2.,False)['perimeter_channels'] is False
