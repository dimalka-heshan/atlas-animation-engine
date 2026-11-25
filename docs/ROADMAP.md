# Roadmap â€” V2 development order

The V2 master brief supersedes the older phase numbering. ATLAS remains one Python/Blender codebase. Blender is the sole 3D execution and rendering backend; no alternative renderer is planned. Existing 0.3 asset and silent-video workflows remain supported.

## Foundation through 0.5

V0.5.2 adds reviewed Blender-native imports, reusable fort modules, a photographic woodland, and authorized Sketchfab discovery. [V0.5.2 status](V052_REPORT.md)

V0.4 verified isolated Turbo CPU speech and Rhubarb facial animation. V0.5 added official KayKit and Poly Haven acquisition and inspected source-rig playback.

## V0.6 and V0.6.2

V0.6 verifies a KayKit-to-MPFB retarget, immutable cached movements, bounded routes, approach distances and simultaneous speech. Broader capture and rig support, terrain IK and phase-matched gait transitions remain open. [V0.6 status](V06_REPORT.md)

V0.6.2 verifies shared production contracts and one stateful wrist-level prop handoff with approach, dialogue and measured release. Opt-in walking stabilization reduces measured ankle drift in the guided fixture. [V0.6.2 evidence](V062_DEMOS.md)

V0.7 starts with a deterministic layout contract, reusable asset pins, named interaction anchors and spatial validation. [Ordered implementation checkpoints](superpowers/plans/2026-11-25-director-infrastructure.md)

## Ordered phases and exit criteria

0. Audit/protect: preserve schema1.0/1.1, inspect runtime/database/source and pass legacy tests; retain Blender-only architecture. Baseline complete.
1. Local voice: isolated runtime, pinned Turbo source/model, device/download diagnostics, reference consent, profiles/history, segmentation, per-line cache and verified WAV. Exit: actual local Turbo narration on supported hardware, with measured inference and explicit limitations.
2. Narrated video: schema1.2 dialogue/narration, measured event timing, mixing and audio-aware MP4 verification. Exit: an existing scene exported with actual generated narration while silent projects remain unchanged.
3. Lip-sync: measured alignment adapter, audio-bound cue timelines, facial mappings, editable shape-key and basic jaw controls, silence/rest/smoothing. Exit: a compatible character visibly speaks a generated line. This foundation uses coarse English mouth cues, not precise phonemes or general humanoid rigging.
4. Asset libraries and rigs: V0.5 verified two providers, an embedded GLB rig profile, approved glTF dependency packing, two source-bound humanoids and reusable environment media. Remaining: more provider/format coverage, imported facial rigs, independent motion assets and broader mappings.
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
