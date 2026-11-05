import copy
from pathlib import Path
import pytest
from root_refresh_annotation_recipe_20261023 import recipe_options


@pytest.mark.parametrize('kind',['reference_fields','reference_map'])
def test_only_finite_public_inputs_are_recompiled_not_old_identity_or_success(kind):
    old=dict(board_hint='renamed',maximum_components=3,seed_index=2,owner_uuid_scope=['opaque-owner'],
        reverse_ownership='rigid_root_group_per_component',via_ink_policy='native_mask_and_bore',
        reviewed_courtyard_contract_ids=['exact-contract'],grade='/stale-grade',
        binding={'code_identity':'stale','source_family':'stale'},success=True,admitted=True,
        records=[{'forged_seat':True}],native_library_context={'caller':'not-authority'})
    before=copy.deepcopy(old)
    value=recipe_options(old,kind=kind,grade='/actual-fresh-grade',board_hint='renamed')
    assert old==before
    assert value['grade']==Path('/actual-fresh-grade')and value['owner_uuid_scope']==['opaque-owner']
    assert value['maximum_components']==3 and value['seed_index']==2
    assert not({'binding','success','admitted','records','native_library_context'}&value.keys())
    value['owner_uuid_scope'].append('different');assert old==before
    if kind=='reference_fields':assert value['timeout_s']==10.
    else:assert value['reverse_ownership']=='rigid_root_group_per_component'


@pytest.mark.parametrize('kind,hint,ownership',[
    ('unknown','renamed','rigid_root_group_per_component'),
    ('reference_map','wrong-board','rigid_root_group_per_component'),
    ('reference_map','renamed','footprint_children')])
def test_no_unknown_scope_board_or_visibility_ownership_can_be_relabelled(kind,hint,ownership):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,reverse_ownership=ownership)
    with pytest.raises(ValueError):recipe_options(old,kind=kind,grade='/actual',board_hint=hint)


def test_actual_nested_field_recipe_preserves_only_its_explicit_finite_search_mode():
    old=dict(board_hint='renamed',request=dict(maximum_components=8,seed_index=0,
        owner_uuid_scope=['owner'],max_gap_mm=2.,cooperative=True,timeout_s=7.,
        reviewed_courtyard_contract_ids=['exact-contract']),
        binding={'old':'not-authority'},cooperative_search={'selected':{'forged':'geometry'}})
    r=recipe_options(old,kind='reference_fields',grade='/fresh',board_hint='renamed')
    assert r==dict(grade=Path('/fresh'),board_hint='renamed',maximum_components=8,
        seed_index=0,owner_uuid_scope=['owner'],max_gap_mm=2.,cooperative=True,timeout_s=10.,
        reviewed_courtyard_contract_ids=['exact-contract'])


@pytest.mark.parametrize('enabled',[False,True])
def test_map_recipe_retains_explicit_peripheral_search_without_old_seat_authority(enabled):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component',
        peripheral_reverse_seats=enabled,records=[{'old_seat':'not-authority'}])
    before=copy.deepcopy(old)
    r=recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')
    assert r['peripheral_reverse_seats']is enabled
    assert 'records'not in r and old==before


def test_old_map_recipe_does_not_silently_enable_peripheral_search():
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component')
    r=recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')
    assert 'peripheral_reverse_seats'not in r


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_map_recipe_rejects_non_boolean_peripheral_search_flag(value):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component',peripheral_reverse_seats=value)
    with pytest.raises(ValueError,match='explicit_peripheral_reverse_search_flag_required'):
        recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')


@pytest.mark.parametrize('enabled',[False,True])
def test_approved_body_guide_recipe_is_an_explicit_boolean_not_old_geometry(enabled):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component',interrupt_projected_body_guides=enabled,
        records=[{'old_clipping':'never-authority'}])
    r=recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')
    assert r['interrupt_projected_body_guides']is enabled and 'records'not in r


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_body_guide_recipe_cannot_smuggle_truthy_waiver(value):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component',interrupt_projected_body_guides=value)
    with pytest.raises(ValueError,match='explicit_projected_body_guide_interruption_required'):
        recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')


@pytest.mark.parametrize('enabled',[False,True])
def test_rear_chart_recipe_replays_public_policy_not_old_fitted_geometry(enabled):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component',opposite_face_chart=enabled,
        records=[{'old_chart':'not-authority'}])
    r=recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')
    assert r['opposite_face_chart']is enabled and 'records'not in r


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_rear_chart_recipe_requires_boolean(value):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component',opposite_face_chart=value)
    with pytest.raises(ValueError,match='explicit_opposite_face_reference_chart_required'):
        recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')


@pytest.mark.parametrize('enabled',[False,True])
def test_fab_body_recipe_copies_only_the_explicit_policy(enabled):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component',project_native_fab_body=enabled)
    r=recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')
    assert r['project_native_fab_body']is enabled


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_fab_body_recipe_requires_boolean(value):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component',project_native_fab_body=value)
    with pytest.raises(ValueError,match='explicit_native_fab_body_projection_required'):
        recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_new_leader_policy_recipe_cannot_be_truthy(value):
    old=dict(board_hint='renamed',maximum_components=1,seed_index=0,
        reverse_ownership='rigid_root_group_per_component',positive_leaders_only=value)
    with pytest.raises(ValueError,match='explicit_positive_reference_leader_policy_required'):
        recipe_options(old,kind='reference_map',grade='/fresh',board_hint='renamed')
