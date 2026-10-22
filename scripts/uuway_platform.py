"""Small distro-specific decisions shared by the CLI and runtime."""
import os
from pathlib import Path
import re


def fedora():
    return Path('/etc/fedora-release').is_file()


def niri():
    return 'niri' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':')


def wine_bin_dir():
    return Path(os.environ.get('UUWAY_WINE_DIR') or ('/usr/bin' if fedora() else '/opt/wine-stable/bin'))


def compatible_wine(version):
    return bool(re.match(r'^wine-11\.0(?:\D|$)', version or ''))


def intel_environment(environment):
    """Scope the tested ANV fast-clear workaround to this program's processes."""
    if fedora():
        for vendor in Path('/sys/class/drm').glob('renderD*/device/vendor'):
            try:
                if vendor.read_text().strip() == '0x8086':
                    environment.setdefault('INTEL_DEBUG', 'noccs,nofc')
                    break
            except OSError:
                continue
    return environment


def umbriel():
    return 'umbriel' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':')
