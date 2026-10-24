. (Join-Path $PSScriptRoot 'common.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Force $root | Out-Null
try {
    Assert-SeparatePaths (Join-Path $root 'app') (Join-Path $root 'data')
    $blocked = $false
    try { Assert-SeparatePaths $root (Join-Path $root 'child') } catch { $blocked = $true }
    if (-not $blocked) { throw 'Nested data folder accepted.' }
    $blocked = $false
    try { Assert-SeparatePaths (Join-Path $root 'APP') (Join-Path $root 'app') } catch { $blocked = $true }
    if (-not $blocked) { throw 'Overlapping folders accepted.' }
    $script:calls = 0
    function Invoke-WebRequest {
        param([switch]$UseBasicParsing, $Uri, $OutFile)
        $script:calls++
        [IO.File]::WriteAllText($OutFile, 'verified content')
    }
    $source = Join-Path $root 'source'
    [IO.File]::WriteAllText($source, 'verified content')
    $hash = (Get-FileHash $source -Algorithm SHA256).Hash
    $destination = Join-Path $root 'download'
    Get-VerifiedDownload 'https://example.test/archive.zip' $hash $destination
    Get-VerifiedDownload 'https://example.test/archive.zip' $hash $destination
    if ($script:calls -ne 1) { throw 'Verified cache was downloaded again.' }
    [IO.File]::WriteAllText($destination, 'corrupt')
    Get-VerifiedDownload 'https://example.test/archive.zip' $hash $destination
    if ($script:calls -ne 2) { throw 'Corrupt cache was trusted.' }
    $blocked = $false
    try { Get-VerifiedDownload 'https://example.test/archive.zip' ('0' * 64) $destination } catch { $blocked = $true }
    if (-not $blocked -or (Test-Path "$destination.partial")) { throw 'Invalid digest was not rejected/cleaned.' }
    Write-Host 'Installer helper tests passed.'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
