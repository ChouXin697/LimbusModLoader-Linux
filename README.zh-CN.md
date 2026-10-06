# Limbus Mod Loader —— Linux / Proton 移植版

[LEAGUE-OF-NINE/LimbusModLoader](https://github.com/LEAGUE-OF-NINE/LimbusModLoader)（上游 `v1.8`）的**非官方 Linux 移植**，
连同我们在 Linux + Steam/Proton 环境下运行它的全部经验：代码改动、配置步骤，以及遇到过的每一种
故障模式与排查方法。

目前没有为 Linux 做的 mod 框架——游戏本体只有 Windows 版，靠 Proton 跑，所有的 mod 工具也是。
本仓库让现有加载器**直接跑在 Linux 宿主机上**，而不是塞进 Proton 前缀里跑，这样既简单又便于调试。

> 与 Project Moon 及上游加载器作者无关。风险自负。

**语言：[English](README.md) · [中文](README.zh-CN.md)**

---

## 为什么需要移植

上游加载器以 PyInstaller 打包的 `main.exe` 形式发布，其 Python 源码依赖一串 Windows 专有接口
来定位 Steam、游戏与 mod 目录：

| 上游的假设 | 在 Linux 上的后果 |
| --- | --- |
| `import winreg` 读 `HKCU\Software\Valve\Steam` | `ModuleNotFoundError: No module named 'winreg'` —— 加载器**在 import 阶段就死**，什么都还没开始打补丁 |
| `os.getenv("APPDATA")` | Linux 宿主机没有这个变量；游戏的 AppData 实际在**Proton 前缀内部** |
| 写死的 Windows 路径（`r"steamapps\common\..."`） | 根本解析不到 |
| `tasklist /FI "IMAGENAME eq LimbusCompany.exe"` | 不存在这个命令，自动还原的监视循环永远看不到游戏 |

移植用一个很小的 `platform_paths.py` 取代上述全部逻辑，在 Linux 上自行发现 Steam 库、Proton 前缀与
游戏目录。具体 diff 见 [docs/zh-CN/02-工作原理与移植改造.md](docs/zh-CN/02-工作原理与移植改造.md)。

## 快速开始

```bash
# 1. 安装依赖（用宿主机的 Python，不是 Proton 里的）
#    无论你是 clone 下来的还是直接拷贝文件夹，都一样
cd /你的路径/LimbusModLoader-Linux/loader
python3 -m venv venv-linux
venv-linux/bin/pip install -r requirements-linux.txt

# 2. Steam → 右键「Limbus Company」→ 属性 → 启动选项，填入：
#    "/你的绝对路径/loader/run-linux.sh" %command%
```

通过 Steam 启动游戏一次。加载器会创建
`.../compatdata/1973530/pfx/drive_c/users/steamuser/AppData/Roaming/LimbusCompanyMods/`
——**mod 就放这里**。把 `.carra2` / `.carra` / `.zip` / `.bank` 文件丢进去，重新启动即可。

完整流程见 [docs/zh-CN/01-安装与配置.md](docs/zh-CN/01-安装与配置.md)。

## 仓库结构

```
loader/                 适配 Linux 的加载器源码（可直接用）
  platform_paths.py     新增 —— Linux 下的 Steam / 前缀 / 游戏目录发现
  run-linux.sh          新增 —— Steam 启动项入口
  main.py patch.py sound.py modfolder.py compress.py
  linux-port.diff       相对上游 v1.8 的改动 unified diff
docs/en/ , docs/zh-CN/  双语文档（索引见下）
LICENSE                 GPL-3.0，继承自上游
```

`loader/` 是上游的 **Linux 相关子集**，不是完整镜像：Windows 专有的构建工具（`main.spec`、
`install_deps.ps1`、Go bootloader、发布 workflow）都省略了，因为从源码运行都不需要它们。
若要构建 Windows 版 `main.exe`，请直接用上游仓库。

## 文档索引

| # | 中文 | English |
| --- | --- | --- |
| 1 | [安装与配置](docs/zh-CN/01-安装与配置.md) | [Installation & setup](docs/en/01-installation.md) |
| 2 | [工作原理与移植改造](docs/zh-CN/02-工作原理与移植改造.md) | [How it works + the port diff](docs/en/02-how-it-works.md) |
| 3 | [疑难排查](docs/zh-CN/03-疑难排查.md) | [Troubleshooting](docs/en/03-troubleshooting.md) |
| 4 | [模组格式与取证](docs/zh-CN/04-模组格式与取证.md) | [Mod formats & forensics](docs/en/04-mod-formats.md) |

## 测试环境

- Linux（Ubuntu 系内核 7.0.0-38-generic），Python 3.12
- Steam 为**原生安装**（代码同时也探测 Flatpak 路径 `~/.var/app/com.valvesoftware.Steam/data/Steam`）
- Limbus Company 通过 Steam Play 运行，兼容层用 **GE-Proton 11.5**；AppID `1973530`
- 加载器上游版本 `v1.8`

## 已知局限

- 打的是 **Addressables 缓存**，不是游戏文件本体。打补丁前把 `__data` 换成 `__original`，退出时还原
  ——若被强杀，可能残留已打补丁的状态（见[文档 3](docs/zh-CN/03-疑难排查.md#缓存残留打补丁后的-__data-没还原)）。
- Lunartique 格式的 `*.zip` 会被转成 `*.carra2` **并删除原 zip**——请自己留好每份下载的压缩包。
- 第三方站点下的老 mod 可能静默失效（bundle 哈希过期）或直接崩溃（序列化布局不兼容），见[文档 4](docs/zh-CN/04-模组格式与取证.md)。
- 部分地区连不上 Project Moon 的内容 CDN，会导致游戏**根本进不去**，与 mod 无关，见[文档 3](docs/zh-CN/03-疑难排查.md#开始按钮按不了)。
- **没有 CI，也没有测试集。** 验证是手工的——导入模块图、解析路径、在下述环境实机运行。请把它当作
  「人工验证过」，而不是「穷尽验证过」。
- **Windows 依然可用。** `platform_paths.py` 保留了注册表 / `%APPDATA%` 分支，因此 `loader/` 在
  Windows 上也是可直接替换的；只是这里只实测了 Linux 一侧。

## 致谢与许可

上游加载器由 LEAGUE-OF-NINE 团队（`@myssal`、`@zenocara`、`@qifeetrying`）开发 ——
<https://github.com/LEAGUE-OF-NINE/LimbusModLoader>。本移植版及文档沿用同一 **GPL-3.0** 许可（见 [LICENSE](LICENSE)）。

**这是上游的修改版。** 全部改动列在 [`loader/linux-port.diff`](loader/linux-port.diff)，说明见
[文档 2](docs/zh-CN/02-工作原理与移植改造.md)；最近修改日期 2026-10-06。
