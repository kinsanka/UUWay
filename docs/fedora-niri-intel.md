# Fedora 44 / niri / Intel port

This is a local development port of https://github.com/kinsanka/UUWay.
The newer VA-API implementation is incorporated from the original upstream,
GaryOAO/UUWay commit `1dcdd25d10e3c0c2845bd0fd124c589120acc9c4`.
The requested fork's starting commit was `5fd52a9`.

Target: Fedora 44 x86_64, niri 26.04, Intel UHD 730 (i915), Intel media driver
26.1.5, Mesa 26.2.4, Wine 11.0. The Intel render device on the tested machine
is `/dev/dri/renderD129`; the other render node belongs to Virtio. Production
encoding selects the actual GPU by Vulkan UUID, not a fixed render-node number.

## Changes

- Native Fedora Wine paths and RPM version reporting; `.deb` OTA is blocked.
- Fedora MinGW, FFmpeg development include paths, Wine header layout, C++20
  for the newer Fcitx5 headers, and a native RPM builder.
- Intel added to the VA-API encoder, Windows D3D11 adapter and PipeWire producer.
- Spatial AQ uses the driver's supported number of regions: UHD 730 reports
  8 H.264 regions and 16 HEVC regions, instead of the AMD backend's assumed 32.
- The tested Intel ANV driver returned black D3D11 texture readbacks. The
  process-local `INTEL_DEBUG=noccs,nofc` workaround restores correct contents.
  No global driver or compositor configuration is changed.
- niri display enumeration uses its own IPC. The initial backend exposes only
  the active mode, requires normal orientation and scale 1 for input, and does
  not change resolution or create GNOME virtual displays.
- niri advertises no RemoteDesktop keyboard device. Text uses the existing
  Fcitx5 add-on and the unused GNOME text portal service is not started.
- GNOME 50's portal chooser did not appear on the tested niri session. niri's
  own Mutter ScreenCast compatibility API successfully captures the selected
  monitor. Setup validates actual Vulkan imports and saves a private
  `niri-capture.json` diagnostic record; this is not a portal restore token.
- niri 26.04 provides invalid PTS on most captured buffers. The niri producer
  explicitly uses the monotonic frame receipt time and reports this timing
  source. Other compositors retain the upstream source-PTS requirement.
  Separate cursor metadata was verified on niri, allowing the controller to
  display the pointer independently of video frame delivery.
- VA-API accepts the Windows encoder's NV12 planes directly, avoiding the
  previous NV12 -> BGRA -> NV12 round trip. BGRA retains its validated path.

The historical internal backend identifier remains `amd` / `amd-vaapi` for
bundle compatibility; it now covers the tested Intel hardware as well.

## Build

Install the dependencies on Fedora, then build as the normal user:

```sh
sudo dnf install --setopt=install_weak_deps=False wine wine-devel gcc gcc-c++ \
  mingw64-gcc mingw64-gcc-c++ meson ninja-build pkgconf-pkg-config glslang \
  libavcodec-free-devel libavutil-free-devel libswscale-free-devel libva-devel \
  vulkan-headers vulkan-loader-devel libdrm-devel pipewire-devel json-c-devel \
  libX11-devel libXfixes-devel fcitx5-devel libei-devel gstreamer1-devel \
  gstreamer1-plugins-base-devel xorg-x11-server-Xvfb xclip python3-gobject \
  python3-dbus gtk3 at-spi2-core git ripgrep rpm-build
bash scripts/build-fedora.sh
python3 -m unittest discover -s tests -p test_fedora_port.py
python3 packaging/build-rpm.py
sudo dnf install ./build/rpm/RPMS/x86_64/uuway-*.rpm
```

The RPM contains the native runtime and support files, not the proprietary UU
installer or any account information. The installer must come from the official
UU Remote website. Development RPMs are unsigned and versioned `0.0.0`.

## Validation boundaries

The native encoder probe produced 64 H.264 and 64 HEVC frames, with headers,
forced IDR, bitrate reconfiguration and handle lifecycle checks. The Vulkan
host-frame probe checked four changing images and sealed memory buffers.
The new Fedora tests and runtime packaging tests pass on the target machine.
The independent decoder checks every changing frame and requested IDR. Its
documented lossy color bound is 16/255 per channel (observed maximum 13 for
H.264 and 2 for HEVC in the BGRA test), below the 85/255 test-frame steps.

