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

## Version 0.2 asset slice

The paragraph above describes the 0.1 baseline. Asset import is now implemented and timed. Other unmeasured quantities remain unmeasured. Same machine/runtime; engine version 0.2.0, no new runtime packages. Original lantern: 8 mesh parts, 1144 polygons, 3 materials, dimensions 1.5 x 1.5 x 2.825 meters after Blender coordinate conversion, no image textures.

Initial isolated inspection measured 0.438 s inside Blender and 2.987 s for the whole Blender process. This is one observation, not a throughput guarantee. The final report is refreshed after review hardening. Asset bytes are identical in both videos (hash recorded in [asset evidence](evidence/2026-11-23-assets.json)).

| Project | Instances | Resolution | Frames/fps | Scene build | Frame rendering | Encoding | Total | Job disk* |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| lantern-studio | 1 | 640x360 | 48/24 | 0.638 s | 53.34 s | 0.309 s | 57.61 s | 10.92 MiB |
| lantern-courtyard | 2 | 640x360 | 48/24 | 1.506 s | 57.78 s | 0.181 s | 63.93 s | 10.65 MiB |

Both are two-second Eevee previews requesting 32 samples. *Disk includes local GLB copies, PNG frames, .blend, logs and video before terminal manifest replacement. Unit/integration work ran concurrently during parts of these runs. They are acceptance measurements, not controlled comparisons against the lower-resolution 0.1 videos.

Frame 24 was visually inspected and retained for each project. Imported materials, geometry and multiple instances are visible; sampling noise is present. Both had zero origin-visibility warnings. The example videos precede the review fixes; final-code tests and an installed-wheel production run exercise the hardened importer, exact vertex bounds, texture loading and inspection proof. No shared-mesh cache, third-party pack benchmark or peak-memory measurement has been added.

## Version 0.3 batch and thumbnails — 2026-11-24

Same machine/runtime. The final installed 0.3 wheel ran from outside the checkout working directory. An original six-file collection had five selected GLBs: three succeeded (including duplicate bytes with separate provenance), corrupt/unreviewed inputs failed independently, and unsupported OBJ was skipped. End-to-end batch time was **49.67 seconds**. Three records share two unique registry blobs. New batch/thumbnail staging directories contain no remaining GLB copies; existing inspection diagnostics and production snapshots retain their own copies.

| Asset | Import inside thumbnail worker | Thumbnail rendering | Reported thumbnail total* | Complete batch item |
|---|---:|---:|---:|---:|
| beacon-copy | 1.03 s | 4.03 s | 9.17 s | 14.92 s |
| beacon | 1.11 s | 4.18 s | 9.23 s | 14.74 s |
| crate | 1.40 s | 4.61 s | 14.12 s | 19.95 s |

Previews are 256x256 PNG, CPU Cycles, 24 samples, four threads. *The thumbnail report timestamp precedes final registry evidence validation/persistence; complete batch-item time includes registration, inspection and thumbnail completion. Hash deduplication avoids duplicate registry blobs; it does not cache inspection or preview work.

The installed package then rendered `06_batch_showcase.json`: two imported originals, Eevee, 480x270, 24 frames at 24 fps, one-second verified H.264/yuv420p MP4. Blender process took 39.23 seconds, encoding 0.44 seconds and complete production 41.17 seconds. Retained job size at measurement was 3,476,093 bytes (~3.32 MiB), including sources, frames, scene and video before terminal manifest replacement.

Both distinct previews and video frame 12 were visually inspected and retained alongside [machine-readable evidence](evidence/2026-11-24-batch.json). Geometry is visible and framed; the models are simple originals and video sampling noise remains visible. Other tests ran during parts of these observations. These are one-run small-collection acceptance measurements, not controlled performance comparisons, large-library throughput or third-party pack acceptance. Peak memory and final-quality rendering remain unmeasured.

## V0.4 and V0.5 observations

V0.4 generated 4.27 seconds of mono 24 kHz Chatterbox-Turbo speech. CPU model load and two segment inferences took 34.84 seconds on the Intel Core 7 240H. The verified WAV contained 102,480 samples and zero clipped samples. The enrolled local model is approximately 2.99 GB and the runtime is separate. V0.5 reused that exact checked speech and its measured 29-cue Rhubarb timeline.

The V0.5 starter acquisition stored 26,160,115 bytes of original archive and media blobs across 19 unique files. The 12 registry GLBs total 7,758,180 bytes. Inspection loads took about 0.52–0.59 seconds for the static objects and 2.75–2.93 seconds for the two humanoids in the observed Blender runs. Normalization preserves the rig and applies a parent transform. Its standalone cost was not sampled. The exact per-file transfer and inspection data appear in the evidence JSON. These single-machine observations include development and some concurrent load.

| Preview | Frames at 12 fps | Duration | Total production |
|---|---:|---:|---:|
| Acquired assets | 48 | 4.00 s | 58.62 s |
| Source rig showcase | 48 | 4.00 s | 43.79 s |
| Talking character | 58 | 4.83 s | 61.40 s |
| Medieval courtyard | 72 | 6.00 s | 80.21 s |

The first, second and fourth previews are 480×270. The talking preview is 360×360. All are H.264/yuv420p with complete decode verification. The spoken previews have measured stereo 48 kHz AAC streams. Frame inspection confirms visible textured geometry, different body poses and an active mouth shape. It is visual spot checking, with no automated judgement of acting, style or historical accuracy.
