#!/usr/bin/python3
"""Join UTF-8 text through Wine's clipboard API and Wayland data-control.

No keyboard focus, synthetic input, audio routing, clipboard files or content logs.
Initial clipboard ownership is observed without overwriting either side.
"""
import contextlib
from collections import deque
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

LIMIT = 4 * 1024 * 1024
STOP = False


class TransferGuard:
    """Back off a conflicting clipboard writer without ending the video service."""
    def __init__(self):
        self.changes = deque()
        self.paused_until = 0

    def allow(self, now):
        if now < self.paused_until:
            return False
        while self.changes and self.changes[0] < now - 10:
            self.changes.popleft()
        if len(self.changes) >= 12:
            self.changes.clear()
            self.paused_until = now + 10
            print('UU clipboard transfer burst: pausing sync for 10 seconds; no payload logged', flush=True)
            return False
        self.changes.append(now)
        return True

def bounded(command, data=None, timeout=2):
    if data is not None:
        # wl-copy forks a selection owner that inherits stdout. Capturing that
        # pipe waits for ownership to end, not for the successful write.
        result=subprocess.run(command,input=data,stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,timeout=timeout)
        return b'' if result.returncode==0 else None
    with subprocess.Popen(command, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as p:
        try:
            if data is not None:
                p.stdin.write(data)
                p.stdin.close()
            out = bytearray()
            with selectors.DefaultSelector() as sel:
                sel.register(p.stdout, selectors.EVENT_READ)
                deadline = time.monotonic() + timeout
                while sel.get_map():
                    remain = deadline - time.monotonic()
                    if remain <= 0: raise TimeoutError()
                    if not sel.select(remain): raise TimeoutError()
                    chunk = os.read(p.stdout.fileno(), min(65536, LIMIT + 1 - len(out)))
                    if not chunk: sel.unregister(p.stdout); break
                    out.extend(chunk)
                    if len(out) > LIMIT: raise ValueError('clipboard exceeds bounds')
            return bytes(out) if p.wait(timeout=max(.01, deadline-time.monotonic())) == 0 else None
        finally:
            if p.poll() is None: p.kill(); p.wait()

class Wine:
    def __init__(self, executable, prefix=None):
        env = dict(os.environ, WINEDEBUG='-all')
        if prefix is not None:
            env['WINEPREFIX'] = str(prefix)
        # This helper uses message-only Win32 windows. It must not also mirror
        # the shared Windows clipboard onto Xwayland: the parent owns the sole
        # native bridge, otherwise Wine/XWM selection notifications can feed back.
        env.pop('DISPLAY',None)
        env.pop('WAYLAND_DISPLAY',None)
        env['WINEDLLOVERRIDES']='winex11.drv=;winewayland.drv='
        self.p = subprocess.Popen(['/usr/bin/wine', str(executable)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        self.seq = -1
    def line(self):
        with selectors.DefaultSelector() as sel:
            sel.register(self.p.stdout, selectors.EVENT_READ)
            if not sel.select(3): raise TimeoutError('Wine clipboard response')
        line = self.p.stdout.readline(80)
        if not line.endswith(b'\n'): raise RuntimeError('Wine clipboard protocol')
        return line.split()
    def get(self):
        self.p.stdin.write(('G %d\n' % (self.seq & 0xffffffff)).encode()); self.p.stdin.flush()
        line = self.line()
        if not line: raise RuntimeError('Wine clipboard exited')
        if line[0] == b'U': return False, None
        if line[0] == b'E': return False, None
        if line[0] not in (b'D', b'N'): raise RuntimeError('Wine clipboard protocol')
        self.seq = int(line[1])
        if line[0] == b'N': return True, None
        n = int(line[2])
        if not 0 <= n <= LIMIT: raise ValueError('Wine text exceeds bounds')
        data = self.p.stdout.read(n)
        if len(data) != n: raise RuntimeError('short clipboard payload')
        data.decode('utf-8', errors='strict')
        return True, data
    def put(self, data):
        if len(data)>LIMIT or b'\0' in data: return False
        self.p.stdin.write(('S %d\n' % len(data)).encode()+data); self.p.stdin.flush()
        line = self.line()
        if line[0] != b'O': return False
        self.seq = int(line[1]); return True
    def close(self):
        with contextlib.suppress(Exception): self.p.stdin.write(b'Q\n'); self.p.stdin.flush()
        with contextlib.suppress(subprocess.TimeoutExpired): self.p.wait(timeout=2)
        if self.p.poll() is None: self.p.terminate(); self.p.wait(timeout=2)

def native():
    try: return bounded(['/usr/bin/wl-paste','--no-newline','--type','text'])
    except (TimeoutError, ValueError): return None

def synchronize(wine, previous, changed, remote, current):
    # A native change observed in this iteration is newer than the preceding
    # Wine sample. Equal values are already synchronized; never echo them.
    if current != previous and current is not None:
        if current != remote and not wine.put(current): return previous
        return current
    if changed and remote is not None and remote != current:
        result=bounded(['/usr/bin/wl-copy','--type','text/plain;charset=utf-8'],remote)
        if result is not None: return remote
    # A failed read or an unsupported selection is not a new text selection.
    # Retaining the last observation prevents a later successful read of the
    # same text from being echoed into Wine again.
    return previous if current is None else current

def main(*, stop_event=None, ready_event=None, prefix=None, helper=None):
    helper=helper or Path(__file__).with_name('uu-clipboard-pipe.exe')
    wine=Wine(helper, prefix=prefix)
    try:
        wine.get(); previous=native()
        print('UU bidirectional text clipboard ready',flush=True)
        if ready_event is not None:
            ready_event.set()
        transfers=TransferGuard()
        while not STOP and not (stop_event is not None and stop_event.is_set()):
            changed, remote=wine.get()
            current=native()
            would_transfer=((current!=previous and current is not None and current!=remote)
                            or (changed and remote is not None and remote!=current))
            if would_transfer and not transfers.allow(time.monotonic()):
                # Consume both observations during backoff, but write neither
                # selection. A later copy can sync after the cooldown.
                previous = previous if current is None else current
            else:
                previous=synchronize(wine,previous,changed,remote,current)
            if stop_event is None:
                time.sleep(.3)
            else:
                stop_event.wait(.3)
    finally: wine.close()

def stop(*_):
    global STOP
    STOP=True

if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    main()
