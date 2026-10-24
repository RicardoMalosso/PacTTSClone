param([string]$AppRoot, [Parameter(ValueFromRemainingArguments=$true)][string[]]$AppArguments)
if (-not $AppRoot) { $AppRoot = Split-Path (Split-Path -Parent $PSCommandPath) -Parent }
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    $config = Get-Content -Raw -LiteralPath (Join-Path $AppRoot 'active.json') | ConvertFrom-Json
    Set-LocalEnvironment $AppRoot $config.data_dir
    $env:PATH = "$($config.ffmpeg_bin);$env:PATH"
    & $config.python -m pacttsclone.cli --data-dir $config.data_dir --device $config.device @AppArguments
    if ($LASTEXITCODE -ne 0) { throw "Application exited with code $LASTEXITCODE" }
} catch {
    Write-Host "PacTTSClone could not start: $_" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
