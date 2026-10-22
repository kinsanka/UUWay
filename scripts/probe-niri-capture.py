#!/usr/bin/python3
"""Validate niri's explicit monitor stream without retaining desktop pixels."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
from gi.repository import Gio, GLib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('direct_capture', ROOT / 'scripts/mutter-direct-capture.py')
direct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(direct)


def probe(connector, binary, encode_check=False, cursor_fd=None):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    session = direct.call(bus, direct.ROOT, direct.SC, 'CreateSession', GLib.Variant('(a{sv})', ({},)))[0]
    subscription = None
    try:
        stream = direct.call(bus, session, direct.SC + '.Session', 'RecordMonitor',
            GLib.Variant('(sa{sv})', (connector, {'cursor-mode': GLib.Variant('u', 2 if cursor_fd else 0)})))[0]
        nodes = []
        subscription = bus.signal_subscribe(direct.SC, direct.SC + '.Stream', 'PipeWireStreamAdded', stream,
            None, Gio.DBusSignalFlags.NONE,
            lambda connection, sender, path, interface, signal, params: nodes.append(params.unpack()[0]))
        direct.call(bus, session, direct.SC + '.Session', 'Start')
        deadline = time.monotonic() + 10
        while not nodes and time.monotonic() < deadline:
            context = GLib.MainContext.default()
            while context.pending():
                context.iteration(False)
            time.sleep(.01)
        if len(nodes) != 1:
            raise RuntimeError('No unambiguous niri monitor stream')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as remote, tempfile.TemporaryFile() as encoded:
            remote.connect(str(Path(os.environ['XDG_RUNTIME_DIR']) / 'pipewire-0'))
            mode = ['--encode-h264', str(encoded.fileno())] if encode_check else ['--vulkan-import']
            environment = dict(os.environ, UURB_CAPTURE_DURATION_SECONDS='4',
                               UURB_CAPTURE_TIMESTAMP_SOURCE='monotonic-receipt')
            inherited = (remote.fileno(), encoded.fileno())
            if cursor_fd is not None:
                environment.update(UURB_CURSOR_STATE_FD=str(cursor_fd), UURB_CURSOR_METADATA_BACKEND='mutter')
                inherited += (cursor_fd,)
            result = subprocess.run([str(binary), str(remote.fileno()), str(nodes[0]), *mode],
                pass_fds=inherited, env=environment,
                capture_output=True, text=True, timeout=20)
            print(result.stdout, end='')
            if result.returncode:
                raise RuntimeError(result.stderr[-3000:])
            cursor_diagnostics = []
            for line in result.stderr.splitlines():
                if line.startswith(('UURB_CURSOR_METADATA_REJECTED ', 'UURB_CURSOR_METADATA ')):
                    label, payload = line.split(' ', 1)
                    cursor_diagnostics.append(dict(event=label, **json.loads(payload)))
            reports = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            if len(reports) != 1 or reports[0].get('frames', 0) < 2:
                raise RuntimeError('No continuous niri monitor frames')
            if encode_check:
                encoded.seek(0)
                decoded = subprocess.run(['ffprobe', '-v', 'error', '-f', 'h264', '-count_frames',
                    '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames', '-of', 'json',
                    '/proc/self/fd/' + str(encoded.fileno())], pass_fds=(encoded.fileno(),),
                    capture_output=True, text=True, check=True, timeout=15)
                count = int(json.loads(decoded.stdout)['streams'][0]['nb_read_frames'])
                if count != reports[0]['frames']:
                    raise RuntimeError('Independent desktop decode frame count mismatch')
        report = dict(backend='niri-mutter-screencast', connector=connector, validated=True,
                      frames=reports[0]['frames'], independent_h264_decode=encode_check)
        if cursor_diagnostics:
            report['cursor_diagnostics'] = cursor_diagnostics
        if cursor_fd is not None:
            header = struct.unpack('<16I', os.pread(cursor_fd, 64, 0))
            if not header[4] or header[2] % 2:
                raise RuntimeError('No complete native cursor metadata')
            report['cursor_metadata'] = dict(active=bool(header[4]), visible=bool(header[5]), width=header[7], height=header[8])
        return report
    finally:
        direct.call(bus, session, direct.SC + '.Session', 'Stop')
        if subscription is not None:
            bus.signal_unsubscribe(subscription)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connector', required=True)
    parser.add_argument('--capture-binary', type=Path, required=True)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--encode-check', action='store_true', help='Also encode and independently decode an anonymous H.264 sample')
    parser.add_argument('--metadata-check', action='store_true', help='Validate the separate compositor cursor channel')
    args = parser.parse_args()
    if args.metadata_check:
        spec = importlib.util.spec_from_file_location('capture_broker', ROOT / 'scripts/uu-native-capture-broker.py')
        broker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(broker)
        with tempfile.TemporaryDirectory(prefix='uuway-cursor-check-') as directory:
            cursor = broker.CursorState(Path(directory) / 'cursor.state')
            cursor.reset(1)
            try:
                report = probe(args.connector, args.capture_binary, args.encode_check, cursor.fd)
            finally:
                cursor.close()
    else:
        report = probe(args.connector, args.capture_binary, args.encode_check)
    if args.state:
        args.state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(args.state, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'w') as state:
            os.fchmod(state.fileno(), 0o600)
            json.dump(report, state)
    print(json.dumps(report))
