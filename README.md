# ATLAS

A local, configuration-driven Blender animation engine. Version 0.5.2 adds Sketchfab discovery and OAuth, reviewed Blendkit native import, expanded Poly Haven models, and selection based on verified asset quality. Start with [V0.5.2 setup and renders](docs/V052_DEMOS.md). [MPFB character generation and local voice](docs/V051_DEMOS.md) remain available.

Change JSON to produce a different video. No paid AI, browser service or coding assistant is required during production. Voice generation uses a separately installed local model. This is a working foundation; the full studio roadmap remains incomplete.

## Install (PowerShell)

Prerequisites: Python 3.11+, Blender and FFmpeg/ffprobe with libx264. The tested environment uses Python 3.14.6, Blender 5.2.3 LTS and the installed FFmpeg build recorded in `docs/PERFORMANCE.md`. Other Blender releases are not certified.

```powershell
cd C:\Dimalka\yt\blender
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\atlas.exe doctor
.\.venv\Scripts\atlas.exe validate examples\01_orbit_studio.json
.\.venv\Scripts\atlas.exe render examples\01_orbit_studio.json
```

For the exact tested dependency versions, install with `-c requirements-tested.txt`. These pins were verified with Python 3.14 on Windows; older supported Python versions may need fresh compatible resolution.

Activation is optional. `python -m apps.cli` provides the same commands from the configured environment. On Linux/macOS use `.venv/bin/python` and `.venv/bin/atlas`; these platforms have not yet been exercised.

Blender is found on PATH or under standard Windows/macOS installation directories. Explicit paths take precedence:

```powershell
$env:ATLAS_BLENDER = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
$env:ATLAS_FFMPEG = 'C:\ffmpeg\ffmpeg.exe'
$env:ATLAS_FFPROBE = 'C:\ffmpeg\ffprobe.exe'
```

`doctor` reports discovered versions, CPU, RAM and Windows GPU information. A discovered GPU is not proof that a particular render backend works: the integration tests actually exercise it. Install software separately; ATLAS does not download executables or assets automatically.

## Make videos

```powershell
.\.venv\Scripts\atlas.exe render examples\02_sunrise_grove.json --output outputs
.\.venv\Scripts\atlas.exe render examples\03_motion_columns.json --output outputs
# CPU fallback for machines where Eevee cannot initialize graphics:
.\.venv\Scripts\atlas.exe render examples\01_orbit_studio.json --engine cycles
.\.venv\Scripts\atlas.exe jobs --output outputs
.\.venv\Scripts\atlas.exe schema > project-schema.json
```

Each successful command prints absolute video and manifest paths. Every run uses a new directory, retaining earlier outputs. A job contains:

- `video.mp4`: H.264, yuv420p, exact configured frame count and frame rate.
- `frames/`: numbered PNG frames; `scene.blend`: editable scene with animation.
- `project.json`: effective input including defaults and CLI overrides; `resolved.json`: expanded placement.
- `manifest.json`: source/configuration hashes, versions, settings, output hash and measured timings.
- `blender-report.json`: per-frame timings and basic camera-center visibility warnings.
- `blender.log`, `ffmpeg.log`, `verification.log`: external process diagnostics.

`outputs/jobs.sqlite3` retains status across invocations. Errors return exit code 2; Ctrl+C returns 130. Ordinary failures retain diagnostics and a failed manifest. Power loss or force-killing the host can leave `running` records; automatic resumption is deferred. Rerun the configuration into a new job to recover manually.

## Reuse an imported model

An original generated GLB lantern and two schema 1.1 projects are included. Register it once, inspect it with Blender, then reuse it in different scenes:

```powershell
.\.venv\Scripts\atlas.exe assets register assets\fixtures\lantern.glb --id lantern --provenance assets\fixtures\lantern.provenance.json
.\.venv\Scripts\atlas.exe assets inspect lantern --version 1
.\.venv\Scripts\atlas.exe render examples\04_lantern_studio.json
.\.venv\Scripts\atlas.exe render examples\05_lantern_courtyard.json
```

See [ASSETS](docs/ASSETS.md) for provenance policy, version pinning, search, normalization, supported GLBs and custom-library commands. Older primitive-only projects remain schema 1.0.

Generate a preview of an inspected asset, or scan your own collection into an editable selection plan:

```powershell
.\.venv\Scripts\atlas.exe assets thumbnail lantern --version 1 --size 256
.\.venv\Scripts\atlas.exe assets scan 'C:\MyModels' --plan outputs\asset-plan.json
# Review the plan and sidecars; set selected=true only for assets you intend to import.
.\.venv\Scripts\atlas.exe assets batch outputs\asset-plan.json --root 'C:\MyModels' --thumbnails
```

