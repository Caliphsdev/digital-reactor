; ============================================================================
; digital_reactor.iss — Inno Setup 6 installer script for Digital Reactor
;
; Prerequisites:
;   1. Run PyInstaller first:   pyinstaller digital_reactor.spec --noconfirm
;   2. Confirm dist\DigitalReactor\DigitalReactor.exe exists
;   3. Compile this script:     ISCC installer\digital_reactor.iss
;      (or open in Inno Setup IDE and press F9)
;
; Output: installer\Output\DigitalReactor_Setup_v1.0.exe
; ============================================================================

#define AppName        "Digital Reactor"
#define AppVersion     "1.0"
#define AppPublisher   "Caliphs Zvinowanda"
#define AppExeName     "DigitalReactor.exe"
#define AppDescription "PFAS & CEC Wastewater Research Platform"
#define SourceDir      "..\dist\DigitalReactor"
#define IconFile       "..\ui\icons\favicon.ico"

; ----------------------------------------------------------------------------
[Setup]
; AppId is a PERMANENT GUID — do NOT change between releases.
; Changing it causes Windows to treat each version as a separate program.
AppId={{D4F8A2C1-9E3B-4D7A-B5F2-8C1E6A4D0B93}

AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments={#AppDescription}

; Install into Program Files (respects x64/x86 automatically)
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Output
OutputDir=Output
OutputBaseFilename=DigitalReactor_Setup_v{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}

; Compression (lzma2 ultra gives best size for a Qt bundle)
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; UI
WizardStyle=modern
WizardResizable=yes

; Platform requirements — 64-bit only (Python 3.14 x64 build)
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; Privileges — writing to Program Files needs admin
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline

; Restart handling
CloseApplications=yes
RestartApplications=no

; Installer behaviour
; Skips the "select Start Menu folder" page
DisableProgramGroupPage=yes
DisableReadyPage=no

; ----------------------------------------------------------------------------
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ----------------------------------------------------------------------------
[Tasks]
Name: "desktopicon"; \
  Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; \
  Flags: unchecked

; ----------------------------------------------------------------------------
[Files]
; Visual C++ 2022 Redistributable — required by python314.dll and Qt DLLs.
; Extracted to a temp dir so it can be run before the app is launched.
Source: "vc_redist.x64.exe"; \
  DestDir: "{tmp}"; \
  Flags: deleteafterinstall

; Copy the entire PyInstaller dist folder, preserving sub-directory structure.
; "ignoreversion" prevents Inno Setup from comparing file versions on update —
; PyInstaller bundles don't embed proper version metadata in every DLL.
Source: "{#SourceDir}\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; ----------------------------------------------------------------------------
[Icons]
; Start Menu
Name: "{group}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  WorkingDir: "{app}"; \
  Comment: "{#AppDescription}"

Name: "{group}\Uninstall {#AppName}"; \
  Filename: "{uninstallexe}"

; Desktop (only if task selected)
Name: "{autodesktop}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  WorkingDir: "{app}"; \
  Comment: "{#AppDescription}"; \
  Tasks: desktopicon

; ----------------------------------------------------------------------------
[Run]
; Install Visual C++ 2022 Redistributable silently first.
; /install /quiet /norestart — standard Microsoft silent install flags.
; The registry check in [Code] below skips this if already installed.
Filename: "{tmp}\vc_redist.x64.exe"; \
  Parameters: "/install /quiet /norestart"; \
  StatusMsg: "Installing Visual C++ Runtime..."; \
  Check: VCRedistNeedsInstall; \
  Flags: waituntilterminated

; "Launch after install" checkbox on the final wizard page
Filename: "{app}\{#AppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

; ----------------------------------------------------------------------------
[UninstallDelete]
; Remove any .pyc caches generated inside the install folder at runtime
Type: filesandordirs; Name: "{app}\__pycache__"

; ----------------------------------------------------------------------------
; NOTE: User data in %APPDATA%\DigitalReactor\ (reactor.db, trained ML models,
; backups) is intentionally NOT touched by the installer or uninstaller.
; The researcher's data survives any number of upgrades or reinstalls.
; To fully remove user data, the researcher must manually delete:
;   %APPDATA%\DigitalReactor\
; ----------------------------------------------------------------------------

[Code]
// ---------------------------------------------------------------------------
// VC++ 2022 Redistributable check
// Reads the installed version from the registry. Skips installation when the
// runtime is already present (version >= 14.40), so repeated installs are fast.
// ---------------------------------------------------------------------------
function VCRedistNeedsInstall(): Boolean;
var
  sVersion: String;
  iMajor, iMinor: Integer;
  sParts: TStringList;
begin
  Result := True;
  // Check for VC++ 2022 / MSVC 14.x (x64)
  if RegQueryStringValue(
      HKLM,
      'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
      'Version',
      sVersion) then
  begin
    // sVersion is like "v14.44.35112.0" — strip leading 'v'
    if (Length(sVersion) > 1) and (sVersion[1] = 'v') then
      sVersion := Copy(sVersion, 2, Length(sVersion));
    sParts := TStringList.Create;
    try
      sParts.Delimiter := '.';
      sParts.DelimitedText := sVersion;
      if sParts.Count >= 2 then
      begin
        iMajor := StrToIntDef(sParts[0], 0);
        iMinor := StrToIntDef(sParts[1], 0);
        // Already have 14.40 or higher — no reinstall needed
        if (iMajor > 14) or ((iMajor = 14) and (iMinor >= 40)) then
          Result := False;
      end;
    finally
      sParts.Free;
    end;
  end;
end;

// ---------------------------------------------------------------------------
// Upgrade handling: if the same AppId is already installed, silently uninstall
// the previous version before installing the new one.
// ---------------------------------------------------------------------------
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := ExpandConstant(
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function UnInstallOldVersion(): Integer;
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
  Result := 0;
  sUnInstallString := GetUninstallString();
  if sUnInstallString <> '' then
  begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    if Exec(sUnInstallString, '/SILENT /NORESTART /SUPPRESSMSGBOXES', '',
            SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := iResultCode
    else
      Result := 1;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) then
  begin
    if (IsUpgrade()) then
      UnInstallOldVersion();
  end;
end;
