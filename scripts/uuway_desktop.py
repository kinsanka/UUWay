#!/usr/bin/python3
"""Fedora/Umbriel login-lock profile. Never accepts or stores a password."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / 'scripts/uuway_desktop_system.py'
PAM = Path('/etc/pam.d/login')
GREETD = Path('/etc/greetd/config.toml')


def run(argv, *, check=True, timeout=15):
    return subprocess.run([str(x) for x in argv], check=check, capture_output=True, text=True, timeout=timeout)


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError('Refusing symlinked managed file')
    fd, temp = tempfile.mkstemp(prefix='.uuway-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(content); out.flush(); os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def set_table(text, table, values):
    """Change only flat keys in one TOML table; preserve other user settings."""
    old = tomllib.loads(text)
    lines = text.splitlines(keepends=True)
    start = next((i for i, s in enumerate(lines) if s.strip() == '[' + table + ']'), None)
    encoded = ''.join(k + ' = ' + json.dumps(v, ensure_ascii=False) + '\n' for k, v in values.items())
    if start is None:
        result = text.rstrip() + '\n\n[' + table + ']\n' + encoded
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith('[')), len(lines))
        kept = [s for s in lines[start + 1:end] if not re.match(
            r'^\s*(?:' + '|'.join(re.escape(k) for k in values) + r')\s*=', s)]
        result = ''.join(lines[:start + 1]) + encoded + ''.join(kept) + ''.join(lines[end:])
    new = tomllib.loads(result)
    expected = dict(old)
    expected[table] = dict(old.get(table, {}), **values)
    if new != expected:
        raise ValueError('Unsupported TOML layout; refusing to alter unrelated settings')
    return result


def status():
    data = json.loads(run(['/usr/bin/noctalia', 'msg', 'status'], timeout=3).stdout)
    if type(data.get('locked')) is not bool:
        raise ValueError('Noctalia did not expose lock status')
    return data['locked']


def session_marker():
    path = Path(os.environ.get('UMBRIEL_SOCKET') or
                str(Path(os.environ['XDG_RUNTIME_DIR']) / ('umbriel-' + os.environ['WAYLAND_DISPLAY'] + '.sock')))
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('Expected the current user compositor socket')
    key = hashlib.sha256(f'{path}:{info.st_ino}:{info.st_mtime_ns}'.encode()).hexdigest()[:24]
    return Path(os.environ['XDG_RUNTIME_DIR']) / ('uuway-session-' + key + '.json')


def marker_phase(marker):
    if marker.is_file() and not marker.is_symlink():
        return json.loads(marker.read_text()).get('phase')
    return None


def guard():
    marker = session_marker()
    if marker_phase(marker) in ('existing-session', 'lock-confirmed'):
        return  # Do not re-lock the owner's current session on a UU restart.
    deadline = time.monotonic() + 25
    requested = False
    while time.monotonic() < deadline:
        try:
            if not requested:
                run(['/usr/bin/noctalia', 'msg', 'session', 'lock'], timeout=3)
                requested = True
            # Noctalia status.locked also includes a pending lock. Only its
            # compositor-confirmed session_locked hook may acknowledge readiness.
            if marker_phase(marker) == 'lock-confirmed':
                return
        except (subprocess.SubprocessError, ValueError, OSError):
            pass
        time.sleep(.2)
    # A new automatic-login session must not be left unlocked if its locker fails.
    run(['/usr/bin/umbriel', 'msg', 'session-quit'], check=False, timeout=3)
    raise RuntimeError('Startup lock was not confirmed; returning to the greeter')


def locked():
    """Acknowledge the compositor-confirmed session_locked hook, then return fast."""
    if not status():
        return
    private_write(session_marker(), json.dumps({'phase': 'lock-confirmed'}))
    subprocess.Popen(['/usr/bin/python3', str(Path(__file__).resolve()), 'clear-prompts'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)


def clear_prompts():
    """Cancel only keyring prompt windows, only while the lock remains active."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not status():
            return
        windows = json.loads(run(['/usr/bin/umbriel', 'windows', '--json']).stdout)
        for window in windows:
            if (window.get('app_id') == 'gcr-prompter' and
                    window.get('title') in ('Unlock Login Keyring', '解锁登录密钥环', '解锁“登录”密钥环') and
                    re.fullmatch(r'[A-Za-z0-9_-]{1,128}', str(window.get('id', '')))):
                # Recheck before each close: never cancel the owner's unlocked prompt.
                if not status():
                    return
                run(['/usr/bin/umbriel', 'msg', 'window-close:' + str(window['id'])])
        time.sleep(.5)


