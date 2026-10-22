#!/usr/bin/python3
"""niri display catalogue via its IPC; no saved compositor config is changed.

The first port deliberately exposes the active mode only. Resolution changes
and GNOME virtual monitors are refused until their rollback path is validated.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import stat
import subprocess


def ipc_path():
    explicit = os.environ.get('NIRI_SOCKET')
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    candidates = [Path(explicit)] if explicit else sorted(runtime.glob('niri*.sock'))
    valid = []
    for path in candidates:
        info = path.lstat()
        if stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid():
            valid.append(path)
    if len(valid) != 1:
        raise RuntimeError('Expected one same-user niri IPC socket')
    return valid[0]


def outputs():
    environment = dict(os.environ, NIRI_SOCKET=str(ipc_path()))
    result = subprocess.run(['niri', 'msg', '-j', 'outputs'], capture_output=True,
                            text=True, check=True, timeout=3, env=environment)
    if len(result.stdout) > 256 * 1024:
        raise ValueError('niri output catalogue exceeds bounds')
    return decode_outputs(json.loads(result.stdout))


def decode_outputs(raw):
    if not isinstance(raw, dict) or not 1 <= len(raw) <= 16:
        raise ValueError('Invalid niri output catalogue')
    monitors = []
    for name, value in raw.items():
        if not isinstance(name, str) or not 0 < len(name) <= 128 or any(ord(c) < 32 for c in name):
            raise ValueError('Invalid output connector')
        logical = value.get('logical')
        index = value.get('current_mode')
        if logical is None or index is None:
            continue
        modes = value.get('modes')
        if not isinstance(modes, list) or type(index) is not int or not 0 <= index < len(modes):
            raise ValueError('Invalid current niri mode')
        mode = modes[index]
        width, height, rate = mode['width'], mode['height'], mode['refresh_rate']
        scale, x, y = logical['scale'], logical['x'], logical['y']
        if (any(type(v) is not int or not 2 <= v <= 4096 or v % 2 for v in (width, height)) or
                type(rate) is not int or not 1000 <= rate <= 144000 or
                type(scale) not in (float, int) or not math.isfinite(scale) or not 0.5 <= scale <= 4 or
                any(type(v) is not int or not -32768 <= v <= 32768 for v in (x, y)) or
                logical.get('transform') != 'Normal'):
            raise ValueError('Unsupported niri mode, rotation or layout')
        identifier = f'{width}x{height}@{rate}'
        monitors.append(dict(connector=name, width=width, height=height,
            refresh=rate / 1000, scale=float(scale), x=x, y=y, primary=x == 0 and y == 0,
            mode=identifier, virtual=False, friendly=name,
            modes=[dict(width=width, height=height, refresh=rate / 1000, scales=[float(scale)])]))
    if not monitors or sum(item['primary'] for item in monitors) != 1:
        raise ValueError('niri requires exactly one origin output')
    monitors.sort(key=lambda m: (not m['primary'], m['y'], m['x'], m['connector']))
    for index, item in enumerate(monitors):
        item.update(index=index, gdi_name='\\\\.\\DISPLAY%d' % (index + 1),
                    device_path='\\\\?\\DISPLAY#UURB#%s#%d' % (item['connector'], index))
    return monitors


class NiriDisplay:
    def __init__(self, connector=None):
        self.connector = connector
        from gi.repository import Gio
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def identity(self):
        path = ipc_path()
        info = path.stat()
        return [Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                str(path), str(info.st_ino)]

    def monitors(self):
        return outputs()

    def _reply(self):
        # Read-only catalogue used by the disabled virtual-screen status UI.
        entries = []
        for m in self.monitors():
            spec = (m['connector'], 'niri', m['friendly'], '')
            entries.append((spec, [], {'display-name': m['friendly']}))
        return (self.current()['serial'], entries, [], {})

    def current(self):
        catalogue = self.monitors()
        selected = next((m for m in catalogue if m['connector'] == self.connector), None) if self.connector else catalogue[0]
        if selected is None:
            raise RuntimeError('Selected niri output is no longer active')
        serial = int.from_bytes(hashlib.sha256(json.dumps(catalogue, sort_keys=True).encode()).digest()[:4], 'little')
        mode = dict(selected['modes'][0], id=selected['mode'])
        return dict(serial=serial, connector=selected['connector'], mode=selected['mode'],
                    scale=selected['scale'], modes=[mode], layout_mode=2,
                    can_change_layout=False, underscanning=False, supports_underscanning=False,
                    topology=catalogue, multi_output=len(catalogue) > 1)

    def configure(self, state, target, verify_only):
        current = self.current()
        if current != state or target['mode'] != current['mode'] or target['scale'] != current['scale']:
            raise ValueError('niri port currently supports the active mode only')


def topology():
    monitor = outputs()[0]
    if monitor['scale'] != 1.0:
        raise ValueError('niri input currently requires scale 1.0')
    return dict(generation=0, connectors=[monitor['connector']],
                layout=[dict(x=0, y=0, scale=monitor['scale'], transform=0, outputs=1)],
                modes=[dict(width=monitor['width'], height=monitor['height'])])


if __name__ == '__main__':
    import sys
    print(json.dumps(topology() if sys.argv[1:] == ['--topology'] else outputs()))
