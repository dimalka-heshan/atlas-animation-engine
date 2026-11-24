# Development handoff — ATLAS 0.3

Repository: C:/Dimalka/yt/blender; dedicated local branch atlas-foundation. Continue this engine. Read STATUS and ASSETS first. The user's master prompt authorizes routine implementation choices and requires progressive working releases, evidence and honest limitations.

## Working capability

JSON drives primitives or approved inspected static GLBs into Blender scenes, PNG frames and verified MP4. Schema 1.1 pins asset IDs/versions; schema 1.0 remains compatible. The registry preserves independent provenance and shared content hashes. Directory discovery now produces an explicitly selected hash-bound plan, applies each file independently and optionally renders verified previews. SQLite schema 2 adds thumbnail status and migrates v1 records intact.

## Relevant files

- engine/assets/batch.py: scan/plan validation, regular-file reads, source containment, sequential application and cancellation reports.
- engine/assets/thumbnails.py and engine/adapters/blender/thumbnail.py: host lifecycle and packaged CPU studio worker using the shared importer.
- engine/quality/images.py: bounded PNG framing/checksums, probing, decode and spatial variation checks.
- engine/assets/registry.py and models.py: schema migration, source/image/inspection proofs, rights and readiness.
- apps/cli/assets.py and main.py: scan/batch/thumbnail CLI and partial-failure status.
- tools/create_batch_fixture.py and examples/06_batch_showcase.json: original mixed collection and reusable production configuration.
- tests/unit/test_asset_batch.py, test_thumbnails.py, test_asset_cli.py and tests/integration/test_asset_thumbnails.py: new coverage.
- docs/evidence/2026-11-24-batch.json: final installed-wheel acceptance, hashes and timings.

## Run

Refresh the editable installation with .venv/Scripts/python.exe -m pip install -e '.[dev]'. Without activation:

    .venv/Scripts/atlas.exe assets scan C:/MyModels --plan outputs/asset-plan.json
    # Review sidecars and select intended candidates in the plan.
    .venv/Scripts/atlas.exe assets batch outputs/asset-plan.json --root C:/MyModels --library assets/library --thumbnails
    .venv/Scripts/atlas.exe assets thumbnail lantern --version 1 --size 256

ASSETS documents original fixture generation and the two IDs required by example 06. Project commands accept --asset-library; asset commands accept --library. Root must match the reviewed plan and cannot overlap the library. Changed bytes/sidecars require rescan. Registration retries are idempotent; requested inspection/thumbnail work reruns. There is no resume/cache behavior.

Run .venv/Scripts/python.exe -m pytest -q; set ATLAS_INTEGRATION=1 for real Blender/FFmpeg tests. Final result: 148 passed, 1 skipped in 215.38 seconds (133 unit and 15 integration passes); outputs/batch-final-tests.xml is the authoritative report. A long Blender call triggered the optional 30-second diagnostic but passed; no subprocess implementation change was needed. The Windows file-symlink privilege test may skip; the directory-junction test runs independently.

## Evidence and review

Nine reproduced review-test failures covered damaged-but-decodable PNGs, public readiness bypass, staging retention and nonregular descriptors. Fixes require PNG CRC/IEND validation, approved matching inspection and independently decoded image evidence, bounded regular-file reads and finally-block cleanup. Cancellation preserves the active registered version and later pending entries. The reviewer rechecked four important fixes with 26 passing targeted tests. An early globally mocked fstat test disrupted pytest capture; the mock now has a scoped context and preserves the full stat tuple.

Final installed-wheel batch: three ready previews, two intended failed candidates and one unsupported skip in 49.67 seconds, two unique blobs for three records. Both distinct previews were visually inspected. Final installed-wheel video: two assets, 480x270, 24 frames/24 fps, one second, verified H.264/yuv420p, 41.17 seconds production time. Artifacts are in STATUS. Concurrent testing means these are observations, not controlled benchmarks.

## Next task

Build reusable environment templates and prove reuse with multiple explicitly licensed compatible asset packs. Inventory actual source/license documents, retain attribution and provenance, use scan/review/batch, inspect previews, render two distinct configurations and measure costs. Keep primitive, import and thumbnail regressions green. Expand formats/rig handling only when a concrete accepted pack requires it and the scope is documented.

## Outstanding work

Full Phase 2 pack acceptance, additional formats/texture repair, rigs/clips, caching, library indexing and global rights revocation remain incomplete. Batch requires portable filenames; full-report rewrites are not optimized for 10,000 selected entries. Stable source directories are required, not a hostile filesystem. Hard kills can bypass cleanup; existing inspection/production snapshots retain diagnostic sources. Characters/actions, audio, multi-shot production, queues/resume, dashboard and Unity are future work.
