"""Diagnostic hooks cannot modify proof results or borrow another tool slot."""
import sys
import pytest
from root_constituent_progress181_20261101 import observe


def first(x):return x+1
def second(x):return x*2
def fails():raise RuntimeError('original_failure')


def test_only_actual_selected_entries_emit_without_replacing_functions_or_results():
    seen=[];ids=list(map(id,(first,second)));profile=sys.getprofile();trace=sys.gettrace()
    with observe((first,),seen.append):
        assert first(2)==3 and second(4)==8
        assert first(10)==11
    assert len(seen)==2 and all(s.endswith('.first') for s in seen)
    assert ids==list(map(id,(first,second))) and sys.getprofile() is profile and sys.gettrace() is trace
    first(1);assert len(seen)==2
    assert all(sys.monitoring.get_tool(i) is None for i in (3,4))


def test_receiving_failure_is_not_caught_or_relabelled_and_monitoring_is_cleaned():
    seen=[]
    with pytest.raises(RuntimeError,match='original_failure'):
        with observe((fails,),seen.append):fails()
    assert len(seen)==1 and all(sys.monitoring.get_tool(i) is None for i in (3,4))


def test_callback_return_value_is_not_a_receiving_result():
    with observe((first,),lambda _:dict(ok=True)):assert first(2)==3


def test_callback_failure_cannot_become_success_and_is_cleaned():
    def error(_):raise ValueError('progress_IO_failed')
    with pytest.raises(ValueError,match='progress_IO_failed'):
        with observe((first,),error):first(1)
    assert all(sys.monitoring.get_tool(i) is None for i in (3,4))


@pytest.mark.parametrize('functions',[[],[first,first],[object()],tuple(first for _ in range(33)),None])
def test_ambiguous_or_unbounded_function_scope_refuses(functions):
    with pytest.raises(ValueError):
        with observe(functions,lambda _:None):pass


def test_another_tool_is_not_overwritten_when_both_slots_are_taken():
    for i in (3,4):sys.monitoring.use_tool_id(i,'unrelated-'+str(i))
    try:
        with pytest.raises(ValueError,match='no_private_constituent_monitoring_slot'):
            with observe((first,),lambda _:None):pass
        assert [sys.monitoring.get_tool(i) for i in (3,4)]==['unrelated-3','unrelated-4']
    finally:
        for i in (3,4):sys.monitoring.free_tool_id(i)


def test_unrelated_function_does_not_generate_global_monitoring_events():
    seen=[]
    with observe((first,),seen.append):
        assert all(sys.monitoring.get_events(i)==0 for i in (3,4))
        for i in range(10000):second(i)
    assert seen==[]
