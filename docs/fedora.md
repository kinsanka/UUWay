# Fedora 44 / Umbriel 发布说明

本项目面向已有 Umbriel + Noctalia 桌面的 Fedora 用户，不替换合成器、音频服务器或其他远程软件。0.18.1 的默认登录、锁屏与 GNOME Keyring 集成见 [桌面默认配置](desktop-defaults.md)。普通安装见 [README](../README.md)。旧的 [niri 调试记录](fedora-niri-intel.md) 是迁移历史，不代表当前安装方式。

## 目标与架构

实测：Fedora 44 x86_64、Umbriel nightly 20261017（965da48）、对应的 xdg-desktop-portal-umbriel、Noctalia 5.3.0、Wine 11.0 Staging、Intel UHD 730 / i915、Intel media driver 26.1.5、1080p60、正常旋转和缩放 1。虚拟机同时有 Virtio 显示设备；编码器按 GPU UUID 选择硬件，不硬编码 renderD 节点。

一个 `uuway.service` 别名指向 `uu-native-bridge.service`。`uuway_daemon.py` 校验不可变运行时包，先启动只读显示 RPC 线程，在 UU 引导就绪后启动文本剪贴板线程。任一管理线程意外退出会停止整组，由 systemd 统一恢复。线程不会互相发送 systemd READY/WATCHDOG。

剪贴板在 10 秒内反复传输超过保护阈值时，仅暂停同步 10 秒，再允许后续复制；不因此结束远程画面和键鼠连接。暂时无法读取原生文本时保留上次观察值，减少重复写入。此保护不代表已确定其他远程软件是反复同步的来源。

显示与剪贴板不再各运行一个持久 Python 管理进程。Wine、Windows UU 服务、原生输入、采集与终端工作进程仍然存在。采集及编码的数据通路保持不变。

显示适配读取 Umbriel IPC，只报告现有活动模式。屏幕通过 xdg-desktop-portal / PipeWire 获取。`uu-umbriel-cursor-meta.so` 处理本环境的光标元数据协商，保留独立光标。Intel 的局部 `INTEL_DEBUG=noccs,nofc` 修正限定于 UUWay 子进程。

`~/.config/uurb/video-codec.json` 的 `codec=auto` 允许 HEVC 协商；不强制客户端使用不支持的解码器。安装器仅在配置缺失时创建它。内部 `amd` / `amd-vaapi` 名称沿用旧包兼容约定，不表示 Intel 使用 AMD 驱动。

## 首次使用

官方程序由用户从 https://uuyc.163.com/ 下载。已验证版本为 4.43.0，后续官方版本未经本次回归。RPM 不打包官方程序，也不硬编码会过期的下载链接。

安装 RPM 后打开「UUWay 安装与修复」。向导检查 Wine 11.0、输入权限、独立 Wine 前缀、辅助程序及 Fcitx5 插件，等待用户登录，然后取得屏幕共享授权并启用后台。Fcitx5 文字输入为可选通道，不更换输入法皮肤。

需要在 Umbriel 图形会话中操作，不能在无桌面的 SSH 会话中完成屏幕选择。首次授权输入设备后可能需要按提示重新登录；向导不会强行注销。共享授权令牌保存在本人私有目录，不可复制给其他用户。

## 从源码构建

在 Fedora 44 下执行，Wine ABI 限定 11.0 系列：

```sh
sudo dnf install --setopt=install_weak_deps=False wine wine-devel gcc gcc-c++ \
  mingw64-gcc mingw64-gcc-c++ meson ninja-build pkgconf-pkg-config glslang \
  libavcodec-free-devel libavutil-free-devel libswscale-free-devel libva-devel \
  vulkan-headers vulkan-loader-devel libdrm-devel pipewire-devel json-c-devel \
  libX11-devel libXfixes-devel fcitx5-devel libei-devel gstreamer1-devel \
  gstreamer1-plugins-base-devel xorg-x11-server-Xvfb xclip wl-clipboard \
  python3-gobject python3-dbus gtk3 at-spi2-core git ripgrep rpm-build zenity
bash scripts/build-fedora.sh
python3 packaging/build-rpm.py --version 0.18.1 --release 1.fedora_umbriel
```

