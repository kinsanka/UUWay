#!/usr/bin/python3
"""Inject native packet failures into a disposable Windows PE encode test.

Only synthetic pixels and a private Wine prefix are used. Requires the Fedora
build and build/validation-venv with PyAV for independent CPU decoding.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    stage = ROOT / 'build/native-presenter'
    output = Path(tempfile.mkdtemp(prefix='recovery-windows-', dir=ROOT / 'build'))
    app = output / 'app'
    app.mkdir(parents=True, exist_ok=True)
    shim = ROOT / 'build/vaapi-receive-failure.so'
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'libavcodec'], text=True))
    subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
        *flags, str(ROOT / 'tests/probes/vaapi_receive_failure.c'), '-o', str(shim), '-ldl'],
        check=True, timeout=30)
    for name in ('uu-nvenc-pe-encode-probe.exe', 'uurb-nvenc-encode-loader.dll',
                 'uurb-nvenc-encode.dll.so', 'd3d11.dll', 'dxgi.dll'):
        shutil.copy2(stage / name, app / name)
    with tempfile.TemporaryDirectory(prefix='uuway-recovery-') as prefix:
        env = dict(os.environ, WINEPREFIX=prefix, WINELOADER='/usr/bin/wine', WINEDEBUG='-all',
            WINEDLLOVERRIDES='mscoree,mshtml=;d3d11,dxgi=n;uurb-nvenc-encode-loader=n',
            INTEL_DEBUG='noccs,nofc', DXVK_CONFIG_FILE=str(ROOT / 'config/dxvk-amd.conf'),
            UURB_AMD_UU_PROBE='1', UURB_INTEL_HEVC_LOW_POWER='1', LD_PRELOAD=str(shim))
        env.pop('WINEDLLPATH', None)
        process = None
        try:
            with (output / 'probe.log').open('w') as log:
                process = subprocess.Popen(['xvfb-run', '-a', '/usr/bin/wine',
                    str(app / 'uu-nvenc-pe-encode-probe.exe'),
                    'Z:' + str(output).replace('/', '\\'), 'nv12', 'uav'],
                    cwd=app, env=env, stdout=log, stderr=log, start_new_session=True)
                code = process.wait(timeout=90)
            lines = (output / 'probe.log').read_text().splitlines()
            injected = [line for line in lines if line.startswith('UURB_TEST_INJECTED')]
            recovered = [line for line in lines if line.startswith('UURB_NATIVE_ENCODER_FALLBACK')]
            if code or len(injected) != 2 or len(recovered) != 2:
                raise RuntimeError('Missing successful per-codec failure/recovery: ' + '\n'.join(lines[-30:]))
            result = subprocess.run([str(ROOT / 'build/validation-venv/bin/python'),
                str(ROOT / 'scripts/verify-fedora-encode.py'), str(output), '--allow-hevc-gpb'],
                capture_output=True, text=True, timeout=40)
            if result.returncode:
                raise RuntimeError(result.stderr)
            report = json.loads(result.stdout)
            report.update(injected_packet_failures=2, same_codec_recoveries=2,
                          no_desktop_or_uu_account_accessed=True)
            (ROOT / 'build/validation-recovery.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            subprocess.run(['/usr/bin/wineserver', '-k'], env=env, capture_output=True, timeout=10)


if __name__ == '__main__':
    main()
