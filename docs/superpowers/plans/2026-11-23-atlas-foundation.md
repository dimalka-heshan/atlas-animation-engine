# ATLAS foundation implementation plan

> Execute inline with test-driven development and one final independent review.

**Goal:** Generate three real, distinct MP4 videos from JSON without engine changes.
**Architecture:** Pydantic project IR -> deterministic scene expansion -> isolated Blender worker -> PNG sequence -> FFmpeg -> ffprobe validation. SQLite records jobs; atomic manifests retain provenance and measured timings.
**Stack:** Python 3.14, Pydantic 2, pytest, installed Blender 5.2, FFmpeg.
**Spec:** User's master development prompt, immediate assignment (Phases 0 and 1).

## Constraints and decisions
- All execution local; no paid services or asset downloads.
- Empty directory is the initial isolated repository; use atlas-foundation branch in place.
- Integer frames, meters, right-handed Z-up, Euler degrees in portable JSON.
- One scene/camera per project initially; multiple shots and advanced modules deferred.
- CPU Cycles is portable fallback; Eevee selectable and tested against actual runtime.
- Configurations contain no executable expressions or output paths. CLI supplies approved output root.
- UUID job directories prevent collisions and preserve earlier renders.

## Review focus
Reject nonfinite values, invalid references, duplicate identifiers, invalid keyframes and unsupported fields. Verify missing/failed tools cannot report success; verify frame count, duration, codec and dimensions. Keep all job writes under output root. Ensure deterministic scatter and source provenance survive installed-package execution.

## Tasks
1. Core: engine/core/models.py and engine/worlds/placement.py; tests/unit/test_models.py. Write failing validation/determinism tests, run RED, implement validated IR and seeded expansion, run GREEN.
2. Execution: engine/rendering/{runtime,pipeline,video}.py, engine/storage/jobs.py, engine/adapters/blender/worker.py; unit failure/path/verification tests plus actual Blender integration tests. Test RED, implement safe subprocesses, persistence, primitive builder, transforms and camera tracking, render/encode/verify, test GREEN.
3. CLI/examples: apps/cli/main.py and three JSON examples. Exercise doctor/validate/schema/render/verify/jobs, actual subprocess CLI tests and three video renders.
4. Release evidence: inspect rendered frames, decode/ffprobe videos, run full suite and clean installation, independent review, fix regressions, document results and next task.

## Progress
- Inspection: Windows 11 Pro; Core 7 240H (16 logical CPUs), 31.7 GiB RAM, Intel integrated graphics; Python 3.14.6; FFmpeg installed. No existing files or repository.
- Ruling: user explicitly delegates routine decisions and requests immediate implementation; proceed without design approval questions.
- Task 1 complete: validation/determinism tests initially failed on missing engine; implementation passed 17 tests.
- Task 2 complete: process/database/video tests and real Blender tests exercised both engines. Failure paths retain logs and statuses.
- Task 3 complete: CLI tests initially failed before implementation; all three configured videos rendered and verified.
- Task 4 complete: independent review followed by reproduced RED/GREEN regressions; full suite 53 passed, 1 skipped; wheel installed outside repository and rendered successfully; evidence and handoff written.
- Ruling: initial directory has no base branch or remote; retain local foundation branch. No merge/push decision is necessary for this assignment.
- Review fixes: terminal manifest before SQLite success; guarded provenance; stream plus container validation; read-only history with containment; invalid aim and extreme numeric preflight; streaming video hash; revalidation of mutated API input.
- Remaining limits: Windows file-symlink test cannot run without privilege; crash resume, advanced modules and peak-memory profiling intentionally deferred and documented.
