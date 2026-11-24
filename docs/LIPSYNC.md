# Lip-sync foundation

ATLAS aligns existing PCM WAV speech with **Rhubarb Lip Sync 1.14.0**, then animates an original Blender talking head or explicitly mapped mesh/armature. This is coarse English mouth animation, not precise phoneme timing, linguistic forced alignment, or a full facial performance system. Audio determines timing; text is a recognition hint. There is no text-length timing fallback.

## Runtime and commands

The optional runtime runs in its own subprocess; neither the main environment nor Blender needs speech ML packages. On Windows:

```powershell
./tools/install_rhubarb.ps1
$env:ATLAS_RHUBARB = (Resolve-Path outputs/runtimes/rhubarb/Rhubarb-Lip-Sync-1.14.0-Windows/rhubarb.exe).Path
atlas lipsync doctor
atlas lipsync align recording.wav --transcript-file transcript.txt --output timeline.json
atlas lipsync validate timeline.json
```

Alternatively supply `--executable`. The installer downloads the [official versioned release](https://github.com/DanielSWolf/rhubarb-lip-sync/releases/tag/v1.14.0), checks archive SHA256 `62fa416a8d5e382a3828ee4bef358ce520d0b4cabdeaea75a7ac266d098d1fe3`, preserves the entire distribution including `res` and `LICENSE.md`, and writes `installation.json`. This checksum pins the archive downloaded during implementation; it is not a separately signed upstream attestation. Keep `res` next to the executable. Do not commit the runtime into source control.

`doctor` verifies version, reports executable hash and recognizer. Alignment has a 600-second timeout, captures process errors, validates all cues before atomically writing output, and checks the source hash again after recognition. A failed run does not produce a new successful timeline. It leaves a preexisting output file unchanged.

## Timeline contract

`engine.lipsync.align_wav(audio: Path, transcript: str, output: Path, executable=None) -> LipSyncTimeline` produces:

```json
{
  "audio_sha256": "<64 lowercase hexadecimal characters>",
  "duration_seconds": 1.0,
  "method": "rhubarb",
  "version": "1.14.0",
  "cues": [
    {"start": 0.0, "end": 0.2, "value": "X"},
    {"start": 0.2, "end": 0.7, "value": "C"},
    {"start": 0.7, "end": 1.0, "value": "X"}
  ]
}
```

Generated files additionally record transcript and executable SHA256. Duration is measured from WAV sample count/rate, not recognizer metadata. Rhubarb exports centiseconds; only the final endpoint is reconciled to sample duration, with an 11ms maximum discrepancy. Other durations, missing cues, gaps, overlaps, unsupported values, negative/nonfinite numbers, and out-of-bounds cues fail validation. Limits are 180 seconds and 10,000 cues. Silence must be represented explicitly with `X`; no gap is silently converted to speech or invented alignment. Cue objects and controls reject unknown fields.

The built-in shape values A-H distinguish closed, narrow, open, wide-open, rounded, puckered, lower-lip and tongue-associated mouth silhouettes. `X` resets to the relaxed basis shape. These are visual categories, not individual phonemes. The original simple character uses abstract silhouettes; it has no articulated tongue or moving teeth. See [Rhubarb's mouth shapes and dialog hints](https://github.com/DanielSWolf/rhubarb-lip-sync#mouth-shapes).

## Blender mapping and frame policy

`engine.adapters.blender.facial.build_talking_head(spec: dict)` creates the original `atlas-face-1` teal robot bust and returns its root. It faces local **-Y**, extends approximately from z=0 to z=2.7, and has eight mouth shape keys. The production worker applies entity transforms and transform animation to the root.

`apply_performance(root, spec: dict, fps: float)` accepts the validated timeline, `start_seconds`, optional `smoothing_seconds` (default 0.04), `profile` (default `atlas-face-1`), and optional explicit `controls`.

Frame positions are **`1 + (start_seconds + cue_seconds) * fps`**. Fractional Blender frames are preserved, avoiding cumulative integer rounding. Video frame 1 represents time zero. At 24 fps an event starting at 0.25 seconds starts on frame 7; its one-second endpoint is frame 31. Linear interpolation blends neighboring speech shapes over at most the chosen smoothing interval on each side, capped at half each cue's duration. Silence boundaries and utterance end explicitly reset all controlled values to zero. The first key is rest, so a delayed utterance cannot open the mouth before its start. Very short cues can be missed by integer video-frame sampling; this foundation does not claim frame-perfect recognition.

The default profile discovers exactly one marked mouth under the actor. Generic meshes can specify all eight independent shape keys:

```json
{
  "kind": "shape_keys",
  "object": "hero_mouth",
  "mapping": {"A":"Closed", "B":"Narrow", "C":"Open", "D":"Wide", "E":"Round", "F":"Pucker", "G":"LowerLip", "H":"Tongue"}
}
```

Generic armatures can specify one jaw bone and one Euler axis. Angles are absolute **radians**, and the controlled axis must be neutral at zero:

```json
{
  "kind": "jaw_bone", "object": "hero_rig", "bone": "Jaw", "axis": "X",
  "angles": {"A":0, "B":0.05, "C":0.15, "D":0.3, "E":0.12, "F":0.08, "G":0.03, "H":0.18, "X":0}
}
```

Controls must belong to the actor root or descendants. Missing objects, shape keys and bones are errors. Rig-specific retargeting, driver conflicts, bones with nonzero neutral angles, facial expressions and automatic rig discovery are outside this foundation. Do not place unrelated animation on the same controlled channels.

Production schema 1.2 binds a facial performance to a dialogue audio event and actor. Host integration validates actor/speaker assignment, measured duration, and WAV hash before Blender receives resolved timing. Narration needs no facial performance. The alignment file is reusable only with the exact pinned audio bytes.

## Verified local evidence

`tools/create_lipsync_fixture.ps1` generates explicit **Windows SAPI synthetic technical test speech**, not Chatterbox-Turbo output and not a cloned person's recording. It saves the voice identity, transcript and SHA256 under `outputs/lipsync-demo`. The locally available voice was Microsoft David Desktop. System voice licensing continues to apply; the fixture is not checked in or presented as a generally redistributable voice asset.

The measured 9.378367346938775-second fixture produced 52 real Rhubarb cues including all A-H shapes and X rests, with audio SHA256 `d89ff839c70b7554823080b1e41efe52efd8ad6c2e7a93ea66e82146537c12c3`. A separate digital-silence WAV produced only X. Blender 5.2 tests create and reopen a saved `.blend`, evaluate an active mouth shape, verify terminal rest, reject missing controls and evaluate a basic jaw bone.

```powershell
$env:ATLAS_INTEGRATION = '1'
python -m pytest tests/unit/test_lipsync.py tests/integration/test_facial_animation.py tests/integration/test_rhubarb_alignment.py -q
```

The real recognizer test skips if its optional runtime/fixture is unavailable. Unit tests remain independent of those downloads. A synthetic cue test exercises Blender persistence; the separate real alignment test verifies actual recognition. Neither alone is a claim of perceptual lip-sync quality: inspect the rendered talking-character preview with its audio.

## Alternatives and next work

[Montreal Forced Aligner](https://montreal-forced-aligner.readthedocs.io/en/latest/) provides a dedicated alignment stack with acoustic/language resources. [WhisperX](https://github.com/m-bain/whisperX) combines transcription with wav2vec2 alignment and optional diarization. They are candidates when phone/word-level outputs or multilingual processing justify their runtime/model requirements. Rhubarb was chosen for this small isolated English mouth-cue foundation; the timeline adapter can be replaced later without making Blender run ML code.

Next work: evaluate alignment quality on varied real speech, richer rig profiles with rest-pose calibration, reusable profile storage, improved lips/teeth/tongue geometry, and an actual editing/preview UI. Keep claims and tests distinct for recognition, temporal association, and visual quality.
