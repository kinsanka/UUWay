#!/usr/bin/python3
"""Independently CPU-decode synthetic Windows ABI output using PyAV's full codecs.

Fedora ffmpeg-free/openh264 omits HEVC and some decoded H.264 metadata. This
development-only verifier does not replace the system's media packages.
"""
import argparse
import json
from pathlib import Path
import sys
import av

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests/probes'))
from nvenc_encode_probe import validate_packets, validate_sequence_headers


def verify(directory, allow_hevc_gpb=False, width=640, height=360, codecs=('h264', 'hevc')):
    log = (directory / 'probe.log').read_text()
    if 'ENCODE ABI checks passed;' not in log:
        raise RuntimeError('The real Windows PE probe did not pass its ABI checks')
    packets = [json.loads(line[7:]) for line in log.splitlines() if line.startswith('ENCODE {')]
    reports = []
    for codec in codecs:
        rows = validate_packets(packets, codec, total_codecs=len({row.get('codec') for row in packets}))
        path = directory / (codec + '.bin')
        data = path.read_bytes()
        if len(data) != sum(row['bytes'] for row in rows):
            raise RuntimeError('Encoded packet sizes do not match the stream')
        validate_sequence_headers((directory / (codec + '.sequence.bin')).read_bytes(),
                                  data[:rows[0]['bytes']], codec)
        count = 0
        max_color_error = 0
        with av.open(str(path), format=codec) as container:
            for index, frame in enumerate(container.decode(video=0)):
                if index >= len(rows) or (frame.width, frame.height) != (width, height):
                    raise RuntimeError('Unexpected decoded geometry/frame count')
                allowed_types = (1, 2, 3) if codec == 'hevc' and allow_hevc_gpb else (1, 2)
                if bool(frame.key_frame) != rows[index]['idr'] or int(frame.pict_type) not in allowed_types:
                    raise RuntimeError('Decoded IDR or picture type does not match the encoder')
                # The bridge explicitly encodes BT.709. PyAV's reformatter
                # otherwise defaults to a different YUV matrix for small video.
                rgb = frame.reformat(format='rgb24', src_colorspace=1, dst_colorspace=1)
                plane = rgb.planes[0]
                raw = bytes(plane)
                pixels = b''.join(raw[y * plane.line_size:y * plane.line_size + width * 3] for y in range(height))
                expected = ((index & 3) * 85, ((index >> 2) & 3) * 85, ((index >> 4) & 3) * 85)
                for x, y in ((width//8, height//8), (width*7//8, height//8), (width*5//8, height*5//8),
                             (width//8, height*7//8), (width*7//8, height*7//8)):
                    offset = (y * width + x) * 3
                    error = max(abs(a - b) for a, b in zip(pixels[offset:offset + 3], expected))
                    max_color_error = max(max_color_error, error)
                    # Lossy Intel H.264 under the probe's constrained VBV
                    # reaches 13/255 error; a 16/255 bound still rejects a
                    # stale frame (85/255 step), wrong order, or black output.
                    if error > 16:
                        raise RuntimeError(f'Frame {index} color error exceeds 16/255: {error}')
                count += 1
        if count != len(rows):
            raise RuntimeError('Incomplete CPU decode')
        reports.append(dict(codec=codec, frames=count, width=width, height=height, all_frames_pixel_checked=True,
                            idr_verified=True, timestamps_verified=True,
                            max_sample_color_error=max_color_error, allowed_color_error=16,
                            hevc_gpb_allowed=codec == 'hevc' and allow_hevc_gpb,
                            decoded_frame_order_verified=True))
    return dict(windows_pe_abi=True, independent_cpu_decode=True, decoder='PyAV',
                codecs=reports, live_uu_connection_tested=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--allow-hevc-gpb', action='store_true',
                        help='Intel HEVC uses past-reference GPB slices; still check every frame in submission order')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=360)
    parser.add_argument('--codec', choices=('all', 'h264', 'hevc'), default='all')
    args = parser.parse_args()
    if any(value < 2 or value > 4096 or value % 2 for value in (args.width, args.height)):
        parser.error('Expected even dimensions from 2 to 4096')
    codecs = ('h264', 'hevc') if args.codec == 'all' else (args.codec,)
    print(json.dumps(verify(args.directory, args.allow_hevc_gpb, args.width, args.height, codecs), indent=2))
