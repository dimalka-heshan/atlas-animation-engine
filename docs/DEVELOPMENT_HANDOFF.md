# Development handoff — ATLAS 0.6.3

The workspace is `C:/Dimalka/yt/blender`. The V0.6.3 cache is `outputs/v063-library-motions`. Use examples 29–32 and the saved reports to compare anatomical transfer, corrected locomotion and handoff. [Current status](STATUS.md) · [Retargeting evidence](V063_REPORT.md)

## Working interfaces

- `engine/production.py` owns the typed director-intent and capability contracts, asset and motion preflight, movement compilation and bounded preview entry point.
- `engine/core/models.py` admits schema 1.6 with a named prop handoff and optional walking contact correction. Earlier schema versions are supported.
- `engine/characters/interaction.py` verifies initial participants, meter-scale MPFB profiles, declared prop and arrival timing. Blender validates evaluated wrist reach and transform continuity through `engine/adapters/blender/handoff.py`.
- `engine/adapters/blender/walk_contact.py` stabilizes ankles within measured flat-ground support windows while preserving source foot orientation. The job retains before-and-after metrics.
- `engine/adapters/blender/retarget_anatomy.py` validates joint landmarks and computes arm frames, profile refinement and motion metrics. `engine/adapters/blender/bake_motion.py` uses those calibrated poses. `engine/characters/cmu.py` is the reviewed BVH allowlist.
- Examples 27 and 28 use the existing `outputs/v052-library`, `outputs/v052-audio`, `outputs/v052-acquisition` and `outputs/v06-release-motions`. Their exact job paths and reproduction commands are in [V0.6.2 demos](V062_DEMOS.md). Keep WAVs, caches and render jobs local.

## Next implementation task

Qualify a loop from the captured straight walk. Measure gait phase, pose discontinuity at the loop boundary and contact drift before enabling it for guided locomotion. Then measure running flight and replace the old grounded run in the guided profile. Keep the current arm comparison, exact route arrival and fort handoff as regressions. Resume procedural worlds after the animation quality checkpoint.

The interaction profile supports one fixed-orientation wrist-level transfer per shot. Plan later extensions for grasp orientation, finger contact and collision checks once those have fixture measurements. The foot correction remains optional and specific to walking on a flat plane. [Director implementation sequence](superpowers/plans/2026-11-25-director-infrastructure.md)
