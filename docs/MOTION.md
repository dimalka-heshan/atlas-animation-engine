# Motion, retargeting and locomotion

V0.6.3 uses anatomical joint frames and optional category refinement. Reviewed CMU MotionBuilder BVHs add captured human movements. Both are baked into the same versioned motion registry and played by the same Blender worker. [V0.6.3 report](V063_REPORT.md) · [Current bake and comparison commands](V063_DEMOS.md)

Use `animations list --character kaykit-knight --library outputs/v05-library` to inspect available source clips. `characters rigs --library PATH` reports the canonical bone mapping and rest fingerprint from production inspection. Reuse the previously acquired CC0 Adventurers Knight and generate the MPFB game-engine target with the supplied human specs. [Source setup and commands](V06_DEMOS.md) · [KayKit license](https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0/blob/672074b73ba276876a19e8816ecdc5241817ab47/addons/kaykit_character_pack_adventures/LICENSE.txt)

## Supported inputs and cache

- KayKit sources are inspected CC0 rigged GLBs with embedded skeletal Actions. The CMU command admits the reviewed file hashes listed in the source allowlist. Proven targets are the clothed MPFB game-engine curator and scholar with the expected shoe mesh. The normalized rigs are meter-scale, Z-up and face negative Y. General-purpose BVH, FBX and arbitrary rig import remain open.
- `animations retarget SOURCE CLIP TARGET --id ID` samples the Action in offline Blender at 30 fps for up to 12 seconds. It aligns joint frames, transfers pose rotations through the target hierarchy and scales pelvis displacement by leg length. KayKit and captured walk clips retain the source XY root trace and subtract it from the target pelvis. Other reviewed human capture clips preserve horizontal movement. Captured takes play as one-shots with `loop=false`.
- A motion pin contains `id` and `sha256`. The bake identity includes the source and target versions, asset and rest hashes, source Action, Blender build, relevant worker hashes, category and grounding settings. A repeated bake uses the cached record when it matches. New IDs may reference the same content. The job validates each exact pin and copies shared bytes once.
- `motions providers`, `motions list` and `motions inspect ID SHA256` expose provider, bake provenance, compatibility, speed, contact and arm metrics. `motions list --include-legacy` includes historical bakes. The target version, asset hash and rest fingerprint must match the original bake. Submit a new bake when the character specification or assets change.

## Schema 1.5 projects

Set `navigation.bounds` and optional `obstacles` to rectangles `[min_x, min_y, max_x, max_y]` in meters. `clearance` expands obstacles and insets bounds. `actor_separation` is minimum planar center distance. Routes stay on the explicit Z=0 plane. Meshes, terrain and obstacles outside these rectangles play no part in route selection.

Declare one movement action per base-pivot, unscaled rigged actor. `walk_to` and `run_to` take `destination`, `follow_waypoints` takes `waypoints`, and `approach_actor` takes `target_actor` and a personal `stop_distance`. All use a pinned compatible motion. `start_frame`, `speed_mps` and `blend_frames` are optional. Omitted speed comes from the bake. Frame rounding and short segments affect realized speed. A run requires a calibrated run pin.

An approach can target a stationary or already-arrived actor. It prefers the nearby point on the stopping circle, and checks a bounded set of alternate points when that route fails. Actors already within stopping range turn in place. The planner rejects conflicts between actors during shared time intervals, including between frames. Dynamic replanning, automated yielding and progress around a moving target are deferred.

The compiler sets position and heading keys and uses an embedded `HumanIdle` strip beneath the baked motion. The motion strip fades in and out over the requested windows. Headings follow the route and ease into larger changes over adjacent frames. Position follows straight segments with exact knots and a fixed stop. A manually authored schema 1.5 actor can also use sequential pinned events over a covering base strip. Overlays are full mapped-body replacement with weighted edges. Phase-matched gait crossfades, limb masks and turn-in-place clips remain open.

## Foot placement and facial animation

For walk, run and idle, the bake measures the two evaluated shoe meshes as vertex groups and offsets the pelvis vertically to correct the lowest point at each sampled pose. Reported contact indices identify feet within 25 mm of the lowest point. Playback blends and resampling can introduce additional height errors. Horizontal foot locks, flight-aware running, terrain alignment and leg IK remain open. Use `--no-ground` for exploratory seated or gesture clips. Those bakes still require the inspected rig and shoe profile.

Speech runs through the existing WAV mix and Rhubarb-bound facial shape keys. Body overlays and face channels can run simultaneously. See example 24 and its reopened evidence. [V0.6 delivery report](V06_REPORT.md)
