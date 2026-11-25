# Reproduce ATLAS V0.5.1

These commands were exercised on Windows with Python 3.14, Blender 5.2.3 LTS and FFmpeg. Install the host using [README](../README.md), then follow [VOICE](VOICE.md) and [LIPSYNC](LIPSYNC.md) to install the optional speech and alignment runtimes. Only setup, acquisition and new voice generation require these optional downloads.

## Install and generate the cast

```powershell
$python = '.\.venv\Scripts\python.exe'
$cache = 'outputs/v051-acquisition'
$library = 'outputs/v051-release-library'
$runtime = 'outputs/v051-mpfb'
$audio = 'outputs/v051-audio'
$renders = 'outputs/v051-renders'
& $python -m apps.cli characters install-mpfb --runtime $runtime
Get-ChildItem examples/humans/*.json | ForEach-Object {
    & $python -m apps.cli characters generate $_.FullName --runtime $runtime --library $library
    if ($LASTEXITCODE -ne 0) { throw "Character generation failed for $($_.Name)" }
}
& $python -m apps.cli characters list --library $library
& $python -m apps.cli animations compatibility mpfb-curator HumanPresent --library $library
& $python -m apps.cli quality profiles
```

The setup uses the official MPFB 2.0.18 source tag and three official CC0 asset archives. Blender builds and installs the GPL extension in an isolated resource profile. The MPFB worker generates the character from validated parameters, fits the selected clothing, exports a packed blend and an embedded GLB, and measures the result in a new background Blender process. Keep the source downloads, generated assets and voice files outside Git. [MPFB source](https://github.com/makehumancommunity/mpfb2/tree/d0a32e57a7f915cb2f2b95410e2117648c7bbb7e) · [MakeHuman assets](https://static.makehumancommunity.org/assets/assetpacks/index.html)

## Acquire the courtyard assets

```powershell
foreach ($provider in 'polyhaven','ambientcg','smithsonian') {
    & $python -m apps.cli assets sync $provider --cache $cache
}
foreach ($slug in 'wooden_crate_01','wine_barrel_01','stone_01','coast_rocks_01','rococo-side-chair') {
    $provider = if ($slug -eq 'rococo-side-chair') { 'smithsonian' } else { 'polyhaven' }
    $resolution = if ($slug -in 'coast_rocks_01','rococo-side-chair') { '1k' } else { '2k' }
    $format = if ($provider -eq 'smithsonian') { 'glb' } else { 'gltf' }
    $id = "$provider-$slug"
    & $python -m apps.cli assets download $id --resolution $resolution --format $format --cache $cache --library $library
    if ($LASTEXITCODE -ne 0) { throw "Acquisition failed for $id" }
    & $python -m apps.cli assets inspect $id --version 1 --library $library
    if ($LASTEXITCODE -ne 0) { throw "Inspection failed for $id" }
}
foreach ($slug in 'kiara_1_dawn','kiara_2_sunrise','studio_small_03','kloofendal_28d_misty_puresky','kloofendal_38d_partly_cloudy_puresky') {
    & $python -m apps.cli assets download "polyhaven-$slug" --resolution 1k --cache $cache
}
& $python -m apps.cli assets download ambientcg-pavingstones036 --resolution 1k --format jpg --cache $cache
& $python -m apps.cli assets download ambientcg-wood099 --resolution 2k --format jpg --cache $cache
& $python -m apps.cli assets catalog 'wood' --category environment --style photorealistic --cache $cache
```

The project pins its HDRI and ground texture fingerprints. If an upstream derivative changes, compare the new source and explicitly update the two project fingerprints. Keep metric scale when placing the Smithsonian chair. The used media, including the chair's credit and authority record, are documented in [High-fidelity sources](HIGH_FIDELITY_SOURCES.md).

## Re-create the dialogue audio

```powershell
$voices = 'outputs/v04-voices'
& $python -m apps.cli voice create atlas-demo --name 'ATLAS bundled model voice' --library $voices
$lines = [ordered]@{
    'atlas-line' = 'Hello, I am Atlas. My voice and animation run locally.'
    'courtyard-question' = 'We are closing the exhibition. Could you show me the way back?'
    'courtyard-reply' = 'We should take the courtyard path. The light is beautiful this evening.'
}
foreach ($id in $lines.Keys) {
    $line = $lines[$id]
    $take = & $python -m apps.cli voice generate atlas-demo --library $voices --text $line | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Speech generation failed for $id" }
    $sidecar = "outputs/$id-provenance.json"
    @{
        name = $id
        creator = 'ATLAS demonstration text synthesized with Resemble AI Chatterbox-Turbo'
        source_url = "urn:atlas:voice:$($take.cache_key)"
        license_id = 'LicenseRef-ATLAS-Generated'
        license_text = 'Original demonstration text synthesized locally from MIT-licensed Chatterbox-Turbo and its bundled conditioning. Authorized for this ATLAS demonstration.'
        approval = 'approved'
        render_allowed = $true
        voice_origin = 'synthetic'
    } | ConvertTo-Json | Set-Content -Encoding utf8 $sidecar
    & $python -m apps.cli audio import $take.wav_path --id $id --provenance $sidecar --library $audio
    $transcript = "outputs/$id.txt"
    Set-Content -Encoding utf8 $transcript $line
    & $python -m apps.cli lipsync align $take.wav_path --transcript-file $transcript --output "outputs/$id-timeline.json"
}
```

Use a fresh voice library or skip profile creation if `atlas-demo` already exists. The examples pin timelines for exact successful WAV hashes. If a different CPU or runtime produces another WAV, replace each performance's `timeline` with the generated JSON, pin the actual audio version and check that the scheduled WAV ends within the configured video. The two courtyard characters use the same bundled synthetic conditioning.

## Render and verify

```powershell
$courtyard = 'examples/collections/stone_courtyard.json'
& $python -m apps.cli render examples/12_mpfb_talking_human.json --asset-library $library --audio-library $audio --output $renders
& $python -m apps.cli render examples/13_mpfb_cast.json --asset-library $library --output $renders
& $python -m apps.cli render examples/14_courtyard_dialogue.json --asset-library $library --audio-library $audio --asset-cache $cache --environment-collection $courtyard --output $renders
& $python -m apps.cli render examples/15_stone_courtyard.json --asset-library $library --asset-cache $cache --environment-collection $courtyard --output $renders
& $python -m apps.cli render examples/16_mpfb_showcase.json --asset-library $library --output $renders
& $python -m apps.cli render examples/17_mpfb_motion.json --asset-library $library --output $renders
& $python -m apps.cli render examples/18_courtyard_flythrough.json --asset-library $library --asset-cache $cache --environment-collection $courtyard --output $renders
$env:ATLAS_INTEGRATION = '1'
$env:ATLAS_VOICE_INTEGRATION = '1'
$env:ATLAS_ACQUIRED_INTEGRATION = '1'
$env:ATLAS_MPFB_INTEGRATION = '1'
& $python -m pytest -q --junitxml=outputs/v051-final-tests.xml
```

The cinematic defaults use Cycles at 1920 × 1080 and 128 samples. Realistic defaults use Cycles at 1280 × 720 and 64 samples. Preview and stylized use Eevee. The sample projects explicitly reduce dimensions and samples for the available hardware. The cast and courtyard stills retain Cycles. The dialogues use Eevee with the realistic look and authored lighting. Exposure, color look, linear-light intensity, color temperature, shadow switches, lens, aperture, samples, denoising and motion blur can be configured in schema 1.4. Geometry and texture budgets apply to inspected scene assets before Blender opens the job.

Open each job's `manifest.json` for frame counts, runtimes, checksums and source licenses. `scene.blend` retains editable animation and the dialogue mix reference. FFmpeg decodes the entire output before the job can succeed. See the [release report](V051_REPORT.md) and [delivery evidence](evidence/2026-11-25-v051.json).
