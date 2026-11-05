"""Plan-only comparisons reject metadata camouflage; live replay is separate."""
import copy
import pytest
from root_unchanged_annotation_epoch_20261024 import _compare_step,receive


def fixture():
    declaration=dict(schema=1,origin=dict(path='/original',sha256='0'*64),steps=[
        dict(kind='print_context',candidate=dict(path='/base',sha256='1'*64),proposal=dict(path='/print',sha256='2'*64)),
        dict(kind='reference_map',candidate=dict(path='/selected',sha256='3'*64),proposal=dict(path='/old',sha256='4'*64))])
    parent=dict(boards=[dict(board='b'+str(i),path='/selected'if i==0 else'/b'+str(i),
        sha256='3'*64,expected_opens=0,expected_warnings=0,**(dict(annotation_transition=declaration)if i==0 else{}))for i in range(9)],
        scope='nine',out_of_scope=['argb-standard'])
    current=copy.deepcopy(parent);current['parent_plan']=dict(path='/parent',sha256='5'*64)
    current['fresh_annotation_recipe_receiving']=dict(path='/proof',sha256='6'*64)
    current['boards'][0]['annotation_transition']['steps'][1]['proposal']=dict(path='/fresh',sha256='7'*64)
    proof=dict(board='b0',selected='/selected',selected_sha256='3'*64,
        annotation_transition=copy.deepcopy(current['boards'][0]['annotation_transition']))
    return parent,current,proof


def test_exact_metadata_recompile_is_only_plan_comparison_not_admission():
    parent,current,proof=fixture();assert _compare_step(parent,current,proof)=='b0'
    assert 'ok'not in proof and 'receiving'not in proof


@pytest.mark.parametrize('fault',['pcb','counts','rule','second_board','origin','base','kind','candidate','scope','proof_selected'])
def test_non_recipe_changes_cannot_be_camouflaged_as_epoch_refresh(fault):
    parent,current,proof=fixture();row=current['boards'][0];decl=row['annotation_transition']
    if fault=='pcb':row['sha256']='8'*64
    elif fault=='counts':row['expected_opens']=1
    elif fault=='rule':row['rule']='relaxed'
    elif fault=='second_board':current['boards'][1]['expected_warnings']=1
    elif fault=='origin':decl['origin']['path']='/elsewhere'
    elif fault=='base':decl['steps'][0]['candidate']['path']='/elsewhere'
    elif fault=='kind':decl['steps'][1]['kind']='reference_fields'
    elif fault=='candidate':decl['steps'][1]['candidate']['path']='/elsewhere'
    elif fault=='scope':current['scope']='other'
    elif fault=='proof_selected':proof['selected']='/elsewhere'
    if fault in('origin','base','kind','candidate'):proof['annotation_transition']=copy.deepcopy(decl)
    with pytest.raises(ValueError):_compare_step(parent,current,proof)


@pytest.mark.parametrize('value',[True,0,10,1.5,None])
def test_traversal_budget_is_rejected_before_filesystem_access(value):
    with pytest.raises(ValueError,match='bounded_unchanged_annotation_epoch'):
        receive('/absent','/absent',maximum_links=value)
