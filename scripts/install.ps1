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
Run-Checked $PythonExe @('-m', 'pip', 'install', '-e', '.')
Write-Host 'CPU/NVIDIA e modelos serão configurados na aba Initial Setup do navegador.'
Write-Host 'Instalação concluída. Execute scripts\start.ps1.'
