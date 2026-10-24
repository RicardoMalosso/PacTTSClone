param([Parameter(Mandatory=$true)][string]$SetupExe)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:RUNNER_TEMP 'PacTTSClone installation test'
$parent = Join-Path $root 'PacTTS'
$app = Join-Path $parent 'PacTTSClone'
$data = Join-Path $parent 'PacTTSClone-data'
$parentLauncher = Join-Path $parent 'PacTTSClone.lnk'
$arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=`"$app`"",'/DEVICE=cpu',"/LOG=`"$root-setup.log`"")
function Install-Checked {
    $process = Start-Process -FilePath $SetupExe -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
}
Install-Checked
$config = Get-Content -Raw (Join-Path $app 'active.json') | ConvertFrom-Json
if ($config.data_dir -ne $data -or $config.device -ne 'cpu') { throw 'Incorrect setup selection.' }
if (-not (Test-Path -LiteralPath $parentLauncher)) { throw 'Missing parent-folder launcher.' }
foreach ($shortcut in @((Join-Path $app 'Uninstall PacTTSClone.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'PacTTSClone\Uninstall PacTTSClone.lnk'))) {
    if (-not (Test-Path -LiteralPath $shortcut)) { throw "Missing uninstaller shortcut: $shortcut" }
}
. (Join-Path $app 'launcher\common.ps1')
Set-LocalEnvironment $app $data
$env:PATH = "$($config.ffmpeg_bin);$env:PATH"
& $config.python (Join-Path $PSScriptRoot 'verify-runtime.py') --device cpu
if ($LASTEXITCODE -ne 0) { throw 'Installed runtime smoke failed.' }
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
} finally {
    & taskkill.exe /PID $server.Id /T /F | Out-Null
}
$marker = Join-Path $data 'keep-user-audio.txt'
Set-Content $marker 'Preserve user data'
Install-Checked
if (-not (Test-Path $marker)) { throw 'Upgrade removed user data.' }
$uninstall = Start-Process (Join-Path $app 'unins000.exe') -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw 'Uninstall failed.' }
if (-not (Test-Path $marker)) { throw 'Uninstall removed user data.' }
if (Test-Path $parentLauncher) { throw 'Uninstall left parent launcher shortcut.' }
if (Test-Path (Join-Path $app 'environments')) { throw 'Uninstall left application environments.' }
Write-Host 'Real CPU installer, launcher, repeat setup and uninstall smoke passed.'
