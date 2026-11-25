# Local GLB asset workflow

ATLAS 0.3 adds directory inventory, reviewed batch import and verified thumbnails to local registration, immutable provenance versions, deterministic search, Blender inspection and reusable static GLB instances. Primitive-only schema 1.0 and asset schema 1.1 projects remain supported.

In V0.5.2, `assets select` ranks eligible models and reports rejection reasons. `assets derive-module` selects one named root mesh from an inspected static kit, removes its presentation translation, and registers and inspects the standalone piece. Use `assets import-blendkit` for approved native collections. The `pbr` GLB profile extends static registration with bounded IOR and specular values. [Verification and commands](V052_DEMOS.md)

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

`assets register` copies the bytes into `blobs/<sha256>.glb` and records an immutable `(id, version)` row in SQLite schema 2. Schema 1 migrates transactionally, preserving versions and inspections. IDs and paths are separate. Registering the same latest content/provenance is idempotent. Changing bytes or provenance produces the next version, retaining earlier records. Different IDs can share blob bytes without sharing their permissions. Search returns latest versions in deterministic ID order; `show --version` retrieves a pinned older record.

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

## Reviewed directory batches and previews

`assets scan ROOT --plan PLAN.json` inventories files in sorted relative-path order, recursively by default (`--no-recursive` disables recursion). It never registers files or infers approval, refuses to overwrite an existing plan, and leaves every entry `selected: false`. Each GLB uses an adjacent same-stem `.provenance.json`; the plan records separate hashes of source and metadata. Unsupported files and child links/junctions are reported without being imported or followed. GLBs are limited to 256 MiB, sidecars to 500 KB, plans to 10,000 entries and CLI plan input to 20 MiB.

Review actual provenance and select intended candidates by setting `selected: true`; optionally choose stable IDs. Apply with `assets batch PLAN.json --root ROOT --library LIBRARY`. The explicit root must match the plan, and source/library directories cannot contain each other. A changed source or sidecar requires a rescan. Batch requires explicit approved render rights even for registration; single-file registration can still store an unreviewed record. Editing display metadata in the plan cannot grant rights.

`--inspect` adds Blender inspection; `--thumbnails` adds inspection and preview rendering. `--size 128|256|512` selects a square preview (default 256). Files run sequentially. Corrupt, changed, unsupported or unapproved selected entries fail independently; successful records are retained. JSON stdout includes the durable report location, version/hash, timings and per-entry status. Exit code 2 means partial/failed work. Ctrl+C returns 130 and marks the active entry cancelled; later selected entries remain pending. There is no resume command. A retry is idempotent for registration but reruns requested inspection/thumbnail work.

`assets thumbnail ID --version N --size 256` requires an approved, successfully inspected asset. The packaged worker uses normalized geometry, an orthographic camera, neutral studio lights and CPU Cycles (24 samples, four threads). Readiness checks complete bounded PNG framing, chunk checksums, terminal IEND, dimensions, actual RGB decode and spatial variation; reports bind source/image hashes and profile `atlas-thumbnail-1`. These checks detect corrupt or uniform images, not artistic quality or subject visibility. Failed attempts remain explicit without changing inspection status. Earlier images remain in their unique attempt directories.

New batch/thumbnail staging GLBs are removed after success, failure or cancellation. Deduplicated registry blobs, plans, reports, logs and preview images remain; inspection attempt snapshots and production-job snapshots retain their existing diagnostic/reproducibility behavior. Hard termination can bypass cleanup. Check cleanup errors in reports/logs before manually removing leftover staging files.

### Original mixed collection demonstration

Run the included trusted generator with Blender into a fresh empty directory:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python tools\create_batch_fixture.py -- outputs\my-batch-inputs
.\.venv\Scripts\atlas.exe assets scan outputs\my-batch-inputs --plan outputs\my-batch-plan.json
# Select beacon.glb and crate.glb; set their IDs to beacon and crate.
.\.venv\Scripts\atlas.exe assets batch outputs\my-batch-plan.json --root outputs\my-batch-inputs --library outputs\my-batch-library --thumbnails
.\.venv\Scripts\atlas.exe render examples\06_batch_showcase.json --asset-library outputs\my-batch-library
```

The generator also supplies a duplicate beacon, an unreviewed model, a corrupt GLB and unsupported OBJ for failure testing. Selecting all GLB candidates intentionally produces three successes and two failures. Never approve the deliberately unreviewed entry just to make the report green.

The current scan requires portable filenames; Unix names containing colons/backslashes are rejected. Keep source trees unchanged during scan/apply. Descriptor checks reject special files; containment checks are not an OS sandbox against hostile directory races. Durable reports rewrite the full inventory per processed item; the 10,000-entry cap is a safety bound, not a demonstrated throughput target. Use small collections until larger benchmarks justify an append-only journal or indexing changes.

## Deferred

No network downloads, FBX/OBJ/BLEND/USD input, external texture repair, rig/clip playback, automatic semantic tagging, license revocation UI or asset-pack redistribution. Instances currently import geometry independently; shared mesh caching and large-library performance work are future tasks. Full Phase 2 acceptance with multiple third-party asset packs has not been attempted.

## Official acquisition and rigged assets (0.5)

The source catalog, acquisition cache, production registry and job snapshots are separate. See ACQUISITION for official sources and bounded starter installation. Use CHARACTERS for the rigged GLB profile added alongside the strict static one. V0.5 verifies a single-armature, one-skin, embedded transform-animation profile. Zero-duration poses are reported by the container but excluded from the playable clip list. Examples 09 and 11 demonstrate one versioned static environment collection reused through the CLI.
