# Performance evidence

Measured on 2026-11-23 (user date), Windows 11 Pro 64-bit, Intel Core 7 240H with 16 logical CPUs, 33,271,672 KiB visible RAM (~31.73 GiB), Intel integrated Graphics. Windows reports ~2 GiB adapter memory; that value is not a measurement of usable shared GPU memory.

Runtime: Python 3.14.6, Pydantic 2.14.4, Blender 5.2.3 LTS (e13b728c6880), FFmpeg/ffprobe N-123395-gb66c314c4b-20260312. Python dependencies are pinned in `requirements-tested.txt`; full executable versions and configuration hashes are in the manifests and [evidence JSON](evidence/2026-11-23-renders.json).

## Three configuration-only example runs

All use Eevee, 16 requested samples, 72 frames, 24 fps, 3 seconds, H.264/yuv420p. Host settings request 8 rendering threads. Measurements are one run per configuration, not statistically controlled comparative benchmarks. Other development tasks were active during portions of rendering.

| Project | Size | Entities | Scene build | Frame rendering | Mean/frame | Encoding | End-to-end | Job disk* |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| orbit-studio | 480x270 | 3 | 0.195 s | 50.55 s | 0.702 s | 0.233 s | 54.28 s | 10.54 MiB |
| sunrise-grove | 480x270 | 37 | 0.264 s | 52.83 s | 0.734 s | 0.234 s | 56.60 s | 9.92 MiB |
| motion-columns | 270x480 | 4 | 0.194 s | 48.64 s | 0.676 s | 0.206 s | 52.45 s | 9.01 MiB |

*Disk includes retained PNGs, .blend, logs and video at the measurement point, before the terminal manifest replacement. It is not MP4-only size. Scene build includes materials, geometry, animation, camera, lights and .blend save; those substeps are not yet timed independently. End-to-end includes tool startup/version detection, scene work, encoding, probing and full decode validation.

Each frame time is retained in `blender-report.json`. Render work dominates these previews; encoding takes under 0.25 seconds here. These results do not predict final-resolution, imported-asset or Cycles performance. No speedup claim is made and no before/after optimization benchmark has been performed.

The examples were rendered before review hardening and reverified using the final duration/container checks. Their manifests retain the exact source hashes used for those runs. Final-code integration tests and a freshly installed wheel separately exercise the hardened pipeline.

## Quality and unmeasured work

Representative frame 36 was visually inspected for all three videos and saved under `docs/evidence/`. Objects are visible and videos are distinct. The previews show sampling noise and simple primitive scenery; they are acceptance artifacts, not a claim of finished cinematic art. No center-visibility warnings were recorded. This check cannot detect occlusion or certify full-subject framing.

Peak process/GPU memory, asset import time, separate animation preparation time, cache effectiveness, production-scale failure frequency, multi-machine behavior and final-quality performance are not yet measured. Caching and asset import do not exist yet. Tiny CPU Cycles and Eevee renders are covered by integration tests. Future benchmarking should add process memory sampling and controlled repeated profile/complexity comparisons before optimization.
