# 1. Installation & setup

Everything here runs on the **Linux host**. Only the game itself runs under Proton.

## Prerequisites

- **Steam + Limbus Company**, installed with Steam Play / Proton, and **launched at least once
  without the loader**. This is what creates the Proton prefix and the Addressables cache the
  loader needs to find. If `compatdata/1973530/` does not exist yet, nothing below will work.
  (Tested with **GE-Proton 11.5** as the compatibility tool; stock Proton should behave the same,
  since nothing here depends on the Proton flavour — the loader only reads the prefix on disk.)
- **Python 3.10+** on the host (3.12 tested).
- The loader source in this repo (`loader/`).

## Step 1 — Install dependencies

```bash
cd loader
python3 -m venv venv-linux
venv-linux/bin/pip install -r requirements-linux.txt
```

Do **not** reuse a Windows venv, and do not install into the Proton prefix. The loader is a normal
Linux process; it spawns the game as a child.

## Step 2 — Locate your paths

Three directories matter. Substituting your own Steam library if it is not the default one:

```bash
STEAM="$HOME/.local/share/Steam"                       # native Steam
# STEAM="$HOME/.steam/steam"                           # alternative native path
# STEAM="$HOME/.var/app/com.valvesoftware.Steam/data/Steam"   # Flatpak Steam

GAME="$STEAM/steamapps/common/Limbus Company"
PREFIX="$STEAM/steamapps/compatdata/1973530/pfx"

# The game's AppData/Roaming, as the game sees it inside the prefix:
find "$PREFIX/drive_c/users" -maxdepth 3 -type d -name Roaming
```

Conventionally that last command prints

```
.../compatdata/1973530/pfx/drive_c/users/steamuser/AppData/Roaming
```

and the mods folder is `.../Roaming/LimbusCompanyMods` (created on first launch).

| What | Where |
| --- | --- |
| Mods to install | `<AppData>/Roaming/LimbusCompanyMods/` |
| Loader log | `<AppData>/Roaming/LimbusCompanyMods/log.txt` |
| Addressables cache the loader patches | `<AppData>/LocalLow/Unity/ProjectMoon_LimbusCompany/*/*/` |
| Game log (crashes, Addressables errors) | `<AppData>/LocalLow/ProjectMoon/LimbusCompany/Player.log` |
| Sound banks | `$GAME/LimbusCompany_Data/StreamingAssets/Assets/Sound/FMODBuilds/Desktop/` |

If your Steam library is not auto-detected, the loader also reads every path in
`libraryfolders.vdf`, and you can bypass detection entirely:

```bash
export LIMBUS_GAME_DIR="/path/to/steamapps/common/Limbus Company"
```

The same override exists for AppData (`APPDATA=...`) if you ever need to point the loader at a
different prefix.

## Step 3 — Configure the Steam launch options

Right-click **Limbus Company** → **Properties** → **General** → **Launch Options**:

```
"/absolute/path/to/loader/run-linux.sh" %command%
```

Two things matter here:

- **Quote the script path.** It contains no spaces in a clean checkout, but the whole value is
  a shell-like command line and Steam does not quote for you.
- **Keep `%command%`.** Steam expands it to the real launch command (including the Proton
  wrapper). `run-linux.sh` `exec`s the loader with that command as its arguments, and
  `main.py` re-executes it via `subprocess.call(sys.argv[1:])`. That is how the loader ends up
  as the *parent* of the game process — see
  [doc 2](02-how-it-works.md#2-restoring-assets-without-tasklist) for why that matters.

## Step 4 — First launch

Start the game from Steam. On the first run the loader:

1. restores any previously patched assets,
2. converts every `*.zip` in the mods folder into `*.carra2` (**deleting the original zip**),
3. extracts the mod objects into a temp folder,
4. backs up each targeted `<bundle>/__data` to `__original`, writes the patched `__data`,
5. copies any `*.bank` files over the game's sound banks (keeping `.bank.bak` backups),
6. launches the game and waits for it to exit, then restores everything.

Watch it work:

```bash
tail -f "$PREFIX/drive_c/users/steamuser/AppData/Roaming/LimbusCompanyMods/log.txt"
```

You are looking for `* Patching complete <hash> (<size>) -> <hash> (<size>)` lines. To confirm the
game really started under the loader, check that the log ends with `Starting game` **and** the game
window appears.

> **One-time cache clear.** If this is your first time using *any* mod loader, the upstream advice
> still applies: clear the Addressables cache once so stale patches from previous experiments are
> gone. See [Restoring a clean state](#restoring-a-clean-state) below.

## Step 5 — Install mods

Drop files into `LimbusCompanyMods/` and relaunch. Supported inputs:

| File | Meaning |
| --- | --- |
| `*.zip` | Lunartique format. Converted to `.carra2` on launch, **original zip deleted** |
| `*.carra` | Older already-compressed format |
| `*.carra2` | Current format; what you usually end up with |
| `*.bank` | FMOD sound bank (voice / SFX replacement) |

Keep your own copy of every `.zip` you download — the conversion is irreversible.
Do not put two mods that rewrite the *same bundle* unless you understand the overlay order;
see [doc 4](04-mod-formats.md#overlapping-mods).

## Restoring a clean state

The loader is designed to be reversible:

- **Remove a mod**: move its file out of `LimbusCompanyMods/` and relaunch. Next start, the loader
  restores `__original` over `__data` for every bundle it had patched.
- **Force a full revert**: quit the game, then for each cache bundle directory replace `__data`
  with `__original`:

  ```bash
  for d in "$PREFIX"/drive_c/users/*/AppData/LocalLow/Unity/ProjectMoon_LimbusCompany/*/*/; do
      [ -f "$d/__original" ] && mv -f "$d/__original" "$d/__data"
  done
  ```

  (This is what `patch.cleanup_assets()` does; doing it by hand is the recovery path when a crash
  interrupted the automatic cleanup — see [doc 3](03-troubleshooting.md#stale-cache-a-patched-__data-left-behind).)

- **Sound banks**: the loader leaves `<bank>.bank.bak` next to each replaced bank. Delete the
  patched `.bank`, rename the `.bak` back, or just remove the `.bank` from the mods folder and
  relaunch.

## Verifying your setup without launching the game

Before you trust the launch-options plumbing, you can run the discovery logic by hand:

```bash
cd loader
venv-linux/bin/python -c "
from platform_paths import steam_roots, library_roots, find_game_dir, find_prefix, get_appdata
print('steam roots  :', *steam_roots(), sep='\n  ')
print('libraries    :', *library_roots(), sep='\n  ')
print('game dir     :', find_game_dir())
print('prefix       :', find_prefix())
print('appdata      :', get_appdata())
"
```

If any of these raise `FileNotFoundError`, the message tells you exactly what is missing
(game never launched, prefix absent, Steam not where we looked).
