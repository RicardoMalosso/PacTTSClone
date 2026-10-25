Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert-SeparatePaths([string]$AppRoot, [string]$DataRoot) {
    $appPath = [IO.Path]::GetFullPath($AppRoot).TrimEnd('\') + '\'
    $dataPath = [IO.Path]::GetFullPath($DataRoot).TrimEnd('\') + '\'
    if ($appPath.StartsWith($dataPath, [StringComparison]::OrdinalIgnoreCase) -or
        $dataPath.StartsWith($appPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Application and data folders must be separate, not inside one another.'
    }
}
function Set-LocalEnvironment([string]$AppRoot, [string]$DataRoot) {
    $env:UV_CACHE_DIR = Join-Path $DataRoot 'cache\uv'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $AppRoot 'runtime\python'
    $env:UV_PYTHON_CACHE_DIR = Join-Path $DataRoot 'cache\python'
    $env:UV_PYTHON_INSTALL_REGISTRY = '0'
    $env:UV_PYTHON_BIN_DIR = Join-Path $AppRoot 'runtime\bin'
    $env:UV_NO_CONFIG = '1'
    $env:UV_PYTHON_PREFERENCE = 'only-managed'
    if ($env:HF_HUB_CACHE -and -not $env:PACTTS_PREVIOUS_HF_CACHE) { $env:PACTTS_PREVIOUS_HF_CACHE = $env:HF_HUB_CACHE }
    $env:HF_HOME = Join-Path $DataRoot 'cache\huggingface'
    $env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
    $env:PIP_CACHE_DIR = Join-Path $DataRoot 'cache\pip'
    $env:TEMP = Join-Path $DataRoot 'temporary-system'
    $env:TMP = $env:TEMP
    $env:PYTHONNOUSERSITE = '1'
    Remove-Item Env:PYTHONHOME, Env:PYTHONPATH -ErrorAction SilentlyContinue
    foreach ($path in @($env:UV_CACHE_DIR, $env:UV_PYTHON_CACHE_DIR, $env:UV_PYTHON_INSTALL_DIR, $env:UV_PYTHON_BIN_DIR,
            $env:HF_HOME, $env:PIP_CACHE_DIR, $env:TEMP)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }
}
function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}
function Get-VerifiedDownload([string]$Url, [string]$Hash, [string]$Destination) {
    if ($Url -notmatch '^https://' -or $Hash -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid download manifest.' }
    if ((Test-Path -LiteralPath $Destination) -and
        (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $Hash) { return }
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null
    $partial = "$Destination.partial"
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "Downloading $Url (attempt $attempt/3)"
            # BITS is not required and no system-level download service is configured.
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $partial
            if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $Hash) {
                throw 'Downloaded file SHA-256 mismatch.'
            }
            Move-Item -LiteralPath $partial -Destination $Destination -Force
            return
        } catch {
            Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
            if ($attempt -eq 3) { throw }
            Write-Host "Download failed; retrying: $_"
        }
    }
}

