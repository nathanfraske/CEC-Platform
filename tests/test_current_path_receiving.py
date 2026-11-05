import copy
import pytest
import cec_current_path_receiving as receiving


def graph(trace,rated):
    def parts(rows):return dict(components=[[dict(uuid=u,position_nm=[i,0])
        for u,i in ((u,ord(u)) for u in row)] for row in rows])
    return dict(trace_connectivity=parts(trace),rated_connectivity=parts(rated),
                required_by_layer_mm={'F.Cu':1.1})


def test_inherited_unrated_debt_is_not_qualified_but_is_preserved():
    before=graph(['ab','c'],['a','b','c'])
    result=receiving.compare(before,copy.deepcopy(before))
    assert result['ok'] and result['complete'] and not result['new_joins']
    assert not result['inherited_debt_qualified'] and not result['release_authority']


def test_better_open_count_with_new_thin_authority_join_is_rejected():
    before=graph(['ab','c'],['a','b','c']);after=graph(['abc'],['a','b','c'])
    result=receiving.compare(before,after)
    assert result['complete'] and not result['ok']
    assert result['unrated_new_joins']==[['a','c'],['b','c']]


def test_new_join_must_be_rated_even_with_other_inherited_debt():
    before=graph(['a','b','cd'],['a','b','c','d']);after=graph(['ab','cd'],['ab','c','d'])
    assert receiving.compare(before,after)['ok']


@pytest.mark.parametrize('fault',['lost_trace','lost_rated','pad_identity','width','duplicate','missing','empty'])
def test_uncertain_or_regressed_inventory_refuses(fault):
    before=graph(['ab','c'],['ab','c']);after=copy.deepcopy(before)
    if fault=='lost_trace':after['trace_connectivity']=graph(['a','b','c'],['ab','c'])['trace_connectivity']
    elif fault=='lost_rated':after['rated_connectivity']=graph(['ab','c'],['a','b','c'])['rated_connectivity']
    elif fault=='pad_identity':after['rated_connectivity']['components'][0][0]['position_nm'][0]+=1
    elif fault=='width':after['required_by_layer_mm']['F.Cu']=1.
    elif fault=='duplicate':after['trace_connectivity']['components'][1][0]['uuid']='a'
    elif fault=='missing':del after['trace_connectivity']
    else:after['rated_connectivity']['components']=[]
    assert not receiving.compare(before,after)['ok']
