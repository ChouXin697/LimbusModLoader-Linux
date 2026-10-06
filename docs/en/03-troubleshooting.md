# 3. Troubleshooting

Every problem below is one we actually hit. Each entry starts with the **symptom**, then the
diagnosis, then the fix — in that order, because the symptom is what you will have in hand.

## Where to look first

| File | Contains |
| --- | --- |
| `<AppData>/Roaming/LimbusCompanyMods/log.txt` | Everything the loader does: conversion, extraction, per-object patching, digests |
| `<AppData>/LocalLow/ProjectMoon/LimbusCompany/Player.log` | Unity/game-side errors and the crash trace |
| `<AppData>/LocalLow/Unity/ProjectMoon_LimbusCompany/<A>/<B>/` | The cache bundles: `__data` (live) and `__original` (pre-patch backup, present only while patched) |

`<AppData>` here means
`<library>/steamapps/compatdata/1973530/pfx/drive_c/users/steamuser/AppData`.

Two habits that save a lot of time:

- Always `tail -f log.txt` in a second terminal for your first few launches.
- When the game crashes, read **the end** of `Player.log` first — the last `Crash!!!` block names
  the exact bundle that failed.

---

## The loader does nothing / exits immediately

### `ModuleNotFoundError: No module named 'winreg'`

**Symptom.** `log.txt` ends right after `Limbus Company` detection, or Steam flashes a console that
vanishes. Running `venv-linux/bin/python main.py` by hand shows the traceback.

**Cause.** You are running the **upstream** source. `sound.py` imports `winreg` at module level and
`main.py` imports `sound`, so the failure happens before any patching.

**Fix.** Use the ported files in `loader/`. The `winreg` import is gone; `sound.py` now imports
`find_game_dir, is_windows` from `platform_paths`.

### `Exception: APPDATA not found` or `TypeError: ... NoneType` in `bundle_data_paths`

**Symptom.** Loader starts, then dies as soon as it tries to find the mods folder or the cache.

**Cause.** Upstream reads `os.getenv("APPDATA")`, which is unset on the host. The game's AppData
lives *inside the Proton prefix*, not in the host environment.

**Fix.** Same as above — the port derives AppData from the prefix. You can also set it explicitly
if you run the loader by hand:

```bash
APPDATA="$PREFIX/drive_c/users/steamuser/AppData/Roaming" venv-linux/bin/python main.py echo
```

### Launch options look right but Steam starts a bare console and no game

**Symptom.** A terminal window appears and closes; the game never launches.

**Cause.** `%command%` was omitted, so `main.py` has no command to run (`len(sys.argv) < 2` → exit
1), or the script path is not quoted/executable.

**Fix.** Check, in order:

```bash
chmod +x loader/run-linux.sh          # must be executable
# Launch Options value, exactly:
"/abs/path/to/loader/run-linux.sh" %command%
```

Then verify by hand that the script can see its venv:

```bash
echo "/abs/path/to/loader/run-linux.sh" && ls -l loader/venv-linux/bin/python
```

### Game launches but mods are ignored

**Symptom.** Game runs, `log.txt` shows patching, but nothing changed in-game.