Fedora's stock ffmpeg-free lacks HEVC CPU decoding and its OpenH264 decoder
does not return the metadata expected by the upstream acceptance script.
For independent decoding without replacing system packages, the development
verifier uses PyAV in a dedicated virtual environment:

```sh
python3 -m venv build/validation-venv
build/validation-venv/bin/pip install av
build/validation-venv/bin/python scripts/verify-fedora-encode.py build/windows-intel-fixed --allow-hevc-gpb
```

One pre-existing display-confirmation test fails on the target's Btrfs layout:
the device number in `/proc/PID/maps` differs from `stat()` for the same inode.
The verification guard has been preserved. Resolution-changing operations remain
disabled in this niri port. Intel HEVC uses GPB slices with past references;
the explicit verifier option accepts these while checking all 64 decoded colors
in submission order, requested IDRs, and the original Windows ABI packet checks.
Both BGRA and NV12/UAV output pass independent decoding.

UU 4.43.0 was installed from the official download and interactive login
succeeded. The display and bridge services are enabled for the graphical
session; `uuway doctor` reports no failures or warnings. Fcitx was reloaded and
the native IME socket is available. The user confirmed a real UU connection:
the Fedora desktop is visible and mouse movement/clicking work. The broker
recorded 3,192 frames in that session with no service restarts. A separate
anonymous capture/encode/decode check passed for 70 real 1920x1080 desktop frames.
Clipboard, terminal, and Chinese text entry have not been confirmed from a
controller; these remain outside the completed acceptance checks.

## Performance revision (RPM 0.6)

Direct NV12 preserves the checked registration/device/resource/handle rules,
retains source textures until unregister/close, and copies both planes respecting
the mapped pitch. The 640x360 BGRA and NV12/UAV probes still pass all ABI and
independent decoded-pixel checks for H.264 and HEVC. A full-HD synthetic encode
comparison measured 64 frames in 1523 -> 991 ms (H.264) and 1413 -> 884 ms (HEVC).
These measure the encoder probe, not a controller's delivered frame rate.
Full-HD HEVC also passes the independent frame-color check. The extreme full-HD
flashing-color H.264 stress case has two large pixel errors on both the old and
new path; it is recorded as a pre-existing driver/rate-control limitation, not a
passing test. The cached-readback experiment did not improve performance and
was reverted. niri provided a complete visible cursor snapshot in the direct
capture diagnostic. The working compositor-embedded cursor is retained by
default while independent cursor presentation awaits a real controller check.

The first server can exit during a warm restart. Both supervisors now keep the
bootstrap and winlogon stand-in alive through a bounded 60-second startup
recovery window; the normal missing-server check remains active afterwards.
The startup recovery timing, later failure detection and zombie/other-prefix
exclusions have automated coverage.

Fedora/niri desktop mode keeps UU's UI and companion window on the current
Xwayland display. The controlled-side process exited normally during repeated
cold Xvfb starts; the visible login path remained alive. This mode uses the
desktop's Xwayland clipboard directly, so the separate-X-display clipboard
helper is not started. Advanced Windows virtual-file clipboard behavior has
not been accepted in this mode. The installed niri unit also omits the remote
display-reconfiguration option, matching its active-mode-only display catalogue.

The visible desktop mode remained alive past the previous failure interval,
with no supervisor restarts, and accepted a real 1920x1080 capture session.
The desktop launcher focuses the existing niri window while the service is
active, preserving the UI/companion lifetime rather than starting another
bootstrap owner.

Final real-controller acceptance: the user confirmed that the desktop-mode
revision connects successfully and is noticeably smoother when moving the
mouse and dragging windows. The installed RPM is 0.0.0-0.9.fedora_port.fc44;
the active video/runtime payload is unchanged from the 0.8 desktop-mode build.

## Capture/encode overlap revision (RPM 0.10)

The user subsequently reported around 30 FPS and extra latency in the browser,
despite selecting 60 FPS or above in the controller. A visible frame-clock
fixture measured 59.757 FPS from the niri DMA-BUF source (236 frames), so the
compositor stream itself is capable of 60 FPS during continuous changes.

