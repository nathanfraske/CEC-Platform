"""Execute the production oracle's actual refused-pair branch in isolation."""
import ast
import copy
import inspect
import os
import time
from unittest import mock

import pytest
import cec_pair_fallback as fallback
import cec_synth_pipeline as synth


def exercise(report=None, error=None, complete_failure=False):
    function=ast.parse(inspect.getsource(synth.route_oracle_grade)).body[0]
    branches=[node for node in ast.walk(function) if isinstance(node,ast.If)
              and isinstance(node.test,ast.Name) and node.test.id=='_refused'
              and any(isinstance(child,ast.Attribute) and child.attr=='route_atomic_pairs'
                      for child in ast.walk(node))]
    assert len(branches)==1
    # Earlier stages can have used these local variable names. A failing
    # fallback must not accidentally publish that unrelated stage's evidence.
    initial=ast.parse('prec3="old-stage.kicad_pcb"\n_staged={"stale":True}\n'
        'pair_return={"stale":True}\npair_gate={"stale":True}\n'
        'pair_fallback={"stale":True}\n_protect={"KEEP"}').body
    if complete_failure:
        initial+=ast.parse('label="isolated-failure-handoff"\nstage_trace=[]\n'
                          'route_requested=True\ncheckpoint=None').body
        initial += [copy.deepcopy(node) for node in function.body
                    if isinstance(node,ast.FunctionDef) and node.name in ('_trace','_fail')]
    module=ast.Module(body=[ast.FunctionDef(name='run',args=ast.arguments(
        posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),
        body=initial+[copy.deepcopy(branches[0])],decorator_list=[])],type_ignores=[])
    ast.fix_missing_locations(module)
    refusals=[dict(name='PAIR',p='/P',n='/N',refs=['ENDPOINT'])]
    scope=dict(os=os,time=time,_refused=refusals,work_dir='/scratch',prec='/source.kicad_pcb',
        _protect={'KEEP'},passes=16,opt=30,seed=0,fr_timeout=90,verbose=False,hints=[],
        _skip_taps=True,t0=time.monotonic(),prec_report={},
        _sanitize_failure_artifact=lambda artifact,work,stage:(None,dict(skipped=True)),
        _oracle_fail_dict=synth._oracle_fail_dict,
        _fail=lambda stage,error,**kwargs:dict(stage=stage,error=error,**kwargs))
    exec(compile(module,'<actual-route-oracle-pair-branch>','exec'),scope)
    with mock.patch.object(fallback,'route_atomic_pairs',return_value=report,side_effect=error):
        result=scope['run']()
    return result,scope['prec_report'],refusals


def test_failed_wrapper_receipt_reaches_actual_oracle_failure_stack():
    receipt=dict(schema=1,ok=False,board=None,error='bounded fallback refused',
        attempts=[dict(accepted=False,error='parent still open',staged=dict(tiers=[dict(
            reason='tier_pair_physics_refused',pair_physics=dict(ok=False,pairs=[dict(
                p='/P',n='/N',violations=['unmatched transitions','uncoupled'])]))]))])
    original=copy.deepcopy(receipt)
    result,precision,refusals=exercise(receipt)
    assert result['stage']=='critical_pair_fallback'
    assert result['evidence']['pair_fallback']==receipt
    assert result['evidence']['precision_refusals']==refusals
    assert precision['refused_pair_attempts']==receipt['attempts']
    assert result['artifact']=='/scratch/precision-tiered.kicad_pcb'
    for key in ('staged','pair_return','pair_quality'):
        assert result['evidence'][key] is None
    assert receipt==original


def test_exception_before_wrapper_result_cannot_reuse_previous_stage_evidence():
    result,precision,refusals=exercise(error=RuntimeError('backend setup failure'))
    assert 'backend setup failure' in result['error']
    assert result['evidence']['pair_fallback'] is None
    assert result['evidence']['precision_refusals']==refusals
    assert 'refused_pair_attempts' not in precision
    for key in ('staged','pair_return','pair_quality'):
        assert result['evidence'][key] is None
    assert result['artifact']=='/scratch/precision-tiered.kicad_pcb'


def test_nested_receipt_survives_actual_trace_and_fail_dictionary():
    receipt=dict(ok=False,error='bounded pair refusal',attempts=[dict(accepted=False,
        staged=dict(tiers=[dict(reason='coupling',pair_physics=dict(ok=False))]))])
    result,precision,refusals=exercise(receipt,complete_failure=True)
    assert result['failure_stage']=='critical_pair_fallback'
    assert not result['gate'] and not result['routing_complete']
    assert result['routed'] is None and result['failure_artifact'] is None
    assert result['blocker_evidence']['pair_fallback']==receipt
    assert result['stage_trace'][-1]['detail']['pair_fallback']==receipt
    assert result['blockers'][0]['causal_chain'][-1]['detail']['pair_fallback']==receipt
