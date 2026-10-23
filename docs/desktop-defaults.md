# 默认桌面集成：自动登录后锁屏、钥匙环与托盘窗口

本项目的主线目标是 Fedora 44 + Umbriel + Noctalia 5.3。选择 Umbriel 是本机实测后的兼容性决定：迁移后 UU 的画面、独立光标、键鼠输入和 HEVC 视频已确认可用，之前在 niri 上明显的排队延迟在该环境不再出现。这不是所有 Intel 显卡或所有合成器的性能排名；niri 迁移记录保留为历史资料。

## 默认安装行为

0.18.1 起，安装向导在 UU 配置完成后默认安装以下桌面配置：

1. **已有 greetd 登录管理器**在开机时自动登录当前用户的 Umbriel 会话。保留现有登录页、语言及 GPU 环境参数，不安装或切换其他登录管理器，不替其他账号开启自动登录。
2. 在新图形会话中启动 Noctalia，立即请求密码锁屏，关闭免密宽限时间及空密码解锁。确认锁屏生效后才允许 UUWay 启动。若新会话的锁屏在限定时间内无法确认，则退出该会话返回登录页。
3. 锁屏使用系统密码验证。GNOME Keyring 的 PAM 模块接收这次认证密码，尝试解锁 **Login** 钥匙环。不会把密码写进配置、脚本或命令行。
4. 锁屏确认后，仅取消已知的 GNOME Keyring 解锁弹窗；一旦用户解锁桌面就停止处理，不关闭其他窗口，不禁用或杀死钥匙环服务。
5. 密码解锁后，Noctalia 的 `session_unlocked` 事件会启动一个最长 10 秒的临时检查：只有桌面已解锁、Secret Service 确认 **Login** 钥匙环 `Locked=false` 时，才关闭仍停在“等待输入密码”的登录钥匙环弹窗。再次锁屏、钥匙环仍锁定或状态查询失败时不会关闭该提示；不读取密钥内容、不提交密码，不增加常驻服务。

**真正的登录界面尚未进入用户桌面，不能靠提前运行 UUWay 来采集和控制。**这里看到的是自动登录后的锁屏。远程连接依然需要通过锁屏认证后才能操作桌面。自动登录到锁屏生效之间存在短暂的会话启动阶段，这种方案不能等同于“从未登录”，也不能替代磁盘加密或限制物理访问。

配置对**下次图形登录**生效；安装时不注销、不重启、不锁住正在使用的桌面。当前会话会登记为已接管，之后单独重启 UU 不会反复锁屏。后台启动守卫是短暂的 oneshot 服务，不增加常驻管理进程。

默认配置需要已安装并使用 greetd、Umbriel 和 Noctalia。其他登录管理器不会被悄悄替换。若不希望向导开启自动登录，可以运行：

```sh
/usr/lib/uuway/scripts/uuway-setup --no-autologin
```

这个参数表示不新增自动登录设置；不会撤销用户自己已有的自动登录。已装 UU 的用户也可单独配置或先演练：

```sh
python3 /usr/lib/uuway/scripts/uuway_desktop.py install --dry-run
python3 /usr/lib/uuway/scripts/uuway_desktop.py install
```

### 已安装 0.18.1：补上解锁后的弹窗清理

`fedora-0.18.1` RPM 本身只有锁屏期间的清理，尚不包含上述第 5 项。当前 `main` 的 `bash install.sh` 会在安装稳定 RPM 后自动更新这两个桌面辅助脚本，再进入原安装向导。仅补上桌面配置、不重新运行 UU 向导时，可在本项目 `main` 源码目录运行：

```sh
bash scripts/install-desktop-profile.sh
python3 /usr/lib/uuway/scripts/uuway_desktop.py install
```

配置会保留其他解锁钩子。对于已知的 `~/.local/bin/close-keyring-popup.sh` 旧脚本，仅在内容校验完全匹配时替换其钩子；旧文件保留，原 Noctalia 配置另有备份。用户改写过的脚本不会被自动移除。

本机已核对：锁屏 PAM 包含 `pam_gnome_keyring.so auto_start`，密码解锁后的 Login 钥匙环确实处于解锁状态，用户原先也已设置 `session_unlocked` 关闭残留弹窗。此处将这项做法纳入默认配置，并收窄为只处理已解锁的 Login 钥匙环提示；安装过程不触发锁屏，不中断 UU 或通话。下一次自然锁屏/解锁时才会走新的事件钩子。

