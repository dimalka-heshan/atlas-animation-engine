# Local Chatterbox-Turbo voice generation

ATLAS owns approved profiles, text segmentation, verified PCM audio, content-addressed caches and provenance. A package-owned subprocess worker runs the optional ML stack in an independent Python environment. Neither the main interpreter nor Blender imports torch. Existing silent scenes work without the optional installation.

The official source is pinned to [`ab55923c27757c90cfcc407baa57dc25a7d25217`](https://github.com/resemble-ai/chatterbox/tree/ab55923c27757c90cfcc407baa57dc25a7d25217), distribution version 0.1.7. The official Turbo model is pinned to [`749d1c1a46eb10492095d68fbcf55691ccf137cd`](https://huggingface.co/ResembleAI/chatterbox-turbo/tree/749d1c1a46eb10492095d68fbcf55691ccf137cd). The worker verifies the installed source commit, downloads only the necessary files at that immutable model revision, and calls `ChatterboxTurboTTS.from_local(..., device=..., nano=False)`. It does not silently select Nano or a remote paid provider. Source and model are MIT licensed; review the upstream terms for your production.

## Installation and diagnosis

From the repository root on Windows:

```powershell
.venv/Scripts/python.exe tools/install_voice_runtime.py --python C:/Python314/python.exe
.venv/Scripts/atlas.exe voice doctor
.venv/Scripts/atlas.exe voice doctor --download-model
```

The independent environment defaults to `outputs/voice-runtime`, and the model cache to `outputs/voice-models`. `requirements-voice-tested.txt` records the actual resolved environment. The installer does not modify the host environment. It uses the complete frozen dependency list with `--no-deps` because upstream's declared Perth dependency otherwise floats at `master`.

`--runtime-python`, `--model-cache`, `--device cpu|cuda` and `--timeout SECONDS` are available on doctor/generate/preview. Doctor reports dependency import failures, source pin mismatch, model download state, CPU availability, CUDA devices and GPU memory, free storage, and package versions. `ready` means the imports/device/model files are available; it does **not** prove inference or acceptable performance. Only a successful generation records `inference_verified: true`.

The official GitHub API reported archived=false on 2026-11-24; the archived-project statement in the brief does not match the current repository. The audited source now explicitly handles CPU/MPS checkpoint loading and Python 3.14 dependencies. Support must be established by running the pinned combination, rather than assuming the old Python/CUDA restriction still applies.

## Persistent profiles and speech

```powershell
atlas voice create narrator --name "ATLAS narrator"
atlas voice generate narrator --text "Welcome to ATLAS. This scene uses locally generated narration."
atlas voice preview narrator
atlas voice list
atlas voice history narrator
```

The no-reference profile uses the model's distributed `conds.pt` conditioning. It does not import or impersonate a selected real person. Returned `wav_path` points to actual validated audio and includes measured duration, sample rate, channel count, peak, clipping count and SHA-256. Preview generates a short audio artifact; it does not automatically play it or claim listening approval. A generated file can then be registered through `atlas audio import` with an explicit audio provenance sidecar and referenced in a project by its immutable audio version.

`VoiceLibrary(root).generate(text, profile_id, provider, settings=None)` is the host API. A replaceable provider exposes `identity` and `generate(segments, outputs, reference, settings)`; provider identity participates in cache keys. `ChatterboxProvider(runtime_python, device="cpu", model_cache=...)` is the production implementation. `engine/audio/validation.py:verify_wav(Path)` is the shared verifier.

Profiles under `assets/voices/profiles/<id>` are immutable. Use a new ID to change a reference or profile defaults. Cache manifests form a persistent output history. Deleting a profile removes its local reference, history and generated cache; exported or separately registered audio is intentionally retained.

## Reference permission and privacy

Reference WAV files must be PCM16 mono/stereo, 8â€“192 kHz, longer than five seconds and at most thirty seconds, with audible unclipped content. The model uses at most the relevant first 10â€“15 seconds internally and applies its supported loudness normalization. Approval is never inferred from a filename or from possessing a recording.

```json
{
  "approved": true,
  "owner": "The person who authorized this recording",
  "allowed_usage": "Describe the authorized production usage",
  "evidence": "Describe or reference the permission record"
}
```

```powershell
atlas voice create approved_actor --reference my-recording.wav --consent consent.json
atlas voice delete approved_actor
```

Only use `approved: true` when permission has actually been obtained. The reference is copied inside the profile and SHA-256 pinned. Changed data or removed consent is rejected before generation. Local files inherit filesystem permissions; ATLAS does not encrypt reference audio. Keep the library in an appropriately restricted user directory. Deletion is ordinary filesystem deletion, not a guarantee of forensic erasure or removal from backups.

## Segmentation, controls and cache behavior

Speech is split at sentence and paragraph boundaries with bounded word-preserving segments. Multiword tags remain intact. The controlled tags are `[laugh]`, `[chuckle]`, `[cough]`, `[clear throat]`, `[sigh]`, `[gasp]`, `[sniff]`, `[groan]`, `[shush]`, verified against the pinned model's added-token vocabulary. Other tags and unsupported controls are rejected. These are model requests, not guarantees of a particular performance.

Pass a settings JSON using `--settings settings.json`. Available settings are `seed` (default 0), `temperature` (0.8), `top_p` (0.95), `top_k` (1000), `repetition_penalty` (1.2), `segment_chars` (250), `pause_ms` (150) and `paragraph_pause_ms` (300). Turbo ignores CFG, exaggeration and min-p upstream, so ATLAS deliberately does not expose those controls. Reproducibility is tied to model/runtime/device; identical seeds do not guarantee bit-identical cross-device inference.

Use --force to regenerate into a new retained take. A different seed requests an alternate random performance; force alone does not guarantee a different waveform.

Model downloads are checked against the pinned revision's published LFS SHA256 or Git blob identities. The bounded range fallback is `python -m tools.download_voice_model` when full responses stall. It downloads about 2.99 GB and verifies hashes before publishing model files.

Cache keys include text, profile/reference/consent, source/model pin, runtime dependency versions, device, worker hash, settings and assembly version. Each cached WAV is validated and hashed before reuse. Segments are individually cached, so changing a line preserves unaffected segments. Assembly inserts explicit silence with integer sample counts and records measured segment start/duration. There is no invented text-based timing or automatic time stretching. Each segment contains the model's own ending silence; the configured pause is additional silence. This first implementation does not crossfade or optimize prosodic continuity across segments.

The WAV verifier limits inputs to 256 MiB and one hour, PCM16 mono/stereo at 8â€“192 kHz. It rejects empty, truncated, effectively silent, and pathologically clipped audio (>1% full-scale samples). Files with occasional clipping retain a measured count for review. Float/nonfinite audio is rejected by the inference worker before PCM conversion. Reference-quality recordings and natural sentence boundaries improve results; listen to takes before production approval.

## Verification boundaries

`tests/unit/test_voice_runtime.py` uses deterministic non-speech PCM fixtures for host cache/profile/validation/CLI tests. Those tests are not evidence of Chatterbox inference. The worker's JSON protocol and error handling are tested independently. Runtime/model/inference results and measurements belong in the recorded real generation manifest and project handoff. Lip synchronization is a separate measured-audio subsystem; Turbo does not return word or phoneme timestamps.
