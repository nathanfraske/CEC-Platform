"""Composition capacity is explicit work scope, not an admission shortcut."""
import ast
from pathlib import Path
import pytest
import cec_finishing_phase_budget as budget


@pytest.mark.parametrize('count',range(1,9))
def test_explicit_longer_chain_is_bounded_and_keeps_every_receiving_obligation(count):
    q=budget.require_count(['typed-received-phase']*count,limit=8)
    assert q['actual_phase_count']==count and q['explicit_phase_limit']==8
    assert q['default_limit_unchanged']==4
    assert q['independent_leaf_deadlines_unchanged'] and q['whole_original_parent_receiving_required']
    assert q['no_copper_current_or_release_authority']
    if count>4:
        with pytest.raises(ValueError):budget.require_count(['phase']*count)


@pytest.mark.parametrize('limit',[True,False,0,-1,9,32,4.,float('nan'),float('inf'),'8',None])
def test_invalid_unbounded_or_implicit_work_expansion_refuses(limit):
    with pytest.raises(ValueError):budget.require_count(['phase'],limit=limit)


@pytest.mark.parametrize('phases',[None,{},'phase',iter(['phase']),[],list(range(9))])
def test_nonfinite_or_empty_or_oversized_composition_does_not_skip_receiving(phases):
    with pytest.raises(ValueError):budget.require_count(phases,limit=8)


def test_zero_geometry_change_is_explicit_and_not_a_received_construction():
    q=budget.require_count([],allow_empty=True)
    assert q['actual_phase_count']==0 and q['whole_original_parent_receiving_required']
    with pytest.raises(ValueError):budget.require_count([],allow_empty=1)


@pytest.mark.parametrize('filename',[
    'root_receive_source_bound_finishing_chain_20261016.py',
    'root_verify_typed_finishing_pair_20261016.py'])
def test_both_real_entrypoints_use_the_same_explicit_default_preserving_policy(filename):
    # Inspect real entrypoint syntax, not a copied facade. The actual native
    # multi-phase saved-source replay remains an integration-level obligation.
    root=Path(__file__).resolve().parents[1];tree=ast.parse((root/'build'/filename).read_text())
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
    assert any(isinstance(n.func,ast.Attribute) and n.func.attr=='require_count'
        and any(k.arg=='limit' and isinstance(k.value,ast.Attribute) and k.value.attr=='max_phases'
            for k in n.keywords) for n in calls)
    args=[n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='add_argument'
        and any(isinstance(a,ast.Constant) and a.value=='--max-phases' for a in n.args)]
    assert len(args)==1 and any(k.arg=='default' and isinstance(k.value,ast.Attribute)
        and k.value.attr=='DEFAULT_LIMIT' for k in args[0].keywords)
