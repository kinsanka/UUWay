"""Unified worker lifecycle; no real Wine, compositor or audio device is used."""
import importlib.util
from pathlib import Path
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('unified', ROOT / 'scripts/uuway_daemon.py')
daemon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daemon)


class UnifiedWorkers(unittest.TestCase):
    def test_ready_worker_joins_on_shared_stop(self):
        stop = threading.Event()
        def work(s, ready):
            ready.set()
            s.wait()
        worker = daemon.Worker('fixture', work, stop)
        worker.start(timeout=1)
        worker.start(timeout=1)  # Readiness may be reported again after a reconnect.
        self.assertIsNone(worker.failure)
        stop.set()
        worker.thread.join(timeout=1)
        self.assertFalse(worker.thread.is_alive())

    def test_start_failure_stops_group_without_reporting_ready(self):
        stop = threading.Event()
        def fail(s, ready):
            raise ValueError('private payload must not become a failure message')
        worker = daemon.Worker('fixture', fail, stop)
        with self.assertRaises(RuntimeError):
            worker.start(timeout=1)
        worker.thread.join(timeout=1)
        self.assertTrue(stop.is_set())
        self.assertEqual(worker.failure, 'ValueError')

    def test_unexpected_exit_stops_group(self):
        stop = threading.Event()
        worker = daemon.Worker('fixture', lambda s, r: None, stop)
        with self.assertRaises(RuntimeError):
            worker.start(timeout=1)
        self.assertEqual(worker.failure, 'RuntimeError')

    def test_unready_worker_is_bounded_and_cancelled(self):
        stop = threading.Event()
        worker = daemon.Worker('fixture', lambda s, r: s.wait(), stop)
        with self.assertRaises(RuntimeError):
            worker.start(timeout=.02)
        worker.thread.join(timeout=1)
        self.assertFalse(worker.thread.is_alive())


if __name__ == '__main__':
    unittest.main()
