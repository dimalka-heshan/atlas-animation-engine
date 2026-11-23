# Development handoff — ATLAS 0.2

Repository: C:/Dimalka/yt/blender; local branch atlas-foundation. Continue the existing engine. Read STATUS and ASSETS before the next narrow change.

## Working capability

Primitive production remains intact. Schema 1.1 projects additionally reference approved, inspected GLBs by immutable ID/version. The registry preserves independent provenance and shared content hashes. Blender imports hierarchy/materials, computes exact vertex bounds, applies pivot/normalization, and animates the entity root. Production retains checked source copies and attribution notices. The same original lantern appears in two distinct configurations.

## Relevant files

- engine/assets/models.py: rights policy and required inspection evidence.
- engine/assets/glb.py: bounded static/self-contained triangle profile, scene/image references.
- engine/assets/registry.py: SQLite schema 1, versions, deduplication, search and resolution.
- engine/assets/inspection.py and resolution.py: inspection lifecycle, source snapshots and provenance.
- engine/adapters/blender/asset_import.py: shared bpy importer, exact bounds, lazy texture decode and normalization.
- engine/adapters/blender/inspect_asset.py and worker.py: inspection/production entrypoints.
- engine/core/models.py: portable AssetReference/AssetEntity and 1.0/1.1 compatibility.
- apps/cli/assets.py and main.py: asset commands and project library selection.
- tools/create_asset_fixture.py: original reusable GLB generator, not a per-video script.
- assets/fixtures/ and examples/04_lantern_studio.json, 05_lantern_courtyard.json: runnable examples.
- tests/unit/test_assets.py, test_asset_projects.py, test_asset_cli.py and tests/integration/test_asset_import.py: new coverage.

## Run

Use .venv/Scripts/python.exe -m pip install -e '.[dev]' to refresh the editable package. CLI commands:

    atlas assets register assets/fixtures/lantern.glb --id lantern --provenance assets/fixtures/lantern.provenance.json
    atlas assets inspect lantern --version 1
    atlas render examples/04_lantern_studio.json
    atlas render examples/05_lantern_courtyard.json

Use .venv/Scripts/atlas.exe without activation. Asset commands accept --library; validate/render accept --asset-library. Identical latest registration is idempotent; changed bytes/provenance creates a new version. References never silently advance. Reinspect to refresh readiness evidence after importer-profile changes.

Run .venv/Scripts/python.exe -m pytest -q. Set ATLAS_INTEGRATION=1 to include real Blender/FFmpeg tests. Final result: **117 passed, 1 skipped in 87.84 seconds** (108 unit and nine integration passes). Logs are retained locally in outputs/asset-full-suite-final.log. The skip is the Windows file-symlink privilege test.

## Evidence and review

Two new videos are 640x360, 48 frames, 24 fps, two seconds, verified H.264/yuv420p. Their manifests contain the same pinned source hash. A fresh installed-wheel library was registered, inspected and rendered from outside the checkout. PERFORMANCE and docs/evidence/2026-11-23-assets.json record actual measurements.

Review defects were reproduced and fixed: lazy packed-image state, unbound texture references, unused/alternate scene nodes affecting imports, rotated AABB errors, inspection/hash mismatch, incomplete provenance URLs, invisible nonsurface meshes and SQLite integer overflow. Current preflight rejects unsupported scene topology and nonsurface modes explicitly.

## Next task

Implement deterministic directory discovery, reviewed batch registration and thumbnails. First test stable order, duplicate bytes versus provenance, unsupported formats, per-file failures and path containment. Reuse all GLB/rights/readiness checks; do not automatically approve missing provenance. Produce thumbnails through the trusted Blender adapter and verify the actual images. Benchmark a small local fixture collection. Keep all primitive and asset render regressions green.

## Outstanding work

Full Phase 2 asset-pack acceptance, more formats, external texture repair, rig/clip support, thumbnails, import caching and global rights revocation remain incomplete. Older pinned approvals stay independent of later versions. Characters/actions, audio, multi-shot production, queues/resume, dashboard and Unity are not implemented. Source files should remain unchanged during provenance runs. Example videos predating review fixes are explicitly distinguished from final-code integration and installed-wheel runs.
