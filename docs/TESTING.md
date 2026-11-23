# Testing

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