## GNOME Keyring 必须安装

本项目默认配置明确依赖 `gnome-keyring`、`gnome-keyring-pam`、`seahorse`（密码和密钥管理界面）及 `libsecret`，RPM 会安装它们。`libsecret` 只是客户端库，不能独自替代钥匙环服务。本配置使用 GNOME Keyring；其他 Secret Service 实现不属于这个默认配置的验收范围。

Noctalia 5.3 的锁屏使用 `/etc/pam.d/login`。安装器保留 Fedora 原来的认证栈，只确保包含以下 **optional** 模块；不会修改 `system-auth`、取消系统密码验证或设置免密 PAM：

```pam
auth optional pam_gnome_keyring.so auto_start
```

`auto_start` 使认证阶段可以启动钥匙环服务，锁屏认证完成后不必依赖另一次 PAM open-session。遇到用户已有的自定义控制规则或 `only_if=` 限制时安装器会停止，不覆盖这些策略。

自动登录本身没有提供密码，所以此时钥匙环仍可保持加密锁定。首次在锁屏中输入系统密码后，PAM 才能尝试解锁。请在 **「密码和密钥」** 中确认 Login 钥匙环使用与系统账号相同的密码，并按需要将它设为默认。安装器不会迁移、清空或修改现有钥匙环的密码。指纹等无密码认证不能提供解密钥匙环所需的密码，因此这个默认配置使用密码解锁。

依据：[Noctalia Secret Service 文档](https://docs.noctalia.dev/noctalia/configuration/secret-service/)、[GNOME Keyring PAM 手册](https://wiki.gnome.org/Projects/GnomeKeyring/Pam/Manual)。

## 自动隐藏 Wine 小白条

0.18.1 的文本剪贴板辅助程序默认每秒检查一次当前 **UU 专用 Wine 前缀**的窗口，只隐藏窗口类为 `Shell_TrayWnd` 且拥有进程为 `explorer.exe` 的托盘宿主。它不关闭窗口、不结束 Explorer、不关闭 UU 大窗口或实际服务，也不会操作其他 Wine 前缀。

已运行时也可手动执行一次：

```sh
python3 /usr/lib/uuway/scripts/uuway_desktop.py hide-tray
```

需要回到原先显示托盘宿主的行为，可为 UU 后台设置环境变量 `UUWAY_SHOW_WINE_TRAY=1` 后重启服务。此选项不会让已经隐藏的旧窗口强行重新映射；下次宿主创建时会保留原行为。

若只需要合成器规则，可在 Umbriel 用户配置中使用以下可选示例。注意它按应用名匹配，范围是所有 Wine Explorer 窗口；**默认程序中的前缀内 Win32 筛选更精确**，不要同时把未知 Wine 程序的窗口全部隐藏：

```toml
[[scratchpad]]
name = "uu-helper"

[[window_rule]]
match.app_id = "^explorer[.]exe$"
default_scratchpad = "uu-helper"
default_focused = false
background_render = true
```

首次开机是否仍会在辅助程序就绪前短暂出现白条，需在实际重新登录后确认；不能仅凭源码构建宣称所有首启表现均已修复。

## 备份与回退

修改前备份到 `~/backup/UUWay/桌面默认配置/backup-*/`。`files.json` 记录原路径及原文件是否存在，按原路径保存用户配置和可读的系统配置。备份含个人设置，不公开上传。

回退前先用 VNC／本机终端，停止并停用 `uuway-session-guard.service`，移除新建的 `90-login-lock.conf`，按备份恢复用户文件并重新加载用户服务。`/etc/pam.d/login` 和 `/etc/greetd/config.toml` 要使用 sudo 及 root 所有权恢复；不要把整个备份目录以 root 身份递归复制进用户目录。若自动登录原本就是用户设置的，保留该设置并自行决定是否关闭。整个安装过程不会重启 greetd、Umbriel、音频服务或通话程序。

仅撤回本次辅助脚本更新时，可从 `helpers-*/` 将两个 Python 文件用 `sudo install -o root -g root -m 0644` 恢复到 `/usr/lib/uuway/scripts/`，同时从对应 `backup-*/` 恢复原 Noctalia 设置；无需结束图形会话。
