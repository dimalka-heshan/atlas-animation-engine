# Reproduce the V0.6 previews

Use the host setup in [README](../README.md). Acquire the pinned KayKit Adventurers source and inspect `kaykit-knight@1` via [ACQUISITION](ACQUISITION.md). Generate the curator and scholar with the pinned [MPFB runtime](V051_DEMOS.md). The fort also needs the matching models and environmental media, and the `fort-line@1` Chatterbox-Turbo WAV from [V0.5.2](V052_DEMOS.md).

```powershell
$python = '.\.venv\Scripts\python.exe'
$source = 'outputs/v05-library'
$library = 'outputs/v052-library'
$motion = 'outputs/v06-release-motions'
$out = 'outputs/v06-previews'
$runtime = 'outputs/v051-mpfb'
& $python -m apps.cli characters generate examples/humans/curator.json --library $library --runtime $runtime
& $python -m apps.cli characters generate examples/humans/scholar.json --library $library --runtime $runtime
& $python -m apps.cli characters rigs --library $library
& $python -m apps.cli animations list --character kaykit-knight --library $source
& $python -m apps.cli animations retarget kaykit-knight Walking_A mpfb-curator --id curator-walk --source-library $source --library $library --motion-cache $motion
& $python -m apps.cli animations retarget kaykit-knight Walking_A mpfb-scholar --id scholar-walk --source-library $source --library $library --motion-cache $motion
& $python -m apps.cli animations retarget kaykit-knight Running_B mpfb-curator --id curator-run --category run --source-library $source --library $library --motion-cache $motion
& $python -m apps.cli motions list --motion-cache $motion
```

Skip generation when the exact assets already exist at version 1. Compare the emitted `motion` pins with the configuration. A different Blender build, target hash or worker revision can yield different motion hashes. Replace each pin with the actual reviewed output in your copy of the example. For fresh speech, replace the inline facial timeline with the one measured for the actual WAV and confirm that the cue timing and audio offset fit the shot.

```powershell
& $python -m apps.cli navigation plan examples/23_v06_guided_walk.json --asset-library $library --motion-cache $motion
& $python -m apps.cli actions compile examples/23_v06_guided_walk.json --asset-library $library --motion-cache $motion
& $python -m apps.cli render examples/23_v06_guided_walk.json --asset-library $library --motion-cache $motion --output $out
& $python -m apps.cli render examples/24_v06_fort_walking_dialogue.json --asset-library $library --motion-cache $motion --asset-cache outputs/v052-acquisition --audio-library outputs/v052-audio --environment-collection examples/collections/stone_fort_approach.json --output $out
& $python -m apps.cli render examples/25_v06_parallel_walk.json --asset-library $library --motion-cache $motion --output $out
& $python -m apps.cli render examples/26_v06_walk_run_study.json --asset-library $library --motion-cache $motion --output $out
```

Use each returned manifest to locate the job. Open `scene.blend` and inspect the actor's NLA strips, destination and frame boundaries. `movement-plan.json` records planned actions where used. Each video has a matching `project.json` for `atlas verify VIDEO --project PROJECT`. The manual gait study uses authored root keys and a grounded run without a flight phase. It is a transition diagnostic.

## Fort cut with a gesture after arrival

Compile the exact routes from example 24, then append a pinned local gesture while the curator is already standing and speaking.

```powershell
$gesture = (& $python -m apps.cli animations retarget kaykit-knight Cheer mpfb-curator --id curator-cheer --category gesture --no-ground --source-library $source --library $library --motion-cache $motion | ConvertFrom-Json).motion
$scene = (& $python -m apps.cli actions compile examples/24_v06_fort_walking_dialogue.json --asset-library $library --motion-cache $motion | ConvertFrom-Json).compiled_project
$scene.id = 'fort-approach-and-gesture'
$scene.render.frames = 82
$scene.render.width = 320
$scene.render.height = 180
$scene.render.samples = 3
$scene.scene.camera.keyframes[-1].frame = 82
foreach ($actor in $scene.scene.entities) { $actor.clips[0].frame_count = 82 }
$curator = $scene.scene.entities | Where-Object id -eq curator
$curator.clips += @{name='curator-cheer'; motion=$gesture; start_frame=55; frame_count=16; blend_frames=3; blend_out_frames=3; overlay=$true}
$scene | ConvertTo-Json -Depth 50 | Set-Content -Encoding utf8 outputs/v06-fort-gesture-project.json
& $python -m apps.cli render outputs/v06-fort-gesture-project.json --asset-library $library --motion-cache $motion --asset-cache outputs/v052-acquisition --audio-library outputs/v052-audio --environment-collection examples/collections/stone_fort_approach.json --output $out
```

## Regression tests

```powershell
$env:ATLAS_INTEGRATION = '1'
$env:ATLAS_VOICE_INTEGRATION = '1'
$env:ATLAS_ACQUIRED_INTEGRATION = '1'
$env:ATLAS_MPFB_INTEGRATION = '1'
$env:ATLAS_MOTION_INTEGRATION = '1'
$env:PYTHONUTF8 = '1'
& $python -m pytest -q --junitxml=outputs/v06-verified-tests.xml
```

Set `ATLAS_MOTION_SOURCE_LIBRARY` and `ATLAS_MOTION_TARGET_LIBRARY` when the locally approved source or human library is elsewhere. The motion test uses a temporary bake cache and verifies that the second bake hits it.
