param([string]$OutputDirectory = 'outputs/runtimes/rhubarb')
$ErrorActionPreference = 'Stop'
$releaseUrl = 'https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.14.0/Rhubarb-Lip-Sync-1.14.0-Windows.zip'
$expectedHash = '62fa416a8d5e382a3828ee4bef358ce520d0b4cabdeaea75a7ac266d098d1fe3'
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$runtimeDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$archivePath = Join-Path $runtimeDirectory 'Rhubarb-Lip-Sync-1.14.0-Windows.zip'
if (-not (Test-Path -LiteralPath $archivePath)) {
    Invoke-WebRequest $releaseUrl -OutFile $archivePath
}
$actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) { throw 'Official Rhubarb archive hash mismatch; refusing extraction' }
Expand-Archive -LiteralPath $archivePath -DestinationPath $runtimeDirectory -Force
$executablePath = Join-Path $runtimeDirectory 'Rhubarb-Lip-Sync-1.14.0-Windows/rhubarb.exe'
$manifest = [ordered]@{
    version = '1.14.0'
    source = $releaseUrl
    archive_sha256 = $actualHash
    executable = $executablePath
    executable_sha256 = (Get-FileHash -LiteralPath $executablePath -Algorithm SHA256).Hash.ToLowerInvariant()
    license = 'Rhubarb-Lip-Sync-1.14.0-Windows/LICENSE.md (MIT and bundled third-party notices)'
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDirectory 'installation.json') -Encoding utf8
$manifest | ConvertTo-Json
