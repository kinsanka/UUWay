"""Clipboard conflicts must not tear down remote video or expose clipboard data."""
import contextlib
import importlib.util
import io
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('wayland_clipboard',
    Path(__file__).resolve().parents[1] / 'scripts/uu-wayland-clipboard.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class ClipboardConflicts(unittest.TestCase):
    def test_unavailable_native_text_does_not_make_same_text_a_new_copy(self):
        wine = Mock()
        with patch.object(bridge, 'bounded') as copy:
            previous = bridge.synchronize(wine, b'private text', False, None, None)
            bridge.synchronize(wine, previous, False, None, b'private text')
        wine.put.assert_not_called()
        copy.assert_not_called()

    def test_conflict_burst_pauses_and_resumes_without_raising_or_logging_payload(self):
        guard = bridge.TransferGuard()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertTrue(all(guard.allow(i / 10) for i in range(12)))
            self.assertFalse(guard.allow(1.2))
            self.assertFalse(guard.allow(5))
            self.assertTrue(guard.allow(11.3))
        self.assertEqual(output.getvalue().count('pausing sync'), 1)

    def test_busy_clipboard_keeps_its_worker_alive_until_normal_stop(self):
        stop = threading.Event()
        wine = Mock()
        wine.get.return_value = (True, b'remote fixture')
        wine.put.return_value = True
        count = 0
        def native():
            nonlocal count
            count += 1
            if count > 35:
                stop.set()
            return ('private fixture ' + str(count % 2)).encode()
        with patch.object(bridge, 'Wine', return_value=wine), \
                patch.object(bridge, 'native', side_effect=native), \
                patch.object(bridge.time, 'monotonic', return_value=1), \
                patch.object(stop, 'wait'), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            bridge.main(stop_event=stop)
        self.assertGreater(count, 35)
        self.assertLessEqual(wine.put.call_count, 12)
        wine.close.assert_called_once()
        self.assertNotIn('private fixture', output.getvalue())
        self.assertNotIn('remote fixture', output.getvalue())
