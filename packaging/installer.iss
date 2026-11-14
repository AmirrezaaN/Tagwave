; Inno Setup script for Tagwave.
; Build: ISCC.exe packaging\installer.iss   (after PyInstaller has produced build\dist\Tagwave)

#define AppName "Tagwave"
#define AppVersion "1.0.0"
#define AppExe "Tagwave.exe"
#define ProgId "Tagwave.exe"

[Setup]
AppId={{8E4C7A51-3B1D-4E2F-9A6C-5D7B2E91F0A4}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Tagwave-Setup-{#AppVersion}
SetupIconFile=..\assets\tagwave.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
WizardImageFile=..\assets\wizard-large.bmp
WizardSmallImageFile=..\assets\wizard-small.bmp
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.Integration=Windows integration:
english.ContextMenu=Add "Edit with Tagwave" to the right-click menu of music files and folders
english.SendTo=Add Tagwave to the "Send to" menu (handy for many files at once)
english.EditWith=Edit with Tagwave
english.OpenFolder=Open in Tagwave
english.NoWebView=Tagwave displays its interface with the Microsoft Edge WebView2 Runtime, which is part of Windows 11 and up-to-date Windows 10, but it wasn't found on this PC.%n%nSetup will continue. If Tagwave doesn't open afterwards, install "Microsoft Edge WebView2 Runtime" from Microsoft (or run Windows Update) and start it again.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "contextmenu"; Description: "{cm:ContextMenu}"; GroupDescription: "{cm:Integration}"
Name: "sendto"; Description: "{cm:SendTo}"; GroupDescription: "{cm:Integration}"

[Files]
Source: "..\build\dist\Tagwave\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{usersendto}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: sendto

[Registry]
; "Open with" list
Root: HKA; Subkey: "Software\Classes\Applications\{#ProgId}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: """{app}\{#AppExe}"",0"
Root: HKA; Subkey: "Software\Classes\Applications\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
; Folders: right-click a folder, or the background of an open folder
Root: HKA; Subkey: "Software\Classes\Directory\shell\Tagwave"; ValueType: string; ValueData: "{cm:OpenFolder}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Directory\shell\Tagwave"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\Tagwave\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\Tagwave"; ValueType: string; ValueData: "{cm:OpenFolder}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\Tagwave"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\Tagwave\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%V"""; Tasks: contextmenu
; Music files: "Edit with Tagwave" + listed in "Open with"
#dim Exts[22] {".mp3", ".flac", ".m4a", ".m4b", ".mp4", ".aac", ".ogg", ".oga", ".opus", ".spx", ".wav", ".aif", ".aiff", ".aifc", ".wma", ".asf", ".ape", ".wv", ".mpc", ".tta", ".ofr", ".dsf"}
#define i 0
#sub EmitExt
Root: HKA; Subkey: "Software\Classes\Applications\{#ProgId}\SupportedTypes"; ValueType: string; ValueName: "{#Exts[i]}"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\{#Exts[i]}\OpenWithList\{#AppExe}"; ValueType: string; ValueData: ""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\{#Exts[i]}\shell\Tagwave"; ValueType: string; ValueData: "{cm:EditWith}"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\{#Exts[i]}\shell\Tagwave"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\{#Exts[i]}\shell\Tagwave\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
#endsub
#for {i = 0; i < DimOf(Exts); i++} EmitExt

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\Tagwave"
Type: filesandordirs; Name: "{localappdata}\Temp\Tagwave"

[Code]
const
  WV2 = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasVersion(Root: Integer; Key: String): Boolean;
var
  V: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', V) and (V <> '') and (V <> '0.0.0.0');
end;

function WebView2Installed: Boolean;
begin
  Result := HasVersion(HKLM, 'SOFTWARE\WOW6432Node\' + WV2) or HasVersion(HKLM, 'SOFTWARE\' + WV2) or
            HasVersion(HKCU, 'Software\' + WV2);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not WebView2Installed) and (not WizardSilent) then
    MsgBox(ExpandConstant('{cm:NoWebView}'), mbInformation, MB_OK);
end;
