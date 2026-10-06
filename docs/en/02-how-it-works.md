# 2. How it works, and what the port changed

## The pipeline

The loader never touches the game's install directory for asset mods. Limbus keeps its bundles in
Unity's **Addressables cache**, and the loader patches those cached copies at launch.

```
Steam launch options
  └─ run-linux.sh …main.py %command%
       ├─ cleanup_assets()            restore __original → __data, restore *.bank.bak → *.bank
       ├─ detect_lunartique_mods()    *.zip  →  *.carra2   (zip is deleted)
       ├─ extract_assets()            unzip every *.carra* into a temp dir, flattened
       ├─ patch_assets()              for each cache bundle: back up, graft objects, write back
       ├─ sound.replace_sound()       copy *.bank over the game's sound banks (keep .bak)
       └─ subprocess.call(sys.argv[1:])   run the game, block until it exits
       └─ atexit → cleanup_assets()   restore everything
```

Two details drive most of the porting work:

- **Bundles are matched by hash.** A cache bundle lives at
  `LocalLow/Unity/ProjectMoon_LimbusCompany/<A>/<B>/__data`. A `.carra2` entry is named
  `<A>/<path_id>.<type_id>`, and the loader only ever matches on the **outer** `<A>`. Anything
  under `<A>` in the mod is grafted by `path_id` into the bundle whose folder is named `<A>`.
- **Mods are Windows-agnostic.** The Lunartique `Installation/`+`Uninstallation/` layout, the
  `.carra`/`.carra2` object blobs and the `.bank` files are all plain data. What is *not*
  platform-agnostic is the loader's own path/process handling — that is the entire port.

## What the port changed

`main.py` and `compress.py` are untouched: the core patching logic is pure Python + UnityPy and
runs anywhere. The Windows-specific code lives in exactly three files, which import
`winreg` / read `APPDATA` / call `tasklist`.

### New file: `platform_paths.py`

Replaces every Windows-API lookup with a Linux-aware equivalent.

| Function | Purpose |
| --- | --- |
| `steam_roots()` | Candidate Steam installs, most likely first: Windows registry on Windows; on Linux `~/.steam/steam`, `~/.local/share/Steam`, the Flatpak path, `/usr/share/steam` |
| `library_roots()` | Every Steam library: the roots themselves plus every `"path"` in `libraryfolders.vdf`, de-duplicated |
| `find_game_dir()` | First library containing `steamapps/common/Limbus Company/LimbusCompany.exe`; honours `$LIMBUS_GAME_DIR` |
| `find_prefix()` | `steamapps/compatdata/1973530/pfx` — the Proton prefix |
| `get_appdata()` | `$APPDATA` if set, otherwise the first `pfx/drive_c/users/*/AppData/Roaming` |
| `is_windows()` | `os.name == "nt"` |

The precedence matters: `$APPDATA` wins over prefix detection, so the same code works whether
it runs inside Proton (where `APPDATA` is set) or on the bare host (where it is not).

### Modified files — `loader/linux-port.diff`

```diff
--- a/modfolder.py
+++ b/modfolder.py
 import os
+from platform_paths import get_appdata
 def get_mod_folder():
-    if appdata := os.getenv("APPDATA"):
-        return os.path.join(appdata, "LimbusCompanyMods")
-    else:
-        raise Exception("APPDATA not found")
+    return os.path.join(str(get_appdata()), "LimbusCompanyMods")

--- a/patch.py
+++ b/patch.py
 from compress import compress_lunartique_mod
+from platform_paths import get_appdata
-def bundle_data_paths(appdata: str = os.getenv("APPDATA")):
+def bundle_data_paths(appdata: str | None = None):
+    if appdata is None:
+        appdata = str(get_appdata())
     cache_path = os.path.join(appdata, "../LocalLow/Unity/ProjectMoon_LimbusCompany/*/*/")
     return map(os.path.normpath, glob.glob(cache_path))
@@ patch_bundle_asset
         if not isinstance(f, SerializedFile):
             logging.info("Expected serialized file but got a %s instead?? Skipped", type(f))
-            return
+            continue

--- a/sound.py
+++ b/sound.py
 import time
-import winreg
 from threading import Thread
 from modfolder import get_mod_folder
+from platform_paths import find_game_dir, is_windows
-def get_steam_dir() -> str:
-    ... winreg ...
 def sound_folder() -> str:
-    steam_dir = get_steam_dir()
     return os.path.join(
-        steam_dir,
-        r"steamapps\common\Limbus Company\...\FMODBuilds\Desktop"
+        str(find_game_dir()),
+        "LimbusCompany_Data", "StreamingAssets", "Assets", "Sound", "FMODBuilds", "Desktop",
     )
 def is_game_running() -> bool:
+    if not is_windows():
+        return False
     ...
@@ sound_replace_thread
         shutil.copyfile(sound_file, target)
+    if not is_windows():
+        return
     for _ in range(30): ...
```

