# Reproduce the V0.5 demonstrations

Acquire and inspect the starter collection using [ACQUISITION](ACQUISITION.md). These demonstrations use the actual Turbo WAV and Rhubarb timing from V0.4. This workspace retains the registered clip at `outputs/v04-audio`, ID `atlas-line@1`. Voice and alignment installation are documented in [VOICE](VOICE.md) and [LIPSYNC](LIPSYNC.md).

```powershell
$python = '.\.venv\Scripts\python.exe'
$library = 'outputs/v05-library'
$cache = 'outputs/v05-acquisition'
$collection = 'examples/collections/medieval_village.json'
$audio = 'outputs/v04-audio'
& $python -m apps.cli render examples/09_acquired_assets.json --asset-library $library --asset-cache $cache --environment-collection $collection
& $python -m apps.cli render examples/10_acquired_character.json --asset-library $library
& $python -m apps.cli render examples/07_talking_head.json --audio-library $audio
& $python -m apps.cli render examples/11_medieval_courtyard.json --asset-library $library --audio-library $audio --environment-collection $collection
```

The collection format pins static asset IDs and versions and declares reusable placement. Both the showcase and courtyard load the same collection via a trusted host CLI argument. The effective merged JSON is retained inside each render job. Duplicate entity identifiers and rigged entries in a static collection fail validation.

For a fresh workspace, create a bundled Turbo voice, generate the original text “Hello, I am Atlas. My voice and animation run locally.”, and register the WAV using `atlas audio import` with an explicit provenance sidecar. Run `atlas lipsync align` against the exact generated WAV and transcript. Replace the inline timeline in examples 07 and 11 with that generated timeline, and pin your audio ID/version. Adjust render frames to contain the measured duration plus the configured offset. The recorded sample used 4.27 seconds of CPU-generated audio and 29 Rhubarb cues. The manifest retains each exact clip hash.

Use the output manifest for dimensions, decoded frame count, durations and hashes. The engine checks and decodes the final MP4 before marking success. PNGs and an editable scene.blend are retained locally. The medieval preview is a stylized village arrangement, with no claim of historical authenticity. The generated speaker uses its own facial profile; the two imported humanoids use source body animations.
