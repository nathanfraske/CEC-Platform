"""Incremental forward domains match the old prefix-rescan semantics."""
import copy
import random

import pytest
import cec_joint_connection_search as joint


def reference(domains,conflicts,validate):
    ordered={k:sorted(v,key=lambda q:(q['cost'],q['id']))for k,v in domains.items()}
    selected={};visits=0
    def visit():
        nonlocal visits
        if len(selected)==len(ordered):return dict(selected)if validate(selected)else None
        remaining=[]
        for key,choices in sorted(ordered.items()):
            if key in selected:continue
            available=[]
            for candidate in choices:
                clear=True
                for other,prefix in sorted(selected.items()):
                    visits+=1
                    if conflicts(candidate,prefix):clear=False;break
                if clear:available.append(candidate)
            if not available:return None
            remaining.append((len(available),key,available))
        _,key,choices=min(remaining,key=lambda q:(q[0],q[1]))
        for choice in choices:
            selected[key]=choice;answer=visit();del selected[key]
            if answer is not None:return answer
        return None
    answer=visit();return answer,visits


@pytest.mark.parametrize('seed',range(80))
def test_forward_domains_preserve_exact_deterministic_first_accepted_solution(seed):
    rng=random.Random(seed)
    domains={str(i):[dict(id=str(j),cost=float(j),cells=rng.sample(range(15),rng.randrange(4)))
        for j in range(rng.randrange(1,4))]for i in range(rng.randrange(2,7))}
    before=copy.deepcopy(domains)
    conflict=lambda a,b:bool(set(a['cells'])&set(b['cells']))
    validate=lambda selection:sum(int(q['id'])for q in selection.values())%3==seed%3
    expected,_=reference(domains,conflict,validate)
    actual=joint.solve(domains,conflicts=conflict,validate_selection=validate)
    assert actual['complete']==(expected is not None)
    assert actual['selected']==(expected or {})
    assert domains==before and actual['input_unchanged']
    assert actual['incremental_forward_domains']and not actual['routing_admitted']
    assert not actual['release_authority']and not actual['no_path_proof']


def test_wide_compatible_prefix_does_not_repeat_old_constraint_scans():
    domains={str(i):[dict(id=str(j),cost=float(j))for j in range(48)]for i in range(20)}
    expected,old_visits=reference(domains,lambda a,b:False,lambda selected:True)
    actual=joint.solve(domains,conflicts=lambda a,b:False)
    assert actual['complete']and actual['selected']==expected
    assert actual['states']==21
    assert actual['compatibility_visits']==48*20*19//2
    assert actual['compatibility_visits']*6<old_visits


def test_child_domain_failure_does_not_prune_alternative_sibling_branch():
    domains={'a':[dict(id='bad',cost=0,slot=1),dict(id='good',cost=1,slot=2)],
        'b':[dict(id='one',cost=0,slot=1),dict(id='two',cost=1,slot=1)]}
    result=joint.solve(domains,conflicts=lambda a,b:a['slot']==b['slot'])
    assert result['complete']and result['selected']['a']['id']=='good'
    assert result['failure_frontier']and result['input_unchanged']
