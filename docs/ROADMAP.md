# Roadmap

## Current scope: 0.1 foundation

Phase 0: repository, installable Python package, validated schema, structured CLI logging, runtime discovery, job history, atomic metadata, unit and real Blender tests.

Phase 1: reusable primitives and deterministic scenery, transforms/keyframes, configured tracking camera and lighting, PNG rendering, MP4 encoding/verification, multiple JSON-only example videos. Evidence and remaining limits are in STATUS and TESTING.

## Next releases

1. Phase 2: local approved-asset registry, hashes/provenance, deterministic metadata search, one GLB import path with diagnostics, then multiple licensed asset-pack demonstrations. Add normalization, texture/rig inspection and thumbnails incrementally.
2. Phase 3: rig profiles, reusable compatible animation controllers and semantic interactions. Pick-up must validate capabilities, contact timing and state changes; do not substitute an unrelated clip.
3. Phase 4: multiple shots, camera plans, composition and obstruction checks, continuity and lighting presets.
4. Phase 5: action dependency graph, timeline conflicts and deterministic scene planning; optional local AI only behind validated specifications.
5. Phase 6: shot-level cache keys, queues, cancellation controls, stale-job reconciliation and resumption; audio and benchmark expansion.
6. Phase 7: local FastAPI + React production dashboard backed by functioning APIs.
7. Phase 8: advanced rigs, retargeting, physics, crowds, vehicles, facial motion, additional rendering backends and distributed rendering only when justified by measurements.

## Example coverage

Implemented: studio sculpture/camera animation, seeded grove/lake environment with moving beacon, portrait animated columns. They exercise the same renderer without example-specific Python.

Planned: rigged character interaction, real vehicle following a route, multi-shot sequence with synchronized audio, reusable imported licensed worlds. Current primitive movement must not be described as a rigged-character or vehicle system.
