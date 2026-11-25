# Development handoff — ATLAS 0.6

Repository `C:/Dimalka/yt/blender`. The V0.6 implementation is on GitHub `main` at `f1c0389`. See the [delivery report](V06_REPORT.md), [preview commands](V06_DEMOS.md) and [motion interfaces](MOTION.md). The release motion cache is `outputs/v06-release-motions`. Use the jobs listed in the report to inspect the editable scenes and evidence. Keep acquired sources, motion blobs, model weights, WAVs and full renders out of Git.

The working interfaces below record the foundation. V0.5.2 provider and conversion details are in its [delivery report](V052_REPORT.md).

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

Start **V0.6.2 Intelligent Character Interactions, Object Manipulation, Semantic Action Planning and Multi-Character Acting** from example 24. Define a named prop anchor and preconditions for reach, ownership and release. Compile an approach, turn, dialogue and single handoff to explicit synchronized events. Reopen the saved scene and measure hand–prop error and ownership across the transfer. Preserve the current exact-pin checks and flat route tests.

Resolve horizontal foot slide and gait phase changes in a short saved-scene study before marking the moving actor ready for close-up production. General motion formats and additional rig families remain open. Runtime tests used Windows, Blender 5.2.3 LTS, FFmpeg and Intel CPU rendering.
