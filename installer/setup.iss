#ifndef AppVersion
#define AppVersion "0.3.0-rc.12"
#endif
[Setup]
AppId={{7FF568CE-33A3-40B1-A7C0-15AA76F1DB84}
AppName=PacTTSClone
AppVersion={#AppVersion}
AppVerName=PacTTSClone {#AppVersion}
VersionInfoVersion=0.3.0.9
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
AlwaysRestart=no
RestartIfNeededByRun=no
DisableWelcomePage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "bootstrap.ps1"; Flags: dontcopy
Source: "dependencies.json"; Flags: dontcopy
Source: "verify-runtime.py"; Flags: dontcopy
Source: "ffmpeg\bin\*.exe"; Flags: dontcopy
Source: "ffmpeg\BUILD-PROVENANCE.txt"; DestDir: "{app}\app\runtime\ffmpeg"; Flags: ignoreversion
Source: "ffmpeg\licenses\*"; DestDir: "{app}\app\runtime\ffmpeg\licenses"; Flags: ignoreversion
Source: "..\dist\pacttsclone-*.whl"; Flags: dontcopy
Source: "common.ps1"; DestDir: "{app}\app\launcher"; Flags: ignoreversion
Source: "launch.ps1"; DestDir: "{app}\app\launcher"; Flags: ignoreversion
Source: "common.ps1"; Flags: dontcopy

[Icons]
Name: "{group}\PacTTSClone"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\app\launcher\launch.ps1"""; WorkingDir: "{app}\app"
Name: "{app}\PacTTSClone"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\app\launcher\launch.ps1"""; WorkingDir: "{app}\app"
Name: "{autodesktop}\PacTTSClone"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\app\launcher\launch.ps1"""; Tasks: desktopicon; WorkingDir: "{app}\app"
Name: "{group}\Uninstall PacTTSClone"; Filename: "{uninstallexe}"
Name: "{app}\Uninstall PacTTSClone"; Filename: "{uninstallexe}"
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}\app\environments"
Type: filesandordirs; Name: "{app}\app\runtime"
Type: files; Name: "{app}\app\active.json"
Type: files; Name: "{app}\app\active.json.new"

Type: dirifempty; Name: "{app}\app"

[Code]
var
  DataPage: TInputDirWizardPage;
  IntroPage: TWizardPage;
  SeparateData: TNewCheckBox;
  AppSize, DataSize, IntroTitle, IntroWarning, IntroModels, IntroUnsigned: TNewStaticText;
  IntroUntil: Int64;
  IntroSeen: Boolean;
  IntroTimer: LongWord;
  PreparationFailed: Boolean;
  LogButton: TNewButton;
  SetupLogPath: String;

function SystemTicks: Int64;
  external 'GetTickCount64@kernel32.dll stdcall';
function SetTimer(Wnd, ID, Interval, Callback: LongWord): LongWord;
  external 'SetTimer@user32.dll stdcall';
function KillTimer(Wnd, ID: LongWord): Boolean;
  external 'KillTimer@user32.dll stdcall';

function DefaultDataPath: String;
begin
  Result := AddBackslash(WizardDirValue) + 'data';
end;

procedure SyncDataPath;
begin
  if not SeparateData.Checked then DataPage.Values[0] := DefaultDataPath;
  if SeparateData.Checked then AppSize.Caption := 'Est. 4-12 GB' + #13#10 + 'app only'
  else AppSize.Caption := 'Est. 12-32+ GB' + #13#10 + 'app + data';
  DataPage.Edits[0].Enabled := SeparateData.Checked;
  DataPage.Buttons[0].Enabled := SeparateData.Checked;
end;

procedure SeparateDataClick(Sender: TObject);
begin
  SyncDataPath;
end;

procedure IntroTick(Wnd, Msg, ID, Time: LongWord);
var Remaining: Integer;
begin
  if WizardForm.CurPageID <> IntroPage.ID then Exit;
  Remaining := (IntroUntil - SystemTicks + 999) div 1000;
  if Remaining <= 0 then begin
    WizardForm.NextButton.Enabled := True;
    WizardForm.NextButton.Caption := SetupMessage(msgButtonNext);
  end else begin
    WizardForm.NextButton.Enabled := False;
    WizardForm.NextButton.Caption := 'Next (' + IntToStr(Remaining) + 's)';
  end;
end;

procedure MakeSizeLabel(LabelControl: TNewStaticText; ParentControl: TWinControl;
  EditControl: TControl; BrowseControl: TControl; CaptionText: String);
var Reserve: Integer;
begin
  Reserve := ScaleX(102);
  EditControl.Width := EditControl.Width - Reserve;
  BrowseControl.Left := BrowseControl.Left - Reserve;
  LabelControl.Parent := ParentControl;
  LabelControl.Left := BrowseControl.Left + BrowseControl.Width + ScaleX(8);
  LabelControl.Top := EditControl.Top;
  LabelControl.Width := ScaleX(94);
  LabelControl.Height := ScaleY(32);
  LabelControl.AutoSize := False;
  LabelControl.WordWrap := True;
  LabelControl.Font.Size := 8;
  LabelControl.Font.Style := [fsBold];
  LabelControl.Font.Color := clRed;
  LabelControl.Caption := CaptionText;
end;

procedure OpenSetupLog(Sender: TObject);
var Code: Integer;
begin
  if FileExists(SetupLogPath) then
    Exec(ExpandConstant('{sys}\notepad.exe'), '"' + SetupLogPath + '"', '', SW_SHOW, ewNoWait, Code);
end;

procedure InitializeWizard;
var ExistingData: String;
begin
  LogButton := TNewButton.Create(WizardForm);
  LogButton.Parent := WizardForm;
  LogButton.SetBounds(ScaleX(8), WizardForm.NextButton.Top, ScaleX(140), WizardForm.NextButton.Height);
  LogButton.Caption := 'Open setup log';
  LogButton.OnClick := @OpenSetupLog;
  LogButton.Visible := False;
  IntroPage := CreateCustomPage(wpWelcome, 'STEP 1 - Choose your folders carefully',
    'Downloads are large. Read this before choosing an installation drive.');
  IntroTitle := TNewStaticText.Create(WizardForm);
  IntroTitle.Parent := IntroPage.Surface;
  IntroTitle.SetBounds(0, 0, IntroPage.SurfaceWidth, ScaleY(32));
  IntroTitle.AutoSize := False;
  IntroTitle.Font.Size := 20; IntroTitle.Font.Style := [fsBold]; IntroTitle.Font.Color := clRed;
  IntroTitle.Caption := 'STEP 1 - PICK THE FOLDERS';
  IntroWarning := TNewStaticText.Create(WizardForm);
  IntroWarning.Parent := IntroPage.Surface;
  IntroWarning.SetBounds(0, ScaleY(40), IntroPage.SurfaceWidth, ScaleY(72));
  IntroWarning.AutoSize := False; IntroWarning.WordWrap := True;
  IntroWarning.Font.Size := 16; IntroWarning.Font.Style := [fsBold]; IntroWarning.Font.Color := clRed;
  IntroWarning.Caption := 'This installer downloads a bunch of shit. Pick folders on a drive with space.';
  IntroModels := TNewStaticText.Create(WizardForm);
  IntroModels.Parent := IntroPage.Surface;
  IntroModels.SetBounds(0, ScaleY(116), IntroPage.SurfaceWidth, ScaleY(88));
  IntroModels.AutoSize := False; IntroModels.WordWrap := True;
  IntroModels.Font.Size := 13; IntroModels.Font.Style := [fsBold]; IntroModels.Font.Color := clRed;
  IntroModels.Caption := 'OmniVoice is about a 3.3 GB download in browser Initial Setup. Dependencies, the transcription model and caches need more. Pick the folders right.';
  IntroUnsigned := TNewStaticText.Create(WizardForm);
  IntroUnsigned.Parent := IntroPage.Surface;
  IntroUnsigned.SetBounds(0, ScaleY(210), IntroPage.SurfaceWidth, ScaleY(28));
  IntroUnsigned.AutoSize := False; IntroUnsigned.WordWrap := True;
  IntroUnsigned.Font.Size := 13; IntroUnsigned.Font.Style := [fsBold]; IntroUnsigned.Font.Color := clRed;
  IntroUnsigned.Caption := 'Unsigned for now, cause cba.';
  WizardForm.SelectDirLabel.Caption := 'Choose the root folder. Application files go in its app subfolder; models and recordings go in data.';
  WizardForm.DiskSpaceLabel.Visible := False;
  AppSize := TNewStaticText.Create(WizardForm);
  MakeSizeLabel(AppSize, WizardForm.DirEdit.Parent, WizardForm.DirEdit,
    WizardForm.DirBrowseButton, 'Est. 12-32+ GB' + #13#10 + 'app + data');
  DataPage := CreateInputDirPage(wpSelectDir, 'Data and model storage',
    'Choose where voices, audio, models and download caches are stored.',
    'By default, app and data are inside the destination you selected. Only tick the checkbox to store data elsewhere. Estimates include growing caches and recordings; data is preserved on uninstall.', False, '');
  DataPage.Add('Data folder:');
  ExistingData := GetPreviousData('DataRoot', DefaultDataPath);
  SeparateData := TNewCheckBox.Create(WizardForm);
  SeparateData.Parent := DataPage.Surface;
  SeparateData.SetBounds(0, DataPage.Edits[0].Top + ScaleY(48), DataPage.SurfaceWidth, ScaleY(25));
  SeparateData.Caption := 'Choose a separate data location';
  SeparateData.OnClick := @SeparateDataClick;
  DataPage.Values[0] := ExpandConstant('{param:DATADIR|' + ExistingData + '}');
  SeparateData.Checked := (ExpandConstant('{param:DATADIR|}') <> '') or
    ((GetPreviousData('DataRoot', '') <> '') and (CompareText(ExistingData, DefaultDataPath) <> 0));
  DataSize := TNewStaticText.Create(WizardForm);
  MakeSizeLabel(DataSize, DataPage.Surface, DataPage.Edits[0], DataPage.Buttons[0],
    'Est. 8-20+ GB' + #13#10 + 'models/cache');
  SyncDataPath;
  IntroTimer := SetTimer(0, 0, 100, CreateCallback(@IntroTick));

end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = IntroPage.ID then begin
    if not IntroSeen then begin
      IntroSeen := True;
      IntroUntil := SystemTicks + 5000;
    end;
    IntroTick(0, 0, 0, 0);
  end;
  if CurPageID = wpSelectDir then WizardForm.DiskSpaceLabel.Visible := False;
  if PreparationFailed and (CurPageID = wpPreparing) then WizardForm.NextButton.Enabled := False;
  if CurPageID = wpFinished then begin
    { Never opt the user into restarting Windows from this private-runtime installer. }
    WizardForm.NoRadio.Checked := True;
    WizardForm.YesRadio.Enabled := False;
  end;
  if CurPageID = DataPage.ID then SyncDataPath;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if PreparationFailed and (CurPageID = wpPreparing) then begin
    Result := False;
    Exit;
  end;
  if (CurPageID = IntroPage.ID) and not WizardSilent then
    Result := IntroSeen and (SystemTicks >= IntroUntil);
  if CurPageID = wpSelectDir then SyncDataPath;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := WizardSilent and (PageID = IntroPage.ID);
end;

procedure DeinitializeSetup;
begin
  if IntroTimer <> 0 then KillTimer(0, IntroTimer);
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'DataRoot', DataPage.Values[0]);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ExitCode: Integer; Device, Args: String;
begin
  Result := '';
  ExitCode := -1;
  NeedsRestart := False;
  PreparationFailed := False;
  LogButton.Visible := False;
  SetupLogPath := AddBackslash(DataPage.Values[0]) + 'logs\setup.log';
  ForceDirectories(ExpandConstant('{app}\app'));
  ExtractTemporaryFile('bootstrap.ps1'); ExtractTemporaryFile('common.ps1');
  ExtractTemporaryFile('ffmpeg.exe'); ExtractTemporaryFile('ffprobe.exe');
  ExtractTemporaryFile('dependencies.json'); ExtractTemporaryFile('verify-runtime.py');
  ExtractTemporaryFiles('{tmp}\pacttsclone-*.whl');
  Device := 'auto';
  { CPU/CUDA selection now happens in the browser's Initial Setup tab. }
  Args := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\bootstrap.ps1') +
    '" -PayloadDir "' + ExpandConstant('{tmp}') + '" -AppRoot "' + ExpandConstant('{app}\app') + '" -DataRoot "' + DataPage.Values[0] + '" -Device ' + Device;
  WizardForm.StatusLabel.Caption := 'Downloading dependencies. Follow progress in the setup console. Closing it cancels setup.';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Args,
    ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, ExitCode) then
    Result := 'Could not start dependency setup.'
  else if ExitCode <> 0 then
    Result := 'Dependency setup failed or was cancelled. Open the setup log for details. Go Back to retry, or Cancel to exit. No restart is required.';
  PreparationFailed := Result <> '';
  if PreparationFailed then begin
    NeedsRestart := False;
    WizardForm.NextButton.Enabled := False;
    if not FileExists(SetupLogPath) then begin
      SetupLogPath := ExpandConstant('{app}\setup-error.log');
      SaveStringToFile(SetupLogPath, Result + #13#10 + 'Dependency setup exit code: ' + IntToStr(ExitCode) + #13#10, False);
    end;
    LogButton.Visible := FileExists(SetupLogPath);
  end;
end;

