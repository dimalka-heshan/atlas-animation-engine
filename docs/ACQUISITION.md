# Acquiring and reusing open assets

The local SQLite catalog stores source metadata separately from immutable production asset versions. Network use is explicit through sync/download. Rendering from locally available, inspected assets and acquired media uses local files. The [high-fidelity source guide](HIGH_FIDELITY_SOURCES.md) covers the 0.5.1 Poly Haven model expansion, ambientCG materials and the curated Smithsonian derivative.

V0.5.2 adds `assets variants` and `--resolution auto` for Poly Haven. `ATLAS_ASSET_CACHE_MIB` controls the content-addressed source cache, with a 5120 MiB default. The per-acquisition `--budget-mib` limit still controls transfers. [Sketchfab OAuth setup](SKETCHFAB.md) · [Blendkit official add-on and import](BLENDKIT.md) · [V0.5.2 acquisition commands](V052_DEMOS.md)

| Provider | Implemented source and scope |
|---|---|
| KayKit | Curated, commit-pinned starter members from the official [Adventurers release](https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0/tree/672074b73ba276876a19e8816ecdc5241817ab47) and [Medieval Hexagon release](https://github.com/KayKit-Game-Assets/KayKit-Medieval-Hexagon-Pack-1.0/tree/84fa4e91af6a88989be7c99e0891cede11f2ca38). License text comes from each selected archive. |
| Poly Haven | **Powered by Poly Haven**. Live models, HDRIs and textures with 1K, 2K and 4K derivatives where available. See [API terms](https://github.com/Poly-Haven/Public-API/blob/master/ToS.md) and [asset license](https://polyhaven.com/license). |
| ambientCG | API v3 PBR texture sets in JPEG and PNG. See the [high-fidelity guide](HIGH_FIDELITY_SOURCES.md). |
| Smithsonian Open Access | Reviewed CC0 Rococo chair with a pinned static GLB derivative. See the [high-fidelity guide](HIGH_FIDELITY_SOURCES.md). |

Quaternius and Kenney starter packs may be imported through the documented local ZIP workflow after obtaining and checking the exact assets. OpenGameArt and Blender Studio assets have source-specific terms. MPFB is installed through the [character generation workflow](V051_DEMOS.md).

## Starter acquisition

Examples use PowerShell from the repository root. Change the cache and library paths if needed. Commands default to a 64 MiB maximum per archive or requested media set. These are serialized downloads with provider-host validation, bounded responses and a content-addressed cache. There is no automatic resume of a partially transferred file. The live catalog is refreshed provider by provider in SQLite. Search is exact metadata term matching with style/category constraints and optional deterministic seed ranking.

```powershell
$python = '.\.venv\Scripts\python.exe'
$cache = 'outputs/v05-acquisition'
$library = 'outputs/v05-library'
& $python -m apps.cli assets providers
& $python -m apps.cli assets sync kaykit --cache $cache
& $python -m apps.cli assets sync polyhaven --cache $cache
& $python -m apps.cli assets catalog 'medieval' --category environment --style stylized-low-poly --seed 24 --limit 10 --cache $cache
& $python -m apps.cli assets download-pack adventurers --cache $cache --library $library
& $python -m apps.cli assets download-pack medieval --cache $cache --library $library
$objects = 'knight','mage','fence','gate','wall','tavern','tree','rock','barrel','crate','cart','bridge'
foreach ($item in $objects) {
  & $python -m apps.cli assets inspect "kaykit-$item" --version 1 --library $library
}
$media = 'studio_small_03','aerodynamics_workshop','aerial_grass_rock','brick_wall_001','wood_floor','cobblestone_floor_01','rocks_ground_04'
foreach ($item in $media) {
  & $python -m apps.cli assets download "polyhaven-$item" --cache $cache
}
& $python -m apps.cli assets storage --cache $cache
& $python -m apps.cli assets licenses --library $library
& $python -m apps.cli assets normalize kaykit-knight --version 1 --library $library
& $python -m apps.cli assets thumbnail kaykit-mage --version 1 --size 128 --library $library
```

The catalog is a lightweight index, with 12 reviewed KayKit starter entries and live Poly Haven texture/HDRI metadata. Downloaded entries do not imply successful Blender inspection. A local registry version retains the source revision, archive SHA256, creator and verbatim license text. Media records retain the API's size/checksum, SHA256 and channel fingerprint. Pin the fingerprint from acquisition in schema 1.3 when using HDRI or ground materials. If official files change, validate the new fingerprint and update the example explicitly.

## Manual archive workflow

```powershell
& $python -m apps.cli assets import-archive C:\Downloads\pack.zip --member 'Folder/Model.gltf' --id local-model --provenance C:\Downloads\model.provenance.json --library $library
& $python -m apps.cli assets inspect local-model --version 1 --library $library
```

Use the existing approved provenance schema. Supply the precise archive member with portable slash-separated paths. ZIP validation rejects traversal, links, encrypted entries, scripts/executables and inflated data beyond the limits. The process reads the selected model and its allowed dependencies without extracting arbitrary files. GLB can be registered directly. External glTF derivation currently embeds a single same-directory BIN plus same-directory PNG/JPEG images, then applies the existing GLB importer profile. External URIs, multi-buffer glTF, FBX, OBJ, imported BLEND and USD are outside the production profiles. Malformed inputs fail before Blender or on isolated Blender inspection. Blender runs with factory settings and disabled auto-execution; its importer is not an OS sandbox.

Never commit the large archives, source media or rendered videos. The acquisition cache retains originals. Production GLB derivatives and job-local media are separately checked and preserved. Cleanup/recovery policy is manual. Preserve the cache and library when you need to rerender pinned examples.
