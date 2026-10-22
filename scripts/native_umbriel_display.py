#!/usr/bin/python3
"""Read-only UU display adapter for a same-user Umbriel compositor."""
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import stat

from native_niri_display import NiriDisplay


def ipc_path():
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    explicit = os.environ.get('UMBRIEL_SOCKET')
    display = os.environ.get('WAYLAND_DISPLAY')
    candidates = ([Path(explicit)] if explicit else
                  [runtime / f'umbriel-{display}.sock'] if display else
                  list(runtime.glob('umbriel-*.sock')))
    valid = []
    for path in candidates:
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid():
            valid.append(path)
    if len(valid) != 1:
        raise RuntimeError('Expected one same-user Umbriel IPC socket')
    return valid[0]


def outputs():
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(str(ipc_path()))
        client.sendall(b'{"cmd":"outputs"}\n')
        data = b''
        while b'\n' not in data:
            chunk = client.recv(16384)
            if not chunk:
                break
            data += chunk
            if len(data) > 256 * 1024:
                raise ValueError('Umbriel output catalogue exceeds bounds')
    reply = json.loads(data)
    raw = reply.get('ok')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 16:
        raise ValueError('Invalid Umbriel output catalogue')
    monitors = []
    for value in raw:
        if not value.get('enabled') or not value.get('powered'):
            continue
        name = value.get('name')
        if not isinstance(name, str) or not 0 < len(name) <= 128 or any(ord(c) < 32 for c in name):
            raise ValueError('Invalid output connector')
        modes = value.get('modes', [])
        current = [m for m in modes if m.get('current')]
        if len(current) != 1:
            raise ValueError('Expected one current Umbriel output mode')
        mode = current[0]
        width, height = mode['width'], mode['height']
        rate = mode['refresh_mhz']
        scale = value['scale']
        x, y = value['position']['x'], value['position']['y']
        if (any(type(n) is not int or not 2 <= n <= 4096 or n % 2 for n in (width, height)) or
                type(rate) is not int or not 0 <= rate <= 144000 or
                type(scale) not in (int, float) or not math.isfinite(scale) or not 0.5 <= scale <= 4 or
                any(type(n) is not int or not -32768 <= n <= 32768 for n in (x, y)) or
                value.get('transform') != 'normal'):
            raise ValueError('Unsupported Umbriel mode, rotation or layout')
        monitors.append(dict(connector=name, width=width, height=height,
            refresh=rate / 1000, scale=float(scale), x=x, y=y, primary=x == 0 and y == 0,
            mode=f'{width}x{height}@{rate}', virtual=False, friendly=name,
            modes=[dict(width=width, height=height, refresh=rate / 1000, scales=[float(scale)])]))
    if not monitors or sum(m['primary'] for m in monitors) != 1:
        raise ValueError('Umbriel requires exactly one origin output')
    monitors.sort(key=lambda m: (not m['primary'], m['y'], m['x'], m['connector']))
    for index, item in enumerate(monitors):
        item.update(index=index, gdi_name='\\\\.\\DISPLAY%d' % (index + 1),
                    device_path='\\\\?\\DISPLAY#UURB#%s#%d' % (item['connector'], index))
    return monitors


class UmbrielDisplay(NiriDisplay):
    def monitors(self):
        return outputs()

    def identity(self):
        path = ipc_path()
        return [Path('/proc/sys/kernel/random/boot_id').read_text().strip(), str(path), str(path.stat().st_ino)]

    def _reply(self):
        entries = [((m['connector'], 'Umbriel', m['friendly'], ''), [],
                    {'display-name': m['friendly']}) for m in self.monitors()]
        return self.current()['serial'], entries, [], {}


def topology():
    monitor = outputs()[0]
    if monitor['scale'] != 1.0:
        raise ValueError('UU input currently requires scale 1.0')
    return dict(generation=0, connectors=[monitor['connector']],
                layout=[dict(x=monitor['x'], y=monitor['y'], scale=1.0, transform=0, outputs=1)],
                modes=[dict(width=monitor['width'], height=monitor['height'])])


if __name__ == '__main__':
    import sys
    print(json.dumps(topology() if sys.argv[1:] == ['--topology'] else outputs()))
