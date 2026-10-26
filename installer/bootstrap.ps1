param(
    [Parameter(Mandatory=$true)][string]$AppRoot,
    [Parameter(Mandatory=$true)][string]$DataRoot,
    [ValidateSet('auto','cpu','cuda')][string]$Device = 'auto',
    [string]$PayloadDir
)
if (-not $PayloadDir) { $PayloadDir = Split-Path -Parent $PSCommandPath }
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-SeparatePaths $AppRoot $DataRoot
Set-LocalEnvironment $AppRoot $DataRoot
New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot 'logs') | Out-Null
$log = Join-Path $DataRoot 'logs\setup.log'
Start-Transcript -Path $log -Append | Out-Null
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $manifest = Get-Content -Raw -LiteralPath (Join-Path $PayloadDir 'dependencies.json') | ConvertFrom-Json
    $wheel = @(Get-ChildItem -LiteralPath $PayloadDir -Filter 'pacttsclone-*.whl')
    if ($wheel.Count -ne 1) { throw 'Setup payload must contain exactly one application wheel.' }
    $version = $wheel[0].Name.Split('-')[1]
    if ($version -notmatch '^[0-9A-Za-z.]+$') { throw 'Invalid application version.' }
    $Device = 'auto'
    Write-Host "[1/6] Preparing $Device installation; data: $DataRoot"
    $downloads = Join-Path $DataRoot 'cache\setup'
    $uvArchive = Join-Path $downloads 'uv-0.9.5.zip'
    Get-VerifiedDownload $manifest.uv.url $manifest.uv.sha256 $uvArchive
    $uvRoot = Join-Path $AppRoot 'runtime\uv'
    Expand-Archive -LiteralPath $uvArchive -DestinationPath $uvRoot -Force
    $uv = @(Get-ChildItem -LiteralPath $uvRoot -Filter uv.exe -Recurse)[0].FullName
    Write-Host '[2/6] Reusing or installing isolated Python runtime'
    $managedPython = Join-Path $env:UV_PYTHON_INSTALL_DIR "cpython-$($manifest.python)-windows-x86_64-none\python.exe"
    if (-not (Test-Path -LiteralPath $managedPython)) {
        Invoke-Checked $uv @('python','install',$manifest.python)
    } else {
        Write-Host "Reusing private Python: $managedPython"
    }
    if (-not (Test-Path -LiteralPath $managedPython)) {
        throw "Managed Python was not found at $managedPython"
    }
    Invoke-Checked $managedPython @('-c', 'import sys; print(sys.version)')
    $envRoot = Join-Path $AppRoot "environments\$version-$Device"
    $python = $null
    $activePath = Join-Path $AppRoot 'active.json'
    if (Test-Path -LiteralPath $activePath) {
        try {
            $previous = Get-Content -Raw -LiteralPath $activePath | ConvertFrom-Json
            $previousPython = [IO.Path]::GetFullPath($previous.python)
            $allowedRoot = [IO.Path]::GetFullPath((Join-Path $AppRoot 'environments')).TrimEnd('\') + '\'
            if ($previousPython.StartsWith($allowedRoot, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $previousPython)) {
                & $previousPython -c 'import sys; assert sys.version_info[:2] == (3,12)'
                if ($LASTEXITCODE -eq 0) {
                    $python = $previousPython
                    Write-Host "Reusing existing application environment: $python"
                }
            }
        } catch { Write-Host 'Previous environment is unavailable; creating one from cached packages.' }
    }
    if (-not $python) {
        Invoke-Checked $uv @('venv','--allow-existing','--python',$managedPython,$envRoot)
        $python = Join-Path $envRoot 'Scripts\python.exe'
    }
    Write-Host '[3/6] Installing verified gyan.dev FFmpeg Essentials binaries'
    $ffBin = Join-Path $AppRoot 'runtime\ffmpeg\bin'
    New-Item -ItemType Directory -Force -Path $ffBin | Out-Null
    foreach ($tool in @('ffmpeg.exe','ffprobe.exe')) {
        Copy-Item -LiteralPath (Join-Path $PayloadDir $tool) -Destination (Join-Path $ffBin $tool) -Force
    }
    $env:PATH = "$ffBin;$env:PATH"
    Write-Host '[4/6] Installing only the web application (no CUDA/PyTorch/models)'
    Invoke-Checked $uv @('pip','install','--python',$python,'--index-url','https://pypi.org/simple',$wheel[0].FullName)
    Write-Host '[5/6] Checking web runtime and audio tools'
    Invoke-Checked $python @((Join-Path $PayloadDir 'verify-runtime.py'), '--device', 'web')
    Write-Host '[6/6] Activating installation; open Initial Setup in the browser to install inference and models'
    $settings = @{python=$python; data_dir=$DataRoot; ffmpeg_bin=$ffBin; device=$Device; version=$version; uv=$uv}
    $temporaryConfig = Join-Path $AppRoot 'active.json.new'
    $settings | ConvertTo-Json | Set-Content -LiteralPath $temporaryConfig -Encoding UTF8
    Move-Item -LiteralPath $temporaryConfig -Destination (Join-Path $AppRoot 'active.json') -Force
    Write-Host 'Setup complete. Start PacTTSClone from the Start menu.'
} catch {
    Write-Host $_.ScriptStackTrace
    Write-Host "Setup failed: $_`nLog: $log`nRerun setup to retry. Completed downloads are reused." -ForegroundColor Red
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