For the host/memfd transport only, DXGI now acknowledges each source after
UpdateSubresource has copied its bytes into the local D3D11 texture. The next
capture can overlap UU's color conversion and encoding. The local texture
cannot be updated again until ReleaseFrame; each producer frame receives one
ACK. NVIDIA's shared GPU allocation retains its original ReleaseFrame ACK.

Both real COM/Unix-packet state suites pass, including held/pending close,
failed copy, invalid descriptors, ordering and cursor-only frames. A real
Intel/DXVK test immediately overwrites the producer's host memory after every
upload and checks every pixel of all 64 changing textures; all remain correct.
Reproduce that hardware check with:

```sh
cd tests
UURB_TEST_GPU=1 python3 -m unittest test_dxgi_duplication -v
```

Optional `UURB_PERF_TRACE=1` records up to 24 five-second aggregate reports per
object. `receive_then_upload` separates waiting for a source from D3D11 upload;
`readback_then_encode` separates D3D11 readback from VA-API encoding. These are
host pipeline rates and timings, not controller presentation FPS or network
latency. No pixels, window titles or account data are logged.

## Intel encoding revision (RPM 0.11)

The controller reported little improvement from 0.10. Live aggregate timings
showed that the remaining bottleneck was VA-API encoding (19–21 ms/frame),
versus about 1 ms for D3D11 readback and 1.4–1.7 ms for capture upload. Source
delivery reached about 50–52 FPS while encoding often remained around 28–38 FPS.