This is almost always the **silent no-op** case — the mod targets a bundle hash that no longer
exists. See [Mod installed but nothing changed](#mod-installed-but-nothing-changed-silent-no-op).

---

## The start button does nothing

**Symptom.** The game opens, all other buttons respond, but **Start** (开始) appears dead.

This is **not a mod problem**, and it is the single most commonly misattributed failure.

**Diagnose.**

```bash
tail -50 "$PREFIX/drive_c/users/steamuser/AppData/LocalLow/ProjectMoon/LimbusCompany/Player.log"
```

If you see it repeatedly printing `Not Initialize Addressable`, the Addressables system failed to
initialise. That is a **network** problem, not a patching one. Confirm:

```bash
# resolves fine, but 443/80 time out => the CDN is unreachable from your network
getent hosts download.limbuscompanycdn.org
curl -sS -m 5 -o /dev/null -w '%{http_code}\n' https://download.limbuscompanycdn.org
```

**Cause.** `StreamingAssets/aa/settings.json` has `m_DisableCatalogUpdateOnStart = false`, so the
game pulls a remote catalog **on every launch**. If
`LocalLow/ProjectMoon/LimbusCompany/com.unity.addressables/` is missing (no local fallback) and the
CDN is unreachable, Addressables initialisation fails and the Start button's click handler never
completes.

**Fix.** Make `download.limbuscompanycdn.org` reachable. A VPN is required — and it must be in
**TUN / global mode**, because the game runs inside Proton and **cannot see Linux `http_proxy`
environment variables**. Changing DNS alone does nothing. Because the check happens on every
launch, the VPN must be up every time; once it succeeds, the local cache directory is rebuilt.

---

## Stale cache: a patched `__data` left behind

**Symptom.** Mods appear applied even though you removed them; or a "clean baseline" comparison
gives absurd numbers (e.g. you conclude a mod changed only a handful of objects when it plainly
changed hundreds).

**Cause.** `patch.py` moves `__data` → `__original` and writes a patched `__data`, then restores
on exit. If the game is force-killed, or the loader's cleanup is interrupted at launch, the cache
is left in the **patched** state **with `__original` still present**. Any diff taken against the
current `__data` is then against a polluted baseline.

**Diagnose.** For each cache bundle directory:

- Does `__original` still exist? (It should not, outside a patched run.)
- Is `__data` conspicuously larger than expected?

**Fix.** Move the polluted `__data` aside and restore the real original:

```bash
for d in "$PREFIX"/drive_c/users/*/AppData/LocalLow/Unity/ProjectMoon_LimbusCompany/*/*/; do
    if [ -f "$d/__original" ]; then
        mv -f "$d/__data" "$d/__data.polluted.bak"
        mv -f "$d/__original" "$d/__data"
    fi
done
```

Next launch patches from a genuinely clean baseline. For any comparison you intend to trust,
also keep a **known-good original** (a fresh re-download or a pristine backup) as the reference —
`__original` is convenient but only trustworthy if the previous run exited cleanly.

---

## The game crashes right after launch

**Symptom.** Game starts (or crashes while loading a battle / a character), `Player.log` ends with
a `Crash!!!` block. Typical signature:

```
The image data of Texture '<name>' has an unexpected size (expected N, got 0)
The file 'archive:/CAB-<hash>/CAB-<hash>' is corrupted!
[Position out of bounds!]
```

Three distinct root causes all produce this family of messages. Identify which one you have:

### 1. Stale bundle hash (mod points at a bundle that no longer exists)

Not a crash, but listed here for contrast — it produces `log.txt` lines about the bundle simply not
being found, and an unchanged game. See the next section.

### 2. Old serialization layout (the payload is byte-incompatible)

**Diagnose.** For a `Texture2D` entry inside the mod, decompress it (`lzma.decompress(data,
format=FORMAT_XZ)`) and compare the triple right after `m_Name` — `[m_ForcedFallbackFormat,
m_Width, m_Height]` — with the **vanilla** object of the same `path_id`:

- identical → layout is compatible;
- **shifted by one int** → the mod was exported against an older Unity/game layout. Do **not**
  install it; retargeting will not help.

Mods built in 2024 are the common offenders; mods rebuilt against the current build match
field-for-field.

**Fix.** Remove the mod (move the file out of `LimbusCompanyMods/`) and relaunch — the cache
self-heals from `__original`.

### 3. MonoBehaviour type tree missing fields

**Diagnose.** The node index and `path_id` "match", so the loader happily grafts the object — but
the object was exported against an **older type tree**. Example: an appearance-controller script
with 58 fields / 276 B versus the current game's 64 fields / 340 B (a season update added
`spEffects: vector<PPtr<GameObject>>`, 5 elements = 64 B). The game then reads past the end of the
object and crashes with the same `corrupted! [Position out of bounds!]`.

**A matching type index is not proof of compatibility.** Compare the type trees: for every type
index the mod uses, walk `serialized_file.types[idx].nodes` (recursing into `m_Children`) and
compare the vanilla vs modded node strings. A single differing index is enough to crash one object.

A quicker check is to read every object in the **grafted** bundle and report failures:

```python
for path_id, obj in serialized_file.objects.items():
    try:
        obj.read()
    except Exception as e:
        print("unreadable", path_id, e)   # e.g. EOFError: read_length out of bounds
```

Objects that read fine in the mod's own bundle but fail after grafting are the incompatible ones.

