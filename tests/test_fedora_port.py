"""Fedora/niri compatibility contracts; run without opening a portal dialog."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


niri = load('native_niri_display')
platform = load('uuway_platform')


def output(width=1920, scale=1.0):
    return dict(name='Virtual-1', modes=[dict(width=width, height=1080, refresh_rate=60000)],
                current_mode=0, logical=dict(x=0, y=0, scale=scale, transform='Normal'))


class FedoraPortTests(unittest.TestCase):
    def test_exact_wine_protocol_series(self):
        for version in ('wine-11.0', 'wine-11.0 (Staging)', 'wine-11.0.1'):
            self.assertTrue(platform.compatible_wine(version))
        for version in ('wine-11.01', 'wine-11.1', 'wine-12.0', None):
            self.assertFalse(platform.compatible_wine(version))

    def test_fedora_uses_native_wine_without_ubuntu_paths(self):
        with patch.object(platform, 'fedora', return_value=True), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(str(platform.wine_bin_dir()), '/usr/bin')

    def test_niri_catalogue_omits_hardware_serials_and_uses_actual_mode(self):
        raw = output()
        raw['serial'] = 'do-not-export'
        monitors = niri.decode_outputs({'Virtual-1': raw})
        self.assertEqual(monitors[0]['gdi_name'], r'\\.\DISPLAY1')
        self.assertEqual(monitors[0]['width'], 1920)
        self.assertEqual(monitors[0]['modes'][0]['refresh'], 60)
        self.assertNotIn('serial', monitors[0])

    def test_origin_order_is_stable(self):
        other = output()
        other['logical']['x'] = 1920
        decoded = niri.decode_outputs({'DP-2': other, 'Virtual-1': output()})
        self.assertEqual([m['connector'] for m in decoded], ['Virtual-1', 'DP-2'])

    def test_unsupported_modes_and_ambiguous_layouts_fail(self):
        for raw in ({'Virtual-1': output(width=8192)}, {'A': output(), 'B': output()}):
            with self.assertRaises(ValueError):
                niri.decode_outputs(raw)

    def test_read_only_backend_refuses_mode_writes(self):
        backend = object.__new__(niri.NiriDisplay)
        state = dict(mode='1920x1080@60000', scale=1.0)
        with patch.object(backend, 'current', return_value=state):
            backend.configure(state, state, True)
            with self.assertRaises(ValueError):
                backend.configure(state, dict(mode='1280x720@60000', scale=1.0), False)

    def test_real_vaapi_vendor_filter_accepts_intel_and_amd_only(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'vendor.c'
            binary = Path(directory) / 'vendor'
            source.write_text('#include "native_vaapi_vendor.h"\nint main(void) { return '
                              '!uurb_vaapi_vendor(0x8086) || !uurb_vaapi_vendor(0x1002) || '
                              'uurb_vaapi_vendor(0x10de) || uurb_vaapi_vendor(0x1af4); }\n')
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'src'),
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_intel_aq_grids_respect_the_driver_region_limit(self):
        source = r'''
#include "native_spatial_aq.h"
#include <assert.h>
int main(void) {
    unsigned char y[256 * 128]; int delta[32];
    for (unsigned row=0; row<128; ++row) for (unsigned col=0; col<256; ++col)
        y[row*256+col] = col<128 ? 128 : ((row/4+col/4)&1)*255;
    for (unsigned rows=2; rows<=4; rows*=2) {
        for (unsigned i=0; i<32; ++i) delta[i]=12345;
        uurb_spatial_aq_grid(y,256,256,128,15,4,rows,delta);
        assert(delta[0]<0 && delta[3]>0);
        for (unsigned i=0; i<4*rows; ++i) assert(delta[i]>=-5 && delta[i]<=5);
        for (unsigned i=4*rows; i<32; ++i) assert(delta[i]==12345);
    }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'aq'
            subprocess.run(['cc', '-x', 'c', '-', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'src'),
                            '-o', str(binary)], input=source, text=True, check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
