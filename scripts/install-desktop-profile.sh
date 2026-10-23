#!/usr/bin/env bash
# Update only the desktop-profile helpers on an installed Fedora UUWay package.
set -Eeuo pipefail
umask 077
[[ $EUID -ne 0 && -f /etc/fedora-release ]] || {
    echo '请在 Fedora 桌面中以普通用户运行。' >&2; exit 1;
}
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target=/usr/lib/uuway/scripts
rpm -q uuway >/dev/null
[[ ! -L "$target" && $(stat -c %u "$target") == 0 ]] || exit 1
files=(uuway_desktop.py uuway_desktop_system.py)
changed=()
for name in "${files[@]}"; do
    [[ -f "$source_dir/$name" && ! -L "$target/$name" && -f "$target/$name" ]] || exit 1
    if ! cmp -s "$source_dir/$name" "$target/$name"; then changed+=("$name"); fi
done
if ((${#changed[@]})); then
    parent="$HOME/backup/UUWay/桌面默认配置"
    mkdir -p -- "$parent"
    backup="$(mktemp -d "$parent/helpers-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
    for name in "${changed[@]}"; do cp -- "$target/$name" "$backup/$name"; done
    echo "桌面辅助脚本备份：$backup"
    restore_helpers() {
        for name in "${changed[@]}"; do
            sudo install -o root -g root -m 0644 -- "$backup/$name" "$target/$name" || true
        done
    }
    trap restore_helpers ERR
    for name in "${changed[@]}"; do
        sudo install -o root -g root -m 0644 -- "$source_dir/$name" "$target/$name"
        sudo restorecon "$target/$name"
    done
    trap - ERR
fi
echo '桌面辅助脚本已更新；未重启桌面、UU 或音频服务。'
