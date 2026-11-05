"""A received measurement path is not permission to ignore graph evidence."""
import copy
import pytest
import cec_measurement_leaf_evidence as evidence


def example(owner='INPUT'):
    old=dict(pad_uuid='root',owner=owner,pin='4',net='shared-force-name',layer=0,width_nm=250000,
        boundary_uuids=['boundary'],track_uuids=['old-a','old-b','old-c'])
    new=dict(old,track_uuids=['new-a','new-b','new-c','new-d','new-e'])
    first=['shunt','boundary','old-c','old-b','old-a','root']
    last=['shunt','boundary','new-e','new-d','new-c','new-b','new-a','root']
    return first,last,old,new


@pytest.mark.parametrize('owner',['INPUT','UNRELATED_MONITOR_19','not-a-board-policy'])
def test_only_complete_owned_run_can_change_between_exact_native_context(owner):
    first,last,old,new=example(owner);frozen=copy.deepcopy((first,last,old,new))
    assert evidence._rebind_path(first,last,old,new)==first
    assert (first,last,old,new)==frozen


@pytest.mark.parametrize('fault',['old_missing','new_missing','new_order','new_context','old_context','extra_internal',
    'root','width','face','boundary','owner','net','duplicate_path','duplicate_ids','boolean_node','oversize','empty'])
def test_rebinding_cannot_hide_any_other_terminal_context_dimension_or_path_change(fault):
    first,last,old,new=example()
    if fault=='old_missing':first.remove('old-b')
    elif fault=='new_missing':last.remove('new-b')
    elif fault=='new_order':last[2],last[3]=last[3],last[2]
    elif fault=='new_context':last[0]='other-shunt'
    elif fault=='old_context':first[1]='not-the-boundary'
    elif fault=='extra_internal':last.insert(4,'foreign-branch')
    elif fault=='root':last[-1]='other-input'
    elif fault=='width':new['width_nm']+=1
    elif fault=='face':new['layer']=2
    elif fault=='boundary':new['boundary_uuids']=['different']
    elif fault=='owner':new['owner']='other-device'
    elif fault=='net':new['net']='other-net'
    elif fault=='duplicate_path':last.insert(1,'shunt')
    elif fault=='duplicate_ids':new['track_uuids'].append('new-a')
    elif fault=='boolean_node':last[0]=True
    elif fault=='oversize':last[:0]=['extra-'+str(n) for n in range(1024)]
    else:new['track_uuids']=[]
    with pytest.raises(ValueError):evidence._rebind_path(first,last,old,new)


@pytest.mark.parametrize('value',[True,False,0,11,float('nan'),float('inf')])
def test_input_path_receiving_has_no_boolean_or_unbounded_work_lease(value):
    r=evidence.receive('not-a-source','not-a-candidate',board_hint='not-a-policy',pad_uuids=['root'],timeout_s=value)
    assert not r['same_evidence'] and not r['comparison_complete'] and r['errors']
    assert not r['full_kelvin_qualification'] and not r['release_authority']


@pytest.mark.parametrize('value',[True,False,0,41,float('nan'),float('inf')])
def test_absolute_cut_lease_cannot_be_silently_widened(value):
    r=evidence.receive('not-a-source','not-a-candidate',board_hint='not-a-policy',pad_uuids=['root'],sense_timeout_s=value)
    assert not r['same_evidence'] and r['errors']
