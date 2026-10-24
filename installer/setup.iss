#define AppVersion "0.3.0-rc.1"
[Setup]
AppId={{7FF568CE-33A3-40B1-A7C0-15AA76F1DB84}
AppName=PacTTSClone
AppVersion={#AppVersion}
AppVerName=PacTTSClone {#AppVersion}
VersionInfoVersion=0.3.0.1
DefaultDirName={localappdata}\Programs\PacTTSClone
DefaultGroupName=PacTTSClone
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=PacTTSClone-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayName=PacTTSClone
CloseApplications=no
InfoBeforeFile=notice.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "bootstrap.ps1"; Flags: dontcopy
Source: "dependencies.json"; Flags: dontcopy
Source: "verify-runtime.py"; Flags: dontcopy
Source: "..\dist\pacttsclone-*.whl"; Flags: dontcopy
Source: "common.ps1"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "launch.ps1"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "common.ps1"; Flags: dontcopy

[Icons]
Name: "{group}\PacTTSClone"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\launcher\launch.ps1"""; WorkingDir: "{app}"
Name: "{autodesktop}\PacTTSClone"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\launcher\launch.ps1"""; Tasks: desktopicon; WorkingDir: "{app}"
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}\environments"
Type: filesandordirs; Name: "{app}\runtime"
Type: files; Name: "{app}\active.json"
Type: files; Name: "{app}\active.json.new"

[Code]
var
  DataPage: TInputDirWizardPage;
  DevicePage: TInputOptionWizardPage;

procedure InitializeWizard;
var ExistingData: String;
begin
  DataPage := CreateInputDirPage(wpSelectDir, 'Data and model storage',
    'Choose where voices, audio, models and download caches are stored.',
    'Use a separate folder with several GB free. This folder is preserved on uninstall.', False, '');
  DataPage.Add('Data folder:');
  ExistingData := GetPreviousData('DataRoot', ExpandConstant('{localappdata}\PacTTSClone-data'));
  DataPage.Values[0] := ExpandConstant('{param:DATADIR|' + ExistingData + '}');
  DevicePage := CreateInputOptionPage(DataPage.ID, 'Processing device',
    'Choose which dependencies to download.',
    'Automatic detects NVIDIA with nvidia-smi. CPU is slower. CUDA requires a compatible NVIDIA driver. Models download on first use.', True, False);
  DevicePage.Add('Automatic'); DevicePage.Add('CPU'); DevicePage.Add('NVIDIA GPU (CUDA)');
  DevicePage.SelectedValueIndex := 0;
  if ExpandConstant('{param:DEVICE|auto}') = 'cpu' then DevicePage.SelectedValueIndex := 1;
  if ExpandConstant('{param:DEVICE|auto}') = 'cuda' then DevicePage.SelectedValueIndex := 2;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'DataRoot', DataPage.Values[0]);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer; Device, Args: String;
begin
  Result := '';
  ForceDirectories(ExpandConstant('{app}'));
  ExtractTemporaryFile('bootstrap.ps1'); ExtractTemporaryFile('common.ps1');
  ExtractTemporaryFile('dependencies.json'); ExtractTemporaryFile('verify-runtime.py');
  ExtractTemporaryFiles('{tmp}\pacttsclone-*.whl');
  Device := 'auto';
  if DevicePage.SelectedValueIndex = 1 then Device := 'cpu';
  if DevicePage.SelectedValueIndex = 2 then Device := 'cuda';
  Args := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\bootstrap.ps1') +
    '" -AppRoot "' + ExpandConstant('{app}') + '" -DataRoot "' + DataPage.Values[0] + '" -Device ' + Device;
  WizardForm.StatusLabel.Caption := 'Downloading dependencies. Follow progress in the setup console. Closing it cancels setup.';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Args,
    ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, ExitCode) then
    Result := 'Could not start dependency setup.'
  else if ExitCode <> 0 then
    Result := 'Dependency setup failed or was cancelled. See ' + DataPage.Values[0] + '\logs\setup.log. Click Install to retry.';
end;
