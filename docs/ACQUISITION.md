# Acquiring and reusing open assets

ATLAS 0.5 ships two working provider adapters. The local SQLite catalog stores source metadata separately from immutable production asset versions. Network use is explicit through sync/download. Rendering from locally available, inspected assets and acquired media uses local files.

| Provider | Implemented source and scope |
|---|---|
| KayKit | Curated, commit-pinned starter members from the official [Adventurers release](https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0/tree/672074b73ba276876a19e8816ecdc5241817ab47) and [Medieval Hexagon release](https://github.com/KayKit-Game-Assets/KayKit-Medieval-Hexagon-Pack-1.0/tree/84fa4e91af6a88989be7c99e0891cede11f2ca38). License text comes from each selected archive. |
| Poly Haven | **Powered by Poly Haven**. Live HDRI and texture catalogs and official 1K file descriptors. Download one .hdr per environment or three JPEG channels per material (diffuse, roughness and OpenGL normal). See [API terms](https://github.com/Poly-Haven/Public-API/blob/master/ToS.md) and [asset license](https://polyhaven.com/license). |

Quaternius publishes [CC0 characters](https://quaternius.com/packs/universalbasecharacters) and compatible animations, but its selected pack uses an interactive download flow. Kenney's [Castle Kit](https://kenney.nl/assets/castle-kit) likewise exposes a website-mediated signed download. Use the documented local ZIP import for compatible files obtained through those interfaces. The [ambientCG API](https://docs.ambientcg.com/api/v2/) is a candidate for a future adapter. OpenGameArt licenses vary by asset. Sketchfab requires its authorized download workflow. MakeHuman/MPFB, Blender Studio and additional sources need format and source-specific license work. Only the first two provider adapters are implemented.

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
