# Limbus Mod Loader — Linux / Proton port

An **unofficial Linux port** of [LEAGUE-OF-NINE/LimbusModLoader](https://github.com/LEAGUE-OF-NINE/LimbusModLoader) (upstream `v1.8`),
plus everything we learned running it on a Linux + Steam/Proton setup: the code changes, the
setup steps, and a catalogue of every failure mode we hit and how to diagnose it.

There is no mod loader built for Linux — the game itself is Windows-only and runs here through
Proton, and so does every modding tool. This repo makes the existing loader run **natively on the
Linux host** instead of inside the Proton prefix, which is both simpler and far easier to debug.

> Not affiliated with Project Moon or the upstream loader authors. Use at your own risk.

**Read this in: [English](README.md) · [中文](README.zh-CN.md)**

---

## Why a port is needed

The upstream loader ships as a PyInstaller-built `main.exe`. Its Python source reaches into
Windows-only APIs to find Steam, the game and the mods folder:

| Upstream assumption | What happens on Linux |
| --- | --- |
| `import winreg` + `HKCU\Software\Valve\Steam` | `ModuleNotFoundError: No module named 'winreg'` — the loader dies **at import time**, before patching anything |
| `os.getenv("APPDATA")` | Not set on the Linux host; the game's AppData actually lives *inside the Proton prefix* |
| Raw Windows paths (`r"steamapps\common\..."`) | Never resolve |
| `tasklist /FI "IMAGENAME eq LimbusCompany.exe"` | No such tool; the auto-restore monitor can never see the game |

The port replaces all of that with a small `platform_paths.py` that discovers Steam libraries,
the Proton prefix and the game directory on Linux. See
[docs/en/02-how-it-works.md](docs/en/02-how-it-works.md) for the exact diff.

## Quick start

```bash
# 1. Get the code and install dependencies (host-side Python, NOT Proton)
git clone <this-repo> LimbusModLoader-Linux
cd LimbusModLoader-Linux/loader
python3 -m venv venv-linux
venv-linux/bin/pip install -r requirements-linux.txt

# 2. Steam → right-click "Limbus Company" → Properties → Launch Options:
#    "/absolute/path/to/loader/run-linux.sh" %command%
```

Launch the game once through Steam. The loader creates
`.../compatdata/1973530/pfx/drive_c/users/steamuser/AppData/Roaming/LimbusCompanyMods/`
— **that** is where mods go. Drop `.carra2` / `.carra` / `.zip` / `.bank` files in and relaunch.

Full walkthrough: [docs/en/01-installation.md](docs/en/01-installation.md).

## Repository layout

```
loader/                 Linux-adapted loader source (drop-in)
  platform_paths.py     NEW — Steam/prefix/game-dir discovery on Linux
  run-linux.sh          NEW — Steam launch-options entry point
  main.py patch.py sound.py modfolder.py compress.py
  linux-port.diff       unified diff of the changes vs upstream v1.8
docs/en/ , docs/zh-CN/  bilingual documentation (see index below)
LICENSE                 GPL-3.0, inherited from upstream
```

## Documentation

| # | English | 中文 |
| --- | --- | --- |
| 1 | [Installation & setup](docs/en/01-installation.md) | [安装与配置](docs/zh-CN/01-安装与配置.md) |
| 2 | [How it works + the port diff](docs/en/02-how-it-works.md) | [工作原理与移植改造](docs/zh-CN/02-工作原理与移植改造.md) |
| 3 | [Troubleshooting](docs/en/03-troubleshooting.md) | [疑难排查](docs/zh-CN/03-疑难排查.md) |
| 4 | [Mod formats & forensics](docs/en/04-mod-formats.md) | [模组格式与取证](docs/zh-CN/04-模组格式与取证.md) |

## Tested environment

- Linux (Ubuntu-family kernel 7.0.0-38-generic), Python 3.12
- Steam installed **natively** (the code also probes the Flatpak path `~/.var/app/com.valvesoftware.Steam/data/Steam`)
- Limbus Company via Steam Play, using **GE-Proton 11.5** as the compatibility tool; AppID `1973530`
- Loader upstream `v1.8`

## Known limitations

- Patches the **Addressables cache**, not the game files. `__data` is swapped for `__original`
  before patching and restored on exit — a hard kill can leave the patched state behind
  ([doc 3](docs/en/03-troubleshooting.md#stale-cache-a-patched-__data-left-behind)).
- Lunartique `*.zip` mods are converted to `*.carra2` **and the zip is deleted** — keep your own
  copy of every archive you download.
- Old mods from third-party sites may silently no-op (stale bundle hash) or crash (incompatible
  serialization layout). See [doc 4](docs/en/04-mod-formats.md).
- Some regions cannot reach Project Moon's content CDN, which prevents the game from starting
  at all — unrelated to mods. See [doc 3](docs/en/03-troubleshooting.md#the-start-button-does-nothing).

## Credits & license

Upstream loader by the LEAGUE-OF-NINE team (`@myssal`, `@zenocara`, `@qifeetrying`) —
<https://github.com/LEAGUE-OF-NINE/LimbusModLoader>. This port and the documentation are
distributed under the same **GPL-3.0** license (see [LICENSE](LICENSE)).
