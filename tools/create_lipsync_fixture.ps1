param([string]$OutputDirectory = 'outputs/lipsync-demo')
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$fixtureDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$fixtureWav = Join-Path $fixtureDirectory 'windows-sapi-test.wav'
$fixtureText = 'Hello, I am Atlas. This is a local animation test. My mouth follows the recorded audio. Thank you.'
$speaker = New-Object -ComObject SAPI.SpVoice
$stream = New-Object -ComObject SAPI.SpFileStream
try {
    $stream.Format.Type = 22 # SAFT22kHz16BitMono
    $stream.Open($fixtureWav, 3, $false)
    $speaker.AudioOutputStream = $stream
    $speaker.Rate = 0
    $voiceDescription = $speaker.Voice.GetDescription()
    [void]$speaker.Speak($fixtureText)
} finally {
    $stream.Close()
}
$fixtureText | Set-Content -LiteralPath (Join-Path $fixtureDirectory 'transcript.txt') -Encoding utf8
$provenance = [ordered]@{
    source = 'Locally generated Windows SAPI synthetic technical test speech'
    voice = $voiceDescription
    method = 'SAPI.SpVoice offline system voice'
    purpose = 'ATLAS lip-sync and audiovisual pipeline validation'
    consent = 'No human voice recording or voice cloning used'
    limitations = 'Not Chatterbox-Turbo output. Local technical fixture; system voice license applies.'
    transcript = $fixtureText
    sha256 = (Get-FileHash -LiteralPath $fixtureWav -Algorithm SHA256).Hash.ToLowerInvariant()
}
$provenance | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $fixtureDirectory 'fixture-provenance.json') -Encoding utf8
$provenance | ConvertTo-Json
