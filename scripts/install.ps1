param([ValidateSet('cpu', 'cuda')][string]$Device = 'cuda')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Run-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Falha ao executar $Exe (exit $LASTEXITCODE)." }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw 'Instale FFmpeg e abra um terminal novo antes de continuar.'
}
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Run-Checked 'py' @('-3.12', '-m', 'venv', '.venv')
}
$PythonExe = Join-Path $PWD '.venv\Scripts\python.exe'
Run-Checked $PythonExe @('-m', 'pip', 'install', '--upgrade', 'pip')
$WheelIndex = if ($Device -eq 'cuda') { 'cu128' } else { 'cpu' }
Run-Checked $PythonExe @('-m', 'pip', 'install', 'torch==2.8.0', 'torchaudio==2.8.0', '--index-url', "https://download.pytorch.org/whl/$WheelIndex")
Run-Checked $PythonExe @('-m', 'pip', 'install', '-e', '.[inference]')
Write-Host 'Instalação concluída. Execute scripts\start.ps1.'
