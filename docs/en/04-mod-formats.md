# 4. Mod formats & forensics

This document is about **what is inside** the files the loader consumes, and how to inspect them
when something goes wrong. The port did not change any format; this is background for
[doc 3](03-troubleshooting.md).

There are three kinds of artifact in `LimbusCompanyMods/`:

| Artifact | What it is |
| --- | --- |
| `*.zip` | Lunartique "installer" package — a folder tree with `Installation/` and `Uninstallation/` copies of `__data` |
| `*.carra` / `*.carra2` | A compressed **delta**: only the objects that differ from vanilla |
| `*.bank` | FMOD sound bank (event metadata) or `.assets.bank` (sample data) |

---

## `.carra` and `.carra2`

Both are **ZIP archives**, but not the kind you unzip and read:

```
<A>/<path_id>.<type_index>      ← .carra2 entries
<A>/<path_id>                   ← old .carra entries (no type suffix)
```

- `<A>` is the **outer** hash of the target cache bundle. Since `extract_assets()` flattens
  `<A>/<B>/<file>` down to `<A>/<file>`, **`<A>` alone decides which bundle a mod patches**; the
  inner `<B>` is discarded. Advice that tells you to "rename the inner folder" is a no-op here.
- `<type_index>` is an index into **that bundle's own type table** — it is *not* a global type id
  and cannot be translated across bundles. Old `.carra` entries omit it, which makes the loader
  treat it as `-1` and skip the type check.
- Each entry's **content is an XZ stream** (magic `\xfd7zXZ\x00`). Decompressed, it is:

  ```
  u32LE name_length | object name | pad to 4 bytes | raw object bytes
  ```

> **Pitfall — never scan a `.carra*` for strings without decompressing.** The entries are
> LZMA-compressed; scanning the ZIP-entry bytes yields noise. Conclusions like "this pack contains
> no text" must be drawn from the *decompressed object names and payloads*, not the compressed
> bytes. We made exactly this mistake once and had to retract the claim.

### How a `.zip` becomes a `.carra2`

`compress_lunartique_mod()` is a delta encoder:

1. Find the root folder that contains both `Installation/` and `Uninstallation/`.
2. For every object under `Uninstallation/**/__data`, hash its raw bytes (`xxh128`).
3. For the matching object under `Installation/`, write an entry **only if** the bytes differ or
   the object is new.
4. Each written entry is `lzma.compress(data, preset=9, FORMAT_XZ)`.

