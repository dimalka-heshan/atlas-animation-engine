# Testing

V0.6 motion tests cover hashed aliases, exact target versions, collision and route rejection, alternate approach stops, scheduled facing, overlap and root timing. With `ATLAS_MOTION_INTEGRATION=1`, a real KayKit clip is baked onto MPFB, resolved from cache, rendered through the production pipeline and checked after reopening the scene. [Fixture setup and test commands](V06_DEMOS.md)

V0.5.2 provider tests use offline HTTP and archive fixtures by default. `ATLAS_INTEGRATION=1` runs the native conversion tests with real Blender, including packed image and material retention, rejected input, and saved-scene verification. The delivery report records separate permitted live discovery, actual acquisitions, and demo jobs. [V0.5.2 results](V052_REPORT.md)

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$env:ATLAS_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest -q
```

Ordinary tests do not require Blender. Integration tests are skipped unless explicitly enabled; a skip is not a render pass. With integration enabled, missing tools cause failures rather than silent skips.

## Coverage

- Schema roundtrip/defaults; unsupported schema/fields, unsafe IDs, odd dimensions, invalid frame counts/fps/seeds, invalid geometry/scale/nonfinite vectors, broken/duplicate timelines, missing camera targets and duplicate IDs.
- Repeatable scatter, source immutability, actual XY separation, different seeds, impossible placement failure.
- Output containment, atomic replacement, SQLite persistence, real subprocess failures/timeouts, failed render status and retained manifest.
- Independent hand-authored ffprobe metadata contract and rejection of wrong dimensions, frame count, codec, pixel format, fps or duration.
- Actual CLI subprocess validation, JSON Schema generation, missing/malformed projects, all examples.
- Real CPU Cycles and Eevee: three PNG frames at 64x64, H.264 export and full decode, saved .blend reopened in a new Blender process; midpoint position and camera target independently asserted. First/last PNGs differ.
- Review regressions: container duration/format and ancillary stream rejection, final-manifest/provenance failure persistence, missing-history read-only behavior, unchanged database bytes, directional aim validation, extreme numeric input, and API mutation revalidation.
- Reopen a rendered seven-primitive scene to verify rotation/scale interpolation, moving camera, mesh geometry and depth-of-field state. Failure injection at the manifest I/O boundary verifies real render finalization errors cannot leave a successful job record.

## Acceptance workflow

Render each example through the CLI; check terminal status, manifests, expected frame counts and ffprobe properties, then inspect representative images. Use saved effective `project.json` when independently verifying output. The production pipeline checks every output, and FFmpeg decodes all frames before publishing the MP4.

Clean-install acceptance builds a wheel plus dependency wheels, installs into a fresh venv, calls the installed CLI outside the repository, then renders a tiny video. This checks that `worker.py` ships in the wheel and does not depend on the working directory.

Record actual counts and artifact evidence in STATUS/PERFORMANCE. Automated visibility warnings inspect object centers only; they do not certify silhouette framing, absence of obstruction, scene beauty, smooth motion or physical realism.

Set `ATLAS_MPFB_INTEGRATION=1` after running `characters install-mpfb`. The test generates or reuses a pinned real human, registers it in a disposable library, and reopens a Blender scene to verify the jaw, both blinks, resting mouth, weighted rig and independently changing head transform. Set `ATLAS_MPFB_RUNTIME` for an installation outside `outputs/v051-mpfb`.

## Asset regression coverage (0.2)

Unit tests cover registry migrations/refusal of unknown versions, deduplication with independent provenance, immutable version history, deterministic literal search, missing/tampered blobs, approval/permission/attribution/restriction gates, malformed provenance URLs, SQLite integer bounds, and inspection evidence/hash binding. The bounded GLB profile rejects corrupt chunks, external/data URIs, unsupported animation/skins/extensions/morphs, missing texture sources, alternate/unreachable/cyclic scene nodes and nonsurface primitive modes. Schema tests preserve old projects and reject ambiguous/path-bearing/unpinned references. CLI tests execute actual register/search/show commands and check absent-library behavior.

Blender integration tests generate original geometry, register and inspect it, render it in two configurations, then reopen scenes to verify hierarchy, scale, base pivot and rotation. Additional real GLBs exercise a rotated triangle (exact vertex bounds), a valid embedded 2x1 PNG (lazy decoding), a corrupt embedded PNG (failed status), and a missing executable (failed inspection). Imported asset demos and an installed-wheel render supplement these tests. Test fixtures contain no third-party assets.

## Batch and thumbnail coverage (0.3)

Tests cover stable inventory, explicit selection, sidecars, independent duplicate provenance/idempotence, source/metadata changes, corrupt/unapproved inputs, disjoint roots, traversal, real Windows directory junctions, cancellation state, nonregular descriptors and staging cleanup. A migration test preserves v1 versions and inspection evidence. CLI subprocesses exercise scan, refused plan overwrite and partial failure exit code 2.

Real Blender thumbnails verify dimensions, pixel variation, persisted source/image hashes, image tampering, missing executables and required inspection. PNG regressions reject uniform colored images, missing IEND and corrupt chunk CRC even when FFmpeg can decode them. Public ready-state persistence cannot bypass successful inspection. Review failures and the final full-suite output are retained under outputs/batch-review-red.log and outputs/batch-full-suite-final.log.

The installed-wheel acceptance uses an original six-file collection outside the checkout working directory, explicitly selects five GLBs, expects three successes/two failures/one skip, and renders the two distinct approved assets through the regular production pipeline. Thumbnail images and a representative video frame are visually inspected. Performance observations cover this small collection only.

## V0.4 and V0.5 regression commands

```powershell
$env:ATLAS_INTEGRATION = '1'
$env:ATLAS_VOICE_INTEGRATION = '1'
$env:ATLAS_ACQUIRED_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest -q --junitxml=outputs/v05-final-tests.xml
```

Voice integration uses the pinned downloaded Turbo model and isolated Python. Rhubarb uses the installed executable and local fixture. The acquired-rig integration requires the locally downloaded and inspected KayKit Knight and crate. Set ATLAS_ACQUIRED_LIBRARY to override outputs/v05-library. The test reopens the generated blend and checks skin weights, actual per-frame pose and skin changes, packed images, editable action slots, hand attachment motion, clip boundary precedence and rest after the final clip. The suite normally does not perform any live catalog network requests.

Offline tests cover ZIP traversal, special or executable members, bounded download integrity and cache hits, glTF dependency restrictions, catalog filtering/paging/seed stability, historical media replay and changed blobs, project version gating, clip intervals and environment collection reuse. Live acceptance additionally downloads official assets, decodes all seven acquired Poly Haven media sets in Blender, inspects all 12 acquired GLBs and verifies four complete MP4 previews. Exact final counts and skips appear in STATUS.
