param([Parameter(Mandatory=$true)][string]$SetupExe)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:RUNNER_TEMP 'PacTTSClone installation test'
$app = Join-Path $root 'PacTTSClone'
$data = Join-Path $root 'PacTTSClone-data'
$arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',"/DIR=`"$app`"",'/DEVICE=cpu',"/LOG=`"$root-setup.log`"")
function Install-Checked {
    $process = Start-Process -FilePath $SetupExe -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
}
Install-Checked
$config = Get-Content -Raw (Join-Path $app 'active.json') | ConvertFrom-Json
if ($config.data_dir -ne $data -or $config.device -ne 'cpu') { throw 'Incorrect setup selection.' }
foreach ($shortcut in @((Join-Path $app 'Uninstall PacTTSClone.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'PacTTSClone\Uninstall PacTTSClone.lnk'))) {
    if (-not (Test-Path -LiteralPath $shortcut)) { throw "Missing uninstaller shortcut: $shortcut" }
}
. (Join-Path $app 'launcher\common.ps1')
Set-LocalEnvironment $app $data
$env:PATH = "$($config.ffmpeg_bin);$env:PATH"
& $config.python (Join-Path $PSScriptRoot 'verify-runtime.py') --device cpu
if ($LASTEXITCODE -ne 0) { throw 'Installed runtime smoke failed.' }
# Real HTTP startup in a child launched through the installed launcher.
$launcher = Join-Path $app 'launcher\launch.ps1'
$server = Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$launcher`"",'--port','17860','--no-browser') -PassThru
try {
    $ready = $false
    for ($i=0; $i -lt 60; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:17860/api/health'
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
if (Test-Path (Join-Path $app 'environments')) { throw 'Uninstall left application environments.' }
Write-Host 'Real CPU installer, launcher, repeat setup and uninstall smoke passed.'
