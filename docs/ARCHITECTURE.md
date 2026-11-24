# Architecture

## Implemented flow

`apps/cli` loads JSON -> `engine/core/models.py` validates a Project -> `engine/worlds/placement.py` expands deterministic scatter -> `engine/rendering/pipeline.py` persists a job and calls the Blender worker -> `engine/rendering/video.py` encodes and checks the result -> `engine/storage/jobs.py` records status and atomically writes the manifest.

The host runs Python/Pydantic; Blender runs trusted stdlib + bpy entrypoints. Blender needs no pip packages. Portable models never import bpy. No generated script or expression from project JSON is executed. Adding a future renderer can consume `resolved.json` and pinned asset snapshots without changing the IR; the current production orchestrator explicitly supports Blender only.

## Public interfaces

- `Project.model_validate(data)` / `Project.model_validate_json(text)`: version 1.0 typed input; unknown fields are errors. `Project.model_json_schema()` provides editor/tool validation schema.
- `expand_project(project: Project) -> Project`: independent validated copy with scatter expanded and removed.
- `render_project(project: Project, output_root: Path, *, blender=None, ffmpeg=None, ffprobe=None) -> Path`: fresh production job; returns a verified MP4 path or raises an actionable error. Tool overrides are trusted executable paths.
- `verify_video(path: Path, settings: RenderSettings, ffprobe: Path) -> dict`: ffprobe dimensions, decoded frame count, duration, codec, pixel format and fps checks.
- `JobStore(path)`: transactional `create`, `update`, `list`; no persistent connections.
- `atomic_json(path, data)`: same-filesystem temporary write, fsync and atomic replacement.

## IR v1.0 and v1.1

A project has `schema_version`, a safe stable `id`, `seed`, `scene`, and `render`. A scene contains explicit entities, scatter groups, environment, camera and lights. Schema 1.0 remains primitive-only; 1.1 additionally accepts `AssetEntity` with an `AssetReference(id, version)`, pivot and normalization policy. Primitive and asset fields are mutually exclusive. This release has one scene and one camera per project; later schema changes must be versioned rather than silently reinterpreting existing fields.

All positions use meters and right-handed Z-up. Rotations are Euler XYZ degrees, interpolated as Euler values; shortest-path quaternion interpolation and rig animation are deferred. Numeric inputs must be finite, non-boolean numbers within +/-1e9 and any tighter field bounds. Timing uses integer frames with integer fps. Resolution is independently configurable for landscape, portrait or square.

Primitive sizes before scale: cube 2x2x2; sphere radius 1; cylinder radius 1 and depth 2; cone base radius 1 and depth 2; plane 2x2; torus major radius 1 and tube radius 0.25. Origins are at primitive centers. Object scale is applied in local space. Bevel width is local-space and supported for cubes/cylinders. Smooth shading is supported for spheres and tori.

Materials expose linear RGB color, roughness and metallic. Environment exposes background RGB/strength and an optional ground plane at Z=0. AREA/SUN/POINT lights expose energy and color; energy follows Blender units (SUN differs from watts), and `size` controls AREA size or POINT soft radius. SUN size is currently unused.

Camera supports focal length, position keys, fixed point or entity tracking, and optional depth of field. Tracking uses negative camera Z and Y up. Perspective clipping ends at 10000 m. Render reports flag frames with no entity centers inside the frustum; this is a limited diagnostic, not occlusion detection or artistic approval.

Scatter derives one RNG from the project seed and group ID. It tries up to 1000 positions per object and rejects exhausted placement. Scale and Z height vary together; yaw is randomized. Minimum spacing applies only to centers within that group. Large groups can be expensive (pairwise rejection); 10000 total scene entities are the hard safety limit.

## Execution boundary

Blender launches with factory settings, disabled auto-execution and nonzero Python error exit codes. Workers are package-owned and accept validated IR or a host-prepared asset inspection request. Project fields can reference approved registry IDs/versions but cannot select scripts, command arguments, input file paths or output paths. All command invocations use argument arrays with shell execution disabled. Tool paths from the CLI/environment are administrator-controlled configuration.

Output roots are explicitly selected through the CLI/API. Unique UUID child directories and resolved containment checks prevent ordinary configuration path traversal. Directory creation and path checks are not a sandbox against a separate hostile process racing filesystem changes. The application runs with the user's OS permissions.

Encoding uses a fixed argument vocabulary and a partial MP4. The host verifies every expected PNG, probes stream and container duration, rejects unexpected streams, fully decodes it using FFmpeg, then publishes `video.mp4`. The terminal manifest is saved before SQLite success is recorded. Failed jobs preserve intermediate files. SQLite and manifests are separate persistence boundaries, not one atomic distributed transaction; forced termination can leave inconsistent terminal metadata and requires manual inspection. Listing jobs opens an existing, contained database read-only and creates no output directories.

## Future renderer contract

A future adapter (including Unity) should consume a validated resolved project and approved job directory, produce numbered RGB PNGs, a reopenable scene where practical, and a versioned report containing actual backend version/settings and timings. Capability validation must reject unsupported primitives/materials/animations before rendering. No Unity stub or unused adapter hierarchy is included; extract a formal Python Protocol once a second working adapter or backend-specific capability negotiation needs it.

## Asset subsystem (0.2)

`engine/assets/models.py` defines declared provenance and readiness evidence. `glb.py` checks the bounded static/self-contained GLB profile; it is intentionally not a complete glTF validator. `registry.py` owns SQLite schema 2 migrations, immutable provenance/content versions, deduplicated blob snapshots, deterministic search and rights/hash/readiness resolution. `inspection.py` starts the bpy-only `inspect_asset.py`; `asset_import.py` is shared by inspection, thumbnails and production. `resolution.py` binds project references to a library and writes checked job-local snapshots and attribution notices. See ASSETS for the complete public workflow.

The importer groups original mesh/empty hierarchies under a normalization parent and an animated entity root. Exact world-space mesh vertices determine aggregate bounds. Stored GLB material/image data is retained; entity material overrides are deliberately unsupported. A report can be marked ready only if its current profile, source hash, positive surface count, dimensions and missing-texture checks pass. Successful inspection does not certify artistic quality or independently establish licensing rights.

Registry lookup checks a pinned version's own approval; older approved versions are not automatically revoked when a newer provenance version is registered. Global revocation policy is future work. Local generated examples have no external licensing dependency.

## Batch and thumbnail subsystem (0.3)

`batch.py` owns validated inventory/selection plans, bounded regular-file reads, root/child-link checks, reviewed content/provenance hashes and incremental per-file reports. Apply uses the existing register/inspect workflow, with independent failures and explicit cancellation states. SQLite records and atomic batch reports are separate durability boundaries; no resume guarantee is made.

`thumbnails.py` snapshots an approved inspected blob, launches the package-owned `thumbnail.py` Blender worker, and persists an image/provenance report. `quality/images.py` validates PNG framing/checksums and decoded pixels. Registry readiness/resolution revalidates image evidence rather than trusting caller-supplied dimensions or pixel statistics. Schema 2 adds a thumbnail status table without altering immutable asset versions. Temporary batch/thumbnail GLBs are cleaned in finally blocks; logs, images and production sources remain local artifacts.
