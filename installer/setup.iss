; Inno Setup script for LithnodeSetup.exe. Build everything with installer\build.ps1.
; build.ps1 passes the version from version.py (/DAppVersion=...)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3C2A51-6B7E-4E9D-9C1A-1E5B7D4C2A90}
AppName=Lithnode
AppVersion={#AppVersion}
AppVerName=Lithnode {#AppVersion}
AppPublisher=Lithnode
VersionInfoProductName=Lithnode
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoDescription=Lithnode installer
AppPublisherURL=https://lithnode.com
AppSupportURL=https://lithnode.com
DefaultDirName={localappdata}\Programs\Lithnode
DefaultGroupName=Lithnode
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableWelcomePage=no
DisableReadyPage=yes
DisableFinishedPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=LithnodeSetup
SetupIconFile=lithnode.ico
; one click: a small dark rounded window instead of wizard pages (oneclick.iss; art: make_icon.py)
WizardStyle=modern dark
WizardBackColor=#0e0e10
UninstallDisplayIcon={app}\Lithnode.exe
UninstallDisplayName=Lithnode
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; oneclick.iss closes a running Lithnode itself, so Inno never stops to ask about files in use
CloseApplications=no

[Files]
; the app window (Electron) at the top, the engine and Claude Pet (PyInstaller) in server\
Source: "..\dist\Lithnode-win32-x64\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\dist\Lithnode\*"; DestDir: "{app}\server"; Flags: recursesubdirs createallsubdirs ignoreversion

#include "oneclick.iss"

[Icons]
Name: "{autoprograms}\Lithnode"; Filename: "{app}\Lithnode.exe"

[Run]
Filename: "{app}\server\lithnode-cli.exe"; Parameters: "install-pet"; Check: WantPet; Flags: runhidden; StatusMsg: "Adding Claude Pet to Claude Code..."
Filename: "{app}\server\lithnode-cli.exe"; Parameters: "uninstall-pet"; Check: not WantPet; Flags: runhidden
Filename: "{app}\Lithnode.exe"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Lithnode.exe /IM lithnode-server.exe"; Flags: runhidden; RunOnceId: "StopLithnode"
Filename: "{app}\server\lithnode-cli.exe"; Parameters: "uninstall-pet"; Flags: runhidden; RunOnceId: "RemovePetHooks"

[Messages]
SetupWindowTitle=Install Lithnode
