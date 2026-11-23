# Local GLB asset workflow

ATLAS 0.2 adds the first Phase 2 slice: explicit local registration, immutable provenance versions, deterministic search, real Blender inspection, and reusable static GLB instances in schema 1.1 projects. Primitive-only schema 1.0 projects remain supported.

## Try the bundled original fixture

The committed `assets/fixtures/lantern.glb` is generated entirely from local primitive geometry. It contains no downloaded asset or texture. Its sidecar identifies the source generator and the rendering permission for this project. The `assets/library/` registry is local state and is ignored by Git.

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\atlas.exe assets register assets\fixtures\lantern.glb --id lantern --provenance assets\fixtures\lantern.provenance.json
.\.venv\Scripts\atlas.exe assets inspect lantern --version 1
.\.venv\Scripts\atlas.exe assets search --tag lantern
.\.venv\Scripts\atlas.exe assets show lantern --version 1
.\.venv\Scripts\atlas.exe validate examples\04_lantern_studio.json
.\.venv\Scripts\atlas.exe render examples\04_lantern_studio.json
.\.venv\Scripts\atlas.exe render examples\05_lantern_courtyard.json
```

Each asset subcommand accepts `--library PATH`. Project commands accept `--asset-library PATH`; default is `assets/library` relative to the working directory. The path is supplied by the operator, never by the scene specification. Searching an absent library returns an empty list without creating it.

## Register your own static GLB

Provide an existing local `.glb` and a provenance JSON. Required metadata: `name`, `creator`, `source_url`, `license_id`, `license_text`. Optional metadata includes `description`, `category`, `tags`, `attribution`, `restrictions`, approval and explicit rendering/redistribution permissions.

Approval defaults to `unreviewed`; both permissions default to false. Registration can store unreviewed provenance but inspection, validation and rendering reject it. To use an asset, its record must have `approval: "approved"`, `render_allowed: true`, non-empty creator/source/license text, and a supported license ID. `CC-BY-4.0` also requires a non-empty attribution statement. Any additional restriction currently blocks use because this release cannot evaluate restricted usage policies.

Supported policy identifiers are `CC0-1.0`, `CC-BY-4.0` and the project-local `LicenseRef-ATLAS-Generated`. These checks enforce declared permission; they do not independently establish ownership, authenticate a license or interpret its legal terms. Do not label someone else's work as generated, CC0 or approved. Preserve the actual license text and attribution from the source.

No license is automatically inferred from a filename, a site, a free download, or the GLB format. `redistribution_allowed` is tracked but ATLAS has no publishing/export-library command that grants redistribution. Job snapshots remain local production artifacts.

## Versions and content integrity

`assets register` copies the bytes once into `blobs/<sha256>.glb` and records an immutable `(id, version)` row in SQLite schema 1. IDs and paths are separate. Registering the same latest content/provenance is idempotent. Changing bytes or provenance produces the next version, retaining earlier records. Different IDs can share blob bytes without sharing their permissions. Search returns latest versions in deterministic ID order; `show --version` retrieves a pinned older record.

Search supports literal case-insensitive `--query`, case-insensitive `--tag`, exact `--category` and `--license` filters. There is no cloud/embedding search. The implementation favors correctness for modest local collections; it is not yet indexed for very large tag searches.

Before inspection or rendering, ATLAS checks rights, blob existence, SHA-256 and supported GLB structure. Missing or changed files fail with a diagnostic. Never manually edit a blob: register changed content as a new version. Unknown database versions and unversioned nonempty databases are rejected rather than overwritten. Registry/database and blob operations are not a single cross-filesystem transaction: a crash can leave an unreferenced blob; it cannot make a half-written blob a successful registered version.

## Inspection and instantiation

The inspection command invokes Blender with factory settings and script auto-execution disabled. It uses a copied/hash-checked source and stores bounds, dimensions, mesh/material/texture counts, polygon count, missing texture information, import timing and Blender version. Bounds use actual world-transformed vertices, including for rotated non-box meshes. Failed imports retain a log and `failed` status. Production requires `ready` inspection with a matching content hash, current inspection profile, positive mesh/polygon counts and valid bounds, and rechecks the source content hash. Reports from earlier inspection profiles require reinspection.

Use an asset entity instead of a primitive entity:

```json
{
  "id": "hero",
  "asset": {"id": "lantern", "version": 1},
  "normalize": "unit",
  "pivot": "base",
  "location": [0, 0, 0],
  "scale": [3.5, 3.5, 3.5],
  "keyframes": [
    {"frame": 1, "rotation": [0, 0, 0]},
    {"frame": 48, "rotation": [0, 0, 90]}
  ]
}
```

The project must declare `schema_version: "1.1"`. Asset references pin a positive integer version; no source file path belongs in project JSON. An entity cannot simultaneously specify primitive/material overrides and an asset. Imported materials and hierarchy are preserved.

`normalize: "unit"` makes the longest aggregate dimension one meter before the entity's scale. `none` preserves original dimensions. `pivot: "base"` centers X/Y and moves the aggregate minimum Z to zero; `center` centers all axes; `origin` preserves the source origin. Blender's glTF importer converts coordinate systems; inspection bounds are world-space Z-up meters. A separate normalization parent preserves imported local transforms, and the public root receives the entity's animation. Asset references are also accepted as scatter prototypes.

Each render copies the approved blobs into its job directory, checks the copies, stores an `asset-map.json`, and embeds every pinned record and inspection report in `manifest.json`. It writes `attributions.txt` for the sources used. A `.blend` contains the imported meshes/materials. This is a source snapshot, not an automatic portable library installer.

## Supported input boundary

Only static GLB 2.0 with embedded BIN/bufferView resources and triangle-surface primitives is currently supported. Maximum file size: 256 MiB; JSON chunk: 8 MiB. External file/HTTP/data URIs, all glTF extensions, skins, animations and morph targets are rejected. Files must contain one scene with all nodes reachable from its roots; multiple scenes, unused nodes, invalid references and non-tree graphs are rejected. Imported object types are limited to meshes and empties. Embedded PNG/JPEG textures are supported; invalid texture references and failed/missing textures prevent use. A conservative container check precedes Blender; Blender remains responsible for deeper geometry validation.

The boundary follows the [Khronos GLB specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html) and the tested [Blender 5.2 importer API](https://docs.blender.org/api/5.2/bpy.ops.import_scene.html). It deliberately supports less than the full format. Asset parsing is not an OS sandbox, and executable paths/library contents remain operator-controlled.

## Deferred

No network downloads, directory scanning, FBX/OBJ/BLEND/USD input, external texture repair, thumbnail generation, rig/clip playback, automatic semantic tagging, license revocation UI or asset-pack redistribution. Instances currently import geometry independently; shared mesh caching and large-library performance work are future tasks. Full Phase 2 acceptance with multiple third-party asset packs has not been attempted.
