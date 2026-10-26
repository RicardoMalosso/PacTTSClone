param([Parameter(Mandatory=$true)][string]$SetupExe)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:RUNNER_TEMP 'PacTTSClone installation test'
$parent = Join-Path $root 'PacTTSClone'
$app = Join-Path $parent 'app'
$data = Join-Path $parent 'data'
$parentLauncher = Join-Path $parent 'PacTTSClone.lnk'
$arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=`"$parent`"",'/DEVICE=cpu',"/LOG=`"$root-setup.log`"")
function Install-Checked {
    $process = Start-Process -FilePath $SetupExe -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
}
Install-Checked
$config = Get-Content -Raw (Join-Path $app 'active.json') | ConvertFrom-Json
if (-not $config.python.StartsWith($app + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime escaped app subfolder.' }
if ($config.data_dir -ne $data -or $config.device -ne 'auto') { throw 'Incorrect setup selection.' }
if (-not (Test-Path -LiteralPath $parentLauncher)) { throw 'Missing parent-folder launcher.' }
foreach ($shortcut in @((Join-Path $parent 'Uninstall PacTTSClone.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'PacTTSClone\Uninstall PacTTSClone.lnk'))) {
    if (-not (Test-Path -LiteralPath $shortcut)) { throw "Missing uninstaller shortcut: $shortcut" }
}
. (Join-Path $app 'launcher\common.ps1')
Set-LocalEnvironment $app $data
$env:PATH = "$($config.ffmpeg_bin);$env:PATH"
& $config.python (Join-Path $PSScriptRoot 'verify-runtime.py') --device web
if ($LASTEXITCODE -ne 0) { throw 'Installed runtime smoke failed.' }
& $config.python -c "import importlib.util; assert importlib.util.find_spec('torch') is None; assert importlib.util.find_spec('omnivoice') is None"
if ($LASTEXITCODE -ne 0) { throw 'Native installer installed inference packages.' }
# Launch the actual user-facing parent shortcut, not a script command.
$server = Start-Process -FilePath $parentLauncher -PassThru
try {
    $ready = $false
    for ($i=0; $i -lt 60; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:7860/api/health'
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) { throw 'Installed launcher did not serve HTTP.' }
    # Verify the installed wheel serves the exact original bundled media.
    $clip = Join-Path $root 'installed-jingling-keys.webm'
    Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:7860/static/jingling-keys.webm' -OutFile $clip
    if ((Get-FileHash $clip -Algorithm SHA256).Hash.ToLower() -ne '01f5003f1ad001452249af8939afdecd6cb7470d29772af7d18d038c41d3c894') { throw 'Installed WebM differs from original user upload.' }
    & ffmpeg -nostdin -v error -i $clip -map 0:v:0 -map 0:a:0 -f null -
    if ($LASTEXITCODE -ne 0) { throw 'Installed WebM video/audio decode failed.' }
    $initial = Invoke-RestMethod 'http://127.0.0.1:7860/api/setup'
    if ($initial.ready) { throw 'Initial Setup gate was bypassed.' }
    $session = Invoke-RestMethod 'http://127.0.0.1:7860/api/session'
    $headers = @{'X-PacTTS-Token'=$session.token}
    Invoke-RestMethod 'http://127.0.0.1:7860/api/setup/start' -Method Post -Headers $headers -ContentType 'application/json' -Body '{"device":"cpu"}' | Out-Null
    $deadline = [DateTime]::UtcNow.AddMinutes(20)
    do {
        Start-Sleep -Seconds 3
        $state = Invoke-RestMethod 'http://127.0.0.1:7860/api/setup'
        Write-Host "Web setup: $($state.status) / $($state.stage)"
        if ($state.download) { Write-Host ($state.download | ConvertTo-Json -Compress) }
        if ([DateTime]::UtcNow -gt $deadline) {
            Invoke-RestMethod 'http://127.0.0.1:7860/api/setup/cancel' -Method Post -Headers $headers | Out-Null
            throw 'Web setup exceeded its 20-minute test deadline.'
        }
    } while ($state.status -eq 'running')
    if ($state.status -ne 'succeeded') { throw "Dependency/model acceptance failed: $($state.error)" }
    if ($state.ready) { throw 'CPU-only dependency acceptance must not unlock CUDA-only generation.' }
    if ($state.models.files.Count -lt 2) { throw 'Model verification manifest missing.' }
    & $config.python (Join-Path $PSScriptRoot 'verify-runtime.py') --device cpu
    if ($LASTEXITCODE -ne 0) { throw 'Web-installed CPU runtime smoke failed.' }
} finally {
    & taskkill.exe /PID $server.Id /T /F | Out-Null
}
$marker = Join-Path $data 'keep-user-audio.txt'
Set-Content $marker 'Preserve user data'
Install-Checked
if (-not (Test-Path $marker)) { throw 'Upgrade removed user data.' }
$uninstall = Start-Process (Join-Path $parent 'unins000.exe') -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw 'Uninstall failed.' }
if (-not (Test-Path $marker)) { throw 'Uninstall removed user data.' }
if (Test-Path $parentLauncher) { throw 'Uninstall left parent launcher shortcut.' }
if (Test-Path $app) { throw 'Uninstall left app subfolder.' }
if (-not (Test-Path $parent)) { throw 'Uninstall removed the root containing user data.' }
Write-Host 'Minimal installer, real web CPU/model setup, launcher, repeat setup and uninstall smoke passed.'

# All native command results above are checked explicitly. A best-effort taskkill
# can leave LASTEXITCODE=1 even after every acceptance assertion passed.
exit 0
