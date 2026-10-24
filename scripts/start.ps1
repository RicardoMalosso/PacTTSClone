$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$PythonExe = Join-Path $PWD '.venv\Scripts\python.exe'
if (-not (Test-Path $PythonExe)) { throw 'Execute scripts\install.ps1 primeiro.' }
& $PythonExe -m pacttsclone.cli @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
