# Status — ATLAS 0.3.0 — 2026-11-24

ATLAS now supports reviewed directory batches and verified asset thumbnails alongside configuration-driven Blender/MP4 production. Phase 2 remains partial: no third-party pack acceptance, additional input formats or rig support is claimed.

## Implemented

- Existing primitive/scatter/keyframe/camera/light pipeline, CPU Cycles/Eevee, verified H.264 video and persistent jobs/manifests.
- Local static GLB registry, immutable provenance versions, content deduplication, rights gating, search, Blender inspection, normalization/pivots and schema 1.1 pinned references; schema 1.0 remains compatible.
- Deterministic directory scans, all entries unselected by default, reviewed source/sidecar hashes, explicit matching root, disjoint library, child-link rejection and bounded regular-file reads.
- Sequential batch registration with optional inspection/thumbnails, independent failures, durable reports, partial-failure exit code 2 and cancellation preserving registered versions/pending entries.
- CPU studio previews at 128/256/512 pixels and transactional SQLite schema 1 -> 2 migration preserving prior records.
- Thumbnail readiness requires approved matching inspection, source/image hashes, complete PNG framing/CRC/IEND, actual dimensions/decode and spatial pixel variation. New batch/thumbnail staging copies are cleaned after normal success/failure/cancellation.

## Verification

**Final suite: 148 passed, 1 skipped in 215.38 seconds**, with ATLAS_INTEGRATION=1 (133 unit passes and 15 real Blender/FFmpeg integration passes). The only skip is the Windows file-symlink privilege test; the directory-junction test passed. Authoritative test evidence is outputs/batch-final-tests.xml; its readable summary is outputs/batch-full-suite-final.log. A 30-second diagnostic exposed a long Blender call that subsequently passed; no runtime change was needed. Independent review rechecked four important fixes with 26 passing targeted tests and found no remaining concrete defect in those areas.

The final installed 0.3 wheel ran outside the repository working directory. Its original mixed collection produced the expected three successes, two independent failures and one skip in 49.67 seconds. Three records share two unique blobs; no new batch/thumbnail staging GLBs remain. Both distinct previews were visually inspected.

The installed package rendered and fully verified the same two assets in a 480x270, 24-frame, 24-fps, one-second H.264/yuv420p video (41.17 seconds total). Frame 12 was visually inspected. No new runtime dependency was added. Concurrent testing means these times are observations, not controlled benchmarks.

## Outputs

- outputs/batch-showcase-bf2562ded77e4bf290b2f6eb368cebec/video.mp4: final installed-wheel video with scene, frames, sources, manifest and logs.
- outputs/batch-library-v03-final/: registered versions, previews, inspection diagnostics and durable report.
- outputs/batch-result-v03-final.json and outputs/batch-plan-v03.json: results and reviewed original-fixture selection.
- docs/evidence/2026-11-24-batch.json and adjacent PNGs: tracked provenance, timing and visual evidence.
- tools/create_batch_fixture.py and examples/06_batch_showcase.json: reproducible originals and configuration-only video.
- Previous five example videos and the original lantern fixture remain retained.

## Limits

Only the documented static embedded triangle GLB profile is supported. No external textures/extensions/skins/animation/morphs, additional formats, repair, rig/clip playback or shared import cache. Provenance checks enforce declarations, not legal ownership; older pinned approval is not automatically revoked.

Batch inventory requires portable filenames and stable source trees. Child links/special files are rejected, but path checks are not an adversarial OS sandbox. Full-report rewrites favor small collections; 10,000 entries is a cap, not proven throughput. Hard termination may leave running records/staging files; no automatic resume. Registry, blobs and reports have separate durability boundaries. Existing inspection diagnostics and production snapshots retain source copies. Thumbnail checks detect corruption/uniformity, not artistic quality or visibility.

Characters/actions, physics, audio, multiple shots, queues/resume, dashboard and Unity remain deferred. Scatter checks centers only; camera warnings do not detect occlusion. Preview noise remains visible. Other platforms/Blender versions, peak memory and final-quality performance remain unverified.

## Exact next task

Continue Phase 2 with reusable environment templates backed by explicitly licensed compatible assets. Start with a small source/license inventory, retain original license/attribution records, import through the reviewed batch workflow, and render two distinct environments through the same engine. Measure costs before expanding formats, a dashboard or rigging. Do not claim full Phase 2 until multiple real asset packs pass acceptance.
