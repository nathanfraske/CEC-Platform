"""Wait on one exact systemd invocation's D-Bus signals, without polling.

Emits one armed record and one terminal event. This controls no service and
does not judge PCB quality. Loss of a tracked unit is reported, not success.
"""
import argparse
import json
import re
import sys


def terminal_event(snapshot, expected_invocation):
    actual = snapshot.get('invocation_id')
    if actual != expected_invocation:
        return dict(kind='invocation_changed', **snapshot)
    retained_exit = (snapshot.get('active_state') == 'active'
        and snapshot.get('sub_state') == 'exited'
        and snapshot.get('remain_after_exit') is True
        and snapshot.get('exit_timestamp_monotonic', 0) > 0)
    if snapshot.get('active_state') in {'inactive', 'failed'} or retained_exit:
        return dict(kind='service_completed' if snapshot.get('result') == 'success'
                    and snapshot.get('active_state') != 'failed'
                    else 'service_failed', **snapshot)
    return None


class UnstableUnitSnapshot(RuntimeError):
    """Separate D-Bus property reads could not bind one stable invocation."""

    def __init__(self, before, after, attempts):
        super().__init__('systemd invocation/state changed during property reads')
        self.before, self.after, self.attempts = before, after, attempts


def coherent_service_snapshot(properties, *, attempts=3):
    """Never combine one invocation's Unit state with another's Service result.

    D-Bus serializes each GetAll call, not this multi-interface transaction.
    Re-read invocation and state after the service properties, with a small
    fixed retry bound for a service completing/restarting during inspection.
    """
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise ValueError('snapshot attempts must be bounded to 1..3')

    def read_unit():
        unit = properties.GetAll('org.freedesktop.systemd1.Unit')
        return dict(active_state=str(unit['ActiveState']),
                    sub_state=str(unit['SubState']),
                    invocation_id=bytes(unit.get('InvocationID', ())).hex())

    for _attempt in range(attempts):
        before = read_unit()
        service = properties.GetAll('org.freedesktop.systemd1.Service')
        after = read_unit()
        if before == after:
            return dict(after,
                result=str(service.get('Result', 'unknown')),
                remain_after_exit=bool(service.get('RemainAfterExit', False)),
                exit_timestamp_monotonic=int(service.get('ExecMainExitTimestampMonotonic', 0)),
                exit_code=int(service.get('ExecMainCode', 0)),
                exit_status=int(service.get('ExecMainStatus', 0)))
    raise UnstableUnitSnapshot(before, after, attempts)


def parent_pipe_event(stream, condition, loop, *, hup_mask, error_mask):
    """Exit when the owning desktop bridge closes its pipe, not on a timer."""
    if condition & (hup_mask | error_mask) or not stream.read(1):
        loop.quit()
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit', required=True)
    parser.add_argument('--invocation', required=True)
    parser.add_argument('--parent-pipe', action='store_true',
                        help='exit when the owning bridge closes stdin')
    args = parser.parse_args(argv)
    if (not re.fullmatch(r'[A-Za-z0-9_.@:-]+\.service', args.unit)
            or not re.fullmatch(r'[0-9a-f]{32}', args.invocation)):
        parser.error('an exact service name and invocation ID are required')
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    manager = dbus.Interface(bus.get_object('org.freedesktop.systemd1',
        '/org/freedesktop/systemd1'), 'org.freedesktop.systemd1.Manager')
    manager.Subscribe()
    try:
        path = str(manager.GetUnit(args.unit))
    except dbus.DBusException as exc:
        # A very short unretained transient unit can be collected before the
        # listener attaches. Report the missing evidence to the task, not an
        # unhandled traceback/silent missed wake or a fabricated success.
        print(json.dumps(dict(schema=1, unit=args.unit,
            expected_invocation=args.invocation, kind='unit_unavailable',
            error=exc.get_dbus_name(), requires_result_review=True)), flush=True)
        manager.Unsubscribe()
        return
    loop = GLib.MainLoop()
    if args.parent_pipe:
        GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR,
            lambda stream, condition: parent_pipe_event(stream, condition, loop,
                hup_mask=GLib.IO_HUP, error_mask=GLib.IO_ERR))
    finished = False
    bound = False

    def emit(event):
        nonlocal finished
        if not finished:
            finished = True
            print(json.dumps(dict(schema=1, unit=args.unit,
                expected_invocation=args.invocation, **event)), flush=True)
            loop.quit()

    def inspect():
        nonlocal bound
        if finished:
            return
        try:
            props = dbus.Interface(bus.get_object('org.freedesktop.systemd1', path),
                                   'org.freedesktop.DBus.Properties')
            snapshot = coherent_service_snapshot(props)
            if not bound:
                if snapshot['invocation_id'] != args.invocation:
                    emit(dict(kind='initial_invocation_unavailable', **snapshot))
                    return
                bound = True
            event = terminal_event(snapshot, args.invocation)
            if event:
                emit(event)
        except UnstableUnitSnapshot as exc:
            emit(dict(kind='unit_snapshot_unstable', requires_result_review=True,
                      attempts=exc.attempts, unit_before=exc.before, unit_after=exc.after))
        except dbus.DBusException as exc:
            emit(dict(kind='unit_unavailable', error=exc.get_dbus_name()))

    def changed(interface, _changes, _invalidated):
        if str(interface) in {'org.freedesktop.systemd1.Unit', 'org.freedesktop.systemd1.Service'}:
            inspect()

    def removed(name, _path):
        if str(name) == args.unit:
            emit(dict(kind='tracked_unit_removed', requires_result_review=True))

    bus.add_signal_receiver(changed, signal_name='PropertiesChanged',
        dbus_interface='org.freedesktop.DBus.Properties', path=path,
        bus_name='org.freedesktop.systemd1')
    bus.add_signal_receiver(removed, signal_name='UnitRemoved',
        dbus_interface='org.freedesktop.systemd1.Manager',
        bus_name='org.freedesktop.systemd1')
    inspect()  # Subscribe before reading, so completion cannot fall in a gap.
    if not finished:
        print(json.dumps(dict(schema=1, kind='armed', unit=args.unit,
                              expected_invocation=args.invocation)), flush=True)
        loop.run()
    manager.Unsubscribe()


if __name__ == '__main__':
    main()
