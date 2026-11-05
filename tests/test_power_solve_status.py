"""A failed complete-placement plan is repairable, never a qualified freeze."""
from copy import deepcopy
import pytest
import cec_power_guard_geometry as geometry


def deferred_state():
    return dict(placement_scope='complete', frozen_nets=[], pours=[], vias=[],
        corridors=[], reserve_report={}, exclude_pins=[],
        report={'renamed-main-current': dict(path_found=False, segments=0, bridges=0,
            layers_used=[], current_contract=dict(amps=7, margin=1.25, effective_A=8.75,
                                                  source='declared-budget')),
                'renamed-logic': dict(path_found=True, skipped=True, segments=0,
                                     bridges=0, layers_used=[])},
        future_owned_routes=[dict(net='renamed-sense', layers=['F.Cu', 'B.Cu'],
                                 x0=1, x1=3, y0=2, y1=4)])


def test_completed_placement_with_positive_failed_solve_retains_future_routes():
    state=deferred_state();old=deepcopy(state)
    status=geometry.solve_status(state)
    assert status['status']=='deferred' and status['deferred_nets']==['renamed-main-current']
    assert not status['frozen'] and not status['power_qualified'] and not status['release_authority']
    rows=geometry.reservations(state)
    assert {r['layer'] for r in rows}=={'F.Cu','B.Cu'}
    assert all(r['net']=='renamed-sense' for r in rows)
    assert state==old


@pytest.mark.parametrize('fault', ['no_report','empty_report','unknown_result','unrepresented_success',
    'missing_contract','corrupt_margin','boolean_current','claimed_geometry','claimed_barrel',
    'claimed_net','claimed_pin','claimed_admission','claimed_segments','claimed_layers'])
def test_missing_or_contradictory_freeze_never_gets_repair_permission(fault):
    state=deferred_state();row=state['report']['renamed-main-current']
    if fault=='no_report':state.pop('report')
    elif fault=='empty_report':state['report']={}
    elif fault=='unknown_result':row['path_found']=None
    elif fault=='unrepresented_success':row['path_found']=True
    elif fault=='missing_contract':row.pop('current_contract')
    elif fault=='corrupt_margin':row['current_contract']['effective_A']=7
    elif fault=='boolean_current':row['current_contract']['amps']=True
    elif fault=='claimed_geometry':state['pours']=[dict(net='renamed-main-current')]
    elif fault=='claimed_barrel':state['vias']=[dict(net='renamed-main-current')]
    elif fault=='claimed_net':state['frozen_nets']=['renamed-main-current']
    elif fault=='claimed_pin':state['exclude_pins']=['terminal-1']
    elif fault=='claimed_admission':state['exact_admission']=dict(passed=True)
    elif fault=='claimed_segments':row['segments']=1
    else:row['layers_used']=['F.Cu']
    with pytest.raises(ValueError):geometry.reservations(state)


@pytest.mark.parametrize('fault',['nan','missing_net','empty_layers','inverted','unknown_row'])
def test_failed_plan_cannot_drop_malformed_future_territory(fault):
    state=deferred_state();row=state['future_owned_routes'][0]
    if fault=='nan':row['x0']=float('nan')
    elif fault=='missing_net':row.pop('net')
    elif fault=='empty_layers':row['layers']=[None]
    elif fault=='inverted':row['x1']=row['x0']
    else:state['future_owned_routes']=[None]
    with pytest.raises(ValueError):geometry.reservations(state)


def test_any_missing_frozen_net_polygon_is_still_unknown():
    state=dict(placement_scope='complete', frozen_nets=['one','two'], corridors=[],
        pours=[dict(net='one',layer='F.Cu',polygon=[[0,0],[2,0],[2,2],[0,2]])])
    with pytest.raises(ValueError, match='frozen_power_net_without_exact_polygon'):
        geometry.reservations(state)
