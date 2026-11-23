# ATLAS

A local, configuration-driven 3D animation engine. Version 0.1 implements the first working production slice: JSON -> procedural scene -> Blender PNG frames -> FFmpeg H.264 MP4 -> independent verification.

Change JSON to produce a different video. No paid AI, downloaded assets, browser service or coding assistant is required during production. This is an early foundation, not the complete platform described in the roadmap.

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

Verify a video using its saved effective project (especially after `--engine` overrides):

```powershell
.\.venv\Scripts\atlas.exe verify 'outputs\JOB\video.mp4' --project 'outputs\JOB\project.json'
```

## Configure a new scene

Copy an example JSON and change its `id`, geometry, materials, transforms, keys, camera, lights, scatter seed or resolution. Coordinates are meters, right-handed Z-up; rotations are Euler XYZ degrees. Primitive dimensions and schema details are in [ARCHITECTURE](docs/ARCHITECTURE.md).

`render.frames` is inclusive from frame 1; duration is `frames / fps`. Keyframes have increasing unique integer frames within that range. Location, rotation and scale can be keyed independently. A base transform key is inserted at frame 1 for each animated channel. Interpolation supports LINEAR, BEZIER and CONSTANT. Camera location is animated while its orientation tracks a fixed point or explicit entity.

Default rendering is CPU Cycles at 320x180, 48 frames, 24 fps, 16 samples, 8 threads. Examples use Eevee at 480x270 or 270x480 for three seconds. For final output, increase resolution and samples in JSON after checking a preview. Both dimensions must be even. Higher settings can substantially increase render time and disk usage.

Seeded scatter provides minimum XY center spacing within each group; it does not test mesh collisions or avoid other groups. Primitive assets are reusable without third-party files. No character rigging, semantic actions, imported asset libraries, multi-shot editing or audio is claimed in this release.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$env:ATLAS_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

See [STATUS](docs/STATUS.md), [TESTING](docs/TESTING.md), [PERFORMANCE](docs/PERFORMANCE.md), [ROADMAP](docs/ROADMAP.md), [ASSET_LICENSING](docs/ASSET_LICENSING.md) and [DEVELOPMENT_HANDOFF](docs/DEVELOPMENT_HANDOFF.md).
