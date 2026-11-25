# Source rigs and animation clips

V0.6 adds a measured transfer from the CC0 KayKit Knight skeleton to generated MPFB game-engine humanoids. The existing source-rig and MPFB facial controls remain available. [Rig profiles, motion pins and playback](MOTION.md)

Schema 1.3 adds a rigged asset entity. The source GLB version pins the skeleton and all compatible embedded actions. The strict static GLB importer stays the default for old projects. The separate rigged profile currently supports one embedded armature, skinned meshes, inverse bind matrices and ordered transform animations with LINEAR or STEP sampling. External resources, extensions, morph targets, arbitrary rig scripts and multiple armatures are rejected. Blender verifies actual weights, materials and images before registry readiness.

```powershell
$python = '.\.venv\Scripts\python.exe'
$library = 'outputs/v05-library'
& $python -m apps.cli characters list --library $library
& $python -m apps.cli characters inspect kaykit-knight --version 1 --library $library
& $python -m apps.cli characters validate kaykit-mage --version 1 --library $library
& $python -m apps.cli animations list --character kaykit-knight --version 1 --library $library
& $python -m apps.cli animations compatibility kaykit-knight Walking_A --version 1 --library $library
```

The inspection report records bone names, parents and rest matrices, a stable skeleton hash, weighted mesh count, validated KayKit humanoid roles, source action ranges and facial control availability. The canonical map covers root, pelvis, spine, chest, head, limbs, hands, feet and toes for the inspected rig family. Unknown hierarchies have no inferred canonical map. Imports retain the armature and skin intact. A normalization parent centers/scales skinned bounds and grounds the rest pose; source root motion and animation poses can depart from that ground plane.

```json
{
  "id": "knight",
  "asset": { "id": "kaykit-knight", "version": 1 },
  "rigged": true,
  "normalize": "unit",
  "pivot": "base",
  "location": [0, 0, 0],
  "clips": [
    { "name": "Idle", "start_frame": 1, "frame_count": 12 },
    { "name": "Walking_A", "start_frame": 13, "frame_count": 24, "loop": true },
    { "name": "Cheer", "start_frame": 37, "frame_count": 12 }
  ]
}
```

Event intervals are start-inclusive and end-exclusive. Clips are imported at a fixed 30 fps source clock, then converted to the project fps and requested speed. Clip lengths must fit the source duration unless looping is requested. Compatible actions are assigned to their original slots in editable Blender NLA tracks. Sequential clips, speed, truncation, looping and a limited blend-in are supported. Blend-in uses the underlying pose, with no automatic transition matching or root-motion extraction. An explicit scene transform can move an in-place walk. Zero-duration poses do not count as clips.

For rigid equipment, use `"equipment": {"right_hand":"prop"}` and define a separate approved static asset entity named `prop`. Its transform becomes local to the mapped hand bone and inherits actor normalization and scale. Equipment must have a single owner. Adjust the local transform for the specific actor/prop. Skin fitting, wardrobe variants and arbitrary bone retargeting are future work.

Both acquired KayKit humanoids report the same measured rest-skeleton hash and 69 nonzero-length clips apiece. Compatibility is limited to an action present on the exact pinned version. The original `atlas-face-1` remains available for the V0.5 courtyard, where the two KayKit rigs handle body animation. Clip timing, skin deformation, an attached prop, packed textures and editable NLA strips were checked after reopening a real Blender scene.

## Generated humans in schema 1.4

`characters generate` calls the pinned MPFB extension in a separate Blender profile. The five specs in `examples/humans` set age, build, musculature, height, proportions, gender, ancestry, skin, hair and wardrobe on the same rig family. MPFB's gender slider runs from 0 (female) to 1 (male). The command exports a packed source blend, an embedded GLB, a generation report and an inspected registry version.

The separate `human` profile admits a small fixed set of position morphs, a single weighted skeleton and bone transform actions. `mpfb-visemes-1` maps Rhubarb A–H to MPFB Meta visemes. Rest resets the mouth and jaw. Blinks use explicit frame numbers, and jaw and brows use measured cue timing. Face keys and armature actions stay editable on separate Blender tracks. The quality of these first assets depends on clothing fit, lighting and camera distance. Clip compatibility remains scoped to the exact registered version.

`HumanIdle` and `HumanPresent` are source-authored 3-second upper-body clips. The generator binds them to each MPFB rest rig. Locomotion, motion capture, cross-rig transfer, production eyelid collision, cloth simulation and independently authored historical wardrobe are open. See the [V0.5.1 commands and evidence](V051_DEMOS.md).
