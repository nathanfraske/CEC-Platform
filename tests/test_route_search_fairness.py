"""Search cost changes priority only, never live net or geometric eligibility."""
import ast
from pathlib import Path
import pytest
import cec_certificate_repair as repair


@pytest.mark.parametrize('max_mm', [40., 80.])
def test_deep_worker_does_not_silently_drop_long_residual_branches(monkeypatch, max_mm):
    from unittest.mock import Mock
    board = Mock()
    synthesize = Mock(return_value={'closed': 0})
    monkeypatch.setattr(repair.pcbnew, 'LoadBoard', lambda p: board)
    monkeypatch.setattr(repair.cec_fr, '_project_netclass_resolver', lambda p: None)
    monkeypatch.setattr(repair.cec_fr, 'synthesize_lastmile', synthesize)
    report = repair._lastmile_worker('synthetic', ('unfamiliar-rail',), 12, 8,
                                    wall_timeout_s=20, max_route_mm=max_mm)
    args = synthesize.call_args.kwargs
    assert args['max_mm'] == args['maze_max_mm'] == max_mm
    assert args['wall_timeout_s'] == args['per_net_timeout_s'] == 20
    assert args['include_nets'] == {'unfamiliar-rail'} and args['clearance'] == 0
    assert report['residual_search_domain_mm'] == max_mm


@pytest.mark.parametrize('max_mm', [0, -1, 81, float('inf'), float('nan')])
def test_invalid_residual_search_domain_fails_before_native_load(monkeypatch, max_mm):
    from unittest.mock import Mock
    load = Mock()
    monkeypatch.setattr(repair.pcbnew, 'LoadBoard', load)
    with pytest.raises(ValueError):
        repair._lastmile_worker('unused', (), 8, 4, max_route_mm=max_mm)
    load.assert_not_called()


def completion():
    return {'refused_details': [
        {'net': net, 'distance_mm': distance, 'certificate': {'net': net, 'distance_mm': distance}}
        for net, distance in [('near', 1), ('islands', 8), ('islands', 12), ('far', 20)]]}


def test_deep_portfolio_spends_full_time_on_real_maze_not_second_breadth():
    tree=ast.parse(Path(repair.__file__).read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='repair_board')
    calls=[n for n in ast.walk(function) if isinstance(n,ast.Call)
           and isinstance(n.func,ast.Name) and n.func.id=='_spawn_apply'
           and n.args and isinstance(n.args[0],ast.Name) and n.args[0].id=='_lastmile_worker']
    deep=[n for n in calls if isinstance(n.args[1],ast.Tuple)
          and any(isinstance(v,ast.Name) and v.id=='deep_route_inner_s' for v in n.args[1].elts)]
    assert len(deep)==1 and ast.literal_eval(deep[0].args[1].elts[4]) is False


def test_more_open_opportunities_then_distance_but_no_net_is_dropped():
    assert repair._rank_single_net_closure_targets(
        ['far','near','islands','unknown'],completion(),value_first=True)==[
            'islands','near','far','unknown']


@pytest.mark.parametrize('stage',['broad_canonical_closure','deep_route_portfolio'])
def test_untried_work_precedes_previously_spent_prefix(stage):
    history=repair.route_search_history({},[{'stage':stage,'net':'near'},
        {'stage':stage,'net':'islands'}])
    result=repair._rank_single_net_closure_targets(
        ['near','islands','far','unknown'],completion(),history=history,
        stage=stage,value_first=True)
    assert result==['far','unknown','islands','near']
    assert history['release_authority'] is False


def test_history_is_revision_bound_and_stays_compact():
    stage='deep_route_portfolio'
    old={'algorithm_revision':'old','stages':{stage:{'near':100}}}
    reset=repair.route_search_history({'route_search_history':old})
    assert not reset['stages'][stage]
    first=repair.route_search_history({},[{'stage':stage,'net':'near'}])
    second=repair.route_search_history({'route_search_history':first},[{'stage':stage,'net':'far'}])
    assert second['stages'][stage]=={'far':1,'near':1}
    many=repair.route_search_history({},[{'stage':stage,'net':str(i)} for i in range(500)])
    assert len(many['stages'][stage])==256


@pytest.mark.parametrize('bad',[None,[],5,'bad',{'stages':[]},
    {'algorithm_revision':repair.REPAIR_ALGORITHM_REVISION,'stages':{'deep_route_portfolio':[]}}])
def test_malformed_hint_never_becomes_geometry_authority(bad):
    assert repair.route_search_history({'route_search_history':bad})['stages']=={
        'broad_canonical_closure':{},'deep_route_portfolio':{}}