Intel now selects `VAEntrypointEncSliceLP` (VDEnc) when that profile supports
the negotiated YUV420 format, CBR/VBR mode and requested ROI QP deltas. Otherwise
it retains `EncSlice`. ROI geometry is queried for the selected entrypoint.
The selected GPU is still matched by Vulkan UUID. Other vendors retain their
previous defaults. Intel uses compression level 5, capped to the advertised
quality range, to favor latency. This trades some compression efficiency for
speed; the requested bitrate, resolution, GOP and color metadata are retained.
See the [FFmpeg VA-API options](https://ffmpeg.org/ffmpeg-codecs.html#VAAPI-encoders).

The target exposes 16 ROI regions and seven quality levels on both LP profiles.
Native 64-frame H.264/HEVC lifecycle, IDR, header and bitrate-change probes pass.
Real Windows PE tests with NV12/UAV and BGRA/UAV inputs pass independent CPU
decoding, including frame colors, order, timestamps and IDRs. The full 1920×1080
flashing-color test also passes both codecs (maximum sampled channel error
2/255), including the H.264 case that failed with the previous path. That probe
measured 64 frames in 899 ms (H.264) / 589 ms (HEVC); these include the probe's
texture work and are not controller FPS. A separate FFmpeg 120-frame HEVC
benchmark measured 2.877 s with defaults versus 0.419 s with LP/level 5.

## Independent pointer / recovery revision (RPM 0.12)

Real controller acceptance of 0.11 reached around 40 FPS but the user still
reported substantial delay. Live HEVC encoding averaged about 7 ms/frame,
then Intel returned VA-API error 24 and UU switched to H.264. This means the
synthetic LP tests above did not establish long-running desktop reliability.

LP send/receive failures now trigger one retry of the uncommitted frame on
the normal entrypoint with the same codec, rates, resolution and timestamp.
The AQ layout and speed range are queried again; a fresh IDR carries updated
parameter sets. A second error is still reported. A synthetic Windows PE test
injects a packet failure once in each codec after successful frames, exercises
both recoveries, and independently decodes all 64 frames per codec with correct
order, colors, requested IDRs and timestamps (H.264 max color error 13/255,
HEVC 2/255). Run `python3 tests/probes/vaapi_recovery_probe.py` to reproduce.

The target machine is configured for metadata rather than embedded cursor mode.
After a metadata pointer is established, DXGI checks it at most eight
milliseconds apart while waiting for video. A pointer-only acquisition retains
the existing texture, performs no upload and sends no producer ACK. Both COM
transport suites verify that a cursor update interrupts a one-second video
wait in under half a second without video or desktop input injection. Window
and desktop content still form a single captured image; this is not a
per-window remote application protocol. Real pointer/latency acceptance of
this revision remains separate from those checks.

The installed 0.12 service accepted a real 1920×1080 metadata-cursor session,
published changing cursor positions/shapes, and logged DXGI pointer-only frames.
The service had no restarts and `uuway doctor` reported zero failures/warnings.
The temporary performance service override was removed after sampling; the
already-running process retains bounded diagnostics until its next restart.
The user subsequently confirmed that pointer movement no longer had noticeable
delay. The reported video queue-delay value remains unavailable.

The user then confirmed that 0.12 removed perceived mouse-pointer latency,
while desktop content still lagged, especially during fast pointer movement.
The input-dispatch startup samples had a median 0.5 ms for the complete bridge
round trip (first-call setup maximum 14 ms); these are not end-to-end latency.

## Pointer/video notification comparison (RPM 0.13)

An explicit `UURB_DXGI_POINTER_ONLY=0` mode avoids returning an unchanged desktop
texture solely because the pointer moved. USER32 cursor snapshots and the full
DXGI pointer position/shape APIs on real video acquisitions remain available.
The default DXGI implementation still generates standard pointer-only events.
The Fedora/niri metadata runtime selects the opt-in mode; setting the variable
to `1` overrides it for comparison. Embedded/composited and other desktop
environments retain their existing policy.

Both real COM transport suites check that a cursor-only change does not upload
or return a video texture in this mode, respects the caller's timeout, sends no
ACK, and still supplies the latest pointer on the next real video frame. The
runtime policy tests cover platform/mode scope and explicit overrides. All
33 native-trial tests pass. Real controller comparison of this revision is
still pending; duplicated encoding is a hypothesis, not a measured conclusion.

The 0.13 live log showed `notifications=1`: UU rebuilt its server's Windows
environment, so the Unix-side setting alone did not activate this comparison.
Its client observations must not be treated as a test of notification mode 0.

## Service environment propagation (RPM 0.14)

The bootstrap carries the strict 0/1 notification policy through its existing
invocation-owned, absent-only registry environment transport. Exact-value
cleanup preserves changes made by another owner. The recovery journal stores
the original policy, including the absence of a value for old runtimes, rather
than substituting today's environment/default after a crash.

The real Wine test builds a fresh service environment block and checks the
policy, normal cleanup, preservation of another owner's changed value, startup
conflict rejection and cold recovery. Native-trial recovery tests cover absent,
0 and 1 journal values. Live activation and client latency acceptance must be
checked separately before attributing any performance difference to this mode.

The user reported that fast pointer movement still delayed desktop video and
could produce a black screen, which recovered after stopping pointer movement.
The 0.13 capture log contains repeated producer exits/recreations, but most lack
a fixed GPU-channel failure record; their cause is not yet established. The
kernel also recorded an Intel EncoderQueue hang/reset at 15:52:17 MST, before
the active 0.13 runtime started at 16:14. It cannot be attributed to that later
black-screen report. No LP encoder fallback/error was found in that runtime.
Repeated rate/VBV reconfigurations reopen the VA-API encoder and force fresh
IDRs; their contribution to latency remains a separate hypothesis.

The 0.14 RPM was installed and refreshed. Both its recovery journal and a real
UU acquisition confirm policy 0 (`notifications=0`). Bounded performance and
producer-stderr diagnostics were enabled for this investigation. This runtime
reproduced another kernel EncoderQueue hang/reset at 16:24:40 MST, an HEVC LP
output-map error 24, and a 6,104,302 microsecond readback/encode maximum in the
same log interval. The same-codec normal-entrypoint recovery then ran. The
capture generation did not exit during that observation. This is concrete
evidence of a multi-second encode stall; it does not establish that every
reported video delay or black screen has the same cause.

The user reported some improvement on 0.14 but black screens persisted and
desktop video caught up roughly three seconds after stopping pointer movement.

## HEVC stability mitigation (RPM 0.15)

Intel HEVC now selects the normal entrypoint by default. Waiting for an LP
encode error before falling back cannot prevent the preceding GPU timeout.
H.264 retains its capability-checked LP selection, and other vendors are
unchanged. `UURB_INTEL_HEVC_LOW_POWER=1` explicitly opts back into the unstable
diagnostic path; the synthetic failure-recovery probe sets that override to
continue exercising both codec recoveries. No desktop-wide driver setting is
changed. The independent cursor and policy-0 video notification changes remain.

`tests/probes/vaapi_hevc_stress.c` generated 1,200 moving full-HD HEVC frames
with AQ and 49 FPS/bitrate/VBV reconfigurations. All timestamps and requested
IDRs passed; independent CPU decoding recovered exactly 1,200 1920×1080 frames.
The logged entrypoint remained normal. This finite synthetic test is not a
guarantee of long-session stability or client presentation FPS.

The Windows PE NV12/UAV path also passed independent CPU decode of 64 frames
per codec, all-frame color/order checks (maximum sampled error 2/255), requested
IDRs and timestamps. Live mode logs in the disposable prefix verified H.264 LP
and HEVC normal selection without any diagnostic override. Actual UU session
stability/performance on 0.15 still requires separate acceptance.

The user rejected 0.15: black screens were worse. Further logging recorded 21
capture-generation exits. The saved producer stderr reports `Invalid bounded
cursor metadata`, including a generation that exited before any cursor update.
No encoder error/fallback was logged in that runtime. Thus the HEVC mitigation
did not resolve the separate cursor-induced capture failure. The installed and
active service was rolled back to 0.12 before preparing another revision.

## Cursor/video failure isolation (RPM 0.16)

Malformed/unsupported optional cursor metadata retains the last valid cursor
snapshot and no longer terminates the video stream. The parser still rejects
it without mutation or out-of-bounds reads. Both normal and superseded buffers
use this isolation policy; cursor-only buffers still cannot become video.
The first eight rejected updates log bounded scalar geometry/format details,
without pixels. Video plane, FD, corruption and synchronization validation
remain strict. Later valid cursor updates are processed normally.

`cursor_video_isolation.c` exercises the real capture callbacks with a stubbed
GPU sink: valid video is delivered despite a malformed cursor, superseded and
cursor-only buffers do not encode, the next valid cursor recovers, and a
corrupted video plane still terminates capture. All 15 PipeWire probe tests and
33 runtime tests passed. The normal HEVC entrypoint remains the default. The
policy-0 cursor-only/video experiment is no longer selected automatically;
standard DXGI pointer-only notifications and the independent cursor remain.
Actual UU stability and client latency still require acceptance.

The user confirmed that 0.16 stopped black screens. Video remained uneven,
including playback with a stationary pointer, and felt less responsive.
The active runtime logged no capture-generation exits and no encoder errors.
Sampled HEVC encoding was around 14–15 ms per frame, apart from readback/upload.

## Explicit H.264 capability policy (RPM 0.17)

An optional private `~/.config/uurb/video-codec.json` containing
`{"schema":1,"codec":"h264"}` restricts VA-API capability negotiation to H.264.
Absent configuration or `codec: auto` preserves both hardware-supported codecs.
Only the worker environment receives `UURB_VAAPI_CODEC_POLICY`; no global
driver/desktop setting changes. Explicit diagnostic environment values take
precedence. Invalid policy/schema values are rejected. The installer refresh
preserves this separate private file. Direct native encoder tests remain able
to compare both codecs without changing the production negotiation policy.

HEVC-specific capability, preset and sequence-header requests are rejected by
a restricted query session; an HEVC stream is never silently encoded as H.264.
Native capability enumeration and H.264 sequence export passed on the actual
Intel device. All 36 runtime tests passed, including optional/private policy,
explicit override and rejection cases.

The same 1,200-frame 1920×1080 moving-pattern test with 49 parameter changes
measured H.264 LP at 6,169 microseconds average / 16,556 maximum, versus normal
HEVC at 12,662 average / 34,737 maximum. Reconfiguration averaged 2,553 versus
12,612 microseconds. Independent CPU decoding recovered all 1,200 frames for
each codec. These are native synthetic timings, not remote presentation FPS.
The existing 0.16 cursor/video failure isolation and default pointer contract
are retained. Real UU negotiation and client playback must be checked separately.
