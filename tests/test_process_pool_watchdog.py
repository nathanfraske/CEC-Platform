#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from concurrent.futures import Future
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_process_pool as guard  # noqa: E402
import cec_fr  # noqa: E402


class _Process:
    def __init__(self, alive=True):
        self.alive = alive
        self.terminated = False
        self.killed = False

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        del timeout

    def terminate(self):
        self.terminated = True
        self.alive = False

    def kill(self):
        self.killed = True
        self.alive = False


class _Pool:
    def __init__(self, processes=()):
        self._processes = {index: process
                           for index, process in enumerate(processes)}
        self.shutdown_args = None

    def shutdown(self, **kwargs):
        self.shutdown_args = kwargs


class TestProcessPoolWatchdog(unittest.TestCase):
    def test_budget_accounts_for_queued_worker_waves(self):
        self.assertEqual(
            guard.pool_wall_budget(
                100, task_count=5, worker_count=2,
                cleanup_s=20, multiplier=1.5, minimum_s=1),
            470.0)

    def test_completed_future_is_yielded(self):
        future = Future()
        future.set_result("ok")
        pool = _Pool([_Process(alive=True)])
        self.assertEqual(
            list(guard.watched_as_completed(
                pool, {future: "payload"}, wall_timeout_s=1,
                poll_s=0.001)),
            [future])

    def test_dead_workers_fail_while_work_is_pending(self):
        future = Future()
        pool = _Pool([_Process(alive=False)])
        with self.assertRaisesRegex(
                guard.WorkerPoolStalled, "all route workers exited"):
            list(guard.watched_as_completed(
                pool, {future: "payload"}, wall_timeout_s=1,
                poll_s=0.001))

    def test_forced_shutdown_terminates_without_waiting_forever(self):
        process = _Process(alive=True)
        pool = _Pool([process])
        report = guard.shutdown_process_pool(
            pool, force=True, grace_s=0)
        self.assertTrue(process.terminated)
        self.assertEqual(
            pool.shutdown_args,
            {"wait": False, "cancel_futures": True})
        self.assertTrue(report["clean"])
        self.assertTrue(report["forced"])


class TestFreeroutingInterruptionCleanup(unittest.TestCase):
    def test_keyboard_interrupt_kills_native_router_tree(self):
        class FakePopen:
            def __init__(self):
                self.returncode = None
                self.calls = 0

            def communicate(self, timeout=None):
                del timeout
                self.calls += 1
                if self.calls == 1:
                    raise KeyboardInterrupt()
                return "", ""

            def poll(self):
                return self.returncode

        proc = FakePopen()

        def kill_tree(target):
            self.assertIs(target, proc)
            target.returncode = -9

        with tempfile.TemporaryDirectory() as temp, \
                mock.patch.object(cec_fr, "_rest_base", return_value=None), \
                mock.patch.object(cec_fr, "ensure_jar", return_value="fr.jar"), \
                mock.patch.object(
                    cec_fr, "_fr_command", return_value=["fake-fr"]), \
                mock.patch.object(
                    cec_fr.subprocess, "Popen", return_value=proc), \
                mock.patch.object(
                    cec_fr, "_kill_fr_tree", side_effect=kill_tree) as kill:
            with self.assertRaises(KeyboardInterrupt):
                cec_fr.run_freerouting(
                    os.path.join(temp, "board.dsn"),
                    os.path.join(temp, "board.ses"),
                    workdir=temp, timeout=60,
                    version=cec_fr.FR_VERSION)
        kill.assert_called_once_with(proc)
        self.assertEqual(proc.calls, 2)


if __name__ == "__main__":
    unittest.main()
