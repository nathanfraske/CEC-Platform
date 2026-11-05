"""Actual endpoint landings do not arbitrarily forbid a route-body face."""
import pytest
from cec_native_ordinary_chain_scope import migration_endpoint_faces
from root_native_ordinary_terminal_migration_20261012 import migration_faces


@pytest.mark.parametrize('source,body,landings',[(2,[0,6,2],[0,6]),(0,[2,8,0],[2]),(6,[0,2,6],[0,2])])
def test_endpoint_and_body_faces_are_independent_but_both_source_bounded(source,body,landings):
    result=migration_endpoint_faces(body,landings,source_layer=source)
    assert result==sorted(landings) and source in body and source not in result
    scope=dict(net='/RENAMED/ORDINARY',source_layer=source,endpoints_nm=[[1000000,2000000],[3000000,4000000]])
    rows=[dict(uuid=str(i),net=scope['net'],at_nm=point,kind='PCB_VIA',native_full_stack_plated=True,
        diameter_nm=600000,drill_nm=300000,layers=[0,2,4,6,8,10]) for i,point in enumerate(scope['endpoints_nm'])]
    actual=migration_faces(rows,scope,eligible_nets={scope['net']},enabled_layers=[0,2,4,6,8,10],
        target_layers=result,plane_layers=[4,10])
    assert all(row['target_layers']==result and row['new_endpoint_vias']==0 for row in actual['endpoints'])
    assert not actual['current_authority'] and not actual['release_authority']


@pytest.mark.parametrize('body,landings,source',[
    ([0,6,2],None,2),([0,6],[0,2],2),([0,6],[0,0],2),([0,6],[],2),
    ([0,6],[True],2),([0,6],[0],True),([0,0],[0],2),([0,6,64],[0],2),
    ([],[0],2),([0,2,4,6,8],[0],2),([0,6],['0'],2)])
def test_body_landing_split_grants_no_new_layer_or_source_waiver(body,landings,source):
    with pytest.raises(ValueError):migration_endpoint_faces(body,landings,source_layer=source)


def test_existing_single_target_call_keeps_the_old_default():
    assert migration_endpoint_faces([6],None,source_layer=2)==[6]
