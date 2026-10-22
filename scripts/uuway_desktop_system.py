#!/usr/bin/python3
"""Root-only, fixed-path greetd/PAM changes; no password collection or storage."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import stat
import subprocess
import tempfile
import tomllib

GREETD = Path('/etc/greetd/config.toml')
LOGIN = Path('/etc/pam.d/login')


def greetd_config(text, user):
    data = tomllib.loads(text)
    initial = data.get('initial_session')
    if initial:
        if initial.get('user') != user:
            raise ValueError('Existing automatic login belongs to another user')
        if '/usr/bin/start-umbriel' not in shlex.split(initial.get('command', '')):
            raise ValueError('Existing automatic login uses another desktop')
        return text  # Preserve locale and tested GPU environment overrides.
    if 'default_session' not in data:
        raise ValueError('Missing greetd greeter configuration')
    return text.rstrip() + '\n\n[initial_session]\ncommand = "/usr/bin/start-umbriel"\nuser = ' + json.dumps(user) + '\n'


def login_pam(text):
    lines = text.splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith('#'):
            continue
        fields = line.split()
        if fields and fields[0].lstrip('-') == 'auth' and 'pam_gnome_keyring.so' in fields:
            if len(fields) < 3 or fields[1] != 'optional':
                raise ValueError('Preserve custom keyring authentication controls; configure manually')
            if any(x.startswith('only_if=') for x in fields):
                raise ValueError('Restricted keyring PAM policy requires manual review')
            if 'auto_start' not in fields:
                lines[i] = line + ' auto_start'
            found = True
    if not found:
        # Append after the existing authentication stack, without weakening it.
        lines += ['', '# UUWay: Noctalia 5.3 uses the login PAM service.',
                  'auth optional pam_gnome_keyring.so auto_start']
    return '\n'.join(lines) + '\n'


def replace(path, value):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('Refusing non-root-owned or writable system configuration')
    fd, name = tempfile.mkstemp(prefix='.uuway-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
            stream.write(value); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
        subprocess.run(['/usr/sbin/restorecon', str(path)], check=True)
    finally:
        Path(name).unlink(missing_ok=True)


def main(user, autologin=True):
    if os.geteuid() != 0:
        raise ValueError('This operation requires sudo')
    account = pwd.getpwnam(user)
    if account.pw_uid < 1000:
        raise ValueError('A regular desktop user is required')
    if autologin and subprocess.run(['systemctl', 'is-active', '--quiet', 'greetd.service']).returncode:
        raise ValueError('The default profile requires an already configured greetd display manager')
    paths = (GREETD, LOGIN) if autologin else (LOGIN,)
    for path in paths:
        if path.is_symlink():
            raise ValueError('Symlinked system configuration needs manual review')
    shadow = subprocess.run(['getent', 'shadow', user], capture_output=True, text=True, check=True).stdout.split(':')
    if len(shadow) < 2 or not shadow[1] or shadow[1].startswith(('!', '*')):
        raise ValueError('An enabled password login is required for this lock/keyring profile')
    old = {p: p.read_text() for p in paths}
    desired = {LOGIN: login_pam(old[LOGIN])}
    if autologin:
        desired[GREETD] = greetd_config(old[GREETD], user)
    # The caller saves readable originals in the user's private backup tree.
    # Apply only after parsing and validating both complete configurations.
    changed = []
    try:
        for path, content in desired.items():
            if content != old[path]:
                changed.append(path); replace(path, content)
    except Exception:
        for path in reversed(changed):
            replace(path, old[path])
        raise
    print(json.dumps({'changed': [str(p) for p in changed], 'display_manager_restarted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    parser.add_argument('--no-autologin', action='store_true')
    args = parser.parse_args()
    try:
        main(args.user, not args.no_autologin)
    except Exception as error:
        print('Session system configuration failed: ' + str(error))
        raise SystemExit(1)
