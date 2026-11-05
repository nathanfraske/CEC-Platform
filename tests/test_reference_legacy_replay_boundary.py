"""Old artifact observation cannot become new annotation construction."""
import copy
import json
from pathlib import Path
import pcbnew
import pytest
import cec_mask_search_reference_mapping as maps
import cec_force_current as force
import cec_field_coupling as field
from test_dense_reference_mapping import fixture
import root_receive_local_transaction_20261022 as transaction


def historical(tmp_path):
    source,grade,owner=fixture(tmp_path)
    options=dict(grade=grade,board_hint='synthetic',maximum_components=1,owner_uuid_scope=[owner],
        reverse_ownership='rigid_root_group_per_component',peripheral_reverse_seats=True)
    # Deliberately reconstruct the frozen v1 producer as TEST fixture data,
    # not via the new public constructor or any hardware admission path.
    old=maps._private.plan(source,**options)
    assert 'positive_leaders_only'not in old
    child=force._copy_family(source,tmp_path/'historical')
    maps._private.write_private(source,child,old)
    qpath=tmp_path/'old.json';force._write(qpath,old)
    return source,child,old,qpath,options


def test_read_only_existing_reconstruction_is_exact_and_cannot_publish_new_candidates(tmp_path):
    source,child,old,_,options=historical(tmp_path)
    before=[p.read_bytes()for p in(source,child)]
    current=maps.replay_existing_plan(source,child,**options)
    assert current==old
    proof=maps.receive(source,child,current)
    assert proof['ok']and proof['complete']and proof['read_only_legacy_replay']is True
    assert [p.read_bytes()for p in(source,child)]==before
    with pytest.raises(ValueError,match='legacy_annotation_replay_cannot_construct'):
        maps.construct(source,current)
    with pytest.raises(ValueError,match='legacy_annotation_replay_cannot_construct'):
        maps.write_private(source,child,current)
    fresh=maps.plan(source,**options)
    assert fresh['positive_leaders_only']is True
    assert maps.construct(source,fresh)


def test_whole_repair_phase_refuses_observational_legacy_scope(tmp_path):
    source,child,old,qpath,_=historical(tmp_path)
    phase=dict(kind='reference_map',candidate=str(child),candidate_sha256=force._hash(child),proposal=str(qpath))
    with pytest.raises(AssertionError,match='legacy_observational_annotation_scope'):
        transaction.receive_phase(source,source,phase,'synthetic')


@pytest.mark.parametrize('value',[False,None,0,1,'true',[],{}])
def test_new_public_generation_cannot_request_the_legacy_zero_leader_behavior(tmp_path,value):
    source,grade,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='new_reference_construction_requires_positive_native_leaders'):
        maps.plan(source,grade=grade,board_hint='synthetic',positive_leaders_only=value)


@pytest.mark.parametrize('fault',['glyph','pose','source'])
def test_historical_observation_cannot_excuse_unowned_source_or_candidate_changes(tmp_path,fault):
    source,child,old,_,options=historical(tmp_path)
    target=source if fault=='source'else child
    b=pcbnew.LoadBoard(str(target))
    if fault=='glyph':next(g for g in b.GetDrawings()if g.GetClass()=='PCB_TEXT').SetText('wrong')
    else:next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(b,target)
    with pytest.raises(ValueError):maps.replay_existing_plan(source,child,**options)


def test_serialized_strict_flag_cannot_relabel_an_old_plan(tmp_path):
    source,child,old,_,_=historical(tmp_path)
    forged=copy.deepcopy(old);forged['positive_leaders_only']=True
    # Even where the old geometry happened to be nondegenerate, changing a
    # public finite policy requires re-planning and all actual saved gates.
    new=maps.plan(source,grade=old['grade'],board_hint='synthetic',maximum_components=1,
        owner_uuid_scope=old['owner_uuid_scope'],reverse_ownership='rigid_root_group_per_component',
        peripheral_reverse_seats=True)
    assert new['positive_leaders_only']is True
    bad=copy.deepcopy(new);bad['positive_leaders_only']=False
    assert not maps.receive(source,child,bad)['ok']
