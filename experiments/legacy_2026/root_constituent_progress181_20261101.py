"""Scoped low-overhead progress observation, without wrapping proof engines.

Only actual entry into the finite supplied Python code objects emits an
event. Callback results are ignored; receiving results and internal budgets
are untouched. This is watchdog observability, not electrical authority.
"""
from contextlib import contextmanager
import sys


@contextmanager
def observe(functions,callback):
    if (type(functions) not in (list,tuple) or not 1<=len(functions)<=32
            or not callable(callback) or any(not hasattr(f,'__code__') for f in functions)):
        raise ValueError('finite_real_python_constituents_and_progress_callback_required')
    codes={f.__code__:f.__module__+'.'+f.__qualname__ for f in functions}
    if len(codes)!=len(functions):raise ValueError('unique_actual_constituent_code_objects_required')
    if not hasattr(sys,'monitoring'):raise ValueError('local_code_event_monitoring_unavailable')
    monitoring=sys.monitoring
    tool=next((i for i in (3,4) if monitoring.get_tool(i) is None),None)
    if tool is None:raise ValueError('no_private_constituent_monitoring_slot')
    monitoring.use_tool_id(tool,'CEC exact receiving constituent progress')
    registered=False;enabled=[]
    def started(code,offset):callback(codes[code])
    try:
        if monitoring.get_events(tool)!=monitoring.events.NO_EVENTS or any(
                monitoring.get_local_events(tool,c) for c in codes):
            raise ValueError('previous_monitoring_events_must_not_be_overwritten')
        previous=monitoring.register_callback(tool,monitoring.events.PY_START,started)
        if previous is not None:
            monitoring.register_callback(tool,monitoring.events.PY_START,previous)
            raise ValueError('previous_monitoring_callback_must_not_be_overwritten')
        registered=True
        for code in codes:
            monitoring.set_local_events(tool,code,monitoring.events.PY_START);enabled.append(code)
        yield
    finally:
        for code in enabled:monitoring.set_local_events(tool,code,monitoring.events.NO_EVENTS)
        if registered:monitoring.register_callback(tool,monitoring.events.PY_START,None)
        monitoring.free_tool_id(tool)
