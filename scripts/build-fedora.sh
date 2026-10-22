#!/usr/bin/env bash
# Native Fedora VA-API build. Run as the desktop user after installing dependencies.
set -Eeuo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f /etc/fedora-release ]] || { echo 'This build targets Fedora.' >&2; exit 1; }
[[ "$(uname -m)" == x86_64 ]] || { echo 'x86_64 is required.' >&2; exit 1; }
wine --version | grep -Eq '^wine-11\.0([^0-9]|$)' || { echo 'Wine 11.0 is required.' >&2; exit 1; }
export UURB_WINEGCC="$(command -v winegcc)"
export UURB_WINE_HEADERS=/usr/include/wine
export UURB_GLSLANG="$(command -v glslangValidator)"
cd "$root"
for script in build-dxvk-capture build-helpers build-uu-native-input build-uu-native-display \
              build-native-ime build-pipewire-probe; do
    bash "scripts/$script.sh"
done
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror -shared \
    -o build/native-presenter/uurb-dxgi-capture-loader.dll src/uu_dxgi_duplication_loader.c
UURB_AMD_BASE="$root" bash scripts/build-amd-runtime.sh
mkdir -p "$root/capture"
gcc -std=gnu11 -O2 -Wall -Wextra -Werror -shared -fPIC \
    $(pkg-config --cflags libpipewire-0.3) src/uu_umbriel_cursor_meta.c \
    -o capture/uu-umbriel-cursor-meta.so -ldl -pthread
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    src/uu_clipboard_pipe.c -o build/native-presenter/uu-clipboard-pipe.exe
echo 'Build complete. Validate hardware with scripts/test-amd-runtime.py before setup.'
