# Reproduce ATLAS V0.5.2

Use a fresh working library for version-1 references in these examples. The commands were exercised on Windows with Blender 5.2.3 LTS and local FFmpeg. [Host setup](../README.md) · [MPFB and local speech setup](V051_DEMOS.md)

## Acquire and inspect Poly Haven models

```powershell
$python = '.\.venv\Scripts\python.exe'
$cache = 'outputs/v052-acquisition'
$library = 'outputs/v052-library'
$audio = 'outputs/v052-audio'
$renders = 'outputs/v052-renders'
& $python -m apps.cli assets sync polyhaven --cache $cache
& $python -m apps.cli assets variants polyhaven-modular_fort_01 --cache $cache
$models = [ordered]@{
  modular_fort_01='2k'; large_castle_door='2k'; gothic_statue='2k'; chinese_screen_panels='1k'
  boulder_01='1k'; fern_02='1k'; dead_tree_trunk='1k'; fir_sapling='1k'; pine_roots='1k'
}
foreach ($slug in $models.Keys) {
  & $python -m apps.cli assets download "polyhaven-$slug" --resolution $models[$slug] --cache $cache --library $library
  if ($LASTEXITCODE -ne 0) { throw "Download failed for $slug" }
  & $python -m apps.cli assets inspect "polyhaven-$slug" --version 1 --library $library
  if ($LASTEXITCODE -ne 0) { throw "Inspection failed for $slug" }
}
foreach ($slug in 'misty_pines','forest_ground_04','secluded_beach','cobblestone_05') {
  & $python -m apps.cli assets download "polyhaven-$slug" --resolution 1k --cache $cache
}
& $python -m apps.cli assets select examples/asset_requirements/fortification.json --cache $cache --library $library --seed 282
```

`--resolution auto --max-texture-size 2048 --budget-mib 64` chooses the largest advertised supported variant that fits both limits. The original download is cached separately from the inspection-ready GLB. `ATLAS_ASSET_CACHE_MIB` defaults to 5120 MiB per source cache, and `assets storage` reports actual source and production storage separately. Keep using the exact fingerprints in the example project if source bytes match. If a provider publishes new bytes, verify their provenance and explicitly update the media fingerprints.

## Derive the fort and generate the speaker

```powershell
$parts = [ordered]@{
  'fort-gate'='wall_thin_gate_01'; 'fort-wall'='wall_thin_straight_01'
  'fort-tower'='tower_round'; 'fort-stairs'='wall_stairs_straight_01'
}
foreach ($part in $parts.Keys) {
  & $python -m apps.cli assets derive-module polyhaven-modular_fort_01 --version 1 `
    --node "modular_fort_01_$($parts[$part])" --output-id $part --library $library
  if ($LASTEXITCODE -ne 0) { throw "Fort module derivation failed for $part" }
}
& $python -m apps.cli characters generate examples/humans/curator.json --runtime outputs/v051-mpfb --library $library
& $python -m apps.cli assets collections
```

The kit originally lays out parts for browsing. Derivation keeps each selected piece's source geometry and materials and clears the presentation offset. The collection places the inspected pieces in meters and pins their derivatives. The fort is an interpretation assembled from a modular asset. [Poly Haven Modular Fort 01](https://polyhaven.com/a/modular_fort_01)

## Prepare the new narration

Use the approved bundled voice profile `atlas-demo` from [V0.5.1 setup](V051_DEMOS.md).

```powershell
$line = 'The stone gate marks the narrowest part of the approach. From here, we can see the layered walls and the path into the courtyard.'
$take = & $python -m apps.cli voice generate atlas-demo --library outputs/v04-voices --text $line | ConvertFrom-Json
$sidecar = 'outputs/v052-fort-voice-provenance.json'
@{
  name='Fort approach line'; creator='ATLAS original text with Resemble AI Chatterbox-Turbo'
  source_url="urn:atlas:voice:$($take.cache_key)"; license_id='LicenseRef-ATLAS-Generated'
  license_text='Original demonstration script synthesized locally with MIT-licensed Chatterbox-Turbo and its bundled voice. Authorized for this ATLAS demonstration.'
  approval='approved'; render_allowed=$true; voice_origin='synthetic'
} | ConvertTo-Json | Set-Content -Encoding utf8 $sidecar
& $python -m apps.cli audio import $take.wav_path --id fort-line --provenance $sidecar --library $audio
Set-Content -Encoding utf8 outputs/v052-fort-transcript.txt $line
& $python -m apps.cli lipsync align $take.wav_path --transcript-file outputs/v052-fort-transcript.txt --output outputs/v052-fort-timeline.json
```

The project includes the measured timeline and original WAV hash. Use the new timeline and actual version if you generated different WAV bytes. Allow the whole utterance and its start offset to fit in the render.

## Render and verify

Acquire and register `blendkit-small-wooden-table@1` with the verified add-on workflow first. [Blendkit walkthrough and exact local command](BLENDKIT.md)

```powershell
$fort = 'examples/collections/stone_fort_approach.json'
& $python -m apps.cli render examples/19_photo_woodland.json --asset-library $library --asset-cache $cache --output $renders --environment-collection examples/collections/photo_woodland.json
& $python -m apps.cli render examples/20_fort_approach.json --asset-library $library --asset-cache $cache --audio-library $audio --output $renders --environment-collection $fort
& $python -m apps.cli render examples/21_fort_cinematic_still.json --asset-library $library --asset-cache $cache --output $renders --environment-collection $fort
& $python -m apps.cli render examples/22_blendkit_table.json --asset-library $library --output $renders
$env:ATLAS_INTEGRATION = '1'
$env:ATLAS_VOICE_INTEGRATION = '1'
$env:ATLAS_ACQUIRED_INTEGRATION = '1'
$env:ATLAS_MPFB_INTEGRATION = '1'
$env:PYTHONUTF8 = '1'
& $python -m pytest -q --junitxml=outputs/v052-final-tests.xml
```

Sketchfab discovery can run separately through `assets sync sketchfab --query 'castle' --cache $cache`. Downloads require authorized credentials and a qualifying catalog record. [Sketchfab authentication and acquisition](SKETCHFAB.md)

Each completed job contains a verified video, exact asset and media pins, the editable scene and time measurements. Keep editable projects with private Blendkit derivatives on local storage. [Delivery report](V052_REPORT.md)
