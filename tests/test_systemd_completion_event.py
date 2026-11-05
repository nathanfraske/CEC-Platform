from io import StringIO
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import cec_systemd_completion_event as listener
from cec_systemd_completion_event import parent_pipe_event, terminal_event


def test_running_success_is_not_completion():
    assert terminal_event(dict(active_state='active',result='success',invocation_id='a'), 'a') is None


def test_ended_invocation_generates_one_terminal_kind():
    assert terminal_event(dict(active_state='inactive',result='success',invocation_id='a'), 'a')['kind']=='service_completed'
    assert terminal_event(dict(active_state='failed',result='timeout',invocation_id='a'), 'a')['kind']=='service_failed'


def test_reused_service_name_is_not_the_old_run():
    assert terminal_event(dict(active_state='active',result='success',invocation_id='b'), 'a')['kind']=='invocation_changed'


def test_retained_completed_service_can_be_observed_after_process_exit():
    snapshot=dict(active_state='active',sub_state='exited',remain_after_exit=True,
        exit_timestamp_monotonic=123,result='success',invocation_id='a')
    assert terminal_event(snapshot,'a')['kind']=='service_completed'
    assert terminal_event(snapshot,'b')['kind']=='invocation_changed'
    assert terminal_event(dict(snapshot,result='exit-code'),'a')['kind']=='service_failed'


def test_retention_without_actual_exit_cannot_complete_a_live_run():
    snapshot=dict(active_state='active',sub_state='exited',remain_after_exit=True,
        exit_timestamp_monotonic=123,result='success',invocation_id='a')
    assert terminal_event(dict(snapshot,exit_timestamp_monotonic=0),'a') is None
    assert terminal_event(dict(snapshot,sub_state='running'),'a') is None
    assert terminal_event(dict(snapshot,remain_after_exit=False),'a') is None


def test_owned_listener_stops_on_parent_eof_hangup_or_error():
    for stream, condition in [(StringIO(''), 1), (StringIO('x'), 2), (StringIO('x'), 4)]:
        loop = Mock()
        assert not parent_pipe_event(stream, condition, loop, hup_mask=2, error_mask=4)
        loop.quit.assert_called_once_with()


def test_owned_listener_does_not_mistake_data_for_parent_death():
    loop = Mock()
    assert parent_pipe_event(StringIO('x'), 1, loop, hup_mask=2, error_mask=4)
    loop.quit.assert_not_called()


def test_failed_state_cannot_complete_from_stale_success_result():
    snapshot = dict(active_state='failed', result='success', invocation_id='a')
    assert terminal_event(snapshot, 'a')['kind'] == 'service_failed'


def test_missing_invocation_cannot_be_labeled_completed():
    snapshot = dict(active_state='inactive', result='success', invocation_id='')
    assert terminal_event(snapshot, 'a')['kind'] == 'invocation_changed'


def _unit(invocation, active='active', sub='running'):
    return {'ActiveState': active, 'SubState': sub,
            'InvocationID': bytes.fromhex(invocation)}


def _run_fake_bus_main(monkeypatch, capsys, unit_rows, service_rows):
    """Exercise actual main() without connecting to, or changing, any bus."""
    unit_rows, service_rows = list(unit_rows), list(service_rows)
    calls = []
    def get_all(interface):
        calls.append(interface)
        rows = unit_rows if interface.endswith('.Unit') else service_rows
        return rows.pop(0) if len(rows) > 1 else rows[0]

    manager = SimpleNamespace(Subscribe=Mock(), Unsubscribe=Mock(),
                              GetUnit=Mock(return_value='/test/unit'))
    properties = SimpleNamespace(GetAll=get_all)
    bus = SimpleNamespace(get_object=lambda _name, path: path,
                          add_signal_receiver=Mock())
    dbus = ModuleType('dbus')
    dbus.SessionBus = lambda: bus
    dbus.Interface = lambda _obj, interface: (
        manager if interface.endswith('.Manager') else properties)
    dbus.DBusException = type('DBusException', (Exception,), {})
    glib_main = ModuleType('dbus.mainloop.glib')
    glib_main.DBusGMainLoop = lambda **_kwargs: None
    loop = SimpleNamespace(quit=Mock(), run=Mock(
        side_effect=AssertionError('terminal inspection must not wait for signals')))
    repository = ModuleType('gi.repository')
    repository.GLib = SimpleNamespace(MainLoop=lambda: loop)
    for name, module in {'dbus': dbus, 'dbus.mainloop': ModuleType('dbus.mainloop'),
            'dbus.mainloop.glib': glib_main, 'gi': ModuleType('gi'),
            'gi.repository': repository}.items():
        monkeypatch.setitem(sys.modules, name, module)
    listener.main(['--unit', 'cec-test.service', '--invocation', 'a' * 32])
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 1
    assert rows[0]['unit'] == 'cec-test.service'
    assert rows[0]['expected_invocation'] == 'a' * 32
    manager.Subscribe.assert_called_once_with()
    manager.Unsubscribe.assert_called_once_with()
    return rows[0], calls


def test_main_rejects_restart_between_unit_and_service_reads(monkeypatch, capsys):
    first = _unit('a' * 32, 'failed', 'failed')
    replacement = _unit('b' * 32)
    event, calls = _run_fake_bus_main(monkeypatch, capsys,
        [first, replacement, replacement, replacement],
        [{'Result': 'success'}, {'Result': 'success'}])
    assert event['kind'] == 'initial_invocation_unavailable'
    assert event['invocation_id'] == 'b' * 32
    assert calls.count('org.freedesktop.systemd1.Unit') == 4
    assert calls.count('org.freedesktop.systemd1.Service') == 2


def test_main_retries_same_invocation_state_transition(monkeypatch, capsys):
    running = _unit('a' * 32)
    failed = _unit('a' * 32, 'failed', 'failed')
    event, calls = _run_fake_bus_main(monkeypatch, capsys,
        [running, failed, failed, failed],
        [{'Result': 'success'}, {'Result': 'exit-code', 'ExecMainStatus': 17}])
    assert event['kind'] == 'service_failed'
    assert event['active_state'] == 'failed'
    assert event['result'] == 'exit-code'
    assert event['exit_status'] == 17
    assert calls.count('org.freedesktop.systemd1.Service') == 2


def test_main_unstable_snapshot_is_bounded_and_review_required(monkeypatch, capsys):
    first, second = _unit('a' * 32), _unit('b' * 32)
    event, calls = _run_fake_bus_main(monkeypatch, capsys,
        [first, second] * 3, [{'Result': 'success'}] * 3)
    assert event['kind'] == 'unit_snapshot_unstable'
    assert event['requires_result_review'] is True
    assert event['attempts'] == 3
    assert 'result' not in event  # No mixed, unbound service result is published.
    assert calls.count('org.freedesktop.systemd1.Unit') == 6
    assert calls.count('org.freedesktop.systemd1.Service') == 3


def test_main_failed_state_overrides_stale_success_result(monkeypatch, capsys):
    event, _calls = _run_fake_bus_main(monkeypatch, capsys,
        [_unit('a' * 32, 'failed', 'failed')], [{'Result': 'success'}])
    assert event['kind'] == 'service_failed'
