"""Joint reference seats free only positively moved ink, never old body space."""
import copy
import json
import time

import pcbnew
import pytest
from shapely.geometry import box
import cec_force_current as force
import cec_reference_field_seating as seats
from test_dense_reference_mapping import fixture


def choice(owner,shape,index=0):
    return (0.,float(index),0,[index,0],shape,dict(owner=owner,index=index))


def select(menus,originals,faces=None):
    return seats._cooperative_assignment(menus,originals,
        faces or {u:0 for u in menus},.15,time.monotonic()+10.)


def test_mutually_blocked_old_ink_can_move_together_without_freeing_a_stay():
    left,right=box(0,0,1,1),box(3,0,4,1)
    # Each individually valid owner-local seat overlaps the other's wrong
    # original label. A greedy original-ink obstacle rejects both. This
    # geometry oracle grants no change of physical owner/body association.
    rows,q=select({'a':[choice('a',right)],'b':[choice('b',left)]},
        {'a':left,'b':right})
    assert {r['owner']for r in rows}=={'a','b'}
    assert q['literal_stay_owners']==[]and q['immutable_original_ink_retained_for_every_stay']


def test_unmovable_neighbour_keeps_its_original_ink_and_cannot_be_overlapped():
    left,right=box(0,0,1,1),box(3,0,4,1)
    rows,q=select({'a':[choice('a',right)],'b':[]},{'a':left,'b':right})
    assert rows==[]and q['literal_stay_owners']==['a','b']


def test_three_way_original_ink_cycle_has_a_complete_deterministic_solution():
    shapes={u:box(i*3,0,i*3+1,1)for i,u in enumerate('abc')}
    menus={u:[choice(u,shapes[v])]for u,v in zip('abc','bca')}
    rows,first=select(menus,shapes);again,second=select(menus,shapes)
    assert len(rows)==3 and rows==again and first==second


def test_actual_faces_are_separate_but_same_face_clearance_is_not_relaxed():
    target=box(2,2,3,3);old={'a':box(0,0,1,1),'b':box(5,5,6,6)}
    menus={u:[choice(u,target)]for u in old}
    rows,q=select(menus,old,{'a':0,'b':1});assert len(rows)==2
    rows,q=select(menus,old,{'a':0,'b':0});assert len(rows)==1
    assert len(q['literal_stay_owners'])==1


def test_finite_search_failure_never_exports_a_partial_ink_selection(monkeypatch):
    monkeypatch.setattr(seats.joint,'solve',lambda *a,**k:dict(complete=False,
        input_unchanged=True,selected={'a':dict(id='0')}))
    with pytest.raises(ValueError,match='not_completed'):
        select({'a':[choice('a',box(2,2,3,3))]},{'a':box(0,0,1,1)})


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_public_cooperative_recipe_reconstructs_and_receives_all_literal_native_properties(tmp_path,quarter,back):
    source,grade,uid=fixture(tmp_path,roomy=True,quarter=quarter,back=back)
    original=source.read_bytes()
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',
        maximum_components=1,cooperative=True)
    assert q['request']['cooperative']is True
    assert q['cooperative_search']['selected'].keys()=={uid}
    child=force._copy_family(source,tmp_path/'cooperative-child')
    seats.write_private(source,child,json.loads(json.dumps(q)))
    r=seats.receive(source,child,q)
    assert r['ok']and r['complete'],r
    board=pcbnew.LoadBoard(str(child));fp=next(iter(board.GetFootprints()))
    assert fp.IsFlipped()is back and fp.Reference().IsMirrored()is back
    assert fp.Reference().GetTextAngleDegrees()in(0,90)
    assert source.read_bytes()==original and r['all_copper_parts_pads_poses_models_rules_exact']


@pytest.mark.parametrize('fault',['record','selection','stay','mode'])
def test_json_cooperative_recipe_does_not_own_any_extra_annotation_changes(tmp_path,fault):
    source,grade,_=fixture(tmp_path,roomy=True)
    q=seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',cooperative=True)
    bad=copy.deepcopy(q)
    if fault=='record':bad['records'][0]['at_nm'][0]+=1
    elif fault=='selection':bad['cooperative_search']['selected']['forged']='0'
    elif fault=='stay':bad['cooperative_search']['literal_stay_owners'].append('forged')
    else:bad['request']['cooperative']=False
    with pytest.raises(ValueError,match='stale_or_forged'):
        seats.construct(source,bad)


def test_cooperative_cannot_ignore_actual_mask_bodies_or_unknown_original_ink(tmp_path,monkeypatch):
    source,grade,_=fixture(tmp_path,roomy=True)
    monkeypatch.setattr(seats.masks,'native_mask_artwork',lambda *a:(box(0,0,60,60),{}))
    with pytest.raises(ValueError,match='no_readable_clear'):
        seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',cooperative=True)


@pytest.mark.parametrize('value',[1,'yes',None,[]])
def test_cooperative_flag_is_explicit_not_truthy(tmp_path,value):
    source,grade,_=fixture(tmp_path,roomy=True)
    with pytest.raises(ValueError,match='bounded_explicit_cooperative'):
        seats.plan(source,grade=grade,board_hint='explicit_synthetic_legend',cooperative=value)
