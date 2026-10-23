#!/usr/bin/python3
"""One Umbriel supervisor for bridge, read-only display RPC and text clipboard.

Wine and the native capture/input workers remain child processes. Audio devices
and routing are never changed here. GNOME retains its independent rollback guard.
"""
import argparse
import ctypes
import importlib.util
import json
from pathlib import Path
import threading
import traceback

ROOT = Path(__file__).resolve().parents[1]


def report_failure(event, error, *, worker=None):
    """Keep crash locations useful without logging exception text or payloads."""
    detail = dict(event=event, error_type=type(error).__name__, frames=[
        dict(file=Path(frame.filename).name, line=frame.lineno, function=frame.name)
        for frame in traceback.extract_tb(error.__traceback__)
    ])
    if worker is not None:
        detail['worker'] = worker
    print(json.dumps(detail), flush=True)


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Worker:
    def __init__(self, name, callback, stop):
        self.name, self.callback, self.stop = name, callback, stop
        self.ready = threading.Event()
        self.failure = None
        self.thread = threading.Thread(target=self._run, name='uuway-' + name, daemon=True)

    def _run(self):
        try:
            self.callback(self.stop, self.ready)
            if not self.stop.is_set():
                raise RuntimeError('Background worker exited unexpectedly')
        except Exception as error:
            self.failure = type(error).__name__
            report_failure('background_worker_failed', error, worker=self.name)
            self.stop.set()
            self.ready.set()  # Wake startup; failure is checked before continuing.

    def start(self, timeout=15):
        if self.thread.ident is not None:
            if self.thread.is_alive() and self.ready.is_set() and not self.failure and not self.stop.is_set():
                return
            raise RuntimeError(self.name + ' worker cannot be reused after exit')
        self.thread.start()
        if not self.ready.wait(timeout) or self.failure or self.stop.is_set():
            self.stop.set()
            raise RuntimeError(self.name + ' worker could not become ready')


def run(config_path):
    from native_runtime_state import read_private
    from uuway_platform import umbriel
    if not umbriel():
        raise RuntimeError('The unified supervisor currently targets Umbriel only')
    config = read_private(config_path)
    if Path(config['bundle']).resolve() != ROOT:
        raise ValueError('Supervisor must run from its configured immutable bundle')
    bundle_tools = load('package-uu-native-runtime')
    bundle_tools.verify(ROOT)
    # Set a recognizable task name, without concealing or renaming child workers.
    ctypes.CDLL(None).prctl(15, b'uuway', 0, 0, 0)
    display = load('uu-native-display-service')
    clipboard = load('uu-wayland-clipboard')
    bridge = load('uu-native-service')
    stop = threading.Event()
    workers = [
        Worker('display', lambda s, r: display.run(config_path, stop_event=s, ready_event=r,
                                                  notify_systemd=False), stop),
        Worker('clipboard', lambda s, r: clipboard.main(stop_event=s, ready_event=r,
            prefix=Path(config['prefix']), helper=ROOT / 'runtime/uu-clipboard-pipe.exe'), stop),
    ]
    try:
        workers[0].start()
        # Starting Wine's message-only helper before the bridge would make the
        # owned prefix busy (and can initialize it without a graphics driver).
        bridge.run(config_path, stop_event=stop, ready_callback=workers[1].start)
        if any(worker.failure for worker in workers):
            raise RuntimeError('A unified background worker failed')
    finally:
        stop.set()
        for worker in reversed(workers):
            if worker.thread.ident is not None:
                worker.thread.join(timeout=10)
        if any(worker.thread.is_alive() for worker in workers):
            raise RuntimeError('Background worker did not stop within its deadline')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.config)
    except Exception as error:
        # Never include clipboard text, account data or private argv in the journal.
        report_failure('uuway_failed', error)
        raise SystemExit(1)
