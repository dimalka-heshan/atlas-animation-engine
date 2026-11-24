# Audio versions and narration production

Audio input is explicit. The optional voice subsystem generates WAV plus measured/cache/model provenance. The audio library separately records the operator's approved usage before a clip enters video production. Imported recordings use the same workflow; no voice provider is silently substituted.

## Import and version

```powershell
atlas audio import speech.wav --id narrator-line --provenance speech.provenance.json --library assets/audio
atlas audio list --library assets/audio
atlas audio show narrator-line --version 1 --library assets/audio
```

The provenance contract extends the asset declaration (`name`, `creator`, source URL/URN, supported license ID and exact license text, approval/render permission, attribution/restrictions) with `voice_origin: synthetic|recording`. Recordings also require `voice_owner` and `consent_to_use: true`. This is a declared permission record, not independent ownership verification. Reference cloning has its own stricter voice-profile approval. Do not relabel someone else's recording as generated.

The local SQLite schema1 stores immutable `(id,version)` records and SHA256-deduplicated WAV blobs. Unchanged registration is idempotent; changed bytes/provenance increments the version. Resolution rechecks rights, source hash and actual decoded PCM metadata. Registration accepts PCM16 mono/stereo WAV, 8–192kHz, at most64MiB; the shared verifier rejects empty/truncated/effectively silent or pathologically clipped input. Unsupported compressed/float input must first be explicitly converted to PCM16; ATLAS does not guess source licensing during conversion.

## Schema1.2 timeline

```json
{
  "schema_version": "1.2",
  "id": "narration-example",
  "render": {"frames":120,"fps":24},
  "scene": {"entities":[{"id":"subject","primitive":"cube"}]},
  "audio": [{"id":"introduction","clip":{"id":"narrator-line","version":1},
             "role":"narration","start_seconds":0.2,"gain":0.8}]
}
```

Roles are narration/dialogue. Dialogue can name its `speaker`; facial performance requires the same actor ID. Events need unique IDs and finite nonnegative offsets; gain is greater than zero and at most one. This first production profile is limited to180 seconds and100 audio events. The actual offset plus WAV duration must fit the video, or validation fails before Blender starts with an instruction to extend `render.frames` or move the event. No implicit trimming, speeding speech or text-length timing is used.

Audio requires schema1.2. Schema1.0/1.1 reject audio and retain strict silent-video verification. Merely accepting schema1.2 does not change a silent project's output contract.

## Production and verification

Approved audio is copied into the job and hash-checked. `audio-manifest.json` and `audio-attributions.txt` retain version/provenance/timing; original voice-generation cache evidence is referenced by the provenance source URL/URN. FFmpeg resamples to48kHz stereo, applies explicit gains and delays on a sample clock (nearest sample, half up), mixes without implicit normalization, pads to the configured video duration, and rejects a clipped mix. The verified mix is saved as `audio-mix.wav` and attached to the editable Blender scene for playback. 3D image rendering remains independent of the sequencer.

Silent video is encoded first, then muxed with AAC audio at192kbps. Validation requires exactly one H.264/yuv420p video stream and one AAC48kHz stereo stream, expected frames/fps/dimensions/duration, near-zero audio stream start and bounded audio/video duration difference. Full FFmpeg decode runs before success is recorded. The WAV sample count is checked against the planned duration. These checks verify technical timing/integrity, not speech pronunciation or perceptual synchronization.

Duplicate voices or overlapping tracks can clip; lower event gains when reported. There is no automatic loudness normalization, ducking, fades, music/SFX workflow, captions, queue/resume or arbitrary audio-file parser in this release. AAC can introduce small coding changes; clipping detection currently evaluates the PCM mix. Whole-shot render caching is not implemented; speech segment caching is separate.
