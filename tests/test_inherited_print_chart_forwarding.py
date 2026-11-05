"""CLI composition must not discard a positively declared Source chart.

Public native chart identity/association rejection is separately exercised
by test_received_chart_print_context. These regressions pin the missing
wrapper-to-public-API argument handoff that caused the real continuation.
"""
import ast
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]


def tree(name):return ast.parse((ROOT/'build'/name).read_text())


def test_uniform_print_cli_exposes_finite_source_chart_identifiers():
    t=tree('root_construct_uniform_print_20261023.py')
    arguments=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and n.func.attr=='add_argument'and n.args and isinstance(n.args[0],ast.Constant)
        and n.args[0].value=='--source-chart-group-uuid']
    assert len(arguments)==1
    kws={k.arg:ast.literal_eval(k.value)for k in arguments[0].keywords}
    assert kws==dict(action='append',default=[])


def test_public_print_plan_receives_the_exact_cli_source_chart_scope():
    t=tree('root_construct_uniform_print_20261023.py')
    calls=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and isinstance(n.func.value,ast.Name)and n.func.value.id=='op'and n.func.attr=='plan']
    assert len(calls)==1
    value=next(k.value for k in calls[0].keywords if k.arg=='source_chart_group_uuids')
    assert isinstance(value,ast.Attribute)and isinstance(value.value,ast.Name)
    assert (value.value.id,value.attr)==('a','source_chart_group_uuid')


def test_inherited_chart_scope_comes_from_hash_bound_prior_proposals_not_a_new_allowlist():
    t=tree('root_construct_inherited_print_20261024.py')
    updates=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and isinstance(n.func.value,ast.Name)and n.func.value.id=='charts'and n.func.attr=='update']
    assert len(updates)==1
    arg=updates[0].args[0]
    assert isinstance(arg,ast.Call)and isinstance(arg.func,ast.Attribute)and arg.func.attr=='get'
    assert isinstance(arg.func.value,ast.Name)and arg.func.value.id=='proposal'
    assert ast.literal_eval(arg.args[0])=='source_chart_group_uuids'
    forwards=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and isinstance(n.func.value,ast.Name)and n.func.value.id=='command'and n.func.attr=='extend'
        and n.args and isinstance(n.args[0],ast.List)and n.args[0].elts
        and isinstance(n.args[0].elts[0],ast.Constant)and n.args[0].elts[0].value=='--source-chart-group-uuid']
    assert len(forwards)==1 and ast.unparse(forwards[0].args[0])=="['--source-chart-group-uuid', uid]"
