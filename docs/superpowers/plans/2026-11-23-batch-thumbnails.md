# Batch registration and thumbnails plan

> Execute inline with test-driven development and one independent final review.

**Goal:** Discover a local directory deterministically, apply a reviewed selection without automatically approving licenses, isolate per-file failures, and produce verified Blender thumbnails for approved assets.
**Architecture:** Scan -> editable hash-bound BatchPlan -> explicit source-root check -> existing registry/rights/import pipeline per selected file -> durable batch report. A separate thumbnail worker uses the shared GLB importer and CPU Cycles. SQLite schema 2 adds thumbnail status/provenance; existing v1 records migrate intact.
**Stack:** Existing Python/Pydantic/SQLite/Blender/FFmpeg only.
**Spec:** User master prompt Phase 2 and 0.2 DEVELOPMENT_HANDOFF next task.

## Decisions and constraints
- Continue clean dedicated local branch from 5928813. No new external services, downloads or license inference.
- Plans default every entry to unselected. The operator edits selections/IDs; provenance still must explicitly permit rendering. Automation can select the original locally generated acceptance fixtures under existing project authorization.
- Plan stores source/provenance hashes. Apply requires an explicit approved source root, rejects changed files, absolute/traversing paths and any child symlink/junction, and does not allow the library inside the source directory.
- Scan is stable by relative path, supports recursive/nonrecursive operation, reports unsupported/broken entries and ignores provenance sidecars as standalone assets.
- Batch persists incremental reports; one file failure does not stop other selected files. Partial failures return CLI exit code 2. Interrupted work retains the report and completed registry records; no resume/cache claim.
- Thumbnails require current rights and successful matching inspection. CPU Cycles studio thumbnail, square sizes 128/256/512, fixed normalization/framing; PNG is probed and decoded before ready status.
- Thumbnail reports bind image/source hashes, profile, settings, backend and timings. Unique attempt directories preserve earlier images; failure is explicit.
- Migrate registry v1 -> v2 transactionally; do not lose immutable versions/inspection records.

## Review focus
Source/provenance changes after review; symlinks/junctions and library recursion; duplicate IDs and malformed plans; partial failures/interruption; PNG corruption/dimensions/uniform output; migration preserving v1 and rejecting future versions; failure cannot overwrite success metadata with false readiness; installed wheel workers.

## Tasks
- [x] Scan/plan/batch: failing tests for ordering, sidecars, hashes, explicit selection, bounds and isolated failures; implement and pass.
- [x] Thumbnails: migration tests and image verification tests; shared importer/studio worker, persisted evidence and real Blender tests.
- [x] CLI/acceptance: scan, batch and thumbnail commands; mixed local collection, real batch and inspected thumbnail images; package smoke.
- [x] Review/verification: fix reproduced defects, full regression suite, actual video smoke, measured benchmarks, status/handoff and commit.

Completed 2026-11-24: 148 passed, 1 skipped; installed-wheel mixed batch and verified two-asset video, visual evidence and review fixes recorded in STATUS.
