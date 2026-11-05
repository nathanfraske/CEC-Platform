"""Fresh craft failures and missing evidence must never become clean/admitted."""
import ast
import copy
import inspect
import types

import pytest
import cec_dashboard as dashboard
import cec_source_retaining_ses_import as retaining


def inventory(issues=(),non45=()):
    return dict(issue_count=len(issues),issues=list(issues),
                non_octilinear_count=len(non45),non_octilinear=list(non45))


def metrics(report):
    return types.SimpleNamespace(detail={'route_quality':report})


@pytest.mark.parametrize('evidence',[None,{},['malformed'],'malformed', {'ok':False,'error':'native geometry exception'},
    {'craft_ok':True,'error':'partial evaluator failure'}, {'craft_ok':True,'ok':False},
    {'craft_ok':1}, {'craft_ok':'true'}])
def test_dashboard_unknown_or_failed_craft_never_reads_clean(evidence):
    gates=dict(ok=True,kelvin_ok=True,drc=0,unconnected=0,route_sanity=evidence)
    verdict,why=dashboard._verdict(gates,dict(ok=False))
    assert verdict=='UNKNOWN' and why==['route-craft-unverified']
    gates['unconnected']=1
    verdict,why=dashboard._verdict(gates,dict(ok=False))
    assert verdict=='FAILED' and 'unconnected' in why and 'route-craft-unverified' in why


def test_dashboard_explicit_clean_and_explicit_defect_remain_distinct():
    gates=dict(ok=True,kelvin_ok=True,drc=0,unconnected=0,route_sanity={'craft_ok':True,
        'craft_policy_identity':dashboard._current_craft_policy_identity()})
    assert dashboard._verdict(gates,dict(ok=False))==('CLEAN',[])
    gates['route_sanity']={'craft_ok':False}
    assert dashboard._verdict(gates,dict(ok=False))==('FAILED',['route-craft'])


@pytest.mark.parametrize('introduced',[
    dict(type='reverse_diagonal_jog',net='/renamed',layer='In2.Cu',track_uuids=['new'],at_mm=[1,2]),
    dict(type='acute_branch_junction',net='/other',layer='B.Cu',track_uuids=['new','retained'],at_mm=[3,4])])
def test_retaining_import_cannot_trade_inherited_for_new_craft(introduced):
    old=inventory([dict(type='acute_backtrack',net='/old',track_uuids=['old'])])
    new=inventory([introduced]);saved=copy.deepcopy((old,new));report={}
    with pytest.raises(ValueError,match='introduced_saved_route_craft_defects'):
        retaining.require_saved_route_craft(report,metrics(old),metrics(new))
    assert report['saved_route_craft_nonregression']['ok'] is False
    assert not report['saved_route_craft_nonregression']['inherited_craft_qualified']
    assert (old,new)==saved


@pytest.mark.parametrize('bad',[None,{}, {'error':'failed',**inventory()},
                               {'issue_count':0,'issues':[]},
                               {'issue_count':1,'issues':[],**{'non_octilinear_count':0,'non_octilinear':[]}}])
def test_retaining_import_missing_or_incomplete_evidence_is_not_positive(bad):
    with pytest.raises(ValueError):
        retaining.require_saved_route_craft({},metrics(inventory()),metrics(bad))


def test_retaining_import_same_or_removed_old_defects_are_not_qualified():
    issue=dict(type='reverse_diagonal_jog',net='/old',track_uuids=['old'])
    old=inventory([issue])
    for new in (old,inventory()):
        proof=retaining.require_saved_route_craft({},metrics(old),metrics(new))
        assert proof['ok'] is True and not proof['inherited_craft_qualified']


def test_real_retaining_worker_requires_saved_craft_before_positive_publication():
    tree=ast.parse(inspect.getsource(retaining._worker))
    checks=[node for node in ast.walk(tree) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Name) and node.func.id=='require_saved_route_craft']
    positives=[node for node in ast.walk(tree) if isinstance(node,ast.Assign)
               and isinstance(node.value,ast.Constant) and node.value.value is True
               and any(isinstance(target,ast.Subscript)
                   and isinstance(target.value,ast.Name) and target.value.id=='report'
                   and isinstance(target.slice,ast.Constant) and target.slice.value=='ok'
                   for target in node.targets)]
    assert len(checks)==1 and len(positives)==1 and checks[0].lineno<positives[0].lineno
