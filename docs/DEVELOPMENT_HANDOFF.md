# Development handoff — ATLAS 0.5

Repository `C:/Dimalka/yt/blender`. For the current V0.5.2 implementation and fixtures, use [the delivery report](V052_REPORT.md) and [reproduction guide](V052_DEMOS.md). `engine/assets/sketchfab.py` owns authorized HTTPS and OAuth. `engine/assets/blendkit.py` and `engine/adapters/blender/convert_native.py` own user-mediated licensed conversion. `engine/assets/selection.py` ranks pinned candidates using the provider catalog and Blender-measured quality. Downloaded sources, voice weights, editable native assets and videos stay in local `outputs/`.

The rest of this handoff records the V0.5 baseline and the proposed navigation slice.

## Working interfaces

- apps/cli/assets.py and engine/assets/providers.py: two provider adapters, SQLite catalog, live sync, deterministic search, explicit download, bounded manual archive import, storage and license queries.
- engine/assets/acquisition.py and environment_media.py: reviewed HTTPS origins, source blobs, ZIP and glTF packing, environment media fingerprints and job-local checks. Poly Haven live listings retain source credit.
- engine/assets/glb.py and rigged.py: separate static and embedded rigged GLB profiles. Registry keeps existing schema and pins the chosen profile in asset container metadata.
- engine/adapters/blender/asset_import.py and skeleton.py: inspect weights, hierarchy, rest matrices, actions and materials. Normalize via a parent. Retain original action slots in NLA with checked repeat limits and end-exclusive rendered frames. No hostile-input OS sandbox.
- engine/core/models.py and apps/cli/characters.py: schema 1.3 timelines, hand equipment, environment references, collection composition and character/animation queries.
- The existing voice, audio and lip-sync subsystems remain operational. Need Turbo weights and isolated runtime only for new speech generation. For existing demonstrations, resolve the pinned local clip in outputs/v04-audio and use saved Rhubarb timeline JSON included in the projects.

## Evidence

Fresh V0.4 baseline: 211 passed, one Windows symlink privilege skip. Final full suite: 227 passed and one skip in 169.52 seconds, with both local Turbo and acquired-asset integration enabled. Post-review targeted suite: 16 passed in 9.72 seconds. The installed 0.5 wheel rendered an acquired rig outside the repository. A first in-progress test run failed while source files were changing and when the generic example check did not yet recognize pinned environment media. The later full suite passed. No ongoing regression was observed.

Main artifact inventory is docs/evidence/2026-11-25-v05.json. The 19 acquisitions are the original sources in outputs/v05-acquisition and 12 approved inspected KayKit GLBs in outputs/v05-library. Never stage the cache, WAVs, model weights or render output. Source binaries can be reproduced with the official pinned starter commands. The four videos retain their exact engine source hashes. The final raw NLA boundary correction has dedicated saved-scene and installed-wheel evidence.

## Exact next work

Use the two acquired humanoids to develop a validated locomotion/controller slice. Measure source root transforms and distinguish in-place loops from root-motion clips. Build deterministic waypoint traversal with controlled heading and frame-correct clip transitions. Verify an independently reopened Blender scene and a short two-actor render before claiming navigation or atomic pick-up actions. The next larger sequence is compatible retargeting, conflict-checked interactions and multi-character acting.

Broader asset providers, alternate import profiles, cross-file clip transfer, external facial rig support, procedural cities, multi-shot direction, queues and dashboard remain incomplete. Keep API experiments and larger downloads opt-in. Runtime tests used Windows, Blender 5.2.3, FFmpeg and Intel CPU/integrated graphics. No GPU Turbo throughput or production-scale catalog performance is claimed.