def install(*, autologin=True, dry_run=False):
    if os.geteuid() == 0:
        raise ValueError('Run as the desktop user; sudo is used only for system files')
    if 'umbriel' not in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':'):
        raise ValueError('This profile requires Umbriel')
    for package in ('gnome-keyring', 'gnome-keyring-pam', 'seahorse', 'noctalia'):
        run(['rpm', '-q', package])
    from uuway_desktop_system import greetd_config, login_pam
    user = pwd.getpwuid(os.getuid()).pw_name
    system_needed = login_pam(PAM.read_text()) != PAM.read_text()
    if autologin:
        run(['systemctl', 'is-active', '--quiet', 'greetd.service'])
        system_needed |= greetd_config(GREETD.read_text(), user) != GREETD.read_text()
    login_pam(PAM.read_text())
    marker = session_marker()
    h = Path.home()
    settings = h / '.local/state/noctalia/settings.toml'
    original = settings.read_text() if settings.exists() else ''
    effective = {}
    for p in sorted((h / '.config/noctalia').glob('*.toml')):
        effective.update(tomllib.loads(p.read_text()).get('hooks', {}))
    effective.update(tomllib.loads(original).get('hooks', {}))
    hook = '/usr/bin/python3 /usr/lib/uuway/scripts/uuway_desktop.py locked'
    old_hook = effective.get('session_locked', [])
    commands = [old_hook] if isinstance(old_hook, str) else list(old_hook)
    commands = [x for x in commands if x != hook]
    commands.insert(0, hook)
    desired = set_table(original, 'lockscreen', {'enabled': True, 'grace_period_seconds': 0,
                                                'allow_empty_password': False, 'fingerprint': False})
    desired = set_table(desired, 'hooks', {'session_locked': commands})
    units = h / '.config/systemd/user'
    guard_unit = units / 'uuway-session-guard.service'
    bridge_drop = units / 'uu-native-bridge.service.d/90-login-lock.conf'
    profile = h / '.config/uurb/desktop-defaults.json'
    noctalia_unit = units / 'noctalia.service'
    create_noctalia = run(['systemctl', '--user', 'cat', 'noctalia.service'], check=False).returncode != 0
    desired_files = {
        settings: desired,
        guard_unit: (ROOT / 'systemd/uuway-session-guard.service').read_text(),
        bridge_drop: '[Unit]\nRequires=uuway-session-guard.service\nAfter=uuway-session-guard.service\n',
        profile: json.dumps({'schema': 1, 'autologin': autologin, 'locker': 'noctalia', 'keyring': 'gnome-keyring'}),
    }
    if create_noctalia:
        desired_files[noctalia_unit] = '''[Unit]
Description=Noctalia desktop shell
PartOf=graphical-session.target
After=graphical-session.target
[Service]
Type=simple
ExecStart=/usr/bin/noctalia
Restart=on-failure
[Install]
WantedBy=graphical-session.target
'''
    print('Default profile: greetd auto-login -> password lock -> UU background; GNOME Keyring via PAM.')
    if dry_run:
        print('Dry run: no files, services, login settings or lock state changed.')
        return
    backup_parent = h / 'backup/UUWay/桌面默认配置'
    backup_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=time.strftime('backup-%Y%m%d-%H%M%S-'), dir=backup_parent))
    manifest = []
    for p in list(desired_files) + [PAM] + ([GREETD] if autologin else []):
        if p.is_symlink():
            raise ValueError('Symlinked configuration requires manual review')
        existed = p.is_file()
        manifest.append({'path': str(p), 'existed': existed})
        if existed:
            dest = backup / str(p).lstrip('/')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
    private_write(backup / 'files.json', json.dumps(manifest, indent=2))
    try:
        for p, content in desired_files.items():
            private_write(p, content)
        run(['/usr/bin/noctalia', 'config', 'validate'])
        # The owner is already using this session. The login lock applies next session.
        private_write(marker, json.dumps({'phase': 'existing-session'}))
        args = ['sudo', '/usr/bin/python3', SYSTEM, '--user', user]
        if not autologin:
            args.append('--no-autologin')
        # Inherit the terminal for sudo; never intercept the password.
        if system_needed:
            subprocess.run([str(x) for x in args], check=True)
    except Exception:
        for p in desired_files:
            saved = backup / str(p).lstrip('/')
            if saved.exists():
                shutil.copy2(saved, p)
            else:
                p.unlink(missing_ok=True)
        raise
    run(['systemctl', '--user', 'daemon-reload'])
    run(['systemctl', '--user', 'enable', 'uuway-session-guard.service'])
    print('Configured for the next graphical login; current desktop was not locked or restarted.')
    print('Backup: ' + str(backup))


def hide_tray():
    runtime = json.loads((Path.home() / '.config/uurb/native-runtime.json').read_text())
    helper = Path(runtime['bundle']) / 'runtime/uu-clipboard-pipe.exe'
    env = dict(os.environ, WINEPREFIX=runtime['prefix'], WINEDEBUG='-all',
               WINEDLLOVERRIDES='winex11.drv=;winewayland.drv=')
    env.pop('DISPLAY', None); env.pop('WAYLAND_DISPLAY', None)
    subprocess.run(['/usr/bin/wine', str(helper), '--hide-tray-once'], env=env, check=True, timeout=10)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'guard', 'locked', 'clear-prompts', 'hide-tray'])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-autologin', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'install':
            install(autologin=not args.no_autologin, dry_run=args.dry_run)
        else:
            {'guard': guard, 'locked': locked, 'clear-prompts': clear_prompts, 'hide-tray': hide_tray}[args.action]()
    except Exception as error:
        print('UUWay desktop profile failed: ' + str(error))
        raise SystemExit(1)
