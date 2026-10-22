#!/usr/bin/python3
"""Build a native Fedora RPM from the validated VA-API build, without .deb conversion."""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deb_manifest', ROOT / 'packaging/deb_manifest.py')
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)


def entries():
    result = []
    for source, dest, mode in manifest.files():
        if (source.startswith('build/backends/') or 'uuway-wine.preferences' in source or
                'lintian' in source):
            continue
        result.append((source, dest, mode))
    result.extend([
        ('build/encoder-backend', f'{manifest.LIB}/build/encoder-backend', 0o644),
        ('build/native-presenter/uu-vaapi-probe', f'{manifest.LIB}/build/native-presenter/uu-vaapi-probe', 0o755),
        ('capture/uu-umbriel-cursor-meta.so', f'{manifest.LIB}/capture/uu-umbriel-cursor-meta.so', 0o644),
        ('scripts/uuway-setup', f'{manifest.LIB}/scripts/uuway-setup', 0o755),
        ('packaging/uuway-setup.desktop', 'usr/share/applications/uuway-setup.desktop', 0o644),
        ('docs/fedora.md', 'usr/share/doc/uuway/fedora.md', 0o644),
        ('docs/desktop-defaults.md', 'usr/share/doc/uuway/desktop-defaults.md', 0o644),
        ('scripts/uuway_desktop.py', f'{manifest.LIB}/scripts/uuway_desktop.py', 0o755),
        ('scripts/uuway_desktop_system.py', f'{manifest.LIB}/scripts/uuway_desktop_system.py', 0o755),
        ('systemd/uuway-session-guard.service', f'{manifest.LIB}/systemd/uuway-session-guard.service', 0o644),
    ])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='0.0.0')
    parser.add_argument('--release', default='0.1.fedora_port')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[0-9A-Za-z_.]+', value) for value in (args.version, args.release)):
        parser.error('Invalid RPM version/release')
    if (ROOT / 'build/encoder-backend').read_text().strip() != 'amd-vaapi':
        raise SystemExit('Build the Fedora VA-API runtime first')
    top = ROOT / 'build/rpm'
    stage = top / 'payload'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for source, dest, mode in entries():
        original = ROOT / source
        if not original.is_file() or original.is_symlink():
            raise SystemExit('Missing regular build input: ' + source)
        target = stage / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        target.chmod(mode)
    for dest, link in manifest.COMMANDS.items():
        (stage / dest).parent.mkdir(parents=True, exist_ok=True)
        (stage / dest).symlink_to(link)
    for directory in ('BUILD', 'BUILDROOT', 'RPMS', 'SPECS', 'SOURCES', 'SRPMS'):
        (top / directory).mkdir(exist_ok=True)
    # Runtime ELF dependencies are found by RPM. Wine is constrained explicitly
    # because an otherwise installable newer Wine may change the bridge ABI.
    content = f'''Name: uuway
Version: {args.version}
Release: {args.release}%{{?dist}}
Summary: UU Remote compatibility runtime for Fedora Wayland desktops
License: AGPL-3.0-or-later AND MIT AND Zlib
URL: https://github.com/kinsanka/UUWay
ExclusiveArch: x86_64
Requires: python3 python3-gobject python3-dbus gtk3 at-spi2-core
Requires: xorg-x11-server-Xvfb xclip wl-clipboard procps-ng systemd udev xdg-desktop-portal zenity
Requires: wine-core >= 11.0
Requires: wine-core < 11.1
Requires: gnome-keyring gnome-keyring-pam seahorse libsecret
Requires: noctalia >= 5.3.0
Recommends: fcitx5 intel-media-driver
%global debug_package %{{nil}}
%global __brp_strip %{{nil}}
%global __brp_strip_comment_note %{{nil}}
%global __brp_mangle_shebangs %{{nil}}

%description
Native Fedora build with VA-API encoding on Intel/AMD and a unified Umbriel
background supervisor. The proprietary UU Remote installer
and account are supplied separately by the user.

%prep
%build
%install
mkdir -p %{{buildroot}}
cp -a "{stage}/." %{{buildroot}}/

%post
if [ -d /run/udev ]; then
    udevadm control --reload-rules || :
    udevadm trigger --subsystem-match=misc --sysname-match=uinput --action=add || :
fi

%files
/usr/bin/uuway
/usr/bin/uuway-console
/usr/lib/uuway
/usr/lib/udev/rules.d/70-uurb-native-input.rules
/usr/share/applications/uuway.desktop
/usr/share/applications/uuway-setup.desktop
/usr/share/icons/hicolor/scalable/apps/uuway.svg
/usr/share/doc/uuway
'''
    path = top / 'SPECS/uuway.spec'
    path.write_text(content)
    subprocess.run(['rpmbuild', '-bb', '--define', f'_topdir {top}', str(path)], check=True)
    for rpm in (top / 'RPMS').rglob('*.rpm'):
        print(rpm)


if __name__ == '__main__':
    main()