构建脚本固定 DXVK v3.1（70d7508c01201ed3d4bfb33da42ba834eafe3857）和 nv-codec-headers n13.0.19.0（e844e5b26f46bb77479f063029595293aa8f812d），核对源码版本。DXVK 修改以 `patches/dxvk-3.1-private-capture.patch` 提供。Fedora 使用系统 MinGW、Wine 开发头和 glslang，不抽取 Ubuntu 开发包。FFmpeg 等动态库由 RPM 解析为系统依赖。

这里提供可重建的源码和步骤，**不声称不同机器的二进制逐字节一致**。本次 RPM 的核心采集／编码文件来自已在目标机使用并核对哈希的构建产物；新增光标 shim、剪贴板辅助程序和 Fcitx5 插件在目标机重新编译。完整源码重建和其他硬件矩阵需另行验证。

## 验证

不打开共享窗口的自动检查：

```sh
set -e
for suite in test_desktop_defaults test_unified_supervisor test_wayland_clipboard test_native_service test_fedora_port \
  test_native_runtime_package test_uuway_cli test_wayland_portal_probe; do
  python3 -m unittest discover -s tests -p "$suite.py"
done
```

覆盖线程就绪、启动失败、退出与超时、统一服务生成、运行时闭包与篡改拒绝、CLI 安装与备份，以及 Fedora 编译兼容性。真实 Umbriel 的只读显示 RPC 还验证了 inspect 请求、线程停止和 socket 清理，无显示模式修改。发布包需通过真实 UU 重连、画面／输入及双向中文复制复核，结果记录在 GitHub Release；自动测试不能代替这些检查。

原链路在 Umbriel 上由用户确认画面、鼠标键盘和视频流畅，H.264 与 HEVC 对照均可用，随后选择 HEVC。历史独立编码探针通过 H.264/HEVC 帧颜色、IDR 及生命周期检查；探针耗时不等同于客户端实际帧率。

系统声音、文件／图片剪贴板、其他显卡、多屏混合缩放、锁屏／注销后无人值守连接未列为完成验收。Noctalia Dock 12 像素触发区是独立修正，不包含在 UUWay RPM 中。

## 升级与回退

安装新版 RPM 后运行安装与修复。现有账号、配置和共享令牌保留在用户目录，旧运行时不删除。修改前备份到 **`~/backup/UUWay/安装升级/backup-日期-随机串/`**，权限 0700，内有 `RESTORE.txt`。备份含私人授权，切勿上传。

升级后台会短暂断开 UU，不注销图形会话。旧 `uu-native-display`、`uu-wayland-clipboard` 服务停用，文件保留。仅移除明确属于旧迁移启动包装器的 `70-umbriel.conf`，修改前一并备份；其他自定义覆盖不自动删除。

回退时在本机/VNC 终端停止 `uuway.service`，按备份内 `RESTORE.txt` 还原并重新加载用户服务，恢复升级前启用的显示、剪贴板及桥接服务。如需撤回系统包，安装自己保存的上一版 RPM；不要删除 Wine 前缀和共享授权来“重装”。

诊断使用 `uuway doctor` 及 `systemctl --user status uuway.service`。日志可能包含私人路径和 UU 输出，公开反馈前先脱敏，不上传整个用户状态目录。

## 许可证与隐私

保留 AGPL-3.0-or-later、继承部分的 MIT 声明及 DXVK Zlib 许可。完整源码在同版本 Git 标签和源码归档中提供。RPM 含 LICENSE、NOTICE、DXVK_LICENSE，不含官方 UU 安装程序、账号、Wine 前缀、屏幕令牌、私钥或私人日志。