Every scan entry starts unselected. Batch import requires approved provenance, checks reviewed hashes, and reports each file independently. `--thumbnails` includes inspection; partial failure returns exit code 2. See ASSETS for the original mixed-fixture demonstration and `examples/06_batch_showcase.json`.

Verify a video using its saved effective project (especially after `--engine` overrides):

```powershell
.\.venv\Scripts\atlas.exe verify 'outputs\JOB\video.mp4' --project 'outputs\JOB\project.json'
```

## Configure a new scene

Copy an example JSON and change its `id`, geometry, materials, transforms, keys, camera, lights, scatter seed or resolution. Coordinates are meters, right-handed Z-up; rotations are Euler XYZ degrees. Primitive dimensions and schema details are in [ARCHITECTURE](docs/ARCHITECTURE.md).

`render.frames` is inclusive from frame 1; duration is `frames / fps`. Keyframes have increasing unique integer frames within that range. Location, rotation and scale can be keyed independently. A base transform key is inserted at frame 1 for each animated channel. Interpolation supports LINEAR, BEZIER and CONSTANT. Camera location is animated while its orientation tracks a fixed point or explicit entity.

Default rendering is CPU Cycles at 320x180, 48 frames, 24 fps, 16 samples, 8 threads. Examples use Eevee at 480x270 or 270x480 for three seconds. For final output, increase resolution and samples in JSON after checking a preview. Both dimensions must be even. Higher settings can substantially increase render time and disk usage.

Seeded scatter provides minimum XY center spacing within each group; it does not test mesh collisions or avoid other groups. Primitive assets need no external files; imported static GLBs require an approved, inspected registry version. General character rigs, semantic actions and multi-shot editing remain deferred.

## Local speech, narration and talking characters

Blender remains the sole 3D backend. The optional voice runtime is isolated from the main environment and Blender. The tested CPU runtime/model revisions, install instructions and consent workflow are in [VOICE](docs/VOICE.md).

```powershell
.\.venv\Scripts\python.exe tools\install_voice_runtime.py --python C:\Python314\python.exe
.\.venv\Scripts\atlas.exe voice doctor --download-model
.\.venv\Scripts\atlas.exe voice create narrator
$speech = .\.venv\Scripts\atlas.exe voice generate narrator --text 'Hello. Welcome to ATLAS.' | ConvertFrom-Json
.\.venv\Scripts\atlas.exe voice list
```

`voice preview` creates a short WAV, `voice history` lists retained output manifests, and `--force` preserves a newly regenerated take. Reference-conditioned profiles require explicit owner/usage/consent evidence. There is no paid-service fallback. CPU performance is measured in PERFORMANCE; doctor readiness alone is not inference proof.

Register generated speech or an approved recording with `audio import WAV --id ID --provenance JSON`. Schema 1.2 projects reference immutable audio versions and measured offsets. Use `--audio-library PATH` with validate/render; legacy schema 1.0/1.1 stays silent. [AUDIO](docs/AUDIO.md) documents metadata and timing.

`lipsync align WAV --transcript TEXT --output timeline.json --executable RHUBARB` creates real audio-bound mouth cues. Embed that timeline in a schema 1.2 facial performance assigned to its dialogue event and actor. The original `atlas-face-1` character has editable shape keys; static GLBs do not become facial rigs. See [LIPSYNC](docs/LIPSYNC.md) for installation, mappings, silence and subframe timing.

Examples 07/08 reuse the verified local Turbo demonstration clip `atlas-line@1`: a talking robot bust and the existing orbit scene with narration. Their source audio, exact timeline and local library are retained in this workspace under `outputs/v04-*`; the WAV/model weights are not bundled in Git. Regenerating speech changes its hash/duration: realign it and update the example's timeline and render duration before reuse. Both examples run through the ordinary `atlas render` command.

## Acquired environments and characters

The asset CLI can synchronize the KayKit starter catalog and the live Poly Haven material and HDRI catalogs, download approved sources, and register their production derivatives. Try `assets providers`, `assets sync`, `assets catalog` and `assets download-pack`. Schema 1.3 adds pinned rigged entities, clips, hand attachments and environment media. Existing scene schemas 1.0–1.2 remain valid.

The [acquisition guide](docs/ACQUISITION.md) includes the starter download and inspection commands. The [character guide](docs/CHARACTERS.md) explains skeletal profiles, clip timing and compatibility. The [demo guide](docs/V05_DEMOS.md) reproduces all four previews through the normal CLI.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$env:ATLAS_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

See [STATUS](docs/STATUS.md), [TESTING](docs/TESTING.md), [PERFORMANCE](docs/PERFORMANCE.md), [ROADMAP](docs/ROADMAP.md), [ASSET_LICENSING](docs/ASSET_LICENSING.md) and [DEVELOPMENT_HANDOFF](docs/DEVELOPMENT_HANDOFF.md).