### Why each change was necessary

1. **`winreg` → `platform_paths` (fatal, at import time).** `import winreg` raises
   `ModuleNotFoundError` on Linux. Because `sound.py` imports it at module level and `main.py`
   imports `sound`, the loader dies before it patches anything — the only symptom is a log that
   stops right after `Limbus Company` detection.

2. **`APPDATA` → prefix-derived AppData (fatal, silently).** `os.getenv("APPDATA")` returns
   `None` on the host, so `bundle_data_paths()` would do `os.path.join(None, …)` →
   `TypeError`, and `get_mod_folder()` raises `APPDATA not found`. The game itself *does* have an
   `APPDATA` — inside its own prefix — which is why the correct source is
   `pfx/drive_c/users/*/AppData/Roaming`, and why anything you drop in that folder shows up in the
   game.

3. **Hard-coded Windows paths → `os.path.join` component lists.** `r"steamapps\common\…"` is a
   single path segment on Linux. Splitting it into components lets `os.path.join` build a correct
   path on either platform.

4. **`return` → `continue` in `patch_bundle_asset` (latent upstream bug).** When a bundle contains
   more than one serialized file, the original aborts the whole function on the first
   non-`SerializedFile`. We hit this while iterating; the fix is one word. Worth upstreaming.

## 2. Restoring assets without `tasklist`

This is the part that is conceptually different on Linux, not just a path swap.

**Why the polling exists.** `sound_replace_thread()` copies the banks and then, on Windows, watches
for the game to exit by polling `tasklist /FI "IMAGENAME eq LimbusCompany.exe"`; when the process
disappears it restores the sound banks *and* the patched assets. That polling is the only part of
the restore logic that is Windows-specific.

**What replaces it.** The launch option is `"/…/run-linux.sh" %command%`, so `%command%` arrives as
`sys.argv[1:]` and `main.py` calls `subprocess.call(sys.argv[1:])` — which **blocks until the game
exits**. The `atexit` handler then runs `cleanup_assets()`, which restores both `__data` and the
`.bank` files. Same end result, no polling, and nothing depends on a tool that does not exist on
Linux.

That is why the port:

- makes `is_game_running()` return `False` on Linux (the monitor loop is a Windows-only concern),
- and early-returns from the monitor section of `sound_replace_thread` after the copies are done.

The copy itself still happens on both platforms — only the "wait for the game and restore"
tail is Windows-only.

> Consequence: because restoration is driven by the loader process exiting, **killing the loader**
> (or a hard game crash that takes the parent with it) can leave the `__data` patched. That failure
> mode is documented in [doc 3](03-troubleshooting.md#stale-cache-a-patched-__data-left-behind).

## What the port deliberately did *not* do

- **No `main.exe`.** `main.spec` (PyInstaller) and `install_deps.ps1` (PowerShell) are Windows-only
  build tooling. On Linux you run the source from a venv; there is nothing to freeze.
- **No gamescope/sandbox tricks.** The loader runs as a normal user process and Steam handles the
  Proton side. This keeps `stdout` and `log.txt` readable, which is the whole point of porting
  rather than running `main.exe` inside the prefix.
- **No changes to the file formats.** `.carra`, `.carra2` and `.bank` are untouched by the port;
  their quirks are documented separately in [doc 4](04-mod-formats.md).

## Related

- Upstream assumes the loader may also *start* the game on Windows. On Linux, `%command%` is the
  single source of truth for how the game starts — never hard-code `LimbusCompany.exe` anywhere.
- If you add a feature that needs the game directory, use `platform_paths.find_game_dir()` rather
  than re-deriving it; that is the one place Windows/Linux/Flatpak knowledge is allowed to live.
