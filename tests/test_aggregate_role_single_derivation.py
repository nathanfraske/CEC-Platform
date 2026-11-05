"""Same-call native leaf observations are used once, never cached authority.

Canonical hierarchy exports/native copper are real. Only the inherited
aggregate-current fixture is synthetic; this grants no new rail rating.
"""
import copy
import pcbnew
import pytest
import cec_additional_aggregate_macro as aggregate
import cec_aggregate_cap_ground_leaf as ground
import cec_source_aggregate_capacitor_cell as cap
from test_aggregate_cap_ground_leaf import fixture


def context(tmp_path,monkeypatch,quarter=0):
    source,root,board,pad,ids,_=fixture(tmp_path,monkeypatch,quarter)
    fp=pad.GetParentFootprint();owner=board.FindFootprintByReference('AMP73')
    x,y=-1000000,-2000000
    for _ in range(quarter):x,y=y,-x
    poses={fp.GetReference():[(x+15000000)/1e6,(y+15000000)/1e6,fp.GetOrientationDegrees()],
        owner.GetReference():[owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()]}
    return source,root,board,pad,ids,poses


@pytest.mark.parametrize('quarter',range(4))
def test_distinct_fresh_leaf_derives_canonical_current_and_selected_minima_once(tmp_path,monkeypatch,quarter):
    source,root,board,pad,ids,poses=context(tmp_path,monkeypatch,quarter)
    calls={name:0 for name in ('_owner','_canonical','_unassigned')}
    for name in calls:
        original=getattr(cap,name)
        def counted(*args,_name=name,_original=original,**kwargs):
            calls[_name]+=1
            return _original(*args,**kwargs)
        monkeypatch.setattr(cap,name,counted)
    before=cap.row._source_binding(board);raw=source.read_bytes()
    roles=aggregate.collect(board,poses,board_hint=str(root))
    proof=roles[pad.GetParentFootprint().GetReference()];leaf=proof['source_Ground_leaf']
    assert calls==dict(_owner=1,_canonical=1,_unassigned=1)
    assert leaf['track_uuids']==ids
    for name in ('canonical_source','unchanged_selected_bypass_assignments','aggregate_domain',
        'aggregate_contract','current_contract','source_reference_map'):
        assert proof[name]==leaf[name]
    assert proof['maximum_Ground_return_mm']==.8 and not proof['new_barrel_authority']
    assert proof['Source_Ground_leaf_retirement_requires_fresh_independent_ownership']
    assert raw==source.read_bytes()and before==cap.row._source_binding(board)


@pytest.mark.parametrize('fault',['source','source_sha256','source_native_binding','source_family',
    'code_identity','footprint_uuid','pad_uuid','owner','net','scope','source_reference_map'])
def test_a_mismatched_fresh_leaf_observation_cannot_be_composed(tmp_path,monkeypatch,fault):
    _,root,board,_,_,poses=context(tmp_path,monkeypatch)
    original=ground.plan
    def changed(*args,**kwargs):
        proof=copy.deepcopy(original(*args,**kwargs))
        if fault=='source_reference_map':proof[fault]={}
        elif isinstance(proof[fault],dict):proof[fault]={}
        else:proof[fault]='wrong'
        return proof
    monkeypatch.setattr(ground,'plan',changed)
    before=cap.row._source_binding(board)
    with pytest.raises(ValueError,match='fresh_Ground_role_Source_binding'):
        aggregate.collect(board,poses,board_hint=str(root))
    assert before==cap.row._source_binding(board)


def test_each_separate_collection_freshly_rederives_the_actual_leaf(tmp_path,monkeypatch):
    _,root,board,_,_,poses=context(tmp_path,monkeypatch)
    calls=[];original=ground.plan
    def counted(*args,**kwargs):
        calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(ground,'plan',counted)
    first=aggregate.collect(board,poses,board_hint=str(root))
    first['RENAMED_C']['source_Ground_leaf']['track_uuids']=[]
    second=aggregate.collect(board,poses,board_hint=str(root))
    assert len(calls)==2 and second['RENAMED_C']['source_Ground_leaf']['track_uuids']


def test_original_isolated_no_Ground_leaf_path_still_derives_canonical_once(tmp_path,monkeypatch):
    from test_additional_aggregate_macro import fixture as isolated
    _,root,parent,_,proposal=isolated(tmp_path,monkeypatch)
    calls=[];original=cap._canonical
    def counted(*args,**kwargs):calls.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(cap,'_canonical',counted)
    proof=aggregate.collect(parent,proposal['poses'],board_hint=str(root))['RENAMED_C']
    assert len(calls)==1 and proof['source_Ground_leaf']is None and proof['no_Source_copper_retirement']
