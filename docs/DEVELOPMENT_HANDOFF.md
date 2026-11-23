# Development handoff

## Resume here

Repository: `C:\Dimalka\yt\blender`; local branch `atlas-foundation`. Version 0.1.0. Read STATUS first, then the narrow module needed for the next change. Do not rebuild the working foundation or implement every roadmap module at once.

## What works

Validated JSON -> deterministic primitives/scatter -> isolated Blender scene and keyframes -> PNG frames -> verified silent MP4. All three example JSON files generate distinct scenes with the same engine. Both CPU Cycles and installed Eevee have real integration coverage. The installed wheel works outside the checkout.

Relevant files:

- `engine/core/models.py`: schema v1.0, constraints and cross-reference/timeline checks.
- `engine/worlds/placement.py`: deterministic scatter expansion.
- `engine/adapters/blender/worker.py`: bpy-only scene/animation/render execution.
- `engine/rendering/pipeline.py`: job lifecycle, manifests, subprocess orchestration and success ordering.
- `engine/rendering/runtime.py`: discovery, capability/environment report and process diagnostics.
- `engine/rendering/video.py`: fixed encoding arguments and verification contract.
- `engine/storage/jobs.py`: SQLite jobs, contained output paths, read-only listing and atomic JSON.
- `apps/cli/main.py`: user commands and machine-readable errors/logging.
- `tests/unit/`, `tests/integration/`: validation/failure/real rendering coverage.
- `examples/`: three standalone projects; `docs/evidence/`: tracked render summaries and preview images.

## Run and verify

```powershell
.\.venv\Scripts\atlas.exe doctor
.\.venv\Scripts\atlas.exe render examples\01_orbit_studio.json
.\.venv\Scripts\python.exe -m pytest -q
$env:ATLAS_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

Full suite on 2026-11-23: 53 passed, one skipped (Windows file-symlink privilege). Integration tests perform actual rendering, video verification and Blender scene inspection. Failure-injection tests first reproduced review defects, then passed after fixes. Full output is retained locally under `outputs/full-suite-final.log`. Exact dependency versions are in `requirements-tested.txt`.

Three retained example videos are listed in STATUS; all have 72 decoded frames, 24 fps, 3-second duration, H.264/yuv420p. Measured end-to-end times: 54.28 s studio, 56.60 s grove, 52.45 s portrait. See PERFORMANCE for conditions and unmeasured quantities.

## Known issues and boundaries

This is the first production slice, not the complete vision. Deferred systems and security/runtime limits are enumerated in STATUS. Of particular importance: no automatic crash resume; no imported assets; no shot sequencing or audio; no full mesh collision or camera-obstruction validation. Keep Blender API changes isolated to the worker. Do not add host dependencies inside Blender or execute code from project specifications.

## Next development task and acceptance

Build the Phase 2 asset-registry/GLB-import slice described in STATUS. Begin with schema and database migration tests for source hash, creator, source URL, exact license, attribution and restrictions. Reject unknown/incompatible usage; no automatic third-party downloads. Add only one supported import format initially, test it in actual Blender, and demonstrate one explicitly approved asset reused in two scene JSON files. Preserve config-driven primitive rendering as a regression path.

Future modules should be added only when they contain working features. Update this file, STATUS and measured evidence at the next milestone. Keep source unchanged during reproducibility runs; hashes describe the files present when a job starts.
