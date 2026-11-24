# Roadmap — V2 development order

The V2 master brief supersedes the older phase numbering. ATLAS remains one Python/Blender codebase. Blender is the sole 3D execution and rendering backend; no alternative renderer is planned. Existing 0.3 asset and silent-video workflows remain supported.

## Current implementation cycle: 0.4 voice/audio/facial foundation

The fresh 0.3 baseline passed 148 tests with one Windows file-symlink privilege skip. The current cycle adds an isolated pinned Chatterbox-Turbo provider, voice profiles/cache, approved PCM audio versions, schema 1.2 audio events, FFmpeg mixing/verification and a Rhubarb-driven original simple facial character. Actual inference and final production evidence are recorded in STATUS; presence of an adapter alone is not an exit criterion.

## Ordered phases and exit criteria

0. Audit/protect: preserve schema1.0/1.1, inspect runtime/database/source and pass legacy tests; retain Blender-only architecture. Baseline complete.
1. Local voice: isolated runtime, pinned Turbo source/model, device/download diagnostics, reference consent, profiles/history, segmentation, per-line cache and verified WAV. Exit: actual local Turbo narration on supported hardware, with measured inference and explicit limitations.
2. Narrated video: schema1.2 dialogue/narration, measured event timing, mixing and audio-aware MP4 verification. Exit: an existing scene exported with actual generated narration while silent projects remain unchanged.
3. Lip-sync: measured alignment adapter, audio-bound cue timelines, facial mappings, editable shape-key and basic jaw controls, silence/rest/smoothing. Exit: a compatible character visibly speaks a generated line. This foundation uses coarse English mouth cues, not precise phonemes or general humanoid rigging.
4. Real asset libraries/rigs: accept multiple properly licensed packs, external textures, versioned rigged import profiles, skeletal/clip/facial inspection, character catalog. Add FBX only for a justified accepted pack. Exit: approved real rigged characters and animations import without weakening static checks.
5. Movement/interactions: compatible motion libraries, locomotion/path navigation, rig profiles, blending/retargeting, semantic actions with preconditions/contact/state. Exit: multiple compatible characters execute configured actions without per-video Python.
6. Procedural worlds: modular cities/buildings/interiors, terrain/biomes/vegetation, deterministic layouts, interaction anchors and navigation metadata. Exit: distinct usable environments from reusable asset collections.
7. Cinematic production: persistent multi-shot state, camera library/director, dialogue-driven framing, composition/occlusion, continuity, transitions and lighting. Exit: a coherent multi-shot acted conversation.
8. Story planning: structured storyboards, requirements/action dependency resolution, audio-aware timing, deterministic templates and optional local AI behind validation. Exit: multiple executable scene plans without source changes; unsupported requests return useful errors.
9. Physics/effects: rigid bodies, contacts, simulation caches, weather/particles/cloth and justified advanced effects. Exit: reproducible configured simulations within documented limits.
10. Production caching/queues: dependency hashes, shot-level reuse, persistent scheduling/cancellation/retry/recovery, memory/GPU monitoring and benchmark expansion. Exit: a changed line/shot preserves unaffected production outputs.
11. Local studio: FastAPI, React/TypeScript project/asset/scene/storyboard/voice/lip-sync/timeline/render/quality tools. Exit: create and complete a video through functioning UI workflows.
12. Full integration/optimization: robust long narration, multi-speaker acting, SFX/music/ducking/fades/loudness, captions, batch production and quality review. Exit: distinct verified one-minute Shorts with reusable scenes/rigs/voices/lip-sync/multiple shots/audio, measured production costs and no per-video hardcoding.

## Acceptance sequence

Retain original primitive and imported-model videos. Add (1) actual narration audio, (2) narrated environment, (3) talking-character preview, (4) two-character conversation, (5) state-aware character/object interaction, then (6) complete one-minute Short. Verify codecs, frame/audio timing, hashes, decode and editable Blender artifacts; distinguish technical checks from perceptual quality and human review.

Track unfinished exit criteria explicitly in STATUS and DEVELOPMENT_HANDOFF. Do not mark general voice cloning, advanced acting, precise phoneme alignment, third-party rig compatibility or full studio automation complete from a small fixture demonstration.
