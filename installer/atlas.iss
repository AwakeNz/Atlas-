; A.T.L.A.S. — Inno Setup installer
; Build:  iscc /DMyAppVersion=0.3.0 installer\atlas.iss   (build.py does this)
;
; Design decisions that matter:
; - AppId is a FIXED GUID. Never change it. It is what makes Windows treat every
;   future version as an UPGRADE of this same app (one Apps & features entry),
;   not a second install.
; - Program files install to {autopf}\ATLAS. ALL user data lives in
;   {userappdata}\ATLAS (the app writes there via core/paths.py). The installer
;   NEVER creates or touches that folder on install/upgrade — so upgrades keep
;   every byte of settings, memory, plugins, skills and models.
; - AppMutex matches the mutex the app creates on startup (core/singleton.py),
;   so Setup can detect a running instance; CloseApplications (Restart Manager)
;   closes and relaunches it for silent in-place upgrades.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "A.T.L.A.S."
#define MyAppExeName "ATLAS.exe"
#define MyAppPublisher "AwakeNz"
#define MyAppURL "https://github.com/AwakeNz/Atlas-"

[Setup]
; ---- identity (DO NOT CHANGE AppId) ----
AppId={{7F3B2C6E-4A19-4E2A-9C7D-3E1A2B4C5D6E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}

; ---- install location + privileges (per-user fallback if no admin) ----
DefaultDirName={autopf}\ATLAS
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; ---- running-instance detection for clean upgrades ----
AppMutex=Global\ATLAS_Running_Mutex
CloseApplications=yes
RestartApplications=yes

; ---- output ----
OutputDir=..\dist
OutputBaseFilename=ATLAS-Setup-v{#MyAppVersion}
SetupIconFile=..\assets\atlas.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
WizardStyle=modern

; ---- size / speed (Optimizer) ----
Compression=lzma2/max
SolidCompression=yes

; ---- license ----
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startupicon"; Description: "Launch {#MyAppName} at Windows startup"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; ONEDIR: install the whole PyInstaller output folder (dist\ATLAS\*) into {app}.
; The bundled plugins/skills/web/wake/assets ride along inside _internal; the
; app materializes editable copies of plugins/skills into %APPDATA%\ATLAS on
; first run.
Source: "..\dist\ATLAS\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; "Launch at startup" via the Run key (NOT the Startup folder), per the spec.
; HKCU so it works for both machine-wide and per-user installs; removed on uninstall.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "ATLAS"; ValueData: """{app}\{#MyAppExeName}"""; \
    Flags: uninsdeletevalue; Tasks: startupicon

[Run]
; Optional "launch now" checkbox on the final wizard page. On silent upgrades
; RestartApplications relaunches the app, so skip this to avoid a double launch.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove anything the app wrote INTO the program dir (should be nothing in 0.3+,
; but pre-migration remnants get cleaned). User data is handled in [Code].
Type: filesandordirs; Name: "{app}\update"

[Code]
{ On uninstall, ask whether to keep user data. Default YES (keep). Only wipe
  %APPDATA%\ATLAS if the user explicitly declines. Skipped in silent mode so an
  automated uninstall never destroys data without consent. }
procedure CurUninstallStepChanged(CurStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurStep = usUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\ATLAS');
    if DirExists(DataDir) then
    begin
      if not UninstallSilent then
      begin
        if MsgBox('Keep your A.T.L.A.S. settings, memory and plugins?' + #13#10 +
                  '(Your data in ' + DataDir + ')' + #13#10#13#10 +
                  'Yes = keep it for a future reinstall.' + #13#10 +
                  'No  = permanently delete all of it.',
                  mbConfirmation, MB_YESNO or MB_DEFBUTTON1) = IDNO then
        begin
          DelTree(DataDir, True, True, True);
        end;
      end;
    end;
  end;
end;