**Fix.** Delete that entry from the `.carra2` (keeping the vanilla object). Lowest-risk, fully
reversible, and in the case above a zero-loss change.

### 4. Streamed texture pointing at a missing `.resS`

**Diagnose.** A `Texture2D` (class 28) with a non-empty `m_StreamData.path` stores its pixels in an
external `archive:/CAB-xxx/….resS`. `.carra2` carries **only the object's raw bytes** — it cannot
carry the external `.resS`. If the streamed slice's `offset + size` falls outside the target
bundle's own `resS`, or the referenced resS simply is not in the package, the grafted bundle
becomes corrupt.

Check before converting: read every `Texture2D`'s `m_StreamData` and compare against the length of
the `*.resS` entries actually present in the package. If the texture is **inlined**
(`m_StreamData.size == 0` and non-empty `m_ImageData`), it is safe.

**Fix.** Two options, in order of preference:

1. **Drop the broken entry** if it is a *modified* object with a self-consistent vanilla
   counterpart of the same `path_id` — the game keeps the original texture and everything else
   still applies. (Useless if the bad texture is a *new* object: there is nothing to fall back to.)
2. **Find a build where the texture is inlined.** Same artwork, different export — a mod whose
   texture lives in `m_ImageData` carries fully inside the `.carra2`.

This is a *missing asset* problem, not a *format* problem — the two are independent and can
co-occur.

### Locating which mod caused a crash

1. Take the `CAB-<hash>` name from the last `Crash!!!` block in `Player.log`.
2. Search the cache for it to find the bundle folder:

   ```bash
   grep -rl "CAB-<hash>" "$PREFIX"/drive_c/users/*/AppData/LocalLow/Unity/ProjectMoon_LimbusCompany/ 2>/dev/null
   ```

3. The bundle folder name (`<A>`) tells you which mod's entries targeted it — every `.carra2` entry
   is prefixed with exactly that `<A>`.

---

## Mod installed but nothing changed (silent no-op)

**Symptom.** No crash. `log.txt` shows the mod extracted, but no `Patching`/`Loading` lines for its
objects — or patching runs and the game is visibly unchanged.

**Cause.** Old mods from third-party sites hard-code the target bundle hash `<A>` as it was when
the mod was made. The game **recomputes bundle hashes on update**, so `<A>` no longer matches any
cache folder. The loader matches on `<A>` only, so it finds no bundle and does nothing.

**Diagnose.** Search the whole cache for the mod's target by `path_id` (stable across versions),
not by hash:

```bash
grep -rl "<path_id>" "$PREFIX"/drive_c/users/*/AppData/LocalLow/Unity/ProjectMoon_LimbusCompany/*/*/__data
```

**Fix.** Retarget: rewrite `<A>` inside the `.carra2` to the folder name that actually contains the
target bundle. Note that the *inner* `<B>` is irrelevant — the loader flattens
`<A>/<B>/<file>` to `<A>/<file>` and only ever keys on `<A>`.

Caveats:

- Resources the game rebuilt (e.g. `sactx` atlas pages) may have **new** `path_id`s. Map those by
  object name (minus the trailing hash suffix) plus dimensions, 1:1; if the dimensions differ, skip
  it rather than forcing a match.
- Old-format `.carra` entries have no `.<type_id>` suffix, so the loader treats `type_id` as `-1`
  and skips the type check, replacing purely on `path_id`.

---

## Sound mods

**Symptom.** A `.bank` was placed in the mods folder but the audio is unchanged.

**Checks.**

1. `log.txt` should contain
   `Replacing <file>` for each bank, and the file should exist in
   `$GAME/LimbusCompany_Data/StreamingAssets/Assets/Sound/FMODBuilds/Desktop/`.
2. Compare timestamps: everything in that folder except the bank you replaced should have the
   **original** install date. If several files look fresh, something else is going on.
3. Only one modded version of a given `.bank` can be in effect at a time — two `.bank` mods with
   the same base name overwrite each other.

**Restore.** Delete the patched `.bank` and rename its `.bank.bak` back; or remove the `.bank` from
`LimbusCompanyMods/` and relaunch.

> Analysing *what* a bank changed (which lines, which speakers) is a separate topic with its own
> tooling gotchas — see [doc 4](04-mod-formats.md#sound-banks).
