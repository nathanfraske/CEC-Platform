"""Reject impossible proximity early without denying a future qualified VIP."""
from copy import deepcopy
import pytest
import cec_support_craft_gate as craft


def row(supply=1.4,ground=1.4):
    return dict(cap_ref='BYPASS',owner_ref='OWNER',owner_pin='7',rail='/RENAMED',
        status='assigned',return_gate_mode='absolute_ground_distance',
        owner_supply_position_mm=[0,0],cap_supply_position_mm=[supply,0],
        owner_ground_position_mm=[0,1],cap_ground_position_mm=[ground,1],
        supply_excess_limit_mm=.25,tangent_target=dict(
            best_loop=dict(supply_mm=1.,loop_proxy_mm=2.)))


@pytest.mark.parametrize('transform',[
    lambda p:p,lambda p:[p[0]+37,p[1]-14],lambda p:[-p[1],p[0]],lambda p:[-p[0],p[1]]])
def test_both_possible_return_modes_fail_independent_of_names_or_pose(transform):
    item=row();item.update(cap_ref='C_RENAMED',owner_ref='U_RENAMED')
    for key in ('owner_supply_position_mm','cap_supply_position_mm',
                'owner_ground_position_mm','cap_ground_position_mm'):
        item[key]=transform(item[key])
    before=deepcopy(item)
    faults=craft.proximity_geometry_faults([item])
    assert len(faults)==1 and list(faults.values())[0]==pytest.approx(.15)
    assert item==before


@pytest.mark.parametrize('supply,ground',[(1.4,.2),(1.1,1.5),(1.25,1.5),(1.4,.85)])
def test_do_not_reject_when_either_permitted_mode_can_still_pass(supply,ground):
    assert craft.proximity_geometry_faults([row(supply,ground)])=={}


def test_shared_or_unavailable_geometry_is_not_an_early_authority():
    first=row();second=dict(first,cap_ref='SECOND')
    assert craft.proximity_geometry_faults([first,second])=={}
    assert craft.proximity_geometry_faults([dict(first,shared_pin_reference={'ok':True})])=={}
    for extra in (dict(status='missing'),dict(return_gate_mode='rail_to_rail_tangent_loop'),
                  dict(tangent_target={}),dict(owner_ground_position_mm=None),
                  dict(cap_supply_position_mm=[float('nan'),0])):
        assert craft.proximity_geometry_faults([dict(first,**extra)])=={}


def test_raw_reference_and_configured_limits_not_rounded_display_numbers():
    item=row(1.2502,1.5)
    item['ideal_supply_distance_mm']=1.0
    item['tangent_target']['best_loop']['supply_mm']=1.0004
    assert craft.proximity_geometry_faults([item])=={}
    item=row()
    assert craft.proximity_geometry_faults([item],loop_excess_max_mm=.81)=={}
    item['supply_excess_limit_mm']=.41
    assert craft.proximity_geometry_faults([item])=={}
    item=row(1.250001,1.5)
    assert craft.proximity_geometry_faults([item])


def test_return_constrained_reference_uses_existing_authority():
    item=row();item['tangent_target'].update(return_constrained=True,proximity_supply_mm=1.2)
    assert craft.proximity_geometry_faults([item])=={}


@pytest.mark.parametrize('limit',[-1,float('nan'),float('inf'),True])
def test_invalid_loop_limit_fails_closed(limit):
    with pytest.raises(ValueError):craft.proximity_geometry_faults([],loop_excess_max_mm=limit)
