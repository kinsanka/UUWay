# UUWay · Fedora / Umbriel

Native Fedora packaging and Umbriel Wayland integration for the UU Remote controlled endpoint, derived from [GaryOAO/UUWay](https://github.com/GaryOAO/UUWay).

[中文](README.md) · [Build and validation](docs/fedora.md)

## Install

Tested: Fedora 44 x86_64, Umbriel, Noctalia 5.3.0, Wine 11.0, Intel UHD 730, 1920×1080 / 60 Hz. Other GPUs have not passed this project's live acceptance tests.

1. Download the RPM from [the Fedora release](https://github.com/kinsanka/UUWay/releases/tag/fedora-0.18.1).
2. Run `sudo dnf install ./uuway-0.18.1-1.fedora_umbriel.fc44.x86_64.rpm`.
3. Download the official Windows installer from [UU Remote](https://uuyc.163.com/). Open **UUWay 安装与修复** from the desktop menu, select the installer, and complete installation and sign-in.
4. Select the whole display in the system screen-sharing prompt and allow access. Connect using the normal UU desktop or phone app.

Alternatively, run `bash install.sh` from this project inside Umbriel. It downloads the matching release RPM, verifies its published SHA-256 checksum, and launches the same wizard. Login and screen-sharing consent remain normal user interactions.

## Desktop defaults

The primary target is Umbriel + Noctalia: live testing on the target Fedora/Intel machine showed better compatibility and removed the earlier noticeable video queueing. This is not a general benchmark across compositors.

The first-run wizard defaults to existing greetd auto-login, immediate Noctalia password lock, then UU startup. RPM dependencies include GNOME Keyring, its PAM module and Seahorse. A successful password unlock can also unlock the matching Login keyring; no password is stored. Known keyring prompt windows are cancelled only while the desktop is locked. The UU prefix’s Wine tray host is hidden without terminating it. See [desktop defaults](docs/desktop-defaults.md) for commands, opting out, backups and the startup exposure interval.

## Background model

One `uuway.service` (an alias of `uu-native-bridge.service`) owns the supervisor, read-only display RPC and clipboard management. These managers run in one Python process with a shared lifecycle. Necessary Wine, capture, native input and terminal workers remain subprocesses; this release does **not** claim a single operating-system PID.

Existing codec preferences are retained; new installations allow HEVC / H.265 negotiation and normal client fallback. The internal `amd` / `amd-vaapi` identifier also covers this project's Intel implementation.

## Limitations and license

Remote system audio is unresolved. Setup does not change PipeWire defaults, microphones or voice-call routing. Clipboard support is UTF-8 text only (4 MiB limit). The Umbriel backend reads the active physical mode without creating virtual displays or changing resolution. A logged-in Wayland session and valid screen-sharing consent are required. First-login tray behavior still needs a real login test. Traffic-monitor browser automation is a separate private workflow. Use RPM upgrades; Ubuntu `.deb` updates are disabled on Fedora.

See [docs/fedora.md](docs/fedora.md) for source builds, backups and validation boundaries. No proprietary UU executable, Wine prefix, account, portal token or private log is distributed. See [LICENSE](LICENSE) and [NOTICE](NOTICE); DXVK retains its Zlib license. This project is unaffiliated with NetEase.
