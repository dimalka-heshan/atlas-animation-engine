# Development handoff — ATLAS 0.6.2

The workspace is `C:/Dimalka/yt/blender`. GitHub `main` includes the shared production contract checkpoint `0e3f571` and the V0.6.2 implementation `46ddc6f`. [Current status](STATUS.md) · [Production evidence](V062_DEMOS.md)

## Working interfaces

- `engine/production.py` owns the typed director-intent and capability contracts, asset and motion preflight, movement compilation and bounded preview entry point.
- `engine/core/models.py` admits schema 1.6 with a named prop handoff and optional walking contact correction. Earlier schema versions are supported.
- `engine/characters/interaction.py` verifies initial participants, meter-scale MPFB profiles, declared prop and arrival timing. Blender validates evaluated wrist reach and transform continuity through `engine/adapters/blender/handoff.py`.
- `engine/adapters/blender/walk_contact.py` stabilizes ankles within measured flat-ground support windows while preserving source foot orientation. The job retains before-and-after metrics.
- Examples 27 and 28 use the existing `outputs/v052-library`, `outputs/v052-audio`, `outputs/v052-acquisition` and `outputs/v06-release-motions`. Their exact job paths and reproduction commands are in [V0.6.2 demos](V062_DEMOS.md). Keep WAVs, caches and render jobs local.

## Next implementation task

Start V0.7 with a typed, seeded layout request that references a pinned environment collection. Compile two distinct layouts through existing placement and asset preflight. Emit stable entity IDs, transforms, occupied bounds, named prop and standing anchors, and explicit navigation rectangles. Reject overlap and blocked approaches deterministically. Reuse the V0.6.2 handoff as a regression fixture. Add scene-state persistence after the layout contract has verified results.

The interaction profile supports one fixed-orientation wrist-level transfer per shot. Plan later extensions for grasp orientation, finger contact and collision checks once those have fixture measurements. The foot correction remains optional and specific to walking on a flat plane. [Director implementation sequence](superpowers/plans/2026-11-25-director-infrastructure.md)
