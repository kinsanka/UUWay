# UUWay · Fedora / Umbriel

在 Fedora 44 的 Umbriel Wayland 桌面上运行 UU 远程被控端。本项目整理了实际使用的 Intel VA-API 编码、屏幕采集、独立光标、输入及双向文本剪贴板适配，提供原生 RPM 和安装向导。

[English](README.en.md) · [安装、构建与验证说明](docs/fedora.md) · [上游项目](https://github.com/GaryOAO/UUWay)

## 为什么采用 Umbriel

在本机 Fedora / Intel 实测中，换用 Umbriel 后 UU 的画面、独立光标及输入兼容性更好，先前明显的排队延迟也不再出现。因此当前主线以 Umbriel + Noctalia 为默认目标；这不代表所有硬件上的统一性能结论。

## 安装

适用范围：**Fedora 44 x86_64、Umbriel、Wine 11.0、可用的 Intel VA-API 驱动**。实测 Intel UHD 730、1080p / 60 Hz、Noctalia 5.3.0；默认登录配置还需要已有的 greetd。其他显卡和桌面请先阅读验证边界。

1. 从 [Fedora 发布页](https://github.com/kinsanka/UUWay/releases/tag/fedora-0.18.1) 下载 RPM，打开终端安装：

   ```sh
   sudo dnf install ./uuway-0.18.1-1.fedora_umbriel.fc44.x86_64.rpm
   ```

2. 从 [UU 远程官网](https://uuyc.163.com/) 下载 Windows 官方安装程序。在 Umbriel 桌面中打开应用菜单里的 **「UUWay 安装与修复」**，选择该安装程序，按提示安装并登录 UU。
3. 在系统共享屏幕窗口中选择整个屏幕并允许共享，再用电脑或手机 UU 连接。

也可以下载本项目源码，在 Umbriel 的终端运行 `bash install.sh`。它下载对应版本的 RPM、核对发布校验和，然后进入同一个向导，不需要 AI 再次配置。首次登录和屏幕授权由用户本人完成。

## 默认登录、锁屏和钥匙环

安装向导默认配置 **自动登录 Umbriel → 立即密码锁屏 → UU 后台上线**。加入 GNOME Keyring、PAM 模块和「密码和密钥」为 RPM 依赖，锁屏认证时尝试同时解锁 Login 钥匙环；锁屏后取消已知的钥匙环弹窗。密码不会被保存。

默认还会自动隐藏 UU 专用 Wine 前缀中的 Explorer 托盘小白条，保留其后台进程。配置说明、手动隐藏命令、关闭自动登录选项及回退方法见 [桌面默认配置](docs/desktop-defaults.md)。自动登录后立即锁屏仍有短暂启动阶段，不等同于始终停在未登录界面。

## 一个后台入口

Umbriel 模式使用一个 `uuway.service` 管理后台；它是 `uu-native-bridge.service` 的别名。显示查询、剪贴板控制和桥接管理在同一个 UUWay 管理进程中运行，共同启动和退出。

**进程列表仍会显示 Wine / UU 及必要的原生输入、采集、终端子进程**。这不是单一 PID 的重写版，不能将 Wine 的不同程序直接合成 Linux 线程。旧版独立显示与剪贴板服务会在升级时停用，并保留配置备份。

```sh
systemctl --user status uuway.service
uuway doctor
```

默认保留 HEVC / H.265 协商，客户端不支持时由 UU 协商回退。升级不会覆盖已有的编码选择。内部后端名 `amd` / `amd-vaapi` 同时包含本项目的 Intel 适配。

## 已知边界

- 远程系统声音尚未修复；安装及统一后台不修改 PipeWire 默认设备、麦克风或通话路由。
- 剪贴板仅同步 UTF-8 文本，最大 4 MiB；文件、图片剪贴板不在支持范围。
- 当前 Umbriel 路径使用已有显示器的活动模式，不自动创建虚拟显示器或修改分辨率；初始目标为正常方向、缩放 1。
- 需要已登录的图形会话及有效屏幕共享授权。切换桌面或撤销授权后可能需要重新授权。
- 首次启动托盘窗口在辅助程序就绪前的表现，还需实际重新登录确认。流量监控浏览器是独立的用户工作流，不属于此软件包。
- 本项目的 Fedora RPM 不使用上游 Ubuntu `.deb` 自动更新。请下载新版 RPM 安装。

测试范围见 [Fedora 说明](docs/fedora.md)。Noctalia Dock 的边缘触发修正独立于此软件包，不会在安装 UUWay 时替换桌面组件。

## 来源与许可证

派生自 GaryOAO/UUWay 和 Lachlan Chen 的 uu-remote-ubuntu-bridge，保留 [AGPL-3.0-or-later](LICENSE)、[MIT 声明](NOTICE) 和 DXVK 的 Zlib 许可。构建时使用固定版本的第三方源代码，具体见构建脚本和 `config/`。

发布包不包含 UU 官方安装程序、Wine 用户前缀、账号、共享屏幕令牌或私人日志。UU 商标及官方软件属于其各自权利人。本项目与网易无隶属关系。
