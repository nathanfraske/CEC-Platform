"""Planned transitions do not inherit unrelated remote THT copper faces."""
import copy
import pytest
from root_native_power_authority_selector_20261012 import planned_barrel_faces


@pytest.mark.parametrize('body',[0,2,6,8,31])
@pytest.mark.parametrize('reverse',[False,True])
def test_remote_through_land_does_not_inflate_new_local_barrel(body,reverse):
    enabled=[0,2,4,6,8,31]
    launch=31 if body==0 else 0
    stacks=[[launch],enabled[:]]
    if reverse:stacks.reverse()
    before=copy.deepcopy(stacks)
    actual=planned_barrel_faces(selected_layer=body,enabled_layers=enabled,pad_layer_sets=stacks)
    wanted=[sorted([body,launch]),[]]
    if reverse:wanted.reverse()
    assert actual==wanted and stacks==before


def test_separate_barrels_keep_their_separate_endpoint_contacts():
    assert planned_barrel_faces(selected_layer=8,enabled_layers=[0,2,4,6,8,31],
        pad_layer_sets=[[0],[31]])==[[0,8],[8,31]]


def test_both_actual_same_face_endpoints_need_no_new_barrel():
    assert planned_barrel_faces(selected_layer=0,enabled_layers=[0,2,4,6,8,31],
        pad_layer_sets=[[0],[0,2,4,6,8,31]])==[[],[]]


@pytest.mark.parametrize('fault',[
    dict(selected_layer=3,enabled_layers=[0,2,31],pad_layer_sets=[[0],[31]]),
    dict(selected_layer=True,enabled_layers=[0,1,31],pad_layer_sets=[[0],[31]]),
    dict(selected_layer=0,enabled_layers=[0,2,31],pad_layer_sets=[[2]]),
    dict(selected_layer=0,enabled_layers=[0,2,31],pad_layer_sets=[[6],[31]]),
    dict(selected_layer=0,enabled_layers=[0,2,31],pad_layer_sets=[[0],[False]]),
])
def test_disabled_ambiguous_or_incomplete_native_stack_refuses(fault):
    with pytest.raises(ValueError):planned_barrel_faces(**fault)
