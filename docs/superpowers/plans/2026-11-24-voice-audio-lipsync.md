# Voice, narration and lip-sync implementation plan

> Use executing-plans for coordinated implementation, test-driven changes and an independent final review. The user's V2 brief delegates routine design decisions and explicitly requests immediate implementation without repeated approval pauses.

**Goal:** Extend ATLAS 0.3 with isolated Chatterbox-Turbo inference, reusable verified narration and audio-driven facial animation while preserving silent projects.
**Architecture:** A package-owned JSON subprocess worker hosts optional ML dependencies. Main Python owns voice profiles/cache/audio evidence; schema 1.2 adds pinned audio events and explicit facial performances. FFmpeg mixes audio after Blender renders; a replaceable Rhubarb adapter generates measured mouth cues for a reusable original simple character.
**Stack:** Existing Python/Pydantic/SQLite/Blender/FFmpeg; isolated pinned Chatterbox runtime and optional pinned local Rhubarb executable.
**Spec:** User's MASTER DEVELOPMENT PROMPT V2.0, attachment SHA256 07e16bf81a0791ab6c3e258feb07b3a51786206c76767569ab669bcf40c8a67b.

## Constraints and choices
- Preserve schema 1.0/1.1 behavior and all existing examples. Blender is the sole execution backend; remove active alternative-renderer roadmap work.
- No paid service or API credentials. ML installation stays outside the primary environment and Blender. Use official source/API and immutable runtime/model revisions; report actual hardware/runtime failures.
- No automatic real-person voice approval. Conditioned voices require recorded reference permission; imported recordings remain an explicit supported path.
- Audio is the time authority: measure actual PCM, reject overrun unless an explicit timing policy is selected. Never invent phoneme timing from text length.
- Choose subprocess protocol over localhost service for current single-user CLI. Choose Rhubarb coarse English mouth cues over heavyweight forced alignment for this foundation; describe its precision honestly.
- Baseline remains on the existing dedicated branch; independent subsystem agents edit disjoint files. Parent integrates shared models/worker/pipeline/CLI/docs.

## Review focus
- Cache invalidation for runtime/model/reference/settings and corrupted cached audio.
- Nonfinite/empty/clipped WAV, unapproved reference use and missing runtime/model weights.
- Audio beyond video duration, wrong hashes, extra streams, silent legacy compatibility.
- Wrong actor/clip assignment, unsupported facial mappings, silence/rest and frame rounding drift.
- Failed/cancelled jobs, external process timeouts, packaged worker availability, no fake real-inference claims.

## Tasks
- [ ] Audit current docs/source/database/CLI/hardware; run baseline suite and record evidence.
- [ ] Voice subsystem: failing tests, official API/runtime pin, doctor, profiles/reference approval, generate/preview/list, validated PCM WAV, cache/provenance; run actual inference when available. Own engine/voice, apps/cli/voice.py and engine/audio/validation.py.
- [ ] Audio production: tests for pinned imported WAV and rights, schema 1.2 events, measured timing, verified mixing and AAC+H264 output, preserved silent validation. Own engine/audio (except validation), core models, rendering pipeline/video and main CLI.
- [ ] Lip-sync: tests for bounded measured cue timelines, Rhubarb adapter, shape/bone mappings, smoothing/rest/frame policy; reusable original character and Blender preview integration. Own engine/lipsync, apps/cli/lipsync.py and new Blender facial modules.
- [ ] Integrate shared interfaces; create real artifacts, inspect waveform/scene/video evidence, run relevant tests and installed-wheel smoke, independent review and corrections.
- [ ] Update README/STATUS/ROADMAP/ARCHITECTURE/TESTING/licensing/performance/voice/lip-sync/handoff; commit verified capability with remaining limits and exact next task.
