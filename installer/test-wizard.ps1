param([Parameter(Mandatory=$true)][string]$SetupExe)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing, System.Windows.Forms
$root = Join-Path $env:RUNNER_TEMP 'Wizard layout test'
$app = Join-Path $root 'PacTTSClone'
$process = Start-Process -FilePath $SetupExe -ArgumentList @('/SP-','/LANG=english',"/DIR=`"$app`"") -PassThru
function Elements($window) { $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition) }
function Find-Name($window, [string]$name) {
    @(Elements $window) | Where-Object { $_.Current.Name -eq $name } | Select-Object -First 1
}
function Find-Next($window) {
    @(Elements $window) | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $_.Current.Name -match '^Next' } | Select-Object -First 1
}
function Click($element) {
    if (-not $element) { throw 'Expected wizard control not found.' }
    $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
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
    Screenshot 'step1'
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while (-not (Find-Next $window).Current.IsEnabled -and $watch.Elapsed.TotalSeconds -lt 8) { Start-Sleep -Milliseconds 100 }
    if (-not (Find-Next $window).Current.IsEnabled -or $watch.Elapsed.TotalSeconds -lt 3) { throw 'Unexpected notice countdown duration.' }
    Click (Find-Next $window)
    Start-Sleep -Milliseconds 300
    if (-not (Find-Name $window "Est. 4-12 GB`r`ninstalled")) { throw 'App space estimate missing.' }
    Screenshot 'application-path'
    Click (Find-Next $window)
    Start-Sleep -Milliseconds 300
    $checkbox = Find-Name $window 'Choose a separate data location'
    if (-not $checkbox) { throw 'Separate-data checkbox missing.' }
    $edits = @(Elements $window) | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Edit }
    $dataEdit = $edits | Where-Object { $_.Current.IsOffscreen -eq $false } | Select-Object -First 1
    if (-not $dataEdit -or $dataEdit.Current.IsEnabled) { throw 'Default data picker must be locked.' }
    $value = $dataEdit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    if ($value -ne (Join-Path $root 'PacTTSClone-data')) { throw "Incorrect sibling default: $value" }
    Screenshot 'sibling-data'
    $checkbox.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Toggle()
    Start-Sleep -Milliseconds 200
    if (-not $dataEdit.Current.IsEnabled) { throw 'Checkbox did not unlock data picker.' }
    $dataEdit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue((Join-Path $root 'Different data'))
    $checkbox.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Toggle()
    Start-Sleep -Milliseconds 200
    if ($dataEdit.Current.IsEnabled) { throw 'Checkbox did not relock data picker.' }
    if ($dataEdit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value -ne (Join-Path $root 'PacTTSClone-data')) { throw 'Sibling default not restored.' }
    Write-Host 'Interactive notice delay, estimates and folder checkbox checks passed.'
} catch {
    if ($window) { @(Elements $window) | ForEach-Object { Write-Host "$($_.Current.ControlType.ProgrammaticName) $($_.Current.Name)" } }
    Screenshot 'failure'
    throw
} finally {
    & taskkill.exe /PID $process.Id /T /F | Out-Null
}
