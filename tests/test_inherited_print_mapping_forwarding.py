"""Inherited print construction forwards fresh maps, never old success JSON."""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def parsed(name):return ast.parse((ROOT/'build'/name).read_text())


def test_prior_nested_mapping_is_not_dropped_like_unrecognized_closed_guides():
    t=parsed('root_construct_inherited_print_20261024.py')
    fresh=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and n.func.attr=='_fresh_nested_map']
    assert len(fresh)==1
    passed=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and n.func.attr=='extend'and n.args and isinstance(n.args[0],ast.List)
        and n.args[0].elts and isinstance(n.args[0].elts[0],ast.Constant)
        and n.args[0].elts[0].value=='--reference-mapping-declaration']
    assert len(passed)==1


def test_exact_query_mode_is_explicit_and_not_default_print_recognition():
    t=parsed('root_construct_inherited_print_20261024.py')
    flags=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and n.func.attr=='add_argument'and n.args and isinstance(n.args[0],ast.Constant)
        and n.args[0].value=='--retained-reference-association']
    assert len(flags)==1 and ast.literal_eval(flags[0].keywords[0].value)=='store_true'
    conditioned=[n for n in ast.walk(t)if isinstance(n,ast.If)
        and ast.unparse(n.test)=='a.retained_reference_association'
        and 'same_literal_map_queries'in ast.unparse(n)]
    assert len(conditioned)==1 and 'same_literal_map_queries'in ast.unparse(conditioned[0])


def test_uniform_wrapper_receives_declaration_file_not_worker_authority():
    t=parsed('root_construct_uniform_print_20261023.py')
    calls=[n for n in ast.walk(t)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)
        and isinstance(n.func.value,ast.Name)and n.func.value.id=='op'and n.func.attr=='plan']
    assert len(calls)==1
    kw=next(k for k in calls[0].keywords if k.arg=='reference_mapping_transition')
    assert ast.unparse(kw.value)=='reference_mapping'
    assert 'mapping_input'in{n.id for n in ast.walk(t)if isinstance(n,ast.Name)}
