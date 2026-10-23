# Fedora 0.18.1

- Fedora 44 + Umbriel + Noctalia is now the `main` branch and the default installation target. The original [GaryOAO/UUWay](https://github.com/GaryOAO/UUWay) project remains credited in README and NOTICE.
- Keep Intel VA-API H.264/HEVC negotiation, independent cursor metadata, native input and bidirectional text clipboard. HEVC remains available through the user's existing automatic codec negotiation.
- Add GNOME Keyring, its PAM module, Seahorse and libsecret as RPM dependencies. The setup wizard defaults to an existing greetd automatic-login session followed by a confirmed Noctalia password lock before UU starts. Configuration applies at the next graphical login; it does not restart the current desktop or audio services.
- Hide only the UU Wine prefix's `explorer.exe` / `Shell_TrayWnd` host through the existing clipboard helper. Do not close the host or end UU's background lifecycle. A one-shot hide command and rollback instructions are documented in [Desktop defaults](../docs/desktop-defaults.md).
- Record the failing background worker and source location without exception text, clipboard contents, account data or full filesystem paths.
- Accept the existing unified service during upgrades and validate its configuration before stopping a live UU connection.

The previous 0.18.0 runtime passed the user's remote picture/input/text-clipboard and reconnect checks. First-login locking, keyring unlock and the new tray-hiding behavior require separate desktop acceptance. Simultaneous hypervisor VNC and UU use remains under investigation; this release does not claim to fix it. Audio forwarding remains unresolved. Sunshine and existing audio routes are preserved.
