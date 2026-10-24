param([Parameter(Mandatory=$true)][string]$SetupExe)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing, System.Windows.Forms
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class NativeWizard {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll")]
    public static extern IntPtr SendMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", CharSet=CharSet.Unicode, EntryPoint="SendMessageW")]
    public static extern IntPtr SetText(IntPtr hwnd, uint msg, IntPtr wParam, string text);
}
'@
$root = Join-Path $env:RUNNER_TEMP 'Wizard layout test'
$app = Join-Path $root 'PacTTSClone'
$process = Start-Process -FilePath $SetupExe -ArgumentList @('/SP-','/NORESTART','/LANG=english',"/DIR=`"$app`"") -PassThru
function Elements($window) { $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition) }
function Find-Name($window, [string]$name) {
    @(Elements $window) | Where-Object { $_.Current.Name -eq $name } | Select-Object -First 1
}
function Find-Next($window) {
    @(Elements $window) | Where-Object { $_.Current.Name -match '^&?Next' } | Select-Object -First 1
}
function Click($element) {
    if (-not $element) { throw 'Expected wizard control not found.' }
    [NativeWizard]::SendMessage([IntPtr]$element.Current.NativeWindowHandle, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
}
function Read-Edit($element) {
    $text = New-Object Text.StringBuilder 4096
    [NativeWizard]::GetWindowText([IntPtr]$element.Current.NativeWindowHandle, $text, $text.Capacity) | Out-Null
    return $text.ToString()
}
function Screenshot([string]$name) {
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $image = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($image)
    try { $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size); $image.Save((Join-Path $env:RUNNER_TEMP "pactts-wizard-$name.png")) }
    finally { $graphics.Dispose(); $image.Dispose() }
}
try {
    $window = $null
    for ($i=0; $i -lt 100; $i++) {
        $window = @([System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)) | Where-Object { $_.Current.Name -like 'Setup - PacTTSClone*' } | Select-Object -First 1
        if ($window -and (Find-Name $window 'STEP 1 - PICK THE FOLDERS')) { break }
        Start-Sleep -Milliseconds 100
    }
    if (-not $window -or -not (Find-Name $window 'STEP 1 - PICK THE FOLDERS')) { throw 'Step 1 notice missing.' }
    $next = Find-Next $window
    if (-not $next -or $next.Current.IsEnabled) { throw 'Next was not initially locked.' }
    $initialSeconds = [int]([regex]::Match($next.Current.Name, '(\d+)s').Groups[1].Value)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    Screenshot 'step1'
    while (-not (Find-Next $window).Current.IsEnabled -and $watch.Elapsed.TotalSeconds -lt 8) { Start-Sleep -Milliseconds 100 }
    if (-not (Find-Next $window).Current.IsEnabled -or $watch.Elapsed.TotalSeconds -lt [Math]::Max(0, $initialSeconds - 1.25)) { throw 'Unexpected notice countdown duration.' }
    Click (Find-Next $window)
    Start-Sleep -Milliseconds 300
    if (-not (Find-Name $window "Est. 12-32+ GB`r`napp + data")) { throw 'App space estimate missing.' }
    Screenshot 'application-path'
    Click (Find-Next $window)
    Start-Sleep -Milliseconds 300
    $checkbox = Find-Name $window 'Choose a separate data location'
    if (-not $checkbox) { throw 'Separate-data checkbox missing.' }
    $edits = @(Elements $window) | Where-Object { $_.Current.ClassName -match 'Edit' }
    $dataEdit = $edits | Where-Object { $_.Current.IsOffscreen -eq $false } | Select-Object -First 1
    if (-not $dataEdit -or $dataEdit.Current.IsEnabled) { throw 'Default data picker must be locked.' }
    $value = Read-Edit $dataEdit
    if ($value -ne (Join-Path $app 'data')) { throw "Incorrect contained data default: $value" }
    Screenshot 'contained-data'
    Click $checkbox
    Start-Sleep -Milliseconds 200
    if (-not $dataEdit.Current.IsEnabled) { throw 'Checkbox did not unlock data picker.' }
    [NativeWizard]::SetText([IntPtr]$dataEdit.Current.NativeWindowHandle, 0x000C, [IntPtr]::Zero, (Join-Path $root 'Different data')) | Out-Null
    Click $checkbox
    Start-Sleep -Milliseconds 200
    if ($dataEdit.Current.IsEnabled) { throw 'Checkbox did not relock data picker.' }
    if ((Read-Edit $dataEdit) -ne (Join-Path $app 'data')) { throw 'Contained default not restored.' }
    Write-Host 'Interactive notice delay, estimates and folder checkbox checks passed.'
    # Deliberately select the protected app directory as data: bootstrap must fail
    # before downloads. The user must never be advanced to a Finish/restart action.
    Click $checkbox
    [NativeWizard]::SetText([IntPtr]$dataEdit.Current.NativeWindowHandle, 0x000C, [IntPtr]::Zero, (Join-Path $app 'app')) | Out-Null
    Click (Find-Next $window)
    $install = $null
    for ($i=0; $i -lt 6; $i++) {
        Start-Sleep -Milliseconds 200
        $install = @(Elements $window) | Where-Object { $_.Current.Name -match '^&?Install$' } | Select-Object -First 1
        if ($install) { break }
        Click (Find-Next $window)
    }
    if (-not $install -or -not $install.Current.IsEnabled) { throw 'Install action not reachable.' }
    Click $install
    Start-Sleep -Milliseconds 500
    $failure = @(Elements $window) | Where-Object { $_.Current.Name -like '*Dependency setup failed or was cancelled*' } | Select-Object -First 1
    if (-not $failure) { throw 'Expected preparation failure was not shown.' }
    $next = Find-Next $window
    if ($next -and $next.Current.IsEnabled) { throw 'Failure page incorrectly enables Next.' }
    $finish = @(Elements $window) | Where-Object { $_.Current.Name -match '^&?Finish$' -and $_.Current.IsEnabled } | Select-Object -First 1
    if ($finish) { throw 'Failure page incorrectly offers Finish/restart.' }
    $openLog = Find-Name $window 'Open setup log'
    if (-not $openLog -or -not $openLog.Current.IsEnabled) { throw 'Failure log button missing.' }
    $errorLog = Join-Path $app 'setup-error.log'
    if (-not (Test-Path $errorLog)) { throw 'Early failure diagnostic was not saved.' }
    Screenshot 'failure-path'
    Write-Host 'Failed preparation blocks Next/Finish and exposes the diagnostic log; no restart requested.'
} catch {
    if ($window) { @(Elements $window) | ForEach-Object { Write-Host "$($_.Current.ClassName) $($_.Current.ControlType.ProgrammaticName) $($_.Current.Name)" } }
    Screenshot 'failure'
    throw
} finally {
    & taskkill.exe /PID $process.Id /T /F | Out-Null
}
