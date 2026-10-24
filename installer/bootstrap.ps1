param(
    [Parameter(Mandatory=$true)][string]$AppRoot,
    [Parameter(Mandatory=$true)][string]$DataRoot,
    [ValidateSet('auto','cpu','cuda')][string]$Device = 'auto',
    [string]$PayloadDir = $PSScriptRoot
)
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
    if ($Device -eq 'auto') {
        $Device = 'cpu'
        if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
            & nvidia-smi --query-gpu=name --format=csv,noheader
            if ($LASTEXITCODE -eq 0) { $Device = 'cuda' }
        }
    }
    Write-Host "[1/6] Preparing $Device installation; data: $DataRoot"
    $downloads = Join-Path $DataRoot 'cache\setup'
    $uvArchive = Join-Path $downloads 'uv-0.9.5.zip'
    Get-VerifiedDownload $manifest.uv.url $manifest.uv.sha256 $uvArchive
    $uvRoot = Join-Path $AppRoot 'runtime\uv'
    Expand-Archive -LiteralPath $uvArchive -DestinationPath $uvRoot -Force
    $uv = @(Get-ChildItem -LiteralPath $uvRoot -Filter uv.exe -Recurse)[0].FullName
    Write-Host '[2/6] Downloading isolated Python runtime'
    Invoke-Checked $uv @('python','install',$manifest.python)
    $managedPython = (& $uv python find --managed-python $manifest.python | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $managedPython)) { throw 'Managed Python was not found.' }
    $envRoot = Join-Path $AppRoot "environments\$version-$Device"
    Invoke-Checked $uv @('venv','--allow-existing','--python',$managedPython,$envRoot)
    $python = Join-Path $envRoot 'Scripts\python.exe'
    Write-Host '[3/6] Downloading FFmpeg'
    $ffArchive = Join-Path $downloads 'ffmpeg-8.0.1.zip'
    Get-VerifiedDownload $manifest.ffmpeg.url $manifest.ffmpeg.sha256 $ffArchive
    $ffRoot = Join-Path $AppRoot 'runtime\ffmpeg'
    Expand-Archive -LiteralPath $ffArchive -DestinationPath $ffRoot -Force
    $ffmpeg = @(Get-ChildItem -LiteralPath $ffRoot -Filter ffmpeg.exe -Recurse)[0].FullName
    $ffBin = Split-Path $ffmpeg -Parent
    $env:PATH = "$ffBin;$env:PATH"
    Write-Host '[4/6] Downloading PyTorch and application dependencies (can be several GB)'
    $variant = if ($Device -eq 'cuda') { 'cu128' } else { 'cpu' }
    $index = "https://download.pytorch.org/whl/$variant"
    Invoke-Checked $uv @('pip','install','--python',$python,'--index-url',$index,"torch==2.8.0+$variant","torchaudio==2.8.0+$variant")
    Invoke-Checked $uv @('pip','install','--python',$python,'--index-url','https://pypi.org/simple','--index',$index,
        '--index-strategy','unsafe-best-match',"$($wheel[0].FullName)[inference]","torch==2.8.0+$variant","torchaudio==2.8.0+$variant")
    Write-Host '[5/6] Checking installed runtime, CUDA selection and audio tools'
    Invoke-Checked $python @((Join-Path $PayloadDir 'verify-runtime.py'), '--device', $Device)
    Write-Host '[6/6] Activating installation; model downloads happen on first use'
    $settings = @{python=$python; data_dir=$DataRoot; ffmpeg_bin=$ffBin; device=$Device; version=$version}
    $temporaryConfig = Join-Path $AppRoot 'active.json.new'
    $settings | ConvertTo-Json | Set-Content -LiteralPath $temporaryConfig -Encoding UTF8
    Move-Item -LiteralPath $temporaryConfig -Destination (Join-Path $AppRoot 'active.json') -Force
    Write-Host 'Setup complete. Start PacTTSClone from the Start menu.'
} catch {
    Write-Host "Setup failed: $_`nLog: $log`nRerun setup to retry. Completed downloads are reused." -ForegroundColor Red
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
