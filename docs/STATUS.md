# Status — ATLAS 0.2.0 — 2026-11-23

The Phase 0/1 foundation now includes the first Phase 2 asset-import slice. An original registered GLB is reused in two different configuration-driven videos. Full Phase 2, including multiple third-party asset packs, remains incomplete.

## Implemented

- Existing primitive/scenery/keyframe/camera/light pipeline, both CPU Cycles and Eevee, PNG frames, verified silent H.264 MP4, persistent jobs and manifests.
- Local GLB register/search/show/inspect CLI, SQLite schema 1 migration, immutable ID/version provenance, hash-deduplicated blobs and literal metadata search.
- Explicit approval/render-permission gating, creator/source/license text/attribution tracking, restriction rejection and source URL/URN checks. No automatic licensing approval or downloads.
- Bounded self-contained static GLB preflight, scene graph/texture-reference validation and real Blender inspection with failure diagnostics.
- Imported hierarchy/material preservation, exact vertex bounds, unit normalization, center/base pivots, root transform animation and embedded texture decoding.
- Schema 1.1 pinned asset references, schema 1.0 primitive compatibility, checked job-local GLB snapshots, asset manifests and attribution sidecars.
- Readiness evidence tied to the current profile and content hash, positive surface counts, valid bounds and no missing textures.

## Verification

Final full suite with `ATLAS_INTEGRATION=1`: **117 passed, 1 skipped in 87.84 seconds**. The only skip is Windows file-symlink creation privilege. This includes 108 unit tests and nine real Blender integration tests (five for imported assets). Full output is retained in `outputs/asset-full-suite-final.log`.

Real integration tests cover primitive rendering, persistence failures, asset reuse, hierarchy/scale/pivot/animation, rotated triangles, valid and corrupt embedded PNGs, and failed inspection. Independent review findings were reproduced with failing tests and fixed.

An installed 0.2 wheel registered the fixture into a fresh library, ran the packaged inspection worker and rendered a verified CPU MP4 from outside the repository.

Both new example videos are 640x360, 48 frames, 24 fps, exactly 2 seconds, H.264/yuv420p. They share lantern version 1, SHA-256 ea217311b71e809c6942e761368407395b8caa1d24eab6cfdfedb8d4cb3fa05f. Representative frames were visually inspected. Earlier Phase 1 videos remain retained.

## Outputs

- outputs/lantern-studio-30e2573835f34969916549ae43ef65e1/video.mp4
- outputs/lantern-courtyard-bcd1627801df469c8d4ccd5eae82f2d3/video.mp4
- assets/fixtures/lantern.glb and lantern.provenance.json: committed original source fixture.
- assets/library/: ignored local registry and inspection logs.
- docs/evidence/2026-11-23-assets.json and adjacent PNGs: tracked provenance, timing and visual evidence.

Every asset job retains its input/resolved IR, .blend, PNGs, logs, manifest, checked source blobs, asset-map.json and attributions.txt.

## Limits

Only one-scene static triangle GLBs with all nodes reachable are supported. No extensions, external/data URIs, skins, animation, morphs or imported cameras/lights. PNG/JPEG textures must be embedded. Additional formats, directory scanning, thumbnails, repair, rig/clip handling, shared import caching and large-library indexing remain unfinished.

Provenance checks enforce operator declarations, not legal ownership. Older approved versions are not revoked automatically by newer provenance versions. No third-party asset-pack acceptance is claimed.

Characters/actions, physics, audio, multiple shots, queues/cache/resume, dashboard and Unity remain deferred. Scatter checks centers only; camera visibility checks entity origins, not obstruction. Preview noise remains visible. Hard termination or disk failure may leave unfinished metadata; manual rerender is the recovery path. Database, blob and manifest writes are separate transaction boundaries. Asset parsing is not an OS sandbox. Other platforms/Blender versions and peak-memory/final-quality performance remain unverified.

## Exact next task

Continue Phase 2 with deterministic directory discovery, reviewed batch registration and Blender-generated thumbnails. Reuse provenance/hash/profile checks, never auto-approve licenses, isolate per-file failures, verify path containment and actual thumbnail images, and benchmark a modest local fixture collection before adding formats or a dashboard.
