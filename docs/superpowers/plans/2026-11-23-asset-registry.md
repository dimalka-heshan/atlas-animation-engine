# ATLAS asset registry implementation plan

> Execute inline using test-driven development, with independent review at the end.

**Goal:** Register a local self-contained GLB with provenance and reuse its pinned version in two verified videos without engine edits.
**Architecture:** Portable asset entities extend schema 1.1 while 1.0 primitive projects keep working. A versioned SQLite registry stores immutable metadata and content-addressed GLBs. Preflight checks rights, content hashes and self-contained GLB safety before a Blender importer inspects and renders the model. Each job snapshots the approved source and provenance.
**Stack:** Existing Python/Pydantic/SQLite/Blender/FFmpeg; no new runtime dependency.
**Spec:** User master prompt Phase 2 and docs/DEVELOPMENT_HANDOFF.md next-task acceptance.

## Design decisions and constraints
- Continue the existing dedicated local branch; working tree was clean at start.
- Registry copies explicit local files only. No downloads, scraping, arbitrary scripts or external resource resolution.
- Only self-contained GLB 2.0 static meshes initially. Reject external URIs, extensions, skins, animations and morph targets with actionable diagnostics; count/inspect unsupported capabilities for future work where practical.
- Approval is supplied as local provenance, never inferred from file format or price. Unknown/unreviewed/rejected rights and unsupported restrictions block use. Explicit supported render permission and attribution are required.
- Content hash deduplication shares blobs but never silently shares or overrides provenance. Re-registration of identical metadata/content is idempotent; changed provenance/content creates an immutable version. Render references pin both ID and version.
- Preserve imported materials and hierarchy; animate a generated entity root. Optional unit-longest-axis normalization and center/base pivots operate on aggregate world bounds in Blender Z-up coordinates.
- Store actual import dimensions, mesh/material/texture counts, polygon count and missing textures. Failed inspection is recorded and cannot render.
- No claim of completing all Phase 2 asset-pack/world features; this is the first import vertical slice.

## Review focus
Malformed or path-bearing GLBs, missing/hash-changed blobs, rights/version mismatches, failed/partial inspection, duplicate IDs and database migration safety, imported hierarchy/scale/pivot correctness, old schema compatibility, installed-wheel importer availability.

## Tasks
- [x] Registry: provenance schemas, migration v1, immutable versions, streamed hashes and atomic local copies, deterministic filters. Tests first for duplicates, licenses, corruption, migration refusal and traversal.
- [x] GLB boundary and Blender inspection: bounded parser, reject external dependencies/unsupported capabilities; trusted inspection worker; aggregate bounds and diagnostics; real fixture import tests.
- [x] Production integration: schema 1.1 asset entities, version-pinned preflight, job snapshots/manifests, hierarchy-preserving instantiation/normalization; unchanged primitive regression tests.
- [x] CLI and examples: assets register/search/show/inspect; validate/render with a library; generated original fixture, two JSON scenes, actual MP4 renders and verification.
- [x] Release evidence: full tests, installed-wheel smoke, independent review and regression fixes, documentation/status/handoff and local commit.

## Progress
- Baseline: f8f46b1, clean working tree, existing environment and retained Phase 1 outputs.
- Ruling: user's continue accepts the previously recorded next task and delegated routine technical decisions; no new approval pause.
- Core RED/GREEN: registry/GLB and schema tests failed before implementation; 93 unit tests passed at the first complete CLI milestone; real reuse/inspection tests passed.
- Review RED/GREEN: reproduced rotated-bound errors, valid packed texture rejection, missing texture-reference acceptance, unsupported node graph import, mismatched inspection proof, incomplete source URLs, nonsurface primitives and SQLite integer overflow. Fixed all findings and retained regressions.
- Final full suite: 117 passed, 1 skipped (Windows symlink privilege), 87.84 s. Both new example MP4s independently verified; original fixture reused with matching pinned hash. Fresh installed-wheel library registered, inspected and rendered outside checkout.
- Ruling: restrict this first importer to one fully reachable static triangle scene; reject unsupported semantics rather than silently changing the asset. Additional formats and full licensed-pack acceptance remain Phase 2 work.
