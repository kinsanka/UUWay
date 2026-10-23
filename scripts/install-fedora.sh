#!/usr/bin/env bash
# Install the matching published Fedora package, then open normal first-run setup.
set -Eeuo pipefail
umask 077
[[ $EUID -ne 0 ]] || { echo '请以桌面用户运行，安装 RPM 时会单独请求 sudo。' >&2; exit 1; }
[[ -f /etc/fedora-release && $(uname -m) == x86_64 ]] || { echo '需要 Fedora x86_64。' >&2; exit 1; }
desktop=${XDG_CURRENT_DESKTOP:-}
[[ ${XDG_SESSION_TYPE:-} == wayland && ${desktop,,} == *umbriel* ]] || {
    echo '请在 Umbriel 桌面的终端里运行安装程序。' >&2; exit 1;
}
tag=fedora-0.18.1
rpm_name=uuway-0.18.1-1.fedora_umbriel.fc44.x86_64.rpm
base="https://github.com/kinsanka/UUWay_Fedora-Umbriel/releases/download/$tag"
cache="${XDG_CACHE_HOME:-$HOME/.cache}/uuway-installer/$tag"
mkdir -p "$cache"
[[ ! -L "$cache" && $(stat -c %u "$cache") == "$UID" ]] || exit 1
chmod 700 "$cache"
for name in SHA256SUMS "$rpm_name"; do
    curl --fail --location --proto '=https' --proto-redir '=https' --retry 2 \
        "$base/$name" -o "$cache/$name.part"
    mv -- "$cache/$name.part" "$cache/$name"
done
expected="$(awk -v name="$rpm_name" '$2 == name {print $1}' "$cache/SHA256SUMS")"
[[ $expected =~ ^[0-9a-f]{64}$ ]] || { echo '发布校验清单无效。' >&2; exit 1; }
actual="$(sha256sum "$cache/$rpm_name")"
[[ ${actual%% *} == "$expected" ]] || { echo 'RPM 校验失败，请重试下载。' >&2; exit 1; }
sudo dnf install "$cache/$rpm_name"
# Main may contain a desktop-only fix newer than the stable runtime RPM.
bash "$(dirname -- "${BASH_SOURCE[0]}")/install-desktop-profile.sh"
exec /usr/lib/uuway/scripts/uuway-setup