So a `.carra2` contains only the changed objects — which is also why a broken entry can be deleted
from it (the vanilla object simply stays in place; see
[doc 3](03-troubleshooting.md#the-game-crashes-right-after-launch)).

`detect_lunartique_mods()` performs this conversion at launch and then **deletes the `.zip`**. Keep
your own copy of anything you download.

### Inspecting a `.carra2`

```python
import lzma, struct, zipfile

with zipfile.ZipFile("mod.carra2") as z:
    for entry in z.namelist():
        bundle_hash, _, rest = entry.partition("/")
        pid, _, type_idx = rest.partition(".")
        raw = lzma.decompress(z.read(entry))          # FORMAT_XZ
        n = struct.unpack_from("<I", raw, 0)[0]
        name = raw[4:4 + n].split(b"\x00")[0].decode("utf8", "replace")
        print(f"{bundle_hash[:8]}  pid={pid:<8} type={type_idx or '-':<3} len={len(raw):>9}  {name}")
```

Reading the object name this way is the fastest way to see what a pack actually touches — the names
are the game's own asset names (`idle`, `skill3_10`, `10812_normal_profile`, `sactx-0-2048x2048-…`).

## Overlapping mods

Several mods can target the same bundle; they are applied in the order the loader sees them
(`sorted(..., key=mod_file_size, reverse=True)` — **largest file first**). Later grafts (smaller
files) overwrite earlier ones when they carry the same `path_id`.

Two consequences worth knowing:

- A mod that touches only a few objects is effectively a patch *on top of* a bigger one; the bigger
  pack's other objects survive.
- Two packs that both rewrite the *same* object cannot coexist — one silently wins, and which one
  is decided by file size, not by name.

In practice the useful strategy is to **combine the best parts of each pack** rather than installing
one wholesale: take the newer/better assets from one and leave objects the other does not
override. If a pack crashes because of one bad object (an incompatible type tree, say), dropping
just that entry lets the rest of the pack coexist with everything else.

## Anatomy of an appearance pack

A character skin pack is not "just textures". A typical one contains:

- **Sprites / Texture2D / SpriteRenderer** plus `SpriteAtlas` data (`<name>` and `<name>.atlas`) —
  the illustrations.
- **AnimationClip** (`*_Default` idle, `*_Move`) and a **PlayableDirector** timeline — the idle
  illustration is **cut frame-by-frame by an AnimationClip on a Timeline**, not a single static
  image. This is why "just change the idle art" inevitably drags in sprites, atlases, clips,
  directors and Transforms, and looks like it also changed the animations.
- **Transform**s — the pack's own skeleton/attachment points.
- A **character appearance-controller MonoBehaviour** that also holds the ultimate ("special
  skill") effect hooks: `spEffects` (PPtr list to effect objects), `spSkillReadyEffect` /
  `spSkillReadyEffect_Burn`, `OverrideDeadTimeline`, plus appearance fields such as
  `material_Current` / `material_Future`, `OverrideSprite` and `afterimageTrails`.

That last item is the usual crash candidate when a pack is old: the controller's **type tree** may
have gained fields since the pack was exported. See
[doc 3, cause 3](03-troubleshooting.md#3-monobehaviour-type-tree-missing-fields).

## Where text and font colour live (and why nobody ships a colour mod)

In-game dialogue is drawn by **TextMeshPro**, using a `Font` asset and a `Material` at runtime.
Text colour can therefore come from exactly two places:

1. **Rich-text tags inside the string itself** — `<color=#RRGGBB>` embedded in the localization
   text, which lives in a `TextAsset` (the localisation table), and
2. the **`Font`/`Material` default colour and outline**.

Neither lives in a voice bank, and neither lives in an appearance pack — which is why packs
shipping altered art do not change dialogue colour. To ship a colour mod you would have to either

- change the global `Font`/`Material` (affecting **all** text and UI, rarely desirable), or
- embed per-line `<color=…>` tags in the localisation table (very many strings, and fragile across
  game updates).

That cost is why colour changes are usually a local/private tweak rather than a published mod.

## Sound banks

A mod sound file is dropped into `FMODBuilds/Desktop/`. FMOD splits each bank into two files:

- `<name>.bank` — event metadata (RIFF `FEV FMT` container),
- `<name>.assets.bank` — the sample data (`FSB5` chunks).

Both are RIFF containers that may hold **more than one `FSB5` chunk**. Voice banks are organised by
**season/content unit**, not per character — a single `Voice_Default_<S><part>.assets.bank` mixes
many speakers, which is why "Ryoshu's bank also contains four other people".

### Reading an FSB5

`FSB5` header layout (little-endian; 60-byte header, `0x3C`):

```
'FSB5' | version | numSamples | sampleHeaderSize | nameTableSize | dataSize | mode | hash…
```

The name table starts at `offset + 60 + sampleHeaderSize` and is `nameTableSize` bytes long. The
`mode` field identifies the codec — `15` = Vorbis, `16` = FADPCM.

**Tooling gotcha.** `ffmpeg`'s `fsb` demuxer only supports up to **FSB4** and will fail on FSB5,
even the build bundled in the Flatpak GNOME runtime. Use **vgmstream-cli** instead
(`-i` to list names/codecs, `-S 0` to dump everything).

### Comparing an original bank with a modded one

Two orthogonal measurements, and you need both:

- **Waveform correlation, time-normalised** → tells you whether the *timbre* (the voice) changed.
- **Envelope correlation** → tells you whether the *rhythm/pacing* changed.

Normalise duration **before** correlating. A few milliseconds of length difference will drag a
waveform correlation from ~1.0 down to ~0.6 and produce a false "it changed" verdict.

```python
import numpy as np

def resample(a, n=4096):
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)

def ncc(a, b):
    a = resample(a); b = resample(b)
    a = a - a.mean(); b = b - b.mean()
    denom = float((a * a).sum()) * float((b * b).sum())
    return float((a * b).sum()) / np.sqrt(denom) if denom > 0 else 0.0
```

Interpretation: waveform ≈ 1.0 → same recording (possibly re-encoded); waveform low but envelope
high → same take, different voice/speaker; both low → a different recording.

Finally, validate that you are comparing like with like: the modded and vanilla banks must have the
**same index → name mapping**. If names are missing or shifted, every per-name comparison is
meaningless.
