"""No coordinate, refdes, board or net-name exceptions in control preclear."""
import copy
import pytest
from cec_native_ordinary_chain_scope import chain


def fixture(net='ordinary_A',face=0,offset=0):
    rows=[]
    for index,(a,b) in enumerate((((0,0),(1000000,1000000)),
                                 ((1000000,1000000),(1000000,2000000)))):
        rows.append(dict(uuid='source_'+str(index),kind='PCB_TRACK',net=net,layer=face,
            width_nm=200000,locked=True,grouped=False,
            start_nm=[v+offset for v in a],end_nm=[v+offset for v in b]))
    return rows,[r['uuid'] for r in rows],[net]


@pytest.mark.parametrize('net,face,offset',[('ordinary_A',0,0),('/sheet/other_B',2,35000000),
    ('renamed_C',6,-12000000),('different_D',8,54000000)])
def test_exact_locked_ordinary_scope_is_data_not_name_or_position(net,face,offset):
    rows,ids,nets=fixture(net,face,offset);saved=copy.deepcopy(rows)
    result=chain(rows,ids,nets,allow_locked_track_uuids=ids)
    assert result['locked_scope_used']==ids
    assert result['source_layer']==face and result['source_width_nm']==200000
    assert result['native_saved_boundary_and_partition_receiving_required']
    assert not result['current_or_pair_or_ground_authority']
    assert not result['release_authority'] and rows==saved


def test_locked_is_protected_by_default_and_partial_scope_is_not_full_permission():
    rows,ids,nets=fixture()
    for allowed in ([],[ids[0]]):
        with pytest.raises(ValueError):chain(rows,ids,nets,allow_locked_track_uuids=allowed)


def test_unlocked_legacy_chain_needs_no_lock_scope():
    rows,ids,nets=fixture()
    for row in rows:row['locked']=False
    assert chain(rows,ids,nets)['locked_scope_used']==[]


@pytest.mark.parametrize('fault',['power','pair','ground','group','stale','duplicate',
    'extra_lock','not_locked','wide','boolean_width','boolean_layer','unknown_lock',
    'boolean_point','mixed_net','mixed_layer','mixed_width','zero','branch','disconnected'])
def test_scope_never_reclassifies_or_mutates_invalid_source(fault):
    rows,ids,nets=fixture();allowed=ids[:]
    if fault in ('power','pair','ground'):nets=[]
    elif fault=='group':rows[0]['grouped']=True
    elif fault=='stale':ids.append('missing')
    elif fault=='duplicate':rows.append(copy.deepcopy(rows[0]))
    elif fault=='extra_lock':allowed.append('another_source')
    elif fault=='not_locked':rows[0]['locked']=False
    elif fault=='wide':rows[0]['width_nm']=500000
    elif fault=='boolean_width':rows[0]['width_nm']=True
    elif fault=='boolean_layer':rows[0]['layer']=True
    elif fault=='unknown_lock':rows[0]['locked']=1
    elif fault=='boolean_point':rows[0]['start_nm'][0]=True
    elif fault=='mixed_net':rows[0]['net']='unrelated'
    elif fault=='mixed_layer':rows[0]['layer']=2
    elif fault=='mixed_width':rows[0]['width_nm']=250000
    elif fault=='zero':rows[0]['end_nm']=rows[0]['start_nm'][:]
    elif fault=='branch':
        other=copy.deepcopy(rows[1]);other['uuid']='branch';other['end_nm']=[2000000,2000000]
        rows.append(other);ids.append('branch');allowed.append('branch')
    elif fault=='disconnected':rows[1]['start_nm']=[5000000,5000000]
    saved=copy.deepcopy(rows)
    with pytest.raises(ValueError):chain(rows,ids,nets,allow_locked_track_uuids=allowed)
    assert rows==saved


@pytest.mark.parametrize('values',[['source_0','source_0'],[''],[True],list(map(str,range(33)))])
def test_uuid_scopes_are_finite_and_exact(values):
    rows,ids,nets=fixture()
    with pytest.raises(ValueError):chain(rows,ids,nets,allow_locked_track_uuids=values)
