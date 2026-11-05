"""Reviewed bodies reserve front map space without altering Source courts."""
import copy

import pytest
import cec_additive_route_receiving as ast
import cec_force_current as force
import cec_mask_search_reference_mapping as maps
from test_reference_reviewed_body_reservations import with_remote_missing_body,CONTRACT


def test_known_missing_remote_body_allows_a_received_front_map_not_an_inferred_courtyard(tmp_path):
    source,grade,uid,remote=with_remote_missing_body(tmp_path);before=source.read_bytes()
    old=maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend',owner_uuid_scope=[uid])
    assert old['mode']=='opposite_face_projected_courtyard'
    q=maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend',owner_uuid_scope=[uid],
        reviewed_courtyard_contract_ids=[CONTRACT],reverse_ownership='rigid_root_group_per_component')
    assert q['mode']=='nearby_front_mapping_chart'
    assert q['reviewed_body_reservations'][0]['records'][0]['footprint_uuid']==remote
    assert q['reviewed_body_helper_dependencies']
    child=force._copy_family(source,tmp_path/'private');maps.write_private(source,child,q)
    proof=maps.receive(source,child,q);assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()==before
    assert ast._nodes(source)[1][remote]==ast._nodes(child)[1][remote]
    assert q['reviewed_bodies_are_obstacles_only_not_source_courtyard_or_overlap_admission']
    assert not proof['release_authority']


@pytest.mark.parametrize('fault',['value','land','partial'])
def test_explicit_reviewed_map_context_does_not_waive_wrong_or_partial_source_body(tmp_path,fault):
    source,grade,uid,_=with_remote_missing_body(tmp_path,fault=fault)
    with pytest.raises(ValueError):
        maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend',owner_uuid_scope=[uid],
            reviewed_courtyard_contract_ids=[CONTRACT])


@pytest.mark.parametrize('fault',['envelope','hash','helper','omit_request'])
def test_map_reconstructs_the_entire_reviewed_body_context(tmp_path,fault):
    source,grade,uid,_=with_remote_missing_body(tmp_path)
    q=maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend',owner_uuid_scope=[uid],
        reviewed_courtyard_contract_ids=[CONTRACT])
    bad=copy.deepcopy(q)
    if fault=='envelope':bad['reviewed_body_reservations'][0]['records'][0]['world_points_nm'][0][0]+=1
    elif fault=='hash':bad['reviewed_body_reservations'][0]['source_sha256']='0'*64
    elif fault=='helper':bad['reviewed_body_helper_dependencies'][next(iter(bad['reviewed_body_helper_dependencies']))]='0'*64
    else:del bad['reviewed_courtyard_contract_ids']
    with pytest.raises(ValueError):maps.construct(source,bad)


@pytest.mark.parametrize('ids',[None,'a',[''],[True],[CONTRACT,CONTRACT],list(map(str,range(9)))])
def test_reviewed_map_body_request_is_explicit_finite_and_distinct(tmp_path,ids):
    source,grade,uid,_=with_remote_missing_body(tmp_path)
    with pytest.raises(ValueError,match='bounded_explicit_reviewed'):
        maps.plan(source,grade=grade,board_hint='explicit_synthetic_legend',owner_uuid_scope=[uid],
            reviewed_courtyard_contract_ids=ids)
