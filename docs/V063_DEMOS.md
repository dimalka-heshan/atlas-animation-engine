# Reproduce the V0.6.3 anatomy checks and renders

Use the existing `outputs/v05-library` KayKit registry, `outputs/v052-library` MPFB actors, and matching fort media and speech from [V0.6](V06_DEMOS.md). Put the reviewed BVHs in `outputs/v063-cmu`. Their source paths and byte hashes are in `engine/characters/cmu.py`. [Pinned BVH files](https://github.com/una-dinosauria/cmu-mocap/tree/09a07f54f3bbb58797325f009282d0b2048a2871/data) · [CMU terms](https://mocap.cs.cmu.edu/)

```powershell
$python = '.\.venv\Scripts\python.exe'
$lib = 'outputs/v052-library'
$src = 'outputs/v05-library'
$motion = 'outputs/v063-library-motions'
$out = 'outputs/v063-renders'
$clips = @(
    @{Id='curator-walk'; Action='Walking_A'; Target='mpfb-curator'; Kind='walk'},
    @{Id='scholar-walk'; Action='Walking_A'; Target='mpfb-scholar'; Kind='walk'},
    @{Id='curator-idle'; Action='Idle'; Target='mpfb-curator'; Kind='idle'},
    @{Id='curator-run'; Action='Running_B'; Target='mpfb-curator'; Kind='run'},
    @{Id='curator-sit'; Action='Sit_Chair_Down'; Target='mpfb-curator'; Kind='sit'},
    @{Id='curator-stand'; Action='Sit_Chair_StandUp'; Target='mpfb-curator'; Kind='sit'},
    @{Id='curator-gesture'; Action='Cheer'; Target='mpfb-curator'; Kind='gesture'},
    @{Id='scholar-reach'; Action='Interact'; Target='mpfb-scholar'; Kind='gesture'}
)
foreach ($c in $clips) {
    $extra = if ($c.Kind -in 'sit','gesture') { @('--no-ground') } else { @() }
    & $python -m apps.cli animations retarget kaykit-knight $c.Action $c.Target --id $c.Id --category $c.Kind --source-library $src --library $lib --motion-cache $motion @extra
    if ($LASTEXITCODE -ne 0) { throw "Retarget failed for $($c.Id)" }
}
& $python -m apps.cli animations retarget-cmu outputs/v063-cmu/141_16.bvh mpfb-scholar --id scholar-cmu-wave --library $lib --motion-cache $motion
& $python -m apps.cli animations retarget-cmu outputs/v063-cmu/141_19.bvh mpfb-scholar --id scholar-cmu-walk --library $lib --motion-cache $motion
& $python -m apps.cli animations retarget-cmu outputs/v063-cmu/35_01.bvh mpfb-curator --id curator-cmu-walk --library $lib --motion-cache $motion
& $python -m apps.cli animations retarget-cmu outputs/v063-cmu/141_17.bvh mpfb-curator --id curator-cmu-sit --library $lib --motion-cache $motion
& $python -m apps.cli animations retarget-cmu outputs/v063-cmu/22_21.bvh mpfb-curator --id curator-cmu-point --library $lib --motion-cache $motion
& $python -m apps.cli animations retarget-cmu outputs/v063-cmu/141_34.bvh mpfb-scholar --id scholar-cmu-run --library $lib --motion-cache $motion
& $python -m apps.cli motions list --motion-cache $motion
```

On a different Blender build or after regenerating the humans, update the example copies with the pins emitted by the local registry. Example 29 also needs the exact legacy walk stored in the comparison cache.

```powershell
& $python -c 'import sys; from pathlib import Path; from engine.characters.motion import load_motion,store_motion; pin={"id":"curator-walk","sha256":"59b9aac5aa85108d548eb6ecba4eed9e38cf4df92eeb00a1486954af21e3b840"}; record,_=load_motion(Path("outputs/v06-release-motions"),pin); assert store_motion(Path(sys.argv[1]),pin["id"],record)==pin' $motion
& $python -m apps.cli production preview examples/29_v063_walk_comparison.json --asset-library $lib --motion-cache $motion --output $out
& $python -m apps.cli production handoff examples/30_v063_fort_handoff.json --asset-library $lib --motion-cache $motion --asset-cache outputs/v052-acquisition --audio-library outputs/v052-audio --environment-collection examples/collections/stone_fort_approach.json --output $out
& $python -m apps.cli production preview examples/31_v063_guided_anatomical.json --asset-library $lib --motion-cache $motion --output $out
& $python -m apps.cli production preview examples/32_v063_motion_sampler.json --asset-library $lib --motion-cache $motion --output $out
& $python -m apps.cli production preview examples/33_v063_captured_gestures.json --asset-library $lib --motion-cache $motion --audio-library outputs/v052-audio --output $out
& $python -m apps.cli production preview examples/34_v063_captured_run.json --asset-library $lib --motion-cache $motion --output $out
```

The editable `scene.blend` and verified MP4 are in each returned job path. To measure a saved scene, run Blender with `--background --factory-startup --disable-autoexec --offline-mode JOB/scene.blend --python-exit-code 1 --python tools/retarget_scene_report.py -- JOB`. Append `--stills 17` for matched front, rear, side and upper-body screenshots of that frame. The direct bake probe, `tools/retarget_bake_probe.py`, accepts a JSON file with local `source` and `target` GLB paths, a verified `motion` blob path and an `output` JSON path. It samples the native and baked Actions without NLA.

```powershell
$env:ATLAS_INTEGRATION = '1'
$env:ATLAS_MOTION_INTEGRATION = '1'
$env:ATLAS_HANDOFF_INTEGRATION = '1'
$env:ATLAS_CMU_INTEGRATION = '1'
$env:PYTHONUTF8 = '1'
& $python -m pytest -q --junitxml=outputs/v063-release-tests.xml
```

The data used in this project was obtained from mocap.cs.cmu.edu. The database was created with funding from NSF EIA-0196217.
