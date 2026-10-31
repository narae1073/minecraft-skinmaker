# Reference pattern pack

The renderer can learn style primitives from user-provided Minecraft skins without
copying whole skins. The derived pack is `assets/reference_pack.json` (about 22 KB).

## Corpus

- 218 long-hair, 319 short-hair skins.
- 100 hood-up, 11 hood-down skins.
- 34 hat/cap skins — **excluded** from the current hood/hair pack.
- All references are 64×64 PNGs; raw skins stay in gitignored `out/reference_skins/`.

## What is stored

- `hair.short` / `hair.long`: 6 derived L2 tone maps per length (five head faces).
  Values are percentages of the reference face median luma; the renderer damps
  them and uses column averages so they read as strands, not block patches.
- `eyes`: 3 mirrored eye templates (2×8 sclera/iris masks).
- `hoods.up`: 4 canonical L2 head masks.
- `hoods.down`: 2 L2 body cowl masks.
- No raw reference skin is stored; the pack only holds derived masks/tone maps.
- License/provenance is recorded in the pack header; the user confirmed the
  reference set may be used for this derived pack.

## Rebuild

```bash
.venv/bin/python scripts/build_reference_pack.py \
  --refs out/reference_skins \
  --out assets/reference_pack.json
```

`build_reference_pack.py` uses only 64×64 PNGs under the labelled folders. Hat
folders are ignored. The renderer falls back to its previous hair/eye behaviour
if the pack is absent.

## Limits

- The references are **unpaired**: they teach patterns, not a photo→skin mapping.
  Style selection still uses the photo measurements/VLM.
- The corpus is heavily anime/costume; eye/hood patterns are a first approximation.
- The pack is deterministic, not a trained model. A learned model would need a
  larger paired corpus.
